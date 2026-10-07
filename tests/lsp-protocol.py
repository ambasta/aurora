#!/usr/bin/env python3
"""Focused real-server protocol checks; never builds or runs generated Aurora code."""

import hashlib
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import tempfile
import time

SERVER = Path(sys.argv[1]).resolve()
CASES = 0
CHECKS = 0
GOOD = "module demo; auto answer() -> i64 { return 42; }\n"
BAD = "module demo;\n@"
DEP_GOOD = "export module dep; auto dep_value() -> i64 { return 0; }\n"


def require(value, reason):
    global CHECKS
    CHECKS += 1
    if not value:
        raise AssertionError(reason)


def notification(method, params=None):
    result = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        result["params"] = params
    return result


def request(method, id=1, params=None):
    return dict(notification(method, params), id=id)


def frame(message):
    payload = message if isinstance(message, bytes) else json.dumps(message, ensure_ascii=False).encode()
    return f"Content-Length: {len(payload)}\r\n\r\n".encode() + payload


def diagnostic_metadata(message):
    diagnostics = []
    if message.get("method") == "textDocument/publishDiagnostics":
        diagnostics = list(message["params"]["diagnostics"])
        require(len(diagnostics) <= 128, "each URI publication stays within the diagnostic count bound")
    failure = message.get("error", {}).get("data", {}).get("diagnostic")
    if failure is not None:
        diagnostics.append(failure)
    for diagnostic in diagnostics:
        severity = diagnostic["severity"]
        require(type(severity) is int and severity in (1, 2), "only error/warning severities are published")
        require(
            diagnostic["data"]["firstErrorOnly"] is (severity == 1),
            "firstErrorOnly describes errors, never lint warnings",
        )


def parse_frames(raw):
    messages = []
    while raw:
        header, separator, raw = raw.partition(b"\r\n\r\n")
        require(bool(separator), "stdout contains only complete framed protocol messages")
        require(header.startswith(b"Content-Length: "), "stdout has clean framing")
        count = int(header[len(b"Content-Length: ") :])
        require(0 <= count <= 8 * 1024 * 1024, "encoded UTF-8 output stays within the wire payload bound")
        require(len(raw) >= count, "output body is complete")
        message = json.loads(raw[:count])
        diagnostic_metadata(message)
        messages.append(message)
        raw = raw[count:]
    return messages


def run(messages=(), roots=(), raw=None, status=0):
    global CASES
    arguments = [str(SERVER)]
    for root in roots:
        arguments += ["--module-root", str(root)]
    body = raw if raw is not None else b"".join(map(frame, messages))
    completed = subprocess.run(arguments, input=body, capture_output=True, timeout=20)
    CASES += 1
    require(
        completed.returncode == status,
        f"server exit {completed.returncode}, expected {status}: {completed.stderr.decode(errors='replace')}",
    )
    return parse_frames(completed.stdout), completed.stderr.decode(errors="replace")


def opened(path, text=BAD, version=1, uri=None):
    return notification(
        "textDocument/didOpen",
        {"textDocument": {"uri": uri or path.as_uri(), "languageId": "aurora", "version": version, "text": text}},
    )


def changed(path, text=GOOD, version=2, uri=None):
    return notification(
        "textDocument/didChange",
        {"textDocument": {"uri": uri or path.as_uri(), "version": version}, "contentChanges": [{"text": text}]},
    )


def closed(path, uri=None):
    return notification("textDocument/didClose", {"textDocument": {"uri": uri or path.as_uri()}})


def phases(actions, roots=(), initialize_params=None):
    params = {"capabilities": {}} if initialize_params is None else initialize_params
    messages = [request("initialize", 1, params), notification("initialized", {})]
    for index, action in enumerate(actions):
        messages += [action, request("aurora/testFence", index + 100)]
    messages += [request("shutdown", 2), notification("exit")]
    outputs, logs = run(messages, roots)
    require(
        outputs[0]["result"]["capabilities"]["textDocumentSync"] == {"openClose": True, "change": 1},
        "full sync advertised",
    )
    require(outputs[0]["result"]["capabilities"]["positionEncoding"] == "utf-16", "UTF-16 advertised")
    stages, pending = [], []
    for output in outputs[1:]:
        if "id" in output:
            if output["id"] == 2:
                require(output["result"] is None, "shutdown response")
            else:
                require(output["error"]["code"] == -32601, "unknown requests rejected")
                stages.append(pending)
                pending = []
        else:
            require(
                output["method"] == "textDocument/publishDiagnostics", "diagnostics are the only unsolicited output"
            )
            pending.append(output["params"])
    require(len(stages) == len(actions), "all phases completed")
    return stages, logs


def by_uri(stage, path):
    return next(value for value in stage if value["uri"] == path.as_uri())


def lint_warnings(publication, expected, truncated_messages=False):
    require(len(publication["diagnostics"]) == len(expected), "exact number of root lint warnings")
    for diagnostic, (name, line, character) in zip(publication["diagnostics"], expected):
        require(
            diagnostic["code"] == "AU6001" and diagnostic["severity"] == 2 and diagnostic["source"] == "aurora",
            "lint preserves compiler warning identity",
        )
        message = f"local binding '{name}' is never read"
        if truncated_messages:
            message = message[:4096] + " [truncated]"
        require(diagnostic["message"] == message, "exact compiler lint message or explicit bounded prefix")
        require(
            diagnostic["range"]
            == {
                "start": {"line": line, "character": character},
                "end": {"line": line, "character": character + len(name)},
            },
            "lint warnings preserve source order and exact half-open identifier ranges",
        )
        require(diagnostic["data"] == {"rangeKnown": True, "firstErrorOnly": False}, "precise warning metadata")


def lint_limit(publication, omitted):
    require(len(publication["diagnostics"]) == 128, "a truncated publication includes its notice within the limit")
    notice = publication["diagnostics"][-1]
    require(
        notice["code"] == "aurora-lsp-diagnostics-limit"
        and notice["source"] == "aurora-lsp"
        and notice["severity"] == 2,
        "truncation notice is explicitly server-owned, not a compiler finding",
    )
    require(
        notice["range"] == {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 0}}
        and notice["data"] == {"rangeKnown": False, "firstErrorOnly": False, "omittedWarnings": omitted},
        "truncation reports an honest unknown location and the exact omitted warning count",
    )
    require(
        notice["message"] == f"[location unavailable] Diagnostic publication truncated; {omitted} warnings omitted.",
        "truncation is explained without claiming precise compiler provenance",
    )


