#!/usr/bin/env python3
"""Bounded native ASCII token gate, independent regex oracle and host differential.

Reuse utf8_range's identity, budgeting and ordinary bounded command runner. The
host adapter alone has a narrowly separate build/run resource classification.
Keep all generated sources, assembly, complete i64 output and failure receipts.
No target FFI, runtime imports, implementation-derived oracle or source mutation.
"""
from __future__ import annotations
import argparse
from dataclasses import dataclass
import hashlib
import itertools
import json
import os
import pathlib
import random
import re
import resource
import subprocess
import sys
import time
sys.dont_write_bytecode = True
import utf8_range as harness
from compiler_contract import parse_cxx, selected_flag_vectors, tool_record

require = harness.require
MIN, MAX = harness.MIN, harness.MAX
STATUSES = ('success', 'end_of_input', 'invalid_byte', 'invalid_window')
KINDS = ('none', 'identifier', 'digit_word', 'punctuation', 'operator_pair')
ACCESSORS = ('byte_offset', 'byte_count', 'consumed_bytes', 'skipped_lf')
PAIRS = (b'->', b'==', b'!=', b'<=', b'>=', b'::', b'<<', b'>>', b'&&', b'||')
PUNCTUATION = b'(){}[]:;,=+-*/%<>!.&|^~'
TRIVIA = re.compile(rb'(?:(?:[\x09-\x0d\x20]+)|(?://[^\n]*(?:\n|$)))*')
WORD = re.compile(rb'(?:[A-Za-z_][A-Za-z0-9_]*|[0-9][A-Za-z0-9_]*)')
PAIR = re.compile(rb'(?:->|==|!=|<=|>=|::|<<|>>|&&|\|\|)')
PUNCT = re.compile(rb'[(){}\[\]:;,=+*/%<>!.&|^~\-]')
SPAN = 'builtin::span<const u8>'
RESULT = 'std::TokenResult'
BAD_SHAPE = (3, 0, 0, 0, 0, 0)


def model(data, offset, count):
    """Anchored byte regexes over an explicit final slice; no library helpers."""
    if (len(data) > 4096 or offset < 0 or count < 0 or offset > len(data)
            or count > len(data) - offset):
        return BAD_SHAPE
    window = bytes(data[offset:offset + count])
    skipped = TRIVIA.match(window).end()
    lf = window[:skipped].count(b'\n')
    remaining = window[skipped:]
    if not remaining:
        return (1, 0, offset + count, 0, count, lf)
    word = WORD.match(remaining)
    if word:
        length = word.end()
        kind = 2 if remaining[:1].isdigit() else 1
    elif PAIR.match(remaining):
        length, kind = 2, 4
    elif PUNCT.match(remaining):
        length, kind = 1, 3
    else:
        return (2, 0, offset + skipped, 1, skipped + 1, lf)
    return (0, kind, offset + skipped, length, skipped + length, lf)


def report_model(status, kind, offset, count, consumed, lf):
    values = (offset, count, consumed, lf)
    valid = (status != 3 and all(0 <= v <= 4096 for v in values)
             and count <= 4096 - offset and consumed >= count
             and consumed - count <= offset and lf <= consumed - count)
    if status == 0:
        valid = valid and ((kind in (1, 2) and count >= 1)
                          or (kind == 3 and count == 1) or (kind == 4 and count == 2))
    elif status == 1:
        valid = valid and kind == 0 and count == 0
    elif status == 2:
        valid = valid and kind == 0 and count == 1
    return (status, kind, *values) if valid else BAD_SHAPE


@dataclass(frozen=True)
class Case:
    label: str
    data: bytes
    offset: int = 0
    count: int | None = None
    windows: tuple[tuple[int, int], ...] = ()

    def span(self):
        data = self.data
        for offset, count in self.windows:
            require(0 <= offset <= len(data) and 0 <= count <= len(data)-offset,
                    'generator supplied invalid subspan')
            data = data[offset:offset + count]
        return data

    def extent(self):
        return len(self.span()) if self.count is None else self.count


@dataclass(frozen=True)
class Test:
    label: str
    body: str
    expected: tuple[int, ...]
    helper: str = ''
    # Actual native trace (including terminal EOF) is reconciled against bytes
    # and then compared with the separately executed unchanged host lexer.
    stream: bytes | None = None
    stream_offset: int = 0


