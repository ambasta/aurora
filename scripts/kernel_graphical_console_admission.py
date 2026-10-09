#!/usr/bin/env python3
"""Exact combined graphical Console admission; no inherited image qualification.

Capture contracts bind the observed numeric capture002 linked forms. Unknown
forms fail closed. Successful emit is evidence for independent review, never review.
"""

from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build/uefi"
RECEIPT = BUILD / "graphical-console-admission.json"
MODES = ("graphical-console", "graphical-console-capture")
ENTRY = "__au_v_m1_24kernel_graphical_console_n0__d17graphical_console"
REFLECTION_HELPERS = frozenset(("aurora_reflect_size", "aurora_reflect_field_count"))
BRIDGE = "__au_runtime_graphical_entry"
VALUE_BRIDGE = "__au_runtime_graphical_value"
VALUE_ENTRY = "aurora_kernel_value"
TOOLS = ("as", "ld", "objcopy", "objdump", "nm", "readelf", "c++filt", "python3")
HOST_IMPORTS = frozenset(("__au_runtime_console_next", "__au_runtime_console_put", "__au_runtime_display_pixel"))
CPP_OBJECTS = ("payload", "acpi", "pci", "runtime", "graphical-console")
ASSEMBLY_OBJECTS = ("payload-entry", "console-entry", "language", "memory")
BASE_FLAGS = tuple(
    (
        "-std=c++23 -O2 -fstack-usage -fcallgraph-info=su -Wall -Wextra -Werror -ffreestanding -fcf-protection=none -mstringop-strategy=libcall "
        "-fno-exceptions -fno-rtti -fno-stack-protector -fno-asynchronous-unwind-tables "
        "-fno-unwind-tables -mno-red-zone -mgeneral-regs-only -fno-tree-loop-distribute-patterns"
    ).split()
)
PROFILE_FLAGS = ("-DAURORA_UEFI_ACPI", "-DAURORA_UEFI_GRAPHICAL_CONSOLE", "-DAURORA_UEFI_GRAPHICAL_FIXTURE")
TU_FLAGS = {
    "payload/acpi/pci/graphical-console": ["-fpie", "-fvisibility=hidden"],
    "runtime": ["-fpie", "-fvisibility=hidden", "-Ibuild/uefi"],
    "loader": ["-fpie", "-maccumulate-outgoing-args", "-Ibuild/uefi"],
}


def need(value, reason):
    if not value:
        raise ValueError(reason)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


common = load("graphical_common", ROOT / "scripts/kernel_program_console_admission.py")
console = load("graphical_console_controls", ROOT / "scripts/kernel_console_service_admission.py")
digest = common.digest
verify_irq_body = console.verify_irq_body
verify_irq_reachability = console.verify_irq_reachability
verify_stack_budgets = console.verify_stack_budgets


BUILD_KEYS = {
    "schema",
    "mode",
    "flags",
    "source_sha256",
    "compiler",
    "cxx",
    "tools",
    "pe_linker",
    "translation_unit_flags",
    "objects",
}


def source_files():
    return sorted(
        set(common.source_files())
        | {
            ROOT / "compiler/Makefile",
            ROOT / "meson.build",
            ROOT / "tests/meson.build",
            ROOT / "tests/compiler-test-inventory.json",
        }
    )


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def read_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            need(key not in result, "Duplicate JSON key: " + key)
            result[key] = value
        return result

    return json.loads(
        path.read_text(),
        object_pairs_hook=unique,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError("Non-finite JSON: " + value)),
    )


# These are SOURCE contracts, never synthetic replacements for emitted code.
# The native overlay implements the independently reviewed closed fixture plan.
# Freeze complete token streams, plus each conditional region and its insertion
# point, so a matching fragment cannot hide a second writer or bypassing path.
# Whitespace/comments are irrelevant; strings, operators and all other tokens
# remain exact. All three Session headers are unchanged reviewed dependencies.
CAPTURE_NATIVE = "kernel/uefi/graphical-console.cpp"
CAPTURE_POLICY = "kernel/uefi/graphical-capture-policy.hpp"
CAPTURE_SOURCE_PINS = {
    CAPTURE_POLICY: "d243cfdd14409fdbbe6803662378c12e9ff17f72734c4702e9f24b158cd53611",
    "kernel/graphical-session.hpp": "27ef0622f075054ab3062148e332b66d68d3e37dc4801e3ff0b7be279b61d79f",
    "kernel/console-session.hpp": "8dcf227c5283735ffa02bc41f40509f907a980f56877189cb04d345b082af21f",
    "kernel/display-session.hpp": "a087a8e34438ff75c373b7015133db274c18ddd8f5a8c92b750f20893bd9117d",
}
CAPTURE_REGIONS = (
    ("policy include", "ifdef", 3, "864f5fcd25a82700a95438723b30f9e7e3302661c8f1b58e32503c18adb94f01"),
    ("private state", "ifdef", 143, "594d1f1292f5a429620ca1e3eb9a6da93deb0634a375da90b5277660d1c1aea7"),
    ("failure diagnostics", "ifdef", 456, "acc794c0ac7709b2ad4c2a39aa63952b39596e619723bcdc680c3b069706da44"),
    ("production fail exit", "ifndef", 463, "77105a271a56baed767bd387c269f99d8f181029b6950b226932a84ac3be933a"),
    ("selector gate and sole writer", "ifdef", 907, "99e40589f9d9a15e42b20e22bc37602409112fbac244f92e2b3b5420323ee19a"),
    ("admitted pixel failure", "ifdef", 1246, "7be663f9d39f01990c9850ffcfb75374736911348fb84bc9cd94329852f0eb78"),
    ("pre-sample diagnostics", "ifdef", 1847, "ddf0a795439653c175b4e86475c001392cec7056510d2ff1a1019be3064878c8"),
    ("pre-grant gate call", "ifdef", 2930, "f8ad783a0ef5ac8964306cfa7eb8b44fe293e471a247cf6049fb7a463714477c"),
    ("local record and real reopen", "ifdef", 3047, "f2f7d5c3a0806f8b88198e1b99d88942984c81ff1b1b037859ba98f7ca1dab42"),
    ("completion diagnostics", "ifdef", 3273, "b7be54c1a7e28646f80d7ffa8ff17fbc102407f256413d1956572d5da7b8da72"),
    ("production completion exit", "ifndef", 3280, "5b0af10a4420bb529ad54f0ea52302a493b18c1b59b2666d3ca098fb1e3b9d22"),
)
CAPTURE_SELECTORS = {
    "G": "normal",
    "C": "cross-console",
    "D": "cross-display",
    "c": "stale-console",
    "d": "stale-display",
    "F": "first-pixel-error",
    "I": "interior-pixel-error",
}
CAPTURE_SELECTOR_CODES = {"G": 1, "C": 2, "D": 3, "c": 4, "d": 5, "F": 6, "I": 7}
CAPTURE_LINKED_REQUIREMENTS = (
    "closed selector decode, sole scenario writer and release ordering",
    "local six-word record mutations and genuine Session close/reopen generations",
    "trusted-record identity and both preflights dominate the sole compiled entry",
    "pixel admission dominates one checked attempt increment and fixed 0/55 failure before store",
    "exact failure/completion diagnostics and successful-store accounting",
    "actual object/link bytes, relocations, frames and unchanged generated language/bridge bytes",
)
CAPTURE_ONLY_TOKENS = tuple(
    text.encode()
    for text in (
        "graphical_capture",
        "capture_scenario",
        "capture_gate",
        "pixel_attempts",
        "AURORA_GRAPHICAL_CAPTURE_GATE:",
        "AURORA_GRAPHICAL_CAPTURE_RELEASED",
        "AURORA_GRAPHICAL_PRE_SAMPLE:",
        "capture initial state",
        "capture UART status",
        "capture selector",
        "capture release deadline",
        "pixel attempt counter overflow",
        "cross-console",
        "cross-display",
        "stale-console",
        "stale-display",
        "first-pixel-error",
        "interior-pixel-error",
    )
)
CAPTURE_ARTIFACTS = ("payload.elf", "payload.bin", "esp/EFI/BOOT/BOOTX64.EFI") + tuple(
    name + ".o"
    for name in CPP_OBJECTS
    + ASSEMBLY_OBJECTS
    + ("loader", "embed", "transition", "loader-pe", "embed-pe", "transition-pe", "memory-pe")
)
CPP_SOURCE_TOKEN = re.compile(
    r'//[^\n]*|/\*[\s\S]*?\*/|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|'
    r"[A-Za-z_]\w*|0[xX][0-9A-Fa-f]+[uUlL]*|[0-9]+[uUlL]*|"
    r"::|->|\+\+|--|==|!=|<=|>=|&&|\|\||<<|>>|\+=|-=|\*=|/=|%=|&=|\|=|\^=|[^\s]"
)


def capture_source_tokens(text):
    need(not re.search(r"\\\r?\n|\?\?/", text), "Unreviewed capture source line splicing")
    return [row.group() for row in CPP_SOURCE_TOKEN.finditer(text) if not row.group().startswith(("//", "/*"))]


def capture_source_digest(text):
    return hashlib.sha256(canonical(capture_source_tokens(text)).encode()).hexdigest()


def capture_source_projection(text):
    """Only the actual closed profile directives, not a general preprocessor."""
    production, capture, regions, region = "", "", [], None
    for line in text.splitlines(keepends=True):
        directive = line.strip()
        if directive in ("#ifdef AURORA_UEFI_GRAPHICAL_CAPTURE", "#ifndef AURORA_UEFI_GRAPHICAL_CAPTURE"):
            need(region is None, "Nested capture source condition")
            region = [directive.split()[0][1:], "", len(capture_source_tokens(production))]
        elif directive == "#endif":
            need(region is not None, "Unmatched capture source condition")
            kind, body, position = region
            regions.append((kind, position, capture_source_digest(body)))
            if kind == "ifndef":
                production += body
            else:
                capture += body
            region = None
        else:
            need(not directive.startswith("#") or directive.startswith("#include "), "Unreviewed source directive")
            if region is not None:
                region[1] += line
            else:
                production += line
                capture += line
    need(region is None, "Unclosed capture source condition")
    return production, capture, regions


def capture_source_evidence(mode, sources=None):
    need(mode in MODES, "Unknown graphical profile")
    paths = {CAPTURE_NATIVE, *CAPTURE_SOURCE_PINS}
    if sources is None:
        sources = {name: (ROOT / name).read_text() for name in paths}
    need(set(sources) == paths, "Changed capture source dependency inventory")
    for name, expected in CAPTURE_SOURCE_PINS.items():
        need(capture_source_digest(sources[name]) == expected, "Unreviewed capture source dependency: " + name)
    production, capture, regions = capture_source_projection(sources[CAPTURE_NATIVE])
    need(len(regions) == len(CAPTURE_REGIONS), "Changed capture conditional region inventory")
    for actual, (name, kind, position, expected) in zip(regions, CAPTURE_REGIONS):
        need(actual == (kind, position, expected), "Changed capture source region/position: " + name)
    need(
        capture_source_digest(production) == "1e85afab1304e327bbf9dbce2677e1665ee7059ebdafffaef8a9fa15f3472066",
        "Changed ordinary graphical source projection",
    )
    need(
        capture_source_digest(capture) == "452260bade4db427f3d07ee0c38fe1ff52931d6467895bda59dec42cfd01a809",
        "Changed complete capture graphical source projection",
    )
    return dict(
        schema="aurora-graphical-capture-source-v2",
        mode=mode,
        status="source-contract-only",
        source_sha256={name: hashlib.sha256(sources[name].encode()).hexdigest() for name in sorted(sources)},
        selectors=dict(CAPTURE_SELECTORS) if mode == MODES[1] else {},
        release=(
            dict(prefix="AURORA_GRAPHICAL_CAPTURE_RELEASED: selector=", codes=dict(CAPTURE_SELECTOR_CODES), invalid=0)
            if mode == MODES[1]
            else None
        ),
        invalid_selectors=249 if mode == MODES[1] else 0,
        failure_successful_store_ordinals=[0, 55] if mode == MODES[1] else [],
        regions=[name for name, *_ in CAPTURE_REGIONS],
        remaining_linked_proofs=list(CAPTURE_LINKED_REQUIREMENTS)
        if mode == MODES[1]
        else ["production fixture absence"],
    )


def capture_artifact_evidence(mode, artifacts):
    """Presence/ownership is necessary; it cannot establish capture semantics."""
    need(mode in MODES, "Unknown graphical profile")
    need(set(artifacts) == set(CAPTURE_ARTIFACTS), "Changed fixture artifact inventory")
    embedded = {"payload.elf", "payload.bin", "esp/EFI/BOOT/BOOTX64.EFI", "embed.o", "embed-pe.o"}
    found, hashes = {}, {}
    for name, fields in artifacts.items():
        need(set(fields) == {"contents", "symbols", "relocations"}, "Changed fixture artifact evidence fields")
        hashes[name] = {}
        for field, value in fields.items():
            need(type(value) is bytes, "Fixture artifact evidence must retain original bytes")
            hashes[name][field] = hashlib.sha256(value).hexdigest()
            tokens = [token.decode() for token in CAPTURE_ONLY_TOKENS if token in value]
            if tokens:
                need(
                    mode == MODES[1], "Capture fixture leaked into production: " + name + ":" + field + ": " + tokens[0]
                )
                need(
                    name == "graphical-console.o" or name in embedded,
                    "Capture fixture has foreign ownership: " + name + ":" + field,
                )
                found[name + ":" + field] = tokens
    if mode == MODES[1]:
        owner = artifacts["graphical-console.o"]
        need(
            all(token in owner["symbols"] for token in (b"capture_scenario", b"pixel_attempts"))
            and b"AURORA_GRAPHICAL_CAPTURE_RELEASED: selector=" in owner["contents"],
            "Missing capture fixture state or exact release diagnostic",
        )
    return dict(
        mode=mode,
        status="requires-actual-linked-fixture-proof" if mode == MODES[1] else "fixture-absent",
        fixture_tokens=found,
        artifact_sha256=hashes,
    )


def require_capture_linked_proof(mode, evidence=None, build=None):
    need(mode in MODES, "Unknown graphical profile")
    if mode == MODES[0]:
        need(evidence is None, "Production cannot carry capture linked proof")
        return
    # emit/checked supply only their freshly recomputed stack proof, after all
    # source/output provenance, object association and ordinary safety guards.
    # Close the complete independently reviewed proof object, including exact
    # files/bodies, selector, authority, pixel and diagnostic facts. A source
    # contract, artifact-presence record or external receipt pin cannot replace it.
    need(
        type(evidence) is dict
        and hashlib.sha256(canonical(evidence).encode()).hexdigest()
        in {
            "c060811e6e5afabe3527685dfc87905d56ef319ef0caaade1f93063cb1565af2",
            "3d6ae7af3fc62adf5c78861ce0d5d28ed6feb87f4ea7744b097fa534cfc106c2",
        },
        "Capture fixture linked proof pending: missing or changed complete reviewed proof",
    )
    if evidence["files"] == CAPTURE_LIBCALL_FILE_CONTRACTS:
        verify_capture_libcall_applicability(build)


def unreviewed_linked_function(symbol, original_code, payload, error):
    """Retain unknown emission as a precise blocker, never a neutral opcode."""
    reason = str(error)
    rows = [
        row
        for address, row in sorted(original_code.items())
        if symbol.address <= address < symbol.address + symbol.size
    ]
    if reason.startswith("Unknown instruction semantics: "):
        rows = [row for row in rows if row.op == reason.removeprefix("Unknown instruction semantics: ")]
    elif reason.startswith("Unbounded or unknown stack adjustment: "):
        rows = [row for row in rows if row.args == reason.removeprefix("Unbounded or unknown stack adjustment: ")]
    evidence = [
        dict(
            address=row.address,
            bytes=payload[row.address : row.address + row.size].hex(),
            operation=row.op,
            operands=row.args,
        )
        for row in rows
    ]
    return (
        symbol.name
        + ": "
        + reason
        + "; call/stack effect remains unproved; original linked instructions="
        + canonical(evidence)
    )


# Numeric capture002, retained after its deliberate linked-proof rejection.
# This is an address-specific emitted-form contract for the exact compiler tuple,
# not a relocation/opcode allowance. Whole original instructions (including
# padding), data, ELF, object relocations and .su bytes remain closed. Semantic
# checks below additionally establish the reviewed fixture behavior.
CAPTURE_RUN = "_ZN6aurora4uefi21run_graphical_consoleEmRKNS0_5BytesE"
CAPTURE_CONSOLE = "_ZN6aurora7console7SessionINS_4uefi12_GLOBAL__N_116ServiceTransportENS3_15ServicePlatformEE"
CAPTURE_DISPLAY = "_ZN6aurora7display7SessionINS_4uefi12_GLOBAL__N_116DisplayTransportENS3_15ServicePlatformEE"
CAPTURE_FAIL = "_ZN6aurora4uefi12_GLOBAL__N_14failESt17basic_string_viewIcSt11char_traitsIcEE"
CAPTURE_PLATFORM_FAIL = "_ZN6aurora4uefi12_GLOBAL__N_115ServicePlatform4failEv"
CAPTURE_MACHINE_CONTRACTS = {
    "_ZN6aurora4uefi12_GLOBAL__N_113timer_mappingEv": (
        0x3700,
        159,
        37,
        "6e11125735e34ef0701183d2f3427d918f1deaf74f8d429399076b9dca9ee844",
    ),
    "_ZN6aurora4uefi12_GLOBAL__N_15quietEv": (
        0x37A0,
        181,
        54,
        "5a6c682866e2e24bb00c865af3f534ec79cefdd6ae49cf1bec2eb28d616a9054",
    ),
    "_ZN6aurora4uefi12_GLOBAL__N_14failESt17basic_string_viewIcSt11char_traitsIcEE": (
        0x3860,
        302,
        61,
        "3bfeefb04473b7ce5caff2baa1dc0e4217751355e52019627b2975d46e45d800",
    ),
    "_ZN6aurora4uefi12_GLOBAL__N_115ServicePlatform4failEv": (
        0x3990,
        21,
        4,
        "952742cd535c11523a1e81074e161cf17d8137d15d0d43729f5119ef477e255a",
    ),
    "_ZN6aurora7console7SessionINS_4uefi12_GLOBAL__N_116ServiceTransportENS3_15ServicePlatformEE8validateEPKvmb": (
        0x39B0,
        81,
        23,
        "b69073216128440c8318c71ceadd8dc5abcbd199b7713c0178c085c3587ea798",
    ),
    "_ZN6aurora7console7SessionINS_4uefi12_GLOBAL__N_116ServiceTransportENS3_15ServicePlatformEE4openEv": (
        0x3A10,
        105,
        23,
        "3461a6904be113d664558b24ce7c6955a7bcee6a5193ded964179e918874b219",
    ),
    "_ZN6aurora7display7SessionINS_4uefi12_GLOBAL__N_116DisplayTransportENS3_15ServicePlatformEE8validateEPKvmb": (
        0x3A80,
        126,
        35,
        "278a6028ec82948ebc7931d97f219357170100bc09599afdb379d1426d11ae3e",
    ),
    "_ZN6aurora7display7SessionINS_4uefi12_GLOBAL__N_116DisplayTransportENS3_15ServicePlatformEE4openEv": (
        0x3B00,
        215,
        47,
        "577e3fb7f7c0115e7c7ca631c8819eb33ccba165667cf2453120a44adb5fb8b4",
    ),
    "__au_runtime_console_put": (0x4320, 413, 95, "06290d07df8509d8fba603080304993ca2ac50707945a9f75bc766f2e5745f55"),
    "_ZN6aurora4uefi21run_graphical_consoleEmRKNS0_5BytesE": (
        0x4E20,
        4599,
        934,
        "7e3f6ba5a613342d796ab7a07c05a405c9e37b532b5b5371df55185e04c2b134",
    ),
    "__au_runtime_console_next": (
        0x44C0,
        1586,
        375,
        "3c451c00820806e0448867cc60a43df32e0c4529484dc27a960d10849f314cc5",
    ),
    "__au_runtime_display_pixel": (
        0x3BE0,
        1223,
        250,
        "6fb76fb5d6e35c967e0ce59c12fb1a5cce2dd0389b517056dddd299519917e29",
    ),
    "_ZN6aurora7console4UartINS_8hardware2IoELNS0_11FifoTriggerE192EE6numberEm": (
        0x7B00,
        219,
        57,
        "5ee41bf219caf5629e8b8439568b32d2d1d3a553e695c5c4b9345b6c382fce3f",
    ),
    (
        "_ZN6aurora7console4UartINS_8hardware2IoELNS0_11FifoTriggerE192EE4textE"
        "St17basic_string_viewIcSt11char_traitsIcEE"
    ): (
        0x7A90,
        104,
        36,
        "65ecfaa7aad5e6998f062a24fbe619478d7e88ae1885e28365ff54914056ea4d",
    ),
}
CAPTURE_FILE_CONTRACTS = {
    "payload.bin": "b07c591fa80dccbc9b34ea2037f720850ccb6e0d5ad33f7f8deeb891a0266d35",
    "payload.elf": "8f575ff00dbc15b346aa024e38f0153f2288253afdb6dbb61e84e9b4849c9cd3",
    "graphical-console.o": "72c43139c2c56d7ff207938b1d6ed849df2c2cca0746fae8aec82259882d18fb",
    "graphical-console.su": "67dcdd6fbc51d1f72c32346764fadd7dccb1852c70ec2a9f8292793a9f1abd7e",
    "language.o": "b079cf859050110b5a6a891be36433819cdf0bd93886968bc4f0a0bf08e63bd8",
    "language.s": "e554e294ee0d9c91542b70c79c2907974ae69ee27f4076f562e7b3bbfb279c5d",
}
# Reviewed checkpoint007 GCC14 libcall emission. This second complete tuple
# preserves the original numeric002 tuple; no per-file mix-and-match is allowed.
# The14 capture bodies/state/data are unchanged. Four outer object bodies change;
# their fresh complete stack/IRQ/wait admission remains mandatory before emit.
CAPTURE_LIBCALL_FILE_CONTRACTS = {
    "graphical-console.o": "b40c5548dc03ba52680f850a003253f0acf080704d65a656c75a68c27f38e8f5",
    "graphical-console.su": "67dcdd6fbc51d1f72c32346764fadd7dccb1852c70ec2a9f8292793a9f1abd7e",
    "language.o": "b079cf859050110b5a6a891be36433819cdf0bd93886968bc4f0a0bf08e63bd8",
    "language.s": "e554e294ee0d9c91542b70c79c2907974ae69ee27f4076f562e7b3bbfb279c5d",
    "payload.bin": "d266113c87fb779e2876705c3734dd18c3d24ba1ebd4d97527ef276a898aec10",
    "payload.elf": "ee5cb6084521a84cc00c7d513cf23f3b2443ce55e698edfa1ccd1b1314ddf8d1"
}
CAPTURE_LIBCALL_TOOL_SHA256 = {
    "as": "07dd8551ea0aa065975e4dddb8e1bb7dc308d12d54eca22c3858db79467c7cb9",
    "c++filt": "7d54ea6797a5e8c69255f711b79577efd9934c3502c6edee4bc25b7dc7d97bd2",
    "compiler": "b741da52f8b77ad8b1b14710c1595ad1bf86f8d9efe2a63bb00d849be02f3dcc",
    "cxx": "6b3696e4dcb85e1c949c732a02befa50e3983ecf94ce7e8e58d9d503b954b79d",
    "ld": "d2766988b6a1b1d1518cdc09242e726d1f24e151e16410ada3092b11ffd9081b",
    "nm": "ddb55c0685721bf494aa2d090056b8b32a40614ad4464b305896f527d882c3c1",
    "objcopy": "403f90bbd5d26c8ab9a2ad51f56255b812e8858a83aa8740ee71791071ddb580",
    "objdump": "96afb8521834982d0e711b5d6e9785252bf82129fb0106b93a6bd54d83fae11f",
    "pe_linker": "d2766988b6a1b1d1518cdc09242e726d1f24e151e16410ada3092b11ffd9081b",
    "python3": "fa67443527ed9647f760d807e2a38f26340757123e643c4639cf273ed15d5ea7",
    "readelf": "4a387d80a70e6e97ef940a666fab59d5c38e7cf19ff907192fa983cb8505a7de"
}
CAPTURE_LIBCALL_SOURCE_SHA256 = "0bc17d08d9eb2eb3267ad6f1613c5e5eaa933254db5377737548b4f6984e16b8"


