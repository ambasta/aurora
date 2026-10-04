from pathlib import Path
import hashlib,json,os,subprocess,time
out=Path('/tmp/aurora-amd310-independent-review')
root=Path('/workspace/scratch/48c5de6446f8/aurora-dma-tables-candidate/normative')
records=[]
def run(name,args,expected=0,env=None):
 start=time.time_ns();p=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=120,env=env)
 (out/(name+'.log')).write_bytes(p.stdout)
 records.append(dict(name=name,args=args,returncode=p.returncode,expected=expected,start_ns=start,end_ns=time.time_ns()))
 (out/'reviewer-commands.json').write_text(json.dumps(records,indent=2)+'\n')
 assert p.returncode==expected if expected==0 else p.returncode!=0,(name,p.returncode)
 print(name,p.returncode,p.stdout.decode().strip()[:130],flush=True)
flags=['g++','-std=c++23','-O1','-g','-Wall','-Wextra','-Werror']
run('reviewer-compile',flags+[str(out/'reviewer-tests.cpp'),'-o',str(out/'reviewer-tests')])
run('reviewer-execute',[str(out/'reviewer-tests')])
run('reviewer-sanitized-compile',flags+['-fsanitize=address,undefined','-fno-sanitize-recover=all',str(out/'reviewer-tests.cpp'),'-o',str(out/'reviewer-tests-sanitized')])
env=os.environ.copy();env['ASAN_OPTIONS']='detect_leaks=0'
run('reviewer-sanitized-execute',[str(out/'reviewer-tests-sanitized')],env=env)
run('qemu-model',['python3',str(root.parent/'qemu_deny_model.py')])
run('qemu-model-optimized',['python3','-O',str(root.parent/'qemu_deny_model.py')])
mut=out/'public-mutant';mut.mkdir(exist_ok=True)
for p in (root/'include').iterdir():
 s=p.read_text()
 if p.name=='dormant-tables.hpp':s=s.replace('class DormantTables final {','class DormantTables final {\npublic:',1)
 (mut/p.name).write_text(s)
for member,call in [('page','page(0)'),('dte_word','dte_word(0,0)')]:
 for public in [False,True]:
  header=(mut if public else root/'include')/'dormant-tables.hpp'
  for valid,expression in [(False,member),(True,call)]:
   name=f'{member}-'+('public' if public else 'private')+'-'+('valid-call' if valid else 'original-negative')
   source=out/(name+'.cpp')
   source.write_text(f'#include "{header}"\nauto leak(aurora::memory::DormantTables& t) {{return t.{expression};}}\n')
   run(name,flags+[str(source),'-c','-o',str(out/(name+'.o'))],expected=0 if public and valid else 1)
manifest=json.loads((root/'frozen-source-sha256.json').read_text())
assert all(hashlib.sha256((root/p).read_bytes()).hexdigest()==sha for p,sha in manifest.items())
main=root.parents[1]/'aurora'
before=json.loads((out/'main-before.json').read_text())
after={str(p.relative_to(main)):hashlib.sha256(p.read_bytes()).hexdigest() for p in main.rglob('*') if p.is_file()}
(out/'main-after.json').write_text(json.dumps(after,sort_keys=True,indent=2))
changes=[p for p in before.keys()|after.keys() if before.get(p)!=after.get(p)]
(out/'main-change-comparison.json').write_text(json.dumps(changes,indent=2))
print('main changes',changes)
assert not changes
summary={'scope':'independent CPU-only construction review','commands':len(records),'all_expected_statuses':True,'main_files_unchanged':len(after),'frozen_candidate_unchanged':True,'reviewer_assertions_per_run':2178006,'new_finding':'Original page and dte_word compile negatives fail even when methods public; corrected valid calls discriminate.'}
(out/'reviewer-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
