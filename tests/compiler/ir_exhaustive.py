#!/usr/bin/env python3
"""Check canonical IR mapping and fail-closed source verification/emission.

Temporary copies inject unknown variants/forms into the instruction codec,
then exercise the actual Aurora verifier and emitter with hostile observations
and removed handlers. Source dispatch has runtime rejection, not C++ compile-time
exhaustiveness.
The textual IR cases also supply separate native ABI and exact-trap checks.
"""

from pathlib import Path
import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
from unittest import mock

from integer_oracle import command

ROOT = Path(__file__).resolve().parents[2]
COMPILER = shlex.split(os.environ.get("CXX", "g++"))
HEADERS = (
    "diagnostics.hpp",
    "types.hpp",
    "services.hpp",
    "ir.hpp",
    "ir_layout.hpp",
    "ir_verify.hpp",
    "hosted_graph.hpp",
    "hosted_ir_metadata.hpp",
    "hosted_ir_metadata_writer.hpp",
    "hosted_ir_instructions.hpp",
    "ir_instruction_codec.hpp",
    "x86.hpp",
    "byte_literal.hpp",
)
GENERATED_HEADERS = ("hosted_frontend_abi.hpp",)
# Verified textual IR cases; the aurora-ir-check driver prints their assembly.
AIR = ROOT / "tests/compiler/ir/ir-tests/abi.air"


def compile_codec_probe(directory):
    # Both inventories are authoritative: generated source forms and the one
    # parameterized operation variant. No independently maintained opcode list.
    generated = (directory / GENERATED_HEADERS[0]).read_text()
    declaration = re.search(r"enum class InstructionForm\s*:\s*std::int64_t\s*\{(.*?)\};", generated, re.DOTALL)
    if declaration is None:
        raise AssertionError("could not locate generated instruction forms")
    forms = re.findall(r"([A-Za-z_][A-Za-z0-9_]*)\s*=", declaration[1])
    probe = directory / "probe.cpp"
    probe.write_text(
        '#include "ir_instruction_codec.hpp"\n#include <array>\n#include <utility>\n'
        "using namespace aurora::ir;\n"
        "template<std::size_t... I> consteval bool covered(std::index_sequence<I...>) {\n"
        "  constexpr std::array mapped{detail::InstructionCodec<"
        "std::variant_alternative_t<I, InstructionObservation>>::form...};\n"
        "  constexpr std::array expected{" + ",".join("detail::InstructionForm::" + name for name in forms) + "};\n"
        "  if (mapped.size() != expected.size()) return false;\n"
        "  for (auto form : expected) { unsigned count = 0; "
        "for (auto value : mapped) count += value == form; if (count != 1) return false; }\n"
        "  return true;\n}\n"
        "static_assert(covered(std::make_index_sequence<std::variant_size_v<InstructionObservation>>{}), "
        '"instruction variant/form mapping must be one-to-one");\nint main() {}\n'
    )
    return subprocess.run(
        COMPILER + ["-std=c++23", "-fsyntax-only", "-I", str(directory), str(probe)],
        capture_output=True,
        text=True,
        timeout=45,
    )


