#!/usr/bin/env python3
"""Shared native runner for compiler-semantics cases.

A test registers its cases as data and calls `Suite.finish()`. Accepted
programs are packed into as few compiled programs as aurorac's 1 MiB source
limit allows: every case keeps its own declarations inside a private namespace
of one generated module, which is compiled, assembled and linked once. Cases
share a pack only with the same options, extra modules and imports, so packing
never widens what a case can see. The binary runs once for all value cases.
Trap cases live in the same binary; its entry glue selects one case from argv,
so each trap is one exec, not one compile. A pack that does not compile is
split until the failing case is found (a case that cannot nest in a namespace
is compiled alone); `standalone=True` marks cases that use a whole per-graph
compiler budget or pin root-level symbols. Every rejection is compiled once
and must fail with a diagnostic and no published artifact. Independent
programs run in a thread pool sized to the available CPUs and bounded to about
2 GiB of available memory per worker (AURORA_ORACLE_JOBS caps it).

Results are the complete 64-bit return register. Traps must be a kernel
SIGILL at the exact named UD2 label, observed by integer_signal.cpp.
"""

from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from enum import Enum
import os
from pathlib import Path
import re
import resource
import shlex
import signal
import struct
import subprocess
import tempfile
import threading
import time


ROOT = Path(__file__).resolve().parents[2]
LIBRARY = ROOT / "library"
MASK = (1 << 64) - 1
UD2 = 0x0B0F
FAULT_IDENTITY = 0x4155524F52414654
# aurorac accepts at most 1 MiB per source file; leave room for the wrapper.
SOURCE_LIMIT = 960 * 1024
PACKED_MODULE = "cases"
RUN_CHUNK = 64
REJECTION_SENTINEL = b"existing output must survive a rejection\n"
# One well-formed error line with a normal (lexical, syntax, module, semantic) code.
# As a rejection `pattern`, DIAGNOSTIC also requires the line to name the input path.
DIAGNOSTIC = re.compile(r"(?:[^\n]*:[1-9][0-9]*:[1-9][0-9]*|aurorac): error AU(?:100[12]|200[123]|3001|4001): [^\n]+\n")
STACK_NOTE = '.section .note.GNU-stack,"",@progbits'
# Children inherit a zero core limit (a preexec_fn is unsafe with the runner's threads).
resource.setrlimit(resource.RLIMIT_CORE, (0, resource.getrlimit(resource.RLIMIT_CORE)[1]))


def diagnostic_line(path):
    """DIAGNOSTIC for one input: `path:line:column` or `aurorac`, then one normal error."""
    return re.compile(
        rf"(?:{re.escape(str(path))}:[1-9][0-9]*:[1-9][0-9]*|aurorac): error AU(?:100[12]|200[123]|3001|4001): [^\n]+\n"
    )


class Trap(Enum):
    BOUNDS = ".Laurora_bounds_trap"
    OVERFLOW = ".Laurora_overflow_trap"
    ZERO = ".Laurora_division_zero_trap"
    COUNT = ".Laurora_shift_count_trap"


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def is_trap(expected):
    return isinstance(expected, Enum) and isinstance(expected.value, str) and expected.value.startswith(".L")


