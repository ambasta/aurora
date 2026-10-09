#!/usr/bin/env python3
"""Keep the assembly-only UEFI memory helper's unresolved/relocation contract."""
import os
import subprocess
import sys

obj = sys.argv[1]
if subprocess.check_output(['nm', '-u', obj]).strip():
    raise RuntimeError('UEFI memory object has unresolved helpers')
relocations = subprocess.check_output(['readelf', '-rW', obj], env=dict(os.environ, LC_ALL='C'), text=True)
if 'There are no relocations in this file.' not in relocations:
    raise RuntimeError('UEFI memory object has relocations')
print(relocations, end='')
