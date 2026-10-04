#!/usr/bin/env python3
"""Replay unchanged M020 contract sources against isolated baseline/candidate."""
import hashlib,json,subprocess,sys,tempfile
from pathlib import Path
root=Path(__file__).resolve().parents[1];main=root.parent/'aurora'
sys.path.insert(0,str(main/'tests/compiler'))
import nested_values as old
cases=[]
class Capture:
    def check(self,name,source,expected=42,error=None,modules=None,**kw):
        cases.append((name,source,error is not None,modules or {}))
    def reject(self,name,source,error=True,modules=None):
        if name=='unsupported template-body or template form: function template':return
        self.check(name,source,error=error,modules=modules)
capture=Capture()
old.native_cases(capture,18018,24);old.boundary_cases(capture);old.rejection_cases(capture);old.module_cases(capture);old.trap_and_shift_cases(capture)
rows=[]
with tempfile.TemporaryDirectory(dir=root/'tmp',prefix='m020-diff-') as temporary:
    directory=Path(temporary)
    for index,(name,source,reject,modules) in enumerate(cases):
        case=directory/str(index);case.mkdir();input=case/'input.au';input.write_text(source)
        roots=[]
        if modules:
            module_root=case/'modules';module_root.mkdir();roots=['--module-root',str(module_root)]
            for module,content in modules.items():
                file=module_root/(module.replace('.','/')+'.au');file.parent.mkdir(parents=True,exist_ok=True);file.write_text(content)
        row={'name':name,'source_sha256':hashlib.sha256(source.encode()).hexdigest(),'expected_rejection':reject}
        for label,compiler,library in [('baseline',root/'baseline/aurorac-m020',main/'library'),('candidate',root/'build/aurorac',root/'library')]:
            output=case/(label+'.s')
            result=subprocess.run([str(compiler),str(input),'-o',str(output),*roots,'--module-root',str(library)],capture_output=True,timeout=10)
            row[label]={'status':result.returncode,'assembly_sha256':hashlib.sha256(output.read_bytes()).hexdigest() if output.exists() else None}
        row['match']=row['baseline']==row['candidate']
        rows.append(row)
        if not row['match']:
            target=root/'evidence'/f'baseline-difference-{index}.json';target.write_text(json.dumps({'row':row,'source':source,'modules':modules},indent=2)+'\n')
report={'cases':len(rows),'source_hashes':len(set(r['source_sha256'] for r in rows)),'accepted':sum(r['baseline']['status']==0 for r in rows),'rejected':sum(r['baseline']['status']==1 for r in rows),'all_match':all(r['match'] for r in rows),'intentional_omission':'M020 blanket function-template rejection is now accepted; all other original sources unchanged','rows':rows}
(root/'evidence/m020-contract-comparison-final.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='rows'}))
if not report['all_match']:raise SystemExit(1)
