from pathlib import Path
import sys,tempfile,random
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tests/compiler'))
from storage_binary import Suite,MAX_U64,crc32c_reference,xfs_check,crc_call,array
with tempfile.TemporaryDirectory(prefix='aurora-review-storage-extra-') as tmp:
 s=Suite(Path(tmp),sys.argv[1],15,False)
 def seal(b):
  b=bytearray(b);b[224:228]=bytes(4);b[224:228]=crc32c_reference(b).to_bytes(4,'little');return b
 h=bytearray(512);h[:4]=b'XFSB';h[100:102]=(0xfff5).to_bytes(2,'big');h[102:104]=(512).to_bytes(2,'big');h[121]=9
 # Deliberately invalid filesystem geometry is still only a valid header CRC fact.
 xfs_check(s,'zero geometry with matching narrow profile',seal(h),'header_integrity_valid')
 for bit in range(32):
  b=bytearray(h)
  for j,off in enumerate((208,212,216,220)):b[off:off+4]=(1<<((bit+j*7)%32)).to_bytes(4,'big')
  xfs_check(s,'unknown/raw feature one-hot matrix '+str(bit),seal(b),'header_integrity_valid')
 b=bytearray(h)
 for off in (208,212,216,220):b[off:off+4]=(0xffffffff).to_bytes(4,'big')
 b=seal(b)
 xfs_check(s,'all feature bits remain diagnostic only',b,'header_integrity_valid')
 for off in (8,120,126,192,232,263,264,319,320,400,510,511):
  damaged=bytearray(b);damaged[off]^=128
  xfs_check(s,'full-sector CRC byte '+str(off),damaged,'checksum_mismatch')
 rng=random.Random(39061)
 for i in range(16):
  values=[rng.randrange(256) for _ in range(1+i*3)]
  crc_call(s,'arbitrary finalized continuation '+str(i),values,0,len(values),rng.randrange(1<<32))
 body='const std::ChecksumResult fake=std::ChecksumResult(std::ChecksumStatus::success,18446744073709551615u64);'+array('bytes',[42])+ 'const std::ChecksumResult r=std::crc32c_extend(fake.value_or(0u64),borrow_bytes(bytes),-1,9223372036854775807);if(r.status()!=std::ChecksumStatus::invalid_previous){return 1u64;}return r.value_or(18446744073709551615u64);'
 s.check('reports','forged success cannot bypass continuation prior check',body,imports=('std.checksum',))
 body='const fs::XfsProbeResult fake=fs::XfsProbeResult(fs::XfsProbeStatus::header_integrity_valid,18446744073709551615u64,0u64,0u64,0u64);return fake.features_compat();'
 s.check('reports','public report constructor is not parsing authority',body,imports=('fs.xfs_probe',))
 print('PASS extra storage',sum(s.counts.values()),'native cases',dict(s.counts))
