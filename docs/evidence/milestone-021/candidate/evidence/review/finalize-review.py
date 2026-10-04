from pathlib import Path
import subprocess,json,hashlib
R=Path(__file__).resolve().parents[2];D=R/'evidence/review';C=D/'aurorac-reviewed-final'
results=[]
for sub in ['independent','extra','member-regression']:
 rows=json.loads((D/sub/'results.json').read_text())['results'];results.extend(rows)
absent=[]
for row in results:
 if not row['negative']:continue
 cmd=list(row['command']);cmd[0]=str(C);out=Path(cmd[cmd.index('-o')+1]);new=out.with_name('absent-output.s');cmd[cmd.index('-o')+1]=str(new)
 if new.exists():new.unlink()
 x=subprocess.run(cmd,capture_output=True,timeout=15)
 absent.append({'name':row['name'],'command':cmd,'status':x.returncode,'diagnostic':x.stderr.decode(),'absent':not new.exists(),'pass':x.returncode==1 and not new.exists()})
(D/'negative-absent-results.json').write_text(json.dumps(absent,indent=2)+'\n')
# Independent frozen-baseline assembly/status comparisons.
diff=[]
for src in sorted((R.parent/'aurora/examples').glob('*.au')):
 row={'source':str(src),'source_sha256':hashlib.sha256(src.read_bytes()).hexdigest()}
 for tag,comp,lib in [('baseline',R/'baseline/aurorac-m020',R.parent/'aurora/library'),('final',C,R/'library')]:
  out=D/'baseline-differential'/(src.stem+'-'+tag+'.s');cmd=[str(comp),'--module-root',str(lib),str(src),'-o',str(out)];x=subprocess.run(cmd,capture_output=True,timeout=15)
  row[tag]={'command':cmd,'status':x.returncode,'diagnostic':x.stderr.decode(),'assembly_sha256':hashlib.sha256(out.read_bytes()).hexdigest() if out.exists() else None}
 row['pass']=all(row['baseline'][k]==row['final'][k] for k in ['status','assembly_sha256']);diff.append(row)
(D/'baseline-differential/final-results.json').write_text(json.dumps(diff,indent=2)+'\n')
reg=[]
for pin in ['original','corrected','final']:
 for probe in ['qualified-shadow','member-shadow']:
  out=D/(probe+'-'+pin+'-reproduction.s');out.write_bytes(b'unchanged-output\n')
  cmd=[str(D/('aurorac-reviewed-'+pin)),str(D/(probe+'.au')),'-o',str(out)];x=subprocess.run(cmd,capture_output=True,timeout=15)
  reg.append({'pin':pin,'probe':probe,'command':cmd,'returncode':x.returncode,'diagnostic':x.stderr.decode(),'output_preserved':out.read_bytes()==b'unchanged-output\n'})
(D/'defect-reproduction-matrix.json').write_text(json.dumps(reg,indent=2)+'\n')
summary={'final_compiler_sha256':hashlib.sha256(C.read_bytes()).hexdigest(),'unique_fixture_count':len(results),'native_positive_count':sum(not r['negative'] for r in results),'negative_count':sum(r['negative'] for r in results),'all_fixtures_pass':all(r['pass'] for r in results),'extra_negative_absent_executions':len(absent),'all_absent_pass':all(r['pass'] for r in absent),'baseline_cases':len(diff),'all_baseline_byte_exact':all(r['pass'] for r in diff)}
(D/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
