#!/usr/bin/env python3
"""Actual compiler frames plus linked direct-call edges for CPU-only table modes."""
from pathlib import Path
import hashlib,json,re,subprocess,sys

def calculate(rows):
    def size(fragment,optional=False):
        found=[n for name,n in rows.items() if fragment in name]
        if not found and not optional:raise ValueError('Missing stack frame:'+fragment)
        return max(found,default=0)
    # The new profile explicitly separates parsing lifetime from PCI enumeration.
    payload=size('payload_main(');wrapper=size('discover_acpi(')
    acpi=size('prepare_table_acpi(');topology=size('Topology::parse(');pci=size('discover_pci(')
    verifiers=[n for name,n in rows.items() if 'PageTables::verify(' in name and '<lambda' not in name]
    if not verifiers:raise ValueError('Missing verifier entry frame')
    verify=max(verifiers);walks=[n for name,n in rows.items() if 'PageTables::verify(' in name and '<lambda' in name]
    if not walks:raise ValueError('Missing four-level verifier recursion')
    runtime=size('run_protected(');request=size('pin_request(');prepare=size('DormantTables::prepare(')
    grant=size('PinLedger::grant(');release=size('PinLedger::release_reserved(')
    ownership=size('DormantTables::ownership(');readback=size('table_readback(');decode=size('independent::validate(')
    table_prepare=size('table_prepare(');table_release=size('DormantTables::release(')
    scrub=size('table_scrub(');fault=size('pin_fault_returned(');reborn=size('pin_reborn(')
    corruption=size('table_corruption(',True);exhaustion=size('table_exhaustion(',True)
    if wrapper>128 or acpi>5120 or topology>4096 or pci>11264 or runtime>2048 or request>1024:
        raise ValueError('Reviewed large frame limit exceeded')
    if max(prepare,grant,release,ownership,readback,decode,table_prepare,table_release,scrub,fault,reborn,corruption,exhaustion)>1024:
        raise ValueError('Table path frame exceeds bounded profile')
    if any(n>11264 for n in rows.values()):raise ValueError('Unexpected large frame')
    # 512 covers bounded subordinate helpers;1024 reserved for synchronous fault
    # delivery and diagnostics. This is a conservative reviewed call-path bound,
    # not an arbitrary recursive-program stack proof or whole-firmware bound.
    leaf=512;fault_reserve=1024
    cleanup=table_release+release+scrub+leaf
    construction=table_prepare+prepare+max(grant+release+scrub,ownership,table_release+release+scrub)+leaf
    ancillary=max([n for name,n in rows.items() if name.startswith("runtime:") and "run_protected(" not in name]+[request,prepare,grant,release,ownership,readback,decode,corruption,exhaustion])
    paths={
      'acpi':payload+wrapper+acpi+topology+leaf,
      'pci':payload+wrapper+pci+verify+4*max(walks)+leaf,
      'construction':payload+runtime+request+construction,
      'readback':payload+runtime+request+readback+decode+leaf,
      'corruption':payload+runtime+request+corruption+max(decode,ownership)+leaf,
      'exhaustion':payload+runtime+request+exhaustion+max(construction,cleanup),
      'cleanup':payload+runtime+max(request,fault,reborn)+cleanup,
      'runtime_ancillary':payload+runtime+8*ancillary+4*192+leaf,
    }
    peak=max(paths.values())+fault_reserve
    if peak>15360:raise ValueError('16KiB stack reserve exhausted')
    return {'paths':paths,'peak_with_fault_reserve':peak,'fault_reserve':fault_reserve,'stack_bytes':16384,'minimum_unused':16384-peak}

def linked_edges(disassembly):
    current=None;edges=[]
    for line in disassembly.splitlines():
        head=re.match(r'^[0-9a-f]+ <(.+)>:$',line)
        if head:current=head[1]
        call=re.search(r'\b(?:call|jmp)\s+[0-9a-f]+ <(.+)>',line)
        if current and call:edges.append((current,call[1]))
    if any('prepare_table_acpi(' in a and 'discover_pci(' in b for a,b in edges):
        raise ValueError('ACPI parser retains frame across PCI discovery')
    for caller,callee in [('payload_main','discover_acpi('),('discover_acpi(','prepare_table_acpi('),
        ('discover_acpi(','discover_pci('),('payload_main','run_protected('),('run_protected(','pin_request('),
        ('pin_request(','table_prepare('),('table_prepare(','DormantTables::prepare('),
        ('pin_request(','table_readback('),('table_readback(','independent::validate(')]:
        if not any(caller in a and callee in b for a,b in edges):raise ValueError('Missing reviewed linked edge:'+caller+' -> '+callee)
    return edges

