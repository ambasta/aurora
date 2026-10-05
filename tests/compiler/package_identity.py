#!/usr/bin/env python3
"""Independent bounded regex/integer oracle for native package.identity.

Run: python3 tests/compiler/package_identity.py build/aurorac --artifact-root evidence/package-identity/oracle-run
Every observation is a complete little-endian u64 emitted by freestanding x86-64
GNU as/ld code, without target libc. Success scratch products are removed only
after a receipt is committed; failing products and all sources are preserved.
No implementation parser, existing parser oracle, IR, kernel or network is used.
"""
from __future__ import annotations
import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import random
import re
import resource
import shutil
import subprocess
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
COMPILER_SHA256 = 'e1953ce8446973194a66ba579809c37459466f746f491a53a98b1c910ef4110e'
CONTRACT_SHA256 = '79af6fe35314b1dd17a6f1115c8269754866018e39061c5ad1cba6161634887f'
CAP = 128 << 20
MAX_CAP = 1024 << 20
FLOOR = 1 << 30
SOURCE_CAP = 64 << 10
BATCH = 24
U32 = (1 << 32) - 1
U64 = (1 << 64) - 1
IMIN, IMAX = -(1 << 63), (1 << 63) - 1
FALLBACKS = (U64, 1 << 63, 0xFEDCBA9876543210)
BYTE_FALLBACK = 237
PREFIX = 'module identity_oracle;import package.identity;import std.array;\n'
NAME = re.compile(rb'[a-z][a-z0-9]*(?:-[a-z0-9]+)*')
TOKEN = re.compile(rb'([a-z][a-z0-9]*(?:-[a-z0-9]+)*)@(0|[1-9][0-9]{0,9})\.(0|[1-9][0-9]{0,9})\.(0|[1-9][0-9]{0,9})')


def require(ok, message):
    if not ok:
        raise AssertionError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def artifact_path(value):
    # Reject traversal rather than allowing lexical prefix checks to miss output
    # outside the charged candidate. Reject symlinks before resolving them away.
    raw = Path(value).absolute()
    require('..' not in raw.parts, 'artifact path traversal denied')
    require(not any(p.is_symlink() for p in [raw, *raw.parents]), 'symlink output root denied')
    canonical = raw.resolve(strict=False)
    require(canonical.is_relative_to(ROOT), 'artifacts must stay within the candidate')
    return canonical


def candidate_cap(mib):
    require(type(mib) is int and 128 <= mib <= 1024,
            'candidate cap must be an integer between 128 and 1024 MiB; increases require explicit aggregate admission')
    return mib << 20


def cap_self_test():
    for mib in (128, 512, 513, 1023, 1024):
        require(candidate_cap(mib) == mib << 20, 'candidate cap boundary conversion')
    for mib in (-1, 0, 127, 1025, 1 << 30, True, 512.0, '1024', None):
        try:
            candidate_cap(mib)
        except AssertionError:
            continue
        raise AssertionError('invalid candidate cap accepted')


def signed(value):
    return '(-9223372036854775807-1)' if value == IMIN else str(value)


@dataclass(frozen=True)
class Result:
    status: str
    name: bytes = b''
    version: tuple = (0, 0, 0)

    def values(self):
        success = self.status == 'success'
        name = self.name if success else b''
        def at(index):
            return name[index] if 0 <= index < len(name) else BYTE_FALLBACK
        # 37 observations: normalized status, size, all numeric fields, every
        # owned name byte, signed/index-boundary fallback behavior, copy isolation.
        return (['success', 'malformed', 'out_of_range'].index(self.status) + 1,
                len(name), *(self.version if success else FALLBACKS),
                *name.ljust(24, b'\0'),
                at(0), at(len(name)-1), at(len(name)), at(-1), at(IMIN),
                at(IMAX), at(23), 1)


def parse_oracle(data, offset, count):
    # Python integers are unbounded. This intentionally does not duplicate the
    # implementation's scanning/control flow or arithmetic overflow mechanism.
    if offset < 0 or count < 0 or offset + count > len(data):
        return Result('out_of_range')
    match = TOKEN.fullmatch(data[offset:offset+count])
    if match is None or not 1 <= len(match[1]) <= 24:
        return Result('malformed')
    version = tuple(int(part) for part in match.groups()[1:])
    if max(version) > U32:
        return Result('malformed')
    return Result('success', match[1], version)


def constructor_oracle(status, storage, length, version):
    if status != 'success':
        return Result(status)
    if (not 1 <= length <= 24 or any(storage[length:])
            or NAME.fullmatch(storage[:length]) is None
            or any(not 0 <= value <= U32 for value in version)):
        return Result('malformed')
    return Result('success', storage[:length], version)


@dataclass(frozen=True)
class Case:
    label: str
    body: str
    expected: tuple
    helpers: str = ''


