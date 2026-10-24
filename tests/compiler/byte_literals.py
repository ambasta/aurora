#!/usr/bin/env python3
"""Exact-u8 character spelling, native boundaries, diagnostics and numeric equivalence."""

import json
from pathlib import Path
import re
import sys
import tempfile

from native_runner import DIAGNOSTIC, Suite, Trap, command, require, run


def app(body, result="u8"):
    return f"module test;auto test()->{result}{{{body}}}"


def byte_string_length_diagnostics(compiler, root):
    source, output = root / "string-length.au", root / "string-length.s"
    # Independent decoded counts distinguish bytes from spelling length,
    # Unicode characters and an imagined terminator.
    for spelling, actual, expected in [
        ('""', 0, 1),
        ('"a"', 1, 2),
        ('"hello"', 5, 4),
        ('"é"', 2, 1),
        ('"😀"', 4, 1),
        (r'"\x4142\01"', 5, 4),
        (r'"\0"', 1, 2),
        (r'"\x00\xff"', 2, 1),
    ]:
        prefix = f"module test;auto test()->u8{{const array<u8,{expected}> b="
        source.write_text(prefix + spelling + ";return b[0];}")
        message = (
            f"array initializer length does not match its declared type: expected {expected} bytes, "
            f"got {actual} decoded bytes"
        )
        output.write_bytes(b"preserved\n")
        result = run([compiler, source, "-o", output], timeout=10)
        require(
            result.returncode == 1 and message in result.stderr.decode() and output.read_bytes() == b"preserved\n",
            f"string length diagnostic or failed output preservation: {spelling!r}: {result.stderr}",
        )
        result = run([compiler, "--check", "--diagnostics=json", source], timeout=10)
        require(result.returncode == 1, f"string length mismatch passed check: {spelling!r}")
        diagnostics = json.loads(result.stdout)["diagnostics"]
        require(len(diagnostics) == 1, f"string length diagnostic count: {diagnostics}")
        diagnostic = diagnostics[0]
        require(
            diagnostic["code"] == "AU3001"
            and diagnostic["message"] == message
            and diagnostic["range"]["start"]["offset"] == len(prefix.encode())
            and diagnostic["range"]["end"]["offset"] == len((prefix + spelling).encode()),
            f"string length diagnostic or source span: {diagnostic}",
        )
    print("PASS byte-string length diagnostics: 8 decoded byte counts, spans and preserved outputs")