def source_verifier_probes(directory, args):
    # Intentional mutation-test interposition, as in the emitter probe below.
    # Only the verifier entry is wrapped. It borrows the production-admitted
    # metadata and structured instruction owners, never a copied stream.
    sys.path.insert(0, str(ROOT / "scripts"))
    import bootstrap_frontend as bootstrap

    directory.mkdir(parents=True)
    fixture = directory / "verification-probe.cpp"
    fixture.write_text(r"""
#include "hosted_frontend_abi.hpp"
#include <cstdlib>
using namespace aurora;
namespace {
unsigned entered = 0;
struct RequireEntry {
    ~RequireEntry() { if (entered == 0) std::abort(); }
} requireEntry;
}
extern "C" std::int64_t probe_verification_run(const void *, std::int64_t) noexcept;
extern "C" std::int64_t __wrap_aurora_hosted_verification_run(
    const void *input, std::int64_t callable) noexcept {
    const auto &roots = *static_cast<const hosted_abi::VerificationRunRoots *>(input);
    if (!roots.workspace || !roots.metadata || !roots.instructions ||
        roots.workspace == roots.metadata || roots.workspace == roots.instructions ||
        roots.metadata == roots.instructions || callable < 0)
        std::abort();
    auto *const workspace = roots.workspace;
    const auto *const metadata = roots.metadata;
    const auto *const instructions = roots.instructions;
    ++entered;
    const auto result = probe_verification_run(input, callable);
    if (roots.workspace != workspace || roots.metadata != metadata || roots.instructions != instructions)
        std::abort();
    hosted_abi::compiler_ir_verification::VerificationReport report{};
    aurora_hosted_verification_report(workspace, &report);
    if (result != static_cast<std::int64_t>(report.statusValue))
        std::abort();
    return result;
}
""")
    fixture_object = fixture.with_suffix(".o")
    command(
        COMPILER
        + ["-std=c++23", "-I", ROOT / "compiler", "-I", args.abi_header.parent, "-c", fixture, "-o", fixture_object],
        timeout=45,
    )
    source = directory / "verification-probe.au"
    source.write_text("""
export module aurora.compiler.frontend;
import aurora.compiler.ir_verification;
import aurora.compiler.ir_verification_errors;
import aurora.compiler.ir_verification_storage;
import aurora.compiler.ir_metadata_storage;
import aurora.compiler.ir_instruction_storage;
export namespace compiler_frontend {
    auto verification_run(compiler_ir_verification::VerificationWorkspace& workspace,
        const compiler_ir_metadata::MetadataStore& metadata,
        const compiler_ir_instructions::InstructionStore& instructions,
        i64 callable) -> compiler_ir_verification::VerificationStatus {
        return compiler_ir_verification::run(workspace, metadata, instructions, callable);
    }
}
""")
    modules = directory / "modules"
    bootstrap.stage_modules(
        modules, [*sorted((ROOT / "compiler").glob("*.au")), ROOT / "library/std/decimal_digits.au"]
    )
    transfer = modules / "aurora/compiler/ir_verification_transfer.au"
    original_transfer = transfer.read_text()
    original = json.loads(args.abi_facts.read_text())
    inputs = []
    for case, parameters, result, body in (
        ("constant", "", "i64", "return 42;"),
        ("branch", "bool b", "i64", "if (b) { return 42; } return 17;"),
    ):
        path = directory / (case + ".au")
        path.write_text(f"module verification_probe_fixture; auto test({parameters})->{result} {{ {body} }}\n")
        expected = directory / (case + "-expected.s")
        command([args.compiler, path, "-o", expected], timeout=30)
        inputs.append((case, path, expected.read_bytes()))
    for mutation in ("unchanged", "unknown-form", "missing-handler"):
        changed = original_transfer
        if mutation == "unknown-form":
            # Corrupt only the observation inside the real dynamic dispatcher,
            # after immutable instruction admission and CFG normalization.
            changed = replace_once(changed, "const i64 form = row.form();", "const i64 form = 999;")
        elif mutation == "missing-handler":
            # Remove the actual Constant route while preserving all other routes.
            changed = replace_once(changed, "(form >= 5 && form <= 19)", "(form >= 6 && form <= 19)")
        transfer.write_text(changed)
        assembly = directory / (mutation + ".s")
        facts_path = directory / (mutation + ".json")
        command(
            [
                args.compiler,
                "--local-symbols",
                "--module-root",
                modules,
                source,
                "--abi-facts",
                facts_path,
                "-o",
                assembly,
            ],
            timeout=90,
        )
        facts = json.loads(facts_path.read_text())
        # Compare the complete closed verification owner and every copied pool,
        # report and reason with the graph used by the production native capsule.
        for group in ("records", "enums"):
            for entry in original[group].values():
                name = entry["source_name"]
                if name.startswith("compiler_ir_verification::"):
                    if bootstrap.abi_declaration(facts, group, name) != bootstrap.abi_declaration(
                        original, group, name
                    ):
                        raise AssertionError(mutation + ": verification probe ABI differs: " + name)
        for group, name in (
            ("records", "compiler_ir_metadata::MetadataStore"),
            ("records", "compiler_ir_instructions::InstructionStore"),
            ("functions", "compiler_frontend::verification_run"),
        ):
            if bootstrap.abi_declaration(facts, group, name) != bootstrap.abi_declaration(original, group, name):
                raise AssertionError(mutation + ": verification paired-owner ABI differs: " + name)
        bootstrap.verification_abi(facts)
        with mock.patch.object(
            bootstrap, "PASS_ENTRIES", {"verification_run": bootstrap.PASS_ENTRIES["verification_run"]}
        ):
            bridge = "\n".join(bootstrap.pass_bridges(facts)[1]).replace(
                "aurora_hosted_verification_run", "probe_verification_run"
            )
        assembly.write_text(assembly.read_text() + "\n" + bridge + "\n")
        executable = directory / mutation
        command(
            COMPILER
            + [
                fixture_object,
                assembly,
                args.main_library,
                args.frontend_library,
                "-Wl,--wrap=aurora_hosted_verification_run",
                "-o",
                executable,
            ],
            timeout=45,
        )
        for case, path, expected in inputs:
            for existing in (False, True):
                output = directory / (mutation + "-" + case + "-" + str(existing) + ".s")
                if existing:
                    output.write_bytes(b"preserve this artifact\n")
                observed = subprocess.run([executable, path, "-o", output], capture_output=True, text=True, timeout=5)
                if mutation == "unchanged":
                    if (
                        observed.returncode != 0
                        or observed.stdout
                        or observed.stderr
                        or output.read_bytes() != expected
                    ):
                        raise AssertionError(
                            f"{mutation}/{case}: positive verification control failed: {observed.stderr}"
                        )
                elif (
                    observed.returncode != 1
                    or observed.stdout
                    or observed.stderr != "aurorac: error AU9001: invalid hosted IR verification workspace\n"
                    or (output.read_bytes() != b"preserve this artifact\n" if existing else output.exists())
                ):
                    raise AssertionError(f"{mutation}/{case}: wrong verification rejection: {observed.stderr}")
            print(f"PASS source verifier {mutation}: {case}")