def capture_file_contract(files):
    need(type(files) is dict, "Changed exact capture object/relocation/frame/language/image bytes")
    for contract in (CAPTURE_FILE_CONTRACTS, CAPTURE_LIBCALL_FILE_CONTRACTS):
        if files == contract:
            return contract
    raise ValueError("Changed exact capture object/relocation/frame/language/image bytes")


def verify_capture_libcall_applicability(build):
    need(type(build) is dict, "Missing exact capture libcall build applicability")
    need(build.get("mode") == MODES[1] and build.get("flags") == expected_flags(MODES[1]),
         "Changed capture libcall mode/flags")
    need(type(build.get("tools")) is dict, "Missing capture libcall tool identities")
    for name, expected in CAPTURE_LIBCALL_TOOL_SHA256.items():
        item = build.get(name) if name in ("compiler", "cxx", "pe_linker") else build["tools"].get(name)
        need(type(item) is dict and item.get("sha256") == expected, "Changed capture libcall tool: " + name)
    source = build.get("source_sha256")
    need(type(source) is dict and all(type(name) is str for name in source), "Missing capture libcall source identity")
    compiled = {
        name: value for name, value in source.items()
        if name.startswith(("compiler/", "kernel/", "library/", "examples/"))
        and Path(name).suffix in (".cpp", ".hpp", ".S", ".au", ".ld", ".lds")
    }
    need(hashlib.sha256(canonical(compiled).encode()).hexdigest() == CAPTURE_LIBCALL_SOURCE_SHA256,
         "Changed capture libcall compiled-source closure")


CAPTURE_STATE_CONTRACTS = {
    "_ZN6aurora4uefi12_GLOBAL__N_116consumer_entriesE": (0x101E8, 8, 3, 1),
    "_ZN6aurora4uefi12_GLOBAL__N_112sample_callsE": (0x101E0, 8, 3, 1),
    "_ZN6aurora4uefi12_GLOBAL__N_115output_attemptsE": (0x101D8, 8, 3, 1),
    "_ZN6aurora4uefi12_GLOBAL__N_16storesE": (0x101F8, 8, 3, 1),
    "_ZN6aurora4uefi12_GLOBAL__N_117completed_samplesE": (0x101D0, 8, 3, 1),
    "_ZN6aurora4uefi12_GLOBAL__N_15wakesE": (0x10210, 8, 3, 1),
    "_ZN6aurora4uefi12_GLOBAL__N_114pixel_attemptsE": (0x101C0, 8, 3, 1),
    "_ZN6aurora7console7SessionINS_4uefi12_GLOBAL__N_116ServiceTransportENS3_15ServicePlatformEE6grant_E": (
        0x10140,
        24,
        3,
        1,
    ),
    "_ZN6aurora7console7SessionINS_4uefi12_GLOBAL__N_116ServiceTransportENS3_15ServicePlatformEE11generation_E": (
        0x10130,
        8,
        3,
        1,
    ),
    "_ZN6aurora7display7SessionINS_4uefi12_GLOBAL__N_116DisplayTransportENS3_15ServicePlatformEE6grant_E": (
        0x10100,
        48,
        3,
        1,
    ),
    "_ZN6aurora7display7SessionINS_4uefi12_GLOBAL__N_116DisplayTransportENS3_15ServicePlatformEE11generation_E": (
        0x100E8,
        8,
        3,
        1,
    ),
    "_ZN6aurora4uefi12_GLOBAL__N_116active_operationE": (0x101F0, 4, 3, 1),
    "_ZN6aurora4uefi12_GLOBAL__N_116capture_scenarioE": (0x101C8, 1, 3, 1),
    (
        "_ZN6aurora9graphical5EntryINS_7console7SessionINS_4uefi12_GLOBAL__N_116ServiceTransportENS5_15ServicePlatform"
        "EEENS_7display7SessionINS5_16DisplayTransportES7_EES7_E7active_E"
    ): (
        0x100E0,
        1,
        3,
        1,
    ),
}


def capture_rip_target(row, payload):
    matches = list(re.finditer(r"(-?0x[0-9a-f]+)\(%rip\)", row.args))
    need(len(matches) == 1, "Capture RIP operand is not one exact displacement")
    displacement = int(matches[0][1], 16)
    encoded = struct.pack("<i", displacement)
    raw = payload[row.address : row.next]
    need(len(raw) == row.size and raw.count(encoded) == 1, "Capture RIP bytes/operand disagree")
    return row.next + displacement


def capture_cfg(decoder, symbol, code):
    rows = paired_rows(symbol, code)
    addresses = {row.address for row in rows}
    successors, predecessors = {}, {address: set() for address in addresses}
    for row in rows:
        edges = set()
        if row.op in decoder.BRANCHES:
            target = decoder.target_of(row)  # No indirect transfer exception.
            need(target in addresses, "Capture branch leaves its exact function")
            edges.add(target)
        terminal = row.op in ("ret", "ud2", "jmp")
        if row.op == "call":
            target = decoder.target_of(row)
            terminal = target in (0x3860, 0x3990)
        if not terminal and row.next in addresses:
            edges.add(row.next)
        successors[row.address] = edges
        for target in edges:
            predecessors[target].add(row.address)
    reachable, pending = set(), [symbol.address]
    while pending:
        address = pending.pop()
        if address not in reachable:
            reachable.add(address)
            pending.extend(successors[address])
    dominators = {address: ({address} if address == symbol.address else set(reachable)) for address in reachable}
    changed = True
    while changed:
        changed = False
        for address in sorted(reachable - {symbol.address}):
            incoming = predecessors[address] & reachable
            need(incoming, "Capture reachable block lacks a predecessor")
            value = {address} | set.intersection(*(dominators[parent] for parent in incoming))
            if value != dominators[address]:
                dominators[address], changed = value, True
    return successors, dominators


def capture_expect(code, expected):
    for address, operation in expected.items():
        row = code.get(address)
        need(
            row is not None and (row.op, row.args) == operation, "Changed capture semantic instruction: " + hex(address)
        )


def capture_call(decoder, code, address, target):
    row = code.get(address)
    need(
        row is not None and row.op == "call" and decoder.target_of(row) == target,
        "Changed capture semantic callee: " + hex(address),
    )


def capture_readonly(linked, address, count):
    need(
        any(
            section[1] == 1
            and section[2] & 2
            and not section[2] & 5
            and section[3] <= address
            and address + count <= section[3] + section[5]
            for section in linked.sections
        ),
        "Capture selector/diagnostic data is not in allocated read-only storage",
    )


def capture_direct_writers(decoder, code, payload, target, count):
    result = []
    readonly = {"cmp", "cmpb", "cmpl", "cmpq", "cmpw", "test", "testb", "testl", "testw", "bt", "lea"}
    for row in code.values():
        args = decoder.arguments(row.args)
        if row.op in readonly or not args or "%rip" not in args[-1]:
            continue
        address = capture_rip_target(row, payload)
        if address >= target + count or address + 8 <= target:
            continue
        width = paired_width(row, args)
        if address < target + count and target < address + width:
            result.append(row.address)
    return sorted(result)


def capture_selector_proof(decoder, linked, code, payload):
    capture_expect(
        code,
        {
            0x53B3: ("mov", "$0x989680,%ecx"),
            0x53B8: ("mov", "$0x3fd,%edx"),
            0x53C0: ("pause", ""),
            0x53C2: ("sub", "$0x1,%ecx"),
            0x53CB: ("in", "(%dx),%al"),
            0x53CC: ("test", "$0x1e,%al"),
            0x53D4: ("test", "$0x1,%al"),
            0x53D8: ("mov", "$0x3f8,%edx"),
            0x53DD: ("in", "(%dx),%al"),
            0x53DE: ("sub", "$0x43,%eax"),
            0x53E1: ("cmp", "$0x21,%al"),
            0x53F6: ("movzbl", "%al,%eax"),
            0x5400: ("movzbl", "(%rdx,%rax,1),%ebx"),
            0x5404: ("test", "%bl,%bl"),
            0x541F: ("movzbl", "%bl,%edi"),
        },
    )
    for address, operation, target in (
        (0x53C5, "je", 0x545C),
        (0x53CE, "jne", 0x57EB),
        (0x53D6, "je", 0x53C0),
        (0x53E3, "jbe", 0x53F6),
        (0x5406, "je", 0x53E5),
    ):
        need(
            code[address].op == operation and decoder.target_of(code[address]) == target,
            "Changed closed capture selector rejection edge",
        )
    need(
        code[0x53F9].op == "lea"
        and code[0x53F9].args.endswith(",%rdx")
        and capture_rip_target(code[0x53F9], payload) == 0xE8A0,
        "Changed capture byte table address",
    )
    capture_readonly(linked, 0xE8A0, 34)
    table = payload[0xE8A0:0xE8C2]
    expected = {ord("G"): 1, ord("C"): 2, ord("D"): 3, ord("c"): 4, ord("d"): 5, ord("F"): 6, ord("I"): 7}
    decoded = {}
    for byte in range(256):
        index = (byte - 0x43) & 255
        selected = table[index] if index <= 33 else 0
        need(selected == expected.get(byte, 0), "Capture selector table admits a wrong byte/code")
        if selected:
            decoded[chr(byte)] = selected
    need(
        capture_direct_writers(decoder, code, payload, 0x101C8, 1) == [0x5414],
        "Capture scenario has a missing, late or additional writer",
    )
    need(
        code[0x5414].op == "mov"
        and code[0x5414].args.startswith("%bl,")
        and capture_rip_target(code[0x5414], payload) == 0x101C8,
        "Capture scenario is not the validated byte result",
    )
    capture_call(decoder, code, 0x541A, 0x7A90)
    capture_call(decoder, code, 0x5422, 0x7B00)
    capture_expect(
        code,
        {
            0x7A99: ("push", "%rbx"),
            0x7AA8: ("mov", "$0x3f8,%ebx"),
            0x7AF5: ("pop", "%rbx"),
            0x7AF6: ("ret", ""),
            0x7AF7: ("ret", ""),
        },
    )
    text_symbol = next(symbol for symbol in linked.functions.values() if symbol.address == 0x7A90)
    _, text_dominators = capture_cfg(decoder, text_symbol, code)
    need(
        {0x7A99, 0x7AF5} <= text_dominators[0x7AF6] and 0x7A99 in text_dominators[0x7AA8],
        "Capture diagnostic callee does not restore full RBX",
    )
    for row in paired_rows(text_symbol, code):
        arguments = decoder.arguments(row.args)
        need(row.op != "call", "Capture release text helper acquired an unproved callee")
        if arguments and paired_register(arguments[-1]) == "rbx" and row.op not in decoder.READ_ONLY | {"push"}:
            need(row.address in (0x7AA8, 0x7AF5), "Capture diagnostic callee acquired an RBX clobber")
    # The complete text helper contract below saves/restores RBX on the nonempty
    # path and leaves it unchanged on the empty path. The only later release
    # value is zero-extended BL, whose producing write zero-extended all EBX.
    _, dominators = capture_cfg(decoder, linked.functions[CAPTURE_RUN], code)
    required = {
        0x5344,
        0x534D,
        0x53CB,
        0x53CC,
        0x53D4,
        0x53DD,
        0x53DE,
        0x53E1,
        0x53F6,
        0x53F9,
        0x5400,
        0x5404,
        0x5414,
        0x541A,
        0x541F,
    }
    need(required <= dominators[0x5422], "Capture numeric release bypasses validated selector/state lineage")
    need({0x5414, 0x5422, 0x5433} <= dominators[0x5AAC], "Capture grants precede release completion")
    return dict(selectors=decoded, invalid_bytes=249, table=[0xE8A0, 34], writer=0x5414, numeric_release=0x5422)


def capture_authority_proof(decoder, linked, code, payload):
    symbol = linked.functions[CAPTURE_RUN]
    edges, dominators = capture_cfg(decoder, symbol, code)
    reaches_entry = {0x5C19}
    while True:
        larger = reaches_entry | {address for address, targets in edges.items() if targets & reaches_entry}
        if larger == reaches_entry:
            break
        reaches_entry = larger
    for address, target in (
        (0x5AAC, 0x3A10),
        (0x5ABB, 0x3B00),
        (0x5B65, 0x39B0),
        (0x5B90, 0x3A80),
        (0x5EB9, 0x39B0),
        (0x5ED0, 0x39B0),
        (0x5EDE, 0x3A10),
        (0x5EFB, 0x3A80),
        (0x5F2E, 0x3A80),
        (0x5F40, 0x3B00),
        (0x5C19, 0xD017),
    ):
        capture_call(decoder, code, address, target)
    capture_expect(
        code,
        {
            0x5046: ("lea", "0xf0(%rsp),%rcx"),
            0x50A5: ("mov", "%rcx,0x8(%rsp)"),
            0x5C14: ("mov", "0x8(%rsp),%rdi"),
            0x5B53: ("mov", "0xf8(%rsp),%rsi"),
            0x5B5B: ("mov", "0xf0(%rsp),%rdi"),
            0x5B63: ("xor", "%edx,%edx"),
            0x5B72: ("mov", "0x108(%rsp),%rsi"),
            0x5B7A: ("xor", "%edx,%edx"),
            0x5B7C: ("mov", "0x100(%rsp),%rdi"),
            0x5C4D: ("mov", "%r13,0xf0(%rsp)"),
            0x5EA4: ("mov", "%rbx,0x100(%rsp)"),
            0x5EE3: ("mov", "%rax,%rbx"),
            0x5EE6: ("mov", "%rdx,%rbp"),
            0x3A18: ("cmp", "$0xffffffffffffffff,%rbx"),
            0x3A43: ("lea", "0x1(%rbx),%rdx"),
            0x3B0D: ("cmp", "$0xffffffffffffffff,%rax"),
            0x3B1E: ("lea", "0x1(%rax),%rbp"),
            0x5B26: ("cmp", "$0x2,%al"),
            0x5B2E: ("cmp", "$0x3,%al"),
            0x5B36: ("cmp", "$0x4,%al"),
            0x5B3E: ("cmp", "$0x5,%al"),
            0x5EB7: ("xor", "%edx,%edx"),
            0x5EC4: ("mov", "$0x1,%edx"),
            0x5EF3: ("xor", "%edx,%edx"),
            0x5F26: ("mov", "$0x1,%edx"),
        },
    )
    for row in paired_rows(symbol, code):
        if 0x5046 < row.address < 0x50A5:
            arguments = decoder.arguments(row.args)
            need(
                row.op != "call"
                and row.op not in decoder.BRANCHES
                and not (arguments and paired_register(arguments[-1]) == "rcx" and row.op not in decoder.READ_ONLY),
                "Capture local record pointer register is clobbered before its save",
            )
    expected_record_writes = {
        0x5AD0: (0xF0, "%rbx"),
        0x5AE8: (0xF8, "%rbp"),
        0x5AF5: (0x108, "%rax"),
        0x5B0E: (0x100, "%r13"),
        0x5B16: (0x110, "%rcx"),
        0x5B1E: (0x118, "%rdi"),
        0x5C4D: (0xF0, "%r13"),
        0x5EA4: (0x100, "%rbx"),
    }
    observed = {}
    pointer_writes = []
    for row in paired_rows(symbol, code):
        if row.address not in reaches_entry:
            continue
        args = decoder.arguments(row.args)
        if row.op in decoder.READ_ONLY | {"lea", "nop", "nopl", "nopw", "cs", "data16"} or len(args) != 2:
            continue
        slot = paired_slot(args[-1])
        if slot is None:
            continue
        if not (
            (row.address >= 0x5AAC and slot < 0x120 and 0xF0 < slot + 8)
            or (row.address >= 0x50A5 and slot < 16 and 8 < slot + 8)
        ):
            continue
        width = paired_width(row, args)
        if row.address >= 0x5AAC and slot < 0x120 and 0xF0 < slot + width:
            need(width == 8, "Capture record gained a partial/overlapping write")
            observed[row.address] = (slot, args[0])
        if row.address >= 0x50A5 and slot < 16 and 8 < slot + width:
            pointer_writes.append(row.address)
    need(observed == expected_record_writes, "Capture record/geometry/generation writer inventory changed")
    need(pointer_writes == [0x50A5], "Capture local record pointer slot is overwritten before entry")
    for branch, opcode, destination in (
        (0x5B28, "je", 0x5C4D),
        (0x5B30, "je", 0x5EA4),
        (0x5B38, "je", 0x5EB1),
        (0x5B40, "je", 0x5EEE),
    ):
        need(
            code[branch].op == opcode and decoder.target_of(code[branch]) == destination,
            "Changed fixed cross/stale scenario branch",
        )
    for clear, target, reopen, preflights in (
        (0x5ED5, 0x10150, 0x5EDE, {0x5EB9, 0x5EC9, 0x5ED0}),
        (0x5F37, 0x10128, 0x5F40, {0x5EFB, 0x5F0C, 0x5F05, 0x5F1A, 0x5F2E}),
    ):
        need(
            code[clear].op == "movw"
            and code[clear].args.startswith("$0x0,")
            and capture_rip_target(code[clear], payload) == target,
            "Capture stale fixture lacks real Session close",
        )
        need(preflights | {clear} <= dominators[reopen], "Capture reopen bypasses real close validation")
    for address, target in ((0x5EC9, 0x10151), (0x5F0C, 0x10129)):
        need(
            code[address].op == "movb"
            and code[address].args.startswith("$0x1,")
            and capture_rip_target(code[address], payload) == target,
            "Capture stale fixture skips Session enter",
        )
    for target, writer in ((0x10130, 0x3A65), (0x100E8, 0x3BA2), (0x10148, 0x3A6C), (0x10108, 0x3BA9)):
        need(
            capture_direct_writers(decoder, code, payload, target, 8) == [writer],
            "Capture Session generation has an additional/reset writer",
        )
    for name, comparison, dereference, overflow, advance, generation_store in (
        (CAPTURE_CONSOLE, 0x39BB, 0x39CA, 0x3A18, 0x3A43, 0x3A65),
        (CAPTURE_DISPLAY, 0x3A88, 0x3A9A, 0x3B0D, 0x3B1E, 0x3BA2),
    ):
        _, validation = capture_cfg(decoder, linked.functions[name + "8validateEPKvmb"], code)
        need(comparison in validation[dereference], "Session grant is dereferenced before exact address equality")
        _, opening = capture_cfg(decoder, linked.functions[name + "4openEv"], code)
        need({overflow, advance} <= opening[generation_store], "Session reopen can reset/wrap/bypass generation")
    required = {
        0x5046,
        0x50A5,
        0x5414,
        0x5422,
        0x5AAC,
        0x5ABB,
        0x5B65,
        0x5B90,
        0x5B99,
        0x5BA6,
        0x5BC1,
        0x5BDB,
        0x5BE7,
        0x5BF4,
        0x5C09,
        0x5C14,
    }
    need(required <= dominators[0x5C19], "Compiled entry bypasses local record identity or paired preflight")
    need(capture_direct_writers(decoder, code, payload, 0x101E8, 8) == [0x5C09], "Consumer entry counter writer drift")
    return dict(
        record_bytes=48,
        record_stack_offset=0xF0,
        record_pointer=[0x5046, 0x50A5, 0x5C14],
        cross_writes=[0x5C4D, 0x5EA4],
        real_reopens=[0x5EDE, 0x5F40],
        preflights=[0x5B65, 0x5B90],
        compiled_entry=0x5C19,
        stale_record_generations_preserved=[0xF8, 0x108],
    )


def capture_pixel_proof(decoder, linked, code, payload):
    symbol = linked.functions["__au_runtime_display_pixel"]
    edges, dominators = capture_cfg(decoder, symbol, code)
    capture_expect(
        code,
        {
            0x3DF0: ("cmp", "$0xffffffffffffffff,%rax"),
            0x3DFA: ("add", "$0x1,%rax"),
            0x3E0C: ("cmp", "$0x6,%al"),
            0x3E14: ("test", "%rcx,%rcx"),
            0x3FA0: ("cmp", "$0x7,%al"),
            0x3FA4: ("cmp", "$0x37,%rcx"),
            0x3E1D: ("mov", "$0x1,%ebx"),
            0x3FFF: ("add", "$0x1,%rcx"),
            0x4017: ("mov", "%ebp,(%rbx)"),
            0x4019: ("xor", "%ebx,%ebx"),
            0x3CF4: ("cmp", "$0xff,%rax"),
            0x3DDC: ("cmp", "$0xf423f,%rcx"),
            0x3EB3: ("mov", "%rbx,%rax"),
        },
    )
    for branch, op, target in (
        (0x3DF4, "je", 0x4096),
        (0x3E0E, "jne", 0x3FA0),
        (0x3E17, "jne", 0x3FA0),
        (0x3FA2, "jne", 0x3FAE),
        (0x3FA8, "je", 0x3E1D),
    ):
        need(
            code[branch].op == op and decoder.target_of(code[branch]) == target,
            "Capture fixed pixel failure edge changed",
        )
    for address, target in (
        (0x3DD5, 0x101F8),
        (0x3DE9, 0x101C0),
        (0x3DFE, 0x101C0),
        (0x3E05, 0x101C8),
        (0x400D, 0x101F8),
    ):
        need(capture_rip_target(code[address], payload) == target, "Capture pixel state lineage changed")
    for address, operation, prefix, suffix in (
        (0x3DD5, "mov", "", ",%rcx"),
        (0x3DE9, "mov", "", ",%rax"),
        (0x3DFE, "mov", "%rax,", "(%rip)"),
        (0x3E05, "movzbl", "", ",%eax"),
        (0x400D, "mov", "%rcx,", "(%rip)"),
    ):
        need(
            code[address].op == operation
            and code[address].args.startswith(prefix)
            and code[address].args.endswith(suffix),
            "Capture pixel counter register lineage changed",
        )
    need(
        capture_direct_writers(decoder, code, payload, 0x101C0, 8) == [0x3DFE],
        "Capture attempt increment is missing or duplicated",
    )
    need(
        capture_direct_writers(decoder, code, payload, 0x101F8, 8) == [0x400D],
        "Capture successful-store counter writer drift",
    )
    required = {
        0x3BF9,
        0x3C1F,
        0x3C39,
        0x3C4C,
        0x3C55,
        0x3C60,
        0x3C6B,
        0x3C74,
        0x3C81,
        0x3C8B,
        0x3C9F,
        0x3CAF,
        0x3CBE,
        0x3CD1,
        0x3CF4,
        0x3D00,
        0x3D09,
        0x3D12,
        0x3D30,
        0x3D7B,
        0x3DCC,
        0x3DDC,
        0x3DE9,
        0x3DF0,
        0x3DFA,
        0x3DFE,
        0x3E05,
        0x3E0C,
        0x3FA0,
        0x3FD1,
        0x3FFF,
        0x400D,
    }
    need(required <= dominators[0x4017], "Pixel store bypasses admission, checked attempt or fixed failure predicates")
    reachable, pending = set(), [0x3E1D]
    while pending:
        address = pending.pop()
        if address not in reachable:
            reachable.add(address)
            pending.extend(edges[address])
    need(not {0x3FFF, 0x400D, 0x4017} & reachable, "Injected pixel failure can reach a store effect")
    indirect_writes = []
    for row in paired_rows(symbol, code):
        arguments = decoder.arguments(row.args)
        if row.op in decoder.READ_ONLY | {"lea", "nop", "nopl", "nopw", "cs", "data16"} or not arguments:
            continue
        destination = arguments[-1]
        if "(" in destination and "%rip" not in destination and "%rsp" not in destination:
            indirect_writes.append(row.address)
    need(indirect_writes == [0x4017], "Capture pixel acquired another non-frame store")
    return dict(
        attempt_writer=0x3DFE,
        failure_successful_store_ordinals=[0, 55],
        error_join=0x3E1D,
        successful_store_counter=0x400D,
        mmio_store=0x4017,
        success_order="attempt, fixture predicates, successful counter, MMIO store",
        returned_error=1,
    )