def load(directory):
    rows={}
    for name in ('payload','acpi','pci','runtime'):
        for line in (directory/(name+'.su')).read_text().splitlines():
            signature,size,kind=line.rsplit('\t',2)
            if kind not in ('static','dynamic,bounded'):raise ValueError('Unbounded frame')
            rows[name+':'+signature]=int(size)
    return rows

def self_test():
    rows={k:v for k,v in [('payload_main(',224),('discover_acpi(',48),('prepare_table_acpi(',3504),('Topology::parse(',3184),('discover_pci(',10736),('PageTables::verify(',208),('PageTables::verify(<lambda',96),('run_protected(',848),('pin_request(',416),('DormantTables::prepare(',192),('PinLedger::grant(',160),('PinLedger::release_reserved(',144),('DormantTables::ownership(',168),('table_readback(',160),('independent::validate(',48),('table_prepare(',64),('DormantTables::release(',112),('table_scrub(',8),('pin_fault_returned(',32),('pin_reborn(',48),('table_corruption(',208),('table_exhaustion(',272)]}
    result=calculate(rows)
    if result['peak_with_fault_reserve']!=13136:raise ValueError('Changed explicit reference sum')
    rejected=0
    for key in rows:
        for operation in ('remove','inflate'):
            changed=dict(rows)
            if operation=='remove':del changed[key]
            else:changed[key]=32768
            if operation=='remove' and key in ('table_corruption(','table_exhaustion('):continue
            try:calculate(changed)
            except ValueError:rejected+=1
            else:raise ValueError('Stack mutation accepted:'+key)
    extra=dict(rows);extra['runtime:unexpected_helper(']=4096
    try:calculate(extra)
    except ValueError:rejected+=1
    else:raise ValueError('New large runtime helper accepted')
    try:linked_edges('')
    except ValueError:rejected+=1
    else:raise ValueError('Absent link proof accepted')
    positive='\n'.join(f'{i:x} <{caller}>:\n {i:x}: call 100 <{callee}>' for i,(caller,callee) in enumerate([
      ('payload_main','discover_acpi('),('discover_acpi(','prepare_table_acpi('),('discover_acpi(','discover_pci('),
      ('payload_main','run_protected('),('run_protected(','pin_request('),('pin_request(','table_prepare('),
      ('table_prepare(','DormantTables::prepare('),('pin_request(','table_readback('),('table_readback(','independent::validate(')]))
    linked_edges(positive)
    try:linked_edges(positive+'\n200 <prepare_table_acpi(>:\n 200: call 100 <discover_pci(>')
    except ValueError:rejected+=1
    else:raise ValueError('Nested parser/PCI path accepted')
    print(f'PASS table stack2 positives/{rejected} negatives')
if __name__=='__main__':
    if sys.argv[1:]==['--self-test']:self_test()
    else:
        directory=Path(sys.argv[1]);out=Path(sys.argv[2]);out.mkdir(parents=True,exist_ok=True)
        rows=load(directory);result=calculate(rows)
        disassembly=subprocess.check_output(['objdump','-d','-C',str(directory/'payload.elf')],text=True)
        result['linked_edges']=linked_edges(disassembly)
        for name in ('payload','acpi','pci','runtime'):(out/(name+'.su')).write_bytes((directory/(name+'.su')).read_bytes())
        (out/'payload.disassembly.txt').write_text(disassembly)
        result['elf_sha256']=hashlib.sha256((directory/'payload.elf').read_bytes()).hexdigest()
        result['compiler_frames']=rows
        (out/'stack.json').write_text(json.dumps(result,indent=2)+'\n')
        print('PASS CPU-table stack peak',result['peak_with_fault_reserve'],'of16384')
