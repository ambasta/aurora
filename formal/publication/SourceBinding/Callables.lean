import SourceBinding.Types
namespace Aurora.SourceBinding

structure Body where
  opening : Lexeme
  tokens : List Lexeme
  closing : Lexeme
  deriving BEq, DecidableEq

inductive BodySyntax (input : ByteArray) : List Lexeme → Body → List Lexeme → Prop
  | body : Is input opening "{" → Balanced input "}" tokens inside closing rest →
      BodySyntax input (opening :: tokens) ⟨opening,inside,closing⟩ rest

structure ParsedBody (input : ByteArray) (tokens : List Lexeme) where
  body : Body
  rest : List Lexeme
  grammar : BodySyntax input tokens body rest

def bodySyntax (input : ByteArray) (tokens : List Lexeme) : Option (ParsedBody input tokens) := do
  let opening :: tail := tokens | none
  if openBrace : Is input opening "{" then
    let inside ← group input 65536 "}" tail
    return ⟨⟨opening,inside.body,inside.closing⟩,inside.rest,.body openBrace inside.grammar⟩
  else none

structure Initializer where
  name : ByteArray
  arguments : List Lexeme
  deriving BEq, DecidableEq

/-- Initializer expressions are opaque; only target names and balanced argument boundaries are bound. -/
inductive Initializers (input : ByteArray) : List Lexeme → List Initializer → List Lexeme → Prop
  | last : Identifier input name → Is input opening "(" → Balanced input ")" tokens args closing rest →
      (∀ next ∈ rest.head?, ¬ Is input next ",") →
      Initializers input (name :: opening :: tokens) [⟨spelling input name,args⟩] rest
  | more : Identifier input name → Is input opening "(" → Balanced input ")" tokens args closing (comma :: tail) →
      Is input comma "," → Initializers input tail others rest →
      Initializers input (name :: opening :: tokens) (⟨spelling input name,args⟩ :: others) rest

structure ParsedInitializers (input : ByteArray) (tokens : List Lexeme) where
  initializers : List Initializer
  rest : List Lexeme
  grammar : Initializers input tokens initializers rest

def initializers (input : ByteArray) : (fuel : Nat) → (tokens : List Lexeme) → Option (ParsedInitializers input tokens)
  | 0, _ => none
  | fuel + 1, tokens => do
    let name :: opening :: tail := tokens | none
    if ident : Identifier input name then
      if paren : Is input opening "(" then
        let args ← group input 65536 ")" tail
        match eq : args.rest with
        | [] => return ⟨[⟨spelling input name,args.body⟩],[],.last ident paren (eq ▸ args.grammar) (by simp)⟩
        | next :: remaining =>
          if comma : Is input next "," then
            let others ← initializers input fuel remaining
            return ⟨⟨spelling input name,args.body⟩ :: others.initializers, others.rest,
              .more ident paren (eq ▸ args.grammar) comma others.grammar⟩
          else return ⟨[⟨spelling input name,args.body⟩],next :: remaining,
            .last ident paren (eq ▸ args.grammar) (by simpa using comma)⟩
      else none
    else none

inductive ReceiverMode where
  | ordinary | readonly | consuming
  deriving BEq, DecidableEq

inductive ModeSyntax (input : ByteArray) : List Lexeme → ReceiverMode → List Lexeme → Prop
  | ordinary : (∀ next ∈ tokens.head?, ¬ Is input next "const" ∧ ¬ Is input next "&&") →
      ModeSyntax input tokens .ordinary tokens
  | readonly : Is input token "const" → ModeSyntax input (token :: rest) .readonly rest
  | consuming : Is input token "&&" → ModeSyntax input (token :: rest) .consuming rest

structure ParsedMode (input : ByteArray) (tokens : List Lexeme) where
  mode : ReceiverMode
  rest : List Lexeme
  grammar : ModeSyntax input tokens mode rest