def capture_serial_sequence(decoder, linked, code, payload, begin, end, seeds):
    registers, result, address = dict(seeds), [], begin
    while address < end:
        row = code[address]
        args = decoder.arguments(row.args)
        if row.address == 0x5DA6:
            need(
                row.op == "movb" and row.args.startswith("$0x0,") and capture_rip_target(row, payload) == 0x10179,
                "Capture completion does not clear ready state",
            )
        elif row.op == "call":
            target = decoder.target_of(row)
            if target == 0x7A90:
                length, data = registers.get("rdi"), registers.get("rsi")
                if (length, data) == ("reason_length", "reason_data"):
                    result.append(["text", "<reason>"])
                else:
                    need(
                        type(length) is int and type(data) is int and 0 < length < 128,
                        "Unproved capture text arguments",
                    )
                    capture_readonly(linked, data, length + 1)
                    need(payload[data + length] == 0, "Capture diagnostic string extent changed")
                    result.append(["text", payload[data : data + length].decode("ascii")])
            else:
                need(target == 0x7B00 and "rdi" in registers, "Unproved capture diagnostic callee/value")
                result.append(["number", registers["rdi"]])
            for register in PAIRED_CALLER_SAVED:
                registers.pop(register, None)
        elif row.op in ("mov", "movzbl", "lea") and len(args) == 2:
            destination = paired_register(args[-1])
            need(destination is not None, "Capture diagnostic unexpectedly writes memory")
            source = args[0]
            if source.startswith("$"):
                value = int(source[1:], 0)
            elif "%rip" in source:
                target = capture_rip_target(row, payload)
                value = target if row.op == "lea" else ["counter", target]
            else:
                value = registers.get(paired_register(source))
                need(value is not None, "Unproved capture diagnostic register lineage")
            registers[destination] = value
        elif row.op not in ("nop", "nopl", "nopw", "cs", "data16"):
            raise ValueError("Unreviewed capture diagnostic instruction: " + hex(address))
        address = row.next
    need(address == end, "Capture diagnostic boundary is not an instruction boundary")
    return result


def capture_diagnostic_proof(decoder, linked, code, payload):
    fail = capture_serial_sequence(
        decoder, linked, code, payload, 0x3884, 0x397C, {"rbp": "reason_length", "rbx": "reason_data"}
    )
    expected = [["text", "AURORA_GRAPHICAL_CONSOLE_FAIL: "], ["text", "<reason>"]]
    fields = (
        (" entries=", 0x101E8),
        (" samples=", 0x101E0),
        (" output_attempts=", 0x101D8),
        (" stores=", 0x101F8),
        (" completed=", 0x101D0),
        (" wakes=", 0x10210),
        (" pixel_attempts=", 0x101C0),
    )
    for label, counter in fields:
        expected += [["text", label], ["number", ["counter", counter]]]
    expected += [["text", "\r\n"]]
    need(fail == expected, "Capture failure diagnostic counter order/source changed")
    completion = capture_serial_sequence(decoder, linked, code, payload, 0x5D9A, 0x5E96, {"r12": "completion"})
    complete_expected = [["text", "AURORA_GRAPHICAL_CONSOLE_COMPLETE: completion="], ["number", "completion"]]
    for label, counter in (fields[5], fields[3], fields[0], fields[1], fields[2], fields[4], fields[6]):
        complete_expected += [["text", label], ["number", ["counter", counter]]]
    complete_expected += [["text", "\r\n"]]
    need(completion == complete_expected, "Capture completion diagnostic counter order/source changed")
    release = capture_serial_sequence(decoder, linked, code, payload, 0x541F, 0x5438, {"rbx": "selected_code"})
    need(release == [["number", "selected_code"], ["text", "\r\n"]], "Capture release numeric value changed")
    capture_expect(code, {0x3980: ("cli", ""), 0x3981: ("hlt", ""), 0x5EA0: ("cli", ""), 0x5EA1: ("hlt", "")})
    return dict(failure=fail, completion=completion, release=release, terminal="capture cli/hlt loops")


def capture_linked_evidence(decoder, linked, code, payload, file_hashes):
    contract = capture_file_contract(file_hashes)
    need(
        hashlib.sha256(payload).hexdigest() == contract["payload.bin"],
        "Changed exact capture payload bytes",
    )
    for row in code.values():
        if row.op == "call" or row.op in decoder.BRANCHES:
            decoder.target_of(row)  # The complete capture has no indirect control flow.
    named = {row.name: row for row in linked.symbols if row.section}
    for name, identity in CAPTURE_STATE_CONTRACTS.items():
        need(name in named, "Missing capture state symbol: " + name)
        symbol = named[name]
        need(
            (symbol.address, symbol.size, symbol.section, symbol.kind) == identity,
            "Changed capture grant/counter/state storage identity: " + name,
        )
        need(linked.sections[symbol.section][1] == 8, "Capture private state is not zero-initialized BSS")
    bodies = {}
    for name, (address, size, count, expected) in CAPTURE_MACHINE_CONTRACTS.items():
        need(name in linked.functions, "Missing exact capture body: " + name)
        symbol = linked.functions[name]
        need((symbol.address, symbol.size) == (address, size), "Changed exact capture body extent: " + name)
        rows = paired_rows(symbol, code)
        inventory = [[row.address, row.size, row.op, row.args, payload[row.address : row.next].hex()] for row in rows]
        need(
            len(rows) == count and hashlib.sha256(canonical(inventory).encode()).hexdigest() == expected,
            "Changed original capture instruction/byte inventory: " + name,
        )
        bodies[name] = dict(address=address, bytes=size, instructions=count, sha256=expected)
    return dict(
        schema="aurora-graphical-capture-linked-v1",
        status="checked-contract-requires-independent-review",
        files=dict(file_hashes),
        original_bodies=bodies,
        selector=capture_selector_proof(decoder, linked, code, payload),
        authority=capture_authority_proof(decoder, linked, code, payload),
        pixel=capture_pixel_proof(decoder, linked, code, payload),
        diagnostics=capture_diagnostic_proof(decoder, linked, code, payload),
    )


def verify_bridge_body(decoder, body, starts):
    need(
        len(body) == 6
        and [(r.op, r.args) for r in body[:3]] == [("push", "%rbp"), ("mov", "%rsp,%rbp"), ("mov", "%rdi,%r11")]
        and body[3].op == "call"
        and starts.get(decoder.target_of(body[3])) == ENTRY
        and [(r.op, r.args) for r in body[4:]] == [("leave", ""), ("ret", "")],
        "Changed private dual-grant bridge or graphical entry",
    )


def verify_value_bridge_body(decoder, body, starts):
    need(
        len(body) == 1 and body[0].op == "jmp" and starts.get(decoder.target_of(body[0])) == VALUE_ENTRY,
        "Changed value-only private bridge",
    )


def normalize_instruction(decoder, row, payload):
    if row.op in ("sti", "mfence", "pause", "wrmsr"):
        need(not row.args, "Unexpected privileged/fence operands")
    if row.op == "push" and row.args.startswith("$"):
        expected = {"$0x0": b"\x6a\x00", "$0x28": b"\x6a\x28"}.get(row.args)
        raw = payload[row.address : row.address + row.size]
        need(
            expected is not None and row.size == 2 and raw == expected,
            "Unreviewed immediate push width, bytes or value",
        )
        return decoder.Instruction(row.address, row.size, "push", "%rax"), dict(
            address=row.address,
            original=row.args,
            bytes=raw.hex(),
            equivalent="validated imm8 sign-extended qword push, +8 stack bytes",
        )
    # No memory-push, signed-wide stack immediate, or mnemonic normalization.
    return row, None


def verify_inventory(linked_names, frames, language_names, memory_names):
    fixed = {
        "uefi_payload_entry",
        "uefi_payload_fault",
        "uefi_payload_page_fault",
        "fault_common",
        "uefi_console_interrupt",
    }
    need(
        set(linked_names) == set(frames) | set(language_names) | set(memory_names) | fixed,
        "Unaccounted combined linked function/frame inventory",
    )
    need({ENTRY, BRIDGE} <= set(language_names), "Missing exact paired language entry/bridge")
    need(
        REFLECTION_HELPERS <= set(language_names)
        and {name for name in linked_names if name.startswith("aurora_reflect_")} == REFLECTION_HELPERS
        and not REFLECTION_HELPERS.intersection(set(frames) | set(memory_names)),
        "Reflection helpers must belong only to generated language",
    )
    runtime = {name for name in linked_names if name.startswith("__au_runtime_")}
    need(runtime == HOST_IMPORTS | {BRIDGE, VALUE_BRIDGE}, "Unexpected combined runtime authority/import inventory")
    need(
        not any(name.startswith(("uefi_runtime_", "aurora_user_", "aurora_kernel_budget_")) for name in linked_names),
        "Unexpected protected runtime or budget fixture",
    )


PAIRED_WALK = (
    "_ZZNK6aurora4uefi10PageTables16verify_graphicalEmRKNS0_5BytesEPKNS0_18LocalApicAdmissionEPKNS0_"
    "20FramebufferAdmissionEENKUlOT_mjmE1_clIRKSD_EEbSC_mjm"
)
PAIRED_ALIAS = (
    "_ZZNK6aurora4uefi10PageTables16verify_graphicalEmRKNS0_5BytesEPKNS0_18LocalApicAdmissionEPKNS0_"
    "20FramebufferAdmissionEENKUlOT_mjmE_clIRKSD_EEbSC_mjm"
)

# This pure induction engine is not an admission substitute. The caller must
# first establishes the closed linked root snapshot/guard and visited-store
# contract below before applying this engine to the original instructions.
PAIRED_LEVEL_HELPER = "_ZN6aurora4uefi14expected_flagsEmRKNS0_5BytesE"
PAIRED_LEVEL_SPILLS = frozenset((0x18, 0x20, 0x3C))
PAIRED_LEVEL_OPS = frozenset(
    (
        "push pop mov movabs movb movl movq movw movzbl sub add cmp cmpb test lea xor "
        "shl shr and or call ret nop nopl nopw cs data16"
    ).split()
)


def paired_frame_envelope(decoder, symbol, code):
    rows = [row for address, row in sorted(code.items()) if symbol.address <= address < symbol.address + symbol.size]
    saves = ("%r15", "%r14", "%r13", "%r12", "%rbp", "%rbx")
    prologue = [("push", saves[0]), ("mov", "%rdx,%r11")]
    prologue += [("push", register) for register in saves[1:]] + [("sub", "$0x48,%rsp")]
    need([(row.op, row.args) for row in rows[:8]] == prologue, "Changed paired fixed-frame prologue")
    restores = [("add", "$0x48,%rsp")] + [("pop", register) for register in reversed(saves)] + [("ret", "")]
    exits = []
    allowed_stack_changes = {row.address for row in rows[:8] if row.op in ("push", "sub")}
    for index, row in enumerate(rows):
        if row.op == "ret":
            need(
                index >= 7 and [(item.op, item.args) for item in rows[index - 7 : index + 1]] == restores,
                "Changed paired fixed-frame restoration",
            )
            exits.append(row.address)
            allowed_stack_changes.update(item.address for item in rows[index - 7 : index + 1])
    need(exits, "Paired walker has no balanced return")
    for row in rows:
        args = decoder.arguments(row.args)
        need(not (row.op == "lea" and "%rsp" in row.args), "Paired private frame address escapes via LEA")
        if row.op in ("push", "pop", "leave", "pushf") or (args and args[-1] in ("%rsp", "%esp", "%sp", "%spl")):
            need(row.address in allowed_stack_changes, "Paired spill frame base changes inside body")
        for operand in args:
            if "sp" in operand and "%" in operand:
                need(
                    operand == "%rsp"
                    and row.address in allowed_stack_changes
                    or re.fullmatch(r"(?:0x[0-9a-f]+)?\(%rsp\)", operand),
                    "Paired private frame address escapes or has indexed/unknown form",
                )
    return rows


def paired_gcc16_slot_frame(decoder, symbol, code):
    """Prove the closed GCC16 allocation/save-slot form on every CFG path.

    This is a frame constituent only. Separate exact-machine and storage proofs
    must justify each admitted external/indexed write and all helper effects.
    """
    layouts = {
        PAIRED_ROOT: (0xE8, {"rbx": 0xC0, "rbp": 0xC8, "r12": 0xD0, "r14": 0xD8, "r15": 0xE0},
                      {0x789: ("movb", "$0x0,0x48(%rsp,%rax,1)")}),
        PAIRED_ALIAS: (0x78, {"rbx": 0x48, "rbp": 0x50, "r12": 0x58, "r13": 0x60,
                              "r14": 0x68, "r15": 0x70}, {0x76: ("movb", "$0x1,(%rdx,%rax,1)")}),
        PAIRED_LAYOUT: (0xB8, {"rbx": 0xB0}, {}),
    }
    need(symbol.name in layouts, "Unknown GCC16 save-slot frame owner")
    size, slots, external = layouts[symbol.name]
    rows = paired_rows(symbol, code)
    successors, _, _ = paired_cfg(decoder, symbol, code)
    registers = (*PAIRED_CALLER_SAVED, *PAIRED_SAVES)
    initial = tuple(name if name in PAIRED_SAVES else None for name in registers)
    states = {symbol.address: (0, initial, (None,) * size)}
    pending, returns, saves, restores = [symbol.address], set(), set(), set()

    def schedule(address, allocation, regs, memory):
        state = allocation, tuple(regs[name] for name in registers), tuple(memory)
        prior = states.get(address)
        if prior is not None:
            need(prior[0] == allocation, "GCC16 frame allocation disagrees at CFG join")
            state = allocation, tuple(a if a == b else None for a, b in zip(prior[1], state[1])), tuple(
                a if a == b else None for a, b in zip(prior[2], state[2])
            )
            if state == prior:
                return
        states[address] = state
        pending.append(address)

    while pending:
        address = pending.pop()
        allocation, values, memory = states[address]
        regs, memory = dict(zip(registers, values)), list(memory)
        row = code[address]
        args = decoder.arguments(row.args)
        offset = address - symbol.address
        need(row.op not in ("push", "pop", "leave", "enter"), "Unexpected GCC16 frame stack operation")
        if row.op == "ret":
            need(allocation == 0 and all(regs[name] == name for name in PAIRED_SAVES),
                 "GCC16 return has unbalanced allocation or damaged callee save")
            returns.add(address)
            continue
        if args[-1:] in (["%rsp"], ["%esp"], ["%sp"], ["%spl"]):
            need(args == ["$" + hex(size), "%rsp"] and row.op in ("sub", "add"),
                 "Unknown GCC16 stack allocation operand")
            need(allocation == (0 if row.op == "sub" else size), "Repeated or missing GCC16 frame allocation")
            allocation = size if row.op == "sub" else 0
        elif row.op == "call":
            need(allocation == size, "GCC16 call outside allocated frame")
            for name in PAIRED_CALLER_SAVED:
                regs[name] = None
        elif row.op not in PAIRED_NO_WRITE | decoder.BRANCHES and not (row.op == "xchg" and row.args == "%ax,%ax"):
            need(row.op in {"mov", "movabs", "movb", "movq", "movzbl", "lea", "xor", "and", "or",
                            "sub", "add", "shl", "shr", "sete", "setne", "seta", "setae", "setb", "setbe", "cmove"},
                 "Unknown or multi-destination GCC16 frame instruction")
            need(args, "Unknown GCC16 frame instruction")
            value = None
            if row.op == "mov" and len(args) == 2:
                source = paired_register(args[0])
                if source in regs and args[0] == "%" + source:
                    value = regs[source]
                slot = paired_slot(args[0])
                if slot is not None:
                    need(allocation == size and slot + 8 <= size, "GCC16 restore reads outside allocation")
                    parts = memory[slot:slot + 8]
                    if parts[0] is not None and parts == [(parts[0][0], index) for index in range(8)]:
                        value = parts[0][0]
                        if value in slots:
                            need(slot == slots[value] and args[-1] == "%" + value,
                                 "GCC16 callee restore uses wrong slot/register")
                            restores.add((address, value, slot))
            if "(" in args[-1]:
                slot = paired_slot(args[-1])
                if slot is None:
                    need(external.get(offset) == (row.op, row.args) and allocation == size,
                         "Unclassified GCC16 frame memory write")
                else:
                    width = paired_width(row, args)
                    need(allocation == size and slot + width <= size, "GCC16 store escapes allocated frame")
                    overlap = [name for name, start in slots.items() if slot < start + 8 and start < slot + width]
                    if overlap:
                        need(len(overlap) == 1 and width == 8 and slot == slots[overlap[0]]
                             and value == overlap[0] and args[0] == "%" + overlap[0],
                             "GCC16 private spill overwrites a callee-save slot")
                        saves.add((address, overlap[0], slot))
                    memory[slot:slot + width] = [(value, index) if value is not None else None for index in range(width)]
            else:
                destination = paired_register(args[-1])
                need(destination in regs, "Unknown GCC16 frame register effect")
                regs[destination] = value if args[-1] == "%" + destination else None
        for target in successors[address]:
            schedule(target, allocation, regs, memory)
    need(returns and {name for _, name, _ in saves} == set(slots)
         and {name for _, name, _ in restores} == set(slots), "Incomplete GCC16 save/restore inventory")
    return dict(allocation=size, frame_with_return=size + 8, save_slots=slots,
                saves=sorted(saves), restores=sorted(restores), returns=sorted(returns))


def paired_readonly_leaf(decoder, name, symbols, code, functions):
    need(
        name == PAIRED_LEVEL_HELPER and name in symbols and not functions[name]["calls"],
        "Paired level helper is not the exact closed leaf",
    )
    symbol = symbols[name]
    readonly = {"cmp", "cmpb", "cmpl", "cmpq", "cmpw", "test", "bt", "nop", "nopl", "nopw", "cs", "data16"}
    for address, row in code.items():
        if not symbol.address <= address < symbol.address + symbol.size:
            continue
        args = decoder.arguments(row.args)
        need(
            row.op not in ("call", "push", "pop", "leave", "pushf", "rep", "xchg", "syscall", "out", "in")
            and not any("%rsp" in operand or "%rbp" in operand for operand in args),
            "Paired helper has calls, side effects or private-frame access",
        )
        if row.op in decoder.BRANCHES:
            need(
                symbol.address <= decoder.target_of(row) < symbol.address + symbol.size,
                "Paired helper branches outside its read-only body",
            )
        elif row.op not in readonly and row.op != "ret":
            need(
                row.op in {"mov", "movabs", "movzbl", "lea", "xor", "or", "sub", "add", "shl", "cmovae"}
                and paired_register(args[-1]) not in PAIRED_SAVES,
                "Paired helper has unknown effects or clobbers a callee-saved register",
            )
            need(
                args
                and re.fullmatch(
                    r"%(?:r(?:ax|bx|cx|dx|si|di|[89]|1[0-5])|e(?:ax|bx|cx|dx|si|di)|[abcd][lh]|r(?:[89]|1[0-5])[dwb])",
                    args[-1],
                ),
                "Paired helper writes memory or a non-scalar register",
            )
    return dict(symbol=name, calls=0, memory_writes=0)


def paired_level_induction(decoder, symbol, code, starts, generic, bitmap_stores=(), storage=None):
    """Original-instruction ECX/R9D and byte-spill fixed points for seeds 0..3.

    bitmap_stores must be the exact addresses whose bounded, root-owned target
    was proved by the linked root and local walker contract. With storage set,
    each seed also establishes caller-memory preservation and closure forwarding;
    a child may preserve spills only after its smaller seed was established.
    Without storage this is solely a pure level constituent, never admission.
    """
    rows = paired_frame_envelope(decoder, symbol, code)
    begin, end = symbol.address, symbol.address + symbol.size
    body = {row.address: row for row in rows}
    bitmap_stores = frozenset(bitmap_stores)
    need(bitmap_stores <= set(body), "Bitmap write summary references another function")
    call_rows = [row for row in rows if row.op == "call"]
    targets = [starts.get(decoder.target_of(row)) for row in call_rows]
    need(
        targets.count(symbol.name) == 1 and targets.count(PAIRED_LEVEL_HELPER) == 2 and len(targets) == 3,
        "Unexpected paired helper/self-call inventory",
    )
    generic_calls = {row["address"]: row for row in generic["calls"]}
    need(set(generic_calls) == {row.address for row in call_rows}, "Paired generic call inventory mismatch")

    def register(operand):
        if operand in ("%rcx", "%ecx", "%cx", "%cl", "%ch"):
            return 0
        if operand in ("%r9", "%r9d", "%r9w", "%r9b"):
            return 1
        return None

    def width(operand):
        if re.fullmatch(r"%r(?:ax|bx|cx|dx|si|di|bp|[89]|1[0-5])", operand):
            return 8
        if re.fullmatch(r"%(?:e(?:ax|bx|cx|dx|si|di|bp)|r(?:[89]|1[0-5])d)", operand):
            return 4
        if re.fullmatch(r"%(?:ax|bx|cx|dx|si|di|bp|r(?:[89]|1[0-5])w)", operand):
            return 2
        if re.fullmatch(r"%(?:al|ah|bl|bh|cl|ch|dl|dh|sil|dil|bpl|r(?:[89]|1[0-5])b)", operand):
            return 1
        return None

    def stack_slot(operand):
        match = re.fullmatch(r"(0x[0-9a-f]+)?\(%rsp\)", operand)
        return int(match[1] or "0", 16) if match else None

    if storage is not None:
        need(
            storage["walker"]["conditional_on_smaller_seed"] is True
            and bitmap_stores == {storage["walker"]["bitmap_store"]}
            and set(storage["helpers"]) == set(PAIRED_HELPERS)
            and all(effect["caller_memory_writes"] == 0 for effect in storage["helpers"].values()),
            "Missing paired local storage/helper premise",
        )
    levels = {}
    readonly = {"cmp", "cmpb", "test", "nop", "nopl", "nopw", "cs", "data16"}
    preserve_flags = {
        "mov",
        "movabs",
        "movb",
        "movl",
        "movq",
        "movw",
        "movzbl",
        "lea",
        "push",
        "pop",
        "nop",
        "nopl",
        "nopw",
        "cs",
        "data16",
    }
    for seed in range(4):
        # Byte precision prevents adjacent qword data spills from being treated
        # as preserving overlapping dword level facts. No address-only memo.
        closure_seed = ("closure", "closure") if storage is not None else (None, None)
        states = {begin: (seed, None, None, (None,) * 0x48, closure_seed)}
        pending, visited, calls, returns = [begin], set(), {}, set()

        def schedule(address, state):
            need(begin <= address < end and address in body, "Paired CFG leaves body or enters an instruction interior")
            prior = states.get(address)
            if prior is not None:
                state = tuple(a if a == b else None for a, b in zip(prior[:3], state[:3])) + (
                    tuple(a if a == b else None for a, b in zip(prior[3], state[3])),
                    tuple(a if a == b else None for a, b in zip(prior[4], state[4])),
                )
                if state == prior:
                    return
            states[address] = state
            pending.append(address)

        while pending:
            address = pending.pop()
            row = body[address]
            need(
                row.next <= end and row.op in PAIRED_LEVEL_OPS | decoder.BRANCHES,
                "Unreviewed paired level instruction or extent",
            )
            visited.add(address)
            cx, r9, zf, memory, closure = states[address]
            values, memory, next_closure = [cx, r9], list(memory), list(closure)
            args = decoder.arguments(row.args)
            next_zf = zf if row.op in preserve_flags | decoder.BRANCHES else None
            if row.op == "ret":
                returns.add(address)
                continue
            if row.op == "call":
                target = starts.get(decoder.target_of(row))
                call = dict(generic_calls[address])
                if target == symbol.name:
                    need(
                        seed > 0 and seed - 1 in levels and cx == seed - 1,
                        "Paired child lacks previously proved decreasing level",
                    )
                    if storage is not None:
                        need(
                            levels[cx].get("caller_memory_contract") is True and closure == ("closure", "closure"),
                            "Paired child lacks established memory contract or identical closure",
                        )
                    call["level"] = cx
                else:
                    need(target == PAIRED_LEVEL_HELPER, "Unexpected paired level callee")
                    if storage is not None:
                        need("closure" not in closure, "Paired closure escapes to scalar helper")
                    call["level"] = None
                previous = calls.get(address)
                need(previous is None or previous == call, "Paired call level facts disagree at a join")
                calls[address] = call
                # No caller-saved level/flag survives even a read-only helper.
                schedule(row.next, (None, None, None, tuple(memory), (None, None)))
                continue
            if row.op in decoder.BRANCHES:
                target = decoder.target_of(row)
                taken = (
                    zf if row.op in ("je", "jz") else (not zf if zf is not None and row.op in ("jne", "jnz") else None)
                )
                if row.op == "jmp" or taken is not False:
                    schedule(target, (cx, r9, zf, tuple(memory), closure))
                if row.op != "jmp" and taken is not True:
                    schedule(row.next, (cx, r9, zf, tuple(memory), closure))
                continue
            if args and row.op not in readonly:
                closure_register = paired_register(args[-1])
                if closure_register in ("rdi", "rsi"):
                    destination = ("rdi", "rsi").index(closure_register)
                    next_closure[destination] = None
                    if row.op == "mov" and args[-1] == "%" + closure_register:
                        source = paired_register(args[0])
                        if source in ("rdi", "rsi") and args[0] == "%" + source:
                            next_closure[destination] = closure[("rdi", "rsi").index(source)]
                        else:
                            offset = stack_slot(args[0])
                            if offset is not None and memory[offset : offset + 8] == [("closure", i) for i in range(8)]:
                                next_closure[destination] = "closure"
                destination = register(args[-1])
                if destination is not None:
                    values[destination] = None
                    if row.op == "mov" and len(args) == 2 and args[-1] in ("%ecx", "%r9d"):
                        source = register(args[0])
                        if source is not None and args[0] in ("%ecx", "%r9d"):
                            values[destination] = (cx, r9)[source]
                        else:
                            offset = stack_slot(args[0])
                            if offset in PAIRED_LEVEL_SPILLS and offset + 4 <= 0x48:
                                content = memory[offset : offset + 4]
                                if len(content) == 4 and all(type(value) is int for value in content):
                                    value = int.from_bytes(bytes(content), "little")
                                    values[destination] = value if value <= 3 else None
                    elif row.op == "lea" and row.args == "-0x1(%r9),%ecx" and r9 is not None:
                        values[0] = (r9 - 1) & 0xFFFFFFFF
                if "(" in args[-1]:
                    offset = stack_slot(args[-1])
                    if offset is None:
                        need(
                            address in bitmap_stores and row.op == "movb" and row.args == "$0x1,(%rdx,%rax,1)",
                            "Unproved paired external/aliased write",
                        )
                    else:
                        size = {"movb": 1, "movw": 2, "movl": 4, "movq": 8}.get(row.op)
                        if row.op == "mov" and len(args) == 2:
                            size = width(args[0])
                        need(
                            size is not None and 0 <= offset and offset + size <= 0x48,
                            "Unbounded or unknown paired spill write width/range",
                        )
                        memory[offset : offset + size] = [None] * size
                        if row.op == "mov" and args[0] in ("%ecx", "%r9d") and offset in PAIRED_LEVEL_SPILLS:
                            value = (cx, r9)[register(args[0])]
                            if value is not None:
                                memory[offset : offset + 4] = value.to_bytes(4, "little")
                        if row.op == "mov" and size == 8 and args[0] in ("%rdi", "%rsi"):
                            value = closure[("%rdi", "%rsi").index(args[0])]
                            if value == "closure":
                                memory[offset : offset + 8] = [("closure", i) for i in range(8)]
            if row.op == "test" and row.args == "%r9d,%r9d" and r9 is not None:
                next_zf = r9 == 0
            schedule(row.next, (values[0], values[1], next_zf, tuple(memory), tuple(next_closure)))
        recursive = [row for row in calls.values() if row["target"] == symbol.name]
        need(
            not recursive if seed == 0 else len(recursive) == 1 and recursive[0]["level"] == seed - 1,
            "Paired recursion is not bounded for every seed",
        )
        need(returns, "Paired seed has no returning path")
        levels[seed] = dict(
            generic,
            calls=sorted(calls.values(), key=lambda row: row["address"]),
            instructions=len(visited),
            returns=len(returns),
            seed=seed,
            private_spill_bytes=0x48,
            caller_saved_killed=True,
            caller_memory_contract=storage is not None,
            established_child_seed=None if seed == 0 else seed - 1,
            identical_closure_forwarding=storage is not None,
        )
    return levels


