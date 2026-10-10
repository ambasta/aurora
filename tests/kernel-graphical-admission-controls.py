#!/usr/bin/env python3
"""Independent hostile combined-profile controls. Source prepared, not qualified.

No compiler, guest or subprocess is launched. All safety assertions use explicit
exceptions or unittest assertions and remain active under python -O.
"""

from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import sys
import struct
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "graphical_controls_target", ROOT / "scripts/kernel_graphical_console_admission.py"
)
graphical = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = graphical
spec.loader.exec_module(graphical)
decoder = graphical.load("graphical_controls_decoder", ROOT / "tests/kernel-uefi-owned-bytes-stack.py")


REFLECTION = (
    "aurora_reflect_size",
    "aurora_reflect_field_count",
    *(f"__au_reflect_s{module}_{field}" for module in (1, 2, 3, 4, 5, 6) for field in ("size", "field_count")),
)

# Independent frozen image006 fixtures: original bytes and objdump operands.
# Numeric code/data addresses are relocated by the fixture loader, separately
# from the checker. No compiler, disassembler, external file or subprocess runs.
PAIRED_LINKED_FIXTURES = {
    "root": """
0|4157|push|%r15
2|4156|push|%r14
4|4155|push|%r13
6|4154|push|%r12
8|55|push|%rbp
9|53|push|%rbx
a|4881ecb8000000|sub|$0xb8,%rsp
11|4c8b2f|mov|(%rdi),%r13
14|4c8b6708|mov|0x8(%rdi),%r12
18|488b4710|mov|0x10(%rdi),%rax
1c|4889742428|mov|%rsi,0x28(%rsp)
21|48894c2420|mov|%rcx,0x20(%rsp)
26|4c89442418|mov|%r8,0x18(%rsp)
2b|4c896c2448|mov|%r13,0x48(%rsp)
30|4c89642450|mov|%r12,0x50(%rsp)
35|4889442458|mov|%rax,0x58(%rsp)
3a|4885c9|test|%rcx,%rcx
3d|0f845d060000|je|+6a0
43|4c8b7c2418|mov|0x18(%rsp),%r15
48|4d85ff|test|%r15,%r15
4b|0f844f060000|je|+6a0
51|4885c0|test|%rax,%rax
54|0f8546060000|jne|+6a0
5a|488b442428|mov|0x28(%rsp),%rax
5f|4889fb|mov|%rdi,%rbx
62|4989d6|mov|%rdx,%r14
65|4889cd|mov|%rcx,%rbp
68|4889c7|mov|%rax,%rdi
6b|48890424|mov|%rax,(%rsp)
6f|e800000000|call|@layout
74|498d5424ff|lea|-0x1(%r12),%rdx
79|4883fa0f|cmp|$0xf,%rdx
7d|0f871d060000|ja|+6a0
83|3c01|cmp|$0x1,%al
85|0f8515060000|jne|+6a0
8b|488b0424|mov|(%rsp),%rax
8f|480500100100|add|$0x11000,%rax
95|4939c5|cmp|%rax,%r13
98|0f8502060000|jne|+6a0
9e|4d8b4e08|mov|0x8(%r14),%r9
a2|4983f907|cmp|$0x7,%r9
a6|0f86f4050000|jbe|+6a0
ac|498b3e|mov|(%r14),%rdi
af|31c0|xor|%eax,%eax
b1|31f6|xor|%esi,%esi
b3|66662e0f1f840000000000|data16|cs nopw 0x0(%rax,%rax,1)
be|6690|xchg|%ax,%ax
c0|0fb61407|movzbl|(%rdi,%rax,1),%edx
c4|8d0cc500000000|lea|0x0(,%rax,8),%ecx
cb|4883c001|add|$0x1,%rax
cf|48d3e2|shl|%cl,%rdx
d2|4809d6|or|%rdx,%rsi
d5|4883f808|cmp|$0x8,%rax
d9|75e5|jne|+c0
db|48b849464555524f5241|movabs|$0x41524f5255454649,%rax
e5|4839c6|cmp|%rax,%rsi
e8|0f85b2050000|jne|+6a0
ee|498d41f8|lea|-0x8(%r9),%rax
f2|4883f803|cmp|$0x3,%rax
f6|0f86a4050000|jbe|+6a0
fc|0fb64709|movzbl|0x9(%rdi),%eax
100|0fb6570a|movzbl|0xa(%rdi),%edx
104|48c1e008|shl|$0x8,%rax
108|48c1e210|shl|$0x10,%rdx
10c|4809d0|or|%rdx,%rax
10f|0fb65708|movzbl|0x8(%rdi),%edx
113|4809d0|or|%rdx,%rax
116|0fb6570b|movzbl|0xb(%rdi),%edx
11a|48c1e218|shl|$0x18,%rdx
11e|4809d0|or|%rdx,%rax
121|4883f806|cmp|$0x6,%rax
125|0f8575050000|jne|+6a0
12b|498d41f4|lea|-0xc(%r9),%rax
12f|4883f803|cmp|$0x3,%rax
133|0f8667050000|jbe|+6a0
139|0fb6470e|movzbl|0xe(%rdi),%eax
13d|0fb6570d|movzbl|0xd(%rdi),%edx
141|48c1e010|shl|$0x10,%rax
145|48c1e208|shl|$0x8,%rdx
149|4809d0|or|%rdx,%rax
14c|0fb6570c|movzbl|0xc(%rdi),%edx
150|4809d0|or|%rdx,%rax
153|0fb6570f|movzbl|0xf(%rdi),%edx
157|48c1e218|shl|$0x18,%rdx
15b|4809d0|or|%rdx,%rax
15e|483d80000000|cmp|$0x80,%rax
164|0f8536050000|jne|+6a0
16a|498d41f0|lea|-0x10(%r9),%rax
16e|4883f807|cmp|$0x7,%rax
172|0f8628050000|jbe|+6a0
178|31c0|xor|%eax,%eax
17a|31f6|xor|%esi,%esi
17c|0f1f4000|nopl|0x0(%rax)
180|0fb6540710|movzbl|0x10(%rdi,%rax,1),%edx
185|8d0cc500000000|lea|0x0(,%rax,8),%ecx
18c|4883c001|add|$0x1,%rax
190|48d3e2|shl|%cl,%rdx
193|4809d6|or|%rdx,%rsi
196|4883f808|cmp|$0x8,%rax
19a|75e4|jne|+180
19c|4881fe00001000|cmp|$0x100000,%rsi
1a3|0f85f7040000|jne|+6a0
1a9|498d41e8|lea|-0x18(%r9),%rax
1ad|4883f807|cmp|$0x7,%rax
1b1|0f86e9040000|jbe|+6a0
1b7|31c0|xor|%eax,%eax
1b9|31f6|xor|%esi,%esi
1bb|0fb6540718|movzbl|0x18(%rdi,%rax,1),%edx
1c0|8d0cc500000000|lea|0x0(,%rax,8),%ecx
1c7|4883c001|add|$0x1,%rax
1cb|48d3e2|shl|%cl,%rdx
1ce|4809d6|or|%rdx,%rsi
1d1|4883f808|cmp|$0x8,%rax
1d5|75e4|jne|+1bb
1d7|48393424|cmp|%rsi,(%rsp)
1db|0f85bf040000|jne|+6a0
1e1|4983e920|sub|$0x20,%r9
1e5|4983f907|cmp|$0x7,%r9
1e9|0f86b1040000|jbe|+6a0
1ef|31c0|xor|%eax,%eax
1f1|31f6|xor|%esi,%esi
1f3|0fb6540720|movzbl|0x20(%rdi,%rax,1),%edx
1f8|8d0cc500000000|lea|0x0(,%rax,8),%ecx
1ff|4883c001|add|$0x1,%rax
203|48d3e2|shl|%cl,%rdx
206|4809d6|or|%rdx,%rsi
209|4883f808|cmp|$0x8,%rax
20d|75e4|jne|+1f3
20f|4883ee01|sub|$0x1,%rsi
213|4881feffff0000|cmp|$0xffff,%rsi
21a|0f8780040000|ja|+6a0
220|ba08000000|mov|$0x8,%edx
225|be28000000|mov|$0x28,%esi
22a|4c89f7|mov|%r14,%rdi
22d|e800000000|call|@bytes
232|4883e828|sub|$0x28,%rax
236|483dd8000000|cmp|$0xd8,%rax
23c|0f875e040000|ja|+6a0
242|ba04000000|mov|$0x4,%edx
247|be30000000|mov|$0x30,%esi
24c|4c89f7|mov|%r14,%rdi
24f|e800000000|call|@bytes
254|4883e801|sub|$0x1,%rax
258|0f8542040000|jne|+6a0
25e|ba04000000|mov|$0x4,%edx
263|be34000000|mov|$0x34,%esi
268|4c89f7|mov|%r14,%rdi
26b|e800000000|call|@bytes
270|4883e801|sub|$0x1,%rax
274|4883f802|cmp|$0x2,%rax
278|0f8722040000|ja|+6a0
27e|ba08000000|mov|$0x8,%edx
283|be38000000|mov|$0x38,%esi
288|4c89f7|mov|%r14,%rdi
28b|e800000000|call|@bytes
290|4989c1|mov|%rax,%r9
293|488d40ff|lea|-0x1(%rax),%rax
297|4c894c2408|mov|%r9,0x8(%rsp)
29c|483dffff0100|cmp|$0x1ffff,%rax
2a2|0f87f8030000|ja|+6a0
2a8|ba08000000|mov|$0x8,%edx
2ad|be50000000|mov|$0x50,%esi
2b2|4c89f7|mov|%r14,%rdi
2b5|e800000000|call|@bytes
2ba|4c8b4c2408|mov|0x8(%rsp),%r9
2bf|4889442410|mov|%rax,0x10(%rsp)
2c4|4c39c8|cmp|%r9,%rax
2c7|0f82d3030000|jb|+6a0
2cd|ba08000000|mov|$0x8,%edx
2d2|be40000000|mov|$0x40,%esi
2d7|4c89f7|mov|%r14,%rdi
2da|e800000000|call|@bytes
2df|4885c0|test|%rax,%rax
2e2|0f84b8030000|je|+6a0
2e8|a9ff0f0000|test|$0xfff,%eax
2ed|4889442408|mov|%rax,0x8(%rsp)
2f2|0f85a8030000|jne|+6a0
2f8|ba08000000|mov|$0x8,%edx
2fd|be48000000|mov|$0x48,%esi
302|4c89f7|mov|%r14,%rdi
305|e800000000|call|@bytes
30a|488b4c2410|mov|0x10(%rsp),%rcx
30f|4c8b4c2408|mov|0x8(%rsp),%r9
314|4839c1|cmp|%rax,%rcx
317|0f92c2|setb|%dl
31a|4c39c8|cmp|%r9,%rax
31d|400f92c6|setb|%sil
321|09f2|or|%esi,%edx
323|4881f900000200|cmp|$0x20000,%rcx
32a|400f97c6|seta|%sil
32e|4008f2|or|%sil,%dl
331|0f8569030000|jne|+6a0
337|4809c1|or|%rax,%rcx
33a|f7c1ff0f0000|test|$0xfff,%ecx
340|0f855a030000|jne|+6a0
346|ba08000000|mov|$0x8,%edx
34b|be58000000|mov|$0x58,%esi
350|4c89f7|mov|%r14,%rdi
353|e800000000|call|@bytes
358|4939c5|cmp|%rax,%r13
35b|0f853f030000|jne|+6a0
361|ba08000000|mov|$0x8,%edx
366|be60000000|mov|$0x60,%esi
36b|4c89f7|mov|%r14,%rdi
36e|e800000000|call|@bytes
373|4939c4|cmp|%rax,%r12
376|0f8524030000|jne|+6a0
37c|ba08000000|mov|$0x8,%edx
381|be68000000|mov|$0x68,%esi
386|4c89f7|mov|%r14,%rdi
389|e800000000|call|@bytes
38e|4c8b2c24|mov|(%rsp),%r13
392|4889c2|mov|%rax,%rdx
395|498d8500200200|lea|0x22000(%r13),%rax
39c|4839c2|cmp|%rax,%rdx
39f|0f85fb020000|jne|+6a0
3a5|ba08000000|mov|$0x8,%edx
3aa|be70000000|mov|$0x70,%esi
3af|4c89f7|mov|%r14,%rdi
3b2|e800000000|call|@bytes
3b7|4885c0|test|%rax,%rax
3ba|0f84e0020000|je|+6a0
3c0|ba08000000|mov|$0x8,%edx
3c5|be78000000|mov|$0x78,%esi
3ca|4c89f7|mov|%r14,%rdi
3cd|e800000000|call|@bytes
3d2|4889c2|mov|%rax,%rdx
3d5|498d8500000e00|lea|0xe0000(%r13),%rax
3dc|4839c2|cmp|%rax,%rdx
3df|0f85bb020000|jne|+6a0
3e5|4c3b6d00|cmp|0x0(%rbp),%r13
3e9|0f85b1020000|jne|+6a0
3ef|4d3b6f30|cmp|0x30(%r15),%r13
3f3|0f85a7020000|jne|+6a0
3f9|8b4d08|mov|0x8(%rbp),%ecx
3fc|498b5718|mov|0x18(%r15),%rdx
400|498b07|mov|(%r15),%rax
403|8d71e0|lea|-0x20(%rcx),%esi
406|4889542430|mov|%rdx,0x30(%rsp)
40b|83fe14|cmp|$0x14,%esi
40e|0f878c020000|ja|+6a0
414|4885c0|test|%rax,%rax
417|0f8483020000|je|+6a0
41d|488d72ff|lea|-0x1(%rdx),%rsi
421|4881feffff2f00|cmp|$0x2fffff,%rsi
428|0f8772020000|ja|+6a0
42e|4889c5|mov|%rax,%rbp
431|4809d5|or|%rdx,%rbp
434|81e5ff0f0000|and|$0xfff,%ebp
43a|0f8560020000|jne|+6a0
440|498b7f08|mov|0x8(%r15),%rdi
444|4839d7|cmp|%rdx,%rdi
447|0f8253020000|jb|+6a0
44d|be01000000|mov|$0x1,%esi
452|48d3e6|shl|%cl,%rsi
455|4889f1|mov|%rsi,%rcx
458|4839f0|cmp|%rsi,%rax
45b|0f833f020000|jae|+6a0
461|4829c1|sub|%rax,%rcx
464|4839f9|cmp|%rdi,%rcx
467|0f8233020000|jb|+6a0
46d|4981fdffffefff|cmp|$0xffffffffffefffff,%r13
474|0f8726020000|ja|+6a0
47a|488d0c10|lea|(%rax,%rdx,1),%rcx
47e|4939cd|cmp|%rcx,%r13
481|7310|jae|+493
483|498db500001000|lea|0x100000(%r13),%rsi
48a|4839f0|cmp|%rsi,%rax
48d|0f820d020000|jb|+6a0
493|beff0fe0fe|mov|$0xfee00fff,%esi
498|4839c6|cmp|%rax,%rsi
49b|7210|jb|+4ad
49d|4881eeff0f0000|sub|$0xfff,%rsi
4a4|4839ce|cmp|%rcx,%rsi
4a7|0f82f3010000|jb|+6a0
4ad|beff0fc0fe|mov|$0xfec00fff,%esi
4b2|4839c6|cmp|%rax,%rsi
4b5|7210|jb|+4c7
4b7|4881eeff0f0000|sub|$0xfff,%rsi
4be|4839ce|cmp|%rcx,%rsi
4c1|0f82d9010000|jb|+6a0
4c7|be000000e0|mov|$0xe0000000,%esi
4cc|4839ce|cmp|%rcx,%rsi
4cf|730e|jae|+4df
4d1|b9ffffffef|mov|$0xefffffff,%ecx
4d6|4839c1|cmp|%rax,%rcx
4d9|0f83c1010000|jae|+6a0
4df|488b3424|mov|(%rsp),%rsi
4e3|b8ff0fe0fe|mov|$0xfee00fff,%eax
4e8|4839f0|cmp|%rsi,%rax
4eb|0f8278010000|jb|+669
4f1|4881c600001000|add|$0x100000,%rsi
4f8|482dff0f0000|sub|$0xfff,%rax
4fe|4839f0|cmp|%rsi,%rax
501|0f8299010000|jb|+6a0
507|488d542460|lea|0x60(%rsp),%rdx
50c|488d442430|lea|0x30(%rsp),%rax
511|b910000000|mov|$0x10,%ecx
516|be18000000|mov|$0x18,%esi
51b|4889942488000000|mov|%rdx,0x88(%rsp)
523|488d542420|lea|0x20(%rsp),%rdx
528|4c8d6c2438|lea|0x38(%rsp),%r13
52d|4889df|mov|%rbx,%rdi
530|4889442460|mov|%rax,0x60(%rsp)
535|4c8d642448|lea|0x48(%rsp),%r12
53a|488d442428|lea|0x28(%rsp),%rax
53f|4889942490000000|mov|%rdx,0x90(%rsp)
547|488d542418|lea|0x18(%rsp),%rdx
54c|4c8d7c2478|lea|0x78(%rsp),%r15
551|4889942498000000|mov|%rdx,0x98(%rsp)
559|4c89ea|mov|%r13,%rdx
55c|4c89742468|mov|%r14,0x68(%rsp)
561|4889442470|mov|%rax,0x70(%rsp)
566|4c89642478|mov|%r12,0x78(%rsp)
56b|4c89ac2480000000|mov|%r13,0x80(%rsp)
573|48898424a0000000|mov|%rax,0xa0(%rsp)
57b|4c89b424a8000000|mov|%r14,0xa8(%rsp)
583|e800000000|call|@guard
588|84c0|test|%al,%al
58a|0f8410010000|je|+6a0
590|b918000000|mov|$0x18,%ecx
595|4c89e2|mov|%r12,%rdx
598|be18000000|mov|$0x18,%esi
59d|4889df|mov|%rbx,%rdi
5a0|e800000000|call|@guard
5a5|84c0|test|%al,%al
5a7|0f84f3000000|je|+6a0
5ad|b938000000|mov|$0x38,%ecx
5b2|4c89fa|mov|%r15,%rdx
5b5|be18000000|mov|$0x18,%esi
5ba|4889df|mov|%rbx,%rdi
5bd|e800000000|call|@guard
5c2|84c0|test|%al,%al
5c4|0f84d6000000|je|+6a0
5ca|b910000000|mov|$0x10,%ecx
5cf|4c89ea|mov|%r13,%rdx
5d2|be18000000|mov|$0x18,%esi
5d7|4c89e7|mov|%r12,%rdi
5da|e800000000|call|@guard
5df|84c0|test|%al,%al
5e1|0f84b9000000|je|+6a0
5e7|b938000000|mov|$0x38,%ecx
5ec|4c89fa|mov|%r15,%rdx
5ef|be18000000|mov|$0x18,%esi
5f4|4c89e7|mov|%r12,%rdi
5f7|e800000000|call|@guard
5fc|84c0|test|%al,%al
5fe|0f849c000000|je|+6a0
604|b938000000|mov|$0x38,%ecx
609|4c89fa|mov|%r15,%rdx
60c|be10000000|mov|$0x10,%esi
611|4c89ef|mov|%r13,%rdi
614|e800000000|call|@guard
619|84c0|test|%al,%al
61b|0f847f000000|je|+6a0
621|4c89e8|mov|%r13,%rax
624|c60000|movb|$0x0,(%rax)
627|4883c001|add|$0x1,%rax
62b|4c39e0|cmp|%r12,%rax
62e|75f4|jne|+624
630|488b5c2448|mov|0x48(%rsp),%rbx
635|4531c0|xor|%r8d,%r8d
638|b903000000|mov|$0x3,%ecx
63d|4c89fe|mov|%r15,%rsi
640|4c89ff|mov|%r15,%rdi
643|4889da|mov|%rbx,%rdx
646|e800000000|call|@walk
64b|84c0|test|%al,%al
64d|7451|je|+6a0
64f|488b442450|mov|0x50(%rsp),%rax
654|31d2|xor|%edx,%edx
656|4839d0|cmp|%rdx,%rax
659|7459|je|+6b4
65b|41807c150000|cmpb|$0x0,0x0(%r13,%rdx,1)
661|743d|je|+6a0
663|4883c201|add|$0x1,%rdx
667|ebed|jmp|+656
669|48b80020000000a0ffff|movabs|$0xffffa00000002000,%rax
673|4801c2|add|%rax,%rdx
676|488b0424|mov|(%rsp),%rax
67a|4839d0|cmp|%rdx,%rax
67d|0f8384feffff|jae|+507
683|480500001000|add|$0x100000,%rax
689|4989c7|mov|%rax,%r15
68c|b8fdff0700|mov|$0x7fffd,%eax
691|48c1e02d|shl|$0x2d,%rax
695|4c39f8|cmp|%r15,%rax
698|0f8369feffff|jae|+507
69e|6690|xchg|%ax,%ax
6a0|31c0|xor|%eax,%eax
6a2|4881c4b8000000|add|$0xb8,%rsp
6a9|5b|pop|%rbx
6aa|5d|pop|%rbp
6ab|415c|pop|%r12
6ad|415d|pop|%r13
6af|415e|pop|%r14
6b1|415f|pop|%r15
6b3|c3|ret|
6b4|4c8b7c2428|mov|0x28(%rsp),%r15
6b9|4c89f6|mov|%r14,%rsi
6bc|4889ef|mov|%rbp,%rdi
6bf|4889542408|mov|%rdx,0x8(%rsp)
6c4|e800000000|call|@flags
6c9|4a8d4c3d00|lea|0x0(%rbp,%r15,1),%rcx
6ce|4c89e7|mov|%r12,%rdi
6d1|4989c5|mov|%rax,%r13
6d4|4889ce|mov|%rcx,%rsi
6d7|48890c24|mov|%rcx,(%rsp)
6db|e800000000|call|@entry
6e0|4d85ed|test|%r13,%r13
6e3|488b542408|mov|0x8(%rsp),%rdx
6e8|740b|je|+6f5
6ea|488b0c24|mov|(%rsp),%rcx
6ee|4883e09f|and|$0xffffffffffffff9f,%rax
6f2|4909cd|or|%rcx,%r13
6f5|4c39e8|cmp|%r13,%rax
6f8|75a6|jne|+6a0
6fa|4881c500100000|add|$0x1000,%rbp
701|4881fd00001000|cmp|$0x100000,%rbp
708|75af|jne|+6b9
70a|4889d6|mov|%rdx,%rsi
70d|4889df|mov|%rbx,%rdi
710|e800000000|call|@window
715|4885c0|test|%rax,%rax
718|7486|je|+6a0
71a|beffff0100|mov|$0x1ffff,%esi
71f|4c89e7|mov|%r12,%rdi
722|48c1e62f|shl|$0x2f,%rsi
726|e800000000|call|@entry
72b|4885c0|test|%rax,%rax
72e|0f856cffffff|jne|+6a0
734|bef9ff0f00|mov|$0xffff9,%esi
739|4c89e7|mov|%r12,%rdi
73c|48c1e62c|shl|$0x2c,%rsi
740|e800000000|call|@entry
745|48ba1b00e0fe00000080|movabs|$0x80000000fee0001b,%rdx
74f|4883e09f|and|$0xffffffffffffff9f,%rax
753|4839d0|cmp|%rdx,%rax
756|0f8544ffffff|jne|+6a0
75c|488b5c2430|mov|0x30(%rsp),%rbx
761|4c8b742418|mov|0x18(%rsp),%r14
766|4531ed|xor|%r13d,%r13d
769|49b80010000000a0ffff|movabs|$0xffffa00000001000,%r8
773|48bd00f0ffffff5f0000|movabs|$0x5ffffffff000,%rbp
77d|49bf1b00000000000080|movabs|$0x800000000000001b,%r15
787|4939dd|cmp|%rbx,%r13
78a|7359|jae|+7e5
78c|4b8d740500|lea|0x0(%r13,%r8,1),%rsi
791|4c89e7|mov|%r12,%rdi
794|48893424|mov|%rsi,(%rsp)
798|e800000000|call|@entry
79d|488b3424|mov|(%rsp),%rsi
7a1|49b80010000000a0ffff|movabs|$0xffffa00000001000,%r8
7ab|4883e09f|and|$0xffffffffffffff9f,%rax
7af|4889c2|mov|%rax,%rdx
7b2|48b8ff0f000000a0ffff|movabs|$0xffffa00000000fff,%rax
7bc|4839f0|cmp|%rsi,%rax
7bf|735f|jae|+820
7c1|4d3b6e18|cmp|0x18(%r14),%r13
7c5|7359|jae|+820
7c7|498b06|mov|(%r14),%rax
7ca|4801e8|add|%rbp,%rax
7cd|4801f0|add|%rsi,%rax
7d0|4c09f8|or|%r15,%rax
7d3|4839c2|cmp|%rax,%rdx
7d6|0f85c4feffff|jne|+6a0
7dc|4981c500100000|add|$0x1000,%r13
7e3|eba2|jmp|+787
7e5|befdff0700|mov|$0x7fffd,%esi
7ea|4c89e7|mov|%r12,%rdi
7ed|48c1e62d|shl|$0x2d,%rsi
7f1|e800000000|call|@entry
7f6|4885c0|test|%rax,%rax
7f9|0f85a1feffff|jne|+6a0
7ff|48b80010000000a0ffff|movabs|$0xffffa00000001000,%rax
809|4c89e7|mov|%r12,%rdi
80c|488d3403|lea|(%rbx,%rax,1),%rsi
810|e800000000|call|@entry
815|4885c0|test|%rax,%rax
818|0f94c0|sete|%al
81b|e982feffff|jmp|+6a2
820|31c0|xor|%eax,%eax
822|ebaf|jmp|+7d3
""",
    "walk": """
0|4157|push|%r15
2|4989d3|mov|%rdx,%r11
5|4156|push|%r14
7|4155|push|%r13
9|4154|push|%r12
b|55|push|%rbp
c|53|push|%rbx
d|4883ec48|sub|$0x48,%rsp
11|488b07|mov|(%rdi),%rax
14|48897c2408|mov|%rdi,0x8(%rsp)
19|488b10|mov|(%rax),%rdx
1c|4939d3|cmp|%rdx,%r11
1f|0f82db010000|jb|+200
25|488b4008|mov|0x8(%rax),%rax
29|48c1e00c|shl|$0xc,%rax
2d|4801d0|add|%rdx,%rax
30|4939c3|cmp|%rax,%r11
33|0f83c7010000|jae|+200
39|41f7c3ff0f0000|test|$0xfff,%r11d
40|0f85ba010000|jne|+200
46|4c89d8|mov|%r11,%rax
49|4829d0|sub|%rdx,%rax
4c|488b542408|mov|0x8(%rsp),%rdx
51|48c1e80c|shr|$0xc,%rax
55|488b5208|mov|0x8(%rdx),%rdx
59|803c0200|cmpb|$0x0,(%rdx,%rax,1)
5d|0f859d010000|jne|+200
63|c6040201|movb|$0x1,(%rdx,%rax,1)
67|8d44c90c|lea|0xc(%rcx,%rcx,8),%eax
6b|4189c9|mov|%ecx,%r9d
6e|4531e4|xor|%r12d,%r12d
71|49c7c5ffffffff|mov|$0xffffffffffffffff,%r13
78|89c1|mov|%eax,%ecx
7a|89442438|mov|%eax,0x38(%rsp)
7e|4d89da|mov|%r11,%r10
81|49d3e5|shl|%cl,%r13
84|4889742428|mov|%rsi,0x28(%rsp)
89|4c89442410|mov|%r8,0x10(%rsp)
8e|4d89ee|mov|%r13,%r14
91|e99f000000|jmp|+135
96|662e0f1f840000000000|cs|nopw 0x0(%rax,%rax,1)
a0|4585c9|test|%r9d,%r9d
a3|0f856f010000|jne|+218
a9|488b7c2408|mov|0x8(%rsp),%rdi
ae|44894c2420|mov|%r9d,0x20(%rsp)
b3|4c89542418|mov|%r10,0x18(%rsp)
b8|488b4728|mov|0x28(%rdi),%rax
bc|488b00|mov|(%rax),%rax
bf|4939c0|cmp|%rax,%r8
c2|0f8238010000|jb|+200
c8|488d9000001000|lea|0x100000(%rax),%rdx
cf|4939d0|cmp|%rdx,%r8
d2|0f8328010000|jae|+200
d8|488b7730|mov|0x30(%rdi),%rsi
dc|4c89c7|mov|%r8,%rdi
df|4c89442430|mov|%r8,0x30(%rsp)
e4|4829c7|sub|%rax,%rdi
e7|e800000000|call|@flags
ec|4885c0|test|%rax,%rax
ef|0f840b010000|je|+200
f5|4c8b442430|mov|0x30(%rsp),%r8
fa|4c8b542418|mov|0x18(%rsp),%r10
ff|448b4c2420|mov|0x20(%rsp),%r9d
104|4909c0|or|%rax,%r8
107|4939d8|cmp|%rbx,%r8
10a|0f85f0000000|jne|+200
110|66662e0f1f840000000000|data16|cs nopw 0x0(%rax,%rax,1)
11b|0f1f440000|nopl|0x0(%rax,%rax,1)
120|4983c401|add|$0x1,%r12
124|4983c208|add|$0x8,%r10
128|4981fc00020000|cmp|$0x200,%r12
12f|0f8423020000|je|+358
135|498b12|mov|(%r10),%rdx
138|4885d2|test|%rdx,%rdx
13b|74e3|je|+120
13d|0fb64c2438|movzbl|0x38(%rsp),%ecx
142|488b442410|mov|0x10(%rsp),%rax
147|4d89e0|mov|%r12,%r8
14a|4889d3|mov|%rdx,%rbx
14d|4883e39f|and|$0xffffffffffffff9f,%rbx
151|49d3e0|shl|%cl,%r8
154|4909c0|or|%rax,%r8
157|48b80000000000800000|movabs|$0x800000000000,%rax
161|4985c0|test|%rax,%r8
164|0f8436ffffff|je|+a0
16a|48be000000000000ffff|movabs|$0xffff000000000000,%rsi
174|4c09c6|or|%r8,%rsi
177|4989f7|mov|%rsi,%r15
17a|4585c9|test|%r9d,%r9d
17d|0f8598000000|jne|+21b
183|48b8000000000090ffff|movabs|$0xffff900000000000,%rax
18d|4839c6|cmp|%rax,%rsi
190|0f84aa010000|je|+340
196|488b442408|mov|0x8(%rsp),%rax
19b|488b4020|mov|0x20(%rax),%rax
19f|488b10|mov|(%rax),%rdx
1a2|48b8ff0f000000a0ffff|movabs|$0xffffa00000000fff,%rax
1ac|4839f0|cmp|%rsi,%rax
1af|0f83f4feffff|jae|+a9
1b5|41f7c0ff0f0000|test|$0xfff,%r8d
1bc|0f85e7feffff|jne|+a9
1c2|48b800f0ffffff5f0000|movabs|$0x5ffffffff000,%rax
1cc|488d0c06|lea|(%rsi,%rax,1),%rcx
1d0|483b4a18|cmp|0x18(%rdx),%rcx
1d4|0f83cffeffff|jae|+a9
1da|480302|add|(%rdx),%rax
1dd|48ba1b00000000000080|movabs|$0x800000000000001b,%rdx
1e7|4801f0|add|%rsi,%rax
1ea|4809d0|or|%rdx,%rax
1ed|4839c3|cmp|%rax,%rbx
1f0|0f842affffff|je|+120
1f6|662e0f1f840000000000|cs|nopw 0x0(%rax,%rax,1)
200|31c0|xor|%eax,%eax
202|4883c448|add|$0x48,%rsp
206|5b|pop|%rbx
207|5d|pop|%rbp
208|415c|pop|%r12
20a|415d|pop|%r13
20c|415e|pop|%r14
20e|415f|pop|%r15
210|c3|ret|
211|0f1f8000000000|nopl|0x0(%rax)
218|4d89c7|mov|%r8,%r15
21b|48b89f0f00000000f0ff|movabs|$0xfff0000000000f9f,%rax
225|4821d0|and|%rdx,%rax
228|4883f803|cmp|$0x3,%rax
22c|75d2|jne|+200
22e|48b8000000000080ffff|movabs|$0xffff800000000000,%rax
238|4c21f0|and|%r14,%rax
23b|4c39f8|cmp|%r15,%rax
23e|0f84b9000000|je|+2fd
244|48b8000000000090ffff|movabs|$0xffff900000000000,%rax
24e|4c21f0|and|%r14,%rax
251|4c39f8|cmp|%r15,%rax
254|0f84a3000000|je|+2fd
25a|488b442408|mov|0x8(%rsp),%rax
25f|4c8b6810|mov|0x10(%rax),%r13
263|48b80000000000a0ffff|movabs|$0xffffa00000000000,%rax
26d|498b4d00|mov|0x0(%r13),%rcx
271|480301|add|(%rcx),%rax
274|4c21f0|and|%r14,%rax
277|4c39f8|cmp|%r15,%rax
27a|7212|jb|+28e
27c|48b80010000000a0ffff|movabs|$0xffffa00000001000,%rax
286|4c21f0|and|%r14,%rax
289|4939c7|cmp|%rax,%r15
28c|736f|jae|+2fd
28e|4889542418|mov|%rdx,0x18(%rsp)
293|498b5d08|mov|0x8(%r13),%rbx
297|31ed|xor|%ebp,%ebp
299|4c89442420|mov|%r8,0x20(%rsp)
29e|4c89542430|mov|%r10,0x30(%rsp)
2a3|44894c243c|mov|%r9d,0x3c(%rsp)
2a8|eb1a|jmp|+2c4
2aa|660f1f440000|nopw|0x0(%rax,%rax,1)
2b0|4881c500100000|add|$0x1000,%rbp
2b7|4881fd00001000|cmp|$0x100000,%rbp
2be|0f843cffffff|je|+200
2c4|4889de|mov|%rbx,%rsi
2c7|4889ef|mov|%rbp,%rdi
2ca|e800000000|call|@flags
2cf|4885c0|test|%rax,%rax
2d2|74dc|je|+2b0
2d4|498b4510|mov|0x10(%r13),%rax
2d8|488b08|mov|(%rax),%rcx
2db|4801e9|add|%rbp,%rcx
2de|4889c8|mov|%rcx,%rax
2e1|4c21f0|and|%r14,%rax
2e4|4c39f8|cmp|%r15,%rax
2e7|75c7|jne|+2b0
2e9|488b542418|mov|0x18(%rsp),%rdx
2ee|4c8b442420|mov|0x20(%rsp),%r8
2f3|4c8b542430|mov|0x30(%rsp),%r10
2f8|448b4c243c|mov|0x3c(%rsp),%r9d
2fd|488b7c2428|mov|0x28(%rsp),%rdi
302|418d49ff|lea|-0x1(%r9),%ecx
306|4c89542420|mov|%r10,0x20(%rsp)
30b|48b800f0ffffffff0f00|movabs|$0xffffffffff000,%rax
315|4821c2|and|%rax,%rdx
318|44894c2418|mov|%r9d,0x18(%rsp)
31d|4889fe|mov|%rdi,%rsi
320|e800000000|call|@walk
325|448b4c2418|mov|0x18(%rsp),%r9d
32a|4c8b542420|mov|0x20(%rsp),%r10
32f|84c0|test|%al,%al
331|0f85e9fdffff|jne|+120
337|e9c4feffff|jmp|+200
33c|0f1f4000|nopl|0x0(%rax)
340|48b81b00e0fe00000080|movabs|$0x80000000fee0001b,%rax
34a|4839c3|cmp|%rax,%rbx
34d|0f84cdfdffff|je|+120
353|e9a8feffff|jmp|+200
358|b801000000|mov|$0x1,%eax
35d|e9a0feffff|jmp|+202
""",
    "layout": """
0|488d870000f0ff|lea|-0x100000(%rdi),%rax
7|ba0000e0ff|mov|$0xffe00000,%edx
c|4839c2|cmp|%rax,%rdx
f|7307|jae|+18
11|31c0|xor|%eax,%eax
13|c3|ret|
14|0f1f4000|nopl|0x0(%rax)
18|81e7ff0f0000|and|$0xfff,%edi
1e|75f1|jne|+11
20|4157|push|%r15
22|4156|push|%r14
24|4155|push|%r13
26|4154|push|%r12
28|55|push|%rbp
29|53|push|%rbx
2a|4881ecb8000000|sub|$0xb8,%rsp
31|48c744242800000000|movq|$0x0,0x28(%rsp)
3a|488d4c2410|lea|0x10(%rsp),%rcx
3f|48c744243000100800|movq|$0x81000,0x30(%rsp)
48|4889c8|mov|%rcx,%rax
4b|48c744243800100800|movq|$0x81000,0x38(%rsp)
54|48c744244000100000|movq|$0x1000,0x40(%rsp)
5d|48c744244800200800|movq|$0x82000,0x48(%rsp)
66|48c744245000100000|movq|$0x1000,0x50(%rsp)
6f|48c744245800400800|movq|$0x84000,0x58(%rsp)
78|48c744246000400000|movq|$0x4000,0x60(%rsp)
81|48c744246800900800|movq|$0x89000,0x68(%rsp)
8a|48c744247000400000|movq|$0x4000,0x70(%rsp)
93|48c744247800000b00|movq|$0xb0000,0x78(%rsp)
9c|48c784248000000000200000|movq|$0x2000,0x80(%rsp)
a8|48c784248800000000000c00|movq|$0xc0000,0x88(%rsp)
b4|48c784249000000000000100|movq|$0x10000,0x90(%rsp)
c0|48c784249800000000000900|movq|$0x90000,0x98(%rsp)
cc|48c78424a000000000000100|movq|$0x10000,0xa0(%rsp)
d8|48c78424a800000000000a00|movq|$0xa0000,0xa8(%rsp)
e4|48c78424b000000000000100|movq|$0x10000,0xb0(%rsp)
f0|48c744241000300800|movq|$0x83000,0x10(%rsp)
f9|48c744241800800800|movq|$0x88000,0x18(%rsp)
102|48c744242000d00800|movq|$0x8d000,0x20(%rsp)
10b|4c8b00|mov|(%rax),%r8
10e|4981f8ffff0f00|cmp|$0xfffff,%r8
115|0f8795000000|ja|+1b0
11b|41f7c0ff0f0000|test|$0xfff,%r8d
122|0f8588000000|jne|+1b0
128|ba00001000|mov|$0x100000,%edx
12d|4c29c2|sub|%r8,%rdx
130|4881faff0f0000|cmp|$0xfff,%rdx
137|7677|jbe|+1b0
139|4885ff|test|%rdi,%rdi
13c|0f84ea010000|je|+32c
142|49b9ffffffffff7f0000|movabs|$0x7fffffffffff,%r9
14c|4889ca|mov|%rcx,%rdx
14f|48bb0000000000800000|movabs|$0x800000000000,%rbx
159|eb41|jmp|+19c
15b|0f1f440000|nopl|0x0(%rax,%rax,1)
160|4989f3|mov|%rsi,%r11
163|4181e3ff0f0000|and|$0xfff,%r11d
16a|7544|jne|+1b0
16c|4989da|mov|%rbx,%r10
16f|4929f2|sub|%rsi,%r10
172|4981faff0f0000|cmp|$0xfff,%r10
179|7635|jbe|+1b0
17b|4d8d9000100000|lea|0x1000(%r8),%r10
182|4c39d6|cmp|%r10,%rsi
185|730c|jae|+193
187|4881c600100000|add|$0x1000,%rsi
18e|4939f0|cmp|%rsi,%r8
191|721d|jb|+1b0
193|4883c208|add|$0x8,%rdx
197|4839d0|cmp|%rdx,%rax
19a|7428|je|+1c4
19c|488b32|mov|(%rdx),%rsi
19f|4939f1|cmp|%rsi,%r9
1a2|73bc|jae|+160
1a4|66662e0f1f840000000000|data16|cs nopw 0x0(%rax,%rax,1)
1af|90|nop|
1b0|31c0|xor|%eax,%eax
1b2|4881c4b8000000|add|$0xb8,%rsp
1b9|5b|pop|%rbx
1ba|5d|pop|%rbp
1bb|415c|pop|%r12
1bd|415d|pop|%r13
1bf|415e|pop|%r14
1c1|415f|pop|%r15
1c3|c3|ret|
1c4|4883ff02|cmp|$0x2,%rdi
1c8|0f8550010000|jne|+31e
1ce|488d6c2428|lea|0x28(%rsp),%rbp
1d3|41bc00001000|mov|$0x100000,%r12d
1d9|4c8db424b8000000|lea|0xb8(%rsp),%r14
1e1|48bfffffffffff7f0000|movabs|$0x7fffffffffff,%rdi
1eb|4889ee|mov|%rbp,%rsi
1ee|488d5918|lea|0x18(%rcx),%rbx
1f2|49bd0000000000800000|movabs|$0x800000000000,%r13
1fc|4c8b0e|mov|(%rsi),%r9
1ff|4981f9ffff0f00|cmp|$0xfffff,%r9
206|77a8|ja|+1b0
208|4c8b4608|mov|0x8(%rsi),%r8
20c|4d85c0|test|%r8,%r8
20f|749f|je|+1b0
211|4c89c8|mov|%r9,%rax
214|4c09c0|or|%r8,%rax
217|a9ff0f0000|test|$0xfff,%eax
21c|7592|jne|+1b0
21e|48b80000000000800000|movabs|$0x800000000000,%rax
228|4c29c8|sub|%r9,%rax
22b|4c39c0|cmp|%r8,%rax
22e|7280|jb|+1b0
230|4c89e0|mov|%r12,%rax
233|4c29c8|sub|%r9,%rax
236|4c39c0|cmp|%r8,%rax
239|0f8271ffffff|jb|+1b0
23f|4d85db|test|%r11,%r11
242|746f|je|+2b3
244|4c890424|mov|%r8,(%rsp)
248|4889e8|mov|%rbp,%rax
24b|4f8d1401|lea|(%r9,%r8,1),%r10
24f|eb50|jmp|+2a1
251|0f1f8000000000|nopl|0x0(%rax)
258|4c8b4008|mov|0x8(%rax),%r8
25c|4d85c0|test|%r8,%r8
25f|0f844bffffff|je|+1b0
265|4989d7|mov|%rdx,%r15
268|4d09c7|or|%r8,%r15
26b|41f7c7ff0f0000|test|$0xfff,%r15d
272|0f8538ffffff|jne|+1b0
278|4d89ef|mov|%r13,%r15
27b|4929d7|sub|%rdx,%r15
27e|4d39c7|cmp|%r8,%r15
281|0f8229ffffff|jb|+1b0
287|4c39d2|cmp|%r10,%rdx
28a|730c|jae|+298
28c|4c01c2|add|%r8,%rdx
28f|4939d1|cmp|%rdx,%r9
292|0f8218ffffff|jb|+1b0
298|4883c010|add|$0x10,%rax
29c|4839c6|cmp|%rax,%rsi
29f|740e|je|+2af
2a1|488b10|mov|(%rax),%rdx
2a4|4839d7|cmp|%rdx,%rdi
2a7|0f8203ffffff|jb|+1b0
2ad|eba9|jmp|+258
2af|4c8b0424|mov|(%rsp),%r8
2b3|4889c8|mov|%rcx,%rax
2b6|488b10|mov|(%rax),%rdx
2b9|4839d7|cmp|%rdx,%rdi
2bc|0f82eefeffff|jb|+1b0
2c2|f7c2ff0f0000|test|$0xfff,%edx
2c8|0f85e2feffff|jne|+1b0
2ce|4d89ea|mov|%r13,%r10
2d1|4929d2|sub|%rdx,%r10
2d4|4981faff0f0000|cmp|$0xfff,%r10
2db|0f86cffeffff|jbe|+1b0
2e1|4f8d1401|lea|(%r9,%r8,1),%r10
2e5|4c39d2|cmp|%r10,%rdx
2e8|7310|jae|+2fa
2ea|4881c200100000|add|$0x1000,%rdx
2f1|4939d1|cmp|%rdx,%r9
2f4|0f82b6feffff|jb|+1b0
2fa|4883c008|add|$0x8,%rax
2fe|4839c3|cmp|%rax,%rbx
301|75b3|jne|+2b6
303|4883c610|add|$0x10,%rsi
307|4983c301|add|$0x1,%r11
30b|4939f6|cmp|%rsi,%r14
30e|0f85e8feffff|jne|+1fc
314|b801000000|mov|$0x1,%eax
319|e994feffff|jmp|+1b2
31e|4883c008|add|$0x8,%rax
322|bf02000000|mov|$0x2,%edi
327|e9dffdffff|jmp|+10b
32c|4883c008|add|$0x8,%rax
330|bf01000000|mov|$0x1,%edi
335|e9d1fdffff|jmp|+10b
""",
    "bytes": """
0|4531c0|xor|%r8d,%r8d
3|83fa08|cmp|$0x8,%edx
6|774c|ja|+54
8|488b4708|mov|0x8(%rdi),%rax
c|4839f0|cmp|%rsi,%rax
f|7243|jb|+54
11|89d1|mov|%edx,%ecx
13|4829f0|sub|%rsi,%rax
16|4839c8|cmp|%rcx,%rax
19|7239|jb|+54
1b|85d2|test|%edx,%edx
1d|7435|je|+54
1f|480337|add|(%rdi),%rsi
22|c1e203|shl|$0x3,%edx
25|31c9|xor|%ecx,%ecx
27|66662e0f1f840000000000|data16|cs nopw 0x0(%rax,%rax,1)
32|66662e0f1f840000000000|data16|cs nopw 0x0(%rax,%rax,1)
3d|0f1f00|nopl|(%rax)
40|0fb606|movzbl|(%rsi),%eax
43|4883c601|add|$0x1,%rsi
47|48d3e0|shl|%cl,%rax
4a|83c108|add|$0x8,%ecx
4d|4909c0|or|%rax,%r8
50|39ca|cmp|%ecx,%edx
52|75ec|jne|+40
54|4c89c0|mov|%r8,%rax
57|c3|ret|
""",
    "flags": """
0|4889f8|mov|%rdi,%rax
3|488b7e08|mov|0x8(%rsi),%rdi
7|4889f2|mov|%rsi,%rdx
a|4883ff07|cmp|$0x7,%rdi
e|0f8680000000|jbe|+94
14|488d4ff8|lea|-0x8(%rdi),%rcx
18|4883f903|cmp|$0x3,%rcx
1c|7676|jbe|+94
1e|488b36|mov|(%rsi),%rsi
21|0fb64e0a|movzbl|0xa(%rsi),%ecx
25|440fb64609|movzbl|0x9(%rsi),%r8d
2a|48c1e110|shl|$0x10,%rcx
2e|49c1e008|shl|$0x8,%r8
32|4c09c1|or|%r8,%rcx
35|440fb64608|movzbl|0x8(%rsi),%r8d
3a|0fb6760b|movzbl|0xb(%rsi),%esi
3e|4c09c1|or|%r8,%rcx
41|48c1e618|shl|$0x18,%rsi
45|4809f1|or|%rsi,%rcx
48|488d71fb|lea|-0x5(%rcx),%rsi
4c|4883fe01|cmp|$0x1,%rsi
50|0f86aa010000|jbe|+200
56|4883f904|cmp|$0x4,%rcx
5a|0f85c0010000|jne|+220
60|48b90100000000000080|movabs|$0x8000000000000001,%rcx
6a|483d00100800|cmp|$0x81000,%rax
70|0f8482010000|je|+1f8
76|488db00000faff|lea|-0x60000(%rax),%rsi
7d|48b90300000000000080|movabs|$0x8000000000000003,%rcx
87|4881feff0f0200|cmp|$0x20fff,%rsi
8e|0f8664010000|jbe|+1f8
94|488d8800f0ffff|lea|-0x1000(%rax),%rcx
9b|4881f9ffff0000|cmp|$0xffff,%rcx
a2|0f8640020000|jbe|+2e8
a8|4885c0|test|%rax,%rax
ab|0f8437020000|je|+2e8
b1|488d8800f0feff|lea|-0x11000(%rax),%rcx
b8|4881f9ffff0000|cmp|$0xffff,%rcx
bf|0f864b020000|jbe|+310
c5|483d00200400|cmp|$0x42000,%rax
cb|0f843f020000|je|+310
d1|488db000c0fbff|lea|-0x44000(%rax),%rsi
d8|48b90300000000000080|movabs|$0x8000000000000003,%rcx
e2|4881feff3f0000|cmp|$0x3fff,%rsi
e9|0f8609010000|jbe|+1f8
ef|488db00000fbff|lea|-0x50000(%rax),%rsi
f6|4881feffff0000|cmp|$0xffff,%rsi
fd|0f86f5000000|jbe|+1f8
103|b901000000|mov|$0x1,%ecx
108|483d00100200|cmp|$0x21000,%rax
10e|0f84e4000000|je|+1f8
114|483dff1f0200|cmp|$0x21fff,%rax
11a|0f86e0010000|jbe|+300
120|4883ff57|cmp|$0x57,%rdi
124|0f86d6010000|jbe|+300
12a|4c8b02|mov|(%rdx),%r8
12d|31ff|xor|%edi,%edi
12f|31d2|xor|%edx,%edx
131|66662e0f1f840000000000|data16|cs nopw 0x0(%rax,%rax,1)
13c|0f1f4000|nopl|0x0(%rax)
140|410fb6741050|movzbl|0x50(%r8,%rdx,1),%esi
146|8d0cd500000000|lea|0x0(,%rdx,8),%ecx
14d|4883c201|add|$0x1,%rdx
151|48d3e6|shl|%cl,%rsi
154|4809f7|or|%rsi,%rdi
157|4883fa08|cmp|$0x8,%rdx
15b|75e3|jne|+140
15d|4881c700200200|add|$0x22000,%rdi
164|4839f8|cmp|%rdi,%rax
167|0f8393010000|jae|+300
16d|31d2|xor|%edx,%edx
16f|31ff|xor|%edi,%edi
171|410fb6741040|movzbl|0x40(%r8,%rdx,1),%esi
177|8d0cd500000000|lea|0x0(,%rdx,8),%ecx
17e|4883c201|add|$0x1,%rdx
182|48d3e6|shl|%cl,%rsi
185|4809f7|or|%rsi,%rdi
188|4883fa08|cmp|$0x8,%rdx
18c|75e3|jne|+171
18e|482d00200200|sub|$0x22000,%rax
194|b901000000|mov|$0x1,%ecx
199|4839f8|cmp|%rdi,%rax
19c|725a|jb|+1f8
19e|31d2|xor|%edx,%edx
1a0|31ff|xor|%edi,%edi
1a2|66662e0f1f840000000000|data16|cs nopw 0x0(%rax,%rax,1)
1ad|66662e0f1f840000000000|data16|cs nopw 0x0(%rax,%rax,1)
1b8|0f1f840000000000|nopl|0x0(%rax,%rax,1)
1c0|410fb6741048|movzbl|0x48(%r8,%rdx,1),%esi
1c6|8d0cd500000000|lea|0x0(,%rdx,8),%ecx
1cd|4883c201|add|$0x1,%rdx
1d1|48d3e6|shl|%cl,%rsi
1d4|4809f7|or|%rsi,%rdi
1d7|4883fa08|cmp|$0x8,%rdx
1db|75e3|jne|+1c0
1dd|48b90100000000000080|movabs|$0x8000000000000001,%rcx
1e7|4839f8|cmp|%rdi,%rax
1ea|48b80300000000000080|movabs|$0x8000000000000003,%rax
1f4|480f43c8|cmovae|%rax,%rcx
1f8|4889c8|mov|%rcx,%rax
1fb|c3|ret|
1fc|0f1f4000|nopl|0x0(%rax)
200|48b90100000000000080|movabs|$0x8000000000000001,%rcx
20a|483d00000e00|cmp|$0xe0000,%rax
210|0f8560feffff|jne|+76
216|ebe0|jmp|+1f8
218|0f1f840000000000|nopl|0x0(%rax,%rax,1)
220|4883f903|cmp|$0x3,%rcx
224|0f85f4000000|jne|+31e
22a|483dffff0f00|cmp|$0xfffff,%rax
230|0f87defeffff|ja|+114
236|a9ff0f0000|test|$0xfff,%eax
23b|0f8535feffff|jne|+76
241|48b90100000000000080|movabs|$0x8000000000000001,%rcx
24b|483d00100800|cmp|$0x81000,%rax
251|74a5|je|+1f8
253|488d8800c0f7ff|lea|-0x84000(%rax),%rcx
25a|4881f9ff3f0000|cmp|$0x3fff,%rcx
261|0f86a9000000|jbe|+310
267|483d00200800|cmp|$0x82000,%rax
26d|0f849d000000|je|+310
273|488db00070f7ff|lea|-0x89000(%rax),%rsi
27a|48b90300000000000080|movabs|$0x8000000000000003,%rcx
284|4881feff3f0000|cmp|$0x3fff,%rsi
28b|0f8667ffffff|jbe|+1f8
291|488db00000f4ff|lea|-0xc0000(%rax),%rsi
298|4881feffff0000|cmp|$0xffff,%rsi
29f|0f8653ffffff|jbe|+1f8
2a5|483dffff0800|cmp|$0x8ffff,%rax
2ab|0f86c5fdffff|jbe|+76
2b1|488db00000f7ff|lea|-0x90000(%rax),%rsi
2b8|4881feffff0100|cmp|$0x1ffff,%rsi
2bf|0f8633ffffff|jbe|+1f8
2c5|488db00000f5ff|lea|-0xb0000(%rax),%rsi
2cc|b901000000|mov|$0x1,%ecx
2d1|4881feff1f0000|cmp|$0x1fff,%rsi
2d8|0f861affffff|jbe|+1f8
2de|e931feffff|jmp|+114
2e3|0f1f440000|nopl|0x0(%rax,%rax,1)
2e8|48b90100000000000080|movabs|$0x8000000000000001,%rcx
2f2|4889c8|mov|%rcx,%rax
2f5|c3|ret|
2f6|662e0f1f840000000000|cs|nopw 0x0(%rax,%rax,1)
300|31c9|xor|%ecx,%ecx
302|4889c8|mov|%rcx,%rax
305|c3|ret|
306|662e0f1f840000000000|cs|nopw 0x0(%rax,%rax,1)
310|48b90300000000000080|movabs|$0x8000000000000003,%rcx
31a|4889c8|mov|%rcx,%rax
31d|c3|ret|
31e|4883f901|cmp|$0x1,%rcx
322|0f866cfdffff|jbe|+94
328|e949fdffff|jmp|+76
""",
    "guard": """
0|4801fe|add|%rdi,%rsi
3|721a|jb|+1f
5|4801d1|add|%rdx,%rcx
8|7215|jb|+1f
a|b801000000|mov|$0x1,%eax
f|4839f2|cmp|%rsi,%rdx
12|7204|jb|+18
14|c3|ret|
15|0f1f00|nopl|(%rax)
18|4839cf|cmp|%rcx,%rdi
1b|0f93c0|setae|%al
1e|c3|ret|
1f|31c0|xor|%eax,%eax
21|c3|ret|
""",
    "entry": """
0|49ba9f0f00000000f0ff|movabs|$0xfff0000000000f9f,%r10
a|53|push|%rbx
b|4c8b07|mov|(%rdi),%r8
e|4989f9|mov|%rdi,%r9
11|488d3d00000000|lea|@levels,%rdi
18|49bb00f0ffffffff0f00|movabs|$0xffffffffff000,%r11
22|488d5f0c|lea|0xc(%rdi),%rbx
26|4c89c0|mov|%r8,%rax
29|8b0f|mov|(%rdi),%ecx
2b|4889f2|mov|%rsi,%rdx
2e|48d3ea|shr|%cl,%rdx
31|81e2ff010000|and|$0x1ff,%edx
37|488b04d0|mov|(%rax,%rdx,8),%rax
3b|4889c2|mov|%rax,%rdx
3e|4c21d2|and|%r10,%rdx
41|4883fa03|cmp|$0x3,%rdx
45|7539|jne|+80
47|4c21d8|and|%r11,%rax
4a|4c39c0|cmp|%r8,%rax
4d|7231|jb|+80
4f|498b5108|mov|0x8(%r9),%rdx
53|48c1e20c|shl|$0xc,%rdx
57|4c01c2|add|%r8,%rdx
5a|4839d0|cmp|%rdx,%rax
5d|7321|jae|+80
5f|4883c704|add|$0x4,%rdi
63|4839df|cmp|%rbx,%rdi
66|75c1|jne|+29
68|48c1ee0c|shr|$0xc,%rsi
6c|5b|pop|%rbx
6d|81e6ff010000|and|$0x1ff,%esi
73|488b04f0|mov|(%rax,%rsi,8),%rax
77|c3|ret|
78|0f1f840000000000|nopl|0x0(%rax,%rax,1)
80|31c0|xor|%eax,%eax
82|5b|pop|%rbx
83|c3|ret|
""",
    "window": """
0|48c1e60c|shl|$0xc,%rsi
4|4889f8|mov|%rdi,%rax
7|488d1500000000|lea|@levels,%rdx
e|49b89f0f00000000f0ff|movabs|$0xfff0000000000f9f,%r8
18|4801fe|add|%rdi,%rsi
1b|4c8d520c|lea|0xc(%rdx),%r10
1f|49b900f0ffffffff0f00|movabs|$0xffffffffff000,%r9
29|49bb000000000080ffff|movabs|$0xffff800000000000,%r11
33|8b0a|mov|(%rdx),%ecx
35|49d3eb|shr|%cl,%r11
38|4c89d9|mov|%r11,%rcx
3b|81e1ff010000|and|$0x1ff,%ecx
41|488b04c8|mov|(%rax,%rcx,8),%rax
45|4889c1|mov|%rax,%rcx
48|4c21c1|and|%r8,%rcx
4b|4883f903|cmp|$0x3,%rcx
4f|751f|jne|+70
51|4c21c8|and|%r9,%rax
54|4839f8|cmp|%rdi,%rax
57|7217|jb|+70
59|4839f0|cmp|%rsi,%rax
5c|7312|jae|+70
5e|4883c204|add|$0x4,%rdx
62|4939d2|cmp|%rdx,%r10
65|75c2|jne|+29
67|c3|ret|
68|0f1f840000000000|nopl|0x0(%rax,%rax,1)
70|31c0|xor|%eax,%eax
72|c3|ret|
""",
}


