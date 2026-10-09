#!/usr/bin/env python3
"""Thin Make convenience entrypoint; Meson/Ninja owns the incremental native graph."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import shlex

import meson_toolchain

import compiler_contract as contract


def execute(root, scope):
    root = root.resolve(strict=True)
    env = os.environ.copy()
    # Preserve rejecting public controls. This does not build a fresh compiler,
    # produce a qualification receipt, select a historical pin or run old Make.
    controls = argparse.Namespace(goal='test', entry='root', repo_root=root)
    mode, _, _, _ = contract.prepare_controls(controls, env)
    contract.require(mode == 'developer' and not env.get('AURORA_TEST_CONTEXT'),
                     'Use test-acceptance for the separately pinned legacy workflow')
    contract.require(not any(env.get(name) for name in (*contract.CAP_CONTROLS, 'IR_TEST_CXXFLAGS')),
                     'Canonical Meson uses registered full caps and fixture flags; remove legacy overrides')
    contract.require(not env.get('SANITIZE') or env['SANITIZE'] == '0',
                     'SANITIZE cannot configure fixed Meson targets; use a separate explicit sanitizer build/gate')
    contract.require(not env.get('CPPFLAGS') and not env.get('LDFLAGS'),
                     'Configure nondefault CPPFLAGS/LDFLAGS directly in a separate Meson build')
    cxx = contract.tool_record(contract.parse_cxx(env.get('CXX', 'g++')))
    gcc = contract.tool_record('gcc')
    contract.require(contract.query([gcc['resolved'], '-dumpfullversion'], root).strip() ==
                     contract.query([cxx['resolved'], '-dumpfullversion'], root).strip(),
                     'Select matching gcc and CXX toolchain versions on PATH')
    host_identity = meson_toolchain.snapshot([cxx['resolved']])
    config = dict(toolchain=host_identity, cpp_flags=env.get('CXXFLAGS', ''))
    key = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()[:16]
    # A supplied directory is configured explicitly with direct meson setup;
    # otherwise a stable compiler/configuration-specific directory is selected.
    supplied = env.get('MESON_BUILD_DIR')
    build = Path(supplied) if supplied else root / 'build' / ('meson-' + key)
    build = (root / build).resolve() if not build.is_absolute() else build.resolve()
    build_jobs = int(env.get('AURORA_BUILD_JOBS', '3'))
    test_jobs = int(env.get('AURORA_TEST_JOBS', '4'))
    contract.require(1 <= build_jobs <= 64 and 1 <= test_jobs <= 64,
                     'AURORA_BUILD_JOBS and AURORA_TEST_JOBS must be between 1 and 64')
    for name in contract.MAKE_CONTROL:
        env.pop(name, None)
    env['CXX'] = cxx['resolved']
    if supplied:
        contract.require((build / 'build.ninja').is_file(),
                         'Configure MESON_BUILD_DIR first with meson setup and the selected toolchain')
    build.mkdir(parents=True, exist_ok=True)
    with (build / '.aurora-test.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if not (build / 'build.ninja').exists():
            subprocess.run(['meson', 'setup', str(build), str(root), '--backend=ninja', '-Dlsp=false'],
                           cwd=root, env=env, check=True)
        configured = json.loads(subprocess.check_output(
            ['meson', 'introspect', str(build), '--compilers'], cwd=root, env=env))
        command = configured['build']['cpp']['exelist']
        contract.require(len(command) == 1 and contract.tool_record(command[0])['sha256'] == cxx['sha256'],
                         'Configured compiler differs from CXX; select the matching build directory')
        options = json.loads(subprocess.check_output(
            ['meson', 'introspect', str(build), '--buildoptions'], cwd=root, env=env))
        cpp_args = next(item['value'] for item in options if item['name'] == 'cpp_args')
        contract.require(cpp_args == shlex.split(env.get('CXXFLAGS', '')),
                         'Configured cpp_args differ from CXXFLAGS; select matching flags/build directory')
        meson_toolchain.verify(json.loads((build / 'aurora-toolchain.json').read_text()),
                               meson_toolchain.snapshot(command))
        subprocess.run(['meson', 'compile', '-C', str(build), '-j', str(build_jobs)],
                       cwd=root, env=env, check=True)
        subprocess.run(['meson', 'test', '-C', str(build), '--suite', scope, '--no-rebuild',
                        '--num-processes', str(test_jobs), '--print-errorlogs'],
                       cwd=root, env=env, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo-root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--suite', choices=['full', 'compiler', 'dev', 'slow', 'integration', 'boot'], default='full')
    args = parser.parse_args()
    execute(args.repo_root, args.suite)


if __name__ == '__main__':
    try:
        main()
    except (contract.ContractError, subprocess.CalledProcessError, BlockingIOError, ValueError) as error:
        raise SystemExit(str(error))