# Closed image006 instruction contracts. These hashes cover the complete original
# instruction inventories, including unreachable padding. Only independently
# resolved direct-call and RIP-table relocations are normalized. They freeze the
# audited semantics below; neither a matching hash alone nor a selected slice is
# a storage/recursion proof. A new emitted shape requires a new independent audit.
PAIRED_ROOT = (
    "_ZNK6aurora4uefi10PageTables16verify_graphicalEmRKNS0_5BytesEPKNS0_18LocalApicAdmissionEPKNS0_"
    "20FramebufferAdmissionE"
)
PAIRED_GUARD = "_ZN6aurora4uefi10PageTables33paired_graphical_storage_disjointEmmmm"
PAIRED_LAYOUT = "_ZN6aurora4uefi20RuntimeLayoutProfileILm2EE5validEm"
PAIRED_BYTES = "_ZNK6aurora4uefi5Bytes3getEmj"
PAIRED_ENTRY = "_ZNK6aurora4uefi10PageTables5entryEm"
PAIRED_WINDOW = "_ZNK6aurora4uefi10PageTables11window_slotEv.isra.0"
PAIRED_HELPERS = (PAIRED_LAYOUT, PAIRED_BYTES, PAIRED_LEVEL_HELPER, PAIRED_GUARD, PAIRED_ENTRY, PAIRED_WINDOW)
PAIRED_MACHINE_CONTRACTS = {
    PAIRED_ROOT: (2084, 483, "248f70669f871707a268211f3454fd9365a402b01009fbf44f5910d235ad24cf"),
    PAIRED_WALK: (866, 194, "d8867daaaceefeb5d64ef4dcd7c18b14dfe4207f96a24c1c4ac78b12d2bf6458"),
    PAIRED_LAYOUT: (826, 174, "a405c4b6a848938ff414204e852558572acf8627fa0578414e16161a42299d1e"),
    PAIRED_BYTES: (88, 27, "63e95aa6c16e985070d60d833a3973841213d5425306a8449926b75d128bd276"),
    PAIRED_LEVEL_HELPER: (813, 153, "c66fbbbc719273cdaf98d1639ecf89dfa11fb829766cb8bd2c96e10d16a301ba"),
    PAIRED_GUARD: (34, 14, "94a3650c743e0a6f5676c288ae3ad4e987dcc456b22da68e288242a740abf0e2"),
    PAIRED_ENTRY: (132, 37, "80aec290b73bb625358142cbf89e138facfc2ca601e760243e0af2312d444af1"),
    PAIRED_WINDOW: (115, 29, "36367b56b5d8d3a1e36126e10a90fc51eb7a72958fe453ed720786c494cbeb43"),
}
PAIRED_SAVES = ("r15", "r14", "r13", "r12", "rbp", "rbx")
PAIRED_CALLER_SAVED = ("rax", "rcx", "rdx", "rsi", "rdi", "r8", "r9", "r10", "r11")
PAIRED_NO_WRITE = frozenset("cmp cmpb cmpl cmpq cmpw test bt nop nopl nopw cs data16".split())


def paired_rows(symbol, code):
    rows = [row for address, row in sorted(code.items()) if symbol.address <= address < symbol.address + symbol.size]
    cursor = symbol.address
    for row in rows:
        need(row.address == cursor and row.size > 0, "Paired instruction overlap, gap or wrong address")
        cursor = row.next
    need(cursor == symbol.address + symbol.size, "Incomplete paired function instruction extent")
    return rows


def paired_register(operand):
    for root in ("rax", "rbx", "rcx", "rdx", "rsi", "rdi", "rbp", "rsp"):
        stem = root[1:]
        aliases = (
            (root, "e" + stem, stem, stem[0] + "l", stem[0] + "h")
            if root in ("rax", "rbx", "rcx", "rdx")
            else (root, "e" + stem, stem, stem + "l")
        )
        if operand.removeprefix("%") in aliases and operand.startswith("%"):
            return root
    match = re.fullmatch(r"%(r(?:[89]|1[0-5]))[dwb]?", operand)
    return match[1] if match else None


def paired_width(row, args):
    if row.op in ("movb", "movw", "movl", "movq"):
        return {"movb": 1, "movw": 2, "movl": 4, "movq": 8}[row.op]
    need(row.op == "mov" and len(args) == 2, "Unknown paired memory-write semantics")
    source = args[0]
    root = paired_register(source)
    need(root is not None, "Unknown paired store width")
    if source == "%" + root:
        return 8
    if source.startswith("%e") or re.fullmatch(r"%r\d+d", source):
        return 4
    if source in ("%al", "%ah", "%bl", "%bh", "%cl", "%ch", "%dl", "%dh", "%sil", "%dil", "%bpl", "%spl"):
        return 1
    return 1 if source.endswith("b") else 2


def paired_slot(operand):
    match = re.fullmatch(r"(0x[0-9a-f]+)?\(%rsp\)", operand)
    return int(match[1] or "0", 16) if match else None


def paired_machine_inventory(decoder, symbol, code, starts, payload):
    rows = paired_rows(symbol, code)
    inventory = []
    for row in rows:
        raw = payload[row.address : row.next]
        need(len(raw) == row.size, "Truncated paired machine bytes")
        args = row.args
        if row.op == "call":
            target = decoder.target_of(row)
            need(
                row.size == 5
                and raw[:1] == b"\xe8"
                and row.next + int.from_bytes(raw[1:], "little", signed=True) == target
                and target in starts,
                "Paired direct call bytes/target disagree",
            )
            args, raw = starts[target], raw[:1] + b"\0" * 4
        elif row.op in decoder.BRANCHES:
            target = decoder.target_of(row)
            need(
                symbol.address <= target < symbol.address + symbol.size and target in code,
                "Paired branch leaves body or enters instruction interior",
            )
            condition = dict(
                jo=0,
                jno=1,
                jb=2,
                jae=3,
                je=4,
                jne=5,
                jbe=6,
                ja=7,
                js=8,
                jns=9,
                jp=10,
                jnp=11,
                jl=12,
                jge=13,
                jle=14,
                jg=15,
            )
            need(row.op == "jmp" or row.op in condition, "Unreviewed paired branch condition")
            prefixes = (
                (b"\xeb", b"\xe9")
                if row.op == "jmp"
                else (bytes((0x70 + condition[row.op],)), bytes((0x0F, 0x80 + condition[row.op])))
            )
            size = 1 if raw.startswith(prefixes[0]) else 4
            prefix = prefixes[0] if size == 1 else prefixes[1]
            need(
                raw.startswith(prefix)
                and len(raw) == len(prefix) + size
                and row.next + int.from_bytes(raw[-size:], "little", signed=True) == target,
                "Paired branch bytes/condition/target disagree",
            )
            args = hex(target - symbol.address)
        elif "%rip" in row.args:
            match = re.fullmatch(r"(-?0x[0-9a-f]+)\(%rip\),%(rdi|rdx)", row.args)
            need(
                match and row.op == "lea" and row.size == 7 and raw[:3] in (b"\x48\x8d\x3d", b"\x48\x8d\x15"),
                "Unreviewed paired RIP access",
            )
            displacement = int.from_bytes(raw[3:], "little", signed=True)
            need(displacement == int(match[1], 16), "Paired RIP bytes/address disagree")
            target = row.next + displacement
            need(
                0 <= target <= len(payload) - 12 and payload[target : target + 12] == struct.pack("<III", 39, 30, 21),
                "Changed paired read-only page-level table",
            )
            args, raw = "levels[39,30,21],%" + match[2], raw[:3] + b"\0" * 4
        inventory.append([row.address - symbol.address, row.size, row.op, args, raw.hex()])
    return inventory


def paired_exact_machine(decoder, symbols, code, starts, payload):
    need(payload is not None, "Paired snapshot/guard linked storage proof requires exact machine bytes")
    receipts = {}
    for name, (size, count, expected) in PAIRED_MACHINE_CONTRACTS.items():
        need(name in symbols and symbols[name].size == size, "Changed paired audited function size: " + name)
        inventory = paired_machine_inventory(decoder, symbols[name], code, starts, payload)
        actual = hashlib.sha256(canonical(inventory).encode()).hexdigest()
        need(
            len(inventory) == count and actual == expected, "Changed paired audited instruction/byte inventory: " + name
        )
        receipts[name] = dict(bytes=size, instructions=count, normalized_sha256=actual)
    need(len(receipts) == 8, "Incomplete paired audited machine inventory")
    return receipts


def paired_cfg(decoder, symbol, code):
    rows = paired_rows(symbol, code)
    addresses = {row.address for row in rows}
    successors, predecessors = {}, {address: set() for address in addresses}
    for row in rows:
        following = set()
        if row.op in decoder.BRANCHES:
            following.add(decoder.target_of(row))
        if row.op not in ("ret", "jmp"):
            following.add(row.next)
        need(following <= addresses, "Paired CFG leaves its exact body")
        successors[row.address] = following
        for target in following:
            predecessors[target].add(row.address)
    reachable, pending = set(), [symbol.address]
    while pending:
        address = pending.pop()
        if address not in reachable:
            reachable.add(address)
            pending.extend(successors[address])
    dominators = {address: ({address} if address == symbol.address else set(reachable)) for address in reachable}
    changed = True
    while changed:
        changed = False
        for address in sorted(reachable - {symbol.address}):
            incoming = predecessors[address] & reachable
            value = {address} | set.intersection(*(dominators[parent] for parent in incoming))
            if value != dominators[address]:
                dominators[address], changed = value, True
    return successors, predecessors, dominators


def paired_helper_effects(decoder, symbols, code, functions):
    effects = {}
    for name in PAIRED_HELPERS:
        symbol = symbols[name]
        rows = paired_rows(symbol, code)
        need(not functions[name]["calls"] and all(row.op != "call" for row in rows), "Paired helper acquired a call")
        saved = PAIRED_SAVES if name == PAIRED_LAYOUT else (("rbx",) if name == PAIRED_ENTRY else ())
        prologue = [row for row in rows if row.op == "push"]
        need([row.args for row in prologue] == ["%" + value for value in saved], "Changed helper register saves")
        # A per-path save/restore automaton proves preservation, including early
        # layout rejection returns before its conditional prologue.
        successors, _, _ = paired_cfg(decoder, symbol, code)
        states, pending = {symbol.address: ((), 0)}, [symbol.address]
        stores = []
        while pending:
            address = pending.pop()
            row = code[address]
            stack, allocation = states[address]
            args = decoder.arguments(row.args)
            if row.op == "push":
                need(args == ["%" + saved[len(stack)]] and not allocation, "Unbalanced paired helper save")
                stack += (args[0],)
            elif row.op == "pop":
                need(stack and args == [stack[-1]] and not allocation, "Unbalanced paired helper restore")
                stack = stack[:-1]
            elif args[-1:] == ["%rsp"] and row.op in ("sub", "add"):
                need(
                    name == PAIRED_LAYOUT and row.args == "$0xb8,%rsp" and len(stack) == 6,
                    "Unknown helper stack allocation",
                )
                need(allocation == (0 if row.op == "sub" else 0xB8), "Changed helper private-frame lifetime")
                allocation = 0xB8 if row.op == "sub" else 0
            elif row.op == "ret":
                need(not stack and not allocation, "Helper returns without restoring its caller")
            elif row.op not in PAIRED_NO_WRITE | decoder.BRANCHES:
                need(
                    row.op
                    in {
                        "mov",
                        "movabs",
                        "movq",
                        "movzbl",
                        "lea",
                        "xor",
                        "and",
                        "or",
                        "sub",
                        "add",
                        "shl",
                        "shr",
                        "setae",
                        "cmovae",
                    },
                    "Unknown paired helper effect",
                )
                destination = paired_register(args[-1])
                need(destination != "rsp", "Unknown helper stack write")
                if destination in PAIRED_SAVES:
                    need("%" + destination in stack, "Paired helper clobbers an unsaved callee register")
                if "(" in args[-1]:
                    slot = paired_slot(args[-1])
                    width = paired_width(row, args)
                    need(
                        name == PAIRED_LAYOUT
                        and allocation == 0xB8
                        and slot is not None
                        and 0 <= slot
                        and slot + width <= allocation,
                        "Paired helper writes caller/unknown memory",
                    )
                    stores.append((address, slot, width))
            state = stack, allocation
            for target in successors[address]:
                if target in states:
                    need(states[target] == state, "Helper stack preservation disagrees at CFG join")
                else:
                    states[target] = state
                    pending.append(target)
        # Classify even unreachable instructions; exact machine coverage prevents
        # hidden stores in ignored padding and the reachable pass checks lifetime.
        all_stores = [
            row.address
            for row in rows
            if decoder.arguments(row.args)[-1:]
            and "(" in decoder.arguments(row.args)[-1]
            and row.op not in PAIRED_NO_WRITE | decoder.BRANCHES
        ]
        need(set(all_stores) == {address for address, _, _ in stores}, "Unclassified paired helper memory write")
        effects[name] = dict(
            caller_memory_writes=0,
            private_stores=sorted(set(stores)),
            callee_saved_preserved=list(PAIRED_SAVES),
            calls=0,
        )
    return effects


def paired_gcc16_helper_effects(decoder, symbols, code, functions):
    effects = {}
    for name in PAIRED_HELPERS:
        symbol = symbols[name]
        rows = paired_rows(symbol, code)
        need(not functions[name]["calls"] and all(row.op != "call" for row in rows), "Paired helper acquired a call")
        if name == PAIRED_LAYOUT:
            frame = paired_gcc16_slot_frame(decoder, symbol, code)
            private = []
            for row in rows:
                args = decoder.arguments(row.args)
                if args[-1:] and "(" in args[-1] and row.op not in PAIRED_NO_WRITE | decoder.BRANCHES:
                    slot, width = paired_slot(args[-1]), paired_width(row, args)
                    need(slot is not None and 0 <= slot and slot + width <= 0xB8,
                         "GCC16 layout helper writes outside private frame")
                    private.append((row.address, slot, width))
            effects[name] = dict(caller_memory_writes=0, private_stores=private,
                                 callee_saved_preserved=list(PAIRED_SAVES), calls=0, frame=frame)
            continue
        saved = ("rbx",) if name == PAIRED_ENTRY else ()
        prologue = [row for row in rows if row.op == "push"]
        need([row.args for row in prologue] == ["%" + value for value in saved], "Changed helper register saves")
        # A per-path save/restore automaton proves preservation, including early
        # layout rejection returns before its conditional prologue.
        successors, _, _ = paired_cfg(decoder, symbol, code)
        states, pending = {symbol.address: ((), 0)}, [symbol.address]
        stores = []
        while pending:
            address = pending.pop()
            row = code[address]
            stack, allocation = states[address]
            args = decoder.arguments(row.args)
            if row.op == "push":
                need(args == ["%" + saved[len(stack)]] and not allocation, "Unbalanced paired helper save")
                stack += (args[0],)
            elif row.op == "pop":
                need(stack and args == [stack[-1]] and not allocation, "Unbalanced paired helper restore")
                stack = stack[:-1]
            elif args[-1:] == ["%rsp"] and row.op in ("sub", "add"):
                need(
                    name == PAIRED_LAYOUT and row.args == "$0xb8,%rsp" and len(stack) == 6,
                    "Unknown helper stack allocation",
                )
                need(allocation == (0 if row.op == "sub" else 0xB8), "Changed helper private-frame lifetime")
                allocation = 0xB8 if row.op == "sub" else 0
            elif row.op == "ret":
                need(not stack and not allocation, "Helper returns without restoring its caller")
            elif row.op not in PAIRED_NO_WRITE | decoder.BRANCHES:
                need(
                    row.op
                    in {
                        "mov",
                        "movabs",
                        "movq",
                        "movzbl",
                        "lea",
                        "xor",
                        "and",
                        "or",
                        "sub",
                        "add",
                        "shl",
                        "shr",
                        "setae",
                        "cmovae",
                    },
                    "Unknown paired helper effect",
                )
                destination = paired_register(args[-1])
                need(destination != "rsp", "Unknown helper stack write")
                if destination in PAIRED_SAVES:
                    need("%" + destination in stack, "Paired helper clobbers an unsaved callee register")
                if "(" in args[-1]:
                    slot = paired_slot(args[-1])
                    width = paired_width(row, args)
                    need(
                        name == PAIRED_LAYOUT
                        and allocation == 0xB8
                        and slot is not None
                        and 0 <= slot
                        and slot + width <= allocation,
                        "Paired helper writes caller/unknown memory",
                    )
                    stores.append((address, slot, width))
            state = stack, allocation
            for target in successors[address]:
                if target in states:
                    need(states[target] == state, "Helper stack preservation disagrees at CFG join")
                else:
                    states[target] = state
                    pending.append(target)
        # Classify even unreachable instructions; exact machine coverage prevents
        # hidden stores in ignored padding and the reachable pass checks lifetime.
        all_stores = [
            row.address
            for row in rows
            if decoder.arguments(row.args)[-1:]
            and "(" in decoder.arguments(row.args)[-1]
            and row.op not in PAIRED_NO_WRITE | decoder.BRANCHES
        ]
        need(set(all_stores) == {address for address, _, _ in stores}, "Unclassified paired helper memory write")
        effects[name] = dict(
            caller_memory_writes=0,
            private_stores=sorted(set(stores)),
            callee_saved_preserved=list(PAIRED_SAVES),
            calls=0,
        )
    return effects


def paired_gcc16_guard_contract(decoder, symbols, code):
    symbol = symbols[PAIRED_GUARD]
    # Both additions branch on carry before either unsigned endpoint comparison.
    # The only true results establish rhs >= lhs_end or lhs >= rhs_end.
    expected = [
        (0, "add", "%rdi,%rsi"), (3, "jb", 0x15), (5, "add", "%rdx,%rcx"),
        (8, "jb", 0x15), (0xA, "mov", "$0x1,%eax"), (0xF, "cmp", "%rsi,%rdx"),
        (0x12, "jb", 0x20), (0x14, "ret", ""), (0x15, "xor", "%eax,%eax"),
        (0x17, "ret", ""), (0x20, "cmp", "%rcx,%rdi"), (0x23, "setae", "%al"),
        (0x26, "ret", ""),
    ]
    for offset, op, args in expected:
        row = code[symbol.address + offset]
        need(row.op == op and (decoder.target_of(row) == symbol.address + args
             if isinstance(args, int) else row.args == args), "Changed GCC16 disjointness/overflow predicate")
    need({row.address for row in paired_rows(symbol, code) if row.op not in {"nopl", "nopw", "nop"}}
         == {symbol.address + offset for offset, _, _ in expected}, "Unclassified GCC16 guard instruction")
    return dict(endpoint_additions_overflow_checked=True, unsigned_disjoint_endpoints=True, caller_memory_writes=0)


PAIRED_GCC16_MACHINE_CONTRACTS = {
    '_ZNK6aurora4uefi10PageTables16verify_graphicalEmRKNS0_5BytesEPKNS0_18LocalApicAdmissionEPKNS0_20FramebufferAdmissionE': (2512, 561, '1c9f7755fd96fc7e1f56a44e82da2e5c036e1f89e1633e4610befa7fa1f07978'),
    '_ZZNK6aurora4uefi10PageTables16verify_graphicalEmRKNS0_5BytesEPKNS0_18LocalApicAdmissionEPKNS0_20FramebufferAdmissionEENKUlOT_mjmE_clIRKSD_EEbSC_mjm': (932, 203, 'f3000925e7753004a02924e2145c962d69f71c969ad69b0cbef9a306ff2c0f1d'),
    '_ZN6aurora4uefi20RuntimeLayoutProfileILm2EE5validEm': (714, 141, '0048919eda23f803e3088bc3174b10947d7e4533c5bb7254c9e7e4ef6cb4c3a6'),
    '_ZNK6aurora4uefi5Bytes3getEmj': (102, 31, 'eae393a9a39601eb8a2a32285728dfad1d5f3b3b80e3f9ace6a6f1ccdc3b0bc9'),
    '_ZN6aurora4uefi14expected_flagsEmRKNS0_5BytesE': (714, 138, '0ca4f24e09c658c0c58812b4ae35910e6947015f37972724622447873a942244'),
    '_ZN6aurora4uefi10PageTables33paired_graphical_storage_disjointEmmmm': (39, 14, '8af6ed02855c460056f9bf347ba5fcb4de0ad402e19021f58171119a431037cc'),
    '_ZNK6aurora4uefi10PageTables5entryEm': (132, 37, '9d8328eaaa13c372e732543f87f1c1d16e31411653ddb9f214b37636a6e73c71'),
    '_ZNK6aurora4uefi10PageTables11window_slotEv.isra.0': (115, 29, 'b66ac4f0516ae6d93820a6e70063f31b8d29bfc281750eb8bce77d4fe9b6346f'),
}