def array(name, data):
    require(1 <= len(data) <= 4096, 'supported input array length')
    return f'array<u8,{len(data)}> {name}={{' + ','.join(f'{x}u8' for x in data) + '};'


def parse_case(label, data, offset=0, count=None):
    if count is None:
        count = len(data)
    # A zero selected window is representable; accepted spans have no empty owner.
    owner = data if data else b'\0'
    expected = parse_oracle(owner, offset, count)
    body = array('owner', owner)
    body += ('const package::IdentityResult parsed=package::parse_identity('
             f'borrow_bytes(owner),{signed(offset)},{signed(count)});'
             'const package::IdentityResult r=parsed;'
             f'i64 index=0;while(index<{len(owner)}){{owner[index]=0u8;index=index+1;}}'
             'return observe(r,slot);')
    return Case(label, body, expected.values())


def constructor_case(label, storage, length, version=(1, 2, 3), status='success'):
    require(len(storage) == 24, 'constructor storage must be exactly 24 bytes')
    expected = constructor_oracle(status, storage, length, version)
    body = 'std::array<u8,24> storage=std::array<u8,24>();'
    for index, value in enumerate(storage):
        if value:
            body += f'storage.set({index},{value}u8);'
    body += (f'const package::IdentityResult r=package::IdentityResult(package::IdentityStatus::{status},'
             f'storage,{signed(length)},' + ','.join(f'{v}u64' for v in version) + ');'
             'i64 index=0;while(index<24){storage.set(index,255u8);index=index+1;}'
             'return observe(r,slot);')
    return Case(label, body, expected.values())


def shared():
    source = '''auto observe(package::IdentityResult r,i64 slot)->u64{
if(slot==0){if(r.status()==package::IdentityStatus::success){return 1u64;}
if(r.status()==package::IdentityStatus::malformed){return 2u64;}
if(r.status()==package::IdentityStatus::out_of_range){return 3u64;}return 999u64;}
if(slot==1){return u64(r.name_size());}
'''
    for slot, (method, fallback) in enumerate(zip(('major_or', 'minor_or', 'patch_or'), FALLBACKS), 2):
        source += f'if(slot=={slot}){{return r.{method}({fallback}u64);}}\n'
    source += ('const std::array<u8,24> bytes=r.name_bytes_or_zero();'
               'if(slot>=5){if(slot<29){return u64(bytes.at(slot-5));}}\n')
    for slot, index in enumerate(('0', 'r.name_size()-1', 'r.name_size()', '-1', signed(IMIN), signed(IMAX), '23'), 29):
        source += f'if(slot=={slot}){{return u64(r.name_byte_or({index},{BYTE_FALLBACK}u8));}}\n'
    source += '''if(slot==36){std::array<u8,24> changed=r.name_bytes_or_zero();
i64 i=0;while(i<24){changed.set(i,255u8);i=i+1;}
const std::array<u8,24> again=r.name_bytes_or_zero();
i64 j=0;while(j<24){if(again.at(j)!=bytes.at(j)){return 0u64;}j=j+1;}return 1u64;}
return 998u64;}\n'''
    return source


