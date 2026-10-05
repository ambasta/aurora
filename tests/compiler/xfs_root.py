#!/usr/bin/env python3
"""Fresh reconstruction: portable bounded native XFS lookup gate; no old receipts."""
from __future__ import annotations
import argparse, hashlib, importlib, json, pathlib, random, resource, shutil, subprocess, sys
from dataclasses import dataclass
sys.dont_write_bytecode = True
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / 'scripts'))
from compiler_contract import add_identity_arguments, resolve_identity, validate_identity_selection
ROOT = FIXTURES = ARTIFACTS = CANDIDATE = None
geometry = None
MODULE_PATHS = {}
CAP = 128 << 20
FLOOR = 1 << 30
MODULE_SHA = '8f669775ea7a5e850a314e50c37d90a5ba1ef30b1d60f6c8a54be5a6faef9e4f'
FIXTURE_SHA = {
 'empty-superblock.hex':'55ad821909c312048d9936a74c8904cd25f97aa190b48ae0004b03eaffdc6586',
 'empty-root.hex':'963d4d1ae9f5821528cdeaac5dbc65abc0a4146a737dab84ade621a12d2c326e',
 'named-superblock.hex':'9fd8b9f7bfa7d12c99ae6e7b3a7633cc3ab48c45ff5facde79c36ad69503edb7',
 'named-root.hex':'283d31448057d3a9b1406cf655274b799e0636abb32e466b40c15bf3df9d265b'}
DEPS = ['xfs_geometry','storage_binary','readonly_spans','utf8','unsigned_oracle']
def require(c,m):
 if not c: raise AssertionError(m)
def sha(p): return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def allocated():
 if ARTIFACTS is None or not ARTIFACTS.exists(): return 0
 return ARTIFACTS.lstat().st_blocks*512 + sum(p.lstat().st_blocks*512 for p in ARTIFACTS.rglob('*'))
def budget(reserve=0):
 require(ARTIFACTS is not None,'explicit artifact root required')
 require(allocated()+reserve<=CAP,'owned output budget including reserve')
 require(shutil.disk_usage(ARTIFACTS if ARTIFACTS.exists() else ARTIFACTS.parent).free-reserve>FLOOR,'global free floor including reserve')
def configure(args):
 global ROOT,FIXTURES,ARTIFACTS,CANDIDATE,geometry,MODULE_PATHS
 validate_identity_selection(args)
 identity=resolve_identity(args,args.compiler,args.repo_root)
 for supplied in [args.repo_root,args.fixture_root,args.artifact_root,args.candidate_library or args.repo_root/'library']:
  p=pathlib.Path(supplied).absolute();require(not any(x.is_symlink() for x in [p,*p.parents]),'symlink root rejected')
 ROOT=args.repo_root.resolve(strict=True);FIXTURES=args.fixture_root.resolve(strict=True)
 CANDIDATE=(args.candidate_library or ROOT/'library').resolve(strict=True);ARTIFACTS=args.artifact_root.absolute()
 require(ROOT.is_dir() and FIXTURES.is_dir() and CANDIDATE.is_dir(),'input roots must be directories')
 require(ARTIFACTS.parent.is_dir() and not ARTIFACTS.exists() and not ARTIFACTS.is_symlink(),'artifact root must be fresh with existing parent')
 MODULE_PATHS={}
 for name in ['fs/xfs_root.au','fs/xfs_geometry.au','fs/xfs_probe.au','std/binary.au','std/checksum.au','std/bit.au']:
  found=[root/name for root in dict.fromkeys([CANDIDATE,ROOT/'library']) if (root/name).is_file()]
  require(len(found)==1,'module must resolve uniquely across explicit roots: '+name)
  require(not any(x.is_symlink() for x in [found[0],*found[0].parents]),'symlink module path rejected')
  MODULE_PATHS[name]=found[0]
 require(sha(MODULE_PATHS['fs/xfs_root.au'])==MODULE_SHA,'recovered module byte identity')
 dep=ROOT/'tests/compiler'
 for name in DEPS:
  require((dep/(name+'.py')).is_file(),'missing explicit oracle dependency '+name)
  if name in sys.modules:require(pathlib.Path(sys.modules[name].__file__).resolve()==dep/(name+'.py'),'stale oracle import '+name)
 sys.path.insert(0,str(dep));geometry=importlib.import_module('xfs_geometry')
 for name in DEPS:require(pathlib.Path(sys.modules[name].__file__).resolve()==dep/(name+'.py'),'oracle root mismatch '+name)
 budget(65536);ARTIFACTS.mkdir()
 return identity
