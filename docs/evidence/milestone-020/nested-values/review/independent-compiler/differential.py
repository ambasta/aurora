#!/usr/bin/env python3
from pathlib import Path
import subprocess,random,hashlib,json,resource
BASE=Path(__file__).resolve().parents[2];D=BASE/'tmp/independent-compiler/differential';D.mkdir(exist_ok=True)
OLD=Path('/tmp/aurora-resource-main-compiler-frozen');NEW=BASE/'build/aurorac';rng=random.Random(48151623);out=[]
# Valid type-directed numeric trees, including named operands before < and >>.
def num(kind,depth=0):
 atoms=['a','b','c','1'+kind,'3'+kind,'15'+kind]
 if depth>2 or rng.random()<.35:return rng.choice(atoms)
 op=rng.choice(['+','-','*','/','%','&','|','^','<<','>>'])
 right=rng.choice(['0','1','2','3','n']) if op in ('<<','>>') else num(kind,depth+1)
 return '('+num(kind,depth+1)+op+right+')'
sources=[]
for i in range(400):
 k=rng.choice(['u8','u64']);expr=num(k)
 if i%2==0:
  expr=expr+rng.choice(['<','>','<=','>=','==','!='])+num(k)
  body='if('+expr+'){return 42;}return 0;'
 else:body='return i64('+expr+');'
 sources.append('module arithmetic;auto test()->i64{'+k+' a=2'+k+';'+k+' b=5'+k+';'+k+' c=7'+k+';i64 n=1;'+body+'}')
# Ungrouped shifts and comparisons exercise exact parse precedence.
for a in ['a','1u64','(a)','a+b','a&b','a|b','a^b']:
 for op in ['<','>','<=','>=','==','!=']:
  for expr in ['b>>n','b<<n','b>>n+1','b+1u64>>n','b>>n < c','b<<n == c','b>>(n)']:
   sources.append('module arithmetic;auto test()->i64{u64 a=2u64;u64 b=16u64;u64 c=4u64;i64 n=1;if('+a+op+expr+'){return 42;}return 0;}')
for i,src in enumerate(sources):
 inp=D/'input.au';inp.write_text(src);res=[]
 for compiler,label in [(OLD,'baseline'),(NEW,'candidate')]:
  asm=D/(label+'.s');asm.write_text('SENTINEL\n')
  r=subprocess.run([str(compiler),str(inp),'-o',str(asm)],capture_output=True,timeout=10,preexec_fn=lambda:resource.setrlimit(resource.RLIMIT_CORE,(0,0)))
  res.append({'status':r.returncode,'assembly_sha256':hashlib.sha256(asm.read_bytes()).hexdigest(),'diagnostic':r.stderr.decode()})
 same=res[0]['status']==res[1]['status'] and res[0]['assembly_sha256']==res[1]['assembly_sha256']
 out.append({'index':i,'source':src,'source_sha256':hashlib.sha256(src.encode()).hexdigest(),'results':res,'identical':same})
 if not same:print('MISMATCH',i,src,res,flush=True)
receipt={'baseline_sha256':hashlib.sha256(OLD.read_bytes()).hexdigest(),'candidate_sha256':hashlib.sha256(NEW.read_bytes()).hexdigest(),'seed':48151623,'count':len(out),'successes':sum(x['results'][0]['status']==0 for x in out),'mismatches':sum(not x['identical'] for x in out),'results':out}
(BASE/'review/independent-compiler/arithmetic-differential.json').write_text(json.dumps(receipt,indent=2)+'\n')
print({k:v for k,v in receipt.items() if k!='results'})