def parsing_cases():
    cases = []
    add = lambda label, data, offset=0, count=None: cases.append(parse_case(label, data, offset, count))
    for token in (b'a@0.0.0', b'package-name@1.2.3', b'a1-b2@12.34.56',
                  b'abcdefghijklmnopqrstuvwxyz'[:24]+b'@4294967295.4294967295.4294967295',
                  b'a0-b1-c2-d3-e4-f5-g6-h7-i@0.0.0'):
        add('canonical/'+token.decode(), token)
    for length in range(1, 27):
        add(f'name-length/{length}', b'a'*length+b'@0.0.0')
    for number in (0, 1, 9, 10, 99, 2147483647, 2147483648, U32-1, U32, U32+1, U64, 10**10):
        for component in range(3):
            parts = [b'2', b'3', b'4']; parts[component] = str(number).encode()
            add(f'component/{component}/{number}', b'a@'+b'.'.join(parts))
    bad_names = (b'', b'-', b'0', b'1a', b'A', b'a-', b'a--b', b'-a', b'a_b', b'a.b',
                 b'a/b', b'a b', b'a\0b', 'café'.encode(), b'\xffa')
    for name in bad_names:
        add('invalid-name/'+name.hex(), name+b'@1.2.3')
    for value in (b'', b'00', b'01', b'0000000000', b'00000000000', b'+1', b'-1', b'1e2',
                  b'0x1', b'1_0', b' 1', b'1 ', b'\x001', b'4294967296', b'9999999999'):
        for component in range(3):
            parts = [b'1', b'2', b'3']; parts[component] = value
            add(f'invalid-component/{component}/{value.hex()}', b'a@'+b'.'.join(parts))
    for suffix in (b'\0', b'\n', b'\r', b'\r\n', b' ', b'\t', b'-pre', b'+build', b'.4', b'@1.2.3', b';'):
        add('trailing/'+suffix.hex(), b'a@1.2.3'+suffix)
        add('leading/'+suffix.hex(), suffix+b'a@1.2.3')
    for token in (b'a@0.0.0', b'a1-b2@12.34.56', b'a'*24+b'@4294967295.4294967295.4294967295'):
        for cut in range(len(token)):
            add(f'prefix/{token.hex()}/{cut}', token, 0, cut)
            add(f'suffix/{token.hex()}/{cut}', token, cut+1, len(token)-cut-1)
    # Every byte at every position of this representative token: lowercase name,
    # name digit, internal hyphen, separator @, numeric starts/tails, both dots.
    token = b'a1-b2@12.34.56'
    for position in range(len(token)):
        for value in range(256):
            data = token[:position]+bytes([value])+token[position+1:]
            add(f'all-byte-substitution/{position}/{value}', data)
    maximum = b'a@4294967295.4294967295.4294967295'
    for position in (11, 22, 33):
        for value in range(256):
            add(f'max-component-byte/{position}/{value}', maximum[:position]+bytes([value])+maximum[position+1:])
    owner = b'\xff\0a@1.2.3\n\xff'
    for offset in (IMIN, -57, -1, 0, 1, 2, 3, len(owner)-1, len(owner), len(owner)+1, IMAX):
        for count in (IMIN, -1, 0, 1, 7, 57, len(owner), len(owner)+1, IMAX):
            add(f'window/{offset}/{count}', owner, offset, count)
    add('window/exact-delimited', owner, 2, 7)
    for length in (58, 64, 128, 4096):
        add(f'bounded-long/{length}', b'a'*length)
        add(f'large-owner-small-window/{length}', b'\xff'*(length-7)+b'a@1.2.3', length-7, 7)
    rng = random.Random(220104)
    for index in range(128):
        name = bytes([rng.randrange(97, 123)]) + bytes(rng.choice(b'abcdefghijklmnopqrstuvwxyz0123456789') for _ in range(rng.randrange(24)))
        version = tuple(rng.randrange(1 << 32) for _ in range(3))
        token = name+b'@'+b'.'.join(str(v).encode() for v in version)
        add(f'seed220104-valid/{index}', token)
        bad = bytearray(token); bad[rng.randrange(len(bad))] = rng.randrange(256)
        add(f'seed220104-mutation/{index}', bytes(bad))
    return cases


def construction_cases():
    cases = []
    def add(label, name=b'a', length=None, version=(1, 2, 3), status='success', tail=None):
        length = len(name) if length is None else length
        storage = bytearray(name[:24].ljust(24, b'\0'))
        if tail is not None:
            storage[tail[0]] = tail[1]
        cases.append(constructor_case(label, bytes(storage), length, version, status))
    for status in ('success', 'malformed', 'out_of_range'):
        for length in (IMIN, -1, 0, 1, 24, 25, IMAX):
            add(f'constructor/{status}/length/{length}', length=length, status=status)
        add(f'constructor/{status}/poisoned', b'\xff'*24, IMAX, (U64, U64, U64), status)
    for name in (b'a', b'a'*24, b'a0-b9', b'1', b'A', b'a-', b'a--b', b'-a', b'a\0b', b'a_b'):
        add('constructor/name/'+name.hex(), name)
    for pos in range(1, 24):
        for value in (1, 255):
            add(f'constructor/unused-tail/{pos}/{value}', tail=(pos, value))
    for value in (0, U32, U32+1, 1 << 63, U64):
        for component in range(3):
            version = [1, 2, 3]; version[component] = value
            add(f'constructor/component/{component}/{value}', version=tuple(version))
    for value in range(256):
        add(f'constructor/first-byte/{value}', bytes([value]))
    return cases


