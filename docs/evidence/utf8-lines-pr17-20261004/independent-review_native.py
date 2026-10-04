#!/usr/bin/env python3
"""Independent UTF-8 line review: no candidate test imports or oracle reuse."""
import collections, hashlib, itertools, json, pathlib, random, resource, shutil, struct, subprocess, sys, time, tarfile
sys.dont_write_bytecode = True
BASE = pathlib.Path(__file__).resolve().parent
ROOT = BASE.parent / 'aurora-utf8-lines-pr17-20261004'
OUT = BASE / 'native'
CC = BASE.parent / 'aurora-package-identity-pr16-integration-20261004/build/aurorac'
PIN = 'e1953ce8446973194a66ba579809c37459466f746f491a53a98b1c910ef4110e'
MIN, MAX = -(1<<63), (1<<63)-1
S = ['success', 'end_of_input', 'out_of_range', 'invalid_sequence', 'truncated']
E = ['none', 'lf', 'crlf']
sha = lambda p: hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def require(ok, reason):
    if not ok: raise RuntimeError(reason)
def budget(reserve=24<<20):
    used = sum(p.lstat().st_blocks*512 for p in [BASE, *BASE.rglob('*')])
    require(used + reserve <= 64<<20, f'64 MiB review allocation cap: {used} + {reserve}')
    require(shutil.disk_usage(BASE).free - reserve >= 1<<30, '1 GiB global free-space floor')
    return used
def oracle(raw, offset, count):
    if offset < 0 or count < 0 or offset > len(raw) or offset + count > len(raw): return [2,0,0,0]
    if not count: return [1,0,0,0]
    selected = raw[offset:offset+count]
    content, separator, suffix = selected.partition(b'\n')
    consumed = content + separator
    try: consumed.decode('utf-8', errors='strict')
    except UnicodeDecodeError as ex: return [4 if ex.reason == 'unexpected end of data' else 3,0,0,0]
    ending = 2 if separator and content.endswith(b'\r') else 1 if separator else 0
    return [0, len(consumed)-ending, len(consumed), ending]
def partitions(raw):
    # Byte partition plus strict decoding: Python splitlines is intentionally not used.
    cursor = 0; lines = []
    while True:
        result = oracle(raw,cursor,len(raw)-cursor); lines.append(result)
        if result[0] != 0: break
        require(result[2] > 0, 'oracle progress')
        data = raw[cursor:cursor+result[1]]
        tail = raw[cursor+result[1]:cursor+result[2]]
        require(data.decode('utf-8').encode('utf-8') == data, 'oracle strict content roundtrip')
        require(tail == (b'',b'\n',b'\r\n')[result[3]], 'oracle exact terminator')
        cursor += result[2]
    require(b''.join(raw[sum(x[2] for x in lines[:i]):sum(x[2] for x in lines[:i+1])] for i in range(len(lines)-1)) == raw[:cursor], 'reconstruction')
    return lines
def array(raw):
    raw = raw or b'\xff'
    return f'builtin::array<u8,{len(raw)}> owner={{'+','.join(f'{x}u8' for x in raw)+'};'
def observe(name='r'):
    code = 'if(field==0){'+''.join(f'if({name}.status()==std::Utf8LineStatus::{s}){{return {i};}}' for i,s in enumerate(S))+'return -900;}'
    code += f'if(field==1){{return {name}.content_bytes();}}if(field==2){{return {name}.consumed_bytes();}}'
    return code + ''.join(f'if({name}.ending()==std::Utf8LineEnding::{e}){{return {i};}}' for i,e in enumerate(E))+'return -901;'
