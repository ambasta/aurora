#!/usr/bin/env python3
from pathlib import Path
import subprocess, hashlib, json, resource, sys
BASE=Path(__file__).resolve().parents[2]; OUT=BASE/'tmp/independent-compiler'; OUT.mkdir(parents=True,exist_ok=True)
COMP=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else BASE/'build/aurorac'
RECEIPT=Path(sys.argv[2]) if len(sys.argv)>2 else BASE/'review/independent-compiler/results.json'
PIN=hashlib.sha256(COMP.read_bytes()).hexdigest(); results=[]
def run(cmd):
 return subprocess.run([str(c) for c in cmd],capture_output=True,timeout=20,preexec_fn=lambda:resource.setrlimit(resource.RLIMIT_CORE,(0,0)))
def check(name,src,expected=42,error=False,modules=None):
 d=OUT/name; d.mkdir(exist_ok=True); p=d/'input.au'; p.write_text(src); asm=d/'output.s'; asm.write_text('SENTINEL\n'); hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest()}
 for name_,contents in (modules or {}).items():
  m=d/(name_.replace('.','/')+'.au'); m.parent.mkdir(parents=True,exist_ok=True);m.write_text(contents);hashes[str(m)]=hashlib.sha256(m.read_bytes()).hexdigest()
 cmd=[COMP,'--module-root',BASE/'library','--module-root',d,p,'-o',asm]; r=run(cmd)
 good=(r.returncode==1 and asm.read_text()=='SENTINEL\n') if error else r.returncode==0
 rec={'name':name,'compiler_sha256':PIN,'command':[str(x) for x in cmd],'status':r.returncode,'stderr':r.stderr.decode(),'expected_reject':error,'input_sha256':hashes}
 if not error and r.returncode==0:
  bridge=d/'entry.s'; bridge.write_text('.text\n.globl _start\n_start:\n call test\n pushq %rax\n movq $1,%rax\n movq $1,%rdi\n movq %rsp,%rsi\n movq $8,%rdx\n syscall\n movq $60,%rax\n xorq %rdi,%rdi\n syscall\n.section .note.GNU-stack,"",@progbits\n')
  for cmd_ in [['as','--64',asm,'-o',d/'output.o'],['as','--64',bridge,'-o',d/'entry.o'],['ld','-o',d/'program',d/'entry.o',d/'output.o']]:
   rr=run(cmd_)
   if rr.returncode:raise RuntimeError(rr.stderr)
  rr=run([d/'program']);actual=int.from_bytes(rr.stdout,'little',signed=True) if len(rr.stdout)==8 else None
  rec.update(native_status=rr.returncode,expected=expected,actual=actual);good=good and rr.returncode==0 and actual==expected
 good=good and all(hashlib.sha256(Path(p_).read_bytes()).hexdigest()==h for p_,h in hashes.items())
 rec['passed']=good;results.append(rec);print(('PASS ' if good else 'FAIL ')+name+' '+r.stderr.decode().strip(),flush=True)
 RECEIPT.write_text(json.dumps({'compiler':str(COMP),'pin':PIN,'results':results},indent=2)+'\n')
