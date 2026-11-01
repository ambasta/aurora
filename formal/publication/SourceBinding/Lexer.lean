import Publication.Fields

namespace Aurora.SourceBinding
open Aurora.Publication (Span byte NaturalText naturalText)

/-- Restricted ASCII source profile. This is not the complete Aurora lexer. -/
def Space (b : Nat) : Prop := b = 32 ∨ (9 ≤ b ∧ b ≤ 13)
def Letter (b : Nat) : Prop := (65 ≤ b ∧ b ≤ 90) ∨ (97 ≤ b ∧ b ≤ 122) ∨ b = 95
def Digit (b : Nat) : Prop := 48 ≤ b ∧ b ≤ 57
def Word (b : Nat) : Prop := Letter b ∨ Digit b
def CommentByte (b : Nat) : Prop := b ≠ 10 ∧ ((9 ≤ b ∧ b ≤ 13) ∨ (32 ≤ b ∧ b ≤ 126))
def Punctuation (b : Nat) : Prop := b ∈ ([40,41,123,125,91,93,58,59,44,61,43,45,42,47,37,60,62,33,46,38,124,94,126] : List Nat)
def Pair (a b : Nat) : Prop := (a,b) ∈ ([(45,62),(61,61),(33,61),(60,61),(62,61),(58,58),(60,60),(62,62),(38,38),(124,124)] : List (Nat × Nat))
instance (b : Nat) : Decidable (Space b) := by unfold Space; infer_instance
instance (b : Nat) : Decidable (Letter b) := by unfold Letter; infer_instance
instance (b : Nat) : Decidable (Digit b) := by unfold Digit; infer_instance
instance (b : Nat) : Decidable (Word b) := by unfold Word; infer_instance
instance (b : Nat) : Decidable (CommentByte b) := by unfold CommentByte; infer_instance
instance (b : Nat) : Decidable (Punctuation b) := by unfold Punctuation; infer_instance
instance (a b : Nat) : Decidable (Pair a b) := by unfold Pair; infer_instance

/-- Every consumed byte has an explicit property and an in-file bound. -/
inductive Run (input : ByteArray) (pred : Nat → Prop) (start : Nat) : Nat → Prop
  | empty : Run input pred start start
  | next : Run input pred start stop → stop < input.size → pred (byte input stop) →
      Run input pred start (stop + 1)

structure RunEnd (input : ByteArray) (pred : Nat → Prop) (start : Nat) where
  stop : Nat
  run : Run input pred start stop
  boundary : stop = input.size ∨ (stop < input.size ∧ ¬ pred (byte input stop))

def scan (input : ByteArray) (pred : Nat → Prop) [DecidablePred pred] (start : Nat) :
    (fuel pos : Nat) → Run input pred start pos → Option (RunEnd input pred start)
  | fuel, pos, prior =>
    if done : pos = input.size then some ⟨pos, prior, Or.inl done⟩
    else match fuel with
      | 0 => none
      | fuel + 1 =>
        if bound : pos < input.size then
          if yes : pred (byte input pos) then
            scan input pred start fuel (pos + 1) (.next prior bound yes)
          else some ⟨pos, prior, Or.inr ⟨bound, yes⟩⟩
        else none

inductive NumberKind where
  | signed | word | octet
  deriving BEq, DecidableEq, Repr

def maximum : NumberKind → Nat
  | .signed => 9223372036854775807
  | .word => 18446744073709551615
  | .octet => 255

def suffix : NumberKind → String
  | .signed => ""
  | .word => "u64"
  | .octet => "u8"

/-- Numeric spellings are decimal, canonical and bounded in this profile.
    Binary/separator literals and minimum signed unary-minus special syntax reject. -/
inductive NumberText (input : ByteArray) (span : Span) (kind : NumberKind) (value : Nat) : Prop
  | decimal (split : Nat) : NaturalText input ⟨span.first, split⟩ value (maximum kind) →
      span.last ≤ input.size → span.last = split + (suffix kind).toUTF8.size →
      input.extract split span.last = (suffix kind).toUTF8 → NumberText input span kind value

structure ParsedNumber (input : ByteArray) (span : Span) where
  kind : NumberKind
  value : Nat
  grammar : NumberText input span kind value

