#!/usr/bin/env python3
import hashlib,json,os,pathlib,resource,subprocess,sys
BASE=pathlib.Path('/workspace/scratch/48c5de6446f8')
TREE=BASE/'aurora-m022-method-candidate'
OUT=(pathlib.Path(sys.argv[2]).resolve() if len(sys.argv)>2 else TREE/'review/independent-method-review')
OUT.mkdir(parents=True,exist_ok=True)
COMPILER=pathlib.Path(sys.argv[1]).resolve() if len(sys.argv)>1 else TREE/'build/aurorac'
SAN=any(x in str(COMPILER) for x in ('/san/','asan','sanit'))
def limits(sanitized=False):
 resource.setrlimit(resource.RLIMIT_CORE,(0,0));resource.setrlimit(resource.RLIMIT_CPU,(20,20));resource.setrlimit(resource.RLIMIT_FSIZE,(32*1024**2,32*1024**2))
 if not sanitized:resource.setrlimit(resource.RLIMIT_AS,(384*1024**2,384*1024**2))
def run(args):
 return subprocess.run(list(map(str,args)),capture_output=True,timeout=25,preexec_fn=lambda:limits(pathlib.Path(args[0]).resolve()==COMPILER and SAN))
def require(ok,msg):
 if not ok: raise AssertionError(msg)
BOX='''class Box{i64 n;public:Box(i64 v):n(v){}auto get()const->i64{return n;}auto add(i64 v)->i64{n=n+v;return n;}auto take(Box a,i64 n,Box b)const->i64{return a.get()+b.get()+n;}auto copied(Box a)const->Box{return a;}};'''
CASES=[]
def case(name,body,decl=BOX,helpers='',imports='',expected=42,error=None,modules=None):
 CASES.append((name,'module review;'+imports+decl+helpers+'auto answer()->i64{'+body+'}',expected,error,modules or {}))
case('nested-odd-stack-six-positions','Box a=Box(3);Box b=Box(6);Mixer m=Mixer();return 1+(2+m.mix(7,a,m.scalar(a),b,8,a));',BOX+'''class Mixer{public:Mixer(){}auto scalar(Box a)const->i64{return 6+a.get();}auto mix(i64 x,Box a,i64 y,Box b,i64 z,Box c)const->i64{return x+a.get()+y+b.get()+z+c.get()+3;}};''')
# Compound RHS preserves an already-pushed receiver array index, then calls packed method.
case('receiver-array-store-nested-packed-call','Box source=Box(20);Array object=Array();return object.update(source);',BOX+'''class Array{builtin::array<i64,2> a;public:Array():a{}{}auto update(Box source)->i64{a[1]=2+source.take(source,0,source);return a[1];}};''')
case('implicit-forwarded-classargs-and-result-after-nested-call','Box source=Box(21);Holder receiver=Holder(20);Box result=receiver.outer(source);return result.get();',BOX+'''class Holder{i64 n;auto inner(Box a,i64 add)->Box{n=n+add;const Box result=Box(a.get()+n);return result;}public:Holder(i64 v):n(v){}auto outer(Box a)->Box{const Box result=inner(a,a.take(a,0,a)-41);return result;}};''')
case('implicit-argument-mutation-precedes-reborrow','Box source=Box(19);Holder receiver=Holder(20);return receiver.outer(source);',BOX+'''class Holder{i64 n;auto bump()->i64{n=n+1;return n;}auto inner(Box a,i64 captured)const->i64{return a.get()+captured+n-19;}public:Holder(i64 v):n(v){}auto outer(Box a)->i64{return inner(a,bump());}};''')
case('copied-method-param-returned-after-nested-empty-return','Box source=Box(42);Receiver receiver=Receiver();const Box result=receiver.copy(source);return result.get();',BOX+'''class Empty{public:Empty(){}};class Receiver{auto empty(Empty v)const->Empty{return v;}public:Receiver(){}auto copy(Box v)const->Box{const Empty a=Empty();const Empty b=empty(a);return v;}};''')
case('caller-private-type-generic-method-copy','Secret source=Secret(42);Boxer<Secret> receiver=Boxer<Secret>();Secret result=receiver.copy(source);return result.get();','class Secret{i64 n;public:Secret(i64 v):n(v){}auto get()const->i64{return n;}};',imports='import lib.box;',modules={'lib.box':'export module lib.box;export template<Value T>class Boxer{public:Boxer(){}auto copy(T source)const->T{return source;}};'})
case('caller-private-generic-method-no-private-field-authority','Secret source=Secret(42);Boxer<Secret> receiver=Boxer<Secret>();return receiver.inspect(source);','class Secret{i64 hidden;public:Secret(i64 v):hidden(v){}};',imports='import lib.box;',error='private',modules={'lib.box':'export module lib.box;export template<Value T>class Boxer{public:Boxer(){}auto inspect(T source)const->i64{return source.hidden;}};'})
case('caller-private-generic-method-no-private-method-authority','Secret source=Secret(42);Boxer<Secret> receiver=Boxer<Secret>();return receiver.inspect(source);','class Secret{i64 hidden;auto secret()const->i64{return hidden;}public:Secret(i64 v):hidden(v){}};',imports='import lib.box;',error='private',modules={'lib.box':'export module lib.box;export template<Value T>class Boxer{public:Boxer(){}auto inspect(T source)const->i64{return source.secret();}};'})
case('public-method-param-private-type-leak','return 42;','',imports='import lib.api;',error='private',modules={'lib.api':'export module lib.api;class Secret{public:Secret(){}};export class Api{public:Api(){}auto use(Secret s)const->i64{return 42;}};'})
mods={'lib.value':'export module lib.value;export class Value{public:Value(){}};','lib.api':'export module lib.api;import lib.value;export class Api{public:Api(){}auto consume(Value v)const->i64{return 42;}};'}
case('public-method-signature-transitive-visibility-reject','Api a=Api();return 42;','',imports='import lib.api;',error='visible',modules=mods)
case('public-method-signature-direct-import-accept','Api a=Api();Value v=Value();return a.consume(v);','',imports='import lib.api;import lib.value;',modules=mods)
case('ordinary-helper-receiver-cycle-reject','Box b=Box();return b.loop(b);','class Box{public:Box(){}auto loop(Box b)const->i64{return helper(b);}};',helpers='auto helper(Box b)->i64{return b.loop(b);}',error='cycle')
case('readonly-param-no-receiver-mutation','Box b=Box(42);Reader r=Reader();return r.inspect(b);',BOX+'class Reader{public:Reader(){}auto inspect(Box b)const->i64{return b.add(0);}};',error='mutable')
case('class-field-argument-requires-projection','Box b=Box(42);Wrapper w=Wrapper(b);return b.take(w.value,0,b);',BOX+'class Wrapper{public:Box value;Wrapper(Box b):value(b){}};',error='local name')
case('nominal-template-mismatch','Box<i64> a=Box<i64>(42);Box<u64> b=Box<u64>(42u64);return a.inspect(b);','template<Scalar T>class Box{T value;public:Box(T n):value(n){}auto inspect(Box v)const->i64{return 42;}};',error='expected Box<i64>, got Box<u64>')

