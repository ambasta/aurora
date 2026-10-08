"""Shared bounded native transport for the independent package test oracles.

The suites own their cases, expected vectors, validators and rejection diagnostics.
This helper only runs those cases, accounts for resources and retains artifacts.
"""

import hashlib
import json
from pathlib import Path
import re
import resource
import shutil
import subprocess
import sys
import tarfile
import time

from owned_outputs import allocated_bytes, free_bytes, temporary_environment, write_checked_receipt

FLOOR, RESERVE, SOURCE_CAP = 1 << 30, 24 << 20, 64 << 10


def require(ok, message):
    if not ok:
        raise AssertionError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def safe_receipt(path, record):
    active = sys.exc_info()[0] is not None
    try:
        path.write_text(json.dumps(record, indent=2) + "\n")
    except BaseException as exc:
        if not active:
            raise
        print("Secondary receipt-write failure; primary failure preserved: " + str(exc), file=sys.stderr)


class PackageRunner:
    def __init__(self, compiler, artifacts, cap, *, root, prefix, shared, validate, function_prefix, sentinel):
        self.root, self.prefix, self.shared, self.validate = root, prefix, shared, validate
        self.function_prefix, self.sentinel = function_prefix, sentinel
        self.compiler, self.artifacts, self.cap = compiler, artifacts, cap
        self.peak, self.process_count = 0, 0
        self.tools = {}
        for name in ("as", "ld", "nm", "readelf"):
            found = shutil.which(name)
            require(found is not None, "required tool missing: " + name)
            self.tools[name] = Path(found).resolve(strict=True)
        self.pins = {}
        self.host_tools = set(self.tools.values()) | {Path(sys.executable).resolve(strict=True)}

    def measure(self):
        allocated = allocated_bytes(self.artifacts)
        self.peak = max(self.peak, allocated)
        return allocated, free_bytes(self.artifacts)

    def budget(self, reserve=0):
        allocated, free = self.measure()
        require(allocated + reserve <= self.cap, f"owned-output {self.cap} byte cap: {allocated} + reserve {reserve}")
        require(free - reserve >= FLOOR, "1 GiB free floor including reserve")
        return allocated

    def verify_pins(self, *, include_host_tools=True):
        for path, wanted in self.pins.items():
            if include_host_tools or path == self.compiler or path not in self.host_tools:
                require(sha(path) == wanted, "input/tool changed during execution: " + str(path))

    def command(self, args, directory, name, *, compiler=False, allow_rejection=False):
        args = list(args)
        if str(args[0]) in self.tools:
            args[0] = self.tools[str(args[0])]
        self.verify_pins(include_host_tools=False)
        self.budget(RESERVE)
        self.process_count += 1

        def limits():
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
            resource.setrlimit(resource.RLIMIT_CPU, (10, 11))
            resource.setrlimit(resource.RLIMIT_FSIZE, (8 << 20, 8 << 20))
            resource.setrlimit(resource.RLIMIT_AS, ((512 if compiler else 128) << 20,) * 2)

        executable = Path(args[0])
        host_scope = executable in self.host_tools and executable != self.compiler
        require(not host_scope or executable in self.pins, "trusted host tool lacks suite baseline")
        record = dict(
            command=list(map(str, args)),
            wall_seconds=30,
            cpu_soft_hard_seconds=[10, 11],
            address_space_bytes=(512 if compiler else 128) << 20,
            regular_file_cap=8 << 20,
            total_growth_reserve=24 << 20,
            executable_sha256=self.pins[executable] if host_scope else sha(executable),
            executable_hash_scope="suite-boundary" if host_scope else "command",
        )
        try:
            with (directory / (name + ".stdout")).open("wb") as out, (directory / (name + ".stderr")).open("wb") as err:
                result = subprocess.run(
                    list(map(str, args)),
                    stdout=out,
                    stderr=err,
                    timeout=30,
                    preexec_fn=limits,
                    env=temporary_environment(self.artifacts),
                )
            record["returncode"] = result.returncode
            stderr = (directory / (name + ".stderr")).read_bytes()
            allowed = (0, 1) if allow_rejection else (0,)
            require(result.returncode in allowed, f"{name} exit {result.returncode}: {stderr[:4096]!r}")
            if result.returncode == 0:
                require(not stderr, name + " unexpected stderr " + repr(stderr[:4096]))
            self.verify_pins(include_host_tools=False)
            self.budget()
            return result.returncode, (directory / (name + ".stdout")).read_bytes(), stderr
        except subprocess.TimeoutExpired:
            record["timeout"] = True
            raise AssertionError(name + " wall-clock timeout")
        finally:
            safe_receipt(directory / (name + ".command.json"), record)

    def compact(self, directory):
        # Preserve every successful byte, including native binaries and generated
        # assembly. Read back and verify the complete archive before deleting any
        # originals. Failed batches never reach this method.
        self.budget(RESERVE)
        paths = sorted(p for p in directory.iterdir() if p.is_file())
        pins = {p.name: dict(sha256=sha(p), bytes=p.stat().st_size, mode=p.stat().st_mode & 0o7777) for p in paths}
        archive = directory.with_suffix(".tar.xz")
        with tarfile.open(archive, "w:xz", preset=3) as output:
            for path in paths:
                output.add(path, arcname=path.name, recursive=False)
        self.budget()
        with tarfile.open(archive, "r:xz") as stored:
            members = stored.getmembers()
            require(len(members) == len(pins), "archive exact member count")
            require({x.name for x in members} == set(pins), "archive member equality")
            for member in members:
                require(member.isfile(), "archive regular files only")
                blob = stored.extractfile(member).read()
                wanted = pins[member.name]
                require(member.size == wanted["bytes"] and len(blob) == wanted["bytes"], "archive exact member size")
                require(member.mode == wanted["mode"], "archive exact member mode")
                require(
                    hashlib.sha256(blob).hexdigest() == wanted["sha256"], "lossless archive verification " + member.name
                )
        receipt = dict(archive=archive.name, sha256=sha(archive), verified_members=pins)
        (archive.with_suffix(".verified.json")).write_text(json.dumps(receipt, indent=2) + "\n")
        self.budget()
        for path in paths:
            path.unlink()
        directory.rmdir()
        self.budget()

    def batch(self, number, cases):
        self.budget(RESERVE)
        directory = self.artifacts / f"batch-{number:03d}"
        directory.mkdir()
        source = self.prefix + self.shared() + "".join(dict.fromkeys(case.helpers for case in cases))
        bodies = list(dict.fromkeys(case.body for case in cases))
        source += "".join(
            f"auto {self.function_prefix}_{i}(i64 slot,i64 argument1,i64 argument2)->u64{{{body}}}\n"
            for i, body in enumerate(bodies)
        )
        require(len(source.encode()) <= SOURCE_CAP, "64 KiB batch source bound")
        (directory / "input.au").write_text(source)
        receipt = dict(
            status="running",
            source_sha256=sha(directory / "input.au"),
            source_bytes=len(source.encode()),
            cases=len(cases),
            distinct_functions=len(bodies),
        )
        try:
            self.command(
                [
                    self.compiler,
                    "--module-root",
                    self.root / "library",
                    directory / "input.au",
                    "-o",
                    directory / "compiled.s",
                ],
                directory,
                "compiler",
                compiler=True,
            )
            expected = tuple(value for case in cases for value in case.expected)
            asm = [".text", ".globl _start", "_start:"]
            position = 0
            for case in cases:
                function = bodies.index(case.body)
                for slot in range(len(case.expected)):
                    asm += [
                        f"movq ${slot},%rdi",
                        f"movq ${case.arguments[0]},%rsi",
                        f"movq ${case.arguments[1]},%rdx",
                        f"call {self.function_prefix}_{function}",
                        f"movq %rax,observations+{position}(%rip)",
                    ]
                    position += 8
            asm += [
                "movq $1,%rax",
                "movq $1,%rdi",
                "leaq observations(%rip),%rsi",
                f"movq ${position},%rdx",
                "syscall",
                f"cmpq ${position},%rax",
                "jne .Lwrite_failed",
                "movq $60,%rax",
                "xorq %rdi,%rdi",
                "syscall",
                ".Lwrite_failed:",
                "movq $60,%rax",
                "movq $91,%rdi",
                "syscall",
                ".bss",
                ".align 8",
                f"observations: .zero {position}",
                '.section .note.GNU-stack,"",@progbits',
            ]
            (directory / "entry.s").write_text("\n".join(asm) + "\n")
            self.command(["as", "--64", directory / "compiled.s", "-o", directory / "program.o"], directory, "assemble")
            self.command(["as", "--64", directory / "entry.s", "-o", directory / "entry.o"], directory, "entry")
            self.command(
                ["ld", "-o", directory / "program", directory / "entry.o", directory / "program.o"], directory, "link"
            )
            _, undefined, _ = self.command(["nm", "-u", directory / "program"], directory, "undefined-symbols")
            require(not undefined.strip(), "freestanding binary must have no unresolved symbols")
            _, elf, _ = self.command(["readelf", "-l", "-d", directory / "program"], directory, "elf-linkage")
            require(b"INTERP" not in elf and b"NEEDED" not in elf, "no ELF interpreter or runtime library dependencies")
            code, output, _ = self.command([directory / "program"], directory, "native")
            observed = self.validate(output, expected, code)
            require((directory / "input.au").read_text() == source, "compiler must preserve source")
            offset = 0
            records = []
            for case in cases:
                end = offset + len(case.expected)
                records.append(
                    dict(
                        label=case.label,
                        arguments=case.arguments,
                        expected=case.expected,
                        observed=observed[offset:end],
                    )
                )
                offset = end
            receipt.update(
                status="passed",
                complete_u64_observations=len(expected),
                observations=records,
                assembly_sha256=sha(directory / "compiled.s"),
                executable_sha256=sha(directory / "program"),
                native_output_sha256=sha(directory / "native.stdout"),
            )
        except Exception as exc:
            receipt.update(status="failed", error=str(exc))
            raise
        finally:
            safe_receipt(directory / "receipt.json", receipt)
        self.compact(directory)

    def reject(self, number, label, source, message):
        for existing in (False, True):
            self.budget(65536)
            directory = self.artifacts / f"reject-{number:02d}-{int(existing)}"
            directory.mkdir()
            path = directory / "input.au"
            path.write_text(source)
            output = directory / "compiled.s"
            sentinel = self.sentinel
            if existing:
                output.write_bytes(sentinel)
            receipt = dict(status="running", label=label, existing_output=existing)
            try:
                code, stdout, diagnostic = self.command(
                    [self.compiler, "--module-root", self.root / "library", path, "-o", output],
                    directory,
                    "compiler",
                    compiler=True,
                    allow_rejection=True,
                )
                require(code == 1, label + " must reject normally with exit 1")
                require(not stdout, label + " unexpected stdout")
                text = diagnostic.decode(errors="strict")
                # Validate the expected root path and complete renderer syntax before
                # comparing the explanation. Never strip location-like user content.
                match = re.fullmatch(
                    rf"(?:{re.escape(str(path))}:[1-9][0-9]*:[1-9][0-9]*|aurorac): error "
                    r"AU(?:1001|200[123]|3001|4001): ([^\n]+)\n",
                    text,
                )
                require(match is not None, label + " malformed rejection: " + text)
                normalized = match.group(1)
                require(normalized == message, label + " wrong exact rejection: " + text)
                require(path.read_text() == source, "rejection changed source")
                require(
                    output.read_bytes() == sentinel if existing else not output.exists(), "rejection changed output"
                )
                receipt.update(status="passed", diagnostic=text, normalized_diagnostic=normalized)
            except Exception as exc:
                receipt.update(status="failed", error=str(exc))
                raise
            finally:
                safe_receipt(directory / "receipt.json", receipt)