def byte_strings(compiler, root, suite):
    # Strings reuse named array storage and the existing native value/trap oracle.
    spellings = [
        ('"IOMMU "', b"IOMMU "),
        (r'"\0\a\b\f\n\r\t\v\\\'\""', bytes([0, 7, 8, 12, 10, 13, 9, 11, 92, 39, 34])),
        ('"é中😀"', "é中😀".encode()),
        ('"' + "".join(f"\\x{value:02x}" for value in range(256)) + '"', bytes(range(256))),
        (r'"\x4142\01"', b"A42\x001"),  # Exactly two hex digits; zero is not octal.
        ('"' + "a" * 4096 + '"', b"a" * 4096),
    ]
    source, output = root / "string.au", root / "string.s"
    for spelling, expected in spellings:
        if len(expected) <= 256:
            body = f"const array<u8,{len(expected)}> b={spelling};"
            body += "const builtin::span<const u8> view=borrow_bytes(b);"
            body += f"if(view.size()!={len(expected)}){{return 1u64;}}"
            body += "".join(f"if(view.at({i})!={value}u8){{return 2u64;}}" for i, value in enumerate(expected))
            name = f"byte-string contents and exact borrowed extent {spelling[:16]}"
            suite.value(name, body + "return 0u64;", 0, "u64")

        # No hidden terminator, alternate storage, lifetime or backend operation.
        def assembly(initializer):
            source.write_text(app(f"const array<u8,{len(expected)}> b={initializer};return b[{len(expected) - 1}];"))
            command([compiler, source, "-o", output])
            return output.read_bytes()

        require(
            assembly(spelling) == assembly("{" + ",".join(f"{value}u8" for value in expected) + "}"),
            "string initializer changed assembly relative to explicit byte array",
        )
    # The capacity boundary is compiled and executed without inflating source depth.
    suite.value(
        "maximum string array",
        'array<u8,4096> b="' + "a" * 4096 + '";'
        "b[4095]='z';const array<u8,4096> copy=b;"
        "const builtin::span<const u8> view=borrow_bytes(copy);"
        "return u64(view.at(4095))+u64(view.size());",
        4218,
        "u64",
    )
    byte_string_length_diagnostics(compiler, root)
    malformed = [
        b'"unclosed',
        b'"\\',
        b'"\\q"',
        b'"\\x"',
        b'"\\x0"',
        b'"\\xGG"',
        b'"\\u0041"',
        b'"\\U00000041"',
        b'"\\101"',
        b'"a"u8',
        b'"a"_suffix',
        b'"a"0',
        b'"\\\n"',
        b'"\\\r"',
        b'"' + b"a" * 4097 + b'"',
    ]
    malformed += [b'"' + bytes([value]) + b'"' for value in list(range(32)) + [127, 128, 191, 192, 193, 245, 255]]
    malformed += [
        b'"' + value + b'"'
        for value in [
            b"\xc2",
            b"\xc2A",
            b"\xe0\x80\x80",
            b"\xed\xa0\x80",
            b"\xf0\x80\x80\x80",
            b"\xf4\x90\x80\x80",
            b"\xe2\x82",
            b"\xf0\x90\x80",
        ]
    ]
    prefix = b"module test;\r\n\tauto test()->u8{const array<u8,1> b="
    column = len(prefix.split(b"\n")[-1]) + 1
    lexical = re.compile(rf"[^\n]*:2:{column}: error AU1003: [^\n]+\n")
    for spelling in malformed:
        suite.reject(f"malformed byte string {spelling!r}", prefix + spelling + b";return b[0];}", pattern=lexical)
    rejected = [
        'const array<u8,1> b="";return 0u8;',
        'const array<u8,2> b="a";return 0u8;',
        'const array<u8,1> b="ab";return 0u8;',
        'const array<u8,1> b="é";return 0u8;',
        'const array<i64,1> b="a";return 0u8;',
        'const array<u64,1> b="a";return 0u8;',
        'const array<bool,1> b="a";return 0u8;',
        'const u8 b="a";return b;',
        'return "a";',
        'const builtin::span<const u8> v=borrow_bytes("a");return 0u8;',
        'const builtin::span<const u8> v="a";return 0u8;',
        "array<u8,1> b=\"a\";const builtin::span<const u8> v=borrow_bytes(b);b[0]='b';return v.at(0);",
        'array<u8,1> b="a";b="b";return b[0];',
        'const array<u8,2> b="a" "b";return b[0];',
        'const array<u8,0> b="";return 0u8;',
        'const array<u8,4097> b="a";return 0u8;',
    ]
    for body in rejected:
        suite.reject(f"string type/length/lifetime restriction {body}", app(body))
    suite.reject(
        "string-backed local array escaped through returned view",
        "module test;class Box{builtin::OwnedBytes payload;public:"
        "Box(builtin::ByteRegion region,builtin::OwnedBytes initial):payload(move(initial)){}"
        "auto view()const->builtin::span<const u8>{"
        'const array<u8,1> b="a";return borrow_bytes(b);}};auto test()->u8{return 0u8;}',
        "returned span must derive directly",
    )
    for program, diagnostic in [
        (
            'module test;auto take(u8 value)->u8{return value;}auto test()->u8{return take("a");}',
            "byte-string literals require a typed local u8 array initializer",
        ),
        (
            'module test;class Box{array<u8,1> data;public:Box():data("a"){} };auto test()->u8{return 0u8;}',
            "array fields require explicit empty-brace zero initialization",
        ),
    ]:
        suite.reject("string escaped its local initializer context", program, diagnostic)
    print("PASS byte-string arrays: 6 exact assembly comparisons", flush=True)


