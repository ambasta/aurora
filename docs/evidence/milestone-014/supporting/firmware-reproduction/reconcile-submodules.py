from pathlib import Path
import subprocess, hashlib, json
root=Path('/tmp/aurora-clean-ovmf/edk2')
records=[]
for line in subprocess.check_output(['git','ls-tree','-r','HEAD'],cwd=root,text=True).splitlines():
    meta,path=line.split('\t',1)
    mode,typ,pin=meta.split()
    if mode!='160000': continue
    p=root/path
    if not (p/'.git').exists():
        records.append(dict(path=path,pinned_commit=pin,initialized=False)); continue
    actual=subprocess.check_output(['git','rev-parse','HEAD'],cwd=p,text=True).strip()
    diff=subprocess.check_output(['git','diff','HEAD','--name-only'],cwd=p,text=True)
    tracked=subprocess.check_output(['git','ls-tree','-rz','--name-only','HEAD'],cwd=p).split(b'\0')
    digest=hashlib.sha256(); count=0; missing=[]
    for f in tracked:
        if not f: continue
        q=p/f.decode()
        if not q.is_file():
            missing.append(f.decode()); continue
        digest.update(f+b'\0'+hashlib.sha256(q.read_bytes()).digest()); count+=1
    records.append(dict(path=path,pinned_commit=pin,actual_commit=actual,pin_matches=(actual==pin),tracked_diff=diff,tracked_file_count=count,checkout_populated=(count>0),missing_files=missing,tracked_files_sha256=digest.hexdigest()))
Path('/tmp/aurora-clean-ovmf/provenance/submodule-reconciliation.json').write_text(json.dumps(records,indent=2)+'\n')
print(json.dumps([{k:v for k,v in r.items() if k not in ('missing_files','tracked_diff')} for r in records],indent=2))
