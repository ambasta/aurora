from pathlib import Path
import importlib.util, re, copy
root=Path('/workspace/scratch/48c5de6446f8/aurora')
spec=importlib.util.spec_from_file_location('pin',root/'tests/kernel-uefi-pin-smoke.py')
pin=importlib.util.module_from_spec(spec);spec.loader.exec_module(pin)
original=pin.validate
saved=[]
def capture(status,text,mode,metadata):
    original(status,text,mode,metadata)
    if mode=='runtime-pin-fault' and not saved:saved.append((text,copy.deepcopy(metadata)))
pin.validate=capture
pin.self_test()
pin.validate=original
text,metadata=saved[0]
owner=re.search(r'AURORA_PIN_OWNER:[^\n]*\n',text)[0]
restart=re.search(r'AURORA_PIN_RESTART:[^\n]*\n',text)[0]
rows=list(re.finditer(r'AURORA_UEFI_DOMAIN_EVENT:[^\n]*',text))
last=text.rindex('AURORA_UEFI_DOMAIN_ENTER:')
arena=int(re.search(r'AURORA_UEFI_OWNERSHIP_OK: arena=(\d+)',text)[1])
controls={
 'owner deleted':text.replace(owner,''),
 'owner duplicated':text.replace(owner,owner+owner),
 'owner moved early':owner+text.replace(owner,''),
 'owner moved late':text.replace(owner,'')+owner,
 'restart moved early':restart+text.replace(restart,''),
 'restart moved late':text.replace(restart,'')+restart,
 'restart bad uint64':text.replace(restart,re.sub(r'current=\d+','current=18446744073709551616',restart)),
 'restart same epoch':text.replace(restart,re.sub(r'current=\d+','current=2',restart)),
 'restart old not loan owner':text.replace(restart,re.sub(r'old=\d+','old=1',restart)),
 'restart malformed prefix':text.replace(restart,'prefix '+restart),
 'owner malformed prefix':text.replace(owner,'prefix '+owner),
}
for event,label in [(rows[1],'recognized fault'),(rows[3],'restart return')]:
    for field,value in [('vector',255),('error',1),('pc',0),('cpl',0),('root',0),('frame',0)]:
        altered=re.sub(rf'{field}=\d+',f'{field}={value}',event[0])
        controls[f'{label} wrong {field}']=text[:event.start()]+altered+text[event.end():]
controls['peer restart instead of service']=text[:last]+text[last:].replace('slot=1','slot=0').replace(f'root={arena+0xa0000}',f'root={arena+0x90000}').replace(f'stack={pin.runtime.STACK+0x200000+0x4000}',f'stack={pin.runtime.STACK+0x4000}')
for name,bad in controls.items():
    try:original(33,bad,'runtime-pin-fault',metadata)
    except ValueError:pass
    else:raise RuntimeError('accepted '+name)
print(f'PASS: {len(controls)} additional independent owner/restart/origin transcript mutation controls rejected')
