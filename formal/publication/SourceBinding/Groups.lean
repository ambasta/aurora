import SourceBinding.Headers
namespace Aurora.SourceBinding

/-- Angle brackets are deliberately not general delimiters: in bodies they are comparisons. -/
def Opening (input : ByteArray) (token : Lexeme) (close : String) : Prop :=
  (Is input token "(" ∧ close = ")") ∨ (Is input token "[" ∧ close = "]") ∨
  (Is input token "{" ∧ close = "}")
instance (input : ByteArray) (token : Lexeme) (close : String) : Decidable (Opening input token close) := by
  unfold Opening; infer_instance

def Atom (input : ByteArray) (token : Lexeme) : Prop :=
  ∀ delimiter ∈ (["(",")","[","]","{","}"] : List String), ¬ Is input token delimiter
instance (input : ByteArray) (token : Lexeme) : Decidable (Atom input token) := by
  unfold Atom; infer_instance

/-- Balanced opaque token sequence ending at its original opener's closer.
    The exact interior and closing token remain available to later selected-body parsing. -/
inductive Balanced (input : ByteArray) : String → List Lexeme → List Lexeme → Lexeme → List Lexeme → Prop
  | finish : Is input closing close → Balanced input close (closing :: rest) [] closing rest
  | atom : Atom input token → Balanced input close rest body closing remaining →
      Balanced input close (token :: rest) (token :: body) closing remaining
  | group : Opening input opener innerClose → Balanced input innerClose rest inner innerEnd after →
      Balanced input close after body closing remaining →
      Balanced input close (opener :: rest) (opener :: inner ++ innerEnd :: body) closing remaining

structure ParsedGroup (input : ByteArray) (close : String) (tokens : List Lexeme) where
  body : List Lexeme
  closing : Lexeme
  rest : List Lexeme
  grammar : Balanced input close tokens body closing rest

/-- Fuel is a recursion-depth ceiling, not a claimed exact token-byte budget. -/
def group (input : ByteArray) : (fuel : Nat) → (close : String) →
    (tokens : List Lexeme) → Option (ParsedGroup input close tokens)
  | 0, _, _ => none
  | fuel + 1, close, tokens => match tokens with
    | [] => none
    | token :: tail => do
      if ending : Is input token close then
        return ⟨[], token, tail, .finish ending⟩
      else if atom : Atom input token then
        let remaining ← group input fuel close tail
        return ⟨token :: remaining.body, remaining.closing, remaining.rest, .atom atom remaining.grammar⟩
      else
        let nestedClose := if Is input token "(" then ")" else if Is input token "[" then "]" else "}"
        if opening : Opening input token nestedClose then
          let inner ← group input fuel nestedClose tail
          let remaining ← group input fuel close inner.rest
          return ⟨token :: inner.body ++ inner.closing :: remaining.body, remaining.closing, remaining.rest,
            .group opening inner.grammar remaining.grammar⟩
        else none

/-- A balanced opaque span consumes an actual prefix, never a hidden deletion. -/
theorem Balanced.prefix {input : ByteArray} {close : String} {tokens body : List Lexeme}
    {closing : Lexeme} {rest : List Lexeme} (grammar : Balanced input close tokens body closing rest) :
    tokens = body ++ closing :: rest := by
  induction grammar with
  | finish _ => rfl
  | atom _ _ ih => simp [ih]
  | group _ _ _ inner tail => simp [inner, tail, List.append_assoc]

end Aurora.SourceBinding
