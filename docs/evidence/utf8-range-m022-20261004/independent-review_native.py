#!/usr/bin/env python3
"""Independent read-only UTF-8 range review. Does not import candidate test code."""
import hashlib, itertools, json, os, pathlib, random, resource, shutil, struct, subprocess, sys, time
sys.dont_write_bytecode = True
ROOT=pathlib.Path('/workspace/scratch/48c5de6446f8/aurora-readonly-text-m022-20261004')
BASE=pathlib.Path(__file__).resolve().parent
OUT=BASE/'native'
CC=pathlib.Path('/workspace/scratch/48c5de6446f8/aurora-xfs-m022-integration-20261004/build/aurorac')
PIN='e1953ce8446973194a66ba579809c37459466f746f491a53a98b1c910ef4110e'
MAX=2**63-1;MIN=-2**63
STATUS=['success','out_of_range','invalid_sequence','truncated']
sha=lambda p:hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def check(x,msg):
    if not x: raise RuntimeError(msg)
def budget(reserve=24<<20):
    used=sum(p.lstat().st_blocks*512 for p in [BASE,*BASE.rglob('*')])
    check(used+reserve<=64<<20, f'review allocation cap: {used} + {reserve}')
    check(shutil.disk_usage(BASE).free-reserve>=1<<30,'global free-space floor')
    return used

def oracle(raw,o,n,f,k):
    if min(o,n,f,k)<0 or o>len(raw) or n>len(raw)-o: return [1,0,0]
    try: text=raw[o:o+n].decode('utf-8',errors='strict')
    except UnicodeDecodeError as ex: return [3 if ex.reason=='unexpected end of data' else 2,0,0]
    if f>len(text) or k>len(text)-f: return [1,0,0]
    return [0,len(text[:f].encode()),len(text[f:f+k].encode())]

def corpus():
    text='A\x00\u0080\u07ff\u0800\ud7ff\ue000\ufeff\uffff\U0010ffff'
    raw=text.encode()
    for f,k in itertools.product(range(12),repeat=2): yield ('all mixedwidth intervals', b'\xff'+raw+b'\x80',1,len(raw),f,k)
    for cp in [0,1,127,128,255,0x7ff,0x800,0xD7FF,0xE000,0xFEFF,0xFFFF,0xFDD0,0xFDEF,0x10000,0x1fffe,0x1ffff,0x10fffe,0x10ffff,0x378,0x301,0x200d]:
        v=chr(cp).encode()
        for f,k in [(0,1),(1,0)]: yield ('scalar policy boundary',b'\xff'+v+b'\xff',1,len(v),f,k)
    bad=[b'\x80',b'\xbf',b'\xc0\x80',b'\xc1\xbf',b'\xc2',b'\xc2\x7f',b'\xdf\xc0',b'\xe0',b'\xe0\x9f',b'\xe0\xa0',b'\xed\xa0',b'\xed\xbf\xbf',b'\xe1\x80',b'\xef\xbf',b'\xef\xbf\x7f',b'\xf0',b'\xf0\x8f',b'\xf0\x90',b'\xf0\x90\x80',b'\xf4\x8f\xbf',b'\xf4\x90',b'\xf4\x90\x80\x80',b'\xf5',b'\xff',b'\xf1\x80A']
    for v in bad:
        for f,k in [(0,0),(0,1),(MAX,MAX)]: yield ('bad trailing bytes invalidate early selection',b'A'+v,0,len(v)+1,f,k)
        yield ('malformed prefix',v+b'A',0,len(v)+1,0,1)
    wire='A¢€😀Z'.encode()
    for o in range(len(wire)+1):
        for n in range(len(wire)-o+1): yield ('every byte window',wire,o,n,0,0)
    for d in range(4):
        for v in [MIN,-1,0,1,3,4,MAX]:
            a=[0,4,1,1];a[d]=v;yield ('signed independent coordinate',b'A\xc2\xa2Z',*a)
    for a in itertools.product([MIN,MAX],repeat=4):yield ('combined extreme',b'\xff',*a)
    for f,k in [(-1,0),(0,-1),(MAX,0),(0,MAX)]:yield ('negative versus malformed precedence',b'\xff',0,1,f,k)
    rng=random.Random(0x524556494557)
    for _ in range(80):
        chars=[]
        for _ in range(rng.randrange(0,12)):
            cp=rng.randrange(0x110000)
            if 0xd800<=cp<=0xdfff:cp=0
            chars.append(chr(cp))
        text=''.join(chars); raw=text.encode(); f=rng.randrange(len(chars)+2);k=rng.randrange(len(chars)+2)
        yield ('independent random Unicode',b'\xff'+raw+b'\xff',1,len(raw),f,k)
    for _ in range(60):
        raw=rng.randbytes(rng.randrange(1,10));yield ('independent random bytes',raw,0,len(raw),rng.randrange(3),rng.randrange(3))
    raw=b'A'*4092+'😀'.encode()
    for f,k in [(4092,1),(4093,0),(4093,1)]:yield ('maximum owner',raw,0,4096,f,k)

