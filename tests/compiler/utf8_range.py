#!/usr/bin/env python3
"""Bounded native UTF-8 scalar-range gate using Python strict-decoding oracle.

No target FFI is introduced: Linux assembly is only the existing host test seam.
Every native status/offset/count is returned as a complete signed 64-bit value.
Failed source, tool outputs, receipts, and binary observations are retained.
"""

from __future__ import annotations
import argparse, hashlib, itertools, json, os, pathlib, random, resource, shutil, stat, subprocess, sys, time

sys.dont_write_bytecode = True
MIN = -(1 << 63)
MAX = (1 << 63) - 1
STATUSES = ("success", "out_of_range", "invalid_sequence", "truncated")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts"))
from compiler_contract import add_identity_arguments, resolve_identity, validate_identity_selection

CAP = 128 << 20
FLOOR = 1 << 30
RESERVE = 24 << 20


def require(value, message):
    if not value:
        raise AssertionError(message)


def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def model(data, offset, count, first, length):
    # The oracle uses CPython's strict whole-string decoder and string slicing,
    # not the library's byte scan or its existing decoder test implementation.
    if first < 0 or length < 0 or offset < 0 or count < 0 or offset > len(data) or count > len(data) - offset:
        return (1, 0, 0)
    try:
        text = bytes(data[offset : offset + count]).decode("utf-8", "strict")
    except UnicodeDecodeError as error:
        return (3 if error.reason == "unexpected end of data" else 2, 0, 0)
    if first > len(text) or length > len(text) - first:
        return (1, 0, 0)
    return (0, len(text[:first].encode("utf-8")), len(text[first : first + length].encode("utf-8")))


def cases():
    scalars = (
        0,
        0x7F,
        0x80,
        0x7FF,
        0x800,
        0xD7FF,
        0xE000,
        0xFFFF,
        0x10000,
        0x10FFFF,
        0xFEFF,
        0xFDD0,
        0x0378,
        0x0301,
        0x200D,
        0x1F642,
    )
    mixed = "".join(map(chr, scalars)).encode("utf-8")
    for first in range(len(scalars) + 2):
        for length in range(len(scalars) + 2):
            yield ("mixed scalar interval", b"\xff" + mixed + b"\xff", 1, len(mixed), first, length)
    for value in range(256):
        for first, length in ((0, 0), (0, 1), (1, 0)):
            yield ("every single byte", bytes((value,)), 0, 1, first, length)
    # Every byte window of a representative mixed-width sequence. These include
    # starts in continuation bytes and viable versus impossible truncated tails.
    window = b"A\xc2\xa2\xe2\x82\xac\xf0\x9f\x99\x82Z"
    for offset in range(len(window) + 1):
        for count in range(len(window) - offset + 1):
            for first, length in ((0, 0), (0, 1), (1, 1), (2, 0)):
                yield ("all mixed byte windows", window, offset, count, first, length)
    malformed = (
        b"\x80",
        b"\xbf",
        b"\xc0\x80",
        b"\xc1\xbf",
        b"\xc2",
        b"\xc2A",
        b"\xe0",
        b"\xe0\x9f",
        b"\xe0\xa0",
        b"\xed\xa0",
        b"\xed\xa0\x80",
        b"\xed\xbf\xbf",
        b"\xe1\x80A",
        b"\xf0",
        b"\xf0\x8f",
        b"\xf0\x90",
        b"\xf1\x80\x80",
        b"\xf4\x8f\xbf",
        b"\xf4\x90",
        b"\xf4\x90\x80\x80",
        b"\xf5",
        b"\xff",
        b"\xe1\x80\xff",
        b"\xf1\x80A",
    )
    for bad in malformed:
        for prefix in (b"", b"A", b"\xc2\xa2Z"):
            for first, length in ((0, 0), (0, 1), (1, 0), (MAX, MAX)):
                data = prefix + bad
                yield ("invalid whole window suppresses early match", data, 0, len(data), first, length)
    base = (b"A\xc2\xa2Z", 0, 4, 1, 1)
    for dimension in range(1, 5):
        for extreme in (MIN, -1, 0, 1, 2, 3, 4, 5, MAX):
            args = list(base)
            args[dimension] = extreme
            yield ("signed edge dimension", *args)
    for offset, count, first, length in itertools.product((MIN, MAX), repeat=4):
        yield ("combined signed extremes", b"\xff", offset, count, first, length)
    for first, length in ((-1, 0), (0, -1), (MAX, 0), (0, MAX)):
        yield ("range versus malformed precedence", b"\xff", 0, 1, first, length)
    for value in scalars:
        raw = chr(value).encode("utf-8")
        for first, length in ((0, 0), (0, 1), (1, 0), (1, 1)):
            yield ("scalar boundary value", b"\xff" + raw + b"\xff", 1, len(raw), first, length)
    rng = random.Random(20261004)
    for _ in range(160):
        values = [rng.choice(scalars) for _ in range(rng.randrange(17))]
        raw = "".join(map(chr, values)).encode("utf-8")
        yield ("seeded valid mixed scalars", b"\xff" + raw + b"\xff", 1, len(raw), rng.randrange(20), rng.randrange(20))
    for _ in range(128):
        raw = bytes(rng.randrange(256) for _ in range(rng.randrange(9)))
        yield ("seeded arbitrary bytes", raw or b"\xff", 0, len(raw), rng.randrange(4), rng.randrange(4))
    for first, length in ((0, 0), (0, 4093), (4092, 1), (4093, 0), (4093, 1), (MAX, MAX)):
        yield ("maximum 4096-byte owner", b"A" * 4092 + chr(0x10FFFF).encode(), 0, 4096, first, length)


