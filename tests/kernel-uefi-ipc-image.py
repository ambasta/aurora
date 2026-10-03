#!/usr/bin/env python3
from pathlib import Path
import importlib.util
ROOT=Path(__file__).resolve().parents[1]
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
images=load('ipc_images',ROOT/'scripts/kernel-uefi-ipc-images.py')
fixtures=load('image_fixtures',ROOT/'tests/kernel-uefi-user-image.py')
def main():
    positives=0;negative=0
    for base in (images.BASE,images.BASE+4096):
        data,blob,symbols=fixtures.fixture(base);images.verify(data,blob,base,symbols);positives+=1
        failures=[]
        for pc in (base-1,base+128,base+16,base+32,base+40,base+48,base+56,base+8):
            altered=symbols.copy();altered['aurora_probe_pc']=pc;failures.append((data,blob,base,altered))
        for offset in (0,1,88,120,128):
            altered=symbols.copy();altered['aurora_kernel_probe_target']=base+offset;failures.append((data,blob,base,altered))
        changed=blob.copy();changed[80:82]=b'\x0f\x0b';elf=data.copy();elf[4096:]=changed
        altered=symbols.copy();altered['aurora_probe_pc']=base+80
        images.verify(elf,changed,base,altered);positives+=1
        for args in failures:
            try:images.verify(*args)
            except ValueError:negative+=1
            else:raise RuntimeError('Invalid IPC image authority accepted')
    fixtures.main()
    print(f'PASS: IPC image authority {positives} positive and {negative} negative cases')
if __name__=='__main__':main()
