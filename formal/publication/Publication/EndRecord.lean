import Publication.Bytes
namespace Aurora.Publication

/-- Positional decimal arithmetic over actual bytes, independent of parsing. -/
inductive Digits (input : ByteArray) (start : Nat) : Nat → Nat → Prop
  | empty : Digits input start start 0
  | next : Digits input start stop value → stop < input.size →
      48 ≤ byte input stop → byte input stop ≤ 57 →
      Digits input start (stop + 1) (value * 10 + (byte input stop - 48))

structure DecimalValue (input : ByteArray) (start stop : Nat) where
  value : Nat
  digits : Digits input start stop value

/-- At most twenty digits are inspected; arithmetic uses unbounded naturals. -/
def digitLoop (input : ByteArray) (start stop : Nat) :
    (fuel pos value : Nat) → Digits input start pos value →
    Option (DecimalValue input start stop)
  | fuel, pos, value, prior =>
    if done : pos = stop then
      some ⟨value, done ▸ prior⟩
    else match fuel with
      | 0 => none
      | fuel + 1 =>
        if pos < stop then
          if bound : pos < input.size then
            if lo : 48 ≤ byte input pos then
              if hi : byte input pos ≤ 57 then
                digitLoop input start stop fuel (pos + 1)
                  (value * 10 + (byte input pos - 48)) (.next prior bound lo hi)
              else none
            else none
          else none
        else none

/-- Literal bytes of the sole record family implemented at this checkpoint. -/
def endTag : ByteArray := "ir-end ".toUTF8

def EndTag (input : ByteArray) (start : Nat) : Prop :=
  ∀ index : Fin 7, byte input (start + index.val) = byte endTag index.val

instance (input : ByteArray) (start : Nat) : Decidable (EndTag input start) :=
  inferInstanceAs (Decidable (∀ index : Fin 7,
    byte input (start + index.val) = byte endTag index.val))

/-- A canonical record payload; its final LF is separately supplied by Frames. -/
structure EndRecord (input : ByteArray) (span : Span) (value : Nat) : Prop where
  tag : EndTag input span.first
  nonempty : span.first + 7 < span.last
  bounds : span.last ≤ input.size
  digits : Digits input (span.first + 7) span.last value
  canonical : span.last = span.first + 8 ∨ byte input (span.first + 7) ≠ 48
  signedRange : value ≤ 9223372036854775807

structure DecodedEnd (input : ByteArray) (span : Span) where
  value : Nat
  grammar : EndRecord input span value

def decodeEnd (input : ByteArray) (span : Span) : Option (DecodedEnd input span) :=
  if nonempty : span.first + 7 < span.last then
    if bound : span.last ≤ input.size then
      if tag : EndTag input span.first then
        if canonical : span.last = span.first + 8 ∨ byte input (span.first + 7) ≠ 48 then
          match digitLoop input (span.first + 7) span.last 20 (span.first + 7) 0 .empty with
          | none => none
          | some parsed =>
            if range : parsed.value ≤ 9223372036854775807 then
              some ⟨parsed.value, ⟨tag, nonempty, bound, parsed.digits, canonical, range⟩⟩
            else none
        else none
      else none
    else none
  else none

theorem decodeEnd_sound (input : ByteArray) (span : Span) (result : DecodedEnd input span)
    (_accepted : decodeEnd input span = some result) : EndRecord input span result.value :=
  result.grammar

theorem digit_exhausted (input : ByteArray) (start stop pos value : Nat)
    (prior : Digits input start pos value) (unfinished : pos ≠ stop) :
    digitLoop input start stop 0 pos value prior = none := by
  simp [digitLoop, unfinished]

end Aurora.Publication