def comparison_cases():
    cases = []
    tokens = (b'a@0.0.0', b'a@0.0.1', b'a@0.1.0', b'a@1.0.0', b'b@1.0.0',
              b'a@4294967295.0.0', b'a@0.4294967295.0', b'a@0.0.4294967295',
              b'a@4294967295.4294967295.4294967295', b'A@1.0.0', b'a@01.0.0')
    for i, left in enumerate(tokens):
        for j, right in enumerate(tokens):
            l, r = parse_oracle(left, 0, len(left)), parse_oracle(right, 0, len(right))
            valid = l.status == r.status == 'success'
            same = int(valid and (l.name, l.version) == (r.name, r.version))
            order = ((0 if l.version < r.version else 1 if l.version == r.version else 2) if valid else 3)
            body = array('left', left)+array('right', right)
            body += (f'const package::IdentityResult l=package::parse_identity(borrow_bytes(left),0,{len(left)});'
                     f'const package::IdentityResult r=package::parse_identity(borrow_bytes(right),0,{len(right)});'
                     'if(slot==0){if(package::same_identity(l,r)){return 1u64;}return 0u64;}'
                     'const package::VersionOrder order=package::compare_versions(l,r);'
                     'if(order==package::VersionOrder::less){return 0u64;}'
                     'if(order==package::VersionOrder::equal){return 1u64;}'
                     'if(order==package::VersionOrder::greater){return 2u64;}return 3u64;')
            cases.append(Case(f'comparison/{i}/{j}', body, (same, order)))
    # Forged invalid success must normalize before comparison. Explicit statuses
    # must remain invalid even with otherwise canonical publicly constructed data.
    for status, length in (('success', 0), ('malformed', 1), ('out_of_range', 1)):
        body = 'std::array<u8,24> name=std::array<u8,24>();name.set(0,97u8);'
        body += (f'const package::IdentityResult l=package::IdentityResult(package::IdentityStatus::{status},name,{length},1u64,2u64,3u64);'
                 'const package::IdentityResult r=package::IdentityResult(package::IdentityStatus::success,name,1,1u64,2u64,3u64);'
                 'if(slot==0){if(package::same_identity(l,r)){return 1u64;}return 0u64;}'
                 'if(slot==1){if(package::same_identity(r,l)){return 1u64;}return 0u64;}'
                 'if(slot==2){if(package::compare_versions(l,r)==package::VersionOrder::invalid){return 1u64;}return 0u64;}'
                 'if(package::compare_versions(r,l)==package::VersionOrder::invalid){return 1u64;}return 0u64;')
        cases.append(Case(f'comparison/normalized-invalid/{status}', body, (0, 0, 1, 1)))
    return cases


def ownership_cases():
    token = b'owned-name@4294967295.2147483648.17'
    helpers = ('auto make_owned()->package::IdentityResult{'+array('local', token)
               +f'const package::IdentityResult r=package::parse_identity(borrow_bytes(local),0,{len(token)});return r;}}'
               'auto pass_copy(package::IdentityResult r)->package::IdentityResult{return r;}')
    result = parse_oracle(token, 0, len(token))
    cases = [Case('ownership/function-owner-scope-exit',
                  'const package::IdentityResult local=make_owned();const package::IdentityResult r=pass_copy(local);return observe(r,slot);',
                  result.values(), helpers)]
    scoped = ('auto make_scoped()->package::IdentityResult{{'+array('local', token)
              +f'const package::IdentityResult r=package::parse_identity(borrow_bytes(local),0,{len(token)});return r;}}}}')
    cases.append(Case('ownership/nested-owner-scope-exit',
                      'const package::IdentityResult r=make_scoped();return observe(r,slot);', result.values(), scoped))
    helpers = '''class Counter{i64 calls;public:Counter():calls(0){}
auto next()->u64{calls=calls+1;return 18446744073709551615u64;}
auto byte()->u8{calls=calls+1;return 237u8;}
auto count()const->i64{return calls;}};'''
    for valid in (True, False):
        data = b'a@1.2.3' if valid else b'a@01.2.3'
        body = array('bytes', data)+f'const package::IdentityResult r=package::parse_identity(borrow_bytes(bytes),0,{len(data)});'
        body += ('Counter counter=Counter();const u64 a=r.major_or(counter.next());'
                 'const u64 b=r.minor_or(counter.next());const u64 c=r.patch_or(counter.next());'
                 'const u8 d=r.name_byte_or(0,counter.byte());'
                 'if(slot==0){return u64(counter.count());}if(slot==1){return a;}'
                 'if(slot==2){return b;}if(slot==3){return c;}return u64(d);')
        cases.append(Case('eager-fallback/'+str(valid), body, (4, 1, 2, 3, 97) if valid else (4, U64, U64, U64, 237), helpers))
    for token in (b'A@1.2.3', b'a@x.2.3', b'a@1.2.3'):
        base = parse_case('private-helper-shadow/'+token.decode(), token)
        helpers = 'namespace package{auto lowercase(u8 value)->bool{return true;}auto digit(u8 value)->bool{return true;}}'
        cases.append(Case(base.label, base.body, base.expected, helpers))
    return cases


