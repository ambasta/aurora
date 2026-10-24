#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONDONTWRITEBYTECODE=1
if [[ "${1:-}" == --images ]]; then
    [[ $# == 3 ]] || { echo 'Expected --images NORMAL_DIR SPAN_DIR' >&2; exit 2; }
    normal_dir="$2"
    span_dir="$3"
else
    if [[ -n "${1:-}" ]]; then export AURORAC="$1"; fi
    normal_dir=$(python3 -B scripts/meson_test.py --kernel uefi --profile runtime --print-image-dir)
    span_dir=$(python3 -B scripts/meson_test.py --kernel uefi --profile runtime-span --print-image-dir)
    export AURORAC="$(python3 -B - "$normal_dir" <<'COMPILER'
from pathlib import Path
import sys
sys.path.insert(0, 'scripts')
from meson_test import selected_kernel_compiler
print(selected_kernel_compiler(Path(sys.argv[1]).parents[2]))
COMPILER
)"
fi
python3 -O - "${AURORAC:?native span gate requires a selected compiler}" "$normal_dir" "$span_dir" <<'PY'
from enum import Enum
import json
from pathlib import Path
import sys
import tempfile

root = Path.cwd()
sys.path.insert(0, str(root / 'tests/compiler'))
from unsigned_oracle import (Case, NativeRunner, command, require,
                             validate_trap, validate_values)

class Trap(Enum):
    BOUNDS = '.Laurora_bounds_trap'

compiler = Path(sys.argv[1]).resolve()
normal_dir, span_dir = (Path(value).resolve(strict=True) for value in sys.argv[2:])
with tempfile.TemporaryDirectory(prefix='aurora-uefi-span-') as temporary:
    output = Path(temporary)
    span = json.loads((span_dir / 'user-images.json').read_text())
    native = output / 'native'
    native.mkdir()
    runner = NativeRunner(native, compiler, 5)
    observed, _ = runner.assemble((span_dir / 'user-clean.s').read_text(), ['aurora_user_main'])
    validate_values(observed, [Case('span-clean', '', 42, 'i64')])
    observed, native_symbols = runner.assemble((span_dir / 'user-bounds.s').read_text(), ['aurora_user_main'])
    validate_trap(observed, Trap.BOUNDS, native_symbols, 'unchanged bounds fixture')
    source = (root / 'tests/kernel-programs/span-clean.au').read_text()
    require(source.count('view.at(0)') == 1, 'span bounds mutation is ambiguous')
    for index in (-1, 1):
        fixture = native / 'span-bounds.au'
        assembly = native / 'span-bounds.s'
        fixture.write_text(source.replace('view.at(0)', f'view.at({index})'))
        command([compiler, fixture, '--module-root', root / 'library', '-o', assembly])
        observed, native_symbols = runner.assemble(assembly.read_text(), ['aurora_user_main'])
        validate_trap(observed, Trap.BOUNDS, native_symbols, f'span bounds {index}')
    print(f"PASS: UEFI span image {span['clean']['size']} bytes; native return 42 and 3 exact bounds traps")
PY
