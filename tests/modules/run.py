#!/usr/bin/env python3
"""Execute real freestanding imported modules and fail closed on invalid graphs."""

from pathlib import Path
import resource
import os
import signal
import subprocess
import sys
import tempfile

COMPILER = Path(sys.argv[1]).resolve()
LIBRARY = Path(__file__).resolve().parents[2] / "library"
COUNT = 0


def require(value, message):
    if not value:
        raise AssertionError(message)


def run(command, good=True):
    result = subprocess.run(
        [str(x) for x in command],
        capture_output=True,
        timeout=60,
        preexec_fn=lambda: resource.setrlimit(resource.RLIMIT_CORE, (0, 0)),
    )
    if good:
        require(result.returncode == 0, f"{command}: {result.returncode}: {result.stderr!r}")
    return result


def check(
    name,
    source,
    modules=None,
    expected=42,
    error=None,
    library=False,
    root_sets=None,
    setup=None,
    roots=True,
    trap=False,
    existing_output=None,
    check_only=False,
):
    global COUNT
    with tempfile.TemporaryDirectory(prefix="aurora-modules-") as directory:
        base = Path(directory)
        groups = root_sets if root_sets is not None else [modules or {}]
        search = []
        for index, files in enumerate(groups):
            root = base / f"root{index}"
            root.mkdir()
            search.append(root)
            for module, text in files.items():
                path = root / (module.replace(".", "/") + ".au")
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text)
        if library:
            search.append(LIBRARY)
        if setup:
            setup(base, search)
        input_path = base / "input.au"
        input_path.write_text(source)
        assembly = base / "program.s"
        if existing_output is not None:
            assembly.write_text(existing_output)
        command = [COMPILER, input_path] + (["--check"] if check_only else ["-o", assembly])
        if roots:
            for root in search:
                command.extend(["--module-root", root])
        compiled = run(command, good=error is None)
        if error:
            require(compiled.returncode > 0, name + ": invalid graph accepted")
            if existing_output is None:
                require(not assembly.exists(), name + ": output created on rejection")
            else:
                require(assembly.read_text() == existing_output, name + ": existing output changed on rejection")
            require(error.encode() in compiled.stderr, name + ": " + repr(compiled.stderr))
        elif check_only:
            require(not assembly.exists(), name + ": check created output")
        else:
            bridge = base / "entry.s"
            bridge.write_text(""".text
.globl _start
_start:
    call test
    pushq %rax
    movq $1, %rax
    movq $1, %rdi
    movq %rsp, %rsi
    movq $8, %rdx
    syscall
    movq $60, %rax
    xorq %rdi, %rdi
    syscall
.section .note.GNU-stack,"",@progbits
""")
            run(["as", "--64", assembly, "-o", base / "program.o"])
            run(["as", "--64", bridge, "-o", base / "entry.o"])
            run(["ld", "-o", base / "program", base / "entry.o", base / "program.o"])
            executed = run([base / "program"], good=not trap)
            if trap:
                require(executed.returncode == -signal.SIGILL and not executed.stdout, name + ": expected exact SIGILL")
            else:
                require(len(executed.stdout) == 8, name + ": missing scalar result")
                require(
                    int.from_bytes(executed.stdout, "little", signed=True) == expected, name + ": wrong scalar result"
                )
        COUNT += 1
        print("PASS modules", name)


def app(body, imports=""):
    return "module app; " + imports + " auto test() -> i64 { " + body + " }"