def modeSyntax (input : ByteArray) (tokens : List Lexeme) : ParsedMode input tokens :=
  match tokens with
  | [] => ⟨.ordinary,[],.ordinary (by simp)⟩
  | token :: rest =>
    if ro : Is input token "const" then ⟨.readonly,rest,.readonly ro⟩
    else if consume : Is input token "&&" then ⟨.consuming,rest,.consuming consume⟩
    else ⟨.ordinary,token :: rest,.ordinary (by simpa using And.intro ro consume)⟩

structure Function where
  name : ByteArray
  formals : List Formal
  mode : ReceiverMode
  result : SourceType
  body : Body
  deriving BEq, DecidableEq

inductive FunctionSyntax (input : ByteArray) : List Lexeme → Function → List Lexeme → Prop
  | function : Is input keyword "auto" → Identifier input name → Is input opening "(" →
      Parameters input tokens params afterParams → ModeSyntax input afterParams mode (arrow :: afterMode) →
      Is input arrow "->" → TypeSyntax input afterMode result afterResult → BodySyntax input afterResult body rest →
      FunctionSyntax input (keyword :: name :: opening :: tokens)
        ⟨spelling input name,params,mode,result,body⟩ rest

structure ParsedFunction (input : ByteArray) (tokens : List Lexeme) where
  function : Function
  rest : List Lexeme
  grammar : FunctionSyntax input tokens function rest

def functionSyntax (input : ByteArray) (tokens : List Lexeme) : Option (ParsedFunction input tokens) := do
  let keyword :: name :: opening :: tail := tokens | none
  if auto : Is input keyword "auto" then
    if ident : Identifier input name then
      if paren : Is input opening "(" then
        let params ← parameters input 256 tail
        let mode := modeSyntax input params.rest
        match eq : mode.rest with
        | [] => none
        | arrow :: afterMode =>
          if arrowText : Is input arrow "->" then
            let result ← typeSyntax input 32 afterMode
            let body ← bodySyntax input result.rest
            return ⟨⟨spelling input name,params.formals,mode.mode,result.type,body.body⟩,body.rest,
              .function auto ident paren params.grammar (eq ▸ mode.grammar) arrowText result.grammar body.grammar⟩
          else none
      else none
    else none
  else none

structure Constructor where
  formals : List Formal
  initializers : List Initializer
  body : Body
  deriving BEq, DecidableEq

inductive ConstructorSyntax (input : ByteArray) (owner : ByteArray) : List Lexeme → Constructor → List Lexeme → Prop
  | plain : Identifier input name → spelling input name = owner → Is input opening "(" →
      Parameters input tokens params afterParams → BodySyntax input afterParams body rest →
      ConstructorSyntax input owner (name :: opening :: tokens) ⟨params,[],body⟩ rest
  | initialized : Identifier input name → spelling input name = owner → Is input opening "(" →
      Parameters input tokens params (colon :: afterParams) → Is input colon ":" →
      Initializers input afterParams initValues afterInit → BodySyntax input afterInit body rest →
      ConstructorSyntax input owner (name :: opening :: tokens) ⟨params,initValues,body⟩ rest

structure ParsedConstructor (input : ByteArray) (owner : ByteArray) (tokens : List Lexeme) where
  constructor : Constructor
  rest : List Lexeme
  grammar : ConstructorSyntax input owner tokens constructor rest

def constructorSyntax (input : ByteArray) (owner : ByteArray) (tokens : List Lexeme) :
    Option (ParsedConstructor input owner tokens) := do
  let name :: opening :: tail := tokens | none
  if ident : Identifier input name then
    if same : spelling input name = owner then
      if paren : Is input opening "(" then
        let params ← parameters input 256 tail
        match eq : params.rest with
        | [] => none
        | next :: remaining =>
          if colon : Is input next ":" then
            let init ← initializers input 256 remaining
            let body ← bodySyntax input init.rest
            return ⟨⟨params.formals,init.initializers,body.body⟩,body.rest,
              .initialized ident same paren (eq ▸ params.grammar) colon init.grammar body.grammar⟩
          else
            let body ← bodySyntax input params.rest
            return ⟨⟨params.formals,[],body.body⟩,body.rest,.plain ident same paren params.grammar body.grammar⟩
      else none
    else none
  else none

end Aurora.SourceBinding