def negative_cases():
    initial = array('bytes', b'a@1.2.3')
    view = 'const builtin::span<const u8> view=borrow_bytes(bytes);'
    parse = 'const package::IdentityResult r=package::parse_identity(borrow_bytes(bytes),0,7);'
    tail = 'return 0u64;'
    def wrap(body):
        return PREFIX+'auto answer()->u64{'+initial+body+'}'
    out = [
        ('live named span owner mutation', wrap(view+'const package::IdentityResult r=package::parse_identity(view,0,7);bytes[0]=0u8;'+tail), ('cannot mutate a byte array while a span is live',)),
        ('live reborrow owner mutation', wrap(view+'{const builtin::span<const u8> copy=view;const package::IdentityResult r=package::parse_identity(copy,0,7);}bytes[0]=0u8;'+tail), ('cannot mutate a byte array while a span is live',)),
        ('borrow cannot escape as return', PREFIX+'auto leak()->builtin::span<const u8>{'+initial+'return borrow_bytes(bytes);}', ('result', 'return', 'supported')),
        ('span field cannot escape', PREFIX+'class Leak{builtin::span<const u8> view;};auto answer()->u64{return 0u64;}', ('field', 'span', 'supported')),
        ('private status field rejected', wrap(parse+'if(r.outcome==package::IdentityStatus::success){return 1u64;}'+tail), ('private',)),
        ('private name field rejected', wrap(parse+'const std::array<u8,24> copied=r.stored_name;'+tail), ('private',)),
        ('private numeric field rejected', wrap(parse+'return r.major_value;'), ('private',)),
        ('private helper rejected', wrap('if(package::lowercase(97u8)){return 1u64;}'+tail), ('visible', 'unknown', 'private')),
        ('unsigned offset rejected', wrap('const package::IdentityResult r=package::parse_identity(borrow_bytes(bytes),0u64,7);'+tail), ('type', 'i64')),
        ('unsigned count rejected', wrap('const package::IdentityResult r=package::parse_identity(borrow_bytes(bytes),0,7u64);'+tail), ('type', 'i64')),
        ('result cannot convert to integer', wrap(parse+'return u64(r);'), ('conversion', 'class')),
        ('closed status cannot convert', wrap('return u64(package::IdentityStatus::success);'), ('enum', 'conversion')),
        ('closed version order cannot convert', wrap('return u64(package::VersionOrder::less);'), ('enum', 'conversion')),
        ('unsigned name index rejected', wrap(parse+'return u64(r.name_byte_or(0u64,0u8));'), ('type', 'i64')),
        ('wide byte fallback rejected', wrap(parse+'return u64(r.name_byte_or(0,0u64));'), ('type', 'u8')),
        ('signed version fallback rejected', wrap(parse+'return r.major_or(0);'), ('type', 'u64')),
        ('private owned name storage excluded', wrap(parse+'const std::array<u8,24> n=r.name_bytes_or_zero();return u64(n.elements);'), ('private',)),
        ('const returned copy cannot mutate', wrap(parse+'const std::array<u8,24> n=r.name_bytes_or_zero();n.set(0,0u8);'+tail), ('const',)),
        ('span cannot be forged from result', wrap(parse+'const builtin::span<const u8> v=borrow_bytes(r);'+tail), ('array', 'origin')),
        ('constructor-bearing designated initialization rejected', wrap('const package::IdentityResult r=package::IdentityResult{};'+tail), ('private', 'constructor', 'initializ')),
    ]
    exact = {
        'live named span owner mutation': 'cannot mutate a byte array while a span is live',
        'live reborrow owner mutation': 'cannot mutate a byte array while a span is live',
        'borrow cannot escape as return': 'only scalar function results or scalar-field class values are supported',
        'span field cannot escape': 'class fields require scalar, class or private fixed-array storage',
        'private status field rejected': 'private class field is inaccessible',
        'private name field rejected': 'private class field is inaccessible',
        'private numeric field rejected': 'private class field is inaccessible',
        'private helper rejected': 'private function is not imported: package::lowercase',
        'unsigned offset rejected': 'expected i64, got u64',
        'unsigned count rejected': 'expected i64, got u64',
        'result cannot convert to integer': 'class values are only supported in local initializers and field accesses',
        'closed status cannot convert': 'expected distinct i64, u64 or u8 conversion types',
        'closed version order cannot convert': 'expected distinct i64, u64 or u8 conversion types',
        'unsigned name index rejected': 'expected i64, got u64',
        'wide byte fallback rejected': 'expected u8, got u64',
        'signed version fallback rejected': 'expected u64, got i64',
        'private owned name storage excluded': 'private class field is inaccessible',
        'const returned copy cannot mutate': 'mutable method requires a mutable receiver',
        'span cannot be forged from result': 'borrow_bytes requires a named local byte array',
        'constructor-bearing designated initialization rejected': 'constructor-bearing class rejects designated initialization',
    }
    return [(label, source, exact[label]) for label, source, _ in out]


def validate(output, expected, returncode=0):
    require(returncode == 0, f'native exit {returncode}')
    require(len(output) == 8*len(expected), f'exact output length expected {8*len(expected)}, got {len(output)}')
    observed = tuple(int.from_bytes(output[i:i+8], 'little') for i in range(0, len(output), 8))
    for index, (actual, wanted) in enumerate(zip(observed, expected)):
        require(actual == wanted, f'observation {index}: expected {wanted}, got {actual}')
    return observed