def extract(name):
    return ''.join(f'if(field==0){{if({name}.status()==std::Utf8RangeStatus::{s}){{return {i};}}}}' for i,s in enumerate(STATUS))+f'if(field==1){{return {name}.byte_offset();}}if(field==2){{return {name}.byte_count();}}return -900;'

def native_cases():
    for label,raw,o,n,f,k in corpus():
        vals=','.join(f'{v}u8' for v in raw)
        body=f'builtin::array<u8,{len(raw)}> owner={{{vals}}};i64 before=0;i64 j=0;while(j<len(owner)){{before=before+i64(owner[j])*(j+1);j=j+1;}}'
        body+=f'std::Utf8RangeResult original=std::utf8_subrange(borrow_bytes(owner),{o},{n},{f},{k});const std::Utf8RangeResult snapshot=original;'
        body+='i64 after=0;j=0;while(j<len(owner)){after=after+i64(owner[j])*(j+1);j=j+1;}if(before!=after){return -901;}owner[0]=0u8;'
        yield {'label':label,'args':[raw.hex(),o,n,f,k],'expected':oracle(raw,o,n,f,k),'body':body+extract('snapshot')}
    for status in STATUS:
        for o,n in [(MIN,MIN),(-1,1),(0,MAX),(MAX,0),(MAX,1),(1,MAX),(2,3),(0,0)]:
            v=STATUS.index(status)
            if v==0 and (min(o,n)<0 or o+n>MAX):v=1
            body=f'std::Utf8RangeResult original=std::Utf8RangeResult(std::Utf8RangeStatus::{status},{o},{n});const std::Utf8RangeResult snapshot=original;'
            yield {'label':'fabricated report copy and masking','args':[status,o,n],'expected':[v,o if not v else 0,n if not v else 0],'body':body+extract('snapshot')}
    body='const std::Utf8RangeResult snapshot=escaped();'+extract('snapshot')
    yield {'label':'copied report survives owner and nested reborrow lifetimes','args':[],'expected':[0,1,4],'body':body}

HELPER='auto escaped()->std::Utf8RangeResult{builtin::array<u8,6> owner={65u8,240u8,159u8,152u8,128u8,90u8};const builtin::span<const u8> a=borrow_bytes(owner);const builtin::span<const u8> b=a;const std::Utf8RangeResult r=std::utf8_subrange(b,0,6,1,1);return r;}\n'

def run(argv,d,name,want=0):
    budget();t=time.monotonic()
    def limits():
        resource.setrlimit(resource.RLIMIT_CORE,(0,0));resource.setrlimit(resource.RLIMIT_CPU,(20,21));resource.setrlimit(resource.RLIMIT_FSIZE,(8<<20,8<<20));resource.setrlimit(resource.RLIMIT_AS,((512 if str(argv[0])==str(CC) else 128)<<20,)*2)
    receipt={'argv':list(map(str,argv)),'wall_limit_seconds':45,'cpu_seconds':[20,21],'file_limit_bytes':8<<20,'status':'started'}
    try:
        with (d/(name+'.stdout')).open('wb') as out,(d/(name+'.stderr')).open('wb') as err:
            p=subprocess.run(list(map(str,argv)),stdout=out,stderr=err,timeout=45,preexec_fn=limits)
        receipt['returncode']=p.returncode
        check(p.returncode==want,f'{name}: return {p.returncode}, expected {want}; '+(d/(name+'.stderr')).read_text()[:1000])
        if want==0:check(not (d/(name+'.stderr')).read_bytes(),f'{name}: unexpected stderr')
        receipt['status']='passed';return (d/(name+'.stdout')).read_bytes()
    except Exception as e:receipt.update(status='failed',error=str(e));raise
    finally:
        receipt['seconds']=time.monotonic()-t;(d/(name+'.json')).write_text(json.dumps(receipt,indent=2)+'\n');budget(0)

def batch(cases,i):
    d=OUT/f'batch-{i:03d}';d.mkdir();src='module independent_utf8_range;import std.utf8_range;\n'+HELPER
    src+='\n'.join(f'auto probe{j}(i64 field)->i64{{{c["body"]}}}' for j,c in enumerate(cases))
    check(len(src.encode())<65536,'review source-size limit');(d/'input.au').write_text(src)
    expected=[v for c in cases for v in c['expected']]
    (d/'cases.json').write_text(json.dumps([{k:v for k,v in c.items() if k!='body'} for c in cases],indent=2)+'\n')
    run([CC,'--module-root',ROOT/'library',d/'input.au','-o',d/'generated.s'],d,'compile')
    entry=['.bss','.align 8','observations:',f'.skip {8*len(expected)}','.text','.globl _start','_start:']
    idx=0
    for j in range(len(cases)):
        for field in range(3):entry += [f'movq ${field},%rdi',f'call probe{j}',f'movq %rax,observations+{8*idx}(%rip)'];idx+=1
    entry+=['movq $1,%rax','movq $1,%rdi','leaq observations(%rip),%rsi',f'movq ${8*len(expected)},%rdx','syscall', 'movq $60,%rax','xorq %rdi,%rdi','syscall','.section .note.GNU-stack,"",@progbits']
    (d/'entry.s').write_text('\n'.join(entry)+'\n')
    run(['as','--64',d/'generated.s','-o',d/'generated.o'],d,'assemble');run(['as','--64',d/'entry.s','-o',d/'entry.o'],d,'entry');run(['ld',d/'entry.o',d/'generated.o','-o',d/'probe'],d,'link')
    got=run([d/'probe'],d,'execute');check(len(got)==8*len(expected),'native output length mismatch');values=list(struct.unpack('<'+'q'*len(expected),got));check(values==expected,f'native mismatch batch {i}: '+str([(j,a,b) for j,(a,b) in enumerate(zip(values,expected)) if a!=b][:3]))
    (d/'result.json').write_text(json.dumps({'status':'passed','source_sha256':sha(d/'input.au'),'expected':expected,'observed':values,'output_sha256':hashlib.sha256(got).hexdigest()},indent=2)+'\n')
    print(f'PASS independent batch {i}: {len(cases)} cases',flush=True)

