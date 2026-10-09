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


# Independently retained GCC16 image-window003 instruction bytes and operands.
# The fixture relocates direct targets without invoking a compiler/disassembler.
PAIRED_GCC16_LINKED_FIXTURES = {
    'root': """
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
    'walk': """
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
    'layout': """
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
    'bytes': """
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
    'flags': """
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
    'guard': """
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
    'entry': """
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
    'window': """
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
        obj=Admission.paired_object(linked)
        name=graphical.PAIRED_ALIAS;address=0x8240 if linked else 0
        strings=b"\0"+name.encode()+b"\0"
        obj.data=struct.pack("<IBBHQQ",1,0x22,2,3,address,932)+strings
        obj.sections=[(0,)*10,(0,2,0,0,0,24,2,0,8,24),(0,3,0,0,24,len(strings),0,0,1,0),(0,)*10]
        obj.symbols=[decoder.Symbol(name,address,932,3,2)];obj.functions={name:obj.symbols[0]}
        obj.section_data=lambda index:strings if index==2 else b""
        return obj

    def test_gcc16_single_definition_raw_metadata_binding(self):
        for linked in (False,True):
            obj=self.gcc16_single_object(linked)
            proof=graphical.paired_walker_evidence(obj)
            self.assertEqual(proof["canonical"],graphical.PAIRED_ALIAS)
            self.assertEqual(len(proof["definitions"]),1)
            self.assertNotIn("aliases",proof)
            for field,value in (("size",931),("section",0),("kind",0)):
                changed=self.gcc16_single_object(linked);row=changed.functions[graphical.PAIRED_ALIAS]
                values=dict(name=row.name,address=row.address,size=row.size,section=row.section,kind=row.kind);values[field]=value
                changed.functions[row.name]=decoder.Symbol(**values)
                with self.subTest(field=field),self.assertRaises(ValueError):graphical.paired_walker_evidence(changed)
            for index,value in ((4,0x12),(5,0)):
                changed=self.gcc16_single_object(linked);raw=bytearray(changed.data);raw[index]=value;changed.data=bytes(raw)
                with self.subTest(raw=index),self.assertRaises(ValueError):graphical.paired_walker_evidence(changed)
            changed=self.gcc16_single_object(linked);row=changed.symbols[0]
            changed.symbols.append(decoder.Symbol("unproved_alias",row.address,row.size,row.section,row.kind))
            with self.assertRaises(ValueError):graphical.paired_walker_evidence(changed)
            changed=self.gcc16_single_object(linked);row=changed.symbols[0]
            changed.functions[graphical.PAIRED_WALK]=decoder.Symbol(graphical.PAIRED_WALK,row.address,row.size,row.section,row.kind)
            with self.assertRaises(ValueError):graphical.paired_walker_evidence(changed)
        with tempfile.TemporaryDirectory(prefix="gcc16-frame-controls-") as directory:
            root=Path(directory);location="kernel/uefi/tables.hpp:1:1";signature="exact single walker signature"
            (root/"graphical-console.su").write_text(location+":"+signature+"\t128\tstatic\n")
            label=signature+"\n"+location+"\n128 bytes (static)"
            graph='graph: { title: "kernel/uefi/graphical-console.cpp"\nnode: { title: '+json.dumps(graphical.PAIRED_ALIAS)+' label: '+json.dumps(label)+' }\n}'
            obj,linked=self.gcc16_single_object(),self.gcc16_single_object(True)
            with patch.object(graphical,"CPP_OBJECTS",("graphical-console",)),patch.object(decoder,"Elf",return_value=obj):
                (root/"graphical-console.ci").write_text(graph)
                frames,receipts,proof=graphical.graphical_cpp_frames(decoder,root,linked,graphical.PAIRED_ALIAS)
                self.assertEqual(frames,{graphical.PAIRED_ALIAS:128})
                self.assertEqual(receipts[graphical.PAIRED_ALIAS][0]["compiler_symbol"],graphical.PAIRED_ALIAS)
                self.assertNotIn(graphical.PAIRED_WALK,linked.functions)
                for changed in (graph.replace(graphical.PAIRED_ALIAS,graphical.PAIRED_WALK),
                                graph.replace("128 bytes","136 bytes"),graph.replace("tables.hpp:1:1","tables.hpp:2:1"),
                                graph.replace(' }\n}', ' }\n'+graph.splitlines()[1]+'\n}')):
                    (root/"graphical-console.ci").write_text(changed)
                    with self.subTest(metadata=changed),self.assertRaises(ValueError):
                        graphical.graphical_cpp_frames(decoder,root,linked,graphical.PAIRED_ALIAS)

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
                for raw_symbol in (graphical.PAIRED_WALK, graphical.PAIRED_ALIAS):
                    (root / "graphical-console.ci").write_text(graph.replace(graphical.PAIRED_WALK, raw_symbol))
                    frames, receipts, aliases = graphical.graphical_cpp_frames(decoder, root, linked)
                    self.assertEqual(frames, {graphical.PAIRED_WALK: 128})
                    self.assertEqual(receipts[graphical.PAIRED_WALK][0]["source"], "kernel/uefi/tables.hpp")
                    self.assertEqual(receipts[graphical.PAIRED_WALK][0]["compiler_symbol"], raw_symbol)
                    self.assertEqual(len(aliases), 1)
                    self.assertEqual({call.args[2].name for call in associate.call_args_list},
                                     {graphical.PAIRED_WALK, graphical.PAIRED_ALIAS})
                    self.assertIn(graphical.PAIRED_ALIAS, linked.functions)
                node = graph.splitlines()[1]
                for changed in (
                    "", graph.replace(graphical.PAIRED_WALK, "unproved_alias"),
                    graph.replace(node, node + "\n" + node.replace(graphical.PAIRED_WALK, graphical.PAIRED_ALIAS)),
                    graph.replace(node, node + "\n" + node),
                    graph.replace(' label:', '.clone" label:', 1),
                    graph.replace(' }\n}', ' shape : ellipse }\n}'),
                    graph.replace("128 bytes", "136 bytes"),
                    graph.replace("tables.hpp:1:1", "tables.hpp:2:1"),
                ):
                    (root / "graphical-console.ci").write_text(changed)
                    with self.subTest(changed=changed), self.assertRaises(ValueError):
                        graphical.graphical_cpp_frames(decoder, root, linked)
                (root / "graphical-console.ci").write_text(graph.replace(graphical.PAIRED_WALK, graphical.PAIRED_ALIAS))
                # Metadata must not let an unproved or nonidentical alias reach
                # the shared frame join. The actual raw .ci spelling is valid.
                original = obj.functions.pop(graphical.PAIRED_ALIAS)
                with patch.object(decoder, "object_stack_rows", side_effect=AssertionError("unproved alias reached join")):
                    with self.assertRaisesRegex(ValueError, "Missing exact"):
                        graphical.graphical_cpp_frames(decoder, root, linked)
                    obj.functions[graphical.PAIRED_ALIAS] = decoder.Symbol(
                        original.name, original.address + 1, original.size, original.section, original.kind)
                    with self.assertRaisesRegex(ValueError, "Diverged"):
                        graphical.graphical_cpp_frames(decoder, root, linked)
                obj.functions[graphical.PAIRED_ALIAS] = original
                old_bytes = linked.function_bytes
                linked.function_bytes = lambda symbol: b"\xcc" * symbol.size if symbol.name == graphical.PAIRED_ALIAS else old_bytes(symbol)
                with patch.object(decoder, "object_stack_rows", side_effect=AssertionError("nonidentical alias reached join")):
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
            for records in ([], associations[symbol] * 2,
                            [dict(object="graphical-console.o", source=source, bytes=16)],
                            [dict(object="graphical-console.o", source=source, bytes=24, compiler_symbol=symbol)],
                            [dict(object="graphical-console.o", source=source, bytes=16,
                                  compiler_symbol=next(other for other in graphical.SESSION_VALIDATORS if other != symbol))],
                            [dict(object="console.o", source=source, bytes=16)],
                            [dict(object="graphical-console.o", source="kernel/foreign.hpp", bytes=16)]):
                changed = deepcopy(associations)
                changed[symbol] = records
                with self.assertRaises(ValueError):
                    graphical.verify_session_frames(frames, changed)

    def test_graphical_only_validator_emission_attributes(self):
        declaration = "    static auto validate(const void *grant, std::uint64_t generation, bool operation) -> void {"
        guard = ("#ifdef AURORA_UEFI_GRAPHICAL_CONSOLE\n"
                 "    // Preserve two independently bound bootstrap authority frames in the paired profile.\n"
                 "    [[gnu::noinline, gnu::noclone, gnu::noipa]]\n"
                 "#endif\n")
        def check(text):
            if text.count(declaration) != 1 or text.count(guard + declaration) != 1:
                raise ValueError("Missing exact graphical-only validator emission declaration")
            if text.count("gnu::noipa") != 1:
                raise ValueError("Ambiguous validator emission attributes")
        dependencies = {name: (ROOT / name).read_text() for name in (graphical.CAPTURE_NATIVE, *graphical.CAPTURE_SOURCE_PINS)}
        graphical.capture_source_evidence("graphical-console-capture", dependencies)
        legacy = dict(dependencies)
        for space in ("console", "display"):
            legacy["kernel/" + space + "-session.hpp"] = dependencies["kernel/" + space + "-session.hpp"].replace(guard, "")
        graphical.capture_source_evidence("graphical-console-capture", legacy)
        for space in ("console", "display"):
            mixed = dict(dependencies)
            mixed["kernel/" + space + "-session.hpp"] = legacy["kernel/" + space + "-session.hpp"]
            with self.assertRaises(ValueError):
                graphical.capture_source_evidence("graphical-console-capture", mixed)
            text = (ROOT / "kernel" / (space + "-session.hpp")).read_text()
            check(text)
            for changed in (text.replace(guard, ""), text.replace("gnu::noipa", "gnu::noinline"),
                            text.replace("#ifdef AURORA_UEFI_GRAPHICAL_CONSOLE", "#if 1"),
                            text.replace("#ifdef AURORA_UEFI_GRAPHICAL_CONSOLE", "#ifdef AURORA_UEFI_CONSOLE"),
                            text.replace(guard, guard + guard)):
                with self.subTest(space=space), self.assertRaises(ValueError):
                    check(changed)

    def test_authorized_memory_push_reads_old_rsp_before_allocation(self):
        name,base="bounded_memory_push",0x1000
        symbol=decoder.Symbol(name,base,17,1,2)
        code={base:decoder.Instruction(base,4,"sub","$0x18,%rsp"),
              base+4:decoder.Instruction(base+4,4,"push","0x8(%rsp)"),
              base+8:decoder.Instruction(base+8,4,"push","0x18(%rsp)"),
              base+12:decoder.Instruction(base+12,4,"add","$0x28,%rsp"),
              base+16:decoder.Instruction(base+16,1,"ret","")}
        permit=dict(owner=name,sites={base+4:8,base+8:24})
        result=decoder.analyze_function(symbol,code,{base:name},memory_pushes=permit)
        self.assertEqual(result["local_peak"],48)
        self.assertEqual([(row["depth_before"],row["source_old_rsp"],row["depth_after"])
                          for row in result["stack_memory_pushes"]],[(24,8,32),(32,24,40)])
        self.assertEqual(result["returns"],1)
        with self.assertRaises(ValueError):decoder.analyze_function(symbol,code,{base:name})
        for changed in (dict(owner="other",sites=permit["sites"]),dict(owner=name,sites={}),
                        dict(owner=name,sites={base-4:8}),dict(owner=name,sites={base+4:-8}),
                        dict(owner=name,sites={base+4:16}),dict(owner=name,sites={base+4:24,base+8:24})):
            with self.subTest(permit=changed),self.assertRaises(ValueError):
                decoder.analyze_function(symbol,code,{base:name},memory_pushes=changed)
        for address,op,args in ((base,"sub","$0x8,%rsp"),(base+4,"push","0x8(%rbp)"),
                                (base+4,"push","0x8(%rsp,%rax,1)"),(base+4,"pushw","0x8(%rsp)"),
                                (base+12,"add","$0x20,%rsp")):
            changed=dict(code);row=code[address];changed[address]=decoder.Instruction(address,row.size,op,args)
            with self.subTest(instruction=(address,op,args)),self.assertRaises(ValueError):
                decoder.analyze_function(symbol,changed,{base:name},memory_pushes=permit)
        # The authorized source must end below the incoming return address at
        # the OLD RSP. Checking after the push would incorrectly accept this.
        short=decoder.Symbol(name,base,13,1,2)
        edge={base:decoder.Instruction(base,4,"sub","$0x8,%rsp"),
              base+4:code[base+4],base+8:decoder.Instruction(base+8,4,"add","$0x10,%rsp"),
              base+12:decoder.Instruction(base+12,1,"ret","")}
        with self.assertRaisesRegex(ValueError,"pre-push"):
            decoder.analyze_function(short,edge,{base:name},memory_pushes=dict(owner=name,sites={base+4:8}))
        branched={base:decoder.Instruction(base,4,"sub","$0x18,%rsp"),
                  base+4:decoder.Instruction(base+4,2,"jne",f"{base+12:x} <skip>"),
                  base+6:decoder.Instruction(base+6,4,"push","0x8(%rsp)"),
                  base+10:decoder.Instruction(base+10,2,"jmp",f"{base+16:x} <join>"),
                  base+12:decoder.Instruction(base+12,4,"nopl","0x0(%rax)"),
                  base+16:decoder.Instruction(base+16,4,"push","0x18(%rsp)"),
                  base+20:decoder.Instruction(base+20,4,"add","$0x28,%rsp"),
                  base+24:decoder.Instruction(base+24,1,"ret","")}
        with self.assertRaises(ValueError):
            decoder.analyze_function(decoder.Symbol(name,base,25,1,2),branched,{base:name},
                memory_pushes=dict(owner=name,sites={base+6:8,base+16:24}))
        extended=dict(code);extended[base+17]=decoder.Instruction(base+17,4,"push","0x8(%rsp)")
        with self.assertRaisesRegex(ValueError,"Unused"):
            decoder.analyze_function(decoder.Symbol(name,base,21,1,2),extended,{base:name},
                memory_pushes=dict(owner=name,sites={**permit["sites"],base+17:8}))

    def test_graphical_memory_push_authorization_is_closed(self):
        base=0x2000;name=graphical.STACK_MEMORY_PUSH_OWNER
        owner=decoder.Symbol(name,base,5437,1,2);payload=bytearray(base+5437);code={}
        for offset,displacement,raw in ((0x79C,8,bytes.fromhex("ff742408")),(0x7A6,24,bytes.fromhex("ff742418"))):
            address=base+offset;payload[address:address+4]=raw
            code[address]=decoder.Instruction(address,4,"push",hex(displacement)+"(%rsp)")
        permits,receipts=graphical.stack_memory_push_evidence({name:owner},code,bytes(payload))
        self.assertEqual(permits,{name:dict(owner=name,sites={base+0x79C:8,base+0x7A6:24})})
        self.assertEqual(len(receipts),2)
        self.assertEqual(graphical.stack_memory_push_evidence({}, {}, b""),({},[]))
        for symbols in ({}, {name:decoder.Symbol(name,base,5436,1,2)},
                        {name:owner,"alias":decoder.Symbol("alias",base,5437,1,2)}):
            with self.subTest(symbols=list(symbols)),self.assertRaises(ValueError):
                graphical.stack_memory_push_evidence(symbols,code,bytes(payload))
        for address,row in code.items():
            changed=bytearray(payload);changed[address+3]^=8
            with self.subTest(bytes=address),self.assertRaises(ValueError):
                graphical.stack_memory_push_evidence({name:owner},code,bytes(changed))
            for op,args,size in (("push","0x8(%rbp)",4),("push","0x18(%rsp)",4),
                                 ("pushw",row.args,4),("push",row.args,5)):
                if (op,args,size)==(row.op,row.args,row.size):continue
                altered=dict(code);altered[address]=decoder.Instruction(address,size,op,args)
                with self.subTest(operand=(address,op,args,size)),self.assertRaises(ValueError):
                    graphical.stack_memory_push_evidence({name:owner},altered,bytes(payload))
            altered=dict(code);del altered[address]
            with self.assertRaises(ValueError):graphical.stack_memory_push_evidence({name:owner},altered,bytes(payload))
            altered[address+1]=decoder.Instruction(address+1,4,row.op,row.args)
            with self.assertRaises(ValueError):graphical.stack_memory_push_evidence({name:owner},altered,bytes(payload))
        with self.assertRaises(ValueError):graphical.stack_memory_push_evidence({name:owner},{},bytes(payload))

    def test_capture_memory_push_layout_stays_separate(self):
        base=0x2000;name=graphical.STACK_MEMORY_PUSH_OWNER
        owner=decoder.Symbol(name,base,8448,1,2);payload=bytearray(base+8448);code={}
        for offset,displacement,raw in ((0xC86,24,bytes.fromhex("ff742418")),(0xC90,40,bytes.fromhex("ff742428"))):
            address=base+offset;payload[address:address+4]=raw
            code[address]=decoder.Instruction(address,4,"push",hex(displacement)+"(%rsp)")
        permits,receipts=graphical.stack_memory_push_evidence({name:owner},code,bytes(payload))
        self.assertEqual(permits[name]["sites"],{base+0xC86:24,base+0xC90:40})
        for extent in (5437,8447,8449):
            with self.subTest(extent=extent),self.assertRaises(ValueError):
                graphical.stack_memory_push_evidence({name:decoder.Symbol(name,base,extent,1,2)},code,bytes(payload))
        for address,row in code.items():
            altered=dict(code);altered[address]=decoder.Instruction(address,4,"push","0x18(%rsp)" if row.args=="0x28(%rsp)" else "0x28(%rsp)")
            with self.assertRaises(ValueError):graphical.stack_memory_push_evidence({name:owner},altered,bytes(payload))
            changed=bytearray(payload);changed[address+3]^=16
            with self.assertRaises(ValueError):graphical.stack_memory_push_evidence({name:owner},code,bytes(changed))
        body={base:decoder.Instruction(base,4,"sub","$0x30,%rsp"),
              base+4:decoder.Instruction(base+4,4,"push","0x28(%rsp)"),
              base+8:decoder.Instruction(base+8,4,"add","$0x38,%rsp"),
              base+12:decoder.Instruction(base+12,1,"ret","")}
        sym=decoder.Symbol(name,base,13,1,2);grant=dict(owner=name,sites={base+4:40})
        result=decoder.analyze_function(sym,body,{base:name},memory_pushes=grant)
        self.assertEqual(result["stack_memory_pushes"][0]["depth_before"],48)
        with self.assertRaises(ValueError):decoder.analyze_function(sym,body,{base:name})
        body[base]=decoder.Instruction(base,4,"sub","$0x28,%rsp")
        body[base+8]=decoder.Instruction(base+8,4,"add","$0x30,%rsp")
        with self.assertRaisesRegex(ValueError,"pre-push"):
            decoder.analyze_function(sym,body,{base:name},memory_pushes=grant)

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
        result = dict(machine=graphical.paired_gcc16_exact_machine(decoder, symbols, code, starts, payload),
                      helpers=graphical.paired_gcc16_helper_effects(decoder, symbols, code, functions),
                      guard=graphical.paired_gcc16_guard_contract(decoder, symbols, code),
                      root=graphical.paired_gcc16_root_storage(decoder, symbols, code, starts, functions),
                      walker=graphical.paired_gcc16_walker_storage(decoder, symbols[graphical.PAIRED_ALIAS], code, starts))
        levels = graphical.paired_gcc16_level_induction(decoder, symbols[graphical.PAIRED_ALIAS], code, starts,
            functions[graphical.PAIRED_ALIAS], (result["walker"]["bitmap_store"],), result)
        return result, levels

    def test_gcc16_closed_storage_profile_and_relocation(self):
        for shift in (0, 0x100000):
            fixture = self.paired_gcc16_linked_fixture(shift)
            proof, levels = self.gcc16_storage_proof(*fixture)
            self.assertEqual(len(proof["machine"]), 8)
            self.assertEqual(proof["root"]["objects"], {"bitmap": (0x48,16), "snapshot": (0x58,24),
                "helper_closure": (0x70,24), "closure": (0x88,56)})
            self.assertEqual(len(proof["root"]["guards"]), 6)
            for seed in range(4):
                self.assertTrue(levels[seed]["caller_memory_contract"])
                self.assertEqual(levels[seed]["established_child_seed"], seed-1 if seed else None)
                self.assertEqual([call["level"] for call in levels[seed]["calls"]
                                  if call["target"] == graphical.PAIRED_ALIAS], [seed-1] if seed else [])
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
        for offset in (0x6BE,0x6E0,0x705,0x729,0x750,0x777):
            altered = dict(code); row = code[root.address+offset]
            altered[row.address] = decoder.Instruction(row.address,row.size,row.op,
                f"{symbols[graphical.PAIRED_LEVEL_HELPER].address:x} <wrong>")
            with self.subTest(guard=offset), self.assertRaises(ValueError):
                graphical.paired_gcc16_root_storage(decoder,symbols,altered,starts,functions)
        for offset,op,args in ((0x7,"mov","0x8(%rdi),%r10"),
                               (0xAC,"mov","$0x1,%r9d"),
                               (0xB1,"mov","$0x111000,%r10"),
                               (0x8E,"mov","$0x100000,%r15"),
                               (0x644,"lea","0x48(%rsp),%rcx"),
                               (0x792,"cmp","$0x11,%rax"),
                               (0x7A8,"mov","$0x4,%ecx")):
            altered=dict(code);row=code[root.address+offset]
            altered[row.address]=decoder.Instruction(row.address,row.size,op,args)
            with self.subTest(root=offset), self.assertRaises(ValueError):
                graphical.paired_gcc16_root_storage(decoder,symbols,altered,starts,functions)
        guard=symbols[graphical.PAIRED_GUARD]
        for offset in (3,8,0x12):
            altered=dict(code);row=code[guard.address+offset]
            altered[row.address]=decoder.Instruction(row.address,row.size,"jae",row.args)
            with self.subTest(overflow_or_disjoint=offset), self.assertRaises(ValueError):
                graphical.paired_gcc16_guard_contract(decoder,symbols,altered)

    def test_gcc16_save_slots_and_recursive_lineage_reject_mutations(self):
        functions,symbols,code,starts,payload=self.paired_gcc16_linked_fixture()
        proof,levels=self.gcc16_storage_proof(functions,symbols,code,starts,payload)
        for name in (graphical.PAIRED_ROOT,graphical.PAIRED_ALIAS,graphical.PAIRED_LAYOUT):
            symbol=symbols[name];frame=graphical.paired_gcc16_slot_frame(decoder,symbol,code)
            for address,register,slot in frame["saves"]:
                for args in (code[address].args.replace(hex(slot),hex(slot+1)),
                             code[address].args.replace("%"+register,"%eax")):
                    altered=dict(code);row=code[address]
                    altered[address]=decoder.Instruction(address,row.size,row.op,args)
                    with self.subTest(save=(name,address,args)), self.assertRaises(ValueError):
                        graphical.paired_gcc16_slot_frame(decoder,symbol,altered)
            for address,register,slot in frame["restores"]:
                altered=dict(code);row=code[address]
                altered[address]=decoder.Instruction(address,row.size,row.op,row.args.replace(hex(slot),hex(slot+8)))
                with self.subTest(restore=(name,address)), self.assertRaises(ValueError):
                    graphical.paired_gcc16_slot_frame(decoder,symbol,altered)
        root=symbols[graphical.PAIRED_ROOT];row=code[root.address+0x12];altered=dict(code)
        altered[row.address]=decoder.Instruction(row.address,row.size,"xchg","%r13,%rax")
        with self.assertRaises(ValueError):
            graphical.paired_gcc16_slot_frame(decoder,root,altered)
        walk=symbols[graphical.PAIRED_ALIAS]
        for offset,op,args in ((0x15,"jae",code[walk.address+0x15].args),
                               (0x76,"movb","$0x1,(%rdx,%rcx,1)"),
                               (0x350,"mov","%rax,%rdi")):
            altered=dict(code);row=code[walk.address+offset]
            altered[row.address]=decoder.Instruction(row.address,row.size,op,args)
            with self.subTest(walker=offset), self.assertRaises(ValueError):
                graphical.paired_gcc16_walker_storage(decoder,walk,altered,starts)
        for offset,op,args in ((0x33A,"lea","0x0(%r9),%ecx"),
                               (0x33E,"mov","%rsi,0x18(%rsp)"),
                               (0x350,"mov","%rax,%rdi")):
            altered=dict(code);row=code[walk.address+offset]
            altered[row.address]=decoder.Instruction(row.address,row.size,op,args)
            with self.subTest(induction=offset), self.assertRaises(ValueError):
                graphical.paired_gcc16_level_induction(decoder,walk,altered,starts,functions[walk.name],
                                                       (proof["walker"]["bitmap_store"],),proof)

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



# Retained checkpoint011 GCC14 capture bytes; reviewed independently before acceptance.
CAPTURE_SEPARATE_14_SNAPSHOT = (
    'c$}=gTW@7aa;5oS@>Ly`e!mo;hZ;@yjDVggL26+d7z_e_&7_J!Mw1a)nJvtJpKtAR$T&Pak)?-0qg9a%#`eA4&6cg@Zf5@PKlHD6'
    '_w$E8{`(K(@zdwK`}L$he{NrX{^5^5{P@?$r@uUZZe#uUJf7N@@$-+Nj5t>cA?@;G`}*|w)IR+5)IR@wH`@J&@%Zrkc)vb4<B~O|'
    '{J4I(o9lsp|8I|X4{LtdkK^kz|NGawhxz!|55~A3e;UJv^P|QO|LKS4pPP$`(R&Vdw&-^0Ik#E5?KWg<hK)70Y5Oj`#H?#C*OKqu'
    'm{~&Y%ed|57(e{K|LKSE>#vvJ^Y!`Z$A0(l<F6%sOyR@*-NV;kKm7FY^}|np_jey`xEwuopK4lRj$Y!jqlP-Ncg?uIc8g~DTKpQj'
    'hOzQ0EAl2Y8sBRSJ=dwx_kH{6`G-IL-#>hK{xbi5{N3L<&k!H}?DT*4^OrXM^5N@q`)M8j%>>>bQ~BZUVL$%;^H=@!|Kf+o|E^!Z'
    'JhjuGo|vlRU+kx~c*?`Pd-&<}i2dR7)8m&lzT7=N{Qbk@!|~)#&tIPSjmOWt2CKM!`t9%U@A^1Dc|SaUSig?-S^wtw<tI;HzTCb1'
    '`Shaa2cL)L$L;yIhw<~%<HO_E=MP^Ww4@)tw0^%{AM);ppY&vw|9`%`*-z_XJz+Rc>!;@rj}Q01z5LTJeA<WmN8Wkf>Gk{9FY5!#'
    '_+>qvUh;qa)4%@npa1z!AOH0~|CfLK_@{sPr+<9+!~gA{|MXA)`#=7}pZ@E|fB5tN`7eL|umAaXe&fIV<A48e|N76r_Z$E4r++$r'
    '<Nx_jKYV(e3k!K~_M?6N^7Tny_SpZ8xjNSVbNlW7vCTiM`^{gx{1;Zpf34@wKQhdZ|I45M{NIlM^WRhW13%!ezOH@u;pMk~{`{FA'
    '-M5FIzG5wZ&;+bcea%1o3x9eU{qy7f{fAHMOPlRW`@_FIKWc=#PyB;-KYe-bBY$q=^WE`>&*SvJPhTIt+<jWdpWl7s={HaR{KI<q'
    '^7PyBlb3h+_LJ9_)qi|ipB`U+&OcmF#~)9hpg&=j56^cpz{}_V;c$VM{}^{KFMIs>_|x$-z4z%i$N48OUvT{N<v)(UdH+4f@4Wx<'
    '@!RKjJ$~i<=Zl|z_<Z?sFaLFX)XRT-`>xYZFrLS+Up{~R^6>>{{`~~NKWe#ueEFt7{!rrXKxntEbiYj<aoe=|Ovdk2Mro#|ZenVy'
    '?6RYebMGBv;+cUzOvb)`?xR3$&5*qHbpw&P<&|pat;bNjHKnxKL+sTAXHu*=myuIg#uwf-IFR<nW0{;kvKU}x1b|!UV?@V0`#wA9'
    '7=g9mgR7H2w3S0>J4e8@#gh6;ouQ|H``l||Vmbi!*itsN?zTgZ&g7A6GdWp1s~xt@F<mYEEUY>VxZMg95r!jRrQ6TH;V^&vp@uN$'
    '4xsw(JMMi%mr`3QCVQ5>=3YarzC`QNj<(fmckDY<6Wi|b?NAriKtPLp!A?839eGEqWt*jrGItAe=hVA%Wi8&@>}jeCE)G63r^(lO'
    'cjM6jz#o5@gGrb!u58M#)i1Z=4oS<L66=v&VUknN{DV3NMv(i6ktmftQyFeOSMO_*;~hdUu3?Tb1aC{7VJ@G1EY|03^Bjekn^;s#'
    'tC_XDTiy6!#wb_M{T|jaP|uOj-h9MrVr9^}Fr~RHf!w=Uj7fvYA28Zwmra<ZGuAL|#?5gxF*lu=g=Gax#p3$*rT3DW8!7uSs?B&#'
    '->tiWMa}4^@wPE<ZFRS@UvY%E|JEQU|H6yruD+%mcPzYnh)W}F=FOS9R@$vu=SwQp@0i9Kk@?O(ls4+$8sl&_8GoxDrqfM{c?D;~'
    'E;+><oZrnZR@VFGJ<eeQuGdG&!4x|;zq9k(L2d<zKmK4VcIkOhY_%lI)P#iz6&OaD)2!{PpSI@FVhni(YhxL}(;PKVv#%WbA{O8U'
    'CRd&k@fTyQ>G(DNWjj_Cyf3znxlNyVSOHW@A7Ptj`Zi@j@@DzYqlvXYEM8{08rCwivaWzu&jt?~t}<#44ZvH=<sCo{W}nsV5J#|<'
    '-?>K3OO(e(LDki)k4_d-g54S4#ac_VJK5>W$~eVpA&=fBxMW?(DbH-H#=rIKlVLi%-j?Q>?`d}j!FnlR*}!(-y{u}r7$R=g(%5|s'
    'Oqi$p<`&~Ld-KW1OatG^LREp{GU|fH!rY4)&GF$({qViyILx$ATf<)_yTiuqa*x^Ge(+&}JJ-b5?_?_W;AR7adjKkZOR+82apYB6'
    'Pa~S{YwezA2Vz-W!NzMlzYL%<?_79bj*Gdh#HCy}pk;>}4inx?6kart7bDoB=f?>&X>mfxW!-xA@!(aWuYD7!k~d*&VOIr^na{dw'
    '&tMjg-*J3HM9Cor!YxQ61yXXkLiTG8^v55D&DmSG@V8aL78iOV64n@7th32u7LnE^U;W5~74c<wKM7ryIO1+T{~(G?N*YelSw7(L'
    'Xh6R0wdVA86ztq!oTi&PCjm0YuyK`wS>pgc4?Au@`!GL{!e(0tV%P^fBH%YAqy(l{U<^P>3Ie58!y6QDawyCPE6O}JUv58IY*!Xo'
    '93R}J)57$tq%pH|JLd_S1O%RS1UrV9li7pe<XXeFo!2K$edpPl?8%#AcXb+Ea^<}uw5C`9YBHfNv3!eoVLVjE&OoScwt~FFq{IZ?'
    'Ud%JT8qgwCM@%nk0w6Fg+|fJUsS*=Rh{F>SCYIDvDigcIF43i<4qLAR#hH}y#wo7N@1PAUx_2kww0Mt2?8OV4ko}w~FGnzla@J)h'
    'y3&M%sw5D<f9x?2iP(frj@FL72d<vG9Zc?SsMpnlC;{$7T%Oj|wpic=O3Q%Sp4am*&V+9Hj(dSTMXzju9@tR8UupuOFe~OE*cDQc'
    'Ee1GVC2re}n>h6H)nhLxIMW-jFpwIzBEW2%9F}WS1W%kx#QBX)WPAs*F?z&1-ExIc?;1QO_1lj=@UAgY#gAF6_-o2;t`!DE*B1th'
    'xj-ypIAV?EFCDyeCkULPWxZy%7b4>S@A<fv1(1`?WE2QZXQ^O4xI}0vSTi6844X4J4zp&FT?RB5)fDG>eUOV^`QG!7hdX0Hik3J2'
    'H5$Y-zz&_=aOkovT#dDG_$aPaAziU_(F%C(YTC}Yn(=qSR1pk7wQ%ihA>rAEDQ#jsAUL7l4!V=A-*&CKfzwPt1F&ab4R~#>Xs_h+'
    '`gni$@RzsyPv70Ixd#~cyxgyuj$l_y=|seCCx}V_9S4bC*(D+?6o#L|9+_6ij_2=)qkH3y#df{J^Z0pvYSJ^`+t@nh;lnQqjn9u?'
    'pT@cna{ovB3sZBitpUH}kl6Ix-f!H~1K)6r=$CCVc-Sp3Y2e;y3!D`z#U&e|EF=PHJ{0w7JMPDe$Bvxgeu=oTpa*pmvl>RAe^{8&'
    '43Th<96}<H(qad%oahePX+)IJ<zxGAUo_)iwEc2kMpg%=kQc8B-Y2n^tyLuA5_}7$8JC1-#IA`CgOH05g6Jap958wL_<7fUdU$;P'
    'ayOpOPq(Fv0M(jqrNT<UUnU_KO6m#1E?75b5UD|I^|Cfx4Q~%3QCNF>^Ys1r^r?M$u|87}gFQe`2sXr9P}|zP3UCo2IAy}e;NH#c'
    ';R7#Vcc~~Wyl248`}+rf{M7Cq{xFWG`+)U?ykSVYcj)tgAEZgJjord{(1FR=jE;_AYa@P52Un4~<CvkndHU1i!<Y5&;x;K6{)J0S'
    'MsJv4lceqZE20cTf+oo7RiNP6B22O)CJu;MFWu&`!sVlXX0AV;O!8&IM}y)<i9Zx89@!z3o>vArV35s<4w+71gFpD-agh>WjPR3Y'
    '5+8K=_`3(-q}|{B&n8s)xZC*hGR*V|wmu6qY+(ufOJgj*pvg)l$=lQ1kih`Ks!)Dn8_F_A2qW-d-VXC+{j{F0?6Rz~og2Ju?!+vJ'
    'cEGnGCDj8StYJha<L-Tk+5$L>mjLcF#tK_{WA=AX=Z98a7n$T8iW512q(MQ8^+Zgku_Q=Y=DIO=17_|);*pDQIGHK9!`p{`yl=lf'
    'etoe>tgaUf+3>Ie-$*56Xmt|J<{%QA&=(poZoD6t-8PtorXw<qfr4CD&;DgS-R<9AteqIYiE^N7YGY%aP*%Vf`@<EP@))Pd#xn!C'
    'VkcV^498~Du(0sv+4t+$^)eqVh()5bd4Y^|BL`+kW)x<4CMR(QpPxnw3%<Bk6g$NF!5x6%4P@OT^?}mym$MH=<g+9PCfr77TXH51'
    'vn?VO_b*bJn8X$|47(UQ9+TGiFlc$d{p{0w2P-C1_~3*Fo4^)Cuyt0BP-nG?A3DlUyHGw04_L;XeH!|Ebk_B=FI*puz?<UEtQ@p-'
    '0kb|fpsHI!$jZy0PQa}K=~~+=ru9}0To*$rt6V?&^W!Nfzj%%ddyCb>cC|<l>wxM(?NkB=qSwL&3CgS6qLrx<-@t6$5J_IaTtEML'
    'J^k{!o){C0)bJA&C_Ia$LRx}0Nkk?OaFul|nJM=`4I!gKLL_4$Pic?qhaa5c^W)Pi>XySmV8j++aj4f7BGIEsn6Z=#_k>>}d(f!a'
    'jT{q##h@)3u6*p1y*~e9&XWQ5k$eXA;fRS7^$cP)G+&L7g~Vrp^ku~yOv_At^qY8!I*06CJ@#>ay?=$nIh^s+AhkDB9u~gikscdC'
    '-vB%w3Ach_wW+-to{vRpOVK&$lkx`0Kewmn*O?~rbS*fDZ3@B_Bj+i&yEgQ2LI^yfP!S%(6c!W4anp)Zu&{5<<Qe|)a1k`)tcT1F'
    '5sqMhA7TLv6g3EaW4KUZGtNSenOZz$jbraKmsY{FW7py0*-yXReG3nmSSBiH6M-<5@(c~qH}<Mc(yKrOv_V*xwtpJBvIu+=vusfH'
    ';f;Yj|Mu{u{rW;9h&Tvo=%6(&G^l37*w)Ul6k-b><HpebOgHdwRPhclGnOx+h_1rgm-XrMef#qI(!f%fX7K72Ry8D*3~Cfdj|7GU'
    '_~|q;rqU7Z0D^?LTeG;x8cp}c+rRww`SrP|4SqFlZLb?6P|b!3AtWymZfH>KKpuX9k7%E^_$sN|U`8G=zI-lZ^~FbW3C=Qo+P&Jb'
    'BCAn~bz=XZQL-cC4o_Q?c@BhvTsHI%!UCpgTS~_XzcyxIJ&Ojnr{6xF4o?5jBuWDAiu{9^V8=N+kY{Y3j2K3S&Ya^YVMQ3WC*%Vf'
    '1xgB=^V*hK(Oo`%+_&fFkH570uguBubnC74XmVEEv{KMDtSjDQe0L0KfKgQM>dY4OA3YH|e}^tFBe!Y7o2NfMElAaupHGiA#*cv7'
    '(VkmG3}!zpGf&LLr?JJ33s!AggR7O#N}g4>5K<gnH0bit`|HDT+WGMj?2{%rzkb?*<w5`YN^F5tOB9w4p2MZEPQpNou?6B}LL;Kx'
    'V~=<-UmV9eHoxAF@#XO^>*38TO~fU^H!=}Ch3H+0l?Yll8{(bMj2$#(p5VEttyP?{33+0%N-*oqEFpd#*8PWm_jrD|VS$;H4STD+'
    'HPPJmnxx^YAcwUH8Uwu4rUHiE9aGwyHZ!}~>&C-hgv=QXPUGaDU0uZH;GOaQ;zr-d=oEoh3!NZn>dnQ338#EU@~cc@xHd&f`TjVk'
    '=X>520nZ8p-4Gx~S+OBrh;BGfk}T3@b&v8lGxKp~L~N~bMJ)Qp^XJ_&!0_AK?|`-O-Og&ybYPehybRi4K_x*YA}kd`K&Z})YtTiR'
    'sNom9I2-M_+!*Km9{e%V0PDfrHN7_X7%MfLwpS5$*YQUL40;UZ&+xWuLkhVIw~+u}$M)0pNRNM2f`nw*dG(vNt6R?43BkWQ%R>kk'
    '+C&_qgKpb_RvoH6ag@Z*ApA^k0}3H2>BbnJpC0+3PjA1)6hak`OXxnk24a9mh7GyHLo&7(Goobc++s~l6inY@*@i%*fb)Kwvui*b'
    'cl2&Wa0A5HgD~DV{LwMe1n)*_rumR0l7S4OI2y|#%PXSxja4ZV;Q3>FdTPI&XNQ$0)WyIecS1qg+n_iy4wJG&4=^x4?nnkAyY`l9'
    'DGi6x-XntFTt5BN`ttMRJo)v<_3QY#J^b|I8U;H=3@0>iUWA1d;s5}<<wFtyZSV;&GLXAuJ0ygsys$3Red}*v<Y7I3S@Q;nq&~bc'
    'JMixy$v8c;(Fl&(j+f*?O-^n1Ky^ZiW(wG#orc)YD!4b_a(epnXb<Okf(0%~G5){uXDY}8?`t|LMR~ir2H#SbLLM{Um(F^aGrT3?'
    'FZzJfqW;+Cd|J=XAC82e=QCd$p%N%#EQrU9tQm8f-BKd{#*TJ2Js&}`r`19cdZ9S8Vsb|N<@Vjjzr^K&3!u7E3>MdML|~W@#8P$-'
    'GafY&T6tfc4;7-SXXzoJIAUf+E*}5+Zk*qF0c-{h3T;Xmu;7<jzdnf7jnI>pqR|3cQOSfh@WhmOpgGd2ABS6)4?Q!J#xD^lok4Y3'
    'z@K<BbF`l2%$wDP1i=PP+6BrJ9Z{Is(5bS8_jmX0q5bjk%W<yDC&F$Qc8!<A(PD+F*{HoO)OupciU){v0M%e|4i8wTCr1ca@K=vi'
    'n%55%tz`(Xh){#x<@2<O3Dw&W35i9Ws&?(c6z#o4?Z_ghJ^Bshdr*?|GspeidiZhx@#8c2cr6g(3H5<QZ7C$obtO~7hK%T(T$u)C'
    'Ra24O0NT=tx7S_|JPRh+;>Aekn00^muwEVxU=bIG-BRq}Ah<5F)vE}ESq<3~mZV3@6=|=OF-)+7p4J2Y?;rjd<Kugd{f+Y=n;0HL'
    'Ex0`14J`y-nFWEBtvawKwxlv)T;Pv3Igw@?{7t-vYt_9U<QW71_WVU;a0J__ED3ya#mEHJRfYqw^5_{tn!=XchHANEvk11o8&(_Z'
    'jT!pdUZ;PcMZhkRU|u_0Gvk8#X>W=V!T5lY^cZ1umZc&*f@(Zi(Yg7t-#z@r&JoxXAqk@=;5iSh5}dH`&KhjA4h+JeP2kN2i3Qzs'
    'B|>=70>yPxzdcu$qntwJVcd<E{f(kCWTHYG#F&v2(FP-(VJ)3dIoLlYLNJ;zaA*<kWFbN;LEQ%YbH9E5i6Xq2^wltig|7w&WlpF+'
    'G*c5YvcMIQ0FliKt<W7rZdXWjkvNCGTIIrW=A(4$+qd^sXVwG8?=qCw!)DUx%2;65+!0tYakOF|2_2IQ9=x^e42Msq%cnm{3VxVt'
    'JkD3Gi4evAp;6dH#Vvh5HUtft8l~ECBmyX5Z{-Oj$7IVgIsil%0B+U3fBq>s??tdAP-;m=E|$yd=$z%SN{Rq_a816bS40*L#q6ct'
    'DpU)-tIZ1n{kO+|%P2gcZ1{}97CgS#<HQrcg<}LH2G6i4_?9NxE$KvJAc}04LNEqR2$Wx}>b`sW^w;*Jl!fDD_iQzYob93#fs!B?'
    'OTkr@P?8tXiTTksK~pMIuvG~#@z`E+5=cPXx95K&d~fXr(ksb+oEeM7lnAy|?4+&W(Qw_uyNl6*Ad|mQ0f-mSczRDjnB&_B+T?s{'
    '2#R0Uhqt~}(P=zGIvD$eRqOz{(Y72|rt>mb4N(Qs=?~GBv(g&|3LE}VM!Xv1>Feh&FLAn$9u?hO8z#X7vL*5pnt8Y={NYD&W0wRi'
    'G!UV>HJE*D)({<LyZPwzMnYN0O<$zu;kWSnQVp!7@pD2qK!b|2+E)p4wFNIjOOLILB<+3oi${MRZ{5i`gDGf(X)Y{h_-bny&N&N-'
    'uR1`7>T53quBntcf|!oOYx9lix9RPpFOJ>b?Pd++Jg-KWGf8JO293~;{T0L7y6&e3EeQr_rKtJNNh8+;qV91qJvziXg<67x*O6Us'
    'Nbs1TD9*@dAc#akz{)Ca#gUI4P_*wFEQK~m3{lZvAkF3en2p5kijFB^Z<{tzFrh^XegvCyRUupFgOQNim@(+QPROCdjB4xULqC7M'
    'd-&<)ECO$z^YD2Kv4Yk*$c&EiD(sZ!&XRpRGICI_bC(s|WC;r7X4Y=LJ@-<_oR3g|(hj5d1_l}l2s?s?=GYs@x-#6i7t_%pfl10@'
    'Spj0I;}&F&E4QD0CWvEp#J0937N{~JOl|1AXhIzg<ZS~gK7?fLcCdf=n8%+`i9LGXF5L2S`|0(m3$f#oICEr}TOK+YwcrKV#M=@5'
    'eAsL1&|mws9Tu6;kP&UMq)IOAjw$|dzvfS`2tMZwl~~-BQ=Xa33OpcHQ<{+P1vl;;`3N-zASL}~+zylI{B?mUUOZZ!a`!5_&V=ma'
    '3n4qx|B=j4c-Wfz6#P`aS=1pr7Kys_lTXp+p5rfgGpO})wP`!Xfb73B+@*%Z8Co?uPc4YZtz;h=P_9yPsJ+Hig7C@>E#PoyvL@}V'
    ';=r+7lD+F;Ug73r|H?FeId4uC?fK7zmm?&HQUjq~I9h>)H?L6FU_IKLOBUcBW1?>S@(`R_LjIlcK97$V=jUgItZAt_CoUp7Q@S6n'
    'jR$M<tr4a)#_GG;1kHpM5_M|OPG`gszdzd3<JX7z@#(SOJ-kT4rsLpX%S6+|8Q_xI8zBzEIla<0h(0nR0Cp-1aQM`8To?wQ|2yWv'
    'G=92!X!jr2FPO>s!_tV_u&66&17VE}%>hNAI@(oV9$?v`6)m|8zX0QLEr=wLfWWz2w)4)yDIMxx4kFikB~Us*5HvjwV7iD@hks|+'
    '0)zop0t17ULb;M1QwxYtx7GLc{@HKN*uV=gKY*IvtT@)jWy*1Eo%m0O7i~qMYHW2d=cTwr6bWM@-}?&hAOHO2X|+!;+&{0)#HP3p'
    '{qKPO0iD{>I;H;|+m|TZiLW3h=S1eBDV0hHa`y6mW==6-`?&oc#F^<PBnoz7kFDPrdN4{X(TV!7@Y7(Fx&%?`2=*}}gsF}<k3H9U'
    'oKe;~m>^mcem2@dfA|e(gRcSd%ot9q!2(ARjaU#@ZnL$4L>eon?QTB$46>L73K7LX*hY|6o&Zw&PS{83png1yz@#KTV$TAOp`GGh'
    '35C7d1?xQQ{lj7J?_zLQN{ClpBDA<*gZP<7t^f!zePky>Bu*RnLVEzeboF5F(A)FdD9Yo|(a&2lfsq>*JnFX&pbv&Xh!m&Dp&Cdp'
    '4hu%2+t4le_Ttk5uQPVG%A7Lqpa1j{;6S|!6CaRCaIe5~4D6(}oI2EhW%yN6T494DZo-tcQ(Bn+#KS_p_2je8g-R)9IrS3c7I}J>'
    'wl8CfUqLe35QUHsZ~%jrY=!8WohqR){do~OpV!kJr1tLN^Viev0)z~GzPz?kh`2Bbhb>wHamU^fa@G;pqWF}Vh+hlx0q)GbC6Lq$'
    '2z~w{*{Nq5{MJNZH#2dtu(UD+HB}QUwmCieuL5B32;yArs252@ZQLAN^%v3R1+6|DX!V}2K^q9p%IVeqpF?s3j<JI)pdl6s=V5-W'
    'HlF~Ori~M%XyiR$A(wjMwUXhju^?a}!UlSU&{4{25iy#4eKxL1GH<JaI`SDkodS?n0pwMO#Q<&%@WRAREzE+kC{19u5sNX6h`Wr@'
    'c;~2-$sxFbKrYpqL4l@HdW;18y!GTWwP-4-z@h-d*fthPw1+mEsr|QH_fFO*JHkM~h$}id3TYE3TZF`i>nDG{gEQZKT2CMD9$$!2'
    'hl<pk3}liRp^^;vFDC9mLT%-ue2d3t2#R=Z(=NQuCT88R-b;HthUo3-!#S_`{Cx4-bj(6&$9ArEM1fZP5GIk9uM6K<ov_jC3=W!('
    'e9_SyU+?3M=fA~(Ks24;o&^YG^ALDLC?X{BLCi3bL9{$hWHd?-m~dbp>@~Bx)7^Of(>mV&?qO)po{x1t8lYw&{*?@GlZSlzvi4Tu'
    'smUx!KeAb%@VJ%^phN|6vDR-se>^_Dqzs{jg0_Tpj*WN#0}<2kscMw+I|wZSKfsR%5^{!#bh6-Ci-07t?0Sh$l<J*#wPi3s03PBG'
    '(kN}9S*iS_tyMRWO3h#ch+a8y06DhOmZG&w8|GJ|yq3o)`{~!0L68v2+Ld5LN8tVwGP8lOp&WE2Yc0|4j>wT&>zG^F$ADi4pTo5&'
    'y)7F0m*WIbM=l-agmVo{M_I8fvEOclwv-X2t<td~g4^quTD$JfJ4u6bx%2&Ifb)sdCDSoF)dlqU2A;x_=VfLb1{-V1c4f9e^oj5I'
    'GuR5`CB$*?IF2iqn(T6*Gh86@y~rmPX|YG`U}TpE`W@5P-iXnE>eNOGt8E>jAXJD5a?1UkulSbqBMpOmu{Ow8l_R8*fB<xCRWEoQ'
    '`4?r;rll0iY%@G(p-B3)>+0dJJ9;m<vnQueX;hrnRHZGUk+97*ODtj3Z2_MRhZs7_L5ujIjNA?Cb(m7^h=yyUy*m24Sct9i5f9#J'
    '3kagGBuS$+1vwl6A_irR*o7_h38$90gRE2t49a|&>w(T&WOq2nQTh5pRCYvJ>Np~Wl)W>`0o>Xx?lusEf-<P!<OM$=dKjI{q8qS6'
    '8AD6o8RqSzEvDLFrDG{;T$G5}a9Oxsb;_K*cGGx&D`o0eCs-uDK?QNkx$8;WP|(%C?!B%M7Zh#Aw!j0Lj`^K62)JxIa>|DV`2gkv'
    '(K`@4S#>{c>9A|1Ss}EqKjw0rt0ZBaG7#(ml3a#PLjs1NQb2$fkyE;kpTf}6!;r*-@&AB8DHdJje{Z0>U)TL>+M_d215k1r1Xu#n'
    'o$}|E*s8-dRtNtWIoPBl%(->wcCg6NS}p!}Kj<=)L{%#wDbY1)m$D$-S|X^PPZbTStxQbYRHi8=7!btVBoC2<KM{k!KhD|n3$M7s'
    'G+ukpd!(f7QdBK!4I#$!G6=HuV_v)?d|HFU_M#FnsgmCr;AJz}!-$be)2b{eO(jYcNRHEfmyX4WQ;T^5ekY)4K#CUIvBd|_U*p!r'
    'QTeG3`YQBVridWgw(_O0-@s~T?E^z-F<v+}Ai>)J`=;z<Qh{F(uaSARUY-=*E{?mvfdP{;iXq-W$fk-dvrdPg+*Sk^En3DjNIbc!'
    '&f}QR4QMp&dA(bj8wG_YXf9F3RWJ}+fip-k(K4bifw(?VZ$XE;Q-zTudDj*qm@i48W^8U=la=?woDD5N%_CE#s+LAf&nK!FbKh&B'
    'C80$qkCc>A!3#vCO=E{$c(cnj75z30I!}q^FV+wc;S0d$^~zSNlEQw0S#NY6{?YJ8s4h@0f~}IS2`s2=AgDy>YM7tf!+hNP1!ZE('
    'QI$p(=4Hx?gmQ)Y1zqfO0`_qtUqq*qbn0%ZEs6%Bt*n4+=htrTRg6*QF+dBHtCmx1-w7{)pA~-?_CTcVqNU!|D;B$0d;pe>8|FHa'
    'X@IW;m<yvag@7&!+GosC(+9+$;Bgdu!l?3d>O>vPQLdbmvdc>PFMPDQcE`J4o}S-2$b!mQ+#zlRLQsk@R*D#yyG&NITbK*PUJeT#'
    '-GmeZXH*F>|I)sT^v3{i$Y~{XL!yTA*ir_<iNma7=tlx2YlA$ntdwEh2h+z=;q}^fYTBQ^9^j>h@noa`>*CGz;!YWf1TQ5`J3c2m'
    'G}wUT1#I8?lsB*rJBiwRas^J=uT{<Ya7Xi=t+Mx2;x%)3-osHKoI3n<qHI_s>oKF%ruA{WQ(!(yiqUS!uGf_P;g?UxVejYm^kO?Y'
    '-itmHj=XBW90Ziu(ST5twQ7Me6C$z2j`%IOecdqOp|mKhc3-dTF~a}&y1stPT9l1+2Uk;NG|?7%h*F9=*N0Q#4xV{&9nB79P&y1W'
    'T8=RE+u<7eE_T5$?9=KzKq<D%!57jngR$I_CQK$PB~^!-Iv~*gWe|-k5I+{nL6ZD6=)K>@4?6W~NC0R%FReZIq4O=2GFH`hMW{|p'
    '3l0<{ZJ0^SYC%q5;Apwu8Q|;yqs%dtM>XIDzB`^vfP<>lt;7lACi=%HOFZ*|y_qhVI5&UBqOK9>ZH4Bc2(*d9$5&yt56T8E$C*r6'
    '&|9z>qRq4Hh&nmnsxPfDdTpk38|}4`zLrs*v&Es4bFijB=ux=l#d@2?Tazb9!#h+yuMFOT2@`Pu38LRrqDA@6+n=@#;re3`JN@XT'
    'w6(E5q)c{pKtXFn^8+wJwNC^!a5UnsO0nhFf{J;rpFOU2J9aE3<Dpp`6Qz;RKVG%>R>xJC4qVh>EX)Dx!puQ|yEa>zik`zYdLA{8'
    'C(GB-w$EZ;L@Q;PL+-m%ZI04?_kyt~Hx5Vh(dlp^b_e-0A_gX0LyjJN4k);|v}aVw(5x^-$bN|8D$ZEpFQI%YqZ3Ww`vMsXq8qFz'
    '31)rmQaYx&3Mih47nFb4^yToMJ=L=zWaU&S(R)ujRM<+;t++)wgc<Tr#Oa-Syw1EkBM%x&yC-OEbe3x5W@Cw^B`b1I`dcTR9;sU7'
    '+fg;eIDpyc{_U;@Ie)>0#Y5{e%9b}qZsO)kry<HCawYVZLpRbH2*rpLYw%ZAJ_lS`APOn^&H!(A;=SzvTebLWSQaK?;3id|pvD~L'
    'Xx;z~HrnTo*ozKWiIv(%RKD-ESG|n!CNV)N7=!oQ+XW;6As*e6#;%|-ajG<BnnZp+n3k@reK4C~&~*M8zc*25BPC{SIJpwzh%u|f'
    'OuASoaK93qWh##g3Wirf4#5hzBb*ufj2gyyzw_|(rW~_vSzfsn_);dXsU$Xsyp=PLs+9FvwCgX<qm4d7+ls1@JmvOXKKw=Wo_B8E'
    'cyXvIAU4{HoVy(bSrH>vS`?x%6LSDH7l|<ujE31`deCqOCkD04H9)@%b!-8i4Hi`cqB%I>LLw?<FfBDbuu1?-Fjb>W`RP$5{0<V?'
    '!@SG@?|6yjuDR%&H72glJ+(jII}<#>UxQbxTDQr&`BPS<evpR~D&|@`m7i$d!gpPB#EV0`qe%)YEa?$Ml`8ZG{8&27hl;}tnX9#7'
    'Ttmqz5kM(^O+sgZ_5r8w!s9^>PrWm~c^h;lC{66>UjXymF<7I14r}ks+N4!=?Ak4>;MHXyx2_gE21#c|y%to*825L3jo-#AWK54='
    'A!kC$s#Q}fgB?%X^BL@LAxrXXwbCd7PNY*fqC+4c9m(mp#=v6VT2h9t_onP=jH9mzFJy+iIt5{`(|7Gy@{JvVm{YApjn%YWhr;%-'
    'v5P_U{FfuJle^&#=vv$N@D(|nYJ!y#9YH|{`orOg4_P_ElP?&<8*e6nhpvXyHTRu|pQ#q1chm&KU-(l}SD>X5o}fk%NV4vs7K)n{'
    'Tn!$wWIS*iER+n2w%<Pdw5p&(%dJkYLPn#S9<Q*?*P>@J%+y%ug}uXfiOk5Z)g;Lxa<C@3)%{(6YEQrYcwNnLmgA=+`JoMS!i!FJ'
    'jYO-?x>UY3)(X&1R6s9McsO5C=M98L+ErMhn#$i9=BxrvMI*EC-jj9+AcLzRv^`2_1W5Vh4Yd1SL(zHLtWNvB%6jopx%(<ly*Z3('
    'i7&q;4&^5owWk7LERoFdd`wZ<C<L~KR$ysTs)QhZm5*?dPwHD|+2!`PXb|PXjq`_KFe)cTg(-_7nd0Clep-WTBWI3Ua8L-3fVFR7'
    'xYgF6ANXZG&X?bfp&FjY=QZCJ!Vqix3fg{!X2ewq6Ag)-;GAH%jwyP95p?37ehpzz(X?aW<4p6-8RIJek9$_;`Ro1pFh1|iL*TkN'
    'ZU8Zm)q97XlxUw2G-Ckp$R|XDwYd%^N~gnhF(4HF<_E2Zub)1izUm^M!6G8HX{hbXA%<7B8fHQ5)o?{^ZBQprSv22qun<-7xCI}*'
    '4<GHVk<>Wo^*gk+itg@e@5M(oSg+LqXoq=7smFwyB9jTvb=C$_4(1ij)mAj$d-`ed&x@jbSq!%w-FIN8M1Jp~(r5+flFuqRkdoD@'
    '$I>=;FG5Mx68ehv{O%y<66EtR0iglqRXMb6a7Uu6%EEMvpaVst0{mT*)&51*$&TvWkgGa8F>9vp4s-wb_?NGr&lA=%4%(LbbVzsR'
    'rv32+?7({R$f{=!A%KRhnB=|cwuiEL1|$pX{_Y^BzK<XO`gHf@oTn3Afd%#jO1qXYfvF7^CaZ~#<B!B4uX3zVwI>WOgvvs>R9(qh'
    ')muY-ZsRY+!H>tr(%Ha(m_bbP1wwnOf6I_3)J2Ahs3D9R;Hb4`Yk3lN8Dq}M2f9%EK?%P*j2eo5x%=|lx#WjQDp47?0kAhIAyleL'
    'yqHE)VROc+EN$sfUVRe?Y6&8;ET5`M<lh_VQ+puzKA+ul<p~W~Ee11ksH#gI#2O;-W_=u5W+)+vc&LgEY(b6ox^lOiP3!31_HHEN'
    '*2m}LXyN1enC}>>XB}7<oxM37%mDvQJ!57ifNw&<%pt0%v>^7X`f}+^bWWY-l+)4JyP=*LL?3mDpl*!3`%>-KGQp_m5Txu1${t^Z'
    '2RW}TA=S5J)0~P2mdO^HN8q?=3@^j%yLJCkif44_+4D9rBB<u@OB>~2e$7*LAuWM(HZrN0z~*nVQcx>le5<cqyEV?&FT1E=$ZH)Q'
    'B)?6pG?f&fRXT#*DCHU3S~|N$vo!?$9&@Y2tf9dzKD+rYWZlhgImS4)DO68$-_F5pcg1{w7}2^cs)^{vusXsOY0>OJKrFOjE7Px|'
    '@0mm_5}MKQ=kE@68sz*zyu8(?tgJHst&`&*69dQ$u|-+TS?9^X58o4%1EKx|y{ul<{^R?jeC4OF^-bH1$dss!&El=mZDSL+RWskF'
    'vg|xl<UvtX9r7Gi+>Lgvf=yN>O1Fmjbw7XnX+3^g;>E`(h@GK2%c<^IM@^4<TR>{mCks|y41qs3mawUk0QiQKgQ=KjBs^V)wtag3'
    'v2lIkO<0x6qd<GGy;v251kJZGASy5eQ(|I9$;gC&cs@!RoAP{n&uP4W_S<(K#7JU>D=<U?ek{O!21OIpBjo5jL^JlN4VpOAganr6'
    '#aZFdnH7Bhd>Cs#zkCfj=!maX?M*ZYE9x*oG=nO`iw+8K5Qhets1WTrtBs9Ae2KP|8xMa{sn02_7&Sl&s#e}<I&I7mnWwa0SKFHo'
    'aa>BF0(ns@Md?2(Z;D2T(!IWa_6e%aZ$2#qbTZ@66Tn-W#{i;DEjjh1g5y`ODh<RHq!meymQaSpE*WZe85z%b`{P9b*%fUaAR+~A'
    'apaW-#2HWzk~==fW(#c(QqSn*9Ot&$&IEP0q}{Ejzl|G?uO`Oo2wtu1ly2L3Q{;_pIs!qt5*@YCHq<a|DqUbJj<sS{3VCCIx8b4<'
    'B{l7WsF|uG+p8Dtw=|U+BVt8|0-v#k64@&!d^M1AMtDr>m;U?wW&U`SKAvCQbyXp#q+tafVAZaJg;1kX_4qPIrDanIItd^0wQirI'
    'y2g3!o!F}<pESZtQKdmA8xSR{p*GaXL4Yu3KT!5_pfI%y3xiO+1<!PRo0Vw<JK=+FKKhL^s9+-jawUf#&Z1OAH+7HNn>SU4Db!GX'
    'RaKPW_+2QxELQvM7}t6?!pn5$;<i2Z1iGotS8aU&jUX8AWDC&-!Z>-?fV>33O^pOuAP>ssmb-rLwW8@dbr=vX>xNE1jXEIt%FhDf'
    'vnrQ;wvwk>$zX_a=8mB2V5b|rM!50(mqON|dBi!UGFRbeQw_%8!%R3PH~<mtbsi;ofyIRSWy5+n^=agbuAY4KMtT1F=}cORHc*TX'
    'jaAwXO~}(V{@FP7oGUe|OxgQX)G7fFPGG6Jf1>)Ezg|$)@t?s3)t{vbyww%}1`t*8+)N#kD1hKpXHTbdN>7|c<~egvPp8JA*XwxJ'
    'Loe+C)Wr^HMf++SvZy%`a#va1JPq%MB)SHesYqZYI8luqBUCpd*REaX%;?YS2-%JB1E(|ZBd>xFRWqkeOm!Lh4hbc)sxXCMYmO34'
    'pi#RKk-&2G>~E^a6I)s<NO+y?@DIQyMTLkyVJd;I1o?ncGtz9isUHF4ib*pLiQI2I_>#E8Hqum^-CmeTSGrEhD{zIlJ@)7aRHH;+'
    'JWGd&aC2w=G7<ii$ltCWk1SkIcP~89TD8)Lq-g6)9lwb5*l;#b1EMQ)+~EOA*#^A;Gk}J8JptXIs@bb&UsoWD1EcvGfCUi*u%mhy'
    'G4pDe*r(K?QT#yM6m>Si<>AXy8U#W0W-~yK7l}FhJmIh$C9g+=AG?zJS)rj81S2ZWjM!b+#0RCXsgjTJRTrAOQg?1V_>xirq#I*X'
    '&&U?0$uUZlSM5_V8OT7UfT&%Lwkg_5M0paMjXG<Mx7zRZ@fXYsX#!=500?nd39|))H<g&IxSUlsshug+&0^eW3nZ^<+6tl!)46ud'
    'uV3!&U!&XfDp}vLsy=VKJr3ja3*De5-+3t0S`Bbv{id^`#PBAn<sFQ_z6}uvq5rYpKaRhAyn8&ypsjzGOysRg*Xd2d`6a=v`dK#g'
    'C2B%jRZ%t8NQ$g2e8P*02J^Zxz&9=Qq8h4lW^nVa&2xh#J9VJ)0p_6{S_HG2RAKH=#jI?7WVw#beXq6M8shTtNr|>)Chg|!qz1uE'
    'N>Trex!iP0ej#{|Q#(-zU(mK~PR!#<80Pry<KMJsQ7dVp*hom5TpjV<tggIxAFbu}y^9w5zJUOBcXz5k*JmWmIhi9V|I-r2oUiHl'
    '0f7g>mEwiz=SuJi2Cuj3XsJ>@K)LDg)#n|KhIQ}*HQq~Vf9j8}EYIWV?(>(^W|tb)eE1^L^8E9Wqs6iz^>zVHlNna}Ea)tdnI*U_'
    '*L^|5R0tjPRwa2+U!{|5+mEIx*H8bbtWT9Y{^9d)0)u1#KPASh;~C*V8zrc-h$CyGs~>5&HWL2*fNeB~33rGT1paK9FC$zeG<`g0'
    '9DURsA_#+HC>`<c1BIRT&YUg>@#-)V)KXj<LqM83E7_(-`l>Z>_UKPh__1#nL#eyox%cC#_t-I8+R22o_dX9*bMzP7Ta3bvyg<je'
    ')h`g85x^dcL+|Oj8WV2c{kk0B+@IsfLvQ!@r{`m7BlPT?S{o!d0)Q4~K#gZ@(%@!}Nx}KD6cbVcMA9Cbn(rZS(s!P(<$gYmP)pm^'
    '@`lI)Wq9#eoyDq^r0Pl452>qWA5}Y)eF1i=9raSXVZvs8KY}_9d^l<#j{zjVVlh@pLIqo@Quch1b$FO^+AI^j)czt>WnO?5*ljRN'
    '{iwmO8v|$+P7m)eE?%A}9dyQ$4Fn?!Fnz-+ORFBm<5=EGFy9Ja6Sav*Gz7O@!uyB6=J<XhhMfl4P0hWP(V3z;Q6jCC{iy>%qx0;n'
    'Ghq*StT?B^51M+8=1yQ-5GwcmK`z!om{1PIbkvpU<N~)IfT~I-F&yIIQ5&RFcyrWZHPv^h5C1sT?%W>aY)I}n?;2}>%x-ygpEtE@'
    '^Rzn=E2|=th8Z9|wt6Ra{9_Yz&=T`F6uEl*y!+)&#nG2D6<LVlIwUHC_C$FggLTlZjD)$$%2Bj%26UV^>M3Zo?#M2c@Pr#5@jA-I'
    'RKbvmGK8I684ef>YGk&YRh#wXOkTb!aX5u+7Jr*XWnENuimIC9jZt1I;g3NM=uqz-yG&CL3r)jR$^+UMjkY#He|t4Lhl9EaZ-Sw#'
    '(~vXBtYmPE^0x*#zC^X%x-Y0EAJo#v%D*g3%WG=~YlD(k^`_$a2!d3V(5yz61<f1VjX^GRRnLfchC(D~Bl>!;G>pM#bag(3&#FTY'
    'V3cfe$Kg{wYD2bKB_9G`zm)Co5B2$J{c^YddiEDp9uHHLP#l$+H6}Q$EHxE^sEGxx4ZjiF+e&6vc33R>bpFQPu(h{CY3t<pCf0nY'
    '@tK-RY~;KWJ+U+5)zWUqg3rpP_vsdmQdJC`ebwoog*f`(ALwG8h&q^70csEj1ye$!u5j!tS@lgXAUm8eW@iR`zG5D6h%%sQRXqNF'
    'px0vbHojb$xAxYC4yM&hKJn)2a=w`<MB(-es%h0dLibStOiGC`N^7YLk)d;(_k(>)M|<;8LN0BTJ5`w~nMi#GMuC2#EkV2vPG_UK'
    'i;C#1bsACXaik8;e&eGqv(hdGn#MWhAV8WSa%)(aIEv8{bOC79Hiw|3lLm|T*ke{YrP};dRn#53r8ftX#l0CwJ)hLpS3#^Jh17M('
    ';#D=Fv(T5yayDJ92VtnhJ0<U_i3l-Njo@w!q%^75V62>8n-G}ME5rs7M9sK*jyqMmIUVj-wVqXn4zCPsJG#m!Mw;_RFxKNQ-XDdj'
    '<~6P|LrnY}pihDIMlhzU{iRn{`JtqtheYh&P-X_EO{|IG2Cylq>0$s#7uHpaQm^5eNQ7yWgf<}!>U08nV%?yc`n{@HpXiCU1`S|O'
    '!``4PS4mC$@25|2)l*1|;*Uovd@8H;rOeDdm1+^IHho0MnskV=2z?~>)K;8I_oGg5{`P1Wp~p7<*}&bM+V80Mq<VB^l^2Y9h!fZm'
    'KXy4VVIp89i#;Jlruysr&B4wl2EY$B7632d6js@T$-^9>e^9-slwjkdwk_0TE+|TMuX~Z8nLggKf%7nzc03#MqGZ<z)OKa%)I!CU'
    'bGyj`j8e^fP5O}y%}!_th(NG4>PT{f)qJbxy_~Z$hiYMhlAygGIcm=wR2bT)G_Wc;O;ocan>;$E!#^7=y{RL3**8AsO>ytH4=MrV'
    '%tj%tD=E||v47g7oUn=j;{O0V+TxybD}~-1=c`qg$c*3kpr@~ABP%+8NxE3d>FTT1lUm(C%bHqtKqXrXYohY<RyLse&w_8lBV<!Q'
    '@)oZieJ;Sgd-&;%eGy&|UeL6O)RKajqa-D^wd&CQ6LqB`WnFI4RaG1dAtOjHq8`_cPq=t^QfuMHYo(-o7-Ed7(Nb7t4S3rUgEdM0'
    '`G`EqzV!r}iMa5PvoLS?<)za{tCn#**y?hwf`26@x})_a_n{jtfC^Cat&}m9R~DUMVqLxMbR$Y0{r|tg;%3HM(DhUqnwpXh!HX+N'
    'r{hYl3X0Mb=NvYuh%YN8T)RnDJ2f{@_jtYvA796Sc7+Bk+GvqYDz6(Ul%!;V>6&UD)ooozB#a)nIsp~SN2pn%Ci8d3kR=^#BH^w('
    'NA>UsMUO}O7^Nd^_=U^xK3%oOCuCyP*47=s5vFRF)vfG?P<b8WlDyh<v<^^}PzoM3lEL+%&JsDdp`vT$PZs{($C!74E~&S<4w3hY'
    'H<tP|$|)J}b;2r09)c8_Q%a=v1`_`dAcP5P_h4o;g(8&Vi^y~ILmOs5b~5?96Lzi^y$J3TaxFRxyVh+4D({{?F&{fbwY0CQ0yc9`'
    'rL8i@b4$6HIkl@>&36ZS)p)Tv6`vMm)ZozS^JP_z2#6Rp`k!3~d82fl7Yk{j{|%YPq*`6-^PLfHXs|KzbdZh$Dc#I|#C+7GZZ~bJ'
    'nntiJ8+EpiguO$P2jvEKU5^7}`~8v5I0B+B)PlDCdMUk0_~nI7D@qY}F(&OY0gKwQW0G_Umaa)qR{!|ke7)9PzFL4!M?ZID-O*S~'
    '9T_U1Rg@m9l7_67j4JJLaSnq03Pzno_~6<wp6?mj>p+)#2zX}SHtNC+eOZ}Jc@~&fZnN4nw3&v5=z^bMDhe8oXQ0MTcg3ymd5$>p'
    '>*w%hC_C_~so7G2Y^hMDmfS;7=Rdwf$(q?|!^jg9B>0aTNm|}m{qKx%<Zzy4pVFJ4463eGb8sG_RDz%;Ho6+?xX<fo4L5a3ppGZB'
    'v#+N03;lO1zP}E0IbnbXug82H{lU~#DkzzsZ_~vOy{fNcz^SrAWzr=FfQ2qtTk6I2JtH{keZE1!kuF_{M#PYUSp}OR_C#;y4vHO#'
    'g)xEp2qGju*sTWksvvDlX#bu8oQjHGKvTC1so9ol41h(Yc@VhN<;4YfwR&kN(NcxH=v*WXL@6g7{+aE&y&)pL4RXndaQHg$6Wc%*'
    'NFq#mEA0)pDMx~obP^Z<fD;xGLPXP@g7)!XE8mMT=WE9<#g}q>`c{8zRX{_Im6tM3Whgl>^>>~vsl}W_v_t|V>dB}v1B3b-ob_~B'
    '4t(f!VGOX}j{ba0!$2LjTDa$>>Ke7<w7FGv%&f}d1&xEceu7IF8$$hitAEAyLBNhsY%Tk#bTI<xRFmJmEGz8QTISgO#AD`CFFRf8'
    'RlATZRpaJ&MtRB2|AsSaX0Haqs~%SZD(|H!-5+a6cu$SR_r0}0KXq4~4lE@kgYHKw>xO7~GtQ;g=-vgD9%jqeApBKM9eH_pifWt?'
    'by3~xg6l>3SW(W&I>7-Tw&}+1(lOEn4^uyb<h5(SbBZo<A%rN0SbNi5Ns!7jMW6EnpR~(2<_y}k-f7zTJ&*x0FP0xyb6a;=E^Im<'
    'iGvctC{~aAkEH}I-2=6ccGZ}pu5D4pqWUAP_&r-b2DuDoO4e0d5!K`A<_?|u5`LS`8k94sB8NO+m{7FYr^*V|me=%3=;+@=vQxhP'
    'x3B5WBdV2>dbHl|5Sj{oN1LjjdutP5X$JPGtPhq-x9BAJW(s(#`>rvchq?G3-PEGic!)~jK5q{V2(mYiP*BZ>(hT8(E!pH$1u<1n'
    '5tAB_)>}mXG|;yZbkMN28(6M7nRfhssE11MI+=t;Z{67vMAZn)$W~Rt>ZVT=zRDZEGs3qzfpd(hMruwsyam4^F38FNqcsPwLK;YG'
    'gB<GGT1&h};KQ#*vPeEaB8D3qJm1Fo{BwK0T%OFbtMBJR<QsJ<hn%%x6CMFzBIDGh6s<ATJJsvJRGqYO7N<T^`+InHIo9QVCJYvR'
    'zdSh8)s6>~-BxY(I$XfCqqPTm*6o-vf78^~NI5dr?Qkl=y&mo1`R*re_FQ-=G^K7~3#Ka^K!<H4JqD6>ypp94bSWQSENR16qS70Y'
    'yhZIm-U@6lqg;j@V*b=!8Y3QALYUEUX$%B66ty%`c^q(7E%FS4(b0$KtKrq)foSn=l#gc~`0-p-^RdlOcc=cMhgrz#RK+rpjJ+~D'
    'DIhSEngTzI9@XKuuI!!4)=+98DqLMWgH_LW_Z}BMu1{a@o6aMLPHs=5%!IxH-n;;gutg|4_;WoPY;S|6Wh#}D)YYY<YfmU4Yt^I='
    'z5br#e!M({yZR(}W^yCzq9DsR1;^*4qL3;O0?eE>mhf!#nQGdOT2GSJYEga41OJ`DUN)VNp`tQ9CA+gz&j2Z=5sw{c^?l#URcrgG'
    '_;<SS#aL*32D&3!#D@0XC_cVc$-ge#)z`(<5*7i8M_Ln`P$Up&ZP`ZM#-!x-R!7XpY{(A`C`S<$-*juxY&X8{ychJn0hL&w_UUTJ'
    '*_4+xDhho&T@s}GS3@k)zPk0c0ZvWZt`MR=3BM)Wfb@@Y=GW0KtOT9bwD?Lt9e|OFVLfZ-l(^rt{S_BsMJ!vF+4Z8cy<L>kje>NS'
    'jQ*58d%E-d41fWH+Dc@Ctgi&=QDECk>6%0k<<F|RF{yY;*GB0+R$c1?_tjM{_VPPk615+in(2OoH9V}Rvp=b_u<M>-Z&YuxTOkNy'
    '#btUGg&y}X$E^DdnrOXRzV}*(&Z2=Ue`Az$yM!05P?RO3CZGj#&S)E@f~(CHa}|g?HdO~M1h`?+C4AT%?y9Pdr3RlD13Z8E?d8mR'
    '=_c2?pa&k1WP+8q+Jl<gHt45rdsPw}VHIMZG3jKT^GbJckfArPeL(d~x8xV>)P*rXAp$TkA2li4t3f#&)So$K!L`AxBuitq5^Ig_'
    'O75GG?cZ#XA5TAB*!XfzYGrUywH>NdLUu5_5FOx4w?NEp)OB3CBf#Vi4{botBFGiAAkRMV_s8~WLc-2{-;_mgzmBcT^U?mfago*L'
    'sFGr~(#A8KK$ojPMo{siwWFfXCNV~($~Psj*RG~H19d;=^=QXw%zb-5kaZolrh8P6Gr5|Aio4M-GiId$uMA5AaSZXr4Q1Nu{)A@H'
    'sk#d5+h@JWw)k-OpwCl_gO>}pbz+9D>_H_xN!RWWKH+4#N<HZY&{%gFuzAyT<jr^Jh+8)=>Sne6Zk(&+%fq^ehi!!{pcg;ZmFFk`'
    '2-Ix&?^L<sP-BQ;>`sNHgU8t;XJsFSwBH@%d|%($HN3i1^Uj!&ZlXQVFq+<GuvHD!pcg@1#w`)F>KdNhkJj9?E+>1xG0aQy(FuA{'
    'NieUWxlo0|?z-y7c?ihdbL#>Wb^5@Zr|I(d7Rt&+jVUY3Z*M&R@#*RDuR^N+Z)?0DmGWq+Q-c6v)F$vVr0Pku(LWsAyeiK-W63(%'
    'a5_+rI2G<1mMYQz_BbC~f2ow$r8`1h#JA4+Eq<a3Fk`(M`k7c7e`9qqBTExhL$4GXT@j-z_+0!C4t9K)g^nwel=!sZoVwo{XjJ2I'
    'C@Jz(*AjN4Qr>0Jak1eeR#{i;$TzsPK-Xj4y)*{FBZhVYjM3>H)GRGDJ8BL@hM0i`HEE-N508v<>N%cO6f)K2ZftX7tc%>-)8`P)'
    'o%&NbHF!-(sN&&8N!JW36)kUD#Xz@fBRUi+a0=~2d~E{pu?Kx?h*PD^DQ2nYIFB}~GI2me-PxFdPK-hu4M(3`zAmcjPnRfcrR}JT'
    'f`#YL_bBk@`qk$b>_>gnRn?!aW?d6R)KV)Pk1<6)lHj67wveN4)q)2v8ZGNQ%?euI4{}`U^%Ah~8eMYUmO6SyJF&8%1DRugqpBAS'
    'N<@9fje2UPGSqj-z|l%l@~gY?_^WEk^H;>7uCH6UjHsw;)WTr!|Dl1c=ypkqCe(?)vb5*X6c75`${t$#Tf@9z&gV6U^mw#|$b&L`'
    '!2A&^AYdin2TD|(fOXL!zoE+>EB{~~UHRj5M^CxmALj6uqiKllhbT6y)$JBT@XB<?@zjbw=%`T_sU(DfoTPzpCT$f7?-A4$>Ti#v'
    '?6Q~Zbmq~UOqFslHy1HBuj9+4vY6xZ+E9D8?3miFBzKGJpxanCT^{te2YYo)UEijoP{1@o?tsmui|dE(tY1o=@?GqJzaAaT(M9N9'
    'O<{F?26#Q+5A{;i`o<hqS1PY-P#&e{BB^XWDoa)U8zD`~P*fiXWxeZOJp-3PFhJB*A$nt!i<^bdljbA5i1}Z-AbBsf!GX*;G@@0`'
    ';BnKuuZ#(xR;3^p6)z00daQaRnf=ZfXMvG;Z6ze?w0A0dX*H!rb=^I(fDs8%{9PNVNiEh1epv#007Loa5Jwlow^qG%>;y8Y_M5d3'
    'bS1B|&8*YSW{#G*Dnf?0TBU+3+F=V><+Hio0L!akUacB4GR?P)=>VKD;xqs*lr`c;m~)0Q+W>4v9YU*p^l{S#DBi8Enf==%U08MS'
    'UJc9oaRa$m4s!wA(Ph;kK%tnBoOE=L?h;ij+EPUKQCD%gTY>a?uve>IIJ|30C>z=PG<orAg6>AKZtBjxu6uF~4y^|A`#Ahi^{cMg'
    'Qa7OYL%l1ZK2}OS@O0UGQX4i^@u+1%P)4z?$vlc?ni^%VMtDQl&Qh(~Z6)1tXUmOGTL0tg9iFouULh{1sJukHMJ~~ct}+t2-N;tm'
    'MWYJ>bo5QUVR>d%C-R`?B#`)<k#pbu3R){6x7|Ic#`zT7)JX?)fzUM2Misj%7y$>iF71rk#D|6oQ3*I09k?4+C#G(%E8YNt^Yz?k'
    'oKe%~1Yb*I;@1W&Py;G=)LzD@i}Z>Md5fb9*a$~VA<-(yZEwZS^W)E26=^+`3bhpbC5qH5TU9p*eeLIhBuE?G^F=6#PG1s%Bt*I0'
    '$Km<))8Ahxc^XMq=_;`>tBHDt7U7N6KmxM$Yt>@VXGh+)7k6{KgAPEG6riq!`j3qC@$O-+&+9>@YG)(xy2n*HVA|#0s<lDZYCEtR'
    'v7`}NR|_n)o>w<~b*@#DF}w;%bjx+VU1s@ux9WLAW2yU-LUWr@tpVmyci`5-tWi?dsHRM}>`q<MxhGPu6h)3Y*S;~*%}c}2ZmO#N'
    'qE@2nJE{ak1tTpGZxC9sR(I3tN<(c1X*AvI6&-9btJ~$R!A@6)UuJ;AII?aKRr-`cg5oX$ly&Mmq87Zmn9R(sD=&Dqo4PDR-M;;<'
    '$cpceq8-C_|B5*aj;rf4w2{hcBeP&N8Le1!8IW=*L*sLgs{?eqk`*rTbIBfibLP%X2u_wKO_(OZht(*$!o=!oa>Zw-bcEE@)RX`i'
    '6^N$x>{gGu6eH(p%?(Vud-}M3{keU8*1pMk!=yKFi;@;sUF$gewC(7rrM}(ja#i_1YIZW!_{TtfimGb@Q0h=XHwQWGsJ^t1b9F}x'
    'Gh{y0{Z-M?EX`ZeE^u7x3FuvlW=Y`1lPw^2^b75V|6DeOID>LPMB<w>ZtZcjyj+>B=mrg4TuyXT&jc0z+HC^sLG*#PLAJC#aRUr4'
    'hB#G%pX0PK!DI;uWP#e*)Y6f(1wIgiPI3&!#dkt7kO|7N1~%339-qv<-7u`Ty(dn~j`=#<6f>K;qM*yvSWlObl)A;8jw{@VI!c4r'
    'eob#kU{h2P2hIP^Am`2#r$t9TqrnA}&J{JMRb~!;sa}O>OcBAT_D2xxEpj$=M2U(I5*+@<hQKkz#Z0M7kXbByU~QG@Y!P)Gm8n};'
    '%9z`hK;Xx$F(q(@V2r7wa-abr_Z!6N7~!RL=_!D@qHLC|_D)GjQ@Yq7Z2$w0feI}3*DHSYvM?yf=+uUq>M8@uw%!O}@4IK5QjT@_'
    'IG825`YO;aCLdM~O2Jh|)S;v|7{k=@ZjOGdb-k-<rWDF87I?pY1x*;}m%H{7FP)OIygJe<;cu;C7B;%nQ&YsqI^A*U&@qDr0=)ue'
    '0zWKOO;*Q^uz!zTz4R2e%1!L*Cuh+0LCJOnSL;*R9{{B?1yq*nbX=5mMY2`%4s6crIPyCWKh4f@nMq@YCH3$HV0~uE{~mCNtT<+^'
    'E;T`Qs2#pjAN&Ok&&lR>Lz3M;{&Z}?>vZ#SuS8Trjl7&;iqw(CO5H;yRlVJ+lE0OX0D**Yx!xNTO0qoxlQZNSQ1X7H(}tOHZB<vC'
    'mKt|Te@FF*#EXqOn&6MD7Cc?GaKIx=rn~J;h8CcDZdlg&s@Y?l^S-{D>a&Q86)p1Al@(BPltnfoF~~Z#XVU4d#_*vuy~;|FmCN;p'
    'QC*I4F>6_!wsfSZ(>YyjwYxf7>XwF))Pz!1@Kz0^)dL7Rp^Y@ORCGQilW!pWyMaz0<O4Dpr<f`UtaV#B9r%~ik(8jD$B&D#<v(f%'
    'V?eg3TaMMZ6#Du%#(Aas1yoeR*Muf#U5~s~QEqT>fv#Usl^N=ng$#FUV3s<O8YoxBbQw4B@$w$v*VXZ=+D9g<33E4uUXO*VA{6^Q'
    'I&q^jt7?Rzy5-0M;`C}`nqdMr5c16+-)4<j^2#FOv3nbUSiNzjk}6JboQdiqj_uBBRFxCOh`c&evR=gH8{YGFpx0@$b45J?C7UsC'
    'o#!mw_^ZoHlm!IwZ&69LJ*o<%tChfv#^PCBQ1gDE^S#EG(^j1BgWRaCpr+N}l~?}&qhnb3B@2SU<Y``=1)T4?AMQBE%!(1~hEbnR'
    'l1_E=r=10Uv0z>{DoHMa#Jr>KIKd@d*Nrf$-!{j=`dS1>B${?S^&Y6i-yh;qy&7Hbwn0htupaZcA$#O(b(OceQqJ9!*`}g(Bj&8`'
    'ra4w<I`OQo8<=@H(CfMo+MO&^T{<VCt{lL*bdt{4>d*=gG66JJUlx?VQs309FgW!;zM;rZ!+iRBzSQ;<kCh9MD_qa(j*6}xg2*x#'
    'A}q2UHyx=3MbbSPHm0eq2CNd?@w2&b0|efV^39;<GP>_ut%Zx%{ttRZn{Q|c6>c@P3^drqB5IU^3|H=*?si^>QoO;6uSR;ExvukM'
    'qm9?C8?_KXJXqI>V$GniSBq|S%RsR?h+hGmwVV?Mvx8kXEc)E^=Nm|SUHu7597l3VHsz>`&^<=#m)dlxh0VxXD_U4o&C;qmMRy`A'
    ';^Vv1b_HoVJ;QJi*M%tJw7G*r5TCbK#+>dLJuZ|b{8y1q^<=`pTT%Pf^f$ib<LTJ<OqJDZvsc}as%F|?{ZQw`F;-H0MD_l$Dhgi#'
    'jH^KbLRYsA^cpaoZ)`NaAL-JGbYBcK4RXG8xoNFO!&9f*%~aT;4rkr6UR8Ip79qA8Ul0lxepPNoxy$jMAHP1mY@4u1EqnD$KQ1}U'
    'DO#P6>L%FEvP^BqXhTL>IM{UzFx}<SM3K6=ZviPIi3q;gO;;J6^#HOm_te~571=f#<tJ`kJJFPnh*Lp5a_*?;sC(jU(k|_ux4-9N'
    'l#6g`wd1QRnS)APS!>-@+{bAvAAZ<kN@83pO2A8%ai^Qe`AoRVEn#*w(yR69;x<h_=%t=%N1JNkTNk)SV!EnawQ=io11<&w$#NyD'
    '{*^_vrwoIuk>0k3J8fu0V*XZVIFyW9)Gl4JRzYs~oL9P?Lw{By<_00kXesBXGEAEVT5o*LyT)+mz^%;@?ZU%kB!-V0M;JAG-DlqY'
    'R%5^3l+_KH)QQnjE^Zz}Jw$G}(z~{BCyHnX{1e>VDi#GHb#&&`rFiSU7F}Y8{#X?&-wDzPMU6_69J#3#$_;{`ajwJZtP{1$Tk7^Y'
    'yVdX_E73(?Q@U~yijB@5-DCPtFlyRNi`uet>&D8cCFtYB{co2b7o|LOlP1WFEFa1l?l8iP*h3=10kcv*2s}hN0?7i&(L%T>pb<y;'
    'ol#Cb5ndv<i4KB*Jp(;UH@v6=iC3???R6ledxBI|-+I<9V-tre7EcRmwXtrTs9cY85mj~lqZ$bV-uO*JwjvbQarUTAcX%iaQuhja'
    'mOt02ykuCVZq@AO*8bUzvCau7FNf?$-ss+S<1+}h)|^$pkd8B91-h^Yx2=-IyiebKs{;yRg4c}g*4Mq{TMzXwCE6H*g4M(qnb!c)'
    'lI||VXCpyWc?m3-^2l{aJ=C6T0<7i+w4FO*oKt4JOL}TcG9NdOGjsKw!MA&?%D(Q<>Z(&<NKQN|`UniV7SGNb1mxTh;|-rS2R~E('
    '0o>N6W@j5XDv?<Q-6}^=<VifU90gr)(`fzCrl?PM!^YkWasiuB1?=hu)rDW%r>%=xf>kq6^vpmlGC`oH3f8y!i~*|&*(g?N{^mfh'
    '7ADJwekjc(u;ls=FcJ-l*qKW9^;vxhVNh8u+bV0Adxh(RX#C_xBzW6L<h%ulMRw%|)uK*IgOKIbCUW74V;F)Z6j&(~$OrstZHbgU'
    'ipA)CxuL0EPELM$dVJ|aYIJE8?gqX~9H62W@jea+XH=JnGEJ~Y#v8EAhp{%=n+iksf)#sn$}R^vtxHp-G#FdgU~QfH^jTHF={hE-'
    'J1HRvY9mKf(cPcYS<QK;S{T=F(cCwKydH4bErF2ZQAc~Urx8=)JC19hJVR(RZJ?(JL<SPTWLmS#)?Jvc-oXF2<6Ll?r5;$!m$w*C'
    'RMYJob;)BdekobGRQ#$J-BFIdF{5bNmY9dmuIG*2z_&wvBf9F3yp!VOA{JNY(Xwh!n1N)psaKP-u6{?_>e8htrmv%!o!VD~8>H=e'
    'pl|-;H;z-9y7~8fklLaoH@(6H+IHoEaAI9=k*7+`)RPja;6_Ti$L~Kd*5wqsrnV9AsG{EY>U=SylCEu3E=5m>MqO2l0xi(`DLmWV'
    '=CIVLZ{E=I&p$stefc=<p2pX^mklad3K6k+U8>o2cYKvgfnX}`P~}oI8AS5BM-Ffh8tK}H#VR3&ZcvXmgIqvDB3dEOV3_I&GEiKw'
    'Ghh>!#sAf7aTs0Irxt`*U_kMB-QQ*cB>UEe<n=&rB97WbRyCeYdteA^Rj!MOuykd_7~Olt2VrmaxX)hutH>6Jy^`ahsW*l@`1I*q'
    's{Qt|gU`g^kNB-G9<#+BQU>AFQY5LJJv5-}9tnHg<vw#Ngh8(^T&kX_xA5U=oU?FL3oP{>9m=SgO|4OqUB@+GiSQa#Yg!?0a#hSz'
    'G9M`$bcY%7<;E~ypj01!`r4l6^QonKoVo^nC{uUn@D$yyYXR|7G|%kt1)>5GVuOBO)iXL$gB=ZRy7pTjbPRE{r+A&Ngl$FD+?S@4'
    '><k8}OEF{sHz8zu%tY!gJDsCp_;S;M&k~4ko~XPu*FCpvJPG<>(PTRhX260rF>V}&*d`%$5KeTBw5~O}agC4@k&0@N!9u2aW45l&'
    '1+|CgCddd)%c?tH;M!4Ig|UrtTx{eHRlGXUNfl?uhPaC2Q*AeZ^rAuB`Q*{+5}b-V*tw2tdy5)KdsPd}HLVotgtiym1-q;5r?XH9'
    'Lj`SqcZ5rjaYNTh6y4gLbUTa^X>m#*4)qo=yQ)G2mO?e<Bj_%?(2t8em6Pdj*zec!@uidADYz}^hZb~yxzT-2&8yhD@I?!Dqr2{O'
    '*+zmQ4xOVqf<YkgslUcv@do#MDNZ<xCszR8puOk@E9M`0jNYjKCR{Tsql@TZ!kA9CfvRnLwQCHN)Yi4M-+%twbJH2r?i^7I?cZwA'
    'kXiLWl+oTw2|>w5h3KrdGP+nbE9`-s2=8TXB~ctr`%WAd6<MwFua5%ZtQ#|2Q&$k(bOw}H?F$DeAwnl99mX&_czD#c7PsX2(O7Ri'
    'jK_(pJu3_)psJ@0ECNE7SILKsHkEN<LWF?OpdEGTvZu5es1@Y~o6?rux7OiXbHMWk=bBy#GWzwdGp!no)zN52d#k~c7dZ||74^Dz'
    '0A|zSGC`=g+O3uN)*tY+A&kglC84H4mxQU^rQ~W+QXn&;R1zjnmma9$m;yX{Ts;+FWV$x!{Rjth{W#kFYsO(#aR&k!!yh}xmQpsX'
    '?7`8ug#T6~M!xi}raJB@sWqzOR2z{Saq6`-^XU_il2f^tAo@|Sf`VNWJ_glO!4Zh0;yhyqUJaU~W@C-eFr%ZJaN`r+v}ZnV#4MFO'
    'oZ6xe)rezEL|e>gC?Sjpp;jZ9DKBi(#QQvClkY<br1YI{IJzjGeIX6JK)qIVy9tVP4_9TK?r2bp{@O9%<W&vscY=_l<NB(u27=>;'
    'y}msEWBdHF_us89)<GB~sA4)ww6vErQQlUy;!~Hp$isLbejMRm(x<wj3J1J_;jd$yE~hy)f!f3BPDKQRPF<_6`7)?bT{x~*B8x!b'
    ')WJa|X)O{rru2%gWyrCV8$#uxC-e!()%H%O?rICElz0dROvI`#zeg;GH7dc4sHT5`u%V742wx&P)*ZjGxVe5=_m7{|#_I9Yr}prY'
    'gQGOztlpt&6lBz_P~9q&ce5pkqb(}SbU{~d?@`q+dwOpUr%`hA>j1afSDn<m3IKI=LodN%icz7mOA1YtggOJrX1A^?%Dd&M>s@s*'
    'Tk%R_kKa-V?s)O9AKoPr?jydd1&`Gf!_qNS*=1IhrmmrZnT`NeObED9A*EtFa4ua&HuKx(E2B$YzK%7~Jbi#7e7+d<McKpt5~5f2'
    '9seJ5Z^ENVa%2bo6{4{ONKCir_aV#<KmoN{f)r;!j<CQAi$a{;Nz^r!RaEr|`tNHm+&#iPJUlZiD>Hi<5H*z^pP%M-x!E()JZa_{'
    'P)s(G=1!ahncx#iJpg6Rq!Rf+CjUYT3XnEZ9^mDm>&N&1zP$V4=IvHHJnf&xb2aoAQl{ZQG6*h39f%diJQ6@il#c;*kS4OaX^#a&'
    '?n(wZqBVL$?Ip_dXg~a27N^x}1a1Fd#f-8?enO_O@LCUR1bm)Sw0DbzN~Z;B3|ixclGp`WbP%Tj-y+dqn5N~nFnTys;1)tzXFSS7'
    'XIp@jL6Q++=0wc~w{s?DZ^^hIg;z&1i$)+Fxb>?4d{|lC-QMJhlatUu$krI(uwK1TbTx+vWX+X$vqe!}66{25!3rf%-AsBp92CJZ'
    '9#g_(Vqi+4>f@F#6QPulhTxF`xR5|4V@ngiMA#sSMA{?L6P8FC3G##@89vMd#`-TWV}dxzfMggbgQQp)I3?&5=}wY-2WBenKk(h)'
    'kf4JA2#8I%i98;HgGWxohhf^?xOA*2^+*cnh)VMsh;Kx_b3n;ngvkmTWI<6BGTuidqahI(r$Um-vb-2R#FmenH8z@)TxgD4w7ZRD'
    'E(0)sMpmB;quN5N=t>~<n@#{VU_FdbIxfHJK{x#;jFfDirEMa?Js^hO&v8YCX75qx92&JFS{=w#pCur46i~0BDB?<Lh3A)vPI$U|'
    'j6_6;5uv$DlKiCjDR_&BX|KqyMbz1f5R?Uo2*mj%86Bh@A$|+Fie#?I^AOXU8>C+$%=Z25K!-jLA3p8HUJcRHR^$Lt?qqgK;JaA_'
    'rLPc|K*pIY@>TJQJbKjPf)ANYXasG@=1|U~P47SaTu6*AM_dDOM>5k^qDM)L3pFZc+>kA_4l!52EhQt0nB~0C`2<>*G|DnJUT3K4'
    'p!8NM(IUBG@~F8Dm#{*4bfo?Yq$m-qCvHN#ct)uvDDbEOG6H*mWnkPrSn}w(i02u)n*pWiNqG1{;cUiLj2@919z|9LGO{D$iGh|I'
    'w59pM0#FT6oW?4C71)0PkH)kYaN3L;Mlc*}mPnc`XNOuDWa}(;A!eqD#x2PiIL7U;G?%~N=8(+1rQy=Uaw+SE=-ZKuePQTi9I3A)'
    ')S|J7_8P~q1;>pFLUmjase^1tH`0!W0OWw~P=yuH+z^%`@vK6pOa`Fa0>6l(ph7R|zG>j^q42WuD8A)TJDEr~;89ET2Ke~?^QXgd'
    '80oO_t3ix_2SmN{t?DKqF$I!%twO{v5=pnB#-v-&oh7YC(VemlH{QYOaxukIQf~w-Hz{Bcfg~<z$MrCH(l1k598md)LS`o<@m7Hc'
    '5&+wfhC`=Fieke-&%^!O=i$xGdNZ*I0EeV<G9dISXVQ)$(3MEY0c3{muRu(>Q+k2ZpG<*qM%e(r<-j3?n#F%KL#B1*s}vAuhrsM5'
    '4#4>&A_NOUWEtRsCQ^B6NyIQDEcvjYb}%WvWFw%|v+0iVZuoHf)B9r5Yf?2W_GU#HsfEbfJ0z_lo{D4xic4*0>4^OhZy@uDSo%C7'
    '^h|56{hx;UJbWxejEj~C!x@m9PiG;BzX)e75z2(($8;Y_bw-HHOk0cKA0pJ~Ntjz?=M0@8_63k?GAiXK()v*J1;rG>n*o@rwBABi'
    '5XwZN6WN-=TKYb~aR9`ghNufdQ(>QrlOw7O2(pC9J_3RuiDJ4EbUK1A3MzF4lGH?m4oK?r5cQ1QP+~Y_i(Pg9X88GskBCwKxC;al'
    'y_RG>im{AJJGy;Hj1xYrmM)VLq+tMxhQwN&JR)+{GJvlIQkUG=O3`MRr0U59C5X*P%OGo42~zKXc1|h`X&rzvw1zGy$q5vqKr*wo'
    'tDeSjlyOnMp{X)TO}SgS;1#K;WMq&nLrR?oR1Jz>uO0}%Y6V}w>j7D*bWRgZ1HkkXz^)sT+Chw&)<M%lW+|X!NP+Py$;b_lbVOu_'
    '-5?1@;{6LMRRP4Etk?jUJw-c=GL+phnBM0Ap=|)j;*{GEWXMnv3*PuvJx(JaIm1MX)FOx=q(IK{ioAi**(J7gJHLNB+>}jH5zu<5'
    'BRL^>4~2LoYRHQPxhbfe497DnXTZw9Q?vu%SOj(~4cQ)ehDRQD-4bP1#z-Poz>PzS^b9}jf?yY`MjApH&|6#(=%5r$9Obc=t?0Gp'
    'k5Q))$X<Vcl&uGXGoIz7BMX&8xRwYQCuvXTjY-p1AUT~>a~Vm~1zyRBx+%anBAu(@zh#skmv_rYE*$|wEu>fx2_j8Ey&U@e<fM}b'
    '#T+MOS^=14MSv!$OM@Qc3VnPaRvB8V$^&J$T@K(Ndw4*oBF=gu!$;6cNYB=E-l)`VHsB}PMhV<JAmnV;H2exQt*K${J7{$()0<<I'
    '*4fy&VTb__UeG@VQknu8b_%8=Di_P3C2=Z1JQ~sp6<$=3Zj2H+=Rpci$qx*Hg7k5cuV8hW?g%MD#4HxnU?m-QMhPFf)ez1)c$gEw'
    '0-PYBp?)IT|2zga_fHa7;!Q~b8cpcQkr<-?NCYD3pDaC3q95u1ngsMna+)-y8BkmZUn2dJEUEKQJ8;M`&<|S)g!jek7Q~2hi<Z_C'
    '5D~dLZAn}$@TlUNlT;?n0^yMZDM=HF-gN;?gTSNJ-16jO#FJ>Dy+JIE)&LTkk(uN-$BQ5?1(58h5brR|6OtIo5~ppL5lJwh7`bh<'
    '*>;?yF~MB%c#8(esv;Rbjmr$QGSb$G(5DrJ(j_pW5Rapcad>DSM>9n-!W*u943o+$=fcDpbc416cGzl019S<4VElzNX_P;v3rbov'
    'T_z=$#f+%QDT(*EFh_}uzqR3;$5<bRAE5*0mm9h+7PZ;6M_|o711X<2Z2-PMf<^+Fg(QnecoX#y^C6XV^92(1lMT|`BQ{LRTlnGa'
    '@`;4-r=d8VklZ-{xxx%$Mk)#E<AAkCSZqK6l$FGc6bObPt2V6DOsbMu3=kTIW(%35A!bf2*RQDK6G?ayPeY9gfq=Du5K|&7RH?Ff'
    'FDIpit{s9_G?4YoIyZ)4a%-KzIg02cjh|E)vcafl0MaaCtCld)9s-F?E2J+12w(!>`(lYMH0hf7H{!Lg2dh{dZPP6MOiC6BmJO>O'
    ')#?D3=@2gj*#)536)7G-gCg1L$o#QDRUu2Hk!m{>`<B~zvU4N+SK|zSEN~u?9jg~oDe+7-!x>JKAsLO*Eo4Cv`Jvk55IrgF0B&tJ'
    'uO5t<xxfG>q6PA<m`DSbVuq)hE+h~p18Mt+=kUV@HitBNhm>zi3<4fj+fdwTq{_-A)0LzdDIll_w36CJS5ngoV6T&iLSPzXkx)dH'
    '(;}?FGQ}tr(c9>!#`3%#E5BFGP6|jjIxD2+lNvy4g9D2wok)5n^J$=&kdcigdPFh<cqWofK#JtWP=yXi3j*j{B)&c1S(tdE0mc|9'
    '&@-yt45Zo)c)yDC<jjoHBgAxx@>e>XrP;6pCBMkIHNZtVpbicFKO)fqd4hP^0d7j9ftFd!FnP(K-9rA63r06s3r9!QY!k!BFKY-A'
    'buUm=+W|z>2B%QAT+aZ++MpXrs~S*(Wih1m7+`=IA_~%Kac{0iAj|yb-%GW4vf~!Kp-a>oL)g{~e@##*UmJ;oP1LEfi2t{U`Jds2'
    '7D$jIn{Ofo`#i*l4alwl2mp@&(429`%%%+^7buWQY9RZEWkdkHw$ql;fI3KCuSkthWD7PL8u0L${)$o}3Dkx3Sh{p-9#C`^4}=rZ'
    'Dw%hvL@zX%kUBsECtaMFiiRgDNZ(F<+Eq)`P#9+<HrWYv1r1(dL!>DNRFD8v`82MGu$@t6J%ZcNaiF9z!2O$^Z{GdzW|@E7`36a8'
    'VDpo_BdI|qKG8hz&q(K{RggvmH0$6zYHClL^8%P|5T7mvH_nY#Sy1B7m~q;n6eZsO6$x%js{kPVLe@2EReE5S&yMU$V#Y*k0~shl'
    'w5B^uvM{Rl08Rk=+uPBH_c!l8?U5PQL9#-}i*%|`1M$v`{6lz-NfP6UDgY))&ah!o^oXow@9>n~Zro|W-PHrkr4fn83otiS1hkU`'
    'd?^%4D3*wYCp}zmw71~KlU@LDWimpAZO{HRQ04M5q$;l?DS!smA(6wYeN^Kjqtn1DB=d>b|0IC(6+Dq74LKqUXkLJE*_hzx!8YEw'
    '!Di+0Ciss?P6z<wqnr(iE@)_ERxS~cPr{L=5d~huQQb#t;E15m??OgLBkjw0WXjUAiYT@S3L}{^k@i3=FOWJJ0|K~-%?Pz|WTG0B'
    '`-M6H7+;IJT*QZGH!R&9BpdL}`2I_=`@Q!h->sC!tSdx0YO-rok{!jWVnlEv4U6z8J<;7=xAMGBu5<<G*d68LXA;GqKmGLnBOU^>'
    'h#XPH)Q~!abRuGE@Vj}u$&ul@kODtWKuC&Y_zO)e19YKL0|*{*YZ?oxjCK3z<1)P6Z!Qrl?fp!Gew_^9%bi$&m>jI8n-f+Ez<&e_'
    '3$oY)spb)}@c^D8)44ZDvCn*z0DX_BzeC#VN;bs=++4Q^Je`uA762|pHUX-!OJI=#^eG}HdRQ9$DEEH*yAhQaO0{ixNdUD#R{{8q'
    'UPo{VCCGq+&V?G@3o1Y0eTUe$S!OeALGM75XdTPPAnDnm0G6aegT(Xa!Q+jGglr%NM^^<E`lLWH6i?enHia6<GMJE2YLGs@Ju;CJ'
    'FIiIec`(xW_WF?lC0j{FA^i>kWq2+nmN`X0ZB7VmCMzN!?*~yjcvD7^rigO5WNWOw`-w3wo*hzUN##5uE1`vHBBF^@Evt#sB0XU;'
    '2s{h{VL_zU+Bi;d4Z!Rj7nIUidyMY(cRPT39(%~e2m{_X2BI#g0yABG2aG&o+bHF|<-$xrLQ(TVJ29i~1MMtvD1kJ<sd-T8jyGl+'
    '8GwYMNk5A4mT2J0%+N-V`WN8H^Tq>ag7l~jDMibXcpWJOWbYW?C&Yccib^ahpOV@{dYVAg45=>zi4m}Z5xH5xkjhJT$@Z3rI5-mq'
    'X8^7SL)`V)1cu9gFGLWoZ%Wn0btG$f9^gBO2%k{v0Ax;5)WeAMJ=6qr^NMF<V)7dT`%0z}Frq9965c=F#|6%?dHMLm+naZ#Aol10'
    'o(R8bSWsn65qU;LgP{BwaV*j<W<-jtkYmJJ@E#se=m-Tx?xLAy(0^Y(zAuz27d#Flp9LVd6ObB)h_Y9t<ddpDlfmi`F^jB6Il*fZ'
    'NP;4J*i7=Slgy(YV+pdVPy*U*{sN*LWl_62n3+U~8@I=IJOrW!`wYix1Pa=0qsE)9X&e{(Sg;@xftKRJq|A*(Y1X4kCQ<7k1j<~G'
    '6QH-(iI}8aE$)c-q}{-Ch7v`~x>bK}d@|KQHUH8IvERf5^<;4nTg1L_ibPrfxFkT_XkYO>A&Bw#kqmByoNv-lf@;i&YNWHNm+r!V'
    'oQ#$9Y*H*V(ot7Iv>}1NiAuSP3n+IDy}+y!s`3i!fO;~bs7&Z7ZMVOxufPHnVgNdfo=!-w26aR63_Vy8@y19>y3>wKS0@l1Atmi0'
    'xG9+~wC8<}Qj5)cHzn*!#CI9mL`Z1sQ8jNy?1Ws&#BhL~BgIb383ETM5H=uVO|t-8+P#B*{;<UaF;cM_#Z3(oKoOtjNw=Y{9BE64'
    'iJw<$A~TcB4%7jQD1AuE9ns82wTo{20sD}=n9*^1fW#nMWF!T6ohAea(3<=T_#)I~8YKvkq=P^`nuP=r*_sG4lzuDJ*cYz3?hx5;'
    'O!9$U4)716klcpE>=l469E$2{(&g6`z(YWX1^|Iy$1pnRUaQ}rZyzw)?T5m@h6G`yfec7JAw-%i<&h{|52Oww<es+G!`_n!gD?n?'
    'nt+%)Ap)*{cpEl7TNP=Avn3&lqON{&s1IlbX&wXd6a%H6{zMij(dMk^+LIzna({*eC`i+beU`NYd6VW%m*GM%kVM6Ei(OWWM^}=t'
    'UYh6vvV>557g6S(Hi3?LqD?lWP{5TbP;r@5*1jrnAeH}gv%)j>xezE)T2Tjz3^7NlN&t$E1Y#FZPc+<^BWQ9)ZYLQ#7B3i!*$|hY'
    'KJ|IoX~_S1Gnc~Bh+3!30`vjk*XhV+?}lj^R}I1-S%<oko}|1YV}C&szJ`J`k`)ymvcG>H-rUT&5cII2(*Xx8tSbPGX422`rs1HL'
    '(H=^Y79?wlQO_IhJTY@6XOyDU(_K3Xkol}~o|PpFjQ>ak<Pi5_=$eq-K9I<mU;vX1LWZGU0LiFG5hODXE*X;Vh$nAdKX(mT^d*E9'
    '&LsWj3E68i9iJ!Jw7^Q76+$SCL|M`as-SQYX>Ec81|m6-F>o<tuE<t=a&Z=<E0Ba4=15yL;B5;|^Z~iq)(n9TFiw_KcR7Rg5aBrF'
    '_iPTSrQs`_d(}S8056jwJzx|FTp=@7AiG$g0N+5uTf)*=fStM;i6Y-{(r@^efh>`=@l7;*GQXM|wTzP@h07u~!Z}iD%?kIAT><<J'
    '^bfP8-i%ryk{=4Tr<2@Vfu<32e3;6cxmcRLR}rNJ5ytF^#DS&1z&8SWBmiT?09iK@V~cvV$R&gQwc0Q@1b8t}3KVleE!M3AS+R6$'
    'wzmg0qfGBIpwgUM7O&{G;TdW4NG(x_Bmp=US$(aKzOZ2K@-lEk1T9cIMUgpegBk%`Zizk6|2+{8(TGHvNPm{V&jm&&OguFPKes}='
    'j8V1<=>B3xUITp8F%lb`Rs<CyIu`ZM0+|_fiB$+g@T8Q_;P6E7mS`e0N6%(HDrjMr_@wh=AX4>sPk={0EXI=JNLL~vqz3On6L2JH'
    'B9c^94eQo5l8We+6l=1{(n~{i;$cKS3Qct(gF)DFBE4mS?k>o1@fO8U$s#3%(@h)R7TtOYU_42djw3VYVPmDYEj5wQqdm5yD+HiB'
    '4k#&1CepY)YRuD!V$ASEt)yQJTMR@HK-6-ij5h9oy(Szn02*xAu^y2EG>)iUNtzj{xuXCC3<>;6ubYdUGzqg>h%VaMNTSNmKr5iD'
    'IaLUm=Yc*h)BBHeaiNerK*gD9LGs2x3<RO8C@e@fbCff#P6))bN%Yg589cRZxI-Iq$J(3{FQd03@1qcs9)m-IDxyy37(DW;0Eq$o'
    '4HpqEumC;@HZ~avv>>e_;)dxSH5X+cgvT~)u&1Q)AS8#bHL_fQnmPempJaR_o;TCv;X;e^5G=8U2w|v3x|gkpJI44l6tFLnzW`dJ'
    '8%SaWFv+B$D>ozXgG?#XSR9=Nk?vwpfdt8Dn`AH(S$*r;I&qJBfFFnb*Z~`W7%04+3ukNuS|Exoz?h;D6uek)-3B100jOh$$ib(*'
    'qN~<i_%cRu&jEyTA?wh?$poB5gyoTSDp7G0aIa)>2-Fa^c+ZXt09ujRD}}<d>2>!>K(aT+8Hu&T0|N;=gkI4hlNv?)VirG<`mN}S'
    'BO4y*qz*NQJjAFaLXZLFG4C3N9XjGN2cWE@gc0d5NUifD>A<uV%RoCWQ6I~pgf%fllB6r({oq-LL~EUmRUtqYd_cDYuWNB~K$Vu0'
    'h?W@tYz(T2jzmzNSg_ve5u!w=+7hn;CQcTWpU3Ov93^t!eOkU0FD<f^=xRlWmnrI<_$++%f;uLSP9uA=*A_hg5~l>hwZQ9NoMFC`'
    'JZ)H6U8Ij45iu{YWGNhq<)PdK9CUPpNDm8SE-hpn8l_j-CNdBua)`EA0}GwpwDCIiK$Yhib+U+Q(1lZ8(x8a%ho4zWxP?hABpofT'
    'n&bfuwIPnnh}hHM@D|g$x9g!eJ&@^4J5P)Yv9Xd&Tmj<<g<q`naeJ^q1uTy{vyv_t=^Dim@7`<lttOKSX0S*RK(g+7(*OsGU4k8H'
    '4_66O92pB9(0swr6`kn#7u1DA(uPKXXkxcS6Qo|#j^97phnp|Un>}}wB<Vb@GxDa0v^Lm!QkSN%4u~`WhGiJYu2_*(j?}GHFVbvC'
    '25?w3T1_)r71AR?@Rk%a1ngTfoDHd((r+N=GpSJqaC6>=NfI-G&j5vVkW6AxQ7m5b2{u}x3~Qt#o`f<M%Q66c3Q=<;`UYUmBDIRl'
    'W{Kj=8YP=i>5F8~AV{|+8GJnqkE#orc)dfp3ZQS2p%WsR;B*`dsu+mPE9VqmITu82qm&fhUndb}yzgK4Uur}aM8G8?*AI1m6%u>N'
    'P*wnACi0p|cOAzO)#v~=O6J#ye0bD5i3sl}f!iqR`xuO{Nx1|7Z5WhYN77@%AQh@|8bp*T7;kh<10vnciaJz)&nD^THn`)#Uvq`6'
    'sNz}eK)GT!Xp16))B#X45t>An%t+EkE1a`~T7rt^bZIQ=@6wsiFdNl;&FZ$1*m8zRlUSB0Q$h*`Y043y3~C`Aj&8hMwZ-e#WazqT'
    ')bFGdBimpLCIV*UwUA4LAnCfm{jAVdCX^R8K&KI?IR~EtDhd&cH7I{T#wfKJ__fEGbX`(!hKXd+)R@_<5al7R5fX#~aHO-YfPj<|'
    'DKEs5EzXO$H8JT)%@Z-ENuh?bgsdPrrvxbqy1!j}4G;l$X#}_fiarB3k)#YM2((oK!86lV%~um!B^e|~qBCMgGET%4NKLuyKb5)M'
    '!zM=3zTulSD={<ym`8=YS4AU`B^Xwitt8}TGM6nbJgFbF9+I*MlDp<&TkHfo3o}}xo(WhE9w@b>3PT4&LX=+N2HTV#D1rfa)=C4e'
    'mslAoYoz|zYx-s36X$pE73HK5t0_@P-Wif9$iEdtXQbDXbP)*7AOk>}m9)(<keNPj$fKkyn%MXNoAFTRC|{T@8(IU|jVu?kC+VmG'
    'euKhhD#9;8%Av3;Y3wK>46s%dRwVv~@ZdIZw;76UBW>CUC=pGBMv5ERxTM-Byn&HIy+%9CB-4g4OH$<UL=E9e*BCBw;^VEmosETj'
    '$32V#d1UJh&|f<E6)(Z?5z)A0=>QpnhBRJ_!I~(YMoHgcCL710?A2hdNdh4eTwix05c8tLmC_?U7H&9&f>>ll6Tc)gVI2GjRCy0@'
    '7Ge@^Q*jg-kyGm!u8M@RakK>(&!{%&MIyZwcsVE<JriZ4Otk`x!&WDJnJnEVP4qw%GAu~qbk~%S$Jya|;rSN^wOxp9;yIo6OaVs1'
    'Ap|Cn9)fD{sN@UyOn9Tnpf_>Dx@+H-Qu)rDu91}9J!F{3Y}N=w9JhiDBk7?CZ>H07fO0TSIDmEoSI!zYcsFlxzoZn5%3q5!9$*t-'
    'IFl(x(h%fh3=K#2J}D9op-n*iCfP$$0T`-q+<6fL3RYVL_+4MqT)LB=2~_-r6d}5Yq)8BG!EkOCQ7s5bB{re9auZ~&6Kiur0Cz@Q'
    '63Tsc$hZu1+?I$cZbAcGToZ4@BPoecV3!dy)f;ptA}iyDkQB&tCO+tZ%H_dvJKEq;y|d7<MW_by0%)@(LOv%$`%k*kOoXQgI3G~N'
    '3fT<+?j+qbC}8K9A&jPZ<7>)kva#s$=}`gBg)TP9dDQQfvl6tAsB}sSl&5pX{}(mN(2+dQBdR&iWOk`G8Lb(Moe^oy2B442N(_+{'
    '0Of#QLkg{gg9~U$#Bj(k1WK6$8uYqlmEqmUqWDaIEMS*q?-Q^<CBOq{n#$Ojgae|*P&0m56e{)1aN?5fF$yFhPY7C@VQvS-0dCnC'
    'MSn#IgC!M!1UuanI&&2A#`BY)HQ+G;8o@#f^l(5=sIRt=7KgyASzIWV#nH`<gKTh8FveBDtFbP?f+p1rA?S$U4@h%FIx)!~tHo?B'
    '9<@~%rV#~!%!P7U*EUV$rA8!94hsnj5@N*EM-m-+9tF~iRY1+Dfs_nGwhiFgmGn?RNc#kMoocoIeGG<=Nlc6EdlIyO%^^YJiQNN0'
    'd7Q~?LYTfpf+6)tin@iLCJ-STlv37oV6DUSd`AFdpe(5{#9lq|)GhC1B6=cSpZFG8NOmQnMm`y_n*l(OC^G5BX$27MnFqfvrCut4'
    '5?Z>U?n&E2;1_Xor^s%A@$cvgpzNh2lhDp2@3#a!ixd|xJV^jat>-c7!lLiTr5=sAu0UGBptnS6j|z>E^n272Ky@SsOgU1GS38e*'
    'zcK;%>L|~M?3%OCXSGH7D5#7EIY~@@M9$x$VW_Gt1`_G&v>4=V0)l|l3qZb1Rset;nC%>z{mt!%?SbL_^ge^V0+Dj@q(}H++3>1y'
    '^TrurMMTr<u#BYDtVpr|8lMM%5GggJvI>ESj97L3`Q6Q4(_vJb88pyQPBXMEJd|lf^h#3jkr+a@xCd?!&7QP=;UxgqkZ?#6Djs+G'
    '?Q%=n-1zzC&Ae^J5&+IKlg@^SH`-~k=Si0$`Dz!9f@ov_5hEhbCxM%RyH8XV0WwS6>FD-7+~2pq0|-#ALR#0Pm{4$ZcBt?Ton$-Y'
    '5v4Vjd4k)_h^@|Z0Gc<QtCfR9S;+wjTD0%i1Et$mvON}H#4HFLvZQag0ae{1f=%i20+3@xEZHjUKqAV`00p(%Qz(frx<uj5A*#iY'
    '?YsiLodhdc1Z2-5^3uRhjbZ#eNxJ}sh3sKc_h|d(6%x}f$U~tk-i$;S;q&dMcRLgU$u>99ep!jMq!kt2NK^x-JOWP-c;B=`W01rR'
    'QPBtCNin?&pfKOu4p4wC!}bZ(BcK8qVy=>ieprM=LW-VI?QMw2$d!}z&`-iDN6-e|Zdp!ha^3?&ASK-ldojnY1ervwZDO5bSw<ud'
    't|kg##}JL$5hXlH#gQ}VsfLVtJ+6a6!8JSa(pt9*a-wb~HhmX}M7)|;6l|rdt4NfQPNCfD76d4h44}WPNFdP2NA?=NSK1yF&f(z3'
    'N8k8&RnV4Zzl;)ih@@en+NHKcq;&Dg7$@#0=w7VwKNG16JXHdq$ynf+I+E7x@dp3P>W`-98$%kJBh!fV;3beMKnClKh*+Xj6d)xw'
    'Fp?Z1J<T|vKwCG#voZ{NqU~Z&s@t@OkDqQ(?B{h>XVX(kl*Hi?+Z9(!YG+vS2sM++M`q_VEmDz@N&Jt@0n)~XMFyByqc*s9hKZeR'
    'hyp?Lx}0(zgy!!x8DXSzk~V<~gmlAE9d;buFaT=QZ@3vK4=t1yB&$jD6wx6YVbt{?Tq+Pn0f?j|i7z$~WuPD?fEw^3Mf$6?cAO?e'
    'f;fjz?5$j5KsY=Q7*{e!Nz6`k^z|^;^@Z`02`J8aCE7yOAQJr}P-@AJUc6D;gDhzx8d@lxr~tY#N{RGUy6A_9tLp$K6#xOUsKA4R'
    '4s;3&(x*KwV_rr}8-&7Tc;OtaBg2U<<m6~5{A5H?u<!mib^iYSo7?aH^Z)v8*#7s!@Cj9bfA{%zD+>F&FTuTb2A1>ZFF*YF?(+}y'
    '+4tYw{xm4-w!mRJ8w<a^Kz6o`-V%cVRN5lpejw8v2I*`8@CXE#fKoRkF}CVkW5f)mfA|O5uTKvey?o22;L$l*H)N^Vh3+Tm>ttz3'
    'i6?vS5kX4&;iT=B2Lll25z+HBHM{_fv%(Z0tsXG?oB2PD>&yqAm3KgUK?o}uq{LFgG*26N5h?EgBUfgTTf(!Ef(Vz?WHll~cZUCI'
    '#NhAVK4@_Ij1N5H{ZF9&jRKTF1Uxa>Vu&&u=>~v7l0rMoNYfkfFa(4`Md~6c;dI+E@cZ#^c<F!8=;d2B1p~`Wj3Y5GMPxgmt|jmn'
    '5zt3BC`i1|qeukm4tPU+#>)*h6C#4_gFJ=#^V<&(ox=7ln*wQU>qu6+3>vioiG$+c?Up4(f3^y4F+3C^XBSb$WXuz}AkBq1liV)A'
    'ho3+F^!}aZQ+WU3)9;X7{N;DqXK<VTN$MCW$RB?$u7ux}B5%_TeUdub=AQffPn$&BXS))W8lw?>H6w6mMO;|eirJI)teggVv`76A'
    'h<iZJO{?-6ulF+w;9|BwtzO=&58ANuEk84)+R~VVCt*XIM6w^*R?e-%Xyc3^;>Ay^+<;*{V&pf;0U&xZz31h-{|%OL6xn_aE%NpH'
    'X83XA9_gj!yZ`(@zWZVQa09jKhquEtecn=ommf%T`|<tFyB~iTKK=+c^1~lCO>tvw-~E4d6vNNx;dg*0`rU`==66l1YSs0M$ky@Z'
    '&CREu|IeRpNHuwfPV(8@_vLwXEDVQCzxyBJdrALzgPTr0{tx-RrGE}@-q62E*#GJu@r&1avab=#`%n1HrC;6TUwQoVr;S(PpW%D;'
    '{da%c$k&~E*z$A!L40vrH&S4@x9|T>U;ZEB%esF5>t(*#S}gkb^8O>W{Cc^)`5ynXHF(}If59)lYz^@kRq0>-<2rnPvkBd|@6()>'
    'tOi^5v6TDXl!o8@`s3|~-+oX3yESPxLGdN*t!YSY>&??!N5i|hET{TUpw|!h&Iq>4>v@yc;pWXYVPo;xL-x^%?{%3bO^$Z!<FL)p'
    '>Z*Zu>*JIf9CqvDg1)KwcKp?^=iC2`_1*jydyW5dzWMF;X}~H!F6DG>Yz7M(O(=Ak|DKL4O~RSZB%D7car^20?XP}4yg3c-s=>m('
    'Ft6%KdEMCo@6a%9n~2rn@V2A%iC(t1Z#VzyAKxxSDSuyRPnFp=HOT9AhHW{wpU0!e^mork+LpQfJ&J9hp*v7i2a)|CzR2H{d4Bm`'
    'g4n{iedUj@@VD>tr}O@4x={)=m}W;bD0gBdp|H*49p+&tJ`bt$Z9JW{6tQ!1QmO~j4;k90ZtKfEeAy{Q%54v!1Rf*i>8rGjn0=Jn'
    '>}jhp`6W$WsXW(zAK#>lJa1FUJu90p`QE(E^kbM)bL58_=HrK29ou#}u-@naxvPmz(jPtlV`g1uyQcG!zfAobee~}K*1u2P8++P4'
    'L(EqYp+Ty=d;j5o{z`lizX7>#G+*ezZoG)v-)yWaeUX~n#`8aXzWr&N$M_-rwI%n`Vk*Wdhl5Mg^{l!|OY#*v+Gx47=<hwLpj%G6'
    '_%f|#qIumghD%mMMZaNZnq*vY*+iz&um17%|NCb*eE#_U;}CutKF+Wf++UZEH^Uo)h?Q4={e)^Dw>MKMjEG01KTPyzInfVZlXSoN'
    'bo+<t)vL7Ep`!Qk!_F*7JE&T|921WAxu->jZFK<ZkX*vn`{~VTKS?8e_UTDq(}&zIk5b#^AzcXDM$8>j(WDkrs}M@rT8U7~9Rhtx'
    ')0XP>fBn-x|CitY>GkVBzm^7)@+)Rbcglz~WksBhMgyG1R?Bv}{Z;oWDZLRnwU?QhjTP-wFLnB>s{g9eUrlqZN{hd^hRTHY?xYqg'
    'FYX%Y{SAvQEw*!$6iM)1;raFSQGLI!!BzJYKFTva`I;6bQ=|Oz--J+c7OD0Ns)FW&lL>a$;O^b$x8w5h)z7)tP~D<sZEjJz<ol}q'
    'zGyAPb1#|<+74IJB(NX5Xf112ye#^(Xszm_w#TB?v!ArqqG7msaQ*m`*7|hPvp6r>*xsV;^PjY>PMS_=U$p&(lXkizKD0Y;hdgh`'
    '^WSM5_`VuBR6`h8JxU+XPuVzry_t8f{+_$A4`=5(b~Pg-PK@2Azn&PoNq;pLLck;?`y>QRQmjv`-qhMPWA%m@TXinstR@+GrFa?D'
    '+JU8|rU5zbL}1iL1iPG=4nbk`v!A{pS?Y_`1SutsT`>O8jO7$Bd=Vtkb<F+5@7-=WB;%Wwm{)J@Zac_%xbDad+33E|X7WzC)3JDW'
    'J{Ho4j}051LTO2p^5z&Bb|32Lf^f$#zuhfe6XeO8vTUF29ugBOTX;B(D-*IY{E(fFlJ5f1TsxB(xPdppz{_q2A?k&!2gjN77ry>t'
    'nU62FO}5f7Pmer%M)GV!_Ke8xZMW&R?4-9GvsAj8gA(C9OTC#X6Ab9%u9ddd-;v0}CaW;FPy?GxvJHoM-tG1>88Q$JZxM%ghi(W|'
    'yq`X@raYA0PKkzklP^{xh5)z0!p0@Ra_EA$H*e5Buy)t#mw5zd>%jwSifyNnb?RHURQ{!RRi}!rC|QPer-5}Ey4xP=ZBlHeM9fX6'
    'o^={+uhST+PIcG`z-1rI-gGR&3CAg58_piXIdQRZj<u6Y;26ou?RIBpT6TbL?2;(<`davq{I^PW)GMb<+mZ%QHD?5?&Q4jUxs|z^'
    'R)qWidw4g$Ust>3;S&EdNU{FIAL;)<5b2-Zl6jA^+o*zoDj9TdrG544ZJMp#BtdZt!AUs0Nevs<-x#|YdwfeJ#^sEyZ#7wghg{9B'
    'N~^e+jaHA7O>W=R?!S*)`@ij*0IQOH;aVn}q>yuIvfBZfp>sf5<`YVqS7EdI@I5E#=t8ZXhn>y4P^++tol_JYQ^Li{9FUx;CpE}d'
    'md>ow8UK+Vvi&cJ2i89>pI*KF+drir+0HEe$@h;-nP=%`&*1U0vW~aSO^TOS@)5IBt~Zd1)$GhMZ(V!C^s&2M$98s`0_cr;#O#dc'
    '6yU}2`jCdJX_YqZ_$akk9%Eu1xc;o2SbM09X^=B(_acjs@3Nbg+WGIj=Zgv#i;Dkk3*`TA!-stDlfLeQy1vhzc=&#w=dp7`%$Rzq'
    'iFvb@VrtmLOIANNXKr@$`dD4g?I$5Mq`NshXyhPllKvldU9<XcKlf0p_z?|aYmlnw5AT-4mr)vB)xADivJ-rJw9s+7o~9C0nx@(Y'
    'Nd)wpjY9B*A`cP@$;Wo#i4Q7t9^iuB=I~|u>BsHx=r{Q%TAf|&`5k5(GT)z|9cMJ+H|dM;+g*@_v%<4;=U_Jd>Gmgd|Lf_^E}BAm'
    '0Lur?q;#;l+DdcuWtnxM&DBdMeEef_7>49BtDaTz2#)#h?>`b(Q;uAZvvur2N)Nu%kxb75!OP=pHx(5JEDlK)e9d_eHWh-X=HQRt'
    '1k?PcwD8G|o%^9wz8|qzB8d|6^scBO-bW2l^r#_<4mCvCp@t}HYB-(~qvX`!JL{86T3?j0dZyY;_dJBk&qcS}M)gin`TX){4y`})'
    'fb?dlJb#bc8aCb*(~ER6ezfe6n+%EEqPERZCu)m2eg!9qrlz)VBDQGSaZ1ZqjYC$;H9v}0clZ(MiYH<V*R&R$xR2JH@6no<9a{6I'
    'Lu=mmXe~%aYxmuy7<BW1J?4JgZnWROvmx{tPmF4lecKV4b?(SMH>Zwj+nzt(!q>p$t`ze&#+)1V>6m2aoPc|N&p}BcZRez@DPA9y'
    '6zPeWpH<ocYO$Teq9$fm>7{pCcFa%cx-zVov5p|~vx?1>>@vr6)6(qWjbpzzmNSdn8{QO}*n`qUSIRw<O6Y6up_o1z){)yd&*5QH'
    'QUt+HpG4bX-YlJwv@IifZh221^=@cTQ>FjkvS(P~L-i}Mt6E4}DlSokf#tt#T;s$0qVMIu_KXq$yKtSEsB@3{$?d1-fx~K%QuK@~'
    'YSLe?|4YPUaBbBdhe7`xRB5J;OH=D1_avG7w~AxR^OMz$BP+b|=}AOTG~UDf^Q0_pH1>eW=!y@c7;rn7_T9k@i>G<OXl8TT9%L(%'
    'Pn5`J&L70xIsAa`l3#6)@lvTTo%^z(F-bCcBEI5lPVDq(GbQic;qIX?woU&yzrFof=sibX9E&CL9Dd48Oi#7KcE<NMkAG4hkM{zJ'
    '5Do4IpVax~kUrt2;nVrSrR1?vr&tsjeKoIfY=TRaFwZkDC2D_xJRaGklBS+l49&bM@5NKjiwwMKUY5;E%X(h((9BDRXPTF($$Mtg'
    'GWDb6IGkVOrLy*!rsYo24UWyr+0(qvkEK$1^-S~fzOPxSz)S)odM1a@@notm{Zy=%?+&98c;r3lreb)6bkjn29*HC(9y&q3TKLB4'
    'Wx0gbQZ-Jvm|HCW>E_RJg8x*B%F2<+@qS1ptxTmIY&}$ibGKo3AFFBzUG*?+A5=Z)*nFU?9!%9k{5~tvM|-S&Q*8QHCnp!RI4e8P'
    'pp(q!V`HVR$_p{AFPz<3iPPNM{eaPYHzrgQ@rPp~@$3ghQP_^ZkD6+MY!6LaN7;~rsdh3t?te9h)|9OVBP9R8vJZ6rpz<%zhnqke'
    '5u4F1KW8Hi?_3?7=WRg<K;?)&?vEil4X4hBs`K<-vp+6~rgQDv9{A=MQ$0_pwg)RJ?=rm4v6=(vO8f&nq{M0n=c=oY4`kH?nGokm'
    'j`atTe?UBoKB$JM^b{H7#=1_tONxIPeq8=_LvL_@Uq0TfKfikWmp}gbui|xLYp?!g`-cpFdQUz5{=?1m`vUgz>eZkB_}}0B^S{1+'
    '`?t5RUQciS@RvXS_4lt|y&C@-@uwW&8$0fBYB9TRdjB0Vk!{$)7Ip?`g{<1enV_xcxr3=G@%XnNvIkUr|C`;s-D8fW{)*|^z721a'
    '4PWt<yavU>vF&0yV_1{NP^KqjERQdBqT}{3el9(Q&gPZ=^!9?r-sv~fptPRiTx1T-INJTObzXHQv#2~7(*`PM#$xM$(1}@2*4jq4'
    'R2Ry+D#T4+gknjveEG0UpO!ggLY;0xo}RP!>{T5h&LUAHVgvZ2#h8)~(yK*Tqp#Bh2IlWTn83b~x<`XUp~1jiLbo?;9-$YDM@^wo'
    '11cG8qrPXOD~*XXlM9uJvmLvo`{dVf>4fgw^E`Ja!X1f7k*NeOX-ij*BPWlbDZ6%FtBnhJPUj$SW@tE7$4w31o;7Euo+oe$RadTV'
    'Wj4y4k=M6!Zx07Cjh#Ip&XC8ltplj6uTI2bfy>n7p5)RwC)<ld1M!RFobBB^=R)^RIWLcG2p!L!S+i%)rRbiEJLSCV-6`i|d#Cu7'
    'adrB~*It<rI~=J@jU?>@uT1RvTD@TV<a$he&P?2kQ%t5lu8gl;;M1U+E92!e8Noh1GGFFiD%CqcU&n-h<@tCmy42@2^IW-}2i_JB'
    'yw|mToBe(J5=<L4P?liyw=BW*FOawLtCnDE%2<~@lC!Mh!qHe(;pDfhB3X3Tt8j;>)U6#hU|nVd-q+!%ERYrzU2F1gU5LI)=y*!<'
    'K4p8Xw!K>MB7!PUJv@KHhYY8T52nL~Z%Fw7&PKKLxSZ1;WH=>#c((HA&-#!-i}v#J-LE6kzjFDe?wmOtgQ=Z+acX?D!9IH?oeZbo'
    'bLN{1PPH^yrsjOlHy8XPqW0uDc!UM#$<Pfvq^7QqFocW9y`*I2Xpyg-Vst$pVTkQm+3<)$HhS1lnrb(FV979frcrLco^Og?pZ{uF'
    'rRpX(`NxwhLP@Ukc4Q6@sg_aFQT6llCxn&Mxns@CK{OZST4rzj^G~rhgOlSg4{yJLhn#{)rsx{Ug(#8^3yuEyc}VnZ_=~sR7}Pf`'
    'Klm<9)+y2zO}<EuG>cXx-abw76x&Uo`1`^(%a`&{<bz(WH61rBdFUiokD-U-;W6jc3RRH}>Q<hZ3w=^MHPYj8{&|YIO#0&kCX^yE'
    'FFb41<XS_tH1(WHN|-kNy=0)*lGBPda$E_kSR`?B)Xr1PTaZ7A?I(U&_$SWsPqwF@d2%cNgiKE)0v_@Co7b4Wn)p|>DLI7;i(Ah('
    'w-XAny#_$f$>9FWpa1&WC5&>Z|K+EjZ;_b@jrz6_V+xmSJ-SLnW(fqdc206!b4RhZ1X#AUh_xOY#eCvKN{Z((5tTdz@5^}13+Nt|'
    '99^0ma;cu@os>GRLgu$HMa2i!s=lertS-|}fsq$Ja3xLkV4h;-Zw|L6eZY{9g73t5xMj$*wIvXj`_ymuh`9WbVFcql*=}xerOz77'
    'X!>#l&y|Y~0FZn5;Ql2a{1OfdIYlC)DoE#gd?!by>|T=_-o)(t;Cd^Z%L-4rDf2X{b7)GK&Wee8uFw>P(3JDy%Qlj(>b5EG;p2rk'
    'tFtB<P?4v%>v{SJG+|F#^PZGZx(d0gE>0FTZC%hr|LvH~JT9CaE9DQzC|YNCmZnOxN5*Cn$EC=)7%5&W%pH#BP3Cw2%y9LkxZW#!'
    '`1v2ut8JqKWCkL!CwgK#l`cvZj9Gr=m|qziG#u(i`NT^mujV(W_f2XKTu9Id^#4)|d&3AzZ*8`$EmS^yX%4}QSdSevN%XF--$7AM'
    'KK#QWsZ^|e_`#oD2lUDF`0$k$rbo+KxXS6Bf_e?laZy?d224iV{F@z`N@>}>v|766ZGg2Z#<Zg7_<Frpc?rrMk|C<jW229A`Fu+='
    '1ct$PN7iyh|5~@aHfxLe;;oUl9xsj2bX<{s9P>;}<PvquGSPgG^LE%`10T6RUw+HZ$yV{4Qja^aYsY}SRF6hurcr%zgK!$vt_}bU'
    'I-Y4%`{xM&q>f|7Fi970#?JBj+d^F@0MpMlcgP<Z>xe?7>tsz@=-CKWrgBq0;X+M<oH`_fGH1zPB;)wecHZdyWO9%4VI1FZ1i1Tq'
    'Ra<srnP*o#8E#rVpj)kKQQn)Z-lAJ>KaZ7=6$2Bp#<;H<+HlwJG%F&Z*RO}quQLiL!|4C}@aA*21<fe~P7Um!EMo;j$DtqORC+qa'
    'xQ2rwjjNq!er+@t<DVzSl{&6tTs30}z{IFxmDfgWnGl}cIbovinbsz{o@s3=foeu|fs7;R@LxCRI9CtEq%ds?+X)JzqFT#=XE@Ht'
    '2BlcY#-1Y28lVwnQ(oHz(g-zq#vGQ=E=l|)(et0S3XT7g5XS%Tr?=|WtDHsrc1v-~t5RKi&1zXgC(>V34-JIcHYJ_E03UQ@4M%}o'
    '<fCUT^Q_GYJ;>%ipWuT`{&TnjoU`@>SETZv)fKRuB}Q<CA7@Pk|1)x&I45hg191vhRW>~@963#=NFVyZo&XazZKMurRVVC@=?f#a'
    'a7J7x9aQt6TNG=*k2oVUkT!pwi^^Z|t{jP@tFCO-6{&x9S0;Z|bw%V>eU(3QRafS;$z*4zud1%-tgpKARaeBJtB*#JzpA=&;d`n0'
    'XL%b!)fd?y^;c8wEL5G5T~L1}^JhHRQ+eV&^=Gks#(VRmb6@v1RK2P53WoAo)tfmlq4YLZz1h<#1)aW<)mP`c5JLW{8q%MRDa`3B'
    'RrTeWr*#i952-DvN_j6HnbI2f5bp89Z~0I*l+)T3Ub=k)o0X%d$qZFT4EIwEmtU_ho_Et_#{)Ho;XTAgI9X$rn<`{uY<#kLrd+oJ'
    'hxmYvRzOB57!?zuARafCR#~kI+H82fv?;@Qn^xy*Z(K|tnwCkH4FHztsgEFz|GwYZeStmL_HlHNp1zD_`bjIiORESq0QlzMlrlH@'
    'DxEHaXUI%{p1B{N<XnBLY^B&|YN`;R(<F0KdnI{ed}7+G@zrwLMffcnvW`Gws9!4P2((SR8l8Up@g_)c1^9)F_{lPyth~Ah7P^W#'
    '6nuQ5U5Te)amE^A9W2fQ@>D@%*mfhDN6(^|V3C7k6(7gG8Ok@Ck#26(EM;}nkKYYfc7qg)hvOGVqfY?F(U_jn9F40Eoa=)ztB^UJ'
    'I<pkAT&us9Z*7%&t@2-en~+U^jn!Y1)*DmC?EY7q|Ef<)eRQU_a1UM`T{r~Tv@DNi)*0(vMc>QHDa-aT`v+<XSJI7D43=jzjVx&>'
    'FPm(|d*s0mJ>0V@sfqbTvyL)t#F`FG3mW1ciIEOR3l1u}zj(#mrZ1J1+*-)~X?TDZJHXI)dt}4St~u%aw7m=Mz*>&L#V47FsiKJD'
    '&Ty!O!+`|e;A`}RWL}n5tDaQQQHQNkaXQ{Iw5!Tl@U^&#pYg?b@s!M+`fEc+_MvQVdOq}~7Y@jaCz)P2MP|rdfzcu!PRS`eTHdNr'
    '=dmKAajfbv8>p>?t1C;6v3du=K4qk@q%@%N_o4Vr{?Q%`l~ZT5Opf3yUy7Epxv9*?q2}IAmGS^|e2SyXpcU-7v<MOn(2Dx1mWGrU'
    'f3}IFopW<|Qlm)ATCbOyO~q6&P}TIUIFtY0qMwxfrHzfcnd=`($2|R$d$co;q+%Y+Re)H557m~}Nn!?}1y8zOe|lMC+){>W*M|e|'
    'iJFe&$H}jczh7&f1`np)FHqTy&?cc|tw6@7<$i$GI2ea|{2AMF#xYhQDoOiE_g~d24RZuilk4w?60HqTY86QJr2C;{xI!8)6H(@A'
    'xr5SezDj24O6!(8l%^|pNoh3t0Q`EAIhy;VkFvVQLsTk7mU#$(aUMxu>yT$-!<ETehI6*VM^rWzo{UhuX-w8a%eC&pK!Ua6=x|eT'
    'kJl(%o<_L94=)uyLJN486&o_E8*4UMDAdGhe0sbODQ667eJXHt6cEx{up)S4P>(+qmB*5zcPd(%PH;0d#bX)+@L?Z04Ke0vs4j76'
    '721HLJdITQ<O!!i%FO-6#I!aK`^<)GXjqLPk86kyjq)U#v8p4VL<3%=7?86!_vD2j`OM^Hxp3A$`3t7jUNywMH`(2``MNQ^XJJMu'
    'N@*&6w!XzOTphf{1)dI%ok^(R(s{rXwH>DL*L9lsK_b|FKQkZE(HxkI8H=P07^^_UiEj%j0uL|SV&JiO_}2;GK3gZuG%>1)RJvt#'
    '0;#=aiKR4<Za_fGk2F(TGYwCr$ul!!n`KgUOv16tC!aPZ@0sDR&9l2NA?m1WM!&3V3C2}SDmQlc%{1ak?v4l0#yWm&Bd%?nb5p??'
    'dQ&!PhxE)pc85Yd#|NQ<Z>%Y=q)t_jGdm&|&Pz#ULN89+SB9uOVi~exVmxz{{g6F+9NLyxpQvgs%zRS=V^ASJaEURmFhQ~&iey6P'
    '9aCfEB=FT;$5VKL$$vhD7wG)wQ+UDVtJSF0(#8>Jpvbgw1gJTF&2smj)f<iEx{*bVX)Eh}t}=2o>bUIBEc5(OYO<M{tPHK^T4$J<'
    'D;fjNOyktnR_WHMO@FnmQ(Naim)fbV5w23xE=tL`J7Yby)m_Jrt<x1atGA}gR?Gx%6Nk7ev8pYvxHON;12<VOd6QEOro$1>{fsu('
    'U>Y9RHOHkr?r`4eTDg#FKK$*}sILQ9D`X7%tOskXGg!^uy_}CHN)5Og%fv}>OPBLw$KmfoHP*nKxz3-UrVgsHwy{Mumbs;eYD`TG'
    ')p%a*1CJx4gOWDa!|B$phV{b}Yp%kj5r6Y=3GSpj?X2u=Evnhvv$alz-qs>Y=Xz_Mw&$%aOVOdXwT=t#<tm%`a%+dosa*GIj+*L}'
    '=NneY&lH81X*CxcW!1eKmE`*6MkP)CYNHZr1mCDKF;~M88rB`p`&rCGH)<*y<xfR8*r5K1l3DeGHIHJrqkztp12|uKmt6F>%coqr'
    'BaZp+wO4!O^b*tcT|R9;Ny&iP3wCvpBv`sa*__?Ne#8pAtkc}tA^Mc9{_cIj_sD;(OJq&#2dZ)ej9++@**zv-&(pnbvupBpd0p2<'
    'ki6;i7_-$)NrKp$<1uEH57n7u%vzIAS*}+`syAQ5x_rO*w)Re3%A=|-3w_mt!=$FlpknYm+Piomj4mMd$yPP@F#;cCj}iFfn!aEJ'
    'K7=zPD054d)~+}vg3t~|Fh2O)bUC-$#H=<e-Md|On@x6`bf`JJ?Jmvh2w1zXYJon1t6XhqP@=b`L7C2$2IU+1o^;8eMQ=+HRCa9X'
    '@?Zv%159+#u9Nwu1FuwAI|fm?r^!T<xrupsS1BKSH}h*_s4E<>0_-}l3I|`$g+kIScUB{I13kFvt>-AtqD#%6aiiA<Z>}zz>ufV*'
    '=3v3q%lyEaJX_{6K5$T%9eu(3Ixgj~<U?Ri#Yb#ly7E^(f{g6)=$=WS-s7Oipe=Rz*i09ZfjF%8=}HnZCq<5OyW%_uSgQ@a*e^w@'
    'qY_sJdyZeb?7v1f<zgVJOEW*JOEVwAX%}XG)R$&{)V+H1Iu{!{YGiF^QF`NrEx|uoTm$0M+M<eqe__8O-c843^4&={uF;pTcslS}'
    '?&0YO`0DWVT)O9ir^nFf%jN7s?D2F2hV49ky?CJd27)gBLm;)B<Aw}SbXSW^5o??|LU4=_ZAp+^2pKhe_RBXt>0Cpas}WLkE(bN8'
    '(s~b4q&C;Og6OZl_4m+UL+kG`B45_Z-(y6&tF^y}{%UGAU{GtQ6E|bTsf1ptnmaT9v=Q2!J{k5;axrIN#Oaf9|D-I;m`c902U#Ob'
    'sM-QMaNGDA_7-~@Gc?o6HT3o|!}rHVJKgKJGA+|fY57gO)1wH|sqT{HO@8-Atwa0f{0-#kavgEu<7r2h<}B0GEc;|`Hm%ey<_A@N'
    '9%XY-<!7<+T<kvzr!lAVm{RmkS&H*1ukDX7PPw$n-YFv@%$?<UY2%RJ&vaN)^}H_B<T`@ZNYz*eojQj`>iet%BTdgbFgZl5l_Vxd'
    'h_#Z$9OyF5HLfsa=(L}dJujI(1BvDmTe-~7Y3Ad2rek%z<WM8M>>g|5)9o33^yz(0T_d|rU25t$b&YJDx@B@*r>>FQsVjw<pH}5f'
    '*c3(yd7UH7D}&Hi;qDw^qoi(>hrP+|rp_}_hEi<=Kvo5mvd>PKsJ(O%L{?^?{qxV@RDmh5lQH$#F{n|aY9Mn~o6jignx?EVDa$k2'
    '9|-YjR7&iqitZNjO0inkkA()2SMGVGyXvB#nsb3A2A*nEU9-B{zW9h5fkq{9zVDG@{6HuF*44{3wT0*2qH{RaQA6G6bL|>NVOp8q'
    '7HQ=lu|+y5)mLPsQ_lahUNn6|Lgm|FYQQCJ*f!LNRn<0B0HzP#h74wPwG9^;RD09&(}_2|tEByjPS{n_p-(5_QFIb}7-7_8@2m`F'
    'bgZAgWzCRGe$RQvT_hE{w~I#B04bK;wj3vQwTniXN9-bTq;?mRg=};SR8}@f+vk?}v<=-2GW7--zCpIXLH1D_WG^--k(qI-dfQ^)'
    '`^Mz*y3fd|GD6RFj+#NF)N}Jn6IAz%PT+Kgu>upjywb$S@JcJ%G>=TgHf1Q>E}yoijErJttZ+Trwjx%)nDQ?YN>)mJuj2oxsrG8C'
    'DkIa_bZ4o<vFb3{u!VZ29Z%4p)YUW7j@9byrYW=4*RScRWUc|S&U2HMJt?$|tn8`O1}o@HZJ|e2);$8Vo_^(;t6%2f?ya_HtZ%C='
    'mY@6h{JYpK97-&$TR7C%*sJDk>|+Xt8bla%6d89$_-0K~KDP)y*T7;M<W5-rj**$G!Tk9KIsJ(04JL;zU6C2$mKd2SbwOs%Ton2)'
    'P2t(e%-LEQ)rZH|+2c_`s-aCh`G(<ju3KZA>sofs)i=QNQ}kWS&iTh!cFxx!W`^xUP&+@DYHf3bzGWYB-VhBEDxKHv?)9=8DGut;'
    'd3lrDFPl_Lo2T+E6CBc$w(+8RoLee4RGx?zZ6V3hluF;#Az8+!s&_4NyFrN5GYe6#x;`0yN(%Cf!+PB-E=Nu7j<RO!c+iwLk6|^4'
    'i#qe-y~D^Z>++;NW}TxY4GL@ZcFel|j=8oBOxZE_7^U8)1cXb?-TOjl?<z|3EVFHWT4q*wnGbbE!Y^!{Reh~EKQ7;~3=?{nCW>dj'
    'G|}})APCvz*Fm)2%DFT>##<R=6;c=E1v?6LEG2&d3p{c7nYJoqK$dNIsY08i{w;ShW3AIDeJeI3)#Su<gAUJr6>@Ca^{kA$nw4QW'
    'pHjJ}m0~JOv0xuSHcs}WSa61M+2=aZREfKs&-2ixm-j%P8&n=U2d9t_J5X&>oz9f#VnP%b0Zb-D#`^b6l91afm*Tu5cu`9YEpE+$'
    'Bb>PgLeVZ}m;cKKyiA`;!_k@c2lz6_C@aI0x$UEpN0RCO^gflw`fcW@ylM~<rb~Qx_0kwstYB{?Lo+Zrq>EuLY(Go@+GR?*^=Flz'
    'r-170;^0~T)MOhie{bT?nEEPn@Tz_#iwug%XSa{bEW~IlWMaOx85wbW{HQF(Eyce?c8L*{b`GiCo2nR87BLY|Wm6c_iaC8^c>Ff`'
    '`eoWMV)m8Z%oPXJ4`aupFT%Au<Eog)4W>ypxGkMu<ms6hu4uIUBwo-c(SAjv@sxFkGFA7)mf9S`b`d;aH}tggG%c!zokl^H*}Zx5'
    'HiwS2dGl7NmLu&={u&J}os$(>cDMmG)h4#*zX}I7h%~yzOuVNUHIh(M%DBxzX1fJ><b+On9wszQpfqJfv?rN|tx+3qS?W49`cp{L'
    'u&0EVxwxW6@~FHFJvZl1>UjB$)s>(7I?p8(c|$E{w7C5z{xo7}Mhxdr!Ev8=Sy~lk%DWF2F<RwEv8mo&eidEg5SSPMrX|&-aR}^9'
    'hLM&1`Wol|uzA7Lc}gi7&q$u5luV13_9F1~0pqALj=CEok^YlxXkF(o2gz~vsQK{0OB-7lrTZr)*N`V>YM6ePT^~br8YD*VnLWF2'
    '(#F%1LvquX&Ya`t_l?u{ZIyw2_GLakHpr5!HSp=U@R;eSrA#Mw?G=k?tNqlzahxV_>T2C86@KrmTS?2;JwArKbxvNeO38{~jj9M1'
    'CBTlQf8$U*`jM7y%mu+JbMJLy1dIA#e4}(lugdzTqgUnX+1sn@ro6a1xV`l$=M!o-p*%#D3UyqRs+mwhZhDGY0JNzdiibQ{ROVu&'
    '`Y4XC3&+o8x{gS0rm<-GlmjVMTZac~rOh?GF4C{9R=sL_)bte~H&&+@;H%^SYBM>7t4RE<Bt^0oQdDZDHf=={l{!~ZsaD$-=BCWp'
    'H83}&UuVv`LD>LTKfDFjoo9e%bQF&{A8E?@_!^E}Wu8^05qec7sVRjU4^KiSp@+I*b(CEyiTZSargwlb-gkgTwDsTe6ih;8zc@f6'
    '8|7{;Ev|QfrS4YNsbmWs`+x)VDUZ{lESKZ)inY)&7uaWI!CLpu)@XN_?%&APP`Imev>CDK>S%%3^zd7bnp|J;wY#rwlLgGtiL$~q'
    'WtoeB^)qE%1gw`GXam+uzg56`MOhaC>!rIYVBNY$v4)HXVK-c&2W#tA${sZ#`sM+8Ncmc2TbjOJ4*jtVqbg4xgLkt{bt-#Dbt(%8'
    'ps!e+sncne3iI2dLeya;(ba#%zI&Iq-Ljg;-+K9g<Z}<HTi5j&SkIT`#uo1XAu8*Vr{dcPbEe*)V%7e_ZN|sAC&*UKL#61M>$p2>'
    'qkXc&a$j{va>z{2qIL499{8;X?_{i0>`)m9Wj@MXsr;o?>!-7goUY?}LoKEdBJ)(Xk+Zc~xRw7pTNj9YdAMza3SWKO2*5c{W{bE`'
    '&wjeHjSx!Gw~btU!ufb{qS^Y|dcp0mZ@Wxh)@EV6TDn)KTD<kzy?R2s(4VaA@p3|@#oEnegJ6#HT-gt^(0H1uTK3}mt^Cv9o9|Db'
    '+<Si*<MX~NwSkILOKlWvdw`GM#|p}U;h<7eulk_{w9RR__z);w3*efEGmId+3r5I7J%gayxUbTW;<os=dF>HKz)0kqu4+i2Q4Kz*'
    '&0sd|i?7Y`0`>FBO>S}x0#5l+^=!sl>`{q|jG-#T;ah9W0>5F(3$=AFjb7(N_eZHVS2aQxmm)nV0F|bLOJIYq9~+K$^ZeUW3EtJH'
    'Er+6zMaDEwN9l!q;?--LS0C<W1R1S{2dwS0jFKObe(EFAd6EgnBNJ9iJf6!8Hq4ltciR?kzNZw6Vnaf1Jyb;GWbSP&D%Oi9EnmDj'
    'J<`0RsIE#lz*23jt2Pit9czkWgWGujxrByo3(HLxKBz>h@xnZdxrOJhyY;D;TONO6f(c=KFG~Lq&Wkc|5BW?#?6Z_2co#_n9H&YF'
    'J-|+=&Gn=`%B!6v#8m$`AG_`^DgjRiLJz3}6|CJ@*Y&Wdde;128s0(Nyd3n!8}<bo!U^#eJ{Gcc^d-x8Lb}eAIyI$Gmd~4eBQ4zt'
    'rMllMTLm&4K`hi%m&C|0yWg8b6>}nav?@8WH@SmNRfzFUq<EYC)@-@6rOoi_QQKw9@4oxCnEvWb70AO-Je{bMQCaCxmw{iZOFWgP'
    '8p|lMu`+_%W<L9H=OuRUKEEB8kFS0{aEj>nCB@<P&A;uAx}*2dm4XhaFkLC=gpd484!m|JQf?X#+PeKvNRDk)Di&6yif){IKckca'
    'UXGTJ5PKvWYbe~(ZK}kVCN590uC)lJX2(VFa;FI9J3b`YN*#orbIQpaO5X}qYO+i?t#=AlK5VXsM!)wRY3Wca>{41fnLO54($Y!A'
    '6|v>Pl$RsUovb5r7-l#%`JNbbGNG(ph(U*XW9Jz9OiWT&sW^eR1SSUk{NQ!OvW^ql43ioTa5I(cqrcb(NGm5(X8Ik{%1L)Zy0iJu'
    '>H+}I$*OelW;GS~PA3x(>Ivq~Wz3fo%$)<?OAB-75R1@8i8?^QT*KVCTpp}OTqqkC>ROrUh87YCx^85?Ehj^j+c)t6bItGVbt5Jx'
    '`5ggw?(cNw>(3`+=wG&f$ndB4)9~i^A8w}K&u?#TZ*Shed-dwifBf%n{`p^Dzx~_WSFfixfB4HE|N8sauU?IRjrbD`ZChxDhuY<M'
    't}lFrv5qS`LL6N#>{a+GmmsQ6o#lItvR=od-7mU!gkGFeDKhP%BG^R{>r^k$Rd6!D@EYonz>yz<uF8N`=cAiILmtKFl#xw1XZh(K'
    '<vSLo?l*hqg(D~v|HEuh;$K|GClFhcUdS?|SFTN~$^1mQ0_nDM^NSU`I^%PL&`sP+dBHR|1f5oTwo|?h2+bT0F(#*|@p6p<&-)0='
    '%kS`9HaOe|x$F?a@_;D+aulf+dI|OBTA&uPc`4eP{=?i!En73}oHkHqtz?5jBF*t~>vUc1bi)<TTCc7jBDbcjN@!h0%d-G}YU0Uo'
    'GRPO+sJum~#z~uA=CqN=JIpV8jOL<}UJ?)5)<Ejv;1)pgIRQPe-#M1$JE-Nw7pL-Ds5_NY6Q@jIr+o_woU(A7&N&9x38*Yz#{uhS'
    'SIomSzW8#-F|Rh9!@Z~C&DbwmsH|vdcN<Q(5fZtf3XmATum)R&pH>+4)XMez5MQ3ebGC>x;@*n!nNQ{TqdK5A<ffx0n2bKW{DpNP'
    'FGsdW$7>~LSk+Kx6wCb2FrQNWmaRFJX=SnY<(ImE(C(fuW;q+pf^2gV?#u4SRF2o^%l(MgM{IlGjSe;Am~8z;*W^@}WY+~jF>+*U'
    's*6GnjEfo1-ur(^-emCn_+THXiQRxAmutaYWH&hz>sm?N!bO?4CiBSw6sbYaroWmNJ=@vjiK@}F>8~}?b~691tdX{D{;N8<Cv19('
    'zg(zQf?r+LTwTlW_LilXFL=?pt*)(lj{HWA?M(=|g+(R)qRNS_QD1h%R$fBeS<@Cq&I>VtWg7mnE3x8i<76$i0&*&K92N7nTO0T>'
    'hf=O`KV?@{(;k@n+ot^Iq6X`)4<635_p+C1LTxOO`<LBg{+N4g(m@VEHnK3aXKraj1KD1FSv`**wN@O8*!_oKur~5=#$WUt+`TEP'
    '^hs!rs^V=<>I>F2mBzYY+4P0C#s46R8jAZ}DJH}24`2aa&gmY)1~nPZ#(vQ?X?KN*m!c^gX@yMZ|79m?S}oaLIwzd9?Sp4|8_O)%'
    '@dv?7t~`U(ImeSUe%X~f_7J$wvn)2Lip85<QJHUdtPZ@|bj~bvUFg(la4v+NHtM4MkK(;@(X$|}Uy^YH4eT80khc;+pO*1-^$YBm'
    '%CjWZ^&Xz?&!wPj{<CVFe-%yobJZu4{~WGf$-EX<uVh}Ut5-5amR`J)d0hjvTV^PDeFs82pkP>f|8P;vNUGQW^-ur&Uw;3m*RTKl'
    'T1xSkWtjh;n|Jg3|7oW8ALwuj$jm($Gc0Jpr>uy(oX-eywcLGwszgN}TxRBfV6Ow-)y0RZU2zx1ha5^ew&s&}7sZF1_ZP*795BXO'
    '^T~U2VLo|(ifp34_^$cnL;K)RrX8+|GH0FH*GTvCfe1@Y)#ECEYpTG!wx*LURzZ4gPbc;H0M_eJ)zy4eR#uw->*nKIypR87c=zLS'
    '8$J?k;pV@3n?24Um5#gcI0x>)8m=;yo{nyFC>o8~I-e?qJJcrbp|Ho?TqUles9>%G<$^ku1xzx%cprnlb_$*Rewj4Gg$wEYWg@}w'
    'H3@JoR6zhASqUU+s*rP7gi%QMBw61tbx>YaI#Ap^{gnz7eC;_le8#a^X4b|-Q0FJu1Q3=0rKr6IvpcX}s3~%@cB?2^dQC=G{cc?X'
    'RzeK?cU(1z^&OmXNj1NOQMADf`)}i(F4s0n%{$&6KMlYA85ryEmCIufqGE4BFLdBh)f`YtCXl1PaD(q{toYH3&6Xo|W%YX_qw=hg'
    '@w#>$WAl|wJa{c~ClUCC;cZ8$h!<PZDc+rFebL5-fb%6J6_C?e{5~&rC$q#=_#;l~)Qi?vSdo766tg0j+(?R{x;aF?C-D~RFd!cH'
    '8F?7cOKmU5?mkcn^Df3yuC`$1ojmeO&VpL8o$^A2Z<o|w$ky$bWM4XKj}nd@;VIJx>Tao(Q-ebKSnF%WfLd(FYnFtx7pC<?Gbv5&'
    'wvOGc6dNycl*|h<3@>t_8TNLScX0fYXXV6;^Dz&wEr0CfY_&guG5T}q#}n@H%D?n4zptt8<3-|w&*8)D9kI}H6vv`BJsc~SYg&2!'
    'gavBlPpZ>GjBu?cB$<^PH&%M{?(c6t{Fud=Dov4-u0CixUv|k$JsmRpxMWgRx((Apyi}^;(|gl}PYLld?0(CuKzlq89g^6~I?#T5'
    't}jFADwk_Rf-XJlDimC5_A8@$dWc7;>~0~9Ym3PGgak$X|5G0HzBCap_Za>?himf&7lw`4-Q$SnH+$R~?;<pGTejG>_4M{8%iNjc'
    '`m9$>j`@yBS4AzBd%&jEe~h6v^WscFhPLKRW(qRAyte3NXy8oi{fjy?q>I1?k4UBtH&LRABCa}CqEyr_@PtJ_D|}2{zG{@8pI$Zi'
    'xhff7ej}B#cT=KLUGR9Xw0dz$RJwINXG&B?{sJ3lDkEPWMFzaGqNSBBYiy?#Tk^_!I*h7W*JgK@?ww^i_XS4&6RtLv)ut+3*;_q0'
    '`>b1R%b>0oDdG`5%(1V7iMzU0s5G3?)IFkj?{;*172SoS+pDu#v72;W3*E_~_lW3iz2Efbs~i#f^Hq+B*YYYy#A|t#BSL@P7~pQ|'
    '&C}uN^;#8mjX9EMqb1YVGHTrP;q%R0_D!GRxJ6}EX?+ADDKbV|+R*dO?ezZd%g5Kl^x@|8hVhp_|Mj(dyS#n>@n@<3<)@!-Z^-<@'
    '!^f5_KdqSr^|@5u?!enm!np29q-c?PRaRs}qUzAI4lM%#dB&Bw78JQ0zB5;g4s4EfHR)>63FNL`w69?r5ueX~5O`kO7JilWPMxCl'
    'KhAG&Kkj`c(CvK#-EMd4zz}brapPjiOGw(|uWxVO>;;Rd)wGVIkvWd&3*U1bd6SSNH^<TQt-uI(c9N%1iF~z;tVkn0bbQE7<{UqD'
    'q+g~lRGn)eSJttrNIO35`es?yr|ay1?F?qFXBb^0v3cGUUu2G^#%kvQTGZGp*6wo=&M(C*p7&r0Z&EG$7CYS=>rPK~$>(x&1SVwo'
    'K5v|CQ1R+A?(|95_Q`>xRT=l(udkl>Z+1VDITiN`thWkZzf_-js-qanNrW1kT^-4MWx=5bfA39t+bhShCAyXjYHHLCm6a|dLpxH#'
    'RT$kjENv<J;ueki(AOnz6J+=uufqNaA>An{bSMeIr1wx#hWWdqB%9OzTS~IY8Nn$j`xUKGJyNnsN*7YP($>Fazsq);kTvY@iZ@+W'
    'o?c5Ak$td5UTVQVaE5=7yz08@!Yls8_+f*OsQL)pKSqLS`=aV2)EKpv@o1YvYBK*DFT6J2!vA!3)7a>Hcgn`tV{z_lfG@o30AF|~'
    '&-~E#s2DMK_fWA@U4H0vk00jBlr29*UCIs-J5%w)D@gxuIGTbiOvBU+(KX`JovKwZ@##1=ni`&1d@e<N=K7ac<l|h$lH&&5lF7$?'
    '4LfxHUUulhnH{>GU`2e}eS{Rd>=0!nJA@P)c9;|~gn@Mk$qUX67xBb|l=Gx$m@3mU9+UP`w(0Su$#NG*;4R_IJZH}Ld;-PXfp-R@'
    '&(`^=J|ufo@E54EP0gw#W)M6j)!C7<R8z66Vra^m8(5TrM_|-RP|Tb`BedxOnZNm<uZw{-p()7^fM_Ij_81ll^fB|Rqd3<7vpS*n'
    's5Ih%!`Id%%8fyoO3%$@R8mc%y!WA|6IN-(2U%t0M&8mE$K9L4OBjM7;h$7By~>J|=Z-W+XCc)_+5BkFI5k}ZN!;)WFd&I%oPlX8'
    'YUN9Kf(A_Syy;#PY{1Nz+y!dlw=kx~<jJKnNV}W)mhX@CFW^@SuJ+rff=1cz7hLVP-(KnVw)i5nP3Br)c0P+HD5n^7t7SUQ#KOro'
    '(wl9Rirsr)|D6Mzc>IS))KxftVEGpto?gR;rK`S?Cr!m4nr>9Qu+}QuVw>Nxl`1A6N*cyoSo&F}Mb*_~V&W8csUK0F^;n<WF<kw~'
    'y_tLU*l4<XY_zQ&TUwg1{p?wewyVfS$FKSN#QKLS`bRwZF_mHaLH8(BG6&?v$u|<M@GBt9@syurBB1>E7xsAU&&(vo9&{=-)$nud'
    'u|LK-{P6&<2tfWji{Z2)YO+_?K`>~+AOPHW@y*1)L7A5J8(H;3)O7Vt)lZIWeOu!gs;VD4p{pxg_2a8R==l`qOv;1gDT#x5zPG7='
    '$^*LV$R}zE&o4WI*zqCDt(S5*h294#RP#~XKguM7@^SI>5yPvT^G7w5)sfL3q^b*fvUuc>A>i74o&W&2^VC8!wPXg@h515iGOE|J'
    ';mqhrx1@$p`}jbFtSn}b$!tBMq~?h?hUfRn2kFe&D}T!Zxq@`@Y`aW(el_R_=NHmf8Qtep-yrK3&5+Zf$0Hh#KJkqem&c7&2xvUT'
    'H3opB-4R?Ga%9BI-CUKPMlWuz5-*_j1$7G1JOw@mRfCUjv0+Iw4k%G~M=CP4S1_sRrzSVW(;08%&v9#lN(RHb<;O%qdC<C`@sU$N'
    'rjM#P#}5bXBz@lST022mo{NeHv%?z~5SQ@$Ds2E%*|mB@O;ssm&Qer@R?L$VT0QCH^r*_@sxum;XH~WHOuRc^)vzC9<^(F}-hqWW'
    'x=*r>L#+7m`7G<YNkQ@V%kx>H6dv2IIX>xj8Jp@R(=a_xS<u~#i;!a-%H-Td`L1s{%SGnNNtvJc3oa%xK18R+yhqZ#$R5c$dgM@k'
    'gI1@qiRL(7z@u@cb~uM`2dyiGYzy7z4-f%C6X*1uEW}W`@BBhCaG9ZPlaQe6cHg|9jMd<-k$9ER(f8yn1f4`?mP+N-u?ogd2cdsl'
    'KD~PTx4he-7t<bc``tnDLC2~C7Fir~d(}Y`Sd2PB*YGRUqM2};p4QHtbHN1~rT1tZjJ!zp;CqgmdxtY&i})X_cGXEX2qmQ8d1VJ8'
    '3i#oi4ZUD=6H-wrZ-%bK-M0#F{*AGk*}Ac9+TUE7E-kw1PMMQ%5u@CNOV$yLzx1V4Hw(|;SKsiVETGZaZzkT)23ph_hEvs#(#<Wc'
    'uCZ0&Wpzi}%XgucmmooFdJ15^|9IlQ=0KUkXg$3PYQH86HQ<r@E57zyDUWws>UI80?Y8>Op8d&PRsrZby8|hQ;b#kT?>pF+P#y6m'
    '-cdK~sivdhO<diOSDF3aFgcqmum)7JJDJnNa&`we5u1<Zv(1e%c0F_6DcSP^IMqS!2u_7&)TtR&yWY=rJL$Fgx$&)|ptL2kgZl&a'
    '7SlQe_#1a{HAvQ$+FQvi=UNZ8sy{g6K5(Z(eqDZMr-G~162>*kM$~#qE7@FZ^`%PNL(w`WU0mftND4@WNOB<^Gb~A^A5>bOmo2Pn'
    'mW{qfBWI`YWdn0oi4dP;%*%<83_x-rLVSJ|d|o!@bx%U%W2!}rZbXbvB~va!E2t^<)YBw={GOkDFn#csn0S7^6`tcFv9c|(aD4Cd'
    'OK^PeV#D#19_~;1l+e@mChjXxPwXqO#aG~cy!%d{fJy?pXtghoz2XOdanEgaU7|fKFZNh+u(VJoI>UD3VQ1m=&d>7DLy&cxJu_B='
    'yvN)ON;ZtxR^zHFOLl)=ILHp@9w$~&@t>d>>~qGVchww>s)q2Q8N$S-i;5iu%h{1yFJeN??}=#ar!DQfaGpQj!+IWG^6Q`SG(v|7'
    'BqkA@zS|BBuE*tquY{2~o4CPOvdA_(ged3**d!oCP6Dm*mxkB`5|wj~uFAqqRTFZiZoX?#h_lDdagW<nd)%T3eUDp|@+BBzlr5@z'
    'UNPWCI^I*feKU?YJ#9RPGbT??HSwJJeWx&ysLx2|u6$9Zs$EaPjj2G;rCuD3>1eOHUL70KoF`>_4_VRL({KIxw@!4`-snt6?FF2N'
    't&ZxX)J9%7{28gqw`iS}D2buDUu6lQzF*-m9E&iCDa7r{(2c3~Y)UC42|Ye7K@MYH-(JV|s1nNJ?5O>s-s9F3fw7@>M}11I8cI_I'
    'u*|THsEPZOwR&3B!wpIGh#9Gb;UuxyN!<uIu0TWtA3Q&8MUmC|-Tf|ez(B~;P%jZ37=^B$bJbZ(i@AE?fqd$}|MmPPHJO*Vg)~g>'
    '7ACJ?L<mP^CEMTRIx8Q`p{HoM!~H>Ycr+Fa)8}1<Yl}6O2_$Y-`BX_3&$%(&QIBH{tea53HYvl~T%&w)FF+KjmM)8vJ8n$WoEvYN'
    '?di8K5Kj`NFbzkop+%w;RhSyf_l#0j%ywJfSehD~jV;bG%dm)wh-WTX29!<lkn$tN0B4h&-lx(!qRLDZ)1WpoWxvvrv(Bq(?%%M>'
    'UWUBODfD~~>Kys>w0ntjHkB8Kxq8ah8s8{#Wrp?zG;bQEuF;zU_A*5{+1lO7<cI}VWt*LOVxjJ{P>&UkN)~Y3N{m}!#fSREqfFV2'
    'ZMr74n8r%qn|uWkbi<lbUh+j!4mB~1S!Lw%v>Ozcyg{*5&1i;_k(d&q$4Hb=ylJa%nz?}zU-94&QJ=7SaENLzbbM0B^8P5<dV9)*'
    'mA(eRi#g)viV<ZP6Rv=lm1xyvL`pMsAZ4C7D%R(y*oY#AXDu?{a@5Iv{#&k$YpQ_dORjA7hAky;(mRT&(#sQXjw^Gs6++G7{n$yx'
    '#%A)F3n^Er=hE;dcVvC&Z~<iUEt3~EPu{EU<?@v_>bTct&R?|tDISL#Pq9S_947Z3TCC!VGpbm5mhJiVI|2cP`CNv1%Ov1W)KS;o'
    'MY1+(KOlWj`TL0r)K0pnYfx2*xEvp<51JPPQ?;vJ{9cNcjapS5Y{|L4nu2Zuv=XvHL{!b)FfkFqGk00d^g)$5EA5tXVe{N<g)TRK'
    'V863HI0R~nTy%_2OS(a4(ghmHwQI1<!}VZRVy?-zi=A!P3fORF<Jx!YKT+G=(n0&KbkLzE9dzhQhg=wsONW%)6LV#}OX-04A0{21'
    '7%?DZ#DJ({<ssTGQFY6VP%j`OOkK|9{9+hUJ+HOwQf?77))0$_11uU<hf3Q+G@FZ(p;P%)XtVP96GJq*O6(`5dd_2rrVf1z+ZPpc'
    'FmyxjiRFprI%8t2`soDoRQ+5B^YB2OxCQgv9jFtneA(;^8qoEgp|UKo%2Zz*&po@a1Mmd@#5bJWn)W$NSDRz%T4~#fSJu0=RTtZV'
    'tEvmz2}h@v7YIj>sPlDS<VZxNuKOZK=%d*4kVhMI$FUx5=;Vk*8=D-FCUPX&1k8T%^Q)McbL2>LBKBP9F+)eRF7ycOh&v-kqEn(D'
    '_d%`h1)O34p18((&J5IP-(!T%@U)Ca!cj+Odc=*0o#!WRXYbL~-07k7{Mr~1;B)<qKuxye+$|i&dGQq{tNWT_meKW#Sw@#^aIVaZ'
    'to~G?eJ_}^pv2ahY7{T{+np0ntNF!{H9ufcTt6&EFKds6;Z1yU_KD5GSj<5$UB1dpNLH2&iV?kltKO^DwyEc#_1(6C*P$_7v+3bY'
    'TkdslI$%GQdEyYpAj;}&H}FX34_u?s<y(q~p^jynlxkn+)iF_D*66ApJR4o554_<{0Tw=z?O*Rt#W*yZdXO)`?GV`0ah~~b5m;W>'
    'K)eVn&p*qCK#~G_{MA3wEN+)iX}oZEL?5;LcF?R%2iZ$kjG+$Z<8n9Dws`{>5W@?H^U;8vK$jR^BAhRVI-IX5h7^P81$;*oD7rrc'
    'n?4Jzn5aUqW3Vs607DmWJqD+GVj?*HEbhF1S~0QeJUQ3KIX8+l>K)yyNQYp~8QF*8S~QmsyBc+f-4N~=h3u%yQ8XFlt+pMd>SSb7'
    'QzwL*S{h$R{>iC`-#H^YMpd!=aB$R^fPp*ub<Eiq&#Pab;52-jHyxwt1=3|^7i$f*;h_M~=r|-|4c>d?WXB5g;v&5*MlS7g1|Dal'
    'F?ot#j*XI}>9EoGBBGNnW`~XDbBwB^S!FgGqi=X=s_@1`n*o)}_*9N<j^(@ZiF*NNO5?~je>SO0Xmb}2t))@%{9Z5Sr-ft<bD5x0'
    'cZclalO{PmT^wrCJq-hGJs>l*^-^Z3&D@=lhA%?bGgY?Fy5^BZ)}1(UcOWr7@y!hmRUck8qntjdN<;oap~f_i(93Cy<%7F(+USee'
    'sZWU}{rv0$!^9@Qrx4Vs%ur->h^U)0jn4bed`B&(HYv^-)Jt`^vW7|A-pSUA#-wt0$_V;GbFZ!z7f_?&U*CUt|K|OVKidz($J>V!'
    '$>08|46&(0N0{DL7GSKWVa!XMptS!#b8p%sXKtj6{*{Bl80f+68E{{K3j;nlH5Z0G9%I_`S$MbXE~BK<RF&H5^Xo79a*N=SSy`Et'
    'k^rl%mrU*q27^yLfx{C5zBQkClT}0|kY@e_kwq7BsR~C~0&!7%;w_vYT|JuC(Q4o=*k=IGh=~#oue_n_O4`r#CM5o@9!sFGUO`Jl'
    '%7MiB24oKpIT%52l3wr4#|0y37w#{?7A<Z@(UZ}R#h%b;F@~KKX@$P@IoiEG;aWI8%@6R`;s((Md^PCBW(BtB)DVfI3Q(v`=hiCP'
    'SgCRW>Ncy!X*?rCk54QCk(p7~rCFG_CAR_WvS_!ayx6mRj$3d<x_W~5b+L}lKjvr>F$X3Sf4`Q%cz-`6j>U8eb3&0#-0j34a5Pt+'
    'M^<^JoF^UGoU}}6`S-L#g_eIv;X4<I2<MU*sp>Uty_rEW<(YGy+(%}HRdCu~-1F}c5Bc&H{SFg2N|<&Ngu1V1#E<FHB;pqZJn=pa'
    'Gu&`ERM@k-qyF&xFj{Pl3lhy-V?GaE-`;%|3$rY>VcO*|x~&E`#3F`CAUe|^2!a4bfa%w#wb*o2yys<UI97F)1@&U;w1Bm}pavJh'
    'Q8%Xgal+*g?TEW08WkeZklRin5^;L&k0jLKLR6=*_*@oRqEgt7!N8>$WNJ2aU;gzIDe>$1Z~g}LtlT!ZKm1m0g1_$npytnyuB1PF'
    'zF+>Ze!PEvzJL65clVb+{rAIv{_VrZzkj^@usr<nzy9>oA3ogO%|BWH>G!D_0|T^63NBFZt+k31wh^CW6z9RG*~V}pfe||Cl`_0U'
    'rhd+@pYuaXQn%=*BqQsyOQY@US<)dTg`h1<u4{i@3{UL~2TT|E=Th?-6Nj&scan()43Gz(wRh1Zz$7QYo6hp<x=t*!N!{bSHK+`K'
    'V6@Lo<U7An2|1N0?{fwL{41s_V;HxHVRY3<Y<6Nm7E2UUHe%9p8sakIJ#3%YzJA`8mu>xUc$j{Eu3DHH5PY)>$#aBx&d5K~=QGVS'
    'TVAr`V6Z+>fbAx)yqwp(oVBWznbJIa%xLa17-YZZw1-{+qFHXAUY?v}PF06kuLG|z3$IVows`N72IUgFuHW-AiPTzmNA;l}79aLu'
    '2pFM6VgD`Qq~+2mL7NK(Z}h2p;J)V5>>dsB@pD|$@v{>*@N+7O?UuUqIlQg=&m4W`>9a(iMf$AKXPG`*9Cg!u;^cKhBN}@eirM6I'
    'bfJ<QsRTaiOfM5I=~V0{m*rIOCZ7czsb1yV(&|@c6g$bK1$1$Ty~U^PfTkE~bz|zfffptf7p%t}VG>hXxD}Fk(qzCm?2_onwcDpP'
    '?uIM6Bk7L6VJX-S+^$_(hu|Q$6)_yx^}0vkD$^0DgUz<*dF>Kmz{B{eWFX^&&mx;Bo4M~?7hyG#>-vtbhNUiWTh`dS@t(SR1imi&'
    '0fAS2-HCG$-y3v@Kay4f9wmuLf-M|e35kE~;mV6Z=S3jVQ|bDUJjPv;f;1rSIJgSEmNs!gT#ky396nxX$nX-qBJ%h`s<LRN$R-eN'
    'DztU;`qtww!dfmOFiLknY%TQ+M#tD?T@HkIe<eGt|Cu^*Q8Jj|8$NZ>lw%mq-6z`Su8&VB!@*<9`z;V7NMm_PQ)~pDen!C*n_$lA'
    't{WqHGyQmS4bq`sKQC$oo6MuG%#l&ox7l?@V>lfJ;>;L^#OigupM{)L8=Tr<kH({Md29pP$y11<IwI}E5_S{q!v<915g$93hc=<v'
    'Dt*v0(g+E>)oeiPrhD;pUG;xuN&UARqxj$g&icK(mN%FCBy_Bx<M#{;Utec^-S>>`klr(_?1!(LV(2;w!`Hd&iojRMy~FtV!$Y9z'
    '0%aA+FWwtG*s0D6!{)i#=O4>m#To(Z9W&9_9TKC{kQfE~SYCM2p0^>iR%Y{;D2<~ufzsf`dN)v%B-^vG#9{ZSlhNy&hd|uoF~C2P'
    'cc|3@$}084zuO+y1N?&|><Vy%^=Uzq3(@graorFB+d@-U*l{z4fB9%&O3yh>Utr?!7W?D6h_`{i(g@;Bj|0TEPiuD<+}Y%CKt<sw'
    '9B|?Kt8?-GpSJ0`)1sy{G-||QPyH1UZ2swR<;|~kYJ(oYLi1MC7^SA&Fs?<B@|qrc?_(=mI~@klyyh&qXkCR6p<PXhCMu)%mJt=K'
    'YTw+c?=`Fn_T9s(fOkCbhx2Ltl5wGQNV6698)bYva+KW!6Y4sNd}7!3m5x$@BRZmI2A9g~X9jddqmf?-KPALP?J-!8076MX0Krop'
    'UFDfe9v1Up{PR>Z9Qqu)h4=pB7Z7|HkGSTj9$}YUPgF9f51a*0Spt7=T4r$E1XHPGE08lZaAia}v#9Hm^&GY>&9|*dGfl!5C5stl'
    '1Q6fvRx!-!=X2mI9W9hiE|FG~N=o2~=bT43=QYPwFbq~+z_MY;OJFzKl?BNdeqa1oS904$E=Gnw>cLYCm!8yWm)24Oqk95n;hark'
    'L#=4%nqQ`;)jQCtpSGv_=|Q|~Uti9K(7H+h^5tJcsOiwbJP8tc=xcGb8S2xQkMs6)_ggAoVqzA#nRW^l23ts2yD~Qz1kKSPn064f'
    'zGM*05Km5-!5hHBTJeGUPMx<Hx#Ty%j2dAt=sK@p%HU1YrRibUIlaN+kGQJRbq@_FO<?4bjx&iD{=7B|pF=PE<S&rZ^bH0etMXaG'
    'v1aXaamm_80lD^IW}sxLhsqXLH(2{zjiOg1)yjwa0$1r`ug*fAM~A0!?Wj&`j^LE@d|gAxfiI~u2CukDk#@ydJR5X_(_!IsY!f;R'
    '1!?W$sGEY+oYTbyoliYMZ!oKZj$);yo{EdMc8}@jIhSmPGEH!PgU&;}0+QgDW?;SI+|E}@I27nYl5yvyyg}y`X%*w#0>v-sw^Kxr'
    'Jm<XGU7~uP(y(@Oi<NIsjE!|B?b5dwje<2pX)ZC86iIVQ)cg0|b4eiqNLVvPvWjZSP!HG*HmHw02My5e29^Ah4Jx@FPmy5bDH1o>'
    'por578mDqAB;G=czZs_oKq?iw5YF0`3t{e~Lc|knC!Sb7=i$-GGZfIfFWkydP|5_M23B7e(y$y@YD{<#`26Mhmwy6yB==q6?;?FS'
    '_<OW$$N<+Z-&y+3b|_W)o~#cZdWOEI@x^=|fWg_P1!{mVaojk7c~J!&730aj-otyc3KxOmuurlN!kV)HX4z~DNQo3U8y(b{oKpXf'
    '-|5Lxr6_&~pJ6vWC@sHQU04s+69Q9i8nEDRk?cQ!Mc1WqT1ay)Yyxi|e)EV1VbF4<`y`2;IKHAZbG6n<(Y(d&tEN<jISc?_wM$b-'
    '+y~Td0&P9zb*EtPo8Y06gpG<O`S4n^PVDTysI-%n=Hn65>S`lq7#uOPKR~1I;-^1Ka*iYuVnDt!Y>kSbGSDS?{4};H4bS>g1y89h'
    'pD#9|>MEiyuU$Q<rfnIx2pqO+_p`wE;)r=mm=4n!c>5o_kp7S9v;1{>xL@ynjRWl=am`&wtSJ#W6adEwsv#BsWpiE8YRzAP_|QW3'
    '&(X9FbR^uLVng^F8p2aUB$k)US5(o}<fX=;w>wj=_f8#ykhna9NXikALp`Aue1stTBLqoPYXtUpt^R<Gq$?|Y!2wboZ150BAD|Hg'
    '0qI@7=w18x>uw#0_o-NlAuS_+P7=T|@^CK2q91mWhTR03ynHg72zbnb)=<&3qof(w5N*zH2sf!A0SnuGJ&oYC9x$1D?Aoi@4_)?*'
    'FoO>l(d7}+SNW{Sq(XiOc??u+Jb~4~x5uTa(GhDTWHwqevyn@w_^1pl5D`*sZ<u#l<{h7m28b6ET=k!~m-L)Drv%LOP2rl1cCNS-'
    '%o{|GNFv7=iPj`-7o|b;ElxIrdycVeyketkMQEn0|NJ3TYigz)x|dRmLsdYSJ+)*IyTd1mYIV}#^0dUBT%MMW_%U4?BctVM8LyXT'
    'Zah=N^=Uce_t|<!?y12QX?<Fb3BwlH2Cks`yz7M~CE3xkwt~fFy&sFeTkjuI0>U*Rvyl~JOox^DEWr=jR-O@d#J{KRN_RvT{*XCY'
    'eTqR(G{f}}?zYF*Lx+t%cc-PJ&qbStqAgukt+8l5K-`T7lY#ZHykR|<ydE$<#7*9hU<SiZj1?V(dc%PjVV;as=k8QG>(T;*@A7LX'
    '^N=_V?q(PyHO*xhS&WT01Adv31dvS^Hi+VhWJS0$!Z?tc7uFMevwAy<MF3q-YO=`K)ou_*IIDzaxCwMN3G?W;6PtvQ-~!UyB+S!v'
    '^*0G4vSCQfZI@ysG+i26yW|a<WXWS2;H@PppedV#d4wFhimvX8+V44_o*nO5<|@RJNqxGkE-e~~o`z1N*9ai&88Ia3*7Mffpj@(O'
    'ZdWEH>2hD+-Y^|yHlp|ocEpQrVa&thP*^Je37^Eg>{lAJk0_@uQOjLX1Fqh*ej_d}W0_caKV>y8j+L7jqZHXprmyIC3eLg#?O$^9'
    '1H<;QOCyW%{qi|3R&d>Clv5-Ppyksg%2p4}Bjd8R9<J`Q?RdB{507g-T$zu%*Lt`zPj1$FxVq1(<KgN)o65u0eHw{VS~;Ra-P$F}'
    '(M`;yLC1xQbZbU2eLgw~sFJWAyPRK-Tv9#yRgS*QBlcdEFGde;b$geD#`U>qtu9F->pBB~ZI?JyL79ixX=Je2*=*BKS@7IW=l0yX'
    '7QQc2<F3KQk@j%DY7Mer2R!Cc!(#M3<UVUsk_F1o+&<I1f9F{09K)_KE3g1F#>&CVNhdPjySG!3+)g!KOM#I*9amfHj`r^D6gIV!'
    'pAi7VWfx~ez;M~+Fa(BA9A25-=#l2k%CoHacQeaM);GolhVjVaK>?NjchC1bsqlJV4HhJ(J9J`Yy#K1m{nF#BgU4vr;zhrT-@>hX'
    'e8F}jnIAB7@s?G2WX_X^Gbm&|`gH0RG->GH(hnm{vO~YdJW3MRE1G&arNf`on*2?7er{TZx11P4p0&Y9ebRU~IBUa%Mybt_k?7ls'
    'ZO#FYd|LaF`ylC}oZ|!N9;I2Z=Vj|W`|e$t=hPK}T&Y&H3IsB(gZLgkO`TMbxn#9G2~U2}1=nR5%S^72uY+A-<!XEf;LzCZcE~pn'
    'JW~=pK1k$nsbf}8FGc-dDUk#8=Qm#L+BRr_+==SpOMruo8}t42!HP&48ikb<LP*ca81N(^mmmZ#9o;(oy?cw-=oH9A=IsZFqX>0K'
    'Il?p1_Ocr);#;!&T(c4}K?&}?;KEAcc0TGoRo~5g30C!<G`(l=$^6igg1viVWwNn|_~ejoVHDo<1y>_14HJT*G{8OL(jaNSm&@Qy'
    'n+Z%?@%$MW4F#sHFx7jwOMeS#1@k~yxYZSq)t=xoEX5hG#ejn^@*RzgcZ07MYJkEXz1Vq3YzO`3zIS4~zz~T(OBW!=L?0l>L?0l>'
    'L?0l>gl%b2OPcC|=a{Fe)L`)}$WA0ll3VDWo;oCHvDZ13?TUQ)d!V%6r&^E!B0S@;l-5D3<<>!{Lv)i%<}t}eVWNB*c7-HM@q$Tv'
    'N1k`nlR?etn5|?>+_a+Dh4(2Rib@qOJ#$@+1P1JPoDn&GX^_%1M{-V6sCk{s<|WO`_bsXF+k@Q43SNw)>Rp~@2<>E2v*zxTf3G{2'
    'ru@U;C)<XG@=3gNF{<hvMTm7twr0-O?a!?kg?ROegYdDGMK~<hYFSDHwjipmJ8@ZGRWY_e#|r7m91#NApU4Z1jQKGSm59v)%QD4U'
    '7<n$8$)3sEhpp|HylXzjG)Bz!Ox_+C+c9}7&U+?r#btdesSwSeZ}#y_j_@iNqC_%;*m9XfbFIyN6dKH|X|=9PW_C#ml@e`q@;vxK'
    'X!RmWFb}pJtq9pfu%96Fq02A?4X_yI7CAuYI+bkpK^{qEpakpi5?nG|bKVG=3^?zY(l-(DN{hY*Jm;0C4Olqu)((S!zpMfNx*T$-'
    ';VMgp8g69&1WU4l;xb)%53(9j>~f$ooW@ltyBfI;zFOIhq@7)5H<EU~v(n{($_Q2gD4|@UEblY#*#?bOYLeZ2^I&jrW+m^7k|=I5'
    'Qe0I>GP8}kp+$Xev#B|_BZp^K--!I3eSJeqHagU`tV4V-(^lNVI`i*UZ9ryo`+KFv8i&?HWk_p$r=uuMXV;l`oIG<h9Hq~IUGI=<'
    '7t@vxEtJ|q*R(2@Fl7-Z4F^^=%f=(7t4y*PeM34+BbPv19X9`P6v5Od*}CFZPc<#vGXI`6o1#@zeZ=75vN2o?3+J5>B3Lkc3^Wp7'
    '3lLvM6!br5*9`LpA?nOzuRw5wQjMCa@cHDMne`WgJqtXbq4G#!Mk71S0w4B_M%I8G#FC2+T=NOwvVKKrw%L?9&6K!s@3$#Uz-D5d'
    'c8zrYNv)3YfU`$XV{I{2gi=T;NNF?!cuX^-UjyWTE=?A1l=thc&0a+rJDqF*F@!-D2eyh*3gxATMXUEelVgNpq#Q4~2{yx@-mwK7'
    'Z*2>}Ssq3$icR{-&hfjzTw}Z2Oa2iEl)=T7jS@UtC9K5Z46WCwaswp@XUI9bvP{ZP>^_Ea9o{OBLky|7H$h(8I8(+U#M(#?YY2>B'
    'F=%q%jwP*NhB*^0%;S>gQDbxShS3_6?a(u#0>Xl&<pXEdj$>Ccj|qQwDar}i<w^m&9w2=_M^TsGu@#h!ZfBg(ikfgOrynOnHxEvN'
    'eYQM!1lHD^%!g<fm&V^;M7dh5XN@i~0(WB-x?FM+J(Ayf_@(IUw^2)V8SGfU<&m8f+054T%cGP9oOCG*kipL70gMH15L$N8iv~fb'
    'ri54Gt^v&@n&HvFiKRC<8eBCRpX)$_=RTbB4K}LBLx-oHf0Q-Lg2ohcP=1q!P>ZE2;I|Sn3)6M%E0_v6|KG8h73IGGvWtpcz{9kJ'
    'Hs(~)(Up<=u*(DVFsI=*(Rk-BNiUW$pE~DZiu?G+=VUh{A3#nG_5u7M6UruFQW^o%Ism#%(3gc%+xVbHfDNY>8Y^JL1gAE&Q04S9'
    'Mr3_oc)o{{kP+J$$xTe6(B{g`m9?|vdEx32V_D=mLyIh8hwI8Bbx3VsnAZ~ANI7HpZ4Y>RamHD(*9hLS|6kNREmHG1c6y*IxXy7V'
    'uxlgVQ+ZAmBPRgvDMhiPiu+{xXJ;M`$<aMEP_v64*}uSbCp9LfhG`0iFbYr9*xjCcR4iD09SZJ?MwX{jl7;g;9>(&@Pa9&+i#)^w'
    'I|j1g%m8P`eWt=YX#xwm47ZT+%wqh=0w>?1s|uuO;XX2Rxk<g-NIE^!uZ+-yLQHg@Qqj8UAfPW=H>|WmBPH&g=7Q59!GKG<$z8^S'
    'ice@J9wj{1Ogug6`>$FjeUbJ-ftce0tNS2CH0R;25GRt$>z**orW1x&R}Kc-pa8kjt^s*JQFw2vFs(>`ikQ}}fakgi6WZ0ExJTc='
    'ULoS<92yUQhd3$x1Tn`Hsl34j<tOzh(YZyZpEKSlOXX)RFggvg;OIREs7anGv=)i!s1qE*qQ#XFBs@V#xTxZ{Lk&t`B0>1D@6u#h'
    'cxBDO;SLan=Xox@%i|U4RQj<)4hzbPht|L}h5Sy@nNs5)IZD&O_A6~m)_c)`vo2|H_3*iid+g*`F%udw$AzWAW12bZ3bLagU!UC*'
    'd{&BGL^U=q1HH?N#BBcEP38kpk9La;9(KKpObkE`FEVMRN`?&r0+tx?L}@2o`T0tu=POrFyWn#B_zfOs-FbvxuqaqGGT@W*j-zn3'
    'Ng1V{AKHILKMN{5{u$3dgPIJ#^2qWsvg)LBH;?$lJo*53%RMgf2I`IsA$KqY2)$o&X>MW?^6{yU+oq(Iw`homNR9-c3haVi<--FT'
    '&yZO@{`5K7!?nC`-&EmVUI9*_u*)Z$;^w5RQ=$zgoJSy@kR4@1VT1}$8kCfcUY`pLp<m;y$}7*RDAVfh;Z<-$j3;n8EPl(U&0bI%'
    's?Tg{z3MJ{pxWltSZ(VAO_}2a#ax+o*3zZKN6$9!6{dZwP!@4zAiJ6e$#JBy`{hOcC8fgfNaZ3AGH95A(m6utN)Ad<4(@YUoI}DK'
    ')@PV-278mK(M%lCfpl;#9T=xHCpS5KVodDl2;yaF`mXVJkrVdywmhtPy?HbnbS6m$llK1Xt&<7&q@eKolD}g{=QV#9JqH)=2}I%d'
    'w7j*z&Mj;H4*Qfvjt=B#`Lm6mgJr(B+oS;qR{8RsrtcDeXX!hxHR&EPkag|;!+jL%jz^LEjxT8N@y#Rd>a;xC!99L-8S#4Na~e<$'
    'x#NXCxK-zu+K1)w)AQrQ_Tm21%l7p2<@3vj_1-PEm*tnVj5OjA-61-;RD%)ksXqoI-c$FD?7-&T=N`!3ea0aBG#3_EnWoO7D$_(;'
    'RAX8dRzt9V9%+l%aPpF~JvJQfQGKwGujw;|pO^fZb=(fP30Ic%dCH$FuNyd%CQzo_KW#7nllQ47Nqq&A05^<`6$npoS~D7^Q7~-C'
    'bj=ONfeqL?)m~ICkLd-=ERkqK+|4*cMxaaNUR!R71g7*55iG#L(o*nfyk1;R7$G;V4-dTSWwjtgF1QStK<|)grB~>Mz)c|g3U`rs'
    '0ZczMq`BYZp9RgjTvT@OMoG2h#7h&p1U|Sj0oWZ7LbZ5|SsjWG6l5jIHut`iW(i<MbehPCn2=Ny`SJYl_;UB_zuiASP5(yRiKNqk'
    '<Y9K8DHim=5=8cjmY0XkWjN54T7s#)o^f@mu&!UNK7%$i@LuPZAz<PPZE2Q4%f4dv?QLN;wT0C@B-{t|K4q)4d`Qg0Ew9<TxaE!R'
    'YQ<Ua)t<bxE<v`Gt4S<asfGf|N{a=QYz35c=j`hRl+`W4Yi^0Q#|4z<F@2?g@&u*5tfniV1PQygFQ8ni90(|v)RKkgpHVs%P=Zi>'
    'Qa}m9+AzwwfS^iu1e73^ag4(>WE@k6Q`?mO<Nnk7_>bWp6(rcSJJQJ|wG1mI%>wCkg=Ppk5>0{#0Y%d_DpMo5B#0y<x#ZH&=`fv='
    'OQVJ)q2vmzogv*PbxJ6S$QaraO2Sis)<vpwtSy2BzqbwqMtJs4U0clNN!cGtm>xk4aJba6<+h{j!~gf^|NP&7`16MkfB8Tuf4Tp-'
    'J$?8%eg1s^>F2v&J@tc00~DY%>Eb`nv;->6jj}ip0)(QvM0>TyP#8|<cgqvpmp(!@YA6Vbo0b-(XpKW>2A3wl(z>*v0Y+bF3xS)k'
    'pp2lFPHSmt?hVAB`8;fDhTWskple_q7eaVG%_iOmK{?#UwtEf$Bc-?y3E10o=T+_Wuq14_pmIozC8)$t9C*kSt@ji?ZQ^!$hU`RQ'
    '=eMki)F)XNU7j5XP_9T38k~zYtyWdipjM?tYa}{7mSRq0X>i;rcyjt!*YNy0pfp)r7B6jsztEn(#zX~0uz=%83QFS&Cm4=yduBv<'
    ';qhyAbCSYx*f#e!oxzT0;gla(F?Ovh%^c%&IIAqUkyR{3?z1kWk#3;Zw+!@}de&&Qf{B(OCpSs(&M9G+13V>|Bw%B&rxt?zpD*{@'
    '%ib)W=HJsr_Ue(i9%y2JV?`>P{SIXW6zf<*1XDnt3gD0Rmz1Qg&=iBEx01~{<LMZI-Y-Na0+(P|QY>gqMM*JV&`zTfRfRCfhe1^6'
    'GQ6ZMaD>qvT-UJr1UMIL%*`t}X{0$HM*a{y7^SkHgXaP#km<?46r8)uVskm=kPZQau5w8d?32T(eGCReuDNs_kJ%uXDk<qBYJ<^<'
    ';kf|7OQ7_40omJQNDG4<wnvH79?r*;!|_878g5=QuL<tjcC2d#H9eTc(<oOJOL(z*<3KxQ<ydPhYE9q@8ni}<%Uh$6=>opx3J)?v'
    'UP~}cfZ)h#u6iECRQ>tUrT^jc{qi@zr2qIBoACD}0eHAZbl0>Y7q4l<#+@?)<L_|ijJ-nV>?qcpOHvniu8QZ&4|DNZa^ifqp5K4k'
    'Ef2d?Pjw42Y?cVrLw|pMd$S5|FEz`;X3=r8=(t(5N3!TXTd2MqTBzo@xrfwTb`I=Hc$UG=o1BQCzaHtF@SwlWd!YM{9RDC6kr06?'
    'qkEu;@GiJK+-C_VLa;OJWItPilpGJwyUIZ%!qZ-Nrea9JAd;*(CHci+x_>yAo-!Q~B2W~4JZztqt&Bx2wGLokd+Z+2dhBM4sUS%P'
    '9PV3di^fUEM?vx5)6>fz|MJs^9A26I@$v4@K9Vq{|9*dX{M*z0&p&TZchs`GySK$$7CtEW!1GWD(|LPLX(5Q=chLo_(1=^5n-TZu'
    '#6j?Rmu9|~uE+p2&T6&g<cBJRwcBH8@fdQ2=B6;==?*EG#6v1YJEWYAhm`B@W=I9YLrUg$NQHg>A(a9Tsi5tUDohkhDI8O!zMC=C'
    '6pg9bR6C~Hy#JUQENd-S?U;6`$#NSJb<j5*QbkBLq_!DSMfAH5siF)IDPzr$DvBLTW-z3RiSK4e88+IRNwh=C)%y>rpm<1WyYrR6'
    'DusqaD*1Oaq!OEb%%a;NRr39ZR3mQzYYt00q`Hc34{u*SRQmTarolv2#uPq}r{-Gm{$pxecd=BzCiw7DYrBMF)b{UTNHrZZxeCol'
    'eYx=@jPBDf4=>;o12;e0aYetvH6xh`H4>VNcL3O}EkHcKJbunMCe0x9));#I_A;94;v=$H5lI@mw@O_xIZ${MYaC45nx#E=G`?P%'
    'lh1JHb~5!(p7l_z6@v56+SulmQfoOL7mWxJ0*_AWvVn{U_OSH!l>TXZe!hSF<hNDtlC6H)o_@Vww!b}1pPoNIKE2%i<tP4u%J})O'
    '57W!x@#*8;o%wZoxOctY?*96xUq8;?lD(ucF`{`@@-LZ^2`&y|lir*S`it%Au1`OdpbkPu%lfzPRmR{!*Bb)cY6y7w{f1371hOTs'
    '55A!kH`II|gK8*>coWP{X%8FvoeXE-Fb6;%zjMU|%~^(hCz~%qgHdA*ntS%W%snT_0yw?))hz#BjtqZ>>+fUba65b&GQrUTJ`EWG'
    '&vtI@Nt<ZhnsAEc5fbM(!V9CukaL$Px^`m^%!Vqd25_gGM`NCd%KPDfvVy0GNsD)#Iq~>;`-C6*j5eJIdd+6E*%2(|TeQ;XZYw!z'
    'r4`?}l~!G}!ENyD>}_xhPug$LH4l(KL&dSQA-dXWmov7&Qrq!55f%d9BCGPO4irwaWhe~&thRC|Ovnk#@$({x*CssvyVMb@*fvy!'
    'K!|Mwys!fPJYec(wFvZksXBR9^d4kYBMz;)t~j)6Z)#t@d7L;JM%`-WI~=?t1Ffkw*rJtN1NGPGfH+dM_uzV%eml8T|4+#GhO<Z~'
    ';I8$oDE%cX+zfekS+r!WZQl?>n#;+?8oMNj<mlV=*fm7A8ap$ntrS2*zGYL9o6D}T?-2_?L)CXOsMHKKc1hTGGMtRJ8oS~Q2pmaZ'
    '@YrwKSk8`W?2_>BW$wAT<Up51j4)#^Nq!$IM*t_8c)y<^hrJ|{4zc@^Nb!AiBb>My4X;IWnn|Mgce1P$pl02*hioz4a%00YA~<q7'
    'J6fCXq(g?_4$Z3VkWrlup?iiT_IsHj+l$2}iLD)XB(eIMI-8_Jn5*>uD;@Nc`!0K0n)^PqH%m(Kld4?jX1`FXPu*g3Rt7k#=as$d'
    'yp`+8%F?K@-u+M!XtI*t8>YIHgizdhAUTNE{7t$cM5i0_fV&~-H*TfWLrs~gi)>u(_ahsZOVZzVjcJaBoXoKP^it#U*eVatd6LfP'
    'eS9>M{-(aaN@`g%#CfmTHr(u*(@Y`n!}ngvLM(>jvI;{nxKve~e!juzGJ@4?NNp$?ytRCb#)aDo8rC(pO`-6_Y#-K~8qMV2Y*^Xw'
    'X{vJxmW)H{Q;&GW0T(6XrZvz=4efBQX!Kk;OSLp-3zIbsCaOis23%QwX<!orJ1arI&f((9{et3NC}f}6yE#jKK)ukslSdkq#~^dn'
    '5=KK>oJS*D(0#~*M7sC1(N&9G9;6$216y!h_(xiVZ9$y&s9)S?+EZsdopH+_BRQ=tQ|{AMEmN+%JvhlR*G$P-6_H%V@4SjgF4A|_'
    'qdaooMUNuMeOFy|$`d5_)F~cVU9%97P@m!zl2RUuK9zVpB@f(mg<7AiC^-hs-lg2Kdp3TUzI=H4^2r0iKSXKq;q(31?O~_WN`ooI'
    '5E&^sCYZ2F7iY9|B5{PCd^hZX<fpx7U7nUKBhP@gEo47UfEfm8cWJUQ=jPRfaom1R^MbO78e)&}mDUu(9G$P`aBD|ujv(-?J4`25'
    '0iAxIeuv|BfM~)ltp&2D$rq#rvZuu(yxa(<M~)oe7x#?hy?5dOgE3(|(0gCoQumpHyy&*jqNjsH@FZjbec~)uB+*6SxXAQ)@b>~y'
    '<qDLfkq&_FMndw!Q@b6uQ`?$usY_w&W}AkXwjxvF(iTdA_<-xdoG6`9lS<dDD!o`t(&i9BoqbE`Mqac*geAibVp+KdtlKFunPXwP'
    'AEu{Hw3sD2_9cNNuICgl0~t*@0!Y#QlOpR`ng?!`E)7AQ7AV1FQX|9Ju-Fr=+L9r|^E<;viNjPbEvaJOp;M75jlZ#CE~|>mXyhJ?'
    'orK{2<Clkc!h>z&mOtb%f>AMD8jd!L(j?OUf@b-gr&p@c!=RLE^!)0QK+MqtSEu%{RB0F#CP@n-$;3n)4uCgw2QoSeAO+K){tO74'
    'rs&U#!_qm`l(%di0+pyprO7beXzz;blBv&&5NeEFR1~pMf#A9lA?4#$g5#zzOxPk0v~3Ef&AFeBHid69D_#nUqp>wL^@&u1Hw_e3'
    '4){KBE*phZl6MwI9v=xX+MUopQh9cRBXduJjV`SvrH{o2fMgaftEz5iU{LkYZC@(Wl3?WO4P=N~wLGQRSeb^&C^!(5)cZ(TijOi;'
    'TwQV&^Tygew{Shm60h~teI1OdVX^ym(AKD`DWWlkqzZCJUk}(x;&uk?BvSKHP;-~Ws|V{cfgXljPPhX*H56Rrp{Oo7LT8y?8YO_z'
    ';#Zkq`~cIXD%#M2ic^(ykt$bJ<sG>cS!Z8kvDO+&biz-ygYnc3jUjH(e4-6+ts{b>M;mRE%^-21yBzJ=7-7J<E2<nu+CsXNji1!Y'
    '66usQ1V81ifZj?PBHmoAYJ&Yx7H_p?9DLQK>EXS^FfzQC7{<T-jU(YogIB>uPAT?`CB@zYL0>_MD^2Yb0K9ahshk4D)VQ5Ua~r1s'
    'SC1Y7jiga67Ar3RWycFZv+)AZ^2mxa-@$#<7=>?}`%@055GN)pc3h<6dN3irdxsJhh*Xo7V46f^l(N_wn9L})vIgedtV4F~K8p@D'
    'wv1e~6_K{|bh0h&wzRCKQgff^c+J?bx3cupMfzC;W7)(hU7V?;i(8ISxm*M3XE_MKzRssMGhNeWwt@}yAuHPWe0f|2U{KnYllRPx'
    '<O;!+!rxMAt<=gP>Li7DKfjj>do^?3kUY9PC{`tHHCC%RGND2niVYmqJ+dol1HK@P)mhCp3f)4TI?<f8K1@2iOztMY7!koGsv!fA'
    'ON97~?Qqg!OXD0Wf<2mxwJMdZJeH4xR#5^IDbW1(Hs!$Z$|LKJ&Vq`Fwrt3PAt01TwAJd(ntsS|crCU9vFlR1JnHpTH1`3&Bn6Bt'
    '7x2wP5o`m1<h+Uq%nQs{f4fV;Ih98(6`#L#Ii+aQO{BRw&F-o^yDMB*Y|W;*EjLh;cJs@W2F)tlPW^XWh^?u0T2?jddPOT@#&#8#'
    'IJB!MABTKkS8-Q<*4%~>52%Vzn4WD#d00!Cj&nLpgJb{E>7W#E;Sk3x?Fdh`YT|lFmf@0v38>1MldYR_>zKOc!<eGHV!7Cg%I6X>'
    'nTz4JR{0ba{1z&otEb}mk+7i>b5C%)wGG8ck@st8aJkP7U12*bS9z`vZ9BETO*>6>Pol7)M&pLc#;0FV{3i8&4YeoVZk0!Kblz5#'
    'k8j?2TUCq>3AYrZ7rnK)-;dtf6oc^XgE~p*EdSxg;)C0@AD*X=pC7gzYmweO6w4s&B!>Kv#teL+SBwK*y~9b@`F@q@=~uCeX9zBC'
    'PcMtsj3UjNVd6GxhKaE!iek`PW*@NzyQ^3*z(dOpO10UjB&ar30HM#14-X%<Ppb#U$kZa;MkC9`Y1?@zq${3Cqgq>!YbMHLc|%I8'
    'JlLbfXt>WO0=`hBKJku27S8T@HM6$lDN6g4w=M~w9tAaaJbGKaN-6GPMXz?WRGu*ulM^c*F#g&0J$(gFQp#g3pxO;zvpogG`3<hZ'
    '2~aeavenc|8iXVt*0*ig6y?tqcVgNYp5;?ffEb?TDhg0Fs9GNxRBg{6)H<RcYPxBkGjp1S&f|xJe$${%I<>>LAh(u2H`neNIFD!F'
    '2Q{5do*7d?JB(X?P<;9D)(V_m9L=D|C5)#;FoVl>`X5^f1j8v2@Jm$*xqP>eUP~OTJW-_tQb7ARBA5<0Lg*<><Y%vt2w}*GogG9+'
    '7X^i+P+0uaxhP?I4m1ab>tGO?A5t3d77}Es!^eSk(WJHujk%iWQeHBWt|APk=r)0(dq(Gyu*fqIA{AX)q3C{XyKHL^Pv^NLP+_(m'
    'NyNy1g$v7{r{5mGy!`d)@o@jJ{qfHq+1;Jot(58MQAskwS-YgdCGg5-OL8*WUz$mY1ID`**BMnA+<^0zno$W%H*Z@xEoxV147sOj'
    'L@em~APHColG|p6b6T+domE|+k9~g03`<Ieh?0O|Ny!jQ67Vp&Pv{=<X8u?uB^yq?6mTo8M-(Y8b8!`-0&rs~sW818lg%TAlFHmf'
    '2bDpFL>&}LaH*><2-pQvb%8aUwJy(%x?uTOjaG!T%BI3WAJYa?!J)axQ#WbTFDXsJMKCSnMG(P0%9AgiaR94M6pkYYu+zt@LvrW4'
    'M}6n~$Qi6cAgsX|>?sIQ@%Z>v!A?Ioeto#<*V4%=&k#5=CM!3HXAiq#uRr@$0N)PJex;8F6;R61v)gAdV=pOI(lR%e6uf}Xvm82k'
    'bmuLNaERPgo`%m~Niep_mA9f?AXI~(>WIXilf?Fj4JaJ|p|$c%cu+V%J>og%u{RM8W9B&(As=vV;r`H~IH@>ocO4JPG^NVKWkwk-'
    'hDMnf0y$36>sk|lR6W`uwG-AgkD%_e={$leA0HV%RJwhEU*Q?FbZUiP;pNtlK`X6q@(S<j(PImuC(A=CRjh48&5c&76{iAoDIdgm'
    'WD)d871U8cuk8}C!voc=snpP$I6NqGR(Jy^E*W~;Atj_+7Q=>DUNJ0wufn0H1#SA_(B1cOXcJ|G09&xZK<BOa<z+`er``%ReiHDp'
    'k<qlM&a}wes8J?R??7{u2dNAqNVv2%QbZnhjZjJ}yo?wWqUC%UX@=2RlmXFM1YPO}aXdj=Di6nFLFON0M1w@h(_+S#Qe#PlQt`IZ'
    '>98&E)V1j9%I(~xzkM%)y5FZp$kwVm9Rx)!rNAp9d2*x)^`uqV%*>V=AcsetlJqWM8FKiY4zp-foEn=lMlLFdR1s{}M_X}7HZl)W'
    '8QHsSwQ&!7=(y~$tgOV3lKcSQ8LY(UztG^tyUv*SzG@+MGuq0hgE^p)S0J2>V6uj#;(jG~u2T(9`jn{{5*fMg=Dz6?eAJERaZz_j'
    'qRs|oICg0B;v#RQNSf6NvZJgK@MpWsUGmQ$(j-3pmLD3>N==Wpa;B-38ET4F{DLqR7Mq;RTFwDY2&pE1Djn4%@J>8_N#bemZAw$<'
    'y&*2+t#sIBvG_@Xz(mSGhvo5Uv2j}5uSC^e1KUe29R2w#>}g=R?)QZuxw-#t&c7SVO-<NPZfe3SXeVqZm)~4kY9d<rZ5}Ma+xytG'
    '%^IvL?SnM8dbjqtoEFyT#PE!Mta=bd_qhjA)Fe=K0;OG(pqF<oC7S3KlAPP8H55bU_{v-I%F~!2o`N6+ni$LwPi%wR&;-Q{dN<ui'
    '6MI#_ijD!7TdSI;r1HC#>AULrZ@cf6X3OJuN_rZvrnDOj%zf{Y7HS{9c@%NkB^s!DPY1Hps<)0Pp{~lTDN{gT9cn+hv}`_YUtd6U'
    'ard(dMx(&Gp&Y|#h-qH%H5E63(YShKt01SoV<;Z<%hpu3{#khj<wZsW_xq6%K~n{c2y7dvYH>Oegv0%8=tQll8ah#HA4YnBRo5|Q'
    '^tTn~J}9->^~-1+lZPO)2^723h=8-*hfPeUhHcH`7Tk6F<A%9x@VMEQ=p&DtHAt`AwayGw)vUbY!kfo7LvI^hfrq}$;Clp8tA}j_'
    'otG>i3FE=Tml}gujs0Owg>zb6X0=BJLCp#PF<n}^j3oD?X<G|hTbdY_UA@o|kK#jXChSO^)l3#fFd-Tzvw9^-nYttO5fv^5bnfWZ'
    'nuV>48k3e1Lt8fhrcGK$s=*P1`ZOKZr`b?ncZtA&!p-P@9(zA;sq<R(7Rt1uQ8zeTU%79UNj7y9P^h;@R8m*h_247{mdEdw2LP0H'
    '$%v)t`QD|vzd|A>@P&Ze!|`4(F$k#p9goxvWl7rdPM9nAEH?0t?E19kx}ja4&+K^B8%tGJ6n85u5`Y8GDUx-SV-4MQwCAuXJ{*hp'
    ';aC8aT64%>?T27?IX0XFoqc|qmeg<o=fO4o#NJa$PH_QI7NOex@01K2N8RZ#QjPQJkd$MN-Ovv54IrvqREsfB>)J<a9vw7XjSm`*'
    'AE3X@8NoGrE1T9sLz<=iv*_!LM4HEwe4i@4oLB<lkegx2$V{ZU6=O-st!_;`>jvH3v<L*2J!vWs9;K3|f)wUI!H33x*qMa2(}MDz'
    'G-bF=jGU6D?({k$O$8@IX(~8v4qM8a!&YQh7$h<Xx)OWr7Lv@n@Ga6&2;`T)z{6MsB|JIqcpFbX|AZ7rMUjx^geVe<k3^ABNGzW?'
    '5w>(92&HjfpUez(KcQ*s{wZ_fSVRaj77=x{UnnAk`3^*cu$73=jU8D_LOM%nLE#OwB!KgIcMtl(U&>M{rD(!=<QxGR6kZXDIiuuY'
    '^tFP@N7F5WYF&=65J_UB87+C&j<hPYX(Gc+SDZ;9I}%Hv3sEGK$-hT71CM;_Sh!^M;GA=tp6yBo*hl4F>po*kmq?$nGp<aZYhGga'
    'N!Ql`88qGOz9(0>ZG7BXn99*@OKRXD<pZ9dIQw<d=Vhc4K~cipSNuo|{O6u*%wp8|(LqZ~PdqxfEV{ZsLeEaE2#0LIJDY^v^-Y>G'
    '=u>_!T7_VWSy1INNUEhiUhvb3OP6q5w-e*aXc|`!iaPP`p;fpC_TD{Q8j#GAoVaZ=p01mUYk19qFCW_DtOn=15@dK)RN}}@O2MaS'
    'Nk%Upxt%n%Q}nJ<D@WqN6Yz}QK9sE2A3XJy8ow7P#ZJ9_C?&^lA4-A89x;4<&r2fdI|{!=@9dJLJDQJ`H;?@q_D1VQgvKpe(fv@A'
    '1d*g-J=F=4J7E%!9}w#lX(TG>p<Qi8SrjmKTBe3vS?d5FNjrZj{-7jfuq{g#YJ#Q)7BQD1qVUkH<>gxNpB3mAp0B5=ap#ICRk~gB'
    'dMt_dkf?LAt8*NBv=7;NPWIr2e^iueY$k;MA}+0U)-ow6Fo;A~=QN;(j7#&;B6n}$r?|6!%wAa91SETy*dH=O&W{4x+)bc^PA=3i'
    'B8)Z^yfw$PTybFd%iZ7rU#WdSMMUfHL)=j&50PQRuv9J$hc5!I^4e730t<h~3-7m6^-t~7Iqg%ALxOJPh4W2&$kF)ZHev`DuyGT6'
    '+M3SEEpoCsXYoajna&H9$?t&S^#0cn6u|ro)Dui~ov2Unh^mPvxIA@&^L&DP$jvDFpi69t+;fc<7^c*zqnqcW+gLt4x=jdp(L1`0'
    'Rl}p(STjDlJ?aOv^Tg53^U-Yy>m1z+KDsSI>)pb$&Q_FD_~^D&4-Y#Vs4<Qm-JZ8*cywC^wUtvxcjg0ezf<k$oV$a!_D<MQdc)bc'
    'HyqQg0I_K~a-xCT*9r(km#2<yo{w%T5X96hRM$$q=dKxx1}nuWrQRyi6AdyaE2z|)tdGb0lXWW68KT3Q(c`u?qObTTv0*C{d@VL?'
    '40RL4h8n`1(kPoGHmsGW6o2ojHj*ALje}jOPf3r&bYWtYyPotgo~))XJzSC*Ne@FP8A=a>5I|}OdCKjishzY#^E}N6^kfL5BgNkk'
    'R)dHp*i~jn`^}I*$aqA0xGa1qJxq#w7P@@O&dHOZ(-7Wy!phwdsH^*}zw{<}qxE|uTBXaTB;*rk%MNq86>#kp?%H>v6FPUoZT_Q5'
    'xAF12pl&}aR_pdAlJ4~G2F8=_yj~|a#GKN}jpxKUepxZzYyb5U$52|o<{FQ48EAbjZKN2xq@H4IC_7Rb8!E;w?X+TSC?6`u#*^0!'
    '6l0e*R*Vf5rxatCWvCdtw4q{bs2nQBE)6Kgs^Mp=*KvY|y5EfyW8*<7!_&{Do>Ghr)m_Dy=j3w~V?)hAF*ej5QH*J-%^p>Z4I@x7'
    ')~6r<B0&I*M|O-9V-w>9b&oa}CP?UpW2&xDr=!h>_Zb~+jE)pz!{|^kc4=e9*xmF9Z0CuiP3UyAG1gOzrvp0L7#k|arlyO*M;qfq'
    '#n>=@N-;J}j1^<UpczlI6T3;sw3`^-*>3T{?%=JBY+A-g7#j9Qjud0VBvOn`F$=ldH&l#u6QHH;gvgyxSTQ!+Tq(xJGuVtpgNKtG'
    'SBwoaUB#H^WTY6g%Ghm~J?og_Bh;r$87RilBJMIARg4X%P%(CQf)k^>B(dQkAg2^#&c=$d2X2%lI-imrTaq4}jTK|ghKg|vZ`73@'
    'F~m_{dc-(Kshy{!$CjiA@5MivCWE907h}bki(`th4{kKtZ;@c<nDpTCh+@noP>i)bweb=v+x-qJ#sqao(XsU4YOEN0EXhDI=BibU'
    ';|}8*D#rShrA^Ga6IwuEAgc*)>nBo`e>aAt8;&9AW}X|rRl{!sNq6<&mlg*6R*esb1RHu-8w|7&<R*TDM$iF+giEO~?JRxo^5D7e'
    'T^>9mdc-Hs=|{aFr<2tXMrtBkP}nMl)ei3WpI)}7r!Svhc23LbW%&ir$r-^_uLdPi4T4`#LwIy=Y7nRf5D4x38f1#03Sq%^<){V-'
    '4|gZWYibZlkc!5A)P1Tvk|kWi%HqAIb-RT1O+1o~Fc^*xd|6!@hU34LVa63S!sQzQZP#Z{ZHG?JeMEG6NxF-GEblR#7y)^k&u)dp'
    '+|83+N<_W1k3GT$<tYKNa|<O!<lvCU$iz5Nfgkw%7KW>Tx@tq;Eh8De@=}zhE*TeQs&Oe8-X!;YRH%VVoJ)gJ{4#zkBgKdV-FV#3'
    'o0p(xVG<P)ncF~fOqKMK0hFhyv5dzH)vG3LU>O74&u^+7Gg<63SZ(bZ(Vao^XqP50s9j?pd$ceN#?Z_JC~DG32z&HqrL56QgDA7+'
    '|MmZV+&(^UFR4!a;=I>sQW7dP==7;ntIxSADPoY}Y#%dMAO%r#jG}DV3l#z|^njfvhS!3(trhYU86RY8K<920<Aq{A0R8jNm_i0Q'
    '1M3V1hG=1hp@mEY9AW;z{5uYLrOaHDi**;s5<QHJ#~tCIzCXlpV)tdJE3}^hi%4a~187z`5gDz`{HnE^Zy8F8p-_uKysjhElo~O&'
    'xg?<W*@oAs+X0$w?+Q~ePPUD$WR$L@(_G|3UQ(tFC725^Ksue@#A9rXxq8gTIDJKF@{;PYmpm$22dbK5?1v?*X!ZM?NZaUXNwjMU'
    '@l<CwUsJ#w|F7NzRd}k>{?rUjFk^6p(+>AB$8bRfxS9Kb-<Eevf38H33ueJ%pz0ASB}<?(y`g9{!7z@X(UL%YYQbq72bDo-`l3k-'
    '<f(<3k_FnXq)ch0n$aj}_L6Z9`1;~4D*QD~!)OmiYd{lf^{cK>)X-dmJ!!1drn*!CT1Ml!s^Fz+YWb{;wzs)d#jt8!;o!Ndpj}G?'
    '-Nm?DLJ3S^N??kdfyzr3kO|&x(CE8-MddRZy@JyU@;e&NvWJyj(gMB*tuG77N7+mfIARtAH#xrs!BE_1(+;9+DVmm?7A-n2ac8H`'
    '`%@gaJQ4;p8Kc-mO;-CMP)Y}f#deU)z{YEOQB|6k33dm26BXMSb6Ex9k-SVW-3>Z;4cW_vD_-!?tv}+`>RZ3Zs*P^_#-gRXu~#+Y'
    '5dAuhCG;5CCWU01#x}^7qN>F>YpETFSLwklu}K+Qaoj+@U1KShigs(QrIy`BDq4P$naOxAt5*a)NE^=+RSjqcT-sTW-_{d7o{?RX'
    'QwU~bHEJEC2XScz-HaG)IV6)xGCE)XJe`zRKDL)FDE;a4URjh}rJg_(6^@&Dk<4k9T(kj#at*JNr3*Dc8_k-vsPDj`-_0}J4AbkZ'
    '1}vEk+|N%?`7^kFEWuZ4xPDxkYG!E4X?8qAHiF6046P68vw$;{>tQ&e-19wb1Tz;*kxc+JI7PV+oDZkSCF*91@(<AgJ^6r(ub86r'
    '4CQ{#8u4vCgH$WNEeY`wd*a)rY2bZ+{?N#Np!7aPwe?uDquB`qS2s&SG~th9ifT(VUPH)EV|~cBS5RW-?6${QUFx#>SY7t@oYgk6'
    'GIdFhtfywWU`~8sw%77kTgr~cuCO#Ps*U)oUAnxet>VN4kr_@9l_#>J@I2Nd!;Z`+RmbL&y1U-%BL`WkkFcRz8V;jwkQkT9FB(H*'
    'TM?9-Wl_j-h~aZ-@L^)w=2wZJL~39?lTd90jV~>h5kyTn?_R(fQS(?v@I@TH%36;CYrTNo=bjg^Wwhr7Y*`Z@*Rr#?gDnfFkeY4H'
    'eXm&9MEYL6So8F~%P(wMpI_LrKEJSy1VROA16`*r%TeOtGq6Hjtd>d0H?o*EJR74=Up{^K`Dyz6%e~WQ(|Wl3_+Nke%TMHk{NKO1'
    'b$qvToJ956Ml4ocGv}ygW#6G@-Fy00bVD^8_6{{0)2mrpRI`=WubC4RHh5B|VKuQH5T>&gWKwo*v(Wcw8}<PRw9X=>wRF&FM{$O6'
    'uL1~2UI8o(P!l;v7DjK)O3wtABNo4vg)7;gU=KqV_|MzR-N(PDE(C~vKJyeDGw}{<*oQBx`<MG(@#JgNdCb3qJCFExUf+4_(G0C_'
    'E)7LW-AJ%yQ;AlU;iK0Am-Y^_hvNswJuGh?1S_xhP-F#x<_Gvt<dRt7+qhD{1c5NS<%xsyRZu!yF@j>?mxL=u;O&W4j9}s|D@L$3'
    'lv7#^g1>{{^~65S-A4qLg!=9y0^x4=?&Bd>*Kb^fo<;*KTRE0zt)k$<vxb?z-4fr=IEXQ|LfJRXo)+UaRai$wV4Es#d(=_Wp{<gK'
    '3ANY0ZM9k3DSAQ2y(9?U9$*h&Q<`lTkEDoIIo%&5rDz92#X91Qa+(0U)8mYI1!qb23(4TUf6*O@^y)>I@cdTdfH~<EISA%7VG{4t'
    '{bbIg!a>NjYc-0C-rI83DAB&omNaqwMg;<s-mCI<&};&?M_Ii=GL#0M=@x4*XqvXEY4T(QXd9!t6*Dye^;(Is1V(FFo2hL?{k*rC'
    '+DbEK3b)c?Ie37buo`!weSx%!+$6rTt7ljC3gfG1)AlkjZFB`SXt@$~!8)KRyr)%cKit7H2ic#fvuVQPh?2G;mxH{d))czgsz7J)'
    '_>|9qEbA0kwNB`SVM?>Z^Fvjx4e0z(M-EDl9D)}dDa%SuS88|BddvCYAw8x#N-ca?vr03VV?SY5oWqbtM@~0-kH--J%0ZJYsEnr3'
    's0E%0ZY8LE{|v`!C)o|<(cU?{$ur?R9uME<L4DD@B9#Lz)e&2^J8Q1&f_277T4ox@Pp7nZhtQ%0@uqp#0*Ky~U$EsEO*>9k1Pbu='
    '&uWRCI@DomB$8G)aq6%hoMK8_*5>8eYK<Rb?qN>?Yh2Hb+j{5-^4kI0fsb+qYCV)%(|M>ZWZv}?hSr!B@b^<e6C`_=Cl;#r+ySj+'
    '<5V<I#%!9N8){$~uID9N%)wNXW5Km>q|`2et<t3d4L!C|;9m>Y*f-J&F+#RI#I2JYjZ!<eM$x7WN^le0EdUf^JHw<=H<quFh_V!6'
    'DtFd`(Xa-~uKDxc0{nB^c9c@oNSmptlj!$ZP$`ze4dosF{f4UKJ0*Xee%}5z%@5nN`gMD{Km1nh^1tr?pytnyuB1PFzF+>Ze!Sn='
    'MDOnY@~8iP_|Lz6`1tpacORCAKmOOBe)_|QySw=(>p%TIHA9WA{5Hh4h;ryU!qGyKjIz4GR<sQ9(V}-Fn?-pxNG3`Fph8+Muix%5'
    'A*f4}BWS(#=z?+?TG#o4#?0wm!eV67u2`g9XfZV*WTUlKLIelpy|@`-`}%oXUbgka;bHpuxoSpgfT9?iF88}(z^3PxVACBQ7KQlW'
    '(=8w-YT)a$kqe9#Y)eK98;pMOT!5kYtcPD@$zGOY>IJ$^P)<8q7~G|D`}FekTehe<nRf)^YoRV;4Z6KT9|`L*6vdEptu<{8dY+2W'
    'U4!cHF{2pyzU$~H0|F$i+jc>tmJrIo7b;F@bS@7Y0cLy}JR^76JQMU|z8{g#_v;Hft7EDV!^PlJ&A{ElrO7JXYrZD<G}#;~D{hs?'
    '4WMpMl~V5VXnFp9!2K+E_(M|Vys~^MaFO231^0ZeY_1XC;Y*lRmuB%5Ue2|y$@X{W_t!OjJrW*9rkQV#Q|Mp)e41?LJ9mJQX1)(-'
    'zWuXiJKqO1-}EhyJN{>_+|7*^23f3FdpB{JWP6_F0wg@oHhqC`=F+4VE7J2I2(1bVw9llG2LXl7CP^ewjjmO@OHE1B#n^UW7Z}?_'
    'q^|R2j%))it%9KgwhEs(vJJR2%ic8a!PO)Y2<?4OQ_4u|{Ws?{4jdq^G%$=vG+Uc2JOOEd7-h|5l{9(v$@0(&+@@l9TT;CYEuaOi'
    'ea7@V3>2o_0X`xw4f1d!)3HyJ1OE}91`*5GYACj2Pha7vK|A)ryT!k`K1y?a0ph!OWYQ48;_}I1^k|o;FbjmFb@XVT=N2pwt{&ad'
    '%+mk{H~!R4Nt&aG8F(|^;YOYSC(6l`2MZMmduam=bb*SQ{dJp|SQ3LJ@j!B)8QmxWjpfiu{dem_EI^?Gs2FzE2T#IHA+d-B6~PQ{'
    'gMnpm)@y@C1#mlVLm-FCg)`Jap?ZZIRCw>6m3}W3E*!O7kzU~z6^<i^<H9w;WP1k4a?kmK5>dA_aJ2v3oNAs?%|`ZGH=#V}d{W}j'
    '*)ZncpQex7{N-@ip8h)h_V75lOUskH?ma$jKn@)4zrK8V+TwM|7p<X2CTj~3BZ727LemA{?tC7LN~ujmE=MN&M5S<43Zt+T)oBY;'
    'ol@olDur`YN~bN{^h%jgDFSJ#y3-a(dZplTk!W;vr!BpJ+jPd`5)5!zYwol~cOJ*-w4hRqK&5orVtZ|wBr3%Y7(<-?K}sM&DGtlq'
    '&m_ApzfWcAa3&R!m|5@5(rCI84aXi2Q#wKP_R1yYsd8$o$}J6bqv?^+^KRO!7UF`cnMhT048{SEvOW=EraY5SbH;jFja!_tQuGju'
    'RIg}+B=C-uMCuEMi0f3d)HqOTs9E840m52IqAs{RxsIlal^*Lqo_7Py4P))xXnUKvsi?!Wrfpj+UT93f&LFp3t#JtI6iiF}_w@AQ'
    'BWW4eiuE7U)5iYzc=zYsN>2a%{_yy>r~99O-k$E<HS6w9ylh`z&hLw=@TuXA;vQ*i3bBi6L$1(V_36vU+5ID(mx^L*3emOSp375('
    '64GEu6_el1kaA3qL=JO1q+GxMkP6n?@lyQ)J?-j)ZH-q71*iVDLn^U#!kYbIKRtH2460^kT!8^YMJ|B-#wW>g!P|wL=F}!#5moz7'
    '!3AOZ^1OkMqG8<3&DJHZqoneJqh0ZIw0l%TmvPf4!T9a}3|TdOA^`kKv0X4ocFBWe>&RB1LMy--vRrVtmlMhL)iJA}Axo1%Fk_#D'
    'BZUbLOz}D}{}*@}g+D|Z(%}M-gIv|`Q=t{efq=cMDL#Jqyfu4Qvs-{1d_9<cX;)m!xH0UEttW7}q&&O{AXlD2Gk(kE6A01mE`9EQ'
    'DT#rFv|aF|BqNuuFSACH*mjU*b;d7nmLwoE4|mjwOdC|9v|`_jfYte)9_P`IZ|RFB?|xco-M&KP`VGOS6|K>dK9Bxx2GceUzy4##'
    ';n#m2IsE!Gz@8(ixIiK+Hs{7cTT*aUNR2ThxrRl}WvyATd>&gi8&&HCZ4zs2lc`)J4q)yL#g{T}TE*Y6+g!>Ft027wHk4xxmP^w%'
    'RNUr0&<Lmv(;gt3+V%c<dHi*I+SU&*kDnhO9)JEV5}3LIf)NH^KNkw1!9I@$E8#k;(^QHc1*eHoBN{-Twm<$ZpTFF%dCQp)MiTQ6'
    'xX&5_;I`cYP0@R$32gHPOiUOfK#wp6czw%dyTCNzW-!?%Ocn3dkZ9HhLlDSg`$G`oDOE#YE2*kA_=zPDezQgF=9&`s@}Aa@&ri8L'
    'OK^E~hQ(1du)Cd$p@Fr5exfR~a)RRUdC`VI%BjqqpoyagXv;>9bv~`7m`~5JmgC!`02AziSLg~S%k?OrZCsull_iDfrhG;NDBvys'
    ')vupcj{L=ZT16CY;83ZNznD)0_oHZnWOx|g;*;clHuOpIX?Qa;G_gaUB%juD4JJL%bGW>vop2*$JSG@`9W!)^%%p_0Rd9o<2pc57'
    '+wL<!d7(1!S-`VxqI@ff@UFqw1@}cA<B0o0?eI{ep27tlYHV#xU6k;f+%+h{t__h!Hl@MUdy(^~D@=%iE#4&+kdb8ck~1%oGx#!1'
    '5pm@xg7Y4n5exQiLtZ96gKi|RSkTf_faUCJEm!DCh&K-?E=LvXWOGfo1RSQ+GslQT!kZp2^X~&Iazr~qB*^aG(`Q=sY5W~}YtYjb'
    'FAqH?X0W8~Y&B69KoO&iSoZf=6DNv7KB#Looe~6AW;Lqc=fM6`hXYA%&siWB<JDS5^+@5PRiw5MpJd62NZOi4*wR1+)sj2=B;HDD'
    'f`7at#*5J|K}K^C*zE;iTzy)w>dn_2rvZD@&aX?^{$JPxh2qfR=7lh85DvRXqA3|dkhOHoT&V-vKyQcSOT?hGpil$uz!)j5URBbx'
    'WMM*WdqzCxAKO+3LQBTST|4I5;&Q;ix<!Kkeel>Uh?r~~KU@}e+`q)-2vlWxzmn!iU>v?oZ&9DYg$QWBmt9rK{>S$5@#(k!m_Ccg'
    'e|&nr`<Tu^&rdTr1DOQx(N|g>3_s|%vemQJ^bg52^-QVJ-H3W*lpFE;5DU^RoMo50<cAp2FD(%kysi*Zr&NI5t_+-X!{Bx^u*g8q'
    'AKxChyZ};WVt{C0sIJ{d!gfiQbIL%N5y`~`W*VpSrCI|)RrYmQ0CLVH!sml4EelRq+s_I1lau$THuwVs37MQi^E&W|u<KV@y={V5'
    'BFY)&mR!Kf<CrM`1S4>19I6tWT>uX-M5l&w(L@f+4GpK}l}AR16C&3W{nR!BWYD1=<977=OMRd;nYXFnhYMc6=pi*7>&HOt$|DB#'
    'V<_lL=QO4^sJQhH<!bD*>gFz<*MebVcM!@$aKyzW?{kN!VO+8$$V+MoMC&kuhtGr#&wUn<YY6p-w}Gv|rRk%d+%5-wi_-}80ma50'
    '7i?(0pq?zJxfrMM^ijr+U-kumi$TTdm11xbrZpqNa?ckgC=P@~df)ODr3HHwynA4+R|FEqt17OdLiOyIqJ7<FBZI&(b$}<YPb=_w'
    'w=FLaVU{KlCUmDsL66L1Y}z;)B@M(`xLTWxKDJCNy;s0xYLVUpUAd@_^Yw-`C<#B(7>^ws?HNfc%n300QAt~`Y`kYYInG<!%SPH`'
    'nll+35c;Z%<N(Yj*d@RRl9s*X8j0;0)+gxok4YIWon21-!;CL@o-XJ54G2#+Am&<q#!4lSUr!0w;nVbqQ@)D4HKAW?Sp=6mF)vVb'
    'Bv1V@^u&!r8vGcd&|<f(YjfT~7CY7RwK?rPE)Qm5&1vcxZvgJN;g@hZD7qtt6B$_r6+_tN72LQ}8645O*wq#s#GLcAJYRNM8NfPF'
    'g**|0cHr`Glm}{Qm0(daVaq}6Ub`#@RDgPuil8)_su`X?O7rGAk4*x~w6RapB2cDdP{8x-u>y^kaAh#im_$jD6Rz7-6h7eRhsT$@'
    'U;pj?`DyyMh?1fnUNmr8cZn3BX~a5RAPwg!RS2DE(uFFoF^xFbqA52gf>7~N(hE>x_K^F}@F@l2>i9&=YDHLqZ>D+G{1&WMzMe`2'
    '<*=a`qNEQ~16QXJqV)a^t$o+fh+^M0eUPec=xu!0sMh@m#y+Ku#1Wt1Nzf4eV|NyM+Nerspu)@vMsjRTj-Z_TPrp8V{<&(GAy@)0'
    '`cQ*%sEOA5On^Xf`96%2sZ@U~#SDo3E~R8|-)0kMzfWaWV1WrN3d1W**V+K=s6i;{_gfTI2&F^g!sFxFHdc?4CI+-zKFt&#7N_@J'
    'Fsv*Y|J*P%YfI+007z`%!|h>A5?DJSEW6L6drP&f(?ITFV{X&UjcTVP=C%F2Q!Y7}FQO7>$?@!QO{WE9Dbg6zb0<JxcnW!Bx7b;p'
    '61z*9BFhv6z1ex2oBd^ZP?*D&PhG-qIm>hkS#AfbF0FqnG|Ev_yl54-QsVigbudEaDF_>LL9RflkxAR*K?Wvm8({AFG!MZT((T6T'
    '4s$q5X}Z|g!<$@A!bE+vP<Z+@j`3K#`Jkj)bX$#=^&btILECa==K{i`Q4AUMWKoiBoYP~PCtv}$sOxNQPb&i30s=%Z&$R(>Kn5j&'
    '3(&Qi!jPZ*PBoP4V*+f5YgNbzvU7{FioGi{dT*sD4dP_wdI217nniAmZI*Gau=2UKC{0xl>EIgUof_e;f}jQOc{f&)z1P`LN%rnj'
    '@30gVR?GMI_bgn!lS0uLl)7NhXORaT-|>UI{+!aF*-fbn`Z$Z+M~#$yJM%)TkoUQ1Lu^&&ZJq}UEF3@JV3R(zJ>U$1e<&~$dGHHb'
    'D{uvRKA(b%f#e<@yHG`Y1lpv3{qIp_#Y5G<D}!ecIbEU$ny3f*=SpZvDJOM$&Gye&@t{lI$Tfh;zYq)}d-*gF$Kan~<T9TI9|)zr'
    'z&12#o_d5yZ|!VptuuHlPs_y1W16adZw|Hc>rDek!4Qn<4uUdOUajkCEnsvLvtTb)JI%CN`VnuD2oetJl;I&#JC@OWJ;`H8Vg&Fl'
    'l*BadcEIuIlM2V9T-FPwnbJAUGdmSsk8lEpi-nirJgrmlcgiOK3-*jG<zXZ}pURE}1S23In9Is(K{!=t1s1~|MNt}}Sd||F6r<WM'
    'c<Y>(LmDbx`9=WmT*d_QjnJFa&3b3@CcY7_9$6X6_XjCL;4~n#q*^Z^1f1tBRjfD$j6dH$z)1<mEr6WCL`{%{lPHasJLa|88V=iJ'
    'ItEcReHu{Wn}%jJzT*(+QaS1)>W0DLCn-v^*YBe31s%;R)<Tye)nyn}S&IGb{^R!a$45%;Ki$9FPY?J1cf0$0uE&gI7AFMAtmT5k'
    'meMJmwjL1!TP|MHa`F7~_&Fijom`>ACQ}ZYJYS%Mc`#qD51TppVFr@Shob6x?J|#y88wsz5a#pV(9ZOo(NIHDLpiS+YGFe;BGrU!'
    'o{Wd+agSe8L-(Gfw2@mf<AM!4C?E`JF&9X2rxYeJ&NKTCKwLTX0kVI%Ow|MW{%6s!zp7%UK1^_=lpc>p1sO-K{LI5)Mq{PN-tCNQ'
    'aO7!yf#<{`mo!$o_a-$V+9bxSN5VK(9FA3m8?VMH1p4leRpagse<_CU?yQhc!KT{-flZI>Q|Uz3JsF5jWcfc|?zfjLMg$%CQ7}Q_'
    'bl3|Xpcg&o>Jnwn16;aNqdqb4)~}~a)`3auK(H}!4HKMU)ray%^}$e~_fvfYLIm@Pc73GvPus3^dpGG$-BkUwJ^gyWY=3*2K0SYa'
    'e0sV2%TL@*e*FB`hw0_;`1JAaPCS0zK9$uV>=;zSglz3|b6UqzRX5sV6%Z)22%jt0bRP}%VfyW4m;O)4cW#%|==nTtZK2W2!d5J}'
    '>CPYwIsU-xau`%bdlU2!pgt6U#tWy!$o9bF3m>8xLhke+l1$PTqK6^pOtR!R8MHqyQ<nTHnFXHYsIH{}Y%+-hIPBpcC~l2l7(>xK'
    'n>$4x4eio|H}F~7KoqoUN^~s-#)Txse2Ay44B1OS)>{HuGpPltj)Uqnh$S>nmv|i$lT2>XFjSua^%()`yGYj~S=aNp7=~{$xjxH4'
    'eV4GXQ<7-dU7;N!HES$Ho-jou(xol{Jvd<!Q4j7CNsmA9xEyxyz>~JN3RJy0M$A`mzAJ`gpPk=VoSWTCa(dbB{`#k1Kc-XHT`*u5'
    'Xp7up3O}!AnE?kvl5sa>_4CdsDS{hOYKZSkE(<V1R$*`a-J7A4(Y)_5G8jtT!+_>dG!(s48eL3!C69TJb!<gdb5UW^@M=Qep=M3='
    'sl}zk%U3a*%<x^z^B_TAH+Pt#)Nn_fuG(hKM{6<H8vvlW&6c4=jhn1Cm>Qv**KM-AOwreBsOW12<KJDYy+NzO6qVL&ke8K3(xB>!'
    'qt_K@(s0@8OQJ(kX;b?=*AIoDzP)a<3Rt(nPPwgGXVCp?S*b^wf0({}cnY5EpjCUUmRP&NjMX4qjZed{WC50z347(bOUr~UmQCVj'
    '&MzI=+8UX2Dw~6z3>q!W|Albw%s>V(D=%pJ#&gT7h=}gST5felAZ9bY*oK3R85E@G{cd$tsIgrW#y1EPo|59Lo)H&t)U8aVYPGmX'
    'Xc#^6FlEL7=S9mexTJ41UDA!==*i8@syRN5MOp}SA$4hN_}b=Kb_R6yE)98jiB@^3LagoAlm%Tue1tXlRHs2$LzA)?oMkO%bn1fb'
    '_#Mx<B3=!W63rl4L7Gw)wA_5Cu<z;B&_@y*tTZd-)mNI8W0l?FN8z2&BCQk;)EdChnMKI<Z=~wm3MY>m--`*6(<*Q<91uf$r?i3O'
    '=q{7_4tj5~GiTYz$rfd;8BIJV1jE~S86WO}WYKE!k6<;?2bx*#5(6eDbU6Gj4Q$*HRKtxrR5v(b<eOh{Tq6*NN~;@l!U?);XxhLr'
    'ImzS)Xwfi<`dht^Tt%PZC^%ZrPl*#LaR<oMc0jTBXj>g|9In4=f1<^s)p%`UPW5lJYK&-Bw>se2Mo5*jwGsFG5wgT3fk<I;y2Q+P'
    'NM=4BBg1v!5}XnQ>(%qz@SSo>*)6n7PN5T-U(U<YEN9BZQ1DTvj_W_1@=Ch_AZC-YU^8u_B5^7ZO{i7dq1Jym#cvEyg>z|Yq{4BJ'
    '<T|Q1@fgyr43cj5yoYNY)tfjq?0eFiTzm9rPf!C`V5dv;rbE)3xCfj0DL8DOmQ0`SzG5$@)i%%}&PYYXyn)Tci0a%f)dGzLoKXn('
    '_?GO!t|?|jbH^E?^?ny3W>*K=Nm`qR$Ck4S2LXjw1cH4RLn-ieMswgEk(w*to!go-?53f0>j1}@>X2jPwC{!6nlp`&tD4w$NRiI)'
    'PD6^(t6I0u>YP=q2^J3NcN2nza~y)js&#3Gl)rxn7S3@97Og=jm^7p{O%WVY{@sLN;T(rxv1-=skiLHi7VhC&a7fj*wnHi^A72W`'
    '^t*|{;+kUdm|E73sZ#GhrkYk`+W2R4kIaH&I>R9~-_23ajln~z)^<p(eD@(0gj7S?aO`tYvA)2NBwWz%C6a|}3RcCHXaZXC$ollY'
    'V_LCCF*sZtA6{Z^by^|lcQd4~3t-DVPK&y15BFJn_kkMSr(Ygkz$XI;5$B7Lxg;TTxlk>P3d4b17D(}SomUVpj@VU%t|<b*5)7{&'
    '-7B*&$d>U<%$=?gYTPl?iAS5#Y{jhsJ7#-!J83Aqib+g%@@;xAiH&|Z{{WXpsTpc1MP})n!YR3AL%^g<8v-V|WY>QS<dS24X#hZE'
    'DaUxdOF@VBM=3;e8-C7dh#unG*e0dKjKHl$+XvKy24P8B3!10K>g)`v(0bF*E9qKRW2w=*M#rKpwLu*ahlYWKOC#T-Z8#7FUKzG!'
    'OwB8*dXPn{#+q-xYSb}?J(sFG(no9%5Wy8i@PeBnpSfc6IP#f$aN<!+GFQB%14M{pUI7QUc4;d39Fs7~$TX{@9H6Ij8LB0RrMMmM'
    'p*bjxZD`PIz$K#Rd~HR0$x#Nq3BTJ5fI<;hxV5M1X;x3DIIo>5CJ_uc!gX~Ov7|MXX>t=<Ag(JiOA2*(O>qQO)44Ngb`zQ~u4|@R'
    'c;D64Wy5qHleD-AO_-}k9hrKGFZRZ?YhKHn(1dZVs?DijLshjod1sC4+iXsca)b?qFCW@eX6H7BCD-;g&xk&j;m~{#Db9c~w{0i}'
    'L%v@_J$iCD^M+#BpE@+*khoztf&FpAsaF#GeSB|B??xU$lRgq<P=rMK&hU4hz6<=FrSJGc0XUtwheA^Dn{?6elxd?&h>;xs=4<+n'
    'wEgG%A7L7l`l~q_%_2s0N=J@C(5e{dj;twh<V5U}K#0Rt$YWKe02=O)XEN7|i8l9JbRGl^>G@Y_URgRfsq{bq67N*LL#SI?!+@iC'
    '7&U%g^gl|DS=<9J;crq)gO5=9oM%3Slg^*hA~FhnPHWB>U-r{hOhLx%+bNPUrX`%#u5GO+xt)P8u@e@G+dwjpc#uI4ErDE7t6;C4'
    '(&%3A3P8MQki?kVNS!*rwQSlT!b5<ZG_;oD^|W7zaw21Jv7TQ$YXdEW>P^akJvd|A;{1B-Xnj|U9D^=R!If(LLbYp3v!?<ar1}Nm'
    '9@vC^Wd|v<sfWV$$v?T32zzOOeDe^|ngT90NLmmmY2&X7u(RKAliAYaIw3>hj!CgGu)=-HgG?uoR)AZL0)j$NJok`H?}gwlpA%L8'
    '<n6cr>xlK%2V^`ad(h&my^Hb)4|=R)d*7!l<+|?jAr+PU5b_v6D<}x1h#U?ua0<_USB3h@MF%uRTzD%WXBH%c7VY^$2*RK_V_jZ5'
    'vnde0D*!uMP*^dCcAPgX8&?7j3PKNM!3vL#1gmm=?YTl{lZqF+_FKiNWd8!kRSdZ<1i{XHa8U|RfCpQyVVP2a@RnN-{?u={$m1e+'
    '|F>g0ksvt~YVuLuyVqZs%AQ`BT8$T`X=2djq5~C9cVVVzEOCqsEHSt!q_xvy0`HE|mWRmVNC>-*m20+f+3&0=o19-e1ANZK>ocT?'
    'pk(*T>}mjl(k7~wO)0YQ2t{#CQ<6bMksSOgIXJ!XgmeYy*Bw>DV;T#<ceSsbCY`2<R`DY^>|%@`5%<aA)f;?G8{9`Igl9Dc;)4d0'
    'S~Pa8c71Kr*Hn1$spyIZihU!HXz(ygy03+#APTBTwO7q(t5PLTZdD)HaI{rv3jNk@RjTc1t5U;;Ta^YqIBnH8h%;)?T87slL1Tco'
    '`K@ONwMWhnYGI_|ZQ-vie&V_Kq1GZiUK3ti*nV+gYf3#w5fRMEf)n>(!B{Qx>2M)2c3S3p0=>~fVqz%snP_Bw8gM4YGM`B#^QTwO'
    'b$T6lCA1vSx#oa;MxjE}@@5i6mxGVMf<+&OH!nbjtm^0Au7xMQ8(klTC!(trjojsMagD3{K(^PmecMviAyR49kjhmpPnsQS=7LpQ'
    'Pov*my7SnPoyP-GI*$2UWKs;ccyzn@_=z=JzD-H(&PnH*2Nw>GZq7JZZ0BG71V_)_Z#ero7sL7Fkxw&@>Ko?FQ^&mmVk5XXqAzh-'
    'S@mT4URm`-`mTCbK*0k-r?vtLu1L?)=f2aPHBWHt(73|mi-(JEULrd$!*ebWn*;>lSQcD^NEHX!v94<1)bL;1^7ypM&(qWMcK6eZ'
    'c>X+n`s1J6|CxV#+5Y^I8X=SxPKoE*DZi2`D(~+8?yYQj!D|^WvA};|4>309f!7ujm!r;@)-y71N25A6I`>(3%y7cP1zR(m;NeP8'
    'nc>`LY_v<0Zn4oWtr4p#>zw<f`_>X62zqsWzON$*x*YHUe)pu#%;7F^e0Ov=0)!K}FV=VAQHB<>Du_H4rDCV!pP@W>cD8e}hl}x1'
    'qlXZtHhMhw^b8@{Nj<}}n~n4g5kh?T^b8TgIzT-mk72d7pq?S(&I)?Q!MxYjQfX`X;EpxDvcEn^&#dNj7Va%2pnXO*5#Vya40O^v'
    'bb>Nor|l_VqYxI`w#Zkz&-A~*#cV~DXUci<Tv>xuGdLlVV6}}xIVedp$>n#ps@F92O4{h6`RCz`20x$MpNFujh<my;jfr8|9lKag'
    'Lzm_o%wY`D2s*kpbLhcoIM3D&hLGbqtfIBzIh5l`ko6=iZM}*Ne_oMIldp%)&-IZx)O1+37VYs|63vY#(bSua%XSuxsWYi|JS-be'
    'qgCT+RAe|01?ZJ47EQ$}M0)7{p4MW9>-P6lj3-jH7Vunnuz=@V4E>>sI^uFvj~@q=XbWM`4Q5(#S&s#4$AZ_gkJFqfovTXlBeN-V'
    'vkdYNCEOJ-?uJWh)*)#tmS*^SRSO!<+utkM&U8t%!@@hkQ%jlzX3<;BqoG6nPZ>Vc|5T<@&Ld<-+LZ^bozkw9)kEz{6FSnad^FC1'
    'cIA<2Bkf94@am(8YH0+nG|VCyVs$v;OUR&m*i@=+E2m@7%`_vtfH~9sMzdjHX{Va97C)5k->%ZeS0VRPK=k5kW5T+hAp|ibQFCbq'
    'iOujl#^HIRCD?DixdJ81o61cee-ohw80?G!B(Jw<ObAI>;WLW$S8ILab!jlvPry}Yupc2qtIoErKY7(5_u^NtIz!r6!s+5}g4k&f'
    '>%6W^#Ko4w`T$cYyXmSk)C|YfFg)f=fN?d<49C@j-rh2<TtS0H3-J~v_@F?OWf{3ho1Pgt@wkfHYC%TI@wh6C24xEzS0%^eio)-{'
    'eq8l<@0iL5ml@a=Gu}JKw3CHwJjT9l5nw=B*jzHDp@$B4hJqRPkTSnEwwL|6If4V-XF&9{UxW7Gr!opMOVh9X%J|)yent1!(V#u7'
    '1#2jLJky&BJ{vY+iI+g@fws)tbZJ{Ih6;eKLt(?^WU-eRT22;uiM@KYREV%W_+i!@t!%Xeo03`*uDp<1lU+$tje?$zXb%9pse*2`'
    'L<)li-P7i#>Vik50i*|IaLj^tSQ;}6lPoFkMYm|CMJ!je@ph5~AMH*|l!YM)qyqLmsXU=%3=7*`jgo}tw)>A?9?Ie=iB*W07<;_b'
    '9gG0^O3C1l83I)tcE`UE)Y8Npolp+Upr!}1J`fNU{0Y$~Q&~bZd%&ioc(Ho?b$=K|vn`3Fuo0$q0+U3d-DS{k?JZY|Bx-nkOCM4d'
    '&sC9elIY>_?b6<Id`mJug(Wd++|G(vhYQ$FdqUTel)UBqc0WUV3^*CbMM7z^p!^de)J_Hj8DV3<Efl=sNlFn@FDsscX**DcU1duS'
    'lQN(n173}Y4K1~BHj)%H<<PJY8&Bm@f}k*c$pZ{>NSGt<2av&{cJjTQ0%egLWsz&z*&qwNc5i#|6t<uoil9R1nqCS)7I<`T`*Pv9'
    'B`S>v@QvoUB^tsS4!n&gb){WAr?sf}h&#s~0wpyd7;v<{q)ig3^>(SFm~LaYL7qR(KTr2h+Y0<kpI=<YpSKU|{qx@+??1U+@-ZL^'
    '4yl0#xhbshNT8OzbLCcybRbEwro9{Ql3ZZ~HOySCVG;KzcW4=U<#wNB|CQUNAoSe=41JPOnw0wu+zF(Q09#i;hj2)jrrYeVLV`%f'
    'UYYN8$P(!zW4tP#d}TiM%6vM20hV8W-Urep=g~3bMD$&#Juo{AA>-1{dFGd#oZ~qmIXwrkC_PWwIobJXQNx4Z9+1Rkjd6kSeNgxD'
    ')MGFNYA`1yF~Q}~Oz+a#h}&yUQ*m#gt>O8@SkeP=NLk54yxmWaFR`lh84<S!LjIBnTr?EtuL*M+Nq_%71E{s+3dC8*L=uwgD(X0J'
    'Ta{enK``it3bu}%+d7e3r-%1R>7hlH_~1sIUM)fX_b1ji0&EXJ`HGz^hLY3+ej-5Zkc;)vB>~7OH9!QG^I{+N@z#DxX&er!?HmxJ'
    '$hK}sWjX}}ZDA)!u6Q6KXc0S=-GCtAQg9g~p5(_xBFK+uJgWFVoS^!I?(E7nr&?V6Ui6ZSma_BXT(s23!i#$(8OW><B{p6so=oc+'
    'Q{nd4u?8{Jpuj7dZ<5-_?S|<F+iAnV!*tsdOrEi-TJj>8_Ipb?@Pv2wj)(Fz1=&-8F)4#mf_I0zm-co?1pRb(he!Qn1ELb9qXeIb'
    'Snd6Ul7{QFdn9*?k4x^a4592xWLn=In$lR4Hsv&N&i?b{QpeQ*2KS$5jCzIEkTh|Z|I~K%Fq<|~cy69zuMrP9yJnsJTj~nx(5Nnh'
    '*-^w=2qQ}#U0x^s%VP$0L`6y3lf(hiBU;8XND=Hu13V{P8d5iqey@ma#+vN?PZ5o!qO#NfTmaQ0JC0(&NkWNN9k|WvPsl`9S}@+D'
    '829PiuR$^L$KS2@4=K$S_`VXn4Vw9iW~5-5QgM2GZLtGfTPmC@o$<}<OI3#pUSG;{IUL<PXe}#wD*FL$HKlq-S81BYkZ^^n(mho*'
    'uZs{xCND^a>oq1dGmVRrWB<Bm3kaK-&zd83cxEEhdj2E)u_o%s!K<AHbmW}dhqYv;dVKI|YT-J+P|ExGh{xJ>K<(nBr=>?|28g?k'
    'P6-drNO*m>zTUJi4{2X&KJ;yop2Vm+es$nE>0K^0yfW2zL8;@VDXAJWO0!7q=P*sOYtD{5ag<S{IC?0@@$5)Z)gjVwcW`uXG3T8S'
    '&ZxXT(N)_M5?yfwOy#kO`fF5Upebo+o6K)ocG*`=YI{l$qnYqHj^o+UOqc)-8w|Ihd_3HS$}0|c3=i2KZXX|VG~E9`b#L1vNsgll'
    '{*^`J4%ox>4)jh6STu0htHTX;u(#Nm{haU@^X{0*%B;!E>aN~jf0CQYoHTo6=I$ARj0)6;EJ-GpC`uwJ@*$5IVA?Rw{wZ>M-^StA'
    '8N=qE@~dsm-t8*AD=4Jc%GEpXRbIK(MHDzy$_WKdMIP-b%fP9~(W1bqQVs&7=DN5VR}(-uG77jV<=4>Fn-fbEfk=@RID0+=;AQha'
    '#>}GsbohIb-2eNR&zF~v!$1Dh&+ez6CPby5+X{`qBLFlhvIx*h(E;-^3tRkuKm7gU=fl~>FGDro%A}^3m*2kq`epd(3VL*ze^|b4'
    'oW2MIoX8|!Nl#zY9%HBKMDm|f7uOot62{23V&$FmRfNRG>X;(Lb6dr)>KYiOd|nemE~6Y<T{c#b4#l=TLAqI}&9g81Dw3@|%~g0L'
    'DM)D!%69E$F%R7$xT#q4Qm#YUVjiWKMJQX$&Vo?3SUpwNp=>daAT5hfwo<$@s#iyry#u0R6eT6bOb_LagR)36`}%xcU0CEZ`FNpN'
    'd!DM}RkXiV+fin0ES%#igrIS3PVz>6{edSH$5w*_*G!+2di6O74276Uy!yQU@JL|`1%|_8+aKN(EPi++^6@(H*m?fxysm3QUf`^='
    '^cBciLF?M3XID}0CG6uRtWO&He+#dDzFekr|K3;9>3%3bK=PUU_EJ7^WilgH8n{48Rd~CNmTnF)GAQrL4^75M#@R)iJhwT|ZIquw'
    'Sse3QG>XXH>UdSI2X5305zH#sWd4N^)=?_+5JNAlC*9m(Wcc4=^syH`m`u!z&yVZRQ$OM;)jX8FzDZ+lB~=%N{qptKeax!R4uU8g'
    'FI;P(rB0R;UbwuF*luaz^0MA;cH#Uba=Mke@Ps!^`AkCr9weFV<m>%5l(Y-aZb>J*@a&GlO*2{7O>LL#Q=Z-Bv(%HON?m?ShN@mR'
    'T{1-N$wi6`ap{I6$Pl0L<VrTF++Bl_x7;KzB}-=eOtz!~tZk6QlyRMJKuqqs{-)~7BI}aed)3#ZOH6PLDx8Ak)IE4Nxt&okRx(k1'
    'sq1FCNY!mb4#@wp&PEN$uD$1yI!l~e$A}zT|1NX_IuCOTmi=EdsgfRn_p5s?=n;6;$JGIibc?V~X`gkAs4s$x9HWSjdVNlFsq5BI'
    '>bwM|;)+Yf=T^6Hq?Kz<AcM(Vx6b=|))Z&AZlS3)Lh!fkoo;v6JaP%D-@GnWAN7%W`72gAW~Q2DkZ(V8UjK{-?78SeW`>x5Mvr8~'
    ';<*96uYbme)z3KnGk%?u*Djg_lC#O+XX2V@P7gH!qAi=SoJ{~fLw?<fK8HM8Iaa&Q!cv;#)xK|spwDhqcb@CklT;H3nlZ`=T8Fo2'
    'B5x(jW2U2x)WlO};`{Rv|McJf>;L@t|NYB{pa1pepFW&E{^S4numAjiefa68<3HzGG;Q6WEum6ps6HKUC-DSl<;^K#SKHMYT-Pt4'
    ')G5bev9|5}2s57RY?=9wvxT);C`v1O%Q=oQ@hBQPg+MF)xZOEHqSGY;xuBmJmJ6pguBajmu9@BR<_U3)W;u^;GJae~o+u5kGdddD'
    '=tk>@u$W)%Hn*S8Dn`sU_k+2?<R>-~@32mr^wjW<hc-M~OWf_y2&^tGnZ+$NSDI<Vdyu8ihT*qghSRs<{NeKP@aM0Kz1{}ESp!_h'
    '>*Pm->v<%3oy)9UpCPBdo)dBw)MMa;^bGa#<eikFk!TOnl_5o=!P0N1ej{Ntc_nG-Q#D#mWV@5^Jr19~efj%rVu?1ZLrDyw4RRC*'
    'ap=t@OPMP=WtCP+d-TF8P4ShsP-<H!jsoYjMPL0~i=I1YciV$8tdZ;IRSfGa1YhSmm69Z(loWFPto_@|r}O8(efawE^S7V=`VTK('
    'za0L-v|)~^FEF3i6moBO^2fABsGH}QQlB<S&mVzNtNDkQPv3?wUw-}N8zup5k$~Qm1l)`4nVDn(1z;y<xS3E{L&~^|q++J-QJakU'
    'o>L&1*e6;tZ>qGXMXsFdsUm2SY&TD6svcH~UME4Xq;lvyP7@Dc6nv}OV6x=tP3g5bXo8$FIA~^Cse|Tma>To@feD`o-ozE4XzA3z'
    'M*T^dF)08sWlKu54)mOVh2C}v7HA)B0zzC*%w6M78iPzuzx?`AiP;LB@;jdTB-v*cIT>DmR%GC;Sd4&7e^z9{tjM~J4}y4vAAq%i'
    'Y&UEn(fFLZ__^^hw>g)c=eDHYJ?-f2d#m^UE!l+@r~{{)x86*P(UI)S`RA`+ZnFssKW(1<v=dE$A#XI|1w4o&l7k)9p~Ya63Q1jy'
    'vXnG1Q&1~Ficcgka++Ms1fTrx!*Tvj=P&&a|M}<P=dZ)JHV@X1SpRW4Ly81q<x?GT!h@fuoMpJ|;p41XUwdk8;u@9Ow>khu+$!0~'
    'h!oBM)a#kWJWLQ?rT-R8qJZls+e4U4lWc9rz|dBZt-4)KQp97M`>V@No7aN?9w?O(S|eWEn;^zEQjAVs(neCJs!pBi<n?x2i$f3O'
    'VJ2l%3*pvViQ~eGEFU^JsWhDKx+PA({Js5t(m4VuqK;q!GH-bjGNrwXlSd<_xYn0e|C;daEyq|R)!cOi(~G-3$2!KEm`RSKx;ee!'
    'IC4E&@Hmco9PUk@yt5y{ux}7QHL|7*LM=-5YkJE;)WBjjh#Ep%260k@h;PanHP0HN#7Qp)r8gY}w-ZbNE}eoJL4MOsTw!X|2<ijm'
    'Npb^KD4Mq$0U2u+G#Kg-PHG7DEwxrMiz`idT#->X+V}a$QpLu>&lROAyxm1bX1oR^#^QWfPvTc;^On3$Cc2erKtzR<`UUp1&=1KZ'
    '<&Jk<p<7*;@p|51*dzk%{*(EQM#|Zx$6#rAy+Lkw@i~;=lMUFvp~hFb&nv_J%)|@VKmpxDW|4<kLJSo(@ELE2@)>o<Vy$+B5#kQn'
    'MTn_H2rSyCS=(?zt5e=C%FTL`%*py^a9_)3UEiEi*Y$fU3h@HbQqeW6ttxFF+W3s$Q~9h1hBS{hX^*w`^mH3?T6><(BTnk^;_9fP'
    'Ts+89Sg((3b+mf$W~095C|g_~^;q|x)uZ_crIb}CPT@#JNV|33oj<jYQ}1wghTrgTc6RNsWKFB<rpGIFEqZb(fVWh-<ec{360d#a'
    '8kXaAR!0JXsn5g~ux-=wIw=6ijo4Ve`VUD87{RqJC@;+sS@}ARDJgF2qvcEc{MS#z%3?}2W!loc=vEiR$$U)dbtplpQ6ib1D*(AM'
    'B@%KlDs@X;|C*z2b^;LL08|~0cHqsaBI|S>^vSVXB2iAB45cbcyKVi7TMhTn&B<jM_;}#gVXv5H_R5;QtXk2`az&4?^Fo<U(+eee'
    'qZ6&$vs??WodMN)`#IuWCmtN*Gp0oits@(y6VP>0OCz<YH4$1Te_E-d)uK)}ruU{}j4xGwwW@QEp5&??UdOx@kLN~Mual#k<hT|$'
    's+Ck2FI0eOL_RLyEJcO{@^PI(=vK#XC|LTm@NYG?N{kmdDIFuD#w|l+UjM}M;5{a{DiYBzZ}HRJfNt_^x3(RJrGZ$Tl{~lG&F4uz'
    'ck_8tFspo?+-hX@9=UIV(Uv;7-=+*_ZBJcZ$7v;*$!Udx)hTI@a$I9(r?11e>C)umRN*A*(sb<4UpYVF=6sUCIaGb#{0-6T$~KMa'
    '!D*|xBXM2_FLk5iDZUN~&asi8j}ky3Y%x^`I61grtYMx-*k`N|HyA6e6UDZ!lgbPAA{Qfd6U9<RQ@XL%(TCTeYY2_5q;rRJ<*k{8'
    '-ZXrN!U*x9@<z;m$5Hp5X~b`8Knhs_drE(qQb!W6`dZhd`)EXF?R1Fwb#Bu%<v68^8MSSqr)Zn6@6s?W!+=XOg=2eF;EZbEgv+}5'
    '?XYrsrs#XWWc5$^^-o#-TVV~bR3R4XpF)bFIHoyXyN%!air^K)W=Wx><p*hdib>(>UPB|i?my-A2=shu5rln1v%NJT=@91un8Fi$'
    '5`1G5?!y03952<zq9*_+@eGTekMnQm{s|JZ2(W&AQ6pwKw^u(EV$S!#BvJ*z>Se8_WEUxUV=GrGvyAViGzHBsP%28fM<^AP+yd3Y'
    'wQ@oz6{Q@aO;8%Ic$mVMk{7N{^#*;BheOi&Sgy#?%KDRnRiCS@bfs3wtC|{tZesj-*b7v!Q>4Oeb?=W^7^|ESOoIa&>=e=Pe_taS'
    '{!1<UKd%w~6YC_2wLMZoMQxP^)YX&HXe?Jq&$qg@U_TQokuV7TUMMxDd|zdcYVuoR`F{3$nbZOTKnjUz!mOO+3B9_x=eILAnAqma'
    'nr&)=y9Ljk)g~j;Q0`<*%6V~`kpi9koe-RCT;9QGYF30UjOkZTqrqU5@n=dp>D4*rx^5O(8daoO+i+KH!_BqVt3W@JX`5*~w8^KH'
    'Csk82NQqDrguXgXNrN1X+MQ{2ab-1XKN?h^=QYo_(;Y_@EXvDpz|uh5dc818Q4*;A>1^Zs<sIvrZduOFyRP}_-X<lTe3ooMYS)Z5'
    'fcH6b*TD0MIChSkN%x_w(!%FC`NfSJbS$DZOTSSn0=YbvuH2?&hba%<LNvJ5t|QeZa}8VbyORv6-`?V-)0mY!#Llnep*Crket)-o'
    'b@dZWa8<EJCTMCldv#^9;6nC!c_gWDLE@lNO37eZVwEiH`M5Wlpxt1Y0dW+;s=t>tNxcx*#%W1=M+!gH>84?_oj2=tE;30}8nt;z'
    '8OM*Zirw!|1gS7`_a}iM-p3Iyr*Bw44Y^jQ-vU`IOHEWLV^k;PvG%1E-s%_sj&Ca8P~|DRsICZW<Y}45P{&(Z<lkhajCDMlcg#!H'
    'HD1ayVu#L){fo3jXWt7#Z>LgTL?^l17Rx#~=`0;s@|a6%E4pZI8dv!b+YiLv#?Js_T1Fko2_yiC)Vd*oh;-t2ysn3NS&1QttkJV?'
    'S7K&~y2Y|4t8h38aa!s^Urf!Jl$d&azf^NAHCN#ce-Hlu#58QIUkQv8;n++$(#NyUy<?{FEnf^9*D(sr6LzE|Y_pW1+4v3P8=Fo#'
    'hC?InsJPCZX<OZu`EGU61a;#4ehGZYjlL0Dpr&_EHc1+wekW6!R9d;Bu^r%x-9kyhIZVqrzPO)SBNonAv&V~W5q^IQpG7LDc}6o~'
    '^7_=#!LjxzHjy1&2UM1f!(7*cX5<O<58<$|!u<PvNG@#eOLoT<II#0%#nsVQB_k2f5T!BzRAR1PzH3xswq8R%yH?Bqm6+{>D6Ub7'
    'OR)o}#HDzdSc@xwVDBY}t;PoDKZ>p*Oh|QOH5Jp%cFg-exoIpIDruKKFY8FU^!+~cDz0wH=yt*)Bexu#6K$kp99x}UT1FwT%_7in'
    'IG^7!X)fnRn!G;dHv}VRQkOJNpF@f?PM$-*6Vf=H`gbifIj3Ie>`iEDr-7@lr(0stg1TNwVWXe3ydqt&>bg0p>&AsX-@4G}TQ`Aq'
    'U2UMlh=%n}7l((oI1wk<YLvAL%8oA9m^5ka|JhDeH)XUt{H_?6l*#?P0%9mF;_{tuWVCh{I_-g3LH&nzAv#_qR#yi7(jcu2`d+ul'
    'cJ(OWPr5}C5N*RDyko+jLL>a>a=w*BjjP)@!iJlO>#glz!_5u&_hu$$uY)V4ZyZnl>2sY(H_zUiS24Voj{0~=rIK&fy&=D6iXLZ*'
    '2D7?)#vMG*Dxep!(_BkZ)woi9u8S(j?xbin8tdRWI;Hr9SIm^>cM=<aFGSX_8+PSOQCjo@?s#fIU5rrETBt7CDR?uuvF9E9h|)qR'
    ';1j}g7It3t`VsbeBI`4|<?~(Mr%2zQa{4wVkVs8Dfx@bjUEe*yDvR>fkGUNN!Akg-bbPnR+r%LY2w1@(ZSjKZaY$o;;Co4vI4B&W'
    '---Gj#;4Zi!0~REP~A{r%&LL4?hw{C_og~thM}2p=Is%=YmW)Z{_gBCA<^$}K}m<Z3#hSDrzhmz^MqWR5WBmqV%NmgceIP<&UPc>'
    '+tT@%<Cu?U>0n&S6LK)-8a)6UjJf8E1`fuh+#&~Ku0aMeo!wDd_M*#5=o$S(<{@YglA9ONJQkl;QkC*E;uzFLx^{jmEtEIYX@yeH'
    'F`A|Rq;JTm5$LaR_CdEu`aXBdG(%jY5|#k(QTIVQy6Yt39=Qf2v~!B~F<jqjgH%`j_ViiClzYA;jVD>ZTV6%bTP3}}DUBG{STBiL'
    'fU&%n5hvq1!e|?I(!d{M{>oNom1=Po_#LIruhfoq7$l8UC%v;c*=2N%<nlD89(on*9!^eVb(rLA>!d=E7ID)TRY!9MlXtV6VMN`W'
    '%?&r<GllpL*)IwQ^)>5_E_65B%EAhm(mJDGyBtyq?{K<gR(85@RWDk-20$QLCEyR<&3srJCC16jJDIzf37l9NBqaz6r)(c^n`1J)'
    '{NJUjLD=5H$HilIL&@Qao4XU`%Tqi7it=R|F|bvXZ>w@{`Ow?uS<!GiQNCQG24(|Gnc)vy?o(TB@@s79V519{=wgwRLWQsvQwZIB'
    'n_Tg9-`(z{5l?2m4tO%V+-4L*_aT+yJKUd?H2;q&F0Uf+yb~$$qRnA$Gcz%19CyX3qqm4oU^#!tX372YckCCx%j@6eRl?i(^K2HM'
    'AJ?Dfegex<*-K!_Y`O_7c>?QwUz}U9fhFgjmYmBrb~%?P=ihh5x$NR%d50C}vdfD$=M@XE_iOH)JMgq(>-ocAyX+B`yXv(5-EQVq'
    '=2_-xpI_FW$JpoGngPDocXA4`kkxb(zeCogMK(jT;$7mEP&C&~VFB-pce(G##MyM^9?q_BwB)?ZXgrxSfH+e#%<qXa%U}U1&eULm'
    'jyRKT?1?kkc9Fx%%$yWwh99_2mfJdI7x3HcJR@)4--gNKp>^9ZD={Sp+ubmE(gNSrhN*e)dmE;P6ZAGro(*dncn$7}WcK$&qW+#3'
    'Go8RaF(PZhJwepp6Kutvu=e-^_r$R|)@K$5kE=mcT3<5LJKPXcQl@4>zM{qCR!6I?FjnQ7$mYH6glzgSgQc#kGM58?nGN3cZij4i'
    'xGCBR*#HE>c^qp5!ntd|68Gm30tCXjM~OgK^lbkFcf!TDrSKa0#LCG8uWpVhj(@I>=Dk@4%b2=(@3UE;2uqCSY!(Q@;b!3}buwqw'
    'y|~8Nj56PC$0}wR4P7&B&#JP;6uc+OW{rLwBxSQk>yk*^*&5TOtTp}_%Gyz?Q%u`v*J20W)8U=%B88MBo^=`=)CWmC$9>}YXW+K8'
    '9iIy^@q)%0cB=0EF{O=NNcL<O*`vJN?lx^OWqOV&(;69lx`Zuh!^J9>eQBW{KJx-Zswf>s9T!u|#@qLt-rwRZu=~~GEU^2dJTaVc'
    '-NkVuFyNz$<0N*!^oq}|9^{;tPt!%UGt$m0Ou)H%)HgJa_d<N<a+mndYXIM%i0^Zs_~DtP3VHJ4hwsJNMf2VsxXYNXQp6%Kau!it'
    'vMXj$yVa%l_XeIF^|zy=MOHj{R!#uxm?QYP?U>beT&IyQEjkE2(}wlNte#!kx85|6-zzN2`C}_iy&YV!&BN`BuP^NrdsWM&F49O='
    '5zZG-6IZLsJcubN?C|ZNyL2KXvXuVuHa?f%AJ<Gi=n~Cfo}uSuY94_Bp8Y#~{K|eqVDJlpA<9kQHv|U%oWS7I+T(J1*U!}h`~4Ab'
    'aY`uSu|8dryi+_=pLqG1<Tkl_ey@n<THX750m#9GF7blVmvxey7ZyoYB=Lf!XNVV^a4Ed`qxn_~+?Lu%odODXZpv3AgE(^VX|*<U'
    '2mT!%av{Y2+AK~Cl8hZ<?5|Dar`9I*o$GQ)>D>uSOP^&$yv2z@im^B3itwCV5%N0I);yN1GHne8v2Fxn#d)st?~iq(5y=T=WOK2b'
    'qkWH~wrbRVmGdk|_a28W9kpkic_H&Ge6_FdG~>KxCX#4>bM4H2qw+Ny3a;kuYq<2hYhrLx`M8G3sxZ~kLIh3!Z(}~f+vo4lXd7ed'
    'A9*q6cX#AX;Q7j)Gh(RBWKLOY2bYEMJkt9!*hGCGAA~P+saw5>->O*UwI9`hxi-H;H6WR_hiVi~ou$DVmi<;o@6Oy)-O!hTLygrY'
    'z<v3WHCMScoLW1}lIx;f<%+LAgC4yb8jLvo3Ji6gj221HYNC@!`mWY9#MRT=_%|%zv~!B?-JK*UvclGy<S2!$mD7lB(bnW7_1~1@'
    '4Z(u^<p;i%7P+y_DiK659!1D`PtnG{p?7$6us%Ajv7zG`K2M3)mWsJ9+Zl$1f;s=dg*u$ultxj1e&W(sFKHS7^qZ=Cf2Mp|SO+e{'
    'X}LgT*U2$%btD$Z(GOgp6SXPXytP0s^%uy!zr&imHXjVPWL5L9!v@cd(M;1>7yRW1uF(0?=Cm-0409fbS=pi3H^J9r3hz!ppqPQ#'
    'YhH%bJqO$IP1<6sj&_<XwpYfCr~Csa+_I>ZG0_UON4kDy8XZj*`*5C8HvQ@5cX&{a$l~pOP9l-`G-@7=u&spvHaW~K^kG{)>1U2-'
    't8KVenzL$v0WTDDl?ObtBl+tNjL$nYK3*ATt26%+l&C2tti!yo?~+NG26)`nt^XkUpKRwmnmgw)t|Db~b=qIfGwWX&chW2;tq^E('
    '_0bnCXcZKlnf&@!G&Nc2F4uG{bN?J9CCai@qq_b&uV_Vj7FqY<mU-iIMY3l#f<<oloXt9W{6V*{QRjyL<1Gc@)I!AqCzk-6l-O$C'
    '|8jWwGMq(@x0>^<)PFd?eErwYFQ2~s^z+XxcYMwx94WwY$=ScZm-+0|dIz@cnS<sCCpaR9jjda8-+P-XNB5TGkJKgqJ2ZUd1bnJy'
    '@{@idjgtK2H^@)iCqLV_BtNGv`I+Az`E%%BPUWw29{O_WyB_&#C9StjtFz|K$X|PpnEbWsz2RPzF)ckcZ`@xixx@XX&f5+0>-;~O'
    '{64=W`9tWEKfJex#xkbpHpm~TPyS@q+h!(zitBAN*YR7DpM0166yG2DfxLBS6rK?hWP-&hs;^e}B92O3R`K)Jsk$H{CL)I)NCy`h'
    '9kRm46EgI18n!hmFFV&fBx6#ATBnb2FL-!@#8*7r*wk9L=I^;KuJ6y*r&TQc&any0cwKi>*fH7fyV?}ikz|IrR47XeuToUkm!x4{'
    '9KU{Lx_w7tw)RJ|{;{#X9bZah9@U2T-R%2Q!|)E5Dy$Eoc_GHo%n@6U;xYZe0msw^9C7xa1{UrlOi*c_R346lIt5Y!maq9sGJQ5A'
    'X~+xd2bzzgp+=c8=jht5HIJIri73F)Yn_h8p+eI0Y~(BTSz{?&^W5Gldw}%5uE+Z$RZV>WVS{Q_FMz+)S)(k60<W-E(mE4KE#`G5'
    'l3JYCnMg|Ul<Hk&BB{lGor$Ct$8{!>T1+|<Ni9<O58TqUR9bkQ94?4!)@fl};Ck0OWimQ1-2O|0(Z+E4PT=p_kuqeCPF>d-$QRVo'
    'E{3k^;Iu$2yo*a+T4QC;6i6aH#I;UMG3lhDcIRl1!>4aw{{B<D-D?bjf;#kaRMbn#+osD#+$u5tz(e{H+l&~w(#{JsLR@bp6r6Wl'
    'mO;fQwOm={byJde%Q*0k+-vHfxSuV+8*k!Pwt&*WN*s-3f8=AzG5@IzN^Q2Y+%(?ytn#JKNfU}sythR5Z!e$Dpa1sZ>&MUEe){V_'
    'ynOv~_=iSW@46`gY9+rrscTAxaMQgn^5weL$L<m4$7JxgoA@G0u42(1K8bukCaqLP^WJ>c>Y%jg`+9;%N+w|ap6fJ3m^(>IDl5n1'
    'l%#&TIDs?X4skz1Z`^YvdY!dO$)!HO$0gFH0r9-pWTaqv(ECl&31gI6GagufzTO1qR=Z9i3la$N)Y`6FFR~%FBew>2+>!LJ$xy+s'
    'b6B_QDvVj<COMeG54@*oX!mpoVJT8w?@=Bls<sz`ehE^WC`2bEBLx~$Yt#4aq6)F!^G&F=IL}3A*~dId_iV91c_k&bo!YS5dq1kO'
    'qn74bx$_Bcfm$cs`DphFd_$IC*LG`=s5#A9Kl~qplcTZkZ`jcY^<^G%qja27-N_U=x4JCr)Cxr_0bG?{8|^yO?mXAMyHL9_C<l{O'
    '&8zCAu_p~bP){drdV2I8S|!>E5IuJfrZ^&@X^X}DVTj*zF2!j2a#D=%E=Z>i>aHtto<r)N_;Cb;o!yv^GbXbnFn!m-AIE2v4uQva'
    'm9N9MVYG&~Vv!1@(B1t=y1O=!?7HTpI6dTy11A3i-MQ)P=K-fXa*248`X;nww4eL+NIk!d3}Wrn$gVHOTb(eJ(}kqLh)$nBef|7#'
    '2><i&<=a30w}1Y?e>r?P|LyQ)aR2!Er+>Oq!2Ulkm(Tz5<>k+R9=`l!v-|0%@NM|*+fV=e&C>Dk_2u;8>$fj2pZ@&euP?*j{_#|b'
    '?Wy$g;oFzP%eSxpc>3wOhV2kalVMM1FRA6~@VU+)PgPDoZTst~)izLa*Jos<vs^AGFCN5_U%cvG>a*_r%cHy71Qsga6jRX1$PFIS'
    'n%42c<L44wkPp8V##`{@DgF@J`zD~)9073!i@M;%F;GrIH{GT)<*FMwX*m6m*~C+uO}gH(6UPka7xC(qlCNC$^69#2*SNWMu+?-1'
    ';<M`+a+*JrzB+aGgZz-??Cp=4y=}9ntM&Z$9B!-c;2~D*?w6)8)L0O)saU>2BsPmpagYS$Ys&A>zqTjRD-~OvNOgRZ{Rc@%&Z>zs'
    'vT{7dCqkagkJ%LME>Bq-xQ!xGCdn*E`LddF?vjX%Sv>^iR;3<fvpA{ANc2WJ{us*4T0jj70dFv5&GJEntX&tm>U6q!)=<rGwGg9D'
    '`cI0P<PE$!YBq(QF9i7oK%x<kOjHEkeEs=<|HJ&&e3BYB1?5hCOF=p2C@c-4@}@p&453<2>z}Ye{YE)-M)%y0qKO{Hl%{=8j3Czb'
    'W2t=+aFCglc^ds=e*X32boaL6jo$JE`2OV&GYo#)7!&CKEU}!Y$h;t*EqF?mIVp-F$5yRl8D)8r;%Wux_hK4X9LQT`5ayHXmb`8-'
    'o+-py%usV;9jSVj7It<zVMSKoO{uW!uI2CwyEc9L_2*;xpPJ|{wC%_vBy6LY71kJDXm(mc;t@m%Nl1CxCcF@2w1mV(jJZ3FOlh7>'
    '4}HB>wqF`$swuRcM`^YVC*@7KszTl0<SIVAf?Op@erN&{j~O{SGZ`~-KuL+&->x`5y@I49$9HNX5OeH`K+Mz=fhJgeC<0Be`d9>F'
    'd2{pW6+|F4ttQ*lu!yy6lS#=o*{I!`<+Yuc9&k#w$)<mC=P?i4mTZ%)@5?rMO!7EU=<v#C!EAuY`WP!4N6y~auFz5=J-Tyu`mPi='
    'M0P4Fjl~U^y#!z9{K`|#^OU^?(pEQlh4KfYO7^^zOR~=(t7a(=%3tB@FMpJE8W-KFpB_bo&tK*XUf$eU8T8LDAOHBDW>A;b;+Br$'
    '-~TYDOFAm|sho7q&s+K0ejcRjYbGZNGqWlAmA&;=mykgy(=A8Lzfa5~euuk|QngZSid^CO|NQaqzx?IHu?U^=hO6-qtJx%PFQ?=N'
    '*<a?HZK_Bcyy%ep7^Us4F@Bf0r4b|IS_2-!f|DQG42Wxu>jkaWIuD3jic_Dsb^?Qk#I+R;{zlwzSkNL}8Y%qxea8>pQX%d|_BR@H'
    '?;-9CTed~q7%_2US`*jH4~tlgh?}TS+|kK!MO^Y*#HIc#y*1JusO*3RE%MMv0p78w$dg5M@`LPe#4EmsxHEe3263%%khm4|d_~+K'
    'KeQeZ*Mb=TTOA?dT4y$hYhCCQw>mc8h<jMl;?ziC!MkzgTwZXlmHE{-iEBf+gSa7M;>NYs8lwC#8Ax1^WAj#rjPRwHwuno8vwo=z'
    'g1Bc|(Bg7xq@eXaq?5Bnk@1SSobDxVws#OWCrsSJ_UkJ^eCP}z;ySa251H#mm2pX2XTt_@-6&yU;!cjGBXJKVEofog@lUNG*obT5'
    'x>0|-gSgJ~K5<>}khs-(bTt~1AI1QQ8`rP1w>pNzO?Hd8sqbP|Dutc(;Nz0G@z7{N>y21Gu*2feb)%*89_n(ugSy#Z>SmDClf{SL'
    'SVUcKT$j3jw2~~T>kV&E*IU=8u9vSthZL67<;fS(R)52eFy^i7(9xaL_46~#26eqBNZsnFw;E2C9|nfh4Y^O<=pc1t+@kK7Gq6M5'
    'BoyRB_Dkv>xzQr6w<4XmoDD`g&sb04Uh2+C;J2vD0aKUP!eKbb4|9an&1)FmTU|!f4aRLycXCa`)D1?wKOIhPN!?+3WVFGqw_?#O'
    'b0M!i$qvVt#XG250gHF38$8s~N;%Ndj`G8Rw6s#()zV5G($Z{oF594P>}zSZdY9d(d$9{zIGY+RBG`)2MVq5K8A7^OO$&5~nidGF'
    'Y1O}MH5|3d4Ar!d`)XRqP)!SYOHG@AeKB>bOVv!>V+9-5)D4r(u{2z7#VU}QdN{}q?Y(+hba&`!W&I#^qXT-{S$^oDo)&#yPm2NS'
    'X)$c+X>r4w+Ey2$8+F5FNnHw!77=X4a-kj06<kSlnC?~7V!A_7i-Z-m2ppS(lwBf2MQw80!PI4_sKvacsKvaYsKqQ4wIdBn>K=Tf'
    'MFv}ud_J58McriX)zp%`LsLr@YibF+F9vzLCJ!~W<olXh@=#MteoIqJVM9|(L1=2n!+A;Fvum^n>#gVyqaG}ICdGSIwUq8q)l$N$'
    'T7{}yd43!DAwg9wQD0R{3{|znTdLXw9oeC77OL9ud|J?=$mER{8LMgwBLkUxRW&kqsA^=fs#eh!SHzWDh#XYa$n{k<a!^&P&*y#O'
    'lHX9(>I3>r+>==vc71cQuoatdHJ$9^l65KGtEy4FLsg@MRW(X$`7lb$ZoLc;b*Zna5kXarXiHTi-cZ$ug{pS)OUtg0&9qye_K`rg'
    ';@y0&s>bFHRgDc+)#~&8in`LY%ND9?72U2!U3O4algaJZ)MdA!s<9WU+9@qfyPlhEm;HJx`k@+|wV7dhL%)Z*;SN=eBUaTaHr|T5'
    '(zeS9s%o72sv0M#sxfV;YD^od8k11fPI*ZSf1GK-KvgqqMVRxws+!F2-lc9fSXIkrEgwc{+^rei0d=QGVMyKjCJd;X?Ut&R-G-``'
    'olw<Ir=@Y%56!w;-)%c0gHqM9zgJbOZ=w6t4OmsHAb2b4O6zU~q(jtAeN`<dsH)|(rK(LhavkcDP}NSCrFA#hX5G!S-io#;W-IFQ'
    'y{cNycc^MPV^uBZwR{+bdDj_(R5dq&vmxp_W09&>iZ@g>XKY_pbM<v}rtaA-&ATB?=H1c|sA}bwJ!tAW<L^|}T+NQXM_p$ERMlL~'
    'RK21u%MT+`)k<+!RdW-f*owMoLscuaeO1lX=g}K=<I=nvC^uRppsFQza7CL_)TKLBHD`EVRV$64s^)6y=e2++KCCI80d*%FEJ$5z'
    'kg8USH&iueZC_P$^?me4U0#}Z!(lS-mWJ!Cc)isY)V1zTRn1wyuc|rgp{nL8(9?>#2l-(@s#+=Ts%oy{86oP%4OOkw_Ej}!lTg*p'
    '$EA5UoT<?wt+yhbT>Y~b*&*GjtJN2|JE+T0S1aW}Ks55hjC8e9+||`e9n#gDGaI^^bEdDWxe1DAqVBLX??yA3cU{Hh0WyO>3`$pX'
    '&fTf2xr(f_OI_!ou2#y|0;1YOE+Ada)kMNQ>bih*wNkvHtCdOgbv0L?NN4H}c4^*?Ee6L`%$(J9_$u$7g6uHesjInL(%miU64cd7'
    'IS>$?{E(5ZR*Jj2nsXWHYObc+-Jovn>uRn(k>055m*(A=Ci8A-h@RC#`E!bQy}eUcD=qhRHRm1F)m(*ASy9)^4?WV=N^w_LD|JX$'
    'a}}$kPhB7Sx|;Jr=xRe+ns?)roTfC4U@KNlI5;EEU7zmM)k@2KUCnudx>_k;3y5Csp_(ujQJ1^ATB$?2S}ESp)tt|LUCsF{bhRNb'
    '&AajB8ZGjAD;7cG5)Rcb^44K6cj{{8VBFW$N+YPNIRxzCqx{ezUCjmG)zwNJ($!o|=Gv!j2z_16g&=gb;j}dG#*1yV2*~}>nuRNl'
    '3-L}}&4skDtGSS%uI6f%)zxs4{E(oo7O1bQ1%|p>;4NJ(@P@7yve4Cr%hJA^TBw+-z#PcVP^hcU-DvLB)uOpWSBn<wYBeG0YB*98'
    'jt=T-(e-t;=%B6^{g$p4{f4d<CH(5etvq+brP0Cz;GD1$cVoC$Rg3WsRV_xWs>KB4LwP_&f~s1izN!`ps%nw8RJAQw16N;2Z^VsD'
    '^KPP{(Sq@-8U-!x#(b};mdqWhS~6HwtC=5H!;y+`vQSl<;^!fCrxc7!>L$0PswKCfswFQ}wF@t4kq$F0JlKf`Yc31wrf{#SmckvX'
    'T8dazOK~k9I;pDF=x{{c)K}F~f~s1gEmbYihN@OyNN?0VE{!<p+>AIihI=_3HJj=DzJsdy4ke;SLqn<p$;C_a0vV`8km)NCWT6s4'
    'c1wvMyP-so6H3HoSgL4bnu>OPT3sEt<{Atjy7S>q+LFIR$fbaVTng)(Rl)_k8i9;x8~Z{oMJVLna+g8c_LIif%A1hO#w^7!@=Xk@'
    '>CINiIjrDv98K(h2W0{O)0wVe7xHGLyY~U*D>Xk3hriajv_iiKBXg9s#y5qEm2!nODZ|K09e2aX-1Op#!^j-ZHp|*A2qSYfE_#>A'
    '*y2lvfv<0pHWqg9(qY%XblAg7hyB*2!+zt^;a~-m#VRk&NibkQS@{AO3J-oLKchH~qr80%#NDnBvB?b_@3@CJ;d_XI`)`tFmm1-W'
    '2u}TbhzZ_9^?`MR;Jk4UO>x2#!8v!S(t^w!12g_LROfh-&WkP^^Dx1)xx<Q>Ew&<N;1QgpC8h?=0)l7Pw<2Z-t%&u_wNLQuH>`-+'
    'M?vsopDKAK3b5>71J5p+!>1_K#|R$pkO^vbF-UOWB%GviCMPHp<kXi5GC`Rj)0Rw-X+tK+>;%CpOkam8Ef}rlH-tead^uP}@Ejf|'
    'c;2@)*1SoG;59wbn&44>Xpyb4CT{2vyyhYR1g`-2eS%j2_b$OJZugDg)}}61T7X&wz6KobFML!SUXf@YC3pory@TKpN@f)Ua!v3g'
    'KTJq6tAJyDf+r-IRji>cf>U2ItMD>{;1wvhLzOvbtwO~hb3=WlILV%wA18R;w@B7Fa7=LEU7Unfrv}X;f?M0QNY<cHMDY54+b6hn'
    'eT$@@vI|WFr_d*O3uLQ7bVx}a_(Uhk;?~E9DQ?5Qm9mC(K#E)7ahzCw7?G8-`nC5do{*KYdQfjsJoT-V)zel`{NVc(Z^3QV7Z!#A'
    'Eaa5xLijkvdEatbJ+m;yffsTT=AY`sf++4x*K%2XI1t6_J8z%j&h{;r^}SqB{OtM^Zvk)hMZ5FvSraCUu3dhZ;?D1zGwb^bq__jF'
    '$>|_JjL4i>jm&+DM`X^d_RKAcr@lF}n!RomcgFT9-h$w&VG0Go6`iO8UWl$KJx+1n*EXw`gDDQ&mD5pvn31+wWv?#9y+PV$z2P?~'
    '?oD6YtapH*xHny@%z<(BfJT1U6izC1tMcN*6!&gl-K>9*;vTp#CwZ6qfYi-W+*LQd4@lkg^^JIg;<2x8mP(;+x_IeRyamg758ooL'
    '-V`iFF;5Tco8_B*ebak}`erEy`sP`Fn329&io5!z_ZjJ%-scT{(+AVnH%q0^Hysasinjo|@(BzJkB7raiQ~aOtZ@3^_7%?32r8VV'
    '94MTF{LmwX(=XCYD2j)G6i#2?k~b(G`U<D72_9|~Kc4#(Z$WkC6M)(<$|{=T>0yntd~=7!83=2f0k}V>i~NwG#u>P;aR!DOXMJDZ'
    'pm^TUI71d1r>mgFJ&LzLJ704$K(G0Q${FqBDrdBJsGQMZl`{gDXi_8cQ00uiuX08YRnGe6+^2X98!BfELgn;VxGzkVIry%80z%5&'
    'Wy#_(KCW`cbcf0r6IMAR@RF91tUeM{IV1N~&d5;ZjJ&0C#=N0&#w=7$ANq#zIUuim0stReQ8~5Uu-vbYtDMQ+p>igRRn7!Fr^(3='
    '9aK4!>#Ll}LzOf6EtPYEg~t@H$nZCcQ{OT^2kDhhfXZ34qGQkmkB@7dDc+%Rri3-lgq*3p{E(o=nW(REPPpSMg7cQfnRr9vOe{1`'
    'f9O+Xj@$DUgM9rKVFt5g@%*^PN#+iXv*BkiDNew_nxqbV#l>DzoLpbyBnLH4a$6eb1e}d2-rl!Iil6(Y@i~^y*N5)4Gw~I4MdBuU'
    '3Xf}?6z|YDDPoP2fYUWe+c+htaZ>7QoJ3ILtWez>6sHZ1lUQh+!Srq8b9`U<1Oz1=YkZ$RRVY8MaZ<iR<79(1PDYN{QX{KS-GJf@'
    '5<%VSpvGBYyZaR9jck^lMK((gzHc0#WBz<a;l?q4n&KQD*El)cp>cA=8YctiY?9V-PEh0I)YmvUL5-8smd44np>fs+>>I^X-#R|W'
    '0hUkJo7WwVaYb={T;t?B+@4A!tZ_1Mdm?FB%h2t~=f2yM&(Q6u6mMyqdBg3=XW{n5A@{B0b8Mi`zyYdgq4hsS@$4VhIJ3V)<IDkT'
    'oEbQAleCWK2sO?e`x<ACP~)t~${Q3<8yaVQ!oE@b)VGe$@q#`R(m3l2(1POpxW<|J4vjNstZ`=G*iFJZUWSJ>&R|Se;|#_ijWblZ'
    '<u1j8v3-p*7=gOZ;nKH`&oPAM6R>$}q!1~UGZ^=<${CE`S2;@~sB)I_wb&}H$H4@oat0H-DrYbeshpu=FmF&i^;OPLAF*eON7uKG'
    '&vAw26A&$L%+*#KWY_et${7srtDL0~R5^nI9^lT&4>M9ZLxpJWQQR7&a)t`b+^4uTeU&rRSL_?bL*F_+#~PMTfbVFQxQ@ZPht<ts'
    '-M+dRtcU7mDPK#h&dU!2Qa3||Z0-^}AayfTpymx?$G*B5>I3$T*wi<S&!LCqll8u}@e<u}Py|m8Yn#E+zP4E!L2WZw;3MngezO^A'
    'o5AL;wi#?j+GenML)#3_^tH`U->+{3KlJV5b2MW41iWwBOCU=!lD3>L4{MvjxqWT3G=kb@DF*^;lplJeZB`GPF2!9y+GePT&KndD'
    'eQh(;_v;(Q&wac29HCe~0nQ2j8h0;!DT7N7Yn#EPeQh&1g4$*&2Vosae#l7M434|nW^jzO%}`OEHz=O_+GeQl*E7YF>D$HUsKxqJ'
    '4`4A|KIE+C=k3GVX7F}j+YH`8ZL^fG1y)D$Lyxr0;C)xy4BjJcGgRc~KE-|LYn!3IU*9P1`-bs3lCgZU-n^{j6CWSeGlNh2dS+<^'
    '^~_QZ0)tt8NJ!5Np1OKw@Qn1#P;sC)Xw7{+GkB33ic{Kf7H@Hl<r5T*bxoTgBc6-a`LLcDg4x$IL$FZKEahua)n)miLwaTiuB&H;'
    ';E<jfDmHYV;=%Xz%urvhZxqjcs?5QTMZH;XTdw{RHGzrfIX<jrhHyt7qY!W&qf!neRVg+Fn8zrDejcL`U>>6ow(=N-u#v|o1d+#x'
    ')2VL~pW`3PCt&X$hRgAAkXmNQk87Fnj@(A25!Nyz$Zh0~@<W*0D8znlqYz<kqY$@p8-=)$+bBel+lbSpZxK)DQ=<w<bHw42Rq$Sj'
    ';c*=^-jVL8G{QP&1nG|4Nqz{^9fjCWcN8K_cNF4Qx}y*`(jA2;(j76mzCE1Gu~7wNKH?hCr(*g-%#Z7t@s1QoA>kBAr5xy)gZvPt'
    'Knkg!0x2Yz0x6`e6i6X$q(BNuq(EYdeRDYZ$sArj0eYq}D~c!oxT2Zv$cq#b&WjWh$crT5XG4N{kwWU{MG6V#MG9#vFH%Swd67aA'
    'd6Ag7Zw{xF8&yDxq%fk5DT4FkdS<#KS5j$&^~?lvC3$&<6U>zqsGln-5X_YnXe(Dzsol^sN#sgmI`*yMlqYL=`DDF!i;z<ITOH!$'
    'A6GN!j{Hf1aQ>uH4uIa|Ax<!VQlNhRq*4dfOxntyRBAWWOcME%_?oA_NAOcKh7-u76s!r>TE*hTkE@w<M^2?cIHyt|kW<MEH`>53'
    'r&8d4PNl#wr&8dpoJxT=aw-KDIhB}g-xyApW(-FW*Y;u-j}Pn~S2g*LEK8*kRy7%9S&|^vfnk=V!2K*sfnk=Vz*||CO6`WK$s)@V'
    'v+tY2*)>x*3b?MYaFxkr&-A#a$#*1P3XBsk1qO+iBy>Swn0P60Kk-tjgPLaEO1xBRH#E&G5-%~QzB!y@Gl!#q>-yTWK;jG8J+5lz'
    'JCZSljFT~ijFK_QO_yOZrjYx|m`WW~HS<<7rjR$1F@-FWF)`=9J-qOLqY8+)E&|T^a7mit>2X~%-;toHG{U-O1__#?lv6TH&=hh%'
    'K~t%Nx@O)=&=k!^f~IIhf+oJEZ0}M0IN8G^3c2=U@QF;~6ODaX+l=Opq)nv})Hb65Nt@zHeh8B`Mbl5(6b($;6wOxBrc&G2Hlq<q'
    'o0u<sdpHlaQ3a)Ms>Z8oHI!Yaht<t!?nvYm4Nl|~4M^k^&+<c<$SInBBBxS^)XiwN5;>LHzPcHWNaV!X_3h!=nno26bX^^rDwj(h'
    'x8`AWGuk_nJC#OI-Ha9_cZzC6Fu7B-{p3!i4yl{bZY6h$b|bk{v?94vxyt)i@$4^+Dj?{(x?ag%<HM?Ew0GosDvhA387<27bdevz'
    'Tu;&Vb3H{1b3H}7mFub0_EpVjMXo2#yaAt*W~zXA>nemVtSQl%hjq>9?nnR?9Zmoh9Y_F`)QDgLsOb6$ph_LmHKW@~099)Hx@L4D'
    '0TkzB-y)v#xlskgTg%6X=;FglW^{LCgNhDkgNhDhgQBDS5N3mluAdF6)FCA^x~*(b(QRadicVyM;ym<i;rVoGQ~`n3HBE!94{WmQ'
    '{IHrC{T&&iN+YOdMh`MXk(5t7%n%iQKSNaXFhf-ITN$ECZC}ldUSx>kgY8?c@`W2!K%n)M%}Bl>M;|13;GGn|1FR-`3|1385S&QL'
    'Cmw>;l;W<|6Fmg0Da9LFPxKpLHKkH$JqO>{GY>8_svxi$u8O@nR6O(J1ivF0PxLq$PxK%e4@vPPz+^lz^po+#V4(;ewvzG0u#t=>'
    '29b=152-H@9%2&+1BgLQClyi^!?bfAp?0_f#3Kd_;!z#bB{9!0t@tYQlwbW=%8Abk!MgqM6t4QvU`I2Uf{Bb_d>9chkufZSH6|#?'
    '7)J1rp8-r{3}Xfr2oo8@7y*l6B4e0AbS5$^VIoTlV0V-RCX&R+<wpND{Pyj`*Fub;!i%(PJdEy!3kr;A2#Nx1F$KoE4pX39btEWo'
    'P!z};K$)eM>Zh$+Ybyn^B0*6~Z%st)A8Yfei51K9A8WZ}!Z<&Mv<>y2>ME(<uzYJWF2SOY8A46;p@&&?_`P9zFMs7agvHNz0z=im'
    'Q})Q-?*ug)3#Jpnbetwh+@DWU^KoE43Czdo`OyA+NX^HA`7oG|*Yn~1`7F@RrY;sgHKN)~KXtewyLvUFG$;KTf61-S#TurK&c%u{'
    'E<d&4Qw!DPWczCJ^hRFpp@X`J>ic;ABAQUh@kLZ$$>)pc=uZFPKY#de`1QkIKm2SzxbSbomrp}EjOSzd^!d}*&mV^mpUj63XKT)1'
    '4u2bu>Z>OGr`D%D*pI<{N2dpxJ7q=D#uRcc*!4Xoxn0HnP@h6II`ut+W12mK7mKmw8XVJxYj8}`HTYP)5}u~p@!04Fe23-5la$Z!'
    '#oF)q(LhZePiwDY54HeyD~?Hn@HVL;jR7i?RKdn}#HKceIqF@UB|)7fxBS+9rebJZk4f9k=P{15Ya8Q%4)P*zBbzfa$&u-^2blj('
    'Qd65S+|}_F)#M07p$t+sC+F5(s8J9ANF1bwK4qy^T_imUzq@Y<XMT(XP^6V9hG6E$Nd3%@k><>gN4aTfEAwNi-LUPF$o$C1!F|X6'
    'v0-w3DV?sD|17l_qTS^O4q}7UJSp!kKL9Ja2xs#+J?U>OKO3q4y%u@cnmwjs>|z`lxfn}azR1wWxD<C^ek0F5#`-ScEhpnr+kg5k'
    'mE!65RG$o<r(15%I1Jp7W#+EPN<Ttu#Q+uSC=VtcH_HZFG0=t1s*BNAa*M54CKh-#@_;QP&l}D_I!$_RSqpw?ed}d|&7m2fU&+mO'
    'ec500<rKLN`7+yxPP=Tktf3S1I%dm?y`CCdUQGNRX(2UxX$DZ!lI}U!HQh-uL=I8Woz^Ep#{QEr1OLe=zk}|RrMNGs=h=Ny(|yZ*'
    'GUg5U$x<0^bRP!)J#=pf4@Cpg$7ldV!~QcdbKK=~oN_p3lydm?T{1A^a48;-re8lUibuj!LZ8l6d_Da7<@1-rhcCnB<8b=+;qo$k'
    'JQsre`srKU?9F7HjD_2<l-nInN*K{SO^EJ?^LZ*(pX4Wpxq+jSYLI;G_3OjEdi01@im$6W^7O(ZD%Ak_`eTRj$Kvjfo!XBDm7C>C'
    'mviehNG)9LqGYtO?yP1$A^ra4ORYP7R8{ctqm-{L)>eK86C)%uCPp}XLaU0s5)$%CF!DR-l#n)@64K2n;gb|G(xz8J+VV<B)hpq4'
    'rkuV@^K*@}Eb#xAQ@7TGvs~Vxr3vXBxH?;s#Xyb8O7osjs??{*{-10g$1d3!$4(yS$!_7;CA)!Rmnu5^jr7OMcac6d(gOzuMf#Z5'
    'q-Uc@pY)Bu>%-3`cq5eZxJ&wk{LPZ3uD@Bb<RR&4!{01f?)#ginoayh`s(5LJn2nnq@VND{-I+kOg2MfN2)RXJNJ#ni5W_H-Xl4N'
    'txpqd{qi!ci1kn1QVs_7qzTL(-iQ^;{<+_Bn2^qeJ>IR37-*QI`i6&DRJiAc=~=#rOuJ1TbZ#NEuGQGm1PW2fMYAJ+B^U8Vb#Zs2'
    'x(GL_8<A;NT$B8hB*N!`8_xs09Q5pOVVI8O7BVonY%qvHnm`QjFqxkmW)5qv$?A-*ko)ohgx4eXIQq1d>jPu`ERj6k$-W<+SL%>W'
    'E%~kRyyQ2+^Gc<#sSW0P9uRz*UJz3CIZ+Qs>)qx(bi*s<S|VA$AS54<cAh4f1WdPpwDaV{hIXEO>}%(#!u;RpM#t}=+u$1ABJJ{9'
    'M<(zo?vlJCLi@GndqiJ%7=0ZZ62Y*sa+~}*bSi=0#<5e$XRScm+o#hjLGoE2!MCA(om*VZe~q228H<ClvN*R=FH5<VLM?US|8ky-'
    'sq6iaf>j0>tKR-ou<~8TABVPIzm(JM<>%qU`Q_^`9}j>3@XO0@!^erM!gxB2r|0VT#;bhRL#3J)CY^UwL(OIPXl>$g@OZU@7fiYk'
    'nFEYTDaBpytQ6*$6s@R*t)P??HiA-8kU=R!MZNxxZEYGkfI6(EuEJGb>0vNc;E0>y_O*_vKygp>3!VEv0GKYtZV;ub6x;6QAM%qX'
    'sc689rB=|Qf@C>=*W0>lkLxKe<N_cBMeHw~BJh`%^o!74x)k??r|6y(o}vd1LfW<vz2xev73+EWQL}K>v<!l)U&)jbcWv6G3Fhhu'
    'Y}#s7piR3J_qjTzXStdHSCi&y75;fj-*dv*vzdQ5@99X9J6sL2jVk(O%++~=tMijwoebb=_3BibNUlD4{;ub+OZ#DvR!b5gImz{}'
    'bwi}_`BgbMrYZS^aBxg%k&kF{Vob>?i?VcZOhr{u4vs8^j^sC7JW~qFZaF$Q>a(TXF}+iC@=Qx9Za6rW+C2xy(q!AgF{QNQ;8<Fu'
    '-C@ctiyRzNA~aO}JH)%cBi;RwgJVhzY?e-wBzHCV`FEs^4LLZL77Ttz&4-NJ`yDcA;dr?AaZF^_Z|us&F_8_szoZ>q*Zz%(kf*EH'
    'Gjf^}fYp*bR&r?j$+oZuREKFp9i~|w{wU>U+Ej;WOC2Vu4qvKI_5J5lz8+7f;p4{|2;1zu6s4Q?<@nH%r@CyJ#7mdEreng{>=OZS'
    '1sPzJ2xhY{#obu7L~}O#KP&Zxw$j-r+DK<#Dn+o`<@AuqrD)ayz!QNdWXXLj)7<9}ho^rshRKmKF$g+$>PK;ArBc4T%NV15CI)Dq'
    'G9WcEMEgwam6QK<HQLF+i?~8-RVB}lBSlE@yF$vLQ71^RA1(RtcrVV{{AKYce}D3Ty{gXHn1=*GwQ#fA&%gnejs6o4(yRlo)T1+}'
    '^y;G<Gu{05`OA9WFxlH-lg(rDmHxSQ*zl-+pZ@*Z=UI^A@icfjzckUNl`BC?Q-b@xDyd?wJmr<Z9g7+RG$Mh*n=%9=N_hk$T0U1~'
    '6Q2{ru>)3`9I&9!UmdWX`z;4to|N-)%D_2S;&i3#@qv{6?tzp8UWp7G2-Sg<Bc@U8A4oZF97q*h<*5THr~ZL7`C;92AZ1bq5<kBO'
    'ZHs+R8F+_moJg7bCsOA0`om+POg_f6d40O%j8B)G`+*QteZ8JJLCS~F_lFD!e9rO*VcavBG46SBf)qvIxi?`l@cp?Ici*4MJo)}i'
    '#siH;1sRY5sS%C*Z4_Om+=0nNeU_}>XvpC3|5Cm_OVpac=zlW(=zlVVUerqQh6+JuBl@3e?vi%?Wapn(A$*IRCIfCWNp)+$(XTwH'
    'OA~DwT)%CR#YqsU0t;^3rDS0aM6&%Hh@}pByOQ0?fk<{E2O?EGm>bm}Gtz3Rn@MG$>T$L0>q-`9zbfVX)P}i%$i}WGL#cbtlYy*M'
    '7-xH++Lboxh_|(i2U!eyU&?uJLtBUmPLrz^o-Cy&CyN3?lim!xaJdH~#)2i;<x?%76T|^5#ocHSvNH~#+7E6E2awzb4q&Og1%qUp'
    '9&#5{`@zNO$%5R%&3SDcFHNBQNN%ant_kk&DdILx5r<C^w|R=Vty9E_Osd&l9`c#jRBMl>rORDjb69jH7xoDrIs^xfooD$SPQO~p'
    '0q8)GA9fA_hcaKtJIZ0d3v!Dmm$mN$Io4;>%J+fXm~(jH`%sGW+V_E6wrk&qQi{Bo$mwUB^IROez7M5R9k<%|f&7S1^^ora`4RFK'
    '`aY1iuIKwu>e5rb4^%;V(0Y02d%h3kA&wjQK8_pt8OKfeK9Ju6awES1<VHTIP5iuq<IY1P#<rg{d5QA&I@Uw-N!oH==P>e%TOP<I'
    'ozymjQrjp-gPCn;%4`F#_?p?~sVlxh1ntPXUS=`K<~z8+-nbyso}d#9j4~+YYrRQQFIXrb1=|;pf_+jz3h0?f>uAAAem19vd`2|&'
    'T7DG@ephk|*!)CcX?_BP@7$qbafbpSK6LKT>Xx-55-&l6ZsjWk$F-+6h0Y}$B7tiw#0;*j08>R%&=_IoxmaCt?fMK!;}`{byG&kP'
    '_>r5ccNSk~imTcFG3)B_{=T&+g7&J#RR|DGGH9ZDsmXIzO`Pf_S^`aUFNN(_O}y@<u;{vp?j?ktMAKGS!Sr0Wpz0vHj=VE}KWA`i'
    '-!G^dX9&@0p;tt$S!_g$^KWaKlIr91+nS`L`rtJ|S#^<*YkG28`Cd#0zfzYKGDd#d$!9u(;`pdPOHqo?<M^IGzN;*b=VUevJ{8et'
    'mN#5Yee|s9VVLl6N|$RfT*@02zUQ^&jkE}aTcfW~avK_F&2}?eU_yKdwm}c6;p<WY8KM*!0zgGkeqxlu!cTF%8B>IB<&*$!L6qMm'
    '^i*DoyHDkm5+jYZrorh8yNUWQ<y2i}1l6CvsH1Ne^%CL+T$vq+8%n%SZLDXd+>QI9l%I?HA~JYo$%H*ogbWmCCk!39xMUq#T(TRm'
    'rlqzIYf9B2XFgdxKX23w)Qp<62zdiS4LQ8H1kzcN{LVv*CWXF5v*PtUx3buam1q&<1|&tC`G+<#|IjV-k6ziW%s;f1`G;!epWC)|'
    '-*JB1c77A>Zd>ZuV2F0NEy4KnQrzFR#LsS99QRtv_jwn`y_WKA-em)Mmu;VS**?j;jA8PL0ZhJx+9^wbwG9TIbrN8QIAE=m!E4@G'
    'eHgJ3sCvlk80|PxM~H1&2Pcb+cGaC`t^II{K>Oi@K=_C?F2i{)&V8dDllIotdQ8O^de~^k<4XiK+VS`X0gZOmtK})99pn6SrJTA('
    'yKLZjm`(pY%!Z-SF59gGae@}Y2Vw;na<>EVAymo5fjB{aQ3m@-P23Aas8<rAvxHNArGq{Dy>S211Rs0ZgAA1NJNyWlHy$DLvyYG&'
    'Jwj?>JxgTC?7zc(%{Tuw%8At~zlL6tK@vViR(=D{Vz&x%pgi8nBFKT3@Jmx517(gYMf+CAD#*b(c~Vt>oUQ?=dLgZ0oSpLP=jvl4'
    'gL<71xF=<wjTPQkOV{*Li_npc`Vr~>2I3spIG`=+aW3M$;W(u&5(PT22_SmO>9GbCU9gT~V6(CiEu$s4`r7P{R&F{J#=s^4bRDOE'
    'DBZDqq~j&Pj0nugYqGF5L9E>jOA~m*u>lD*?2+Y{8OaKzxC_|J)>t6-m*Ne)-cs9lQ)6qbxaJ-NWusL^4K$c+MqFW%#G!L}45kM5'
    '-7>+HzT@7)bdo<YO8yjN3IfL2pLiqt6W_8w9n`{XJsR>>_9vFvpUU<37?3g~-XS#N$*cuA+J|lf-1l*q``*LKWs7Baw!q6hJNaQk'
    'Dj(a_#r0sD5UvMX+Q9WFwS8O<wnSoG++)GFkanloXh&JDi+>DK3-*1!w7%Kyt_#CwC$7#(D>YDWn2hkqN^uvDtf-a-ZJ3Jn)L$59'
    '`gmkqGiu)!<}t$~Cf;Rwr7m4NrLB1Nvm$w2KBmWDT;cDMIkX>kS16q#WBp-?TQX^<T-}Fmir}HhCDQ=@ZEpbfL;9zePeTeH&eK2I'
    'ull5Z)gI0IXM=PaIfNAM|JnR6!*AdIOOYqP7U6RKcl+_c`#&BfTF2pdZZh=GkNvncFP~n%y&OKi{I7O?ReY%3pHEWvJ{EF4`}1G_'
    '^7(H?PdS|b-hQ53@6D&w^&dOfk#Mhz`4x^O>)W~H*edo9@^_`D{j0M-$gn5Ro$9%?LYgW<mK5PUa28g5I0O1PDKW5OIc@gg3H71J'
    '5rQJ3T-lm=YyJIMk6|17lYQEd@;up_b@!Mai*oNQ(u6o&`raW9BjTJjak9><Ggpg#I-V?yJXvG}DPva_o?Kbr?G$VSz>#shrFaAX'
    'hJ)+l-*9zcnOA@w#J_<n;G12EYs#!$>f!8HjI&?WBxt+GU`=EtjzM#L@)(TgmoMMi0k{Ps#MM9LM#T6EZ0s(LjjMyoE)i3Qh=hqq'
    'cMy>@5ofvOK_a@tw>FUx9Q0=yn{NkomITiGbH$ch4q9uS=bHDg?P#K!D?fQ{=hLrWzJC7lVV-id=nNm!5fc}Pyg*}&7?GFb(h*@T'
    'J4c796&>wTI$}^SuAV)teYWOxl%EIqIK?q6&eQ??G*0=*)!}FL<WWk)`pJW1gu;J}1fD!fv3d!ao?c3^ehHC|FdRoKY{%Xg%f;7s'
    '_~PmkwCV80k%0%5@=fCEr?c(w#i__5+YVox%0;y8@WnOJ)waVIClCD7yza#>@EF!yv%rGU4qv>4fm!<_aEf-*<Eu1C+a6z>v`^UD'
    '<BOB_30r%7ane3vd|Z=M`-J5+L3y1}u~`wT>xuCAy4WY3p8wRk%Uypju8t@@*+1nC&6kYOe96Cp2=2~J1h0rOQfzhVci&L;tpGB6'
    'Cnt3dY;q3WQ8Y#hY~E27EJoZ>Ha~esrPJr1e|~8fRLwDUv+TUG<U)S`jv*Wu$Q7_=ORK0(DBy6X*i93`6%3{dX*GWOk@q+ziL}~L'
    '6o{l3eZ0H^%h^1$9ML|1r~~0>htrd~zq`DAdina755F8<KFw^hl*>+FCG&<AfU>Xx(1XD6Sj%W$c+3mT=2<@#zt83ktpU})MGfG%'
    'rcMWih7k%)lv*lAq2URI1}cdY3e6&=GPB=^)MgHS$K6sX9CztK2u8eoshtuP!A2ZG=T|WLdm84>my8Q|0|yr{g9yK*mInIN@B}-9'
    'mxe4{8rpg%o4{f^OT*%wjNL;%)g9`cQllR4-%G5LGM>mieePUsj>mHPo`-pBkHLdb^5ER}2jvP+bEC>@JW~1jl`5OiwK`V6o;N#Z'
    'vfVd-XXlkFJIjTSE{FZg%X#=PDzxqQ-L|DKqpS=IYh%qNCI}QCONt8#lv*+*7TLx=HWj1};X-N%sp%<yQ;ocC)DDiLYGhR-T4W+#'
    'Irs504cN-LkE<JsTvca8FO9Ml*1~GtN;bW=%BC6|*R6^mqgqwuQPfKJ<)k<f+<EE7H!n=#nLo8}a#eWC!T0ZtIlv%2J>{`icHKDc'
    'Tlbd>nqCY~_FvdyJ^CeC(sKamxq5vl&k(b^h$_TTJ<&c5f0p-9o-$W``uuHCd=(1E+*y(ivd0N6`_u5~c&&6+!WU<00|Q{Q1%N<S'
    'eg^@8vbEg+*leFf1u7rHGf6F~^*WQnyykKM8{$#6Qas|zE7;IO&TRrg%l_+^)@-BPs|S0y+<)fZURu8l|5^yyel^M$|JR;Uvb%f1'
    'ZoC?0t6q&>^$y9FXiu2W7U#CeS4V{{#)o((dBQuvjGv#&ZJ3=wN~?N;%+-BhX~+eqh{L)|cFqE8Mk#iC99xq@Nsb*JcwCq{mTKXz'
    'KM!rf9%T1%Mo$<(?8yak=)Kb^@5$1J7u*XdmY~N<DNnt(*6av55tZVu6H%!npiSgk+9jY(WXF9cqCCNaj5{mm$1+I3ofZADEfD9s'
    'xGm#b#bt)vmh+xaoc#zL-PrBK$0u!PhhKgfK26F=^}60=7H^f^A-sa-oCezl;QTHpdK?Lpz1OZ2PJILKXYacaeR)d7wB$q|HX`~;'
    'ZC``SJ_-#kpC8L@jybV~_LaWFKF=iOzI2{#R*ya+4_^*n+ZpBM{_n92`8Q-4+CRKJcDF0#`tb7d8yKsaeeNG#KEuN+n61Mrn2p1$'
    'rdgU<=I|JTaEE0MO=byZ|Cp)H8Nw8j=*cJZ$^B~h`IqK>kb~PlYijbQH)EXO_s^ORvPhnMHfF|&>Kl00gwQ{0LWE~ch+Ah(#RTay'
    'P7-I$;laE=m~k4AP_Bp}yNpBftU1Q`qzx@!`Q|Uf$6wly)Bbr=-7?;eZFv8@2^pU^)zL$;jX=`O5vE?P?&w{%i3XlG)kUMvHqmaJ'
    'H`R0F#y0d2erbnrcFG!6`rbcpqLb&%v8>&*w!SOheEoL#_UqU7`+onxQTd);n{%r7$R6iJ3@Vgk?D~b~g`daF9kGAl!~_qVn6?g_'
    'm^KcaB8mvkIlRJ?M+!~Gh_rv;OlUKWbIzA1g`3G}|LdoJ`}Fy5pV|O;|Imr~4G*1|_Ya+9@S&58K6F@q1Jk#b;{KtNEIf45R{GXb'
    'yK(3wCl8(B73AW?O)gGu|IkTZ2|30;U~E#X<0l{UYISN4J~@T`V<!a}r~1mglcL$@orpEmBrO9PHX)}3O+VF-sLMMkL*AhcsN0-2'
    'eDO=Ac!hs$!tt(8X-+JCN>AbNq+{+V=M29!H<nyIl=j$$%x(ZhX+v-IdX_8b&6e$noLkR9zn*21VYk|yJ(CB=uJ+Z>By%agHV0If'
    '9Uc6-HtSOChLPmScL%dBMajDH72Z`-OJ|WO^~D8JLGiEqpqq(g^!qCtvKJmn=U4Cyu$1P`sZTNvZ%DE+s#yj1=Zc@BgZncraJQxa'
    '{#-qoI>G&!vQxgk!Ur-}@1_-M^Fhp-jf`DAvY9RQ(}e$e`1tFUh?5^d<`FncPi2DFkyEMAI%q0v*Y2UWI*n5)VG2s+22N#Ww}f|D'
    '#?zN3{nclbCsu#$x#z>%&f)5eBx2;R@I}_hgM`DzVNtz)ZimJ30c-E=Ic)TTtBxPd1jGxiLW+hQLCC(Ib&}ihLJvsXXi%4CRp-?8'
    'h@PoQ3h&_xceS7<VQH9Y6U{j@BNzKp+>Niz)n5omHJmr%Ycp?n8Rsm$jE}?cU4%{T_{^poT3hM>K#N-KZ2g<8cDB2FCp)*Z+8M`$'
    'l=8L1o7~#jBY(GC-F|wjodfcBE5#fBZl!kP?YAbun%{oU7y2&3I*N_3z}Zi7`ZBFmP?ghr^x<JQi*k|ft|x1R<m+-?fBcVDtt!U*'
    'DCNM7QJ!5H!hPi2h5HD`7_h9hxWBBmw!5sQQo?<l_?h?M+p<oOMzz<iEX$>Syz9`a)=GM6Rm+#&Z?9@?LU*icX%`SCMJ->?EJgWY'
    '1jdS5+%s0xI$*3Q#i?(ssI^^VMXeOZiqnz5YgMhE>6_MIT~7Y&h|<_u)-eq6nPpvIwxVSn?OOZG3egv9`FdvQBtEnVez6pf@QZL+'
    '?HEtITvj`0nnBB2!Dzb6YNzDn<Fa19Z?m@Kc(vQL`;3=A>tlaet<O&`>oNruSk{_?>Yin_5jh6c^7YI}jUJhYYH`mzRO^6ws1$FQ'
    'hiYwCY_63;Y(AU#eakw*EtPJ$_xxAuw&mv1LZzoTUmgg1f)~DNqsm(selQi%rORwJ!P9fh=IqXeUz)gkF8taKUHG*eT=<gc4#{z~'
    'xPRe0B*)d_tqb4v<+xHA#f5)<<f$An+tAJs2e6vtjqlRNjbHIoo?KSiz40C0cjG(8H-63Sv^qmreu#W9YH|O@cgP1L7{B3zQENAD'
    'd@p@4&WG>2@e7Clsdc-3<9oYt<5xea=a$vG-5cNg`)+&>fk$gOxbd_65FwA2;@H3OeS|l@k6SmsPa8MBPvXWuKjp3|mNmBB>eKd('
    '?`h-4uL+Z$Tvpz_@jc&n<NJ(ne4oLMAH;{jz#Bi9{*50DyzztGy74E(7`&_%H|DmiuXeX8Zzc5*R_pd|{GgD5UvX4Eyn#)o_PcvX'
    '1PN*YY%;Y4dQ+_B>sX2;zeDZ}wYcZbQ0kC7LoM#RGt}CyJ42}?ceBa7B4KGgcX<GWQFz3sL&)yQ(;?&?8(Z1B#@%%~L>M7c%hxj_'
    'dGJLPB2$a|%UZ!;z_LcSwXD%?ENk?_OJ(5veamX-Pp#W^wiqd*O<AGvvetZ1&n;^OiP>A$$oDO4LdZ6?d_6OD=vUtyw5-%akgs(N'
    'mzDbf^0l@LAYUs5fc!8Ab3eJP6V!L<Hm~vQq==SAp%O1^GU3T(P1fu!Yjx1MXIT>j<}Kv_m^Vp|O$e8_7WZ&@Yh6Ignl^BGOKl&Q'
    'w^j;V-r@3{yOr8*O(3DCJgHJl8_Sx^v&)*&?y{1(Z&~5vRxMx8OzqZ$Ubkv-?{%xxq1UZi+<)DwwcXdPU=)VV#ee5+J+$3Q0Gv?H'
    'ofesL)v{7cmHY6r(gLvzEGxNm*RqmF7(2CmJu{N#4+;Qwu@?7W7i(QY%SxdSyI5-bh=H{-iDgaSxm$;}TM2-1s=22Pk%{P8k%?$m'
    'WFo##WSV?A*2~H}A`@jOGEwe}Ol+XY#AZumVzVJKu@xfIg}&4C;FAB;x(yvy_);gcIY5PqodkJ$#Zfs@{l1pm&meu8<Wu(G`CU5u'
    'l_sH^c4_XVqj53NxYRabta9;&%EhzF^-(d}rpm=zDi=!+^2_jjOInn>Mta)G$Xc6h93jll9w7`9CD!sCX2{Symd&nMm}PFmO8Ryr'
    'o$8U)+VCDdvc>k=yz};4ky_BeT`x~ut)piU%*uxzq%P4rraE_s&HPA+EaE7W=bzqQzZ`b0Cpj)he>0)97Tb?GdCy6zG@<1&dh<JL'
    'Ewt5e=@?#H2-JjwvETQC7IJ$*t1ci5Pr+K~w5MP#(t7FW4Oq)X#vtV>SnH^l>aA2}+w~NzwMmj}^c0jgk2R);elwBX-dskG;wKu-'
    'tuaj_pR3CdRSWCaEu3xv`tYiS1APSD0`w783lI88x&`QiREq%mVBG@rkyVQb`Z(woppT<!kw70O-2(J+RxJqhG3XYckBe%-pbu+w'
    '6T~2zLo(_`vq(n0C>|-x2bu)k1ofi0#3F9BNjE{gC_b@>UoGn<s29a47ICaS=q9Ka#VZ!^tUc)_s29a87ICc|bQ9Ez;unkf)*0Od'
    '^x_o1Sj4%`=_aTb%`b>|o#q$ByH4{9;$5ft1@W#^{NfPrI@V24FN$9rJZTTQ3F<}hi$lEYPPz%|Me&P6yz2(t1ofi$#UbAHMmIs1'
    'hvFB9c-K4K1ofi$#UbAHK{r9YD1LE>cYV@LP%oNa5bt`;FNk-&<`=}fUh@m$U9b4XBi{8V-30Zb_{AgM^@DDLdQtpR9SJtXOzRhZ'
    'pKEc)d)gLdtp^ZA>Nld@`;EBF-nfutON&jJ-1?OFeuLH`dDQdR%)V0US?C)FduYakC$d9bv63e}($<IjrL1gyHVav~6j>xImvYyW'
    'm8~D)NTIA;Dsx{}wm~VINLCJ;sClJ+;rhQ`lpu|(aN%pRm(AbsNiNFysaT3Jr1y#h{-@UMD$=PI=H;3!0Yn<zL+C|1)w*t^Q?2Yr'
    'I+fbE6X{f&$o+bL`M6%TWOr0cdwW^`Lw)^^tJi<K^}23@F!daqea6bxpwg<D?c5fH^s5-sXiFpbBvvH4^^@2^ewWdUSSjwlh?P3@'
    'B4%q^m#&S>MgxqW%CKRl<SyIuj20nD)bjOde3suifX-cud+6M?4xn?_;yyZesr7sBCZ$Q*Ig(>AJH{+q-`=~77y}7LjL*DT2u7sI'
    'LR7l#1vQttF;~ZQAcgddFOc|6H$fegj+4EED-!guE#>RGO>%!E<X~&3r+my6j2vuB@rHw~tuOig)yh_^)>B4*LAiWvgv%m?{NVBf'
    'A^fP{W19QDW1ChV0<<8>Y;V(K;Wn*#Z+Z)oEZnBaZf(=#x+t-=GKvK`eCPH#we3>@L3WOYq*8I_<0JX4mWIjptNx8PX7zE{n@&*o'
    '=_)$7w%E8&Q<V4V={rY0%ma_1dyGv9h2DT#Dc!Ma2)>ltiX^g1P$<7+^iW=kyAS2Ix=f&5!y6Cfwt7eOS1Tv6TEhbnSBP@fghsi{'
    '@*KN7gPANlwoTZr4ja2mLJ)qamII%Zi~P_cpOjME^+~bhkWY#wx8ajgYWqGZw&o&g{+@@TNPQ>ij<%7`?>YTgk}?ePq_sGsP%U43'
    'WXnAYGYZw>u0yt^h#aylr45JdQrmaPE|oWj?1T5uL^n&yMrxEL+dZ6!_-zg+;=Q04OH6yqnepLO!8*27+3MQ?mXpmG8gW$@7t6_`'
    '?|qY?<<qOJULVgqy;`<=u?D5d(w|{z6jGQRole{yC2J<3-ow4EIfI^hxVIee0#yu;t^LLkFHqc{s#40~!@cFy!#A#VZ^ZCSe*fsN'
    '{u7X11VWq?!5Dcu*a=Vr9#EWHAka}BP@Fdcfoyf1=pInncyT}-AHc_g2h@3b;x7FPAEkpoJ!5&29k+nM(lPC?Nymr7A|DPK<cH9S'
    '!%j{da80snF?R>KCfRSq+?Co5y}Y?@jB9d!#_K?m?h+g6ymV*qm+xF`XXnM<m+|vL#$O+2IbhS2NCE`?w`|S-gVrqdZBscx+tkgi'
    '1g;tNy|qi_&0G5r9>JM|r1djtfm5@*7As1~9_h1LUq{M}oO4&zaTOZGy}{vHI^Me&N|T*C&{dd`-W^yfpS%N|f%!gbx!XN_T*Vn#'
    '^P@9v&!^TIX%)m5VQI6s;LhyH)TITKsZ04*!jn=DW$IGgOL$W2o)fg3Nqd5pGigWAa@A`EC+H}3Y~F~oM?G6Tk2o{>a*5{=XBKH^'
    'rYDe69(&It&Wtf~@X5-V5nBO2kCa;VR=Iw%a@Op;MV1zAQILC=vnH?KT&-#`$L@68yIf5hwdvmFtOI=n-2(IxRSOULNV)~+gH($E'
    '`e5Ax^pRDI2>Lka7NC!#YLP%6C*1<{aaJt|^fBlbppT1c!JrT2-c_0)2GJanQ7@WBGU`R~NIA-O+`CE>)QjR0hqzU_ca<in7sV$I'
    '@vCz0at<-9a_@2uajbIhDos!?idP)sS>@hUnxI}3w>ZSL%Dt;JLA@w`afok~dsk@!dQt9O&LPfK?p>t`>P7Pl;$5ft1@W%a{DOGb'
    'X?{VxtK7SsN4%@tyPQY7tK7SshbQepH$lB9e({KRm3x=-h<BBHR}p7XFN1D^dQtr15$`JZF6R;ND)%nu5$`JZF6R;ND)%nu5$`JZ'
    'F6R;ND)%nu5$`JZF6R;Ndd)A0cfIBp#JgVe3*ud``33Q=a_@2h@vd_3aslzKa_@2h@vd_3asi47ieCbh6O3*GdI^eO0^;4^bQ9Ez'
    ';+KGUHw4`T^`iJCAl?m0H$lB9ehG+ol}6|S;@zP5B_Q4n2i*kqqWJ~!ZqWRKcsFQ%LA)C@zaZWXieDn)UFC97njpba@k>O!8=Y=~'
    'dQtom5%0#Jo1k74zeL2lG3h3#7sW3T@or?@1ofi$B_iI92i*kqqWC2u-i;^S1ofi$B_iI9gKmO)(fopVH)(!Byqh$?Al^-yUl8vm'
    '#V-l*ZVI{y>P7KOLcE)jZi0GI{E`swCe}?*FN$9h)X)yP3F<}hOG3PxPPz%|Me$2QyqgBy1ofi$B_ZA=qnjY5Q}Iheyh~0uLA_{x'
    'LA*<vUl8w-<`=}fr1=H$E-8K?#Jj}03F<}h3nAX6gKmO)QT#%Pcj=^?pk5Te5aL}LbQ9Ez;+OjJ%`5wY;+L9#W8FmY3ypcu7fqaQ'
    '!k~%b7or53D1NDVBGye5ztl(GbrZ!eY|wB?H`(!=c5Kn_D2`%>ekbcDh%Abu*dwwij$*iqilZ2=qT(oqt2pQ;Xt;`_7_DMf9K~oA'
    'v*IX5tC$r>WweUf>n32hS#eahXt;`_>dV}^iQ=g2(Qp+<<$#9Ex(OPt;+GuJa23DQho^ND#V?uAa23B~M#DYpCTO^dUuwATx{2f$'
    'U!!?fO%6siL0j!$RTH$;4o)`#!##M_1Z}lLP)*QQJ4Dq4ZM8#EP0&_5kZyv8%c=?5YKN?vpsjW|s3vHu9VEYai?-U~q?@4Oo>ddH'
    ')eeJdg0|X0@ry-U?Wp+0qOEqcx(OKWQSpmKTkWX$#iFftRQzJmRy!(wv1qFulWu~BtN6vDt#(xW;?Pz*Dt>Wjs~r`;IJDJ{N8JPs'
    'SMiHOTkWX$#i6ZsRQ%%5Ry!(wacHZZjBWykds6)3&{jJsesO54ofN+~wAD_EUp(4sr>L8t;VORdXsewRzj(COPKsYV+G;1oFCJ~R'
    '(?K^u!&Us^(N;Ste(`9lofN-#wAD_EUp(4sr;Ba^hI>~0;?Y(+D}D)RtDP0U1hm!8ieCcSYUiMvpy4Wh323XG6~6?u)y|4v0@`Y4'
    '#V-MEwR6@@&~O#M1hm!8ieCcSYG=hS0d2Lj;+KfF+Ii4T&~O#MM6}fg#V-+UwL$SqL|bi8{1VYt8@z4;hC3*JiD;`0ieDnyYJ=jJ'
    'h_>3G_$8vPHn47jhO77`qOCS4eo1Jn4T@h9+G>O1mxQ+3aMn%Ga23BKwABX1F9~h6i{h7rw%SGUOF~=i;&c-*+>7Fugtpp6@k>Hm'
    '?V|W4p{;gN{6c7}T}U@U!&Ur3XscZmzYyAL7sW4xw%SGU3!$xcIq4>7xQbs0ZMBQy7eZU@qWFc-Rx1LzYJ>KgHCDF)1GYx7458g-'
    'jp7+b+szuqG|)C;jp7<;9I+<pHgL>}Z=iX^8pSx!K4OjH9B3f1MzIdGkXUonZQz&{^FSMkHHv$nk;EFsKF~^HjpCnbCfUGP_Sx>>'
    'ZIu>bktMkL(<lbaZXHZ%<&TW8#-D~i|3UZy`s$+mjN_iqVRz604O($UO$)dYZBR3@@BK)M>mPBNG9X}1{RoT91&8C=+>dFY(p%5}'
    'u3^$sM#|cISh)$-%%cl8LBC7{IJpAWY@R(gK|lHYLKKCXkg@M3SQ7>ApeWRAcUyF;$-A~8OlxkcZS1|!alx(Wkk&ztEI;%p4y7h$'
    '>A8c~yd?n6vnKuMyMxy}5nXrinqT4O4t|QyrX4pgpI*Mb96rAMuj*mSQ(Rrml(0v=c*X6U{h~F6;**&B6+Ij;3dsB76h{zp9Ip7q'
    'J3hV@pLfqEx?;TU(F3EAR=ClvvoRQmMp|(Udk)VP7x1Zbv!d4R?3#);C(fhG1A&?wY}F!ND<s?Iwyyd7x=dyLlPT0Hv=CgI3Rbs5'
    'svqP}1_az&Ax8F?$||H7%v2U&kV@9DNdg|79!aOMu^2~cR7q>xqZ&`VxE*S!FuEOT#Bc9*sDZBC+aXMTzW8>iVSszLgU$g6Fm`Ip'
    ')b0uuX?MQ8g-9b7prYU*zNwbf4WX)fWh1t6wwtu0`Yodi!nuv49n}T4e?e3$?CpX$J&;#TGEX}E^2_k)EMS1DYp7();Yqf<_1uzs'
    'RY%XgRjY>My;TdHRSWA?3u@USUbeWgY_Todp9i&WX>;Au*19FRZjYo&#ner)QJ3Vpoy`OIF1TklbI<!hOZ9;tFAK=oq;7V{@DQ%f'
    '(%ogr4n(om_tULa$$bcr`hIv@m9u>ylBYwvb_!QlY_Tft0kAII^TEwM?<0NGXF0ek-h!MM@@n)B3c(fdu(vASB@o9NZYdMds(8O4'
    '1bZ)p;In@q1Q^rq=o{^TWFUF6zG{e7%iq11%0bqCI_}}nS4;2SA?TCsOH%&Xtfkd_hS}u~Xt-)%f-J-P6Xspu{c1AV?WP<Hdvwb%'
    'M!0IEo3dK4C`7nQyj?NAx}ZNL#@BbDotak0^lhU}-QwFb3ihp7Jd8KAmOR54F)Ag`5F(U3Lr7i8GmNr13||ak1m5jPp8r2{Z{E8}'
    'ZlsBQ6{7+F<(>iWV_+;W>#eZ`X|;l+g#j-Xg*;m|TbJvQ)NA;=J0f@_BQx@St9~tww=mPH;!85gU@#cR!yvwl`0)CobHP0J2|<mg'
    '`iZ;QLkM?&q*b~kswXbpt0yjXt&*uHm{sv!<huMoJ#l$ZPuBH2lDUms;kQrIXG$(vlae{Fn0B&%M<N@sV?XtdpRJi!PuI+AdCd@t'
    '|4^sI;GeK)HKn7tXqeZr>XhS}dHZP1ynV1{-VSTFsTZ08owQ+Yq;*%JIG&Q;k88Sx7wR_s!)p^D-alPa|9nm5HyNGuCgUg=<tG_k'
    'eUeei6Xa?h$0k|WF@Sj-Uvv!kbm!shM9BKtDd6)Hq^k?+>7f})sv}w12rtc%0K!(*O@rW|Wfnt_9kk(DvTYaa(>y^g2<f&*_6T18'
    'eV9IY;nWQNa%u)IpPIqnpPG2LU_3Sbcxs05=+q2BI5izRHZg7BSVdzMuXq*ir)|ID;^<l>sbl=OFq-jT5+VYY4}+%;OV>WKkQ><Y'
    'ab}ifrfh~&CxVmJuz^Iy9(UH)kwkUQ`u-2~;_}gn)?+8;I+Cc*Y27cLv^XXbYgd4IC+68hP%iRBVpbT5ee&WQ)Ohk#l8aW>%%gA!'
    'IX5=+qG}%fZT24c%}Gaa^bfN4xESuU_c#poA4l-^LZOg8ZJ$5FPm~S0dCf3A;G<I*FIM;_kY=S{=+hs+t-F&UrmHj@^`9thDaY9-'
    '^QCv{y7o6#SrV)=cK9UOEKB-+?eXPA!4sSGqqWB;6>rx*nPKgB|2J6sma7c94$o+pO6pDda7OsV%MRz{!~|##-%)&cI43V9K!ai)'
    'VRP5hIWhZ8KAqFaLX!w0=jev=$KjYH=IC~*=ysxspI)llr6kCIzHL%wddB`j`+Q`pw6xFX$Km&^ghPQ3FRS=$A@YsyG3z_+{-`14'
    'w1wi^oVG6aoVILR=SMkhU4D?$)@7@PZT(V5Jrk=v{+@*=iP@o+Z?<1PJ!2}7-HCjR*N^V_7_l-h;$wVf@mBccU|%SFa*)r19M#j='
    'm-kA`h-Bu9F9k2;;-)Ml6rW3Q`Q)XvN0q)1`SR{@T@3c_G1QaS@nq3m1*uo+X%;xB^Xz2tN`3;vE8z(YJ+>2{!0@W1!j~8je)BJ4'
    'K(8dtlSwM5;t&03+QZ*KknT(Syr7(#ab729zqDBXnJd?;@Py!TI4b_e8lYG4YL-Ib*(~)9pmQ=yJtA~&%u@L6-kIy`TaU6?>Q#E;'
    '%=PMVK4`DYTi++tqQ?YvFJeWlp8yIy!egE+wHACIY|z$>OYL4564UxmZ`SSg^7Yf_51-IYJGV*LE2Iz#&yYeW5+Q{ip*VM|t=&DO'
    '(AQLWH>=GMIU;Dpb41Rk_05GLw0{B_^!h<m&Fhy&)x3_+5|u)gcs>-gx*iH%C$|3Sg<6T3aD-O10SZ7;D7>z^3?zl}2dn-7Nb2<?'
    'AgR|+fu!E3XRB^bimE_-qxBOPs7L&cbQT(Y_b^_sAtr?O<~|`b{MHgek5L_O9wmhKnB8ySjQKm>#b8k5A`@O025E<YDchYhh$*nU'
    'kwJ`2B7<OF!8-;q&fGJIap3`j7_Xl)2!H!fVi5lf?dS0+&XGZkz#v66{p*KMSD}pw2Jg%akGPp;X3T1P;o0riH=n-zj7emhBsb&J'
    '<Fhs|L=g9m!`eDdcjsK6Qo4tEdXrxW^Msa9cd}Lbo5Uz$XQb_H)w3f40X4UCv-+h+gnjy+15}AW=3#C<ABi+SD;dz<+FJwK<6Yk('
    'blx+mW8DJ_8h*XEpuP2n1q~cH{X!0mt`W<RhoDX`RDycPYw8`lr>o%8v$Mhm@hKlDe}+}}7NiL4{qmBPx1yU0if^Bi^R_=FcUsy<'
    'Z^?Q4;4L|ChqvVZrYn%|VtB`wMVuj&Kf?!k_cYY$F}0*XU4;MKQP*iJoz_l2cv8bVbN{3U{AdT_#$PJA=O($G@qeFv<IFR$NoXWt'
    ')!b7^uy<!j@O4jAz|m#Z+`W$FoTy_t|47He?3n`r^9!}_gMd>bpcnKjd}{WjUm=7^(yyGq*RLw5N!G7ic%)ys_*B1g@tJ<*;xiT5'
    'C3}CSV)D+HovDa(5_v9%Cj&yT((Ql{PV}+?dHs~xG2g(qC@}Ifv)-HMUoh=<YGv<Hj~E<;nECUOCjxVN4trsH;prZh5AWW+K|1*+'
    'O@Jw{o58!wX7Enl4Bp*uhKekbJx=v)*_+MagRmJGr~7ah<nF`|`Pm8N;~jVQPLg_Z`PCzK=;7k!C)gs752!xA{0dbbzEAG)Wz>U1'
    'z&?GUuga8nMqhuN-q40}jZrYG!-Y{Qs%T`CV2sEpp@7*%MhS*aoz5s}WE4ai-7`wCf@?A|P6@(OXpYg&i}4>%AfZ!3uyBV8GV09-'
    '0rlobS9OTu%}gl2-syAu*f7ar7GM5+{KYIAVIg0cmk|fiGg8ASFyt7U_VLDxgD{zM!w|=YMhr-KeE0HljbfZ*baD(O3MjL{=ICXG'
    '3G;PczR2bnWX_4<$~j>?*P@JDhVm=tfEXJpB$;z!x^fN-VyJL)Kx3kchr~%Y=6h0C&I!xdP|KW?^b^j(ToqzNBXG_*$0Wm=d=er@'
    'Vcb^9%bb&hyar(#8wQzk5IS+;95&P_a}GXY_;{#E<{V6N@pw71%sD9woHI(fEWefu<yX$J)7VhUoP*GUhYXO7%sJUyIfrelY-P^D'
    'xAY#*QGU+OOV8Ocs<!9sE)9h+A`=~1eiqtGSuQwnlFT_d39luNESIy)IhbJL(r~~>1k5WcG=y@2bM)9yi<|@H!aK|Ci$>&}K##SZ'
    '8~U-Kd^;V=ubeXyCnzU!4wOHB7c}6DX=1}5a1I-46gekgfcY}iG&W2k=LCAl?7`U)C`c<c6c9>mIkbFt8_F4a|0o_`M4RYFc^ovd'
    'fEiB3cKOmSv3A;s?X<nL%e-BX+r>+}iM2CIY*zq^tliAp$#gMSx-7h%Oc!&d%gWkWnJ)H9myNfR>0+;R*;zX$)5Trs!qCk@JDD)<'
    'N*H=(Y-lJ`#$72xkB=P<y-XT^B@I1EHZ+uJ<FB-#hsutIK_*TRh~s%fnK(fpPT&n?;sk*>d>=-cI8h)D--uBrP85j4cVd!>lLX@M'
    't(auuB!M`5FD98dNgxj2j9Dg57Kp=lW0r}N1>&&nXp~4CqXgpYyrD=OBgkQP?*VFv#4&;(Hf%o{SrQvT5*x!Cio`L3C^l?A8d(+_'
    'K^7aw8_L8Hgt76wp-db>8XLABjVz9hAdXGs4Q1j8@|azM2}TykMi9s*^M*2U1c7WO-cTlvAdn5)k46^AMi9tm;SFWt2m;x#{b*!?'
    'Yy^R9_<ocHvJnKb;rme*$VL#zmhZ=&p|U%>{-Hj`bJQtU{NHYv_(4Ry2E)_-ECkdH{7XHD<@hDfztnSBvO26E+jCfsb=Z})V6`+W'
    '$NT9yENdMzT`rwLCH|bQ8~lU;Q*7V*2?IvsGap0k{ix!&GdNsg6@lfGz+(Q5Q$#ylV7>t(+WzF}<%0-3ChLVkgm~$L)U2bE$RiV8'
    '7)T7)PWVVp&=V(&B>77xhL0pa1CfX0CBvZ;K9bCXTJ|~;r|hK@%SPf9yEaVz=Xx75xD%Q*UR?B0g{HbpZ}G~*w1xc_;(q^K?YHEg'
    'C_wEqOFJ`$eY}5R*hj0+fBNv3*Ppg&{h5Gfu7CU*{0YvSgFnF;G58alxefjV3^tEG{mdq2A7m{Hjwc+g!5=0GoaC4rjbtY~=7JL('
    'bIdGvvSThd$uYN#4Q0n%aDroQ^aKSbJLZBD9COU|;AO{L@PcE`kIoJ+JLaHVaOsXz^|E6wc*!xhj}2wVT=0TpF2=E;?3fE)aLjSy'
    '$d0+-1;<=q#E~6y!3&N#K1bOx2jv3itYbsjF&Dhxm}3pYjbko6bIgSs$6OE`bECgIgd4|P5FB%1bRmTs$6R>km<u<Kxga>^>^wHS'
    'am)q5F~>M3+&Jcf<d|bay>ZM1!7<1DYvIN*7X-%~TgQ0gn2SPEMfSz0WzLC0Qc>n$jYj62Xatw;NStV8&WZMMFd#%Ha}K7Be<<am'
    'mpLbTAs8@9xhUU=3o$+pBZZh`&XF#5Gbx8RyTyjWwHij8q-4%XLeA%4#)fhdo{)qjJZz51$efdmAahtlD{~HBn|{cv$;q6P+!M}8'
    'UgjLU`}~ksQ;<0)1>v+}Lya=$q$F_8xRFzqIR`H$Km1}=GUsIVM9;}u=A5jroWta5HZten+kOw1BU_nsvV9zY4B5$?lbygh<3`S2'
    '=A0}f3ucj$9AwVPLEs#=98u<+9G`@da*{a*Q^Q~I83V6Ir9{qwazW2o#)k5Z@u-AsmE%T^%7~l;<&Oi95tF)$4F&Yu$N*6}k#nH@'
    'v4$L#7dZ#YAD>oH$$1T+T;LowR5>#%ls}d^@h0balyaW)hH^fSsD*qUBa=t1WzNyUm1D*LTFxaErTdhl_8427>eA3MNbynZuKu#Y'
    '3XClm`K4XDv~#ST(_%YkF6}&T=jC?c(k}3JS#0OkrCnt0yi6B=rAy-NWV-k(T{3GIWV(baT_)a6rc1ceW#;W<y2LA87S=Axbct8G'
    'th}8}mw2Vi#@Z#BF6l~_owt+elCE@Nanh)hOqhHn42zRSon^}8D`i-mH0msqCSOUz;-t|ikv2wMX~W{A(I}BPMhV36yrD=OqXpuy'
    'ZD_Pe9HRx|MBY#&PR%pV8?udPj7%IO5GV77GI5MRoQXG-iDL!gu)Szx8Ega@%;Kcc$U@i%LYT!#qmiYs5u`ASlSU(pVIzoP7AK8H'
    'mcvGn!z@l3jVy?bAc$F<G#XhF8$lAYIB7JpC^mv9Hhe$Ive*c+*zo-*3u7Y)W5f5OERBsIjSb(AvN$$^I5vDg%JSF<^4ReGC<|mG'
    '2xP<eqb!h(Adn5;kFr2Ef<QKWKgt5x2m+bKNu!kovK0g}i<3ePkvLWm$Sh6@HALcAK_Ig@Dbx^&V+DcC;-t~a0@(@z*|Pm;Wr1u3'
    'fou(LC=*8z$ky_PGI0cfY}tOavOu<yQtWv{nK*(#wroFISs+_MAlt|r%ES=_G7IQJ4VgHCK(=f@T3H}lK_J_SH<XDZ2xQClqm>1+'
    '6$G;7`%xCiRuIUR??+i6TR|XOz8__QYz2XA`F@lIvK0if<NFZ=@-@OA`C6yUa0~8&TZrsJa>Fe|{v{BLPY@E(fgls=uzv6&@e}+*'
    'bViz$=l#I;W_9d#0YF4oQXz}Dg@|th+{Qv9rssc*TZqp4yXbXWLFdnTbXf-{%t5>a>7mLMbHE32f*f4I6VXYK1I0QyK@P3}is%H$'
    'f#xGQK@P46is&TB0UyZ;a&SdZL@z)N7;Yirlh=<C6cKN!KEy3VudnHTDsCZqGh9v_V&n&IA!5Y#?|@r~zT71jaSQNc7;p=De&Gv0'
    'nP3Zl+TMP|i-<n-Pp1oNA^LLlXFx4Pf4UAfx6v_F978QcU!VsfY9V_6Xs5C)`66l|df{5w_`*T-^0lz&rE6iMOU}#J!l3+dR3>`)'
    'T3GbLwXo6C9fN!=49XuzWnz%8g~cFT3uBJXAYTiE^2e8ZVvw(e#UNb^8(ri<z7`gPggyylLm7Pn<w87f9UIE%6DWUtMI#0oeG-Fo'
    'EsPOIMxVqWpikIxL>YYo<xe;#%IFg)7cTd(FUsf>D1UsRFh&`D5~GAZVGU*UNsQ99Fg-Su(I+uV*TUEwW%Nmm0{VnEl+h<pE<}Py'
    '28c5H1j+@@8P_q%=o2Wva?Th*j7dhHK>3w(*g7T|eFEiI&KWOi0}W)(Ndo%Bv4%4G1j?_R<3<UPWb{c)0{X;_QJEy8PoVtDIh?98'
    '`UJ`!V+dlB(I-(#T+KFemeD6r{`eAe%rg1}%7xQv6pvX(pFp{QTN>9f%jgp*7i7+OB4-(W60?9lVN}gB`UJ|K$ef#e%rQSfpTsPq'
    'PoVrsBsk0Hlb8kc$=EO{8GVwZ7sp2iNJ>VZK)Jv<+t^S>pCl!rPvY26MxP`lpijnam6VJ=f%3<C4oE?fbCMF!C!DG>`UJ`aJ%>?M'
    'MxP`lp-&i9W%LP@3!F1-tE6T0NzwxPgb_!}=#!)c^vQ_MOj<^tBrTv%#uGVd8GVwpfIf+As51H_X#su0zbK<mlJrzHpQDUENm@Xk'
    'Fb2>v`Xp%qeKJb&q-FF;(gOM<j$bq~`Xm_vePY+Kp^QFBMnIp~FgBFYC&>ut6Fbh)$mo+~taQr<im$hPM*nPT=~pl9u9ti~Yv-g3'
    'PzhgJegq;&#!2^|p!j<KDYAB6y8e`mzg~Yzyq!!Jf2B+2?PR+6D_thmF35BVSGvr+olKW-rOU$FMVT(~N|%+llj#z#blG@2nJ)24'
    'mz}jsGF_5z4^{DoGGUT%4^^{<S*A=D?x7mqP$o?lF6mm{P^L{5F6pvOXq8ADs|4bB-cTeC=A?ZHB1l$?#Iaf+PUH<m;#e&ZC-H_N'
    'ajX`I!*=57S?S);2*jCqLzy^6AP(D$7}b&*T7ftVZzvN-5W);ZkgP0)tssRNh#*;63|m1AGY~<tvK+R89A+SbWMx5Y1wqU}1j)*h'
    '*b0)Efe4b7MX?n`F#{1KE6ZXl$YR6yqb!WAAdC&)kFqqjf;2XKKg#0R3gX!C{V2<0E68KR_oFP3tssyM-;c6Dwt_%5d_T$p*$M*L'
    '@ck$YWGe_{!}p^skgXt)8HgY`Ss*(>ATtmF)DVf|1cA&z1j)$)*$D!ffe4b51+o(aG6NAn4Usrb5XcNfken=#ogk1Ih#)yxAUi=I'
    'GY~;?vOso%KxQBUs38+a5XcNf05xRd2m+ab2$GWpvJ(U{0}&)A3uGq<WCkKgP8P^c5XcNfken=#ogk1Ih#)yxAUi=IGY~;?vOso%'
    'K(>58$^zL50@?EYC<|mK2xQCmqb!h}Adns3k5NiV5cyiC@B~DVSo~K65hRTNJ^>LVeCqrOh#+~bo`DFUj+khH_hU|p7Qj?Kg9sAl'
    '2)+XmB#epPh9;ATJ@gnvkj}4wUqJ*31Dv-Yf`s>NAA<-IJ_h~>M369J?_&@_!U*X@5JAHC!5@PN65iB(2qH-5_rR|pf`ku(KLimZ'
    'pKsq`Zk+_B9)k!H-sOD^B1rgT_(Kpu3Jg)lKm-Znv5!FnDH!+n01+gN+}?o*66XCqKm_Yc-{jPqPz0a9Okci!MjU~Q?d!!Q%y0xy'
    '7*05XbiTSg_W@orO7!2HW}7v#nK}Ppvj(1HL<_Qs9x8tj?@A%a&dv}7H~HuZ4pDY?;*;W+hNGK2B-z;+gyh)#i}Di_Q2scjK#EFs'
    'c1HC$r9h$t#8N}^#7!Qp?CiuBxgUDFqm!MTQOHcqJi$@UObz9av&5z-XQob3$V@#(*iw`;Q$zXV&|HdgW@;#Z;wF!BW@;#Z!Z}IK'
    'Obz7%=Zv1<Bxk0Ea^aFD`=XqgIwc`9HDiDzXQqboE9ZDNR5>#>lnZcx(J`Oo%+ydW1a;X^We5_KKL(PdBtwv({P88tlw=4Jlnb0Q'
    'T<=X;h9IRZWu_j7nq>$Qls^g0Wf_75<&T59Da#O~l%+RKN0!Sn1Sw@N!I7c(3P)z<S@sedIpIy|hf##=B`|Wr^v4gQ2subtWGKF3'
    'kuz^6L6H+)z<wA-Xla$t?c$X#GjAu;C0^;W@OCm?(v>dEF3U-#OS;l!<LzX+q$^#RRn}ts=XP1RY^8WZnJ`(nY^8Zai82}Qt3Qk)'
    'WThn1WXwYSFp2;*B-%i+a1+h3hFT&{#+&dDqX@YrxV|(Lh!c22nK(uuPGk*@OdKN+C-H_dag0Em%o<vmI94Fe#2d=Qu>x^s-cTlv'
    '6Nt00hE67q6Nt0&hB9%SK%9*=6vZ$U3&h!ZLzy^&9A;63jQPf&_#853DHy#Z=HeyEioZ5hyd<7~DN5HU9RE_1u2DGNPnNDxSl&;T'
    'X2txqS*z344?SO;^BJFgzVnj6j}Ow$WrUDC_L5{wRPfj>khP8XUXrYxe&Q0y+Ffrr@Il<abKd*#S5FJ`l0XgaYPlw6%sL3J7Cw@|'
    'T`kwdj2Tl*KlGAhyp+#65k`^(R|_9W;;t4Wj3i%OEtZdjg+-W`B<s_QhvDKS$#~`c@8BiL^-*QfOOg>s)4e2%vg=FVeIhT(*Z2SJ'
    '{fEE2$ER(bYM<BFH|ev{=Qru0NPLq%8-4pGea07^@2*>9yzG9zTaDFEu3Kayp?e2)J{uX`n~i|(9f4Na$mrf|q(>jNv7wCa%|<}?'
    'jwVYsGP*aLC+J?VOhiL48wuSzAYZeU(Y@J9=-zRtRz~+`E1`R*v7wCa&GrepH(MFqo2`KE9sMiW%IIDwf1KwjTN&M(t(04i4OK?>'
    'W-Fn4*%xJWZ?*!u*D|Wg=w2v)!Z}Vx_hu)cdl_+@jPA|uNp899WOQ$KPjbs;C!>3_6VSbUjxxG8I|1E0dIGYO(Y@J8=w3Ed8Qlxz'
    '0_TjP!^!C0>?Cw=92?5$UMLsbmg5|~jPA|;3A#6X8Qlxzg4=SOqnFXWQ2vB-yo~OJ^2ZME>}7Os_5!+hys4GFjP8Z<#}DddFQa>*'
    '{Bb_Z>}7N>lnZxJSVI}zo4u4<Zan6KjPA`rK=<;7GP)Pa1<o1Q@%(z^QT`Ygo`a0;h4Lqy6Xe`-IS9Gs80Q2zw;Yr|zW<hkoLdgc'
    'AKyjELC!4)<xgZzkaNpHxgc{!2@vGmaybgQ<(LGBTIQT6<(3=g80Fk@Q2yBAouiyv4$7aLR?*3v6WtR%CwiH4q8A+ABUPjPW<8WY'
    'Ijv%pIVVQpv>F*8CYf_$67(Fl99ia^m>=h}%t^_dlk}By#?WO>M&_Jk1er6+)g-@q4&_(Q8J|YY$;q6PobdeX$T`W&oRfs`EGLc}'
    'o`v$qnNV|*!?RE>$Q(9DIXnyHPh?J#!?RHSMCN2UJPYMQsAT+Nmcz3-3*p%@RFbnCo`rJJN0$W$Ci6pQ*?*Y@|E1;aME7MD+?UJ?'
    'on`N37QC09w-cS0S#Vx5AG91o%2Eg^@^&&^1lMKa?PR(LAtdI2mP1Hc3L#CrolF-Ygv8v>atJ9)A*6-3lj$OakXGJKri&0lV!mfN'
    'gp{Qa($3q-bP+;GEEJUG7*ZBvNSZg4DI>*@_!g96NM4CCq+t(Y4S_aTEJOkvZzvE4iv{9%)=-KeVX;7*z#9t0!D4|pkvEiyBgK#s'
    'YbeE#uvj2Y<_%@yNHL^|HIzg!77N6gc|(~vQVeO~4Q1j;F{G6>l%y~g3&h!YLzy^I3~6T#B{_`6!uh0lLzy^I3`z5bGI0b+JYFcl'
    '8ZvPNQEd2rlw>g$3)u|$ew2hU77N7T`%#j{SS%2S??*`-L$M%^4d0KFJjP;yID9`!0vU@1;_&?_31lo5h{N}zB#^OKAP(P;vOv~?'
    'KsIbYYFQv_K_HuzHx!AZ1%YhXe$=u+)`CDbJ8viwM+*YkD&9~gjv$aN+mBin$XXD{*6@ZhaRh;E*?!crK-PjlwvIQHi6be+o;Q?<'
    'BM4;6_M?^svK9ogjl7{u96=ykwjZ@DkhLI?ZRQPS;s^rSPQ0N^96=ykwjZ@DkhLI?E#Hr_K-PjlwtPRz0$B?J+4B7;3uG+_WXt!X'
    'EReMzkR9KTA~+%Pwa)tSg%YgdA73cJDiVAlurHZ2eBpAT1nOuBa^ZPDM$BBv`>`j;h278C4Xl*!pc3$-v$w%l{53s>N<bAKA73be'
    'DnZ{uCGc1O_(BO*xn6wWgNW|&g%YfCeUWp7N<fWdA73cJD#DYTd?eXCMvh>WYko|_MuMrGAEHOFitr>S8wp-ue+VDJDp&Z3<s;G8'
    'mmdpM0)8{*@r4qslK&1+3Fx=nk&>Vi_+uKN5^i!Ygi6@@n&!W5%a?7%D<#3V?-!i+h?T%Xl9&fp0*koIac)CommNo}1pXG-b`5N9'
    'UOm{Z*8A&~5-wGw!1dr>g$iQe8p?&h_2AHj3S!_I%LVMa85@d$Yb?JyblpBQlmpjTE;w|@FUo;yEWbK*8FA#mHI`o;x}FVH3|wRR'
    ')uB7Y^q_(mxW;lJ{K&p22ClJO0LyG+LoslT<yX$}Y^Y-38p?&hH6N-NxW;lJ6tD~p<-j$T3!F3ZsvNk+a)EQkp~``4EEhP3eNhZt'
    'W4XXNX>2G4uCZL;oIExZ1J_tCBvEu@LoslT<-(<AEWTc9W{SO!!kuO;zTRn$yq$2R8H=x1nwg06Nx0FB#n&6nnYR-zG-L7gLi5Di'
    '$#h9qx-gyIXPGYfN|%MVlj)MLbYU8Oi}Ih^VUYiU{~0TYbioU&5B$$qL8J@bVtwR)h8kKVOwdBg7R?)qlnGkMXT$94U}Vx5A)k%q'
    '4Q1LGA)k%o4Q1jOfjG>*4pt_P6^IjfLzy^MAP(Dy!O6sN0&x;=C|$qj7ECDj(Ysxy4<)kMWr5#EFLoI>aqz9*$MAHlBVEwv9s#`m'
    '`WT)Lb&@nI?&-saemR8QUfsF~uDG?!@MYh7MGx=3KC#Q9PS0!z#9G|jW%$zX6Z-)#%09HqqV<o_=UC-x+i|-L0U8g{=U7EB?)XT&'
    'eT+WGDp%u<+hsAB$LMpcA{cjkB#|3;Mi@!F8h6|-i_9s)?Xs9|FE2E^ET+H5YXQ)2zI`nKe;i&5SVGu-$!h`IU*CNBUoaSy`lm0i'
    '1z_RnwE(Zu3G3F(uB7f>3&7uaN)A6x3$G#H?^Jw$`C^iB;gy7Z=mU%dDv0^ev0OYul5mFb4_YbZ373|5lX;ZOSFxPNZP~;!7pIt2'
    '`<XaRUJ|)noFa}!sKfh-(xmu-gwHc`v3ylNQcCwy8B=IKSZmP0o=9c9%KStiX00AbWlX94L>S`j=7&-lUv_>X3$qa%T}%RH`&1Sp'
    'g66SQ&hDu!%)&J(E|v4?o|G0wBHWYWQaPXQNoipu!aXT2l{w^uOXYkL`|c{0a}oQ0bE%97lUu2bFp@(mM>D<9Tc(Owe)sXq&mfoQ'
    'see0M#d1ZajAA*TpsRBq-qiuwe=Dbr>?zCn{#KFKO6ez_GN^L3%tr%TEAe>)EEg>EZEPq$Z-C{3Wv<4C;`0VrE<not*igIxh2?@z'
    '$Bhle3s6ulT!1ocsNw}EEEjw_W^5>4fWmSC-pS@DUVy@K;W3_Zj#|6`h2?@zCyoup3s6`taLzbXEna}a@+;@C<<Q~<C@g=hLTD{s'
    'fWq>J4`V<D@d6Z<3!Ib2hO!@7Yr&7~SVP&5thL}r9-XsV%YI}if5JIN_9H{N;0?56L)nk4jo?RS>u6*@vNnPrnJtHr{m4)*$Q<@X'
    '*^jJ^7(CZT3Z9SB(TK5gD87b=9d9Q^hoSfy9rnDP6dcw@h@1!3P7Itw@ilNBc{`adLfo948b%D8L-Ca^nYWYaB1Fw6-cF{A5Hz1z'
    'I}yYL#aFs4yq!!J0mHPib|QpH8v(+!@pdv@1O(I0+lh3s5~6g}|FsnXOxj9_Qq3ERl(7<`)UbvkfC-8P(4^%JMcP;iQR;X@nK%-n'
    'l<h(*0+^s!AWq;7W#UMPQnnAR2w;L@fjEgb6d@LTt(|@1eAIYz__6a*V`A?o=CrnAHV@1D2@-I`@_xiz9ftRFhQk0qoXurzv%WQR'
    'HRg@J*PR{gp~q$}RC)5OCRE{$5pL$fuknfVQRAzvkIY={&JIjr5P}1fnYr4XJeXH|TRX{v$wzYbU<xA<JeY=$<mAD;8r<4R9!x%x'
    'vj<ZciQvJsd?fMeDywF$b|)mx)%mDhLE`+a&0J7r?X8&$KgPk#%|`#C{2B9yukTmFgy`M(&*zJ!t7~X`uynO6J8z+pkPqsA{<OYn'
    'zxf{nj1oIoCYS%G|8@HM>BFb#^`~uryDeW{e}41dH~gvz^{Za--ptUOS7UEp-}lx?2+A_+&5pfk*4zEqY#*E9y}7YBGxiql$7cK3'
    'Ebq;ay;;`V{n%U|o8!Huu{SsN7VpRA`q(`0Z615`thf8I`98M5dkc(kVeBs556<_&#Zz~Ta*=g+Kf2IImrmV<vAZ;Om+wax`shyE'
    'fl?au?%00F_oIt#bm6og!nm-3ZHVc9bg_*toHhhyhw0t19WmXHF7?r!b_AtG>D{p{G2f3a_0gTSL>T!lust!~k1qGoo%RG>5%1lx'
    'O|jgMF89%S%G`5^rgaI+DD8qzW0&_MocaiZyL7pZLMi~SA6>5Zqn!FEW4v}bvNXnfhc53&IrmX!b?uTZO^!pC+x;l#Hp&QA$+^pI'
    'WFEYTKXiFN%B77GpXWVyxvyiFpzI%A?)Rfy`Y27lcDapR+Awx`KgzX_(wS?Q``D$+N0+m@ALZId2?F`lC5GaME<s5ey1XCd)<+3q'
    '=G>(lB~Kj1?5yucx%E*NxYA!gd}?agp`yj)&RPYgW$s|ydY<*_#WTvPXUnROezY1P9jjw-^se_*U_QKhzOSysrTUne{#@N$rkc$C'
    'RFl0-HQ5JKb=RpnK2_$_tj`4V`h2c<CueBjue0@hwwl!s*Xf1_(~Z~ZMtfg9U8kEKtZcf@Ha%F`e4T5)U)iiKQ_bprs##yAn)Ut4'
    'W^<V;DE+*;W%Vy}&E~YSVXS|CKLCqP3p<bX-F3E(&(=(1eSe*<=hGeD*@Pd%b-sbm*KVx-b-sbm*Y0Eec%5(L^L1muAzwvQK8q-}'
    'yjK~Ov%NKx@_2$ScE8Be{mu4v1uO3B`!A!tWbnfHjlE>>PWaKOi%&b<TBq9HnN9E;>-6bJZ6B$zch-}^Na4|`e>zgzM{4bz5oIvC'
    'ICT1Sq^^(D**jax;BD!n)9`epu8-8)JCn-blgmS=Pe<zeNQ1q#tPI{=K6;H$hwA%KqrEk-;78W$)3Js=)?{z(EQ42xk6zQ$v4%d@'
    ')215DE%=f3`gE+#>N5JYt46EKXtu5L)3G+=%jna#8jUabk@fm?tf`Onw68`R%xJc;rl(^~eXOUAHJV~Zvz;|P9c%7mJ?*T~A~Tw8'
    't@-I#b04d}8WW>oX7E1h(DT#rPJO)LYEz8%nE?x6=y`cM=BbZ4UQLV9Of#4nc<A}*nCCv`e6=uEwt9K6FqZY{n48gNjJg;a%xE+C'
    '2=>tP(=j*O4H{nT4Q9I;Gx`#i?dh18K4yD0+D8-4V6xqz=ci*{`<UI;b{{P{gCXUk=l$uJ*FI){G2xj(XE543^!#+pTOV`0Sn|xS'
    'g9^hQT-DPtZ+*<=6;a8&Gxb5|K^HO@b{%ymHCE4ORm))1^sah+N_nhqmA$X7&x)nNfaQJlvtDVe&iB>LWvUn|ysd68Q^h#nZFP5@'
    's(Ub1f1Rp-Fjaq@sz0gFWA$*IYIrc!c%5o|Fx7OOYI-o$OI*TWMDV`)b*lM(RqGqCV|9Gr^|tys$v76>Pqn_T%Bq|Dsn(}aS#^6q'
    ')%va}ul``F?mAWXV5<H)RsUeB;X2juV5;#t)%akl@jBJ`V5(QK<Q|A6cNI$*-ZDS_@O3pqQM?xAa}h?lE=3%BRY9RpetiP*_-(xF'
    '1Va1>TpE1i^N31j7gUW9{`pyiP`!S=>UjC#-?e@(uMcA3g_K@X?6w3b^Bk6bl+-W(d3yU5JN>Ue{;<D!yM6xQpZ=d8`bYnve)Jzd'
    '{P0gdgiWQi?%C!L{qB=BtMgl!%(Aa;1ucKu!ahx)2&a&;-F;ZL#n0OstxMCAVF1^TKYxXu(VUsGb$Omu@^N#ZgzhN@A7KaXlivIs'
    't(~lmK`ZA>p20S8D(Q8HI(vkk-%js;`a1noMmnpQmp%E6S9!IX{S>B@L4&fvS(|hQrAW<dwkd@i(hT;qn$*0jv;{k_Y3vUO^26r6'
    '+u%IhHnrvjpT{tBR118>WcXBc(-vU%Chj1Q0!-X&aklfk&j#vv3><%)et!F5TK{o=^ByN07Bj80!|z#`PPW^$Z`-<By(H*f`E^sX'
    '%Ili<DSEfVuoCnJ-?eek%h2KWcE=en$s`lzuqRjxyQKgcr7?Sqt6hVOPHVG!HR-SdQ^l~&F=w}fx@u?89@7v1FD(Dp_sf?zur5FR'
    '(|`FdKfM0Geyh#v|NS@r>EHkJZ(hIt?Q2+(>CM|$fB2%~Jbiw%y#D;<)0_7{z5er??JvJtpja<|nm)b$@@abW<@2wWSFe8fk@S6('
    '1qN6VI}C;O+}CY?!#mgN_uI7opKso;AO7N&4<CPi_3jT}+~<$e`(MHT&Od+Ie)CS_Q_ax<iEUKbQ=kk#6Y%B5axJ-i=-2E^>UXe^'
    'f1GCEZtdQ@|FV7h^!4MH*Pq{h`10z{|M=$fr|BORjMkD<nD*84e)L~xtk+J+!^S#!Fl+ne&AaW>>vz+~k3h>;AV0LjOkpLV&+`ua'
    '|NZsN_NBBl=yWEO^YeBuSWD*+8%0XqH%!d`Vf*ywH_P_Bx6_yX!>4!UgEUSI))--!v5JKFhwbxcV8dVi_7AV6u0!qmkDsRZpFe*1'
    '^ySrW|6pHVzWC}@0@3znoxW_Ze)sD?znkgXcv<t`;@j@S$L)QYFZte;zz}hL^ZDc3>F1{({ST$yOD0VIRTKUVK7Py?@&7-XZ`}g^'
    'FTiB4p^w*}r*|LUZq!9Ec>68&asTx8=Z}ASJp(uX06a(;a+B{LIL=5`4`eTlBOHR^%l22;^-vE^OzZLac6;!`x1Y&s{WSfhe2V%('
    'hSDy4e@~e@S~gS-K#fN%qowp3-#enKmH-__@|7nFha4ULx97m5@S8X9x8Po{^)EmC=oBW4bt-*tSL}ji|2uSOFs-4^gE)E7<)An3'
    '-+XxkO#k0u!k|tg!zBO9x~$oGruAp&(&K{yNrhk1rC;BC`a+$dkHb&^>BXIy=?nIR7dHGa>L@Q?KYfNxSNj9X`CqgaVfpax-5cr*'
    'Q^Dk4G&s;zU}Zo5>Gj76j%(}_cG-{7{jxqsh}{oAmb+m^-G6zf`cH4x?RB9gjuX>{2K~KV9y_k2g@T?6k~Y7%Cpyu-zQcV1M>ptU'
    '?iW!nfQGWY2eLVb8T`yITMNH^nm*&u;18H?`j;`wa77T8m2d_r{i4l5J^pEX3r3R*4r91l|1wcEJ|hpEf=-Y3m2&(WuylQO4SJ=w'
    '=F2-TFYlD+Cxc$g(`+SI=r1HGUa!YBLJt~cj4B-p7AYKH^t^=mZn7VnsR$A5iJpzn@fYp&jtfS<#n)ThAj-LlW9+rJefs*gXzBqu'
    'RMLQpdKCZV)AVkezwZ0?>G#|6;nV6rPM<z+ubM&h>n9e`zy9!}aTdgR0lAD69$`VS4g?zZ$03a0e_ajB*Ql{$PcTWx&(u#}-=p2q'
    'r}pvd7n&9r2qxSaE=K*nH2cl;^M|ire)s7Ex*LA=n|J2bD^H5+t9S4@Orezyh4tO`?%fCUa9}L-*7g_-Gi%|@__VFVdVc-_6@S`Z'
    'gU0)>AK*NB^$z~fr|?#i8$PvsBnk54?Hn{r{mLn?-u?d9zx{)H?f*Tj%4al|vcYTYK93!7Thjf@n@{ilGJV>9KfV8H`<zhYzzMv<'
    'q2cvNH|oC+P0{e@?bDn6=VM%_@%)bdq0?_Zz;FNj@y+tj>$^9k^w*z^8d&c55lED9If||(5+wc~6Ij9fUKj9NIrJUwNl;A76AR*!'
    'hCbRqqKW*g52Lb2EbhrAXYTw9>5m^iet7%gr=P!n_uw@};Cgdd828Z^+(n2e@uOw@V72OEeftu<`t7g(^V|RQ$Jg)v_1&x2%iCZ5'
    '{?~u_=hv@Z&40*P^aE%c0lgo0d&B+n^6`!TLag<zB=|1B00lbBwZD4_@gBq|)Qxoa*{b|ar24xtwm{PVKqUR&3Q0}Gj9)1TW^);2'
    '22rwrSVB4TrLq}{_Gl;*$RJSA?TX$Ydn@kU_ScVe(!So`PCtFV$P&z!`(x5pl+o`%KSuKm&lBbDq(%OZ+q(~+e*TZs$GT5psMcZn'
    'D|dH-UH4ygHT~<1TMy^?z{zDBeO^z%eWxk?{<nX49p2H1wEf+me*TOri>r>ajd%monKTmdGrF_UA@&Uubf5@*CK(FG7Ur7CNo34J'
    'hF5K)dCG6TP{wY50t&nX31KZ}1`|Y2g8i|gSVvD02&?e^>$`dT^a{@v@(gDC%@lWVaDBwJG9FFutQiZmt#$Y_(W5hcSwP`Iv?(yK'
    '`X*PV-`;=u^fSt2M?g+%M2b~^(d&<I{<^(IFAs{|6!jDGQs+cow6xs+I2&Jo=gvQ`tV3_ocZo`m3>k$JuX!Kcf1W;lK}THwmig6('
    'SHGdT>VJ8&fB564H$VLZ+yo-`)vLx@c$g}5fg3I8Eidc)`zL2hUPg7NDd;q;$nT2yG9FZFP|ikv+28#2%hyj^(FF-d9S>hP>Cmsy'
    ')9~Rvy54>y5u^mw73%%)BPso2h02wbGD7<OBkGH_7u3`p)%veJ>hi-s{je`vN)tX^q0~O@ZkzXI-uGS6AFKCZ^=h_R!4GOHrLe(f'
    'Fnt{UuSbV{+86k{-5gX&i!HUbyt<wKz;Ag^_}^9Uc5;iwm(zAERlO97Q(hGOR%_e5N8sb7)WxTop?0=;g;QSRjnD~<_yD~_12pI9'
    'J9e8e#r|IVY2UMY!7uq0EPfr;J_pR3NB<iz5Vxr4)$G!~BZ39~8|c4N^jlugr@5(J!ywf02mX!!M3)YXZ=H8Nl^=YW0seQj-Yv^s'
    'X=b-Yr7htN^jeZPqRqN(Nu^Q>R5qQ;&_24-eoK4Q^ybr?w5}8myK8F}f;39dPBn~Bdq-4U>S%o#<7(TeoL0M0t1sU)W-VXZbzSi-'
    '!B?paS80n|GOEu4TI_Dw>gZ!@k@wny<_R;5V~fr97QVGe;b^f!i*4)wh8C;3wg~GmDrm9#N~04MS6$j}35ikuR@P4`nR0D?p*paP'
    '4~>qEf~DWIlz!`)&p@%ce^+nIlG;dh>T}WiT8okEU|kmr`;Ar^1Dw!@W*iXO*b!@1_tTnamqD|ACcc9S?6_wZ6V1A{8U~+wf?d31'
    'EP)a1M-O(@w)|_GwQ2KBcF$@nwfD5IrM7}ywnkbPpjOHn>Ma@{5rO~3=WEiUVYL+O9%Lk%UfMt~B-m`Bw5xSeEsbNTQMEL&(pEPQ'
    'r4uMb^s9y6U_x`PGXY&Qd{!5_=DBbY{dbzTMsbo)3ysgg|G)>WE4+epR<PLXinGRcenGqod<|p;NITW~AUa!UOS!aL+d#EpHEOka'
    'Grd0T^d+tHTnC7ph{1ZSH?~Nu1?<_yZ^=!iW+{dGuGP2g3s}=_$@*S%jSC`PaAzEU!!gE$f14ayhviSg$3IbPsw0C_cp53R_%dj>'
    '!uPZDBu!VFfv9`3AVYN>gWVUP9MoDSw*t@j)luoBYy`e>GjQF4;(MW!B?MS7kii-ZH=zBp__p~9Um<_3cEf?v>O)USIgrVo<kp6g'
    '-p=I<dXK^37*+?HdEUmJpjDjPWEIxKuYxuT6aD7zCipHMHGU5<>lx+;!qKfJZ+gpc;*^uF%odRedl?IHG>rhte4BauJ|a=R@B45n'
    '+GrNlW(_M4;6$Sppmp(hUbp`B<Nh=BZ&?4p87py5Cf3r_X2D|sPI#qv;{6r5!o<1E88`f<rkt=gvOMgId9B|o=L+qnEtY@5fxdtw'
    'T@Sv;Uy(;unm5mO0PNPK)Ph4Cw1DU%%AC2>Zc@&b|HEAwqY0{&r?DK4Vh2pJl)a--*1Fk&Sl*C2rt|j#Jhjic3<LS!nms@(_;x@Y'
    '=#cMtQrcxHdj@1B(c{nqN{xA0=2Byey#_m*a%wf!&};ay#yYhci*Gg5I@SOkr`DKV?<24py49F$sZls(%gU5>9OY0r_@$iPx%`GF'
    '3ASod1yoy<Jh&zqWn`hfQ&oOqNotbRP;U<ZmfGJeNhSQ7Zu<l|I>LJBHg;S|P5+15--3sP-zx>HUboH*GIJeskx$U?KDBW<lzFS~'
    'e+y;ocxG>{jxS?(IKDY6dr$zS<8)Aj>e%C##D6jL?P(kl{5!)hIUWDTvFP5%JkT3k&RrJ6F-vnrSsYyiTEP+*dM!o!)`bc>DcIV0'
    'OUs4O_c>CG^kG~%IOkDvmiDBHEV`XXq?hEj=b;bMb2g&RvbXipsHNG$d#oqWJBZI5YSGE#Sd~TjwVR@wHGa@(>}y%eS==m%!UY>N'
    'D{>~fDV}#j^vhIfvw`+oq^`z&U1tLS+LvP{F4UPc&9#kx!tom0NB?Nlcq+!zSk-x~GwOeK9INeP1qqRHtSJ4Pw(7RtBYxY%x|efH'
    '9~vzzBdeoLsRR1n*6Nsv)e&?^kW+OWlPlvW<=z+TVs0C%=ts?BAuZg@dguv;oJ)&C)1M|)dudb$eYdX0SyC;jv<E(_I`6&4MEv3F'
    'FRczcHL8x}&^{?ONjfExNk|=}BN*tQ|Cdt)wC$aw)dHLVlx*W}5*gcsjqIUe&Qr5I4k}qyYoMHgk>)hE2=+=Pv^yLBl=BOCYP}nQ'
    'Qb%p&m%O$W1{t}7@*Hq}vw@?b{zCJFW3|k4O@3RWcUzYP*snSE^xE}N_~Q#TmCwF^2mZA|7i~-y4yX1T$Y3ApcXg)-9?keSl2l+r'
    'GJgTkM6GS*gTXn_8I{Kxn<=XVed$sIb*Sj-SwCAm3zxFWMee6Vub*LAQ33|Cs!;Mn37t$9r3CDp>Ck?PF0ox?%QCeQ00X4DPwWDx'
    'k<&{669A0>(m-JE?3FqhrTfzL=gNT==m$y;72y|Q71vPy4J~F+Y<de&h*1+!aiRWk2a|_n3G>tl3`&!RV|fAMS~$&f=?O*YajqnX'
    '{te|(H{WBG156%)2&?mhEgOqGS`A6U#TqyQVxKRb2UA;Lpw$W#295n}C!-#U_5n%VwbyrgLv7zXi}XbuAC6v|wkf(TT%=^~>+Z{_'
    'kX|s$Z4I?Ieb$<+ZEfs)w858#3T2|*0;efh#o2PYqkVF$EA1|`s;R9SoHQU=vML^}viHnXN0Y|Upx>yBW_NoiylvSWchxjSeVm_t'
    'FT%`G=HQ<*eUZzlZ_(Db#hOByUF~-bdS>$`c#w4${{{If^tQ}>2F1QLY5Zn8*~@P@6|E|bV6}RAI?9`sd}tK4B$0YO)bW=(zNqR$'
    '9b9<F>LA`AvpVroCzd(Pr6dhDZdLJ*^5X|m^ILfyis>9~<zxMPlutMHr?LKYl+QwaN7{r^mdy@1EU^-t!CFc{_E$|O6&nm0B*omM'
    '8Cp83@d0YgZN7zr$gW#V(R(z?$I3AwMzV2H3wPVpEc-d{{ZH)L0a*EI9wt;ivCVjT0ynzSmVBXTXB}QHFvYNZoye<eXdc5Dz*Jko'
    '0zJ3{Y`--CuP>ythC|Z>IR{3(UaQnfO%pTayf9QlN4y+x;~%Xj3Fwb)KlmBMg7##i!vAmZ|2uh;ar_2p>D6JKgksO=xu1q~uDU~q'
    '2O8}X^=R*}K4XrQW-lL9q!r$XGP$jAj1y`7usIT*@TlwMo&4r_=;j5i@Poz~)^<+Ueht;O=<|jx-?XHolx%xl{Tc9;bp~yNzM_iH'
    'KZAa>rxi|nz0JNzto{`mpK9YnE^>4Cjbu2?R~Tm`{){7k+SI>DTAiV~)!s9v@*i=6Ax>D7UTA$+JgSXu?Yl=3+6FicH_`-(--7y5'
    'w$$9_iL9wMt0kRlZd>t>!dT5X*3DEeDvp(Scs=njdS#a8Ypt|uW3QH%8M(O3VLtr3sHddjXN-O(?pyHE5T3TS*mdYdg0ZC1W=>60'
    '*ziUS>*vreH#lpWPq+Wp+pW6%ChZitELUrryk1}-ks36EU@q|+;4nBMpkJ3LdV}*x5${V<BnCm}pv^?kY%ui(Sg7(Yz4y>7Rbx0r'
    'pX%2tzUhSCEl`#+MRArEUAmmFIDVjN#1kFVA2b+|7fQ{-&pztvSzK{mYjfYnxMkpE5CQlm(Po8n7M8U5shp=Xo9IhzK_l{W`4*Qq'
    '7;hTnC+#=V(m<!%$xa2@`3-eSlp3atWF=lU<ki_6>RuoP{ooUvt4}aI@j0ST(7M4VSbUc2e76dv*C(FFB=?H@h5WzaY3t}t{$JW_'
    'aON$|Bd5nm3Z6mPlm3rd_zvX3vb1ROPd2R@{hbM|!nOE06P_`!9}`KPrO6cdrOF%-?Py!M=;B;>|4IA^S7K3hC4PzTx2@zJM*jE?'
    'PcQc*H+v#0^hm7aSGFqC>^GeKv^FURvo8LA*v~oAza2`TZNYjyDy8Rq$dXiLXW3uy?^;XHZ}r}-INX0+pT#}ZD0kXhJ$_j{P@n*~'
    'rYWhe-aS~IPQUMpKcvEcGsqVga42AM>~u@Jo;W&Gox;MFzGxFw0<rxA@-ovpM$i=De?ex<#B)YB?|Y&#s9LK;z$oFGB7Z$dI)6wR'
    '8mEtOo@?)0ZMT-*YOm(h>%#uE*Aet@*dc0}wlg>D?~kOwx?{}(JxD%Oo#WE;cgIK`MMwF*My|(i8{5>gLxNzrj#u9}^HD|AYBsPE'
    'W7?N?u5RQbIAlFaslDn9x6!@`HeeY0Fzl?sK33KHxJCeLAJ*}4khF6`JICAU%lL_+hO7#A9lJe^y~RI@-@^4MK&65%GYI>&Cx4p3'
    'YKNXY#eGO8_4?Y@o!ZX+G>WQ&+8XIT^kZ7}B=mTiS6W(+z&#$$5fn3ZOc|Z?8Z%KB--oL4uN)S1&rkT}Jyd-w(;me$$}?TE{>~_J'
    '8iSka7`mT*h>0|=hO_S46N}@Z@7wpD##N?sbduViMxwkl5>tQ%eI#)?bWEU&g|m{y#p9{hb*g^+Qr{unrXhOe;j6`uNBoSky8l+<'
    'l;~+}-^Y`_$M)lOPO;I1;sHbn=zmK&9;4V+)CIl1ZwEVm@AZkxK-++G5B}2TPJSJ|6z^0U5!e*VWkhE=V0zCqzvf}7kypPgr4O)R'
    'j;}lXI`F{4#zdt(I(_MH0WCbOTb^ubC;9ilOlth9icE#m7wsmJeT2<eE$sFpp(*(R)hd6mC9UDEstyh<3nI*r1fLR|GF3tpZ?{`p'
    'L}@YAmr4i%Z!?v2>(!#yamL55>Uq|z!r}$6rr=YeqPY3GN74roI|759;k$u<cNgpfJdOM;W5CG%Y1p<oZYs5Tk#>qUWZOW+r?yu#'
    'Kt?=74CJGrbIxsQDtI)o?K6!LAK1$E>_^*P_umu#Zw#O#lya;c$~jH3jTNl-vR^jZFJYScEb-fpc&Pg@4y~>HNvc>Dg-ZyMGel#H'
    'vW@)dhA8RLGLe*4dqo0-;D$(UYMep!@^C&PCZi!~n#_&|wx+h+#FlfbhodftCu+YR?Qztgtj>=|ZF`?8UuHblZ*Swb_j-68H0-o1'
    '^LLv&%6GIVD_u4<tjX?)SJsB4!QExhIzqee89t4;0X0q1z*ep&nW`rR;*MDNQX*>=y%2Gf-aFxWKtfbB$x355zTm$53ubNoGYVn!'
    '#rUax;d`xqCZCScrSBb`$oaIJ=XB)}kXn{}MBO_;^uOIdicTfcY*oYAZIXYV<N=`?7_S^&-F1_+7wems=kX4XZt`spEfn=>d+6Zz'
    'DIZ^M-g@NTJe;(+4`OZqEqf@$<J75p$Vq$1+pdk5S(k4I(393v`^efCoibQ^`3{_SBfpgvx_?nmrNx%5KCIH_Z;_~3)?DJpimkl;'
    '{f1Ulzpg#W=uma0ExWw0ZA{gFPG11-MO$50pSH8WPN-ecS3pzQ8_#loY(Y84IXmSHa?duSmD%PCx=tp)7Xo(8woD-Gqk|vOGld6d'
    'Ud^`EbF_RrW8CcSMEtfg=HCJf-i-1g&v{uF_NUwROP|+L&^BZ#mv~9<zy7<|edIr^=QmJy)9oxrl&LECZHHcT@{o`R6D?1RSev9='
    'J?#r(mC&q9i7@M~SLYZJI}<<-$!moxS|ZsLr(6gzNZ#+Ijjx>gs4<Q!m=C<}gY`?}`fYphK`)Wwp5&hZmFXVcUe>3_523&9&I428'
    'EfhVTG4>8$naR>#5B<uUK~DpkE>v$t$!B#tZ!;ki^cck?ob7QQW7G)Nf@lqft!nGFVDw)Xnc(-vOBT6g4-`4d>$(J(kfvyL-hIJ+'
    'sdB@hXs58LeBl1qIi2-i_`Y6iJh({ixy#SF>o{He)i4IsT$YYPq8=6lmfc$FHS3_q?{eL5iK6R?EKD4OsT6T;8z}25<uD3iH-n;L'
    'C7%yQabbRI;c@hhlP54aPdHYel^7$+CAJhm?#wK}S#9gNL@Y`FByHE$^J3~~im}&Rb-rdFW^>d+ygXu=+V{!M##$~`Dg9XgIecv<'
    '$&tI0JglQP9ECTRI1E}9<V{-3f>J!M-Z@#y4HdL{=1B2!!Y)?Snju6HoIDL(MHHM%Jj`*tUWrVgN0sb3r>cFnA?);uuW0RYl!<!I'
    'Fo+qc*Y^mD^h#qKYg%{&IQnEcZ~6nR<P=&=bHul0VK0UjuS4EOPz~|=JZToXCXERFf^EILjqOy;>oq22rnV!_`kRkr8<D1YiJyRM'
    '@rlPx4BMZG-Y^B4kNn=SLckCH+xUU*ZIC5aB9y*M@_e8h3kGRRlONHTgfVMtT5*{mko5*%o3|srH!sJ0Q{6-JK9=Dhna?XC8|_-q'
    'nG;F^L@j2*ot0n9DCWcZH0W<HR&`xvQ&8Q+@3zDh6KS;Z!0tL#qP@tGzQuom`{*PrHko&oQ(>;Nrd7je+nzMql+lLr>#^?i<<Ky`'
    'hyW%Tv>aGavmR0Yf)g$g*y8h3YuD{C5#e;;M#`EPSd(?uT@v<vIoF=@F_uPaT)Vz*sjV9vPN{Md%zxEK1U1ghLp|KTK`dHa+l?Mu'
    'I6Jx750O`t-zXsoe`+zf+HW^upU7?264FqY*hLwW?c;aFBb14Xy5Lpyg#QbQfI*%h2M<{P^xxc~^|%@=z5#Qi2=s`5E9f9RLrX-u'
    'THU_KjvLn6&Bv^rrSmo(^yK5m-$Bw?qY6rHu;;yrV?X0JK_5STQ#bl!#BIeMLCkB?^z5;m6jArcCm~l03$)Widv;aADeo%6Oo;!2'
    '{5g1pw0RLN1?|@&ZxlvTTMzqWaHrAVi|*mt{i1dPCh8Syf^8M+en*>Yuc%$rJ`gREc<mXq$8z4IFB|V65W2CPpQR<O?h0GL*>N8x'
    '(|fM>Gf6V6s57U1*hBpW34+{e8Qq_$x(#_H;(YXmw?11Oa#8L64jeS$;Y}K}Tynn&)1x$Qf~D<uR;o2b-}Jgr`_41K`J2A~C`wem'
    'Ke6wFv`K{B={^@i;#+n6I~Rmo*E}cMljYy=EAjl`#hHA$jZ>*V(&;gN0mtv3kN-+PGqIJL!s*Mmc#13i!t?dZXZkHAMi{H#H8vWq'
    'M<2NNY|$a9ML>V@)jwRYahu|Q=*~teeq&s#77IfQ@uHLGd1zivS<;tK>m{vwN2@}Q9$)Jg!e4?MTuia!yDw%_^(Gy9oCDcSxc3a~'
    '{CdL<WGKeT?K1Z}cStdcj1y{y;!lLqabO=b8q9V>IZfw<pVs5PUUCOF7VZj-yFBR>^_)I#jT|_%Lcb1-8`f~2Vg#Kj(e7Q!?v?NZ'
    '@p1eXtp-1?|2&x?f;blpXWKc1e^Z0!cV?qax!(TNhfRcfOPNJ$cZ{T#FLJrQsjpA<OR2f39WK4MJ85{op~PdFm4->88|~;z4W$kL'
    'Mw!vAS=VdKeWhyLy~W{M#61_pXSIUq*A{s%)&k;>)Vfeic<GjLOiLMyJ8s1-{r1B)SSTp_*Sa~%UYxpKmJSVV17nWQ*3b0|T~nf%'
    '_dHlO*;F)R_QVzV1z6*CuGmDnk2t&Po&u}IDN8pfKr1-L-*uB!RgBLHhqIcG_`ynNWE+1X?O-Z>>r>y+hk5LCL9U$$5uPzR5xt+s'
    'czE+3A)Ru;@Ah+`>S7D|d8#ZLe|JmO+S*;N;}>pe0xt!(l?dH3*r6v~lxcvuVlv%s`yISPS5EL}z?!x-OS;~gtU9sf{J~~8XLHP*'
    '?t^v&Gv5&l-Dj+3;DBcq_tRPLZsm)TcI9&Y7EuiOahnUqxy?=6b|bWE`Q5TM>i)F7&yUa$XwWh0Ph`t(x@c+#2X*XOY<qgz_^zMU'
    'VULR#8>+RmTC8**<wM!|CBE*=x-`qJ-kmEp4#|N7Uy@QE@o|%`t$n2?@i3e{g&=2{(QdmpxxAQzgAt9wSHUaQ?gou~T>2p0qpb>j'
    ')shbyPEJf)uZoT3O}!gMzOLevgVWa#jfYtjpUYBC=`s(xsW~Tp=Fl#5HGjadvxoiL?s?X>P2#s%+J1+%{2sfe*JuDVTgN$%`?Oh='
    'brf~(o@fQ5>6tIGr;&v!!w4U!kYPxQ70#yUYL}3C?yb3m425^$8@~JvIu7y)(`&lZzvG$XY~?h<xo`c;hYt&Dkq@FsqT-8&)h)hn'
    'j1=popnpNe?#B3*OQzkjC0~)QJ)=BE%ZG4ECLG_R{hSK6mMp?le_IMyYx0D+fUggLT@~tj<K1D~d!d=m^Ps8NO%*+QQ3dr~b`zmM'
    'LC5pOBEYz<D)$K~X90Yz-h3uRo#uFBQ}M=xaYY_>xH@zXws=!u{rxyEtGeeK<w4C@(npE=0LC1h@0@uj)3U05AdF57nFcJak%pFK'
    '+~h<R<sYq`X=}&u)5sBFoKHo|IecQUb0ne>7eZHn#oG5p!KtT$D@DDzdAdn5xUy?P<%vKVKE)F9aQ@L=EvHUMQ`>oz!@~8v7NL~6'
    'me-=*_I6z=rJD7k?6*~jzc$|X6zxXu*+9wa*Pvc|9u?w|nm^{AeyF#_fqp=xSS(2738h;6tI1$JucJ=Al73ci`Q~Pic8TYzjj$a5'
    '9;MdpDgJjow>LOJci;4z(|G68c$t)Kvfa{5%09%ul~wF#zgOLA`L{lU`FXo4)oumS`suP0w=HE`y*zcy^IU7Xv&LtOE?0Mhx!vWD'
    ';vZFeu~mBs(d$9)?OF@v=ZZ_Yu}2uaHvYPg=;S{l4JGQ73g+?fui?l`o|}4qYbmp*ybp8VXLH$)b(b&YHZoyyeEBL$q``tD&3a3_'
    'UR(5}?g_4&)@%gku!Oe+Yhp*e1o)%Pi)BX;wY;q(guY+P>$V-|n>*XC^V}obZY9L)iPLh!HysvS95nmHwYVZFifwmjP%Ynr^PE~?'
    '?R~dg4u>^TwKiL|Hk(N&XxWllgc47yy=ZM$y=obvp1VG2WqmKq%ONM)%3h^I$$C*^wqQxw{jdXgMvOyV>}%_FEp#c;bmF#LyMEwm'
    '-j3#28tpcdik+I&T=H`?C)Z9$-!jVP*Kv#P@odCNb|3g$Gbxpwp^|M8k4|;+3Yk9Z89gWKF}@kc*Bo6f*8$}k88D>8Z*2~wC6(y&'
    'w6JU?9r+s$d?3l}(SMix6>03vG2acy=rZ1{4r|d@o$YhCg)h}iIGs4q1j|ul)kS-Z8uiC^(}D1ew10M0e<jQ#?3THdR)l1c(e1SM'
    'gcNWMz1F<1LoSzPw4>^&)@M3XZmhwFwXolFJ?{?6a7qoCWK{1z9{%C=ltrfH+~U6{{(DyZ_c4PEjxP;9wfcMCFH`v*{TuQ9TSpp1'
    '&@B&+8{{MW1S%We_jFw*X1dh^va;w$$jVKs?06RnCHJi9KF4B**n-~4QBY%NF0RMOwvrJJZ@sTuM><ERSEWYeK4oJ;&vQ6r+=dR+'
    'c1o1&D}=_6Zr)^k7Fq~+zqdtjP}i3u!*}sl7AL6skiF5L>_vZi6gMD^(;xo&E&FMAjUuzx&6`Ft9qY-q)*862Rjf*dm>tXrv2S_P'
    'B`-l)=_0pDO6hW+VL_C*Cf_DTI;UE@>IB6@xW*B+t_NPM`JFENYdS?&=FX3s+Dy|Z4)0gb6Xlm~uiNU;s(BTrwwq_X9@R%sq<P^@'
    ';1NCa-m*(o8SIzZ(|}I!HEV-_e=q)rc8hJ^ZI3QGkv~pxB%u7>Fos}pm$9sro2qL?bGz%157a<Mbig;mN_WKf3wi@&z!{YRdvPVq'
    '2pansAto>BPFS6dG6oFy=etDj`W^C(v)j0mnCCBAvv56Q515~Gi>Ed08Ig*fCLmPGZZ*?dya$L;Dw+&tf5X^q(QfbzFe`lt@Ac&R'
    'rM`+<^=NX_FCyMzM-6;3!nkTX*j)`(I#&)YmgOMb3}u2N+`?*BpQh${SdI7d)V&K$TMh{DK>9#!RJ}^=f}80lf<p|}mgk0j(iQiQ'
    'w{TGZ!ECFC^@sU#bpLL%j52v07Q*7~tq0U`7Nqywycw`Ey2@3J_Y!u87VXw<?qH^!G_^dbJ(ubdSsT=Ow%UetIH;Rj-MROVW5E1J'
    'It_KhSQnUjYW$D)Y?K{GGOv9kuC;&<552=!Hq4(@%2;Ms7}W;UueG~Xb;vARkvl~%=~xo<D5$Aq-|RVViK?+tyJ#G~#YA#Hr;4?g'
    '5N_GOd!ml1<1ckR&L|Ic8FkcBe{m&`RCLFQh*@qrb$TAD{W$+fbDmY<V7xzgN24`wL)I^4+T2ac3y_vnYBXyWX0hM(Hk)Gvb>~i6'
    '9S8!uW<9rjINM5+7;zIIo{Q|(Teha&RFd=4bY!U|lqaGKe8Cz`1>>NG`y$25w#P#k!u-4-^~m$I)!5sROR3%*g>!SFnC_te`lt_F'
    '@0yNmDJUzqenXnt%>xG05wIvxGE`TyuWHpZ>l`Q5d}Kc?T2$yLGuNeSs2=BOEp9X7&CsJe{XPziWOb<_&oCMt4=Q-Xk${aiA9N}8'
    '7`}CBwn#-`3|U;kW}-X-m?Nv?b6u9=r7w5`-R7SOzt_EHbStN8IL}ZJ-<*}8*(?=*VCg=k+Or`{CX7m#QH60-TammidjR@IZOc8-'
    '@GIY#zaX;jH{?SuXDp3I(VbAtES}3f=5ne$!+$)@e~>Tv4`8`4r&$Qa{#F>}M++)0YMLtsby53d@up2!YitE(A6oX^{rEo4{~I#l'
    '^7*Shpzjy&Az&_-hGLA~7PN#V&B+tWFl;lSXeq10(z8zE#40}l-&)hOP4pXsj4+g4*LH-dnd&_l#=n#ifkunI5M1k<3_cA{PuxHp'
    'd7x5}9$VHm6Y6*6Kgl(Vz1_BojiUP|&4Uwz3iY;7&4)zM8$%hyOBR%^XhO!m#Q!%&g_fS(-Xhu$BS?tsaNAmPD%|Zq7Zu$?1li%4'
    '=QI@0X|=**i5~TT#qs9hQnDVDj7%QG+?4euQpp6TL?}}AoWG*pPf2|qF!E(9YhLq~(p8I+?Z&tJ_yfX}ZgkO|MpttHC49a(!8zi*'
    '!wl=N?e`L6LbxOxDeybFlCvwf|7$*gTCaG<4s8K5Or+!Vn71(lWko*XP2%P7O+~%-+w?m|uJBHHSt}6bj2{~Q8GX#xJo9VAAA((3'
    '&)35{2-~^f{%Hi1Wed)zmKzZ^z&btQptAlH3`1^N=$7q~J$CRP6Q5Z0v4Fg=HO|<)HD>g7dfTFm^<ON;SP|n6IKtrmfm6*l-J$pm'
    'a36PF0&I`_-Aw%7v$#?Q6Q@hA_*8CA*7#QEu6FBWA$ytfC3;jz<6Lga&8eN;M%}IWVe1ChavAr0o}i12>mFk&Il&h*#{m3+cR@nK'
    'YDT>HO>{LS|A#fxBf6Tz{xzTITE0m)<U4-*@T7MQ4R;`BO<cNF3f~X4Pk$ddfnV9Wn)A9=o8P347sYumq_I?ex1jYwMj`5?t+^{$'
    '?xJ@U&-JD&=J~iG=eF2m5UW|VExQJ|wD2VQjuy;OgIdt451ZQ&K5L*3C|m>HxMbdH_AkX=LB}hyLLZ3u1B(ZTJ$b@o^R<*Vo+6|D'
    'J%Hv{*$ln~g)yE!$C**7qo8AyZh3~K=cv#Jz4m@CC%pS~w&#1U44m~${Mv8M;oTu~Ah8Agz2p=&%UbmIVSj?&Zsy^}q*BA3fi(^i'
    'Iq7n5Yi%bsIvV5J^1~~A#FJ)sjF0X)p*_~%T!@w`860wt9q2i=znAxENL$4lbn880_&$GG(ZDQa0NM}zClh@a(tC2f)xXA2??7Ti'
    '*Bo>2*%k93$&lah*BG0HNqM*`nv*n;tPbtH<cW)cB1A@+iuc!;7kbOhvwQJRIXufs&I})h+-|yLvRVl65Gx|l&R`LP{<vkQh8!KK'
    'Sje`uf4VBB<_e*;(0%Ux<sV!9R8UrJ$08&3LfTq=LE<HACg1<I%VqrvZn>a)8(O2FsB_H;XX?%^`Jh9!e1U2@7cB6m%ezJe4Pi2&'
    'g)yrFY7JqZ4<4*5i?=z~@5G-K=|y>R&ogMFCQe*?2DOb&WLrmXN#5sbO{3Me;$GV*OW;a(kubvv?%j5O<&<9z*MF(&zf?VFDN>rW'
    'qq*e<;d>ai-BNYu@W{gZru+qqMNpSK|1$!9tM~U8e%|!61-%PZYGifDxavJ46dC7kkVYt)vz;8?35CNQL1KPFn>eK~!Fd4xi?6V3'
    'c$Kkm{;-$9a;WDA)Ky`Ey#<Dpw_bbWy$|H!Kur&`@xqt9r5BlsrWdLPSaQ+it@u6YB`v+_=Htku9qv{CY5LF%|3AV1qc)rTjtQsz'
    '<TGeY^$r}J<Dxxt*bg-iT=#iE_tR8kywcrQl-+m+dwR+PZ@!+;{CUg?n;Q~;B0eTW@S4v^d{n1s7ZxObJNGRrGE|aU)(E^~O!C+2'
    'hPoldJ!*2GY>4?=;26H&f5QCz-*Eove~9_tpMOc&HRN{7H#$dJf%3X$_H{K9hnA92E6T+gm|3@9i!8Oy4fnv+y6U;zlE9qYQ~Ou*'
    't#%KX8nYd@F=#*D>gD+`hwOk=ekm5ACS+u>$Fpj5++)OBz2gm$b|<-L`>4C8*mU=D*OlE$PUA}tHLuc);(+!nQE}PZE%1oX{$NSJ'
    '7Y=85$cvwn0$ww;szk@&=i~kdW{Fn)#TtBtspLC0<4ZQ^J5au@YAz!y@5)u%xI}ohnoxMyakjQxThm9L#X@5RG@ft)SncxO#I{VB'
    'q+j@DCCN|sSZho#2h-n;!guTX@232o*zYsww0p%yZ3O0zc#U=1^H|ntJ;^-G?Bw$59?@f;(BrK73gG${8C|`oh(xOT%(U$o2Wa|y'
    'eU&HISJ(F0ZjF17_xg6#OEH=db9?Whe-G%>YT#{AHP_b<Fd5y^(z|QR#f&Z0+*+D2wggkRw(Rc#rpb>jw=mZn`6`bsZRp=jojQrN'
    '%&q0NjPo?6x13wcFpn)K*IF+7*i!e=9+3>UjV+hhTFz!{xi1CvFt?-*7?06oOFy-ixz7Lk{$CEIhIXY!JOA4IiSSi0)Tj<{QPY!-'
    '{dLaxznI)cJGa_${ujIh2O3AePeAW2mN%(9Y(Bh|j~W3S`S{vB>IC>JW)wCndZcjHAW@>l7dFrupd7$E<~&-lCUC-3dIz~ena=Ps'
    'SM&-ap=;4r%8pb1*zfrMO7nI;eBY9?80!^-f^7zv3oC-Pfilj_b6wAfS=+J14kZrxV;qB><r%|y3j5L1t9{DvdhUpMwQf`S*I{em'
    '8-(~iNv~B<KpEAdqYN||U;c&jZSwJQ{~urd%cY*TZDm4R87#}75Vmnrwt%ueD9__=$a4f5Jgkoa>xxcLS|2x+^|7Y(9_!kc^|3R^'
    'h_!0mg*L?l-tR_7yys6RsLO4IjiUEpI(=XyL;qUiuX7lGg%zs5DubEqV3(MKzmGf%<&6~u7VUi8YftrFd)@80zG|9>+>D`O_owNo'
    'u}^c;;_?2%kwYqD{5RNR&SX2+-)Se;^`iGxY+p&xC@8enda0QXN)AiR4N*>v7{lahevIJDTd*}Nd(D#Vr@K`RHGcx|g6;EP@tvFg'
    'udGUBvUvRFni;|tzm>tXrM)Ji28MR4&&R(=ULF6!duYD!G`_3TenU<NU4Hf}uGpMgW_B@u#$DbFhdRdI*3;MbZ^Pw<QQxGa_hoH('
    '{&C8WficzMYtDo|SP7?v|6R8fbIA*Ooct?$YY1mHSGx9G^q7*U`=Q3SH}K?M=@|i~N)CmMav)L$`L$u3I5yVK#!uVaZh_d2tb<?R'
    'RLaLMaqgJ7?HG0OpHz&Ng*DpyXfd*o8*Wprs?MXuJC-F{<B8JKe8hMnaK?oDX}7Hu4;w@n(94m<&r4KN40qqLx&FZB);9{)j?`|k'
    ';&kN1IC8)o@2>P!MlC#6K0xb3HLIm%%xpJJN?nk@ef23HPS)6CyG`10EspNzt-h_IcJ;nQ8{K}*P%|KeYNqT$Ez|ErYFagrdZCP>'
    'Wb%}<*TBB_V2U(L;Bls!RPS*6>4=fTszux9sxe?%a%|N+3YyVx@R$_27!Lepi<p1}(WY@5$SkjG|CqfY`beh(T5EBlS3{cjY(OWB'
    '?*dId*DKxvx}MXAR^;kCkJ%OO4mCe5Kkwx4j3dGKU&}XfA8I!b=-Ex-PF}W|WwdkOk#7gzf35FxS)evO`5UV$GVCZ+cT#<Ix9^8i'
    'tE`4ibH9IaydMeYfh*P%-8pJ;J*;2n;WTDWSM@c$s7{in#6EP*+R}RVs=WAI?)a1!7Kk6uI}ddZI4o`BN6gxq@OE@o%b<M>>qpk|'
    'HdlWGjC_Zg8#;$$E4`B&#cm#PjKLgVY4OF1rgn;ax^1T0oPfK)NU0c~j)JN$ay9K1Xqama_EK8jO6FyHf2-EuFa5>6)i6`<gPl8Y'
    'P}dqdmm1geZPZWb{zAWn3i@nDNu8#OsnZduaT-NX?HgNcZzY}dznS#&o<nwszQoP*{Y@v+R9}y%yFJ*_7VZ0*_pHvc`55RmSyop3'
    '0ED!yU%2y6;fpjVFGz0f<7jmA6L`!GLEkmPcUjrk+kib6dOQ0L@TI4-hX7F@ZLlSiQ~4dg0>6Q(s13gKhIxRl-iV4;j`Zeua^+s='
    'fvC#HFJV69^g8b~5fkDmP(vqe*?@jDWC-xgR|1mE6@(~a&Et{}-f@Mi?B3h?+73>~?!c=r@EB7(G2SCWp!L2&Ipzg+`-Jbe6$Ej8'
    '{ct(ISLb!EUJy89V&g+~L4BIk>ftkwSAGR9OY|Nw`uo0rrL??Kt@pB0vcD&XM{79vmVDCHlGs|V06fi?8Ze;@O6j05ohU0ivgrlH'
    'xoZy9;<mZ!ZORnN6#LvBuMWa~rTi7gO1O1tHgD0T=iM+lw$+@AV2j1}avzscZf)OP!iW+d^Our;fW2i2%vM`Xb898-@KpSxrDfIM'
    '>npD2EOSHev!UT@{_(ZskfO63tp!u=U^WW07n{qyi;cALZJ7#n58qKNRK@kdlw9Rk(u(F$=bnxiu+i3ZQ}Zl!ttcIoAgPJ(G!(50'
    'Iy$nTrscrcfE-PG>FJW6cB5SU=!%~<%58!v<B>yfq|4k#N*Qb6pY?{owowF+{);(LL2mcFt7ye-8%1yix*WO@oLQ>9Dv5RROLLs+'
    '83|T2BBk1w>z|_gob{b~?tRWnh7~=c<amk}rx<#!Qdu*6f48h{#jD-gcZTS%>N*ZD|FU<#>$Nr12jkxK^piygU(e;%N#&UJY`@X?'
    '+Kmu6b76^y7A50V)05Aw@J4f6Z?XW*)ZaI*V_HkE<g0D;)mv^6^Q_1%Sz^3?4W$OH``%U~6%2=KSr(5~-pbt#-7*<(6XwSy-Z9w6'
    'w6-rEyg2et!KR^rM*JBf$w~>Vn=UO0bc^Uqr`G!S6@Ba2d))d6Q_aH)WT99js#O`ZPgI&KvTZ#)vGx6vJBwhoeI3zKTc-A!Xy1Qp'
    '+hZM5M|U1+mu;@pFO(oONX_?&W2XDA4=7S*ug$RzK<=hF7HS2$C0|~Jljn`s^C{|$?<^nh&)v<}&*OY!9Y211+op!LSSu25EqH2r'
    'f3Tp6xV@$iZVdA@yt;U{;hZ|?dY@Z1SA=hk1J7V)QZxbMgQ(Y+v;0Qt;qGX8pjUhe(nP_(Q}8K+43*_0=CF|DqiwVN2Kh+YqT5c{'
    'dR`XHQw!WWPv^YauEpuVhMCgT-=U@$-%ZYL!kVKGc)!c>edO`}J}l4olyd*pQm_HE_IoUG_~l#jfLqD~Zd?7-5NnkAdo|_dG`9MA'
    'SpBW7{=@v_wEhA3mvO+D|NGhcFT?t$XX{__@}{gmy%DsQsOmfwuGW}y>=9S*BUj_y-RJW&`K9~~=l?v+?<s%R`JMQC*=T-OjwRj>'
    'RY7a~{w=)wZ8_-k|DXJ~emnp97xNz+AJg~n-<n4G)A$du;En&bIi-jEcao~=!3!$CT)rkgzZc5aWybk!8P2-7+8|6%M1e_t!jW2h'
    'pkT)^D`i!wXwNCyQlsmS<D1`g>KLVoaq4&ly$}w>4<(jL+)<(?)cjUkOVHb5vO3!+F}9IX`stl8wHf29OWb<=J-W?~mMmFmVB;@!'
    '1l6_(?O$Yt+ofbeZugAveRfrS0J^s$TR-SUAK#i*dZpD-04Sd9{eng}m`@$cyM@1$_byZMAH*hR8h$#@b8NHQ)cq}=nulpANYy2O'
    'N4_P@4_!R+CCd_8VhwbN_zTl!i)zp@+w!gy`l~xlR$#2|-zXT8U`zSvFM(ZV3Koqb0(LWd@rU%eQ)I)@``r|ojcd1(R*WvRw}dEj'
    'qiMg<dnLw{_a1a4lzE9OjF`&k3A?Ws-(GQ|`p}P}_q`+KXTU2ZdN{w&{u5X4>}~h}X}=-7V5|@~VN#Ug;&{n&rLlWWIq)fSM#J*L'
    'ZzN3-Kiyx2Pr!3T-|TqKjg@5gidpxeuNrRzs$=P53|e;^-q=F^v-6k>BKo|x@3j06n%?gocL-=$+MK+I6YT+t=P_Rsa8yN%gmshN'
    'w>kB5|H{;J{i(nHY|?D&4I6w-*J#8@&!+KtqQ^P<>r1YV!<@%aUY+cH0S`f$$6Ru0Ic}xYzUp1HgHD9Y?{NarH#V6*kE?GC-`&D?'
    'lK-r;0MwCvWEDe8f4<FEMmXB_81LZ)yZ0TR$0GThM?dej4ms&he%|_;IL0kNC`=9Ep%>Ri((Il)4B?G`LZg48#!PX(y1nN}(bVbq'
    '#oF-~yB@!Q*cpFO$1gsQzZlzn#^}jk+WmY5|H^BviFmK(J;(DX(0|#BsQr#l%{h?va)!8mhl}zxl-knkjkO(|Q>|Uim6*zk4R2He'
    'w~Vdu0c6a6uphDL{(cIgE@$y|(E2?P9J<L_x?u_Asl34UMcT)9cRgB!ZdNpa+Dgyji=s=*;tV?8G*ut!?w1}3!#Ls8aSj_wvy8J@'
    'Xil4L@1`5ngw{EZClu^=V@xS$9{msvWnV;S^t8wNA|PTs@g}9Y+Rs<4L#j8^VOz{iHV*!}lh@g;tv={41udXAO7hb1@u7a8=|!sC'
    'vGF|<j$P<}g)xhIKuNqAzIxv%=~bm<&Ga*#HEGNVg=mbD4PG5to{qdkH<{I2cEG#xbS^L1q9WaRE*xDkxAZP<^*pju2#%-9M`k)Q'
    'K8#tDhU_;>^-!&8%)eE!5m<i8T}3n)>aAlIWc<Bm>0<vLvpFrqqxIdB)Ur2GucsVO=bTOIE+<n*WegdoQdti*ydpsPz=ynMvpX_>'
    'qjkFQ?AyalzLHIsPF#$m*B2(8>NSpxO^)O{<!Nbtw259GCXE&E744mK#!O3u-msJt4NjVtiKypU+KMDSUiQ1q`BZdsnVZU8k)9E#'
    '`~m5l_!`%I^_VGe%s?UWcYh_jF4hJ|!QAfn^@wiaQpMsl^OSo0XFF#f9Cqt@1p8?O`(*@}?Bse59GWfJw3NjbJ@|v>ysmi*O`>me'
    'gz1TIUU&K5zN0YPLA8~vEn4`r?EQ4uCXlMJXzr6e%9klx${I=9xM}aHlTNPcElH5O^9}xl*?(Y3R(hJf)05t8E9fP!=pGTi-=HYh'
    'f6bc-CTIlum{L~XLfMKBMAM6VIjT@wlpafqrM5WM16!opBC;0rn`ylz;kVW<Uw)fy^~jX>|6u%cty5Y|<zI;J);-&A$#`5(!#HVH'
    'Uh#&Ay&ua%tv~Ol@>+kMd3kL0PyNSMf9O9AwomzWT28+v_Ny<y_SdU*p>@(0lYy1IDiuu?gIcJ(elOQ^H%2-e*eMLmSy4)Q*$Scq'
    'Jre8G+Ej#)#Z=y{tei27+rY4@{p_h{h{97|ms9)5s*Lzw(=()F%y_C2H_p8rTh@)nGVV+!94+^HSq9GN&D5`Ow0WLl^~J1fX^C2V'
    '4tP?`Q}bGFvqE=(&GijOq;I2HkIs0|GH3>5>w#2e(Jf222^OPcAlj&L6!VrU@+C}LMH0-R<pw}Aj4GGBf2QR9qiiyGcIR?-1O4iu'
    '3BrAywl?#qO=ztV)4S$6&l4rIZ<O$<)L=I4LfUOA_<%J|b)AhlYhlT>xhVJlwfChxmfS{y|3#l`g(Q<qlKai;>Ddvi@fel{3(R0p'
    '$b%`B-PKiFRV}#}*#Eu}!Qhch=DWJB87<U?RWCEiU<8j~Fc?RmrMAb{HkMfXz&$bc5bvekWOIxGpt7(ekJ*;!oEdW}2rr2r^9c>a'
    'C)%b?<!GW?MvYmTCKv4wV>~W;>!XoHisnW98*6RiqE1prV`{!7TRcX8i+6%)ACQ}KK$K=ET9s^+?&{KH6TeJRGD{J4hkhQ*cfF;k'
    '1v*772y<=I`-`w_wbCozyXKI~9#xyA)-T2w4ptcGVZ~C|%vni81o4g*nL{6}VDW}g0m%-SeY_?gtwnpzHA!Vb_OUoXG}cCsl-X~f'
    '_<R=a{=%ePjfRai#}H95Zf>-Jr7U%k{%A21;y^_yNXGn>A<7+`??HlD`Cqiv18#vkCN*k@A!pTFf+U$Frz~-#cA{NE%=fU9d8cfP'
    'ivmVh#R82INsKzp(rc15#o8rrEaW{g`c3ZFB0{KBZU|OUVHM51%Z3~VXhS^sNsb)NAJ=fFVgxGfIV&E09mASh*lUK2xA2*LZZ>(F'
    '`w&+z#Ony!IOddkDznm2KkRa3bl%N#(OWb3V~z|@H|?9~9#e?tLb0xb1Vug=A*ODWI`g`!Ph%LrZAwxk!fHm$Oe+ic;+)HK?E7Hh'
    '8FJ*(d{0p@F=%e+CF15`b&$=d)RMi#;yYn_%7ziKC?Y0+Y$lGeOq`;?vU7VZgP#Rk@;ZuifaV|^RbX^{yrw)?K1E%WF@6eKYcJ(2'
    'j<LoiYtZ8C+ntmZp8?9K&1w^icPdYrJa)xQaOL@#?j4+S@wOkNo`upchbN(zK0M_<3ic;1#>7CAD4QhRHLl0<6dQ6tZcmq-)vAgk'
    'i}q_i>W{+7EaX<E^+fTahMmnIA9OwW#q;jimnB9O_u)aM5*rwLNIP}!Q;bv67f%guScmIupW~NuL9!2lSz|A5J#<Sh#xmVlVzRi1'
    'N#_G5aYT!gdAJ!&S_zy<$et?yfEiCyX0@DayO}kvk&SLz_FfCqng@#Csj#ysiu~E(iJIgXKRHfA50BXvnXIqZJZGm`gCVqFi7ol0'
    '7u+>?kW-#&wDFrml$<ku<eQ9kF*+7yw4;5D_`dAtxQ}txRX97wH|$@I`8`J1b14Vi%4el6<e0TF$1KM?O*54=1)d@45Gh;|H(wXi'
    'OTIzsXUCr8<w#`z4uPH@uHn%k5RZ;C^@^aij^W}viZ97rBuE$R6O+6gg03XoHV~#M>oLw<C*l}Nxdbi>Vr#^769-q)t+ZaOOP<`_'
    'G6~1GP~#l9e%fVC%uX}8>_m~Y_8^ysns@^;irrlW#aki?D6E{#EwScEGbo=29<rh(8d{~n>ZQC&B(dWyqqls60+kjDa{#a@Y7d?f'
    'XnkqEWi|5z*f{jx4!eJ(W#k+=XurSxVmU)h?cojIK)y`hT+9YB!%|NrFsdV!AZz<6YO^Qcm|={{JNDu{wXyA+R<3to$yWTH$xfkT'
    'Q%vjyRCBCbF9U5N9<6hz=wr`MD%1r&x^fKaBvqiyO?!j}IkwyKwsJqRMU4N(ZbDICi<|}1RwKsxsY=$6S$~-#388n=%>L)frkJFb'
    'WA&tb2wf>z&V}}p^{P>ONjgcK<7;}Rd_jZfah^k*BGad5ikdY>tK6<%f&d@z!<^zdOU|_20jL*Zui(w0$A(1Nrv;u=J5tVessy3S'
    'n%HS9G_i_x&*<Nlp$2U<a(Oto*@&f2IY-b7(e(MtVse(4Ek<&gQcFGXRX#Vb)=W!P$L2aNov!<3@VU;&J&N;h+1w+!A=`rXi=SN~'
    '!z{4XhB@Dr8DYpGe~EhSERClK{Hrs(qp}8>q6AVLqBZ&z^tb|TY-zOIQpcX_zP3|_!{Qt$5d9L*AsbDrcb;RRq21_G*ph^(Bxo-Z'
    'TIB3=fj0-u{uDAV#Ti`OzAbov<&p-dTR`56Pp-OEfHns1m-sc_DPa77z!L&acIN{N{WdIdk4bN{)hk&O={O>IKb1;{6Kt34_)(K%'
    '#3H1Lw)X%JHR_nE*71FnU46WZOL={8=7Q*NVtZ1TGr;DU%2_JMYdP*8y6xgwx3kur*~^CcU%+Nfp2dS*aufi)-@7JlrZoQPWC#3d'
    '4sFLZ%i~DnhKAx11C;5@>>M2caVdU!F%ueNYR2t|=P{j^ASJUMk!I`OFk_7&raP_D=Me;ahgf^@BHF}~E<_C?o-$CUWlhu`CQak4'
    'MLc<6%n%>PQo6FH9#YM8?u5Oss0o`H*Mx1os44nXGsi`l%9_g@N6fG3J;n_0_B97z)|^bNxyZ7n$EbPTHckmlfTE_8vF4;VHK$lJ'
    'M;qx?S#wxoO=mYXWok2xr7&ep*w(qGVft&`<z!6MEwe{)>;5Cg4~hG9m-0S1_N6aZd)TK|xh!Y+fN&fI0D5y;*!Lg#vXL%DNP~H?'
    'EcuQp$`%ep)s$m4L=w-OBj}Z2)VsyExI;I)BzuV=Vqvt=HCI^I;Aw1NItJJUPvBNm#*bv6Km&}H$}~*VvWWsvXFDn-n<U9h<*j!7'
    'lA~+-O8OC~3tEzG<wkZ>FmZX_4j}@RC*1^>-RL>HA(oxHB|_WUUP;5Avmltp5>r_MI9-fZ<5P)EE5PNr1Tf85VzXQJ2@f;J65Ymw'
    'cXft2z%V5kU0Fh;5_)X60xX)>2%I^mFb5m<KgsqdoKHhUrbWkyOi+8A!cIi_XjrNy4HEDMm}MdIyq<!6?AFhs_NOA)Ht2$Lq*S9('
    '1AwDu@VvH!9h1C3=-fGD&h<EZ7tH(~d`0}kxoTYz>m)@=CH==jG7fzYaUbKcjWUD6!G+_gA7t1(5nU(62*5bmXQQtVQO@Gr*myrH'
    'DB29g*%jo8744Hy!>nnAMC??ElZ_GJhgSag3*x^=4A_2;Bstd~#O2EIVaW>~Rcbw2I%5Py3(_i|wsXI0Wr}wpuH`Vsm5OmKXAhfv'
    'C=;nl@%zo0`~eO8DPFW3Q~w!^BFZuQy*g$2*vMaC&g2ik2>xo*K1O*(FB!Zk80dB$@B8GS0)?>ks~l;!nE!+=<uM2u4(L>rMwl`j'
    'EH*^9A6Wac@po|?8PBopUmOz|?MS@qxn<H7Pm?$uzq6gcgFFmTPZg}SN3z>RJt*c9480SxHJ^wZ5!O3ru}1E(#Owvp<DySUeb)Lr'
    'oqwUuexOnJ*^3?>=3rCHQM)j56hOkL(?iH?r-$xTOz&Y6VSDI~V|r`Nqsh=0uHjEYpEply3wrRp=Y_@4`{4C4^rzyy553wv?c;$j'
    'x?}siv8POf>s;i*8hRNr81*7U$Gm=Q3qSJLZu8V{a{rCVqOzZToV78(MaXQ?U!B>5vpDKer#q&FvYu}2_ln(=PCmwrGxIOpF*bLm'
    'Aqq4@TS#ModXNYot;W?R>bFf%zmt8ctlEQ4&Fu}r{x8SE!WNZoKv7#LVjh!}%J*nFs#el3$gTlt-a=Z<IPJ>VvP^6PbqKx-r3rfs'
    '$3VJg3<|F>W*7DZuTNA);pRm86prhgGD}jl`-P)XAKkSfcBAF?!d)-6TEwpA8(*@V!?`qCzOPzh79AJk{>~EfsLe6PjO%mEY|i9E'
    'nZ6WfES2$g*-{i2zBB2&F3xq*9}~stEYCNU+c-^#8%D5R)i8?`iOFU?zVfLTQvXK{bL<7F$8_KCw<U{t5iJ2aKgOJ1;r6sEHQ$mV'
    '12V32Iz?bK|6ZoNLP3kDIJ%me__+@yhe;}`F`<7I{CB48&r^?90kG70zkq|j?{j3bZG1(H$7`e*N&Z7SHC>KtuqDO;i~9-Qmr|ad'
    'ZtjosqWm)N9K{&UZ*KL+xIKP)n5!Myl)@NgZ;s%}fnFTw&4Kpn=${k3InW;|`*JLWCB<?4;UoXM(jG{Q1D_3dWjvE~qk1Zyi5M^S'
    '(Fj>%0={+p;jN8*JdsW@xaR5y3G&@|NLhWu(~44Dd8mjBJX9#6CTe(t4g+}%rUcr{uY6yJJ0fKzUFFOcO`$a*0*8T}aRh#~iWu`i'
    'n?ZyOkChis!eoo>j>@%qS5iQ-qa7l4Vjf~Ev$2C<D}#9R$)i5R9topfx5=X}M^U$oGn~$n!H!Xt@s$DAKrtw$a00|Esh3813iX30'
    '4y=<9L9Fn=Nsum%+k_rfdnl*YAIayA>?Ru7h3LN~dhF<A8#DturFKIsX$&NfmU;{MZ_sb_=TIE4)en_Vz)U$qm4tDF(^Qc6#hh|{'
    'Q=L=M;!6D*`qS}jG76K?q5nnfGrWN&plCadXDk?>Sx0PCmu#&EBPSQ%+wy%s20MAujIHAoRYxhWElMk+8(rK9!@H>E=PaBCq<s3N'
    'O-FYR!PYsRQgm7Y?JV)BuC1Qi=Yb(uC5APCYkMF&<BeC+j*6&-mi@TRrK+S0kdAzUuvTZe7L9Frw}0ddg|+-L4lGA4Q}%+&IR|I9'
    'InXh?&yk0WPx*cOFh2*D^<C6$qVzQ+`6XCO2OBOGP9bC;X1X{!D#g(ZmeO|XWs|a_yD^_DS{cPdWR*G_cy*_{WXtZPsdUvH<u0Rm'
    'w(r~C0|scOuyl)MWCd;Go3gPZlod3UzVsE0^0qhFG0n-^G|Z||<-FH0=KYjz&vABv*t?W#r|)9akdOg@d|B9QD%*(_S?yp=d%`Z%'
    'rVI*`k2}MW|B347Y(t5+Z!(|Hg8z$UKj-NGg1PO|9a9(~&Gv6F38LH_a?BQ)j)OJEgxR5W&MlmA%`xNWVfNdVH_WL9l!$j|y{yY='
    'yM-*+TQJB!lq-2nboL3?=#$FPgQ1R#Hcr7(jcU$l-&dT*bgn7pG<Jn2(JIGiAzWp9-rBO+E=BESug6sdDL%@)*^;_n!Y!C3OIZ*W'
    'W4X%W8vpJiUnUFgV7Z-qYbTDLI`Kk4s(MNCnkCDF^gY^f<9B7VJ#O5JP!|?#reUB1C+x|BLP;OzGOPxP5jiC3lQFU*Y3mm9=jYf_'
    'ISZIcd0%Ir+X>md(EpF4*mYCkKh{N`uy|&lQj8;lCjsL=-3h9WF-1Ek+$eD_^z{fto4nHQLUySIL4N6JOm#>1iGlxb%1n(iP=b9X'
    'OMkp12P5B~HYHf6ptC)MUdFOSRL++$<`{jNeCX%cmC;VP{1#~>i@0&wd}GkT@4^Km+co;<_IBKGHOt>YKH<F}=!{bIE{-+I>l4F+'
    ';9f^M10&YB+CUx&<!BsWaj8{?z8kd97-0N~{iz<XLO-su%-%b|ahz`QGGpsF3&-W7dT}1Ihd?)v$xbQdMeMSTI_1Klz1P@e58`S+'
    'qrhnM4BteeMbu>3w_b#(v~)uwNw+Ox9uFI&%YkkYig>8lSF|&jaQA^X*1?WDXrgH>khAbq&bxV7ml|!Cjx>d6aoJM_t{8hHWS}Cr'
    ';pQb}9j3fc1UKYVRRZngB|=_Oys@NxN5}(n$#CysDKi<{fEU*AbVd(4BWZKyLN##&UzA{1v4s9Xe?1d2oe6{9fK2T&alTbJub!Y4'
    'Z*79?6mOgqV>eM|L_MdxfAm{O&LsmUXv)DHZ6I>HA<I`MPu??yEML<`8>^#L;4*MtV~1<5v@V}HdN65#ymHblqjx^)Pzz26l8eT<'
    '9yk<9F}h3l$=UZ5%ZaKSa@l-_j~ps|ljva-W@xnE*Cb~yeJo-5EQCfYI^Y{_X*#xd50pX|%-&(bSbTS=!ATGCe1{@UD@tVW0q96#'
    'W8Gb_(ZxtElplS``N1(z`Nsc%v$gi5Uyo7K1@(WSt&aEpwEielUa$m?xt`FnlyVtOn7*R$UB=uHRCA^o*`dxHvun<D*W)<SHprVZ'
    '$MgUm0W&)J=`7@(i8EHmdm?FzDD?~Ft0!Mm{MU?Mp`(||P}os(PpPECoeS@hNg2*_6?!LFQ5W)b4g?UgJ!9_`^7dp*kPPRPGnjmg'
    ';2C(K8e^PImi@XZ^)CBHkt7|pt*n{Fl@p?;hZqo1$8qldi#U<u`#?!q@<6)iy0rf)+4D?yFmFg+MlS?U(ogaQnTj3{(j~`N2I(+x'
    'lz`vHXTU~Y$dty|DO(*_7xNV0J{B|?Y0UEZX0Js}@&45~7BgJMHK4j+NfOre-r_%6!>_8irRmCfpEA-ma}yw+!#v6Tq)-`!D`<`7'
    'frrS0Oa)?%IswZoPsJ?dt&z-GywpYU_sO2YAjbR5c2Xn_Lm%QxZAUAN1L}m6ETg96P2U)Ss_dA3Ql@lzoCYhZ+GC6xHYwu1n5nCT'
    'Wu%bJ`1_%ZqkCAGOz{LKa8^$kB8@Vy&gs-VCtpln={<<zVyxmrQbelajG24^Y0f6^2|B^WyD-+D#na_76E!+W>ZIinp8U$t=)Is!'
    ')7d(%?m79Y@rox*g9p}}Wq!JAWDS;PeLy)QqZ}#)sXYoi@71Gy8O!l1<vZZkWVGkko==b-<hv^WFSNAx4~jE)UShp5@5a#z(2ZTp'
    'Lv;Hc%5nUmWaEiGwc&ow@X9x$EA|Upa`||x7Gzo#eyQlipZxauRuJY?v@wlZgN1L8m0F{xM?6h~M40@@vo>a>NN*v_%DiO#O0Yg('
    'XXoNs0mmfXrw84X;Py#_g6DOeTL`x5h3}PP4?D~&GcYeecLj<*xw?)dHyG5IC1&c++BUiC?U$1MgmP-Y;nF}9W<|~UStglqz{q`3'
    '<_;D?j2~-V9qUO?*;ts3jm1fws?nR4RoODkp0Z`n(3TS!)6K^I!tCuY`V_c?&gR3W^@tgbi?m(JI)oz<*I%+fy54>(<aCalOs~<`'
    'f?D^sY~6GA?cDlBR!>c<E400%QC?GfJqAiHXW=B;?cHFdM)5lXwZyjqwZ`(5+ObEyx7NF;NrRIxow}AKYe^{4D8ty_xHF7lE@6aK'
    'imYZ=Pi^bzZd;G3l4Ok`_qg{J?tQFJmJX_j4;6DW1vd-Ul$jV+Vsi&j(b5fWV-L_J4YVjMB9?v+sg7CWg^L<Qo#LHQt!&eob<Cuz'
    'Y2c?Snx`Q_W!-X#X*e-EiK-sNRRw#KfwjJ34U$X<(1TVd1D=Lf(pwHL`o@41N--WwIZ%&{zN>H>EaR5AaKG+rZ9SdQe!8edt469u'
    't$OSw*TS7IdY**{L`96wq?4VJM@RGah(_Mk<K??XtqKo1da-Pj+wZDKcvF$XZD76OB>3F|?^g1C$E;o9&JU%+Akmp1+2QVEL^yW@'
    'DGBwR!RpG+>734(+djQnj12nAz#Amz{W3D2?NJ*JTt#E_h>e9-mrq4z4fAV3-X%4|pZvzUi1znY6kfJ#Y(>%vh4*BK+2`{X+co*1'
    '=P+`}nBz4p&5FffzDO71ukxugwjsME;<AYsfKl{Fmi0cbHjILebykk280yRy)mdDu)A0a@Z*b7{6W=cSHEFFV?lDtBw%FnP74ZwW'
    'n|xx%yi18Txs>gPvd-nxw~jY$3r7-(L3Jvturk(btVc3nu=TU?j)d<MyLit^8kHr>Z?4c~MmQuvE+*YAZlcA8JHt81pF`rI;bw9O'
    'H+$^+R_ahUvFJE%T+~>3nCL$FSK%y=w{}2%*{<C7LCCMLt-10RHo487GVW`_*1D;=46$aijU-x&n(+==Y-`3-<cT)pJ+#`^bn{`&'
    '5(kWuZ2Ttgs43!M;@uom7UYQ#{aJ^2csiT}8h5`z`^~4n5qd<IxrelflD=mDwQyIc9bV?bCPFLLs6Iqum2f7UVlJ<!hmYC_&e9k?'
    'P+6;FRnjQr)lU|c6Wti%of^l_S<*SYA6(A=%K8J0_{#m))*{3cPSCHdoG~YIT(pre#)Z4W(PCRm9J6$%7-BuUj=Yyq!AzyeLnCVo'
    '4P}P_I>Wvd?iW#aw6Il)9*0wBa`+xbBi&YZQ;JDSXK|1&^WAB{kZ({y;?r)<Wr@%8`M$V2E$htaUlZ$`&l?Z2pGx|Id`CR-tsrF)'
    '2^N8sX2W76iAuxdvS(3h&rx2o9%k5N(e_Jcd@V`d=wF#=41O@p_UfD6wtfs+T4|4lbxN(`Zal<Dgrv*DyA4~!y^S;0m1F3q5jazt'
    'v1Jc081u|kH`=2pHE*>Ri0NHGrpEi)X<M7}$vZ2vRR;zGIJD2i7$S2|k)_ri)~?6Q!MKyR^AAi@l%%iBFJRjF1u(21LAyA=0CA#y'
    'c7X|VKR4{d?Bwfg7C>Rl?1Fiwk`+^x$%WpKW#Jrhx}48}(aevI^P|jvG4Q)0|3x>4{1+huz-%}9FGMVFvnBu8{1<tg&iF4~n*ZWp'
    '{0w^+UY`FVkKZQy#T2x>60?u>!G16Jf%!RDa8e{pw9d3<!QLP}g+_G`X<Igy8NlUTIuWV43#I2S^2m->mh|(0X$#^h6}5m-zf?h&'
    'H$Yzjy77J7Pd&<#ZRq{=(9!KsbRYpo-)g)CYC~7oLnqvAi90mYhOV!N-cy{IxxgJrX+s}wg`P*uJ0TCCn;W2GzhjWpguCZ>FFWY='
    '2I!)mk&`-r?yiUK(7IX9Hsfyf0rc^D=peue*dS%rf9v4@`gA??UO26Vmbqu7Ie<Q24;@vOqAO=4Mf_+%U#^F41RUSTa#Uw`0NvjL'
    'efDlN1#~waKwqziPCU|%1t%D$HuQ=ST)`vDwMsE`TF`Ig?;6BH)@!3J!g2upM*gl%IU^UJv}jxCH}Q9XYrM$)KCTDQZ{Y8N6LiI0'
    'mF*6o-@@NTJ!iByfPM>qC+I?F+@(B#ehYsG=z27!kO`7Lt%80Nf0yGZhhol<XH5(G4g4LUZ%5VX1L(K#_f^8bl1C0h8+tX}FI=mB'
    '=*M!-^yUEi4V(ZSJjix6LGSDV^jkQAR}>~O_so*?brtj*I05`uR-9lwfPMofuoz`R2@w@CAn8p9&~KFVwz$U#g*)gsZ~_d8CQLbJ'
    '#Bu=r22K#>dp<LHj9}0;q2Is>V9pF%+^6*b`VE`_p?4TxKS9qL+%5EKx}SqSZ!K9EIsn{ZeI19HgBKlLi`opg-<|X1b@CVEOU5Dv'
    'zTrKc6uQNvbqjLo>~1-I4ma>5*l^MFsyImq-;J#?8gAi9Vw$%nIM0!-cF=F(N!@C<r_Z@NfPMo{5;%1?J>$dy^c#2*d9UJ#=6y^a'
    'K)-<}soA2jWWhCn=eMEXz?0?<Z79oi4O6lW{T7}?bEZ6}EV{Ez=r`~r41BQNgU8_j`VG=a2Loz1r%z)Jpx<!%lwwv!m9oCF2heXg'
    'eIonV_Ka``&~G?>cHKDZ&FRyRooPb9;q(csshTs>bO8N^(<iRg?MVWbKofekm@dYBwdLtkF9*<X;_s`)o4`V2;SZqSz~4J`Rd6Nl'
    '>w*5y+{oWOnlYq)Uk>zt<_7+bj?-x3T5y5`{hzsszoU8mRGj+Ff&S0jz~2M(^7N_t1L!yKcZ9C(IAv)ZV>dOS-@xAiibB`;f)gC*'
    '|I97?9dO_7P1Aw?&)mY_J2P+3SoT2wCvRA*md=M=SLiP70rVTzsv6~{KY<gt1L!xbRX@sU)k0_J>w*4H-mq3@)TNsk@tP#P1O1=8'
    'VXY25p0RpfpCsuW=>Oy`=flA{H#(U)!Em7elQ*nYtGdk^1WC^yK)+$Ff;50L*=A1Atq0I=SgSaV@j@}<?ho{T@`klKcGKwBToX9K'
    'f&Ne4Ad6WLc-2~*5}iHJ|H&I<u~4$?8QmX1ze!r+e_3~_4xry4Er||S(?%vZ(Es%}^?Nw~X6W;g{_lo<7o8BOhAM6`j`V*w$-rhV'
    '5}Y6>IMV;!Fsg_*?5yRP&mBO&=>`V1i{+f@#y0edy<Z4@9hR{?4KD}!KYhcTLGKH^TPq~J1O1=A>DI0zPL}74Ine*<TjmToGPptp'
    'R{j9`EptX~Z_Yu|TMwY$bZ)|bb64DFa_!xz?1nj0D-FGyMH{-gh0mbB+-B#?Ss^Ou*Ug!^ko58$$utZ*xHsq+>7ZBcs8c`g;9fUR'
    'Sa&(wt{5agVMNpnSFavJDTKTc=k=H96-N5YI+jUO`zicfWQUG0X6xKCq-;xeDxT0jj^g72c4Rw_#_IfR_hnTdJk=D&4{3eny1r|D'
    'm0Wje)@9E(z3l2z@AW+fxzcm+n9~c55&rVF7?-{=F49jzajh=Z>dw?!n|<zbHk2@?Gmq&suF=C1Xqda)o+g{mWMv6oCmPSWS`A3u'
    'MDxze{g;vI_^I)wD``8)A>^J;%qBS5#qZ%VF3bK)z-2X!FElH+_+-wo!>7^j0iXJ2EaNjZdM)6yw7xJt`#X>@5{_q+;}zc>pDT8K'
    '$DZ80vmds=z2RbS9G|+HE$AdwA(T1I--K}k-ikMP7`vO5Jv!rndQcJkqBP4NsV%Ekm0;jyONf!Iayia!M*dsmFSztR;?X$8OG>`o'
    '>YIXU-J&{0a5(H&%OhtKADHa9zO>6(s0_<?mqS%WR;Q9Lxe7)c6*T#beGtdONq(2xFTRp*4&!LGv5A*#IGVHV_JDQn+S6mzo-Mzs'
    'Y13Yp+smytxo?BN2*dTds@@sCWQJCITR4FOPhI{!+Tu4;2m5FEi#wXoBmCdN{{e43rX3gdNI}-<FvWAkw-CuHMm#su5>6W-j$&pv'
    'r)Kl+B+36kN{YTRiDTOCcrC@TF^of;uOOlKMdn#v52s=1X#>Ne<=>hll8RrQfYX~2j>D7vkmJG?Jn94tp*Jur-oHf{m&!baS5hJK'
    'z)}p61Mu%zIVYB?C7j~@Mz+cCw^B`bA0!rOt&Q?bE*~TCY$chKJaRseYQ`-Dd#txwu9%m}*0Eu2&~006*eW}Ua>>z{tdgcrnQZ6a'
    '**{^vYm~^QN>>#kHDEUF4n{V3Lf|MlhcT8Y4pZ=t=lyCmL36?V*U&gd9_S^PEN0%qdXFrzO?3y}K<~I_sMpYo79X)@K`&Ek<%ZIR'
    '1~GB_Wl!nQmy}NSc>kN?4sxQUlhTShx5JJ+>qmP$YNuN0M7i5$d1&11V1DeUqRqT7X8OvR(3hp7OgMHI?{TW$fzR%4Yu!fTmGxPc'
    '-imtOomidM?RQe;*qQZyr*!C-FSFkb?E9PdnDK)Bq0^g@g#BTe%l&S;V4w1RKV}#c?o+OW;mdK`&8(@ADM;EX`cwPRqpI9{Fkhw0'
    'cQ?sf$<}W&%IVFnjNFxxyE6T*Okb2i8fZqi;Hyc`$;&tFf+=cenX`TqgGOR(FROxwAoQOH$sZY8o;#rrR`QxUGZXA)4ckJNUeEE5'
    '&pl6xxy?VeXQO!xR(zLo06ewkxzavICRu;3V4pu_ZpQKmXVY!rUV@7ra-D`fYS%h(hqv`<`xf5ghtVAIp3Y><uHZcf_Kv;0PO_aj'
    'YHgNmXHiPXmrABGXE5Dp<Gjr=sEelyv~gwGLRRf68MRru*1uI>v;J)(^VGDSUI{I^v`ZTQ9Rza*0*{qDzQsR>Lzi&qufSpES(h!m'
    '#uQm=ap_cw*&^8nl-}zuW&~d6kpHlLue}&r@24SU1Ksk_h)HSV$F>M<9%*6jmEOqB65Y8HeS$%)i_N#Pw%FBXu4U{wJf+RMaDF;_'
    'mf4+#Nb<}PH#V^JTKBXSV%%aX`b+DsONgop=xN!tvESDcDzyky3tP$_Szi=2IoqB<I&)jGgvcd+h0=(xq!E9)G=efnj;gwmMpk)7'
    '8i^|@-Ba~l&gOo41c9^C2*zEco~<YLl5SMJ-p_gOVw9h{t-++(GL`EvQ$g=zc{i8&+0)wRyU1>j*NGb}<eLk_=}I`)-8!nirm0_K'
    ')F__eZbQruUqR@4!8>x3=M)?Z#+6~r20FkMan?HYuBW$4emleZ>el$YlVUJ_E_7q&hBiHw^BmsV)>~1P#rQV)#6?jwV)PG+4%Me9'
    'pYV+#rrH<_YDy)bw%F7jmcE$J8Rykt6lBaQq|nwqV~VlD`m)Y;)KBXET&lO(Pl!8p)tvRaU6ZY`^Lpwwb%>+qxLCV+ee$$7_kDp`'
    'T0eo4cDq%cv2wn%x#nt*^^jbm%i7LdK1r<NlC>h`F=nMSA>_VYvdAxXt{n#Q5)49YsIs-ih`!ZY8IiitT7O$>rk8W8wIYIbt2KRF'
    'Yto9T)mo`nYP2@o)|zr+ZM7D!=?_{{x3#7x*&Mf&A-dg~y{I+4+ouMp8?8<HXg!!q+EF{s@0@gvHCL~YUL>vc>HT4Qp4>{bnI9Ev'
    'd%I(~YR8%caWRUbKNj%Q_m+(ZYu77%aJ#ImPLG=8rLv9kgh*fUJSUY+V^@uIEblP}QrvCJn)%GM`FCc9RD2+}V%L+cTw&!*ksjqq'
    '9Z}36+<SJE%dH|LjO))b%~e*unCG`Svr>DbKhxe-_SW2<JZ{gNqwgwfD{ikpZm&N>-*p~6X}0Lp63>>DGycr@t^>=IU$VbXjPK-6'
    'w|AX~$NBNK=jgl2j{N-is&n*R=Z&yzxqcd7;*~baEp3i)h3^1Kil?>4iNa-(e%oqA;Z@!o7jOi9roF3r^!$t&&d_(A*YgD&;qO78'
    'I&N=Wf;ahLd$+83ecaxx&$M@)_s_DGB{wVLq?KAYjpE<4cH<380VQJXk~VDuZHGI3q*+i*yK#%bDSd~WWxDal8Xm)nw`j|2AH&gJ'
    'QigA4L!X_ooFz#q%0zVWL*5VgSCIt4zw*02{Zi?dPQQlq%cNg6{c`Eon0`&^*PMPW>6cHx*7%E}rG{S#Kaubg2|tnW6A3?&@Dm9?'
    'k?<1<Kaubg2|tnW6A3?&@Dm9?nedYdKbi282|t<elL<eW@RJEYnedYdKbi282|t<elL<eW@RJF@KH=9V{Q87npYZDwetp8PPx$o-'
    'zdqsDC;a+^U!U;n6MlWduTS{(>%rQNGxO~HUyJ#Fu1tG9U$I_Vds+*N^Y>pzXO|e0W3%_`EE!I<9e#JIPaE^fs`h2x0UJ)EyMkwK'
    'HI<QG*B$r_U5stkx$Y^x&ZEIc?7dz5YQw2N=IT2-749h-lO=0~&2|2eO^VDFUNK~=8}m4Qfs^T;QaPQJKU=oUZ1o)WxQRW4cY9a`'
    'uiSB+m&ILsgM!_TyS=Sg4t#b_L<Bmz8{Lo2v8T(?4XtnY-E}@~h{+MZDR=$N=uK)p)z5wmcT&3SseSKWJn~VlnY#dYFSnH1-rppX'
    '-z1Y?m1IJ{RKias{8YkECHz#vPbK_R!cQgqRKias{8YkECHz#vPbK_R!cQgqbiz+3{B*)kC;W86Pbd6z!cQmsbiz+3{B*)kC;W86'
    'Pbd6z!cQmshJ@dc@Ea0-L&9%J_zelaA>lV9{Dy?zknkH4enY}<Ncas2zail_B>YUm&m{az!p|i9Ov2A3{7k~nB>YUm&m{az!p|i9'
    'Ov2A3{7k~nFn(pg1%4LQv#g%`>RDCKx_Ta}=cKGGxv-Vl>V%(N^*mP3Q}sMo&r9{}tLJt5oK<@KT=j#i`oUHG;HrLbRX@0@ADpS4'
    'EBakUzpLnX75%QF-&ORxihftopG9YWuIL{t`p1g?v7&#h=pQTk$BO>3qJOODA1nIDivF>pf2`;qEBeQZ{_Nh#&lUYsMgLUMKUMTk'
    '75!61|5VXGRrF64{ZmE%RM9_G^iLK2Q$_z&(O=xlh3AU?xuSor=$|Y4=ZgNhqJOUFpDX(3ivGExf3E1CEBfb({<)%muISIlK7Ov~'
    'Un=^SivFddf2rtSD*Bg-{-vUSspwxS`j?9SrJ{eS=wB-Omx}&;4B_XBeqYh=EBbv!zpv=`75%=V-&geeihf_w?<@L!MZd4;_Z9uV'
    'qCX#!`MIKht>|AX`qzs7wW5Em=wB=P*NXnNqJOREUn~08ivG2tf34_WEBd=^X&RnI^(?FBzIs;Gv#y?p>e*D!wt9Be^H@Dk)$?3E'
    'FV(ZJo>QEz=G{)AccU<A`Ic*U>x4F5cuE}>DH?TcQMWtQitLU{USpqdc$blM_}AO{l4W7?U+I@r7f=1XG!Atl?fZ=L9!TBHR<HTK'
    '#`!jVTa3n`#HbOcXou04)~e<?qnq>VyoV_q=uf~qk!7dlZ`#y6{U>Oz4tzxP(x$Z@*J%{Vcm6W{(rz41%r?7->K6Xo+P^{Lblu$W'
    'r{_i+-if)fUOpy+K8f>LJ*^)^aYMc1q)piMc+XP!+~yHyS#Ma!dN)QCkJ_Otaqt<Ry3!|Twp*W|C3^iZZ(8=A>KnfwA3fHiPf@q^'
    'NUwSGiA+?jF+A}0lci7a-g=>kmNR#svnR~Ek@H#<cicxKH&uJWe8DOO9#GtIqo4ZGp0KBnd-x<x!`$ru45z@wsEEs!`eDe_r~aX~'
    '!~K7(1+yz!7%U58f^yX7^pC9j$C(rX=}69*zAUdhDJ3l<ds|&BVO=Bp#F$-eNyTm2F0D##Xyb5~+0C-z_T_Wi$ueSP8w(Ur65}S_'
    '!XMF{@vZBin7pq8!cNlEo$&{il<VTCm$vVD%uhq4+_;fPw&7lMJ9+?PkHhDU+d;o-wt_$Id1cs6em`0pSqH{q%vr0yymWHn9CN}-'
    'p*qK$$LTnV3`Lr1<f|meyKGzGZ7utR-L$>|KUKEbS}Wc|BQHgeiJNeD7JyyTa<^;RM|VxD)9|*oggepN&Mx^BZEd*Cp4??a=$bZq'
    'ryw*j+u0F^^IUD^af*s|Pd4GUacGZFyR|mOJ6p_C^PyRGXI*)swS#_WL%3p|?J?67V+mMw_-pyE;lBg_)%;iS-=6<U{ww$|!}BZu'
    '_563?zcc@x`0vPnxqZ*=dv4!z`<~nP+`i}bJ-6?<eb4PL-2TGtFWmmZ?JwN^!tF2I{=)4q-2TGtFWmmZ?JwN^!tF2IKFWVHCWJ3N'
    'c9$R*f+V+${Jpp*q37b>B0N{$=j!{Mu6k6{W4YxuOmTS%ui-J^6upKgjxFR=^d6o#o>6$iWu{a{7IJZlagrmFxZukiyo<x$Vy%aL'
    '6Z5WTFXQ%JlCyVh;yx6y`+jMzu*+$AiZeC2<1RnOm*U&ah(`x++dE2=^Y1cQo#0oy`0Bq({`w1#aa+P@k8!)Ti=$fo{d)aicfVpj'
    '{5^KH<JNY$$4^Nv?Oty~Xi{;_SRC|2d)(R(+Op+^(jM>Nyi=~cQ?9&IuH$c#!k3j4!rz(OpSk^++n>4pncJVa{h8aJx&4{jpSk^+'
    '+n>4pncJVa{h8aJS(31oq{6%T;u?|+NiJRWd{&Z)H#e6{Dz=hT+)h$)J4q!=Gh!#rL`fw}Gjb=*l#)sr(_rpXT=LJ9S9Tix{{()2'
    'jdZlj1{qpw$`#k_4cF{M*X-U0r||Y(b`4i;_gNF)Yxcdi?nAZTHpfCW`TbS0SbN;s`$$`&Y>#nsu3t57*Jv2pZ`)L~W!<LSc9j(K'
    '`8Zr5L0qFRx@KJ*z`a81+GWxUJ=vT)yByfz?U9b+H;LpoiR8;jBq>6|uTdf~<Jz5(NPsF+$s(FCJlb^*I8u}U9hAM|JluxxYtw}6'
    '^5LD@>#yLI2mJb)-Qn-089O>N{(r}b_nZVdk!Macb(d;sx6e!Uec@ZgYdFzZaiYvYx*Z3JoG5E(#ZE&TInlD?M9YB|*I93S>-`rx'
    '75$=e)4{D?du23ls1C|rqg}h^JaNS>*+FYpoG-7EY_GUOY)jX>Y^A4gxMI&a*j<{tz`?C_b2QtU!}b}h{dSk*^!gpHeMj5gU9QnL'
    'Tr(C;xCeXL6)WJX`Oua&t~hlboW9%hp$WIWr(dPxZujIB<90yt(LT-l=x;jS-%eCt_(ZiP_`kvv)gt`4J87V5*qx}x|1y?MyPUbF'
    'cC2>U=FW1k6Sg5V`FC5Nd4O-bZ1XhJ-eLDV`M)Y>+pi=#VOTz4*jrB&+h^a298L7Xl^Ir0al)|m$}G+k@q}UPm06r8;t9jnE7Nza'
    'm5J-h+s=4<eogA#nhe>w_PcN#_kF)&zjHpHWww|0YxP`xU(1XS7xw#H_4~Z*_hr}b%dX%3uHXHx-`9hFpP=8><jrUB!nQQr<}JH1'
    'I>9%ux#4e1Yi)V230F1GD+k=^8qBWYZ|%3&>@`i^-NyIe*6E0w{%YjMUyRG<n3TUNE~}N-t<{dtoE1S88NcwIq<7=yT~F`q=AEK<'
    '!{(i)cWU#_(mT0%N0}f+=_Roa1TXsk@;idpZSWfgdbh!EF!XMN-$3nl8~g@G?>6`iBfZ<;HxPc^7QY$at=ZN=tm`c1f%Fde#g$){'
    'zWAaxUxxg}ubVGZ@ntN(__6q+%P;FveCak{eEzabn=fneWhlR3Mv(MHlwWX`$1gF4L&!jibE%A-o}NYZTz|jzxq_#w?~+G9K8w$7'
    '?=$g>a#?yFs^_V~f80LDJFN8VtLJt599emMwgrB_t@Yp5`WId6)m-~ef9}69ykG5eN9!&BKS}kN(RIQ+Q!`2bC<Az><h;qf^xMDR'
    '{{8mvw|~F=`>*>?39YqMEBs&JL0f4xD5qnl%Naxvq44NEz+ZUoDI}om25qE~!)hqfsqEmlGhO&S^zfD=pk4?a50*+}bkGIk<_>lc'
    'gCEoYGTSgn%-}BZjp<E?ZQ?!QuFL?>^Wfl(Fbe*zc>77^d%%s~0CtXQY51bUFMx|-ed({E2%EzKFp!ef7$}3Z_Rt=MZ>0Jb-w{+D'
    '0s%wYhQ1hywO4AP$M&h*KsagoCI*6qaG_>z0=^jk(`&0j83*tC01sO10p0>_%m6b%G1w}%Nd2P`#_kJ^Q~`0tUZhb1N)2Jjqej1R'
    '?2u0Qg8j_j0+xWsgwL%W*tXlHp5xwG;eRvteHaTGD>Ig31#_W?nc)Z*hqwTgfqLKVAYy-GPavEb>h~q2gR&QvqrMb?gA6pEEH`6W'
    'z*QIH<mj!U7IBUmqsuzbn@}&renoom-Ua4<uPDqkt^-_S+TxoKVYggGv6tW%{M8y)B+hysDV=}Q{1!k3VH4LTj#GTgb!^Y881W_i'
    '`wW5Rmdo=5XccKT#&WBHnF-^sQJIZBO!H#Fd9;~BYoI^jvYFS31_LcjMT>xuvDnvb*hG(`(NKgR&X@tI2r~q+g890J`ATz%=9dZd'
    'I^t#)O3y~eHPR@9+%9ko5oTn@i)q0Y6wPsA()usTRBL4O4LR39{otUSru7N*;H<%!LThNIk}W*qx0SfcLfmR4t|kn{D$Zr{T5j{V'
    '0vhy+378QFO=Gw%wH?LCcYA|W0#w{3;1|x2KCB+&XeA0-A;=kdH4r4=P6Qd(3eBg3(J5wJz`@X5MOuh1;u`>cMjH39iE4WUy`1Bh'
    'Kred3#d7dJjdPUB;|ikvVN-UXU2Qp<rMV=m_8z%Hb1tWS>-_g(>{r4bxDw9Nh&9bNS?_1Ghhcf*Yk-%DoIie}x_!Y{OPr4Ps)DNm'
    '7bITS>ObI(cGI)8(?eOr1Njy1rajHBz+D5MDW!mcIGBmj13&{xao*yb<^6>?BRt{A>Uyu*?$mWzkZc5Csd6bptG_OXyotCm<Jc&%'
    '*;B%<OncEBB!;ew9D-(IW1rl79|#gdCw^3Z6+t>EXvUT{vI31|;I%k^PSkFVN1z0yGa9`x`)1;(d2C9UmiU#z9UzSYOK53Tl;!I&'
    '614x397DTb*q3*FY*(*<nR#3>s*=`*qi>;Ql1EWC$ffpkm---#QQC)h`xQ$Y2YU=lfteFgKkC#2h19x-%VXmYc8#Jmt!{s+7i&qj'
    's$cDG=gt>OgRI-be?i`XwZAHlatzMmxHf7Zpfm7RAl3ssl%p)X!K}`!nn*gLxrEg1VIH4Q=q)m(K4O?55<gsxx*Q&ybp+sNaJGN|'
    'qYGHX&7j9Y8tXB5Ae?}XsZ>)qA+_7fvLWD%r>vFESVlX>S`)9p71jsb59=GC*(-!%P|`#=(6a!RdK95_St>ll$I#ynM+9I9H4`lC'
    '%bsx4^~rK06K!O@OZH(rLt*M<pkN@_u&abtfF7YHdWT~w=si*x<mZ{zzrzuQG3a_1ea+6(Lo)?iz~=?N%?z_C-R|GYtEG*r`&-bd'
    'LI*q*C6{I#W!Pu(7+wz#|BE!k+cZDweeO#5+xdaNxL*_A4Vg2vA-R79UulTSQsLb9tN(?J&f%`8c7wU(AErV&@vrCG2*rOj{~h?R'
    '>9!d|Pto_)-B+)EetUTO@cPw%|M!3I?sotCkGp@D=1$xV@Sr+3+yOh4lD-X!KKDI*mUp_B%HF~1SL#kmr>ICTsfZGH_O9oT1FSTF'
    '1;bPpK@j+;VRwg@u-NYOogJW_RPfnBb!rnyyF(F`9!02Y;#Y?s)R4aY2hjKFae8`B<bCy3LDg5!<EQse<MQA9hqsqcUq6L!158D6'
    'hb?}!jvwE@-Oo>tk53=Iy6bgnF4p{detzE7`u*2JbYDZqYLs2?gao<-ez^a)KMHyOKfnE#|M9zT@9+P3FVs3dynpxIn=sS(`Y_+W'
    'zP&tr_~HJi2mkXoGrSh_kK@bz+spXy_WI5I?%h{+0y<@|*xPM@&reV9p;+i<A*_OKp|;2Q`Jss|z!=7lFHbL{`smk(Ej-cv*^kTr'
    'dibzB{jBDv=TGk*zk5@!&*O)0;P3S5&42p{jlh8v1{BZ5PHQm;ji{nn4_z=sWT9J>`C3r7h+*3;Cos^^?1NwK-=3bI-aq~D38}Lh'
    'x}nFZ$kYLB!#%zM{XDmce);&}?cvckzy0tsKL7YIkMIB63~S=)eY+GO{f7<K-JixE{P*MZ-oFa<@ZrtBynK9qyMKNE^!DzjuOD7t'
    'Mnq8bR^q_u+$*v-UrR(?OS|or;|9dfG$ecIPRknl5c+%z9X_bgVY^mOj75)~_HzF?K0m`eefJZzh_~c-Lc3y09s_XW^7!!j3cLpA'
    '2P#ltX~!`<-L!c6`2);?@x^}_sj`F0_QJY<^)Da%`}>zC=q;)X>*CV7Z`k9&17OC4y86;~_5c3(;NL<oN#JP0ii>(lzrdRNM2%U2'
    'jQ5hp%+J6ia8N?EAy<Q;w(e_1W8DE`?k*bZ8(0(U@)B01yogAUZeewO#OZ|G_rbr0-i6tC;mF9>@$nglW_<rXR_-pXte-x<J%4<='
    'AK%{m<MSKW7nct0@cQ=j5>ZwcPbLFf384H26FDHy5V}ht=%2^G#!AD*J*A!>{sz;3L#wqHSJ&V9m!BSH|EKrk+xqnK7^VhIYY^$~'
    'WMftvW}W6cPs{zAKYn-LoCFN|`<L;<>+{pg+q*x0*Wd42eD}`&G`@dW#y9`&Pk;F7aiX@d1Ad9N2iOrlyxj+u1shL`Wqt8Rh4{gL'
    '@Gm0@X54gpo_+C_)zh>85Qf)+d?z~H=;P(#_4)ny>1?C_5X#*$zRuuIKKufWmjevPhC9{j<}cmoet<z>x^PKamQi>q!-O1KbMi~0'
    'oM(m>xRZ#+%xE?+!ujGSe-G6Iy@7!N@3?UDALjA-?c<BTf1P3be|dNcbi3ig%@O(L!`nSj!F-p97-R>h72B9$P1(o)?HSHVz`BtK'
    'GYh_Wzv&2p*SB&0Yp805T=n<g{jcwT|4(1{#*zdJB6F__LCxx~`%{vdOA@PohX)xP=g;8^x;6Ii5a@nFLD~KE`Oe(GqyHEl_%OYZ'
    'nM9J`j~{;c2=Z*>(DlRnPtQNzPas!(g))8*qNUYorX^bMH|3;(<0fjdV!1c}H|TFD=kegCG@KXmUU5Huy#ML`QQS+#qG1Nh9e4ks'
    'yT4yVx4eu$ho%S)Za6{>*F$myX!h^l1Ds*N19h*>4H%i-2LNbLq7}AN8-Ra32T<G(-#&csgSub%$5(j5w{U>&?6siW_t53P2LfM#'
    '+VmR$!ZHKATp<`D#K-F(itgb92)M9I{2w4#^$ypq)t?9Q^+z~Ek+cmU^&o-&cEjg@)XT%m8v&EOy_2&09AI*MLr4Pnr2Z^GZvOc4'
    '3cQcuS=8Ws4!i+1A`b*iX?y2B3ppWI7}?h!@1I9FH6u(|Wp_q>9!wh92@Y+GUx0VQoCa3k^`8Y){P?iIafA92@$8HSwstMZyy9N`'
    'UtmK4NN{Wi-sf(HWcVnBpir?ksL$%X0gm_n19Y2G!T_Al8w(A4{wtz}Dt3?=K5w#wC5y+HPdKa=^=sCC*5V+DKl=C2fa9QWkA<`4'
    '=S>s>37h@fN92D-<Ke$^<_k>ek01W};pyiO0M!n?xzpyeXcs+mz`u}W15h0abwYj?uAxi)-;hPXqEqq?*#rX&GRr-~0<r%iZeY$>'
    '<d?TErocoHlEo<|%xA523y1q>_(by-WE0%P4#Y&+@1c?2ILMedLt7{0AdH!Rd>J48^l@GN%b)%H^s?yZ@#WROi(1w{oKds><tsRj'
    '_NbDQs_NkvzrKfIy?>=0Q^SEuz-Xi{#`f=7jeU<NdV~Z-s_mZ2n$kqt^T#(Ls|P`JC|Fj6L~<8#k8m4++NQ46ZQY*(<Zs7MPaog@'
    '^zyVmy!YRH`zYVN({vbo_XrqiRLSH+;G=(heEJE<K^_00qN&i7_C0JXFCet%K|<9He7^@__AgJc<-B`@f7BFe%T>|T{7g*d?nt>Q'
    '1@z8-GQE5J^B?~BU3ahl2Min@(S(ydt^wBo6a{tluj9)bO6m5;@n!jWeDU&|r+42X93lSkVSW1k<>7}P{L4E428T!W;%ASdwSNI9'
    'Bw*u3>E=ANRUfN=e0X_8xPJ!G+rL^Ad$5b%A@OiR0^+x4p=0gy@RNUeSU+XTD~kU_55j)?1mAx5{4oD6seQvI*%kBtcZE(E&N_I)'
    'A%U^k<>sHp56jcK@)WsrnLHw60O{Bb=4jFk3ES^c$^Fe!DRI&|BlT%7?EwV)J>O7Vzk~&>6uc<XhX-mM?qGiR@$JW_mxs4c`U9@B'
    'aIVtDQL<Y5>w|y41m!id0O$IW1>FDJiBaZ3zI<rk{qYa~`u<<OzkmG8<GcI${WpL9!*{=fbKvxy!&ihU-Ul^S?Eq`->E)B?|McUh'
    'SDa6X#j6lRqkn#yf4mR3J{#q5VmUaIndQ*6SBF=DjZRd*o1Y&v>GLlhoU0VzQs9M#?N2gLBnrwJ)Sw7B-yZN|*g&9EzTiAPSbw)A'
    '*%;J+ph5k87*vT?xp#IrRH8Uwvoo;lm+}e^c19yDDo+Y#`}j<Js63}vuvAjPtnbGkUUz&Jrnb7XqTh6B+PI$HzrUaS4-X%3|I##1'
    'xNA3E|2Sd^Mca0#j`*SbXPUDAJU%lg0+M>v+@Sp38d17p{_1Wspl28m-yi*DLf(VjC5{zteeC9Yyy&fZ=FhOLwAa`>90=5S$}B{0'
    '(0<09l4m1`F$sBq_Ue(R!2DHvDIhc!7A1&J{jgb-2R*4kuzjWN2oBF^AK+|rCFKp5rAG~WH^{<AV-<R#{{i~)5tuC*7F6WMNs{hu'
    '@h;Vr7yh}!(*}*YGuR%64<8>V*qBjPpzBxHU%baC5JsMH?nsRq7bi|*g)+<Y_%?%_E6`W^&US}Xm+V2)?89A9S)50`Y<4WG_wMPs'
    '2(`Sp*;ymbi~>(>7zI3FtBZD*UxZ<aD>+s@vI>RStF{1*^VT$EjN8P#IJHoG>Cl`4c9<^(`+DN~Za}SIcO;t$Ta3t`0w<6fPEvSR'
    'TFjUA;cuwS5Ar>Bm@wKM^K4=w$gxed==s0@552J}H2'
)
CAPTURE_SEPARATE_14_SHA256 = '0f720da87618f5c85e2bde71fc2833f41320327eb6872246476b0f0b5c2c371e'


# Retained checkpoint011 GCC16 capture bytes; reviewed independently before acceptance.
CAPTURE_SEPARATE_16_SNAPSHOT = (
    'c$~DoZExktcHQ?~=B?Cs>iOXUdZ8$GBEX3Z$wmwWL8BgLsM}4pNcP+r8~*P8t^YY>A0D2bF$@HWuX@<*s()4Oz4lsFyLSDzANtq3'
    'PxFUA|F<8;!{;w|pVp)P{G~nr{KKDr`0=j~kAHdk(#HDnX*{;)@$-+Nj5t>cA?@;G`}+9s*gpL9*uMOHH`=EU<Kh14;nVuyj7!#-'
    '^5gpDZmxU&{l7lk-LLs!Ka8(W{NKOc-Oq==elW)U_|q6Rotqjz{Ou1<KQ|W>y?47;&B3&g_}^q}*sJUwz4Jafw_=aG@t2jqT+S}r'
    'XAZ4zUu;{k`XB!L-~KRu{q=ugJo=&!|Ms<gy4wuv`R?KVWkmJI$A^dKAHP05{@CyCfBdzik12fkba(&t*AGA4fBo>&-~7!7n=VJ;'
    '^7h`EZo{l;MQ>K$Au@2^dRQjrG|aL-t`TeY!{yj>>#Z8IX0(246#G;A>FI|*|Gz(cczT|HH~!{toTrNq|K#+)`{}ujzkK-m)P7pW'
    'f3pyujwShUcfTM0?&+(3`v365<NvN-pC8-lPmhfD_!s+eEn2ysclSS?n%Ez{JU%?Hp|Stn{lopy^5>`LM}Fhs3!lO4t)G7TyH9t0'
    'oLk=a4<FXAV|~%Td3yQD<MZ>~%b!mldT#jKH9u}ozuk|YA0O@?zCL~UdN0%X@Z9>R_1eh0AAVNLn9+ZI`LdtZ{d&XzAJ<P$A0F;M'
    '{r2)tpBdVRPY-<aywm6Rug~iP=J328PapZe|NVdd=YRU=zyJ83|J}d;$B%#i5C8EW-~I6a_~*a>kN@XC{=?t@hmZg8PyhG7{L_E<'
    'cfa!+|NbBU%YXXM|NMKu@ehChACKSo|Ni!e&ku89A@AL1v@g$JA2qUv{;$l{vG!luZ=W98{L}ih`HPqT!V3AX_4MUOy7}>c`=@{U'
    'PsjiKmlXcQ5BRIEYu|l%`R$*-eBno*+Wk*ov6eq+0@mlg=AZtBKfUz+<>Aw(51-d_o9(&%>0h57)Wh9p{=vJSzO?(mpWFCycl_bY'
    'IQ`$pulLV)pV#r{cVj&L=INh*SohD5za2k$`G#*ldHq=Z$LIC=;pON2!}WOl@iYYe3A4O^x|0E3w*RNY1z!GR+`WA4@#Eu9$ItZL'
    'r{5gspS+CV`02}k9DnnEJjd_6|MBtL=WjiJ<^1Q1pMUsrIk=bqItKOfAK%7x`U%GK@b&r2*XNHfIP>35K>nka`^T3t{rQLJM{5n#'
    'v}VsdR`GR5>r9%iH4{_JYn7S#lO4184&Yi}<E}nUfTYm(b-NEV8}eLxFUzml6i4W^TdQ5(N4G-&wsPLXq-J{?yEGG`i+yC^&9oic'
    'jb@n~+6}cBSNNTgTunXg6lx6JE)X#k{YihW*3=zFcH52sa2ns1Yjei8?Oq$xpMUVJ)I5S^%%*u;`|gDaAZ+mC(b7n*#O}s&eXWtk'
    'wwv$v!^Ui5i0O9wHylQ|KZhS6J0GmiHf@?QVqd{9%{^?#Uu|Z)**#n*jIkyu?KN`>go3wSU0B1Pf1s(xXV31l4Vh?XmPvgqpIxPo'
    'MVB!S<3?kEJ}jcjOmW6td@d%%8%+ZMfBs<(Yv*)vWm9&oei37LNEpOUw9kB(;%Dlae^BR0d}<$&ctzmq(S=*>>U+1@y|r!H3U;T3'
    'aoM;!V=Xo(Z(?16mV*L&U6El#zuGc6IKr|w{i@yXVcnm97^}8Hpk+RmO`$^yLKu}si{-x<TQ9ly;To%*Y^bYrqVMj`)w1l>oZocj'
    'KmSm0qa82{CMM^~zs6{iv%`$CH}f(E#yU%jw&4W?^w>6mKDa%bE#;3oIqcM#GJ~h-luV62cn9@K(;8MFH(#=M&fDN?Xk|bc7&Ifo'
    ')7Oq+{9zx5vt?r=bZYu!QfRJPtj@~V`2+AU8uPRB8Z&wy3Z7fCtu{4`*~3n*mgQD}fWu7}m=~MMV(ih`5J7<zw&uOqvMLS;b!#<Y'
    'tCruaV+T{~=)v>zw|!j1f<OPTM(braWAX;Cx?|2pUQAH(w!7^!_Ssl^s8<97p>Jh@DZ#es=*4}f=_fTEW8ingT4vV4#01wft@E#{'
    '!P-MxsjdaJ3nr%>lUup_4w^WAC(f&;FHj!yVU*4dyXFp)SzXIQS9@K!>xdSQPHC>#7NnG(`wR=$o)`j#giYUS`(&8G)zLr|gW3Cl'
    'xdAa1jKeyjoiXILeYM4Jkko>01df7%Hk+2m5UwZWCBA|S!8cZ~7D7Tzar=lnL%|E!(*4RV84ub;gM&3w-Lxx#`O!3MJ??(9;ll*+'
    'ZjYBQ<BaJG^GE=(1DXj~C8ru0z-p!7VoA{@H25;THk)f9*1T=`GJyX12b;?<)6@y3E<3F)KqE#SH15&UWTLZ8we}FBmT+S?DR1Id'
    'm^Rs4Z66IYvBb0q;;m$Da)$X>%cn#$0I{E-kRZ*t*c7S2xm1Xky&FI~Us=aB2g3S*i(EtKsngaX9NS%6A>@`gDq_g4ZE~Ui(PHIi'
    'JI*-`1N6k0TyM625Jf_VUBd;w#w7fj$(;mGVGEkbSSF_CS%b`E<%x~w5X_2`P`~+=-EX&jq8h!<m>SV^j?R)f{I43o#e2}5g)O6G'
    '*90J-{~X)77HpZV13zP%+f9q@0wWL(TsK?UuIYv7AB;p*+ja)4&xM7=oU<`)c<aD|oiV44O-=iqDLEDs6AM0VR*+TaTSKkRHVe3B'
    ';6ol0bDeymiDfTvIc1dQ7!$iB_TFy!Fm7zPLuKk}nRrI9=!|;tM<UyrU|vG|IpAyIgQ2z#uh|2KHDDy+<*Mm%rgVhz#jk-zOs{c7'
    'g+x&BG4OdX2otiOlaF*W`>1$|@vpK>NLuRZ-Zy)A3ogr&w2<L)Abr7YGWgIiG{s3mi<=nc-dOYYbL31gwGl)tIKz71>M;j!5i`Id'
    'eu+=kC^zzVl!{mM>VnH61uKAcz51Y-6Csj46DxX&S5)PKf@5!xMGI2HIK`n>gJoe|ahB>JQX_BccE*c9uF>O2-7SZq2SOWe+iy30'
    'IAA5{1xN#?1#Bh{gX$nXWYdnlJ8YJPT!ee95U7fgxu|A>AI$f(w_E=IVLq;90mQ)@V%r$S4@TUUH#Mi!4B;_^XmTrNF|s{m!49v3'
    'fe~L~4x+k!e6Rge<3yklhBYRvG>6fc0nH*>5?YP`Zi)O2Bp!O2B9zwiE1ij>H*;kp?}X`}e`t{Al^oim5m4qf-ZTf<=pEJwXS5s8'
    '?#;Un8f;iRaR4F>?}4j#WW|3+yseL)?(YBczp{@7M1Fm~`}E{O{s8WLS>JYjPTzg}{~zwxUoSU!Y>V*KA$c;vRE%rD>nE|qn}Mt_'
    '2I5`uDF|-YE><oXBQ20dKAKtKqo2ml>vPi#d~ZkX_<#?;$hMvyzCMn1q5S@@_7~>zllBt4HjU&2ER5g5PPjj_3WWr3V(^QYj248f'
    'yCyEb!hj#Q4tzksLOvw;X&>;%i)Q8RFrDflY-QBlGfV?8;UB`RK{n?ctjKf^2DJ#qu1@?YFdaZdxoo!o_N*m()_%=--4`ulCQD2='
    'lq8z9Vb`wtG2AE}0t0G7J#YkwkgzvatZ|1fMVT&}pLgx2`-i9JyYX~x9nOtHr3d0QWHb5(G$LPO_StL~EW!YWLlk5@5NOC9@Bl5L'
    'FNDjR*7w8X=k|PVm|&1c?g2jI3fd)>1<lB-h(dQ^XoqW>+T0!<$~!HF5Y6`d_aY3wZ}{Wqc6a}$akTCO#3~@8GZ54BMzWx&ry)Eb'
    'DK})mCfv6M!s*;CS4cb5()w*XDzm+5{qf=cdELMG8KQ!JL4f8nTaiZ33O`c+jV^(oLF@<o(WgW!&<+1W0{7Cb*!yMEKQq@KPbT>?'
    ';Rxw1OoRl~FuUoXDP$htEU9<t0AQg*;6PWT4YH;n=95dlnZ$rDo4>mUf7++J|9Wi0euRWPzjT9e0S6{L5OM|1XTqW77c^N3MTQzq'
    'bC=cw(yYRdBnFZ;SOs6jyzS<B{j?sh?6N?N;OcyB?rl#v5wL-x2^B(ISi|VzfL9`B@COiO@ev*xg0YJAyy@Zb+-T)<v-biq3>YD`'
    'k=$4{dNCt=F?HxT^UmCj;Ts^*M~2$rWTxN_ZyWvisr~lw^~EBwx?V73Lu0^;PbFh$6|Oo&J)8-BSqIz4`*GQAVRr-t0x8_sly%ki'
    'FYEDc|Mp_-WA*LCx&d57T6Vre;NYndS7gd#gngm}@XU&x>`@#<tutv@Sa{R+r}gW4nU5BtxD^wDJ7L{WR8St#$P7;f1AG&<ZY0T&'
    'M{5xf6Y)^E12DXStWQs0egsO#U(P-h14BieVZv<$$l`*Q4zq28FlCSYY8#W-f(9fRUB_e68Uq8l`|Y+*-yP64SOEi0)0YWsdCQlw'
    'atJvja>6r_iiB|Qv+#gr+}Wq0zc0mIw|(LI&|$t*GIjQf3<YL=Y(Q1F!J382_11t}rO!-YWG1Fg4B%lH3PyX~^p}TI6o2s?7tn@n'
    '5>~wy2|gNf1cYZLU~EDJ<PmDH5Mf%GD!l{D)(!LI6U=q{PwVlQ*Y(7hSfqxZOy<IFma13j?<D4vkslCqVjxrQff_<at$Q<t%NhW8'
    'TsMA@kS`C9uc%uN0~y+^pc6m*f{#h%8Z%hRg?nz|utWK^?4Z&TfX2qsaOEB^+rOCeWPp9tlWDs;Vj`*m<3&v@!cqz?F)WZCp`jxw'
    'Sn-U06Hg_+*1Br;VSfGe3WpPt?<cCfY^FRce8)#^gQDL6Jeq`fBmLWi-XQ&%X*Xerh#2^6c?0BM+T+vfOcQy!7CdO%11f}((+cjM'
    'fmxgo#_yI;q+*!DV!}9XT5$>%_N|#b!9VUVf@Yi*=S59KID!Fwhy_qq1dHAB)S#Udgi>%!EuOLnPAI5cS_RWwecSfqFL&R<116S<'
    '3T_cMnb$nwjw_F?&AYS+8vIwyzOo*T09tnu_$FrAjA+6e19|%G{<;17LL-Pc)4-aYH7>M}pgzpa&af0>3xjd+&^l09%iHQF{2g(`'
    'lp~?8!rJrt{N+=7e*I`*DNHl?^a`sQ(pIKGENqVi25J8RosS9Ki$I!wVMK1t;v#D_-5YOz{_V?ayD&n2H9~cnY$H(3h6y1gukDzW'
    'WVN|~2_rlv%L)KjLVaj3BM%r~w)<;IFFuk>aF*%o+msz^K~PNXP5KTRC4@}w@H7N^_JL54%ZC0zSim&xW9j_i*TxL2C!KS)$KO7l'
    'PHg|wj%|9}HPMFO*l~^y<Qbcm_d-qYnR6Tkl@S`zt4OXEC@E}?e-zC+wryUUAD`OO)5l-hr?1S((K^~&JFD6TGp!Va5bKKf7~dUT'
    '8enwpy^vunEWTm`GTTo$^~i0S@TT>L#|5c+{`u6jF@A(%wl?Xs`;k3r#!Fi0n7P3xz(DPDgR7NcC2zGCRKb{o23<D2zuq6mqaPo@'
    'K8cv~=cgT59`vHG#1=?(0oO_g&*4&7Ct(1^fY7dlw&Crlu}8d^5y!Etz1hd}!(Z0@n^~H<@o~8Fg5P+ecO_P$fKlnFeTEse!_GXx'
    'b5W|RIAfEx!LUj&>&+~omhRUl^v}b&al-;LDI4}y`D&s$(iS<14GD5so1i|xOYK5n=-n};y=nKeo4sx{{vu?~U~uXO^;RbG5%y6C'
    '8L2q5)4-o1@M@=axrV-6Oqg)WFc9Nq62m=%J@(SS)6c1W&$puZSz(}CdoSqH*bpy7H=HL)7G+=`?TEjbnH8-Gv8ZlDa=$f6^X>^?'
    '`0edDU~P=s*_nYD40D2)K|3<2B&bA$r9ub@)tP<`x(EdbM!<`+(H6~(e%^1|A3bS{8_Zo3LJ%u`rH0e?D#GqM{)m7<kChnd-ohck'
    'SHPKA4(lM2-RSAzugc7jEIY4$)BbkL89O2PS7&L2Z~;ydOFHPb9ca~|+7m}fI`2rE>1{wEBqiPG<ICd%1N!`SET#~uXfC1q>>7vx'
    'nhYCqhlgZrFJ?r^-VH)BHBm5qi)9-Ekpj;9e$K7|ZQRkj6~PS<V-Lc3-|$CAPZPWwshQ@{{)ptJ<D!kma@F;UsC{EqN*#Fm*d8C-'
    'Z|B)zr3rO0u*jWIQ1&(`j*P>k?9c;r%#S;gfyl1SsEXFdp*Fu$%^^EpTmQVCe}0%Jzy7#>9Y44GpI%&}V5f-TgyzkQu#iF=0ARNa'
    'BoWXCLx7Qi+$Gx~Aw1=Ub)oKCe*+`;>*;yT8z7SU@WyPN96*wBdS;^$921>L@}MTCLE1ufLWyPy*r1(;*v~4sH)A=q{xsVCd7fZ_'
    'OHz#g2WiX|<bn6Kg4WDBs$7Gy)TNNe%y(EW1a}s^CE+g`z-du`Y;!)Yr>76c4$jk=uZ>U%lra{>V@B4DIn8b<5r1PxJDZ-5AlcJu'
    'p$NTDoLMnBqy2LGZu2j3x!?k*t`vjCbsP~GCIqpR-NTGWO@vmymk7HGQPs2b5KtU3vmzJGf4LjyZ(abKL4#VQGyxX;GV9j|vAPj@'
    '(o!^9Kr1S_>l}y4j|Z9~t@`#?jh>lF<Ch4O&Y-$1;7>f6Ia<$h=FRFtf?$ItX%}inB~LLMi8-+F{^Qu^+-QGzcs>q-86xa<Y2U4H'
    'I9jYwHH-7nD(=dX6%P=>Id_A_IXqyUT8<E~;IEoge%TKdtz`(Xh){#xWq8{4gz9aGgv6rdOS|@9iuPWjws4Wt9{q;$Jt)b!&GG4O'
    '-9H~d{O|-mUJHbHLVX}nTM7wtUCGq2AtP;f)IVBmRa24O02;n8&PYguXTbzpyy)p1vp(J3ub0LFEaKv@TZ$bV1lL8jdKG~%t09}h'
    'lJrPA8)nK_j<h=HX+7ZozVR;@ALBXpH_n}GVt5R-;PQAkv=De@76ewdB78HkC6%coQWz#Y5NWo--^6#gR^9tfo-pul?JpvOBiPOw'
    'fzphoiA+#kWw@yXiJl>(DQwAYsFpi6i(vb^VYRW|n4z!jb@~Td1nd$C=CiXkGcKr~_NM3&j1N(VXAwqcSt`OKs7Awz&drbguJIQ;'
    'M_^BcB#fSb=RB}VaKgenYp~HeFbIP-fj1i@7If2<2;oHw6xU7t)~+l^o4`ukxEn9~8+`C!5piQ;%*Z+v#YksZ%Wl3F_K%4Wj3x{m'
    'TBPg+h|o$<w*mj$Z`(gngg2AE8pg2j)!?AaN$0%;CLtpWToDNn*{skC-9hAbg+v#Lb5>{N7nU<0q+8#9y$3WAF))6Yp~N0GlSW@w'
    '8&Zg51y)QPt=LCG$K-+sZ!J6B;gjjI^+!p;4|9!&`KmP$qWC{F3cIMdrSHdvpg~ikR6CAD0440LJb~n>!*=7dHpd7et=jkPpR)O0'
    '1WRf<1_s6#%jI>}&T_yn5%P24nvAGdL>3Ok?4{l+R13YU%?kqkx8}d4ARbUQe8yl49$$!MkU;zvjuDU;v|&;3Elspr8akLq6xl9?'
    'U<{fND8E?MefRkJukBGe4#!dO*=i6u+eJHUOM+l51y{w2w70?hHm7ZZW_-cWt1@QdvAyIZkbt&t?SCVDZ|w%sE6F~`;hBoVU`xeL'
    '+6o>G*Dbue7($=UY&R+Z@d6r8?+FNVeCt7*oR1Ab@yq(~*0<_$<fkzg>=Rb81LQ{Aa$uPb*kCn86-cK)L|4wrhZrbq_(K`-s*lI7'
    'U!Gs$bRRt`y16z?f(c~nbgbNHTonHBqqwn4f)*NxP~95LJ~nHJ4zt~C`n-`)7IM=Usd@M<{JvBJYiY{m@eQCs#aZpEgt^*+m!YM{'
    'Rtl5$zWYVfU&dQ^a?W51+F+Us%Nf4f8isSuLgFD=9^$Kgh7H#&C<TJp5OZn1G5t2ZZTjMz?%i(IK+f}NggKLRMq|(j?bu&2tgY*Q'
    'deD+!fL4l{@0`?gO(5zX7t^CtuT!WcIDlXgyFh}+1VwR1J_A7{3IbMEaVw5|?0}+u*I+5ML1KuC{sL((_s47`ZdY_n347bLiGm3&'
    'Qt%_#oU01iFaU^ma*Y{-&MU1MI!v#&UN-vW%iaA?FJ}>W`<#c*TZk33)<I_SkuD9Xbx^_VV-dQcUgs_=xXBU}$jz+Xd~5eo$DEH)'
    'fYJ`5_hu^zh*^%Hp*i-(v91jF?ZtF-NMMq(SXO|T>bM1&<I3%}&jfMIj@Z`L!~#`DgsBak7fq<6fxK-%#fOlr-46B-AM^MVDzQiJ'
    '+l5<xX+OQTx)3`ai8Durx#eLjmIq#dO?(~E&xgGxG1+LJwkv@J4H?lEORD6;?wH~apVs{86~X76p%RP1Qf!XNtiS_OHKhspUU1{y'
    'k&jSg08-L##_ceP&R-X(;ziT)l)G2abtYsVUkKTm{*Ppa!o$|wr{JfOAEQp?u}IXVpA1Etdyc>0%b?cF)u!zj1G4{4cb6J6DR+}O'
    'wK`Q2DFcr&pj@ToP<xH31mT%ISHR)WWKG&z#erkFBzxE0yu!`L{*`HbK5tGb6T-}emm?&JP<Rx5BDP`S%`4P3W!j3AS%7<tiMsL2'
    'LvU&d`FHyJGCp1$xStiWrlleqZ4uF#(*1C4JXo7=jWDG?R^QboXeO+Xs8fS>IwOww{oWoQzTVG|j}QIs{zVEl9S18T2Tc!WfJ<s`'
    'gg6Z6^p!wK^pOz(u(SG5hfht%g<&xK-!TuS@$=n%`}A@Bf|;BLmPXWuMO{G~2y0|$4k!ZE(XRUP0LvDwXvt;xMNyU}!L9)b2%O7h'
    'JMS!<@~8ggAacD|0;K~4LDS;^ri(~*_;+?KKp0>pFfdptluN14T0n%lt-i1KZNE8V124e*0BU-(;#eD(DaWyO;y)c;v=xP_vDLwx'
    'm*NspB#eoC?<>4-{^|K~wa+iyKd;TirnnFN?|}XRol@5JsL&~GU!rg)zJi>b6Pb&qRPG_j*~|NxImLwS<Mw+HXQrEwDA<WTwti#i'
    '!6*|&C+fq(PlI7@EJUdz*vE_zraIm<d%hTQMp^4%f@n?n*-#!floHSeUjyWsKAcvA1&$yZu^_J8W@`h9G*(XA-E8^{vX})55ye2*'
    'Mvzuo0I7W^?4xv0Kb}QkQWAsMvw&l0r?^)_VZ*n-HGSCohr{0A#b9FWkxOklw76h{_?ddH00=Q%dFBuzaoWHL?E(DK)q}Z1Z_jVN'
    'D33!&KX1tdMs8g2sNXt(J{W>mzOZM8s)6+4uwW#*4c&roFNPNQoUyaDLd5s&KfVMwP_M$o2V@f5EASixJ83Pa4)tFdeuaCP+Te(r'
    'FlFtO7Un<kuuyNceAc;8DR_5Jy#%>Mo}Q)c%b4Poz8moZ<v~U`fI&;PLUhec3j?hD&qd4Y@eWdZcmL(<X?FoahCW|j+bBd_n1sU?'
    'ErGaW?+7{T2y9V&%1p$s1^EDX=H3!W>IH;8Jxg|~P36>^sQU#>94suY3_(rRD5n|TivFtr7(9YFS3BxO5>XpB$5#DCw0S|R4+mPk'
    '=WEagCBMnKp~w!&4LHUQu7HMEB%Fu&wc30FT$(mckfKqSyUf1S6R%ev-Wto1BZ`l&jnJ_XbtPgnl{al%lVsjj9d+b0dO8Iltpdoa'
    '4vPWY>fnWmn_8F!W2f@swZ#fWF%fqeqw&pACzC^P1A)YmppHaIrSupH_<5`4Gqq@7t}q)gjBR6)M0;qnnc9ELb?;=2vLg%xjJTqc'
    'qmVXnvPDRIxNiB&9h~{@^LqSn_wYiDI#i_QWFV8oh?bZQ!hHr?u}dEk%C~rYhM<VoHtoXeY+}|8>%Fwcql?}iKb#Yh&+UufrehXL'
    'JGOJRBdU}+92K^`d|mj?>V%D6XK>JTugfFw>vlSayKet21_Yw%1otdJAe)E4o2D#Q)(p`LEeoRMaU!EpdccGO`(Uq`)t&A}`;Y7R'
    '{=563J$nZ0d^AAKQqFaTBP0*`^kwbM2p9=V(vNHwC_JvE11M2JT&(q*?T?4Ymy{v2P|%jJ&an{>U?5@|K2;$=s0~6(zz^`_frOl4'
    'BAqOF)*>KDEW2Lf6Qz3RU2Pc*5P*mHgEUGTXjUpeX=~LDq*6230HRk;96*k(w54e6(uVm}FR%CMl>PMUOD9MOB()#_`8aU@37OeI'
    '80Js(P;!=NcSq#NtaZ$-oLIoGgU{jGl-}Ml`j_JbP)9Bu=7e(%Ovft+opsr6gtn9srLEGjB7)oNm|DB;&O1qia=G*Uri1f|(<Rd}'
    'I@JaA7z3@a<awDHhrz~LvR#=i5Pjl1{tUJPc?oeGJdWear6#-V=nNN#d@u5eMOy4pI~dvJfquvIwKrn)pE|XX!fIPbC<qlIf}C=H'
    'XB6L(exzZLFV+V6s&a%%R(dJ_7KuB(j{NynSmv6JpV$n~Styb|?Ye6Gbw}?d+4kfVSSM3#O;y?w8VTE6v&0fc-4^iKaEPI!9JGjs'
    '@HCLB=~^+Xk7&3y+N-0#i-pjg<LbdXZ2>{_l_Y7jrXYtSK*XS|5xcO3KH=07caW6|fkBxsbKTK-i|h{PIIhaR5S1NKmO73|A!S_>'
    'idHb%@P|MQ3d*2@lNbDi=wWm&i*CRQWehESr<=EvwwP*zm5!w}b5SB@!)4)m)hToK+D+s8t(2)>onVm|11kv>yX#5YP|(%C?!B%M'
    '7Zh#Awm<_-$NbJ31Y9;9IpxEGd;s%-=p6{2th%4JblA1htPtAQgSqVIZC0_<DFeYCAjxIuG$ddM1S05kMdXyO<EJpR^e`mxVEjKI'
    'P>MxY`QPj4?$`C{HSN(Er~xQB4FW6y=}rmvN^I5P8mohUj2vvz5$4=FbURq&Xss6iy92rmB~UKt26{~Q7D`zVZY>d1&!>t8)mA2^'
    'Z7S0g6ATDqZjy&c!k>u2-|y$_`GrqhVH&T!=RHzVb}6bBwT2L*y$phE{g@B$2%pyAu)2(84^{Fz9lUHNdl)fNX<GP;NmGdu1(M^m'
    '-=$-5-N9s@fZquy8jzyJc5Lwh^w+p`aa4Y~IDHj*EmK4gZCm+L*l%F9v-W`@v=}cO8<5~@fPGVTGO55Xh}X!xS}#uuZ{Mc7z<~ji'
    'GKwMIK*#{k0g9FYC<H5lixw?o8YG@vRp)U<+2PJK?RmXhnj1F|PtaT<k-oz~Yz59B#YD@9!UW>_bh@l!wC9OdAIZD65W$Qjg_^Os'
    'c}-T{cXKwh05y+HmD4T@F+HECV$6N7g_eXCp*&JjMg<=bl{SqXcHzw~*HrXdH|RVimcLj-K!h&<pU*2>sY(j_1!ld`dH6@Ox_>x<'
    'auMwASDL^=+Qwq2?*QlLc0V8XenFYoa`eqx3-dB%MMAkk{emv`IRX1PkuRdtNji16#BWCf(N<Q#wexE?_bSFH^BAB7%46!s+IPZB'
    ';Ah1jhCL8zyJ)F*^@_zV79W6R<A%A8Wa{860p`M}Od+6)g7z7+)bs%{y16|jJ^@eCmW|IyCq)&sDatM@>Ax^&bM20IzdSy@b&v&>'
    'v$#Xt2!x;%VXPD}Fn5`(X16dGh`k&ZI=Trd1Wx8n`3=p!i}XhaZ^&sSbVH(s^4L-a!imGIV(3Q#C2NB`u&k6}-3QahQsMR5c52$6'
    'zV6`V(&NcU0oKKr>%*Ng5(!>Pnsy8)IyBgT<OOWs`jj`Y4m*k3dvXO%*{@a2`EW<`o~^R?R@Rm5?!1SiKsa^y>qObGNY-OUt4-_U'
    'ct=;mloX@gkX^4S`~5GUkHg+C?eWESbi5aRCLCdLt~v-Pv7-T@C~NQ+yWd1&iyiS>aQnJp!sEF7H{HHo*`tSl`?|h<%UYC;bO%>6'
    '9z(J4>#6&9I@gC&;SQd8aUIPLWl%Z{G+K@@^xNSY`Yv|CFYMFmJU}V7%fT1YFoV9_k|s<hD<xHjnmQoR{$&u2D-b^x%jwe8HR!$H'
    '#t%C6YDfTRJ0Gn*_o4GGlrmP;cSWd9ObZSaByE^U%xXbSVBl!E-|67&0He$?l}9z;1-?7lCBQ+|>Q>@}aTEPxlqH@SU~i^NCeF>D'
    'v8ZbVdV8hwPz2gUVenO$?Sry`%W)<X7W5WuhG^549Z@IeXepQpj9!~5U6*%nckr4m4xOAs*F~{S-E{L}z0KmS$rGgE9W)n|!CS0q'
    '&Op>1(QhizqI~D;PuqrY{V|B0UROHX+E^b_CObQZDl?$@b@xm6a|vqTXvAHWV#}`uUFNxNdtB{y>{v?1L$f$0N+Y3v{Ps$w>hi4y'
    '7j+m5bHKVVb5P)}%@+Jphm-Hye+iK~+V)xOi)f`RbI5&nx|^eP-@RZg%8kR(d~`aTh}}W{jEI2=*N~%z&jAG&m-dXhGBhg;5wahm'
    'xQa7Y_)93C%IHKB_`X1fg6IY-itZa<yOfS;t^$fD;sxa&HjNzqv*$3nh^U+jC3^2^Sp`hCnTlJKLzp4|M4aBK$Lq|yGxDIZw0nZq'
    'MrUOu3pJKlTCyVdq`!62>5-~Mz8zuB2?sD6-M`&+C+87dSUj{oqip$N<R)&ubQ+>OB3D9hIdmhPfl!P{u?Bx-<#WK51)`9m?{x5H'
    'Ctmk04SEZI4NH|k4BVs&6sjHArBMomsYd(U5qr@AE3s1hh|2f9_NtdY-Xta{1!M4id%J)nAjG44(%2O=CQg;6OcUK7A52SE);^d`'
    'FlajejNhB6vyl?BHk@3Eam1L_VJ2NH6u4gr&N7w91qH*aAcrdCF{OT?&!}OX_dAWBH|3aZ%ks*tz?U-lOeL{7<gJ`}RHdxXqFsM+'
    '9&Pjy+E%O<dhf1b`9<`ecW&Nzaj3d+Y_t_QcRMa*MT}T!QHa7!%mLI~B*sJ)fLPkNgN8deF{oXx0s5t@V+-(Xu&5dk&A|y*)@{}d'
    'A1YQUHHAiCsz#ae)1yj)%ECYah<XFO<0F>4=Av)bn7BUo)c$<$Oz;4I4PI?=-X`znPnjvKK^{)1(53vTGaZxy<GSXE7l(L9RTWlP'
    '(j$l}Rp<@)v2>UZ6^9uzS8Kz#hLTg_RDp&y37y60Hf??v9uIPODz@>>+n_T+X<{t0u7Rishy@#<a(idiCatPt*RFCl1ZN5NzEn63'
    'NoPjA7F0(cpYHY=zl~SOm>$1E&V-b8S1ozN7*5;s8SHQ&OY-ah?v(&1(kUF#ArO#`<n&v8V6ks4DMQzLQ}#5*(N}~QGDE&8!3dS6'
    '3$%nIj30rRQ>{b|m5Q<Omh5A`bZNE!as+mAH{1bTYx^F)B8O8=uu`HUDCj_cI6Uz|<=XI;fRyvbn+f2dt08sGeW&p=)gttcnqc?~'
    'e@gHP8gp>*Xo$numWNs>ZdPzLc*v6Rz-_QlGAP=9+xTf!L5G%Gon99ijqdb#g>6QQp2aXzW1$!J4&Nm*BfD0UB#X$wn&eiW?)qbU'
    '{O!l<+Z<;(eoB%b+At@)=w#POwCb!&*SE%60s4sw=tT+-=POC2m(a+&3QKgS@^`v9tANv`k=eH{ayuq~|JM-OUX?fkq<r!P+I`n0'
    '>N@hQPW!&fdht=Y`?{Wbvm4zdz8p&&%1<sw849Q^k<8IPrl@Qb0$W2Xurw)ELJ+^oAY5cfed{c{+#ZWMQ7+s#4+MkJbz)SQvM7=%'
    'E~!$VHMll%rm9{ED1=AA+P5&=YHQFB{IVYB%kTQo9iE4$HQ!!@A=Y>mkE$ws5mzNlG$eL{bAsVIrsxGm&{brDUqcvFH0>DpIMaM{'
    '#ux?Q@rjjr`ugd77@zm15x6dn8$b+X_1<A8CE6zh%@_bY@(IykZLXuKR0JYn(IFK6=784y*UukMqq@jvu!u-)8fyD;h~X7t&J?u|'
    'Rk^Ino9$3pG~aQs5Ov{k3qE=uKH6J7snXEvIJC8j?uH8oC1y8Ruhju)hj~b;$Ap_AlL^mt)&^1z<`vD=Ry5yh{j~V!MNz&ihTFu$'
    'v{Opt_Z}*ZR)8+~tSbjnvO4ux+UD*>D5<-IzM?(9+sXL~^0}LU(17ylI<#$YN205)h3ObU2Z}})@OMpC`xjLwJG$qlf-?m$STlXM'
    'n@<l9fBE|5JYg;4pbgkYHLC_%)BgAZc3?euWZh>DA%KRhnB=|gZ4YJh3`iE%{oPJZg(5%x_3`fcoTn3AQ7MQ8O1qXYfvF7^CaZ~#'
    '<B!B4uj^Q$YEKwm2$h9$>2@V+Rd03mrH#K32R|MgOJ@TEVg@nE7Zuw&?!RTo6Y3&EMI4HBWQjc#Z_AUYOCNJq2IxZV2POP&H>za%'
    'eE0m@`N|KIRH8C&gKA-<gixuv;>9$Y3Y#;k{^FMo<yAL<pq3ya%Q95mME<>=KDT><@6*{mSDw&-)nYIs2UV2lgIGfZ-mH&9%M2wX'
    '5f61^16xR5rRAKWTUy@T>WR4Z@##2P_;^0%JG$yw2i8SrZ%zj@z`rVyqH_q~n@})wh`Ll-5PQ{6<>aL`r%rRq>1ga-S5I`JL0uxK'
    '8zb+&boXnSV07sar0fdH9$$qAIj=1t-EYaJIb9xDCR=D8f#aqzymYhg)~A=Nct(ewJ#P~uf@%)0`iC?+YM#0m(h@jlBa?~=Z2l%I'
    '1+@~!H)46UTm5`}-bEEgUhm;S^4r8pQ%M0@r6bslQl2W|rL$W!TSL(AF}JRmH8i-zXE)<Q*4-S-(Z{h(q5CwS+BvxGu9y!HBU)88'
    'tPtH)wg-a~Y0>OJKvXApE7Px|@0mm_5}MKQ=kIoP>f}5iKHh35E9;v7*2!^@i2-DW*rF`vtn*~xhw%jEK&U=JFRNFT|M-3{U-{|l'
    '{ibb3WJ*-`X7SbNwy}xZx-;LVvg|xl<UvtX9r7Gi+>Lgvf=w!TcoTbm-A^BXS`VL>c=6E-VrS@{C1kAj<4%uiTR>{6?tpD2Q$c1M'
    'OW1Ui0QiQKgQ=KjBs^V)wtZ^<*tkCNCag-=qd<GGy;xlc37T(XKvZA`ro_aIl934k@qAoqY|8WPJ*V-$?YG}Ph>^q$S73+){8)hd'
    '42mYGN6686h-U0j8#HmK2nj6Bi?hO^Gb{MMeHd#$e|!x&=!maX?M*ZYE9x*oG=px27abJfAPx;OQ6buMX6k{jY((42jmA|N`5acD'
    '1;~EgR^BRVxsM&fDeZ>>*|S3&mr|%eUeroa`j4(RMWaLMUf;KUf~xbEPYVH^%sBJ}@Yd#WSH<R*u*4AI_|@x{2I30RiX=x%D8pix'
    '3^luqjAy+4@gjiis-l_@k%G23@=62Z45$am9mBDzkIHN_=jh}d=eF9;R82@pyIZZljT??p6JvD*U(<0DEp@&Wd1IT7Kv1qkM{TqX'
    ')`NMR9oHj{wW1nq?M4T0!$liPYT5-+Gj)$_uU@p@(sb1r5i2?r7{(S#WUrj?rDA<5^GJZa^xvoF`Qvf*@%-to>lT8pG%VF(vntoY'
    'LTnXZg-aWwt7TIOItd^0wQkk&go%3Xo!G0EPa5InQl&vB8x@>P9=1-CSp}55A1M1dP?*|<g+VCZf@eCu&B`=_oiL!AO}|kF6>KCx'
    'uH+EJS(J+C<|SV@U#bjKsA1X=`K~*gNgD~WSnac8T<cvAFVmfi+xFNK=%yYOOm&c=ifKu8^oTYP#>uw^<Ru7hY9z=4c~CaD+;zLx'
    'il*z-VL-U78#)0ss(|DxKMRD<s$BM|;(#h86IEF%cLZGrJKf+j!j1M{F0u~IBhGOYCWoI*RU{j#VW`XH0}#<(=W!)3u$WN4Y*-I$'
    'l9iwNs^z0L%G1}+XVOx%fns!MtgG$Nggjm2pN&(Ix>BRADSMxaN+saI2`sg>Adq77*9)q9{AX}M^=GL9Z?y%00Yu$+Zl(@N6hLtH'
    '*mS#!9*DEZJZBE->EN98dL7St=%qYBXZnCvw6C@yi;5E=ca_ymYg;8_yK8`%E(xpzC#tbygsNub+O_MP8U1-3A-fTN;B@AF<W+Rl'
    'CN(-z4K739A)!Q8T}&a^n&XNl(5T&rNMN~Y`<v?V#Fo|y5?*IJ`~$E_Q6Z|<ZiGt%kN~A>e2&?2Q#}I66_aKh61m@K_>#E8HWKY_'
    '7K@2=rR$`;0#}IJV~>77HA?iwvvi0EH+SYQ6X8#Z{OziFWZ`<ed*OlBs+u4qMO$C0_(i10hO>bh5M7z$4i8YuHs}SI0W`$x3Frph'
    'n!RfK`UbK%Fq*FcSP($~JF12eGe1DWKBW$g;s@eJ1yNOf8NNKFK@e1LHUreWNX*&i35Vsl@_H2bu`8*b6&h+mFrwnjh~0%vd{FwD'
    'Zt~H;?uF*A)SVj*Us6hdbYpA{LEpkOIYx={s(mUZ0~yE^5VgxuHbq;BC{JRuQDv?1R{Om+f5E(vCQz0LfDnh3Fk2vaQ;Ern%URbZ'
    'wKJuAvlutp0?Dg8Z3R(=>0G;}O6I*rx9N3deaEW%dE4!A7^h$82By2`p-gL4%!T!v&WaMlo2b@N&$zw~5eK3Fv446PfBAU#aE?J+'
    '|1O!xSC_8Sn}qXAf?E~9Z0JkWgtn@p?pPx!vbOLEFS<0C*NqOoX`vU@P?a--n|E!V8!XwW0+kOi5ADz*m{p_-bB8KsW$Po$b!_f?'
    't?gD9m(3?7+LoELo41oH3NtB1^)u#j(<%9d;63=E3KeJMBcv%O=1~=a$M|mZZ%VWPrb=5K32Bq7Bfjh537slLYx#WdqRPl_ry9OW'
    '9_({#7zuMu=19u_yo535_d$M8-A`3VFKB0#r!6=SUT>Et7(hk=<)*_|pLaM4*1-={cn>qKN;dyNRSqBTzC52cyHv2|!?Q@s)6Yka'
    '7R!dz+XXmHW?1R7ptC?`mf*Hr_XQ18o2u$&UCE0Yl}@s4KZ>SYxBgLCpSte&r!T(=43Yu-lo+duXM_W7l%URHQAzea`jLifBjMkV'
    'rs~L;aEC}i;Ln!%(!)hU)5mkh(MLUAf-pF`(h=`IP}phj%*_(2SA~(__2&dVa4Lz9kWs;0-8FFbs869v`MzCrrRsX;+K;E&W5;Z1'
    'Clk)z`#e<5QD1OxF$z2K0v+R4y+Cw^O6OY~dQaC?m~i{<*JTIi`W#0ddi(V0)IOFrLeI{rv_XO+0BB(b)Ogk=4Q}R`6r3+hF(D;D'
    'B<-Q8_#Of$eW!gb_tU9|TH3ajFGLn7!;5Bh7OPT{x=*TlNL_dKQME(a7hq=&PPHu{TJgBdebs|14SYE6Kpq`Pe#K&}l7tGjRHf`0'
    'kac*Na@s5ty;S}pRb^g)7T9et;2-}e-s(WBaB956xcGRYbkG?~HV}*`!1N8PEUkL0vZT-kg1L(7BDGROBpQO-F5!LSuQ|S-iD9Qs'
    'c1w2ZUzikCiE<ycnvD(wjn1=Gz8wNPRK98&{6M9*gUZ`uNW-}AcXF`~!h~`trsH0jPA+ik0jTQgB!)vgJnjbR6y6+nv6}98Bo7dr'
    '?(W>~<ZMXpIPV&3fXr@rUm!KLYxA@_5i6@pCJi${dTiBB?D)qf=%6L$aVT=t{Ji_+PM4!EXDYG~#dSzj2JMORKnCleT^R{;T`Nb?'
    '!WqzU-l(Ra)w(0QbcH9}7{qHY7gGg8Cdv?Ya-}<9FsP8(a=<BC*_ph&%0>4SvRV9X7L|2T*(ti!9B=gUaufdO<bV#<?y<`>)v(Ys'
    'Or<=ajnQap6ZE(DEx|3IS@0$px+)DhgUm_>$0&c)$uSb$?KX;4$p@A6vGOkq)AHKd!P=nYRkf*TA3>0+5}H-$vY>fmyV1#IuId>P'
    '&rpcuY(!u0m4-1GMpxz2rq>YAn{WYJ+;R9+kGmlo0}F@1*Dq!J`(1r`T)*6{zn=X?H;;!YN+^!X%o-CMR+gGBf~bfEt_{Bt+uKTJ'
    'S9Vw|8ajVtZ`j(~uC#S>jEOZLDtxA*5*s<ML{IFDc(t_KvEZ|^>Ft6;VwI}Pz}Z)w{#l5l|NV|G)=Aa->nK1C;-FwkXw(&seI;uP'
    ')EQ)l6UOX}Ua_c{M;xLIXj)w!f8WvTW%M?lugqI}YeNUqnaN0e`BuGeW(rZb{eo&*RgZu<!#}N3B8<{n>Oy4b9Or#!-_p_E3`)qQ'
    'jdG`3rb;GKoq<uH-)Kt^uY=Rs=-x%uqcU|GQR;D|4$gjKP?uS07adLGoN^E#%@DaYEKD55XbHLiwC*<RbrF@Ca{MO}OzD&=^HX)B'
    '?$|B8*^w;nO-HKvq_VyWVjU@@szVm9stKKizEqa8=_)-4LnYoRc~3<|h@mP3ccUYvNxcSR<@DNwz>HoYHi#f<#+wmm&bB%o?pKwb'
    'RfP_(3~W2Pu2GCM=Z#>j<}bb<g{k5-t};VR{2ZW9f%Qf(rmOs=S62C<q@jmI?A}mj2BuA{iQxvYDXHnA14tLvRf|%u;h9K;siN3K'
    'Q4>_@1oXtZ_3jSXtjqdDPqZ~?FjQ{*23@&IYU2NX{tQ<=g|sOCc%;JX)seoGnYpJ@En?NCj|f?l4pA1NkHntZiqqBos1uw&?(HJ<'
    '*v3B_xVuyN9o3#xjjpWg1*0C~1a_o1E^=VPM8HZGdqRp#)z|sM&dw$Vzz-D`059PbR@sBe!yKW1P`#*>VB@2<EmUMKC`xtKhcF5w'
    'kGE{#+|8vO&xX7x*>wW7U0FG`P_gCQZn6NQR5M?beq=+l6B+^{5NwSqlH6c5-|q8X&RLm5cVU8(puHbCYR?>07}}>auqruCRIwzR'
    'JUXW9=@M9aQ$_HyZw%(m<=$@tDgoroMj@>$Dby*kf7+#-u!;cUe*hkBanHGxLT`@q)hbJ5#%~Ph@$1>hiq2oqN^Lo?5~7_{>IPcY'
    'RI&pq*;-f=m6x}&0abq%d=nlaoBENrc-8dz0`A@YPjBpt@PhDyrcI=l6vP}QDY30phwh)KD_v5C+2HcY*;oh}L3$DOxNZ#LqVc5C'
    '!i~>LN%=5aPv-;(;3{jt+m;xtNvh9B<Wcsmp4gd)3lBL9^M+quI(@V%8ArnwaOnmAN=$S|>r3uKH(CG{RM}rCW4c~hbb^U>^|sTE'
    'D0w^>@C_C>Gu}W$ak98l(jj<pCFyir$yGs7dg^5W8+3^;D<xdJNme^GH&FLzUl$)=`+#<Z1}xfWkxjZ@H&Q4`$pX_g-FZ~Cbsdq='
    'yB?$5PET5O6-(4){!SmVq=QW)Jz<ceYIuaA=FvVz=|~%X;WE6hAypYdCRS~2-2oh7>h7|tmE903uYFvSSDTK~0lFoWf=7*HaDAw<'
    'M9yvK(zWs@3xDrp%)3CBRNGvK$a}>bOMU9)lnnSfVHG3~K?=<&B~p6>iT@8Egb8c+U}iLhB9!8b$aC~V8)iUuGWoj`cD^lo5!@%_'
    'T67q8t=9;2y?g522t-9xN&Bi>z-I2Lv{mMKZYdWtr*?I#`EEzA8ZS1d%cn&dH8`~Dd|6#b1VoGq{m-t0yivN&i-ok%|Ax$CQtht&'
    '2C^SL+|XcS<mn(C1yZ`1{fPOfNZoGQRMoq2s^Qz$J`(m0O&*jR*pn*JuRrMNj3XfGLM>?9Pml973BSCsX+<gGF2<x?CSXxpc1#lX'
    'TlGwWviisO=Iiy|<*NnwbkuW4)*Xe#RFR<qT1Dxxy3&wUl2KPXT%3bozk*RE5j`@~FrM!j+G|IbdkA=D-!?`o2xn1dQ=SE;mD{W~'
    '>4B4pg-mo(&@)UMj%T382vNspeWxpN<k#WwWhguFO0V=`SD=T=VU*lMP~|_yp=8bMv|;243KIMQ(d1g*SpDzxapZ8GWuMZUpbWZQ'
    'tK#4^qEv#QA~q@6t*0pRQ5tTBFsF_uw6m|G^$Y!XE55&Wb2(vv2A{`#9reLfRVpZ%pRwuThhA0JG2m2Lp)%=_1Hi)Sq)fHAzGno-'
    'eV=a-aHLCDq7gBqU{=9qh&|Dpxzl5E#KM^L3SeYOP?%8#>~({*F`@l?25`Dm^a7gb*P>!ux?=z=D$Rqyr7ABjz^heDLy4BU$cxTJ'
    '(m<4Q(&3-kzS|oj;#((|j0lIX6F;#HWPv2Yl(*8}aGP=@NJ%Gw0RT8*5g|l0-6?1v54Q5X7;}E7>{5Iwx2JE_$JPyK$g%QL#_1YL'
    '&P(;3XG<zE=MXKC0I8P~RhWTJ{SD4~dR+%T^tvzx*l$ODzNK!U4qGMMv)&^vD#vMatE!k;mBkAh2UYz9moPSj`uA4<itB@b9iiA-'
    '_EYI%1kkA>zk69$*sHY6vHOX~%%xg(L_IK8NS3N`^E<t~<mP|F85Ofv0pW!PS0)l#xhdTrYe;xcjm7u9wLgyrYR7@4ge0s0m{~VO'
    '%bR{Ky+-dY=;~p%j0WMa>(r5tho|U{6QVAvdR=h6C?6}zIaw#YF$zb#vAcBibiu<^&mej28qiMBLoS36<q&Icx+@7%d8X)de&CaK'
    '`No_<yViOVa()kFK+KEf$JN{hU(CX$^N~0xA&g@6xc^v6;3{UfeUz)l9QACAZY-)k(u&`+<)f3!V5VeUl@-x_JiXkZQ(wYw(^-RZ'
    'CUwankD}+URYXG93RRZZ^h)UH-$SxfzW%q-bmtM(N=ZFRZ+8eyg}$RrRnNV(39vK+`&8BkOQlzI5_~fSyw!czn9to@j7KlEs5Bm;'
    'Qn=68Lj!{B%_9_a=R;|RaKV;ra=HaEb)h0A6(Fs*i2kXgZ$0RsVQn|CTvamd`2A1~mEd(U35(u(vn7bC5txy!x(Um===}m+Z}?6R'
    '-|h*VV@x$tb9xdk_!V(MRt6ZYIe1;9fwVTr;cx}<JPQIJel?Os@&OVt+}Pmx*3Xxp+tcOpWR_iZKNlk3s7g8HtPPv+2mliqrz)jr'
    'jiK79UI(VCq>ZyU)sfoY!?Vl2F84EGu;}~c!I`ddJecgZDzn$&0;V0MJ<zjm$Bg-#rm{xLk+E)v(-qw7-tM37e$r;og_lB8>K3+O'
    'y21f;*hbQ0AX&#NS^6NUD(^IsHjEOL-iYKaY6tRGV0-E1GUO2Rr{2;S@yHUwjE+ZRAh@BZq>--2>G?~GJcD3#^db6c=<Q0p>-{Qy'
    'JoCVh=UX)&+x&cYsxNw&g{)4uSoG|0ugp#g2n?mBz|W#bb@;6}ey6fElv;=iR~64-RrB4w$AypU^Vd&J=aEAvx2IlaLf-&yUI0hf'
    'B9tBcxgG_!w?We~l}btKs?yQ5CzO!2D$<8uf6sA0ULL|-4GEr^+{k(;$TFtj7)~k*sRE&)cSemRJX;M@McYy9Nzz&+s!w^~zth>v'
    'rt{HNRHmn7cXp~7AjLG|u>-BT?_0TQZ67!OogREK78;*{?uZt#p}jYXkFU4nUl;CbbaAzWML^<_*2E?h2?SbOwo$J!DY?DX5i>Fy'
    '@&g0PdQMX1Vx=A1jnSR=g1*<G5(`v5UFA5N^0G!np>L;0f*OG-#3JphXL1|h)U@piA?lOxTfz-U|0rjE?d`%!&}mJJuk_Oa80j*s'
    'XYHI4_nWrA;v%ewW$Q7!UUas%i*mYAknWPvpR#99kEEXgFknzyiA<37l^{I|Y<nqPlL(^xS>0|-x;&+4qk0=d&$_^U^^}Xf9LGzd'
    '_I*<^-H)(_`}KJCC*3UUV;AjU)fRRu1VOC0Os`9!OJy@+)_Vp`v|c6Od#yuf(ZH3z(aX79!i!cY%92qL(1JN<w2e~1RpyGh3d9|o'
    's#|(D7{04V_^>(LRkt>l3VdF4@bvuK%b7K7LaFx90}n_t!OC0hLB(ww^wZmMB(V`zA@&)QPS!cEbO#3+dh^)_RKHY9e!)&X7y}d{'
    '00Z+;ld`=Ul*2*&nd77fUV(?Dx=&k)wMLIC_f5$5Z??#f)=w`yzMPX<8C=xe4&78jb}+jT9pFo^K+JAbbzHh5z~l}OZ9vZ=$Q868'
    'Z6EmiWBWWIVduJU$|Cr*j;+h{(f+w`k)9#8N{ZP^8_#e8J+1;7LB$U}ldQYfNsLjc@=XcswX0~(K;6%I-P>^*^Qpb>$hr<&14+zr'
    'CRbC?<!<!Lj9F>GE5p)297B9@Lz%XEKcQK4s-D97Hmo<<79Z~JH9VC#IKR-X``cg`WKCCklAhfme8S26Ald{6eAHbAY~C~-c{2_j'
    'aqHzpy{y*X^>dYcc~}?mu&s~<^y0^TH!$5npk~8=r>-jw6^0nb?o?Phc$__QR`zj`_Pd>&-|IWOhF6tpz8N#(gVTYA(e$P#f>lrr'
    'dJ$A*+!8^np5e*;D9t_Va<cau-Ml0pouC($1oIl23*AuIT~GZu4*{8bZasjaN*|c>G+qAQLRq<}FlA-=?Tz*y9v>h6Dx~WFy2cAq'
    'DUYT)6$l_k>B(cd)O`|d^bb9#UX|yav1FZWI31`*oC<dhOE=N~xSx-$zuc79qdP)fuji%->-dRofEnvm(9guu_#3N-8Cja3JM>DS'
    '(GxLxg3rbO$<B^}S?IVjNr_Jj&gr(UV;2=3hms;s^(<jGy2`sOIxaSR#477*9r*^g7U;UKyO+Wsc*M|7fH6AVgPNs<W=G9|$PhEI'
    'peAkf@8OYgPBq7~E`>~0xjVf_ecjhZZtiI~M02P5R89q66B4R;cu~^3#7afW+g35q?b?VAg$kTPI}u--Kz!^$-|FIYQ|1)2bm=&c'
    'HmfpmKt#RSn1N1=LK_W7om@s2b?Z-$C~T$esEUGx=g;>j@aFl|rx)x;ebiM|pRQ&-6GYTfDIAY6MFvT5Q6XE%QMW3=gBOjKb)IGg'
    't?xTI9`$+&Sa?m<gRx5$J)@mi+0cQ^vA<DO3kD^ky5mMQHB%X?J7nN!B`NvU-Dv*mw&Zyfaj5F+RxTqdsv4Cr82mqIU@LlE(&|<E'
    '0&(#bwyvUhUC(&$p|!u&%^T)?UUNu~M_Y(ID8mQLAE5#QRsw#YL{$k`4;}IwdhD_C59U#oKTdbll>7Z|4sSV%hUk5WVzWx!ZZQO}'
    'OlKTVrRal>8ugG$LKw(N8VG07)+OORf~rFOaZk!FdwEW09<|AIQx4|lq8|Cy@nzDrm}7W)S6!P3Os$@|9v0U@x3O+|Jm`-*dv#1b'
    '-=?Ebz%)YcfX&shIT(M}6Chw)7dzmuM+bAJvd&c$R?laE*YkZ>FPB>1n8WHy<#i3pqx4)Pm959kQr-TIkS1j)st$y*-u14Yfy*Em'
    'AnLjydZU+%mxa%h<|Dj_`Cob<c`ud0fy_8GqE*h|RCR1$=@US$N<l8VyfD1(W7Q+c?05P&3yh=(y(M5*uT$Aet0^_A>+O*Rj7W&$'
    '@7hRBDzQ%R%M#cF7|J)hII0-Fwd$>7Cy+^ZzgY`GSMoaB%sSm{<|vt~OUUq6t5k4BJ8U8A`fRQ@!1Ah_SF6U1O!F;cIsj*kI1PXc'
    'WsSHI=A5C-HUOJZhtMh?eY|u5ig&ALX8*XS3#$&^t6-U4p*l*bHXVJy`_KRgP$(uOCmq$JyF?X>wiMBQ)Ki@9Rv^9Z?A59l4)2;0'
    '%0~7+O+LJuptn)1n|gDv>z!PKL#u%NJ`O*0`&G|usT$DxuHIdtK2}OK@bo%-QW-Yg;!(+hpp0TYlX+a4X)2Vx8sQCHJ4>}Hx0Uq9'
    'oh>(pwEpeu9iFr9Um-5&QhAAbQeF4Ri=HwPx!uTCy+xx30(A6EykU7}RVDJE;v|sxn~`(h{R&zuA-CP#>yGm&xT%s3=mMc>pp9<q'
    '>cR*(u=QwX)FwVORESEz!RWx<sC#0n_PXK?AUHqIea0CTeNOPTG$wv+zycMZa>w1v81;}|aUpMUbO9UTh$$pmCAsab*m-XLtW}ZL'
    'L#a?pv0tJ{wX${V2BEM0T#y85qj$at1<`3F5lBLm+kG6KU$_4LLCI53dP-M`g;_<^JG2OItOgR0tzWAagFZX*w!OHU;~R7Unxp{r'
    'EY$x@Pap5@=lZhlbye+b1YYmBDhEuv+*@~TkhR(ltVS$pgw|C8OQq*k4PTXORb&jWLK59_oo|m>zP_z`-q2X8{-n^{W>jf_dE7g2'
    'Yhl(XDQk46Ot0)tJ<_=+Qm+(6jyl)A(bLUG!_RK2Tl+<&L{)cG35W_tS|Gk4v|_E^rqz>%+6+=}de<vD*kV?-%UhkDo({jv0Ecm8'
    'y&$UeDT4&XT?8oWRCh!rc=a%unO#p_(6*a;EJM}4{jSK0@Ask|!}jSFa~2#|&u3^OmDNUO!D=#EvFI@%<x+;maF3@0^tzH2F7b28'
    '9(!}<&P51LmM2Y^Cc%f*D0;%g>S=PtXQy<8)Kt`z02mdBruOVsk9rg%=V{FiOuKvhxPJY)eSOlt$$7)1H*brQ7FS*CIQz8isHvs8'
    '-Kug``5zTKnJWBapgu*nYXVT}P(U|3Iqj&vl#g?DM+-A#K2-fx(a|i;ThcCYT&fA^U5aK&;Kh?IAa?W%?S}tc7KJ#2azI4ln=@|h'
    'akRW#nXTvr4Lw{=bW_a)UHrA%1lEJ-18swBX?x-Z7+iF5x(R-c)5ZjoB_xmqDrZwmN75GfKnyy`F&G!)gk&HSlw}QUs^C37nSHxq'
    'SZ`}joR%H)b+##HHdRGIm#MIx9w8}pi#r`pxDj=f2Cw~^-jKki=tdkg|2v(WD^Hvj9r=s~7fd==RGe0sIryb&6{0ak1f$9yL9n;T'
    '+0YRsDn3YX_!}DnM;8|}r7A&YvFw4hRi?8=)OA#*USTO?Zd(F@AG5}kz!`!urjE*i287&i5T~Pum(r!D0OpFaS+dGIB_&PiVS}^*'
    '3_J!ZuvA~K_|?n8pdh1D8)~{&8Bn(MMgV(XJ>!&eti#8_EXmbZfp#(ZuyRlet}>zyCB4BIrjB=W^joFtT~#rqP;RlnPwQ9EgpPi>'
    'YcKKADJjdVBCQhs)+%OUqf0e4MU1S|8<!3pGgu(dD_|z@!%|gbb=(O1pRlW!n!;AOiCy*N47xrj*{<MfeJc9{pj4)SuH`x%7iB$>'
    'Y*oAioAWx3{7&Pi**P9FY0R*s9=-sq&n)@h0}hcD$E?+(Ca4aT!*{BKzo6kc*}QH@vQG~`9b51^-Mri@5tUFOFK3t{Rb;VJ_mD~5'
    '-fmUN-%3Y-K*G3O?+pqi*`9#O8S)J%dEe7%!%Vrhx>uZ*3U^9>N7abLi;XIp;E${pJY9F;fJc^0Z`+#;EkO0$u&nb_vqwMYeSJ4o'
    'XAu`GTI8uGE1>2mi)=(<kaa50q|;mV;X`Tql$9bYm+K9qy6od(*0L&X=}1whb9&lpcU893D-9#52&HbpTNRL24It=*Hqy{i(fO22'
    'zJc)XIyw!=2V^o%F?A)d)@|W*;9pKhQi5I{KOV-G|EL^{0okHnIac9P=<6T!^Gfv#sHlXm2~Ey=9(n6Vxxv8&x_(97%uu~7WVllS'
    'v($;yK)Eue%eaA$m+t_-u8!BOePptVFn2@f^;o!Wgkrx(C2n+P)g7UzYB{oiIK9f4W|+VYgnZM<w^?JByt0UBc5ed^t2VAwQpM?w'
    'Gf{QKvE5mXZskNVBCpDntQT?lhWEVf=ylrcTv08cWHaWi^PHs@fAx5YvVb7|Eh?$DN8JMHDkU(Zv3OP&)V%NL{I2okv=yiKAUA3&'
    'sAx5K<yAkx=ol7$$$}s-Y0ay$fb(7N!yV_CSutYWFzVAu(&^s(X=j07ESQ&#N|K8pG2f^+PH;)r^&*V!Z=2&_eJz3`5=}dv`VLg$'
    '?{{&jUX7l2+n}UsSdV$UkUes?ddgc>Dd%p=Y}2K6Bj&8?ra4w<I`OQo8<=_7(d)Vp+MO&^RXQi4t{lL*bdpZrs?Z7#G66JJT^5wT'
    'Qr}dpFgVpezM;rZ-F*Ife$@69kCh9MD_qa(jf$=sg2*x#A}q2UFCD1_MbbMNHm0eq2CNd?@w2&b0|ego^39;<GJ5Y@rG<;v{ttRZ'
    'n{Q|cUEFFa8ECMJMbsz-8Lr$rz3sdXrFerCU-k4lb6w}jMjNkNFKQuxXjspQV$GniSBY*_%RsR?h+hGmwVV?Mvx8kXEc#sZ=Nm|S'
    'J^cww97l3VHs!b%p?8c_FSY4W3!9O(R<y9_HcP9j6y1reh>!11+ZCkg^bEs6To<B<)8-BiL44j`8FPAL^mtH~@LxqbRg(z=Z$;%-'
    '(;tlF<LTJ<OqEq@vsb;4s$$w;{ZQq^F;-G}MAiPWx)i<w7*~S=gr064=rv$E-`Hq;-_xZN>Ae_e8svQGano9lf~QWeo9SYUDx7u8'
    'dR4v2T7=jtd_gE&_*J<T<u3bsdieVIvTed5wd_?h{dnXsr)YIPs+V9p%QCecqYW8l;b7M>z;u^O6GiIgz6GT8BqI1`H(l50tOt;l'
    'xu@dZx{+<8QGVjqvlC7Eh&UD0Bj=8aj(R7~ChgMhd3!t;y<CJ-s~ulG$sBaWm9^Ge#eJN%^5KUqrX<FtO9^<XGVb&eIm3jj+!AJ2'
    'J-u3=9&Xd*gI=ncc9f|GzV(1>B&O?@t2S<(Uckj*AX%<t-G5~f?J2|Hs;9T5;Z7SGk(j?#84e|*617W@tW}U3KIfHg=g^<kh`B+C'
    'GFr;{sSML*fz}(tc~=<j9JsYPqFs2HjKuKq;t0KFulLNm-zx0ao3gqglR7b4%EirNsD{W5S9(_#?nDvofPaFUTbD&aNFALyRVm(j'
    'uSJj8p+8o|%6Eb^LQ$jABu8#4g>r)+sGsX_I_pHO@|AkM&TbXF$Vzn4Xi8TuLb1`=qk2pq3Pw$vX;E8tZrxZJl>~jb|Mc4>$VDj+'
    'y`%{;Bg=<!hC7TfBleJpaKNmT4+0NSjzF?Na<mX`3TVVpey5jHO@x=oZK8u9V9!9$(hD!DK;l*FZhIXF>75|ms&75(m9dFK6^o|@'
    'mD*T0PE@Y@xrnNI{!xX50dM@KAzKlO>o|K<r8_(n2B~)iJ<Ff#R9-TyQm<-ub8G+XMqlRyl$S&HBX4x?y73tVTWij$UP#B8umU~U'
    'gWFa~V!o&EzEuGQF~MiXc58Gm`PM`AONlmypkOueMdmetw4}ES@!3caRbB!MraW>TQV*3Un*gi10d41s80VB3?~+<=N#^6`ab~W%'
    'Gx&CoRoT}aT3vMt49SVdjXnZ{p2f5C1_3!2#CXG}&B4!<e*m|&soB{Ej!I<Kg>GF(P~=IpS&j=`aMNi0QKqO*cf-csbaDZkQ5V=%'
    '4XO*jwoh9RwFIkTpy-)_T4aJiPhD8wsxt<xCS;>nrTN2-UM)<P5B*S@NnpwKA7CUJ6tOdv?CZ1Y62hReO14$jF!u`A2hsS+jY#me'
    'j>vfn5R2@}4XQ<zmIfiqt4!p=6UQ(FODM2XD3A~M)!Gs%dlZY&`*K55y_}r<^!V^nht%lND%=fxmpDL0E#iF~5YDJ75oMZSkBm29'
    'nSrr3+M5bP?}8P3bIL9|Iju|6O=&Q;uEE+m)#<ak0jKAfoZh5_B&duWQAKZmN@q3ao$kW8ev9V5>E!i*%WesT9FKdnM|m1CCB|_)'
    '1Lf&Ln`r|*MIbVe04CF#WwzeJboB=QzwPIO+bq?<V!ph^c%q7K=cq>>d+|%j%BA90z37c{^o<!s%eKTkbap*&>;}H=>KoBjedL`K'
    'Cl|4}I**oBdBO}NqfNbvly%iR(pHxqO)-5P#q3nRBHSQt*ByQHAHQ*&(p1gA=Y!N1CAsMnCeXGk4Z?}_yhWb6Vy2puNCh`i(mQ_t'
    '6MbDyp=&A|0go!GeXq(FGb-uYM&(lUglN=LwJ6X6t)IfP-E9s_h5F_VE&ufM!{hVEarZdB-o0#4!BU8b&FfLkuD9c>TnYr!<qq9k'
    'iY9|dUhl{O4niY6`><Fg#Lx}u@urgtNJvC0<QWW8H9-c73w8!<;<EU^YAp_<r}|Wa5DN?_9<TS?On_wH+K{~N=uN~?naHZbvuO_u'
    'L8Z#|5D}KHj2NSLuNV;aW{>ymwZDpNf!HfK9-4ZiyMs@k&ZXLKFFW{54E~7U`r<KL>>*_kP9;T>%GpB$y55nn$6M|*r$QL?s=}q)'
    'GxZieT=jDnjw*qr+M`1mHM6NSO0w&C1}qU?qwbnkh?`s$^OVd-$_Bk*Mtr%^%`=qh<4<4P<9s@mbdOWdzz=2W4jrDN+x09Uev0Oq'
    '9lk(RAVO@=&+GP#j?`dBLz}Ms76=_(9OWrqrz>GwQFrc3(@Ay)gH)v$GJu;9vOQ)Zb(fva(J*|u>A+_RL^n@VUW)6UOE#VaeXwY<'
    'od+{uL7Nyi4nu5{kU9t_x<*>p8ojti$cacr706&A)4VZTSLcG-!*dg4gr;TPJ73`1akUC#8|8S|$Q`P9b)u7QoE;nDx)h&ky8)yZ'
    '1>(*pk5-T1RNTSNbv)Z!R6yG6w!mD|N}*0@d(m64yV`y_3xzOL(B^l0xC9wD^qfS|tKCVj!zhs!rv&0qZvnHbx`@D1=uY_vdJ8Y~'
    ';~`JwWcnNS`?Y+0sib!bZcF;11-)Nx^qy1mx@=t-(SqIRtvfxok)Vh}=ctZg5D0v#ud!FW!Tnw?C!EETD*$iMUUY*M^N&16Z&ZI1'
    'u9=n5MRYJ>OsCgCRkpp_H3mv*>si|GxBvFsbOx0>N7O?5w@Nf*Ry`19w6{`1P_j`WI;*UV9#+i?dmtymdzo8F6i3m%6Ng1bR;&E$'
    '<AQM3iy5w|Du`Y>1InxRg#(ljp_7yjW0)O0JnC7CTk`xUthesR!$j4d6^0T}RnrC*0U^t)<ikdru5n>Pgn-bX9d+rkr?ly)73Bt-'
    '(w5z~*5O-m!1D&@nqCPq`t`0ets0Eg(P&3|tH6>MISxrT>h<mb%%;O-f>3d_TPyLcKHzCX7?H<HLQR7n2~)XC$<?ByKxRa#But(j'
    'Jy5|h1$gwhYAV3U^lZ@k9uDUEakNjb8HZVyI}pei{@6LTl(J!E501Vi{I?=8@}+kb)p5s_TBCcMDkE|uPQ8|9J`DjWIhA_}q96BF'
    'P_S#l$Dn$;a0DXha-OjRuLjLgv#~~Kn9<QqxG{t`<(bbLF-un-PGwPt?ucVdL|e>gC?Sjpp;9B5DIaXp#QQvClkuShQu@vqjw;G$'
    'Uq}NlP_0$HZh|7+!&O<QI||gIzjh2bc~yb?oggIXc)qHufZ(`cuP^O?Y+qjX{=3z~ItYUVRZPbfE$t;ul(*Gg@u^2$<Y6?3A4j;C'
    '^r@bx!U1n!_-h}h$7xPQp!TqOQxU<SQ`f3zz6>f<500yp$RbcURdCRiv=)gQQ+h?uGUQmw4WV*T6Z!<?Dto6>ca?=yN<0JuCSr9j'
    'zeg;GH7dc4sG@&?u%U`02wx&P)*ZjGxVe5=pB}!bjMc;E&+Yyt2S;hbS+zq|D9ET-p{i9V?`BI7M_Y6)(*-@fy+>8O?CHHZoJPsb'
    'uN~YfUv*ONx&WxB8+r*AQ;Z6gT~cVGBvctdHoNsyQQj?2J@2ZA*@{;Zd;FF{aL0##{qQc4a3AqqC3vi+7?zHq$}Y2RY3dmonCS>m'
    '#e{$x6;dj;1Lx9XWHY~QUm0Dh@^!3<=IH|z;mbv@FUlVFmk_<W-vRUF%e_i5#R_u=Npur@5cO0jYeI=~LGmvMiYjgV59Z#*$B*PV'
    '6Z}^M!2%?hbCd6f;WHouygfl$*^s<A;EV%N&zaWoWi~nHcya&x#aEeG6<Jx?-E4Mqc5tUPJL{Lv$arPM7by?$a?tg|yZ>6=es}X`'
    's~w*9Pvf~7`U@%3@E;ijm!b~D3S%A#ASBAifI3JMS>3e90wQ-MgB;Nsy`lCJ<$1L4ev-v$wHiU&KUguN?2(_4DJ;C!!x{mfrxfko'
    'VxiJ$K^lYBxS=F=ffgOaX}~u~G#I97xh;$y&J?(XP}Uib^3d59AZ3tbM3^~Iv%&40iP>8+E=b|kk<6kINC$4c>OUV=R(H2IdE(?G'
    'G!U{i1~{x&FBDzPAp%)*CEjdNl$QiM5nHfA2~;<eUJeIEaE!;4Fqs&bQmFd4<;z4UC8QyEqyR1?P|4WR#4iyxNFtH;i1dUdl173&'
    'p-6@g^MJAb%gdM`PBI`F2Ff5QRt8Q9Iz_sZB;SFViu(_IH#j8dAOHel6K*1phv49m)9`+nb~i2^D@r|*0y?77yawVMQSTg3vKL{p'
    'f(BVo6oriU5y@ys1jeb5q_Qk8h7Ymj<7SPG<|G%I;}-31Bbmzp%%73fC&Q?=&?>qTNd2Z0Kn++ABb1KIuX@l;{|O@{n`dd8NN^8`'
    'q4#rKQK8v;6gr1S?TA(fGSz1Z2pt8~Ybc7il3L;UWug<F?j9o%5n@DW?vf-wDSisxB4XMr@@o-wwju;&0U`o%eo00LX-A0PLarj2'
    'Yw|qA^!f(rR|vCxcRSFb&%^tVd$CtT^t2T@K$JU~of7zN7D4GN#3hh%CX0MkydsYtwYcCzCKDP#8?rf+^Jvq%_dgdBqstN3K-`hc'
    'w3X;l65~RRiWxU#3#~)U6>v+*h$3b=FLXYE)+LRy%#GI>syZmWl}fZou9!S(Zo?(4P#ztrzXB;r#OjHg5HFrlstF1_YJiNu9$*<5'
    'cMq04dM@I5hVEuSX?hYKeo#1@aTTLSq=rY4m4S@xh<IY4<pynOey{*kLlmd6ieClxU%;a=?FF1R<AxCo$C@RQCd=8ORtDKRi(QDB'
    'X`*pUat4lZJ1ouRFSt1*GjD0Q^srpYx*_^@Bx7F~IvGdmD+#q|ETX-}F>Jwcqk>Q!7ewkH8`6!m;~@Y!pgUAy1vEE=rAR!h&?%Dv'
    '=(fNw;wY%li@I+b_<Jb4tUQWuIn+)j(hYdj61@RFy!-U=upCA@Z2W2vBj5p1uY9Yz2}n$VBwni!@ry*#t*9~S7IbGxt5I~PY{QLr'
    'u)17K@s!jX0n1Ga7(^h6OWJWg44(AMlokh6KBAD>2}!(F;DH3dHl*RuDUzbtaM1H`|M6*feY4(7ECRqGshkW5y~>%iqX={*5^?~U'
    'q5CTkQ|^>r;PfX`V4P7lz;8Kl2%%>2AI*?yUHK{n1ll1mdx-;ZK8Xmyf)H5-xS)wtURn|{3<*m<ET|n!iZ9s+DD`Z*qr4s7-~RZn'
    'nDm-dO^dx*QATPZ^7al%tB9u}*?{6w+gUndKg1izd?J=Uj|e@}nrr{3VLlBX$`IqCCBkq9<mS^^2;wioSxba6q4+V~M^c>;A~Vz0'
    'BKU_0HF^@}7TGyNXNY|Pq?(LM`H8eX6n#N4Met?-rYfzskQIb7k?2IWrm&X24{#g+v8N&Gg3wgh=i=muDg%NnVX}{aAV{K^t^}Qq'
    'po@Y^U4bMu5upQ;`aDEEBR7;74%uQ?-M=1w{_X=})IaP3fkdw*S&w2YqtcFU9}?q)538liqy%XgfTAI>7AKF0T(u0~Yk|}yH?~r='
    '878TEazP1VGtx51+Es$oJD{DD3PV~4pbV{{3rcbVg(#5BtnI3&aU5k_ly7LNj8aqXRxWr&Dk>QnWXq6J=K)oN;@7JO0<c=a7w~#O'
    'Rw|v-MAHB;{RFV<hNN~7W2SY`^pIH!=onI9{7N!%!y_FL*<m+Gf{}Rtf=X2YaVIM_0A^3o4x<cZcMPWYIY4L|0J1pcHUt?mRK$We'
    'zEzLY2uRK_ks`GSA_ysvv%Dg2V03ngE#1!V-V8TolT-w>9_mO=2;M^>UWpp=VnJ>SDksD7jLI3XGVm1b05}$b9ZN&D2cF@Phh4Ws'
    'nUyh;h!t?-kRm<954#}P#j25pPzLlC7X&&eMH5GPtYs^Dt@&frX#}#@-yLP^f#8g1IqAqkB@wPA0>(+&(|Kdkv=vBBC)Hd=(sY4W'
    'GNNt@@Qq04YWQy%<%i|%@_|c7z)%Y*Rz!kG6HqUQem^<sBtkLA37J*^W?2!SN$S#|$GActABa_kma6hV*=?5tILICz5UPl?p2+YK'
    'v=Y*@HJvvqb(;<NiMCM!HxCFon>7u;0!?dbSo;oIoyzp)7^QVKHf|VVz=Id`kAak?K!%-y>4?h3GH6Mh3J{Nmv_gd!6{H)ZM9z7T'
    'f>ZJxL!cmioa8H5ou)fNiV!i21vOYn$DL8ahi)~5vko5S1h4=nNNA{^i1t5^!Oi`X1eSPHQh-JidU7O&=syyHNctyB&y(m!`oAUt'
    'J(8RzO=$)c7s8iF|0GN5Jk$;xat!p{Rs!K&@wx>uqTHgT^#nvju1;GLR|`C<xaK64NwYwB<UmT&M51?H0Mj7wXf?My`55seT4-+&'
    'OQSV_gl1$W`OWbnh)V$^J1WFG4D*B}MzX|d8)ifj3@Ao!8*R27CuvMDS3KUL0kWz{#!uri1Fej-bt3d>MWJ*Fj3~t8Xk#26+Q-pM'
    'k&N($D<8w8^2)g|aR%L>t$-c2n$ZAV!XOxbAx#?PkLiMv7EPB)$z?GkYH~{AJub{qBI9pu_~tRz`{4)ZfcfQyu8T!&cI^>ZGtWTE'
    'r%fAx?~kC7KxQGyA`;$2J;Z!SCEa|1MEzugH1~)Nlkyh6d$W8bA^dSDPA4RH4nVFjgP4&@Li#vh?GY9mPyl5mF(U<nVaTct>ok+9'
    'WEKO2hN0O)CTWP76U+50>i9$wp2X8oqe38HEg-~{2n$uJEZ)mWX`yR}pcM^dJ+sb@VVK-nXK;=pI!WUv6^3ju>KTAEi`c3qOtgnU'
    'V$%xgivR+c0QkOGq6<yBCjO0h?d!oR7DwAOOFxs6MS^9+sz<dtz-2nb3qf`PD0W4P2hgBMwmLF@EKpU*5^1E`4#mFZcAo6q2>;bM'
    '!ygNrM`Xw9g;YvBQ_XOO(_~0SqjU>dP(*&H_BcdON;`mC+s&&7V`eTefQe{<yelTsfTft>siq4FgvmhKKH@q2uz}4Xjou;U+Y*C-'
    'ht)O|cN(d(a>;ZhX+{bNDgv#fw$YW;v;x@cB%%<Q23aH&QRTD<Yp_f)N=5WG`l+!zugA*oRkM=<(v8jvsrjS^(Awa@B1$Kcp2>U~'
    'XeMN2V~HM-%mAK=WD}4gc`;O>1JZ&3`WA_A4|o<P-e`a^Mhf(dYBvL^wgcX;;ygJsqx1+dU84Mz4rggL>_Evca&8T9Q4Xj>L;pXK'
    '=zu&yyzBrsCDK64EM}OzWYBIQ|HuWS8?1$+qiVK^;p3Mz1c|yAsH*J%B5H$EC|j;)0Ag*>jigl#D8aHAQhE$9zzh)uX|=dF*CUW+'
    'e)C_YT0Gft3*OKr>Wv|6YlgojD3q^_#K9)&R9VFTTg3d&a6=0u$dS!Ak%E05;{66>R{#WnM*wKfIAdnhhLH;tNF_Cp{lhXM0AAZ^'
    '%V<CyB(GPbMkulc8x0M3_)LFADUk%~LV7G+IyDa{I*SLwiD;F~J5-_<noLL?pn;PvPE19^6BVRyr#|hfC2A;)GZLHZgt~$TudpG~'
    '6ay+q0IGZ%S47y(D6<~HZRj{q(iq_WP0u%Pzk9vRKkR&iq%^SkN#2pvAQPWx9{6XZbJHqFBLbRra2_?ar_Ff*OgD&67lRw;Myo6+'
    '@n_69?NEvm@BfMfx2078kbWWS8nr4tFw190b|o=mqP2kx6d+pD9VS^AReJy@fc@?5=>5B!w;%V&4C^3Sq2on5Rj7e@XGZ=ZJjW!7'
    '@kA8>lO$)@uqb*&*0OhaN^dvrG~n*)0p`+(#N!2+8!7_YNdmqU3MCXv#KMyvt~c6SaN|iY0Jt(4p~ALje;TNA`501_*O3%JgX)mT'
    ';nhB>agot!U=@=2MC^YO!1)TENRoyekp(m_z_@Ho@bh3BZ`@$B@^};cM<gc%fbmhzhC~-MG%_of2*@YlNYjV{ui>cfqcw0uQ0R9d'
    'qoa}bWjr!vX<0=STLguXOqob~AeI+Mos0ni+{9*t+Bh;%4a)sO9RQ54MO`l9!?PQf?hcX-_<DTzx!C>Qdy?-~N@La)q8v5ZH7d!D'
    'VpTCBIFW`$_>`XL?yg&TUME+&f^+PS^5GMS;!huceD?tl0a-+jsA6hJ9YQ)0F*W$zJl^EUa9v1&A15FrMKb(_CYAxZ(5L|fkGM6B'
    '1y#nn{rF)S-t0G*h?Vw!CPBYW2Jq!hEI>>SR@2Q1s|4Ubf`tWH?15DCh}d`lPm$@|8>HB0K1zVTN7UaT?R6!aVghciTLhj?$xaIZ'
    '7b2Sg)z~GlNCEm35feQujeeASzx{qh<%Lph8(tDXEznf}exuhBTtW#lprCW1hWCQX4|v}p_HCBg3|r7U&?H*N@-awyb|`=)sn8(t'
    '{CV(r;~^m%h{4fSL4`gkPz=S>_K{7Y2C@t$WRx1Dk8h7mq{K^>)O{X|G`_ulWI)MQQc+01LqHjxONnJp5m1{G0-MQ-2*~?Eln&mM'
    'QKTuN94^@!YwvzyjEiT7R9R9vkH|`BVVa0&B2~+3;<QLlm<$3BLqJ#%skJta6I=r@d&dQ(G}a!YyZwF#P|srzxfo%<`^G@j1yx|C'
    'tM7o3M{FCVytiDK2}mevUT7y~)P10xB@QK!1~@ejD&6tMOd|u3P&DaB5#ACFT$vf#2vYw79C_Y&z)X-HwIQWwITEiUg@EiG<NJiT'
    'k5^HNMdedcn@CR+h?*hwWgsyERxlzrD;QFF$u8O65)lVy!r%<R)nJIb9-F{$+3$r2!u55jy10&HEzbjd2NB^DY8`;gNs4+Hk-mqT'
    'fNoy#Y)njkLttOYGy+DHMM1**$NR9r88$B;zI$`?wiLu39l#UeHw_D_tSKVTh-eU$KO>Gs+Qp1Wkri@`SPS060}36XpvYY`(+v7w'
    '%ZGP`QssijVdS#_<aPp5!w^ySij;g(^=C3z9U^9t^(ZHJO#(?!WDlE3-gT0B)MG3`RuxJ>yUkxfl%p(aR|hkb2yx@~_>PA_)L@_C'
    'c#S|on{Cv1vo($5Vjl|@L?X~qT$q%(ktof2RLLZ29fUxc>v00~_Bs)hw5!D(@t(9Bc+OCwXj!-F&y7!}8mQ)9S|RqEn4q344q}Vg'
    '7fz8#3jmh{h#T!Io+kt`9zT-7t&sCg8cI-&8BvXNHuch77?6{(lAcY9g+@B+Du^~D@HbH@cX0vbuAvv0bwX8MVI5FUMii9^J*DmT'
    '`}ztjKp_U8!|3UR^lDHy6wlCu6%lWYq@+9T$aHlA(GgP89)g>a=|X$n=P0$<tanqwu0(v7p-qH@wjNdUX2ed&l}ro==s8mCw44!e'
    'O#)#9GS)N;z@^<g=%@EvOb{a#t5Mw4AORHdX`XZ&>dKL}gqZkwr6w{n$?QNKu!z!!q}&nBY*f4G#viZ`$%`2srw2$3vPDKxfY)h4'
    'Z~(2zuYfN?O{P(T5J@@+)T3EQ5Rt8kAVcZ5LXCaln(Gdc{l+98*yRBKAPUKCNX%XV=)$3>t|nc6T>(4<bZ7t&_;n1UgYLEZ4f^&0'
    'qustQ{A)-MRvO5F)DuFa$x<GP()B><FhcHWTRrSOi7*I*0I3Oxxf3Gb`iHk+)3a5PRybP{qA2R>Cx`lgR*>c~5Kl2s>gi8pkrHjr'
    'imp8=vLyFsSb%~wz1U}2JCHYN-gFr*1OrJ_Jh#|owRm(T3G1baE+9(?)prqP?r9U~m?zp~Lkb04nF1A;NoDP;5(iTGk2fnkW1k9v'
    'BBd2|pvVw&q^bm<=tv-T0rf<~jX8oQXXJL0v19Rqv6u~U3F=dymz{?E&zrdvmPXV%Z5E&p0KZO0HhVWr%eZO~2FW_qmGmU#6&d>r'
    'lJGSYoRO@k@R0reX?T4z=R(lKhE4|@u&}NGG@402$D4+OT1I;)Nm`JsB}P4Oxbwu!m7GzEQcrj7C_v`3%6V3nEHM5f5s*XNi=k^m'
    'cKbjgV}b!pHV7GpdI2P(B1MqQIJjg;z9XKzb^Y8mWYL!pRydRNn<r$i&2)U8WYYpGaaIVSFcM`+C#ZtLMWnR}5*Uc&K*qqukhvmT'
    '@yW$mkgh-yW|$*w)quAxIMD~>W?M4^I>0ztQr+bY)<cBjkl(X8q?U%SaPC$6Gy}X$iu8a{AaI4uSb^+ffdYI332zBYX90HVY9xw$'
    '!%4s4Uk0*7*2Xu{@X7pYZqzbPiWDx3*a+uHr8O(uKXwK1H_$)KmU=U4g-CuV*q%;ua|N14%<*9=Z{}iY_FhGl7DO1cClUvi{sP|!'
    '?2!PB5d&o1NQ^D&)gqS+_Sb5|+z{Z!Kq*kn1+`eW4rImBt=Zll)QmE{%YaIAZdtsd+lFVP(Id4)A(8~(SY-9JKKjCfxy#GI4H2|J'
    '?G#1kv<+$maJeP+K>zndJVYZBX(Ihu0zVfRoiOp#82sD{?J`E$Dxmv|8F>xxQO8JZa9R;mi0D|<KMQ1L&?QzO48fC9K7+#(!CRt<'
    '&>TIR`KX|US>lt<kAX<l<2?Z$`LGyEiX&Z#h>#k*2Tj0{q=`sURW+<z*GMX&S5mCWCQC03)rp4@`6x8ig$xE^$BFco1-iQ+!^K+^'
    'LnVup6izp7cw2PqC4liHSvro)oQI8--nP_4LXY;?lCBVd?l_>NFquf>_NXyWBZ@J@54DnhF>EmqK>$(9kuuu21NNG5!~kfpVaIwz'
    '3eY&Bb|q<Mq~?wS5HKY0C%tYia?&KsY9YF4XCsL!KLf3RuI5xBWS$55uuShh%*BO5@&FZQrUl6x12GVUuA;CY-ON$WxH=&a(<aeR'
    'cV_U^w&4zK$Q^5QO1zBTj=YaTNO}wo395)Xon!FGuL2|n@HbpUxWEGVB-q$wB+!DiiijJgd(>Q%eGneou)&^^#)FU?y4J{Y0cz?5'
    'Xnm6Lk$B!rlZOi}&O@-o79xb98tGoPBJLRD<50l9Nd5w7jcy=`6~H8uhOXR<zz;H|NMmty7DT#>K?M>dqivGGOl0+~YwN^4>H&Tj'
    '_G1TZ0Air<dM=!?5om!Zwg6*_Mo{o#!F3yem<FJZAtDE#_KL1rbK%Pv#XScQ%7v^$4<{3F77><5)~Q6rO~Ad9#UW5b*y24qE&ymn'
    'X0H?q&!*SiCjrUc7-uBb5)TX{>=1fIhfHb|?TcCbMC!MqD~@b<pp!b(9P$vOmIy%xl*hbl7<TB0%N&5RjuJ+s!yvWJkE8?BRxAVU'
    'xI}#{hZ5Gr5J{4*fcJxE9TKf|HdciIS?~ef4!o|#$pKYbP9j=j{IfBrCOQ&9d1AqOt4D|uooY+G2ADWmRDK?>mvfZJefx3wT)ec%'
    'QlhIB9bTrWcjB|~(F^LBI695&$zEIV{7ak?2-gCye{qKSPV%&2Wp$B0c0|Oyz>=kKD3*tE7jV$g4I(`(kh!#wacGoYX`9GEl*l34'
    'Vht>Ga?{4^)B{zXXVl3era>1@c}asJz8`*ODd83-wUBhQxN4FIG}MMTE+b-3gTq@)>)x)1;`BhKGwnPvF2u%4GI0frBNTqI(#P$='
    '1{JV8?#xQMV5DmlN4$Hl(YKmRDwx3{MF7dV>rDe3D0T^Uq&-|EOmSo^ctG<7LsxX7<6lr04oMpt1)_=F5>1eLO*?-7Xzy=6FR%C9'
    'QIe$dw9d$zBGTGm>q%Xj!a5+*02r2GAiH8kRyk6)R=r5GAsN77(P%ZzXjMp$1i@QU%n-0|$#6ELYD&L>oX@028NkhXA0|o61U>^4'
    '(m^tbMMbfA%_rDsg)*#>j(8HvSS-r`^eIHmk?0$MIg8XPGMgoeGi#J=Mx`&3J%b?Knq=_xFg&U*XyWw_<tl)_Nrp~{WP;OiEU022'
    'Hm{shc;#FWwT)6zcz>NlnDM@U-G8YOSr7r2h+IF^`Bg~lB|}*OjG4%5Cf#)$M^vK&*eID_Bl6)<?<69;p9F5BsPAJi!Y1Vs0JLFH'
    'b{$EN4TDsu%4rZ$s$jg)H4TV#H!JE;0Y00gpWEP$2Y<~KwxWt>wFBjf-JmUs3{nR`%|vJtSu!I@8?A884r&Q1n$xARsJ}~RKErHO'
    '^EIp6Mq<kuCQV{lqD%=X7^EpjgfggwbU3>4a@7{EUz4Hhs!_j_PK<1WEtm+Hk=H^l4T7ZW0{62*TbWQ^*Z`eIpynKW3aBVVEY_g>'
    '0U4vzX5iNzXVP^^y%{EwMN?yDvqF@IxJF123c!)hx&i`HN~F9HOSU*K;?~5ZCpAyRm?ni9&JwbM<eU<uDCqun?KMCI+@%rV4k-Ez'
    '+(eQxq#)2%2?WnfTQy%zY?Wk?9Er||9mzNmQy?|vvj0@(au1srN&ALx)~v+P1YjN&@?I5<K$c)wVYZTxo5@_ZxbUQY(0WM9B1rC<'
    'i*2zJ>@3V^iFzhrIe4Jdk}3=x3<*(sg&S;BdY}jf;8`mTxL#sqq^yzpW3TC#g-@K{!B>=%Lae4lA$ey=rXc@T5S@`;OVULkID-rT'
    'X;#uU$3SNKydjU0u4rQ818l}aouhnVwrpq(WH+*0$eyI52KWsMo2dxD1SyBYuB5S}h%mrfQCN}q7s7+vz};pjwvDuDBcMby5gI9O'
    'WaE-*qwoes3iTT8Fq2Fh!YoOV!xJ@xD_vu_#EFl$?shg7@*Vdu4&;%oGeCdo;8(l^!$(BplBEM=3>wmSEe30%bQ&dnhnZ{~hq70L'
    'xh4sOL~woGi9pPY4p&N#^jNsz6bfRI6;1q-%!G09BT(f%z*&e%xJ|`TWJFG_W4J03%Er+aU_7JRpcjesR^a8JX!J~!jWX2=Fb-Rt'
    '@MW@en>5h_QOK|$iPK$ELLO&_=Y{8A7}Rzlwu$F-+A{?h35O7vKzazO!K0Ed;4|TkB7@$<4ePFbTT10SbGk-SdiRiFBC}Z|5OLfJ'
    'GK{2$BD|SS%K^&4IN<==4O}^E+~D23#r={}Fe-m7&Uk=LfZ<H07)e8rk1;eH+54nOID|F<@tb51Nd;i2!g1$C3@BJ_5#V=yO>^l^'
    'ekM@y7gB`i9+D<OoCU+VSwyuUB$e2N+R9CkwN9+f4FTL4aY-om*&*XH%yC;Hs<;UaaB)q%4UeQGLV;aI%v5jCortWA8$wbb)0z07'
    '11gsX$L(l?NA=D^#}=U)$P1v&mI(Qr4DCPZN;46j9^iaH5i4Xj0JxKM)1ZKzV}>xA=8dl@r^&{m%cn;LI2XFuB<E4TSI$b%KBCeo'
    'DNvry8UIhzC__i`K#!>AJd@d_+GMn5EOthuIU9gJE-NuaQUH_#dJQSG5)Lk)B@x3R!w@KC4rtKpmQ{v#Ba7lQ{jq>umc38F0+j#{'
    'plK>&XA%yG7DLVWVNs~mGsB5Xw#O)tgghZ=ZHBoW6bHCvV-)=rAq<vO021tUQ|Qc5$Q#d3g4Te?1ZV^cEzrXOJ)yqZLRuUGuV!(f'
    'SQbY&I}WnJNx>Lb0k6io01KK_GlZZcf<GY55$VJvf2<a>wRqH4VVFh~1Tq)OWnJ4ek(U~gI5{jNEJ%nEQy)om=y?=KFIE9Hrv_3o'
    '4B0k-Ygf`k0U_-Z;B~6i`u8yyJ|;0OvhPXI0yc*Pi6?ds0OfHevk77P5($RXBPr?@ewsjpY*0#B(}A@P)AJnxjDfPG!Vr7)#8bDt'
    'lZohwbbaDmWFgs=h#L81#BK%vL88c{8>baOuxB3ps+4-E07_`-hPo$h4}o9A&7C5<0mi?hD}b_>l1xH7lf2&&^ej?byznFeB(<K$'
    's0)j}8<%=C;<^H91%uuar9CP%M$+$5O90i895CfbHD2vJ;{D15;H#rNBeHAGLZ8(Z<)ff78ssD~`4KsPi-w`9wirmHtJ7kTw+RRW'
    'QZE4cGFbrta$vS|X!h5)@3#krchkEJ_6kJG#giW4hh@X7#?2dNgcT7@ufsBuR<k0>0%&|5079hHkjg3qA~Ist^{2NtdrgN?ZD!Cw'
    'M>);Vw(wA<5z#A2!AD{U+2S6!K{R{P`h}MOTtmVkNvL?-={L(QX>;SJo7eNU6-xj(&rCWSBHn1H$(|=&isY+ZGzy}T0Yr?5IG+S='
    '2JSvlRRqW^ai^o(cW{5-eh(0!T!pl*Nim_|=<HD88#>8$$RkQ?Eb|1nnGsu^=KwTsI#(+PiL#Od60~UFuLnxEtz>&Fz=&B8IAlrR'
    'a09BkMFgAD<pm(eideE$+JQurn*j=Hx2I4NVRVVYokLWMA=`NcdOHbLvIxkYMdYP{pBlsXd6ISk3=7%Ar0&u7%_}6PU66-DSG*aC'
    'F2bkVk8gJ<1d?rTqW!WGX-O+8x{;^`PI&~L9`L?thsGd@8=|5Q!jocp6+mIWxgDSYTZZius7F8rGQ?aZ5&f_TiG&nAquSdLk&!DW'
    '>!F{7RgRzyyxp>#)a1MehCoWX8TMk1TM06WTHC}r#j=b@99&Hlz>XmrwIfP+l8Pf|(o+o?^?F<fgMw>z;-$527vx0UOl<lt5Q%s-'
    'uPE3`S67iJBb`FI)h!56CK*6~S&=}Xk&o;(e6O@UD4fH=jgP+Z@2a3J&3+jr@DNGEM72w8iAd?<lQB-*Ptd(s;eRGl6?m!yK$Ee+'
    'F?A%Z+2alVm(?Fl&o_oNG)JZp>A_1NRe%iE84<BWsVG27Y+xigM0%QWK!LVyf@ftI^hDdmo>aGK4<A0>pxDo=tj?yVlqiYABepB9'
    'mekI$;t^^lm5<EMX<DQrBa`?anFFMa4T}sgu|{oh?F<t;+YkkU=2bc6JP6I-Ycj$}=Ok?c6$t5uqdM$3x?up+sNZliP##(+El5_A'
    '<|(2>Ho~auLAX>PiUJTxNfKXdAj&{NOaL|DMT+!SYwb8qhy-yCq1aow#(;2mATX|Ej*^(2=;-TVuImfqB@<Ab^GdXZszD_BN1)V_'
    '9ldy?wg*|#L^QNeJW&C3W0Vr<t8~#15m(m%PAUKbWKn?!2Oa1X7Nk#mTE@JLmNp25%kaWET1SQxUC7DNQ25D+qF}%N|ETkK?_S^j'
    '`XB!1uZQh_-wz*A1^D~_eD~r1y`>c`-``Fj;IaMQ5OX0_389$b`{C0El6l{aH*Y_Eym@^~T;jWgzVn?D${|bZ`%MUZ|HE+m{c!u;'
    '+vPuLA-6vc$~s&EvK|4_g{--S^b1n0Q40xZn>Y=Gx&~moBZqwk0EGqarbQ6R0$dPGeER#pr)~cD9Fs0zd_R5uyp6%89;6Bj>9%?@'
    'nCd{vCqP3zDv}`gTfjp(;SC7YM2R}hMEVi2ZXhb@b(=bb<JZi3dA+`0%A{kS^!ERqHyU6{052sKaGtir{AmP@05WPq@`$j+xHRcj'
    'R*z1SghxUwo{gO&J%7P$-@bX)J%0P<Jn0Dl7XT_C{$~-kOLl`neUV7olo*kgGXvY%1VDyFBZ=erX$8_WEksL9`rY_9L@_+;%*z;T'
    '>NYB}7bYko#FG}_o;u+3>j^RJq)3smG{KK3$5|pG%x`5urg;S*mC||Y^QSlOpL^=t7;Ng86mtFz>2zd&63<5XO0a<3b!1)-qya%M'
    '$5Z(LbHdZ+8$8ym0o)N&fB*BxAK$&zeCqGsfBYVq+MmDA{+HYIPf~5k*!b{sam##P3g%5W^hxRn^UeRK{@*t3V4v+ekPI^#fowB^'
    'pjO1#1^BsPi72Om#O+aw1*#L^`=(WSjYx<Y#e^|iAb`_Vde)6DW3Z_UJVqiY6cK)?|4f_?HAeC3NK%?qvw^g-K%GSrc*e~r)upG^'
    'B5quI+Gw!tqtN*)X!5Vt*TWAR2T!kEzy61R|Mhq4`x~gX-@O^8>C={;y?jU7^AGQC-v032@PWRk#y_MPL%jU@|Dhusent=910L%8'
    '_tVYyO}cQ^^@`}?@#gi-$DjZAA8$xKe2Y%<ncny1d2}oc#6iFNckx2fKVC!Gq#plWzOeMq;q`0!H)%<~`bYfYRi5lC#8dwhK6B|;'
    'H~Ci{|NL=d;P_{Fp<ev@ZyVXWQx98?)ZdHGZtF%04EN^UPxR&AiO=i$;y25Dv$a_C@%h~cYWdA_d-DSSvo(0$Fn`7`K5q^27**+C'
    '{o^`(dc7$=Z{DRjD_IS;>|-hS!jy*J{^rB&``^8w|J|B2o1pj{_SQ6{w)N)et)t=XT$WS)C(!GAd}jpPWjUR9c^z(EZ!<O)-#ug_'
    't$3l!JZW~cT_1*RidI(*v|S&j)ZnmP9~SgY&9~#Pely?x0~UDmJ8U-o&-vze+ou7`{IHbcwXqp2Y($~ZW&V3Qvor~3I+Jkzn8fYJ'
    'celU#&G7m(xT^*W`@+1cC*^f#2fRbWv~40*htu26)+d750ubE%tABj65UKpM(4H!@ZEBF$>kQj+Za<AjkLmB8kF+gw`+F4IKtp$+'
    's17RoPJEWXE%W^RLW0`DxP9f1ukg1Q`O|s-G+ikLB22R*B9uF|O0gaJ-`-*#cH;ApI$y`rNlOtsCnu$PF#SkrPTkhGd-%Llij><P'
    'LK8nm%+ptC8!`JRx7pKHWAaOyyi$3t|24i&H+kNsl6zJ*-}1eAo9Txzr{>5HHO$8kwK}%#a$vpD0}_Z6ouof{{>RL_%yv!ZC4ZUv'
    'H~Q$`53GNmx;OT;dxp5LAVPy!dHe4DfBs5*7QY3#Z!}-%z&_|J_n@!*gT4yxg-h)lx4ifwZkP7`r`sR54Hz@y)-OCM>l@erxTXf5'
    'z1jHec7MpYZZ4t}sinI0>~bry@#4~{9H`5H9;HmOVC$0RnrUJ9{JZpb{X)_dfi<xenw@Tc)m^Ys=1fxC5OGeep%!jN(eeLgN%u!-'
    'eTb{o{^}oJ{oj9<>eYYy)4%-l@Bj4b)t_I<KN-k@mw)|;qB6HPQ>m{BHRul${aH>w4yc7W+<d(K!}RhcQH-`p(&<fb<kekHJy9a('
    '5@lkU96^o551wdZCZvfaiMH>FUguqYE4!&8H*dF{oIle}4zE*##EddepkEOq*qe^YuHvaSQKY$A%V{ef96{M|T17Zk;WSo3+8=&J'
    '(rjBwYT2k|nCF8rC-QcI%ME!nczJM!<*AmZ^72Sv?ib{@`>jd>C#Ekdc@~em6%I};t$d<+MVaOmRCC#H^RV{%&W3OoXIEUhw)Zgl'
    ';~q-=R2R|bix}fQ7f}n-xrkc$W0%cSUBr+sq871x5p@#R?M2i{Y+qeOE!kxCQ<17qq^f1D10FX~E7iS;TKUdR)G9PLF{}GpHOgX4'
    '4feQ-Qa#lIU0$H}caW$y=S8x!GMs$fQ<3kG$XA<qdE>NIJ)*VtpacI@(;4%0tnUz}4PC-?j90m*I=3O8o2yTT5vKEf!c3;i6=4!j'
    'zJm_@S?n-62uz)jVSb`@PIFo(abDlBu{7n_C56aHAwJcN<~*a=BZb%{1tS<Kgr{PtQ(~w_)TA)%q+mp!6pZYVf{`^TKr1L6%590q'
    'k2Xr#TGXaO(K%&P!6^A~b=GKAdv%P~wO_}OrE^f(_*A!PO}EKtcbYx1#fQ({Y`e1C7E&b-O3!pKwly7MYH*Fs8&X58t(WA>apJ<J'
    'F-}%ixMI#9$MwqTgW9E!Aw`fGLQ)uOcS|VQEyml*tXY1G7PRNt_;}hw($!AN(f0k4=NZf$9LEIaQ<Jb#8b8%xbeJgb(REC89bRE#'
    '+^?n*{(2nav#U#X*`O8fnl0F*OkJ@BD~_?{dgY5dYyvAKcX5q}<HDZqE5GGdhR!Xwq}iM`k#x{jX|9Qk?^z3T<H)5m;jHCbQgz}s'
    't^Y_Ph!@1Nk{fetPnt)er)hU^=CO>bysbC8&(s>Txdf=^VZ2R!PxXKEPL<Z0b{5jGX^_<vwhvyj5BNO&eZ*ybb#0|MT%gI(R}O7k'
    'M52BhWN-VEt-)K$!oy~*z4`Q-F##K8Z}7NTeYZb;$aJy$vuq5t0hU}{FU;=__oz_EEbvFxV!69&`n(V5M5t!2#o>mP@^Ey64zmMM'
    'rX6(Bb{64eXjo$6qE2mHCNibb;_(}m#6MO?Jms27L!wfrDk>bdbKlI(7mT+#t@u~t`Kvsm<ajGPgDYBoZ(3F;60Ogv{VrbU41ZsU'
    '9bPymUg+$7<mzmX7dp#$;SjFJS(4V_T%Q*@*WrcEb$Ow4Z0y)Mv^gJ|uW4Q$+OPAb%M4wTP#4V5B~ev*uJf5Dk9*AwbBjNip$eTD'
    'PkF{9&bXs-cKQ&nsXLNT?ZgxLcp<sy^*i|_UgE_jnXhzYPZH+AdW=_hQ>j;XQK?s)N|z3mN|nge>-)&m>mHeU%}AxE8py00c+;m-'
    'Z#s19O_xr+VT1QXpv*GR+b*GcYbtsE{+N|@9WwP~g*HNCqaN>MMW&xwi(zCs_a-d!gz4tqCA7V_cL{Bu+;bN~+XwX^p`CVsEW0~}'
    'cAyJ!r_c`Kq>Kjm7aw{N!k5@CL04YGLktDYh1!x0fH^g_ZlJV-!KjY(55`u~KaF8RXK*V!!arDhpYRXqne{^W2d6s1KRDYH{=tR2'
    'gn#h84fM8={V_F!j_40T?V?}zM8C|kKO_sJEBo__gm|ayPcw?u!|bNO<ex|1W6n{00hvXq&dfRf?x3hB-5tC+DtYi`J@i=SV)L7@'
    'zK1tQ6*{~*YPqvVJ$6(Gxh5SV>a*o?@aCw)HE)iI`(N?qXxQLG@AQ{+`qAiG=RA0GG*_}X&x<bBHFu7-eg2NAp^5{LtRWt}S@)D4'
    'nYErsJf7<ilO1;*B6a5iR}<_`A{!w_ueyZj-JP@*#9g!%ETgTS+*eud$Kdayt*%=yGPfQbNoOFPX)B(6Uk7bTA=EW-QH$<T7vTMl'
    '@w?V<7X9?K@6neOr|2V2VAN<k6h=+1ksC3!C~<x<OUF(v?2%vh6aXd5w8?n7O9MdC$h8WPCz7t`g$f`AUC#&T0A=2E(e6|Nq;TSH'
    'Er7n*d=PiV1qlBIo<1o;C2x<IASo(4yps0R*1o^y-HM?j?t%Kj<$c~2DNJVqw33d*mr~06L_R7pbYwm?g^tjdQpujw2Z+d}*pE3f'
    'NA<Q+YT3yBkXuYg@KaORCBNxOew8J^lqnAG9?>tQv3JV;JS!_Y!k?OSkLgm|mr$N`%~Lar_>j`y_0&ww?6J=D6abYK0Q&sC$77<2'
    '-s>?n9WSz`rvs?01JKv~_h2bw=RufSx-Y`i#wO6y1JqJzAy#j^EZTz1xc(zAHTGV4sVOw7K%x~Tt7qPDkcyJ*o!9h~0hN^j`rKFA'
    '!02Qhx+HUq5LXAn;ct*CJw;!VrqYeF$%#$ryOd3U2QgynX#_fJ1QKCC_Yj*hJ$+N=5S?_^J*7Zrr9dKTr%P<gc2rJk>FS(PIW~cw'
    'R-lVkfFPY7vAMq1DG`v<Beta2wb4D);u>Phhwqu@X?jY5E=qw47qXZOS{22$QjjMSZBHpc6wE`Ef;4YLrrfO*Xi|~xRtmH-_bCNh'
    'e?crB38hLV-yQ+L5<wDYtsq|_ZAItUv^71Y0C5OhDagCxM0WyC_p|~83f!j^XfJzOf%c}S73dVcb*UBT{Z+8m3PRq?(BI488?_(@'
    'x03DD(+hMoyIx>>dVwx_fsU?uu-Q8bmny^XnZE&$VxccphVt25!f`8|DzXmJL*M7=#~-#GqGje8m@kPCm8K05oq5!;xid&q8XhHT'
    'dm4i-8iTnv?o*m>;3qX5!IZYAG3cT(m^(r_rRl|TQcE|OQyLb{X?q%jE*gWW<1=~0wz(rfQ<`psCN-Hhc0QBJDM(YWCLX3~dpd(I'
    'I)k}0$cLKyQ9jb}FdsX2=)uTB51oifYUqk`Jmc?&&{G>sQ5#Iuy@O6y{`#QP1y5u2<en*V&%}C1*g;#-e|4wE-m|;3r|`$q8CZFK'
    'zhY-#d7_bB=g#bP3RIF-$zJRfDqQrA!7>+~6TLx98ASJv!Rr1oSj~>1r?r`)wOL&s!@!Qg+;t45e+(wFL?}Dv7-yH#{|u(1^nw17'
    '^Wt7@nO!e`%F{}6x}|aZMV6g)r|==0{_I<!o=pYob^QyI|7`0&>-=Yb5uOAzpo^FyX~R`ek+c^XNqdv2ERnb#NfafcE>;hia@>Vc'
    '%<Ws0-%gDqRMix-By%J}yUPefc=#?m+4wjsap=@tPEJ{33Q|IxJ2NL_CxT)#Z^}^xcS%F1du~o@I{b{zpD#xq%I3S_^c{XqXL^24'
    'XZn6lXW01eDiIS)%`DPY8g3;EoxQ`$>1@}_i2#MOW}FGhxyH@8w=g#+jeI?8U1sezg4-3wz<f5&v#cu@)pbu^<(^0lc6=k(EtNFi'
    '4af2o+@P<!3ONPNh1%O7nc|OVgX)qE^M1*)66~U3ENyy{5Xn5T$f6gZuM7P5TX2Bi9h$ZmC$GS|Y~LMc?q&5#J+KTrFO!-+K4i~5'
    '-DS2JM)BE{4wKuvn4B<A%Kh@nR?BhYu<vDA3*FB86L;omB?=*Ngrzg(sZ80(YcA%^$u}(68ce8XG0SG6Nfq4*d11@6`IYqDPs_oy'
    '%kNzE=sGZC%2!dM)Uw%zB^$5xSC`>@{o=eWq;%=G9Y2inkVqqtZLWCtK{4a-_U1LUyQ<xFXB}cad|+)+H{E*PZS=ivgAi4>O7J$*'
    'bQ@T=L4<C%vfeBec$;myjlA1BC#C9EsoL6SUiFZ2&5t&|63umu0V9rlMBVP+P_=vTz?}%CV3ITNBvaR@-1(l2nK73rhrGBgkR@NZ'
    'Q>??txJR&ckPp~-N!kzA@sxKxwVIy)KZm#TyLGi&wH#uP28EFR@JIST0QLH(H#D{Z7=-{bTeOz63H$Qpn>=O5?aD2UJPXo5GRc*^'
    'Vc!!;wk+M%TvjP>&H26u&zS7C2_PQk-3n({U4R2j3;szI4I9q#D#SG7lyPj=&Xo0<ryQ%;2z8(oWNk8v+MHnuKs*^jik(@Ml^1Ay'
    'e^5cJ{oazZ{;cpu#RVbWdbSh)BR_Kc&%p52KP(?#zWLif<)6jwTy?z+T-SZBI(Fx3S|*#d@0ffTUp&W?N@ds_?a3>`_p^2oR&%T!'
    '(rJz+H@Qd6F$GMQ6LMlFiZWzP!&1LEzDgeiS$&}JL8v~cdoW<=RS%KJ8zar1KB#(#_5M#6Ym5JV!{h$%!~4t_lHCVwqvOq12rRhd'
    '1=L~=UJzvGV!51&Dr9v<rP_Con$i^=9@<kyo?A~T$5yB+mTSIYEw*x}p3p?rokZx%SagiHOF4_Zn<O^&ZZvE02LMK}%k>(RUh*1r'
    '#b$8OQlFn;l`y6Q?LbYggXuy|#kX)gbsg^7l3Fcn1r#8Dn?Av#Sjpx^G{V_xDZ?ielG`6Qul@9T7hKe`X&z}_+@-CAuU*=Pb>~?~'
    'Cn+e`yI10z=yTV&7Rw;nJbC-Tb4cphA?MfQM1x}|>dufcr6=P`Pb^dkvQCtkqq4?R>a<{Iks|8$S@`2u@|2)+ygR4@L6Rm2u#3wH'
    '+93n>knZLfS>!2l(#U%Vh>?3pL#j5}qfATLGij85lZP&oMh0a`ExOKp2&_AvEFARIS*4uvDs>n0L?J|C>*{vfu-=K<e4^4+2_qXD'
    '$Q(;@Fd;v8wqA~9>#b<cH|7@eC2T`lR}on_(U^4YKzq}djpSU9^~mJiyFiUnWHFy;EObcByL(A2=q`z+ce5)JON!tXiACKdvB>fs'
    '9&nLTbVUVCl$1@SlCa!t{`>b>3DaXfDqYreT5&WTkr++xNt&KCpyTQtB<<trv}8H1+Y$<#(N|Q<5$F?sTuQebp-e$H93ih#bB1s{'
    'aVo@HoDZvXW;j0>dWRMAVJVYi$g-I}u|aJ05<GwAP3EkUH~tu<>I{YI_s)C?9XRd-m_8WZ(WWObr=}Ev$pDpnb=kV<d6{%}GbvR)'
    'RZk!Eq4%iMGxecRqlQTJE3q3UN<~?G>wpW)f7>p>`*%gt%YW_JO$xvsNB_`)4z*Tk(PELM_XKLH-E;P^VTc-K$39S6KE{|*88~BC'
    'VA&}FIpa8mo>Nq3uP91fR?a@tx*mbB+*q__**Pw7eAr+l^!Q-mYB1xwgIR{R_JGms=4CwSRVIHa(aW4aIFgMX&|L};-$4LX>PzLm'
    'k|28Uw)@)BoRY(i!$_s)rVsO*+Yg1BbL7XdA|kTk$JE4i%{Y!dCOziyPtNf1FtYT?7w+A3@`Wq?T)uGXx%Lvs;h2~a^-Gu+_B=5}'
    'cRbI;%qar|mfk)wRi_TPMK%*l;ULd3u~U}E%;u#-J+F0X=2baLo^)O(UkdHtF)?dT6C0a}B?Ok|nAi!yMOrp7uTCV^o}`b@HL=jO'
    'uubyFBpp9YXB>qh#0Q^yin1r)%qbDp9eyljMORK)@hCZ!As8;6iBv{hxYFD!$c5~GGR(cCfV*HTuNnzl!9P%~+b!mn+G>&MvFMOL'
    'mLtP%niPaN?^|2`!R8~D)!?S;VcI^ZdN8*6Kvg}QY_ye4&n6`c(;wE3j%DVoV_8=TTq!REu5}jzH|b$EnNUfnJYY26Rqw42h#M^v'
    '35VCR&|Z3b%D>$nx(m#k4YiNW9BQxSevC{Ay4vbk0T7tOg`Sm0Co1d#%{~zMgX;B)BT+gjn$ZnEM*uId&gId0-j;J%gg)*ELL$Pc'
    '^H_DRt58TKn$C4-d*GYnQX<}ASu{OZ$$Qvb$)TD9X;AzFJcfj72qLcY9EPd~UoDe(4t-Gd5GrO6U+iejxtR-AImL}Joj8*e|2q7z'
    '{M%M4&Hc1|xLJRG`Q|Tw{PSPMtHiWk{_FM+8UFN+diwqQo9XwZvf|5^fBxhDc>OQ`_Ug^w-n@J@z5c^r{`lA5zk2y{{A<LY66L$7'
    'JC13`vg+=?L5`=@aaih%+bC4;g89s#-@MO$NO4>R9vP!NL&dp&LSA-#YhJciL7t{$y717%O_niy!K+lFCkeb#M-;#?#!gQ$mY&S@'
    '_U+wmZ-6WsKnT{VT@|$=b9}|#&cbL%+0pRLnl*fH+VtwoH~i_T_5HyHy_Jph;pFb?=hiT^&#lrdpWiRj$7N2C_9sfuv*Y+8S36a^'
    '+_>P*K?;m191BbF?7PErU~UNSS-#9~_Xp<W+9|8|;q>0IvD-3m0uap-V&Z)V+lc#YGy0l81bLyjaQ0v~`1Snwta4~W2lzcQxtxO>'
    'c8lB|O@YDF4MWF$M#^7CNj)V+arHEa+BCDXIjg5ZK9^~Rz=(^>lU*u^f4ICnrCqbjV>_3}>U?=>aEI!K1YMIKd%FupKFQ?>#<iph'
    'KtI0Ew#&4FRlN%mQasV+1qt?&_)Djb6F>Lw1=l5hKtnv9_=A5a@dw{0eiouPiXPKk%DJCo^fV*>lV8Hdp&|Zf^Gk#ndrs|GTTT49'
    'V{J8k;r_>j(SJ!SQL-q?F?61ftjo_w@f7!-Jz@J2POsQ}2}*s<5|r;RL5nY1f<C3-E_?iAS%vo9Rn&z!zH}9)e`{kxr%d!6JBGRS'
    '*)Tr`n6MaB6;DnP8^W2s<Fh$MqN^|0FgBMfp0K~Rh@vw0$|)j8Uvb_*BhDzg=Ke~$_wd?$Tt0vN@+sDj0xWh-W!Q^-`038!-P=!Z'
    '#^uAypL4&l_W6)?-Yos(mGt|{wWzQ7bF7@ki0$naY!3A!!WS)HBZB4Hf2c+M(zaT4j*8Yo%jaMIDIb~vE{hZV7>jb#h)TKkW>Hf`'
    't`GEPX<@r@YSh*XZ_~o{!tHbpP`L<U)542K&C%PAUZRC>2P=s5K{QI$P?|PZ+I&--Rr#-NsBl?Rh+jdCr<Xa!s4><ce@3}8HA>;0'
    'of?7mQE^JEnrX<;<CIz^^rz>YVvYU5f<?4E-PbQV9I0J>0@K-TujMIWjB!e7!t<}(vQX+%V59~j$m7?3LWF08DNnLfFD*s*=a&*d'
    '74e5jFGWztb5Fj^sN{1`=wbOX9(wyUcN{NnjCt%NL)qB!csNO(RxRuMD~0xlj**!jiu-U)Yt!NK@0DPn3inS*bv;*Fo$zqgZf0pE'
    'd#)L+l<epq`V^94s|bzcOV@}=@fF9!9{4ryLH;IOe50-A-x$lk*&atw#oq95$O1*~-Vvt0d1mpM<exdti)iT=_OhODZl`xYEgxQ?'
    'p5e({{>z{L`pUi8!g!_r*B^hrMK&k2=xj-A<-)aJR4dQ4|7q!j&bVpF9i0Gpjv9X&)od!R<eTfK!ZX>0)bmL-i)>=CR-cUV=ZR_Y'
    'Oz+hi@hH`e^l?4qSZQMD9e1+U^~(h;5vlmZm8jlxjt{befVh&~b34n9b>~)>r>o10*Y3Xl?T$}TD(Yy>B6DZi@m;%Bl|Jk8kJ)3m'
    'MT(XCu8p{lA?{!D!Br>r(~Bt&ZrUu%vbVO1K4*Dj)WouRX3<;WQdW3MN?^W1t?Q>hQkTw;|2o$)c@FBk0L>};=v@x<+XJQxebt8@'
    'P9jB3x*_0DJwGLHIqxgvzT$>!L(}<>V@wk>(Qcm@;f}7FUXDF8#Bf77Jai&<%FkzL@|(pLr8JKn%J(r-K7d5r`QhebKa4&E@&kI+'
    'DldocGJ8qT884*P;PVQMZuTN+Ql)NDfxl&ejODj>d(TTJ54ZNg8Oj$<w}&S9%zXO>qN}Ob87|ZL-Bp`V<%}W9b9$Xy^q1^nu$@;B'
    'YHDkOW=U@%6KxL|ByxB0gjDUss^;VDqiwEJnMcy9D!=>DYI$YQx%c+q^V@?4u*Si(=icXI`TT^l$-K4HR(rGb5YOz#s%P?Mp{R8W'
    '0G+f*o7AxLe(kM?H*a2gJbubNJ_ma2Zf`xl;OR5_@mZGfKlg%nd=B2BuYG@4ZSAYl@$4g{Po610Nn2-*t=l-Vn9m&9`UBl$5k1mh'
    'GU?kBVh#(c(})<Um)fXxsO9lYOO2vlstbqk$$Z}CNd3g;8=(BM*1428ql@|wKJOR|?)|+YI)#a&uGn%M{_p|aN?!}<-elFr%Wpr8'
    'Ot8{!xyZ~6r{x!ot+`dQ>XB@NSFeUouX0WFR|js)Ps8g^OZim|TCRrUq+BX?lZeusA$JN)gvtfT&ecL>IEWIpLMo!PjZ)>R7y73p'
    '%BCg=V+^PX!Y3BY+Dyzpzvs#MuKDaj*L-%Bd1fbZffgj`^j|fIL08YWI#&a^ENX{3AeUGh39Tj*j6b1IHCP+;MTHv1wI`nf8xvnx'
    'ayhzcE#fbUlK(XP{O;4ofBo=oy?MR-;ZJYW%a=J7_RWT)|4+HUu9fEHse-ij35Vx$?TE9vz*5PF;Cc0_CCEolTjpt}#DXi(A?@|a'
    'Zei0PnR*7S^tC~j3Cfch)qqv<FiQHON^E8EZKdv_JC&~rn>tYE{A*7a=khCE4HiySHOfa-SMdxVpwd^B`ig*&tFCwqtVRuvx+{~u'
    'vQ<~|R3@x^RCT3Ju%98OuUyrYc9&hbsw;ECHy=g%%2!>T%ZBA$@KslU^Hcn*Dfd-b3n*hze<sUkRd1xP*Pq4wS*&^^DSh1=kDSzz'
    '?s)y#kU!(WjT)sMu6rA*-t=kHg3c@8ADJ_)hV+rFMzm*Io%2^!UmTuhGdK1;Z)&Tto64=rt^TM0vd+t+nS{$?8;{Dq;Ym62SI59K'
    'hbI{>RJP|9yFFI>7v<US#Uo;=-PKO)O?WWiXOl}D<ofT^<L7MCoQ)9ISdT`Cws>1AbSY$=s+2Z0<xf&$;G60mzo{-yur7|kAeKz2'
    'j<CtXb+V7&3|q#s{RmDY>MGBy!l%fY+v8KMS=Sckk-=+(X<@jg(qwi;bX^{=8Te9~mOpXti40{kOq&{<%aIDpTvY4u_=)H;5o@@|'
    'Xgnlsu0|?cFLK$4WLEB5$rJ@65-#_l;Lu-Gv+-qjef_v~L<SnXZ|{i=sEzR06|1qVIJk%DDMrL9%3htd5F>d2S<Q`&6sFIOjV!9>'
    '6H&F4?D;ftzciW5+oY_+xl%2L+@=oy<de)rRZ*1ef@M&L916**SsIzL?9Li)Y1R5^86V&v&NL9j@gJL*sj7PN#h4a;xHM(#{iott'
    '@`TR6hY{`Lh2A9V?DA@oEW7+kCh6)I;J6Dl$x2vCae*`T&?}q~!Hletl$rz@BYhnQoDlwb2@@l8cxx)8EQa;bv&x`f)MF~;H-Vt~'
    'MX~YXe!8le``_gDdLQQ--WGSTq^CGDCE8Sn%=eYxs0s|%*5G}<i|lDsazH)ZT~$!U@4l;LXss*YCcYZ&nwPu1DedV~-2-K+>>7Ez'
    'pc$1zPKR_8hDQ%Z%gKYK7s(xc;)V@obw{OA);;Zt-RaGcahZ%tQD(t%Ka6^6wxGQ1D^<#yo>GN4geTn(4hfHHT#xQ?Ei3Dw##2MM'
    '%jz*I>N~b1y6%?5r@a)K7|oRjD@{Zvj`DOoLrdS~|CyC)B^!=VrlSnMrt9OcX(;naIW`^RN9*2AMIgkJ9)oFh@JuP%^pxE)OWOk}'
    'HrlcX3%bgWwiZ>f7WD<xby6nu8BXqaG^Mt-3|jeBU}gjv=8xXWSZ3(&F`Ujo9rDoEbc%Y<o`x%k{fC;9nLp^L?w*Vh^@H#6Tt`g|'
    'g=__G)gvb(QpA@b(+7KfM;##pOb(9De8gN+Q`{{hDTn)Frx8?>H^C@*R;>8j0JT?wnU&BnMjc={UpQzA?#LQcirUW9Xmo`mS&diY'
    '@^GnW^rNSefa!|j$Ro(9?RZH0(q387rF~1Ym@tMxsO2p9GGd)(H}Q?Jl}mx)gi@2~y@D8&ka=)j17qA5RCqUL52N4FE^o2Wa%0T}'
    'j9l4+7Dlf8C^F?NQ+e5fB$u;x&4TbvF2s^aBkfz+(#ZUOvIKqJd5XCj0UbsaGsGg-3<|c?o*F=gggdJ=7%RI+Xlsn(YAET?L&@+E'
    'n+a7}9`czE_i-L;iimh!PBOdLiLmn*fnAmPLHM^D`^!6B(>?c>AqM2M`~;tRN$%DO&d%iV)){j<OUwQ)zkD$mM`M%B+nMalq`mcq'
    'aoNc|aFJP!u*tkWw7Ct6a!hR;&gv0ehq_pF!j*rY+uSvS&o|M=3e{snq+pLH#ztH1m@Kz^-<7)J<;JlSV7CF<h&#FSjvu-lezgHD'
    'N_CZ_c)93exd4x(Lo`k@HG*sSWn!}SXY&nn>g<GdDa5fYqDC#f0&@mcTdp&cs44OsqePjxgv%9rs&O2M6?H@(xKl>uojO74EAFhz'
    '#aj|pKca8L3k=|mi4l)8krS7+r>8mNtf@?`M4Bm|n;L!fYjb-3GcG;s6%-w5w&IRv&W*M*XSOtL>Vu`V(>Jk8Ldh=P`xdEiWbS)U'
    '4&`90NBlNBYhQ)XT%fHQ7kaVNB#y;3*0XVyEKKp3BDd7<0*rxq!P$&54?XLU&$<uDVtgtky>FLH#kc3&=(`*nwOSsoa-iDE7ks^^'
    'QdTIdSLcM1D)*cda7;Sq<P!$M#X04YD%Cm3+!DIy<P<-rE1l)?oTkhfz3V}%nG@0p*Fk(+6#8<fYS6gLo$|4}Qz^glYNt|;CEuws'
    'u@F1x<;F+Ncj`(<zuc*%>{L8~)3Z^tH)rFEI?fMOY33AIN6N9idh0JNBuEBa`l$X>?$+@-B@fyPO71T2NA<00Yyl=Na&?!t?+Q3T'
    '{%c(scH%#%(J~k@1S57&&7-DiPWf}@MF~r%w#c@?+lTf&W>*EUOU^<6Wp{1tfVY{9Te1U}3-+rdk1m;D_#(S2Bq-rpvW3b~7rNkz'
    ')YL0qKuzI7tj!lp0Hs~-VFFR~N*I_ZIwcIKrBlMdL@9dgGD_}A(=t5ttaI5r>Y#_@M@<#tI^sCXqfJanVRu=4QJptb_I5Pt`*+mz'
    'chq!u)HFL<=5PBuTKOjRRWkndj^@(G)PZYmPZ`!#uP?VZys7f(j!dhGNp5BLvUU&V6+`9~@l^PhIU}M!UY;MrhN9PeMRE5;$GT+t'
    '#-2(`WJ5mK^pVB(L8w^80=7aai3OB1yg~^xxvAQV@jd%hlm|;zIzDh>KIVBvhF5;_r&=K@6gC#1n&w3xxQ_SN3R(Y_0ax1m0mF<X'
    'JH|ZJj!D@)R&YmXGjnC{nK_41y_}x5)%3p5%(5Z}3g7L_vBKWxMy5|{=(2E>ZnJ{dy_80`fkTh2ZnouJ<)tJ+xO*$~5dlSQl{4XZ'
    ')v?0&Y!91D*jz|7E9%@iV!U<Gv=x^X&Uiqy74bekPoI2&m(@z~1=8Lk(x|C5+sF_4?7qq|R$kPJ7)n!9C!+LQ6^dXI*~*Jb5v4m`'
    'DMFfy42Q3vqwJogL3|VAV5C)MwZILwoA=?El5KH+%R<}{%Z0-7PdV98Cfkh&w9?f@JNbP;!I#PzWu@z;dsx{;B&MdOqXc4g7g^J?'
    'D$>iPBbkq%J_)B!hW(R5K|5-3`Gi$$p7SSlsSp-aYn7<8ZyA~8NSqcW&>|4WTxhavT1u*V%uu|<R>{T`E&V3wIQ|5Yf0Bx2R&G+}'
    'SElybD`QzxPIcZ4O{3bk#IGPfm!21C40YO%<$RJ#yVECgvt>rK$5eiv-UzB=+JDxtkn$rdPh(Ean5_e4|MB^Z*XGCW;*9sU?jgHa'
    'xl03Irmr~LGo6<Ay?d;D51G-bz0l!qZ0vVB7q{E@CEQm7%Bt9_0Yy#C<6Z7o3(*l4s3p@87Fu||r9+#G^%YyXr2H%zq)i+bO!Lvw'
    'F?Y-}ovT(|A&|pouFe&4Fc(JT)wybYpBK|=-Sc8vZ8}~|YH2QEnVji)F|D@Ti)k)$L%w25rC9Qw@_JD`#W67Mt53P4O@<?V;TrW|'
    'Z`yeN?ecLmJ~O0`1?a~)G9u&_n}4u<KbP+}PeRI4p+COZJIc}enewJ5rMxNcQVn3oPboqA)X6hDRYvptx5CsFP&w(F`oV!cqFIwl'
    'puRcPRLlhna@2D2wORz%++9PBK4~!&$|O?I8^0FGDPc`|{^OzfWp>Ip*P?XC^TVZ;PkP?c<^wm`A<OG@mbq!)Bw4Ulb5z`TwiEB7'
    'Nn3=u)XYw$D(H;am5sE%In}vlcIKp7^Ib^(ptg{qHR<J#7c$J(!Fbc0YU$4NFcWK@_EbYT)#Uj-9{SluMm?QQ<bp*|&9fissnpI<'
    'P1@R1B~?~U+FH>Kq0Ar13Lj@nV&tjFn9Cg{GpwzF?84#Iv5zY4O+Smx)yn&98SJ~XLwr&qSYjSuSI#Ic&fcmF)RKKo&ve{XRiD#w'
    'pJ1Q0VaILlJ;&`H0|ZMyv)w~+_4A=(O`gR**x07Ce9d{yYo3~~cPg-*3a6b4Y^TC~I~5<dQ?VkSQ_&UL{uU@J<Q9ErEh!6h7S4fW'
    '74Ku6{05tyYY<&+_PP3yWn9Rqdp6tEb+W>V$+)^oRy@VISZ5w}Rxa18D|k1jOa&r(aXceD+m>3@-BMeFHyOUAPTjMmt_trN&XvWi'
    '^XgHX=DR5T)^T0?*)}Ydue;96ByPm=HlA+|(f1C`pGvM6#&i&=bLXLX*_I&Vgzlw(%$a#r1?)B0CG<g6DoUQ&me;CbTV=f$^;}D@'
    '$+>+t?R>7R(p<aJV?w*!e|CG5f0wRfHt~`rlTY0zC^H^{$B^qRuv=1(W8I@`!o12a(u3&bSSg0}On>EvDW~gXo%-Z*YOPc684j^@'
    'PfM<<kgE^!Zk@*Sl9113CHrn6NowjAJSHLD%dDNt2X|_yp(^A0;5!rK1t|UJ+*E^4Ulc;LC}Gs`cmx%{0gDQ{E2@L3MKvqiX@j{('
    'R0sPgSz7{rE;PtsYYmbqHGu7L&#lx1*Q>T*!>LS(<8<lcJv$X1WdMb`LS;ocb#)P?t_Uy29^plyz5(GyQDXe_o3B1y$P!Sr&BDhg'
    'eGt@hei4kaSLee<Rr4Xw4mGNK?B%E*#Z4kFJJOm3@$}ehSc^SWD!;Z#f?xC0t8Jd0m6h#b%kx^<F<ZxRO5VicIQ{aZ#xU8|d48_K'
    'e_bj_{A51G+F#5Jt62Msv*3-s114`HS7Kd!(j8ZG+3_5eeq9c29gp*mqT!pRg<qqo&BXnxAOM%=*~Obl_rVF#6YB09Z{!a#<HVzc'
    'vJ=wXsmM5?x<w<MP(?L+%P4{VT>GY3fPh0qqUv4WiCPn8$dfJyA>}nK{&6|9d7*XU<UyX)qMn^RX^_x8)f4aw<DS$O?xB{dNW{aB'
    '-Bs|tK{of_3168ZfgQUK&oA|yNFl*lgZA!8HE2CdWt5&&bK<03SGVoHTP($+uA>z9Tt{F^^{%6orsc~{N|uNIOqPhta8TFNQWxUF'
    'WiY66y!J`uoQ^}DR~@B%Md#9pYdPmoE$Pq{o{0cuN;%8>@LZQkrn>ZZ#92B-l@Vut|LOL}%!u=!YrK^d2bDL-)g@GfVTj}T=YWVi'
    '1-+3tK9GG<rP7!_4xQxwa;XAKk;}0+pAWbvYL8cg<^M92yhxwcS)h!&DN)DZOvm`S{!s~>4!k8E2mxhU*@NMftX_0j1UWV3IQY$B'
    'vc2l<Exr+prN4v}ysJ8rxl3FQ++tub+Yeu`@B*iF>oYGuPcS9fud>C4?=5vim}X6e=jny`!1A3(xFPkR_^>Qc%blQ>_(>UtqVT9u'
    'yQN;7vJ4vYk)797A<S_pl&vgEh92cql}Z<keDJth=5d{AQk$~WQYkv~{k!-4hUf6H6FHTic-xXwjz!q_itP4Ur&Hm+5M&2XqwClr'
    'r=qx;W;|<-Dn0~@&1um|ho%;D<~J!-d@AjAu#jg>xx#Ns29L5e7VfEKjR5mx5>Q`tlK%nhSmr51bM;D-dct|AI=MOR#asp|nG#jt'
    '?B^pQ(`kJU=!-jtPWfgo7k#>l$aMM?tr>PXqYaN+3H&GiG-7B*wC70Dai4ctnsuG-vzPlK9MkF6(_Mb$Tx0ulNG?ZGx?}u101mnR'
    'IEM>Y&i%((0L7dRqVa*0IR+jmHH?oLN69h{FURqB1%Q2*jVSN5t5HKvSNhT=rPL*7gs!6J+(mr=m$8Z1+Xa8ubtZ>S<~_bDt9So|'
    'azd^{IjM6vUo#(7$LFr~bhNFG{Ok6|)aC)hm2@Ri>Pg12qF(mpx~;!!-PsfUG{@lTa9N`&5;Uo*+25XIs8F9cV7J<(hx*8Mz4U0G'
    'Zs`bC;`6arSHg;L$58;y=jrC7YHpxvZh+!X`%#SMF;u8>j-<26x?@A-(7-%YN!Lze*)}`u0b^xEY3l5h5W$oIYoBr;>n@~l$Zb9R'
    '4`-e1M5R(w7l6oFl0^^B?Q)h3v@iHNs#D18R{SEAj}8fJW4I>{+@bK&bsRV~#p^h52V9-YIB<u!o9j4mYT_@*@dC5-0k=Wr+W>SP'
    '4hpFh596oiDzo*Lv1`<2a=Qicl|<!I4DAt!S@TC{dg=Gn)Jwmorf@o6(>Y&f?@RV`D4*0jU)M?Yqn1vxp936D?|iG2n7BS>V@oQ&'
    '%fUOB2N)Py#8+}U7kZg;)D*f0bZ;goeewmFpw53uCaB95jW~UTYx?l&zWg5NbuYh%nmYMC&YMnt54H62d#H)$_Y4>Ll@FkgA>V&*'
    'T9*_DwiYNza?H1O3~*`!#?Cz*@hwSp7$$tZG!}{{b*MI_z3(C(IZw921C~(wj^^BV3gEnp3Q<yt3-U!&>?sHaH!h>lk2n#h(}4te'
    'H_~{$k3pSq6X`Ga;U>DERnJ@xnx}1zc6=05AM;X-Y7!%u`cn{Pwuj^x+IOw{hg$OM6=F@gwaJJ#$)`IW=kKy5gJ(~)UunYxUl*GT'
    'SBiWH`VK`NktOP>6z34@+NYtG(IGO(%C8(MirReJDvF(#9#7%X_0pq!Lh~*1_^<DBDY0fg%H3hZM6I51K04G#QQxc*LNY!9!6Q<H'
    'FFjr^-PY!tJgwb5q5T$pO&jCognS!1&sqZuGK=mpoM+0MCx$wd?0{Htv5_?KUP<GH=z(xj(+RoNi&GNtAsDF1a}xL(zpEEgvnRl>'
    'A}5dXVRt|Dc|>h+ES@R_G3HNNvn03Zqk^y;$13;vYm1a3Oh)Eq=&s4?g=qjrvW-0F_BzCHHEN6VpYq9>$l?mdI^N?6mY{52f|d6Y'
    'V>0!5DAGPl%j#x~bq%m5m}IUD=Eb>a?K<yTIW=x-;?3J_lQ)-ndc3C=&w^?GE&<Z+ZG7gn2m2|uSLB)dI!$h77x@%ps@K34l^(0!'
    'eJWu<+saZ?Xz|LDx!@6u(zy_UTMJ`&>h;R9-Vo2+DLw>Z$;*UmcX^dizwE3GPxXKE{$}oFdZ)UAZKk%K73u*9)Kr3<j__6bpo;sQ'
    '_L!HDnzd<vFAeX&l)90x*%#FiR^G=J0l4#E+ty20S9d&~j=iiXb4j!^=cYElH!m`kX67yX{^iolpEmP$Ka9{rV5cTuy#OBurYA{N'
    '@&1h3{K6csp7f37Q4Z5*-c;2fV<io|N@ennpueMZ8MU!@R@}LqjTe5Go4b2?3Y}mmt6s^r4#@tiaAfYC>Q$ewq<j16&A5Dc`SXF)'
    '<W<VND+D=ggp}UBbDn<wtcvU(&!3fvrf7?@X_0l1d>WTmQ|T`uM`ao;+?mTnb;^l5$wXy6lZlhNQzr5q8?vxd_C9bXkGO=6uv1B#'
    'B#|-sJB1w|J$pC3I^`QwQVcbruBBMU#<`SY8PX<C$vv2ahC)I<_QaDq)r_gclM22ko>YRasv#0GiNz{bTMFL9y`7VN@JeD?N$g_J'
    'do4~e86LqF4-iUP))fG3V4ceP0fZYK)L0?3Z`t)6{m$ze;+_GBdd*RSPml6m>pB*Q|4!?}k-Nz4a@-M<<9?#OTz@|4=>NL?Lxw-S'
    'n}*lFe}6OmetvUvdwcWl?aP;c{^S36{V)Ia>doKYynHpi{=;AX_}AaRdiiqvYs8;6JcWGCw2tS16`s-Twb4!N+TP?jS7+`(uWcIv'
    'S(a`!dxZF9*KX^Re}BSN@Y+=;zeUWAnWUVrLY#6j!`$dKb6+h9-1Hl-G2b;^bB&Q7Qm6_IRp%G%nJVTRPTC=Mz^=WH#ljtn=JeaW'
    '^Zl|$|G&xxA^wAxSWqAWe*I0YOMtCNm0D_C4v8cx!|BJ=`H7nvB6V)6>q4NigQ<p9E$t<!Rc};X6#_LSY&C9`0I?MVqOa!MR*rUO'
    '`tA9c#1**yJh7<HB6p0b_U`uPl)p|N1g54fTdp)$qH{^7tR>7|eRDckR3?Lj_uPi`QA=C+`6Ax9e4S9VO4upCROW=jp;=SKFy`eK'
    'V2Zhf9!(|kd;yk+o{a|+>exc4-O?WKYV<+4H)gu5J8A!Aw^$;ix1tSk&I$+$O|eXfDSl)2@lSac@jCs-Tghq<%!~g84%6p3USN7<'
    '8D&-dIvx)GVwF8->a*WzmfN(<`kOCKne3RfI#kM+G)zKS)0%l>X)<@@^=+4V|B^kB%y$0fYn|r2)E!TVql9kPvfMgrE3oqo(LCgq'
    '2Ing`I1ckA6>BhcRS7#Y31S`hPtEGv3-4k`0N3b2_1L{lYEYd`louN~L96iXZ)?m(r|mFKQ7@?+cnn-e+ZeUfOm#=?u{sEODh(x4'
    'X?K4yHvwXwj{WezfNGZCjXWZ%uJ$8d9<ftBkQ0xXD5h@yqHEIq(1&$Fl!6@DnvCh$QO>Za$6t~+xs=y(_5S5-7pE-=6X&X;0h$#J'
    'Q2B$Z2Xpk0^=Rj-9t`Wj<PWMIEbGCh4?@+0I(jHO9qKqi?pbh+58cK4>JNAqyD6EeS6`QjXs6^wFL;ZZLU*=+E~;niW&c&otE!Tu'
    'Y8Z?^Wp`AL1Fu@N`NVL&W{_RKsICjhBn}cI^22oH#vx<1apUBL<m$M?FR!(GW6nluR+bTaW=^z}PBH8A-d0v@I03g&yW?(xfjP{5'
    'a-bANJPcnPCXi=;(l=PHFSRkZ=`Xv-uC|PhTbaqh^PD11@O4Dz$XYm##V^UkYjCMwcAHaH-rFr#FaM<tRD>Qd>=rnK@1-qOm0lFi'
    'Y%2(N!M5^k2%=ULH@ma6rP%K}?VSGF7UeEeku|v5oPVLVh=)Wd2hf;DXyBn(|DvjBP?x3q^4kx>5&u`2=!HIIYhOb-3{wZG<b$dn'
    ')&j?JFIW7Ae_$2&UjL#ix9olQlw0Y8V{fM?qICBK-)<UcR-Hq|)T(}JuEs6wklEVXU)}=}YR2{pve<9}|2X2#sHx_@zu<nw<aWyn'
    'A=3t<Xx)B1rPu>gj3<Nyrg%na`+=4|D#>DAS9y^>p<eyBKmE%;|Nc*}Uj6x%l;SVTF#lgSZ|8UaX{LAYX(I}R#XSfXEKVsVW_#iA'
    'jbBn>*B_{1`+G+!!&3C8XwEsz>+ZWLBN|tw^i*4CPx0bD-iy59qZ7@`gy)X==qhg!f0>A`cB^r`439#A=f_gZwZ&ZU@5=8M>!&Er'
    'OJb-nRj1EqB{T+q_e(>J94S{Tbp@|r{*RjvZ}2$%m*MRX%We2TWP}U#@=f;XR>k|^(yfj%Advsk<r@&!xhryH$3G_pm%<-3X#0lb'
    '1D~%n9bbM57oiWTI<9fv1B*zDQg>;)LDY{>+vBMdd~p4s^pa%q20&(=pW$4!mWx_vCtqLk83bXwnJ1+BHFi?Eg8>1EOky$^fgn6H'
    'Sl9W&$a%WM&6)N=cvWdD+k7G~-5#pSet(zD*PW*X(IVd@Ejal_sJ-F<>3yaAG+exGm&RzgImjNksHq}}`Sa;1HAtZvEA?}3vFC`U'
    'y(KhiMjj8yRV5|qqOrmw-<}@%<7_|>p}sDiOl_=+!8bZ_fLgU)S!v2_c?#*bnv#~+rc{1(2)StDt`uxOqKP4Rgj_uF2zWQF%`myI'
    'gt&<6e?qRAqo@NyJ1hH={!+0?dv>>ljHp#UaA${I02mhk;Oxhw52_yg*^e0je8oRF`!R!b9Mx;RC@A@ao23c?>~YUM-6hESz4&7D'
    'g1KkuA@;PNAmb^oFvt_E`=Le$;B5Kc!=7MC(m}QP-KCFIl>P{b<8KT>$u^6jG%5Mbg@jU?-_OHAJLhF8e<dL@XGKNCyL766fYCcj'
    'Is|o++2T}MmOiLD2&c%pkYh-{PH79u`i_=UPTTcVnV8#K)dD1QRxf1w+WU?YsOqbr8g)z6S3#Y1Diz{g>L&^kx^FC%RE)V001uVV'
    'l(v1L1qc55M$^)%p4oBc!XjAuh5=^MH+2QF6MpZ?zEtv?Z>&~rXhxZi=I`?3`-76THpjAmlZrXh+Ko<YPv00OwD)iLftj=B$MlR`'
    '&G6>!Pp{wqkX28an{0KB_*<OGANa0DrCEhxCFT~B@+n3Ay5>EuFFt!-%q&p59wcG_q}Ex_-J5i!o6jjWuTsvn_ZQztUY|bbP&w%$'
    '8zH4)?8b;>9f#UZQS4U_O5Z_Ja$fWv**`GwvVe%lV^d}XjF-HOqYKx8P6&X?I=}nnsT;}s+e8G<dd~`G8I5Z1jFSjPUc`o!Hl@Bf'
    'XE1fDBztfRM$2!{Yf&xn(vmEDWMpPa7vUtq^cjk=>h6y1X5bQ)6|}q;$1`;L!pVLl3$@x`V7I)yhujhh_BFX>9PDp8;n2pI6mkpx'
    '7udk4D+agMSqQnlVoeWQQeL441dWC!u}@TARImAA@7zjtq-3mD3GYw0)SS{oV}`qJC#&?`hNo5GZo?CRW_Ma&h@!mH@U%u(hUc?d'
    '>BUG#<YjH7Tk{1#K>;-sIgYe8aaRxXT|*dSZCY9v?g3&6HX(fM=HWasW7P)TGfiy`sRVIad?+>+RhB;>ta@ZRoh73;oZRkn<fas2'
    '`e=aZ{imC`tS46^JYaZ5W&b&Om=ntD3yRnC&F%E=r{%+|VS0aadT#p5pa1&Gy;<J8`|z{W|N7(4w>M<R;f-oT53pmVaVJledv=4W'
    '?2W4nfAhU@%C)OXB+qKoZ~uALp=LlL&$u#uxw60}V)`pH7b`nebbzIK{J?UpY)RoIb8g!D`Y^w_{jm3CH-g)D$?aAuV(xaP{*1fh'
    '3Tk-LGHJFWn{ooItsRFfwS+z}UB97AP$63~?lUeR=(BdhpV+Crx|7@M%RE+hGTL)^+5VoEJpx|Tz)tcAWC;lJV`O{<*Y`E+oYO;S'
    '@KUu$F|(Il`l1G^^sGsVZ!$-9g<u(TTMxl9_+&_z=PfC>Fm^fT#!ki$wYaOo>aj=yB>Lqqjk*VAE&#5rV=DP{rMVZf^jqOar`#`@'
    'Tk0et_JV~<iHCVroM}&W7DZ?A&er5|;A58+yZ(Xr3Q`mc+qcr|hR8~X-g6?mQbWIDVa}G71zlZeq}9z6_h%wB?fhnzqKJc!ZIW;{'
    'dwukmAr%1_btgItCpycl03mDl&>2wZI&>Cf2hA`9)u0)UrKN{vNKKy8nS0vf$bs?!6&O43lL$ZK2em0oobd)zRimJj+z%s|`jBPv'
    'pz$AD+2~qQRNd1ZWM3o?Tje<i<{bMX%-a`LAHGJ5wT$tjYT-fe!Cqj}eGR?ObKc=#d-pUX2%4*V8q#ac<?A})m`?D#CxWKKO58V!'
    'dpTzmUCs%pxD!QZff^;}oZGAUSbo#xoKaPr^9rB$D>hta5Red6%{pBpX`_lgNgHdWc6?e%>vC8W4bx@b(cB?TV|qiq%XW%iWWhyu'
    'W{ytuXvy8n9i#7Z$LJgGSZFDTGc9E)97C5oMvmU3^wm4<*U(ZZv{Y9hm3z&>fJmrt=&id1+hrBfry5L$m|H5p^QL%|mev9t7|V-7'
    '*7YB)8cr5>L`c!YiYdh{cu1W+Ib$`TF%2gl0{_6aWdPIpQPXv1+4;rKq_3T=N-+(r6jRJ`L%iNn`I)b!kl8gFYSP_$OA&Ztyg<%&'
    'wx!-uSwLtpXD^b{OOLTC!IV49O}!dSQHsh?G*7JCPl@A1DXNTlcFm}%a@O$^l+0cCjB~5s`y(4)F)a0GoWSXo@F=(v5uC#>oSD>q'
    ';mQf>_9dY-<=C6drtHOo+}E(FTqQ0d*rs|Clxz!)WB#XS+d<9+(&NLyW~8ls@lx=%@J-0yZES4!R384<a?Yu0?nR6yHQ9<OBL;J>'
    'xUxLiG-~^Tb4lR0u`jkbIjO2XV!YtRk|X6rpsF<rFOU7BFHWkB-xc1dvi_BH8>8F0h+nhSYD|R@qf++5i!hcs^s0wNz^!#u-uOkJ'
    'YEkVTzM|ClR6MdV`69~2-L2F_GQB!VO)Su8jmZ~Pl2_d1OA=n4YDfjvTgJ#vSHV27XF+Ax0u56Kv?{~4BV3r?DmS&bg;@lv;G3rO'
    'auQXlWKi~ZHs^b%VrVS-yz#omCW*Uw8MQD?NEEjW>4RS7_y`0uHY3@TfQ?#JVg1`JtFEd>>Oyl>XTv`M!M2}F{1bC^;g_lxC$B!K'
    'dLbPLH{(r(p}AJQgjR)<JVK1Dkt;n=YCe#u_dM36?5Vj*QeBqkd)iB6Y@|8V#mq@ElK~*qW$YNW1SSmQ6I*vO3mc=#h8O;`45xt3'
    'Xm;<){!QG!$)rjPzuQ$7^Rs_ddawN0*5y!HsC_h*<CDd6Q%gKgD>Tz;d0Y9l7w2D(&98kuWy$9pIF<&#wI-bWq2^@NM^l?>DH14I'
    'VkXryIzrUuiTy5y<C!Bou_5WQAsGRt#OoR76!-+DlQlIfD?EZjMaf*x$~NgIvq~%DJxt9i-&nGFZ>_G$Om9ytoXjc=prT&t)MRRO'
    'HhGFZji|r%O&J6ItH&5@0@1i&3^o<YNQ@yo@ne@83l%tdw=}e_7u%X%^rH3Vnnq%7jwdqPE(*tNiZ-}TAa7R5ZS3J<6he&^R)J*Z'
    'k|ixRG7j(^qjkyEuSAuuN;{cvwkWt9xD=gaVOYwo7wKMKV;cCB-$lc;A)<MqC<4YTJAP^Mb9$bf^-pWr=^R@bovQA<)W?l>wd<a_'
    '-=ouQ$atk6xi;p!(r{cIbH1rSp=$R$q}*QAS~9<<MVk+|^ZN%^KF>?817O4X3b;BDo!yai2b`<kEw=oqP))v(QsIzsnNv6)8hb5N'
    'J9OVIa<R%{9EsPAuXBt32E4|_$Q_hHoW+SxzQ$c<_{JvoJh`h_3R&XdN&0Sy<5lSC;9kpyJ}aT&wL8;iMZdn5It_h#Q~iERx~K>o'
    'a4Z)Zudh0B`s$mC47|TG1!P5UK3v%XGFJV>c%jBi9()vo6yH{o0(0Y9T;i>BC*fz~%%P6UYdAru!}8>r69ldAq3~cT@7_FGd*nBi'
    'PeM-`ri&izX_V<KFN3?Uq6mHBzQDl&P>3)1`u}I{-FhX-jWof(GH6IZ2`deFrx6$k&|q^H4QbRum*!<(5)t7Msw3pB^JJB(=GQOH'
    'd2ur*>3$+3;$-DR0TssMPUppFX8i0kC>wF%n4e?oSrI^>r`&TogiGWF0zKy*H`QSTbq_(b@t3KHOmjZhzoHjJuE&{lOTTmKUclQ^'
    'ewIi-t$n>9ebeZ?_KWhhC3EG<->cBNa^=tTpqzO?%7pb>Pt99dg?9GmrtS2l`EzTB&Rj?}5j)OYG+jo{+_AK1U7Z|k3ag6Im*mZr'
    'KlBvM1@3U)!}WZ~(+>Rh@35$z9QX=B@D^*#aBKmr#gUj0vu}k+HpiQ+VZ*VBG^|N;4;h=Nmr(o1c8PDO14lp^i?$q>xGl<fFT>Ky'
    '`sc>5<Wmah#jLVbH3IxejVf%QaDP~wStzd`hF-+?xE+>|*v4-IX<`cyJqv*XX5#<!gLHyD2@3;lf@We9$-2{`W@3{BSn6DcpiB=}'
    'iA<sYE_MN>ut40ER(HM(J6!Ud$fOb*Bp6EE_O^{pjM?6|v58fC%TMM!yt4e%otK{~pX$`^@{<nsG=$`IG7BI9MPX}76Qj)Ir!*1M'
    'Y*<jSP1xIJ$gsVMO2a0wzsZymdz%dJxpp?0(vGeXxN|UCz#q$dppU?fA|v+p1Ky?W><6{4j+NUzrIe>j>2Vqx;r{$`a7nSPicG=&'
    'zQVFTdxIC;-r#9r_N)LcclC`{VsCsk)4q>WNm}dOt|agM;VWMohFEhs5P2j~kl2W2d{F!l%G_q0BDUZW-8Kw@O+pik(EK6ZG`Fr('
    '>4G0cyXpsUR<Cue1RMCRU`cGiSiK$}Sim<9*d0(59v@nWW|FX5v4z+`iml)RHn5w4f!LxJP+VN7)M{>&BH?8kjbfpHy^dAH7Mc{!'
    'Tm1C$tkMWxA!r`oW7>*{^}8v*XO0^#LQ7ap6&%f7JLt739kfibO4S)qr<$!_r^E5s=K_+5GSAW;Cpe4mI3^6+v=Mf;=?r%v>t*|_'
    '_{$m$42h7U(Ci^8_o+UF9A)Jrt!P8}Tt8Sr>G)FlAj@8}x|!^(O}v|2Yf8=EqGTHmekw9rYDV{>HS=|X{W4S1y!1Zd<@H+sSo$%l'
    '%2Tw0)gx}1P#O&C)kKkzuc6tj@q@`K=dZQnb#Lu>-LKMpCji&1d(8LUT=&+i=Gv;R18?`%Du`dlN`XOW97V4X8;`FEy7AfSZVUwM'
    'n-UxreGo#UQ!E=}N2!J$_ysPp3)N%7V0Lj0897PPPaoKcRR)$a#H@DeRi@HumIEtWCC=_^nc69P6K`zS+o~M7&e)vfLB6qQG-tVP'
    'Ctgf>v~?{>CQwH2*v5?`M$WN_5y{U+nQiVSo~T*m9JJB@B1@`-!Y}Kec~T2GMbnperjpIMt4m4nC;@U4GOtMbXFzX4!XeysHGm3b'
    'HGpGi=|KAzC^h~mYaEyD_llqAmz~%k6_(C_7fr|XyBCB43k}NpNdHPYz)R6?KPWP@kXaqnec{S*IMpsN(<Nsj(&6)pbBZU#>{AhT'
    't}0}ag#i>P$~3DsPOC?vaF8{PqRwudo+#y2Y-9x8a@eVQisyPN-R-y(I9ZWam3@`#oOJH#qRh(CcJ$T^x1+ayy&Y>;ofz*&o`@YT'
    '_l+WeFHr>VSmlX{1V_CiaMFvv?<Scpb(5^B&jZnc-m~NrCW3`4Gmg)F18U$)Kn)YRM^{50?7*O|+aU1tElH=Jn>cfQyk+`VH^#6i'
    '4iJnSO&Tg%N<v2+e&;b!WlTVX)}=a8oq~zveNv*FZ;4HSh2Cj-z$jG=0+VQ<nc4#7NGDG3R@BU~K`If|(=wo27h#dHjAq=iRX>3C'
    '6dK5^Qp^|cr`@8=kld6*=+GbCFfl>eGBL*Oc(P#SP(32lgX-Q~DK48rwUOtfO867J9Ip|ZyDL(7V{>Sj2B)8?^$5_W<<{Oplb2in'
    'EN#uM(uP1`2ZVkQMQ*ILArOLXb?6a*-7?RjY`~CeyAcZE_3j9Q<i&xy?}BrOvf#oh-K4=F#U@I$=6NxmgK~QT=Ae0gho08S8?g;{'
    '50<i7C}KpV3qK}`pdTcyUAH{(P0X+6S|&Ia_yMx`0v5^HM&ZRq-tEEgVk79@+ff{zoOzjdfOrzGsrQh05--&{>3qBi$2c|+L~QZ8'
    '$ask{>rqTJFD48r?u8{WPQ%(zj#^RLI2Ov8?@0Ohq;e0P2nyQGudp@II@y3_<t2{Vcmv@zl~%!wvTaZ}%F>ZivhuM6fQ2I4ym<}a'
    'iml`T0EVKr>uU&CY^2Nx!-Yav>-j25WedhBIoM=fkced7L~#y?9v(Z-((GKJ$&BdeWCxdRA$h4ESo?^vfnCQv*>%5^o)-(6Ri#=r'
    'v9}Yo$H%~MXGwUKofY-&@M<jU2O0F<q$GUY#>p8ELw3PC*$bg3FKy%wJU2Fpru570Evc$)yt22-Vo{oUj1vRYq7;Y;bQ1Eu1Y#ib'
    'Bq%e=TSi%Xdshd{v~&h_q%7q#IQCAgTl(%q>APJK8rbFfLL%N|iA_Cj6)S!{NO;IlW*hJGSO(CA#{H}^PY5**_Rjw2RL9SA%G+hl'
    '=df?o>t+9qVK7o9<oIA3f_!`$3%<sWyiKV>=mh3+=T}MM4eUW`5k?B8>|`u%Ks564zx|Kc<LC32+_$Kr_f(YDBa$?f>9+f)`iG<R'
    'nJ6=Rs1vEp>*izQS#L(ij<)VKmddISL4)a#+Of4n*e6gH_*pWCWS-cOq&;U_{qDD=I1R&cNDVU_iy$=^^n;uw8Yo=jfkP8og<ros'
    'aJUAE^+eO2qBTzLzLy?{bH4PDMyyljd$zcd>!kUfE#8CORI|4@*3zt!DyY?K(uG{#nm2lo{vJhUomtqk*w;z>veKhRnH{<VCb8&H'
    'Q@s8Ww3c|FTF5xHWr!O`bKoDg2#se+@SfrE@@1to(6D|Km1sBx3Dc#f19IaQI<f%JzZP`DgWXf8R%mX&H~zd8uyz61d1F(^_Z3w#'
    'GT#qWvQ^?WRI*iWVCI+kwptFZ2#VIW+V$0XUjB@NU;#6b^^F_^>wU?!F;U*uc3^f{15~|j?d#}m>&AN9x(>{)3O!Zale}*t)G-`N'
    '2RU{%-$oXhUvK3)$RL>MLk%|zc5kNz4n#73@%xIhu%Q7WvEAr|8pXmg{6jj~5&?0Y5;xm!w9F~G?Y|jhNjfzM=H_kW^vEMGTh-~I'
    'I&nOcfQ1BY83+Tfp>kZ>za2D9SsKnlvu4Y}bgnsm%DQx%L$2p9xK66qkuN)7xg)qNPkc$G*hyI~zC-*BfB*RD<GYXl_{DxYe13lU'
    'lKE#Dp`f#QN@`(DJXVg-kmYI{+@0B{-5<+qhQ-XHP`=6;wGi)jO2S6560f4_GmxZ)4K%&(l?Wwym0oD3(P+j>)&kzJ1P_w1k`;;P'
    'H>ebRB9V-rf^9yn3Q%JUW<|~S+MewY1b$F+SI*}%J@0)BLiPM5o)?6;&_B*8#1A%xJ;#5O?4deV{FIZDn#;AfiT0k?mC7;@ud{MN'
    'j1X%Qfe;nLb$0i~aGlPl(t}c?`qRHv5Mv;jSQ4o$US%i}VeO(zj@j;z>UX6DEwk{zo={L}>Hx8hpjMkJ7BRBV(VEh+O)YU*+8k<|'
    'a$JHLu@<1LLt9Y)(9&xwQsNgyZuMSh-<wD|Nt<JBQ@_!f;VYbPUGVyMo)!i@Q6C(<VS2+d+3UCj0A?7(f`lC{kRh0e8-*nWsL8GA'
    'P=%IIlbhTSLUZHIFV4e?PspqZ>|zti-0VP%#C*XJIv4Bw>OE){`#iMX9+K-f>2#$BMm5i`J<Uz*Z1pcuiuMK8whyuVAx^W0w1MH^'
    'T81g<_=qN^)|$WAc?if&Cntbo_UN4PZ23!q>GXp>MG3*JS~Z6=1#7~&iB4f&{p-6+fy?>t=;l1TxC@>xzpVDa-{$|3@RyJANq_qE'
    'bo$fu{^|Mo>EnktZ~pq{|NZVi{{Hs;Ki|K3dwTcp|M}<d|Md3Fo8$KZfBIwT#waZ#iu@}WlS+&@i$amZwwI-Z)}#F$Wot-4-a{mg'
    'F_pH4ksVHPET%FR<`viu<7=!O1uvAaw!LL6BVg$b=|$-K;%Y&c{yBO#b56wfW-3B*e&Xoyt)+w;6>mXVAgTSAJ2P!hnQ1$|$4f@5'
    'k}A)CuHEpXwN@4*XqJH^OG$?Mgh1*^U*Ntaa?WBZ-?0kKs^!dxG6qjOlDt8Mz?uyjL#d=-Ay?=De$DykPv_H@^Yr%e?(mQ2)hGP1'
    'JP4>NPIfo}f0o`#sYkv~l-a?_RlWzgRdl~-Eef-n`thfEV{ojzlDa7}RsT}!<|;AY;ws5OXdru-6QZ~6`NNmbQEiuTNj755G~>13'
    '!-e+3upKWglL1+0%HMat9DM1mUDXPi$flK+RA7CeR+OvglVzQ7@^w1l+)#TVVa%)a!RvwBsH9&mjJ0t0<*GQJRp|lrOXVDLc^65m'
    '<;3QJRnngEUEz0hGlh*&4M5L?(|vDJ&nDlbDkQmCf0O0af6A^?k^sC{SB6TZ+o~jFhsV+a27Z!KoH&<8C8CVx(Ovv~LyObJm4Q%h'
    '>u^*_DKd4m$PzWrA+0}o-}Cz%%K42@Fq%(rtYi-4NKr=Z92?4t^)bk<DPjY5qtarLvA*Cf$AEI9JfFOwvFybaJ552`oK}sBe{ftp'
    'c7;_YUU&*AUO|$t%;1Mx=X|-)$7sRAZZywDX(^V~qb`U0CZ?TLPE1qC3p8>Rw50rZm*br+H$Bxp@M0o94%4*6X_QtYZ+)sQ!uU+q'
    'ninxp6WJL0Hq%9?LVJB<OB?eV!5pRSi}pqBmJ@r!>9|VCW)@c|+N+yJ&ijp#gI5VU$M<k<tv1A>bQoUPl?7%5EBiFBzQqSblAvJ*'
    'UX->7y-e$+ObSRpz5kI^|6}81xHr%O5=!hk>VIOGYN_vQIb4p#axe-yan~b_2`i&jCvJSCao5;}qq3#;Yb2dAhC?4ENvT#DAXQK9'
    '6P++iY%mP)tk1e!+awoPJRg2$Q<gYsi}1uee&gt)=X^<iNE*i!&e5~A4L=+{PYBF+-=9A}9p0HQ=byh^eNC^7Cl}Cvh#z0aw+@dt'
    'tQ)7zZnzIWzCWHnzxky;pW_^(W!laTaIJ3X+f#Lj2M<DUY!ILwgb;2RgjG3~Ns4nb2#oY74niPr&vZwR9Ryo5d@E{c!7|jID0j;^'
    '@al$>xJ>OhXc&)!(XTKLO*uE!83(Ix8HebTvvHVfY^}zj#|TzrUcACMq+-@}91!W*><g>_bHg}*Vc)3elYuFY(?yzgjKVAI3nye_'
    'dzZ74aTjR;_x0Q^qIhnZyJ$g+hxUwf((^O!Oh(fw^$H`kD*B{|q3E=@VWBu}`G$dG`~9?t%t~?a0y2;K{1wmH9BHdPu=bYkUs0h6'
    '-zp5}{P_F*YfL}KUnbY8_5g00e^|}GSMB!)KL4J+J-ovFdk*oOpmmqLyk!)c0y*Rh5jIBE<vFx=mRGMa3ejX|s!F$Kyw|HlD)uGD'
    'yh1Mx4+ChrR=riX%#!uvS#pZcl56$2ci|Pj-}96AglL(1b>#gpRju|CJS$YKP766>{o25IHr1TYcKTEYDum1?nsK2B7dW3!xx{>G'
    'gkUe*c!?};P=S1%TMUS1_zNmqC}hIfq4QRZ@g|#?iHffHwUE+!moyu(hD^mKBzLyBwN;qz%AU_(4rz^xV-fKB*b@y(LQ2Oi+-(KU'
    '0G5E15a&Q1XBXZyt<054<X9@Wj<0pY2;<CY!-{sqpXQCS#nP`JB{U?0px+><1=sMWA_U@|^ZQLiWvyx27>#ypF=S$kvKA9mS1T+z'
    'x!U-{_2Xp^Wx#;@N|Fv(qRi<q?I=c>v%0*6%!hr4-UVTs`>T10*Oy^ABMLbcIYnzGfvZyyWZT`MhJq{<g);+GL7W7o29=snX6c_C'
    '>Yp^(2K8y0#29ZK6kcj>MkF%=8x<-Ja&f}buobTZDReBev*R<^+6?sOx&D2L76y)ro-43g-Ukb`56jHuA^|F-+}CC18dE25Q1o0)'
    '*zuS6RoO@cuX^6XHy_HwZ-KMX&z~asQ1DE>dBAy`E!0XL1)jO4%Fq}Vr>~JKcus7<%zJt2sKM~R<|F2R9X{Eg4)30(H$VL`|FJBL'
    'OtpYKfoV;p(V)sSifCk*#~`&(OJ;?(8QgT$+CA&iPsNx`)`ePQ1Kn=BtoF1><ShA;)3~qbh^ZY}-KETRO7qgxBHyK?_niIp?>YJM'
    '9)8mqkJlAdxkg+WXJ6C8GEgk#rj4?d+4=jzi-oWQev^XUb6^)KS~yk-H_*QhJi}o1Z_yrFc)bGl%+R9pAnzO2ydna*K*_b4zT%`W'
    'rc`{EXGs+}s6dVeErM+NvB)g#NN=z0b>vVwB842;92((V6kYYSSn^t?!>wB}EDEn-)YDl1s$=8QRR5`TNij!Qe3#k)F&wo_mnJ<N'
    'q(=PJ$||Uj*0g}$M1XHv8lJxb^ohnT_zJDR!v2%0PR6Q|gCwgDNt2dIw;3dH)udle<vptmcG)aH>DpM%qKjpsW9cqVnZcN;pZa*c'
    'o|B>IIq5eRXM!`;%R<3>=;!OoE!$Yj8hxz+|M9xx(b)dF8y3}!D>8AU_ST&e4Wn4bWoRT^8m&8(VGnuT!B?!i!v7PW#m=pXnCns2'
    'GZ!_YktkH)M7y1=&*E3mB;_cx<5#5{QS{i(%w^M=1B$GJWvUhDM`epdCGv>=eY4K>xHcDwGW?cyv_O<qy9-3wFkT?8aaZc2)2YW6'
    'h$$j|>>2t*ujvB$ic><?Q$l&}GNY|Zr-$a^#FNo|#mVT(tAOYH9O&o5LY$#Z_=<DS*DnfYDdn;@7{cL51~S^0*rOv!nO#Jdc#Ai6'
    'NK1a;E28_gWC#9j?@?o&suk0zG@mKTW|%?$z(;DOD-L{Z)|xkYB)yG=%u0J3OWU#L)o!SHwQDqQ8E`jNyxLR6Yp!JtoC7{}GE!n}'
    '-dBZI`&fi-2`t?>>3+U&CGSZ<r#iW*zDoI~+ujAf(eTAV(wu&rX@4E6U4A^b{*&gJw~|z*h(?!Kwqf)|ukQW1blwO?enNS|vkpS2'
    '(bzIFk`*i>ybQ(tFp?ELB58X$JQ0@^dj=s`DK6fsc$p(DY;M5|C+P-?6<csu4DF|?2#nz-Gz}X@p<9I_<4+zrptd5u+E}+YG*0df'
    '4KGx^>a+`c<L1rY?E2l2h24>burYXXm9Gac9z`z*t7|LF#>%t851lnD0)e#MW|LcK_JaEw*^a3CByPUVaP-6NuB%lPdX~KSP(+*)'
    'QWKF@R99R-6g3>gkUHJfWR2cg@|IJ6cb2@hTYiq^o2s+sE#Fj~6>SsFF0YQ8!n@jfx%b81?R_zf2&U>cf!q70An*50!EMbzV0$ZE'
    '@0Uwo{BnfTyhIZ?`NDR}>^eA3D;5iw+3cR_HAQUV*d>yp3Js}<7}p)8x{Fdrq5;;o;QX14$$WmEKE0S&=l?>rTZSxdpu|4N3P{r!'
    'rL(@%goQDkV+)Fe^XrH3g)Nt5JJlB42<4-M85UgaWA&?{L5;LT^rHM^mYSEfOFUI`Hm0D6pb?dRdO?W9Q>ZQ7H=SyOCZ_A7S#*Vc'
    '@1?)0xoUju)T6q|{3@^>-Oul48t5XX=Bw@S{C?dkljW%KdRT`^d();}*RkeFm^5iC%7Auy#8Y;4r)yNl+j0t*eTya9(^Xb!VIDkg'
    '4Y!E2^`gHHL_;njU2RlH(s9~+>XCW3V)ztv3jB!TGm7l`#io6+Z^FX$?_rJ3m%jaba6`U-oy#$GA0Al39Ig4Hu^5wk<h+4UR7Whs'
    'Qmm-VLBteH>3Jq0>Lq1sgsSvwAZaYobcNCYHK?6d)EF}VjP@+(xf?VwVd<i72flo@rm=n}?ltbGI_{~QG|8-^9ivH751Dl<s6jnX'
    'YFTobKq#M9^r%|%2j#1Ty1g@Z5Ss@mB15O)z^1`5)C17IxIm{t-D@Cf6adn_Lx;;Fiu8jg!G~dd4uHk(C^@@^hGAYp**3Xe;WD<|'
    'y6DE#AlUKt31Jjd3vGdw(!-30=?2w;U{i|J?{^v2%P|jYko?O0nJ(@i$(8v7<}|4F38!>(3<gz*H2=@PawFNCCP8(My7~k?JnDkB'
    'k6pIGwDp&`86IjaI0AR%W_YmFYqK39g0JhPQl*#nMF>V6+zZ>i;F>X{3ym!YE2Mjk0bjUA&ZxzSa>v(Zv}N-gh8V>tTVoXCPhsUt'
    '7{SX$QWX(py4KLt?$D-_Jp4nmD{h1sgG8fn;ZM<SGOyoFZAw3-7|n;l+G-<=h7pnji@&SxNy6L|-^(C?%Cx@M6I<o66?MVB?bMA8'
    'KO^*zDI?0LH{?#=V4D>rh!J}2I5mEg5oQgWscuub*fC;E7->Y0FcPwi@kO$~vTH!PY2WJP=&#-S=FfNjI<y{B>6ah&%e#@k6lLL8'
    'vp9LZ1?o6OnHkyNMgT)H(5qR4v|&3T`Pinh(o>8jL-ULj!}?WG#yS@0%cW=;aZ9Hq!>D-q4R%zymW+K-OrgVZxoS01{%W+BlpKI)'
    'h=!8s?mnG6Ubm&p9^T6!OE=YuQGh5WtYXORfcO(B&A!g#FjAB9v6ujFjIr7RYeHRbZw98}BftHi%C~FafwcmME`c>8Q~lRf7KuSl'
    'w)Mayt9Y4iZGuI7FZpy@1x|Z4@Qoh%>2NHcZuRP1g63S3mK3F4FAX<q1j^`J2gj8$JMuwu?V!EPJU55}^rR;zdKGIV=+-c26*XfM'
    'PpMevESM8ZgE6ubg+G=*4_kJ<QG(os`cB38udX~W7ia!sc}tt86N;!!)5!-dLIUXp#DSzS7ImcLFjQewVj|k|jAEN>V8SL>SfoeT'
    'L@d^F+ih~SMP3gQ*3Y8B_s5OB9UrR7nnuwtGS<D$-M}r~GqroJXF<~Fomr^Hs38g@CSj0lY!s7-!ZvQd{2>hD6-L3DjKegqg$5S6'
    '{B`J9nf$NU6@*#G!mwjnv<^flB9aIQvc2lOWzLTI!ZW_b^#id+Uxm6iTJf4dCme!0K3dsPs4>b|qC4e?HJb4ptV=jXaZ4{-hgJj4'
    'A3wFwns_*Jl0mM}wOwOt3|2|pGmSOlC1y^ArnN7!7Rfm&^@BMvF}>|DI(agE2Rs^ZS4|fT?mOzNz}W58f!%k^vspXIFPfM~q64+M'
    'dYQ$ytm#re)#w0&c)LMp-zz9;!#UUIEV&cQOEl5bX=vF`EbTBhVI=c&Hr~ndrzlPlZ{{ZaDVkBl&zXZK$DdNUKByVS6gNWhMpl@y'
    'Ln{mkzp70Fofyb1!(B5D;%oTfr;dvrHTm#M;m!y4A?^E(1oPO0?2T1|xiQYY%22t6kLl1%wqIZVsIWfqj2~Ye7z1i}Oq=mRYnp>r'
    'LG#{VhJRj*#??PRuK(N$H9n}V7<LUYk1Usp%A}?%?A+3I-ZXWP={n<k?BKRLimrjk#9hhH#uiv-ux=x3(je>NrZcQb3#~KOD&C|)'
    'H5%(!@wrnAzcZF{T0c%}Td!9pjG!yW!_b7u1rdvT(-t5#SQc@iCq#%qoY@mq!j@Ke>F@v>%gemLDrwqSMyl7?N=`7OF{!Uy<Y53>'
    '%Zk*=Ce5O;@11ORaAV**WyYGrt!^ag_H@GwNrQ}5tM@h*K0*see{LFu*O>UOSNOLIhn0Vg>(rY$v3&Tb`87YjPGr>GQu#zrs;vZi'
    '%hI=}Ls=bOH<onSp)T>c*L^W}Ps$vzb-+njQ{_8drFLx%7xm$Qp$Y>r%w3Q}yWXV(pk!@RG75vlR3j}-Ya;67Jqt6=K5$VYSQC+A'
    'oxZ~^(lCdY%;lTc%CXAKf+l}p9~HYZJ<@9{uk@=7Q>uta@g?8o$&9A3q*n<D$6QZpD55|z*&f(i4!jI>S>?K@kDfAXnCm$68N}hr'
    'm#d{wgM3Y;70d04cRcfap*)Bp*NZVDeb$H!!(=ezatT5n=Pg-A{?5Z9>#zWWRuLMHD5B7+!=1aJNf)?fXvrW1x|i-9cB^qWA1E*K'
    'ygGA+oB^SloxaHIf{qBTt<!W%@07@SE%7y;*>|eJx*M$TNI80H9p(Zbi!D|>^F(Qa;;WEhD?pKT_&Bc$5ulD{L|!P?(qO^HWi39i'
    '8*5^2Vwx2yvX;ThARU>b&OPI;k7D1PSXJgouH*whENZ8~tNh|pV)ilk*O_XN8(so{8+Zc6SAdRfGga9Z#h-y5#ouYR)Q=?&7=+t%'
    '?GT^1<JuwP*N$t4G+sNdU08)+JFZ=Z@m1IEa$nc(l1C1qfIAtbCZqsP?=-`Lkgsr>g%$t8>=|WKCorV&;|z`9L%wAE*Rs=8vLtc~'
    'u&>jTAo;=3q*0j=*s*XRWYQMvUOG0IM5kHA+&$jRwL)@YP_vwAQ5G6mRs>e0yw+lNO(fV5Wt{Ww=T#uU3O(dxu!2{UBTknU+KsLr'
    'q72q<T*wk5xnYW<e9EXlC~cS%NNc)A84QA27Wu+n9@Mf36T7Cl=Rt3Jt4l}Q`#o^G6$z8uyDN#Z=Gd)|4iwi$`7)!(w7|mpXP(?)'
    '9L{$(Y@x1QzPT1(!AhZ;BP<k=?MIo)DwA@gWi6IpTtXe<&Y_M&4t2!Wa4mZzz0c0?9D_f}`}V*bYY!ApX(Gw>RwhVk51AKbta$XC'
    'XH?c;E(O`vxcu~cMSMh?Yd$VTnV5_^ZFdf{ni6NVGU4)9Hq!5#;%Twr$e1d-3o9<xN?H17TO8L-d*Px=ms3UPE&Pd<j?f3svzlNA'
    '<%-s3{;@}&IWjR4vI0DHy!;SeX=Sec^yt|Kx7-%iYv-c)Bv7cz(cD?Noog?GcnRjqW~Q~C<7t(krJWw;am4q)9{9;B*-{K;rKS|U'
    '^M2gAQ!AgLvt5-ILwgNNI*#o%rNe9N9c5(WKo`xd46m!CiS|`2)#%X4skv#{+S)(6n;~SC<CozlvJ@P=&QkFFke7NUc+<xs*00nJ'
    'yY0(Z1@d)z0>iTKQ8vUzMcFPBl2yU2Lg}X1;VbqttHmy@pw(hXD`>SG(F$5Eo4fP!5qf2C0ezxkOX1Es)Kndc05o7O$odw}>ZE|^'
    '-mmvqQAl}N!s)(o3gs@PpT?}OkB&@*Y6G3?M8Q6UviQu7Tw`SAhLp@FTP!J`uxUu2n2PH`uN|lP2c#gMp(AZW=EF)mw><P(f_$BU'
    'Ps9opzJoF7KzK}SCYxiX(<0ML6m(K;CdF-+w6gRu@QA^QY+EB3Iv}ir0*2ElFfFqpp(D0~k!I+r7}>@l7-GR1wI3TWip2&bsq$>G'
    'rsW!IUVIg!Wn)SdU4)RgD<S~~^C+%pZktrcL?@7RZP}<uKeyJku?^F;#zCWN>!hU1wNAV~iY(E!EI431bwYSh!LY;bbmzm)*2B(#'
    '9$eT)(SY;5$b)KDL+yTO!M=4hB#8C%F@XY3baPt4xt2r|ldy>xc~F7+a-t8D9D)x_#)38{5*9&xR=sPRI!qt8g*M8_TiJwc%9^q1'
    'maM=gD0fhl@f&u{WR!sWfnDDST3S6MlC@Sd+P)KA6*f5yz1U*ZUf1k-YnxypGqB30wRS&RXx%tkXx%VcXnhkcgd!QHe%Op!D|`OV'
    '_LZ&n6(ZpJ9E}#sQr4i_<4kPJ$zXAjEJI$Z_u%0DMv}fIGQPU=CHtemw1On7&N0{j*x`)1$=@psKJh*KuD_FRxH}xrsbUdBr{wE='
    'gW{HzDwb7Q*}0hIf-j?;)OHxKavDetl#^=HY;Rgwr&IZW#4lY2O134uZyKml!aKfa92Rz#2PS}yQ7ZJ6`*%9D8J#!nadRyFv%tLi'
    '13g2Wldo|5ZgW}AHPE8=!mFhh2YKIcusW7-u=DULkw2Hh2A_U>{vii2%I}u{ZmPgz&eG`}>a6n9oIah~k_m&relNz53xfS#S6Ptk'
    '_o@D__;Ws$-!=Qa?pow0rq8Lr({HL8+NImB`g15h2ljJ0@_i~mv-~d0@0$Ov%J2NG8QoyL;IGY)hWPvHy*B^OU8vcMEnnuPX=G)z'
    'eag=tnVx84<a{*i6|LQF=T(PG?d|E~hv$#)&TpSSd^vyq{NtxDZ>OiY*uI>8_+$A?*I3TWQ_}~1{KUT}nPc_m^7&e`pUY?^#?1P2'
    '8C>nz&t)z&e`T3E!(JK6uk4Lbex0+p%dd5$6PI}T`MLh=>Ca__B6O2Jq)dqk^yjkvk^hoDr2Z`F&xiW+s%j9M$)vEKKA*q*SKX%w'
    '-h9c81kzK!sGWadJ9uHc@UnIw+EOlMB0w_tjwT0M1Oc)X@o-qDh+BmEVISfH4#(%ZV?_OT375sV%SAzZ1Sl2~sJOnZ=IWQ#2yu~i'
    'URCy`SfDx4zU?=KrC->(EPpJtNy#fF$}?#pk=-OyHF*H_4;^Q0m&EsklqRqktMjo~rCu)p%Q9!D<d-ZHzza^Z02hE*?Bo>hSVX$9'
    '{1+L8Dx7tXpIu;S*uNv$#IuzDdipSZ{MXy(cOSpJ`RTtuJ%2v@cR^@Z;sXQi2X$~Ev{i=|8G*XqqZ_<>#4~+Y$SJ0Wdwp{dT$K<C'
    '7aIhlDPr*wPJ%d{!&i1h75fxP4|zg#{7LQlCqWH4#Vq0s*N;p$0zIc4YmHvvv}18l&n`yJdX7fVN@eLoI$=5(a*L%w>#gHCw0IDy'
    '-u}OT`H%nkr@y>?``5SfFH(PbdVl`>_Wj}0r>779c=OX7;wZys{8A$b`!X#xo@-yM8JpO_dfJ<o5#S}gfzlgRJMr|HZrhORYA-!K'
    'UK&*#Txfz_Rpu4l_P6%b^P<C)2|WsdcNLbd*3U`h?o(H>xb_*^fe)<m>C}MgLSThYPffJjA>eSE7~Tm<5FqDHLcj~gr8o!iVZ%Gc'
    'DC2aibj%zA5Ba8ZB2kKVsRdjHBlcgU*40~Fu4}rb6P!q8GZyoRL(ZMhER0Pd=Ps8kU1h2`VfZp3r=t_AN{AOKvz#bsD$ld?-p@zP'
    'v}lDWq5BZp8>tt}qPdh=w0+|taN{A{El#AWG?Z?iC7L?nDTG{t+&O>j`NNmbzr1;0y5rmK6g%c}KF9yc<FeD8fUx1d%*I%qwiPi1'
    'o6^urK5`;CdD+drb)>O2>B~<KC%LUUdu^q^GTEy1WKq5<o?>=6sT4g~(3m^DD<Z<~a#6cqX8-HQr}LNjgLM5M)tqn2>$VqK4|~BX'
    '9bELTq9)xiP`aUgap*5q2_UIi>sz^86}7Gx_50sWKV*@ihsM_qi81^*kaB%;IfNe)M*}%QL^c1*K9jb+N2{}+L5Ig%I_fl|o-w(E'
    'TJ5B7X>IHKJ)yO|bRcr$_ZJ{he1@d}^ApwS2ohZBbeT#rZsAZI7C;@unq3C{^<M{Tem^IZncuP!IT;k!^7LSnm6h_}3QXZbk6$Gi'
    'o6vcG=o*Fc$MU3gzWHUHv*vP1)s9{1kPdCx{qCA==gYQJxoXew;6O&EWzi^QG8U?)-6P{G9a}`_kzQT1u6<e8SXy;7(Mqo_zUbU3'
    '-K+w{{E@UkCkk4$qy{@>G&7fJb#SLxDdn#n<yx?H?t@?Y0Od876}KQQ>UXCS<_qL~Vt*d)&`V5x*jfvS?Ol|M@;u*91-4SWXYq*)'
    '(0wY>Kvy-prEnZh_q87bx(%Jx&cQGj(cx#1w+DO0+Yh$9J#<4%%TOw2s3M|nyEz+qEmdc1%b}wa+NO>z1?e~h*xfv~TEcj2wNk^e'
    ')r^q)a=hm4r}}o~IfC|bT)>G=>p2$i^kE*F`8Y26QtOe6?sPU`o^Kfyz3x|_{W9Zz4MPV}WT{Desy_oUX}`9=iEyhEB8eh?K5D9C'
    'IWRCGwitBKX~(ZI2>oc3F@)JnYQ_+hPBXHAOkP^v?Nz#&daC*zDeG7|D>}?)=`%HGZUpx_vvXD2?qmVU&o<%GQt+?dVJ?TKcUSWL'
    'N>e(LJfZiO^M})U8I9mr{M*m9t)2)v${C^QQ6n$qCOt=pV}o6|ursou?hcfp-<cJY<7K8wT@;bYs$gEiu}iyZ_A3U<7Ikc15KJ(d'
    'K$|j%qjpv=5j>=ee?VWM%&TeC$VAkL8LJVK)CeWns8*ygbk*Y5o#`KX@^#id;Oo3AUuQbW=Vw`BX}OW*IT9H_r->EF%JR;mbfBZ;'
    '=6KS_AIlz{hpNata~^Y);Y>%%3+`VECe&oKI_#5oShvN$$`H*3$T-m<@UR*JphEz9JOrIg)1n-Jd90F(0x`>s=pcP=|8i5mJZZOD'
    'N0;RIL>arTIFg(2C<|nEPA!Sv?R`9FCOv0G%fS$eXt&6zvr=uVP%GW03bjg76}oS!e#OTgiwd=BH+Rw5gtYFe(2UG16Y~fadM+vy'
    'k)C4}YLk!HQ=u8^*;S#|$gv8whAM^QBUI>ARH!w!r$T|L&;@EbRH2A69jj35)KGue#6Y^GLalRS6>1&bq~Q^Y<X99*2E6uFsP$$;'
    'g<2oRLjWy_dfEHH0NjCSE=zB+jetjd`JsL}1ZE0KeOQ}<HaKbuhP5T=gxFPMPBe63T#Y%YHr1HRsP?SJE{{-SQWiayxh1zhNtvM@'
    'bBY*CQawVCNmCS=Q(;4qIc-LY%xODRWG>;U`ijhv3|S-PBNUm`MUzD@qNm9e(`3%To+gWWdqa~U;B>T&oeg`M%%u__eN7f0Kr~q='
    '+x;F(w`^$V{8*JaFE&(}^L9K2s~X`%l{pY2YcPXKiz@5zhuq=QMg4RriI?vdC!aCjIz)<Ej>Te>Sq|%u(_0;J@as!{=Tn8ff`Vs}'
    'U@tmV-B}k9hPjS=Ko%*{MEFkp-?ZSyoY$g*0x;}lIt)v-yBWgx@>@!8uOWVR-m#22ng!&%Z!3?7B5JF*mf=YSt>6Fn?%xQQ(|J(i'
    '7eTHf_xax{Vr;6iz)}V?ncwdXz2o-W#h9L$%+Wk23IlVDC=p*Q$TrMHs&kLyM*BlbzlGlwxf^~F@X9w6fzCOQE$3$aJGpSa8~G5U'
    'LRPB+B+yZt*La>^P*+`zBe0U*e&vzM2FO$z`L6L$CJOR>Z!#X_^bq6WQj7;k=#c)NE7XY8YN*|`#QRa=5mtjz#cF`&IHXns*rEHw'
    'Fr_Q20o;cB1CF>q^706)LCIn@fb01`!Z51={I36lNY$~`05JA{5UjdmH2`e*KZrkFhHHArhP~7c%b6nM&Z1)wwj3Y`V+Sat(u@o!'
    '6^e*CKvYEpK^-93NqM=$rx$u2huBr>0SRI1iC>PGunMxI5hxB@pt<MCK}uZ6CEgTL;&}&SkgH<9Z)lXOZVS5a7!{=vG<A&BLqg=L'
    '#>j)-cZ`B*9i!S?8bwyFWiPlxXF-<Enk~l&@vj3F7wp(E%E;KhiVK$PS@n=0xvEj};5v@cbm39*;C3CO;I|wjM7<8Tx8HS)0&F-&'
    '0f=Ly9ug&2HB27Bk5ybq_xWYUF<QKgKo~3e5Oia$R;9s_`;>0N3tAk?sE35fRf&`PE?k&8C0@w(G8T%+jJ%yFV>t8aG6QFrx8xDh'
    'yX~cTWD0$`-{XbRJAPjD(B#kt^9Z+nxe4lpyT(oO$l`fTa~Qfw9$7p4ZW5+(4%{SP$TYc|<X23Z>_teWIdGGrY~M}tQV!juC>y#-'
    'UdpkX<Pp=l;U;;hhHjEa-phfT<fR_ENxoF;o!un$5Ys~y)5A+Wa+AEgiZsGYyYD7>X*b;@k9BMpQ$ou}m=aps^6_r$CizTo*|Q-$'
    '<+e21Ji<-V&Xis@ha<5ey!0bCDT;<}l9w=cle`4tCTaZ$8$w%GJ`Xx>(sU8jhVU}%xk<6fhMVM-7@nXWnJu?%2%qZ!cWnr-1TndE'
    'r%?Mn)@<3ZN{-zmujGcC<dqz{NnWXuo8*;h?ul}!GK#31q&svucldNwKV305>3BY!*KU$mdc#ff$}l%+hRZWQDYh8+Nq)h`4*Vpq'
    ')_0jJ<)$q4leB+`atlSdA=GxqPx8tQ{iG-(ev&>s!cWqL>n*-)!%y;92YI05lpp#@K0|x^IxZu7^XG+!=(uCiaflRdb=>*Dbew`c'
    'Kgp}G;U{^lygc0BVb4$UT8#aqC?tN8?$m_1$I>kuU5l}w<h307Nge^mqY*$h&w-y5Wz0{aWNThiLSd|T{D@D7`sr%VPttnmCuu$Q'
    'lMwYw{iL&m#!o^z&K*B#E))H7KM89<@AygDZ}>^tU*#tut>rb%!&QEg5o13INhJq<l959{$;hssWYpMCGHUE68TA4`$>_14Wc1ii'
    'GJ3;LLb&IapJdF~PeQ2W$WJnM>?avZ{3P=b+rw1b!`PvpWUi{j;f;TRpJe>DpM)ic7gNI6N0<`E7gHkRF#B6HBQd)+M1f+?sxv<2'
    '5xqPVKgl$QBefw+82U*Wi`lgytl03AtRQ}p@sF?}Oei*l6+J&`Ix!o<t}#rl4T0pGV;jP%@d=91${icRstrG>kZY#lvJcs?g-66&'
    'z2PTWz2zq%x^g%MX6PqbGrCTSBI+lZ{j83!`E*x5-Eco?I*7(kvUbZ)vX1#l(6~v~joc*b_S_`9zVck@HtVUIWR4HfZBx;02%g+?'
    'lQL4WtKte&GR^Gy5pGh{L8Y^><tEuMbdzityGb@|xJj1c)Xnq|6?Z8r&WWCzG&!c?5XZTr;+))albjs8Nlxy%NltCJNlp<r$#e>1'
    '++*pMeU1>%p^9^Q>?S!qR`O1d-6TY0j@%@yH%?UCKHJOJeEO+=y4iD+kV16eCOJEHlbq#l(&^H=NzU!MNmyX~3O5NsiaTzS3ma|{'
    'vPoWHf_ib4n}l$|YnrREn}kG*12-ubzV5k6UU%K3=<keQWX5h1QXcNQNzn=zx=G%S-6U@}+@xHQdgvzQvef-Aa$`3MOH+^Br1*!6'
    'n`9qidQ@U;@BPqC!s6A}tfKG&H_3->HwjUWiz#6rl6hoH>QQ{#hMNRp>?Q#r$};vLIY+i69mSVzxk(_0ZW73`n*?gZO#(&SB>Rx0'
    'BU`eLJeI(2ZHN=gI`XhaG_^Lw8qmpY2r%Ol6wI!h1ZKlc0z*tL`;e?7Thfj^*bO%c?3SB^D9qs)xS^Yrc|Ch>5;*E6*@qy6YYm3@'
    'Htr^!Txi@R@LO&Y7RM%T(y?)q07h;Sz@D1~>nqQ-ZVS{+vJXi|a<b~Su<s^iJY`qK6+q=Yv#wJ!=nkDV#Z5vy<yggGLGXc!3v%ox'
    '1-aoS1xfa-dq_HxE9poc!JZuz$I_8J!a8?UTxilysfr7F>?Q@h>m~)W;U-b0(YSOUvCmyeNAd{x9ICir$8J)vV<jK#*iAxw=EzOL'
    'vg<^}JtQ5;iTdeo&rJ$`=q4c(>BvnAp1VoM(4y`F?7B&aU3|Hl1VZe&Ng(9dO#<WzeYpt=Gu!7C&Gj{I5(qPNlOSUUJ8lvna<K0v'
    'fv`O{34|NENl`X*lK{y#_uM29e&{Ae+0ab_;m2-LG?h2qq$nS{Ng!b8CV>b;HwloGv${#{A*P2brbm3)$W4OlcsoJLeK#pK+H{j3'
    'Gk0cF!aXE8$(7_JKr+zb7L^@phT2U^&EOxBoa9S#638uX29QH;29RTJ29O)v3{gnjB=?ZyBwvz~K=#NPrXx#E0=Y}h0Bb-evmro^'
    '$r(WIk~736V>c-Zsmb+_<Rn*;lR)~hn-ql`ZW72bI|E1<xk(^l<R(QCb(7pf5W?<UKb_Mv9FN+r-6TLN(xICKN-#IcuiYe2V&Eo$'
    'YDpWon*?gW+EA2+Vyq4RA<0R;BqxE|XKeu0VQr|rrK}D9A<0R;BqxE|Vr>95WNnC|p_>$CV>bzCU323f!{AktlR))Y8>RzGP6D;d'
    '+5l>cwIND}ZW5?n)&@`;tPN2}+$8^y<Ro8`lR&w#n*><meBdTU*;vUdKXj8o`JtNx$RoO_IRB93ByZ}c!;YH-DvaEuC>pv+QO4b*'
    'L+d7i7JF_IAawBxHwmkZ@3=`?Z@5WFGJ1sxs;}a30DTpQ1L!e_1Lz@#1Lz@#Llkx0Bt7PE06pe#h_V;BNqWrT0D8>f0D6PN0n9ds'
    'LzIu*Bs1o405j%r07E$({6kC+Uri4)<Zu9U6^8?u7jQVhn$dD?N*KoB01rt{f|8sR-?rf<nK6e07|P)Q4@pjflAIJ@w&f<7A%{a0'
    'jol=(!Ql{v#7%;SBqu>hPKqz<xk(3>oCIc<!vWTKPHsb(F^2<~T@HuXWW!A|l*0iYlAHv(ZrBYDhbY`~lgyaI0ql^&0jwA$Cq)r;'
    'li(o$VJHCM_%`k)h0D~qNo%4^?j~8z;V_q5;(n4HkvM?eBXIz`P2v#c)K7wkBqu>hP6E46;sAC`;sBPCIKV@alb|Fgf!!i;06Qdc'
    'h@!EdWH(40qL6Odha@LKNlpUWC2<HWISK48i38Xz5(ltj5(lumBo1IVNF1V&_(|}P<Rl1nqi>KnfE|-KMA=x&+cAj)*f92!93ydn'
    'ha@LKNluE7-}95)ki;R1#(t7pkvIg=`bln=!~xt@Bo5Jt+4Ym$28lxyUgambt4JKcT}9#mZcO3;Zb;$)Zb;$)u1n$&x7XND@?#PQ'
    '@Gl^706!*ih_bPt<Tpqhz;BZ{fFF}MfFF}MfFF}ML>cju!b5D2P;C!CByj+L6^R4*7mzrB-zISY&qy4?Lz0t1NluDy+whb8n8X1*'
    'C2<H3NlpqSIVrwu%TMw{5(n^O5(n@bBo0wX{G{-Z<fKrNlfZXL9DpS!f!`%@fHk0#+Ym4&afq^AKM6KS8~`YZLwHDXQYgtu02?F@'
    'QMlzN!I;DWU`XN+MMFOc7>Pr82tqix`sphY2X|b!?n+-ZWBXQ%0?Kl;%k~Y>vNbTaZ-4<=Lmd@H)({?&g%nB_62LxL13-tYq4t)N'
    'HH7m+D*A|`%V3MF0boeh5Jh8u2sX$XqL6ORhh!mzl7$4&C2Ihdg#@rm)&Q_Y))1v*e+YKT8X#<tHAErthr&a$kV45qf*{6h-w@;m'
    '+czNGax?}(j@Z5dORN)JCYgw`eTRo+A%#=@^kF;((U-jbSNv&K+&{egviy`wP-Y$T5FF$|*50P9FIKr05Ccjo*VcK{v@-i|=F+u?'
    'ABv2Y4-+Chf}kvvPMg-H!@bb2`w5{#Pr;i5sV@z|Y5bJM18mBK0#<%^Wd;8MJ&RiMa#_boua#P`=p+!Cr#dgn(7${tPxs@e*Kdlp'
    ')%G_9HUz=u-BG<-_B{b!ZT4ahi_e~V-kZDfok66;lu}>g!9A0^C4PfYyv8~yE*NE8|4Udri-2U3)W(T+YqfEnOB=%~{ax;l1TJ4{'
    'u8C5_qk|RZo7`#1il{T?^mt$#i&o8#ujArrwCZp?(NFfLj~|{tzB~Kx&(F_KA3yy2U%!9b83yUTKY#w|>2&`4=fj8RPai*jdGpur'
    '^;>E4&wqP&_;UI9`Td(W@YCVlQ~c`lo4@_}r}xJ>f3%E=Z|j&EX{}X8n~OPHEhPP3P^)jk_{CEhF|faquL7Ur5v0Q8e2uX5l@fA%'
    '%dV#T@I0au)~=q(*hoj+uVhdYRJWEho`Wl86HD>y7)~i>g+suCxO3q^EY=|9uVnK{3NOf=1v>Xq{z~RvN?_Gk_YJgCzqUL;jVk6w'
    'k^OZn9p#ywO?5c}u6dR6Ak#Hs9ujld4U{y!Nyk_nA?=6JyCAO$UIuBaf%|XirlkC?+3kX}OHO}nlM)tdEcded$C{dD=8oDtbmq**'
    'Pv;MFJ>&wp2#AXIYc)SPcVxTWQ%C4q^wQgIFE#6Brm^~Vy##aP4u>$@;q<Ki7T?xMuG%ni)T-R_cevtzw_M=F2A;Z#$NDoVS2gcP'
    'oM$cRJS%CrQK^;^f2Z;s#RGDZxCRJ|Ufz*kq0a0T$z$zZ;siyx59do9{QFX5BeyZ8)239V&TVX?4>RZM-SnYK{3CsRh;*%V811pO'
    '&6Ss3C5R~9kzJliRLeFzGSACTPtTv;9e&wes{eOt_Z5ecFJ2i!f(J|1nCRPE!Ivz*il0dR_Mn2;u-TDF_1E#m>Hd|gNd>&GB>4Fa'
    'yQ)(eVQRChKs$;^=3m92>U7c5x7oG$l?<npt<7$|q6$Yx1N7H1qDpMr>{|U==3cqmPIRs1=tS3A|2mdVqDm?T?d;;Gv$|+Tof7ox'
    '4mi-`P-h(TH~)-u<fcV6JFM+-rmg&ytShURNbPJs$kN&K(%C?_bh1;{TiUr_$p<-LA7n4C{UC2TAH+Qk4ZoHd0^PGuHJG*0hUpyl'
    'G}?4R{r!CU;UC#P{cRn=(DzAo;33qxG*j`r^(t-1&Y(2zu$n|R^%92_d8=L7@27Bi=maf}$aKlWW2EW0g4VEQgb5wXy~MZZW%4oB'
    'z0?=h%jji%+g=)Sp*owq=^%ctJv8>V^Uowkl-~J=Y~0^;A=#D63ec!5;|ve>NZGiWCS`LcKPp4q*o|InG0$_|T^cvkA_Xyz!{J+v'
    '191EH^fUc9n(*;0Iu|6LB!8@vR0l9Yn%M-*NRa|)37GOhCqT^;ut*8I@*8}kr5v<%0}_wgN=>5)r}^MClc2i9DuxxOXqYh5aPK?9'
    'bvzOhm4PLS_P5&6t|ULh90Kb~qMjg^)MTs;F*dUez%P}o3C&-Z?P#s+48)O{MAiZeYnY&$Eo)t;7t8~(D}GD@4-QB<O?q)my>Juj'
    'g%6!J;8>f6c!u>LWrDIN@Gb`3nTo(x1tR*>mHEHQT+aQt@J4~pH?<y+{kUTXIoa4jPTtoJa#%cm4qh#<xGGOGxU`TLvxr_tIDMmQ'
    '=giQxbCi7LblOFjN&BzE)0ek#4BkE;-hX;`o)tu)SBZ}+(eHO;7Ogt5S+v9tJM9Ai`tK~scfqaL8YhBCaF(Mk?O}1X%0|chgjYc%'
    'xOn`A9qfgRM=UdeRqGo%@a&98R&SLCy&TdP5oZ*?;B5}Pzy0*_-MhEv4^te$lP(<#p;4pdabD;SD$sa#$LghMW8qe4-o`gDtoS3)'
    'JzKOMrZsFrf20t!k7}>^jD9MouwSwGso($h^g|XIMeN*ZpIv9LA4-Zsd?2h<1JW>Gp&Gm+$7MCx%HqvA2W4xYG2};t=FVT^MXP`7'
    'EO-XBo_=OBinX5hDLwi<fu$omGp_gofxYH@fzZMzb;!%&1Xdaae`i7(V86qVgRtWvhs0*k9deNLjxm~}U)Pg^FCD>i^u>t8fWZ3~'
    'AQFqBhU8!_h(r!Y42XT-fg=WF7v`u&E!8BLtpdrF+X5cOHt=%v9wN{!Q6^r9*<`PBdjFKZiwf<XSBqyie$Sth!N-nY0PZOow-8&^'
    'p-c(w3l7%*{<qV+A|p6}=?q`lXAPy#D-x}^&Xxl_q|zAm05_9w4)7r0bq?^5yqo?dC8D$0XGr=P%JR=ROzmedh{+>ALvP%*2D4fn'
    'Iy6p6uxwJ0V*sCVVxjnuDu;D-Q%FP?|2)o1==iluNR%ZM5~m)!1g}Hy9Q96;?^44?(Y|4ErJvVvCB!%{vvTevSu63MKYsY~^#1&p'
    '!!I9y{PMTYA1_bu&j0?G_v+0XJBMxGyf6KPVT>sNF^caoBwz-vdYJ?2wN+`I;+&YhO2sJu=xG^J)V8h$+pdOq8jE>ZRR`y|JRu6D'
    'Z13o+%-nIQ;Pd9NKs`^5zgST}Jj#`BmhB>&519M)C1oZ&e<|4#_><<@68MwhITiR54|eY7u1Sq6^z+;IhfklPj>xW|nqmLl6^SBh'
    'K%6nhe&k8WsXmVTV$lXEN)UzI88ZZr_FUT7S8>MTi=6D{u%N`O9Toi1w)rCXvm4}#pe)ewGpF(Rh0-YmvAopAip^oKIm!Bn&1-~m'
    'koAF0{EnHW1cGkaV+2X<K=EE`M{FanNbQKtmF?K$i_|lF{O~gqUOfqj{(PbN7aOO0iGlft^0ZTn`Im;A$gQ}#e^#**T3fja5n!9n'
    'jjT2#{21Ff$36S`;zu2htPvJ;l56^j_$a|z0YyQa&uZf<F6A@8u_#6y88+u3X`f?y<ORl$%!O$1Z@Bik5akokDW-h%WE<s!)$U(K'
    '`Cu{o?X*{Hb5qnWK0pnkekdYQzn4vyQY$}niBO_2@EB|SNpo{J{`oQ)NTkXVg|urY!@P<)j4$##VY%2Q)!ePu+0vHZf&Xsu?<r`r'
    '{I1LIivO<4?}lHOmx0a44!=gn-yMq=D>fTmu$w4#tk>vO@2FHAtFJVbhh=$O=IHp_!;f!2Co{J$lMm;gzbt`RH3w1H;qT~_1D|qT'
    'BKvg8!)r}>7<xcTXkiBEN|Z6=<qWVZbA<)k*OVz`es#+6`})nC5pliETne?P+0w8*Te29RI+5RZk~dMth5+fD>Lh7ieet;XT2ZD2'
    'yIA4g(xcNm%7;be0`tL=Pb_<x4>lX<k)=%vlh5aim11X+%X3-fI^Fv9$BkE&;^St`c-(Bo|I&LC<s|EJ3N?M>(XCgC^gciy9qVZ-'
    'E}K$Xt&o@P!M&72Mkn(3YE4O^lr)skR${im@qq=pRfjp4o>k*7w0|ara64DfDAN_}VTBJn>%tbZ%rwQ9fUFEND!zmwJEWC}(#~yp'
    'SvE#dN~&4*8Kxq$!xt*5`x)f~3aRct?`(@x*%d~M&azOJ8Iujs?3z3xHZf{77za8S#t(=SP{x^0etUX{3fPqKu!>?wo}Z#L{-+3O'
    '9QJaN+h0A&^3`$Q!fH+G<y>1{?koeX#c!JGyGcC<E9UAR8?Vmg4C9|A4(R&Gi9XWXuY08LZ5?`f8ykTk;k45`&V+|@paC^$j<Lm='
    'wFoRZ5U1%>Iv&V8SOGhFL%O0kGO(s1gYdQUf0H<)YRYpjduQZS4oS;A0(08u6zRl#%CnNu&k}vg!nV>44-PBC@ZhjYefuN9Dh}I}'
    'heP9#V&(ZA*yhr7fo)oSQQLE6CRMtTh@(5V*eHVy9c!&_udiibF0OTAq)+Xbwi$)XaT2Z79eoN#pIR4s$Lz%Ww5rnB(We&VhCW4H'
    '&q$xz_PmwHb93I>?s+SZo_5rwN+^qNp4IQ7ADv)CA}4wtyJT_~{!Ez2A?KvnR7Q?ciglHdlVPNcoRUO~%AGUeQqBaYH2>DmFzX^+'
    '`m9KZtx%rYB3xBpqB_E980rW__>6RfGv?dt2xkJ<5lS>V!r5LxN`wPjN>0=3oM=0Jhi+DtdN$!YU*{|hC}%mYh=S@PE&NM0l>@nG'
    's%SUvXsWX=g8^%EKW!SxH%;(EeddL1HI_KDliH^mLiO)ijKE9Pg5~gMj-jiq=lEXvxp=ic5f;>+b@>_C&p9UIlO<b!w&iEFjvaZW'
    'cf(`3+Imq7aR<?Tg!R^`R8MpZdTkc|DJ#OBjqi(%kL;$n%`WE;r}NTXy`uJWOEfFwCWce{;Y1T|zu3SIQYlcRm_qrEQ~F_p)iJ;*'
    '{h~bIwx-XO%5Hyd)am7O-3#WS!!%l7OqfQkv^#dF(!~(nA`M09fHV|EBht_)8<U2jP?Me-x6@PQN>97|pV7c%8*z{S6Pt|rKb08s'
    'f1+%M{}Y=G`9D!e+z+XC>=Px5fwHFZB=mPE98-CsbVTJDWlA(kFBB2Omq{if@Um!U?*(%%^($1^roxU*lG9qY?rDX2j|~jJj}dn9'
    '0P855FdzYsGP}(#9$PrsL?oezTA0<4`a3rFJ7nUqNlGVM5R3Sec{yS+HV;=YZz&PP75w0_xx9iOJT_M&e()&M1AcH64fw%P)Zqt@'
    'KbsLhILb!+;3(VR2QQiw`Tf>R*NcqtgFipf7uz8}coe!VesGkJ_`y*&;s=j1KjH^R*^<Fx<!Mjd9Lh!wo>6^IPh_g#3aEW-9(Jj|'
    'u~DDuJCC^(f>3>1CHIchTm%;XaLC$?!r@se5hGLev@$zqsm}FW@$WXyQYqx<ERCY!St^AZpQTce%SEg7&RME+?g0K>_bjC~hhn33'
    'IhW=vl|pZvr4mssgTp7v_RiASWPFxNVaQpk_D&&HP9Z7mkQN(-8)vD++SkL+aRXXx6mhKf6BW_3RP9}isB`@a$IRfv<-E9fSxHJP'
    'jZN&}*)>b`dUS38dmPu;X1nN5Y_Ybu*4sCDx_$l5_SLp-->}D5t)lfY;;TlPCoANzw~L|dV%c0S&|NHtmkSb+HltlE<&b(Bg>)^4'
    'y<P0fE|#jpB7M3X*e;f8hebLzY3fkZU7YJscbC1?J1o+%i5ap;qmV?;mEXJlwq^ZGGc1r3g?3B`jnWYzG|E~+=(3%Vy^Wg0n#nZX'
    '$8PUCO#KdLx9w3WeS1R=MdU|@u9Q5t>2x6#mFwVx-!V`n7F~Y1$tw}mvu)zXC2LkDuSDjqmm3u_dW2Us*VovvQkkI*E0rDDuu(L!'
    'VP&q+yRu<ruFBhgksI2uQMPZxO00=Huwf;_Q3f__l#Ojzi6v||Y}hCt+OSbJv|%MeQ3f__lo1<N?;Vi39*`=GY*>jLQ&%hqE%$BM'
    '*l62^%>a;m2x_}?2pU}uL9I4ySgpo3Y^E5>H#@L%`WaVFKi!-K^z_quXv1nfwqdo|uwgYxi?!PCoPNfZ(@&d@4SPDD*y*R&B{<sC'
    'PundUR=cqctKF^*tKEhTtLb&L-ot*G0{)WPZ`iQNr!zkN5G^wN92nZL87$JXVG%2`oPFBteTAxD0o;Z?t*f-eCSj{eOFT-%z6EQ<'
    'W|fxMKyDkbMp6S-ANTfdD0|n)eFN60u>oroF<|w1ZwsHw7B*_jfHit(z(%z*+`>k07_dgug*@$T;bYmt#`Fx>vtwJ>m|X+5tq@GN'
    'aIO&CUGv878nDJ~7_f*oS-$+ZxA;R@{KgF{nna=BGGGyLGW;ArsAv*J!0gvRw-HeDRqtJ#8>nBANUm}@g^QoI|Ikk5@4^bb>KCMy'
    'L|_Wl3+MB~OjWjq6|aL{l~~}HL8~R{sg-Jlvt2VDV4LttJynfijkSEQuyl~cg<zRa)2U)h>e95P3#yg~2<d>TB{I8oK-Ka0F(z6f'
    'f~0OLGdxi~{g|#v$^fj~K56Mx+0~*tHTh7{`FpKJ<$N<$4jMPFj-hW0p4M?+xraaho{X`l7}o27(9!}UJRm^mC^BS<)OmA?&h>e2'
    '1m}%1HUOB+woFWDp}uuugXzF|PZQAl`RKcUdt8QeqJuL!oz9Z=R2Js-av+fzMZ8Pl8?jc7pmk}~FHqjA7#`#_*~QQ*Th66=crQR='
    'NM{xdeB5(>d+L4ZglXxcmM3mrs!L~E1jcF7XEtsrJ0x3a<}k9-Qn#SkXfDNV`~H<1R>MP?r=zf~qpDl#Hp<#X>8Pw7ipHjy8<(|1'
    'Au-L&X=IwEejbWp=6dz%PLpSbncJ&R7n^L<r$g!3FmrqL>6G;2`gABHhM5_fG<i9c`SD`y3sTF=Cz_8k2}gQn`4rdcev6k3ayS3o'
    'vHqPO>OHT-Q14~jP7l2%y@GGA?Yw3@0Y@4Q^16dQJDnWOnUvmiIL7ejwZcz-d~xiLt?7WP;?K4Nu98@7nB$`2PcQ%pNn{CH4}I-j'
    '_6M>Wnzq$Y$)=2d=EnxH_lnytqDiNe-oKKW>4Bf5xAD2*^Flv2T>7vwHEsFb^zs1X@2k8)U4DnI$qGVrO;+R_>Y1#F45Hx?PcVKG'
    'aX<8oJsm3}<q~OtRC#<s&WnkQ9XV2(a8Tx)eEaF?=kq&~3mE@yRVR-6D4<xKxWjZlG>ZrHtJI0Z7uns22(k|iQUaq)H<oanHscyg'
    'xK6bRO=P+(C$KCI55Hel6j)0|f!v)UZ_!P*HMl|9CKQpQE4t%5>p&jrBmL04296=2fM%I#lX`$=EX2OjwrbY4UQ=xgob39@IWiti'
    '&|N-1h<y2!ym3*{V?}XeJ>1r+IR<9cU}4)h8Wqh-{yrqkND&z-l5)ip$b^0|+rh1!rDkKB;xGk8YOY~d-FeX}d2M5X*ZJY|a`8=0'
    '>iX%bWThfK`|9aS_@eBNkW)9m;^`*bwnKt7qaA`UtO^GA4Un?wR6$ZAS19MqOsiR5*a}GHSaUe+s>jFOLL(^0Q)QX0hABd*NF44&'
    '^%N2bk<s?MqiySG2f^QbT+>!#8`n_()Oil!>)wnsGW^X8-B!^)NJ28GyM(gY^L(oJqjtIMM4AYCjW=7zi!9OG|4^rr$~?cSL^3#X'
    '4UI|OgT;kO&CB9~=H{%~t>x+r^I>PYqb`qAV%(_xOCE1ImF=3{Sz#&~O`bSaO627eY<oA4Z#pczorL5A^EKLg<N4fOjsi?%U}ntm'
    'tk<CeM1F74cqv5s(grgHv0SxakC+{L%UcA+J3>g@YDeOlZSV_@Jw^&>UgX#)O2!rtZK<TD{>=20_}k$h=f5A0@6ONm{Nc;zUoy)W'
    '{`rWdJ9ko2KW&-9<@y`%#+!Mx#obMzmohyF#The&1#;%747*|6TJ<r;R&Fip!>)ewqI|8D{KOE8F<C!25$G39a?R5__-fnVKZuH1'
    'Hw8ie$s_&XM8lZWNbL7vl5M}kyx~e4*_q0uKlAZF8=s44L=LJ@8Ij`z4(kw1qfj76VH7KShr_MgZs)Rhi{W9EzEHVR#P$elf3$hI'
    'x8>!Ezx;5v%??!BzA$PSn+Bp){W^cE>4(*&AErgt)Q6hT1_lo-aZ{<9=~i+p>GaoQNF{r`eu`TT1VrNyd!UIWH7mM=la%t3IegR4'
    'bY{Hy+Q))u(;C%Ogl-fVQmPY3FMC9VA!mkC!GCl6UTKB{_h!$GR_a{;a>bM<76(~rv4SDUh9603`8s4(N+(2THyo|>x*j~4S-pz3'
    '(V5lS4QE#CFkVX9e0#Spsu<CU6^6;sO^z6zbriMiY>nCEZNTsVXZC~@-8PNxDD6!r6d8ZEogicU*>!@9@n@c@sq@dkQ#DQbS#>fv'
    'Ra0pSf3h2ECUg>>xG9_oT1wb}-oz@CD7Jecg(xGJ|JI4)&VD?X88vcNUt1(#vCZ(RFv@_w__)4-Y62v|mp4aaY=?eK8Liks;Fp8I'
    'XhOXgHTJFsf}(-U>UvFkauArrx1GINvFCcpb8)?laU)kU%BVvJ%_Vws;Ff!Ig#<0sp$li<oR-G5EV5;Znq0g3E8gtf>dm5kb4@BI'
    'F&u8vo0L_~J<9s`$^B*?<svhUN4dyaPlCHFCf#-M;$Ews1^Bv|wt_K5pTc3y6dl`0$>P(7$!s%UiwuZ2a80L_;nTHnk(}$pwO~U!'
    'hgWlMxU!l>co-LjLNv;<*`UGHw^6gQjF8lX4Av3|T%K*_;i$cmf(c2K@0>Q3DLqcvLp1_8vCpwBDN5Pn*76j3HPM3>SxsKx%GVxx'
    'NunEb#{GA7QmZ1f-csXu_R~+{MDN&?O|E*esl=W}ljow*Y;xhZLix(}4j;a0kgcTk;n}7^;t|@%moHGPJ+!Cpo#K0buK7^s+eMQL'
    '@_e(9^3ozN)6_eVdxw#_l*0%)M(%i%rm(yaGY`+i%5{d-zdBruY^+>o?dw>%Zhe6&X-^$TY8{ps>e5sHI!G<${OVrT(w+jpmpx3X'
    '?J2y@y{vL!RGA57+{HN@+adL@#K#+5;=RgDv5gYFD_)iPOV(Gm3c(PaE8F;chY7zJ^~hV&6yrR>ffB>SMg)oomo+c@(}yqT&!2z%'
    '^kv@XhcBle$i-}Q@I~(p!Lm0Pf6E&}_YKTB^48t(hEzC@R~b76T5l>gqBoX7$d|mq$nu5;4XKdmWVr2+v4pK=Sl9Q6ZQylov=x$)'
    '3~sBVjNcJ|b>#r%!|1X&itG)O8=5*{_#>+mRt#VtXu0p-Q2KoZLQz}o%3i?AxP=QTl9MMCq~vYROO&Sc5OEOexhR?gRHy7kdA4E>'
    '%eB2%ES-+jghW|jZXb<Zg4VZ;nYOF(SZ;=kRs_zHLE&RjcDGV1@nNHKz9>>(zdRw)__E4K$NFG@%kc49g{6+lk*_D$-j^P$EWs*|'
    'U-fp+Yx-bWl=khO)%2nGIRzkZcsp<q4O<qg;PFwAxC<7lA~6|K{tjh~bo=<<{>S_C`{(nQ^3DLwJ5zeBT34N#N8;xt2~1_wMK^pI'
    '5;IcSe6y@PSDHSsOkKxnqgJdo6TSBddORdSv)CDPZjtgv^Q5$i7TSmnVCYL`_M7CgB<kJzXUVaxe+KlO)UQonS-Wb9cKl5)oL2wN'
    '(x_Jm{w1qzDqc>otRz$%q3;sNDvo0vVaH>yKxcT!o)JZ!b?imkU@F@nbP!SXrOdy$Q9A|(&t}>&P;mCayyydDy#@-fIup&QITHiG'
    'O3@t`RZ|yKV9_CVdl?dXGO3ztyQnd4(Wzd>ULPCz_G~UPDQ<baWGCS2$@XPcx3Fm#7Sz&0xn}T=RYoe}d`0&)QH_6y?_D@yODrh1'
    'VH1paoMnXb{?@`+{-DzmKCIti8DL<(-mWjnoZVkJ3)VLyRG*xRcVye^`bTpT1&VUeSVoGR4JR%G9*?IouWp(&Pp}5RnG>Gp;9a)L'
    'wBY!!v|g&r+%nF!%FlmQHI5fqB$%c}Aoke7zQ|LPL6$e<WUCX#D91;pmg@`GrOYG>c{C!p=E7CWSGsW3Qpur)kcwAG@QW>^u@Kf0'
    '7=$G-SQ}`2%PNxEuQT6Mk-z$UBXi}AvW#Lk*i=h%lk!2VPoS#_;v0fsZ*bzKH^j|L0K1_<+-RBLXgwW$zIb(DO+CZGAnJxlY0<2&'
    '=qb2mu;Y?#pv78-+g=bHA8d(R_rT^;iJMlG60NVV5n<H&`tj$XudkJ)aHb=?s2l23yCGY&+YDZ-z%5#KPa_J+rJmII6S3vBO0|st'
    '`IVh9Vy83o-bJfS9Nf8-jxx21V#S~I6@G?R>E5(=53dz<MbmsNZ%&46bhggPzRW+TW9-Anl3-nap5KzTRM9F#I!?>hSgPulna>4h'
    'h)c741FZPB*{}!hodEqqzVFU2>yxT|>hN2!1)$ghh<3wp0cZiu6qS+F*-gz;G`%Z78#+bxNs>>(G?&pml_j6cQ+@3;XbP$3SnMd%'
    '<7vpnsMs{rKh*RjIEurI`eY8JPg=FQNo(EHO<J3wZqnM{G&FjrbUiBxs<ArNW^<vaqo8epT8&DAYVCOOO%@Z-Sd;1nB}i*?@A>;y'
    '?@FW}qj$kIRYT*z^{R#zYfcAVHI#-)qA=VtXGXldf~Yofvx2D3<)KCuM71I1-|R8G$a+?#f{`}43S65~s*whW8O)@XuQrMs%pjZV'
    'JB<LNS2388vS)kIAL+s{2{FEC6i2s&Nm%jG5=A5tEpIDlU;tmJ$d&VgBfK^T(OIacDrJNhEM}(-vmvivsNh=NTDuj*C<3E%4X5(n'
    '<GMO)|GkC%K_i_G@g(rtUz*>s=XXHVj<G9fD|jVudXcKF>?LZ)pL;3T+De{+ZOYH<6l`tfC<R+v#i`1Gc4xhp0@+J;wU_+lo4sUT'
    'YcE-I4HKcZsTlD>M`77#+ul{Mbw@Uj&QTQG^t8?@(ugfuC+`4nKyg_orQ6u3{QTpGxBvKj`1He59K^Cv-@O0NKmYZ6@z(y&U*ZOP'
    'GgqM~1L2|9ck5Z-f!uVSoca3qmW(ZpASNI&;5o@k@y`vGHTi^1G#fG}G;Jc)+=M;FNy(b%nQ4_jMF!Snu9jo?QxxlN+(@_x_)|15'
    'a7fBBYi9&s`_SN3VjKTDYu{Pbn{q+15wTIY`&x6Z2m7$buopYH|BF|-b=EHw0Y$I56vfD4rIUpwqOTo0hVIlg&fJ<(o63p+PFZ7!'
    '&$9*{0kP{`pvWgFO((G~bw&T<{N>I2f9Ae;!K>Ff^6gk=>E7S&B>|(c48Et*z&0OQ1^|IdROaajcxAtC1hg2&B)uM`6V@?GCH?AA'
    'eHJVaR3m@N=(Yv1NbcU_Yezk<1I)M-Zo6&MSVw6`rRP#foeMdQ*rFOvI;rCg-+wF}^7NkZ^jVYpAx|@9yK4{pc<rr-_bpp{EMx2C'
    'YY&k;JI5VJv3J}d5@+YQL)gsDaR<@U-#PApXSq_4ga$*?_D=SO#axmRqgO23Km}M<->pmm*m*4xdMd(croo2$_s-cJ<pA^yDz?5k'
    'Q!rm_<NJ%UK7{gsrv?WC*w6qx*~MOnEb$cNQs5VT!w%EBY%vIKyT^g2I3b9jT17z+I86N%C_*=k$s#UgCyhxX2;~Y3KU_uFsY4~~'
    'EUB$CxE@L?qAY@8SY`2DY6H~!&DD{5nYKC?MWUFK`e;kjq9+2+(O446@Q~s1L{>9lf{xaI=}K5GIYK7RFD}v?Z3soi{M_01IT=Q2'
    'r-SE9*ONboj6_KNou(W5J58m(Dd5mwUx{gJE5jnT30Eu_BZOEjm^q@-SunAw+gmUO>m3aiOqBV-f-#xYgD#k?6;0;!=q(r{SmC+p'
    'bjyM%Q5ho?TNKY}QAkQ2Y6Q=pO@O)5DIJ;v!C=sk90+x|SmD^yXF)&Cuu|WjF?lPe@<kamFvxs`V2~zc8I-fU++eZDOBs}*$#yK='
    'wS8F8&%dLS>1=~2spIAdtmt0d_I<Ds@04%BC{+gH{+&umB3oD3b$tNWmWs*(DUxv3H>`c7>)H?8v7u==MsnoV!JZnFhLPfRf(1rO'
    'K8VuK#jBPKI)f#YsyXFP$I}f1B#x)@-sHg%X4T|O6&-D)UQ&1c>2$-Hpu}k^Z%xU<A3wJ`P@2XyjC!QV^rjUQ8*oMseQI#_My5J8'
    't!-ByvO3c3g$i>4_H5nB^9|OWJeT1}1#kG7Uf<|-b6_tr|A5}W-Y5f%$X<;MqGM~;?G*IL7>KfQlD|Q$%N16DlGor8jH>Z;W;Eow'
    'LELIkJiOku8kBBp6qL_YX?^#s29>xUsnu|-A~&=eGG?P3kcV3|XQ_~BlvRTRvdpEjtTtE96wXPbMx|O}{gT;6rLyZ4ttsmvRzJ$I'
    'K=5qJPSi0r%G)LkG68D=y7AG^{274-t!LXP@MnZJW_@7K(89MZ*fX?TaR`y`)VVO;OkQ*mH>g)FigwKuEA>81CM)6ji4JhCtkg>v'
    'GOV)F#e^F=WkTuHs_GKG|23LJd=FMOaeKq5S{`^5BOQw#)q;;wy|Xa2lTA>EFHEe8v~Ix{ruMWV&%M?~!s2(euZ9i*y_%Sppn<ZI'
    '+{ZsO(Z$EHC{sT*5goH)Z^1N%bG~XdCWSW2TmeoMOhv}&a;b41Ekim3^XFdJ3}8(p(ytZ}X^i5=r6wmp)C%;kFUwzN4w2XbnjT2O'
    'yI>saLVFS$%NVU@8j!MI%!)9`k_~R0=)9b*QR9HVJak^}S@(`hi+tm45Kqv&M)GeAgZOZLOYlv&_Q-l_MSFjFVlTn#`?ZR`@MkF5'
    '>FKHoyX`s6w15BK29Kiq>HPWW^2=)R|84#s34i$*pY*3sPp3ak@1JINsW)%_`se@s?mzzi_WeKKzj=Fl_wWDt=kNdY_RX8)_W^&('
    '`(?!_LPGl{SGUP(`#w4&SHtP*46KN=qJ#Oak_K1f%9?QhUUh0w)?V2#3YZ(Lf3uiMy(8r1ohcPB;zP}bsbe{1HPc>}*2<uZzwF^v'
    '?VFjZd8#sY{{bDlPnz@3pU$T*=jrX`-Qge4tFI{ihmomQtWN|HG>K$I7Q{e**Nz4n+^N=g5+XYa<!qg&3$1rL3{GSN>f=xI%&j6V'
    'E@8Q;-CQ5vNsl^K8N0l^k{8vu1kiZ_Q>k&v43{J#9+q2@JM9mrHOHi-3(`!;W?W@$AU;2DKm(ESYi{V&rC5Lt!K7-<gu_i`gf5KK'
    'jbrzovx+`4HShea#Gjw0FYLf9(u8G=U;VE-V{Hdu$yam&Zh+vJQf}M0z`3CbS}V#}5c;5xm&Wq-LcfmXi{Jxla2(d@D#mltItp`*'
    'G8Pt~$U?K!dFf{Z8^6Y7)0e6y&|d#cbEr4acWUZR(`;blHBUC6*}zdqAURRD+;B+LYKX=gxqWdNTR4VlC|Pw?-pO8EWR`Z>-*D9$'
    'KfiR@`n@hYcI8$wGgHi`tZ?s0z~m1YorQ*G*LcrUOxefzg@_>Pb9=)zva;pdK=x1Gaya-z6F@QzeTE4hOH9fKxm=eyak)Wrn@iE$'
    '$b&-TXGd~ZYjXXUUUG)XHDEeWQoJQt-HDlUCpP8iR@oTPxf7dK(JkoQiA`13Y}NW`b|*$l{2A!niPb04J25A2G1*Kt*^sq_P$W*Q'
    'Gg`6rD%EKL(AHjQW@J*1MFXi0-1GU%oR<6i^sfBguJQUjQ!<?9G~qaM`S-Nxi|vF1x;)P=XwiG^3*;Q(A3rVBLuGG(Yt5PZA(^ot'
    'ZC34W!F;&VsZ~ii%9UgwB_l5fsBGZQ2GVYS`~ix%5I%gDg+9LSpR~m*ozBlpwqj8wvLHyD_g)ho#A>x`LU@0yZ*Et6m8FVtDZTw}'
    'y^>}p`W$3v4EwSMgHo*YMC+1-R6OJPhtI_Trhl&Gl9Tb<X|Ak+*SRT#TH5&W>y6+K2PPy;P|1kJhYR*_+wFkoZ8kd4&_Tltkra@h'
    'q}Y=@@2+BF;Z3hAz#afYFlUtM4l^}A;=~>iH17i&vfz7t2;>1)2tDe9MVtqHxF(k;7TGtLP|&}W^y?4h%}4fTC3?L(@HRBv0*;-_'
    'Z3+L+=fnH+@yE;M{P}N(U*3H@Ov-+adjI3+Gub?sr=P$4`1xGCP>Tc_WT)81NV7t_CbE0Hlwu>f4Zm2mO&HD!db7GbC9tPh2F`Px'
    'zPJ{g7oTF;QyeopU8gTz^`0WxQ#=c;_)cHIbe<CUxCA!3zSEb`8{NRhMbhjEMx{`mB4rzWk55tTDHL(KFd@*Vs9s;-$eyA{JbM=T'
    '9G08@^DWpAan9fnD|0d(VOKo*xnGXWm$cNFR^|p{+L@`m-0IcKgPh-O`TS&@-eG>Vz2Oqw*>icd8zWDw<S?Ftl1;@zEB)&rPppJa'
    'no67=&4vgF_{7;;kZGYH(`>%+FDv?ZF$?)m@_4Kg%>JEymMXIM?~;;|Uqsrb9Gz9GVw9<ZZjR|%m8v0CpBR&Fq$1XoMZ$+sL1wFT'
    '3C7kyN&4$jLo>GEfcaG^X{!t=BI4BH27}BUY#EmX-W&8eq4#=4q@zi<TqQd-$s0OTvW%^=>ypc)#B`Lxpu}_(g(WqXmzcK7(Ughb'
    'uoBZYm(Iywak{~)aVJ;4!j;ueX#S5EhSs&p^9+c#0CjA#F6exqqXBAEwArdelekfU+NzW`)h$3Bg(Oz0Zo!?nL*0P9e$QM#cKOsq'
    'g;C~jzDubeiaZyi4-LMFSd`tYg&g@d7OUzk9+$c$66i`K&}v>s_jnFV#J7yBmdu=`_qrCjGstyQz}u!U6<IID&Mvksf;&2GfVDBY'
    'NjX39f79YlS)FNMxRuXuv!gqIO`?FEE6-ffJTBC0nulu$GOghRohNdEV@)bb!4_92qV}4yOryyTY_8x@h7uVRhHp}q`zpj$F^Pwl'
    '*FKE@G3o5cjZ#FsRt6DF#z=l??tYY!a9MVe>ZUY|gEwxxjOVJ}k1=-qNrp3zl30jEVg(ut3H0xB>}xjJbcc5O#T(O?q8c^>ChF)|'
    'GLb7fe}3c}H%2bnrJ74R(DUd7cBUJ@eWqvDhJ2>$aKoAILpjrPEto;KVSJ{WK+bf1y5UUsr*fv}(lUcH-Gt$pZo>FXw_@W=w}PDM'
    '`gp^c?vLe6M<_~rrk{bG>CsQyJJXRWVtl4sH9pg$dAN6`TeWefTSd-veangG>xmbSrSX}b@hsgl9RV%F4^8xebb*%LY7INm!-Bf9'
    '2w7Q9bbU)omWTR%hFzM3NgW%f!8SH4)gU(I2bU-K#%Hij?`2BGHn8J5Sg$wLj7|01iki9HqGm2d%~%j)HDeQFT35{=>ZC43qi#?$'
    'pk(b#*ibVzn30;Xl>TY0W*GU?TFnHqp^Usi&44Uw#tGR|Gm5DhCty#_IJsVwRLwXE!`<hS^|GaAT(V^PYQ`yYccnXp)2~=)Wg9x>'
    '$7;rDF;p{7kM$`cX-2Mt(|+hWAjF0!np>_d{keW&G`053duLgxiQ{CCjeFso9J&{-Q=)jo^mkY{a>tu+**4#F4_w?tJ4JIWR`9vP'
    'YWG*M;9IZ8Mm|>3SuX=9qOp<hb=S!EW^CkpGdA+Q*)a0+;pZ*0@dK4G3!j?P-fkH9-t8Fp-i-}>taCFm@Vy@!_}&u(-`sLeLp`Ux'
    'Zw>r1i6B<orWPS0*Q}n<wex`;z?rjRcmM+}0PM_k!vPFaIe<ZI*!dvFc0N|5sY=?48?bOen9`Z%$e{-?$f2DNa%|^g>6_sJjNp>x'
    '0KVLE0AI=h460}6Plg@9pm*(j&|7vs0!c>a5|~{(KjTgM2QV0FmQ1(ouTpQqg59w5vC>Uz0M}2oVf?91G?qRT5ksN?vGjqK&T!_I'
    '>j9|O1K?QlUpQ*BSo$)z@ovM?2jF8w+!omK#{nQ`tybfnhY(=JmD8w}Kr)J))i<b?psQ+03|O0PN!<HG4HE=0@uN|BL!VqR@e!;t'
    ')-XX1P5dCoCO#I_8ETjy$zF<X*bQG{i-rlRXX2mEOv41VYvKpJW#VHEp3$}ode_9yWqSG=1`G8pqjF0=e<=C<@tGSYez0Q`KiIJ<'
    'MdFu105?!LT<pkUTCM}@Yq<^zOhk2%Rkw_Rs$;N1!vzQq*ueX>rezx-qiM4qfE(zE0vt=9l2&UgQQ45V{5~Cid_GsxDu8QLLhU^)'
    '=|b*!OJw&_BfD7rXSC^q+t}EF(80UoErgtx!pP}_FsnD#7djyv*)z9Ty`fmWPKe%hbzTlmBxc*r&^RHv;x<IDIFS_M!sJ1}BJ0D1'
    '<*>J0`i64p>xAM-6mvoA>`*zOcm(czS@!93X`^2!i^5^Oq8F5qaR{jz!CD;>)UYo)hW3lx>y!X>!tq*eGi+#C3XUgls{<k3C~dr5'
    'n=exxj>SB3!qc)Gzde46FN*)kLQrIP+yZO}1=!#?3Jl+eMW`l<0&|E0<8YmYC?;o2#WujI*&w`8>cua25*aLBuqveFeq?Hu9#xFJ'
    '*l5#_bW%}2(#ac!>LANdNj0`lqj2a)I!WjRoHI9Q(Ss>kR5o@EIpm^r<VQx)(2sNoRvR4#4#{Vhueb%-ekjQH_{^Rkc@osh`~Ru?'
    ')?P_+BfGz12wq?eOAEdk1PlRdyKM`S*TPEvJjklbnz@61ZFkS8$G_fW@{tjIWY+DxkDC4<Xl}4FnZZ{?@Wcr}dV7APZ?fS>noxyk'
    'VEmYXecQJ3e3P*sX}CeQui*zytcm9ni`%gu>4h79q?Zo;NW+1(p<J0|#E4rGZS%qfY{dEF^uQ;w@`=?wM6-ZX(U-J<^#M5Kq%ZlU'
    'F}a|>fCG2uXaNg+Rchb>^V9^1c*+F$-gp5E&PEGZ#Hdtv0SDfn;Q|&MIV8p&fO$@K&R@Z8X91rU`hl{5MMc-&S-?WnPAgu(p#;=u'
    'R*P6?b!!0&3F8GU6yBUQ9GPg4wGx9<`7o5FT;uw^suv_F-y1n-``@cc&Y^Rs)!J~mNv%v2fia;76>P^WOn}{OMO%!hf;{#56{&o2'
    'TEC|w2k<E$zyfwJfqk3tIV>=4!^{WF@@dXyx!A&Oc<JyQ7GvCoksG)TFT|VC<;XdF$>*@_;x<l(oWpV#x8a*?ox^gB+c0t$x8a*?'
    'oWm01Hq7bBA$7`!l-$5=7&*pmc-auQVWe!am}%Wg#p%-4O|-?gfkCvzNK6!J%n>~5G!-3a*|4AbKlbXr_&@6o9d?l#wE8SNaEP8*'
    'K18Ld03FDKl+-PAmrKK`Wdg|ZMLbAJa>OD<d>J>8D;q^vb|?d}v~l=4-CPeut)}ZKcM6BhmsosA)<c)lMiP#Bf7o~Q<1P=M&mVr7'
    'Kh2l#zkK-k;q8YXetq*xdWB-W8X%llUV)2hUAj;6X#tc<Vhd>HD$3!2c^bTIK>(dU{`_z$(>>J$%S-+86+cWMru2miGGy;z9V$Vn'
    '%Q>Qn;;9AMXO`!$C#{mCf?#=XtYCzBO9d{3W<nJ&M3;IwVD1Ta$@ZR7RkZ?^5-ZV*wHT{67MicrtEnv!0R8AE1*?H$FL{xxSW)xS'
    '<=y8`>jO<ncznAa6eSW9s)^O-Zs~fJZNN{sBk}ee(`l4v0>cYwsnkmsl8Tj$s(wb#s^68!6g>C_Cke)7n$~N$cr$1;W24?`w#{$q'
    '8$k0p0)thIjuZ&^5rjk51OO)?I=*6|;45pZIf(-{_f=$@TZ=(WgHwL16yzFJGTbFh0RCOYDD9<`5f|^?T1osd`hZn=)!C}l5$J+~'
    'U@{?2&=k>H){R7IR0dmHGLHav-EbnqS>Rr%2c%L)8>nB*+80|f{CyP+4TT;$zo!cTXOVk1O*T7b$^r2*RIFfGR7f-=fHc}smPJJB'
    '>t%8en`O+S7<!F)6hp5u4MT4{WI7DJzU?kUZ;0QG2;__zGW2@Uh@sbuh77&lt;W_190?(vO9;v6Av2#bno`n<g_15YiF@fT)Xw;S'
    'j~XBQ7^s~w0QGQ=2$zj<a(6f_YeRcek*U#eT4w9vOxR9iBQHRAI4#E@ayW8FdCqr~CNOJZ(%wj=1o%*~LK1t``(x~@I^%<>!Z0q7'
    ')Ewiqk~iiqsaRwzEdwzTg-C~g?Ur|wGv1N{5A(u|E2|ddU=4H>l6FALWA=6^w56iEMy$;wB}m4ooiZ0Fh>;`a6=My3Dm8GeZ8-+>'
    '$!RSio0sKSE*6}%rM$-P5JuEkAVu4ZTFvHc8rx`8m7k_mE@NY<@%&TWd8y<5mr^!X!~+4jfhDgjf2M2;>+kZ>1B@_PE}TJ-MTBX$'
    ';DT3_u>nHWXs=xYjh0c>O+SD6@x!Nw|2Myh3lILDC(PfzsLvm#_ka4c|34?c8vpW+gHmA*Gb=4~T64qon>X)%diT>$KfOzI8wLd3'
    'Xe6o<>xG21My=nGJ)OWi1+_a!n4e961g<O$(~<gYY|8FnKno)7h?Zp81neGefeN*i7OoQ`1B<KZ8Zb1u)d|F%l?T%z>pjy{fFU7s'
    'fI-Q^(qGW{A(!|NeI^fyvw7ukGnvD!_}&>67p+$(4@6}yGDl?sDh?adqy~a<Y<zA9tlVB~+BFx%!(s)-al3nVx_GVIJv&{x)$N>}'
    'E;{YR6#AG&YIt@A#Mydwx+9RNONK<5z_?U%vXiU`-+~6iu6(66D+8m+34l2Wy$p70f-hW+X-9MZyl9gmXu^XDv`L*uuFs1cvMDy|'
    'T)zl-{1@MzOi>&Dt0u%I85uT2EU<HNUPsR|PS~^J-OaLmBPs7Cza_f3x!pN?FzbT^x~MDu%{l*EkQDa?y34XC!o!vnh&bz3k)t8$'
    '^^~^EJGeOf%9q0Ts}$BlF)yogTnl-ay{Xt9<>dhiU9`o>^D2T7Ynx?S;0b>|K&x{(CsrN*P=)(~35C6kmVbJ{GP9O{da}M4!b^G~'
    'eK8u5!#&vx=?#Kf*RVI}N$Te^aaS2O+Z`OZQ@_9^cP0{-cFC<RvnaCrR9_D{X{Kx~=s@#gbjj_Gq@7)I+L?bQ4SI65nv&jB5)~xA'
    'siNiExEHx*@J?HsyastYodXG82x*p$lJnXq#j50SgL`=Y%iE7X#7zUTNN{52*b~%O7B(QFFrP2ygwNOVSo;+fV5tr*?`9&r+r$r$'
    'aL?Rj4JnF6;1e24uB!BgwhW8q+Pu(M8e)-N8ynEpWwSVzRaLXDL}u6AvWXoCzs?MDZxg%t&S{>!X&dlAI6%WL$g#8BiT%SqowA7`'
    't49Z8MZDH7H)~d{#nxSF!k0rc?a(KC0H|=a38-KNrK&?imuHc{wUJ4Elsp#~%u7cHQ_^R(nuJpHw)5J6P_59k)__|r=483~Cb~9i'
    '7Sux7GK6-G<y1b($dLi*Wu{>qUVrC^p%j_XvjHI}8V=Toju)xMP%0uj3TIdWY{O6zv9|HHp(I?(`B@&|BsNaCAhIF9t(B3cI-So?'
    'v@Rtx#8Uc*K0;DjTQXiUt&7uB_JtGd!e{cnbSE@D>Bo!KQp$@VfjfF6&Ng8?@<_meO<{(-DM%Vz1oA#da-JQQDOzLvijiVoN{PI&'
    '^(D3FxZ&lO(c3GA+l44V!!u09m?%`<SZ(^!pj@~UKM;wy@^g7*dn)Ntn>8%^vav}^7K6j0gu6e*o*l45uEh?K&~ERVo^WL_oLY;S'
    '_*2Z-hL7Eb8et>DFP#@BwABQ71e!K@E~;n~rsMSdm59imdZFfGKuL6JuDC3<Ywa{MsUu5D<t3%07~R=fRRv)LsvBxmio)be+ap7&'
    '^N=dF9ka8E2&`+W5F)TTW@ZBw*s47^vN+CVan!gA4#*S^unU4kv#K$LRV3Vbep6UkIaXXmq9)bYBSra6xhS7iF`uu0e`pn`ad!aE'
    'bI?adN|%wUa+`xSvyPObIhqc!FXfTaOufuVY1X<VWrq)_5d=v(RH&6@gra|{Yp(UkwU^a`Qo<P56kxFxM^`MnEVHcsy=*nC1_f2}'
    '=BX7q{&6`%tEu04(wEgwNrt)BhBiU4@4TxglB_h!PER`py?Cn7w<`ShT76L@7-DT-g?VHQV4bwcHya4KM3;@*29U^l4+MwUxFH9R'
    'G_=Pg4P#3jQ4N?7g9cu&RHbv7IDtuX^N|?3Weu~$*ExSh<!5ZF<VHX*<xM75nn)H(xHyTvQkE)YK3$K%kgf@a<eyoc5Ekt_MpP$+'
    'IXA1qh!;8`0!@{{a7h0u77Qt@TvFHSbR;%-EwMqPIKeW7@-%qN;*r1Zhl~i3KNRdgEK6YS=_&iFCB_>r#mm<B>D85PI;yjA(#e0d'
    'iA}3~Bl!$W4nT3ZUS^;E6Ait3Jje1;=>RfTG+=iBM~T7grFRy4E5U&Dd()3uhH4g?^Hm%u1kA1?_Z=!Qd-{h}7Aw!Mi3LmMd6Gql'
    'IFU_7)(@zaO-c$JOtNfjS6kL5b2+riEOTkkET}@JXpG)sqLC8sDKF;~u_$ne$%>r~JOJ&{he(nuR|UAOlw19fn(S|9EgGxA#!^=W'
    'x}jD#J9jwNFy6Y+wpKre8QKP<&SRQeL%wn%(KTzK36YeqgIs519ZI$g<vC(})_1^G1kXA?j5Aq>LoMecln<O`&IfB9EqSxtljdCj'
    '7=^YiG-#(RQ^+wqAIT%)EGH7#P*rYo)`}~hwZKiYgcw~y5EI-7Q#Sx{wrvu!N<dPyB#p}iK+g8VuK4mDT8bLdag73}e@NJkI3=@*'
    '1X@;~@Ats(*204pwA+1#5mntK89?kyoPB)`2CmWP6x9S4_D5(Ebeidf=#hMU+`glYc3}sqRC3N_o?MQN-FR?x6Z4<k7-<2J^CCuC'
    'V7qcim%VvZH1A@TPL=oK{|r^$3ppTNBD;Iqli3N4{eUu!@Qb7WSi-a?BBMr-Br^LP9hTkOxK-DjTpl^K*Br19<4T3`?ksn>$oSKJ'
    'lBr-?<O2-3Ss-C>XK`BOMcN~)PTJfZ+g6C6TRPP+>@}wvj#o%S4M)<Zr`E88p@#jLIYha58Lqy2ITB6fJcm>LQ*C3cLjZ2I#=8Hr'
    '8yV}sIG&D|=}_;c(mTF$#1e}dm>7l(y=>=zjW+EmKT6si0~?r<>wfizfYNPFNZ*Da$=n4Wu@F#OqbHPa+QS5fq*bJXvPOGz8kj}t'
    '!I#r?WRy-*9;J%#eM#s`XQLNVOr*UuA#Mn8qL(-ufq7kRoQ)Fac0$4vmBYq{SO=2x6z)a!?G+<(_Y6ydS2?%xdP4J!b2Feq08Ypy'
    'aTL&tA{*Z4B?@?ivqZ2=S^`|u)GH2mG%}_4@X1~_WH5lh$Ta#usfHgY4UUN)xi1hbUl>3@P7$p7QqxXJTnZ5a+Ns0mVDa}hq_q>)'
    ')R?r^yD)Xdm<#@;84(gfU|Sk-Uw9!hpywmkU|jH`EXz8;e#NguS#^b)hWr9TA;Ar0fgLLgVEYOKctbNno;{=)@uFVVf>dNC2u3h%'
    'bEh6bwae*$|M_A5lGBbLaT4_=c%mdqLw4lemy3My3xUeW(z7Id)k%=A5@P%M!M8w=gZT(?t>02i?wc4_>johyOv?gm&K#j$rdl@;'
    '5~4KiNNN`djk}^I%9CxAI_%%(<=*E{|N6J@JKf{vZ}X>L9?tXMKTYpHfBf+2%bS1woBW>Z^yk06oxWT@e0ulhjr#C$e!osCZE#-H'
    'rNPL7Fsi<^D`t`~HCUlw20>U%9H~x}9NS(VK7V{W{kr>E|2?*Q>}Oexp?`Ceiv)q^2)BUt!yP9X4h?n|0=-Z_<0(NfLB_PRPR3Kh'
    '(1GN7JC6b+&B&Y@;sf7;+yRPq5lSiXTjDb~`ItnEgHnD@l9k)0vH?q)Ub&>f2>PIS1G0ib)_p4Ap-?xx(@<xuKwz7}P2|#qey-(B'
    'CJwJOVpoD+%fu1iO^M{YfsC+s9AYRR1}LHKWDl@U@~c((eU2(pq4zm-aeIOT7m@r5=_V3XWW>TT+x$MoBzoWZ091`%&rsgyIz@r`'
    'jFa?0aca9Ah%9*9&E{A8V`~#U3`(+X@GvBNQ?_9j#+qy_5SUWh^+}pC1e_Ay_3iWS`tZy2_Te&pncw{N&%eAoWi@E>k!43%ujhS}'
    'jjuG-&l@-v1o#qe!aAC^hBoP_8WdLNxgh`o1+Lj7N!m9kr^tDvp7%T&D4ganqn$eIJD`X#oSq|2=F*1qXIK-Y9^k4yG?<|#AnDt*'
    'R+U}bxaa7b)T4=7UL4~wD+=HQM7nfqJ(LuYMpCuqmi+1ZOmj<mt3w+{`s@T2MsUvBWiw+b@Mq{U*keA5c4FkCgt~Vt*64{kY#1Y`'
    'G4B^t$tMuNK&^Ae`GilI0PMkYzqO!JF}eb*cIXX4;3;nopd-DLc*&nuv1}kL8yL#6;hN3P$UUzkU}{pmw13BXxt@t$G`_aF$|*zx'
    'zMp>n-ha=Rhj%mjruqGsPrv5AYuoq?sb&rsLvM!BWjF*R%ac!PW9b~>^NQU}*VPcfCT%Q-<zQuM1Qc5j7yJZNNYY!J2cUG`;=Jar'
    'R}9YH7Fyk0<EWdf=hn@&?1kLiP&Kc%?5VS4;}T1t-T8VX9xARm9%{Kewqsc_3>#Wu(2(*YMz-R-ybr3`$eS}XpklDi^?*j*$^ivi'
    'Hp;9bxw0oNS0F9qCd3LshiRENS~V`#nd~2d<_5opU7HH?z70*JS7-|hgf_KDdZKTDYTd%6)fCv~DQ7zE9JaGx9j^-k7&Dk}xiH_8'
    '&bI`%>DuqW2wWN`vU?dByO_F_Wn8?z?*bJKGRGfA3*6HW6MFn%WpQF#flZix20-3{=LU*gpe!)c@`Xx_hg^|pUSy{#zq9Lt`=`$j'
    '%eOmXCxNCvmsqjdzP^JMFiHJ*blx&T&A#nmS%55cW`U-fux|B*^8UpX36A@B4Lqu3If8o*M-CkQ!q!)EOmsS*4~pF8IUG61^>EcX'
    '!G@E|Q6?8MZ=Gn3T^bH_t-VZRmQI@2pSw;Gc1%p_>t&eF>Kq4*li3zZ(;YH}0yoj%XbLsz%4N3YM+)t6oh$8ut7<6V)CUMyBy8TQ'
    'xhYNs0e18v=B=}oa*UzQltl${xa~U7I~G^qULy9CJk@5KbHvzL=*Wms<`~nP#-U@pdJD6))#ez@K*d&@3wbu1R-11@?OWF7fjK7i'
    'w$<hWxaN+mHW$d3`b)#H#Jd_-20!BXX@1S`OKIiT`Te<+H1vPft(Q7ouXx{fj2h<7OzT8SmrlNo8=R8q40Oz@!5QLm1BX%hBA7_A'
    'fLOW!bZozph;LJKw6=xF{6SRZY|uI=E|f(pbx<rnQU`_WTnNSSh+yv)GID%eZ`R9DB!JIH?t=8JN^dp_&N@CUIO|2jg0qfq6r6P&'
    '6`ZyFNC_0Ka}5;7yA@{{se$77ZpB&GR%V;9I>r@e9p9}u>-a{+S;tYuSwGhf9fUb|!9R3da@Jc+HOdF@w`x89R^1X%=Pe*$hiVeD'
    'RVMLie<X*P>#2OC(VNSd$D#pw8D9^CQMtZe@>^q-rNJ_`ZH?HqJ81q3ailj!l-@uM-y_QyM({nyJ7o;Yl#Gc%gJq2BF<HS6fcv=N'
    'bN-A{8-Xlifp2bI0B7$k<F-B<UdE|DTX$*;&i9tF;A*^#1;?B8^~i;`zNQOp|4?!!F8&_Z{|SGvsP`?rmW3GaTY?hKdn;|Vt4{g%'
    'k#Ih@u{nVv!%>`w9HyH`vQSMC`1Fu`9*eqGWVMimMpfVg+tradr}KH73a)MU-HeZAfv9h+fFsAUfqX0rvvn*7>a4+f4gjUmdKPx$'
    'SQcbkvPX_(WAm{rpmQuw*E2bm1?(QnZJ{=@p54aucDu*2WE;n_WawBH`pAi8bUv{p+c=gb-#V59tZVeGlDEflUcyq)V;QmIJBjnI'
    'tT<8<fE!glQfTb3O;>wvTtX?u&?S_T5boehF)!<J6jO&$dh@1jL)}4X+SKYZ{dd7iv?AYaBIqi0m1XkQ&p-aKjF4A!8CiHt?yr;X'
    'F;y&_Vvng};X<*j$29lH#ABK(5^_7Ej3Y0T%`}B9YU}Ie`4DK7!Xtlvn`UtSvl_oC*Uw3r#1cg;l%afzi9+r73I$JmBaNxHK0go{'
    'DppAe@tm@VqU%3Kru}&p;vV}Y{0IM`p$89Hd6fQ;eiErg7khm!GD;ij$nRFZhCo($V2RsY#l<Ng1a`~v%_HfSWQ+Gpu2=rkW2)vj'
    '&1lt}q$MCGgJzqhh@IxB6mg)<JM!JdWYBzEi`Z!~tVQf)E1o{E$Q|iTu@!Wa5rb_7El0(OotDF5#9lToM(ngihoU@WE7)QyXxYKj'
    'Of$6=wA!mi?6lgbM(ng6RwH&=?^PrAO~%!Tokm46{aib=#)_?=DK9Iv6|~u?MC`O3Rw8!ViiYb8vdCal0k3LpQSO<Qhb#qKECmgO'
    'j0on5H7<w-z%B?hE=WL#?YST(hTb+@5K|MRRQriZ$#-c#ITRAKB_wEK^4)gd`8cFta7axaiVWHk84MIr<88%=VMxJ<aY(_4jgW$o'
    'c>NrT4B8SI4CGRsZG}b#joJ+<7_}8r2u0FHOU>xrkb==0AqAt6gDDS125pH98tum0iZOLE9Nty}_0#ZM4GdinV@VeJa@D%ZG~QSa'
    'MFwq&46f+A=z`2lH7-a3-*sJ(fV~^JAc3)I&jkroOnWYf?c}0wxF7*mw&#M_=sBhB1luN7KFa71c&^7ZH)EsUnxWBe&DiL-wrliT'
    'J2v{Q9UJ`?ZZP^SjE#N^W1~MYCH0N|K$Wy<^oQbPqfY`hHu`~$jecOr=vRkMYbd960&w+={(#@AjDC1jsZ0mr2BROuw$Tp~8~w^1'
    'Ii$hmLmK3U(GO~D^oROoW&c*^Bd0T*^XUxDafDB2&_kmi^w{VJy<zl&Mn=Cn9XXxhluze??P^cw3y{+p%&yT7O}rGJ&S1wze;|q4'
    'Ii10782tdqXi@Ia8gpfh!G_UK&|l5z3~p@nhnjK&qaWPR=noa)*0Wh1VtIqi^5z_)M*l@ljnVHIG5TF&^oMeCdq%$#dq%$#+eW_='
    '*yvZ+L;J}!?<Wa6w%vC*Hu{}JM!yzEwiT~{+$ptX^gA^)`kfjZ{ehusxUD#i){o{#wiU<ow&HZp=)VZEtvIu5^gFX<^n3emxYV58'
    'HTs?1F#4TEM!)Jn?jAGc%9^tqM!#zqFz~kG#tax<Ha7bG;u#wKewgsaa)d;d!(2YnQKSESs*Qfh7#kV=K{hh_WuRW$G5UQQv1j!A'
    'Hl6xFL!;j}S9?akZ=?H0e~>)F==aUdBaD8za47ce)*u@g{XsM``n}9`jQ;TFk<lMyBcosXG21ozL!*(=A7mq=-^=*W=nuk8qdznl'
    '8U0=+Mn->-jg0;vLq@+obXvP~T8D=YjD9bYmC+ym^a!KhH&?qxe`vI2^n1C+M!&usIi%f1=kL}-qu&e7$mkC;Wb_+$<aC~x%Drih'
    'qxE$5QadpEgJ@**2ief*4?<-0>+7M@`D*fK)Jc)c>3mk`boPy4$LJ4D#zw!Fx{=WzWIINGXfibVB@+xAEtf-U?2^}*U_+xn2**ah'
    'm-3O(A7lfgKZuCYzf@;aS%i&#eLnPw=kkfP>;RlmKrV0d0j#uP^!o;K&*=AU)V9$dT5K8pL5_`nBaiGSlg#@`;$+(HyB-<+L57Te'
    'V-9UACT}akjE(*v9T@#VG&1^wY-sd*A>xa)<`8$+r1Q2SY|rRF&172<uw(RxCS#-DOWnxm53(JjKQtK{{XvL~esd@pW|C#ixuMZ7'
    'nPg+5KS)PLe~^ugelO$1=tp3qAj3w#IZ{KNPa=P$<kaXtnHp^5+laBzABqi*jD9Kijee>2jee;gW%P%NdwWK|v?HTm+D94v5*}sr'
    'D>gRz6&o7;0irZA`cqZA+UQq&Z1gKWHu{yg!RS|FZ1gKJHu{y^F#46;G5VDp8~qh-iWvO~H`O)zl|n|pIdoc2<+N66X!I-H82w5='
    '%IH_-2BTk@ZKGdVZ1h`x<d8n`d`Ji4sG-rH09f7ASphQotvYf#pHx1bRdXES(^<Kp(XZUt=vQvT=vNLI{Z<}1oli2K&dT+S{u3jo'
    'v+mTVsZQq_@kLK(&BsQ+=DS9}<{L)87RYF^{Ky(R@w~>g*f9FF*fRP9d~5iva%l8xIf(QJ5jOhmA(Y^Wl}}XE=%3DWWAtl9jDF4='
    't6%GVt6!Tvt6$ewN!5m;4YvC2k&5E{Wb=li?Y`BohbcorhOB-&9oko>yszkul%XIUTK#&MG8AMRR=>t6L)IPIS6tp#bT4ISnkKTZ'
    'n7x#t&}7T%H^Y>nAltS2%{XN!2$9uq?V&|y^P)?%V*P!^h%Ku>;J1d~D#lj7kz=dhNNn|6bLb;Y`AA8v{z<f<ext@#zfohW-*nRl'
    'sMQ~EQhQc^C`I=Ot3SYz_N;#6MpnOZkFxqhxwpqO7h|j6ilNnS#n|e%vTOBQIkx%(QPs%mx9SF~->R|IZ`Ii9w|c|sw|d9ww|Z>#'
    'SHLM^^(Wv|*Xp;Z2xF*>c3@GR%W<8^wR%>+wT;zp?W3%I3pZH(7PhVaTy`!V(r^gWf7bbsPG#r%R)0cZbx-Gjz$*JU90K*9A)n6B'
    '97p(c20pa<fsd_z;2TyyaAftvAyEI>=F=H?&+2z)aymnezi3bA8uCR?=K%N`ome1ut$vUjRzE0Yw7?-y|5@iX79e56(;3v3)gSO%'
    '!*A6?s~_|*)DIe4{cs2-cvj^TX$^XClWVMgFvRLVHAX+!eWM>>&*+ExDyiB}0I<;yhd}-3Q{GPk5NprqPpGT@w&IY{4~Ibg=Q(dH'
    'j%^wJjtz}|$Hqp#V;e@l<9PiX0`;FSd0TP3XY@Nmwv_<<+SyiIlRAaB6(`3=e_b-Lv#q4cf&FbImkx|-IRxrIpYob>a>M9%YRl*k'
    '_^si$s<F}U^w{W6ykB`^IRxrIPvs*uHTvPwhWecu8~x6Vjs6AEwPW-LoYbDt@7!aI{!rm-&*<lj4~%{<d5qD|*<&(!ee+=^Z;*|Q'
    'elHpt{hakOdBdNFM!%O0jegGdGkHU!q0!ITFq7BI#+kf9xNY?N21BEtvtcH0kPVG~&TuBLJ9JuK@@efKIx_k>t224SpB`iMbH1O+'
    '8yamI{hX6bUUvx8e@USJ@YJ!<&-pNuH^`9D?+$_bFA3Bi9=c)lb3V%C4WgmZ&-pl$Hwcl@?+$_bFA3Bi9@;bd0fYK|qrFVt&}75t'
    '=X{vS8)SP%zi%=&`u(gxMvFTH>c6<W#`rjsHwZV3e$I!Pyg@cH`Z>2Fqn~q<$?Fcm1TRoNvC8BHd#R0n&S@quXSLPO`EDw&<YFh4'
    'H?-Ka`n?=m{q7K||8mV6ir7u%4Q+;2KNmQacRGaXpGDqR#6~J_kdCZ=E{3VRK{mGf{qBes&~ymZKl8k=h;Aw`2(qt;y;R=NWW(zB'
    'd+^Ze=VC9FH#8Yr{aoNwUUvx9f4SyGC&sC~UbvCU8>B<4-^+$pKNogr^>aZ|dEFsY|79*8=`E=p%bW{v#52J48OsPbGx7|0KuX<U'
    'wWrNhhT!?OAHb#HyM}$>Kr+jY@sHt-As>^s>zh9&Z`U^;=IsVqYvQ{s8k_i%=Iv&c4bygmY;57n{j}ZCXl&ujVcM>jjnj66aL2-z'
    '!?az=)i7;0$i^1F!fCtHp`&>&N3-gr?WTcLythY0y4@gMthv64tor%7j-145Ghf%sNxtrM2)aLK=)QmIhH0;c`MN=dO#2f%R0EOm'
    '+?$PjT`wKw>ju%-v{&PN-5^A!{d5SrKWFGZSKWMFOQ8E)?d9u+CR?Vx8s_T;*{*4?#`(Hli1T%)L(u*CQWn=ZUpEL19>KtfyM8H*'
    's0)M4HHLj&u}<Ri*CE4RIfIVh=@1lfK9>)4uzN@a@K$A#bG|TpUvdN3+y`{3HXZkYlQ^;uTt(gobgT@qX_1dPyMhdF2l`M6R-G;K'
    'EzT~<hn!tOG~Nz2IJ<%nZ3icHWIMR3ydCs8yUdkr2fLhIp~=>EFy`zEvfb@qgR{#Ev8R7Jghsz+G&-+1yByvPwkW&2bi>h4lwFi{'
    'n`fCJj<-U!=*pXcY#N*s8QwKchro?jUi1)mHyk?Dj{=(W0NnDe&u<^f6AW8a^yAwv=uZM~9ETuO*9@WJfeWmz(@ly>`zFzHdeYi+'
    ';i<%?L{+A|jAC$5m8l>b6$%M5wBd9LH~JQm)K!0t@>8J`di?1U#-CpC7I6IO%5*j<J)Q9;WwgA5ulGBZTYCDB)mxmjyO5q5QVy#!'
    'VV=CF>chwReJbVSUv5bmtft6SXwjDF%wYr5x$?+vhKW@@o_Z<4sLHgLxlviDARCp13bO4QsFKs_n6FaxDRhDq32Q2r`4*fv)w(7v'
    '1)gn|cPiKUMr83=fkQq|Q_?Fub-Ub{Zz0=qW0N<nNZ$yi{mJ^K_;BvnVJW;I8x<GyGEx)wwPuZ8YC&Z~;!@X4_brU>ZBlF^TDP<)'
    '`uTakg>F*TI$R)o?o1rmuGQyTIDwym^pNA60TPH?pl8V30`Nw$OixZWiU7#NJ#E)02;MwH5E}$ylE@QpoFK^-Hg$k+)nL`55-Xzp'
    'Ql3Z6UcOkpX-YwrA>wphaX7RA)S+i9$>v|AX{~`!Abahp2HI0Iw>>rbg?eh~RY%xq)}C5Td&*C3PeHs;PodiO4DP8D^wMxLZBLzh'
    'nVvefR0_u%^cu)?u{1+kYLgP*zSL$V@*C^Qm3U<Y3>(pn;*D;curH(=DaNDdVkn^W)XH|gIi+5xr&T<GGu%_HXis}OH7`;CGQ5cH'
    'i!<)1rQ4!KrLap!?F(&-4ytWY;hqBB7OjzOPu<IGi-JXHKndoFfP47-F$)zwPZy^iAIZJ}xlLWJijw~#7``Z3yi-<6Zsrzt<lzX0'
    '@u;bkJ*V%cC8R@r_H1qlCh$P}Z|_vDbpLyP_u<p8|9kqV7vnCUzJf{Y&MZ;Gva5NaL19BwgEEL<jgDR9<}1~Qf4u+v=H0vh9Invv'
    'd*d}resuKbi#`-CJ9E*uK3%U*Clz9rs5|;B1=z-0O{+4R_@HOFc53ONhGAG=FwB}l{Hro#hSuYu6EU(ieVR)cO9ZT;+YYje3N?5_'
    '_l<(Z0AEtaqU%+(Y%^<U_<FtKZ%LV%X(&=ry8WR@_2<F^B)(ldk$GSF%c?eEMPO*Fqdw_AL-2SY{}dLpo#pw)o^g3jUE{c(Qk(}|'
    ';8ErgS=*naoG%w2aRq$S>xF7&S$x0C4P3f5`CYs-5qJ*qxN>`FWiK;(I4KcecKDw8TKz-)Q0Pmq?AFyNa^jc>fIR#viJq<FvrkEl'
    'w?3SgorF_Fw_9B`FR}z3usGcCdybq|kqFRo9B8>V$&)`3pmj>#2btcx_Ywj0c6&%$@JPaougNYCxyc$1@a;%QpM4kG1k`N4y%3_q'
    'wK5giauj|3ae-i*->!HH5egu#8^v-+<q!6giVUK{Pvp2*_htJ8LZg^(5k;zFSRT&ti%Ai(Z<!*(pPuCDS2RfyS}o7On-3daPMZK}'
    'E7R-`X$y-NoJFtkj;%Y(L`?YT&N3mXUMzm5KPA!9ftx!HrQ^yC0URQbjbQ*s`mXMb6f~u)KO;M+v7&;A8tcx;c&p!?krs$@06!4~'
    'o-{XaTD)vpB9?zBn?HsPd10FHpO?oQxb^V{%H!P-gd)VFVDv&p(%O8+x&lQLsh%LIxtm3Psh8vP;%-$?1}%$FQ?MU|%?GrM5vp|g'
    '_6@d!4ER$PzW#S{ryYHN1oV(ql9#ts46Tx@xcT%F<wKPr%Nxq-&XX+^6s+IB%GA;K8#dfKLYczR-VtcR_KZgPs3dJ6t0e8HjP8~o'
    '!R>Ad(zRtN^Oq%vTyINIOpdk$#msO^P@Lf{;T!f#McM0!2dGk#^yym<sl-{<KcrM*7)pEnEN^}MEc4^(6)>4aiS4YoOMG#c_$5nW'
    'cOC`ivPaA#RXngfkN9vRsmR#AIgwPP_vufhRH3&wkz&Fho=8REmW?M;;ucF2>1Jz(7jq}^h{ZkyEHQp_^y3N~6PrS+0%|BCGuR#a'
    'h6(7z&W0YCy3mIHc&}eGanpvbxoF)!o@E*%c7ceX@iU4{EMV#goxM!<#;#8`cRljkbdqU=uIOz(ViDREzQuJ4II30U-{NL!6_1Ff'
    '>}(LJ;pw53LCBeJ*>M7M*G+@1Vc0=K19k?-Ni=o*VoZ!>nO$9He;}6-Oxg2v#G$XTKt_aW9nl=pT!jdPeT8!ytc1UOI8Sf?<>SNo'
    'UoP(+mWxa`{ru&}51$_X-~1*9{Ne8(K7M%n;fG(}{OybS{Be5!r$77ubNcnm{Fiqel;4_^3XC=(SDG8H-@JME)4QL3`Y8sw%HUdu'
    'BPd=6RnSrc2{PE`)>de6P25wFAdIH;`sCQt&Nd+&O?qG$S<4F!K5r<5S}Rnp_rEse-G;Zo5U#UK;$OQ<6LdA4+_ORxR}H|ZHFi4p'
    '@L}xVet!Su;oba~>DLcGfBEaD57&pc^Pm3mPP}=OVyW-`m>)KXE9O~g2n>_NQz;GBwUhS${IjaqIYyF8aE0QZY1oY-XN895tT2i^'
    '!=Te751$qZKvJ?~f@RI}(CB<ukCJGBv@o`95yNPuiPbbti;i()sY6OO7XzXW!X_NjW>C!l;6x)}&Awxt9>kUt7+P4y2H|7K4VJm`'
    '{==7K%H=;>8p-8MkX_Ak>=R$@<rU_b%D!EwZV0irX$QW}VSp#RJgvB=9@k_<^UT6OtYP6A*wLA#lC-IbG<Wn#a*4i{CEyrdAOWrf'
    ')z>((zXo8^{d|m87&7A;$c(Tt<q_X?ux1GTref~qldP=#BxK2C=f_%TfeG1pv(R`y*&+^5CyU}5d{IRc+z6a%I?n=PL98v@>Uq4f'
    '#sWK9ovE2`G#D58W+QhUBE%vtfbPeESmH;kDahE8M1UF?9N>B7&zE9g?q$0k;@O_vY0(;lP|*SLyhO6w42s%(tg*X5i^i@KRg2bc'
    'Bv4raM%1>Oq>nJRZa^PkMPnYyss-%?Z|p;ggR+;~Jh(g<6ibMX`fLyefYZPr1gFrY+w0CM7XghAF==;+SA=tI<!8uSk&E@PO3eKH'
    '6$`z7@8*kWRS0PPLnl;oZ(Y7b&@_y%D5eys!A3r{qpOoQ;8NkJ<=vQmfvQWQT<8T7R=TY6HP?w+%sEj=q<V|X5CFTr#t`sx8G}ff'
    '(7#}DDQtch$FMW3RqR9*YwoGLcA0|7ZVRDa(p4+&sjGzY<s3VT=K-`K_p%IOO<V-t$xM5J*_>%8LM`BSj&MaZ@Aw^Q-c=k8ux?_Z'
    'oF&#e<|ha>C+|k<p(f?_mKSO?-i^{joxUc?BhB<sSd9$G8IMQ2py`i?fYk>Bc4}D(USL3g=P#7336qyEl=rhqhLS@KVpCz;FVw9W'
    'o#desOcPg1z_3t=q(O6PMxLy3R4Rck#U%@2bjK6O`{O0XGS<SjF!Sfvpv?I6z+gXO%n1zg4X?^7qe!9-@(gmzw5fjhWtlYbx~DuR'
    'lE19aAu_#sWgt2gcV0kKTxCr;N>dXuM}khUqaFB5M;VEMe{>9J4K$%C0)VgOr^JPWnHB=2WpkT)p|`1lrmv;%DY6DT=8{BU=$Ko*'
    '99h?-#V1X!NgH=Bu3qCdMeuZ;A`{}0-ofW76#$oLN=>KNm{RtXyGj{-VGYg)S{*!D0?EKS{;CC%LlzA)Vgo}*a|KlNqDe;Vgzy-F'
    ')L;Zk_A*z^+UO94XS;|2C^ORN<_@WRtpS{uxXfr*O=#QVO!BOS24+$oOhMCM@vMawW|AN17@pA3W|h9cgwENhAq8lZb1hS;TQa6)'
    'Y#cPxB#)_}m~6Zw3tByW(HUfsZ6FU>odTE2PN(TAQ;q49yyXDGErCZ6`ZX*c--o1XA!K_!5W)0W<3iA*ouSdlyojfJIIj|)VzJ`l'
    'p<KEeb2rG4tg;B!o$lh?6>5B>3bl2liekhSEOz%i6<Y6}r-5m4be@J9y8ZK1#A+*@^HfB-7lOnt&$9+^Kl5u?h~ktjL}6(>aGCMt'
    'GotzSdH#}YJ9o+g3fDf7A1zubKf1h4e~%kor1FU)y^fKi&l47JSq{O!{e*oD14I@BL^3{{u#!;{mxndYE_e;qSt?jPWy{=_yhUr*'
    'b5`;etz9}I8nkvE9w{(dJ8tB;i=stqmnTYej|hUdnd&bvYiE}SK~m(m3llI;PARd$`r3z%l*@%P$=)jePVu6u41hBC)bm(RE1&s*'
    '3=F9eZXCFHjXjKC^ByLn2|Jh#sOtKwpLWu8lI8NkG-?~t<6Ah=0;NT!z=pKs85-SZiQIxbqlE=YN%3ecEJ(_TM@zuN*TvUK=|=Fm'
    'qBdGYohV(g9h8(zb+6Z0QMjZGQSeia6)Dbl6sBk*MrT-3$!kj06Y15<YhsENK>=0`+yGITHKAxKaY>+FA0f@o98`+$%t56Lo*k2X'
    'h1p>f!c`^)*6wMow8Wd(=~etdu%)LrVR8Kt0mG~$sj7Mc76Im@vSt)mP?knj6!!0MWo+<PN2@0LKR!+G=F`vqH2d^#^ZCQ4i~cx$'
    '`aIvPk)OhfhO7zD9n>M@Pb}m<73eTG(1qKl#vHCKpwogpgPXR6AkPr0(}Fxhb~-A_GgPOik~~8}?Z{{U->Z(8e`KfwvnItx`ag{+'
    'm8CZ0;1MOnoX^;94}_S5loc<7VQ^kswwL|v+dPIhT|SPSQku2~MK8BS1|rFw+!h&%2oG{wyi5;rTcn8v%R5O@(g@yI;^m2$unlCV'
    'h|trl$BZ?WOHJVlu%!ZdYe?J?T6nLAe6b`6jU?D;6uRmIaqiqNJxSm56_SaGfyn7{%RnO-i8Pv3ZKl$u3{^~zFQG9q9vX;@#KuCE'
    ';cAS_?~JbA3+;PJgn|Ctit6X5_UBa+6S+Z7gpS>3S0${-@Pd8WA#}3(&PzLl&Q@*aMi+tCaWsShu00$=%Z6hR;M(-P=k~p^U`+q#'
    'uKM}4{dv5Z=?|e5O?F&)wq)&zz6#Zgj-gfc5|g?aM5|QY$h7KEFdoHJLA5`MdOQre9tNq}7n>%dwfx@Hn~b#W?_;*&U>svIQ}^K('
    '5oDwa4b#{EgnwM!vC1nE>XK9U5(DiB<Kg09kX$2aD?*uoJGJEM9T>0G$s2V7t2fVu`ZP8=mqx@Pk}S6<ju~*-OsDb+ZrkZp9xXT;'
    'u`|AT3Kfy7uCcaj0*1er&G*ap_foghX%)KR!<A?b=T)|5LWYrkrn$l)G0;n(2}sEK&fX?LDHG?ujG#u@moG5Gfu{2lix-R<I-6i>'
    't`4~(03ytwSjS*@xjKBCAy<b4XrjO6(SW1B(atZw8gg~Wgn~{7hEmhB&5bGR+0h8^h0IikBfLs>Jol&Rj<uybZaD0Y-Utv!$1&Nv'
    'LC3>hGC^dh#k@D}jt>bLq!Z0edA^5r0v}&EW8I5}gbXr4rL&^V^|=&1UH_QhI9^{)s#=+BtW3rBmDwqDTV58i&s}9|RV(vSer3nX'
    'G#o1v=I2u8dCtm=1;8lnk;6t;DyZB|qm~J!9E}Hc>RkCeO@A|Sv2>ASsK4kPu1yDO?!*<Jq&q^$(jAhBgOUMqY{WrTeGAnCkq(Be'
    'QC>z;y6ems=^SBOJ^hFO@@{_jdH#}n=G;~if+9?ry^~cj=C)5(#khLOlhwa(0UOmchnL)8683n3+34R`dzC`eUW;OlwI+CNt@%bB'
    '|8jkTYi!W+LnUiVuKcVCZHUIqR7|ts?{)20i^j}UrF3`4%v6kCW?{&em*FjPqM~KXAs)?=qqOQYa$_Tp=1QdcMRz5|Xb#$fLnagm'
    'ia{L*5RHGU7&HTBT7^4?U6yr7^Yw~vF$_g{Stk^gAI+H<%>~|gQ$jUe<E-&2%I}*vh_LPNc_$cEgan#8eI+8<%$GBnFI<>rBBl#I'
    '#bf=#6<I>&5>M3&m${@n#S5QiE=isWnkg<@K2?Kve#KR@p<G&Bs%F6EX2Pu{xJx6qdces}QoIw|EU$^7%`zKd{kcjlOef}2I$%um'
    '=ww4FZpQ;|o1N+0ew?+#-$Na35>xwoP#YZws2^VX?V90%_Tf&Ce-HKVPtETIYt|Er3_j#Wz2I&Z@=my^Jf4$q6H3@pg4^1(Ex!^p'
    'qR8>j1YSqy=L#K2mO=+A)V)Rtbf>Radoi}+t)){m-P4~XCu!meGbyM*@fo3R;T!(x@{oU}P@u>E_4n)Z6w0#Fm*;YgB){fwR%U=R'
    '$Y+Dl6p7HF8C0SSO-9{IoSwpr&=IBA=EeJDiRH4?_$yP{QVtQ0mz;IYWnLBmfpODC1vEDdMP0lM5E}PImX4#m?l`Ge1zOW}Qol%V'
    '2v;1=oAWXP#>SbYD#0*gu<|83DkEL<LoSO=4h+d?jTBi38IoQlr{|==KjtLi=eksim~hs<l43!7*Of98X$He)o|LSaY<YC0lsQ@J'
    'G@}S$5tEzS7&y){#a>w7if}{3;z`6(l4?{4s%TcXH6J8>hTaK5D@jQ%7K@FLuPJE=LTq^p#)_y=P<?v~l-A%!tXv!A5x{nKb_oO?'
    'wp^@8(hJ!0_z9G5S&J3fhLVniEj~ZgtRa3($urJhYf=!UXpxS~SA_0Ss(2FX3xLRpqGDMt{FO>D+~EARg7&Dj>N!H%N!kLz8$q%T'
    'yzxoqx=Ij66>6y80R2+_-)-&mjqQvgIV6A}L`u;!5_31IK(C6pIaVI0VuOWB-6QTsFC23>dg0352wr0yx<91+F)WWe)a-xGAKuMh'
    'K0Okm_wM9J$z-D;mGnjmA+y?%YH)5{U3mx9jPHaIG&9x8Sa%4`T(b>XvNknuIUw`qpt;56aF@*i=(|OmznAv~EeJ>BLeoQEEeXvd'
    ')NDh(0WN@ZjKtB;Zn+M`x{0wYwFAN)r4=eC30AjA#uuJjC&-_q_f80{iScjS10YnxMl%rF{aqWkLFcGK9qLUwM-`|_x9J>}?!hxT'
    'd5Y-)GzFtgItWccpVEV9O8S%@MpM$KNMg1Vqb?ABT68-^w#PuPNfDO*PrK}sz71iYoEr8?Wi(-*T*o<KE|oEqd~zLU$PIerlPc97'
    '#^jTXY|8;rwk{8I?NnQR+2xUQWJ4o7wWrq7GqB4Ws3>ynuD-7v9tEb@kO-;(U>lJLD%%!}$q^@u`FX?KSJ<<#ye%xh$_(PNxF>}L'
    ')=@<lN&Kwr=~x;PCV?y~=us+~7_5!yW!Whuv2H7Ed(4U?qiMG|U)#&%>Og^f^|Ob&eE3+UZ(x~J0bW<QMu~+}S{Qb(pJ>Q@;p>E1'
    '`%VM%vc{z;YbirWiaGxtR}u1!bmgDWN4SBJSh@ji4Z>8CSXsvi6>MgGTz~9L1MVtoIVI7?wQR2~HO5O1j!rxoDggcviS4B!u~h-c'
    'w@$1Mq18+G-Ll+wocl#71@fo>H%(M!mEjN5ZF1sEf7nUo4-?C2Q}GLwehU&QT1u!FS;7p(nRZ_vMcExYW;RfEM;vEKdpxKiBvIxT'
    'cE?l)Ep|+GFsNGbUAe)bLiVU4nIeR)eFfWH1%udAAJ{$hMGE&jRG(w4+Az-bhT)hVZWw{Sb=@$`tA7_imk*09euE9e(M^zS7>?iT'
    '?(PKL-RDAowhopU@9s|E53?=a@1;NNGUpGI&F+4!22753c!%!-?rXr}=A5rmWE+KZs;XvRQD-Yx5o5C^2p%w=eJd_|AI|6|2u=fH'
    '&Qb<KUWe2I+OfI1ppO9h2;E$61oqV`EJtrHoMUwZQ8ge>SR#Lff>E=$pM4Ykw*N7$w9(XK(JWSk>qPT(DCnKZs_$wR`kqysI(j{t'
    'G!r{1GQNcw1bC7$ubEtVx?zGAnfbz>F6T@B^btFDibiOr2)-NVNO)O$cf_e`lpFEpX+{_BrCD^E(aSzjN6s{>?)rFr=ct)!iS=oN'
    'iuq~CoatK{G>E#rWqRpBJe~6(LiG)((|}4Tz$9KhBqTF|f@YLR578}Z7PqlA7a*~KL=MBeZR<eNImkWG0X;dOcG8^nYHoh+q?2pD'
    'pW>nUIK@NrHpQbnS~MAorGw)X56wx6hZC>9kBXdl?z=|kAx9K<Iv^?0OoSG@`Qn?P&iz)y92PHAV@^9Swbe}G<Ea#jb8SzhnA+N('
    'N-?9gJC#h6ESnExZrpe(S&65Tdi5BSm`-^}I#tHX*IJ62K4V#gb!84L4BhfFy+VuAfkRIV?$!d%FulG5AhQFYc}&A4eWypQV3^4I'
    'u6BCCTHhpZbs~|;-($D=kSxW^U}IYl#bzvIC3s6H*FZYJV)yn0AzSX~(hWJfM$(B=6eEN4o*)#Zi%|H93a4s%f8w>rLtOJVEut~m'
    'rM}cc3&LWVP`^5`i4K@Ay^JznW=};J!uCvyH+$)FU7L9^muXSP%GmLgF&K~H$EtGPw5Ukj7gEi9d<tvv@oC$P-WT7SraUfC=gh|M'
    'A~U`$jr}6#T8xXBYuOet&%-H65%V}ZcovNfD#?jKb!qbyUs|&=B{b@QLe+IG4mxQh$Cu=Hb!H_H>?V_D86aZS-q&XgOH7p+L}PE4'
    '2P{)8LwKioz2?iupHylPJ6Ip!2;iDLToZN(eEaBSy21{}bGQ7|5ku)KeynMsywo$7F((jHjk+YU<Vt-Br4*4|tt-b~-*GY7aj8f)'
    '(Gce?sUq2I178(d7Y$_I!DUPYEH%x^RkN4E3gn+$i`RbX`F~BoZmlBxi*7<EG947V+s<<WzH0H}z6HK|x~sUP5`^V%Sxb41su(@U'
    '+kzt^f~CR9yjoS|IIj42sT#+E<aPYjEpd_AJbcd_p~+mUO=zX$Xuna3o%wWk0Xr4zf}}Y&$=5eITsAqBCIS5Onn3480<CiP>No*u'
    'RO$52?yM52bW*r(`LADmE{NRsn3X^9B$dIW4$i#(qCA&HX@(R#T3NnhL8w$!AuoZ~zY}r!PDI%@i<*GXv;qoGV>O=9x1b3^qJm~?'
    ')gcaukH{99a;gKHFB>^6Cv*Oaq2Ze3F7$96I^-^F;yS#Bcm<8CAl<%&-iF6%EhK)%>1z!x_bn*+rh(^ZEk~5!Sr=N8gsvqCiJ;uI'
    'R^(e^=&x!)t~Of~i`JSo`jGS)v|M_NbJ4n3)^#$|`VfN&(yV%QROXaGnOa+MOPZ3_5X0%`AAeY)DqdXX1E?lEo0p7EiA2kBec~N%'
    '2lm(LhxzZ*>FxYk%8%2-r}^^z51*!wKR%qNx8HyM;v4=je}8%S{L_br_g~(;dl%~t<oJ<>*5%3ey-tK_&-ZfIrYRS#M8bOlL(aQ^'
    'VYp+R+n#Uin8-$EAWWu-5&lnlxU(B(+vc!G4y{cGRGEEX!*dvJB4Icq>XZ%tC;599C*Sy0QjjdUP=u}Ifq1FInN<r;gVT_Tp_M3?'
    'Nt(A!Gp^d^Ws)RqiRIBGNN*?w4+f)q8K#grmUE>|Je+$t3}g9f#+_^@GZ@gu@z?3sw;!g9(4Xcom1Z=xt`A?o{QPNtvlIc%4wtcb'
    '$3K6P>s_?5Sg+?#C<|IAa^oUXcnN?E^WfvppMSirGXWMhhmRlPgmU?>#P#|75$!Jq9Ik4|c>>J~d|(+zLOD22Xya{j(%Yp&tN#sp'
    'E1RojojfdDE<%UAkZ!scYSH7#rw<XGEG$l+B702v^eL*-SwWwodtCYSDZ0~LNuOe9vBQseJPZNnbJ3bGfsB_lY3(2jG--_P7S=Ue'
    'kacp1r_~V4hLW7E1+A9nIWY5#iw_tO+5xeo8)U!@@P%7=m2w6MNvA1CZmjo}B??7npT661Qs$NEO_9#Z1WBqEVw!p#P~au9`1IXV'
    'l5`Kc-P3&BJ+06k=hOGkFp_8n3}06PT|!)-6AO%MW%+}ws5}^akb$LTx0i`jz881{%Ob}h07>3)jduu?ml~SeZb<jx@v!9b+@6;9'
    'fBBjI;d)Ic<IRR|(rRLf?VX^BB=(sWabT6D*J&=#wqk`jUKgjEN}D`@PVkQZm?I)i4ANHfjf|5OBNc{V1ZLL(shyX>AQGN-6Q|@L'
    '+77uvQ)r_+T=VL~q5W{(V*UseSGx{wkU(*D;#uu>!PcdrPi+@A3OQ&uEac!t^a|Jz8NTUz`f2AR#@yL;i!1$h!vZmeQ7GOSU5a~I'
    '2Kud~TQDD>VUf<TR~gYT)=)T=pK*lsiIZ@BCvO<tN>@2zDN2<V*53)t`Foyvh4LP+WNuTm&p%%d$(&385<lC%Vwe=f^I2jsWLNdB'
    'Aj5M&Lw(Ho7J59+ijr0Y$_p;(3$!M|PPGI()g?=zo+t~g(p)A3b)NzcNe%*;z+gH64R{$0pmW}x<>N`zmU$>|Bfd;5%bWs5h5_4{'
    'V1O}q=Szo~{aYs3H04pI+-0a<v=^aUx(n+N;C;)RFW3BL$B41bn?Rije5bgHY@%$2GfXb`<cok;`JagY*>Fy6noyyuY;atV2%^K*'
    'kQWlXa+}6t0%{kp4Y{lhMjj$b)%BTSGc#+DD`NL>)k)vb|J9o}pXCqpmpAWz%HOSdJ6~m%sb<RLmBY0~bEb2L_AR3!#JP0K?adi('
    's1GNb2(bxZ(Y<K}@>!=9z<63YTE*NjJgpq;%pAdJR4Jqlagr8fM4Z%*o)i_p5o6>{062~g`@k%^NwMZzkUXR%R!;JejF2RdHX;5Z'
    'lMs*Ox;IZqLFpVg3KSWkNWYeQ08RU)NWYd4ouDl=dB)|T1_>LXb<;xA7KV*3*}Y7ym+V*FiRXUHJj~HtBP=<=RdXfdTZ~U|5#uHK'
    '*Ow+!&LnEge1JnZzu}T)fM@D5=ohM7M;!h3!pKP0l49j48AuzO=M%+CPWIuJVbDmynrF<Uk5WKm169wEvV8{aM=ZKp`qBALW$-i3'
    '4Tpk}_%bQCpl>l%F#|M`(zLp|(&yXJnN|7-t*)-L2Y_k9_}MMfx!QT~1%>%#{`7GD_079@MHM%tH-C-yRh{CkZ{Gatpa1XM|MU0n'
    '-~IIN&G+ZGfBLsS|LtGCfAi+_Hy8etCcTU#s2x|`i}Y$zKmBr3tmk99EF4~=7!~I-1y!X9K&~^4;?Mg9Vpt0^6pL(PT6vFF0+1a$'
    '_e%PFL%;kI&;63*w)OOp7+gw{%1t3IJg11R2{n;dWWj9Otd?);nLL%A0gV_(QkU|2dXe0OKTJT_Sezx5X<^C}u+24}pT_2rF56rI'
    '3)5ftd6QR0HBt9Vk&)m^6S^}hQcC1K0jAE3RrA-6^ZCns`TqKL`r&i69prxEN_yX==%nupCtZbMy=bFA4$i{zF+dZ4Cv5sE$1{NT'
    'Jtp5RVm*lBm<pSL0eB`MGm3h6$5z8Trk>x2Yx}&_=?G-+6AND*wlp+nL$h9UL>oQpr?G~m$mVbWhIF7SAG37V=ntrn9iv~%U87$s'
    '!tu$`49MG9B655#zd&mmeAj5|YVBG}Hp?*oRjWW_#=fYwIKf|D&N~x~^M5?NzkK+|_n+T>`10nLe}4G<Y5M1UI%wM)NSB3fym}G{'
    '<hhQm1SBDfy_8qCE<)*+BUQ$%v!RI21ByQTCT;oTYo;d*|Kc*sL$v@R+UA7oI}f?3N>rlEMPmdCL{*NB5sEkz=XDT_KtY|W?EqK4'
    'Mb9e1R*b>N@OKI6AM;wXsp)N5%8(N_qHrD;Ijxr@&S;?<m6BRNmB`#GGEK;$yi+-HmB|;5mm<}4)@J56z}Bsy%Woo&j|pHY#fuaN'
    'FsTgmTI`6(Fk$V}&w7)Bm8oBtuh1AvqBvyM2joQo5j{t@Xx6eq(-R0hn;eq?tg-g01HAvHLuf9&0@yodj5B-3jAd%?m<d&-ca9k='
    '*mE8;HX7>vo!F8c;>ia;6s{(~wnVs;_dF~0jun=wO|Kio6>XVTsU!B1RU2oN)#6!~tJVFTv3wh~#CxhSs@*%w&kY<>jg=d!N$~7v'
    'Q;j7i@{*cXz6<!CTA;2ffGr^F*de{Rp3MVU=x(*YA*Q2}1Ljg>rZF0Tk$>0`2U3$Bb9))!uJO^!TZBM2#!o+pAgZW0t2vzg_AiIg'
    '#!wSG)P(x@^Fz>P{-a%q4%TN{{7fZKD)cjamg;^M;4bKm&(gim(sttqi`9@ON{kcbwE%|RS8?14V>&M~cwx;kB~+&fEkx*NW*RT^'
    'BqnCA)>I-IU*+z3=Mm;T3+8RqH@-Fnx8MstUEY2Ew0^6@<!9ry%k*QGJ!{y^RYmXr>2oMGR%~9!=of{+`uZ`BcRt2(F}!ebq*TOw'
    'q5GZVqo{q}FC8fsF~>k&zIAuiDpq*t-A<(l<4C25y6~;3u|740mq}P3auAf4>xM>Sna>a%kf}7ovGnQfdhL+fre+<0K<<R0rPPB8'
    'iVU;t`*D4mK&KWt(CH#qerNQ`_eEDakKPII9S+pS;6dx+lqnVKK6I{P(xkDJDG)>lV)q1fb^e%NrrUV<8DBP7#^p1vXdB8IliL(@'
    'hijQo18sfI+LDCH5?vb=eWsHwtrW4Wl=H`5^ZOOO%~AOEsxDWyZVoo_=#8(CZQ{{;?ESE1)ddsLh@o8)fV*UOyF~Fb6T%}{2JG9q'
    'TOA{$yN-G(f@sj~z&9*s<W{)NXS6)-_>b;1=M*fo=rJ85Ubww``UY*JIe&6Mtl)fy4r<wkYP&Uk{W;5MsTKNcsh`s#uw3yS%hF~f'
    '%xd^n*YK7{tmyM~(l0Bw^dRLg@XJE4T9t{ift~GH`{7qxzaN(N1D;tQ&_+Uqjzbsj-O;pjwi!E89Lt7^y3g5H!8$fRcW8bIE{W@n'
    '$QP{O`Sy10KPk^;0|4e(`!9K;Yd)t{B5_w0Z@WrWt)A7ow*fDc(zj9<^55y*NWg-YEm>5TBN8#k+QiS*yPvd)oh!X97!vvKcCeL}'
    '{@AMICnG}af#bld4Mk?V-v<o!q{ITPi00hdLjhT!=nq8xJ3-9=G{%Q;I7kMjbLaY!NyB;I9SsZ1<tilJVOh!KPIT5v&Ud1-zKPq3'
    '&RSVrCAQI7D<!6YIh~#+ItwW}YZC=jH)G5O0w|1ivw)R^oult^E%!XZq^4;$qB#MjZVMFVStaob%Sh{Tz)RC%mdd|0x@229#r7~i'
    'Jb`{zHQf&XiK718?O}ud`+^PnZ{bf1&NS~q(juHr%o&N_TXY#OI?2u4DjQN|SqY*EzZE@!UemsQD~fWw;cQzz>5}EJ9u~imZ&DOf'
    '$Wbk4t5O{{T+X`4IIAa3T!5F-AVudtwUb8i98xF_?RVw*IVNEhj?n&A)Jdz0E>L!A@CG6&6mD9Q{qxx!&{;SGWI5RV|7K}hHI<Zl'
    'vr4stnYVhS2sY`|ppLET6qweu?^W`cZp>&^uo(rO+#A`5(a4AP`MX4VkglPNnW=13(t-Av)|F^0I9mlRVwqPhaFMe)qOoZMR6*Iv'
    'NPlsc)6hGfc^bN#iY8kfSAV(Y!ZirI(Bk#S?|A*my#DksD3HxT&07Ma&%|`lLUa!QRodb{A&X!=`(@-xy-R)ZtIYb63PXNMwM1(0'
    '1csp6;K|>tQ2O?7<)bN22_O$iYl&w^w5lJ-{GoeblYMP<v<~yBi5X43tSvz!=&vokpZ!*ZsMU51d+<Ui;o{%Qpiz?1CNbJ-N-~P_'
    '8_I^}aLOWCxs=%iB?ej(Su4^m_}kExi9p!CQ)T?Y;GM_cU8XM+H@^#q#DCa0A_Da8G0kI{3v!W^9a1AHbu}RK#3%~<j_e%em&&g5'
    'RY!jByBq`QraT5(l2e56*LkTStMl@e2wedsIeEu+FE4hlG4wXF*ih?roNq&8S`sZX(}vn}q{Ad;wGkWyZEGe{4{iZa%2Oj563%+g'
    'eTn<XvP)p@hb(rg-B*hYO;Z8)J8)ATH_K!fpv$O&^Wm2YZ07_wBBA6`h`h_o+}O&r)XU@dyT6J|J#PbQu%|WGpO#iaV=@-KDUNnF'
    'eZNyi+A?QUAJjb+3^*>nXuYw~5cn0DK?P3yig9=Q`IF0EZ%i);1bI3q9{2aZp)ax{cJ?w%poq`J8n4I#Yy?cLYcFIp%>u{|0!9my'
    'lR_Ei(g?xKlP$Qgrl1z?w>GgLva&?$sC-b-3vag^3X0?>r15}0L}6L7=s-49W~->>5jzzbI^2F6R!JZy8|3hN8A(M{?G+1XN{`?0'
    '<Jp8}EYPzD6uSaipV74UGhk?a>GpaC%#i;#-Of}ssu8j#AHEPX1&h&5?oa|58Kv;Ep<=b!W)bymV60a+Dk@NV<n%_5oExe%;0mkW'
    'IyR!y^&(Y!`MC$KpO#c-F_kBAOEO;YigAL{8Au{S%z(cU*U^=Ftz$zz6kN6ybiXPKT2vq#a-kwpgmney7<rlMnivDS-$jy^JV0kM'
    'K-Byo7aT5`AJO=_<H)WokzHq6aQuep>EhLVUo+N?H3Q-|rx_Sg>y?jkB)G>{GbV4RuAknxnzlr{z?h{zzDBq>Z^<xvpyMbru;@zl'
    'M#js`Xk;J&akje1t1iZxCWSxx^6)kZ<i`7@Y0QAMcY0ZukQxF+bA4W*nOI*HdC}57_?wtb!02_^a*;<UsUSd0s~gZb{>eJ<4K{A`'
    'yp)7I&dAh)s&sQ(&=RWB%}~dYfnmcS3`OYwmA0@=ELzfMq%`Gt^QA85yB#-iJ?C+Yu1Yub34!FT!%mS5G6+!DF8M@mz!}~Z?fsg-'
    '(j^nvcbR}-Pl)sz0^eJcUQlG}N$w&1gT_gQz{Q#f@6;LYR-s~s{5?W7he%xa>qqr`;d7Qsn#wMTOf`E#d8#Bv=!wV_8=e<jAx_2L'
    'ijFIq7?dxNzl!>1q7Kvg2ILVfJPx=akC4rMk#9ksA)3o%;Fhh?ia+?C`W6nE%D#bWHd(rpbK5`9JHZj)sYpkf0~mD<oK}p-<X~Qg'
    '@%N6;ce-<>;TMbzhCh#ti0n}vQY#4cl<S1StOvmyzRUY9#4teM5`5l?ykFyq=VHVl#2D1+g{^Ow{krQs=SWtb^I{y50`Z#*Nr6z3'
    '4CikkCgA(LTf+tdV4cPdvbBlVpW(l~xojx$Eyv$ue}ms+%`MO{2*CQA+C`d>&B+mnD{<AK8Abd+Vk@+`$%%^JOI06d>arXfbBsFL'
    'QV?fq0SQt+M+)Kzoxe7|9w~F&bGM{yY4tU2p~xd#4Gi@S$RidYqM?t_f|$~06fy%DW6{YsnWr6MtLK`DA-g3(AbgiB=`XD2nKTUq'
    'E7ex;BAFr<kys8+`R{h@NTkZjb+vks7F}3R%PoI?oL!5}IK%dcz@AZGxze)l5{&p`!5eWzVV5;74x#=sc5CVKa&^$$|4HmF*;Lq='
    'fPqQMF(~R;;!0qkI3L*7dFxc1aJ(-08H5iPlxUry9E4J$Wz)aV-bqb*hdAg#Ny5duz?f(HZe<4jPmw}UG`|E+HT2lGAaz`pIvUjU'
    'SBBSH0;i8KrrA~K6D%f7JXRJBlqDbCkaL0pGOA4_Sx{gGhI?Mzfj5%Y2SHv{p6kllu2)rj9nE;dA-&3Uj!!O;uebTnXl+rh5D3LQ'
    '1>Pjej}Q~2%ZX#JvPW>1H;JmQ=o#Hxro|WPilP>XG$Ah^EytUQmW0#m(%eddR)o@PZf+$(M;6!qh7<s_)rO=s3~up28^TFg3e%B@'
    'i#E26SEo6tEyi!UUB<`fJQ#}?psi_Q#|lL+G|*c`i$!WB__>?!ag5k-3GDcgrQ{kOb3J>R9x=Osj+xM#=Ts;GdOJK7j9<}@X<mYT'
    'E6EB1q+|vK2t<=;ma^|+8^EC;BilkgQ;{`=e9EKay$VKaWc?UL*%kpmQ6aWPXXe-3yHuVgMz=U1#kEjZEkcoD6?%=n!3@jBfk~wT'
    '?rK?^DjXQrHRjcXz(YAe3wRma-@-OP7eK7Hwm4X22?s7o+GZ+k$}Dy?f1FHJSJeYU#nd1a7VU$TAYfPNd!c!+WusDMU`qxgE>%|j'
    'oKuQHT&fH#A5~%lE2x2Dh)mz#%(aq}nR~8hu9Ypb>nd~iH*>Ah)$q>E%nbyXw9TcR0$R4SvphiCW?GjYni0$n5_2Vb@40=i8P6`u'
    'tDj%npI15Cbmm6nNB7wg_<<+}i4g8^>N-We1=h@62aPqAWx&M!&D~I{c4ROCXG4PtxEROXf!7h*6fEo5Gojk;o;?#FrXza>B0W;i'
    'o&njE1}NQ^Ftld^ujOjb*w^&MMDfKysXkz!d=X|@x|`XhEBCrFQv$K(aKU7Pi@W+H%f}1G%JG6J3FKu>z;I0f+g}r4$7{mz;hJzw'
    'EydEq7z^pHiByF*uZhd)71u<r00WK@QuCMyq_fQ2-*Rwq(=5wDH0OuoX1E*z{`c;dLjduPmV*<++I8RxT{(%)b(e#adUrWE)h2_M'
    'eyAn^uRK~c=1J*c1l{$QgGRL6&Yy*^xEyj#Ti+>Y%Jr3xF@hW)2|K-tU8#n5H!~}mmFr?@&JGvr9rPCq$U9st;Kqx^4J#;tE2S&T'
    'VrkBfGL&vNKID3Zo~I&f;zQ}tE){yl<ZGAwD?W@5xd0<Zi$(KSTr4O4$JD9lHkZXB0Dq03=*$ZdN^x&%#rKIWeYp}RJElbAP8X56'
    'yG7zwuycWTh}xZY0q|Tk;<aPyO#n9ZryZ+GI*=hAI>e4O4zXnIi|wc;nHSX&EGgUHgBW_$UTB672RAC%>X?&vXAt>LQL<-5w(K~g'
    'l-g3QyPOvei*`BAMRS!&E<1gTws;<p1{BD#T&N2A2=Pr^&W=aYitZ3`NsT{&Ws2S1uEQ0@D*+xoO__rw;L)ooNAc*zVl0nWEG?FZ'
    'xDs3_U0q-DlAL14EhnKUPIJq=+}@w|L5{Uw)xp*bYv0MS_8q}WEYxjhGVujdH9iTb{M*J)@OJzX_|gfEc#1I^Adino;QoaU%T3o;'
    '93OVgA0*Upe1xd>Jv=^wLi5S^2>ET>j!+cOg%M3oD1_&_7wtueTE%@(&VPYRM%_)H^~Q+nYQ*t=D9px)n-;4_7aT40di#{1)c+^s'
    '`vyXp0X`>T9h`ts-h@jH9BXb=%X)T%IuGG;5_reAfP~D8)Mg1v=Oh!`JAq6@qUnbTUgIQ3cYCoKPl5n>k*w*UVj1B4M3M1+6M3S*'
    '{51H&*o(~YWnyu(>uFtnDKnyoU<>`<kwJ>Fg)WphU)Syouec6W%Bk^vBB-GAI=n@v-a2sGng1@}HaF2nz6ETfkDRn5FA~EXU7!=*'
    'L?1Z`b{l=<q{A5#dcM4(`Y%cQim~A?q^f#I8t+1iv*9kJIITa_U=Up(+TFw;IwfRdb<;;wjJ7of(WzJk>Cs!AO2v@~`968DlDk+z'
    '-w3DlOs|Q1)*1NhlpYpaamvt{V6c^;j2@4+fo8O+zU(&+glz|+ngdXe1hfMI_c#!4JP^8Ck_Iokgd*(@gl6zfde(eji<-ApsY-{1'
    'z(GVII#5X8Xjt;lX^HK#I~gJ^$M%_))IPI#t!Op2&$RkBi(G55KSUbFR=YOn<i8gUo3T%-4fRPaSp;_Mlj;Z-f4qjF27q@o3~l|Z'
    '(qUSod}iH6;95Lzen8-Jy}LyaP^=}$^j$7Ql?|Fe=X!@-hJmk<-31ei1ZB5i3CVI!K8)Kt{4h@F@E{LIxu`KXF{OOdRHT+9q(Ny>'
    'W?)3$(+lVGS9D+G3{H9tp)W;*#Q9v<K@>T!O}t&m-qGho#Ntxb`2N;qRA!1HL@_QA*+y$U5Q(7YX_P}XUF|ClpSF4UH0<~}CT7(n'
    '|G-%JdfmRr+-u95XlNt=ETeAe^_RHP>tbgTTT8q*Ix+W(qhVbBE>J^X&wxerGWW9j$7MmCaU&?c7im%@m_`sRBl$L%9M{V*N!*F4'
    '*BmzW$K0tlKZT=|4re(DBwfA|nOx((_wqrUIszPzPKqUUF4wJ)&A{bjzzRZ=g()_@EZ(k9cQvT-+#!Vt%EwTag$wymX$gf`33CPR'
    ';u^ma|IK-G$|t>z#kxWSaE@9|f7cu_nw)VE&1!XbrnJ?laLsqcvLx)Z&Kj~dV&ZDngOPY*m{){d=yQf$Sfjf|K%!Ay)`At|`EK?7'
    'EqP0e@J4PChF!=2c5j-*t-EYyV4J}#KX+`fFkH)7QXc3m38K678(=tHz@5-a0H#)&lRH@n0fugf>dqPboX__FIB%N7ZNcRxLNwZi'
    'EYf}DLMOtJt~Wr6zHX%%>Ne%B+?8&XCW@O^Ue%&o-KNH6#Z?zxx$r5vr~~b~7dc>LGaThNv3f(z`{@6Uz?$S1BybboooX$i;^!Kz'
    'Oh_ewmrd*f=Jon(XOsKux1aIWT*jue-{egSQca3`+L{AKT(4h+c&)RK>|%7GQ!zfDvX0ZJ7RQk*$6MCJJj_mTjHX!JXGa3*E&>61'
    'CC~HAW6(0UKxI>>(!$}loSV|Z&czsIc}C|GwP<=e5l7#}%Y+gVZiw=H3sP|^R+FaBu;dxCy}k{g-}+k|eMSX)3820bFA2oF&1X<m'
    'I5SX1{0tRH!N@I?s)}NV76c^Il%4i1xN2IQXbT}4T9Ffdi^S!*;KVw#m}ogk`Eh#qG+$5^+)x$Q%fG)oeE#Xf!}~99-uZuj%umO+'
    '4)e5LQU@9IDet^Uu{+ynL!V5$JkNPFBMz;zy32U$&d=lO_Cmu4t2@Zla}E%xQ&bI*6~h6t_h!KPJ^{V{l4O8D52|XH0dm9bHwZ`D'
    'uVS3>XB;5T%y57LJasTYfeH8C28iHc>7MF^5evJqV{&1~1H`2mEx^*kKIbqgF&-v0;Pwn6dw;{E<#-)&4I6`C<lZ1eEX~F;<m4Le'
    '$%l!Mj#a}1YB)?_?r)f!*cc|)S!#Kh1RE~3(!%ZxQzCJFreP9-4TnhxIT|LBh$!x9n1mc9@&;L6X{Bm-84iq63oS>f>0VZ4-k|)G'
    'AjCJV7x9XBC>C7Si5l$!Wr}LTyVkL%L^PQ?_b@?L<#eExA!uPn#47D&<Jv<yx4?(Uo%2rn?!x#~3eeioI)eK<l`1f=sU6hNg5&{*'
    'SWg*s$=V3^RAh(~?{a#@uLYjJRx(|IO4e=RoTBr2AQRo}N=mv$1B3AX40RdFw8>^x1}asUidU!?bAHAB>U=I8?w2Ua6>0<~wfD_q'
    'a5fi2KwzC9BeCAgSG2hVLfy5*-|6y-*#<^l^S7%CPvyV+Qt(z@uH|k#&$p^_B*g{m#B?qfitOHkeZEf?GoIheI9Y;TLP4*HWA`nf'
    '1;6F<Rsv0x6X;ZwxD0s;mT?k8lI}@LtAq!UIAxeei>vMX!|~y-nA&kP6l?1*=Z{sqEk;DXNAWfphLgCO5+oZ2_)e~#p5K4@^y`~^'
    'E-OLGAfm(<NDU;ZeKC>lOOg{)M>l-~#aa`m$m)8>>#r!33Q%uUVnF!t%iR7h(ur-As4g!b(Pw*+Ve}QW*Bd*8N;||I!A*Rpti%>>'
    '=6Dq=YRk8w<iorUmxmUn&&E_9L31omE2DIf5zGJdin|o>yh|w>M?2$rttqAm-DCwB-eKfrH#e65<Kg|~!#}?N{Px3_H^2Pz!{<-a'
    'KeIpPhYbrjc_Bx4e0MUNG_Qg#SB%E;a<Lb8(UID0J%6uQ@$%4Srsa^v-U}7GztyR$Q2w$}VSSFH`K1MA_!MWXPs0xB)972u$>jY{'
    'M*^Fz{kIH;ZH><&1967~MJr&c8v5#6R5_kdpQM_4g^2J*v4EVvq4H#efBWVXB6z~5kcp`<$#%brSM*yPWWOZ<zcIKgdK*02QhBzT'
    '-Oa<$ggI#JKO<#hP*HoyNb-oKWC?wQl1J8zQKM3+Wq`CCoVJh~wDrihCWE=De7Q@lBOl8xi_}1C`kjlc-5PS)`5ALb_@+(|*Sd*o'
    'B05#q*YvSn@v#FfGRm!3DID_vW>|4rVfWJOHZqV0gp|7TO*x7RP>!)6TpXV$?Ai2IU_wPlByDO?o-bD3;puCo>D4SP<4o#_&C@HA'
    '-Z>_6p9fKpyop-9w~1N}Z3LwJ+#IsN?6{DS7utKA19m&2#;dghW>3A2lcVlb()_WSN!7?ls~KVtxvyqmy&_NH?-otxJBh#sTIJED'
    '6mT4Yz4BMgfpXTC4x3P7<>Swve~h-*$NYDaSh>W<i!6qjR}QR&$G8X=hw{UxfB#*&dBfHS2)Aa7EGc5C_Q9#NkSkYWc*H8lbHZCa'
    'xYz67+X|@)U+IBz%MU-~>x%Se-IATGGMUh<2+SJ(yfWDRd%ovc-($9Bv_bbG*OOl>KfL|*<B#8;9=?2D2x;=zbo>=%B)^`GnDO&0'
    'VzHRabg3R_<t0B6*bT}Jwop&G&~7bC;2%2ERc<H6Hp?7iJ>@!7uc1}0V;j4&i=^jCxgms1bYXJ9ByjoGUn6J9tyeBK_goA}-k@Ap'
    'Vvifjby9Sd>-@BDlq>NM{eN|o>r@-STV=MZT+OzWtJQ{bwJpl^C(2yu!p&I~x?P7B1o!Jt;+Y$GYj0F;sgAs*T<iMEh1MNa3jfft'
    'u5w)qonK|Dt6XQt%H@plp>n-YA?3<i7w4o3&N`-Xn7Ke_E@#}_rd%G#RQHtY8=0PR{oie?T#bJyZAZDBNf;@YGsQc~^?z1d%2h+Q'
    '1uxVbDL42yL>Jd{R)ucYp*;(3{mdoGHS$*F7T$y{<yzTSu5BwID}#Rss;gYkW90&LmFxJHa--KfP;PR2qjKG;(ghc%qzm4O3#nGQ'
    'zTJ(=<y`M8mkZWaE*G5|Qx^YF@}6?J6hr0m!T?5;%Oz|mmyg-~f>0yno~K&5ddj*`?LxGZ<TKrLy~^yZ+BM<^?Hb$HZYPeT0RPZJ'
    'SG%@N+A6Xb!fCV%dP}=7zLnqs?6+$7>T2y~Xq9i+TZxM?CXt276TjvS+D%NG+u9AZnmz3Xm|)W#hkqz^PrHJqA`|V3m@ZdqS4gp;'
    'T_J}=5kcry?Q#LNc2AIXq1vTr&*1k4hGTeKXnw19QI+wrb`9@q*R;l=n(z;;=xW!>v39NLYS+3g?M7(9K)Ya&cD1dwJKL-aXqTd&'
    '_|B`BpYa17+^Aj2_PsRUsOzQqzjwT}6aFFZd1*W`Id-+1=p1Y927u96yHbw5G%u7$yCKJq=t6Llbs;-TQTv(dG}#%Xy3tMZXUM*r'
    '#zPhFu6A|DO~a!sP0vl^vQrtg$ZXF|;{mU;p<O$6)BJhJkakbH)~?c77tk)nV34t}Ip7Dn8~rrja^Fwmigo=o|M!lccELa7JwMI='
    'dFZEc#e065HwrfVG@fc+_q7{fFspWFRcqI#aG`J5S&IHZn=YYp9D1O<(NW_{?K^5*sjj2uO`VQ?h;5gEX6b3SQ~q<6^&B;>%$B1T'
    's%4M0YmuWSxU981$*hY`FjiUVrt?g-3%7b|p(ysgc3t073&paV?%>l^v#zI>3SxJ)t9jQ`(|pTQ(|p5I(*k*FLWx?tmvnW&1307c'
    'gQw^R<2j?{t*)AuH@IqA^<A|<GT7W$G5kZ_b=9;UyK0F*u+gsBa@DliaMc2f->O~9D_uy&vo37kRjYyw8g6yfG~D2-Y1envv}^4{'
    'jhB#NT~{rz<&BhUSl3kxY;|Mh8ouGG8ID{vG1Y-xZ*KfCH*8m;c2d_<*N9tPH6w3u)r{=BY5_#hbVuMHs;;YM)Yw%sy6dVLz2&MI'
    'z2T}EgIqOnt|PlrU$ZVu$5rzNSv_}+z13AS_6AqYK;KpCVhbexq3gP8q1f?IyRPf1S+?b>S+?P-S%zFSajiqU5>jlJTiz~3Ir9J`'
    'AYle8ZgtfHJ=U&vt?avMR<`z`R``di>#A8bcGaxvx@x!va7Vj(!&S40{&13_)`dJ3U39=Q(blDour;^3YS!N1s#)82)k68-M!Pt;'
    'YoY6^*-rI<Rn~RYtlM(cwyuadphTld>N>b9=N#Py)-J_lG7wh{_^qy5xC`CYE{MLX2A%X5jibAPji{qtkYiU3RM%AlwdJaT+Hlpv'
    '<>;zisH3}z=jblzb}8~;?A6*ex4LRzZgADW_Fc75&9%`k4(|eVT{VEQs|L_@)xd4JYKe1apk0StHF>JTyDCEqe8Y~bX04to?K*a='
    'tLFF(uA1Y0S1nXCZM2KSyP-m8N4rjrT{S1Wu9}luu9{ODu3ESrU9~&c;az2OcsJA-Z5?4T3GdAj?dn@yHD_*c)tu?OYR>cwMEpbB'
    'b=905yJ`-)u9|}_SIxnOtCnhBM(z3;T5EU8;oVRGvwNyh?Fz<jbk%&zeOFB|-gVVPp!aFCJK-OSo~tH8UCDuVy{zY|2_`pOHIZ0+'
    'y4n?q#wTf4)!|)ru~`?YU5fTB!ash+57amMYQE*ZuO^u3`f4I@?lgxi!#}h=UrjJO^wmVF$k=GtZun|~!Pr+543Mv;Y#rX!%w%0a'
    'yA-|6Ag7u5YJ#~NeKl{&?fYuJQP)=sfzP%(cnxvh^VR&HhrXKNqUWpmKX3SIUOM*G1eeHHQ&Sz@)lz3&$aX18SnS=i!Vgq8`f9%A'
    'zON>@?)qx}?;QhC;2)Zvujc<e^wqqq=c@_t_H1d_j(s%|u1HtyUh42}L4%6G%F^x(%KsB&?s9jduO_(L_tk`8U0+QEew0SL6916*'
    'd^P{)p|9p;JzvfLdBax|LX3SiAq4W(G^@kA+NJQWZ`fIi!4vkI0p53oywO(^Lhbu%La45<=KtOrh!U@%P{XdLT{HC6ysYP|`9E*?'
    'YC_ntuO`A3>8f2>hj;Z^WL?;HDf(UPs-|F*pa;T@zM2Rn?e?|ny1ttKdk1xeJYgYO&sP(vpj}tHsj6MAUCB3mH7_0eY9d^buG%$q'
    'cvoLjc-J@V!5{tHrBECp<&D0YZ@KTQ38}iing}K5n(i3<L*4V${GW%unwRx_HIWz-M%p!FUrmH7(p9^zj_;aO+ch-oEJbhXdhL>Z'
    'SK1qWHNS=I`)Wc$*H;tLwFaU@p0Eft=Q`R|Z0M_rz!cEYu3{U$noxY~s|m%Cucl88a#yAJu5Z{b#o$X+=B^Sqx@vyc-FMY|qpqvw'
    '|K70=@dl+-&sFn(9=d8m>7J|R|GeR<dFj|y6AD$En)F<Uca5F1E=>Pc%_?f{DtoJ|rtA%_nu5Norl4aVI{ZV|b=8y`yJ{&{zSeF?'
    'lOJn0m3ixHH{6gG?HXR|!fPk#Li5f_oH)By+STG#S51o>Ts1BGu37-7G-oV!)wJrmYFdq5HLbd?npRt`n${bxTDT!ywX5nNj=8w3'
    '3*9b7@-+sPk=fR&xxtChw(msfj^!e8ctJzgiO?{1A~bZJ2<^6<2<<kU2<?y)VQlT9S(aV2<!ZIrZW#}>u<PRt=Qrxs@EeR=!}~^V'
    '$h>Z5>;?Z&bd6ji$3||*vhL{C$Sot+s0|}GBweq%ooX}8%4~)i)lQWwkQ_Z>()7PUvz_^GFLp`0z$c@*c^w$DX!GqnE$lJrk9OHj'
    'KFwdypQy)|QpNn=NzOG+BNHa_D|FMyM7nY9r;!O$VwT~toisAv;)X-Vxc;GII#^$WV=N(Mx--cv8y`BBbq}3zn>wCkp%&3_l39)q'
    'ojKS`g#)ykP$q0AW^X4sg9I|;tVE~JiL=Y_(cYBE&z3iwLss?AA=`of8XR^B#eaGV*W+`@>h3v|(uGF~Hyh_rD1K8EZu$KGd3zUD'
    'Npd7z@UL7778bT=(A%Wp(y)(a8E!Lo*dAEe%X08|b)VZ=nK_wRUDdPfe_vUIyN8+Ull(;F$xRCCAeR(!lgV6W_L*6iDoc==BVfkA'
    'hUy%SPVp1b;{?xdup)9z8c1+}2u{)xLj_t9sr0Rg*+45I`&|13&x4dfZjPp%2_E`XSpv^o2A2J6;MqlU_#CDB5W%y1!<`^|d?&~N'
    'B%GvihAX)Mg6Gh`6XXEz1nh<#5Ihd<1YGUqPH;MQsj>v4xeSc`9CVT|lT`#K`#8br4Yo!u#R3TqaKlO3YjT0M#$5Wg#$2GSkv+40'
    'f^#fum*B++TO&<}E>)HQHCKTBpR&K?gXZvJ^TPx$?hQAy;_%I^04Q;iCLFGF0tjA0|7KPKyqU4Hc0lkrxS5qGZf10vx>Q+%*6I+D'
    'Hj0fcS;FewTt4M7g3}u;l3Y^-5*(n5leFrT3@wr+_brm8K#L^%ZwCY~eT$?wMpz^>mm2L6d<kT$Lx62^vgdrHqmffv_bA2dn0+gy'
    '=i)Aa;<dfCjif9GdSs=n&0Q;{Hy&9jJ^OUK6!#|dt(5hluu|5mU7zAha9bUM!vHq-6mMdAoZ@NUa_LQimP>B{3ON-yFeA%lZSGnw'
    'y~)UO>DkXapm^z9F6%>Kxy*_B6kh_~>JZ>gxcWW0gx`H?u2S+S#koYuF2${d=1gw^G&xOjphM=&+T1l~dh3xn)3filPjTz}=1gyc'
    'FlW}!a-ZT$5L_JsFevq7#_~p<;kio3V-%13+NS3s9+2VyuAB~XAR%qDHg~m6_B23>=Yh8AZSHHE^`X!<^D%a*vIfR^3)~JNR%P#~'
    'Lbtp#538GX%)YwmorUUVZ3pV+Q4VxS-K@=Bb<;bC)J^Z)K;87t_tnk%P^g>v68aQhg5~NE<cqkXDRPoihllk|@8Z6`Svx^}v$g|$'
    '^CSl*q;LAUs05}sA$`+38t9weQD5KmE(?9LUWWS=Ujpdr5EvF7r|BrK<KC5r70x<lU*YuLK!wwL0Ci4hInW}7vo?1XPVX&JI6eE4'
    '`xN)CuW;6fLg6gY^(npt)p-wm7V}+2QQU`zHO@L_U*q&XLXESw1C8?{2PUL(*5<Cp>3u>Pr)U52fa28GIO{{9ah7cR6kh`EJZHd%'
    'sClh&dY>OwIlV9YDrfBkRZi~#B%0)kI9WZQc(7fS(+7)GPR~B)KE;FUtDN<rP&vyr-4~|H8hlrWfRJ)`*|PYYu>K)}a}N7mf`<TA'
    'P9FeDT1K+^5RuC1=lt}T;0dXmp8e1Rf)5fi`anYEET_I<d=1E}LqNg@S5;1JH}oMtu5yO_29+}uta1i`oF-uz_t8L=Gn&5284Xl9'
    '**D#%c(enRGg_f?PNr`eUxW1O5TJ58TMj`HJi5m<&gkEuaYm0d&WOO&UJi^<<BXup_Wc>uIN4o2Ab1*RoG}TFbMk$vtZ{pF2ud4f'
    '&KuLXkMy|48S@)7&X}>r83DkWqz)Vl)Hq}5Yn;hIjWd~%#+l4O<6QjPH;SjeX?%_4^X%wu!Nk|3D>84QpA&^YMDcs-@Bzh>#~Nn>'
    'plgb9V1OED3Vn?;1*mbRIMO&%9B7=JH~dcV(zlJT@qP8S1cH(d9N(v<N}|U#&O~p}I8(+NXF@=1sgb1uHO^G}8t0sdyrFm*X`EyR'
    '8Yla&?-W1wjpJ*~UmemO-doI{ra0NhHBNGG&^XCqjgtU4n@A4yP~#-u*ElIajg!Ji<D@XqIN5=Hr}(9B9be-B>yY;Fy6F%bil@gl'
    'PI?3E$rFY>)%Nz%O471M5ccG$4}0<iVNae$uqRIg*pnv-dpfwjb$pEt^ceu4LJa($qIkBCYn<7>LF3F0Yn&N?xJg>avxgdI_I-^r'
    'd#G`8X5~J`a~NoxIS7sO5c}5gHD0g|K^iA}fHoA5k87Mcy+Py532U4g0J}+A$1_2VlM^p@DW0Lm$?28{6fXmflYQ8Cis!y{e2pQj'
    'L%`wXNFmZHXEBefoW;ID<t!GfoCScrmG!tdsB)Hm^#)%&R5>{ZbD!d6P>sp66Z=l_L*F{S#ue5fAX?s-tF2bveoK5@<t*_HDrZSp'
    '<tzXJ?&N*75L7uiMRS+p1XWH>%silY9;lq`#lBPg+_#Rev4(XBz>XG~*U^{qu(}zH*;hAfC#Y^RjJ92qmjfMAH@QxDkJwxW8W5Xn'
    'Ecc1c1#P>;=3=FHVjpeaFusN!a)Hs7z2hai!+DZ3hljOIF5C77f=8%ra;>hG;6V;dNZaHRL4AS~(l)uc$%x?8*EYHSf*^S4+r`&t'
    'L@s^+ZsM0vZ{A1se&u0plQXFAQ`{P;ZE|Anmf}$kv`E|JM8#c-TZ^<!PK!IBxOIJPlar(hic{Y%zD6i=B2xgOyvE&2EF~w6e3;@k'
    '>}#8xnGaJug0PMx2PUL#a=x)X#S_vtIlI+};?&nRIoFY(_|&(HuThJfj|im2aAhh*zh8b>+vJQUZ=iUA+9v18XelnVO->_#DDF&G'
    '+vEs)L~+ji+^4v+eQlFN<OIc!eZ%+~$;eT~E%;5|PdIk-VOl%CuV-?E9Hg}aF%vG!ff4DM9MsdNbwqk5N0W?bo%(tv2N4KbUj|_D'
    'C9aVX{U93aS~erA_sb9KnGDo@1H}u}Ga1_nE>2>gH%QN9a9fw+-XJ}bfl&jBd)wDD8Ax-d_{sIDvIaXcss(U&zNHQkGrNb?O!ian'
    '6WrrEM(o)HHXb<;)-ht&PM_egjuHC>Mg$+!F=9KiAb9MX#Mk&oHtK>GJ6{gdWaP~Bu$IYYnl}&}*EV9szFpTr4urLhSh496JiyvU'
    'd@~*pJPc|Z@l{F?Johc)=`>r!`CbFS%a@{p_d;+F>zE<Dq1+K49Z2s0${o3*90<!D@xMO3VY#CaM&*v!h&Q0OEO&G|^zGqf4hvO4'
    '<)b{8FO@T=$Mwwch7w4%6V@{WD1js+jzfSYkV5E}KnektKnh`00x85n38WBZ38d4xZw@Cvo5Sl6pl2?XV&&BKaYZw}p)OMGgcZ#Q'
    '>LSVXvmwH|NFny?B83R+BC#QQMDamgq!49Yq_gdt!zq=8DxgGCxMdqt1W%9aneh#^lIo$vdS(Q*lDw4R5!Olyv0p1GL|7{+#8IuJ'
    '`gEXYMp-NA9QxL9Dzh~_plaInl2Z9w3GrkfS2NQa>L-PS>nGKAkmyYc@dWE9h19Q~#L!7Z@HDEQ6w;u6Qb@9X(wX|ka5~aL6;Mg('
    'T9oWsnMzC@A6GNe8)_<rglj4VR2$o$<Um+cDWrZ)rI27vrI1E7mFm-hnwexxrSsG`hSMc2Q~?p!_F}a2A&_}o)ucC6Sqg-!ECm8p'
    'mSmFaK(NYEpnjF5`V6X?G^(-`Xi#N|D@q7@pZcco?BYTd5O5u?7fe|$HBfw9)1)^PUJ8T@F9iaHmt^XKK(O#qpnl<{K(O#qpi$wa'
    'K!d_dfn?#Oi|L!gb6m{fDBzmCJ)2B?fy(2mW`094rrHUsni&;il7}wCVoV|Ti!s$_P}R(%VoV_qiZO*Oi!oh%-yWXxVh=|V*L7D<'
    '(?zA)2{}BjYvwl;XsVsCu9-oBrYP?z85U>?xnH0uWLTgn<WYg9`gEXcW?7)=lKS@Wd|2$^DCFATf=_~?czImg%x@^#R8<(PZ5B|p'
    'DawmVfkm4_=@)IP&!DzhMn#+I(}A{GWYMNe>D$Bed9jD1nCq+YimirnYX7*pS>8~{sdmEZW&wqqqP(aSSjZ`qej%s&462)DRLH67'
    'q62la$U;t+L*E`=>|zf`LD#<A3N%O_FZpqGv%I0WQ|*M+%>s%$MX{o2U~#8t`o*29s*cpnXhy}I>eIfu8I3INbUF8};>FKa@rZ)1'
    'uNtqI)jzCiM)QVRPto97Ptl-SPZv25)_RJjU+bwpL#k#pqgqe(X<yZhM$~#b7&}Oxl2)pKcx%3dZ>%ZN<cD?5Xx>l&DjHk>DjHA#'
    'D#;aDSO6;8egUZZ4C$KDjtW3UJ177ZttbF>FrjY|FJ-ofM-*=@oe$Bvhn37|-%t&zc7jS~w4fRk9ppe*4Jz7xHK=G|HK=Gu)u8Ir'
    'zLFWOs0MW~)VGC~<8h%12(+$WN-j$+{cF+E!)j)<Z>SIzEv^t1EvOJhM>!Byh>EsfA*wz@YG!n!3Q_fGU(Jk8RERp5sc*R|m)UX^'
    'QK0o)%}Dx?qjMs8;2SCK-jJ*&I-IN~I&g8KlN<<>)kN1%RudgeR#Te?T2FL?WHt4n7ZgAB^~}kIg(@gnO=iVj2^E*(;{<<0F`npf'
    'F`no^F&>iF69<d&MAt9IQ=g$Lcyyy;Jkbq`@zjST2!82b2&ZTks(={ObW|Z#(a$I65o-H4B=LwIC-I1!BU}*k^tv=(?>zNaKh*Ye'
    'A(g>;`QbTS^`XVy%wQ@_Wb`-3h)5GzoAf7VP6ZkLEqTb#AWdZSw+bpSO=R@92w0pZGWs=%&P;}Fn#kG%*c~N-W01sf^^5-P{M)ye'
    'uay{QPA{^2#{CU$xS_x;8-k)h%$NeVZylyU{nU}5z@#XU28lAGub(oyPg{AaQlMxOWP9%-p8k%zFI~j;{EytOm~eH5EC=czc$d^~'
    'lz8uQ+k)*JrJX}9lilV!%M8}YU%4(p|4gs}ELHzbJtKR+<J8;O_I0?da`QV*k%T?qd%qLZ`#A7E0lbgX?-TalC#v^x;C&)^AFtmh'
    '?Z3|^+u1zD=BI91ZRVevu9;oEextSM&+V67D;GIT8_7k^GA@T&G!&}IA@|kf*+*W#LzDUtv46b(A)2$0;|~#g$=45&J=*{DpI=_4'
    'Uta$9^0R$$;jiZ}AJ0`7uVVT5>EqW=AI>iy&CAQFitI1buQySB)ueyF%&7$XDSpSK6Rnd*MbU*R)Vn|%QH=7qit{0dLS%4l?yJ#p'
    'MF#85h$Colj00$JeJJ#3%cz8>>2^3QbOYF7`QeEQGaRS%9Y0zR%<`)(s@S(jAYxc?j5-PLa;u290G0VxF{P<<ZCci_M!gGJ5|k{t'
    '*SGF7Rf5L#7`5$uUE}TUI<K+bYA*6azN~Dm$Rt;$WKRU<zoXRD<{a)yd`10oAPVIy@8+?Tb_%tM1QH~krG`FNsa8`YwTfhS&uzk$'
    'A7cVpq?IWq!OD*@^(#Ndv{rsR$U~b(l^<goRDO&}RDL`-qVG6AHq6kMI%&K8C#l7xxVQZY0L0Ex^Gs=X`$4jj3&|<+?)GP?|GgV|'
    'GVL-Ih8V|$AjUE;UnGbzuFYM~Z=@AttiJ^`0vSgdfQ;+IB-n~w2G7&2%x;`W0ER3pcSTbA5n?L>S+NdMFwyO>4A_c*E_6~;+^~`Z'
    'wxURqt=@|~;K)dMLkZkYlYTeS7r)eg^@y-JltA_?dDyO=eZZHwZw;m5khG&RvWCv7*D+gi?)9{=Wh~S8+!oSeFU=s;w4{5sxurWP'
    'hRDt-x>G9=GR9BVcHq#G;~;#pHuo>;d4*3Zy5|vmGUfq%GUj?Ey3?KV_t1UG@K7h!Vl)7vVf;+Y$?frZ#wCYiMkR;kI9PGGHs3_k'
    'FCTPsz7d8AeeryKoqqZ9>C5!;<$U>YK7M<-yq-UtDnWkv_>B+yYBJ8aVnO5(m_1H{8QtTY(S16d=4Le{J-5s<$fFWDNS<f?`tYn4'
    'I<bnq?&^)FH;Aan0rLD~)9uHm-5*<ycX6sV%atytWl|@#aD9r3HrAcgo6nhk|MG>O9Y3f?*!fWaPDg4&1r|n#<yIJB`UrNlgGz`9'
    'l^_Kg1|`G+C?VcK2_MxJV~9$KBUD0URKi`R#P8Dl+{#%1|F2%X7$D2lH?)+XPhcxs3Qp7*i!|>ErRqL38JNc|nSLI-WY#=(Qk*9<'
    '%43(zAdg+*?C^s0;k!sbV_OpfFc|rx-nXRB@-v!@*I$I(2)|?k{36tLw@dnf@Mg(`F5WDeXdvn10B@E|?BmT6R};UJo)Lb}liq}d'
    '^lP2kpE{<(WC$8N636t9zc<O?!VI-N?UEd(txt2>`pw5Qv9t7<uT(NHs3*<I?9mr7aW4C(e#;t6NNemK?=lbrEYsf9H@Hk&Rk-Jt'
    'X`}Rr%%@EXx@0$()>e(JUEn1uSw}nfuVg(wsMhZuRO{hEwYSVPTdv`>1J98N%L99p2Y5T;v%iJYbkug*`Pd|!#30Q{4Dd2jd~%s&'
    'TdpZeMsv!2=>W-K#W?!3wrhdWx+RjuC)xJH^XfBXQ%iOfo|oJpJg+_!HnmW`$ARF}>_JG3IZ=+I_Ov+*VR*G&-$+^yLhXXI^E9VP'
    'fOMO){BP;z+(0`|&h@qP#A*Ilx<zZghi+%L(9MTEesi5WfeUVz<oF7mT#I~<U^IrlC)dV?M6hhE+$PtCP9^Z$ICd(zq!mbeA3A#p'
    'k|QmG?@Rl-_PCn=7Iv~`Y0k2_%&j*F{nDD3R-~n-4gTe{His_yp*~aw7^{5$$rb6BiP0^5_oYg=*PqWXr`NBaKTLmr`TY9Z`NP6h'
    'H|cPbp4;E^w@>-1hYB?<`B~?k)zGjjT9@mww|KX`6->IhGJ6=4l6*fVCHXZbMJZ~@kAhN?9|WZ&FM?7Ik+WWZ$FVjGIe<E>UR{N&'
    'ypv-vapH)(;r6{ml#g!j>gPM(e-F}hDRzTdx@vRoe*8T>XOgM|fyYuSXkMjc@!#cJcZ+j9`OUomT!K8tOD7NT(vp4w!li3-|MC>f'
    'lb5Gp0YFIE7HSvC)mJOl^Yo+R^21JX_4}AoQrNX=*Djc=1F&hUU4b_3+T7>r5T4{}PM0yZ-lw3#Ki%bfB%D1h5-!BFrz3@gxjKMq'
    'ql$inxta!CP0w<523(yqS7*u9?s)nxci3h5VNg~}5+NGJ_3!kBh&T7E0yw6*_=EsBrnsp`G=msZG|HkZ0gm-qRshE=FCEbiAf72Y'
    'Ww*Qm9JOqTu4}iPk!dNq0l+auzXx!vUB&>%6#WjsF~#6_mnn}d0yw4^(NgvA#JKxA67GipjwvQ!vvisysjI=SzawpI2;f+IMDRQM'
    'eW>jIPWBt%VT*B0F}FT;uivQH-Cxo`*B0NHB0{<<fMZHVa{{nhCWDonG<Mmhgw^3RP>0j14u6pM<}_4?(?}goQXNi=seZeBDp&Dz'
    'Jb(DWfv}66H+c!uuAhmgr(7zD*C}^R#|c-nPYEPfkO4+1!D{xkxf`pN(pt^_&q{qsqjL5s4a(Wqhay-l#fPq3ie^gycuK&9thi5='
    'xt}in>7R_@u>2+nI(O<vab>02zJJPaw$GG6woe(5nh0k5Ok@<u|GFEC<e*Jlp|$E^T%9BJl9G2XDKnHHk&~z&ee<E)cX8F`FPnez'
    '_h$s`#~ZJdhc1F@<5snw001@{{qOFOPNV~`PU=O1fA`hhD&73{=}UWVC}b&Y9=l)ZpId|t-PG^nzkmC*UZm(I4PH;L%hhISR~IQw'
    'iP*=gB+j|=3@V`x#K(X@Hlied5GEr^bW29GbyrY!&t1eZ04vP^EO_Z>0M>KARRH8kftOPT;9QxfD`krXQntGSDO<b~82|{CK*|o%'
    'D7(Hu%6=e_IJwGG0x5^SK$>w_ZxKj2NP$H5`7>yj*!PqHI%FV`a_UQ@oc#MQF9~JxA*RjLN|#Jnx@77HLL|m|JtaXh4t%cdt+BJn'
    'AB1twDc|Crw-O|mCw;;N`=86e|6HE+KNkx$8Wm(vyA1KJsi5dG1qV*WYgqz(GzEwM*Y;MH$UP}A`ahL^^nWT5deq7&`oBIMs1RJc'
    'WJQbQ<MS$nUm~aLlw;MY5D@)QZ(P=vLEzgexCmk@pa`P;mKIn8F_nG|L^1}UUCE4UAd(r>KqSrwbEo=aMp{jEGph{5h^sNyl?<+a'
    'RonNdUArJ80~yyvGLZ4lAsNU>g>kh9%2P=u=!mx#;z0%{y|3+Y=Rnsk$SFoMR13ds^iRGl3J6ukPcmr(xd$u87fUi*S1q6u%mY}P'
    'yU`$I);xgvJdE-Hk{RRytPe#nNH!0_1=V?Q@wgCn19NVT<5h`-_eU~Yg%%JTN)a*xDPpk{u|p|hM^eO!N~(vPAHvLQsx3~_I^`~}'
    'S$uUSYj+9GcrZ8=06R}|94^0F+d<NSAP07YfJK!rj2wt@7i2dsmlpd_@2FZfHP{ETx0=Hn>_cr%E%t$I$}RSREFlyVS?#ttt<A2B'
    'eW(wWxYgJPvbX$H4`Cn3-csH|>_dH6de{fD#Xp68AWqVQ_RCdGql0~@&)^w${XA~u);w+s`#^4#$c@|}ksCRu4)OB}jyuf?4!JQ-'
    'nw-k=_Ab`LI;XVdypJ$)o3A{$mvl<o5GrjW84Xvqp}DdR{KRu*o2NeUoFZs^-zBH27|?fcfxUA9g}sZ8BN$~++grU!Q7^*_k}LfS'
    'k}FSMkQ{RJC>@Qwk^D^YA<T%T-cnzs&bfPY^4R=DertYe3GX}KP`~+xf=j&bd_x(QwR0ujCJnl`HyIpTq&E4^N7(xSK3m==@Y(XP'
    'R5W>=BW(F>`Jg^>%jeSvoyRE1ugi?;!cJ~tbXLB;Y3FhNUD1zk-|u^mdeLrrTrUClF7<obcG0uc?_<-&=~+quUDPa`$fxPz)ht}J'
    'rtP9<akh7(S$0^Z>A4<3JwfT*ch>Q11*c{FhN@vrAv$k#LsYI}BYK>EYiP>pc|?!nZw*O9RCDB(pixax4lO;CZ?G4$!LL3`Dl>+A'
    '8ssyJpm1~QueT`0=i%nhzxh=*;yF;?;6t3zXT5I}E`9W@>EY~`h357eF7F$hzURH~8(|X&*JfX#Xa*W5SG!p)Fw^;=v<-SmOMYF7'
    'phA=+Lv$c3io%IebQ_#vdl;jKzH*8nZ$Xsf0&<nt=B}%pVu(m%<uW+^%WjN)PdPDUMo|6v4|Vj*hkBdh27EF*DQ+mHeQIMpD^fS^'
    'iy}Q2_eC*xb~f9+t4Pf7Iy>jk!JC^4+}tuqYg(W7)0z?ka#qPQ+2@U#_0l(!ByB?8z@;V`ytxUKvm!apLW^dyeTydN>v?Kt6GpMt'
    'cG|ls;>tfXsQg3s%0Fsnhn0V5RQZRv^3VO)9=}6=+eLn-xO;3<#|D$)?y*fU{=7E#k8Mg%9@~WDUTgb4@8Y=E+P=fP8S`!)@NRjQ'
    'cX670N+3<XOtnLVk#$4>Stk?h5Lv9167c4o)If)gK#Y*tG1^tVVaI4kJ|m+Y!)aRWr(TMI_Co<B;Um&{8BS|+>KpASYP7D_V>rLi'
    '!$v#0c_OgUj&42(XtZNg%Tq=>!u98Bd*~YNC_{Njxi1eXM`*O8JQ9d=Y9TBTIl<8VQ}<X_$&ElP3o*cXk}sZ(%n0>9m*}k0DZh_k'
    '&vq}|zjnc5FI!N7QjWt;$UJaD=4YLd895>KWj(9RlI1(#YktA6Q4TVl-23Py85H4DWQ{+7vtnt294Ozu$|A^tw&|DVKnBXmHH!BA'
    'SyVv|&Phqdc$~fgh;uJBX`G$H^%G-kWKgdY7w$#b&qbiGw$SwY6lF)&%p>t{AkKk`0otNkXW7JiqjeT(i$sAAR4j;IQUM565~}Ee'
    'Hj05tV<Fl`OAupic2_G89SUQh5<qqxr++ByZ(oTzUIM&P1aIUuS)w*Uv@k;|34h@VD4<~vS&k%lS18m?*h_^ny7!kn$k$t+_F-!E'
    'p~%;JcrYm&H4iw@V6ho-nxwnXIh4oJ)WEryN-%Y9x4SW&TP-U76l4j4jH^H8LG`D6ul_WNjmg96PkB`RDa-0lm3WUOQijBvX7pAz'
    's%pXE@X*%)&wV(rbMNKKtzF<9J{y2?FHQ~&Naf2Wbn|*-6Hs1{Y}Vi~xG%Av*CU%K@_HN&j|JaC+8yIUyO`v@oE}T51?N6p*17ZU'
    'z9i^&$_!3w)Ifb;2<0QI&E0%t^%=nflLz_8vdR5?Wc8t_M{;<~@Q8_bF$?i>QQC@^KU+lcx}&{3mc|wSE}0nto*7U?*E`lv+q@;S'
    'cA6PJbXNqAX<G1|f8ASveMx_O{di8{<uw1X{HpcpSM9;HKkFoD<Tzc*+kdwF+xfR||7*QZeyx|w_3!1!UEKe1FSB)=Tw3nXKR@>4'
    '*1Udv{q{P2c>Rw>esO-N-JcIq_dez0;n|=6`j=0?Ry}1p{eAiQP<lR}s#5ix9oa?!uRFST5KGoCa>>T5*gweMl}P({XMa#(Ps$xe'
    'E;X5^>Lp8D;cB0u(w#ZQQ#;2|UIR1davIIS*dQ>6S_gxGBoXD#a^<ad{7J82occ4n(7)x?hk3Q`)=hdW%DuBmbH?fH;tp{VBF;$@'
    'hjd+?^|71>BUv&+vd9S1jG-)fhO)q~lPgOC92v)3n+N%CGJg}hJHP;z)xLgyF#iqQ0l(OlGMCKSqh6=_RmRn?vcFaK8HzzJWF^EP'
    'g(t;eJiUJTwg|vc5~0lal$D65^E<GyyV&)I-$2CBA!5Kp3~wM}R76bcz2!k7y6M~UBDdtAKg-yBdsec<r?mgB*m9e_)>_whrTx#g'
    '&+4;H_Q}t7IsWqH>!&X-_gBtHhM$#)@tcgit;SfpU<u>5K!o=091NybFkzR{0Vnm!jO@u8v$gJ{9PXfViVH{TpFV@1#w8y!1AZEp'
    'M-JY$E{_~My!;0rfXkycD^JMmda2FY6C!~yIozzU*xpy4#sT0fGbCsT_{t#x1eL-jWya}@0bjXl0y}`O+NJCOzA_iO8Uwy^GytEb'
    '0AD%UO+JQ}Yc{!HG~g?5)4;TNgdANSBEE9ekgyi<ReR(y;wwju32PBwIciK;J~Ska8WUDpg2uL>;%r6C3_THuuQ)vkdj9<~UFzb!'
    'G6PY1cmGHO%{P+Jd{4)BxPrUWas}s%G4k3f?J+U`K-HHM$m~hZ*b&&V6!eWsw@88EH;R+RNZrmo`Hf1)Pe1?sx_qFx#?;-i^UgPy'
    'WcR-@3C9IyPFOS2Dj0+UgnRPcG7*`R!SE%G<EJ0-$K@n5t#%ZJ6eNoNnBRfrY*|<?#jwvGN+6tawomH*?(+Ka_3K|=K2NV7S2o$+'
    '%Z^|tX<!9NB&-1E2NT0%En`99)w%PA&DyU@%0JK=!1xxmfCHco&O(z>7MduvRGft-&sk`ok~n9f*_2eyWCxMjnQR}po5=~_?)kwK'
    'jClLfA|*J3&0PeY=^c#zp3dv!TgGj9gK%&`CJ^D5)Yd>uO`g-v;H?Q6ZcQBc$?}{mrn5Cs_{q+PhcMM0>K)TUy|n*bB2|>}d^$cY'
    'cdj<aLzTX#^K!K57CZ=V9z=aSXy)`ZcdERHlgh7ND$2HNb!1%650f)g_RZg1vs|j}>%H*N?XZ7&J)K`}3hnQgxyP2ijH)thtc_et'
    'OcLm^qPUPiX(@)3MYXXHiweR^xR6?cU-Xn;RVS}Hg+*{2R41!C#Z4vR2HcmoWxyJ6UuGDJ+*N19EDL2ht%cRPmFznAVuNGbt6pSO'
    'FU~xQda1dJk=KcEX<&To##Em9{W2!8!dnI3zc0+uF0$D06k;zIcU$*;`pX5p9v82AZvM&^?drE=3C|@+&y4y|$Pm+hh{{dh`*{Ad'
    '`VP&Nt3H1EwrRdz3U9TuBpu|8bGGb{=ZDuT!AhMEXTb@9asdf}q?{-)Ay6)*8vvWjlUad^F;FJSO|7i1D=DmdeqTWC)4v`SBd<r7'
    '{0=tsP|ETGPT&1oPirw=p4DRx;q5a2?rHsU{_mBL%ddLr@qh1E@_Fwp6f^J|)rZP!^q$|4Vq)04%vU)FmDX|vD)bq@;Cv@#&Ub<s'
    'zi_^j=NLaDrB%5g3&RJthTK+)6oYk_VoC<qjM`lGIF^e-NsgrloC_<*5;y+x^L*7WoROq?VQ16}TaaQ;ZjeR(PN&e5#rnA6-j-rE'
    'K*UOI_dQ>0u@QlYYI7GvRG$T)O_Y1tC7?|doBAN4GN%W*oh;)Ys~`bSR`iEugHn16w^@Q;mD(N=w{Z%Qol9}Cx75+grP!~RnMZAB'
    ')926UkEi8*@*9|?D7(Yy9W>{3o;By95{z^>(cws#;*5q)I620m?{jVLM)Z}r6w{Uyof|~-)u(+8t~gf&C#J`0n`2H~Li>vIc9&<I'
    'm++-iSZ!91I+4#`rmu^Pa`OClSY|HH^n+L??h7x6;dZrM3okFnz*yDds4u)6LE+_SB)nW62rn+PbZ42zG6;8AW?JqnF7JyO24_f9'
    'h<VawKEtohKYw1(2X*RwS;NJfei-9;yDw`xnMKNs*;pAT$}tYg8t?kD#yco$ydTLL&I!_G9EMoj8Rx;eKbUcrL_&o#hU_tp4@%Y?'
    'E>GIf%9U^aa{lmn`SG|fZy1*G<Jczc%NtKv-Z0QZvQ3g>VCmK3b6?*04CM_&GzM%_2J(iH8!Ovb^HBcM4&f{<ge&{<CKx4eOeoLV'
    '`mTKQ_1pCAml^F^=iV1Ms@~Ika}J|N_Bbctq(UXQE-tiea306Cxi4^nhXN;rk-!OIAaFtu0;ehk??AY)+%ZDj7dUganT2ygdGc~I'
    '8|{Dj_}7o0e*L&CAngmCKtE9E1lkumA!DHvvKBg7j)CP{Yja=dgaU<57?p1=aZtXsL?eX`y~DjY<>g)+&A!lyRtcSSdcfGESjW#8'
    'bGAAy4xc*vzSxOQ#HqeF??gwtyc0dvP@}XA=(GtX259<W98r&VVn~R0Vi=^lEpdRwuMd;pop&Z&+{KiZm?Wn3eDF^Kb8q*Y^KT1`'
    'r7%Kimu+Y_fTF}4ew6pDaMGKR?J1VhzJvCjl_bM%HJrU93&gI*>X#&IDZV!cFl0vuzqV%G<ho%bWybDc)=gfr?)e@3s%a@_QIhXp'
    '7gA8d=3O1Sb#hXZzpEj8gGfs6fDEvdmdRu2lPuXENU~d0vkLAnoIghg_m{NEyEO;!7e+F5g8S>UqOiUK16df|)MRa*<XdMEyLxms'
    'u9o`wh5t5v_~lB(u)NAGan|NlZs~Q@t7O8jl3RG_`mE?Yl}^1&8RV%fWVY#Dw(<0}OMmwX)rr-kZR}xq7dgyeBoQNjO<!b<6eQ#Z'
    '!h%shtFUnK0c-Ew9d<*(G4NwC0ntXQkXJ+UAY@;^wHL?nnCt^LZnUV&VpXTmMMSUE3@YElHQm*Qni1cIDGswa7fJ|XUz@w}wT1CQ'
    ';8sI4h_5X)KpEGEBz8Od?;>nk#3xZVw6;(N30m}S7xQCwyX>ExQg(Jb<Cu`z-U8m_(asj(-3r5gdb^!1!n>9126(snbm05tB3P^M'
    'H{|1Y5!TThN?I}i`$<mUmbD7{;cZRRqcDq-<L>FrQD;cLZs+yKe`nRM;(Q;q9l#i+?8-3RN6GzkA0-ps)=|2Tk_YKN>ccyX@#yU{'
    '{^0wzE-8&l9#>f|<@T+^yIM?ma#xErd%MaosJHCuwTu+l)hilmyQ|W$UOY5bFg&WatHncO1p}k{yIR7)Si$*l?z<XJ-?gjOuk;OV'
    'vM%YsEVnF;oo&5^AwILMo1Cp^TW@x){cXkB7i)X_X6Yyg!t{%!+|n=NZN0@4H`}^ant|I|sJE^0T0`%?t@-;7>rxz#r)}XgUjD3g'
    'y=~=(>8Wk4BR3_enr-DS=?&Xj`*{Qm;`a8<NUa{3hq$?C9^z-fJjBg?^H6=-HxKbcac%Zx`o3+Q(=G9|J@;RIhU!y@n-uqu_vVlv'
    '2z!Dbe6y^IMj!n8Ja<3%{P4LCejQnMKKR__Eg$@7EWE~XJNV#BqFZ#2<L2H6pPzvber+Dy<M?U!gU=7e2R}UGDo4zAUSx;`xtgr}'
    '+0gys^TX%9_;qC5`Qmezw|w!rANu0g_SC)^WjPRGFu1w*#ph?>i_gvdFMfU6$6)Y7@x>4R`@Z<jt@O>KFMfSqx?lWg7$^1IwmP%('
    '#jjoLTfX?*4}I~u9enYN9EdWHa&zyCU!QsK#pmY!7oVRFzW6SPFMfCmt|_)PE~nLn@fY94!55zkCOx^WY4?lo(%ZiHj_?=X5%}T<'
    'IWWU7zRUeDzRU27@ABx2KWB{TY-<r;{P+8|DzuVvghj(BrSTWv%gn&<xGHb$53tGbyt_ie%cKUtCc{0DPm$Z(Sc)XaAvgm!_uvft'
    '48R#`^8n7kPrGmiepv1{nRg^?Y~Ni90DrqYV(H*hc~Uxf+Oe^5m+~g*;9-Oex3_ObQt){cBE!vtZ7pzHgBfjWFoSIkMxa!pJ%8V}'
    '8k*^QO)E3FqRmyI@V0V2sOPqolf>+7D`SJ+vaKPY%r@NKzL^sGjLiYt8e%VlJU@$YTVp?ge0`d_3FP@<6x+H6b3eJQbE<Eiw#{cJ'
    'uV~?RsqAcPw$E;Brrm8V_HEk=6Z3LADC;dbHln<|+}z8{Tc53YdDXVYL0(>d+Re*bABw!Z$C$tKw9;}~BPi%8B~|pkzpc^JliSL`'
    'n4N8nf!?&O5jwZHy?rxvS|jpqadXeR#m|6ut2Ph3Tl}=^-QtJByA_Y$d0MCCv__DeP`&%6Qm)?CrBv?Y+q%hE2DUXB|E6tC2Ibh{'
    '_V&$4nm>{SX%}m=>!n@fXC7^9a{aW6^=Ut2AV2hCTQA>vTF=XAO&}SkdiOB6GNthBl_|yDD^rSZyE4sKj&@tq&Xp+<yfP)~UzrlY'
    'D^tp&D^tpYD^tqi%9QMPA`dQQp>MGrC_F#QI|>yUk>u$eS4AeMdEe{aPoR97<WsW1{Vu_NwTtVPU0P@9Xj}v|E_F-@t6VftxoB0n'
    'K1fERp~^)gm5U^TJmv4((va3IjXM=txywL=P<&Q|5G<6)?K{js&^$)8do3hc+mK1Wh@>Nnq@_>XrANm0S{nME>)p^mb8R-gI&u6g'
    'Jd?q!4z!?ji9Rt5?huFhkq}wLQKqavJ>I|UcC9DbZ&!aep)5Vd&YZjllHx8~F?z?H%{`*F8g7B%+#^XEPT%K23uW=3F$83T6y(OD'
    'k%F};X}$D@2IO{8F-Rc=`B~_ddgF(=ixjL+$xD*mkb>&VlQ*XjkbOOb2k{ekn&(9$Umw>csvgC(J)G_V=J2vdF<_3Mdw@Bj>S4hg'
    'N%sJAkm}*U99j1Oa}?FXgE=PM1I%$yJp!2HsC$4pPO3))bDVV#FvmspNMH_YbQi=RibL+04B5r$E@&3bBN@%2nFKPc<`TrMR<j9W'
    'S1b9%8pN+Q>n>=PqPifCwUh3GW;v)Xh-d9lcR{n9R2Rgx_N=?0SuUyz;#+5Q7ch&nste*==X4h|i&tF`@4BG7pjo2of_T>@-385}'
    '`33Q=)BJ*X*J*x%l2-Ez;$5fs#UkEyN8JU@qWHxk-gRf)1<j)P#UkGIMt4CU55+GQ@ve8e3z|joi$%QagYJT6QT$>N@A{;>pji~Z'
    'Sj4+N>n>;(#V;1|uAg)lG>hgJ#JgVe3*ud``33Q=*Zcyn35s7BNHDl&TDQS{HrE~N?6x}N<|<ozv?+?zZ@9eo8-828adVTcJ%)F3'
    '>q6T5jo4nvqkfNJ^_BWONqr-S#dz>Ub*O8u<XMlj?6}|Fm1`qy?#i_(qq}l#FTK06b+>e+@UC1Rrv6>oI;CuayK?O@%9>Z7Z=nBR'
    'Q>1YfZaf!z8U2R0GKeYDQ?V4cklt%1@ZT@fHjz%;n6`VeO(3$+-P>NIQ+?*Tkxu-uAL&$|`khE8?jq0Y>GeaiZQkb{)zaQQ>p!vg'
    'KQ`WfJMykuFHJr9@QjshNtMQCw$rjHQG3OZMq4{Umso9YU1F0Qmyk!SHg`Q@))VrGSuX3+wUO1Q!1$>Q8+I=4vh$u9Ws>0bRvMq='
    'xB{|sb8{~{ceLz~2k#k7KRY)+-SeB+VEv9r4wiO|S(bh8T}BK}VEgj<8J~q<M4Bx`b=qD~bA5KJ)iDdC>GBK~Nc^UoQyuWcd7mpn'
    'fC$^#-hSI8_lJl8wsv;qW3Gq@U~5Af0BkLL^834$1i-dDW%L)6D~E+}BtyuHdmw}#&3j1eyl*(Bj3Iy<LgQl^GCZbS_ollc1s~Hg'
    'Jf@|aB{tTpxf2`Wzw`JUm*c|;L3Tt#)TKDxBlWGehRNku?GHMbjB(g|9jCshO>{8#7<^Bo%q&>qcdq=rF5KI$7@G?U{QznOzkh1D'
    '6cIW#oJpi9P$<Vm<S4f>bsgoFArs)##58b}TSiCpcZ-ChywC$Ft`Oy{2@B;&CUz+0nViXTVtZL9rZ;Q}Oh3f!0F!c&0}H~W)aEWG'
    'r9MNL6r0QdlTx4dF)5a75v_R7$vuNfk)%7=nRLnSfqrTiQfI%tOXG?{+}<Lx<r#$)g}Av3$hOHNKz3~&0J3cgeL!}7C;-{z_)K)O'
    'q->;xvLSbcQ;PA&2&a_xf?{k+VQ)JV7G9jJW2DM5wgYWvzJ*3y)y3_0-mv$}4f?1yCO=g?stzoBu?Drv7SFIX3aOkNcoH&ul;lc6'
    'J;%M}nn6!F?(0arL7c;5bl%9p4I;n)s!Az`j{DlDm*2QP3qOeADVlxJ&-e*QuLwe%6u}ZgI@md(1{6?4OCZoe3MisMAdqF~L{~sj'
    '7J)!hcpyI(6i_F>kS<G%(v+UDJjscdfWSI&c*CAx42MM+4myj07{p;`5C`0oY?he2N$yEDgP1#;?LaSIpc}V6Nzb4TB<U{k_shHz'
    '&M@Wg+-zt4I`QruKX2~%tvJgLo2En&Ac)_xT>l5{neW@Ca)7p}JFEomS?Hs+ZH@x1Jw1|V4wBZdqy?a6`B~&FA$z1x)P9bX897s5'
    ')#212?nemMoOeGAIq!V~In7A-8<@+p-@pv(eR6x*7e1V41n^@qdzjkVrR;tP%l@6Z?B1zM=T2RQRXXc)e5WqmDxLi7$%|GAyBDnz'
    '_AXkCTEPW6_!<2e&Mr4STf0Zf4a+6nBV|)|W^sX(TeJ^!kCa=C9ClfiTW*Dpd!&%^RRWh)p*>$@S)tSj-epTpt<P0C*UK8a(}8zc'
    'E*mw3cR6Fg96|R0b41m{f;p1z0p=jp!+|-n?g8c~s)q-2Ou7e{<Dhy3Fvn5%0CSvFj|k>C>mFc^i|UcU917l5yC4R!stci6obG~V'
    '(L9pTESgCmvuZ9u+-fzOAa+&oE@u(HDtMQ(h+!4H%UQ&+3f@(_pji~JSj4jm-c`GxSroTe#I*|ERlA^B6u(%+w+h}>yMS2~yvtd{'
    'xeDG@yP#PVzgWb(3f|=`;#~#rau)Hff_FKKc-LuuLA>iUzaZXqnqQ!#)%=2ZSHZiSL%gftUCtriRq!t75br8@mve}B6}-zi#JdXK'
    '<s9N&1@CeW@vee*Ifr;x!MmJ8ysO|{&LQ4a@Gj>N?<#ngbBK2pysN%5nkDNlXcomU4)LyncR7c6*K2-3yz4c;Al~(wUl8wl%`fnp'
    'p!mhZdxFtjz$`)Wi$}a0obG~VQT*Z&?}nhepji~Zc*MIQ=`Ls%#V;Q5uF?pdN4y&pzj(yEVbWdDEQ((|;@xo6UC=CwUp(U7aMoSW'
    'ESg^s??%lph<Bsr7sR_!^9$nLsQ4uy-i<+bL9-}+35a)N(p}IjieCca-I#S3G>hVwfOt1fx(k{`@k>Cw8;`mRnnm$TK)f5zx(k{`'
    '@k>Cwn~d%PW=V=)0^;4|bQd&><`=}fN%ITh-K6;i@ov)mf_OJ6eu;>8Q`TM3EQ((u)X*l~1<j)PB_iHUN8JU@qWC2u-c4uS1<j)P'
    'B_iG>qq`ubQ}Ihgyh~1ZL9-}+iHLV8=q_j$#V--@E+yRs&7%1Q@h)k8LA*<vUl8w-<`=}fr1&Kv-le1Nf@V?tk`V9GS$9FRD1Kqj'
    'cW&$pMt3Qoi{h7btAoDjqWFcg2((=kzoh6v7sW4JC!*~Vbr-Z;#V?7_auvU%yn~!}DWl&}9F+?C9mP>(5LpyQkws)t97S*!kGcz5'
    'uHq<yyQnyd;4UhTBD9M|aTK9lELL{`%Poqd2<>7~9L1s7Z5PE+RM2u2N3mzF?UHmCv|Pne*`nnte&HncZ5PEa*`wtueqqN`+vT9U'
    'pyeul$q_AA@k>r<xr$#n+_&wb_=Tf+n=X^lUBGfD#V;8hwMp?yK}T&;{8G?Sn-sqkbkwG(yP)MNektgvO^RO%I%<>Rmx7Mkr1+(v'
    'qc%;t3tFz?mx7Mkr1+(vqc$miDd?z8l3%<*M{T<3E?~I_qq?A@cCe}oI%)@}x}c+W@Tv<sYKNe^pyfu@1s%0RQeDtdJCN#vj@lus'
    'F6gKoitd7zJE<<{s2wD~c#DqO;i$Txqjor{F6gKo&bkX)uHqMqj@nW2i$zE6sQAUAqjpsMV$o4Mdff#q_o(>AqN8?H{9@5jJ1Ty$'
    '=%^hPzc_T%j#+m>%T@g1&`~=oesSoi9TmSgbkvTDUmQAW$CK`YmaF*1p`&(G{Nm72J1Kr~=%}3(zc_T%PEL0L%RMQ6ap<U>6u)?M'
    ')J}?DJUVJ8#V;NmwG-(sXt|1CJUVJ8#V;NmwUgo(kB-_&@ry@C?R3;#&~g>Ocy!cGieEfBYA3}n9v!u_;+KGq+S%$ZV7X_-F9993'
    'v*MS4j@nuAOF&2MtoS9MqjpZZ3tFz?mw=AiS@BCiNA0ZmC7`2rR{RpsQ9B=W7qnc(F9993v*MSCj@nuAOGHQQtoS9OqjoX63s~+&'
    '@k>NU?V|W4qN8?E{1VYoyC{B%=%`(y?t+%9_$8vFc2WEi(NVi7eu?O)T@=40bkr`B?t+%9_$8sEc2WG2&{4Z6eo5%4T@=40bkr^v'
    '-32Vy8pSXPoi%F|$0T&vtWhkJ&}p+q@k~O;&6=S5z%?tbfyNPQ6x%@Sh&76Dpn1d^#W>JDVolL~;F=ZdKnsaAig%!i#2Ups&_-g7'
    ';vQ%uvF5D%z%?uWVKd1f$FirqlW)tD%p^HO;H<*j)Glo>rNF`Yd`oNm@%-nX1QyUUMEM!up3in~(OfRDU9{o~E(<t_Ht^Z+K-GK>'
    'uKf{(F7X)z%&8xVqH@8hUOwNR(?XTEUjODW>A50ho&5&?Q!v5W=r%AxzbynfLjirh<t_dhzy$q_`Gr{&e7;%jF-)*NO)X4NWl``9'
    '-5t`cfb@iVhE3U|21V;T5M0j?+$P9TL^*l}(Y6>>&-vUsaB$D2r8b>sZ5~89`r`Ugj`iU^%JJmR&z2oGuODB(y-puq|AP^xd5){|'
    'oHcGtJvMVCfs57@@=xa6_gowhZAt-kUu3L{FA)KUJsZi!7+=pQ-5pG{FUjuF17{=k1!N<Yva!Hyq`urjY7pSrb7Hxt<Yw8aLR)(j'
    'Bjr(kAW(C_R!gL7oqiZm8MvNbkE!azCrhYR1q>$c4V<j5$y9%qKj~27-e7h!kOreN#XzR2ecGfDR{nYr36D<xk#ZV?%{b6PmC)ur'
    's*T&cN3{v&Jqm2w?0g-9iLU!~2s6$Xe;tBJAn%d-Is{z<5aieiChcWE32ZT4zuw|XBR3$!svUtXse?;ZU{Eh&o6;@X5jYQC`+*3i'
    '42pIHYx+ey0$X9%4}^~o)K!zrlcvv~&mT`B4N#q!BwNyxY<Zt~DehHg-rY4e9PjKJ=jcPb#s=jk%u8;Y^>Ev)?{6EY>AP*)pJkj^'
    'Z6EGi80}k-`}RnwR7~9z7wQJJZ_@+$UGU7=tTXQiEd?8~5VoLZll-y=o1hS8uyl7@QUOt{!O|dmda%?_0a70pu`AO9kvtvREmD}F'
    '*kV_X4<zftGf!@vc|X%f?F28uwH?&Nke^0d&?Pu<!o%LKIO9PaYq*z8M7!c_{}Nmuic7FRJrDwnX?K`|B7*}r1Id%@)wu6k@ZWuw'
    'svui_+U@0`4^AeI!9vja+`mb=XRDS5&f<vJ#l0alTyPOxb%TrhFPwH0?+2Imq8|fiYTTn6!5HD%-r7;*UCm__B3zqu?;0N%g8s}k'
    'KCoYC=S>-yJ~rCaE<>YD;1r5Kh{gTw3$1US{uVJRZ=T*cc=PnmcW<8lb~lINi^1O#?{;pUTp4i~z8JhOW1CR$VfTLGJ7<XD?xS0!'
    'Pw;x;Q~!G6(|W5^*AvdF*cZ8;2G<i$;(8L&1IgSZSH$y|>FYJQWLbEE<n1Kn2NK!9iQ}|Ryt`+4f6q#1&&tl7lAV8G)8>?paML)i'
    '<9w%-dlt-S&+6^Azi0K1CHAa5sS2#5O><_yz&^>*SF%b?v8T~IdAC`A__PR+Dgt-*lpUQrd)leV7*I_{DHw4{#xR#;M0tY3oX2sI'
    'Eb24Bc^sem420CPaIQp1dG9L_Xb0(9d+dHR!!6YjzHEeNb0pM}_--12fmUe@5gKUgzU?I24$<!B2?`OU+m`GRUH&mlA3gYLM&Eoj'
    'qsL#(==)zyjxCU1%_zT`F^s;NF@UdTP@hds8z{S2?h=java!=HPkD3f(uMBp=Z%q7;6hBmBjEKibn37S<^Z{Yy<R7&EHk&mpeG?<'
    'WOaHWSrvD-U?q8*_5B~_z-2K>mXkQJlCn+f-dNJ2OeD610INxo*((GUl1?P%+m$4<Q*kaNyHhGDB#Uq634DY?kOLjOnkU!I-V>6y'
    '=o6g$AbU@J+Rxq-*ww#&f@6MCDC95aub=CqYc}M?YR2gSM_*wMtca^XO4E}zefisVH8P~wN<(@7N$5xg%|4{JKA3jzJ6c%+TABLz'
    'B&?RDJlOkUktH^j;og_Q-jk7ge|d+!Uvibzsr?@9=$3jDf1DXU@!ZFmEKGnFxQ^oR<4hhUK&#E#!xq}FGb#NHf1PQgp&^3c9No2j'
    '?2aLrqdU;;ZU<F-diHKd3CMqaY$&OFMtM>{mu!`f%g@u${T?WTkHThoIqYsk$M#6Mce`JEz?`<Vxtr6rJ|lFj^C+in$b+1=A)9-h'
    '<x_grP_M-5;(rerlq6OkwcI&=c~iy|kUcxd#~gmt<739kJjKUcX0a=LaxhN{pB(V_AP3rg`&+%z+lnA_<@h9cA>^Bx@<u{fE+OQN'
    'mD1n4tQ(P<y2tZosJh1?6W+&-Mh66Grrj)XA?MvMOU5NILIx!;q#(_(1V+fWRQQkq%MBRtI0F`R^VE{6SSRmC<{bp-Wf7zWTu$Zn'
    'sBDb=V6%$fHRTpRCU^<*Q}NC>z!HI4T4JM?E&!daTFMBWo?2Ssz?eJNdhDpBCG8n=%Qzo&D7RYQ8`NUp1a;4`V%`B128PG%Z8flc'
    'h($+^j}u#ce$pjo?O$F`=a=IzU%r0&!e-jp<QF-s-FCNY;}%j_n;@hxG8Ct?+tJuQq%h8@@bGR&g~)-Rk*E<lUrw)EhKR=RKn81%'
    'zE>@pXT56C#JxnNwM*E36s&1K3bmiyf3i>BO5DUN^k!Kg0Fu_mcGoeGw6+g+eE=klW&|YVQs29~o_BXW?^Q$LqQW~SP_9jjzJ*+F'
    'c88}dObE@DRC{+>u1N}#3v*%5{#};KTT0Fd57fm_P~)3Sc)2mi{1M=Kl`VtV8|+Rph_w+i2<H{-F^ILL&mh+M0fShV_ZY<L+J}Ha'
    'tlvZXakVYQAg*N)d%K$c_UTJ2v^l|GPtD+>D|a=6=*e$)JiUJT_IFMqyGU{?OOK!E@FaqGoj9G=iF@C<^_5Z|=E;Q<o)n{&c2BaU'
    '{3bEV*co)3ZQlDtFrcRYZsplegxjs>z&TidSH!!m`AER~Ig1o%&W70)IvneJ6FMK2)NyX0L3576K5IKCG-x_pzLNtfEW~p1BbeQj'
    'm!NgxQ(h+C7^%=M__+72Z~>O`;p}9)vsWpiW^XE4MF-7PoU*CEwQDK4&DM@;$#KS>!Pbgea__nW)bru3zf2Hk$f;>|sk`gy<g_P{'
    'y183YgHw;7ueB?Kk{X<JqfcCKj3BQ0Udeq}B)2#2$DA8)_Qd8DjRbbh??Qq($HU&4m;p!IUGuJg$MO!|vAi4Iu{e9CB;b>`?>hmf'
    'g@7L1uej9g=6=NxCUn2@zJI@(K~4C6<-_QH<-_j%%E!I?m5+N@WS>m`o65;MpZlgV&I$4y`Mm{E->1TngU>D~?=ySxZ@R$XGP4|k'
    'v-b<ZEYYbmd&_&o-9X4t{Gla+b9#!iKu><%)A7^KKff}a;v!9g1BW5F<}d_@4?}SM!!RR@pv5W9wPibpA$V{Y6sL#Kb8@f54{7fU'
    '6k?A%*GVGn1i!M=c)WSEgDqk&%}($uThhlrQY45vAD`4nt-IA3efd1SUJq1Q8Kn?ll-tQrj8Y0@lz0QPLq>__`qfz(B}+zOq*0$y'
    's)p1u3Mo#BpcGn=w2Kb<f8rG+v>8}$exd_Lz43W&2Rb=0!pKZsO1spH9GI|}<;tJqUnH!AMQWK>6DQ*<U<3>)ebX^^tT+sl*$zx3'
    '26DzuG?43FHenR<9g~GVl-k~!^pku?hOfYZ4g_w<cjQ`=aA0UTC&}+x!nozy-f~VVa$v%olTyn$l_x}p&Ig(kRg8(#QQuQ;IVT<E'
    'z=Am^l^xFEToq^_8NfO69SOslYJ1B$NggY5m~#l^HArVU&|}VF=tRRgYN-Kp4i_;TFEwG#;UpKs?I6OOLj*WSN;$&Sa%+3bIewA@'
    '3+5b#77Q668_YS`w49@kRkoOOxR&1V9XsXhA}VL6sJfK1YX$;0q7oe$mxYcf%Y`OR#GI28sFo;ME)(V)PB767402$`oRc%)94R`u'
    'q#GPqK%Hgzi^X8hxfW~N4wU;?aCCZYZ#hR1r#Q?x#f|HNMy{9!2YSFcYN-Kp4m+5erAj6*5p&M9klE<ladpz7fdHYTw*$v+*LH>8'
    'zc<T@Xwx;KoaBv+Gn~S4sTr5`xB|x&(~K)>oQ62v$AxCxq{k5+mz!}1F)kT{=#q?S>2lQL5M2`2N864&>2ZiI$=H@IXEn|ux+Lva'
    'zKy%+afmLpxuuIjHz(sTVO&d?Ynd@I5L3prl(`lk69X}6d`p^ZNwWJuk7?su+FT2jiGi3n9uOz0fdLaI0OBM)5ECZ=;*cJQi4y^F'
    'vKkmMaUvj2(E~AYA|TGB1}03L1c;;0V#35pfH?XvCQKXx#L=gbFmVVFM;}MR#34W&eIB74uFWlRoIa0G5GMl!vD4=fO5$XIBzF2d'
    'LQ!0sTjDr<9-%Bw2FPNk&ZEV`*aBhfq8<o|V}UewNe_g?u|OO<bsjC2#}>$A6$DdzK;l>+kexb@77Jtx1hSj-KujDUkljHK#KZvt'
    '*{Snru|T#!AiI+uh=~IPvQy{LVu5UdKz0{B5EBOoWEByW?3$r+HFo{OT#V=5=N97s;mnC2AnG+)o%ZK=1!^Y!OKT2G`Abp%(wf6k'
    '_0jXJIV@$Lpy$cxt%9Cs&0#tBaZ?j?mYmV$bc3)HCQh;4wG$@x#uvSYdG>o3r;Wj>@l_<1PlB8EZ)`l;se$<>_GrhArB^Q^XrF8Z'
    'iwL2a<9f{!lW5OG1Ph72okXu>13d{~CCN3DIK7gz2O>}RN`_(*y%N$+Ee}?bO*4ttE6FNs_-cQiqal;qph>AQ(I;1~uX>z5aLB_c'
    'n(&>t-`_9u(jDf$Wod7u+vjk8((Pl-*S~!F_2tWXI{p0$G@G#<b^g}*lf2nFf08%Q`IEfqI)4&7o25;^s28(?tYyjTgrl?bM@a&Y'
    '40A$BP97WPk_U!4sg@^?4RgsO!`x90#D=-#fniQsf|AFEx#WRi&Z&XeFqb?q%tbE;V#8c*2PR!f)qo9iDImk#MGnM<xfFn5jz|u~'
    'hPf1gVNMYzV8dJrz%VC`$SGjMTnfN2r{579=28HLxpa~Pv0*L+V3^Ybv0<*Zj}3DvV8dK(2hIRt?@kdL=4w0OoFE5c!(56xhPf26'
    'VJ<~rnDYlY5F6%F1co`qIT0J?YCAB@sik7WTx|!=07V>Zm`f2D=F~n$Y?w<CBvsVESTN^AkW^F}SW_~XbCLljT}hl|G3O*Zb_S&6'
    'Fz0aE_@R_b9&=9ez!@N=T*47?wSDYHN-1K_L4n;$%5h{j90<Z{G;s)XP69cflam8+5}uSm5+3!AWH9HD0WwDow3u@^Y<kG6<S^%u'
    '+u<DYm~%MxdC032Fy~MJUn{lLh&hKM;2e37DPhjxz~u2S66PGDoqG;t%sEtA&QWqT8_YRe+i$oX*<#MgcI<#m*<sGf4seb<$k}7g'
    '$sk#<^pvC=Fz4g|I7e;=$GgITaqLD)IbqJ>)bI^HL-J}S%sH9BJxAVGGmaQf8Dy(e2RRqaImL_}kcpGJ!+`+(rWl|&%sIvF+>ndM'
    'oKyVH*Q(&W2DKe<j#?_t%v#%bWKJjNc|tkQ^+24@BNdR(Los>5A;+nJkYmLF1?Q4VD4tT@9%=DYZ3dFD3Q~M;wynKPXo0lkB5%gU'
    'W?azYG9Fi&aZ!zP4vteP6mR2_9+&VqYQ~Wo=P_M;OP8$2VY>L1E=7;Sbnz`+CN(Z#x`dW42R#ncCA4%os&Nt1CAM@q>2a7Yv8Bsd'
    'kHd6{EnO~ZT*7ooEnSqKluW{eNiAWNpOg$?%1}!g<tHUWm^9Rq#_BUjm^ReX#_B_uF>x{=jy{DM6DI@W=wnzgaS9-gK8FPprvT#U'
    'gIF+e3LuU;iPk{kSObVN>4A_q9L_rQlaj?U*a8`>{G?>D5Vk-FD?ce&EQKwQ!pcud7K>pE#IW*{lEre^0y(Vwq-3!mwm=XoKPg!('
    'i7k-C%1=rbi((5zvGS9W#j@A}S*-k|WU(-|Ko~1ODOoIyEs(~_Pf8YxV++Kw@{^Lq^4J1-to)>8u|T#!AUk~?u|T#!AUk~?u|T#!'
    'AUk~?u|T#!AUk~?u|T#!AUk~?u|T#!AUk~?u|T#!AUk~?u|T#!AbWitu|T#!AbWitu|T#!AbWKl9TvzA2xRZ|Ku8=11hQA>(P4q?'
    '(4{!)fsi;32xOo1Ku8=11hQA>(P4q?fIwCb-P!{a2MA=Z&ZENu*#Uv<Cp{1o2MA<;&;v1XfI#-@JUT3p9T3R=qz7W+0D<h)d30DH'
    'J0Ot#MGwTp0RmZh?}>fIt%slVUZ<pR3!%X+kP1j%a0{e=sfxuNgao-N$Uq-GPZd2o_=nmDy_Ld05W7HCAAfED5ae&EkRfh?xHdr7'
    '7fPI-e~eoo?_JM(z3ia(+dR5zf(_<?8Yg}2(qazuA~ukN7Cb>7K@N<XWCJ;90Tko`<iP5cY#;|Mf`UAP9O#v7AO|gif;@m6IK7hG'
    '%^r83q>OP3<V&0GXT~kmXCgRJ_{i_L1!9lw55O%@xW$q~+yaHUl*|>kaIWh7lj(7;u!X;zKYZpu#F&<!zWI_BYJtKn^hcl;C~U&P'
    '4(sZ2L(%ow4SE1k3-#gXq^d0W5Vb%7goVip2NZBv7zGp-c98>dSXgZzdu1r#urLZBEKFLuDd4cM+CKKmP{3hf6hK&*G;~tLVPUm>'
    '9Na?@hlSPlac~bs92Q0qp-++=h|wpt9r*K3av(;ZPz2}`wH*<oPbi|WFhv}UKA{NECwe<D`lPn+a8AVNliCh~d*m-Bj6SLD<A6d+'
    '7=1zsp-<F6j6R`+!osW^h|wpMP*|9HM~pt91kfjXAV!~1Lg*98012Z{YCGT@xsM5>PilM1Inskj38PPHd&@a$9|@yRYJ1B$GEkcc'
    'qfcsk%Q-;}#ORaS-f~Wm5`ZxJgb1KdLXiV8`lPnEoTI2p7=2RP#~1=4j6NZhxLO@#!swIQJ`Q3g!swIQ4!%}WJZ6kOsqFx_B=<36'
    '^hs?8GDm)qGe)0K2Ivz-)r`?6wS7nCbn-D%-a(&G#^{sUKK2At#^@8u0DYndV)O~2isOm_GDe@&cECB(gIF;7gbG5RkQ|87CsY9X'
    'L>;Sw(I>Ti=blqA`h*HVpD3ypj6SLD;GQF?S}^*A3PPVKs$%p>Z3mnqk5$3w6Dk0GqKSjiCsY9XM4~gZ!RV800Qy9Jk+Z?*lWYL`'
    'M4rcNF#04LfIiW`h|wn*m8#b7h|wq60Q8AufNU`OBpZM}k&-+cj6TT*pifBsB1WHN1JEb_BnM*jNj3m|;*%VR(I?pg^of`6xH!0)'
    'ffhyi)aEwIN7`rel76)r*9Q4SJq`sxWv;Y50uf~EQ2bMEZsVUwk3->4*}69TDXVcF)5W)RDS8~Hi*M;N>2a7Yp{2_~jSHAAp{2`F'
    'kHd5cEnQA(T*P#VEnUuf9HvWb>2lHIFkKReLp5q(!h}g64%O;`m@)~(p*l5?Flh(`>3Tg7(}qBhu0Di>iIV|w^eN1kI2jN}AH$4^'
    'lL2w`IV_ks1rSFc#Da-a0CDt5ERZ<P0OF{l=nN!|Gk`b;JrEMd89*F$7#$YE4hUfdBFGL)VF#qJ0uf|~#jpcnSb+$#!*bXGIjleg'
    '*<nHKfFM>Ng6yy)c0dv<5J7fW6gwb_6^I}^EQ=kG#R^1_9Tvt82xA2z$PP<m2c)qA5oCwOu>;~*fe5n0^4I}+tUv^{2PO^>$O=SI'
    'dtl-Kf$a2o!~)p?f$a2o!~)p?f$a2o!~)p?f$a2o!~)p?f$a2o!~)p?f$a2o!~)p?f$a5p!~)p?f$a5p!~)p?f$a5p!~)p^fvi9T'
    '*<*q1fk0Lug4zQT#{+?^Km^%if$V`mRv?1f0}{srfvi9TwFf2+5XcHdkUbX29tdOwBFG*KWDf+g0uf}71+oVMS%C<$#{$^{fvi9T'
    '*<*q1fk0Lug6y$C_CO#j5JByMi30?(0uf}71+oVMS%C;@50sLC^j;^w10u-E{|i9`nf<>zAcD-L&UZir*=O1V5oBLrq6Ib2Jx%Ze'
    'A~-c5g3LLBdmw_$KGCjgGKYGG#vp>ctpeVH2r@f3yC8zh@wQ_SLFQuMBM?F6jJ;zJL1qu>5JZr<KKK|!kU3I!2qMVadf+XHAag<R'
    'A&4Lc>egXiCm|Yx2r|d=jzI*OONI|Y1UV=~odOYL_Q#Gv1UVY}BR~Y1J-0m&LFT-_cMw5%wkD^wR}{h5Z_~G5zA}y=(DLgyld!@O'
    ')JDI-5#(*?@?l+In^EHaEUUvx>dl-R9M-6Fj94I>u7%16{;nJYHg?7U%;aY|Fk)jTmlSUX9^}A;jhzuB$JW1yOH9=EaY}(4Gd6a{'
    'JWeT)uL+3Jz%n+I=VY+4lPhwMtlc?TZ0t-RGqth=C!Co&Cy<$15hvly)H#97)Y8M26V6Os+sCfCoN#99+P-5ZPdGDmZQtRXgfmmu'
    'cECB(5}a^m>e>#1H03W6&P<&NWTsXOKsYmXZEraz%B2#{OkLXn96%c831_Cx1RzMt-9Z?FRNKcul1vzaRNKcvnwc;JskQ^o$#Niu'
    'AZ0?Csnt?31gW-<U2{2O2vThyJ9Tr$5Tx1;I7hNv#t@{O9fBj*<`#~u)U)gn8aZ>M^w5itJpv<VPJcY~BIJOu$hEn}A{RXlL6I{D'
    'U=O_rOIqb-TuT?FndOM-5?i_)^*BtI*wRJmWjSHGq?RscJr2_)wRE}YahNU%1Y0THBoihKfnY1E2V%+)h(uFXlAJMVGKfU;dLX7v'
    '29an%55&aDfH=xZvLv|P4lIB;`WO~WoC1iW&S5c-IK=?sWIYfPrx-w-q6b3a6a$E(j^YBj*bcOSI0rot5~o-|9Ca9r!^ClbI43<2'
    '6UPDKob^CV93Y0Z7olJ|T!0+bUIflJzGrjbECtd^;#w<7(bcAIRuXNM;3CsIsU0)djowM^m>EUV_R%&xPGSK1=y~!c^ur!n<2;vr'
    '?pjGo8Kj*n3?Ug?NeU+_7@Gx(v7v7zDaPg<lRz=9jd0M5=+`-4=kTqiMOjH|4{d5`6EjwU0Zc7=B|)27+Qf{7Q%n!7B!z?W)g)jg'
    '5tv%^N|H9UIIxn`np(VGiE@i5D@ie%iifGOk`xYk{{dE#G8a{bR+7Rvn!A-Go!ql^pRQJtUq1fz<ELLga%tOOmY*+eP5NTWwkCaT'
    'f;H)jDczd%g)2Ju!Yv91yZ2A4HF+o8qF99P71#M<F}k-{fbNw*t70*_w^&s4;VcJYbZ@Z$-78g=Vlle6*d26l{gy&Suvmodb#fp^'
    '_ZExLy=ti#-CHa|_lkNk#bI=BaXaYV;xM|mIDqbz_Lbr=y0^BE^E?%Y(Y?i?+;VEE7~NYOLieg)#OU7Q0J_&Js$z6+ZQtP>hta*o'
    '0d%h>4o3GDx0740c#Q5XekZqF@fh7(JV5uVck~$DTRcGbN=rcT7~NYuLiehrVsvk92b?2ChsWsN+738}<Uow>t?j^UsooKzdyC&e'
    '_ZE-Qy~QJRuYAXV(Y>{OhjRi(_ty5Y!Mg;E?kxeJdu60n2^ig5+s6g<>fIc3P5|g$na{EWjP9-NAQnXp#OU7IK8{5x0i%0M0O(#l'
    '5Tko*JK!9(j~LxsB0%>lNggq}x3=$aPQ<z8N(8y(6z4>oTduZ`<KIfex#ep6I2NTuoLjE8@5r2pbIa9sAakSyh&Z=gZ66!FOT@Y5'
    'YCE{+sCUG<<!bxb;9V6_%sI*Ke65nhoRi$nJtuk0ImrWqx1?&qHS25p&etkM%sDB7ua#tglrZO{1nxO<I}%~eNi@!9S#^HQIVrcC'
    '6BShp=A2Z3%#m`HaMknL-g1sCjatZJ&LIcNze>&_k2!~cdsY#LuzR+)k29eb!tUAH4rGpcN9>-h?K?7uuzR+)@5mg&?%CQ7TqWuk'
    'v3s_*k6k4tWA|)rM>e|J3=$$q^)W;HWy!#P>Ge2dzAPD-FM}Eft(UdAwO&R&4jC^?2FA;z$6>kv+a;-S&~#al3n}Yym@dGDRMa@='
    'LMq6GH0g1eF2IF!(Bm*&fD7rU#z7ZSK`x||9*5}yTu5g%4!V#Eav@#xI7}DdLQ<}vf_+E@`jD&|2z^Ke`jGSygg&GKeMtHYLLX9r'
    'J|ukzp%1A*ACf+W(1%o@4@n<G=tC;dhosLT^dS}KLsAD3`;ZFsAr(Ck5(oN_COr@m2l|lIS;Ri10)0qFJrEKH`jFIV#6F|~eMo0L'
    '5EBRakS=;4CJvCp$`w?w52-*OlGOt-aeyRN0VSniQCxs1RskiYU|C#%ELH&}rC?!PfG}18C8c0#T!1uI0VSniaa@2nRskiYV0m1C'
    'Ja+m#Vu4(MKz8~(Vu4(MKz8~(Vu4(MKz8~(Vu4(MKz8~(Vu4(MKz8~(Vu4(MKz8~(Vu4(MKz8~(Vu4(MK=%4PVu4(MK$Za|$rvP%'
    'xfvwvb9x{k4mX2rhF%W@#NlR;%`m8eNFZ}FAWqZ+0dcq)5GSdDNFZ}FAP(t)m^eTnOJ_9qz{CLpSq7BU9!MZ_Ga$~S2V&v?fh+?`'
    'Y7Zokxfu}Ws0U)=0D&w6O1K9m4iLyPpoD8%W8wgTECWio2PO^>$P#$KWwQ}Df%IOdJPs(SUC50CO1KMxFC_g-Tlhi~P{MV*5#%DO'
    'c{tI*IG}|4Y#<l@vc+!HPB!(R67``oUFR!5jbo?;mlhA>fD-PKyHE)(Lhi-^CETSAe9()Cb{tT`UD}GA5-L%9Br^^u;Vz&gr(Q`a'
    'W8?@IRd4fSI=vFwL62|=c2JU2uO#olM{1YS!biMbNogxT-k=ivtc(LnlHsJt?+=yW^76I^mEea_KqU^oJPDQXb2ZKXem;IXpE#r>'
    '#r5~ECMb!O;Kr-OykjM}Nt+xG%Mw+vqr^(^Gp~+oQt#$ya9o{tZAgihD#&py%&WBnbX;@$(4bp8K*u$=1MIt#1EJ%Z+gpQfxX6Lf'
    'ab4Si<68eBbX;?LYtU81!H#QgZw<OpE)_ejxxF>$3ZGu>03Fxd4&0CG7op>t+W}bSEC)izHMh5%6V+0o<C@!n`%x_wI<C1LxB`xH'
    'Aaq=FJK!A2tJrZ}+kxX+?IU(vb35Q1`HR?b&Fz45vK$B<*W3;`r^tcOan0=@iDHlgq2rp{K~OU{w?WP7VjlvCX|Bz&jcHc*`Vc`#'
    'GdH&(%~_8F5zXA(Ml`Ei{gPXEJ1(^W&66I7>5^Ky9P~I$7i#IEuJnO0U8tqYNsq&Hp_VS{Lcdg>-HyvGT`qbYrb`AXTZ|rv2~$AI'
    '7NuW@f+<r#J{zY8V$u|l&qnFj(LmZn1M=AfJrEKn8bF+=2SVa7E@EVV<{pqZ9Q8V~KXVUAoM-`Y)Ins(#hwNeZ}I4>US{u?$VD%U'
    'Iv)L|muVG;YyFPl>9tQl0s7h^z~QfBczW%V&|5h@Pue6EsI=dhb!#W0zFx+aeft+Zj(y$H%VLRpIs{`a`g$2x`rXkVI8b(|mnG}Q'
    '=yUGU>ULT$V}QmGea>Bga;I0~%@}>oU0UT%>t)H8G5WlA2|&5iD+yY;b6_R0RqnK2mXuLM>t!i*gBKRPETtb&Er93kRtu;PNmdIu'
    '8UH=i0?xm^e*2%;8I+fwrlwi|H*Ts0a1*K)!0o+i0rgqdDLJBgt=vz^QJ)sms$^PtC6EtYz)0#LgZa?89ezUyd_&X^GE!zwT5=?_'
    'l*_GHCV4Cuv8=@@XVu;lr{s~y)#8+KG@y^3C!m+oA0#f%ti^JB`Jfd0Qkhd|_xGAHG&@q6Lz#C3B4rv#WlpKRBMdpZc_@{+vh$8C'
    '%mx^`jGkmy7BYfnES0m}m4z9ENolE^H*r!HtOUeKX{nqyaZ(nn1jI>csjML<S}Ny_*bl8#&Ns3D?oyc%CS9q_FcKk^50@vcW#%T9'
    'fByXK?^P}zrscP9fHW<ZXJm>L%XtG`J*>-X4UqR|rEe+A)Q>9Sr+Lp(mO*&~rC?`R-hkVIW-cu(1(rA9cA%Nd4?%(D4Y(aZ%BA(8'
    'zyK(22R0pP3n(xEira_4;MxHOKyf>;=}6mLfdNq54&a^Y9bo`eZ3h8RLA@gkfZ}#w(;+z!20(E;;2g13YhVBrx3`=lx5FA30LAU&'
    'D}*&L0E*j(g)wRe7y!lXfOE1Oi0#PM06TI}1F;?18em73##w8y9l5rTIma4oN45spk-Z#<?a0;uJF?nGi|xqP0z0zW4vX!`wH?SD'
    '^^4e!Y%O%2TZ^3MLONOtedo2gbq@zM4!X{3bL$<BdK_{NTMInrNsWV!^V-}x&Pk8MbOC<ztjA%x0JnKj<Dl2PHn(({^f*ix;50v|'
    'aR|i3%`IJydK{(;z%ZTkI7}A+VLGdE2*Je7EnO~p9Ht9Glo~Y<0hqWM-~z24h$({*rA`mTq(O*MeFhPLiJJjvQXfJDVB%&#9CZpE'
    '1TfWRK%ArpLgF}tC?!1*62~D#sXB<9QhdkwXxR-rHa=R893C4VEhqNgQKzkg**v_SCm`U6*Ym(!9Zt`)g~Qm?sLR%++*NZe=Z)^('
    'o$FKDQFH6ZVW+HS?V=4MTFtFb!;bOMa@E$6nrr>mfY~m>0|TZ~bFJT4Fk5}wdSt=WE7@8w!AgJy)9ICLESRmrZ9TGJ>XmFQm|!Kq'
    'g6Z{2LTf6U)m-a0NSxOAX#EX|^WJK1y&;&cnp+<Rq2^u=>AUi096tT>@pQ$6*h^f0J~f)Ion6~P)3yF~@{ZS)Ty0SQ!<W<R{Hz|l'
    'R9DFpT+HeGpZ@do%a>1Irk5}0%ZKyv+soJ2|2Xrny0rW%>Dio|Ez8-?sXyCF!mMZWa<-yo>#xnPYb$!TAZ80j&UWdq%`a;UM$Z=I'
    'Y*x+IUt3t#7Ob8v%h{Zmt*Q_G+19l=J=;Of=GAQdwZ(O9UeA^k;ewpb_7@k|#f8muigHm+*I!*)R~I+aB{^M^)4BfY(z?3Mak!>5'
    'Sf?X3U4M17u5NQ4lG<2#AS$2sr(0LIIS|+EFza+hP1j#tURSp{5!bXR%XCp5iAtCLbj#}E=13&TchRcp`l~C;>f+{1Ttmdy>C~Z!'
    '{neFqb?%zE=PsH~$8?m^F8U~^?5}WIR~T$F<w**uSb6<EW$LeTT2~oEJEdf4_V<b@`>Q;xt4!2RskVlKn3DRdJglp%TFG|Gvtpi1'
    'a?1WHkLxOnZ>GGQ#FVLC_U}{X{wj~lDw9d=lxI1m^>WJoDo@KQIdyU~<wZ{El9;meS9w}jSq1WDN-{=HSuaUq%Kj?P>ncNRrVLW@'
    'Bqe62{wmMwDsOP5-#&d=u3`5pT1s|%tKhWED;RhFp542braKwcUE0xR52@~+`?KF*KB{|8{qDs#-DPI_O?NWQtCH!zDw*b0$@X7$'
    '&eyEF>sM7q&ACjl>hJWsvSCaN@Xgzj*Kcc8|Iof}7`$$1UpJb5_t?H}?C&h4_H9#tXNlT(rNPeT_Eq!XRdf5QWw5iQebu60)k;(D'
    'obg%q&t|i;N%r5?58$TF#vWvU*SsxzHf4V|ss7FDX0KmY)Y;^R&HHAr-`AgI|Iof~(C_OnvVUyfH|qBd(&3O>5tX+hDy#nO`;zG@'
    'N?CqE-6=Hk^zwTCaH?9|FCV`teTf6cd-@W`go{a!yOS=mIv3Mbn{ttpo_ANeYEQ+OuJ**9LNV#?N>?SSSkqOa*t>Y2^s>9sRhKHx'
    'bag3?mKKxlu5?wYiZ@-Aic2o9lX|ne(p9tKxaO{A#j(p`*4?G93Ra1xuV9rZXSKU)UG=PzOkdC9P+~Fb?pjxMt85OHQn!jcRo?Bc'
    'b=A7c=2R)It7J9n?pjynt89*yQof2jSKjZgb<x3`*_<n>gE?c=th;MnR552Z2TQ7A&d8JH!|qzky4KCfk{X#aPR+Wz*0QeEx5|W6'
    '%pAv~-e-=x>z&s1hE}JL`k6D)$eDN7JgsYvt!g3FG{>2N?=z>}H6PYBr&hx_sokR_XWm`&VO?`>6b+@cIWB^IpP6>od|cOD8hu0Q'
    'Zq7<uf~VazFDjgy)9rRuILFC$?=$D!H7}Z+v#!<Mr6%Y2<}7C3UGr&Ovu{**rO-L{_TFbMyK6qLYYvSjuk<=+m2@w=Yd)`QzEu%L'
    '>YbYlI*YrIW4EikI~m!XwpT63UekW}?M=(sZ2H~v_G0PSVcG3ow)aYBOX_x?D-g@>>?-Vbx6P}vpReD&c~y4#b-TOfRh{d<>YN)`'
    'b@!VqwCo<*R}F(#jqR((!K=phRny>A8^45Ok6^buwXaHpUCr&Q=E19OlZ<oI;8jcWs$5yM*L^OHs=N1Jb*^iwy4(J%&heS5yX(K|'
    'Tv1eY_x)F$%YmxyVeqP<ebq2{)!4pj9K32Pmi$00`Bp5kd&~Xqr(aG^G=;V)wN1Hc+MxDkP-ty$OCa8#$ylc<#P5zv$2C6hUdh9B'
    'iL;0BZ+jj>^YU`C)I694y)RAmL2hhGS+2g@n}hOLuZ-)bWd7y9O&@;YN&oNqrFs2u{`%8D{XajgKl%^zkN)HF^{0RODbw+M2`(Pk'
    'KS+h$om17m?a>_b<x)<^<MA++Q=X!oh%WVX$LVr5F}TZVs?xo#pq=?so!Hka%PIIeUt&b258j>gC7tT6A$yuC4Skh?Hq@7y^6@~E'
    '4fV&;H0ARph9jQ%>o0X?GB#cg@#Hx`W^$bGp6tON>vf}?+;p5meGNJvPqE(hvm=wKDy(Tb)K12n8O88n`uOKxra#|SdOl8ve3^`)'
    'OT3grJ(T81=eo?~?ZMS6Q97Tda*pO;<1|gKD(YufwJJNE>R03F<a}Rwz8FL85YA_FD#yCK;0{!$tX;Vv1cm9G%K7Z*66$^N5|caA'
    '!5<EngR6ZayQDu)fB*1lI{o9}^<$mT*z?had^(#{U#i&iDVi%ar{kIPZsbCzQVChtMW;G7g<#I{bUE8g?Q%JY3C|xcb;3ia15zM+'
    'DIuFfE|)sO*7ut(_7p5n6ptYi)w|Jj^bCGEUZ~zIF45VOEkFIgm9c*Lc>MNS_vNR5`fva3r<echU#xri-~aeu|Cj&yk1sF(@?!rO'
    'F4OCWKm6&NrNi{~_4xAj+n3jme}4Jf>-pDzKGtS?{LA#^<=dC(_1o8fKK|hkKmCp|O74oKbCu0`%5-Dv@XPt~s;9T+|2R*l|MT_Z'
    '>C>;_`04ZC|M2slzJ;%!r;q<!|9|-VxAPx=wp=`xX+fSU2S%H0<lmvINksk7e^I|={<Uu9zfFgFa;*LJ`Wr7_KYaT3hrj*f>(?*S'
    'KbpGMcugUC{Q&H*_K((od;R(R<>lw;^XE#1Km3hnxB{lr8)u0B{>$t6+jSsACx2Ik(Ax$+u@8w0GrM#JDZF7T;-Ai6{`Pu2|Lce8'
    '+vU@jpKrg&D=n;dUags%X=pys^r!RJua$}Z`CtC@f~HRM)c^Kn`uO$pr!U|B@GpPzFU>Fh;Safryw}t8?fi#-{V#v}`EdR1`hCj('
    'fBbg%^!fbp_P$qWrU6?@r`NBaKTLn${n7vJ*6*1Yc8s@lVAJ0H$Hg1-H_N#<@}iBuRyKR7le~PLe*XO7e4B&4Z0UZK{`}$Zpa1f5'
    'sQmcT?}E9e&du@ubp3d$e)X1GJEXY2{<rgQ-(J4fe)UrtBG+~IcV>9|$J(5}OuycK>N*c2%WX)H&s44x9nXAc2q`ki@tW=8;T5&l'
    'hdLo$jp*3~HQ`_P5liWhuOH7TyqxAge)?TBoJBU6{OD9F@^byVPG~vbAq#{5kG(f*x*W$2#Quw(`vEHf_)WHJ><MXPMQi-%s31U6'
    's*bL%idx2M|9YPl0C{=8<z}XAk2|9~D=!IRJvjSv>haT2LqGiGhu?kxsQ<rU!O>H+P>x^LrKIgyx4%M{5i1Q)+0NIyjN1>t{6?K2'
    'ZE%#Q?&Z$h`WyCyksR@hIx6k=Uw(y4C;h?B#V<OGrTz5dk3Udnm?Nfq(d4W<;ADUOx9@*mfA|aa3GC<}QuwkyXWzTO`vV7!MbaR='
    '-l_e!AGZB_-b<Kgz<i>M{cM-x#&NzVyddOaTVC#oNZRi|;=QomrW14X%JBl1vj1hnC1Pqn_hn}h_g~guacUp|0IjfJ1}szTARa3@'
    'Amsc-mxFrzxBbr`O~u6{_2$r-F94LOzC3iA0+sYF=_`P=lw*TlsR(^cU$pj1;xg!!YqnYUMROf-_jpFAS_`qy^F~w!0!DQw+^4sF'
    'TqZ^$)Dx;9ZTh0S-W`S!Zn3OOm{9qd$8r9#w`2YN&%~@dV5QA13(Wjc`cJ>CKkoJS<Jf=s<KBMyWs5(rzx=v?r_#(nyd%#1>F@pk'
    'Qf_j8D2u!7@a!)H=Rn@XaU#N(spNnB36}8pKmXAFe*5tUVie2z`)~jD(=YJ-cYpkcfBF~meg3aM{ruCPfBM(Iet3RA{^`d*{pn9X'
    '{s_}_5u*)C2Lv4Tdl5{(N0|W*4@08tg#`cd`(IFc>YMxX?*LZLMi8G|^v_Pk{E<KV$Mvs2{r=lO|MC-RLjLnV{^-8@E)wtj9nJ~s'
    'yC>W6+mHK?KmLTu7l5Adbf+fy(0ia-zwFxtQNR8M4gYoj9+>Vw{R9;4yB~j~<;RFBr7{iGenw8g{GmKsgN3C(!s>TF@?pgP5%&Gp'
    '?+C~+)`K?hiAWp%(+|J=_<ydy?0;PU@~``^8F?ODz;`$`>#%+U*Ia*JB3}O6{>u-?U&p*I^Z94`aR*NF%9#o1$4l6v?16!G(LUSx'
    '^uMkkj30*_;D=!lcbO_;m1lxV2kg&ZKN~23ESmJ>{!MlryoTtja=M0ZY_{z6$9MR<fBJ|2{m=i~fBhb=-FM%&KmX@H{=>ig{rBH}'
    'SO2BpBZO<%+?bz1T=@I;^AGVif{c%D!KYLUo^p3*_vQuv3*cdZYUA+CIOXH}TlLN0@@7l_XWG*LiMP}z59}5v-oHf`1u#Jatb%Cb'
    'H^rYo8#3X;w@xDb^6U2VhYtd`7e#5x_c)LYYKc)8@lT0R*#G@!qW|9?e_sFf*9ZKv;I*8v<Oy;A2wXdAv*4J>Zu<m<l>f5-_|q?c'
    '{V(g!a(Vw7iqlw>x;#}gdEL10SJ;fpwEp-{|MLCvBXw&1KmXfbf5jt5aKIU7tWp+SFw;i-iW+n@eLYqDjX4Hjv3~uIsTMkc#E@?x'
    'cHm~=V^lf+WCWhO|JNO;!k>`bp>pGnBxkre8{%u!LV?h`{N?u_>;B7kKroU;DgQ!7_38k<*?;-v_n&`5^7HfhTLX^BIV@Y1%5&;4'
    'U8A`F<+oq{iYRlTxL<#NRYjxp{m(!A`~GL7#tGQQV#_<bM4i(vp-JYMs`vgPJ}@J;OwIn6{ih#yocX616I7hR?M20zH8)rBdJF-z'
    'N}s}biCk}<f_R>m@XvgsTm;?|c!+u5jvxO0x8Hx+iDijYOfHS-60`X|isV221>gUHRB7gh#e#N!hq3=;8h>mcr$d<x?%w~5Y>o7S'
    'H$70R|D#(M{_cPHyQA&du7>It9P1JGdbD~RhoL{-9*eh|+pB>WX6L6N=j!3I;(sGv+I%$lx8DOa$yfmvTkT~F2mOI}<;eK=W)HuH'
    '=0m|J@PE^v!sA?;fp^l{mm{UcHf|e=!`8)@4Zs3J`16Xl5qgIY;9rTx@%w6Qiih;0<9XX~q_{a0?aWazr&OT-g6QpF+!Rd>`8d!A'
    '1pZ#=?={7}G`}ovH;08unEvO>p5c=~Pojr)Z}6YYdrqreX%AA^@)q%Qpf!GV*H?(Nid+kb{>~g|FEi`tA9kb|bUpWVJvQU%WZIe?'
    'Y`}rLSXzcRS>Eh0zHi3Zu)$8}6dQm9%&$Qg&6fs~@`+}*^Q?3izhHcG8XwNEVODrJ>BHjqqvxrIYBG=C`yah7HJgohXYTn)KaF;@'
    '@8^^L)|>vawfuBnj!>SQkKU<g?}G)J%4d#$V-y)cc#P2#G&i7ThcnxPP-3?jF&i;K$+lDrQ-z7b{@eQQ{=2*Vhp`?{-}CP8HN_2X'
    '4crL4<E_saW)d4d0qg*Gu5JyD&eI?L#`bl}@7~9lAKv=Sz{;zR4Sy$?K|azR`7QKk;a=m803;R{vazj%4EGkH1tuTRzuUuXxIONn'
    '!~KJmm6Y0sUoH)rt~C1q|El=?w(<S3>+A6QxPyp;Xa`riKX`IL0}g`8x@lWH!?>D6W0|+__Xp-@p3g7COyq1G&uoL4;SRlfw)OL8'
    '`wY^btPin%hV$baaD@Ob?>_|r&>kVcP7u&|WeNeI5d>@i0sce#Z@&OO%maKB!LLQ(!)y_71dWF{znG}A`WE9i%j367<KIF-7*J4N'
    'fdZy+A3T3EoxknpU;6of6a!c}f5rgjjq?wmJO8gsU-vBg@B8`3#U8bvzqy|Ox1sONy>b3wI{)<>o<DPec>YD_Hl4qd_a8fdBfKVa'
    'mCJno#6uG92MUV()s_HE7zWz9EKlh(^Ec^h@;Cbds{?LoOaE`?Z}!}F;5YEkTl^;mJR|4g;a^L@kZa&*gnvP*4m<6E<{hO&)?x9f'
    '-CNaZz19CW*nfg9=4KK8ONP6rQvo>u=uQJlVu&Ayo^3sp)1%eIb>r25<g@{Q#}dw#X$1J}sI;3qK_lHVx8b-ONJa*uP*AQy=*4><'
    'mZNA7ehVxA+N+JiU*mk8HQd@A{2t)C80gc$E;QoD8|+>##tC-E`?6cSl^AD2i_1F*YB@PfQjP7UO_rx=e(H=o&8Mf@woFg6XX?Cr'
    'cn70ZX|uwv;x1X<)l%tB(*4}ly6b-LIaS6ya6MuBpbL+iWMsvFdh)UHy++Q&WyL+-Xdkr8fX8z@0*}Z19=3+FkY;sv6VBNQ@2*uQ'
    '2=l1P6utw~7y0xBz<C34Xm!11(3ajjv|M&vLDBgnn9oA=ZW;fAbu5UNuxxlpzz5^XQr`1n_)EmVx-)B%)dB48z&FCOcX_hGsFq}8'
    '!lK6xJGKFI#6}n&PQs^UA&C-b-$oEf(!IzJunxqmEt;_orV{{`h=t9-rvaqmKzM9NS=%=r!5(SxINBEMZt6Ps1Yf0o#SFEhaZ|t>'
    '@y5stj(jLD5Ax{lMUF2Pw*>~>VedrGz$;B@fiGwtq;;Ut6PyOG8Tj5lw#lCz8?d%dt~p&ZoWf${6j)o*gk}d~WwHO`+&@XT&_CcH'
    'L%c1Xm-Y`g35Y4uH{xFiXE2P?*e2m61c`7rYsvT=ff^uxmHo!GfxNgA947wNB7m)pZ9q1@1+>DF=TY}~f^*y{Zi$d~Q2)917KG^n'
    '{|{t|mJ)i#%JV!wM@>7NknFETY`UyKsqKz??-(<H@LG6ygmUkWr3KuLWvhpoM)h$4gw1yqxTS<A4w!kJTbQUV;0UyZn_KK~M%)5W'
    'ytGhi$}QmTNDH_3K9*C9sx1KjYm0cAht+wYA1<~)xByDk7*b~(vz#yo;6rZ`LsKgRt%4l_;bO!Ok@(w&^3A3^59;A!RxC;Mq96}%'
    'v;NEJO+=VY$FwVWZq~3~0nTl~^HyXjnzOA2L;~_nq^HPJIh~Uy?g}wm5I&2Zu^vm>1nP<SMBrzQAL|CJAIjJVYU9S6e12nT?6plZ'
    'g5L#an9qH#qfctT=Fy%c9Kf`uGK3&H0r-UHx$-+)C7=#is?P|!v3C4``$T$1){bIs8r6j&Z-Z(Zt0UWE)jJG*kZy0IJt1zS@K-w!'
    '2!_Ma6LATR=n3FFJ_oo^p6EVe_H0DfZD~ipdHvq+fVk-H<`k;CLMO0bk)gA0M-<Fy;nwM#kt1qj&cVoRaV{_tFjqX%iu1v^7lzU?'
    'Pn_RI_>;9UI6qilyPID_{>snuE33|Lk@*p&YJ5Mc@BKv7+qzI$FKzi;vCV4FZLH%qz?1FT21xAO=7!IMCNdA8tFd!w5%@_u(W;jS'
    'TC~jkB6B%_8OHg;7a?*_fNPR|u?mM-58de<$J1vgoa8p039!N3;wfJPxDP{d&CI`?G5_FXfD@pWbb^_13hs_U-OFL=37j0z7M;}z'
    'm%4>SRG1Z9-eWumHuYhDyzUQT4TK>xf6*%UH1Cf+dW(v*3ZP-RpU3VF=I*nJ;~U_XfvOTz5Z(iH9~N9+bsHLw1YR~5(`v|O0o+mC'
    'w-m$P?>X*<8+UahuCX$-M&3=JIjF_6`YU?r4Zg*@rtd)Nh@0hKw(m=AEJG9aiO!v@EU>oZbdUFRc%e0AZV{5U*cNU<JGPaB$0A$}'
    '+)!fd1pmryU`oJUa7|&c3&}o+o#07h-5JO>aCg?h71522d%9v2pp-%3v(JIGjTYntl(|voLGx<J-?I)IaCRFwyPzmR*q*s+)P>i2'
    'YT>I;3Tlx&N}P<L4Pof8w<S+>z%UHsgF3I8_$*+IperwQBk1iYGo=&!>^l|3Eo?xKZ6WN8y3_^n3-r(|?HbEpEdB5~Bb|VK-miFW'
    'Eef|F)j8#0fm^bKfw%rWQgL*kZn*0S7WsfNv-SkIoqNh2_8PE=W4?>9+v(Pnero`q^>0iBZh#6DC**)ny9-<;oWOh{3E+D=VY+E<'
    'LuCq09ql)8Z*$nAj0^YBtumWD&nE6Vo8);m_3)=P0+XKwGq_Ia`n}wdNn)IN(svMlLpbGDGWTdqM609f+kjh5UG|TJ11C)d+|EuR'
    '>VEV;Nw5w}rtUO)5PnSFWjfV7TH_)wPx9a%_=&K~Q=9P62Ddnz+Qcjur9YwS@TWG*LmNTBb$XJ8S*Is?x*znXP0!~Sc04b0`!YR$'
    '(te%Wuha9J_N1wV=l--V+?#xU0{`Cl3D5w!V;N5mPdlZUNmeoA^aF9$h(79ko{UF9lJ4paxZSRZzJ@IiDC5}ClXIl+LwIW!{*W!&'
    'PH+bjf=s++u#AgY?pu;43SH;f2yYIYo5Ckqy%7VkREcyFczN$sD{=?3459AHt~9j4)o5wOWIwM>bnFeeJHTOml`C3|rW4|SLhsa?'
    '*I71hVISWR{YBiG;v@qcd9$#fy~grHe_R1RalH{|l7WLCUI&{e8NSXMJ=~F)v`wuK^F_NLN%}{HwhpZd)V7h`%(HZk)(V_AwgBXz'
    'Bf<&tiM5PaZazV5X)Cwf>*~9HPa*2k)<iw1=H|Hrt)NqcL*MYIX{InQYwjQmdqS>v%#TJQ`OF!?g0b0d7b5tvMsz8KWWl3<e}cc7'
    '6&voQ<|l1BueKxWN^NHU2jnt9+D{}~RaAk|da%5hV;dg%eejOr4Imf{i2uA#M8!Qz%D6{wS#s{5iVukDWl-;9^ag=+m0(=-0%;`4'
    'W~LMK_iQKScdz(=WS@`{!hJXEphOe>LTU7%^VovjaCf#%sc%9GeE?g4=xb-msyV(BiFLP26WH3qA~TKH$00sGX)(Ltk=on(2C#wa'
    'DPo@?`JjkQfF}@l>cyxQCv9kBFBUl@)K{?P0p{)x)n8cB8-N^#a2tGLO&Ru#XApx~-qgk+5gAr}<U&L5p`Q2bv*(Xv+xN%z*RdJq'
    'NPD`xt36F&XiuYHXVS#zX%h80-Sno~FT}ivi$YTlPW&Q{B;FCgeG-1kc;DA!e0Lx&2}xxNpe#FLFxKE~#=dL+BrL;R5}uyyS9<5H'
    'W_|IrUvg59`=8#~|9stlTD9V0FFp<4MB0Tt0Zzu%wTyO7#3rTUN`TebSvQXuWvAVO>(w!rz;9)E9r%r&5lru8NzdBPtw07AT=(|<'
    'CrP1OLsDGWi>-O~VHkS)%(u!-oMeai4?+5K_y_n+pE}KmbUu`@prJ3ia6~i(BaU8x>Mep#0E_s1#b*<@9d!JFmKTJB1o9`@`@(_#'
    'If&h@5uJEuZIZOh1j$&JMRZK25DnV`<71p@ObPgX?tho>Htx-;1bFVXoqioM104hK-8d)MnA45$*?!!DA`pxxk1eg-_eJ=Khn_!q'
    '*GR_a&ApL%%u#$J?f^CWDAbZTg_bv`oDTALF3z~fI-MJPgz`DT>~^-_Jh5>&;u0BacN>RzNReh#=@4Q<<x`X<q~KRaYv0bjyOV{6'
    '<;u11s^7Ca(MjyP%6)udv)lA;vHsjo8e-ZF=yOd+RW525ij6pc+waIXKaLQtBkVZWQ$KQY4ru7fTIuuSw@Z|7yN;T$8FP_*!c5sw'
    'eoytJC5(@&ZLF8)HL|r}&%V#kSALruu*p+T;jt&t@LQD5$ND1MEtMl5vI6no`=c!+JgixJMh*GCbZdJRsap1dtsJP}LD@+l9Of??'
    'c|%VYXAh&A8Kb8716U;1R9k!xG}w+=>g`a?SU>CS*sgPrk8_`_3_16?vp#CJy2!oEsF~ld{Z96w0SC7CHp9?yf%MVG4J-izax){x'
    '`_gBW>yRB1t;Kkd(8An%y6N2->3xP&lqdp1L{)nl`aoLp62Tj6asEX$-%WigP$Nnf7e0~hDd4@}EA*+d>_N)jAaNaYIn7k|a?c>='
    'tKWs3s={lDGxbvK(w2_}+w0gzeB9-`eaKD5Y5l}W1Hr37zK$UYB*Nuxrl(V1p3XU-buqZ3%{PyqF0o_vc?Pnda63g7-b;x*mk0m!'
    'O5P!xjbS_F+-fO$OAON)k~$8<*1r{Xt4Mhcp=o@lCT~8ZwjeCG1iiDryC<B^ej-KmC+f{n@zWp{3di0v?9~w6j!!n()8yPDdTQ^i'
    'P>Ue4d&KY1SH-kgVT9#8!eQ>@yJlj2CfkvGRKqU%7V<q<8e!w%dw`x7q`R?1(cvhS%OOu1;YW&aIp`B$`uj{&7QJft`Gq4vU%}Ju'
    'S=QkJL(&GqSY7)w+*5%7Jo_@<sFrk9Dq;@tEm)RID?Za%io{lFjI5fN`taTU_?@rk*)duseq=v?4|lfe_r8B`>%$uA<0vLS>;bP1'
    ';A(zzpjJlK-Ii%D3vz^csZD)w0AiNGsl6(HvM&lqKqh{UfApm7S!RrVkWbLG>vli%{n_6qlKaMI$CD9&O;mrEY4tD4AJcq3$K}F&'
    '>Z(2j{3pvUkQUNj-vB=kxZpv*f^9Fo%<_rCiy<mRT>7FE@o|(#{Gm92d~}9&*$$jYG<)YhXX^uLZinV>y19w%b9yJz`A(#z#OW?k'
    '``omBdT38~cj!#@4u!`%v@E@q&Y$tfvNfh0)A#Ajjbf{?Jd6^xmF-f16;0yU-T6FNew1A$j90Bt&;lgsfqs#9bwj^2iYG$b%K7}i'
    'dHm8n?dbm9x8BvP$78wwxp($Qy|8&DZ}?wx{DqzTua}em^+)3`)c=}e{Z!*M{O^PBzSq9{UcaM%`sV)EVbXWr?hl*=c~&tO)V)yI'
    'y3lp@c*EU9DQh5|#o3=v{8W7$l!Y|3#K{#9SnYn2y8SlVq3+i))vu%h5xpN-@5Kwy#ZH~bx74H6rnI15r-9=Ox5=jrwM@I}Y$JK%'
    '1I#W!9ze=QNNa^`R-(fdX{_xaTQUEG*(k4^ptIW<^G%VXqASC`6^mZEMEJfj<Ry?(#Ac$LcOD*pYAZ*0CBLhqYov+)5GNe;Bd|+9'
    'F~1X$*bes6q?-i0fL<)9{STW#515EtOp5v5rd3q7&0WH;CnKlGB{f7#mNNFJ@WOZ1VMU($F3MMt44Y%wM=RiR$a_g=(P1g1%=<HI'
    '@kxJC7xl}la`vLBBoDnR=Pj~?6TN>VJI0Cr)efQ3a_INsgMN?K%r*#>GLoxAuXuyV@+Wb;D@FJ<j3B7M$!FC_Sb}x*JqoQ$spO@V'
    '8%dPhrVvkDMDLBBCp%MuB$S5WbL}?@5yv<ey3;H}ArFJn67A|r+5%E*rHHN`XRC1DiSy_%8;2hgd4Twuc8l}zsna_^<qP4=72(8A'
    'Hb>!23ce965^Yh5EU#Bu2-t4bo6_xvtn;*c8~!b`g~!F`@h#}P;n=4PZv*|CILn}YUEo15Nm5Lb$;KmiF%G;)E1G>!ljw(bFaDO9'
    'N9*40>QSWL@C2o?TaH?pPCj=p`dqgMUT=8Tm)hnxd^IojHMV72v_ZqoAnTM_>+rAG5H{JGb~xDOZlme=Sbc;VX;RRt&8Nv+XKLL`'
    'Hi%6I=@sHFKsTsc+R!03Y&Ns+JmO6o(&9zF>^oa~<Us9_1658#?sm$1QC;onM75Xk#pRSIYX`#8GUPnMirH<$<AiN0l{~c4M*fAv'
    '-?4OSh@O7q9U2-(hyJeOZ8_0|q0K92yS(Cmg$VXm5G#nl5n+7Qb->=HP4((=?R;nTTdc-(ufT&P)iC&9i9I#qS>!i$&_Q^|KJmYv'
    '<R}A7N5`rCWPSGqX0Nf0_@vFUx2#7e761&plJ=tz<n8$PZlBs`;I06Vrye3|X^F(KF@@>6*1cP^&;wsIO#8rk#5bhTeP4&Z1?~^='
    'x0&fxtYz+F9&c^e@m9gYXn#8__Xh+6<_dT|j;l%$h?e{()?rcmEUd4>{XdQ0<0vcfw7Zqh0B<&ls2g_x@eObl5xI}vl6--RM&BJP'
    'VFUU%OE@7%@x09nx!4c31Wqmq4nld$_ICN)t^&6#@lVK!QA7lJXCfRg{1wNSH0Gg<;tQ0Wf{af)xv*XzJ@++Y5V`P@rn~Bom19^a'
    '=2Z3z6)(cQk<KHCKQZY%_F;7={*UE%INvwpcsyCq>qURDg>}=YoT?f$95LHIB4BVdBFX%V#uIFd&_C55Sob*#GRG%6jT}&tK>o?Z'
    '593+O$@a6Kv`92Bb>&4lBeRd$&={?ec6QC`V?9~G2mD2ye|$FoVMn{pA5LmLomAUQmy(BP#GCS8AAfmvemws6F#blktznXY`Gn9e'
    'OP;lME4pt}90o=)uHp}Rry&+kzY~ij=Thbf4wPE}Yl-i_+%}>U)i5Vdr+C<tCV4}feXGcYJxDF6MecfK!g`BjYS`cn`xuZ%*t+U-'
    'jG;$PZ?*D-_bkvlx8`=?p*dP)&BK!;YZeHck!RmJ95c1v)0Strj1n`-aV)0a=d!Y2WcP^8?13t9$h+yynMYE1^(S~u33v{cY3Y`K'
    'M5`&#<I~&PM7;fWf}T)Ur;<~lat4L&T^62_*1iqvDSnOI)vmk*M>w(Fs<vsxK{$-Q_HCZ+v?p7;f4)CyzhBz()8pD&;MC>I3AD=z'
    'OtwM0vW$avX61%~B01e(8eOjt{6>7Wm(kDZ{&l|w^>a{<2KuVY2dAe!%5GQ}cxQv#NH#`Yj^AL%CR@EwDfENoJD3MAXC&Lx!|9;k'
    '(yGy0Rp*SDgme-tU+%eBiF2NIWJ@D1_yiq6IKj?8a+E_^2*SkQH+BwFq}@h-g+x87+&T1n1;!k`;8D-Jb?pJ?#1R`3XQiR|VWAYg'
    'Z;i7H!)Bdj&vceVlWUL1J4LP0d7PpY_?AvlZn6&84Z<Q}>w8j95qh#mNuaP6H}2B;MEDjdhdw+3rd23UKkihzXuc=E@cZXa+LufF'
    '?iGG|x|2?E)&Uje$sTsqKCC^E<uW4Po%WDcy5Z83-pqF><#YT8JiWnGs0lc<f%n8urEwlDxMOmYlgg`d`%<@Zsh^YjJ<WGiXL)&g'
    'Oy8bvZd~Q&E~FQ$TbuOwy{}v^)TExMN#pl*dVk?2PqhDTe~<@Z-6i`4mqDp4s&e?(h`+dwvDa<C>K{)0nn03y0(s^E^4{UxqQu=+'
    '=AZUbR`zG<`j&V1>^%Q$F7vNfjuyBM8EXk+tS9Sz;7ngzC(LVA`}JqmbDclXp*pk;k@SpL{o&VyvAt~KdGYwh?!&%RnG;!rqqh@='
    'yTO2|OY0QTTvM3+ckBtH2Y>bii7Ff4;i7?U$fK<WJL9D)k<$*a2c8tgYII3kvUMS61~)xYOh3iHb>0G3whVtW<~nz?Wqli%)&<^U'
    'KkmJ(hWiT_-buCmEQj~#Zq{-!#YlTj5~Hf?9{L-Q#FUE>?-tcJb3c!B&dbA`vE4Cd1p6-W&7B5p-R6in&PbJ}D~p`7U|1zFyHb)d'
    'fqO}ZyrEnftc6VC{nA&H``K-joyyicQBn24VgG2Sc%zXgE9FQOO%nPkN<;y0!61)-d=U&%1dewh%`?#n;R@JuXF>bXL3RL_r`f_B'
    '66@_H(!U-vC%t*(nb?X$_q(9B$*<^B*=Kj=&UJQ_?P8i8$~%^{YPstMa7~#!ZBlZZRm>h0+L5~pQ!Xd*zb4z5_!-FwHG~_<S`amg'
    'f*}mShw(^Z7#B;Z<IyCa2ko&yr{>c^b<^ka&yjV}b!vT$|5&E|04Xl9EJd20$>Ke88}<!eD=^>N?;-ncqFhsSEe3BZVf--h%+38j'
    '!+CXiGM{lJdZX22L>t#x;<;iQ6t?H}h$p-0SOPY(DFw+BN7T8TZRU{fe79fWkVv*6sb+W}1FcsNI;8<}hBN&gIVeP19h9~JRt%g='
    'SJ#%T^cXreIraU>sRFO2x~~&|`Ud~G68{NYrY#TrXW=|^jBQBU9bJ++sWuJe8@km8S+RpVQ?%FyZSTFHv7dUuyE#eov(!L4r>jFh'
    'Rn7?fux^s1PWR?UvIi+(;mF`lU3T#_?vz)vm0;}#@fpYcfiuA!sxbY2f5<95Jh64pI6`OJ-i1Z-OTd`&GlV^pygPJ0jaztx#<+KH'
    '@2&7^l2LrY(r1{VaeLH;oGmY+Z`j>o=Y4eR@G6(q4>a9$ULYFgWXy!~kbmJ=Qxop?)N#(JMw$fD<4hdDm?QB5scxO~?H>5V6HXXL'
    'SAD@XJI+Hh&DHTW_fHn2z}TuMJ3$+U>R$%eRw&~x+b~a1to(SL@IhuS)bI?d=NV*ES(e}QrXoMo^^g*owWxhttbwF?aPlnrveS(P'
    '9<zH>mvG8sLwOBGL@?*^Alpe+ikdij&~ao(pw)!QW8AI7ubz50{T{+RAHCGA&QIcX1Li>hFel0wjUOu#k8#vhEJqUW<&vwx=V+a@'
    '9Ql(h`UOq$@51-zF!GlCVBxk@jrbV1sOefF#mogBMK$2fOqqseNPEaRgb)_SDHHCU-alj_y5<*RyF{LQk=WkUzmL~9S>G(?{AS4~'
    '_$Qe!P85{BnP76Iar73fcHib34wzlN&>wCEYkCn&nZ912$#~L$l)A_H$a{p*pO})OY=DwAQxQn7oCV3Yu53POx+K3TzCkk}>Co6G'
    'r$Z%j6*25RA0iC0b(p4GIPLe-JVUGBv(EXH2Z_AF4!@V`Serz@LF$J4pBZLQ24B6r7496iN-j6sE0jSJUlQ~VC{}g=J<ex;Ch-kH'
    '2&6PCs+ne}<-M%ox@#DDo_yHZVr>1x>W5r9@nbH@x`*_6H{V<T6WJ-DyERL|_gFzDEtW3?Er7gj-I4z#dUTy#U|)W`#STCO_9e-A'
    'u+2CE6_+P9KhE#cTOogpg!vh-{j^>CVL3Jp-4b(7lTHWZ2bMA@^HCs2Zt`o});1^^oPNjFfN#9uok|%mfvZrbf_m7&t04E(*b4#u'
    '+AyYp{@z)RAzr!cLSa(Hg!%@P!5o@T3QII|uSV=A0L5nd0%>;M*YSnf`xiyO$cbAJ#%wGzw{8CF*m!aCS4%s8MYDDDS9|MU1^p`8'
    '>8pC|J0K)}a?Q;I7yaOGe9~S4mNq=UF#IwwA5GdMN0!}n9INw}%wtQOXNImn*Y%hnEf5M1^dFnQNbT{9y$Z$&;&13rU%387&rG$s'
    'j-!Z|$f|+LHs0?-0chYBb;54|Pn)jUX_f@UUwuB9%}eKZ?Guhm`pm1eKnHWpX-4#HmMr|%7WP)aH8#57=;6@TUGt|2mk&H*0rXE='
    'u6Oen)NoMY`0lraHkHCYPh`_1zdE4cfa`=qzxdaCO4@{R+)lL`68+3JdXh<;<JHezO6-@USuU&{wh$1zNdA~S4kfQf!Q7n^DG&cP'
    '6jM()>Fkk9Iq&Ln*zQfnUXzaa*M+Dtd88aH>7>p%N}kssv@z-Tw)@Tv|21cNRv=xKSiy)--#3xN*vg8%5f6*nokX0wTH(a5#ZnyE'
    'hJ12^*W5Sq4cZ33kcb;8YFFOK|CN2;8u?{2SB05(8)X}etbJlXgE~BGw_rw=ReY!QUq*(6xBR<5nEPSQprA3%2yHx@Wu6VJBT5Yw'
    '(G-Q@58=Kb|HCQwgyx4q7$TX@aXcGYN-^&>N1@`e11Zw+A7f=cls}?evhPMznr#ZVM%IoI)+_S!YsV7}#Ll%U?`MwHvo5aK=_||}'
    'i9R=i-v;OW3H$%@ruPr8z?}9E^OgYmz?^ODVXOX`306nZ6BG%EQJnyP3!pQE?1TI-+^_&7(ICo+PoB=>&W_tEcT=^und>9aT!EWb'
    'PuFXHp@%;Ct8>pmy(=Han0mkSzrmT~J=x1%9`obKt@8<}C;HUv1vRRBA)II*_Tg@}QSx&>?89DC&x7=_o!g5>ZF8^CLw+mI#eLk%'
    ')jtnTS7ToC>}Qack?ni(8=UfajWasy?5$?8dGt?be?Y@Lz0{V<0zDhxnNRAE88@RQ!e<NI{F)v#aGbjcI0HaN6jhmGVd*zn_P$DX'
    'd2aoMx8d|FJ>;d3oV`6hi?i$pS{F(t?z#UrSC`N^lZU$IwpCweX_uoP{_M8be<H4d;Z%Ac`pW*Pilx+}{fjeOWYwD-5*f$)h$*;g'
    '0%px#wQrOEYxhiMpLeu`?jXZ{E%+U}y9C#t`J5trM{=Yc;QC{$;?^+W2fcf7KLTZPI(zz}yxk;^NtDRoWCp|(S@9e>oG|A3^gBsA'
    'jW8A;;+3&1^ItpT{S*EPX9xjwU`2Mt6E=kOFe-wn^9u9{sKFe&hgs$P76E($Aa?Ymr+Yxrd&nC$?}2;7oYn#L)K2CrnGImjNI4pw'
    '$7fmO9|zyddVSWI`0<?R$#h03Imy*mq+-Zsfgf)qcy{XdG5-&=|Dg`F5%oIxfC$BId{5v*jleZ<mbdnd{ytoOU++EN)8Lo4>SusV'
    'AbX%$gfN?dZ%uV1lW)efTNWu6|9Xu7XlnJ$%2B<|-wk^s^Z1-a_CUibVodV-TUjUDbc~htXyZ5QzxwaW+O+YT=#%``y`EqwrLb}a'
    '3Ri(645vto<oo%!RrlMKx6j92f7dHs<`~tq__ylIh=0Vi_Ig=+y{x@n)?Vke17{#vF@`iKCog#<M0eCCEm9la4en^EYmu(r47x`h'
    'hTS_b>@G0u9%xs$FDgCu#8RVGu=F}<7@=rub*hI0EVXYVvawZx<2G4{?MdRnJR_d*DMxDVU6+bped1rpPm;t1dhxy})YsCc>KlzS'
    'hpFe*L6+wxwVIspY(-^Xig4RBVxo$CB)ZwSs`q8-TI{f?e1$p8*b-lpqbP3D(CdE5$<SFIUL|h)zQ>cFGs?wlJlTD84@=bRK61Z^'
    'RY}bp<b$UfP-d+|w`>xgIgS=t&wwQ*<ZJu&VZP)!^80kZ`o14&+ULUFHlh%NyNPisY1KH|t?!O_+>8~LrkM}B{YYz_)Y3CQbzPZy'
    'HM4ZCbrV`8o_wQxCL86YlbWB;F~wW?6EM%zM=F_+-v-K$Td$H=R8rv#ud-LQ-y4K~)F&YHi(Jp#e=`!3w*kr9j7q@-e@*vqB`v<#'
    '_E`J9SDU7IevlxLXRumZp>=*XX#A_M7CkW5XZ7Pyrym6Z9^Uf`i2r{7G~t@2k>hz-j`m_D%JxbBEkyv~h!_X{6=!$?3fFVR-N2{D'
    'uizGaHvdPdGw!q_5)$~@WB8{a&(<-muHB(6j84X(&dTEbBgZX^J_-xf)D1ub;a~K2-Aj$#4`~bNv#*iLlJB2(OmTF#UJ>;nNbg=g'
    'OidK-8)^EqW+yNrpND^gs`~pZbb{Y7mn(4|oV!%;`pF)K;}`N^%2qsbdMy>qFGVsc`*Fd#OL7axByg<ql<g<Rp+iBL{muGvdVk%U'
    '_qX&scUpg`^yvDO*6y!C-UOT7X~u@4?~u~%#buS3uKEYP$pGU^_dVQ_MURZ3ah5v?Se);{jvm<?%XB~kiU!wWS=?@+fyuKsz$x=v'
    '0O7Q8A4%RX06&<z2*`zrKHBJFj3DchTwo)t12arUPt|g{#@s@c=Q33}!oNAPpDIvC#}+Q4LRk6efd2yr5mC;--xdB3d>)A57Q_4j'
    'Ahx*10vA{G2E@;NSSI|EXKW`kO{FlDLV($&`xMGuZUvIl5bIL?0?ayaiJ-cRoy8nmg|ch44`kP3$%V3OS&EBdi4R=`Y?A0-Z`Erq'
    'NN)4kv+JDvznf$denbBdUEySmT!V-5u2&PcW!G3Jiv5?`R&+Dr5D$IJIhws2Iwbgd%i}%tg<dZT6TMDPx1wG(N*JF#vK*)uDVWFn'
    'rGb1Shlj*wG?ReTdF7ovNQUKHf&l-RiG6HA>6XtVn*U%ou@a%F^_uxXt+ivcy{_x?{4P81@|KQWD;*V(8?8L`)6?h<Ac<=>0F#bR'
    'pZ40?eiB>d1YLpGi*ev1r+x0vIj22h$Fuy1n1-Kre|k7Go7q-skZ1IhW~XU}0IXn*_F`w0CiAXkkh`g4i>GE%7EBCx7_;}GA5&f^'
    'n+LA$V9zF#m><FaMy?RV`J{$9TF=Cx4T<-s`ph{&sGfAs^u9@*2=WMW=dY>9(=&7rqB!xmu8+Oc6*w=+VMD71(hSea{EYpDC;xrU'
    '7Oa_RSl8jZg^9JB+p(gpFKxSW2pIfM`>b-vUd1MQ0N>AflK>ZStT<OCws-us)+gSd=I6mGfx#Vfejda$D<C06@Hj8HojfmFbL;Z!'
    'v1-;HqQCSv=Jf%F^Ub=(SXa4v%DJ;qp68m7H6w2K+sr?Iz4@bbxzYUT1pM06iidTfztQ~NH`xDcE-IA{30nYuUL`5HMz%iWxnjNC'
    'hpG>MLH@lgk`T{ct0VW^SLfQ}UUFX%W&nElnER@Y$Vbh6wIdIB*f-;^u?piconTRV!`Z6dJHL>HJbdQ-9_vz<k++QD57{q1kcYbU'
    'TJJ>b(;rXakLTaszW<U~^i%V{)U|I^n={tCoM{Y88bb}x2ZZlbvuD849mHK>`E8x&|Nr36ymWrI@Q3(sAMn?9=9I4RXYJR7zcp|B'
    '7sDUdAow8sSsC$f@b@*~4?t!6O7M5Vf2(09vj_Z_zb5=GFU|i;;P1#=`y2dyE%?i_n_nOP7Rg}t0Dtvs!k>F-{$B!r#YjB<-{9}7'
    '@PE9UUmyN_WNp#|{H3qV|E>Sw@VEXA{=Opr_rm#og#SA>&a3*s|Cz7M|CRq(_%nt_{2TmzCH^me3-|*fCACUK|MK8J{B`s%%PaGL'
    'NB_e2<5-Wd*Q1pd^RYCI(p=fQ|4yTdy6Jp*hFU<?vT~whwf$@^7rU_XQ!S1)m#dbxXOe7E(S5boaraUWes{?q;`auFUg`xKSEU+o'
    's`}OQ{ErQN|EJ#667Cyk@sAj7bp(%gC$40Met2#}Pc@EMbIIqJtfgA6S#r3NcG1VYa_=cxvWa5t#T4n-wj-#HH3bt{Gi@@~lgiy@'
    '^VVICoR4jbd8`0!W+?#B7{4ublUh0nt@`-HPfx<0v5@kZgRl21X8#zf!dVRZ_AY(*HYe*FUL(tbt=!&Q$-PH?(RgN~jr<GOYtvZo'
    ')gQMOj)RF_PiE1R!Dl6eK2P@Jqw|U6QR}F}0eX|h<cd`7rSl0ZpHFh!dy=!|^YH-Y%XZou%KZ|&<~L1f|K^(5MNilnv`m@4KQNQ2'
    'e{1pWu}B0zy<MulH4ZDu?78&XfQ8Q&Eg*)^*|x3c+Q4%r>xaZD;pv9jYoTF=!ZzOcV}8?XK=y14J613{#m{S{C7g4~eO%N|$oi<h'
    '%)xcq<hC9;<>4K}^?DoHh?2}KZ^_X&`*CP>(1ohICXFKp<_o}z@grqMM^CDUljf{zn1eU2MO%{(L<txYEdFDFqur*s0=mVNy}ELV'
    '0}>x^SkyM&S<E`qe;M{n;AkEgvB>-u^!q~R626mGEc3w{KFhVen}3$<TNwW~b{}v7#(Qs0E89`M=Xz+YIODjra2BH-y?6Y;j933b'
    'w4Zi}+a^nUvcAVe5nU%6(5h?UyAGg3-vWgwV#T`Hz#i>l+3b-i$=dY!{rc73g>8#g{kqt__U+@=Gs7?!lfSpY-B7dRDK#@^Y6j0S'
    'y@Rt@N_?VdkF<(vBT_a7<Z>`Sj3dnH0B?1ef;+K9{soj52sdDubL1$T@s?`fGqwUBXZ%<tOLm8eP1_$>H02JT!u|DS+z7m_XS-~r'
    'TD?^HqF^Ncu!#dk#4w=_r7LImQG0on)_!+K?>kE0z|O3rPCEImqdyT^hT(3fqtAdmhO}w{vVF%2tI6!J$ll~Oz`9S-jxp=HVaNNr'
    '32KF}(YmBx!q32SEw^Xh<!NBCY&%}dTM#1X2<_8w!T7#Lth;NJLIlUZND`^r6upI!D%+_#5oe<J-CHv)cB$P*L|_WJKiaE(W8aX$'
    'PoaH%+UX#%24pR-FzdM=zbKE@3ios8zeZj<i+JT=L0F+^j#gS5uZQWWMLuqs#{l+3=33I2>j|DU5-gGhHz56-SFkOb^@20Dqu(jW'
    '8$AmNptr(v;C#%v$0we@!rfl%Hu8DXtTxHdfoD?}@e8#(PL`pB{Hw@^D*`=ndXDMPbIj}`*E57nT>B)Gl8-QD{Ko1vBpEpDCn`KV'
    'kqkIK1CdG&=v9FEqj)x6W)R2+$gDtfHu?94o)V<@YkihkDxtt;kd=04e~`4J>74QR*5k5^WHr*ta^h#w_dksKlmG+kx~ZoT<yIh{'
    'S$E2qY{yP8RRa3U5&5(ml<QRZN1XR&wm0q7yaQFD<mv2E_vz&wTSyis@3$vw2N9R0J6zA?75Ze&Esg4ou(M{2J(3EbA0!5a;(r(Q'
    'xz&0J)9(1dD?ymFedc{sjV^(G(&+pko=UNHFSkv+-j0*MQdIxlecNj(v$w~x%(AW{U*xYN-yT_Z;9L6_wBcV6580Ww{0s8O{0lzk'
    'll=|#FG2J#lnw7NpU}UQcl9s(6aC8v&eyzhzR&f~W$6EQ!;%cb<RVtL8~w}rW$?M?_7&{cqy@z2+?D;0o<Q8B1@y6fffvHpfXe?q'
    ';IHNOg8lw|_(T04OE}+J|M$ZDpW??>asGP&W~(xbZ8i2qGP<miIb_>*Y2i*%MlQ;gwZ<);%XgSTgo%*yf5PiI827|awyfi>R(mDR'
    'Zj%}S2stQIOa2+*@0!G~OTMU`I5n7<Sj>5Z9aTY#@&~(ZBi4v`L76V*c<kBki4zY^a|RLhO(AWaC+TM@S}`HEckmhOTj!f{`;>iu'
    'oGilWzEeKxX$J-m0`idPKWX<eL6g&rRlt5H)JL^pIl!mHA+T3=t-Ys;M}3AA6ZOQJ<oBWa@Nvjr&-wpEd50}*jKtbUiGN<MGVQ*u'
    'l0T<J%_}tNe=qz$WpFwuqJ-m0Fb!GZ3^)ui?YQIZlb2oSnRe>lcdpJgM~G+3O)RPyFTGRL^r8Bd4olER@~`*`vi~mM9NBB$Rea;O'
    'rHnVJYL+&)k6BYDX~|=PG7B)+I$O+?ROAiNjOMv7ibBCiNnc!l8*854QaxamcknFMjo(i3f5-tIn3WNv8YfYlj<Z>Xp2c(-bq1*7'
    'kyZv{jw_yg>F;xTVT23cxLxOe^2AS?wPDIUZTftbJ}z_42Wq(>Hd&k1a~!&gKA-(Do7v<+kCKfurALFpE}3<l)}irCw>AIjepAcO'
    '1M6)if&+eOJ_?P%<E#Yxr~nEh0!N^GVlhbzV;zDpJKDkCMeTRU3VBq?p5%hfa7&J_(D`U3si_jN)Sc;>4Q*}jNjlE4Rb#IXF~&F%'
    '%=fi0z1*>MVSbe7@B5rbg|8fIJ4w>(+Hb;tBoXDkt!DbevQK(L_L=nw3`v88NnIuf^wK`&U*R`S&izsU0Xv#N>gH@itEa3?z202E'
    'p;<Nfc!r5r#5Xi~Ol=2G4L{}F6btcScrzQ{Oe5JI+_)h?@HhsRbGXV3nXg=njKNVTQ>310+>TnU(#k^LQ8lY^Ip-9mOq+)C812CA'
    'ARgAtCMZP)u6%mA@xY%@axJm~HOJ%ZK;1_an&Njpk2u|Ix$Aw8_fk(MbJjmew$Na>Zh(GM*Mj^F>k3CsIfl|;SIJ5j8)p@~(xm3s'
    'm0N_`Tb#I=&1nn2YKyb}zV<#`;TE_0vqfm8Rr101oHaGs6QG$`<##J_dgAFx7*EWKbOQiVJQ<J!!{Q9*S?5jX1UGq6z5$qT%+D7G'
    '4c+~$S*45`K*tW5fncLWeo5^nhUdnzL65@+UX-eYx^3V4*Ob`~u*Wpwy25B4Z_^rsWS&*sGUc##rSS8UHaRDkNuRx^x{f@!$AVhR'
    'l~;(>eM!fW>(EdW-YJeU!9CBPLA!(bnHJ5S|G{kWSS3=kKP8SCMY&>2y80E^nz8y+c~3*@dj#iQryW4e{lZ!8;;hj}J$t11!R992'
    '{6!m&p7DY9&tN9to`)MPOq@k7a0Zm5@5m1fQ9bGGlXn!MzR~G6s-u1E6d{QJwvGGIxne3FnoZ(t!w9kUHb2S59<nSe<BFV*z4Nur'
    ';kqybilO`miY#D1X%*2LqOEf^C3r_tXr1!-qTLtald~vH*?fVkaqE!~%P<W#l5ddnllVGk`-Nvgd)7?M7@=Ou*~_9$^_$(rf=1a0'
    '6ltP9w9kdi5vR6DgPzG>q`&kuUy1}g60mB(@oA3KtQKN{ScF!~Utkouj_0o9(cR@f9rWpPMBj&H&TYm0a5VZdV~hCA4x@?b%)K4P'
    'P=w!|t)?HJw0X3}XjGj|AGE~)1||9DVrQ~`6`Mx@lqU1egURc$nzlL3*?gX1cB|368IRV~VZr3vda+<)Wc{K%945w8_-viB37508'
    '{1%3PjPglhS6maXW3Ri|j-TgG(!A8{QPKv*DCv}EnEYA_wu(txVO%c0KUckzN*7Zedd%?A>kYP^@u&a3<lm-@KAQ3RYT<%Cmer-k'
    'tHU{&*yj{0dB=n>o~#>V*d*&iTta#T@y;kjMUFHw)7QO6wdXZg#hD260BM=({IX9&U9}}J3;i3|di{oRbI(#Id46}r;O0`LSo8Om'
    't*T^m+FzB+LeEO!%vSH`6Z?F^GUoF&PlxHSRH~srfDLx8A+1#m0e?*E>)HAW$%EZuK4l!rRK*YIDO>G!Kja{-^}tz*7zfTg`{(mV'
    'M0oPF{_1@OQqLMg%Jf+Lma?pZGfSkjxTEKJdt+8({HOI--^l*~_^S2YE4xD<4ul2DxC{RU491=Zk*N2`XR%d3^A-p25L7#4L%rYR'
    'EwCg2EW#0XqK~*j)a2L)u6bF-W2Ks%As6ef65x<#2`iimFTRfCyvQs@yZ2RNRpi6DHp2w*pDi}E5u!VQ@R$rCbzm*O=S5^>&Plrt'
    'tyYH~zAt{{dV2>_-p+sefzz9-=aL_Q*!_BT@|`N52G2JXZ`d|^qx-*2RVVO<?$i4^b2M^e=Zx`nt{cHKIa1;r=y^F+c|cE<_COh('
    'o^8WzIM|AKGgrY5^IYpR*S&5|ax0*oqBYJ*4ZK^=HpTTlr9JIS)GsJcCuOoxHJrBBwVvudaP6LHm*!f5{mX~i&%CO+uAa7?c6gII'
    'b*H|qx#B6swsXsMsu-eYb6k7sb#p+jX(}m@tS{Ou+7oC-S{;7lI*#r6BdPjiWB3vn(;BUfC6TgL%?3CyMA>`olL-p3>H<|IK!2xG'
    '^#!DHaPRg|H7Ebju@P<9LeDNk(t>0gL#+!9Kz_C$@o0srbzDe+gGPR*r|QrLaJmy04)5*El_O<jJY`PYQ3a8X_ZA(J73!$=$*QA$'
    'TH?FV_aO}(xUT&~_qLj6xeK|Ht#!EzWZKy4sxg*JSk)S-N+6o&HLEMr4=gwk2m@_r45V}B3_>Ke2<Pv~D%V8nE4$R`^C&4B%4@yQ'
    'Tvp0sP5vcqPi$S^u$Y{DLHYAA*T+@U0Gzn&@w#sPW}D3{`lVAlA!V9jNzQH{xwk$SpFH8s+I=LXGF0Ns#AKU<!^l90vEDCxqH(=6'
    'e3J=c7F3+!J8GBab^vQ|zWjuFCIDgj)^Y3n(7H+MzR%P;Q|t0DhwR0IigoSa>pIP3<$nXUDo*uvQe%m+<GR)3^gPS+a(=#O`*?Y-'
    '?d|z_lJ@1&f0FiP>i<-MnBTg~+dRL`mES71s;i|tl`Y5?GLI^`6cg+wK94e<<|R+*k+-nxD%A_J+cxF-7hk6g#W9KxQ6pW-Ue$L%'
    'q~S2$Z!X52DcU8r2>I-w_C2xhBF=f+KK*8VQOfo6{sm@=FA5x)vP*sgieNi9GG3@w_i~wO;{>B=t|mX8*W=O4;I5wTe~|x6&)Rk*'
    '&g(V#AD}-7`X6kD?7<Fqi2M&SNH$Ns4-Ra9lySxvdjR_%*mwO8-aOx|`J7%nU-CRa%l$#;OVH_Rxr;nU>@($0{5tUIzHt6m_<RP1'
    '<d;>eR`w;W@goF2gVtw|`IX?$ybph-G5lfPOU(KAVfcHRRbJrFe3}1C&{8;G<UfLbvjl~y`(L5Q&o%yc(>zKOeth5m<(>H7`uX_t'
    '8U7e|03WsOg)O9wv+l1)1(v-m$hS{3s7CVFAHEpAe?+SyYi7FFY1|AyS<#Xa_St8s;f@6lOqK<{tX(akSkQsmWw&lCYv6A6-zToA'
    '7X8W`Td%RyL_5DmQK7;!hgruBWgHE}pCMV?s#dw*+-4VUjlN4^1BUK7{6*9heTo0yE9dv%zZAuPj{L8_$REtqPsPJyj#Pi14|{(B'
    'Cv=AXm;Jxq$^Y@W`96pLxR-K<|I*@?(Y`CXIFX0W5d*G>2M(sy?i$6+(Qjtu*^$&B^@%W|3HU4a(=s*p?9Mp9$-jhUC}59izOhMd'
    'Z<aGNRS`t{f>{emL#z#oS#Cwm!jt!YDn{@1JAgV2FJ3E{*&M4q+V0;am3|9*U|>tiT`#SfM_eU)b8kIK?Y&myq-$~<L!i0IPcj-D'
    '5Iym#>G4z#sVU?DWn4JxVq9d__Z2@VWB&BZ_pIrbs0-TSt@tg}FQb3Ge$V^b&y)U2Gu-asD~<nt{h)BtpA`<77A=BQU=EEcSw)4?'
    'V5Ht(VE?2b77eaLPqo9*LL&MP^!_8LM7;=m92S1YSrkFqmn!x#X+7r!^U*qf9`SkWk{SlX2KGZroPDs@MAnI8{XN^`dK=c0m%9<9'
    'e(aPc6!r~Ri4J$Ojx2~pQ*~}6bL^sVvaCCGsj7^LQK_bOOa6d(8)NIweS*DSQ0GuCn$p+wpYfvqEEnAz%6MB*$&!8ZCk{|8Z}(gv'
    'X2N~Um5X@mk{wsHZ$sNgzAvQJhymlO@L$Vr5IgMTU+5@vF6XJX?_|y`L!W`QXq??f=G-E7K2Mc-kk2H)oPAG`z9X+$Lppw+6;Ge7'
    '<9=ao3<KIWjo`008Db0K3e=8y@uaH&qTJ6pU+v7N%ZTggM4XP;(suHeob;8<Id+}$w!vw%htuFXRK%%X&V*&x2DD}ijpvD8Q*N^P'
    'Tr{Nh3_JHehc+IO>6+vk=Q#HjPy3v88FMOAj^vFp!sB^weE;7*@4f4<Nc*6*vEbZyId}BAid`$~siJZAp-g&O$8bQoLugdhUYSA_'
    'n6i;O0dg<Rf#cKJZ_fqkNxW;3R@D07@z}^K+);hn8$U+$SxiZyf9@*8Hmd7{G?Mi1mh`qwmED*he^Z?_*;S~joMH~aFFo$TqbFFC'
    '2(n9FhZIWp|B!0&k+YL$$r>(RXY%yOy&pgK<Er+vROttEp|8Z}!`-yqk{PukBSyhT-UGBgaa|lAv9z_Ge(ZX4uCj&pi>h(+#4l>Z'
    '_F-JFL(U_pK5TPZXQP%8+S$DWVmY+OM}G;JkL4;(epuj69@|UPb??W<oFqp2p(Y$K1XXS(oQ<06J&Okioc%_r#!+8s`MsfA9mR($'
    'H7rwHjlFod$Q4xj32?Un>@VwWEH=VM-4DqH|LFTc6@%NI4+!EjZbLjSh~B#5gf+9ifd4>$453v4W`xNf#++8IRfP4McyEZ2#2s5W'
    'AN6tZo$0<HXOEWCDRxX)kL#O&cMBi}uo(2@74ztm?E83L=O5tB-6$t2a=v4(h>r^hjD(w3dz}gM<T`$e+Xh4Q(JAV+O1*>FZarOY'
    '^9JyoSciG`eQ_Vo0U&*p@Yu)fg~XXo9=wnQ3)TA3m~cE3SnG!}+{kW^2osd8LJ?mTx9DzvELwb9ulc|M^zv#AXGHCJ!Ko(q-djZA'
    'UZ@3ffxcGtX2~r*N|v)!I>#N`L%w?!cib`O^t6#Ks&ed*f%{Ui(DTuAUSROZR$U$TS;396Z)Z<cqx+WEjeQB4N|1X_M(t$}Hp<e-'
    'H)4xGgSSnqpb*b8*~^K8*eA<HnK=rnNVLtrXPfo|7s=9u?XoRP46{X;J@HMeJ<6HuaZ&X+@xakLr1t&E`b^xi+JwpXN9*x4;yw^N'
    'H~CFD^NZ=fsiqX*YOWatFt(dId=F!^y>9xOe3r&xaa~iC|F_zAw~dub^i7?u*xI+5f47q@o+LEaV?anU+r|j`7P-V)s_sK1cNa4x'
    '8I+w-YXMiMx7kO<pL({^yRG&ad944b{z^zS&)?+nO&N7jP*&*QtW7FX0f}Kp`<`p(7`3a+226F&6ku1Gr&ZYTT#2brTt*o+?)U}-'
    '^4uDCf%8Nht#-=AGXM;yRs*Vi!?j~@mQni*<i%ZUk5u2fWnJnb1Ps(WXKdI_Q6C>R)E)}G3MV^oiOhhaUbpQ7190sQjL)kADW|9%'
    ';;6i@9YTiH7h$DMRLsD==DE_&B)x5umj!zFZM`pgt3DTiiw)<x;CaEi9&$)*$0k+P?;=(xYIv93vKSx7t=Vrt;uRBGpMis1$4miF'
    'qoTHFN4R1Q%K4z4+g9^~^zSR5KKW6B2tUKUGu#^X&nVn4f!j=LpgHjDChk|@$}x&wc_pn-p0CZy_&b`PwtkxNk^4k19)S(h)aH-p'
    'EkT!x8RT5~yhZg%I5?b6c|>!e-#~i*ywPL+$$4iN#(A%v^Bz!c0^f6Gk=A^zoTq5gQp&zNvcLfm->>$!FV&wf>S6rl`tyRm9PjJT'
    'y?N6fXg)a~o41fI8g%mJu(9;LT|8SZZ|W!eFN>dUd40jYewi)j8^bJ~jpO$bQ>P~R2N>$a4~=zDvv!K1j-NMkeGa7V*2>;4J$$zM'
    '-&eK2tNk;H{nLjJ#{Yw8o8Ga1KFw9|b?l!SS^jnGpX9IQ8Gcuj)yo3m_c8y(SApN<%jd7~t5$e{UlZ2hCGyST_pL~(|DNFwMU-y?'
    'e}2vCErIa&SpVm%z@Pi_`9Fcbo<HMn@b^vqKi02cfA9Vu%YZ*Tly47zdtP6#e}9C2FKtzih`+(#H-kU(<>&VV|1|)O0e@We=j+4Y'
    'n%B?gum2GIsYm(W;O`srf1l6a{~`RhmaKLh#DDdh@qb@B|0nRbHI9Y&8~lA^{_iW~@4th;v}HX%#D9<eXJ3o|`_lQ}z~3_{qw2hd'
    'WAX$p3yk~33-}6+&m`v;<3At$&y(c8GhY$@?6>tl2mUX8{`_wI&$05wa;m>T^E35J^M9_(XXn=*^DBDwa@;GQA=P|DFUR)merx>;'
    'weT4AyecVkmZ4dzJ6kx=$^__hzqT2=RN@@kDjD4O+?FO;YEUCzwzYdh?b+t8E1&E`-BMM&<=J%I@kK|Avw?n(i{6+uz7m;9_P#zJ'
    '%+_$#4ZFBXw0m6VQRaMd-uF>XmNj0LS?5)iZOrIoUmL6ZfF(`WB7I!mI5?}-ac=ZI!v>ND`fAe#7F7Hml4l6J+7p*uTP&`(I7hfv'
    'Z4qs6ak71^OV;cVhFb(X?OiEpznvYrfADv3xVJs~n#I~_$NbHu4{2fg{LLw=(Q#;t!!{><oczZYuPt`NErR6g#@+6otW*7Hw!UoS'
    'QMvFrVYVM&%ga&JuLkq8u!R@Dj;McjUcDS957{a`681qzSoGwj%KB}61M-{19DHlh+6F0ZM(R5^&P+kN`GT3Bv+H?R3XiC>nzL{N'
    '0BVLf_!mZeF>mxRKE?BMrnN<Lww3PlwP=17@*Jx`>^8K&vTyFOyib)lddH*>$NmS-b5GfKELA(f*;IRAx@L+H^1IRT1IK$(418A4'
    'loS0C|IPG{|LryV0Qz2FzLgS^QmQBP6{BS+`_az6aO$tt*b0QVdrz9(>*jk}9j~A*{TW8dYlbO$r(DK)=RfR!oXq?F&zJRsoa&Ry'
    ')BeN76|d-zdu8kR_U-Y@L;e7uu)8-6J@d95=^*832QYrzU%$S&zh$psb4ZJLuRUc+O+8wh`BFN;<o2`|E6#;zt)NU>wchqU^3yDg'
    'HCBx>#XcSRp4pHR<)tdUIt=+zbA+n+a5F}do6eQo8&NLKfJeU7NqxM@t|&AGFk$1u5=4>6n#i_G^3fMhYu&3z)Jpqo8fQSe)S!XM'
    '=ikEtnS6uAhZ|7BlyChKKN~vMX-dP-(GSQu9}9gWez@qhw~8k;dij#qE?Oc8^Q2g+<dYHaZuaTbj8_Q@X9#80+yx?QQgnQdsppWv'
    '$V2i~w<9Yo`NDegwkJ-E{i?l05z~#9@5vhu{<y=~<IrcoH%q*+-wuQj>Lf3I(-yq<iM{#A%E}QLR`xZjtyuhJI>w)T`1M~{{Xje<'
    '@*Jsx6l;b8+oO{Kw+n~2aGEE^=g2Rz2L@KqVh@H(tTWs@g4>O<!(FV!G#Bz1#5|3ZjRyd9VXR4&n>Ohc->!zMIZ1XzU!=B99T_nI'
    'K{v_C7SJ~;twh-=b7yabp=eq1wFT#NWQwSX+^X)AHv{?}H)#)}(OuoyLw4DEufzw0EUTP&foO>KhmL)GNW*^#ZS;<0JI+;#`7A>e'
    'tc`RWpupHpQQ`XdL>vS24T0eio$;RJH9*J&sYQH}M_vQ!-%|f`Mx*A%_m8r$tG@?(5>QS!<TD(PYIe>=3l!ZEUf%lXT~efbfplRN'
    'ejrN@1L5iq##@A^TGIFr%CE~<+mWn{*w*P?uT=4iZaG)8cZoAYR^@yom!DrA_R3&VijVG8AR4lv&p5^jz(t|l?+4Wt=4<1u$gu}{'
    'a`V}czfNG9WsQ4lJQUnDW0Ias<eDOOLH$kx3Pa9aM~dk8kJYJmpt1sY+%_DZDAYP(YvCh9Rt_@WVsM~S>(RacBGVM^YqSPzv0(Ja'
    '!27*VfQe`&pDu=hN+0|y-_2)uqjT0+6O~Th(S3=Z)m+&nYtGCSvn7T~6lhQwgduaGKvM{e{Jy+*m-p`S-e2DP@xF1a9B0-QipKNB'
    'JA?PWD6jRU@n4_ff3wzk^45buiy>H}YGWhZD%;K!Eg8z;5)*oJKaIFcoX@5Isy*UPv)hm#JofI*srOC3*x&5Eoqip6y$8b6N;|oC'
    '&)Oll?r-((!|7Lg=$)$gF>LvRd>i+H-D8t`Q<(3PUMNm6V00zkjRU<Z33u@fEYF~=((3%nOPj0_Bb=qw^qV;DDQsNH!fR?KX3l8i'
    'F^T$fs8}?k_E{#`T*B1$D*rI9YCb>ZubIC=T(wVqdE(^9*UzM*@%1`?P5w}J?;I{w{-n849ya20&~w^%sfB4P^9>jkn5yzCBmdds'
    '&h3KX0GqlY8@HXI$1ycKFzSb*M)(XhcTtwN=JabiJEDL1&U02W%6(5LBc;-mGgyp_7NrNuPqI+I6U-{a=s4l@E1e*Qc8~M+wv|Se'
    'I+Cf&`-^_L$>>rE3xfdqDsiWh%YF4MGszh8T|50+M_XLCJk6(HmEiMme2b~VB*)|sL>7Vu#^ePfXKdgMSjAzbON=n&Fax~raODWA'
    '!#@J$->XZfLcB^i<B=Cl-U5{riH`K7Wz?pkn?W4SQ8;^3@|())q4k_goZA<<63Q_y`FuR}(DRIMIS;M_<KRZ#e@~e^;65*s_xXUW'
    '8ydTzcgzYU{tUr%h8&%{WM`(8V?8XxdPCj;dXhOZc9INLbEMjz+&!a<#HV5S0MXT8_;<({6$x}5>6`_;vof{5r&b?(Mmy8GR3K9B'
    'ENz`-UC!*}ITpFjxrxVp8XC70G<KNrLv52R$#pP9-Z5Po!n~od(4_bSbHlLAyVyqvOSIGHem^Do^6$(03*X@`e22U69q!C`5Y4i!'
    '%UX}}bkA!j^0etvmo;6UmM9v|(>iCAyU4$8P+W{+m?|MWO2HTtjGQ@2hF%#Be4Z9Qfi0_agxYt<wk68EMt%)09gni~NnUpg+B#}j'
    '*eiQch~KQ%&J7GZ^H(HYM9nKpk~3xePo87g%4q}}YwmJJraTc2t0uc%JC?k-GBOrth>>+QewN;VBEV63<ociNT~GRZ)=O2nm1f+g'
    '86%JOFk`nSjYZs#YfGMuwk$o5oWIjJ5WcG6d_RYNY3RzA9*=R(ED*X@f&zRc{{Uu;kqqmqi|CP|VG(!&x$MN7^=c-Rqh`biiDq48'
    '*}(b-jk6t^6SV=gDFcVrUMZuJNOY5aJF|pt{YipeGuDpWx}NpW`2P>+Pv`8poXeq#lzwR3kZ4bx_WA*>=$Qk=8|b=}jh0%1f6C-R'
    '`e&nSl&2KV=|`SafQ^G{>WJ($<|LN(W|lX3!ENFNCn@_z#uiPnvz*I=t57<Y2C6&ftqt$y$zYj#yXc8MR|z3(h*}_xyaO4o`5}L&'
    'HJogU6cc}lj=g8Cq^b_6vxub2SqS5BOuA4W()P0tS0PKx&?42)wPT}3k7gV71;fh|maC_%7bE-}o`u0V06qvJ(>IcrDGOKExhT}8'
    'HBZ`Wv26p71x(^zYmw@n%b3ev+s3Cncq`2~D>SvPiSaUWgNX0Ra#Zj@@ONC8i@|juHl~U&kC+a*5a;q8{*J4iG3(%#kdtxD!9>Yh'
    'Gx!3er4JMwc^t<)P7H7HIK^=8gTxZ0-7I3usXCP8h6acuiAbvHocJH){wPPNd1Ai<{wPdwj4Q)q|9wc_^&nAXJ%>Ee%{^O;Gd?te'
    '%x;|78aZl*Dlg1(4L}fVB%FttPB~L=&vJpe58%tiQDvDp&y9ZP^KW~3Z!hoN<-NPS_m}q*Z-eve7V#-pe!c98Z9UiewSLio6`}AC'
    '@-_h&4a=Ol#AO5CqYp8!EMiBSP|4MIME<9m5|@1EV5CJpxA2SRuCTQ`@(j-e&XR*ln7Yqz<KRdiEHWV0Cp}N9b!&A5lCN+UMYE#A'
    'zgOj92fZ6Q5Rot2qg6$8AETd6^G58Xe{6NH_u=ZtTgNF|B#XsMIf7aLAL=qRFlCDDCEF(HCOIbx=Z5Zj?8y4Iy6~QooqnQ-W7LiG'
    'rrX}fj)b`}(wg|;)0mAp9UWyai)du->Kfp<QU_kRr_e6-1Yix~Yl9{$^jN^`9lUpC+axPB-sPK_Tq+Y>W@gvNnQ5h{^Nea66$~&w'
    'GmC!>$7oJ6sNndJN2DxSJaK=WN|>Z$Ccd6!&D4E(dIh{eeL9c9XBmueWRx+yd&2ab=9f%P+leydIofgZn%RbYeTi(}MyBA4Kg|~U'
    '{PRWfoF$(rgL;0<wXQMN@}^gpSW@2Sdu@+#h6pdj;{bIxqZ$vjGqvxQa59{MawmN5=u50sO>jGB4j;EZpK^!?l5@Az=eZvP6M-!5'
    '^Q!mQ2iJsqCdeUZK+fzow|QE!R`{NBo2S6OwoYXF&%m=%?hdDAUAv`HbJ3^XyWG4z?{@80ZMlmSt-Ww=8uIOus@|v&7RzuwZZc%;'
    'j~TLtjp}e>+d@JH{2=8Rz`P}8YU@#l2H1zHbZ&2DOv=t4Q-&<dPl!UJY;1~H*Mio&;tCL7wxdRB)$1N@OJ%v#4vZ0uWS=>RKIN%>'
    'toz7W^U%IwexY;wm2eBkzjl}+seR8eN?SZPmg5DIIP25ky!a1gUMieRimSvV@$XP#JTfEt%_M$;lEY$pyGsT|{4ZKOr?KEEWfn|S'
    '>4~x<8m-I`eU+XBJ>c#3j<T#|syQI<Ij;~Fl^+=zJz5Om)>vNaIa7zFS**$|&ibppu_!#WI<%)N+h+~d62*k;!HnK|<!ZL22>v)#'
    'l0fL3##6iRHf!OizAf=QEQw5h#*`mcsgIwq>P1T+HBkYQ46kCYDC95gFv|sqE9OemT)ws=>J)b}YCp7o=yj4@a*+N>uADSw0(CRL'
    'Ec-&1Ux7GZRRhyu5};9PHexQV;iX`;B4tFekgNW*^V@WKYr1?mGWEo)wPtygM57#;<-VGw&Xs80(XzrGFa4k}--jKUdX$!p3Xsx1'
    'kM^x_d&<~|y4Hxf-<WnRE8{WUGaQv|CWnbs|9Dv)W_t_@3%S$8ee0F>IJ@H)V>6IW3uEew{TMNA>Yf={Y9({FIOO~SX+L7G<10B$'
    'X%Cyo@kn_CRlQZe3=8r`P#qiXY#92Wopb`6la4K@=<#A2RU~n;vu(5&X_#!sQtzf)b0}};qB^h8HEXeJ))M+Rqe&aBLs%8IO<q4I'
    'I{;VDl6PS*MQGlA{D)>*$!XB6o_B=hecW5#9rAecaqxGeh!O2F=Pit5&BRaEwD?H|BE4|;S0g|3k~Oy?S1Lf$e1`z}D)byUXpQ3W'
    '=x*$a;NJAaeBz(k^F~lc%G~R*Xil53D9jXqCGudxJcGMee=!s2>^SnlOBOGqxWXum0*NOb6;d>{X%=0r@A(kxl<?HBwW*;DC0g`;'
    'T0MtUzRM9R(ref@J*nDlStCQFW@9ue1tYYZ8QPC!(q9djFrw>`(XZJQQA3A$Jbeu->lZht{lK{*onLS2Mk6OA{H7;sBVehXRdIN+'
    'gzia=KJQ1@8O>J1$yTQREaGLIx|g-qH)bk(ZiD?weZh@9yfUQ+yzq|Bb_v;IeZ2`Ha-*HpQ>Akk9`Fnw{NACDFx8$RAMKt~=I(6I'
    'Z8eY8bV9iHY%gESnF9=aK7};*belockXB3E32rQuUJKY`kWkX1Sk1Gq`N3H(sm2o7&buw4b<3#9nJ9F(-1!W$P44*ojp|60M{4-<'
    'YxD+YSt?m$S(wLdq^nE}ujK4#nVumpPFZPb-6=AD>a$d<t-zG;7B;ru3XVk#T#mj1#Ax$9P+r+l&QO$KuzsR&;pzcPR*%dz>SGo9'
    'yHh3MGkpV!|B&BS??>76yQNOnri*_O@AqD!ax&ds4$pdJ>5tia@AaGe(2Z2fIiL@zLZ3$UOwYN^x`v|fH9<-2`m&{SZxq3U)k2ZI'
    'pei<WA3gc(g=UmqkTn5F9%)Dy(JTb<;Iggj0Pgg+QjKhix;eN;Shr@K;&+e>ZK{{*`iMf6f!n##n_?l4v@4%&Q1+r76g_-Key?->'
    'U8mPIc<N&tR9DD3nW9zyCImuc04P@_?g-E-N9#GQ@*0)IdnMf0RJpF6)^piQ!jH&3r><)*DyLb~t7QNWp>{ToRRHv%nb|53#>tEB'
    '^YM$X`_BO?0Z4&AE*$Xx$$zf8PVtFtR2)whsW7tde^uW)8ac(&$YCCNNvDx_>1{jtHo41K@A%#MZI&ARavEJ{MrY<kDmk5&%!cAO'
    'J|9108KVhikB9P~H2QvuZlU@lr_nzYHS#zrRv{;h+stXS(^{*$AMJ%0A@V2ZwGwvbwIX?*M&C|rO@1C-y#ZnL&wB%Utjk8DuiKFJ'
    '(4VE-xv6GD8Bpfcsh0gOoq9vQ1!bpd4QZ;@(BXR*-%%ry!AT>a6uqexY(zYCn<?AvQOm0M@tk!XaZcJq5k6}Me4cv;sM7C?PzQwc'
    'gQ7DI(b_>z%2l1}2%FP9#cnZIu~hFx>-rqYF6)KgPcEgo$6(HLJC>xiBUzhi=7_&oPT%J1Y;^R^_g>JavqyY%io)77uhhhm{il$w'
    'QD;iO@gwm?l2nr<(~@{eb{&3?`L&14FjHb*RNmKJy0wqKO_`XMzeAbG*SuY|Lh-yuAEv?H=??lHRWs-<VUPL<AKeOb8V&n1>$yK`'
    'Mt`J3jH|!t?*h4dN?h?^`gYP_rBP3lyp3aOC+pP(*5G{ZdLy`tPwigB$@=%^Va%xPog!v)^%Xt-;NNcIVc=;3F*Zd^<lg<*(8r8C'
    '&EViso5x<nJJpQf8Yk*Gy6}AIR}eo^Oz*y3p>Bu9hvw1U(BExfWOq;%#>jBC*WIdK6tOwh@a`T~B!L5FUCIA}@}~Q;rQ~)yM-?$P'
    'hPGCG-aKj(9m#&^g+aFsr6`nb=+91kI|x!XSdgp$L6@DSXx3e|BVnW?>@L@aQ2#cx8LXZ)1}GoY<K)%0_mQZkvD|WtVsj(S^`en$'
    'mL)~<F0-|CPcs}lkNKiU-D58yj$U*<tSeIabDuE``8-p9ge6GI?=hR6BaL01c!7LcGu!Q*j+xaKO_-eY&TxbiFTb;eIZS?y@{OPD'
    'lR+$iQzg$WbUhr^#Wm-zN1o<1tb$qlQEhnDf}W=LbD2fx-oU9_Ec5iuT<uq-j=rym;90MNI>jE-mqh0bqhCgQ+?^eW-CZA1?aXD?'
    '^p{Dy``A-l?t1dE&*rj+;XIpeH}LMRA8W5Oy8HS%OLVBZ>rEpEPQ96PZ{eo5JxKN5Q*X_4Z{#C{Q5WdHGI40+{frs<$uc|Z$W{9g'
    '*>CY;dnSIUc6-WlgvYUgbM8@ITnm@2?d1Cj9IxVOlm$r0X07Ik4WoEIz<dj9G1Qi#T0*LPg1Xj35sqFhK=?gc+^%<&s*7#iVuzPo'
    'bQCV0J^5L>W?uyM+GqX*co>`5M!gcG#LEdYpIy2iUAOeODBqoJJd5s)WOtz0ye4&V$(N6H3BbjdL!P1qJZ#IbJYp6V;T*-gquYx*'
    'U!|N9>%%i;0?Monle+3?UoDEeMEhHJ;awi=vM~?4Y)z@0zKg5t-(Bpp{X5K4QT034x?U<J4NJa}XlS(-PtoD5sUc5+QtN}JkgE3}'
    'bY!K1R3qK4(|jiFf9LQ;FN8c&$bEJ7?6-><H*Ur(H&uFOYqDjX_oWVy*wrx-(pL~ha`GV3-)XVw9%}qHT{hAkdWw}nJ5c8+;C_rc'
    'KuLU<;Y{>?T+d`9_|E6Eter!-ujMqb8^}u@^NY_ts6GtF-?<;=W>ydz2s=~8jJ?sGd#d1VNE5rUrz_xxh~gRPMNSrYV`9-&v&OC0'
    '<K%i>Y`fgsg3e$n)$Qfjj8qM}^zL5h{ea%n?iDlcaGRd=?myo<7BK}@#F?bM17mgHd-#0sH1|Bu9frB@J$}A-H1(rddCVP_a^L&%'
    'YVYI3_5$qbeedao-f`ctEPS6k>{7h#J-^Vqy+ULSPkJw(?;V(X6I{z<?m0f`ef@mzfKY4+#Z6lJ<w@`L^SygpVzkkXopI?&@9p!w'
    'Q;|+HLnKw*xa)oUeDBGEK)BAQ+RBsO_g8vvds)-eds(0Ketf=n!jT|74@|Js``#~z;1f7<zN=)YyX*Z${2p_W`$_ti?Md%1;`f+l'
    'h}?FqFMH|zCHxNkCSdOSzOToV-e17)j0sF0cQu<Qy}yFr?G<LCebW0Y_?>#Uam?MhC%wOd-=X)orZn*cUcGNFy}yLt-MYGEf|(Yc'
    '^!@^V$KKDUTH=%5U%~H(gFiElT$cOZFW~;cySguaongkOC%wOb2^w<dF6Ys^$xnKJ1rzLniWrZb*@}9wTzY>26Tsi@f(h0qy}y77'
    'GUn$C)~WyvoL+s>`-`03dG4V->HP&v;E)$fGtAiSN$)RU0*3dY_1`g1p}Fn-1xx@ivz+IyWhEbae*qI<@8(#ieIK5#=iV>i{$B6x'
    '?4KjOqoU?I>(5~rsUK?1oGoXs{z1-jpX0w|z9cA5^X2CxDVQzwdkcJNE6smi`dnVXNkDKj+9d|ou)EQ!_UGPT!AZ8Zvjn#vnrrUT'
    '`ztufpk{EEKAU;c`wKY9BIurWrr0OFzkrjd?k%3^pkwYy?=Rq_&@#rVOjyJFC%wOblbUI0%bM;rfaHDeuizwtnORQRB+l}o_ZM&y'
    'I-s3t@VY$d{RQsCU~<Ki^a(uNeeW+wpU$>GL8N_WLVnWw3(_Z|kMqvh@}&0{q)%hk7EjXWzM6E~`wP-1+@=f6)cU0N7o<<Tt7l09'
    'O~7}(UoO*!=YHf_`i$F?-e1D+2YSZYNn^1;>HP)#4s*xcL(|-kC;GqiB7UcG#C_klC;Gqi0)7wZVrpHOFu@c3UwR3@H#E#oQh$1)'
    '|4T36ckX?bK7)VK`wRFTdyiO^r*q>rJn8)f{0_Z@0L;yV37+Wx(kuAgpqJ%Lo9Yw&UwQ?<o7B!SR(_)Yb1&T0O!A>IlkPG<>HUSf'
    '8di7OPrwA_N$)S*)qQpKh&GPik0<&+_rhIms7p_F^1W_P^ndP!ySjLkvAo<*;`E;A|J*C`;ZjP$q*5IdEKl@*?uEOGK>_DeC7s<}'
    '?=Rd{;06$q^S}h?+Irjj3wIU4ICpD4VS*?6Klj32T}@s0V|=+|-S7L}U*N?uFudreKYGtk^ndOJUW{ALI}`nr-e2OD<j>Guh9|wh'
    'z%5yWx9P+aJkkI8m-e0I-_d(}rvH0k->tD0)lica<C*^NB_24nV;HCr6Fk%Zy>O~HZ%lYJdZ%3AcfG%4fgxwF31-ZC-}?o<f3Wvs'
    '+16Pa-k#|H;tMbnc0;zciPL+c|BEkK?F?bE0W;}|{x7})Gvo|jCLTEKPkMg^X2RKW4xHZcr1zKPCj0|iI_#P9^@CLQ0?b^MhI?uD'
    'zW4MBp1~-<6Xh%JN$;P7nKp5H!$wk<<)Pmfbc`hE%@noz^`YO-!HMWDTQ<`n?U>7Q>Ng&HULyMnen5YTzDuOPyymR9)qdK&O&+A$'
    'N6Q7BjMe)!*XbAgL8EUQfGtHcdhvCO9P@f^8$A0{g}C3pm2Y=*_g3=9#_jf7@pX;c!?(11o+`k_#_@j82jzIJIFspI{LQ(zy^>!y'
    'er5Vs=AEyO+dVIJJJbIrXIj^ug8<gh%oq>f8qMB8Z!4W=yW9p`T_w2N-Q$~;zS--|8#Ax%O$^~4*NJ(YYu@(9eq}D(;~SpKk#61)'
    'RG#NEFvG)qZuXt$bG3|(`P7?T<N0iNZ)84?HV{6EBG6Ri#+&DI#lzmAPvzPv`_mC*H;V4YbE)fggxI+%?4@=1?K8gV??4OQ0pgS>'
    'd*YY_>On1e)VnDBM;|MPBlJGd*uq)t!)V8qEy(MU^9OH!*LmDX@fgt^Z}(<eb-Y`3?H1E#`<mtCa>oNTzqglpd$(8VE1Qq^sxG=$'
    'yi_iI=&1n8K6DTCEQ*t7WBlnYCd<(|j!HsTj8^jfcz`+|#*6D^yga`R^)#Lt<Bid8vF{Cju}Qu&m+#)eOKG_q@7xb#;A+Od*F61O'
    'RtNNx|BDpO#+7nd+6eQGYp1x4vnK&nOWhmRH})RZniQ#SENx)FZDMBLg60QFQvLv!q~87=V`lUGF6r4MnS;VBaOi%@o+0<)?LJ~X'
    '^^wu@@8}%K1z)|<k56+y1tt4siV_$&>Ww~ZJoS;${x)S5`Vh}EMY2ph4_rl#Wyk-%%jamTD~B^ZKk+u>`I)QX=ghHC@+{$JMtjK`'
    'b>U>*#F6a@SF@gb$j|jw+b7_%`#Rou8<_KmH@?b+qERs$bET-O#PWa0S^*e6$5TX(tX_0goO5C`DN?>E@-4?xDg`qsA62Q2(yJq}'
    '=0f)GM&qbBaCg#jg1k-i9)n}6*A0AOz3VZ0{mgpN<3qok)+;N`?zGYy4PwXk+v7?XKd-dr=k%{C1$kqnH@TJY9)(>6>eu}I)ZQAw'
    '*qPc6erP>Wuzh8XnT$E;;#l7d34U&^JmG3SOyk0p0>4Y$j_Vj5S6*dVdTOt5_r~q~9KCCRU7pdq5P4s|4!v78=41zrSwBD@Ogx<='
    '(1)$f^sat@PVL^WqmODv{+oWj<J=w~t4=({#<}SFe#V`5G|aRI_R54|yP^El9D{v%GN#<0JhX8SZQMf}|Ip@?4Z9M}%cG`+)Cas|'
    'bz{0WD!xdb{E<N?aPEB0k+@@Y5FoYzJG=)6M<Tur3Hfw~^TbOZ@8ORxm8WdG#~)|esIBb9_fZUhQtN<~dpWZ6`t8#9`%>oVET7Fe'
    'nRCA%nM+*8H#h#M=1$_~r&nqF72H#7S)bt^lg7+GfqS0#J9_sy&bCSB(ZSg^J9Ee%<xHLF()&ppx9478p-#U(ppBc`PQ0qQ@Tj+~'
    'ull#k+o69u@jTbHzI_w!_)^m~{trE*cY2VsD$lL>@6EyVIrvY^p$XIt53g1HI$GXJmr4N#R`CI)=g|n1<fC!b`0Mky+vV;#)jSbM'
    'IpI*9$?W4Nz6kd?5-Tx{e6LShnD<)v-Up3tPw(ch?ZelCwNid>o^I6Ct>f3bvdn`tM4V?Cczy0G9@m}D)~@H7_Ub$DetT@37Z;`%'
    'ow=X=<5xEH5n<If&%DRb7pW%ayc4+2F_yNlqs9LRxsm<CjqD%iMuKG5={a=<H*&alxDmZc-A?6=O1kfzAYfKHL8T&BXnlj0m^JwL'
    '2=jZ<+%VU%meir8&i8Pvf}U&p(z-<gpNG@DJ{jYOcyp6}%-qlCtd7B7*MzBAWsdJ)w`GylTzW9x3PrxfITOZ$bCo_?f(_72m-1&>'
    '=;=0|Hn?Br(BBVS4CdyD#tdwj`>z?!;c32mYA<a88!V-380*&iBCaPluMlbBUDm_`@-ehXwYPw;?dj`f^AkLeIUfmgzhT9`fWGcy'
    'rbmv^&)=L+{Y~9p>EE5`31KI5f!Y0mYKk}ZxKHNv4PkUYEFV|6epA|O-cK{@_lGg5dAQ|cR%JJNe5tw6pF<pM;5JsR?K{V6KXO-`'
    'dp@(7o3QS2T=K}DDA&Ub+(%|W`N>YBZOQt((U#-Q(fn(pCGXnZXg<F=T6}FZmu<ZpZPqK@jJCWsT0k$6o6*!v|75iA+Gw%5+jA@a'
    '&C&9QMvD)0YH{&qv>Kn?hxCzg!UN_n#g&^ocfBFrcCGc>^x-T|o;liqkEXkQrdZ`dv8p93wilol>(qaLf9K;N+VzV*_`a>XNRN^D'
    'rFo25LZr7S&$-Yu?b*voYx^B@4k@*rzZ^2t>CZb5a=`;*lzhB7$|t;>DW{fuQ%9sV-u*6ta${8N3Db%TPxC1+U+<qlRv&NO-x=>y'
    '{?;;{dp=%zZ+)NgwvzGu^YQ#U>-$_pPluM+M-pgJkCXS#_gI9d{F?jy#`)I$?eRVr;qm_Y=J(e3DL?Y}&o{iczRyJ?Y-g<B&zEpz'
    'R=(vPBYYxufH=jswZ?sg+vfK3sFxLfDw^X17$Lqh-lul-eTZ4!S>NZPp8xOmp0w9(9LfLkK6?UDyrlh>>2c2lo#_dZ3<lUn!_Yw`'
    'PWxKhFX=bH{`ajSDT<;fTZ&(IPZm}Vi=tFFtBQxj2_E6M;E#>tYijd0`6#}xY4Lm<U&XKBoA>rl-OnX^E#l%THPai#->d7!BP#_M'
    'X`l9a<I?ap8tGe}NrpNp`V?Fm??|iE&G_RJ3O~ag<E?A^x!ywP`aO1L*2wJ2%2}N$wK<WV_|b1am|c7I*ALBEca6F;=FYe~6Yfm9'
    'v&^04?yPWUr8}$KS?$i0J8RlA{XIu>=IA4iKH}&jjy~e(BaS}e=p&9k;^-reKH}&jjy~e(BaS}e=t~`asiQA-^reoz)X|qZ`cg+<'
    '>gY=yeW{}_b@Zi<zSPl|I{H#aU+U<ijy~$>qmDl6=%bE4>gc16KI-VBjy~$>qmDl6=%bE4>gc16KH7}5?bb4{+JEEO|FwJK?RiFf'
    'iN&-S71!s##`-SpH#vH-pLdyI8Lq=mroPi=eP!_Uw6_C#o`xr$&+Ly>w*2PF$U8%msqMyGhaAs)qd~RQtE^T{W_tZ)9?h|`agGYN'
    'k~N@a-usYIj^vEDV)R<w+_$~kdZt58)AC~e8C%P2S3R2;SK2p(2Qe&w=SSRJrQTe7go8oE?ax-!Bk$~7_#)8Q+~`m{<8Qi*&Csg2'
    '?B>1GhLnu?8$aszv{$m`lALijl2*=+%b|29Yrf5Es>Hw@<}Lnc?>#fQXC~iNW}?rSqmMcIn4^z5`k14SIr^BRk2(67qmMcIn4^z5'
    '`k14SIr^BRk2(6dqmMiKxTB9d`naQyJNmezk30IfqmMiKxTB9d`naQyJNmezk30H=qfa>cgriS5`h=rTIQoR6PdNI7qfa>cgriS5'
    '`h=rTIQoR6PdNIdqfa{eq@zzd`lO>zI{KuePdfUfqfa{eq@zzd`lO>zI{KuePg?r?4=&g;3Cd|ura_qnWge78P<Dfrz8B8YZq<n`'
    '=Rvs$%4JZlf^r>{RZwpF<!(sNmIFEDfgJKc4tXGlJdi^k$RU?OIp9AJ_|F6W^ML<6;6D%e&jbGRfd4Law&j5TBH+IW_%8zfi-7+k'
    ';J*m?F9QCHfd3-kzX<p*0{)AD|03YO2>9<_@3iHB|1#je4EQet{>y;>GT^@q_%8$g%Ygqf;J*y`F9ZI|fd4Y!zYO^I=H*N|;J*s^'
    'uLAz7fd4AszY6%T0{*Lj|0>|W3iz)A{;PohD&W5g_^$%~yKbK?2mIFo|8>BB9q?ZV{MP~hb-;fe@Lvb~*8%@^z<(X^UkCix0snQt'
    'f7cDM<$!+`@UH^?RlvUr_*Vh{D&SuQ{HuU}74WYD{#C%g3iww6|0>|W>m=K9z<(3)-vs<O0sl?Fe-rTE1pGGv|4qPu6Y$>z{5Jvr'
    'O~8K>@ZSXdC*4X@Qzk(<4azhqv!Kj_vIxpDC}%-A56VSQE`xFvl<T0Zg0lNgS9EU28+X&6N$Y002D47M#tVC?qE1QV+01)3xr8N6'
    '#_yc7K4Ek&!;Rt3U+1e=7P|LWXziZGUcYS`qhliR`HbstASIPu_1ewX;J$e={`wRZ!lx+mouUCn&poQz*$j``*Y!6{p+kQG-i2Lu'
    'V(*(qN1pzG(W{YnM0g$NHPmZa5clr<wDF~Z9xhm0R+C^B{#x7riV>%IwxKTDMjYM++i0fiMDU9=Umd4af_O9315X--9qPMEiRy5U'
    'd6woY+A$yKs5H9}Lt16t87~w6ouDe~zY|oqZ~a)`R1e=&@4fe<+BeqQcZ!n!8|k5MzOWNjOot<H`=$On!Nb)H-q&)f<d&FF4K$}X'
    '@#eV4G*<>Op_<T2!3TJA-1wgQSWFo5XC-`*Cs9S^-@)-{k*uYq&%F>G_f9?<x0(NMp91S@R~Xc_r3CY+TjZ05^2w$90@7HXQ$DY+'
    'yO<@_g?-y<a)vc0_i4Y`70*=i9&UeC$yeYQjWPo(^JZUe#na`8!P;2hKyNx4<(sH6zB_uuXE043J_E^)8>zeUK4_}<x)_sE|GL%r'
    'Wr(!)d}JK%q}kCC7(*Iv)7yw#xm^W6E_o*HI{BftdbtkhqUd&+eg5p^LO<rhDutjQbDgH~ugK^xO-1&r)Q|_eZJDcK?qi~9I0Js^'
    '-YB-%_Z}kqQka}L3U{yqFo~|*O`_|gljy2bb2VHEcLCdAUGgQ~;&7vq9PEaWMAztDf)J%_u#VXD=fYJUm$-;aG72|NLtH~~Y;leU'
    'YcVg`L-gLk>dFh)M&uBOFvHG<lyUuyC2-Z|H?zOe{tElc?Ju*x)c&USm)KtmPc`;e+27j!R`$2FzlHs^_?5-4EPiG2D~n%Q{L122'
    '7QeFimBn9M{I$hjTl}@fUt9dO#a~<ewZ&gs{I$hjTl}@fUt9dO#a~<enEzE0zedwanBlJTIxmDwt}bl7H&3F=-n@k=2lZ7@U%9Cs'
    '7JXwm_SUfeE|2%taA9a_-x@CMw}o=IBX?=PXVmQoU7D{S*)N)Sd9nM(N%uvP+`P+d-Yzz=CCe1V&8FQ!TEAr+k0ssiUA^x<c;D{('
    'y}iO<Ps>Z5De4^u`(r$p-;RFqXyj@<qC`FaU?-~!{%Y`j^>5O@{?0m%XBcrE$FWWRs?~2N^^xd4!ybN%s5Xvmu=n_-%q1@MID{w{'
    'b96Bxhq&J25aPMz#B9$-a2qKb8z~zbDVyS+DLikcV16r$zq0r%i@&n?D~rFf_$!OQviK{Dzq0r%i@&n?D~rFf_$!OQvYA8{WGXhA'
    '*Lft9(V0sUl&@wo?aa;eOeG64m3)w?<bzD5%Vx+Rn`twZE}KaQ*^Hm5_}?_BsQWJYjrq!8ME?))_j9tN!ETTSTQskj6C374qB+rf'
    'q!%8KWpli0TxL;v=fu7E*awSWjp~9${r#+5EUveB9EoR?aUDl(eU{$lj4;Hn#<_^+y3xFCRu*$R4Kp%`Ipalh+QkUm8Cln0Cp{y{'
    'sO=2)z&2OM#whL?$vq=^o{YqOA>muhNMz9@S27adN(Q+I*A$LLoe_@|^?xJx&gc)vA$)5iA%p$!F2(v8zH-E0&xsDd)yUXbpYi{l'
    'Cmwnd^hC;fqB5B}O4~2jL49p!5$AZKBJf0=2T2AVr1eDI2rU_m(6*ka9(ba9WE3~gR7NwUo~c*#yXH+JvwHEC5uKqLxp&U!+MNEx'
    'j9Ib~Y%}_ovohNmbBOWmdazsRB^qYLoRR1fjRGUH(ot>3M-JnCu=v%%9;fpoTzrl;9$n^)H_XvR6z)hYo6!Ph*+V?rn9=JT>3zrT'
    'AqqDh(`Suw$0a#KZzCL!#c3Ny?_<389@R7Vs2T_V8|+clL|vPc2Cl@QM^*gCtZW+WnR_W>#qW(qmXSyphY<DO@$t+NdgJ#-do%F}'
    'JM_u_sh(}vl5`IvvptOLYkL&^vPwwzHPMMJ)3hM3hmnOX)9X*PJ&Y`DnO=XQ?O|kL%T!6MWn#NhSt3<-y-o5#n>4#~4Wn?Y_n}--'
    '?sh+)y2_@?H7E!5jlbi=M7dXi+^d1y>w(<sf!x(V?rI?SW<>5K$eoo+-rx)4*>K#q40LqCZ_b(Fk7sM~d@l-@Mf)ow-f0eHbNpNU'
    '>YP{;_1$rLM`oSIyy-WSKmKlBw)-aKH|1qHQ#{t%v21rmVBU^jcrDe}irzJ<uVuY!OkWedYg}Jry=$4imiDgcogj(-mP8{oy!QQH'
    'driYjdh`jQul48?QeW%QCp6xqM;~r10oQu;i9%oN(I+&0NuRz7uQlCT2hubZse~SPz?$5zsi{}PdNrb}QBAL=^lA#fMipKS_iLKk'
    't4Vq_s;jBXUQOfG2)_n*1aURQuR$wsYuax(m>o#bmi%w0yD|yNVg1~40FMXtsnvd4Cb#0dk-j!Bb7c{f%Ygo(UvB5HTv-L>reAJd'
    'd0Wmr`tEK0-qxSBtp~RDhnMLy!~15-iEeM*KbO_xj;<x{GgayAA9Dbev$X2%y>vhB$Njh;_v3!tkNa^y?#KPOANS*a+>iTlKkmo<'
    'xF7f9e%z1y@q7m(ob!}5@Q>i~5yqKdImf-x^>;Q|!wAC#B?5k-O!Y<=X(G5xWhxq}_wPv)IL~Eb&IN_5c3+=~&~dp0<GANdjk`gK'
    'Oc0?26ODiapfi9ES0t4Q;>6YOgL?#&E0Mz$A{qQPxTas<Pk}aj1*psQQyglzIRm)3S(W~kdfymP0}SM(krM7fUMb+yo090~GrXpu'
    'a<jb^;Fh{ZrucNDF;K*>?-QCPuIq@<un;ahNu{9|cePPGW9FV5u2TaKFj9b51C9z{Iw%scT8vsg9AOM<w5B|W4N6gK2{@ISN~<+}'
    'j=DoWp$6q_>kO4ZM~UT_1p0UrCpjyf2L4o5_C^<4SF-SR1-3xJGIC8zj<f(2p{1V>Afmic5(uY)=cx~A<lc$*X;~7WAvHW-ysyH0'
    'fmZJ6Dc4t-#)vj5CHJ2JX~J`8!(j20=`GXH`psTpC;?nw%rmSr`$qY#sFf0&!7u07BGKxtrg(R*?VA7>nwqw4qMq8T_L+>@R*dv&'
    '`e_G2+g9G$3GhmsHMaLP5-bz+&vA(+N?6-Pjds+tp~mp<XzAIt<3R$3(!&T8$qZ#3hpqX^wKkZh4=qL@7sf)6DzMka*elwSw#Z6b'
    'B>FJp2Z*sVuddN;wAO9E(LRDmy`NQgPuDWy-ok^%Wu|#Wx^l^!MEZC2WzyOyHSJd4g*+(@jTxv=TS?xw?xd$715s){B4wIN-KM~4'
    'R!H#>y3u1Cwy)_)uysq8#<KDenBhG!omdO75<*=v?M;Yup4Pi3@J78l)PS(kt+j+wz{aqBVw?1Ik++<|ACC5>ImFhWeZ7A#v`309'
    '_=>d&9mncXyQC5+2J6At3TG&7YJ85&wf`d8uV6f}KBS9VahQI+XRVFa5qKq(UCXJKK^n$09mDW`?bm=x*?RuAPCrXMd-Z7=k5!&m'
    '1)ryVT}<ZSC9|G3bfkxSkq-1%7)_~`lku*`&-ht@&>l>-*#kfWPO+t-&TV|ro)JoDzdVdp{YV|&3z-c8Dp_}z)HWI3hrUUBV@qS?'
    'j$TYLQCY{L%47^l(%P+VZ;?3Js}~xQg|1tPUrS7O;PH%@dbxturSY|BKNp^k>BDe>*_qa!vA#;Tb1y^dXGnc-K4{541)2884C95<'
    'na$^1i}LReHA-}})LD;?l_rW0{Pf^C4`%1XJsU`MOUiYf!K|}a%p|(IhL)}+W;E)e_8_|1++@U0+MKcT{95YVNx;i-hj6VX)rbf7'
    'wIYn~9hc&@{srTZ>r(h1G9PIB4O5uMpcS`mBmA<>6?hGhuK*rqR2f`J@ER+1cBHKX=^erx@1f|c=#*$nVFywB!$z{{@Sv|lfIf-('
    'hXjUuu(US=8A3KjaZ3#70gZFXO4CD%<Lh!mpc#8vjqYPfo?EK9_7&J>sG)uIc?mo#hEODCng|CZ3t+WG5lYf!g`@OH{hOdh00v=|'
    'hJ~`Enl>KxECDA$d4ri@9Yh6l7tljksjs0<h`x>#n*6uYEiy-qfD99ww_iZIPLI|!V!(0@b(Mt~%}$3`)7kl!fAlhwUT!-L(j<8k'
    '-M`?5Pe6eZHaw;#&U8AQ4-fxGnZZ?OA7PxE3BPY2cxLtD=#FH`21jb;OYA~j621%-9(oUJyMj6VILnj+H|V}_P`gH!*<Wsdh5eOo'
    '4Q>2*SUj9mbzbjxr-%Rg>8E5d`1AAPr&KP;LO_8fxmbvl=DDsDOjlD1)#*Y&UlD2{tfh-I<wD;A=XeVvi)=w{B}9xgTcFYTw;%{C'
    'O59rkE&_1A$l&iHWl){N<GPwdd|P0$rHjNoD{XBCt~dwKuI^{x?`d1^H=4bN2al_VL-DlP7xkai?tFZDu{U+VMM@Tk@u4XmH|JHg'
    '-){H2hXv&hUHjyV>Tno5wfgTLNxJ&$>wo<D<?Gez#}#?anqs|KzB?0H7N>Q!I-QT}-G|lZwfgd^g3F}(SR7a9W3fJ;URBHG!-C`>'
    'LdH<62=coZBq1+AR}gtYHUugcWCYh?zuy1^BWXf129nYD7S&-rMzAOzkNac69#ymM10=~?Rn-4l@9O;*R_zZ@%k8@}I~|JMEBGy+'
    '&g%6RkU;N-F-%sHoO2=wM=l_)Gq4e#4Mtv&C>!Gxye1s*u2sD{?+^RU{=*Z3#&@k26wT4H2f$@aM29NQ_3?3cUT;;j?!&P-d|X$>'
    '=1&#0i~S~k7f}5}kL=`4@j<;W%8fb^@<oemb=vID%g-;?r(=QC5uPPL9pRl!(p1J|0u^jT<(Fhdk*VWqTO1BxW6RHo5`xu&2#4}A'
    'guJM?>(dDw0*V>m#{f%gg?t4$*?-xAo{FQ|75eEEp3bH|{EIs7)Mj<ugT(a1GM)bL8O0856|`y|W|J}V|9M=ivlf*gC}^5Z6BR!~'
    ')6mw)NP^;>gid~ec8<C+&#|e`eT5eh6kH{S^J)A*nh56pi1vdnaji~9ltfI{LwYK<2UJ9{+1RJS-lsmz_mAhp<9St_&uV)(w*V$<'
    'Qk>5FV@oxiZaorwJWzcG+coqX5a@-c+R&HcmliRfE-rRh{|YAG<Cn;(&lCPm9Y3!t^=4C?oBeTXOau)%PoU9)qZ;U4T8}2*Dc#6l'
    '{rGMb11&7*_s3#)I_!_<<&W>^YJhRM%sv;JbzPj*^34yQx249768JrE3vkrC^U63XmPH-avm+(sgW9QMfjN^!9XGXS$ISKzwKM9)'
    '9LV^bP{#H8bl4P6SCRh3-1jy5#ng<X5vTI($UOzq98wt;6Z3N;9VnRQVzLX$Z0=y&GK3QmGs@?t*)t7_xnnvpgb|L>Xazv5=QA)c'
    'cNAn|#y~^?9f;3r1vD6`89xZEacbf~)vpKWg@FG>KWYQ`^th2|CQj#~`o%m8GN1aasEWh+@u*g(3bK~tdT$h$d2tzYwCqJ1$<f~Z'
    '>-~3sdqD-oItdk&dHI`UFK9Heli3TVp8&f`lVN6;y9AUkv2TLraf>(MF_T#$(4if|y+f;eCs#}TpR}qr%>tcJE2K@a`|t?)Z=@gf'
    'Ve@qOxGEtpd4L{d2I&OJxHB%t>#BEODkR(hUHtaGv-%Zu4EHIh<rMm)w2LvT;&JtPwI!>R*)*~PYX!I3C973UlKNPDF{m^gj_EiP'
    '^C9ILP^C7T2kgsYB1gIW3X0^Q0szWP0C!o!dH{d929T`8>-A0vwyN#P!-6N7z^;2X7gYWpME)Hxcmi(SIRFF)L3EDMgSedsktFLK'
    'B*G9~{tXOsnhA<_aU00fN9c3uv>ZTkmgkEs5x0Qk_4;_$z_8PnrpYb9(&CJe5<)>Kw*bnk$KwfnwuJ|h<2UI-;2_6Z1EZ8L@|%bw'
    'X#<))eOw)i^-jZtoEUuSZ7{WFOX%O#ss`T)HqAkZ^d_L><GO~vik2nN$<Uz*G8bgm;*RPQL@{h2smK;A|7u9mcEk`ACDI>6`6~4m'
    '2S^WUWKpNdx9NgIls_S9jHVFP$Zf`Ank;sIo=~k26u}E*H#H6o@uS)tfJQ+vOU69xCPUF6A;CC5qW{BA8l>O3d<K(#-2JlKf7t=l'
    'j1va1Z{nR$>j6LMbPAy6Nsi-y=}oj6k*Z(OMTjINIYdrJr^#7X78Z0D9x;IBLZH9=`o?6Oh=!B_@kHL#*0ZC6RAy)F7P1FOFp`n<'
    'Hl;&odMFrk<CJpD*do1KlZ?slkHuD%k4>YFZ&kHF*8ET$PionYn*MNQ*!0uGf>I{aMK01n!bjC?K&`8jj+lZ_a5CHr!T~AS>pigW'
    '^02O6wnKV(@p%5YKf?3Nw?F*&E?H&o+cDLt^ld+FKYjYN-2#~@$9_@n3<0sO?9liMhay0E4AZM11lyrkC)~p$m{m$}_8{e+mRnFd'
    '^V9yzOfg`_oWvBDyfu(t7f<`g^PA(oS#Q*<*V}Zt<hmQXM6yLL7Lqs@xK-Qj{<Fe_7K~y{nBLefr4ZPT&{yfq1jn7Aeg*0Dr#%F{'
    '<#wwjgp<$<ntQ0K111y6A|Eq80@4|p^KxtS#s3Vd!M-KfAq1;T%Xe&?h5fTQp0S^heJqakm*S|>SNr8_ghR;p>t_G{xc=}#9hcCh'
    'hi)%Bs!CyUuZ{p^We0Gx-uPsHz?*%)K5h~2TS)%ZDZ|7IMYKfbNt)qYkMu=4K3*<9tK+(P>NpQLexnO9o3>SH;<db&-WWE;&D6oL'
    '$e3>B--=zmZyIYNlN$o+5xXZzKGxZGt!usyAbK2-@I;PTBsY^XFHMU+Kk*$l6VowcUjH|69?e>9YBNxdJ|vS#--ldKlGV|4%`AWX'
    ';h&p-ykCLOSgxwgtG7SAdkG!M@?DOXkWx?z&mwI>KvUTtp9p>P@#%!-fK;3a(LAcdzWTT_vp~JEY3DJ}5Ut11V;Kof4@QK@URH-S'
    '*K-Gxl{0GuUXNOlEWPOekSS=<3631=%rWjyAp!x!ZqoCzvVOA`6;bM6v{Jt_N~My5`Q>!fmFD0jEAY5Se@YKRYo^1=$WvNV?0BjV'
    'lNE*HN9EJh_x05l(n9RZ(a{*r+-Ov@DL$MAzE_|_@gj)UlM811&1O}q59=MOG||Rq_0`kow!k|G2X&{UmrwLmn*UulgufRD>z+R2'
    's09cZ(xRxH=*jGdMbAw7?9o>KE1VJzxO)rXBHs9xs3Gu4dTK3(`G677nkg{k@B_4y!d?-yb2g0b2AOHCQf8nmzqO7CgF(uCTAC~*'
    'Nx+4%EZW4nKx*?+T)cn_3r56kq(DC?2;rYFeZj%1&OP=t4RIbK<>TRO)JS6zcaax|<<`YU>>jrzL|o92)N_A9_B4QvDaD~USC9y&'
    'sf5&1_M**b^XJ+QFh~gk&5F>t3$o*XD?JZ|YLn1g$Vq-hnAXTZm|5a0HO$9i4rGvnlH9xPuWG+lNcpUM6z3(t>)^ZuNg^&JR0G45'
    'a+W8TIH5K^k(zldyfKEIa_Dm4e55D0X8kLUHS08#>jfGzi5q}+Bf3qX6KR*8{QSTF2d~-2iv'
)
CAPTURE_SEPARATE_16_SHA256 = '641e6d9e71659e02f6e6632e0d264e1b402b768667dff922b424acd805032b5e'

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

    def test_closed_libcall_capture_tuple_and_build_applicability(self):
        old = graphical.capture_linked_evidence(decoder, self.linked, self.code, self.payload, self.files)
        new_files = dict(self.files)
        new_files.update({
            "payload.bin": "d266113c87fb779e2876705c3734dd18c3d24ba1ebd4d97527ef276a898aec10",
            "payload.elf": "ee5cb6084521a84cc00c7d513cf23f3b2443ce55e698edfa1ccd1b1314ddf8d1",
            "graphical-console.o": "b40c5548dc03ba52680f850a003253f0acf080704d65a656c75a68c27f38e8f5",
        })
        self.assertEqual(graphical.capture_file_contract(self.files), self.files)
        self.assertEqual(graphical.capture_file_contract(new_files), new_files)
        changed_names = ["payload.bin", "payload.elf", "graphical-console.o"]
        for mask in range(1, 7):
            mixed = dict(self.files)
            for bit, name in enumerate(changed_names):
                if mask & (1 << bit):
                    mixed[name] = new_files[name]
            with self.subTest(mask=mask), self.assertRaises(ValueError):
                graphical.capture_file_contract(mixed)
        for original in (self.files, new_files):
            for name in original:
                for mutate in (lambda value: value.pop(name), lambda value: value.update({name: "0" * 64})):
                    changed = dict(original)
                    mutate(changed)
                    with self.assertRaises(ValueError):
                        graphical.capture_file_contract(changed)
            with self.assertRaises(ValueError):
                graphical.capture_file_contract(dict(original, extra="0" * 64))
        # This synthetic projection is not a newly executed image proof. The
        # real emit/checked path must recompute every stack and capture check.
        projected = deepcopy(old)
        projected["files"] = new_files
        build = {
            "mode": "graphical-console-capture",
            "flags": graphical.expected_flags("graphical-console-capture"),
            "source_sha256": graphical.common.hashes(graphical.source_files()),
            "tools": {},
        }
        # This historical image tuple belongs to the pre-attribute headers.
        # A current build with changed headers must not inherit its applicability.
        current_sources = dict(build["source_sha256"])
        build["source_sha256"].update({'kernel/console-session.hpp': 'a5428035b05b6b44dc449b28c1987e98ea05a02a78094c8851850f24d439b400', 'kernel/display-session.hpp': 'fc415dc9bf56c3c75f379ec89fc0c6216eada3037711179fefa26d0f4971588d'})
        for name, digest in graphical.CAPTURE_LIBCALL_TOOL_SHA256.items():
            target = build if name in ("compiler", "cxx", "pe_linker") else build["tools"]
            target[name] = {"path": "/synthetic/" + name, "sha256": digest}
        graphical.require_capture_linked_proof("graphical-console-capture", old)
        graphical.require_capture_linked_proof("graphical-console-capture", projected, build)
        changed = deepcopy(build)
        changed["source_sha256"] = current_sources
        with self.assertRaises(ValueError):
            graphical.require_capture_linked_proof("graphical-console-capture", projected, changed)
        with self.assertRaises(ValueError):
            graphical.require_capture_linked_proof("graphical-console-capture", projected)
        for name in graphical.CAPTURE_LIBCALL_TOOL_SHA256:
            changed = deepcopy(build)
            target = changed if name in ("compiler", "cxx", "pe_linker") else changed["tools"]
            target[name]["sha256"] = "0" * 64
            with self.subTest(tool=name), self.assertRaises(ValueError):
                graphical.require_capture_linked_proof("graphical-console-capture", projected, changed)
        for mutate in (
            lambda value: value.update(mode="graphical-console"),
            lambda value: value["flags"].remove("-mstringop-strategy=libcall"),
            lambda value: value["source_sha256"].update({"kernel/uefi/graphical-console.cpp": "0" * 64}),
            lambda value: value["source_sha256"].pop("compiler/main.cpp"),
            lambda value: value["source_sha256"].update({"kernel/unreviewed.cpp": "0" * 64}),
        ):
            changed = deepcopy(build)
            mutate(changed)
            with self.assertRaises(ValueError):
                graphical.require_capture_linked_proof("graphical-console-capture", projected, changed)
        # A known new file tuple cannot bless forged capture behavior.
        changed = deepcopy(projected)
        changed["pixel"]["failure_successful_store_ordinals"] = [0, 54]
        with self.assertRaises(ValueError):
            graphical.require_capture_linked_proof("graphical-console-capture", changed, build)

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


class SeparateValidatorCapture(unittest.TestCase):
    def setUp(self):
        raw=zlib.decompress(base64.b85decode(CAPTURE_SEPARATE_14_SNAPSHOT))
        self.assertEqual(graphical.hashlib.sha256(raw).hexdigest(),CAPTURE_SEPARATE_14_SHA256)
        data=json.loads(raw)
        self.linked=SimpleNamespace(symbols=[decoder.Symbol(*r) for r in data['symbols']],
            functions={r[0]:decoder.Symbol(*r) for r in data['functions']},sections=data['sections'])
        self.code={r[0]:decoder.Instruction(*r) for r in data['code']}
        self.payload=bytes.fromhex(data['payload']);self.files=data['files'];self.build=data['build']
        self.no_tools=patch.object(graphical.subprocess,'check_output',side_effect=AssertionError('No external tools'))
        self.no_tools.start();self.addCleanup(self.no_tools.stop)

    def proof(self):
        return graphical.capture_linked_evidence(decoder,self.linked,self.code,self.payload,self.files)

    def test_actual_separate_validator_complete_gcc14(self):
        result=self.proof()
        self.assertEqual(result['variant'],'gcc14-separate-validators')
        self.assertEqual(result['pixel']['failure_successful_store_ordinals'],[0,55])
        self.assertEqual(result['pixel']['mmio_store'],0x3eb0)
        self.assertEqual(result['authority']['record_bytes'],48)
        self.assertEqual(result['selector']['invalid_bytes'],249)
        graphical.require_capture_linked_proof('graphical-console-capture',result,self.build)

    def test_gcc14_meson_compiler_exact_tool_tuple(self):
        result = self.proof()
        build = deepcopy(self.build)
        build['compiler']['sha256'] = graphical.CAPTURE_SEPARATE_MESON_COMPILER_SHA256['14']
        graphical.require_capture_linked_proof('graphical-console-capture', result, build)
        for name in graphical.CAPTURE_SEPARATE_TOOL_SHA256['14']:
            changed = deepcopy(build)
            row = changed[name] if name in ('compiler', 'cxx', 'pe_linker') else changed['tools'][name]
            row['sha256'] = '0' * 64
            with self.subTest(tool=name), self.assertRaises(ValueError):
                graphical.require_capture_linked_proof('graphical-console-capture', result, changed)
        other = '16' if '14' == '14' else '14'
        for compiler in (graphical.CAPTURE_SEPARATE_MESON_COMPILER_SHA256[other],
                         graphical.CAPTURE_SEPARATE_TOOL_SHA256[other]['compiler']):
            changed = deepcopy(build); changed['compiler']['sha256'] = compiler
            with self.subTest(crossed_compiler=compiler), self.assertRaises(ValueError):
                graphical.require_capture_linked_proof('graphical-console-capture', result, changed)
        changed = deepcopy(build); changed['flags'] = []
        with self.assertRaises(ValueError):
            graphical.require_capture_linked_proof('graphical-console-capture', result, changed)
        changed = deepcopy(build); changed['source_sha256']['compiler/main.cpp'] = '0' * 64
        with self.assertRaises(ValueError):
            graphical.require_capture_linked_proof('graphical-console-capture', result, changed)

    def test_separate_capture_rejects_mixed_file_tool_source_and_proof(self):
        result=self.proof()
        for name in self.files:
            changed=dict(self.files);changed[name]=graphical.CAPTURE_LIBCALL_FILE_CONTRACTS[name]
            if changed==self.files:continue
            with self.subTest(file=name),self.assertRaises(ValueError):graphical.capture_file_contract(changed)
        for name in graphical.CAPTURE_SEPARATE_TOOL_SHA256['14']:
            build=deepcopy(self.build);row=build[name] if name in ('compiler','cxx','pe_linker') else build['tools'][name]
            row['sha256']='0'*64
            with self.subTest(tool=name),self.assertRaises(ValueError):
                graphical.require_capture_linked_proof('graphical-console-capture',result,build)
        for path in ('kernel/console-session.hpp','kernel/display-session.hpp','compiler/main.cpp'):
            build=deepcopy(self.build);build['source_sha256'][path]='0'*64
            with self.subTest(source=path),self.assertRaises(ValueError):
                graphical.require_capture_linked_proof('graphical-console-capture',result,build)
        for key in result:
            changed=deepcopy(result);del changed[key]
            with self.subTest(proof=key),self.assertRaises(ValueError):
                graphical.require_capture_linked_proof('graphical-console-capture',changed,self.build)

    def test_separate_capture_original_body_and_state_mutations(self):
        for name,(address,size,count,digest) in graphical.CAPTURE_SEPARATE_MACHINE_CONTRACTS['14'].items():
            code=dict(self.code);r=code[address];code[address]=decoder.Instruction(address,r.size,'nop','')
            with self.subTest(function=name),self.assertRaises(ValueError):
                graphical.capture_linked_evidence(decoder,self.linked,code,self.payload,self.files)
        for name in graphical.CAPTURE_SEPARATE_STATE_CONTRACTS['14']:
            linked=deepcopy(self.linked);linked.symbols=[decoder.Symbol(r.name,r.address+8,r.size,r.section,r.kind) if r.name==name else r for r in linked.symbols]
            with self.subTest(state=name),self.assertRaises(ValueError):
                graphical.capture_linked_evidence(decoder,linked,self.code,self.payload,self.files)

    def test_separate_capture_pixel_dominance_and_error_paths(self):
        fn=graphical.capture_pixel_proof_gcc14
        for at,op,args in ((0x3ca2,'jb','3cc9 <reverse>'),(0x3cad,'jb','3cc9 <reverse>'),
                          (0x3e4b,'jae','3ec0 <reverse>'),(0x3ec9,'jb','3e4d <reverse>'),
                          (0x3d44,'jb','3d75 <reverse>'),(0x3d52,'jb','3d75 <reverse>'),
                          (0x3d7e,'mov','0xb473(%rip),%rax'),(0x3d92,'mov','0xb427(%rip),%rdx'),
                          (0x3da7,'mov','%rdx,0xb412(%rip)'),(0x3dae,'movzbl','0xb413(%rip),%edx'),
                          (0x3ea6,'mov','%rax,0xb34b(%rip)'),(0x3c10,'mov','%rsi,%rbx'),(0x3c13,'mov','%rdi,%rbp'),
                          (0x3c16,'mov','%rsi,%r12'),(0x3d20,'call','39b0 <wrong-helper>'),
                          (0x3c5d,'jbe','3efe <reversed>'),(0x3dfd,'mov','%rbx,%rsi'),
                          (0x3e0e,'movb','$0x1,0xb314(%rip)'),
                          (0x3c3d,'call','39b0 <wrong-kind>'),(0x3db7,'je','3e38 <changed>'),
                          (0x3e40,'jne','3dbe <changed>'),(0x3d99,'cmp','$0x0,%rax'),
                          (0x3dbe,'mov','$0x0,%r12d'),(0x3eb0,'mov','%r13d,(%rbx)'),
                          (0x3c57,'cmp','$0x100,%rax'),(0x3e95,'add','$0x2,%rdx')):
            code=dict(self.code);r=code[at];code[at]=decoder.Instruction(at,r.size,op,args)
            with self.subTest(at=at),self.assertRaises(ValueError):fn(decoder,self.linked,code,self.payload)
        code=dict(self.code);r=code[0x3dd4];code[0x3dd4]=decoder.Instruction(r.address,r.size,'jmp','3eb0 <store>')
        with self.assertRaises(ValueError):fn(decoder,self.linked,code,self.payload)

    def test_separate_capture_console_callee_identity_and_arguments(self):
        fn=graphical.capture_import_proof_gcc14
        for at,op,args in ((0x41e9,'call','1310 <wrong-quiet>'),(0x4302,'call','1310 <wrong-quiet>'),
                          (0x4293,'movb','$0x1,0xaeb7(%rip)'),(0x434a,'jmp','43dd <bypass>'),
                          (0x41e6,'mov','%rsi,%rbx'),(0x42ff,'mov','%rsi,%r12'),
                          (0x4228,'jne','42b7 <reversed>'),(0x4204,'call','3a80 <display>'),(0x4313,'call','3a80 <display>'),
                          (0x4286,'xor','%edx,%edx'),(0x430d,'mov','%rbx,%rsi'),
                          (0x43d5,'mov','%rbp,%rdi'),(0x4445,'xor','%edx,%edx')):
            code=dict(self.code);r=code[at];code[at]=decoder.Instruction(at,r.size,op,args)
            with self.subTest(at=at),self.assertRaises(ValueError):fn(decoder,self.linked,code,self.payload)


# Add this helper and one calling test to the existing registered admission controls.
# It tests constituent reasoning only; the full retained fixture is tested separately.
from types import SimpleNamespace
import dataclasses


def gcc16_inline_constituent_controls(checker, decoder, module):
    fixture = r"""400c|4c8d0d15c70000|lea|0xc715(%rip),%r9
4013|4d8d591f|lea|0x1f(%r9),%r11
4017|660f1f840000000000|nopw|0x0(%rax,%rax,1)
4020|450fb611|movzbl|(%r9),%r10d
4024|be40420f00|mov|$0xf4240,%esi
4029|eb0a|jmp|4035 <_ZN6aurora4uefi12_GLOBAL__N_1L4failESt17basic_string_viewIcSt11char_traitsIcEE+0x55>
402b|0f1f440000|nopl|0x0(%rax,%rax,1)
4030|83ee01|sub|$0x1,%esi
4033|742f|je|4064 <_ZN6aurora4uefi12_GLOBAL__N_1L4failESt17basic_string_viewIcSt11char_traitsIcEE+0x84>
4035|bafd030000|mov|$0x3fd,%edx
403a|ec|in|(%dx),%al
403b|89c1|mov|%eax,%ecx
403d|a81e|test|$0x1e,%al
403f|7415|je|4056 <_ZN6aurora4uefi12_GLOBAL__N_1L4failESt17basic_string_viewIcSt11char_traitsIcEE+0x76>
4041|c605e8e1000001|movb|$0x1,0xe1e8(%rip)
4048|b8c3ffffff|mov|$0xffffffc3,%eax
404d|bafa030000|mov|$0x3fa,%edx
4052|ee|out|%al,(%dx)
4053|83e1fe|and|$0xfffffffe,%ecx
4056|83e120|and|$0x20,%ecx
4059|74d5|je|4030 <_ZN6aurora4uefi12_GLOBAL__N_1L4failESt17basic_string_viewIcSt11char_traitsIcEE+0x50>
405b|4489d0|mov|%r10d,%eax
405e|baf8030000|mov|$0x3f8,%edx
4063|ee|out|%al,(%dx)
4064|4983c101|add|$0x1,%r9
4068|4d39d9|cmp|%r11,%r9
406b|75b3|jne|4020 <_ZN6aurora4uefi12_GLOBAL__N_1L4failESt17basic_string_viewIcSt11char_traitsIcEE+0x40>
4135|488d74240c|lea|0xc(%rsp),%rsi
413a|488b0da7e00000|mov|0xe0a7(%rip),%rcx
4141|4531c9|xor|%r9d,%r9d
4144|48c744240c00000000|movq|$0x0,0xc(%rsp)
414d|4989f0|mov|%rsi,%r8
4150|49bacdcccccccccccccc|movabs|$0xcccccccccccccccd,%r10
415a|48c744241400000000|movq|$0x0,0x14(%rsp)
4163|0f1f8000000000|nopl|0x0(%rax)
416a|66662e0f1f840000000000|data16|cs nopw 0x0(%rax,%rax,1)
4175|66662e0f1f840000000000|data16|cs nopw 0x0(%rax,%rax,1)
4180|4889c8|mov|%rcx,%rax
4183|4983c101|add|$0x1,%r9
4187|4983c001|add|$0x1,%r8
418b|49f7e2|mul|%r10
418e|4889c8|mov|%rcx,%rax
4191|48c1ea03|shr|$0x3,%rdx
4195|488d3c92|lea|(%rdx,%rdx,4),%rdi
4199|4801ff|add|%rdi,%rdi
419c|4829f8|sub|%rdi,%rax
419f|83c030|add|$0x30,%eax
41a2|418840ff|mov|%al,-0x1(%r8)
41a6|4889c8|mov|%rcx,%rax
41a9|4889d1|mov|%rdx,%rcx
41ac|4883f809|cmp|$0x9,%rax
41b0|77ce|ja|4180 <_ZN6aurora4uefi12_GLOBAL__N_1L4failESt17basic_string_viewIcSt11char_traitsIcEE+0x1a0>
41b2|4901f1|add|%rsi,%r9
41b5|66662e0f1f840000000000|data16|cs nopw 0x0(%rax,%rax,1)
41c0|450fb659ff|movzbl|-0x1(%r9),%r11d
41c5|bf40420f00|mov|$0xf4240,%edi
41ca|eb09|jmp|41d5 <_ZN6aurora4uefi12_GLOBAL__N_1L4failESt17basic_string_viewIcSt11char_traitsIcEE+0x1f5>
41cc|0f1f4000|nopl|0x0(%rax)
41d0|83ef01|sub|$0x1,%edi
41d3|742f|je|4204 <_ZN6aurora4uefi12_GLOBAL__N_1L4failESt17basic_string_viewIcSt11char_traitsIcEE+0x224>
41d5|bafd030000|mov|$0x3fd,%edx
41da|ec|in|(%dx),%al
41db|89c1|mov|%eax,%ecx
41dd|a81e|test|$0x1e,%al
41df|7415|je|41f6 <_ZN6aurora4uefi12_GLOBAL__N_1L4failESt17basic_string_viewIcSt11char_traitsIcEE+0x216>
41e1|c60548e0000001|movb|$0x1,0xe048(%rip)
41e8|b8c3ffffff|mov|$0xffffffc3,%eax
41ed|bafa030000|mov|$0x3fa,%edx
41f2|ee|out|%al,(%dx)
41f3|83e1fe|and|$0xfffffffe,%ecx
41f6|83e120|and|$0x20,%ecx
41f9|74d5|je|41d0 <_ZN6aurora4uefi12_GLOBAL__N_1L4failESt17basic_string_viewIcSt11char_traitsIcEE+0x1f0>
41fb|4489d8|mov|%r11d,%eax
41fe|baf8030000|mov|$0x3f8,%edx
4203|ee|out|%al,(%dx)
4204|4983e901|sub|$0x1,%r9
4208|4939f1|cmp|%rsi,%r9
420b|75b3|jne|41c0 <_ZN6aurora4uefi12_GLOBAL__N_1L4failESt17basic_string_viewIcSt11char_traitsIcEE+0x1e0>"""
    code = {}
    payload = bytearray(0x12240)
    for line in fixture.splitlines():
        address, raw, operation, operands = line.split("|", 3)
        address = int(address, 16)
        raw = bytes.fromhex(raw)
        code[address] = decoder.Instruction(address, len(raw), operation, operands)
        payload[address:address + len(raw)] = raw
    label = b"AURORA_GRAPHICAL_CONSOLE_FAIL: \0"
    payload[0x10728:0x10728 + len(label)] = label
    linked = SimpleNamespace(sections=[(0, 1, 2, 0x10728, 0, len(label))])
    def proof(changed=None, data=None):
        return module.Proof(checker, decoder, linked, code if changed is None else changed,
                            bytes(payload) if data is None else data)
    def run(which, candidate):
        if which == "uart":
            return candidate.uart(0x4024, ("mov", "%r10d,%eax"))
        if which == "text":
            return candidate.text_loop(0x400c, "AURORA_GRAPHICAL_CONSOLE_FAIL: ")
        return candidate.number_loop(0x413a, 0x121e8, 0x418b,
                                     "%r10", "%r9", "%r8", "%rsi", "%rdi")
    for which in ("uart", "text", "number"):
        run(which, proof())
    mutants = [
        ("uart", 0x4024, "mov", "$0xffffffff,%esi"),
        ("uart", 0x4033, "jne", code[0x4033].args),
        ("uart", 0x4035, "mov", "$0x3f8,%edx"),
        ("uart", 0x403f, "je", "4064 <bypass-error>"),
        ("uart", 0x4048, "mov", "$0x0,%eax"),
        ("uart", 0x405b, "mov", "%r9d,%eax"),
        ("text", 0x4013, "lea", "0x20(%r9),%r11"),
        ("text", 0x4020, "movzbl", "(%rsp),%r10d"),
        ("text", 0x4064, "sub", "$0x1,%r9"),
        ("text", 0x406b, "je", code[0x406b].args),
        ("number", 0x413a, "mov", "0xe09f(%rip),%rcx"),
        ("number", 0x4150, "movabs", "$0xcccccccccccccccc,%r10"),
        ("number", 0x418b, "mul", "%r9"),
        ("number", 0x419f, "add", "$0x31,%eax"),
        ("number", 0x41b0, "jb", code[0x41b0].args),
        ("number", 0x41c0, "movzbl", "(%r9),%r11d"),
        ("number", 0x4204, "add", "$0x1,%r9"),
        ("number", 0x420b, "je", code[0x420b].args),
    ]
    for which, address, operation, operands in mutants:
        changed = dict(code)
        changed[address] = dataclasses.replace(changed[address], op=operation, args=operands)
        try:
            run(which, proof(changed))
        except ValueError:
            continue
        raise AssertionError("accepted GCC16 constituent mutant " + which + " at " + hex(address))
    changed = bytearray(payload)
    changed[0x10728] ^= 1
    try:
        run("text", proof(data=bytes(changed)))
    except ValueError:
        return {"positive": 3, "negative": len(mutants) + 1}
    raise AssertionError("accepted changed GCC16 text bytes")


class SeparateValidatorGcc16Capture(unittest.TestCase):
    def setUp(self):
        raw=zlib.decompress(base64.b85decode(CAPTURE_SEPARATE_16_SNAPSHOT))
        self.assertEqual(graphical.hashlib.sha256(raw).hexdigest(),CAPTURE_SEPARATE_16_SHA256)
        data=json.loads(raw)
        self.linked=SimpleNamespace(symbols=[decoder.Symbol(*r) for r in data['symbols']],
            functions={r[0]:decoder.Symbol(*r) for r in data['functions']},sections=data['sections'])
        self.code={r[0]:decoder.Instruction(*r) for r in data['code']}
        self.payload=bytes.fromhex(data['payload']);self.files=data['files'];self.build=data['build']
        self.module=graphical.capture_gcc16
        self.no_tools=patch.object(graphical.subprocess,'check_output',side_effect=AssertionError('No external tools'))
        self.no_tools.start();self.addCleanup(self.no_tools.stop)

    def proof(self):
        return graphical.capture_linked_evidence(decoder,self.linked,self.code,self.payload,self.files)

    def test_exact_capture_owner_marker_and_file_inventory(self):
        legacy="_ZN6aurora4uefi12_GLOBAL__N_116capture_scenarioE"
        gcc16="_ZN6aurora4uefi12_GLOBAL__N_1L16capture_scenarioE"
        self.assertEqual(set(graphical.capture_files_for_symbols({legacy})),set(graphical.CAPTURE_FILE_CONTRACTS))
        self.assertEqual(set(graphical.capture_files_for_symbols({gcc16})),set(self.module.FILES))
        self.assertIsNone(graphical.capture_files_for_symbols(set()))
        with self.assertRaises(ValueError):graphical.capture_files_for_symbols({legacy,gcc16})

    def test_gcc16_actual_complete_original_capture(self):
        result=self.proof()
        self.assertEqual(result['schema'],'aurora-graphical-capture-linked-gcc16-v1')
        self.assertEqual(len(result['original_bodies']),15)
        self.assertEqual(len(result['original_state']),24)
        self.assertEqual(len(result['files']),7)
        graphical.require_capture_linked_proof('graphical-console-capture',result,self.build)

    def test_gcc16_meson_compiler_exact_tool_tuple(self):
        result = self.proof()
        build = deepcopy(self.build)
        build['compiler']['sha256'] = graphical.CAPTURE_SEPARATE_MESON_COMPILER_SHA256['16']
        graphical.require_capture_linked_proof('graphical-console-capture', result, build)
        for name in graphical.CAPTURE_SEPARATE_TOOL_SHA256['16']:
            changed = deepcopy(build)
            row = changed[name] if name in ('compiler', 'cxx', 'pe_linker') else changed['tools'][name]
            row['sha256'] = '0' * 64
            with self.subTest(tool=name), self.assertRaises(ValueError):
                graphical.require_capture_linked_proof('graphical-console-capture', result, changed)
        other = '16' if '16' == '14' else '14'
        for compiler in (graphical.CAPTURE_SEPARATE_MESON_COMPILER_SHA256[other],
                         graphical.CAPTURE_SEPARATE_TOOL_SHA256[other]['compiler']):
            changed = deepcopy(build); changed['compiler']['sha256'] = compiler
            with self.subTest(crossed_compiler=compiler), self.assertRaises(ValueError):
                graphical.require_capture_linked_proof('graphical-console-capture', result, changed)
        changed = deepcopy(build); changed['flags'] = []
        with self.assertRaises(ValueError):
            graphical.require_capture_linked_proof('graphical-console-capture', result, changed)
        changed = deepcopy(build); changed['source_sha256']['compiler/main.cpp'] = '0' * 64
        with self.assertRaises(ValueError):
            graphical.require_capture_linked_proof('graphical-console-capture', result, changed)

    def test_gcc16_rejects_mixed_files_tools_source_and_proof(self):
        result=self.proof()
        for name in self.files:
            changed=dict(self.files);changed[name]='0'*64
            with self.subTest(file=name),self.assertRaises(ValueError):graphical.capture_file_contract(changed)
            changed=dict(self.files);del changed[name]
            with self.subTest(missing=name),self.assertRaises(ValueError):graphical.capture_file_contract(changed)
        for name in graphical.CAPTURE_SEPARATE_TOOL_SHA256['16']:
            build=deepcopy(self.build);row=build[name] if name in ('compiler','cxx','pe_linker') else build['tools'][name];row['sha256']='0'*64
            with self.subTest(tool=name),self.assertRaises(ValueError):graphical.require_capture_linked_proof('graphical-console-capture',result,build)
        for name in ('kernel/console-session.hpp','kernel/display-session.hpp','compiler/main.cpp'):
            build=deepcopy(self.build);build['source_sha256'][name]='0'*64
            with self.subTest(source=name),self.assertRaises(ValueError):graphical.require_capture_linked_proof('graphical-console-capture',result,build)
        for key in result:
            changed=deepcopy(result);del changed[key]
            with self.subTest(proof=key),self.assertRaises(ValueError):graphical.require_capture_linked_proof('graphical-console-capture',changed,self.build)
        with self.assertRaises(ValueError):graphical.require_capture_linked_proof('graphical-console-capture',result,None)

    def test_gcc16_original_machine_state_and_payload_boundaries(self):
        for name,(address,size,count,digest) in self.module.BODIES.items():
            code=dict(self.code);r=code[address];code[address]=decoder.Instruction(address,r.size,'nop','')
            with self.subTest(body=name),self.assertRaises(ValueError):graphical.capture_linked_evidence(decoder,self.linked,code,self.payload,self.files)
        for name in self.module.STATE:
            linked=deepcopy(self.linked);linked.symbols=[decoder.Symbol(r.name,r.address+8,r.size,r.section,r.kind) if r.name==name else r for r in linked.symbols]
            with self.subTest(state=name),self.assertRaises(ValueError):graphical.capture_linked_evidence(decoder,linked,self.code,self.payload,self.files)
        payload=bytearray(self.payload);payload[0]^=1
        with self.assertRaises(ValueError):graphical.capture_linked_evidence(decoder,self.linked,self.code,bytes(payload),self.files)

    def test_gcc16_inline_uart_text_and_decimal_constituents(self):
        self.assertEqual(gcc16_inline_constituent_controls(graphical,decoder,self.module),{'positive':3,'negative':19})


if __name__ == "__main__":
    unittest.main()
