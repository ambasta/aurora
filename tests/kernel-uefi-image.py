#!/usr/bin/env python3
"""PE32+ relocation/permission and independently linked PIC payload verifier."""
from pathlib import Path
import hashlib
import json
import re
import subprocess

ROOT=Path(__file__).resolve().parents[1]
BUILD=ROOT/'build/uefi'

def need(value,reason):
    if not value: raise ValueError(reason)

def u(data,offset,size):
    need(0<=offset<=len(data) and 0<size<=len(data)-offset,'Truncated integer')
    return int.from_bytes(data[offset:offset+size],'little')

def pe_validate(data,payload):
    need(data[:2]==b'MZ','DOS signature')
    nt=u(data,60,4); need(data[nt:nt+4]==b'PE\0\0','PE signature')
    need(u(data,nt+4,2)==0x8664,'Wrong PE architecture')
    count=u(data,nt+6,2); optional=u(data,nt+20,2); opt=nt+24
    need(1<=count<=32 and optional>=240 and opt+optional+count*40<=len(data),'PE headers')
    need(u(data,opt,2)==0x20b and u(data,opt+68,2)==10,'Not PE32+ EFI application')
    need(u(data,opt+32,4)==4096 and u(data,opt+36,4)==512,'PE alignment')
    size=u(data,opt+56,4); base=u(data,opt+24,8); entry=u(data,opt+16,4)
    need(0<size<=1048576 and size%4096==0 and base==0x100000,'PE image bound')
    need(u(data,opt+108,4)==16 and u(data,opt+70,2)&0x140==0x140,'PE relocation/NX flags')
    sections=[]
    for i in range(count):
        at=opt+optional+i*40
        virtual=u(data,at+8,4); rva=u(data,at+12,4); raw=u(data,at+16,4); offset=u(data,at+20,4); flags=u(data,at+36,4)
        need(virtual>0 and rva>=4096 and rva%4096==0 and rva+max(raw,virtual)<=size,'PE section range')
        need(raw%512==0 and offset%512==0 and offset+raw<=len(data),'PE section bytes')
        need(not(flags&0x20000000 and flags&0x80000000),'PE writable executable section')
        for old in sections: need(rva>=old[0]+max(old[1],old[2]) or old[0]>=rva+max(raw,virtual),'Overlapping sections')
        sections.append((rva,virtual,raw,offset,flags))
    def locate(rva,n):
        for start,virtual,raw,offset,flags in sections:
            if start<=rva and rva+n<=start+min(virtual,raw): return offset+rva-start,flags
        raise ValueError('RVA not file-backed')
    _,flags=locate(entry,1); need(flags&0x20000000 and not flags&0x80000000,'Entry permission')
    import_rva,import_size=u(data,opt+120,4),u(data,opt+124,4)
    if import_size:
        at,_=locate(import_rva,import_size); need(not any(data[at:at+import_size]),'External imports')
    reloc_rva,reloc_size=u(data,opt+152,4),u(data,opt+156,4)
    need(reloc_size>=12,'Missing base relocation')
    cursor,_=locate(reloc_rva,reloc_size); end=cursor+reloc_size; targets=[]
    while cursor<end:
        page,block=u(data,cursor,4),u(data,cursor+4,4)
        need(page%4096==0 and block>=8 and block%4==0 and cursor+block<=end,'Relocation block')
        for at in range(cursor+8,cursor+block,2):
            item=u(data,at,2); kind=item>>12
            if kind==0: continue
            need(kind==10,'Only DIR64 base relocations allowed')
            target=page+(item&4095); file_at,_=locate(target,8)
            need(target not in targets,'Duplicate relocation')
            value=u(data,file_at,8); need(base<=value<base+size,'Relocation target outside image')
            targets.append(target)
        cursor+=block
    need(targets,'No actual address relocation')
    need(data.count(payload)==1,'Embedded payload identity/uniqueness')
    # Independent relocation arithmetic check at a second load base.
    relocated=bytearray(data); delta=0x2500000
    for target in targets:
        at,_=locate(target,8); value=u(data,at,8)
        relocated[at:at+8]=(value+delta).to_bytes(8,'little')
        need(u(relocated,at,8)-(base+delta)==value-base,'Relocation arithmetic')
    return nt,opt,sections