def cases():
    for byte in range(256):
        yield Case(f'byte {byte} outside comment', bytes((byte,)))
        yield Case(f'byte {byte} after trivia', b'\t\n\r '+bytes((byte,)))
        yield Case(f'byte {byte} in opaque comment', b'//'+bytes((byte,))+b'\nZ')
    for word in (b'a', b'Z09_', b'_', b'_0', b'9', b'12foo', b'0x', b'7_', b'9u8', b'if', b'while'):
        yield Case('word classification and unsupported suffix deferral', word+b'\xff')
        yield Case('word final window', word+b'tail', 0, len(word))
    for pair in PAIRS:
        for offset, count in ((0, 1), (1, 1), (0, 2), (0, 3), (1, 2), (2, 0)):
            yield Case('operator pair clipped/final '+pair.decode(), pair+b'=', offset, count)
        yield Case('operator pair nested subspan '+pair.decode(), b'!? '+pair+b' ??',
                   1, 2, ((1, 6), (1, 4)))
        yield Case('operator pair nested final first byte '+pair.decode(), b'!? '+pair+b' ??',
                   1, 1, ((1, 6), (1, 4)))
    for raw in (b'//', b'///', b'/x', b'//opaque\r\0\xff', b'//\n\nZ', b'//\rZ\nQ',
                b'//\0\x80\xff\r\n\nQ', b'/\n/', b'/*text*/', b'++--**!!..'):
        for start, count in sorted({(0, 0), (0, 1), (0, len(raw)), (1, len(raw)-1),
                                    (len(raw), 0), (0, max(0, len(raw)-1))}):
            yield Case('comment/op final and slash-clipped windows', raw, start, count)
    yield Case('window beginning inside parent comment has ordinary state', b'//name \xff\nQ', 2, 4)
    yield Case('unsupported byte inside parent comment becomes ordinary window input', b'//\xff\nQ', 2, 1)
    for raw in (b' A0->b\n//z\n9_', b'\xff\nZ', b'\v\f\r\t \n', b'[]{}(),:;', b'?:@$`\\"\''):
        # A bounded representative window sweep, rather than all long products.
        for start in range(len(raw)+1):
            for count in sorted({0, min(1, len(raw)-start), len(raw)-start}):
                yield Case('representative byte windows', raw, start, count)
    for dimension in range(2):
        for extreme in (MIN, -1, 0, 1, 2, 3, 4, 4096, 4097, MAX):
            args = [1, 2]; args[dimension] = extreme
            yield Case('signed window dimension', b'\xff\nA', *args)
    for offset, count in ((MIN, MIN), (MIN, MAX), (MAX, MIN), (MAX, MAX), (-1, -1)):
        yield Case('combined invalid signed windows before unsupported byte', b'\xff', offset, count)
    for offset, count in ((0, 0), (0, 1), (1, 0), (-1, 0), (MIN, MAX), (MAX, 0)):
        yield Case('actual zero-length endpoint nested span', b'\xff', offset, count, ((1, 0), (0, 0)))
    for raw in (b'A'*4096, b'9'*4096, b'_'*4096, b'//'+b'\xff'*4094,
                b' '*4096, b'\n'*4096, b'\t'*4095+b'Z', b'A'*4095+b'\xff',
                b'9'*4095+b'"', b'//'+b'\0'*4093+b'\n'):
        yield Case('maximum 4096-byte owner/word/comment/trivia', raw)
    yield Case('maximal word final excludes invalid suffix', b'A'*4095+b'\xff', 0, 4095)
    rng = random.Random(20261006)
    for _ in range(40):
        raw = bytes(rng.randrange(256) for _ in range(rng.randrange(1, 25)))
        start = rng.randrange(len(raw)+1)
        yield Case('seeded arbitrary window', raw, start, rng.randrange(len(raw)-start+1))


def observe(report='report', selector='field'):
    body = f'if({selector}==0){{'
    for number, status in enumerate(STATUSES):
        body += f'if({report}.status()==std::TokenStatus::{status}){{return {number};}}'
    body += f'return -777;}}if({selector}==1){{'
    for number, kind in enumerate(KINDS):
        body += f'if({report}.kind()==std::TokenKind::{kind}){{return {number};}}'
    body += 'return -778;}'
    for number, accessor in enumerate(ACCESSORS, 2):
        body += f'if({selector}=={number}){{return {report}.{accessor}();}}'
    return body+'return -779;'


def preserved_and_copy(original='original'):
    return ('i64 check=0;while(check<len(owner)){if(owner[check]!=saved[check]){return -780;}'
            'check=check+1;}owner[0]=0u8;'
            f'const {RESULT} report={original};')


def source_case(case):
    span = case.span()
    expected = model(span, case.offset, case.extent())
    helper = f'auto input_scan_CASE({SPAN} bytes)->{RESULT}{{'
    parent = 'bytes'
    for i, (offset, count) in enumerate(case.windows):
        name = f'view{i}'
        helper += f'const {SPAN} {name}={parent}.subspan({offset},{count});'
        parent = name
    helper += f'const {RESULT} result=std::next_token({parent},{case.offset},{case.extent()});return result;}}'
    body = harness.array(case.data)+f'const builtin::array<u8,{len(case.data)}> saved=owner;'
    body += f'const {RESULT} original=input_scan_CASE(borrow_bytes(owner));'
    body += preserved_and_copy()+observe()
    return Test(case.label, body, expected, helper)


