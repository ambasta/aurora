from pathlib import Path
import json,hashlib,os,subprocess,time
root=Path('/workspace/scratch/48c5de6446f8/aurora-xfs-geometry-next');out=root/'build/final-acceptance';out.mkdir(exist_ok=False);h=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
paths=[p for d in ('compiler','library','tests','fixtures/xfs-offline') for p in (root/d).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix in ('.cpp','.hpp','.au','.py','.hex')];paths.append(root/'compiler/Makefile');inputs={str(p.relative_to(root)):h(p) for p in sorted(paths)};(out/'inputs.json').write_text(json.dumps(inputs,indent=2)+'\n');result={'status':'running','commands':[]}
def run(args,name,san=False):
 args=list(map(str,args));env=os.environ.copy()
 if san:env['ASAN_OPTIONS']='detect_leaks=0:halt_on_error=1'
 r={'name':name,'argv':args,'wall_timeout_seconds':300,'ASAN_OPTIONS':env.get('ASAN_OPTIONS')};start=time.monotonic()
 with (out/(name+'.stdout')).open('wb') as stdout,(out/(name+'.stderr')).open('wb') as stderr:
  try:p=subprocess.run(args,cwd=root,env=env,stdout=stdout,stderr=stderr,timeout=300);r['returncode']=p.returncode
  except subprocess.TimeoutExpired:r.update(returncode=None,timeout=True)
 r['seconds']=time.monotonic()-start;result['commands'].append(r);(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
 if r['returncode']!=0:raise RuntimeError(name+' failed')
 print('PASS',name,flush=True)
try:
 for opt in ([],['-O']):run(['python3',*opt,'tests/compiler/xfs_geometry.py','--self-test-only'],'selftests-'+('optimized' if opt else 'normal'))
 for tag,pin,san in [('release','/tmp/aurora-resource-main-compiler-frozen',False),('sanitized','/tmp/aurora-resource-sanitizer/aurorac',True)]:
  flags='--compiler-sha256 '+h(Path(pin))+(' --sanitized-compiler' if san else '')
  run(['make','-C','compiler','test-xfs-geometry','OUT='+pin,'-o',pin,'XFS_GEOMETRY_TEST_FLAGS='+flags],'geometry-'+tag,san)
  run(['make','-C','compiler','test-storage','OUT='+pin,'-o',pin],'old-storage-'+tag,san)
  run([pin,'--module-root','library','library/examples/xfs_geometry.au','-o',out/(tag+'.s')],'example-compile-'+tag,san)
 if (out/'release.s').read_bytes()!=(out/'sanitized.s').read_bytes():raise RuntimeError('example assembly differs')
 run(['as','--64',out/'release.s','-o',out/'example.o'],'assemble-example')
 run(['as','--64','build/example-entry.s','-o',out/'entry.o'],'assemble-entry')
 run(['ld',out/'entry.o',out/'example.o','-o',out/'example'],'link-example')
 run([out/'example'],'native-example-42')
 if inputs!={str(p.relative_to(root)):h(p) for p in sorted(paths)}:raise RuntimeError('input drift')
 result['status']='passed';result['entry_source_sha256']=h(root/'build/example-entry.s')
except Exception as e:result.update(status='failed',error=str(e));raise
finally:(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
