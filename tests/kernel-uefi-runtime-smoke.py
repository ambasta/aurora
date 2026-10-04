#!/usr/bin/env python3
from pathlib import Path
import importlib.util,json,re,sys,copy
spec=importlib.util.spec_from_file_location('pci',Path(__file__).with_name('kernel-pci-smoke.py'))
pci=importlib.util.module_from_spec(spec);spec.loader.exec_module(pci)
need=pci.need
SUCCESS_MODES=('runtime','runtime-span')
MODES=SUCCESS_MODES+('runtime-code','runtime-stack','runtime-kernel','runtime-window','runtime-root','runtime-kernel-trap','runtime-entry-stack','runtime-write','runtime-nx','runtime-return','runtime-unknown','runtime-syscall','runtime-sysenter')
BASE=0x10000000000
STACK=0x10000200000
SUFFIX='AURORA_UEFI_LANGUAGE_OK: value=42\nAURORA_UEFI_OK\n'

def validate(status,text,mode,metadata,*,retained=0,final_slot=0):
    need(type(retained) is int and retained in (0,2), "Invalid retained pin count")
    need(type(final_slot) is int and final_slot in (0,1) and (final_slot==0 or retained==2), "Invalid final slot")
    need(mode in MODES,'Unknown runtime mode')
    keys={'entry','size','return_pc','bounds_pc','overflow_pc','division_zero_pc','shift_count_pc','probe_offset','probe_pc'}
    need(type(metadata) is dict and set(metadata)=={'clean','bounds'},'Malformed metadata set')
    for index,name in enumerate(('clean','bounds')):
        image=metadata[name]
        need(type(image) is dict and set(image)==keys and all(type(v) is int and 0<=v<1<<64 for v in image.values()),'Malformed metadata values')
        base=BASE+index*4096;size=image['size']
        need(image['entry']==base and 4<=size<=4096,'Metadata layout widened')
        sites=[image[k] for k in ('return_pc','bounds_pc','overflow_pc','division_zero_pc','shift_count_pc')]
        need(all(sites[:3]) and len(set(pc for pc in sites if pc))==len([pc for pc in sites if pc]),'Ambiguous metadata sites')
        need(all(pc==0 or base<=pc<=base+size-2 for pc in sites) and image['return_pc']>=base+2,'Metadata site outside image')
        probe=image['probe_pc'];offset=image['probe_offset']
        need(probe==0 or base<=probe<=base+size-2 and probe not in sites,'Metadata probe outside image')
        need(offset==0 or size>=8 and 2<=offset<=size-8 and all(not(base+offset<pc+2 and pc<base+offset+8) for pc in sites if pc),'Metadata probe literal outside image')
        expected_probe=index==0 and mode in ('runtime-stack','runtime-kernel','runtime-window','runtime-write','runtime-return','runtime-unknown','runtime-syscall','runtime-sysenter')
        need(bool(probe)==expected_probe and bool(offset)==(index==0 and mode=='runtime-kernel'),'Unexpected metadata probe authority')

    patterns=(r'AURORA_UEFI_DOMAIN_ENTER: slot=\d+ root=\d+ entry=\d+ stack=\d+',
        r'AURORA_UEFI_DOMAIN_EVENT: vector=\d+ error=\d+ pc=\d+ cpl=\d+ root=\d+ frame=\d+ cr2=\d+',
        r'AURORA_UEFI_DOMAIN_RESTORE: slot=\d+ root=\d+ stack=\d+ event=(returned|bounds) value=\d+',
        r'AURORA_UEFI_DOMAIN_REUSE_OK: frame=\d+',rf'AURORA_UEFI_DOMAIN_CLEANUP_OK: used={retained}',
        r'AURORA_UEFI_RUNTIME_ROOT_PROBE: root=\d+',r'AURORA_UEFI_RUNTIME_IST_OK',r'AURORA_UEFI_RUNTIME_OK',
        r'AURORA_UEFI_RUNTIME_FAIL: (exception root authority|exception origin/stack|exception site authority|double fault)')
    for line in text.splitlines():
        if line.startswith(('AURORA_UEFI_DOMAIN_','AURORA_UEFI_RUNTIME_')):
            need(any(re.fullmatch(pattern,line) for pattern in patterns),'Malformed runtime record')
    need('AURORA_UEFI_PAYLOAD_FAIL:' not in text and 'AURORA_UEFI_FAIL:' not in text,'Unexpected boot failure')
    if mode!='runtime-root': need('AURORA_UEFI_RUNTIME_ROOT_PROBE:' not in text,'Unexpected root probe')
    if mode!='runtime-entry-stack': need('AURORA_UEFI_RUNTIME_IST_OK' not in text,'Unexpected IST proof')

    start=text.find('AURORA_UEFI_DOMAIN_ENTER:')
    need(start>=0,'Runtime never entered user domain')
    pci.validate(33,text[:start]+SUFFIX,'pci')
    owned=re.search(r'AURORA_UEFI_OWNERSHIP_OK: arena=(\d+)',text);arena=int(owned[1]);kernel=arena+0x11000
    enter=list(re.finditer(r'AURORA_UEFI_DOMAIN_ENTER: slot=(\d+) root=(\d+) entry=(\d+) stack=(\d+)',text))
    events=list(re.finditer(r'AURORA_UEFI_DOMAIN_EVENT: vector=(\d+) error=(\d+) pc=(\d+) cpl=(\d+) root=(\d+) frame=(\d+) cr2=(\d+)',text))
    restores=list(re.finditer(r'AURORA_UEFI_DOMAIN_RESTORE: slot=(\d+) root=(\d+) stack=(\d+) event=(returned|bounds) value=(\d+)',text))
    count=4 if mode in SUCCESS_MODES else 1
    need(len(enter)==len(events)==count and len(restores)==(4 if mode in SUCCESS_MODES else 0),'Run/event/restoration count')
    for prefix,records in [('AURORA_UEFI_DOMAIN_ENTER:',enter),('AURORA_UEFI_DOMAIN_EVENT:',events),('AURORA_UEFI_DOMAIN_RESTORE:',restores)]:
        need(text.count(prefix)==len(records),'Malformed/duplicate runtime record')
    for index,(entry,event) in enumerate(zip(enter,events)):
        slot,root,pc,sp=map(int,entry.groups());wanted_slot=1 if index==1 else final_slot if index==3 else 0
        need(slot==wanted_slot and root==arena+0x90000+slot*0x10000 and pc==BASE+(1 if index==1 else 0)*4096 and sp==STACK+slot*0x200000+0x4000,'Wrong private entry layout')
        need(entry.start()<event.start(),'Event before entry')
        vector,error,rip,cpl,actual,frame,cr2=map(int,event.groups())
        need(actual==root,'Event under foreign root')
        expected_cpl=0 if mode=='runtime-kernel-trap' else 3
        need(cpl==expected_cpl,'Wrong privilege origin')
        if mode=='runtime-entry-stack':
            need(arena+0x89000<=frame<=arena+0x8d000-176 and frame%8==0,'Wrong IST stack')
        elif mode=='runtime-kernel-trap':
            need(arena+0x44000<=frame<arena+0x48000 and frame%8==0,'Wrong kernel trap stack')
        else: need(arena+0x84000<=frame<=arena+0x88000-176 and frame%8==0,'Wrong RSP0 frame')
        image=metadata['bounds' if index==1 else 'clean']
        need(image['entry']==pc and 4<=image['size']<=4096,'Fixture metadata entry')
        if mode in SUCCESS_MODES:
            kind='bounds' if index==1 else 'returned';target=image['bounds_pc'] if index==1 else image['return_pc']
            need((vector,error,rip)==(6 if index==1 else 129,0,target),'Wrong exact contained site')
            restored=restores[index];rslot,rroot,rsp,rkind,value=restored.groups()
            need(int(rslot)==slot and int(rroot)==kernel and arena+0x44000<=int(rsp)<arena+0x48000 and rkind==kind and int(value)==(0 if index==1 else 42),'Restored authority/result mismatch')
            need(event.start()<restored.start() and (index==3 or restored.start()<enter[index+1].start()),'Continuation order')
        else:
            if mode in ('runtime-code','runtime-stack','runtime-kernel','runtime-window','runtime-write','runtime-nx'):
                address={'runtime-code':BASE+4096,'runtime-stack':STACK+0x200000,'runtime-kernel':arena,'runtime-window':pci.WINDOW,'runtime-write':BASE,'runtime-nx':STACK+0x4000-8}[mode]
                err={'runtime-code':20,'runtime-stack':4,'runtime-kernel':5,'runtime-window':4,'runtime-write':7,'runtime-nx':21}[mode]
                target=address if mode in ('runtime-code','runtime-nx') else image['probe_pc']
                need((vector,error,rip,cr2)==(14,err,target,address),'Wrong protection fault/site')
            elif mode=='runtime-root': need((vector,error,rip)==(129,0,image['return_pc']),'Wrong return-root probe')
            elif mode=='runtime-kernel-trap': need((vector,error,rip)==(6,0,image['bounds_pc']),'Wrong known kernel UD2')
            elif mode=='runtime-entry-stack': need((vector,error,rip,cr2)==(8,0,image['return_pc']-2,arena+0x84000-8),'Missing exact entry-stack double fault')
            elif mode=='runtime-return': need((vector,error,rip)==(129,0,image['probe_pc']) and rip!=image['return_pc'],'Wrong forged return site')
            elif mode in ('runtime-syscall','runtime-sysenter'): need((vector,error,rip)==(6 if mode=='runtime-syscall' else 13,0,image['probe_pc']),'Inherited alternate privilege entry')
            elif mode=='runtime-unknown': need((vector,error,rip)==(6,0,image['probe_pc']) and rip not in [image[k] for k in ('bounds_pc','overflow_pc','division_zero_pc','shift_count_pc')],'Unknown UD2 accepted as known')
    if mode in SUCCESS_MODES:
        pci.validate(status,text,'pci')
        need('AURORA_UEFI_RUNTIME_FAIL:' not in text,'Runtime failure hidden by success')
        reuse=re.findall(r'AURORA_UEFI_DOMAIN_REUSE_OK: frame=(\d+)',text)
        need(len(reuse)==1 and int(reuse[0])==arena+0xc0000,'Wrong reused frame')
        need(restores[2].start()<text.index('AURORA_UEFI_DOMAIN_REUSE_OK:')<enter[3].start(),'Reuse before retirement')
        for marker in (f'AURORA_UEFI_DOMAIN_CLEANUP_OK: used={retained}','AURORA_UEFI_RUNTIME_OK'):
            need(text.count(marker)==1,'Missing unique cleanup/runtime completion')
        need(restores[3].start()<text.index('AURORA_UEFI_DOMAIN_CLEANUP_OK:')<text.index('AURORA_UEFI_RUNTIME_OK')<text.index('AURORA_UEFI_LANGUAGE_OK:'),'Final cleanup order')
        need('AURORA_UEFI_RUNTIME_ROOT_PROBE:' not in text and 'AURORA_UEFI_RUNTIME_IST_OK' not in text,'Unexpected failure probe')
    else:
        need(status==35 and text.count('AURORA_UEFI_RUNTIME_FAIL:')==1,'Missing unique runtime failure')
        need(all(marker not in text for marker in ('AURORA_UEFI_LANGUAGE_OK','AURORA_UEFI_OK','AURORA_UEFI_DOMAIN_REUSE_OK:','AURORA_UEFI_DOMAIN_CLEANUP_OK:','AURORA_UEFI_RUNTIME_OK')),'Rejected domain continued')
        need(events[0].start()<text.index('AURORA_UEFI_RUNTIME_FAIL:'),'Failure before event')
        if mode=='runtime-root':
            probe=re.findall(r'AURORA_UEFI_RUNTIME_ROOT_PROBE: root=(\d+)',text)
            need(len(probe)==1 and int(probe[0])==kernel and events[0].start()<text.index('AURORA_UEFI_RUNTIME_ROOT_PROBE:')<text.index('AURORA_UEFI_RUNTIME_FAIL: exception root authority'),'Root probe authority')
        elif mode=='runtime-entry-stack':
            need(text.count('AURORA_UEFI_RUNTIME_IST_OK')==1 and events[0].start()<text.index('AURORA_UEFI_RUNTIME_IST_OK')<text.index('AURORA_UEFI_RUNTIME_FAIL: double fault'),'Missing IST proof')
        else:
            reason='exception origin/stack' if mode=='runtime-kernel-trap' else 'exception site authority'
            need('AURORA_UEFI_RUNTIME_FAIL: '+reason in text,'Wrong boundary rejection')

