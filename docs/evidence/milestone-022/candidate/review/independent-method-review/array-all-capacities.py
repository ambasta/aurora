#!/usr/bin/env python3
"""Independent Python list oracle, four scalar kinds x all 64 capacities.
Already-built compiler plus GNU as/ld only; native results use full i64 output.
"""
import hashlib,json,pathlib,resource,subprocess,sys
ROOT=pathlib.Path(__file__).resolve().parents[2]
COMPILER=pathlib.Path(sys.argv[1]).resolve() if len(sys.argv)>1 else ROOT/'build/aurorac'
OUT=pathlib.Path(sys.argv[2]).resolve() if len(sys.argv)>2 else ROOT/'review/independent-method-review/array-capacities-release'
OUT.mkdir(parents=True,exist_ok=True)
def limit(sanitized=False):
 resource.setrlimit(resource.RLIMIT_CORE,(0,0));resource.setrlimit(resource.RLIMIT_CPU,(30,30));resource.setrlimit(resource.RLIMIT_FSIZE,(64*1024**2,64*1024**2))
 if not sanitized:resource.setrlimit(resource.RLIMIT_AS,(384*1024**2,384*1024**2))
def run(cmd):
 san=pathlib.Path(cmd[0]).resolve()==COMPILER and any(x in str(COMPILER) for x in ('/san/','asan','sanit'))
 p=subprocess.run(list(map(str,cmd)),capture_output=True,timeout=45,preexec_fn=lambda:limit(san))
 if p.returncode:raise AssertionError(f'{cmd}: {p.returncode} {p.stderr!r}')
 return p
EDGES={'i64':[-(1<<63),(1<<63)-1,-1,0,1,42], 'u64':[0,(1<<64)-1,1<<63,42], 'u8':[0,255,128,42], 'bool':[False,True]}
def lit(t,n):return ('true' if n else 'false') if t=='bool' else str(n)+(t if t in ('u64','u8') else '')
results=[]
for scalar,edges in EDGES.items():
 d=OUT/scalar;d.mkdir(exist_ok=True);source='module array_review;import std.array;'
 for n in range(1,65):
  T=f'std::array<{scalar},{n}>'
  left=[edges[(i+n)%len(edges)] for i in range(n)]
  right=[edges[(i*3+n+1)%len(edges)] for i in range(n)]
  body=f'{T} a={T}();{T} b={T}();'
  for i,(a,b) in enumerate(zip(left,right)):
   body+=f'a.set({i},{lit(scalar,a)});b.set({i},{lit(scalar,b)});'
  body+=f'{T} self=a.exchange(a);{T} old=a.exchange(b);'
  for i,(a,b) in enumerate(zip(left,right)):
   body+=f'if(self.at({i})!={lit(scalar,a)}){{return 1;}}if(old.at({i})!={lit(scalar,a)}){{return 2;}}if(a.at({i})!={lit(scalar,b)}){{return 3;}}if(b.at({i})!={lit(scalar,b)}){{return 4;}}'
  changed=edges[(edges.index(right[-1])+1)%len(edges)]
  body+=f'b.set({n-1},{lit(scalar,changed)});self.set(0,{lit(scalar,changed)});old.set(0,{lit(scalar,changed)});'
  for i,b in enumerate(right):body+=f'if(a.at({i})!={lit(scalar,b)}){{return 5;}}'
  body+='return 42;'
  source+=f'auto probe_{n}()->i64{{{body}}}'
 (d/'input.au').write_text(source)
 cmd=[COMPILER,d/'input.au','--module-root',ROOT/'library','-o',d/'output.s']
 p=run(cmd);(d/'compile.stderr').write_bytes(p.stderr)
 entry='\n.text\n.globl _start\n_start:\n'
 for n in range(1,65):entry+=f'call probe_{n}\npushq %rax\nmovq $1,%rax\nmovq $1,%rdi\nmovq %rsp,%rsi\nmovq $8,%rdx\nsyscall\naddq $8,%rsp\n'
 entry+='movq $60,%rax\nxorq %rdi,%rdi\nsyscall\n.section .note.GNU-stack,"",@progbits\n'
 (d/'combined.s').write_text((d/'output.s').read_text()+entry)
 run(['as','--64',d/'combined.s','-o',d/'program.o']);run(['ld','-o',d/'program',d/'program.o'])
 p=run([d/'program']);(d/'result.bin').write_bytes(p.stdout)
 if p.stdout!=(42).to_bytes(8,'little')*64:raise AssertionError(f'{scalar}: expected 64 complete i64 results equal42; got {p.stdout!r}')
 print('PASS',scalar,'capacities1..64',flush=True);results.append({'scalar':scalar,'capacities':list(range(1,65)),'result':'pass'})
(OUT/'results.json').write_text(json.dumps({'compiler_sha256':hashlib.sha256(COMPILER.read_bytes()).hexdigest(),'array_source_sha256':hashlib.sha256((ROOT/'library/std/array.au').read_bytes()).hexdigest(),'results':results},indent=2)+'\n')
print('PASS256 independent array exchange capacity cases')
