import Std
namespace Aurora.Publication

/-- Total indexing; grammar rules separately establish in-file bounds. -/
def byte (input : ByteArray) (index : Nat) : Nat :=
  if bound : index < input.size then (input.get index bound).toNat else 0

structure Span where
  first : Nat
  last : Nat
  deriving Repr, BEq, DecidableEq

/-- Independent ASCII payload grammar, excluding the terminating LF. -/
inductive AsciiRun (input : ByteArray) : Nat → Nat → Prop
  | empty (start) : AsciiRun input start start
  | next : AsciiRun input start stop → stop < input.size →
      32 ≤ byte input stop → byte input stop ≤ 126 → AsciiRun input start (stop + 1)

/-- Consecutive lines, recorded in reverse order for a linear builder.
    The endpoint is immediately after the final LF, not merely a parsed prior. -/
inductive Frames (input : ByteArray) : List Span → Nat → Prop
  | empty : Frames input [] 0
  | next : Frames input previous start → AsciiRun input start stop →
      stop < input.size → byte input stop = 10 →
      Frames input (⟨start, stop⟩ :: previous) (stop + 1)

structure Line (input : ByteArray) (start : Nat) where
  stop : Nat
  payload : AsciiRun input start stop
  inBounds : stop < input.size
  newline : byte input stop = 10

/-- Fuel counts inspected bytes, including LF. Exhaustion rejects. -/
def lineLoop (input : ByteArray) (start : Nat) :
    (fuel pos : Nat) → AsciiRun input start pos → Option (Line input start)
  | 0, _, _ => none
  | fuel + 1, pos, prior =>
    if bound : pos < input.size then
      if lf : byte input pos = 10 then
        some ⟨pos, prior, bound, lf⟩
      else if lo : 32 ≤ byte input pos then
        if hi : byte input pos ≤ 126 then
          lineLoop input start fuel (pos + 1) (.next prior bound lo hi)
        else none
      else none
    else none

structure Framing (input : ByteArray) where
  reversed : List Span
  complete : Frames input reversed input.size

structure Limits where
  fileBytes : Nat := 16777216
  lineBytes : Nat := 1048576
  lines : Nat := 300000
  deriving Repr

/-- Success carries the independent full-coverage derivation. -/
def frameLoop (input : ByteArray) (lineLimit : Nat) :
    (fuel pos : Nat) → (previous : List Span) → Frames input previous pos →
    Option (Framing input)
  | fuel, pos, previous, prior =>
    if done : pos = input.size then
      some ⟨previous, done ▸ prior⟩
    else match fuel with
      | 0 => none
      | fuel + 1 =>
        match lineLoop input pos lineLimit pos (.empty pos) with
        | none => none
        | some line => frameLoop input lineLimit fuel (line.stop + 1)
            (⟨pos, line.stop⟩ :: previous)
            (.next prior line.payload line.inBounds line.newline)

def frame (limits : Limits) (input : ByteArray) : Option (Framing input) :=
  if input.size ≤ limits.fileBytes then
    frameLoop input limits.lineBytes limits.lines 0 [] .empty
  else none

theorem frame_sound (limits : Limits) (input : ByteArray) (result : Framing input)
    (_accepted : frame limits input = some result) :
    Frames input result.reversed input.size := result.complete

theorem frame_oversize (limits : Limits) (input : ByteArray)
    (large : limits.fileBytes < input.size) : frame limits input = none := by
  simp [frame, Nat.not_le.mpr large]

theorem line_exhausted (input : ByteArray) (start pos : Nat)
    (prior : AsciiRun input start pos) : lineLoop input start 0 pos prior = none := rfl

theorem frame_exhausted (input : ByteArray) (lineLimit pos : Nat)
    (previous : List Span) (prior : Frames input previous pos)
    (unfinished : pos ≠ input.size) :
    frameLoop input lineLimit 0 pos previous prior = none := by
  simp [frameLoop, unfinished]

theorem AsciiRun.ordered {input : ByteArray} {start stop : Nat}
    (run : AsciiRun input start stop) : start ≤ stop := by
  induction run with
  | empty => exact Nat.le_refl _
  | next _ _ _ _ ih => exact Nat.le_trans ih (Nat.le_succ _)

theorem Frames.no_trailing {input : ByteArray} {spans : List Span} {finish : Nat}
    (coverage : Frames input spans finish) :
    (spans = [] ∧ finish = 0) ∨
    ∃ last rest, spans = last :: rest ∧ finish = last.last + 1 ∧
      last.last < input.size ∧ byte input last.last = 10 := by
  cases coverage with
  | empty => exact Or.inl ⟨rfl, rfl⟩
  | next _ _ bound lf => exact Or.inr ⟨_, _, rfl, rfl, bound, lf⟩

end Aurora.Publication
