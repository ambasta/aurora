#!/usr/bin/env python3
"""Independent native UTF-8 oracle; Python strict codec, no candidate-model reuse.
Compiles are separate. Bounded 8192-case runtime batches feed only scalar entries.
No assertion statement is used: checks survive Python -O. Target signals/timeouts
and incomplete output are failures. Native library calls repeat with identical
input and compare original storage before lexical borrow release and owner write.
"""
import argparse, hashlib, itertools, json, random, resource, struct, subprocess, time
from collections import Counter
from pathlib import Path
HERE=Path(__file__).resolve().parent
LIB=HERE.parent/'aurora-utf8-next/library/std/utf8.au'
PIN='6ad8d1c11ce26197932e2118151a7761e518ea2db7dc64a1fd1a3e956761f31c'
MAX=2**63-1; MIN=-2**63; SENTINEL=2**21-1

def require(ok,msg):
    if not ok: raise RuntimeError(msg)

def oracle(data,offset,count,final):
    if offset<0 or count<0 or offset>len(data) or count>len(data)-offset:
        return (2,0,SENTINEL,2,0,0)
    selected=data[offset:offset+count]
    ds=1; width=0; scalar=SENTINEL
    if selected:
        for n in range(1,min(4,len(selected))+1):
            try:
                decoded=selected[:n].decode('utf-8','strict')
                require(len(decoded)==1,'decoder oracle unexpected length')
                ds=0; width=n; scalar=ord(decoded); break
            except UnicodeDecodeError as error:
                if error.reason!='unexpected end of data': ds=3; break
                ds=4 if final else 5
    try:
        decoded=selected.decode('utf-8','strict'); vs=0; used=len(selected); scalars=len(decoded)
    except UnicodeDecodeError as error:
        vs=(4 if final else 5) if error.reason=='unexpected end of data' else 3
        used=error.start; scalars=len(selected[:used].decode('utf-8','strict'))
    return ds,width,scalar,vs,used,scalars

def encode(fields):
    ds,width,scalar,vs,used,count=fields
    return ds|(width<<3)|(scalar<<6)|(vs<<27)|(used<<30)|(count<<34)

def case(data,count=None,offset=0,final=True):
    require(len(data)<=8,'oversized testcase')
    if count is None: count=len(data)-offset
    return data.ljust(8,b'\xff'),offset,count,final

def vectors():
    for raw,expected in [(b'A',(0,1,65,0,1,1)),(b'',(1,0,SENTINEL,0,0,0)),(b'\xe0\x80',(3,0,SENTINEL,3,0,0)),(b'\xe0\xa0',(4,0,SENTINEL,4,0,0)),(b'\xf4\x90',(3,0,SENTINEL,3,0,0)),(b'A\xf0\x90',(0,1,65,4,1,1)),(b'\xed\xa0\x80',(3,0,SENTINEL,3,0,0))]:
        require(oracle(*case(raw))==expected,'golden oracle mismatch '+raw.hex())
    # Direct Unicode 17 Table 3-7 anchors for precedence, independent of codec timing.
    for first,lo,hi in ((0xed,0xa0,0xbf),(0xe0,0x80,0x9f),(0xf0,0x80,0x8f),(0xf4,0x90,0xbf)):
        for second,final in itertools.product(range(lo,hi+1),(False,True)):
            require(oracle(*case(bytes((first,second)),final=final))==(3,0,SENTINEL,3,0,0),'Table 3-7 invalid-prefix precedence mismatch')
    require(oracle(*case(b'\xe0\xa0',final=False))[0]==5,'nonfinal oracle mismatch')
    require(oracle(*case(b'A',count=MAX))[0]==2,'range oracle mismatch')

def ranges():
    raw=b'A\xc2\xa2\xe2\x82\xac\xf0\x90'
    for offset,count,final in itertools.product((MIN,-1,0,1,2,3,4,7,8,9,MAX),(MIN,-1,0,1,2,3,4,7,8,9,MAX),(False,True)):
        yield case(raw,count,offset,final)

def two_bytes():
    for length in (0,1,2):
        for t in itertools.product(range(256),repeat=length):
            for final in (False,True): yield case(bytes(t),final=final)

def scalars():
    for cp in range(0x110000):
        if 0xd800<=cp<=0xdfff: continue
        b=chr(cp).encode('utf-8','strict')
        offset=cp%5
        yield case(b'\xff'*offset+b,count=len(b),offset=offset,final=bool(cp%2))

def extended_boundaries():
    edges=(0,0x7f,0x80,0x8f,0x90,0x9f,0xa0,0xbf,0xc0,0xff)
    for lead in (0xc2,0xdf,0xe0,0xe1,0xec,0xed,0xee,0xef,0xf0,0xf1,0xf3,0xf4,0xf5,0xff):
        for b,c,d in itertools.product(edges,repeat=3):
            raw=bytes((lead,b,c,d))
            for size,final in itertools.product((3,4),(False,True)):
                yield case(raw,count=size,final=final)
    for lead,lo,hi in ((0xe0,0xa0,0xbf),(0xe1,0x80,0xbf),(0xed,0x80,0x9f),(0xef,0x80,0xbf),(0xf0,0x90,0xbf),(0xf1,0x80,0xbf),(0xf4,0x80,0x8f)):
        for second,other,final in itertools.product((lo,hi),range(256),(False,True)):
            yield case(bytes((lead,second,other)),final=final)
            if lead>=0xf0:
                yield case(bytes((lead,second,0x80,other)),final=final)

