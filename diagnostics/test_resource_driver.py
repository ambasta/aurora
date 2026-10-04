#!/usr/bin/env python3
"""Ensure resource measurements cannot pass on compiler failure or wrong output."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('baseline', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    directory = args.output.resolve()
    directory.mkdir(exist_ok=False)
    driver = Path(__file__).with_name('compare_readonly_resources.py').resolve()
    wrong = directory / 'wrong-output-compiler.py'
    wrong.write_text('#!' + sys.executable + '\nimport pathlib,sys\n'
                     'output=pathlib.Path(sys.argv[sys.argv.index("-o")+1])\n'
                     'output.write_text(".text\\n.globl test\\ntest:\\n movq $43,%rax\\n ret\\n'
                     '.section .note.GNU-stack,\\"\\",@progbits\\n")\n')
    wrong.chmod(0o700)
    results = []
    for name, compiler, diagnostic in [
        ('always-fail', Path('/bin/false'), 'candidate failed valid readonly corpus'),
        ('wrong-output', wrong, 'candidate native result is not exact u64 42')]:
        output = directory / name
        command = [sys.executable, '-O', str(driver), str(args.baseline.resolve()),
                   str(compiler), str(output)]
        result = subprocess.run(command, capture_output=True, timeout=30)
        receipt = json.loads((output / 'results.json').read_text())
        results.append(dict(name=name, command=command, returncode=result.returncode,
                            stdout_hex=result.stdout.hex(), stderr_hex=result.stderr.hex(),
                            observed=receipt))
        (directory / 'controls.json').write_text(json.dumps(results, indent=2) + '\n')
        require(result.returncode == 1, name + ': driver did not reject normally')
        require(diagnostic.encode() in result.stderr, name + ': wrong failure reason')
        require(b'PASS bounded measurements' not in result.stdout, name + ': false PASS')
        require(len(receipt['results']) == 1, name + ': missing exact failing-case receipt')
        observed = receipt['results'][0]
        if name == 'always-fail':
            require(observed['candidate']['exit_code'] == 1, 'lost compiler failure')
            require(observed['candidate']['assembly_sha256'] is None, 'unexpected assembly')
        else:
            require(observed['candidate']['exit_code'] == 0, 'wrong stub failed before native result')
            require(observed['native'][-1]['stdout_hex'] == (43).to_bytes(8, 'little').hex(),
                    'wrong native result not retained')
        print('PASS resource-driver control', name, flush=True)
    (directory / 'provenance.json').write_text(json.dumps({
        'driver_sha256': hashlib.sha256(driver.read_bytes()).hexdigest(),
        'control_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'baseline_sha256': hashlib.sha256(args.baseline.read_bytes()).hexdigest(),
        'wrong_output_stub_sha256': hashlib.sha256(wrong.read_bytes()).hexdigest(),
        'python_optimized': not __debug__}, indent=2) + '\n')


if __name__ == '__main__':
    main()
