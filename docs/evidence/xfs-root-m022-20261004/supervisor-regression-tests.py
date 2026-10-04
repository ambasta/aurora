import ast,pathlib,os,stat,tempfile,json,subprocess,signal,time
w=pathlib.Path(__file__).resolve().parent;tree=ast.parse((w/'run_parent_gate.py').read_text());node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='alloc');scope={'pathlib':pathlib,'os':os,'stat':stat};exec(compile(ast.Module(body=[node],type_ignores=[]),'<alloc>','exec'),scope);alloc=scope['alloc'];controls=[]
with tempfile.TemporaryDirectory(dir=w,prefix='supervisor-controls-') as t:
 root=pathlib.Path(t);victim=root/'vanish';victim.write_bytes(b'x'*10000);original=pathlib.Path.lstat
 def raced(self,*a,**kw):
  if self==victim and self.exists():self.unlink()
  return original(self,*a,**kw)
 pathlib.Path.lstat=raced
 try:result=alloc(root)
 finally:pathlib.Path.lstat=original
 if result!=root.stat().st_blocks*512:raise RuntimeError('vanished file accounting')
 controls.append('file disappears between scan and lstat -> ignored')
 d=root/'vanishing-directory';d.mkdir();scan=os.scandir
 def raced_scan(path):
  if path==d:d.rmdir()
  return scan(path)
 os.scandir=raced_scan
 try:alloc(root)
 finally:os.scandir=scan
 controls.append('directory disappears between lstat and scandir -> ignored')
 def denied(self,*a,**kw):raise PermissionError('synthetic denied accounting')
 pathlib.Path.lstat=denied
 try:
  try:alloc(root)
  except PermissionError:controls.append('permission error remains a failure')
  else:raise RuntimeError('permission suppressed')
 finally:pathlib.Path.lstat=original
# Exercise exact fixed exception handler with a live owned harmless child.
tr=next(n for n in tree.body if isinstance(n,ast.Try));handler=tr.handlers[0];body=ast.Try(body=[ast.Raise(exc=ast.Call(func=ast.Name(id='RuntimeError',ctx=ast.Load()),args=[ast.Constant('synthetic supervisor error')],keywords=[]))],handlers=[handler],orelse=[],finalbody=[]);mod=ast.fix_missing_locations(ast.Module(body=[body],type_ignores=[]));proc=subprocess.Popen(['sleep','30'],start_new_session=True);r={}
try:
 try:exec(compile(mod,'<handler>','exec'),{'r':r,'proc':proc,'os':os,'signal':signal,'subprocess':subprocess})
 except RuntimeError:pass
 if proc.poll() is None or r.get('status')!='failed' or 'terminated_child_returncode' not in r:raise RuntimeError('cleanup handler failed')
 controls.append('supervisor failure terminates and waits owned process group')
finally:
 if proc.poll() is None:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
(w/'SUPERVISOR-CONTROLS.json').write_text(json.dumps({'status':'passed','controls':controls},indent=2)+'\n');print('PASS4 supervisor regression controls')
