"""Independently authored Python bigint model of PROPOSAL.md's bounded facts.
No Aurora implementation or author's test oracle is imported. All arithmetic is
unbounded first and representability is checked separately. CRC is whole-message
GF(2) division, not the implementation recurrence. Synthetic bytes are not images.
"""
from pathlib import Path
import hashlib, json, re
MAX=(1<<64)-1
MASK=(1<<32)-1
STATUS=['probe_rejected','unsupported_feature_profile','unsupported_layout','offline_state_indicated','inconsistent_header','size_unrepresentable','header_geometry_consistent']
ISSUE=['none','legacy_required_bits','legacy_excluded_bits','features2_required_bits','features2_excluded_bits','extended_feature_masks','features2_mirror','needs_repair','offline_operation','realtime','external_log','striping','quota_or_misc_flags','block_geometry','inode_geometry','directory_geometry','ag_geometry','data_byte_size','realtime_zero_geometry','inode_alignment','log_geometry','misc_geometry']
PROBE=['wrong_length','unrecognized','unsupported_profile','checksum_mismatch','header_integrity_valid']
FIELDS={'blocksize':(4,4),'dblocks':(8,8),'rblocks':(16,8),'rextents':(24,8),'logstart':(48,8),'rootino':(56,8),'rbmino':(64,8),'rsumino':(72,8),'rextsize':(80,4),'agblocks':(84,4),'agcount':(88,4),'rbmblocks':(92,4),'logblocks':(96,4),'versionnum':(100,2),'sectsize':(102,2),'inodesize':(104,2),'inopblock':(106,2),'blocklog':(120,1),'sectlog':(121,1),'inodelog':(122,1),'inopblog':(123,1),'agblklog':(124,1),'rextslog':(125,1),'inprogress':(126,1),'imax_pct':(127,1),'frextents':(152,8),'qflags':(176,2),'flags':(178,1),'shared_vn':(179,1),'inoalignmt':(180,4),'unit':(184,4),'width':(188,4),'dirblklog':(192,1),'logsectlog':(193,1),'logsectsize':(194,2),'logsunit':(196,4),'features2':(200,4),'bad_features2':(204,4),'compat':(208,4),'ro_compat':(212,4),'incompat':(216,4),'log_incompat':(220,4),'spino_align':(228,4)}
FACT_GROUPS={'blocks':['block_bytes','sector_bytes','block_log','sector_log','directory_block_bytes','effective_log_sector_bytes'],'inodes':['inode_bytes','inodes_per_block','inode_log','inodes_per_block_log'],'data':['data_blocks','claimed_data_bytes','claimed_data_sectors'],'ags':['ag_block_log','ag_blocks','ag_count','ag_bytes','last_ag_blocks','last_ag_start_bytes'],'log':['log_start_encoded','log_ag','log_ag_block','log_start_bytes','log_bytes']}
FACTS=sum(FACT_GROUPS.values(),[])
def require(c,s):
    if not c: raise AssertionError(s)
def reflect(x,n): return int(f'{x:0{n}b}'[::-1],2)
def crc(data):
    reflected=bytes(reflect(x,8) for x in data)
    rem=(MASK << (8*len(data))) ^ (int.from_bytes(reflected,'big')<<32)
    while rem.bit_length()>32: rem ^= 0x11edc6f41 << (rem.bit_length()-33)
    return reflect(rem,32)^MASK
def repaired(data):
    d=bytearray(data); d[224:228]=bytes(4); d[224:228]=crc(d).to_bytes(4,'little'); return bytes(d)
def mutate(data,repair=True,**fields):
    d=bytearray(data)
    for name,value in fields.items():
        p,n=FIELDS[name]; d[p:p+n]=value.to_bytes(n,'big')
    return repaired(d) if repair else bytes(d)
def fixture(path):
    with Path(path).open('rb') as f: raw=f.read(1729)
    require(len(raw)==1728,'transport length')
    rows=raw.splitlines(keepends=True); require(len(rows)==32,'transport rows')
    for i,row in enumerate(rows):
        require(re.fullmatch(rb'[0-9a-f]{4}  (?:[0-9a-f]{2} ){15}[0-9a-f]{2}\n',row) is not None,'transport canonical form')
        require(int(row[:4],16)==16*i,'transport offsets')
    data=bytes(int(v,16) for row in rows for v in row[6:-1].split())
    require(hashlib.sha256(raw).hexdigest()=='d1d3fbc3f8b693d1c0ddf395e92b136a81b2a5d30b9e3cdec36addd580d42986','transport hash')
    require(hashlib.sha256(data).hexdigest()=='55ad821909c312048d9936a74c8904cd25f97aa190b48ae0004b03eaffdc6586','fixture hash')
    require(repaired(data)==data,'CRC fixture'); return data