def self_test():
    require(parse_oracle(b'a@0.0.0', 0, 7) == Result('success', b'a', (0, 0, 0)), 'oracle minimum')
    require(parse_oracle(b'a@4294967295.0.0', 0, 16).version == (U32, 0, 0), 'oracle u32 upper')
    for token in (b'a@4294967296.0.0', b'a@01.0.0', b'a--b@0.0.0', b'a@0.0.0\n'):
        require(parse_oracle(token, 0, len(token)).status == 'malformed', 'oracle invalid '+repr(token))
    require(parse_oracle(b'a@0.0.0', IMAX, IMAX).status == 'out_of_range', 'oracle signed extremes')
    validate(U64.to_bytes(8, 'little'), (U64,))
    controls = [(b'\xff'+bytes(7), (U64,), 0), (bytes(7), (0,), 0), (bytes(9), (0,), 0), (bytes(8), (0,), -4), (bytes(8), (0,), 1)]
    for output, expected, code in controls:
        try:
            validate(output, expected, code)
        except AssertionError:
            pass
        else:
            raise AssertionError('observer accepted a broken high-bit/length/exit control')
    require(len(Result('success', b'a').values()) == 37, 'observation vector size')
    require(artifact_path(ROOT/'build'/'future-artifact') == ROOT/'build'/'future-artifact', 'normal contained output path')
    for path in (ROOT/'build'/'..'/'..'/'escaped', ROOT/'..'/'escaped', ROOT.parent/'escaped'):
        try:
            artifact_path(path)
        except AssertionError:
            pass
        else:
            raise AssertionError('artifact containment accepted traversal/outside path')
    require(candidate_cap(128) == CAP and candidate_cap(1024) == MAX_CAP, 'approved cap boundaries')
    cap_self_test()