PROVIDER = """export module lib.array;export namespace std{template<Scalar T,i64 N>class array{builtin::array<T,N> data;public:array():data{}{}auto at(i64 i)const->T{return data[i];}auto set(i64 i,T n)->T{data[i]=n;return n;}auto copied(std::array v)const->std::array{const std::array local=v;return local;}};}export class Factory{public:Factory(){}auto inspect(std::array<i64,1> a)const->i64{return a.at(0);}};export auto module_probe()->i64{std::array<i64,1> a=std::array<i64,1>();a.set(0,42);std::array<i64,1> b=a.copied(a);return b.at(0);}"""
DECOY = """namespace std{template<Scalar T,i64 N>class array{T data;public:array():data(1){}auto value()const->T{return data;}};}"""
case('qualified-self-retains-defining-module-after-import','return module_probe();','',imports='import lib.array;',modules={'lib.array':PROVIDER})
case('same-spelled-array-caller-shadow-rejects-ambiguity','std::array<i64,1> local=std::array<i64,1>();Factory f=Factory();return f.inspect(local);',DECOY,imports='import lib.array;',modules={'lib.array':PROVIDER},error='ambiguous visible declaration')
ENTRY='''\n.text\n.globl _start\n_start:\ncall answer\npushq %rax\nmovq $1,%rax\nmovq $1,%rdi\nmovq %rsp,%rsi\nmovq $8,%rdx\nsyscall\nmovq $60,%rax\nxorq %rdi,%rdi\nsyscall\n.section .note.GNU-stack,"",@progbits\n'''
results=[]
for name,source,expected,error,modules in CASES:
 d=OUT/name;d.mkdir(exist_ok=True)
 (d/'input.au').write_text(source)
 for module,content in modules.items():
  p=d/'modules'/(module.replace('.','/')+'.au');p.parent.mkdir(parents=True,exist_ok=True);p.write_text(content)
 cmd=[COMPILER,d/'input.au','--module-root',TREE/'library']
 if modules:cmd+=['--module-root',d/'modules']
 cmd+=['-o',d/'output.s']
 (d/'output.s').write_bytes(b'preserved-output\x00\xff')
 p=run(cmd);(d/'stderr').write_bytes(p.stderr)
 if error:
  require(p.returncode==1,f'{name}: expected reject, got {p.returncode}, {p.stderr!r}')
  require(error.lower() in p.stderr.decode().lower(),f'{name}: wrong diagnostic {p.stderr!r}')
  require((d/'output.s').read_bytes()==b'preserved-output\x00\xff',f'{name}: changed output on reject')
 else:
  require(p.returncode==0,f'{name}: compile failed {p.stderr!r}')
  (d/'combined.s').write_text((d/'output.s').read_text()+ENTRY)
  for command in (['as','--64',d/'combined.s','-o',d/'program.o'],['ld','-o',d/'program',d/'program.o']):
   p=run(command);require(p.returncode==0,f'{name}: {p.stderr!r}')
  p=run([d/'program']);require(p.returncode==0 and len(p.stdout)==8,f'{name}: run {p.returncode},{p.stdout!r},{p.stderr!r}')
  result=int.from_bytes(p.stdout,'little',signed=True);require(result==expected,f'{name}: expected {expected}, got {result}')
 results.append({'name':name,'result':'pass','rejection':bool(error)})
 print('PASS',name,flush=True)
report={'compiler':str(COMPILER),'sha256':hashlib.sha256(COMPILER.read_bytes()).hexdigest(),'source_sha256':{str(p.relative_to(TREE)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [*(TREE/'compiler').glob('*.hpp'),TREE/'compiler/main.cpp',TREE/'library/std/array.au']},'tests':results}
(OUT/'review-probe-results.json').write_text(json.dumps(report,indent=2)+'\n')
print('PASS',len(results),'independent source checks')
