#!/usr/bin/env python3
"""Executable mutation controls against private copies only. Never main/candidate.
A killed mutant means this targeted check sees a wrong value or a native fault;
it does not increase the count of original-library accepted/rejected inputs.
"""
import argparse,hashlib,json,shutil,struct,subprocess,sys
from pathlib import Path
sys.dont_write_bytecode=True
from review_oracle import *
from review_native import run,function,entry,enum_functions

def main():
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--compiler',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
 original=(a.root/'library/fs/xfs_geometry.au').read_text();data=fixture(a.root/'fixtures/xfs-offline/superblock-v5-512.hex')
 tests=[
 ('encoded_as_linear','const u64 linear_start = log_ag * ag_blocks + log_ag_block;','const u64 linear_start = encoded_start;',mutate(data,agblocks=30000,dblocks=120000)),
 ('forget_short_tail_fact','ag_blocks * block_bytes, data_blocks - tail_base, tail_base * block_bytes);','ag_blocks * block_bytes, ag_blocks, tail_base * block_bytes);',mutate(data,dblocks=98368)),
 ('ceiling_as_floor','if (remainder != 0u64) { expected_count = expected_count + 1u64; }','if (remainder != 0u64) { expected_count = expected_count; }',mutate(data,dblocks=98368)),
 ('allow_unknown_extended','if ((unsupported.compat() | unsupported.ro_compat() | unsupported.incompat() | unsupported.log_incompat()) != 0u64) {','if (false) {',mutate(data,compat=0x80000000)),
 ('omit_data_product_guard','if (data_blocks > maximum / block_bytes) {','if (false) {',mutate(data,agblocks=268435456,agblklog=28,agcount=16777216,dblocks=1<<52)),
 ('omit_block_shift_bound','if (block_log > 16u64) {','if (false) {',mutate(data,blocklog=64)),
 ('omit_sparse_zero_divisor_guard','if (sparse_alignment != 0u64) {\n                if (sparse_alignment > inode_alignment)','if (true) {\n                if (sparse_alignment > inode_alignment)',mutate(data,spino_align=0)),
 ('omit_legacy_required','if ((raw.versionnum() & 46240u64) != 46240u64) {','if (false) {',mutate(data,versionnum=0xb425)),
 ('forget_ag_header_exclusion','if (log_ag_block <= 1536u64 / block_bytes) {','if (false) {',mutate(data,logstart=65536,logblocks=1)),
 ('forget_same_ag_extent_bound','if (log_blocks > actual_ag_blocks - log_ag_block) {','if (false) {',mutate(data,logstart=2*32768+32767,logblocks=2)),
 ]
 results=[]
 for name,old,new,fixture_bytes in tests:
  require(original.count(old)==1,f'unique mutation site {name}')
  d=a.out/name;d.mkdir(exist_ok=True);shutil.copytree(a.root/'library',d/'library',dirs_exist_ok=True);mutant=original.replace(old,new);(d/'library/fs/xfs_geometry.au').write_text(mutant)
  (d/'input.au').write_text('module mutation;import fs.xfs_geometry;import fs.xfs_probe;'+enum_functions()+function(0,fixture_bytes));(d/'entry.s').write_text(entry(1))
  run([a.compiler,'--module-root',d/'library',d/'input.au','-o',d/'program.s']);run(['as','--64',d/'entry.s','-o',d/'entry.o']);run(['as','--64',d/'program.s','-o',d/'program.o']);run(['ld','-o',d/'native',d/'entry.o',d/'program.o'])
  observed=subprocess.run([str(d/'native')],capture_output=True,timeout=15);(d/'stdout').write_bytes(observed.stdout);(d/'stderr').write_bytes(observed.stderr)
  expected=flattened(inspect(fixture_bytes))+[1,336];got=list(struct.unpack('<44Q',observed.stdout)) if len(observed.stdout)==352 else None
  killed=observed.returncode!=0 or got!=expected
  results.append({'name':name,'mutant_sha256':hashlib.sha256(mutant.encode()).hexdigest(),'status':observed.returncode,'killed':killed,'expected':expected,'observed':got,'fixture_sha256':hashlib.sha256(fixture_bytes).hexdigest()})
  require(killed,f'surviving mutant {name}')
 receipt={'source_sha256':hashlib.sha256(original.encode()).hexdigest(),'compiler_sha256':hashlib.sha256(a.compiler.read_bytes()).hexdigest(),'controls':results,'limits':'Ten semantic/nonredundant controls. No claim to kill mathematically redundant guards; those are source-audited. Mutant faults are intentional negative-control failures, not original-library acceptable responses.'}
 (a.out/'result.json').write_text(json.dumps(receipt,indent=2)+'\n');print('PASS',len(results),'independent executable mutation controls')
if __name__=='__main__':main()
