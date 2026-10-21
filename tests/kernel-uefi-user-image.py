#!/usr/bin/env python3
from pathlib import Path
import importlib.util, os, shlex, struct, subprocess, sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import kernel_stack as stack

spec = importlib.util.spec_from_file_location(
    "images", Path(__file__).resolve().parents[1] / "scripts/kernel-uefi-user-images.py"
)
images = importlib.util.module_from_spec(spec)
spec.loader.exec_module(images)


def fixture(base, size=128):
    blob = bytearray([0x90] * size)
    blob[14:18] = b"\xcd\x81\x0f\x0b"
    for at in (32, 40, 48, 56):
        blob[at : at + 2] = b"\x0f\x0b"
    data = bytearray(4096 + len(blob))
    data[:7] = b"\x7fELF\x02\x01\x01"
    struct.pack_into("<HH", data, 16, 2, 62)
    struct.pack_into("<QQ", data, 24, base, 64)
    struct.pack_into("<HH", data, 54, 56, 1)
    struct.pack_into("<IIQQQQQQ", data, 64, 1, 5, 4096, base, base, len(blob), len(blob), 4096)
    data[4096:] = blob
    symbols = {
        "aurora_program_entry": base,
        "aurora_user_main": base + 8,
        "aurora_program_return_pc": base + 16,
        ".Laurora_bounds_trap": base + 32,
        ".Laurora_overflow_trap": base + 40,
        ".Laurora_division_zero_trap": base + 48,
        ".Laurora_shift_count_trap": base + 56,
    }
    return data, blob, symbols


def multipage_controls():
    positive = negative = 0

    def reject(action):
        nonlocal negative
        try:
            action()
        except (ValueError, RuntimeError):
            negative += 1
        else:
            raise RuntimeError("Invalid multipage stack/entry contract accepted")

    base = images.BASE
    for fault in (False, True):
        end = base + (68 if fault else 63)
        symbols = dict(
            aurora_program_entry=base, bad_entry=end - 2, aurora_user_main=base + 256, aurora_program_return_pc=end - 4
        )
        code = {}
        cursor = base

        def add(size, op, args):
            nonlocal cursor
            code[cursor] = stack.Instruction(cursor, size, op, args)
            cursor += size

        for reg in ("rbx", "rcx", "rdx", "rbp", "rsi", "rdi", "r8", "r9", "r10", "r11", "r12", "r13", "r14", "r15"):
            add(3, "or", f"%{reg},%rax")
        add(2, "jne", f"{end - 2:x} <bad_entry>")
        add(6, "cmpq", "$0x0,-0x8(%rsp)")
        add(2, "jne", f"{end - 2:x} <bad_entry>")
        if fault:
            add(5, "mov", "$0x1,%edi")
        add(5, "call", f"{base + 256:x} <aurora_user_main>")
        add(2, "int", "$0x81")
        add(2, "ud2", "")
        add(2, "ud2", "")
        images.need(cursor == end, "Multipage fixture extent")
        images.need(images.multipage_wrapper(code, symbols, base, fault) == end, "Multipage wrapper extent")
        positive += 1
        for address in code:
            changed = dict(code)
            row = changed[address]
            changed[address] = stack.Instruction(row.address, row.size, "nop", "")
            reject(lambda: images.multipage_wrapper(changed, symbols, base, fault))
        for name in symbols:
            changed = dict(symbols)
            changed[name] += 1
            reject(lambda: images.multipage_wrapper(code, changed, base, fault))
        reject(lambda: images.multipage_wrapper(code, symbols, base, not fault))

    late = "__au_m_m2_3std4utf8_n2_3std16Utf8EncodeResult_d7byte_or"
    functions = {
        "aurora_user_main": dict(local_peak=32, calls=[dict(target=late, live_bytes=32)]),
        late: dict(local_peak=48, calls=[]),
    }
    symbols = {late: base + 9000, ".Laurora_bounds_trap": base + 10000}
    images.need(images.multipage_evidence(functions, symbols, base)["peak_with_wrapper"] == 88, "Multipage stack peak")
    positive += 1
    for name in symbols:
        changed = dict(symbols)
        changed[name] = base + 8192
        reject(lambda: images.multipage_evidence(functions, changed, base))
    changed = {**functions, "aurora_user_main": dict(local_peak=32, calls=[])}
    reject(lambda: images.multipage_evidence(changed, symbols, base))
    changed = {**functions, late: dict(local_peak=15360, calls=[])}
    reject(lambda: images.multipage_evidence(changed, symbols, base))
    changed = {**functions, late: dict(local_peak=48, calls=[dict(target=late, live_bytes=48)])}
    reject(lambda: images.multipage_evidence(changed, symbols, base))
    return positive, negative


def image_policy_controls():
    # Exercise the actual header, not a source-text check or a copied default.
    compiler = shlex.split(os.environ.get("CXX", "g++"))
    source = '#include "kernel/uefi/image-page-policy.hpp"\n'
    command = compiler + ["-std=c++23", "-Werror", "-fsyntax-only", "-x", "c++", "-I", str(images.ROOT), "-"]
    policies = {"one_page": (1, 1, 1), "multipage": (3, 3, 3), "call": (2, 1, 1), "owned_text": (3, 1, 1)}
    for policy in (None, "unknown_image_policy", *policies):
        flags = [] if policy is None else ["-DAURORA_RUNTIME_IMAGE_POLICY=" + policy]
        assertions = ""
        if policy in policies:
            assertions = "".join(
                f"static_assert(aurora::uefi::ImagePagePolicy::pages({index}) == {pages});\n"
                for index, pages in enumerate((*policies[policy], 0))
            )
        result = subprocess.run(command + flags, input=source + assertions, text=True, capture_output=True, timeout=30)
        diagnostic = result.stdout + result.stderr
        images.need((result.returncode == 0) == (policy in policies), f"Image policy {policy}: {diagnostic}")
        if policy not in policies:
            expected = "Select an explicit AURORA_RUNTIME_IMAGE_POLICY" if policy is None else "unknown_image_policy"
            images.need(expected in diagnostic, f"Wrong image policy rejection: {diagnostic}")
    return len(policies), 2


