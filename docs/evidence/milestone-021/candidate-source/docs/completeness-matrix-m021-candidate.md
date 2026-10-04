# M021 candidate completeness update (not adopted)

- Explicit namespace-level function templates: implemented in isolated source;
  bounded one/two Scalar/Value parameters, explicit calls, copied values.
- Reusable factory: `std::make_pair<T,U>` and executable byte-array/source-range
  example use existing class construction/copy semantics.
- Narrow dependent class template-id: bare function parameters or concrete M020
  argument trees; nested dependent expressions and template-body function-template
  calls are rejected. Class-template bodies are unchanged.
- Validation: complete isolated release/fatal host ASan/UBSan compiler gates and
  independent frozen-source review/replay passed; see evidence/VERIFICATION.md.
- Still unavailable: deduction, overloads, generic methods, function capacity
  parameters, recursive generic expansion, general concepts, heap/resource/ref
  generics, a new ABI, complete standard library and self-hosting.
- Mainline/compiler image integration: not performed in this candidate.

On adoption, merge these statuses into the canonical completeness matrix without
copying or replacing its unrelated rows. See compiler/FUNCTION-TEMPLATES.md for
limits, finite phases, authority, and test obligations.
