#!/usr/bin/env python3
import datetime,hashlib,json,pathlib,resource,subprocess
ROOT=pathlib.Path(__file__).resolve().parents[3]
OUT=pathlib.Path(__file__).resolve().parent
FROZEN=[ROOT/'tests/compiler/method_values.py',ROOT/'tests/compiler/method_values_ir.cpp',ROOT/'tests/compiler/method_values_abi.py']
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
source_pins={str(p.relative_to(ROOT)):sha(p) for p in FROZEN}
def require(value,message):
 if not value:raise AssertionError(message)
def run(command,sanitized=False):
 def limits():
  resource.setrlimit(resource.RLIMIT_CORE,(0,0));resource.setrlimit(resource.RLIMIT_CPU,(20,20));resource.setrlimit(resource.RLIMIT_FSIZE,(32*1024**2,32*1024**2))
  if not sanitized:resource.setrlimit(resource.RLIMIT_AS,(384*1024**2,384*1024**2))
 env=__import__('os').environ.copy()
 env['ASAN_OPTIONS']='detect_leaks=0:halt_on_error=1:abort_on_error=1'
 env['UBSAN_OPTIONS']='halt_on_error=1:abort_on_error=1:print_stacktrace=1'
 return subprocess.run(list(map(str,command)),capture_output=True,timeout=25,preexec_fn=limits,env=env)
PREFIX='module audit;class Value{public:i64 value;};class Receiver{public:Receiver(){}auto inspect(Value source)const->i64{return source.value;}};'
CASES=[('actual-mutref-method-parameter','module audit;class Receiver{public:Receiver(){}auto inspect(mutref<i64> source)const->i64{return 42;}};auto answer()->i64{return 42;}','only scalar or enum method parameters are supported'),('extract-existing-inspect-method',PREFIX+'auto answer()->i64{Receiver receiver=Receiver();i64 extracted=receiver.inspect;return extracted;}','unknown field')]
ENTRY='\n.text\n.globl _start\n_start:\ncall answer\npushq %rax\nmovq $1,%rax\nmovq $1,%rdi\nmovq %rsp,%rsi\nmovq $8,%rdx\nsyscall\nmovq $60,%rax\nxorq %rdi,%rdi\nsyscall\n.section .note.GNU-stack,"",@progbits\n'
reports=[]
for mode,compiler in [('release',ROOT/'build/aurorac'),('fatal-sanitized',ROOT/'build/san/aurorac')]:
 pdir=OUT/mode;pdir.mkdir(exist_ok=True)
 for name,source,diagnostic in CASES:
  for previous in [False,True]:
   d=pdir/(name+('-saved' if previous else '-absent'));d.mkdir(exist_ok=True)
   inp=d/'input.au';out=d/'output.s';inp.write_text(source)
   if previous:out.write_bytes(b'prior verified output\x00\xff')
   else:require(not out.exists(),'unexpected prior absent-artifact fixture')
   result=run([compiler,inp,'-o',out],mode=='fatal-sanitized')
   (d/'stderr.bin').write_bytes(result.stderr);(d/'stdout.bin').write_bytes(result.stdout)
   require(result.returncode==1,f'{mode} {name}: rejection returned {result.returncode}: {result.stderr!r}')
   require(diagnostic.lower().encode() in result.stderr.lower(),f'{mode} {name}: wrong rejection {result.stderr!r}')
   require(out.read_bytes()==b'prior verified output\x00\xff' if previous else not out.exists(),f'{mode} {name}: rejection changed output')
   require(inp.read_text()==source,f'{mode} {name}: changed source')
   reports.append({'compiler':mode,'case':name,'previous_output':previous,'result':'pass','diagnostic':result.stderr.decode()})
   print('PASS',mode,name,'saved' if previous else 'absent',flush=True)
 d=pdir/'existing-inspect-call-control';d.mkdir(exist_ok=True)
 (d/'input.au').write_text(PREFIX+'auto answer()->i64{Value source=Value{.value=42};Receiver receiver=Receiver();return receiver.inspect(source);}')
 result=run([compiler,d/'input.au','-o',d/'output.s'],mode=='fatal-sanitized');require(result.returncode==0,f'{mode}: positive control {result.stderr!r}')
 (d/'combined.s').write_text((d/'output.s').read_text()+ENTRY)
 for command in [['as','--64',d/'combined.s','-o',d/'program.o'],['ld','-o',d/'program',d/'program.o']]:
  result=run(command);require(result.returncode==0,f'{mode}: tool failed {result.stderr!r}')
 result=run([d/'program']);require(result.returncode==0 and result.stdout==(42).to_bytes(8,'little'),f'{mode}: native positive control failed')
 reports.append({'compiler':mode,'case':'existing-inspect-call-control','result':'pass','native_i64':42});print('PASS',mode,'existing-inspect-call-control',flush=True)
require(source_pins=={str(p.relative_to(ROOT)):sha(p) for p in FROZEN},'frozen suite files changed during probes')
(OUT/'results.json').write_text(json.dumps({'time_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'compiler_pins':{'release':sha(ROOT/'build/aurorac'),'fatal-sanitized':sha(ROOT/'build/san/aurorac')},'frozen_source_pins_unchanged':source_pins,'reports':reports},indent=2)+'\n')
print('PASS two diagnostic-specific negatives with absent/saved output plus positive native control on each compiler pin')
