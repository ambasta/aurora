#!/usr/bin/env python3
"""Host-only candidate verification; no emulator/device commands."""

from pathlib import Path
import argparse, hashlib, json, os, re, subprocess, sys, time

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("output", type=Path)
parser.add_argument("--privacy-only", action="store_true")
args = parser.parse_args()
OUT = args.output
OUT.mkdir(parents=True, exist_ok=False)
paths = [
    ROOT / p
    for p in [
        "kernel/pin-ledger.hpp",
        "kernel/pages.hpp",
        "kernel/domain-policy.hpp",
        "kernel/dormant-tables.hpp",
        "kernel/dormant-decoder.hpp",
        "kernel/uefi/dormant-inspector.hpp",
        "tests/kernel-dormant-tables.cpp",
        "tests/kernel-dormant-generation.cpp",
        "tests/kernel-dormant-api.cpp",
        "tests/kernel-dormant-decoder.cpp",
        "tests/amd310-translation-oracle.hpp",
        "tests/kernel-iommu-oracle.cpp",
        "tests/amd310-event-completion-oracle.hpp",
        "tests/kernel-iommu-event-completion.cpp",
        "tests/kernel-dormant-oracle.cpp",
        "scripts/kernel-dormant-tests.py",
    ]
]


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


before = {str(p.relative_to(ROOT)): digest(p) for p in paths}
(OUT / "inputs-before.json").write_text(json.dumps(before, indent=2) + "\n")
records = []


def run(name, argv, expected=0, env=None):
    start = time.time_ns()
    r = subprocess.run(argv, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120, env=env)
    (OUT / (name + ".log")).write_bytes(r.stdout)
    records.append(
        {
            "name": name,
            "argv": argv,
            "status": r.returncode,
            "expected": expected,
            "start_ns": start,
            "end_ns": time.time_ns(),
        }
    )
    (OUT / "commands.json").write_text(json.dumps(records, indent=2) + "\n")
    if r.returncode != expected:
        raise RuntimeError(f"{name}:unexpected status{r.returncode}")
    print(name, "PASS", flush=True)
    return r.stdout


flags = ["g++", "-std=c++23", "-O1", "-g", "-Wall", "-Wextra", "-Werror"]
san = ["-fsanitize=address,undefined", "-fno-sanitize-recover=all"]
env = os.environ.copy()
env["ASAN_OPTIONS"] = "detect_leaks=0"
run("compiler-version", ["g++", "--version"])
if not args.privacy_only:
    for name, source, extra in [
        ("ownership", "tests/kernel-dormant-tables.cpp", []),
        ("independent", "tests/kernel-dormant-decoder.cpp", []),
        ("translation-oracle", "tests/kernel-iommu-oracle.cpp", []),
        ("event-completion-oracle", "tests/kernel-iommu-event-completion.cpp", []),
        ("constructor-oracle", "tests/kernel-dormant-oracle.cpp", []),
        (
            "generation",
            "tests/kernel-dormant-generation.cpp",
            ["-DAURORA_PIN_LEDGER_TESTING=1", "-DAURORA_PIN_LEDGER_TEST_GENERATION_LIMIT=3"],
        ),
        ("production-api", "tests/kernel-dormant-api.cpp", []),
    ]:
        for suffix, options in [("-sanitized", san)] if os.environ.get("SANITIZE") == "1" else [("", [])]:
            binary = str(OUT / (name + suffix))
            run(name + suffix + "-compile", flags + options + extra + [source, "-o", binary])
            run(name + suffix + "-execute", [binary], env=env)
    for name, defs in [
        ("test-zero", ["-DAURORA_DORMANT_TABLE_TESTING=0"]),
        ("small-production-generation", ["-DAURORA_PIN_LEDGER_TEST_GENERATION_LIMIT=3"]),
        ("zero-generation", ["-DAURORA_PIN_LEDGER_TESTING=1", "-DAURORA_PIN_LEDGER_TEST_GENERATION_LIMIT=0"]),
        ("negative-generation", ["-DAURORA_PIN_LEDGER_TESTING=1", "-DAURORA_PIN_LEDGER_TEST_GENERATION_LIMIT=-1"]),
    ]:
        run(name, flags + defs + ["tests/kernel-dormant-api.cpp", "-o", str(OUT / name)], expected=1)
