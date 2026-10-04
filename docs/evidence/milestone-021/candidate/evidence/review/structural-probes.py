from pathlib import Path
import subprocess, json, hashlib, resource
ROOT=Path(__file__).resolve().parents[2]
D=ROOT/'evidence/review/structural';D.mkdir(exist_ok=True)
base='module probe;template<Value U>class Box{public:Box(){} };'
probes={
'qualified-local':'template<Value T>auto never()->i64{const Box<T::Hidden> x=Box<T::Hidden>();return 42;}',
'qualified-local-deep':'template<Value T>auto never()->i64{const Box<Box<T::Hidden>> x=Box<Box<T::Hidden>>();return 42;}',
'qualified-constructor':'template<Value T>auto never()->i64{const Box<i64> x=Box<T::Hidden>();return 42;}',
'qualified-reflection':'template<Value T>auto never()->i64{return size_of(Box<T::Hidden>);}',
'qualified-signature':'template<Value T>auto never(Box<T::Hidden> x)->i64{return 42;}',
'unknown-local':'template<Value T>auto never()->i64{const Box<Missing> x=Box<Missing>();return 42;}',
'wrong-kind-nested':'template<Value T>auto never()->i64{const Box<never<i64>> x=Box<never<i64>>();return 42;}',
'wrong-arity-fixed-signature':'template<Value T>auto never(Box<i64,u8> x)->i64{return 42;}',
'wrong-arity-fixed-local':'template<Value T>auto never()->i64{const Box<i64,u8> x=Box<i64,u8>();return 42;}',
'function-tree-nested':'template<Value T>auto never()->i64{const Box<helper<i64>> x=Box<helper<i64>>();return 42;}',
'qualified-bare-local':'template<Value T>auto never()->i64{const T::Hidden x=42;return 42;}',
}
r=[]
for name,body in probes.items():
 p=D/(name+'.au');p.write_text(base+'template<Value V>auto helper()->i64{return 42;}'+body+'auto test()->i64{return 42;}')
 output=D/(name+'.s');output.write_text('sentinel')
 cmd=[str(ROOT/'build/aurorac'),str(p),'-o',str(output)]
 c=subprocess.run(cmd,capture_output=True,timeout=10,preexec_fn=lambda:resource.setrlimit(resource.RLIMIT_CORE,(0,0)))
 entry={'probe':name,'command':cmd,'returncode':c.returncode,'diagnostic':c.stderr.decode(),'output_changed':output.read_text()!='sentinel'}
 r.append(entry);print(json.dumps(entry))
(D/'results.json').write_text(json.dumps(r,indent=2)+'\n')
