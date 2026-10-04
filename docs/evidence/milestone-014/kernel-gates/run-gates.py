from pathlib import Path
import os,json,hashlib,subprocess,shutil,datetime
root=Path('/workspace/scratch/48c5de6446f8/aurora');os.chdir(root)
out=Path('/tmp/aurora-m014-kernel-receipts');out.mkdir(exist_ok=False)
now=lambda:datetime.datetime.now(datetime.timezone.utc).isoformat()
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(name,data): (out/name).write_text(json.dumps(data,indent=2)+'\n')
def inputs():
    files=[Path('Makefile')]
    for dirname in ('compiler','library','examples','kernel','scripts','tests','storage/design/model'):
        files += [p for p in Path(dirname).rglob('*') if p.is_file() and p.suffix not in ('.md','.pyc') and '__pycache__' not in p.parts and 'build' not in p.parts]
    return {str(p):sha(p) for p in sorted(set(files))}
env=os.environ.copy();settings=dict(AURORAC='/tmp/aurora-m014-compiler-corrected',QEMU='/tmp/aurora-qemu/root/usr/bin/qemu-system-x86_64',QEMU_DATA='/tmp/aurora-qemu/firmware',LD_LIBRARY_PATH='/tmp/aurora-qemu/root/usr/lib/x86_64-linux-gnu',OVMF='/tmp/aurora-ovmf/root/usr/share/ovmf/OVMF.fd');settings.update(AURORA_BAR_FIRMWARE='/tmp/aurora-clean-ovmf',AURORA_BAR_COVERAGE='/tmp/aurora-m014-bar-coverage.json');env.update(settings)
assert sha(settings['AURORAC'])=='2d86780c0082d861e7031955737eef81bb36936c7971d5032b6a1abbb4a24bf8'
start=now();before=inputs();write('source-inputs.json',before);shutil.copyfile(__file__,out/'run-gates.py')
versions={n:subprocess.check_output([exe,'--version'],env=env,text=True).splitlines()[0] for n,exe in [('g++','g++'),('as','as'),('ld','ld'),('python','python3'),('qemu',settings['QEMU'])]}
write('tools.json',dict(versions=versions,environment=settings,sha256={p:sha(p) for p in [settings['AURORAC'],settings['QEMU'],settings['OVMF']]}))
old=json.loads(Path('/tmp/aurora-m013-kernel-receipts/results.json').read_text())
modes=[(x['family'],x['mode']) for x in old['modes']]+[('uefi','runtime-span')]+[('bar',m) for m in ('bar-state','bar-capture','bar-inherited','bar-read','bar-write','bar-revoked','bar-alias')]
if len(modes)!=147 or len(set(modes))!=147:raise SystemExit('Wrong final mode inventory')
commands=[(['python3','scripts/kernel-uefi-bar-run.py',mode,'--output',str(out/'bar'/mode)] if family=='bar' else ['./scripts/kernel-smoke.sh' if family=='bios' else './scripts/kernel-uefi-smoke.sh',mode]) for family,mode in modes]
write('commands.json',dict(cwd=str(root),started_utc=start,source_manifest_timing='Captured before first build/gate; rechecked after all gates.',commands=commands))
results=[]
for (family,mode),command in zip(modes,commands):
    dest=out/family;dest.mkdir(exist_ok=True);label=mode.lstrip('-');log=dest/(label+'.command.log');started=now()
    with log.open('w') as stream: result=subprocess.run(command,env=env,stdout=stream,stderr=subprocess.STDOUT)
    files={str(log.relative_to(out)):sha(log)}
    base=(root/'build'/('kernel-serial' if mode=='normal' else 'kernel-'+label)) if family=='bios' else root/'build/uefi'/mode
    for suffix in (() if family=='bar' else ('.log','.metadata.json')):
        source=base.with_name(base.name+suffix)
        if source.exists():
            target=dest/(label+suffix);shutil.copyfile(source,target);files[str(target.relative_to(out))]=sha(target)
    results.append(dict(family=family,mode=mode,started_utc=started,completed_utc=now(),command=command,exit_code=result.returncode,result='PASS' if result.returncode==0 else 'FAIL',files=files))
    write('results.json',dict(started_utc=start,completed_utc=now(),distinct_modes=len(results),compiler_sha256=sha(settings['AURORAC']),modes=results))
    print(f'{len(results)}/147 {family} {mode}: {result.returncode}',flush=True)
    if result.returncode:raise SystemExit(result.returncode)
after=inputs();write('source-inputs-after.json',after)
if after!=before:raise SystemExit('Source inputs changed during final gates')
write('results.json',dict(started_utc=start,completed_utc=now(),distinct_modes=147,bios_distinct=37,uefi_distinct=110,compiler_sha256=sha(settings['AURORAC']),source_inputs_unchanged_at_completion=True,source_input_count=len(before),source_input_manifest_sha256=sha(out/'source-inputs.json'),normal_images_restored=True,independent_new_modes=8,independent_logs='/tmp/aurora-review-m14-bar',modes=results))
(out/'README.txt').write_text('Final exact-source 147-mode worker receipts:37 historical BIOS modes on the existing BIOS/QEMU path, 102 historical UEFI modes plus one protected span mode on packaged OVMF, seven BAR modes with explicit stock/clean firmware profiles. Each command must exit zero through its strict validators. Source inputs captured before first build and rechecked after all gates, including storage model Python inputs. BAR receipts independently bind argv/tool/firmware/artifact hashes; historical receipts retain existing metadata formats. Parent aggregate acceptance is separate. Development failures are preserved separately and are not passed gates.\n')
write('SHA256.json',{str(p.relative_to(out)):sha(p) for p in sorted(out.rglob('*')) if p.is_file() and p.name!='SHA256.json'})
print('PASS full147; source unchanged; receipts '+str(out),flush=True)
