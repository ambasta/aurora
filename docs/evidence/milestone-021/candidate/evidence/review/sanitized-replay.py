#!/usr/bin/env python3
from pathlib import Path
import os,subprocess,json,hashlib,resource,time
ROOT=Path(__file__).resolve().parents[2];D=ROOT/'evidence/review';OUT=D/'sanitized-replay';OUT.mkdir(exist_ok=True)
C=ROOT/'build/san/aurorac';PIN='423db8bcf0642263e445582107c73f967decdc13132f2bd98a973fce2db03d0f'
assert hashlib.sha256(C.read_bytes()).hexdigest()==PIN
ENV=dict(os.environ,ASAN_OPTIONS='detect_leaks=0:halt_on_error=1:abort_on_error=1',UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1:abort_on_error=1')
PRESERVED=b'unchanged release-reviewed output\x00\xff\n'
records=[]
def invoke(cmd):
 return subprocess.run(cmd,capture_output=True,timeout=60,env=ENV,preexec_fn=lambda:resource.setrlimit(resource.RLIMIT_CORE,(0,0)))
for sub in ['independent','extra','member-regression']:
 release=json.loads((D/sub/'results.json').read_text())
 assert release['compiler_sha256']=='d866abc707349ca8652a966800d38bd920bd41345997f08e4b849c9bfc3b7b64'
 for row in release['results']:
  d=OUT/sub/row['name'];d.mkdir(parents=True,exist_ok=True)
  source=Path(row['command'][-3]); # command ends INPUT -o OUTPUT
  inputs={str(source):hashlib.sha256(source.read_bytes()).hexdigest()}
  module_dir=source.parent/'modules'
  for p in module_dir.rglob('*.au'):inputs[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
  cmd=list(row['command']);cmd[0]=str(C);cmd[cmd.index('-o')+1]=str(d/'compiled.s')
  output=d/'compiled.s';output.write_bytes(PRESERVED)
  start=time.time();x=invoke(cmd)
  result={'name':row['name'],'source_group':sub,'negative':row['negative'],'command':cmd,'compiler_status':x.returncode,'compiler_stderr':x.stderr.decode(),'seconds':time.time()-start,'release_evidence':str(D/sub/row['name']/'result.json'),'input_sha256':inputs}
  (d/'stdout.bin').write_bytes(x.stdout);(d/'stderr.bin').write_bytes(x.stderr)
  result['pass']=x.returncode==(1 if row['negative'] else 0) and x.stderr.decode()==row['stderr']
  if row['negative']:
   result['existing_output_preserved']=output.read_bytes()==PRESERVED
   result['pass'] &= result['existing_output_preserved']
   absent=d/'absent.s';assert not absent.exists()
   second=list(cmd);second[second.index('-o')+1]=str(absent);y=invoke(second)
   result['absent_replay']={'command':second,'status':y.returncode,'diagnostic':y.stderr.decode(),'absent':not absent.exists()}
   result['pass'] &= y.returncode==1 and y.stderr.decode()==row['stderr'] and not absent.exists()
  elif result['pass']:
   # Same freestanding eight-byte return observer from the release fixture.
   entry=source.parent/'entry.s';result['observer_sha256']=hashlib.sha256(entry.read_bytes()).hexdigest()
   for acmd in [['as',str(output),'-o',str(d/'compiled.o')],['as',str(entry),'-o',str(d/'entry.o')],['ld',str(d/'entry.o'),str(d/'compiled.o'),'-o',str(d/'native')]]:
    a=invoke(acmd)
    if a.returncode:result['pass']=False;result['native_build_error']={'command':acmd,'status':a.returncode,'diagnostic':a.stderr.decode()};break
   if result['pass']:
    native=invoke([str(d/'native')]);result['native_status']=native.returncode;result['native_hex']=native.stdout.hex();result['expected']=row['expected']
    result['pass'] &= native.returncode==0 and len(native.stdout)==8 and int.from_bytes(native.stdout,'little')==row['expected']%(1<<64)
  result['inputs_unchanged']=all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in inputs.items());result['pass'] &=result['inputs_unchanged']
  (d/'result.json').write_text(json.dumps(result,indent=2)+'\n');records.append(result)
  print(('PASS' if result['pass'] else 'FAIL'),sub,row['name'],flush=True)
summary={'compiler_sha256':PIN,'compiler_after_sha256':hashlib.sha256(C.read_bytes()).hexdigest(),'asan_options':ENV['ASAN_OPTIONS'],'ubsan_options':ENV['UBSAN_OPTIONS'],'same_fixture_overlapping_coverage':True,'fixtures':len(records),'native_positives':sum(not x['negative'] for x in records),'negative_fixtures':sum(x['negative'] for x in records),'extra_absent_output_compilations':sum(x['negative'] for x in records),'passed':sum(x['pass'] for x in records),'all_passed':all(x['pass'] for x in records),'results':records}
(OUT/'results.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps({k:v for k,v in summary.items() if k!='results'},indent=2))
assert summary['compiler_after_sha256']==PIN and summary['all_passed']