def expired_owner_reports():
    for raw in (b'A', b'12foo', b'->', b'\n\xff', b'//\xff\n'):
        helper = (f'auto expired_scan_CASE()->{RESULT}{{'+harness.array(raw)
                  +f'const {RESULT} result=std::next_token(borrow_bytes(owner),0,{len(raw)});return result;}}')
        body = f'const {RESULT} original=expired_scan_CASE();const {RESULT} report=original;'+observe()
        yield Test('copied result survives destruction of source owner', body, model(raw, 0, len(raw)), helper)


def public_reports():
    # One dimension at a time around valid representatives. Cross-field edges are
    # explicit below; the four dimensions are never a large Cartesian product.
    seeds = ((0, 1, 3, 2, 4, 1), (0, 2, 0, 1, 1, 0), (0, 3, 4095, 1, 1, 0),
             (0, 4, 2, 2, 3, 1), (1, 0, 4096, 0, 4096, 4096), (2, 0, 2, 1, 3, 2))
    values = set(seeds)
    for seed in seeds:
        for dimension in range(2, 6):
            for edge in (MIN, -1, 0, 1, 4095, 4096, 4097, MAX):
                row = list(seed); row[dimension] = edge; values.add(tuple(row))
    for status, kind in itertools.product(range(4), range(5)):
        for shape in ((0, 0, 0, 0), (0, 1, 1, 0), (0, 2, 2, 0), (2, 1, 3, 2)):
            values.add((status, kind, *shape))
    values.update(((0, 1, 4095, 2, 2, 0), (0, 1, 0, 1, 2, 0),
                   (0, 1, 1, 1, 2, 2), (0, 1, 1, 1, 1, 1),
                   (1, 0, 4096, 0, 4096, 4096), (1, 0, 0, 0, 1, 0),
                   (2, 0, 4096, 1, 1, 0), (3, 4, MIN, MAX, MIN, MAX)))
    for status, kind, offset, count, consumed, lf in sorted(values):
        expected = report_model(status, kind, offset, count, consumed, lf)
        body = (f'const {RESULT} original={RESULT}(std::TokenStatus::{STATUSES[status]},'
                f'std::TokenKind::{KINDS[kind]},{offset},{count},{consumed},{lf});'
                f'const {RESULT} report=original;'+observe())
        yield Test('public copied shape and masking', body, expected)


def trace_model(raw, offset=0):
    used = 0
    reports = []
    while True:
        report = model(raw, used, len(raw)-used)
        # Rebase to a requested nonzero window when needed.
        report = (*report[:2], report[2]+offset, *report[3:])
        reports.append(report)
        if report[0] == 1:
            require(used+report[4] == len(raw), 'oracle EOF consumes final trivia')
            break
        require(report[0] in (0, 2) and 0 < report[4] <= len(raw)-used,
                'oracle trace progress')
        used += report[4]
        require(len(reports) <= len(raw), 'oracle bounded nonterminal trace')
    return tuple(value for report in reports for value in report)


def trace_case(raw, label='repeated scanning and exact reconciliation', prefix=b''):
    # Empty input is an actual zero-length subspan, not an owner plus count zero.
    data = prefix + raw
    owner_data = data or b'\xff'
    start = len(prefix)
    body = harness.array(owner_data)+f'const builtin::array<u8,{len(owner_data)}> saved=owner;'
    body += f'i64 used={start};i64 selected=field;i64 calls=0;bool stopped=false;'
    body += f'while(!stopped){{if(calls>{len(raw)}){{return -781;}}'
    if data:
        call = f'std::next_token(borrow_bytes(owner),used,{len(data)}-used)'
        helper = ''
    else:
        helper = (f'auto empty_scan_CASE({SPAN} bytes)->{RESULT}{{'
                  f'const {SPAN} empty=bytes.subspan(1,0);'
                  f'const {RESULT} result=std::next_token(empty,0,0);return result;}}')
        call = 'empty_scan_CASE(borrow_bytes(owner))'
    body += f'const {RESULT} original={call};'
    body += (f'if(original.status()==std::TokenStatus::invalid_window){{return -782;}}'
             f'if(original.consumed_bytes()<0){{return -783;}}'
             f'if(original.consumed_bytes()>{len(data)}-used){{return -784;}}'
             'if(original.byte_offset()<used){return -785;}'
             'if(original.byte_count()<0){return -786;}'
             'if(original.byte_offset()+original.byte_count()!=used+original.consumed_bytes()){return -787;}'
             'i64 lf=0;i64 pos=used;while(pos<original.byte_offset()){'
             'if(owner[pos]==10u8){lf=lf+1;}pos=pos+1;}'
             'if(lf!=original.skipped_lf()){return -788;}'
             'if(original.status()==std::TokenStatus::end_of_input){'
             f'if(used+original.consumed_bytes()!={len(data)}){{return -789;}}stopped=true;'
             '}else{if(original.consumed_bytes()<=0){return -790;}}'
             'if(selected<6){'+preserved_and_copy()+observe(selector='selected')+'}'
             'used=used+original.consumed_bytes();selected=selected-6;calls=calls+1;}'
             'return -791;')
    return Test(label, body, trace_model(raw, start), helper, raw, start)


