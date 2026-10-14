# Compiler status and ownership

Source-bootstrap builds are restored. Further migration uses deletion-first steps
with one semantic authority and final-source qualification for each change.

| Component | Current source authority | Remaining work |
|---|---|---|
| Source loading and file I/O | C++ host | Native runtime and source-loading migration |
| Lexing and parsing | Aurora | Complete final-source predecessor/current convergence |
| Resolution and typed lowering | Aurora | Validate final integrated behavior |
| Metadata, callable and frame admission | Aurora with native transport adapter | Finish final-source validation; retain transport bounds |
| Instruction storage and static admission | Aurora with native transport adapter | Validate diagnostic order and the source/native boundary |
| Local initialization facts | Aurora workspace | Validate allocation, error behavior and joins |
| Current values, operand stacks, bounds evidence | C++ verifier | Migration frozen; unmerged draft is not current functionality |
| Ownership, provenance and worklist | C++ verifier; Aurora owns entry-binding uniqueness | Continue deletion-first migration; retain dynamic checks |
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

Metadata and instruction-flow masks share the source-owned `FlagMasks` table.
Its existing generated ABI bridge supplies native readers; structural passes
read the needed `u64` masks once per pass and keep the 32-byte code row unchanged.

Native adapters still bind storage, convert records and enforce transport bounds.
Those checks do not justify duplicated semantic policy. Static source admission
and dynamic native lifetime/provenance checks have different inputs; remove a
native check only after establishing which authority replaces it.

Aurora admits the unique entry-binding prefix; native code constructs its state
and retains dynamic lifetime, initialization and provenance checks.

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

Each deletion-first change requires final-source GCC16 full validation, generated
ABI checks and multi-stage convergence; no execution waiver applies.

Language contracts: [values](VALUES.md), [ownership](OWNERSHIP.md),
[generics](GENERICS.md), [scalars](SCALARS.md), [services](SERVICES.md),
[stack probes](STACK-GUARDS.md). Project direction: [roadmap](../docs/roadmap.md).