def paired_gcc16_exact_machine(decoder, symbols, code, starts, payload):
    need(payload is not None, "Paired snapshot/guard linked storage proof requires exact machine bytes")
    receipts = {}
    for name, (size, count, expected) in PAIRED_GCC16_MACHINE_CONTRACTS.items():
        need(name in symbols and symbols[name].size == size, "Changed paired audited function size: " + name)
        inventory = paired_machine_inventory(decoder, symbols[name], code, starts, payload)
        actual = hashlib.sha256(canonical(inventory).encode()).hexdigest()
        need(
            len(inventory) == count and actual == expected, "Changed paired audited instruction/byte inventory: " + name
        )
        receipts[name] = dict(bytes=size, instructions=count, normalized_sha256=actual)
    need(len(receipts) == 8, "Incomplete paired audited machine inventory")
    return receipts


def paired_require_slice(symbol, code, offset, operations):
    address = symbol.address + offset
    for operation in operations:
        row = code.get(address)
        need(row is not None and (row.op, row.args) == operation, "Changed paired protected instruction slice")
        address = row.next
    return address


def paired_root_storage(decoder, symbols, code, starts, functions):
    symbol = symbols[PAIRED_ROOT]
    rows = paired_rows(symbol, code)
    begin = symbol.address
    saves = [("push", "%" + register) for register in PAIRED_SAVES]
    paired_require_slice(symbol, code, 0, saves + [("sub", "$0xb8,%rsp")])
    paired_require_slice(
        symbol,
        code,
        0x11,
        [
            ("mov", "(%rdi),%r13"),
            ("mov", "0x8(%rdi),%r12"),
            ("mov", "0x10(%rdi),%rax"),
            ("mov", "%rsi,0x28(%rsp)"),
            ("mov", "%rcx,0x20(%rsp)"),
            ("mov", "%r8,0x18(%rsp)"),
            ("mov", "%r13,0x48(%rsp)"),
            ("mov", "%r12,0x50(%rsp)"),
            ("mov", "%rax,0x58(%rsp)"),
        ],
    )
    paired_require_slice(
        symbol,
        code,
        0x6A2,
        [("add", "$0xb8,%rsp")] + [("pop", "%" + r) for r in reversed(PAIRED_SAVES)] + [("ret", "")],
    )
    # The three observed qwords are captured before ANY store after the prologue.
    # Initial callee saves precede the observation interval and are not reused as
    # descriptor-field values. Field validation is pinned and dominates walking.
    successors, predecessors, dominators = paired_cfg(decoder, symbol, code)
    rootcall, bitmap_store = begin + 0x646, begin + 0x624
    captures = {begin + offset for offset in (0x11, 0x14, 0x18, 0x2B, 0x30, 0x35)}
    need(captures <= dominators[rootcall], "Partial or bypassed paired snapshot capture")
    required = {begin + offset for offset in (0x74, 0x79, 0x7D, 0x83, 0x85, 0x8B, 0x8F, 0x95, 0x98)}
    need(required <= dominators[rootcall], "Paired used/base/arena validation does not dominate root call")
    paired_require_slice(symbol, code, 0x74, [("lea", "-0x1(%r12),%rdx"), ("cmp", "$0xf,%rdx")])
    need(
        code[begin + 0x7D].op == "ja" and decoder.target_of(code[begin + 0x7D]) == begin + 0x6A0,
        "Paired snapshot used count lacks unsigned 1..16 rejection",
    )
    paired_require_slice(symbol, code, 0x8B, [("mov", "(%rsp),%rax"), ("add", "$0x11000,%rax"), ("cmp", "%rax,%r13")])
    need(
        code[begin + 0x98].op == "jne" and decoder.target_of(code[begin + 0x98]) == begin + 0x6A0,
        "Paired snapshot base is not the admitted arena table base",
    )
    objects = dict(bitmap=(0x38, 16), snapshot=(0x48, 24), helper_closure=(0x60, 24), closure=(0x78, 56))
    intervals = sorted((start, start + size) for start, size in objects.values())
    need(
        all(0 <= start < end <= 0xB8 for start, end in intervals)
        and all(left[1] <= right[0] for left, right in zip(intervals, intervals[1:])),
        "Paired protected root objects overlap or escape the real frame",
    )
    construction = {
        0x2B: (0x48, "captured_base"),
        0x30: (0x50, "captured_used"),
        0x35: (0x58, "captured_framebuffer"),
        0x51B: (0x88, ("frame", 0x60)),
        0x530: (0x60, ("frame", 0x30)),
        0x53F: (0x90, ("frame", 0x20)),
        0x551: (0x98, ("frame", 0x18)),
        0x55C: (0x68, "bytes"),
        0x561: (0x70, ("frame", 0x28)),
        0x566: (0x78, ("frame", 0x48)),
        0x56B: (0x80, ("frame", 0x38)),
        0x573: (0xA0, ("frame", 0x28)),
        0x57B: (0xA8, "bytes"),
    }
    guard_calls = (0x583, 0x5A0, 0x5BD, 0x5DA, 0x5F7, 0x614)
    guard_args = (
        ("original", 24, ("frame", 0x38), 16),
        ("original", 24, ("frame", 0x48), 24),
        ("original", 24, ("frame", 0x78), 56),
        (("frame", 0x48), 24, ("frame", 0x38), 16),
        (("frame", 0x48), 24, ("frame", 0x78), 56),
        (("frame", 0x38), 16, ("frame", 0x78), 56),
    )
    guard_states = dict(zip(guard_calls, guard_args))
    for offset in guard_calls:
        row = code[begin + offset]
        test = code[row.next]
        branch = code[test.next]
        need(
            row.op == "call"
            and starts.get(decoder.target_of(row)) == PAIRED_GUARD
            and (test.op, test.args) == ("test", "%al,%al")
            and branch.op == "je"
            and decoder.target_of(branch) == begin + 0x6A0,
            "Paired guard does not reject its false result",
        )
        need(
            {row.address, test.address, branch.address, branch.next} <= dominators[bitmap_store]
            and branch.next in dominators[rootcall],
            "Paired bitmap write/walk bypasses a successful storage guard",
        )
    paired_require_slice(
        symbol,
        code,
        0x621,
        [
            ("mov", "%r13,%rax"),
            ("movb", "$0x0,(%rax)"),
            ("add", "$0x1,%rax"),
            ("cmp", "%r12,%rax"),
        ],
    )
    loop = code[begin + 0x62E]
    need(
        loop.op == "jne"
        and decoder.target_of(loop) == bitmap_store
        and predecessors[bitmap_store] == {begin + 0x621, loop.address},
        "Paired bitmap initialization has an unbounded/bypassing loop",
    )
    paired_require_slice(
        symbol,
        code,
        0x630,
        [
            ("mov", "0x48(%rsp),%rbx"),
            ("xor", "%r8d,%r8d"),
            ("mov", "$0x3,%ecx"),
            ("mov", "%r15,%rsi"),
            ("mov", "%r15,%rdi"),
            ("mov", "%rbx,%rdx"),
        ],
    )
    # Symbolic pointer/capture lineage with byte-granular local slots. Facts meet
    # conservatively at every CFG join. Arithmetic invalidates origins; exact
    # loop contracts below summarize only the two bounded bitmap loops.
    initial = {name: None for name in (*PAIRED_CALLER_SAVED, *PAIRED_SAVES)}
    initial.update(rdi="original", rdx="bytes", rsi="arena", rcx="lapic", r8="framebuffer")
    registers = tuple(initial)
    initial = tuple(initial[name] for name in registers)
    states, pending = {begin: (initial, (None,) * 0xB8)}, [begin]
    observed_stores, observed_calls, constructed = {}, {}, set()

    def schedule(address, regs, memory):
        state = tuple(regs[name] for name in registers), tuple(memory)
        prior = states.get(address)
        if prior is not None:
            state = (
                tuple(a if a == b else None for a, b in zip(prior[0], state[0])),
                tuple(a if a == b else None for a, b in zip(prior[1], state[1])),
            )
            if state == prior:
                return
        states[address] = state
        pending.append(address)

    def remembered(memory, slot, size=8):
        parts = memory[slot : slot + size]
        if len(parts) == size and all(
            part is not None and part == (parts[0][0], index) for index, part in enumerate(parts)
        ):
            return parts[0][0]
        return None

    while pending:
        address = pending.pop()
        row, offset = code[address], address - begin
        regs, memory = states[address]
        regs, memory = dict(zip(registers, regs)), list(memory)
        args = decoder.arguments(row.args)
        if row.op == "ret":
            continue
        # Every field load from original-this belongs to the single observation
        # interval. No helper may subsequently receive it except as guard integer.
        for operand in args:
            for used in re.findall(r"%[a-z0-9]+", operand):
                if "(" in operand and regs.get(paired_register(used)) == "original":
                    need(
                        offset in (0x11, 0x14, 0x18) and used == "%rdi" and operand == args[0],
                        "Late original descriptor read or aliased original receiver",
                    )
        if row.op == "call":
            target = starts.get(decoder.target_of(row))
            need(target in (*PAIRED_HELPERS, PAIRED_WALK), "Unknown root helper effect")
            if target == PAIRED_GUARD:
                values = tuple(regs[name] for name in ("rdi", "rsi", "rdx", "rcx"))
                need(
                    offset in guard_states and values == guard_states[offset],
                    "Wrong storage guard object/extent/lineage",
                )
            elif target == PAIRED_WALK:
                need(
                    offset == 0x646
                    and (regs["rdi"], regs["rsi"], regs["rdx"], regs["rcx"], regs["r8"])
                    == (("frame", 0x78), ("frame", 0x78), "captured_base", 3, 0),
                    "Paired external root lacks snapshot/closure/level-three provenance",
                )
                for slot, value in ((0x78, ("frame", 0x48)), (0x80, ("frame", 0x38)), (0x88, ("frame", 0x60))):
                    need(remembered(memory, slot) == value, "Wrong paired immutable closure field")
            elif target == PAIRED_ENTRY:
                need(regs["rdi"] == ("frame", 0x48), "Paired member receiver is not the immutable snapshot")
            elif target == PAIRED_WINDOW:
                need(
                    (regs["rdi"], regs["rsi"]) == ("captured_base", "captured_used"),
                    "Paired scalarized window receiver lacks snapshot provenance",
                )
            else:
                need(
                    not any(
                        regs[name] == "original" or isinstance(regs[name], tuple)
                        for name in ("rdi", "rsi", "rdx", "rcx", "r8", "r9")
                    ),
                    "Paired private/original address escapes to an unrelated helper",
                )
            observed_calls[address] = target
            for name in PAIRED_CALLER_SAVED:
                regs[name] = None
        elif row.op in ("push", "pop"):
            need(offset < 0xA or 0x6A9 <= offset <= 0x6B1, "Unexpected root save/restore inside lifetime")
            if row.op == "pop":
                regs[paired_register(args[0])] = None
        elif args[-1:] == ["%rsp"]:
            need(
                offset in (0xA, 0x6A2) and row.op in ("sub", "add"), "Paired root frame moves during protected lifetime"
            )
        elif row.op not in PAIRED_NO_WRITE | decoder.BRANCHES and not (row.op == "xchg" and row.args == "%ax,%ax"):
            value, destination = None, paired_register(args[-1])
            if row.op in ("mov", "movabs") and len(args) == 2:
                source = paired_register(args[0])
                if args[0].startswith("$"):
                    value = int(args[0][1:], 16)
                elif source and args[0] == "%" + source:
                    value = regs[source]
                elif offset in (0x11, 0x14, 0x18):
                    value = {0x11: "captured_base", 0x14: "captured_used", 0x18: "captured_framebuffer"}[offset]
                elif paired_slot(args[0]) is not None:
                    value = remembered(memory, paired_slot(args[0]))
            elif row.op == "lea" and paired_slot(args[0]) is not None:
                value = ("frame", paired_slot(args[0]))
            elif row.op == "xor" and len(args) == 2 and args[0] == args[1]:
                value = 0
            if "(" in args[-1]:
                slot, width = paired_slot(args[-1]), paired_width(row, args)
                if slot is None:
                    need(
                        address == bitmap_store and (row.op, row.args) == ("movb", "$0x0,(%rax)"),
                        "Unclassified root external/aliased write",
                    )
                    need(
                        regs["r13"] == ("frame", 0x38) and regs["r12"] == ("frame", 0x48),
                        "Bitmap loop loses its exact [0,16) bounds",
                    )
                    observed_stores[address] = dict(object="bitmap", offset=0x38, bytes=16)
                else:
                    need(0 <= slot and slot + width <= 0xB8, "Root write escapes allocated frame")
                    overlap = [
                        name for name, (first, size) in objects.items() if slot < first + size and first < slot + width
                    ]
                    if overlap:
                        need(
                            offset in construction and width == 8 and construction[offset] == (slot, value),
                            "Root spill overlaps or changes immutable snapshot/closure",
                        )
                        constructed.add(offset)
                    memory[slot : slot + width] = [
                        (value, index) if value is not None else None for index in range(width)
                    ]
                    observed_stores[address] = dict(
                        object=overlap[0] if overlap else "private_scalar", offset=slot, bytes=width
                    )
            elif destination:
                # Partial writes destroy pointer provenance. Zero-extending
                # immediates/zero are scalar constants, never preserved pointers.
                regs[destination] = value if args[-1] == "%" + destination or isinstance(value, int) else None
            else:
                need(False, "Unknown paired root destination/effect")
        if offset == 0x659:
            # The inventory exit is taken only when its integer counter equals
            # the captured used count. This fact is used as window_slot's second
            # scalarized receiver; it is not assumed to survive any call.
            need(
                row.op == "je"
                and decoder.target_of(row) == begin + 0x6B4
                and code[begin + 0x64F].args == "0x50(%rsp),%rax"
                and code[begin + 0x656].args == "%rdx,%rax",
                "Changed postwalk used-count equality",
            )
            branch_regs = dict(regs, rdx="captured_used")
            schedule(begin + 0x6B4, branch_regs, memory)
            schedule(row.next, regs, memory)
        else:
            for target in successors[address]:
                schedule(target, regs, memory)
    need(
        constructed == set(construction) and {begin + offset for offset in construction} <= dominators[rootcall],
        "Missing or bypassed immutable paired object initialization",
    )
    all_stores = {
        row.address
        for row in rows
        if "(" in decoder.arguments(row.args)[-1] and row.op not in PAIRED_NO_WRITE | decoder.BRANCHES
    }
    need(all_stores == set(observed_stores), "Root contains an unclassified/unreachable memory write")
    need(
        set(observed_calls) == {call["address"] for call in functions[PAIRED_ROOT]["calls"]},
        "Root call inventories disagree",
    )
    external = [
        (name, call)
        for name, function in functions.items()
        for call in function["calls"]
        if call["target"] == PAIRED_WALK and name != PAIRED_WALK
    ]
    need(
        len(external) == 1
        and external[0][0] == PAIRED_ROOT
        and external[0][1]["address"] == rootcall
        and external[0][1]["kind"] == "call"
        and external[0][1]["level"] == 3,
        "Unexpected paired walker external caller or entry level",
    )
    return dict(
        symbol=PAIRED_ROOT,
        frame_bytes=0xB8,
        objects=objects,
        coherent_capture_qwords=3,
        postwalk_conditional_on_bounded_walker=True,
        guards=[begin + offset for offset in guard_calls],
        bitmap_initialization=bitmap_store,
        rootcall=rootcall,
        stores=observed_stores,
        snapshot_member_receivers=6,
        original_descriptor_integer_only=True,
    )


def paired_walker_storage(decoder, symbol, code, starts):
    rows = paired_frame_envelope(decoder, symbol, code)
    begin = symbol.address
    successors, predecessors, dominators = paired_cfg(decoder, symbol, code)
    # Original machine sequence: the descriptor comes only from closure[0], and
    # closure[8] is the root bitmap. Root validation gave 1 <= used <= 16 and a
    # page-aligned arena+0x11000 base below 2**32; hence end cannot overflow and
    # (table-base)>>12 is in [0,15]. All rejection edges go to the false return.
    prefix = [
        ("mov", "(%rdi),%rax"),
        ("mov", "%rdi,0x8(%rsp)"),
        ("mov", "(%rax),%rdx"),
        ("cmp", "%rdx,%r11"),
        ("jb", 0x200),
        ("mov", "0x8(%rax),%rax"),
        ("shl", "$0xc,%rax"),
        ("add", "%rdx,%rax"),
        ("cmp", "%rax,%r11"),
        ("jae", 0x200),
        ("test", "$0xfff,%r11d"),
        ("jne", 0x200),
        ("mov", "%r11,%rax"),
        ("sub", "%rdx,%rax"),
        ("mov", "0x8(%rsp),%rdx"),
        ("shr", "$0xc,%rax"),
        ("mov", "0x8(%rdx),%rdx"),
        ("cmpb", "$0x0,(%rdx,%rax,1)"),
        ("jne", 0x200),
        ("movb", "$0x1,(%rdx,%rax,1)"),
    ]
    address, protected = begin + 0x11, []
    for op, args in prefix:
        row = code[address]
        need(
            row.op == op and (decoder.target_of(row) == begin + args if isinstance(args, int) else row.args == args),
            "Changed bounded visited-index/snapshot instruction",
        )
        protected.append(address)
        address = row.next
    bitmap_store = protected[-1]
    need(
        bitmap_store == begin + 0x63 and set(protected[:-1]) <= dominators[bitmap_store],
        "Paired visited write bypasses a bounds/alignment check",
    )
    for previous, address in zip(protected, protected[1:]):
        need(predecessors[address] == {previous}, "Entry into middle of paired visited bounds proof")
    child = begin + 0x320
    need(bitmap_store in dominators[child], "Paired child bypasses visited storage proof")
    # Conditional local transformer, not a child memory proof: assuming smaller
    # descendants preserve caller memory, the known root closure reaches both
    # self arguments. The ascending engine below discharges that assumption at
    # each actual seed and rechecks pointer forwarding. Full-width spills retain
    # byte tags; every overlapping partial/wide write destroys those tags.
    initial = {name: None for name in (*PAIRED_CALLER_SAVED, *PAIRED_SAVES)}
    initial.update(rdi="closure", rsi="closure")
    registers = tuple(initial)
    states = {begin: (tuple(initial[name] for name in registers), (None,) * 0x48)}
    pending, calls, stores = [begin], set(), set()

    def schedule(address, regs, memory):
        state = tuple(regs[name] for name in registers), tuple(memory)
        prior = states.get(address)
        if prior is not None:
            state = (
                tuple(a if a == b else None for a, b in zip(prior[0], state[0])),
                tuple(a if a == b else None for a, b in zip(prior[1], state[1])),
            )
            if state == prior:
                return
        states[address] = state
        pending.append(address)

    while pending:
        address = pending.pop()
        row = code[address]
        regs, memory = states[address]
        regs, memory = dict(zip(registers, regs)), list(memory)
        args = decoder.arguments(row.args)
        if row.op == "ret":
            continue
        if row.op == "call":
            target = starts.get(decoder.target_of(row))
            if target == symbol.name:
                need(
                    address == child and regs["rdi"] == regs["rsi"] == "closure",
                    "Paired child closure is unknown, clobbered or not forwarded identically",
                )
            else:
                need(target == PAIRED_LEVEL_HELPER, "Unproved paired helper write contract")
                need(regs["rdi"] != "closure" and regs["rsi"] != "closure", "Paired closure escapes to scalar helper")
            calls.add(address)
            for name in PAIRED_CALLER_SAVED:
                regs[name] = None
        elif row.op not in PAIRED_NO_WRITE | decoder.BRANCHES:
            destination, value = paired_register(args[-1]), None
            if row.op == "mov" and len(args) == 2:
                source = paired_register(args[0])
                if source is not None and args[0] == "%" + source:
                    value = regs[source]
                slot = paired_slot(args[0])
                if slot is not None:
                    parts = memory[slot : slot + 8]
                    if parts == [("closure", index) for index in range(8)]:
                        value = "closure"
            if "(" in args[-1]:
                slot = paired_slot(args[-1])
                if slot is None:
                    need(address == bitmap_store, "Unclassified paired walker external/aliased write")
                else:
                    width = paired_width(row, args)
                    need(0 <= slot and slot + width <= 0x48, "Paired private spill escapes allocation")
                    memory[slot : slot + width] = [(value, index) if value else None for index in range(width)]
                stores.add(address)
            elif destination and destination != "rsp":
                regs[destination] = value if args[-1] == "%" + destination else None
        for target in successors[address]:
            schedule(target, regs, memory)
    need(calls == {row.address for row in rows if row.op == "call"}, "Incomplete paired walker call effect proof")
    need(
        stores
        == {
            row.address
            for row in rows
            if "(" in decoder.arguments(row.args)[-1] and row.op not in PAIRED_NO_WRITE | decoder.BRANCHES
        },
        "Unclassified paired walker write",
    )
    return dict(
        bitmap_store=bitmap_store,
        bitmap_index=[0, 15],
        private_spill_bytes=0x48,
        conditional_on_smaller_seed=True,
        stores=sorted(stores),
        calls=sorted(calls),
    )