def array(data):
    data = data or b"\xff"
    return "builtin::array<u8," + str(len(data)) + "> owner={" + ",".join(str(x) + "u8" for x in data) + "};"


def observe(report="report"):
    body = "if(field==0){"
    for number, status in enumerate(STATUSES):
        body += f"if({report}.status()==std::Utf8RangeStatus::{status}){{return {number};}}"
    return body + f"return -777;}}if(field==1){{return {report}.byte_offset();}}return {report}.byte_count();"


def source_case(item):
    label, data, offset, count, first, length = item
    body = array(data) + "const builtin::array<u8," + str(max(1, len(data))) + "> saved=owner;"
    body += (
        f"const std::Utf8RangeResult report=std::utf8_subrange(borrow_bytes(owner),{offset},{count},{first},{length});"
    )
    body += "i64 check=0;while(check<len(owner)){if(owner[check]!=saved[check]){return -778;}check=check+1;}"
    # Mutation is after the call-bounded borrow; saved reports remain copied data.
    body += "owner[0]=0u8;const std::Utf8RangeResult copy=report;" + observe("copy")
    return label, body, model(data, offset, count, first, length)


def report_cases():
    for status in STATUSES:
        for offset, count in itertools.product((MIN, -1, 0, 1, 4, MAX), repeat=2):
            expected_status = STATUSES.index(status)
            if expected_status == 0 and (offset < 0 or count < 0 or count > MAX - offset):
                expected_status = 1
            expect = (expected_status, offset if expected_status == 0 else 0, count if expected_status == 0 else 0)
            body = (
                f"const std::Utf8RangeResult original="
                f"std::Utf8RangeResult(std::Utf8RangeStatus::{status},{offset},{count});"
            )
            body += "const std::Utf8RangeResult report=original;" + observe()
            yield ("public copied report masks failure or nonrepresentable coordinates", body, expect)


