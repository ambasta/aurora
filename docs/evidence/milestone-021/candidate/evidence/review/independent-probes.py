#!/usr/bin/env python3
from pathlib import Path
import subprocess, json, hashlib, shutil, resource, sys
ROOT=Path(__file__).resolve().parents[2]
D=ROOT/'evidence/review/independent'; D.mkdir(exist_ok=True)
COMP=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else ROOT/'evidence/review/aurorac-reviewed-original'
COPY='template<Value T>auto copy(T x)->T{const T result=x;return result;}'
TAG='template<Value T>class Tag{public:Tag(){} };'
BOX='template<Value T>class Box{public:T value;Box(T x):value(x){} };'
CELL='class Cell{public:u8 value;Cell(u8 x):value(x){}auto set(u8 x)->u8{value=x;return value;}};'
PRESERVED=b'original assembly\x00\xff\n'
records=[]
def source(body,defs='',imports=''):
 return 'module review;'+imports+defs+'auto test()->i64{'+body+'}'
def run(name,src,expected=42,modules=None,negative=False):
 d=D/name;d.mkdir(exist_ok=True)
 f=d/'input.au';f.write_text(src)
 mod=d/'modules';mod.mkdir(exist_ok=True)
 for m,s in (modules or {}).items():
  p=mod/(m.replace('.','/')+'.au');p.parent.mkdir(parents=True,exist_ok=True);p.write_text(s)
 inp={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [f,*mod.rglob('*.au')]}
 out=d/'compiled.s';out.write_bytes(PRESERVED)
 cmd=[str(COMP),'--module-root',str(ROOT/'library'),'--module-root',str(mod),str(f),'-o',str(out)]
 result=subprocess.run(cmd,capture_output=True,timeout=15,preexec_fn=lambda:resource.setrlimit(resource.RLIMIT_CORE,(0,0)))
 r={'name':name,'command':cmd,'returncode':result.returncode,'stderr':result.stderr.decode(),'negative':negative,'input_sha256':inp,'inputs_unchanged':all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in inp.items())}
 if negative:
  r['pass']=result.returncode==1 and out.read_bytes()==PRESERVED
 else:
  r['pass']=result.returncode==0
  if r['pass']:
   asm=d/'entry.s';asm.write_text('.global _start\n.text\n_start:\n call test\n push %rax\n mov $1,%rax\n mov $1,%rdi\n mov %rsp,%rsi\n mov $8,%rdx\n syscall\n mov $60,%rax\n xor %rdi,%rdi\n syscall\n.section .note.GNU-stack,"",@progbits\n')
   try:
    subprocess.run(['as',str(out),'-o',str(d/'compiled.o')],check=True,capture_output=True)
    subprocess.run(['as',str(asm),'-o',str(d/'entry.o')],check=True,capture_output=True)
    subprocess.run(['ld',str(d/'entry.o'),str(d/'compiled.o'),'-o',str(d/'native')],check=True,capture_output=True)
    n=subprocess.run([str(d/'native')],capture_output=True,timeout=5,preexec_fn=lambda:resource.setrlimit(resource.RLIMIT_CORE,(0,0)))
    r['native_status']=n.returncode;r['native_hex']=n.stdout.hex();r['expected']=expected
    r['pass']=n.returncode==0 and len(n.stdout)==8 and int.from_bytes(n.stdout,'little')==expected%(1<<64)
   except (subprocess.CalledProcessError,subprocess.TimeoutExpired) as e:r['pass']=False;r['native_error']=str(e)
 r['pass'] &= r['inputs_unchanged']
 (d/'result.json').write_text(json.dumps(r,indent=2)+'\n'); records.append(r);print(('PASS' if r['pass'] else 'FAIL'),name,r.get('stderr','').strip(),flush=True)
# full-width independent scalar return and deep copied branch/loop ASTs
fn='template<Scalar T>auto transform(T a,T b)->T{T x=a;while(x<b){x=x+b;break;}if(x==a){return a;}else{return x;}}'
# no break syntax; use a finite branch while loop instead
fn='template<Scalar T>auto transform(T a,T b)->T{T x=a;bool again=true;while(again){if(x<b){x=x+b;}again=false;}return x;}'
for kind,val,want in [('i64','-9223372036854775808',-(1<<63)),('u64','18446744073709551615u64',(1<<64)-1),('u8','255u8',255),('bool','true',1)]:
 run('full-width-'+kind,'module review;'+COPY+'auto test()->'+kind+'{return copy<'+kind+'>('+val+');}',expected=want)