def paired_gcc16_root_storage(decoder, symbols, code, starts, functions):
    symbol = symbols[PAIRED_ROOT]
    rows = paired_rows(symbol, code)
    begin = symbol.address
    frame = paired_gcc16_slot_frame(decoder, symbol, code)
    paired_require_slice(symbol, code, 0, [("sub", "$0xe8,%rsp"),
        ("mov", "(%rdi),%r10"), ("mov", "0x8(%rdi),%r9"), ("mov", "0x10(%rdi),%rax"),
        ("mov", "%rsi,0x38(%rsp)"), ("mov", "%rcx,0x30(%rsp)"), ("mov", "%r8,0x28(%rsp)"),
        ("mov", "%r10,0x58(%rsp)"), ("mov", "%r9,0x60(%rsp)"), ("mov", "%rax,0x68(%rsp)")])
    successors, predecessors, dominators = paired_cfg(decoder, symbol, code)
    rootcall, bitmap_store = begin + 0x7B5, begin + 0x789
    captures = {begin + offset for offset in (7, 0xA, 0xE, 0x21, 0x26, 0x2B)}
    need(captures <= dominators[rootcall], "Partial or bypassed GCC16 snapshot capture")
    paired_require_slice(symbol, code, 0xC1, [("lea", "-0x1(%r9),%rdx"), ("cmp", "$0xf,%rdx"),
        ("seta", "%dl"), ("xor", "$0x1,%eax"), ("or", "%al,%dl")])
    branch = code[begin + 0xD1]
    need(branch.op == "je" and decoder.target_of(branch) == begin + 0x100,
         "GCC16 used/layout validation does not select the valid successor")
    paired_require_slice(symbol, code, 0x100, [("lea", "0x11000(%r15),%rax"), ("cmp", "%rax,%r10")])
    branch = code[begin + 0x10A]
    need(branch.op == "jne" and decoder.target_of(branch) == begin + 0x420,
         "GCC16 snapshot base lacks arena-table rejection")
    required = {begin + offset for offset in (0xA7, 0xC1, 0xC5, 0xC9, 0xCC, 0xCF, 0xD1, 0x100, 0x107, 0x10A)}
    need(required <= dominators[rootcall], "GCC16 used/base/arena checks do not dominate walking")
    objects = dict(bitmap=(0x48, 16), snapshot=(0x58, 24), helper_closure=(0x70, 24), closure=(0x88, 56))
    intervals = sorted((start, start + size) for start, size in objects.values())
    need(
        all(0 <= start < end <= 0xE8 for start, end in intervals)
        and all(left[1] <= right[0] for left, right in zip(intervals, intervals[1:])),
        "Paired protected root objects overlap or escape the real frame",
    )
    construction = {
        0x21: (0x58, "captured_base"), 0x26: (0x60, "captured_used"), 0x2B: (0x68, "captured_framebuffer"),
        0x651: (0x98, ("frame", 0x70)), 0x663: (0x88, ("frame", 0x58)),
        0x670: (0xA0, ("frame", 0x30)), 0x67D: (0x70, ("frame", 0x40)),
        0x687: (0x90, ("frame", 0x48)), 0x694: (0xA8, ("frame", 0x28)),
        0x6A1: (0x78, "bytes"), 0x6A6: (0x80, ("frame", 0x38)),
        0x6AE: (0xB0, ("frame", 0x38)), 0x6B6: (0xB8, "bytes"),
    }
    guard_calls = (0x6BE, 0x6E0, 0x705, 0x729, 0x750, 0x777)
    guard_args = (
        ("original", 24, ("frame", 0x48), 16), ("original", 24, ("frame", 0x58), 24),
        ("original", 24, ("frame", 0x88), 56), (("frame", 0x58), 24, ("frame", 0x48), 16),
        (("frame", 0x58), 24, ("frame", 0x88), 56), (("frame", 0x48), 16, ("frame", 0x88), 56),
    )
    guard_states = dict(zip(guard_calls, guard_args))
    for offset in guard_calls:
        row = code[begin + offset]
        copy_result = code[row.next]
        need((copy_result.op, copy_result.args) == ("mov", "%eax,%r8d"), "Changed GCC16 guard result copy")
        test = code[copy_result.next]
        branch = code[test.next]
        need(
            row.op == "call"
            and starts.get(decoder.target_of(row)) == PAIRED_GUARD
            and (test.op, test.args) == ("test", "%al,%al")
            and branch.op == "je"
            and decoder.target_of(branch) == begin + 0x54A,
            "Paired guard does not reject its false result",
        )
        need(
            {row.address, test.address, branch.address, branch.next} <= dominators[bitmap_store]
            and branch.next in dominators[rootcall],
            "Paired bitmap write/walk bypasses a successful storage guard",
        )
    paired_require_slice(symbol, code, 0x787, [("xor", "%eax,%eax"),
        ("movb", "$0x0,0x48(%rsp,%rax,1)"), ("add", "$0x1,%rax"), ("cmp", "$0x10,%rax")])
    loop = code[begin + 0x796]
    need(loop.op == "jne" and decoder.target_of(loop) == bitmap_store
         and predecessors[bitmap_store] == {begin + 0x787, loop.address}, "Changed bounded GCC16 bitmap loop")
    paired_require_slice(symbol, code, 0x798, [("lea", "0x88(%rsp),%rsi"),
        ("mov", "0x58(%rsp),%rdx"), ("xor", "%r8d,%r8d"), ("mov", "$0x3,%ecx"),
        ("mov", "%rsi,%rdi"), ("mov", "0x58(%rsp),%r15")])
    # Symbolic pointer/capture lineage with byte-granular local slots. Facts meet
    # conservatively at every CFG join. Arithmetic invalidates origins; exact
    # loop contracts below summarize only the two bounded bitmap loops.
    initial = {name: None for name in (*PAIRED_CALLER_SAVED, *PAIRED_SAVES)}
    initial.update(rdi="original", rdx="bytes", rsi="arena", rcx="lapic", r8="framebuffer")
    registers = tuple(initial)
    initial = tuple(initial[name] for name in registers)
    states, pending = {begin: (initial, (None,) * 0xE8)}, [begin]
    observed_stores, observed_calls, constructed = {}, {}, set()

    def schedule(address, regs, memory):
        state = tuple(regs[name] for name in registers), tuple(memory)
        prior = states.get(address)
        if prior is not None:
            state = (
                tuple(a if a == b else None for a, b in zip(prior[0], state[0])),
                tuple(a if a == b else None for a, b in zip(prior[1], state[1])),
            )
            if state == prior:
                return
        states[address] = state
        pending.append(address)

    def remembered(memory, slot, size=8):
        parts = memory[slot : slot + size]
        if len(parts) == size and all(
            part is not None and part == (parts[0][0], index) for index, part in enumerate(parts)
        ):
            return parts[0][0]
        return None

    while pending:
        address = pending.pop()
        row, offset = code[address], address - begin
        regs, memory = states[address]
        regs, memory = dict(zip(registers, regs)), list(memory)
        args = decoder.arguments(row.args)
        if row.op == "ret":
            continue
        # Every field load from original-this belongs to the single observation
        # interval. No helper may subsequently receive it except as guard integer.
        for operand in args:
            for used in re.findall(r"%[a-z0-9]+", operand):
                if "(" in operand and regs.get(paired_register(used)) == "original":
                    need(
                        offset in (7, 0xA, 0xE) and used == "%rdi" and operand == args[0],
                        "Late original descriptor read or aliased original receiver",
                    )
        if offset == 0xC1:
            need(regs["r9"] == "captured_used", "GCC16 used validation lost captured snapshot lineage")
        if offset == 0x100:
            need(regs["r15"] == "arena", "GCC16 table-base computation lost original arena lineage")
        if offset == 0x107:
            need(regs["r10"] == "captured_base", "GCC16 base validation lost captured snapshot lineage")
        if row.op == "call":
            target = starts.get(decoder.target_of(row))
            need(target in (*PAIRED_HELPERS, PAIRED_ALIAS), "Unknown root helper effect")
            if target == PAIRED_GUARD:
                values = tuple(regs[name] for name in ("rdi", "rsi", "rdx", "rcx"))
                need(
                    offset in guard_states and values == guard_states[offset],
                    "Wrong storage guard object/extent/lineage",
                )
            elif target == PAIRED_ALIAS:
                need(
                    offset == 0x7B5
                    and (regs["rdi"], regs["rsi"], regs["rdx"], regs["rcx"], regs["r8"])
                    == (("frame", 0x88), ("frame", 0x88), "captured_base", 3, 0),
                    "Paired external root lacks snapshot/closure/level-three provenance",
                )
                for slot, value in ((0x88, ("frame", 0x58)), (0x90, ("frame", 0x48)), (0x98, ("frame", 0x70))):
                    need(remembered(memory, slot) == value, "Wrong paired immutable closure field")
            elif target == PAIRED_LAYOUT:
                need(regs["rdi"] == "arena", "GCC16 layout helper lost original arena argument")
            elif target == PAIRED_ENTRY:
                need(regs["rdi"] == ("frame", 0x58), "Paired member receiver is not the immutable snapshot")
            elif target == PAIRED_WINDOW:
                need(
                    (regs["rdi"], regs["rsi"]) == ("captured_base", "captured_used"),
                    "Paired scalarized window receiver lacks snapshot provenance",
                )
            else:
                need(
                    not any(
                        regs[name] == "original" or isinstance(regs[name], tuple)
                        for name in ("rdi", "rsi", "rdx", "rcx", "r8", "r9")
                    ),
                    "Paired private/original address escapes to an unrelated helper",
                )
            observed_calls[address] = target
            for name in PAIRED_CALLER_SAVED:
                regs[name] = None
        elif args[-1:] == ["%rsp"]:
            need(offset in (0, 0x50, 0xF6) and row.op in ("sub", "add"),
                 "GCC16 root frame moves during protected lifetime")
        elif row.op not in PAIRED_NO_WRITE | decoder.BRANCHES and not (row.op == "xchg" and row.args == "%ax,%ax"):
            value, destination = None, paired_register(args[-1])
            if row.op in ("mov", "movabs") and len(args) == 2:
                source = paired_register(args[0])
                if args[0].startswith("$"):
                    value = int(args[0][1:], 16)
                elif source and args[0] == "%" + source:
                    value = regs[source]
                elif offset in (7, 0xA, 0xE):
                    value = {7: "captured_base", 0xA: "captured_used", 0xE: "captured_framebuffer"}[offset]
                elif paired_slot(args[0]) is not None:
                    value = remembered(memory, paired_slot(args[0]))
            elif row.op == "lea" and paired_slot(args[0]) is not None:
                value = ("frame", paired_slot(args[0]))
            elif row.op == "xor" and len(args) == 2 and args[0] == args[1]:
                value = 0
            if "(" in args[-1]:
                slot, width = paired_slot(args[-1]), paired_width(row, args)
                if slot is None:
                    need(
                        address == bitmap_store and (row.op, row.args) == ("movb", "$0x0,0x48(%rsp,%rax,1)"),
                        "Unclassified root external/aliased write",
                    )
                    # The exact zero-start/increment/cmp16 loop above bounds this indexed store.
                    observed_stores[address] = dict(object="bitmap", offset=0x48, bytes=16)
                else:
                    need(0 <= slot and slot + width <= 0xE8, "Root write escapes allocated frame")
                    overlap = [
                        name for name, (first, size) in objects.items() if slot < first + size and first < slot + width
                    ]
                    if overlap:
                        need(
                            offset in construction and width == 8 and construction[offset] == (slot, value),
                            "Root spill overlaps or changes immutable snapshot/closure",
                        )
                        constructed.add(offset)
                    memory[slot : slot + width] = [
                        (value, index) if value is not None else None for index in range(width)
                    ]
                    observed_stores[address] = dict(
                        object=overlap[0] if overlap else "private_scalar", offset=slot, bytes=width
                    )
            elif destination:
                # Partial writes destroy pointer provenance. Zero-extending
                # immediates/zero are scalar constants, never preserved pointers.
                regs[destination] = value if args[-1] == "%" + destination or isinstance(value, int) else None
            else:
                need(False, "Unknown paired root destination/effect")
        if offset == 0x7CF:
            # The inventory exit is taken only when its integer counter equals
            # the captured used count. This fact is used as window_slot's second
            # scalarized receiver; it is not assumed to survive any call.
            need(
                row.op == "je"
                and decoder.target_of(row) == begin + 0x81A
                and code[begin + 0x7C5].args == "0x60(%rsp),%rax"
                and code[begin + 0x7CC].args == "%rcx,%rax",
                "Changed postwalk used-count equality",
            )
            branch_regs = dict(regs, rcx="captured_used")
            schedule(begin + 0x81A, branch_regs, memory)
            schedule(row.next, regs, memory)
        else:
            for target in successors[address]:
                schedule(target, regs, memory)
    need(
        constructed == set(construction) and {begin + offset for offset in construction} <= dominators[rootcall],
        "Missing or bypassed immutable paired object initialization",
    )
    all_stores = {
        row.address
        for row in rows
        if "(" in decoder.arguments(row.args)[-1] and row.op not in PAIRED_NO_WRITE | decoder.BRANCHES
    }
    need(all_stores == set(observed_stores), "Root contains an unclassified/unreachable memory write")
    need(
        set(observed_calls) == {call["address"] for call in functions[PAIRED_ROOT]["calls"]},
        "Root call inventories disagree",
    )
    external = [
        (name, call)
        for name, function in functions.items()
        for call in function["calls"]
        if call["target"] == PAIRED_ALIAS and name != PAIRED_ALIAS
    ]
    need(
        len(external) == 1
        and external[0][0] == PAIRED_ROOT
        and external[0][1]["address"] == rootcall
        and external[0][1]["kind"] == "call"
        and external[0][1]["level"] == 3,
        "Unexpected paired walker external caller or entry level",
    )
    return dict(
        symbol=PAIRED_ROOT,
        frame_bytes=0xE8,
        frame_preservation=frame,
        objects=objects,
        coherent_capture_qwords=3,
        postwalk_conditional_on_bounded_walker=True,
        guards=[begin + offset for offset in guard_calls],
        bitmap_initialization=bitmap_store,
        rootcall=rootcall,
        stores=observed_stores,
        snapshot_member_receivers=6,
        original_descriptor_integer_only=True,
    )


def paired_gcc16_walker_storage(decoder, symbol, code, starts):
    paired_gcc16_slot_frame(decoder, symbol, code)
    rows = paired_rows(symbol, code)
    begin = symbol.address
    successors, predecessors, dominators = paired_cfg(decoder, symbol, code)
    # Original machine sequence: the descriptor comes only from closure[0], and
    # closure[8] is the root bitmap. Root validation gave 1 <= used <= 16 and a
    # page-aligned arena+0x11000 base below 2**32; hence end cannot overflow and
    # (table-base)>>12 is in [0,15]. All rejection edges go to the false return.
    prefix = [
        ("mov", "(%rdi),%rax"), ("mov", "%r12,0x58(%rsp)"), ("mov", "%rdx,%r12"),
        ("mov", "(%rax),%rdx"), ("cmp", "%rdx,%r12"), ("jb", 0x220),
        ("mov", "0x8(%rax),%rax"), ("shl", "$0xc,%rax"), ("add", "%rdx,%rax"),
        ("cmp", "%rax,%r12"), ("jae", 0x220), ("test", "$0xfff,%r12d"), ("jne", 0x220),
        ("mov", "%r12,%rax"), ("sub", "%rdx,%rax"), ("mov", "0x8(%rdi),%rdx"),
        ("shr", "$0xc,%rax"), ("cmpb", "$0x0,(%rdx,%rax,1)"), ("jne", 0x220),
        ("mov", "%r13,0x60(%rsp)"), ("mov", "%ecx,%r9d"), ("xor", "%r13d,%r13d"),
        ("mov", "%r14,0x68(%rsp)"), ("mov", "%r12,%r14"), ("mov", "%rbx,0x48(%rsp)"),
        ("mov", "%rbp,0x50(%rsp)"), ("mov", "%r15,0x70(%rsp)"),
        ("movb", "$0x1,(%rdx,%rax,1)"),
    ]
    address, protected = begin + 4, []
    for op, args in prefix:
        row = code[address]
        need(row.op == op and (decoder.target_of(row) == begin + args if isinstance(args, int) else row.args == args),
             "Changed GCC16 bounded visited-index/snapshot instruction")
        protected.append(address)
        address = row.next
    bitmap_store = protected[-1]
    need(bitmap_store == begin + 0x76 and set(protected[:-1]) <= dominators[bitmap_store],
         "GCC16 visited write bypasses a bounds/alignment check")
    for previous, address in zip(protected, protected[1:]):
        need(predecessors[address] == {previous}, "Entry into middle of GCC16 visited bounds proof")
    child = begin + 0x353
    need(bitmap_store in dominators[child], "Paired child bypasses visited storage proof")
    # Conditional local transformer, not a child memory proof: assuming smaller
    # descendants preserve caller memory, the known root closure reaches both
    # self arguments. The ascending engine below discharges that assumption at
    # each actual seed and rechecks pointer forwarding. Full-width spills retain
    # byte tags; every overlapping partial/wide write destroys those tags.
    initial = {name: None for name in (*PAIRED_CALLER_SAVED, *PAIRED_SAVES)}
    initial.update(rdi="closure", rsi="closure")
    registers = tuple(initial)
    states = {begin: (tuple(initial[name] for name in registers), (None,) * 0x78)}
    pending, calls, stores = [begin], set(), set()

    def schedule(address, regs, memory):
        state = tuple(regs[name] for name in registers), tuple(memory)
        prior = states.get(address)
        if prior is not None:
            state = (
                tuple(a if a == b else None for a, b in zip(prior[0], state[0])),
                tuple(a if a == b else None for a, b in zip(prior[1], state[1])),
            )
            if state == prior:
                return
        states[address] = state
        pending.append(address)

    while pending:
        address = pending.pop()
        row = code[address]
        regs, memory = states[address]
        regs, memory = dict(zip(registers, regs)), list(memory)
        args = decoder.arguments(row.args)
        if row.op == "ret":
            continue
        if row.op == "call":
            target = starts.get(decoder.target_of(row))
            if target == symbol.name:
                need(
                    address == child and regs["rdi"] == regs["rsi"] == "closure",
                    "Paired child closure is unknown, clobbered or not forwarded identically",
                )
            else:
                need(target == PAIRED_LEVEL_HELPER, "Unproved paired helper write contract")
                need(regs["rdi"] != "closure" and regs["rsi"] != "closure", "Paired closure escapes to scalar helper")
            calls.add(address)
            for name in PAIRED_CALLER_SAVED:
                regs[name] = None
        elif row.op not in PAIRED_NO_WRITE | decoder.BRANCHES and not (row.op == "xchg" and row.args == "%ax,%ax"):
            destination, value = paired_register(args[-1]), None
            if row.op == "mov" and len(args) == 2:
                source = paired_register(args[0])
                if source is not None and args[0] == "%" + source:
                    value = regs[source]
                slot = paired_slot(args[0])
                if slot is not None:
                    parts = memory[slot : slot + 8]
                    if parts == [("closure", index) for index in range(8)]:
                        value = "closure"
            if "(" in args[-1]:
                slot = paired_slot(args[-1])
                if slot is None:
                    need(address == bitmap_store, "Unclassified paired walker external/aliased write")
                else:
                    width = paired_width(row, args)
                    need(0 <= slot and slot + width <= 0x78, "Paired private spill escapes allocation")
                    memory[slot : slot + width] = [(value, index) if value else None for index in range(width)]
                stores.add(address)
            elif destination and destination != "rsp":
                regs[destination] = value if args[-1] == "%" + destination else None
        for target in successors[address]:
            schedule(target, regs, memory)
    need(calls == {row.address for row in rows if row.op == "call"}, "Incomplete paired walker call effect proof")
    need(
        stores
        == {
            row.address
            for row in rows
            if "(" in decoder.arguments(row.args)[-1] and row.op not in PAIRED_NO_WRITE | decoder.BRANCHES
        },
        "Unclassified paired walker write",
    )
    return dict(
        bitmap_store=bitmap_store,
        bitmap_index=[0, 15],
        private_spill_bytes=0x78,
        conditional_on_smaller_seed=True,
        stores=sorted(stores),
        calls=sorted(calls),
    )


def paired_gcc16_level_induction(decoder, symbol, code, starts, generic, bitmap_stores=(), storage=None):
    """Original-instruction ECX/R9D and byte-spill fixed points for seeds 0..3.

    bitmap_stores must be the exact addresses whose bounded, root-owned target
    was proved by the linked root and local walker contract. With storage set,
    each seed also establishes caller-memory preservation and closure forwarding;
    a child may preserve spills only after its smaller seed was established.
    Without storage this is solely a pure level constituent, never admission.
    """
    paired_gcc16_slot_frame(decoder, symbol, code)
    rows = paired_rows(symbol, code)
    begin, end = symbol.address, symbol.address + symbol.size
    body = {row.address: row for row in rows}
    bitmap_stores = frozenset(bitmap_stores)
    need(bitmap_stores <= set(body), "Bitmap write summary references another function")
    call_rows = [row for row in rows if row.op == "call"]
    targets = [starts.get(decoder.target_of(row)) for row in call_rows]
    need(
        targets.count(symbol.name) == 1 and targets.count(PAIRED_LEVEL_HELPER) == 2 and len(targets) == 3,
        "Unexpected paired helper/self-call inventory",
    )
    generic_calls = {row["address"]: row for row in generic["calls"]}
    need(set(generic_calls) == {row.address for row in call_rows}, "Paired generic call inventory mismatch")

    def register(operand):
        if operand in ("%rcx", "%ecx", "%cx", "%cl", "%ch"):
            return 0
        if operand in ("%r9", "%r9d", "%r9w", "%r9b"):
            return 1
        return None

    def width(operand):
        if re.fullmatch(r"%r(?:ax|bx|cx|dx|si|di|bp|[89]|1[0-5])", operand):
            return 8
        if re.fullmatch(r"%(?:e(?:ax|bx|cx|dx|si|di|bp)|r(?:[89]|1[0-5])d)", operand):
            return 4
        if re.fullmatch(r"%(?:ax|bx|cx|dx|si|di|bp|r(?:[89]|1[0-5])w)", operand):
            return 2
        if re.fullmatch(r"%(?:al|ah|bl|bh|cl|ch|dl|dh|sil|dil|bpl|r(?:[89]|1[0-5])b)", operand):
            return 1
        return None

    def stack_slot(operand):
        match = re.fullmatch(r"(0x[0-9a-f]+)?\(%rsp\)", operand)
        return int(match[1] or "0", 16) if match else None

    if storage is not None:
        need(
            storage["walker"]["conditional_on_smaller_seed"] is True
            and bitmap_stores == {storage["walker"]["bitmap_store"]}
            and set(storage["helpers"]) == set(PAIRED_HELPERS)
            and all(effect["caller_memory_writes"] == 0 for effect in storage["helpers"].values()),
            "Missing paired local storage/helper premise",
        )
    levels = {}
    readonly = {"cmp", "cmpb", "test", "nop", "nopl", "nopw", "cs", "data16"}
    preserve_flags = {
        "setae",
        "xchg",
        "mov",
        "movabs",
        "movb",
        "movl",
        "movq",
        "movw",
        "movzbl",
        "lea",
        "push",
        "pop",
        "nop",
        "nopl",
        "nopw",
        "cs",
        "data16",
    }
    for seed in range(4):
        # Byte precision prevents adjacent qword data spills from being treated
        # as preserving overlapping dword level facts. No address-only memo.
        closure_seed = ("closure", "closure") if storage is not None else (None, None)
        states = {begin: (seed, None, None, (None,) * 0x78, closure_seed)}
        pending, visited, calls, returns = [begin], set(), {}, set()

        def schedule(address, state):
            need(begin <= address < end and address in body, "Paired CFG leaves body or enters an instruction interior")
            prior = states.get(address)
            if prior is not None:
                state = tuple(a if a == b else None for a, b in zip(prior[:3], state[:3])) + (
                    tuple(a if a == b else None for a, b in zip(prior[3], state[3])),
                    tuple(a if a == b else None for a, b in zip(prior[4], state[4])),
                )
                if state == prior:
                    return
            states[address] = state
            pending.append(address)

        while pending:
            address = pending.pop()
            row = body[address]
            need(
                row.next <= end and row.op in PAIRED_LEVEL_OPS | {"setae", "xchg"} | decoder.BRANCHES,
                "Unreviewed paired level instruction or extent",
            )
            need(row.op != "xchg" or row.args == "%ax,%ax", "Unknown GCC16 level exchange")
            visited.add(address)
            cx, r9, zf, memory, closure = states[address]
            values, memory, next_closure = [cx, r9], list(memory), list(closure)
            args = decoder.arguments(row.args)
            next_zf = zf if row.op in preserve_flags | decoder.BRANCHES else None
            if row.op == "ret":
                returns.add(address)
                continue
            if row.op == "call":
                target = starts.get(decoder.target_of(row))
                call = dict(generic_calls[address])
                if target == symbol.name:
                    need(
                        seed > 0 and seed - 1 in levels and cx == seed - 1,
                        "Paired child lacks previously proved decreasing level",
                    )
                    if storage is not None:
                        need(
                            levels[cx].get("caller_memory_contract") is True and closure == ("closure", "closure"),
                            "Paired child lacks established memory contract or identical closure",
                        )
                    call["level"] = cx
                else:
                    need(target == PAIRED_LEVEL_HELPER, "Unexpected paired level callee")
                    if storage is not None:
                        need("closure" not in closure, "Paired closure escapes to scalar helper")
                    call["level"] = None
                previous = calls.get(address)
                need(previous is None or previous == call, "Paired call level facts disagree at a join")
                calls[address] = call
                # No caller-saved level/flag survives even a read-only helper.
                schedule(row.next, (None, None, None, tuple(memory), (None, None)))
                continue
            if row.op in decoder.BRANCHES:
                target = decoder.target_of(row)
                taken = (
                    zf if row.op in ("je", "jz") else (not zf if zf is not None and row.op in ("jne", "jnz") else None)
                )
                if row.op == "jmp" or taken is not False:
                    schedule(target, (cx, r9, zf, tuple(memory), closure))
                if row.op != "jmp" and taken is not True:
                    schedule(row.next, (cx, r9, zf, tuple(memory), closure))
                continue
            if args and row.op not in readonly:
                closure_register = paired_register(args[-1])
                if closure_register in ("rdi", "rsi"):
                    destination = ("rdi", "rsi").index(closure_register)
                    next_closure[destination] = None
                    if row.op == "mov" and args[-1] == "%" + closure_register:
                        source = paired_register(args[0])
                        if source in ("rdi", "rsi") and args[0] == "%" + source:
                            next_closure[destination] = closure[("rdi", "rsi").index(source)]
                        else:
                            offset = stack_slot(args[0])
                            if offset is not None and memory[offset : offset + 8] == [("closure", i) for i in range(8)]:
                                next_closure[destination] = "closure"
                destination = register(args[-1])
                if destination is not None:
                    values[destination] = None
                    if row.op == "mov" and len(args) == 2 and args[-1] in ("%ecx", "%r9d"):
                        source = register(args[0])
                        if source is not None and args[0] in ("%ecx", "%r9d"):
                            values[destination] = (cx, r9)[source]
                        else:
                            offset = stack_slot(args[0])
                            if offset in frozenset((0x18, 0x28, 0x38)) and offset + 4 <= 0x78:
                                content = memory[offset : offset + 4]
                                if len(content) == 4 and all(type(value) is int for value in content):
                                    value = int.from_bytes(bytes(content), "little")
                                    values[destination] = value if value <= 3 else None
                    elif row.op == "lea" and row.args == "-0x1(%r9),%ecx" and r9 is not None:
                        values[0] = (r9 - 1) & 0xFFFFFFFF
                if "(" in args[-1]:
                    offset = stack_slot(args[-1])
                    if offset is None:
                        need(
                            address in bitmap_stores and row.op == "movb" and row.args == "$0x1,(%rdx,%rax,1)",
                            "Unproved paired external/aliased write",
                        )
                    else:
                        size = {"movb": 1, "movw": 2, "movl": 4, "movq": 8}.get(row.op)
                        if row.op == "mov" and len(args) == 2:
                            size = width(args[0])
                        need(
                            size is not None and 0 <= offset and offset + size <= 0x78,
                            "Unbounded or unknown paired spill write width/range",
                        )
                        memory[offset : offset + size] = [None] * size
                        if row.op == "mov" and args[0] in ("%ecx", "%r9d") and offset in frozenset((0x18, 0x28, 0x38)):
                            value = (cx, r9)[register(args[0])]
                            if value is not None:
                                memory[offset : offset + 4] = value.to_bytes(4, "little")
                        if row.op == "mov" and size == 8 and args[0] in ("%rdi", "%rsi"):
                            value = closure[("%rdi", "%rsi").index(args[0])]
                            if value == "closure":
                                memory[offset : offset + 8] = [("closure", i) for i in range(8)]
            if row.op == "test" and row.args == "%r9d,%r9d" and r9 is not None:
                next_zf = r9 == 0
            schedule(row.next, (values[0], values[1], next_zf, tuple(memory), tuple(next_closure)))
        recursive = [row for row in calls.values() if row["target"] == symbol.name]
        need(
            not recursive if seed == 0 else len(recursive) == 1 and recursive[0]["level"] == seed - 1,
            "Paired recursion is not bounded for every seed",
        )
        need(returns, "Paired seed has no returning path")
        levels[seed] = dict(
            generic,
            calls=sorted(calls.values(), key=lambda row: row["address"]),
            instructions=len(visited),
            returns=len(returns),
            seed=seed,
            private_spill_bytes=0x78,
            caller_saved_killed=True,
            caller_memory_contract=storage is not None,
            established_child_seed=None if seed == 0 else seed - 1,
            identical_closure_forwarding=storage is not None,
        )
    return levels


