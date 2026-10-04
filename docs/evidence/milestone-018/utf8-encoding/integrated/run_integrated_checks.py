from pathlib import Path
import hashlib,json,subprocess,os,time
root=Path('/workspace/scratch/48c5de6446f8/aurora');evidence=root/'docs/evidence/milestone-018/utf8-encoding';out=evidence/'integrated';out.mkdir(exist_ok=False);build=root/'build/utf8-encoding-integration';build.mkdir(exist_ok=False);h=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
manifest={'status':'running','commands':[]};delta=json.loads((evidence/'integration-delta.json').read_text());protected=json.loads((evidence/'unchanged-inputs.json').read_text())
def run(args,name,san=False):
 args=list(map(str,args));env=os.environ.copy()
 if san:env['ASAN_OPTIONS']='detect_leaks=0:halt_on_error=1'
 row={'name':name,'argv':args,'wall_timeout_seconds':120,'ASAN_OPTIONS':env.get('ASAN_OPTIONS')};start=time.monotonic()
 with (out/(name+'.stdout')).open('wb') as stdout,(out/(name+'.stderr')).open('wb') as stderr:
  try:result=subprocess.run(args,cwd=root,env=env,stdout=stdout,stderr=stderr,timeout=120);row['returncode']=result.returncode
  except subprocess.TimeoutExpired:row.update(returncode=None,timeout=True)
 row['seconds']=time.monotonic()-start;manifest['commands'].append(row);(out/'result.json').write_text(json.dumps(manifest,indent=2)+'\n')
 if row['returncode']!=0:raise RuntimeError(name+' failed')
 print('PASS',name,flush=True)
try:
 for tag,pin,san in [('release','/tmp/aurora-resource-main-compiler-frozen',False),('sanitized','/tmp/aurora-resource-sanitizer/aurorac',True)]:
  for target in ('test-utf8-encoding','test-utf8'):
   args=['make','-C','compiler',target,'OUT='+pin,'-o',pin]
   if san:args+=['UTF8_TEST_FLAGS=--sanitized-compiler']
   run(args,target+'-'+tag,san)
  run([pin,'--module-root','library','library/examples/utf8_owned_scalar.au','-o',build/(tag+'.s')],'example-compile-'+tag,san)
 if (build/'release.s').read_bytes()!=(build/'sanitized.s').read_bytes():raise RuntimeError('example assembly mismatch')
 (build/'entry.s').write_text('.global _start\n.text\n_start:\n call test\n cmp $42,%rax\n jne .Lfail\n xor %edi,%edi\n jmp .Lexit\n.Lfail:\n mov $1,%edi\n.Lexit:\n mov $60,%eax\n syscall\n.section .note.GNU-stack,"",@progbits\n')
 run(['as','--64',build/'release.s','-o',build/'example.o'],'assemble-library')
 run(['as','--64',build/'entry.s','-o',build/'entry.o'],'assemble-entry')
 run(['ld',build/'entry.o',build/'example.o','-o',build/'example'],'link-example')
 run([build/'example'],'native-example-42')
 if any(h(root/r['path'])!=r['sha256'] for r in delta['files']):raise RuntimeError('delta changed')
 if any(h(root/p)!=sha for p,sha in protected.items()):raise RuntimeError('protected input changed')
 manifest['status']='passed';manifest['entry_source_sha256']=h(build/'entry.s');manifest['compiler_hashes']={p:h(Path(p)) for p in ['/tmp/aurora-resource-main-compiler-frozen','/tmp/aurora-resource-sanitizer/aurorac']}
except Exception as e:manifest.update(status='failed',error=str(e));raise
finally:(out/'result.json').write_text(json.dumps(manifest,indent=2)+'\n')
