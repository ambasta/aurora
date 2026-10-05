#!/usr/bin/env python3
"""Controlled local test builds and explicitly labelled compiler identity.

This is a trusted local workflow, not a compiler-correctness proof or a signed
attestation. Explicit pins and local build provenance are intentionally distinct.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time

SCHEMA = 'aurora.compiler-contract.v1'
DEFAULT_FLAGS = '-std=c++23 -O2 -Wall -Wextra -Wpedantic -Werror'
SELECTORS = ('AURORAC', 'OUT', 'PACKAGE_IDENTITY_COMPILER',
             'PACKAGE_MANIFEST_COMPILER', 'PACKAGE_GRAPH_COMPILER', 'KERNEL_BUDGET_COMPILER')
PINS = ('PACKAGE_IDENTITY_COMPILER_SHA256', 'PACKAGE_MANIFEST_COMPILER_SHA256',
        'PACKAGE_GRAPH_COMPILER_SHA256', 'KERNEL_BUDGET_COMPILER_SHA256',
        'UTF8_LINES_COMPILER_SHA256', 'UTF8_RANGE_COMPILER_SHA256', 'XFS_ROOT_COMPILER_SHA256')
TEST_FLAGS = ('PACKAGE_IDENTITY_TEST_FLAGS', 'PACKAGE_MANIFEST_TEST_FLAGS',
              'PACKAGE_GRAPH_TEST_FLAGS', 'UTF8_TEST_FLAGS', 'UTF8_LINES_TEST_FLAGS',
              'UTF8_RANGE_TEST_FLAGS', 'XFS_GEOMETRY_TEST_FLAGS', 'XFS_ROOT_TEST_FLAGS',
              'XFS_ROOT_API_TEST_FLAGS')
FORWARDED = ('CXX', 'CXXFLAGS', 'IR_TEST_CXXFLAGS', 'IR_TEST_BUILD_PREFIX',
             'UTF8_LINES_ARTIFACT_PARENT', 'UTF8_RANGE_ARTIFACT_PARENT',
             'XFS_ROOT_REPO', 'XFS_ROOT_FIXTURES', 'XFS_ROOT_ARTIFACT_PARENT',
             'PACKAGE_IDENTITY_CAP_MIB', 'PACKAGE_MANIFEST_CAP_MIB',
             'PACKAGE_GRAPH_CAP_MIB', 'KERNEL_BUDGET_CAP_MIB', 'ROUND_ROBIN_TEST_CAP_MIB', 'SANITIZE',
             'ASAN_OPTIONS', 'UBSAN_OPTIONS', *TEST_FLAGS)
CAP_CONTROLS = {'PACKAGE_IDENTITY_CAP_MIB': (128, 1024),
                'PACKAGE_MANIFEST_CAP_MIB': (256, 1024),
                'PACKAGE_GRAPH_CAP_MIB': (256, 1024),
                'KERNEL_BUDGET_CAP_MIB': (128, 1024),
                'ROUND_ROBIN_TEST_CAP_MIB': (128, 1024)}
MAKE_CONTROL = ('MAKEFLAGS', 'GNUMAKEFLAGS', 'MFLAGS', 'MAKEFILES', 'MAKEOVERRIDES',
                'MAKELEVEL', 'MAKE', 'SHELL', '.SHELLFLAGS')
SOURCE_DIRS = ('compiler', 'scripts', 'tests', 'library', 'kernel', 'fixtures',
               'storage', 'tools', 'examples', 'diagnostics', 'docs')
TOOLS = ('make', 'g++', 'as', 'ld', 'objcopy', 'objdump', 'readelf', 'nm',
         'python3', 'bash', 'rg')
OPAQUE_ENV = ('GCC_EXEC_PREFIX', 'COMPILER_PATH', 'LD_PRELOAD', 'LD_AUDIT')
BUILD_ENV = ('PATH', 'CPATH', 'CPLUS_INCLUDE_PATH', 'C_INCLUDE_PATH', 'LIBRARY_PATH',
             'LD_LIBRARY_PATH', 'SOURCE_DATE_EPOCH', 'LANG', 'LC_ALL', 'LC_CTYPE')


class ContractError(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise ContractError(message)


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b''):
            value.update(chunk)
    return value.hexdigest()


def file_record(path):
    path = Path(path).absolute()
    resolved = path.resolve(strict=True)
    st = resolved.stat()
    require(stat.S_ISREG(st.st_mode), 'regular file required: ' + str(path))
    # Resolve normal distribution compiler/header symlinks, retaining both names.
    return dict(path=str(path), resolved=str(resolved), sha256=digest(resolved),
                mode=stat.S_IMODE(st.st_mode), bytes=st.st_size, device=st.st_dev,
                inode=st.st_ino, mtime_ns=st.st_mtime_ns, ctime_ns=st.st_ctime_ns)


def check_files(records):
    for name, wanted in records.items():
        require(file_record(wanted['path']) == wanted, 'input changed: ' + name)


def source_inventory(root):
    root = Path(root).resolve(strict=True)
    paths = {root / name for name in ('.gitignore', 'AGENTS.md', 'Makefile', 'README.md')}
    for name in SOURCE_DIRS:
        directory = root / name
        if not directory.exists():
            continue
        for path in directory.rglob('*'):
            relative = path.relative_to(root)
            if '__pycache__' in relative.parts or path.suffix == '.pyc':
                continue
            if relative.parts[:2] == ('docs', 'evidence'):
                continue  # Archived receipts, not live gate inputs.
            if path.is_file():
                paths.add(path)
    # These historically frozen documents and oracle ARE live runtime inputs.
    evidence = root / 'evidence'
    if evidence.exists():
        paths.update(evidence.glob('*/contract-before-implementation.md'))
        oracle = evidence / 'package-graph/oracle/reference-v1'
        if oracle.exists():
            paths.update(path for path in oracle.rglob('*') if path.is_file())
    return {str(path.relative_to(root)): file_record(path)
            for path in sorted(paths) if path.is_file()}


def pin(value):
    require(isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) is not None,
            'expected compiler SHA256 must be 64 lowercase hexadecimal characters')
    return value


def add_identity_arguments(parser):
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--compiler-sha256', help='explicit expected compiler SHA256; no default')
    group.add_argument('--developer-build-receipt', type=Path,
                       help='checked local fresh-build receipt; not external approval')


def validate_identity_selection(args, preflight=False):
    expected = getattr(args, 'compiler_sha256', None)
    receipt = getattr(args, 'developer_build_receipt', None)
    require(not (expected is not None and receipt is not None), 'choose exactly one compiler identity mode')
    if not preflight:
        require((expected is not None) != (receipt is not None),
                'provide exactly one of --compiler-sha256 or --developer-build-receipt')
    if expected is not None:
        pin(expected)


def read_context(path, root, compiler=None, developer=False):
    path = Path(path).resolve(strict=True)
    value = json.loads(path.read_text())
    require(value.get('schema') == SCHEMA and value.get('status') == 'built', 'invalid build context')
    require(value.get('mode') in ('developer', 'acceptance'), 'invalid build context mode')
    if developer:
        require(value['mode'] == 'developer' and value.get('origin') == 'fresh-source-build',
                'developer receipt must describe a controlled fresh source build')
    require(value.get('root') == str(Path(root).resolve(strict=True)), 'receipt source root mismatch')
    require(source_inventory(root) == value.get('source_inputs'), 'source/input-set drift since build')
    require(set((*TOOLS, 'python-supervisor', 'shell', 'cxx')).issubset(value.get('tools', {})),
            'incomplete recorded host tool set')
    check_files(value['tools'])
    require(value['build_environment'] == {name: os.environ.get(name) for name in BUILD_ENV},
            'build environment differs from receipt')
    vectors = selected_flag_vectors(os.environ)
    require(isinstance(value.get('host_test_flags'), dict)
            and value['host_test_flags'] == vectors, 'host test flag vectors differ from receipt')
    selected_cxx = parse_cxx(os.environ['CXX'] if 'CXX' in os.environ else 'g++')
    require(tool_record(selected_cxx)['resolved'] == value['tools']['cxx']['resolved'],
            'current compiler selection differs from build receipt')
    output = value['compiler']
    require(file_record(output['path']) == output, 'selected compiler changed since build')
    require(os.access(output['path'], os.X_OK), 'selected compiler is not executable')
    if compiler is not None:
        require(str(Path(compiler).resolve(strict=True)) == output['resolved'], 'receipt compiler path mismatch')
    if value['origin'] == 'fresh-source-build':
        require(set('cxx-' + name for name in ('cc1plus', 'collect2', 'as', 'ld')).issubset(value['tools']),
                'incomplete bootstrap subprogram identity')
        require(value.get('build_returncode') == 0 and value.get('build_recipe') == 'gnu-cxx-main-v1',
                'missing successful controlled build')
        require(value.get('build_cwd') == str(Path(root).resolve() / 'compiler'), 'build cwd mismatch')
        require(isinstance(value.get('flags'), list) and value['flags'], 'missing exact build flags')
        require(value.get('build_command') == build_argv(value['tools']['cxx']['resolved'], value['flags'],
                                                        output['path'], value['dependency_file']),
                'build recipe/argv mismatch')
        require(vectors['CXXFLAGS'] == value['flags'], 'current compiler flags differ from build receipt')
        require(value.get('header_inputs'), 'missing compiler header dependency closure')
        check_files(value['header_inputs'])
        reject_pch(value['header_inputs'])
    else:
        require(value['mode'] == 'acceptance' and value['origin'] == 'externally-pinned-prebuilt',
                'invalid prebuilt provenance mode')
        require(file_record(value['prebuilt_input']['path']) == value['prebuilt_input'],
                'external compiler input changed')
    if value['mode'] == 'acceptance':
        require(pin(value.get('external_expected_sha256')) == output['sha256'], 'external compiler pin mismatch')
    else:
        require(value.get('external_expected_sha256') is None, 'developer receipt cannot claim an external pin')
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
        return dict(mode='developer' if self.receipt else 'explicit-pin',
                    observed_compiler_sha256=self.sha256, external_expected_sha256=self.expected,
                    developer_build_receipt=str(self.receipt) if self.receipt else None,
                    developer_build_receipt_sha256=self.receipt_hash,
                    assurance='Local identity/provenance only; no correctness or independent approval claim')

    def verify(self):
        require(digest(self.compiler) == self.sha256, 'compiler changed during gate')
        if self.receipt:
            require(digest(self.receipt) == self.receipt_hash, 'developer receipt changed during gate')
            read_context(self.receipt, self.root, self.compiler, developer=True)
        active = os.environ.get('AURORA_TEST_CONTEXT')
        if active:
            context = read_context(active, self.root, self.compiler)
            if self.receipt is not None:
                require(context['mode'] == 'developer' and Path(active).resolve() == self.receipt,
                        'developer receipt conflicts with active test context')
            if self.expected is not None:
                require(context['mode'] == 'acceptance' and context['external_expected_sha256'] == self.expected,
                        'explicit pin conflicts with active test context')


def resolve_identity(args, compiler, repo_root):
    validate_identity_selection(args)
    compiler = Path(compiler).resolve(strict=True)
    require(compiler.is_file() and os.access(compiler, os.X_OK), 'executable compiler required')
    expected = getattr(args, 'compiler_sha256', None)
    receipt = getattr(args, 'developer_build_receipt', None)
    root = Path(repo_root).resolve(strict=True)
    actual = digest(compiler)
    if receipt is not None:
        receipt = Path(receipt).resolve(strict=True)
        read_context(receipt, root, compiler, developer=True)
    else:
        require(actual == pin(expected), 'exact expected compiler SHA256 required')
    result = Identity(compiler, actual, expected, receipt, root, digest(receipt) if receipt else None)
    result.verify()
    return result


def tool_record(name):
    found = shutil.which(name)
    require(found is not None, 'required host tool unavailable: ' + name)
    return file_record(found)


class RunInterrupted(BaseException):
    def __init__(self, number):
        super().__init__('test supervisor interrupted by signal ' + str(number))
        self.number = number


@contextmanager
def interrupt_handlers():
    def interrupted(number, frame):
        # Repeated cancellation cannot interrupt owned-group cleanup/finalization.
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        raise RunInterrupted(number)
    old = {number: signal.signal(number, interrupted) for number in (signal.SIGTERM, signal.SIGINT)}
    try:
        yield
    finally:
        for number, handler in old.items():
            signal.signal(number, handler)


def stop_group(child):
    # Descendants may remain after the direct child exits. Own the session group,
    # not only the direct Popen object's liveness.
    for number in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(child.pid, number)
        except ProcessLookupError:
            break
        if number == signal.SIGTERM:
            try:
                child.wait(timeout=2)
            except subprocess.TimeoutExpired:
                pass
    child.wait()


def capture(argv, cwd, timeout=60):
    child = subprocess.Popen(argv, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             start_new_session=True)
    try:
        out, err = child.communicate(timeout=timeout)
        return subprocess.CompletedProcess(argv, child.returncode, out, err)
    except BaseException:
        stop_group(child)
        raise


def query(argv, cwd):
    result = capture(argv, cwd)
    require(result.returncode == 0, 'tool query failed: ' + shlex.join(argv) + '\n' + result.stderr.decode(errors='replace'))
    return result.stdout.decode()


def parse_flags(value, name='CXXFLAGS'):
    """Bounded data grammar whose argv survives Python, Make and shell unchanged."""
    require(isinstance(value, str) and 0 < len(value) <= 16384,
            name + ' must contain 1..16384 characters')
    require(re.fullmatch(r"[A-Za-z0-9_./,:=+ '\"-]+", value) is not None,
            name + ' contains unsupported characters; Make/shell expressions, controls and escapes are forbidden')
    try:
        flags = shlex.split(value)
    except ValueError as error:
        raise ContractError(name + ' has invalid quoting') from error
    require(0 < len(flags) <= 256 and all(len(flag) <= 1024 for flag in flags),
            name + ' must contain 1..256 arguments of at most 1024 characters')
    exact = {'-std=c++23', '-std=gnu++23', '-std=c++2b', '-std=gnu++2b',
             '-O0', '-O1', '-O2', '-O3', '-Og', '-Os', '-Oz', '-pipe', '-pthread',
             '-pedantic', '-pedantic-errors', '-fno-omit-frame-pointer',
             '-fno-optimize-sibling-calls', '-fno-sanitize-recover=all',
             '-fno-pie', '-no-pie', '-fPIE', '-fPIC', '-m64', '-mtune=generic',
             '-fstack-protector', '-fstack-protector-strong', '-fstack-protector-all',
             '-fno-stack-protector', '-fsanitize=address', '-fsanitize=undefined',
             '-fsanitize=address,undefined', '-fsanitize=undefined,address'}
    warnings = {'all', 'extra', 'pedantic', 'conversion', 'sign-conversion', 'shadow',
                'format', 'format-security', 'undef', 'cast-align', 'double-promotion',
                'null-dereference', 'old-style-cast', 'overloaded-virtual',
                'non-virtual-dtor', 'zero-as-null-pointer-constant',
                'missing-declarations', 'unused', 'unused-parameter', 'unused-variable',
                'unused-function', 'unused-result', 'deprecated-declarations',
                'maybe-uninitialized', 'uninitialized', 'switch', 'switch-enum'}
    warning_flags = {'-Werror', '-Wno-error', '-Wformat=2'}
    warning_flags.update(prefix + warning for warning in warnings
                         for prefix in ('-W', '-Wno-', '-Werror=', '-Wno-error='))
    header_options = ('-I', '-isystem', '-iquote', '-idirafter', '-include', '-imacros')
    operand_options = {'-D', '-U'}

    def operand(option, text):
        require(bool(text) and len(text) <= 1024, name + ' has an empty or oversized operand')
        if option == '-U':
            require(re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', text) is not None,
                    name + ' undefines require one identifier')
        else:
            atom = r'(?:[A-Za-z_][A-Za-z0-9_]*|[+-]?(?:0[xX][0-9A-Fa-f]+|[0-9]+)[uUlL]{0,3})'
            require(re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*(?:=' + atom + r')?', text) is not None,
                    name + ' defines require an identifier with an optional identifier/integer value')

    pending = None
    for flag in flags:
        require(not any(flag.startswith(option) for option in header_options),
                name + ' user header/search/forced-header options are unsupported; host header closure is not recorded')
        if pending is not None:
            operand(pending, flag); pending = None
            continue
        if flag in operand_options:
            pending = flag
            continue
        attached = next((option for option in ('-D', '-U')
                         if flag.startswith(option) and len(flag) > len(option)), None)
        if attached:
            operand(attached, flag[len(attached):])
            continue
        require(flag in exact or flag in warning_flags
                or re.fullmatch(r'-g(?:gdb)?[0-3]?', flag) is not None
                or re.fullmatch(r'-march=x86-64(?:-v[234])?', flag) is not None,
                name + ' has an unsupported flag or untracked input mechanism')
    require(pending is None, name + ' has a missing option operand')
    return flags


def selected_flag_vectors(env):
    build = parse_flags(env['CXXFLAGS'] if 'CXXFLAGS' in env else DEFAULT_FLAGS)
    host_ir = parse_flags(env['IR_TEST_CXXFLAGS'] if 'IR_TEST_CXXFLAGS' in env else shlex.join(build),
                          'IR_TEST_CXXFLAGS')
    return {'CXXFLAGS': build, 'IR_TEST_CXXFLAGS': host_ir}


def parse_cxx(value):
    require(isinstance(value, str) and 0 < len(value) <= 4096
            and re.fullmatch(r'[A-Za-z0-9_./+-]+', value) is not None,
            'CXX must name one simple executable path; expressions, spaces and wrappers are unsupported')
    return value


def reject_pch(headers):
    for entry in headers.values():
        for name in (entry['path'] + '.gch', entry['path'] + '.pch'):
            require(not Path(name).exists(), 'precompiled header input unsupported: ' + name)


def dependency_inputs(cxx, flags, cwd):
    data = query([cxx, *flags, '-M', '-MT', 'aurora-contract', 'main.cpp'], cwd)
    require(data.startswith('aurora-contract:'), 'unexpected dependency discovery output')
    names = shlex.split(data.split(':', 1)[1].replace('\\\n', ' '))
    require(names, 'empty dependency discovery result')
    paths = {str((cwd / name).absolute()) for name in names}
    records = {name: file_record(name) for name in sorted(paths)}
    reject_pch(records)
    return records


def build_argv(cxx, flags, output, dependencies):
    return [cxx, *flags, '-MD', '-MF', dependencies, '-MT', 'aurora-contract', 'main.cpp', '-o', output]


def actual_dependency_paths(path, cwd):
    data = Path(path).read_text()
    require(data.startswith('aurora-contract:'), 'unexpected actual dependency output')
    return {str((cwd / name).absolute())
            for name in shlex.split(data.split(':', 1)[1].replace('\\\n', ' '))}


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def execute(argv, cwd, env, log):
    """Retain and stream output; never leave the owned process group on interruption."""
    with Path(log).open('wb') as output:
        child = subprocess.Popen(argv, cwd=cwd, env=env, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, start_new_session=True)
        try:
            while True:
                data = child.stdout.read1(65536)
                if not data:
                    break
                output.write(data); output.flush()
                sys.stdout.buffer.write(data); sys.stdout.buffer.flush()
            code = child.wait()
            try:
                os.killpg(child.pid, 0)
            except ProcessLookupError:
                return code
            stop_group(child)
            raise ContractError('command left descendants running after its exit')
        except BaseException:
            stop_group(child)
            raise


def reject_make_controls(env):
    require(not env.get('MAKEFILES'), 'MAKEFILES is unsupported for supervised tests')
    # GNU Make's inherited ordinary assignments are read from the whitelisted
    # environment below. Option flags that can skip/ignore work are never allowed.
    for name in ('MAKEFLAGS', 'GNUMAKEFLAGS', 'MFLAGS'):
        text = env.get(name, '')
        require(not any(option in text for option in ('--eval', '--file', '--makefile')),
                name + ' may not select or inject Make recipes')
        words = shlex.split(text)
        for word in words:
            if '=' in word or word == '--':
                continue
            option = word.lstrip('-')
            require(not any(x in option for x in ('just-print', 'dry-run', 'question', 'touch', 'ignore-errors')),
                    name + ' contains coverage-skipping options')
            if option and not word.startswith('--') and not word[0].isdigit():
                require(not any(letter in option for letter in 'nqtif'), name + ' contains coverage-skipping options')
    if env.get('SHELL'):
        require(Path(env['SHELL']).resolve() in (Path('/bin/sh').resolve(), Path('/bin/bash').resolve()),
                'custom SHELL is unsupported for supervised tests')
    if env.get('MAKE'):
        require(Path(shutil.which(env['MAKE']) or env['MAKE']).resolve() == Path(shutil.which('make')).resolve(),
                'custom MAKE is unsupported for supervised tests')
    require(not env.get('.SHELLFLAGS'), 'custom .SHELLFLAGS is unsupported for supervised tests')


def validate_cap_controls(env):
    """Treat caps as bounded decimal data, never extra command-line options."""
    for name, (minimum, maximum) in CAP_CONTROLS.items():
        if name not in env:
            continue  # Omission retains the Make target's reviewed default.
        value = env[name]
        require(isinstance(value, str) and re.fullmatch(r'[0-9]{1,4}', value) is not None,
                name + ' must be an unsigned decimal integer with no whitespace or options')
        require(minimum <= int(value) <= maximum,
                name + ' must be between ' + str(minimum) + ' and ' + str(maximum) + ' MiB')


def prepare_controls(args, env):
    require(args.entry in ('root', 'compiler'), 'invalid Make entrypoint')
    require(re.fullmatch(r'test(?:-[a-z0-9-]+)?', args.goal) is not None, 'invalid test goal')
    reject_make_controls(env)
    validate_cap_controls(env)
    selected_flag_vectors(env)
    parse_cxx(env['CXX'] if 'CXX' in env else 'g++')
    expected = env.get('ACCEPTANCE_COMPILER_SHA256')
    mode = 'acceptance' if args.goal == 'test-acceptance' or (args.goal != 'test' and expected is not None) else 'developer'
    alias_pins = [env[name] for name in PINS if env.get(name)]
    if args.goal != 'test' and alias_pins and expected is None:
        expected = alias_pins[0]; mode = 'acceptance'
    if expected is not None:
        pin(expected)
        require(mode == 'acceptance', 'use test-acceptance for an external aggregate pin')
    require(mode != 'acceptance' or expected is not None, 'test-acceptance requires ACCEPTANCE_COMPILER_SHA256')
    require(all(pin(value) == expected for value in alias_pins), 'conflicting compiler SHA256 selectors')
    prebuilt = env.get('ACCEPTANCE_COMPILER')
    require(not prebuilt or mode == 'acceptance', 'prebuilt compiler is only valid in acceptance mode')
    if prebuilt:
        prebuilt = Path(prebuilt).resolve(strict=True)
        require(os.access(prebuilt, os.X_OK) and prebuilt.is_file(), 'prebuilt compiler must be executable')
        require(digest(prebuilt) == expected, 'prebuilt compiler does not match external expected pin')
    entry_cwd = Path(args.repo_root).resolve() / ('compiler' if args.entry == 'compiler' else '')
    if env.get('XFS_ROOT_REPO'):
        require((entry_cwd / env['XFS_ROOT_REPO']).resolve() == Path(args.repo_root).resolve(),
                'XFS_ROOT_REPO conflicts with the supervised source root')
    supplied = [name for name in SELECTORS if env.get(name)]
    if supplied:
        require(prebuilt is not None, 'Make tests own the fresh compiler path; remove compiler path overrides: ' + ', '.join(supplied))
        cwd = Path(args.repo_root).resolve() / ('compiler' if args.entry == 'compiler' else '')
        require(all((cwd / env[name]).resolve() == prebuilt for name in supplied), 'conflicting prebuilt compiler selectors')
    for name in OPAQUE_ENV:
        require(not env.get(name), 'opaque compiler/loader environment unsupported: ' + name)
    full = args.goal in ('test', 'test-acceptance')
    if full or mode == 'acceptance':
        require(not any(env.get(name) for name in TEST_FLAGS), 'full/acceptance tests reject TEST_FLAGS overrides; use an explicitly focused developer target')
        require(not env.get('IR_TEST_BUILD_PREFIX'), 'full aggregates reject opaque IR_TEST_BUILD_PREFIX overrides')
    return mode, expected, prebuilt, full


def run(args):
    root = Path(args.repo_root).resolve(strict=True)
    env = os.environ.copy()
    mode, expected, prebuilt, full = prepare_controls(args, env)  # No artifacts before this point.
    requested_cxx = parse_cxx(env['CXX'] if 'CXX' in env else 'g++')
    host_test_flags = selected_flag_vectors(env)
    flags = host_test_flags['CXXFLAGS']
    tools = {name: tool_record(name) for name in TOOLS}
    tools['python-supervisor'] = file_record(sys.executable)
    tools['shell'] = file_record('/bin/sh')
    tools['cxx'] = tool_record(requested_cxx)
    cxx = parse_cxx(tools['cxx']['resolved'])
    source = source_inventory(root)
    build_env = {name: env.get(name) for name in BUILD_ENV}
    versions = {name: query([entry['resolved'], '--version'], root).splitlines()[0]
                for name, entry in tools.items() if name not in ('shell',)}
    headers = {}
    if prebuilt is None:
        # GCC's ordinary distribution symlinks are supported; opaque wrappers are not.
        verbose = capture([cxx, '-v'], root, timeout=30)
        require(verbose.returncode == 0 and b'gcc version ' in verbose.stderr, 'controlled build requires GNU C++')
        require('linux' in query([cxx, '-dumpmachine'], root) and
                query([cxx, '-dumpmachine'], root).startswith('x86_64'), 'x86-64 Linux host compiler required')
        for name in ('cc1plus', 'collect2', 'as', 'ld'):
            selected = query([cxx, *flags, '-print-prog-name=' + name], root / 'compiler').strip()
            if '/' in selected and not Path(selected).is_absolute():
                selected = str(root / 'compiler' / selected)
            tools['cxx-' + name] = tool_record(selected)
        headers = dependency_inputs(cxx, flags, root / 'compiler')
    require(source_inventory(root) == source, 'source drift during build preflight')
    check_files(tools)
    # The lock serializes separate invocations sharing the existing kernel output.
    build = root / 'build'; build.mkdir(exist_ok=True)
    with (build / '.test-contract.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ContractError('another supervised test run owns this source tree') from error
        work = Path(tempfile.mkdtemp(prefix='test-contract-', dir=build))
        compiler = work / 'aurorac'; depfile = work / 'compiler.d'
        planned = None if prebuilt else build_argv(cxx, flags, str(compiler), str(depfile))
        original = file_record(prebuilt) if prebuilt else None
        attempt = dict(schema=SCHEMA, mode=mode, goal=args.goal, entry=args.entry,
                       root=str(root), status='running', native_complete=False,
                       origin='externally-pinned-prebuilt' if prebuilt else 'fresh-source-build',
                       external_expected_sha256=expected, started_ns=time.time_ns(),
                       source_inputs=source, tools=tools, tool_versions=versions,
                       header_inputs=headers, build_environment=build_env,
                       build_command=planned, build_cwd=str(root / 'compiler'), flags=flags,
                       host_test_flags=host_test_flags,
                       prebuilt_input=original, selected_controls={name: env.get(name) for name in FORWARDED},
                       planned_output=str(compiler))
        write_json(work / 'run.json', attempt)
        try:
            command = None
            if prebuilt is not None:
                require(file_record(prebuilt) == original, 'prebuilt compiler changed after planning')
                require(original['sha256'] == expected, 'prebuilt compiler changed before copy')
                shutil.copyfile(prebuilt, compiler)
                attempt['prebuilt_copy_sha256'] = digest(compiler)
                write_json(work / 'run.json', attempt)
                require(file_record(prebuilt) == original, 'prebuilt compiler changed during copy')
            else:
                command = planned
                code = execute(command, root / 'compiler', env, work / 'compiler.log')
                attempt['build_returncode'] = code
                write_json(work / 'run.json', attempt)
                require(code == 0, 'fresh compiler build failed with status ' + str(code))
                require(compiler.is_file() and depfile.is_file(), 'build did not produce compiler and dependency outputs')
                require(actual_dependency_paths(depfile, root / 'compiler') == set(headers), 'header dependency set changed during build')
                check_files(headers)
            require(compiler.is_file() and compiler.stat().st_size > 0, 'build did not produce a compiler')
            compiler.chmod(0o555)
            output = file_record(compiler)
            attempt['observed_compiler'] = output
            write_json(work / 'run.json', attempt)
            require(expected is None or output['sha256'] == expected, 'fresh compiler does not match external expected pin; no tests started')
            require(source_inventory(root) == source, 'source drift during compiler build')
            check_files(tools)
            context = dict(schema=SCHEMA, status='built', mode=mode, root=str(root),
                           origin='externally-pinned-prebuilt' if prebuilt else 'fresh-source-build',
                           source_inputs=source, tools=tools, tool_versions=versions,
                           build_environment=build_env, compiler=output, host_test_flags=host_test_flags,
                           external_expected_sha256=expected,
                           assurance='Trusted local workflow; not correctness, external approval or complete supply-chain proof')
            if prebuilt:
                context['prebuilt_input'] = original
            else:
                context.update(build_returncode=0, build_recipe='gnu-cxx-main-v1', flags=flags,
                               build_cwd=str(root / 'compiler'), build_command=command,
                               dependency_file=str(depfile), header_inputs=headers)
            receipt = work / 'compiler-context.json'; write_json(receipt, context); receipt.chmod(0o444)
            receipt_hash = digest(receipt)
            inner = env.copy()
            for name in (*MAKE_CONTROL, *SELECTORS, *PINS, 'ACCEPTANCE_COMPILER', 'ACCEPTANCE_COMPILER_SHA256',
                         'AURORA_TEST_CONTEXT', 'AURORA_TEST_MODE', 'AURORA_TEST_COMPILER', 'AURORA_TEST_IDENTITY_ARGS'):
                inner.pop(name, None)
            inner.update({name: value for name in FORWARDED if (value := env.get(name)) is not None})
            inner.update(CXX=cxx, CXXFLAGS=shlex.join(host_test_flags['CXXFLAGS']),
                         IR_TEST_CXXFLAGS=shlex.join(host_test_flags['IR_TEST_CXXFLAGS']),
                         PYTHONDONTWRITEBYTECODE='1',
                         AURORA_TEST_CONTEXT=str(receipt), AURORA_TEST_MODE=mode,
                         AURORA_TEST_COMPILER=str(compiler))
            inner.update({name: str(compiler) for name in SELECTORS})
            if mode == 'acceptance':
                inner['ACCEPTANCE_COMPILER_SHA256'] = expected
                inner['AURORA_TEST_IDENTITY_ARGS'] = shlex.join(['--compiler-sha256', expected])
            else:
                inner['AURORA_TEST_IDENTITY_ARGS'] = shlex.join(['--developer-build-receipt', str(receipt)])
            goal = 'test' if args.goal == 'test-acceptance' else args.goal
            argv = [tools['make']['resolved'], '--no-print-directory', '-j1', goal]
            # Preserve explicit command-line cap admission over target-specific defaults.
            argv += [name + '=' + env[name] for name in FORWARDED
                     if name.endswith('_CAP_MIB') and name in env]
            cwd = root / ('compiler' if args.entry == 'compiler' else '')
            read_context(receipt, root, compiler)
            attempt.update(origin=context['origin'], compiler_sha256=output['sha256'], context_sha256=receipt_hash,
                           make_command=argv, make_cwd=str(cwd), scope=('native-aggregate' if args.entry == 'root' else 'compiler-suite') if full else 'focused',
                           native_complete=False)
            write_json(work / 'run.json', attempt)
            code = execute(argv, cwd, inner, work / 'native.log')
            attempt['make_returncode'] = code
            require(code == 0, 'native tests failed with status ' + str(code))
            require(digest(receipt) == receipt_hash, 'compiler context changed during aggregate')
            read_context(receipt, root, compiler)
            attempt.update(status='passed', native_complete=full and args.entry == 'root',
                           coverage='complete-requested-goal' if full else 'focused-or-diagnostic',
                           limits='Native stage only; no emulator, external approval, cross-host or physical-hardware qualification')
            print('PASS ' + mode + ' ' + attempt['scope'] + ': ' + str(work), flush=True)
        except BaseException as error:
            attempt.update(status='failed', native_complete=False, error=str(error), exception_type=type(error).__name__)
            if isinstance(error, RunInterrupted):
                attempt['interrupted_by_signal'] = error.number
            raise
        finally:
            attempt['finished_ns'] = time.time_ns()
            write_json(work / 'run.json', attempt)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    launch = sub.add_parser('run')
    launch.add_argument('--repo-root', type=Path, required=True)
    launch.add_argument('--entry', choices=('root', 'compiler'), required=True)
    launch.add_argument('--goal', required=True)
    check = sub.add_parser('check')
    check.add_argument('--repo-root', type=Path, required=True)
    check.add_argument('--context', type=Path, required=True)
    args = parser.parse_args()
    try:
        with interrupt_handlers():
            dispatch(args)
    except RunInterrupted as error:
        parser.exit(128 + error.number, str(error) + '\n')
    except (ContractError, OSError, ValueError, KeyError) as error:
        parser.exit(1, 'compiler contract: ' + str(error) + '\n')


def dispatch(args):
    if args.command == 'run':
        run(args)
    else:
        value = read_context(args.context, args.repo_root, os.environ.get('AURORA_TEST_COMPILER'))
        require(os.environ.get('AURORA_TEST_MODE') == value['mode'], 'active mode/context mismatch')
        expected_args = (['--developer-build-receipt', str(args.context.resolve())]
                         if value['mode'] == 'developer' else
                         ['--compiler-sha256', value['external_expected_sha256']])
        require(shlex.split(os.environ.get('AURORA_TEST_IDENTITY_ARGS', '')) == expected_args,
                'active identity arguments conflict with context')
        if value['mode'] == 'acceptance':
            require(os.environ.get('ACCEPTANCE_COMPILER_SHA256') == value['external_expected_sha256'],
                    'active acceptance pin conflicts with context')
        else:
            require(not os.environ.get('ACCEPTANCE_COMPILER_SHA256'), 'developer context cannot supply acceptance pin')
        for name in PINS:
            require(not os.environ.get(name) or os.environ[name] == value.get('external_expected_sha256'),
                    'per-family pin conflicts with context: ' + name)
        for name in SELECTORS:
            if os.environ.get(name):
                require(str(Path(os.environ[name]).resolve()) == value['compiler']['resolved'], 'active compiler selector mismatch: ' + name)

if __name__ == '__main__':
    main()
