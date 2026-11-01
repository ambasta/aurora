# Published-IR consumer: framing checkpoint

This standalone Lean project begins consuming the actual version-1
[published listing](../../compiler/IR-PUBLICATION.md). It is **not yet a
complete listing decoder**, a source-to-IR proof, or a kernel safety proof.

The first checkpoint implements two independently specified grammars:

- `AsciiRun`/`Frames`: printable ASCII line payloads with LF terminators,
  consecutive spans covering the entire input byte array. The span list is
  reversed for linear construction; span ends exclude LF.
- `Digits`/`EndRecord`: the exact `ir-end ` tag followed by a nonempty,
  canonical unsigned decimal spelling of a nonnegative i64. No leading zero
  except `0`, sign, overflow, extra space or trailing payload is accepted.
  `EndRecord` describes a payload; framing separately establishes its LF.

The total functions return dependent witnesses of these grammars. Proofs are
constructed in checked definitions and erased during native execution; there
is no separate untrusted AST extractor. The grammar definitions do not invoke
these functions. Exported soundness theorems expose the independently specified
relations, with full-input coverage, ordered spans and exhaustion/oversize
refusal results. Small acceptance/rejection fixtures use kernel reduction, not
`native_decide`. An axiom audit permits only the existing core proof principles
`propext` and `Quot.sound`, not admitted results or execution-backed axioms.

## Exact limitations

Framing allows empty lines, arbitrary printable tags and repeated records.
The probe checks only framing and the final `ir-end` payload. It does **not**
check the header, compare the trailer against actual bodies, reject earlier
trailers, decode other records, establish pool uniqueness, validate CFGs or
select a call closure. Tests deliberately demonstrate acceptance of unknown
and duplicate records by this first-stage scanner. Such input is not thereby
accepted as a version-1 artifact. Later stages must enforce those obligations.

No source bytes or declarations are parsed. Same-typed field-use swaps cannot
be detected by structural typing alone. Publisher fidelity, capture authenticity,
source-to-IR semantics, primitive effects, native ABI, listing-to-object binding,
backend correctness and hardware semantics remain separate obligations.

## Running and resource boundary

Use the official Lean 4.24.0 release already pinned by the repository:

```sh
./verify.sh
.lake/build/bin/publication-probe /path/to/complete-production-listing.ir
```

Default limits are 16 MiB input, 1 MiB per line **including LF**, and 300,000
lines. Decimal parsing inspects at most twenty digits. Natural-number arithmetic
cannot wrap. Every exhausted budget rejects rather than returning a partial
success. The driver reads at most the byte limit plus one sentinel byte before
rejecting an oversized file. These limits intentionally need not accept every
possible valid listing. Input files are never compiled into huge Lean constants.

The production probe scans the complete captured file, not selected snippets.
Its success is a **native execution receipt**, not a kernel proof of acceptance
of those concrete bytes. Generic soundness is kernel-checked; execution additionally
trusts Lean native code generation/runtime, standard byte-array primitives,
file IO, OS and the acquired file's identity. Hashes can record provenance but
cannot establish semantic correspondence. The probe's time/RSS checks feasibility,
not authority correctness or a formal complexity bound.

The configured ceilings are operational checks. No theorem yet bounds the
successful output's line count/length or native running time/space. Termination
and explicit zero-fuel refusal are proved; these are not complexity proofs.