box='''template <Value T> class Box { public: T item; Box(T x):item(x){} auto get() const -> T { const T result=item; return result; } };\n'''
phantom='template <Value T> class Phantom {};\n'
check('deep_values', 'module review;\n'+box+'''auto roundtrip(Box<Box<Box<Box<i64>>>> x) -> Box<Box<Box<Box<i64>>>> { return x; }
class Holder { Box<Box<Box<i64>>> value; public: Holder(Box<Box<Box<i64>>> x):value(x){} auto get() const -> Box<Box<Box<i64>>> { const Box<Box<Box<i64>>> result=value; return result; } };
auto test() -> i64 { Box<i64> a=Box<i64>(42); Box<Box<i64>> b=Box<Box<i64>>(a); Box<Box<Box<i64>>> c=Box<Box<Box<i64>>>(b); const Box<Box<Box<Box<i64>>>> d=Box<Box<Box<Box<i64>>>>(c); const Box<Box<Box<Box<i64>>>> e=roundtrip(d); const Box<Box<Box<i64>>> f=e.item; const Holder h=Holder(f); const Box<Box<Box<i64>>> g=h.get(); const Box<Box<i64>> k=g.get(); const Box<i64> l=k.get(); a.item=0; return l.get(); }''')
check('full_binary_tree', '''module review; import std.utility; auto test()->i64 { std::pair<u8,u64> a=std::pair<u8,u64>(2u8,40u64); std::pair<std::pair<u8,u64>,std::pair<u8,u64>> b=std::pair<std::pair<u8,u64>,std::pair<u8,u64>>(a,a); std::pair<std::pair<std::pair<u8,u64>,std::pair<u8,u64>>,std::pair<std::pair<u8,u64>,std::pair<u8,u64>>> c=std::pair<std::pair<std::pair<u8,u64>,std::pair<u8,u64>>,std::pair<std::pair<u8,u64>,std::pair<u8,u64>>>(b,b); const std::pair<std::pair<u8,u64>,std::pair<u8,u64>> d=c.first; const std::pair<u8,u64> e=d.second; static_assert(size_of(std::pair<std::pair<std::pair<u8,u64>,std::pair<u8,u64>>,std::pair<std::pair<u8,u64>,std::pair<u8,u64>>>)==64); return i64(e.first)+i64(e.second); }''')
check('canonical_capacity','''module review; import std.utility; import std.array;
auto copy(std::pair<std::array<u8,03>,std::array<u8,0003>> x)->std::pair<std::array<u8,3>,std::array<u8,3>> {return x;}
auto test()->i64 {std::array<u8,03> a=std::array<u8,3>(); a.set(0,42u8); const std::pair<std::array<u8,3>,std::array<u8,03>> b=std::pair<std::array<u8,03>,std::array<u8,003>>(a,a); const std::pair<std::array<u8,3>,std::array<u8,3>> c=copy(b); const std::array<u8,003> d=c.first; static_assert(type_id(std::pair<std::array<u8,3>,std::array<u8,03>>)==type_id(std::pair<std::array<u8,003>,std::array<u8,3>>)); return i64(d.at(0));}''')
check('empty_inner','module review;'+box+'''class Empty {};auto test()->i64 {const Empty e=Empty{};const Box<Empty> b=Box<Empty>(e);const Box<Box<Empty>> c=Box<Box<Empty>>(b);const Box<Empty> d=c.get();const Empty f=d.get();static_assert(size_of(Box<Box<Empty>>)==8);static_assert(field_count(Box<Box<Empty>>)==1);return 42;}''')
for n in (4,5):
 t='i64'
 for _ in range(n):t='Phantom<'+t+'>'
 check('phantom_depth_'+str(n),'module review;'+phantom+'auto test()->i64 {const '+t+' value='+t+'{}; return 42;}',error=n>4)
check('containment_depth5','module review;'+box+'class Leaf {public:i64 x;};auto test()->i64 {return size_of(Box<Box<Box<Box<Leaf>>>>);}',error=True)
for cap in (1,32,64,65,0):
 t=f'std::pair<std::array<u8,{cap}>,std::array<u8,{cap}>>'
 check('leaf_array_'+str(cap),'module review;import std.array;import std.utility;auto test()->i64 {return size_of('+t+');}',expected=cap*2,error=cap>32 or cap==0)
for body in ('Box<i64> x;', 'auto get()->Box<i64>{const Box<i64> x=Box<i64>(1);return x;}', 'auto get()->i64{return size_of(Box<i64>);}', 'auto get()->i64{Box<i64>(1);return 42;}'):
 check('body_specialization_'+str(len(results)),'module review;'+box+'template<Value T> class Bad {'+body+'};auto test()->i64{return 42;}',error=True)
for arg in ('own<i64>','ref<i64>','mutref<i64>','array<u8,3>','builtin::array<u8,3>','builtin::span<const u8>','Unknown','Box','Box<>','Box<i64,u8>','Box<0>','Box<65>','Box<true>','Box<i64> >','Box<i64', 'Box<i64>>>'):
 check('bad_arg_'+str(len(results)),'module review;'+phantom+box+'auto test()->i64{return size_of(Phantom<'+arg+'>);}',error=True)