check("old root seam", app("return 42;"), roots=False)
check(
    "std core execution",
    app("return std::min(42, 100) + std::max(-1, 0) + std::abs(0);", "import std.core;"),
    library=True,
)
check(
    "std min signed limits",
    app("return std::min(-9223372036854775808, 9223372036854775807);", "import std.core;"),
    library=True,
    expected=-9223372036854775808,
)
check(
    "std max signed limits",
    app("return std::max(-9223372036854775808, 9223372036854775807);", "import std.core;"),
    library=True,
    expected=9223372036854775807,
)
check("std abs negative", app("return std::abs(-42);", "import std.core;"), library=True)
check(
    "std abs minimum traps", app("return std::abs(-9223372036854775808);", "import std.core;"), library=True, trap=True
)
check(
    "std private helper inaccessible",
    app("return std::detail::select_min(42, 100);", "import std.core;"),
    library=True,
    error="private function",
)
check(
    "root helper cannot hijack std",
    (
        "module app; import std.core; namespace std::detail { auto select_min(i64 a,i64 b)->i64 { return 0; } }"
        " auto test()->i64 { return std::min(42,100); }"
    ),
    library=True,
)
check(
    "namespace forwards and reopen",
    (
        "module app; namespace app_api { auto value()->i64 { return later(); } } namespace app_api { auto later"
        "()->i64 { return 42; } } auto test()->i64 { return app_api::value(); }"
    ),
)
check(
    "namespace nested spelling",
    (
        "module app; namespace outer { namespace inner { auto value()->i64 { return 42; } } } auto test()->i64 "
        "{ return outer::inner::value(); }"
    ),
)
check(
    "namespace relative lookup",
    (
        "module app; namespace outer::inner { auto value()->i64 { return helper(); } } namespace outer { auto h"
        "elper()->i64 { return 42; } } auto test()->i64 { return outer::inner::value(); }"
    ),
)
check(
    "export function",
    app("return answer();", "import value;"),
    {"value": "export module value; export auto answer()->i64 { return 42; }"},
)
check(
    "private function rejection",
    app("return answer();", "import value;"),
    {"value": "export module value; auto answer()->i64 { return 42; }"},
    error="private function",
)
check(
    "defining module missing helper cannot use root",
    "module app; import value; auto helper()->i64 { return 42; } auto test()->i64 { return answer(); }",
    {"value": "export module value; export auto answer()->i64 { return helper(); }"},
    error="unknown function 'helper' in defining module value",
)
check(
    "two private helpers have separate identity",
    app("return a::value()+b::value();", "import one; import two;"),
    {
        "one": (
            "export module one; auto helper()->i64{return 20;} export namespace a { auto value()->i64{return he"
            "lper();} }"
        ),
        "two": (
            "export module two; auto helper()->i64{return 22;} export namespace b { auto value()->i64{return he"
            "lper();} }"
        ),
    },
)
check(
    "mangling module namespace boundary",
    app("return c::value()+b::c::value();", "import a; import a.b;"),
    {
        "a": "export module a; export namespace b::c { auto value()->i64{return 20;} }",
        "a.b": "export module a.b; export namespace c { auto value()->i64{return 22;} }",
    },
)
check(
    "direct dependency visible to defining body",
    app("return outer::value();", "import outer;"),
    {
        "outer": (
            "export module outer; import inner; export namespace outer { auto value()->i64 {return inner::value();} }"
        ),
        "inner": "export module inner; export namespace inner {auto value()->i64{return 42;}}",
    },
)
check(
    "transitive exports not implicit",
    app("return inner::value();", "import outer;"),
    {
        "outer": (
            "export module outer; import inner; export namespace outer { auto value()->i64 {return inner::value();} }"
        ),
        "inner": "export module inner; export namespace inner {auto value()->i64{return 42;}}",
    },
    error="unknown function",
)
check(
    "explicit reexport deferred",
    app("return 42;", "import outer;"),
    {"outer": "export module outer; export import inner;"},
    error="reexports are not supported",
)
check("exports require interface", "module app; export auto test()->i64{return 42;}", error="require an export module")
check(
    "import requires interface",
    app("return 42;", "import value;"),
    {"value": "module value; auto private_value()->i64{return 42;}"},
    error="requires an export module",
)
check(
    "duplicate module declaration rejected",
    "module app; module other; auto test()->i64{return 42;}",
    error="expected 'auto'",
)
check(
    "import after declaration rejected",
    "module app; auto test()->i64{return 42;} import value;",
    error="imports must precede",
)
check(
    "duplicate dotted import with trivia rejected",
    app("return 42;", "import value.part; import value // comment\n . part;"),
    {"value.part": "export module value.part; export auto answer()->i64{return 42;}"},
    error="duplicate import in app: value.part",
)
# Traversal must reach each edge before diagnosing its duplicate. In particular,
# an earlier dependency's parse/header failure is not hidden by a later edge.
for dependency, error in (
    ("export module value; @", "module value: unsupported character"),
    ("export module other;", "module header mismatch: expected value, got other"),
):
    check(
        "dependency failure precedes duplicate import: " + error,
        app("return 42;", "import value; import value;"),
        {"value": dependency},
        error=error,
        check_only=True,
    )
