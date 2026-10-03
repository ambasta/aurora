#!/usr/bin/env python3
from pathlib import Path
import importlib.util,struct
spec=importlib.util.spec_from_file_location('images',Path(__file__).resolve().parents[1]/'scripts/kernel-uefi-user-images.py')
images=importlib.util.module_from_spec(spec);spec.loader.exec_module(images)

def fixture(base):
    blob=bytearray([0x90]*128)
    blob[14:18]=b'\xcd\x81\x0f\x0b'
    for at in (32,40,48,56):blob[at:at+2]=b'\x0f\x0b'
    data=bytearray(4096+len(blob));data[:7]=b'\x7fELF\x02\x01\x01'
    struct.pack_into('<HH',data,16,2,62);struct.pack_into('<QQ',data,24,base,64);struct.pack_into('<HH',data,54,56,1)
    struct.pack_into('<IIQQQQQQ',data,64,1,5,4096,base,base,len(blob),len(blob),4096);data[4096:]=blob
    symbols={'aurora_program_entry':base,'aurora_user_main':base+8,'aurora_program_return_pc':base+16,'.Laurora_bounds_trap':base+32,'.Laurora_overflow_trap':base+40,'.Laurora_division_zero_trap':base+48,'.Laurora_shift_count_trap':base+56}
    return data,blob,symbols

def main():
    cases=0;rejected=0
    for base in (images.BASE,images.BASE+4096):
        data,blob,symbols=fixture(base);images.verify(data,blob,base,symbols);cases+=1
        failures=[]
        for length in (0,7,16,63,100):failures.append((data[:length],blob,base,symbols))
        for offset,width,value in ((16,2,3),(18,2,3),(24,8,base+1),(32,8,len(data)),(54,2,55),(56,2,2),(64,4,2),(68,4,7),(80,8,0),(88,8,0),(96,8,4097),(104,8,129)):
            changed=data.copy();changed[offset:offset+width]=value.to_bytes(width,'little');failures.append((changed,blob,base,symbols))
        failures.append((data,blob,0,symbols))
        failures.append((data,blob[:-1],base,symbols))
        for name in symbols:
            changed=symbols.copy();changed[name]=base+4096;failures.append((data,blob,base,changed))
        for name in ('.Laurora_bounds_trap','.Laurora_overflow_trap'):
            changed=symbols.copy();changed[name]=base+16;failures.append((data,blob,base,changed))
        for offset in (1,127,129):
            changed=symbols.copy();changed['aurora_kernel_probe_target']=base+offset;failures.append((data,blob,base,changed))
        changed=blob.copy();changed[16]=0x90;elf=data.copy();elf[4096:]=changed;failures.append((elf,changed,base,symbols))
        for arguments in failures:
            try:images.verify(*arguments)
            except ValueError:rejected+=1
            else:raise RuntimeError('Invalid high-VA user image accepted')
    data,blob,symbols=fixture(images.BASE);blob[88:96]=bytes(8);data[4096:]=blob;symbols['aurora_kernel_probe_target']=images.BASE+88
    images.verify(data,blob,images.BASE,symbols);cases+=1
    print(f'PASS: UEFI user image metadata {cases} positive and {rejected} negative cases')
if __name__=='__main__':main()
