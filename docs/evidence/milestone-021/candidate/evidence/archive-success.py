#!/usr/bin/env python3
"""Losslessly archive only explicitly approved completed-success generated trees."""
import hashlib,json,shutil,stat,tarfile,sys,time
from pathlib import Path
root=Path(__file__).resolve().parents[1]
for arg in sys.argv[1:]:
 path=Path(arg).resolve();path.relative_to(root/'build')
 if path.parent != root/'build' or not path.name.startswith(('xfs-geometry-','utf8-native-','utf8-encoding-native-')):
  raise SystemExit('not an approved generated directory')
 if json.loads((path/'manifest.json').read_text()).get('status')!='passed':raise SystemExit('not completed success')
 records={}
 for p in [path,*sorted(path.rglob('*'))]:
  name=str(p.relative_to(path.parent));st=p.lstat()
  if p.is_symlink() or not (p.is_dir() or p.is_file()):raise SystemExit('unexpected artifact type')
  records[name]={'mode':stat.S_IMODE(st.st_mode),'kind':'directory' if p.is_dir() else 'file','sha256':hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None}
 output=root/'evidence'/f'{path.name}.tar.gz'
 if output.exists():raise SystemExit('archive already exists')
 with tarfile.open(output,'w:gz') as archive:archive.add(path,arcname=path.name,recursive=True)
 with tarfile.open(output,'r:gz') as archive:
  members=archive.getmembers()
  if len(members)!=len(records) or {m.name for m in members}!=set(records):raise SystemExit('archive path mismatch')
  for m in members:
   r=records[m.name]
   if stat.S_IMODE(m.mode)!=r['mode'] or (m.isdir() and r['kind']!='directory') or (m.isfile() and r['kind']!='file'):raise SystemExit('mode/type mismatch')
   if m.isfile() and hashlib.sha256(archive.extractfile(m).read()).hexdigest()!=r['sha256']:raise SystemExit('archive byte mismatch')
 # Recheck originals before dropping recoverable duplicates.
 for name,r in records.items():
  p=path.parent/name
  if stat.S_IMODE(p.stat().st_mode)!=r['mode']:raise SystemExit('original mode changed')
  if r['kind']=='file' and hashlib.sha256(p.read_bytes()).hexdigest()!=r['sha256']:raise SystemExit('original bytes changed')
 receipt={'original_directory':str(path),'archive':str(output),'archive_sha256':hashlib.sha256(output.read_bytes()).hexdigest(),'verified_path_mode_and_bytes':True,'members':records,'duplicate_expanded_directory_removed':False}
 receiptpath=root/'evidence'/f'{path.name}-archive.json';receiptpath.write_text(json.dumps(receipt,indent=2)+'\n')
 shutil.rmtree(path)
 receipt['duplicate_expanded_directory_removed']=True;receiptpath.write_text(json.dumps(receipt,indent=2)+'\n')
 print(path.name,len(records),output.stat().st_size)
