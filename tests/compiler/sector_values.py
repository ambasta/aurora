#!/usr/bin/env python3
"""Focused sector-sized owned values: exact bytes, copy isolation and fail-closed bounds.

Results are complete 64-bit values and traps must reach the exact named bounds
UD2 (native_runner.py). Literal Python byte models do not use compiler layouts.
"""

from pathlib import Path
import argparse

from native_runner import require
from packed_values import Suite, Trap, byte_storage


BLOCK = byte_storage("Block", 512)
REPORT = """
enum class Status { success, out_of_range };
class Report {
    Status state;
    Block payload;
public:
    Report(Status status, Block block): state(status), payload(block) {}
    auto status() const -> Status { return state; }
    auto block_or_zero() const -> Block {
        if (state != Status::success) { const Block zero = Block(); return zero; }
        const Block copied = payload;
        return copied;
    }
};
"""
CARRIER = """
class Carrier {
    Report stored;
public:
    Carrier(Report report): stored(report) {}
    auto snapshot() const -> Report { const Report result = stored; return result; }
    auto take(Report report) const -> Report { return report; }
};
"""
IDENTITY = "auto identity(Report value) -> Report { return value; }"


def initialize(name="block"):
    return (
        f"Block {name}=Block();i64 initialize=0;while(initialize<512){{"
        f"{name}.set(initialize,u8((initialize*73+19)%256));initialize=initialize+1;}}"
    )


def check_bytes(name, values=None, index="check"):
    if values is None:
        values = [(index * 73 + 19) % 256 for index in range(512)]
    require(len(values) == 512, "sector oracle requires every byte")
    literal = ",".join(f"{value}u8" for value in values)
    return (
        f"const builtin::array<u8,512> expected_{index}={{{literal}}};i64 {index}=0;"
        f"while({index}<512){{if({name}.at({index})!=expected_{index}[{index}]){{return 0u64;}}"
        f"{index}={index}+1;}}"
    )