def corpus():
    for b in range(256):
        raw=bytes([b])+b'\n'; yield 'every byte then LF',raw,0,len(raw)
    for raw in [b'',b'\n\n\r\n',b'\r\n\r',b'\xc2\xa2\n\xe2\x82\xac\r\n\xf0\x9f\x98\x80',b'A\n\xff']:
        owner=b'\xff'+raw+b'\xff'
        for a in range(len(raw)+1):
            for b in range(len(raw)-a+1): yield 'every byte window with poisoned margins',owner,a+1,b
    bad=[b'\x80',b'\xbf',b'\xc0\x80',b'\xc1\xbf',b'\xc2',b'\xc2\x7f',b'\xdf\xc0',b'\xe0',b'\xe0\x9f',b'\xe0\xa0',b'\xed\xa0',b'\xed\xbf\xbf',b'\xe1\x80',b'\xef\xbf',b'\xef\xbf\x7f',b'\xf0',b'\xf0\x8f',b'\xf0\x90',b'\xf0\x90\x80',b'\xf4\x8f\xbf',b'\xf4\x90',b'\xf4\x90\x80\x80',b'\xf5',b'\xff',b'\xf1\x80A']
    for fragment in bad:
        for prefix,tail in [(b'',b''),(b'',b'\n'),(b'\xe2\x82\xac',b'\r\n')]:
            raw=prefix+fragment+tail;yield 'malformed prefix before delimiter or final',raw,0,len(raw)
        raw=b'good\r\n'+fragment;yield 'invalid suffix deferred',raw,0,len(raw)
    scalars=[0,1,27,127,128,0x85,0x7ff,0x800,0xd7ff,0xe000,0xfeff,0xffff,0xfdd0,0xfdef,0x10000,0x1fffe,0x10ffff,0x378,0x301,0x200d,0x2028,0x2029]
    for cp,tail in itertools.product(scalars,[b'',b'\n',b'\r\n']):
        raw=chr(cp).encode()+tail;yield 'scalar boundaries and ordinary content policy',b'\xff'+raw+b'\xff',1,len(raw)
    for a,b in itertools.product([MIN,-1,0,1,2,3,4,MAX],repeat=2):yield 'signed extremes and range precedence',b'\xff\nA',a,b
    rng=random.Random(0x4c494e45524556)
    for _ in range(60):
        raw=bytes(rng.randrange(256) for _ in range(rng.randrange(1,19)));yield 'independent arbitrary bytes',raw,0,len(raw)
    for _ in range(45):
        chars=[]
        for _ in range(rng.randrange(1,20)):
            cp=rng.choice(scalars+[10,13,rng.randrange(0x110000)])
            chars.append(chr(0 if 0xd800<=cp<=0xdfff else cp))
        raw=''.join(chars).encode();yield 'independent random scalar sequences',b'\xff'+raw+b'\xff',1,len(raw)
    for raw in [b'A'*4096,b'A'*4095+b'\n',b'A'*4094+b'\r\n',b'\n'+b'\xff'*4095,b'A'*4091+'😀'.encode()+b'\n',b'A'*4093+b'\xe2\x82\n',b'A'*4093+b'\xf4\x8f\xbf']:
        yield '4096-byte owner boundary',raw,0,len(raw)