def source_emitter_probes(directory, args):
    # Reuse the built CLI main and stock admission. Only emission is wrapped,
    # using a local-symbol source graph with the identical generated root ABI.
    sys.path.insert(0, str(ROOT / "scripts"))
    import bootstrap_frontend as bootstrap

    fixture = directory / "emitter-probe.cpp"
    fixture.write_text(r"""
#include "hosted_frontend_abi.hpp"
#include <cstdlib>
using namespace aurora;
extern "C" std::int64_t probe_emitter_run(const void *, std::int64_t, std::int64_t) noexcept;
extern "C" std::int64_t __wrap_aurora_hosted_emitter_run(
    const void *roots, std::int64_t binding, std::int64_t reflection) noexcept {
    const auto result = probe_emitter_run(roots, binding, reflection);
    const auto invalid = static_cast<std::int64_t>(hosted_abi::compiler_x86::EmitStatus::invalid);
    if (result == invalid) {
        auto *workspace = const_cast<void *>(static_cast<const void *const *>(roots)[0]);
        if (aurora_hosted_emitter_status(workspace) != invalid ||
            aurora_hosted_emitter_add_retained(workspace, 0) != 0 ||
            aurora_hosted_emitter_status(workspace) != invalid ||
            aurora_hosted_emitter_size(workspace,
                static_cast<std::int64_t>(hosted_abi::compiler_x86::Artifact::assembly)) != -1)
            std::abort();
    }
    return result;
}

""")
    fixture_object = fixture.with_suffix(".o")
    command(
        COMPILER
        + ["-std=c++23", "-I", ROOT / "compiler", "-I", args.abi_header.parent, "-c", fixture, "-o", fixture_object],
        timeout=45,
    )
    inputs = {}
    for case, parameters, result, expression, expected in (
        ("constant", "", "i64", "42", "movabsq $42, %rax"),
        ("unary", "i64 x", "i64", "-x", "negq %rax"),
        ("binary", "i64 x, i64 y", "i64", "x+y", "addq %rcx, %rax"),
        ("comparison", "i64 x, i64 y", "bool", "x==y", "sete %al"),
    ):
        path = directory / (case + ".au")
        path.write_text(f"module emitter_probe_fixture; auto test({parameters})->{result} {{ return {expression}; }}\n")
        inputs[case] = (path, expected)
    # Every operator of every scalar family must reach a handler; signed and
    # unsigned operands take different emitter paths. Behaviour is the oracles'.
    operators = [
        ("unary-negate", "i64 x", "i64", "-x"),
        ("unary-not", "bool b", "bool", "!b"),
        ("unary-bitnot", "u64 x", "u64", "~x"),
    ]
    for scalar in ("i64", "u64"):
        for name, symbol in (("add", "+"), ("subtract", "-"), ("multiply", "*"), ("divide", "/"), ("remainder", "%")):
            operators.append((f"binary-{name}-{scalar}", f"{scalar} x, {scalar} y", scalar, f"x{symbol}y"))
        for name, symbol in (("eq", "=="), ("ne", "!="), ("lt", "<"), ("gt", ">"), ("le", "<="), ("ge", ">=")):
            operators.append((f"comparison-{name}-{scalar}", f"{scalar} x, {scalar} y", "bool", f"x{symbol}y"))
    for name, symbol in (("and", "&"), ("or", "|"), ("xor", "^")):
        operators.append((f"binary-{name}-u64", "u64 x, u64 y", "u64", f"x{symbol}y"))
    for name, symbol in (("shl", "<<"), ("shr", ">>")):
        operators.append((f"binary-{name}-u64", "u64 x, i64 n", "u64", f"x{symbol}n"))
    for case, parameters, result, expression in operators:
        path = directory / (case + ".au")
        path.write_text(f"module emitter_probe_fixture; auto test({parameters})->{result} {{ return {expression}; }}\n")
        inputs[case] = (path, "")
    original = json.loads(args.abi_facts.read_text())
    source = directory / "emitter-probe.au"
    source.write_text("""
export module aurora.compiler.frontend;
import aurora.compiler.x86_module;
import aurora.compiler.x86_storage;
import aurora.compiler.ir_metadata_storage;
import aurora.compiler.ir_instruction_storage;
export namespace compiler_frontend {
    auto emitter_run(compiler_x86::EmitWorkspace& workspace,
        const compiler_ir_metadata::MetadataStore& metadata,
        const compiler_ir_instructions::InstructionStore& instructions,
        i64 binding, i64 reflection) -> compiler_x86::EmitStatus {
        return compiler_x86::run(workspace, metadata, instructions, binding, reflection);
    }
}
""")
    modules = directory / "modules"
    bootstrap.stage_modules(
        modules, [*sorted((ROOT / "compiler").glob("*.au")), ROOT / "library/std/decimal_digits.au"]
    )
    storage = modules / "aurora/compiler/ir_instruction_storage.au"
    scalar = modules / "aurora/compiler/x86_scalar.au"
    storage_original, scalar_original = storage.read_text(), scalar.read_text()
    for mutation, cases in (
        ("unchanged", tuple(inputs)),
        ("unknown-form", ("constant",)),
        ("unknown-operators", ("unary", "binary", "comparison")),
        ("missing-handler", ("constant",)),
    ):
        storage.write_text(storage_original)
        scalar.write_text(scalar_original)
        if mutation == "unknown-form":
            storage.write_text(replace_once(storage_original, "return instructionForm;", "return 999;"))
        elif mutation == "unknown-operators":
            changed = storage_original
            for field in ("unaryOperation", "binaryOperation", "comparisonOperation"):
                changed = replace_once(changed, "return " + field + ";", "return 999;")
            storage.write_text(changed)
        elif mutation == "missing-handler":
            # Remove one real family, not an independently enumerated form list.
            prefix, signature = scalar_original.split("    auto emit_scalar(", 1)
            scalar.write_text(prefix + "    auto emit_scalar(" + signature.split("{", 1)[0] + "{ return false; }\n}\n")
        assembly = directory / (mutation + ".s")
        facts_path = directory / (mutation + ".json")
        command(
            [
                args.compiler,
                "--local-symbols",
                "--module-root",
                modules,
                source,
                "--abi-facts",
                facts_path,
                "-o",
                assembly,
            ],
            timeout=90,
        )
        facts = json.loads(facts_path.read_text())
        for group, name in (
            ("records", "compiler_x86::EmitWorkspace"),
            ("records", "compiler_ir_metadata::MetadataStore"),
            ("records", "compiler_ir_instructions::InstructionStore"),
            ("functions", "compiler_frontend::emitter_run"),
        ):
            if bootstrap.abi_declaration(facts, group, name) != bootstrap.abi_declaration(original, group, name):
                raise AssertionError(mutation + ": emitter probe ABI differs: " + name)
        with mock.patch.object(bootstrap, "PASS_ENTRIES", {"emitter_run": bootstrap.PASS_ENTRIES["emitter_run"]}):
            bridge = "\n".join(bootstrap.pass_bridges(facts)[1]).replace(
                "aurora_hosted_emitter_run", "probe_emitter_run"
            )
        assembly.write_text(assembly.read_text() + "\n" + bridge + "\n")
        executable = directory / mutation
        command(
            COMPILER
            + [
                fixture_object,
                assembly,
                args.main_library,
                args.frontend_library,
                "-Wl,--wrap=aurora_hosted_emitter_run",
                "-o",
                executable,
            ],
            timeout=45,
        )
        for case in cases:
            path, expected = inputs[case]
            for existing in (True,) if mutation == "unchanged" else (False, True):
                output = directory / (mutation + "-" + case + "-" + str(existing) + ".s")
                if existing:
                    output.write_bytes(b"preserve this artifact\n")
                observed = subprocess.run([executable, path, "-o", output], capture_output=True, text=True, timeout=5)
                if mutation == "unchanged":
                    if observed.returncode != 0 or observed.stderr or expected not in output.read_text():
                        raise AssertionError(f"{mutation}/{case}: positive emitter control failed: {observed.stderr}")
                elif (
                    observed.returncode != 1
                    or observed.stdout
                    or observed.stderr != "aurorac: error AU9001: invalid hosted x86 emission transport\n"
                    or (output.read_bytes() != b"preserve this artifact\n" if existing else output.exists())
                ):
                    raise AssertionError(f"{mutation}/{case}: wrong emitter rejection: {observed.stderr}")
            print(f"PASS source emitter {mutation}: {case}")


