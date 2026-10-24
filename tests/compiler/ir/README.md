# Textual IR cases (.air)

Hand-built `ir::Module` fixtures are data. Each `.air` file holds one or more
cases; `tests/tools/aurora-ir-check` (one driver, built once) runs them and
`tests/tools/air_lit.py` runs every file below one directory in parallel. Each
top-level directory here is one Meson test with the suites of the fixture it
replaced, so `meson test ir-tests` or `--suite core` select as before.
`tests/compiler/ir_api.cpp` keeps the C++ API unit tests (owner moves, views,
metadata writers, emitter reuse) and loads its modules from these files.

## Module text

`compiler/ir_text.{hpp,cpp}` print and read `ir::Module`. The reader checks
syntax only and never validates, so malformed modules can be written down.

```
layout Pair [i64 bool]                 ; classLayouts
fields Pair [(i64 0 1 false) (bool 1 1 false)]  ; type firstLeaf length array [count]
storage Pair [0 8] [0 8] 16 8 16       ; leaves fields size align reserved
carrier Name / descriptor ID SIZE PUBLIC / views [(SCOPE [IDS])] / enum Name CASES
function test
  result i64
  params [i64 (class Pair)]
  frame 16
  receiver Pair true false             ; class mutable constructor [public]
  slot 8 i64                           ; also object, array, span, service,
                                       ; region, bytes, values, scope, roots,
                                       ; firstmut, spanfield
    Constant 42 i64
    MethodCall get_pair 0
    Return
end
```

Instructions are the operation variant's class names; operands follow the field
order of `compiler/ir_instruction_codec.hpp`, and omitted trailing operands keep
their default-constructed values. Types are kind words (`i64`, `u8`, `span`,
`bytes`, `console`, ...) or `(kind name key=value...)` with keys `display`,
`resolved`, `elem`, `len`, `eparam`, `lparam`, `targs`. Names that are not plain
words are quoted with C escapes. Out-of-range enumerators print as integers.

Repetition is input sugar: a list item `x*N` repeats an item, and `{a,s}` inside
it spells `a + s*i` for repetition `i`; lines between `repeat N` and `endrepeat`
expand the same way.

## Cases

```
; CASE: name                  starts a case; the lines before the first CASE are
;                             the file's header module
; BASE: other name            optional: patch against an earlier case
; RUN: verify | emit [local] [referenced] | stack-facts | abi-facts | metadata | metrics [null]
; EXPECT-OK / EXPECT-ERROR: substring of what() / EXPECT-MESSAGE: exact message / EXPECT-CODE: AU0000
; ABI: function|record|enum SYMBOL SOURCE-NAME [MEMBER...]   (declarations for abi-facts)
; CHECK: / CHECK-NEXT: / CHECK-SAME: / CHECK-NOT: / CHECK-DAG: on the RUN output
; CHECK-JSON: dotted.member.path EXACT-VALUE / CHECK-JSON-COUNT: path N
; CHECK-PROBES: N             stack reservation of N bytes on the following lines
```

A case body is either a full module or zero-context unified hunks
(`@@ -a,b +c,d @@`, as `diff -U0` writes them) against its base; `-` lines must
match the base exactly. Several RUN lines may follow one another; expectations
attach to the latest RUN. `metadata` prints the published metadata, retained
bodies, instruction IDs and control flow; `metrics` prints the verifier outcome
and metrics after real ingress, with sentinel inputs (`null` passes none). CHECK
patterns may contain `\n`, and `{{...}}` spans are regular expressions.

`aurora-ir-check --output FILE CASE [DEST]` writes a case's first RUN output, for
the native ABI runners that link emitted assembly against handwritten harnesses.