def body(operations):
    return [decoder.Instruction(index, 1, op, args) for index, (op, args) in enumerate(operations)]


# Independently retained GCC16 image-window003 instruction bytes and operands.
# The fixture relocates direct targets without invoking a compiler/disassembler.
PAIRED_GCC16_LINKED_FIXTURES = {
    "root": """
0|4881ece8000000|sub|$0xe8,%rsp
7|4c8b17|mov|(%rdi),%r10
a|4c8b4f08|mov|0x8(%rdi),%r9
e|488b4710|mov|0x10(%rdi),%rax
12|4889742438|mov|%rsi,0x38(%rsp)
17|48894c2430|mov|%rcx,0x30(%rsp)
1c|4c89442428|mov|%r8,0x28(%rsp)
21|4c89542458|mov|%r10,0x58(%rsp)
26|4c894c2460|mov|%r9,0x60(%rsp)
2b|4889442468|mov|%rax,0x68(%rsp)
30|4885c9|test|%rcx,%rcx
33|7415|je|+4a
35|4d85c0|test|%r8,%r8
38|4d89c3|mov|%r8,%r11
3b|410f94c0|sete|%r8b
3f|4885c0|test|%rax,%rax
42|0f95c0|setne|%al
45|4108c0|or|%al,%r8b
48|7416|je|+60
4a|4531c0|xor|%r8d,%r8d
4d|4489c0|mov|%r8d,%eax
50|4881c4e8000000|add|$0xe8,%rsp
57|c3|ret|
58|0f1f840000000000|nopl|0x0(%rax,%rax,1)
60|4889ac24c8000000|mov|%rbp,0xc8(%rsp)
68|4889fd|mov|%rdi,%rbp
6b|488b7c2438|mov|0x38(%rsp),%rdi
70|4c89a424d0000000|mov|%r12,0xd0(%rsp)
78|4989cc|mov|%rcx,%r12
7b|4c89b424d8000000|mov|%r14,0xd8(%rsp)
83|4989d6|mov|%rdx,%r14
86|4c89bc24e0000000|mov|%r15,0xe0(%rsp)
8e|4c8b7c2438|mov|0x38(%rsp),%r15
93|4488442420|mov|%r8b,0x20(%rsp)
98|4c895c2418|mov|%r11,0x18(%rsp)
9d|4c894c2410|mov|%r9,0x10(%rsp)
a2|4c89542408|mov|%r10,0x8(%rsp)
a7|e800000000|call|@layout
ac|4c8b4c2410|mov|0x10(%rsp),%r9
b1|4c8b542408|mov|0x8(%rsp),%r10
b6|4c8b5c2418|mov|0x18(%rsp),%r11
bb|440fb6442420|movzbl|0x20(%rsp),%r8d
c1|498d51ff|lea|-0x1(%r9),%rdx
c5|4883fa0f|cmp|$0xf,%rdx
c9|0f97c2|seta|%dl
cc|83f001|xor|$0x1,%eax
cf|08c2|or|%al,%dl
d1|742d|je|+100
d3|488bac24c8000000|mov|0xc8(%rsp),%rbp
db|4c8ba424d0000000|mov|0xd0(%rsp),%r12
e3|4489c0|mov|%r8d,%eax
e6|4c8bb424d8000000|mov|0xd8(%rsp),%r14
ee|4c8bbc24e0000000|mov|0xe0(%rsp),%r15
f6|4881c4e8000000|add|$0xe8,%rsp
fd|c3|ret|
fe|6690|xchg|%ax,%ax
100|498d8700100100|lea|0x11000(%r15),%rax
107|4939c2|cmp|%rax,%r10
10a|0f8510030000|jne|+420
110|4d8b4608|mov|0x8(%r14),%r8
114|4983f807|cmp|$0x7,%r8
118|0f8602030000|jbe|+420
11e|498b3e|mov|(%r14),%rdi
121|31c0|xor|%eax,%eax
123|31f6|xor|%esi,%esi
125|0f1f440000|nopl|0x0(%rax,%rax,1)
12a|66662e0f1f840000000000|data16|cs nopw 0x0(%rax,%rax,1)
135|66662e0f1f840000000000|data16|cs nopw 0x0(%rax,%rax,1)
140|0fb61407|movzbl|(%rdi,%rax,1),%edx
144|8d0cc500000000|lea|0x0(,%rax,8),%ecx
14b|4883c001|add|$0x1,%rax
14f|48d3e2|shl|%cl,%rdx
152|4809d6|or|%rdx,%rsi
155|4883f808|cmp|$0x8,%rax
159|75e5|jne|+140
15b|48b849464555524f5241|movabs|$0x41524f5255454649,%rax
165|4839c6|cmp|%rax,%rsi
168|0f85b2020000|jne|+420
16e|498d40f8|lea|-0x8(%r8),%rax
172|4883f803|cmp|$0x3,%rax
176|0f86a4020000|jbe|+420
17c|0fb64709|movzbl|0x9(%rdi),%eax
180|0fb6570a|movzbl|0xa(%rdi),%edx
184|48c1e008|shl|$0x8,%rax
188|48c1e210|shl|$0x10,%rdx
18c|4809d0|or|%rdx,%rax
18f|0fb65708|movzbl|0x8(%rdi),%edx
193|4809d0|or|%rdx,%rax
196|0fb6570b|movzbl|0xb(%rdi),%edx
19a|48c1e218|shl|$0x18,%rdx
19e|4809d0|or|%rdx,%rax
1a1|4883f806|cmp|$0x6,%rax
1a5|0f8575020000|jne|+420
1ab|498d40f4|lea|-0xc(%r8),%rax
1af|4883f803|cmp|$0x3,%rax
1b3|0f8667020000|jbe|+420
1b9|0fb6470e|movzbl|0xe(%rdi),%eax
1bd|0fb6570d|movzbl|0xd(%rdi),%edx
1c1|48c1e010|shl|$0x10,%rax
1c5|48c1e208|shl|$0x8,%rdx
1c9|4809d0|or|%rdx,%rax
1cc|0fb6570c|movzbl|0xc(%rdi),%edx
1d0|4809d0|or|%rdx,%rax
1d3|0fb6570f|movzbl|0xf(%rdi),%edx
1d7|48c1e218|shl|$0x18,%rdx
1db|4809d0|or|%rdx,%rax
1de|483d80000000|cmp|$0x80,%rax
1e4|0f8536020000|jne|+420
1ea|498d40f0|lea|-0x10(%r8),%rax
1ee|4883f807|cmp|$0x7,%rax
1f2|0f8628020000|jbe|+420
1f8|31c0|xor|%eax,%eax
1fa|31f6|xor|%esi,%esi
1fc|0f1f4000|nopl|0x0(%rax)
200|0fb6540710|movzbl|0x10(%rdi,%rax,1),%edx
205|8d0cc500000000|lea|0x0(,%rax,8),%ecx
20c|4883c001|add|$0x1,%rax
210|48d3e2|shl|%cl,%rdx
213|4809d6|or|%rdx,%rsi
216|4883f808|cmp|$0x8,%rax
21a|75e4|jne|+200
21c|4881fe00001000|cmp|$0x100000,%rsi
223|0f85f7010000|jne|+420
229|498d40e8|lea|-0x18(%r8),%rax
22d|4883f807|cmp|$0x7,%rax
231|0f86e9010000|jbe|+420
237|31c0|xor|%eax,%eax
239|31f6|xor|%esi,%esi
23b|0fb6540718|movzbl|0x18(%rdi,%rax,1),%edx
240|8d0cc500000000|lea|0x0(,%rax,8),%ecx
247|4883c001|add|$0x1,%rax
24b|48d3e2|shl|%cl,%rdx
24e|4809d6|or|%rdx,%rsi
251|4883f808|cmp|$0x8,%rax
255|75e4|jne|+23b
257|4939f7|cmp|%rsi,%r15
25a|0f85c0010000|jne|+420
260|498d40e0|lea|-0x20(%r8),%rax
264|4883f807|cmp|$0x7,%rax
268|0f86b2010000|jbe|+420
26e|31c0|xor|%eax,%eax
270|31f6|xor|%esi,%esi
272|0fb6540720|movzbl|0x20(%rdi,%rax,1),%edx
277|8d0cc500000000|lea|0x0(,%rax,8),%ecx
27e|4883c001|add|$0x1,%rax
282|48d3e2|shl|%cl,%rdx
285|4809d6|or|%rdx,%rsi
288|4883f808|cmp|$0x8,%rax
28c|75e4|jne|+272
28e|4883ee01|sub|$0x1,%rsi
292|4881feffff0000|cmp|$0xffff,%rsi
299|0f8781010000|ja|+420
29f|498d40d8|lea|-0x28(%r8),%rax
2a3|4883f807|cmp|$0x7,%rax
2a7|0f8673010000|jbe|+420
2ad|31c0|xor|%eax,%eax
2af|31d2|xor|%edx,%edx
2b1|0fb6740728|movzbl|0x28(%rdi,%rax,1),%esi
2b6|8d0cc500000000|lea|0x0(,%rax,8),%ecx
2bd|4883c001|add|$0x1,%rax
2c1|48d3e6|shl|%cl,%rsi
2c4|4809f2|or|%rsi,%rdx
2c7|4883f808|cmp|$0x8,%rax
2cb|75e4|jne|+2b1
2cd|4883ea28|sub|$0x28,%rdx
2d1|4881fad8000000|cmp|$0xd8,%rdx
2d8|0f8742010000|ja|+420
2de|4983e830|sub|$0x30,%r8
2e2|4983f803|cmp|$0x3,%r8
2e6|0f8634010000|jbe|+420
2ec|0fb64732|movzbl|0x32(%rdi),%eax
2f0|0fb65731|movzbl|0x31(%rdi),%edx
2f4|48c1e010|shl|$0x10,%rax
2f8|48c1e208|shl|$0x8,%rdx
2fc|4809d0|or|%rdx,%rax
2ff|0fb65730|movzbl|0x30(%rdi),%edx
303|4809d0|or|%rdx,%rax
306|0fb65733|movzbl|0x33(%rdi),%edx
30a|48c1e218|shl|$0x18,%rdx
30e|4809d0|or|%rdx,%rax
311|4883e801|sub|$0x1,%rax
315|0f8505010000|jne|+420
31b|ba04000000|mov|$0x4,%edx
320|be34000000|mov|$0x34,%esi
325|4c89f7|mov|%r14,%rdi
328|4c89542410|mov|%r10,0x10(%rsp)
32d|4c894c2418|mov|%r9,0x18(%rsp)
332|4c895c2420|mov|%r11,0x20(%rsp)
337|e800000000|call|@bytes
33c|4883e801|sub|$0x1,%rax
340|4883f802|cmp|$0x2,%rax
344|0f87d6000000|ja|+420
34a|ba08000000|mov|$0x8,%edx
34f|be38000000|mov|$0x38,%esi
354|4c89f7|mov|%r14,%rdi
357|e800000000|call|@bytes
35c|4989c0|mov|%rax,%r8
35f|488d40ff|lea|-0x1(%rax),%rax
363|483dffff0100|cmp|$0x1ffff,%rax
369|0f87b1000000|ja|+420
36f|ba08000000|mov|$0x8,%edx
374|be50000000|mov|$0x50,%esi
379|4c89f7|mov|%r14,%rdi
37c|48899c24c0000000|mov|%rbx,0xc0(%rsp)
384|4c89442408|mov|%r8,0x8(%rsp)
389|e800000000|call|@bytes
38e|4889c3|mov|%rax,%rbx
391|483b442408|cmp|0x8(%rsp),%rax
396|7277|jb|+40f
398|ba08000000|mov|$0x8,%edx
39d|be40000000|mov|$0x40,%esi
3a2|4c89f7|mov|%r14,%rdi
3a5|e800000000|call|@bytes
3aa|4885c0|test|%rax,%rax
3ad|7460|je|+40f
3af|a9ff0f0000|test|$0xfff,%eax
3b4|7559|jne|+40f
3b6|ba08000000|mov|$0x8,%edx
3bb|be48000000|mov|$0x48,%esi
3c0|4c89f7|mov|%r14,%rdi
3c3|4889442408|mov|%rax,0x8(%rsp)
3c8|e800000000|call|@bytes
3cd|4889de|mov|%rbx,%rsi
3d0|4c8b542410|mov|0x10(%rsp),%r10
3d5|4c8b4c2418|mov|0x18(%rsp),%r9
3da|4839c3|cmp|%rax,%rbx
3dd|4c8b5c2420|mov|0x20(%rsp),%r11
3e2|410f92c0|setb|%r8b
3e6|483b442408|cmp|0x8(%rsp),%rax
3eb|0f92c2|setb|%dl
3ee|4109d0|or|%edx,%r8d
3f1|4881fb00000200|cmp|$0x20000,%rbx
3f8|0f97c2|seta|%dl
3fb|4809c6|or|%rax,%rsi
3fe|4109d0|or|%edx,%r8d
401|f7c6ff0f0000|test|$0xfff,%esi
407|0f95c0|setne|%al
40a|4108c0|or|%al,%r8b
40d|7439|je|+448
40f|488b9c24c0000000|mov|0xc0(%rsp),%rbx
417|660f1f840000000000|nopw|0x0(%rax,%rax,1)
420|488bac24c8000000|mov|0xc8(%rsp),%rbp
428|4c8ba424d0000000|mov|0xd0(%rsp),%r12
430|4531c0|xor|%r8d,%r8d
433|4c8bb424d8000000|mov|0xd8(%rsp),%r14
43b|4c8bbc24e0000000|mov|0xe0(%rsp),%r15
443|e905fcffff|jmp|+4d
448|ba08000000|mov|$0x8,%edx
44d|be58000000|mov|$0x58,%esi
452|4c89f7|mov|%r14,%rdi
455|4488442420|mov|%r8b,0x20(%rsp)
45a|4c895c2418|mov|%r11,0x18(%rsp)
45f|4c894c2410|mov|%r9,0x10(%rsp)
464|4c89542408|mov|%r10,0x8(%rsp)
469|e800000000|call|@bytes
46e|4839442408|cmp|%rax,0x8(%rsp)
473|440fb6442420|movzbl|0x20(%rsp),%r8d
479|0f85cb000000|jne|+54a
47f|ba08000000|mov|$0x8,%edx
484|be60000000|mov|$0x60,%esi
489|4c89f7|mov|%r14,%rdi
48c|4488442408|mov|%r8b,0x8(%rsp)
491|e800000000|call|@bytes
496|4839442410|cmp|%rax,0x10(%rsp)
49b|440fb6442408|movzbl|0x8(%rsp),%r8d
4a1|0f85a3000000|jne|+54a
4a7|ba08000000|mov|$0x8,%edx
4ac|be68000000|mov|$0x68,%esi
4b1|4c89f7|mov|%r14,%rdi
4b4|e800000000|call|@bytes
4b9|440fb6442408|movzbl|0x8(%rsp),%r8d
4bf|4889c2|mov|%rax,%rdx
4c2|498d8700200200|lea|0x22000(%r15),%rax
4c9|4839c2|cmp|%rax,%rdx
4cc|757c|jne|+54a
4ce|ba08000000|mov|$0x8,%edx
4d3|be70000000|mov|$0x70,%esi
4d8|4c89f7|mov|%r14,%rdi
4db|e800000000|call|@bytes
4e0|440fb6442408|movzbl|0x8(%rsp),%r8d
4e6|4885c0|test|%rax,%rax
4e9|745f|je|+54a
4eb|ba08000000|mov|$0x8,%edx
4f0|be78000000|mov|$0x78,%esi
4f5|4c89f7|mov|%r14,%rdi
4f8|e800000000|call|@bytes
4fd|440fb6442408|movzbl|0x8(%rsp),%r8d
503|4889c2|mov|%rax,%rdx
506|498d8700000e00|lea|0xe0000(%r15),%rax
50d|4839c2|cmp|%rax,%rdx
510|7538|jne|+54a
512|4d3b3c24|cmp|(%r12),%r15
516|7532|jne|+54a
518|4c8b5c2418|mov|0x18(%rsp),%r11
51d|4d3b7b30|cmp|0x30(%r11),%r15
521|7527|jne|+54a
523|418b4c2408|mov|0x8(%r12),%ecx
528|498b03|mov|(%r11),%rax
52b|498b5318|mov|0x18(%r11),%rdx
52f|8d71e0|lea|-0x20(%rcx),%esi
532|83fe14|cmp|$0x14,%esi
535|4889542440|mov|%rdx,0x40(%rsp)
53a|400f97c6|seta|%sil
53e|4885c0|test|%rax,%rax
541|400f94c7|sete|%dil
545|4008fe|or|%dil,%sil
548|740d|je|+557
54a|488b9c24c0000000|mov|0xc0(%rsp),%rbx
552|e97cfbffff|jmp|+d3
557|488d72ff|lea|-0x1(%rdx),%rsi
55b|4881feffff2f00|cmp|$0x2fffff,%rsi
562|7605|jbe|+569
564|4531c0|xor|%r8d,%r8d
567|ebe1|jmp|+54a
569|4889c6|mov|%rax,%rsi
56c|4809d6|or|%rdx,%rsi
56f|81e6ff0f0000|and|$0xfff,%esi
575|4989f4|mov|%rsi,%r12
578|75ea|jne|+564
57a|498b7b08|mov|0x8(%r11),%rdi
57e|4839d7|cmp|%rdx,%rdi
581|72e1|jb|+564
583|be01000000|mov|$0x1,%esi
588|48d3e6|shl|%cl,%rsi
58b|4889f1|mov|%rsi,%rcx
58e|4839f0|cmp|%rsi,%rax
591|73d1|jae|+564
593|4829c1|sub|%rax,%rcx
596|4839f9|cmp|%rdi,%rcx
599|410f93c0|setae|%r8b
59d|4981ffffffefff|cmp|$0xffffffffffefffff,%r15
5a4|0f96c1|setbe|%cl
5a7|4120c8|and|%cl,%r8b
5aa|749e|je|+54a
5ac|488d0c10|lea|(%rax,%rdx,1),%rcx
5b0|4939cf|cmp|%rcx,%r15
5b3|730c|jae|+5c1
5b5|498db700001000|lea|0x100000(%r15),%rsi
5bc|4839f0|cmp|%rsi,%rax
5bf|72a3|jb|+564
5c1|be0000e0fe|mov|$0xfee00000,%esi
5c6|bfff0fe0fe|mov|$0xfee00fff,%edi
5cb|4839ce|cmp|%rcx,%rsi
5ce|410f93c0|setae|%r8b
5d2|4839c7|cmp|%rax,%rdi
5d5|410f92c1|setb|%r9b
5d9|4508c8|or|%r9b,%r8b
5dc|0f8468ffffff|je|+54a
5e2|41b80000c0fe|mov|$0xfec00000,%r8d
5e8|41b9ff0fc0fe|mov|$0xfec00fff,%r9d
5ee|4939c8|cmp|%rcx,%r8
5f1|410f93c0|setae|%r8b
5f5|4939c1|cmp|%rax,%r9
5f8|410f92c1|setb|%r9b
5fc|4508c8|or|%r9b,%r8b
5ff|0f8445ffffff|je|+54a
605|41b8ffffffef|mov|$0xefffffff,%r8d
60b|4939c0|cmp|%rax,%r8
60e|b8000000e0|mov|$0xe0000000,%eax
613|410f92c0|setb|%r8b
617|4839c8|cmp|%rcx,%rax
61a|0f93c0|setae|%al
61d|4108c0|or|%al,%r8b
620|0f8424ffffff|je|+54a
626|4c39ff|cmp|%r15,%rdi
629|0f82b7010000|jb|+7e6
62f|498d8700001000|lea|0x100000(%r15),%rax
636|4839c6|cmp|%rax,%rsi
639|0f8225ffffff|jb|+564
63f|488d542470|lea|0x70(%rsp),%rdx
644|488d4c2458|lea|0x58(%rsp),%rcx
649|be18000000|mov|$0x18,%esi
64e|4889ef|mov|%rbp,%rdi
651|4889942498000000|mov|%rdx,0x98(%rsp)
659|488d542430|lea|0x30(%rsp),%rdx
65e|488d442440|lea|0x40(%rsp),%rax
663|48898c2488000000|mov|%rcx,0x88(%rsp)
66b|488d4c2448|lea|0x48(%rsp),%rcx
670|48899424a0000000|mov|%rdx,0xa0(%rsp)
678|488d542428|lea|0x28(%rsp),%rdx
67d|4889442470|mov|%rax,0x70(%rsp)
682|488d442438|lea|0x38(%rsp),%rax
687|48898c2490000000|mov|%rcx,0x90(%rsp)
68f|b910000000|mov|$0x10,%ecx
694|48899424a8000000|mov|%rdx,0xa8(%rsp)
69c|488d542448|lea|0x48(%rsp),%rdx
6a1|4c89742478|mov|%r14,0x78(%rsp)
6a6|4889842480000000|mov|%rax,0x80(%rsp)
6ae|48898424b0000000|mov|%rax,0xb0(%rsp)
6b6|4c89b424b8000000|mov|%r14,0xb8(%rsp)
6be|e800000000|call|@guard
6c3|4189c0|mov|%eax,%r8d
6c6|84c0|test|%al,%al
6c8|0f847cfeffff|je|+54a
6ce|b918000000|mov|$0x18,%ecx
6d3|488d542458|lea|0x58(%rsp),%rdx
6d8|be18000000|mov|$0x18,%esi
6dd|4889ef|mov|%rbp,%rdi
6e0|e800000000|call|@guard
6e5|4189c0|mov|%eax,%r8d
6e8|84c0|test|%al,%al
6ea|0f845afeffff|je|+54a
6f0|b938000000|mov|$0x38,%ecx
6f5|488d942488000000|lea|0x88(%rsp),%rdx
6fd|be18000000|mov|$0x18,%esi
702|4889ef|mov|%rbp,%rdi
705|e800000000|call|@guard
70a|4189c0|mov|%eax,%r8d
70d|84c0|test|%al,%al
70f|0f8435feffff|je|+54a
715|b910000000|mov|$0x10,%ecx
71a|488d542448|lea|0x48(%rsp),%rdx
71f|be18000000|mov|$0x18,%esi
724|488d7c2458|lea|0x58(%rsp),%rdi
729|e800000000|call|@guard
72e|4189c0|mov|%eax,%r8d
731|84c0|test|%al,%al
733|0f8411feffff|je|+54a
739|b938000000|mov|$0x38,%ecx
73e|be18000000|mov|$0x18,%esi
743|488d7c2458|lea|0x58(%rsp),%rdi
748|488d942488000000|lea|0x88(%rsp),%rdx
750|e800000000|call|@guard
755|4189c0|mov|%eax,%r8d
758|84c0|test|%al,%al
75a|0f84eafdffff|je|+54a
760|b938000000|mov|$0x38,%ecx
765|be10000000|mov|$0x10,%esi
76a|488d7c2448|lea|0x48(%rsp),%rdi
76f|488d942488000000|lea|0x88(%rsp),%rdx
777|e800000000|call|@guard
77c|4189c0|mov|%eax,%r8d
77f|84c0|test|%al,%al
781|0f84c3fdffff|je|+54a
787|31c0|xor|%eax,%eax
789|c644044800|movb|$0x0,0x48(%rsp,%rax,1)
78e|4883c001|add|$0x1,%rax
792|4883f810|cmp|$0x10,%rax
796|75f1|jne|+789
798|488db42488000000|lea|0x88(%rsp),%rsi
7a0|488b542458|mov|0x58(%rsp),%rdx
7a5|4531c0|xor|%r8d,%r8d
7a8|b903000000|mov|$0x3,%ecx
7ad|4889f7|mov|%rsi,%rdi
7b0|4c8b7c2458|mov|0x58(%rsp),%r15
7b5|e800000000|call|@walk
7ba|4189c0|mov|%eax,%r8d
7bd|84c0|test|%al,%al
7bf|0f8485fdffff|je|+54a
7c5|488b442460|mov|0x60(%rsp),%rax
7ca|31c9|xor|%ecx,%ecx
7cc|4839c8|cmp|%rcx,%rax
7cf|7449|je|+81a
7d1|440fb6440c48|movzbl|0x48(%rsp,%rcx,1),%r8d
7d7|4584c0|test|%r8b,%r8b
7da|0f846afdffff|je|+54a
7e0|4883c101|add|$0x1,%rcx
7e4|ebe6|jmp|+7cc
7e6|48b80020000000a0ffff|movabs|$0xffffa00000002000,%rax
7f0|4801c2|add|%rax,%rdx
7f3|4939d7|cmp|%rdx,%r15
7f6|0f8343feffff|jae|+63f
7fc|bafdff0700|mov|$0x7fffd,%edx
801|498d8700001000|lea|0x100000(%r15),%rax
808|48c1e22d|shl|$0x2d,%rdx
80c|4839c2|cmp|%rax,%rdx
80f|0f824ffdffff|jb|+564
815|e925feffff|jmp|+63f
81a|488b6c2438|mov|0x38(%rsp),%rbp
81f|4c89f6|mov|%r14,%rsi
822|4c89e7|mov|%r12,%rdi
825|48894c2418|mov|%rcx,0x18(%rsp)
82a|e800000000|call|@flags
82f|4a8d542500|lea|0x0(%rbp,%r12,1),%rdx
834|488d7c2458|lea|0x58(%rsp),%rdi
839|4889d6|mov|%rdx,%rsi
83c|4889542408|mov|%rdx,0x8(%rsp)
841|4889442410|mov|%rax,0x10(%rsp)
846|e800000000|call|@entry
84b|4c8b442410|mov|0x10(%rsp),%r8
850|4889c6|mov|%rax,%rsi
853|488b442408|mov|0x8(%rsp),%rax
858|4889f2|mov|%rsi,%rdx
85b|4c09c0|or|%r8,%rax
85e|4d85c0|test|%r8,%r8
861|490f44c0|cmove|%r8,%rax
865|4883e29f|and|$0xffffffffffffff9f,%rdx
869|4d85c0|test|%r8,%r8
86c|480f44d6|cmove|%rsi,%rdx
870|4839c2|cmp|%rax,%rdx
873|0f85ebfcffff|jne|+564
879|498d9c2400100000|lea|0x1000(%r12),%rbx
881|488b4c2418|mov|0x18(%rsp),%rcx
886|4881fb00001000|cmp|$0x100000,%rbx
88d|4989dc|mov|%rbx,%r12
890|758d|jne|+81f
892|4889ce|mov|%rcx,%rsi
895|4c89ff|mov|%r15,%rdi
898|e800000000|call|@window
89d|4885c0|test|%rax,%rax
8a0|0f84befcffff|je|+564
8a6|beffff0100|mov|$0x1ffff,%esi
8ab|488d7c2458|lea|0x58(%rsp),%rdi
8b0|48c1e62f|shl|$0x2f,%rsi
8b4|e800000000|call|@entry
8b9|4885c0|test|%rax,%rax
8bc|0f85a2fcffff|jne|+564
8c2|bef9ff0f00|mov|$0xffff9,%esi
8c7|488d7c2458|lea|0x58(%rsp),%rdi
8cc|48c1e62c|shl|$0x2c,%rsi
8d0|e800000000|call|@entry
8d5|48ba1b00e0fe00000080|movabs|$0x80000000fee0001b,%rdx
8df|4883e09f|and|$0xffffffffffffff9f,%rax
8e3|4839d0|cmp|%rdx,%rax
8e6|0f8578fcffff|jne|+564
8ec|488b5c2440|mov|0x40(%rsp),%rbx
8f1|4c8b442428|mov|0x28(%rsp),%r8
8f6|31d2|xor|%edx,%edx
8f8|49bb0010000000a0ffff|movabs|$0xffffa00000001000,%r11
902|4839da|cmp|%rbx,%rdx
905|0f8381000000|jae|+98c
90b|4a8d341a|lea|(%rdx,%r11,1),%rsi
90f|488d7c2458|lea|0x58(%rsp),%rdi
914|4c89442418|mov|%r8,0x18(%rsp)
919|4889542410|mov|%rdx,0x10(%rsp)
91e|4889742408|mov|%rsi,0x8(%rsp)
923|e800000000|call|@entry
928|488b542410|mov|0x10(%rsp),%rdx
92d|4c8b442418|mov|0x18(%rsp),%r8
932|49bb0010000000a0ffff|movabs|$0xffffa00000001000,%r11
93c|49b91b00000000000080|movabs|$0x800000000000001b,%r9
946|4883e09f|and|$0xffffffffffffff9f,%rax
94a|4889c1|mov|%rax,%rcx
94d|48b8ffefffffff5f0000|movabs|$0x5fffffffefff,%rax
957|4839d0|cmp|%rdx,%rax
95a|7270|jb|+9cc
95c|493b5018|cmp|0x18(%r8),%rdx
960|736a|jae|+9cc
962|48b800f0ffffff5f0000|movabs|$0x5ffffffff000,%rax
96c|490300|add|(%r8),%rax
96f|4803442408|add|0x8(%rsp),%rax
974|4c09c8|or|%r9,%rax
977|4839c1|cmp|%rax,%rcx
97a|0f85e4fbffff|jne|+564
980|4881c200100000|add|$0x1000,%rdx
987|e976ffffff|jmp|+902
98c|befdff0700|mov|$0x7fffd,%esi
991|488d7c2458|lea|0x58(%rsp),%rdi
996|48c1e62d|shl|$0x2d,%rsi
99a|e800000000|call|@entry
99f|4885c0|test|%rax,%rax
9a2|0f85bcfbffff|jne|+564
9a8|48b80010000000a0ffff|movabs|$0xffffa00000001000,%rax
9b2|488d7c2458|lea|0x58(%rsp),%rdi
9b7|488d3403|lea|(%rbx,%rax,1),%rsi
9bb|e800000000|call|@entry
9c0|4885c0|test|%rax,%rax
9c3|410f94c0|sete|%r8b
9c7|e97efbffff|jmp|+54a
9cc|31c0|xor|%eax,%eax
9ce|eba7|jmp|+977
""",
    "walk": """
0|4883ec78|sub|$0x78,%rsp
4|488b07|mov|(%rdi),%rax
7|4c89642458|mov|%r12,0x58(%rsp)
c|4989d4|mov|%rdx,%r12
f|488b10|mov|(%rax),%rdx
12|4939d4|cmp|%rdx,%r12
15|0f8205020000|jb|+220
1b|488b4008|mov|0x8(%rax),%rax
1f|48c1e00c|shl|$0xc,%rax
23|4801d0|add|%rdx,%rax
26|4939c4|cmp|%rax,%r12
29|0f83f1010000|jae|+220
2f|41f7c4ff0f0000|test|$0xfff,%r12d
36|0f85e4010000|jne|+220
3c|4c89e0|mov|%r12,%rax
3f|4829d0|sub|%rdx,%rax
42|488b5708|mov|0x8(%rdi),%rdx
46|48c1e80c|shr|$0xc,%rax
4a|803c0200|cmpb|$0x0,(%rdx,%rax,1)
4e|0f85cc010000|jne|+220
54|4c896c2460|mov|%r13,0x60(%rsp)
59|4189c9|mov|%ecx,%r9d
5c|4531ed|xor|%r13d,%r13d
5f|4c89742468|mov|%r14,0x68(%rsp)
64|4d89e6|mov|%r12,%r14
67|48895c2448|mov|%rbx,0x48(%rsp)
6c|48896c2450|mov|%rbp,0x50(%rsp)
71|4c897c2470|mov|%r15,0x70(%rsp)
76|c6040201|movb|$0x1,(%rdx,%rax,1)
7a|8d44c90c|lea|0xc(%rcx,%rcx,8),%eax
7e|4c89442408|mov|%r8,0x8(%rsp)
83|4889742420|mov|%rsi,0x20(%rsp)
88|48897c2410|mov|%rdi,0x10(%rsp)
8d|89442404|mov|%eax,0x4(%rsp)
91|e99f000000|jmp|+135
96|662e0f1f840000000000|cs|nopw 0x0(%rax,%rax,1)
a0|4585c9|test|%r9d,%r9d
a3|0f8587010000|jne|+230
a9|488b742410|mov|0x10(%rsp),%rsi
ae|488b4628|mov|0x28(%rsi),%rax
b2|488b00|mov|(%rax),%rax
b5|4939c0|cmp|%rax,%r8
b8|0f8235010000|jb|+1f3
be|488d9000001000|lea|0x100000(%rax),%rdx
c5|4939d0|cmp|%rdx,%r8
c8|0f8325010000|jae|+1f3
ce|4c89c7|mov|%r8,%rdi
d1|488b7630|mov|0x30(%rsi),%rsi
d5|4c89442418|mov|%r8,0x18(%rsp)
da|4829c7|sub|%rax,%rdi
dd|44894c2428|mov|%r9d,0x28(%rsp)
e2|e800000000|call|@flags
e7|4885c0|test|%rax,%rax
ea|0f8403010000|je|+1f3
f0|4c8b442418|mov|0x18(%rsp),%r8
f5|448b4c2428|mov|0x28(%rsp),%r9d
fa|4909c0|or|%rax,%r8
fd|4939d8|cmp|%rbx,%r8
100|0f85ed000000|jne|+1f3
106|0f1f4000|nopl|0x0(%rax)
10a|66662e0f1f840000000000|data16|cs nopw 0x0(%rax,%rax,1)
115|66662e0f1f840000000000|data16|cs nopw 0x0(%rax,%rax,1)
120|4983c501|add|$0x1,%r13
124|4983c608|add|$0x8,%r14
128|4981fd00020000|cmp|$0x200,%r13
12f|0f8465020000|je|+39a
135|498b16|mov|(%r14),%rdx
138|4885d2|test|%rdx,%rdx
13b|74e3|je|+120
13d|0fb64c2404|movzbl|0x4(%rsp),%ecx
142|4d89e8|mov|%r13,%r8
145|4889d3|mov|%rdx,%rbx
148|48b80000000000800000|movabs|$0x800000000000,%rax
152|4883e39f|and|$0xffffffffffffff9f,%rbx
156|49d3e0|shl|%cl,%r8
159|4c0b442408|or|0x8(%rsp),%r8
15e|4985c0|test|%rax,%r8
161|0f8439ffffff|je|+a0
167|48be000000000000ffff|movabs|$0xffff000000000000,%rsi
171|4c09c6|or|%r8,%rsi
174|4989f4|mov|%rsi,%r12
177|4585c9|test|%r9d,%r9d
17a|0f85b3000000|jne|+233
180|48b8000000000090ffff|movabs|$0xffff900000000000,%rax
18a|4839c6|cmp|%rax,%rsi
18d|0f84dd010000|je|+370
193|48b8ff0f000000a0ffff|movabs|$0xffffa00000000fff,%rax
19d|4839f0|cmp|%rsi,%rax
1a0|0f8303ffffff|jae|+a9
1a6|41f7c0ff0f0000|test|$0xfff,%r8d
1ad|0f85f6feffff|jne|+a9
1b3|488b442410|mov|0x10(%rsp),%rax
1b8|488b4020|mov|0x20(%rax),%rax
1bc|488b10|mov|(%rax),%rdx
1bf|48b800f0ffffff5f0000|movabs|$0x5ffffffff000,%rax
1c9|488d0c06|lea|(%rsi,%rax,1),%rcx
1cd|483b4a18|cmp|0x18(%rdx),%rcx
1d1|0f83d2feffff|jae|+a9
1d7|480302|add|(%rdx),%rax
1da|48ba1b00000000000080|movabs|$0x800000000000001b,%rdx
1e4|4801f0|add|%rsi,%rax
1e7|4809d0|or|%rdx,%rax
1ea|4839c3|cmp|%rax,%rbx
1ed|0f842dffffff|je|+120
1f3|31ff|xor|%edi,%edi
1f5|488b5c2448|mov|0x48(%rsp),%rbx
1fa|488b6c2450|mov|0x50(%rsp),%rbp
1ff|89f8|mov|%edi,%eax
201|4c8b6c2460|mov|0x60(%rsp),%r13
206|4c8b742468|mov|0x68(%rsp),%r14
20b|4c8b7c2470|mov|0x70(%rsp),%r15
210|4c8b642458|mov|0x58(%rsp),%r12
215|4883c478|add|$0x78,%rsp
219|c3|ret|
21a|660f1f440000|nopw|0x0(%rax,%rax,1)
220|31ff|xor|%edi,%edi
222|4c8b642458|mov|0x58(%rsp),%r12
227|4883c478|add|$0x78,%rsp
22b|89f8|mov|%edi,%eax
22d|c3|ret|
22e|6690|xchg|%ax,%ax
230|4d89c4|mov|%r8,%r12
233|48b89f0f00000000f0ff|movabs|$0xfff0000000000f9f,%rax
23d|4821d0|and|%rdx,%rax
240|4883f803|cmp|$0x3,%rax
244|75ad|jne|+1f3
246|0fb64c2404|movzbl|0x4(%rsp),%ecx
24b|48c7c0ffffffff|mov|$0xffffffffffffffff,%rax
252|48d3e0|shl|%cl,%rax
255|4889c1|mov|%rax,%rcx
258|48b8000000000080ffff|movabs|$0xffff800000000000,%rax
262|4821c8|and|%rcx,%rax
265|4c39e0|cmp|%r12,%rax
268|0f84c7000000|je|+335
26e|48b8000000000090ffff|movabs|$0xffff900000000000,%rax
278|4821c8|and|%rcx,%rax
27b|4c39e0|cmp|%r12,%rax
27e|0f84b1000000|je|+335
284|488b442410|mov|0x10(%rsp),%rax
289|4c8b7810|mov|0x10(%rax),%r15
28d|48b80000000000a0ffff|movabs|$0xffffa00000000000,%rax
297|498b3f|mov|(%r15),%rdi
29a|480307|add|(%rdi),%rax
29d|4821c8|and|%rcx,%rax
2a0|4c39e0|cmp|%r12,%rax
2a3|48b80010000000a0ffff|movabs|$0xffffa00000001000,%rax
2ad|400f93c7|setae|%dil
2b1|4821c8|and|%rcx,%rax
2b4|4939c4|cmp|%rax,%r12
2b7|0f93c0|setae|%al
2ba|4020c7|and|%al,%dil
2bd|7576|jne|+335
2bf|4c896c2430|mov|%r13,0x30(%rsp)
2c4|498b6f08|mov|0x8(%r15),%rbp
2c8|4531ed|xor|%r13d,%r13d
2cb|4889cb|mov|%rcx,%rbx
2ce|4889542418|mov|%rdx,0x18(%rsp)
2d3|4c89442428|mov|%r8,0x28(%rsp)
2d8|40887c243f|mov|%dil,0x3f(%rsp)
2dd|44894c2438|mov|%r9d,0x38(%rsp)
2e2|eb18|jmp|+2fc
2e4|0f1f4000|nopl|0x0(%rax)
2e8|4981c500100000|add|$0x1000,%r13
2ef|4981fd00001000|cmp|$0x100000,%r13
2f6|0f8494000000|je|+390
2fc|4889ee|mov|%rbp,%rsi
2ff|4c89ef|mov|%r13,%rdi
302|e800000000|call|@flags
307|4885c0|test|%rax,%rax
30a|74dc|je|+2e8
30c|498b4710|mov|0x10(%r15),%rax
310|488b08|mov|(%rax),%rcx
313|4c01e9|add|%r13,%rcx
316|4889c8|mov|%rcx,%rax
319|4821d8|and|%rbx,%rax
31c|4c39e0|cmp|%r12,%rax
31f|75c7|jne|+2e8
321|488b542418|mov|0x18(%rsp),%rdx
326|4c8b442428|mov|0x28(%rsp),%r8
32b|4c8b6c2430|mov|0x30(%rsp),%r13
330|448b4c2438|mov|0x38(%rsp),%r9d
335|488b742420|mov|0x20(%rsp),%rsi
33a|418d49ff|lea|-0x1(%r9),%ecx
33e|44894c2418|mov|%r9d,0x18(%rsp)
343|48b800f0ffffffff0f00|movabs|$0xffffffffff000,%rax
34d|4821c2|and|%rax,%rdx
350|4889f7|mov|%rsi,%rdi
353|e800000000|call|@walk
358|448b4c2418|mov|0x18(%rsp),%r9d
35d|84c0|test|%al,%al
35f|89c7|mov|%eax,%edi
361|0f85b9fdffff|jne|+120
367|e989feffff|jmp|+1f5
36c|0f1f4000|nopl|0x0(%rax)
370|48b81b00e0fe00000080|movabs|$0x80000000fee0001b,%rax
37a|4839c3|cmp|%rax,%rbx
37d|0f849dfdffff|je|+120
383|e96bfeffff|jmp|+1f3
388|0f1f840000000000|nopl|0x0(%rax,%rax,1)
390|0fb67c243f|movzbl|0x3f(%rsp),%edi
395|e95bfeffff|jmp|+1f5
39a|bf01000000|mov|$0x1,%edi
39f|e951feffff|jmp|+1f5
""",
    "layout": """
0|488d870000f0ff|lea|-0x100000(%rdi),%rax
7|ba0000e0ff|mov|$0xffe00000,%edx
c|4839c2|cmp|%rax,%rdx
f|7307|jae|+18
11|31c0|xor|%eax,%eax
13|c3|ret|
14|0f1f4000|nopl|0x0(%rax)
18|f7c7ff0f0000|test|$0xfff,%edi
1e|75f1|jne|+11
20|4881ecb8000000|sub|$0xb8,%rsp
27|bf01000000|mov|$0x1,%edi
2c|48beffffffffff7f0000|movabs|$0x7fffffffffff,%rsi
36|48c744242000000000|movq|$0x0,0x20(%rsp)
3f|488d4c2410|lea|0x10(%rsp),%rcx
44|48c744242800100800|movq|$0x81000,0x28(%rsp)
4d|48c744243000100800|movq|$0x81000,0x30(%rsp)
56|48c744243800100000|movq|$0x1000,0x38(%rsp)
5f|48c744244000200800|movq|$0x82000,0x40(%rsp)
68|48c744244800100000|movq|$0x1000,0x48(%rsp)
71|48c744245000400800|movq|$0x84000,0x50(%rsp)
7a|48c744245800400000|movq|$0x4000,0x58(%rsp)
83|48c744246000900800|movq|$0x89000,0x60(%rsp)
8c|48c744246800400000|movq|$0x4000,0x68(%rsp)
95|48c744247000000b00|movq|$0xb0000,0x70(%rsp)
9e|48c744247800200000|movq|$0x2000,0x78(%rsp)
a7|48c784248000000000000c00|movq|$0xc0000,0x80(%rsp)
b3|48c784248800000000000100|movq|$0x10000,0x88(%rsp)
bf|48c784249000000000000900|movq|$0x90000,0x90(%rsp)
cb|48c784249800000000000100|movq|$0x10000,0x98(%rsp)
d7|48c78424a000000000000a00|movq|$0xa0000,0xa0(%rsp)
e3|48c78424a800000000000100|movq|$0x10000,0xa8(%rsp)
ef|48c744240800300800|movq|$0x83000,0x8(%rsp)
f8|48c744241000800800|movq|$0x88000,0x10(%rsp)
101|48c744241800d00800|movq|$0x8d000,0x18(%rsp)
10a|4c8b01|mov|(%rcx),%r8
10d|4981f8ffff0f00|cmp|$0xfffff,%r8
114|7758|ja|+16e
116|41f7c0ff0f0000|test|$0xfff,%r8d
11d|754f|jne|+16e
11f|48899c24b0000000|mov|%rbx,0xb0(%rsp)
127|488d442408|lea|0x8(%rsp),%rax
12c|4d8d9000100000|lea|0x1000(%r8),%r10
133|eb29|jmp|+15e
135|0f1f00|nopl|(%rax)
138|4989d1|mov|%rdx,%r9
13b|4181e1ff0f0000|and|$0xfff,%r9d
142|7522|jne|+166
144|4c39d2|cmp|%r10,%rdx
147|730c|jae|+155
149|4881c200100000|add|$0x1000,%rdx
150|4939d0|cmp|%rdx,%r8
153|7211|jb|+166
155|4883c008|add|$0x8,%rax
159|4839c1|cmp|%rax,%rcx
15c|741a|je|+178
15e|488b10|mov|(%rax),%rdx
161|4839d6|cmp|%rdx,%rsi
164|73d2|jae|+138
166|488b9c24b0000000|mov|0xb0(%rsp),%rbx
16e|31c0|xor|%eax,%eax
170|4881c4b8000000|add|$0xb8,%rsp
177|c3|ret|
178|4883c108|add|$0x8,%rcx
17c|4883ff02|cmp|$0x2,%rdi
180|0f8532010000|jne|+2b8
186|48beffffffffff7f0000|movabs|$0x7fffffffffff,%rsi
190|488d4c2420|lea|0x20(%rsp),%rcx
195|4c8b01|mov|(%rcx),%r8
198|4981f8ffff0f00|cmp|$0xfffff,%r8
19f|77c5|ja|+166
1a1|4c8b5108|mov|0x8(%rcx),%r10
1a5|4d85d2|test|%r10,%r10
1a8|74bc|je|+166
1aa|4c89c0|mov|%r8,%rax
1ad|4c09d0|or|%r10,%rax
1b0|a9ff0f0000|test|$0xfff,%eax
1b5|75af|jne|+166
1b7|48b80000000000800000|movabs|$0x800000000000,%rax
1c1|4c29c0|sub|%r8,%rax
1c4|4c39d0|cmp|%r10,%rax
1c7|729d|jb|+166
1c9|b800001000|mov|$0x100000,%eax
1ce|4c29c0|sub|%r8,%rax
1d1|4c39d0|cmp|%r10,%rax
1d4|7290|jb|+166
1d6|4d85c9|test|%r9,%r9
1d9|7475|je|+250
1db|488d442420|lea|0x20(%rsp),%rax
1e0|4f8d1c10|lea|(%r8,%r10,1),%r11
1e4|eb59|jmp|+23f
1e6|662e0f1f840000000000|cs|nopw 0x0(%rax,%rax,1)
1f0|488b7808|mov|0x8(%rax),%rdi
1f4|4885ff|test|%rdi,%rdi
1f7|0f8469ffffff|je|+166
1fd|4889d3|mov|%rdx,%rbx
200|4809fb|or|%rdi,%rbx
203|f7c3ff0f0000|test|$0xfff,%ebx
209|0f8557ffffff|jne|+166
20f|48bb0000000000800000|movabs|$0x800000000000,%rbx
219|4829d3|sub|%rdx,%rbx
21c|4839fb|cmp|%rdi,%rbx
21f|0f8241ffffff|jb|+166
225|4c39da|cmp|%r11,%rdx
228|730c|jae|+236
22a|4801fa|add|%rdi,%rdx
22d|4939d0|cmp|%rdx,%r8
230|0f8230ffffff|jb|+166
236|4883c010|add|$0x10,%rax
23a|4839c8|cmp|%rcx,%rax
23d|7411|je|+250
23f|488b10|mov|(%rax),%rdx
242|4839d6|cmp|%rdx,%rsi
245|0f821bffffff|jb|+166
24b|eba3|jmp|+1f0
24d|0f1f00|nopl|(%rax)
250|488d442408|lea|0x8(%rsp),%rax
255|488b10|mov|(%rax),%rdx
258|4839d6|cmp|%rdx,%rsi
25b|0f8205ffffff|jb|+166
261|f7c2ff0f0000|test|$0xfff,%edx
267|0f85f9feffff|jne|+166
26d|4b8d3c10|lea|(%r8,%r10,1),%rdi
271|4839fa|cmp|%rdi,%rdx
274|7310|jae|+286
276|4881c200100000|add|$0x1000,%rdx
27d|4939d0|cmp|%rdx,%r8
280|0f82e0feffff|jb|+166
286|4883c008|add|$0x8,%rax
28a|488d542420|lea|0x20(%rsp),%rdx
28f|4839c2|cmp|%rax,%rdx
292|75c1|jne|+255
294|4983c101|add|$0x1,%r9
298|4883c110|add|$0x10,%rcx
29c|4983f909|cmp|$0x9,%r9
2a0|0f85effeffff|jne|+195
2a6|488b9c24b0000000|mov|0xb0(%rsp),%rbx
2ae|b801000000|mov|$0x1,%eax
2b3|e9b8feffff|jmp|+170
2b8|488b9c24b0000000|mov|0xb0(%rsp),%rbx
2c0|bf02000000|mov|$0x2,%edi
2c5|e940feffff|jmp|+10a
""",
    "bytes": """
0|83fa08|cmp|$0x8,%edx
3|775b|ja|+60
5|488b4708|mov|0x8(%rdi),%rax
9|4839f0|cmp|%rsi,%rax
c|7252|jb|+60
e|89d1|mov|%edx,%ecx
10|4829f0|sub|%rsi,%rax
13|4839c8|cmp|%rcx,%rax
16|7248|jb|+60
18|85d2|test|%edx,%edx
1a|7444|je|+60
1c|480337|add|(%rdi),%rsi
1f|c1e203|shl|$0x3,%edx
22|31c9|xor|%ecx,%ecx
24|31ff|xor|%edi,%edi
26|0f1f4000|nopl|0x0(%rax)
2a|66662e0f1f840000000000|data16|cs nopw 0x0(%rax,%rax,1)
35|66662e0f1f840000000000|data16|cs nopw 0x0(%rax,%rax,1)
40|0fb606|movzbl|(%rsi),%eax
43|4883c601|add|$0x1,%rsi
47|48d3e0|shl|%cl,%rax
4a|83c108|add|$0x8,%ecx
4d|4809c7|or|%rax,%rdi
50|39ca|cmp|%ecx,%edx
52|75ec|jne|+40
54|4889f8|mov|%rdi,%rax
57|c3|ret|
58|0f1f840000000000|nopl|0x0(%rax,%rax,1)
60|31ff|xor|%edi,%edi
62|4889f8|mov|%rdi,%rax
65|c3|ret|
""",
    "flags": """
0|488b4e08|mov|0x8(%rsi),%rcx
4|4883f907|cmp|$0x7,%rcx
8|766c|jbe|+76
a|488d41f8|lea|-0x8(%rcx),%rax
e|4883f803|cmp|$0x3,%rax
12|7662|jbe|+76
14|488b16|mov|(%rsi),%rdx
17|0fb6420a|movzbl|0xa(%rdx),%eax
1b|440fb64209|movzbl|0x9(%rdx),%r8d
20|48c1e010|shl|$0x10,%rax
24|49c1e008|shl|$0x8,%r8
28|4c09c0|or|%r8,%rax
2b|440fb64208|movzbl|0x8(%rdx),%r8d
30|0fb6520b|movzbl|0xb(%rdx),%edx
34|4c09c0|or|%r8,%rax
37|48c1e218|shl|$0x18,%rdx
3b|4809d0|or|%rdx,%rax
3e|488d50fb|lea|-0x5(%rax),%rdx
42|4883fa01|cmp|$0x1,%rdx
46|0f86a4010000|jbe|+1f0
4c|4883f804|cmp|$0x4,%rax
50|0f85ba010000|jne|+210
56|4881ff00100800|cmp|$0x81000,%rdi
5d|0f849a010000|je|+1fd
63|488d870000faff|lea|-0x60000(%rdi),%rax
6a|483dff0f0200|cmp|$0x20fff,%rax
70|0f866a010000|jbe|+1e0
76|488d8700f0ffff|lea|-0x1000(%rdi),%rax
7d|483dffff0000|cmp|$0xffff,%rax
83|0f8674010000|jbe|+1fd
89|4885ff|test|%rdi,%rdi
8c|0f846b010000|je|+1fd
92|488d8700f0feff|lea|-0x11000(%rdi),%rax
99|483dffff0000|cmp|$0xffff,%rax
9f|0f863b010000|jbe|+1e0
a5|4881ff00200400|cmp|$0x42000,%rdi
ac|0f842e010000|je|+1e0
b2|488d8700c0fbff|lea|-0x44000(%rdi),%rax
b9|483dff3f0000|cmp|$0x3fff,%rax
bf|0f861b010000|jbe|+1e0
c5|488d870000fbff|lea|-0x50000(%rdi),%rax
cc|483dffff0000|cmp|$0xffff,%rax
d2|0f8608010000|jbe|+1e0
d8|4881ff00100200|cmp|$0x21000,%rdi
df|0f84c8010000|je|+2ad
e5|4881ffff1f0200|cmp|$0x21fff,%rdi
ec|0f86c6010000|jbe|+2b8
f2|4883f957|cmp|$0x57,%rcx
f6|0f86bc010000|jbe|+2b8
fc|4c8b06|mov|(%rsi),%r8
ff|31c0|xor|%eax,%eax
101|31f6|xor|%esi,%esi
103|0f1f8000000000|nopl|0x0(%rax)
10a|66662e0f1f840000000000|data16|cs nopw 0x0(%rax,%rax,1)
115|66662e0f1f840000000000|data16|cs nopw 0x0(%rax,%rax,1)
120|410fb6540050|movzbl|0x50(%r8,%rax,1),%edx
126|8d0cc500000000|lea|0x0(,%rax,8),%ecx
12d|4883c001|add|$0x1,%rax
131|48d3e2|shl|%cl,%rdx
134|4809d6|or|%rdx,%rsi
137|4883f808|cmp|$0x8,%rax
13b|75e3|jne|+120
13d|4881c600200200|add|$0x22000,%rsi
144|4839f7|cmp|%rsi,%rdi
147|0f836b010000|jae|+2b8
14d|4881ef00200200|sub|$0x22000,%rdi
154|31c0|xor|%eax,%eax
156|31f6|xor|%esi,%esi
158|410fb6540040|movzbl|0x40(%r8,%rax,1),%edx
15e|8d0cc500000000|lea|0x0(,%rax,8),%ecx
165|4883c001|add|$0x1,%rax
169|48d3e2|shl|%cl,%rdx
16c|4809d6|or|%rdx,%rsi
16f|4883f808|cmp|$0x8,%rax
173|75e3|jne|+158
175|4839f7|cmp|%rsi,%rdi
178|0f822f010000|jb|+2ad
17e|31c0|xor|%eax,%eax
180|31f6|xor|%esi,%esi
182|0f1f840000000000|nopl|0x0(%rax,%rax,1)
18a|66662e0f1f840000000000|data16|cs nopw 0x0(%rax,%rax,1)
195|66662e0f1f840000000000|data16|cs nopw 0x0(%rax,%rax,1)
1a0|410fb6540048|movzbl|0x48(%r8,%rax,1),%edx
1a6|8d0cc500000000|lea|0x0(,%rax,8),%ecx
1ad|4883c001|add|$0x1,%rax
1b1|48d3e2|shl|%cl,%rdx
1b4|4809d6|or|%rdx,%rsi
1b7|4883f808|cmp|$0x8,%rax
1bb|75e3|jne|+1a0
1bd|48ba0300000000000080|movabs|$0x8000000000000003,%rdx
1c7|4839f7|cmp|%rsi,%rdi
1ca|48b80100000000000080|movabs|$0x8000000000000001,%rax
1d4|480f43c2|cmovae|%rdx,%rax
1d8|c3|ret|
1d9|0f1f8000000000|nopl|0x0(%rax)
1e0|48b80300000000000080|movabs|$0x8000000000000003,%rax
1ea|c3|ret|
1eb|0f1f440000|nopl|0x0(%rax,%rax,1)
1f0|4881ff00000e00|cmp|$0xe0000,%rdi
1f7|0f8566feffff|jne|+63
1fd|48b80100000000000080|movabs|$0x8000000000000001,%rax
207|c3|ret|
208|0f1f840000000000|nopl|0x0(%rax,%rax,1)
210|4883f803|cmp|$0x3,%rax
214|0f85a1000000|jne|+2bb
21a|4881ffffff0f00|cmp|$0xfffff,%rdi
221|0f87befeffff|ja|+e5
227|f7c7ff0f0000|test|$0xfff,%edi
22d|0f8530feffff|jne|+63
233|4881ff00100800|cmp|$0x81000,%rdi
23a|74c1|je|+1fd
23c|488d8700c0f7ff|lea|-0x84000(%rdi),%rax
243|483dff3f0000|cmp|$0x3fff,%rax
249|7695|jbe|+1e0
24b|4881ff00200800|cmp|$0x82000,%rdi
252|748c|je|+1e0
254|488d870070f7ff|lea|-0x89000(%rdi),%rax
25b|483dff3f0000|cmp|$0x3fff,%rax
261|0f8679ffffff|jbe|+1e0
267|488d870000f4ff|lea|-0xc0000(%rdi),%rax
26e|483dffff0000|cmp|$0xffff,%rax
274|0f8666ffffff|jbe|+1e0
27a|4881ffffff0800|cmp|$0x8ffff,%rdi
281|0f86dcfdffff|jbe|+63
287|488d870000f7ff|lea|-0x90000(%rdi),%rax
28e|483dffff0100|cmp|$0x1ffff,%rax
294|0f8646ffffff|jbe|+1e0
29a|488d870000f5ff|lea|-0xb0000(%rdi),%rax
2a1|483dff1f0000|cmp|$0x1fff,%rax
2a7|0f8718feffff|ja|+c5
2ad|b801000000|mov|$0x1,%eax
2b2|c3|ret|
2b3|0f1f440000|nopl|0x0(%rax,%rax,1)
2b8|31c0|xor|%eax,%eax
2ba|c3|ret|
2bb|4883f801|cmp|$0x1,%rax
2bf|0f86b1fdffff|jbe|+76
2c5|e999fdffff|jmp|+63
""",
    "guard": """
0|4801fe|add|%rdi,%rsi
3|7210|jb|+15
5|4801d1|add|%rdx,%rcx
8|720b|jb|+15
a|b801000000|mov|$0x1,%eax
f|4839f2|cmp|%rsi,%rdx
12|720c|jb|+20
14|c3|ret|
15|31c0|xor|%eax,%eax
17|c3|ret|
18|0f1f840000000000|nopl|0x0(%rax,%rax,1)
20|4839cf|cmp|%rcx,%rdi
23|0f93c0|setae|%al
26|c3|ret|
""",
    "entry": """
0|53|push|%rbx
1|4c8b07|mov|(%rdi),%r8
4|488d1500000000|lea|@levels,%rdx
b|49b99f0f00000000f0ff|movabs|$0xfff0000000000f9f,%r9
15|488b7f08|mov|0x8(%rdi),%rdi
19|4c8d5a0c|lea|0xc(%rdx),%r11
1d|49ba00f0ffffffff0f00|movabs|$0xffffffffff000,%r10
27|4c89c0|mov|%r8,%rax
2a|48c1e70c|shl|$0xc,%rdi
2e|4c01c7|add|%r8,%rdi
31|8b0a|mov|(%rdx),%ecx
33|4889f3|mov|%rsi,%rbx
36|48d3eb|shr|%cl,%rbx
39|4889d9|mov|%rbx,%rcx
3c|81e1ff010000|and|$0x1ff,%ecx
42|488b04c8|mov|(%rax,%rcx,8),%rax
46|4889c1|mov|%rax,%rcx
49|4c21c9|and|%r9,%rcx
4c|4883f903|cmp|$0x3,%rcx
50|752e|jne|+80
52|4c21d0|and|%r10,%rax
55|4c39c0|cmp|%r8,%rax
58|7226|jb|+80
5a|4839f8|cmp|%rdi,%rax
5d|7321|jae|+80
5f|4883c204|add|$0x4,%rdx
63|4c39da|cmp|%r11,%rdx
66|75c9|jne|+31
68|48c1ee0c|shr|$0xc,%rsi
6c|5b|pop|%rbx
6d|81e6ff010000|and|$0x1ff,%esi
73|488b04f0|mov|(%rax,%rsi,8),%rax
77|c3|ret|
78|0f1f840000000000|nopl|0x0(%rax,%rax,1)
80|31c0|xor|%eax,%eax
82|5b|pop|%rbx
83|c3|ret|
""",
    "window": """
0|48c1e60c|shl|$0xc,%rsi
4|4889f8|mov|%rdi,%rax
7|488d1500000000|lea|@levels,%rdx
e|49b89f0f00000000f0ff|movabs|$0xfff0000000000f9f,%r8
18|4801fe|add|%rdi,%rsi
1b|4c8d520c|lea|0xc(%rdx),%r10
1f|49b900f0ffffffff0f00|movabs|$0xffffffffff000,%r9
29|49bb000000000080ffff|movabs|$0xffff800000000000,%r11
33|8b0a|mov|(%rdx),%ecx
35|49d3eb|shr|%cl,%r11
38|4c89d9|mov|%r11,%rcx
3b|81e1ff010000|and|$0x1ff,%ecx
41|488b04c8|mov|(%rax,%rcx,8),%rax
45|4889c1|mov|%rax,%rcx
48|4c21c1|and|%r8,%rcx
4b|4883f903|cmp|$0x3,%rcx
4f|751f|jne|+70
51|4c21c8|and|%r9,%rax
54|4839f8|cmp|%rdi,%rax
57|7217|jb|+70
59|4839f0|cmp|%rsi,%rax
5c|7312|jae|+70
5e|4883c204|add|$0x4,%rdx
62|4c39d2|cmp|%r10,%rdx
65|75c2|jne|+29
67|c3|ret|
68|0f1f840000000000|nopl|0x0(%rax,%rax,1)
70|31c0|xor|%eax,%eax
72|c3|ret|
""",
}