# Each isolated mutant must compile and fail its intended semantic fixture.
# No production mutation or additional test framework is involved.
if not args.privacy_only:
    oracle = (ROOT / "tests/amd310-translation-oracle.hpp").read_text()
    fixtures = (ROOT / "tests/kernel-iommu-oracle.cpp").read_bytes()
    mutations = [
        (
            "requester-bound",
            "if (request.requester >= entries)",
            "if (false && request.requester >= entries)",
            "declared size wins over excessive backing",
        ),
        (
            "upper-address",
            "if (request.address >= 2097152)",
            "if (false && request.address >= 2097152)",
            "upper address must not alias low leaf",
        ),
        (
            "leaf-presence",
            "if ((entry & 1) == 0)",
            "if (false && (entry & 1) == 0)",
            "PR clear ignores every payload bit",
        ),
        ("parent-read", "parent.read && leaf.read", "leaf.read", "parent and leaf cumulative rights"),
        ("parent-write", "parent.write && leaf.write", "leaf.write", "parent and leaf cumulative rights"),
        (
            "validity-bypass",
            "if ((control & 1) == 0)",
            "if (false && (control & 1) == 0)",
            "V zero ignores noncanonical fields and bypasses",
        ),
        (
            "translation-valid",
            "if ((control & 2) == 0)",
            "if (false && (control & 2) == 0)",
            "TV zero faults without interpreting mode root or rights",
        ),
        (
            "mode-zero-rights",
            "if (denied(parent, request.access))",
            "if (false && denied(parent, request.access))",
            "Mode zero enforces DTE rights",
        ),
        (
            "root-binding",
            "root_base != input.root_physical_base",
            "(false && root_base != input.root_physical_base)",
            "encoded root must match bounded backing",
        ),
        (
            "reserved-leaf",
            "if ((entry & 0x07f0000000000000ULL) != 0)",
            "if (false && (entry & 0x07f0000000000000ULL) != 0)",
            "present leaf reserved bit has defined RZ and request fields",
        ),
        (
            "ordinary-class",
            "if (special(request.address))",
            "if (false && special(request.address))",
            "special address never ordinary memory",
        ),
        (
            "fault-interrupt",
            "bool interrupt = false;",
            "bool interrupt = true;",
            "requester length precedes backing lookup",
        ),
        (
            "fault-domain",
            "result.domain = domain;",
            "result.domain = domain & 0;",
            "TV zero faults without interpreting mode root or rights",
        ),
    ]
    for name, original, replacement, marker in mutations:
        if oracle.count(original) != 1:
            raise RuntimeError("ambiguous oracle mutation: " + name)
        directory = OUT / ("oracle-mutant-" + name)
        directory.mkdir()
        (directory / "amd310-translation-oracle.hpp").write_text(oracle.replace(original, replacement, 1))
        source = directory / "kernel-iommu-oracle.cpp"
        source.write_bytes(fixtures)
        binary = directory / "mutant"
        options = san if os.environ.get("SANITIZE") == "1" else []
        run("oracle-mutant-" + name + "-compile", flags + options + [str(source), "-o", str(binary)])
        diagnostic = run("oracle-mutant-" + name + "-execute", [str(binary)], expected=1, env=env)
        if ("FAIL: " + marker).encode() not in diagnostic:
            raise RuntimeError("oracle mutant missed intended fixture: " + name)
        if not re.search(rb"FAIL [0-9]+ independent AMD310 translation checks; no device operation\n$", diagnostic):
            raise RuntimeError("oracle mutant did not reach its normal terminal: " + name)
        for fatal in (b"AddressSanitizer", b"UndefinedBehaviorSanitizer", b"LeakSanitizer", b"runtime error:"):
            if fatal in diagnostic:
                raise RuntimeError("oracle mutant encountered a sanitizer failure: " + name)