class Runner:
    def __init__(self, compiler, artifacts, cap=CAP):
        self.compiler = compiler
        self.cap = cap
        self.artifacts = artifacts
        self.peak = 0
        self.process_count = 0
        self.tools = {name: Path(shutil.which(name)).resolve(strict=True) for name in ('as', 'ld', 'nm', 'readelf')}

    def budget(self, reserve=0):
        allocated = ROOT.lstat().st_blocks*512 + sum(p.lstat().st_blocks*512 for p in ROOT.rglob('*'))
        self.peak = max(self.peak, allocated)
        require(allocated+reserve <= self.cap, f'whole-candidate {self.cap} byte cap: {allocated} + reserve {reserve}')
        require(shutil.disk_usage(ROOT).free-reserve >= FLOOR, '1 GiB free floor including reserve')
        return allocated

    def command(self, args, directory, name, *, compiler=False, allow_rejection=False):
        args = list(args)
        if str(args[0]) in self.tools:
            args[0] = self.tools[str(args[0])]
        self.budget(24 << 20)
        self.process_count += 1
        def limits():
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
            resource.setrlimit(resource.RLIMIT_CPU, (10, 11))
            resource.setrlimit(resource.RLIMIT_FSIZE, (8 << 20, 8 << 20))
            resource.setrlimit(resource.RLIMIT_AS, ((512 if compiler else 128) << 20,)*2)
        record = dict(command=list(map(str, args)), wall_seconds=30, cpu_soft_hard_seconds=[10, 11],
                      address_space_bytes=(512 if compiler else 128) << 20,
                      regular_file_cap=8 << 20, total_growth_reserve=24 << 20)
        try:
            with (directory/(name+'.stdout')).open('wb') as out, (directory/(name+'.stderr')).open('wb') as err:
                result = subprocess.run(list(map(str, args)), stdout=out, stderr=err,
                                        timeout=30, preexec_fn=limits)
            record['returncode'] = result.returncode
            stderr = (directory/(name+'.stderr')).read_bytes()
            allowed = (0, 1) if allow_rejection else (0,)
            require(result.returncode in allowed, f'{name} exit {result.returncode}: {stderr[:4096]!r}')
            if result.returncode == 0:
                require(not stderr, name+' unexpected stderr '+repr(stderr[:4096]))
            self.budget()
            return result.returncode, (directory/(name+'.stdout')).read_bytes(), stderr
        except subprocess.TimeoutExpired:
            record['timeout'] = True
            raise AssertionError(name+' wall-clock timeout')
        finally:
            (directory/(name+'.command.json')).write_text(json.dumps(record, indent=2)+'\n')

    def batch(self, number, cases):
        self.budget(1 << 20)
        directory = self.artifacts/f'batch-{number:03d}'
        directory.mkdir()
        source = PREFIX+shared()+''.join(dict.fromkeys(case.helpers for case in cases))
        source += ''.join(f'auto identity_case_{i}(i64 slot)->u64{{{case.body}}}\n' for i, case in enumerate(cases))
        require(len(source.encode()) <= SOURCE_CAP, '64 KiB batch source bound')
        (directory/'input.au').write_text(source)
        receipt = dict(status='running', source_sha256=sha(directory/'input.au'), source_bytes=len(source.encode()), cases=len(cases))
        try:
            self.command([self.compiler, '--module-root', ROOT/'library', directory/'input.au', '-o', directory/'compiled.s'], directory, 'compiler', compiler=True)
            expected = tuple(value for case in cases for value in case.expected)
            asm = ['.text', '.globl _start', '_start:']
            position = 0
            for i, case in enumerate(cases):
                for slot in range(len(case.expected)):
                    asm += [f'movq ${slot}, %rdi', f'call identity_case_{i}', f'movq %rax, observations+{position}(%rip)']
                    position += 8
            asm += ['movq $1,%rax', 'movq $1,%rdi', 'leaq observations(%rip),%rsi', f'movq ${position},%rdx', 'syscall',
                    f'cmpq ${position},%rax', 'jne .Lwrite_failed', 'movq $60,%rax', 'xorq %rdi,%rdi', 'syscall',
                    '.Lwrite_failed:', 'movq $60,%rax', 'movq $91,%rdi', 'syscall', '.bss', '.align 8', f'observations: .zero {position}',
                    '.section .note.GNU-stack,"",@progbits']
            (directory/'entry.s').write_text('\n'.join(asm)+'\n')
            self.command(['as', '--64', directory/'compiled.s', '-o', directory/'program.o'], directory, 'assemble')
            self.command(['as', '--64', directory/'entry.s', '-o', directory/'entry.o'], directory, 'entry')
            self.command(['ld', '-o', directory/'program', directory/'entry.o', directory/'program.o'], directory, 'link')
            _, undefined, _ = self.command(['nm', '-u', directory/'program'], directory, 'undefined-symbols')
            require(not undefined.strip(), 'freestanding binary must have no unresolved symbols')
            _, elf, _ = self.command(['readelf', '-l', '-d', directory/'program'], directory, 'elf-linkage')
            require(b'INTERP' not in elf and b'NEEDED' not in elf, 'no ELF interpreter or runtime library dependencies')
            code, output, _ = self.command([directory/'program'], directory, 'native')
            observed = validate(output, expected, code)
            require((directory/'input.au').read_text() == source, 'compiler must preserve source')
            offset = 0
            records = []
            for case in cases:
                end = offset+len(case.expected)
                records.append(dict(label=case.label, expected=case.expected, observed=observed[offset:end]))
                offset = end
            receipt.update(status='passed', complete_u64_observations=len(expected), observations=records,
                           assembly_sha256=sha(directory/'compiled.s'), executable_sha256=sha(directory/'program'),
                           native_output_sha256=sha(directory/'native.stdout'))
        except Exception as exc:
            receipt.update(status='failed', error=str(exc))
            raise
        finally:
            (directory/'receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
        # Only successful, reproducible build products are deleted. The source,
        # command logs, native bytes, hashes and detailed receipt stay on disk.
        for name in ('compiled.s', 'entry.s', 'program.o', 'entry.o', 'program'):
            (directory/name).unlink()

    def reject(self, number, label, source, words):
        for existing in (False, True):
            self.budget(65536)
            directory = self.artifacts/f'reject-{number:02d}-{int(existing)}'
            directory.mkdir()
            path = directory/'input.au'; path.write_text(source)
            output = directory/'compiled.s'
            sentinel = b'keep existing identity output\n\x00\xff'
            if existing:
                output.write_bytes(sentinel)
            receipt = dict(status='running', label=label, existing_output=existing)
            try:
                code, _, diagnostic = self.command([self.compiler, '--module-root', ROOT/'library', path, '-o', output],
                                                   directory, 'compiler', compiler=True, allow_rejection=True)
                require(code == 1, label+' must reject normally with exit 1')
                require(diagnostic.startswith(b'aurorac: '), label+' needs a compiler diagnostic')
                text = diagnostic.decode(errors='replace').lower()
                require(words in text, label+' wrong rejection: '+text)
                require('sanitizer' not in text, 'sanitizer error is not a semantic rejection')
                require(path.read_text() == source, 'rejection changed source')
                require(output.read_bytes() == sentinel if existing else not output.exists(), 'rejection changed output')
                receipt.update(status='passed', diagnostic=diagnostic.decode(errors='replace'))
            except Exception as exc:
                receipt.update(status='failed', error=str(exc))
                raise
            finally:
                (directory/'receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('compiler', nargs='?', type=Path, default=ROOT/'build/aurorac')
    parser.add_argument('--artifacts', '--artifact-root', dest='artifact_root', type=Path)
    parser.add_argument('--quick', '--smoke', dest='smoke', action='store_true', help='development subset, never the full acceptance gate')
    parser.add_argument('--self-test-only', action='store_true')
    parser.add_argument('--candidate-cap-mib', type=int, default=128, help='whole-candidate storage cap 128..1024 MiB; default 128; increases require explicit aggregate admission')
    parser.add_argument('--compiler-sha256', default=COMPILER_SHA256, help='explicit expected compiler SHA256; default preserves accepted M022 pin')
    parser.add_argument('--check-cap-only', action='store_true', help='configuration-only cap checks; no compiler, native test or acceptance receipt')
    args = parser.parse_args()
    cap = candidate_cap(args.candidate_cap_mib)
    if args.check_cap_only:
        cap_self_test()
        print(json.dumps(dict(status='configuration-only', native_executed=False,
            candidate_cap_mib=args.candidate_cap_mib, cap_bytes=cap,
            focused_default_mib=128, maximum_cap_mib=1024), sort_keys=True))
        return
    self_test()
    if args.self_test_only:
        print('PASS independent regex/integer oracle and observation negative self-tests')
        return
    compiler = args.compiler.resolve(strict=True)
    require(re.fullmatch(r'[0-9a-f]{64}', args.compiler_sha256) is not None, 'expected compiler SHA256 must be 64 lowercase hex characters')
    require(sha(compiler) == args.compiler_sha256, 'exact expected compiler SHA256 required')
    artifacts = artifact_path(args.artifact_root or ROOT/f'build/package-identity-{os.getpid()}')
    require(artifacts.parent.is_dir() and not artifacts.exists(), 'fresh artifact root with existing parent required')
    runner = Runner(compiler, artifacts, cap)
    runner.budget(65536); artifacts.mkdir()
    frozen = ROOT/'evidence/package-identity/contract-before-implementation.md'
    require(sha(frozen) == CONTRACT_SHA256, 'frozen pre-implementation contract byte identity')
    pins = {str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p): sha(p) for p in
            [compiler, ROOT/'library/package/identity.au', ROOT/'library/std/array.au', Path(__file__).resolve(),
             frozen, Path(sys.executable).resolve(strict=True), *runner.tools.values()]}
    report = dict(status='running', compiler_sha256_before=sha(compiler), pins=pins,
                  contract_document_sha256=sha(ROOT/'docs/package-identity-contract.md'),
                  authored_contract_sha256=sha(frozen),
                  tool_paths={name: str(path) for name, path in runner.tools.items()},
                  python_path=str(Path(sys.executable).resolve()),
                  command=sys.argv, started_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                  cap_bytes=cap, free_floor_bytes=FLOOR, per_source_cap_bytes=SOURCE_CAP,
                  cases_per_batch=BATCH, smoke_only=args.smoke,
                  model='Independent Python bytes regex fullmatch and arbitrary precision int',
                  native='GNU as/ld x86-64, direct Linux write/exit only, no target libc',
                  limits='Bounded finite execution evidence, not a memory-safety or performance proof')
    try:
        for name, tool in {**runner.tools, 'python': Path(sys.executable).resolve()}.items():
            runner.command([tool, '--version'], artifacts, 'version-'+name)
        parse = parsing_cases(); construction = construction_cases(); comparisons = comparison_cases(); ownership = ownership_cases()
        if args.smoke:
            parse = parse[:6]
            construction = construction[:6]
            comparisons = comparisons[:6]
        cases = parse+construction+comparisons+ownership
        report.update(parse_cases=len(parse), constructor_cases=len(construction), comparison_cases=len(comparisons),
                      ownership_eager_cases=len(ownership), native_cases=len(cases),
                      complete_u64_observations=sum(len(c.expected) for c in cases), rejection_cases=len(negative_cases()))
        for start in range(0, len(cases), BATCH):
            batch = cases[start:start+BATCH]
            runner.batch(start//BATCH, batch)
            print(f'PASS package identity {start+len(batch)}/{len(cases)} native cases', flush=True)
        for number, (label, source, words) in enumerate(negative_cases()):
            runner.reject(number, label, source, words)
        require(pins == {p: sha(ROOT/p) for p in pins}, 'compiler/library/test inputs changed during execution')
        report['status'] = 'passed'
    except Exception as exc:
        report.update(status='failed', error=str(exc))
        raise
    finally:
        report.update(compiler_sha256_after=sha(compiler), candidate_allocated_bytes=runner.budget(),
                      peak_candidate_allocated_bytes=runner.peak, global_free_bytes=shutil.disk_usage(ROOT).free,
                      process_count=runner.process_count, finished_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()))
        (artifacts/'manifest.json').write_text(json.dumps(report, indent=2)+'\n')
    print(f'PASS package identity: {len(cases)} native cases, {report["complete_u64_observations"]} complete u64 observations, '
          f'{2*report["rejection_cases"]} rejection runs; pinned compiler unchanged', flush=True)


if __name__ == '__main__':
    main()