def replace_once(source, old, new):
    if source.count(old) != 1:
        raise AssertionError("probe mutation anchor is not unique: " + old)
    return source.replace(old, new)


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("ir_tests", type=Path, nargs="?")
parser.add_argument("--abi-header", type=Path, required=True)
parser.add_argument("--abi-facts", type=Path, required=True)
parser.add_argument("--compiler", type=Path, required=True)
parser.add_argument("--frontend-library", type=Path, required=True)
parser.add_argument("--main-library", type=Path, required=True)
args = parser.parse_args()


def dispatch_checks(directory):
    directory.mkdir(parents=True)
    for name in HEADERS:
        (directory / name).write_text((ROOT / "compiler" / name).read_text())
    # This is the exact predecessor-produced dependency used by host IR targets.
    # Keep its generated bytes separate from the checked-in source set.
    generated_header = directory / GENERATED_HEADERS[0]
    generated_header.write_bytes(args.abi_header.read_bytes())
    enum_original = generated_header.read_text()
    result = compile_codec_probe(directory)
    if result.returncode:
        raise AssertionError(f"instruction codec unchanged mapping did not compile:\n{result.stderr}")
    print("PASS IR exhaustive unchanged instruction variant/form mapping control")
    original = (directory / "ir.hpp").read_text()
    pattern = re.compile(
        r"(template\s*<class Offsets,\s*class Services,\s*class Literals,\s*class Roots>\s*"
        r"using\s+BasicInstruction\s*=\s*std::variant<)(.*?)(>;)",
        re.DOTALL,
    )
    if len(pattern.findall(original)) != 1:
        raise AssertionError("could not uniquely locate the authoritative BasicInstruction inventory for injection")
    injected = pattern.sub(
        lambda match: "class ExhaustivenessProbe {};\n" + match[1] + match[2] + ", ExhaustivenessProbe" + match[3],
        original,
    )
    (directory / "ir.hpp").write_text(injected)
    result = compile_codec_probe(directory)
    if result.returncode == 0 or "unhandled typed IR instruction codec operation" not in result.stderr:
        raise AssertionError(f"instruction codec missing specific unknown variant rejection:\n{result.stderr}")
    print("PASS IR exhaustive unknown variant rejected by instruction codec")
    (directory / "ir.hpp").write_text(original)
    form_pattern = re.compile(r"(enum class InstructionForm\s*:\s*std::int64_t\s*\{)(.*?)(\};)", re.DOTALL)
    if len(form_pattern.findall(enum_original)) != 1:
        raise AssertionError("could not uniquely locate generated instruction forms")
    generated_header.write_text(
        form_pattern.sub(
            lambda match: match[1] + match[2].rstrip() + "\n    ExhaustivenessProbe = 999,\n" + match[3], enum_original
        )
    )
    result = compile_codec_probe(directory)
    if result.returncode == 0 or "instruction variant/form mapping must be one-to-one" not in result.stderr:
        raise AssertionError(f"instruction codec missing unknown form rejection:\n{result.stderr}")
    print("PASS IR exhaustive unknown source form rejected by instruction codec")
    generated_header.write_text(enum_original)
    print("3 canonical instruction-codec dispatch checks passed")


