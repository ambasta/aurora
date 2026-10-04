from pathlib import Path
import sys,json,hashlib
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'evidence/review'))
# Reuse independent observer setup without running its fixture body.
ns={'__file__':str(ROOT/'evidence/review/independent-probes.py')}
sourcecode=(ROOT/'evidence/review/independent-probes.py').read_text().split('# full-width independent scalar')[0]
exec(compile(sourcecode,'independent-helper','exec'),ns)
ns['D']=ROOT/'evidence/review/extra';ns['D'].mkdir(exist_ok=True)
run=ns['run'];source=ns['source'];TAG=ns['TAG'];COPY=ns['COPY']
inner='class Inner{public:u8 value;Inner(u8 v):value(v){} };'
outer='class Outer{u8 value;public:Outer(u8 x):value(x){}auto get()const->Inner{const Inner result=Inner(value);return result;}};'
mods={'generic':'export module generic;export template<Value T,Value U>auto extract(T x)->U{const U r=x.get();return r;}'}
run('two-exact-private-types',source('Inner a=Inner(42u8);Outer o=Outer(42u8);Inner b=extract<Outer,Inner>(o);return i64(b.value);',inner+outer,'import generic;'),modules=mods)
# Supplying Outer alone cannot make generic fixed Inner lookup available.
mods={'generic':'export module generic;export template<Value T>auto extract(T x)->i64{const Inner r=x.get();return i64(r.value);}'}
run('nested-private-not-arbitrary-lookup',source('Inner a=Inner(42u8);Outer o=Outer(42u8);return extract<Outer>(o);',inner+outer,'import generic;'),modules=mods,negative=True)
base=TAG+'template<Value T>auto factory()->i64{return size_of(Tag<T>);}'+''.join('class C'+str(i)+'{public:C'+str(i)+'(){} };' for i in range(128))
body=''.join('factory<C'+str(i)+'>();' for i in range(128))
run('factory-exact-257',source(body+'return extra<i64>();',base+'template<Scalar T>auto extra()->i64{return 42;}'),negative=True)
run('factory-256-with-repeats',source(body+'factory<C127>();factory<C0>();return 42;',base))
mods={'generic':'export module generic;'+TAG+'export template<Value T>auto factory()->i64{return type_id(Tag<T>);}'}
for name in ['left','right']:
 defs=''.join('class C'+str(i)+'{public:C'+str(i)+'(){} };' for i in range(64))
 calls=''.join('factory<C'+str(i)+'>();' for i in range(1,64))
 mods[name]='export module '+name+';import generic;'+defs+'export auto '+name+'()->i64{'+calls+'return factory<C0>();}'
run('factory-256-cross-module-identities',source('if(left()==right()){return 1;}return 42;',imports='import left;import right;'),modules=mods)
# Same generated class requested through an ordinary root class template type and function factory stays interned.
run('class-generated-first-order-interning',source('Tag<i64> first=Tag<i64>();if(factory<i64>()!=type_id(Tag<i64>)){return 1;}return 42;',TAG+'template<Value T>auto factory()->i64{return type_id(Tag<T>);}'))
(ns['D']/'results.json').write_text(json.dumps({'compiler_sha256':hashlib.sha256(ns['COMP'].read_bytes()).hexdigest(),'results':ns['records']},indent=2)+'\n')
print('TOTAL',len(ns['records']),'PASSED',sum(x['pass'] for x in ns['records']))