def rejects():
    p='module reject;import std.utf8_range;'
    one='builtin::array<u8,1> owner={65u8};'
    for field in ['outcome','relative_offset','byte_length']:
        yield ('private '+field,p+'auto test()->i64{const std::Utf8RangeResult r=std::Utf8RangeResult(std::Utf8RangeStatus::success,0,0);return r.'+field+';}','private')
    yield ('mutation with nested reborrow',p+'auto test()->i64{'+one+'const builtin::span<const u8> a=borrow_bytes(owner);const builtin::span<const u8> b=a;owner[0]=66u8;const std::Utf8RangeResult r=std::utf8_subrange(b,0,1,0,1);return r.byte_count();}','span is live')
    for cap in [0,4097]:yield ('owner limit '+str(cap),p+f'auto test()->i64{{builtin::array<u8,{cap}> b={{65u8}};const std::Utf8RangeResult r=std::utf8_subrange(borrow_bytes(b),0,1,0,1);return r.byte_count();}}','array')
    yield ('no mutable span',p+'auto test()->i64{'+one+'const builtin::span<u8> a=borrow_bytes(owner);return a.size();}','const')
    yield ('cannot return range as borrowed view',p+'auto test()->builtin::span<const u8>{'+one+'return std::utf8_subrange(borrow_bytes(owner),0,1,0,1);}','only scalar function results')
    yield ('report cannot construct authority',p+'auto test()->i64{const std::Utf8RangeResult r=std::Utf8RangeResult(std::Utf8RangeStatus::success,0,999);const builtin::span<const u8> a=r;return a.size();}','span')
    yield ('dependency not reexported',p+'auto test()->i64{'+one+'const std::Utf8ValidationResult r=std::validate_utf8(borrow_bytes(owner),0,1,true);return r.scalar_count();}',"unknown function 'std::validate_utf8'")

def main():
    check(sha(CC)==PIN,'compiler pin mismatch');frozen=json.loads((ROOT/'work/source-freeze-v2.json').read_text());check(all(sha(ROOT/x['path'])==x['sha256'] for x in frozen['files']),'candidate mismatch');check(not OUT.exists(),'fresh output required');budget();OUT.mkdir()
    summary={'status':'running','compiler_sha256':PIN,'source_freeze_sha256':sha(ROOT/'work/source-freeze-v2.json'),'python':sys.version,'script_sha256':sha(__file__),'cases':0,'rejections':0};(BASE/'tool-versions.txt').write_text(subprocess.check_output(['as','--version'],text=True)+subprocess.check_output(['ld','--version'],text=True))
    try:
        items=list(native_cases());print('Independent native cases:',len(items),flush=True)
        batches=[];current=[]
        for item in items:
            if current and (len(current)>=16 or sum(len(c['body']) for c in current)+len(item['body'])>60000):batches.append(current);current=[]
            current.append(item)
        if current:batches.append(current)
        for i,group in enumerate(batches):batch(group,i);summary['cases']+=len(group)
        for i,(label,source,token) in enumerate(rejects()):
            d=OUT/f'reject-{i:02d}';d.mkdir();(d/'input.au').write_text(source);marker=b'preserve the old output\n';(d/'generated.s').write_bytes(marker)
            run([CC,'--module-root',ROOT/'library',d/'input.au','-o',d/'generated.s'],d,'compile',1)
            diag=(d/'compile.stderr').read_text();check(token in diag.lower(),f'rejection diagnostic mismatch for {label}: {diag}');check((d/'generated.s').read_bytes()==marker,'rejected input overwrote output');(d/'result.json').write_text(json.dumps({'label':label,'status':'passed','diagnostic':diag},indent=2)+'\n');summary['rejections']+=1
        check(sha(CC)==PIN,'compiler drift');check(all(sha(ROOT/x['path'])==x['sha256'] for x in frozen['files']),'source drift');summary.update(status='passed',full_i64_observations=3*summary['cases'],batches=len(batches));print(json.dumps(summary),flush=True)
    except Exception as e:summary.update(status='failed',error=str(e));raise
    finally:summary['allocated_bytes']=budget(0);(BASE/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
if __name__=='__main__':main()
