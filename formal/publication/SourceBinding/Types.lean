import SourceBinding.Groups
namespace Aurora.SourceBinding

inductive SourceType where
  | named (name : Name)
  | applied (name : Name) (argument : SourceType)
  | constant (inner : SourceType)
  | reference (inner : SourceType)
  deriving BEq, DecidableEq

/-- A deliberately bounded type surface, not type resolution or compiler admission. -/
inductive TypeSyntax (input : ByteArray) : List Lexeme → SourceType → List Lexeme → Prop
  | named : Qualified input "::" tokens name rest → TypeSyntax input tokens (.named name) rest
  | applied : Qualified input "::" tokens name (opening :: arguments) → Is input opening "<" →
      TypeSyntax input arguments argument (closing :: rest) → Is input closing ">" →
      TypeSyntax input tokens (.applied name argument) rest
  | constant : Is input qualifier "const" → TypeSyntax input tokens typ rest →
      TypeSyntax input (qualifier :: tokens) (.constant typ) rest
  | reference : TypeSyntax input tokens typ (ampersand :: rest) → Is input ampersand "&" →
      TypeSyntax input tokens (.reference typ) rest

structure ParsedType (input : ByteArray) (tokens : List Lexeme) where
  type : SourceType
  rest : List Lexeme
  grammar : TypeSyntax input tokens type rest

mutual
  def typeSyntax (input : ByteArray) : (fuel : Nat) → (tokens : List Lexeme) → Option (ParsedType input tokens)
    | 0, _ => none
    | fuel + 1, tokens => match tokens with
      | [] => none
      | token :: rest => do
        if qualifier : Is input token "const" then
          let base ← typeCore input fuel rest
          return ⟨.constant base.type, base.rest, .constant qualifier base.grammar⟩
        else typeCore input fuel (token :: rest)
  def typeCore (input : ByteArray) : (fuel : Nat) → (tokens : List Lexeme) → Option (ParsedType input tokens)
    | 0, _ => none
    | fuel + 1, tokens => do
      let name ← qualified input "::" 64 tokens
      let base ← (match eq : name.rest with
        | opening :: arguments =>
          if angle : Is input opening "<" then do
            let argument ← typeSyntax input fuel arguments
            match endEq : argument.rest with
            | closing :: tail =>
              if close : Is input closing ">" then
                some (⟨.applied name.name argument.type, tail,
                  .applied (eq ▸ name.grammar) angle (endEq ▸ argument.grammar) close⟩ : ParsedType input tokens)
              else none
            | [] => none
          else some ⟨.named name.name, name.rest, .named name.grammar⟩
        | [] => some ⟨.named name.name, [], .named (eq ▸ name.grammar)⟩)
      match eq : base.rest with
      | ampersand :: tail =>
        if amp : Is input ampersand "&" then
          return ⟨.reference base.type, tail, .reference (eq ▸ base.grammar) amp⟩
        else return base
      | [] => return base
end

structure Formal where
  name : ByteArray
  type : SourceType
  deriving BEq, DecidableEq

inductive FormalSyntax (input : ByteArray) : List Lexeme → Formal → List Lexeme → Prop
  | parameter : TypeSyntax input tokens typ (name :: rest) → Identifier input name →
      FormalSyntax input tokens ⟨spelling input name, typ⟩ rest

structure ParsedFormal (input : ByteArray) (tokens : List Lexeme) where
  formal : Formal
  rest : List Lexeme
  grammar : FormalSyntax input tokens formal rest

def formal (input : ByteArray) (tokens : List Lexeme) : Option (ParsedFormal input tokens) := do
  let typ ← typeSyntax input 32 tokens
  match eq : typ.rest with
  | name :: rest =>
    if identifier : Identifier input name then
      return ⟨⟨spelling input name, typ.type⟩, rest, .parameter (eq ▸ typ.grammar) identifier⟩
    else none
  | [] => none

/-- Parameter list after its opening parenthesis, through its closing parenthesis. -/
inductive Parameters (input : ByteArray) : List Lexeme → List Formal → List Lexeme → Prop
  | empty : Is input close ")" → Parameters input (close :: rest) [] rest
  | last : FormalSyntax input tokens parameter (close :: rest) → Is input close ")" →
      Parameters input tokens [parameter] rest
  | more : FormalSyntax input tokens parameter (comma :: tail) → Is input comma "," →
      Parameters input tail parameters rest → parameters ≠ [] →
      Parameters input tokens (parameter :: parameters) rest

structure ParsedParameters (input : ByteArray) (tokens : List Lexeme) where
  formals : List Formal
  rest : List Lexeme
  grammar : Parameters input tokens formals rest

def parameters (input : ByteArray) : (fuel : Nat) → (tokens : List Lexeme) → Option (ParsedParameters input tokens)
  | 0, _ => none
  | fuel + 1, tokens => match tokens with
    | [] => none
    | token :: tail => do
      if close : Is input token ")" then
        return ⟨[], tail, .empty close⟩
      else
        let parameter ← formal input (token :: tail)
        match eq : parameter.rest with
        | [] => none
        | separator :: remaining =>
          if close : Is input separator ")" then
            return ⟨[parameter.formal], remaining, .last (eq ▸ parameter.grammar) close⟩
          else if comma : Is input separator "," then
            let others ← parameters input fuel remaining
            if nonempty : others.formals ≠ [] then
              return ⟨parameter.formal :: others.formals, others.rest,
                .more (eq ▸ parameter.grammar) comma others.grammar nonempty⟩
            else none
          else none

end Aurora.SourceBinding