def elf_validate(data,binary):
    need(data[:6]==b'\x7fELF\x02\x01' and u(data,18,2)==62,'Payload ELF architecture')
    need(u(data,24,8)==0 and u(data,56,2)==3 and u(data,54,2)==56,'Payload entry/headers')
    start=u(data,32,8); previous_end=0
    for i,flags in enumerate((5,4,6)):
        at=start+i*56
        kind,actual=u(data,at,4),u(data,at+4,4)
        offset,virtual,size,memory,alignment=(u(data,at+x,8) for x in (8,16,32,40,48))
        need(kind==1 and actual==flags and alignment==4096,'Payload section policy')
        need(virtual%4096==0 and virtual>=previous_end and memory>=size and virtual+memory<=0x20000,'Payload section bound')
        need(offset+size<=len(data) and virtual+size<=len(binary) if size else True,'Payload truncation')
        if size: need(data[offset:offset+size]==binary[virtual:virtual+size],'Payload extraction mismatch')
        previous_end=virtual+memory
    need(0<len(binary)<=0x20000,'Payload bound')

def budget_call_present(disassembly):
    # GNU objdump -drwC on an unlinked x86-64 object: a direct E8 call with
    # zero displacement, an exact target/addend, and relocation at its imm32.
    pattern=(r'\s*([0-9a-f]+):\s+e8 00 00 00 00\s+callq?\s+'
             r'([0-9a-f]+) <[^>]+>\s+([0-9a-f]+): R_X86_64_PLT32\s+'
             r'aurora_kernel_budget_tick-0x4\s*')
    for line in disassembly.splitlines():
        match=re.fullmatch(pattern,line)
        if match:
            call,target,relocation=(int(value,16) for value in match.groups())
            if target==call+5 and relocation==call+1: return True
    return False

def main():
    pe_path=BUILD/'esp/EFI/BOOT/BOOTX64.EFI'
    data=pe_path.read_bytes(); binary=(BUILD/'payload.bin').read_bytes(); elf=(BUILD/'payload.elf').read_bytes()
    nt,opt,sections=pe_validate(data,binary); elf_validate(elf,binary)
    names=['payload','payload-entry','language','acpi','pci','runtime']
    symbols=subprocess.check_output(['nm','-a',str(BUILD/'payload.elf')],text=True)
    if 'uefi_runtime_enter' in symbols: names+=['runtime-entry','runtime-exceptions']
    if 'uefi_service_drain_begin' in symbols:
        policy_relocations=subprocess.check_output(['objdump','-drwC',str(BUILD/'runtime.o')],text=True)
        need(budget_call_present(policy_relocations),
             'Service timer does not call the actual Aurora budget entry')
        policy_symbols={row.split()[2]:int(row.split()[0],16) for row in symbols.splitlines() if len(row.split())==3}
        need(0<policy_symbols.get('aurora_kernel_budget_tick',0)<policy_symbols['__payload_text_end'],
             'Aurora budget entry outside owned payload RX')
    for name in names:
        relocations=subprocess.check_output(['readelf','-rW',str(BUILD/f'{name}.o')],text=True)
        types=set(re.findall(r'R_X86_64_\w+',relocations))
        need(types<= {'R_X86_64_PC32','R_X86_64_PLT32'},f'Non-PIC object relocation in {name}: {types}')
    need(not subprocess.check_output(['nm','-u',str(BUILD/'payload.elf')],text=True).strip(),'Unresolved payload symbol')
    negatives=[]
    def mutate(at,value,width):
        broken=bytearray(data); broken[at:at+width]=value.to_bytes(width,'little'); negatives.append(bytes(broken))
    for at,value,width in ((0,0,2),(nt,0,4),(nt+4,0x14c,2),(opt,0x10b,2),(opt+68,3,2),
                           (opt+32,512,4),(opt+56,0xffffffff,4),(opt+16,0,4),(opt+156,0,4)):
        mutate(at,value,width)
    section_table=opt+u(data,nt+20,2)
    mutate(section_table+36,0xe0000020,4)
    mutate(section_table+12,0,4)
    negatives.extend((data[:128],data.replace(binary,b'\0'*len(binary),1)))
    for broken in negatives:
        try: pe_validate(broken,binary)
        except ValueError: pass
        else: raise RuntimeError('Invalid UEFI PE image accepted')
    bad_elf=bytearray(elf); bad_elf[u(elf,32,8)+4:u(elf,32,8)+8]=(7).to_bytes(4,'little')
    try: elf_validate(bad_elf,binary)
    except ValueError: pass
    else: raise RuntimeError('RWX payload accepted')
    (BUILD/'image-metadata.json').write_text(json.dumps({'pe_sha256':hashlib.sha256(data).hexdigest(),
        'payload_sha256':hashlib.sha256(binary).hexdigest(),'payload_bytes':len(binary)},indent=2)+'\n')
    print(f'PASS: PE32+ EFI relocation/RX policy, exact PIC payload; {len(negatives)+1} negative images')

if __name__=='__main__': main()
