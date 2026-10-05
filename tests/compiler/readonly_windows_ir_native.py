#!/usr/bin/env python3
"""Direct-IR native bounded-window oracle, with exact trap PC validation."""
from pathlib import Path
import argparse
from readonly_spans import Trap,MIN_I64,MAX_I64,require
from unsigned_oracle import NativeRunner,Case,command,validate_trap,validate_values
p=argparse.ArgumentParser(description=__doc__);p.add_argument('ir_tests',type=Path);p.add_argument('--artifacts',type=Path,required=True);a=p.parse_args()
a.artifacts.mkdir(parents=True,exist_ok=False)
assembly=command([a.ir_tests.resolve(),'--emit-native']).stdout.decode();(a.artifacts/'direct-ir.s').write_text(assembly)
runner=NativeRunner(a.artifacts,None,10);cases=traps=0
values=[11,128,255]
for offset in (MIN_I64,-1,0,1,2,3,4,MAX_I64):
 for count in (MIN_I64,-1,0,1,2,3,4,MAX_I64):
  valid=0<=offset<=3 and 0<=count<=3-offset
  for target,index in [('window_size',0),('window_dynamic',-1),('window_dynamic',0),('window_dynamic',count-1),('window_dynamic',count)]:
   if not MIN_I64<=index<=MAX_I64:continue
   name=f'{target}({offset},{count},{index})'
   wrapper='\n.text\n.globl test\ntest:\n'+f'movabsq ${offset}, %rdi\nmovabsq ${count}, %rsi\nmovabsq ${index}, %rdx\njmp {target}\n'
   observed,symbols=runner.assemble(assembly+wrapper,['test'])
   if valid and (target=='window_size' or 0<=index<count):
    result=count if target=='window_size' else values[offset+index]
    validate_values(observed,[Case(name,'',result,'i64')])
   else:validate_trap(observed,Trap.BOUNDS,symbols,name);traps+=1
   cases+=1
summary=f'PASS readonly window direct IR native: {cases} cases, {traps} exact bounds traps'
(a.artifacts/'summary.txt').write_text(summary+'\n');print(summary)
