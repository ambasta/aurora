from pathlib import Path
import json,hashlib,os,subprocess,time
root=Path('/workspace/scratch/48c5de6446f8/aurora');evidence=root/'docs/evidence/milestone-019/xfs-geometry';out=evidence/'integrated';out.mkdir(exist_ok=False);build=root/'build/xfs-geometry-integration';build.mkdir(exist_ok=False);h=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();delta=json.loads((evidence/'integration-delta.json').read_text());protected=json.loads((evidence/'protected-inputs.json').read_text());result={'status':'running','commands':[]}
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
 for tag,pin,san in [('release','/tmp/aurora-resource-main-compiler-frozen',False),('sanitized','/tmp/aurora-resource-sanitizer/aurorac',True)]:
  flags='--compiler-sha256 '+h(Path(pin))+(' --sanitized-compiler' if san else '')
  run(['make','-C','compiler','test-xfs-geometry','OUT='+pin,'-o',pin,'XFS_GEOMETRY_TEST_FLAGS='+flags],'geometry-'+tag,san)
  run(['make','-C','compiler','test-storage','OUT='+pin,'-o',pin],'old-storage-'+tag,san)
  run([pin,'--module-root','library','library/examples/xfs_geometry.au','-o',build/(tag+'.s')],'example-compile-'+tag,san)
 if (build/'release.s').read_bytes()!=(build/'sanitized.s').read_bytes():raise RuntimeError('example assembly differs')
 (build/'entry.s').write_text('.global _start\n.text\n_start:\n call test\n cmp $42,%rax\n jne .Lfail\n xor %edi,%edi\n jmp .Lexit\n.Lfail:\n mov $1,%edi\n.Lexit:\n mov $60,%eax\n syscall\n.section .note.GNU-stack,"",@progbits\n')
 run(['as','--64',build/'release.s','-o',build/'example.o'],'assemble-example')
 run(['as','--64',build/'entry.s','-o',build/'entry.o'],'assemble-entry')
 run(['ld',build/'entry.o',build/'example.o','-o',build/'example'],'link-example')
 run([build/'example'],'native-example-42')
 if any(h(root/r['path'])!=r['sha256'] for r in delta['files']):raise RuntimeError('delta drift')
 if any(h(root/p)!=sha for p,sha in protected.items()):raise RuntimeError('protected compiler/library input drift')
 result['status']='passed';result['entry_source_sha256']=h(build/'entry.s');result['compiler_hashes']={p:h(Path(p)) for p in ['/tmp/aurora-resource-main-compiler-frozen','/tmp/aurora-resource-sanitizer/aurorac']}
except Exception as e:result.update(status='failed',error=str(e));raise
finally:(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
