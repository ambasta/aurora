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


def parse_frames(raw):
    messages = []
    while raw:
        header, separator, raw = raw.partition(b"\r\n\r\n")
        require(bool(separator), "stdout contains only complete framed protocol messages")
        require(header.startswith(b"Content-Length: "), "stdout has clean framing")
        count = int(header[len(b"Content-Length: ") :])
        require(len(raw) >= count, "output body is complete")
        messages.append(json.loads(raw[:count]))
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


def changed(path, text=GOOD, version=2):
    return notification(
        "textDocument/didChange",
        {"textDocument": {"uri": path.as_uri(), "version": version}, "contentChanges": [{"text": text}]},
    )


def closed(path):
    return notification("textDocument/didClose", {"textDocument": {"uri": path.as_uri()}})


def phases(actions, roots=()):
    messages = [request("initialize", 1, {"capabilities": {}}), notification("initialized", {})]
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
    stages, _ = phases([opened(source, "module demo; auto answer() -> i64 { return true; }")])
    require(by_uri(stages[0], source)["diagnostics"][0]["code"] == "AU3001", "semantic diagnostics use shared checker")

    imported = root / "dep.au"
    imported.write_text(DEP_GOOD)
    caller = "module demo; import dep; auto answer() -> i64 { return 42; }"
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
