#!/usr/bin/env python3
"""Create one disposable, populated fresh-profile XFS image without mounting it.

The output must not exist. Only a newly created O_EXCL regular file is formatted;
physical devices, existing images and host mount/boot configuration are untouched.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import stat
import subprocess
import tempfile

HELLO = b"Aurora reads a real XFS file through its checked block backend.\n"
PATTERN_SIZE = 9001
IMAGE_BYTES = 512 * 1024 * 1024


def pattern() -> bytes:
    """Fixture input, including NUL bytes and 504/512/4096-byte crossings."""
    return bytes((index * 37 + 11) % 256 for index in range(PATTERN_SIZE))


def create_image(destination: Path, mkfs: str = "mkfs.xfs") -> Path:
    destination = destination.absolute()
    version = subprocess.run([mkfs, "-V"], check=True, capture_output=True, text=True)
    if version.stdout.strip() != "mkfs.xfs version 6.13.0":
        raise ValueError("fresh fixture requires mkfs.xfs 6.13.0")
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError("new image is not a regular file")
        os.ftruncate(fd, IMAGE_BYTES)
        with tempfile.TemporaryDirectory(prefix="xfs-prototype-", dir=destination.parent) as temporary:
            root = Path(temporary)
            if any(character.isspace() for character in str(root)):
                raise ValueError("mkfs prototype input directory must not contain whitespace")
            (root / "hello").write_bytes(HELLO)
            (root / "pattern").write_bytes(pattern())
            prototype = root / "prototype"
            prototype.write_text(
                f"dummy\n0 0\nd--755 0 0\nhello ---644 0 0 {root / 'hello'}\npattern ---644 0 0 {root / 'pattern'}\n$\n"
            )
            # Bind mkfs to the inode we created, not a replaceable pathname.
            subprocess.run(
                [
                    mkfs,
                    "-f",
                    "-d",
                    f"file=1,name=/proc/self/fd/{fd},size=512m",
                    "-s",
                    "size=512",
                    "-m",
                    "crc=1,reflink=0,rmapbt=0,bigtime=0,inobtcount=0,uuid=5cdfd5a7-110e-4cd7-8e31-fc36b74c265f",
                    "-i",
                    "sparse=0,nrext64=0",
                    "-b",
                    "size=4096",
                    "-p",
                    str(prototype),
                ],
                check=True,
                pass_fds=(fd,),
            )
    finally:
        os.close(fd)
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path, help="new disposable regular image; never overwritten")
    parser.add_argument("--mkfs", default="mkfs.xfs", help="mkfs.xfs 6.13.0 executable")
    args = parser.parse_args()
    create_image(args.image, args.mkfs)


if __name__ == "__main__":
    main()