def replay_windows():
    cps=(0,0x7f,0x80,0x7ff,0x800,0xfff,0x1000,0xcfff,0xd000,0xd7ff,0xe000,0xfdcf,0xfdd0,0xfdef,0xfdf0,0xfeff,0xfffe,0xffff,0x10000,0x3ffff,0x40000,0xfffff,0x100000,0x10fffe,0x10ffff,0x378)
    for cp in cps:
        b=chr(cp).encode()
        for prefix in (b'',b'A',b'\xc2\xa2',b'\xe2\x82\xac'):
            for split,final in itertools.product(range(len(b)+1),(False,True)):
                joined=prefix+b
                yield case(joined,count=len(prefix)+split,final=final)
                yield case(b[split:],final=final)
                yield case(b,final=final)
                yield case(joined+b'\xff',final=final)
                for offset in range(9-len(joined)):
                    yield case(b'\xff'*offset+joined,count=len(joined),offset=offset,final=final)

def random_cases():
    rng=random.Random(0x17c0ffee)
    good=[chr(cp).encode() for cp in (0,65,127,128,0x378,0x7ff,0x800,0xd7ff,0xe000,0xfeff,0xffff,0x10000,0x10ffff)]
    for i in range(50000):
        raw=bytes(rng.randrange(256) for _ in range(8)) if i%2 else b''.join(rng.choice(good) for _ in range(8))[:8]
        offset=rng.randrange(9); count=rng.randrange(9-offset)
        yield case(raw,count,offset,bool(i%3))

def check_output(run,expected):
    require(run.returncode==0,'native exit/signal '+str(run.returncode))
    require(not run.stderr,'unexpected native stderr')
    require(len(run.stdout)==8*len(expected),'native output length mismatch')
    actual=struct.unpack('<'+'Q'*len(expected),run.stdout)
    for i,(a,e) in enumerate(zip(actual,expected)):
        require(a==e,f'native mismatch at batch index {i}: observed {a:016x} expected {e:016x}')

def self_test():
    vectors()
    for kwargs in (dict(returncode=-4,stdout=b'',stderr=b''),dict(returncode=0,stdout=b'\0'*7,stderr=b''),dict(returncode=0,stdout=struct.pack('<Q',0),stderr=b'')):
        try: check_output(subprocess.CompletedProcess([],**kwargs),[42])
        except RuntimeError: pass
        else: raise RuntimeError('oracle harness accepted corrupt observation')
    check_output(subprocess.CompletedProcess([],0,struct.pack('<Q',42),b''),[42])


def native_limits():
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    resource.setrlimit(resource.RLIMIT_CPU,(15,15))
    resource.setrlimit(resource.RLIMIT_AS,(256*1024*1024,256*1024*1024))
    resource.setrlimit(resource.RLIMIT_FSIZE,(64*1024*1024,64*1024*1024))

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('binary',nargs='?');parser.add_argument('--self-test-only',action='store_true');args=parser.parse_args()
    self_test()
    if args.self_test_only: print('PASS self-tests under active checks');return
    require(args.binary,'missing binary');binary=Path(args.binary).resolve()
    require(hashlib.sha256(LIB.read_bytes()).hexdigest()==PIN,'candidate library source drift')
    report={'library_sha256':PIN,'native_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'python_oracle':'Python strict UTF-8 codec; no candidate branch/model reuse','batch_limit':8192,'per_batch_timeout_seconds':20,'seed':0x17c0ffee,'native_limits':{'cpu_seconds':15,'address_space_bytes':256*1024*1024,'file_bytes':64*1024*1024,'core_bytes':0},'groups':[]}
    start=time.monotonic();digest=hashlib.sha256()
    for name,generator in [('strict_signed_ranges',ranges),('all_0_1_2_byte_sequences',two_bytes),('all_unicode_scalar_values',scalars),('longer_boundary_classes',extended_boundaries),('stateless_replay_and_windows',replay_windows),('random_windows',random_cases)]:
        begin=time.monotonic();total=0;batch=[];hist=Counter()
        def flush():
            nonlocal total
            if not batch:return
            data=b''.join(struct.pack('<QqqQ',int.from_bytes(raw,'little'),o,c,int(f)) for raw,o,c,f in batch)
            fields=[oracle(*x) for x in batch];expected=[encode(x) for x in fields];digest.update(data)
            try:
                run=subprocess.run([binary],input=data,capture_output=True,timeout=20,preexec_fn=native_limits)
                check_output(run,expected)
            except Exception as error:
                (HERE/'failure-input.bin').write_bytes(data)
                (HERE/'failure.json').write_text(json.dumps({'group':name,'completed':total,'error':str(error),'cases':[(r.hex(),o,c,f) for r,o,c,f in batch]},indent=2))
                raise
            hist.update(str(x[0])+'/'+str(x[3]) for x in fields);total+=len(batch);batch.clear()
        for item in generator():
            batch.append(item)
            if len(batch)>=8192:flush()
        flush();entry={'name':name,'cases':total,'seconds':round(time.monotonic()-begin,3),'decode_validation_status_histogram':dict(hist)};report['groups'].append(entry);print('PASS',json.dumps(entry),flush=True)
    require(hashlib.sha256(LIB.read_bytes()).hexdigest()==PIN,'candidate library source drift during run')
    report.update(total_cases=sum(x['cases'] for x in report['groups']),corpus_sha256=digest.hexdigest(),seconds=round(time.monotonic()-start,3))
    (HERE/(binary.name+'-results.json')).write_text(json.dumps(report,indent=2)+'\n')
    print('PASS TOTAL',report['total_cases'],'SECONDS',report['seconds'],'CORPUS',report['corpus_sha256'],flush=True)
if __name__=='__main__':main()