def numberKind (input : ByteArray) (span : Span) (kind : NumberKind) :
    Option (ParsedNumber input span) := do
  let length := (suffix kind).toUTF8.size
  if bound : span.last ≤ input.size then
    if length ≤ span.last then
      let split := span.last - length
      if exactLength : span.last = split + length then
        if spelling : input.extract split span.last = (suffix kind).toUTF8 then
          let n ← naturalText input ⟨span.first, split⟩ (maximum kind)
          return ⟨kind, n.value, (.decimal split n.grammar bound exactLength spelling)⟩
        else none
      else none
    else none
  else none

def number (input : ByteArray) (span : Span) : Option (ParsedNumber input span) :=
  numberKind input span .signed <|> numberKind input span .word <|> numberKind input span .octet

inductive Kind where
  | whitespace | comment | identifier | numeral (kind : NumberKind) (value : Nat) | punctuation
  deriving BEq, DecidableEq, Repr

structure Lexeme where
  span : Span
  kind : Kind
  deriving BEq, DecidableEq, Repr

/-- Independent lexical rules; maximal words/pairs cannot be split into prefixes.
    Quotes, block comments, invalid bytes and malformed numerals have no rule. -/
inductive Lexical (input : ByteArray) : Nat → Nat → Kind → Prop
  | whitespace : start < input.size → Space (byte input start) →
      Lexical input start (start + 1) .whitespace
  | comment : start + 1 < input.size → byte input start = 47 → byte input (start + 1) = 47 →
      Run input CommentByte (start + 2) stop →
      (stop = input.size ∨ (stop < input.size ∧ byte input stop = 10)) →
      Lexical input start stop .comment
  | identifier : start < stop → start < input.size → Letter (byte input start) →
      Run input Word start stop →
      (stop = input.size ∨ (stop < input.size ∧ ¬ Word (byte input stop))) →
      Lexical input start stop .identifier
  | numeral : start < stop → start < input.size → Digit (byte input start) →
      Run input Word start stop →
      (stop = input.size ∨ (stop < input.size ∧ ¬ Word (byte input stop))) →
      NumberText input ⟨start,stop⟩ kind value → Lexical input start stop (.numeral kind value)
  | pair : start + 1 < input.size → Pair (byte input start) (byte input (start + 1)) →
      Lexical input start (start + 2) .punctuation
  | single : start < input.size → Punctuation (byte input start) →
      ¬ Pair (byte input start) (byte input (start + 1)) →
      ¬ (byte input start = 47 ∧ (byte input (start + 1) = 47 ∨ byte input (start + 1) = 42)) →
      Lexical input start (start + 1) .punctuation

structure Piece (input : ByteArray) (start : Nat) where
  stop : Nat
  kind : Kind
  progress : start < stop
  grammar : Lexical input start stop kind

def lexOne (input : ByteArray) (fuel start : Nat) : Option (Piece input start) := do
  if bound : start < input.size then
    if ws : Space (byte input start) then
      return ⟨start + 1, .whitespace, Nat.lt_succ_self _, .whitespace bound ws⟩
    else if comment : byte input start = 47 ∧ byte input (start + 1) = 47 then
      if second : start + 1 < input.size then
        let tail ← scan input CommentByte (start + 2) fuel (start + 2) .empty
        if ending : tail.stop = input.size ∨ (tail.stop < input.size ∧ byte input tail.stop = 10) then
          if progress : start < tail.stop then
            return ⟨tail.stop, .comment, progress, .comment second comment.1 comment.2 tail.run ending⟩
          else none
        else none
      else none
    else if word : Word (byte input start) then
      let tail ← scan input Word start fuel (start + 1) (.next .empty bound word)
      if progress : start < tail.stop then
        if letter : Letter (byte input start) then
          return ⟨tail.stop, .identifier, progress, .identifier progress bound letter tail.run tail.boundary⟩
        else if digit : Digit (byte input start) then
          let n ← number input ⟨start, tail.stop⟩
          return ⟨tail.stop, .numeral n.kind n.value, progress,
            .numeral progress bound digit tail.run tail.boundary n.grammar⟩
        else none
      else none
    else if pair : Pair (byte input start) (byte input (start + 1)) then
      if second : start + 1 < input.size then
        return ⟨start + 2, .punctuation, by omega, .pair second pair⟩
      else none
    else if punctuation : Punctuation (byte input start) then
      if safe : ¬ (byte input start = 47 ∧ (byte input (start + 1) = 47 ∨ byte input (start + 1) = 42)) then
        return ⟨start + 1, .punctuation, Nat.lt_succ_self _, .single bound punctuation pair safe⟩
      else none
    else none
  else none

