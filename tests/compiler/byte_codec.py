#!/usr/bin/env python3
"""Native byte codec behavior, independent endian model, and packed value layout.

--without-layout is only the intermediate numerical gate: it deliberately does
not establish compact storage. The default run includes representation checks.
The shared runner verifies full-width values and preserves failed artifacts.
"""

from pathlib import Path
import argparse
import hashlib
import random
import tempfile

from unsigned_oracle import Case, NativeRunner, Rejection, command, require, validate_values


def codec_cases(seed, count):
    rng = random.Random(seed)
    values = [0, 1, 42, 127, 128, 255, 256, 65535, 65536, 0x12345678, 0x80000000, 0xFFFFFFFF, 1 << 32, (1 << 64) - 1]
    values += [rng.randrange(1 << 32) for _ in range(count)]
    for value in values:
        for endian, opposite in (("le", "be"), ("be", "le")):
            valid = value < (1 << 32)
            expected = value if valid else 0
            body = (
                f"const std::Encode32Result report=std::encode_{endian}32({value}u64);"
                f"if(report.status()!=std::ByteCodecStatus::{'success' if valid else 'out_of_range'})"
                "{return 18446744073709551615u64;}"
                "const std::Bytes4 bytes=report.bytes_or_zero();"
                f"return std::decode_{endian}32(bytes);"
            )
            yield Case(f"{endian} roundtrip {value}", body, expected, imports=("std.bytes",))
            if valid:
                ordered = value.to_bytes(4, "little" if endian == "le" else "big")
                opposite_value = int.from_bytes(ordered, "big" if endian == "le" else "little")
                yield Case(
                    f"{endian} cross decode {value}",
                    f"const std::Encode32Result report=std::encode_{endian}32({value}u64);"
                    "const std::Bytes4 bytes=report.bytes_or_zero();"
                    f"return std::decode_{opposite}32(bytes);",
                    opposite_value,
                    imports=("std.bytes",),
                )
                for index, byte in enumerate(ordered):
                    yield Case(
                        f"{endian} byte {index} of {value}",
                        f"const std::Encode32Result report=std::encode_{endian}32({value}u64);"
                        "const std::Bytes4 bytes=report.bytes_or_zero();"
                        f"return u64(bytes.at({index}));",
                        byte,
                        imports=("std.bytes",),
                    )
    yield Case(
        "failure masks a deliberately nonzero public report",
        """
        std::Bytes4 source=std::Bytes4(); source.set(0,255u8);source.set(3,255u8);
        const std::Encode32Result report=std::Encode32Result(std::ByteCodecStatus::out_of_range,source);
        const std::Bytes4 copy=report.bytes_or_zero();return std::decode_le32(copy);
    """,
        0,
        imports=("std.bytes",),
    )
    yield Case(
        "success report and output copies are independent",
        """
        std::Bytes4 source=std::Bytes4();source.set(0,42u8);
        const std::Encode32Result report=std::Encode32Result(std::ByteCodecStatus::success,source);
        source.set(0,1u8);std::Bytes4 copy=report.bytes_or_zero();copy.set(0,9u8);
        const std::Bytes4 original=report.bytes_or_zero();return std::decode_le32(original);
    """,
        42,
        imports=("std.bytes",),
    )
    yield Case(
        "all byte values remain valid data",
        """
        std::Bytes4 source=std::Bytes4();source.set(0,255u8);source.set(1,255u8);
        source.set(2,255u8);source.set(3,255u8);return std::decode_be32(source);
    """,
        0xFFFFFFFF,
        imports=("std.bytes",),
    )


