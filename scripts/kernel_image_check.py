#!/usr/bin/env python3
"""Linked kernel image check (a modpost-like build step).

Format and permission properties of every image, plus the declarative symbol
policy in kernel-images/image-policy.py:

- UEFI PE32+: EFI application, NX and dynamic-base flags, no writable and
  executable section, entry in an executable section, no imports, only DIR64
  base relocations that target the image.
- Linked ELF (payload, BIOS kernel, user programs): no writable and executable
  segment, page-aligned non-overlapping loads, entry in an executable segment,
  no undefined symbols, no constructor sections.
- Position-independent payload objects carry only PC-relative relocations.
- Profile policy: symbols the image must not define, and the complete set of
  runtime symbols each generated Aurora object may import.

Usage:
  kernel_image_check.py --profile ID --policy FILE --output STAMP
      [--pe EFI] --elf ELF [--pic-object O ...] [--language O ...] [--user ELF ...]
"""

from fnmatch import fnmatch
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kernel_elf import PF_W, PF_X, Elf, image_policy  # noqa: E402

PIC_RELOCATIONS = {2, 4}  # R_X86_64_PC32, R_X86_64_PLT32
CONSTRUCTORS = (".init_array", ".fini_array", ".ctors", ".dtors", ".preinit_array")


class CheckError(ValueError):
    pass


def need(condition, message):
    if not condition:
        raise CheckError(message)


def check_pe(path):
    data = Path(path).read_bytes()

    def u(offset, size):
        need(0 <= offset and offset + size <= len(data), f"{path}: truncated PE")
        return int.from_bytes(data[offset : offset + size], "little")

    need(data[:2] == b"MZ", f"{path}: missing DOS header")
    nt = u(60, 4)
    need(data[nt : nt + 4] == b"PE\0\0" and u(nt + 4, 2) == 0x8664, f"{path}: not an x86-64 PE image")
    count, optional = u(nt + 6, 2), u(nt + 20, 2)
    opt = nt + 24
    need(u(opt, 2) == 0x20B and u(opt + 68, 2) == 10, f"{path}: not a PE32+ EFI application")
    need(u(opt + 70, 2) & 0x140 == 0x140, f"{path}: NX/dynamic-base flags missing")
    base, entry, size = u(opt + 24, 8), u(opt + 16, 4), u(opt + 56, 4)
    sections = []
    for index in range(count):
        at = opt + optional + index * 40
        virtual, rva, raw, offset, flags = u(at + 8, 4), u(at + 12, 4), u(at + 16, 4), u(at + 20, 4), u(at + 36, 4)
        need(not (flags & 0x20000000 and flags & 0x80000000), f"{path}: writable and executable section")
        need(rva + max(virtual, raw) <= size, f"{path}: section outside the image")
        for other in sections:
            need(
                rva >= other[0] + max(other[1], other[2]) or other[0] >= rva + max(virtual, raw),
                f"{path}: overlapping sections",
            )
        sections.append((rva, virtual, raw, offset, flags))

    def locate(rva, length):
        for start, virtual, raw, offset, flags in sections:
            if start <= rva and rva + length <= start + min(virtual, raw):
                return offset + rva - start, flags
        raise CheckError(f"{path}: RVA {rva:#x} is not file-backed")

    need(locate(entry, 1)[1] & 0x20000000, f"{path}: entry is not executable")
    imports, import_size = u(opt + 120, 4), u(opt + 124, 4)
    if import_size:
        at, _ = locate(imports, import_size)
        need(not any(data[at : at + import_size]), f"{path}: external imports")
    cursor, length = u(opt + 152, 4), u(opt + 156, 4)
    need(length >= 12, f"{path}: missing base relocations")
    cursor, _ = locate(cursor, length)
    end = cursor + length
    while cursor < end:
        page, block = u(cursor, 4), u(cursor + 4, 4)
        need(block >= 8 and cursor + block <= end, f"{path}: malformed relocation block")
        for at in range(cursor + 8, cursor + block, 2):
            item = u(at, 2)
            if item >> 12:
                need(item >> 12 == 10, f"{path}: only DIR64 base relocations are allowed")
                target, _ = locate(page + (item & 4095), 8)
                need(base <= u(target, 8) < base + size, f"{path}: relocation target outside the image")
        cursor += block


