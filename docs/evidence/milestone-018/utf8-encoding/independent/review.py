#!/usr/bin/env python3
"""Independent exact-byte native UTF-8 encoder review. No decoder or author oracle.
Python strict encoding is checked against positional arithmetic and Unicode17
Table3-7 on every scalar. Runtime native batches <=8192; full failure preserved.
"""
import argparse, hashlib, json, os, random, resource, struct, subprocess, sys, time
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parent/'aurora-utf8-encoding-next'
PIN='a9448bed52974ca1e690b9a10e86a5f879c5b24f475a12ab1ec079e4e97bc646'
COMPILERS={
 'release':('/tmp/aurora-resource-main-compiler-frozen','14cbaa33b69b81240b5828b6893f4c150eeaa9a11d95a83726d32e417c1f8980'),
 'instrumented':('/tmp/aurora-resource-sanitizer/aurorac','805567b1cac1e535d0951b4ddbc02b598d9bb546bea718f7afb74d482dab94bf')}
TABLE=[(0,0x7f,((0,0x7f),)),(0x80,0x7ff,((0xc2,0xdf),(0x80,0xbf))),
(0x800,0xfff,((0xe0,0xe0),(0xa0,0xbf),(0x80,0xbf))),
(0x1000,0xcfff,((0xe1,0xec),(0x80,0xbf),(0x80,0xbf))),
(0xd000,0xd7ff,((0xed,0xed),(0x80,0x9f),(0x80,0xbf))),
(0xe000,0xffff,((0xee,0xef),(0x80,0xbf),(0x80,0xbf))),
(0x10000,0x3ffff,((0xf0,0xf0),(0x90,0xbf),(0x80,0xbf),(0x80,0xbf))),
(0x40000,0xfffff,((0xf1,0xf3),(0x80,0xbf),(0x80,0xbf),(0x80,0xbf))),
(0x100000,0x10ffff,((0xf4,0xf4),(0x80,0x8f),(0x80,0xbf),(0x80,0xbf)))]
def require(ok,msg):
 if not ok:raise RuntimeError(msg)
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def arithmetic(cp):
 if cp<128:return bytes([cp])
 width=2 if cp<2048 else 3 if cp<65536 else 4
 acc=[]
 while len(acc)<width-1:
  cp,tail=divmod(cp,64);acc.insert(0,128+tail)
 return bytes([256-2**(8-width)+cp]+acc)
def oracle(cp):
 if cp>0x10ffff or 0xd800<=cp<=0xdfff:return 1<<40
 expected=chr(cp).encode('utf-8','strict')
 require(expected==arithmetic(cp),f'Python/arithmetic disagree for {cp:x}')
 matched=False
 for lo,hi,ranges in TABLE:
  if lo<=cp<=hi:
   require(len(expected)==len(ranges),'Table3-7 width')
   require(all(a<=b<=z for b,(a,z) in zip(expected,ranges)),f'Table3-7 range {cp:x}')
   matched=True;break
 require(matched,'missing table row')
 return int.from_bytes(expected.ljust(4,b'\x00'),'little')+(len(expected)<<32)
def validate(output,expected,code):
 require(code==0,f'native exit {code}')
 require(len(output)==len(expected)*8,f'wrong output length {len(output)}')
 for i,(actual,want) in enumerate(zip(struct.iter_unpack('<Q',output),expected)):
  require(actual[0]==want,f'index {i}: got {actual[0]:016x}, expected {want:016x}')
def controls():
 expected=[oracle(cp) for cp in (0,0x7f,0x80,0x7ff,0x800,0xd7ff,0xd800,0xe000,0x10000,0x10ffff,0x110000,2**64-1)]
 require(expected==[1<<32,(1<<32)+0x7f,(2<<32)+0x80c2,(2<<32)+0xbfdf,(3<<32)+0x80a0e0,(3<<32)+0xbf9fed,1<<40,(3<<32)+0x8080ee,(4<<32)+0x808090f0,(4<<32)+0xbfbf8ff4,1<<40,1<<40],'literal anchors mismatch')
 good=struct.pack('<'+'Q'*len(expected),*expected);validate(good,expected,0)
 for data,code in ((good[:-1],0),(good+b'x',0),(good,1),(good,-4),(bytes([good[0]^1])+good[1:],0)):
  try:validate(data,expected,code)
  except RuntimeError:continue
  raise RuntimeError('harness accepted bad output')
 print('PASS active Python -O controls',flush=True)
