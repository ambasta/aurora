from pathlib import Path
import sys
sys.path.insert(0,'/workspace/scratch/48c5de6446f8/aurora/tests/compiler')
from enum_composition import Suite,program
s=Suite(Path(sys.argv[1]))
for mask in range(64):
 classes='';params=[];inits=[];args=[];terms=[]
 for i,n in enumerate((1,3,7,9,17,31)):
  classes+=f'class C{i}{{builtin::array<u8,{n}> data;public:C{i}():data{{}}{{}} auto set(u8 v)->u8{{data[{n-1}]=v;return v;}} auto get()const->u64{{return u64(data[{n-1}]);}}}};'
  if (mask>>i)&1:
   params.append(f'C{i} p{i}');inits.append(f'C{i} c{i}=C{i}();c{i}.set({i+1}u8);');args.append(f'c{i}');terms.append(f'p{i}.get()')
  else:
   params.append(f'u8 p{i}');args.append(f'{i+1}u8');terms.append(f'u64(p{i})')
 result='class Result{public:u8 head;u64 total;u8 tail;Result('+','.join(params)+'):head(255u8),total(21u64+'+'+'.join(terms)+'),tail(128u8){} };'
 body='static_assert(size_of(Result)==24);const u8 before=17u8;'+''.join(inits)+'const Result result=Result('+','.join(args)+');const u8 after=19u8;if(before!=17u8){return 1u64;}if(after!=19u8){return 2u64;}if(result.head!=255u8){return 3u64;}if(result.tail!=128u8){return 4u64;}return result.total;'
 s.check('packed constructor record mask '+str(mask),program(body,classes+result,result='u64'))
print(f'{s.count} independent packed constructor ABI cases passed')
