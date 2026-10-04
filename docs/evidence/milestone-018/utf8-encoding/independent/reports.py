#!/usr/bin/env python3
import itertools,json,struct,sys
from pathlib import Path
from review import HERE,ROOT,PIN,COMPILERS,command,digest,require,validate
M=2**63-1;N=-2**63
widths=(N,-99,-1,0,1,2,3,4,5,6,99,M)
indices=(N,-100,-1,0,1,2,3,4,5,100,M)
patterns=(0,0xffffffff,0x04030201,0xff000000,0x000000ff,0x80808080,0x00bf80c0,0x00bfa0ed,0xbfbf90f4,0x41414141)
def expected(packed,width,good,index):
 size=width if good and 1<=width<=4 else 0
 b=packed.to_bytes(8,'little')[:4];body=b[:size].ljust(4,b'\0');fallback=(packed>>32)&255
 value=b[index] if 0<=index<size else fallback
 return int.from_bytes(body,'little')+(size<<32)+(int(size==0)<<40)+(value<<48)
def cases():
 for raw,width,good,index in itertools.product(patterns,widths,(False,True),indices):
  fallback=(raw+width+index)%256
  yield raw+(fallback<<32),width,good,index
 # Each possible byte and fallback, each legal width; malformed success prefix allowed.
 for v,width,index in itertools.product(range(256),range(1,5),(-1,0,1,2,3,4)):
  yield v*0x01010101+(v<<32),width,True,index

def run(mode):
 path,pin=COMPILERS[mode];require(digest(path)==pin,'compiler pin');require(digest(ROOT/'library/std/utf8.au')==PIN,'library pin')
 out=HERE/('reports-'+mode);out.mkdir()
 command([path,'--module-root',ROOT/'library',HERE/'reports.au','-o',out/'compiled.s'],out,'compile',compiler=True,instrumented=mode=='instrumented')
 command(['g++','-std=c++17','-O2','-Wall','-Wextra','-Werror','-no-pie',HERE/'reports-driver.cpp',out/'compiled.s','-o',out/'native'],out,'link')
 values=list(cases());require(len(values)==8784,'case count')
 for start in range(0,len(values),2048):
  batch=values[start:start+2048];raw=b''.join(struct.pack('<QqQq',*x) for x in batch);name=f'batch-{start//2048:02d}'
  (out/(name+'.input')).write_bytes(raw);data=command([out/'native'],out,name,raw)
  wants=[expected(*x) for x in batch]
  try:validate(data,wants,0)
  except Exception:
   (out/(name+'.expected')).write_bytes(struct.pack('<'+'Q'*len(batch),*wants));raise
 summary={'cases':len(values),'compiler_sha256':pin,'library_sha256':PIN,'source_sha256':digest(HERE/'reports.au'),'assembly_sha256':digest(out/'compiled.s'),'binary_sha256':digest(out/'native')}
 (out/'results.json').write_text(json.dumps(summary,indent=2)+'\n');print('PASS',mode,'reports/copies/ABI',json.dumps(summary),flush=True)
if __name__=='__main__':run(sys.argv[1])