def fixture(specification, analyze=True):
    """Build machine-shaped fixtures only; the expected denials are below."""
    starts = {100 * index: name for index, name in enumerate(specification)}
    addresses = {name: address for address, name in starts.items()}
    symbols, code = {}, {}
    for name, rows in specification.items():
        base = addresses[name]
        symbols[name] = decoder.Symbol(name, base, len(rows), 1, 2)
        for index, (op, args) in enumerate(rows):
            if args.startswith("@"):
                target, _, offset = args[1:].partition("+")
                args = f"{addresses[target] + int(offset or 0):x} <{target}>"
            code[base + index] = decoder.Instruction(base + index, 1, op, args)
    functions = (
        {name: decoder.analyze_function(symbol, code, starts) for name, symbol in symbols.items()} if analyze else {}
    )
    return functions, symbols, code, starts


class Admission(unittest.TestCase):
    @staticmethod
    def paired_object(linked=False):
        # Exact independent symbol inventory from unadmitted attempt002.
        names = [
            "_ZZNK6aurora4uefi10PageTables16verify_graphicalEmRKNS0_5BytesEPKNS0_18LocalApicAdmissionEPKNS0_20FramebufferAdmissionEENKUlOT_mjmE1_clIRKSD_EEbSC_mjm",
            "_ZZNK6aurora4uefi10PageTables16verify_graphicalEmRKNS0_5BytesEPKNS0_18LocalApicAdmissionEPKNS0_20FramebufferAdmissionEENKUlOT_mjmE_clIRKSD_EEbSC_mjm",
        ]
        address = 0x67E0 if linked else 0
        strings = b"\0" + names[0].encode() + b"\0" + names[1].encode() + b"\0"
        offsets = [1, len(names[0]) + 2]
        raw = b"".join(struct.pack("<IBBHQQ", offset, 0x22, 2, 3, address, 866) for offset in offsets)
        sections = [(0,) * 10, (0, 2, 0, 0, 0, 48, 2, 0, 8, 24), (0, 3, 0, 0, 48, len(strings), 0, 0, 1, 0), (0,) * 10]
        symbols = [decoder.Symbol(name, address, 866, 3, 2) for name in names]
        return SimpleNamespace(
            type=2 if linked else 1,
            data=raw + strings,
            sections=sections,
            symbols=symbols,
            functions={row.name: row for row in symbols},
            relocations=[],
            section_data=lambda index: strings if index == 2 else b"",
            function_bytes=lambda symbol: b"\x90" * symbol.size,
        )

    @staticmethod
    def gcc16_single_object(linked=False):
        obj = Admission.paired_object(linked)
        name = graphical.PAIRED_ALIAS
        address = 0x8240 if linked else 0
        strings = b"\0" + name.encode() + b"\0"
        obj.data = struct.pack("<IBBHQQ", 1, 0x22, 2, 3, address, 932) + strings
        obj.sections = [
            (0,) * 10,
            (0, 2, 0, 0, 0, 24, 2, 0, 8, 24),
            (0, 3, 0, 0, 24, len(strings), 0, 0, 1, 0),
            (0,) * 10,
        ]
        obj.symbols = [decoder.Symbol(name, address, 932, 3, 2)]
        obj.functions = {name: obj.symbols[0]}
        obj.section_data = lambda index: strings if index == 2 else b""
        return obj

    def test_gcc16_single_definition_raw_metadata_binding(self):
        for linked in (False, True):
            obj = self.gcc16_single_object(linked)
            proof = graphical.paired_walker_evidence(obj)
            self.assertEqual(proof["canonical"], graphical.PAIRED_ALIAS)
            self.assertEqual(len(proof["definitions"]), 1)
            self.assertNotIn("aliases", proof)
            for field, value in (("size", 931), ("section", 0), ("kind", 0)):
                changed = self.gcc16_single_object(linked)
                row = changed.functions[graphical.PAIRED_ALIAS]
                values = dict(name=row.name, address=row.address, size=row.size, section=row.section, kind=row.kind)
                values[field] = value
                changed.functions[row.name] = decoder.Symbol(**values)
                with self.subTest(field=field), self.assertRaises(ValueError):
                    graphical.paired_walker_evidence(changed)
            for index, value in ((4, 0x12), (5, 0)):
                changed = self.gcc16_single_object(linked)
                raw = bytearray(changed.data)
                raw[index] = value
                changed.data = bytes(raw)
                with self.subTest(raw=index), self.assertRaises(ValueError):
                    graphical.paired_walker_evidence(changed)
            changed = self.gcc16_single_object(linked)
            row = changed.symbols[0]
            changed.symbols.append(decoder.Symbol("unproved_alias", row.address, row.size, row.section, row.kind))
            with self.assertRaises(ValueError):
                graphical.paired_walker_evidence(changed)
            changed = self.gcc16_single_object(linked)
            row = changed.symbols[0]
            changed.functions[graphical.PAIRED_WALK] = decoder.Symbol(
                graphical.PAIRED_WALK, row.address, row.size, row.section, row.kind
            )
            with self.assertRaises(ValueError):
                graphical.paired_walker_evidence(changed)
        with tempfile.TemporaryDirectory(prefix="gcc16-frame-controls-") as directory:
            root = Path(directory)
            (root / "objects").mkdir()
            location = "kernel/uefi/tables.hpp:1:1"
            signature = "exact single walker signature"
            (root / "objects/graphical-console.su").write_text(location + ":" + signature + "\t128\tstatic\n")
            label = signature + "\n" + location + "\n128 bytes (static)"
            graph = (
                'graph: { title: "kernel/uefi/graphical-console.cpp"\nnode: { title: '
                + json.dumps(graphical.PAIRED_ALIAS)
                + " label: "
                + json.dumps(label)
                + " }\n}"
            )
            obj, linked = self.gcc16_single_object(), self.gcc16_single_object(True)
            with (
                patch.object(graphical, "CPP_OBJECTS", ("graphical-console",)),
                patch.object(decoder, "Elf", return_value=obj),
            ):
                (root / "objects/graphical-console.ci").write_text(graph)
                frames, receipts, proof = graphical.graphical_cpp_frames(decoder, root, linked, graphical.PAIRED_ALIAS)
                self.assertEqual(frames, {graphical.PAIRED_ALIAS: 128})
                self.assertEqual(receipts[graphical.PAIRED_ALIAS][0]["compiler_symbol"], graphical.PAIRED_ALIAS)
                self.assertNotIn(graphical.PAIRED_WALK, linked.functions)
                for changed in (
                    graph.replace(graphical.PAIRED_ALIAS, graphical.PAIRED_WALK),
                    graph.replace("128 bytes", "136 bytes"),
                    graph.replace("tables.hpp:1:1", "tables.hpp:2:1"),
                    graph.replace(" }\n}", " }\n" + graph.splitlines()[1] + "\n}"),
                ):
                    (root / "objects/graphical-console.ci").write_text(changed)
                    with self.subTest(metadata=changed), self.assertRaises(ValueError):
                        graphical.graphical_cpp_frames(decoder, root, linked, graphical.PAIRED_ALIAS)

    def test_exact_paired_alias_raw_identity(self):
        evidence = graphical.paired_alias_evidence(self.paired_object())
        self.assertEqual(evidence["canonical"], graphical.PAIRED_WALK)
        self.assertEqual({row["name"] for row in evidence["aliases"]}, {graphical.PAIRED_WALK, graphical.PAIRED_ALIAS})
        for missing in [graphical.PAIRED_WALK, graphical.PAIRED_ALIAS]:
            obj = self.paired_object()
            del obj.functions[missing]
            with self.assertRaisesRegex(ValueError, "Missing exact"):
                graphical.paired_alias_evidence(obj)
        for field, value in [("address", 1), ("size", 865), ("section", 2), ("kind", 0)]:
            obj = self.paired_object()
            row = obj.functions[graphical.PAIRED_ALIAS]
            changed = dict(vars(row))
            changed[field] = value
            obj.functions[graphical.PAIRED_ALIAS] = decoder.Symbol(**changed)
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "Diverged"):
                graphical.paired_alias_evidence(obj)
        for name in ["arbitrary_alias", graphical.PAIRED_ALIAS + ".clone"]:
            obj = self.paired_object()
            obj.symbols.append(decoder.Symbol(name, 0, 866, 3, 2))
            with self.assertRaisesRegex(ValueError, "alias inventory"):
                graphical.paired_alias_evidence(obj)
        # Mutate either raw symbol independently: bind, visibility, type,
        # section, address and size must all agree with the parsed inventory.
        for entry in [0, 1]:
            for field, value in [(1, 0x12), (1, 0x20), (2, 0), (2, 3), (3, 2), (4, 1), (5, 865)]:
                obj = self.paired_object()
                raw = bytearray(obj.data)
                values = list(struct.unpack_from("<IBBHQQ", raw, entry * 24))
                values[field] = value
                struct.pack_into("<IBBHQQ", raw, entry * 24, *values)
                obj.data = bytes(raw)
                with (
                    self.subTest(entry=entry, field=field, value=value),
                    self.assertRaisesRegex(ValueError, "raw identity"),
                ):
                    graphical.paired_alias_evidence(obj)
        obj = self.paired_object()
        obj.data = obj.data[:24] + obj.data[:24] + obj.data[48:]
        with self.assertRaisesRegex(ValueError, "Duplicate or missing"):
            graphical.paired_alias_evidence(obj)

    def test_exact_compiler_metadata_keeps_session_kinds_and_methods_distinct(self):
        # Equal locations and sizes must still retain exact template signatures
        # and assembler symbols. No demangled name or typedef guessing occurs.
        records, nodes, symbols = [], [], {}
        source = "kernel/uefi/graphical-console.cpp"
        for space, transport in (("console", "ServiceTransport"), ("display", "DisplayTransport")):
            for method in ("open", "validate"):
                symbol = "_Z_" + space + "_" + method
                signature = f"aurora::{space}::Session<{transport}, ServicePlatform>::{method}()"
                location = "kernel/" + space + "-session.hpp:1:1"
                records.append(location + ":" + signature + "\t16\tstatic\n")
                label = signature + "\n" + location + "\n16 bytes (static)"
                nodes.append("node: { title: " + json.dumps(symbol) + " label: " + json.dumps(label) + " }")
                symbols[symbol] = object()
        text = "graph: { title: " + json.dumps(source) + "\n" + "\n".join(nodes) + "\n}"
        rows = decoder.stack_rows("".join(records))
        mapped = decoder.callgraph_frames(text, rows, symbols, source)
        self.assertEqual(set(mapped), set(symbols))
        self.assertEqual(len({row.identity for row in mapped.values()}), 4)
        for changed in (
            text.replace(nodes[0], nodes[1]),
            text.replace(nodes[0], ""),
            text.replace("16 bytes (static)", "32 bytes (static)", 1),
            text.replace("-session.hpp:1:1", "-session.hpp:2:1", 1),
            text.replace("_Z_console_open", "_Z_display_open", 1),
            text.replace("ServiceTransport", "DisplayTransport", 1),
        ):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                decoder.callgraph_frames(changed, rows, symbols, source)
        with self.assertRaises(ValueError):
            decoder.stack_rows("".join(records) + records[0])

    def test_paired_aliases_both_associate_but_have_one_compiler_frame(self):
        with tempfile.TemporaryDirectory(prefix="paired-frame-controls-") as directory:
            root = Path(directory)
            (root / "objects").mkdir()
            signature = "paired walker exact source signature"
            location = "kernel/uefi/tables.hpp:1:1"
            line = location + ":" + signature + "\t128\tstatic\n"
            (root / "objects/graphical-console.su").write_text(line)
            label = signature + "\n" + location + "\n128 bytes (static)"
            graph = (
                'graph: { title: "kernel/uefi/graphical-console.cpp"\n'
                + "node: { title: "
                + json.dumps(graphical.PAIRED_WALK)
                + " label: "
                + json.dumps(label)
                + " }\n}"
            )
            (root / "objects/graphical-console.ci").write_text(graph)
            obj, linked = self.paired_object(), self.paired_object(linked=True)
            with (
                patch.object(graphical, "CPP_OBJECTS", ("graphical-console",)),
                patch.object(decoder, "Elf", return_value=obj),
                patch.object(decoder, "associate_object", wraps=decoder.associate_object) as associate,
            ):
                for raw_symbol in (graphical.PAIRED_WALK, graphical.PAIRED_ALIAS):
                    (root / "objects/graphical-console.ci").write_text(graph.replace(graphical.PAIRED_WALK, raw_symbol))
                    frames, receipts, aliases = graphical.graphical_cpp_frames(decoder, root, linked)
                    self.assertEqual(frames, {graphical.PAIRED_WALK: 128})
                    self.assertEqual(receipts[graphical.PAIRED_WALK][0]["source"], "kernel/uefi/tables.hpp")
                    self.assertEqual(receipts[graphical.PAIRED_WALK][0]["compiler_symbol"], raw_symbol)
                    self.assertEqual(len(aliases), 1)
                    self.assertEqual(
                        {call.args[2].name for call in associate.call_args_list},
                        {graphical.PAIRED_WALK, graphical.PAIRED_ALIAS},
                    )
                    self.assertIn(graphical.PAIRED_ALIAS, linked.functions)
                node = graph.splitlines()[1]
                for changed in (
                    "",
                    graph.replace(graphical.PAIRED_WALK, "unproved_alias"),
                    graph.replace(node, node + "\n" + node.replace(graphical.PAIRED_WALK, graphical.PAIRED_ALIAS)),
                    graph.replace(node, node + "\n" + node),
                    graph.replace(" label:", '.clone" label:', 1),
                    graph.replace(" }\n}", " shape : ellipse }\n}"),
                    graph.replace("128 bytes", "136 bytes"),
                    graph.replace("tables.hpp:1:1", "tables.hpp:2:1"),
                ):
                    (root / "objects/graphical-console.ci").write_text(changed)
                    with self.subTest(changed=changed), self.assertRaises(ValueError):
                        graphical.graphical_cpp_frames(decoder, root, linked)
                (root / "objects/graphical-console.ci").write_text(
                    graph.replace(graphical.PAIRED_WALK, graphical.PAIRED_ALIAS)
                )
                # Metadata must not let an unproved or nonidentical alias reach
                # the shared frame join. The actual raw .ci spelling is valid.
                original = obj.functions.pop(graphical.PAIRED_ALIAS)
                with patch.object(
                    decoder, "object_stack_rows", side_effect=AssertionError("unproved alias reached join")
                ):
                    with self.assertRaisesRegex(ValueError, "Missing exact"):
                        graphical.graphical_cpp_frames(decoder, root, linked)
                    obj.functions[graphical.PAIRED_ALIAS] = decoder.Symbol(
                        original.name, original.address + 1, original.size, original.section, original.kind
                    )
                    with self.assertRaisesRegex(ValueError, "Diverged"):
                        graphical.graphical_cpp_frames(decoder, root, linked)
                obj.functions[graphical.PAIRED_ALIAS] = original
                old_bytes = linked.function_bytes
                linked.function_bytes = lambda symbol: (
                    b"\xcc" * symbol.size if symbol.name == graphical.PAIRED_ALIAS else old_bytes(symbol)
                )
                with patch.object(
                    decoder, "object_stack_rows", side_effect=AssertionError("nonidentical alias reached join")
                ):
                    with self.assertRaisesRegex(ValueError, "instruction mismatch"):
                        graphical.graphical_cpp_frames(decoder, root, linked)

    def test_session_frames_require_distinct_source_and_object_ownership(self):
        frames = {symbol: 16 for symbol in graphical.SESSION_VALIDATORS}
        associations = {
            symbol: [dict(object="graphical-console.o", source=source, bytes=16, compiler_symbol=symbol)]
            for symbol, source in graphical.SESSION_VALIDATORS.items()
        }
        graphical.verify_session_frames(frames, associations)
        spelled = deepcopy(associations)
        for records in spelled.values():
            records[0]["source"] = records[0]["source"].replace("kernel/", "kernel/uefi/../")
        graphical.verify_session_frames(frames, spelled)
        for symbol, source in graphical.SESSION_VALIDATORS.items():
            missing = dict(frames)
            del missing[symbol]
            with self.assertRaises(ValueError):
                graphical.verify_session_frames(missing, associations)
            for records in (
                [],
                associations[symbol] * 2,
                [dict(object="graphical-console.o", source=source, bytes=16)],
                [dict(object="graphical-console.o", source=source, bytes=24, compiler_symbol=symbol)],
                [
                    dict(
                        object="graphical-console.o",
                        source=source,
                        bytes=16,
                        compiler_symbol=next(other for other in graphical.SESSION_VALIDATORS if other != symbol),
                    )
                ],
                [dict(object="console.o", source=source, bytes=16)],
                [dict(object="graphical-console.o", source="kernel/foreign.hpp", bytes=16)],
            ):
                changed = deepcopy(associations)
                changed[symbol] = records
                with self.assertRaises(ValueError):
                    graphical.verify_session_frames(frames, changed)

    def test_graphical_only_validator_emission_attributes(self):
        declaration = "    static auto validate(const void *grant, std::uint64_t generation, bool operation) -> void {"
        guard = (
            "#ifdef AURORA_UEFI_GRAPHICAL_CONSOLE\n"
            "    // Preserve two independently bound bootstrap authority frames in the paired profile.\n"
            "    [[gnu::noinline, gnu::noclone, gnu::noipa]]\n"
            "#endif\n"
        )

        def check(text):
            if text.count(declaration) != 1 or text.count(guard + declaration) != 1:
                raise ValueError("Missing exact graphical-only validator emission declaration")
            if text.count("gnu::noipa") != 1:
                raise ValueError("Ambiguous validator emission attributes")

        for space in ("console", "display"):
            text = (ROOT / "kernel" / (space + "-session.hpp")).read_text()
            check(text)
            for changed in (
                text.replace(guard, ""),
                text.replace("gnu::noipa", "gnu::noinline"),
                text.replace("#ifdef AURORA_UEFI_GRAPHICAL_CONSOLE", "#if 1"),
                text.replace("#ifdef AURORA_UEFI_GRAPHICAL_CONSOLE", "#ifdef AURORA_UEFI_CONSOLE"),
                text.replace(guard, guard + guard),
            ):
                with self.subTest(space=space), self.assertRaises(ValueError):
                    check(changed)

    def test_authorized_memory_push_reads_old_rsp_before_allocation(self):
        name, base = "bounded_memory_push", 0x1000
        symbol = decoder.Symbol(name, base, 17, 1, 2)
        code = {
            base: decoder.Instruction(base, 4, "sub", "$0x18,%rsp"),
            base + 4: decoder.Instruction(base + 4, 4, "push", "0x8(%rsp)"),
            base + 8: decoder.Instruction(base + 8, 4, "push", "0x18(%rsp)"),
            base + 12: decoder.Instruction(base + 12, 4, "add", "$0x28,%rsp"),
            base + 16: decoder.Instruction(base + 16, 1, "ret", ""),
        }
        permit = dict(owner=name, sites={base + 4: 8, base + 8: 24})
        result = decoder.analyze_function(symbol, code, {base: name}, memory_pushes=permit)
        self.assertEqual(result["local_peak"], 48)
        self.assertEqual(
            [(row["depth_before"], row["source_old_rsp"], row["depth_after"]) for row in result["stack_memory_pushes"]],
            [(24, 8, 32), (32, 24, 40)],
        )
        self.assertEqual(result["returns"], 1)
        with self.assertRaises(ValueError):
            decoder.analyze_function(symbol, code, {base: name})
        for changed in (
            [],
            dict(owner=name, sites=permit["sites"], extra=True),
            dict(owner=name, sites=[]),
            dict(owner=name, sites={base + 4: "8"}),
            dict(owner="other", sites=permit["sites"]),
            dict(owner=name, sites={}),
            dict(owner=name, sites={base - 4: 8}),
            dict(owner=name, sites={base + 4: -8}),
            dict(owner=name, sites={base + 4: 16}),
            dict(owner=name, sites={base + 4: 24, base + 8: 24}),
        ):
            with self.subTest(permit=changed), self.assertRaises(ValueError):
                decoder.analyze_function(symbol, code, {base: name}, memory_pushes=changed)
        for address, op, args in (
            (base, "sub", "$0x8,%rsp"),
            (base + 4, "push", "0x8(%rbp)"),
            (base + 4, "push", "0x8(%rsp,%rax,1)"),
            (base + 4, "pushw", "0x8(%rsp)"),
            (base + 12, "add", "$0x20,%rsp"),
        ):
            changed = dict(code)
            row = code[address]
            changed[address] = decoder.Instruction(address, row.size, op, args)
            with self.subTest(instruction=(address, op, args)), self.assertRaises(ValueError):
                decoder.analyze_function(symbol, changed, {base: name}, memory_pushes=permit)
        # The authorized source must end below the incoming return address at
        # the OLD RSP. Checking after the push would incorrectly accept this.
        short = decoder.Symbol(name, base, 13, 1, 2)
        edge = {
            base: decoder.Instruction(base, 4, "sub", "$0x8,%rsp"),
            base + 4: code[base + 4],
            base + 8: decoder.Instruction(base + 8, 4, "add", "$0x10,%rsp"),
            base + 12: decoder.Instruction(base + 12, 1, "ret", ""),
        }
        with self.assertRaisesRegex(ValueError, "pre-push"):
            decoder.analyze_function(short, edge, {base: name}, memory_pushes=dict(owner=name, sites={base + 4: 8}))
        branched = {
            base: decoder.Instruction(base, 4, "sub", "$0x18,%rsp"),
            base + 4: decoder.Instruction(base + 4, 2, "jne", f"{base + 12:x} <skip>"),
            base + 6: decoder.Instruction(base + 6, 4, "push", "0x8(%rsp)"),
            base + 10: decoder.Instruction(base + 10, 2, "jmp", f"{base + 16:x} <join>"),
            base + 12: decoder.Instruction(base + 12, 4, "nopl", "0x0(%rax)"),
            base + 16: decoder.Instruction(base + 16, 4, "push", "0x18(%rsp)"),
            base + 20: decoder.Instruction(base + 20, 4, "add", "$0x28,%rsp"),
            base + 24: decoder.Instruction(base + 24, 1, "ret", ""),
        }
        with self.assertRaises(ValueError):
            decoder.analyze_function(
                decoder.Symbol(name, base, 25, 1, 2),
                branched,
                {base: name},
                memory_pushes=dict(owner=name, sites={base + 6: 8, base + 16: 24}),
            )
        extended = dict(code)
        extended[base + 17] = decoder.Instruction(base + 17, 4, "push", "0x8(%rsp)")
        with self.assertRaisesRegex(ValueError, "Unused"):
            decoder.analyze_function(
                decoder.Symbol(name, base, 21, 1, 2),
                extended,
                {base: name},
                memory_pushes=dict(owner=name, sites={**permit["sites"], base + 17: 8}),
            )

    def test_graphical_memory_push_sites_follow_operands_and_owner(self):
        base, name = 0x2000, graphical.STACK_MEMORY_PUSH_OWNER
        for size, offsets, displacements in (
            (128, (16, 32), (8, 24)),
            (384, (64, 144), (8, 40)),
            (512, (40, 288), (16, 120)),
        ):
            owner = decoder.Symbol(name, base, size, 1, 2)
            payload, code = bytearray(base + size), {}
            for offset, displacement in zip(offsets, displacements):
                address = base + offset
                payload[address : address + 4] = bytes((0xFF, 0x74, 0x24, displacement))
                code[address] = decoder.Instruction(address, 4, "push", hex(displacement) + "(%rsp)")
            permits, receipts = graphical.stack_memory_push_evidence({name: owner}, code, bytes(payload))
            self.assertEqual(permits[name]["sites"], dict(zip((base + value for value in offsets), displacements)))
            self.assertEqual([row["offset"] for row in receipts], list(offsets))
            for symbols in (
                {},
                {name: decoder.Symbol(name, base, offsets[-1] + 3, 1, 2)},
                {name: owner, "alias": decoder.Symbol("alias", base, size, 1, 2)},
            ):
                with self.subTest(symbols=symbols), self.assertRaises(ValueError):
                    graphical.stack_memory_push_evidence(symbols, code, bytes(payload))
        self.assertEqual(graphical.stack_memory_push_evidence({}, {}, b""), ({}, []))
        # A compiler may use only register pushes; no memory authorization is needed.
        self.assertEqual(graphical.stack_memory_push_evidence({name: owner}, {}, b""), ({}, []))
        for address, row in code.items():
            changed = bytearray(payload)
            changed[address] ^= 1
            with self.assertRaises(ValueError):
                graphical.stack_memory_push_evidence({name: owner}, code, bytes(changed))
            for op, args, size in (
                ("push", "0x8(%rbp)", 4),
                ("push", "0x8(%rsp,%rax,1)", 4),
                ("push", "-0x8(%rsp)", 4),
                ("push", "0x80(%rsp)", 4),
                ("push", "0x1(%rsp)", 4),
                ("push", "0x0(%rsp)", 4),
                ("pushw", row.args, 4),
                ("push", row.args, 5),
            ):
                changed_code = dict(code)
                changed_code[address] = decoder.Instruction(address, size, op, args)
                with self.subTest(form=(op, args, size)), self.assertRaises(ValueError):
                    graphical.stack_memory_push_evidence({name: owner}, changed_code, bytes(payload))
        missing = dict(code)
        del missing[address]
        with self.assertRaises(ValueError):
            graphical.stack_memory_push_evidence({name: owner}, missing, bytes(payload))
        extra = dict(code)
        extra[base + 8] = decoder.Instruction(base + 8, 4, "push", "0x8(%rsp)")
        with self.assertRaises(ValueError):
            graphical.stack_memory_push_evidence({name: owner}, extra, bytes(payload))

    def test_memory_push_full_width_bounds_and_stack_balance(self):
        base, name = 0x2000, graphical.STACK_MEMORY_PUSH_OWNER
        for displacement in (8, 16, 40, 120):
            depth = displacement + 8
            body = {
                base: decoder.Instruction(base, 4, "sub", "$" + hex(depth) + ",%rsp"),
                base + 4: decoder.Instruction(base + 4, 4, "push", hex(displacement) + "(%rsp)"),
                base + 8: decoder.Instruction(base + 8, 4, "add", "$" + hex(depth + 8) + ",%rsp"),
                base + 12: decoder.Instruction(base + 12, 1, "ret", ""),
            }
            sym = decoder.Symbol(name, base, 13, 1, 2)
            grant = dict(owner=name, sites={base + 4: displacement})
            result = decoder.analyze_function(sym, body, {base: name}, memory_pushes=grant)
            self.assertEqual(result["stack_memory_pushes"][0]["depth_before"], depth)
            with self.assertRaises(ValueError):
                decoder.analyze_function(sym, body, {base: name})
            for frame, release, error in ((depth - 8, depth, "pre-push"), (depth, depth + 16, "Unbalanced")):
                changed = dict(body)
                changed[base] = decoder.Instruction(base, 4, "sub", f"${frame:#x},%rsp")
                changed[base + 8] = decoder.Instruction(base + 8, 4, "add", f"${release:#x},%rsp")
                with self.subTest(displacement=displacement, error=error), self.assertRaisesRegex(ValueError, error):
                    decoder.analyze_function(sym, changed, {base: name}, memory_pushes=grant)

    def test_memory_push_copies_saved_slot_without_overwriting_it(self):
        name = "saved_slot_read"
        code = {
            0: decoder.Instruction(0, 1, "push", "%rbp"),
            1: decoder.Instruction(1, 2, "push", "%r14"),
            3: decoder.Instruction(3, 4, "push", "0x8(%rsp)"),
            7: decoder.Instruction(7, 1, "pop", "%rax"),
            8: decoder.Instruction(8, 2, "pop", "%r14"),
            10: decoder.Instruction(10, 1, "pop", "%rbp"),
            11: decoder.Instruction(11, 1, "ret", ""),
        }
        result = decoder.analyze_function(
            decoder.Symbol(name, 0, 12, 1, 2), code, {0: name}, memory_pushes=dict(owner=name, sites={3: 8})
        )
        self.assertEqual(result["local_peak"], 32)
        self.assertEqual(result["returns"], 1)
        self.assertEqual(result["stack_memory_pushes"][0]["depth_before"], 16)

    def test_exact_generated_signed_division_pairs(self):
        owners = (
            "__au_v_m1_24kernel_graphical_console_n0__d9draw_cell",
            "__au_m_m2_7console13session_files_n2_7console12SessionFiles_d6submit",
        )
        symbols = {name: decoder.Symbol(name, base, 10, 1, 2) for name, base in zip(owners, (0, 16))}
        pair = bytes.fromhex("489949f7fb")
        payload = pair * 2 + b"\x90" * 6 + pair * 2
        rows = {}
        for base in (0, 5, 16, 21):
            rows[base] = decoder.Instruction(base, 2, "cqto", "")
            rows[base + 2] = decoder.Instruction(base + 2, 3, "idiv", "%r11")
        verify = lambda symbols, rows, payload: graphical.verify_generated_divisions(decoder, symbols, rows, payload)
        evidence = verify(symbols, rows, payload)
        self.assertEqual([item["owner"] for item in evidence], [owners[0]] * 2 + [owners[1]] * 2)
        with self.assertRaises(ValueError):
            verify(symbols, rows, None)
        for position in (*range(10), *range(16, 26)):
            changed = bytearray(payload)
            changed[position] ^= 1
            with self.subTest(position=position), self.assertRaises(ValueError):
                verify(symbols, rows, changed)
        for address, row in rows.items():
            changed = dict(rows)
            del changed[address]
            with self.assertRaises(ValueError):
                verify(symbols, changed, payload)
            for args in ["%rsp", "%r14", "(%r11)", "%rax,%rdx", "$0"]:
                changed = dict(rows)
                changed[address] = decoder.Instruction(row.address, row.size, row.op, args)
                with self.subTest(address=address, args=args), self.assertRaises(ValueError):
                    verify(symbols, changed, payload)
            for delta in [-1, 1]:
                changed = dict(rows)
                changed[address] = decoder.Instruction(row.address + delta, row.size, row.op, row.args)
                with self.assertRaises(ValueError):
                    verify(symbols, changed, payload)
        for owner, base in zip(owners, (0, 16)):
            for replacement in (None, (base + 1, 9), (base, 7), (base, 9)):
                changed = dict(symbols)
                if replacement is None:
                    del changed[owner]
                else:
                    changed[owner] = decoder.Symbol(owner, *replacement, 1, 2)
                with self.subTest(owner=owner, replacement=replacement), self.assertRaises(ValueError):
                    verify(changed, rows, payload)
            changed = dict(symbols)
            changed["foreign"] = changed.pop(owner)
            with self.assertRaises(ValueError):
                verify(changed, rows, payload)
        # Keeping the total pair count cannot move a third pair to one owner.
        changed = {owners[0]: decoder.Symbol(owners[0], 0, 21, 1, 2), owners[1]: decoder.Symbol(owners[1], 21, 5, 1, 2)}
        with self.assertRaises(ValueError):
            verify(changed, rows, payload)
        changed = dict(rows)
        changed[26] = decoder.Instruction(26, 2, "cqto", "")
        with self.assertRaises(ValueError):
            verify(symbols, changed, payload + b"\x48\x99")

    def test_generated_imports_and_module_identity(self):
        names = graphical.expected_language_functions()  # Fixture construction only.
        imports = [
            decoder.Symbol(name, 0, 0, 0, 0) for name in ["__au_runtime_console_next", "__au_runtime_display_pixel"]
        ]
        bindings = "\n".join(
            f"""1: 000000 1 FUNC {
                "GLOBAL HIDDEN"
                if name in {graphical.BRIDGE, graphical.VALUE_BRIDGE}
                else "GLOBAL DEFAULT"
                if name in REFLECTION
                else "LOCAL DEFAULT"
            } 1 {name}"""
            for name in sorted(names)
        )

        def verify(functions=names, symbols=imports, table=bindings):
            with patch.object(graphical.subprocess, "check_output", return_value=table):
                return graphical.verify_language_object(
                    SimpleNamespace(functions=functions, symbols=symbols, path=Path("fixture.o"))
                )

        verify()
        for changed in [
            imports[:-1],
            imports + [decoder.Symbol("__au_runtime_console_put", 0, 0, 0, 0)],
            imports + [decoder.Symbol("unknown", 0, 0, 0, 0)],
        ]:
            with self.assertRaisesRegex(ValueError, "import inventory"):
                verify(symbols=changed)
        for extra in ["__au_v_m1_22kernel_display_service_n0__d15display_service", "unexpected_host"]:
            with self.assertRaisesRegex(ValueError, "module/function"):
                verify(functions=names | {extra})
        for missing in sorted(names):
            with self.subTest(missing=missing), self.assertRaisesRegex(ValueError, "module/function inventory"):
                verify(functions=names - {missing})
        for table, reason in [
            (bindings.replace("LOCAL DEFAULT", "GLOBAL DEFAULT"), "private ELF binding"),
            (bindings.replace("GLOBAL HIDDEN", "GLOBAL DEFAULT"), "private ELF binding"),
            (bindings + "\n" + bindings.splitlines()[0], "Duplicate"),
            ("\n".join(bindings.splitlines()[1:]), "binding inventory"),
        ]:
            with self.assertRaisesRegex(ValueError, reason):
                verify(table=table)

    @staticmethod
    def reflection_fixture(name="aurora_reflect_size"):
        # Independent exact byte forms, including wide comparison, zero fallback
        # and two constant return arms. Branch offsets target whole return arms.
        base = 64
        specifications = [
            ("cmp", "$0x1,%rdi", "4883ff01"),
            ("je", "5b <reflection+0x1b>", "0f8411000000"),
            ("cmp", "$0x2dc6c1,%rdi", "4881ffc1c62d00"),
            ("je", "63 <reflection+0x23>", "0f840c000000"),
            ("xor", "%rax,%rax", "4831c0"),
            ("ret", "", "c3"),
            ("mov", "$0x8,%rax", "48c7c008000000"),
            ("ret", "", "c3"),
            ("mov", "$0x0,%rax", "48c7c000000000"),
            ("ret", "", "c3"),
        ]
        payload, rows = bytearray(base), []
        for op, args, hexbytes in specifications:
            raw = bytes.fromhex(hexbytes)
            rows.append(decoder.Instruction(len(payload), len(raw), op, args))
            payload.extend(raw)
        symbol = decoder.Symbol(name, base, len(payload) - base, 1, 2)
        return symbol, rows, bytes(payload)

    def test_reflection_lookup_exact_leaf_bytes_and_closure(self):
        for name in (*REFLECTION, "__au_reflect_s3_size", "__au_reflect_s19_field_count"):
            symbol, rows, payload = self.reflection_fixture(name)
            result = graphical.verify_reflection_body(decoder, symbol, rows, payload)
            self.assertEqual((result["cases"], result["calls"], result["data_accesses"]), (2, 0, 0))
        # An internal fail-stop arm is also data-only; no branch may escape it.
        symbol, rows, payload = self.reflection_fixture()
        trap = decoder.Instruction(rows[8].address, 2, "ud2", "")
        changed = rows[:8] + [trap]
        stopped = payload[: trap.address] + bytes.fromhex("0f0b")
        symbol = decoder.Symbol(symbol.name, symbol.address, len(stopped) - symbol.address, 1, 2)
        graphical.verify_reflection_body(decoder, symbol, changed, stopped)

    def test_reflection_rejects_authority_memory_and_control_injection(self):
        symbol, baseline, payload = self.reflection_fixture()
        graphical.verify_reflection_body(decoder, symbol, baseline, payload)
        changes = [
            (0, "cmp", "$0x1,(%rdi)"),
            (0, "cmp", "$0x1,%rsi"),
            (0, "call", "100 <__au_runtime_display_pixel>"),
            (0, "syscall", ""),
            (1, "jne", baseline[1].args),
            (4, "xor", "%rdi,%rdi"),
            (4, "xor", "%rax,(%rdi)"),
            (6, "mov", "(%rdi),%rax"),
            (6, "mov", "$0x8,(%rdi)"),
            (6, "lea", "(%rip),%rax"),
            (6, "mov", "$0x8,%rdi"),
            (6, "call", "100 <__au_runtime_console_next>"),
            (6, "jmp", "100 <foreign>"),
            (7, "ret", "$0x8"),
            (7, "push", "%rax"),
            (8, "mov", "$0x80000000,%rax"),
        ]
        for index, op, args in changes:
            rows = list(baseline)
            old = rows[index]
            rows[index] = decoder.Instruction(old.address, old.size, op, args)
            with self.subTest(index=index, op=op, args=args), self.assertRaises(ValueError):
                graphical.verify_reflection_body(decoder, symbol, rows, payload)
        for index in (0, 1, 4, 6, 7):
            raw = bytearray(payload)
            raw[baseline[index].address] ^= 1
            with self.subTest(byte_index=index), self.assertRaises(ValueError):
                graphical.verify_reflection_body(decoder, symbol, baseline, bytes(raw))
        # Coherent byte+decoded mutations, so rejection cannot rely on disagreement.
        for target in (
            0,
            baseline[1].address,
            baseline[0].address,
            baseline[7].address,
            baseline[8].address,
            len(payload) + 16,
        ):
            rows = list(baseline)
            old = rows[1]
            rows[1] = decoder.Instruction(old.address, old.size, "je", f"{target:x} <mutated>")
            raw = bytearray(payload)
            raw[old.address + 2 : old.address + 6] = (target - old.address - old.size).to_bytes(
                4, "little", signed=True
            )
            with self.subTest(target=target), self.assertRaises(ValueError):
                graphical.verify_reflection_body(decoder, symbol, rows, bytes(raw))
        for rows in (baseline[:-1], baseline[1:], baseline + [baseline[-1]]):
            with self.assertRaises(ValueError):
                graphical.verify_reflection_body(decoder, symbol, rows, payload)
        for name in ("aurora_reflect_extra", "__au_reflect_s0_size", "__au_reflect_s01_size", "__au_reflect_s3_put"):
            foreign = decoder.Symbol(name, symbol.address, symbol.size, 1, 2)
            with self.subTest(name=name), self.assertRaises(ValueError):
                graphical.verify_reflection_body(decoder, foreign, baseline, payload)

    def test_reflection_helper_exact_inventory_and_binding(self):
        self.assertEqual(graphical.REFLECTION_HELPERS, frozenset(REFLECTION))
        names = graphical.expected_language_functions()
        imports = [
            decoder.Symbol(name, 0, 0, 0, 0) for name in ("__au_runtime_console_next", "__au_runtime_display_pixel")
        ]

        def binding(name):
            return (
                "GLOBAL HIDDEN"
                if name in (graphical.BRIDGE, graphical.VALUE_BRIDGE)
                else ("GLOBAL DEFAULT" if name in REFLECTION else "LOCAL DEFAULT")
            )

        table = "\n".join(f"""1: 000000 1 FUNC {binding(name)} 1 {name}""" for name in sorted(names))

        def verify(rows=table, functions=names, symbols=imports):
            with patch.object(graphical.subprocess, "check_output", return_value=rows):
                return graphical.verify_language_object(
                    SimpleNamespace(functions=functions, symbols=symbols, path=Path("fixture.o"))
                )

        verify()
        for name in REFLECTION:
            for changed in ("GLOBAL HIDDEN", "LOCAL DEFAULT", "WEAK DEFAULT"):
                mutant = table.replace(f"GLOBAL DEFAULT 1 {name}", f"{changed} 1 {name}")
                with self.assertRaises(ValueError):
                    verify(rows=mutant)
            with self.assertRaises(ValueError):
                verify(symbols=imports + [decoder.Symbol(name, 0, 0, 0, 0)])
            with self.assertRaises(ValueError):
                verify(functions=names - {name})
        for extra in ("aurora_reflect_address", "__au_reflect_s7_size", "__au_reflect_s1_address"):
            with self.assertRaises(ValueError):
                verify(functions=names | {extra})

    def test_provisional_six_qword_pixel_and_value_bridge_machine_contract(self):
        # Entry stack touch follows retained consumer.s; linked disassembly and
        # the remaining synthetic ABI fixture still require allocated execution.
        entry = [
            ("push", "%rbp"),
            ("mov", "%rsp,%rbp"),
            ("sub", "$0x80,%rsp"),
            ("orq", "$0x0,(%rsp)"),
            ("mov", "%r11,-0x8(%rbp)"),
        ]
        read_indexes, write_indexes = [], []
        destinations = iter([0x18, 0x10, 0x28, 0x20, 0x30, 0x38])
        for group in [(0, 8), (16, 24), (32,), (40,)]:
            entry.append(("mov", "-0x8(%rbp),%r11"))
            for offset in group:
                read_indexes.append(len(entry))
                write_indexes.append(len(entry) + 1)
                entry += [
                    ("mov", ("" if offset == 0 else hex(offset)) + "(%r11),%rax"),
                    ("mov", f"%rax,-0x{next(destinations):x}(%rbp)"),
                ]
        pixel_name = "__au_v_m1_24kernel_graphical_console_pixel_fixture"
        pixel_base = 3
        pixel = [("push", "%rbp"), ("mov", "%rsp,%rbp"), ("sub", "$0x80,%rsp")]
        pixel += [("mov", "-0x40(%rbp),%rdi"), ("mov", "-0x38(%rbp),%rsi")]
        pixel += [("pop", r) for r in ["%r10", "%r9", "%r8", "%rcx", "%rdx"]]
        pixel += [
            ("sub", "$0x8,%rsp"),
            ("mov", "%r10,(%rsp)"),
            ("call", "@__au_runtime_display_pixel"),
            ("add", "$0x8,%rsp"),
            ("cmp", "$0x1,%rax"),
            ("ja", "@" + pixel_name + "+18"),
            ("leave", ""),
            ("ret", ""),
            ("ud2", ""),
        ]
        graph = {
            graphical.ENTRY: entry,
            graphical.VALUE_BRIDGE: [("jmp", "@" + graphical.VALUE_ENTRY)],
            graphical.VALUE_ENTRY: [("ret", "")],
            pixel_name: pixel,
            "__au_runtime_display_pixel": [("ret", "")],
        }

        def verify(rows, live_bytes=16):
            _, symbols, code, starts = fixture(rows, analyze=False)
            functions = {
                name: {
                    "calls": [
                        {"address": row.address, "live_bytes": live_bytes}
                        for row in code.values()
                        if symbol.address <= row.address < symbol.address + symbol.size and row.op == "call"
                    ]
                }
                for name, symbol in symbols.items()
            }
            return graphical.verify_private_abi(
                decoder,
                SimpleNamespace(functions=symbols),
                code,
                starts,
                {graphical.ENTRY, graphical.VALUE_BRIDGE, graphical.VALUE_ENTRY, pixel_name},
                functions,
            )

        verify(graph)
        # Missing, altered-width/opcode/value/address and displaced touches
        # must fail at the exact prologue boundary, not be skipped generically.
        changed = deepcopy(graph)
        del changed[graphical.ENTRY][3]
        with self.assertRaisesRegex(ValueError, "paired entry stack touch"):
            verify(changed)
        for operation in [
            ("nop", ""),
            ("orl", "$0x0,(%rsp)"),
            ("orq", "$0x1,(%rsp)"),
            ("orq", "$0x0,0x8(%rsp)"),
            ("orq", "$0x0,-0x8(%rsp)"),
            ("orq", "$0x0,(%rbp)"),
            ("orq", "$0x0,%rsp"),
        ]:
            changed = deepcopy(graph)
            changed[graphical.ENTRY][3] = operation
            with self.subTest(stack_touch=operation), self.assertRaisesRegex(ValueError, "paired entry stack touch"):
                verify(changed)
        changed = deepcopy(graph)
        changed[graphical.ENTRY][3:5] = list(reversed(changed[graphical.ENTRY][3:5]))
        with self.assertRaisesRegex(ValueError, "paired entry stack touch"):
            verify(changed)
        changed = deepcopy(graph)
        changed[graphical.ENTRY].insert(4, ("orq", "$0x0,(%rsp)"))
        with self.assertRaisesRegex(ValueError, "private record save"):
            verify(changed)
        for operation in [("call", "@" + graphical.VALUE_ENTRY), ("jmp", "@" + graphical.ENTRY), ("jmp", "*%rax")]:
            changed = deepcopy(graph)
            changed[graphical.VALUE_BRIDGE] = [operation]
            with self.assertRaisesRegex(ValueError, "value-only private bridge|direct"):
                verify(changed)
        changed = deepcopy(graph)
        changed[graphical.VALUE_BRIDGE].append(("ret", ""))
        with self.assertRaisesRegex(ValueError, "value-only private bridge"):
            verify(changed)
        for index in read_indexes:
            changed = deepcopy(graph)
            changed[graphical.ENTRY][index] = ("mov", "(%r11),%eax")
            with self.assertRaisesRegex(ValueError, "qword/width/order"):
                verify(changed)
        for index in write_indexes:
            changed = deepcopy(graph)
            changed[graphical.ENTRY][index] = ("mov", "%rax,-0x8(%rbp)")
            with self.assertRaisesRegex(ValueError, "parameter slot"):
                verify(changed)
        for destination in ["-0x9", "-0x11", "-0x88", "-0x0"]:
            changed = deepcopy(graph)
            changed[graphical.ENTRY][write_indexes[0]] = ("mov", f"%rax,{destination}(%rbp)")
            with self.assertRaisesRegex(ValueError, "Overlapping, unaligned or unallocated"):
                verify(changed)
        changed = deepcopy(graph)
        changed[pixel_name][pixel_base + 7] = ("sub", "$0x10,%rsp")
        changed[pixel_name][pixel_base + 10] = ("add", "$0x10,%rsp")
        with self.assertRaisesRegex(ValueError, "Misaligned pixel SysV"):
            verify(changed, live_bytes=24)
        for grant, generation in [("-0x41", "-0x39"), ("-0x88", "-0x80")]:
            changed = deepcopy(graph)
            changed[pixel_name][pixel_base] = ("mov", grant + "(%rbp),%rdi")
            changed[pixel_name][pixel_base + 1] = ("mov", generation + "(%rbp),%rsi")
            with self.assertRaisesRegex(ValueError, "unaligned or outside helper frame"):
                verify(changed)
        for index, replacement in [(11, ("cmp", "$0x2,%rax")), (12, ("ja", "@" + pixel_name + "+17"))]:
            changed = deepcopy(graph)
            changed[pixel_name][pixel_base + index] = replacement
            with self.assertRaisesRegex(ValueError, "completion validation"):
                verify(changed)
        for index, replacement, reason in [
            (1, ("mov", "-0x40(%rbp),%rsi"), "grant/generation"),
            (2, ("pop", "%rax"), "scalar ABI"),
            (8, ("mov", "%rax,(%rsp)"), "seventh argument"),
            (10, ("add", "$0x10,%rsp"), "seventh argument"),
        ]:
            changed = deepcopy(graph)
            changed[pixel_name][pixel_base + index] = replacement
            with self.assertRaisesRegex(ValueError, reason):
                verify(changed)

    def test_object_bytes_size_and_relocation_inventory(self):
        symbol = decoder.Symbol("leaf", 0, 5, 1, 2)
        linked = SimpleNamespace(functions={"leaf": symbol}, function_bytes=lambda _: b"\xe8\x11\x22\x33\x44")
        obj = SimpleNamespace(relocations=[(1, 1, 2, 0, 0)], function_bytes=lambda _: b"\xe8\x00\x00\x00\x00")
        decoder.associate_object(linked, obj, symbol)
        for relocation in [(1, 1, 1, 0, 0), (1, 2, 2, 0, 0), (2, 1, 2, 0, 0)]:
            with self.assertRaises(ValueError):
                decoder.associate_object(
                    linked, SimpleNamespace(relocations=[relocation], function_bytes=obj.function_bytes), symbol
                )
        with self.assertRaises(ValueError):
            decoder.associate_object(
                linked,
                SimpleNamespace(relocations=obj.relocations, function_bytes=lambda _: b"\xe9\x00\x00\x00\x00"),
                symbol,
            )
        with self.assertRaises(ValueError):
            decoder.associate_object(linked, obj, decoder.Symbol("leaf", 0, 4, 1, 2))

    def test_unreviewed_graph_cycles_are_never_bounded_by_accident(self):
        for graph in [
            {"root": [("call", "@root"), ("ret", "")]},
            {"root": [("call", "@leaf"), ("ret", "")], "leaf": [("jmp", "@root")]},
        ]:
            functions, *_ = fixture(graph)
            with self.assertRaises(ValueError):
                graphical.common.graph_peak(functions, {}, "root", set())

    def test_explicit_failures_survive_optimization(self):
        with self.assertRaises(ValueError):
            graphical.need(False, "independent explicit denial")
        with self.assertRaises(ValueError):
            decoder.require(False, "independent explicit decoder denial")

    def test_bridge_target_and_record_forwarding_are_exact(self):
        ops = [
            ("push", "%rbp"),
            ("mov", "%rsp,%rbp"),
            ("mov", "%rdi,%r11"),
            ("call", "100 <entry>"),
            ("leave", ""),
            ("ret", ""),
        ]
        starts = {256: "__au_v_m1_24kernel_graphical_console_n0__d17graphical_console"}
        graphical.verify_bridge_body(decoder, body(ops), starts)
        for index, replacement in [
            (0, ("push", "%rbx")),
            (1, ("mov", "%rsp,%rbx")),
            (2, ("mov", "%rsi,%r11")),
            (2, ("mov", "%edi,%r11d")),
            (2, ("mov", "%rdi,%r10")),
            (3, ("call", "*%r11")),
            (3, ("jmp", "100 <entry>")),
            (3, ("call", "101 <interior>")),
            (4, ("nop", "")),
            (5, ("ret", "$0x8")),
        ]:
            changed = list(ops)
            changed[index] = replacement
            with self.subTest(index=index, replacement=replacement), self.assertRaises(ValueError):
                graphical.verify_bridge_body(decoder, body(changed), starts)
        for name in ["__au_v_m1_22kernel_display_service_n0__d15display_service", "__au_runtime_console_entry"]:
            with self.assertRaises(ValueError):
                graphical.verify_bridge_body(decoder, body(ops), {256: name})
        for changed in [ops[:-1], ops + [("nop", "")]]:
            with self.assertRaises(ValueError):
                graphical.verify_bridge_body(decoder, body(changed), starts)

    def test_irq_every_save_restore_and_dispatch(self):
        registers = "rax rbx rcx rdx rbp rsi rdi r8 r9 r10 r11 r12 r13 r14 r15".split()
        ops = [("push", "$0x0"), ("push", "$0x40"), ("cld", "")]
        ops += [("push", "%" + r) for r in registers]
        ops += [
            ("mov", "%rsp,%rdi"),
            ("mov", "%rsp,%rbx"),
            ("and", "$0xfffffffffffffff0,%rsp"),
            ("call", "100 <dispatch>"),
            ("mov", "%rbx,%rsp"),
        ]
        ops += [("pop", "%" + r) for r in reversed(registers)] + [("add", "$0x10,%rsp"), ("iretq", "")]
        starts = {256: "uefi_console_interrupt_dispatch"}
        graphical.verify_irq_body(decoder, body(ops), starts)
        for index in range(len(ops)):
            changed = list(ops)
            changed[index] = ("nop", "")
            with self.subTest(index=index), self.assertRaises(ValueError):
                graphical.verify_irq_body(decoder, body(changed), starts)
        for index, replacement in [
            (20, ("and", "$0xffffffffffffffe0,%rsp")),
            (21, ("call", "*%rax")),
            (22, ("mov", "%rax,%rsp")),
        ]:
            changed = list(ops)
            changed[index] = replacement
            with self.assertRaises(ValueError):
                graphical.verify_irq_body(decoder, body(changed), starts)

    def test_irq_excludes_language_and_service_on_every_branch(self):
        graph = {
            "uefi_console_interrupt_dispatch": {"calls": [{"target": "large"}, {"target": "small"}]},
            "large": {"calls": []},
            "small": {"calls": []},
        }
        graphical.verify_irq_reachability(graph, set())
        for target in [
            graphical.ENTRY,
            "__au_v_any",
            "__au_runtime_console_put",
            "__au_runtime_display_put",
            "generated_leaf",
        ]:
            changed = deepcopy(graph)
            changed["small"]["calls"] = [{"target": target}]
            changed[target] = {"calls": []}
            with self.subTest(target=target), self.assertRaises(ValueError):
                graphical.verify_irq_reachability(changed, {"generated_leaf", graphical.ENTRY})

    def test_unchanged_stack_and_separate_reserves(self):
        # Independently selected exact boundaries: 15360 total, 4096 IRQ/fault.
        for values in [(15000, 11000, 3736, 360), (15201, 720, 639, 159), (1, 12304, 2048, 1008), (1, 1, 4000, 96)]:
            graphical.verify_stack_budgets(*values)
        for values in [
            (15001, 11000, 3736, 360),
            (1, 11265, 3736, 360),
            (1, 1, 3737, 360),
            (1, 12305, 2048, 1008),
            (-1, 1, 1, 1),
            (True, 1, 1, 1),
            (1, False, 1, 1),
            (1, 1, -1, 1),
            (1, 1, 1, -1),
            (1, 1, 1, 1.0),
        ]:
            with self.subTest(values=values), self.assertRaises(ValueError):
                graphical.verify_stack_budgets(*values)

    def test_immediate_push_bytes_width_and_value(self):
        for args, raw in [("$0x0", bytes.fromhex("6a00")), ("$0x28", bytes.fromhex("6a28"))]:
            row, receipt = graphical.normalize_instruction(decoder, decoder.Instruction(0, 2, "push", args), raw)
            self.assertEqual(row.args, "%rax")
            self.assertEqual(receipt["bytes"], raw.hex())
        for args, raw in [
            ("$0x0", b"\x66\x6a\x00"),
            ("$0x0", b"\x6a\x28"),
            ("$0x28", b"\x6a\x00"),
            ("$0x40", b"\x6a\x40"),
            ("$0x1", b"\x6a\x01"),
            ("$0x0", b"\x68\x00\x00\x00\x00"),
            ("$0x0", b"\x6a"),
        ]:
            with self.subTest(args=args, raw=raw), self.assertRaises(ValueError):
                graphical.normalize_instruction(decoder, decoder.Instruction(0, len(raw), "push", args), raw)

    def test_unsupported_stack_forms_and_opcode_fail_closed(self):
        for op, args in [
            ("push", "(%rsp)"),
            ("push", "0x10(%rip)"),
            ("push", "(%rsp,%rax,8)"),
            ("sub", "$0xfffffffffffffff0,%rsp"),
            ("mov", "%rax,%rsp"),
            ("ret", "$0x8"),
            ("enter", "$0x10,$0x0"),
            ("opaque_new_opcode", ""),
        ]:
            row = decoder.Instruction(0, 1, op, args)
            with self.subTest(op=op, args=args), self.assertRaises(ValueError):
                normalized, _ = graphical.normalize_instruction(decoder, row, b"\x90")
                decoder.analyze_function(
                    decoder.Symbol("sample", 0, 2, 1, 2),
                    {0: normalized, 1: decoder.Instruction(1, 1, "ret", "")},
                    {0: "sample"},
                )

    @staticmethod
    def paired_r9_fixture():
        name = graphical.PAIRED_WALK
        operations, labels = [], {}

        def emit(op, args=""):
            operations.append((op, args))

        def mark(label):
            labels[label] = len(operations)

        for op, args in [
            ("push", "%r15"),
            ("mov", "%rdx,%r11"),
            ("push", "%r14"),
            ("push", "%r13"),
            ("push", "%r12"),
            ("push", "%rbp"),
            ("push", "%rbx"),
            ("sub", "$0x48,%rsp"),
        ]:
            emit(op, args)
        mark("capture")
        emit("mov", "%ecx,%r9d")
        mark("loop")
        emit("test", "%r9d,%r9d")
        emit("jne", "#positive")
        mark("zero_spill")
        emit("mov", "%r9d,0x20(%rsp)")
        emit("mov", "%r10,0x18(%rsp)")
        mark("zero_helper")
        emit("call", "@" + graphical.PAIRED_LEVEL_HELPER)
        mark("zero_restore")
        emit("mov", "0x20(%rsp),%r9d")
        emit("jmp", "#epilogue")
        mark("positive")
        emit("mov", "%rdx,0x18(%rsp)")
        emit("mov", "%r8,0x20(%rsp)")
        mark("positive_spill")
        emit("mov", "%r9d,0x3c(%rsp)")
        mark("positive_helper")
        emit("call", "@" + graphical.PAIRED_LEVEL_HELPER)
        mark("positive_restore")
        emit("mov", "0x3c(%rsp),%r9d")
        mark("decrement")
        emit("lea", "-0x1(%r9),%ecx")
        emit("mov", "%r10,0x20(%rsp)")
        mark("child_spill")
        emit("mov", "%r9d,0x18(%rsp)")
        mark("child")
        emit("call", "@" + name)
        mark("child_restore")
        emit("mov", "0x18(%rsp),%r9d")
        emit("test", "%al,%al")
        emit("jne", "#loop")
        emit("jmp", "#epilogue")
        mark("epilogue")
        emit("add", "$0x48,%rsp")
        for register in ("%rbx", "%rbp", "%r12", "%r13", "%r14", "%r15"):
            emit("pop", register)
        emit("ret")
        operations = [
            (op, "@" + name + "+" + str(labels[args[1:]]) if args.startswith("#") else args) for op, args in operations
        ]
        graph = {name: operations, graphical.PAIRED_LEVEL_HELPER: [("xor", "%eax,%eax"), ("ret", "")]}
        return (*fixture(graph), labels)

    def test_paired_r9_spill_core_all_four_seeds(self):
        functions, symbols, code, starts, labels = self.paired_r9_fixture()
        helper = graphical.paired_readonly_leaf(decoder, graphical.PAIRED_LEVEL_HELPER, symbols, code, functions)
        self.assertEqual(helper["memory_writes"], 0)
        levels = graphical.paired_level_induction(
            decoder, symbols[graphical.PAIRED_WALK], code, starts, functions[graphical.PAIRED_WALK]
        )
        self.assertEqual(set(levels), {0, 1, 2, 3})
        for seed, result in levels.items():
            recursive = [row for row in result["calls"] if row["target"] == graphical.PAIRED_WALK]
            self.assertEqual([row["level"] for row in recursive], [] if seed == 0 else [seed - 1])
            self.assertEqual(result["local_peak"], 128)
            self.assertTrue(result["caller_saved_killed"])

    def test_paired_r9_spill_clobber_mutations(self):
        functions, symbols, code, starts, labels = self.paired_r9_fixture()
        symbol = symbols[graphical.PAIRED_WALK]
        graphical.paired_level_induction(decoder, symbol, code, starts, functions[symbol.name])
        changes = [
            ("capture", "mov", "%edx,%r9d"),
            ("capture", "mov", "%ecx,%r9w"),
            ("loop", "cmp", "$0x1,%r9d"),
            ("decrement", "mov", "%r9d,%ecx"),
            ("decrement", "lea", "0x1(%r9),%ecx"),
            ("decrement", "lea", "-0x1(%r9),%cx"),
            ("positive_spill", "mov", "%r9w,0x3c(%rsp)"),
            ("positive_spill", "mov", "%r9d,0x38(%rsp)"),
            ("positive_restore", "mov", "0x3b(%rsp),%r9d"),
            ("positive_restore", "mov", "%r9d,%r9d"),
            ("child_spill", "mov", "%r10,0x18(%rsp)"),
            ("child_restore", "mov", "0x20(%rsp),%r9d"),
            ("child_restore", "mov", "%ecx,%r9d"),
        ]
        for label, op, args in changes:
            changed = dict(code)
            old = code[symbol.address + labels[label]]
            changed[old.address] = decoder.Instruction(old.address, old.size, op, args)
            with self.subTest(label=label, op=op, args=args), self.assertRaises(ValueError):
                graphical.paired_level_induction(decoder, symbol, changed, starts, functions[symbol.name])

    def test_paired_r9_core_rejects_frame_escape_and_unproved_writes(self):
        functions, symbols, code, starts, labels = self.paired_r9_fixture()
        symbol = symbols[graphical.PAIRED_WALK]
        graphical.paired_level_induction(decoder, symbol, code, starts, functions[symbol.name])
        # Replace a nonessential data spill, retaining all level stores/restores.
        address = symbol.address + labels["zero_spill"] + 1
        for op, args in [
            ("sub", "$0x8,%rsp"),
            ("push", "%rax"),
            ("mov", "%rsp,%rax"),
            ("lea", "0x18(%rsp),%rdi"),
            ("mov", "%r10,0x48(%rsp)"),
            ("mov", "%r10,0x0(%rsp,%rax,1)"),
            ("movb", "$0x1,(%rdi)"),
        ]:
            changed = dict(code)
            old = code[address]
            changed[address] = decoder.Instruction(address, old.size, op, args)
            with self.subTest(op=op, args=args), self.assertRaises(ValueError):
                graphical.paired_level_induction(decoder, symbol, changed, starts, functions[symbol.name])
        # Adjacent qword at +0x18 is safe for the +0x20 dword; changing it to
        # +0x1c overlaps and destroys the fact that the later reload needs.
        changed = dict(code)
        old = code[address]
        changed[address] = decoder.Instruction(address, old.size, "mov", "%r10,0x1c(%rsp)")
        # Zero seed alone can return with an unknown carrier, so force that path
        # back through the level guard to expose the poisoned spill fact.
        jump = symbol.address + labels["zero_restore"] + 1
        changed[jump] = decoder.Instruction(jump, 1, "jmp", f"{symbol.address + labels['loop']:x} <loop>")
        with self.assertRaises(ValueError):
            graphical.paired_level_induction(decoder, symbol, changed, starts, functions[symbol.name])

    def test_paired_r9_core_callee_and_cfg_mutations(self):
        functions, symbols, code, starts, labels = self.paired_r9_fixture()
        symbol = symbols[graphical.PAIRED_WALK]
        graphical.paired_level_induction(decoder, symbol, code, starts, functions[symbol.name])
        helper_symbol = symbols[graphical.PAIRED_LEVEL_HELPER]
        for op, args in [
            ("mov", "%rax,(%rdi)"),
            ("mov", "%rsp,%rax"),
            ("syscall", ""),
            ("call", f"{symbol.address:x} <paired>"),
        ]:
            changed = dict(code)
            changed[helper_symbol.address] = decoder.Instruction(helper_symbol.address, 1, op, args)
            with self.subTest(op=op, args=args), self.assertRaises(ValueError):
                graphical.paired_readonly_leaf(decoder, graphical.PAIRED_LEVEL_HELPER, symbols, changed, functions)
        for label, target in (("child", helper_symbol.address), ("positive_helper", symbol.address)):
            changed = dict(code)
            address = symbol.address + labels[label]
            changed[address] = decoder.Instruction(address, 1, "call", f"{target:x} <changed>")
            with self.assertRaises(ValueError):
                graphical.paired_level_induction(decoder, symbol, changed, starts, functions[symbol.name])
        branch = symbol.address + labels["loop"] + 1
        for target in (helper_symbol.address, symbol.address + symbol.size, 0xDEADBEEF):
            changed = dict(code)
            changed[branch] = decoder.Instruction(branch, 1, "jne", f"{target:x} <outside>")
            with self.assertRaises(ValueError):
                graphical.paired_level_induction(decoder, symbol, changed, starts, functions[symbol.name])

    def test_both_walkers_require_bounded_decrement_and_entry(self):
        paired = "independent_paired_walk"
        saves = "%r15 %r14 %r13 %r12 %rbp %rbx".split()

        def walk(name):
            return (
                [("push", r) for r in saves]
                + [
                    ("mov", "%ecx,%r14d"),
                    ("test", "%r14d,%r14d"),
                    ("je", "@" + name + "+11"),
                    ("lea", "-0x1(%r14),%ecx"),
                    ("call", "@" + name),
                ]
                + [("pop", r) for r in reversed(saves)]
                + [("ret", "")]
            )

        graph = {
            "root": [
                ("mov", "$0x3,%ecx"),
                ("call", "@" + decoder.WALK),
                ("mov", "$0x3,%ecx"),
                ("call", "@" + paired),
                ("ret", ""),
            ],
            decoder.WALK: walk(decoder.WALK),
            paired: walk(paired),
        }
        decoder.recursion_proof(*fixture(graph))
        with self.assertRaisesRegex(ValueError, "Unknown concrete paired walker identity"):
            graphical.paired_recursion_proofs(decoder, *fixture(graph), paired)
        for name in [decoder.WALK]:
            for index, replacement in [
                (6, ("mov", "%edx,%r14d")),
                (7, ("cmp", "$0x1,%r14d")),
                (8, ("jne", "@" + name + "+11")),
                (9, ("lea", "0x1(%r14),%ecx")),
                (9, ("mov", "%r14d,%ecx")),
                (15, ("pop", "%rax")),
            ]:
                changed = deepcopy(graph)
                changed[name][index] = replacement
                with self.subTest(walker=name, index=index, replacement=replacement), self.assertRaises(ValueError):
                    graphical.paired_recursion_proofs(decoder, *fixture(changed), paired)
        for index in [0, 2]:
            for args in ["$0x4,%ecx", "%eax,%ecx", "$0x3,%cl"]:
                changed = deepcopy(graph)
                changed["root"][index] = ("mov", args)
                with self.assertRaises(ValueError):
                    graphical.paired_recursion_proofs(decoder, *fixture(changed), paired)
        changed = deepcopy(graph)
        changed[paired][10] = ("call", "@" + decoder.WALK)
        with self.assertRaises(ValueError):
            graphical.paired_recursion_proofs(decoder, *fixture(changed), paired)
        functions, symbols, code, starts = fixture(graph)
        for missing in [decoder.WALK, paired]:
            changed = dict(functions)
            del changed[missing]
            with self.assertRaises(ValueError):
                graphical.paired_recursion_proofs(decoder, changed, symbols, code, starts, paired)
        with self.assertRaises(ValueError):
            graphical.paired_recursion_proofs(decoder, functions, symbols, code, starts, decoder.WALK)
        self.assertEqual(decoder.WALK, next(name for name in graph if name not in {"root", paired}))

    def test_wait_exact_bytes_decode_single_owner_and_single_sti(self):
        start = 10
        code = {start + i: decoder.Instruction(start + i, 1, op, "") for i, op in enumerate(["sti", "hlt", "cli"])}
        named = {
            "uefi_console_poll_begin": decoder.Symbol("begin", 10, 0, 1, 0),
            "uefi_console_poll_end": decoder.Symbol("end", 13, 0, 1, 0),
        }
        graph = {"uefi_console_interrupt_dispatch": {"calls": []}}
        owners = {"trusted_wait_for_sample": decoder.Symbol("trusted_wait_for_sample", 9, 5, 1, 2)}
        payload = b"\x90" * 10 + b"\xfb\xf4\xfa" + b"\x90"

        def verify(c=code, n=named, g=graph, p=payload, o=owners):
            return graphical.verify_wait_closure(c, n, g, set(), p, o)

        verify()
        for raw in [b"\xfa\xf4\xfb", b"\xfb\x90\xfa", b"\xfb\xf4\x90", b"\xfb\xf4"]:
            with self.assertRaises(ValueError):
                verify(p=b"\x90" * 10 + raw)
        for index in code:
            changed = dict(code)
            changed[index] = decoder.Instruction(index, 1, "nop", "")
            with self.assertRaises(ValueError):
                verify(c=changed)
            changed = dict(code)
            changed[index] = decoder.Instruction(index, 2, code[index].op, "")
            with self.assertRaises(ValueError):
                verify(c=changed)
        changed = dict(code)
        changed[1] = decoder.Instruction(1, 1, "sti", "")
        with self.assertRaises(ValueError):
            verify(c=changed)
        for changed in [
            {},
            {"wrong_owner": decoder.Symbol("wrong_owner", 9, 5, 1, 2)},
            dict(owners, second_wait_for_sample=decoder.Symbol("second_wait_for_sample", 9, 5, 1, 2)),
        ]:
            with self.assertRaises(ValueError):
                verify(o=changed)
        changed = deepcopy(named)
        changed["uefi_console_poll_end"] = decoder.Symbol("end", 14, 0, 1, 0)
        with self.assertRaises(ValueError):
            verify(n=changed)

    def test_each_wait_path_retains_paired_service_not_just_maximum(self):
        path = ["uefi_payload_entry", graphical.BRIDGE, graphical.ENTRY, "__au_runtime_console_next", "wait_for_sample"]
        graph = {
            name: {"calls": [{"target": path[index + 1]}] if index + 1 < len(path) else []}
            for index, name in enumerate(path)
        }
        graphical.verify_retained_wait_paths(graph, path[-1], set())
        for source, target in [(0, 2), (1, 3), (2, 4), (0, 4)]:
            changed = deepcopy(graph)
            changed[path[source]]["calls"].append({"target": path[target]})
            with self.subTest(source=source, target=target), self.assertRaisesRegex(ValueError, "bypasses retained"):
                graphical.verify_retained_wait_paths(changed, path[-1], set())

    def test_inventory_has_no_missing_unframed_or_extra_authority(self):
        fixed = {
            "uefi_payload_entry",
            "uefi_payload_fault",
            "uefi_payload_page_fault",
            "fault_common",
            "uefi_console_interrupt",
        }
        language = {
            graphical.ENTRY,
            graphical.BRIDGE,
            graphical.VALUE_BRIDGE,
            "generated_helper",
            *REFLECTION,
        }
        frames = {"trusted_cpp", "__au_runtime_console_next", "__au_runtime_console_put", "__au_runtime_display_pixel"}
        memory = {"memcpy", "memset"}
        linked = fixed | language | frames | memory
        graphical.verify_inventory(linked, frames, language, memory)
        for missing in sorted(linked):
            with self.subTest(missing=missing), self.assertRaises(ValueError):
                graphical.verify_inventory(linked - {missing}, frames, language, memory)
        with self.assertRaises(ValueError):
            graphical.verify_inventory(linked | {"unframed"}, frames, language, memory)
        for extra in [
            "__au_runtime_display_clear",
            "uefi_runtime_unexpected",
            "aurora_user_fixture",
            "aurora_kernel_budget_fixture",
        ]:
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                graphical.verify_inventory(linked | {extra}, frames | {extra}, language, memory)
        for name in [graphical.ENTRY, graphical.BRIDGE, *REFLECTION]:
            with self.assertRaises(ValueError):
                graphical.verify_inventory(linked, frames | {name}, language - {name}, memory)
        self.assertEqual(graphical.CPP_OBJECTS, ("payload", "acpi", "pci", "runtime", "graphical-console"))
        self.assertEqual(graphical.ASSEMBLY_OBJECTS, ("payload-entry", "console-entry", "language", "memory"))

    def test_begin_invalidates_before_fallible_checks(self):
        with tempfile.TemporaryDirectory(prefix="graphical-invalidation-") as directory:
            root = Path(directory)
            names = [
                "graphical-console-admission.json",
                "graphical-console-build.json",
                "graphical-console-build-start.json",
            ]
            sentinel = root / "payload.elf"
            sentinel.write_bytes(b"preserved prior image")

            def stale():
                for name in names:
                    (root / name).write_text("previous metadata")

            with patch.object(graphical, "BUILD", root), patch.object(graphical, "RECEIPT", root / names[0]):
                stale()
                with self.assertRaisesRegex(ValueError, "Missing exact graphical build controls"):
                    graphical.begin("graphical-console", "compiler", "cxx", [])
                self.assertTrue(all(not (root / name).exists() for name in names))
                stale()
                with (
                    patch.object(graphical, "source_files", return_value=[]),
                    patch.object(graphical.common, "hashes", return_value={}),
                    patch.object(graphical.common, "executable", side_effect=RuntimeError("tool unavailable")),
                ):
                    with self.assertRaisesRegex(RuntimeError, "tool unavailable"):
                        graphical.begin(
                            "graphical-console", "compiler", "cxx", graphical.expected_flags("graphical-console")
                        )
                self.assertTrue(all(not (root / name).exists() for name in names))
                stale()
                with (
                    patch.object(Path, "unlink", side_effect=PermissionError("read-only metadata")),
                    patch.object(graphical.common, "executable") as executable,
                ):
                    with self.assertRaisesRegex(PermissionError, "read-only metadata"):
                        graphical.begin(
                            "graphical-console", "compiler", "cxx", graphical.expected_flags("graphical-console")
                        )
                    executable.assert_not_called()
                self.assertEqual(sentinel.read_bytes(), b"preserved prior image")

    def test_mode_flags_sources_artifacts_and_review_identity(self):
        with tempfile.TemporaryDirectory(prefix="graphical-controls-") as directory:
            root = Path(directory)
            paths = {name: root / name for name in ["source", "compiler", "cxx", "payload.bin", "tool", "pe_linker"]}
            for name, path in paths.items():
                path.write_text("original " + name)

            def hashes(items):
                return {str(path.relative_to(root)): graphical.digest(path) for path in items}

            record = dict(
                schema="aurora-graphical-console-build-v1",
                mode="graphical-console",
                flags=graphical.expected_flags("graphical-console"),
                translation_unit_flags=deepcopy(graphical.TU_FLAGS),
                objects=["payload.bin"],
                source_sha256=hashes([paths["source"]]),
                compiler=dict(path=str(paths["compiler"]), sha256=graphical.digest(paths["compiler"])),
                cxx=dict(path=str(paths["cxx"]), sha256=graphical.digest(paths["cxx"])),
                tools={
                    name: dict(path=str(paths["tool"]), sha256=graphical.digest(paths["tool"]))
                    for name in graphical.TOOLS
                },
                pe_linker=dict(path=str(paths["pe_linker"]), sha256=graphical.digest(paths["pe_linker"])),
                output_sha256=hashes([paths["payload.bin"]]),
            )
            # The actual shared-session header changes in an isolated source tree.
            # Reintroducing the old five-file token gate must reject this control.
            for name in (
                "kernel/graphical-session.hpp",
                "kernel/console-session.hpp",
                "kernel/display-session.hpp",
                "kernel/uefi/graphical-console.cpp",
                "kernel/uefi/graphical-capture-policy.hpp",
            ):
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((ROOT / name).read_bytes())
            for name in ("scripts", "tests"):
                (root / name).symlink_to(ROOT / name, target_is_directory=True)
            paths["source"] = root / "kernel/graphical-session.hpp"
            record["source_sha256"] = hashes([paths["source"]])
            build = root / "graphical-console-build.json"
            build.write_text(json.dumps(record))
            receipt = root / "graphical-console-admission.json"
            data = dict(
                schema="aurora-graphical-console-admission-v4",
                mode="graphical-console",
                status="requires-independent-review",
                clock="tcg-original-clock",
                build=record,
                image={"independent_image_result": 1},
                stack={"independent_stack_result": 456},
                sha256=hashes([paths["source"], paths["payload.bin"], build]),
            )
            receipt.write_text(json.dumps(data))
            real_image_evidence = graphical.image_evidence
            with (
                patch.object(graphical, "ROOT", root),
                patch.object(graphical, "BUILD", root),
                patch.object(graphical, "RECEIPT", receipt),
                patch.object(graphical, "build_files", return_value=[paths["payload.bin"]]),
                patch.object(graphical, "source_files", return_value=[paths["source"]]),
                patch.object(graphical.common, "hashes", side_effect=hashes),
                patch.object(graphical.common, "executable", side_effect=lambda name: record["tools"][name]),
                patch.object(graphical, "image_evidence", return_value={"independent_image_result": 1}),
                patch.object(graphical, "stack_evidence", return_value={"independent_stack_result": 456}),
                patch.dict(os.environ, {"GRAPHICAL_CONSOLE_REVIEW_SHA256": graphical.digest(receipt)}),
            ):
                graphical.verify_inputs(record, "graphical-console")
                graphical.checked("graphical-console")
                graphical.reviewed("graphical-console")
                for key in ["source", "compiler", "cxx", "payload.bin", "tool", "pe_linker"]:
                    path = paths[key]
                    saved = path.read_bytes()
                    path.write_bytes(saved + b" drift")
                    with self.subTest(drift=key), self.assertRaises(ValueError):
                        graphical.checked("graphical-console")
                    path.write_bytes(saved)
                for mode in ["graphical-console-capture", "console", "framebuffer", "graphical-console-stale"]:
                    with self.assertRaises(ValueError):
                        graphical.checked(mode)
                for flag in [
                    "-DAURORA_UEFI_CONSOLE",
                    "-DAURORA_UEFI_FRAMEBUFFER",
                    "-DAURORA_UEFI_GRAPHICAL_CAPTURE",
                    "-O0",
                    "-DUNKNOWN",
                ]:
                    changed = deepcopy(record)
                    changed["flags"].append(flag)
                    with self.subTest(flag=flag), self.assertRaises(ValueError):
                        graphical.verify_inputs(changed, "graphical-console")
                for mutate in [
                    lambda r: r["flags"].pop(),
                    lambda r: r["flags"].reverse(),
                    lambda r: r["objects"].append("console.o"),
                    lambda r: r["translation_unit_flags"].update(runtime=[]),
                    lambda r: r.update(schema="aurora-framebuffer-build-v1"),
                ]:
                    changed = deepcopy(record)
                    mutate(changed)
                    with self.assertRaises(ValueError):
                        graphical.verify_inputs(changed, "graphical-console")
                for pin in ["", "0" * 64, "A" * 64, graphical.digest(receipt)[:-1]]:
                    with (
                        patch.dict(os.environ, {"GRAPHICAL_CONSOLE_REVIEW_SHA256": pin}),
                        self.assertRaises(ValueError),
                    ):
                        graphical.reviewed("graphical-console")
                for version in (1, 2, 3):
                    old = dict(data, schema=f"aurora-graphical-console-admission-v{version}")
                    receipt.write_text(json.dumps(old))
                    with patch.dict(os.environ, {"GRAPHICAL_CONSOLE_REVIEW_SHA256": graphical.digest(receipt)}):
                        for check in (graphical.checked, graphical.reviewed):
                            with self.subTest(version=version, check=check.__name__):
                                with self.assertRaisesRegex(ValueError, "Unexpected graphical receipt"):
                                    check("graphical-console")
                receipt.write_text(json.dumps(data))
                # A caller cannot relabel automatic evidence as independent acceptance.
                changed = deepcopy(data)
                changed["status"] = "accepted"
                receipt.write_text(json.dumps(changed))
                with self.assertRaises(ValueError):
                    graphical.checked("graphical-console")
                receipt.write_text(json.dumps(data))
                for key in list(data):
                    changed = deepcopy(data)
                    del changed[key]
                    receipt.write_text(json.dumps(changed))
                    with self.subTest(missing_receipt_key=key), self.assertRaises(ValueError):
                        graphical.checked("graphical-console")
                for key, value in [
                    ("schema", "aurora-graphical-console-admission-v1"),
                    ("image", {}),
                    ("stack", {}),
                    ("image", {"independent_image_result": True}),
                    ("stack", {"independent_stack_result": 0}),
                    ("extra", True),
                ]:
                    changed = deepcopy(data)
                    changed[key] = value
                    receipt.write_text(json.dumps(changed))
                    with self.subTest(forged_receipt_key=key, value=value), self.assertRaises(ValueError):
                        graphical.checked("graphical-console")
                for raw in [
                    '{"mode":"graphical-console","mode":"graphical-console"}',
                    '{"nested":{"same":1,"same":1}}',
                    '{"number":NaN}',
                    '{"number":Infinity}',
                ]:
                    receipt.write_text(raw)
                    with self.assertRaises(ValueError):
                        graphical.read_json(receipt)
                receipt.write_text(json.dumps(data))
                build.write_text(json.dumps(dict(record, objects=["payload.bin", "console.o"])))
                with self.assertRaises(ValueError):
                    graphical.checked("graphical-console")
                build.write_text(json.dumps(record))
                original = paths["source"].read_text()
                changed = original.replace(
                    "if (active_ || incoming != &trusted)", "if (!incoming || active_ || incoming != &trusted)"
                )
                self.assertNotEqual(changed, original, "Exercise a real shared-session implementation edit")
                paths["source"].write_text(changed)
                with self.assertRaisesRegex(ValueError, "Graphical source changed since begin"):
                    graphical.provenance("graphical-console")
                # Re-enter the real image reader after fresh provenance. Invalid ELF
                # must fail there, not at a source-token gate; no compiler/guest runs.
                (root / "payload.elf").write_bytes(b"invalid ELF")
                pe = root / "esp/EFI/BOOT/BOOTX64.EFI"
                pe.parent.mkdir(parents=True)
                pe.write_bytes(b"invalid PE")
                for mode in ("graphical-console", "graphical-console-capture"):
                    fresh = dict(
                        record, mode=mode, flags=graphical.expected_flags(mode), source_sha256=hashes([paths["source"]])
                    )
                    build.write_text(json.dumps(fresh))
                    graphical.provenance(mode)
                    receipt.write_text(json.dumps(data))
                    with patch.object(graphical, "image_evidence", side_effect=real_image_evidence):
                        with self.subTest(mode=mode), self.assertRaisesRegex(ValueError, "Payload ELF architecture"):
                            graphical.emit(mode)
                    self.assertFalse(receipt.exists(), "Failed fresh image checks must remove stale PASS")

    @staticmethod
    def paired_linked_fixture(shift=0):
        # These are independently retained emitted rows, not an expected shape
        # synthesized from production constants or proof results.
        names = {
            "root": graphical.PAIRED_ROOT,
            "walk": graphical.PAIRED_WALK,
            "layout": graphical.PAIRED_LAYOUT,
            "bytes": graphical.PAIRED_BYTES,
            "flags": graphical.PAIRED_LEVEL_HELPER,
            "guard": graphical.PAIRED_GUARD,
            "entry": graphical.PAIRED_ENTRY,
            "window": graphical.PAIRED_WINDOW,
        }
        locations = {label: shift + 0x1000 * (index + 1) for index, label in enumerate(names)}
        data_address = shift + 0xA000
        payload, code, symbols = bytearray(data_address + 12), {}, {}
        payload[data_address:] = bytes.fromhex("270000001e00000015000000")
        for label, text in PAIRED_LINKED_FIXTURES.items():
            base = locations[label]
            for line in text.strip().splitlines():
                offset, machine, op, args = line.split("|")
                raw = bytearray.fromhex(machine)
                address = base + int(offset, 16)
                if args.startswith("@levels"):
                    delta = data_address - (address + len(raw))
                    raw[-4:] = delta.to_bytes(4, "little", signed=True)
                    args = hex(delta) + "(%rip)," + args.split(",")[1]
                elif args.startswith("@"):
                    target = locations[args[1:]]
                    raw[-4:] = (target - address - len(raw)).to_bytes(4, "little", signed=True)
                    args = f"{target:x} <{args[1:]}>"
                elif args.startswith("+"):
                    args = f"{base + int(args[1:], 16):x} <{label}>"
                payload[address : address + len(raw)] = raw
                code[address] = decoder.Instruction(address, len(raw), op, args)
            symbols[names[label]] = decoder.Symbol(names[label], base, address + len(raw) - base, 1, 2)
        starts = {symbol.address: name for name, symbol in symbols.items()}
        functions = {name: decoder.analyze_function(symbol, code, starts) for name, symbol in symbols.items()}
        return functions, symbols, code, starts, bytes(payload)

    @staticmethod
    def paired_gcc16_linked_fixture(shift=0):
        # These are independently retained emitted rows, not an expected shape
        # synthesized from production constants or proof results.
        names = {
            "root": graphical.PAIRED_ROOT,
            "walk": graphical.PAIRED_ALIAS,
            "layout": graphical.PAIRED_LAYOUT,
            "bytes": graphical.PAIRED_BYTES,
            "flags": graphical.PAIRED_LEVEL_HELPER,
            "guard": graphical.PAIRED_GUARD,
            "entry": graphical.PAIRED_ENTRY,
            "window": graphical.PAIRED_WINDOW,
        }
        locations = {label: shift + 0x1000 * (index + 1) for index, label in enumerate(names)}
        data_address = shift + 0xA000
        payload, code, symbols = bytearray(data_address + 12), {}, {}
        payload[data_address:] = bytes.fromhex("270000001e00000015000000")
        for label, text in PAIRED_GCC16_LINKED_FIXTURES.items():
            base = locations[label]
            for line in text.strip().splitlines():
                offset, machine, op, args = line.split("|")
                raw = bytearray.fromhex(machine)
                address = base + int(offset, 16)
                if args.startswith("@levels"):
                    delta = data_address - (address + len(raw))
                    raw[-4:] = delta.to_bytes(4, "little", signed=True)
                    args = hex(delta) + "(%rip)," + args.split(",")[1]
                elif args.startswith("@"):
                    target = locations[args[1:]]
                    raw[-4:] = (target - address - len(raw)).to_bytes(4, "little", signed=True)
                    args = f"{target:x} <{args[1:]}>"
                elif args.startswith("+"):
                    args = f"{base + int(args[1:], 16):x} <{label}>"
                payload[address : address + len(raw)] = raw
                code[address] = decoder.Instruction(address, len(raw), op, args)
            symbols[names[label]] = decoder.Symbol(names[label], base, address + len(raw) - base, 1, 2)
        starts = {symbol.address: name for name, symbol in symbols.items()}
        functions = {name: decoder.analyze_function(symbol, code, starts) for name, symbol in symbols.items()}
        return functions, symbols, code, starts, bytes(payload)

    @staticmethod
    def gcc16_storage_proof(functions, symbols, code, starts, payload):
        result = dict(
            machine=graphical.paired_gcc16_exact_machine(decoder, symbols, code, starts, payload),
            helpers=graphical.paired_gcc16_helper_effects(decoder, symbols, code, functions),
            guard=graphical.paired_gcc16_guard_contract(decoder, symbols, code),
            root=graphical.paired_gcc16_root_storage(decoder, symbols, code, starts, functions),
            walker=graphical.paired_gcc16_walker_storage(decoder, symbols[graphical.PAIRED_ALIAS], code, starts),
        )
        levels = graphical.paired_gcc16_level_induction(
            decoder,
            symbols[graphical.PAIRED_ALIAS],
            code,
            starts,
            functions[graphical.PAIRED_ALIAS],
            (result["walker"]["bitmap_store"],),
            result,
        )
        return result, levels

    def test_gcc16_closed_storage_profile_and_relocation(self):
        for shift in (0, 0x100000):
            fixture = self.paired_gcc16_linked_fixture(shift)
            proof, levels = self.gcc16_storage_proof(*fixture)
            self.assertEqual(len(proof["machine"]), 8)
            self.assertEqual(
                proof["root"]["objects"],
                {"bitmap": (0x48, 16), "snapshot": (0x58, 24), "helper_closure": (0x70, 24), "closure": (0x88, 56)},
            )
            self.assertEqual(len(proof["root"]["guards"]), 6)
            for seed in range(4):
                self.assertTrue(levels[seed]["caller_memory_contract"])
                self.assertEqual(levels[seed]["established_child_seed"], seed - 1 if seed else None)
                self.assertEqual(
                    [call["level"] for call in levels[seed]["calls"] if call["target"] == graphical.PAIRED_ALIAS],
                    [seed - 1] if seed else [],
                )
            with self.assertRaises(ValueError):
                graphical.paired_exact_machine(decoder, fixture[1], fixture[2], fixture[3], fixture[4])
        old = self.paired_linked_fixture()
        with self.assertRaises(ValueError):
            graphical.paired_gcc16_exact_machine(decoder, old[1], old[2], old[3], old[4])

    def test_gcc16_each_body_and_guard_is_closed(self):
        functions, symbols, code, starts, payload = self.paired_gcc16_linked_fixture()
        for symbol in symbols.values():
            changed = bytearray(payload)
            changed[symbol.address] ^= 1
            with self.subTest(symbol=symbol.name), self.assertRaises(ValueError):
                graphical.paired_gcc16_exact_machine(decoder, symbols, code, starts, bytes(changed))
        root = symbols[graphical.PAIRED_ROOT]
        for offset in (0x6BE, 0x6E0, 0x705, 0x729, 0x750, 0x777):
            altered = dict(code)
            row = code[root.address + offset]
            altered[row.address] = decoder.Instruction(
                row.address, row.size, row.op, f"{symbols[graphical.PAIRED_LEVEL_HELPER].address:x} <wrong>"
            )
            with self.subTest(guard=offset), self.assertRaises(ValueError):
                graphical.paired_gcc16_root_storage(decoder, symbols, altered, starts, functions)
        for offset, op, args in (
            (0x7, "mov", "0x8(%rdi),%r10"),
            (0xAC, "mov", "$0x1,%r9d"),
            (0xB1, "mov", "$0x111000,%r10"),
            (0x8E, "mov", "$0x100000,%r15"),
            (0x644, "lea", "0x48(%rsp),%rcx"),
            (0x792, "cmp", "$0x11,%rax"),
            (0x7A8, "mov", "$0x4,%ecx"),
        ):
            altered = dict(code)
            row = code[root.address + offset]
            altered[row.address] = decoder.Instruction(row.address, row.size, op, args)
            with self.subTest(root=offset), self.assertRaises(ValueError):
                graphical.paired_gcc16_root_storage(decoder, symbols, altered, starts, functions)
        guard = symbols[graphical.PAIRED_GUARD]
        for offset in (3, 8, 0x12):
            altered = dict(code)
            row = code[guard.address + offset]
            altered[row.address] = decoder.Instruction(row.address, row.size, "jae", row.args)
            with self.subTest(overflow_or_disjoint=offset), self.assertRaises(ValueError):
                graphical.paired_gcc16_guard_contract(decoder, symbols, altered)

    def test_gcc16_save_slots_and_recursive_lineage_reject_mutations(self):
        functions, symbols, code, starts, payload = self.paired_gcc16_linked_fixture()
        proof, levels = self.gcc16_storage_proof(functions, symbols, code, starts, payload)
        for name in (graphical.PAIRED_ROOT, graphical.PAIRED_ALIAS, graphical.PAIRED_LAYOUT):
            symbol = symbols[name]
            frame = graphical.paired_gcc16_slot_frame(decoder, symbol, code)
            for address, register, slot in frame["saves"]:
                for args in (
                    code[address].args.replace(hex(slot), hex(slot + 1)),
                    code[address].args.replace("%" + register, "%eax"),
                ):
                    altered = dict(code)
                    row = code[address]
                    altered[address] = decoder.Instruction(address, row.size, row.op, args)
                    with self.subTest(save=(name, address, args)), self.assertRaises(ValueError):
                        graphical.paired_gcc16_slot_frame(decoder, symbol, altered)
            for address, register, slot in frame["restores"]:
                altered = dict(code)
                row = code[address]
                altered[address] = decoder.Instruction(
                    address, row.size, row.op, row.args.replace(hex(slot), hex(slot + 8))
                )
                with self.subTest(restore=(name, address)), self.assertRaises(ValueError):
                    graphical.paired_gcc16_slot_frame(decoder, symbol, altered)
        root = symbols[graphical.PAIRED_ROOT]
        row = code[root.address + 0x12]
        altered = dict(code)
        altered[row.address] = decoder.Instruction(row.address, row.size, "xchg", "%r13,%rax")
        with self.assertRaises(ValueError):
            graphical.paired_gcc16_slot_frame(decoder, root, altered)
        walk = symbols[graphical.PAIRED_ALIAS]
        for offset, op, args in (
            (0x15, "jae", code[walk.address + 0x15].args),
            (0x76, "movb", "$0x1,(%rdx,%rcx,1)"),
            (0x350, "mov", "%rax,%rdi"),
        ):
            altered = dict(code)
            row = code[walk.address + offset]
            altered[row.address] = decoder.Instruction(row.address, row.size, op, args)
            with self.subTest(walker=offset), self.assertRaises(ValueError):
                graphical.paired_gcc16_walker_storage(decoder, walk, altered, starts)
        for offset, op, args in (
            (0x33A, "lea", "0x0(%r9),%ecx"),
            (0x33E, "mov", "%rsi,0x18(%rsp)"),
            (0x350, "mov", "%rax,%rdi"),
        ):
            altered = dict(code)
            row = code[walk.address + offset]
            altered[row.address] = decoder.Instruction(row.address, row.size, op, args)
            with self.subTest(induction=offset), self.assertRaises(ValueError):
                graphical.paired_gcc16_level_induction(
                    decoder, walk, altered, starts, functions[walk.name], (proof["walker"]["bitmap_store"],), proof
                )

    def test_linked_snapshot_contract_and_relocated_baseline(self):
        for shift in (0, 0x100000):
            functions, symbols, code, starts, payload = self.paired_linked_fixture(shift)
            proof = graphical.paired_linked_storage(decoder, functions, symbols, code, starts, payload)
            self.assertEqual(len(proof["machine"]), 8)
            self.assertEqual(len(proof["helpers"]), 6)
            self.assertEqual(
                proof["root"]["objects"],
                {
                    "snapshot": (0x48, 24),
                    "bitmap": (0x38, 16),
                    "closure": (0x78, 56),
                    "helper_closure": (0x60, 24),
                },
            )
            self.assertEqual(len(proof["root"]["guards"]), 6)
            self.assertEqual(proof["walker"]["bitmap_index"], [0, 15])
            levels = graphical.paired_level_induction(
                decoder,
                symbols[graphical.PAIRED_WALK],
                code,
                starts,
                functions[graphical.PAIRED_WALK],
                (proof["walker"]["bitmap_store"],),
                storage=proof,
            )
            for seed in range(4):
                self.assertTrue(levels[seed]["caller_memory_contract"])
                self.assertTrue(levels[seed]["identical_closure_forwarding"])
                self.assertEqual(levels[seed]["established_child_seed"], None if seed == 0 else seed - 1)
                self.assertEqual(
                    [call["level"] for call in levels[seed]["calls"] if call["target"] == graphical.PAIRED_WALK],
                    [] if seed == 0 else [seed - 1],
                )

    def test_linked_bytes_operands_addresses_and_control_transfers(self):
        functions, symbols, code, starts, payload = self.paired_linked_fixture()
        graphical.paired_linked_storage(decoder, functions, symbols, code, starts, payload)
        root, walk = (symbols[name].address for name in (graphical.PAIRED_ROOT, graphical.PAIRED_WALK))
        # Every construction, guard, initialized/visited store and receiver is
        # independently corrupted at machine-byte level without changing decode.
        addresses = [
            root + off
            for off in (
                0x11,
                0x14,
                0x18,
                0x2B,
                0x30,
                0x35,
                0x51B,
                0x530,
                0x566,
                0x56B,
                0x583,
                0x5A0,
                0x5BD,
                0x5DA,
                0x5F7,
                0x614,
                0x624,
                0x646,
                0x6DB,
                0x710,
            )
        ]
        addresses += [symbol.address for symbol in symbols.values()]
        addresses += [walk + off for off in (0x11, 0x14, 0x19, 0x25, 0x55, 0x63, 0x2FD, 0x302, 0x320)]
        for address in addresses:
            changed = bytearray(payload)
            changed[address] ^= 1
            with self.subTest(byte=hex(address)), self.assertRaises(ValueError):
                graphical.paired_linked_storage(decoder, functions, symbols, code, starts, changed)
        for address in addresses:
            row = code[address]
            for changed_row in (
                decoder.Instruction(address, row.size, row.op, "%rax,%rax"),
                decoder.Instruction(address + 1, row.size, row.op, row.args),
                decoder.Instruction(address, row.size + 1, row.op, row.args),
            ):
                changed = dict(code, **{})
                changed[address] = changed_row
                with self.subTest(decode=hex(address), row=changed_row), self.assertRaises(ValueError):
                    graphical.paired_linked_storage(decoder, functions, symbols, changed, starts, payload)
        # Coherent opcode/operand+byte mutations cannot pass by agreeing with one
        # another. The independent instruction contract still rejects each.
        for address, op, args, byte_index, byte_value in (
            (root + 0x11, "mov", "(%rdi),%r13d", 0, 0x44),
            (root + 0x511, "mov", "$0xf,%ecx", 1, 15),
            (root + 0x58A, "jne", code[root + 0x58A].args, 1, 0x85),
            (walk + 0x63, "movb", "$0x0,(%rdx,%rax,1)", 3, 0),
        ):
            changed, raw = dict(code), bytearray(payload)
            old = changed[address]
            changed[address] = decoder.Instruction(address, old.size, op, args)
            raw[address + byte_index] = byte_value
            with self.subTest(coherent=hex(address)), self.assertRaises(ValueError):
                graphical.paired_linked_storage(decoder, functions, symbols, changed, starts, raw)
        # A valid rel32 to a different admitted helper is still the wrong call.
        address = root + 0x583
        for target in (symbols[graphical.PAIRED_BYTES].address, root + 0x584):
            changed, raw = dict(code), bytearray(payload)
            changed[address] = decoder.Instruction(address, 5, "call", f"{target:x} <changed>")
            raw[address + 1 : address + 5] = (target - address - 5).to_bytes(4, "little", signed=True)
            with self.assertRaises(ValueError):
                graphical.paired_linked_storage(decoder, functions, symbols, changed, starts, raw)
        for index in range(12):
            raw = bytearray(payload)
            raw[0xA000 + index] ^= 1
            with self.subTest(table=index), self.assertRaisesRegex(ValueError, "read-only page-level table"):
                graphical.paired_linked_storage(decoder, functions, symbols, code, starts, raw)

    def test_linked_semantic_capture_alias_and_closure_mutations(self):
        functions, symbols, code, starts, payload = self.paired_linked_fixture()
        graphical.paired_linked_storage(decoder, functions, symbols, code, starts, payload)
        base = symbols[graphical.PAIRED_ROOT].address
        # Exercise the semantic storage checker directly, so these cannot pass
        # merely because somebody refreshes an emitted-body fingerprint.
        mutations = [
            (0x14, "mov", "%r13,0x48(%rsp)"),
            (0x18, "mov", "0x8(%rdi),%rax"),
            (0x30, "mov", "%r12,0x4c(%rsp)"),
            (0x3B7, "mov", "0x8(%rbx),%rax"),
            (0x566, "mov", "%rbx,0x78(%rsp)"),
            (0x56B, "mov", "%r12,0x80(%rsp)"),
            (0x535, "lea", "0x40(%rsp),%r12"),
            (0x528, "lea", "0x48(%rsp),%r13"),
            (0x54C, "lea", "0x50(%rsp),%r15"),
            (0x6BF, "mov", "%rdx,0x50(%rsp)"),
            (0x6CE, "mov", "%rbx,%rdi"),
            (0x70A, "mov", "%r13,%rsi"),
            (0x621, "mov", "%r12,%rax"),
            (0x627, "add", "$0x2,%rax"),
            (0x638, "mov", "$0x0,%ecx"),
        ]
        for offset, op, args in mutations:
            changed = dict(code)
            old = code[base + offset]
            changed[old.address] = decoder.Instruction(old.address, old.size, op, args)
            with self.subTest(offset=hex(offset), args=args), self.assertRaises(ValueError):
                graphical.paired_root_storage(decoder, symbols, changed, starts, functions)
        # Mutation of each actual pair's start/size, and bypass to each success
        # tail. All six successful guards must dominate initialization and walk.
        for call in (0x583, 0x5A0, 0x5BD, 0x5DA, 0x5F7, 0x614):
            tail = code[code[base + call].next].next
            for target in (code[tail].next, base + 0x624, base + 0x646):
                changed = dict(code)
                old = code[base + 0x4EB]
                changed[old.address] = decoder.Instruction(old.address, old.size, "jb", f"{target:x} <bypass>")
                with (
                    self.subTest(call=hex(call), target=hex(target)),
                    self.assertRaisesRegex(ValueError, "bypasses a successful storage guard"),
                ):
                    graphical.paired_root_storage(decoder, symbols, changed, starts, functions)
        for offset in (0x511, 0x516, 0x590, 0x598, 0x5AD, 0x5B5, 0x5CA, 0x5D2, 0x5E7, 0x5EF, 0x604, 0x60C):
            changed = dict(code)
            old = code[base + offset]
            changed[old.address] = decoder.Instruction(old.address, old.size, "mov", "$0x1," + old.args.split(",")[-1])
            with self.subTest(extent=hex(offset)), self.assertRaisesRegex(ValueError, "guard object/extent/lineage"):
                graphical.paired_root_storage(decoder, symbols, changed, starts, functions)
        extra = deepcopy(functions)
        extra["foreign"] = {
            "calls": [dict(extra[graphical.PAIRED_ROOT]["calls"][-1], target=graphical.PAIRED_WALK, level=3)]
        }
        with self.assertRaisesRegex(ValueError, "external caller"):
            graphical.paired_root_storage(decoder, symbols, code, starts, extra)

    def test_linked_helper_effects_and_private_frame_mutations(self):
        functions, symbols, code, starts, payload = self.paired_linked_fixture()
        graphical.paired_linked_storage(decoder, functions, symbols, code, starts, payload)
        for name in graphical.PAIRED_HELPERS:
            address = symbols[name].address
            for op, args in (
                ("mov", "%rax,(%rdi)"),
                ("mov", "%rax,(%rsi)"),
                ("mov", "%rax,%rsp"),
                ("mov", "%rax,%r12"),
                ("lea", "0x48(%rsp),%rdi"),
            ):
                changed = dict(code)
                old = changed[address]
                changed[address] = decoder.Instruction(address, old.size, op, args)
                with self.subTest(helper=name, op=op, args=args), self.assertRaises(ValueError):
                    # Private pointer LEA may be harmless in isolation. It must
                    # still reject the complete independently audited contract.
                    graphical.paired_linked_storage(decoder, functions, symbols, changed, starts, payload)
                if op != "lea":
                    with self.assertRaises(ValueError):
                        graphical.paired_helper_effects(decoder, symbols, changed, functions)
        layout = symbols[graphical.PAIRED_LAYOUT].address
        for args in ("$0x0,0xb8(%rsp)", "$0x0,0xb4(%rsp)", "$0x0,(%rdi)"):
            address = layout + 0x31
            changed = dict(code)
            old = changed[address]
            changed[address] = decoder.Instruction(address, old.size, "movq", args)
            with self.assertRaises(ValueError):
                graphical.paired_helper_effects(decoder, symbols, changed, functions)
        flags = symbols[graphical.PAIRED_LEVEL_HELPER].address
        for register in ("%rbx", "%r12", "%r13", "%r14", "%r15", "%ebp", "%r12b"):
            changed = dict(code)
            old = changed[flags]
            changed[flags] = decoder.Instruction(flags, old.size, "mov", "%rax," + register)
            with self.assertRaisesRegex(ValueError, "callee-saved"):
                graphical.paired_readonly_leaf(decoder, graphical.PAIRED_LEVEL_HELPER, symbols, changed, functions)

    def test_linked_visited_range_closure_and_spill_mutations(self):
        functions, symbols, code, starts, payload = self.paired_linked_fixture()
        proof = graphical.paired_linked_storage(decoder, functions, symbols, code, starts, payload)
        symbol = symbols[graphical.PAIRED_WALK]
        for offset, op, args in (
            (0x11, "mov", "0x8(%rdi),%rax"),
            (0x25, "mov", "0x10(%rax),%rax"),
            (0x29, "shl", "$0xd,%rax"),
            (0x46, "mov", "%rdx,%rax"),
            (0x4C, "mov", "0x10(%rsp),%rdx"),
            (0x55, "mov", "(%rdx),%rdx"),
            (0x63, "movw", "$0x1,(%rdx,%rax,1)"),
            (0x84, "mov", "%rdx,0x28(%rsp)"),
            (0x2FD, "mov", "0x8(%rsp),%rdi"),
            (0x2FD, "mov", "0x20(%rsp),%rdi"),
            (0x31D, "mov", "%rdx,%rsi"),
            (0x84, "lea", "0x18(%rsp),%rdi"),
        ):
            changed = dict(code)
            old = changed[symbol.address + offset]
            changed[old.address] = decoder.Instruction(old.address, old.size, op, args)
            if offset == 0x2FD and args == "0x8(%rsp),%rdi":
                # Both slots hold the identical closure, so this is semantically
                # safe forwarding; its changed exact machine shape still rejects.
                with self.assertRaises(ValueError):
                    graphical.paired_linked_storage(decoder, functions, symbols, changed, starts, payload)
            else:
                with self.subTest(offset=hex(offset), args=args), self.assertRaises(ValueError):
                    graphical.paired_walker_storage(decoder, symbol, changed, starts)
        # Fixed-RSP violation that restores the final numerical depth still
        # invalidates fixed-offset spill interpretation during the body.
        changed = dict(code)
        for offset, op in ((0x84, "sub"), (0x89, "add")):
            old = changed[symbol.address + offset]
            changed[old.address] = decoder.Instruction(old.address, old.size, op, "$0x8,%rsp")
        with self.assertRaisesRegex(ValueError, "frame base changes"):
            graphical.paired_walker_storage(decoder, symbol, changed, starts)
        self.assertEqual(proof["walker"]["bitmap_store"], symbol.address + 0x63)

    def test_paired_byte_word_dword_overlap_and_weakening_join(self):
        functions, symbols, code, starts, labels = self.paired_r9_fixture()
        symbol = symbols[graphical.PAIRED_WALK]
        baseline = graphical.paired_level_induction(decoder, symbol, code, starts, functions[symbol.name])
        self.assertEqual(set(baseline), {0, 1, 2, 3})
        address = symbol.address + labels["zero_spill"] + 1
        jump = symbol.address + labels["zero_restore"] + 1
        for op, args in (
            ("movb", "$0xff,0x20(%rsp)"),
            ("movw", "$0xffff,0x1f(%rsp)"),
            ("movl", "$0xffffffff,0x1e(%rsp)"),
            ("mov", "%r10,0x1c(%rsp)"),
        ):
            changed = dict(code)
            old = changed[address]
            changed[address] = decoder.Instruction(old.address, old.size, op, args)
            changed[jump] = decoder.Instruction(jump, 1, "jmp", f"{symbol.address + labels['loop']:x} <loop>")
            with self.subTest(op=op, args=args), self.assertRaises(ValueError):
                graphical.paired_level_induction(decoder, symbol, changed, starts, functions[symbol.name])
        # Initially known zero reaches the guard; a second backedge kills that
        # fact. The weakened join must be reprocessed, exposing a zero selfcall.
        changed = dict(code)
        old = changed[symbol.address + labels["zero_restore"]]
        changed[old.address] = decoder.Instruction(old.address, old.size, "mov", "%eax,%r9d")
        changed[jump] = decoder.Instruction(jump, 1, "jmp", f"{symbol.address + labels['loop']:x} <weakened>")
        with self.assertRaisesRegex(ValueError, "decreasing level"):
            graphical.paired_level_induction(decoder, symbol, changed, starts, functions[symbol.name])

    def test_linked_guard_unsigned_intervals_and_overflow(self):
        functions, symbols, code, starts, payload = self.paired_linked_fixture()
        graphical.paired_linked_storage(decoder, functions, symbols, code, starts, payload)
        guard = symbols[graphical.PAIRED_GUARD]

        def evaluate(a, size_a, b, size_b):
            # Independent miniature interpreter for the retained guard's actual
            # decoded operations, not an invocation of the source predicate.
            values = dict(rdi=a, rsi=size_a, rdx=b, rcx=size_b, rax=0)
            address, carry = guard.address, None
            for _ in range(20):
                row = code[address]
                args = decoder.arguments(row.args)
                if row.op == "ret":
                    return bool(values["rax"] & 255)
                if row.op == "add":
                    left, right = (operand.removeprefix("%") for operand in args)
                    total = values[right] + values[left]
                    carry = total > (1 << 64) - 1
                    values[right] = total & ((1 << 64) - 1)
                elif row.op == "cmp":
                    left, right = (operand.removeprefix("%") for operand in args)
                    carry = values[right] < values[left]
                elif row.op == "jb":
                    if carry:
                        address = decoder.target_of(row)
                        continue
                elif row.op == "mov":
                    self.assertEqual(args, ["$0x1", "%eax"])
                    values["rax"] = 1
                elif row.op == "xor":
                    self.assertEqual(args, ["%eax", "%eax"])
                    values["rax"] = 0
                elif row.op == "setae":
                    self.assertEqual(args, ["%al"])
                    values["rax"] = (values["rax"] & ~255) | int(not carry)
                else:
                    self.fail("Unexpected guard interpreter instruction: " + row.op)
                address = row.next
            self.fail("Guard exceeded its closed acyclic instruction bound")

        maximum = (1 << 64) - 1
        cases = [
            (0x1000, 24, 0x1000, 16, False),
            (0x1000, 24, 0x1001, 16, False),
            (0x1000, 24, 0x1008, 56, False),
            (0x1000, 56, 0x1010, 24, False),
            (0x1000, 24, 0x1017, 16, False),
            (0x1000, 24, 0x1018, 16, True),
            (0x1000, 24, 0x1019, 16, True),
            (maximum - 24, 24, maximum - 40, 16, True),
            (maximum - 23, 24, 0, 16, False),
            (0, 24, maximum - 15, 16, False),
            (maximum - 23, 24, maximum - 15, 16, False),
        ]
        for a, sa, b, sb, wanted in cases:
            for arguments in ((a, sa, b, sb), (b, sb, a, sa)):
                with self.subTest(arguments=arguments):
                    self.assertEqual(evaluate(*arguments), wanted)

    def test_complete_seed_induction_rechecks_closure_and_alias_bytes(self):
        functions, symbols, code, starts, payload = self.paired_linked_fixture()
        storage = graphical.paired_linked_storage(decoder, functions, symbols, code, starts, payload)
        symbol = symbols[graphical.PAIRED_WALK]

        def verify(changed):
            return graphical.paired_level_induction(
                decoder,
                symbol,
                changed,
                starts,
                functions[symbol.name],
                (storage["walker"]["bitmap_store"],),
                storage=storage,
            )

        baseline = verify(code)
        self.assertTrue(all(level["caller_memory_contract"] for level in baseline.values()))
        mutations = [
            (0x84, "mov", "%rdx,0x28(%rsp)"),
            (0x89, "movb", "$0x0,0x2f(%rsp)"),
            (0x89, "movw", "$0x0,0x27(%rsp)"),
            (0x89, "movl", "$0x0,0x26(%rsp)"),
            (0x2FD, "mov", "0x18(%rsp),%rdi"),
            (0x31D, "mov", "%edi,%esi"),
            (0x31D, "mov", "%rdx,%rsi"),
        ]
        for offset, op, args in mutations:
            changed = dict(code)
            old = changed[symbol.address + offset]
            changed[old.address] = decoder.Instruction(old.address, old.size, op, args)
            with (
                self.subTest(offset=hex(offset), args=args),
                self.assertRaisesRegex(ValueError, "memory contract or identical closure"),
            ):
                verify(changed)
        changed = dict(code)
        old = changed[symbol.address + 0x2F8]
        changed[old.address] = decoder.Instruction(old.address, old.size, "mov", "0x28(%rsp),%r9d")
        with self.assertRaisesRegex(ValueError, "decreasing level"):
            verify(changed)