def input_paths(extra=None):
 p=[*MODULE_PATHS.values(),pathlib.Path(__file__).resolve()]
 p += [ROOT/'tests/compiler'/(x+'.py') for x in DEPS]
 p += [FIXTURES/x for x in FIXTURE_SHA]
 if extra is not None:p.append(pathlib.Path(extra).resolve())
 return p
def crc32c_gf2(data):
 rev=bytes(int(f'{x:08b}'[::-1],2) for x in data)
 poly=(0xffffffff<<(8*len(data)))^(int.from_bytes(rev,'big')<<32)
 while poly.bit_length()>32:poly ^= 0x11edc6f41 << (poly.bit_length()-33)
 return int(f'{poly:032b}'[::-1],2)^0xffffffff
def be(b,p,n):return int.from_bytes(b[p:p+n],'big')
def fix(b,p=100):
 b=bytearray(b);b[p:p+4]=bytes(4);b[p:p+4]=crc32c_gf2(b).to_bytes(4,'little');return bytes(b)
def setv(b,p,n,v,crc=100):
 b=bytearray(b);b[p:p+n]=v.to_bytes(n,'big');return fix(b,crc)
def name_ok(n):return 1<=len(n)<=255 and not any(c in (0,47) for c in n) and n not in (b'.',b'..')
def address(sb,n):
 if not 1<=n<=0xffffffff:return 0
 B,A,N,D=be(sb,4,4),be(sb,84,4),be(sb,88,4),be(sb,8,8)
 slots=2**sb[123];width=2**sb[124];ag,local=divmod(n,slots*width);block,slot=divmod(local,slots)
 if not (ag<N and 4*512<=block*B and block<min(A,D-ag*A)):return 0
 linear=ag*A+block;logag,logblock=divmod(be(sb,48,8),width);log=logag*A+logblock
 if log<=linear<log+be(sb,96,4):return 0
 result=linear*B+slot*512;require(result+512<=D*B,'oracle address bounds');return result
@dataclass(frozen=True)
class Expected:
 status:str
 issue:str
 values:tuple=(0,)*7
 def scalars(self):return (1,1,int(self.status=='found'),*self.values,1)
