#!/usr/bin/env python3
"""Hosted graphical console: the real generated Aurora consumer over scripted sessions.

The Meson-built host links the compiled consumer, its private entry and the
production sessions, runs each case below in a fresh child and reports exact
counters and digests of the store sequence, every viewport checkpoint and the
final guarded framebuffer. The results are compared with the reviewed golden
file; `--update` rewrites it for an intended change. This is hosted evidence,
not native image or guest qualification.
"""

from pathlib import Path
import argparse
import subprocess
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from golden import compare  # noqa: E402

NO_LIMIT = (1 << 64) - 1
DENIALS = (
    "null-record",
    "copied-record",
    "null-console",
    "null-display",
    "forged-console",
    "forged-display",
    "crossed",
    "duplicate-console",
    "duplicate-display",
    "zero-console",
    "zero-display",
    "max-console",
    "max-display",
    "width",
    "height",
    "not-quiet",
    "stale-console",
    "stale-display",
    "stale-both",
    "reentry",
)


def samples(text):
    return [(1, byte, 0) for byte in text.encode("ascii")]


def cases():
    exit_tail = samples("exit\rSHOULD-NOT-BE-CONSUMED")
    yield "exit", exit_tail
    yield "editing", samples("hez\blp\r\nstatus\nx\x7fy\n\b\x7f\n") + exit_tail
    yield "commands", samples("help\nstatus\runknown\r\n\nwrite note x\ncat note\n") + exit_tail
    yield "note-replace", samples("cat note\nwrite note old suffix\ncat note\nwrite note x\ncat note\n") + exit_tail
    yield "note-empty", samples("write note old suffix\ncat note\nwrite note \ncat note\n") + exit_tail
    yield "note-edit-crlf", samples("write notf\be fixX\x7f! \r\ncat note\r\n") + exit_tail
    yield "note-malformed", samples("write note saved\nwrite notes x\nwrite note\ncat note\n") + exit_tail
    yield "note-control", samples("write note saved\nwrite note bad\x01\ncat note\n") + exit_tail
    yield (
        "note-nonascii",
        samples("write note saved\nwrite note bad") + [(1, 255, 0)] + samples("\ncat note\n") + exit_tail,
    )
    for name, damage in (("absent", (0, 0, 1)), ("byte", (1, ord("x"), 1)), ("enter", (1, 13, 1))):
        yield (
            "note-damage-" + name,
            samples("write note saved\nwrite note bad") + [damage] + samples("\ncat note\n") + exit_tail,
        )
    yield (
        "note-damaged-crlf",
        samples("write note saved\r") + [(1, 10, 1)] + samples("write note bad\ncat note\n") + exit_tail,
    )
    yield "note-maximum", samples("write note " + "Ab9 !" * 10 + "xyz" + "\ncat note\nexit\n")
    yield "note-overlong", samples("write note " + "x" * 54 + "\ncat note\nexit\n")
    yield "files-copy", samples("write a saved\ncopy a b\nwrite a x\ncat b\ncat a\ncopy b b\nexit\n!")
    yield "files-copy-full", samples("write a X\nwrite b \nwrite c \nwrite d \ncopy a e\ncopy a b\ncat b\nexit\n!")
    yield "files-copy-invalid", samples("write a x\ncopy a b c\ncopy a  b\ncopy a note\ncopy absent a\ncat a\nexit\n!")
    yield "files-demo", samples("write todo Ship Aurora\nwrite ideas Safer drivers\nls\ncat todo\nrm ideas\nexit\n!")
    yield (
        "files-capacity",
        samples("write a \nwrite b \nwrite c \nwrite d \nwrite e E\nwrite b X\nrm a\nwrite e E\nls\nexit\n!"),
    )
    yield "files-replace-empty", samples("write a old suffix\ncat a\nwrite a x\ncat a\nwrite a \ncat a\n") + exit_tail
    yield "files-missing", samples("ls\ncat a\nrm a\nwrite a x\nrm a\nls\ncat a\n") + exit_tail
    yield (
        "files-grammar",
        samples("write a x\nwrite a\ncat a x\nrm a x\nls a\nrm note\nrm .\ncat ..\ncat a\n") + exit_tail,
    )
    yield (
        "files-names",
        samples("write A._-09 y\ncat a._-09\ncat A._-09\nwrite a/b x\nwrite 123456789 x\nls\n") + exit_tail,
    )
    yield "files-maximum-content", samples("write a " + "Ab9 !" * 9 + "xyz!\ncat a\nexit\n!")
    yield "files-maximum-name", samples("write A1234567 " + "x" * 45 + "\ncat A1234567\nexit\n!")
    yield "files-overlong-content", samples("write a x\nwrite a " + "y" * 50 + "\ncat a\nexit\n!")
    yield (
        "files-rejected",
        samples("write a keep\nwrite a bad\x01\nwrite a bad")
        + [(1, 255, 0)]
        + samples("\nwrite a bad")
        + [(0, 0, 1)]
        + samples("\ncat a\n")
        + exit_tail,
    )
    # The combined limits take 83 bytes through exit, so this must exhaust the
    # unchanged 80-event budget after the successful read, before exit completes.
    yield "files-combined-budget", samples("write A1234567 " + "x" * 49 + "\ncat A1234567\nexit\n!")
    yield "capacity64", samples("x" * 64 + "\n") + exit_tail
    yield "overflow65", samples("x" * 65 + "\b\n") + exit_tail
    yield "bad-control", samples("abc") + [(1, 1, 0), (1, 255, 0)] + samples("help\n") + exit_tail
    yield "damage", [(0, 0, 1)] + samples("help\n") + [(1, ord("x"), 1), (1, 13, 1)] + exit_tail
    yield "damaged-crlf", samples("abc\r") + [(1, 10, 1)] + samples("help\n") + exit_tail
    yield "events80", samples("a" * 81)
    yield "samples96", [(0, 0, 1)] * 97
    # All printable glyphs must occur while editable, before capacity/event caps.
    for number, start in enumerate((32, 72, 112)):
        text = "".join(chr(byte) for byte in range(start, min(start + 40, 127)))
        yield f"printable-{number}", samples(text + "\n") + exit_tail