class CaptureAdmission(unittest.TestCase):
    capture = "graphical-console-capture"

    def test_capture_structure_gate_cannot_be_cleared_by_source_or_pin(self):
        graphical.require_capture_structure("graphical-console")
        with self.assertRaisesRegex(ValueError, "Missing current capture structure evidence"):
            graphical.require_capture_structure(self.capture)
        with tempfile.TemporaryDirectory(prefix="graphical-capture-pending-") as directory:
            receipt = Path(directory) / "admission.json"
            receipt.write_text("stale receipt")
            with (
                patch.object(graphical, "RECEIPT", receipt),
                patch.object(graphical, "provenance", return_value={}),
                patch.object(graphical, "image_evidence", return_value={"source": "accepted"}),
                patch.object(graphical, "stack_evidence", return_value={"normal": 1}),
                patch.dict(os.environ, {"GRAPHICAL_CONSOLE_REVIEW_SHA256": "0" * 64}),
            ):
                with self.assertRaisesRegex(ValueError, "Missing current capture structure evidence"):
                    graphical.emit(self.capture)
                self.assertFalse(receipt.exists(), "A source check cannot leave a capture admission receipt")
                data = dict(
                    schema="aurora-graphical-console-admission-v4",
                    mode=self.capture,
                    status="requires-independent-review",
                    clock="tcg-original-clock",
                    build={},
                    image={"source": "accepted"},
                    stack={"normal": 1},
                    sha256={},
                )
                receipt.write_text(json.dumps(data))
                with (
                    patch.object(graphical.common, "hashes", return_value={}),
                    patch.dict(os.environ, {"GRAPHICAL_CONSOLE_REVIEW_SHA256": graphical.digest(receipt)}),
                ):
                    for check in (graphical.checked, graphical.reviewed):
                        with (
                            self.subTest(check=check.__name__),
                            self.assertRaisesRegex(ValueError, "Missing current capture structure evidence"),
                        ):
                            check(self.capture)

    def test_unknown_emission_reports_original_bytes_and_unproved_effect(self):
        symbol = decoder.Symbol("unreviewed_capture_emission", 0, 5, 1, 2)
        rows = {
            0: decoder.Instruction(0, 4, "enter", "$0x20,$0"),
            4: decoder.Instruction(4, 1, "ret", ""),
        }
        with self.assertRaisesRegex(ValueError, "Unknown instruction semantics: enter") as rejected:
            decoder.analyze_function(symbol, rows, {0: symbol.name})
        report = graphical.unreviewed_linked_function(symbol, rows, b"\xc8\x20\0\0\xc3", rejected.exception)
        self.assertIn(symbol.name, report)
        self.assertIn("call/stack effect remains unproved", report)
        self.assertIn('"bytes":"c8200000"', report)
        self.assertIn('"operands":"$0x20,$0"', report)
        self.assertNotIn('"operation":"ret"', report)


