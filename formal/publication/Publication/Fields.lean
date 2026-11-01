import Publication.Tokens
import Publication.EndRecord
namespace Aurora.Publication

structure NaturalText (input : ByteArray) (span : Span) (value maximum : Nat) : Prop where
  nonempty : span.first < span.last
  bounds : span.last ≤ input.size
  digits : Digits input span.first span.last value
  canonical : span.last = span.first + 1 ∨ byte input span.first ≠ 48
  range : value ≤ maximum

structure ParsedNatural (input : ByteArray) (span : Span) (maximum : Nat) where
  value : Nat
  grammar : NaturalText input span value maximum

def naturalText (input : ByteArray) (span : Span) (maximum : Nat) :
    Option (ParsedNatural input span maximum) :=
  if nonempty : span.first < span.last then
    if bound : span.last ≤ input.size then
      if canonical : span.last = span.first + 1 ∨ byte input span.first ≠ 48 then
        match digitLoop input span.first span.last 20 span.first 0 .empty with
        | none => none
        | some parsed =>
          if range : parsed.value ≤ maximum then
            some ⟨parsed.value, ⟨nonempty, bound, parsed.digits, canonical, range⟩⟩
          else none
      else none
    else none
  else none

inductive SignedText (input : ByteArray) (span : Span) : Int → Prop
  | nonnegative : NaturalText input span n 9223372036854775807 → SignedText input span (Int.ofNat n)
  | negative : span.first < span.last → byte input span.first = 45 →
      NaturalText input ⟨span.first + 1, span.last⟩ n 9223372036854775808 →
      n ≠ 0 → SignedText input span (-(Int.ofNat n))

structure ParsedSigned (input : ByteArray) (span : Span) where
  value : Int
  grammar : SignedText input span value

def signedText (input : ByteArray) (span : Span) : Option (ParsedSigned input span) :=
  if nonempty : span.first < span.last then
    if minus : byte input span.first = 45 then
      match naturalText input ⟨span.first + 1, span.last⟩ 9223372036854775808 with
      | none => none
      | some parsed =>
        if nonzero : parsed.value ≠ 0 then
          some ⟨-(Int.ofNat parsed.value), .negative nonempty minus parsed.grammar nonzero⟩
        else none
    else
      match naturalText input span 9223372036854775807 with
      | none => none
      | some parsed => some ⟨Int.ofNat parsed.value, .nonnegative parsed.grammar⟩
  else none

inductive HexDigit : Nat → Nat → Prop
  | decimal : 48 ≤ b → b ≤ 57 → HexDigit b (b - 48)
  | alpha : 97 ≤ b → b ≤ 102 → HexDigit b (b - 87)

def hexDigit (b : Nat) : Option { value : Nat // HexDigit b value } :=
  if lo : 48 ≤ b then
    if hi : b ≤ 57 then some ⟨b - 48, .decimal lo hi⟩
    else if alo : 97 ≤ b then
      if ahi : b ≤ 102 then some ⟨b - 87, .alpha alo ahi⟩ else none
    else none
  else none

inductive HexRun (input : ByteArray) (start : Nat) : Nat → ByteArray → Prop
  | empty : HexRun input start start ByteArray.empty
  | next : HexRun input start pos previous → pos + 1 < input.size →
      HexDigit (byte input pos) high → HexDigit (byte input (pos + 1)) low →
      HexRun input start (pos + 2) (previous.push (UInt8.ofNat (high * 16 + low)))

structure ParsedHex (input : ByteArray) (start stop : Nat) where
  value : ByteArray
  grammar : HexRun input start stop value

def hexLoop (input : ByteArray) (start stop : Nat) :
    (fuel pos : Nat) → (previous : ByteArray) → HexRun input start pos previous →
    Option (ParsedHex input start stop)
  | fuel, pos, previous, prior =>
    if done : pos = stop then some ⟨previous, done ▸ prior⟩
    else match fuel with
      | 0 => none
      | fuel + 1 =>
        if pos + 1 < stop then
          if bound : pos + 1 < input.size then
            match hexDigit (byte input pos), hexDigit (byte input (pos + 1)) with
            | some high, some low => hexLoop input start stop fuel (pos + 2)
                (previous.push (UInt8.ofNat (high.val * 16 + low.val)))
                (.next prior bound high.property low.property)
            | _, _ => none
          else none
        else none

inductive FieldKind where
  | signed | unsigned | hex | literal (text : String)
  deriving BEq, DecidableEq

inductive Field where
  | integer (value : Int)
  | bytes (value : ByteArray)
  | literal (text : String)
  deriving BEq, DecidableEq

/-- Exact byte slice spelling; bounds prevent extract's clamping from admitting
    arbitrary out-of-file or reversed spans. -/
structure LiteralText (input : ByteArray) (span : Span) (text : String) : Prop where
  ordered : span.first ≤ span.last
  bounds : span.last ≤ input.size
  spelling : input.extract span.first span.last = text.toUTF8

inductive FieldText (input : ByteArray) (span : Span) : FieldKind → Field → Prop
  | signed : SignedText input span value → FieldText input span .signed (.integer value)
  | unsigned : NaturalText input span value 18446744073709551615 →
      FieldText input span .unsigned (.integer (Int.ofNat value))
  | hex : span.first ≤ span.last → span.last ≤ input.size →
      HexRun input span.first span.last value → FieldText input span .hex (.bytes value)
  | literal : LiteralText input span text → FieldText input span (.literal text) (.literal text)

structure ParsedField (input : ByteArray) (span : Span) (kind : FieldKind) where
  value : Field
  grammar : FieldText input span kind value

def fieldText (input : ByteArray) (span : Span) (kind : FieldKind) :
    Option (ParsedField input span kind) :=
  match kind with
  | .signed => match signedText input span with
      | none => none
      | some value => some ⟨.integer value.value, .signed value.grammar⟩
  | .unsigned => match naturalText input span 18446744073709551615 with
      | none => none
      | some value => some ⟨.integer (Int.ofNat value.value), .unsigned value.grammar⟩
  | .hex =>
    if ordered : span.first ≤ span.last then
      if bound : span.last ≤ input.size then
        match hexLoop input span.first span.last ((span.last - span.first) / 2 + 1)
            span.first ByteArray.empty .empty with
        | none => none
        | some value => some ⟨.bytes value.value, .hex ordered bound value.grammar⟩
      else none
    else none
  | .literal text =>
    if ordered : span.first ≤ span.last then
      if bound : span.last ≤ input.size then
        if spelling : input.extract span.first span.last = text.toUTF8 then
          some ⟨.literal text, .literal ⟨ordered, bound, spelling⟩⟩
        else none
      else none
    else none

theorem field_sound (input : ByteArray) (span : Span) (kind : FieldKind)
    (result : ParsedField input span kind) (_accepted : fieldText input span kind = some result) :
    FieldText input span kind result.value := result.grammar

end Aurora.Publication