def oracle(sb,ino,q):
 def err(s,i):return Expected(s,i)
 if geometry.oracle(sb).status!='header_geometry_consistent':return err('geometry_rejected','geometry')
 if be(sb,104,2)!=512:return err('unsupported_profile','inode_size')
 if sb[192]:return err('unsupported_profile','directory_block')
 root=be(sb,56,8);off=address(sb,root)
 if not off:return err('invalid_inode','root_address')
 if len(ino)!=512:return err('invalid_inode','inode_length')
 if not name_ok(q):return err('invalid_query','query_name')
 if be(ino,0,2)!=0x494e:return err('invalid_inode','magic')
 if ino[4]!=3:return err('unsupported_profile','version')
 if fix(ino)!=ino:return err('invalid_inode','checksum')
 if be(ino,152,8)!=root or ino[160:176]!=sb[32:48]:return err('invalid_inode','identity')
 f=be(ino,120,8);s=be(sb,216,4)
 if f&~24 or (f&8 and not s&8) or (f&16 and not s&32):return err('unsupported_profile','flags2')
 zeros=[(6,2),(24,8),(64,8),(72,10),(82,1),(84,8),(128,16)]
 if (be(ino,2,2)&0xf000)!=0x4000 or ino[5]!=1 or not 1<=be(ino,16,4)<=0x7fffffff or ino[83]!=2 or be(ino,96,4)!=0xffffffff or any(be(ino,p,n) for p,n in zeros):return err('invalid_inode','core')
 size=be(ino,56,8)
 if not 6<=size<=336:return err('invalid_directory','payload_size')
 payload=ino[176:176+size];count=payload[0]
 if payload[1]:return err('unsupported_profile','inode_width')
 if count>16:return err('unsupported_profile','entry_count')
 if be(payload,2,4)!=root:return err('invalid_directory','parent')
 cursor=6;end_offset=96;seen=set();entries=[]
 for _ in range(count):
  if len(payload)-cursor<3:return err('invalid_directory','entry_bounds')
  n=payload[cursor];record=payload[cursor:cursor+n+8]
  if len(record)!=n+8:return err('invalid_directory','entry_bounds')
  name=record[3:3+n];ft=record[3+n];number=be(record,4+n,4)
  if not name_ok(name):return err('invalid_directory','entry_name')
  if ft>8:return err('invalid_directory','file_type')
  if not address(sb,number):return err('invalid_directory','entry_inode')
  offset=be(record,1,2)
  if offset%8 or offset<end_offset:return err('invalid_directory','saved_offset')
  end_offset=offset+8*((n+12+7)//8)
  if name in seen:return err('invalid_directory','duplicate_name')
  seen.add(name);entries.append((name,number,ft));cursor+=n+8
 if cursor!=len(payload):return err('invalid_directory','trailing_bytes')
 if end_offset+8*(count+2)+8>be(sb,4,4):return err('invalid_directory','block_footprint')
 match=[(number,ft) for n,number,ft in entries if n==q]
 return Expected('found' if match else 'not_found','none',(root,off,root,count,size,*(match[0] if match else (0,0))))
@dataclass(frozen=True)
class Input:
 label:str
 sb:bytes
 inode:bytes
 query:bytes
 def expected(self):return oracle(self.sb,self.inode,self.query)
def fixture(p):
 t=(FIXTURES/p).read_text();require(len(t)==1025 and t.endswith('\n') and all(c in '0123456789abcdef' for c in t[:-1]),'canonical hex512')
 b=bytes.fromhex(t);require(hashlib.sha256(b).hexdigest()==FIXTURE_SHA[p],'recovered fixture identity');return b
def sf(base,entries,parent=128):
 payload=bytes([len(entries),0])+parent.to_bytes(4,'big')
 for name,number,ft,offset in entries:payload+=bytes([len(name)])+offset.to_bytes(2,'big')+name+bytes([ft])+number.to_bytes(4,'big')
 require(len(payload)<=336,'synthetic payload bound')
 b=bytearray(base);b[176:]=bytes(336);b[176:176+len(payload)]=payload;b[56:64]=len(payload).to_bytes(8,'big');return fix(b)
def cases():
 sb,ino=fixture('named-superblock.hex'),fixture('named-root.hex')
 empty_sb,empty=fixture('empty-superblock.hex'),fixture('empty-root.hex');out=[]
 def add(label,b=ino,s=sb,q=b'alpha'):out.append(Input(label,s,b,q))
 add('real alpha');add('real docs',q=b'docs');add('real absent',q=b'none');add('real case sensitive',q=b'Alpha');add('real empty',empty,empty_sb)
 for n in [1,511,513]:add(f'inode length{n}',(ino+b'X')[:n])
 for n in [1,511,513]:add(f'sb length{n}',s=(sb+b'X')[:n])
 for q in [b'.',b'..',b'a/b',b'\0',b'X'*256]:add('bad query'+q[:8].hex(),q=q)
 for p in [0,5,100,103,104,175,176,511]:
  x=bytearray(ino);x[p]^=1;add(f'unrepaired byte{p}',bytes(x))
 for p,n,vals in [(0,2,[0,0x494f]),(4,1,[0,2,4]),(152,8,[0,129,2**63]),(160,1,[255]),(120,8,[0,8,16,1,2,4,32,2**63]),(2,2,[0,0x81ed,0x4fff]),(5,1,[0,2,3]),(6,2,[1]),(16,4,[0,1,0x7fffffff,0x80000000]),(24,8,[1]),(64,8,[1]),(72,4,[1]),(76,4,[1]),(80,2,[1]),(82,1,[1]),(83,1,[0,1]),(84,4,[1]),(88,2,[1]),(90,2,[1]),(96,4,[0]),(128,4,[1]),(132,1,[1]),(143,1,[1]),(56,8,[0,5,6,30,32,336,337,2**63]),(177,1,[1,255]),(176,1,[0,1,3,16,17,255]),(178,4,[0,129]),(182,1,[0,1,255]),(183,2,[0,95,97,104,120,65528]),(190,1,[0,8,9,255]),(191,4,[0,1,128,131,0xffffffff]),(195,1,[0,255])]:
  for v in vals:add(f'field {p}:{n}={v}',setv(ino,p,n,v))
 for q in [b'\xff',b'\xc0\x80',b'a'*255]:add('raw name '+q[:5].hex(),sf(ino,[(q,131,1,96)]),q=q)
 for q in [b'.',b'..',b'/',b'\0']:add('invalid entry '+q.hex(),sf(ino,[(q,131,1,96)]))
 for ft in range(9):add(f'raw type{ft}',sf(ino,[(b'alpha',131,ft,96)]))
 add('permitted first gap',sf(ino,[(b'alpha',131,1,104),(b'docs',132,2,144)]))
 add('overlap later',sf(ino,[(b'alpha',131,1,96),(b'docs',132,2,112)]))
 add('duplicate',sf(ino,[(b'alpha',131,1,96),(b'alpha',132,2,120)]))
 add('later bad name rejects early match',sf(ino,[(b'alpha',131,1,96),(b'a/b',132,2,120)]))
 add('last footprint exact',sf(ino,[(b'alpha',131,1,4040)]))
 add('last footprint exceeds',sf(ino,[(b'alpha',131,1,4048)]))
 entries=[(bytes([65+i]),131+i,1,96+i*16) for i in range(16)];add('sixteen entries',sf(ino,entries),q=b'P')
 for flags in [0,8,16,24]:
  for features in [3,11,35,43]:add(f'flags{flags}/features{features}',setv(ino,120,8,flags),setv(sb,216,4,features,224))
 add('single-dirblock profile',s=setv(sb,192,1,1,224))
 large=geometry.change(sb,inodesize=1024,inodelog=10,inopblock=4,inopblog=2,inoalignmt=16);add('1024 inode profile',s=large)
 for root in [0,1,7,8,127,128,129,(1<<18)+128,(4<<18),0xffffffff,1<<32,2**64-1]:
  s=setv(sb,56,8,root,224);b=setv(ino,152,8,root)
  if root<=0xffffffff:b=setv(b,178,4,root)
  add(f'root address{root}',b,s)
 s=geometry.change(sb,agblocks=32767,agblklog=15,dblocks=4*32767,logstart=65543)
 for root in [(2<<18)+128,(2<<18)+(32767<<3),(3<<18)+128]:
  b=setv(setv(ino,152,8,root),178,4,root);add(f'nonpower AG root{root}',b,setv(s,56,8,root,224))
 s=geometry.change(sb,dblocks=3*32768+64,logstart=65543)
 for root in [(3<<18)+(63<<3)+7,(3<<18)+(64<<3)]:
  b=setv(setv(ino,152,8,root),178,4,root);add(f'partial final AG root{root}',b,setv(s,56,8,root,224))
 rng=random.Random(23004)
 for i in range(40):
  b=bytearray(ino);p=rng.randrange(512);b[p]=rng.randrange(256);add(f'seed23004 mutation{i}@{p}',fix(b))
 return out

PREFIX='module root_lookup_test;import fs.xfs_root;\n'
LEAVES=['root_inode','inode_offset_bytes','parent_inode','entry_count','payload_bytes']
def array(n,b):return f'array<u8,{len(b)}> {n}={{'+','.join(f'{x}u8' for x in b)+'};'
def shared():
    t='auto scalar(fs::XfsRootReport r,i64 slot)->u64{const fs::XfsRootFacts f=r.facts();const fs::XfsRootMatch m=r.match();'
    for i,n in enumerate(LEAVES,3):t+=f'if(slot=={i}){{return f.{n}();}}'
    return t+'if(slot==8){return m.inode_number();}if(slot==9){return m.file_type();}return 999u64;}\n'
def render(c,n):
    e=c.expected();t=f'auto {n}(i64 slot)->u64{{'+array('sb',c.sb)+array('inode',c.inode)+array('query',c.query)
    for k,b in [('sb',c.sb),('inode',c.inode),('query',c.query)]:t+=f'const array<u8,{len(b)}> {k}_copy={k};'
    call='fs::lookup_xfs_v5_512_root(borrow_bytes(sb),borrow_bytes(inode),borrow_bytes(query))'
    t+='const fs::XfsRootReport r='+call+';'
    for k,b in [('sb',c.sb),('inode',c.inode),('query',c.query)]:t+=f'i64 {k}_i=0;while({k}_i<{len(b)}){{if({k}[{k}_i]!={k}_copy[{k}_i]){{return 998u64;}}{k}_i={k}_i+1;}}'
    t+=f'if(slot==0){{if(r.status()==fs::XfsRootStatus::{e.status}){{return 1u64;}}return 0u64;}}'
    t+=f'if(slot==1){{if(r.issue()==fs::XfsRootIssue::{e.issue}){{return 1u64;}}return 0u64;}}'
    t+='if(slot==2){if(r.found()){return 1u64;}return 0u64;}'
    t+='if(slot==10){const fs::XfsRootReport copy=r;const fs::XfsRootReport again='+call+';if(copy.status()!=again.status()){return 997u64;}if(copy.issue()!=again.issue()){return 996u64;}i64 j=3;while(j<10){if(scalar(copy,j)!=scalar(again,j)){return 995u64;}j=j+1;}sb[0]=0u8;inode[0]=0u8;query[0]=0u8;i64 k=3;while(k<10){if(scalar(r,k)!=scalar(copy,k)){return 994u64;}k=k+1;}return 1u64;}return scalar(r,slot);}\n'
    return t
@dataclass(frozen=True)
class Case:
 name:str
 body:str
 expected:int
@dataclass(frozen=True)
class Observation:
 output:bytes
 exit_code:int
def validate_values(o,cases):
 require(o.exit_code==0,'native exit0 required');require(len(o.output)==len(cases)*8,'exact native output length')
 for i,c in enumerate(cases):
  value=int.from_bytes(o.output[8*i:8*i+8],'little');require(value==c.expected,f'{c.name}: wanted {c.expected}, got {value}')
def module_options():
 roots=list(dict.fromkeys([CANDIDATE,ROOT/'library']));return [part for p in roots for part in ['--module-root',str(p)]]
class Suite:
 def __init__(self,compiler,directory,timeout=15,sanitized=False):
  self.compiler=pathlib.Path(compiler).resolve(strict=True);self.directory=directory;self.timeout=timeout;self.sanitized=sanitized
 def command(self,args,directory,name,compiler=False,native=False):
  budget(24<<20)
  address=None if compiler and self.sanitized else (512 if compiler else 128)<<20
  def limits():
   resource.setrlimit(resource.RLIMIT_CORE,(0,0));resource.setrlimit(resource.RLIMIT_CPU,(10,11));resource.setrlimit(resource.RLIMIT_FSIZE,(8<<20,8<<20))
   if address is not None:resource.setrlimit(resource.RLIMIT_AS,(address,address))
  record={'command':list(map(str,args)),'address_space_bytes':address,'cpu_soft_hard_seconds':[10,11],'regular_file_cap':8<<20,'output_growth_reserve':24<<20,'wall_seconds':self.timeout if native else 30}
  try:
   with (directory/(name+'.stdout')).open('wb') as out,(directory/(name+'.stderr')).open('wb') as err:
    p=subprocess.run(list(map(str,args)),stdout=out,stderr=err,timeout=record['wall_seconds'],preexec_fn=limits)
   record['returncode']=p.returncode
   require(p.returncode==0,f'{name}: expected exit0 got {p.returncode}: '+(directory/(name+'.stderr')).read_bytes()[:4096].decode(errors='replace'))
   require((directory/(name+'.stderr')).stat().st_size==0,name+' unexpected stderr');budget()
   return (directory/(name+'.stdout')).read_bytes()
  except subprocess.TimeoutExpired:record['timeout']=True;raise AssertionError('tool timeout is failure')
  finally:(directory/(name+'.command.json')).write_text(json.dumps(record,indent=2)+'\n')
 def run(self,source,functions,expected,directory):
  require(len(source.encode())<=65536,'source64KiB bound');budget(len(source.encode())+65536);directory.mkdir();(directory/'input.au').write_text(source)
  record={'status':'running','source_sha256':sha(directory/'input.au'),'source_bytes':len(source.encode())}
  try:
   self.command([self.compiler,*module_options(),directory/'input.au','-o',directory/'compiled.s'],directory,'compiler',compiler=True)
   asm=['.text','.globl _start','_start:']
   for f in functions:
    for slot in range(11):asm += [f'movq ${slot},%rdi',f'call {f}','pushq %rax','movq $1,%rax','movq $1,%rdi','movq %rsp,%rsi','movq $8,%rdx','syscall','addq $8,%rsp']
   asm+=['movq $60,%rax','xorq %rdi,%rdi','syscall','.section .note.GNU-stack,"",@progbits']
   (directory/'entry.s').write_text('\n'.join(asm)+'\n')
   self.command(['as','--64',directory/'compiled.s','-o',directory/'program.o'],directory,'assemble')
   self.command(['as','--64',directory/'entry.s','-o',directory/'entry.o'],directory,'entry')
   self.command(['ld','-o',directory/'program',directory/'entry.o',directory/'program.o'],directory,'link')
   output=self.command([directory/'program'],directory,'native',native=True);validate_values(Observation(output,0),expected)
   require((directory/'input.au').read_text()==source,'source modified by tools')
   record['observations']=[{'label':c.name,'expected':c.expected,'observed':int.from_bytes(output[8*i:8*i+8],'little')} for i,c in enumerate(expected)]
   record['status']='passed'
  except Exception as e:record['status']='failed';record['error']=str(e);raise
  finally:(directory/'receipt.json').write_text(json.dumps(record,indent=2)+'\n')
def parser(api=False):
 p=argparse.ArgumentParser(description=__doc__)
 for x in ['repo-root','fixture-root','artifact-root','compiler']:p.add_argument('--'+x,type=pathlib.Path,required=True)
 p.add_argument('--candidate-library',type=pathlib.Path);add_identity_arguments(p);p.add_argument('--sanitized-compiler',action='store_true')
 if not api:
  group=p.add_mutually_exclusive_group();group.add_argument('--compatibility',action='store_true');group.add_argument('--representative',action='store_true');p.add_argument('--limit',type=int)
 return p
def main():
 args=parser().parse_args();identity=configure(args);inputs=[args.compiler,*input_paths()];pins={str(p):sha(p) for p in inputs};corpus=cases();require(len(corpus)==203,'reconstructed corpus count')
 if args.compatibility:
  labels={'real alpha','real docs','real absent','unrepaired byte100','duplicate','nonpower AG root524416'};corpus=[c for c in corpus if c.label in labels];require(len(corpus)==6,'compatibility set')
 if args.representative:
  unique={};extra=[]
  for c in corpus:
   e=c.expected();unique.setdefault((e.status,e.issue),c)
   if c.label.startswith(('real ','raw name','flags','nonpower','partial','sixteen','last footprint','permitted first')):extra.append(c)
  corpus=list({c.label:c for c in [*unique.values(),*extra]}.values())
 if args.limit is not None:require(1<=args.limit<=203,'positive bounded limit');corpus=corpus[:args.limit]
 report={'status':'running','revision':'post-reset reconstruction; fresh evidence','requested_compiler_sha256':args.compiler_sha256,'compiler_identity':identity.record(),'repo_root':str(ROOT),'candidate_library':str(CANDIDATE),'fixture_root':str(FIXTURES),'artifact_root':str(ARTIFACTS),'pins':pins,'cases':len(corpus),'complete_u64_observations':11*len(corpus),'compatibility_only':args.compatibility,'representative_only':args.representative,'case_limit':args.limit,'budget_bytes':CAP,'floor_bytes':FLOOR}
 suite=Suite(args.compiler,ARTIFACTS,sanitized=args.sanitized_compiler)
 try:
  for start in range(0,len(corpus),6):
   batch=corpus[start:start+6];names=[f'root_case_{i}' for i in range(len(batch))];source=PREFIX+shared()+''.join(render(c,n) for c,n in zip(batch,names))
   expected=[Case(c.label+f'/slot{i}','',v) for c in batch for i,v in enumerate(c.expected().scalars())]
   suite.run(source,names,expected,ARTIFACTS/f'batch-{start//6:03}');print('PASS',start+len(batch),'/',len(corpus),flush=True)
  require(pins=={str(p):sha(p) for p in inputs},'run-stable all input pins');identity.verify();report['status']='passed'
 except Exception as e:report['status']='failed';report['error']=str(e);raise
 finally:report['allocated_bytes']=allocated();report['global_free_bytes']=shutil.disk_usage(ARTIFACTS).free;(ARTIFACTS/'manifest.json').write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
