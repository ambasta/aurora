from pathlib import Path
import importlib.util,sys,shutil,hashlib
root=Path(__file__).resolve().parents[2]
s=importlib.util.spec_from_file_location('offline_review',root/'fixtures/xfs-offline/verify_native.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
compiler=Path(sys.argv[1]);kind=sys.argv[2];out=root/'docs/review-evidence'/('offline-driver-'+kind);out.mkdir(exist_ok=True)
shutil.copyfile(root/'fixtures/xfs-offline/superblock-v5-512.bin',out/'superblock-v5-512.bin')
m.HERE=out;m.ROOT=root;m.COMPILER=compiler
expected={'release':'2d86780c0082d861e7031955737eef81bb36936c7971d5032b6a1abbb4a24bf8','sanitized':'ca87388b07dd39207ab3342bed2b9cd4ad5212362b435289e7f97b93574476fa'}[kind]
if hashlib.sha256(compiler.read_bytes()).hexdigest()!=expected:raise RuntimeError('wrong compiler')
m.COMPILER_SHA256=expected
m.main()