with tempfile.TemporaryDirectory(prefix="aurora-ir-exhaustive-") as scratch:
    dispatch_checks(Path(scratch) / "dispatch")
    source_verifier_probes(Path(scratch) / "verification-dispatch", args)
    source_emitter_probes(Path(scratch) / "dispatch", args)


# When the direct-IR executable is supplied, exercise the same validated module
# as actual native code. Keep this receipt separate from compile-time exhaustiveness.
if args.ir_tests is not None:
    from enum import Enum
    from integer_oracle import NativeRunner, command, validate_trap, validate_values

    class ArrayTrap(Enum):
        BOUNDS = ".Laurora_bounds_trap"
        RHS_ZERO = ".Laurora_division_zero_trap"

    with tempfile.TemporaryDirectory(prefix="aurora-ir-array-native-") as temporary:
        directory = Path(temporary)
        assembly = command([args.ir_tests.resolve(), "--output", AIR, "array-fields"]).stdout.decode()
        runner = NativeRunner(directory, None, 5)
        names = [
            "test",
            "array_scalar_mapping",
            "array_bool_mapping",
            "array_bool_zero",
            "array_bool_store",
            "array_copy",
        ]
        observed, _ = runner.assemble(assembly, names)
        validate_values(observed, [42, 7, 1, 0, 1, 42], names)
        native_count = len(names)
        trap_count = 0
        for target in ("array_dynamic", "array_store_dynamic"):
            for index in (0, 1, -1, 2, -(1 << 63), (1 << 63) - 1):
                name = f"{target}({index})"
                wrapper = (
                    f"\n.text\n.globl ir_array_probe\nir_array_probe:\n    movabsq ${index}, %rdi\n    jmp {target}\n"
                )
                observed, symbols = runner.assemble(assembly + wrapper, ["ir_array_probe"])
                if index not in (0, 1):
                    validate_trap(observed, ArrayTrap.BOUNDS, symbols, name)
                    trap_count += 1
                elif target == "array_store_dynamic":
                    # A valid index reaches the deliberately trapping RHS; an
                    # invalid one above must stop at the bounds site first.
                    validate_trap(observed, ArrayTrap.RHS_ZERO, symbols, name)
                    trap_count += 1
                else:
                    validate_values(observed, [0], [name])
                native_count += 1
        print(
            f"{native_count} native receiver-array IR checks passed "
            f"({trap_count} exact-site traps; scalar mapping, bool stride, zero init, "
            "copy ABI and bounds-before-RHS)"
        )

    with tempfile.TemporaryDirectory(prefix="aurora-ir-composed-native-") as temporary:
        directory = Path(temporary)
        assembly = command([args.ir_tests.resolve(), "--output", AIR, "composed-fields"]).stdout.decode()
        runner = NativeRunner(directory, None, 5)
        names = [
            "test",
            "nested_receiver_projection",
            "nested_scalar_mapping",
            "nested_snapshot_independence",
            "nested_projection_independence",
            "nested_bool_mapping",
            "nested_distinct_receiver_record",
            "nested_empty_copy",
        ]
        observed, _ = runner.assemble(assembly, names)
        validate_values(observed, [42, 42, 12, 9, 42, 1, 36, 42], names)
        print(
            f"{len(names)} native composed-value IR checks passed "
            "(nominal projection, independent snapshots/copies, bool stride, empty values "
            "and distinct receiver/argument records)"
        )

    with tempfile.TemporaryDirectory(prefix="aurora-ir-method-results-native-") as temporary:
        directory = Path(temporary)
        assembly = command([args.ir_tests.resolve(), "--output", AIR, "method-results"]).stdout.decode()
        runner = NativeRunner(directory, None, 5)
        names = [
            "test",
            "method_result_header",
            "method_result_first_array",
            "method_result_enum",
            "method_result_bool",
            "method_source_snapshot",
            "method_source_header",
            "method_result_independence",
            "method_forwarded_result",
            "method_empty_result",
            "method_empty_from_result",
            "method_enum_receiver_read",
            "method_result_saved_operand",
        ]
        observed, _ = runner.assemble(assembly, names)
        validate_values(observed, [42, 29, 11, 1, 1, 99, 12, 42, 29, 42, 42, 1, 45], names)
        print(
            f"{len(names)} native enum/composed-method-result IR checks passed "
            "(two-element arrays, enum and empty descendants, constructor snapshots, "
            "independent projection, forwarded receivers and nested hidden-register clobbers)"
        )

    class ByteTrap(Enum):
        ZERO = ".Laurora_division_zero_trap"
        OVERFLOW = ".Laurora_overflow_trap"
        COUNT = ".Laurora_shift_count_trap"

    # Direct IR width tests use Python's unbounded integers, including checks of
    # the full returned 64-bit word. Test input parameters obey the closed source
    # ABI's canonical-u8 contract; wide-to-byte conversions accept wide inputs.
    with tempfile.TemporaryDirectory(prefix="aurora-ir-u8-native-") as temporary:
        directory = Path(temporary)
        assembly = command([args.ir_tests.resolve(), "--output", AIR, "u8"]).stdout.decode()
        runner = NativeRunner(directory, None, 5)
        cases = [("byte_aggregate", (), 42), ("byte_receiver", (), 255), ("byte_local_array", (), 255)]
        edges = (0, 1, 2, 15, 16, 127, 128, 254, 255)
        for a in edges:
            for b in edges:
                results = [
                    a + b,
                    a - b,
                    a * b,
                    a // b if b else ByteTrap.ZERO,
                    a % b if b else ByteTrap.ZERO,
                    a & b,
                    a | b,
                    a ^ b,
                ]
                for operation, value in enumerate(results):
                    if isinstance(value, int) and not 0 <= value <= 255:
                        value = ByteTrap.OVERFLOW
                    cases.append((f"byte_op{operation}", (a, b), value))
                for operation, value in enumerate((a == b, a != b, a < b, a > b, a <= b, a >= b)):
                    cases.append((f"byte_compare{operation}", (a, b), int(value)))
            for count in (-(1 << 63), -1, 0, 1, 2, 6, 7, 8, 63, 64, (1 << 63) - 1):
                for left in (True, False):
                    if count < 0 or count > 7:
                        value = ByteTrap.COUNT
                    else:
                        value = a << count if left else a >> count
                        if value > 255:
                            value = ByteTrap.OVERFLOW
                    cases.append((f"byte_op{8 if left else 9}", (a, count), value))
        for value in range(256):
            cases.append(("byte_not", (value,), value ^ 255))
            for target in ("u8_to_i64", "u8_to_u64", "i64_to_u8", "u64_to_u8"):
                cases.append((target, (value,), value))
        for target in ("i64_to_u8", "u64_to_u8"):
            for value in (256, 257, 65535, (1 << 63) - 1):
                cases.append((target, (value,), ByteTrap.OVERFLOW))
        for value in (-(1 << 63), -1):
            cases.append(("i64_to_u8", (value,), ByteTrap.OVERFLOW))
        for value in (1 << 63, (1 << 64) - 1):
            cases.append(("u64_to_u8", (value,), ByteTrap.OVERFLOW))

        def byte_wrapper(name, target, arguments):
            registers = ("%rdi", "%rsi")
            lines = ["\n.text", f".globl {name}", f"{name}:"]
            lines += [f"    movabsq ${value}, {registers[index]}" for index, value in enumerate(arguments)]
            lines += [f"    jmp {target}", ""]
            return "\n".join(lines)

        positives = [(target, args, value) for target, args, value in cases if not isinstance(value, ByteTrap)]
        traps = [(target, args, value) for target, args, value in cases if isinstance(value, ByteTrap)]
        for offset in range(0, len(positives), 200):
            batch = positives[offset : offset + 200]
            names = [f"byte_probe_{index}" for index in range(len(batch))]
            wrappers = "".join(byte_wrapper(name, target, args) for name, (target, args, _) in zip(names, batch))
            observed, _ = runner.assemble(assembly + wrappers, names)
            validate_values(
                observed, [value for _, _, value in batch], [f"{target}{args}" for target, args, _ in batch]
            )
        for target, arguments, trap in traps:
            wrapper = byte_wrapper("byte_trap_probe", target, arguments)
            observed, symbols = runner.assemble(assembly + wrapper, ["byte_trap_probe"])
            validate_trap(observed, trap, symbols, f"{target}{arguments}")
        print(
            f"{len(cases)} native u8 numerical IR checks passed "
            f"({len(traps)} exact-site traps; every complement/conversion byte, "
            "boundary arithmetic and shifts, canonical results, packed-storage calls/copies)"
        )

    with tempfile.TemporaryDirectory(prefix="aurora-ir-packed-method-native-") as temporary:
        directory = Path(temporary)
        assembly = command([args.ir_tests.resolve(), "--output", AIR, "packed-methods"]).stdout.decode()
        runner = NativeRunner(directory, None, 5)
        names = [
            "packed_result_array",
            "packed_result_header",
            "packed_result_first",
            "packed_result_enum",
            "packed_result_bool",
            "packed_source_array",
            "packed_source_header",
            "packed_result_independence",
            "packed_forwarded_result",
            "packed_empty_result",
            "packed_tiny_roundtrip",
        ]
        expected = [42, 29, 11, 1, 1, 99, 12, 42, 29, 42, 128]
        # The private ABI bridge supplies canonical leaves and a pristine result.
        # Nonzero input padding must not be copied as data or clobber its neighbor.
        source_word = 0x7EADBEEF00FF8007
        neighbor = 0x1122334455667788
        for index, (offset, value) in enumerate(((8, 0xFF8007), (16, neighbor), (0, source_word))):
            name = f"packed_record_probe{index}"
            names.append(name)
            expected.append(value)
            assembly += (
                f"\n.text\n.globl {name}\n{name}:\n"
                "    subq $40, %rsp\n"
                f"    movabsq ${source_word}, %rax\n    movq %rax, (%rsp)\n"
                "    movq $0, 8(%rsp)\n"
                f"    movabsq ${neighbor}, %rax\n    movq %rax, 16(%rsp)\n"
                "    leaq (%rsp), %r11\n    leaq 8(%rsp), %r10\n"
                "    call packed_copy_tiny\n"
                f"    movq {offset}(%rsp), %rax\n    addq $40, %rsp\n    ret\n"
            )
        observed, _ = runner.assemble(assembly, names)
        validate_values(observed, expected, names)
        print(
            f"{len(names)} native packed-byte IR checks passed "
            "(mixed alignment, enum and empty descendants, receiver/result hidden registers, "
            "constructor snapshots, nested copies, compact aggregate records and padding isolation)"
        )

    with tempfile.TemporaryDirectory(prefix="aurora-ir-span-native-") as temporary:
        directory = Path(temporary)
        assembly = command([args.ir_tests.resolve(), "--output", AIR, "spans"]).stdout.decode()
        runner = NativeRunner(directory, None, 5)
        names = [
            "span_local",
            "span_length",
            "span_preserve_current",
            "span_mixed_sum",
            "span_mixed_first",
            "span_mixed_last",
            "span_mixed_saved_operand",
        ]
        observed, _ = runner.assemble(assembly, names)
        validate_values(observed, [128, 3, 255, 299, 31, 77, 1299], names)
        native_count = len(names)
        trap_count = 0
        for index in (0, 1, 2, -1, 3, -(1 << 63), (1 << 63) - 1):
            wrapper = (
                f"\n.text\n.globl ir_span_probe\nir_span_probe:\n    movabsq ${index}, %rdi\n    jmp span_dynamic\n"
            )
            observed, symbols = runner.assemble(assembly + wrapper, ["ir_span_probe"])
            if index in (0, 1, 2):
                validate_values(observed, [(11, 128, 255)[index]], [f"span_dynamic({index})"])
            else:
                validate_trap(observed, ArrayTrap.BOUNDS, symbols, f"span_dynamic({index})")
                trap_count += 1
            native_count += 1
        print(
            f"{native_count} native readonly-span IR checks passed "
            f"({trap_count} exact-site traps; capability forwarding, six mixed scalar/class/span "
            "positions, class returns, saved operands and bounds before payload access)"
        )