def finalize_report(runner, report, compiler, artifacts):
    # Every resource/measurement failure is recorded separately. Neither the
    # resource guard nor report writing may mask an already active first error.
    errors = []
    report["host_tool_hash_scope"] = "suite entry/finalization; compiler and sources remain command-scoped"
    try:
        runner.verify_pins()
    except BaseException as exc:
        errors.append("final input/tool hashes: " + str(exc))
    report.update(process_count=runner.process_count, finished_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    try:
        report["compiler_sha256_after"] = sha(compiler)
    except BaseException as exc:
        errors.append("compiler final hash: " + str(exc))
    try:
        allocated, free = runner.measure()
        report.update(
            owned_output_allocated_bytes=allocated,
            peak_owned_output_allocated_bytes=runner.peak,
            output_root=str(runner.artifacts),
            accounting_scope="invocation outputs including tmp and archives",
            global_free_bytes=free,
        )
    except BaseException as exc:
        errors.append("non-enforcing final resource measurement: " + str(exc))
    try:
        runner.budget()
    except BaseException as exc:
        errors.append("final resource validation: " + str(exc))
    if errors:
        report["finalization_errors"] = list(errors)
        if report.get("status") != "failed":
            report.update(status="failed", error="run finalization failed")
    try:
        write_checked_receipt(artifacts / "manifest.json", report, runner.budget)
    except BaseException as exc:
        errors.append("failed-run receipt write: " + str(exc))
        print("Manifest receipt write failed; original error remains primary: " + str(exc), file=sys.stderr)
    return errors
