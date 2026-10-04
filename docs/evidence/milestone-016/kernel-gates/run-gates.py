from pathlib import Path
import os,json,hashlib,subprocess,shutil,datetime
root=Path('/workspace/scratch/48c5de6446f8/aurora');os.chdir(root)
out=Path('/workspace/scratch/48c5de6446f8/aurora-m016-kernel-receipts');out.mkdir(exist_ok=False)
now=lambda:datetime.datetime.now(datetime.timezone.utc).isoformat()
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(name,data): (out/name).write_text(json.dumps(data,indent=2)+'\n')
def inputs():
    files=[Path('Makefile')]
    for dirname in ('compiler','library','examples','kernel','scripts','tests','storage/design/model','fixtures'):
        files += [p for p in Path(dirname).rglob('*') if p.is_file() and p.suffix not in ('.md','.pyc') and '__pycache__' not in p.parts and 'build' not in p.parts]
    return {str(p):sha(p) for p in sorted(set(files))}
env=os.environ.copy();settings=dict(AURORAC=os.environ['AURORA_FINAL_COMPILER'],QEMU='/tmp/aurora-qemu/root/usr/bin/qemu-system-x86_64',QEMU_DATA='/tmp/aurora-qemu/firmware',LD_LIBRARY_PATH='/tmp/aurora-qemu/root/usr/lib/x86_64-linux-gnu',OVMF='/tmp/aurora-ovmf/root/usr/share/ovmf/OVMF.fd');settings.update(AURORA_BAR_FIRMWARE='/tmp/aurora-clean-ovmf',AURORA_BAR_COVERAGE='/tmp/aurora-m014-bar-coverage.json',AURORA_IVRS_FIRMWARE='/tmp/aurora-clean-ovmf',AURORA_IVRS_COVERAGE='/tmp/aurora-m015-coverage.json');env.update(settings)
if sha(settings['AURORAC'])!=os.environ['AURORA_FINAL_COMPILER_SHA']:raise SystemExit('Final compiler identity mismatch')
start=now();before=inputs();write('source-inputs.json',before);shutil.copyfile(__file__,out/'run-gates.py')
versions={n:subprocess.check_output([exe,'--version'],env=env,text=True).splitlines()[0] for n,exe in [('g++','g++'),('as','as'),('ld','ld'),('python','python3'),('qemu',settings['QEMU'])]}
write('tools.json',dict(versions=versions,environment=settings,sha256={p:sha(p) for p in [settings['AURORAC'],settings['QEMU'],settings['OVMF']]}))
external=[]
for directory in ('/tmp/aurora-qemu/firmware','/tmp/aurora-clean-ovmf/output','/tmp/aurora-clean-ovmf/provenance','/tmp/aurora-m015-amdvi-control','/tmp/aurora-msix-trace-control/attempt3'):
    external += [p for p in Path(directory).rglob('*') if p.is_file()]
external += [Path(shutil.which(name)).resolve() for name in ('g++','as','ld','objcopy','nm','readelf','python3','bash','make','timeout')]
external += [Path('/tmp/aurora-m014-traces/stock.trace'),Path('/tmp/aurora-m015-profile/events.txt'),Path('/tmp/aurora-m015-coverage.json'),Path('/tmp/aurora-m014-bar-coverage.json'),Path('/tmp/aurora-clean-ovmf/provenance/policy-three-file.patch')]
external += [Path(settings[name]) for name in ('AURORAC','QEMU','OVMF')]
external += [Path('/tmp/aurora-m015-kernel-receipts/results.json')]
external_before={str(p):sha(p) for p in sorted(set(external))};write('external-inputs.json',external_before)
old=json.loads(Path('/tmp/aurora-m015-kernel-receipts/results.json').read_text())
modes=[(x['family'],x['mode']) for x in old['modes']]+[('uefi',m) for m in ('runtime-pin-cancel','runtime-pin-fault','runtime-pin-stale','runtime-pin-exhaust')]
if len(modes)!=162 or len(set(modes))!=162:raise SystemExit('Wrong final mode inventory')
commands=[(['python3',f'scripts/kernel-uefi-{family}-run.py',mode,'--output',str(out/family/mode)] if family in ('bar','ivrs') else ['./scripts/kernel-smoke.sh' if family=='bios' else './scripts/kernel-uefi-smoke.sh',mode]) for family,mode in modes]
write('commands.json',dict(cwd=str(root),started_utc=start,source_manifest_timing='Captured before first build/gate; rechecked after all gates.',commands=commands))
results=[]
for (family,mode),command in zip(modes,commands):
    dest=out/family;dest.mkdir(exist_ok=True);label=mode.lstrip('-');log=dest/(label+'.command.log');started=now()
    with log.open('w') as stream: result=subprocess.run(command,env=env,stdout=stream,stderr=subprocess.STDOUT)
    files={str(log.relative_to(out)):sha(log)}
    base=(root/'build'/('kernel-serial' if mode=='normal' else 'kernel-'+label)) if family=='bios' else root/'build/uefi'/mode
    for suffix in (() if family in ('bar','ivrs') else ('.log','.metadata.json')):
        source=base.with_name(base.name+suffix)
        if source.exists():
            target=dest/(label+suffix);shutil.copyfile(source,target);files[str(target.relative_to(out))]=sha(target)
    results.append(dict(family=family,mode=mode,started_utc=started,completed_utc=now(),command=command,exit_code=result.returncode,result='PASS' if result.returncode==0 else 'FAIL',files=files))
    write('results.json',dict(started_utc=start,completed_utc=now(),distinct_modes=len(results),compiler_sha256=sha(settings['AURORAC']),modes=results))
    print(f'{len(results)}/162 {family} {mode}: {result.returncode}',flush=True)
    if result.returncode:raise SystemExit(result.returncode)
after=inputs();write('source-inputs-after.json',after)
external_after={name:sha(Path(name)) for name in external_before};write('external-inputs-after.json',external_after)
if external_before!=external_after:raise SystemExit('External dependency/control inputs changed')
if after!=before:raise SystemExit('Source inputs changed during final gates')
write('results.json',dict(started_utc=start,completed_utc=now(),distinct_modes=162,bios_distinct=37,uefi_distinct=125,compiler_sha256=sha(settings['AURORAC']),source_inputs_unchanged_at_completion=True,source_input_count=len(before),source_input_manifest_sha256=sha(out/'source-inputs.json'),normal_images_restored=True,independent_new_modes=4,independent_logs=os.environ['AURORA_PIN_REVIEW_RECEIPTS'],modes=results))
(out/'README.txt').write_text('Final exact-source162-mode worker receipts:37 historical BIOS modes using their BIOS/QEMU firmware path; historical UEFI/span and new4 pin modes on packaged OVMF; seven BAR and eleven IVRS modes with their original per-mode firmware profiles. No DMA isolation or hardware publication claim. The AMD control preserves its failed broader whole-run criterion; only its independently reviewed bounded CTRL producer witness supplies coverage. Source/test/build inputs and external tool/firmware/control inputs were captured before first build and rechecked after completion. Parent aggregate acceptance is separate.\n')
write('SHA256.json',{str(p.relative_to(out)):sha(p) for p in sorted(out.rglob('*')) if p.is_file() and p.name!='SHA256.json'})
print('PASS full162; source unchanged; receipts '+str(out),flush=True)
