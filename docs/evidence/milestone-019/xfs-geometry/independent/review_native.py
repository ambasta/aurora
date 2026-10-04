#!/usr/bin/env python3
"""Independent native adapter, consumes every copied report leaf as full u64.
Expected values come only from review_oracle.py. Linux syscall entry assembly is
review-only bootstrap observation, not Aurora library/C ABI implementation.
"""
import argparse, hashlib, json, os, resource, struct, subprocess, sys, time
from pathlib import Path
sys.dont_write_bytecode=True
from review_oracle import *
from review_cases import build

GROUP_TYPES={'blocks':'XfsBlockFacts','inodes':'XfsInodeFacts','data':'XfsDataFacts','ags':'XfsAgFacts','log':'XfsLogFacts'}
def run(cmd,timeout=120):
    x=subprocess.run(list(map(str,cmd)),capture_output=True,timeout=timeout,preexec_fn=lambda:resource.setrlimit(resource.RLIMIT_CORE,(0,0)))
    if x.returncode:raise RuntimeError(f'Command failed: {cmd}; status={x.returncode}; stdout={x.stdout[:1000]!r}; stderr={x.stderr[:8000]!r}')
    return x

def expressions(prefix='r'):
    decl=f'const fs::XfsProbeResult p={prefix}.probe();const fs::XfsHeaderObservations raw={prefix}.raw();const fs::XfsFeatureDiagnostics masks={prefix}.masks();const fs::XfsFeatureMasks unsupported=masks.unsupported();const fs::XfsFeatureMasks unknown=masks.unknown();const fs::XfsGeometryFacts facts={prefix}.facts();'
    for group,typ in GROUP_TYPES.items():decl+=f'const fs::{typ} {group}=facts.{group}();'
    ex=['status_code(r.status())','issue_code(r.issue())','probe_code(p.status())']
    ex +=[f'p.features_{x}()' for x in ['compat','ro_compat','incompat','log_incompat']]
    ex +=[f'raw.{x}()' for x in ['versionnum','features2','bad_features2']]
    for mask in ['unsupported','unknown']:ex +=[f'{mask}.{x}()' for x in ['compat','ro_compat','incompat','log_incompat']]
    for group,fields in FACT_GROUPS.items():ex +=[f'{group}.{x}()' for x in fields]
    require(len(ex)==42,'expected42');return decl,ex

def enum_functions():
    output=''
    for fn,typ,vals in [('status_code','XfsGeometryStatus',STATUS),('issue_code','XfsGeometryIssue',ISSUE),('probe_code','XfsProbeStatus',PROBE)]:
        output+=f'auto {fn}(fs::{typ} x)->u64{{'
        for i,v in enumerate(vals):output+=f'if(x==fs::{typ}::{v}){{return {i}u64;}}'
        output+='return 99u64;}\n'
    return output

def function(i,data):
    vals=','.join(str(x)+'u8' for x in data)
    s=f'auto case_{i}(i64 index)->u64{{const array<u8,{len(data)}> bytes={{{vals}}};const array<u8,{len(data)}> original=bytes;const builtin::span<const u8> view=borrow_bytes(bytes);const fs::XfsGeometryReport inspected=fs::inspect_xfs_v5_512_geometry(view);const fs::XfsGeometryReport r=inspected;'
    decl,ex=expressions();s+=decl
    # Check actual source array bytes after two complete inspector calls.
    s+='const fs::XfsGeometryReport repeated=fs::inspect_xfs_v5_512_geometry(view);'
    s+='i64 j=0;while(j<view.size()){if(bytes[j]!=original[j]){return 18446744073709551615u64;}j=j+1;}'
    for j,e in enumerate(ex):s+=f'if(index=={j}){{return {e};}}'
    s+='if(index==42){if(repeated.status()==r.status()){return 1u64;}return 0u64;}'
    s+='if(index==43){return u64(size_of(fs::XfsGeometryReport));}'
    s+='return 99u64;}\n';return s

