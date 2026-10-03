#!/usr/bin/env python3
"""Build bounded Aurora images for UEFI's independent high virtual layout."""
from pathlib import Path
import argparse,json,struct,subprocess
ROOT=Path(__file__).resolve().parent.parent
BASE=0x10000000000

def need(value,message):
    if not value: raise ValueError(message)

def verify(data,blob,base,symbols,*,image_count=2):
    need(len(data)>=64,'Truncated ELF header')
    need(type(image_count) is int and image_count in (2,3),'Unknown bounded image profile')
    need(base in tuple(BASE+index*4096 for index in range(image_count)),'Foreign virtual image layout')
    need(data[:7]==b'\x7fELF\x02\x01\x01','ELF64 little-endian required')
    kind,machine=struct.unpack_from('<HH',data,16)
    entry,phoff=struct.unpack_from('<QQ',data,24)
    phsize,phcount=struct.unpack_from('<HH',data,54)
    need(kind==2 and machine==62 and entry==base and phsize==56 and phcount==1,'Exact static image entry/segments')
    need(phoff+56<=len(data),'Truncated segment')
    kind,flags,offset,virtual,physical,filesz,memsz,align=struct.unpack_from('<IIQQQQQQ',data,phoff)
    need(kind==1 and flags==5 and virtual==physical==base and filesz==memsz==len(blob) and 4<=memsz<=4096,'Bounded RX image')
    need(offset+filesz<=len(data) and data[offset:offset+filesz]==blob,'Exact installed image bytes')
    need(symbols.get('aurora_program_entry')==base and base<=symbols.get('aurora_user_main',0)<base+len(blob),'Compiled scalar entry')
    names=['aurora_program_return_pc','.Laurora_bounds_trap','.Laurora_overflow_trap','.Laurora_division_zero_trap','.Laurora_shift_count_trap']
    sites=[symbols.get(name,0) for name in names]
    need(all(sites[:3]),'Required return/bounds/overflow metadata')
    present=[pc for pc in sites if pc]
    need(len(set(present))==len(present),'Distinct exact sites')
    for pc in present:
        need(base<=pc<=base+len(blob)-2 and blob[pc-base:pc-base+2]==b'\x0f\x0b','Exact UD2 within image')
    ret=sites[0]-base
    need(ret>=2 and blob[ret-2:ret]==b'\xcd\x81','Typed return instruction')
    patch=symbols.get('aurora_kernel_probe_target',0)
    if patch:
        need(base+2<=patch<=base+len(blob)-8 and blob[patch-base:patch-base+8]==bytes(8),'Trusted test literal')
        need(all(not(patch<pc+2 and pc<patch+8) for pc in present),'Test literal aliases instruction authority')
    return dict(entry=base,size=len(blob),return_pc=sites[0],bounds_pc=sites[1],overflow_pc=sites[2],division_zero_pc=sites[3],shift_count_pc=sites[4],probe_offset=patch-base if patch else 0,probe_pc=symbols.get('aurora_probe_pc',0))

def build(compiler,out,mode):
    out.mkdir(parents=True,exist_ok=True)
    run=lambda args:subprocess.run([str(x) for x in args],cwd=ROOT,check=True)
    records={}; header=['#pragma once','#include <array>','#include <cstddef>','namespace aurora::uefi::images {']
    for index,name in enumerate(('clean','bounds')):
        prefix=out/f'user-{name}'
        run([compiler,ROOT/f'tests/kernel-programs/{name}.au','--module-root',ROOT/'library','-o',prefix.with_suffix('.s')])
        run(['as','--64','-L',prefix.with_suffix('.s'),'-o',prefix.with_suffix('.o')])
        adapter=out/f'user-{name}-entry.o'
        flags=['--defsym',f'UEFI_USER_{mode.upper()}=1'] if index==0 and mode in ('code','stack','window','kernel','write','nx','return','unknown','syscall','sysenter') else []
        run(['as','--64',*flags,ROOT/'kernel/uefi/user-image-entry.S','-o',adapter])
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
    print('PASS: two independently linked high-VA RX user images')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--compiler',required=True);parser.add_argument('--output',default='build/uefi');parser.add_argument('--mode',default='normal',choices=['normal','code','stack','window','kernel','write','nx','return','unknown','syscall','sysenter'])
    args=parser.parse_args();build(Path(args.compiler).resolve(),Path(args.output).resolve(),args.mode)
