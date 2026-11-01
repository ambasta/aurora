# Published IR records (version 1)

The existing pipeline listing option publishes generic typed records from the
admitted metadata, normalized instruction store and builtin catalogue. It runs
only after verification and graph checking. **Listing replaces emission**: it
is not an object-code certificate or a source-to-IR proof. The ordinary compiler
CLI does not expose this test/tooling option.

The `aurora-published-ir 1 types fields callables operands cfg resources` header
names the represented capabilities. These are not a claim of complete compiler
semantics: reflection descriptors/views, native execution, hardware completion
and the source-to-IR relation are not specified here. A proof consumer must
reject operations or types whose semantics it does not implement.

## Encoding and identities

Records are newline-separated ASCII. Signed integers are decimal i64; unsigned
fields are decimal u64, without a sign. Hex byte strings use two lowercase hex
digits per byte, with an empty suffix for an empty string. They never interpret
names as whitespace-delimited tokens. `ir-name-bytes` contains the complete
metadata byte pool; every name range below is `(begin,count)` into those bytes.
`ir-literal-bytes` similarly contains the instruction literal pool.

Types, classes, enums, callables, slots and operands have zero-based pool IDs.
Instruction IDs are one-based **original row identities**, not body positions;
normalization can leave gaps. `ir-code` positions are zero-based and contiguous
within that published body. Only retained bodies are listed; all callable
signatures remain available. Full operand pools include unused records, which
are not executions. No raw ID is renumbered to conceal a removed instruction.

The older `class`, `callable`, `slot`, `origin`, `body`, `code` and related display
records remain for human inspection and existing fixtures. Their pretty type
spellings are **not** authoritative descriptors. Machine consumers use the
`ir-*` records below; display records cannot override them. Display names escape
control bytes, non-ASCII bytes and backslashes as `\xHH`, so an arbitrary nominal
name cannot inject a new machine-record line.

## Record fields (in order)

- `ir-counts`: metadata-byte count, type count, class count, enum count,
  callable count, slot count, original instruction-pool count, operand count,
  literal-byte count, resource-kind count, catalogue-type count.
- `ir-type`: ID, kind, name begin/count, element kind, array length,
  element-parameter bytes, length-parameter bytes, template-argument count.
  This preserves every `RawTypeRow`/`RawTypeTail` field, including kinds beyond
  the display spelling table. The final three fields are u64.
- `ir-enum`: ID, name begin/count, case count.
- `ir-class`: ID, name begin/count, membership flags (u64), declared leaf-type
  begin/count, canonical field count, canonical leaf-offset count, physical
  size, alignment, reserved bytes. Leaf-type ranges reference the type pool. Publication refuses a class without
  canonical storage rather than emitting negative physical extents.
- `ir-field`: class ID, canonical field ordinal, type ID, first leaf,
  leaf count, array flag, element count, canonical physical byte offset.
  Fields come from `ClassResultRow.fields`, not a reconstructed source layout.
  They preserve declared order when explicit field metadata is admitted; with
  layout-only input the compiler instead synthesizes one field per leaf.
- `ir-leaf-offset`: class ID, leaf ordinal, canonical physical byte offset.
- `ir-callable`: ID, name begin/count, scope, result/formal type begin/count,
  receiver name begin/count, receiver flags (u64), borrowed-root count,
  borrowed-root mutability mask, callable flags (u64), receiver span-field
  summary, frame bytes, slot begin/count. The first type is the result; all
  explicit formals follow in source order, including borrowed roots.
- `ir-slot`: ID, record kind, offset, type ID, length, mutability value.
- `ir-catalog-type`: catalogue ID, metadata value kind, native nominal name
  hex. A kind of -1 means no scalar/class/enum mapping in `catalogue_kind`;
  an empty name is not a fabricated nominal identity. Consumers must reject
  unsupported referenced types, not infer a type from a missing name.
- `ir-resource`: resource kind, catalogue type ID, method count, source type
  name hex. Resource kinds identify the existing sealed resource families.
- `ir-resource-method`: kind, method ID, result catalogue ID, result metadata
  kind, parameter count, uniform parameter catalogue ID and metadata kind,
  effect classification, runtime binding symbol hex. These values come directly
  from `compiler_catalog::resource_method_*` and `resource_runtime_byte`, not a
  second signature table. This is the source/admission signature, **not** the
  native ABI: hidden root/epoch/field/output arguments and native call lowering
  are not serialized here. Zero-parameter operations can have parameter kind -1.
  Effect classifications are the existing admission categories (0 observation,
  1 mutable loan, 2 consuming); they are not proved frame or safety summaries.
- `ir-operand`: ID, role, signed value, unsigned value (u64), slice begin/count.
  All payload fields are preserved, including nested operand slices, type IDs,
  literal slices and name slices. Their interpretation depends on the role.
- `ir-body`: callable ID, normalized instruction count, unreachable-after marker.
- `ir-code`: callable ID, body position, instruction ID, target body position,
  flow flags (u64), record kind, instruction form, unary operation, binary
  operation, comparison operation, metadata query, operand begin/count.
  A target of -1 means no explicit target. Flow flags retain fallthrough and
  leader facts; no instruction is silently omitted from the normalized body.
- `ir-end-body`: callable ID and the repeated normalized count.
- `ir-end`: number of serialized retained bodies; this is the final record.

Kinds, forms, roles and flags use the compiler's existing admitted identities
in `ir_metadata_storage.au`, `ir_instruction_storage.au`, lowering and the
builtin catalogue. Version 1 consumers must explicitly implement the identities
they accept; unfamiliar flag bits are not harmless defaults. Reinterpreting an
existing record, tag or field requires a version change, not merely an appended
capability. Scratch worklist
values and unused code capacity are not semantic records.

## Consumer and proof boundary

No semantic decoder or correspondence checker is introduced by this format.
A later reusable checked decoder must reject unknown versions/capabilities,
duplicate identities, missing rows, count/range errors, malformed hex/integers,
truncated/trailing records, unsupported types and operations, dangling calls,
and CFG facts inconsistent with instruction semantics. It must bind typed
receivers, formal slots and declared field indices, not merely search a listing
for a familiar name. Display text is not a fallback when a canonical record is
missing. Direct IR fixtures test actual serializer output, not that future proof.

Source file bytes, module paths, compiler/tool identities and options belong in
a separate capture manifest. Exact bytes and hashes establish provenance, not
semantic correspondence. Field names are not stored in `FieldRow`: a future
source checker must parse the complete relevant declaration context and check
name-to-field-to-leaf/layout correspondence, including same-typed fields.
Serializer fidelity to the canonical stores, compiler semantic adequacy and
external primitive behavior remain separate obligations. No field, catalogue
entry or emitted record certifies that a program is authorized or immutable.
