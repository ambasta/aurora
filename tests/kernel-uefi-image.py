#!/usr/bin/env python3
"""Compatibility test/CLI entrypoint for the shared independent UEFI validator."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from kernel_uefi_image import *  # noqa: F403 - preserve existing pure-validator imports

if __name__ == "__main__":
    cli()  # noqa: F405