with tempfile.TemporaryDirectory(prefix="aurora-lsp-test-") as directory:
    root = Path(directory)
    source = root / "café-中 space.au"
    source.write_text(GOOD)
    original = source.read_bytes()
    original_stat = source.stat()
    stages, logs = phases([opened(source), changed(source), closed(source)])
    first = by_uri(stages[0], source)
    require(first["version"] == 1 and len(first["diagnostics"]) == 1, "open publishes one versioned first error")
    require(first["diagnostics"][0]["code"] == "AU1001", "compiler diagnostic code")
    require(first["diagnostics"][0]["message"] == "unsupported character", "location-neutral lexical message")
    require(
        first["diagnostics"][0]["range"] == {"start": {"line": 1, "character": 0}, "end": {"line": 1, "character": 1}},
        "compiler range converted to LSP",
    )
    require(
        by_uri(stages[1], source) == {"uri": source.as_uri(), "version": 2, "diagnostics": []},
        "valid edit clears diagnostics",
    )
    require(
        by_uri(stages[2], source) == {"uri": source.as_uri(), "diagnostics": []},
        "close clears diagnostics without stale version",
    )
    require(logs == "", "normal server stderr is quiet")
    require(
        source.read_bytes() == original and sorted(root.iterdir()) == [source],
        "unsaved edits never mutate source or create artifacts",
    )
    require(
        (source.stat().st_mtime_ns, source.stat().st_ctime_ns)
        == (original_stat.st_mtime_ns, original_stat.st_ctime_ns),
        "unsaved edits do not rewrite the same disk bytes",
    )

    stages, logs = phases(
        [opened(source, BAD, 10), changed(source, GOOD, 9), changed(source, GOOD, 10), changed(source, GOOD, 11)]
    )
    require(stages[1] == stages[2] == [], "stale and repeated versions cannot publish")
    require(
        by_uri(stages[3], source)["version"] == 11 and not by_uri(stages[3], source)["diagnostics"],
        "newest version accepted",
    )
    require(logs.count("ignored stale document version") == 2, "stale versions reported on stderr")
    stages, logs = phases([opened(source), changed(source, " " * (1024 * 1024 + 1), 2), changed(source, GOOD, 2)])
    require(
        stages[1] == [] and by_uri(stages[2], source)["version"] == 2, "oversized edit preserves the accepted version"
    )
    stages, _ = phases([opened(source, GOOD, -(2**31)), closed(source), opened(source, BAD, -(2**31))])
    require(by_uri(stages[2], source)["version"] == -(2**31), "reopen starts a fresh signed-version sequence")
    stages, logs = phases([opened(source), notification("$/cancelRequest", {"id": 999}), changed(source)])
    require(
        stages[1] == [] and not logs and not by_uri(stages[2], source)["diagnostics"],
        "synchronous server ignores cancellation notification without changing state",
    )
    boundary_text = GOOD + " " * (1024 * 1024 - len(GOOD))
    stages, _ = phases([opened(source, boundary_text)])
    require(not by_uri(stages[0], source)["diagnostics"], "exact 1 MiB existing-file overlay is accepted")

    for text, expected in [
        ("😀", {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 2}}),
        ("// café 😀\r\nmodule demo;\r\n@", {"start": {"line": 2, "character": 0}, "end": {"line": 2, "character": 1}}),
        ("module demo", {"start": {"line": 0, "character": 11}, "end": {"line": 0, "character": 11}}),
    ]:
        stages, _ = phases([opened(source, text)])
        require(by_uri(stages[0], source)["diagnostics"][0]["range"] == expected, "Unicode/CRLF/EOF source range")
    require(
        by_uri(stages[0], source)["diagnostics"][0]["message"] == "expected ';' (found '<eof>')",
        "location-neutral parser message",
    )
    stages, _ = phases([opened(source, "module demo; auto answer() -> i64 { return true; }")])
    require(by_uri(stages[0], source)["diagnostics"][0]["code"] == "AU3001", "semantic diagnostics use shared checker")

    require(
        by_uri(stages[0], source)["diagnostics"][0]["message"] == "expected i64, got bool",
        "location-neutral semantic message",
    )
    stages, _ = phases([opened(source, "module demo;\n\nauto answer() -> i64 {\n    return missing();\n}\n")])
    resolver_error = by_uri(stages[0], source)["diagnostics"][0]
    require(
        resolver_error["code"] == "AU4001"
        and resolver_error["message"] == "unknown function 'missing' in defining module demo"
        and resolver_error["range"] == {"start": {"line": 3, "character": 11}, "end": {"line": 3, "character": 18}},
        "resolver publishes its real UTF-16 token range without embedded coordinates",
    )

    imported = root / "dep.au"
    imported.write_text(DEP_GOOD)
    caller = "module demo; import dep; auto answer() -> i64 { return 42; }"
    for imported_text, code, message in (
        ("export module dep;\nauto broken() -> i64 { return 0 }", "AU2001", "module dep: expected ';' (found '}')"),
        ("export module dep;\nauto broken() -> i64 { return true; }", "AU3001", "expected i64, got bool"),
        (
            "export module dep;\nauto broken() -> i64 { return missing(); }",
            "AU4001",
            "unknown function 'missing' in defining module dep",
        ),
    ):
        imported.write_text(imported_text)
        stages, _ = phases([opened(source, caller)], [root])
        failure = by_uri(stages[0], imported)["diagnostics"][0]
        require(
            failure["code"] == code and failure["message"] == message and failure["range"]["start"]["line"] == 1,
            "imported parser/semantic/resolver message and original URI/range",
        )
    imported.write_text(DEP_GOOD)
    stages, _ = phases([opened(source, caller)])
    missing_root = by_uri(stages[0], source)["diagnostics"][0]
    require(
        missing_root["code"] == "AU4001" and not missing_root["data"]["rangeKnown"],
        "imports require explicit roots and unknown ranges stay honest",
    )
    stages, _ = phases(
        [
            opened(source, caller),
            opened(imported, "export module dep;\n@"),
            changed(imported, DEP_GOOD, 2),
            changed(imported, "export module dep;\n@", 3),
            closed(imported),
        ],
        [root],
    )
    require(not by_uri(stages[0], source)["diagnostics"], "explicit root import succeeds")
    require(len(by_uri(stages[1], imported)["diagnostics"]) == 1, "imported errors publish once on actual source URI")
    require(by_uri(stages[1], imported)["version"] == 1, "imported overlay version is preserved")
    require(
        by_uri(stages[1], imported)["diagnostics"][0]["message"]
        in ("unsupported character", "module dep: unsupported character"),
        "imported error preserves context without embedded coordinates",
    )
    require(not by_uri(stages[2], imported)["diagnostics"], "import fix clears all root projections")
    require(
        not by_uri(stages[4], imported)["diagnostics"] and "version" not in by_uri(stages[4], imported),
        "closing import drops overlay and clears stale diagnostics",
    )
    require(imported.read_text() == DEP_GOOD, "import overlay never writes disk")
    stages, _ = phases([opened(source, caller), opened(imported, "export module dep;\n")], [root])
    standalone_error = by_uri(stages[-1], imported)["diagnostics"][0]
    require(
        not by_uri(stages[-1], source)["diagnostics"]
        and standalone_error["code"] == "AU4001"
        and "module graph must contain a function" in standalone_error["message"],
        "an import-only interface still receives the shared checker's standalone-root limitation",
    )
    second = root / "second.au"
    second.write_text("module second; auto answer() -> i64 { return 42; }")
    second_caller = caller.replace("module demo;", "module second;")
    stages, _ = phases(
        [
            opened(source, caller),
            opened(second, second_caller),
            opened(imported, "export module dep;\n@"),
            closed(source),
            closed(second),
            closed(imported),
        ],
        [root],
    )
    require(
        len(by_uri(stages[2], imported)["diagnostics"]) == 1, "several open importers deduplicate the imported error"
    )
    require(
        not by_uri(stages[3], source)["diagnostics"] and by_uri(stages[3], imported)["diagnostics"],
        "closing one importer preserves the other current error",
    )
    require(all(not item["diagnostics"] for item in stages[-1]), "closing every owner clears imported publications")
    imported.write_text("export module dep;\n@")
    stages, _ = phases([opened(imported, DEP_GOOD), opened(source, caller), closed(imported)], [root])
    restored_disk_error = by_uri(stages[-1], imported)
    require(
        len(restored_disk_error["diagnostics"]) == 1 and "version" not in restored_disk_error,
        "closing a valid import overlay republishes an invalid disk import without a stale version",
    )
    imported.write_text(DEP_GOOD)

    absent = root / "absent.au"
    stages, _ = phases([opened(absent, GOOD), closed(absent)])
    require(
        by_uri(stages[0], absent)["diagnostics"][0]["code"] == "AU4001" and not absent.exists(),
        "new nonexistent files are explicitly unsupported without writes",
    )
    symlink = root / "linked.au"
    symlink.symlink_to(source)
    stages, _ = phases([opened(symlink, GOOD)])
    require(by_uri(stages[0], symlink)["diagnostics"][0]["code"] == "AU4001", "overlay cannot bypass no-symlink policy")
    link = root / "path-link"
    link.symlink_to(root, target_is_directory=True)
    for middle in ["path-link/..", "missing/..", "path-link/%2e%2e"]:
        uri = root.as_uri() + "/" + middle + "/" + source.name
        stages, logs = phases([opened(source, GOOD, uri=uri)])
        require(
            stages == [[]] and "parent traversal" in logs,
            "decoded parent walks cannot normalize away a symlink or missing path",
        )
    for path in [absent, symlink]:
        stages, _ = phases([opened(path, GOOD)], initialize_params={"initializationOptions": {"lint": True}})
        diagnostics = by_uri(stages[0], path)["diagnostics"]
        require(
            len(diagnostics) == 1 and diagnostics[0]["code"] == "AU4001" and diagnostics[0]["severity"] == 1,
            "lint cannot admit nonexistent or symlink source files through overlays",
        )
    require(not absent.exists() and symlink.is_symlink(), "lint source rejection cannot create or replace files")
    uri = root.as_uri() + "/path-link/%2e%2e/" + source.name
    stages, logs = phases([opened(source, GOOD, uri=uri)], initialize_params={"initializationOptions": {"lint": True}})
    require(stages == [[]] and "parent traversal" in logs, "lint cannot normalize away decoded parent URI components")
    for import_root in [root / "path-link" / "..", root / "missing" / ".."]:
        outputs, logs = run(roots=[import_root], status=1)
        require(not outputs and "parent traversal" in logs, "CLI import roots reject parent walks before normalization")
    for uri in [
        "file://remote/tmp/x.au",
        "file:///tmp/%00.au",
        "file:///tmp/%GG.au",
        "file:///tmp/%FF.au",
        "untitled:new.au",
    ]:
        stages, logs = phases([opened(source, uri=uri)])
        require(stages == [[]] and logs, "invalid URI notification rejected without state")
    bad_change = changed(source)
    bad_change["params"]["contentChanges"][0]["range"] = {"start": {}, "end": {}}
    stages, logs = phases([opened(source), bad_change, changed(source, GOOD, 2)])
    require(
        stages[1] == [] and by_uri(stages[2], source)["version"] == 2,
        "incremental change rejection preserves old version",
    )
    stages, logs = phases([opened(source), opened(source, GOOD, 5), changed(source, GOOD, 2)])
    require(
        stages[1] == [] and not by_uri(stages[2], source)["diagnostics"], "duplicate open does not replace document"
    )
    for version in [True, 1.5, 2**63, -(2**31) - 1]:
        stages, logs = phases([opened(source, version=version)])
        require(stages == [[]] and logs, "invalid document version rejected")
    stages, logs = phases([opened(source, " " * (1024 * 1024 + 1))])
    require(stages == [[]] and "storage exceeds limit" in logs, "per-document bound")
    actions = [opened(root / f"bounded-{i}.au", " " * (1024 * 1024)) for i in range(5)]
    stages, logs = phases(actions)
    require(stages[-1] == [] and "storage exceeds limit" in logs, "total open document bound")
    actions = [opened(root / f"count-{i}.au", GOOD) for i in range(33)]
    stages, logs = phases(actions)
    require(stages[-1] == [] and "storage exceeds limit" in logs, "open document count bound")