/-- Full contiguous byte coverage, including discarded trivia; reverse accumulation. -/
inductive Coverage (input : ByteArray) : List Lexeme → Nat → Prop
  | empty : Coverage input [] 0
  | next : Coverage input prior start → start < stop → Lexical input start stop kind →
      Coverage input (⟨⟨start,stop⟩,kind⟩ :: prior) stop

structure Lexed (input : ByteArray) where
  reversed : List Lexeme
  grammar : Coverage input reversed input.size

def lexLoop (input : ByteArray) (tokenBytes : Nat) : (fuel pos : Nat) →
    (prior : List Lexeme) → Coverage input prior pos → Option (Lexed input)
  | fuel, pos, prior, grammar =>
    if done : pos = input.size then some ⟨prior, done ▸ grammar⟩
    else match fuel with
      | 0 => none
      | fuel + 1 => do
        let piece ← lexOne input tokenBytes pos
        lexLoop input tokenBytes fuel piece.stop (⟨⟨pos,piece.stop⟩,piece.kind⟩ :: prior)
          (.next grammar piece.progress piece.grammar)

def lex (input : ByteArray) (byteLimit : Nat := 1048576) (tokenLimit : Nat := 65536) :
    Option (Lexed input) :=
  if input.size ≤ byteLimit then lexLoop input tokenLimit input.size 0 [] .empty else none

def significant (xs : List Lexeme) : List Lexeme := xs.filter fun x =>
  match x.kind with | .whitespace | .comment => false | _ => true

def spelling (input : ByteArray) (token : Lexeme) : ByteArray :=
  input.extract token.span.first token.span.last

theorem lex_sound (input : ByteArray) (result : Lexed input)
    (_accepted : lex input = some result) : Coverage input result.reversed input.size := result.grammar

theorem lex_oversize (input : ByteArray) (limit tokens : Nat) (large : limit < input.size) :
    lex input limit tokens = none := by simp [lex, Nat.not_le.mpr large]

theorem lex_exhausted (input : ByteArray) (tokenBytes pos : Nat)
    (prior : List Lexeme) (grammar : Coverage input prior pos) (unfinished : pos ≠ input.size) :
    lexLoop input tokenBytes 0 pos prior grammar = none := by simp [lexLoop, unfinished]

theorem Run.ordered {input : ByteArray} {pred : Nat → Prop} {start stop : Nat}
    (run : Run input pred start stop) : start ≤ stop := by
  induction run with
  | empty => exact Nat.le_refl _
  | next _ _ _ ih => omega

theorem Run.bounded {input : ByteArray} {pred : Nat → Prop} {start stop : Nat}
    (run : Run input pred start stop) (initial : start ≤ input.size) : stop ≤ input.size := by
  cases run with
  | empty => exact initial
  | next _ bound _ => omega

theorem Lexical.interval {input : ByteArray} {start stop : Nat} {kind : Kind}
    (rule : Lexical input start stop kind) : start < stop ∧ stop ≤ input.size := by
  cases rule with
  | whitespace bound _ => exact ⟨Nat.lt_succ_self _, Nat.succ_le_of_lt bound⟩
  | comment bound _ _ run _ =>
    exact ⟨Nat.lt_of_lt_of_le (Nat.lt_add_of_pos_right (by decide : 0 < 2)) run.ordered,
      run.bounded (Nat.succ_le_of_lt bound)⟩
  | identifier progress bound _ run _ => exact ⟨progress, run.bounded (Nat.le_of_lt bound)⟩
  | numeral progress bound _ run _ _ => exact ⟨progress, run.bounded (Nat.le_of_lt bound)⟩
  | pair bound _ => exact ⟨Nat.lt_add_of_pos_right (by decide : 0 < 2), Nat.succ_le_of_lt bound⟩
  | single bound _ _ _ => exact ⟨Nat.lt_succ_self _, Nat.succ_le_of_lt bound⟩

theorem Coverage.member_interval {input : ByteArray} {xs : List Lexeme} {stop : Nat}
    (coverage : Coverage input xs stop) {token : Lexeme} (member : token ∈ xs) :
    token.span.first < token.span.last ∧ token.span.last ≤ input.size := by
  induction coverage with
  | empty => simp at member
  | next prior progress grammar ih =>
    rcases List.mem_cons.mp member with head | tail
    · subst token; exact grammar.interval
    · exact ih tail

theorem NumberText.range {input : ByteArray} {span : Span} {kind : NumberKind} {value : Nat}
    (number : NumberText input span kind value) : value ≤ maximum kind := by
  cases number with
  | decimal _ text _ _ _ => exact text.range

end Aurora.SourceBinding