def check_elf(path, allow_undefined=()):
    elf = Elf(path)
    need(elf.type == 2, f"{path}: not a linked executable")
    loads = sorted((s for s in elf.segments if s.kind == 1), key=lambda s: s.address)
    need(loads, f"{path}: no loadable segments")
    for segment in loads:
        need(not (segment.flags & PF_W and segment.flags & PF_X), f"{path}: writable and executable segment")
        need(
            segment.address % 4096 == 0 and segment.memory_size >= segment.file_size,
            f"{path}: unaligned or truncated segment",
        )
    for previous, current in zip(loads, loads[1:]):
        need(
            (previous.address + previous.memory_size + 4095) // 4096 * 4096 <= current.address,
            f"{path}: segments share a page",
        )
    need(
        any(s.flags & PF_X and s.address <= elf.entry < s.address + s.file_size for s in loads),
        f"{path}: entry {elf.entry:#x} is not in an executable segment",
    )
    undefined = elf.undefined() - set(allow_undefined)
    need(not undefined, f"{path}: undefined symbols {sorted(undefined)}")
    need(
        not any(s.name.startswith(CONSTRUCTORS) for s in elf.sections if s.size),
        f"{path}: constructor sections never run in a freestanding image",
    )
    return elf


def check_pic(path):
    elf = Elf(path)
    kinds = {kind for section, _, kind, _, _ in elf.relocations if elf.sections[section].flags & 2}
    need(kinds <= PIC_RELOCATIONS, f"{path}: non-PC-relative relocation types {sorted(kinds)}")


def check_policy(profile, policy, image, languages):
    defined = image.defined()
    present = sorted(name for name in defined if any(fnmatch(name, pattern) for pattern in policy.get("forbidden", [])))
    need(not present, f"{profile}: forbidden symbols present: {present}")
    for path in languages:
        imports = Elf(path).undefined()
        # "imports:STEM" rules widen only the generated object named STEM.o.
        allowed = policy["imports"] + policy.get("imports:" + Path(path).stem, [])
        extra = sorted(name for name in imports if not any(fnmatch(name, pattern) for pattern in allowed))
        need(not extra, f"{profile}: {Path(path).name} imports symbols outside its policy: {extra}")


def main(argv):
    arguments = dict(pe=None, elf=None, output=None, profile=None, policy=None)
    lists = dict(pic_object=[], language=[], user=[])
    iterator = iter(argv)
    for flag in iterator:
        key = flag.removeprefix("--").replace("-", "_")
        value = next(iterator, None)
        if key in arguments and value is not None:
            arguments[key] = value
        elif key in lists and value is not None:
            lists[key].append(value)
        else:
            print(__doc__, file=sys.stderr)
            return 2
    try:
        policy = image_policy(arguments["policy"], arguments["profile"])
        need("imports" in policy, f"{arguments['profile']}: no import policy in the image policy table")
        if arguments["pe"]:
            check_pe(arguments["pe"])
        image = check_elf(arguments["elf"])
        for path in lists["pic_object"]:
            check_pic(path)
        for path in lists["user"]:
            user = check_elf(path)
            need(len([s for s in user.segments if s.kind == 1]) == 1, f"{path}: user image must be one segment")
            need(not user.relocations, f"{path}: user image retains relocations")
        check_policy(arguments["profile"], policy, image, lists["language"])
    except CheckError as error:
        print("FAIL: kernel image check: " + str(error), file=sys.stderr)
        return 1
    Path(arguments["output"]).write_text("checked\n")
    print(f"PASS: {arguments['profile']} image format, W^X and symbol policy")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
