import argparse,hashlib,json,os,pathlib,resource,shutil,signal,stat,subprocess,time
p=argparse.ArgumentParser();p.add_argument('label');p.add_argument('reserve_mib',type=int);p.add_argument('command',nargs=argparse.REMAINDER);a=p.parse_args()
r=pathlib.Path(__file__).resolve().parents[1];w=r/'work';cap=384<<20;floor=1<<30
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def allocated():
 total=0;pending=[r]
 while pending:
  f=pending.pop()
  try:s=f.lstat()
  except FileNotFoundError:continue
  total+=s.st_blocks*512
  if stat.S_ISDIR(s.st_mode):
   try:
    with os.scandir(f) as it:pending.extend(pathlib.Path(x.path) for x in it)
   except FileNotFoundError:continue
 return total
pin='e1953ce8446973194a66ba579809c37459466f746f491a53a98b1c910ef4110e';compiler=r/'build/aurorac';assert sha(compiler)==pin
inputs=json.loads((w/'source-freeze-v2.json').read_text())['files'];assert all(sha(r/x['path'])==x['sha256'] for x in inputs)
used=allocated();reserve=a.reserve_mib<<20
if used+reserve>cap or shutil.disk_usage(r).free-reserve<floor:raise RuntimeError('pre-stage budget admission failed')
env=os.environ.copy();env.update(PYTHONDONTWRITEBYTECODE='1',TMPDIR=str(r/'.tmp'))
receipt={'status':'running','command':a.command,'cwd':str(r),'compiler_sha256':pin,'supervisor_sha256':sha(pathlib.Path(__file__)),'source_freeze_sha256':sha(w/'source-freeze-v2.json'),'source_input_count':len(inputs),'budget_bytes':cap,'reserved_growth_bytes':reserve,'allocated_before':used,'free_before':shutil.disk_usage(r).free,'environment':{'PYTHONDONTWRITEBYTECODE':'1','TMPDIR':str(r/'.tmp')},'start':time.time()}
record=w/(a.label+'.json');assert not record.exists();peak=used;child=None
try:
 with (w/(a.label+'.stdout')).open('xb') as out,(w/(a.label+'.stderr')).open('xb') as err:
  def limit():resource.setrlimit(resource.RLIMIT_CORE,(0,0));resource.setrlimit(resource.RLIMIT_FSIZE,(32<<20,32<<20))
  child=subprocess.Popen(a.command,cwd=r,env=env,stdout=out,stderr=err,start_new_session=True,preexec_fn=limit)
  receipt['pid']=child.pid
  while child.poll() is None:
   used=allocated();peak=max(used,peak)
   if used+(24<<20)>cap or shutil.disk_usage(r).free-(24<<20)<floor:raise RuntimeError('budget reserve reached')
   if time.time()-receipt['start']>1800:raise RuntimeError('gate wall limit')
   time.sleep(2)
  receipt['exit_code']=child.returncode
  if child.returncode:raise RuntimeError('gate nonzero exit')
 assert sha(compiler)==pin
 assert all(sha(r/x['path'])==x['sha256'] for x in inputs)
 receipt['status']='passed'
except BaseException as e:
 receipt.update(status='failed',error=str(e))
 if child is not None and child.poll() is None:
  os.killpg(child.pid,signal.SIGTERM)
  try:child.wait(timeout=10)
  except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait()
 raise
finally:
 receipt.update(end=time.time(),allocated_after=allocated(),peak_allocated=peak,free_after=shutil.disk_usage(r).free,compiler_after=sha(compiler))
 record.write_text(json.dumps(receipt,indent=2)+'\n')
print('PASS',a.label)