def main():
    cases, rejected = multipage_controls()
    positive, negative = image_policy_controls()
    cases += positive
    rejected += negative
    for base in (images.BASE, images.BASE + 16384):
        data, blob, symbols = fixture(base)
        images.verify(data, blob, base, symbols)
        cases += 1
        failures = []
        for length in (0, 7, 16, 63, 100):
            failures.append((data[:length], blob, base, symbols))
        for offset, width, value in (
            (16, 2, 3),
            (18, 2, 3),
            (24, 8, base + 1),
            (32, 8, len(data)),
            (54, 2, 55),
            (56, 2, 2),
            (64, 4, 2),
            (68, 4, 7),
            (80, 8, 0),
            (88, 8, 0),
            (96, 8, 4097),
            (104, 8, 129),
        ):
            changed = data.copy()
            changed[offset : offset + width] = value.to_bytes(width, "little")
            failures.append((changed, blob, base, symbols))
        failures.append((data, blob, 0, symbols))
        failures.append((data, blob[:-1], base, symbols))
        for name in symbols:
            changed = symbols.copy()
            changed[name] = base + 4096
            failures.append((data, blob, base, changed))
        for name in (".Laurora_bounds_trap", ".Laurora_overflow_trap"):
            changed = symbols.copy()
            changed[name] = base + 16
            failures.append((data, blob, base, changed))
        for offset in (1, 127, 129):
            changed = symbols.copy()
            changed["aurora_kernel_probe_target"] = base + offset
            failures.append((data, blob, base, changed))
        changed = blob.copy()
        changed[16] = 0x90
        elf = data.copy()
        elf[4096:] = changed
        failures.append((elf, changed, base, symbols))
        for arguments in failures:
            try:
                images.verify(*arguments)
            except ValueError:
                rejected += 1
            else:
                raise RuntimeError("Invalid high-VA user image accepted")
    data, blob, symbols = fixture(images.BASE)
    blob[88:96] = bytes(8)
    data[4096:] = blob
    symbols["aurora_kernel_probe_target"] = images.BASE + 88
    images.verify(data, blob, images.BASE, symbols)
    cases += 1
    # Explicit capacity only: defaults remain one page. ELF file offsets and
    # page alignment stay 4096 while independent virtual slots have stride 16384.
    for size in (4096, 4097, 8192, 8193, 12288, 12289):
        data, blob, symbols = fixture(images.BASE, size)
        # Retained terminal authority at the actual final two bytes, including
        # a split-page instruction at size4097 and later-page sites thereafter.
        blob[-2:] = b"\x0f\x0b"
        symbols[".Laurora_bounds_trap"] = images.BASE + size - 2
        if size >= 8192:
            blob[4096:4100] = b"\xcd\x81\x0f\x0b"
            symbols["aurora_program_return_pc"] = images.BASE + 4098
            symbols["aurora_user_main"] = images.BASE + 4100
        data[4096:] = blob
        for pages in (None, 1, 2, 3):
            options = {} if pages is None else dict(max_pages=pages)
            accepted = size <= 4096 * (1 if pages is None else pages)
            try:
                result = images.verify(data, blob, images.BASE, symbols, **options)
            except ValueError:
                if accepted:
                    raise
                rejected += 1
            else:
                if not accepted or result["size"] != size:
                    raise RuntimeError("Image crossed its explicit page allowance")
                cases += 1
        if size <= 12288:
            mutations = []
            changed = blob.copy()
            changed[-1] = 0x90
            elf = data.copy()
            elf[4096:] = changed
            mutations.append((elf, changed, symbols))
            mutations.append((data, blob[:-1], symbols))
            for offset, value in ((68, 7), (96, size - 1), (104, size + 1)):
                elf = data.copy()
                struct.pack_into("<I" if offset == 68 else "<Q", elf, offset, value)
                mutations.append((elf, blob, symbols))
            for pc in (images.BASE + size - 1, images.BASE + 12288, images.BASE + 16384):
                mutations.append((data, blob, dict(symbols, **{".Laurora_bounds_trap": pc})))
            for elf, installed, names in mutations:
                try:
                    images.verify(elf, installed, images.BASE, names, max_pages=3)
                except ValueError:
                    rejected += 1
                else:
                    raise RuntimeError("Malformed later-page bytes/extent/site accepted")
    data, blob, symbols = fixture(images.BASE)
    for pages in (0, -1, 4, True, False, 1.0, "3", None, 1 << 64):
        try:
            images.verify(data, blob, images.BASE, symbols, max_pages=pages)
        except ValueError:
            rejected += 1
        else:
            raise RuntimeError("Invalid image page allowance accepted")
    for base in (images.BASE + 4096, images.BASE + 8192, images.BASE + 12288):
        data, blob, symbols = fixture(base)
        try:
            images.verify(data, blob, base, symbols, max_pages=3)
        except ValueError:
            rejected += 1
        else:
            raise RuntimeError("Non-slot or guard virtual entry accepted")
    print(f"PASS: UEFI user image metadata {cases} positive and {rejected} negative cases")


if __name__ == "__main__":
    main()