def literal_span_calls(compiler, root, suite):
    helper = "auto length(builtin::span<const u8> bytes)->u64{return u64(bytes.size());}"
    cases = [
        ("literal empty span", 'return length("");', 0, helper, ()),
        ("literal UTF-8 extent", 'return length("é😀");', 6, helper, ()),
        ("literal exact maximum", 'return length("' + "x" * 4096 + '");', 4096, helper, ()),
        (
            "literal subspan and binary forwarding",
            r'return forward("x\0\xffz");',
            255,
            "auto at(builtin::span<const u8> bytes)->u64{return u64(bytes.at(1));}"
            "auto forward(builtin::span<const u8> bytes)->u64{return at(bytes.subspan(1,2));}",
            (),
        ),
        (
            "literal selects exact span overload",
            'return pick("ab");',
            2,
            helper + "auto pick(i64 value)->u64{return 99u64;}"
            "auto pick(builtin::span<const u8> bytes)->u64{return length(bytes);}",
            (),
        ),
        (
            "multiple literal arguments and repeated loop cleanup",
            r'if(!std::equal("\0\xff", "\0\xff") || !std::equal("", "")'
            r' || !std::starts_with("write x y", "write ") || std::equal("a", "ab")) {return 0u64;}'
            'i64 index=0;while(index<32){if(!std::starts_with("abc", "a")){return 0u64;}'
            "index=index+1;}return 42u64;",
            42,
            "",
            ("std.bytes",),
        ),
        (
            "mutable receiver accepts literal readonly parameter",
            r"std::BinaryBuffer64 buffer=std::BinaryBuffer64();"
            r'if(!buffer.starts_with(2, "\0\0") || buffer.starts_with(2, "x")){return 0u64;}'
            "buffer.write_u8(0,'x');if(!buffer.starts_with(2, \"x\")){return 0u64;}return 42u64;",
            42,
            "",
            ("std.binary_buffer", "std.binary"),
        ),
    ]
    for name, body, expected, prelude, imports in cases:
        suite.value(name, body, expected, "u64", prelude, imports)
    rejected = [
        app('return "x";'),
        app('const builtin::span<const u8> bytes="x";return 0u8;'),
        app('const builtin::span<const u8> bytes=borrow_bytes("x");return 0u8;'),
        app('return "x"[0];'),
        app('return u8("x");'),
        'module test;auto take(u8 value)->u8{return value;}auto test()->u8{return take("x");}',
        'module test;auto take(i64 v)->u8{return 0u8;}auto take(u8 v)->u8{return v;}auto test()->u8{return take("x");}',
        'module test;auto escaped()->builtin::span<const u8>{return "x";}auto test()->u8{return 0u8;}',
        "module test;class Box{public:Box(builtin::span<const u8> text){}};"
        'auto test()->u8{Box box=Box("x");return 0u8;}',
        "module test;" + helper + 'auto test()->u64{return length("' + "x" * 4097 + '");}',
    ]
    for index, program in enumerate(rejected[:-1]):
        suite.reject(f"literal nonescaping boundary {index}", program, pattern=DIAGNOSTIC)
    suite.reject("oversized literal argument escaped the existing lexer bound", rejected[-1], "AU1003")
    # Inspect the real object section independently of source/IR length metadata.
    source, assembly, obj, payload = (root / ("literal-data" + suffix) for suffix in (".au", ".s", ".o", ".bin"))
    source.write_text("module test;" + helper + r'auto test()->u64{return length("a\0\xff");}')
    command([compiler, source, "-o", assembly])
    command(["as", "--64", assembly, "-o", obj])
    command(["objcopy", "--dump-section", f".rodata={payload}", obj])
    require(payload.read_bytes() == b"a\0\xff", "literal backing bytes or hidden terminator changed")
    section = next(line for line in command(["readelf", "-SW", obj]).stdout.decode().splitlines() if ".rodata " in line)
    flags = section.split("PROGBITS", 1)[1].split()[4]
    require(flags == "A", f"literal section is not readonly allocated data: {section}")
    print("PASS literal span calls: exact readonly object bytes", flush=True)