def command(args,outdir,name,inbytes=None,compiler=False,instrumented=False):
 cap=None if compiler and instrumented else (512 if compiler else 128)<<20
 def limits():
  resource.setrlimit(resource.RLIMIT_CORE,(0,0));resource.setrlimit(resource.RLIMIT_CPU,(10,11))
  resource.setrlimit(resource.RLIMIT_FSIZE,(8<<20,8<<20))
  if cap is not None:resource.setrlimit(resource.RLIMIT_AS,(cap,cap))
 receipt={'command':list(map(str,args)),'address_cap':cap,'cpu':[10,11],'file_cap':8<<20,'wall_seconds':30,'started':time.time()}
 env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0:halt_on_error=1')
 try:
  with (outdir/(name+'.stdout')).open('wb') as o,(outdir/(name+'.stderr')).open('wb') as e:
   p=subprocess.run(list(map(str,args)),input=inbytes,stdout=o,stderr=e,timeout=30,preexec_fn=limits,env=env)
  receipt['exit_code']=p.returncode
  require(p.returncode==0,f'{name} failed: {p.returncode}; see {outdir}')
  require(not (outdir/(name+'.stderr')).read_bytes(),f'{name} stderr')
  return (outdir/(name+'.stdout')).read_bytes()
 except Exception as err:
  receipt['error']=str(err);raise
 finally:
  receipt['seconds']=time.time()-receipt['started'];(outdir/(name+'.json')).write_text(json.dumps(receipt,indent=2)+'\n')
def run(mode):
 path,pin=COMPILERS[mode];require(digest(path)==pin,'compiler pin');require(digest(ROOT/'library/std/utf8.au')==PIN,'library pin')
 out=HERE/mode;out.mkdir();cmd=[path,'--module-root',ROOT/'library',HERE/'observe.au','-o',out/'compiled.s']
 command(cmd,out,'compile',compiler=True,instrumented=mode=='instrumented')
 command(['g++','-std=c++17','-O2','-Wall','-Wextra','-Werror','-no-pie',HERE/'driver.cpp',out/'compiled.s','-o',out/'native'],out,'link')
 total=0;valid=0;failures=0;batch=[];group='';receipts=[];stream=hashlib.sha256()
 def flush():
  nonlocal total,valid,failures,batch
  if not batch:return
  index=len(receipts);expected=[oracle(x) for x in batch];raw=struct.pack('<'+'Q'*len(batch),*batch)
  name=f'batch-{index:03d}';(out/(name+'.input')).write_bytes(raw)
  data=command([out/'native'],out,name,raw)
  try:validate(data,expected,0)
  except Exception:
   (out/(name+'.expected')).write_bytes(struct.pack('<'+'Q'*len(batch),*expected));raise
  stream.update(data);total+=len(batch);valid+=sum(x<1<<40 for x in expected);failures+=sum(x==1<<40 for x in expected)
  receipts.append({'group':group,'size':len(batch),'first':batch[0],'last':batch[-1],'input_sha256':hashlib.sha256(raw).hexdigest(),'output_sha256':hashlib.sha256(data).hexdigest()});batch=[]
 group='complete Unicode range including every surrogate'
 for cp in range(0x110000):
  batch.append(cp)
  if len(batch)==8192:flush()
 flush();print(f'PASS {mode} all 1112064 scalars plus 2048 surrogates',flush=True)
 group='above-range contiguous prefix'
 for cp in range(0x110000,0x111000):batch.append(cp)
 flush()
 group='u64 boundaries and deterministic wide values';rng=random.Random(173640)
 batch=[2**64-1,2**64-2,2**63,2**63-1,2**32,2**32-1]+[x for n in range(21,64) for x in (2**n-1,2**n,2**n+1)]
 batch.extend(rng.getrandbits(64) for _ in range(4096));flush()
 require(digest(ROOT/'library/std/utf8.au')==PIN,'post-run library pin');require(digest(path)==pin,'post-run compiler pin')
 summary={'mode':mode,'compiler_sha256':pin,'library_sha256':PIN,'cases':total,'success':valid,'invalid':failures,'batches':receipts,'output_sha256':stream.hexdigest(),'native_sha256':digest(out/'native'),'assembly_sha256':digest(out/'compiled.s'),'limits':'Each <=8192 native cases, 10/11s CPU,30s wall,128MiB AS,8MiB file; compiler512MiB except instrumented AS uncapped; stderr must be empty'}
 (out/'results.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps({k:v for k,v in summary.items() if k!='batches'}),flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('mode',choices=['release','instrumented','self-test']);a=p.parse_args();controls()
 if a.mode!='self-test':run(a.mode)