def self_test():
    arena=0x1000000; kernel=arena+0x11000
    prefix=f'AURORA_UEFI_ENTRY\nAURORA_UEFI_EXIT_OK: attempts=1\nAURORA_UEFI_PAYLOAD_ENTRY\nAURORA_UEFI_OWNERSHIP_OK: arena={arena} bytes=1048576 descriptors=111\nAURORA_UEFI_PROTECTION_OK: root={kernel} stack={arena+0x47e00}\nAURORA_ACPI_CPU: id=0 uid=0 enabled=1 capable=0 x2=0\nAURORA_ACPI_TOPOLOGY: records=1 enabled=1 capable=0 lapic=4276092928\nAURORA_ACPI_WINDOW_CLOSED: copies=14\nAURORA_PCI_APERTURE: base=3758096384 bytes=268435456 segment=0 first=0 last=255\nAURORA_PCI_FUNCTION: segment=0 bus=0 device=0 function=0 vendor=32902 product=10688 class=6 subclass=0 interface=0 header=0 command=7 secondary=0 subordinate=0\nAURORA_PCI_INVENTORY: functions=1 buses=1\nAURORA_PCI_WINDOW_CLOSED: reads=39\n'
    metadata={}
    for index,name in enumerate(('clean','bounds')):
        base=BASE+index*4096
        metadata[name]=dict(entry=base,size=128,return_pc=base+60,bounds_pc=base+64,overflow_pc=base+68,division_zero_pc=base+72,shift_count_pc=base+76,probe_pc=base+52,probe_offset=0)
    cases={}
    for mode in MODES:
        text=prefix
        for i in range(4 if mode in SUCCESS_MODES else 1):
            slot=1 if i==1 else 0; root=arena+0x90000+slot*0x10000;sp=STACK+slot*0x200000+0x4000;image=metadata['bounds' if slot else 'clean']
            if i==3: text+=f'AURORA_UEFI_DOMAIN_REUSE_OK: frame={arena+0xc0000}\n'
            text+=f'AURORA_UEFI_DOMAIN_ENTER: slot={slot} root={root} entry={image["entry"]} stack={sp}\n'
            vector=6 if i==1 else 129;error=0;pc=image['bounds_pc'] if i==1 else image['return_pc'];cpl=3;frame=arena+0x88000-176;cr2=0
            if mode in ('runtime-code','runtime-stack','runtime-kernel','runtime-window','runtime-write','runtime-nx'):
                vector=14;error={'runtime-code':20,'runtime-stack':4,'runtime-kernel':5,'runtime-window':4,'runtime-write':7,'runtime-nx':21}[mode]
                cr2={'runtime-code':BASE+4096,'runtime-stack':STACK+0x200000,'runtime-kernel':arena,'runtime-window':pci.WINDOW,'runtime-write':BASE,'runtime-nx':STACK+0x4000-8}[mode]
                pc=cr2 if mode in ('runtime-code','runtime-nx') else image['probe_pc']
            elif mode=='runtime-kernel-trap': vector=6;pc=image['bounds_pc'];cpl=0;frame=arena+0x47c00
            elif mode=='runtime-entry-stack': vector=8;pc=image['return_pc']-2;cr2=arena+0x84000-8;frame=arena+0x8d000-176
            elif mode=='runtime-return': pc=image['probe_pc']
            elif mode=='runtime-unknown': vector=6;pc=image['probe_pc']
            elif mode in ('runtime-syscall','runtime-sysenter'): vector=6 if mode=='runtime-syscall' else 13;pc=image['probe_pc']
            text+=f'AURORA_UEFI_DOMAIN_EVENT: vector={vector} error={error} pc={pc} cpl={cpl} root={root} frame={frame} cr2={cr2}\n'
            if mode in SUCCESS_MODES: text+=f'AURORA_UEFI_DOMAIN_RESTORE: slot={slot} root={kernel} stack={arena+0x47c00} event={"bounds" if i==1 else "returned"} value={0 if i==1 else 42}\n'
        if mode in SUCCESS_MODES: text+='AURORA_UEFI_DOMAIN_CLEANUP_OK: used=0\nAURORA_UEFI_RUNTIME_OK\n'+SUFFIX
        else:
            reason='exception site authority'
            if mode=='runtime-root': text+=f'AURORA_UEFI_RUNTIME_ROOT_PROBE: root={kernel}\n';reason='exception root authority'
            if mode=='runtime-entry-stack': text+='AURORA_UEFI_RUNTIME_IST_OK\n';reason='double fault'
            if mode=='runtime-kernel-trap': reason='exception origin/stack'
            text+=f'AURORA_UEFI_RUNTIME_FAIL: {reason}\n'
        case_metadata=copy.deepcopy(metadata)
        case_metadata['bounds']['probe_pc']=0
        if mode not in ('runtime-stack','runtime-kernel','runtime-window','runtime-write','runtime-return','runtime-unknown','runtime-syscall','runtime-sysenter'): case_metadata['clean']['probe_pc']=0
        case_metadata['clean']['probe_offset']=88 if mode=='runtime-kernel' else 0
        cases[mode]=(33 if mode in SUCCESS_MODES else 35,text,case_metadata)
    rejected=0
    for mode,(status,text,metadata) in cases.items():
        validate(status,text,mode,metadata)
        invalid=[(0,text),(status,text+'AURORA_UEFI_DOMAIN_CLEANUP_OK: used=1\n'),(status,text+'AURORA_UEFI_RUNTIME_FAIL: forged\n')]
        if mode!='runtime-root': invalid.append((status,text+f'AURORA_UEFI_RUNTIME_ROOT_PROBE: root={kernel}\n'))
        if mode!='runtime-entry-stack': invalid.append((status,text+'AURORA_UEFI_RUNTIME_IST_OK\n'))
        for line in text.splitlines():
            invalid.extend([(status,text.replace(line+'\n','',1)),(status,text.replace(line+'\n',(line+'\n')*2,1))])
        if mode in SUCCESS_MODES:
            invalid.append((status,text+'AURORA_UEFI_RUNTIME_FAIL: unexpected\n'))
            last=[line for line in text.splitlines() if line.startswith('AURORA_UEFI_DOMAIN_RESTORE:')][-1]+'\n'
            invalid.append((status,text.replace(last,'',1)+last))
        else: invalid.extend([(status,text+SUFFIX),(status,text+'AURORA_UEFI_RUNTIME_OK\n')])
        event=re.search(r'AURORA_UEFI_DOMAIN_EVENT:[^\n]+',text)[0]
        for key,value in [('root','0'),('frame','0'),('pc','0'),('cpl','2'),('error','255')]:
            altered=re.sub(fr'{key}=\d+',f'{key}={value}',event)
            invalid.append((status,text.replace(event,altered,1)))
        for field,value in [('return_pc',0),('bounds_pc',BASE-2),('overflow_pc',BASE+4096),('size',8192),('entry',0),('return_pc',True),('probe_offset',4096)]:
            altered=copy.deepcopy(metadata);old=altered['clean'][field];altered['clean'][field]=value
            bad=text.replace(f'pc={old} ',f'pc={int(value)} ') if field=='return_pc' else text
            try: validate(status,bad,mode,altered)
            except ValueError: rejected+=1
            else: raise RuntimeError(f'Invalid runtime metadata accepted: {mode} {field}')
        for code,bad in invalid:
            try: validate(code,bad,mode,metadata)
            except ValueError: rejected+=1
            else: raise RuntimeError(f'Invalid runtime transcript accepted: {mode}')
    print(f'PASS: UEFI runtime transcripts {len(cases)} positive and {rejected} negative cases')

if __name__=='__main__':
    if sys.argv[1:]==['--self-test']:
        self_test();sys.exit(0)
    try: validate(int(sys.argv[1]),Path(sys.argv[2]).read_text(),sys.argv[3],json.loads(Path(sys.argv[4]).read_text()))
    except ValueError as error: sys.exit(f'FAIL: {error}')