with tempfile.TemporaryDirectory(prefix="aurora-lsp-lint-test-") as directory:
    root = Path(directory)
    source = root / "lint café-中.au"
    second = root / "second.au"
    imported = root / "dep.au"
    warning_text = "module demo;\nauto answer() -> i64 {\n    i64 unused = 7;\n    return 42;\n}\n"
    dependency_text = "export module dep;\nauto dep_value() -> i64 {\n    i64 imported_unused = 1;\n    return 0;\n}\n"
    caller = warning_text.replace("module demo;", "module demo; import dep;")
    independent = warning_text.replace("module demo;", "module second;")
    lint_params = {"initializationOptions": {"lint": True}}
    expected_warning = [("unused", 2, 8)]
    expected_imported = [("imported_unused", 2, 8)]
    for path, text in [(source, BAD), (second, GOOD), (imported, dependency_text)]:
        path.write_text(text)
        path.chmod(0o444)
    original_files = {path: (path.read_bytes(), path.stat()) for path in root.iterdir()}
    original_directory = root.stat()

    # Missing, null, empty and false options all retain the original check-only session.
    actions = [opened(source, warning_text), changed(source, BAD), changed(source, warning_text, 3), closed(source)]
    check_only = None
    for params in [
        None,
        {},
        {"initializationOptions": None},
        {"initializationOptions": {}},
        {"initializationOptions": {"lint": False}},
    ]:
        stages, logs = phases(actions, initialize_params=params)
        require(not logs, "valid check-only initialization options keep stderr quiet")
        require(not by_uri(stages[0], source)["diagnostics"], "lint is disabled unless explicitly true")
        require(by_uri(stages[1], source)["diagnostics"][0]["code"] == "AU1001", "check-only still reports errors")
        require(not by_uri(stages[2], source)["diagnostics"], "check-only recovery never leaks warnings")
        if check_only is not None:
            require(stages == check_only, "default, null, empty and false lint settings are equivalent")
        check_only = stages

    for invalid in [
        False,
        True,
        0,
        1,
        "",
        "lint",
        [],
        [{"lint": True}],
        {"lint": None},
        {"lint": 0},
        {"lint": 1.0},
        {"lint": "true"},
        {"lint": []},
        {"lint": {}},
        {"unknown": True},
        {"lint": True, "unknown": False},
        {"moduleRoots": [str(root)]},
    ]:
        outputs, logs = run(
            [
                request("initialize", 3, {"initializationOptions": invalid}),
                opened(source, GOOD, 99),
                request("aurora/testFence", 4),
                request("initialize", 1, lint_params),
                opened(source, warning_text),
                request("shutdown", 2),
                notification("exit"),
            ]
        )
        require(len(outputs) == 5 and not logs, "invalid options neither publish nor retain pre-initialize documents")
        require(
            outputs[0]["id"] == 3 and outputs[0]["error"]["code"] == -32602 and "result" not in outputs[0],
            "invalid initialization options return InvalidParams",
        )
        require(outputs[1]["error"]["code"] == -32002, "invalid options do not initialize the session")
        require(outputs[2]["id"] == 1 and "result" in outputs[2], "valid initialization can retry after rejection")
        publication = outputs[3]["params"]
        require(publication["uri"] == source.as_uri() and publication["version"] == 1, "retry accepts fresh state")
        lint_warnings(publication, expected_warning)
        require(outputs[4]["id"] == 2 and outputs[4]["result"] is None, "recovered lint session shuts down normally")

    for enabled in [False, True]:
        outputs, logs = run(
            [
                request("initialize", 1, {"initializationOptions": {"lint": enabled}}),
                opened(source, warning_text),
                request("initialize", 4, {"initializationOptions": {"lint": not enabled}}),
                request("initialize", 5, {"initializationOptions": {"unknown": True}}),
                notification("workspace/didChangeConfiguration", {"settings": {"lint": not enabled}}),
                changed(source, warning_text),
                request("shutdown", 2),
                notification("exit"),
            ]
        )
        replies = {value["id"]: value for value in outputs if "id" in value}
        require(
            replies[4]["error"]["code"] == replies[5]["error"]["code"] == -32600,
            "duplicate initialization remains InvalidRequest even when its options are invalid",
        )
        publications = [value["params"] for value in outputs if "method" in value]
        require(
            len(publications) == 2 and not logs, "duplicate initialization and unsupported configuration stay quiet"
        )
        for version, publication in enumerate(publications, 1):
            require(publication["version"] == version, "reinitialization and configuration preserve document state")
            lint_warnings(publication, expected_warning if enabled else [])

    # A later error must discard even a successfully analyzed earlier function's findings.
    error_text = warning_text + "auto broken() -> i64 { return false; }\n"
    stages, logs = phases(
        [
            opened(source, warning_text),
            changed(source, error_text),
            changed(source, warning_text, 3),
            changed(source, GOOD, 4),
            closed(source),
        ],
        initialize_params=lint_params,
    )
    lint_warnings(by_uri(stages[0], source), expected_warning)
    failure = by_uri(stages[1], source)
    require(
        failure["version"] == 2
        and len(failure["diagnostics"]) == 1
        and failure["diagnostics"][0]["code"] == "AU3001"
        and failure["diagnostics"][0]["severity"] == 1,
        "a graph error replaces all warnings with the compiler's first error",
    )
    lint_warnings(by_uri(stages[2], source), expected_warning)
    require(by_uri(stages[2], source)["version"] == 3, "corrected snapshot restores versioned warnings")
    require(
        by_uri(stages[3], source) == {"uri": source.as_uri(), "version": 4, "diagnostics": []},
        "removing unread locals clears prior warnings",
    )
    require(
        by_uri(stages[4], source) == {"uri": source.as_uri(), "diagnostics": []} and not logs,
        "closing a lint root clears its publication without a stale version",
    )

    ordered_text = (
        "module demo;\nauto first() -> i64 {\n    i64 zeta = 1;\n    bool alpha = false;\n    return 0;\n}\n"
        "auto answer() -> i64 {\n    i64 repeated = 2;\n    { i64 repeated = 3; }\n    return 42;\n}\n"
    )
    stages, _ = phases([opened(source, ordered_text)], initialize_params=lint_params)
    lint_warnings(by_uri(stages[0], source), [("zeta", 2, 8), ("alpha", 3, 9), ("repeated", 7, 8), ("repeated", 8, 10)])
    underscore_text = (
        "module demo;\nauto answer() -> i64 {\n    i64 _ = 1;\n    i64 _intentional = 2;\n"
        "    i64 a_b = 3;\n    return 42;\n}\n"
    )
    stages, _ = phases([opened(source, underscore_text)], initialize_params=lint_params)
    lint_warnings(by_uri(stages[0], source), [("a_b", 4, 8)])

    for newline in ["\r\n", "\n"]:
        unicode_text = newline.join(
            [
                "// café 中 😀",
                "module demo;",
                "auto answer() -> i64 {",
                "    // avant 😀 café",
                "\ti64 unused = 7;",
                "    return 42;",
                "}",
                "",
            ]
        )
        stages, logs = phases([opened(source, unicode_text)], initialize_params=lint_params)
        lint_warnings(by_uri(stages[0], source), [("unused", 4, 5)])
        require(not logs, "Unicode comments with LF/CRLF terminators lint without protocol noise")

    # Aurora line comments end at LF, not bare CR. Keep that lexer contract
    # while exercising LSP's CR position accounting on accepted source bytes.
    cr_text = "module demo;\rauto answer() -> i64 {\r\ti64 unused = 7;\rreturn 42;\r}\r"
    for prefix, line in [("", 2), ("// café 中 😀\n", 3)]:
        stages, logs = phases([opened(source, prefix + cr_text)], initialize_params=lint_params)
        lint_warnings(by_uri(stages[0], source), [("unused", line, 5)])
        require(not logs, "bare CR positions remain correct after a valid Unicode line comment")
    stages, _ = phases([opened(source, "// café 中 😀\r" + cr_text)], initialize_params=lint_params)
    comment_failure = by_uri(stages[0], source)["diagnostics"]
    require(
        len(comment_failure) == 1 and comment_failure[0]["code"] == "AU2001" and comment_failure[0]["severity"] == 1,
        "bare CR does not terminate a compiler line comment or create lint findings",
    )

    stages, logs = phases(
        [
            opened(source, warning_text, 10),
            changed(source, GOOD, 9),
            changed(source, GOOD, 10),
            opened(second, BAD, 20),
            changed(second, independent, 21),
            closed(second),
        ],
        initialize_params=lint_params,
    )
    require(stages[1] == stages[2] == [], "stale lint changes cannot clear warnings or publish")
    require(logs.count("ignored stale document version") == 2, "stale lint changes retain existing log behavior")
    for stage in stages[3:]:
        lint_warnings(by_uri(stage, source), expected_warning)
        require(by_uri(stage, source)["version"] == 10, "independent refresh preserves the accepted warning snapshot")
    second_failure = by_uri(stages[3], second)
    require(
        len(second_failure["diagnostics"]) == 1 and second_failure["diagnostics"][0]["severity"] == 1,
        "one broken root can publish an error concurrently with another root's warning",
    )
    lint_warnings(by_uri(stages[4], second), expected_warning)

    alias = source.as_uri().replace("file:///", "file://localhost/")
    stages, logs = phases(
        [
            opened(source, warning_text, 10, uri=alias),
            changed(source, GOOD, 11),
            closed(source),
            opened(source, GOOD, 11),
            opened(second, GOOD),
            changed(source, GOOD, 11, uri=alias),
            closed(source, uri=alias),
        ],
        initialize_params=lint_params,
    )
    require(stages[1] == stages[2] == stages[3] == [], "URI mismatches and duplicate opens cannot replace lint state")
    aliased_warning = next(value for value in stages[4] if value["uri"] == alias)
    lint_warnings(aliased_warning, expected_warning)
    require(aliased_warning["version"] == 10, "lint publication preserves the exact accepted URI and version")
    require(
        {"uri": alias, "version": 11, "diagnostics": []} in stages[5]
        and {"uri": alias, "diagnostics": []} in stages[6],
        "only the exact open URI can clear or close a lint snapshot",
    )
    require(logs.count("requires the open document URI") == 2, "lint URI mismatches remain observable")

    # Imported findings appear only while the dependency is independently open as a root.
    imported_error = dependency_text.replace("return 0;", "return false;")
    stages, logs = phases(
        [
            opened(source, caller, 10),
            opened(imported, dependency_text, 20),
            changed(imported, imported_error, 21),
            changed(imported, dependency_text, 20),
            opened(second, independent, 30),
            changed(imported, dependency_text, 22),
            closed(imported),
            changed(source, caller.replace("return 42;", "return false;"), 11),
            changed(source, caller, 12),
            closed(source),
            closed(second),
        ],
        [root],
        initialize_params=lint_params,
    )
    require(len(stages[0]) == 1, "a closed imported module does not publish its disk lint findings")
    lint_warnings(by_uri(stages[0], source), expected_warning)
    lint_warnings(by_uri(stages[1], source), expected_warning)
    lint_warnings(by_uri(stages[1], imported), expected_imported)
    require(by_uri(stages[1], imported)["version"] == 20, "independently open imports carry their own version")
    for stage in [stages[2], stages[4]]:
        require(not by_uri(stage, source)["diagnostics"], "an imported graph error clears its root's old warnings")
        publication = by_uri(stage, imported)
        require(
            publication["version"] == 21
            and len(publication["diagnostics"]) == 1
            and publication["diagnostics"][0]["code"] == "AU3001"
            and publication["diagnostics"][0]["severity"] == 1,
            "import overlay errors deduplicate across roots and suppress that module's warnings",
        )
    require(stages[3] == [], "a stale import fix cannot restore root warnings")
    lint_warnings(by_uri(stages[4], second), expected_warning)
    lint_warnings(by_uri(stages[5], source), expected_warning)
    lint_warnings(by_uri(stages[5], imported), expected_imported)
    require(by_uri(stages[5], imported)["version"] == 22, "a corrected imported overlay republishes its own warning")
    lint_warnings(by_uri(stages[6], source), expected_warning)
    require(
        by_uri(stages[6], imported) == {"uri": imported.as_uri(), "diagnostics": []},
        "closing an imported root clears its warning even while its valid disk module remains imported",
    )
    root_error = by_uri(stages[7], source)["diagnostics"]
    require(
        len(root_error) == 1 and root_error[0]["code"] == "AU3001" and root_error[0]["severity"] == 1,
        "a root semantic error suppresses its local lint findings",
    )
    lint_warnings(by_uri(stages[7], second), expected_warning)
    lint_warnings(by_uri(stages[8], source), expected_warning)
    require(
        all(value["uri"] != imported.as_uri() for stage in stages[7:] for value in stage),
        "closed imported warnings do not reappear during later root refreshes",
    )
    require(all(not value["diagnostics"] for value in stages[-1]), "closing every lint root clears all publications")
    require(logs.count("ignored stale document version") == 1, "stale import update is rejected once")

    for count in [127, 128, 129]:
        declarations = "".join(f"    i64 unused{index:03} = {index};\n" for index in range(count))
        many_warnings = "module demo;\nauto answer() -> i64 {\n" + declarations + "    return 42;\n}\n"
        expected_many = [(f"unused{index:03}", index + 2, 8) for index in range(count)]
        stages, logs = phases(
            [
                opened(source, many_warnings, 40),
                opened(second, GOOD),
                changed(second, BAD),
                changed(source, many_warnings + "auto broken() -> i64 { return false; }\n", 41),
                changed(source, many_warnings, 42),
                closed(second),
            ],
            initialize_params=lint_params,
        )
        publication = by_uri(stages[0], source)
        if count <= 128:
            lint_warnings(publication, expected_many)
        else:
            lint_warnings({"diagnostics": publication["diagnostics"][:-1]}, expected_many[:127])
            lint_limit(publication, 2)
        require(
            by_uri(stages[1], source) == by_uri(stages[2], source) == publication,
            "warning selection and truncation are deterministic across unrelated accepted refreshes",
        )
        require(
            by_uri(stages[2], second)["diagnostics"][0]["severity"] == 1,
            "warning-heavy roots cannot hide an independent root's error",
        )
        failed = by_uri(stages[3], source)
        require(
            failed["version"] == 41
            and len(failed["diagnostics"]) == 1
            and failed["diagnostics"][0]["code"] == "AU3001"
            and failed["diagnostics"][0]["severity"] == 1,
            "a graph error replaces even warning-heavy publications without a stale truncation notice",
        )
        for stage in stages[4:]:
            restored = by_uri(stage, source)
            require(
                restored["version"] == 42 and restored["diagnostics"] == publication["diagnostics"],
                "correcting a warning-heavy root restores the same ordered bounded findings",
            )
        require(not logs, "bounded warning publication is normal quiet operation")

    long_names = [f"unused{index:03}" + "x" * 4096 for index in range(128)]
    long_declarations = "".join(f"    i64 {name} = 1;\n" for name in long_names)
    long_source = "module demo;\nauto answer() -> i64 {\n" + long_declarations + "    return 42;\n}\n"
    require(len(long_source.encode()) < 1024 * 1024, "long-message fixture fits the accepted source limit")
    stages, logs = phases([opened(source, long_source, 45)], initialize_params=lint_params)
    long_publication = by_uri(stages[0], source)
    lint_warnings(
        long_publication,
        [(name, index + 2, 8) for index, name in enumerate(long_names)],
        truncated_messages=True,
    )
    require(
        all(len(value["message"].encode()) == 4096 + len(" [truncated]") for value in long_publication["diagnostics"])
        and not logs,
        "all 128 bounded warning messages preserve full identifier spans within the encoded wire limit",
    )

    # The dependency sorts before its importer. Its unused template succeeds as
    # a standalone root, then produces a definition-site error when instantiated.
    template_declarations = "".join(f"    i64 unused{index:03} = {index};\n" for index in range(129))
    template_dependency = "export module dep;\nauto answer() -> i64 {\n" + template_declarations + "    return 42;\n}\n"
    template_dependency += "export template<Scalar T> auto broken(T value) -> T { return false; }\n"
    template_caller = "module demo; import dep; auto answer() -> i64 { return broken<i64>(0); }\n"
    expected_template = [(f"unused{index:03}", index + 2, 8) for index in range(129)]
    stages, logs = phases(
        [
            opened(imported, template_dependency, 50),
            opened(source, template_caller, 60),
            changed(source, GOOD, 61),
            closed(imported),
        ],
        [root],
        initialize_params=lint_params,
    )
    standalone = by_uri(stages[0], imported)
    lint_warnings({"diagnostics": standalone["diagnostics"][:-1]}, expected_template[:127])
    lint_limit(standalone, 2)
    mixed = by_uri(stages[1], imported)
    require(
        mixed["version"] == 50
        and mixed["diagnostics"][0]["code"] == "AU3001"
        and mixed["diagnostics"][0]["severity"] == 1
        and mixed["diagnostics"][0]["data"]["rangeKnown"] is True,
        "a later imported-template error takes precedence over warnings on the same source URI",
    )
    lint_warnings({"diagnostics": mixed["diagnostics"][1:-1]}, expected_template[:126])
    lint_limit(mixed, 3)
    require(not by_uri(stages[1], source)["diagnostics"], "template failure publishes on its definition source URI")
    require(by_uri(stages[2], imported) == standalone, "removing the instantiation restores the dependency's budget")
    require(
        by_uri(stages[3], imported) == {"uri": imported.as_uri(), "diagnostics": []} and not logs,
        "closing a warning-heavy root clears compiler warnings and its server truncation notice",
    )

    stages, _ = phases(
        [opened(source, caller)],
        initialize_params={
            "initializationOptions": {"lint": True},
            "rootUri": root.as_uri(),
            "workspaceFolders": [{"uri": root.as_uri(), "name": "lint fixtures"}],
        },
    )
    unauthorized = by_uri(stages[0], source)["diagnostics"]
    require(
        len(unauthorized) == 1 and unauthorized[0]["code"] == "AU4001" and unauthorized[0]["severity"] == 1,
        "lint initialization and workspace metadata do not grant module-root authority",
    )
    require(set(root.iterdir()) == set(original_files), "lint sessions create no source, cache or artifact files")
    require(
        (root.stat().st_mtime_ns, root.stat().st_ctime_ns)
        == (original_directory.st_mtime_ns, original_directory.st_ctime_ns),
        "lint sessions do not create and remove transient workspace files",
    )
    for path, (original, original_stat) in original_files.items():
        current_stat = path.stat()
        require(path.read_bytes() == original, "lint leaves readonly root and import disk bytes unchanged")
        require(
            (current_stat.st_mtime_ns, current_stat.st_ctime_ns, current_stat.st_mode)
            == (original_stat.st_mtime_ns, original_stat.st_ctime_ns, original_stat.st_mode),
            "lint neither rewrites original bytes nor changes readonly permissions",
        )