def inspect(data):
    result={'status':'probe_rejected','issue':'none','probe':['wrong_length',0,0,0,0],'raw':[0,0,0],'unsupported':[0]*4,'unknown':[0]*4,'facts':{x:0 for x in FACTS}}
    def reject(status,issue): result.update(status=status,issue=issue); return result
    if len(data)!=512:return result
    if data[:4]!=b'XFSB':result['probe'][0]='unrecognized';return result
    f={k:int.from_bytes(data[p:p+n],'big') for k,(p,n) in FIELDS.items()}
    masks=[f[x] for x in ['compat','ro_compat','incompat','log_incompat']]
    result['probe']=['unsupported_profile',*masks]
    if f['versionnum']&15!=5 or f['sectsize']!=512 or f['sectlog']!=9:return result
    result['probe'][0]='checksum_mismatch'
    if repaired(data)!=data:return result
    result['probe'][0]='header_integrity_valid'
    result['raw']=[f['versionnum'],f['features2'],f['bad_features2']]
    result['unsupported']=[v & (MASK^a) for v,a in zip(masks,[0,15,43,0])]
    result['unknown']=[v & (MASK^a) for v,a in zip(masks,[0,15,2047,1])]
    # Parent-confirmed order: required groups, excluded groups; misc is last.
    if f['versionnum']&0xb4a0 !=0xb4a0:return reject('inconsistent_header','legacy_required_bits')
    if f['features2']&0x18a !=0x18a:return reject('inconsistent_header','features2_required_bits')
    if f['versionnum'] & (0xffff ^ 0xbca5):return reject('unsupported_feature_profile','legacy_excluded_bits')
    if f['features2'] & (MASK ^ 0x18a):return reject('unsupported_feature_profile','features2_excluded_bits')
    if f['incompat']&16:return reject('offline_state_indicated','needs_repair')
    if any(result['unsupported']) or not f['incompat']&1:return reject('unsupported_feature_profile','extended_feature_masks')
    if f['features2']!=f['bad_features2']:return reject('unsupported_layout','features2_mirror')
    if f['inprogress']:return reject('offline_state_indicated','offline_operation')
    if f['rblocks']:return reject('unsupported_layout','realtime')
    if not f['logstart']:return reject('unsupported_layout','external_log')
    if f['unit'] or f['width'] or f['logsunit']>1:return reject('unsupported_layout','striping')
    if f['qflags'] or f['flags']:return reject('unsupported_layout','quota_or_misc_flags')
    B=f['blocksize']; bl=f['blocklog']; I=f['inodesize']; il=f['inodelog']
    if not 10<=bl<=16 or B!=2**bl or B<512:return reject('inconsistent_header','block_geometry')
    if not 8<=il<=11 or I!=2**il:return reject('inconsistent_header','inode_geometry')
    if I==256:return reject('unsupported_layout','inode_geometry')
    if I>B or f['inopblock']!=B//I or f['inopblog']!=bl-il:return reject('inconsistent_header','inode_geometry')
    if bl+f['dirblklog']>16:return reject('inconsistent_header','directory_geometry')
    A=f['agblocks']; N=f['agcount']; D=f['dblocks']
    if not A or not N or not D:return reject('inconsistent_header','ag_geometry')
    expected=(D+A-1)//A # deliberately bigint direct ceiling, unlike implementation
    tail=D-(N-1)*A
    if not 2**24<=A*B<=2**40 or f['agblklog']!=(A-1).bit_length() or N!=expected or not 64<=tail<=A:return reject('inconsistent_header','ag_geometry')
    if D*B>MAX:return reject('size_unrepresentable','data_byte_size')
    if any(f[x] for x in ['rextents','rbmblocks','rextslog','frextents']) or not 4096<=f['rextsize']*B<=1073741824:return reject('inconsistent_header','realtime_zero_geometry')
    align=f['inoalignmt']; sparse=f['spino_align']
    if f['incompat']&2:
        if align!=64*I//B or (sparse and (sparse>align or align%sparse)):return reject('inconsistent_header','inode_alignment')
    elif sparse:return reject('inconsistent_header','inode_alignment')
    ls=(f['logsectsize'],f['logsectlog'])
    if f['versionnum']&0x800:
        if ls!=(512,9):return reject('unsupported_layout','log_geometry')
    elif ls!=(0,0):return reject('inconsistent_header','log_geometry')
    L=f['logblocks']; F=f['logstart']; g,a=divmod(F,2**f['agblklog']); actual=tail if g==N-1 else A
    if not 1<=L<=1048576 or L*B>2136997888 or g>=N or a<=1536//B or a>=actual or a+L>actual:return reject('inconsistent_header','log_geometry')
    linear=g*A+a
    require(linear+L<=D,'oracle implication log fits D')
    vals=[B,512,bl,9,B*2**f['dirblklog'],512,I,B//I,il,bl-il,D,D*B,D*B//512,f['agblklog'],A,N,A*B,tail,(N-1)*A*B,F,g,a,linear*B,L*B]
    if f['imax_pct']>100 or f['shared_vn']:return reject('inconsistent_header','misc_geometry')
    result['facts']=dict(zip(FACTS,vals));return reject('header_geometry_consistent','none')

def flattened(r):return [STATUS.index(r['status']),ISSUE.index(r['issue']),PROBE.index(r['probe'][0]),*r['probe'][1:],*r['raw'],*r['unsupported'],*r['unknown'],*r['facts'].values()]

if __name__=='__main__':
    import sys
    d=fixture(sys.argv[1]);print(json.dumps(inspect(d),indent=2))
    require(crc(b'123456789')==0xe3069283,'CRC known answer')
    require(inspect(d)['facts']['log_start_bytes']==268464128,'baseline log')
    require(inspect(mutate(d,agblocks=30000,dblocks=120000))['facts']['log_start_bytes']==245788672,'nonpower address')
    require(inspect(mutate(d,agblocks=268435456,agblklog=28,agcount=4294967295,dblocks=1152921504338411520))['status']=='size_unrepresentable','overflow witness')
