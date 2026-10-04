#!/usr/bin/env python3
import argparse,json,hashlib,sys
from pathlib import Path
sys.dont_write_bytecode=True
from review_oracle import *
from review_native import run,enum_functions,expressions,entry,GROUP_TYPES

def main():
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--compiler',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
 b=fixture(a.root/'fixtures/xfs-offline/superblock-v5-512.hex');array='const array<u8,512> bytes={'+','.join(f'{x}u8' for x in b)+'};const builtin::span<const u8> view=borrow_bytes(bytes);'
 imports='module review_api;import fs.xfs_geometry;import fs.xfs_probe;'
 decl,expr=expressions()
 life=imports+enum_functions()+'auto returned_report()->fs::XfsGeometryReport{'+array+'const fs::XfsGeometryReport result=fs::inspect_xfs_v5_512_geometry(view);return result;}\n'
 life+='auto case_0(i64 index)->u64{const fs::XfsGeometryReport parent=returned_report();const fs::XfsGeometryReport r=parent;'+decl
 for i,e in enumerate(expr):life+=f'if(index=={i}){{return {e};}}'
 life+='if(index==42){return u64(reflect_size(type_id(fs::XfsGeometryReport)));}return u64(reflect_field_count(type_id(fs::XfsGeometryReport)));}'
 d=a.out/'lifetime';d.mkdir(exist_ok=True);(d/'input.au').write_text(life);(d/'entry.s').write_text(entry(1))
 run([a.compiler,'--module-root',a.root/'library',d/'input.au','-o',d/'program.s']);run(['as','--64',d/'entry.s','-o',d/'entry.o']);run(['as','--64',d/'program.s','-o',d/'program.o']);run(['ld','-o',d/'native',d/'entry.o',d/'program.o']);o=run([d/'native']);(d/'stdout').write_bytes(o.stdout)
 import struct
 require(list(struct.unpack('<44Q',o.stdout))==flattened(inspect(b))+[336,0],'report after local-array lifetime / reflection disagreement')
 types={'XfsBlockFacts':48,'XfsInodeFacts':32,'XfsDataFacts':24,'XfsAgFacts':48,'XfsLogFacts':40,'XfsGeometryFacts':192,'XfsHeaderObservations':24,'XfsFeatureMasks':32,'XfsFeatureDiagnostics':64,'XfsGeometryReport':336}
 sizes=imports+'auto sizes()->i64{'
 for typ,n in types.items():sizes+=f'static_assert(size_of(fs::{typ})=={n});static_assert(field_count(fs::{typ})==0);if(reflect_size(type_id(fs::{typ}))!={n}){{return 1;}}if(reflect_field_count(type_id(fs::{typ}))!=0){{return 2;}}'
 sizes+='return 42;}'
 d=a.out/'metadata';d.mkdir(exist_ok=True);(d/'input.au').write_text(sizes);run([a.compiler,'--module-root',a.root/'library',d/'input.au','-o',d/'program.s'])
 (d/'entry.s').write_text('.text\n.globl _start\n_start:\ncall sizes\npushq %rax\nmovq $1,%rax\nmovq $1,%rdi\nmovq %rsp,%rsi\nmovq $8,%rdx\nsyscall\nmovq $60,%rax\nxorq %rdi,%rdi\nsyscall\n.section .note.GNU-stack,"",@progbits\n')
 run(['as','--64',d/'entry.s','-o',d/'entry.o']);run(['as','--64',d/'program.s','-o',d/'program.o']);run(['ld','-o',d/'native',d/'entry.o',d/'program.o']);o=run([d/'native']);(d/'stdout').write_bytes(o.stdout);require(o.stdout==(42).to_bytes(8,'little'),'runtime group metadata disagreement')
 failures=[];results=[]
 tests={
 'private_builder':imports+'auto test()->i64{'+array+'const fs::XfsGeometryFacts facts=fs::xfs_build_geometry_facts(view);return 42;}',
 'private_validator':imports+'auto test()->i64{'+array+'const fs::XfsProbeResult p=fs::probe_xfs_v5_512(view);const fs::XfsHeaderObservations r=fs::XfsHeaderObservations(0u64,0u64,0u64);const fs::XfsGeometryVerdict v=fs::xfs_check_geometry_fields(view,r,p);return 42;}',
 'private_zero_helper':imports+'auto test()->i64{const fs::XfsGeometryFacts f=fs::xfs_zero_geometry_facts();return 42;}',
 'private_report_field':imports+'auto test()->u64{'+array+'const fs::XfsGeometryReport r=fs::inspect_xfs_v5_512_geometry(view);return r._status;}',
 'private_fact_field':imports+'auto test()->u64{const fs::XfsBlockFacts b=fs::XfsBlockFacts(1u64,2u64,3u64,4u64,5u64,6u64);return b._block_bytes;}',
 'nested_probe_needs_direct_import':'module review_api;import fs.xfs_geometry;auto test()->i64{'+array+'const fs::XfsGeometryReport r=fs::inspect_xfs_v5_512_geometry(view);const fs::XfsProbeResult p=r.probe();return 42;}',
 'span_storage':imports+'class Bad{builtin::span<const u8> value;};auto test()->i64{return 42;}',
 'span_escape':imports+'auto leak()->builtin::span<const u8>{'+array+'return view;}',
 }
 import subprocess
 expected_diagnostics={'private_builder':'private function is not imported','private_validator':'private type is not imported','private_zero_helper':'private function is not imported','private_report_field':'private class field is inaccessible','private_fact_field':'private class field is inaccessible','nested_probe_needs_direct_import':'direct visible import','span_storage':'class fields require scalar','span_escape':'only scalar function results'}
 for name,src in tests.items():
  d=a.out/name;d.mkdir(exist_ok=True);(d/'input.au').write_text(src)
  for existed in [False,True]:
   output=d/'output.s';sentinel=b'preserved reviewer output\n'
   if existed:output.write_bytes(sentinel)
   else:output.unlink(missing_ok=True)
   r=subprocess.run([str(a.compiler),'--module-root',str(a.root/'library'),str(d/'input.au'),'-o',str(output)],capture_output=True,timeout=120)
   (d/f'stderr-{existed}').write_bytes(r.stderr)
   ok=r.returncode==1 and expected_diagnostics[name].encode() in r.stderr and r.stderr.startswith(b'aurorac: ') and (output.read_bytes()==sentinel if existed else not output.exists())
   require((d/'input.au').read_text()==src,'rejection modified input')
   if not ok:failures.append({'name':name,'existed':existed,'returncode':r.returncode,'stderr':r.stderr.decode(errors='replace')})
  results.append(name)
 receipt={'compiler':str(a.compiler),'compiler_sha256':hashlib.sha256(a.compiler.read_bytes()).hexdigest(),'module_sha256':hashlib.sha256((a.root/'library/fs/xfs_geometry.au').read_bytes()).hexdigest(),'lifetime_native_outputs':44,'metadata_static_and_native_types':10,'rejection_fixtures':results,'rejection_artifact_modes':2,'failures':failures}
 (a.out/'result.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt,indent=2));return bool(failures)
if __name__=='__main__':sys.exit(main())
