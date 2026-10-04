from pathlib import Path
import os,json,hashlib,subprocess,shutil,datetime
root=Path('/workspace/scratch/48c5de6446f8/aurora');out=Path('/tmp/aurora-amd310-guest-review/actual-final-four')
out.mkdir(exist_ok=False)
now=lambda:datetime.datetime.now(datetime.timezone.utc).isoformat()
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(name,value):(out/name).write_text(json.dumps(value,indent=2)+'\n')
def inputs():
 files=[root/'Makefile']
 for directory in ('compiler','library','examples','kernel','scripts','tests','storage','fixtures'):
  files += [p for p in (root/directory).rglob('*') if p.is_file() and p.suffix not in ('.md','.pyc') and '__pycache__' not in p.parts and 'build' not in p.parts]
 return {str(p.relative_to(root)):sha(p) for p in sorted(set(files))}
settings={'AURORAC':'/tmp/aurora-resource-main-compiler-frozen','QEMU':'/tmp/aurora-qemu/root/usr/bin/qemu-system-x86_64','QEMU_DATA':'/tmp/aurora-qemu/firmware','LD_LIBRARY_PATH':'/tmp/aurora-qemu/root/usr/lib/x86_64-linux-gnu','OVMF':'/tmp/aurora-ovmf/root/usr/share/ovmf/OVMF.fd','PYTHONDONTWRITEBYTECODE':'1'}
assert sha(settings['AURORAC'])=='14cbaa33b69b81240b5828b6893f4c150eeaa9a11d95a83726d32e417c1f8980'
review_manifest=root.parent/'aurora-m019-development/kernel-review-inputs.json';assert sha(review_manifest)=='e0de2883c7f0cd7f8df351bdc09207ba6017e4e6467f032cc30a51b1ddb23c55'
for p,v in json.loads(review_manifest.read_text()).items():assert sha(root/p)==v,p
xfs=json.loads((root/'docs/evidence/milestone-019/xfs-geometry/integration-delta.json').read_text());assert len(xfs['files'])==9
for item in xfs['files']:assert sha(root/item['path'])==item['sha256'],item['path']
write('xfs-integration-delta.json',xfs)
before=inputs();write('source-inputs-before.json',before)
external=[Path(settings[x]) for x in ('AURORAC','QEMU','OVMF')]
external += [Path(shutil.which(x)).resolve() for x in ('g++','as','ld','objcopy','nm','objdump','readelf','python3','bash','make','timeout')]
for path in (settings['QEMU_DATA'],settings['LD_LIBRARY_PATH']):external += [p for p in Path(path).rglob('*') if p.is_file()]
ext_before={str(p):sha(p) for p in sorted(set(external))};write('external-inputs-before.json',ext_before)
env=os.environ.copy();env.pop('UEFI_MODE',None);env.update(settings);write('environment.json',settings)
write('tools.json',{x:subprocess.check_output([exe,'--version'],text=True,env=env).splitlines()[0] for x,exe in [('g++','g++'),('as','as'),('ld','ld'),('objdump','objdump'),('python','python3'),('qemu',settings['QEMU'])]})
shutil.copyfile(__file__,out/'run-independent-four.py')
results=[]
for name in ('readback','reject','exhaust','quarantine'):
 mode='runtime-table-'+name;dest=out/mode;dest.mkdir()
 command=['./scripts/kernel-uefi-smoke.sh',mode];start=now()
 with (dest/'command.log').open('w') as f:r=subprocess.run(command,cwd=root,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=240)
 for suffix in ('.log','.metadata.json'):shutil.copyfile(root/'build/uefi'/(mode+suffix),dest/(mode+suffix))
 shutil.copytree(root/'build/uefi/table-stack'/mode,dest/'stack')
 stack=json.loads((dest/'stack/stack.json').read_text());assert stack['peak_with_fault_reserve']<=15360
 results.append({'mode':mode,'command':command,'started_utc':start,'completed_utc':now(),'exit_code':r.returncode,'stack_peak_including_fault':stack['peak_with_fault_reserve'],'stack_bytes':stack['stack_bytes']})
 write('results.json',results);print(mode,r.returncode,'stack',stack['peak_with_fault_reserve'],flush=True)
 if r.returncode:raise SystemExit(r.returncode)
 symbols=subprocess.check_output(['nm','-a','-C',str(root/'build/uefi/payload.elf')],text=True);(dest/'restored-normal-symbols.log').write_text(symbols)
 assert not any(x in symbols for x in ['Dormant','independent::','table_readback','table_prepare'])
 assert b'AURORA_TABLE' not in (root/'build/uefi/payload.bin').read_bytes()
 # The smoke trap has now restored ordinary non-table UEFI output.
 write(mode+'-normal-image.json',{p:sha(root/p) for p in ['build/uefi/payload.elf','build/uefi/payload.bin','build/uefi/esp/EFI/BOOT/BOOTX64.EFI']})
after=inputs();write('source-inputs-after.json',after);assert before==after
ext_after={p:sha(p) for p in ext_before};write('external-inputs-after.json',ext_after);assert ext_before==ext_after
write('summary.json',{'result':'PASS','scope':'Actual QEMU guest CPU_BYTES/SOFTWARE_MODEL only','modes':4,'source_files':len(before),'source_inputs_unchanged':True,'external_files':len(ext_before),'external_inputs_unchanged':True,'normal_restored_after_each_mode':True,'source_manifest_sha256':sha(out/'source-inputs-before.json'),'kernel_review_manifest_sha256':sha(review_manifest),'compiler_sha256':sha(settings['AURORAC']),'results':results})
write('SHA256.json',{str(p.relative_to(out)):sha(p) for p in sorted(out.rglob('*')) if p.is_file() and p.name!='SHA256.json'})
print('PASS independent actual four; source/external unchanged; normal restored',flush=True)