def paired_linked_storage(decoder, functions, symbols, code, starts, payload):
    inventory = paired_exact_machine(decoder, symbols, code, starts, payload)
    helpers = paired_helper_effects(decoder, symbols, code, functions)
    root = paired_root_storage(decoder, symbols, code, starts, functions)
    walker = paired_walker_storage(decoder, symbols[PAIRED_WALK], code, starts)
    # Each descendant saves six qwords and allocates 72 bytes below its incoming
    # return address. Its only caller-memory write is within the root bitmap.
    # Read-only helpers and bounded private helper frames cannot reach caller
    # objects, even if input reads alias caller frames. No frame-address escape
    # is admitted by paired_frame_envelope. Ascending induction can now preserve
    # spill facts, snapshot, closure and the bitmap base across a proven child.
    return dict(machine=inventory, helpers=helpers, root=root, walker=walker)


def paired_recursion_proofs(decoder, functions, symbols, code, starts, paired_walk, payload=None, associations=None):
    legacy = decoder.WALK
    need(
        paired_walk != legacy and {legacy, paired_walk} <= set(functions), "Two separate concrete page walkers required"
    )
    # The original legacy contract remains authoritative and unchanged.
    legacy_levels, legacy_roots = decoder.recursion_proof(functions, symbols, code, starts, associations)
    need(paired_walk in (PAIRED_WALK, PAIRED_ALIAS), "Unknown concrete paired walker identity")
    if paired_walk == PAIRED_WALK:
        storage = paired_linked_storage(decoder, functions, symbols, code, starts, payload)
        induction = paired_level_induction
    else:
        machine = paired_gcc16_exact_machine(decoder, symbols, code, starts, payload)
        helpers = paired_gcc16_helper_effects(decoder, symbols, code, functions)
        guard = paired_gcc16_guard_contract(decoder, symbols, code)
        root = paired_gcc16_root_storage(decoder, symbols, code, starts, functions)
        walker = paired_gcc16_walker_storage(decoder, symbols[PAIRED_ALIAS], code, starts)
        storage = dict(machine=machine, helpers=helpers, guard=guard, root=root, walker=walker)
        induction = paired_gcc16_level_induction
    paired_readonly_leaf(decoder, PAIRED_LEVEL_HELPER, symbols, code, functions)
    levels = induction(
        decoder,
        symbols[paired_walk],
        code,
        starts,
        functions[paired_walk],
        (storage["walker"]["bitmap_store"],),
        storage=storage,
    )
    return dict(
        legacy=dict(symbol=legacy, levels=legacy_levels, roots=legacy_roots),
        paired=dict(
            symbol=paired_walk,
            levels=levels,
            storage=storage,
            roots=[dict(caller=PAIRED_ROOT, address=storage["root"]["rootcall"], initial_level=3)],
        ),
    )


def verify_wait_closure(code, named, functions, language_functions, payload, linked_functions):
    begin, end = (named[key].address for key in ("uefi_console_poll_begin", "uefi_console_poll_end"))
    need(
        0 < begin < end <= len(payload) and payload[begin:end] == bytes.fromhex("fbf4fa"),
        "Changed exact timer wait interval",
    )
    need(
        [row.address for row in code.values() if row.op == "sti"] == [begin],
        "Interrupt enable outside the sole admitted wait",
    )
    need(
        all(address in code for address in (begin, begin + 1, begin + 2))
        and [(code[address].op, code[address].args, code[address].size) for address in (begin, begin + 1, begin + 2)]
        == [("sti", "", 1), ("hlt", "", 1), ("cli", "", 1)],
        "Wait decode/bytes mismatch",
    )
    owners = [
        name
        for name, symbol in linked_functions.items()
        if symbol.address <= begin < end <= symbol.address + symbol.size
    ]
    need(len(owners) == 1 and "wait_for_sample" in owners[0], "Ambiguous or replaced wait owner")
    reachable = verify_irq_reachability(functions, language_functions)
    return owners[0], reachable


def expected_language_functions():
    # Exact current source declarations, using compiler/modules.hpp's reviewed
    # private naming. Root scalar helpers retain leaf names in the sealed graph.
    def mangle(kind, scope, name):
        namespace = "0_" if not scope else "1_" + str(len(scope)) + scope
        return "__au_" + kind + "_m1_24kernel_graphical_console_n" + namespace + "_d" + str(len(name)) + name

    names = {
        BRIDGE,
        VALUE_BRIDGE,
        "aurora_kernel_value",
        "glyph_bits",
        "graphical_glyph_bits",
        "text_scale",
    } | REFLECTION_HELPERS
    names.update(mangle("v", "", name) for name in ("graphical_console", "draw_glyph", "draw_cell"))
    methods = {
        "Line64": ("finish", "reject", "consume"),
        "TextCells": (
            "initialize",
            "append",
            "erase",
            "response",
            "hide_cursor",
            "at",
            "cursor_at",
            "dirty",
            "commit",
            "finish_paint",
            "show_ready",
            "show_help",
            "show_status",
            "show_unknown",
            "show_rejected",
            "show_exit",
            "show_empty",
            "show_bounded",
        ),
    }
    for scope, items in methods.items():
        names.add(mangle("k", scope, scope))
        names.update(mangle("m", scope, name) for name in items)
    return names


def verify_language_object(language):
    imports = {row.name for row in language.symbols if row.name and row.section == 0}
    need(
        imports == {"__au_runtime_console_next", "__au_runtime_display_pixel"},
        "Unexpected generated language import inventory",
    )
    need(
        set(language.functions) == expected_language_functions(),
        "Unexpected generated language module/function inventory",
    )
    rows = subprocess.check_output(["readelf", "-sW", language.path], text=True).splitlines()
    bindings = {}
    for line in rows:
        fields = line.split()
        if len(fields) == 8 and fields[3] == "FUNC" and fields[6] != "UND":
            need(fields[7] not in bindings, "Duplicate generated ELF function")
            bindings[fields[7]] = (fields[4], fields[5])
    need(set(bindings) == set(language.functions), "Generated ELF binding inventory mismatch")
    for name, binding in bindings.items():
        need(
            binding
            == (
                ("GLOBAL", "HIDDEN")
                if name in (BRIDGE, VALUE_BRIDGE)
                else ("GLOBAL", "DEFAULT")
                if name in REFLECTION_HELPERS
                else ("LOCAL", "DEFAULT")
            ),
            "Generated function escaped private ELF binding: " + name,
        )
    return sorted(imports)


def verify_reflection_body(decoder, symbol, rows, payload):
    """Closed constant lookup: exact bytes, complete coverage, no authority/memory."""
    need(
        symbol.name in REFLECTION_HELPERS and rows and symbol.address >= 0 and symbol.size > 0,
        "Unknown or empty reflection helper",
    )
    cursor = symbol.address
    for row in rows:
        need(row.address == cursor and row.size > 0, "Reflection instruction coverage gap/overlap")
        cursor += row.size
    need(cursor == symbol.address + symbol.size <= len(payload), "Reflection extent/coverage mismatch")

    def raw(row):
        return payload[row.address : row.address + row.size]

    def immediate(row, op, register):
        match = re.fullmatch(r"\$(0x[0-9a-f]+|[0-9]+),%" + register, row.args)
        need(row.op == op and match, "Reflection operand is not an immediate scalar")
        value = int(match[1], 0)
        need(0 <= value <= 0x7FFFFFFF, "Reflection scalar exceeds closed imm32 range")
        if op == "cmp":
            expected = [bytes.fromhex("4883ff") + bytes([value])] if value <= 127 else []
            expected += [bytes.fromhex("4881ff") + value.to_bytes(4, "little")]
        else:
            expected = [bytes.fromhex("48c7c0") + value.to_bytes(4, "little")]
        need(raw(row) in expected, "Reflection immediate opcode/bytes mismatch")
        return value

    index, keys, targets = 0, [], []
    while index < len(rows) and rows[index].op == "cmp":
        value = immediate(rows[index], "cmp", "rdi")
        need(value not in keys and index + 1 < len(rows), "Duplicate/truncated reflection comparison")
        branch = rows[index + 1]
        need(branch.op == "je", "Reflection comparison must have an equality branch")
        target = decoder.target_of(branch)
        branch_bytes = raw(branch)
        if branch.size == 6 and branch_bytes[:2] == bytes.fromhex("0f84"):
            displacement = int.from_bytes(branch_bytes[2:], "little", signed=True)
        elif branch.size == 2 and branch_bytes[:1] == b"\x74":
            displacement = int.from_bytes(branch_bytes[1:], "little", signed=True)
        else:
            raise ValueError("Reflection equality-branch opcode/bytes mismatch")
        need(
            type(target) is int
            and target == branch.address + branch.size + displacement
            and target > branch.address
            and target not in targets,
            "Reflection external/backward/duplicate or misdecoded branch",
        )
        keys.append(value)
        targets.append(target)
        index += 2
    need(keys, "Reflection helper lacks a closed lookup ladder")
    arms = []
    while index < len(rows):
        row = rows[index]
        arms.append(row.address)
        if row.op == "ud2":
            need(not row.args and raw(row) == bytes.fromhex("0f0b"), "Reflection trap bytes/operands mismatch")
            index += 1
            continue
        if row.op == "xor":
            need(
                row.args == "%rax,%rax" and raw(row) == bytes.fromhex("4831c0"),
                "Reflection zero return must be exact register self-zeroing",
            )
        else:
            immediate(row, "mov", "rax")
        need(
            index + 1 < len(rows)
            and rows[index + 1].op == "ret"
            and not rows[index + 1].args
            and raw(rows[index + 1]) == b"\xc3",
            "Reflection return arm must terminate exactly",
        )
        index += 2
    need(
        len(arms) == len(targets) + 1 and targets == arms[1:],
        "Reflection branches must cover only complete internal return arms",
    )
    return dict(
        symbol=symbol.name,
        address=symbol.address,
        bytes=symbol.size,
        cases=len(keys),
        arms=len(arms),
        calls=0,
        data_accesses=0,
    )


def verify_generated_divisions(functions, code, payload):
    """Exactly two register-only signed division pairs in draw_cell's arithmetic.

    CQTO writes RDX from RAX's sign and preserves flags. IDIV R11 writes only
    RAX/RDX and leaves flags undefined. Neither modifies stack, RCX or R14, so
    the existing conservative scalar/flag analysis is sufficient after this
    complete byte, operand, ownership and adjacency check. Synchronous faults
    retain the ordinary fault-path budget.
    """
    owner = "__au_v_m1_24kernel_graphical_console_n0__d9draw_cell"
    need(owner in functions, "Missing generated division owner")
    symbol = functions[owner]
    forms = [row for _, row in sorted(code.items()) if row.op in ("cqto", "idiv")]
    need(len(forms) == 4, "Unexpected generated division instruction inventory")
    evidence = []
    for index in (0, 2):
        sign, divide = forms[index : index + 2]
        need(
            symbol.address <= sign.address < divide.address < divide.next <= symbol.address + symbol.size
            and sign.op == "cqto"
            and not sign.args
            and sign.size == 2
            and payload[sign.address : sign.next] == bytes.fromhex("4899")
            and divide.address == sign.next
            and divide.op == "idiv"
            and divide.args == "%r11"
            and divide.size == 3
            and payload[divide.address : divide.next] == bytes.fromhex("49f7fb"),
            "Unknown generated signed-division bytes/operands/owner/pair",
        )
        evidence.append(
            dict(
                owner=owner,
                sign_address=sign.address,
                divide_address=divide.address,
                bytes="489949f7fb",
                stack_effect=0,
                clobbers=["rax", "rdx"],
            )
        )
    return evidence


def verify_private_abi(decoder, linked, code, starts, language_names, functions):
    def body(name):
        symbol = linked.functions[name]
        return [
            row for address, row in sorted(code.items()) if symbol.address <= address < symbol.address + symbol.size
        ]

    value_body = body(VALUE_BRIDGE)
    verify_value_bridge_body(decoder, value_body, starts)
    entry = body(ENTRY)
    need(
        [(row.op, row.args) for row in entry[:2]] == [("push", "%rbp"), ("mov", "%rsp,%rbp")],
        "Changed paired entry frame",
    )
    need(
        len(entry) > 5 and entry[2].op == "sub" and re.fullmatch(r"\$(?:0x[0-9a-f]+|[0-9]+),%rsp", entry[2].args),
        "Missing paired entry allocation",
    )
    allocated = int(entry[2].args.split(",")[0][1:], 0)
    need(allocated > 0 and allocated % 16 == 0, "Unaligned paired frame allocation")
    # The retained compiler output touches the allocated stack before saving
    # R11. Require its exact qword, zero-immediate, top-of-frame form; do not
    # skip arbitrary instructions or make the touch optional.
    need((entry[3].op, entry[3].args) == ("orq", "$0x0,(%rsp)"), "Missing or changed paired entry stack touch")
    saved = re.fullmatch(r"%r11,(-0x[0-9a-f]+\(%rbp\))", entry[4].args)
    need(entry[4].op == "mov" and saved, "Missing private record save")
    # BindServiceParameter emits one reload then two qword copy pairs. The
    # trailing width/height scalars each reload the same private record.
    cursor, slots, copies = 5, [], []
    for group in ((0, 8), (16, 24), (32,), (40,)):
        row = entry[cursor]
        need((row.op, row.args) == ("mov", saved[1] + ",%r11"), "Changed record reload")
        cursor += 1
        for offset in group:
            read, write = entry[cursor : cursor + 2]
            address = ("" if offset == 0 else hex(offset)) + "(%r11),%rax"
            need((read.op, read.args) == ("mov", address), "Wrong paired record qword/width/order")
            slot = re.fullmatch(r"%rax,(-0x[0-9a-f]+\(%rbp\))", write.args)
            need(
                write.op == "mov" and slot and slot[1] != saved[1] and slot[1] not in slots,
                "Aliased or missing paired parameter slot",
            )
            slots.append(slot[1])
            copies.append(dict(offset=offset, destination=slot[1], address=read.address))
            cursor += 2
    offsets = [int(slot.split("(")[0], 16) for slot in [saved[1]] + slots]
    need(
        all(-allocated <= offset <= -8 and offset % 8 == 0 for offset in offsets) and len(set(offsets)) == 7,
        "Overlapping, unaligned or unallocated paired record slots",
    )
    need(
        offsets[2] == offsets[1] + 8 and offsets[4] == offsets[3] + 8,
        "Service grant/generation field adjacency changed",
    )
    pixel_sites = []
    for name in language_names:
        rows = body(name)
        for index, call in enumerate(rows):
            if call.op != "call" or starts.get(decoder.target_of(call)) != "__au_runtime_display_pixel":
                continue
            need(index >= 9 and index + 1 < len(rows), "Truncated pixel host ABI")
            before = rows[index - 9 : index]
            grant = re.fullmatch(r"(-0x[0-9a-f]+)\(%rbp\),%rdi", before[0].args)
            generation = re.fullmatch(r"(-0x[0-9a-f]+)\(%rbp\),%rsi", before[1].args)
            need(
                before[0].op == before[1].op == "mov"
                and grant
                and generation
                and int(generation[1], 16) == int(grant[1], 16) + 8,
                "Pixel grant/generation not distinct adjacent qwords",
            )
            need(
                len(rows) >= 3
                and [(r.op, r.args) for r in rows[:2]] == [("push", "%rbp"), ("mov", "%rsp,%rbp")]
                and rows[2].op == "sub"
                and re.fullmatch(r"\$(?:0x[0-9a-f]+|[0-9]+),%rsp", rows[2].args),
                "Pixel helper frame has unknown allocation",
            )
            pixel_frame = int(rows[2].args.split(",")[0][1:], 0)
            pixel_offsets = [int(grant[1], 16), int(generation[1], 16)]
            need(
                pixel_frame > 0
                and pixel_frame % 16 == 0
                and all(-pixel_frame <= offset <= -8 and offset % 8 == 0 for offset in pixel_offsets),
                "Pixel grant/generation slots are unaligned or outside helper frame",
            )
            need(
                [(r.op, r.args) for r in before[2:7]] == [("pop", r) for r in ("%r10", "%r9", "%r8", "%rcx", "%rdx")],
                "Pixel scalar ABI changed",
            )
            need(
                before[7].op == "sub"
                and before[7].args in ("$0x8,%rsp", "$0x10,%rsp")
                and (before[8].op, before[8].args) == ("mov", "%r10,(%rsp)")
                and (rows[index + 1].op, rows[index + 1].args) == ("add", before[7].args),
                "Pixel seventh argument or balanced outgoing stack changed",
            )
            sites = [row for row in functions[name]["calls"] if row["address"] == call.address]
            need(len(sites) == 1 and sites[0]["live_bytes"] % 16 == 0, "Misaligned pixel SysV host call")
            need(
                index + 3 < len(rows)
                and (rows[index + 2].op, rows[index + 2].args) == ("cmp", "$0x1,%rax")
                and rows[index + 3].op == "ja"
                and code[decoder.target_of(rows[index + 3])].op == "ud2",
                "Pixel completion validation changed",
            )
            pixel_sites.append(dict(function=name, address=call.address, outgoing=before[7].args))
    need(pixel_sites, "No concrete Display pixel host call")
    return dict(
        entry_qword_copies=copies, pixel_sites=pixel_sites, value_bridge=dict(symbol=VALUE_BRIDGE, entry=VALUE_ENTRY)
    )


def verify_retained_wait_paths(functions, owner, recursive):
    required = (BRIDGE, ENTRY, "__au_runtime_console_next")
    paths = []

    def visit(name, path, counts):
        if name in recursive:
            if counts.get(name, 0) == 4:
                return
            counts = dict(counts, **{name: counts.get(name, 0) + 1})
        else:
            need(name not in path, "Unknown wait graph cycle")
        path = path + [name]
        if name == owner:
            need(
                all(item in path for item in required)
                and [path.index(item) for item in required] == sorted(path.index(item) for item in required),
                "Wait bypasses retained paired service or Console host call",
            )
            paths.append(path)
            return
        for call in functions[name]["calls"]:
            if call["target"] is not None:
                visit(call["target"], path, counts)

    # Only traverse nodes that can reach the wait, avoiding unrelated scalar
    # call-chain multiplicity; every retained path remains covered.
    reaches = {owner}
    while True:
        larger = reaches | {
            name for name, body in functions.items() if any(row["target"] in reaches for row in body["calls"])
        }
        if larger == reaches:
            break
        reaches = larger
    narrowed = {
        name: dict(body, calls=[row for row in body["calls"] if row["target"] in reaches])
        for name, body in functions.items()
    }
    functions = narrowed
    visit("uefi_payload_entry", [], {})
    need(paths, "No retained wait path")
    return paths


# The compiler's .ci assembler symbol joins its complete .su source record.
# These exact authority symbols are inventory requirements, never name guesses.
SESSION_VALIDATORS = {
    "_ZN6aurora7" + space + "7SessionINS_4uefi12_GLOBAL__N_116" + transport
    + "ENS3_15ServicePlatformEE8validateEPKvmb": "kernel/" + space + "-session.hpp"
    for space, transport in (("console", "ServiceTransport"), ("display", "DisplayTransport"))
}


def verify_session_frames(frames, associations):
    for symbol, source in SESSION_VALIDATORS.items():
        need(symbol in frames and symbol in associations, "Missing distinct Session validator frame")
        need(
            len(associations[symbol]) == 1
            and associations[symbol][0]["object"] == "graphical-console.o"
            and (ROOT / associations[symbol][0]["source"]).resolve() == (ROOT / source).resolve(),
            "Session validator frame has foreign or duplicated ownership/source",
        )


def paired_alias_evidence(obj):
    """Read both raw ELF entries before collapsing one proven code body."""
    pair = {PAIRED_WALK, PAIRED_ALIAS}
    need(pair <= set(obj.functions), "Missing exact paired walker alias pair")
    symbols = [obj.functions[name] for name in (PAIRED_WALK, PAIRED_ALIAS)]
    first = symbols[0]
    need(
        first.size == 866
        and first.kind == 2
        and first.section > 0
        and all(
            (row.address, row.size, row.section, row.kind) == (first.address, first.size, first.section, first.kind)
            for row in symbols
        ),
        "Diverged paired walker alias address/section/size/type",
    )
    need(
        {
            row.name
            for row in obj.symbols
            if row.section == first.section and row.address == first.address and row.kind == 2
        }
        == pair,
        "Unexpected paired walker alias inventory",
    )
    entries = []
    for section in obj.sections:
        if section[1] != 2:
            continue
        need(section[9] == 24, "Unsupported paired symbol table")
        strings = obj.section_data(section[6])
        for position in range(section[4], section[4] + section[5], 24):
            offset, info, other, index, address, size = struct.unpack_from("<IBBHQQ", obj.data, position)
            end = strings.find(b"\0", offset)
            need(end >= offset, "Invalid paired symbol string")
            name = strings[offset:end].decode()
            if name not in pair:
                continue
            need(
                info == 0x22 and other == 2 and (index, address, size) == (first.section, first.address, first.size),
                "Changed paired walker WEAK/HIDDEN FUNC binding or raw identity",
            )
            entries.append(
                dict(
                    name=name,
                    address=address,
                    size=size,
                    section=index,
                    binding="WEAK",
                    visibility="HIDDEN",
                    type="FUNC",
                )
            )
    need(len(entries) == 2 and {row["name"] for row in entries} == pair, "Duplicate or missing raw paired alias entry")
    return dict(
        canonical=PAIRED_WALK,
        aliases=sorted(entries, key=lambda row: row["name"]),
        body_sha256=hashlib.sha256(obj.function_bytes(first)).hexdigest(),
    )


