#!/usr/bin/env python3
"""Run frozen release/fatal gates and retain verified successful generated trees."""
import hashlib,json,os,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
EXCLUDE={'build','baseline','tmp','review','evidence','.git','__pycache__'}
def source_inputs():
 return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in ROOT.rglob('*') if p.is_file() and not(set(p.relative_to(ROOT).parts)&EXCLUDE)}
def usage():
 size=sum(p.stat().st_size for p in ROOT.rglob('*') if p.is_file())
 st=os.statvfs(ROOT)
 return {'candidate_bytes':size,'free_bytes':st.f_bavail*st.f_frsize}
def archive_successes():
 for p in sorted((ROOT/'build').iterdir()):
  if not p.is_dir() or not p.name.startswith(('xfs-geometry-','utf8-native-','utf8-encoding-native-')):continue
  manifest=p/'manifest.json'
  if not manifest.exists():continue
  try: status=json.loads(manifest.read_text()).get('status')
  except json.JSONDecodeError:continue
  if status!='passed':continue
  result=subprocess.run(['python3',str(ROOT/'evidence/archive-success.py'),str(p)],capture_output=True,text=True)
  with (ROOT/'evidence/final-gates-archive.log').open('a') as f:f.write(result.stdout+result.stderr)
  if result.returncode:raise RuntimeError('successful artifact archiving failed: '+str(p))
def run(label,command,env):
 start=time.monotonic();before=source_inputs();resources=[usage()]
 (ROOT/'evidence'/f'{label}-before.json').write_text(json.dumps(before,sort_keys=True,indent=2)+'\n')
 with (ROOT/'evidence'/f'{label}.log').open('wb') as log:
  process=subprocess.Popen(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
  while process.poll() is None:
   time.sleep(4)
   archive_successes()
   resources.append(usage())
  status=process.wait()
 archive_successes();resources.append(usage());after=source_inputs()
 (ROOT/'evidence'/f'{label}.status').write_text(str(status)+'\n')
 (ROOT/'evidence'/f'{label}-after.json').write_text(json.dumps(after,sort_keys=True,indent=2)+'\n')
 report={'command':command,'status':status,'elapsed_seconds':time.monotonic()-start,'source_inputs_unchanged':before==after,'resource_observations':resources,'ASAN_OPTIONS':env.get('ASAN_OPTIONS'),'UBSAN_OPTIONS':env.get('UBSAN_OPTIONS'),'runtime_address_space_cap':None,'CXX_build_address_space_bytes':2147483648}
 (ROOT/'evidence'/f'{label}-receipt.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({k:v for k,v in report.items() if k!='resource_observations'}),flush=True)
 if status or before!=after:raise SystemExit(1)
 if any(r['candidate_bytes']>384*1024**2 or r['free_bytes']<1024**3 for r in resources):raise SystemExit('resource envelope exceeded')
env=dict(os.environ,TMPDIR=str(ROOT/'tmp'))
cxx='python3 '+str(ROOT/'evidence/cxx-cap.py')+' g++'
common=['make','-C','compiler','-j1','test','CXX='+cxx]
run('release-final',common,env)
flags='-std=c++23 -O1 -g -fsanitize=address,undefined -fno-sanitize-recover=all -fno-omit-frame-pointer -Wall -Wextra -Wpedantic -Werror'
env.update(ASAN_OPTIONS='detect_leaks=0:halt_on_error=1:abort_on_error=1',UBSAN_OPTIONS='halt_on_error=1:abort_on_error=1:print_stacktrace=1')
run('sanitizer-final',common+['OUT=../build/san/aurorac','CXXFLAGS='+flags,'IR_TEST_CXXFLAGS='+flags.replace(' -g ',' -g1 '),'UTF8_TEST_FLAGS=--sanitized-compiler','XFS_GEOMETRY_TEST_FLAGS=--sanitized-compiler'],env)
