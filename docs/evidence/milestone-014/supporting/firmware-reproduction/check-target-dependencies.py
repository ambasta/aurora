from pathlib import Path
import re,json
root=Path('/tmp/aurora-clean-ovmf/edk2')
seen=set(); queue=['OvmfPkg/OvmfPkgX64.dsc','OvmfPkg/OvmfPkgX64.fdf']; unresolved=[];hits=[]
while queue:
 rel=queue.pop()
 if rel in seen:continue
 seen.add(rel)
 p=root/rel
 if not p.is_file():unresolved.append(rel);continue
 s=p.read_text(errors='replace')
 for n,line in enumerate(s.splitlines(),1):
  clean=line.split('#',1)[0]
  if any(x in clean for x in ['UnitTestFrameworkPkg','GoogleTest','Subhook']):hits.append([rel,n,line])
  m=re.match(r'\s*!include\s+(\S+)',clean)
  if m:queue.append(m.group(1))
  for f in re.findall(r'[A-Za-z0-9_.$()/+-]+\.(?:inf|dec)\b',clean):queue.append(f)
report={'method':'Conservative all-branches textual closure: starting at X64 DSC/FDF, recursively include every !include and every INF/DEC path, without dropping disabled branches. Does not compile or execute source.','files_examined':len(seen),'hits':hits,'unresolved':unresolved,'files':sorted(seen)}
Path('/tmp/aurora-clean-ovmf/provenance/target-dependencies.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='files'},indent=2))