def paired_walker_evidence(obj):
    """Keep GCC14 equal aliases distinct from GCC16's single raw definition."""
    present = {PAIRED_WALK, PAIRED_ALIAS} & set(obj.functions)
    if present == {PAIRED_WALK, PAIRED_ALIAS}:
        return dict(paired_alias_evidence(obj), emission="gcc14-equal-aliases")
    need(present == {PAIRED_ALIAS}, "Missing exact or unknown paired walker definition inventory")
    first = obj.functions[PAIRED_ALIAS]
    need(first.size == 932 and first.kind == 2 and first.section > 0,
         "Changed GCC16 single walker extent/type")
    need({row.name for row in obj.symbols
          if row.section == first.section and row.address == first.address and row.kind == 2} == present,
         "Unexpected GCC16 same-address function definition")
    definitions = []
    for section in obj.sections:
        if section[1] != 2:
            continue
        need(section[9] == 24, "Unsupported GCC16 symbol table")
        strings = obj.section_data(section[6])
        for position in range(section[4], section[4] + section[5], 24):
            offset, info, other, index, address, size = struct.unpack_from("<IBBHQQ", obj.data, position)
            end = strings.find(b"\0", offset)
            need(end >= offset, "Invalid GCC16 walker symbol string")
            name = strings[offset:end].decode()
            if name not in {PAIRED_WALK, PAIRED_ALIAS}:
                continue
            need(name == PAIRED_ALIAS and info == 0x22 and other == 2
                 and (index, address, size) == (first.section, first.address, first.size),
                 "Changed GCC16 raw WEAK/HIDDEN walker definition")
            definitions.append(dict(name=name, address=address, size=size, section=index,
                                    binding="WEAK", visibility="HIDDEN", type="FUNC"))
    need(len(definitions) == 1, "Duplicate or missing GCC16 raw walker definition")
    return dict(canonical=PAIRED_ALIAS, emission="gcc16-single-definition", definitions=definitions,
                body_sha256=hashlib.sha256(obj.function_bytes(first)).hexdigest())


def paired_metadata_symbol(text):
    """Select one raw compiler name from the separately proved exact alias pair.

    This is only inventory selection. The shared .ci parser subsequently checks
    every complete node, source record and exact object-symbol association.
    No display signature or other assembler spelling participates in selection.
    """
    quoted = r'"(?:[^"\\]|\\["\\n])*"'
    names = []
    for line in text.splitlines():
        node = re.fullmatch(r"node: \{ title: (" + quoted + r") label: (" + quoted + r")( shape : ellipse)? \}", line)
        if node and not node[3]:
            name = json.loads(node[1]).removeprefix("kernel/uefi/graphical-console.cpp:").removeprefix("*")
            if name in (PAIRED_WALK, PAIRED_ALIAS):
                names.append(name)
    need(len(names) == 1, "Paired alias requires exactly one raw compiler frame definition")
    return names[0]


def graphical_cpp_frames(decoder, directory, linked, paired_walk=PAIRED_WALK):
    # Keep the shared decoder untouched. Both alias names cross its exact
    # object/link byte-and-relocation association before one frame is counted.
    associated, receipts, alias_objects = {}, {}, []
    for name in CPP_OBJECTS:
        obj = decoder.Elf(directory / (name + ".o"))
        need(obj.type == 1, "Expected relocatable C++ object")
        if name == "graphical-console":
            evidence = paired_walker_evidence(obj)
            need(evidence["canonical"] == paired_walk, "Object/linked paired definition forms disagree")
            definitions = [row["name"] for row in evidence.get("aliases", evidence.get("definitions", []))]
            for symbol in definitions:
                decoder.associate_object(linked, obj, obj.functions[symbol])
            alias_objects.append(
                dict(object=name + ".o", **evidence, associated_linked_symbols=definitions)
            )
        else:
            need(not {PAIRED_WALK, PAIRED_ALIAS} & set(obj.functions), "Paired walker outside exact graphical object")
        # Select the actual raw compiler definition only after proving both
        # ELF aliases and their linked bytes. Join that name without rewriting
        # metadata; canonicalize the one already-proved pair after the join.
        omitted = None
        if name == "graphical-console":
            raw_alias = paired_metadata_symbol((directory / (name + ".ci")).read_text())
            need(raw_alias in definitions, "Compiler walker definition is absent from exact object")
            if paired_walk == PAIRED_WALK:
                omitted = PAIRED_ALIAS if raw_alias == PAIRED_WALK else PAIRED_WALK
        symbols = {key: value for key, value in obj.functions.items() if key != omitted}
        rows = decoder.object_stack_rows(directory, name, symbols)
        for raw_symbol, row in rows.items():
            symbol = PAIRED_WALK if raw_symbol == PAIRED_ALIAS and paired_walk == PAIRED_WALK else raw_symbol
            need(symbol in linked.functions, "Object function omitted from linked profile")
            decoder.associate_object(linked, obj, obj.functions[raw_symbol])
            if symbol in associated:
                need(associated[symbol] == row.size, "Conflicting COMDAT compiler frames")
            associated[symbol] = row.size
            source = (ROOT / row.source).resolve()
            need(source.is_relative_to(ROOT / "kernel"), "Compiler frame outside kernel source inventory")
            contents = source.read_bytes()
            lines = contents.decode().splitlines()
            need(row.line <= len(lines) and row.column <= len(lines[row.line - 1]) + 1, "Invalid frame location")
            receipts.setdefault(symbol, []).append(dict(
                object=name + ".o", callgraph=name + ".ci", compiler_symbol=raw_symbol, source=row.source,
                source_sha256=hashlib.sha256(contents).hexdigest(), line=row.line,
                column=row.column, record=row.signature, bytes=row.size, kind=row.kind,
            ))
    need(len(alias_objects) == 1, "Missing exact graphical alias association")
    return associated, receipts, alias_objects


def stack_evidence(directory):
    decoder = load("graphical_stack_decoder", ROOT / "tests/kernel-uefi-owned-bytes-stack.py")
    decoder.CPP_OBJECTS = CPP_OBJECTS
    # Scalar additions are the reviewed operand-decoded console forms, not
    # arbitrary opcode rewriting: RSP/RBP writes still cross the core stack
    # checks first; unknown writes kill ECX/R14 level facts. test widths are
    # read-only. MFENCE/PAUSE/STI/WRMSR require no operands below; STI is further
    # restricted to the exact wait. SIDT is an explicit memory write, never an
    # implicit stack adjustment. No form here authorizes indirect control flow.
    decoder.NEUTRAL |= frozenset(
        (
            "sti wrmsr sar movswl movzwl movw sal sidt setg setge cmovb cmovg cmovge "
            "testb testl testw cmovs bswap mfence pause"
        ).split()
    )
    decoder.READ_ONLY |= frozenset(("testb", "testl", "testw"))
    decoder.PRESERVE_FLAGS |= frozenset(("sti", "wrmsr", "mfence", "pause", "cqto"))
    decoder.NEUTRAL |= frozenset(("cqto", "idiv"))
    linked = decoder.Elf(directory / "payload.elf")
    need(linked.type == 2, "Expected linked executable payload")
    need(not subprocess.check_output(["nm", "-u", directory / "payload.elf"], text=True).strip(), "Unresolved payload")
    paired_linked = paired_walker_evidence(linked)
    paired_walk = paired_linked["canonical"]
    old_rows = decoder.stack_rows
    bounded = []

    def stack_rows(text):
        bounded.extend(line for line in text.splitlines() if line.endswith("\tdynamic,bounded"))
        return old_rows(text, allow_bounded=lambda signature: any(
            name in signature for name in (
                "aurora::uefi::run_graphical_console(",
                "FramebufferPayload::restore_graphical_fixture(",
            )
        ))

    decoder.stack_rows = stack_rows
    frames, associations, alias_objects = graphical_cpp_frames(decoder, directory, linked, paired_walk)
    verify_session_frames(frames, associations)
    # Raw symbols and evidence remain intact; only the analyzed function graph
    # loses the compatibility spelling after both associations have succeeded.
    if paired_walk == PAIRED_WALK:
        del linked.functions[PAIRED_ALIAS]
    named = {row.name: row for row in linked.symbols if row.section}
    irq = named["uefi_console_interrupt"]
    irq_object = decoder.Elf(directory / "console-entry.o")
    irq_symbols = [row for row in irq_object.symbols if row.name == irq.name]
    need(len(irq_symbols) == 1, "Ambiguous IRQ object symbol")
    original = irq_symbols[0]
    extent = irq_object.sections[original.section][5] - original.address
    linked.functions[irq.name] = decoder.Symbol(irq.name, irq.address, extent, irq.section, 2)
    starts = {symbol.address: name for name, symbol in linked.functions.items()}
    need(len(starts) == len(linked.functions), "Ambiguous linked function starts")
    code, disassembly = decoder.disassemble(directory / "payload.elf")
    original_code = dict(code)
    payload = (directory / "payload.bin").read_bytes()
    divisions = verify_generated_divisions(linked.functions, code, payload)
    body = lambda symbol: [r for a, r in sorted(code.items()) if symbol.address <= a < symbol.address + symbol.size]
    verify_irq_body(decoder, body(linked.functions[irq.name]), starts)
    normalized = []
    for address, row in list(code.items()):
        if irq.address <= address < irq.address + extent:
            continue  # Entire exact IRQ has its separate save/restore proof above.
        code[address], receipt = normalize_instruction(decoder, row, payload)
        if receipt:
            normalized.append(receipt)
    language, memory = (decoder.Elf(directory / (name + ".o")) for name in ("language", "memory"))
    for obj in (language, memory):
        for symbol in obj.functions.values():
            decoder.associate_object(linked, obj, symbol)
    assembly = [item for name in ASSEMBLY_OBJECTS for item in common.linked_assembly(decoder, linked, directory, name)]
    verify_inventory(linked.functions, frames, language.functions, memory.functions)
    language_imports = verify_language_object(language)
    reflection = []
    for name in sorted(REFLECTION_HELPERS):
        original = language.functions[name]
        need(
            not any(
                section == original.section
                and address < original.address + original.size
                and address + 4 > original.address
                for section, address, *_ in language.relocations
            ),
            "Reflection helper acquired a relocation",
        )
        reflection.append(
            verify_reflection_body(decoder, linked.functions[name], body(linked.functions[name]), payload)
        )
    decoder.NORETURN = frozenset(
        name
        for name in linked.functions
        if name == "uefi_payload_fail"
        or "4failE" in name
        or "21run_graphical_consoleE" in name
        or "23graphical_console_faultE" in name
    )
    functions = {}
    for name, symbol in linked.functions.items():
        if name == irq.name:
            continue
        try:
            functions[name] = decoder.analyze_function(symbol, code, starts, fault=name == "fault_common")
        except ValueError as error:
            raise ValueError(unreviewed_linked_function(symbol, original_code, payload, error)) from error
    console.verify_noreturn(functions, decoder.NORETURN)
    verify_bridge_body(decoder, body(linked.functions[BRIDGE]), starts)
    private_abi = verify_private_abi(decoder, linked, code, starts, language.functions, functions)
    proofs = paired_recursion_proofs(decoder, functions, linked.functions, code, starts, paired_walk, payload, associations)
    recursive = {proof["symbol"] for proof in proofs.values()}
    for name in functions:
        common.graph_peak(functions, frames, name, recursive)
    normal = common.graph_peak(functions, frames, "uefi_payload_entry", recursive)
    session = common.graph_peak(functions, frames, ENTRY, recursive)
    fault = 48 + max(
        common.graph_peak(functions, frames, name, recursive)["peak"]
        for name in ("uefi_payload_fault", "uefi_payload_page_fault")
    )
    dispatch = common.graph_peak(functions, frames, "uefi_console_interrupt_dispatch", recursive)
    irq_peak = 176 + 15 + dispatch["peak"]
    owner, irq_reachable = verify_wait_closure(code, named, functions, language.functions, payload, linked.functions)
    need(owner not in irq_reachable, "IRQ reaches interruptible wait")
    retained_paths = verify_retained_wait_paths(functions, owner, recursive)
    waiting = common.graph_peak(functions, frames, "uefi_payload_entry", recursive, target=owner)
    need(
        {ENTRY, BRIDGE, "__au_runtime_console_next"} <= set(waiting["path"]),
        "Wait does not retain paired Aurora service and Console host call",
    )
    verify_stack_budgets(normal["peak"], waiting["peak"], irq_peak, fault)
    waiting["peak_with_interrupt"] = waiting["peak"] + irq_peak
    waiting["peak_with_interrupt_and_fault"] = waiting["peak"] + irq_peak + fault
    capture_fixture = None
    if "_ZN6aurora4uefi12_GLOBAL__N_116capture_scenarioE" in named:
        capture_fixture = capture_linked_evidence(
            decoder,
            linked,
            original_code,
            payload,
            {name: digest(directory / name) for name in CAPTURE_FILE_CONTRACTS},
        )
    return dict(
        stack_bytes=16384,
        cap_bytes=15360,
        normal=normal,
        session=session,
        boot_fault=fault,
        irq_frame_bytes=176,
        irq_alignment_bytes=15,
        irq_fault_reserve_bytes=4096,
        irq_dispatch=dispatch,
        irq_peak=irq_peak,
        irq_reachable=irq_reachable,
        wait=waiting,
        bridge=dict(symbol=BRIDGE, entry=ENTRY, record_qwords=6),
        host_imports=sorted(HOST_IMPORTS),
        language_imports=language_imports,
        private_abi=private_abi,
        retained_wait_paths=retained_paths,
        reflection_helpers=reflection,
        generated_divisions=divisions,
        compiler_frames=associations,
        linked_functions=functions,
        assembly_objects=assembly,
        original_dynamic_bounded_rows=bounded,
        normalized_stack_immediates=normalized,
        paired_walker_identity=dict(linked=paired_linked, objects=alias_objects),
        page_verifiers=proofs,
        disassembly_sha256=hashlib.sha256(disassembly.encode()).hexdigest(),
        capture_fixture=capture_fixture,
    )


def build_files():
    names = [
        "payload.elf",
        "payload.bin",
        "esp/EFI/BOOT/BOOTX64.EFI",
        "uefi-payload.hpp",
        "language.s",
        "embed.S",
        "console-poll-metadata.json",
        "image-metadata.json",
    ]
    names += [name + ".o" for name in CPP_OBJECTS + ASSEMBLY_OBJECTS + ("loader", "embed", "transition")]
    names += [name + suffix for name in CPP_OBJECTS + ("loader",) for suffix in (".su", ".ci")]
    names += [name + "-pe.o" for name in ("loader", "memory", "embed", "transition")]
    return [BUILD / name for name in names]


def expected_flags(mode):
    need(mode in MODES, "Unknown graphical profile")
    return list(BASE_FLAGS + PROFILE_FLAGS + (("-DAURORA_UEFI_GRAPHICAL_CAPTURE",) if mode == MODES[1] else ()))


def verify_inputs(record, mode):
    need(type(record) is dict, "Build record must be an object")
    need(set(record) in (BUILD_KEYS, BUILD_KEYS | {"output_sha256"}), "Unexpected build manifest keys")
    need(
        record["schema"] == "aurora-graphical-console-build-v1" and record["mode"] == mode,
        "Graphical build profile mismatch",
    )
    need(record["flags"] == expected_flags(mode), "Exact graphical compiler flags/order mismatch")
    need(
        record["translation_unit_flags"] == TU_FLAGS
        and record["objects"] == [str(path.relative_to(BUILD)) for path in build_files()],
        "Changed graphical translation/object inventory",
    )
    need(record["source_sha256"] == common.hashes(source_files()), "Graphical source changed since begin")
    need(type(record["tools"]) is dict and set(record["tools"]) == set(TOOLS), "Build tool inventory mismatch")
    for name, item in list(record["tools"].items()) + [
        (name, record[name]) for name in ("compiler", "cxx", "pe_linker")
    ]:
        need(
            type(item) is dict
            and set(item) == {"path", "sha256"}
            and type(item["path"]) is str
            and Path(item["path"]).is_absolute()
            and re.fullmatch(r"[0-9a-f]{64}", item["sha256"]),
            "Malformed executable identity",
        )
        need(digest(Path(item["path"])) == item["sha256"], "Build executable changed: " + name)
        if name in TOOLS:
            need(item == common.executable(name), "Tool resolution changed: " + name)


def begin(mode, compiler, cxx, flags, linker=None):
    # Invalidate before any fallible argument, source or executable validation.
    RECEIPT.unlink(missing_ok=True)
    (BUILD / "graphical-console-build.json").unlink(missing_ok=True)
    (BUILD / "graphical-console-build-start.json").unlink(missing_ok=True)
    need(compiler and cxx and flags == expected_flags(mode), "Missing exact graphical build controls")
    record = dict(
        schema="aurora-graphical-console-build-v1",
        mode=mode,
        flags=flags,
        source_sha256=common.hashes(source_files()),
        compiler=common.executable(compiler),
        cxx=common.executable(cxx),
        tools={name: common.executable(name) for name in TOOLS},
        pe_linker=common.executable(linker or "ld"),
        translation_unit_flags=TU_FLAGS,
        objects=[str(path.relative_to(BUILD)) for path in build_files()],
    )
    verify_inputs(record, mode)
    (BUILD / "graphical-console-build-start.json").write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")


def end(mode):
    record = read_json(BUILD / "graphical-console-build-start.json")
    verify_inputs(record, mode)
    record["output_sha256"] = common.hashes(build_files())
    (BUILD / "graphical-console-build.json").write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")


def provenance(mode):
    record = read_json(BUILD / "graphical-console-build.json")
    verify_inputs(record, mode)
    need(set(record) == BUILD_KEYS | {"output_sha256"}, "Incomplete build manifest")
    need(record["output_sha256"] == common.hashes(build_files()), "Combined build output changed")
    return record


def image_evidence(directory, mode):
    fixture_source = capture_source_evidence(mode)
    image = load("graphical_image_decoder", ROOT / "tests/kernel-uefi-image.py")
    binary = (directory / "payload.bin").read_bytes()
    elf = (directory / "payload.elf").read_bytes()
    pe = (directory / "esp/EFI/BOOT/BOOTX64.EFI").read_bytes()
    image.elf_validate(elf, binary)
    image.pe_validate(pe, binary)
    graphical_policy = image.graphical_image_policy(directory)
    objects = {}
    for name in CPP_OBJECTS + ASSEMBLY_OBJECTS:
        relocations = subprocess.check_output(["readelf", "-rW", directory / (name + ".o")], text=True)
        kinds = set(re.findall(r"R_X86_64_\w+", relocations))
        need(kinds <= {"R_X86_64_PC32", "R_X86_64_PLT32"}, "Non-PIC combined object: " + name)
        need(name != "memory" or not kinds, "Memory primitive has helpers")
        objects[name] = sorted(kinds)
    names = common.symbols(directory / "payload.elf")
    poll = dict(
        wait_begin=names["uefi_console_poll_begin"],
        wait_end=names["uefi_console_poll_end"],
        text_end=names["__payload_text_end"],
        frame_bytes=176,
        interrupt=names["uefi_console_interrupt"],
        dispatch=names["uefi_console_interrupt_dispatch"],
        polling_count=1250000,
        uart_irq=0,
    )
    need(canonical(read_json(directory / "console-poll-metadata.json")) == canonical(poll), "Poll metadata drift")
    metadata = dict(
        pe_sha256=hashlib.sha256(pe).hexdigest(),
        payload_sha256=hashlib.sha256(binary).hexdigest(),
        payload_bytes=len(binary),
    )
    need(canonical(read_json(directory / "image-metadata.json")) == canonical(metadata), "Image metadata drift")
    fixture_artifacts = {}
    for name in CAPTURE_ARTIFACTS:
        path = directory / name
        symbolic = name.endswith((".o", ".elf"))
        fixture_artifacts[name] = dict(
            contents=path.read_bytes(),
            symbols=subprocess.check_output(["nm", "-a", path]) if symbolic else b"",
            relocations=subprocess.check_output(["objdump", "-r", path]) if symbolic else b"",
        )
    return dict(
        **metadata,
        elf_sha256=hashlib.sha256(elf).hexdigest(),
        object_relocations=objects,
        poll=poll,
        graphical_policy=graphical_policy,
        capture_fixture=dict(source=fixture_source, artifacts=capture_artifact_evidence(mode, fixture_artifacts)),
    )


def emit(mode):
    RECEIPT.unlink(missing_ok=True)
    record = provenance(mode)
    result = dict(
        schema="aurora-graphical-console-admission-v2",
        status="requires-independent-review",
        mode=mode,
        clock="tcg-original-clock",
        build=record,
        image=image_evidence(BUILD, mode),
        stack=stack_evidence(BUILD),
    )
    require_capture_linked_proof(mode, result["stack"].get("capture_fixture"), record)
    need(record == provenance(mode), "Build changed during admission")
    result["sha256"] = common.hashes(source_files() + build_files() + [BUILD / "graphical-console-build.json"])
    RECEIPT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print("PASS: automatic combined image/stack evidence; independent first-image acceptance still required")
    return result


def checked(mode):
    receipt = read_json(RECEIPT)
    need(type(receipt) is dict, "Receipt must be an object")
    need(
        set(receipt) == {"schema", "status", "mode", "clock", "build", "image", "stack", "sha256"},
        "Unexpected receipt keys",
    )
    need(
        receipt["schema"] == "aurora-graphical-console-admission-v2"
        and receipt["mode"] == mode
        and receipt["status"] == "requires-independent-review"
        and receipt["clock"] == "tcg-original-clock",
        "Unexpected graphical receipt/profile/status",
    )
    need(receipt["build"] == provenance(mode), "Admitted graphical build changed")
    need(
        receipt["sha256"] == common.hashes(source_files() + build_files() + [BUILD / "graphical-console-build.json"]),
        "Admission source/output inventory or bytes changed",
    )
    current_image, current_stack = image_evidence(BUILD, mode), stack_evidence(BUILD)
    need(
        canonical(receipt["image"]) == canonical(current_image)
        and canonical(receipt["stack"]) == canonical(current_stack),
        "Receipt image/stack evidence differs from fresh combined proof",
    )
    require_capture_linked_proof(mode, current_stack.get("capture_fixture"), receipt["build"])
    return receipt


def reviewed(mode):
    pin = os.environ.get("GRAPHICAL_CONSOLE_REVIEW_SHA256", "")
    need(
        re.fullmatch(r"[0-9a-f]{64}", pin) and RECEIPT.is_file() and digest(RECEIPT) == pin,
        "Independent GRAPHICAL_CONSOLE_REVIEW_SHA256 receipt pin required",
    )
    return checked(mode)


begin_build, end_build, verify = begin, end, checked


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "action",
        choices=(
            "begin",
            "end",
            "begin-build",
            "end-build",
            "emit",
            "verify",
            "checked",
            "reviewed",
            "diagnose",
            "source",
        ),
    )
    parser.add_argument("--mode", required=True, choices=MODES)
    parser.add_argument("--compiler")
    parser.add_argument("--cxx")
    parser.add_argument("--linker")
    parser.add_argument("--flag", action="append", default=[])
    args = parser.parse_args()
    if args.action in ("begin", "begin-build"):
        begin(args.mode, args.compiler, args.cxx, args.flag, args.linker)
    elif args.action in ("end", "end-build"):
        end(args.mode)
    elif args.action == "emit":
        emit(args.mode)
    elif args.action == "reviewed":
        reviewed(args.mode)
        print("Verified externally pinned exact combined evidence.")
    elif args.action == "diagnose":
        print(json.dumps(stack_evidence(BUILD), indent=2, sort_keys=True))
    elif args.action == "source":
        print(json.dumps(capture_source_evidence(args.mode), indent=2, sort_keys=True))
    else:
        checked(args.mode)
        print("Verified current combined receipt identity; independent qualification not claimed.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, TypeError, subprocess.CalledProcessError) as error:
        raise SystemExit("FAIL: graphical Console admission: " + str(error)) from error
