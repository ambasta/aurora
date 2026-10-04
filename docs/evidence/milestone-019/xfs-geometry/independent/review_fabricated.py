#!/usr/bin/env python3
import argparse,hashlib,json,struct,sys
from pathlib import Path
sys.dont_write_bytecode=True
from review_oracle import *
from review_native import run,enum_functions,expressions,entry,GROUP_TYPES
p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--compiler',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
source='module fabricate;import fs.xfs_geometry;import fs.xfs_probe;'+enum_functions();expect=[]
for case,status in enumerate(['header_geometry_consistent','inconsistent_header']):
 source+=f'auto case_{case}(i64 index)->u64{{';values=list(range(2**63,2**63+24));at=0
 for group,fields in FACT_GROUPS.items():
  n=len(fields);source+=f'const fs::{GROUP_TYPES[group]} seed_{group}=fs::{GROUP_TYPES[group]}('+','.join(f'{x}u64' for x in values[at:at+n])+');';at+=n
 source+='const fs::XfsGeometryFacts seed_facts=fs::XfsGeometryFacts(seed_blocks,seed_inodes,seed_data,seed_ags,seed_log);'
 source+='const fs::XfsProbeResult seed_probe=fs::XfsProbeResult(fs::XfsProbeStatus::checksum_mismatch,1u64,2u64,3u64,4u64);const fs::XfsHeaderObservations seed_raw=fs::XfsHeaderObservations(5u64,6u64,7u64);const fs::XfsFeatureMasks seed_mask=fs::XfsFeatureMasks(8u64,9u64,10u64,11u64);const fs::XfsFeatureDiagnostics seed_masks=fs::XfsFeatureDiagnostics(seed_mask,seed_mask);'
 source+=f'const fs::XfsGeometryReport parent=fs::XfsGeometryReport(fs::XfsGeometryStatus::{status},fs::XfsGeometryIssue::none,seed_probe,seed_raw,seed_masks,seed_facts);const fs::XfsGeometryReport r=parent;'
 decl,expr=expressions();source+=decl
 for i,e in enumerate(expr):source+=f'if(index=={i}){{return {e};}}'
 source+='if(index==42){return 1u64;}return 336u64;}'
 expect +=[STATUS.index(status),0,3,1,2,3,4,5,6,7,8,9,10,11,8,9,10,11]+(values if case==0 else [0]*24)+[1,336]
(a.out/'input.au').write_text(source);(a.out/'entry.s').write_text(entry(2));run([a.compiler,'--module-root',a.root/'library',a.out/'input.au','-o',a.out/'program.s']);run(['as','--64',a.out/'entry.s','-o',a.out/'entry.o']);run(['as','--64',a.out/'program.s','-o',a.out/'program.o']);run(['ld','-o',a.out/'native',a.out/'entry.o',a.out/'program.o']);o=run([a.out/'native']);(a.out/'stdout').write_bytes(o.stdout);require(list(struct.unpack('<88Q',o.stdout))==expect,'fabricated report copy disagreement')
(a.out/'result.json').write_text(json.dumps({'compiler_sha256':hashlib.sha256(a.compiler.read_bytes()).hexdigest(),'module_sha256':hashlib.sha256((a.root/'library/fs/xfs_geometry.au').read_bytes()).hexdigest(),'fabricated_reports':2,'outputs':88,'result':'pass','meaning':'Success can be fabricated with invalid nested probe and arbitrary high-bit data; it is not authority. Failed status masks every fact to zero. Copied constructor/groups preserve full-width values.'},indent=2)+'\n');print('PASS fabricated success/failure report semantics and copied full-width groups')