class CaptureStructure(unittest.TestCase):
    """Hand-authored ELF symbol/section records, never compiled build snapshots."""

    @staticmethod
    def linked(base=0x2000, section_index=1, local=""):
        fields = (
            ("capture_scenario", 1),
            ("pixel_attempts", 8),
            ("consumer_entries", 8),
            ("sample_calls", 8),
            ("output_attempts", 8),
            ("completed_samples", 8),
            ("stores", 8),
            ("wakes", 8),
            ("active_operation", 4),
        )
        symbols = [
            decoder.Symbol(
                f"_ZN6aurora4uefi12_GLOBAL__N_1{local}{len(name)}{name}E", base + index * 8, size, section_index, 1
            )
            for index, (name, size) in enumerate(fields)
        ]
        # Authority identities/sizes are written independently of the checker.
        authorities = (
            (
                "_ZN6aurora7console7SessionINS_4uefi12_GLOBAL__N_116ServiceTransportENS3_15ServicePlatformEE6grant_E",
                80,
                24,
            ),
            (
                "_ZN6aurora7console7SessionINS_4uefi12_GLOBAL__N_116ServiceTransportENS3_15ServicePlatformEE11generation_E",
                104,
                8,
            ),
            (
                "_ZN6aurora7display7SessionINS_4uefi12_GLOBAL__N_116DisplayTransportENS3_15ServicePlatformEE6grant_E",
                112,
                48,
            ),
            (
                "_ZN6aurora7display7SessionINS_4uefi12_GLOBAL__N_116DisplayTransportENS3_15ServicePlatformEE11generation_E",
                160,
                8,
            ),
            (
                "_ZN6aurora9graphical5EntryINS_7console7SessionINS_4uefi12_GLOBAL__N_116ServiceTransportENS5_15ServicePlatformEEENS_7display7SessionINS5_16DisplayTransportES7_EES7_E7active_E",
                168,
                1,
            ),
        )
        symbols += [decoder.Symbol(name, base + offset, size, section_index, 1) for name, offset, size in authorities]
        sections = [(0,) * 10] * section_index + [(0, 8, 3, base, 0, 256, 0, 0, 8, 0)]
        functions = {
            name: None
            for name in (
                "_ZN6aurora4uefi21run_graphical_consoleEmRKNS0_5BytesE",
                "__au_runtime_console_next",
                "__au_runtime_console_put",
                "__au_runtime_display_pixel",
            )
        }
        return SimpleNamespace(symbols=symbols, sections=sections, functions=functions)

    def test_relocated_storage_and_both_local_spellings(self):
        for base, section, local in ((0x2000, 1, ""), (0x9800, 3, "L")):
            evidence = graphical.capture_structure_evidence(self.linked(base, section, local))
            self.assertEqual(evidence["schema"], "aurora-graphical-capture-structure-v1")
            self.assertEqual(evidence["status"], "structure-only")
            self.assertEqual(evidence["behavior_qualification"], "pending-hosted-and-guest-gates")
            self.assertEqual(evidence["states"]["capture_scenario"]["address"], base)
            self.assertEqual(len(evidence["states"]), 14)
            graphical.require_capture_structure("graphical-console-capture", evidence)
            with self.assertRaises(ValueError):
                graphical.require_capture_structure("graphical-console", evidence)

    def test_missing_duplicate_and_crossed_state_owners(self):
        original = self.linked()
        for index in range(14):
            for change in ("missing", "duplicate", "other-spelling"):
                linked = deepcopy(original)
                if change == "missing":
                    del linked.symbols[index]
                elif change == "duplicate":
                    linked.symbols.append(linked.symbols[index])
                else:
                    linked.symbols.append(self.linked(local="L").symbols[index])
                with self.subTest(index=index, change=change), self.assertRaises(ValueError):
                    graphical.capture_structure_evidence(linked)

    def test_state_size_type_section_and_bounds(self):
        for field, value in (
            ("size", 4),
            ("kind", 2),
            ("section", 0),
            ("section", 2),
            ("address", 0x1FF8),
            ("address", 0x2100),
            ("address", 0x2009),
        ):
            linked = self.linked()
            row = linked.symbols[1]
            values = dict(name=row.name, address=row.address, size=row.size, section=row.section, kind=row.kind)
            values[field] = value
            linked.symbols[1] = decoder.Symbol(**values)
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                graphical.capture_structure_evidence(linked)
        for field, value in ((1, 1), (2, 0), (2, 2), (2, 6), (2, 7), (5, 32)):
            linked = self.linked()
            section = list(linked.sections[1])
            section[field] = value
            linked.sections[1] = tuple(section)
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                graphical.capture_structure_evidence(linked)

    def test_overlapping_state_and_missing_functions(self):
        linked = self.linked()
        row = linked.symbols[1]
        linked.symbols[1] = decoder.Symbol(row.name, 0x2000, row.size, row.section, row.kind)
        with self.assertRaisesRegex(ValueError, "Overlapping"):
            graphical.capture_structure_evidence(linked)
        for name in self.linked().functions:
            linked = self.linked()
            del linked.functions[name]
            with self.subTest(function=name), self.assertRaises(ValueError):
                graphical.capture_structure_evidence(linked)

    def test_production_absence_and_orphan_capture_counter(self):
        linked = self.linked()
        linked.symbols = linked.symbols[2:]
        self.assertIsNone(graphical.capture_structure_evidence(linked))
        graphical.require_capture_structure("graphical-console")
        linked = self.linked()
        del linked.symbols[0]
        with self.assertRaisesRegex(ValueError, "without scenario"):
            graphical.capture_structure_evidence(linked)

    def test_incomplete_or_overclaimed_structure_evidence(self):
        evidence = graphical.capture_structure_evidence(self.linked())
        for key in evidence:
            changed = deepcopy(evidence)
            del changed[key]
            with self.subTest(missing=key), self.assertRaises(ValueError):
                graphical.require_capture_structure("graphical-console-capture", changed)
        for key, value in (
            ("schema", "aurora-graphical-capture-linked-gcc16-v1"),
            ("status", "machine-behavior-proved"),
            ("behavior_qualification", "passed"),
            ("states", {}),
        ):
            changed = deepcopy(evidence)
            changed[key] = value
            with self.subTest(field=key), self.assertRaises(ValueError):
                graphical.require_capture_structure("graphical-console-capture", changed)

    def test_all_console_profiles_use_shared_scalar_stack_rules(self):
        for profile in ("program", "service", "framebuffer", "graphical"):
            shared = graphical.load("shared_scalar_" + profile, ROOT / "tests/kernel-uefi-owned-bytes-stack.py")
            shared.configure_console(profile)
            self.assertTrue(shared.CONSOLE_SCALAR <= shared.NEUTRAL)
            self.assertTrue({"testb", "testl", "testw"} <= shared.READ_ONLY)
            symbol = shared.Symbol("pci_byte_flag", 0, 2, 1, 2)
            for op, args, accepted in (
                ("orb", "$0x1,(%rax)", True),
                ("orb", "$0x1,%spl", False),
                ("unknown_new_instruction", "", False),
            ):
                code = {0: shared.Instruction(0, 1, op, args), 1: shared.Instruction(1, 1, "ret", "")}
                with self.subTest(profile=profile, operation=op, operands=args):
                    if accepted:
                        self.assertEqual(shared.analyze_function(symbol, code, {0: symbol.name})["local_peak"], 8)
                    else:
                        with self.assertRaises(ValueError):
                            shared.analyze_function(symbol, code, {0: symbol.name})
            with self.assertRaises(ValueError):
                shared.configure_console("unknown")


if __name__ == "__main__":
    unittest.main()
