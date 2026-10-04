import sys,tempfile
from pathlib import Path
sys.path.insert(0,'/workspace/scratch/48c5de6446f8/aurora/tests/compiler')
from readonly_spans import Suite,SPAN
with tempfile.TemporaryDirectory(prefix='aurora-review-m14-extra-') as d:
 s=Suite(Path(d),sys.argv[1],5,False)
 for mask in range(64):
  kinds=[('span' if mask>>i&1 else ('class' if i%2 else 'scalar')) for i in range(6)]
  defs='class Tiny{public:u8 x;Tiny(u8 n):x(n){} };class Result{public:u8 head;u64 sum;u8 tail;Result(u8 h,u64 s,u8 t):head(h),sum(s),tail(t){} };'
  params=','.join(f'{SPAN if k=="span" else "Tiny" if k=="class" else "u64"} p{i}' for i,k in enumerate(kinds))
  terms=[f'u64(p{i}.at(1))+u64(p{i}.size())' if k=='span' else f'u64(p{i}.x)' if k=='class' else f'p{i}' for i,k in enumerate(kinds)]
  helpers='auto noise(u64 n)->u64{return n/1u64;}auto leaf('+params+')->Result{const u64 n=noise('+ '+'.join(terms)+');const Result r=Result(9u8,n,251u8);return r;}auto forward('+params+')->Result{const Result r=leaf('+','.join('p'+str(i) for i in range(6))+');return r;}'
  body=''
  args=[]; expected=0
  for i,k in enumerate(kinds):
   if k=='span':
    body+=f'array<u8,3> a{i}={{1u8,{i+10}u8,255u8}};';args.append(f'borrow_bytes(a{i})');expected+=i+13
   elif k=='class':
    body+=f'const Tiny a{i}=Tiny({i+10}u8);';args.append(f'a{i}');expected+=i+10
   else: args.append(f'noise({i+10}u64)');expected+=i+10
  body+='const Result r=forward('+','.join(args)+');'
  for i,k in enumerate(kinds):
   if k=='span': body+=f'a{i}[1]=0u8;'
  body+='return r.sum+u64(r.head)+u64(r.tail);'
  s.check('six-position record mask '+str(mask),body,expected+260,definitions=defs,helpers=helpers)
 print('PASS 64 independent mixed span/class/scalar forward/result ABI cases')
