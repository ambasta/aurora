#!/usr/bin/env python3
"""Host-only candidate verification; no emulator/device commands."""
from pathlib import Path
import argparse,hashlib,json,os,subprocess,sys,time
ROOT=Path(__file__).resolve().parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('output',type=Path)
parser.add_argument('--privacy-only',action='store_true')
args=parser.parse_args()
OUT=args.output
OUT.mkdir(parents=True,exist_ok=False)
paths=sorted(p for p in ROOT.rglob('*') if p.is_file())
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
before={str(p.relative_to(ROOT)):digest(p) for p in paths}
(OUT/'inputs-before.json').write_text(json.dumps(before,indent=2)+'\n')
records=[]
def run(name,argv,expected=0,env=None):
 start=time.time_ns();r=subprocess.run(argv,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=120,env=env)
 (OUT/(name+'.log')).write_bytes(r.stdout)
 records.append({'name':name,'argv':argv,'status':r.returncode,'expected':expected,'start_ns':start,'end_ns':time.time_ns()})
 (OUT/'commands.json').write_text(json.dumps(records,indent=2)+'\n')
 if r.returncode!=expected:
  raise RuntimeError(f'{name}:unexpected status{r.returncode}')
 print(name,'PASS',flush=True)
 return r.stdout
flags=['g++','-std=c++23','-O1','-g','-Wall','-Wextra','-Werror']
san=['-fsanitize=address,undefined','-fno-sanitize-recover=all']
env=os.environ.copy();env['ASAN_OPTIONS']='detect_leaks=0'
run('compiler-version',['g++','--version'])
if not args.privacy_only:
 for name,source,extra in [
  ('ownership','ownership-tests.cpp',[]),
  ('independent','independent-decoder-tests.cpp',[]),
  ('generation','generation-tests.cpp',['-DAURORA_PIN_LEDGER_TESTING=1','-DAURORA_PIN_LEDGER_TEST_GENERATION_LIMIT=3']),
  ('production-api','production-api.cpp',[])]:
  for suffix,options in [('',[]),('-sanitized',san)]:
   binary=str(OUT/(name+suffix))
   run(name+suffix+'-compile',flags+options+extra+[source,'-o',binary])
   run(name+suffix+'-execute',[binary],env=env)
 for name,defs in [
  ('test-zero',['-DAURORA_DORMANT_TABLE_TESTING=0']),
  ('small-production-generation',['-DAURORA_PIN_LEDGER_TEST_GENERATION_LIMIT=3']),
  ('zero-generation',['-DAURORA_PIN_LEDGER_TESTING=1','-DAURORA_PIN_LEDGER_TEST_GENERATION_LIMIT=0']),
  ('negative-generation',['-DAURORA_PIN_LEDGER_TESTING=1','-DAURORA_PIN_LEDGER_TEST_GENERATION_LIMIT=-1'])]:
  run(name,flags+defs+['production-api.cpp','-o',str(OUT/name)],expected=1)
# Identical, well-formed member-pointer expressions are compiled against the
# real private class and an isolated mutation with the same region public.
# The positive mutation prevents unrelated syntax/type errors from passing.
public_dir=OUT/'public-control'
public_dir.mkdir()
for header in sorted((ROOT/'include').glob('*.hpp')):
 data=header.read_bytes()
 if header.name=='dormant-tables.hpp':
  needle=b'class DormantTables final {\n'
  if data.count(needle)!=1:raise RuntimeError('ambiguous privacy mutation')
  data=data.replace(needle,needle+b'public:\n',1)
 (public_dir/header.name).write_bytes(data)
privacy_env=env.copy();privacy_env['LC_ALL']='C'
for member in ['pages_','arena_','groups_','dte_word','page','put']:
 source=OUT/('access-'+member+'.cpp')
 source.write_text('#include "dormant-tables.hpp"\nauto expose() { return &aurora::memory::DormantTables::'+member+'; }\n')
 common=[str(source),'-c','-o',str(OUT/('access-'+member+'.o'))]
 run('public-control-'+member,flags+['-I'+str(public_dir)]+common,env=privacy_env)
 diagnostic=run('private-'+member,flags+['-I'+str(ROOT/'include')]+common,expected=1,env=privacy_env)
 if b'private within this context' not in diagnostic:
  raise RuntimeError('missing access-control diagnostic:'+member)
after={str(p.relative_to(ROOT)):digest(p) for p in paths}
(OUT/'inputs-after.json').write_text(json.dumps(after,indent=2)+'\n')
if before!=after:raise RuntimeError('candidate source changed during tests')
main=ROOT.parents[1]/'aurora/kernel'
base=json.loads((ROOT/'baseline-inputs.json').read_text())
for source,value in base.items():
 if digest(main/Path(source).name)!=value:raise RuntimeError('main baseline changed:'+source)
summary={'scope':'CPU-only dormant construction; no hardware operation','privacy_only':args.privacy_only,'commands':len(records),'all_expected_statuses':True,'inputs_unchanged':True,'main_headers_unchanged':True,'receipts':{p.name:digest(p) for p in sorted(OUT.iterdir()) if p.is_file()}}
(OUT/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print('PASS all host-only candidate gates',flush=True)
