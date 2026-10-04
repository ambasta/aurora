import importlib.util,json
from pathlib import Path
root=Path('/workspace/scratch/48c5de6446f8/aurora-resource-next');out=Path('/tmp/aurora-facts-independent-review/evidence/source-sparse');out.mkdir(exist_ok=False)
spec=importlib.util.spec_from_file_location('measure',root/'diagnostics/compare_readonly_resources.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
results=[]
for arrays in [1,4,16]:
 p=out/f'sparse-prefix-{arrays}.au';p.write_text('module sparse_prefix;auto test()->i64{'+('if(true){}else{}'*512)+''.join(f'const array<u8,4096> a{i}={{'+','.join(['0u8']*4096)+'};' for i in range(arrays))+'return 42;}')
 row={'arrays':arrays,'declared_u8_slots':arrays*4096,'branch_diamonds':512,'source_bytes':p.stat().st_size}
 for label in ['baseline','candidate']:
  row[label]=m.compile_one(Path('/tmp/aurora-facts-independent-review/bin')/label,p,out/(p.stem+'-'+label+'.s'),root/'library',512)
  print(arrays,label,row[label]['exit_code'],row[label]['max_rss_kib'],row[label]['wall_seconds'],flush=True)
 row['assembly_identical']=(row['baseline']['assembly_sha256']==row['candidate']['assembly_sha256']) if row['baseline']['exit_code']==row['candidate']['exit_code']==0 else None
 if row['baseline']['exit_code']==row['candidate']['exit_code']==0:assert row['assembly_identical']
 results.append(row);(out/'results.json').write_text(json.dumps({'limits':{'address_space_mib':512,'cpu_seconds':[4,5],'wall_seconds':10,'regular_file_mib':8,'core_bytes':0},'results':results},indent=2)+'\n')
