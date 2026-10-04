#!/usr/bin/env python3
import hashlib,json,os,resource,struct,subprocess,sys,time
from pathlib import Path
D=Path(__file__).resolve().parent;R=D.parent/'aurora-utf8-next'
COMPILERS={'release':'/tmp/aurora-resource-main-compiler-frozen','instrumented':'/tmp/aurora-resource-sanitizer/aurorac'}
ENV=dict(os.environ,ASAN_OPTIONS='detect_leaks=0:halt_on_error=1',UBSAN_OPTIONS='halt_on_error=1')

def require(x,msg):
 if not x:raise RuntimeError(msg)

def command(args,seconds=30,**kwargs):
 def limits():
  resource.setrlimit(resource.RLIMIT_CORE,(0,0))
  resource.setrlimit(resource.RLIMIT_CPU,(20,20))
  resource.setrlimit(resource.RLIMIT_FSIZE,(64*1024*1024,64*1024*1024))
  if len(args)==1:resource.setrlimit(resource.RLIMIT_AS,(256*1024*1024,256*1024*1024))
 result=subprocess.run(args,capture_output=True,timeout=seconds,env=ENV,preexec_fn=limits,**kwargs)
 return result

def scalar_checks(d,status,value,width):
 return f'if({d}.status()!=std::Utf8Status::{status}){{return 1u64;}}if({d}.scalar_or(2097151u64)!={value}u64){{return 2u64;}}if({d}.width()!={width}){{return 3u64;}}'

def validator_checks(v,status,count,scalars):
 return f'if({v}.status()!=std::Utf8Status::{status}){{return 4u64;}}if({v}.prefix_bytes()!={count}){{return 5u64;}}if({v}.scalar_count()!={scalars}){{return 6u64;}}'

def cap_body(n):
 out='builtin::array<u8,'+str(n)+'> a={'+','.join('0u8' for _ in range(n))+'};'
 out+=f'i64 i=0;while(i<{n}){{a[i]=127u8;i=i+1;}}'
 out+='{const builtin::span<const u8> v=borrow_bytes(a);'
 out+=f'const std::Utf8ValidationResult r=std::validate_utf8(v,0,{n},true);'+validator_checks('r','success',n,n)
 out+=f'const std::Utf8DecodeResult d=std::decode_utf8(v,{n-1},1,true);'+scalar_checks('d','success',127,1)
 out+=f'const std::Utf8DecodeResult e=std::decode_utf8(v,{n},0,false);'+scalar_checks('e','end_of_input',2097151,0)
 out+=f'const std::Utf8ValidationResult z=std::validate_utf8(v,{n},0,false);'+validator_checks('z','success',0,0)+'}'
 out+=f'a[{n-1}]=224u8;'
 out+='{const builtin::span<const u8> v=borrow_bytes(a);'
 out+=f'const std::Utf8ValidationResult r=std::validate_utf8(v,0,{n},false);'+validator_checks('r','need_more',n-1,n-1)
 out+=f'const std::Utf8ValidationResult r2=std::validate_utf8(v,0,{n},true);'+validator_checks('r2','truncated',n-1,n-1)+'}'
 if n>=3:
  out+=f'a[{n-3}]=224u8;a[{n-2}]=160u8;a[{n-1}]=128u8;'
  out+='{const builtin::span<const u8> v=borrow_bytes(a);'
  out+=f'const std::Utf8ValidationResult r=std::validate_utf8(v,0,{n},false);'+validator_checks('r','success',n,n-2)
  out+=f'const std::Utf8ValidationResult t=std::validate_utf8(v,0,{n-1},false);'+validator_checks('t','need_more',n-3,n-3)
  out+=f'const std::Utf8DecodeResult d=std::decode_utf8(v,{n-3},3,true);'+scalar_checks('d','success',2048,3)+'}'
  out+=f'a[{n-2}]=128u8;'
  out+='{const builtin::span<const u8> v=borrow_bytes(a);'
  out+=f'const std::Utf8ValidationResult r=std::validate_utf8(v,0,{n-1},false);'+validator_checks('r','invalid_sequence',n-3,n-3)+'}'
 if n>=4:
  out+=f'a[{n-4}]=244u8;a[{n-3}]=143u8;a[{n-2}]=191u8;a[{n-1}]=191u8;'
  out+='{const builtin::span<const u8> v=borrow_bytes(a);'
  out+=f'const std::Utf8ValidationResult r=std::validate_utf8(v,0,{n},false);'+validator_checks('r','success',n,n-3)
  out+=f'const std::Utf8DecodeResult d=std::decode_utf8(v,{n-4},4,true);'+scalar_checks('d','success',1114111,4)+'}'
 out+='a[0]=42u8;if(a[0]!=42u8){return 7u64;}return 42u64;'
 return out

