#!/usr/bin/env python3
from pathlib import Path
import importlib.util
root=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('images',root/'scripts/kernel-uefi-ipc-images.py');images=importlib.util.module_from_spec(spec);spec.loader.exec_module(images)
def main():
    positives=0;negatives=0
    spec=importlib.util.spec_from_file_location('payload_image',root/'tests/kernel-uefi-image.py')
    payload=importlib.util.module_from_spec(spec);spec.loader.exec_module(payload)
    direct='  10:\te8 00 00 00 00  \tcall   15 <caller+0x15>\t11: R_X86_64_PLT32\taurora_kernel_budget_tick-0x4'
    for good in (direct,direct.replace('call   ','callq  ')):
        if not payload.budget_call_present(good):raise RuntimeError('Valid direct budget call rejected')
        positives+=1
    for bad in (direct.replace('tick-','tick_fake-'),direct.replace('call   ','jmp    '),
                direct.replace('e8 00','e9 00'),direct.replace('e8 00','ff d0'),
                direct.replace('tick-0x4','tick-0x8'),direct.replace('11: R_','12: R_'),
                direct.replace('15 <','16 <'),direct.replace('R_X86_64_PLT32','R_X86_64_PC32'),
                direct.replace('call   ','syscall '),direct+' trailing',direct.replace('e8 00 00 00 00','e8 01 00 00 00')):
        if payload.budget_call_present(bad):raise RuntimeError('Invalid direct budget call accepted')
        negatives+=1
    for base in (images.BASE,images.BASE+4096):
        blob=bytearray([0x90]*128);blob[24:30]=bytes.fromhex('48ff0c2475fa')
        meta=dict(entry=base,return_pc=base+64,bounds_pc=base+104)
        symbols=dict(aurora_user_main=base+80)
        images.service_metadata(meta,blob,symbols,20);positives+=1
        probe=dict(symbols,aurora_budget_context_begin=base+24,aurora_budget_context_end=base+30)
        images.service_metadata(meta,blob,probe,20);positives+=1
        failures=[]
        for size in (0,-1,True,25,4096,1<<64):failures.append((meta,blob,symbols,size))
        for begin in (0,base,base+64,base+127,base+4096):failures.append((meta,blob,dict(symbols,aurora_user_main=begin),20))
        for begin,end in ((0,base+30),(base+24,0),(base-1,base+30),(base+24,base+65),(base+25,base+30),(base+24,base+31),(base+30,base+24)):
            failures.append((meta,blob,dict(symbols,aurora_budget_context_begin=begin,aurora_budget_context_end=end),20))
        changed=blob.copy();changed[24]=0x90;failures.append((meta,changed,probe,20))
        for args in failures:
            try:images.service_metadata(*args)
            except (ValueError,TypeError):negatives+=1
            else:raise RuntimeError('Invalid timer image interval accepted')
    print(f'PASS: timer image intervals {positives} positive and {negatives} negative cases')
if __name__=='__main__':main()