check('scalar_rejects_class','module review;'+box+'template<Scalar T> class S { public:T x;};auto test()->i64{return size_of(S<Box<i64>>);}',error=True)
check('scalar_rejects_enum','module review;enum class E {a};'+box+'template<Scalar T> class S { public:T x;};auto test()->i64{return size_of(Box<S<E>>);}',error=True)
check('nominal_inner_order','module review;import std.utility;'+box+'auto test()->i64{std::pair<i64,u64> a=std::pair<i64,u64>(1,2u64);Box<std::pair<i64,u64>> b=Box<std::pair<i64,u64>>(a);Box<std::pair<u64,i64>> c=b;return 42;}',error=True)
check('ordinary_cycle_nested','module review;'+box+'class Loop { Box<Loop> child;public:Loop(Box<Loop> x):child(x){} };auto test()->i64{return 42;}',error=True)
check('nested_enum_native','module review;'+box+'enum class E {x,y};auto test()->i64 {Box<E> a=Box<E>(E::y); Box<Box<E>> b=Box<Box<E>>(a);const Box<E> c=b.get();if(c.get()==E::y){return 42;}return 0;}')
check('visibility_private_inner', 'module client;import api;auto test()->i64{return 42;}',error=True,modules={'api':'export module api;'+box+'class Private {};export auto leak(Box<Box<Private>> p)->i64{return 1;}'})
check('visibility_private_phantom','module client;import api;auto test()->i64{return 42;}',error=True,modules={'api':'export module api;export '+phantom+'class Private {};export auto leak(Phantom<Phantom<Private>> p)->i64{return 1;}'})
check('visibility_transitive_inner','module client;import api;import gen;auto test()->i64{return size_of(Phantom<Phantom<Secret>>);}',error=True,modules={'hidden':'export module hidden;export class Secret {};','gen':'export module gen;export '+phantom,'api':'export module api;import hidden;import gen;export auto identity(Phantom<Phantom<Secret>> p)->Phantom<Phantom<Secret>>{return p;}'})
check('visibility_direct_inner','module client;import api;import hidden;import gen;auto test()->i64{const Phantom<Phantom<Secret>> x=Phantom<Phantom<Secret>>{};const Phantom<Phantom<Secret>> y=identity(x);return 42;}',modules={'hidden':'export module hidden;export class Secret {};','gen':'export module gen;export '+phantom,'api':'export module api;import hidden;import gen;export auto identity(Phantom<Phantom<Secret>> p)->Phantom<Phantom<Secret>>{return p;}'})
check('defining_helper','''module client;import gen;auto helper()->i64{return 900;}auto test()->i64 {const Box<i64> a=Box<i64>(7);const Box<Box<i64>> b=Box<Box<i64>>(a);return b.value();}''',modules={'gen':'''export module gen; auto helper()->i64{return 42;}export template<Value T> class Box {T data;public:Box(T x):data(x){}auto value()const->i64{return helper();}};'''})
check('requesting_lexical_scope','''module client; import gen;class Local{public:i64 x;};namespace N {class Local{public:i64 x;};auto pick()->i64 {const Local a=Local{.x=42};const Box<Local> b=Box<Local>(a);const Box<Box<Local>> c=Box<Box<Local>>(b);const Box<Local> d=c.get();const Local e=d.get();return e.x;}}auto test()->i64{return N::pick();}''',modules={'gen':'export module gen;export '+box})
check('reflection_visibility','''module client;import gen;class Secret {};auto test()->i64{const Secret a=Secret{};const Box<Secret> b=Box<Secret>(a);const Box<Box<Secret>> c=Box<Box<Secret>>(b);if(hidden_size(type_id(Box<Box<Secret>>))!=0){return 1;}if(reflect_size(type_id(Box<Box<Secret>>))!=8){return 2;}return 42;}''',modules={'gen':'export module gen;export '+box+'export auto hidden_size(i64 id)->i64{return reflect_size(id);}'})
# Two distinct scalar-capacity inners and matching phantom outers for each N.
def caps(extra):
 src='module review;template<Scalar T,i64 N>class Inner {};'+phantom+'auto test()->i64 {'
 for t in ('i64','u8'):
  for n in range(1,65):src+='static_assert(size_of(Phantom<Inner<'+t+','+str(n)+'>>)==8);'
 if extra:src+='static_assert(size_of(Phantom<Phantom<i64>>)==8);'
 else:src+='static_assert(type_id(Phantom<Inner<i64,01>>)==type_id(Phantom<Inner<i64,1>>));'
 return src+'return 42;}'
check('instance_cap256',caps(False))
check('instance_cap258',caps(True),error=True)
for count in (64,65):
 src='module review;'+''.join('template<Value T> class P'+str(i)+' {};' for i in range(count))+'auto test()->i64{return 42;}'
 check('template_cap'+str(count),src,error=count>64)
