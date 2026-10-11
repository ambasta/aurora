#!/usr/bin/env python3
from pathlib import Path
import importlib.util, struct

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


images = load("dispatch_images", ROOT / "scripts/kernel-uefi-ipc-images.py")
fixtures = load("dispatch_image_fixture", ROOT / "tests/kernel-uefi-user-image.py")


def main():
    positive = negative = 0
    for index in range(3):
        base = images.BASE + index * 4096
        data, blob, symbols = fixtures.fixture(base)
        images.verify(data, blob, base, symbols, dispatcher=True)
        positive += 1
        tests = []
        for key in (
            "aurora_program_entry",
            "aurora_program_return_pc",
            ".Laurora_bounds_trap",
            ".Laurora_overflow_trap",
            ".Laurora_division_zero_trap",
            ".Laurora_shift_count_trap",
        ):
            for address in (0, base - 1, base + 4096):
                changed = symbols.copy()
                changed[key] = address
                if address == 0 and key in (".Laurora_division_zero_trap", ".Laurora_shift_count_trap"):
                    continue
                tests.append((data, blob, base, changed))
        for flags in (4, 6, 7):
            changed = data.copy()
            struct.pack_into("<I", changed, 68, flags)
            tests.append((changed, blob, base, symbols))
        for address in (images.BASE - 4096, images.BASE + 3 * 4096, images.BASE + 0x200000):
            foreign = fixtures.fixture(address)
            tests.append((*foreign[:2], address, foreign[2]))
        for args in tests:
            try:
                images.verify(*args, dispatcher=True)
            except ValueError:
                negative += 1
            else:
                raise RuntimeError("Malformed dispatcher image accepted")
        if index == 2:
            try:
                images.verify(data, blob, base, symbols)
            except ValueError:
                negative += 1
            else:
                raise RuntimeError("Default two-image profile widened")
    data, blob, symbols = fixtures.fixture(images.BASE)
    for count in (0, 1, 4, True, 1 << 64):
        try:
            images._base.verify(data, blob, images.BASE, symbols, image_count=count)
        except ValueError:
            negative += 1
        else:
            raise RuntimeError("Unknown image profile accepted")
    print(f"PASS: dispatcher image profiles {positive} positive and {negative} negative cases")


if __name__ == "__main__":
    main()