def reject_cases():
    head = "module rejection;import std.utf8_range;"
    yield (
        "private field",
        head
        + (
            "auto test()->i64{const std::Utf8RangeResult r=std::Utf8RangeResult(std::Utf8RangeStatus::s"
            "uccess,0,0);return r.relative_offset;}"
        ),
        "private",
    )
    yield (
        "private count",
        head
        + (
            "auto test()->i64{const std::Utf8RangeResult r=std::Utf8RangeResult(std::Utf8RangeStatus::s"
            "uccess,0,0);return r.byte_length;}"
        ),
        "private",
    )
    yield (
        "mutation while readonly borrow live",
        head
        + (
            "auto test()->i64{builtin::array<u8,1> b={65u8};"
            "const builtin::span<const u8> v=borrow_bytes(b);b[0]=66u8;"
            "const std::Utf8RangeResult r=std::utf8_subrange(v,0,1,0,1);return r.byte_count();}"
        ),
        "span is live",
    )
    yield (
        "retained view in class",
        head + "class Bad{builtin::span<const u8> view;};auto test()->i64{return 0;}",
        "class fields require",
    )
    yield (
        "wrong scalar index type",
        head
        + (
            "auto test()->i64{const builtin::array<u8,1> b={65u8};"
            "const std::Utf8RangeResult r=std::utf8_subrange(borrow_bytes(b),0,1,0u64,1);"
            "return r.byte_count();}"
        ),
        "expected i64, got u64",
    )
    yield (
        "unimported decoder module does not reexport dependency",
        head
        + (
            "auto test()->i64{const builtin::array<u8,1> b={65u8};"
            "const std::Utf8ValidationResult r=std::validate_utf8(borrow_bytes(b),0,1,true);"
            "return r.scalar_count();}"
        ),
        "unknown function 'std::validate_utf8'",
    )


def allocated_bytes(root):
    """Count every directory entry without following child directory symlinks."""
    used = root.stat().st_blocks * 512
    directories = [str(root)]
    while directories:
        # Close each iterator before descent, including for very deep trees.
        # Fail closed on enumeration errors instead of silently undercounting.
        with os.scandir(directories.pop()) as entries:
            children = list(entries)
        for entry in children:
            info = entry.stat(follow_symlinks=False)
            used += info.st_blocks * 512
            if stat.S_ISDIR(info.st_mode):
                directories.append(entry.path)
    return used


