from pathlib import Path
import os,sys,subprocess,json,hashlib,time,datetime
root=Path('/workspace/scratch/48c5de6446f8/aurora-utf8-next')
out=root/'build/final-acceptance';out.mkdir(exist_ok=False)
hashfile=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
paths=[p for d in ('compiler','library','tests/compiler') for p in (root/d).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix in ('.hpp','.cpp','.au','.py')]
inputs={str(p.relative_to(root)):hashfile(p) for p in sorted(paths)}
(out/'inputs.json').write_text(json.dumps(inputs,indent=2)+'\n')
release=Path('/tmp/aurora-resource-main-compiler-frozen');san=Path('/tmp/aurora-resource-sanitizer/aurorac')
manifest={'status':'running','compiler_hashes':{str(p):hashfile(p) for p in (release,san)},'commands':[],'scope':'pure library, unchanged M016 compiler; no kernel execution'}
def run(args,name,sanitized=False,timeout=300):
 env=os.environ.copy()
 if sanitized: env['ASAN_OPTIONS']='detect_leaks=0:halt_on_error=1'
 args=list(map(str,args)); start=time.monotonic()
 row={'argv':args,'cwd':str(root),'wall_timeout_seconds':timeout,'ASAN_OPTIONS':env.get('ASAN_OPTIONS'),'stdout':name+'.stdout','stderr':name+'.stderr'}
 with (out/(name+'.stdout')).open('wb') as stdout,(out/(name+'.stderr')).open('wb') as stderr:
  try:
   result=subprocess.run(args,cwd=root,env=env,stdout=stdout,stderr=stderr,timeout=timeout)
   row['returncode']=result.returncode
  except subprocess.TimeoutExpired:
   row['timeout']=True;row['returncode']=None
 row['seconds']=time.monotonic()-start;manifest['commands'].append(row)
 (out/'result.json').write_text(json.dumps(manifest,indent=2)+'\n')
 if row['returncode']!=0:raise RuntimeError(f'{name} failed; retained {out}')
 print('PASS',name,round(row['seconds'],2),flush=True)
try:
 run(['python3','tests/compiler/utf8.py','--self-test-only'],'selftests-normal')
 run(['python3','-O','tests/compiler/utf8.py','--self-test-only'],'selftests-optimized')
 for tag,pin,instrumented in (('release',release,False),('sanitized',san,True)):
  args=['python3','-O','tests/compiler/utf8.py',pin,'--artifacts',out/('utf8-'+tag)]
  if instrumented:args+=['--sanitized-compiler']
  run(args,'utf8-'+tag,instrumented)
  run(['python3','-O','tests/compiler/readonly_spans.py',pin],'readonly-'+tag,instrumented)
  run(['python3','-O','tests/compiler/storage_binary.py',pin],'storage-'+tag,instrumented)
 current={str(p.relative_to(root)):hashfile(p) for p in sorted(paths)}
 if inputs!=current:raise RuntimeError('source input changed during final acceptance')
 manifest['status']='passed'
except Exception as e:
 manifest['status']='failed';manifest['error']=str(e);raise
finally:
 (out/'result.json').write_text(json.dumps(manifest,indent=2)+'\n')
