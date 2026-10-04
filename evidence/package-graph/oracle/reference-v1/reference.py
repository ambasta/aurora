"""Independent graph specification; frozen before graph.au has been read.

Reference choices: byte-line splitting, decimal canonicalization by roundtrip,
and searching all vertex permutations in lexical order. No production scanners
or graph algorithm are imported. Python unbounded integers define range checks.
"""
from dataclasses import dataclass
from itertools import permutations
U32=(1<<32)-1
STATUSES=('success','invalid_count','out_of_range','malformed','duplicate_package','missing_package','version_mismatch','cycle','index_out_of_range')
@dataclass(frozen=True)
class Identity:
    name: bytes
    version: tuple

def identity(token):
    chunks=token.split(b'@')
    if len(chunks)!=2:return None
    name,numbers=chunks
    if not 1<=len(name)<=24 or not 97<=name[0]<=122:return None
    if name.endswith(b'-') or b'--' in name:return None
    if any(not (97<=c<=122 or 48<=c<=57 or c==45) for c in name):return None
    parts=numbers.split(b'.')
    if len(parts)!=3:return None
    values=[]
    for text in parts:
        if not text or any(not 48<=c<=57 for c in text):return None
        number=int(text)
        if number>U32 or str(number).encode()!=text:return None
        values.append(number)
    return Identity(name,tuple(values))

def manifest(data):
    if not 37<=len(data)<=615:return None
    lines=data.split(b'\n')
    if len(lines)<4 or lines[:1]!=[b'aurora-package 1'] or lines[-2:]!=[b'end',b'']:return None
    if not lines[1].startswith(b'package '):return None
    root=identity(lines[1][8:])
    if root is None:return None
    dep_lines=lines[2:-2]
    if len(dep_lines)>8:return None
    deps=[]
    for line in dep_lines:
        if not line.startswith(b'depends '):return None
        parsed=identity(line[8:])
        if parsed is None:return None
        deps.append(parsed)
    if len({x.name for x in (root,*deps)})!=len(deps)+1:return None
    return root,tuple(deps)

def graph(data,offsets,lengths,count):
    if not 0<=count<=8:return 'invalid_count',(),()
    windows=list(zip(offsets[:count],lengths[:count]))
    if any(o<0 or n<0 or o+n>len(data) for o,n in windows):return 'out_of_range',(),()
    parsed=tuple(manifest(data[o:o+n]) for o,n in windows)
    if None in parsed:return 'malformed',(),()
    roots=tuple(x[0] for x in parsed)
    by_name={x.name:i for i,x in enumerate(roots)}
    if len(by_name)!=count:return 'duplicate_package',(),()
    pins=tuple((i,d) for i,(_,deps) in enumerate(parsed) for d in deps)
    if any(d.name not in by_name for _,d in pins):return 'missing_package',(),()
    if any(d.version!=roots[by_name[d.name]].version for _,d in pins):return 'version_mismatch',(),()
    edges=tuple((i,by_name[d.name]) for i,d in pins)
    # Exhaustive mathematical reference: the first valid full permutation in
    # canonical-name lexical order is the uniquely specified output sequence.
    for order in permutations(sorted(range(count),key=lambda i:roots[i].name)):
        ranks={vertex:rank for rank,vertex in enumerate(order)}
        if all(ranks[d]<ranks[i] for i,d in edges):return 'success',order,roots
    return 'cycle',(),()

def order_constructor(status,order,count):
    if status=='success' and not (0<=count<=8 and sorted(order[:count])==list(range(count)) and all(x==0 for x in order[count:])):
        return 'malformed'
    return status

def entry_constructor(status,ident,count,rank,index):
    if status=='success' and not (ident is not None and 1<=count<=8 and 0<=rank<count and 0<=index<count):
        return 'malformed'
    return status
