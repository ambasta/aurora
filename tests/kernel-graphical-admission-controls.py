#!/usr/bin/env python3
"""Independent hostile combined-profile controls. Source prepared, not qualified.

No compiler, guest or subprocess is launched. All safety assertions use explicit
exceptions or unittest assertions and remain active under python -O.
"""

from copy import deepcopy
import base64
import zlib
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
            signature = "paired walker exact source signature"
            location = "kernel/uefi/tables.hpp:1:1"
            line = location + ":" + signature + "\t128\tstatic\n"
            (root / "graphical-console.su").write_text(line)
            label = signature + "\n" + location + "\n128 bytes (static)"
            graph = ('graph: { title: "kernel/uefi/graphical-console.cpp"\n'
                     + 'node: { title: ' + json.dumps(graphical.PAIRED_WALK)
                     + ' label: ' + json.dumps(label) + ' }\n}')
            (root / "graphical-console.ci").write_text(graph)
            obj, linked = self.paired_object(), self.paired_object(linked=True)
            with (
                patch.object(graphical, "CPP_OBJECTS", ("graphical-console",)),
                patch.object(decoder, "Elf", return_value=obj),
                patch.object(decoder, "associate_object", wraps=decoder.associate_object) as associate,
            ):
                frames, receipts, aliases = graphical.graphical_cpp_frames(decoder, root, linked)
                self.assertEqual(frames, {graphical.PAIRED_WALK: 128})
                self.assertEqual(receipts[graphical.PAIRED_WALK][0]["source"], "kernel/uefi/tables.hpp")
                self.assertEqual(len(aliases), 1)
                self.assertEqual({call.args[2].name for call in associate.call_args_list},
                                 {graphical.PAIRED_WALK, graphical.PAIRED_ALIAS})
                self.assertIn(graphical.PAIRED_ALIAS, linked.functions)
                for changed in ("", graph.replace(graphical.PAIRED_WALK, graphical.PAIRED_ALIAS)):
                    (root / "graphical-console.ci").write_text(changed)
                    with self.assertRaises(ValueError):
                        graphical.graphical_cpp_frames(decoder, root, linked)
                (root / "graphical-console.ci").write_text(graph)
                linked.function_bytes = lambda symbol: b"\xcc" * symbol.size
                with self.assertRaisesRegex(ValueError, "instruction mismatch"):
                    graphical.graphical_cpp_frames(decoder, root, linked)

    def test_session_frames_require_distinct_source_and_object_ownership(self):
        frames = {symbol: 16 for symbol in graphical.SESSION_VALIDATORS}
        associations = {
            symbol: [dict(object="graphical-console.o", source=source, bytes=16)]
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
            for records in ([], associations[symbol] * 2,
                            [dict(object="console.o", source=source, bytes=16)],
                            [dict(object="graphical-console.o", source="kernel/foreign.hpp", bytes=16)]):
                changed = deepcopy(associations)
                changed[symbol] = records
                with self.assertRaises(ValueError):
                    graphical.verify_session_frames(frames, changed)

    def test_exact_generated_signed_division_pairs(self):
        owner = "__au_v_m1_24kernel_graphical_console_n0__d9draw_cell"
        symbols = {owner: decoder.Symbol(owner, 0, 10, 1, 2)}
        payload = bytes.fromhex("489949f7fb489949f7fb")
        rows = {
            0: decoder.Instruction(0, 2, "cqto", ""),
            2: decoder.Instruction(2, 3, "idiv", "%r11"),
            5: decoder.Instruction(5, 2, "cqto", ""),
            7: decoder.Instruction(7, 3, "idiv", "%r11"),
        }
        verify = graphical.verify_generated_divisions
        self.assertEqual(len(verify(symbols, rows, payload)), 2)
        for position in range(len(payload)):
            changed = bytearray(payload)
            changed[position] ^= 1
            with self.subTest(position=position), self.assertRaises(ValueError):
                verify(symbols, rows, changed)
        for address in rows:
            changed = dict(rows)
            del changed[address]
            with self.assertRaises(ValueError):
                verify(symbols, changed, payload)
            row = rows[address]
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
        for owners in [
            {},
            {owner: decoder.Symbol(owner, 1, 9, 1, 2)},
            {owner: decoder.Symbol(owner, 0, 7, 1, 2)},
            {owner: decoder.Symbol(owner, 0, 9, 1, 2)},
            {"foreign": decoder.Symbol("foreign", 0, 10, 1, 2)},
        ]:
            with self.assertRaises(ValueError):
                verify(owners, rows, payload)
        changed = dict(rows)
        changed[10] = decoder.Instruction(10, 2, "cqto", "")
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
                if name in {"aurora_reflect_size", "aurora_reflect_field_count"}
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
        for name in ("aurora_reflect_size", "aurora_reflect_field_count"):
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
        foreign = decoder.Symbol("aurora_reflect_extra", symbol.address, symbol.size, 1, 2)
        with self.assertRaises(ValueError):
            graphical.verify_reflection_body(decoder, foreign, baseline, payload)

    def test_reflection_helper_exact_inventory_and_binding(self):
        self.assertEqual(graphical.REFLECTION_HELPERS, frozenset(("aurora_reflect_size", "aurora_reflect_field_count")))
        names = graphical.expected_language_functions()
        imports = [
            decoder.Symbol(name, 0, 0, 0, 0) for name in ("__au_runtime_console_next", "__au_runtime_display_pixel")
        ]

        def binding(name):
            return (
                "GLOBAL HIDDEN"
                if name in (graphical.BRIDGE, graphical.VALUE_BRIDGE)
                else (
                    "GLOBAL DEFAULT"
                    if name in ("aurora_reflect_size", "aurora_reflect_field_count")
                    else "LOCAL DEFAULT"
                )
            )

        table = "\n".join(f"""1: 000000 1 FUNC {binding(name)} 1 {name}""" for name in sorted(names))

        def verify(rows=table, functions=names, symbols=imports):
            with patch.object(graphical.subprocess, "check_output", return_value=rows):
                return graphical.verify_language_object(
                    SimpleNamespace(functions=functions, symbols=symbols, path=Path("fixture.o"))
                )

        verify()
        for name in ("aurora_reflect_size", "aurora_reflect_field_count"):
            for changed in ("GLOBAL HIDDEN", "LOCAL DEFAULT", "WEAK DEFAULT"):
                mutant = table.replace(f"GLOBAL DEFAULT 1 {name}", f"{changed} 1 {name}")
                with self.assertRaises(ValueError):
                    verify(rows=mutant)
            with self.assertRaises(ValueError):
                verify(symbols=imports + [decoder.Symbol(name, 0, 0, 0, 0)])
            with self.assertRaises(ValueError):
                verify(functions=names - {name})
        with self.assertRaises(ValueError):
            verify(functions=names | {"aurora_reflect_address"})

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
            "aurora_reflect_size",
            "aurora_reflect_field_count",
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
        for name in [graphical.ENTRY, graphical.BRIDGE, "aurora_reflect_size", "aurora_reflect_field_count"]:
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
            build = root / "graphical-console-build.json"
            build.write_text(json.dumps(record))
            receipt = root / "graphical-console-admission.json"
            data = dict(
                schema="aurora-graphical-console-admission-v2",
                mode="graphical-console",
                status="requires-independent-review",
                clock="tcg-original-clock",
                build=record,
                image={"independent_image_result": 1},
                stack={"independent_stack_result": 456},
                sha256=hashes([paths["source"], paths["payload.bin"], build]),
            )
            receipt.write_text(json.dumps(data))
            with (
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


# Independent original numeric capture002 snapshot: retained objdump rows, ELF
# symbol/section identities, complete payload bytes and original artifact pins.
# Compression keeps these observed facts self-contained. No compiler, disassembler
# or external fixture is used by these controls; no admission receipt is issued.
CAPTURE_002_SNAPSHOT = (
    "c-qXp3y)m6kuLaGjK($4#?@T#&EQ~Qpa-ivYjjWBaC@-84i<&Xb53@bQBuiOQd_<I=a)QuoCrQL>yep~3=6FjOg@9bU@+o~|L>dW"
    "eqO%$*Z=-+_J+UtX1bfddGpOT|IeHM=5MtB=kD&#|C>AZyMOz%9Bywu?0&nu-_1AgcDL{U7>b$rtK0M|8~*vr-N*D#cq86?^Y?cj"
    "{69@q!}9*)!*BnSeKu<~oQ3Az-T&%K{tx!~aCr0kWxic0I@Iy`{=rjzzdYW)34g5wiwX1R@QcqY!ELPy`MZBR>^|LnyqWIby}OTn"
    "7MwJ;l(vL<qcY*!-#<Kl_`@6j_ezqegX}XDYHU(!I(c%fX!m~3!y$iIsP#iArx=>$Lp{ld-R<4lVWmT{r_7^fZ)EPK@0_2lhuzvk"
    "EeXNT*25GDCd}5u66*Hk$NleqKR^C!7~kz5!d!>{oNxcI7KJd%hb6DBc1>fj@`MOgrtfjdVke9mbi&xJ6OSM7AAk4z-CfnVA&o&9"
    "m=&~BRt{#snn0M=NerV4i?=SVjr_7-!tBn!`?q(C=agR;Kc_;ilM1{)PFRQY_-Vh@7{6QG(mKrbyJKrZyJ164Y)tkq>@)v1_w(}`"
    "9+(aGYbm>x3g6zOqH`%4ca#V`7<=b=kQZj<Y+drdzYqP;6Yd9>X*X6Y&6yjl9OvT6{KL7bs->HI_qlKi=j$APTpmAeEvD{^IE|tA"
    "j<3D<Qyn_L#Lf$m`uhLw@8U+D*RG_Rg-)Bikk_6*z#PdAFDlI252e_qt=q6%`Qi5cl=vimwD@BZU25H?^O8!&`jy=3w>wn7jnyk%"
    "&7ShYmw85e^dH{efB5I`*k|@_VE2{hGau+x7J2&JD!O8cNHVL;|M2PYm$e`J5Akcu?wO*9;N-haO8f0es)|FhL>#TWoGJ2+ee=!T"
    "vRgYfAJpXgb&CWp2S)f8iqPbs@Y!T$FE?-g?;p+X)5HD44u07^%>UdyEas=>;dXbYJ}#d>zWwPVxBK1W?R4|_@!|IU&o{r`F8}<~"
    "<UjMt|KR51!|wLu<DaItZ{u78;rIQAA}qKQgz|aou+x|BmSFUl6x+$gG@VbYs`(ULT)cbSQvTp&^9ZqSp8HShcJ{(OoQf(^6jdRF"
    "&{T;K!fXfn61&aC&42vx=YRk1hnt%pZ@3C4<uiKg_mpC>%fd@K-`c$UxZ~!Vu$g{0+)6^OOz!EqXKEEih3mPDUj_Xt;#bvdt4y(-"
    "Z73A9dnZyf@9Z_9MI)j!MGtn8@F#dtcz!=Uh&N>nhV0Kp3sLivrM$?I8f7oP6M#q-F3JWKAaUbX9c|pa|MYIZJiPra)e2-6Er(_o"
    "#Z6vDZOfn~W0xMZ^qagdm83tgUpi>XsVH6+Sq)kWy3~3bw7B?6OUW96n;MrdUuh|;m7ZBWXr)Jk)|X#tO;*~kP#Ls-#Y!7FI6kDQ"
    "r-Rqiarr$h0ne-Q8wxj}!mUThpC5J~e!2B!{DtoQ<Ne)ovtIAs{+g=LPZ#IX4K*XhD#5Pf*GjOf_*Hcd0Tq?(>JU&-v93hDqS`eQ"
    "^~wu2vMx}oNs9LrFD2T0V5U$W;QPV^N~}y!&WUL|D3rYT>MMVi+I(vYrxe>}LD@|+=9BB#BK(OiU8={uG3DkEFW-KMY4lo`y91wh"
    "{fg8sUAjBkOqwZEEsHhvvUq)Xo3PzEl$O{jtG1TIy^n=I--gxwL%HcH;FUFHS&J15i2`yL-ffpF1?e*Ul$mxM&w}T<wkHno1#b!$"
    "ykvG@j1J_mNt`*Au(ZT7Zza}A)?6V=4>$eZLb8nT;cnM)w-nY}wq6QJ`XCt8y_D-UWeOMQZLeioYww8cq2sMEQ9J>4Cf*Hq^IY!j"
    "xikKPs4#_X)*Zh?f{ORc10toS^twvEsk^kXA~QfR8!V_@f3R%2;N$IGpzjdfh|yq-ri}w4xwcY=Dz$P{sWqfhfkqT>hO|;ZmBMh^"
    "fliY^J@w4oRBBPBPLC>eKq{3`7{DYOOd)N9Fw9^MSew&ZbB1*$&LFy12@GOczV7a1OiKpPRa|<G?QaVU(S9rVK)o_TwUpR^ppr3&"
    ">SUBP65lcpsy)K(|G9fV-yaV8*WKOi?B$<&{IGlfr|<oL?0@^X{P50S@0GFsIIz+(=h@eA{r2s<*ju@t1lcSUjD)+pNLZ!*D%jP2"
    "B)3EqTt;cStNkr-J6DsbQVVQl^P>+d8_m9vZr`|-{*N*V;Z})Cm{!QfQ^=Uu*>!=`Zm>X-rxl8tR~EB!vpvVt(E!!Xp@?|{RD~62"
    "og5onC5$820gi=wRD&$J>C7Uo@%MO<^}qY2e3U;gAK$+F`yb<v^q`lvvi*lmnR;pY=)z+;xgD>Q8x=1r_zQX`%%~yZNbl6vZ%M6T"
    "a+_T%UE8}=0klfIpm)k*4zO%{eTdCbUiFi<6^e9XG4`S(Y=1=eq8-R(I<PaMTb7QHY^L>e{CjKhprA7-_n*tV`-k8DbN3<b`>3y5"
    "5dHmZy$mn=dEO6ph}y?mC^N6OB^L?n@siY!)tH;iyw;J;x&8zqA@0rHlUfF*<LUpQ`_OYJ>kd@KcY(m-+k(jY!~12kWn`iu)ys{N"
    "jNt2|g>+NDn}SWTn__JwGSIgxhlD2-zOfKQ8(YT`4*~`ca3I${e4c*!d0jmJoAeVYY7={Uhgq9U`v;`Kf`)w?OTZt>K?b$LQ=~Jf"
    "ReyT?<!&`x-Ib#W;saP(aCAz8mSif`R+mP%3#nLtD)~Md3?Z7#$g@gn!65tn=_N6gbNFFfTZ0~?<jxK%;_+DkEZ^34RZ+tNv+X1U"
    "OC|3nrT`e}gWY}us`*W(;Lhy_`$LGdKU}_vL{3QE>v4lS#SM;)xWTajH#k1v2FEEkY|n{~V{Wj6@$n^&&v8edsn)A|YC@#vqQ`Zj"
    "Myn`ndihhE)}LfRd@~dlzelZvRkpeKA{{S3k`LI8Lu5B6b+gow+njXIkR(n~Zi9;1oYDi9a_U*__*+X~9yu)s^2qCo6|+H~*PLOe"
    "c+J=muUS6eHLC`^X6=aAfFoWzwU->o<^g-3>M`ZgetKpBMuNvVv7UYF5~;&HIQz^TE24LM{CFE|4d~qEY+l=#6H!*n#0Trd!!7mr"
    "LUG3RV5L0C^_PmX_(Y7?D$anX=)q!n61rB&Wwcs)pPtYqxmcmgx+kex#YReY?ql3(vG>6mhkma#78Z}Um;{aQK_>YvWuD3<zBIN_"
    "Ob-fGWLC+uS=a<;z|iXZqiwt1EQ6M$&MjF^9-(BpXm}FQ{~ysaEVDp<#fqxsJ0r45^icd4V3isl?mr+Kt^Yc@lyK%4)|owb7O$T~"
    "ubv0CTMOrGbh+{*`F#DK2Y(E#t?F$t{GW|0)if|^O1VolaXIi~O8w(x$N5`$W7FfogQBq>rk_V;apkcmbVd?6tf1GJw8O>}@~3%1"
    "Yic#xZfwh=P1Li^oC>&N9DYJ|(XLi}yhN-^rn)pVSCYh@!N1};D^@+)OwoF`nR|SRb<!W^caIOnu_k(6Y=iaex%(xNke;fU9<*<D"
    "YQIt+xAy`bTr{v5d=mA`p)X=DVh86O`$|>5DBM}nul>GpE)h&!reA_ldja1b*|^|}_RB%jFJiqoXTSUfkMv8Ueo0RIHSd~!Nw`qI"
    "6lL!jbxYAl$^A|>-O~C(-7=MTgF*c=y6P8i`ent1`ep4{vl4)=1d5HW95(rriSg+t938&dE{$Bckx|Z*;033fWODFG#DmAfz{yuK"
    "+ZeqxKA|NSjS<czipD=(?OBH5p9)59IXoKPw^K<9MYMyp2GTe-8z%FyAWcY8!?YG4HAvSKkfa7hYH)9oBE8WawN0V!YZ;AP!4XyS"
    "!87Q@)B0#f)K%U&re(+2os>9<t=&&(%?^D+rDuNFI^t?OC=bv7eS4oL(F0j;nznSjVFyKK(iv=jRh!n7ZVifYTtK4&G8Hh*dwg*P"
    "bxrFUue0I`S1z{7)3gK^0Ah&V_K)&>3RUGhQh9u@DUS=Rsa)E&20S@Rk>?4~)}R@&E(hzgBYp6?5|EpcFF=|whHUjvfRh^h6{7Cs"
    "o)&PpfR|am0BM5gDIEAJx+>Yl*<W@)FMr$Z@0LgN>+*1W`0eexzkdJYPwXa&wYPs+|H0vhdtcLcA8x1b=6AP`kGJ>l-@g6v`~SN8"
    "^WSdX{r%nBo9XUPfBpWa?{40{-T&mmr{v-52Ig>2QAIaBy@!-DSj*=d%R~XF87FjBGqh$SbFe2x8UOCXKHCPrE!W%PbIj#4x~s=`"
    "cpdNXM6RSU2;`2f7d2=@tJH>2qeDhx|5C#SW)EfOToVi?FV`p67c}%vzg`V8weoY}$u(o6+imKs7<6V4sWYl|R8E3LQ-{zA-JG=6"
    "&DlaWls3f0P43!vT&|YSAC~FkGT$8Tc0WH>J0W$?=o52AJ;aeG3J<;k_|ak?gAU@WMINK2VFEj3?+9)JWg_K>2X~nV0h@##Z&5#B"
    "<csG?(5M0A4AxGbm}sIgdCjDwGGVc!*KnWo8qN)qgMFU*ZWtU1L~=+aFi~6T8IBC!oTl_)@LH`5q(0S7;OL@Z1ofNRSzT++MqI{m"
    "%3q^ZZ&#*Exlz2oD+?VqX4((tz)ObImS&?}X=or8a$NQ#bCykK3~x7%ZwPN3WAtd>83V&TWh~#O0S1;mbx4*y6TN#nd&*cd+Ed25"
    "c2D6gV`%utbGHn*fket(^C#^Sw~QOwS}jBKWJW@KPD0$W$|qB9TgFlo_`H+Nma+UomtY$onY*!<LW~yBQlIc=u8);$$bD8K%as{f"
    ";B~gZTS@P?$=+9npxAH-O1@?YYP^B0=Fb{}rkrtDiYI3tMaR&XM`8GDMiFmx{ZW|BQfdwZF`!Kn1J?49Bdw<y%HFLB(UO3UbFz08"
    "?QziU)^Z&WsyWA}vCD^{RS_RZhl5vyeE9nfjrnj3Yr^lUpbv{ie)*^m4wAK-7tcQRNPp(=6&o2HK~dwLn;IJ}XmR=BSI+0iHU~zG"
    "y!t%Nj%;&aU*NUJYv&Q<oX274c<4z(8zBG;eB*fX7I|(Lof+8(!L@Cri-%*p(ZhC`M9uVof?-lm9bbPv-)6l&eO0Yem10A=eL1@Z"
    "SCW3*4o~hOWEeRdRbE~`1-B9!JJ!4$I3<Q6)G2%UF4AjoH2md&-B-wv%86ulra8HS7s)_`I(vB;;;cRT*6TpLV)$T(JV`^O2~S=n"
    "MjCmmvd_yjxyrZO7qO?@Hgie7De@qfzNTY#OKLhEt6S5%?cp)S)iOcYW&y4%;o^%>qegr@PCt)6mr;LwLWiO!X2-JTNv6GsX41&0"
    "B$yHdg+wrVa%$Fkjtiy*@+6Li+GTQS3Q`f*7O~5Mix`88tWQ77WDdB9zj}s1z|B8@wHo_U6D~!sk`r`p+;YBsobG>J9&UEihuiAH"
    "{nsCVx-suo*JdvN^2=|JAu=&&)Q_1Nqq}5l(G|?0n*gZ8U?um5RFRV-&>H5b9_!fL#Qw9(ToDDYocFog`W4VU$T_-*7L!0+s9%D("
    "%&%^W0yiuL-KpqWox2|$BRe*5!4-KhkG}G^n_1HrK*&d62R<HV*`?m<?1+nP>W{Yse1L0(7{;1WohH{w!HlNQoAX@W=m7xagd8j-"
    "apP{_ByCwjRp7>q<WBNTDOQtPOhWg2FryL9d4!d2iY$$yc1?k4*YMtjTvJ4FO{oW;r_t-GX6<ruAJ5E5*4m!|ggvc3)ZGt`CQ#YQ"
    "09OU6sv%C6C#_ZZj{alo&9YyxI2OWghS5NsO?{dQi5?l7PHdYZ;bKI8Etm%q&#ENx0$_%ro1#Bgdb9ICp;p~`1@Ht!qAPwvGZi-q"
    "amLKQGRUqRCTO>*8@Y((=)9Wms`pJ#2Yg8Q0{;IAodk_-8I4Wnu>rB+bG043!PldJCb7}>wFMN#jtr7QIBLTO%No{nm$Bgs$<&CK"
    "B{Rh69i4g=j&Tu^GXzZLr+I^>5|R%$t>mV88$eWngqCAsG_@iPLFnydaANS-Xx*HPuVID(!vIAsQ&1Y&%G#tY%FbIOrfx5dP7O?v"
    "cE3+OQ4XJ|Ym|w^bDX9_s|J1R^B>SUX-fmI_J!G{LBL*O#G@|psI1H&m`A0d4uBwC&7;z)3-PFRL|}SdylFf6>#qYf0|!hy>r^3r"
    "WTYO2LegMOKhXLTDikqOo^hZmLQZWbgHZL!pg5BFP7mJb?W9tT{Am(jVFb9-wTd;mG52$LJSlv&dP22Q(4&0RS-E<*Jbv1fLzeB("
    "A*+;mR?~{O*)ic+=;mhk>E_|n`;WKpmYWSE<=5Tar*s!oRRo;ap@q^&6zm2Dec)5Bsq%4!jU$zz#xr|pG#6$0g*ehuA6JP)Lcqiz"
    "zRHK@*irx&H%=%gM^|g*%;;*Z$bqUB(Lu)He(`S_be!G;u~(Q@g{^|ZAY7|4@C?QoS)mj&+vv*ktN|JkI>xnikVZVoBH^$=J0$kk"
    "$j?9Qe!Ktl@h=behugd5Pd~g9Z{MaU;&*F^TN;%Z-q*C`6gts=5hFAZPg|9A`~tl3kyaQ5a^WxTHBY@(s)ID-KbsEJkpB!lz&Wj1"
    "4{<Jd0Cj-nv=;<D{5Y)${Ldca#2HS}4p`-`Ds+5a*kYP0Paj`ESAYqtHbR|RMTOlleMZa%c2EK7hu=kx+I?7!%;2^8x-TM?!c`f6"
    "9QCTwq$;oe(W+D`MXK`bMoOhZhE%1hN%r^bSc+8T*Sc4gB~^I|O$zN<Dn+U?@P-RqEKLKDy8Io4mYPy!Kq~Y10$PlxV%XVJSTB2M"
    "F_(+s+N{^P`?c*zZK58*E*B%UDK@BWPioWEDuIlpI4M={1%OnFG-<14f;pBFq%Mmrt;NY4A`Jvl-m^s}Q(bZ4-goSlPZdKctX+hc"
    "Zri|SCGTl}4HcUY_c@wNuh*UD-MHDq12u->-Hr{YZezqu1?e)jKU+UztlNe|e2ai4J@aLZiYa(OysRxLl3E2)t$4nEQg-{t^khV>"
    "aV{2At&q$U5U@n6I)H6|Hc-$Ed$7*q-n_W`+~w{^t?-yu0TcjyHE?pCNS1`tCGZTM_|GEq<5||#w#ruYefA{Rz<Os=yCpHvotgJ2"
    "zFG>qfIpxnsRtTD{Sq#Dpsm`~-pH3PZ-fLF0e+$5Kbf23tO-tsM3E&V^c=I|Dra#d8XR>NM-F)+qcN<r;na(Jk*{D5gJWeIN0|&^"
    "o5_ef*GUwzx|c7X4U=cXD;7`3FLp{+0LD(Kk<#pxAq$T6L6=m>6i%H)iody%ueq!yq1PgPwQWGQ|LVxssP(!SF<ZXs^i@_$y)%m5"
    "a5q`)3~UG3v@9<c)(PufI6I2U$-}lT*#{br;waM`XdKP7M?phr*#53~;yftO!=qcJCn39N(ov?BS>vKf=9@TiV#LLf41<c67cZA+"
    "va75lYG(WM$N<R-z|iK|a9cDdnVz=Gp$&+#IWC^1BZ}9sPP;U%3d4Z_CRmD|5U-b+s>N9kI$xnWwY<4$L(*B`u^1xH@L()Er*QZ6"
    "iGf#^Ojr=T?pYXh4>rh)vvdzC&kSA^7|Gmbl$_wj=dIYw)Rsd$9!9lY8$7LrtII=nj=Y1o4e2W?4U)%j+o<?W_Qe(qkwRxAkA~o$"
    "Ek$zP>{N8e@#N7?<$MElJjc={&<cXz84nT}Kr850&4d^iU*Czio)a0)dMT2e>h)Zrt|$TnMY^w9&HjZV&&vK>yGGqi`H#3kmj21S"
    "*qG-}#nhG|fLMT=YSZh)V<xy3oOQg`i~x5f2i6!i(~-+z3x1sJ;pO}5kh+1LY0C!6vjJ@oO416rJFoN$uo|1-5HDY2o!8j8PQEQj"
    "DF@`h5a>x}JRgF&(R_pqDCe9H!J&sVo;xDcd8LDpZM;en=|aj@I%JX=URh-T-!Nyqvib^7ojyX#kqi+r6<LxY0T}0n{B_u+-e~Au"
    "S#xtn59EkQmxZ%2idD^(HS;pnT@XmH6c`<D0`qc>!lZ6M2R}S#_<$DhE-5ztTHV}c;|;}=Fpp0!w;`p7K`E;QM_U3RDH%$Fw+Hd^"
    "RS~Hz&PJ;uxf&(PknzbYc4HUtVPDt{woly<L*|eIT8E^Z`b3_&8(x_?olHzh^|WFd`p~d4IC=CTI%G&sA}RJ>7N!ASBwrwBt4_p)"
    "gy1ukhGn4EKk*BulvXs%T}ZmzZJyVrwK)Ibyg>~}*|9C==BV=)KJX;Gv?oB|(y_yor)^i^=T#czL1fr6pGl5Lr#8&Rghi4YbasHi"
    ";7RToX<JmVSUkOS1h`MP6Ld9EqVZIEM0o-|y%mW$HIQsTK=Y5JBH0^Y8>EUzc8T$KB`c&<5yvjAe4LmxX9~YI&xV~|rIgpq|5Eky"
    "Wl9y(jcs-_8T?6(`vXX&4c@jcY+E-cQpOp&+Z<dHq-XlE*%ad0JqaCr6-{X*G*sQqXo(EeLy2iZJF9KUMU-#83`sFj)=(Vf8rs&2"
    "K1Omb%y?1(2`F$+9HL7jjF7CGA{o(n_mSu@3p~4Or#gNFQaRJ{BakUwOXWu(L#~$Ak3a?#nbwcMe-?d_TYhF5aIHP^8k3sSc_tA#"
    "GURb7&n)x&RBqCVn>2^kaxD|gOpnI`&P-#}mRiWxsO`V%)~GF$qYE`^%iyj;c{ikzF-LtprItg(kEY=YSk!Apq7@Uv>nI_5DORP%"
    "8JFh$^2AA&OPb`EgK0CwV>_cxIhb}Ys~Y3dZhJV*G*vFRm^XX7C(6D9D?!Ha#YV8kGJ(~U>iN7qQOW>U)1ps5wy4Iw<SA5R88B!1"
    "@e`gjKsA=ywW!8CQAVi7o`g`1=YxLYawK$6ug#5cx}~A8e&LBVW#N*+|K{l@xZ$P;7~PxNkj>`A)EWV!sSRE_{i!ul*HfE^B4ISO"
    "1|Qywc&en@B}rw5Pjj9`L!NI@B0mLfdgIPSX>oF*;<?_PsHmy;CMu#v;EBo|Gj5Q8K^h$Qv#6&|)RZU6>IUdAH)=O8nS*??=8-S%"
    "A%RZM0GzhGi6;8T<zq_S;r8h}wQBD%zqq)4myb&f2#m=U8QQubNHA9w(&m&K_6tT}ISq41i)drC`uqEg?~%UJ6j>Acfgpx}{bx*4"
    "#bWY&nQmnpU6ZEEN}3meV^Z}PBT5LZv}${dIq;|IOxz`{$;K$x-X+zl=ZG#lPQERzVcqkH<Yn=tMsS#(WC!p((i-=)R0#gAs!j<4"
    "3w$I9Y&1=G1c3$Ur$g{pU_O$V!3k{>1p6nio6PG*ub5=A;=U_qw_49`HK)X*;*{pKIjo(^S|BTMmEM$sV52Dop$1b5!Zzo7)FnZ("
    "(Ub<KvTaJ2Ckv3|U?M@9LFAhRoT-o+21DkaCK8P&60-6hIDhiqOs|bVGaR4<>=IChgXc>jh?->)HLP6F!H~C}Ejf$KIe+#mzdm_#"
    "Wu9E4n<kS414D=T0g)^k=CXfcqb3>pz*_2;vfbnXkWujk6BxIA&qk1tU0z(XKTuB?C=zH3O&^>1!XXfcgFatMLS&>!UT!_f6CBp)"
    "MbC{>kxD06@4}w^*ShsnWK(<$IMKc4JJG%72j{fTHQ&kZHQ&imzImCF4Q)BHSn(W_A>EK7NXW>qA^4}YNfiN?(BfGMp5+ObROt*n"
    "Ay=6Ucr7PndT{s}$n=!Drz6uHn87jWz>Q>ja11Ll{QzfW=xjd>NG-MBkP0Ze2OT0sv@&XQ!BLFq!E3k*Ieg0Io6g!-h<#Ozv%%)@"
    "B++^EN?Er<j6rP*@?ULh@9|%uwf88NHY>6BC>HlBwfFe1ii!ahat+y0{_!e>Ud)<1Bm1;s(o{uurASKV%oMAN>`Re6Fr~=(jvizc"
    "Q$T2d7F;*BhC<O*o6vMC<<Ki_!j|fr89Az$TrJ~EY5t8nYEcZVL-vx!BwMUehu!X+>}gUSab{gLBTKWE@o5$nnVU(=xr^@_XB5R8"
    "Zx$;5%<0j5I;h&5>NYtWtuklzDj(V(cUC#m_-K`bN0_P4@l3;z-xpdeE=E=tPcnmpR&mkX4hDG+6_=-O2a2oF?LZ|LvGycU$wRC?"
    "Nz{fe(`;jcDdSiBtm1h|;yEDEbg`9l|BOU7jtecTal>V`e7LOksj2FGQ8>A*L!+)IxzVz=M%~=Gp;1?HY}DmU&F58lBQ}K+jQ3-N"
    "ab^%-3XaDJE5YR;M%a@~x$0bqGlUR>w2GdjFV2`D_fp4+EcZa#%lDwlzyxSz6pWxom7qZ8C^w%H+BBr3F$wLS5Amr)4D29DcQboM"
    "U#<RQp$eW?=CY@|7^0x6I>8bGPgR2EtR~av<V)r#9_M9_1d<0b+P8Wy*PaHKo}${FYRjRnWSzSPahMcpG(}R_7fg|iN_CHoWQ_U0"
    "=th$j5-OesMFE$jLeoGItH?AE0MjQ=LjtqvO+zPws*o<vCsvKNlC%|{psgff%qQ?7K5-+AFi+A)GlMDV=+if+0!gL!oD0sPSD{C<"
    "s5k{k(P+0NKdIg<DxqF5i(VqNvlws4O13~{d4i<A^oj4MVK_mGPLRSAq{kDaUo=75jo3^XF#_LLDy7%GprlF&J^dIp6+ERbEh`m>"
    ";Tl!obP9<A<%Y6SxtGXF&Dt=J#KbyAC_FA7*QbnxVx}}RBi`1`kzY*d7ZD{ZhQ1U3KTo1oZ9yV3m5zJXSGXq?#yf20o~hsos*vjH"
    "!n~uUsLeFFx3d459#iJ3fUI+Aw$hbCi`Yt6sWwnTXHSC>TWP~z!dAu%((icE$!v>CTQj;bY3nXOi^IgBUZf2Zhbry#a28*ZI8+4>"
    "qk$r0YJ_h@;{4J_aGe7SO^~Uu{0(9=L&5y<1R2R*GC^{b<w*s<CB$YzblA)&Jz}%qW^`#bGny)+a<ljvy*(;$v764>yi9p(lrh7b"
    "oiTI=SiFjMc(XJ1B{w@`q4Au`^8ljAb1n|%tn-lKhI}JHbY5M|>v=Y!AJnGvVv;GFjf-V})(-CCleV&qJkBk|43#=!nH%x4jj8Xb"
    "OO~=R>s^c7u7Zoyg%43HhBg^n1qE3oVXYh`m-8fZB(2$Dzwwk+FA+7tFRGTsr9y``>%z{<1Ifr75^IfSOq=nH89tmb^Ae@r#sGw_"
    "=5B3fwD*M5EQ)M9oL87-S!RI^z$F#UujS^K#XII^V6<r*yZEMYX2b%(_)uO0Gb4Eo>?PJp;KZd4ct;!o^`*owV1NUMFEmw<09n@N"
    "xq!o2_hiCa_pOX?u@F_0O6Y=wi*JSGo7V4@GQD0Y6!Xc2IqxYZ(kTY|32bBd=oAB^kd(dDipEUbd3`R!o0gw|JXay}SnZtR53vo^"
    "Cg$mkfi4Oh>o_neaJ&;q0*R)YeC;k#D73g%tV$fBf-735cj-^M!1Gv?D~!%GZLw0H6CL_de98&F1(}wo_bC%)gR?hhQsnT}zni=?"
    "I^hWHEk|euD!Fta%!T!b5kNb4NxIQ(!$pVcWa7Y4|DL29Ex(ZPGp2M;%wLH-gIu)Pm3Gk$(P`C34N?i3Y&Ai?uvJ$_z&W&ugI8MZ"
    "Qd>y2k9wk9l{N(lEtkS4b}yeMOJAlHVrJ_aciT(?ftN?RC$}qHY8O-!Z19*X@5JdT2R$CmKXDx%^}J7b)KyV;Ax+f@-%_1i*gDPw"
    "dPPsGyQxFgu&R|1Wp*-dUMJVFHf~-s(MqI3vVAnPxK5f$K9B~UM6cKu{|Yv25U!+pZZhf+gc?J}b#gK*H^?m}bV~hD&<KG{N{DD@"
    ">4#Pw1iQyHU~N18bdN}`YG!!l58^iHxj7Xvt(#W<xn+%;79>iI7FT{^yHSO>MGze)zu50QG~#87tA~z{R{oJ|vUlfSInx*fCIo<~"
    "z3S2!1PVzZw$jhfasEG7D|lQ_&RJs_NqyuTY0+FyFKS2RcEoXvME{4QrX`JE299y|JbAOhbM4>-9peW`9a9vh-z3w=j;w}1Mo;t}"
    "?KiGn_2dxE^tm!)@cO;7`?k$8P<o&HV_kzRiKu|PW8fv-5lill8{SuR@U|+e_R4k|$En`9MNIrY7`NaWk9+?T_LeDlK?}hN!zw`-"
    "HlzUChW^T?u=k@Mx>6m66^cEBVMG2eJW-PHtI+m*{3;CXz3y!{VOekC3iX`*0oecq<yish7bU0=%E(RU=tTf+qD^6!2OTnVAy$2n"
    "#Fts(r!-xgCpXeqBtK_ELUaJ0A<^_8{8~#f%C_f8&j7j6GWr1bf&)BFr4X)s;;$(w;%y;%r6z8Znl)ajGx18*Qrkh|Gc8R6bCc^e"
    "s@4ti1Q^?RrRM4^0yOhW@sjo7DzA^FaO5J%tlSM4WtsG(=x)3_3!8u&uD9buE^)G2Ks8!G=T0r4VrH~}Dx$J?7Ep0HSU?qn(|QY-"
    "^KK=biu0E&pp9{yI;7<?*k6$zI;w+xmIo~5Xl<1=+tvM*Vl5=@8Z2!>Z0ap-Kx}&YE)O}mo>AJI%G;y^%u&Tz(B~}GaagZ8tK+bq"
    "XP|Xh&-D_Ab;4O4hxJ??aah;pMWP|$LFg5i=*il;=6u9W!TaV3dPpuU(p}n@UN-$PHzQzxXR4d*RQgDEDjgtzo-sN_!)X?R`K?2S"
    "sO^^IxBd&}-I_G*8s$8G?dA(eJ||dRo1x7>TRbeYUtXlLE~zWF^)N^3O~_bPUbxl%CFTi#S4~Yt@0q^eoz_mDZL!R=_DFJ>8Qo|N"
    "-?9h3cHs?oM8yWxxf>Z_dMbaWN_oD!k&)D&7w9n+Tx8C5H!_-D3)l2t_3a{fzC8VI6f%5`??wSQ=WKTo1GM*3?`{-aNyc|0<IdP0"
    "%PO9w+txCC4}0BavYcKEU2o`CRJnNR*sVC@z0g*-?0vUGij6d^;LK6?75y+B8t3V%MlZgvm7n%xyuU93&k%gp4o~fXibGHBkg)9u"
    "Hh$~G00-5R)UY{c>*m~3pm=ovu6eq^06rXWa9N-|0MYt=<$8oU+v`DaBS0+js;vqUG^)V|)d|d|eeu=FUw}TJ+$NG~5ODI3Tt5Yr"
    "2EApX@|U6MoH=F#e#4Xos%b2ZJj|Q!A5yg$LR_;(u=t=5P-zCZ1RAVp;WE%;1XL+_4@#^t6qzj&rg>aS%k-H?FLfF{oD>8Jtp+=+"
    "m0miImq?y_iDc?zgz?BY(QDxGoO`fh#@xPNr+BqJMPC#R5xI3!5kpL7p&_qW%h<UmH|Z&kk*xw7SgLk3YlG*gZA^}>a2xlZvTN8n"
    "ute(Epdzcf&h^YC3XWYjhjR}%KmND~6N2QP<Mt_%H>81kN-_DgVlhPU7)u9m91;S$ft`4o8J+eay;^-jO!UvZ&ARPm0-iR69<L4%"
    "Si3#V>!Cx|v*!0);R@Vp<?to$Pzlt8VeA<;7Jt)`U6F4XH-jg2Pl~QApY9@*Rs1N#u)NU3kzsRU@g$lOBf;#xQJX4eShQ%7bEJ^W"
    "05RUM=x<YY%^EwKX$ohLS~pvI_bt<+#-mrRfp(fxcW5vwN<C^4@C(_*QzlU?BZt~b2x{x~*}~CHY~Fu*w_hIK{<h&1`QPUdhsV2r"
    "6hqxsI}A@j6HsA>r=Vfh;WgRt+6{}bY1nD&@xz7)QKl*;3nQVTt0XUL6hpxC(&84}h-Dpx!p+sjOnkB9yz+IWN3bUwd;~B0sWZNd"
    "XREIOM#d?_lPi6DsCtq{htokmwb_&p&HvsGPD>MVg>_F$!=uHzcUl@Qup+iRne&pzx#83!2VsVLk{um`hDVgO&M|00zOmYeJ~0!Q"
    "y7pEp6hOzIou51om&Z||&7f1m1h^S;_W3XR38$6eF*5zgX=S*nknVK)EII&qhLhC6>#ZrncN!jnP%D@_lQ3T@m^%~jURszt6MPX`"
    "FHsX9VEQn3CZz|Xhzoh*fOVWpGYf$1ye;N^0;b6Wk{e7pzt`6d7megc9PZ4oe$5ZRRhOZ^tpDKf!~L|o`|iW-^xgdK_VMxd{{7px"
    "KYssTcYprd&AY$9dwVn8{pqjY|McC>+qe6lT=*0&+B)+LcC}0XT%Yj>og26~nv~cp%T;`W2pT$z=Q^bI+8*t`=-7knMUy&OCld6M"
    "SjT*UhQP^u;W1E`z&&0BNz#Cl^^vxp*&(s6P`q*H%s(w&zWc1yeOoHe5<w{U)l5*7U-*oVAhs&LkR?GcOdD2{<cTmD(yd7I&WMd|"
    "6QW1yB`iZ4TyQ!idbSa^bqGxoF8G*KUgLQi0gn5C<@z%`=Lv>Wkjo~xusp%bKQBehg`Qo#u@)#9Z(fQD>8sh3lJk>c1G(3NHz*`r"
    "Z7;V*(rl+Iu6WXVC4GooNlBHEl6cD_2Yye&!EhY-l_x4qQOt4DhL;(s`1TI-WtUNPGU>(RL2BNldP~wGAo<uPV@m#=K~cUtv0Qy{"
    "BE5y0DxDguB7u#xEhun|!Z9+%81w^BQM`@`SU*KEhiQNH;qLcov{1WyPuZGLHX4vyG}q-0CtDARL?8|l`_G7=X+i^xQSYf(&j)vX"
    "7EjS4MltrZl;S4&A5n)|NTe+%7<U$~zhMoe;c(rRyNnJgakvsF@;||Ra`6W==9s1x`P%1S$_zsL52OO+o3oP0$u<SyUUxpGyu3<w"
    "=fm}vSdYLPO~@IC&ektFCL@L{dsu=~4Bw+M(WH<&B*m0P@BLp=HmUIZ_+%TXazlqAlXAgzqMM9zG*=S7;f6GCP2`gaphyjRw*RVH"
    "^lYP}C5obF`>)WVXB*8a(zZ@tMP;7Q@hQGLP%RkVx}w>-8t?5jN-=HltaEG0I+>^QuVuRvAW@K4;ulp;G(~+Wh^;t<w$Z9hjGP9d"
    "07V*p*^y{g-*J)_OMskm9!G(!?OFp~X2|I(%PJe$*kyCwG5$HL!Seae!>RX{k0MPx4Fz(4**V6Kx!WXd>;Swu3nM*AOAV%*^3<dx"
    "b|edUqB!w&2w3f~JL4B!2Xit+)fa(gsfcVdTy{j)l!-K9+4LFH+*hKgh2(xc#bj6P0m#A27&$`N@Fa!B*cTm>G(Akb=uKg~R)}=|"
    "FWXVoYRS55oG@Cq51#pLEQw%)9|RM-;s{b>3=Y!xvLiQ+<h!2mp>Lw9n624_%d9@(c(v-B>CiPW$kSj9z(^Z4j(;uIE8{G3()yBu"
    "JD`Epo(^d$gVU!*GF^Ou`4Xv@UUfYo)2-+}klE;UM~r`jCvBbeNu|%wdnL1y^<K%W6unon;91&vC9{$Ov}<%xu<{5(dw_yL;r+W#"
    "G9xZ-{^N%~|ND18+}!+l!#VrwvYY>}+xPSRKh<>q!7ok*nK^+mgPaCzjEXpBd=5^o8k_H{OjN!=H!}YNdL6KaCLbcRVmir(Oi1b2"
    "UZ1S#Bp))?c9IX7fHBrypR84#>yx#WXOsV8hu0?y?Sn(^HuRD*C!N_+r2Bb8g!Lpj@+Ki*UMs1(ixEh#_34DJPk{B>RCO_%9xRIb"
    "-?tC%!u$ANckh2*9^t|BR@nJ(-zAGP#ME&ei!)#Y*3Mj%Z<8yUZ&M#vxPe}AH-+6LG6`G_Nd;3LC<CHO3z%?<lJyZ}-zZes{Ss?J"
    "$Anauj4TMx34k*|oB$qB3M5Y=$T`Tv2;x48x9@8$lodn=a;v4Es6b$;<yhe!yJnb48wU{e6Kn(si-1y|ZU$H{p5*YgcFic6YmJvK"
    "`fi;aR=@%N9ac>o-Gg)3q!MpJ$69BG@>^HJ<ys<_xZ?HkQ{mm8fU!1PIp5~M3G^0pr3H6_N<hxhf$St3-u9hD$&aqqTa46|)bEvz"
    "^0P+5>nb|NYAc(t^P0m(q9896rfsPrt~R8~-yLavPP>MI(<byPAm%goCJnW)S(GaH5hqt_S!*jKtRF4KC<!LMBsm~E$FpyBygBLy"
    "g#A7pb_2TB^kVGp4V5s>qN`%Hae5~k;!Em-TA-P-jKS+qYRh<Q_KRm<Tx%OrI1Ua^9t#Nhl+YlEg{AB(2A-k^R<n3WTc%n&G&-d{"
    "T~ps(qS#oLykxE@Ff2=nX3*PJn!)|&)GNcTF2`&D+p^nCE?U|OjM3JqA1mDB11@Q=Kd&+GV<+&zCih|Vj+pt_v2D<+9v(){4{_wF"
    "h^><BR;v|!gsGYk&#XjTMd|JPU++HroQ^Y*Ne;8F+;}@}c8*g$ZD;nj$v7vv4bnm^7ow5Vh19Vr1%DZ|zj@EmK0FX@C$Z(!(SCid"
    "&rL`Y%e5jw=b9yP1?Lj|N{NvkVuPz}xgqQihf6Y)um6v!(Nkd}mKPuX62rAxgR{U6zPsBJ&3DCb4Oan!RECxtF*vw9Nh5RS{=hCf"
    "BWaIuL%bGwo#w#u@nejqsjCYG4sFhvBosJYUt6>sT>s9I=g7$<kUEYHHh3}(q={hqXvKo%jM^EVFzaVoj*0H8M*eyAs)5&4aCiNQ"
    "6ha^8L?PU`$5LFK6NQ8kCkn;CzyvCC$>&>=0V_0Xd1Z|nE4-p}T-iv65ma=o_wHQ1(Mac>FFIP6M;o(nC2RH0=!;IV&W)Opr-%*S"
    "!x;M-lq>31=2ED_)NSzMJ#Of>!kLbt+X@GRE1i{04r1tS@aS!=-~MwiM#O*a#fVtRdodzb@?MOH|GWyoa@Cus&CqM5$m$w0Bri&G"
    "q^~8^xaq^E+d0phtl_vx(p)R$=7{7cs>6_SzI~kTe_bAKcGHL3>J8(sKmK%M-YxI$AAaNVFTecuc<ZlU;o)PAmY);6nU!^_ykfvB"
    "E1}GAC8D<o9hGM3B0(y&s6vfEKrT2k(}E)B#W$)qXh40W*`&#!Bgh>cw52eO!9O4U0B~H}>VB2<P8q%RALe(D52daMx?LvFlzXQH"
    "gm`<wiF1q~0Q~;(_O2u>_Egmxj`qlK<V)C*;mE3pB)J-nE;j<jOl>5Ot`cc$DbCx6jt_~XYX7M%{4$mhG}eG0P{o3<_U_E%%crE0"
    "G&*2igBj}?O6msoyO7*f`lu*YJ9g0W#8I+#o04#T&e!6(I7?U+bJ@4p=~ih|J=H~<3rXXinl}7I8h2l0c=t(;qa=-cs@Ia|{o7(k"
    "QdM#<K(!Hk{hWQ~TuZUbD*+UnT|gC)=u5zGIpW)1UXC@;HAhf;qHMS<SLqPik=X6eJG3PsRoK-V^{KB*R!7M2Bd@}Cb0IC91OrYA"
    "&ZH+eDZ%{pI7z3l|CW<<G)7=fN_Iu9#E6x2Jf$-$nKRFKo^Az6!!FizPAt9JZ$zj(FD1hTjKT$?Rb7%QtiUDqA6EDXQU_rBm_L}-"
    "5~L2G7_}P7Xq{YYlKh(v=aqjck&bW1j`oyxZY1K&bAT_b8312c!)tk{M_e3y?oM#A5kq-s<VYT-%#^J>40$OBOl%a9htqkPI3o-D"
    "W~e|k&GBifY!&GEG#DFA?9P0AF8TOO`7e9yV+;|=ZZ60WHaOKigMI8tacH0xhh}uJ2LHBGjO2#mFr<+jFp_J;VN}F|8`yx6EW^@p"
    "VP|Hf6es1IA(57D>$K&(4Uf+x-DCjD6sU#gjOCt<pqM3Od8cH3JFoIXqDKYWL6vQCR>fl`I8Sj=8&Ve16%BP-s~z%Eu)#5^Iw)o="
    "po44E6C!`pLidw_9l8!DHh3e6+G3bF&^l2k$0|S5O`Ko(5p;4AB_c3I^xTw2CFUeba}ShHP^J|NoJ8b0Oi=^$TN^O^u5b~Ah<`$I"
    "dgT!bTced^O3aP2+R-l9HE9~qu+jkpByqtWs5YZk+JqG}VD#sW`yyilCc$LXc?Hv=Qs-hCq+(`%#Pg%=73@l2WG4|*+G}8_-G1F{"
    "h32lp+y1%+=$?<f3Gym}Y_&{-g&0(KBROx$?rp&Ss~w!M|A!4;S5OzwxWtO5*T`XRNEu#fDt6O!oxq8;4tzT6RC?9<kEt2ex#_1f"
    "&55BN<D#TErhYhC>#;VPW3c*>YEvimSf_@1tkbO?n<<UkezGh(Jyc|!!Q1?BX8l8C{lisuOrg+x_<aPGQx4adeVykOyakxrp7Ntf"
    "JwW;45}MU6H_nZqQ$5KvUcq@GoEv~wKtTShohIXmJW2Pq14Gb)zyfe%r_6-QgfuN}8BXf)+|(;W>Peoh6^@}G_4pO)ZDCT6C63T@"
    "<>%~`2aZD$cj|I)Q-4ein!e|gr@-aU4qyczGVglMca`fsa3-2Ut`tfv6Vk`Isu04foKqp!B<;(;7qZRumpdSAKb{8y09@TQXu1}!"
    "!89=+M3NGtnw9Q`TY3Ue8(&~Tlok_sytZy$QuBm~aCxgdaHIOJ>rr3;H?F?BOsRhqbOg%_ZuPNHU*Pmb6H++ze)GojMQn46OYJ(="
    "IFFLboj&GV3du9#dOKIdr_s*N73>OHABf6DvvPa{LBYpY->|3|Lr76~Box`xP2=1ik0}UF6?BbP_Q$w2AmWAL{ql2iEJ$Bnz4U2I"
    "2)_p%#o>e!N*`guP_7*i8pooB2eZu@2f;7l@+vI^sItC#<4I}|Dhnb)E2hpdDbCtCxfi)}WQ`_nQC98L6Km?N3S}9SBoH7+3kIg~"
    "9LW`fBl5UjOPV(c1b)A)*D|ESL(?_8vrd=NF>kVOW@IS?IgGe~<m-?-XZU&7a^b0SoTn%LjEm_7-(k&xo#^H&bHu6l$fo>)6jj<p"
    "wJmReN5e|(u6ExBDNW<Lj~^f)I8D^yJLwP$nfvM&k{v!Xq;3KdB&FNt1!YefH_eGh4jp+SZUJOGGSjJ)Umb}veq0Fo^YZcSyT7N|"
    "hLKM@B>Hiuc#w__Jd0hT>!XgvAx}^re#KKHI^5>--g9Ri@43E}(W5me-U;@=a~^W;S?ck>Cv-6gHh}C>aM`mXcog8psV{n<q&cd*"
    "DZeF-@2c?T-&|IcSXa6Y`<pYVd!r+JN>zso+w*d`BppH7t}TV^tndupD}$TT0UE6>GvRtx(4zKYIFWjUY<4Nx##+F2bw@plckz^K"
    "u%K2W1u*UZ@WkDhK#9Zrct#skKPL(m!Xx!FO4~J+$NM$(I(?yLt8Yv6CpK9@K-Vb-q~wO5ZkVNR(AQ8M!<+a(-OyD|M}<jP-QZ{L"
    "oX(vKne3|T^lqum0fxDz&|KfSLmIo$b>0X*vH}<}K<)q|plNk#T9sz>bJ=$K(EME4)=-dX@!Emy0fnMkg8+Wx217xz*3e#ZW*O63"
    "umvqp<33=cLV8`kuu;KKwS?F4N?@p7(w=O_wfYj#_CnG+bh;Q~LWl|oK_uy%jtQ28=m$jWvs?^}rC=!<Ia+<o;ix8P;~8_kBP0Qk"
    "bdC_4UIi~J#;i0)byQ1_7}*>#Hl|GJxK?<Q8>y%9^syyAc@z3UzPKp!)2^@>7YU_paarP9Bd;Oxt#OUSk9xSR;wgikR!G=ZAkJ(n"
    "(AidCtvkM_E1(iU8;#oX)>Aj{qs~6pWV<-M-Mr9a$tKc(20Dkk8+JQ`>YX3Op#yL}x~u{}aoq&L8$ql|yMjc?mgj|y?E<<-B`S#g"
    "0SOHjy&-*2f;3@S(}Z$O6+|3?#^OjEI__QSJI^%w;~MszCC~RKM9<Sxe*H0Z0|r7M3JEas_&pTNNXmgFhmoqUxM0ayq#GIHIp_*v"
    "GC+t_2U=q<1=lzd<#l$3MB&D)2`N%H?KQ_(ZE-W$;x<u>n`1DxxH-<RArKw6BNaHnjSQ@(;q4nq#Ob{L97d_sInnrYruUsJM4YUV"
    "%uOzlyDH5{!F4e~P**Q@N)5Evl&=nFqOUupM-N#}>-u58{;gp{wbvOnP<sQMhbBu^DYXtK4!<BbSr{B)c>+KVw7P%`g7+6R;ELd)"
    "i(Bua>tgQN7*gm@=>2&aa<@<8D|u|UETPEH&eJ>j9#@hJ7#pG(>SJitE|X*vSzdmHZOT%JGmk5(9xfr3Ae<!BJ1(084l58YI3HY|"
    "w;W4qeKEiD<S+oK8v?G<4XFljEP2T!j&+V+)bm{=DRGr9s?jctRzVkBILIwo=R7M9dC{Y{+-Cmpe7F%ahUsNTVcKMkxdTy}5u2(%"
    "i|0gyBl$QEfT{ud+9VXFnWI(!$6_vB<R`c77$>nbUNzh5w^#5dah$0}qEcuP#~BRbJssyn*skN-XHtW+vHCftGt7mIh_w{V4RY6a"
    "ICBXk1?P|{U1<$bxhDch%q7YP=|a*$BszQ9++Q)vmP4B5=z3n9I`_DH(p+Pml^B?M^3*CjNI&PeX4mLpm7_O0>?MvcyuEkFD~HRt"
    "Dr@i5nGbcF4s}OxRMG*5Z;5VAtoT&BxZ^Rpu?^Ss6g5CbbjcZ~Km^?)QjAOP1m$=V!k86`FXx>gx1<Sjt!n0b$PtSP#zulfFo8*H"
    "e$ylk1bfDVgA4fy$%BIvCDC!Ej-~k#+>O*RA!Hu_&n1tWo*+svCRhQ_Bavb#h=fGwKti3_E7m5jSQnBQ)>>rR<snb*<#)MIrpW@9"
    "Ho4H`4V!aJk_E+7$mPtFV{+d#L8y^6q_HpHn$9OFBn(l{xxyr~MSV!n=j}Yxsq<D0H<u;asKHj7IhAPbQ`isJRlY?L946HcEmkp+"
    "jKUGivaVmhT|huVHkbXpMiSsBYA306(cd<x9ncpb_I@t~sFBV|3aZM3UycP*pm{M+gf2$@d(l_cNkJ-DgL5tEf@~bLBC>)DUNy&I"
    "Vq9>ZId*II1xVy9*YlQr)k!TH55fF9J%U5<B!`cV{drjzWMbWbM$$J8=6;wF%!*4n`O2}g`;5SblNgtFnE%Psj-L+F4o?ROqtijc"
    "@N`It@$l&ogL_=cjMqIKg8vUX9nKtB3n{SHNk=S1>n0+*OfhkVGeXgHF7=C{3)%D9n_Y}8@<caC?(38gO&DW3npG!d=#+m2ZB#yf"
    "VsJ{5z<w`O>o^9dsOuZ7C5UiPeutj$<#DPXF|jB044ipLJ$+{$?5N{bXP)DZI!^QJMql^_&FC2_oh4c*Qeu1VDTiGEo`CLiO_t<Z"
    "wa;OaOpc<t($*Cxw|A{c73+cvQiUG4qkGB~+|gag^L5H|#Dz><r#we|Avdy+I}LJRSa%u*F(OVocG7di=?Ki;`FYPLruH0hhPjam"
    "-6iOV)`ac?cEnN75oZJ&`+az-xq?wF08jL>o|6DI(vAe7QS9|_)Xu08a|e%|%QLspCv-JaJ#^NujV?I&^q&ztNe_&>S;830o^fS0"
    "&q-$K%s82)Gw}|Nm6`qL#<$K{##-MxMOv{8zug&jUd_)z()<DzMgL*ZS<VK&b)JMfr_X#Hbon}Hxk+0Y9g^f`6Os{K!BlTWd$*ze"
    "kn;H5z)Be8-gZ{C>0S$IgZ&ih%%g)cIz4hcN+QW>(`a;Qmj;ia!Ob=*)t1K9p`$*J(U2M}+RP#runHRmko!ow|5^(pJOO8cUqRXh"
    "$DV<#vfu{M7%sqlV0)|Et{XPuGd(PUCmuiEKmIO5GyZD?{7a?Wakq9qV0%=N2QEf#@1AA{Ztsrd`RQb;bs+S0^-_pw#5(64$ZOn~"
    "f{W6z)JP80@HhjdpWu+~MK(L(knP|qv3w4Ov3xG1NE#d($ulXRX!gt}+9922!OiKUS`8LXtJT31$&J+5tj9p~K=0|-;KpjXV{)K8"
    "2V9Mly0?q)JDvD!mr@h;Y8Jd3pY0Mx#xOqHIRUjlNQ9Yi!Lw(qZM&3J{<7M(zy4$ErER0Aozv|25x2Sg^aZ6eY-FBrM)o7LJ;fXi"
    "c5}}1+GUf7QD@C{#c0S2)EA=;<Q2qd$Su?tqiG$TIvU640(eKy&pA9wZTmj}=c>lj+2wM%$Td7wd^>S36KNWir$B?wvuh>_gySMC"
    "J1<t`4i344LLGPD^+hD_W6cGU8o(n2+Q=c=)36DM_#_9KJ{q6qOK3K<Q|0N?tyeLSI?M^L;!wmj8<^ICmDkh=r#-ds6*wOIe!%Do"
    "<8lEw8sX+kxIvI!AYCC!k2B6%cc08qoHcSf^C4%Z;nBJLY^1<@8gGCE7qa|ZFk+YvuVx2EOTf`H!k3WPGhMRIZ5#e}|Ka}b{^#HH"
    "huy>D)0yP&dD`Tv4sA|*p%?R>c0-w~te_Sn^tC{|4i{l?{&0fmO&1DOHOi6_i1sRn2Dh@w<$^E8p#(x1P6%;yL4hAVOG62BoxwQr"
    "9x%7ES}-Ec7bJURE<t?cg5Fz>3&B|f+U&?&2nuexdS>s)J`MgRb=qsn7ecmseMeiVz=aR^*U9O0ciE{H7$bW_a7FS?XyOaNIo762"
    "Z>h5dvd{<Gb+|^@N>WJ74i@>OfjO_s)qYt@AJ8UCR%|Xe>y|G8{5rD%mfA}9Z%S^7RKm$CWHt%yxDMiCK81rHi6YlqSLJpMWo%Vu"
    "SIXogTk<v{y8NE&_Ts($5WoMU{BWKmMAa^|?Fv(s*_Se9j4|PEw+SiRi~IIF{2({sb44m@jMs#wuEJs=c~0Mi6=-6B8XstyXz~(I"
    "m0>5;pMWS+Bau!-G>7~)*bHjx+q*9U1OQ}WwQ?(gm{O5k%;#xJ97EEwWTsGzwS6R`2p$!v{vE3x2z&`{TEtbLmBgp@QVFz`NYPf}"
    "$ZUBX5Le<lmC!s25nI;Mp3qDR@!mt5!FK=Fv=IupPFHCwmY@x-9%Gyy%L<608TiWl^>Zl;-2At2e|j{26WktttG2*j)_-vL;ojHu"
    "-G|%hyZPPi<Kyl9`?qg@{Qkf0{`|L_cYlBP_GY^K(_g>;>ARb^Z}&gB@F{H#<=E)vqnx;g&Z-<7vz&0InLMHHX$HgntvRdhDh`Ey"
    "aW&_1njXq(zmoTv4BN4MxycB5Qu+q!KvOOLwazpgLhjgk)rJX{(myv;R<-1fqb1!rDLD(dk(Lq2HXJAGL|WnKJEzVY4mwRLk4~-j"
    "qHXpQ0)Fm>Ua^q36jcQxzZ5`mH@oS)?*xm|xtoR>rUVk`+St}0kZG3SX3Cx~pjtkESf-E5d~>+l{rp(<Fn1sZTyLPz88}kn=pSDW"
    "i0ygz8L12!<oGhGBUEnMZTh_S!D-I+K@Cu=JEeP$x4wXRSWY!=%k=2i(U@Cin)h5`kZjk>`;QM^w5NU<HZm6H?j;|jK@gh5_p{`Z"
    ")B!dOG(6Apyi#r2XQ^glVud4+<i1RlZp8;#%~(1cFW>Oa#F-*JwX)QP-<AU)cr1n7llLD`>dEjK$mdd3%xjrG$CrHnS#k1N=FgIR"
    "R{66gpLPCR<@gMrP9^#DWjZR0Ana!P&YhA7U(@&Ql(Z&*<5{A75oeC4iQ>%CETci=T=M3zOb_+#l=!8C6XR(dCv{zfId6)Go%v&K"
    "r-n=A8;U~~Y*q|j&H~8{brD-$BfH_<zJTNdm+?T;g8=V9Ya{SVUloQ{b<26<6lVi@;$oO!FUC6%E%CJvGX@yj!WYrJ$>&+do`QJd"
    "!OG7Yr9L~6hY;_3Nzb?x!m4k_u-e(qVKag?s*fTRNPxM3&XOfjP!3P7m52#;?95C6g$XS2-kk4pY<eJJ1M>wZmp%uH_L^t`h7Tjw"
    "Rf&7?{5l$D8cZO?yaKGnDy1)bz|0AYK|nKVZkD^Mh&zg7>q`jxd>mT;v&!?gy=8&4qh~apN+>bb>3}|c#xPjga~v#uIR=3$T3Dhb"
    "21A!$aJ<CE4EYA=dujt!>r2E?x@WJ;5Vfn!Ivjb{0l3btBYAm9&hbD4B3Acj?!!LyA-E>F6KbZTh=72W&~ZJ~J{*UuXdf;{3Le!5"
    "oq!Yipp(bbh58aPBrxBo_vgJ)&obYrof^5tWEI*~7{wY%9H;I0p(Hpq6=|`D`K%*2usM&wnBhgx8AskSp?O4cb`<;?X#LcIyOev6"
    "<NSNRIJCuem1r>CRzi-T&0ezS^1Ox!C-dAmz~kTEkkZcQDeX|n9v}#fBy8lG&|vVM5L_3!HX5DDFnZq$kEPdmZU~QS6v}PoX%W@k"
    "G7d@5&rn!xpv5SKm}_sZ&#Uh)v&bE->~UK#PoTLbeG;+e1#|l=j2yx6do<LD2YXz@@i;l9-y-`>#|@Y1C)z~9J-0DT6)p*A97nb#"
    "I~+(=K-Q76F{llDV0Sq0p|Mz#XA*{2&Y%EbQNYeD3P9#QIO_Cf{VdI!?i6G>iEwY+$-<^@o~e?k4BSW_AH|F~l{5PqK1^ssUG<3v"
    "sG)0!3@&(+!KaK*sL=_;Q?{%eoR3YxJmkxI&Ado`G%&!IQ0&OeDS4flQ;ztBv~P=k4ebDGD$uCjuJ-l4jdP<$uNFLbO=0{AqwI!1"
    "AyXNvsxrH+j7Vjm#iAwG2hJmY;qALmDEBd)aYu4;?G@}xJ4qk$Wh^;#8Tx%nt2Iom8A|8@CRw0aq)|@xyf09PLwbSo8%0zQmyjKr"
    "vKh^nK`@D{sf<Dj`VxY-nQZc=5;P(7ULUr+7kP6DDUZf^hY~b!ZbED$6uyP5w!C8N_Cy+0^Dn;Uc8JlXp=S;BG=Z0C!u&3D>()yy"
    "555G+kYQ%BbK#fW!yMvw%}>k2?e0!}Tt0t%w$CmPZdj!o{}MA@#{rf_Fhr_bb+jAi{ik>P<>Bpbxqd6?63);rp{1EqG;ST#6(#{3"
    "nFMGj!O7Q5f`gF*yFVLv6T&wanz{VolN(gw^7P`qb%N_x3|$H~dLrd@7ArDzaRuhzz<kos_jkAp(!6HiG+*ytuhC(Y@uliy_{ubb"
    "CVr_2C?WJk!ik3WrFjkS2XG%^$ip?$OF2=tq`e0313wBO5K0()vlca;m@g3(ZUVSNPiyJ0?z*4Oo4@OzrZgJGD9i0MYgmrp@`Uqt"
    "LF*AfdFq#+d|oN8j|S}e5)n27DFoOuoexzduCT6Ex-Z_i^Ktd6&8?~gd03z;rG`>1<p{g*;5CVM-%$9sZcxqQxr3+CibSL<W5$EG"
    "{0f7&rqPVI4!mmEAgMrKV_d7<RbRew>rP*O_?kvJ%=^}uquFa_L3242=em>qHqVR}S6F;q-51<JHcO;sH2^XKc?GRQD-w7E&Gyvl"
    "H5#|pV!T4yj#tRAD~#QYY#F5+mRz1E3)@9LAGzAv>it)s8<_^t+7xr`pp(xG!j_*Uq)SOE6jA&lbcQeb_>bTHeqLcSBKkE(&<Lfm"
    "uYv=4X8TGu?3n=O#sad?H}Pq$i!J2Kadyhbizj!p51$@?!H!YfMCaP=yGq{$qu*uzF6eiWzpK@!D}T>ckC17OeE*!ko5tsKqeTpa"
    "Pie&@aya7#!*M2sW4^`r^OT)#LndG)*kUe496@d53KMZu)d8LfrS(69fXNoJ;A1vG5cfolU}j#~4&CJuAUIE0L?Os_r$=nuH3{y2"
    "e}*m?*StcP8MUep4IfCveQJ-N15C;tbdKIprG8ZpSFYI_bFB@0S7<~Lh|b3aLoV~3rP+KZ<O#-;TV8rrnkVt>v6%dFl)U)5GiDR~"
    "z!_%Da#f#MJ33qrO*CmNk!3;v+R}L18qLIt9ISD-31?~(3%++at~NCxGZl{e1N*a79(RrRCE7Y@6}kl>rgmye)a$u7@$NrYf&ZVo"
    "5Bk^L-R=DL*F4cgxn6d}AZa6pZYM^BTLb43AJ(ddrLy?2c7O&|_yCf)OdXLg=tw^Cl6zQ@m(yq5kUN{aw9X!1a)^+*M~_q(0p2F>"
    "AP&*}yZBYJ)vub(nQCZYZ}kUlB&bYkn^U4E$vPe&x@s^I58%tCFyi}PSEEF_#pPP0Xwak!$)E_(gL%QUmj|QZq=w_6A$eaGK?}+Z"
    "P^~>Jxu~U%q@*9u>WGBg5j}pk4cYVtUeY}Hs683<(HFP92a^=riE+9@QSzF_zKvx7D>lK~Y!IR3X)ros!SNd02{MHOZvn2*VdSml"
    "1?$esx;uI@0unDSJufdG(=)2xXM!bt<A^770=>ivyBCNYl|@d<lDEa^H%#g1191#-$R}8W!Rm6Xi^*eCH<xLC{uG)ycT*1IXgy7g"
    "eEvO6^;4DvQk{a2582aE+jf^doq{2Iro4GQ_6#Um6?>M>YZ&sUGZ@Hd*}Z^2RpC!Vk<ljHhv=`8)#p_&Oxq_QagEqILil*LUXR7!"
    "&$oA(fZeNBxc_affREQ0<S<V_pql5%B^RHfldIzfMH}9s8~6AgKZpQ@b%GxR<D(Spfu;xiAXtk<moBS<2|fS{3^WY3zbr4{hm>w5"
    ")J2>h{o=hTD=3)6K^+HUUT`3q+)#Dy?(kq`^dx-!HPlxHTij5sYPj7VPor945cVG%mnspw#>81J7lP?3Gt?&BJxwF2`Pz0y7^{Ki"
    "MpDx+5Fc$2qbi{pZvx#-;;+OfH;FalO%h``yPE{$KxhgEW+XHPbA)%r3pUAA<~BlFZ^;k=ZxV;18(+DGF{2)8XLUO*YsCrZ_3PS7"
    "m|jGpf6gRVd#@*9FM=Ce(yjMPbA$3^)7-8gliYS+UtX{rWi@ybf6*rSs#}-{o^2!>SNKFvV!7>C9<`4or(UC$`>Is`MwR)ON4p(y"
    "YEJLAf-BMZ<E5LJr|C9+zx)pH8a%)MQ|W$0(mi%*6g*nv`mwg2Dv30}mQTT}_;MU-D|i5}Z$fRwn%}Mowe_DxC)8F1ceysy)_*pg"
    "P+R{QI-$10AEQ;Mt>7>cr%m3x8Sm_vYod1(6Fk1VC4PUEZtd&R!;^qJ>|3|&r{}k$(`&s5>GGan&lkbZ?n&juARS>Ksm34-nPiD|"
    "eT4^2W&$q*hAOBCes{Ko?JYk|!LI4tp5e-nl&c1pXWGkxiU)-{8Qvp=f+m(X&sq$TP0G(KzQEu_9-OA|4KuO;3!%4zS2Dq_-%rCz"
    "KVi&EhHb}{WXxT^pUUNa`kUm_FHe5^$Y&LgMw?#dk3bw=nT2p-6i(x5`m0%GXX_i|gtM1q@esToH)zSn+Z8=|zNM2T86Fq=0^`ay"
    "0TJ-zM%*jCE?9{d$)EIAE2Ll*6r3p!n5BB5sxrEiDbpDhvK~%+aF7-a&RzLod>!rJ%z2Wl+Es14N)CUnYLq+M{ygR*pip)jQT21M"
    "2GWt$(5}gjnxwWQMxrk(wxyvtyQ3v3L1D36h8{q-m}WWJ8+L#Fq3rj0DAbE{CR||6ASZC3odl!tmjPAFllbJ9;(>jEvCK@_81wzW"
    "&A4$lz5_^X?3T=Y0l~A&f=98TrB^6M0;Yl#4S!`Kb~^pC%&s^e#iR>WJ$xy2uqBVuuVV}%XOc?7N-L#waG;L<B&n1Xn04Il`aPa^"
    "xyLd;Mj&4&K(0%^M0_S%J}&V+Iek{VKG0P3g4sszD|edtf@JgxzMl2c)#zC>dIS>Z^$~gf&gyJqQR&Gc-@-V)>8r|v9{JJ;Wo3hs"
    "l0{r_cU43#qc?4TxglP1j~|fHFhOEs*a9HGb?gNQ8bUdmrPv@@t(;4&xF@`*nV|9=&x~fKW>g)c-;Q4FG#5SZH~(E7&kPxgbRFb`"
    "?mNi&?_CEuq5BSU{=05tZwn22&T}F_L0ZH-6R{I%X~yYwLKNC&uan%IF)_fJAMTI271d%&=BZE}Z?)Vz&4%H5o+yV$W5~>kJ%JgD"
    "zR7z>Kkufeqngt(TWQ;*Y@A8T#<Z;h3L{Ft6)!#ex*0$Q><g|4j9(f;?$*)6T7X<c-4o~SUb$~+XF8XjJ;wMJhV?E_d+gdN3{xYF"
    "Z%^x7n#vDjFnXH<E0A>OVpO$DAj0X-8;Ee*{yaj2_cGgth)p)ETehJ3d7l}HY(X5(yKqHc4QP%7D`ZGZOMI`xi9GR?8X%XU@RC%P"
    "846K@p*loxdhM9JLz38z$=m22x}-3shb}2nBH7yH9g@g)Oy0)S=#u^ujLkmA3UU>U$uR}-*b>H?=2~0EXdPPFojB{tPFbNc&;qfR"
    "$&W&-hej++0>$WY1T-*=I}F1pj2k-*7}vrumNuPj_CcOW%NUkm?z|fzL#_H|!~lR#ki@)~6Y(iAZ>s_CGv|f;yc^?OtRI{>{))!&"
    "*O#zE4L7+BcQsrqY=dP&TycfPV0zhE7ibCF!0XTg5l-{D%5DPM>?*qnVe`UDS8!A&ZWViU8rWz;i|;d+?1Q5!_3DzU@G)+2BA6U~"
    "u@TKRX39WyBn#K58`jq6w%9cXx3y-dZ&+YseZztp9qJ)9aMduh4YzKc<@c^OAd7wH_b}EtfDM%)VDwJM3C)$znaeF6@S}M*eE~5x"
    "p+O~GNF<p6(agMVW)32L7*4eO&?H(8#hO(x4Ud6@K`Ph)gdxT@{@^M-S|L^2@kOhzf|kSI>sl2Tt-_k}`3~5}40#)jZPT7m0S%UN"
    "n3#|l3!t3Eh9l<PSy_x9vMCLUK?EJ8+>&lqp}(P<8zWKBt>D;DMWzTxQMV@iz~@*SaXl59!HzETXF_w$<}5V6Wn;bE=5*Y(y6v1("
    "ekAoeU~MWC8Pr%^Tsh}63vLL9oF{WY@O#GiZvs~!^%j+K!O<#S`%r&dq8Ul{SYOl(<)*{24HxXKHjR>8xI=HQXcz2(p<CM_C#?kO"
    "nQhY#ZlAte>hG|Izmy-@EyJW#?7ZEU#WBzUMXGZ_vnm|~<a#WngtK-+XegbqO+K$O4=6ZF>NC%S+U9|Rm|>@c@Lu0+$Bib7`;7G0"
    "*Yiqkuz$?W=n-ObvLQ;w30}g~f|SeTf!+nzlNrhMqB~WxDE~I6*8|4%m%(q`T>L&MnH;`DNTy`#xi=M}8F((s;6;vY*9k<nkUJu3"
    "qg_EnN#;eA!$}cWqZPSi%8;S?3QPd3uji)QurHv;x~yb0qIr+rdnAhy%@h@ZTIOUz1$`PQg5)t(Sn}xNXWrsvhjTWztH~Nq6rU6_"
    "<B4AOq>#LdQNc>P3|`t-*th<F=>_PY8w-o5K;;tlDjiXh3R?^hm5Q{Py$BVqu+g|t4JupSMclZAakV{-BqwCatseQh$dF2T;8g5s"
    "t{b#FWi?r+a-ix2dI=~xyA9=zKpSb|3*kr;$z3CpllzM&;kOH%TtNyZnzy?AGZ8HTSc_jJLy=E{jXblY;Mi?Kp80V?<ktz`jv9-E"
    "09Lw*1aUa8NKl8|hYIx&-4i{H23DY0EGgs$L?V?`=k1<WxqFfXJp1bvx@1WafzJw6u2fm5YUHBtX>}Nh6bg=l2}q$O#cx-uFnA;W"
    "fcZ{a3Q3J=hLZ~712PSU_l1bUemL)0<+pd9S%ZQHq_$_)%3Wb{D^8^{lY%@&hn0%2nAw#_21n(~i(27W1I=3&->DIRiVSYX+x_NZ"
    "Gb!UeC3azh4Z6)#!Z*vAbqKcg!V+ETLTe$p7)1(tnz@F85VB{VP!K|5?6HC%rM&{z%800rFG5AkN##bFs%7wK-WF2Y^9mZjCvyL^"
    "YY^Z{9}Iz=j@cw8e4CL5hH8woY$)KRl}}P*g4^%Y-EL$^tNo1PDUbG1;kRL+b``0z!2=xXDLqPwHYzv&oaQFPSxu!9t@}-$WJUcu"
    "keZ}qn?W=mbt<`c#4W1M%=@x1zmm`xF0%%uRExY<Mx`_Xh?;8HLm9wP!&L6~4cd=XS{z9!a+pX_I<<glG2Sv8%gLFdjBJ8hH=0Ej"
    "S?#9t9yt3cPp*~2y{D``qL?X5fGH-FwOK0Q&)P!nIeu|6WCgDjJIz#u1YD#+b6E*#!B1^6jnfEJyG2Jlmfl4s<>|&3nartL*v7@J"
    ")EJ{4^G=%1ypxu^lL8WH&2XiE=^(r4)2Y;z)s7>k(eZ(z>^P3OE%{|W{t~A4e~_O=m7V@fmY-owMxJ?Q#Wu6%Bwm*<L**E9iuD@h"
    "RSc>+;Sm!D9rCIuLvrqG^aR`q6OndTu~iwyhXT+rIaEFjdk*A{G+v-Qr?@y`W;F3$Ub%x}VOLH#6OmVr$~qIz$*!z3>4fYk8%B$P"
    "(qOc1^!id^bc0N*s@0h<Ql>1c;dLHF`pPdiz))m@rhCCytUilLpZD2l(YdqM)d!k6WqUW!u3Em77$BKqxoTe!41Gu=b~Q^J1C|)Z"
    "!Py@&RpKCza*;;`EH1$LJ~_B;B}xL2WYY;H94(=72^R|NXaRSXrLk3Rda46iVUHN6tYlX?d{TPw6s8emY5s2McU1^0zfE^@;kS?~"
    "9EW=3gUQCotU3fl+K6yazE9=5B;V)qy&Hbwzf*kX%-&WRT2J|INq7t7&yIX{>2q{@+=5~91jIm&?K{ukbuV~ECf~(6*hX6Idcir;"
    "8s3ZdkrZo{gg{A4vyHB_GTYHLVRRW`o5#Ae7Uxb;`|!{dSnX!IfB$%Yx7^&m|F}FneERV5X1?{z_Hp_pvyp|y-MZ8YyyJK-L&ELW"
    "P2GRi9jA5~+zMM4c>kGt#^<$gw8^}5jx?DU+L0DBS2*IKUuN175B<V&&UGC3{XLW*+hm3gNx#wOseBflpaB0_;?KMCxkA*$D;e-z"
    "{g`eamXH4^`xKrQ=Px0~`S%qF5G~$do`nF^I*6^7!SN8sIEi^z$2iI0P}s?#xh3w5={VC0fojnWOHVY%&pT6b(#os=ez*40b>h6Z"
    "i9f*fi#n816kUeEqHK4$-J&o-#0-yjk#qsfKZF)3xBM(>*4ss8b*b2>C?nXn#W`wK)wTt2vN3m*3gY`(tUdySZ6w#+`!dZX&zPu?"
    "8G9mABv+gKc)Yv+`1aTTb^G|R`(MnTNH!lxF6H-4U2$jxj<pB_g~m6Gn{)Mq%jN}eYtC$#=x1w>f&-w~a_NL<(0wv1JB%LbwSV{W"
    "z6h85BI>9hnevApwN*Mf#3uGMXsVQr?&^Xr@$|cn)4Zuci=lu@PJ~?n6`Tl(fYPmi3R%6ME}&eDg6aw=XWelD6+ly;D4?9{7lp2X"
    "QpumKFQ8P)uiX()Dy7%%2`I%PtZ`pJd8$1rpcJE6#aKXjni>cw#VX^N#57_YGlx^#l>hVg{e1t=;U4uB%7JuJDJynQI;oHqdy`IQ"
    "=!W7W(WF9tZ6un`(U=*@CB-xw$t6!Cr^C*@up?P0serCZC5Q?xcPE6B3b3aGq2y_%snR^h+Tt%)qYzRReBf+tF`IVAq4Yhzklmu%"
    "tZw~pxw!d{AO8IB-~DiN^WzQY^5gBh<>BVt?!$-M_dmb=H2^a}o}lPTQ(h$Z9O`UDip8V8>mcfh?rfdm3~%S@0q;v5A(*$0GG5DC"
    "#W`=Dk2V^PNqlWbBc{s+Du{x36&H;3bT@B3Eu#^3d*uyf#IBik0uQ=w6dJgv0z7Dw4TO;req+0}1aj`=w34*t;<R+ko~NfJTfux?"
    "dbn-4rcWGn%1jN&;y;}<ar-hbZqKr&%9x+;=+5WS!G60UC5PQoEwozIM#EZ_Rr?prrP}AY1d3aUPfqTr)8&EC^cGO~+CGE}?dfYw"
    "QczS%%$*gKCQwbKjM^{E6R(2*THT$jupE}f|IPPk$0y{^ffZxby7I~i$%m^dr0QS@`Og+XI$AZqWTNLhvPP>_Lb1j^Q@W&N=ag{M"
    "0iO~nZ+F_*^C?Eq|M+yfd|bOF^ZJMM-o17-Z3mm!U)Yc-X1~KW14eW#AxapePetdC`Ik&GXXpx0>1}j#&In7uSCs1H$5Mhyiiz-4"
    "k`((_^b;tMgaQ&-pepY&%F@oF<`?$#<}-eYufh#QuVjrhmu!UH>q!(E3ZDy-r1A_e1<&1Osk<^J{_P}|QX&2KwoeZ8(<ejErFNT+"
    "*(jGPDH%X8(d?xBz{tT%5xPXchrra+`(sq@kCfxZk-G67Dbp=ovv9s|$A$)^>(MNpXSr%v<BQb`C)z73$9m&PZ;Uw78>3#|8#Bay"
    "RCQKxjzRpDBvx~yJ8w1I{BZB--+j29{uWsJPxq+{f6o#?#%n~Er-8kir$LMd2Q+{{(7}N_!{8zeQ+IGE*}_W)=jiIl!+wkP^5T58"
    "p5MM-Ef1?y&uuF<?3TX;uHAZkdAI7^<?`TgxA?eQeB7;=j-ggxyl#ipm&4&1-96;)is!gpsQ?|>d6QF0$`K@-3Qm8W_dx%Bh^eOh"
    "G!73G72gG?yW1k+g5O??+T<8fa+DV5Ifztz+Uu@Viua2m$-ybfuMWH0yXS&O<|9Ixh{JbS-cQRm7q!$npnV;D_mI}JTO8EMr<DQ>"
    "oM?9xe8{FpLG@p|hmU{y@u!=TbXolA{_PJTXE5jg`}T1Ew};!Ge_kHmawp!teOV@E6)+wL@qnJzd3($>$G@5(IFjyr=ZtM;Tr)XJ"
    "NUvxn^e;LT%_UK*on)I@ox3Xt^X%Cfx|@@S=R0J;pCnVNRXe3pjHguEuVzY>pi|2B?UX8a`6<<kPO0MUl$r`4nd3P%=Bt@g%gLO="
    "V%j;iaQQg}Dr=oI?VMJCEP$sp;<0=UQyNe#>6E%=N)59YpV9z$Nv2eYW=ajGfhBu1r6J|}*D|Go8tq}H+9{Rh@>5FFWbPbqcfL_n"
    "rLcHPwft(PR8zALOtzg;qc1<DmP8Be;4rmQYAZBBeETvWzM46WCaP^t@$-1@u2YwvQ`d%z<@PPj?71^@%fgm_H5#Ff4^Le`D`f?%"
    "FE>`Krnq13KB7+o-TWM|OI$Ouna~oUX^eV`EkHefy#G*cOjcmmTL6Ck{tBMk8m15SBs08K25(jhOoBN~QH>L(_S~`bdI{#-i;~Bu"
    "pY>2}4RPn6EV$;C(nj>U{=8V%qTA#l14cw}hpD%x>`%+%<L&+Xu&sKRZ1dCd@ayfg{Ow`){_(^8!^gKj{v>a>PM`mBxBGawe|Y!y"
    "E&RH>yY-`9-u~tLU*GM6C40(q0;+jc3NM*D<d-<8MF(>>8ZWi0`!OL{7-f@X{mYN4_~7Bt8;1J|488n*!L9<snQG>{&{0l13SY;h"
    "25(sG2=R#Avpn%DnNF@Z*MhZ=VdttHHfMqON;V(heDbNYK-OM-Eo(0su>kI#`f65wuSbSIkoN1~oR|=;`!obG&;maVfx>6Ibnc{0"
    "wC+tj#mWq+=LEv5gvi=gg#sdL&u$zXv$0BQk-JkVV<}EV75#7^MbT5l&Z>*9oVx$8yr&O+V4?FsZ^fQ$cH)-uC3*?A+e=A$N%C%d"
    "iC#MMstxX9WM^-KJABf9fuRKl`Dds&jyFJ8D;RR|EeN2uZPbZ!*zql69h(Ek%j}}#TTv;^vTK~<oK&N1YAX1DZ*8O|mW4E-OanAr"
    "ey;G(qfgyrCPjX)O{dIE-h-TJ#Gy0i6^8*I){f*`@DnG~Xj{#EbqDXrKnH55l{>)t>+V1j)!Gojb+`NNB&+@(vD^#JBAXp|T|h<Y"
    "v#jzf6fj>2%R1M-Ax4@nDaIPRW(4Hu%Z=D~#I_o{0Mb{ETtmKOS4o)5s<E&61W-rKS2C#;wk_7!b%-ALDyCD&R%16(Ac3QqWM9dQ"
    "N^w+U*GzsbYcJt72f7ZBzx@N<ll0fYIm!~uAy$s+T^4?t4}JGNQGFf5h$n9GhPSFY%``LeD`6|6H*mC7dngv;rF7PEyrYwvQtfC9"
    "U&(-g(E;sEJ0LKf0g-!#X6|cQA*Va)sSaT*RA=*_>^XHd&4+HTI>fJZyr2Ac-P6+i_o2O6b55UB^}KKP3+MLKEw&WJ81H+U)b{M_"
    "wp~wVk!MZx?uUk9la=OD)t8c(D7#FgM7ept$S{=Z3_~C2Ff{+dz0`K7DRc8G8<+q6$j0SK_RI2^l~l;-;?|#EYBaa5DkDpotTTof"
    "A4{Y^)c04-ofw4-YwmR8xHuOYY~X$L-m3-U#A{sQ1PPvsvWR_w*%gec*%;bT3w&$&5}k{;6*8@J=^ITREY@i)R3X0Xv<mf%ORyFa"
    "L!SnZN16^%3kj`(Mq6x$^Hr1Q%1N84Ia`FTVK7N6T95K*dRm>bd(&D|2_tZc^?t$WC=9XBtiznNJdjaX*(sxelmTL{n&NC|N6T1Z"
    "3%ZSEh)55SHn!@qFGF;rU|@@Z3;#q3D5{Di??J!#&%CG31UTasKSoPlTc-S{vs$KneJ%{<SZJn}0(y`{T1wV~F!J9;5Aw)=S3QU%"
    "|J`)esQ{4NQ>SD~JeP%l#`=_0gy$U2BkzfZDqDxmGsw-UjHWr8+)Rk*kziV59&dJ^ZXQ0p4=&<2Nsj#g)V*7eEV+>;_*WVWG$3KC"
    "1>R{k4-NG0oWTmxXatq|WnT^=!aYhU<hgWamUL=<{gBR!n~~0l%!tf9Q3+H@<z(<;ycvyV-}mwB-M9IE!No3OwlMUWwAyh8LFYTa"
    "6&t~f-@&UO)MK0I#qg;|&8S1|vFBJQ!wstAQLjVD9lDn@rVcxI=!PH2Okw`qFIQ@ExXG4M6T?W>lkGU48Cf~!B8^~9UI#;*j>=AH"
    "L=ASWxc_nX?LFNxjO=-Ui<~2Jb5%8su;-d*d~Kg{FFALNcD;dBn$kp#mo~%L9zJxjh^~caCb^fFZ5=OL79-|bwv!i@?K~&p&}4=i"
    "e`$+7H<B1P)k#wer)a7#D;)@CQ^rp;tZ2NrXvC`)pdH3sg(P>GFs<ai^Tzip&?bueZPQuM%`U82aYs{2YA!1`tT09`XK2Orn)|Yv"
    "jbYatGpqFqR7$skPqOt2^swgfm$tz1OPHC~3s$);*!1kRw!rikEbHB+Eda$(g&z5c!vYPngglCGDEbUl)uTLOMl-$A3CdJVX*xra"
    "Vb=|2hH+9<NbDDN%1PISdhctYNQgn_8O~}SP)b#{i(fCtZNv+{uvBfX+6<h=(Pj|6(W{AJp3do6>R1#lXFQ*le%~z&XNMux)>%82"
    "e`fSrLhX<Ktn!DoQEs^FIY)Oru;(Vq&XzL$vg>UlVr0ZGTe33FF5Q87SO=%!X{>9Yh0I=bd#ppICoU`%P?C^S3jeS+Bjt#`+gtD?"
    "yBrQKd6#_R#wyrqz>++z3tAu@>y_%-S=4N=829mVt2X@CTJ$hHhWAC|70@Ww8#CYt|5h^KNm+?x60Uu+_)P2++knhc3^wcC5Zup3"
    "=VE%uF_C&n0LiAq;jCtTD1z{sQKGJUIFt;)&KEr&>#QtUvcuE`wL_0kWBCHB-A97o5!-Pv-Rgji2~H9EGT=>-8t@6eNVFD}E(-Zj"
    "qUdiHlo-(@hcu@3Iel)g0sZggm(A*zhwdB)?HJe5(I|bS>4}FZpNNa!)XB=xl*$dSTu=ShlWE_d^FR_^4c849-MMz`U1^8wS#WBh"
    "e#2Wz@0r;sLce+jy&rNMy4N`Xv(k8lYTSBO08nD9<L>MMbSMW9pc>nBfw3jLq*xTPbM7jKWu$t4!M!sgs&<c(>M&6WqPq0jf(kdD"
    "bJWaqy@+0V(KP_g7POL@4y<&87nW`<+vL=4?(T}{)TNSf*Ev?8A39c`w-@#pc;K$W-fWEkLt{xH6u&?k=!e%t7x(;2`V)TWm`<vt"
    "X_tMtXDB|(VB0>2JQrGDoKW1)K?~crKug{Nzw29Y>4nt^V>XaEly_u}xa{Dv_1fT~e+##vEhXrJJ&<!bj*3oA!yyqijPK#|7I?c8"
    "UTi?lhtFyQpx#AV?H<lPe0Ce)_b&R2aKnE1)WXI&Mxx!shB^T}6ix3tqp=hCE}>{nB>iX8z12zal7}xBu|4~PKu}AmD^3nCpN8A+"
    "2}&teyf&9DbZNN7MILRtRfjzO(zde*>lbg;E)r62Z`Dq^3%54u_=Ad^b+>86=la1`?c}A_AD6*9x3}u}vVU2B($TRVJ$B!1loC1K"
    "t2}halT*n!bV0wA<Q`ngbULC_(lsrReG4vCmclP_q}4g4DXr1GJ9nK@heIi~gT-_a7L#>V&8-PB<Z&a*RY;@uut}d&T%{GIF_wFN"
    "D1sj$?UXY)H40sDksdjmGk2eUzF!fE%I>bbq<6RF7+cd!PXJxhfC%?R{Q-Rr4L9TgcCqm5@{i2MirfI^vp0Y`SCGe7X}?}9LZTx^"
    "JUN}4D>`GRxq>jcVQO#@Vsc=hbCG<wU||}e&dJXd1kCV5!k`g%#>VR7#+Z{XVoqMxOU2b(*<Wm3e0rxQkkuGe`<#dw>tnc~zt-$U"
    "k?B)9Exu&Td{MJ$NKWNNEo)L6?sp{**ll0h+LakDgWc5M^Fyi`dq?JJ1fM^<r_}*=?2TxB4j^SCYm^i;(G$YDIh|l?DrxrI5P@Ki"
    "2ovou=+3HesK4{iv5D43qVIiR<V@qCoDs~dw4<xXq}5Zn+rpMcJas}U1Bs1ush$cZfohafL8)_-$z-o6XC%KGNk6yddS^DsPm1`A"
    "qUOEh{+#_>Pqx&od{eXUCaOtmi|_JlqVIP3nwDV;=`O#fna;$_VBDQCI6Qa^qvd{4hZE8E$uq(@emW%@+A`B4qTuF}+L|NB(B{@1"
    "{ka7yeQ6y7;=0<e$r<2KdK0-iMZ`dQby7XZnKKM@>+P;i;r7GF+LDG^!S8rV&s{^Ue4jg>m44{K<l+lDYp9s|hAMoYhPDx>Gi|6w"
    "?rODjeM60VpN3j_&h^e&C$?PUoOPSriq0mF%dJQQ$D#RNet)!n6cinj)}Ux34rlo|>_3AnK898M@p1R*>;1gA%1Wpe6^rLRd6}1r"
    "I#@cJF=tYhv$&|r;-42vGsEq|0ydLd^m7K^XU;@_grTLy3GR*}RTp~YT+&wQO9@TQhLz=!MorN0KYsmkfB$j*JVn3ea;!MzN6#Y8"
    "X}RHIAv_yMx8=wzg=TqHs?W+P5I(vM7h4xS08SEJNTxM8doFu~MXx%UOa5RRj0Mhl>Z7M-97}I@MSA`vRM0M>ur-%xm#%e$TZ`&W"
    "F5T>^IvtfKlBizZV1%A_vdGelAx%O^BeB^=>dO{v;of#$oEbL7M%l}A+1V&Za^A5}BZ}Ejs9wt#3pKLsj)iLESg6KOp;~{DP<KTM"
    "TbOfCNoip}SZlZEvM)j{XOnkD*S{~E!avaM%O@iHdUk0(g8tMz_ciXZ92q(&rGnjHJh+V#YWZOuJ(u^v`4nqdcL5)LE=W4ig^+qm"
    "6YYy<2uR7|5|$VU;n?d5NWT3Gdu;J=93)4uJav;5Xn$YQNDyndbcu1hWHAOrBqdg-TkXF^SBa2Flwk!D!^)nWOA&x*WU2r|%sS6("
    "m%$NWxB~{zhf}{3De;$dVfo|kmoGm*{rTa`@$P>9{U1N64<GCjt6H3OLSZ8e_>i=+sXe#ZPM#xct|RF<Z;joQYH|{*OKQ(b*g*8F"
    "X<55^iO9il5*vTCf=&aJ-3YH~=Ec>e2;j%33XmB-`34{}e1Zl>(?R3Hd@1~YI9f+ueGY}AOG%$lq_nNYH6bDd+SH-sAtK_~Us+MT"
    "ONfZWw1;FJl<wfDnl2dH1>JPv0DTwCJ9Qxi#%-(7kwLaoHqmaeaEH%^@26qVc7H2ro=yUB7*7H$?Xvii131D8z2E@G8WVd@>55q2"
    ")5F=|493K(J~)FBH7}kYznEC2wvS&gYEa#IHXt8V_@R;5M^B2Ei9P(pJp1hT5#i;;*&ov36epAyTEDn`nmt$TkE@mRp%!bH1IhmA"
    "jvINfcf#1u6Lo{~5x^r}Nw|k=C~so9oF|9d;lz%;pGq$rH)|3;5+B_s*ycd=h{uu#<a=xmUL-wn1Nb2%0lPhO3%nQk7)#gZ-82@;"
    "ZdWS14yn$|AyQpPB1W0#wI%{s3{WFO+7?ipmpssQUvkTqH!ghQ@2QHII(>w=pcBAA$K~NA1E7Ap2_V}Ca7i1g*-XXbJoODV?=w@S"
    "ap!ndy|hD%U`TVkqewgII3a+LhrXlSd+_Z#>h%lEBwhlGj@r+MUHi7<C5o+JWFG+^HY~2;`z8Wk_-@8$ktFnHk$$gv4yjA==co88"
    "CQ5G`Ml<>*;FW09DA5l~^dWhVVNtRT7WPWI5dm08!x7P!SE>&dE<>V}y=sqCT8#EcrHK_;tNG*r&9ywX1?;EUcSo%XTL5=gl*?HQ"
    ">=ad2_E)eXElXX9%+8-|n*?847oQBC4G`*;7Zd|-F~8=EWXW)0J3tIj%h#fTINH6SWNb>71!jCL880e1s=L&wY)|gQAyHpeCJTbx"
    "PjG0>GG0q}k&LxcZKUs>7pyKUSgWg+oYo_=h}Rk~5@Sp4x2&fLD8z@?R`DQ|BiTlD=H%PGuwo7~y`PSqyPwzRVW!utj&}cWrWJ?M"
    "iWKa+^~@5|_%VK52&XH~k<X|Jgo=_pZ+VTx1*5k85aZk-J?ncTRQE))pC;;)>$87Idipm;%99;CW|j`0T}MuNCHO*nNkM-~-;89l"
    "Nt_X9IbyTlNbz-v$5gq;`sf+5&CMB-fc|Vb>ks8;?3Bq5&-I7&oH1%T-AqxgOh#|SDDP)+WRf?`YaS+|fG}s1W$1Ubr)E*<zx-Sl"
    ">C)YtW(9lb$}@SUJ+=*dw_u4x^)UiYpR7<iY+Ke;pzY=1iOG|ycGbCYXVPu8Ixl@)J+ML=zT~_#9y|Z^{o$zChyXSJJ%6jojw$@e"
    "4282jE_$Y@m+zkj{btz|(c5QuhL@Hdp&RHCcOZmY<s`CFUnCPNEiZd=ec6-(<0WOQs{+`)RiglQZwd4FOInmX&T5e0zwW=@lR0iP"
    "B2se)k2n$=cW|q>%sq8*a;EjokHppNCwpMItlJ2N37^|ImhkB;pp>^QH7!|=#g!zVBl^r%S>6M@_4YL#$h>WXZwT34NMw&MIPZFE"
    "g?*pkn^2G6HplzO*0_P&6~3!2+%E5g*~0A#-`(a_Ir^JyU6oz76t!372#P^X5sKO(oaA@*Np^7$-l-FIU#I918(&p7=gsH&+j7}1"
    "w$)4pxsJ0V<DAJE*Kx+q^~ZB^#<v@1$B+4mKy8IIGrU<xf0)tD+S#i>LVZNb7;J#f5(BZB;Ph}5->>j9Ch`4&xIEVR<ycHeioGb3"
    "a5P48ci5k<*NJ_p*uR8V!#l92ugwuL<FbaJJ$G-8a2i$VeL>M)*mD<WFD@)v+VRcVOSr61W!TxjC$`pFHuJZ6N#WX`zB_w!Y01W4"
    "wW=b6;9ymGYc7+d6VY`$boRdrlEtD6IQH}tVLX<YkfnG(>C?q)sY~(xS-gAYpz*+BJQp~a{r<pIQIDGjw1Z>X3y2HH2*j2;yx;Fw"
    ">GCpZgA!YX?`BrG@)tH;YrZN#bgKf4xUg{Jn!@*e;Z|Q*xV;KJ&chH#$pghvdP$SK+L(%t-MGNx#w~o$uy#EI=Xg;Ik{2eo&V=)9"
    "D#;`$Fx+F^nS-?8mH0?h)fne7NB?}Dy1<f<*20s7v)8ql*<n?htviKc770{xXeKEj9*daV@pwi})5p@C=24DY1|rSWz-EKmc8w|e"
    "9cro@rNFLY^oqVH)YzaWT3@2j+pN!+u^lM#Syipb4c{BeV7l_;fCe_E;6bq0goqSkH!XSVC_8b&9)!*gO(^Ib731L>E0sZpKi-9f"
    "8UB?MGyYRr7)~F~^w}4aCsy3&IwSYT4mrak2xfZ?9hz$0K<pXL9M37Cb+Q4+6Pjq5Iav0^Wun?xIs2KNdWbX-^$-J54<s}UgwSoE"
    ">de!b-8~c#{wYaRA@%aiMxt!qNWu|2Qu0F*J;VIrjFw-a10g%n<deXN{RQsewJ4yP__BjjZ5blV(Iq=G2)$*F+f8)ehe#iE!NCI&"
    ">tv&FW}FF`;IhIUSDbf<?I{kC*XA;@c+U$b#*bP!m<tQXt8Szqa6DPjUnEQ^G<yKr6R?2134xU2nGZl9nNm54GtH2qG((Be3lK!l"
    "n9*4U8S{j{-s~A83&`R58ItVqJPV0LruKNIGg8;i7`>%Z8Qv%>&YWi<iyfb5AXD_*)_Dfmy@j1F8d`k^q=T(pTT9kZ&s2<Pepy@S"
    "+0(;;=t3Zq2X;<dUT%u|0g|HIZkz-%9Z|!RK=Q~RdJ;$^c*oA3JHhZ+1`UB5rypQXRMl|n;hJo^^3}wG>Yjfbmu9j0LgW>BzV!u^"
    ">N&agJ3&p>ArD-(1!eb+c4uafZlDN2?TZRGezS0Prl`wq`4C+{=+2Cj?RIA6{Dori{Mw1L=nDsNVc~F<8zd+kxj}{`eVH(k;ZE*%"
    "rgORlE!@WLfCp+-fruSq82D`jWLGtn!PSPm8L_=)P>N<)=uZ}NAj$DudN9zMPTN_Y5r)do^srEI^shuaV_8qlFcuWFmHjESlWfD+"
    "mIoKo2Lgx?9{t-FXs0*czQSj-@n97`yAAZV@EJDH+dwxEaJGC_&8t`Vq_-boAhTzbJwEJ*bXU~;1XvF4bwiC#AM4%Ut24)ISpH?W"
    "Al++^^XJ37HWCGQUEQxv)>yLmv8xD}W`pltMM4&6tQkOiWF%vLQ&HQ+1wulW4DbR^PcRAxayMGB!>U#!N>lVnuNjDL73)J}&@|56"
    "ZEOzY2|qjw#uW0v$fX60B~QmNd;l%=`l-~LV9mFDT0)u~>37*tW6M|rhN1B^x}R}^wo{&KXW2`PQyaS9PEfR5Fb+pfEf7}138l|?"
    "KUDf6%E)P_76>CfbZQBS#GU|BoSPD5Jw}HRs-Fwi9l){jZjw9lc5kr94#JYeke?(;vVwvrfjHNR0+JPesNx#}KLR9EO05(_h1N=b"
    "jY8j%L4ZvmY?VxBMVJvKgYD7Rc@q-+M}0tCi;yKl@9%Tqf72Q*3f5p>;{xEiR+(1GM!*O}{Eh*CJwyhLcKDzqrTshO4%N2!6Q%it"
    "1NOIvyeL+{_>kt;UH3Qn4LJPEkaujbz)<TbyEfQFGoQ9A4mlpu2oBN`GDhaMO|H7@E#)_PGD6)7BM-;0Q`o;<m$?$X8>rTU<agPV"
    "A-Q@2oSWhW&>Etr14UgI>ySjJhVjYBychV%n5o0SDY11jnwtC)BnWVN;PnB{lv{H;`2H;stio^UIqZx*dH6-g0CM=vXAVE3%Hiiy"
    "xXET@Wk?)4a)P7L(kRZHdd8Gf&pA0f^_&}7=^;~cY@T|~x$&vz9ME>kbL}jro~sb?^wdMmPCe(@d`EgrI5=Uthv<(mIwxE@eNLTv"
    "E}cQ!r(VPfSx>!LoSO@EHQ|O;s&<Dj?L{xHz42mfxbZ?VFCwySM*jwS>Is@e!42S?+09h5o0nW^M(JCn*~?Q(vsY)8X0JAtW?Pau"
    "T{2Wv)|B)Y>CE1YbY^b{I&;}JygjWmdq;I<wCA=BEZasT9yzBoXOfZ4-J_6<q*dw9?H(m26}%to%-#=mX79&3a|SBe-aR5t32EoK"
    "-D6*N4-Z>9GaT6N;bE*ZdpxBxdmQV`9?$B`AWrDaKz)kQo?Cc@G%5Vfjdu?aTxYg)_W(K8nL!S9X5jpb3sYN3QdDO~bFLFmI}sND"
    "X?+zmLxJ4~MW9oQ!+n0JR)di*QD?!*bLuQ4U!hZaKDZa{IM89+1Hf371sE#E0Go<2;EB?3tQbeckh6+0im_sxJt{U8<LFT_RE$xc"
    "Rg6)N6=RfR#TeCCF-AocV?3Oh$Kk5@@8x$x#khCOpr;?|vx+eqamr*AT_#>I*COi1_UX3zK5Qt)vef2IE5_)lV!TslPB`nz35WiK"
    "VvK&Q7)R8Ox_|D>nWN1@IocwN%IIiA7%IluWn%MaLpY%rBLHouJlD>0v>|RO#{S5THpHP~9AP@fM_Wi8D#j?pImH--7%RqDphi-c"
    "&zWa!G0&plD?3a++8w^MnK=lB664;ekz$O3^FP9BQ9;2_zjo(rTGrN1Xs#IBdEY3;A<GHH7$aiIX~j5XIb}`8$O%KO$&E1?qx;13"
    "w+<9;pctd@r;W)Nd0tLz8z_J(#ydQ>Z4`LT@WZo;F$x$e#wd^|#=HHw-QzfwdU2>2WAw4u-aSy@P%#c^W5pPy5VW1=c8?N28h*E>"
    "7<-_*2TCzijIl)};k!qKB^j+ZDbFd!7>R0zyN6UnG2Y?1g*TOjC)L=Pj8ct_$tblN_ePHtW0ZPiOvcD~Lw1jImNt8+oiOxi%eph3"
    "kh{75&c9}u7fP#!VO}ATfzlxCj&1l4O7||HG@%}@W+_P<%HfmnaM<?^eINKFjE*TU*mUJ6d<~V@L}<b2X0j1>hDvNAv|!}o=|B)4"
    "%a7!i8=hlP1|btsZT7kaySn@QG(SB2{Pk(Ux8FS-{zjmsQEdhTIBQuA%3o6hZq{H}4cc8%L-mBDu^8^4Sq+8+ChwyHc)o^W9>wSv"
    "!>@?p(-;N^mDPM{I^WHB<=zDbC)8v6$h<OH8-B%0(I!z1i55eWy<%w7b16eRMCD-v?J#`C5!xXtpfT7lZUq=-1#$b%a|xr556eTa"
    "`)dmkMwq6k1tB7SaSJ2*3%Ti2fLe@hK=j5fX_^#Q$VE%l$VIl{kRi_y>lU-~(5qnGqE;hNmym>)Pr>MvWExQ7uz>a@)m|gO27Gu6"
    "CKojaAKsA=S=1DK_{Fsw7R|aq;`X&$7S1XaOT#N_cd`#{F50Ia(|MzIz`}{yjPkNegOap}@nMb~d3^fv_%BJ8^W%Suwza$8mTb%;"
    "HeD@h>G%@mK_@5IjhFY3q?l=M5o@SR5+-%j$b_&s?v~R-r|Zg=<1QK@m^15QIwV0UAw#cCPc_Z2OjC<vZXIru{3j^>;##NFghgtR"
    "L}_XU$l-9~>+g`Rp94H+4jpo!2AX74Ad%(2N%n(9lqFA(8d(O^C}fCCi}F<ywPQ_t*7UAd2%}-R?-_=`c;&ulj2rEH(T}U{dk6ol"
    "4oF{nU<KdZWd|e|^0XV+e%(UqlyW^OUM;|p4eaGjbT|fYuho0k?VoEJUQ<1=-G-M8<{Vi1nicvhKutv339sz_2B~%I#m$etR#kfc"
    "7Fl|A`?wSGumKL&1tQ_H!mTt-L8~)z>4#MeOmKONsFf&l#VA<iIti^MBhji}UbL3oLq_eiW{)cep2mHiHBB?}szFP!DJzh@N+`cY"
    "-?9lAYm1LAr0HwqYzsNhf7OjVXhW174y_{wy#qY!mL-d^9qsvdcI?o32#Pye&+lDccks8Ep>y8+-W5@JMw^2LZk+SP3}(YcV&$=e"
    "mB(()fY(eQmpoLcS^DsemhXhkXbfcrg=Vl(b_^}+<t>nlo8&r?;D?p4FK1Easv5$U0EAEzIw3l3Mo*Mjz1N=d%FdtDOCY&l3Pm&-"
    "XWUgyPBGML>Ey7Ok9G+*sExPws;a`F4Qs5-Zk=M~RCeyV3c{hz23W?OV#nu@zfN2pdc%P8xMdh{Aclqk2W%=I)w7y$RHYeUPhs;*"
    "ip`G>+t~Y6RdYziF^OmC!Ky?oqr)*h2YL?5jBe_1qR_t&C^JSRo^xBgSK>JwX=UO01Z`PwY=rMBq^XzO*t}^`DKL{*ZQew^;Wrya"
    "Yc`xvV%cNs_01<}<;VGHPD*?Eyi}HVp0%D71d)yl9>E#X;F<~S9lz5_+J)8yoJrkz)_0&k^wg>}sb{TiRXj5>Qf)nhJ*~C`)Oh^C"
    "bR$$H2maIuC3m$lLQ@%`<ZW6;sMgcqtUuBhNzc~y%ZDhtxJ^AS3PL)}w}%L*!)YF(^@nuYOvXKHh)hOZK#-!}ej%|cwA*iVcpGiM"
    "Ani4xfpf%pjFAQ-sL{#nLeZ-iXn%&02Ek}Hhq#>ujC~FRPR*Va?1rLdt;@+%b%n+HT#6cuxI!bS!jMSO5netfp-<1Hs|lI$6kQEQ"
    ">a7!WH3*2;v=zmf0TO#UKq&1C*f=p#QJol1)ThQX5>h>%C={`oh>ZLQ(byp;WJvT^$<XQ{JtSs-w=H@|M8{5v**|LwntiF)^_b)P"
    "TC}6#y!$1b*RU8q%m6<1_w3;{!uIsxycoUK`f%RxS#5;#VsuvHk+>KctX`mxgpQ2d^5V6B3qUn~-vUsL-?so%<M%B9)%bl2KsA2f"
    "0#H?PMlv&&BmvSfbqiWR8v<1kGAX+C9HFObR`TKJ&mVt!*nR!mT~JobWcl#vFMs&ckK&{Ke|`y*{KJAym2~4!sNQ<w)>^ZgwSR+}"
    "jozwR&a7rD-k@gdwraM>YIgb!YIYo$KtoGN5c2q?b=kzR*EscA;4Rt)J;h619jN+e^0K0kyWN_)d#Ys{rfE=h$e3n%6j6Nxh-vic"
    "ebJFa2me5On7W{Unx8&=`g`tzOc4V0Ky*ZAQog|)mI(`s^{@85VN~?2^IDHP&rpe<-+42#x5qT*WHgIpsFs$_D!IXEQwy+fu=hwF"
    "VH=%9Rv|e3TCYH{FxY+t3Q3vy`&Ikpsh8j3LI1Fx0}(f9IAa<nd&_1_6Kc+848tpb{*2*~=EN^TEw{*5A8;jHdohY1eSa~EpJ8w@"
    "3TaZlLE{?dZ7N`;#BkIy#ntwxDN3@uO!4K6+tZUqX@AM+DWk@1GTeLH3EC#B#vQe`hk8-R9c!<<XtqW4qQ2+@JMNV?z4t=tQ}68*"
    "KQeEpL(Pk91qwQ|L9sMLR;PlVV|%(UY1Ali^x}$1mp$=Ap&ZwxJQ1gjxegd#r_0G)q@uI)_5KwbrITZJ`*6$~r3H3RX*Er%*KbsM"
    "M%{Wco{wJbepp9eC&veB*CJ`e;qHidMbkW%rYV1hHzVX}AZrLQWk@uPuQA*?ZDWIudESGsG1Qa1Gq-P5y1}45(oS$zb2Mh^JK@#)"
    "biyyn-ins&gGL$mz_QRa)u3I_%deORa(1QKWUwJ`7|T7h*eyZ^!fj`dM|(}JInG20lh8E2JghD}r9LA}s}qLJu%!9n`C*#K3U+>&"
    "69=VH+$~1gbtac9btLJ!;QWZFP|zHuNM6lC4kKue<%F4<9MI{=<whT|n+);Oki}56O4C}_f{6Dv308hYtx#=@?#%PV*z_*Xj^_ct"
    "m528w;SI0Qaipa-^9RSSSfQ?%XQ8ZrFJ-dzE#=l7!X|SzcgNHvZQXi91Fu+eN|qI88~g_Hv=<T;JI7ETcioO;6~4=k6dht<ZOha?"
    "D~B9L4SXwOni)iq$FwHskZ1?d--XnATx&hl96+4}!+_B_W}TwH->t3!#oiThjoLMLWOLaD6^)d!hrZ|FXc?jBYqp#NO_$@qYKg>1"
    "ZNznvUi8_pO&bmWwG^Fwqs)-#&(ZaewazKYq|}dXBqM6ekb*Zsds+zgVq(BQOBWNM$XY}Lx~r=LMoeRSSB9eGKX-jcrR0tDlI?(I"
    "$-+zVbV134wD$iu`@0l>-u*QHb+^BtAKgFZhr8o1%_{%%@*fiZ_$8F|A7Aed|1o{Kdwjh6^7+GuKmFl9@Bi0dKYsfArw<<w_rL$k"
    "AAbCgj~_nlf5iAHuQvx~bme!j@=d(f=IAI!$2z;nQjDNE+fU^&4O`xz-&9x7szQ1~V*6U{j+{Z;u%96<c`a|a*2gsRYHP)`zoIew"
    "eQAt@PO&Jf&?{!$+SB#z85f|`TL`pf{`Pe~Jk8U`<NfZZ$EF#j0SdX}xn1st$??3lgq!ZTShQnQN;_&&@p=ukuu@!Mv`}*~TKHu2"
    "%jd%59c_y->(0JT$I=USose2?Xkm1f+WGU-!!OmM=JUJOwgWFxUBvTOE)pXV(j2iez1o~k?_1=}E%|_!Iw=@((a~835Oi+O^A(Lc"
    "%%xGF&T4eoPhxY6h;9<=&YO%UY-^5KJt4#6-SouH>YOUoiOB$R6iX4)xEWiKYXT_U9V%QQju1J#+q+IF2cs{!4?qGKpwP)=W`Q+i"
    "vB4GheC^6T9~uZPBpMnxeuY>2Ue^ToK390~njS{bkGF^6)ek^-<6S!d(2X}&_8?5te!RK5gqJ<;pwz?n4U~>qtkl-sB+?g+-Zvsh"
    "&bsEMzhZONwrtL*U@JTzwW=u4k>iMl2grkJ8F)h`qdMBeHO*FITe$IDVQe#^7~9Z{Z3EbZ-5Y8f$Sw_=wgF@@z0V)_6rx-3i<Z9E"
    "A$6me(U9gz%;>8LhWgO|TikR^6U-6vfanHmP1CPGSYVqrO--aq$b+hLHK}dNtkkb7D31C=0zlMq9+TjZiKpp7a7aw^WRbp3L#5z$"
    "?A_|?9@2;%+o}a7`_lTPEcMC6w|IzdOGEFLkgp}TT|?+&A}6<1E934et#=`}4fU7}&AbTEFhpl7+M_7spf}^i7b)WJ<b5*dX*Ly0"
    "dl`9RB=sYM<#k&?E=jSHykvlKQqabF`t~*5=K>rnfIS{Hoz3n`9DOeqabQIxx23fWK+2FpY_-AD0;KT6He@oRTDTG{(QFkCtZ+3R"
    "&4_x#3TG`>uvIv+!nGY2u7P9y!Mc~r2sy(NS+@-JXWN&W_pD~Cw_3MjdD!{n{BdK!!2fvIeVX?_ACL3HpLf69f7wmSK7{Mumxr0`"
    "1IN2>Pd`7*<+>D#wp1gtorOqBFS^&!-ApOPVjj;*fxZ+_Tcv1L3Lq`TZL|f=Mk)IvEky~*O6l98gxe}*&q|R@Q}umYB7Vz8DNHWx"
    "1%3^>qowFA>F$|aR5HL-t$Cv@#%`3dJFrr$Vx?@f#cj1^XIUw30M`(cR+eY$kB7_8B%BU;da6vIO+aGyercBH!v$H@Tq@UEUtYP*"
    "1jMmW-&Bq=)y;<|+0W9GhBoGks+B2KBMu*Br4}5RNov!bv0BP^Ib*fl@K_8Iny7@dBGFn_TYrU!v@bO)%h{(>&5q5BFca3xwsu!s"
    "o~(gVv9@FVM;i`cC<(7$9UBfe_I6`qRr7c+`?lBy0nE_OFc>nw<G5%(%gX%c?&0b8fBNwwgjP)d+&#?d_g_Bzaj}xi|8aNx^4EvE"
    "pMIJjK1fs_KA5NZ+tUSo;r^++S**cuwYi?^m3}W?p}Fq!&!6_;KgxNjfmu^v@}ie1H2#%Tq^NI3qzFu;({bO4)T9ThHx;RoqPOFf"
    "`XzhXg#&iRtDu3YTM=n?AXx2iutc%e$1WLN1vbD-YpP!XJ*_@m@pfT%`_d-e;ADqS31IQ-?&rsud{iCaXKgm&qqW9fakM*Kj`rx)"
    "unG7Xlhg>*GbR#;U+d>9goKAGBqs(jzA;UaGvpwy85B|LGehF>n2JNuc)>==ti+`;aXIZ)_cGcG&ordt6;2Lza-|!-adHrJ?E*i3"
    "#D4DAF1(AAgEW;jgc5~Txgm$-G&|AS&ZHHlMeALkL0A8+kdJwEhf81hCnrfkCenPxlaf8;CnafR>q&y0kgaUa_yZXws|c2Qx})x<"
    "9rb+;H&k&e8?3GO^gNDHzH47Jy!mNmjUJv>)&M`Pr0oa8+M5xk>!N|<$Bk&<_<0l!9MecNur=n29oeaUZJh5y6>4KVqomzUQwwnw"
    "^Q_>f*0|}4Hf36<SSF5~Or-^WDHG5u{t+YQJ$5^bjY}_(hDIP6)=&#wL!Ee+_dw|+)rRF^!y#MZboY4p@{jppo<2T(`TFJl%TK>#"
    "0Ml3i^w-aWq^`lz5y$G+nw_pu^dvb=oK^#jznHc>{vN*md^go4=MrKa2PcT1sRP`+SfH6llXMB}esv~Z!a+z0hOkxJ<7}?+>OB<O"
    "gtJ_C0g=txL<9+8a$5u`9=;KQYj#!d*-xnZ&76HVr<|Bx(;lWzj}L2ko|h;0v^dWMyV$uD7i@|QZpv(epfq`2l#%O<l)0cUX~D|G"
    "VPKtf8wmIL8CJF!F(isnW{8;e3TM~rQTDcp4(1KPy3~6rKrhV&ub<&(!+0_2n<pYgB9Ek3!+0_2wdx!q6%(VsC?-kzaZFN3<BM6*"
    "f%W5<q>$EQg%v$80=!((PP!1PKPD3Z^VPUu&-A{pLbK`b(*mjQw#x`e{adoaJtziJvf#O`iS({v)fM+eFUox};=T+IwTSORHLv5;"
    "o4P!{&s_s}XhX(`EouJMf=4AtHL}HnBu++FUUTLh_q95=ZgJ~TM8+LbFyiWaH}fcykim94uQ|}E2a2HNy;{pPdlJ(90}8af-E(L<"
    "3VN7EPBc>xcFO~1{k^fo+mU*LL@MS1jH-(K#c$AC%bu?E`p^R<1N5D32Fejv#JoowmiJgF14Y52Uaje#IV-Eqt3NU!GL`3e6s7Go"
    "3&n<ewU&V$Dtrx5T%t!g)I_%1LbusM!inmUn^mN3>UU~(7@$}@##f_VaT%>e@UR!^;~J?*7WHudigH3FH}P*4@LZ{u|D{dPj0TT4"
    "FR{E)ci4ppXU&k19m_HEN*yqcMmv;PB1Lx#q#E#s8)F3fZ0urrj+V^?U4KTDa|)gBbs#onBJJDB(3S`kMq4QR9WVN3L4&o!13w~|"
    "(dqb-2oFP#1SQ%dAwrsvH|06&GrSN<?e|V>sY>`i=TBcAe)*rfujb1?KR<r>l+VBjTQE2SBZ|Okw0@o05yQ|=?yWKUcyLHgMIzda"
    "?nW_GHA?(0QBg+H&1K&eg;6k1kr*zR_KXLr3zb56*cFMojG=OLxdAOQgAAv)2WPKvDGSGK5tp@X_()nV<#HYas8&VAnJdgRpr%r*"
    "lPuQZKs@JSuoAfwzt*(yqVMO9_0zvawJ9DT?T`(6SWH!KQ6+TeU==NLNU;N*c^oN#FbybGXxdUkow~w3An4csUJ6wmabanwOsD4S"
    "N``U1ZEd;HO{%jIFoRBXDms1rjb1h@#hLZ`c*X0NJeH<&{g|j-Rbo^>rW^g*Im4k18sPlndNqzucq8nk_<k}D2Z<K;RLPfrEMv!^"
    "VWJV1MM)hJiaMp|P|<eBA~wIZp&`+%GO`uKd;RH1?s%8D;Nl-O%u^jlHEt4aT#So6BiQxH%YNLNE@`jg(_Qy-My2UqFHCehP>Sh&"
    "hi@#6fJbg=y()5(y|Ut}RO8jNT#A-?TZ{}UvTt^->NSnH&wK5!S(arBQ^t<&X;sFYHh}twE0s_5<URjdZL;>nG*yk>OKg=&IWr37"
    "3Tf`5Iq2o7#&|niGYZ7e<fjzab8800MeRj<X3c0J#;S`J#F@>jYaAa$nf6*(wr%fOefavvq)wO4O~Cx)o?Y-%gv)vT2BfDO!nxL-"
    "v05t@*RyhQ#58;6l-H(TlJ(a{uN#;1S9qy{)ulfM&)hh))kDmbkO(9Dwu)R|zzrMiX&3$SfL&zU(=;O95WnMTLt?=0i0MQ=uriSO"
    "E>A5nMBJJgyvuHf*v6{GXocRt87D=29h6~_2uV8#c{IzT<Zxp#%JtO2J3Jg&0s0~pq2;Ec=TGFOYOnLmBoK07_gGOTfwAh$O+PwF"
    "^-;pyV4w^KQF7u;=(aQ~Sn%Whm!}W^_}$&(!|r#YblCf0(7G}}ylMQjyJ9!o?@EO<h^C_K)Ujn4Y}u5%Ca$DiHe*X%*qmeSKZ+4)"
    "PE6#kk&|lad82mlE~r+@Hi%6T>ZLZcaZ!T9&h!nH_&yD7W7nueEstG;gLQpF-zRoW*%Z6hF&M`b(^**a6TC<oVtnkbo1V3%*)&*T"
    "_8hc6wI-|Vlymp_ANOB>YTM=c4vhZTI^`&vt@jlGK{n-srW{7SVN+Q`J#WFP%a_?st0HS`oCS7tQeflLHFXYl$}unLx0@6Z42T?q"
    "$1a3NMSqyq>QU2_8o_cYm!r&=7#1*B82@&v82_AtZf@E77C?b5l+(a{lE~bVGUwT5WmxBF0{6h2+uGqfM5$ehoY!sV-PMwl`64TE"
    "&Y#Yn=X9As4w%MRo;!&LhH@yF-C{v`D(EhCh*IoZb$Ww&->ok%lER#>e0UAM<-XushC=;d)|L4m*@0*d(OSj5;#5XLwoHQ|j~1P|"
    "pjN<Xzo<#uC)TemleSN8?hR8zx!ri91_awN&93(K^d`3^LHBY~i?ovaV=d-`HPy4*YQC)h0Bi(ZkCj~uNRLLDPv`+zQqNpi(>%RJ"
    "z0%_LNi{2Nk#raL9A<!x7LW_jYc&P11EH<;p&|?7wJJnlc5XvvF$n(NDp?x!lZELDcf8#`d*dnKG1t=_t+0u?MwVuphje<4iJlx}"
    "RZ*t}1xlY#l0mt#k_-x8e=36JYWed1zHY9diDHiK3Zd^!6*|A;r~UeCNuy>rbn==CYab0$_IIEUEs}-`+R(Z4wvK}%7LJBVGN#(0"
    "hMA8zY9<2DU{LrB^g#S#4s0$!OVUcUNl5P0EmT%HR3Uj%=VuVuU84s=(E|aQgVTCa*VpXm5d@4{s&!yeC`PnjAx+8wtyxT?4}^eM"
    "*oJn#*oKgU-tL0fI-LQP?~!<QPSefr;n*p^sQpQ22!&?DgR)fK%xgcb&gfZpKpw@q^LyD%{p@d1f-00dXL!iaj;l1E5Av9jlpuHu"
    "YhsbR8(}=E$Z@m+El>Iym+XBV=X2D1LJKOc^fFwB)vxhR^#s6V&)B5d3#oXLEld!$u$UQF52wakL1)^dyp<-3t6fbaUW_<j@z%LN"
    "<hM>8X_MGxk3{EcA$fG~-uiaFhdl2R8=-~LjiG#bkP^grs|E9x#OVq^!2NzM6>G^I#vkwQ>7b<Jmbjd;L|{9drD>T#d-s}crTl4("
    "Vl$>$?j*w+TGjZCfIuxW&u8f)>xSjrl#-?S*YBd;VkE6I*3pn6=e7_=UERh0diQC5`280t?mpi=-R<u0{`dUh@1-8+276XW0<vcv"
    ")HQq7PL=w+VJ$b$X}NiP`tr4SvWFsY*kq8T$$NQClTnuX8W(hZ+|!*b+%>kNc6IcO88sA>6XxU6(A_nR6cX~4T}vUGh9YUG6mEp("
    "sbyl1`|@*X=+cvtHVRADQi@RrqhAaOLW1KpJ#=Lomlb`7dR+O5qJL=F5a1+L_~2=Ob%RWO+)+t|y>2Lt#$}v^^6TghGm@1VN4INf"
    "$dR}6S42)6?4iiYY`sZ&2Aia1^GKLwrKzkMzwt&^PLE~Pg}d`#j^|Z1D$}OBqhL+<3{S=H&Yj5izka@(pXxRuK@BG_(BZ%<9-t3?"
    "U#lySIrntxTF?4~<gI_VyJj9hod-AuuF*;euKGybsXp9Q=<QS=#XN%bPHx6X`yb~;>5gI28+A+f<NWZCyTkm~hu!DLuU{UXKK$uN"
    "9R@#t{`39r>G<X0(}xe{%h&mHoefI*u~UgwN{&LlbaY(eH`;0y2x&}oZD@L=O1<Cxa<)tVJ>`38m-OiQyew^H*vrD)(J_P^aQcB+"
    "E9+Pp&<oF*fh#~};?RnFwkI54V6{-soh=tht-x+j8t_7}#7!pcFYYOa`YKsBJS{}WYrq^fwdMp43;hEN*V9^xj+%u(n};k+w1=MF"
    "KnKxvG!wFEN)9b1#)YzrMT)1Y3>~g<vYv~Rb*N3T>NKg&5H6v4cTLo>08{F-g4Jh8eO8hBuF~~H)%BuZjN&($TAvf7zH3m}r6@4$"
    "q0lWLHH*~qL~E~^F15Q#m)e!8J)VBx(Hi{Vfu}5OouGOvN6a^JzH4NAAMW3FJBKAoa`!ZU`12qB@u{4;MzB3l_MThX@aNUKXAnUc"
    "3BztihAH;*UP?v*Z^T+deqYi?yD{yJj>t{)WQ4apMh2oZTRxywiU!#`rS;I-9JR6T4d!tKYT`BPHX2?Vhi_4{w`V6;dih$-CVOD1"
    "$YR~%X-iV`9dY-XZMH&==3=SWCI`^kW>hpWIdZN|b~8=QuA8shWObdQZ}m{ox0>?by;ggZR@FdM+L_|A>I@pxTye}au}s#|Y3r|H"
    "hm;me`y$qlq)vTH-F7mpZXT4|t96#$za}B0r}@X-&mSLBBs*!<!qrl0=ZMvmt|p{$w`4=7R$42sJhjpit0r-~uP+_d+M1Db8k>XJ"
    "0hN~H_+QM=T|0^ZcCc48eb%Mru3<!!j@;^;WXNWK*kQ0~$4H9a?pD`OjV+omzd^Y4l$2lf_T~zVx=FcGtx;EP8qSO&OhXb0UOeb4"
    "F6px@mvm<(dvddT*BzhE!YG6^sF7my+NLAQ&H%1Hq`47KSjoXD)|P9^fn7l&!y0|6GlbR<au#qr%cR@aJnc5(jv4Eo_M#DzGo6sU"
    "fUXqA%%>w&*bTiJ>c}KEm}y?=SD$HKja7EfAB7h{i!xK9qt?I;U3=!){+(2P-}uS1#v3_qyfIyDYZZvWty3B(IJ)-M-9Yc19E55X"
    "Ta<ThJn#;B&dwqqUsm1!{^xx`IIJjl1p!lge?t5qDI>xXU11zkH$1@izv6gg7%CgOu}5H+4I?{uObr$MfK3|3CJi+2Bd?>+Fmkl5"
    "I3*2A^A3nz-vKS&qHQhXIGKOYtWP?5z?k9O1dgfxeP#_<)y-~w<fF|zRbH-*z|gZKBvGcY=^8WNv6}fZGu*bj1bF7w3$X9-PBnmd"
    "7wr;g5LukgheJP|Q4KdfKyya_3Cc59U5FEN)@~vkPa9j#RV0)QCUmFgW2gThe`8=O9P&2?rou%}uG4x`rgU3{<oh)r-L+2ZO=!hU"
    "=}l<uXicCcD6rEtdegD$P0`sb4#9E$e5mm08Xb>v+F|cHgsuT%p2=cDZ#Hh1`oN3@2=YeIgF{o?2<9%N;adYSYecq^z(9v%YeeG*"
    "K{hXw9l>rulqS2Kt;<r+Efa&`Zf9>IQX_bn2ADno&Ir8$j#1O>&4|=+&(*~D)rgeo3~wY-?!6k+8{LbvK}|p^(wm`R2~FV?EP6Wh"
    "B7J)b79$!879&J2(gvo8iS%YDSVB`c1&iMMPNeefDOgN&-=ZSb^VEqnq8E)Qsf@fC4wldq&t;0Lm#H>yFH?<;O!vJ^4ZjKPsYtE7"
    "8IfAYMe3$rq)xxRNF6jHRlP_X)E7!gVkC&0k!f>Z(MI$#MfLVFZP23#pM{CwQB>Y?-|4g=58jGM)$<5!P4v@}A=~|3(cVoYY7C$L"
    "cK<{^IRc0{U*(xAif3*p70$qJ8l~N<zk(PwwyT6RGqQ<>G(WmBhcx`|=1!v;d;``o>&G2)Vq}C0X<K$X1(ICFjN)J?->LWB=Qx~y"
    "l1pP~8fz)I@8(Wv6b>CGL)y?`(kOiWw?LzX8ra73!*j?np6^=V$o^=wR3kuN6Ctm@w{6mBB~DwkO(fK$24N*S3z~`0SQ{%tIy&F9"
    "rcp_+WHmP0$kP_>ki)SK$m6l^fYoo&HckY=XNHC0Mx&btSvG5&yMbAA3Slp#+Kt^u&cJ2^nD6HK94g1tp3f#aC!X|4Hb&Uf9>=C}"
    "9Gv^9Y3OrI@ks_&hSCG?=~{-Cr>Q}Vc?-?K7&(j@2#M@DADrngImYVucmW9Yu!lp$bM<tyCskbLj%hfFDB(y*<W~_VdQ+M4_I*0u"
    "fLTha!yDi*VRqxrWKg|NLtCU;df&CpWyAK5NydtIfeABKn(@#_tTNV6=;ypu?tL1n<<R-dM65D4M|D3(Go9hvH`MS`aHj3FjoG>9"
    "ur$_*_i3j)VLr$ZXT+Gh(NOQ-r=g%uj686+KYf&aL(#lXLlL8r5bxtlW43PO*=aH|QRXMl{5|<guHSX}uK0IVzMB!IlZmd7lKiGz"
    "G$Lf$=n~?T<iGh=zB6tA@$LtjMtA)QPO@2KMyGP*IObZFiSEQy5=TMAA!(&Jbi&x@5NL!$UfEhN2ijb2(NzeB!1Fs{;hCjtD5WO="
    "kbI|#9b(-wmJ*IuF&h577=Kg(vrKfnq`xUGO))~{a~=6aCtW|6Nn{QCT;`m0vFwL=H3d1lET;^{Sf+59yRNsM)OIGk#0^>~;}Xa`"
    "!$GD!^p*<UsOJu;Dnj>u1Y&GlhECmIS~heZ;fWxpiWYnW$wU)T(8>Dp+Oa2ENYz8hz#}+w+w%BE-_iE2mN5oHnxQil<3z=&r1^6M"
    "2f2PPSL}hXBjGbUC{^~$4+Z#b@K58FXo2v`ERQatEd*R?kn$^0l9O6Iw?(p;Eu&v2MJQZ+QZN%M+?70j1S=5Ia0LEtqDy9sLI{`7"
    "opk?KwBP>A3F~bnWPC~Xq{TODx6K0`xAz_4_Ab|T@0p4!ev|S5ffWpSkb%Py1Wpst?;5JFT6FTJ$P;fO;LOG+YSFD&2;))HZQ}6U"
    "k=@mSMILA&X~jtFI2TPD5S$c59?67_-jQThPR~78<h~p%AQ$bo;i*&v%gjX5!qKDz9?ZukWdy*ZE%&rcWmbAiC*8B<Vyax!690Bm"
    "CxS|aT4I!!?rly?(EjYijNX%@iJ3VHw<abeD4eZ{35AX2Yjp)#OH3gOW$uXQ%4n`4a-0ca(XndHE>HW%rF6T0?g;38E#AIl7XiOS"
    "Wo~N#03E9qmK43>2<7csmL$i3A~pRLuAr5doRH8g>hVz(eHz`mf8cY6$(LcmhChOyrkMF7@;W&_dx1}7fk%cydR9xaePA-FC1Y1;"
    "`t;nUPo?k_Q?a=<Adih;TSIiSl*?SG3L+|K)+&saDr$XpsYYVM(Ne`i{njs4G=8*H(Td?x#iR$9rFy}3hSqfmtovFzuDa$WX9&6z"
    "X9zk=x8j3-Zt*)^iyvz((O;8ZT-0)LQCT5eK=+=%g<#kV&fS9%+dW^7Cla3B^KAss8%!iC#AwgALUwz87I;V+?)g?ow&(AjJ=W!Q"
    "+zQoWK-Zd+=QE=U&C@%iF?Kon2y8`;VYqYxT0yPq7u>FG1il+xA8iDpYZZ;!<#ch)vs;Pzxow~4Qgvb~tr`-vT&6a|%Wds+Ry0e`"
    ")8AdY@<Iv2m1jlrl+H50U{A7{aPib~vynfsMa##M)UTX;uG#2ZxP5e6fs#zNmtXy?pwHeHoc&e`H5^Zw@ienkFBr239rp|u8!P2l"
    "U$Rm)Ry|w3t1T;F_-?kWfL10Coz@B%zQdNKFMP)>Yo3)npm8F{S4h)riY&MckEKA(O#+5sEL&+-rV1AZwzsZ&64daQ`S9govR`)("
    "kMoBgpUmUe-RIx`A^e~HFHiFyKgpoIJ8z5#mu!L7%AoXq`0)2=Wh)b28l5k(Bz|C_7~5CD8_$8uS!b*q*|BWoUF>ai;j`T^!`bLA"
    "*qh<3Ojm-&3>Ug0Hq3A~(lpY~WsW%0Sm(kgyKOD8(y>?9$GetE&`M7q;Fn11iX0vihj+)2#(`k&R_nWsUWQ0f6^v*Z<U$^Nf%0G@"
    "I@?RKr;G6^qesZ&TBFC~hMr-S5@+>{h;BC0GgPAZ-qJHvqIIBpMv<XvmKN1BR9;z0&rtAIOUsp|70Df2cx4kNzg=wGHbLf+_F3IA"
    "z}0?PN87$Z%J@2MFNBSuLT=j<-*6def^%k-Q%#;-%~Qw9Ii{Mi0r6aIlXM?cz8mEAcfP3?`g%bQf1b{0^7H-1&w)1$Xwy&)%igey"
    "t!ebq{0?K7Ng7E<r)~_Ra~jVxcf!z8564h9Y^`hzwHgkBR_!1h`g#=%f8Kyii*LvN=h}|PFglx!$~LM$p4UY8&Vy*%MW$^(iq^H6"
    "TrUqN#>42$iD7i(aq#UpXwz4mm>#x&-)=M7_rC{qVjz19cr83x!0RnWwyYyoWApfNWQo242EE5f8=+fSs7@9}w0obHHB&iPjg;fj"
    "3@1=G4b~sxfOo?h)y+fESFGIl_w7cbb^m*<`;lG~{jl&2^3*j=6SL@hjHAJ!{%5Ql>VKv}DOU->NV|$oYv;5p<LpqoG7d-DRb=BF"
    "XjjoQZKPcpPhWkso8C&yW-4+{NBl||bVr*C=6(0+OuAV{M0fZp*5Hs>+FBuc|DkgKw!(I?3R6vk3pimz5A+B`E%uIWo9TH>)APnE"
    "!O08^OVsbWZ$|!2<~5*bXY>m4`Yw%0l!T3cMz#LhuyWsbURo<h-0C6C4e89Sb#grGSa|XCXPxW0gv-U<rfsJ`tk-#!{bJX{`bbkj"
    "yzi_7H<l}MnJYu(if$}d#7pGrggNcv9daONUm=pqNPsIMCzEURe|t~4hB}6Fb&7j~ssoX0^m7}@)iL_r=gZZM*N$sqa23$D*zwwN"
    "wjV5J<8k(~Nx&V-(&DlujXiXPGn9_7UpDi{`DvdV1j}av^t4=q7V=Y@H!=t1S8-<i>r{RP%j;;;9;VgT&_+Jfcis40T7)ZKg6ss1"
    "?p>$07iy>g_?8NrPAAW!#MpH5EK2Ozv!(F}TgVTq=IB+g9bif7LAc69^1aD!O){N=UXJMK0QRm5x;L6B3`n|X+`Fm^(JPI3dPqfO"
    "mZHOo%#bC)`d;)N&2(lEL|4r5o*(UDo1hbeLIKB~G?7p?)4~pBV|s48`}FgDM{XMu8;Y3BJ-*hRi~#jYspyZ9IaM5&z`sOlnH*h$"
    "Qqfa6D7J}Yus%YFdTa@!OIcENYXD19zF2+v$MP`BM;j#4MnD?`W<i+&b8blT?>bXJkB{$2smjNS>~Ubm$2XXZj&C?|3WGJ{b~eB|"
    "nyPQ$&goj<E;_%#n?aCqnIs-5&uESGs|JMZHb%li=_?)pL+Vw~a<y1MIf(TwGZ-1kKvW}gLu)N4#Av6GC5NSjU_O;e2}siqRlsWw"
    "scDY79!Lhy+Nqaz8kR*#mc>qGWs@xQ+C4AiDeAy;04qdJ<)v`VqE!=`kxir|hvg5jvU`9<P2C!l-oMo<&Tfu2dW*rChd{Kd<L@nt"
    "Btz?^UB~*KyN%-fY5jF~_b^W+zVz`aWc+FVINd$|{mb3wuu489kAh=qp!FTmbeYEJ#2Z)c)KCXPu4z9KR%45vH4I*@VNe?8Rr|_~"
    ">7{z(l^Z?tzB^DuA9^gx{Y>u!kpZ@?0EX_6A<g#LpXUjJ_^f<Rh-c=L&&;QunNL46pGnRDhrj)_2r?vR>A2{^b((#bXb&-fYJ@Q1"
    "gnP*|zY|`*C_AVZWe-Z#3$jP&qBC2KlPPYG?8J4Bg*4N8QLjm!QJ^Ms(xIjf&Gb&Ho^gAsX(q1?x-?wG4^u@C<dm{bCcfRzU!HPR"
    "`Lkxg?Fo>7O{5_jPCtj{G=u*BeNSAioz%8t7O#EL4eK}wTXoWKAprfMq0YZfytH+uw$2RilP<az@$DmgQs-w&+W)r))~T*Yr=PWw"
    "<!C2$(cvdMh#l8ry{Ar2wE+p`e6<fpzO}#QG@uSD4&nLCwn3y8ibz49-d7@~3uzIa%MOGD+$o_m<4Jv7jG&oR9;)I0(Sp{eq}^DR"
    "Q%&`}_@(GWEn4Y~AJ?LlJw-3BQP9kqL1OcH62Y`yVJK8sU#A+RSc4L-XuV1L$lFcREw|Gq!P9iVwJ}A+s%FZoWZK`D$|~W6Z?2u_"
    "%F`9(&pC`am6Q^`I+WL2t0O!8Y_5*z^|KlfJ?vl1SRLbp_GM&Xi?^1`J5kxM%(SsRGN+|rRF<}@Y3e2GFM>;*Rs$4We-Sb28CpZu"
    "#GO{^+;WX>Ha$~#ZC<#gKVy5S*^Ss(ziVAd9U9eTI68`)rWT3GMa(3#=8>j4bwJ5*7C68~kCyQsq&<(LF|>Nm)D5cNhcw^GS}gsa"
    "YX3oRv9gx}zz*y<A&CY_cp)yC{lzoU#htL@xG(2^>l9;u_}A&~zNC5LzVEfXq#1=QGn9s>=axFsxn<J1vLW9(zf5zu@cCsTmcz-l"
    "!{)M4=dvH^QZw40n)=3YmvG0bGXBJb%-o1|LMmRbb)}g_E@2=0w<TNhu*vzHJ5`4R-g^B5`>{7C4qg*9pcCiZBGxrC*zv(@z|(nt"
    "<t`uj5l^-2$l8UlrKM-r48pt4PKoH8QT_EjUbHTcWnEe^jBRld#HcxbZNfR(x?Ea%WorEeoz0h~qH63}nrCXirfEvN;^<g)<|va)"
    "ag44Ur?WFf)h4FlP2m`GVkOvgM%DSruG$fh=oKYkn}|);Uu!x8&6>uR$^N2gS7X&eapyK-J`(O+c0LlxHEbkqkSD|q`ZdK3_Jp_r"
    "$Kp;5Fr^ujzDV3!mv*2TUV5VoNVCkt_4@3kw}V2m`MVSy<j|U?w*sface@oh<y^9-w1HFMJ8lI|Ij1%Pq-vV(+Eo+~r`%S+RrtPy"
    "uC7ijmINX>$H3Wf+5lb_e@V=uf86~NH1|J0d^z6T&%giUC-vb&MpVl1)}b&QfF?Od1GGSGn3sXr;{Uw+<^IcVQubkv=37c?dc6Dg"
    "^z*~~VF5ilmWmC1+c-SvABda{eI-3S&@~n@jA$Am{|RZjzk#(dMzVZn-bs%nB-Ta86r!HXsD4G)Kuh)WNC-(?O%zK*BD$^EwhKg8"
    "m0DMQ(Yr{tuVs~Z%M__*20`y;QJW51a8oYwQud*2&Lu6T31thPaU+z?MNgGJl+C#W($a*oh0nIzAkdxNAR<PQV`@x(C@(X}6O!52"
    "pV!fag+7y~14YWIBrmG{nk<vfSf;R7T?j#$v0l*=`SlyFSsa@&Ta(^v-#zV@RpSkL^?Ci~8HO!nV6%A!$IZ*Z;=4BzpY4gqrdqY{"
    "(@K*YoOK|+0wIw>>&n)%%Xv>>ACIQrY5e~e=GvFzG4K1&eI+gDgQs*6l-#<`%7m4+b%1zKZ@JK_LktbdTjoR6F+5<C2Wy@>0Lc6t"
    "!r+K+RxlwW@_1E<8?I#o0Rp;UlTt(Uhv}kJb~SMn*5g)p7#jY^Tc15*Hh->s^YeZGb3KkYa*>B}RJP`rTaKpXIFvWqry#K^l#Rf4"
    "E?Ta2d7<w)t;>t2%dK&F>6aV0A;Nt)3DpJOFyUt$3UJ57oPE9DNRo|bH<MH2*=>Q!iF<Z)F<j)??NFGZHig2!<%Eh}HX|{h<eprf"
    "iUGN5&%}VrT_gt0xVvUSPr0Hmp@!3YG8)ajps6rfT<7Zx)2gvBEqDEObnQi7lc6v-jzNY~;E<hz&lk71Bck|_He|YR(QU*s2ejB5"
    ")*$G;=N#}HI3oUV5$9+-ptBAmI$Hk1r0Qu4JmYrE=b8bY!*xENp68G~r9Cz|_(5=7+vo+2k9zHy7D^wwHF%L6v<om5L|iJEN?PMc"
    "yN-EC!=AIVq;2rNPF&(v^f|b+5(Ix)-mW7;@PdNsZxJDc9MIJwC2xpdu1TeuX`>oA9h(s{;6^PxOM>DlwfK&a!Aqe|Ged+NJtePf"
    "vV@sSI)fY4s9t8wciBs|A+sh+ikw;R7kxEG_JwHPR)e&yvL|8jlHUdB6~#*@y0odL>C^7GUh;_%cF@>9-bqG3DIqZ(ouDSp%*4;<"
    "BmVHGKm6zY|N864Pk;aP;p5@{_ka1rkN@%U!-xHk7(eBuE4d|<+!=iI>3B1Z$4fwZa_Y`$H(bw$egPrPZJ)bk`%o3mb<cb{n1LeX"
    "vTxW$l|tgTf}y>Vw!0qhYZ|pK>^7*NFKL!Chte*^0t^;nH@<k3>cK2)>$2@5IR@|C{5q}kb7@^Neh`ECVz#N(C;V9Ik<w(yZemGz"
    "yWQ(FZ@(+eGrhuHHVtKPMB?U)Crw`OdV{1-n)%z;`S3JPACLFDpB|f~UK(IM$G5gi=M%tnZHeot%*yGhoEctoymFpM58!pAhfo^t"
    "DA)t_Wbn$XK_oyGq4%Al#Wz(2T*&ea-MgJXKRx_XEG*&Yp6yAb38j%q8{Ce(IU-fL6f&dq#H5VGD7~|<w1iw)LOSW2d5OOIzNUp6"
    "Y~5uIYAHvA>mjWtA$Y85jFH5_nemhIpLd_9FaP}bc>m?;!#{p^_xP~;ohZ#r%op49JTl0=-OjJI9QRS1v1~N&zc|-_bNBgaet7u#"
    ">(jOf%qbC=Hx+>$1@_cQ(jWoI><d=~<v5~@I#MY*JKSougKKsH?ez(v`M12Yd)-jwEV~Mo3HWihkz*~zNcB}-j6&z-GC>?+cX%UC"
    "Ofn<vTguBc8;v1dHgd=n>kZpzUM!9bO!S;%Aj1=Fp2QKKsP$<8!TzYuXc&GNH6?jt)Ci0yq`mDBG+-Z49YU+NZmb*GcDzY3CWo&-"
    "-%aIl(VI-6Rl@*Mk)D?6C?&(|_sVbf3TO-biC+1wUV#|@09d%ma@na98HTPK-lXT<rlRz?TfEBZL_p0RJY{n8CF%H<6U7RSMRZu*"
    "^okU+bJ@f6>G7fV#!AH<w4pj^hqSjm!>npBRlKK-O_;t-V-*ZyQOnk2weCi`9EnzMP`cIn%rM5pXUDULIWCycx5s}ebLhV<pzOab"
    "+4w_Up~s2--M?kU;h-0_G1d^Dk==d0T`xtIJkSGE=R?D~4Zy=Skw!x7@pWz?dRJ~Cwjt5^*T=j2#i*a{lGdwj>p~qvjva8I`kiek"
    "E)88`7Wl>5Omu*O>Mc&GH$jUnGQfqzl^RGE_IG-nazei0>T<#lg2RiLGfGfD4v#g1@2DD!G@T+#BIJ0y|CfKAmgSKAQu)eoijxH>"
    "pc5j30KMVP=o&lt#t|Bw!+;&|t@%HCYQ1F}qeGWkT9BXK<z!<UBSRBwhkH|XBYIp7+Og;D0R5)z$f(#W)=vzv35{Tb;)Qt2M)(+s"
    "%o-6fltUv9tP%1}XGTQs*^<P84M#-ddCNu^k=F-7UOE`o0`sPeIC>qi7DS`}fzJk~-n0ej)q%)hj!ocm;cf4)p1U(r*Q=0bU(H$8"
    "dmQ;Xg(UTcr<O<HK8*|FPTH)C8VBM{=Q>Ey#}SgV0vfbkc2fk&{PLC&s%a^3?`_-$L+K>a?%%{WpCl(+*Fg_@IYHL5cru|rn!(7o"
    "y!(OiBmajmhs6lPC#2aS){qBxiCcsRZs+1{aWHc5@Zj|jDljC%2ouu-$cx$uZro15aXXu^1jS^AL%)o${+Sah^9#@3XCB2R4p1KD"
    "2o<UH2qiZ6w7dh9ZlUU3P)n~+v1g3sahUshZ~z}}ZHv%7?bA1~lQy~>LG!!^ynM@^&l9E+@<JFOq!a2{v_?gM&Wtu^bnXo|XY{JG"
    "txHkThCF#5YZPs(fEP|(kDxoRxcYN&1Wj;u{&j*3yf58Cb&e#lE{nz=P|#V6%w01<EHB;2?6|26$W&|*8SeAk*-k+S==_Xonp9+G"
    "p6%;AT|1Ybu0e1fRB8hOkwSmAJdGgxKeeof-&UCO8W#Z3o9PVBIYcO)!P7nnBU(tx?9vdDG_~N$8bJ;bvu6Nv4#Lt1$jQIX^s?ZK"
    "P_61|3+sqlM@MvTUS~uPrc~}Y<GP&KSU5W#Z|9pam32^qXw#sYQjpiw9cUTU=uyW8737FWEu`6QP)$jKfmt3R$67n8wM3+}>C;ZX"
    "&ZzEn5iI(Sps=({3fWnd4>ipVz>PvugKJ5s5<tqHN@z`UZ>Ly7BxB>|6B#weBkdGtU1aUnBv$72cPyz#2%Hd6lGZSox2Sp;*&WjG"
    "#Iln{wRU2*S3=Eqme>=d9TIy&jD>4fRo)M!qclEr-AHFf9OEDz^_-gK*Kw?{$GJ$<b8gx_ZI@4UHuF<HG+|#7fO7@VeMKfhiTbOo"
    "Cx!1MT0V{4Ds|w5W6G2LTB2n8_5PLi>wOUco|sg4YEmh&%@Y2Na*f=TyyqvDlH-XLUFce_ky11#h`J+#q12Eu78DElo7L<1l{uaL"
    "%0OvOA`WqGl_{k3TiP;1@z@ba)W3bYdsi8~Y0v^Fj_^r6XF{5#z|~7y*6u-BO0gZb|JPahwzkXZGbZ|wr8xbzhG`lP49YV=+vNf$"
    "SOy@z>*Cw4bAN`26182E<W*r`m1K2An6%adVL_m7A)`P`(UqlmS#skQLn4uomRx_Zw0xyGIBtctt>r7<w}AC`WoYYQZPzT8y2k0("
    "(Yj1gy7c&s7IZpP%M?Ax*O{V|tabbG4x%lIw0?b6LtFKR9*3cL{~WwT(C(S}ydTnBg9ft&YXO>@xM)B)=p1F=z*>OLVfGEI1!&Y;"
    "uomIF-Ga3U-#6hYKxZX?i}M$ZAkI<gv6Cz~!wFm#sA*~?0wa+9oYB~U;mGn#8YX*X#722BpNnjeIkaJ&1<wz1NJ&bN$+aB;A#(`C"
    "e_ui%{@?iR|6U*g@)R=^oI6Q^g?WVxc6gsMi4KZEL)Wy83qTcAvUH~#z^_J9i6g$Fn<{#qq3>+Jnoc#C0aTeZ8RRnS9ei}17`Tem"
    "40+l-Y)l*1q3ch4k$Jrl#WFR!nV~3^zZ!vqZqMqiu7Rh>i-+Q6bjWvsDoK<bIX0I0h=$!t)I`Y9Lh5o9bfBEXwpuoAD@^CPRW2h|"
    "P*p2q?z8RGa#W;r3lt?ych;p+sdODNxZ(vX*->=}o}qu6DF;*}va1KT7t-GD+>zSmxns3?)-fO5-5BZ4M5cu`Y}Fj$hF48N+Xrj)"
    "NzXK}mhs5r)W&&&<<W~$v|+8Vy2q`KSzLFp^qr+UDXs5g+n^-DuTC?tK_6^h8inZeA&auphf1f>{Q6G$2moiAAfGe|%5~fcc4PvX"
    "h0L`tZAmP^5S(NjR5ZL69Ag)|JW>ua7TjiF0ywosxBhCzM2%u*^Gsuoge>T$oHS13i18=yi_TCO8@hNi7F?O)dzxg$uTKSuxO2~E"
    "jR1EZcpRKpBbVop#@`Hq4hskt)taHo$}hpMb5-dZKB;tpp@)bhM~?_8=x*uKGxf@&{Ea29(UD$=8=gy2mAT~Wiy9}={z@&@o(E3$"
    "kObg20w<v)na=#MuRrtW;*n}rB?nI~UX2#M-vFfsj{ROcpf@m-N->5&C>`O3$8}eS)woU6S+R+H58k@w)oM+_5hf~lr^afkr|#52"
    "P2JzJnpz%-e00)2PZ&@q4agBzAoxtGp7uU<!;?mvI%{xX6sR3W%QS4!>Chfe8Q);Q->|D7<3|#M2n`G5GWpgtVuA{*5^s1_VwNwc"
    "O$$_c9|abz@hj<4zS7bWwVcwkj+ikF03r`(dYM1eOvFj6dd9FER{i=0-V*Mp+M_BMC(ne_$~|2~UUsw^wJ1Nra)gW$xP{yT6eRH1"
    "qPf8H*zq7D4UV3+0C}VzdxnUfx;>0>_^dZzi~)t&fH4lA-3E+t_zW8`#(*h~w1F`WpIas_h=_y3mmuU|;y}*q2spU01Fut!MS%k*"
    "qWJ92!6y`I?)s-`njx-#zm|Iyn(fnRpfVOx&nz3}K!==<nno*xG*}m#oTeKV&2cKCapon85qdKg4c~{jXy`ulYY`2&(@GN}d!du7"
    "(o}bY_<DLuEn?CQGG|&?@`olzWXOQ*xH-_{28A5X+mJS#x0rpHlMPfR{Hz-t9LSDu7=5cxNme$JP0mc)qS3vdXx>#(WD309uV~_i"
    "MneZn#SH2wD8WL8j@ASUCuCqwb&&;N&Ie*h>zLS?K_7)Rok3qWIk0;a&<B<yMQr3}Ah|O)EcoI&9vZ#4qMc%0L*dmXnp_dC#{rsL"
    "$pG%xW+p~~YJ@(8(d&G`Pao3YRSfSz`x+xCp-h@wKAZ5CCAt^2L(m;PX$99_$*mW$Lrt~JtMMyKgAPlgmYR%poBL?y1l~MiGBI#g"
    "8-FcA=C2#F^Q8#7`Y13DN`@h*sK_}CE28XztHBK=$3E#{DKLAqGe~G8c3zbH5q8;;`JP<}fZOwQ<GzoX1h`BBitU6MMV9UC{OrjN"
    "=8O=jYz7i2D43gXc6%!`1V%HY4jztXNSy#UVp&3!;Z8pPimvad(o<`3;P`c%P%6=IY~H#<q8plVj`Lj1IAwV#<wo|HkcPiDdkiY-"
    "q5P{EP$NbVWg(4sNZoRWROyfv&#{W(!gT$deEymF5=LC>e2gmL!?g~^;k(&#Fb?0{mV+_I(18sH<M17~9E>rNPE-E7J+bVCM8Dx+"
    "T$-S{2g&M1RNA72>9i{5XB2Y4Y3Dc8Qg_4&{HWCuI`=qU1jnpj;_*$B13Hcg%PY}6B)sKiXdVT2An}o?%?h;T@hs}=TP=|2(qEoF"
    "Q5!$<CCPJATmEjjsGw`2y}d4_pu+8YiFO3E<z`y!#XuRY&Gxn@ysT-^M=a!xLvy`wnT};M&|pU72dJTq!eO%<<*Q-*phm(2k@ak;"
    "=!L)t*+UW3G+QZ8Ze=(lT&<$!hE@4AQs3V6Gm<!{cT>+K7rNE9(pUj=R0Oy5<-;LHMciI@HFS15^V=G*jS*#+PB%}J2u#Aw^v80e"
    "MCwdg$;J+`70_5e0!s;L_yV^%G=4-F9+DKp;rvbBziKpa&F9WV17nUS*op>5lTfo+G;m2m(LVInexe>l1EWD|VA1M34)>vsHuh-J"
    "Mp|W#R#|JTaRx~jtQZn>qLnweI;{j|c7bemS$m|^=phwj48+Z?PpkR-Pn?*G3S3vB)vn32t9i;Kj>y0*<7NGQ@)qHYm+KE<;N}qV"
    "Vw-xQuh-h~&!PGGzW=!!GhU)~ZdkS(GG3zfH+YOjGI~0558ccKJ)XJQ`S-SFF6w4@=YHm*Z}Lpt6mUWg`B+1u9TB;PG#pJ2C)-tZ"
    "=<6L)y`rl+Px<+=|9J{l-=4WHVa;rotp!6i1lC>cZg1*3)6gG^cJ8_cxysYD92Rg>bJy9SBU4C&q2A-17#l5}YblVkIb%beiInu`"
    ")R{I|fT}YwSYV*eIM5??Cep@_)ES4=%}CGRahxR7aYD8IHd}i{`3i1jcKNhvtqZ18Q@p_8g7NtlcvB0;%OSld#&Cksg7MX`#sS*4"
    ")`X|vu!A+>wH>YrpYW`<)`U;oC|hg78#`PRk-&ak6Gra8<C@s-%TQQi@K_9@)cWGBy}<>MX`G4$c|n!Il4eI2YVYs{SArj3nY|xh"
    "nZ3tN=&Q|@z{5?qR|3lMN<ceY2?(Q=074E|0tic2g4N$~B^)!-PG}TIK9RIDQnHgH$MLVpaC4SHP-cXY9MW)z<&4nK$r)nd0Y)eH"
    "T>N8%r1PySmQ99a=&G`vSYnAOxFyM27$J5eG^kz_u^S`2_E553UL@J1)v-xiWe4K+Hg5no79MgCQEjO38XRIKJiG*!8!<f>ZVC?@"
    "OkzdT<n2vLltbutMAb}6y4+EXCnf5OCS{C2XkUA<Bw^?2#NyO2f{jxLqy|JPqyyV7GRfomduwiQaGV$qj^h~rmhKoqwI2^o0_1=3"
    ";CR^fiZ3GsXSm2i4xn~kY68ZB6?#j;M?Vn04!1wmQ)?yR>xCY0TlhNqr@vhI@n?4QUK|tQ#vZsso01mM1V+xa$qKv4LRM?Ypl|LC"
    "JT%IP@r*EhIU1ld!iw>Xu==7IVc{e(UdZ9}i3J<eVE~gI(tH5}USLtC`|{arui%*EGwAR>^VsF@uw2XOU8IT(bPF}HSXF8xGL7u~"
    "wBto035i??^J@Fh-`=drKIjz9p!6_$pu2vR)a2WH{ECf&;UbWY!eHqlkVAzbq+Oyg#GkpryM9c=8x&r%OEBRzgg%a*Dbm`p@GM*;"
    "Jhu`4q)M8*LE(8d7M|yawPQ1{;R0jAV_aa*7aocYf0R1+&<v=SV;Tb#S1R)bksuB&lrRGp<(PJZo1Bt*I5w);F+82vO6lR)M2G4N"
    "#ztv5R+f}DH>WJA6MBVeb_`D^wmP9#sLS*UWnnmVm6LSp&SG=wZm1Qt055NF>UvKBDl*bHS<MP=vDLs@ty|8qkOObA+0;?H;?WbG"
    "r}5QZ-f2?5rkcZWUouOlpH7#rYA9ID+e^4~T{W7r7UnQn8m1a^kf7<zTS$I>Yew79CS}H3UWBW^wJk5Yskio=grQQ!tUbRS9GUSv"
    "WH9FT#({6hyVaLDrgbmkYto`_QPi{=cO6pQ4PFDZ>pfKMZ^`+ieGkjNrr8@a_k=b<&qP(HS_0gsFIj6+52sf5G8~~@#WV`Iej_r-"
    "IQ<L^wRFaCm2|peY5wNM(@5Pty`{gI!)b@CO5EH|Vw7XpT3L^x*jgb|LboVma-jELqcuUWaL4cXR%%d}UTM3DV4PIQvZjm~uNz}-"
    "Z|g9YZyif)XxhVTm#iE3IL9<xVOYGFzT-gcrqZRP>enYOe)Jly;~!XWyu7^uYODjt`OpmzsPO=SB?F}VcO0ODFI@tEYJkv;2MBL("
    "v$lep59XEBsx;e*@tm_MnknyfULU{X2u;V*r^X~QS00CY*|BnLf{$bhH>V(2%6wJLUUeAsa33t&x8)XFwzb=Av0Wx69Pm4K*kS3g"
    "u^nm;as3P#lA}qp4r`YzjJxY@Z=<vcS-hOjPBh3TAxAR8mK?f8j*dBeLrG3&Ja8MXq~@#`U;xd<9N4p<MN4Z}efuI?0Bs+1#@Xo1"
    "-+~gAi;3f5-pjkBW2OO@R&^=gkn&Z@0j!PCNhmt)xBWz3OIk@)PlCRm+R+@o4T=sqjO=S+(u`qPEgefO-zpYqZlWakudVN7<#{ih"
    ">Y~*>FT=4BUn1Utm*IPs`5n&znsdniuu>J~94r>tS+@ZvMV6Y@Uw3y8^F+AdA~#$}|2W+}{{73{=cf;!K4p&iSi0NBafwN{_cHH="
    "=~rM`o?c*w`d(&)mnW8P#C;zvDzC&Fir*_c62HGe!<W|^K2=rxnm>_RDt;qRh~K!e_zk|L_^la=-@4lqzf<GG$vZ#X54{&B#LuA*"
    "(z2;(@Rs5SJrqCK+Y^85smW%4<EhDJKjK*Y!1;fe_(AwL6o16CABZ31?L9Pt5@Yd$vP1EMf_~Xl@oU{Lo0{g{Qv5~^#c%ZOiGM@i"
    "Dmo!lgak^kn4|h)@+jgcrm^^Wsc4#0Bw_-<d`CGbQ{><nHXhNT_qExKza6GZsu0o|HxNzdu=m{@uG17mKfi05?$6IsCb(Y_HeqNl"
    "ju%BD`@OA2ftF4N+g~U{Luouyd`YVA5fReAePvpIXGw46_ni9sGW9XNlu#bkg7;nQ`#Gb$y`e(cZ$fn-QfOwz)`PwKjt#c1G+4=#"
    "VBw0w1cmIH@o+HL71U-3KonD9JPi#s<OLn``$@)%Vm`*iIojK`YOAg8Ub2g20WFWk@j;{$G4i3~SPBcz?V30Oq>pKEgQD_g8#X8="
    "jRN>%8ZgTt!7B`jV0$K#_}TSLB=NKFnMmSi?3qZy=gjoZm`LJh-7}HI&z3Wh#7}Mj^_G7WCX4L+&hjxE(#!zYJEr;0^M+b#q)0Y~"
    "Yk|LGLClbuoVu1CuoqM*lp0+fLYnQDfG%l0R(6$umK2!oK!NFEDkl|{XSQ}be|~!SB}37L+=f$$CJyD&Dx*(vfX56#P8Dmv<0gHy"
    "rAKzlm9`F0g1A0KD7dRxX;ATj4VPoQZdCJ@g>m4P+-qcH6d1Avgk-Nzu?2(-Kyfs};ru<7A1s~Xe%KRRG%&Qvhcs$J(GJcHk^JY~"
    "=jqEoKR(`ndHV2=-`zbv?0#1zi$h9)nCNaz>ynuaVZD1F*~_)e@g<vEm`r5w>q$%=iKS$*XfNK0<cXLxDJ9&T&zh7?X#28*P)RBr"
    "OHy-)Fm<4kWLA!sOVY^a;Eb0|Tqfv^=WL0RvsO)Pi0my65jPEx=f!<#wi`k3XH7@S6s1;-2U1VVNidaE{~Q7#$hpCvV?!)kZVc>r"
    "2I*hXp_J%3tjlqw5^G%6gLmdTp3{CV=d_ZlRjHP96p}_&)`H?ML2MBzC8%b^Kx1O6xn>nbi2b2&f>c_+VAxgSNqWu_Q^t=1CS<{G"
    "e-=Ax$nM0*TOg!ScfK8b$JGj|tX4%)bBeRR`7NEv4sWp8UT&b#R!L{7J4%tWruhL=XGjAI;7aecAxV#7Vx)rG3$+Ue;U-yC9aW^p"
    "9-P19J>5gTr%Ns5rd6Ws09v@=#-tMx8n;-~A4+}AzN96L^(3usFGxpf<)6>77qaW|j;|9SY;|Mae<KvZRlw$|jbEo{m4SfMyUOGI"
    "G$(6#`An%mP^j-IcU3y##K@c^b$-Z64c_VR=+5mYT^nqk!6g#%4NYhv$@Lu4(_NY%Qszw1AB<}nF_iC)o*In&;mha8FZZ+g&)vh*"
    "@Bj4UNBG<BVfyFpVOGEY^5Kt*1myp?JAV1=!`)9m%?}?Wst+H`)BNq}!;eqW?{|-PhmVg>4|kt``uLB#`JcZ(gwOI2O8NNou)BMD"
    "{Qcp>GKO^%%7#78UJ}2%E=&YV5`Ws(%dS-y5H8Qi?9OsL9`yPkCXHxbb&v5`x72KsyITeeC2xu$1zON^OaxV>;Kt+UXcPrH3F)5B"
    "$%Fkave!jHjT`~CgGJ>t(WF2*3f;7JCv(-MnKU21OK<F<^hPabY@RXmM36J2(K61myU)w0Epc;YV~cbK<Y&tsa;QI}zB;k@GyS2X"
    "y_eso_p<a}FV^$*Ib23lv9}Ss`>tFVVk`({#U^hMAq|>Ev7-XC3+4BhpUV^JBE^zMsE$|Nf2M-8o@G&jCZ=6H3-Tbo&!Q-2xpCaU"
    "Etrs;rITg<jf%+mv4|XW4}p0%Gd%1M$xdxNMQ_~gzmH_<Eg%Mk^lvcXGc*q(;S+YB!ifau_L|6W)u>Si{zuhJgRpsYL^g$iFNCy0"
    "^^m6dktrm)A8@Juzt*?r1HExu$=s<A4M$<fpqMxHzQGU*>9(&z8dgWxbdr1SJ;}nGk!jk`sS(zyj$x=wWxL@Z10^Y$^?tt3XK()O"
    "PL$>{;QPZ0gFn?YWE#tqBl8S>wy>EhGhY-5$5u@HKeWBek}NrnCHO0|oJF+=UwDa()TXzyoPCJByz+KMMnuJ<tE#_#NH<e+!t{_d"
    "H}~+&#SJQ{s&)uM3E&Xm{*>jZ->$X<{ki)Y?|C5a7d3V6llLY0zQFVYA-~P=zsa9e?GNNeGGDO5`f)d(`1|R|WBG<v%fI~f&tv_M"
    "R_Ly5%aN`rVK>BL=Z)b9%g*nR_?kos?U3xYO!#3V<9A40w=qwbk*VF2j<T=Ui#fUcy0@e4dfm-#uajlEuWG68KlW9}1AQ;#hi${e"
    "*NPm2UvjO;0e4DF@#7PBJe|Jx{Z88!h$#=ZKuk2+0^QQ;!!6J)tv=oYasTB$p5izEtZi@8jz#SEHY{#$!|Yb8^`C8iWWc$-4a@k$"
    "&DT0?v%L*#9Pe%TTIBJD(BYeP!QBDDUX9g-)Bk$4;ijdX^cenjOS`PCn}RWSDowjDAX}e&{b=9(lWqIS5_}?U_a$$s{J~a50zd9c"
    "BnYUg+1edn;g8?Cz=cGg7d^U1U$+Rq{{9~wE%pB87U$4E|M>Y|{>MG3%huzg9L0ZpluJ7H^r_m(*ZjP<=Ku;x^#iNk?0`Alo8#zQ"
    "WxZCALrBU;jhO$~c#|K`p>ay7csl}dT@<I5p8wx|{_o%Z@zb$xI{PnNI}fq@HJszyiPNROAM=NAN^{hQ8%jQJca-=9xWX7*5C|)&"
    "AE*MsRULzC5rS)F2ChvUq%9r%2e{?%fCb-9+tz;j_)fmmn^$oA7>iz=xle$r_q1gba5ZHJZp)&+1Gi_Lv~1}BT+K8DSFa?)M{pYn"
    "ehjXbNt9lDI?ze%0SmiqP=Gj=Xo`(x-%GAu^A$e>?mc_)3|t8qT-nFVOX&w{gy4cR{vX!}f~z_M*U|)B>*&X)!y^`_I}{*p+$2{Y"
    "B-i@->QitnrZu=01%lfWg73iXgIO){Hvrc_jm`VD44v?HEu%63*Yd=zZ?`S-72LBtVDYwXA+7A!p`21xVkJ9psXPlV*%RP$!QfW0"
    "-+u!7fkF^m;W4;ZlW_;GrWv@`9o7Kc>kjJ*?m6%S7BL++EDS8f9k?l6?YA|!wI?sZO(8}EZffMw-P=e%FeLzPZO$Wb>oo@8rjTq5"
    "ZVGu!F{>9lKkGTuBe-<fu*my`D2E&`Ug@TA^>jXiF6AfCCB^6xDC(*GKsJc3gfY5TFUbyF;TgIbCg}Fjpfi_8bk#O2lt!De9Qzv@"
    "J&A6-hhZk@#y}9=M%3HAj`ag0BXnbwA-XXIgl<fEf^NLl48-Wh+!@Gc%a7<Db;BYjpmw$DhR~B|QY`6NbnivrXXsMG=+b_3SPuO_"
    "&JbNLV|1^Fg?H#mn4v3Wg06J&r}HU2qI;1I3)wHl_WiB!##4X8Yh>{mbgevru0boUWiZ~Od+Y`_IvYT@zU>g*I^PK0MlKtpTQ85%"
    "ZS1lSbl>6w7Ii-Vb?XS0A|<L{ey15ye$q^<PhOj8wG(4>3oz6ASxzJnUD7eS93i?~X6Uj`(3Q?iyR>A(9^FD47LwtHEHvfN-%#_j"
    "=&C+}u4Rm_0XwZbu9RA~S%7X1Lp!ZrLv~uqabl;XJYiF(Mj`q@x4b=~E4Sl?seZ5ESM6|au7d7{`AI{q_FNlkDHmv{)poEy?DsC2"
    "B1D(c7+oTWF6j(iP7`#wGt@3}c|`Y+H!K(|MagzJT|BxX&!Vg833OF3x*)z-`mbv?h3MMQQcEQuOD&Z!vDE6-v89$u>@2m*;rxj1"
    "`Nn>#9rsHyAFg(AFEb@QX{x1?)}~r28JcRTrK;R9ze7K;AXBY2^BCP?5M4?$bcrYEQfI1N&Zh?~a)=uij7>G~WJpDxHPwndVX76y"
    "rdrFkxC6IeLdBq|R%~pl6@#W)3!jg{r7$toS^)hH?pt_t?B<PRky>uT-OsVAk{(2t;<Kh2r6)`^O4wARwBH|6>IY_Ms!<u6YE+=9"
    "MrCHI5lu`rqRv!%%a5MjOm7<&L~uj)D7(bZnrb9Zm}(^0RBPe;9lE(6sL)hv+3kkt8Z_1V;`RVto0w`GI#cb9A6>gyZ@%5yF#-2u"
    "Y<a?*o8cBie*#^OPnc?)u&LH^<L%Hb{lE-OHO^yGjWaaWxXes7E)!FYOJ}OR*&`PDc*mjuQ!VTbVWwwIwZ6Xl7+uDu8q0ovNYoEh"
    "XsX?U!WdnJrW)(aRAZZ%YHXdU_I7%7?&iyB!@_v9WpJjNglA2)77JaXD-oM&EeYNZUG4`aXsSsXn`)AwsU~@5s@?L)VRWT*rrO)v"
    "qj$H&<Az1qFU5BFaEC5EYpMx7VX6sZQ%!ikKcwEhD*{cmTXHsxu0T^wbY`lFPE55H9o^8?kRIK;rEKn9F<`3IcRf6ytKnHwtyRZf"
    "qN@>`YOPZB4&C0ps|lKFn#QKuEu+{Yx|(LDn&yeA*21G7=+dKmx5(z+Z3U<IhHyHhYRx%x%d@7M(i5hd5;oOZ>F50hu^-6LRJ-ND"
    "!srS#)l_Dtn##mfYw^(!boJ4_TMnChSGC};+9SI5tf{8<gsEl$n`$l5(+=I<z1tEO0dy^nO|_QK2%u|eW~y15m}-`+L-+XT-Yw_N"
    "z1z|d0T)^Oi~XL#%Cokbl_zX9BW$Y~fem7B2pdCN&3J698ADsmcxJ1aOl-AVDxMp<mq+(*HRU!eMA4ohA1>ZjGkw-pYngS{=o+@w"
    "%=R0^ehsyvrU2bmJ9LC@t9=R3ZB-q|=(f6oLv&l&ybp9^e01;9b_S=_kK6woec$h%N`J%rq^*`eitdilZ8bCyx~)>h{&iA6kQky%"
    "GDepJM3?gnU6u*D5;}DAqkEUQY*+{itCjkfdf9FHI-f;X<q32xVRQ{}t~yJ&B|Ads#xS(iT521FZp&3NMmNT>t=2L=bm;P<dzZH2"
    "G%bSzwuDOxZ~YC^leStrnz}|eW@xLm^LhK%>DN#z7>m%QI7XKWM3-cSF2@PFTsm~^(Y;Hjv|+*frI=!TD~G0OyBi8Wi>}5e&{f9h"
    "g2Wz~`hg}8T^rhJje&yDZN*&2=%z5X)mnVNL-+LP-leyjd$&d0vFv&(PK#PTiEc`3TP>#yZM7Ep*}o3=0}Ha%nm>DtZc&IX#TmLp"
    "6LhJw)#BTuf0wtTV$Deg{R|adr+1TtXVDdU0$mLlUEOaGv-ATkLUb*S(KUkT+Qe3CpZhVoxl6xVt;8L3x7_@@?X$K|oKqgRyG=7Z"
    "32v3$HMluJQ>~#3b};?Gj7+uqH#F69F341?%`^jdlGY%%2<Zp7^yuDYxolVvj;cv<+ufYGJc};d6X;68=nB{$T0c+;qN_YcR}G?T"
    "X@;)x1YPS)wQB7?qPvwz%dKGI9^Dw;9?&iENmH%%T$^gSBxtJD_Wk}ag??a0rdlp}XsYFsk*QXjC#G61Wo)YD79ssW_xR|<;j?X6"
    "l>Jh4zviaDpFowLFe2J%XoxB!FLOUopb=4IY(x}=Mnut>5m9tvL=@|ch;(^0(Ijjp+Iwhqr*6Z0%E*t~wUfoqVN2nOO)dqz$)&je"
    "vi9kMb31_yu%$HK<Whp0+>hF22wR#Ijn9<3O>PdS9TwX*td%$0WzJETE+^AX{GUJ;$iJNB{n$nSWu&Lq0r5MUKVJ_2`?8%G%dHTZ"
    "KSq{`6FNp#+w<rcS-r-?V`TXjamB~TGTnWagJWd5or_)znc|NQ0j@9iJ{B_g(IFdubjaXGhr{fn!(sB#;n00_GPV8Ey$A+8P?j0^"
    "?B$Rzn$<}hr~d1679HODK-<27(-Yqz&iFgTfd0$9+ohdw27q%Je}}lh?@$Y{P5`ILcj$Ib_y)Mz5S8taS!UqIe?O{oJoV(o%&eaW"
    "T=Elui(<e5Bba+nOgl7-0JpIhkqvqgTg-I~xP*xpQ9|cM%*Qb*+rhIez_b5;@a)Y?`0bSHrvR7q#Gas47ejyxAPIBtoRJLo1d_*l"
    "0x57$AZ4~EkTTg52z7gc+|u+7P}vTn)e#9EI?=a7bbxdEJmCC<uTcd18U^r%x%bz!N>~VR9s3$Zp|7z;W+#B##Mda+`5Nn1eu&C;"
    "KrIXK|JR@LrbjQ~8tl`6w-QuKz%}BXnF1;?_bwdGaA&4@yff1bcV;bEI|f|KWM`(O+nJS?D0hI${m@z+!pPmwq7<k8&cvSwoS*PW"
    "Dr1kN0(LR?UL6(akyIIbBvqkDvc+#Ffa}B~d8;mT16;}&@a-U5Rum>U#EYKf)Qh-<{At83JmIBmwR8~T1{lZOyLv1^FQuiim(mjS"
    "Qd*vQDJ@UDl&!YR2jYi3MtnQmmaX7p0FV0=qwsme=?TxJG4@;<U?Fqw{xN}`OOvtZ(gb=gTby@-xK2Emrk&@qoYNTb?Z8_$6i#@L"
    "d$!_)-K|YNi+BlP?anMAKzC+s-)~v@&<~8romrcQ?#yy4n(}~nX|dlS;w7Z9JF|q`xicxmG2+`HxH_buLvYnJZa=xZbt#`myx0?n"
    "Q^AM>x-uX8flLr_<}u=I5OGN}#Dyn_OJ{9T4ntJ#2jfZrVTVFV%E=wwD#7CC5x2FuSz>_ZW^D)N=BXbTk-1r$hvsI95t*B%#fZm<"
    "$22xK>&4F8BzhYoz8#jULv+NZQ0{M?KW%T8Sn?By7sZGJS~H*ffn*SI4r9bQL&TY9h)b9tE}gwedKn|W9iXd2;IVKz98UdqyhNqX"
    "BW~dd#EmfGfa=U$h@qr_49@aUX2Kz!A~HBjizSZ{ztwlZh_?a{ABZ2%W5l;ZbuG>}+N(IkQ~tEYS;wp`&XNkWI7<TbXMXDkQih0A"
    "86!>t5$7;NoXZ4p?krAfNsC8_ZwKv4tH}Ua^WNkvN$m58Yk2~3HH<i*L`(lhIUtj><S;ZjOAg57EG_0dMm)!{$yqOUCMUnA`@*Q)"
    "58u@x;7ECTdld1UK5cTAoYy92?F3EEk^xJ)Kgn8h5eRtEG2j#-;8bRSlTHBV&gA4Wc8uQ-<kcY=op!va_ZyZh`SXa2K7qJqj5uIU"
    "OX>$&fruN85jSLVmJ%i=XSt<?$B4Jg@E?fF*fV}Vq*n?E<W<D&SRCLbecIxzW7ZaDDH&Rvr64kO?gtiRaW+cj5b#^x@g3krXMj_h"
    "08X97$%ip2_j7xt<sje3BEsdtHC_sT-r_9sgvGh#&)y*p2-Z^ifeJ0oqGOA*7_>Nx%`DDa;%tog7T>-iejdBV?`Qc+3v}<v#P3O0"
    "`n-vS;^!?+iceUal(5A~fOIX?56sZwq&&7bDMO31rRp9dPGw?oQt2#C31i>*{d`|t72r_Pv7PVpT7~%Y7ANr&7AFa|I0+H4dyA~4"
    ">PCp`*y6n9?%pA;GmDcZ)hr8j)ht!=*g1Yb^H*9HZhYp?BhKOT7AMCiEKZKt;$%S17U>5jXmN5LTb!Js#mRYQadMehoGpO;fjE!7"
    "<M(rbb;y44ro)kTh|}jSPJV*+R6AjdlL75Xde0g|+Ed{%?Wr)NJ=Nx!#mN)eQ{kTWBsTVr-_HgX1_Y?8o!b8$;u1b@aY}f?;*^Lj"
    "P5~rtv3_8J7N?}K#VH9|oGr8R7;(uHi?fBWKM+5Sz2o=uf-OhRAOiG&c=^1=DfEQJDTFOf0mN?Uz2hR#;uINMoFdTTZ0VLKi0j1S"
    "lrHPK%G=mGem_H4hcG@VB;Mo{`@G4i;R%yd12#DokiDJvSR*t!HI7YAP0-|QIhe<YYnqsxEr@+bT+`S)em_@Ohk(=aA-wx)``xdW"
    "&zqcDo-jF;u*s=_0iOE(sxmY=TZ-l(;tWmBmY8{hxJ*pW7RCNRyo|l$_p^r8i~!tG>+?ERlj8H{rrHzcrUh(n8X$zH-rTeZ&CQmw"
    "c?7maXl}Md&10}FP0Y;}!2SSR#*Xp((Zf1qziuPFQ953Fz%75?+O+b7wP^)gn+7<tsb6nK(AqQ_Tbstv+BBY7o5mAsv&FAJ06&cV"
    ";`h^tbqI)W#<#jjkdym;`gv>9^a*Rz3|pIKV8hy3n-l`FHYtRmwMii$Ym-_==ON-0;@H}x7Qg;L{5<xH-%lt~NPwJ>-_PCmTuKW0"
    ")7B=1ytXze6liVMc5tkN`+<}o;*`gT6GOzwW{7j1AkLk&X<_Uazn@yHLr_|bWCt_<`$RvFxaKDiSH+0ye#4riA85$hq!@<QCdGiP"
    "O=_8+$B4%`wl=B7uRjpaW5@XYBx4=2U%cAyPbj8O+nE&e+Rm(<pq*LU!NFkd2Ns4{7a3zs0b)&ghBe6q>#jDG8c)dL+quR%1f9lu"
    "FPow6_euIZ;v!EVt_dTq8El;TftDfSR>p`MvNNgWh8`oH!r0EF7P<aF+{UQf4?ET&2Bcd{L%qLq{Ir=#>4`c<wG%WmDS<jh>Cg{^"
    "b&M#D>ljgjb&M#@>KL^w))T<HI!0=zu}l1Z{;>`LYxi(@J01?9zccga0e_;lQSHPSa8TPQ9s7Z>wh^UqZ6ivswh^USZ6ivP+D4SS"
    "+D2+`V~;qWZyxbFBm?sDo4Lb#l;fvuOv+D`JEDxs9o2SVW1jkfu-p;lak(SPu-p;lS-B(1lX6FtyK+Z*NMnDvgyV(^sC=aDK%YC)"
    "N14Ot0e_+d5@lQhskQ?<^U@E5C6FkOOCV8(C6Fl3N+405lt7}~l|a%1josmr4;w0=8d3~lhj<B}HZ-X`Q5T5{u8UOLfuZ@<4}^7*"
    "sEq3(QGs=lsLbjjQJK_5qSDnx(u0oO;lj3|0!k#6Yql{5IF-)>{zR=LD!5h>6;LZF_d2}5T1iyKwUVg7T1ix9wUX-9iJe)xT1k31"
    "j=kYxx}gH9Ce=+!m2aoSDSY0{q$lbp5#jntwH+jS>y<dc`bk9N`bqT~G&5;dKZ$5kKZ&TTpQP_~>PLW|WJ3j1QYx`p+c7#3r}B9-"
    "lb)!lM1*T95rLXY`P>hLHI<0QHI;~9O(mjPO{MyN6El;#no4?%V`sR$@rDXGaUI`+4?Ymt=S@w1qRLY3giTEbRhIfB*Tk^O67jgo"
    "5;3f@L_DjqRIg4<P422J=`oL8;hJbe1su3;Y2liX_jfLzw>0^Q!b`-s@Ded7yws;IAclpPh{uJO>NRL-@~rSuy*jZpxhuS+M;^Pw"
    "mCA++D!~-OV<tXg{k*BkPZVP!#>JROP%)-{(FrWZL^3YMRIfo(Q)b1ONG8RYNV;N7dbF`WT=nJ;Cv@UkG@lP|F4Yc6{=BUzPZVgX"
    "ov^Jbpg<G#`xJo%nn=b4nyRvfwx-MqG}WsUTT{9MP5NH4eT4XN^M|7&*ZF$*q&UR&^VX(3QM8E!7i}T|MVqMKs3<JjL^>|oRIfp6"
    "Q)fk+>eY$0sa??~J-&_o;d<Hp;poiuyYs4f4f|W?&zqb2L?I_qT*!$O6mp_|qoS~o6Y02+Q@sYwO`R2TBApa+BJBz}=_!r<;TAW4"
    "I68FQ4iz^k?`2%&^X8^LQQWC^!se!e;!fn=2o`rD9T#^ZgT<Z5X2qTA)rq-jU2!Kp(by|)dGm^+L)VRZ)!#LJ-qf@wYCVzRT2HN1"
    "&mQc4n_{rm6WO@dQ@sXFO`Fwvs#hnbrggQR^rVyYDSStTQ7ZAhH^t=hwx&H%0E!G3fFc70pxC_;EC59|E&x@pL0i*i1)!=qF}5{1"
    "bOoUFbR2uc&2AoXM(3^j-~)&FX(N-v6V;$<Cun4H0M(%6*bju&pg4@HLDg%>$mB4q233u+FoC+O2BoLV*cWc6(}oH-XkEXQ)vOPF"
    "e2oLs=MjIRLR9TU7;!=5yM7?75XE6!A&LX65XE6uA*x;-o0%ND3Q>BFW6zbn-8@%}4qD%;8TBz_j<HW3_#EQ#iDWe#ak3hYVB;j`"
    "ejrR%Q=5lY4@a1+rZ!Kk9*&b_HT7a=^_=tA&OD^Dp@NdtXfy1cQi;T$2mFa*JRET`9*&?Gk6ikJuow@=aWS5HO(Ed3Vmurt#dzw)"
    "ZVP_q!vvMEp#sjJ^2r^k;&fX%pFul4k;H=&PU68WM|cP3`N!7$zUQe={khe0I-Xqy>+Qj}<Eo!}*{d7OrHSNp4UBYYB5RYPG?ARH"
    "$wN?@NKV%ZDlknXr|St=oF<afJ&Dc@hQ~CKwFmG!_5c^^!La&8|MT)+fBy7G1>@4vi)^3qbfp_UAaKow;1DQ=5x9QqFaq^cCmjL@"
    "hX98e0`*fSAGfW>X+^+11d=|wbXWhSb>F&l)AN6~b|-}QV92(h{zsc7_YCEaF4rk|xW_$(T6Yisn$?D1yk-uuf6DtS_{Zcx;8opo"
    "a$O^<=S25w;{NBfvdX*XBnL^0fUlmD-S0`@_hj&UlK(w<{d<c0Jqi3C0>3Bw-$U!)^N{WAc8iBcU9;NU9(8!n?3(>Ax)=SqJ}K?>"
    "Vmqdd^kU00-VcpvC^D04^UzG@Ta3JZhYs#T)Z*jg578|PIsOo}DEa+EbV;ZG>;L)br^8=A{qLXt8GlOU-!H%aa;eJru9i=~{_@AK"
    "KVN?OCH(Z$IfnD^hyT2)>UT@}U$=Yqiv3c;7jAlx`%T#)x(P-1TMDMWbLp3Bw?5oZWJcHKp&8BP&J6aGQD)R&E)!~Sz1Z2&m&QtX"
    "8Mot&C&C4Ahx-pt={dueV*J8Gi){PxvS$_N{SqjcR?NjG;oWu><$6HnwyV$_2ivCY9qy;zJ6%$oF8Qc$Jr*ir{Epstet*a7-gSG&"
    "vmE*l`Sxb_icI~RIo(r$`|s3SYPTHjPJNO8ao`lnrQe$u3;SF6w*UzeFTI6+t5WT5!R{?6EY~gJ%8yJSi*)abVS<$(nZ}hLneLSz"
    "kNu*hS>;EjN##eTzVhSclD@EhV!2UY>P`34f9|aqDy!)yKoGn1mM8IQ`UxZ}d6WJYvYdYD?Z0n>M|3Gvm}1O?D8_wWJ|@U9uFYjE"
    "Rd<fD{}%9!WL&R~L%;Q67y5l`A%oX(vs)O48PJgX%3aLPK0;!}AS>3fS4@0eEEBO}U<;kyEv{V2iCA&z3k!T3JYdQ6`i2?oPTBu9"
    "_8ULmfAyHLJCs58tA4S)NA~w}c{{ld<&rfcZO1zEhTc-I55%%A4!(({r9fZVE%4?qWsqvR$6bQ$aTg~L60^fy_8LJjf3miNfL1>a"
    "(kE;4c%v?N`lQ2MX7ovx34M~KZi()=$4mYS?pub3dQ-1P3jhuCXILn&<XmWgH!bjHjQ8~z<3IoU**D7-m<IGYwC(HRuit<D{qWQ8"
    "m$#oUr$2vs`*HdCTmkv(mp|KLzq^bDS1hRQwv;58(VcG@-4EyUt=SEc7hiLdM}^xV`F7VoK6_UUD2P>?-)HqI(+`X&ZU^Ms!w%Pn"
    "(eh#2^492Tv%KSS-fkLuE8MRl_0GC;|I2UHz5n>f@9o;@XLkt)KNRqEdP_)QVFcD|VT8jkU{(jL1V*fcUZG)90#8T@{6R|i#ceUB"
    "tOTC161cGvK6J|IOO{`{OO`Btx<;VO-8WQ~{0iLb7R8AgS$p?hXH@k=VIDiyaUMI?dmcNd&TW>*j%||1j$3y459p6?UxNO|ZDmAY"
    "=%Ke%fbY|NMlJa-g6@@{W&B03oLA7dGxz{{%R{~yTZs_*QfAN>oj_mL-UsxJ;rBZ9VT*>@y-w}WRcMTz9qmm2;(KGbFhgyZCFC$|"
    "J>SySKYmPG#`>4OQl|JZSBEA1BDP%iuRY5KKw4VLu0a)VSMv?MrZhUrE3YYyq9ME0)+;&*51ZD#8C$!+O_YSFi~W~`l<?5BTBx-P"
    "TBs7PnQ0!RMq1i|*C5LHF;{(nr=z_3tTF)dVGk?-4Vc70Zb=OAYZAZsnw<7hW5G!c`#_6=H^!$=Yr8DM5)$A_mM}h^SFa(TnuOW$"
    "JPDKIdG+FlPt9WZN&um5k~e7UDtCdS{c4K=((r0KEg}fD3$o7TmL>t>cFXerh+B*k>s(?QTj$c!{D0sk$FJaaxv{OK<y~0FTf}>U"
    "+Mbt?<1MtrJ@cK=XdaB-oed%I+BA6W{n04~&&Fq`B$78E<Hyijlt3bT75wpPf82Y#yZ<(EieYQEzS(ZAR|@^ss#|M@66yIb=X)~^"
    "*$?%ibHGFw`<JMFTqYkc+j{-IYPTQ%y!>?j@yBmJAO8EN-+uhp<>yVRuG-<MJ$KK$e#-B5XzXFX*}PXXG`uZU>uq~1Dd5>op%YTS"
    "WtIfbq}1jiJ4@32Oo}tqB+U+`NSYi<k<=YZsmt2Fw5-Dh2QY`-Pw$Vbd{<ylTH=Vi<M!KBR4RF~^^-LC{wI*8s~5Kfvvk#F8-Dx~"
    "zvhyv19f4bN$OLwSol(GJ#E2tNe}x1un9_-FD(i1r5%2dE?t|)o2O(iZk}>T3*SQR(o6Nb7wdKW<g`6FI;s91SBm7NPrG)(Qk~;m"
    "sx$Oy*XFTQ=lr5nw{#hE@4aMq{PT^!qT%9s({Q=S%0|kBr8?7Gsxw2W&ODat#y5HmKS_(IQ|;0pEqu%RrEu8W_F#>35UiK_@A^XI"
    "Yxva>9OYJgq9Zs;eyB%uBQZ)g9uXYtHFE?<?Kd4IOemgGqVro`365U3lsNQT-k51p;)LKRC9MdKwac8~C?zilj<rWwzGlB<5y4SP"
    "NehBw?ZV6F^mIQ&aFjx2L2#5px_nOWV?zYT+JhGaM=27P&yn&#JWSvx$v(!O{V&qAe3B=+X7Gy;(>42FWM$#CtX;5?Q|2LCA#4uQ"
    "#2lu(Is9|KZ>Fg^Ofz$sdUH56PWAKp$==n|>GJc>?I7&U&nuLuS9!<y@-4SY;`Np**Rc?;W-kPiEA$79gkUxM+MLI;aIa?nZ_a$7"
    "Svh;5Njdv^k-KR)(aV@^2f&3u2-!(rU*_I~E-ycl%5i(9AmUK}P+VE5wl7y1;cTBmAlqkuAXNxv`xFjg7ggOf2S1!EjL}`>dvK&~"
    "Qu1<>a-$Lm$Fz&_ZZFB#@8aE>e|z}rpMPV(zMIaLgS|X)ce9@X0ak<m`v^!2`-4|!_d{~|_P4uMy7{kPf8Vbg&ekcL9A8&9Z=15="
    "tNDHUk3WCCZ>0FD4St+|Y+IYHok!vKdTq>Ak(P7i6;?tWh?fC_Y((5Yknt+GCL?+bSFq&QHsY9oB{u>V-1IjB)@#pFTacH90XetN"
    "(<KtHLXxmlND_1~bfJ(WLX0Gh6_TWhLTbrXUQ$Ss#|r7j!+J&`Np=cJUtfc9JNqtDKBbX_#u`beeE;iFXH0%dXodIMMHp)r;qgHT"
    "X<V<DG>G7X&$WH;?6m%Y@Z7V=_1yEL1`&HPCM<>@Gl@UztMO+Iyf|ba8mD|$QFOY@(Sb#i*CilEqxkrLZMW&1C_McyIzIg`T3|#?"
    "XQ%%~C#V0V)h@ZSMJT^+Lgek_biL)=bW#SYpZvs$_Y8vAmf|9aqM!(3|1DKm15tEb15wlxM158RQFKxRQCdEj57gu97DEo3$<P>A"
    "bFQlxu6|Y9muMTT4I~!FOa@CYG8wEl81Mc-w<;~i6~)7F()-%Zs|9T^C%D|GTKLD-O~PwGmR6Me+U0?A58imNv9!lfEx-xp0j$l#"
    "(;#B^Jb-RJ*enmA*dz~Nz4&n$#0tN?ydDy5Aq#t;IRodo4Gda)G-v_fSc}+1ix}1-Hq|0F(IWNBnL5<o^6RK=LDPE6m8@yNTW1Yn"
    "1-Ldo7#s?So#%cWF27paLDGTJ55!791FC!x`hl2tq2VFqvgbZ%pg89~Xt>rKe&9aTX4!KeG?4AN4|VT@SWFsx*yen1&O`1)y(nYu"
    "gNAE<s!wqrG+a~OLhggMT+0LQgSKQguW%o<CFz0lWpTuPsMi!?IL_my@t()caUV3!61i!dBy!Uj-6DS7z)9zufunKGlh)X0dHWvk"
    "VZCSX%lRH<6d%6w`+bQHO4}$ZZPN=Hu56>X$~Nc|udTApE1!66DT3zvU5$Me1Iu5Kg7_f?OpA?<MmCI|ggJT|AbJ|d=xKQoJzLpm"
    "8m*V-d<w6lx7Amv_gw9qG-3CXrm)&RXc~M&)5ABkfT4qLXrpD#x5S#_;Hmo(=ovhC@DWalz-KEZ0iUe|OGRt)Il|8OX7`cXKA$Q3"
    "JVvGey4+Y@ILNJyou%);ba2`J#r);#_xqzq-DvN6yl(<Ny43IKzKg$0{XXuxB!3qr(8b@Siv6xjc6Vt-YxZ5-U2;sL9nChwE=|w-"
    "5_C66VX)u1kH1%N+QvVin(rw@Zxg)(wN<ep=c|9jw58`E=MQ~^G#7Ud-2s}5yM-P1cv9JMFK!OMdQDtr411a6b5lY28q~k<qMV%P"
    "YdrrNS9ws+S;h_@Z5e&;`weQPk6v{>T=Mp!Leu?5OW*U|`;Gi?5H16;voe9f<ii6alwN<OEx)c7P$8;^p~Sr4iD`+lV8m%jFjlSw"
    "<Sn3nTt=bt+B^)EYsm~OR&8Z)#+%(z#*uPul$j3o@CDSj5A|b;8}P{-q`1*SYqYVQRd{&rOAEht?n{ddW>(T_D^dh*XKy)l@Z@TM"
    "ldE|)xhj*%wU4x>#`?Nbv;N=>l7}O2U{h0UFu9<dRhMl-DIkw#Z610wwdL!1X=VwtSZlkkc8a+2k4`H8=tt!rH?z~qKRT=YqpkAK"
    "$Ffad(BE;>-&B^%mIgi;D$8X{@cemg9xq#>7nd#JbFa01DZ9jjU&ssD6)d|lkzIXNc6A`TAWeRsYDWn(>y!Yqu1~O|9I#c&Aewh}"
    "0~2-vHHOT>X~&5cPCHJ9oOX>)v$uXYXJGwsMoIXTeO`w1y;;UiJ1%kJv}^f=KJB#QYa{|Y?f4plfKI!{YI(_N$GHAnZKt8rjs@yN"
    "ma#r$Vd%7DnJL6uY9Xu;TY{nVp%71BP>8mHp;OAAvUM4uzG)LJeLCfDQtT2|$Ng&;to9_x)a@iN2&pm-LaMwNgscN)wOJRJS(3j%"
    "U&|YRO(nCN<?padB<md3@;68ph20?smFrizJLI5`>6dN?8B{2b4moJ!@AQWpQtCBT<Kv7SKrQ#uE{$_?ynbyQoBmL5iaUC`il*^7"
    "hkBJ3=NxJmo1Sw}u{=NLpz?6u8@;FYzDRV?K{e>&0D@{v^HU6}kr$^Wv~g{gZ`&_Abc{hY$Hg%QZRM7h4=QP%s9Ck}B2lv{g$2#9"
    "cEMjb1qC$XQTve$_X^6xguSY4Xy30g$=6%2j%jN3qII9SPbOuP-Gz40VDlNZG)bM(c{_jo-diP@dhfiPn8B_V6@Myy2?E8{pLA0F"
    "Nk6JT9r}rxR)5l2^(XDCKUrPlUkC4SV{fVTRSQhx<?Hu8Uhel^<;qnX?BNZt+%5G3Gc@@ur}4aGl-ENo>ug?1n#@b-@_J~ZuVZ(j"
    "4Z9-!yyUm9-~0S_zqc*tg>cxZk&||2pj$A;1x^gpcw$)Lf{{3z7@^6;h;|e6ImaUg?`?}x*Y)SDmE1p8yW(|r;ltOTE8(y`*xpm="
    ")IHWNZ^>qzHu}(qA$Z7f<9Gi1>ILFY{Qv&=<-+Bs^X(tkr&?nO^-qn*@c3A(8}0tF!sYqL+W&X?uRs51-B12eH<$N+Zx4^Wet7D$"
    "bsR3|Z4dp=&pkYbAHV$g^T*-mAOGjFJwECB@wvCXkCge<$N%w<U;ne(DTniaZ;vlw6!WRq#=#B?rK8u?CHr+LjG68)WlsD{|J<Hw"
    "|IOlWfv1TWtudE&nWpL{tJ}iWK03dLD!9ifxO><%`elt91n%M9qmh7m5c`>JmACfe&+Z-KJoTr=Jl^Hii}vB&y>R@FNxEg6uA7Mk"
    "IE27CdvMs-)wy5p?}M2vhL|k<2~xvU7Q0bd(AUYL7I2QYHc#^3ShP5q0V^LfaQI~Y8#n`b^D9{^nYBW1Q2okq^(#x)%05#y*a}&7"
    "YA_#PRD*Q>@%x{f0-Plgvc^yO0Fk~yjMLjD#*Lt|1Thal%oxP{1c=3hc;B~t62x@)bNeCJ<e=_se!Mtcl1SFS6?<+id8_sQTY3H2"
    "PLkbk)fYe8cKYl0KYsoFr;nd3NQYmXib)R{c@y}_I3us6M<PPl548bWMoXkKPU>Zi*`uDbb)Uz6c#L>>e9);E@Mv7}(Hh}r7xJjB"
    "X&>^ioY3aKHWLVW)Mf^Rui7j_!k6W%7Z&^b>Q$Z)zN}G#ri8C*BIX6*%NkE-PWZB1_abw`S2a4rg79Un(AAvqW!ZE=__7jY5p=eP"
    "Tri&SWshlK_Iv~@(WZ>AYDAYg<E!?tIpfQU=Y;JUUsgOPOpiNAi|2&d4$x9;#Q3sCJ^4^s^^^A^>G@x`+sTmcWsQh3+WQwCTfX&T"
    "XZarTH*CSvdE0`wj4}PTHTBPxzt8lwmOy5uIm<v{7YpbcRjwxmrr)TRET;QL6?^d;#iw8Y`OhEQ2ddSW`ta<0^Uj6B`Wr*|T%fgt"
    "H8ZQCkx+ngr!*`RVJ#U<+ob*a$#|SmpJ{bqC{XEH^!oM<A{T8FIV!Z24{{3OST3g*ZU6N4<Ch<Q{NtzJ4nKami^=1@>;z_#Ctd*J"
    "&I@p`Z}7P1jfGe5Z4Y9$|EiGujoyI9Z*ebh1nA%_G={R!P;aH;EHrk@LIaJ&TNav!lFG(ma#Gtkj)}YVVn^IPoW4OzWZtwy%V5)~"
    "pz}94{j*%|H-8k|y=*W(Twn}N`1K|740CGimUaeDO*S|+CC#R$OgtzpTg-iGj)}hky%TTf(fYf@t|;T_kY3h1?>@(4)xPJ;wzT<r"
    "co6P9m}P>BbbQd`cLb^O7Ns(lH1s+)UeDjAXIR(nZ?@=6+55imv(pj(@#B2?>1xn!&$qd!Pf%5c2XAAmCDs8%r>_IVTQMZ-s*U};"
    "nIP>I-o(8^+U%77be*#6lsCn3be*E>RLX+fXOCsTcI3WBv~jbVLU)%9*_PHKdfTe+dh693j{9D9Bjb9t%%iB6znAsfiBe9FG`{=9"
    "RGHb}H)#fMReb-k3CI2=HPB0pJ=1u7?~mKRy@8+CidVgM|0)*yw|{^|GrxHE;;n{$mbdkzS9|Z5%fGqr(5-USFTeiz(EPqByw=X@"
    "ap>=O%a;Ai<<sxmla&S^PQ?j<Ol7Vo6ea{R)!_kH(-*S>)q%W>qFC^i6z+50y@1WON7iqTj&I-KLoc@Z&@Iv;(rT9awR$Lrx94^K"
    "N2K-l%m1oCZcj~p#Q(d0QnKY*uvyf|T-4}$zads=xtTXy+rr+73KPM{`A+PX?*s~d%XjjU;MXtMG6dP^1CNeephaw8yO<jCX4Lhx"
    "lvoodv6t|I#7b-Y>z~)HehDojiR{UQ-4AYkY%)RhI*NCuo;_LnBz}<IN5pEMj2J7ey$oWl^;!WWqSibj5w&Zyw<cQim_$^s(vU>d"
    "E_NiMlO4alvM3+72_jibTkXb#v18s#TWglZrnvUGrjFjk?M;s_`pyo&{dW1~y!{?|LRi%K9m+RY&U}g63s_uBB0LGx+HK%IEg=R*"
    "k{E*wCGl2@=}{76%o9nBQO1%OQ)j`Q&gmN@@piPY-8(I1CZ?XgbPRW&)n|jqm){S6Y&t6T>wh3Jx8h8HkI1y#BP)@Kgq2sMG9a7P"
    "YYdfF<gxOK43$^pnevJ<QC_Xg(p_ZE;T!fWbg&ILS*w{w&gfhr)gJy5{p#}1-)`)KcI&mSX~moVHo-|@t!r>*k=E{Y4fSIp)HNxN"
    "bxlf8*Q7MlH7zH|P;eT>;zMxCH!w8mmPn}Gd#!6ycDhFCMIV~I%gsM7KmWEpysY(2qh<VkVnb_vlNjrpM)c^#hWjxB^-YqozDWZ0"
    "O`~W`#6~CjrZG1@#75*BfQzyLr)zzatk*Zk)3Lnj>wA}*KmI)Y`PU!Y^KGqge7&b{mYl{OSxHWgSmES2;)T|02`ZeN#tJ8AsBm(g"
    "DV&@q3MZFd;T*mp<iTazW8|_{IJayw+m|Z5oxkL?|Ld23|K->J{AGIqS}UE*f1}dLyjD6{u+qumm5%mf6e^vpW2KW7DxIt|rIT%<"
    "baG$5^?dn;eKG5{FV41BI`x0O=;ZwNqUhus$Gmx+E}KnN!dmT=*q>AVX4xrGm$Fk5wops&8E|P6>b0Da>@*(HNOnpVBs-;qiR_dy"
    "7r$NXqVV4hT(Pz6P|qnn$$`JJ&$;~9jmA=M%yBI?tm_vP`kSI>_1+q$zNcbg5j|^tWRRVp1PW!r)vtYAEyZt^fJWKzhhM{P=};OS"
    "BWc$rqD!e4T{?V+%lELocp7gP$Q_FR)_`uid4Kx-TOHZ;=AMys{sv}16u#e_#*k6^8zH-%YVHsBw?^`Z`&$!(!~LyY28a9WH4cvJ"
    "`@w;1*Y;-()1m*>(w|+uXt;aoZ$J2dAAbJp9mKNzlxyOwho5pyuj77-DE=v8<Da5FPi1nyMaOw6>s5P9@A7b-zI7STKBGFZZZroT"
    "ad<a9+{j4X8Tt40MKSb>gyTe6G}h0DvN#@J35Q)-aE<t}xq$e=s_3_doOt!CbGIB1NzPw;skhCm&Y6~IW|!~bJ>As<ng#EMxy-UT"
    "*XvZ!u7-(*yPC!q0=pXKIN8<km}T59b}Zw|<?<z9c~hS(Vd(8-k=1N#{Cj3w*K5bZYPR8-kk-B@y!A_40-@P%w4c#zOE5Is64PY1"
    "CGvQ-TM?`+_In6#@+DxC&<$8gG?nznvR1`kyuQ=nlQfGuvMg7x6rUmaeLCMC{x7kgRUtg90`h%uue*ftwDM$H8BeQBr&VUt+Nb+?"
    ")9|HfecOB?GOe;)uV24)gIP6taaJ|N)vPue)HAdCUPcPc>N^|iaaMcBx+dtXX!NMjtZIVJibjkY&#LB$v!dn0`IyzCerZ-?zT=zs"
    "$-4Rgre3o&;%U|EF~nD<^&w{~n%1jdYdx(n`(kU~|1v)H15x_L)~w@cy`CrDP3yhV44hWg$+X^zlV7Lx?Q4s5D~{K0yQk0epWVjO"
    "8cwSPd2w1FOHhGnZ6&ClnN~{)POGK;FBA9n*ga$u_mE-tkWJk~HggYI=N>wQKwq2ITe_uo+j02MXti&)zC1<!;HNKs@VB^J%K<a{"
    ";J1`6V_}n5KlrB04}POnJtb^|ZJdE^T>oi^0q)~!^YDWo1Kh{OFx$t)Fxkh&5Umq7`JxWF+;m6`Y5K*FA&<ZKvE@&BX<B0_t1o^G"
    "<*6@z3<SUUvDJ3k=@9J)LJmd@V-7|Pkb_a1bvCUN4o1C5-LxLQ_Qg->j;~C=_%WzVrq$xB(`u_PeyoE0)U-yJc(k>HFTV8yQRdOs"
    "JpAIvn9vtL#x(ij*Q?_%evCPG(|Y;ZYE87Q)|jVX{20sliyvFTq}QgkF`QP@O7h&aa>CQf;EP}Sfs*00N*Pb92%J_8vuV{bnO5z;"
    "_}}$yjgGD417WeTl%`+&nEK4X-}qK3q`$)_6H{0!iPR@GKt7q;1I85NJ3nezQnp@)bcUG5bcUE9ouM{Q=nOGU=nPe_gb$z0Hv(ID"
    "wndBSx_QLfA#r$7J0#}id`fsqJ0uy*DmWn{z2ZxXr&TA@YIs_0I;}RD)*L=qDu=qJzc#JmMs14kX=Nr`v|CjuJgu!B)N9k)lEf^g"
    "wQ+-<nbw>moYtJvT<JG%4w%+l@^D&nVKl9|*koEW<;k=Xchh=5%>ClD-co(H+v;?Smam)2!L&+xby`K2)2ivYX@!Y-TRSN0?IafE"
    "<!#M2oYr#B%j>4KO!D%!t2Un2(&gnn#J4Z5R@qi-0R=sKO;u7EPisl~;<Pqm%wk$g)~BYm;NVs)Ah_jLYk|?N+DzkVh0(28X3?!U"
    "$)VFOenhtpDSvUb9=6q5KypI&+aD_B`f1%t<$iuzA2ODqX|?j)w3@+brLg~H(z`z>1~jdW8#9_#iUmz8MVU-1jWY(ei=~@Z{^DxA"
    "Y^#+(GEVo~^JL3J<<%_{mF1R+=(#P^jmxp0R$6SCh~burc)VpIfm<e$*_Mf9vSlLewoFOB$UJzn4PQ+oDtx5AngcYb$hss?-}zQX"
    "?!Mo(?<Y_`t(Q{{GB0sayTmxJEZVwYL1SQXxn;uG<l>3R#dnkI=U&iwYI5<+<l@o`+U09gT6mjME@_EdnWzw^S5*iT_Kz_wgn^-Z"
    "jCr{&<i56HgML#<r>2s&KD@+3vA>q*vFF$_wV)TbQJuJUjb6!MR-%NsS}~2>(Jf~EqC^F|KYBiY5|`c+Nsn*;;X>JZ(EK4wl2nvz"
    "`-iA|NXgS;!>vb`HQ|us*CJ@e@`hot9aAvg${ck}!FVfj^vD#9LTSVljEx>LDD~DZ+L$RAh0C5P=)OF{qwF_#*zb$**gfI{bJ;BN"
    "W0&95_0YKQk$ewukL-FFxJU6lz&)t%p#j{3eGhOCaXliqhx#7i9_D%^aF2uU0q${hJu<k*$@c*FIJ+JN+~eYVfP1{T9t7?YgYSX_"
    "#7W2pC!_C@d>3>VCnGB8F2#32ckxn!q&0dmLE;*{oFI9PUQm$0MkgtTBsLy=7jzdVD~4n?o_rT{7bh)-q&8lB7jzdVFNWkc1>XhS"
    "B{_L9B)KX1F6b^!UJS`@D!vQ4i<1{avYXg<L3eTTVn}wA`Yz}$US6Q4_40ybH+gwMvYWiTAlXg5yrh6+H(h)ebeA{R1<7s>z6<(z"
    "MArq$Zce@nx=VIlknHB-yP&&}>w;uAv+siLBCZRP-K@R~x{J9kNOtqVcR_bKx-Lj|^T~HXck%LqWH)<xf!hQxFE%UtQc`^2eeSk9"
    "DF&KvWor+cKO@@e87a?qvbBfIpOIztjI!U7lm8vl>MQj+_4Y<NoL{dF^`0yFW=EzLxPRO$*G7HVE7vANd*u{4jP}YYUel4ny>h)M"
    "<Gpf<&e#Nd<=SJGHLqTOp#FnN>7A>1;;l@dQI$hKDd)@UiR9ihf&c4v+x<zWbSwPQ&&gu~kq!40h9{j;isO?`=~fA5FefRkPCC^t"
    "{dztB_<1*NDcQobOdpZ;_vk<EqW@_YT~DcZ^-w&2Ayry)vz@m|DLyKOEZW)$hQw<7J|uSN#}SH%)#hPDEG0$}vDC`C41Hwvsx2HF"
    "=~moj@jFHF@07hZKKJ9);P13B{+*WL?=+tL&K8PaNLdbLp^|gZg)=L)*!xfrbL_Z%MD{g7l$(dB-gbDXIpu4uj+;UfPG5Uw+EN|V"
    "8{1kca)u1s+D=pH&jk@|(=C(_r6LzZuuYlLOe%;cvqc@jmR@rDcgWds1CF~R<OeeT+I^3FzwZ;vv~dXFgz$WsW`WDJ)x8-`h{9!>"
    "b-GL~OeVx~Hz9{FE}zqV`4}x#gDb^p7ySaI?)KDM8j$Z_n2qDG_&Fu!`RU-=WAZ&MssEmyzWC;s`-`VERAaY-LVp8VxvW=BD@BA>"
    "P0J**D^S>vBNQmF&BH)>YLp4EY6?vP<*BhF#<Rs;pqwt{Yske=HsqLlJ@)qY#T&=B`;GO9DZ%N7YCGVhy!8XMz&TMG&xtCW6N|Gs"
    "F`CSY=?CAFEq)QY<1K?oqOc<U)Gj(_(k5I{sI}**K?*AhwdNrqJ5fS}>_mA&$gWq%gzS2;BV==yFCt5_A)9TeoT%{MqnwE1ayp4t"
    "(@9u)wPYPLQ?_wC&~(c6XvDj@_&A+c?tNF(t-sw%#iQy#%}Wqe7EU3TlVflbTOw&T4BV$yGw7wjeI1D>sO9jOtv60^f;cUIDm$Yb"
    "2JUO0VSeMp`EL?<E^)2;8-D`gRlpG^2N($ijD`n+67zNt=-4YL=E*^z)Tk3f1;x@G1ma`<qJlc-4La#LN_@I}@y6SMz<OhPVoorJ"
    "BOwllT>62K#F1_!4m>Beow+->IkCx^yCh*^mv7XK>zthFi_pE@a$=-L-RS1z?TeG0V!q#axyP4>J^o&uNyM(Ht_Tq1Z>3iM2h5qI"
    "v2RK;^i6%xO5mJjo6K41*xC}m3T?haTjn0#mL+5bJ?X-YEIc-KT56E=cPLkp<%dCJ^$l!kMuy)&(O18LqWBvq7S_tA<rzWpXe&-_"
    "(%vgL_z>!PPp!*6wGQ^wI<3-Kuj4(n4y$ywYcFoJG%q(=npYdG##$K^=&0B9?~!c1+SxulqE{|gA0E+%vNKx<M6aiPV0c8YXXJ3m"
    "O0T&U2H_E9T7;~WSFuRFQ>hWXE2+qw-j(!zc4t8EO08_vl-`xp(wyE^d&r#Ll`Nz=y(_f@BvX1<vY6)duJn;-WI*pqw^~nQdRJ<t"
    "o2K-xWI4_0U8&_3nbNzGl{BY!rIt-(O7BWWX+iI*U1UM;O2%nH?@Gq9pm!ycw4is@F0!C^B}390y_g_zjb2WWyhbl5NMIekD+eU8"
    "j^0(f$b#OL1Cm)s@2Xv7LGQ`|Nv)%I)h@E2cjbWO*3r9a7g^A|azK*n=v}poEa+W1AlY^Ft{jl;I(k<QNOm2)D+eUIj^336l3hpd"
    "$^pr4^6~;Tt(O-hyUEK7lHKIx1<9_Xcjbs=*U`IjM6&DXT{$Azb@Z+rk?cBpSB^+_9la|@B)g8@l_Qc}NAJoJ$*!Y!<%ne0(Yta)"
    "vg_zwIU?D0^sXF{>^gc^j!1SLy(>o~yN=$KBa&T5@5&L$ZuatmWH)<xf!hQxFL0mW<ps%Zaq^Oo?3U!apu0GENl11}@m<heoV+9?"
    "yM=uhbQdQt3CXUr2y;TRTb#TkB)jF{yP&%`c}Yli%gJ{^cX9HPknEO=?}F~)<Ru~5b(D+R1#K+7ydc>nFE2=T$;%6pUGnk*H@Qw;"
    "GLl_l-v!;p$xBAEOX|CzyEu8tNOtMqyP&%`dC5q2>EyehyEu8tNOtMsyP&%`dC5q2IruK%F6`tbBiZHTyP&%`dC5q2x%e*VE?!=c"
    "?6Q{^B)jb81<5XZc|o$vPF@PM&<?%}x{H&Sf@GIZz6-jGlb3>ImoL5xx{H&Sf@D{M?}Cg@Cocubt|Z?D-NngEL9#2wcR_b?@=}oO"
    "3i~eTE>2zwl3h{X1>MEV3zA*&@`7Ynyu2XU6)!JHcE!mHA=#CS?}F~)<fTQvb?0Aj^3v*W?7KwYML`!QFD;9}zKfF=Dg|_L^3v)="
    "?7KL5X+hq77xrDy>pFQMSum$FDSD2RC{pwsCsAYw7AH|05G+oj7|x=TD2B6m_Fd5HI*DR9i%y~#&7wJpVl<29B#O~2TJl}M>zb3O"
    "b`*Qx#Yq$^dR-?`Ei$+7;v`A}dR_5d(Ca#RX-Vw&U7Wl~La*!Or3Ie$U7Wl~L9cuAUC`?~c@aXd>*S>!_uY4K^3qQ8?z$YDya-xq"
    "hv>V2*F89S5wz3}PF@r(wS$uvMN94A<VDd^JFxG9Uf0QsqNR3l@}g*|9h|%<T51O;FN&7h;pn@d*LCuuXsI2XyeL{~2PZFzmfFF|"
    "i=m}<4899^-J_EiLrd-G<i*fZJ34tWwA7AHUJNa@Bl#}qb)CEzT53lpFNT)d(aDRUrFL}kVrZ!y555a}T_-PwmfEqGmsW8ebUC{&"
    "XsI19t_xaf$2Z>vyzVKuE@-KpqU(Z|+9|m%XsMmD>w=crsrWAFb;)%>OYOw23tDO?ab3_-JN5F?Qh0+d=DVQRJ-9Atshy6l3tDO?"
    "Cod5#wUd*Vh?d&v;=7>Nb@CF?Qad|&iD;>voxDV})Xq*`B3f$a?7M*1Jv(`cXsMl@yd<>L&Q4wuT54w}F9|KRv-&RRb)CE<wA9W{"
    "UJ_brXD2TSEw!_gmxPwu`Ru!(*LCue&{8`)c}ZxgU7WlmwA3z6UNTy0m*l&E*S$D-$!MuvoV;YT)Gkh5GFoaECodT-wTt*J=yjdE"
    "WVF;SPF^xvY8NLj87;Molb4K^+U4ZCpx1TslF?GTIC&{(sa>4B6tvXdoV*mY)ZU`+0$%sc$xA^??aj$cK}+q;$xA^??aj$cK}+q8"
    "eHZk)PF@OHYHv<n3R-G!PF@OHYHv<n2rad@qwj)V*U1Z^rS|6Jh0s!abMiuHsl7RQA+*%$m)ZAG)W=B-p~V)16B$CQEe0nugqB+j"
    "PH3QSBnI+*;5$39f!>iAoZLY7NDNMJpnoI=CppkT62rmwf$!{O2f9dNaKZz9Br!PYfliVbocKU5Nepkk&osw!VOiwcs%tkrR0(c;"
    "8Yh6PHY4>FzNR()<??Sm7qB#n@+-u>B4PE?tz6*#rJYo?vVfD*21Sys9+LC^A&y;Aq=flHsIOdbIfv(STDbDo_kXuz(pyE!B3JsK"
    "qY2i={6G^dkA(nlRKOzFyv2wnSZ<tOm_?z;)oYJwg7vB_vM7{B-JRm5ah}4o_Mmz0y)vNSmPWzd9dhhWIhIDE-E&k+%jY(rgO}!7"
    "+NblZ&687(MdSFCW4+j&a(ts#%Z`U1zx?>~$KmH6|EDob^>(hVw5)M+^qQNCJ6^O$D7~0-zqI0jXi^l^ed*7-)XhPLlTub>=F(WY"
    "3r=)VN-I2YHqxRX8)>f_6=owXdOcEu2+yS@mU~HW>Z%HDY1!sFee@Q;MXa`yuJ!iQ6P2aa^BW75y;wr6Sb&LpOG{R_%T(VT)+x<T"
    "2qwpt8Ayw{Ofguf4CEl~MZ<ER@aXL`<uoRfag+^}yw7`78z1u?)h3wts5IZ^=<8r5kG~E#p6}r6V3by02VVma<k%_3VL3x}w<{lK"
    "817q|egY(7xsf#8R5emB5*r;B?I<k|9{50*PKtIEvvJXm(!8)AABdB_COmxj?YGM>=PnIUy>Wl4;q78yz4KPwtD0u3S)=ASp3fS!"
    "9DQKcs5z8($GlQMFrjIy&BJM<mZtAIZU5Gv^Q!HWd83fW^G3}b{V{K!DV2)RW!liq-Mk$`IDYlc8n!!^^`RvSh48e1noa$eodPkO"
    "7LxI_Z~&)RYjd8>3d>|x<Rb;hu}adHv6BruN&T#(^H=YDNcTIJCuT(q&x(fWIaUf5;H+32&x#drj+H)2CZbu1VY~^h7fUxQ`SMll"
    "j<-XR6vMQT7`3QIH*5CgwNw?^_UO3ELr<|!9D|i$Og7v}QGB&(DYYz)NL=C*so^LVwAH0p)<2k*iT5cIFK<)T!U{JQ`~!g>CHCV)"
    ";cpWgZR4p?&|lfcQ;Q3&eyOdTHnq#tX+tfA;@>3V>H39sJ5Ng26QkYEvo>Y4^Q`S<wDY8N-J8SXi<GX3ck#}XT4luP@kL5G%zZ+&"
    "$8vv?25YF%-6y+BN(8qjiN@QLME6~#+n%(nier_Vc(Of7%$>?T^J`K;m){S6yeF5mO(xjwPTu5;H>SgOV_D9btmjMzbEb<uWefhH"
    "NwdkM*?mvx=FDbumcwMua_HtP2K^$me9P=dEhahpO6J(lY2@=4AAH^vNKUIcZGq0koDOO-5~|7AD@I(Bk!~d!QJx^W<#9xLf~e(j"
    "eCacgiB=$xt-b=8d36(6el+tn)e+uo<X3Yf)RA~^nt_AXSqud_XlwH#**2B1%o9W<%)gr@+TSDeC4sMINxQFRN%*T-()g>{&KC4v"
    "P3pgzCC|Q^C4;YKai7hWHn8s!TNetxi}%ygN2b{rw=Vke{%vCVDsWT?L<F*b4WBwp!9753;OyU%U6z^aV(>R%;ABnyMZ^_%j^Is%"
    "z)k#{i1jx~;7v4xRLA~J`b1*e5nz84TNQ$$;uDEw@FupXI7bu~rILsO-kB5l2$j+gjBsmSH^9SBaNP=`PcWrP_MUomoV|xysQ=>="
    "e0fnR=<k<5eyf+>vmtL@vz8uk_7!diEAGk5jycA!KRe!?3{-5oX(hCziW47VKlLT-=YC+75wObK$A_?4MlzXuO~4ado2PTHv$?l!"
    "?h}2(++Xf<Z)J(yHT5R`I5+ylYaeHhFaa91I*QYeGbfY)tv34zTiJh|+1Y3K>&y=p8UTcGj_%q%4aX3}9Nom%y&W|1`PIE06RnmF"
    "liO#!9ltJCdfFb()9^d7#O3P=Ehl2&dt?oZZvn%cwzYYf)3#nyw5)lS)0TLW)0Wt@Th^~S>YZBM;_oD&B(eLb$zb`(Lm5*5yF@6*"
    "?fB71jvH6zB{^<o7Kh45a(q$wNXFj-$-4aY*LtPbH-f??g<pNGtDEu)AuN|b^5CV+A6@Pf!MnQ0x5;pIk83|Xj}I0dP^2QuEO52Y"
    "^2;K)1O|!BEhK>@Fi5Vc@UZ}1i2*MNpe^?w8gjQkO8gCq^lek58m9C+(g$Zhm@G|8SFWZx;F|kS#W(K&wE(kJ%g!v_2s)2uX=CV&"
    "%u+2AXYQ@m<G?IcS~+udo)4PzTI>6PwMZ>N-AkgVvLF;vqsOeK+U76a&c}6AU0w`{#rTgO=gUv0zkdJY*Wa6)c60f)taiKEw(v+P"
    "tWA(oNR5g!nr#bXN+I1+;SFZnF>)YjgghhX_w$dPKv-H(25XN=RLx$Fs##ejDy?1U@uLs}_$U~;`PUbBCF#)KFmJ9WBQ)!@pLH6{"
    "I!$JsX0y)IS?Bev%W~F*mf(x6T%e7=gT95PvXUv75Snb95V~F?kX)E-mJpg-cE3(Cj^#DUu&Yk^=_(+%j{t}3a(4n!8|gtnI0Qxl"
    "!Y!}hKtMReFcgq_v5W<zUbTgQaPYMc_X5Hpt=N9tN^$lAl6C^Z;kq^buU~)PDQ#{E21jNFH{Q(M%*dA)zuk2H@%x|u-IB;2w<+sO"
    "j~`3QU%WA&?>Dx&$aA1E&9h#7k><&PX*p4B&!|yu+!?T(Ydfueo7m*HDZTpJmh~KJ7y1|Le%n1C3HW_6AOo6X7#h&r&iY=J&M&>z"
    ";TR_tbiF#ZpgG3Qf-dRsMG2H!r5=u{{|FYneDTI-z27*kW+5hCd@DF+Sjwlim*w577IAmi{oSFPsy6d@YVW1w9;S9yOOE5DmK?{f"
    "mfW|_0LR4wj7%6^<|VqzP$#$4k_cVVF}fPT*Sa>B8Mvwwa4mM=%2ze_ansz<^53*>Y^65e*+^j4(vlL)>5&q=UlTXN(c`S8INW2^"
    "YiN&En`e8hmOZlr(85;%ypdSyjluq^m70CnUo{F7+FzwK-e28FO?ZEm@@#*V@^XKb%4&a=%3_PmiQ@R1+LCv^_DyX(Cn$4VRxiXl"
    "c_AsUzL2hkUCUD&7+hwSldYd%+v(Jsc=!8=4+kN)%%2la1h<@?-CDT3_;u&gumAk#kA@R%+9XG?7;@Y#h8*!?$Z@<FZp<R+apGHT"
    "*}-DS$>ts>&N<ILK-@BmF1|pyl+{g&E)KtP;|@(Hk7@M~w#DIB&hz@@+$y7fNC@Q@Ez+2-bw+>s?eOD$L6y6pr~*N`t_&wA7O<dP"
    "$?RBA?ER~A7ZmLUr7?}hf>Hu-O^TD00!pEk9=noY{D<F3LJtG$Tz4HX>x~Owy;151mV^hE{h7Y<)(<4CW?SXY`4br%VTEY{j^Hg|"
    "k@-;*F4&91jVALrkfk4Jf(P2(|1bS-qyS?mwSDi>=l(Y~`U)JFz`>3FH?~@naA4j`4)@<R!o20$zL%V;9J&sKC5LD)IrWp=br^i0"
    "TcV0NI0N&YWG^{<>IW*89MXm4v|JT%pvn9<GNv`v_PykAzpOZ7$zhP!fG_>Pge9j@Cw7wKUbSG!X+;d@uS!^QT9S+Dbkujn0~tt8"
    "ujLq5%dPEu$;pR)pkm2s)Pku1uwltz<N30ZfF-BZ(wqLqK{-1{<?I})TRFSkKoCZBszY#DXhvBs95_N)a)jbs<b<*0v;-5ofu$cP"
    "SaL-2Ty?aPZg8NM#S;xn&U>-8$ASGkDn6ZF+j$O-Ml3lR=XF83RZN2elg>p>GnSkdVBWoIFXURV<h&O$n|(XpgS2QMU?{oiP<(c~"
    "wmbIzM{{2h?eKo0T>2eZ%Ww+E$!?t6$*Bf7PUCKz`Edo0quscJAE$Vn?ZzG5IK#Nu9+#6JhjFnzF6Vxn1&E7<JuVkNuHbQdT;BXR"
    "#pCw4ICe8zguqzb1M^;HtQ*L9;2xRx;$t5J6NV=3p?NP!)(yniq&+t8h03~t7@P#aAvZ8%a54ag{Xh&(2H?1LXa$2)066LgVsHuo"
    "$NWGHP66P!rD%k~App+N55(XQ0LLvxV+;-haQtdy3=RWu{BmRr4g+xfdc=CzfF4eMJz_;{KoKXu9<e4ipox=Tk60BOP{qlwN34qt"
    "=;GwpBUZ)+lyUOw5o==u+Bo&=Q36!QwHbgTeqg}^0XXUhDjo>HF*gt@<k}3tIrxE$2Lf=8ZeYUT0EL`Rejo-1DCBhZ12H&2A*YKQ"
    "m@zm&A*VM#5Q760vO5ta;hv%L?(F&>w_-e9pZBQA&zHl9^(w)q{W-l8HQ7Jup2M<#68R_Hb6C1Q{yz5{mVKY%@1y8f6@Q<54$E7g"
    "bl4p_lVHA_Zt47l(o$>>{e;q@@#f#*cK44i(K~~A7poALPvYHC>u&H6(dMwfLE>A;;ltDGUn2XMEP<EEw7bXqHtXXiC5#RL-fvRM"
    "{wDrS9;hb;yb0yqO_F~TT9L@*qmp5F6aOacgIXE9iNxJavVRldo&WiE8dBl|n^bl#dWrh}Q%{GVf4&|?efuKs_g}aB>IcnzC(_o3"
    "eUuKbCN2BpAHV+RPrqLd=l^~unw9P0wh#VDw8!9&M1#Q}i8c)WNDDUiK7H$d*sTQPV67&faP$`Zahf0@$6RM5OTvyhNx(7Jo8^+Q"
    "V@?us%$@py*fA#wIOcj!kR<Gwlf?5hjgqiqP7-j;QSJv~$6Rfv1*+IFCkZ*`I<KW<?3j}b9CIT5K<t>43><R~oQxfFl7VBccOpy1"
    "jycJ|G3S3HcFfgwAUWrLAa=}2297yD5Ig2-``j@n89U}`dzt#XC1b~2Z3mLmxsaq_$DEXfV@?Wo%t--`xqR#gV#l16w2+*F9dota"
    "7O#pOb5ej~P8>McF<0B;d>#vS%t?{7c%ov-DIlq6?_iZ;SaOP$IXD!s<WQIg1B4=$oR&6zs^utQ$)O~3El2o7Ty39+k%S7C9CWbT"
    "X}NZ?8xG{K07tOo5Xkw=sUL`w@Cbn<JpMNtmK?G?AIJeqPCGU|l~s;dayTv|hZB~ZcJ_HHtDLdqaF)fZ7A!ejbiR<8u;jFZ$@3>N"
    "mK>JFK8F=c4r`q2RW>X+t+wBEIwWApkuVQHibO0q63aAFB9gG=2uK#(M@mF8mK@1EpN@9k6%H)20Ee*TwAAoBenu~=!dP;IZN6U>"
    "d}3Tg7yBGBEIDHH0Hm~}?r5L__L~y`jaYItE_TS8u;gf3e61AcHK^^hcvYO4wYD#G&LHQxpq%G^AkOC@3i5e4Ay<6lSQH#Nb^@R{"
    "mz1FMly3L9#i<?#T8PMB*3L)n{AIlrxaA_>jpN<8;>Q^r7sGBGxp6V$ab-7-{W!tnbQ&iWOBk1wrg2iSgmFncjgyKcj7tvFIH_31"
    "xa2a8lgce?`hJ{F<D_B*<5JQzPAXO~E`_IYQn7+@p)ie;%I#F=eq5QyNyP{QLpqO>iZMop(>zWp#uysrd7M;?F*XwBaZ)kC;7FOr"
    "NyP+%BRY?hiYW$1(>zWprWhRMd7M;CF*p|HaZ)kE;8>Z*NyQ9<V>*wMYJfUe1JJ=PPO1SaVGTeDyEv%^sD(8EE$rf?8lW210MxLH"
    "lWKr^xHjuNPO2ecaDXCqaZ(Klg99|Ni<4?d7#yIAU7S=y#^3;5?Bb*vG6n}IV;3jYP%t<^8@o8EhJwKX>e$6eH53dE(8n%Ls(~;#"
    "Kq0$0sRqK}0EO)0q#7850~B)d>ya@yKp`i;9vOoJ6ms(GQ7||_At%2c1%m?=a`Nj@F*raWXTKg5g98+D_UlnGI6xt1za9;P0~B)h"
    ">(MYcKp|(h9wS!B5p9ae4<tMgfWv+u1SbN8oZWhiSRqHCkX=Bx_7FS}faBI<#0ohAg`5w5AO;60<b3o4F*raWXSW_BR>%=3<b3u6"
    "F*raWXSW_BR>%=3<oxCbVsL;$cF}unvEqG%U;JE?INn0p@fOq_NZxo0;-6I2;({Teu_`jq$KR)_o(2D*_OTWJL0bsa^~skV0YcL?"
    "6*A;4XsZn{jD>1T&p+oaXi9k$z20UpB^mP;G(B(*B<ybhI0ybE9w-M4UII}Lg1?C^2o#zC<skYud7vB+coRf9@Ne=!IUw*RfO3%h"
    "n+Pu$6xvRyPI(KOlt#RTdaXO0*u}^{cnjJhwtoX}LG$%2Ipi(Wi>2c&oQ^M6__24|!apuQ|JDv765k)qJJy2c>(QT%wV?UoIN0(2"
    "b~a)yXueVpAZwvsoUK%sB_FaDG=pPdeT4(f_*j_cGLOn=#>c{HdtMC0$HFx8JSw9Z9}BDP^Qeqwd@M|}&OM}>@v*SlK0n-}1s@Bm"
    "?eoJuTJW(jEr@->{Xon<(E`{f>D&**?33C)Kcb-pvrn{8T7ZMuCt3je#7#%R?33EQkeq_qC$*gxPsHq#+CD!}sD#-kN{D^p24eP!"
    "Qk=*0lrZ~5Da|<qN|=43RKj8)W}npdI2QoI?33D_rj!mP%s#2@c^W}f!t9gUUKaC+*(bG~rU$i^G5e&p?<J?WftY<#+xL=FdJVvs"
    "eWDE5C&l`Kn0->)ZH_8q_K7mhIRwg>eWJWL7N(5ZC$)Wkh*=r4PilLf5}uSX`=qv)xsVHHpVW4mo+($s>=Tu^&^dzHC$)W{a|ZdC"
    "RTk_M70f=V?ej>m3TB_E0QQL=h}kEKDvmn=5X?TQ?P(f8RKe^M6~sR27&fYyeWD83CvI6OW}npd#Xd(d`$QG6PaLX>*(bGK=BO%W"
    "pQs}CNsp>x_DOBG`La^XK2ep0&QZ)hQ3dRio}H<R*(a)ied4~zhS?`-fPLcDqha=mS}cnvV)lumQq}G^8fKrU0rrU#0K@DPwKC@|"
    "sbThs8epG@dm?6^r~&p#?lrk#_K6x`pXC0-YM6bZ2G}RL`;8Vb`@}*(r+jL2o{|V`OTW4sCsPuEg&5$t7^frx3$fsFG$j#Oh>FMA"
    "ltf?;6`b$mQl63sEF_Fek|~M6LdLk{I3*ES$QYMQQxbuNjB&{}B@tLC7?+Z#BmxTs<5FZwBCtRh7m9Ndfd#_A5Y0&h76>ClHYX8S"
    "U<?iCIf=kpR0|H2If=l6U~nYPNd&efrQHprIf=l6U~t6dBmxVH!O=V?5m-<Rj>?=wU=L-b?*lE)Ndy)QgJU!&5m<|A!GSg>5m>}Z"
    "I07Z?NCXzK7LGs*I}(9KtcD{{!;VB?5$oXy^spllSj37r0!8dd1QxL-jzAMT5`jgmiX%|PjznM)>*5G>u_F;!#L74VW$Z`<7O^&t"
    "KpQ&}fkmv2BT&bVL|_r?;|TPzBN14{3ONFW>_`N)2L=ZyWJe;fh!t`K3fYkeEMkQmfkIAxJz|9%fkIAxJz|9%fkIAxJz|9%fkIAx"
    "Jz|9%fkMuHJz|9%fkMuHJz|9%fkMuHJz|9%fkMuHJz|9%fkMuHJz|9%fkJj90!vsSC!mlWiJ<miJW%E&0!vsSC!mlWiNF$8$O$N9"
    "M<TF<6><U!*^vk=VTGK4LUtqqOIRT%ppYGjz!Fx-2`FSoBCv!Nasmq3kqBxJ3=UApjznMyE93+evLg}H9=swERMWXENCf8MzmP;="
    "E&jV85m+mAz913QKDr_iSW;e*2<#(G@PFJ*<wp{MwH(1C5`ndt=rA;Cxvrr(iNGGKfbU5J)&iVE5`nezwsR7JwPN5i5`ndhy>k+Q"
    "wFv2yL}0Bx_?$#w?WFFML|~8gzzMtw*_=dRnahGiP`l`yL}2YK@0>(ntz`I=L}1x5>Kuu{T0C}6BCu@f?;sIai`<S#1lIEY-bn<f"
    "@M=xY7~fe0fBbp)^RGV|kD$oEZV$*i9zks^4?F^UJi2_mzaWoz1l9_h_ls5BFN=AySc}gw5`k`dFH}B>cUj5M*;(83)Dvu_WIV6{"
    "XXmjWNCgiB$+7(tafylAK2IrNMHmm1c}f9$Pe6<YsxDsD6c03;db^DRbaonn%+$Rn*a&B)uI=+Iu|_yEwNaj@6fnY>scU;)48)nK"
    "Yx~?yZiF*a*Y<_v5Y9|p+j$zeHo}>yYdbik>7Ix)QybYlrGPQcOkLael0*HgGR{nGj51SOKM-f8uI+Ie?l8s_q}o0wk{DwOQf<!*"
    "a4-d_wwLKSePc{PG8S6ADyAUS_IYT|7*mjH`#h*?f+<L~UFRYvn1W;y5gpkig?SV~QpV%TJc=Mm@Hm}E5hO=AE~j}EVLO4n8^`k~"
    "!j@L~aa;-WD1sD>ODXdxf)tEP(Rma>2;)L&9z_tsxDd~y2wRN*aU6$56hRmR!(|ag5XQ)`E}{q`7#c~7D1r#aMtBiL*p9+K4%D!S"
    "B5Vn+cLU2JiXe)?QC&n4#4tFP7EuH-436<4iXaBT(GV6<gpG2s8(0=m1Py`*>LQAu5rU&JEush-2@m8&6hW~XR-lG`6hW~bR-lJ{"
    "6rtrCU-=wbmV(|(lJ;H__0^`XUJ~z>Xho(MsU5A=jb5a7w8kRY_whcwmc#(`@%NF3qaX3Och0x6&qFVX>Ll%)H44eXOVSb*EZhPX"
    "XyPTYU@Mn^#XR?t*tpL5{T?YTyd?Heh_!$h$#LN&X@rz{Vn%BzrsrOgb|~N71iVSHg_p$0yIK->6Vip3#9Ua!dr9n};vw(7B<;xi"
    "-{B>>6;;MwlE$O?@RH<wezoq?yO-pzU;h1<U;p!$R@%0N?eV&=NpGf)HR)>;tVwUC!<zKgDmssjTUa~nK3=W$Z+_f@LO|@^kL`Tz"
    "0NK5*eaf_}9U!~6wNG6LwF6}Lw)QF0u6BUz-r7EA_tp-O-P_vZjQLtSKz46yPm5QD?B3Q6TnLALAY}Kp_A-BBgzVndK4sd~4v^j3"
    "+NXJ*YKMd+Cnj0EYQ~Zi5xdttv0%xGfZdyWR3l-@iM)`UC|Gi$#05BtB`3~v%he8sB`3~v%TY)HOHK-9{u@)ol9S@JxK-_tu;iq~"
    "i&xE9auQ<q_NpTlEIA3Wd!-*pSaK3z_a^rn8B0!*h2$i~l9Ld-*ZoGrl9Oy9IXPg-$sy05m?M^)4A{NhNv+x;Vads9T2QZc$XIf6"
    "p60Wx9SWA54A{NJ4J0f%nWkq^Y6r%WlL5Qe4-_mp8L)ekn@7WvlP%6Qc?no@N?1rviCA(<Tu4qySaM1#bM;s<mYkAl{zWbYOHL^Z"
    "ol^))P64^)oR%w$C8w~?H9!$8IR)jGbH7os<P@7ays7Sku;fr!e61*A$)UK|=TO3uLn+VoDrGD=lowwsDp+!;&|CnBu;dW&T;zzc"
    "<Pgi^RRv29iOxcowS!{GA+@<)CBu@#A<Rmn)(#O%4#zkP&eRSGOAe<r2ZuA39L{+za$K<FFbL1Od1S(p!?e&j%vf@m7dnRpOAe#("
    "tb3wj$zh#_N@@qglEcV>NkM=EGxg@9Apd1+F0-tZt%KlkIy+EOJ0S06YfiHRC9MPDaXbqJwGJ2;;JXwzE@51N>r(wVj0*@MnH!fe"
    "E+B+-@Z&HpAcS=E<1j8DgmiM_3dRM5kj{P_#s!3sE^ZuQTtEov&5y&lfDlq23TiztFeru;-9X03pcs;0f{dX-F(khR1!IF^NPZCt"
    "1_#BE{3;X-4vHc9WvCb&6hrdsP%$_thU6EbVQ^3k$*)Ai;Gh_iUy4`-!x)lVi;8tHj3J%;K*0lb8VagCuoi|fq>CR&cpy(hL9GV{"
    "2k7DC)}vxY3}Z;q55(XAO`P0%RIG{>sN$6UKnxDh#i{s#7#yIClUt99wXp(ioY)V<-~e@;+<H{3j}_?Sq<$a<2PouZejo-1DCFeU"
    "qhf`uKp`i;9<f4JppcVak60lqP{_%zN34()DCFeVBUZ=?6ms(G5i4W`3OW1rh!wH|g`E9*#0pt~Le73YVuh?gA!olHu|hVWkh5El"
    "h841*O)>d_f(PpKKuPU^6|w<^oW&0$JdmdcN?H#L4p7M1tw+NO*?>aM2R{&l0~B(0>(Q`6HlUF6$q&Tf0EL{-ejo-1DCF$cqhW<?"
    "Kq2QhKM;ch6moIv(I7cN{9KdG50um{oaYBhS{GRyD5-sf76(ddAI%GLN9|*AaiFC2d7xb6w@2;<#g?gHK$WN$V;lxw+f|-ZC2E&M"
    "^8+QViw&s~^=i)Z10}7C%%~EzLrL=kC9MljsS>pZ#rc7f)`g~2iQ0q1oH^3ElqprB^;ob+Y8S~<szmFtppVopnx<5V)<XtViF(b#"
    "{6I<TB7Xx_f?~X$kwR37c9A=(gdEC?REd16run}vr#~;}cBF*q{(ODpO0-7vT#4HB;Bq`}ujmdt_FRc}t+?gN?zcsqEZ3Ow{z!?_"
    "DiH;)d-rM_1g;|rT=x#$I0#%v6u9pFvT+c&jwo<l-ui(!a2-+L+CLEot|JOudvI{zI-<Ze^{+YzTt^hR?qhm!5V(#gaP7bu1g;|r"
    "T$f8f5C^U!3S5(WRUEjEC~)mx6$h>(3S9TRo;V0xM-;d&y{rxb*AWG-{XF8pbwq({_ryWqI-<ZeX+IDLt|JOu_p#YH2wX=LxbDLp"
    "aS*tU8C5%P%`){r$6Nv&SK`$FTssszj;8+S+ClL+oBE&QmRt969ObG1xpu&~kWBs0F*C-6<JA8gGh<wsrvB%+MfrE*Z0diGTlLw;"
    "agwM0=h^||A~N?s$E+9_jdTBV%!-jwn){z?4-C!!&)l2-UUD1>V*iRkz@JPHD(}pJzs!2MwlG?)AZcO13!_nal%~gQHr;GW;u`+n"
    "9Y>z^s@|{rab|W2sk>iQW>g-Lk#UC)&-Kqjh3mBm>bd?|v?Rw59o=*Nv(Ve+;-Fu|Q~k535wDLO&2#;;(3`*R7@q5&1-e|kA;AdE"
    "@#tMH6aFlh3BAUnvs|`{I9TiVxqCXaQT7e@bZDdX8}8}Q#$3%xu5j!rsQ?i1vszc6bH%M(hLwHq89j`BeM2tO-o7P6ps&TfT!xi?"
    "-;f_LQ1+=@W;XTQ`y89NH{>#O(0J;7j!o<vav4U_KJ`AwCgu&f%&6_T_c=DvZ^&gvt-_tW7>QPI$Yo|ximY;(F}J}BO)fLW{Hw@i"
    "#%}j=83q6kxh&Z7YpMm5zrFwbKcO+m_fOkLk<3_k7RikDmm-<5;Z`KW4A}EYHOsV|eR5K<{_=xJwh}MnpJtea2H~0^GuL;Bxwu1?"
    "52B~cThtOGnP<BENS5t<EE`!~$th;lev6!1sox~0=tpzWW`(1#CbeEjSe|($%a6>5HTIq=V+!s2y+$9JH>fg(GQU9(t@BT)GN#mi"
    "gBW6T^HZvfm7U+9g*KQssIuGMq=o1~^PDQX?M+(fF2bZ%s_ag2QsQDH7jaT6Rd%O1DRD89i#Vy3Dz7dlD^+$UvacVhvSYIUFHV)w"
    "!{nAKqZ`Sf%DdcO)Rt{bmOuRX`4^zeac|#dhqRR}SI?B0EW4BIYV5;vw`AGzZF8+Db5=h&s?LVDG-d9hyul)1JAW;iyNmJ$i-yI8"
    "YsuVQl{c6#0>52f1pXobYSGR4>i{Tt?w;!c{B;17@bbB1u<+LbP{LmXK<QaG=dS~xgue)YTIYBj00qx4it#LSybgd8{vrTMySd|a"
    "0F>|-0Z@xF$X^FQ!E^n5JHmAUlnC1!EJU~tfD%F2=R*zG0Z<}b=#dw_Rk+b3hYLNjUOL|Bk%NBj7%ak#9y!=IFelvTk;9c9dDeJ_"
    "8$EKk&?B$=c%w%S;W_5W?OKlv&-GIzm)o@-S#FocbGcm^&nN0Aw@cf(+%9bAdg*s*I)}&lsq?GcE-mMByRe+wrQfCD93IQ3%161W"
    ">vg%XoBOrj^}1Y`&BM}9U$4uB)qG$3U9Zc9(L65w%=NllI5DNQ-}Sm&_%P+Q-}Sm&xG<HapS@m}3lFAa?RUK{S01I?($QTn%#}x}"
    "SUX;?%#}x}TsvMb&6P*#dItUV+FW^*u7}WHFV2-m>3Ryo_2OK4l&;4xTrbX*N9lSFFCCbqxbi4n4kD%$e?$2w(G2@s`6w}R__^{?"
    "Vq)(%#Azumvw5f$jxuja%TiqC>X0j(vpWpX^0T-sg$cJ}uEf02x4bjF^>2u|5}4;Vl#f!Zijh^!g}3Gn<)g%^t<S_<DZ*Q_wiFi%"
    "%tg$V@}$9hl((h4(qJwlk!KC&<4EL%22-vhIcYHE#YnC+nCnQ+8qAB4Txc-WIuaG`#9S#)o;Z)nM=9A8=U-aPg~^LsF&AE%Nz6@B"
    "{HpvJ@#D`wWbz3Shv}bp50b8|rtL}6m6A_hqLGje>VN!{-`96=@GOiH0i>+M|M0);KY#l8X@B>r9N(Ap`Q1<N|7*doO546_S7>sE"
    "=4NO{+(YY2=vHWIhUOP&_hVCiY<`8NXJ}!DX79(Q`q;t>%}mhHiatTRADeDtQ`-v7&(OpS&E1bpx3OWx*cn=!p~(f>{n$(&n_QvU"
    "dEu0r!TI~anLapm0=KN3UclXt&i2vi6F57AGc&kwKRVk-cRCJ~(x8J|&O^8#o$I4Jod>&Y>~bLX`_Z{Ry3>K6>@XeNaw7Ko(fK~Q"
    "(}|$8C>`8#B;x((d>`HENZ1+g^l~QR{pdm)oj#oj3K8$%mP3*5M;F@YuzIeWNmEWX&D2gyJA=F*;oe86<O9e&6DbY2K0xOCQSN<|"
    "+B|}sQ5x;N6Uh5f#y(2pA3-i#14nRxEcc^~eUu=ToI#cuc`y)v0(n2m)JN&{1IQ!KAc5H*AdmY|rasEx9zm7~q}lWg@_v-LjS^EQ"
    "KY%=Dkird+WxF3`ZllDw{S!zuW=tS~Nt!_3kFxYpD*FIZ&y>f^WVVR=QI<YRc31k_$4`w78!VbJ^2}9WTITMITko^poHe6Mb1RnS"
    "VrlLln}>Vo?B=sHckaHq*ALC-%=G8x;c=?reyVnRn5y0Gr&{whug%w~ngzUgm@8HYUck$xgM65+mFsN9(q27G7n23tPFFupSBodj"
    "AE&GDch;K6*_!*Ewf1qY_I_urdz`9!GFAULRsUpX{o_>qI#r?O_Th1^;k2`MYVWp($zqM+rG1>+i-*~wWpi#X_qn}%n68uSbf-F-"
    "_|iYNU+1gJ++ID*7Yh<E?T@*=ew?pf=c~85{UeETXA(7UuY06X&Wc+>$;~(Dp^gW7db}^+XOQB4{^9c?FJZv=oxFrG;RC34Zvt(!"
    "+Iev+HaWileRHH;dU8SBN>6Ah96-&RBke+z-^8sDh1SIh=$j+$vXmF%R+hqO=>gQfInpjtc`0s1DlEA?0ey3%U9!Ts=3B`MW0wb1"
    "_vTQ$faSHg7qGlupuRcQE@yco?&T~DB_2@yn`7<bmOmY;Mcnessq$}*wM$+8bgCAq%P+?&ygAk`eEHL{T7)mZoU8EWSi217Pv>fp"
    "!TfTt_BY4cMX_)?Sc@nYmXo!=Io2+bh11DeB(ks^t@!3xyI>ZicrKV>Jn97b&GB~mEGYe4J_~x1DUS5!n7f#U!J$vZG|UV<L4I@0"
    "U0Or)@Kb3GgFXl3{N|Xu&=#C}F0^40><RLlWA3tB@b<av7G_<-QQjPL7vXBU-CGe(VY1x`@|$CBlAPLvd@9K)G${|r$D3nr0-f5V"
    "c`DE;wDwMr-yC!4V^;pDT&K2)y60_sbIhfWnX8CiiFc|Nbe?!2g=W{8ciQIWRz5Vh>b|+#9-2Gxq`7}=9`2ia`_SCG`{v<ss^NaB"
    "wS4g09PNC!&Beo1(d2jE+&?zIpK8qwyfl|57J6>39;S*Gzgy_~ajN>sRL$d5&6BB`$ElhpQ?-v%wfDPPYrHPa-IJ;M$Eo@!Qw@(("
    "4Ns;T9;X`ar&{Zp&dt%lciUV%Ocg^jZ=1`9sY-c2)mjd8X|BYR=Kityld0;*sp=<FeI!fr30ablWC_h%^4o8I&T@KW9v`{KN8#bo"
    "$!o7Vg~D@r=P(NI=2#~n;=^#Mu*T=GN@BsBY9ai~TNc9Y-McK@!;4DjrGKbChz}o^(v$6$4V0nS)UT5I<-hFT|BOKYuW!FO-hW?y"
    "`sVNd-*5Uy|L6MAzx(*j-+$v|(m-26lF8WYjssmxl#g&1m+W=OhlE#Y-<-C`Ui@B?N3*2&G7Ep8N5CWCpMD0&*5#D5Jz_E<ivvCc"
    "2&S#G`q*=ZmnjNwBwW8G$vqq%SV{Oa{7dXHJ6wS8_aFZJ^ZsWZX@r4+pkV^0ZxvfKyWN35k40Inloui8V~ZIE?`^O?CVg!C7LUyr"
    "t77&uJXnx#iZQwXuUN{KL&8GbGP*6nM}P-+!Rfu&P>OVi-kd#*mBmFB;}Kz)$)Mr*$NiV@KkoVO;`<+XfXM`L?0&<^r4W@ayWEt6"
    "$#33l@X*4?%$}73>CWd;BFtdlqy^5`OaROG2LSXSt()W6wj7f%0L|{uRu|=uO&E1Z5NxDT`;jAXq0x%sbqP_!wk22%_09hW+yC<q"
    ">GONomv8?5zx<bP-u<7y6Y|~v_S^sT@BZPp@813Hoq)Y~|NVD={48ADe|n$Z{q*_M`yc-N?l14lUw@O}u}J^4e|q=%)BgVRPrpgu"
    "efQ0`7->&RUkRv)04<}Q{<$3QSKwm%L)r8H@&1SW@vl04{PCCXKK${s{^`g4hu^^8@t4o#w;zPpfD;;)SUI@OF%HDwXDlkUC>3r0"
    "&_6C;+I|lk`KLVsb_@OfhtK8Hr=NfP{O+gkKYsr1FMs#`r%(IeZ7^Dena?<-|J!iHUumq5Kmuy079dY%tv<j1P(Ho;u>bfYtmSt="
    "KQJs3h%>phy$!(pKR>@OpShnzr7d}mzTNMIz0_zV<8bpYn3(xv`Sh3fsr>%?{qynh(+B<_jT2Rb@?w~-k_7k1^3zX%hQImUAKzVp"
    "wiWcBKJ7pJ^y9}*pTGOvAJw~uFMju(2h#RF@1M(ezyHU-e2DaIKu7;?@ooL_$MOTu*HazB3xsg_{ZBuBzyI>)NB=#ydu74_ttis|"
    "8+?4s7?a|BE5Gyzn7;y&y#pBUe%e3$_<bP|7HvyhXOlqu`TJjf{HJ#ju<@I3f#<_qV4U@i-}XClX{Ue=e_O2$)b4Zn8=QJ*2N#C2"
    "SiW5iT=?=kdCQ;nzw)OD4mywvZNDB;AV8@gYoMG$Uq;Tg|Ft7}<Prd&CtbNGgTes#f4}XRWPkhqhhp`+T>tUSw_0GbSPt0!Do{&+"
    "W&bw-l$h2KIBvN>{OaJK_dmS<{2q}0zruvIrl25iejUh~ooCO#07#1k1t<*Wb&w{%|MZ!Fp^ih60p?|3atGE<8w}VmzY0)DKY#iO"
    "4qb%@D`$SyUfA^U!-w|>%wj5-@T&$V<N-VT(?7lYafj=g_CeTho&I$&XBWF~zUA03LxB&k0~P=DK9_gAmbj3ZHq?r*1vyR}r-i};"
    "LY}nYWk__R{rmyX1)!Y&mQuX`itPmsrTmcblwk%x`Rn$=lu!FlI5hN5hO1)x7dWyMB8b~ceg@wEs>4AL|EYWrLX&m^ZMZ`GI#M;4"
    "kq4k&QRUv?{smCFR$T+ARBN6}B>W1XYko3>N~PH-!`H7}QVg%hJwgqdHhr8I5-EI_%1cQ3`e9-sLXdDxg!@%zz54|t-eUC@J(2R2"
    "#gXa}+OhxqJ#*?#U~KFyqwfC0r~N~TKOaZ=^oNo@e#+*@{nJn7yCx9*;~NsuKY#PB#1vrPl037l@az@@`#?^^W?aJf{dZNce1{x6"
    "KticPuXpOFpMOBPrBCh0pFh*Iy#AKT-dwNA_6P3v+x?f1KY#xHr;n&^_|0!W$nU;0#JGO<fd>xb?icQd^5Mfr)NnXl@4F?N1T&@J"
    "&iGXFw4XnHhK7GG?||d|=Z|ooeD?wV!%v~8ru6iw^dnM`?b|!yOA46!Bc^=!;Sc}#yFYI4%)f(O`3Zz2xosH6&Lu^zWl8-X-hcY="
    "*ZouZ!~Vmc%TFFT4xGSuI5a^i4krHhsVHjyQa-&uei`FBjpz6DL-^l*gm?e&<NNdv`NMl+`s*vXO(-{B!aM?IG^5C$>jiQD`wmj@"
    "anud`QVfMDDr8}Tb$458`)L1!BJyuO&deU6xFwaGywflEKYjf1<M$u`{L9y$9zj?rq*OP@XR^NFDMF7DGfT!#cB^jImv7N`zx&7k"
    "{QZCW)4LD<{NcNI>HFXO;UE9_5AVMFF8(p#qi=xQKvBuuoeljD>BslxGojX(F2Psn1*8Nj!`jGu3h@JwQ6v%MN4Mbhe+$IESkiw_"
    "OZva^lEQ2N<Gr<a$Qgi?Bp^#jXFgXnL(=Z>xcHf%pxPC+LF$&=>+-iB>85>me82zsrw3Ys75cvQgRCwz`UCLCc)xAPMCm(f5&mQO"
    "@bS|x|8f7Zo>LgA!lGVUZ(n@=s;cRqBOX1B1AU_8Qf+<S?SOr!DgEJhe|%>@(1?Wk{XhNk6YebTI?mQfV79c{W~%%Xs<Tlc_5~Bv"
    "zzF?BG*oKJH52?LVh$Q!xs9eNzxe`>UHutW;KM(oZUHlKU639R=OZIoM@<nBEBnLGA7c6R9o{RX84T)+S6suz^&{>TI)j2pB^DHD"
    "M{DRaQKPeePQdVp05{OL&VP|A)07`RfBFS!vc}~0LdnY&tNNmMKfeE4`5v`AM0zJ0d9%I*oz@pEEBe2mlP|vV=%2S%qdMuUXr;lj"
    "6VBbMAN7CUKYd0`T>qB*&ByP4OLG<f;r;RPPoLiZ`Okn(u)*Jb*KiAOQvrJiG$8y-!T$QmDNf9|-LVS7PdoB^reD$kPYvAJj4#Lg"
    "zkUAsQz2&1k|VVnVlXk$?@-n75$GPq(j$s*7rZO9`vy}NQ1<`F1{EtQgTvMPACY0KP-Mm14Q*t#!8d>Z&5?@t`zDarJN84Dc%*os"
    "4F>;H;;>3&S>gsSw!%+gm!i^A<KG4~_WnrlZ&frj@kw#360$z%KX?}okAG%ys9h(8b><Izy7i~<*oU;iyV_cX!vRl{xUCKnTZ7o1"
    "u@;tqkMCLw3(%nh{L9gIRDroTb5uC(drBnylF1<Q3%4E7Vnr(Y+iET0yUuJ;`{O_t7WmWBpSv?9BxS8E+aX{O+xQQD<4<E~yg43X"
    "=NE=&fPZFXG#cr6%~VO7FK`KBjxl-?3aw2p#bb#ad<v^9`zk|!r@4Re2S{Ah!V6JX*dDs=nYCA=1ol+G2!+wKim8s)@EEgdqtaqK"
    "<dzM8Q_8|$Iz-*^;^C|G40oxx;xP%v80DdJsiSwTM>uK^nkUTA%{_|hJxuH2?dXxAM=AX`^vK&|51Xe^L62<e8l6@#3+`JyE(ZV0"
    "9h%nhdga>wLUTYFW7|5m6=b+RG2FW65mqer?~0O=ZzC1H&qW-$K1QsAeN76^8|^ZDN&pP8V1R97M`yEop0cM?2HlQGcn1?W@XRET"
    "Cvs^mF!c$Z;uP=+jNlj$R2GVVl?ZZnov&9%*b28k{E@l!2B$1L+80<Y9|W{Z0?Tp3-&lFvCjq;)!RbLnqUrgfu^7yDSngNb`1;h%"
    "Pca1uJ@w1e);3H}cevW<t%7$jp;+7Ou&x0<D|lVeDvVe}f9|og6({<XXnY#}f)6UqxPo)u@VsT5HTE+}YWf<`3ZQmdgF)-8pf46y"
    "?R_n^hTW*mVv)T)o%G~$jCFvBiD<3Ic5@HE^nf#)O!0c>mi!dj>(*YiFJMbuyfVFIb}$}CCu95z$LKu%Ylj)N`S{@RSI1Q+8A@BB"
    "WO&dz!}o(WL`|~_u&9SuKtn|xgE|td9JETi&VVx}YkInGaI0FYBVb)Z@}1~ru@*KAXs`gu4c0y-vyBylhKOHT6&xt-K0xxD2AXV$"
    "ZWW~TD)JY^;jG3nWDSQomKhTCa<NSo3+~ZZjm9dEU;JGU-^HuO9M%O9VSYdyb(W!s63}abP72Q!?k(Cq7z<%EjR2mRHuLuV&42Cp"
    ";Z{^mrmf8yb^!Ql-T~SdgZFiVFP_5>0ADWf0W&gTPaxD1)F<IJ05|+54#NG6SRq~HIpcvZ+a5f&MwEwh5p(?>-z#*QisN5!p(miE"
    "dEh<1MI7CHEM_?Ya9R_$f=e8@0B0Q1oXD*kmDBt`JeAIoSjW%({2Z=g4M>vs>|os&t)m9AOn05^_?-Z!ju?0ti2q6+7J9+AE%HEd"
    "rp;32RBva0(0U9$fLp|rBey87w^;5bK$F@6eTQlbv)o>LYmrQAvE{i19Jksc>JGy$EktXvD{jG<Qo<&AA7?sbw{;h=LRH1EfV~=3"
    "0a*Yk5AI1o8p&&~w@N?piEort5;Tqf^6g)Ws1p85v~z+O?O;Dd8$0f#p#LHFm++D>hiv>Q@pU;SMCLkXrcVI(*xR@?(!6Z?zbua("
    "@9fgr7#_RE@x`#Iu>wdP_pu_>MvXUqeIx1H`#d7}9pFvy<2Q~)bQp13Z|oU6Erx4WHd^eogSCP!=JiU<eG6U%;Ws$i67kyFe$H{l"
    "h#$tCgL@t+C-)~#B#Cw(5nmG8nFkoe=M-9<bhP~v$fYU9y#*5R9fW5ZxoB^2teZmmbx7vT8a@a=!%CU&;wDKj78K~lbjIo3olk><"
    "^HA5O0QbvOSKzr8?Jg8Y8Z*(h&ZKd!ZTvfqSE@exXQRej(VfP+oyQuH|5Ni=RUa!*h=5~7>fg9kT{=Ykwt;;wjXJe9u#HO_A-N6k"
    "d!@CJ`_kruhXguR$FXZ32R}E4rHj}O6!S;N%!SJ+CP?Tzc;@u?eXCH~ssq1UcjHW{;P8dY?N^@no?{~XFe_)Y-Wruh(kP#BOQKGm"
    "XcDdtt|JKO!2k0t0^IgN)G7fcz)Bt`X#xA#Lh{fw=e<cDW0llaTOgf*kp@5au<CJ@Q0{E_!}k~9RK6R*wvE=CfwP+iH*)~<Y;k^3"
    "<~`LnG*4le(S@7Ll<bTyof05iInH$M{3wbqyqcQ{rhf;1l~P<AlY+~sy#pF-Z2hk2D}q;Zr&J(AF8TsklP$NMw-V<-cT|{L6v?{;"
    "umrb29?I!@*GGkI(oFaL;Oir7D^fs9QWa8uctSUmLMj0#XCK@T^AhEOwxqp{01&{}bD|O^h!n|!2!KKWaUgJZj=DMlse9`DbHzXf"
    ">t_nDFMbhrF<br(Jt8nRy$3MF$cbz&5qvzsq#;Q*?rnjAX%cWPCs<qsw|QVlNJ_`O;x+0wHiNwR;VK<i=#ksn{NTtsrbk&4B}@uK"
    "3SFNs-UoZzUs$UQD-0a_Sx!bi6y*b=y1BR4q9C_#w8Hg89v`k=<;(7Lu@6)-^nEuxDqJs^Wno67&Sc@5lxlrc9DO#Rp}aCq6}zq}"
    "NX0>|>yGlt*jGATGH-j^HD{2rge}=|_T*ki<LA*FM|PDD)Q4r<R?8fL3|3B2jQg{nMVPtQy6GL3^+haqx3a!sX$om}mEQ&MnN6Eu"
    "fYv?eFGyD*N{W33EZ<5$f3w}}{7&&n=QRqc%f!l$=S@l;97TQNiM^iMn1?ooS@o$6F1cRXSdaRwxs7{h<9H5{pZH0}tt|d{?k8PO"
    "8qdS@nC{{Bd~P4c^Zlm%KDXb;^LWu-6F0GKYMC8km|vdY3^G3f+Fv;x&oUUvT`n|ghLX<K@BlexKkm;a*Cok(k3jlZF~&MaGA?rA"
    "y6jD|kKyS5xy~Jcl<(s-Azvvm-kyMsx>3hNk(@QOTp)_!^SqN*SJFJDF@UI+nN6rz0<vGWfa{5PRy#O7pmQL^i(ILeZ=9Iq`$AF+"
    ";Z(fUkJg(6_{Vl0Oa!tZ49TeQ{{sI%NSln~m$;T@8`6noc}B!E))nqmJ$QInqvLAz=<H_`FsXNwm&Yp74i{RP(016low$Cq3E~Zp"
    "yk0m+Z;qF4NFareH4d=1(LchK)LNm=8;*SAlEzb#?M2mRz*lm_NEmFlvCcmLe{}eaRh3FKOtA*N!trfwe27IlcHKyT%RIw49pR^&"
    "@l*N!MdIotwXO1=lokI76C`0m+C-xL&3IKy;k&J&Y9yhrh1;+YC%}3Og0(4bS>jI8RGU@u=a!|geiX(k=dl)9wWv5&!r^?vVbsc`"
    "rfaQh)y7^WFF9i|&mj)|F7hd!^^6V!Vep9+eA_CP>rjgXWAWT4`o<{~;6_$BgS#wn*EF4Of7knE!SAk4%Js8QrESuBfrLbCPz1uv"
    "_8Y)3xFP_q_GG=m`FJN)U`q^~b70w&1I`9^1trw$Q+ltVXWn9CdDm9G7VD-xYPWz{3S`Ae&ARk(zvB2|RUO{w!2Y1Xh`7Kl8J~f("
    "t(wJ*^U6(q?_3Fh$v^_&pQfmbdlt5o^;Fu>olWb@R8B|}`CBW!L3`6gKk2*?mj*oDA*&V36yzy$yVjh`gv*k&Iz=Pz1ys;XI>A_V"
    "f_8gbC#YtfAnPo1yxRqaD&E#)UO>h3Li%6(W^Z@a|I%55J1@oQ&g*v!-a)|-|8H>ausrz8Cqep2F{CZr)5B%fb9%gEh#y6&lNwEd"
    "H<ji9X-C;gJMALl{u}lq+=;Z+o%l7n-?o#7o$=!<G`*`Pxych@Lybfxy)s6e<LnF0e$S1{!K_)|59c{J`b`ehAd5k}Zj}--3|itV"
    "?d0<XziX=t{#G1aio^4_^0RoR+RB~IR<~cW1_~Ge-8iMKvv*H+r?1~v*&jUPUj+K1Ee-`ljsx>Kwi`#-%2Oyf(huB3r9jL10eTr|"
    "A02Rt@HfzmNH`}&)4qEe!&Y0d1q{o9&{O;~nL%Y}oW{8rEA&$PWrkLv$`jPI{5t9g`Zv^Mwe;nT&Eo4VDX{Ndg8*mJR-WSl@>knP"
    "o>@oNbB$P!-<GPeXM=*^bKxF!<BN{UAy-pCN_756?OrXUBN((Esnk(<hFfc&0~yfHFywOAAdI|q7>^df3Pb6297OH(ML)gv6A$C3"
    "6_q4a=*O|E)7YE+gY_1}3Q$);@C@wn2+5pgkktgqkllxPQX?Mw>QmonPNS$isH&Fk!5`DE`wNJtdHK{J0`?fVN07|aF$Gl43y^}U"
    "?xWtuN3aRi^E-a|u$A8mbVl)xG7B$R-!Ch28iU^J7`mQ)vWYaThP&<&l0B`DG#%2s%XE+KSN%^T+04~QBs&`Pk+?K?Ojs8McjaOi"
    "cPFTMuX=oLuW{Y>$$DkrtE|T(d`4Q`-?5z%HI422c++>=zI&XLo2)X0xQYVsiw|y$qGaR+jkxcJ{v*9TVHt26aPPrC+T2O6BNA(;"
    "+K51=NDm`A(*fBb)BKu-rCMH1N(=)enDKRuUk4mW%b4hCw@yF6OTdNuT*9un-<5t3#H5C=m8Qb&i*gguKJv}T3Ql`AwSDAP%{pB7"
    "@YpI34n5f;OcDj(J=`*tLa?@5=Vnn#vg%UFgTSajPrCG~Q0o|tsQ01lQXy*rF#QPL6>cNDc|IKRgXlZ5B@^MhcKz;gAs^svWa70C"
    "7|B1)w=KG|`8F@&PEm%me%7fS)f*t7KZLWSqo8|Emu+W%G?48BjZp~J`LaSC?HTR8$G@Eg9)X`@Ys>dE*)}pr?|fbgofk}^Ai4%K"
    "(D_2_sLux1*7O7{SumE6OU`7CWo8@kQ%_dX(bE%^-j3=CV6C1kxxQfrTN|hQ5q&b`uwn7p9lkZSXSwVdTRR*zdpuG9WAu-t<U`u^"
    "Y}Bg5+`_|*WBqoSzkSrpYph{kJD$HTdOSZ+qO9vuwrNieL%5QgCk>u1iP90ueQ)`v5jG&FNgP;S`6OBSBum)g>RIw6t)dpf&D8rK"
    "e;%L^qS-NU4C4#>tG^&~gTJg0T3@8u+ZVo8>R;&77@hyx(OqIbo#yBtaRjKAA{|lJ4(O-nhi@g~Y`5lTSFZH?L=VWTVZoK5)y?IK"
    "dr_uod7htOr+3rNP$H{OJ3|BC_b_9x>?c1=H!Yq6SNng-8M1ENI`s_ct21O&=f-)~zUt3Rze!tvxAbS8(kk`v9k}mieB&OXe^KmJ"
    "0~nMTQfbq-T&*VW`4v7^-^$zfH)}=h>)sQMwv}fpL5Cx^F;)FJeF3l+Wpz<?+FAiRA$P^609b*Bv#UOqy_{VPdeaiIr$m%8+kAo7"
    "38eQzhh16H4#eJRc!`=Ryf{OarPO<rza7wSc6TFw*|SBz1rofR=|hMi<+S|Q<@z+~naSIRBxSajboljm`V#$Ny}w~~i)eQ_dYNwQ"
    "zpYV=P8t%@V4~!y(AUOqy59EevFe&VWcbCxCIsiucg6x8y51|?(Nw)P0b(MLLDGJwHa@=fkz<^9Fbsd)C;R8;{VNCSppzrJC+R1E"
    "Wm0eKPq!ZeymF_3VS5W%k0aXN;VY3O?L7D^s=e0uG+5I_?J`n6%v#rcNYOJv%vMbDvmN&_T8&^YXsto8-P(R7wEhdG3Fc_Hq!3FE"
    "OO~UMbFwfYLDuSU820<xIKqIrQ#e${uKL&L&-^cZU*zUlN|ZZx`WgKL_bXrw$hoBMg+vgN1j#OQyCxlU`(3E#&69QAlZ1J6BPLo^"
    "%Cxekt{hq+RFOz3GU<HKiVO40jN_;qCrzN&hWuDD1ILw(D6nnG0^Ny=fwRiiku8?Qe-gK=>V2`Bc^!t8t!Z0WJ`8fSLVtPmW$Lss"
    ")K=P6D*c@Q8M-#<uPt{cdRRv<S1-I+y$eCAAZ-%6s<1t;#+)RMP(i6DI<l9O?_%{@ljKnZH%}Pymjl+6>|uKK*JH~BYE(&{)0=4)"
    "DfA+G@ULk7ag?4Q2N*=e)$3;jNqSvl9IH>O1=ty{R@^khTS;#yF-0c?@qf12>kzlmsfKVp?jk;LM5q^R`(>1Cw`$0bHYvHc6LIF>"
    "j3e2IIL!z93D6efSG$Q^&L?_rNOsLfd~d!&fDh)&@PXnsND^ZUrRkJB4DUwvK|=rA*&CC5%-Wt-zf2&=qQKW;8TP%H=5^yU6p!<%"
    "yT<eCk&SXK@XQ`50eUS4@;l?VJc>A^Pl@_=ma6M6OZMs}d{=B&^u*D+;k&Chw)P@M8qsaGk#0hk$&9X;3UiHub`7m<hZiVQI%TW2"
    ")DPZEqIS0W_@W0e(V#SZL1i9Re)bb)3oPsWw%mC;%tW|P-l~DmAe^}<IwkDqGFC`ojHRtL?p@zE-}Vjbdsa+>`DZaKs4g}Q^%Q@D"
    "zG$wPA;Gc7L^PA-73nupNb)~b2(m{vAxy+JrO4Azu<e4!r26<ZYlH%=qF{ejvE$#s2uQ>UQt*KEPk)AHt;gM1>>DsQvOv%NZ|og}"
    "cPLw=tJH0}?YQ|`>o{hu72UUPmA}UL@jXx)B{%kxo8);T-3({`Ch+5@Z;H15XmQI35y-qCPEU#HYyh=0h$l8w2@AN>!9D99)uXG2"
    "*@gWV=+D3r;^r^CrGUN2Om8-_u(n%hmw3|pWr4U;<BQr2=m{#e1lh{f^9~$8P=M4uWYAm0udO3+k9^;wE*s+z$h#3%XP31n?QSk`"
    "4%K`PgY1xNd?v>zBG2rP=?wJ<k`THFF~!fcm=)4s#Q_bYKARmfZ7qHWE*kqZk_IK0&?8~Gl}7KdwLNB~N<;KbK-qjx6VLWf`o4ej"
    "`};Z4#gp$&*SU}<zS_p`z#eX5_RMc?=J1wqe$wLXhSpNn)t}etx&H!=-}o2SPwvZ3ft<H~Iehv0*|+yEoYyb0jnGxSt7~hRC!Hsp"
    "J>Z<$iUKVRNX5_kVfKwH+xj2HY<Sii<6bpe7)po_Jo)KH<y&fFu9tZ41MfsJYkZYX<bMftFiDo<hc0HTk#wkWwj?)M@(I!{!VYLC"
    "+R0UpJ?0Kqj4b2iwPQJ2j3Velg9cwMNT=z(z&NQMujlo^M#e7Nu*(onQSa#yH8T9rc>V0Q-gS(X&H>Nl>GUQ(y;uGNZhO;zz|8v}"
    "cR5)QBl~c+lSBS*+obu8%V>S5(Vt?-M98=BELy)YlKMPdKNmOc#i>0%l{c;J1N0V?hVcz-kLflXxrMfN^rhyd4Zo3QbZJ)i7P0SC"
    "wYxVve6zR*_V^Ut*L&-hca|2=|7gpJY{IEa#tvSEHL8Hl*|f4<`pDI8=IdG9J74AphgLwCTW4!y{X*xI$mSg<$tK9^%@_<}1%3hc"
    "ILGRnNb!hKSM?M~EqYTFK><?37=PzY@>YF(vOu?lVL!-pN4D{M;tqC(El#kVv2li(5Nmhx2oGqTaK^;h9^SM^xK4rncg4(=YUZ_F"
    "qeb(3ohsMXV!6hfRni1pvbwN^E=_Xii5Fcsz)*cMVOqRWExL_3To3<EzNTG|AZpZP<%!jbAIl75kb06e<mACD&eT|$Sk-EiKl9~z"
    "I`iG_dD^Z{WqSM;tr+5CiR|Ot<|b8(2(4Uxm#pP>f7{;YM`#{sS}5e7WYr(J6)U^%nQLcyFYBq_^K`~9eQc;zYOR*1$4npi<g<NU"
    "%bZTJb1dT!9T@&4!S@l5NV>N7bu|fx;qKuDIn#_5?cV5ek^_U$8)e-E472G}Vc;>tAl{?x3Vc<O4jOJw%v-;)jAc}fjUrta>*V0}"
    "m9)mwELi7~_?G5*P^4z`>zzZVP}lqc<77|gx5atZzK!CyS*jkx%I{t0^!ggu8o5#DJfG7hRn}3|xf_n3-?yImA{ZK(tu&1M12;q%"
    "qGF8MWL@nPa*w_DN+B)dE_}oAzW}hkzF~SxefsUr7^f<xk=?5FFAp6Swjvz_QzF(y!|v|Q-iDeA;*NmE9#Wc?OQuEHl1wQoWTeL^"
    "`H-KIvg3Pno;~~4vae2kml&%BX+pGxI|gl5w(d8a1fe<<nrVy^r=kkyn7~k3Jx&vOfdY?bSRz2bosHuODQ5wEtwuhRN1a&xjb-&W"
    "CLdSCVU4>Jo98L*znSNywyycsG1UmiqmL5L0gTyc(=qdoriHEQfzUcJWg1YlM*@2CxJik6N&jf?<YFt`#(a{U=Tp7qGzfcL^O4XS"
    "F_Cu#NUZ%_u%EhTzf$Czo2Hv6gXU9XD^6JA@X3}Cru&c1D&IOFgtn7MIV^O~Yhn4BZh0+gw72e5$=9qGeBSbf{k7q?A!|2k&!&~E"
    "dJTfw^QaJxuzumm`XS%uruBnWax6hI71bxcO~gF&)S39R8s!_BJlZLqt};Rzzh|m-dyD_8-rEIk(8DzT<}}`T8t+178*NuK6F!Id"
    "FW$v|_nS@6ocF)w9lYMRWvdpvx_^RCVksbIRV`1;o)T+IedhQS^K$hxNdL8d5PJA8tIEAtXGFZ<S|~r4OB}IB@nCKI^&HX7KP(Mw"
    "b@J@<IP`0sr|>m?EAi|p??de8Eb@7*r#uZg7|6exdD!e?sIt^{s69S#-~DtvaH(lT=I8xTGjAefpWBil;gZu!-Am}}IlV65t+;b1"
    "-*vouCf{Z9dOcy=9_lEE6z3-H-mjb-Qwx^w1{c+GE@-u`mWv&B%jYm8lFGTM%DJgPe1WVznw1i7tb;kXN8Tz;md`_+IJ15pVj8rf"
    "+GYJCh2YE=O%GDwf*rDeKFI=Yep_r>)XeL`6m?(axiaPEKt11al0;B;L*G0Wpd;t#$lW&^byF=zQjMNWN4IICuVmMQr|MtTY!u9O"
    "Y{NcCyw@Z}(%R%PzKG*1+Y)Wg`9>x`(lF;NLELg|f!@=Sv7~$dy6MD)lMc_DM{nb%YpR(Bv<?_uZ8P(%MvR<LjF(#^Up+Ie2|h=z"
    "RWJwX1oDtA+JSr;>HHj9eM^3ia9ScitzME$r`wHf$a)~xd`M}V^0}m0mZ~?~@NuI2SVND6m@&V{3n9;z!_uKl@!+R?F)h26Sl;{f"
    "ec0Cb%U-UdB7F7dQ!yY-Eq5M?sCTn1i?@L*Q_SY+<n!9$iYv4n8T4d#oXuxsmcgjE-0}fghLGu0ktG##GEi<7v*c#UQ`CoUi9$H<"
    "MayVnL}3r;o#NPXjW-sjEG=T>c;nNL`AtgbR;F~$D3iR?arN(@h$@Z%ZZ;m|JC5y%_4s6;UF-;zUs5;xmGX~z#(TR0ainJG^MSJO"
    "hwk2PM(A0ehwZLqv20gajHS*EeR?os#6hv2mZP``f@o4X`BS6z8@<Q{W|$!AwAa>^XJ8E?+~$*4yYQ<7E-%jBezLyAj;nbqvhk5a"
    "JJ$0^nbhTZ#kgF@4<k@LzGjZ{b3<naSRy9q4NIDhJ5@-N_kylj9WMOiSwB&C$HhaP{0ZN%GZn!1X6s}QiqFuoGi4<i(M?hT+2n2J"
    "I~^U=;xSNdZ{7vz?CAk#F_SL|DghGZu0#8Aqn?3%fyKyg$W*??07kMoJA6~TQ_5D^q-x0p<u@y?^N5uq#qj7g(oQ2skX-n%aHco8"
    "d)6;RfxdI(PrtQXVxs$P;5{KT?5OWwulqRVx}0*}NXo7gL~Wg>Tu!wg>|padjTJ|8y=gIC*E{A}a>c1E;cks~<lxbJ?D~hsPg~p&"
    "<b$C#+~*ZD*t4c_GpK_oA<EgW8U5SPivaZ|@eq2+C?cXcNlwg<rRJ+wJqI&V0eBLdwgXOAqpt$?3jQiyp`Nwpg@QqvbFS6smOhxt"
    "w$whv-$C2ZGeULvIEI7r+fHrm+}1~KOD$vZhbsFR$)5X2^vF*+Lx-^dd|11^X2z3KG!48l75<RA2F+3xd+FRye#FX{nki%Cz(w!C"
    "$!AQn-+9#xhCXJ-eUJIA`gc#OBkK6Mt-%?EsqL~lN8<a8qlv7U*9PdNIcJ$F)BQ(W>c-ex@VdWQp|qDNC)lB4&0QsB-}_KU(KA=U"
    "tZ$(0YK*|Ovz0gF9s7;MFvXJq?L?0X{4o1aVBX~2l%RS<(sTRuO@5p1nX1T36ulD+`zr11Be6~KCak49++?3L<n>FMt5R)uQ!b_&"
    "c?$O`#`wv+PrjH=48P#)N46EDsij9)Q@=R*aB9yIfZasT-YT}9nP=Q&ab!>AJHU2&sJjGcD_;7{YB!<?w()&q{b3}zaZ03>S8l9="
    "K|d6-|Mhj@cFX$L8+7y4i(|?H3-T7_A;274oDVi7*7CEzf+$@YK>t5K`!Wm;=q)dbFV1SPt^Ny&;xV@)Nb>1~Q3)QEokvwj3w5|j"
    "x2jt1g69A7h4~NM>c3GvCj#BVJQ|KE#mwY^<Dgk5`Ii64oB0#ML;eKVF3gE$Ez9m3dI_NP<<hpt>cg70V^??++gxokFnjAp=7#ot"
    "oc|YO(p~4j9Ts)R7{_oBW$-n&T(P$W(OT4m0N&UV$qSdVGNhih8Yfoq3Gi0Q#*L!h88{qC*?Cp>P?dX)qq*e&RYE<=8=QZY4Vd4X"
    "yjpQRN)WPnEPqA*lu)zat5T|O6~(JG?T@pYt<gq$8{Wv0GLUl?mBM_IRIlg{7aMucj!!ZlTA<J~M5BzCZX*RK!vIAw0_`x1=GC(1"
    "wMy`gtxx@zn<Ez!XHDRYP6o~7lr_iElO666%T)E8|DwjX47n6Wo(k`I&3j6r8k{Z1xJM6FiU^~aNL_OXd8~iz;U3XOV}^D(_6OUj"
    "(A^TQ6nKwBO$W`{18P2j+K%m`gPXt%6@J_vK=mitzIsk#BywtcFO+|CkH$aH@`W+wEvJNE@S*unqmKG9PknCwiy(KV7U9)#3y_N>"
    "bzLhK5Z~BxD+*K74!`NYM#eP6mPApy_DcUuc%nAaC>T}klugqkXHBV5%}QB+xl<+z+*=J8A@Tgct!Bj5;(}O?A9KarIrpboFIiwI"
    "1Bw=$Yu<C@WwnoW>}pXfiR5X@w`ef8yo(%Z7k#_C<#xB@Ll(BW<w9;;l>uI4-goCb=M+yeIt%!Lu_U(ndZN;f*Hv=<5GD6#>ni>7"
    "E1ola&^IZ<zWaZ7y)tXj8s|_U7~<Aq9fQ5senZ=3Po;bKcBuYuY2=cZiMW+|r?96#&?od*Y5T3&51e@})_50D{iR2A9rDCY#?CSc"
    "#U}>!S~Q-_zQh=v3CBaVm_UptK;N!uWo(-Lqd99=^N%LGE%0|tC&cik*Ns0!b7pYH<=WOzoN|v}Zn~BtoeVqLh5Fp$vO3*!+U2Xr"
    "P&aaoh_Oybzl%M_OPytXX@-BciiD#*+79R7R|^nYWM)3T9Lq_Z`S`N<WA{~Q{+hhHEQ1NtZfI0Ny4>=~Z)5*r)MIR<Pb@uAAae1#"
    "W_$?U&LE<1|K@r&#GPWq9qzkf4oXo5pkweafz~Q*Rhvms{n^<X1Bn)0Ip)%{D~5>@A<jh7t(TE&EXV52NgPDj2KUW*;+!SxklbYT"
    "_ZOHKx`d|Heb7H?yo)$zhO<*{H^G^#5;;7$>XE1-NW7SrHrQ>-(c#%6$F%-$uClJVLTGJ8pL?(T({9ojnsiw8M2WbqT0x@i!LN`1"
    "R_S5?*l(G=dz-fgdr^m)6HeAs$oZgcmE2*~L||XwBDk&*dqc=T-oltwK~d~~95_{X7Na@ySNfkZ1)@B;=NYt76DH=KL9Nh@s_N(!"
    "VOXenKTzt*cy<b93Ct9Wgc(jSKBUF3obt=z{-?VCsq!(2DQ%7aNLObP7@X8InwzinygTJDND7_0uIGRDfG;(EKdpC0zaL<x4U@w*"
    "=oM+lEN8-Au^XrrlG&hkjWMBcIir)9*-@tT-tIut;cu+MQZQd>?$s0OSq9F((kE!U*&Ple2tq~yIg<ufl{6H{sbMx=_>xgnk%>7q"
    "TRAw+MH7k|m9%7;>LDTja#a4M@iP(rzr+8L8};UZgPqN80&qOO<sXB4_IS?!*F11tX93{%Sna!4v9GXNg*@}Aln3gHPTu@s&Iucu"
    "C;m=&Odi4c!4n_Zp_a8>iX?iL6ktT?iEmjWgsag@N;Iz<^0-G%3>b#X{4H>$-k-mV`I~>i`TPGa=6~-$<~NmXNPEk_rw`6J4^l>)"
    "YYL#GBextV&Ksynd&{&`={XL3%UPrrC4o7)_tfhbjd-Lr!?YOndGLTtQN3$E%qcryrC-}(ohHvnmZ!tk*70x-qk3a`j7es09eHo>"
    "8t=`qu1i$%Qt6@QRf<3knD?PoOh*cB2J)aMrav(f7TN5616-4|tF(^Rq!ItIFO_Vt3R7yCVn-z#l>Il;b~Vg(<=luR$9yO|hN`N0"
    "wwR@<)xP08i@e4gtnn`VsWsP|C~3ze{TFXCQGVj$s?9D~nWyO3@m{w2Zu9#H{OM7BqY63mI}Bspk1#*$YrS9N@FM4O)je8|V@JL6"
    ")^`B+muYm>f}$r<<!APCpq~F&tMcr%>e^9*3)Xsl$JU>sf1=x4y@&q2eCQErgh7F|`hiwjj-Ez8_GFVp>$%0&6C|vuCx|AsXRikc"
    "9QWL_*i>`mZ(;7KZ2xAjGvoczGqj#1&GVG9_l&&;Uz~gHy7f%Q+*9<?4qJsTbI;^j&nV}fM`B-zc#K*TO3XdY-g<^Q|Ht}&oKFt@"
    "6SbJ{zg9mH?OQBWf~=?-pES<bIpcqldmC+Rt*`UHknJNRH&=nIHK`07K8(sojsUKFU;-ub1o##+3S&78cW@OO=@eGjKxshMDr6e-"
    "o~r<uurqX^E0pOBgSnj9&=!-KTj3M8nQ`9HKJ_K}6*!Br$ij~qU@k1DjYS$KV~YlMn6(|BsOgDD{Fuj};`NN-K85pWB3B+cM6bDk"
    "WgmC`HDnE}L5TH9dMow-3dk0XXTZrA{)O{x^zkA7AFKWaZf8{68QXRSp9NqD+c?SU%=?4%+#QlMKfuAG;0@9h-JrBTdguL7lA*i0"
    "x4b_p7BtVKX>H^h8|^U8pKeec+78Q&>cRB&fsst`g}}Gb&TnCd>f23XCObGKa^UyKv%oc0HjrqOnQP6EtR8zTbKdH1)cp6=cYohU"
    "3!uHGYYxnmLn@$s*QzmRlAY^&I>~jvsJ@EoI|&>`@?&3*n(2UZSYmDnzA>D$d&`eu4cCILS=norY_s3(s;&7G02frBf5tjD{a4u7"
    "vgmsRKmM&)_aw7AMoXEEpZaAJ#xJ5*<CigYy)D{9OnZlz4!nFc8Fws(mYMxBf5u(j49wY&`eltPh?z&L7K&C#$cIX!ol2UTN3z-{"
    "3g^q|cGZwF`Ke;w+nOJhF_?3w01gSRvxhT^^}C%ShZ;+3NHyQG#hmvfAk$uR|L7ho!Z~wM&r@19C3;%*e21z}yYEcdn=i16GTWS5"
    "oQTOSA5&HlRjTx?_NV$kamG>@u^RQ5T%F(0#6>%Nj&UXHTDR=AX0Pv&>npPLR`3fifqqt0YXv;C8m%aEb8qD*-*c{Bu*JD{3FRng"
    "?I{OEsX66FE@9KwujgRO$FK@xoCG|vjk804q<J->Xg;i%J|XE*lc_?JEuUlSq1$Ss?Bk|9khy!G57_`|*j8uHxr-9(dC~9u!rv*k"
    "=<}ABXs+w0mr69fIx!r|rq68OjpZ?)&g88m*lQi*zMYaif>RJ~!EJPK<!jD6dX;MjRsip(y6&+&_(pY)tXeC9D622sQvvWmq>g#w"
    "2<qUBV3ZX%PVG$I+II#O50Ad?K<{F#6}!>W0mO)ZwOkWEo%{iSu2z4DIBaNFG!^fjl#}e)mTRqCydjXs9lB-V$D5qyH(U2j$J4u)"
    "0qrOaH&wM)H%vRkBv%9BO>(6=MNBhVe78yN?fZj!3N88<TNPYvwVAn<+efQdb>esiolTQ(Os2YNYD?-Iqko^PC`?>$ttTpW)#_Kb"
    "$}lTGbGH|$)N7+O^{f-WCg&A5O{Y&QewfsBzNYzZ12vFqEa;RY1J8k~5!-#mhi`1p_;QT31eB9wEmIm_Y!Uz1N~fij7_E*<_69zd"
    "plY;PAWAAr?^`KbZ2D`BTt{1h$ts*E2s5K@5Iru*S3{N%%#>Y5*K^`(y*UNvkxE#%Ea!tFI%y;47t);~nlvmbbY6!K(ePXLHFq(2"
    "KIkf!fPh4<lPKMCFRTWz)e4co8?Uzk+v3Cq_w@u_!>wROzQX7qs48(TMYnMQja9(eMAUmy)z~@~xB*HU{zSk(`JL`a*L%WRk|zh|"
    "Zf5(W9Nv+$pRJv;gf;s%v}b?2xKFbxF$9o^GoOKTl}V6|Ws_ey|Mt1kA25ftMUK6NSnCzG7HRJ-mWqbEZTwOU+~ScxoB3-PjbT6H"
    "Dvt%P0Q>fe%fjJmoMr;MA-n#<UCJ-0VGDf+@?;6b3{_&L_(YZVYND$2f2-#e^;0!(pICKdR1JA~#(J!oD&FZ=v7!?CsSpoz%%c%o"
    "&&!bOcjd)*<*G*>(58rr3utHE7gj1eYq(IR8WjXcH`RDF<Xl125fUpEVjinUZCdrFN6#filSZ4!@aPK?PGahNB(mY6wCMMwkY-qt"
    "_JAi<X^FI%bba1QeY9GrTrsQRj%KV<NAG89Kj5!oTq@N&AaJBfGzL9X8uSd$k;~P`PW2mfhi+s#*IR65tto!Yj{LM|ujJ%gJ9&(D"
    "1788lJk`@ief8Jxl(^oh&O^~oUF$1>xIEdzNjGY|s9b)D$GCH_ICs0*bJr!;YN&b6KExF~W9KDXP1v?FyW|*I)-S11H51M&)xXe_"
    "M3tJ(hGoHc$c2u1z3a*kIEH$rV<m^9YU*tJ?m7Q1>9>|ztW|-J`yE@as}oMQ(9WyT<j-1#Se|L_)?rG)Fl+w&Ty?kPi$wJg&MN>i"
    "WpNw>j_VCXyH`r?cuuijs(Y(m>(!|EBxR#(9FWT`7D?pknP7=hsKL9it$*v@zQ9HRQ&(&EAt%x)w~7>*NYMn{Guy3km#sJl`9HS`"
    "fLup4&5~M{Go?T3_h!C+(#H^$$GRvi7sO-AI_%T%Ndvl{>w1>Bl_eiER}Ij<=WPJ`Kskl5R0Co*Y1WUn1Dq*3?njlhOCifS{V7Q&"
    "Fy%YeXe}v)^I6?!KFuLHW2Q64kv^$s&~&I!#3y2UVt6N#YrRmbichlbPq3cOwEiGV?wmajXd<2~m{IG`7-rI3laX*cHA~ct|1o#&"
    "B?gQB_l&!M`)=VCbg1@(U5yx_XZjn-cDOo@sj|0S>=avr>+1YSS93a1dpP8DqB2LKs1j4-)Ja={+`0LZ)3evC74zxY<@Btcp5S|?"
    "h~_DCv?sVjrB$HD`&^DU?ew_XA2TwH8C0+IuBB8NSYDb5XW+A@#V4bO{b?2nHL^+YcZqhleHTM#srvj>j(fjOF$2Ld-t1+1W2BsC"
    "=C?636vw7FalG03{IWm9BE`n4^`i0GYEvfuP1XLS9RRtc^2sr`vtELCo&Qplh!%ZhjH>4Wp~$0QyJtNEddSuavF)@Lj%^by6MWe*"
    "zc|qVNi-n0l^e8Wp#!LuC*NC;kR0n5j;c$ha0B!^*ITat&S;fHxJ7h*v*!%fH8*RaOnN9~yCvV1v7*VQTG!e+7~4~^)zqvJq+d`y"
    "qcwT8jW@~7Z&X`<+OrVqJKX0ozuEQlMr`#i#-qJtB+w(<$A-1h<C%tUzPG4;%oL-}9D2n-UVVaB{WEd3bi>b^U8sBS2L`FJzTx1U"
    "r(DJJdbPD~)mO<^sd&n6EQbGg@%OZROJjY4s9YPe*2lcsl-;boS$4>|uBSwb-ZHJ@p6~OUvW+*Uodc8)mwhm^=G5rIUn1)7dk**P"
    "1Lir!ziq0XLnF$j@0hNzkcMcp=1E^QY+{ciL*&yu<vkvu`W3aTIc%dwuM;?Piut*lyB+C(?^^I|f^<*oAF%)9#4|k9hbSnSN`J!#"
    "#5(i0`GB3O5j09tdfqS0gAQjk?&rD<y7_@bpbd3@$n%D?_FvY7pjafdF&=j{Bu1TxR=+8+Zy4>@;n)u=eMub%MRg$5us`Oh@<Wzf"
    "Idj>kFzr)m`}FqySireuhvxbZPxl8di!kkve`|kgyp!bpp&D_Sy=vml_$OQlPx0@V@elJhygfe|Ud6u@Ywp7@#J@Vf6aE3ShVy&G"
    "D8fA}`5O%%zXZ3wtOm({Q~b+cj(_H5{5xX3tG^KcvY+Wg!#|AWY4`_xw)q<Rx5<A^`sdgA{VMuLb@+&TDLz5}OF7~QzUlu9d%7QT"
    "k@r&!smlAM<mVn9LuThFp|}kzzO7O1q|LzUDj7tj@kG%RJ)Ueka^gwVC#cPoWWQK+0M@nfi#mR;zC!WklO?&RSyMzh0J!C&iNhzr"
    ">^9m-%cT-$%5QO`aHje8kU5GGlh64@Vj17sGga}{<RIWq`ZSI<l2~s8pLY#f;(Eybh@nYj^|oqNVK<JBc~;?!?CY4PFL7i-3SW_r"
    "59<f8<&?AVp+&GcrK5kIY_rXKoIG&2?jUd_E>2k~W7i+DkD*mHTjivWgi|QlSDCB66nU_|aqs#@^hDL@_rsn$DIaEJD;c%s(91T-"
    "_KxVUlw1!;I3?NBz^*>`&QNR?S=Qwkt8o&o<D6&6c?=m8lYZ;0pHy(vntxuIYMJ6}Fw$(J>_?;0F=dy@Mo^6u%Bs|2J>Z>au`;2n"
    "!vN=O%b_&q@X18mGgf5*Sk)f|Rvn)vDY0@)!H8VMKNaT;Le7NTzSFV>34AK&6S8H}ZZ2B-oz8%;XI*aILi6*;yauQGXD2xKRR{y&"
    "JVj7S517v0npjO;3XGA#b!9yERGg_--_!Lw^86jHI^1DNfCUUQ<`RX=qem51ST&Y-UI!m;bjrIt`Tov2Wwf1Rzbn1-r0JB`x@EGC"
    "R?F3w>6l5!&|~bPj}Lyyk2aU{Sgvd}vwdV6F?<j95z5X<(g`vMQIFWkHj*Zz-1&}A_1WEZ#f+ZI9_KBh8k&+84~K7*n%}5A-iWfi"
    "*~S|a<~LH!)@Pq$mGCyS{^zK=u4Uw73x}mYmx|cil&|Q(%FjnEYYZ;=6jdF`MfKj=&#B(8=E|+wn6gxBo_igbA0;mSM!kL(dfms%"
    ">d^Ijz~T3ZM6wf`u%B%$q+dJces>UI-D9lM^HyTHttg#Z7JuOJYP<y2zlwQim{W<e-?~Vx0?sDUoQmSyzRpPGgmQHA4Fu<1O3BX`"
    "i<otivhNDusn9B0>iz(ihyIfn`q{IOn+dwpfB$HoI$LdYZtbbQ7e$8`a(HO*QMP_y4|5e5ZAO)qMDcY}rtQf}VrCEIu<A;JVBKQz"
    "LOkX6qZ%8%7KUfLKG$2X8UFGq>)1nOjg}qu?zuld=S+c)GFC7~*O&{ci(WO;tHp2+O$)R0%C+2fxyPpT>}IKIyC~z{G37>M|2AM@"
    "(qqoNV_S3X#p!*`(761bGWk*MlHngVXYxDV$mF*@$<(K7uF{@uux5ALrYbU24`RyR7pKY(D4nLIUich|&DqrH#znuAT47jkGo7!Q"
    "`83h_M3k;pBHw|}sQfm@l^z{)T1GvLup<u<Mfot{#u1ATT#JxK7Px&;BsJ9&63l**$2#%e*Vx3df<5C~3$7A=-Q!xX<iKq1a$V0e"
    "ez()G?LA}B7UQTYTdUv^mTrrkGwz}Jfw*GVnD_a#o=0$;MsPfgz#cI^-UD*xrcI<Q=KHa5#yN+g8bvSB!Sv>l=<R|2*Y9kYt)|LC"
    "N->wcrK48{EIUwD$DH}5#`Cm0MOlN1+op<bo#)<aq&v{vc*O^t<vS2zWV8SG^`x4e?CEJXiX+APJsZ_}Y2KOw*3oT}pVeAeg>@i;"
    "Dy{<GZfg&Q$URc+G4=y{_}arQJ?Ncm(EP=_)-OD~i>hj5xc)1QKh`$fW9MJ!AJL;Wqi)p-@HTWDQPiJTfAgf)=eD+w$LYCm{+jD^"
    "*V>=pyVib!?<d)Y-|p%3)-P`jzwI{bYT@ugVX{Yh7po=R*)7rY`n^!^UFYa-SZ-mZL(55;ieZl;=$ZG@WFGdYQ)oOcUFRUq*d}Fz"
    "bD-t5=P+|3=ryZ8#(zjRMOAGrzRSh_9D8mYk1)q69lNxnC$K{`qnat)^Bipyc3(9xIdf0s=7YtXBJSNv7cnI4P@&fFt#w<r#nJ;("
    "I<Gj%azK?A>zqPt11c$;rL|c-MN4RuXy>&ddw0w2vV~C}5bhGMv2q|=hT-lGe0Rh8H7lVPusdz$PVl^1&b}P#JWnejOj`-#xy2&0"
    "CgN^A``2X0&@r>inF|A=ROhnk((LO?JQfIkZMPItPxx1<cj*@W$Pojx+}4VJSZ$Bw%vMuJ6iM{BN@~D9#p)k=TceMxqz0?>jhvS)"
    "-y%INO=RiW8i{^muO%mTl*a7564l<83wpi#Gbb+nnG<hyO5kgctsnSyiiygxab`WIwpGc^&y=UEGp1*qVO;ZTe4Vd8MoQPa3pqN6"
    "Cg7-NtzOG9&t6OzVOzPdRI5^R1qsf+h&nXB12#$7WcYp~YeX4USeVbFw!r&%+@R|BvB#E|UgEBrR>c^kfHHae>XtLT&X=o{_WZKd"
    "<Baq8H7-cD`ox^W6y*G)N!(nwvc_ECjalo?+fh|DGbh<Or@?Xb?@&JEsou{6&l^WIIAky;zI5SZTh)Qey>?Dh9L%eXtod#1ZC$5a"
    "&_M@V4ajWXsJATFu)*qo7KFXMR&&8KJVgwYn$?Bg?lt<RMop^7nO|Dgov98y^RubtTVicnrIaSlRY`09)KiV5t%Q`O)k<|8M`aL-"
    "WL&Z{Mb5`Xxe8US^$}V=^~QCMb9I)+3gwsXHDXZ)xyp##PZrR{G}_nNC+s23HPQ*+dzNENm|m>{NX_|l!0H@M8p(FP{!BPU)sWgK"
    "rVKdfe|JAhxjl|@3y-7ZD6;1HPML1d{ie$Qd#LJFs&iO$doEl4EA$4>GZwd66VkRC!@QpllCrKcz?`vv%~&62DYNd~gb87mpUJKe"
    "!oCl#C)X(F8bhjT<Z@plvO6A4-iJNkqv@RP(az&6#c~bcRl2NI4YzXz6<~VGTtl2AqBtg$^8MMfPFqIb?q#6T^>$RN_gTA#t?n%r"
    "7{>OST5*eNAM%)h`5_xZ5dNyhJJkZN5nS$QtGH%pn5kIh>GtI=32h|gyfS5Co+NX&40f#qViJ<4Q^Zw5Y0A|Ak(;Wa7u85(evAXV"
    "h&t1JvuO5DMTwgDm=dcDi*Y8ym!C2!9a9yDvj#&LQ8~7rlVqZ<oIwOFWt2xGai+63@`x-IO<PVTs%T307}0&HQoF}$tRl#clSTpa"
    "i(q}H9qwHADy*{7#x=%$t1(`)S$9k&O+jg%LtG_75;Z@vQ?go!RE_S}e%^@@F(<@z7IC<1ce03)kCb5Tb<bd4f|9*bIdK;?0<c&4"
    "WL*hc8)&3)=vg)sMB76tGgDDuTX+9hY4ea|l{VS$ZbYm{u~#e8o|x+QTh_JeWHG3REIG)Rb5FE@?Bc;@K{@k?1LBjj*oKW`Ljv;W"
    "OhXRzr$gU5IK5O?k9}S(o}X$#F>rb)%?-e&ENmzv(D^deit18?(FDxj!MA^#%f2=5MG@9F&6o3>;RD_Qf7#!KQ4Oe+-U4$tnC@vG"
    "_d3VulY8`To8+m*HxZ;~_slD9`gbBfg>AQuo(q}tIZDU4HjXPf6o_73`KY;X@ikQJ7+eKq5cgCW!|QFOZS#HPr}{1zw+ZF-E~k1h"
    "`BYEhIPn^C=r8@q;fV35yPdU{!jGK(O`E)MmTA&nR=sM|UXo67itZyP74+4uvBoOZJawx7rVNO?AKrgK?Njam<%Zv6TyFqcg=4CM"
    "gY|j(%^4RhYwf-DoYG_)CkWeAXJ?;l@K)V3)*l^ESsP6;pT3ThxSJ`)+&DGfWH<Z`*AdAa`<E2Z)vd*5qF4Uf$B#atOV=vfGWzU2"
    "ZXNJ%u_J{Mw~mZO+Rfl$a^CguBzE055<MET-pv|eF>=2j!KuaeKv`ZXs{CkiISNl;KgGMRU)pNslJelkUVP1RBUEk`au-c&38h9%"
    "q6cc8vkrtBGj92dwfZR2X4dRS*K2@MO`makGTN_pJ!m)ZdwS;WCo2L*0o8RmR}Vt}6{ZP1CV#ZbOs)0=tefpwef!gqqm#UeOxqE("
    "PxaO;!EUY6PC-o$ka!{e$a7mzqmHG@TRf0Ia$Y2)s%H_ATaXvHnK8hRocMz)N3&dApIQ@Cp0nY%>R#koQ|TX%<}fW<*`k`e$Co|c"
    "UD0^o_dkxCIHg_BXV$gqkFamRgy^~6)m(#VgG0Ob3U?DGT<oda*Bu{wnlf|A)lbM&KU~IG=WB%sSthw4?LFcr7xw>ax)5zeo^)E?"
    ">$9dY8Ih)(QKjvr40BK5)%7`l6Wo1M&n>i`aINR%p3>)RQ$Ef;b80(Qj{cnDP#=5RGWU$G^~`eaS+ZB>JXL@IQ_mn<&uEsOvGp9;"
    "rj(w0+T3~uzx0&-o1-$Nn|p%b+T!Tz{Li|}=zP;H@63N***{wTsIwM^V#Oa$JKs}>%=;U3pvEr~9f;hT^TRkf99hu6Jr5gG<1GTP"
    "s=daz)hp#-y%OyDHcr`09k#^qaTLO~Q8?qwnJS>K3v1b|W7rc-s9(`ze8dCs9I!sjm_v-C&B6&?a5kNjiL+IEuC!C%oVXu>x}eM%"
    "UCz845QFLs1?c4Ye!;r(S6b%Hwzg^Gwr8t1U|!{kfiZ0@;)&AL7NPVO%U56ywS~{U#d2G!J`R^!i*1QbKZ4gSKU;^f*at*!VfO2<"
    "z_98W0h!a^<{#?5KP;beM!sxXMn34h@3~hYk(H|^4HC$NfMr}c#6<RwU1K9^M$4sMTK2399$BxQK@9+ElpM-ynQu(21Hp1<D)_8o"
    "FZ`>;ca&Ibm4_+URa*RGDbEqV=e)m7Y@^E1Ah^_e81}2P-wykW-rSqjGwf2ogYC0|vW-!$bU~4C%|8h>%!W=#8(pn);3ycxuHQEr"
    "lS+Q^2&(@cadN<}zu_N-xp@Ru;sE-TL5f6;FmS6~6W-R{Xg59MyvDY1tCZI`6}aSk6=|APufO6p|Fz?%eE)Lq>*p|wbgj8k^xbaW"
    ")Sq$U?fNr%`99_p!6+8A6j-v(7pk<Yd4?r8Ju;_H_)nvyIy79NhNPmt!&IRrbLF&9%RR2~-l1kj4b=y*?TKuDBqb=_@|PSI>#x1w"
    "|3_K!Fp5>PH}+0`xu^%lI<hqqN^{J@^LQv<Ge5C~Ew}13E#gA;LH(-pXTPd?jX~X~5(*e-G|Z29H_RO9GgS_-T-DUr?O9C*JJ+U$"
    "U-vZ`j44e=NzilcQJz9i%dg`KI%lqs#|&L@)Q45i>U3D8mtT)H9kSV~f8MUB%IuLwZ3XBd>1#ki2Xw6IT7BL3`gU7>sip4g-aRT+"
    "DkJL-*C*o2MCz+6Gt~;dW;fl&l<_`Mi~rtqo08<?+#Xsy1K{>zGvz7(6<Q{Z0qQ{-eDn&}a|H+Mdj$u5WtYM4sbl({W&gjC3lYDl"
    "%>@*_LJ?^Xs|9$<s@U}la=U<(R!E22{X-i+w`t#?OgJ02rqN?M6Vg3nVGoTt8;`A}W;sw9MNS#0Pf0bGXsaqr)k<>B=5%Lk!_n=&"
    "evfUv_*F4i0V0bpdCnm&LEGH+ieq45k*YtY#B6$~J*S*ZL5-RTHAYmojCGnVUHnDPf>doLs%iN#t^n%{i?;hs4=1T6XW4qDJRBQV"
    "FgUbLqUXBvLyxaZUxmK@>Vz{O?{|BDSzGD{j@fUewyyPoG56@ud`mT1Ra2KDup*0+y)GPU5p~V3iHQU0x8jyIQg+JVqNJRf5-){d"
    "qC&3#IO_Gj5CuKrQojuse=p3(?xfg>|3g1DGw&<=661!o`vmQ!RA+5V>b|bkzs<8iIp)t+wEK9AU;p$We+%L2hCZc{tNd^@2S;*X"
    "6bD9gpualC-*7Ys#v6@Tjy!o%+~=Rai$9zFfsD9`-3VWq4@i7TJ|MAwX{-iU{o?VS^Utq7_Dv#<ExGbhtOWjUznz(UjQn`WQh$n6"
    "5nm9gB5EGi?0YS9Ea~>hzgBx4-iTCn`jDx5H1XGjU<v~_;|}!d5G`|qaaM5s-cuA$AIUn}hglvMvz+f}kX+m7M6&HG$$2ZPm%-7q"
    "2-2?Gwj#Xi=Wo_sm%BKB88Mt>Nl_yir~LW=%Tf-F$Pyq{!T!=LY22S9a^Repb0kiO^u>A4oQd)g%CqxF{COb1iHquR^rvePJEr>v"
    "C9#XCmH_5}M^8QS*Gu$ojOWlbUw5&mm;jEA)Drd$q$%HGi_BzOc~+Ng(XY9d9gjTsFdK=WYmGC8io#(=lIpl%rbUxX8_iTr!8#d3"
    "d+z7wYG*%r(u^H@EPnDfG1cO+huzNg!YNe-Y58lFWd~e7{mZzGY!B?~+@uua{p_FoP$RAP^{3z0@_=Qp#O|*}+^Jckk{)K!H1tyK"
    "da0DHWoY)%>zJTI@kzDUhyo~&z1*o+$-An2RE{GGYSfJF`H_n|p2ixn=F$)sPWY)RuOFIj({|tK;VsQRT$-g2@(*)c+a2Ajkg%t;"
    "U!!cuvjn-zuus`M4cEcz@f|oa*}cHFn;0F>a=KkLmEmNg%x4(7*GgIKfDFy~N87G^7Mrs85y}%Z-QTDajM>`DeoV;?F0onZRHq$9"
    "?Rm*$v=0uM_pfF3;Ak0&WvNk9!%u9gN(yJX_*OZQ{bqA4?Pj=(KhcVPWV-cD4*87ZUs@b<i+{nq%W_okZWx39Z-4}Tj>6%n>roNL"
    "X{?alO#Us)s;ZWsRx>2o6xWkyQ|}RSX?7wd&+Uv~Aq&rudCdQyw~##gJXIfSjZIZGdpz_B&Buv7)u?Ae|Gr5Y)1#+Ieeb47qC@WP"
    "Av-q5ql$-&)-9Jc@kfVdF23=+!;@NNwt{)`lm%w7wL5uS<KKvf)3=)UHhXRN_*$4P!>ES<XQU+YYM#6f`upa?jqm&ZQ@!`t9P$Zg"
    "54A_EgB0N)Q$5;PYZyt)!y#FxrdhXkB#P4aT%VTKuE|amXA}1x$3wLl;XZUVH|!Rth_S8hf0|>H*pIc<VQiXz7@t9R-2*R0il#lU"
    "cJsdreu|&nJ8VHQ<|B9QMz%x51HZP37j3pyJx<KAcb(_O-8VI-KDVg)12cRd&`)$~(G>ABjI3%4iic0S^O}^4c6rz4s5oQT@~)-8"
    "r5FpK3$bH4dKbvBP_R(n123YQ2RYfxn?=bF-$A<7$z$#y{eX)VHt`<SAGUgi>qF-18Scjj%B2JkqjJ^nu(f%N1fY|F^y9YW?31eS"
    "R^Gc`WAVcF%+Imcu$}zTsqPtN!g9V-ig1o8Vxl^5JI+~~F-m92<5yzM*M`;@NqTJ2GI4q4BrRDCrrg1}R&)zEwsW9$ntire>r8ur"
    "RAis>a&Vj}okoLxN_Sd8^sZD?ZP8C!L9V=bu$84(h^HEW1efbyYk@xT5+Ub2YwVM%kZq-iY~%1$g|hm4PoD22kF$PA`cY}t7+$N0"
    "-0Fcj21z!<z$UJ0DI7-r)!F7)Yh#0K`ed$Xp<zC$S(kJjU8G93CiR-F^lu?+-7t`r9ofU|y2?3nMaNA(wJC8$$GB)-P4fVRV_ENN"
    "Jae-rIh_B{q8;JJ3~*HU5=zsTPLvL~6wI$!DHL%mW_VTYlOMJ=;?z!Tv%KCY6u*-gO%!VSLEbw<JY`m`g|BjtD4}KPXN$~cyFV<+"
    "4{#A+&hzj!RpU?gpeo-XOLLV)lw$xkH>ylmAKlO@b>uj_<n)+Rsvf<FS5zOQ=~YNut!8a?v-{JTq)Msm3Eb*xpl2!7vWr;0Xo_9N"
    "+CZ&Z0%}lDXO1}s6WMwKTjH?xQ8G=Rf_mE?r;{l<6S3GdJCXEL9T21`rG#+YuO?T+A)Wi=M_pG+cO7n;qD!K7way{04tr5g{Pai!"
    "K&wnX)f2xRony{$)GVPGqktI(vaS+S=l!-gJQQ_{9ILSr=!0HI2&XCW_c-tH7uvsOo(1*noPW6MBv3k3Et@Lfjcic}h4`Qz3lgUl"
    "-+G-OprpVZGL_-+EinVW(Z@PdWqU-`lCYpgRH5|2nvA|@L%w;`qOyEXoZdcRc&{;|H`)Ewqkr`HZ{F~So~$(6jQ6Ei%)YAjg0v6o"
    "+^eWj8HFe4XzhWn$W~|a!LPmP1bjVtTJFt``?!;%ilcs}Q5pE2S$?~!Y$`?9FeuI+weD7n9yqqn-{_t-^J)i9ZFjZCu8~e6S}#t$"
    ">kb5TX03H|#0<+xAulUdaGOAOSU{#G!3o4_$|+2Fr&E`jQ;)^0CtU$!F7{J?bjmn2$(TJBkZ?AQoZ7i`TUgbfHR&=Znho76o@^m_"
    "H`Kg+^UMs%*6nns9;;SQJdKniu+k(8Al<AQEK~IXGe$PvR0>jiOn%-+q52o8#k15m^=q={*DY0oEWq=f>bb+09^-===BC{G?c;{-"
    ")jsyE)uDUchH{^OC{BK4T&>Bvdh(svru)LrRK8i&n9tR|X_idap%~vI8#UmRZQrO`gIul0S|2UaqvwdS{Yf0!n1eF8Wn1g2b^Qu^"
    "pC2jMCO_bwG<!PhrbPWdX;3)Rv^`Y@Gi#<6lGJ2vg+5V*D`OvFBW?~h)ii3a-t=t>U+=%v{U>zL7Prg5q_8S>r`MPRr;PzK^EE!4"
    "J%Z}^s@64BJ?S$a3%B@KJk_Z>vwT_4Uk2=%zg#M`JT$pYvpan&Ex#W8FH}!lLh`y@zTQSg`yy+m@U|oE{B{4MulL^)d}2kD&ReVn"
    "eZBbk>!sG<8(;q-ucu3|EA+jiT|TzSBS~&E7DjRXy%)UHD1Rr<mgrXXXz<mfb{|n+yf49bJ(nj*EN8#e&}%RrE$$VDO*0HWrATTX"
    "`suZw+17q_R+79i<m1@YIV)J}Po55Qekfg~0Irc$wPmhll~`;5r@3r4EdBtSpY_1aBcjz%e3rAOh~QQ(H`ebDpU$BHCmqej`1EPc"
    "(RQd!GdGQtrRadAvuLcE{Y`Au`idGR$_aYV>%^iobdcWCh87zGTqxymocTbrU##6}Y}VJYbt<fm$6ofdPC8G$=+sDk(d)eTvi3?`"
    "DQwC>H09vzI@#DGIxek8wDaM-UuC=Kbs7hVUiOp$$vkGli&Kq1TXl(1)Mr?m^H5xKqH1Z0D`bw&F=vOjj}xWWmsjYUP}u9rkD7;d"
    "<X-hB*-6%EGHsBxlA@DC-lw`{Asfsdv3O{0Ln?9y<5za1rK#{oj(nm{biW^Bin2Z0S0tTKcuszpYRFsFuc@%^!$~_vj%HZGitMmn"
    "aNzu^RqAZtkXvqJS@H#77Cp|~TE=OE=j4HUwEB+pE`3p-99o~s+tqg<=$2Tmi{<E=EXsS_V=*WmXC5Dq-3^JkRy!6o3U2;Bw+&%P"
    "-=<mGa?K>tb@;1SSXi?iWz#rq_Vx24n!noa@J+Ln<-xy&Nx#|P5C@rEw=FK&U^&-at!QdH4Q0!uWy@Z*s`-;eai7j*oU~X45WOrq"
    ">t?ls+0WmV>l&an$HcW~t5_7na;NN%JyltI=2k(ZuQ<<j>RByZQmj3j6#3+vwdbbSo*~`#+)lP=SC+cdZpw#QMs;cCC)k6*9KB*9"
    "?D~c6mo?%o#~G~1Qs2*rkpqn5*VtBQ0#z+e9Eakx$}Qh>iLDl%Jk?^{1gX_q1ZvePdEGS%<Mfk9Wh9Fs+SF?PoZRJbWy7fdUG)c;"
    "`PHwPUso+clW<tS#<sw6jH<op{~B16zkB>vZhJ=KF)h0sSEL516Rwo*4V#Cy&{6dUm?z&`Y+pp(5se=+T<rFlOb+jlmOYxWbc;PF"
    "Daqo%T@Kr6wa>Bz6*xW<!fHFURlc8Wr*of#@inav>vK+-GA1iA@qT*B=h$q-WXThrtA4OY;JFqjW|BB*n8JuG>fZ}g*G~b4MUVA#"
    "%r@De6-ksr^*M4J%;opamfdUp7<}pA`q{$MSMfHsEfXQ>ve4e)r@XffW5c|MCGJ3(I>yc`oH6HFI9arJF>Bt=TA(`L3_LYfyN_#c"
    "^yUM`UJkDgOa^f4pNTm{lA_E~hk~<P3{}-S#C83F7#k=3mGuSOb$tO7{a4l(AWF1U7f8_omt|s77ye;BmUA@=m|?5Df_2EYn@THO"
    "g#|qeYt5CnYhYaHZ#;RR&h;;BeKys<*b>*j;0*uCFZC}(Yww3A|C{wM#y-6fzx1W`FK+hF)#$=6uYWQ2Z>fF}YxN*3(XH5jkK@3w"
    "_%8lUnK02i)4NPn#8FRSP~Ah?7P01Fg|pfuBAqsFown``Lnlj?WU(wklTuL&*z`*$=<)^V2S9g4wfnRnFL@1JeLZvxI}{smz%8~K"
    "tw7h%^^0To^Vs1t*U-%iW2ZbZX&O6B<r=zu75dn*5`?^g?p|DXOp@BiUR0}ocY^L;fG*A$8TAeH@b%CGdN<4D$Jo8Ofxdq|bYS2F"
    "T#$0;zm2_t9$#6RV2m(wtc-Lw(9;X}jtO<Q86%HgukHjre?4?3Kz!flT}|NzdU*wUDq(jM^swJRKVGDfexE3Tjn~jmgy1V^<a|~s"
    "ht3uB7wNkJwy^58(LW*IK!1_G8#iNQE?tYZLVt<A16)_cSoi(7fv#Vr1lwe*^4kq`^CA^naK?xm==N3U!i=#?c>~?O2Hot=O*}!@"
    "r=6g`MBnAUOFQ8VMb=zF53fOAcQu$B=&#WCL&ASEjkNX}x_X5Ylw#FB<BW1Q&|jbgsd=$>=$pTR{t6{1lzLB(mC0RScY^)`C4fKW"
    "i4yEL&|jbg9<xknA(}!4IK6lS{Y6f19ec}A_yFC$vhK*~%{bF4oIgN!uj2cVnF?kw*e;>_mvF|eV~@uT^za(=4fEG@=tG0MLYH56"
    "R@3UqQlSIDhf(ie4;KlSZf;WqS3SsiGQTojau%7!%g;$t*s|;A7WmQ>UXecS3p5EXT#US$BneTr{c4ZwD>O;Ov`TQLX102O{t8Xn"
    "4!=sDX}f{`0!<Q#y35K0aRc4FGWO^X+|hB5$s6b|&?KEaI!jJe18Dv=^cQGS+R%q`KG%Sf*U<f|I5W#B*=+t2`U^A(6CbR1@NRFQ"
    "zrdYru%UjDK7oh3h8|y8nWUYbd426~puZq}BKcTXMuZ#a`4xQMlUbzCvTyDZdU@$Iop2_`8|cStXLXe%;0RnociU@YKm06xntTIY"
    "yhbC@5;$or$_;e+(%7{K^Vp9Y{hxc0z87?3=<A+u^ndOJ`i_Cq=;At2f*bvxdx^fIdwrawes`n)bM{r}v-GLe4RrS!bmR9pxN*$g"
    "bP3(R0$pnijh`sNjsDMt*T%lyP4Pzm=U$=jn@g*V<!|(V@`bbNNj@Ao4=~5%4fGezs@~<Yo<Ir04fGezYT0Exj4%@=xY7Sf{gUMD"
    "v}+l!iPO8$|H&85s#Pdssd_$%)4S3C$yek<8$!VPcbyX08~vYjui(t)*IiZR2D*PmF5eK7{h$QfaRdE@vx;c!^+;P%Lb=iZ$rsM*"
    "zQw&9qbE>;8~vYrffw_@@akid5`(|d|H<?Uo#AR=6HlOSpqE#n&vd5Uf)CJ-SL7x<O$$$OqyJMctvk!V1A4mC|D{*PE(EHfCM(9B"
    "{x83FdrSpRkP_VK|6bTt95>vov&<K6puc2+p|YqG&TRWNbp4Xv^{{!LrQv*||1&S(3`Sp|ZEfQ8ZuEcVC9B;=lx*OPyV3udS8#>`"
    "8N$Q^>v9AA6`awl<s3M@;|BWiDxFE&WY4_O|Jm)8+vBAF3rSo<cdyVHjF($(zEKt81pVu9CQY2)u#rS-AK<>AV<bUuzEPvvAK;d+"
    "hYP#tH@oOA%M8~X#amOjZp7RAON<I5{pC5A$))yFlr&X`ZZMJ$AzMGH=}o`TKTdI!IAsCAd?LR7_K$6~5;dm0T)(Y-%Xalv*1q|&"
    "Z;gC2`JpeZo>G|P$|R1MGnw`X|5g07FY01nWQju8UR&?Az0vEqT=Ouhq41ujx~FkJbkAFAYCa+Qo*|#l5tXU2$})25r_+G5i-dPY"
    "KEBzhPl*?Aws~$(DTI8SCsq@TK9}3E<h!vP?rJPJ!gV}@GW`GTJ!_BLHj@9vpJxs6C6f0oo1MKilFbIO7Yp2C(a?jkJDHj8>*=xM"
    "1Ma_H6-iMPMRiNl6K8#B8RHg3s$MKs6-kkt(8K2FNoU3edg^A5p0=5%XF3PsYC?N$(!RwPa=GmMN^Uw`Z9Kx@rJ;Lih;<l*jLtw2"
    "P0-&!aRy$8GkCanw;${g0}a}p;%L`}`1m8>QoQ2<22QrPJ(BrQ&Yx~(*KgVNf-N&W9hqJ{B~70@uahFjb=bjSR<6p|oC<cJR_A1?"
    "+OtqSELALr%A-@AV!Nah7=5kaC!f6x`nu56KO68zxpr+%zv@CrHGHuhTQsfm_`q~d@QEtHr{Y{*kMI=(z5#pI`ey74k^a3RdGCx}"
    "l4TCx7>={RburvmD!TXFf&X;B=+TI%;7`LJ&@HOqaluCt`!zbKcolYhbEnz%JD$tBb-fL@k7Bb(n<qWV;7R)RH-p7g#e7@p>qdGS"
    "dVPfmokb_l`u1=dhNwp{6n^>Fg@`1vS0~^w8N<=ovoD8z;UXJ#0tOKy7z*d#dKgP%9+i!GpeeeY1Mv53oYR*|Bb?~@D7G1%kE0s*"
    "+(j%Dk5uyU%uv4Hm1i8uoV1b6OjJ{iA*lIrt9FH6hHo7+UmFx-jG1qhwcp9h?$D$-m8=ck!>#PE@w{t{$m(RQ%I(yEr)d{Zvu-5>"
    "){@q^?~>h{$*qs~{;HF1<ig9ZocDx=`jV06wSL@Vh}h~>fY0E!>ISH5_{A?i`ZptfJ*SF}IMpY7emmu~WHG0;n)iQo??FyrIvK6-"
    "a~`(xT3@O8T04cIAhEX{;-PBf!A#{w%skG)FAn_0n!w`HeN0#ti+vnVJ@8rY)}=Utt!$?nSS!MFPxGyFoxh`e*gG@zcU(BRyo|pq"
    "{o3Eb$5adaLm@^r3I3sNVt-dJ@Kc7dD%Np>>!l(XCa$-MX4O$lVWX``p2GND%|?CpMizXSy9uk6RQiMzlP8lhbW(;+%CJcp7L`FB"
    "x^RA|Ppk2MzS5tgHafF@v<D5vy}cB7D+ED)1|oknY=iDN8FY5l)EP}sqc*IfSh_oBKQ8T0ktT0H#(krva$oT+wE$Gdx{~ilhFHHz"
    "V4v@0j_PubW?78kE}=z~!#kPpQL{a6_q1&;w>_o|JAY4XPay}&R@k1I?;ROk7uiDnt8rx8kT^nK8ky4J1k=%IoKeFb)KO}|Xk1)2"
    "idBmwM$MK^$KR6NVf<|r^Q63<ZV9=#v<M^q6A1DQ1YcL0t{KzHK`6q!z#<wNuXV#0URBsxtJR@bil;^TZ$RyHQS>JQca7TxIejh+"
    "DRa;3GMolFwxK;G@i%_rl#NuNd+}=IY>DDr2^L^j>|~S|zfC4@d#feYIXbBtyzr1Z+m~swk>{}E#t4?^Qb{X9sxhU6Eq%9Z-A=1O"
    "o}fjZ`srJQ2aMY8T^+?9!+23Yk~5YB@;Tt@OOT<&R~U_$BpNZxqY;cjhFw)h(MU(nL?eAm3iDK~7*2CPU4vj*t2lN|we^HADJssy"
    "ROgNEclk+il`?2c9k;`Q3%5kAhttI8vxm0-tTldUH(L*<h~cc8b>uANiM6y_X5GsEeE0-H!H5dhgq*TiP_G_FBXQfZXrDE^y52r*"
    "ho=p+ucGVIlPCuF&jm3K)=-61tmp7l<(`tHtii$Ue!mN5chTr~|FFA5v9QZ0<avnUZQKj04kh4iGJ3mgS)|Vc&7H(uknvO@j^DZu"
    "l;U1tEPiKP>nF$lG~+pc;+B3UI%_6g(|?UUw5MY9j<x8+zE~5zKH1xA7|Z!WXGx1mD<7!RrclG1othtq^d*X6v~wsQB381btx!5o"
    "SsYCeI>l?h$d5eNgaW#R0=G9*jIEV~<*>y&QfIKS=V6nKHaTq34%Rtr;(6GpB6SX1Jg$_%Rz43K*QCo~>!;~wu<_?%6E)4&n`S4m"
    "sYTet#7~t}WU$p@u06;_zGGtfwWd1L=F%3z2w&zO#{J20L_64{sBMoumQFlYO{^6&TKdxv()`>v9!2(B&3sv!&TH6sDaJ9H$G}|d"
    "&rz;I-6b{Mmp8ZvQtxf!H;c0~5;+Y??7)CUbtkc`_{!Pt^hi&R5%nhsGvgP^4OsirC!Vw73eWk?YF5BknKSsrGw{)QeDWNB%`@<^"
    "d3@{)fAV?SB2sM$XU3nY->&pA<x9%@ME%z0G(M?bwtm$){`AY%FF(iMy448n*y@M+wYE}~!x<78i%_n!2%=kN5!#lTlN_=awg}=3"
    "KK`;AQ=Z{(-KysW7U8$xkDqAqty@h#i|;utUd-cb#2I|-SuLW>w1|^msdZr%=j?amnJ)!6iROR;Z$diWW<7n+GqHQxRbvWHjd#$7"
    "wlVDnw-wLvHne@*j&?~I)z4ln_;S`pN_|XZCw}be2mIwWg7A04GZyZ6xD(;740kfzsc@&mT@~)?aMy&pHr$zT*Y$UHw^Vl*=p%tX"
    "66hm=J`(67fj$!GBY{2==p%tX66hm=J`(67fj$!Gqk%pe=%ax?8t9{eJ{stwfj%1Oqk%pe=%ax?8t9{eJ{stwfj%1OV}U*v=wpFC"
    "7U*MvJ{IU>fj$=KV}U*v=wpFC7U*MvJ{IU>fj-t1Cv>}8p#NQ@|L4l&+w+R{lJjXfD#)|@F8!VyBi}EE$gobo!!MSuY4f%+d3)LF"
    "fRUvU@x1wXq%zE67c*;yifZ+kYyC``<MB01y-}^{l<W2P=l9L^3a1=ZMSev~p)Ti0cI#p~r6(TX**()Kr?fs9f9Aer_Fp|aA6NSo"
    "!V@2sz>7VuHdL?kxZ~N1maN_ph%T<3`IRnnGqffzyLD^Ykdirj6MOwp?bW<HC1+E)IVllKYAW5uHQ&cIP2u29<Cb`|_Zpd8Ba^Qx"
    "GO>3&(8mLPJkZAjeLT>|1ARQu#{+#l(8mLPJkZAjeLT>|1ARQu#{+#L&?f?YBG4xSeIn2&0(~OTCjxyU&?f?YBG4xSeIn2&0(~OT"
    "CjxzCpsx({m4Uu8&{qcf%0OQk=qm$#WuUJN^p%0WGSF8B`pQ6G8R#nmeKOD|1AQ{kCj)&l&?f_ZGSDXjeKOD|1AQ{kCj)&l&?f_Z"
    "GSDYIees41K24G|P0}n$^CT^jbeW{(B(`<WRZ>nT=_*OrNxDhWZIU)gx*Ml;A_twwK__z1i5zqy2c5`4Cvwm-Nhkd4gnymzuM_@t"
    "!oN=V*9reR;lE1wuM+;Ng#Rkxze@P868@`%|0?0XO8Bo5{;P!lD&fCM_^%TFtAzh5;lED!uM__3g#S9>zfSnC6aMRj|2pBnPWZ1A"
    "{_BMQI^n-g_^%WG>xBP0;lD}vZxa5Sg#RYtze)IS68@Wn|0dzTN%(IP{+opVCgHzH_-_*an}q)+;lEAzZxjC8g#R|-zfJgW6aL$T"
    "|2E;jP55sU{@aBAHsQZb_-_;b+l2o%;ol_un}mOp@NW|SO~SuP_%{jvCgI;C{F{V-lkjg6{!PNaN%%Jj|0dzTOZe{+{=0<#F5$mR"
    "`0o<_yM+HP;lE4x?-KsIg#Rw#zf1V<68^h{|1RNw*fqtcNs^{Xnk8wTq(zc0leA3IDoN`kT_x!{NjFKlP0}Vwcf*&pnYo>4+|6#2"
    "M&`e8z;C>;ms+-zWZqRLX2?b*X)#}N&G!kja~WX_fBkp9_RGSseucGaIQx_t-!x{&MDp_)YC*r>fAu=d*JzXHZ%k2D#uR1tDVk99"
    "(xa+_&WNmjonK)J9r_dSPMosSE**LL9Y(Ka)`*BU&udz*bw#>$<4cozIH7H-C0#nobh_<7W5j8lZkW@$(XG{uZpA+3;v~&y$7xMT"
    "%n3`Hg`L)SLy0+WS-NMmV=<{CyC1d2rNnN{cwNM6f*Lhm6Vw*tRY2`@rTS>yk5S{5KK&XaHe;JloJ7?vU-wDlHNiCJ6PnS=w&(hU"
    "W>RxTkoJ7d)rn7N7PL~Z0c}kGyib_&=OuiSr?Sb)e}EIwB6&~CnESFExDWENxZV7J{}yOh|Aj%@dP*>kx<o!Sm5-KT2c)?;r+!&m"
    "cQQ(9E5F)mafG!d_UZTR%10`CgggGK<QX_-z05?*qS=>A@eDCy@@*_|U=K0Q@=eSf-vhnrI|a|Z1Hn!hsXMbCl-jc{=A<-!?(6(C"
    "M0+-FZzJ<?7tM~&z)+`PyqpdS{}uea<hk_U$xmx*6zf1;RKuy&FCU$p=*N)7{g_L3k+C~XWzMV2pSG1hoh*Nv+o`f->3$EHb1CwB"
    ")aSnd%zwF?|2{hZ)oK1rk`vg<W(99~xLHX~PD99lqjw5Ima;Ni$CLANPH~}@!_Cu>uc17)Jjar+(1&bUDVAfKkwYHB3O$=rChQ(d"
    "V5;4(^1ssmmi|}xU+#aI|E2zy_+JmtbpF@)-`4*&{<rqOmH+kljmK|1e&g{QkKcIw#^X00zw!8u$KQJVt;gSb{H@2|di<@&-+KJ5"
    "$KQJVt;gSb{H@2|di<@&-+KJ5TeB;4ykfU?aUn!<ZRPW;@v7fwt6`r`@|z^T2~$1!70bC*!**YuXw`64j8+ZTes3Yo`_;p>-_OWB"
    "QT?tM{Sz9+#bJ+=VMh|})-t=*#m=`VWx#KCI$mX*_a!>(OLVk%-<P%uf~~MjS?eg}Z)CUI6;H`>%U|;4_G+@f`d4XRzi=JX6?NP#"
    "m&2Ep`iyt4e_yXQkBzexkxRECA`+L@MY%$MXCUZHqCM}yy{GKFr|i6^?5b;|@UoGD`)xe_#^Y~1{>I~PJpRVxZ#@3S<8M6v#^Y~1"
    "{>I~PJpRVxZ#@3SM-nQDRJ=EDbtaOrkxLSZoR4IfSsSUSBvR3nNJUQ~m1+{HRFg=ho<u5jHd2ZAG-z1IUnXAR{|5GcO>{Il4KjZo"
    ">1yAw#uKga-ZQ;$a<Nqv%cG+;elI`v!SheEb;0$;u^3<BN7@y2OfRmtH6sko3NFm@F`!jZ%;hw!h#=OC7p-X*CA&20l6jrX>JH0l"
    "HJclwxJD$`h~#A=lJ;wkNMzL&XCe~dN>0Y%wVL-jGZv{{QFcXtI1k}#8wsH+xDYFBr7SM?4!_mN*j%6S|D7eCS`xHG##^F#@hI&$"
    "-6r|1pG90_iK@gB)e}opPb^V0u|&<p615Xc)Xt3JYGo8t#=KCk=!?cpGqZa6mQk%JyJmE4O@E@gIF?`0zg!jBc9%xibj>`bxs--{"
    "zjbC-nk^qW%=f|aPiglX&C&7|y1t@cwPxH}>PuU|Dt+iK?RC!dzRB`$48)4jm^HoRHT5>b@tmJF*D>B}kLow+QFUK)kE$g`pYKtX"
    "lO9#|Z}Vl7=vH{Fd|9)?6Xqc_%f~Zk=*^c^%RQ{%UrP^V+LCM!L-`(tdTx(moHhkvYg=ZW>@Hucv}H#9i6ZS!^er>$PZVi?qHmd|"
    "$oDWR=wTGnsPk<yy8<BVh5LG+$`$4A&+};;wN$Q2I?3<i6CW1Jy-DQWOyu59<lau?ZYFX!6S;RYa<3Kcu5RQ7wotFIEi2-(HL+HH"
    "o^2-H%fjVyg>_m(*&6$%R#<<r+;->b<qM_rwZ)HL%*vKur<E1lh+J#8D-+zQ2=R$u_>9_T)#w?s&(!D{x6jJaGhv_c(KBVA(a|$|"
    "5+sRNNpz)!*RTKe&n&!RL|<9jXCwMbX`hYgD=pq)L|>`xvk`q|WuJ}cD=mG+n7#&|b;Gv~r0W{ely=+!b99{3vM7g-a>^mcbfcU)"
    "%BkWUQ$;x<&gt4Hrx@j!A*ZcJIbD=f#yNN*NXQ{^4r+Oy)9>NnP9Q~HiuX<rX_BPXh3N#INb;$#{XR|93*%o&Umur+beW{<g#K!r"
    "?&q*V+9c_2obF9|pH>ll*S3Cb>o3~Y6J7h=)9l}jp5HB9*!DL3g{U4+bgl86sm4bC7y}s1X)`)|>3UtS>vg@Z*Y&zy*Xw#+uj_Ta"
    "uGjUtUf1h-U9anPy{^~wx?b1odR?#Ub-k|F^}1eP=Hf&ML3sy%1V6Oof|p#w9p-4>@QxFXpI(;m3u$JLgrY?$B$c%6q&?}57I3d+"
    ";qFTYPyGpa3!&qOg<Rn2a4nvjSgMkgrsQQ;!UfPdz=tQ2$pUfWI<ZNa64Fhn;R%r(emh+KX3I06%|8L^w0%oJj&OGX7mszcztWzt"
    "R<-~GIq9T?GRP|feD?S*`@X_w7OHRuK>}`Rb0o#LJBxuKep{}zGzptWN(&3&!kbJwdhz@>BNTUKG(2Yx9$;huuLT?pzzk3%V)YoU"
    "d<4Rn<k*^uAa*E4TT8&Hv{d?9v-enc$S35WoPD0766mNgos+;AZxJNtrPIN`#>?K-g{>=D#dQU`z(6y!r9~qx0Hw6j*As{+Z<GYW"
    "Y2bYpLz*eOu$+}80UD^|`DD2U%L1(;swZuqa*GjlR7w%Q1JZ=|+}VG~FRr@*-Dlh$Gm7m1+n7-J#GSAhx1wH3a0kCaV2ebp_cbMk"
    "d#m3BxUkgpZ4>LMf9l^+%(r5s*V4}h2v)cBpeMj93EJ3~>m+C<)W5*R3@Bl%7cJ`1NQXMdf1qWg*MSEK80rWkP$U(~IuG0Oqit<)"
    "OCM@XiCj1hL8?GsJEyN!m#ltC$FH{5OhM^JioT6x%AmD#7K1pA9O&}AAO>!AoXF7rqcTYw8RennDy<weloPgn0zarVs42D$HMV4q"
    "jy|umR;9Jps<T#&NPAZ0P-bY$dHWVY1F1+ynYEyy4#%a&wb<KTCXq{kie3WlP(zq&JyP42NNfv1%jjE!g#^~gLdLdY^=YPdB8_u2"
    "NUN*Ji{;DO4S?Ptk5kx|Yc&Tw*6}6KBWdWq9Q+fgqqaP@AnPASWlQVT+Bq#9N<wRAXce-$9Q@Y#{HX3bOFdX6)Y6`6t8Fy(XV!;d"
    "d282zF4<fDKF_|(BD)&XH1De-s|r@o+Pa+lz&5IpWUZ%%vPcKoEA*z!YL~OF&d$V9Kxr+Q?4t*O2ArbaqRx8%Vl5-2ux3T-tHz!>"
    "Eenwi0V?@WO4`<+mP6ZQt+A&uQ)1*(oL9EKsBsZPQS=tVYGTGuj`B+j$wRmHD9$A=I*52iOru!A)}^zxs6Qv(&eezG1fw%sdrtcr"
    "Yf*=~iD4>huQ+;uPzydn3#}q9pVkqv{?EoS*84fXJh5Yw_ac~sjf-lP+P0x>p2KY8QH%|SQd8ZvGH`Vi{P4tI`DkOt$M`64utZjl"
    "B1j;LTBmS*-Iy7#5tX*B+nkbO8p$T_C%)}m|AGsMbs78*@eZ{8jvI_)P>cJvk?sL^23`lu8i0p!l!7M(KI65Gj;t;rcT<@2Jrw&C"
    "jS}lA93WbI*h#(|9`tnx&?iw_Ab=4OENjg`;t-87JUj||K=WMk+Vzm~_=eaJXvSVvXZu)EXiv4UwgOuibF|OCFM(&n5sJh}6XAel"
    "0j!lMLMeu*aF!lve+#S;fI)a;VWBLUrA?$g%TY`;iuIQGVeCTzKBzBHN`wtw#bE({2(RrktW#p2BZn@2ZfyJ4Sffw}1=IargXj6N"
    "nt~WG-Qo!|9%eSWoj#?jqm9+_Cbm~09GxIil#rv5IzPkO=flJQk!N@s^dt3iE8&mz1Mj?C1KpXJ)8U|AKEy9+A<0VBbNQ<;YFCT6"
    "wL<ba12Dx&3YcGw!u_xCzoq|`VYSM6{$Aa@dNj>(yL)(i^&kKIXK^$6_ph6OQh7seN=WcRmp6h@?ea=)vl)YIdIRmA^P3WyQE@}5"
    "=C%l<wg@LT>W2Bu5;~~m4XScn1VLD!7-!rtXlys)MwRd$<&dr6b(<}b1`JVclDK!J&y@_~3;-SS{ssJfzOQ$8mc3W6BCcNTtIv14"
    "s{Mm`I37N~-nl#=j*=V1_^PX(?v9&gcYnWocy+@>K-a(dy4mk1Z+-ikkm5B6R%i~C5(<0~%-H<b4}@<1^ZUR3@tf~An;$lWch&ap"
    "_U)0#x_aC;o5$l}`|y7Aace%kY2YzwK2(Rz@lb7#k8hgW+gCRPgi<P$b{^n<x4VO4PRxWT4q~ymt7gB=QVTH3>gljMRQ$<w+c7*+"
    "{A8;3AKQm^_lY;V{pZ{Jw@3cCuO8mOZ~ggbzP|?~&>;nU*e}*Xkdg=_6~p=)A<CXu5DS;D35rF4Oh#fkL4g3YThnfiyZ!EN_x>|N"
    "MwfNNPz^kH09!hVk3sL7Jky7#hvW9%Wb@u1s{My;Q{DZcfi|(bGjn45ZbWtQWA)y=tLi)RNci^QXby*`{c-bnw>#c`e7$`<R7fCU"
    "igKtJF-V0n`I;i>CFaCZnMXiA*(#Yr*Mg?dODFR&bjaXNU=yq->Vl!r4x9UGzXv_N{RkLwmE;W(I#S7b0J>`Lw~votYp@n^eLXbo"
    "z79{LCc94$pas>zJXH8{S-{I`;k&<>!-Kio9Cjcr_inNH-6KjIYyfDCdzUZ8EB^awYmQDz6q}<Wi=-qD(B`b33r*0nE<q+gfsw#U"
    "aj((gHK=N(Uvpd61sLXHQC&a7G=Z0=&?@O7CLy|o*7bzygw}U!9-VYS9~RaOeXQ>HST)t%oqw5>OJ5edr{n(VxT%gubH6|O_lu=f"
    "TRt9lhn{4<SeYca5+L~qitLE*@h*iRK2^W;FO`cW#rNA^LH%Q1abv8-vU+O{AGeM9@vb^{yTiRx4Xf7ZsA)#4r8k}Ot+CDh%@1!k"
    "StanG-yN!l$Nlbby#3)V+e|Rt-l~t)-L|cc=Jv<$KHk?BH~2yIC2*JE5gv{kXR^TY<V@C!BPHa$c`%0x12d00uV*igneX=I!BwvU"
    "9V3Ov$hh4;?(eG4XOaHNm3vP8YKgH^`2~>26)ZKq;W;tCG}37WTZLZKB$ba*d{d@25dZB-9yCLcf<wa>3r&3m{fm!g1Ft)NodE-H"
    "vC#RKO|?Hh9n9vj0r!8{?i}BmE_9A)H@C+PaN+H)Wdedo2vAkIj0t9b-9tYKOgGwK$AMVvZwgDm<FRUfaj!}`y!!3if4uwlFRz(Y"
    "HiCr^j`1i^Q{pu{6{+bEv5H&l$Y4ERViiQL?r#z3RH2~kRDIsc&8_`U`il4JT@2NAS3SIcf_OI5>3V<ndH-QkLtFt}E*w6Dz)1v6"
    "3%qVd<(MczGUd?QIGSHU-cZg!Zb=CUd+-&T>S^<Fb5Ayu`_OOz>jk%YC^nmx6z!q<<WN~S90Fa!%k_}71=N_kJAfl0PKRJ!$Y)R_"
    "Cm8@xNsRjyG|Cv@FXsS~P5J%y!IXT{`kPlboJavRQK+?`^g9swx4_^da2xIcASf^pr=!3SA>OZpNQ&(P1i0WO{s$Q5TndhQaT&<R"
    "5739Q(KdiAnFa@2l$U@M?e=iAzzP6FX>kcKS{(rrZfbfXE&`;Rr^6%IJ`WEhCoZas5=TU~2&|;wp!G$>5!yk`K7QEjE9f=bdVnxq"
    "^2=b_nysPJ)|wV<C(d1f5ZOgQ$%kzV-3=>C6r|!fp0yU_(Bcl}XK*OkK(PPJ^|K*K-<3j86dG>HFOpsf-Fx%UVk^^3-_XnILV(YI"
    "MAE>(Gl&_A7ihBBjrok#DsU`Jsf!wih4{hT?SV!~aKMg`%S;uqAi>!mpV0m(hQ_qe@&#1->EV}$-KPhDsyPJaLSDo>Vcr7%Y$F?l"
    "sueU6LgnQmHNT>X5FpJ08%qz+#Vi{S3&Q><RE`1%3MqYlV{%5sLPD7kc~M(e(7E43mepHM88ob7CQPJk3eAoi+Za<4Ftv1c+(-WT"
    "P~DsQsq4()C)4Z>t=LzGM|0bcvVM1FnDysZH&hTH&JHV%Bz!R49aQV)(RxflDHs_sIAO%U@x#~~?9l@x9Hio7pXx_S18e)Iqh(8R"
    "h!i3j_mFJdWvz#s4ZzW+A}6-uCkOfa>htdD_~T*MZSTyR@9*jDt+1WJ+k3|wuoissy}7^NeFSzSR>_=Hqmfd^z^xo0XdfyGhi)K$"
    "1HtUiJ8(I-_i!O9?E>!sRkKGUQ{2oAZc+l$nJUxm{ZHTh@V3~9KSIS}7tL<uik?@`k5=%%SBE1;>FPsuXg^g4L*MLfzehNP{CV5$"
    "-W|5@-<!iN(I6qh52i5~TAKqv*|<Ih+ODWOG9EtWf8HMM5$;bAdYeauVGoMv7MX{R065)oUub^xx%_Aj+wSwgdBX9JHbK<)JIMQH"
    "ziqw=!@e$y7Lne66O9Q|O%)DNDn27}`IqXU-F2N;k)_Q9SY#MS=~B)qO&O?thlAX2c5%dM+gVAW)5fTpfuP>`8H)8ym{2!uLD?L2"
    "!p*^a^K|^MJ8X}i#RIl8*RK*$S2Ah)-PYW-ZtxmSfP`>G!~?V^YS~xv@~XZ4;k&=z{q5c6{^$GKO>_6=r|;f=1O34It;R<<CxzW@"
    "k!iIhw6)#gGhsh|`22|agj75dVtF+CUGrh%W_?D3!@=aBCOebkro9TB3d{(Rf79%@!j9)JuAEf^;FJP^RI!r=6q!N`ievF4YH^7@"
    "1_uJAh6&EomGzr7$xNmG$yVyOu2O+p97rx_2T?Sb*#=DZA)dkm&nT&#gNcmo{r;7mx?;25l7}If?yh?OII*+B&K?Y2$%-^MuHD_;"
    "rZ(@l4><IrbUBE2B>MXbOK_YiAqAhahx)HpW&c|3y(I#c7>5|f&bwx6)J`$Kx*1jI83W|!kAAMv_TaP=nICXty_h#R(VIx-CvYqI"
    "Hg<~@0iwWNowH=`(NlVDgfJ!$56~VB+7xhUd>REfWWG`A5-0ehMmZx%4uS2Xbw?EX&kBN3m2F9b!}Zal0HX}C@LXLvDX{k-%ln^S"
    "xep75KEp^!!n`fcrOJ51e-L<Z&^UGm?xB2my05`8f3|~nIMTru`xp+v$R2eEKe>UPG&xNb#w`2l*g%{MVF0M8RAPz87FPSv3vz|i"
    "wTxy3>xcI?cDe{hd9AaHy;8m!ylz8rNn&;Q-7OYbX|mF)<rvMb@&R_1M#`6p^LpLF_=RwsE+;P*L#}6zL7M=n6?4HEQBjTj=u80>"
    "(3Qf;(nw#r?XNhRZv%Xsj0bNxjDAdwwzVQ?vUUGS&;R}(HF^55"
)


def capture_linked_fixture():
    raw = zlib.decompress(base64.b85decode(CAPTURE_002_SNAPSHOT))
    if graphical.hashlib.sha256(raw).hexdigest() != "3d758126608f2d43bf21a00863be6d6d4f687547d72667ee8f792fe5acc10c18":
        raise ValueError("Changed independently frozen capture002 fixture")
    data = json.loads(raw)
    linked = SimpleNamespace(
        symbols=[decoder.Symbol(*row) for row in data["symbols"]],
        functions={row[0]: decoder.Symbol(*row) for row in data["functions"]},
        sections=data["sections"],
    )
    return (
        linked,
        {row[0]: decoder.Instruction(*row) for row in data["code"]},
        bytes.fromhex(data["payload"]),
        data["files"],
    )


class CaptureFixtureSource(unittest.TestCase):
    """Mutate real source contracts; these controls make no emitted-code claim."""

    def setUp(self):
        self.sources = {
            name: (ROOT / name).read_text()
            for name in (
                "kernel/uefi/graphical-console.cpp",
                "kernel/uefi/graphical-capture-policy.hpp",
                "kernel/graphical-session.hpp",
                "kernel/console-session.hpp",
                "kernel/display-session.hpp",
            )
        }
        self.native = "kernel/uefi/graphical-console.cpp"
        self.policy = "kernel/uefi/graphical-capture-policy.hpp"
        self.capture = "graphical-console-capture"
        self.no_tools = patch.object(
            graphical.subprocess, "check_output", side_effect=AssertionError("No external tools")
        )
        self.no_tools.start()
        self.addCleanup(self.no_tools.stop)
        graphical.capture_source_evidence(self.capture, self.sources)

    def reject(self, path, old, new):
        changed = dict(self.sources)
        self.assertIn(old, changed[path], "Mutation must exercise actual source")
        changed[path] = changed[path].replace(old, new, 1)
        with self.assertRaises(ValueError):
            graphical.capture_source_evidence(self.capture, changed)

    def test_exact_source_only_modes_and_dependency_inventory(self):
        expected = {
            "G": "normal",
            "C": "cross-console",
            "D": "cross-display",
            "c": "stale-console",
            "d": "stale-display",
            "F": "first-pixel-error",
            "I": "interior-pixel-error",
        }
        capture = graphical.capture_source_evidence(self.capture, self.sources)
        production = graphical.capture_source_evidence("graphical-console", self.sources)
        self.assertEqual(capture["selectors"], expected)
        self.assertEqual(capture["schema"], "aurora-graphical-capture-source-v2")
        self.assertEqual(
            capture["release"],
            dict(
                prefix="AURORA_GRAPHICAL_CAPTURE_RELEASED: selector=",
                codes={"G": 1, "C": 2, "D": 3, "c": 4, "d": 5, "F": 6, "I": 7},
                invalid=0,
            ),
        )
        self.assertIsNone(production["release"])
        self.assertEqual(capture["invalid_selectors"], 249)
        self.assertEqual(capture["failure_successful_store_ordinals"], [0, 55])
        self.assertEqual(capture["status"], "source-contract-only")
        self.assertEqual(production["selectors"], {})
        self.assertEqual(production["failure_successful_store_ordinals"], [])
        self.assertEqual(len(capture["remaining_linked_proofs"]), 6)
        self.assertIn(ROOT / self.policy, graphical.source_files())
        for path in self.sources:
            changed = dict(self.sources)
            del changed[path]
            with self.subTest(missing=path), self.assertRaises(ValueError):
                graphical.capture_source_evidence(self.capture, changed)
        with self.assertRaises(ValueError):
            graphical.capture_source_evidence(self.capture, dict(self.sources, extra="unreviewed"))
        for mode in ("console", "framebuffer", "capture", "graphical-console-C"):
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                graphical.capture_source_evidence(mode, self.sources)

    def test_all_249_unmapped_selectors_and_each_valid_mapping_name(self):
        for value in set(range(256)) - set(map(ord, "GCDcdFI")):
            with self.subTest(invalid=value):
                self.reject(
                    self.policy,
                    "return Scenario::invalid;",
                    f"if (byte == 0x{value:02x}) return Scenario::normal; return Scenario::invalid;",
                )
        for selector in "GCDcdFI":
            with self.subTest(selector=selector):
                self.reject(self.policy, "'" + selector + "'", "'Z'")
        for name in (
            "normal",
            "cross-console",
            "cross-display",
            "stale-console",
            "stale-display",
            "first-pixel-error",
            "interior-pixel-error",
            "invalid",
        ):
            with self.subTest(name=name):
                self.reject(self.policy, '"' + name + '"', '"wrong-scenario"')

    def test_fixed_failure_ordinals_and_closed_predicate(self):
        for old, new in (
            ("successful_stores == 0", "successful_stores == 1"),
            ("successful_stores == 55", "successful_stores == 54"),
            ("successful_stores == 55", "successful_stores >= 55"),
            ("Scenario::first_pixel_error &&", "Scenario::normal &&"),
            ("std::uint64_t successful_stores", "std::uint64_t successful_stores, std::uint64_t ordinal"),
            ("return Scenario::invalid;", "return static_cast<Scenario>(byte);"),
        ):
            with self.subTest(change=new):
                self.reject(self.policy, old, new)

    def test_release_uses_only_validated_closed_numeric_code(self):
        self.reject(
            self.native, "Serial::number(static_cast<U64>(selected));", "Serial::text(Capture::name(selected));"
        )
        for value in (0, 8, 255, 256, 18446744073709551615):
            with self.subTest(value=value):
                self.reject(self.native, "Serial::number(static_cast<U64>(selected));", f"Serial::number({value});")
        self.reject(self.native, "static_cast<U64>(selected)", "static_cast<U64>(selected) + 1")
        self.reject(self.policy, "invalid,\n    normal,", "invalid,\n    normal = 8,")
        self.reject(
            self.native, "AURORA_GRAPHICAL_CAPTURE_RELEASED: selector=", "AURORA_GRAPHICAL_CAPTURE_RELEASED: scenario="
        )

    def test_gate_rejects_parser_writer_and_boundary_drift(self):
        for old, new in (
            ("capture_scenario = selected;", "capture_scenario = Capture::Scenario::normal;"),
            ("capture_scenario = selected;", "capture_scenario = selected; capture_scenario = selected;"),
            (
                "Serial::number(static_cast<U64>(selected));",
                "Serial::number(static_cast<U64>(selected)); capture_scenario = selected;",
            ),
            ('require(selected != Capture::Scenario::invalid, "capture selector");', ""),
            ('require((status & 0x1e) == 0, "capture UART status");', ""),
            ("Capture::select(Io::read(0x3f8))", "Capture::select(Io::read(0x3f8) & 0x7f)"),
            ("remaining = 10000000", "remaining = 10000001"),
            ("    capture_gate();", "    capture_gate(); capture_gate();"),
            ("    capture_gate();", "    Service::open(); capture_gate();"),
            ('Serial::text("AURORA_GRAPHICAL_CAPTURE_RELEASED: selector=");', 'Serial::text("RELEASED");'),
        ):
            with self.subTest(change=new):
                self.reject(self.native, old, new)

    def test_local_crossed_records_and_genuine_stale_generation(self):
        for old, new in (
            ("argument.console_grant = display_argument.grant;", "argument.console_grant = console_argument.grant;"),
            ("argument.display_grant = console_argument.grant;", "argument.display_grant = display_argument.grant;"),
            (
                "argument.console_grant = display_argument.grant;",
                "argument.console_generation = display_argument.generation;",
            ),
            ("static_cast<void>(Service::close(console_argument, 0));", ""),
            ("static_cast<void>(Display::close(display_argument, 0));", ""),
            ("console_argument = Service::open();\n    }", "console_argument = console_argument;\n    }"),
            ("display_argument = Display::open();\n    }", "display_argument = display_argument;\n    }"),
            (
                "console_argument = Service::open();\n    }",
                "console_argument = Service::open(); argument.console_generation = console_argument.generation;\n    }",
            ),
            (
                "display_argument = Display::open();\n    }",
                "display_argument = Display::open(); argument.display_generation = display_argument.generation;\n    }",
            ),
            ("display_argument.height};", "display_argument.width};"),
        ):
            with self.subTest(change=new):
                self.reject(self.native, old, new)
        self.reject("kernel/console-session.hpp", "++generation_;", "generation_ = 1;")
        self.reject("kernel/display-session.hpp", "generation_ = next;", "generation_ = 1;")

    def test_both_preflights_record_identity_and_single_consumer_entry(self):
        entry = "kernel/graphical-session.hpp"
        for old, new in (
            ("incoming != &trusted", "false"),
            ("ConsoleSession::preflight(trusted.console_grant, trusted.console_generation);", ""),
            (
                "DisplaySession::preflight(trusted.display_grant, trusted.display_generation, "
                "trusted.width, trusted.height);",
                "",
            ),
            ("const auto result = call(incoming);", "const auto result = call(&trusted);"),
        ):
            with self.subTest(change=old):
                self.reject(entry, old, new)
        self.reject(self.native, "Entry::invoke(&argument, argument,", "Entry::invoke(nullptr, argument,")
        self.reject(
            self.native, "return service_entry(record);", "service_entry(record); return service_entry(record);"
        )
        self.reject(self.native, "++consumer_entries;", "")

    def test_pixel_counter_admission_failure_and_sole_store_order(self):
        for old, new in (
            ('require(pixel_attempts != UINT64_MAX, "pixel attempt counter overflow");', ""),
            ("++pixel_attempts;", ""),
            ("++pixel_attempts;", "++pixel_attempts; ++pixel_attempts;"),
            ("Capture::fail_pixel(capture_scenario, stores)", "Capture::fail_pixel(capture_scenario, pixel_attempts)"),
            (
                "return static_cast<U64>(FramebufferPixelResult::out_of_bounds);",
                "return static_cast<U64>(FramebufferPixelResult::success);",
            ),
            ('require(offset.has_value(), "pixel coordinates");', ""),
            ('require(stores < 1000000, "pixel lifetime budget");', ""),
            ("++stores;", "stores += 2;"),
        ):
            with self.subTest(change=new):
                self.reject(self.native, old, new)
        native = self.sources[self.native]
        end = native.index("#endif", native.index("require(pixel_attempts")) + len("#endif\n")
        begin = native.rfind("#ifdef", 0, end)
        block = native[begin:end]
        store = (
            "        const auto result = FramebufferPixels<FramebufferMmio>::pixel"
            "(*graphics, x, y, red, green, blue);\n"
        )
        for anchor in (store, '        require(offset.has_value(), "pixel coordinates");\n'):
            changed = dict(self.sources)
            changed[self.native] = native.replace(block, "", 1).replace(anchor, anchor + block, 1)
            with self.subTest(moved_after=anchor), self.assertRaises(ValueError):
                graphical.capture_source_evidence(self.capture, changed)
        self.reject(self.native, store, store + store.replace("const auto result = ", ""))

    def test_exact_diagnostic_counter_sources(self):
        for old, new in (
            ('Serial::text(" completed=");', 'Serial::text(" completed_samples=");'),
            ("Serial::number(pixel_attempts);", "Serial::number(stores);"),
            ("Serial::number(completed_samples);", "Serial::number(sample_calls);"),
            ("Serial::number(wakes);", "Serial::number(expected_wake);"),
            ("Serial::number(output_attempts);", "Serial::number(consumer_entries);"),
        ):
            with self.subTest(change=new):
                self.reject(self.native, old, new)

    def test_capture_condition_scope_and_token_identity(self):
        for old, new in (
            ("#ifdef AURORA_UEFI_GRAPHICAL_CAPTURE", "#ifdef AURORA_UEFI_GRAPHICAL_FIXTURE"),
            ("#ifdef AURORA_UEFI_GRAPHICAL_CAPTURE", "#if defined(AURORA_UEFI_GRAPHICAL_CAPTURE)"),
            ("#endif", "#else\nU64 pixel_attempts{};\n#endif"),
            ("#endif", ""),
            ("++pixel_attempts", "+ +pixel_attempts"),
        ):
            with self.subTest(change=new):
                self.reject(self.native, old, new)
        changed = dict(self.sources)
        changed[self.native] += "\n// A comment is not a second capture_scenario writer.\n"
        graphical.capture_source_evidence(self.capture, changed)
        self.reject(self.native, "#endif", "#endif\\\n")
        self.reject(self.native, "#endif", "#endif??/\n")

    def test_capture_linked_gate_cannot_be_cleared_by_source_or_pin(self):
        graphical.require_capture_linked_proof("graphical-console")
        with self.assertRaisesRegex(ValueError, "Capture fixture linked proof pending"):
            graphical.require_capture_linked_proof(self.capture)
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
                with self.assertRaisesRegex(ValueError, "Capture fixture linked proof pending"):
                    graphical.emit(self.capture)
                self.assertFalse(receipt.exists(), "A source check cannot leave a capture admission receipt")
                data = dict(
                    schema="aurora-graphical-console-admission-v2",
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
                            self.assertRaisesRegex(ValueError, "Capture fixture linked proof pending"),
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


class CaptureLinkedControls(unittest.TestCase):
    def setUp(self):
        self.linked, self.code, self.payload, self.files = capture_linked_fixture()
        self.no_tools = patch.object(
            graphical.subprocess, "check_output", side_effect=AssertionError("No external tools")
        )
        self.no_tools.start()
        self.addCleanup(self.no_tools.stop)

    def changed(self, address, operation, operands):
        code = dict(self.code)
        row = code[address]
        code[address] = decoder.Instruction(address, row.size, operation, operands)
        return code

    def moved_rip(self, address, target):
        row = self.code[address]
        match = graphical.re.search(r"(-?0x[0-9a-f]+)\(%rip\)", row.args)
        self.assertIsNotNone(match)
        old = int(match[1], 16)
        new = target - row.next
        code = self.changed(address, row.op, row.args.replace(match[1] + "(%rip)", hex(new) + "(%rip)"))
        payload = bytearray(self.payload)
        raw = payload[row.address : row.next]
        self.assertEqual(raw.count(struct.pack("<i", old)), 1)
        payload[row.address : row.next] = raw.replace(struct.pack("<i", old), struct.pack("<i", new), 1)
        return code, bytes(payload)

    def proof(self, function, code=None, payload=None, linked=None):
        return function(
            decoder,
            self.linked if linked is None else linked,
            self.code if code is None else code,
            self.payload if payload is None else payload,
        )

    def reject(self, function, address, operation, operands, reason):
        with self.assertRaisesRegex(ValueError, reason):
            self.proof(function, self.changed(address, operation, operands))

    def test_actual_numeric002_complete_machine_and_semantic_baseline(self):
        result = graphical.capture_linked_evidence(decoder, self.linked, self.code, self.payload, self.files)
        self.assertEqual(len(self.code), 12263)
        self.assertEqual(len(self.linked.functions), 89)
        self.assertEqual(result["schema"], "aurora-graphical-capture-linked-v1")
        self.assertEqual(result["status"], "checked-contract-requires-independent-review")
        self.assertEqual(result["selector"]["selectors"], {"G": 1, "C": 2, "D": 3, "c": 4, "d": 5, "F": 6, "I": 7})
        self.assertEqual(result["selector"]["invalid_bytes"], 249)
        self.assertEqual(result["authority"]["real_reopens"], [0x5EDE, 0x5F40])
        self.assertEqual(result["pixel"]["failure_successful_store_ordinals"], [0, 55])
        self.assertEqual(result["pixel"]["successful_store_counter"], 0x400D)
        self.assertEqual(result["pixel"]["mmio_store"], 0x4017)
        graphical.require_capture_linked_proof("graphical-console-capture", result)
        with self.assertRaisesRegex(ValueError, "linked proof pending"):
            graphical.require_capture_linked_proof("graphical-console-capture")

    def test_complete_current_proof_gate_rejects_omission_forgery_and_cross_mode(self):
        result = graphical.capture_linked_evidence(decoder, self.linked, self.code, self.payload, self.files)
        graphical.require_capture_linked_proof("graphical-console-capture", result)
        for key in result:
            changed = deepcopy(result)
            del changed[key]
            with self.subTest(missing=key), self.assertRaisesRegex(ValueError, "linked proof pending"):
                graphical.require_capture_linked_proof("graphical-console-capture", changed)
        for mutate in (
            lambda value: value.update(status="accepted"),
            lambda value: value.update(schema="aurora-graphical-capture-source-v2"),
            lambda value: value["files"].update({"language.o": "0" * 64}),
            lambda value: value["selector"]["selectors"].update(G=True),
            lambda value: value["pixel"].update(failure_successful_store_ordinals=[0, 54]),
            lambda value: value.update(extra="unreviewed"),
        ):
            changed = deepcopy(result)
            mutate(changed)
            with self.assertRaisesRegex(ValueError, "linked proof pending"):
                graphical.require_capture_linked_proof("graphical-console-capture", changed)
        with self.assertRaisesRegex(ValueError, "Production cannot carry capture"):
            graphical.require_capture_linked_proof("graphical-console", result)

    def test_exact_original_object_relocations_frames_language_and_payload(self):
        for name in self.files:
            changed = dict(self.files)
            changed[name] = "0" * 64
            with self.subTest(file=name), self.assertRaisesRegex(ValueError, "object/relocation/frame/language/image"):
                graphical.capture_linked_evidence(decoder, self.linked, self.code, self.payload, changed)
            del changed[name]
            with self.assertRaises(ValueError):
                graphical.capture_linked_evidence(decoder, self.linked, self.code, self.payload, changed)
        for address in (0, 0x5414, 0x3DFA, 0xE8A0, len(self.payload) - 1):
            changed = bytearray(self.payload)
            changed[address] ^= 1
            with self.subTest(address=hex(address)), self.assertRaisesRegex(ValueError, "capture payload bytes"):
                graphical.capture_linked_evidence(decoder, self.linked, self.code, bytes(changed), self.files)
        with self.assertRaises(ValueError):
            graphical.capture_linked_evidence(
                decoder, self.linked, self.code, self.payload, dict(self.files, extra="0" * 64)
            )

    def test_every_original_body_and_state_identity_remain_closed(self):
        for name in graphical.CAPTURE_MACHINE_CONTRACTS:
            symbol = self.linked.functions[name]
            code = self.changed(symbol.address, "nop", "")
            with self.subTest(body=name), self.assertRaisesRegex(ValueError, "original capture instruction/byte"):
                graphical.capture_linked_evidence(decoder, self.linked, code, self.payload, self.files)
        for name in graphical.CAPTURE_STATE_CONTRACTS:
            linked = deepcopy(self.linked)
            for index, row in enumerate(linked.symbols):
                if row.name == name:
                    linked.symbols[index] = decoder.Symbol(row.name, row.address + 1, row.size, row.section, row.kind)
            with self.subTest(state=name), self.assertRaisesRegex(ValueError, "storage identity"):
                graphical.capture_linked_evidence(decoder, linked, self.code, self.payload, self.files)
        for address in (0x5438, 0x3E22, 0x7A90):
            code = self.changed(address, "jmp", "*%rax")
            with self.subTest(indirect=address), self.assertRaisesRegex(ValueError, "Indirect or unresolved"):
                graphical.capture_linked_evidence(decoder, self.linked, code, self.payload, self.files)

    def test_real_selector_table_all_entries_and_readonly_storage(self):
        proof = graphical.capture_selector_proof
        self.proof(proof)
        for index in range(34):
            for value in (0, 1, 8, 255):
                changed = bytearray(self.payload)
                if changed[0xE8A0 + index] == value:
                    continue
                changed[0xE8A0 + index] = value
                with self.subTest(index=index, value=value), self.assertRaisesRegex(ValueError, "wrong byte/code"):
                    self.proof(proof, payload=bytes(changed))
        linked = deepcopy(self.linked)
        for section in linked.sections:
            if section[3] <= 0xE8A0 < section[3] + section[5]:
                section[2] |= 1
        with self.assertRaisesRegex(ValueError, "read-only storage"):
            self.proof(proof, linked=linked)

    def test_selector_unsigned_range_numeric_lineage_and_reject_edges(self):
        proof = graphical.capture_selector_proof
        for address, op, args in (
            (0x53DE, "sub", "$0x42,%eax"),
            (0x53E1, "cmp", "$0x22,%al"),
            (0x53F6, "movzbl", "%ah,%eax"),
            (0x5400, "movzbl", "(%rdx,%rax,1),%ebp"),
            (0x541F, "movzbl", "%cl,%edi"),
            (0x53CC, "test", "$0x0,%al"),
            (0x53B3, "mov", "$0xffffffff,%ecx"),
        ):
            with self.subTest(address=hex(address)):
                self.reject(proof, address, op, args, "semantic instruction")
        for address, op, args in ((0x53E3, "jle", "53f6 <changed>"), (0x5406, "jne", "53e5 <changed>")):
            self.reject(proof, address, op, args, "rejection edge")
        for address, target in ((0x53F9, 0xE8A1), (0x5414, 0x101D0)):
            code, payload = self.moved_rip(address, target)
            with self.assertRaisesRegex(ValueError, "table address|writer"):
                self.proof(proof, code, payload)

    def test_scenario_extra_writer_and_release_callee_clobber(self):
        proof = graphical.capture_selector_proof
        code, payload = self.moved_rip(0x5C09, 0x101C8)
        with self.assertRaisesRegex(ValueError, "additional writer"):
            self.proof(proof, code, payload)
        self.reject(proof, 0x7AF5, "pop", "%rcx", "semantic instruction")
        self.reject(proof, 0x7AAD, "mov", "$0x0,%ebx", "RBX clobber")
        self.reject(proof, 0x5422, "call", "7a90 <wrong-helper>", "semantic callee")

    def test_actual_record_pointer_register_and_slot_are_retained(self):
        proof = graphical.capture_authority_proof
        self.proof(proof)
        self.reject(proof, 0x5046, "lea", "0xf8(%rsp),%rcx", "semantic instruction")
        self.reject(proof, 0x504E, "mov", "%rax,%rcx", "pointer register is clobbered")
        self.reject(proof, 0x5B04, "mov", "%rcx,0x8(%rsp)", "pointer slot is overwritten")
        self.reject(proof, 0x5C14, "mov", "0x10(%rsp),%rdi", "semantic instruction")

    def test_record_cross_stale_generation_refresh_and_geometry_mutations(self):
        proof = graphical.capture_authority_proof
        for address, args in (
            (0x5AD0, "%r13,0xf0(%rsp)"),
            (0x5AE8, "%rax,0xf8(%rsp)"),
            (0x5AF5, "%rax,0xf8(%rsp)"),
            (0x5B16, "%rcx,0x118(%rsp)"),
        ):
            self.reject(proof, address, "mov", args, "writer inventory")
        self.reject(proof, 0x5EE3, "mov", "%rdx,0xf8(%rsp)", "semantic instruction")
        self.reject(proof, 0x5F55, "mov", "%rax,0x108(%rsp)", "writer inventory")
        for address in (0x5C4D, 0x5EA4):
            self.reject(proof, address, "mov", "%rax,0xf0(%rsp)", "semantic instruction")

    def test_real_session_close_reopen_and_nonresetting_generation(self):
        proof = graphical.capture_authority_proof
        for address, op, args in (
            (0x5EDE, "call", "3b00 <wrong-open>"),
            (0x5F40, "call", "3a10 <wrong-open>"),
            (0x3A43, "lea", "0x0(%rbx),%rdx"),
            (0x3B1E, "lea", "0x0(%rax),%rbp"),
            (0x5EB7, "mov", "$0x1,%edx"),
            (0x5F26, "xor", "%edx,%edx"),
        ):
            self.reject(proof, address, op, args, "semantic")
        for address, target in ((0x5ED5, 0x10128), (0x5F37, 0x10150)):
            code, payload = self.moved_rip(address, target)
            with self.assertRaisesRegex(ValueError, "real Session close"):
                self.proof(proof, code, payload)
        code, payload = self.moved_rip(0x5C09, 0x10130)
        with self.assertRaisesRegex(ValueError, "additional/reset writer"):
            self.proof(proof, code, payload)

    def test_paired_preflight_and_entry_domination_cannot_be_bypassed(self):
        proof = graphical.capture_authority_proof
        self.reject(proof, 0x5B65, "call", "3a80 <wrong-kind>", "semantic callee")
        self.reject(proof, 0x5B90, "call", "39b0 <wrong-kind>", "semantic callee")
        self.reject(proof, 0x5B4D, "je", "5c19 <skip-preflight>", "bypasses local record identity or paired preflight")
        self.reject(proof, 0x5B28, "je", "5c19 <skip-cross-validation>", "fixed cross/stale scenario branch")

    def test_fixed_pixel_predicates_counter_widths_and_admission(self):
        proof = graphical.capture_pixel_proof
        self.proof(proof)
        for address, op, args in (
            (0x3DFA, "add", "$0x2,%rax"),
            (0x3DF0, "cmp", "$0x0,%rax"),
            (0x3E0C, "cmp", "$0x7,%al"),
            (0x3E14, "test", "%rdx,%rdx"),
            (0x3FA4, "cmp", "$0x36,%rcx"),
            (0x3FFF, "add", "$0x2,%rcx"),
            (0x3DDC, "cmp", "$0xffffffff,%rcx"),
            (0x3CF4, "cmp", "$0xffff,%rax"),
            (0x3E1D, "mov", "$0x0,%ebx"),
            (0x3EB3, "mov", "%rcx,%rax"),
        ):
            self.reject(proof, address, op, args, "semantic instruction")
        for address, target in ((0x3DD5, 0x101C0), (0x3DFE, 0x101F8), (0x3E05, 0x101E8)):
            code, payload = self.moved_rip(address, target)
            with self.assertRaisesRegex(ValueError, "state lineage"):
                self.proof(proof, code, payload)

    def test_pixel_failure_cannot_reach_success_or_add_another_store(self):
        proof = graphical.capture_pixel_proof
        self.reject(proof, 0x3D03, "jae", "3de9 <skip-mapping>", "store bypasses admission")
        self.reject(proof, 0x3E77, "jne", "400d <failure-reaches-store>", "store bypasses admission|failure can reach")
        self.reject(proof, 0x3FA8, "jne", "3e1d <reversed-failure>", "failure edge")
        self.reject(proof, 0x3ECF, "mov", "%ebp,(%rbx)", "another non-frame store")
        code, payload = self.moved_rip(0x5C09, 0x101C0)
        with self.assertRaisesRegex(ValueError, "increment is missing or duplicated"):
            self.proof(proof, code, payload)

    def test_decoded_diagnostics_bind_exact_labels_and_counter_sources(self):
        proof = graphical.capture_diagnostic_proof
        self.proof(proof)
        for address, target in ((0x38B1, 0x101F8), (0x395F, 0x101E8), (0x5E79, 0x101F8)):
            code, payload = self.moved_rip(address, target)
            with self.assertRaisesRegex(ValueError, "diagnostic counter order/source"):
                self.proof(proof, code, payload)
        changed = bytearray(self.payload)
        changed[0xE20E] = ord("!")
        with self.assertRaisesRegex(ValueError, "diagnostic counter order/source"):
            self.proof(proof, payload=bytes(changed))
        self.reject(proof, 0x5DA6, "movb", "$0x1,0xa3cc(%rip)", "clear ready state")
        self.reject(proof, 0x3980, "sti", "", "semantic instruction")


if __name__ == "__main__":
    unittest.main()
