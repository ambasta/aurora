#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONDONTWRITEBYTECODE=1
python3 -O tests/kernel-uefi-user-image.py
python3 -O tests/kernel-uefi-runtime-smoke.py --self-test
python3 -O - "${1:-${AURORAC:-build/aurorac}}" <<'PY'
from enum import Enum
import importlib.util
import json
from pathlib import Path
import struct
import sys
import tempfile

root = Path.cwd()
sys.path.insert(0, str(root / 'tests/compiler'))
from unsigned_oracle import (Case, NativeRunner, command, require,
                             validate_trap, validate_values)

spec = importlib.util.spec_from_file_location('images', root / 'scripts/kernel-uefi-user-images.py')
images = importlib.util.module_from_spec(spec)
spec.loader.exec_module(images)

class Trap(Enum):
    BOUNDS = '.Laurora_bounds_trap'

compiler = Path(sys.argv[1]).resolve()
keys = {'entry', 'size', 'return_pc', 'bounds_pc', 'overflow_pc',
        'division_zero_pc', 'shift_count_pc', 'probe_offset', 'probe_pc'}
with tempfile.TemporaryDirectory(prefix='aurora-uefi-span-') as temporary:
    output = Path(temporary)
    for mode in ('normal', 'span'):
        command([sys.executable, root / 'scripts/kernel-uefi-user-images.py',
                 '--compiler', compiler, '--output', output / mode, '--mode', mode], timeout=30)
    normal = json.loads((output / 'normal/user-images.json').read_text())
    span = json.loads((output / 'span/user-images.json').read_text())
    require(set(normal) == set(span) == {'clean', 'bounds'}, 'image set changed')
    for index, name in enumerate(('clean', 'bounds')):
        for metadata in (normal, span):
            image = metadata[name]
            require(set(image) == keys and image['entry'] == images.BASE + index * 4096
                    and 4 <= image['size'] <= 4096 and image['probe_pc'] == image['probe_offset'] == 0,
                    'runtime span widened image layout or probe authority')
        require((output / f'normal/objects/user-{name}-entry.o').read_bytes()
                == (output / f'span/objects/user-{name}-entry.o').read_bytes(), 'normal adapter changed')
    require(normal['bounds'] == span['bounds'], 'bounds metadata changed')
    for suffix in ('s', 'o', 'elf', 'bin'):
        name = ('objects/' if suffix == 'o' else '') + f'user-bounds.{suffix}'
        require((output / 'normal' / name).read_bytes()
                == (output / 'span' / name).read_bytes(), 'bounds fixture changed')

    elf = (output / 'span/user-clean.elf').read_bytes()
    blob = (output / 'span/user-clean.bin').read_bytes()
    symbols = {fields[2]: int(fields[0], 16)
               for line in command(['nm', '-a', output / 'span/user-clean.elf']).stdout.decode().splitlines()
               if len(fields := line.split()) == 3}
    helpers = [name for name in symbols if name.endswith('read_clean_byte')]
    require(len(helpers) == 1, 'span helper missing from compiled image')
    require('call ' + helpers[0] in (output / 'span/user-clean.s').read_text(),
            'span helper not called by fixture')
    require(images.verify(elf, blob, images.BASE, symbols) == span['clean'],
            'stored metadata differs from generated span image')
    invalid = []
    for value in (0, symbols['aurora_program_return_pc'], images.BASE + 4096):
        changed = symbols.copy()
        changed['.Laurora_bounds_trap'] = value
        invalid.append((elf, blob, images.BASE, changed))
    changed_elf = bytearray(elf)
    phoff = struct.unpack_from('<Q', elf, 32)[0]
    struct.pack_into('<I', changed_elf, phoff + 4, 7)
    invalid.append((changed_elf, blob, images.BASE, symbols))
    changed_blob = bytearray(blob)
    changed_blob[symbols['.Laurora_bounds_trap'] - images.BASE] = 0x90
    changed_elf = bytearray(elf)
    file_offset = struct.unpack_from('<Q', elf, phoff + 8)[0]
    changed_elf[file_offset:file_offset + len(blob)] = changed_blob
    invalid.append((changed_elf, changed_blob, images.BASE, symbols))
    invalid.append((elf, blob, images.BASE + 8192, symbols))
    for arguments in invalid:
        try:
            images.verify(*arguments)
        except ValueError:
            pass
        else:
            raise AssertionError('invalid span image authority accepted')

    native = output / 'native'
    native.mkdir()
    runner = NativeRunner(native, compiler, 5)
    observed, _ = runner.assemble((output / 'span/user-clean.s').read_text(), ['aurora_user_main'])
    validate_values(observed, [Case('span-clean', '', 42, 'i64')])
    observed, native_symbols = runner.assemble((output / 'span/user-bounds.s').read_text(), ['aurora_user_main'])
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
    print(f"PASS: UEFI span image {span['clean']['size']} bytes; unchanged bounds/normal adapters; "
          f"{len(invalid)} image authority rejections; native return 42 and 3 exact bounds traps")
PY
