# Compiler status and ownership

The repair builds both compiler stages through the source-bootstrap chain. Final
integrated qualification is still pending; prior-source test results do not qualify
this candidate. Further migration and merging remain frozen until the checks pass.

| Component | Current source authority | Remaining work |
|---|---|---|
| Source loading and file I/O | C++ host | Native runtime and source-loading migration |
| Lexing and parsing | Aurora | Complete final-source predecessor/current convergence |
| Resolution and typed lowering | Aurora | Validate final integrated behavior |
| Metadata, callable and frame admission | Aurora with native transport adapter | Finish final-source validation; retain transport bounds |
| Instruction storage and static admission | Aurora with native transport adapter | Validate diagnostic order and the source/native boundary |
| Local initialization facts | Aurora workspace | Validate allocation, error behavior and joins |
| Current values, operand stacks, bounds evidence | C++ verifier | Migration frozen; unmerged draft is not current functionality |
| Ownership, provenance and worklist | C++ verifier | Establish one authority before any further migration |
| Call graph | Aurora | Validate final integrated behavior |
| x86 emission | C++ backend | Aurora-native emission remains incomplete |
| Assembly, linking and hosted runtime | External bootstrap tools/C++ | Native replacements remain incomplete |

## Hosted Aurora parser

Aurora owns the module grammar. The C++ syntax adapter remains for formatting and
tooling; production lowering does not require a second C++ grammar. See
[modules](MODULES.md), [lexing](LEXER.md) and the [source-bootstrap recipe](README.md#source-bootstrap).

### Hosted Aurora expression parser

Expressions, declarations and bodies are part of the same Aurora parser. The
legacy C++ expression parser is retired; final-source convergence remains a required gate.

## Current boundaries

Native adapters still bind storage, convert records and enforce transport bounds.
Those checks do not justify duplicated semantic policy. Static source admission
and dynamic native lifetime/provenance checks have different inputs; remove a
native check only after establishing which authority replaces it.

The verifier protects the backend against malformed internal IR. It is not a
verified compiler or a proof of Rust-equivalent safety. C++ host code, generated
bridges and the emitter remain trusted. Kernel execution also needs its separate
image, stack and authority checks.

## Compile speed

The formerly timing-out XFS input compiled in 12.7 seconds after metadata-name
sharing and lookup simplification, versus 32.8 seconds before them, with identical
assembly. This is one diagnostic input, not a whole-compiler benchmark; the full
XFS test and final integrated suite still determine acceptance.

## Acceptance and next step

Run the original repository check and complete the final-source GCC16
full suite. Then demonstrate a completed migration with a smaller trusted native
implementation and one authority before resuming the series. Generated ABI and
multi-stage convergence checks remain required; no execution waiver applies.

Language contracts: [values](VALUES.md), [ownership](OWNERSHIP.md),
[generics](GENERICS.md), [scalars](SCALARS.md), [services](SERVICES.md),
[stack probes](STACK-GUARDS.md). Project direction: [roadmap](../docs/roadmap.md).