def storage_codec_cases(seed, count):
    rng = random.Random(seed)
    for width in (16, 64):
        size = width // 8
        maximum = (1 << width) - 1
        values = [0, 1, 42, 127, 128, 255, 256, 0x1234, 0x8000, 65535]
        if width == 16:
            values += [65536, 1 << 32, (1 << 64) - 1]
        else:
            values += [1 << 32, 1 << 63, 0x0123456789ABCDEF, maximum]
        values += [rng.randrange(1 << width) for _ in range(count)]
        for value in values:
            for endian, opposite in (("le", "be"), ("be", "le")):
                valid = value <= maximum
                if width == 16:
                    setup = (
                        f"const std::Encode16Result report=std::encode_{endian}16({value}u64);"
                        f"if(report.status()!=std::ByteCodecStatus::{'success' if valid else 'out_of_range'})"
                        "{return 0u64;}const std::Bytes2 bytes=report.bytes_or_zero();"
                    )
                else:
                    setup = f"const std::Bytes8 bytes=std::encode_{endian}64({value}u64);"
                ordered = (value if valid else 0).to_bytes(size, "little" if endian == "le" else "big")
                # Compare every encoded byte against Python's independent wire model.
                checks = "".join(f"if(bytes.at({i})!={byte}u8){{return 0u64;}}" for i, byte in enumerate(ordered))
                yield Case(
                    f"{endian}{width} bytes and status {value}",
                    setup + checks + "return 42u64;",
                    42,
                    imports=("std.bytes",),
                )
                if valid:
                    yield Case(
                        f"{endian}{width} roundtrip {value}",
                        setup + f"return std::decode_{endian}{width}(bytes);",
                        value,
                        imports=("std.bytes",),
                    )
                    reversed_value = int.from_bytes(ordered, "big" if endian == "le" else "little")
                    yield Case(
                        f"{endian}{width} cross decode {value}",
                        setup + f"return std::decode_{opposite}{width}(bytes);",
                        reversed_value,
                        imports=("std.bytes",),
                    )

        patterns = [
            bytes(size),
            bytes([255]) * size,
            bytes([128]) + bytes(size - 1),
            bytes(size - 1) + bytes([128]),
            bytes(range(1, size + 1)),
        ]
        patterns += [bytes(rng.randrange(256) for _ in range(size)) for _ in range(count)]
        for index, pattern in enumerate(patterns):
            setup = f"std::Bytes{size} bytes=std::Bytes{size}();"
            setup += "".join(f"bytes.set({i},{byte}u8);" for i, byte in enumerate(pattern))
            for endian in ("le", "be"):
                # Decode independently assembled bytes; do not rely on encode/decode agreement.
                yield Case(
                    f"{endian}{width} independent input {index}",
                    setup + f"return std::decode_{endian}{width}(bytes);",
                    int.from_bytes(pattern, "little" if endian == "le" else "big"),
                    imports=("std.bytes",),
                )
        yield Case(
            f"Bytes{size} zero initialization",
            f"""
            const std::Bytes{size} bytes=std::Bytes{size}();
            return std::decode_le{width}(bytes);
        """,
            0,
            imports=("std.bytes",),
        )
        yield Case(
            f"Bytes{size} copied function value and result",
            f"""
            std::Bytes{size} original=std::Bytes{size}();
            if(original.set(0,42u8)!=42u8){{return 0u64;}}
            original.set({size - 1},128u8);
            std::Bytes{size} copy=identity(original);
            original.set(0,1u8);copy.set({size - 1},0u8);
            if(original.at({size - 1})!=128u8){{return 0u64;}}
            return std::decode_le{width}(copy);
        """,
            42,
            imports=("std.bytes",),
            prelude=f"auto identity(std::Bytes{size} value)->std::Bytes{size}{{return value;}}",
        )
        for endian in ("le", "be"):
            value = 0x1234 if width == 16 else 0x0123456789ABCDEF
            setup = (
                f"const std::Encode16Result report=std::encode_{endian}16({value}u64);"
                "const std::Bytes2 bytes=report.bytes_or_zero();"
                if width == 16
                else f"const std::Bytes8 bytes=std::encode_{endian}64({value}u64);"
            )
            elements = ",".join(f"bytes.at({i})" for i in range(size))
            yield Case(
                f"{endian}{width} owned encoding to readonly reader",
                setup + f"const builtin::array<u8,{size}> wire={{{elements}}};"
                f"const std::ByteReadResult read=std::read_{endian}{width}(borrow_bytes(wire),0);"
                "if(read.status()!=std::ByteReadStatus::success){return 0u64;}"
                "return read.value_or(0u64);",
                value,
                imports=("std.bytes", "std.binary"),
            )

    yield Case(
        "16-bit failure masks all nonzero public payload bytes",
        """
        std::Bytes2 source=std::Bytes2();source.set(0,255u8);source.set(1,255u8);
        const std::Encode16Result report=std::Encode16Result(std::ByteCodecStatus::out_of_range,source);
        const std::Bytes2 copy=report.bytes_or_zero();return std::decode_le16(copy);
    """,
        0,
        imports=("std.bytes",),
    )
    yield Case(
        "16-bit report constructor and accessors copy independently",
        """
        std::Bytes2 source=std::Bytes2();source.set(0,42u8);source.set(1,128u8);
        const std::Encode16Result report=std::Encode16Result(std::ByteCodecStatus::success,source);
        source.set(0,1u8);std::Bytes2 copy=report.bytes_or_zero();copy.set(1,0u8);
        const std::Bytes2 saved=report.bytes_or_zero();return std::decode_le16(saved);
    """,
        0x802A,
        imports=("std.bytes",),
    )
    yield Case(
        "64-bit encoded results and copies are independent",
        """
        std::Bytes8 original=std::encode_le64(9223372036854775850u64);
        std::Bytes8 copy=original;original.set(0,1u8);copy.set(7,0u8);
        if(original.at(7)!=128u8){return 0u64;}return std::decode_le64(copy);
    """,
        42,
        imports=("std.bytes",),
    )


