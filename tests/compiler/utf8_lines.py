#!/usr/bin/env python3
"""Bounded native UTF-8 consumed-line gate; independent strict Python oracle.

The existing range gate contributes only resource-limited command execution and
output budgeting. No range oracle or implementation is used for line expectations.
"""
from __future__ import annotations
import argparse, hashlib, itertools, json, pathlib, random, sys
sys.dont_write_bytecode = True
import utf8_range as harness
require = harness.require
MIN, MAX, PIN = harness.MIN, harness.MAX, harness.PIN
STATUSES = ('success', 'end_of_input', 'out_of_range', 'invalid_sequence', 'truncated')
ENDINGS = ('none', 'lf', 'crlf')


def model(data, offset, count):
    if offset < 0 or count < 0 or offset > len(data) or count > len(data)-offset:
        return (2, 0, 0, 0)
    if count == 0:
        return (1, 0, 0, 0)
    window = bytes(data[offset:offset+count])
    before, found, after = window.partition(b'\n')
    consumed = before + found
    try:
        consumed.decode('utf-8', 'strict')
    except UnicodeDecodeError as error:
        return (4 if error.reason == 'unexpected end of data' else 3, 0, 0, 0)
    ending = 2 if found and before.endswith(b'\r') else 1 if found else 0
    return (0, len(consumed)-ending, len(consumed), ending)


def cases():
    seeds = (b'', b'A', b'\n', b'\r', b'\r\n', b'A\n', b'A\r\n', b'A\r',
             b'\n\n', b'\r\r\n', b'A\n\xff', b'A\r\n\xe2', b'\n\xff',
             b'\0\x1b\xef\xbb\xbf\n', b'\xc2\x85\xe2\x80\xa8\xe2\x80\xa9',
             b'A\xc2\xa2\r\nB\xe2\x82\xac\n\xf0\x9f\x99\x82')
    for data in seeds:
        owner = b'\xff' + data + b'\xff'
        for offset in range(len(data)+1):
            for count in range(len(data)-offset+1):
                yield ('all seed byte windows', owner, 1+offset, count)
    for byte in range(256):
        for ending in (b'', b'\n', b'\r\n'):
            raw = bytes((byte,)) + ending
            yield ('every byte before final/LF/CRLF', raw, 0, len(raw))
    # Incomplete leading sequences followed by a delimiter must be invalid,
    # never accepted by treating LF as an independent boundary before validation.
    bad = (b'\xc0', b'\xc1', b'\xc2', b'\xdf', b'\xe0', b'\xe0\xa0', b'\xe0\x9f',
           b'\xed\xa0', b'\xed\x9f', b'\xe1\x80', b'\xf0\x90', b'\xf0\x90\x80',
           b'\xf4\x8f\xbf', b'\xf4\x90', b'\xf5', b'\x80', b'\xff')
    for fragment, prefix, suffix in itertools.product(bad, (b'', b'Z', b'\xe2\x82\xac'), (b'', b'\n', b'\r\n')):
        raw = prefix + fragment + suffix
        yield ('malformed or incomplete first line', raw, 0, len(raw))
        if suffix:
            raw = b'valid'+suffix+fragment
            yield ('unconsumed invalid suffix is deferred', raw, 0, len(raw))
    scalars = (0, 27, 0x7f, 0x80, 0x7ff, 0x800, 0xd7ff, 0xe000, 0xffff, 0x10000,
               0x10ffff, 0xfeff, 0xfdd0, 0x0378, 0x0301, 0x200d, 0x2028, 0x2029, 0x85)
    for scalar, suffix in itertools.product(scalars, (b'', b'\n', b'\r\n')):
        raw = chr(scalar).encode()+suffix
        yield ('scalar policies and boundaries', b'\xff'+raw+b'\xff', 1, len(raw))
    for offset, count in itertools.product((MIN, -1, 0, 1, 2, 3, 4, MAX), repeat=2):
        yield ('signed window extremes', b'\xff\nA', offset, count)
    rng = random.Random(20261005)
    for _ in range(128):
        raw = ''.join(chr(rng.choice((*scalars, 10, 13))) for _ in range(rng.randrange(20))).encode()
        yield ('seeded mixed valid sequences', b'\xff'+raw+b'\xff', 1, len(raw))
    for _ in range(128):
        raw = bytes(rng.randrange(256) for _ in range(rng.randrange(16)))
        yield ('seeded arbitrary bytes', raw or b'\xff', 0, len(raw))
    for data in (b'A'*4096, b'A'*4095+b'\n', b'A'*4094+b'\r\n', b'\n'+b'\xff'*4095,
                 b'A'*4092+chr(0x10ffff).encode(), b'A'*4093+b'\xe2\x82\n'):
        yield ('maximum 4096-byte owner', data, 0, len(data))