def formatting(path, id=10, options=None, uri=None):
    return request(
        "textDocument/formatting",
        id,
        {
            "textDocument": {"uri": uri or path.as_uri()},
            "options": options if options is not None else {"tabSize": 4, "insertSpaces": True},
        },
    )


def format_session(actions):
    outputs, logs = run([request("initialize", 1, {}), *actions, request("shutdown", 2), notification("exit")])
    require(outputs[0]["result"]["capabilities"]["documentFormattingProvider"] is True, "formatting advertised")
    require(outputs[-1] == {"jsonrpc": "2.0", "id": 2, "result": None}, "formatting session shuts down normally")
    responses = [value for value in outputs if "id" in value and value["id"] not in (1, 2)]
    replies = {value["id"]: value for value in responses}
    expected = [action["id"] for action in actions if "id" in action]
    require([value["id"] for value in responses] == expected, "one ordered response per formatting request")
    require(
        all(value.get("method") == "textDocument/publishDiagnostics" for value in outputs if "id" not in value),
        "formatting emits no unsolicited commands or other messages",
    )
    return replies, logs


def live_reply(process, identifier):
    deadline = time.monotonic() + 20

    def read_exact(count):
        data = bytearray()
        while len(data) < count:
            remaining = deadline - time.monotonic()
            require(
                remaining > 0 and select.select([process.stdout], [], [], max(0, remaining))[0], "live response timeout"
            )
            chunk = os.read(process.stdout.fileno(), count - len(data))
            require(bool(chunk), "live response ends only on a complete frame")
            data.extend(chunk)
        return bytes(data)

    while True:
        header = bytearray()
        while not header.endswith(b"\r\n\r\n"):
            require(len(header) < 8192, "live frame header remains bounded")
            header.extend(read_exact(1))
        require(header.startswith(b"Content-Length: "), "live stdout has clean framing")
        size = int(header[len(b"Content-Length: ") : -4])
        require(0 <= size <= 8 * 1024 * 1024, "live body remains bounded")
        message = json.loads(read_exact(size))
        diagnostic_metadata(message)
        if "id" in message:
            require(message["id"] == identifier, "live request receives its own response")
            return message
        require(message.get("method") == "textDocument/publishDiagnostics", "only diagnostics precede a live response")


