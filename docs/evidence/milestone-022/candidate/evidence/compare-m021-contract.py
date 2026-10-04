#!/usr/bin/env python3
"""Replay untouched M021 template sources against both compilers and old library."""
import hashlib,json,subprocess,sys,tempfile
from pathlib import Path
root=Path(__file__).resolve().parents[1];main=root.parent/'aurora'
sys.path.insert(0,str(main/'tests/compiler'))
import function_templates as old
print([n for n in dir(old) if n.endswith('_cases')])
cases=[]
class Capture:
 def check(self,name,source,expected=42,error=None,modules=None,**kw):cases.append((name,source,error is not None,modules or {}))
 def reject(self,name,source,error=True,modules=None):self.check(name,source,error=error,modules=modules)
c=Capture();old.native_cases(c,21021,24);old.boundary_cases(c);old.rejection_cases(c);old.module_cases(c);old.trap_cases(c)
rows=[]
with tempfile.TemporaryDirectory(dir=root/'tmp',prefix='m021-diff-') as tmp:
 for index,(name,source,reject,modules) in enumerate(cases):
  directory=Path(tmp)/str(index);directory.mkdir();input=directory/'input.au';input.write_text(source)
  roots=[]
  if modules:
   module_root=directory/'modules';module_root.mkdir();roots=['--module-root',str(module_root)]
   for module,content in modules.items():
    file=module_root/(module.replace('.','/')+'.au');file.parent.mkdir(parents=True,exist_ok=True);file.write_text(content)
  row={'name':name,'source_sha256':hashlib.sha256(source.encode()).hexdigest(),'expected_rejection':reject}
  for label,compiler in [('baseline',root/'baseline/aurorac-m021'),('candidate',root/'build/aurorac')]:
   output=directory/(label+'.s')
   result=subprocess.run([str(compiler),str(input),'-o',str(output),*roots,'--module-root',str(root/'baseline/library')],capture_output=True,timeout=15)
   row[label]={'status':result.returncode,'assembly_sha256':hashlib.sha256(output.read_bytes()).hexdigest() if output.exists() else None}
  row['match']=row['baseline']==row['candidate'];rows.append(row)
  if not row['match']:(root/'evidence'/f'baseline-difference-{index}.json').write_text(json.dumps({'row':row,'source':source,'modules':modules},indent=2)+'\n')
report={'cases':len(rows),'source_hashes':len(set(r['source_sha256'] for r in rows)),'accepted':sum(r['baseline']['status']==0 for r in rows),'rejected':sum(r['baseline']['status']==1 for r in rows),'all_match':all(r['match'] for r in rows),'library':'pinned baseline/library for BOTH compilers','intentional_omissions':[],'rows':rows}
(root/'evidence/m021-contract-comparison.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='rows'}))
if not report['all_match']:raise SystemExit(1)
