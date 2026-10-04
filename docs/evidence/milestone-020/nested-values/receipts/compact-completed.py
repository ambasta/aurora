#!/usr/bin/env python3
"""Losslessly archive this task's completed generated test artifacts."""
from pathlib import Path
import hashlib,json,shutil,sys,tarfile,time
ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT/'receipts/archives';OUT.mkdir(exist_ok=True)
for name in sys.argv[1:]:
 src=(ROOT/name).resolve()
 if src.parent!=ROOT/'build' or not src.name.startswith(('xfs-geometry-','utf8-native-','utf8-encoding-native-')):raise RuntimeError('outside owned test artifact scope')
 if any(p.is_symlink() for p in src.rglob('*')):raise RuntimeError('symlinks not supported')
 files={str(p.relative_to(ROOT/'build')):hashlib.sha256(p.read_bytes()).hexdigest() for p in src.rglob('*') if p.is_file()}
 total=sum(p.stat().st_size for p in src.rglob('*') if p.is_file())
 dst=OUT/(src.name+'.tar.gz')
 if dst.exists():raise RuntimeError('archive already exists')
 with tarfile.open(dst,'w:gz',compresslevel=6) as tf:tf.add(src,arcname=src.name)
 with tarfile.open(dst,'r:gz') as tf:
  observed={m.name:hashlib.sha256(tf.extractfile(m).read()).hexdigest() for m in tf.getmembers() if m.isfile()}
 if observed!=files:raise RuntimeError('archive verification mismatch')
 if any(hashlib.sha256((ROOT/'build'/name).read_bytes()).hexdigest()!=digest for name,digest in files.items()):raise RuntimeError('source changed during archive')
 record={'original_directory':str(src),'files':files,'original_file_bytes':total,'archive_bytes':dst.stat().st_size,'archive_sha256':hashlib.sha256(dst.read_bytes()).hexdigest(),'verified_all_file_bytes':True}
 (OUT/(src.name+'.json')).write_text(json.dumps(record,indent=2)+'\n')
 shutil.rmtree(src)
 print(src.name,len(files),total,'->',dst.stat().st_size,flush=True)
