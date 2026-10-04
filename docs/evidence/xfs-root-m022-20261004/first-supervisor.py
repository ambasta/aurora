import pathlib,json,hashlib,subprocess,os,time,signal,shutil,resource
w=pathlib.Path(__file__).resolve().parent;root=w.parent/'aurora-xfs-m022-integration-20261004';cap=512<<20;floor=1<<30
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();alloc=lambda p:p.lstat().st_blocks*512+sum(x.lstat().st_blocks*512 for x in p.rglob('*'))
def usage():return sum(alloc(p) for p in [root,w,w.parent/'xfs-recovery'])
prep=json.loads((w/'PREPARED-SOURCE.json').read_text());compiler=root/'build/aurorac';pin=prep['compiler_sha256']
pins={str(p.relative_to(root)):sha(p) for p in root.rglob('*') if p.is_file() and 'build' not in p.relative_to(root).parts and '.tmp' not in p.relative_to(root).parts}
if sha(compiler)!=pin:raise RuntimeError('baseline compiler mismatch')
if usage()+(384<<20)>cap or shutil.disk_usage(root).free-(384<<20)<floor:raise RuntimeError('aggregate admission')
args=['make','test','XFS_ROOT_COMPILER_SHA256='+pin];env=os.environ.copy();env.update(PYTHONDONTWRITEBYTECODE='1',TMPDIR=str(root/'.tmp'))
r={'status':'running','argv':args,'cwd':str(root),'compiler_before':pin,'source_pins_before':pins,'time_start':time.time(),'budget_bytes':cap,'reserved_growth_bytes':384<<20,'allocation_before':usage(),'global_free_before':shutil.disk_usage(root).free,'environment':{'PYTHONDONTWRITEBYTECODE':'1','TMPDIR':str(root/'.tmp')},'emulator_gate':'not requested or run; top-level make test only'}
record=w/'PARENT-MAKE-TEST.json'
if record.exists():raise RuntimeError('fresh receipt required')
def limits():resource.setrlimit(resource.RLIMIT_CORE,(0,0));resource.setrlimit(resource.RLIMIT_FSIZE,(32<<20,32<<20))
peak=usage()
try:
 with (w/'parent-make-test.stdout').open('xb') as out,(w/'parent-make-test.stderr').open('xb') as err:
  proc=subprocess.Popen(args,cwd=root,env=env,stdout=out,stderr=err,start_new_session=True,preexec_fn=limits)
  while proc.poll() is None:
   used=usage();peak=max(peak,used)
   if used+(64<<20)>cap or shutil.disk_usage(root).free-(64<<20)<floor:
    os.killpg(proc.pid,signal.SIGTERM);proc.wait();raise RuntimeError('aggregate output reserve reached; retained partial outputs')
   if time.time()-r['time_start']>1800:
    os.killpg(proc.pid,signal.SIGTERM);proc.wait();raise RuntimeError('aggregate wall budget exceeded')
   time.sleep(2)
  r['exit_code']=proc.returncode
 if proc.returncode:raise RuntimeError('parent make test failed')
 if sha(compiler)!=pin:raise RuntimeError('M022 compiler changed')
 if pins!={rel:sha(root/rel) for rel in pins}:raise RuntimeError('test inputs changed')
 r['status']='passed'
except Exception as e:r['error']=str(e);raise
finally:
 r.update(time_end=time.time(),allocation_after=usage(),peak_allocation_bytes=peak,compiler_after=sha(compiler),global_free_after=shutil.disk_usage(root).free,stdout_sha256=sha(w/'parent-make-test.stdout'),stderr_sha256=sha(w/'parent-make-test.stderr'));record.write_text(json.dumps(r,indent=2)+'\n')
print('PASS fresh XFS-only M022 parent make test')