diamond = {
    "left": "export module left; import shared; export auto left_value()->i64{return shared_value();}",
    "right": "export module right; import shared; export auto right_value()->i64{return shared_value();}",
    "shared": "export module shared; export auto shared_value()->i64{return 21;}",
}
check(
    "diamond dependency visited once",
    app("return left_value()+right_value();", "import left; import right; import shared;"),
    diamond,
    check_only=True,
)
check(
    "depth first child failure precedes later sibling",
    app("return 42;", "import left; import right;"),
    {**diamond, "shared": "export module shared; @", "right": "export module wrong;"},
    error="module shared: unsupported character",
    check_only=True,
)
check(
    "duplicate visible exports",
    app("return 42;", "import one; import two;"),
    {
        "one": "export module one; export auto answer()->i64{return 20;}",
        "two": "export module two; export auto answer()->i64{return 22;}",
    },
    error="ambiguous visible declaration",
)
check(
    "root and imported export duplicate",
    "module app; import value; auto answer()->i64{return 0;} auto test()->i64{return answer();}",
    {"value": "export module value; export auto answer()->i64{return 42;}"},
    error="ambiguous visible declaration",
)
check(
    "duplicate namespace declaration",
    (
        "module app; namespace a {auto value()->i64{return 1;}} namespace a {auto value()->i64{return 2;}} auto"
        " test()->i64{return 42;}"
    ),
    error="duplicate or reserved function",
)
check(
    "namespace function name collision",
    "module app; namespace api {auto value()->i64{return 42;}} auto api()->i64{return 0;} auto test()->i64{return 42;}",
    error="namespace and declaration name collide",
)
check(
    "imported namespace local declaration collision",
    "module app; import value; auto api()->i64{return 0;} auto test()->i64{return 42;}",
    {"value": "export module value; export namespace api {auto value()->i64{return 42;}}"},
    error="namespace and declaration name collide",
)
check(
    "reserved native symbol declaration",
    "module app; auto __au_f_fake()->i64{return 42;} auto test()->i64{return 42;}",
    error="reserved compiler identifier",
)
check(
    "reserved native symbol call",
    app("return __au_f_m1_5value_n0__d6answer();", "import value;"),
    {"value": "export module value; auto answer()->i64{return 42;}"},
    error="reserved compiler identifier",
)
check(
    "reserved reflection scope selector", app("return __au_reflect_s1_size(100);"), error="reserved compiler identifier"
)

