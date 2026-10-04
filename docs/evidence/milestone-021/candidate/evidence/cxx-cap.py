#!/usr/bin/env python3
"""Serial trusted-vendor C++ build cap. ASan runtimes are not wrapped."""
import fcntl, json, os, resource, signal, subprocess, sys, time
from pathlib import Path
root=Path(__file__).resolve().parents[1]
lock=(root/'evidence/cxx-build.lock').open('a')
fcntl.flock(lock,fcntl.LOCK_EX)
budget=384*1024*1024
floor=1024*1024*1024
def usage():
    size=sum(p.stat().st_size for p in root.rglob('*') if p.is_file())
    st=os.statvfs(root)
    return size, st.f_bavail*st.f_frsize
before,free=usage()
if before>budget or free<floor:
    raise SystemExit('candidate disk budget or free-space floor prevents build')
def limits():
    os.setsid()
    resource.setrlimit(resource.RLIMIT_AS,(2*1024**3,2*1024**3))
    resource.setrlimit(resource.RLIMIT_CPU,(120,130))
    resource.setrlimit(resource.RLIMIT_FSIZE,(512*1024**2,512*1024**2))
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
start=time.monotonic(); timed=False
process=subprocess.Popen(sys.argv[1:],preexec_fn=limits)
try:
    status=process.wait(timeout=180)
except subprocess.TimeoutExpired:
    timed=True;os.killpg(process.pid,signal.SIGKILL);status=process.wait()
after,free=usage()
receipt={'command':sys.argv[1:],'returncode':status,'wall_timeout':timed,'elapsed_seconds':time.monotonic()-start,'peak_rss_kib':resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,'address_space_bytes':2*1024**3,'cpu_seconds':[120,130],'wall_seconds':180,'regular_file_bytes':512*1024**2,'candidate_bytes_before':before,'candidate_bytes_after':after,'free_bytes_after':free}
(root/'evidence'/f'build-{time.time_ns()}.json').write_text(json.dumps(receipt,indent=2)+'\n')
if after>budget or free<floor:
    raise SystemExit('candidate exceeded disk budget or free-space floor')
sys.exit(status if status>=0 else 128-status)