# Same host-only semantic-mutant contract for the independent event/completion model.
if not args.privacy_only:
    event_oracle = (ROOT / "tests/amd310-event-completion-oracle.hpp").read_text()
    event_fixtures = (ROOT / "tests/kernel-iommu-event-completion.cpp").read_bytes()
    event_mutations = [
        (
            "memory-i",
            "value.interrupt = (b & (1U << 19)) != 0;",
            "value.interrupt = (b & (1U << 19)) == 0;",
            "literal ordinary fault fields",
        ),
        (
            "domain",
            "value.domain = static_cast<std::uint16_t>(b);",
            "value.domain = static_cast<std::uint16_t>(b & 0);",
            "literal ordinary fault fields",
        ),
        (
            "definedness",
            "return !expected.has_value() || *expected == raw;",
            "return expected.value_or(false) == raw;",
            "unknown fault fields ignore raw payload",
        ),
        (
            "event-status",
            "inline constexpr std::uint64_t event_interrupt = 2;",
            "inline constexpr std::uint64_t event_interrupt = 4;",
            "ordinary event uses bit1 and advances only tail",
        ),
        (
            "tail",
            "ring.tail = next;",
            "ring.tail = next == 0 ? 0U : next - 16;",
            "ordinary event uses bit1 and advances only tail",
        ),
        (
            "fullness",
            "next == ring.head",
            "ring.tail == ring.head",
            "one unused slot detects full without tail advance",
        ),
        (
            "overflow",
            "!status.logging() || status.overflow() || next == ring.head",
            "!status.logging() || next == ring.head",
            "disabled or overflowed logging discards events",
        ),
        (
            "dte-order",
            "fetched_ < 2 || !device_cache_ || page_cache_",
            "fetched_ < 2 || page_cache_",
            "page invalidation waits for prior DTE cache invalidation",
        ),
        (
            "dte-not-pages",
            "device_cache_ = true;",
            "device_cache_ = true; page_cache_ = true;",
            "DTE invalidation does not invalidate pages",
        ),
        (
            "fetch-not-finish",
            "++fetched_;",
            "++fetched_; completed_ = fetched_ == 3;",
            "fetching wait never completes invalidation",
        ),
        (
            "read-drain",
            "|| !reads_ || !writes_",
            "|| !writes_",
            "read drain required before completion",
        ),
        (
            "write-drain",
            "|| !reads_ || !writes_",
            "|| !reads_",
            "write drain required before completion",
        ),
        ("store-s", "if (wait_.store)", "if (true)", "completion store requires s"),
        ("interrupt-i", "if (wait_.interrupt)", "if (true)", "completion interrupt requires i"),
        (
            "command-stop",
            "halted_ = true;",
            "halted_ = false;",
            "command error halts fetch even when logging is lost",
        ),
        (
            "fault-not-finish",
            "status_ = append->status;",
            "status_ = append->status; completed_ = true;",
            "ordinary fault and stale status never finish pending batch",
        ),
    ]
    for name, original, replacement, marker in event_mutations:
        if event_oracle.count(original) != 1:
            raise RuntimeError("ambiguous event/completion mutation: " + name)
        directory = OUT / ("event-mutant-" + name)
        directory.mkdir()
        (directory / "amd310-event-completion-oracle.hpp").write_text(event_oracle.replace(original, replacement, 1))
        (directory / "amd310-translation-oracle.hpp").write_bytes(
            (ROOT / "tests/amd310-translation-oracle.hpp").read_bytes()
        )
        source = directory / "kernel-iommu-event-completion.cpp"
        source.write_bytes(event_fixtures)
        binary = directory / "mutant"
        options = san if os.environ.get("SANITIZE") == "1" else []
        run("event-mutant-" + name + "-compile", flags + options + [str(source), "-o", str(binary)])
        diagnostic = run("event-mutant-" + name + "-execute", [str(binary)], expected=1, env=env)
        if ("FAIL: " + marker).encode() not in diagnostic:
            raise RuntimeError("event/completion mutant missed intended fixture: " + name)
        terminal = rb"FAIL [0-9]+ independent AMD310 event/completion checks; no device operation\n$"
        if not re.search(terminal, diagnostic):
            raise RuntimeError("event/completion mutant did not reach its normal terminal: " + name)
        for fatal in (b"AddressSanitizer", b"UndefinedBehaviorSanitizer", b"LeakSanitizer", b"runtime error:"):
            if fatal in diagnostic:
                raise RuntimeError("event/completion mutant encountered a sanitizer failure: " + name)