secret = """export module secret;
namespace api {
 class Hidden { public: i64 first; i64 second; };
 export class Public { public: i64 value; };
 export auto hidden_id()->i64{return type_id(Hidden);}
 export auto reveal_size()->i64{return reflect_size(type_id(Hidden));}
 export auto inspect(i64 id)->i64{return reflect_size(id);}
}
"""
check(
    "exported class inline local",
    app("const api::Public p=api::Public{.value=42}; return p.value;", "import secret;"),
    {"secret": secret},
)
check(
    "private class construction rejected",
    app("const api::Hidden p=api::Hidden{.first=20,.second=22}; return p.first+p.second;", "import secret;"),
    {"secret": secret},
    error="private type",
)
check(
    "private compile-time reflection rejected",
    app("return size_of(api::Hidden);", "import secret;"),
    {"secret": secret},
    error="private type",
)
check("private runtime id guessed", app("return reflect_size(100);", "import secret;"), {"secret": secret}, expected=0)
check(
    "private runtime returned id unavailable",
    app("return reflect_size(api::hidden_id());", "import secret;"),
    {"secret": secret},
    expected=0,
)
check(
    "private runtime field count unavailable",
    app("return reflect_field_count(api::hidden_id());", "import secret;"),
    {"secret": secret},
    expected=0,
)
check(
    "defining module can intentionally reveal own facts",
    app("return api::reveal_size();", "import secret;"),
    {"secret": secret},
    expected=16,
)
check(
    "public class runtime reflection",
    app("return reflect_size(type_id(api::Public))+reflect_field_count(type_id(api::Public));", "import secret;"),
    {"secret": secret},
    expected=9,
)
check(
    "callee cannot reflect caller private type",
    (
        "module app; import secret; class RootOnly { public: i64 a; i64 b; i64 c; }; auto test()->i64 { return "
        "api::inspect(type_id(RootOnly)); }"
    ),
    {"secret": secret},
    expected=0,
)
check(
    "private type through transitive reflection unavailable",
    app("return reflect_size(100);", "import wrapper;"),
    {
        "secret": secret,
        "wrapper": "export module wrapper; import secret; export auto value()->i64{return api::reveal_size();}",
    },
    expected=0,
)
check(
    "class-only exported module",
    app("const shapes::Point p=shapes::Point{.x=20,.y=22}; return p.x+p.y;", "import shapes;"),
    {"shapes": "export module shapes; export namespace shapes { class Point {public:i64 x;i64 y;}; }"},
)
check(
    "qualified private fields still private",
    app("const api::PrivateFields p=api::PrivateFields{.value=42}; return 0;", "import fields;"),
    {"fields": "export module fields; export namespace api {class PrivateFields {i64 value;};}"},
    error="requires public fields",
)
check(
    "aggregate parameter by value",
    app("Value value=Value{.x=42};return consume(value);", "import aggregate;"),
    {
        "aggregate": (
            "export module aggregate; export class Value {public:i64 x;}; export auto consume(Value value)->i64"
            "{return value.x;}"
        )
    },
)

check(
    "no ambient module search",
    app("return 42;", "import std.core;"),
    library=True,
    roots=False,
    error="explicit --module-root",
)
check("missing module", app("return 42;", "import missing;"), error="module not found")
check(
    "header mismatch",
    app("return 42;", "import value;"),
    {"value": "export module other; export auto answer()->i64{return 42;}"},
    error="module header mismatch",
)
check(
    "cycle",
    app("return 42;", "import one;"),
    {"one": "export module one; import two;", "two": "export module two; import one;"},
    error="module import cycle",
)
check("self cycle", app("return 42;", "import app;"), error="module import cycle")
check(
    "ambiguous module roots",
    app("return 42;", "import value;"),
    root_sets=[{"value": "export module value;"}, {"value": "export module value;"}],
    error="ambiguous module found",
)
check(
    "duplicate roots",
    app("return 42;"),
    setup=lambda base, roots: roots.append(roots[0]),
    error="duplicate module search root",
)


def escaping_link(base, roots):
    target = base / "outside.au"
    target.write_text("export module escape;")
    (roots[0] / "escape.au").symlink_to(target)


check(
    "symlink file escape",
    app("return 42;", "import escape;"),
    setup=escaping_link,
    error="escapes its explicit search root",
)


def escaping_directory(base, roots):
    target = base / "outside"
    target.mkdir()
    (target / "escape.au").write_text("export module pkg.escape;")
    (roots[0] / "pkg").symlink_to(target, target_is_directory=True)


check(
    "symlink directory escape",
    app("return 42;", "import pkg.escape;"),
    setup=escaping_directory,
    error="escapes its explicit search root",
)


def internal_link(base, roots):
    target = roots[0] / "actual.au"
    target.write_text("export module linked; export auto answer()->i64{return 42;}")
    (roots[0] / "linked.au").symlink_to(target)


check("contained symlink rejected", app("return answer();", "import linked;"), setup=internal_link, error="symlink")


def alias_identity(base, roots):
    target = roots[0] / "actual.au"
    target.write_text("export module one;")
    (roots[0] / "one.au").hardlink_to(target)
    (roots[0] / "two.au").hardlink_to(target)