def storage_rejections():
    bodies = [
        "const std::Encode16Result result=std::encode_le16(42u64);const std::Bytes2 bytes=result.payload;return 0u64;",
        "const std::Encode16Result result=std::encode_le16(42);return 0u64;",
        "const std::Bytes8 bytes=std::encode_be64(42);return 0u64;",
        "const std::Bytes4 bytes=std::Bytes4();return std::decode_le16(bytes);",
        "const std::Bytes4 bytes=std::Bytes4();return std::decode_be64(bytes);",
        "const std::Bytes8 bytes=std::encode_le64(42u64);const std::Bytes8 copy=bytes.bytes_or_zero();return 0u64;",
    ]
    for size in (2, 8):
        bodies += [
            f"std::Bytes{size} bytes=std::Bytes{size}();return u64(bytes.elements[0]);",
            f"const std::Bytes{size} bytes=std::Bytes{size}();bytes.set(0,1u8);return 0u64;",
            f"std::Bytes{size} bytes=std::Bytes{size}();bytes.set(0,256u64);return 0u64;",
        ]
    for index, body in enumerate(bodies):
        yield Rejection(
            f"storage codec visibility/type rejection {index}",
            "module test;import std.bytes;auto test()->u64{" + body + "}",
        )


def layout_cases():
    for capacity in (1, 3, 4, 7, 8, 9, 64):
        yield Case(
            f"compact wrapper capacity {capacity}",
            f"""
            static_assert(size_of(builtin::array<u8,{capacity}>)=={capacity});
            static_assert(size_of(std::array<u8,{capacity}>)=={capacity});
            std::array<u8,{capacity}> bytes=std::array<u8,{capacity}>();
            bytes.set({capacity - 1},255u8);
            const std::array<u8,{capacity}> copy=bytes;
            bytes.set({capacity - 1},0u8);
            if(reflect_size(type_id(std::array<u8,{capacity}>))!={capacity}){{return 0u64;}}
            return u64(copy.at({capacity - 1}));
        """,
            255,
            imports=("std.array",),
        )
    yield Case(
        "codec representation and nominal metadata",
        """
        static_assert(size_of(std::Bytes2)==2);
        static_assert(size_of(std::Bytes4)==4);
        static_assert(size_of(std::Bytes8)==8);
        static_assert(size_of(std::Encode16Result)==16);
        static_assert(size_of(std::Encode32Result)==16);
        static_assert(field_count(std::Bytes2)==0);
        static_assert(field_count(std::Bytes4)==0);
        static_assert(field_count(std::Bytes8)==0);
        if(reflect_size(type_id(std::Bytes2))!=2){return 0u64;}
        if(reflect_size(type_id(std::Bytes4))!=4){return 0u64;}
        if(reflect_size(type_id(std::Bytes8))!=8){return 0u64;}
        return 42u64;
    """,
        42,
        imports=("std.bytes",),
    )
    definitions = """
        class Empty{public:Empty(){}};
        class Small{public:u8 first;u8 second;};
        class Mixed{public:u8 first;u64 wide;bool flag;u8 last;};
        class Nested{public:u8 first;Small small;Empty empty;u64 last;
            Nested(u8 f,Small s,Empty e,u64 l):first(f),small(s),empty(e),last(l){}
        };
        auto identity(Nested n)->Nested{return n;}
    """
    yield Case(
        "natural mixed widths nested empty and copied results",
        """
        static_assert(size_of(Small)==2);static_assert(size_of(Mixed)==32);
        static_assert(size_of(Nested)==16);static_assert(size_of(Empty)==8);
        const Small small=Small{.first=200u8,.second=255u8};const Empty empty=Empty();
        const Nested original=Nested(1u8,small,empty,42u64);
        const Nested copy=identity(original);Small projected=copy.small;
        projected.second=0u8;const Small preserved=original.small;
        if(preserved.second!=255u8){return 0u64;}return copy.last;
    """,
        42,
        prelude=definitions,
    )


