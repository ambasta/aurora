import SourceBinding.Selection
import SourceBinding.GuardExpr
namespace Aurora.SourceBinding

inductive SourceBinOp where
  | add | subtract | bitAnd | bitOr | shift | rightShift | compare (op : CompareOp) | and | or
  deriving BEq, DecidableEq, Repr

def precedence : SourceBinOp → Nat
  | .or => 1
  | .and => 2
  | .bitOr => 3
  | .bitAnd => 4
  | .compare .eq | .compare .ne => 5
  | .compare _ => 6
  | .shift | .rightShift => 7
  | .add | .subtract => 8

def operatorText : SourceBinOp → String
  | .or => "||"
  | .and => "&&"
  | .compare .eq => "=="
  | .compare .ne => "!="
  | .compare .lt => "<"
  | .compare .le => "<="
  | .compare .gt => ">"
  | .compare .ge => ">="
  | .bitAnd => "&"
  | .bitOr => "|"
  | .shift => "<<"
  | .rightShift => ">>"
  | .add => "+"
  | .subtract => "-"

inductive Callee where
  | named (name : Name)
  | receiver (field method : ByteArray)
  deriving BEq, DecidableEq

/-- Entire selected bodies have raw syntax trees; call syntax is NOT call typing/effects. -/
inductive SourceExpr where
  | signed12
  | signedCount (value : Nat)
  | word (value : Nat)
  | boolean (value : Bool)
  | name (name : Name)
  | call (callee : Callee) (arguments : List SourceExpr)
  | not (inner : SourceExpr)
  | binary (operator : SourceBinOp) (left right : SourceExpr)
  deriving BEq


inductive CalleeSyntax (input : ByteArray) : List Lexeme → Callee → List Lexeme → Prop
  | named : Qualified input "::" tokens name rest → CalleeSyntax input tokens (.named name) rest
  | receiver : Qualified input "::" tokens [field] (dot :: method :: rest) → Is input dot "." →
      Identifier input method → CalleeSyntax input tokens (.receiver field (spelling input method)) rest

structure ParsedCallee (input : ByteArray) (tokens : List Lexeme) where
  callee : Callee
  rest : List Lexeme
  grammar : CalleeSyntax input tokens callee rest

def calleeSyntax (input : ByteArray) (tokens : List Lexeme) : Option (ParsedCallee input tokens) := do
  let name ← qualified input "::" 64 tokens
  match eq : name.rest with
  | dot :: method :: rest =>
    if dotted : Is input dot "." then
      match names : name.name with
      | [field] =>
        if ident : Identifier input method then
          return ⟨.receiver field (spelling input method),rest,.receiver (names ▸ eq ▸ name.grammar) dotted ident⟩
        else none
      | _ => none
    else return ⟨.named name.name,name.rest,.named name.grammar⟩
  | _ => return ⟨.named name.name,name.rest,.named name.grammar⟩

/- Levels 1..9 encode the supported C++ precedence; same-level operators compose
    on the left, and right operands enter the strictly higher precedence level. -/
mutual
  inductive ExprSyntax (input : ByteArray) : Nat → List Lexeme → SourceExpr → List Lexeme → Prop
    | signed12 : token.kind = .numeral .signed 12 → ExprSyntax input 9 (token :: rest) .signed12 rest
    | signedCount : token.kind = .numeral .signed value → (value = 4 ∨ value = 32) →
        ExprSyntax input 9 (token :: rest) (.signedCount value) rest
    | word : token.kind = .numeral .word value → ExprSyntax input 9 (token :: rest) (.word value) rest
    | boolean : Is input token (if value then "true" else "false") →
        ExprSyntax input 9 (token :: rest) (.boolean value) rest
    | name : CalleeSyntax input tokens (.named name) rest → ExprSyntax input 9 tokens (.name name) rest
    | call : CalleeSyntax input tokens callee (opening :: args) → Is input opening "(" →
        ArgumentsSyntax input args arguments rest → ExprSyntax input 9 tokens (.call callee arguments) rest
    | parenthesized : Is input opening "(" → ExprSyntax input 1 tokens inner (closing :: rest) →
        Is input closing ")" → ExprSyntax input 9 (opening :: tokens) inner rest
    | not : Is input token "!" → ExprSyntax input 9 tokens inner rest →
        ExprSyntax input 9 (token :: tokens) (.not inner) rest
    | raise : 1 ≤ level → level < 9 → ExprSyntax input (level + 1) tokens inner rest →
        ExprSyntax input level tokens inner rest
    | binary : ExprSyntax input level tokens left (token :: middle) →
        Is input token (operatorText op) → precedence op = level →
        ExprSyntax input (level + 1) middle right rest →
        ExprSyntax input level tokens (.binary op left right) rest
  inductive ArgumentsSyntax (input : ByteArray) : List Lexeme → List SourceExpr → List Lexeme → Prop
    | empty : Is input closing ")" → ArgumentsSyntax input (closing :: rest) [] rest
    | last : ExprSyntax input 1 tokens expression (closing :: rest) → Is input closing ")" →
        ArgumentsSyntax input tokens [expression] rest
    | more : ExprSyntax input 1 tokens expression (comma :: tail) → Is input comma "," →
        ArgumentsSyntax input tail expressions rest → expressions ≠ [] →
        ArgumentsSyntax input tokens (expression :: expressions) rest
end

structure ParsedExpr (input : ByteArray) (level : Nat) (tokens : List Lexeme) where
  expression : SourceExpr
  rest : List Lexeme
  grammar : ExprSyntax input level tokens expression rest

