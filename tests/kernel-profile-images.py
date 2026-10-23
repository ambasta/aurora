#!/usr/bin/env python3
"""Every canonical kernel profile was built: full covers each image, not a sample."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import kernel_profiles  # noqa: E402


def missing(root):
    result = []
    for name in sorted(kernel_profiles.profiles()):
        platform, mode = name.split("/", 1)
        outputs = ["aurora.img"] if platform == "bios" else ["image-metadata.json", "esp/EFI/BOOT/BOOTX64.EFI"]
        result += [name + ": " + output for output in outputs if not (root / platform / mode / output).is_file()]
    return result


if __name__ == "__main__":
    root = Path(sys.argv[1])
    absent = missing(root)
    if absent:
        raise SystemExit("FAIL: unbuilt kernel profile outputs:\n" + "\n".join(absent))
    print(f"PASS: {len(kernel_profiles.profiles())} kernel profile images built")
