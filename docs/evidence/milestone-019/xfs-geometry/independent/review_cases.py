"""Review corpus authored without loading the candidate implementation/tests."""
from review_oracle import *
import random

def build(data,seed=193706):
    cases=[]
    def add(n,d):cases.append((n,bytes(d)))
    def m(n,**fields):add(n,mutate(data,**fields))
    add('real_canonical',data)
    # Complete positive exponent matrix and endpoint variants.
    for bl in range(10,17):
        for il in range(9,min(bl,11)+1):
            B=2**bl; A=2**24//B; I=2**il; align=64*I//B
            f=dict(blocksize=B,blocklog=bl,inodesize=I,inodelog=il,inopblock=B//I,inopblog=bl-il,agblocks=A,agblklog=(A-1).bit_length(),agcount=4,dblocks=4*A,logstart=2*(2**((A-1).bit_length()))+7,logblocks=64,rextsize=max(1,4096//B),inoalignmt=align,spino_align=0)
            for directory in [0,16-bl]:
                for sector in [0,1]:
                    for stripe in [0,1]:
                        q=dict(f,dirblklog=directory,versionnum=0xbca5 if sector else 0xb4a5,logsectsize=512 if sector else 0,logsectlog=9 if sector else 0,logsunit=stripe)
                        add(f'exponents_{bl}_{il}_dir{directory}_sector{sector}_stripe{stripe}',mutate(data,**q))
    for A in [4096,4097,8191,16383,16385,30000,32767,32768,32769,268435456]:
        lg=(A-1).bit_length()
        for N in [1,2,4,17]:
            for tail in [64,A-1,A]:
                D=(N-1)*A+tail
                f=dict(agblocks=A,agcount=N,dblocks=D,agblklog=lg,logstart=((N-1)<<lg)+tail-1,logblocks=1)
                add(f'positive_A{A}_N{N}_tail{tail}',mutate(data,**f))
    for offset in [0,1,2,3,108,119,232,511]:
        b=bytearray(data);b[offset]^=0x80;add(f'unrepaired_byte{offset}',b)
        if offset>=108 and offset not in range(120,128):add(f'ignored_crc_covered_byte{offset}',repaired(b))
    for n in [1,224,264,511,513,1024,4096]:add(f'length{n}',(data*8)[:n])
    for v in [0,4,6,15,65524]:m(f'old_version{v}',versionnum=v)
    for v in [0,1,256,1024,4096,65535]:m(f'old_sector{v}',sectsize=v)
    for v in [0,8,10,63,64,255]:m(f'old_sectlog{v}',sectlog=v)
    for field in ['compat','ro_compat','incompat','log_incompat']:
        for bit in range(32):
            base=int.from_bytes(data[FIELDS[field][0]:FIELDS[field][0]+4],'big')
            m(f'feature_{field}_bit{bit}',**{field:base^(1<<bit)})
        m(f'feature_{field}_all',**{field:MASK})
    for bit in range(4,16):m(f'version_toggle_{bit}',versionnum=0xb4a5^(1<<bit))
    for bit in range(32):m(f'features2_toggle_{bit}',features2=0x18a^(1<<bit))
    for v in [0,1,0x18b,0xffffffff]:m(f'mirror{v}',bad_features2=v)
    for field in ['inprogress','flags','shared_vn','imax_pct','blocklog','inodelog','inopblog','agblklog','dirblklog','logsectlog','rextslog']:
        for v in [0,1,8,9,10,11,12,16,17,30,31,32,63,64,100,101,255]:m(f'byte_{field}_{v}',**{field:v})
    for field in ['blocksize','inodesize','inopblock','logsectsize']:
        width=FIELDS[field][1]
        for v in [0,1,255,256,511,512,1023,1024,2048,4096,65535]:m(f'scalar_{field}_{v}',**{field:v})
    for il in [8,9,10,11]:m(f'paired_inode{il}',inodesize=1<<il,inodelog=il,inopblock=4096//(1<<il),inopblog=12-il,inoalignmt=64*(1<<il)//4096,spino_align=0)
    for field in ['agblocks','agcount','dblocks']:
        for v in [0,1,63,64,4095,4096,32767,32768,32769,98304,98305,98367,98368,131071,131072,131073,0xffffffff]:m(f'count_{field}_{v}',**{field:v})
    for tail in [0,1,63,64,32767,32768,32769]:m(f'tail_{tail}',dblocks=3*32768+tail)
    for B,bl in [(1024,10),(4096,12),(65536,16)]:
        for A in [2**24//B-1,2**24//B,2**40//B,2**40//B+1]:
            m(f'AGlimit_B{B}_A{A}',blocksize=B,blocklog=bl,inopblock=B//512,inopblog=bl-9,agblocks=A,agblklog=(A-1).bit_length(),dblocks=A*4,inoalignmt=32768//B,spino_align=0,rextsize=max(1,4096//B),logblocks=64,logstart=(2<<((A-1).bit_length()))+7)
    for D in [MAX,MAX-1,(2**32)*32768,(2**32-1)*32768+1,(2**32-1)*32768]:m(f'quotient_D{D}',dblocks=D,agcount=0xffffffff)
    for A in [268435456,268435455]:
        for N in [16777216,16777217,4294967295]:m(f'byte_overflow_A{A}_N{N}',agblocks=A,agblklog=(A-1).bit_length(),agcount=N,dblocks=A*N)
    m('last_representable_4096_byte_count',agblocks=268435456,agblklog=28,agcount=16777216,dblocks=(1<<52)-1)
    m('first_unrepresentable_4096_byte_count',agblocks=268435456,agblklog=28,agcount=16777216,dblocks=1<<52)
    m('required_overflow_witness',agblocks=268435456,agblklog=28,agcount=4294967295,dblocks=1152921504338411520)
    for field in ['rblocks','rextents','rbmblocks','frextents','qflags','unit','width','logsunit','rextsize','inoalignmt','spino_align']:
        bits=FIELDS[field][1]*8
        for v in [0,1,2,3,4,7,8,9,63,64,4095,4096,min((1<<bits)-1,262144),min((1<<bits)-1,262145),(1<<bits)-1]:m(f'geometry_{field}_{v}',**{field:v})
    m('no_spinodes',incompat=0x29,spino_align=0)
    m('no_spinodes_arbitrary_inoalign',incompat=0x29,spino_align=0,inoalignmt=0xffffffff)
    for v in [0,1,128,129,130,MAX]:m(f'ignored_rt_inodes{v}',rbmino=v,rsumino=v)
    for A,D in [(32768,131072),(30000,120000),(32768,98368),(30000,90064)]:
        lg=(A-1).bit_length();tail=D-3*A
        for g in [0,2,3,4,0xffffffff,1<<32]:
            for a in [0,1,7,tail-1,tail,A-1,A,(1<<lg)-1]:
                F=(g<<lg)+a
                if F>MAX:continue
                for L in [1,64,16384]:
                    add(f'log_A{A}_D{D}_g{g}_a{a}_L{L}',mutate(data,agblocks=A,dblocks=D,agblklog=lg,logstart=F,logblocks=L))
    for bl in range(10,17):
        B=1<<bl; A=(1<<24)//B; lg=(A-1).bit_length()
        for a in [0,1,2,3]:
            m(f'header_sector_B{B}_a{a}',blocksize=B,blocklog=bl,inopblock=B//512,inopblog=bl-9,agblocks=A,agblklog=lg,dblocks=A*4,logstart=(2<<lg)+a,logblocks=1,inoalignmt=32768//B,spino_align=0,rextsize=max(1,4096//B))
    for size in [0,1,256,512,513,1024,4096,65535]:
        for lg in [0,8,9,10,12,15,16,63,64,255]:
            m(f'log_sector_present_{size}_{lg}',versionnum=0xbca5,logsectsize=size,logsectlog=lg)
    huge=dict(agblocks=268435456,agblklog=28,agcount=4294967295,dblocks=1152921504338411520)
    m('overflow_before_rt',**huge,rextents=1)
    m('overflow_before_log',**huge,logblocks=0)
    m('overflow_before_misc',**huge,imax_pct=255)
    m('needsrepair_before_overflow',**huge,incompat=0x3b)
    m('logstart_max',logstart=MAX)
    for v in [0,1,2,511,512,16384,32761,32762,521728,521729,1048576,1048577,0xffffffff]:m(f'loglength_{v}',logblocks=v)
    for v in [521727,521728,521729]:m(f'log_byte_cap_{v}',agblocks=1048576,agblklog=20,dblocks=4194304,logstart=(2<<20)+7,logblocks=v)
    # Pair faults: first-error ordering is explicit, every failure still emits all masks.
    faults=[('legacy_required',dict(versionnum=0xb425)),('legacy_excluded',dict(versionnum=0xb4b5)),('features2_required',dict(features2=0x188)),('features2_excluded',dict(features2=0x38a)),('needs_repair',dict(incompat=0x3b)),('extended',dict(compat=0x80000000)),('mirror',dict(bad_features2=0)),('inprogress',dict(inprogress=1)),('realtime',dict(rblocks=1)),('external',dict(logstart=0)),('stripe',dict(logsunit=2)),('quota',dict(qflags=1)),('block',dict(blocksize=0)),('inode',dict(inodesize=0)),('directory',dict(dirblklog=255)),('ag',dict(agblocks=0)),('misc',dict(imax_pct=255)),('rt_zero',dict(rextents=1)),('alignment',dict(inoalignmt=0)),('log',dict(logblocks=0))]
    for i,(an,a) in enumerate(faults):
        for bn,b in faults[i+1:]:
            if a.keys().isdisjoint(b.keys()):m(f'precedence_{an}_{bn}',**dict(a,**b))
    # Deterministic random field patterns, each repaired and unrepaired pair.
    rng=random.Random(seed)
    for i in range(160):
        fs={}
        for key in rng.sample(list(FIELDS),rng.randint(1,6)):
            n=FIELDS[key][1];fs[key]=rng.randrange(1<<(8*n))
        add(f'random_fields_{i}',mutate(data,**fs));add(f'random_fields_unrepaired_{i}',mutate(data,repair=False,**fs))
    # Distinct bytes are deduped for native counting. All descriptive aliases remain.
    uniq={}
    for name,b in cases:uniq.setdefault(b,[]).append(name)
    return [(names[0],b,names) for b,names in uniq.items()]
if __name__=='__main__':
    import sys,collections
    cs=build(fixture(sys.argv[1]));count=collections.Counter((inspect(d)['status'],inspect(d)['issue']) for _,d,_ in cs)
    print('unique inputs',len(cs));print(json.dumps({str(k):v for k,v in count.items()},indent=2))