# Shift tokens adjacent to a just-closed nested type query stay arithmetic.
check('shifts_after_nested','module review;'+phantom+'auto test()->i64{const u64 x=84u64; const i64 n=1; static_assert(size_of(Phantom<Phantom<i64>>)==8);if(x>>n!=42u64){return 1;} if(84u64>>1!=42u64){return 2;}if(u64(size_of(Phantom<Phantom<i64>>))>>1!=4u64){return 3;}return i64(x>>n);}')
check('shifts_and_comparisons','module review;auto test()->i64 {u64 a=3u64;u64 b=84u64;i64 c=1; if(a < b >> c){return 42;}return 0;}')
check('exact_65_leaves','module review;import std.array;import std.utility;auto test()->i64{return size_of(std::pair<std::array<u8,32>,std::array<u8,33>>);}',error=True)
check('exact_257_instances',caps(False).replace('return 42;}','static_assert(size_of(Inner<bool,1>)==8);return 42;}'),error=True)
check('nested_temporary_argument','module review;'+box+'auto test()->i64{const Box<Box<i64>> b=Box<Box<i64>>(Box<i64>(42));return 42;}',error=True)
check('nested_return_temporary','module review;'+box+'auto make()->Box<Box<i64>>{const Box<i64> b=Box<i64>(42);return Box<Box<i64>>(b);}auto test()->i64{return 42;}',error=True)
check('nested_field_assignment','module review;'+box+'auto test()->i64{Box<i64> a=Box<i64>(42);Box<Box<i64>> b=Box<Box<i64>>(a);b.item=a;return 42;}',error=True)
check('nested_chained_receiver','module review;'+box+'auto test()->i64{const Box<i64> a=Box<i64>(42);const Box<Box<i64>> b=Box<Box<i64>>(a);return b.item.get();}',error=True)
check('nested_class_method_parameter','module review;'+box+'class Holder{public:auto method(Box<Box<i64>> x)->i64{return 42;}};auto test()->i64{return 42;}',error=True)
check('nested_private_storage','module review;import std.array;'+box+'auto test()->i64{const std::array<u8,3> a=std::array<u8,3>();const Box<std::array<u8,3>> b=Box<std::array<u8,3>>(a);const std::array<u8,3> c=b.item;return i64(c.storage[0]);}',error=True)
check('public_inner_signature_privacy','module client;import gen;auto test()->i64{return size_of(Phantom<Box<i64>>);}',error=True,modules={'gen':'export module gen;class Hidden{};export '+phantom+'export template<Value T> class Box { public:auto leak()->Hidden{const Hidden x=Hidden{};return x;} };'})
check('same_layout_nominal_inner','module review;'+box+'enum class E{a};enum class F{a};auto test()->i64 {const Box<E> a=Box<E>(E::a);const Box<Box<E>> b=Box<Box<E>>(a);const Box<Box<F>> c=b;return 42;}',error=True)
check('snapshot_before_later_mutation','module review;import std.array;import std.utility;auto test()->i64{std::array<u8,3> a=std::array<u8,3>();a.set(0,42u8);const std::pair<std::array<u8,3>,u8> b=std::pair<std::array<u8,3>,u8>(a,a.set(0,9u8));const std::array<u8,3> c=b.first;if(b.second!=9u8){return 1;}return i64(c.at(0));}')
check('inner_id_precedes_outer','module review;'+phantom+'auto test()->i64{const i64 outer=type_id(Phantom<Phantom<Phantom<i64>>>);static_assert(type_id(Phantom<i64>)<type_id(Phantom<Phantom<i64>>));static_assert(type_id(Phantom<Phantom<i64>>)<type_id(Phantom<Phantom<Phantom<i64>>>));return 42;}')
qual='::'.join('scope'+str(i) for i in range(16))
check('long_qualified_nested_tree','module review;namespace '+qual+'{'+phantom+'}auto test()->i64{'+qual+'::Phantom<'+qual+'::Phantom<'+qual+'::Phantom<i64>>> x='+qual+'::Phantom<'+qual+'::Phantom<'+qual+'::Phantom<i64>>>{};return 42;}')
for n in (1,2,3,4):
 typ='i64'
 for _ in range(n):typ='Phantom<'+typ+'>'
 for spacing in ('> >','>\n>','>// comment\n>'):
  spaced=typ.replace('>>',spacing)
  check('closer_spacing_'+str(n)+'_'+str(len(results)),'module review;'+phantom+'auto test()->i64{'+spaced+' x='+spaced+'{};return 42;}')
for name,src in [('long_opens','Phantom<'*10000+'i64'+'> '*10000),('long_closers','Phantom<i64'+'> '*10000),('wide_arguments','Phantom<'+','.join(['i64']*10000)+'>')]:
 check(name,'module review;'+phantom+'auto test()->i64{return size_of('+src+');}',error=True)

failed=[r['name'] for r in results if not r['passed']]
print('SUMMARY',len(results),'cases; failures:',failed)
sys.exit(bool(failed))
