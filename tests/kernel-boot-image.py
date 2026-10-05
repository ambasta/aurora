#!/usr/bin/env python3
"""Exercise the production BIOS linker with host-note and invalid-layout variants."""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def run(*args: str, ok: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(args, cwd=ROOT, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=15)
    if ok:
        require(result.returncode == 0, f"{args!r}: {result.stdout}{result.stderr}")
    return result


def main() -> None:
    for tool in ("as", "ld", "nm", "objcopy", "objdump"):
        require(shutil.which(tool) is not None, f"Missing dependency: {tool}")
    source = (ROOT / "kernel/boot.S").read_text()
    link = str(ROOT / "scripts/kernel-boot-link.sh")
    with tempfile.TemporaryDirectory(prefix="aurora-boot-") as temporary:
        work = Path(temporary)
        baseline = None
        for name, flags in (
                ("default", ()),
                ("notes-off", ("-mx86-used-note=no",)),
                ("notes-on", ("-mx86-used-note=yes",)),
                ("build-notes", ("-mx86-used-note=yes", "--generate-missing-build-notes=yes"))):
            obj, binary = work / f"{name}.o", work / f"{name}.bin"
            run("as", "--32", *flags, str(ROOT / "kernel/boot.S"), "-o", str(obj))
            sections = run("objdump", "-h", str(obj)).stdout
            if name in ("notes-on", "build-notes"):
                require(".note.gnu.property" in sections,
                        f"{name}: missing adversarial allocated GNU property note")
            if name == "build-notes":
                require(".gnu.build.attributes" in sections,
                        "Missing generated GNU build attributes")
            run(link, str(obj), str(binary))
            boot = binary.read_bytes()
            require(len(boot) == 512, f"{name}: expected one BIOS sector, got {len(boot)}")
            require(boot[:1] == b"\xea" and boot[510:] == b"\x55\xaa",
                    f"{name}: boot entry/signature changed")
            if baseline is None:
                baseline = boot
            require(boot == baseline, f"{name}: host metadata changed boot bytes")
            symbols = run("nm", "-a", str(obj)).stdout.splitlines()
            packets = [int(line.split()[0], 16) for line in symbols
                       if line.split()[-1] == "packet"]
            require(len(packets) == 1, f"{name}: missing unique packet")
            packet = packets[0]
            require(packet % 4 == 0 and 0 <= packet <= 494,
                    f"{name}: invalid packet offset")
            require(boot[packet:packet + 16] == bytes.fromhex("10007f00000000100100000000000000"),
                    f"{name}: BIOS payload read contract changed")

        # An ELF reference safely extracts only relocated text from the previous
        # link layout. Never repeat the unbounded old raw-binary orphan link.
        legacy = work / "legacy.elf"
        run("ld", "-m", "elf_i386", "--build-id=none", "-Ttext", "0x7c00",
            "-e", "_boot", str(work / "notes-off.o"), "-o", str(legacy))
        reference = work / "legacy-text.bin"
        run("objcopy", "-O", "binary", "--only-section=.text", str(legacy), str(reference))
        require(reference.read_bytes() == baseline, "Existing relocated BIOS instruction bytes changed")

        # Both allocated and unallocated unknown sections fail, rather than
        # silently hiding potentially required input. Known GNU metadata alone
        # is discarded. None of these fixtures touches the production source.
        negatives = (
            ("data", source + '\n.data\n.byte 1\n', "separate writable storage"),
            ("bss", source + '\n.bss\n.space 1\n', "separate writable storage"),
            ("common", source + '\n.comm extra_storage,4,4\n', "separate writable storage"),
            ("orphan-allocated", source + '\n.section .unexpected,"a"\n.byte 1\n', "unplaced orphan section"),
            ("orphan-unallocated", source + '\n.section .unexpected,""\n.byte 1\n', "unplaced orphan section"),
            ("unknown-note", source + '\n.section .note.unexpected,"a",@note\n.long 0,0,0\n', "unplaced orphan section"),
            ("text-overflow", source + '\n.text\n.byte 0\n', "exactly one BIOS sector"),
            ("short-sector", source.replace('.org 510', '.org 509'), "exactly one BIOS sector"),
            ("moved-entry", source.replace('_boot:', '.byte 0\n_boot:', 1), "first BIOS byte"),
        )
        for name, fixture, diagnostic in negatives:
            asm, obj, binary = (work / f"{name}.{suffix}" for suffix in ("S", "o", "bin"))
            asm.write_text(fixture)
            run("as", "--32", "-mx86-used-note=no", str(asm), "-o", str(obj))
            result = run(link, str(obj), str(binary), ok=False)
            require(result.returncode != 0 and diagnostic in result.stderr,
                    f"{name}: invalid input was accepted or failed for the wrong reason: {result.stderr}")
            require(not binary.exists(), f"{name}: linker retained a rejected output")

    print("PASS: four host-note variants produce identical 512-byte BIOS sectors; "
          "legacy relocated text, entry, signature and EDD packet preserved; nine layout rejections")


if __name__ == "__main__":
    main()