def native_cases():
    for label,raw,a,b in corpus():
        body=array(raw)+f'const builtin::array<u8,{max(1,len(raw))}> saved=owner;'
        body+=f'const std::Utf8LineResult original=std::read_utf8_line(borrow_bytes(owner),{a},{b});'
        body+='i64 j=0;while(j<len(owner)){if(owner[j]!=saved[j]){return -902;}j=j+1;}owner[0]=0u8;const std::Utf8LineResult r=original;'+observe()
        yield dict(label=label,args=[raw.hex(),a,b],expected=oracle(raw,a,b),body=body)
    for status,ending,n in itertools.product(range(5),range(3),[MIN,-1,0,1,MAX-2,MAX-1,MAX]):
        actual = status
        if actual==0 and (n<0 or n+ending>MAX or n+ending==0): actual=2
        body=f'const std::Utf8LineResult original=std::Utf8LineResult(std::Utf8LineStatus::{S[status]},{n},std::Utf8LineEnding::{E[ending]});const std::Utf8LineResult r=original;'+observe()
        yield dict(label='constructor masking and arithmetic invariants',args=[status,ending,n],expected=[actual,n if actual==0 else 0,n+ending if actual==0 else 0,ending if actual==0 else 0],body=body)
    yield dict(label='result outlives local owner and nested reborrow',args=[],expected=[0,4,6,2],body='const std::Utf8LineResult r=escaped();'+observe())
    inputs=[b'',b'\n',b'\n\n',b'\r\n\r\n',b'\r',b'\r\r\n\n\r',b'A\rB\nC\r',b'\0\n\xef\xbb\xbf\r\n\x1b',b'\xc2\x85\xe2\x80\xa8\xe2\x80\xa9',b'one\ntwo\r\nthree',b'good\n\xff',b'\n\xc2',b'A\nB\r\n\xe2\x82',b'\xf4\x8f\xbf\xbf\r\n\xe2\x82\xac\n']
    rng=random.Random(0x50524f4752455353)
    for _ in range(24):
        raw=b''.join(rng.choice([b'\n',b'\r\n',b'\r',b'a','€'.encode(),'😀'.encode(),b'\x00']) for _ in range(20))
        inputs.append(raw+rng.choice([b'',b'\xff',b'\xe2\x82']))
    for raw in inputs:
        lines=partitions(raw);body=array(b'\xff'+raw+b'\xff')+'i64 used=0;i64 steps=0;i64 content=0;bool done=false;while(!done){'
        body+=f'const std::Utf8LineResult r=std::read_utf8_line(borrow_bytes(owner),1+used,{len(raw)}-used);'
        for index,(s,c,n,e) in enumerate(lines):
            body+=f'if(steps=={index}){{if(r.status()!=std::Utf8LineStatus::{S[s]}){{return -910;}}if(r.content_bytes()!={c}){{return -911;}}if(r.consumed_bytes()!={n}){{return -912;}}if(r.ending()!=std::Utf8LineEnding::{E[e]}){{return -913;}}}}'
        body+=f'if(steps>{len(lines)-1}){{return -914;}}'
        body+='if(r.status()==std::Utf8LineStatus::success){if(r.consumed_bytes()<=0){return -915;}if(r.ending()==std::Utf8LineEnding::lf){if(owner[1+used+r.content_bytes()]!=10u8){return -916;}}if(r.ending()==std::Utf8LineEnding::crlf){if(owner[1+used+r.content_bytes()]!=13u8){return -917;}if(owner[2+used+r.content_bytes()]!=10u8){return -918;}}used=used+r.consumed_bytes();content=content+r.content_bytes();}else{done=true;}steps=steps+1;}'
        body+='if(field==0){return steps;}if(field==1){return used;}if(field==2){return content;}return 42;'
        yield dict(label='full repeated sequence exact per-line observations',args=[raw.hex()],expected=[len(lines),sum(x[2] for x in lines),sum(x[1] for x in lines),42],per_line_expected=lines,body=body)
    for term,width in [(b'\n',1),(b'\r\n',2)]:
        raw=term*(4096//width);body=array(raw)+'i64 used=0;i64 steps=0;while(used<4096){const std::Utf8LineResult r=std::read_utf8_line(borrow_bytes(owner),used,4096-used);'
        body+=f'if(r.status()!=std::Utf8LineStatus::success){{return -920;}}if(r.content_bytes()!=0){{return -921;}}if(r.consumed_bytes()!={width}){{return -922;}}if(r.ending()!=std::Utf8LineEnding::{E[width]}){{return -923;}}used=used+r.consumed_bytes();steps=steps+1;}}'
        body+='const std::Utf8LineResult end=std::read_utf8_line(borrow_bytes(owner),used,0);if(end.status()!=std::Utf8LineStatus::end_of_input){return -924;}if(end.content_bytes()!=0){return -925;}if(end.consumed_bytes()!=0){return -926;}if(end.ending()!=std::Utf8LineEnding::none){return -927;}if(field==0){return steps;}if(field==1){return used;}if(field==2){return 0;}return 42;'
        yield dict(label='4096-byte consecutive delimiters exact progress and no phantom line',args=[width],expected=[4096//width,4096,0,42],body=body)
HELPER='auto escaped()->std::Utf8LineResult{builtin::array<u8,7> owner={240u8,159u8,152u8,128u8,13u8,10u8,255u8};const builtin::span<const u8> a=borrow_bytes(owner);const builtin::span<const u8> b=a;const std::Utf8LineResult r=std::read_utf8_line(b,0,7);return r;}\n'
def run(argv,d,name,want=0):
    budget();start=time.monotonic();as_limit=(512 if str(argv[0])==str(CC) else 128)<<20
    def limits():
        resource.setrlimit(resource.RLIMIT_CORE,(0,0));resource.setrlimit(resource.RLIMIT_CPU,(20,21));resource.setrlimit(resource.RLIMIT_FSIZE,(8<<20,8<<20));resource.setrlimit(resource.RLIMIT_AS,(as_limit,as_limit))
    receipt=dict(argv=list(map(str,argv)),wall_seconds=45,cpu_seconds=[20,21],address_space_bytes=as_limit,file_limit_bytes=8<<20,status='running')
    try:
        with (d/(name+'.stdout')).open('wb') as out,(d/(name+'.stderr')).open('wb') as err:p=subprocess.run(list(map(str,argv)),stdout=out,stderr=err,timeout=45,preexec_fn=limits)
        receipt['returncode']=p.returncode;require(p.returncode==want,f'{name} exit {p.returncode}, expected {want}: '+(d/(name+'.stderr')).read_text()[:1500])
        if want==0:require(not (d/(name+'.stderr')).read_bytes(),name+' unexpected stderr')
        receipt['status']='passed';return (d/(name+'.stdout')).read_bytes()
    except Exception as e:receipt.update(status='failed',error=str(e));raise
    finally:receipt['seconds']=time.monotonic()-start;(d/(name+'.json')).write_text(json.dumps(receipt,indent=2)+'\n');budget(0)
def batch(items,index):
    d=OUT/f'batch-{index:03d}';d.mkdir();source='module independent_utf8_lines;import std.utf8_lines;\n'+HELPER
    source+='\n'.join(f'auto probe{i}(i64 field)->i64{{{x["body"]}}}' for i,x in enumerate(items));require(len(source.encode())<65536,'source cap');(d/'input.au').write_text(source)
    wanted=[v for x in items for v in x['expected']];(d/'cases.json').write_text(json.dumps([{k:v for k,v in x.items() if k!='body'} for x in items],indent=2)+'\n')
    run([CC,'--module-root',ROOT/'library',d/'input.au','-o',d/'generated.s'],d,'compile')
    entry=['.bss','.align 8','observations:',f'.skip {8*len(wanted)}','.text','.globl _start','_start:']
    n=0
    for i in range(len(items)):
        for field in range(4):entry += [f'movq ${field},%rdi',f'call probe{i}',f'movq %rax,observations+{8*n}(%rip)'];n+=1
    entry+=['movq $1,%rax','movq $1,%rdi','leaq observations(%rip),%rsi',f'movq ${8*len(wanted)},%rdx','syscall','movq $60,%rax','xorq %rdi,%rdi','syscall','.section .note.GNU-stack,"",@progbits'];(d/'entry.s').write_text('\n'.join(entry)+'\n')
    run(['as','--64',d/'generated.s','-o',d/'generated.o'],d,'assemble');run(['as','--64',d/'entry.s','-o',d/'entry.o'],d,'entry');run(['ld',d/'entry.o',d/'generated.o','-o',d/'probe'],d,'link');got=run([d/'probe'],d,'execute')
    require(len(got)==8*len(wanted),'native output length');observed=list(struct.unpack('<'+'q'*len(wanted),got));require(wanted==observed,f'batch {index} mismatch '+str([(i,a,b) for i,(a,b) in enumerate(zip(wanted,observed)) if a!=b][:8]))
    (d/'result.json').write_text(json.dumps(dict(status='passed',source_sha256=sha(d/'input.au'),expected=wanted,observed=observed,output_sha256=hashlib.sha256(got).hexdigest()),indent=2)+'\n');print(f'PASS independent batch {index}: {len(items)} cases',flush=True)
def rejects():
    h='module reject;import std.utf8_lines;';a='builtin::array<u8,1> owner={65u8};';r='const std::Utf8LineResult r=std::Utf8LineResult(std::Utf8LineStatus::success,1,std::Utf8LineEnding::none);'
    for f in ['outcome','content_length','terminator']:yield 'private field '+f,h+'auto test()->i64{'+r+'return r.'+f+';}','private'
    yield 'nested readonly reborrow prevents mutation',h+'auto test()->i64{'+a+'const builtin::span<const u8> x=borrow_bytes(owner);const builtin::span<const u8> y=x;owner[0]=66u8;const std::Utf8LineResult r=std::read_utf8_line(y,0,1);return r.content_bytes();}','span is live'
    for cap in [0,4097]:yield 'owner bound '+str(cap),h+f'auto test()->i64{{builtin::array<u8,{cap}> owner={{65u8}};return 0;}}','array'
    yield 'mutable span rejected',h+'auto test()->i64{'+a+'const builtin::span<u8> v=borrow_bytes(owner);return v.size();}','const'
    yield 'cannot return borrowed report',h+'auto test()->builtin::span<const u8>{'+a+'return std::read_utf8_line(borrow_bytes(owner),0,1);}','only scalar function results'
    yield 'report grants no span authority',h+'auto test()->i64{'+r+'const builtin::span<const u8> v=r;return v.size();}','span'
    yield 'retained span cannot be class field',h+'class Bad{builtin::span<const u8> v;};auto test()->i64{return 0;}','class fields require'
    for helper,args in [('utf8_line_checked','borrow_bytes(owner),0,1,std::Utf8LineEnding::none'),('utf8_line_failure','std::Utf8LineStatus::success')]:yield 'private helper '+helper,h+'auto test()->i64{'+a+f'const std::Utf8LineResult r=std::{helper}({args});return r.content_bytes();}}','private function is not imported'
    yield 'dependency not reexported',h+'auto test()->i64{'+a+'const std::Utf8ValidationResult v=std::validate_utf8(borrow_bytes(owner),0,1,true);return v.scalar_count();}',"unknown function 'std::validate_utf8'"
    yield 'wrong coordinate type',h+'auto test()->i64{'+a+'const std::Utf8LineResult r=std::read_utf8_line(borrow_bytes(owner),0,1u64);return r.content_bytes();}','expected i64, got u64'
    yield 'closed ending enum is nominal',h+'auto test()->i64{const std::Utf8LineResult r=std::Utf8LineResult(std::Utf8LineStatus::success,1,1);return r.content_bytes();}','expected std::utf8lineending'
def verify(frozen):
    require(sha(CC)==PIN,'compiler drift')
    for f in frozen['files']:
        p=ROOT/f['path'];require(p.is_file() and sha(p)==f['sha256'] and p.stat().st_size==f['bytes'] and f'{p.stat().st_mode&0o777:04o}'==f['mode'],'source drift: '+f['path'])
def main():
    frozen=json.loads((ROOT/'work/source-freeze-v1.json').read_text());verify(frozen);require(not OUT.exists(),'fresh output required');budget();OUT.mkdir()
    summary=dict(status='running',compiler_path=str(CC),compiler_sha256=PIN,source_freeze_sha256=sha(ROOT/'work/source-freeze-v1.json'),script_sha256=sha(__file__),python=sys.version,cases=0,rejections=0)
    (BASE/'tool-versions.txt').write_text(subprocess.check_output(['as','--version'],text=True)+subprocess.check_output(['ld','--version'],text=True))
    try:
        items=list(native_cases());(BASE/'coverage.json').write_text(json.dumps(dict(collections.Counter(x['label'] for x in items)),indent=2)+'\n');print('Independent cases:',len(items),flush=True)
        groups=[];group=[]
        for item in items:
            if group and (len(group)>=16 or sum(len(x['body']) for x in group)+len(item['body'])>60000):groups.append(group);group=[]
            group.append(item)
        if group:groups.append(group)
        for i,group in enumerate(groups):batch(group,i);summary['cases']+=len(group)
        for i,(label,source,token) in enumerate(rejects()):
            d=OUT/f'reject-{i:02d}';d.mkdir();(d/'input.au').write_text(source);marker=b'preserve existing output\n';(d/'generated.s').write_bytes(marker);run([CC,'--module-root',ROOT/'library',d/'input.au','-o',d/'generated.s'],d,'compile',1)
            diag=(d/'compile.stderr').read_text();require(token in diag.lower(),f'diagnostic mismatch {label}: {diag}');require((d/'generated.s').read_bytes()==marker,'rejection changed output');(d/'result.json').write_text(json.dumps(dict(label=label,status='passed',diagnostic=diag),indent=2)+'\n');summary['rejections']+=1
        verify(frozen);summary.update(status='passed',full_i64_observations=4*summary['cases'],batches=len(groups));print(json.dumps(summary),flush=True)
    except Exception as e:summary.update(status='failed',error=str(e));raise
    finally:summary['allocated_bytes']=budget(0);(BASE/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
if __name__=='__main__':main()