def fixed_array_views(compiler, root, suite):
    span = "builtin::span<const u8>"
    box = (
        (
            "class ViewBox { i64 padding; array<u8,3> data; array<u8,2> other; public:"
            "ViewBox():padding(17),data{},other{}{}"
            "auto initialize()->i64{data[0]='a';data[2]='\\xff';other[0]='x';other[1]='y';return 0;}"
            f"auto bytes(i64 offset,i64 count)const->{span}{{const {span} all=borrow_bytes(data);"
            "return all.subspan(offset,count);}"
            "auto set(u8 value)->i64{data[0]=value;return 0;}"
            "auto first()const->u8{return data[0];}"
            "};"
        )
        .replace("'\\\\0'", "'\\0'")
        .replace("'\\\\xff'", "'\\xff'")
    )
    suite.value(
        "fixed field exact layout and lifetime",
        "ViewBox box=ViewBox();box.initialize();"
        f"{{const {span} view=box.bytes(0,3);const {span} child=view.subspan(1,2);"
        "if(view.size()!=3 || view.at(0)!='a' || child.at(0)!='\\0' || child.at(1)!='\\xff'){return 0u64;}"
        "const ViewBox copy=box;if(copy.first()!='a'){return 1u64;}}"
        "box.set('z');return u64(box.first());",
        122,
        "u64",
        box,
    )
    suite.value(
        "fixed field independent copied root",
        "ViewBox box=ViewBox();box.initialize();ViewBox copy=box;"
        f"const {span} view=box.bytes(0,1);copy.set('z');return u64(view.at(0));",
        97,
        "u64",
        box,
    )
    suite.value(
        "fixed empty endpoint window",
        f"ViewBox box=ViewBox();box.initialize();const {span} view=box.bytes(3,0);return u64(view.size());",
        0,
        "u64",
        box,
    )
    suite.value(
        "fixed temporary argument and release",
        "ViewBox box=ViewBox();box.initialize();"
        "if(!std::equal(box.bytes(0,1),\"a\")){return 0u64;}box.set('b');return u64(box.first());",
        98,
        "u64",
        box,
        ("std.bytes",),
    )
    for offset, count in [
        (-1, 0),
        (0, -1),
        (4, 0),
        (3, 1),
        (1, 3),
        (-(1 << 63), 0),
        ((1 << 63) - 1, 0),
        (0, (1 << 63) - 1),
    ]:
        suite.value(
            f"fixed field checked window bounds {offset} {count}",
            "ViewBox box=ViewBox();box.initialize();"
            f"const {span} view=box.bytes({offset},{count});return u64(view.size());",
            Trap.BOUNDS,
            "u64",
            box,
        )
    suite.value(
        "fixed empty view cannot load",
        f"ViewBox box=ViewBox();box.initialize();const {span} view=box.bytes(3,0);return u64(view.at(0));",
        Trap.BOUNDS,
        "u64",
        box,
    )
    bad = {
        "named root mutation": "ViewBox box=ViewBox();box.initialize();"
        + f"const {span} view=box.bytes(0,0);box.set('x');return 0u64;",
        "descendant root mutation": "ViewBox box=ViewBox();box.initialize();"
        + f"const {span} view=box.bytes(0,3);const {span} child=view.subspan(0,0);box.set('x');return 0u64;",
        "later argument mutation": "ViewBox box=ViewBox();box.initialize();"
        "return inspect(box.bytes(0,1),box.set('x'));",
        "temporary receiver": f"const {span} view=ViewBox().bytes(0,1);return 0u64;",
        "private field projection": "ViewBox box=ViewBox();box.initialize();"
        + f"const {span} view=borrow_bytes(box.data);return 0u64;",
        "span rebinding": "ViewBox box=ViewBox();box.initialize();"
        + f"const {span} view=box.bytes(0,1);view=box.bytes(1,1);return 0u64;",
    }
    diagnostics = {
        "named root mutation": "readonly span is live",
        "descendant root mutation": "readonly span is live",
        "later argument mutation": "readonly span is live",
        "temporary receiver": "method receiver requires a class local",
        "private field projection": "private class field is inaccessible",
        "span rebinding": "assignment requires a mutable scalar local",
        "mutable return": "span results require a const",
        "local return": "returned span must derive directly",
        "different fields": "same receiver byte-storage field",
        "in-method mutation": "readonly span is live",
        "same-class projection": "borrow_bytes fields require",
    }
    helpers = box + f"auto inspect({span} bytes,i64 unused)->u64{{return u64(bytes.size());}}"
    for label, body in bad.items():
        suite.reject(
            "fixed array view rejection " + label,
            "module bad;" + helpers + "auto test()->u64{" + body + "}",
            diagnostics[label],
        )
    for label, methods in {
        "mutable return": f"auto bytes()->{span}{{return borrow_bytes(data);}}",
        "local return": f"auto bytes()const->{span}{{array<u8,1> local={{0u8}};return borrow_bytes(local);}}",
        "different fields": f"auto bytes(bool choose)const->{span}{{"
        "if(choose){return borrow_bytes(data);}return borrow_bytes(other);}",
        "in-method mutation": f"auto mutate()->i64{{const {span} view=borrow_bytes(data);"
        "data[0]='z';return view.size();}",
        "same-class projection": f"auto inspect(ViewBox copy)const->i64{{"
        f"const {span} view=borrow_bytes(copy.data);return view.size();}}",
    }.items():
        suite.reject(
            "fixed array view rejection " + label,
            "module bad;class ViewBox{array<u8,3> data;array<u8,2> other;public:"
            "ViewBox():data{},other{}{}" + methods + "};auto test()->u64{return 0u64;}",
            diagnostics[label],
        )