def entry(count):
    s='.text\n.globl _start\n_start:\n'
    for i in range(count):
        for field in range(44):
            s+=f'movq ${field},%rdi\ncall case_{i}\npushq %rax\nmovq $1,%rax\nmovq $1,%rdi\nmovq %rsp,%rsi\nmovq $8,%rdx\nsyscall\naddq $8,%rsp\n'
    s+='movq $60,%rax\nxorq %rdi,%rdi\nsyscall\n.section .note.GNU-stack,"",@progbits\n';return s

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);ap.add_argument('--compiler',type=Path,required=True);ap.add_argument('--compiler-sha',required=True);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--limit',type=int);ap.add_argument('--batch',type=int,default=16);ap.add_argument('--seed',type=int,default=193706);args=ap.parse_args()
    args.out.mkdir(parents=True,exist_ok=True)
    actual=hashlib.sha256(args.compiler.read_bytes()).hexdigest();require(actual==args.compiler_sha,'compiler pin differs')
    module=args.root/'library/fs/xfs_geometry.au';module_sha=hashlib.sha256(module.read_bytes()).hexdigest()
    cases=build(fixture(args.root/'fixtures/xfs-offline/superblock-v5-512.hex'),args.seed)
    if args.limit:cases=cases[:args.limit]
    expected={n:inspect(d) for n,d,_ in cases}
    (args.out/'corpus.json').write_text(json.dumps([{'name':n,'hex':d.hex(),'aliases':aliases,'expected':expected[n]} for n,d,aliases in cases],indent=2)+'\n')
    started=time.time();failures=[];passed=0
    for offset in range(0,len(cases),args.batch):
        batch=cases[offset:offset+args.batch];dest=args.out/f'batch-{offset:04d}';dest.mkdir(exist_ok=True)
        source='module reviewer;\nimport fs.xfs_geometry;\nimport fs.xfs_probe;\n'+enum_functions()+''.join(function(i,d) for i,(_,d,_) in enumerate(batch))
        (dest/'input.au').write_text(source);(dest/'entry.s').write_text(entry(len(batch)))
        try:
            c=run([args.compiler,'--module-root',args.root/'library',dest/'input.au','-o',dest/'program.s']);(dest/'compiler.stderr').write_bytes(c.stderr)
            require((dest/'input.au').read_text()==source,'compiler changed input')
            run(['as','--64',dest/'entry.s','-o',dest/'entry.o']);run(['as','--64',dest/'program.s','-o',dest/'program.o']);run(['ld','-o',dest/'native',dest/'entry.o',dest/'program.o'])
            observed=run([dest/'native']);(dest/'native.stdout').write_bytes(observed.stdout);(dest/'native.stderr').write_bytes(observed.stderr)
            require(len(observed.stdout)==len(batch)*44*8,'wrong output length')
            words=struct.unpack('<'+'Q'*(len(observed.stdout)//8),observed.stdout)
            for i,(name,data,_) in enumerate(batch):
                want=flattened(expected[name])+[1,336];got=list(words[i*44:(i+1)*44])
                if got!=want:failures.append({'name':name,'batch':str(dest),'fields':[{'index':j,'expected':a,'actual':b} for j,(a,b) in enumerate(zip(want,got)) if a!=b]})
                else:passed+=1
        except Exception as e:
            failures.append({'batch':str(dest),'error':str(e)});(dest/'FAILURE.txt').write_text(str(e)+'\n');break
        require(hashlib.sha256(module.read_bytes()).hexdigest()==module_sha,'module changed during run')
        if offset%160==0:print(f'checked {offset+len(batch)} / {len(cases)}, mismatches {len(failures)}',flush=True)
    result={'compiler':str(args.compiler),'compiler_sha256':actual,'module_sha256':module_sha,'seed':args.seed,'unique_inputs':len(cases),'passed':passed,'failures':failures,'seconds':time.time()-started,'scope':'44 full-width outputs per unique input:42 report leaves, repeat-status and size; input byte preservation checked after repeated calls. Sanitized compiler does not instrument generated Aurora.'}
    (args.out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2));return bool(failures)
if __name__=='__main__':sys.exit(main())
