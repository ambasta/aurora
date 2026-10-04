#!/usr/bin/env python3
import hashlib,json,subprocess,tempfile
from pathlib import Path
root=Path(__file__).resolve().parents[1]
main=root.parent/'aurora'
rows=[]
with tempfile.TemporaryDirectory(dir=root/'tmp',prefix='baseline-') as temporary:
    temporary=Path(temporary)
    for folder in ('examples','tests/kernel-programs','library/examples'):
        for source in sorted((main/folder).rglob('*.au')):
            relative=source.relative_to(main)
            candidate=root/relative
            if candidate.read_bytes()!=source.read_bytes():
                continue
            row={'path':str(relative),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest()}
            for name,compiler,library in [('baseline',root/'baseline/aurorac-m020',main/'library'),('candidate',root/'build/aurorac',root/'library')]:
                output=temporary/(name+'.s')
                output.unlink(missing_ok=True)
                result=subprocess.run([str(compiler),'--module-root',str(library),str(source),'-o',str(output)],capture_output=True,timeout=10)
                row[name]={'status':result.returncode,'stderr':result.stderr.decode(),'assembly_sha256':hashlib.sha256(output.read_bytes()).hexdigest() if output.exists() else None}
            row['match']=row['baseline']==row['candidate']
            rows.append(row)
result={'cases':len(rows),'accepted':sum(r['baseline']['status']==0 for r in rows),'rejected':sum(r['baseline']['status']!=0 for r in rows),'all_match':all(r['match'] for r in rows),'rows':rows}
(root/'evidence/baseline-comparison.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k!='rows'}))
if not result['all_match']:raise SystemExit(1)
