#!/usr/bin/env python3
import hashlib,json,pathlib,resource,subprocess,sys
ROOT=pathlib.Path(__file__).resolve().parents[2]
COMPILER=pathlib.Path(sys.argv[1]).resolve() if len(sys.argv)>1 else ROOT/'build/aurorac'
OUT=pathlib.Path(sys.argv[2]).resolve() if len(sys.argv)>2 else ROOT/'review/independent-method-review/array-self'
OUT.mkdir(parents=True,exist_ok=True)
BASE='''module probe;namespace std{template<Scalar T,i64 N>class array{builtin::array<T,N> values;public:array():values{}{}auto get(i64 i)const->T{return values[i];}auto set(i64 i,T n)->T{values[i]=n;return n;}BODY};}TAIL'''
CASES=[]
def add(name,method,body,tail='',error=None):
 CASES.append((name,BASE.replace('BODY',method).replace('TAIL',tail+'auto answer()->i64{'+body+'}'),error))
add('bare-self-remains-builtin-reserved','auto exchange(array source)->array{return source;}','return 42;',error="expected '<'")
add('qualified-self-exchange-and-construction','auto exchange(std::array source)->std::array{std::array old=std::array();old.set(0,values[0]);values[0]=source.get(0);return old;}','std::array<i64,1> a=std::array<i64,1>();a.set(0,42);std::array<i64,1> b=a.exchange(a);a.set(0,0);return b.get(0);')
add('qualified-self-remains-accepted','auto copy(std::array source)const->std::array{std::array result=source;return result;}','std::array<i64,1> a=std::array<i64,1>();a.set(0,42);std::array<i64,1> b=a.copy(a);return b.get(0);')
add('explicit-builtin-short-storage-inside-self','auto check()const->i64{const array<i64,2> a={20,22};return a[0]+a[1];}','std::array<i64,1> a=std::array<i64,1>();return a.check();')
add('explicit-canonical-storage-inside-self','auto check()const->i64{const builtin::array<i64,2> a={20,22};return a[0]+a[1];}','std::array<i64,1> a=std::array<i64,1>();return a.check();')
add('canonical-bare-type-not-self','auto bad(builtin::array x)const->i64{return 42;}','return 42;',error="expected '<'")
add('canonical-bare-constructor-not-self','auto bad()const->std::array{std::array x=builtin::array();return x;}','std::array<i64,1> a=std::array<i64,1>();return 42;',error='reserved builtin namespace or identifier')
add('canonical-explicit-constructor-not-self','auto bad()const->std::array{std::array x=builtin::array<i64,1>();return x;}','std::array<i64,1> a=std::array<i64,1>();return 42;',error='template-id references inside template')
add('bare-self-context-cleared-root','','array x=array();return 42;',error="expected '<'")
add('bare-self-context-cleared-next-class','','return 42;',tail='class Sibling{public:auto bad(array x)const->i64{return 42;}};',error="expected '<'")
add('bare-self-context-cleared-namespace-std','','return 42;',tail='namespace std{auto bad(array x)->i64{return 42;}}',error="expected '<'")
add('bare-array-outside-call-reject','','return array();',error='builtin array does not provide')
add('source-nominal-capacity-mismatch','auto copy(std::array source)const->std::array{return source;}','std::array<i64,1> a=std::array<i64,1>();std::array<i64,2> b=std::array<i64,2>();std::array<i64,1> c=a.copy(b);return 42;',error='expected std::array<i64,1>, got std::array<i64,2>')
add('source-nominal-element-mismatch','auto copy(std::array source)const->std::array{return source;}','std::array<i64,1> a=std::array<i64,1>();std::array<u64,1> b=std::array<u64,1>();std::array<i64,1> c=a.copy(b);return 42;',error='expected std::array<i64,1>, got std::array<u64,1>')
add('bare-self-type-not-shadowable','auto bad()const->i64{i64 array=42;return array;}','return 42;',error='reserved builtin storage name')
ENTRY='''\n.text\n.globl _start\n_start:\ncall answer\npushq %rax\nmovq $1,%rax\nmovq $1,%rdi\nmovq %rsp,%rsi\nmovq $8,%rdx\nsyscall\nmovq $60,%rax\nxorq %rdi,%rdi\nsyscall\n.section .note.GNU-stack,"",@progbits\n'''
def limit(sanitized=False):
 resource.setrlimit(resource.RLIMIT_CORE,(0,0));resource.setrlimit(resource.RLIMIT_CPU,(20,20));resource.setrlimit(resource.RLIMIT_FSIZE,(32*1024**2,32*1024**2))
 if not sanitized:resource.setrlimit(resource.RLIMIT_AS,(384*1024**2,384*1024**2))
def run(cmd):return subprocess.run(list(map(str,cmd)),capture_output=True,timeout=25,preexec_fn=lambda:limit(pathlib.Path(cmd[0]).resolve()==COMPILER and any(x in str(COMPILER) for x in ('/san/','asan','sanit'))))
def req(ok,msg):
 if not ok:raise AssertionError(msg)
results=[]
for name,source,error in CASES:
 d=OUT/name;d.mkdir(exist_ok=True);(d/'input.au').write_text(source);(d/'output.s').write_bytes(b'unchanged')
 p=run([COMPILER,d/'input.au','-o',d/'output.s']);(d/'stderr').write_bytes(p.stderr)
 if error:
  req(p.returncode==1 and error.lower().encode() in p.stderr.lower(),f'{name}: expected {error}, got {p.returncode} {p.stderr!r}')
  req((d/'output.s').read_bytes()==b'unchanged',name+': reject altered output')
 else:
  req(p.returncode==0,f'{name}: {p.stderr!r}');(d/'combined.s').write_text((d/'output.s').read_text()+ENTRY)
  for cmd in (['as','--64',d/'combined.s','-o',d/'program.o'],['ld','-o',d/'program',d/'program.o']):
   p=run(cmd);req(p.returncode==0,f'{name}: {p.stderr!r}')
  p=run([d/'program']);req(p.returncode==0 and p.stdout==(42).to_bytes(8,'little'),f'{name}: {p.returncode} {p.stdout!r}')
 print('PASS',name,flush=True);results.append({'name':name,'rejection':bool(error),'result':'pass'})
(OUT/'results.json').write_text(json.dumps({'compiler':str(COMPILER),'sha256':hashlib.sha256(COMPILER.read_bytes()).hexdigest(),'cases':results},indent=2)+'\n')
print('PASS',len(results),'array-self checks')