# Identical, well-formed member-pointer expressions are compiled against the
# real private class and an isolated mutation with the same region public.
# The positive mutation prevents unrelated syntax/type errors from passing.
public_dir = OUT / "public-control"
public_dir.mkdir()
for header in [
    ROOT / "kernel" / name for name in ["pin-ledger.hpp", "pages.hpp", "domain-policy.hpp", "dormant-tables.hpp"]
]:
    data = header.read_bytes()
    if header.name == "dormant-tables.hpp":
        needle = b"class DormantTables final {\n"
        if data.count(needle) != 1:
            raise RuntimeError("ambiguous privacy mutation")
        data = data.replace(needle, needle + b"public:\n", 1)
    (public_dir / header.name).write_bytes(data)
privacy_env = env.copy()
privacy_env["LC_ALL"] = "C"
for member in ["pages_", "arena_", "groups_", "dte_word", "page", "put"]:
    source = OUT / ("access-" + member + ".cpp")
    source.write_text(
        '#include "dormant-tables.hpp"\nauto expose() { return &aurora::memory::DormantTables::' + member + "; }\n"
    )
    common = [str(source), "-c", "-o", str(OUT / ("access-" + member + ".o"))]
    run("public-control-" + member, flags + ["-I" + str(public_dir)] + common, env=privacy_env)
    diagnostic = run("private-" + member, flags + ["-I" + str(ROOT / "kernel")] + common, expected=1, env=privacy_env)
    if b"private within this context" not in diagnostic:
        raise RuntimeError("missing access-control diagnostic:" + member)
probe = OUT / "ordinary-header.cpp"
probe.write_text('#include "' + str(ROOT / "kernel/dormant-tables.hpp") + '"\n')
preprocessed = run("production-inspector-absent", flags + ["-E", "-P", str(probe)])
if b"DormantTableTestAccess" in preprocessed:
    raise RuntimeError("Inspector declaration present in ordinary header")
probe = OUT / "ordinary-inspector.cpp"
probe.write_text('#include "' + str(ROOT / "kernel/uefi/dormant-inspector.hpp") + '"\n')
diagnostic = run("production-inspector-rejected", flags + [str(probe), "-fsyntax-only"], expected=1)
if b"Dormant table inspector is restricted to explicit CPU-only test images" not in diagnostic:
    raise RuntimeError("Inspector rejected for wrong reason")
after = {str(p.relative_to(ROOT)): digest(p) for p in paths}
(OUT / "inputs-after.json").write_text(json.dumps(after, indent=2) + "\n")
if before != after:
    raise RuntimeError("candidate source changed during tests")
summary = {
    "scope": "CPU-only dormant tables and independent translation/event/completion oracles; no hardware operation",
    "privacy_only": args.privacy_only,
    "commands": len(records),
    "all_expected_statuses": True,
    "inputs_unchanged": True,
    "receipts": {p.name: digest(p) for p in sorted(OUT.iterdir()) if p.is_file()},
}
(OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
print("PASS all host-only candidate gates", flush=True)
