#!/usr/bin/env python3
"""Bounded exact-output differential check for ordinary compiler-test calls."""
import json,os,resource,subprocess,sys,tempfile,time
from pathlib import Path
ROOT=Path('/tmp/aurora-facts-independent-review')
args=sys.argv[1:]
if '-o' not in args: raise RuntimeError('differential harness requires explicit output')
i=args.index('-o')+1
output=Path(args[i]); before=output.read_bytes() if output.exists() else None
start=time.monotonic()
def limits():
 resource.setrlimit(resource.RLIMIT_AS,(512*1024*1024,)*2)
 resource.setrlimit(resource.RLIMIT_CPU,(4,5))
 resource.setrlimit(resource.RLIMIT_FSIZE,(8*1024*1024,)*2)
 resource.setrlimit(resource.RLIMIT_CORE,(0,0))
with tempfile.TemporaryDirectory(prefix='diff-output-',dir=ROOT/'evidence') as td:
 baseline=Path(td)/'out.s'
 if before is not None: baseline.write_bytes(before)
 ba=args[:];ba[i]=str(baseline)
 b=subprocess.run([str(ROOT/'bin/baseline'),*ba],capture_output=True,timeout=10,preexec_fn=limits)
 c=subprocess.run([str(ROOT/'bin/candidate'),*args],capture_output=True,timeout=10,preexec_fn=limits)
 b_out=baseline.read_bytes() if baseline.exists() else None
 c_out=output.read_bytes() if output.exists() else None
 if (b.returncode,b.stdout,b.stderr,b_out)!=(c.returncode,c.stdout,c.stderr,c_out):
  (ROOT/'evidence/diff-failure.json').write_text(json.dumps({'args':args,'baseline_returncode':b.returncode,'candidate_returncode':c.returncode,'baseline_stderr':b.stderr.decode(errors='replace'),'candidate_stderr':c.stderr.decode(errors='replace'),'output_equal':b_out==c_out},indent=2));raise RuntimeError('baseline/candidate differed')
 if b.returncode not in (0,1):raise RuntimeError('baseline/candidate did not finish normally')
 with (ROOT/'evidence/differential-calls.jsonl').open('a') as f:f.write(json.dumps({'args':args,'exit_code':c.returncode,'seconds':time.monotonic()-start,'output_bytes':len(c_out) if c_out is not None else None})+'\n')
 sys.stdout.buffer.write(c.stdout);sys.stderr.buffer.write(c.stderr);sys.exit(c.returncode)