def reports_body():
 out=''
 for ix,scalar in enumerate((55296,57343,1114112,18446744073709551615)):
  out+=f'const std::Utf8DecodeResult d{ix}=std::Utf8DecodeResult(std::Utf8Status::success,{scalar}u64,-9223372036854775808);'
  out+=scalar_checks(f'd{ix}','success',2097151,'-9223372036854775808')
 out+='const std::Utf8DecodeResult e=std::Utf8DecodeResult(std::Utf8Status::invalid_sequence,65u64,9223372036854775807);'+scalar_checks('e','invalid_sequence',2097151,0)
 out+='const std::Utf8ValidationResult v=std::Utf8ValidationResult(std::Utf8Status::success,-9223372036854775808,9223372036854775807);'+validator_checks('v','success','-9223372036854775808','9223372036854775807')
 out+='const std::Utf8DecodeResult ok=std::Utf8DecodeResult(std::Utf8Status::success,65u64,800);'+scalar_checks('ok','success',65,800)
 out+='return 42u64;';return out

def rejection_cases():
 prefix='builtin::array<u8,4> a={65u8,66u8,67u8,68u8};const builtin::span<const u8> v=borrow_bytes(a);'
 yield 'unsigned_offset',prefix+'const std::Utf8DecodeResult r=std::decode_utf8(v,0u64,4,true);return 42u64;'
 yield 'unsigned_count',prefix+'const std::Utf8DecodeResult r=std::decode_utf8(v,0,4u64,true);return 42u64;'
 yield 'numeric_final',prefix+'const std::Utf8DecodeResult r=std::decode_utf8(v,0,4,1);return 42u64;'
 yield 'private_decode_field',prefix+'const std::Utf8DecodeResult r=std::decode_utf8(v,0,4,true);return r.scalar;'
 yield 'private_validation_field',prefix+'const std::Utf8ValidationResult r=std::validate_utf8(v,0,4,true);return u64(r.complete_bytes);'
 yield 'unexported_helper','const std::Utf8DecodeResult r=std::utf8_failure(std::Utf8Status::success);return 42u64;'
 yield 'owner_write_during_borrow',prefix+'a[0]=0u8;const std::Utf8DecodeResult r=std::decode_utf8(v,0,4,true);return 42u64;'
 yield 'invalid_span_element','builtin::array<i64,4> a={65,66,67,68};const builtin::span<const u8> v=borrow_bytes(a);return 42u64;'
 yield 'missing_final',prefix+'const std::Utf8DecodeResult r=std::decode_utf8(v,0,4);return 42u64;'

results=[]
for build,compiler in COMPILERS.items():
 for name,body in [('reports_are_plain_values',reports_body())]+[(f'capacity_{n}',cap_body(n)) for n in (1,3,4,8,64,4096)]:
  sub=D/(build+'-'+name);sub.mkdir(exist_ok=True)
  src='module independent_fixture;import std.utf8;auto review(u64 x,i64 y,i64 z,bool f)->u64{'+body+'}\n';(sub/'fixture.au').write_text(src)
  args=[compiler,'--module-root',str(R/'library'),str(sub/'fixture.au'),'-o',str(sub/'fixture.s')]
  run=command(args);(sub/'compiler.stderr').write_bytes(run.stderr);require(run.returncode==0,f'{name} compile failed {run.stderr!r}')
  run=command(['c++','-O2','-Wall','-Wextra','-Werror','-no-pie',str(D/'driver.cpp'),str(sub/'fixture.s'),'-o',str(sub/'fixture')]);require(run.returncode==0,f'{name} host bridge failed {run.stderr!r}')
  run=command([str(sub/'fixture')],input=struct.pack('<QqqQ',0,0,0,0));require(run.returncode==0 and run.stdout==struct.pack('<Q',42) and not run.stderr,f'{name} native failed {run}')
  entry={'build':build,'name':name,'outcome':'pass','source_sha256':hashlib.sha256(src.encode()).hexdigest(),'compile_command':args};results.append(entry);print('PASS',build,name,flush=True)
 for name,body in rejection_cases():
  sub=D/(build+'-reject-'+name);sub.mkdir(exist_ok=True);src='module independent_rejection;import std.utf8;auto review()->u64{'+body+'}\n';(sub/'fixture.au').write_text(src)
  for existing in (False,True):
   out=sub/'fixture.s';out.unlink(missing_ok=True);sentinel=b'preserve rejected output\x00\xff'
   if existing:out.write_bytes(sentinel)
   args=[compiler,'--module-root',str(R/'library'),str(sub/'fixture.au'),'-o',str(out)]
   run=command(args);(sub/('compiler-existing.stderr' if existing else 'compiler-absent.stderr')).write_bytes(run.stderr)
   require(run.returncode==1 and run.stderr.startswith(b'aurorac:'),f'{name} did not normally reject: {run}')
   require(out.read_bytes()==sentinel if existing else not out.exists(),f'{name} changed rejected output')
  results.append({'build':build,'name':name,'outcome':'rejected_preserved_absent_and_existing_output','diagnostic':run.stderr.decode(),'compile_command':args});print('PASS',build,'reject',name,run.stderr.decode().strip(),flush=True)
(D/'fixtures-results.json').write_text(json.dumps(results,indent=2)+'\n')
print('PASS TOTAL',len(results),'groups')
