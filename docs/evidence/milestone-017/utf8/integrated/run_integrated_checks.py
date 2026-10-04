from pathlib import Path
import hashlib,json,subprocess,os,time
root=Path('/workspace/scratch/48c5de6446f8/aurora');evidence=root/'docs/evidence/milestone-017/utf8';out=evidence/'integrated';out.mkdir(exist_ok=False);build=root/'build/utf8-integration';build.mkdir(exist_ok=False)
h=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();delta=json.loads((evidence/'integration-delta.json').read_text());protected=json.loads((evidence/'runtime-inputs-before.json').read_text())
records=[];status='running'
def run(args,name,san=False):
 env=os.environ.copy()
 if san:env['ASAN_OPTIONS']='detect_leaks=0:halt_on_error=1'
 args=list(map(str,args));start=time.monotonic()
 result=subprocess.run(args,cwd=root,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=120)
 (out/(name+'.stdout')).write_bytes(result.stdout);(out/(name+'.stderr')).write_bytes(result.stderr)
 row={'name':name,'argv':args,'returncode':result.returncode,'seconds':time.monotonic()-start,'wall_timeout_seconds':120,'ASAN_OPTIONS':env.get('ASAN_OPTIONS')};records.append(row)
 (out/'commands.json').write_text(json.dumps(records,indent=2)+'\n')
 if result.returncode:raise RuntimeError(name+' failed')
 print('PASS',name,flush=True)
try:
 for tag,pin,sanitized in [('release','/tmp/aurora-resource-main-compiler-frozen',False),('sanitized','/tmp/aurora-resource-sanitizer/aurorac',True)]:
  args=['make','-C','compiler','test-utf8','OUT='+pin,'-o',pin]
  if sanitized:args+=['UTF8_TEST_FLAGS=--sanitized-compiler']
  run(args,'target-'+tag,sanitized)
  run([pin,'--module-root','library','library/examples/utf8_scalars.au','-o',build/(tag+'.s')],'example-compile-'+tag,sanitized)
 if (build/'release.s').read_bytes()!=(build/'sanitized.s').read_bytes():raise RuntimeError('example assembly mismatch')
 (build/'entry.s').write_text('.global _start\n.text\n_start:\n call test\n cmp $42, %rax\n jne .Lfail\n xor %edi,%edi\n jmp .Lexit\n.Lfail:\n mov $1,%edi\n.Lexit:\n mov $60,%eax\n syscall\n.section .note.GNU-stack,"",@progbits\n')
 run(['as','--64',build/'release.s','-o',build/'library.o'],'assemble-library')
 run(['as','--64',build/'entry.s','-o',build/'entry.o'],'assemble-entry')
 run(['ld',build/'entry.o',build/'library.o','-o',build/'example'],'link-example')
 run([build/'example'],'native-example-42')
 if any(h(root/r['path'])!=r['sha256'] for r in delta['files']):raise RuntimeError('delta changed')
 if any(h(root/p)!=sha for p,sha in protected.items()):raise RuntimeError('existing runtime source changed')
 status='passed'
finally:
 (out/'result.json').write_text(json.dumps({'status':status,'commands':records,'input_delta':'../integration-delta.json','existing_runtime_inputs':'../runtime-inputs-before.json','example_observation':'exit0 requires full64-bit result42; assembly identical from release and sanitized compiler','compiler_hashes':{p:h(Path(p)) for p in ['/tmp/aurora-resource-main-compiler-frozen','/tmp/aurora-resource-sanitizer/aurorac']}},indent=2)+'\n')
