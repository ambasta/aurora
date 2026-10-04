#!/usr/bin/env python3
"""Old-source and OLD-library compatibility, independent of new library API."""
import hashlib,json,subprocess,tempfile
from pathlib import Path
root=Path(__file__).resolve().parents[1]
main=root.parent/'aurora'
rows=[]
inputs={str(p.relative_to(root/'baseline/library')):hashlib.sha256(p.read_bytes()).hexdigest() for p in (root/'baseline/library').rglob('*') if p.is_file()}
with tempfile.TemporaryDirectory(dir=root/'tmp',prefix='baseline-') as tmp:
 for folder in ('examples','tests/kernel-programs','library/examples'):
  for source in sorted((main/folder).rglob('*.au')):
   rel=source.relative_to(main)
   if not (root/rel).is_file() or (root/rel).read_bytes()!=source.read_bytes():continue
   row={'path':str(rel),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest()}
   for name,compiler in [('baseline',root/'baseline/aurorac-m021'),('candidate',root/'build/aurorac')]:
    output=Path(tmp)/(name+'.s');output.unlink(missing_ok=True)
    result=subprocess.run([str(compiler),'--module-root',str(root/'baseline/library'),str(source),'-o',str(output)],capture_output=True,timeout=15)
    row[name]={'status':result.returncode,'stderr':result.stderr.decode(),'assembly_sha256':hashlib.sha256(output.read_bytes()).hexdigest() if output.exists() else None}
   row['match']=row['baseline']==row['candidate'];rows.append(row)
after={str(p.relative_to(root/'baseline/library')):hashlib.sha256(p.read_bytes()).hexdigest() for p in (root/'baseline/library').rglob('*') if p.is_file()}
result={'cases':len(rows),'accepted':sum(r['baseline']['status']==0 for r in rows),'rejected':sum(r['baseline']['status']!=0 for r in rows),'all_match':all(r['match'] for r in rows),'old_library_unchanged':inputs==after,'old_library_inputs':inputs,'rows':rows}
(root/'evidence/baseline-comparison.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k not in ('rows','old_library_inputs')}))
if not result['all_match'] or not result['old_library_unchanged']:raise SystemExit(1)
