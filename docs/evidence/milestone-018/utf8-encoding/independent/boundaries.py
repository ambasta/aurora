#!/usr/bin/env python3
"""Independent compile-negative and actual exact-UD2 copied-array bounds checks."""
import json,os,resource,signal,struct,subprocess,sys,time
from pathlib import Path
from review import HERE,ROOT,PIN,COMPILERS,require,digest,command
PREFIX='module independent_negative;import std.utf8;import std.array;'
BASE='const std::Utf8EncodeResult r=std::encode_utf8(65u64);'
NEGATIVES={
'private_payload':('auto test()->u8{'+BASE+'return r.payload;}',('private',)),
'private_status':('auto test()->std::Utf8EncodeStatus{'+BASE+'return r.outcome;}',('private',)),
'private_width':('auto test()->i64{'+BASE+'return r.byte_width;}',('private',)),
'wrong_scalar_i64':('auto test()->i64{const std::Utf8EncodeResult r=std::encode_utf8(65);return r.size();}',('type',)),
'wrong_scalar_u8':('auto test()->i64{const std::Utf8EncodeResult r=std::encode_utf8(65u8);return r.size();}',('type',)),
'wrong_index_u64':('auto test()->u8{'+BASE+'return r.byte_or(0u64,0u8);}',('type',)),
'wrong_fallback_i64':('auto test()->u8{'+BASE+'return r.byte_or(0,0);}',('type',)),
'wrong_width_u64':('auto test()->i64{const std::array<u8,4> b=std::array<u8,4>();const std::Utf8EncodeResult r=std::Utf8EncodeResult(std::Utf8EncodeStatus::success,b,1u64);return r.size();}',('type',)),
'wrong_status_nominal':('auto test()->i64{const std::array<u8,4> b=std::array<u8,4>();const std::Utf8EncodeResult r=std::Utf8EncodeResult(std::Utf8Status::success,b,1);return r.size();}',('type',)),
'wrong_array_capacity':('auto test()->i64{const std::array<u8,3> b=std::array<u8,3>();const std::Utf8EncodeResult r=std::Utf8EncodeResult(std::Utf8EncodeStatus::success,b,1);return r.size();}',('type',)),
'wrong_array_element':('auto test()->i64{const std::array<u64,4> b=std::array<u64,4>();const std::Utf8EncodeResult r=std::Utf8EncodeResult(std::Utf8EncodeStatus::success,b,1);return r.size();}',('type',)),
'cannot_convert_enum':('auto test()->i64{'+BASE+'return i64(r.status());}',('conversion',)),
'cannot_forge_numeric_status':('auto test()->i64{const std::Utf8EncodeStatus s=2;return 0;}',('type',)),
'const_copy_mutation':('auto test()->i64{'+BASE+'const std::array<u8,4> b=r.bytes_or_zero();b.set(0,0u8);return 0;}',('const',)),
'nominal_result_substitution':('class Pretend{public:i64 a;i64 b;i64 c;};auto test()->i64{const Pretend p=std::encode_utf8(65u64);return 0;}',('type',)),
'not_array_reference':('auto test()->i64{'+BASE+'const std::array<u8,4>& b=r.bytes_or_zero();return 0;}',()),
'no_direct_chained_mutation':('auto test()->i64{'+BASE+'r.bytes_or_zero().set(0,0u8);return 0;}',()),
'private_constructor_payload_mutation':('auto test()->i64{std::Utf8EncodeResult r=std::encode_utf8(65u64);r.payload.set(0,0u8);return 0;}',()),
}
# Reference declaration/chaining rejections cover unsupported shapes; they are not
# claimed to be dedicated ownership diagnostics.
def run_process(args,where,name,instrumented=False,compiler=False):
 cap=None if compiler and instrumented else (512 if compiler else 128)<<20
 def limits():
  resource.setrlimit(resource.RLIMIT_CORE,(0,0));resource.setrlimit(resource.RLIMIT_CPU,(10,11));resource.setrlimit(resource.RLIMIT_FSIZE,(8<<20,8<<20))
  if cap is not None:resource.setrlimit(resource.RLIMIT_AS,(cap,cap))
 env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0:halt_on_error=1');start=time.monotonic()
 receipt={'command':list(map(str,args)),'cpu_limit':[10,11],'as_limit':cap,'file_limit':8<<20,'wall_limit':30}
 try:
  with (where/(name+'.stdout')).open('wb') as out,(where/(name+'.stderr')).open('wb') as err:
   p=subprocess.run(list(map(str,args)),stdout=out,stderr=err,timeout=30,env=env,preexec_fn=limits)
  receipt['exit_code']=p.returncode;return p.returncode,(where/(name+'.stdout')).read_bytes(),(where/(name+'.stderr')).read_bytes()
 except Exception as err:receipt['error']=str(err);raise
 finally:receipt['seconds']=time.monotonic()-start;(where/(name+'.json')).write_text(json.dumps(receipt,indent=2)+'\n')
