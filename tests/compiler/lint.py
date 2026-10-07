#!/usr/bin/env python3
"""Exercise compiler-owned semantic lint; this runner contains no Aurora parser."""

import argparse
import hashlib
import json
import pathlib
import subprocess
import tempfile


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def program(body, definitions="", parameters=""):
    return "module app; " + definitions + " auto test(" + parameters + ") -> i64 { " + body + " }"


def position(contents, offset):
    return {
        "offset": offset,
        "line": contents[:offset].count(b"\n") + 1,
        "column": offset - contents.rfind(b"\n", 0, offset),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("formatter", type=pathlib.Path)
    parser.add_argument("compiler", type=pathlib.Path)
    parser.add_argument("helper", type=pathlib.Path)
    parser.add_argument("--baseline", type=pathlib.Path)
    parser.add_argument("--artifacts", type=pathlib.Path)
    args = parser.parse_args()
    formatter, compiler, helper = (path.resolve(strict=True) for path in (args.formatter, args.compiler, args.helper))
    baseline = args.baseline.resolve(strict=True) if args.baseline else None
    root = args.artifacts or pathlib.Path(tempfile.mkdtemp(prefix="aurora-lint-", dir=formatter.parent))
    root.mkdir(parents=True, exist_ok=True)
    root = root.resolve()
    records = []

    def run(command, status=0, cwd=None):
        result = subprocess.run(list(map(str, command)), capture_output=True, timeout=20, check=False, cwd=cwd)
        require(
            result.returncode == status, f"{command}: expected {status}, got {result.returncode}: {result.stderr!r}"
        )
        return result

    def check(name, text, expected=(), error=None, modules=None, relative=False):
        directory = root / f"case-{len(records):03}"
        directory.mkdir()
        path = directory / "input.au"
        path.write_bytes(text.encode())
        inputs = {path: path.read_bytes()}
        roots = []
        if modules:
            module_root = directory / "modules"
            module_root.mkdir()
            roots = ["--module-root", module_root]
            for module_name, module_text in modules.items():
                module_path = module_root / (module_name.replace(".", "/") + ".au")
                module_path.parent.mkdir(parents=True, exist_ok=True)
                module_path.write_text(module_text)
                inputs[module_path] = module_path.read_bytes()
        source = "input.au" if relative else path
        result = run(
            [formatter, "--lint", "--diagnostics=json", *roots, source],
            2 if error else 0,
            cwd=directory if relative else None,
        )
        (directory / "stdout.bin").write_bytes(result.stdout)
        (directory / "stderr.json").write_bytes(result.stderr)
        require(not result.stdout, name + ": lint emitted formatted source")
        record = json.loads(result.stderr)
        require(record["schemaVersion"] == 1 and record["success"] == (error is None), name + ": wrong envelope")
        findings = record["diagnostics"]
        if error:
            require(
                len(findings) == 1 and findings[0]["severity"] == "error" and findings[0]["code"] == error,
                name + ": source error was hidden by warnings",
            )
        else:
            require(len(findings) == len(expected), name + f": unexpected diagnostics {findings}")
            data = inputs[path]
            for finding, (binding_name, marker) in zip(findings, expected):
                # The fixture explicitly identifies its declaration spelling; production
                # analysis uses compiler-owned source tokens and resolved local identities.
                offset = data.index(marker.encode()) + marker.encode().index(binding_name.encode())
                require(
                    finding["code"] == "AU6001" and finding["severity"] == "warning", name + ": wrong warning identity"
                )
                require(finding["message"] == f"local binding '{binding_name}' is never read", name + ": wrong message")
                require(finding["path"] == str(source), name + ": wrong source path")
                require(
                    finding["range"]
                    == {"start": position(data, offset), "end": position(data, offset + len(binding_name))},
                    name + ": warning does not cover exact identifier",
                )
            ordinary = run([compiler, "--check", "--diagnostics=json", *roots, path])
            require(
                json.loads(ordinary.stdout)["diagnostics"] == [] and not ordinary.stderr,
                name + ": ordinary check leaked lint",
            )
        for file, before in inputs.items():
            require(file.read_bytes() == before, name + ": source was modified")
        entry = {
            "name": name,
            "status": result.returncode,
            "warnings": len(expected),
            "error": error,
            "source_sha256": hashlib.sha256(inputs[path]).hexdigest(),
        }
        records.append(entry)
        (root / "cases.json").write_text(json.dumps(records, indent=2) + "\n")
        print("PASS lint", name, flush=True)
        return path, findings

    for typename, value in [("i64", "7"), ("u64", "7u64"), ("u8", "7u8"), ("bool", "true"), ("Tag", "Tag::yes")]:
        definitions = "enum class Tag { yes, no };" if typename == "Tag" else ""
        for qualifier in ("", "const "):
            declaration = qualifier + typename + " unused = " + value + ";"
            check(
                qualifier + typename + " unread",
                program(declaration + " return 0;", definitions),
                [("unused", declaration)],
            )
    check("write only", program("i64 value = 1; value = 2; return 0;"), [("value", "i64 value")])
    check("self read assignment", program("i64 value = 1; value = value + 2; return 0;"))
    check("self assignment", program("i64 value = 1; value = value; return 0;"))
    check("return read", program("i64 value = 42; return value;"))
    check("initializer read", program("i64 value = 42; i64 copied = value; return copied;"))
    check("call argument read", program("i64 value = 42; return take(value);", "auto take(i64 x) -> i64 { return x; }"))
    check("array index read", program("array<i64, 1> values = {42}; i64 index = 0; return values[index];"))
    check("if condition read", program("bool value = true; if (value) { return 42; } return 0;"))
    check("then branch read", program("i64 value = 42; if (true) { value; } return 0;"))
    check("else branch read", program("i64 value = 42; if (true) {} else { value; } return 0;"))
    check("returning branch read", program("i64 value = 42; if (false) { return value; } return 0;"))
    check("while body read", program("i64 value = 42; while (false) { value; } return 0;"))
    check("while condition read", program("bool value = false; while (value) {} return 0;"))
    check("nested branch loop read", program("i64 value = 42; while (false) { if (true) { value; } } return 0;"))
    check("short circuit read", program("bool value = true; false && value; return 0;"))
    check(
        "inner use cannot hide outer",
        program("i64 value = 1; { i64 value = 2; value; } return 0;"),
        [("value", "i64 value = 1")],
    )
    check(
        "outer use cannot hide inner",
        program("i64 value = 1; { i64 value = 2; } return value;"),
        [("value", "i64 value = 2")],
    )
    check(
        "shadow initializer resolves outer",
        program("i64 value = 1; { i64 value = value; } return 0;"),
        [("value", "i64 value = value")],
    )
    check(
        "sibling scopes keep identities",
        program("{ i64 value = 1; value; } { i64 value = 2; } return 0;"),
        [("value", "i64 value = 2")],
    )
    check(
        "branch declarations keep identities",
        program("if (true) { i64 value = 1; value; } else { i64 value = 2; } return 0;"),
        [("value", "i64 value = 2")],
    )
    check(
        "function read facts reset",
        "module app; auto earlier()->i64{i64 value=1;return value;}auto test()->i64{i64 value=2;return 0;}",
        [("value", "i64 value=2")],
    )
    check(
        "underscore opt out", program("i64 _ = 1; i64 _intentional = 2; i64 a_b = 3; return 0;"), [("a_b", "i64 a_b")]
    )
    check("parameters excluded", program("return 0;", parameters="i64 value"))
    check(
        "array and capabilities excluded",
        program(
            "array<u8, 2> bytes = {0u8, 0u8}; const builtin::span<const u8> view = borrow_bytes(bytes);"
            "own<i64> owner = own(3); { ref<i64> shared = borrow(owner); }"
            "{ mutref<i64> exclusive = borrow_mut(owner); } return 0;"
        ),
    )
    counter = (
        "class Counter { i64 value; public: Counter(i64 initial):value(initial){}"
        "auto get() const -> i64 { return value; } };"
    )
    check("class bindings excluded", program("Counter instance=Counter(1); return 0;", counter))
    check(
        "field spelling is not read",
        program(
            "i64 value=1; Counter instance=Counter(2);return instance.value;",
            "class Counter { public: i64 value; Counter(i64 x):value(x){} };",
        ),
        [("value", "i64 value=1")],
    )
    check(
        "method spelling is not read",
        program("i64 get=1; Counter instance=Counter(2);return instance.get();", counter),
        [("get", "i64 get=1")],
    )
    check(
        "type spelling is not read",
        program("i64 Counter=1; Counter instance=Counter(2);return instance.get();", counter),
        [("Counter", "i64 Counter=1")],
    )
    check(
        "enum case spelling is not read",
        program("i64 yes=1; Tag value=Tag::yes; value; return 0;", "enum class Tag { yes };"),
        [("yes", "i64 yes=1")],
    )
    methods = (
        "class Counter { i64 value; public: Counter(i64 initial):value(initial){}"
        "auto inspect() const -> i64 { i64 unused=1; return value; }"
        "auto shadow() const -> i64 { i64 value=2; return value; } }; "
    )
    check("ordinary methods and receiver fields", program("return 0;", methods), [("unused", "i64 unused=1")])
    check(
        "unused ordinary function included",
        "module app; auto helper()->i64{i64 unused=1;return 0;}auto test()->i64{return 0;}",
        [("unused", "i64 unused=1")],
    )
    check(
        "source order spans methods and functions",
        program("i64 second=2;return 0;", methods),
        [("unused", "i64 unused=1"), ("second", "i64 second=2")],
    )
    template = "template<Scalar T> auto choose(T input)->T { i64 unused=1; return input; }"
    check("uninstantiated function template excluded", program("return 0;", template))
    check("instantiated function template excluded", program("return choose<i64>(42);", template))
    box = (
        "template<Scalar T> class Box { T value; public: Box(T x):value(x){}"
        "auto get() const -> T { i64 unused=1; return value; } };"
    )
    check("uninstantiated class template excluded", program("return 0;", box))
    check("instantiated class template method excluded", program("Box<i64> box=Box<i64>(42);return box.get();", box))
    dep = "export module dep; export auto answer()->i64{i64 imported=1;return 42;}"
    check("import warning excluded", "module app;import dep;auto test()->i64{return answer();}", modules={"dep": dep})
    check(
        "root warnings with import",
        "module app;import dep;auto test()->i64{i64 root=1;return answer();}",
        [("root", "i64 root=1")],
        modules={"dep": dep},
    )
    check("dependency linted as root", dep, [("imported", "i64 imported=1")])
    check("relative source path", program("i64 unused=1;return 0;"), [("unused", "i64 unused=1")], relative=True)
    check(
        "exact UTF8 CRLF tab span",
        "// café 😀\r\nmodule app;\r\nauto test()->i64{\r\n\tconst i64 unused=1;\r\nreturn 0;\r\n}",
        [("unused", "i64 unused=1")],
    )
    for name, text, code in [
        ("type error wins", program("i64 unused=1;return false;"), "AU3001"),
        (
            "later error discards accumulated warnings",
            "module app; auto earlier()->i64{i64 unused=1;return 0;} auto test()->i64{return false;}",
            "AU3001",
        ),
        ("missing initializer rejected", program("i64 value;return 0;"), "AU2001"),
        ("self initializer rejected", program("i64 value=value;return 0;"), "AU3001"),
        ("unknown local rejected", program("i64 unused=1;return absent;"), "AU3001"),
        ("unreachable rejected", program("i64 unused=1;return 0;i64 later=2;"), "AU3001"),
        ("reserved compiler name rejected", program("i64 __au_reserved=1;return 0;"), "AU2001"),
        ("duplicate binding rejected", program("i64 value=1;i64 value=2;return 0;"), "AU3001"),
        (
            "use after move rejected",
            program("own<i64> owner=own(1);own<i64> moved=move(owner);return read(owner);"),
            "AU3001",
        ),
    ]:
        check(name, text, error=code)
    _, imported_error = check(
        "import failure wins",
        "module app;import dep;auto test()->i64{i64 unused=1;return 0;}",
        error="AU1001",
        modules={"dep": "export module dep; @"},
    )
    require(imported_error[0]["path"].endswith("dep.au"), "imported diagnostic lost provenance")
    effect = program(
        "Counter counter=Counter(0); i64 unused=counter.set(42); return counter.get();",
        "class Counter { i64 value; public: Counter(i64 n):value(n){}"
        "auto set(i64 n)->i64{value=n;return 9;} auto get() const ->i64{return value;} };",
    )
    effect_path, _ = check("side effect initializer warned but retained", effect, [("unused", "i64 unused=")])
    text_warning = run([formatter, "--lint", effect_path])
    require(
        b"warning AU6001: local binding 'unused' is never read" in text_warning.stderr and not text_warning.stdout,
        "text warning missing severity/code or leaked source",
    )
    assembly = root / "side-effect.s"
    compiled = run([compiler, effect_path, "-o", assembly])
    require(
        not compiled.stderr and not compiled.stdout and b"call " in assembly.read_bytes(),
        "initializer call removed or ordinary compilation emitted lint",
    )
    if baseline:
        original = root / "side-effect-baseline.s"
        run([baseline, effect_path, "-o", original])
        require(original.read_bytes() == assembly.read_bytes(), "lint changes altered side-effect assembly")
    bridge = root / "entry.s"
    bridge.write_text(
        ".text\n.globl _start\n_start:\n    call test\n    cmpq $42, %rax\n"
        "    setne %dil\n    movzbq %dil, %rdi\n    movq $60, %rax\n    syscall\n"
        '.section .note.GNU-stack,"",@progbits\n'
    )
    run(["as", "--64", assembly, "-o", root / "side-effect.o"])
    run(["as", "--64", bridge, "-o", root / "entry.o"])
    run(["ld", "-o", root / "side-effect", root / "entry.o", root / "side-effect.o"])
    run([root / "side-effect"])
    before = effect_path.read_bytes()
    frontend = run([helper, effect_path])
    require(effect_path.read_bytes() == before, "frontend overlay test changed disk source")
    (root / "frontend.log").write_bytes(frontend.stdout)
    summary = {
        "cases": len(records),
        "native_side_effect_result": 42,
        "frontend_contract": "passed",
        "baseline_assembly_equal": bool(baseline),
    }
    (root / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(f"PASS semantic lint: {len(records)} CLI cases, frontend contracts and retained native side effect")


if __name__ == "__main__":
    main()