def positive_cases(suite):
    suite.check(
        "512-byte zero construction and exact size",
        "static_assert(size_of(Block)==512);"
        "const Block block=Block();" + check_bytes("block", [0] * 512) + "return 42u64;",
        definitions=BLOCK,
    )
    for capacity in (65, 255, 256, 511, 512):
        definitions = byte_storage("Buffer", capacity)
        suite.check(
            f"private byte array exact capacity {capacity}",
            f"static_assert(size_of(Buffer)=={capacity});Buffer value=Buffer();"
            f"value.set({capacity - 1},255u8);Buffer copy=value;value.set({capacity - 1},0u8);"
            f"return u64(copy.at({capacity - 1}));",
            expected=255,
            definitions=definitions,
        )
    split = (
        "class Split{builtin::array<u8,256> first;builtin::array<u8,256> second;public:"
        "Split():first{},second{}{}auto at(i64 i)const->u8{"
        "if(i<256){return first[i];}return second[i-256];}"
        "auto set(i64 i,u8 value)->u8{if(i<256){first[i]=value;return first[i];}"
        "second[i-256]=value;return second[i-256];}};"
    )
    suite.check(
        "two private arrays share the full 512-byte payload budget",
        "static_assert(size_of(Split)==512);Split value=Split();value.set(255,128u8);"
        "value.set(256,255u8);value.set(511,42u8);const Split copied=value;"
        "if(copied.at(255)!=128u8){return 0u64;}if(copied.at(256)!=255u8){return 0u64;}"
        "return u64(copied.at(511));",
        definitions=split,
    )
    suite.check(
        "all 512 copied bytes stay independent",
        initialize() + "Block copied=block;"
        "block.set(0,0u8);block.set(511,0u8);" + check_bytes("copied") + "return 42u64;",
        definitions=BLOCK,
    )
    suite.check(
        "method returns complete owned sector",
        initialize() + "Block copied=block.snapshot();block.set(511,0u8);" + check_bytes("copied") + "return 42u64;",
        definitions=BLOCK,
    )
    definitions = BLOCK + REPORT
    for status in ("success", "out_of_range"):
        values = None if status == "success" else [0] * 512
        suite.check(
            f"status and complete sector return {status}",
            "static_assert(size_of(Report)==520);"
            + initialize()
            + f"const Report report=Report(Status::{status},block);block.set(511,0u8);"
            "const Report result=identity(report);const Block copied=result.block_or_zero();"
            f"if(result.status()!=Status::{status}){{return 0u64;}}"
            + check_bytes("copied", values)
            + "return 18446744073709551615u64;",
            expected=(1 << 64) - 1,
            definitions=definitions,
            helpers=IDENTITY,
        )
    suite.check(
        "payload-first status report also occupies 520 bytes",
        initialize() + "static_assert(size_of(Report)==520);const Report report=Report(Status::success,block);"
        "const Report copied_report=identity(report);const Block copied=copied_report.block_or_zero();"
        + check_bytes("copied")
        + "return 42u64;",
        definitions=BLOCK + REPORT.replace("Status state;\n    Block payload;", "Block payload;\n    Status state;"),
        helpers=IDENTITY,
    )
    suite.check(
        "generic copied report retains sector-sized leaves",
        initialize() + "const Report report=Report(Status::success,block);const Report result=copy<Report>(report);"
        "const Block copied=result.block_or_zero();" + check_bytes("copied") + "return 42u64;",
        definitions=definitions,
        helpers="template<Value T>auto copy(T value)->T{return value;}",
    )
    suite.check(
        "nested copied report and combined method result",
        initialize() + "const Report report=Report(Status::success,block);Carrier carrier=Carrier(report);"
        "const Report nested=carrier.snapshot();const Report returned=carrier.take(nested);"
        "const Block copied=returned.block_or_zero();block.set(511,0u8);" + check_bytes("copied") + "return 42u64;",
        definitions=definitions + CARRIER,
    )
    helpers = (
        "auto six(Report a,Report b,Report c,Report d,Report e,Report f)->Report{"
        "const Block aa=a.block_or_zero();const Block bb=b.block_or_zero();"
        "const Block cc=c.block_or_zero();const Block dd=d.block_or_zero();"
        "const Block ee=e.block_or_zero();const Block ff=f.block_or_zero();i64 i=0;"
        "while(i<512){"
        + "".join(
            f"if({name}.at(i)!=u8((i*73+19)%256)){{const Report bad=Report(Status::out_of_range,aa);return bad;}}"
            for name in ("aa", "bb", "cc", "dd", "ee", "ff")
        )
        + "i=i+1;}return f;}"
    )
    suite.check(
        "six maximum reports retain every byte and full-width result",
        initialize() + "const Report report=Report(Status::success,block);"
        "const Report result=six(report,report,report,report,report,report);"
        "const Block copied=result.block_or_zero();" + check_bytes("copied") + "return 18446744073709551615u64;",
        expected=(1 << 64) - 1,
        definitions=definitions,
        helpers=helpers,
    )
    # Scalar expressions execute between independent report snapshots.
    helpers = (
        "auto snapshots(Block early,u8 changed,Block late)->u64{"
        "if(early.at(511)!=202u8){return 0u64;}if(changed!=255u8){return 0u64;}"
        "if(late.at(511)!=255u8){return 0u64;}return 42u64;}"
    )
    suite.check(
        "large argument snapshots preserve evaluation order",
        initialize() + "return snapshots(block,block.set(511,255u8),block);",
        definitions=BLOCK,
        helpers=helpers,
    )
    # The largest leaf count requires only one non-byte scalar alongside 512 bytes.
    scalar_fields = "".join(f"u8 b{index};" for index in range(512))
    assignments = ",".join(f".b{index}={index % 256}u8" for index in range(512))
    suite.check(
        "513 flattened leaves and 520 bytes are admitted",
        f"const Flat value=Flat{{{assignments},.word=18446744073709551615u64}};"
        "const Flat copy=flat_copy(value);return copy.word;",
        expected=(1 << 64) - 1,
        definitions=f"class Flat{{public:{scalar_fields}u64 word;}};",
        helpers="auto flat_copy(Flat value)->Flat{return value;}",
    )