run('independent-branch-loop-clones',source('if(transform<i64>(10,20)!=30){return 1;}if(transform<u8>(10u8,20u8)!=30u8){return 2;}if(transform<u64>(10u64,20u64)!=30u64){return 3;}return 42;',fn))
# mutation between class snapshots should preserve each by-value snapshot
mixed='template<Value T>auto keep(T a,u8 ignored,T b)->T{return b;}'
run('left-to-right-snapshots',source('Cell a=Cell(5u8);Cell z=keep<Cell>(a,a.set(42u8),a);a.set(7u8);return i64(z.value);',CELL+mixed))
run('first-snapshot-precedes-mutation',source('Cell a=Cell(42u8);Cell z=keep<Cell>(a,a.set(7u8),a);return i64(z.value);',CELL+mixed.replace('return b;','return a;')))
run('parameter-complete-return-copy',source('std::array<u8,64> a=std::array<u8,64>();a.set(63,42u8);const std::array<u8,64> b=copy<std::array<u8,64>>(a);a.set(63,1u8);return i64(b.at(63));',COPY,'import std.array;'))
run('const-parameter-mutation',source('Cell a=Cell(42u8);return mutate<Cell>(a);',CELL+'template<Value T>auto mutate(T x)->i64{x.value=1u8;return 42;}'),negative=True)
run('incomplete-argument',source('Cell a;const Cell b=copy<Cell>(a);return 42;',CELL+COPY),negative=True)
run('same-layout-wrong-nominal',source('A a=A(42u8);B b=copy<B>(a);return 42;',CELL.replace('Cell','A')+CELL.replace('Cell','B')+COPY),negative=True)
run('same-layout-enum-nominal',source('A a=A::ready;B b=copy<B>(a);return 42;','enum class A{ready};enum class B{ready};'+COPY),negative=True)
# Exact argument authority, member privacy, constructor privacy, no caller lookup
mods={'generic':'export module generic;export '+COPY}
run('caller-private-copy',source('Cell a=Cell(42u8);Cell b=copy<Cell>(a);return i64(b.value);',CELL,'import generic;'),modules=mods)
mods={'generic':'export module generic;export template<Value T>auto inspect(T x)->i64{return i64(x.secret);}' }
run('caller-private-field',source('Cell a=Cell(42u8);return inspect<Cell>(a);','class Cell{u8 secret;public:Cell(u8 x):secret(x){} };','import generic;'),modules=mods,negative=True)
mods={'generic':'export module generic;export template<Value T>auto inspect(T x)->i64{return i64(x.secret());}' }
run('caller-private-method',source('Cell a=Cell(42u8);return inspect<Cell>(a);','class Cell{auto secret()const->u8{return 42u8;}public:Cell(u8 x){} };','import generic;'),modules=mods,negative=True)
mods={'generic':'export module generic;class Locked{Locked(){} };export template<Value T>auto inspect(T x)->i64{const Locked z=Locked();return 42;}' }
run('defining-private-constructor',source('return inspect<i64>(0);',imports='import generic;'),modules=mods,negative=True)
mods={'generic':'export module generic;export template<Value T>auto inspect(T x)->i64{return helper();}' }
run('caller-helper-not-found',source('return inspect<i64>(0);','auto helper()->i64{return 42;}','import generic;'),modules=mods,negative=True)
mods={'generic':'export module generic;export template<Value T>auto inspect(T x)->i64{return size_of(Unrelated);}' }
run('caller-unrelated-type-not-found',source('return inspect<i64>(0);','class Unrelated{public:Unrelated(){} };','import generic;'),modules=mods,negative=True)
mods={'generic':'export module generic;export template<Value T>auto inspect()->i64{if(reflect_size(type_id(T))!=0){return 1;}return 42;}' }
run('runtime-reflection-no-authority',source('return inspect<Cell>();',CELL,'import generic;'),modules=mods)
mods={'generic':'export module generic;export template<Value T>auto inspect()->i64{return size_of(T);}' }
run('compile-time-exact-authority',source('if(inspect<Cell>()!=1){return 1;}return 42;',CELL,'import generic;'),modules=mods)
# Lexical and import boundaries, including unused ambiguous symbols
mods={'a':'export module a;export '+COPY,'b':'export module b;export '+COPY}
run('unused-ambiguous-function-template',source('return 42;',imports='import a;import b;'),modules=mods,negative=True)
mods={'a':'export module a;export '+COPY,'b':'export module b;export class copy{public:copy(){} };'}
run('unused-ambiguous-cross-kind',source('return 42;',imports='import a;import b;'),modules=mods,negative=True)
mods={'a':'export module a;export '+COPY,'b':'export module b;import a;export auto ordinary()->i64{return copy<i64>(42);}'}
run('no-transitive-function-template',source('return copy<i64>(42);',imports='import b;'),modules=mods,negative=True)
run('ordinary-wrapper-works',source('return ordinary();',imports='import b;'),modules=mods)
# Post-substitution ancestry and independent graph instance caps
for n in (3,4):
 t='i64'
 for _ in range(n):t='Tag<'+t+'>'
 run('post-substitution-depth-'+str(n+1),source('return wrap<'+t+'>();',TAG+'template<Value T>auto wrap()->i64{return size_of(Tag<T>)+34;}'),negative=n==4)
for n in (128,129):
 defs=TAG+'template<Value T>auto factory()->i64{return size_of(Tag<T>);}' + ''.join('class C'+str(i)+'{public:C'+str(i)+'(){} };' for i in range(n))
 run('factory-combined-instances-'+str(n*2),source(''.join('factory<C'+str(i)+'>();' for i in range(n))+'return 42;',defs),negative=n==129)
for n in (64,65):
 defs=''.join(TAG.replace('Tag','Tag'+str(i)) for i in range(17))+''.join(COPY.replace('copy','copy'+str(i)) for i in range(n-17))
 run('mixed-definition-count-'+str(n),source('return copy0<i64>(42);',defs),negative=n==65)
# Repeated generated factory class requests and many clones do not invalidate AST vectors
run('factory-interns-and-clones',source(''.join('if(factory<C'+str(i)+'>()!=8){return 1;}' for i in range(120))+'return 42;',TAG+'template<Value T>auto factory()->i64{return size_of(Tag<T>);}' + ''.join('class C'+str(i)+'{public:C'+str(i)+'(){} };' for i in range(120))))
# Both presence and absence of explicit arguments must reject template-body calls
for call in ('other<i64>(42)','other(42)'):
 run('unused-body-call-'+('explicit' if '<' in call else 'bare'),source('return 42;',COPY.replace('copy','other')+'template<Value T>auto never()->i64{return '+call+';}'),negative=True)
(D/'results.json').write_text(json.dumps({'compiler_sha256':hashlib.sha256(COMP.read_bytes()).hexdigest(),'results':records},indent=2)+'\n')
print('TOTAL',len(records),'PASSED',sum(x['pass'] for x in records),'FAILED',sum(not x['pass'] for x in records))
