#!/usr/bin/env python3
"""Focused real-server protocol checks; never builds or runs generated Aurora code."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

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
