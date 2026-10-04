#!/usr/bin/env python3
"""Run one serial build with explicit limits and an exact-status receipt."""
from pathlib import Path
import hashlib,json,os,resource,signal,subprocess,sys,time,shutil
ROOT=Path(__file__).resolve().parent.parent
LIMIT=2*1024**3
budget=384*1024**2
retained=1536*1024**2
used=sum(p.stat().st_size for p in ROOT.rglob('*') if p.is_file())
if used>budget or shutil.disk_usage(ROOT).free<retained:
 print('candidate disk budget or retained free-space gate failed',file=sys.stderr);sys.exit(90)
args=['g++',*sys.argv[1:]]
start=time.monotonic()
def limits():
 resource.setrlimit(resource.RLIMIT_CORE,(0,0))
 resource.setrlimit(resource.RLIMIT_AS,(LIMIT,LIMIT))
 resource.setrlimit(resource.RLIMIT_CPU,(120,130))
 resource.setrlimit(resource.RLIMIT_FSIZE,(512*1024**2,512*1024**2))
child=subprocess.Popen(args,preexec_fn=limits,start_new_session=True)
expired=False
while True:
 pid,status,usage=os.wait4(child.pid,os.WNOHANG)
 if pid: break
 if time.monotonic()-start>180:
  expired=True;os.killpg(child.pid,signal.SIGKILL)
 time.sleep(.1)
code=os.waitstatus_to_exitcode(status);child.returncode=code
record={'command':args,'returncode':code,'wait_status':status,'wall_timeout':expired,'elapsed_seconds':time.monotonic()-start,'peak_rss_kib':usage.ru_maxrss,'cpu_user_seconds':usage.ru_utime,'cpu_system_seconds':usage.ru_stime,'address_space_bytes':LIMIT,'cpu_seconds':[120,130],'wall_seconds':180,'regular_file_bytes':512*1024**2,'candidate_bytes_before':used,'candidate_bytes_after':sum(p.stat().st_size for p in ROOT.rglob('*') if p.is_file()),'free_bytes_after':shutil.disk_usage(ROOT).free}
(ROOT/'receipts'/f'build-{time.time_ns()}.json').write_text(json.dumps(record,indent=2)+'\n')
if record['candidate_bytes_after']>budget or record['free_bytes_after']<retained:
 print('candidate disk budget exceeded after build',file=sys.stderr);sys.exit(90)
sys.exit(code if code>=0 else 128-code)