def whole_edit(reply, text, end):
    require("error" not in reply and len(reply["result"]) == 1, "one complete formatting edit")
    require(
        reply["result"][0] == {"range": {"start": {"line": 0, "character": 0}, "end": end}, "newText": text},
        "whole-document text and exact original UTF-16 EOF range",
    )


def format_error(reply, code, diagnostic=None):
    require("result" not in reply and reply["error"]["code"] == code, "formatting failure returns no edits")
    if diagnostic:
        require(reply["error"]["data"]["diagnostic"]["code"] == diagnostic, "original formatter diagnostic family")


with tempfile.TemporaryDirectory(prefix="aurora-lsp-format-test-") as directory:
    root = Path(directory)
    source = root / "format café.au"
    source.write_text(BAD)
    source.chmod(0o444)
    original = source.read_bytes()
    original_stat = source.stat()
    compact = "module demo;auto answer()->i64{return 7;}"
    canonical = "module demo;\nauto answer() -> i64 {\n    return 7;\n}\n"
    replies, logs = format_session(
        [
            opened(source, compact, 10),
            formatting(source, 10),
            formatting(source, 11),
            changed(source, canonical, 11),
            formatting(source, 12),
            changed(source, BAD, 10),
            changed(source, BAD, 11),
            formatting(source, 13),
            closed(source),
            formatting(source, 14),
            opened(source, compact, -1),
            formatting(source, 15),
        ]
    )
    whole_edit(replies[10], canonical, {"line": 0, "character": len(compact)})
    require(replies[10]["result"] == replies[11]["result"], "formatting never applies its own edit to the snapshot")
    require(replies[12]["result"] == replies[13]["result"] == [], "canonical latest text survives stale edits")
    format_error(replies[14], -32602)
    whole_edit(replies[15], canonical, {"line": 0, "character": len(compact)})
    require(logs.count("ignored stale document version") == 2, "stale changes remain observable")
    require(
        source.read_bytes() == original and list(root.iterdir()) == [source], "readonly disk bytes and files unchanged"
    )
    require(
        (source.stat().st_mtime_ns, source.stat().st_ctime_ns, source.stat().st_mode)
        == (original_stat.st_mtime_ns, original_stat.st_ctime_ns, original_stat.st_mode),
        "formatting cannot rewrite bytes or change file permissions",
    )

    lint_compact = "module demo;auto answer()->i64{i64 unused=7;return 42;}"
    lint_canonical = "module demo;\nauto answer() -> i64 {\n    i64 unused = 7;\n    return 42;\n}\n"
    outputs, logs = run(
        [
            request("initialize", 1, {"initializationOptions": {"lint": True}}),
            opened(source, lint_compact, 70),
            formatting(source, 10),
            formatting(source, 11),
            changed(source, lint_compact, 71),
            formatting(source, 12),
            changed(source, lint_canonical, 72),
            formatting(source, 13),
            request("shutdown", 2),
            notification("exit"),
        ]
    )
    require(
        [value.get("id") for value in outputs] == [1, None, 10, 11, None, 12, None, 13, 2],
        "lint-enabled formatting emits replies without extra diagnostic publications",
    )
    replies = {value["id"]: value for value in outputs if "id" in value}
    for identifier in [10, 11, 12]:
        whole_edit(replies[identifier], lint_canonical, {"line": 0, "character": len(lint_compact)})
    require(replies[13]["result"] == [] and not logs, "canonical lint-enabled formatting is unchanged and quiet")
    for index, version in [(1, 70), (4, 71), (6, 72)]:
        publication = outputs[index]["params"]
        require(publication["version"] == version, "only accepted changes update a formatted lint snapshot")
        lint_warnings(publication, [("unused", 2, 8)] if version == 72 else [("unused", 0, 35)])
    require(source.read_bytes() == original, "formatting in lint mode preserves the readonly disk source")

    # Golden expected text tests comment bytes/anchors, EOF, CRLF/CR/LF, tabs,
    # non-BMP UTF-16 width, and escaped controls without a second Aurora parser.
    for text, expected, end in [
        (compact + "\n", canonical, {"line": 1, "character": 0}),
        (compact + "\r\n", canonical, {"line": 1, "character": 0}),
        (compact + "\r", canonical, {"line": 1, "character": 0}),
        (
            "// café 😀\r\n" + compact + " // 尾😀",
            "// café 😀\r\n" + canonical.rstrip("\n") + " // 尾😀\n",
            {"line": 1, "character": len(compact) + 7},
        ),
        (
            "// \x00\t😀\nmodule demo;// module\nauto answer()->i64{ // body\nreturn 7; // result \t\n}// eof",
            "// \x00\t😀\nmodule demo; // module\nauto answer() -> i64 { // body\n"
            "    return 7; // result \t\n} // eof\n",
            {"line": 4, "character": 7},
        ),
    ]:
        replies, logs = format_session([opened(source, text), formatting(source)])
        whole_edit(replies[10], expected, end)
        require(not logs, "successful formatter keeps stderr quiet, including preserved style findings")
        replies, _ = format_session([opened(source, expected), formatting(source)])
        require(replies[10]["result"] == [], "applied formatting is idempotent")

    separated = (
        "\nmodule demo;\r\n \t\r\n\r\nauto answer()->i64{\n\ni64 value=7; // value \t\r\n\n"
        "// return group 😀\n\nreturn value;\n\n}\n\n// footer\n\n"
    )
    separated_canonical = (
        "module demo;\n\nauto answer() -> i64 {\n    i64 value = 7; // value \t\r\n\n"
        "    // return group 😀\n\n    return value;\n}\n\n// footer\n"
    )
    replies, logs = format_session(
        [
            opened(source, separated, 80),
            formatting(source, 10),
            formatting(source, 11),
            changed(source, separated_canonical, 81),
            formatting(source, 12),
        ]
    )
    whole_edit(replies[10], separated_canonical, {"line": separated.count("\n"), "character": 0})
    require(replies[10]["result"] == replies[11]["result"], "blank-line edits leave the accepted snapshot untouched")
    require(replies[12]["result"] == [] and not logs, "blank-line formatting is idempotent through real LSP")
    require(source.read_bytes() == original, "blank-line formatting never changes disk source")

    syntax_only = "module demo;import absent;auto answer()->i64{return unknown;}"
    expected = "module demo;\nimport absent;\nauto answer() -> i64 {\n    return unknown;\n}\n"
    replies, _ = format_session([opened(source, syntax_only), formatting(source)])
    whole_edit(replies[10], expected, {"line": 0, "character": len(syntax_only)})

    for text, diagnostic in [
        ("", "AU2001"),
        (" \t\r\n", "AU2001"),
        (BAD, "AU1001"),
        ("module demo; auto answer()->i64{return ;}", "AU2001"),
        ("module demo; /* unsupported */", "AU2001"),
        ("module demo; auto answer()->i64{return " + "(" * 300 + "1" + ")" * 300 + ";}", "AU2002"),
    ]:
        replies, _ = format_session([opened(source, text, 17), formatting(source), formatting(source, 11)])
        for reply in replies.values():
            format_error(reply, -32803, diagnostic)
            require(
                reply["error"]["data"]["version"] == 17 and reply["error"]["data"]["uri"] == source.as_uri(),
                "formatter failure identifies accepted snapshot",
            )
        require(replies[10]["error"] == replies[11]["error"], "failure leaves the snapshot intact")

    for options in [
        {},
        [],
        {"tabSize": 4},
        {"insertSpaces": True},
        {"tabSize": 2, "insertSpaces": True},
        {"tabSize": True, "insertSpaces": True},
        {"tabSize": 4.0, "insertSpaces": True},
        {"tabSize": 4, "insertSpaces": False},
        {"tabSize": 4, "insertSpaces": 1},
        {"tabSize": 4, "insertSpaces": "true"},
        {"tabSize": 4, "insertSpaces": True, "trimTrailingWhitespace": True},
    ]:
        replies, _ = format_session(
            [opened(source, compact), formatting(source, options=options), formatting(source, 11)]
        )
        format_error(replies[10], -32602)
        require("tabSize=4" in replies[10]["error"]["message"], "canonical option restriction is explicit")
        whole_edit(replies[11], canonical, {"line": 0, "character": len(compact)})
    for params in [None, [], {}, {"textDocument": {"uri": source.as_uri()}}]:
        replies, _ = format_session([opened(source, compact), request("textDocument/formatting", 10, params)])
        format_error(replies[10], -32602)

    alias = source.as_uri().replace("file:///", "file://localhost/")
    for uri in [
        alias,
        "untitled:buffer",
        "file://remote" + str(source),
        source.as_uri() + "?query",
        source.as_uri() + "#fragment",
        root.as_uri() + "/missing/../" + source.name,
        root.as_uri() + "/%2e%2e/" + source.name,
        root.as_uri() + "/%ff.au",
        root.as_uri() + "/%00.au",
        root.as_uri() + "/%ZZ.au",
    ]:
        replies, _ = format_session([opened(source, compact), formatting(source, uri=uri)])
        format_error(replies[10], -32602)
    replies, _ = format_session([formatting(source)])
    format_error(replies[10], -32602)
    link = root / "link.au"
    link.symlink_to(source)
    nested_link = root / "linked-directory"
    nested_link.symlink_to(root, target_is_directory=True)
    for path in [root / "missing.au", root, link, nested_link / source.name]:
        replies, _ = format_session([opened(path, compact), formatting(path)])
        format_error(replies[10], -32803, "AU4001")

    # Admission must run at formatting time, even after a successful open and
    # earlier edit response. Mutations here are test-client actions, never LSP.
    live_directory = root / "live"
    live_directory.mkdir()
    live_source = live_directory / "input.au"
    live_source.write_text(BAD)
    held = root / "held.au"
    held_directory = root / "held-directory"
    process = subprocess.Popen([str(SERVER)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        process.stdin.write(frame(request("initialize", 1, {})))
        process.stdin.flush()
        require("result" in live_reply(process, 1), "live server initialized")
        process.stdin.write(frame(opened(live_source, compact, 30)) + frame(formatting(live_source, 10)))
        process.stdin.flush()
        whole_edit(live_reply(process, 10), canonical, {"line": 0, "character": len(compact)})
        for index, replacement in enumerate(["missing", "symlink", "directory", "parent-symlink"]):
            if replacement == "parent-symlink":
                live_directory.rename(held_directory)
                live_directory.symlink_to(held_directory, target_is_directory=True)
            else:
                live_source.rename(held)
                if replacement == "symlink":
                    live_source.symlink_to(held)
                elif replacement == "directory":
                    live_source.mkdir()
            identifier = 20 + 2 * index
            process.stdin.write(frame(formatting(live_source, identifier)))
            process.stdin.flush()
            reply = live_reply(process, identifier)
            format_error(reply, -32803, "AU4001")
            require(reply["error"]["data"]["version"] == 30, "admission failure retains the accepted version")
            if replacement == "parent-symlink":
                live_directory.unlink()
                held_directory.rename(live_directory)
            else:
                if replacement == "symlink":
                    live_source.unlink()
                elif replacement == "directory":
                    live_source.rmdir()
                held.rename(live_source)
            process.stdin.write(frame(formatting(live_source, identifier + 1)))
            process.stdin.flush()
            whole_edit(live_reply(process, identifier + 1), canonical, {"line": 0, "character": len(compact)})
            require(
                live_source.read_text() == BAD, "formatting uses accepted text and leaves the restored disk bytes alone"
            )
        process.stdin.write(frame(request("shutdown", 2)) + frame(notification("exit")))
        process.stdin.flush()
        require(live_reply(process, 2)["result"] is None, "live session shutdown response")
        process.stdin.close()
        process.stdin = None
        stdout, stderr = process.communicate(timeout=20)
        require(process.returncode == 0 and not stdout and not stderr, "live session exits without stray output")
        CASES += 1
    except BaseException:
        process.kill()
        process.wait()
        raise

    # Exact input/output limits and output expansion failure remain transactional.
    limit = 1024 * 1024
    exact_input = compact + " " * (limit - len(compact))
    replies, _ = format_session([opened(source, exact_input), formatting(source)])
    whole_edit(replies[10], canonical, {"line": 0, "character": limit})
    exact_output = canonical + "//" + "x" * (limit - len(canonical) - 3)
    replies, _ = format_session([opened(source, exact_output), formatting(source)])
    whole_edit(replies[10], exact_output + "\n", {"line": 4, "character": limit - len(canonical) - 1})
    expansion = exact_output + "x"
    replies, _ = format_session(
        [opened(source, expansion), formatting(source), changed(source, compact), formatting(source, 11)]
    )
    format_error(replies[10], -32803, "AU9001")
    whole_edit(replies[11], canonical, {"line": 0, "character": len(compact)})
    replies, logs = format_session([opened(source, compact), changed(source, " " * (limit + 1)), formatting(source)])
    whole_edit(replies[10], canonical, {"line": 0, "character": len(compact)})
    require("storage exceeds limit" in logs, "oversized replacement cannot affect formatting")
    require(source.read_bytes() == original, "all formatter errors leave source bytes unchanged")

    # Standard lifecycle still applies to formatting; range/on-type are unsupported.
    outputs, _ = run(
        [
            formatting(source),
            request("initialize", 1, {}),
            opened(source, compact),
            request("textDocument/rangeFormatting", 11, {}),
            request("textDocument/onTypeFormatting", 12, {}),
            request("shutdown", 2),
            formatting(source, 13),
            notification("exit"),
        ]
    )
    replies = {value["id"]: value for value in outputs if "id" in value}
    for id, code in [(10, -32002), (11, -32601), (12, -32601), (13, -32600)]:
        format_error(replies[id], code)
    require(
        "documentRangeFormattingProvider" not in replies[1]["result"]["capabilities"]
        and "documentOnTypeFormattingProvider" not in replies[1]["result"]["capabilities"],
        "only implemented formatting is advertised",
    )

initialize = request("initialize", 1, {})
shutdown = request("shutdown", 2)
exit_message = notification("exit")
for messages, status in [
    ([], 1),
    ([exit_message], 1),
    ([initialize], 1),
    ([initialize, exit_message], 1),
    ([initialize, shutdown], 0),
    ([initialize, shutdown, exit_message], 0),
]:
    run(messages, status=status)
outputs, _ = run(
    [request("unknown", 3), initialize, request("initialize", 4, {}), shutdown, request("unknown", 5), exit_message]
)
require(
    [value.get("error", {}).get("code") for value in outputs] == [-32002, None, -32600, None, -32600],
    "initialization and shutdown state machine",
)
for malformed in [
    b"",
    b"{",
    b"[]",
    b"null",
    b'{"jsonrpc":"2.0","id":1,"method":"initialize","params":{},"params":{}}',
    b'{"text":"\xff"}',
    b"[" * 70 + b"0" + b"]" * 70,
    json.dumps([0] * 70000).encode(),
]:
    outputs, _ = run(raw=frame(malformed) + frame(initialize) + frame(shutdown) + frame(exit_message))
    require(outputs[0]["error"]["code"] in (-32700, -32600), "malformed or excessive JSON rejected")
    require(outputs[1]["id"] == 1 and "result" in outputs[1], "valid message after malformed JSON is handled")
for identifier in [None, True, 1.5, 2**63, "x" * 1025]:
    outputs, _ = run([request("initialize", identifier, {}), initialize, shutdown, exit_message])
    require(
        outputs[0]["error"]["code"] == -32600 and outputs[0]["id"] is None,
        "invalid request ID rejected without initializing",
    )
for raw in [
    b"Content-Length: -1\r\n\r\n",
    b"Content-Length: 8388609\r\n\r\n",
    b"Content-Length: 2\r\ncontent-length: 2\r\n\r\n{}",
    b"Content-Length: 2\n\n{}",
    b"Content-Length: 10\r\n\r\n{}",
    b"x" * 8193,
    b"Content-Length: 2\r\n",
]:
    outputs, logs = run(raw=raw, status=1)
    require(not outputs and logs, "bad framing fails closed with stderr only")

# Split headers and UTF-8 payload bytes across writes; pipe boundaries are not frames.
process = subprocess.Popen([str(SERVER)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
fragmented = frame(request("initialize", "😀", {})) + frame(shutdown) + frame(exit_message)
try:
    for byte in fragmented:
        process.stdin.write(bytes([byte]))
        process.stdin.flush()
    process.stdin.close()
    process.stdin = None
    stdout, stderr = process.communicate(timeout=20)
except BaseException:
    process.kill()
    process.wait()
    raise
CASES += 1
require(process.returncode == 0 and not stderr, "fragmented transport session succeeds")
require(parse_frames(stdout)[0]["id"] == "😀", "request IDs preserve escaped Unicode")
print(
    json.dumps(
        {
            "status": "passed",
            "scope": "focused LSP protocol only",
            "server_sha256": hashlib.sha256(SERVER.read_bytes()).hexdigest(),
            "process_cases": CASES,
            "assertions": CHECKS,
        },
        sort_keys=True,
    )
)
