import Publication.Fields
namespace Aurora.Publication

/-- Version-1 wire schema only, not an instruction-semantics catalogue. -/
def schema : String → Option (List FieldKind)
  | "aurora-published-ir" => some (["1", "types", "fields", "callables", "operands", "cfg", "resources"].map .literal)
  | "ir-counts" => some (List.replicate 11 .signed)
  | "ir-name-bytes" | "ir-literal-bytes" => some [.hex]
  | "ir-type" => some (List.replicate 6 .signed ++ List.replicate 3 .unsigned)
  | "ir-enum" => some (List.replicate 4 .signed)
  | "ir-class" => some (List.replicate 3 .signed ++ [.unsigned] ++ List.replicate 7 .signed)
  | "ir-field" => some (List.replicate 8 .signed)
  | "ir-leaf-offset" => some (List.replicate 3 .signed)
  | "ir-callable" => some (List.replicate 8 .signed ++ [.unsigned, .signed, .signed, .unsigned] ++ List.replicate 4 .signed)
  | "ir-slot" => some (List.replicate 6 .signed)
  | "ir-catalog-type" => some [.signed, .signed, .hex]
  | "ir-resource" => some [.signed, .signed, .signed, .hex]
  | "ir-resource-method" => some (List.replicate 8 .signed ++ [.hex])
  | "ir-operand" => some [.signed, .signed, .signed, .unsigned, .signed, .signed]
  | "ir-body" => some (List.replicate 3 .signed)
  | "ir-code" => some (List.replicate 4 .signed ++ [.unsigned] ++ List.replicate 8 .signed)
  | "ir-end-body" => some [.signed, .signed]
  | "ir-end" => some [.signed]
  | _ => none

/-- Display tags are not permitted to introduce authoritative records. -/
def displayTags : List String :=
  ["class", "enum", "callable", "slot", "origin", "body", "code", "object",
   "span", "spanvalues", "service_resource", "retained"]

inductive FieldListText (input : ByteArray) : List Span → List FieldKind → List Field → Prop
  | nil : FieldListText input [] [] []
  | cons : FieldText input span kind value → FieldListText input spans kinds values →
      FieldListText input (span :: spans) (kind :: kinds) (value :: values)

theorem FieldListText.lengths {input : ByteArray} {spans kinds values}
    (grammar : FieldListText input spans kinds values) :
    spans.length = kinds.length ∧ values.length = kinds.length := by
  induction grammar with
  | nil => exact ⟨rfl, rfl⟩
  | cons _ _ ih => simpa using ih

theorem FieldListText.integer_at {input : ByteArray} {spans kinds values}
    (grammar : FieldListText input spans kinds values) (index : Nat)
    (numeric : kinds[index]? = some .signed ∨ kinds[index]? = some .unsigned) :
    ∃ number, values[index]? = some (.integer number) := by
  induction grammar generalizing index with
  | nil => simp at numeric
  | @cons span kind value spans kinds values head tail ih =>
    cases index with
    | zero =>
      simp only [List.getElem?_cons_zero, Option.some.injEq] at numeric
      rcases numeric with signed | unsigned
      · subst kind; cases head with | signed h => exact ⟨_, rfl⟩
      · subst kind; cases head with | unsigned h => exact ⟨_, rfl⟩
    | succ index => exact ih index numeric

structure ParsedFields (input : ByteArray) (spans : List Span) (kinds : List FieldKind) where
  values : List Field
  grammar : FieldListText input spans kinds values

def fieldsText (input : ByteArray) : (spans : List Span) → (kinds : List FieldKind) →
    Option (ParsedFields input spans kinds)
  | [], [] => some ⟨[], .nil⟩
  | span :: spans, kind :: kinds =>
    match fieldText input span kind, fieldsText input spans kinds with
    | some head, some tail => some ⟨head.value :: tail.values, .cons head.grammar tail.grammar⟩
    | _, _ => none
  | _, _ => none

structure Record where
  tag : String
  fields : List Field
  display : Bool

/-- Exact token spans and values for canonical records; display records carry
    no semantic fields. Framing supplies full printable-payload coverage. -/
inductive RecordText (input : ByteArray) (span : Span) : Record → Prop
  | canonical : schema tag = some kinds →
      Words input span.first span.last (tagSpan :: fieldSpans) →
      LiteralText input tagSpan tag → FieldListText input fieldSpans kinds values →
      RecordText input span ⟨tag, values, false⟩
  | display : tag ∈ displayTags → LiteralText input tagSpan tag →
      tagSpan.first = span.first → WordRun input span.first tagSpan.last →
      (tagSpan.last = span.last ∨
        (tagSpan.last < span.last ∧ tagSpan.last < input.size ∧ byte input tagSpan.last = 32)) →
      RecordText input span ⟨tag, [], true⟩

structure ParsedRecord (input : ByteArray) (span : Span) where
  value : Record
  grammar : RecordText input span value

/-- Tag decoding chooses a schema, but the exact original tag bytes are checked
    independently below; no decoded String is treated as a byte certificate. -/
def recordText (input : ByteArray) (span : Span) : Option (ParsedRecord input span) := do
  let word ← wordLoop input span.first span.last 64 span.first (.empty span.first)
  let tagSpan : Span := ⟨span.first, word.finish⟩
  let tag ← String.fromUTF8? (input.extract tagSpan.first tagSpan.last)
  if ordered : tagSpan.first ≤ tagSpan.last then
    if bound : tagSpan.last ≤ input.size then
      if spelling : input.extract tagSpan.first tagSpan.last = tag.toUTF8 then
        let tagProof : LiteralText input tagSpan tag := ⟨ordered, bound, spelling⟩
        match hs : schema tag with
        | some kinds =>
          let tokens ← tokensLoop input 1048576 32 span.first span.last
          match tokens.tokens, tokens.grammar with
          | [], _ => none
          | first :: rest, grammar =>
            if same : first = tagSpan then
              let values ← fieldsText input rest kinds
              some ⟨⟨tag, values.values, false⟩,
                .canonical hs grammar (same ▸ tagProof) values.grammar⟩
            else none
        | none =>
          if known : tag ∈ displayTags then
            some ⟨⟨tag, [], true⟩, .display known tagProof rfl word.run word.ending⟩
          else none
      else none
    else none
  else none

theorem record_sound (input : ByteArray) (span : Span) (result : ParsedRecord input span)
    (_accepted : recordText input span = some result) : RecordText input span result.value :=
  result.grammar

end Aurora.Publication