structure ParsedArguments (input : ByteArray) (tokens : List Lexeme) where
  arguments : List SourceExpr
  rest : List Lexeme
  grammar : ArgumentsSyntax input tokens arguments rest

def operatorCandidate (input : ByteArray) (token : Lexeme) : Option SourceBinOp :=
  ([.or,.and,.bitOr,.bitAnd,.shift,.rightShift,.add,.compare .eq,.compare .ne,.compare .lt,.compare .le,.compare .gt,.compare .ge,.subtract] : List SourceBinOp).find?
    (fun op => decide (Is input token (operatorText op)))

mutual
  def expressionSyntax (input : ByteArray) : (fuel level : Nat) → (tokens : List Lexeme) →
      Option (ParsedExpr input level tokens)
    | 0, _, _ => none
    | fuel + 1, level, tokens =>
      if atomic : level = 9 then atomic ▸ atomSyntax input fuel tokens
      else if low : 1 ≤ level then
        if high : level < 9 then do
          let inner ← expressionSyntax input fuel (level + 1) tokens
          expressionTail input fuel level tokens inner.expression inner.rest (.raise low high inner.grammar)
        else none
      else none
  def expressionTail (input : ByteArray) : (fuel level : Nat) → (tokens : List Lexeme) →
      (left : SourceExpr) → (rest : List Lexeme) → ExprSyntax input level tokens left rest →
      Option (ParsedExpr input level tokens)
    | 0, _, _, _, _, _ => none
    | fuel + 1, level, tokens, left, rest, prior => match rest with
      | [] => some ⟨left,[],prior⟩
      | token :: tail =>
        match operatorCandidate input token with
        | none => some ⟨left,token :: tail,prior⟩
        | some op =>
          if atLevel : precedence op = level then do
            if actual : Is input token (operatorText op) then
              let right ← expressionSyntax input fuel (level + 1) tail
              expressionTail input fuel level tokens (.binary op left right.expression) right.rest
                (.binary prior actual atLevel right.grammar)
            else none
          else some ⟨left,token :: tail,prior⟩
  def atomSyntax (input : ByteArray) : (fuel : Nat) → (tokens : List Lexeme) → Option (ParsedExpr input 9 tokens)
    | 0, _ => none
    | fuel + 1, tokens => match tokens with
      | [] => none
      | token :: tail => do
        match kind : token.kind with
        | .numeral .signed 12 => return ⟨.signed12,tail,.signed12 kind⟩
        | .numeral .signed value =>
          if supported : value = 4 ∨ value = 32 then
            return ⟨.signedCount value,tail,.signedCount kind supported⟩
          else none
        | .numeral .word value => return ⟨.word value,tail,.word kind⟩
        | _ =>
          if yes : Is input token "true" then return ⟨.boolean true,tail,.boolean yes⟩
          else if no : Is input token "false" then return ⟨.boolean false,tail,.boolean no⟩
          else if neg : Is input token "!" then
            let inner ← atomSyntax input fuel tail
            return ⟨.not inner.expression,inner.rest,.not neg inner.grammar⟩
          else if opening : Is input token "(" then
            let inner ← expressionSyntax input fuel 1 tail
            match eq : inner.rest with
            | closing :: remaining =>
              if close : Is input closing ")" then
                return ⟨inner.expression,remaining,.parenthesized opening (eq ▸ inner.grammar) close⟩
              else none
            | [] => none
          else
            let callee ← calleeSyntax input (token :: tail)
            match eq : callee.rest with
            | opening :: remaining =>
              if call : Is input opening "(" then
                let args ← argumentsSyntax input fuel remaining
                return ⟨.call callee.callee args.arguments,args.rest,.call (eq ▸ callee.grammar) call args.grammar⟩
              else match named : callee.callee with
                | .named name => return ⟨.name name,callee.rest,.name (named ▸ callee.grammar)⟩
                | _ => none
            | [] => match named : callee.callee with
                | .named name => return ⟨.name name,[],.name (named ▸ eq ▸ callee.grammar)⟩
                | _ => none
  def argumentsSyntax (input : ByteArray) : (fuel : Nat) → (tokens : List Lexeme) →
      Option (ParsedArguments input tokens)
    | 0, _ => none
    | fuel + 1, tokens => match tokens with
      | [] => none
      | token :: tail => do
        if close : Is input token ")" then return ⟨[],tail,.empty close⟩
        else
          let first ← expressionSyntax input fuel 1 (token :: tail)
          match eq : first.rest with
          | [] => none
          | separator :: remaining =>
            if close : Is input separator ")" then
              return ⟨[first.expression],remaining,.last (eq ▸ first.grammar) close⟩
            else if comma : Is input separator "," then
              let others ← argumentsSyntax input fuel remaining
              if hasArgument : others.arguments.isEmpty = false then
                have nonempty : others.arguments ≠ [] := by intro empty; simp [empty] at hasArgument
                return ⟨first.expression :: others.arguments,others.rest,
                  .more (eq ▸ first.grammar) comma others.grammar nonempty⟩
              else none
            else none
end

theorem expression_syntax_sound (input : ByteArray) (fuel level : Nat) (tokens : List Lexeme)
    (result : ParsedExpr input level tokens)
    (_accepted : expressionSyntax input fuel level tokens = some result) :
    ExprSyntax input level tokens result.expression result.rest := result.grammar

end Aurora.SourceBinding
