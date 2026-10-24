#!/usr/bin/env python3
"""Native replay of the runtime-span profile's user programs.

The profile's clean user program must return 42, and its bounds fixture and the
checked-in reads one element before and after the span must each stop at the
exact bounds UD2. No guest runs here.
"""

from enum import Enum
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests/compiler"))
from unsigned_oracle import Case, NativeRunner, command, validate_trap, validate_values  # noqa: E402


class Trap(Enum):
    BOUNDS = ".Laurora_bounds_trap"


def main():
    compiler, span_dir = Path(sys.argv[1]).resolve(strict=True), Path(sys.argv[2]).resolve(strict=True)
    span = json.loads((span_dir / "user-images.json").read_text())
    with tempfile.TemporaryDirectory(prefix="aurora-uefi-span-") as temporary:
        native = Path(temporary)
        runner = NativeRunner(native, compiler, 5)
        observed, _ = runner.assemble((span_dir / "user-clean.s").read_text(), ["aurora_user_main"])
        validate_values(observed, [Case("span-clean", "", 42, "i64")])
        observed, symbols = runner.assemble((span_dir / "user-bounds.s").read_text(), ["aurora_user_main"])
        validate_trap(observed, Trap.BOUNDS, symbols, "unchanged bounds fixture")
        for side in ("before", "after"):
            assembly = native / f"span-bounds-{side}.s"
            source = ROOT / f"tests/kernel-programs/span-bounds-{side}.au"
            command([compiler, source, "--module-root", ROOT / "library", "-o", assembly])
            observed, symbols = runner.assemble(assembly.read_text(), ["aurora_user_main"])
            validate_trap(observed, Trap.BOUNDS, symbols, f"span bounds {side}")
    print(f"PASS: UEFI span image {span['clean']['size']} bytes; native return 42 and 3 exact bounds traps")


if __name__ == "__main__":
    main()