def rejections():
    bodies = [
        "return result.payload;",
        "return result.value();",
        "std::Bytes4 bytes=result.bytes_or_zero();return bytes.elements[0];",
        "const std::Bytes4 bytes=result.bytes_or_zero();bytes.set(0,1u8);return 0u64;",
        "return std::encode_le32(42);",
        "std::Bytes4 bytes=std::Bytes4();bytes.set(0,256u64);return 0u64;",
        "const std::Bytes4 bytes=std::Bytes4{.elements={0u8,0u8,0u8,0u8}};return 0u64;",
    ]
    for index, body in enumerate(bodies):
        yield Rejection(
            f"codec visibility/type rejection {index}",
            "module test;import std.bytes;auto test()->u64{"
            "const std::Encode32Result result=std::encode_le32(42u64);" + body + "}",
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("compiler", type=Path)
    parser.add_argument("--seed", type=int, default=13013)
    parser.add_argument("--random-count", type=int, default=16)
    parser.add_argument("--without-layout", action="store_true")
    args = parser.parse_args()
    require(0 <= args.random_count <= 256, "random-count must be 0..256")
    compiler = args.compiler.resolve()
    print(f"compiler_sha256={hashlib.sha256(compiler.read_bytes()).hexdigest()} seed={args.seed}", flush=True)
    cases = list(codec_cases(args.seed, args.random_count))
    cases += list(storage_codec_cases(args.seed, args.random_count))
    if not args.without_layout:
        cases += list(layout_cases())
    rejected = list(rejections()) + list(storage_rejections())
    with tempfile.TemporaryDirectory(prefix="aurora-byte-codec-") as temporary:
        runner = NativeRunner(Path(temporary), compiler, 5)
        # Small batches keep generated source and native output bounded. Cases with
        # declarations use an independent module to retain nominal identity.
        batch = []
        for case in cases:
            if case.prelude:
                if batch:
                    runner.cases(batch)
                    batch = []
                runner.cases([case])
            else:
                batch.append(case)
                if len(batch) == 24:
                    runner.cases(batch)
                    batch = []
        if batch:
            runner.cases(batch)
        for case in rejected:
            runner.rejection(case)
        root = Path(__file__).resolve().parents[2]
        example = root / "library/examples/storage_codec.au"
        assembly = Path(temporary) / "storage-codec-example.s"
        command([compiler, "--module-root", root / "library", example, "-o", assembly])
        observed, _ = runner.assemble(assembly.read_text(), ["main"])
        validate_values(observed, [Case("storage codec example", "", 42, result_type="i64")])
    print(
        f"PASS byte codec: {len(cases)} native cases, {len(rejected)} rejections; "
        f"storage_example=passed; packed_layout={'excluded (numeric gate only)' if args.without_layout else 'included'}"
    )


if __name__ == "__main__":
    main()
