"""Hosted-bytes library tests: one compiled, linked driver; every run is a data row.

Resource entries `entry(builtin::ByteRegion region, i64 n, i64 flag) -> i64`
take only scalars and moved owners, so a case's fixed source program becomes a
private namespace of one packed module, compiled once and linked once with
runtime/hosted_bytes.cpp and hosted_records_host.cpp. Runs are rows of
(program, quota, n, flag, allocation-failure point) streamed through one process;
each row gets a fresh Region and a tracing allocator, and must leave the region
closable. A standalone module (a shipped example) is its own one-compile pack.

Expected results, allocation counts, release orders and attempted sizes are
supplied by the caller from standard-library references or reviewed tables.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import os
from pathlib import Path
import re
import shlex
import struct

import runtime_records as records
from native_runner import resolve_entry, split_program

require = records.require
ROOT = records.ROOT
MASK = (1 << 64) - 1
HOST = Path(__file__).with_name("hosted_records_host.cpp")
RUNTIME = ROOT / "runtime/hosted_bytes.cpp"
FLAGS = ("-std=c++23", "-O1", "-Wall", "-Wextra", "-Wpedantic", "-Werror")
LABEL = re.compile(r"^([A-Za-z_][A-Za-z_0-9]*):", re.M)
PACKED = "hosted_pack"


@dataclass
class Row:
    label: str
    program: int
    quota: int
    n: int
    flag: int
    expected: int
    allocations: int
    peak: int
    fail_after: int = -1
    once: bool = False
    release_order: list | None = None
    attempted_sizes: list | None = None


class Pack:
    def __init__(self, standalone=None, entry="entry"):
        self.standalone = standalone
        self.entry = entry
        self.names, self.declarations, self.imports = [], [], []
        self.rows, self.aborts = [], []

    def program(self, name, source):
        """Add one `module ...; import ...; declarations` program; returns its index."""
        require(self.standalone is None, "standalone pack holds one module")
        module, imports, declarations = split_program(source)
        self.imports += [item for item in imports if item not in self.imports]
        self.names.append(name)
        self.declarations.append(declarations)
        return len(self.names) - 1

    def source(self):
        if self.standalone is not None:
            return self.standalone
        header = f"module {PACKED};\n" + "".join(f"import {item};\n" for item in self.imports)
        return header + "".join(f"namespace c{i} {{\n{body}\n}}\n" for i, body in enumerate(self.declarations))

    def run(self, program, quota, n, flag, expected, allocations, peak, fail_after=None, **options):
        """One row; fail_after is None, an int, or "once:N" (fail allocation N+1 once, then allow retries)."""
        once = isinstance(fail_after, str)
        if once:
            require(fail_after.startswith("once:"), "once:N failure point")
            fail_after = int(fail_after[5:])
        label = f"{self.names[program] if self.names else 'example'} {[quota, n, flag, fail_after]}"
        self.rows.append(
            Row(
                label,
                program,
                quota,
                n,
                flag,
                expected,
                allocations,
                peak,
                -1 if fail_after is None else fail_after,
                once,
                **options,
            )
        )

    def abort(self, program, quota, n, flag, stderr):
        """A run that must end in the hosted adapter's abort with exactly `stderr`."""
        self.aborts.append((program, quota, n, flag, stderr))


