#!/usr/bin/env python3
"""Compiler identity selection and host flag validation for focused runners.

This is a trusted local workflow, not a compiler-correctness proof or a signed
attestation. A runner either checks an explicit compiler pin or observes the
Meson-built compiler's stability; new builds use predecessor-backed Meson.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import shlex
import shutil
import stat

DEFAULT_FLAGS = "-std=c++23 -O2 -Wall -Wextra -Wpedantic -Werror"
SELECTORS = (
    "AURORAC",
    "OUT",
    "PACKAGE_IDENTITY_COMPILER",
    "PACKAGE_MANIFEST_COMPILER",
    "PACKAGE_GRAPH_COMPILER",
    "KERNEL_BUDGET_COMPILER",
    "IPC_TRANSACTION_COMPILER",
)
PINS = (
    "PACKAGE_IDENTITY_COMPILER_SHA256",
    "PACKAGE_MANIFEST_COMPILER_SHA256",
    "PACKAGE_GRAPH_COMPILER_SHA256",
    "KERNEL_BUDGET_COMPILER_SHA256",
    "IPC_TRANSACTION_COMPILER_SHA256",
    "UTF8_LINES_COMPILER_SHA256",
    "UTF8_RANGE_COMPILER_SHA256",
    "XFS_ROOT_COMPILER_SHA256",
)
TEST_FLAGS = (
    "PACKAGE_IDENTITY_TEST_FLAGS",
    "PACKAGE_MANIFEST_TEST_FLAGS",
    "PACKAGE_GRAPH_TEST_FLAGS",
    "UTF8_TEST_FLAGS",
    "UTF8_LINES_TEST_FLAGS",
    "UTF8_RANGE_TEST_FLAGS",
    "XFS_GEOMETRY_TEST_FLAGS",
    "XFS_ROOT_TEST_FLAGS",
    "XFS_ROOT_API_TEST_FLAGS",
)
CAP_CONTROLS = {
    "PACKAGE_IDENTITY_CAP_MIB": (128, 1024),
    "PACKAGE_MANIFEST_CAP_MIB": (256, 1024),
    "PACKAGE_GRAPH_CAP_MIB": (256, 1024),
    "KERNEL_BUDGET_CAP_MIB": (128, 1024),
    "ROUND_ROBIN_TEST_CAP_MIB": (128, 1024),
    "IPC_TRANSACTION_CAP_MIB": (128, 1024),
}
MAKE_CONTROL = (
    "MAKEFLAGS",
    "GNUMAKEFLAGS",
    "MFLAGS",
    "MAKEFILES",
    "MAKEOVERRIDES",
    "MAKELEVEL",
    "MAKE",
    "SHELL",
    ".SHELLFLAGS",
)
OPAQUE_ENV = ("GCC_EXEC_PREFIX", "COMPILER_PATH", "LD_PRELOAD", "LD_AUDIT")


class ContractError(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise ContractError(message)


def digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            value.update(chunk)
    return value.hexdigest()


def file_record(path):
    path = Path(path).absolute()
    resolved = path.resolve(strict=True)
    st = resolved.stat()
    require(stat.S_ISREG(st.st_mode), "regular file required: " + str(path))
    # Resolve normal distribution compiler/header symlinks, retaining both names.
    return dict(
        path=str(path),
        resolved=str(resolved),
        sha256=digest(resolved),
        mode=stat.S_IMODE(st.st_mode),
        bytes=st.st_size,
        device=st.st_dev,
        inode=st.st_ino,
        mtime_ns=st.st_mtime_ns,
        ctime_ns=st.st_ctime_ns,
    )


def pin(value):
    require(
        isinstance(value, str) and re.fullmatch("[0-9a-f]{64}", value) is not None,
        "expected compiler SHA256 must be 64 lowercase hexadecimal characters",
    )
    return value


def add_identity_arguments(parser):
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--compiler-sha256", help="explicit expected compiler SHA256; no default")
    group.add_argument(
        "--meson-selected-compiler",
        action="store_true",
        help="observe the Meson-built artifact; no external pin or fresh-build claim",
    )


def validate_identity_selection(args, preflight=False):
    expected = getattr(args, "compiler_sha256", None)
    selected = getattr(args, "meson_selected_compiler", False)
    count = int(expected is not None) + int(selected)
    require(count <= 1, "choose exactly one compiler identity mode")
    if not preflight:
        require(count == 1, "provide one of --compiler-sha256 or --meson-selected-compiler")
    if expected is not None:
        pin(expected)


@dataclass
class Identity:
    compiler: Path
    sha256: str
    expected: str
    root: Path

    def record(self):
        return dict(
            mode="explicit-pin",
            observed_compiler_sha256=self.sha256,
            external_expected_sha256=self.expected,
            assurance="Local identity/provenance only; no correctness or independent approval claim",
        )

    def verify(self):
        require(digest(self.compiler) == self.sha256, "compiler changed during gate")


@dataclass
class MesonIdentity:
    """Artifact stability, not a historical pin or a controlled fresh build."""

    compiler: Path
    root: Path
    before: dict
    expected: None = None

    @property
    def sha256(self):
        return self.before["sha256"]

    def verify(self):
        require(file_record(self.compiler) == self.before, "Meson compiler changed during gate")

    def record(self):
        return dict(
            mode="meson-selected",
            origin="meson-selected-artifact",
            observed_compiler_sha256=self.sha256,
            external_expected_sha256=None,
            compiler_before=self.before,
            assurance="Observed artifact stability; aggregate source/build qualification is separate",
        )


def resolve_identity(args, compiler, repo_root):
    validate_identity_selection(args)
    compiler = Path(compiler).resolve(strict=True)
    require(compiler.is_file() and os.access(compiler, os.X_OK), "executable compiler required")
    root = Path(repo_root).resolve(strict=True)
    if getattr(args, "meson_selected_compiler", False):
        result = MesonIdentity(compiler, root, file_record(compiler))
    else:
        expected = pin(getattr(args, "compiler_sha256", None))
        actual = digest(compiler)
        require(actual == expected, "exact expected compiler SHA256 required")
        result = Identity(compiler, actual, expected, root)
    result.verify()
    return result


def tool_record(name):
    found = shutil.which(name)
    require(found is not None, "required host tool unavailable: " + name)
    return file_record(found)


def parse_flags(value, name="CXXFLAGS"):
    """Split one flag string as data; the argv reaches Meson and runners unchanged."""
    require(isinstance(value, str) and 0 < len(value) <= 16384, name + " must contain 1..16384 characters")
    require(
        not any(character in value for character in "$`\n\r\0"),
        name + " must not contain shell or Make expansions or line breaks",
    )
    try:
        flags = shlex.split(value)
    except ValueError as error:
        raise ContractError(name + " has invalid quoting") from error
    require(bool(flags), name + " must contain at least one flag")
    return flags


def selected_flag_vectors(env):
    build = parse_flags(env["CXXFLAGS"] if "CXXFLAGS" in env else DEFAULT_FLAGS)
    host_ir = parse_flags(
        env["IR_TEST_CXXFLAGS"] if "IR_TEST_CXXFLAGS" in env else shlex.join(build), "IR_TEST_CXXFLAGS"
    )
    return {"CXXFLAGS": build, "IR_TEST_CXXFLAGS": host_ir}


def parse_cxx(value):
    require(
        isinstance(value, str) and 0 < len(value) <= 4096 and re.fullmatch(r"[A-Za-z0-9_./+-]+", value) is not None,
        "CXX must name one simple executable path; expressions, spaces and wrappers are unsupported",
    )
    return value
