#!/usr/bin/env python3
"""Verify measured inherited BME refusal; this is not a positive BAR grant gate."""
from pathlib import Path
import importlib.util,re,sys
spec=importlib.util.spec_from_file_location('pci',Path(__file__).with_name('kernel-pci-smoke.py'))
pci=importlib.util.module_from_spec(spec);spec.loader.exec_module(pci)
def validate(status,text):
    if status!=35:raise ValueError('Expected fail-closed admission exit')
    lines=text.splitlines();indices=[i for i,line in enumerate(lines) if line.startswith('AURORA_BAR_ADMISSION:')]
    if len(indices)!=1:raise ValueError('Exactly one measured target required')
    at=indices[0];prefix='\n'.join(lines[:at])+'\n'
    # Validate the already completed read-only PCI inventory independently. The
    # synthetic suffix is local validator input, never evidence of later execution.
    pci.validate(33,prefix+'AURORA_UEFI_LANGUAGE_OK: value=42\nAURORA_UEFI_OK\n','pci')
    tail=lines[at:]
    if len(tail)!=2 or tail[1]!='AURORA_UEFI_PAYLOAD_FAIL: ACPI discovery':raise ValueError('Execution continued after admission refusal')
    match=re.fullmatch(r'AURORA_BAR_ADMISSION: segment=(\d+) bus=(\d+) device=(\d+) function=(\d+) command=(\d+) grant=0 reason=bus-master-enabled',tail[0])
    if not match:raise ValueError('Missing exact inactive-grant refusal')
    segment,bus,device,function,command=map(int,match.groups())
    if segment!=0 or bus>255 or device>31 or function>7 or command!=7:raise ValueError('Unexpected measured fixture state')
    target=f'AURORA_PCI_FUNCTION: segment={segment} bus={bus} device={device} function={function} vendor=6966 product=16 class=1 subclass=8 interface=2 header=0 command={command} secondary=0 subordinate=0'
    matches=[line for line in lines[:at] if 'vendor=6966 product=16 class=1 subclass=8 interface=2' in line]
    if matches!=[target]:raise ValueError('Admission identity differs from current inventory')
if __name__=='__main__':
    try:validate(int(sys.argv[1]),Path(sys.argv[2]).read_text())
    except (ValueError,IndexError) as error:raise SystemExit('FAIL: '+str(error))
    print('PASS: actual inherited bus-master state rejected; no BAR grant')