def fault_check(code,out,err,address):
 require(code==-signal.SIGILL,'wrong terminating signal');require(not out,'unexpected native output');require(len(err)==40,'fault record size')
 magic,delivered,pc,instruction,si=struct.unpack('<QQQQq',err)
 require(magic==0x4155524f52414654,'magic');require(delivered==signal.SIGILL,'wrong delivered signal');require(pc==address,'wrong trap PC');require(instruction==0xb0f,'not UD2');require(si>0,'not kernel-generated')
def controls():
 good=struct.pack('<QQQQq',0x4155524f52414654,signal.SIGILL,4096,0xb0f,2);fault_check(-signal.SIGILL,b'',good,4096)
 for code,out,err,address in [(-signal.SIGSEGV,b'',good,4096),(-signal.SIGILL,b'',good,8192),(-signal.SIGILL,b'x',good,4096),(-signal.SIGILL,b'',good[:-1],4096),(0,b'',good,4096)]:
  try:fault_check(code,out,err,address)
  except RuntimeError:continue
  raise RuntimeError('fault validator accepted corrupt result')
def run(mode):
 controls();path,pin=COMPILERS[mode];require(digest(path)==pin,'compiler pin');require(digest(ROOT/'library/std/utf8.au')==PIN,'library pin')
 out=HERE/('boundaries-'+mode);out.mkdir();records=[]
 for name,(body,diagnostics) in NEGATIVES.items():
  d=out/name;d.mkdir();(d/'input.au').write_text(PREFIX+body+'\n')
  code,stdout,stderr=run_process([path,'--module-root',ROOT/'library',d/'input.au','-o',d/'compiled.s'],d,'compile',compiler=True,instrumented=mode=='instrumented')
  require(code>0,f'{name}: not ordinary rejection');require(stderr,f'{name}: empty diagnostic');require(not (d/'compiled.s').exists(),f'{name}: emitted assembly')
  # Record diagnostic, but avoid mistaking a related typechecking phrase for a
  # distinct specified public error code. Required authorization/privacy checks
  # must explicitly say private; other fixtures are reviewed from retained text.
  if name in ('private_payload','private_status','private_width'):require(b'private' in stderr,f'{name}: wrong privacy diagnostic')
  records.append({'name':name,'kind':'reject','code':code,'diagnostic':stderr.decode()})
 observer=out/'observer.o'
 command(['g++','-std=c++17','-O2','-Wall','-Wextra','-Werror','-ffreestanding','-fno-exceptions','-fno-rtti','-fno-stack-protector','-fno-pie','-c',ROOT/'tests/compiler/integer_signal.cpp','-o',observer],out,'observer')
 for scalar in (0,0xd800):
  for index in (-2**63,-1,4,2**63-1):
   for op in ('at','set'):
    name=f'{scalar}-{index}-{op}';d=out/name;d.mkdir()
    expr=f'return u64(b.at({index}));' if op=='at' else f'b.set({index},19u8);return 0u64;'
    (d/'input.au').write_text(PREFIX+f'auto test()->u64{{const std::Utf8EncodeResult r=std::encode_utf8({scalar}u64);std::array<u8,4> b=r.bytes_or_zero();{expr}}}\n')
    command([path,'--module-root',ROOT/'library',d/'input.au','-o',d/'compiled.s'],d,'compile',compiler=True,instrumented=mode=='instrumented')
    (d/'entry.s').write_text('.text\n.globl _start\n_start:\n call aurora_install_integer_signal_observer\n test %rax,%rax\n jne .Lfail\n call test\n.Lfail:\n mov $60,%rax\n mov $7,%rdi\n syscall\n.section .note.GNU-stack,"",@progbits\n')
    command(['as','--64','-L',d/'compiled.s','-o',d/'program.o'],d,'assemble')
    command(['as','--64',d/'entry.s','-o',d/'entry.o'],d,'entry')
    command(['ld','-o',d/'native',d/'entry.o',d/'program.o',observer],d,'link')
    symbols=command(['nm','-a',d/'native'],d,'symbols').decode();lines=[s.split() for s in symbols.splitlines() if s.endswith(' .Laurora_bounds_trap')];require(len(lines)==1,'unique bounds label')
    address=int(lines[0][0],16);code,stdout,stderr=run_process([d/'native'],d,'native');fault_check(code,stdout,stderr,address)
    records.append({'name':name,'kind':'exact_bounds_trap','exit':code,'pc':address})
 summary={'mode':mode,'rejections':len(NEGATIVES),'exact_bounds_traps':16,'compiler_sha256':pin,'library_sha256':PIN,'records':records}
 (out/'results.json').write_text(json.dumps(summary,indent=2)+'\n');print(f'PASS {mode}: {len(NEGATIVES)} rejections,16 exact-site native bounds traps',flush=True)
if __name__=='__main__':run(sys.argv[1])
