#!/usr/bin/env python3
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from kernel_uefi_oracle import need, validate

# kernel-acpi-smoke.py loads this module and reuses its need().
__all__ = ["need", "validate"]


if __name__ == "__main__":
    try:
        validate(int(sys.argv[1]), Path(sys.argv[2]).read_text(), sys.argv[3])
    except ValueError as error:
        sys.exit(f"FAIL: {error}")
