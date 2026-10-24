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
; CHECK-JSON-NOT: path VALUE   the member differs from VALUE (e.g. <missing>, null)
; CHECK-JSON-RANGE: path LO..HI  integer member within bounds (LO or HI may be empty)
; CHECK-JSON-ONEOF: path A|B  the member is one of the listed values
; CHECK-JSON-DIFF: A B N / CHECK-JSON-RATIO: A B N   integer members, A - B == N / A == B * N
; CHECK-RUN-EQUAL: N [FROM|TO]  output (or its text from FROM up to the next TO)
;                             identical to this case's earlier RUN N (from 1)
; CHECK-PROBES: [ [[#NAME:]] ] N | LO..HI   page-stepped, probed stack reservation on
;                             the following lines: exactly N bytes, or any total within
;                             the bounds, optionally defining NAME as the total
; CHECK-RANGE: VALUE LO..HI   integer bound, normally over [[#EXPR]] values
```

Pattern variables follow FileCheck and last for the case's RUN lines:
`[[NAME:regex]]` and `[[#NAME:]]` (a decimal integer) define a variable from a
match, `[[NAME]]` matches its text (a backreference inside the defining
pattern) and `[[#EXPR]]` matches the value of an expression over integers and
numeric variables with `+ - * %`, unary minus and parentheses. `[[#EXPR]]` is
also replaced inside `CHECK-JSON*`, `CHECK-RANGE` and `CHECK-PROBES` operands, so
facts can be compared with the emitted code, for example
`CHECK-PROBES: [[#RES:]] 4080..` followed by
`CHECK-JSON: functions.f.local_bytes [[#RES+16]]`.

A case body is either a full module or zero-context unified hunks
(`@@ -a,b +c,d @@`, as `diff -U0` writes them) against its base; `-` lines must
match the base exactly. Several RUN lines may follow one another; expectations
attach to the latest RUN. `metadata` prints the published metadata, retained
bodies, instruction IDs and control flow; `metrics` prints the verifier outcome
and metrics after real ingress, with sentinel inputs (`null` passes none). CHECK
patterns may contain `\n`, and `{{...}}` spans are regular expressions.

Expectations state the property under test, not the current output: a bound,
presence or absence, an unordered set, a relation between two facts or between
facts and the emitted code, equality with another run, or a placeholder for a
register, slot or offset that legitimate code generation may change. Exact
values are kept only where something outside the compiler depends on them:
the hidden-input registers (R10 receiver or result, R11 record, RAX result) and
SysV argument registers that handwritten bridges and harnesses use; record
layouts, copied-record and service-record facts and host-call arity
(`sysv_arguments`, `result_max`) that kernel bridges and the C++ runtime read,
preferably checked through `abi-facts`, `stack-facts` or `metadata` output;
documented verifier limits; and diagnostics. Frame sizes, save slots, scratch
registers, probe totals, instruction IDs and verifier metrics are checked as
bounds, orderings or relations (a save slot lies inside the probed reservation
beyond the declared frame and is the slot read back; `local_bytes` is the probed
reservation plus 16; call-site bytes are 16-byte aligned and cover the packed
record).

`aurora-ir-check --output FILE CASE [DEST]` writes a case's first RUN output, for
the native ABI runners that link emitted assembly against handwritten harnesses.

## Generated programs

The method-span, borrowed-object, logical-span, sector-value and short-circuit
ABI programs are loops over call shapes (about 1.2 MB of module text), so they
are not stored. `abi_programs.py NAME OUT` writes each as one case file; Meson
generates them once per build and passes the file to the directory's test and
to its native ABI runner (`--air`).
