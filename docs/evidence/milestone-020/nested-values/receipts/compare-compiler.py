#!/usr/bin/env python3
from pathlib import Path
import hashlib,json,os,subprocess,sys,tempfile
ROOT=Path(__file__).resolve().parent.parent
BASELINE=Path('/tmp/aurora-resource-main-compiler-frozen')
CANDIDATE=ROOT/'build/aurorac'
expected='14cbaa33b69b81240b5828b6893f4c150eeaa9a11d95a83726d32e417c1f8980'
if hashlib.sha256(BASELINE.read_bytes()).hexdigest()!=expected:
 print('frozen baseline pin changed',file=sys.stderr);sys.exit(96)
args=sys.argv[1:]
pos=args.index('-o')+1
original=Path(args[pos])
index=0; sources=[]
while index<len(args):
 if args[index] in ('-o','--module-root'): index+=2
 else: sources.append(Path(args[index])); index+=1
if len(sources)!=1: raise RuntimeError('expected one source input')
source=sources[0]
with tempfile.TemporaryDirectory(dir=ROOT/'tmp',prefix='assembly-compare-') as tmp:
 other=Path(tmp)/'baseline.s';old=args[:];old[pos]=str(other)
 base=subprocess.run([str(BASELINE),*old],capture_output=True)
 new=subprocess.run([str(CANDIDATE),*args],capture_output=True)
 same=base.returncode==new.returncode and (base.returncode!=0 or other.read_bytes()==original.read_bytes())
 record={'input_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'baseline_exit':base.returncode,'candidate_exit':new.returncode,'identical':same}
 if base.returncode==0:
  record.update(baseline_assembly_sha256=hashlib.sha256(other.read_bytes()).hexdigest(),candidate_assembly_sha256=hashlib.sha256(original.read_bytes()).hexdigest() if original.exists() else None)
 with (ROOT/'receipts/assembly-comparison.jsonl').open('a') as f: f.write(json.dumps(record)+'\n')
 if not same:
  out=ROOT/'receipts/differential-failures';out.mkdir(exist_ok=True)
  stem=record['input_sha256'];(out/(stem+'.au')).write_bytes(source.read_bytes());(out/(stem+'.json')).write_text(json.dumps(record,indent=2));(out/(stem+'.baseline.stderr')).write_bytes(base.stderr);(out/(stem+'.candidate.stderr')).write_bytes(new.stderr)
  print('baseline status or assembly mismatch: '+stem,file=sys.stderr);sys.exit(95)
 sys.stdout.buffer.write(new.stdout);sys.stderr.buffer.write(new.stderr)
 sys.exit(new.returncode if new.returncode>=0 else 128-new.returncode)
