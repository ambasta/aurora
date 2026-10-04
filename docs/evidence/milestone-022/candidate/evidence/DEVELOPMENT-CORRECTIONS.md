# M022 development corrections

1. First library exchange signature used bare injected `array`. The existing
builtin storage reservation rejected this at library/std/array.au line23:
`expected '<' (found 'replacement')`. Source test worker preserved failing
inputs/diagnostics in evidence/method-values-zj5smrfo and its native log.
2. A narrow std::array bare-self exception was briefly implemented and built in
parser/module resolution. Independent reviewer identified the smaller existing
qualified-self spelling `std::array` without template arguments. A successful
control using the pre-exception fatal ASan/UBSan compiler is retained in
qualified-self-control.log/status and tmp/qualified-self.
3. Root selected the existing qualified-self grammar. All parser exceptions were
reverted; parser.hpp is byte-identical to accepted M021. Library exchange uses
std::array parameter/result/local/constructor spellings, bound to the exact
active instantiated class identity by existing resolution. No new grammar is
needed. The temporary exception build receipt is retained as development-only,
not final evidence. Final compiler gates require rebuilt frozen sources.