check(
    "same file cannot alias module identity",
    app("return 42;", "import one; import two;"),
    setup=alias_identity,
    error="module header mismatch",
)
check("path traversal syntax rejected", app("return 42;", "import ../escape;"), error="expected identifier")
check("too many roots", app("return 42;"), root_sets=[{} for _ in range(17)], error="at most 16")
check(
    "FIFO source rejected without blocking",
    app("return 42;", "import pipe;"),
    setup=lambda base, roots: os.mkfifo(roots[0] / "pipe.au"),
    error="not a regular file",
)
check(
    "directory source rejected",
    app("return 42;", "import directory;"),
    setup=lambda base, roots: (roots[0] / "directory.au").mkdir(),
    error="not a regular file",
)
check(
    "imported argument type diagnostic",
    app("return std::min(true, 42);", "import std.core;"),
    library=True,
    error="expected i64",
)
check(
    "imported arity diagnostic uses source spelling",
    app("return std::min(42);", "import std.core;"),
    library=True,
    error="wrong argument count for std::min",
)
check("file byte cap", "module app; //" + "x" * (1024 * 1024), error="file exceeds")
large_modules = {f"large{i}": f"export module large{i}; //" + "x" * 900000 for i in range(5)}
check(
    "graph byte cap",
    app("return 42;", "".join(f"import large{i};" for i in range(5))),
    large_modules,
    error="graph exceeds 4194304",
)
check(
    "exactly 64 graph files accepted",
    app("return 42;", "".join(f"import item{i};" for i in range(63))),
    {f"item{i}": f"export module item{i};" for i in range(63)},
    check_only=True,
)
check(
    "graph file cap",
    app("return 42;", "".join(f"import item{i};" for i in range(64))),
    {f"item{i}": f"export module item{i};" for i in range(64)},
    error="graph exceeds 64",
)
chain = {f"level{i}": f"export module level{i}; import level{i + 1};" for i in range(16)}
chain["level16"] = "export module level16;"
check("import depth cap", app("return 42;", "import level0;"), chain, error="depth exceeds 16")
check(
    "exactly 16 import edges accepted",
    app("return 42;", "import level1;"),
    chain,
    check_only=True,
)
check(
    "depth checked before completed dependency shortcut",
    app("return 42;", "import level16; import level0;"),
    chain,
    error="module import depth exceeds 16",
    check_only=True,
)
check(
    "child header validated before entering excessive depth",
    app("return 42;", "import level0;"),
    {**chain, "level16": "export module wrong;"},
    error="module header mismatch: expected level16, got wrong",
    check_only=True,
)
check(
    "namespace depth cap",
    "module app; namespace "
    + "::".join("level" for _ in range(33))
    + " {auto value()->i64{return 42;}} auto test()->i64{return 42;}",
    error="namespace nesting exceeds",
)
check(
    "module component count cap",
    app("return 42;", "import " + ".".join("part" for _ in range(33)) + ";"),
    error="excessive module name",
)
check(
    "module component length cap",
    app("return 42;", "import " + "a" * 129 + ";"),
    error="invalid or excessive module name",
)
check(
    "import requires an interface unit",
    app("return 42;", "import value;"),
    {"value": "module value; auto answer()->i64{return 42;}"},
    error="imported module requires an export module interface: value",
)
check(
    "invalid module preserves existing artifact",
    app("return missing();"),
    error="unknown function",
    existing_output="previous artifact",
)

# Source identities come from opened descriptors; reject direct and hard-link outputs.
for alias in ("root", "import", "hardlink"):
    with tempfile.TemporaryDirectory(prefix="aurora-output-alias-") as directory:
        base = Path(directory)
        root = base / "input.au"
        dependency = base / "dependency.au"
        root_text = app("return answer();", "import dependency;")
        dependency_text = "export module dependency; export auto answer()->i64{return 42;}"
        root.write_text(root_text)
        dependency.write_text(dependency_text)
        destination = root if alias == "root" else dependency
        if alias == "hardlink":
            destination = base / "alias.s"
            destination.hardlink_to(dependency)
        result = run([COMPILER, root, "--module-root", base, "-o", destination], good=False)
        require(
            result.returncode > 0 and b"aliases a root or imported source" in result.stderr,
            "source output alias accepted",
        )
        require(
            root.read_text() == root_text and dependency.read_text() == dependency_text,
            "source alias damaged captured inputs",
        )
        COUNT += 1
        print("PASS modules output alias rejected", alias)

print(f"{COUNT} module/library tests passed")