def rejection_cases(suite):
    for capacity in (0, 513, 4096):
        suite.reject(
            f"private u8 array length {capacity} is outside 1..512", "return 42u64;", byte_storage("Bad", capacity)
        )
    for kind in ("i64", "u64", "bool"):
        suite.reject(
            f"private {kind} array capacity 65 stays rejected",
            "return 42u64;",
            f"class Bad{{builtin::array<{kind},65> data;public:Bad():data{{}}{{}}}};",
        )
    suite.reject(
        "byte templates retain capacity 64",
        "return 42u64;",
        "template<Scalar T,i64 N>class Buffer{builtin::array<T,N> data;"
        "public:Buffer():data{}{} };class Bad{Buffer<u8,512> value;public:"
        "Bad(Buffer<u8,512> input):value(input){} };",
    )
    for kind in ("i64", "u64", "bool"):
        fields = "".join(f"{kind} f{index};" for index in range(65))
        suite.reject(
            f"65 {kind} boundary leaves stay rejected",
            "return 42u64;",
            f"class Wide{{public:{fields}}};",
            "auto copy(Wide value)->Wide{return value;}",
        )
    fields = "".join(f"u8 f{index};" for index in range(513))
    suite.reject(
        "513 bytes cannot bypass array cap as scalar fields",
        "return 42u64;",
        f"class Wide{{public:{fields}}};",
        "auto copy(Wide value)->Wide{return value;}",
    )
    suite.reject(
        "split private arrays cannot exceed the byte-leaf budget",
        "return 42u64;",
        "class Wide{builtin::array<u8,256> a;builtin::array<u8,257> b;public:Wide():a{},b{}{} };",
        "auto copy(Wide value)->Wide{return value;}",
    )
    suite.reject(
        "514 total leaves reject a sector plus two status words",
        "return 42u64;",
        BLOCK + "class Wide{Block block;u64 a;u64 b;public:Wide(Block p):block(p),a(0u64),b(0u64){} };",
    )
    # 508 u8 leaves + one u64 leaf fit every leaf cap but canonical padding needs 528 bytes.
    padding = (
        "class Padded{u8 head;u64 word;builtin::array<u8,507> bytes;public:Padded():head(0u8),word(0u64),bytes{}{} };"
    )
    suite.reject(
        "canonical padding cannot bypass 520-byte copy budget",
        "return 42u64;",
        padding,
        "auto copy(Padded value)->Padded{return value;}",
    )
    suite.reject(
        "nested storage also checks padding budget",
        "return 42u64;",
        padding + "class Envelope{Padded payload;public:Envelope(Padded input):payload(input){} };",
    )
    for body in (
        "return u64(block.data[511]);",
        "block.set(511,255u64);return 42u64;",
        "const Block readonly=block;readonly.set(511,0u8);return 42u64;",
        "return u64(block.at(511u64));",
    ):
        suite.reject("large class privacy and exact typing", "Block block=Block();" + body, BLOCK)
    suite.reject(
        "constructor must zero complete sector", "return 42u64;", BLOCK.replace("Block():data{}{}", "Block(){}")
    )
    suite.reject(
        "sector source-frame overflow remains rejected",
        "".join(f"Block block{index}=Block();" for index in range(129)) + "return 42u64;",
        BLOCK,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("compiler", type=Path)
    parser.add_argument("--work-dir", type=Path)
    args = parser.parse_args()
    suite = Suite(args.compiler, 15, "sector values")
    if args.work_dir:
        suite.runner.directory = args.work_dir.resolve()
    positive_cases(suite)
    rejection_cases(suite)
    for offset in (-1, 512, (1 << 63) - 1):
        for write in (False, True):
            body = (
                f"Block block=Block();return u64(block.set({offset},255u8));"
                if write
                else f"const Block block=Block();return u64(block.at({offset}));"
            )
            suite.check(
                f"sector {'write' if write else 'read'} bounds {offset}",
                body,
                expected=Trap.BOUNDS,
                definitions=BLOCK,
            )
    suite.finish()


if __name__ == "__main__":
    main()
