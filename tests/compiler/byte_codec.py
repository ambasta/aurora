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

from unsigned_oracle import Case, NativeRunner, Rejection, require


def codec_cases(seed, count):
    rng = random.Random(seed)
    values = [0, 1, 42, 127, 128, 255, 256, 65535, 65536, 0x12345678,
              0x80000000, 0xFFFFFFFF, 1 << 32, (1 << 64) - 1]
    values += [rng.randrange(1 << 32) for _ in range(count)]
    for value in values:
        for endian, opposite in (("le", "be"), ("be", "le")):
            valid = value < (1 << 32)
            expected = value if valid else 0
            body = (f"const std::Encode32Result report=std::encode_{endian}32({value}u64);"
                    f"if(report.status()!=std::ByteCodecStatus::{'success' if valid else 'out_of_range'})"
                    "{return 18446744073709551615u64;}"
                    "const std::Bytes4 bytes=report.bytes_or_zero();"
                    f"return std::decode_{endian}32(bytes);")
            yield Case(f"{endian} roundtrip {value}", body, expected, imports=("std.bytes",))
            if valid:
                ordered = value.to_bytes(4, "little" if endian == "le" else "big")
                opposite_value = int.from_bytes(ordered, "big" if endian == "le" else "little")
                yield Case(f"{endian} cross decode {value}",
                           f"const std::Encode32Result report=std::encode_{endian}32({value}u64);"
                           "const std::Bytes4 bytes=report.bytes_or_zero();"
                           f"return std::decode_{opposite}32(bytes);", opposite_value,
                           imports=("std.bytes",))
                for index, byte in enumerate(ordered):
                    yield Case(f"{endian} byte {index} of {value}",
                               f"const std::Encode32Result report=std::encode_{endian}32({value}u64);"
                               "const std::Bytes4 bytes=report.bytes_or_zero();"
                               f"return u64(bytes.at({index}));", byte, imports=("std.bytes",))
    yield Case("failure masks a deliberately nonzero public report", """
        std::Bytes4 source=std::Bytes4(); source.set(0,255u8);source.set(3,255u8);
        const std::Encode32Result report=std::Encode32Result(std::ByteCodecStatus::out_of_range,source);
        const std::Bytes4 copy=report.bytes_or_zero();return std::decode_le32(copy);
    """, 0, imports=("std.bytes",))
    yield Case("success report and output copies are independent", """
        std::Bytes4 source=std::Bytes4();source.set(0,42u8);
        const std::Encode32Result report=std::Encode32Result(std::ByteCodecStatus::success,source);
        source.set(0,1u8);std::Bytes4 copy=report.bytes_or_zero();copy.set(0,9u8);
        const std::Bytes4 original=report.bytes_or_zero();return std::decode_le32(original);
    """, 42, imports=("std.bytes",))
    yield Case("all byte values remain valid data", """
        std::Bytes4 source=std::Bytes4();source.set(0,255u8);source.set(1,255u8);
        source.set(2,255u8);source.set(3,255u8);return std::decode_be32(source);
    """, 0xFFFFFFFF, imports=("std.bytes",))


def layout_cases():
    for capacity in (1, 3, 4, 7, 8, 9, 64):
        yield Case(f"compact wrapper capacity {capacity}", f"""
            static_assert(size_of(builtin::array<u8,{capacity}>)=={capacity});
            static_assert(size_of(std::array<u8,{capacity}>)=={capacity});
            std::array<u8,{capacity}> bytes=std::array<u8,{capacity}>();
            bytes.set({capacity-1},255u8);
            const std::array<u8,{capacity}> copy=bytes;
            bytes.set({capacity-1},0u8);
            if(reflect_size(type_id(std::array<u8,{capacity}>))!={capacity}){{return 0u64;}}
            return u64(copy.at({capacity-1}));
        """, 255, imports=("std.array",))
    yield Case("codec representation and nominal metadata", """
        static_assert(size_of(std::Bytes4)==4);
        static_assert(size_of(std::Encode32Result)==16);
        static_assert(field_count(std::Bytes4)==0);
        if(reflect_size(type_id(std::Bytes4))!=4){return 0u64;}
        return 42u64;
    """, 42, imports=("std.bytes",))
    definitions = """
        class Empty{public:Empty(){}};
        class Small{public:u8 first;u8 second;};
        class Mixed{public:u8 first;u64 wide;bool flag;u8 last;};
        class Nested{public:u8 first;Small small;Empty empty;u64 last;
            Nested(u8 f,Small s,Empty e,u64 l):first(f),small(s),empty(e),last(l){}
        };
        auto identity(Nested n)->Nested{return n;}
    """
    yield Case("natural mixed widths nested empty and copied results", """
        static_assert(size_of(Small)==2);static_assert(size_of(Mixed)==32);
        static_assert(size_of(Nested)==16);static_assert(size_of(Empty)==8);
        const Small small=Small{.first=200u8,.second=255u8};const Empty empty=Empty();
        const Nested original=Nested(1u8,small,empty,42u64);
        const Nested copy=identity(original);Small projected=copy.small;
        projected.second=0u8;const Small preserved=original.small;
        if(preserved.second!=255u8){return 0u64;}return copy.last;
    """,42,prelude=definitions)


def rejections():
    bodies = [
        "return result.payload;", "return result.value();",
        "std::Bytes4 bytes=result.bytes_or_zero();return bytes.elements[0];",
        "const std::Bytes4 bytes=result.bytes_or_zero();bytes.set(0,1u8);return 0u64;",
        "return std::encode_le32(42);",
        "std::Bytes4 bytes=std::Bytes4();bytes.set(0,256u64);return 0u64;",
        "const std::Bytes4 bytes=std::Bytes4{.elements={0u8,0u8,0u8,0u8}};return 0u64;",
    ]
    for index, body in enumerate(bodies):
        yield Rejection(f"codec visibility/type rejection {index}",
                        "module test;import std.bytes;auto test()->u64{"
                        "const std::Encode32Result result=std::encode_le32(42u64);"+body+"}")


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("compiler",type=Path)
    parser.add_argument("--seed",type=int,default=13013)
    parser.add_argument("--random-count",type=int,default=16)
    parser.add_argument("--without-layout",action="store_true")
    args=parser.parse_args()
    require(0<=args.random_count<=256,"random-count must be 0..256")
    compiler=args.compiler.resolve()
    print(f"compiler_sha256={hashlib.sha256(compiler.read_bytes()).hexdigest()} seed={args.seed}",flush=True)
    cases=list(codec_cases(args.seed,args.random_count))
    if not args.without_layout:cases+=list(layout_cases())
    rejected=list(rejections())
    with tempfile.TemporaryDirectory(prefix="aurora-byte-codec-") as temporary:
        runner=NativeRunner(Path(temporary),compiler,5)
        # Small batches keep generated source and native output bounded. Cases with
        # declarations use an independent module to retain nominal identity.
        batch=[]
        for case in cases:
            if case.prelude:
                if batch:runner.cases(batch);batch=[]
                runner.cases([case])
            else:
                batch.append(case)
                if len(batch)==24:runner.cases(batch);batch=[]
        if batch:runner.cases(batch)
        for case in rejected:runner.rejection(case)
    print(f"PASS byte codec: {len(cases)} native cases, {len(rejected)} rejections; "
          f"packed_layout={'excluded (numeric gate only)' if args.without_layout else 'included'}")


if __name__=="__main__":main()