class Hosted:
    def __init__(self, compiler, scratch):
        self.driver = records.Driver(compiler, scratch)
        self.scratch = Path(scratch)
        self.cxx = shlex.split(os.environ.get("CXX", "g++"))
        self.objects = None
        self.packs = []
        self.rows = self.aborted = 0

    def pack(self, standalone=None, entry="entry"):
        self.packs.append(Pack(standalone, entry))
        return self.packs[-1]

    def host_objects(self):
        if self.objects is None and os.environ.get("AURORA_HOSTED_RECORDS_HOST"):
            self.objects = [Path(os.environ["AURORA_HOSTED_RECORDS_HOST"])]
        if self.objects is None:
            self.objects = []
            for source in (HOST, RUNTIME):
                output = self.scratch / (source.stem + ".o")
                records.checked([*self.cxx, *FLAGS, "-I", ROOT, "-c", source, "-o", output], f"{source.name} host")
                self.objects.append(output)
        return self.objects

    def build(self, pack, number):
        directory = self.driver.compile(pack.source(), f"pack-{number}")
        text = (directory / "compiled.s").read_text()
        notes = [line.strip() for line in text.splitlines() if ".note.GNU-stack" in line]
        require(notes == ['.section .note.GNU-stack,"",@progbits'], "one non-executable-stack note")
        labels = set(LABEL.findall(text))
        if pack.standalone is None:
            entries = [resolve_entry(labels, PACKED, f"c{i}", pack.entry) for i in range(len(pack.names))]
        else:
            module, _, _ = split_program(pack.standalone)
            entries = [resolve_entry(labels, module, "", pack.entry)]
        for entry in entries:
            require(f".local {entry}\n" in text, f"resource entry {entry} must stay private")
        # The resource convention: region, n and flag in a block addressed by r11.
        bridge = [
            ".text",
            ".globl aurora_hosted_entry",
            ".type aurora_hosted_entry, @function",
            "aurora_hosted_entry:",
            "pushq %rbp",
            "movq %rsp,%rbp",
            "subq $32,%rsp",
            "movq %rdi,(%rsp)",
            "movq %rsi,8(%rsp)",
            "movq %rdx,16(%rsp)",
            "movq $0,24(%rsp)",
            "movq aurora_hosted_program(%rip),%rax",
            "leaq .Laurora_hosted_table(%rip),%rcx",
            "movq (%rcx,%rax,8),%rax",
            "movq %rsp,%r11",
            "call *%rax",
            "leave",
            "ret",
            ".size aurora_hosted_entry, .-aurora_hosted_entry",
            ".data",
            ".balign 8",
            ".globl aurora_hosted_program",
            "aurora_hosted_program:",
            ".quad 0",
            '.section .data.rel.ro,"aw"',
            ".balign 8",
            ".globl aurora_hosted_programs",
            "aurora_hosted_programs:",
            f".quad {len(entries)}",
            ".Laurora_hosted_table:",
            *(f".quad {entry}" for entry in entries),
            ".text",
        ]
        with (directory / "compiled.s").open("a") as stream:
            stream.write("\n" + "\n".join(bridge) + "\n")
        records.checked(["as", "--64", directory / "compiled.s", "-o", directory / "program.o"], "assembler")
        imported = records.checked(["nm", "-u", directory / "program.o"], "nm").decode().split()
        require(
            all(symbol == "U" or symbol.startswith("__au_runtime_") for symbol in imported),
            f"driver imports outside the hosted byte runtime: {imported}",
        )
        binary = directory / "program"
        records.checked([*self.cxx, *FLAGS, directory / "program.o", *self.host_objects(), "-o", binary], "link")
        return directory, binary

    def finish(self):
        for number, pack in enumerate(self.packs):
            directory, binary = self.build(pack, number)
            rows = directory / "rows.bin"
            with rows.open("wb") as stream:
                for row in pack.rows:
                    stream.write(
                        struct.pack("<6q", row.program, row.quota, row.n, row.flag, row.fail_after, int(row.once))
                    )
            output = records.checked([binary, rows], "hosted driver", timeout=120).decode().splitlines()
            require(len(output) == len(pack.rows), f"{len(output)} observations for {len(pack.rows)} rows")
            failures = []
            for row, line in zip(pack.rows, output):
                counts, released, attempted = line.split("|")
                observed = [int(value) for value in counts.split()]
                released = [int(value) for value in released.split()]
                attempted = [int(value) for value in attempted.split()]
                wanted = [row.expected & MASK, row.allocations, row.allocations, row.peak]
                problems = []
                if observed != wanted:
                    problems.append(f"observed {observed}, expected {wanted}")
                if sorted(released) != list(range(1, row.allocations + 1)):
                    problems.append(f"allocation/free mismatch {released}")
                if row.release_order is not None and released != row.release_order:
                    problems.append(f"cleanup order {released}, expected {row.release_order}")
                if row.attempted_sizes is not None and attempted != row.attempted_sizes:
                    problems.append(f"allocation attempts {attempted}, expected {row.attempted_sizes}")
                if problems:
                    failures.append(f"{row.label}: " + "; ".join(problems))
            require(not failures, f"{len(failures)} failed rows, first: {failures[:4]}")
            self.rows += len(pack.rows)
            for index, (program, quota, n, flag, stderr) in enumerate(pack.aborts):
                single = directory / f"abort-{index}.bin"
                single.write_bytes(struct.pack("<6q", program, quota, n, flag, -1, 0))
                result = records.run([binary, single])
                require(
                    result.returncode == -6 and result.stdout == b"" and result.stderr == stderr,
                    f"{pack.names[program]}: expected hosted abort {stderr!r}, got {result.returncode} "
                    f"{result.stdout!r} {result.stderr!r}",
                )
                self.aborted += 1


def reject_all(compiler, scratch, rows, jobs=4):
    """Golden rejection rows, one compile each, on up to `jobs` threads with private scratch."""
    jobs = max(1, min(jobs, len(os.sched_getaffinity(0)), len(rows)))

    def work(number):
        directory = Path(scratch) / f"rejections-{number}"
        directory.mkdir()
        driver = records.Driver(compiler, directory)
        for row in rows[number::jobs]:
            driver.reject(row["label"], row["source"], row["diagnostic"])

    with ThreadPoolExecutor(jobs) as pool:
        list(pool.map(work, range(jobs)))
    return len(rows)