FAILURES = (
    ("failure", samples("hez\blp\nstatus\nexit\nUNCONSUMED")),
    ("note-failure", samples("write note saved\ncat note\nwrite note \ncat note\nexit\nUNCONSUMED")),
    ("files-failure", samples("write a saved\ncat a\nrm a\nls\nexit\nUNCONSUMED")),
)
RESET = (440, 146, 443, 1)


def all_cases(stores=None):
    """(name, geometry, script, fail_after, sessions, mode) rows. Output-failure cases need
    `stores`, each baseline's observed store count, and fail at its first, interior and last stores."""
    for geometry in [(440, 146, 443, 0), (800, 600, 803, 1), (1024, 768, 1024, 0)]:
        for name, script in cases():
            yield name, geometry, script, NO_LIMIT, 1, "normal"
    yield "note-reset", RESET, samples("write note secret\nexit\ncat note\nexit\n"), NO_LIMIT, 2, "normal"
    yield "files-reset", RESET, samples("write a secret\nexit\ncat a\nls\nexit\n"), NO_LIMIT, 2, "normal"
    for name, script in FAILURES:
        yield name + "-baseline", RESET, script, NO_LIMIT, 1, "normal"
        if stores is not None:
            total = stores[name + "-baseline"]
            for index in (0, 1, 53, 55, total // 2, total - 1) if name == "failure" else (total // 2, total - 1):
                yield f"{name}-{index}", RESET, script, index, 1, "normal"
    for mode in DENIALS:
        yield "denied-" + mode, RESET, [(1, 120, 0)], NO_LIMIT, 1, mode
    for geometry in ((439, 146, 443, 1), (440, 145, 443, 1)):
        yield "denied-geometry", geometry, [(1, 120, 0)], NO_LIMIT, 1, "geometry"


def run(host, rows):
    data = "".join(
        f"{' '.join(map(str, geometry))} {fail_after} {sessions} {mode} {len(script)} "
        + " ".join(f"{a} {b} {c}" for a, b, c in script)
        + "\n"
        for _, geometry, script, fail_after, sessions, mode in rows
    )
    result = subprocess.run([host], input=data.encode(), capture_output=True, timeout=300, check=False)
    if result.returncode != 0 or result.stderr:
        sys.exit(f"FAIL graphical host exit {result.returncode}: {result.stderr.decode(errors='replace')}")
    observed = result.stdout.decode().splitlines()
    if len(observed) != len(rows):
        sys.exit(f"FAIL graphical host reported {len(observed)} of {len(rows)} cases")
    return {(row[0], row[1], row[3]): line for row, line in zip(rows, observed)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("host", type=Path)
    parser.add_argument("--update", action="store_true")
    args = parser.parse_args()
    observed = run(args.host, list(all_cases()))
    stores = {}
    for name, _ in FAILURES:
        line = observed[(name + "-baseline", RESET, NO_LIMIT)]
        stores[name + "-baseline"] = int(line.split(" stores=")[1].split()[0])
    rows = list(all_cases(stores))
    observed.update(run(args.host, [row for row in rows if row[3] != NO_LIMIT]))
    lines = [f"{row[0]}\t{row[1]}\t{observed[(row[0], row[1], row[3])]}" for row in rows]
    compare(HERE / "kernel-graphical-console.golden", lines, args.update)


if __name__ == "__main__":
    main()
