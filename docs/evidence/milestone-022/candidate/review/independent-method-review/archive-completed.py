#!/usr/bin/env python3
"""Archive only this review's completed-successful generated trees.
Verify exact path/type/mode/byte manifests, then remove recoverable duplicates.
Authored scripts/reports and all exploratory/failure trees remain untouched.
"""
import datetime,hashlib,json,os,pathlib,shutil,stat,tarfile
ROOT=pathlib.Path(__file__).resolve().parent
NAMES=['final-release','final-sanitized','array-self','array-self-sanitized','array-capacities-release','array-capacities-sanitized','native-abi-final']
ARCHIVE=ROOT/'completed-successful-output.tar.gz'
if ARCHIVE.exists():raise RuntimeError('refusing to overwrite prior archive')
def manifest():
 result={}
 for name in NAMES:
  top=ROOT/name
  if not top.is_dir() or top.is_symlink():raise RuntimeError('unexpected selected tree '+str(top))
  for p in [top,*sorted(top.rglob('*'))]:
   s=p.lstat();mode=stat.S_IMODE(s.st_mode);rel=p.relative_to(ROOT).as_posix()
   if stat.S_ISDIR(s.st_mode):result[rel]={'type':'directory','mode':mode}
   elif stat.S_ISREG(s.st_mode):result[rel]={'type':'file','mode':mode,'size':s.st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
   else:raise RuntimeError('refusing nonregular path '+rel)
 return result
before=manifest()
with tarfile.open(ARCHIVE,'w:gz',compresslevel=6) as archive:
 for name in NAMES:archive.add(ROOT/name,arcname=name,recursive=True)
observed={}
with tarfile.open(ARCHIVE,'r:gz') as archive:
 for member in archive:
  if member.name in observed:raise RuntimeError('duplicate archive member')
  if pathlib.PurePosixPath(member.name).is_absolute() or '..' in pathlib.PurePosixPath(member.name).parts:raise RuntimeError('unsafe archive path')
  if member.isdir():observed[member.name]={'type':'directory','mode':member.mode}
  elif member.isfile():
   data=archive.extractfile(member).read()
   observed[member.name]={'type':'file','mode':member.mode,'size':len(data),'sha256':hashlib.sha256(data).hexdigest()}
  else:raise RuntimeError('unexpected member type')
if before!=observed:raise RuntimeError('archive differs from complete source manifest')
if before!=manifest():raise RuntimeError('source changed during archive verification')
receipt={'time_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'archive':ARCHIVE.name,'archive_sha256':hashlib.sha256(ARCHIVE.read_bytes()).hexdigest(),'archive_bytes':ARCHIVE.stat().st_size,'selected_trees':NAMES,'verified_members':len(before),'uncompressed_file_bytes':sum(x.get('size',0) for x in before.values()),'manifest':before,'verified_before_removal':True,'expanded_duplicates_removed':False}
RECEIPT=ROOT/'completed-successful-output.manifest.json'
RECEIPT.write_text(json.dumps(receipt,indent=2)+'\n')
for name in NAMES:shutil.rmtree(ROOT/name)
receipt['expanded_duplicates_removed']=all(not (ROOT/name).exists() for name in NAMES)
RECEIPT.write_text(json.dumps(receipt,indent=2)+'\n')
if not receipt['expanded_duplicates_removed']:raise RuntimeError('expanded removal incomplete')
print(json.dumps({k:v for k,v in receipt.items() if k!='manifest'},indent=2))