def worker_count():
    """CPUs, bounded by MemAvailable at about 2 GiB per worker and AURORA_ORACLE_JOBS."""
    count = len(os.sched_getaffinity(0))
    try:
        with open("/proc/meminfo") as meminfo:
            for line in meminfo:
                if line.startswith("MemAvailable:"):
                    count = min(count, int(line.split()[1]) // (2 << 20))
    except OSError:
        pass
    cap = os.environ.get("AURORA_ORACLE_JOBS")
    if cap:
        count = min(count, int(cap))
    return max(1, count)


def run(args, timeout=30, stdin=None, env=None):
    """Run a command; a timeout is a failure, never a trap."""
    try:
        return subprocess.run([str(arg) for arg in args], capture_output=True, timeout=timeout, input=stdin, env=env)
    except subprocess.TimeoutExpired as error:
        raise AssertionError(f"timeout after {timeout}s is a failure, not a trap: {args}") from error


def command(args, timeout=30, allow_signal=False, allow_rejection=False):
    result = run(args, timeout)
    require(
        result.returncode == 0
        or (allow_signal and result.returncode < 0)
        or (allow_rejection and result.returncode == 1),
        f"command failed ({result.returncode}): {args}\n{result.stderr.decode(errors='replace')}",
    )
    return result


@dataclass(frozen=True)
class Observation:
    output: bytes
    exit_code: int | None = None
    terminal_signal: int | None = None
    delivery_signal: int | None = None
    pc: int | None = None
    instruction: int | None = None
    signal_code: int | None = None


def observe(result):
    """Decode a freestanding run: stdout results plus at most one fault record."""
    if result.returncode >= 0:
        require(not result.stderr, f"normal exit {result.returncode} unexpectedly reported {result.stderr!r}")
        return Observation(result.stdout, exit_code=result.returncode)
    require(len(result.stderr) == 40, f"signal {-result.returncode} without one fault record: {result.stderr!r}")
    identity, delivered, pc, instruction, code = struct.unpack("<QQQQq", result.stderr)
    require(identity == FAULT_IDENTITY, "malformed native fault record identity")
    return Observation(result.stdout, None, -result.returncode, delivered, pc, instruction, code)


def check_trap(observed, expected, symbols, name):
    require(expected.value in symbols, f"{name}: missing named trap {expected.value}")
    require(
        observed.exit_code is None
        and observed.terminal_signal == signal.SIGILL
        and observed.delivery_signal == signal.SIGILL,
        f"{name}: expected actual SIGILL termination, observed {observed}",
    )
    require(not observed.output, f"{name}: trap unexpectedly returned scalar bytes")
    require(
        observed.pc == symbols[expected.value],
        f"{name}: wrong trap PC {observed.pc!r}; expected {expected.value} at {symbols[expected.value]:#x}",
    )
    require(observed.instruction == UD2, f"{name}: trap instruction is not UD2")
    require(
        observed.signal_code is not None and observed.signal_code > 0,
        f"{name}: SIGILL was not a kernel-generated instruction fault",
    )


validate_trap = check_trap


def check_words(observed, expected, names):
    """Each expected value is compared with the complete 64-bit result."""
    require(
        observed.exit_code == 0 and observed.terminal_signal is None,
        f"{names[:4]}: expected normal return, observed {observed}",
    )
    require(
        len(observed.output) == len(expected) * 8,
        f"{names[:4]}: expected {len(expected) * 8} result bytes, got {len(observed.output)}",
    )
    for index, (value, name) in enumerate(zip(expected, names)):
        actual = int.from_bytes(observed.output[index * 8 : index * 8 + 8], "little")
        require(actual == int(value) & MASK, f"{name}: expected {value}, got {actual} ({signed64(actual)} signed)")


def signed64(value):
    value &= MASK
    return value - (1 << 64) if value >> 63 else value


def rejected(check, label):
    try:
        check()
    except AssertionError:
        return
    raise AssertionError(f"check accepted {label}")


def symbols_of(binary):
    symbols = {}
    for line in command(["nm", "--defined-only", binary]).stdout.decode().splitlines():
        fields = line.split()
        if len(fields) == 3:
            symbols[fields[2]] = int(fields[0], 16)
    return symbols


def mangled(module, namespace, name):
    """The suffix of aurorac's native identity for `module::namespace::name` (compiler/MODULES.md)."""
    parts = module.split(".")
    path = "_" + "".join(f"{len(part)}{part}" for part in parts)
    scope = f"_n1_{len(namespace)}{namespace}_" if namespace else "_n0__"
    return f"_m{len(parts)}{path}{scope}d{len(name)}{name}"


def resolve_entry(labels, module, namespace, name):
    """A scalar root function keeps its name; others are ordinary (f) or resource-signature (v) identities."""
    if not namespace and name in labels:
        return name
    suffix = mangled(module, namespace, name)
    found = [label for label in (f"__au_f{suffix}", f"__au_v{suffix}") if label in labels]
    require(len(found) == 1, f"expected one native entry for {module}::{namespace}::{name}, found {found}")
    return found[0]


LABEL = re.compile(r"^([A-Za-z_][A-Za-z_0-9]*):", re.M)
HEADER = re.compile(r"\s*module\s+([A-Za-z_][A-Za-z_0-9.]*)\s*;")
IMPORT = re.compile(r"\s*import\s+([A-Za-z_][A-Za-z_0-9.]*)\s*;")


def split_program(source):
    """Return (module, imports, declarations), or None if the source has another shape."""
    header = HEADER.match(source)
    if header is None:
        return None
    position, imports = header.end(), []
    while (statement := IMPORT.match(source, position)) is not None:
        imports.append(statement.group(1))
        position = statement.end()
    return header.group(1), imports, source[position:]


def freestanding_glue(entries, values, note=False):
    """`_start`: no argument runs entries[values] in order; `prog K` runs entry K.

    `note` adds the non-executable-stack note for glue assembled on its own."""
    lines = [
        ".text",
        ".globl _start",
        "_start:",
        # prctl(PR_SET_DUMPABLE, 0): the fault still terminates the process, but
        # no core is handed to the host's core-dump helper (a pipe ignores RLIMIT_CORE).
        "    movq $157, %rax",
        "    movq $4, %rdi",
        "    xorl %esi, %esi",
        "    syscall",
        "    call aurora_install_integer_signal_observer",
        "    testq %rax, %rax",
        "    jz .Lglue_ready",
        "    movq $60, %rax",
        "    movq $125, %rdi",
        "    syscall",
        ".Lglue_ready:",
        "    cmpq $1, (%rsp)",
        "    je .Lglue_all",
        "    movq 16(%rsp), %rsi",
        "    xorl %ebx, %ebx",
        ".Lglue_digit:",
        "    movzbl (%rsi), %eax",
        "    testl %eax, %eax",
        "    jz .Lglue_parsed",
        "    subl $48, %eax",
        "    cmpl $9, %eax",
        "    ja .Lglue_bad",
        "    imulq $10, %rbx",
        "    addq %rax, %rbx",
        "    incq %rsi",
        "    jmp .Lglue_digit",
        ".Lglue_parsed:",
        f"    cmpq ${len(entries)}, %rbx",
        "    jae .Lglue_bad",
        "    leaq .Lglue_table(%rip), %rax",
        "    call *(%rax,%rbx,8)",
        "    call .Lglue_write",
        "    jmp .Lglue_exit",
        ".Lglue_all:",
    ]
    for index in values:
        lines += [f"    call {entries[index]}", "    call .Lglue_write"]
    lines += [
        ".Lglue_exit:",
        "    movq $60, %rax",
        "    xorq %rdi, %rdi",
        "    syscall",
        ".Lglue_bad:",
        "    movq $60, %rax",
        "    movq $124, %rdi",
        "    syscall",
        # Writes the complete result register; called with the stack aligned as in _start.
        ".Lglue_write:",
        "    pushq %rax",
        "    movq $1, %rax",
        "    movq $1, %rdi",
        "    movq %rsp, %rsi",
        "    movq $8, %rdx",
        "    syscall",
        "    popq %rax",
        "    ret",
        ".section .rodata",
        ".balign 8",
        ".Lglue_table:",
    ]
    lines += [f"    .quad {entry}" for entry in entries]
    lines += [STACK_NOTE if note else ".text", ""]
    return "\n".join(lines)


class Freestanding:
    """No libc: the assembly entry glue plus the freestanding signal observer."""

    def prepare(self, directory):
        # Meson builds the observer once; standalone runs compile it here.
        if os.environ.get("AURORA_INTEGER_SIGNAL_OBSERVER"):
            self.observer = Path(os.environ["AURORA_INTEGER_SIGNAL_OBSERVER"])
            return
        self.observer = directory / "integer_signal.o"
        cxx = shlex.split(os.environ.get("CXX", "c++"))
        command(
            cxx
            + "-std=c++23 -O1 -Wall -Wextra -Werror -c -ffreestanding -fno-stack-protector -fno-exceptions "
            "-fno-rtti -fno-asynchronous-unwind-tables -fno-pie".split()
            + [ROOT / "tests/compiler/integer_signal.cpp", "-o", self.observer],
            timeout=120,
        )

    def glue(self, entries, values, text=None):
        return freestanding_glue(entries, values)

    def link(self, objects, binary):
        command(["ld", "-o", binary, *objects, self.observer])

    def invoke(self, binary, index, arguments, timeout):
        return run([binary, index, *arguments], timeout)


@dataclass
class Case:
    name: str
    source: str
    expected: object = None  # int/bool, a trap enum, or None for a custom program
    error: object = None  # rejection: True, a fragment, fragments, or a compiled regex
    entry: str = "test"
    modules: dict | None = None
    options: tuple = ()
    existing_output: bytes | None = None
    pattern: re.Pattern | None = None
    standalone: bool = False
    inspect: object = None  # callable(assembly text) for a standalone compile
    invocations: list = field(default_factory=list)  # custom-harness (argv, callback) pairs
    index: int = 0


class Program:
    """A handle for a custom-harness case; invocations run after linking."""

    def __init__(self, suite, case):
        self.suite = suite
        self.case = case
        self.name = case.name

    def invoke(self, arguments, callback):
        self.case.invocations.append((list(arguments), callback))


class Suite:
    """Collect cases, then build and run them all in `finish()`."""

    def __init__(
        self,
        compiler,
        label="native",
        *,
        module_roots=(LIBRARY,),
        options=(),
        timeout=5.0,
        harness=None,
        directory=None,
        ignore_case=False,
        pattern=None,
        pack_templates=None,
    ):
        self.compiler = Path(compiler).resolve()
        self.label = label
        self.module_roots = [Path(root) for root in module_roots]
        self.options = tuple(options)
        self.timeout = timeout
        self.harness = harness or Freestanding()
        self.directory = directory
        self.ignore_case = ignore_case
        self.pattern = pattern
        # Optional bound on `template<` declarations per pack, below aurorac's
        # 64-template graph limit, so template-heavy suites do not bisect.
        self.pack_templates = pack_templates
        self.cases = []
        self.rejections = []
        self.failures = []
        self.lock = threading.Lock()
        self.counts = dict.fromkeys(
            ("values", "traps", "invocations", "rejections", "programs", "runs", "fallbacks"), 0
        )

    # Registration ---------------------------------------------------------

    def check(
        self,
        name,
        source,
        expected=42,
        error=None,
        *,
        modules=None,
        options=(),
        existing_output=None,
        entry="test",
        standalone=False,
        inspect=None,
    ):
        """Accept `source` and return `expected` from `entry`, or reject it when `error` is given.

        `expected` is compared with the complete 64-bit result (negative values
        and bools included) or is a trap enum whose value names the UD2 label.
        `inspect(assembly)` implies a standalone compile of this case alone.
        """
        if error is not None:
            self.reject(name, source, error, modules=modules, options=options, existing_output=existing_output)
            return
        require(isinstance(expected, (int, bool)) or is_trap(expected), f"{name}: unsupported expectation {expected!r}")
        self.cases.append(
            Case(
                name,
                source,
                expected,
                entry=entry,
                modules=modules,
                options=tuple(options),
                existing_output=existing_output,
                standalone=standalone or inspect is not None,
                inspect=inspect,
            )
        )

    def value(self, name, body, expected, result="i64", prelude="", imports=()):
        """A function-body case: `auto test()->result{body}` after the prelude."""
        header = "module test;" + "".join(f"import {module};" for module in imports)
        self.check(name, f"{header}{prelude}\nauto test()->{result}{{{body}}}\n", expected)

    def reject(self, name, source, error=True, *, modules=None, options=(), existing_output=None, pattern=None):
        self.rejections.append(
            Case(
                name,
                source,
                error=error,
                modules=modules,
                options=tuple(options),
                existing_output=existing_output,
                pattern=pattern or self.pattern,
            )
        )

    def program(self, name, source, *, entry="test", modules=None, options=(), standalone=False, inspect=None):
        """A program for a custom harness; register runs on the returned handle with `invoke`."""
        case = Case(
            name,
            source,
            None,
            entry=entry,
            modules=modules,
            options=tuple(options),
            standalone=standalone or inspect is not None,
            inspect=inspect,
        )
        self.cases.append(case)
        return Program(self, case)

    # Execution ------------------------------------------------------------

    def start(self, directory):
        """Use `directory` for scratch and prepare the harness; `finish` and `build` need it."""
        if getattr(self, "root", None) is None:
            self.root = Path(directory)
            self.root.mkdir(parents=True, exist_ok=True)
            self.sequence = 0
            self.harness.prepare(self.root)

    def build(self, name, source, entry="test", *, modules=None, options=(), folder=None):
        """Compile and link one program now, unpacked, in `folder` if given; return (binary, assembly text)."""
        case = Case(name, source, None, entry=entry, modules=modules, options=tuple(options), standalone=True)
        built = self._build([case], packed=False, folder=folder)
        require(built is not None, f"{name}: build failed:\n" + "\n".join(self.failures[-1:]))
        return built[0], built[2]

    def finish(self, report=True):
        started = time.monotonic()
        with tempfile.TemporaryDirectory(prefix="aurora-" + re.sub(r"\W+", "-", self.label) + "-") as temporary:
            self.start(self.directory or temporary)
            jobs = []
            for group in self._groups():
                jobs.extend(("pack", pack) for pack in self._packs(group))
            for index, case in enumerate(self.rejections):
                case.index = index
                jobs.append(("reject", case))
            # Largest work first keeps the pool busy until the end.
            jobs.sort(key=lambda job: -len(job[1]) if job[0] == "pack" else 0)
            # Builds hand back their runs in chunks, so execs also use every worker.
            with ThreadPoolExecutor(max_workers=worker_count()) as pool:
                pending = {pool.submit(self._job, job) for job in jobs}
                while pending:
                    done, pending = wait(pending, return_when=FIRST_COMPLETED)
                    for future in done:
                        pending.update(pool.submit(self._job, ("task", task)) for task in future.result())
        elapsed = time.monotonic() - started
        if self.failures:
            text = "\n\n".join(self.failures[:50])
            raise AssertionError(f"{len(self.failures)} {self.label} failures\n{text}")
        counts = self.counts
        if report:
            print(
                f"PASS {self.label}: {counts['values']} values, {counts['traps']} exact-site traps, "
                f"{counts['rejections']} rejections; {counts['programs']} programs, {counts['runs']} runs"
                + (f", {counts['fallbacks']} unpacked" if counts["fallbacks"] else "")
                + f"; {elapsed:.2f}s",
                flush=True,
            )
        return counts

    def _fail(self, case, message):
        details = f"{case.name}: {message}\nReproduction source:\n{case.source}"
        if case.modules:
            details += "\nReproduction modules:\n" + repr(case.modules)
        with self.lock:
            self.failures.append(details)
        print("FAIL", details, flush=True)

    def _groups(self):
        groups = {}
        for case in self.cases:
            alone = case.standalone or case.existing_output is not None or split_program(case.source) is None
            # Cases share a pack only with the same imports: an extra import could change visibility.
            imports = () if alone else tuple(sorted(split_program(case.source)[1]))
            key = ("alone", id(case)) if alone else (case.options, repr(sorted((case.modules or {}).items())), imports)
            groups.setdefault(key, []).append(case)
        return list(groups.values())

    def _packs(self, group):
        packs, current, size, templates = [], [], 0, 0
        for case in group:
            length = len(case.source.encode()) + 64
            weight = case.source.count("template<") if self.pack_templates else 0
            if current and (size + length > SOURCE_LIMIT or templates + weight > (self.pack_templates or weight)):
                packs.append(current)
                current, size, templates = [], 0, 0
            current.append(case)
            size += length
            templates += weight
        if current:
            packs.append(current)
        return packs

    def _workspace(self, prefix):
        with self.lock:
            self.sequence += 1
            folder = self.root / f"{prefix}-{self.sequence}"
        folder.mkdir()
        return folder

    def _roots(self, folder, modules):
        roots = []
        if modules:
            root = folder / "modules"
            for module, text in modules.items():
                path = root / (module.replace(".", "/") + ".au")
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text)
            roots.append(root)
        return roots + self.module_roots

    def _compile(self, folder, source, modules, options, output, timeout):
        path = folder / "input.au"
        data = source if isinstance(source, bytes) else source.encode()  # bytes: deliberately invalid UTF-8
        path.write_bytes(data)
        arguments = [self.compiler, *self.options, *options]
        for root in self._roots(folder, modules):
            arguments += ["--module-root", root]
        result = run([*arguments, path, "-o", output], timeout)
        require(path.read_bytes() == data, "compiler modified its input")
        return result

    def _job(self, job):
        """Run one build, rejection or chunk of runs; return follow-up run chunks."""
        kind, item = job
        try:
            if kind == "reject":
                self._reject(item)
                return []
            if kind == "task":
                item()
                return []
            return self._pack(item)
        except Exception as error:  # noqa: BLE001 - every failure is reported with its case
            cases = [item] if kind == "reject" else item if kind == "pack" else None
            if cases is None:
                with self.lock:
                    self.failures.append(f"{type(error).__name__}: {error}")
                return []
            suffix = f" (pack of {len(cases)})" if len(cases) > 1 else ""
            self._fail(cases[0], f"{type(error).__name__}: {error}{suffix}")
            return []

    def _reject(self, case):
        folder = self._workspace("reject")
        output = folder / "output.s"
        # Alternate absent and existing artifacts: neither may be published or changed.
        existing = case.existing_output
        if existing is None and case.index % 2:
            existing = REJECTION_SENTINEL
        if existing is not None:
            output.write_bytes(existing)
        result = self._compile(folder, case.source, case.modules, case.options, output, self.timeout + 25)
        stderr = result.stderr.decode(errors="replace")
        problems = []
        if result.returncode != 1:
            problems.append(f"expected compiler exit 1, got {result.returncode}")
        if not stderr:
            problems.append("rejection lacks a diagnostic")
        if existing is None and output.exists():
            problems.append("rejection created an artifact")
        if existing is not None and (not output.exists() or output.read_bytes() != existing):
            problems.append("rejection changed the existing output")
        if not self._diagnostic_matches(case.error, stderr):
            problems.append(f"diagnostic does not match {case.error!r}")
        if case.pattern is not None:
            pattern = diagnostic_line(folder / "input.au") if case.pattern is DIAGNOSTIC else case.pattern
            try:
                strict = result.stderr.decode()
            except UnicodeDecodeError:
                strict = None
            if strict is None or pattern.fullmatch(strict) is None:
                problems.append("diagnostic is not one well-formed error line for this input")
        if problems:
            self._fail(case, "; ".join(problems) + f"\nstderr: {stderr!r}")
            return
        with self.lock:
            self.counts["rejections"] += 1

    def _pack_note(self, cases):
        return f" (pack of {len(cases)} cases)" if len(cases) > 1 else ""

    def _diagnostic_matches(self, error, stderr):
        if error is True:
            return True
        if isinstance(error, re.Pattern):
            return error.search(stderr) is not None
        fragments = (error,) if isinstance(error, str) else tuple(error)
        if self.ignore_case:
            return any(fragment.lower() in stderr.lower() for fragment in fragments)
        return any(fragment in stderr for fragment in fragments)

    def _source(self, cases):
        imports, parts = [], []
        for number, case in enumerate(cases):
            _, used, declarations = split_program(case.source)
            imports += [module for module in used if module not in imports]
            parts.append(f"namespace c{number} {{\n{declarations}\n}}\n")
        header = f"module {PACKED_MODULE};\n" + "".join(f"import {module};\n" for module in imports)
        return header + "".join(parts)

    def _pack(self, cases, packed=True):
        """Compile, link and run one pack; split it to find a case that does not compile."""
        built = self._build(cases, packed)
        if built is None:
            return []
        if isinstance(built, list):
            return built
        binary, entries, _ = built
        values = [index for index, case in enumerate(cases) if case.expected is not None and not is_trap(case.expected)]
        return self._execute(binary, cases, values)

    def _build(self, cases, packed, folder=None):
        """Return (binary, entries, text), follow-up chunks from a split pack, or None after a failure."""
        if folder is None:
            folder = self._workspace("program")
        else:
            folder.mkdir(parents=True)
        if packed and len(cases) == 1 and cases[0].standalone:
            packed = False
        if packed and (cases[0].existing_output is not None or split_program(cases[0].source) is None):
            packed = False
        source = self._source(cases) if packed else cases[0].source
        assembly = folder / "output.s"
        if not packed and cases[0].existing_output is not None:
            assembly.write_bytes(cases[0].existing_output)
        compiled = self._compile(
            folder, source, cases[0].modules, cases[0].options, assembly, max(60, self.timeout * 4) + len(cases) * 0.05
        )
        if compiled.returncode != 0:
            message = compiled.stderr.decode(errors="replace")
            if compiled.returncode != 1 or not message:
                # Only an ordinary diagnostic (a per-graph limit, a case that cannot nest) is split.
                self._fail(cases[0], f"compiler exit {compiled.returncode}: {message}" + self._pack_note(cases))
                return None
            if len(cases) > 1:
                middle = len(cases) // 2
                return self._pack(cases[:middle]) + self._pack(cases[middle:])
            if packed:
                # A case may use a construct that does not nest in a namespace.
                with self.lock:
                    self.counts["fallbacks"] += 1
                return self._pack(cases, packed=False)
            self._fail(cases[0], f"compiler exit {compiled.returncode}: {message}")
            return None
        text = assembly.read_text()
        notes = [line.strip() for line in text.splitlines() if ".note.GNU-stack" in line]
        if notes != [STACK_NOTE]:
            self._fail(cases[0], f"compiler output needs one non-executable-stack note, has {notes}")
            return None
        if not packed and cases[0].inspect is not None:
            try:
                cases[0].inspect(text)
            except AssertionError as error:
                self._fail(cases[0], f"assembly inspection: {error}")
                return None
        labels = set(LABEL.findall(text))
        if packed:
            entries = [resolve_entry(labels, PACKED_MODULE, f"c{n}", case.entry) for n, case in enumerate(cases)]
        elif callable(cases[0].entry):
            entries = [cases[0].entry(text)]
        else:
            header = re.match(r"\s*(?:export\s+)?module\s+([A-Za-z_][A-Za-z_0-9.]*)\s*;", source)
            module = header.group(1) if header else ""
            entries = [resolve_entry(labels, module, "", cases[0].entry)]
        values = [index for index, case in enumerate(cases) if case.expected is not None and not is_trap(case.expected)]
        (folder / "program.s").write_text(text + "\n" + self.harness.glue(entries, values, text))
        command(["as", "--64", "-L", folder / "program.s", "-o", folder / "program.o"])
        binary = folder / "program"
        self.harness.link([folder / "program.o"], binary)
        with self.lock:
            self.counts["programs"] += 1
        return binary, entries, text

    def _execute(self, binary, cases, values):
        """Run all value cases once now; return the per-case runs as chunks."""
        runs = 0
        if values:
            runs += 1
            try:
                observed = observe(run([binary], self.timeout + 0.01 * len(values)))
                check_words(observed, [cases[i].expected for i in values], [cases[i].name for i in values])
            except AssertionError as batch:
                # Attribute the failure: run every value case on its own.
                failed = 0
                for index in values:
                    runs += 1
                    try:
                        check_words(
                            observe(run([binary, index], self.timeout)), [cases[index].expected], [cases[index].name]
                        )
                    except AssertionError as error:
                        failed += 1
                        self._fail(cases[index], str(error))
                    else:
                        with self.lock:
                            self.counts["values"] += 1
                if not failed:
                    self._fail(cases[values[0]], f"value cases fail only when run together: {batch}")
            else:
                with self.lock:
                    self.counts["values"] += len(values)
        with self.lock:
            self.counts["runs"] += runs
        runs = [(index, None) for index, case in enumerate(cases) if is_trap(case.expected)]
        symbols = symbols_of(binary) if runs else {}
        runs += [(index, invocation) for index, case in enumerate(cases) for invocation in case.invocations]
        return [
            lambda chunk=runs[start : start + RUN_CHUNK]: self._runs(binary, cases, symbols, chunk)
            for start in range(0, len(runs), RUN_CHUNK)
        ]

    def _runs(self, binary, cases, symbols, chunk):
        for index, invocation in chunk:
            case = cases[index]
            try:
                if invocation is None:
                    check_trap(observe(run([binary, index], self.timeout)), case.expected, symbols, case.name)
                else:
                    arguments, callback = invocation
                    callback(self.harness.invoke(binary, index, arguments, self.timeout))
            except Exception as error:  # noqa: BLE001 - a failing run is reported against its case
                self._fail(case, f"{type(error).__name__}: {error}")
            else:
                with self.lock:
                    self.counts["traps" if invocation is None else "invocations"] += 1
        with self.lock:
            self.counts["runs"] += len(chunk)


