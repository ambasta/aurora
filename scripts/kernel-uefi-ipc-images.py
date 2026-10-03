#!/usr/bin/env python3
"""Build the two pointer-free staged IPC user programs."""
from pathlib import Path
import argparse,json,struct,subprocess
ROOT=Path(__file__).resolve().parent.parent
BASE=0x10000000000

def need(value,message):
    if not value: raise ValueError(message)

import importlib.util
_spec=importlib.util.spec_from_file_location('uefi_image_builder',ROOT/'scripts/kernel-uefi-user-images.py')
_base=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(_base)
def verify(data,blob,base,symbols):
    result=_base.verify(data,blob,base,symbols)
    need(result['probe_offset']==0,'IPC has no address literal authority')
    probe=result['probe_pc']
    if probe:
        need(base<=probe<=base+len(blob)-2 and blob[probe-base:probe-base+2]==b'\x0f\x0b','IPC exact hostile probe')
        need(probe not in [result[k] for k in ('return_pc','bounds_pc','overflow_pc','division_zero_pc','shift_count_pc')],'IPC probe aliases accepted site')
    return result

def build(compiler,out,mode):
    out.mkdir(parents=True,exist_ok=True)
    run=lambda args:subprocess.run([str(x) for x in args],cwd=ROOT,check=True)
    records={}; header=['#pragma once','#include <array>','#include <cstddef>','namespace aurora::uefi::images {']
    for index,name in enumerate(('clean','bounds')):
        prefix=out/f'user-{name}'
        run([compiler,ROOT/f'tests/kernel-programs/ipc-{"client" if index==0 else "service"}.au','--module-root',ROOT/'library','-o',prefix.with_suffix('.s')])
        run(['as','--64','-L',prefix.with_suffix('.s'),'-o',prefix.with_suffix('.o')])
        adapter=out/f'user-{name}-entry.o'
        hostile=(index==0 and mode in ('owner','stale','version','phase','site','unknown')) or (index==1 and mode=='transaction')
        flags=['--defsym',f'IPC_{mode.upper()}=1'] if hostile else []
        run(['as','--64',*flags,ROOT/'kernel/uefi/ipc-user-entry.S','-o',adapter])
        elf=prefix.with_suffix('.elf'); binary=prefix.with_suffix('.bin');base=BASE+index*4096
        run(['ld','-nostdlib','--discard-none','-T',ROOT/'kernel/program.ld','--defsym',f'USER_BASE={base}', '-z','max-page-size=0x1000',adapter,prefix.with_suffix('.o'),'-o',elf])
        run(['objcopy','-O','binary',elf,binary])
        need('There are no relocations' in subprocess.check_output(['readelf','-rW',elf],text=True),'Unresolved image relocations')
        symbols={line.split()[2]:int(line.split()[0],16) for line in subprocess.check_output(['nm','-a',elf],text=True).splitlines() if len(line.split())==3}
        blob=binary.read_bytes();meta=verify(elf.read_bytes(),blob,base,symbols);records[name]=meta
        header.append(f'inline constexpr std::array<std::byte,{len(blob)}> {name}_bytes = {{'+','.join(f'std::byte{{{value}}}' for value in blob)+'};')
        for key,value in meta.items(): header.append(f'inline constexpr unsigned long long {name}_{key}={value}ULL;')
    header.append('}')
    (out/'uefi-user-images.hpp').write_text('\n'.join(header)+'\n')
    (out/'user-images.json').write_text(json.dumps(records,indent=2)+'\n')
    print('PASS: two independently compiled staged IPC RX images')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--compiler',required=True);parser.add_argument('--output',default='build/uefi');parser.add_argument('--mode',default='normal',choices=['normal','owner','stale','version','phase','transaction','site','unknown'])
    args=parser.parse_args();build(Path(args.compiler).resolve(),Path(args.output).resolve(),args.mode)