def observe(report='report'):
    s='if(field==0){'
    for value, status in enumerate(STATUSES):
        s+=f'if({report}.status()==std::Utf8LineStatus::{status}){{return {value};}}'
    s+=f'return -777;}}if(field==1){{return {report}.content_bytes();}}if(field==2){{return {report}.consumed_bytes();}}'
    for value, ending in enumerate(ENDINGS):
        s+=f'if({report}.ending()==std::Utf8LineEnding::{ending}){{return {value};}}'
    return s+'return -778;'


def source_case(item):
    label, data, offset, count = item
    body=harness.array(data)+f'const builtin::array<u8,{max(1,len(data))}> saved=owner;'
    body+=f'const std::Utf8LineResult original=std::read_utf8_line(borrow_bytes(owner),{offset},{count});'
    body+='i64 i=0;while(i<len(owner)){if(owner[i]!=saved[i]){return -779;}i=i+1;}owner[0]=0u8;'
    body+='const std::Utf8LineResult report=original;'+observe()
    return label, body, model(data, offset, count)


def public_reports():
    for status, ending, count in itertools.product(STATUSES, ENDINGS, (MIN,-1,0,1,2,MAX-2,MAX-1,MAX)):
        code=STATUSES.index(status);width=ENDINGS.index(ending)
        if code==0 and (count<0 or count>MAX-width or count+width<=0): code=2
        expected=(code, count if code==0 else 0, count+width if code==0 else 0, width if code==0 else 0)
        body=f'const std::Utf8LineResult report=std::Utf8LineResult(std::Utf8LineStatus::{status},{count},std::Utf8LineEnding::{ending});'+observe()
        yield ('forged report masking and progress invariants', body, expected)


def sequences():
    inputs=(b'',b'\n',b'\n\n',b'A\r\nB\nC',b'A\rB\r\n\r',b'\xe2\x82\xac\n\xf0\x9f\x99\x82',
            b'\0\n\xef\xbb\xbf\r\n\x1b',b'good\n\xff',b'\n\xc2',b'A\nB\r\n\xe2\x82',
            b'\n'*4096)
    for raw in inputs:
        used=lines=content=0;status=1
        while used<len(raw):
            result=model(raw,used,len(raw)-used);status=result[0]
            if status:break
            require(0<result[2]<=len(raw)-used,'oracle progress')
            require(raw[used:used+result[1]].decode('utf-8').encode('utf-8')==raw[used:used+result[1]],'content roundtrip')
            require(raw[used+result[1]:used+result[2]]==(b'',b'\n',b'\r\n')[result[3]],'ending reconstruction')
            used+=result[2];content+=result[1];lines+=1
        if used==len(raw):status=1
        body=harness.array(raw)+f'i64 used=0;i64 lines=0;i64 content=0;i64 status=1;bool stopped=false;while(!stopped){{'
        body+=f'const std::Utf8LineResult line=std::read_utf8_line(borrow_bytes(owner),used,{len(raw)}-used);'
        body+='if(line.status()==std::Utf8LineStatus::success){if(line.consumed_bytes()<=0){return -781;}'
        body+=f'if(line.consumed_bytes()>{len(raw)}-used){{return -782;}}'
        body+='if(line.ending()==std::Utf8LineEnding::lf){if(owner[used+line.content_bytes()]!=10u8){return -783;}}'
        body+='if(line.ending()==std::Utf8LineEnding::crlf){if(owner[used+line.content_bytes()]!=13u8){return -784;}if(owner[used+line.content_bytes()+1]!=10u8){return -785;}}'
        body+='content=content+line.content_bytes();used=used+line.consumed_bytes();lines=lines+1;}else{'
        for number, name in enumerate(STATUSES[1:],1):body+=f'if(line.status()==std::Utf8LineStatus::{name}){{status={number};}}'
        body+='if(line.content_bytes()!=0){return -786;}if(line.consumed_bytes()!=0){return -787;}if(line.ending()!=std::Utf8LineEnding::none){return -788;}stopped=true;}}'
        body+='if(field==0){return status;}if(field==1){return lines;}if(field==2){return content;}return used;'
        yield ('repeated scanning/progress/reconstruction',body,(status,lines,content,used))


def rejections():
    head='module rejection;import std.utf8_lines;'
    for field in ('outcome','content_length','terminator'):
        yield ('private '+field,head+'auto test()->i64{const std::Utf8LineResult r=std::Utf8LineResult(std::Utf8LineStatus::success,1,std::Utf8LineEnding::none);return r.'+field+';}','private')
    yield ('live readonly owner',head+'auto test()->i64{builtin::array<u8,1> b={65u8};const builtin::span<const u8> v=borrow_bytes(b);b[0]=66u8;const std::Utf8LineResult r=std::read_utf8_line(v,0,1);return r.content_bytes();}','span is live')
    yield ('wrong window type',head+'auto test()->i64{const builtin::array<u8,1> b={65u8};const std::Utf8LineResult r=std::read_utf8_line(borrow_bytes(b),0u64,1);return r.content_bytes();}','expected i64, got u64')
    yield ('private checked helper',head+'auto test()->i64{const builtin::array<u8,1> b={65u8};const std::Utf8LineResult r=std::utf8_line_checked(borrow_bytes(b),0,1,std::Utf8LineEnding::none);return r.content_bytes();}',"private function is not imported: std::utf8_line_checked")
    yield ('unimported decoder',head+'auto test()->i64{const builtin::array<u8,1> b={65u8};const std::Utf8ValidationResult r=std::validate_utf8(borrow_bytes(b),0,1,true);return r.scalar_count();}',"unknown function 'std::validate_utf8'")


