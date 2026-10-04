# UTF-8 author evidence

The final aggregate recorded eight known successful process exits and unchanged
source hashes in final-acceptance/result.json and inputs.json. Both pins
passed 406 checks in 39 bounded fixtures, exhaustive scalar/short-input loops,
and readonly/storage regressions. Dedicated Makefile target logs are also kept.
Compiler implementation is unchanged from M016; the only existing-file delta is
the compiler Makefile test invocation.

Release compiler: 14cbaa33b69b81240b5828b6893f4c150eeaa9a11d95a83726d32e417c1f8980.
Instrumented compiler: 805567b1cac1e535d0951b4ddbc02b598d9bb546bea718f7afb74d482dab94bf.
The existing M016 instrumented compiler used C++23, -O1 -g, address+undefined
sanitizers, -fno-omit-frame-pointer and -fno-sanitize-recover=all, with
-Wall -Wextra -Wpedantic -Werror. ASAN_OPTIONS disables unsupported leak checking
and enables halt_on_error. New UTF-8 process limits are in each run manifest.
The sanitizer flag removes only the compiler address cap; native limits stay.
Old readonly/storage harness limits are their preexisting limits, not retroactive
applications of the new UTF-8 runner caps. Regular-file limits do not cap pipes.

Earlier normal-1/2/3 author failures are fixture dialect errors, with exact
compiler diagnostics/sources retained. normal-4 passed before a final test-only
cleanup; optimized-1 and final acceptance bind the frozen test hash. The first
readonly/storage logs reached PASS during an exec-service interruption; their
outer shell exit status was lost. Final acceptance reran them and captured exit0.
No historic failed receipt has been relabeled as a pass.

This directory curates text receipts. distribution.json identifies omitted generated artifact classes and their
independent byte-preserving archive, with a full original hash index retained in
the isolated candidate. Original data is preserved. Per-batch JSON receipts are
consolidated into two named JSON files; original bytes remain in the archive.
Independent review is separate; parent main integration acceptance is pending.
