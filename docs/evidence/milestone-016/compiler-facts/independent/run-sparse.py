import os,time,resource,signal,json
from pathlib import Path
root=Path('/tmp/aurora-facts-independent-review'); results=[]
for label in ('baseline','candidate'):
 start=time.monotonic();pid=os.fork()
 if pid==0:
  resource.setrlimit(resource.RLIMIT_AS,(256*1024*1024,)*2);resource.setrlimit(resource.RLIMIT_CPU,(4,5));resource.setrlimit(resource.RLIMIT_FSIZE,(8*1024*1024,)*2);resource.setrlimit(resource.RLIMIT_CORE,(0,0))
  out=os.open(root/'evidence'/('sparse-'+label+'.stdout'),os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600);err=os.open(root/'evidence'/('sparse-'+label+'.stderr'),os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600);os.dup2(out,1);os.dup2(err,2);os.execl(root/'bin'/('sparse-'+label),label)
 while True:
  waited,status,usage=os.wait4(pid,os.WNOHANG)
  if waited:break
  if time.monotonic()-start>10:os.kill(pid,signal.SIGKILL);_,status,usage=os.wait4(pid,0);break
  time.sleep(0.01)
 row={'label':label,'exit_code':os.waitstatus_to_exitcode(status),'max_rss_kib':usage.ru_maxrss,'seconds':time.monotonic()-start,'user_seconds':usage.ru_utime,'system_seconds':usage.ru_stime,'stdout':(root/'evidence'/('sparse-'+label+'.stdout')).read_text(),'stderr':(root/'evidence'/('sparse-'+label+'.stderr')).read_text()};results.append(row);print(row)
assert all(x['exit_code']==0 and not x['stderr'] for x in results)
assert results[0]['stdout']==results[1]['stdout']
(root/'evidence/sparse-results.json').write_text(json.dumps({'limits':{'address_space_mib':256,'cpu_seconds':[4,5],'wall_seconds':10,'regular_file_mib':8,'core_bytes':0},'results':results},indent=2)+'\n')
