from pathlib import Path
import hashlib,sys,tempfile
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tests/compiler'))
from storage_binary import Suite,xfs_check,crc_call,crc32c_reference,owned_bytes,unchanged
p=ROOT/'fixtures/xfs-offline/superblock-v5-512.bin';data=p.read_bytes()
if len(data)!=512 or hashlib.sha256(data).hexdigest()!='55ad821909c312048d9936a74c8904cd25f97aa190b48ae0004b03eaffdc6586':raise RuntimeError('fixture identity')
zeroed=data[:224]+bytes(4)+data[228:]
if int.from_bytes(data[224:228],'little')!=crc32c_reference(zeroed) or crc32c_reference(zeroed)!=0xb67113c7:raise RuntimeError('CRC reference')
with tempfile.TemporaryDirectory(prefix='aurora-review-real-xfs-') as tmp:
 s=Suite(Path(tmp),sys.argv[1],15,False)
 xfs_check(s,'real mkfs header/all raw facts/input preservation',data,'header_integrity_valid')
 for endian,expected in [('le',0xb67113c7),('be',0xc71371b6)]:
  body=owned_bytes(data)+f'const std::ByteReadResult r=std::read_{endian}32(view,224);'+unchanged()+'return r.value_or(0u64);'
  s.check('real fixture',endian+' stored checksum interpretation',body,expected,imports=('std.binary',))
 crc_call(s,'real full sector with zeroed checksum field',zeroed,0,512)
 for offset,status in [(0,'unrecognized'),(100,'unsupported_profile'),(121,'unsupported_profile'),(224,'checksum_mismatch'),(300,'checksum_mismatch'),(511,'checksum_mismatch')]:
  b=bytearray(data);b[offset]^=1 if offset!=100 else 0x0 # low nibble version lives in second byte
  if offset==100:b[101]=(b[101]&0xf0)|4
  xfs_check(s,'real fixture corrupted byte '+str(offset),b,status)
 for kind in ['unknown features','zero geometry']:
  b=bytearray(data)
  if kind=='unknown features':
   for off in [208,212,216,220]:b[off:off+4]=bytes([255])*4
  else:b[4:16]=bytes(12)
  b[224:228]=bytes(4);b[224:228]=crc32c_reference(b).to_bytes(4,'little')
  xfs_check(s,'rechecksummed '+kind+' does not establish mountability',b,'header_integrity_valid')
 print('PASS real offline fixture',sum(s.counts.values()),'native cases; no image mount or modification')
