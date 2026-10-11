#!/usr/bin/env python3
"""Compiler identity validators and historical local build-receipt readers.

This is a trusted local workflow, not a compiler-correctness proof or a signed
attestation. Explicit pins and local build provenance are intentionally distinct.
The gnu-cxx-main-v1 executor is retired. Its receipt schema and exact argv remain
readable for historical validation; new builds use predecessor-backed Meson.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import stat

SCHEMA = "aurora.compiler-contract.v1"
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
SOURCE_DIRS = (
    "compiler",
    "runtime",
    "scripts",
    "tests",
    "library",
    "kernel",
    "fixtures",
    "storage",
    "tools",
    "examples",
    "diagnostics",
    "docs",
)
TOOLS = ("make", "g++", "as", "ld", "objcopy", "objdump", "readelf", "nm", "python3", "bash", "rg")
OPAQUE_ENV = ("GCC_EXEC_PREFIX", "COMPILER_PATH", "LD_PRELOAD", "LD_AUDIT")
BUILD_ENV = (
    "PATH",
    "CPATH",
    "CPLUS_INCLUDE_PATH",
    "C_INCLUDE_PATH",
    "LIBRARY_PATH",
    "LD_LIBRARY_PATH",
    "SOURCE_DATE_EPOCH",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
)


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


def check_files(records):
    for name, wanted in records.items():
        require(file_record(wanted["path"]) == wanted, "input changed: " + name)


def source_inventory(root):
    root = Path(root).resolve(strict=True)
    paths = {
        root / name for name in (".gitignore", "AGENTS.md", "Makefile", "README.md", "meson.build", "meson_options.txt")
    }
    for name in SOURCE_DIRS:
        directory = root / name
        if not directory.exists():
            continue
        for path in directory.rglob("*"):
            relative = path.relative_to(root)
            if "__pycache__" in relative.parts or path.suffix == ".pyc":
                continue
            if relative.parts[:2] == ("docs", "evidence"):
                continue  # Archived receipts, not live gate inputs.
            if path.is_file():
                paths.add(path)
    # The independent graph reference remains a live test-oracle input.
    evidence = root / "evidence"
    if evidence.exists():
        oracle = evidence / "package-graph/oracle/reference-v1"
        if oracle.exists():
            paths.update(path for path in oracle.rglob("*") if path.is_file())
    return {str(path.relative_to(root)): file_record(path) for path in sorted(paths) if path.is_file()}


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
        "--developer-build-receipt", type=Path, help="checked local fresh-build receipt; not external approval"
    )
    group.add_argument(
        "--meson-selected-compiler",
        action="store_true",
        help="observe the Meson-built artifact; no external pin or fresh-build claim",
    )


def validate_identity_selection(args, preflight=False):
    expected = getattr(args, "compiler_sha256", None)
    receipt = getattr(args, "developer_build_receipt", None)
    selected = getattr(args, "meson_selected_compiler", False)
    count = int(expected is not None) + int(receipt is not None) + int(selected)
    require(count <= 1, "choose exactly one compiler identity mode")
    if not preflight:
        require(count == 1, "provide one of --compiler-sha256, --developer-build-receipt, or --meson-selected-compiler")
    if expected is not None:
        pin(expected)


def read_context(path, root, compiler=None, developer=False):
    path = Path(path).resolve(strict=True)
    value = json.loads(path.read_text())
    require(value.get("schema") == SCHEMA and value.get("status") == "built", "invalid build context")
    require(value.get("mode") in ("developer", "acceptance"), "invalid build context mode")
    if developer:
        require(
            value["mode"] == "developer" and value.get("origin") == "fresh-source-build",
            "developer receipt must describe a controlled fresh source build",
        )
    require(value.get("root") == str(Path(root).resolve(strict=True)), "receipt source root mismatch")
    require(source_inventory(root) == value.get("source_inputs"), "source/input-set drift since build")
    require(
        set((*TOOLS, "python-supervisor", "shell", "cxx")).issubset(value.get("tools", {})),
        "incomplete recorded host tool set",
    )
    check_files(value["tools"])
    require(
        value["build_environment"] == {name: os.environ.get(name) for name in BUILD_ENV},
        "build environment differs from receipt",
    )
    vectors = selected_flag_vectors(os.environ)
    require(
        isinstance(value.get("host_test_flags"), dict) and value["host_test_flags"] == vectors,
        "host test flag vectors differ from receipt",
    )
    selected_cxx = parse_cxx(os.environ["CXX"] if "CXX" in os.environ else "g++")
    require(
        tool_record(selected_cxx)["resolved"] == value["tools"]["cxx"]["resolved"],
        "current compiler selection differs from build receipt",
    )
    output = value["compiler"]
    require(file_record(output["path"]) == output, "selected compiler changed since build")
    require(os.access(output["path"], os.X_OK), "selected compiler is not executable")
    if compiler is not None:
        require(str(Path(compiler).resolve(strict=True)) == output["resolved"], "receipt compiler path mismatch")
    if value["origin"] == "fresh-source-build":
        require(
            set("cxx-" + name for name in ("cc1plus", "collect2", "as", "ld")).issubset(value["tools"]),
            "incomplete bootstrap subprogram identity",
        )
        require(
            value.get("build_returncode") == 0 and value.get("build_recipe") == "gnu-cxx-main-v1",
            "missing successful controlled build",
        )
        require(value.get("build_cwd") == str(Path(root).resolve() / "compiler"), "build cwd mismatch")
        require(isinstance(value.get("flags"), list) and value["flags"], "missing exact build flags")
        require(
            value.get("build_command")
            == build_argv(value["tools"]["cxx"]["resolved"], value["flags"], output["path"], value["dependency_file"]),
            "build recipe/argv mismatch",
        )
        require(vectors["CXXFLAGS"] == value["flags"], "current compiler flags differ from build receipt")
        require(value.get("header_inputs"), "missing compiler header dependency closure")
        check_files(value["header_inputs"])
        reject_pch(value["header_inputs"])
    else:
        require(
            value["mode"] == "acceptance" and value["origin"] == "externally-pinned-prebuilt",
            "invalid prebuilt provenance mode",
        )
        require(
            file_record(value["prebuilt_input"]["path"]) == value["prebuilt_input"], "external compiler input changed"
        )
    if value["mode"] == "acceptance":
        require(pin(value.get("external_expected_sha256")) == output["sha256"], "external compiler pin mismatch")
    else:
        require(value.get("external_expected_sha256") is None, "developer receipt cannot claim an external pin")
    return value


@dataclass
class Identity:
    compiler: Path
    sha256: str
    expected: str | None
    receipt: Path | None
    root: Path
    receipt_hash: str | None

    def record(self):
        return dict(
            mode="developer" if self.receipt else "explicit-pin",
            observed_compiler_sha256=self.sha256,
            external_expected_sha256=self.expected,
            developer_build_receipt=str(self.receipt) if self.receipt else None,
            developer_build_receipt_sha256=self.receipt_hash,
            assurance="Local identity/provenance only; no correctness or independent approval claim",
        )

    def verify(self):
        require(digest(self.compiler) == self.sha256, "compiler changed during gate")
        if self.receipt:
            require(digest(self.receipt) == self.receipt_hash, "developer receipt changed during gate")
            read_context(self.receipt, self.root, self.compiler, developer=True)


@dataclass
class MesonIdentity:
    """Artifact stability, not a historical pin or a controlled fresh build."""

    compiler: Path
    root: Path
    before: dict
    expected: None = None
    receipt: None = None
    receipt_hash: None = None

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
    expected = getattr(args, "compiler_sha256", None)
    receipt = getattr(args, "developer_build_receipt", None)
    root = Path(repo_root).resolve(strict=True)
    actual = digest(compiler)
    if getattr(args, "meson_selected_compiler", False):
        result = MesonIdentity(compiler, root, file_record(compiler))
        result.verify()
        return result
    if receipt is not None:
        receipt = Path(receipt).resolve(strict=True)
        read_context(receipt, root, compiler, developer=True)
    else:
        require(actual == pin(expected), "exact expected compiler SHA256 required")
    result = Identity(compiler, actual, expected, receipt, root, digest(receipt) if receipt else None)
    result.verify()
    return result


def tool_record(name):
    found = shutil.which(name)
    require(found is not None, "required host tool unavailable: " + name)
    return file_record(found)


def parse_flags(value, name="CXXFLAGS"):
    """Bounded data grammar whose argv survives Python, Make and shell unchanged."""
    require(isinstance(value, str) and 0 < len(value) <= 16384, name + " must contain 1..16384 characters")
    require(
        re.fullmatch(r"[A-Za-z0-9_./,:=+ '\"-]+", value) is not None,
        name + " contains unsupported characters; Make/shell expressions, controls and escapes are forbidden",
    )
    try:
        flags = shlex.split(value)
    except ValueError as error:
        raise ContractError(name + " has invalid quoting") from error
    require(
        0 < len(flags) <= 256 and all(len(flag) <= 1024 for flag in flags),
        name + " must contain 1..256 arguments of at most 1024 characters",
    )
    exact = {
        "-std=c++23",
        "-std=gnu++23",
        "-std=c++2b",
        "-std=gnu++2b",
        "-O0",
        "-O1",
        "-O2",
        "-O3",
        "-Og",
        "-Os",
        "-Oz",
        "-pipe",
        "-pthread",
        "-pedantic",
        "-pedantic-errors",
        "-fno-omit-frame-pointer",
        "-fno-optimize-sibling-calls",
        "-fno-sanitize-recover=all",
        "-fno-pie",
        "-no-pie",
        "-fPIE",
        "-fPIC",
        "-m64",
        "-mtune=generic",
        "-fstack-protector",
        "-fstack-protector-strong",
        "-fstack-protector-all",
        "-fno-stack-protector",
        "-fsanitize=address",
        "-fsanitize=undefined",
        "-fsanitize=address,undefined",
        "-fsanitize=undefined,address",
    }
    warnings = {
        "all",
        "extra",
        "pedantic",
        "conversion",
        "sign-conversion",
        "shadow",
        "format",
        "format-security",
        "undef",
        "cast-align",
        "double-promotion",
        "null-dereference",
        "old-style-cast",
        "overloaded-virtual",
        "non-virtual-dtor",
        "zero-as-null-pointer-constant",
        "missing-declarations",
        "unused",
        "unused-parameter",
        "unused-variable",
        "unused-function",
        "unused-result",
        "deprecated-declarations",
        "maybe-uninitialized",
        "uninitialized",
        "switch",
        "switch-enum",
    }
    warning_flags = {"-Werror", "-Wno-error", "-Wformat=2"}
    warning_flags.update(
        prefix + warning for warning in warnings for prefix in ("-W", "-Wno-", "-Werror=", "-Wno-error=")
    )
    header_options = ("-I", "-isystem", "-iquote", "-idirafter", "-include", "-imacros")
    operand_options = {"-D", "-U"}

    def operand(option, text):
        require(bool(text) and len(text) <= 1024, name + " has an empty or oversized operand")
        if option == "-U":
            require(
                re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", text) is not None, name + " undefines require one identifier"
            )
        else:
            atom = r"(?:[A-Za-z_][A-Za-z0-9_]*|[+-]?(?:0[xX][0-9A-Fa-f]+|[0-9]+)[uUlL]{0,3})"
            require(
                re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(?:=" + atom + r")?", text) is not None,
                name + " defines require an identifier with an optional identifier/integer value",
            )

    pending = None
    for flag in flags:
        require(
            not any(flag.startswith(option) for option in header_options),
            name + " user header/search/forced-header options are unsupported; host header closure is not recorded",
        )
        if pending is not None:
            operand(pending, flag)
            pending = None
            continue
        if flag in operand_options:
            pending = flag
            continue
        attached = next(
            (option for option in ("-D", "-U") if flag.startswith(option) and len(flag) > len(option)), None
        )
        if attached:
            operand(attached, flag[len(attached) :])
            continue
        require(
            flag in exact
            or flag in warning_flags
            or re.fullmatch(r"-g(?:gdb)?[0-3]?", flag) is not None
            or re.fullmatch(r"-march=x86-64(?:-v[234])?", flag) is not None,
            name + " has an unsupported flag or untracked input mechanism",
        )
    require(pending is None, name + " has a missing option operand")
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


def reject_pch(headers):
    for entry in headers.values():
        for name in (entry["path"] + ".gch", entry["path"] + ".pch"):
            require(not Path(name).exists(), "precompiled header input unsupported: " + name)


def build_argv(cxx, flags, output, dependencies):
    """Historical gnu-cxx-main-v1 receipt comparison only; never executed here."""
    return [cxx, *flags, "-MD", "-MF", dependencies, "-MT", "aurora-contract", "main.cpp", "-o", output]