def main():
    compiler = Path(sys.argv[1]).resolve(strict=True)
    suite = Suite(compiler, "byte literals", timeout=10)
    spellings = [(f"'\\x{value:02X}'", value) for value in range(256)]
    spellings += [("'" + chr(value) + "'", value) for value in range(32, 127) if value not in (39, 92)]
    spellings += [
        ("'\\" + escape + "'", value)
        for escape, value in [
            ("'", 39),
            ("\\", 92),
            ("0", 0),
            ("a", 7),
            ("b", 8),
            ("f", 12),
            ("n", 10),
            ("r", 13),
            ("t", 9),
            ("v", 11),
        ]
    ]
    spellings += [("'\\xff'", 255), ("'\\xAb'", 171)]
    for spelling, value in spellings:
        suite.value(
            f"byte spelling {spelling}", f"static_assert({spelling}=={value}u8);return u64({spelling});", value, "u64"
        )
    suite.value("byte operations", r"return u64((~'\0' & '\x0f') + '\x01');", 16, "u64")
    suite.value("signed widening", "return i64('[');", 91, "i64")
    suite.value("literal shift", r"return u64('\x01' << 7);", 128, "u64")
    suite.value("literal array", r"const array<u8,3> b={'[','\0','\xff'};return u64(b[2]);", 255, "u64")
    suite.value(
        "literal parameter and direct copied return",
        "const Box b=make('[');return u64(b.get());",
        91,
        "u64",
        "class Box{u8 value;public:Box(u8 v):value(v){}auto get()const->u8{return value;}};"
        "auto make(u8 value)->Box{return Box(value);}",
    )
    for body, trap in [
        (r"return u64('\xff'+ '\x01');", Trap.OVERFLOW),
        (r"return u64('\0' - '\x01');", Trap.OVERFLOW),
        (r"return u64('a' / '\0');", Trap.ZERO),
        (r"return u64('a' << 8);", Trap.COUNT),
    ]:
        suite.value("character preserves checked trap " + body, body, trap, "u64")
    invalid = [
        "''",
        "'ab'",
        "'''",
        "'a",
        "'\\",
        "'\\q'",
        "'\\x'",
        "'\\x0'",
        "'\\x000'",
        "'\\x100'",
        "'\\xGG'",
        "'\\u0041'",
        "'\\U00000041'",
        "'\\101'",
        "'\\01'",
        "'\\\"'",
        "'é'",
        "'😀'",
        "'\t'",
        "'\0'",
        "'\x7f'",
        "'\n'",
        "'\r'",
        "'\\\n'",
        "'\\\r'",
        "'a'u8",
        "'a'u64",
        "'a'0",
        "'a'_suffix",
    ]
    # Every raw non-ASCII byte is rejected even when not valid UTF-8.
    invalid_bytes = [x.encode() for x in invalid] + [b"'" + bytes([n]) + b"'" for n in range(128, 256)]
    with tempfile.TemporaryDirectory(prefix="aurora-byte-literals-") as temporary:
        root = Path(temporary)
        byte_strings(compiler, root, suite)
        literal_span_calls(compiler, root, suite)
        fixed_array_views(compiler, root, suite)
        prefix = b"module test;\r\n\tauto test()->u8{return "
        lexical = re.compile(r"[^\n]*:2:25: error AU1002: invalid byte literal\n")
        for spelling in invalid_bytes:
            suite.reject(f"invalid byte literal {spelling!r}", prefix + spelling + b";}", pattern=lexical)
        # Structured and text diagnostics report the same code and location.
        path, output = root / "invalid.au", root / "preserved.s"
        path.write_bytes(prefix + invalid_bytes[0] + b";}")
        result = run([compiler, "--check", "--diagnostics=json", path], timeout=10)
        require(result.returncode == 1 and not result.stderr, "expected lexical rejection")
        diagnostic = json.loads(result.stdout)["diagnostics"][0]
        require(
            diagnostic["code"] == "AU1002"
            and diagnostic["range"]["start"] == {"offset": len(prefix), "line": 2, "column": 25},
            f"byte diagnostic: {diagnostic}",
        )
        for body, result_type in [
            ("return 'a';", "i64"),
            ("return 'a';", "u64"),
            ("return 'a';", "bool"),
            ("return -'a';", "u8"),
            ("return 'a'+1;", "u8"),
            ("return 'a'==97;", "bool"),
            ("return u8('a');", "u8"),
            ("static_assert('a'==97);return 'a';", "u8"),
            ("i64 n='a';return 'a';", "u8"),
        ]:
            suite.reject(f"implicit widening/type error {body} {result_type}", app(body, result_type), " AU3001: ")
        suite.reject(
            "imported malformed literal keeps its source provenance",
            "module test;import dependency;auto test()->u8{return dependency::invalid();}",
            re.compile(r"/dependency\.au:[0-9]+:[0-9]+: error AU1002: "),
            modules={"dependency": "export module dependency;export auto invalid()->u8{return 'ab';}"},
        )
        suite.finish()
        # Exact generated assembly for every accepted spelling, under identical names.
        source = root / "equivalent.au"

        def assembly(literals):
            source.write_text(
                "module test;\n"
                + "\n".join(f"auto value_{index}()->u8{{return {value};}}" for index, value in enumerate(literals))
            )
            command([compiler, source, "-o", output])
            return output.read_bytes()

        require(
            assembly([s for s, _ in spellings]) == assembly([f"{v}u8" for _, v in spellings]),
            "byte literals changed assembly relative to decimal u8",
        )
    print(f"PASS byte literal assembly: {len(spellings)} assembly-equivalent spellings")


if __name__ == "__main__":
    main()
