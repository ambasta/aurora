#!/usr/bin/env python3
"""Cold, namespace-free emulator IVRS receipts; never used for historical gates."""
import argparse, hashlib, importlib.util, json, os, shutil, subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
MODES=('ivrs-default','ivrs-read','ivrs-write','ivrs-revoked','ivrs-pair','ivrs-alias','ivrs-reserved','ivrs-scope','ivrs-capability','ivrs-range','ivrs-missing')
def module(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/'tests'/f'kernel-uefi-{name}.py')
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result
def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def record(path):return dict(path=str(Path(path).resolve()),sha256=digest(path))
def run(mode,out):
    out=out.resolve();out.mkdir(parents=True,exist_ok=False)
    env=os.environ.copy();env['UEFI_MODE']=mode
    compiler=Path(env.get('AURORAC',ROOT/'build/aurorac')).resolve()
    qemu=Path(env['QEMU']).resolve();data=Path(env['QEMU_DATA']).resolve()
    fixture=Path(env['AURORA_IVRS_FIRMWARE']).resolve()
    coverage_path=Path(env['AURORA_IVRS_COVERAGE']).resolve()
    coverage=module('ivrs-trace').load_coverage(coverage_path)
    events=Path(json.loads(coverage_path.read_text())['events'])
    if not events.is_absolute():events=coverage_path.parent/events
    with (out/'build.log').open('w') as log:
        subprocess.run([ROOT/'scripts/kernel-uefi-build.sh'],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
    shutil.copytree(ROOT/'build/uefi/esp',out/'esp')
    shutil.copy2(ROOT/'build/uefi/ivrs-stack.json',out/'stack-usage.json')
    for name in ('pci','acpi','payload'):shutil.copy2(ROOT/'build/uefi'/(name+'.su'),out/(name+'.su'))
    files={name:record(path) for name,path in [('qemu',qemu),('events',events),('compiler',compiler),('coverage',coverage_path)]}
    for key,name in [('payload','payload.bin'),('payload_elf','payload.elf'),('payload_metadata','ivrs-metadata.json')]:
        shutil.copy2(ROOT/'build/uefi'/name,out/name);files[key]=record(out/name)
    files['loader']=record(out/'esp/EFI/BOOT/BOOTX64.EFI')
    clean=True
    argv=[str(qemu),'-L',str(data),'-machine','q35','-accel','tcg','-cpu','qemu64','-smp','1','-m','128M']
    if clean:
        code=fixture/'output/OVMF_CODE.fd';template=fixture/'output/OVMF_VARS.fd'
        for name in ('vars-initial.fd','vars-runtime.fd'):shutil.copy2(template,out/name)
        files.update(firmware_code=record(code),vars_template=record(template),vars_initial=record(out/'vars-initial.fd'),firmware_patch=record(fixture/'provenance/policy-three-file.patch'))
        argv+=['-drive',f'if=pflash,format=raw,unit=0,file={code},readonly=on','-drive',f'if=pflash,format=raw,unit=1,file={out}/vars-runtime.fd']
    else:
        code=Path(env['OVMF']).resolve();files['firmware_code']=record(code);argv+=['-bios',str(code)]
    argv+=['-drive',f'format=raw,file=fat:ro:{out}/esp,snapshot=on','-device','nvme,serial=AURORA_READ_ONLY,bus=pcie.0,addr=02.0','-nic','none','-display','none','-serial','stdio','-monitor','none','-no-reboot','-trace',f'events={events},file={out}/trace.log','-chardev',f'file,id=firmware,path={out}/firmware.log','-device','isa-debugcon,iobase=0x402,chardev=firmware','-device','isa-debug-exit,iobase=0xf4,iosize=0x04']
    if mode!='ivrs-missing':argv+=['-device','amd-iommu,pt=off,intremap=off,device-iotlb=off,xtsup=off']
    invocation=dict(schema='aurora-ivrs-run-v1',mode=mode,argv=argv,cwd=str(ROOT),environment={'LD_LIBRARY_PATH':env.get('LD_LIBRARY_PATH','')},firmware_profile='clean' if clean else 'stock',boot_root=str(out/'esp'),stdio={'stdout':str(out/'serial.log'),'stderr':'stdout'},files=files)
    invocation['iommu_profile']='architectural' if mode=='ivrs-default' else 'qemu-10.0.13-cold'
    if clean:invocation['firmware_source_revision']='fbe0805b2091393406952e84724188f8c1941837'
    (out/'invocation-start.json').write_text(json.dumps(invocation,indent=2)+'\n')
    with (out/'serial.log').open('w') as log:
        try:status=subprocess.run(argv,cwd=ROOT,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,timeout=60).returncode
        except subprocess.TimeoutExpired:status=124
    (out/'status').write_text(str(status)+'\n');invocation['status']=status
    for key,name in [('serial','serial.log'),('trace','trace.log'),('firmware_log','firmware.log')]:files[key]=record(out/name)
    if clean:files['vars_after']=record(out/'vars-runtime.fd')
    (out/'receipt.json').write_text(json.dumps(invocation,indent=2)+'\n')
    serial=(out/'serial.log').read_text();print(serial,end='')
    metadata=json.loads((out/'ivrs-metadata.json').read_text())
    module('ivrs-smoke').validate(status,serial,mode,metadata)
    result=module('ivrs-trace').validate_trace((out/'trace.log').read_text(),(out/'firmware.log').read_text(),serial,mode,coverage,metadata)
    (out/'trace-result.json').write_text(json.dumps(result,indent=2)+'\n')
    module('ivrs-provenance').validate(out/'receipt.json')
    print(f'PASS: actual cold IVRS gate {mode}; receipt {out}/receipt.json')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=MODES);p.add_argument('--output',required=True);a=p.parse_args()
    try:run(a.mode,Path(a.output))
    finally:
        subprocess.run([ROOT/'scripts/kernel-uefi-build.sh'],cwd=ROOT,env=dict(os.environ,UEFI_MODE='normal'),stdout=subprocess.DEVNULL,check=True)