# Compatibility for library tests that still drive one program per call. -----


def validate_values(observed, expected, names):
    """Signed-or-unsigned scalar list check (integer_oracle form)."""
    check_words(observed, expected, names)


def validate_case_values(observed, cases):
    """Case-list check with u64/i64/bool decoding (unsigned_oracle form)."""
    for case in cases:
        require(getattr(case, "result_type", "i64") in ("u64", "i64", "bool"), "unknown oracle result type")
    check_words(observed, [case.expected for case in cases], [case.name for case in cases])


@dataclass(frozen=True)
class Rejection:
    name: str
    source: str


class NativeRunner:
    """One program per call: `assemble` calls `functions` in order and observes the run."""

    def __init__(self, directory, compiler, timeout, *, symbol_timeout=30):
        self.directory = Path(directory)
        self.compiler = None if compiler is None else Path(compiler)
        self.timeout = timeout
        self.harness = Freestanding()
        self.harness.prepare(self.directory)
        self.observer = self.harness.observer

    def assemble(self, assembly, functions, *, values=None):
        # Callers link program.o elsewhere too, so the entry glue stays a separate object.
        output = self.directory / "program.o"
        if isinstance(assembly, bytes):
            # Test entry glue lives in another object. Expose only its explicitly
            # selected entries in this private test copy, never other functions.
            output.write_bytes(assembly)
            command(["objcopy", *("--globalize-symbol=" + name for name in functions), output])
        else:
            program = self.directory / "program.s"
            program.write_text(assembly)
            # -L retains compiler-local trap labels for exact instruction attribution.
            command(["as", "--64", "-L", program, "-o", output])
        if values is None:
            values = range(len(functions))
        (self.directory / "entry.s").write_text(freestanding_glue(list(functions), values, note=True))
        command(["as", "--64", self.directory / "entry.s", "-o", self.directory / "entry.o"])
        binary = self.directory / "program"
        self.harness.link([self.directory / "entry.o", self.directory / "program.o"], binary)
        return observe(run([binary], self.timeout)), symbols_of(binary)

    def cases(self, cases, *, compiler_timeout=None):
        require(cases and (len(cases) == 1 or all(not c.prelude for c in cases)), "only independent cases batch")
        require(all(not is_trap(c.expected) for c in cases) or len(cases) == 1, "trap batch would hide later cases")
        imports = {module for case in cases for module in getattr(case, "imports", ())}
        if any(getattr(case, "library", False) for case in cases):
            imports.add("std.integer")
        source = "module test;\n" + "".join(f"import {module};\n" for module in sorted(imports))
        functions = []
        for index, case in enumerate(cases):
            functions.append(f"oracle_{index}")
            result = getattr(case, "result_type", "i64")
            source += case.prelude + f"\nauto oracle_{index}()->{result}{{{case.body}}}\n"
        input_path = self.directory / "input.au"
        input_path.write_text(source)
        output = self.directory / "compiled.s"
        output.unlink(missing_ok=True)
        try:
            command(
                [self.compiler, "--module-root", LIBRARY, input_path, "-o", output],
                timeout=max(30, self.timeout) if compiler_timeout is None else compiler_timeout,
            )
            require(input_path.read_text() == source, "compiler modified its input")
            observed, symbols = self.assemble(output.read_text(), functions)
            if is_trap(cases[0].expected):
                check_trap(observed, cases[0].expected, symbols, cases[0].name)
            else:
                validate_case_values(observed, cases)
        except AssertionError as error:
            raise AssertionError(f"{error}\nReproduction source:\n{source}") from error

    def rejection(self, case):
        """Compile once; alternate calls also require an existing output to survive."""
        input_path = self.directory / "invalid.au"
        input_path.write_text(case.source)
        output = self.directory / "rejected.s"
        output.unlink(missing_ok=True)
        self.rejections = getattr(self, "rejections", 0) + 1
        existing = REJECTION_SENTINEL if self.rejections % 2 == 0 else None
        if existing is not None:
            output.write_bytes(existing)
        result = command(
            [self.compiler, "--module-root", LIBRARY, input_path, "-o", output],
            timeout=max(30, self.timeout),
            allow_rejection=True,
        )
        require(
            result.returncode == 1 and diagnostic_line(input_path).fullmatch(result.stderr.decode()) is not None,
            f"{case.name}: expected one compiler diagnostic, got {result.returncode}: {result.stderr!r}\n"
            f"Reproduction source:\n{case.source}",
        )
        require(input_path.read_text() == case.source, f"{case.name}: compiler modified input")
        if existing is None:
            require(not output.exists(), f"{case.name}: rejection created an artifact")
        else:
            require(output.read_bytes() == existing, f"{case.name}: rejection changed the existing output")