class Suite:
    def __init__(self, args, identity):
        self.args = args
        self.identity = identity
        self.root = args.repo_root.resolve(strict=True)
        self.output = args.artifacts.absolute()
        self.budget_root = (args.budget_root or self.output).absolute()
        identity.verify()
        require(identity.sha256 == sha(args.compiler), "compiler identity mismatch before artifact creation")
        require(not self.output.exists(), "artifact directory must be fresh")
        require(self.output.parent.is_dir(), "artifact parent must exist")
        require(not any(p.is_symlink() for p in (self.output, *self.output.parents)), "symlink artifact root")
        self.output.mkdir()
        self.compiler = args.compiler.resolve(strict=True)
        self.pin = identity.sha256
        self.count = self.batches = self.rejections = 0
        self.inputs = {str(p.relative_to(self.root)): sha(p) for p in (self.root / "library").rglob("*.au")}
        self.inputs[str(pathlib.Path(__file__).resolve())] = sha(__file__)
        self.budget()

    def budget(self, reserve=RESERVE):
        require(self.budget_root.is_dir(), "budget root must be a directory")
        used = allocated_bytes(self.budget_root)
        require(used + reserve <= self.args.budget_mib << 20, f"owned output budget exceeded: {used} + {reserve}")
        require(shutil.disk_usage(self.budget_root).free - reserve > FLOOR, "global free-space floor")
        return used

    def command(self, argv, directory, name, expected=0):
        self.budget()
        compiler = pathlib.Path(argv[0]) == self.compiler
        as_limit = None if compiler and self.args.sanitized_compiler else (512 if compiler else 128) << 20

        def limit():
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
            resource.setrlimit(resource.RLIMIT_CPU, (20, 21))
            resource.setrlimit(resource.RLIMIT_FSIZE, (8 << 20, 8 << 20))
            if as_limit is not None:
                resource.setrlimit(resource.RLIMIT_AS, (as_limit, as_limit))

        receipt = dict(
            command=list(map(str, argv)),
            address_space_bytes=as_limit,
            cpu_seconds=[20, 21],
            file_bytes=8 << 20,
            wall_seconds=45,
            status="running",
        )
        before = resource.getrusage(resource.RUSAGE_CHILDREN)
        start = time.monotonic()
        try:
            with (directory / (name + ".stdout")).open("wb") as out, (directory / (name + ".stderr")).open("wb") as err:
                result = subprocess.run(list(map(str, argv)), stdout=out, stderr=err, timeout=45, preexec_fn=limit)
            receipt["returncode"] = result.returncode
            require(
                result.returncode == expected,
                f"{name} exit {result.returncode}; expected {expected}: "
                f"{(directory / (name + '.stderr')).read_text()[:3000]}",
            )
            if expected == 0:
                require((directory / (name + ".stderr")).stat().st_size == 0, name + " unexpected stderr")
            receipt["status"] = "passed"
            return (directory / (name + ".stdout")).read_bytes()
        except Exception as error:
            receipt.update(status="failed", error=str(error))
            raise
        finally:
            receipt["seconds"] = time.monotonic() - start
            after = resource.getrusage(resource.RUSAGE_CHILDREN)
            receipt["child_user_seconds"] = after.ru_utime - before.ru_utime
            receipt["child_system_seconds"] = after.ru_stime - before.ru_stime
            receipt["child_cpu_seconds"] = receipt["child_user_seconds"] + receipt["child_system_seconds"]
            (directory / (name + ".json")).write_text(json.dumps(receipt, indent=2) + "\n")
            self.budget(0)

    def batch(self, items):
        self.budget()
        d = self.output / f"batch-{self.batches:04d}"
        d.mkdir()
        self.batches += 1
        source = "module utf8_range_test;import std.utf8_range;\n"
        for i, (_, body, _) in enumerate(items):
            source += f"auto range_case_{i}(i64 field)->i64{{{body}}}\n"
        require(len(source.encode()) <= 65536, "source-size cap")
        (d / "input.au").write_text(source)
        wanted = [v for _, _, values in items for v in values]
        receipt = dict(
            labels=[x[0] for x in items], expected=wanted, source_sha256=sha(d / "input.au"), status="running"
        )
        try:
            self.command(
                [self.compiler, "--module-root", self.root / "library", d / "input.au", "-o", d / "compiled.s"],
                d,
                "compiler",
            )
            entry = [".text", ".globl _start", "_start:"]
            for i in range(len(items)):
                for field in range(3):
                    entry += [
                        f"movq ${field},%rdi",
                        f"call range_case_{i}",
                        "pushq %rax",
                        "movq $1,%rax",
                        "movq $1,%rdi",
                        "movq %rsp,%rsi",
                        "movq $8,%rdx",
                        "syscall",
                        "addq $8,%rsp",
                    ]
            entry += ["movq $60,%rax", "xorq %rdi,%rdi", "syscall", '.section .note.GNU-stack,"",@progbits']
            (d / "entry.s").write_text("\n".join(entry) + "\n")
            self.command(["as", "--64", d / "compiled.s", "-o", d / "program.o"], d, "assemble")
            self.command(["as", "--64", d / "entry.s", "-o", d / "entry.o"], d, "entry")
            self.command(["ld", "-o", d / "program", d / "entry.o", d / "program.o"], d, "link")
            output = self.command([d / "program"], d, "native")
            require(len(output) == 8 * len(wanted), "exact native output size")
            observed = [int.from_bytes(output[i : i + 8], "little", signed=True) for i in range(0, len(output), 8)]
            receipt.update(observed=observed, output_sha256=hashlib.sha256(output).hexdigest())
            require(
                observed == wanted,
                f"native observation mismatch: "
                f"{[(i, a, b) for i, (a, b) in enumerate(zip(observed, wanted)) if a != b][:8]}",
            )
            receipt["status"] = "passed"
            self.count += len(items)
        except Exception as error:
            receipt.update(status="failed", error=str(error))
            raise
        finally:
            (d / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
        print(f"PASS range batch {self.batches}: {len(items)} cases, {len(wanted)} full observations", flush=True)

    def reject(self, label, source, diagnostic):
        d = self.output / f"reject-{self.rejections:02d}"
        d.mkdir()
        (d / "input.au").write_text(source)
        target = d / "preserved.s"
        marker = b"preexisting output must survive\n"
        target.write_bytes(marker)
        self.command(
            [self.compiler, "--module-root", self.root / "library", d / "input.au", "-o", target], d, "compiler", 1
        )
        error = (d / "compiler.stderr").read_text().lower()
        require(diagnostic in error, f"{label}: expected diagnostic {diagnostic!r}; actual {error!r}")
        require(target.read_bytes() == marker, "rejection modified preexisting output")
        (d / "receipt.json").write_text(
            json.dumps(dict(label=label, diagnostic=error, status="passed"), indent=2) + "\n"
        )
        self.rejections += 1

    def verify_inputs(self):
        require(sha(self.compiler) == self.pin, "compiler changed")
        for name, digest in self.inputs.items():
            require(sha(self.root / name) == digest, "input changed: " + name)


def self_test():
    require(model(b"A\xc2\xa2Z", 0, 4, 1, 1) == (0, 1, 2), "oracle mixed")
    require(model(b"A\xff", 0, 2, 0, 1) == (2, 0, 0), "oracle full validation")
    require(model(b"A\xc2", 0, 2, 0, 0) == (3, 0, 0), "oracle truncation")
    require(model(b"\xff", 0, 1, -1, 0) == (1, 0, 0), "negative precedence")
    require(model(b"\xff", 0, 1, MAX, MAX) == (2, 0, 0), "nonnegative selection after validation")
    require(model(b"A", 1, 0, 0, 0) == (0, 0, 0), "empty window")
    require(model(b"A", 0, 1, 1, 0) == (0, 1, 0), "empty at end")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--compiler", type=pathlib.Path)
    add_identity_arguments(p)
    p.add_argument("--repo-root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2])
    p.add_argument("--artifacts", type=pathlib.Path)
    p.add_argument("--budget-root", type=pathlib.Path)
    p.add_argument("--budget-mib", type=int, default=128)
    p.add_argument("--sanitized-compiler", action="store_true")
    p.add_argument("--self-test-only", action="store_true")
    a = p.parse_args()
    validate_identity_selection(a, preflight=a.self_test_only)
    if not a.self_test_only:
        require(a.compiler is not None and a.artifacts is not None, "compiler and fresh artifacts required")
        identity = resolve_identity(a, a.compiler, a.repo_root)
    self_test()
    if a.self_test_only:
        print("PASS range oracle controls")
        return
    require(a.compiler is not None and a.artifacts is not None, "compiler and fresh artifacts required")
    suite = Suite(a, identity)
    manifest = dict(
        compiler_identity=identity.record(),
        compiler_sha256=suite.pin,
        inputs=suite.inputs,
        python=sys.version,
        optimized=not __debug__,
        status="running",
    )
    try:
        batch = []
        for item in itertools.chain(map(source_case, cases()), report_cases()):
            if batch and (len(batch) >= 16 or sum(len(x[1]) for x in batch) + len(item[1]) > 62000):
                suite.batch(batch)
                batch = []
            batch.append(item)
        if batch:
            suite.batch(batch)
        for item in reject_cases():
            suite.reject(*item)
        suite.verify_inputs()
        identity.verify()
        manifest.update(
            status="passed",
            cases=suite.count,
            full_i64_observations=3 * suite.count,
            batches=suite.batches,
            rejections=suite.rejections,
        )
        print(
            f"PASS UTF-8 scalar ranges: {suite.count} cases; "
            f"{3 * suite.count} full observations; {suite.rejections} rejection controls",
            flush=True,
        )
    except Exception as error:
        manifest.update(status="failed", error=str(error))
        raise
    finally:
        manifest.update(
            completed_cases=suite.count, completed_rejections=suite.rejections, allocated_bytes=suite.budget(0)
        )
        (suite.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
