from pathlib import Path
import sys
sys.path.insert(0,'/workspace/scratch/48c5de6446f8/aurora/tests/compiler')
from enum_composition import Suite,program
s=Suite(Path(sys.argv[1]))
for mask in range(64):
 enums=''.join(f'enum class E{i}{{good,bad}};' for i in range(6))
 helpers=''.join(f'auto value{i}(E{i} x)->u64{{if(x==E{i}::good){{return {i+1}u64;}}return 0u64;}}' for i in range(6))
 args=[];params=[];terms=[]
 for i in range(6):
  e=(mask>>i)&1
  params.append(f'{"E"+str(i) if e else "u64"} a{i}')
  args.append(f'E{i}::good' if e else f'{i+1}u64')
  terms.append(f'value{i}(a{i})' if e else f'a{i}')
 data='class Data {builtin::array<u64,63> values; E0 state; public: Data(E0 s):values{},state(s){} auto set(i64 i,u64 n)->u64{values[i]=n;return n;} auto get(i64 i)const->u64{return values[i];} auto status()const->E0{return state;} };'
 factory='class Factory {u64 base; public: Factory(u64 x):base(x){} auto make('+','.join(params)+')const->Data{Data result=Data(E0::good);result.set(62,base+'+'+'.join(terms)+'); const u64 clobber=85u64/2u64;result.set(0,clobber);return result;} };'
 body='const Factory factory=Factory(21u64);Data first=factory.make('+','.join(args)+');first.set(62,0u64);const Data second=factory.make('+','.join(args)+');if(second.status()!=E0::good){return 0u64;}if(second.get(0)!=42u64){return 0u64;}return second.get(62);'
 s.check('six enum/scalar method positions '+str(mask),program(body,enums+data+factory,helpers,result='u64'))
print(f'{s.count} independent enum method ABI cases passed')
