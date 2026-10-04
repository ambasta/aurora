"""Run the final fixture CLI into separate review receipts; preserve old evidence."""
from pathlib import Path
import hashlib,subprocess,sys
root=Path(__file__).resolve().parents[2]
compiler=Path(sys.argv[1]);kind=sys.argv[2]
expected={'release':'2d86780c0082d861e7031955737eef81bb36936c7971d5032b6a1abbb4a24bf8','sanitized':'ca87388b07dd39207ab3342bed2b9cd4ad5212362b435289e7f97b93574476fa'}[kind]
if hashlib.sha256(compiler.read_bytes()).hexdigest()!=expected:raise RuntimeError('wrong compiler')
out=root/'docs/review-evidence'/('offline-driver-'+kind);out.mkdir(exist_ok=True)
subprocess.run([sys.executable,'-O',root/'fixtures/xfs-offline/verify_native.py','--compiler',compiler,'--compiler-sha256',expected,'--receipt',out/'native-results-final.json'],cwd=root,check=True)