def sequences():
    raw_cases = [b'', b'\n', b'\r\n\n', b'\0\xffZ\n//tail\xff\r',
                 b'alpha 12foo _0\t->\n9u8//opaque\0\xff\r\n end\n\t',
                 b'//\r\0\xff', b'//\n//\n//\xff\n', b' / //tail',
                 b'A\xffB\0C\x7f\n\n', b'/* x */', b'++--**!!..',
                 PUNCTUATION, b' '.join(PAIRS), b'if module while const',
                 b'A'*4096, b'9'*4095+b'\xff', b'\n'*4096,
                 b'//'+b'\xff'*4093+b'\n']
    for pair in PAIRS:
        raw_cases += [pair, pair[:1], pair[1:], b'X\n'+pair+b'\n//end']
    # Full native recovery and host error/valid differential for every byte;
    # every possible byte is also accepted as opaque comment content.
    for byte in range(256):
        raw_cases += [bytes((byte,)), b'//'+bytes((byte,))+b'\nQ']
    for raw in raw_cases:
        yield trace_case(raw)
    yield trace_case(b'\n X\xffY\n//final', 'nonzero-window recovery and final LF', b'\xff\xff')


def rejections(private_fields, private_helpers):
    head = 'module token_rejection;import std.token_scan;'
    construct = f'const {RESULT} r={RESULT}(std::TokenStatus::success,std::TokenKind::identifier,0,1,1,0);'
    for field in private_fields:
        yield ('private result '+field, head+'auto test()->i64{'+construct+f'return r.{field};}}', 'private')
    for helper in private_helpers:
        # Visibility lookup must fail before argument checking.
        yield ('private helper '+helper, head+f'auto test()->i64{{return std::{helper}();}}', 'private function is not imported')
    for dimension in range(2):
        for wrong in ('0u64', '0u8', 'false'):
            args = ['0', '1']; args[dimension] = wrong
            yield ('exact i64 window parameter', head+'auto test()->i64{builtin::array<u8,1> b={65u8};'
                   f'const {RESULT} r=std::next_token(borrow_bytes(b),{args[0]},{args[1]});return r.byte_count();}}', 'expected i64')
    for dimension in range(4):
        args = ['0', '1', '1', '0']; args[dimension] = '0u64'
        yield ('exact i64 constructor parameter', head+'auto test()->i64{'
               f'const {RESULT} r={RESULT}(std::TokenStatus::success,std::TokenKind::identifier,{",".join(args)});return r.byte_count();}}', 'expected i64')
    yield ('status enum nominal identity', head+'auto test()->i64{'
           f'const {RESULT} r={RESULT}(std::TokenKind::none,std::TokenKind::identifier,0,1,1,0);return r.byte_count();}}', 'expected')
    yield ('kind enum nominal identity', head+'auto test()->i64{'
           f'const {RESULT} r={RESULT}(std::TokenStatus::success,std::TokenStatus::success,0,1,1,0);return r.byte_count();}}', 'expected')
    yield ('raw owner cannot replace span', head+'auto test()->i64{builtin::array<u8,1> b={65u8};'
           f'const {RESULT} r=std::next_token(b,0,1);return r.byte_count();}}', 'span')
    yield ('owner length 4097 is unconstructible', head+'auto test()->i64{builtin::array<u8,4097> b={};return 0;}', '4096')
    yield ('nonbyte source owner', head+'auto test()->i64{builtin::array<i64,1> b={65};'
           f'const {RESULT} r=std::next_token(borrow_bytes(b),0,1);return r.byte_count();}}', 'byte')
    yield ('readonly source live mutation', head+'auto test()->i64{builtin::array<u8,1> b={65u8};'
           f'const {SPAN} v=borrow_bytes(b);const {RESULT} r=std::next_token(v,0,1);b[0]=0u8;return r.byte_count();}}', 'span is live')
    yield ('nested empty span still retains owner', head+'auto test()->i64{builtin::array<u8,1> b={65u8};'
           f'const {SPAN} v=borrow_bytes(b);const {SPAN} e=v.subspan(1,0);'
           f'const {RESULT} r=std::next_token(e,0,0);b[0]=0u8;return r.byte_count();}}', 'span is live')
    yield ('span cannot escape as class field', head+f'class Bad{{{SPAN} bytes;}};auto test()->i64{{return 0;}}', 'class fields require')
    yield ('unsupported span return type', head+f'auto bad({SPAN} b)->{SPAN}{{return b;}}', 'only scalar function results')
    yield ('closed status prevents integer construction', head+'auto test()->i64{'
           f'const {RESULT} r={RESULT}(17,std::TokenKind::none,0,0,0,0);return r.byte_count();}}', 'expected')