class Suite(harness.Suite):
    def __init__(self,args):
        super().__init__(args)
        self.inputs[str(pathlib.Path(__file__).resolve())]=harness.sha(__file__)

    def batch(self,items):
        self.budget();d=self.output/f'batch-{self.batches:04d}';d.mkdir();self.batches+=1
        source='module utf8_lines_test;import std.utf8_lines;\n'
        for i,(_,body,_) in enumerate(items):source+=f'auto line_case_{i}(i64 field)->i64{{{body}}}\n'
        require(len(source.encode())<=65536,'source size cap');(d/'input.au').write_text(source)
        wanted=[v for _,_,values in items for v in values]
        receipt=dict(labels=[x[0] for x in items],expected=wanted,source_sha256=harness.sha(d/'input.au'),status='running')
        try:
            self.command([self.compiler,'--module-root',self.root/'library',d/'input.au','-o',d/'compiled.s'],d,'compiler')
            entry=['.text','.globl _start','_start:']
            for i in range(len(items)):
                for field in range(4):entry += [f'movq ${field},%rdi',f'call line_case_{i}','pushq %rax','movq $1,%rax','movq $1,%rdi','movq %rsp,%rsi','movq $8,%rdx','syscall','addq $8,%rsp']
            entry+=['movq $60,%rax','xorq %rdi,%rdi','syscall','.section .note.GNU-stack,"",@progbits']
            (d/'entry.s').write_text('\n'.join(entry)+'\n')
            self.command(['as','--64',d/'compiled.s','-o',d/'program.o'],d,'assemble')
            self.command(['as','--64',d/'entry.s','-o',d/'entry.o'],d,'entry')
            self.command(['ld','-o',d/'program',d/'entry.o',d/'program.o'],d,'link')
            output=self.command([d/'program'],d,'native')
            require(len(output)==8*len(wanted),'exact full observation length')
            observed=[int.from_bytes(output[i:i+8],'little',signed=True) for i in range(0,len(output),8)]
            receipt.update(observed=observed,output_sha256=hashlib.sha256(output).hexdigest())
            require(observed==wanted,f'native mismatch {[(i,a,b) for i,(a,b) in enumerate(zip(observed,wanted)) if a!=b][:8]}')
            self.count+=len(items);receipt['status']='passed'
        except Exception as error:receipt.update(status='failed',error=str(error));raise
        finally:(d/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
        print(f'PASS line batch {self.batches}: {len(items)} cases; {len(wanted)} full i64 observations',flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--compiler',required=True,type=pathlib.Path)
    p.add_argument('--compiler-sha256',default=PIN)
    p.add_argument('--repo-root',type=pathlib.Path,default=pathlib.Path(__file__).resolve().parents[2])
    p.add_argument('--artifacts',required=True,type=pathlib.Path)
    p.add_argument('--budget-root',type=pathlib.Path)
    p.add_argument('--budget-mib',type=int,default=128)
    p.add_argument('--sanitized-compiler',action='store_true')
    a=p.parse_args()
    require(model(b'A\r\n\xff',0,4)==(0,1,3,2),'deferred suffix oracle')
    require(model(b'\xc2\n',0,2)==(3,0,0,0),'lead before LF oracle')
    require(model(b'\xc2',0,1)==(4,0,0,0),'final truncation oracle')
    require(model(b'\r',0,1)==(0,1,1,0),'lone CR oracle')
    require(model(b'A',1,0)==(1,0,0,0),'EOF oracle')
    suite=Suite(a);manifest=dict(compiler_sha256=suite.pin,inputs=suite.inputs,python=sys.version,optimized=not __debug__,status='running')
    try:
        batch=[]
        for item in itertools.chain(map(source_case,cases()),public_reports(),sequences()):
            if batch and (len(batch)>=16 or sum(len(x[1]) for x in batch)+len(item[1])>62000):suite.batch(batch);batch=[]
            batch.append(item)
        if batch:suite.batch(batch)
        for item in rejections():suite.reject(*item)
        suite.verify_inputs();manifest.update(status='passed',cases=suite.count,full_i64_observations=4*suite.count,batches=suite.batches,rejections=suite.rejections)
        print(f'PASS UTF-8 lines: {suite.count} cases; {4*suite.count} full i64 observations; {suite.rejections} rejection controls',flush=True)
    except Exception as error:manifest.update(status='failed',error=str(error));raise
    finally:
        manifest.update(completed_cases=suite.count,completed_rejections=suite.rejections,allocated_bytes=suite.budget(0))
        (suite.output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')

if __name__=='__main__':main()
