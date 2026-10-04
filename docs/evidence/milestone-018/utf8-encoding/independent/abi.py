#!/usr/bin/env python3
import json,sys
from review import HERE,ROOT,PIN,COMPILERS,command,digest,require
VALUES=(0,0x7f,0x80,0x800,0x10000,0x10ffff)
def run(mode):
 path,pin=COMPILERS[mode];require(digest(path)==pin,'compiler pin');require(digest(ROOT/'library/std/utf8.au')==PIN,'library pin')
 out=HERE/('abi-'+mode);out.mkdir();source='module mixed_abi_review;import std.utf8;import std.array;\n'
 params=','.join(f'std::Utf8EncodeResult p{i}' for i in range(6))
 for i in range(6):source+=f'auto select{i}({params})->std::Utf8EncodeResult{{return p{i};}}\n'
 source+='auto test()->u64{\n'
 for i,v in enumerate(VALUES):source+=f'const std::Utf8EncodeResult p{i}=std::encode_utf8({v}u64);\n'
 for i,v in enumerate(VALUES):
  b=chr(v).encode();source+=f'const std::Utf8EncodeResult r{i}=select{i}(p0,p1,p2,p3,p4,p5);\n'
  source+=f'if(r{i}.size()!={len(b)}){{return {100+i}u64;}}\n'
  for j in range(4):
   expected=b[j] if j<len(b) else 253
   source+=f'if(r{i}.byte_or({j},253u8)!={expected}u8){{return {200+i*4+j}u64;}}\n'
 source+='std::array<u8,4> input=std::array<u8,4>();input.set(0,65u8);input.set(1,66u8);input.set(2,67u8);input.set(3,68u8);\n'
 source+='const std::Utf8EncodeResult snapshot=std::Utf8EncodeResult(std::Utf8EncodeStatus::success,input,i64(input.set(0,3u8)));\n'
 source+='if(input.at(0)!=3u8){return 301u64;}if(snapshot.size()!=3){return 302u64;}\n'
 for i,v in enumerate((65,66,67,253)):source+=f'if(snapshot.byte_or({i},253u8)!={v}u8){{return {303+i}u64;}}\n'
 source+='const std::array<u8,4> copied=snapshot.bytes_or_zero();if(copied.at(3)!=0u8){return 307u64;}return 42u64;}\n'
 (out/'input.au').write_text(source)
 command([path,'--module-root',ROOT/'library',out/'input.au','-o',out/'compiled.s'],out,'compile',compiler=True,instrumented=mode=='instrumented')
 (out/'entry.s').write_text('.text\n.globl _start\n_start:\n call test\n push %rax\n mov $1,%rax\n mov $1,%rdi\n mov %rsp,%rsi\n mov $8,%rdx\n syscall\n mov $60,%rax\n xor %rdi,%rdi\n syscall\n.section .note.GNU-stack,"",@progbits\n')
 command(['as','--64',out/'compiled.s','-o',out/'program.o'],out,'assemble');command(['as','--64',out/'entry.s','-o',out/'entry.o'],out,'entry')
 command(['ld','-o',out/'native',out/'entry.o',out/'program.o'],out,'link')
 result=command([out/'native'],out,'native');require(result==(42).to_bytes(8,'little'),f'ABI fixture failed: {result.hex()}')
 manifest={'compiler_sha256':pin,'library_sha256':PIN,'fixture_sha256':digest(out/'input.au'),'assembly_sha256':digest(out/'compiled.s'),'native_sha256':digest(out/'native'),'native_fixtures':1,'distinct_report_argument_returns':6,'late_scalar_argument_snapshot':1,'source_bytes':len(source.encode())}
 (out/'results.json').write_text(json.dumps(manifest,indent=2)+'\n');print('PASS',mode,'six distinct report arguments and late scalar-argument mutation snapshot',flush=True)
if __name__=='__main__':run(sys.argv[1])
