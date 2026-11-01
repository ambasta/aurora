import Publication.Records
namespace Aurora.Publication

inductive RecordLines (input : ByteArray) : List Span → List Record → Prop
  | nil : RecordLines input [] []
  | cons : RecordText input span record → RecordLines input spans records →
      RecordLines input (span :: spans) (record :: records)

structure ParsedLines (input : ByteArray) (spans : List Span) where
  records : List Record
  grammar : RecordLines input spans records

def linesText (input : ByteArray) : (spans : List Span) → Option (ParsedLines input spans)
  | [] => some ⟨[], .nil⟩
  | span :: spans => do
    let head ← recordText input span
    let tail ← linesText input spans
    return ⟨head.value :: tail.records, .cons head.grammar tail.grammar⟩

/-- Wire syntax only. Pool uniqueness, record ordering and graph validity are
    deliberately separate structural obligations. -/
inductive WireDocument (input : ByteArray) (records : List Record) : Prop
  | intro (spans : List Span) : Frames input spans input.size →
      RecordLines input spans records → WireDocument input records

structure ParsedDocument (input : ByteArray) where
  reversed : List Record
  grammar : WireDocument input reversed

def documentText (limits : Limits) (input : ByteArray) : Option (ParsedDocument input) := do
  let framing ← frame limits input
  let values ← linesText input framing.reversed
  return ⟨values.records, ⟨framing.reversed, framing.complete, values.grammar⟩⟩

theorem document_sound (limits : Limits) (input : ByteArray) (result : ParsedDocument input)
    (_accepted : documentText limits input = some result) : WireDocument input result.reversed :=
  result.grammar

end Aurora.Publication
