#!/usr/bin/env python3
"""Execute the exact safe kernel fixtures with full-width and exact-site checks."""

import importlib.util
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
# Reuse the independently tested native signal observer and whole-result checker.
SPEC = importlib.util.spec_from_file_location("unsigned_oracle", ROOT / "tests/compiler/unsigned_oracle.py")
oracle = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = oracle
SPEC.loader.exec_module(oracle)
IMAGE_SPEC = importlib.util.spec_from_file_location("kernel_user_image", ROOT / "tests/kernel-user-image.py")
image = importlib.util.module_from_spec(IMAGE_SPEC)
IMAGE_SPEC.loader.exec_module(image)


def main() -> None:
    compiler = Path(os.environ.get("AURORAC", ROOT / "build/aurorac")).resolve()
    with tempfile.TemporaryDirectory(prefix="aurora-kernel-unsigned-") as temporary:
        directory = Path(temporary)
        runner = oracle.NativeRunner(directory, compiler, 5)
        kernel_entry = directory / "kernel-entry.o"
        oracle.command(["as", "--64", ROOT / "kernel/program-entry.S", "-o", kernel_entry])
        for name, expected in (
            ("valid", None),
            ("shift-count", oracle.Trap.COUNT),
            ("shift-wide", oracle.Trap.COUNT),
            ("conversion-overflow", oracle.Trap.OVERFLOW),
        ):
            source = ROOT / f"tests/kernel-programs/unsigned-{name}.au"
            assembly = directory / "fixture.s"
            oracle.command([compiler, source, "-o", assembly])
            observed, symbols = runner.assemble(assembly.read_text(), ["aurora_user_main"])
            if expected is None:
                oracle.require(
                    observed.exit_code == 0 and observed.output == (42).to_bytes(8, "little"),
                    "Unsigned kernel fixture did not return the complete expected scalar",
                )
            else:
                oracle.validate_trap(observed, expected, symbols, name)
            # Independently link the same emitted object as its bounded RX
            # kernel image, including the >=64 fixture not added as a fifth
            # emulator mode. The host observer is absent from these bytes.
            base = image.BASE + (0 if name == "valid" else 8192 if name == "conversion-overflow" else 4096)
            linked, binary = directory / "user.elf", directory / "user.bin"
            oracle.command(
                [
                    "ld",
                    "-nostdlib",
                    "--discard-none",
                    "-z",
                    "max-page-size=0x1000",
                    "-T",
                    ROOT / "kernel/program.ld",
                    f"--defsym=USER_BASE={base}",
                    kernel_entry,
                    directory / "program.o",
                    "-o",
                    linked,
                ]
            )
            oracle.command(["objcopy", "-O", "binary", linked, binary])
            sites = image.sites(binary.read_bytes(), base, image.symbols_for(linked))
            oracle.require(
                sites["division_zero"] != 0 and sites["shift_count"] != 0,
                "Linked unsigned fixture lost exact fault authority",
            )
    print(
        (
            "PASS: 4 exact kernel unsigned fixtures and bounded RX images: full-width values, negative/64 shift"
            " counts, conversion overflow"
        )
    )


if __name__ == "__main__":
    main()
