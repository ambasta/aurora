from pathlib import Path
import subprocess,os,json,hashlib,time
root=Path('/workspace/scratch/48c5de6446f8/aurora-utf8-encoding-next');out=root/'build/final-acceptance';out.mkdir(exist_ok=False)
h=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
paths=[p for d in ('compiler','library','tests/compiler') for p in (root/d).rglob('*') if p.is_file() and '__pycache__' not in p.parts and (p.suffix in ('.au','.cpp','.hpp','.py') or p.name=='Makefile')]
inputs={str(p.relative_to(root)):h(p) for p in sorted(paths)};(out/'inputs.json').write_text(json.dumps(inputs,indent=2)+'\n');manifest={'status':'running','commands':[]}
def run(args,name,san=False):
 args=list(map(str,args));env=os.environ.copy()
 if san:env['ASAN_OPTIONS']='detect_leaks=0:halt_on_error=1'
 start=time.monotonic()
 with (out/(name+'.stdout')).open('wb') as stdout,(out/(name+'.stderr')).open('wb') as stderr:r=subprocess.run(args,cwd=root,env=env,stdout=stdout,stderr=stderr,timeout=120)
 row={'argv':args,'returncode':r.returncode,'ASAN_OPTIONS':env.get('ASAN_OPTIONS'),'wall_timeout_seconds':120,'seconds':time.monotonic()-start};manifest['commands'].append(row)
 (out/'result.json').write_text(json.dumps(manifest,indent=2)+'\n')
 if r.returncode:raise RuntimeError(name+' failed')
 print('PASS',name,flush=True)
try:
 run(['python3','tests/compiler/utf8_encoding.py','--self-test-only'],'selftests-normal')
 run(['python3','-O','tests/compiler/utf8_encoding.py','--self-test-only'],'selftests-optimized')
 for tag,pin,san in [('release','/tmp/aurora-resource-main-compiler-frozen',False),('sanitized','/tmp/aurora-resource-sanitizer/aurorac',True)]:
  for target in ('test-utf8-encoding','test-utf8'):
   args=['make','-C','compiler',target,'OUT='+pin,'-o',pin]
   if san:args+=['UTF8_TEST_FLAGS=--sanitized-compiler']
   run(args,target+'-'+tag,san)
  run([pin,'--module-root','library','library/examples/utf8_owned_scalar.au','-o',out/(tag+'.s')],'example-compile-'+tag,san)
 if (out/'release.s').read_bytes()!=(out/'sanitized.s').read_bytes():raise RuntimeError('assembly differs')
 run(['as','--64',out/'release.s','-o',out/'example.o'],'example-assemble')
 run(['ld',root/'build/encode-entry.o',out/'example.o','-o',out/'example'],'example-link')
 run([out/'example'],'native-example-42')
 if inputs!={str(p.relative_to(root)):h(p) for p in sorted(paths)}:raise RuntimeError('inputs changed')
 manifest['status']='passed'
except Exception as e:manifest.update(status='failed',error=str(e));raise
finally:(out/'result.json').write_text(json.dumps(manifest,indent=2)+'\n')