def private_names(source):
    declaration = re.search(r'class TokenResult\s*\{(.*?)public:', source, re.S)
    require(declaration is not None, 'TokenResult private declaration available')
    fields = re.findall(r'\b(?:TokenStatus|TokenKind|i64)\s+(\w+)\s*;', declaration.group(1))
    helpers = sorted(set(re.findall(r'\bauto\s+(token_\w+)\s*\(', source)))
    require(len(fields) == 6, 'six private copied fields required')
    require(helpers, 'private scanner helpers required for privacy controls')
    return fields, helpers


class Suite(harness.Suite):
    def __init__(self, args, identity):
        super().__init__(args, identity)
        self.observations = 0
        self.traces = []
        self.mutations = 0
        self.host = self.output/'host'/'token-scan-host'
        for name in ('tests/compiler/token_scan.py', 'tests/compiler/token_scan_host.cpp',
                     'tests/compiler/utf8_range.py', 'scripts/compiler_contract.py',
                     'compiler/lexer.hpp', 'compiler/lexer_types.hpp', 'compiler/lexer_reference.hpp',
                     'compiler/byte_literal.hpp', 'compiler/types.hpp', 'examples/token_scan.au'):
            self.inputs[name] = harness.sha(self.root/name)

    def batch(self, items, module_root=None, mutation=None):
        self.budget()
        d = self.output/(f'mutation-{mutation}' if mutation else f'batch-{self.batches:04d}')
        d.mkdir()
        if not mutation:
            self.batches += 1
        source = 'module token_scan_test;import std.token_scan;\n'
        for i, item in enumerate(items):
            source += item.helper.replace('_CASE', f'_{i}')+'\n'
            source += f'auto token_case_{i}(i64 field)->i64{{{item.body.replace("_CASE", f"_{i}")}}}\n'
        require(len(source.encode()) <= 65536, 'source-size cap')
        (d/'input.au').write_text(source)
        wanted = [v for item in items for v in item.expected]
        receipt = dict(labels=[item.label for item in items], expected=wanted,
                       source_sha256=harness.sha(d/'input.au'), status='running')
        try:
            self.command([self.compiler, '--module-root', module_root or self.root/'library',
                          d/'input.au', '-o', d/'compiled.s'], d, 'compiler')
            entry = ['.text', '.globl _start', '_start:']
            for i, item in enumerate(items):
                for field in range(len(item.expected)):
                    entry += [f'movq ${field},%rdi', f'call token_case_{i}', 'pushq %rax',
                              'movq $1,%rax', 'movq $1,%rdi', 'movq %rsp,%rsi',
                              'movq $8,%rdx', 'syscall', 'addq $8,%rsp']
            entry += ['movq $60,%rax', 'xorq %rdi,%rdi', 'syscall', '.section .note.GNU-stack,"",@progbits']
            (d/'entry.s').write_text('\n'.join(entry)+'\n')
            self.command(['as', '--64', d/'compiled.s', '-o', d/'program.o'], d, 'assemble')
            self.command(['as', '--64', d/'entry.s', '-o', d/'entry.o'], d, 'entry')
            undefined = self.command(['nm', '-u', d/'program.o'], d, 'undefined-object')
            require(not undefined.strip(), 'Aurora object has unresolved target runtime imports')
            self.command(['ld', '-o', d/'program', d/'entry.o', d/'program.o'], d, 'link')
            undefined = self.command(['nm', '-u', d/'program'], d, 'undefined-native')
            require(not undefined.strip(), 'native binary has unresolved imports')
            output = self.command([d/'program'], d, 'native')
            require(len(output) == 8*len(wanted), 'exact full-i64 observation length')
            observed = [int.from_bytes(output[i:i+8], 'little', signed=True) for i in range(0, len(output), 8)]
            receipt.update(observed=observed, output_sha256=hashlib.sha256(output).hexdigest())
            if mutation:
                require(observed != wanted, 'deliberate semantic mutant escaped native oracle')
                receipt.update(status='detected', mismatch=[(i, a, b) for i, (a, b) in enumerate(zip(observed, wanted)) if a != b][:12])
                self.mutations += 1
            else:
                require(observed == wanted, f'native mismatch {[(i,a,b) for i,(a,b) in enumerate(zip(observed,wanted)) if a!=b][:12]}')
                begin = 0
                for item in items:
                    end = begin + len(item.expected)
                    if item.stream is not None:
                        self.reconcile(item, observed[begin:end])
                    begin = end
                self.count += len(items)
                self.observations += len(wanted)
                receipt['status'] = 'passed'
        except Exception as error:
            receipt.update(status='failed', error=str(error)); raise
        finally:
            (d/'receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
        print(f'PASS token {"mutation "+mutation if mutation else "batch "+str(self.batches)}: '
              f'{len(items)} cases; {len(wanted)} complete i64 observations', flush=True)

    def reconcile(self, item, observed):
        raw = item.stream
        reports = [tuple(observed[i:i+6]) for i in range(0, len(observed), 6)]
        used = lf = 0
        tokens = []
        invalid = False
        fragments = []
        for index, (status, kind, offset, count, consumed, skipped_lf) in enumerate(reports):
            position = offset - item.stream_offset
            require(used <= position <= len(raw), 'native token coordinate is supplied-span-relative')
            require(position+count == used+consumed <= len(raw), 'native exact partition of consumed bytes')
            trivia = raw[used:position]
            require(TRIVIA.fullmatch(trivia) is not None, 'native skipped bytes must be complete trivia')
            require(skipped_lf == trivia.count(b'\n'), 'native exact LF reconciliation')
            spelling = raw[position:position+count]
            fragments += [trivia, spelling]
            lf += skipped_lf
            if status == 1:
                require(index == len(reports)-1 and kind == 0 and count == 0
                        and position == len(raw), 'native EOF is unique, final and consumes trailing trivia')
            else:
                require(consumed > 0 and index < len(reports)-1, 'native progress and eventual EOF')
                if status == 0:
                    tokens.append((1+lf, spelling.hex()))
                else:
                    require(status == 2 and kind == 0 and count == 1, 'native recovery consumes one invalid byte')
                    invalid = True
            used += consumed
        require(used == len(raw) and b''.join(fragments) == raw, 'exact full source spelling/trivia reconstruction')
        require(lf == raw.count(b'\n'), 'all source LF accounted for after recovery')
        if not invalid:
            tokens.append((1+lf, b'<eof>'.hex()))
        self.traces.append(dict(label=item.label, hex=raw.hex(), invalid=invalid, tokens=tokens,
                                reports=reports, supplied_span_offset=item.stream_offset))

    def host_command(self, argv, directory, name, sanitized_run=False):
        """Adapter-only variant of the existing command limits, not a new runner API."""
        self.budget()
        as_limit = None if sanitized_run else 512 << 20
        def limit():
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
            resource.setrlimit(resource.RLIMIT_CPU, (20, 21))
            resource.setrlimit(resource.RLIMIT_FSIZE, (8 << 20, 8 << 20))
            if as_limit is not None:
                resource.setrlimit(resource.RLIMIT_AS, (as_limit, as_limit))
        receipt = dict(command=list(map(str, argv)), address_space_bytes=as_limit,
                       cpu_seconds=[20, 21], file_bytes=8 << 20, wall_seconds=45, status='running')
        start = time.monotonic()
        try:
            with (directory/(name+'.stdout')).open('wb') as out, (directory/(name+'.stderr')).open('wb') as err:
                result = subprocess.run(list(map(str, argv)), stdout=out, stderr=err,
                                        timeout=45, preexec_fn=limit)
            receipt['returncode'] = result.returncode
            require(result.returncode == 0, f'{name} exit {result.returncode}: {(directory/(name+".stderr")).read_text()[:3000]}')
            require((directory/(name+'.stderr')).stat().st_size == 0, name+' unexpected stderr')
            receipt['status'] = 'passed'
            return (directory/(name+'.stdout')).read_bytes()
        except Exception as error:
            receipt.update(status='failed', error=str(error)); raise
        finally:
            receipt['seconds'] = time.monotonic()-start
            (directory/(name+'.json')).write_text(json.dumps(receipt, indent=2)+'\n')
            self.budget(0)

    def differential(self):
        self.budget()
        d = self.host.parent
        d.mkdir()
        cxx = parse_cxx(os.environ.get('CXX', 'g++'))
        flags = selected_flag_vectors(os.environ)['IR_TEST_CXXFLAGS']
        (d/'tool.json').write_text(json.dumps(tool_record(cxx), indent=2)+'\n')
        (d/'traces.json').write_text(json.dumps(self.traces, indent=2)+'\n')
        (d/'corpus.hex').write_text(''.join(item['hex']+'\n' for item in self.traces))
        self.host_command([cxx, *flags, '-I', self.root/'compiler',
                           self.root/'tests/compiler/token_scan_host.cpp', '-o', self.host], d, 'build')
        sanitized = any(flag.startswith('-fsanitize=') for flag in flags)
        output = self.host_command([self.host, d/'corpus.hex'], d, 'native', sanitized_run=sanitized)
        rows = iter(output.decode('ascii').splitlines())
        valid = invalid = 0
        for index, item in enumerate(self.traces):
            header = next(rows, '').split()
            if item['invalid']:
                require(header == ['invalid', str(index)], 'host must reject invalid stream independently of recovery')
                invalid += 1
            else:
                require(header == ['valid', str(index), str(len(item['tokens']))], 'host valid token count/header mismatch')
                tokens = []
                for _ in item['tokens']:
                    line, spelling = next(rows, '').split()
                    tokens.append((int(line), spelling))
                require(tokens == item['tokens'], 'unchanged C-locale host spelling/line differential mismatch')
                valid += 1
        require(next(rows, None) is None, 'host adapter emitted unexpected suffix')
        (d/'receipt.json').write_text(json.dumps(dict(status='passed', locale='C', valid_streams=valid,
                                                    invalid_streams=invalid, binary_sha256=harness.sha(self.host)), indent=2)+'\n')
        print(f'PASS unchanged host lexer: {valid} valid spelling/line streams; {invalid} separate error controls', flush=True)
        return valid, invalid

    def example(self):
        self.budget()
        d = self.output/'example'
        d.mkdir()
        source = self.root/'examples/token_scan.au'
        (d/'input.au').write_bytes(source.read_bytes())
        receipt = dict(source_sha256=harness.sha(source), expected=42, status='running')
        try:
            self.command([self.compiler, '--module-root', self.root/'library',
                          d/'input.au', '-o', d/'compiled.s'], d, 'compiler')
            entry = ['.text', '.globl _start', '_start:', 'call test', 'pushq %rax',
                     'movq $1,%rax', 'movq $1,%rdi', 'movq %rsp,%rsi', 'movq $8,%rdx',
                     'syscall', 'addq $8,%rsp', 'movq $60,%rax', 'xorq %rdi,%rdi',
                     'syscall', '.section .note.GNU-stack,"",@progbits']
            (d/'entry.s').write_text('\n'.join(entry)+'\n')
            self.command(['as', '--64', d/'compiled.s', '-o', d/'program.o'], d, 'assemble')
            self.command(['as', '--64', d/'entry.s', '-o', d/'entry.o'], d, 'entry')
            undefined = self.command(['nm', '-u', d/'program.o'], d, 'undefined-object')
            require(not undefined.strip(), 'example has unresolved target runtime imports')
            self.command(['ld', '-o', d/'program', d/'entry.o', d/'program.o'], d, 'link')
            output = self.command([d/'program'], d, 'native')
            require(output == (42).to_bytes(8, 'little', signed=True), 'example full-i64 answer must equal 42')
            receipt.update(status='passed', observed=42, output_sha256=hashlib.sha256(output).hexdigest())
        except Exception as error:
            receipt.update(status='failed', error=str(error)); raise
        finally:
            (d/'receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
        print('PASS unchanged token_scan example: complete i64 answer 42', flush=True)

    def mutation_controls(self, source):
        # Exact anchors are established against the implementation before admission.
        # Each copy retains the original module API and compiles/links/runs normally;
        # a mere compiler failure cannot count as detection.
        controls = mutation_specs(source)
        for label, mutant, case in controls:
            d = self.output/('module-copy-'+label)/'std'
            d.mkdir(parents=True)
            (d/'token_scan.au').write_text(mutant)
            (d.parent/'mutation.json').write_text(json.dumps(dict(label=label,
                 original_sha256=hashlib.sha256(source.encode()).hexdigest(),
                 mutant_sha256=harness.sha(d/'token_scan.au')), indent=2)+'\n')
            self.batch([case], module_root=d.parent, mutation=label)
            self.verify_inputs()


def mutation_specs(source):
    # Fail closed if an implementation rewrite invalidates a reviewed anchor.
    bad_lf = Test('forged LF shape mutation detector',
        f'const {RESULT} report={RESULT}(std::TokenStatus::success,std::TokenKind::identifier,1,1,2,2);'+observe(),
        BAD_SHAPE)
    anchors = (
        ('pair', '(first == 45u8 && second == 62u8)', '(first == 45u8 && second == 61u8)',
         source_case(Case('operator-pair mutation detector', b'->'))),
        ('lf', 'skipped = skipped + 1;', 'skipped = skipped + 0;',
         source_case(Case('LF accounting mutation detector', b'\nA'))),
        ('invalid-progress', 'TokenKind::none, offset + begin, 1, begin + 1, skipped);',
         'TokenKind::none, offset + begin, 1, begin + 2, skipped);',
         source_case(Case('single invalid-byte progress mutation detector', b' \xffZ'))),
        ('window', 'if (count > bytes.size() - offset)', 'if (count >= bytes.size() - offset)',
         source_case(Case('final inclusive window mutation detector', b'A'))),
        ('forged-lf', 'if (line_feeds > consumed_length - token_length)', 'if (line_feeds < 0)', bad_lf),
    )
    controls = []
    for label, old, new, case in anchors:
        require(source.count(old) == 1, 'mutation anchor missing or ambiguous: '+label)
        controls.append((label, source.replace(old, new, 1), case))
    return controls


def self_test():
    require(model(b' \nA9_\xff', 0, 6) == (0, 1, 2, 3, 5, 1), 'word stops before unsupported suffix')
    require(model(b' \n\xffZ', 0, 4) == (2, 0, 2, 1, 3, 1), 'invalid byte consumes trivia and one byte')
    require(model(b'//\0\xff\r\n\nZ', 0, 8) == (0, 1, 7, 1, 8, 2), 'opaque comment and LF')
    require(model(b'//', 0, 1) == (0, 3, 0, 1, 1, 0), 'single slash final window')
    require(model(b'//', 0, 2) == (1, 0, 2, 0, 2, 0), 'comment wins over punctuation')
    require(model(b'->', 0, 1) == (0, 3, 0, 1, 1, 0), 'pair clipped to punctuation')
    require(model(b'A', 1, 0) == (1, 0, 1, 0, 0, 0), 'endpoint EOF offset')
    require(model(b'', 0, 0) == (1, 0, 0, 0, 0, 0), 'genuine empty span')
    require(model(b'\xff', MAX, MAX) == BAD_SHAPE, 'signed invalid window precedence')
    require(report_model(0, 1, 0, 1, 2, 0) == BAD_SHAPE, 'negative inferred start')
    require(report_model(0, 1, 1, 1, 2, 2) == BAD_SHAPE, 'LF belongs only to trivia')
    require(report_model(1, 0, 4096, 0, 4096, 4096) == (1, 0, 4096, 0, 4096, 4096), 'maximal EOF shape')
    require(trace_model(b'Z\xff\n')[-6:] == (1, 0, 3, 0, 1, 1), 'recovery final EOF trivia')


def batches(items):
    batch = []
    size = 0
    for item in items:
        cost = len(item.body.encode())+len(item.helper.encode())+120
        require(cost < 62000, 'single generated test source exceeds batch allowance')
        if batch and (len(batch) >= 16 or size+cost > 62000):
            yield batch
            batch, size = [], 0
        batch.append(item)
        size += cost
    if batch:
        yield batch


def all_tests():
    return itertools.chain(map(source_case, cases()), expired_owner_reports(), public_reports(), sequences())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', type=pathlib.Path)
    harness.add_identity_arguments(parser)
    parser.add_argument('--repo-root', type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2])
    parser.add_argument('--artifacts', type=pathlib.Path)
    parser.add_argument('--budget-root', type=pathlib.Path)
    parser.add_argument('--budget-mib', type=int, default=128)
    parser.add_argument('--sanitized-compiler', action='store_true')
    parser.add_argument('--self-test-only', action='store_true')
    parser.add_argument('--describe', action='store_true', help='generate/count source only; no compiler or native commands')
    args = parser.parse_args()
    harness.validate_identity_selection(args, preflight=args.self_test_only or args.describe)
    self_test()
    if args.self_test_only:
        print('PASS token regex/shape oracle controls'); return
    if args.describe:
        groups = list(batches(all_tests()))
        print(json.dumps(dict(cases=sum(len(group) for group in groups), batches=len(groups),
                              complete_i64_observations=sum(len(item.expected) for group in groups for item in group),
                              largest_batch_source_estimate=max(sum(len(item.body)+len(item.helper)+120 for item in group) for group in groups),
                              host_streams=sum(item.stream is not None for group in groups for item in group),
                              budget_mib=args.budget_mib, per_command_wall_seconds=45,
                              per_command_cpu_seconds=[20,21], per_file_mib=8), indent=2)); return
    require(args.compiler is not None and args.artifacts is not None, 'compiler and fresh artifacts required')
    require(32 <= args.budget_mib <= 1024, 'owned artifact budget must be 32..1024 MiB')
    # A Make fresh build inherits these validated flags. Preserve the explicit
    # switch for a reviewed instrumented prebuilt whose flags are not inherited.
    build_flags = selected_flag_vectors(os.environ)['CXXFLAGS']
    args.sanitized_compiler = args.sanitized_compiler or any(
        flag.startswith('-fsanitize=') for flag in build_flags)
    identity = harness.resolve_identity(args, args.compiler, args.repo_root)
    source = (args.repo_root/'library/std/token_scan.au').read_text()
    fields, helpers = private_names(source)
    mutation_specs(source)  # Reject stale controls before allocating/starting native work.
    suite = Suite(args, identity)
    manifest = dict(compiler_identity=identity.record(), compiler_sha256=suite.pin,
                    inputs=suite.inputs, python=sys.version, optimized=not __debug__, status='running')
    try:
        for group in batches(all_tests()):
            suite.batch(group)
        for item in rejections(fields, helpers):
            suite.reject(*item)
        suite.example()
        valid, invalid = suite.differential()
        suite.mutation_controls(source)
        suite.verify_inputs()
        identity.verify()
        manifest.update(status='passed', cases=suite.count, batches=suite.batches,
                        full_i64_observations=suite.observations, rejections=suite.rejections,
                        host_valid_streams=valid, host_invalid_streams=invalid,
                        detected_semantic_mutations=suite.mutations, native_example=42)
        print(f'PASS token scan: {suite.count} cases; {suite.observations} full i64 observations; '
              f'{suite.rejections} rejection controls; {suite.mutations} native mutation detections', flush=True)
    except Exception as error:
        manifest.update(status='failed', error=str(error)); raise
    finally:
        manifest.update(completed_cases=suite.count, completed_rejections=suite.rejections,
                        completed_mutations=suite.mutations, allocated_bytes=suite.budget(0))
        (suite.output/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')


if __name__ == '__main__':
    main()
