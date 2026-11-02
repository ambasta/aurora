import SourceBinding.Expressions
namespace Aurora.SourceBinding

inductive SourceStatement where
  | ifThen (condition : SourceExpr) (body : List SourceStatement)
  | returnValue (value : SourceExpr)
  | call (callee : Callee) (arguments : List SourceExpr)
  | assign (name : ByteArray) (value : SourceExpr)
  deriving BEq

mutual
  inductive StatementSyntax (input : ByteArray) : List Lexeme → SourceStatement → List Lexeme → Prop
    | ifThen : Is input keyword "if" → Is input opening "(" →
        ExprSyntax input 1 tokens condition (closing :: brace :: afterCondition) →
        Is input closing ")" → Is input brace "{" →
        StatementsSyntax input true afterCondition body (endBrace :: rest) → Is input endBrace "}" →
        StatementSyntax input (keyword :: opening :: tokens) (.ifThen condition body) rest
    | returnValue : Is input keyword "return" → ExprSyntax input 1 tokens value (semicolon :: rest) →
        Is input semicolon ";" → StatementSyntax input (keyword :: tokens) (.returnValue value) rest
    | assign : Identifier input name → Is input equal "=" →
        ExprSyntax input 1 tokens value (semicolon :: rest) → Is input semicolon ";" →
        StatementSyntax input (name :: equal :: tokens) (.assign (spelling input name) value) rest
    | call : ExprSyntax input 1 tokens (.call callee arguments) (semicolon :: rest) →
        Is input semicolon ";" → StatementSyntax input tokens (.call callee arguments) rest
  inductive StatementsSyntax (input : ByteArray) : Bool → List Lexeme → List SourceStatement → List Lexeme → Prop
    | eof : StatementsSyntax input false [] [] []
    | closing : Is input token "}" → StatementsSyntax input true (token :: rest) [] (token :: rest)
    | next : StatementSyntax input tokens first after → StatementsSyntax input nested after others rest →
        StatementsSyntax input nested tokens (first :: others) rest
end

structure ParsedStatement (input : ByteArray) (tokens : List Lexeme) where
  statement : SourceStatement
  rest : List Lexeme
  grammar : StatementSyntax input tokens statement rest
structure ParsedStatements (input : ByteArray) (nested : Bool) (tokens : List Lexeme) where
  statements : List SourceStatement
  rest : List Lexeme
  grammar : StatementsSyntax input nested tokens statements rest

/-- Assignment targets are one unqualified identifier, never expression lvalues.
    The same exact token stream is consumed; malformed assignments fail closed. -/
def plainStatementSyntax (input : ByteArray) (tokens : List Lexeme) :
    Option (ParsedStatement input tokens) := do
  let callSyntax : Option (ParsedStatement input tokens) := do
    let value ← expressionSyntax input 4096 1 tokens
    match eq : value.rest with
    | semicolon :: remaining =>
      if semi : Is input semicolon ";" then
        match call : value.expression with
        | .call callee arguments =>
          return ⟨.call callee arguments,remaining,.call (call ▸ eq ▸ value.grammar) semi⟩
        | _ => none
      else none
    | [] => none
  match shape : tokens with
  | name :: equal :: afterEqual =>
    if assignment : Is input equal "=" then
      if ident : Identifier input name then
        let value ← expressionSyntax input 4096 1 afterEqual
        match eq : value.rest with
        | semicolon :: rest =>
          if semi : Is input semicolon ";" then
            return ⟨.assign (spelling input name) value.expression,rest,
              .assign ident assignment (eq ▸ value.grammar) semi⟩
          else none
        | [] => none
      else none
    else shape ▸ callSyntax
  | _ => shape ▸ callSyntax

mutual
  def statementsSyntax (input : ByteArray) : (fuel : Nat) → (nested : Bool) → (tokens : List Lexeme) →
      Option (ParsedStatements input nested tokens)
    | 0, _, _ => none
    | fuel + 1, nested, tokens => match tokens with
      | [] => if top : nested = false then some ⟨[],[],top ▸ .eof⟩ else none
      | token :: tail => do
        if close : Is input token "}" then
          if inside : nested = true then return ⟨[],token :: tail,inside ▸ .closing close⟩ else none
        else
          let first ← statementSyntax input fuel (token :: tail)
          let remaining ← statementsSyntax input fuel nested first.rest
          return ⟨first.statement :: remaining.statements,remaining.rest,.next first.grammar remaining.grammar⟩
  def statementSyntax (input : ByteArray) : (fuel : Nat) → (tokens : List Lexeme) →
      Option (ParsedStatement input tokens)
    | 0, _ => none
    | fuel + 1, tokens => match tokens with
      | [] => none
      | token :: tail => do
        if conditional : Is input token "if" then
          let opening :: afterOpen := tail | none
          if paren : Is input opening "(" then
            let condition ← expressionSyntax input 4096 1 afterOpen
            match eq : condition.rest with
            | closing :: brace :: afterCondition =>
              if endParen : Is input closing ")" then
                if beginBody : Is input brace "{" then
                  let body ← statementsSyntax input fuel true afterCondition
                  match restEq : body.rest with
                  | endBrace :: remaining =>
                    if endBody : Is input endBrace "}" then
                      return ⟨.ifThen condition.expression body.statements,remaining,
                        .ifThen conditional paren (eq ▸ condition.grammar) endParen beginBody
                          (restEq ▸ body.grammar) endBody⟩
                    else none
                  | [] => none
                else none
              else none
            | _ => none
          else none
        else if returning : Is input token "return" then
          let value ← expressionSyntax input 4096 1 tail
          match eq : value.rest with
          | semicolon :: remaining =>
            if semi : Is input semicolon ";" then
              return ⟨.returnValue value.expression,remaining,.returnValue returning (eq ▸ value.grammar) semi⟩
            else none
          | [] => none
        else plainStatementSyntax input (token :: tail)
end

structure ParsedMethod (input : ByteArray) (function : Function) where
  statements : List SourceStatement
  grammar : StatementsSyntax input false function.body.tokens statements []

def methodSyntax (input : ByteArray) (function : Function) : Option (ParsedMethod input function) := do
  let parsed ← statementsSyntax input 4096 false function.body.tokens
  if complete : parsed.rest = [] then return ⟨parsed.statements,complete ▸ parsed.grammar⟩ else none

/-- Only these bare source spellings resolve to scalar types at this checkpoint.
    Raw cv/ref syntax and nominal/resource types are NOT normalized or inferred. -/
def guardSourceType : GuardType → SourceType
  | .word => .named ["u64".toUTF8]
  | .boolean => .named ["bool".toUTF8]

def GuardEnvironment (fieldDecls formalDecls : List Formal) : Prop :=
  (fieldDecls.map (·.name)).Nodup ∧ (formalDecls.map (·.name)).Nodup ∧
  ∀ formal ∈ formalDecls, formal.name ∉ fieldDecls.map (·.name)
instance (fieldDecls formalDecls : List Formal) : Decidable (GuardEnvironment fieldDecls formalDecls) := by
  unfold GuardEnvironment; infer_instance

/-- Independent source-to-typed-AST relation. Literal bounds and each name's actual
    declaration/index/type are premises; calls are intentionally absent. -/
inductive TypedGuard (fieldDecls formalDecls : List Formal) : SourceExpr → {kind : GuardType} → GuardExpr kind → Prop
  | word : value < 18446744073709551616 → TypedGuard fieldDecls formalDecls (.word value) (.wordLit value)
  | boolean : TypedGuard fieldDecls formalDecls (.boolean value) (.boolLit value)
  | parameter : formalDecls[index]? = some decl → decl.name = name →
      decl.type = guardSourceType kind →
      TypedGuard fieldDecls formalDecls (.name [name]) (.parameter kind name index)
  | field : fieldDecls[index]? = some decl → decl.name = name →
      decl.type = guardSourceType kind →
      TypedGuard fieldDecls formalDecls (.name [name]) (.field kind name index)
  | not : TypedGuard fieldDecls formalDecls inner typed →
      TypedGuard fieldDecls formalDecls (.not inner) (.not typed)
  | subtract : TypedGuard fieldDecls formalDecls left typedLeft → TypedGuard fieldDecls formalDecls right typedRight →
      TypedGuard fieldDecls formalDecls (.binary .subtract left right) (.sub typedLeft typedRight)
  | bitAnd : TypedGuard fieldDecls formalDecls left typedLeft → TypedGuard fieldDecls formalDecls right typedRight →
      TypedGuard fieldDecls formalDecls (.binary .bitAnd left right) (.bitAnd typedLeft typedRight)
  | bitOr : TypedGuard fieldDecls formalDecls left typedLeft → TypedGuard fieldDecls formalDecls right typedRight →
      TypedGuard fieldDecls formalDecls (.binary .bitOr left right) (.bitOr typedLeft typedRight)
  | shift12 : TypedGuard fieldDecls formalDecls left typedLeft →
      TypedGuard fieldDecls formalDecls (.binary .shift left .signed12) (.shift12 typedLeft)
  | compare : TypedGuard fieldDecls formalDecls left typedLeft → TypedGuard fieldDecls formalDecls right typedRight →
      TypedGuard fieldDecls formalDecls (.binary (.compare op) left right) (.compare op typedLeft typedRight)
  | and : TypedGuard fieldDecls formalDecls left typedLeft → TypedGuard fieldDecls formalDecls right typedRight →
      TypedGuard fieldDecls formalDecls (.binary .and left right) (.and typedLeft typedRight)
  | or : TypedGuard fieldDecls formalDecls left typedLeft → TypedGuard fieldDecls formalDecls right typedRight →
      TypedGuard fieldDecls formalDecls (.binary .or left right) (.or typedLeft typedRight)

theorem TypedGuard.cast {fieldDecls formalDecls : List Formal} {source : SourceExpr}
    {a b : GuardType} {expression : GuardExpr a}
    (typing : TypedGuard fieldDecls formalDecls source expression) (same : a = b) :
    TypedGuard fieldDecls formalDecls source (same ▸ expression) := by
  subst b
  exact typing

structure InferredGuard (fieldDecls formalDecls : List Formal) (source : SourceExpr) where
  kind : GuardType
  expression : GuardExpr kind
  typing : TypedGuard fieldDecls formalDecls source expression

structure ScalarBinding (decls : List Formal) (name : ByteArray) where
  kind : GuardType
  index : Nat
  declaration : Formal
  present : decls[index]? = some declaration
  named : declaration.name = name
  scalar : declaration.type = guardSourceType kind

def scalarBinding (decls : List Formal) (name : ByteArray) : Option (ScalarBinding decls name) := do
  let (declaration,index) ← decls.zipIdx.find? fun entry => entry.1.name == name
  if present : decls[index]? = some declaration then
    if named : declaration.name = name then
      if word : declaration.type = guardSourceType .word then return ⟨.word,index,declaration,present,named,word⟩
      else if boolean : declaration.type = guardSourceType .boolean then return ⟨.boolean,index,declaration,present,named,boolean⟩
      else none
    else none
  else none

def inferGuard (fieldDecls formalDecls : List Formal) : (source : SourceExpr) → Option (InferredGuard fieldDecls formalDecls source)
  | .signed12 => none
  | .word value => if bound : value < 18446744073709551616 then some ⟨.word,.wordLit value,.word bound⟩ else none
  | .boolean value => some ⟨.boolean,.boolLit value,.boolean⟩
  | .name [name] =>
    match scalarBinding formalDecls name with
    | some binding => some ⟨binding.kind,.parameter binding.kind name binding.index,
        .parameter binding.present binding.named binding.scalar⟩
    | none => do
      let binding ← scalarBinding fieldDecls name
      return ⟨binding.kind,.field binding.kind name binding.index,.field binding.present binding.named binding.scalar⟩
  | .name _ | .call _ _ => none
  | .not inner => do
    let typed ← inferGuard fieldDecls formalDecls inner
    match eq : typed.kind with
    | .word => none
    | .boolean => return ⟨.boolean,.not (eq ▸ typed.expression),.not (typed.typing.cast eq)⟩
  | .binary .shift left .signed12 => do
    let l ← inferGuard fieldDecls formalDecls left
    match leq : l.kind with
    | .word => return ⟨.word,.shift12 (leq ▸ l.expression),.shift12 (l.typing.cast leq)⟩
    | _ => none
  | .binary op left right => do
    let l ← inferGuard fieldDecls formalDecls left
    let r ← inferGuard fieldDecls formalDecls right
    match op with
    | .subtract =>
      match leq : l.kind, req : r.kind with
      | .word, .word => return ⟨.word,.sub (leq ▸ l.expression) (req ▸ r.expression),
          .subtract (l.typing.cast leq) (r.typing.cast req)⟩
      | _, _ => none
    | .shift => none
    | .bitAnd =>
      match leq : l.kind, req : r.kind with
      | .word, .word => return ⟨.word,.bitAnd (leq ▸ l.expression) (req ▸ r.expression),
          .bitAnd (l.typing.cast leq) (r.typing.cast req)⟩
      | _, _ => none
    | .bitOr =>
      match leq : l.kind, req : r.kind with
      | .word, .word => return ⟨.word,.bitOr (leq ▸ l.expression) (req ▸ r.expression),
          .bitOr (l.typing.cast leq) (r.typing.cast req)⟩
      | _, _ => none
    | .compare op =>
      match leq : l.kind, req : r.kind with
      | .word, .word => return ⟨.boolean,.compare op (leq ▸ l.expression) (req ▸ r.expression),
          .compare (l.typing.cast leq) (r.typing.cast req)⟩
      | _, _ => none
    | .and =>
      match leq : l.kind, req : r.kind with
      | .boolean, .boolean => return ⟨.boolean,.and (leq ▸ l.expression) (req ▸ r.expression),
          .and (l.typing.cast leq) (r.typing.cast req)⟩
      | _, _ => none
    | .or =>
      match leq : l.kind, req : r.kind with
      | .boolean, .boolean => return ⟨.boolean,.or (leq ▸ l.expression) (req ▸ r.expression),
          .or (l.typing.cast leq) (r.typing.cast req)⟩
      | _, _ => none

/-- Whole body syntax, pure typed actual leading guard, and actual next statement.
    Tail statements are syntactically parsed but carry no typing/effect judgment. -/
structure GuardMethod (input : ByteArray) (function : Function) (fieldDecls : List Formal) where
  parsed : ParsedMethod input function
  environment : GuardEnvironment fieldDecls function.formals
  resultBool : function.result = guardSourceType .boolean
  sourceGuard : SourceExpr
  next : SourceStatement
  tail : List SourceStatement
  leading : parsed.statements = .ifThen sourceGuard [.returnValue (.boolean false)] :: next :: tail
  guard : GuardExpr .boolean
  typing : TypedGuard fieldDecls function.formals sourceGuard guard

def guardMethod (input : ByteArray) (function : Function) (fieldDecls : List Formal) :
    Option (GuardMethod input function fieldDecls) := do
  let parsed ← methodSyntax input function
  if environment : GuardEnvironment fieldDecls function.formals then
    if resultBool : function.result = guardSourceType .boolean then
      match leading : parsed.statements with
      | .ifThen condition [.returnValue (.boolean false)] :: next :: tail =>
        let typed ← inferGuard fieldDecls function.formals condition
        match eq : typed.kind with
        | .boolean => return ⟨parsed,environment,resultBool,condition,next,tail,leading,
            eq ▸ typed.expression,typed.typing.cast eq⟩
        | .word => none
      | _ => none
    else none
  else none

theorem method_syntax_sound (input : ByteArray) (function : Function) (result : ParsedMethod input function)
    (_accepted : methodSyntax input function = some result) :
    StatementsSyntax input false function.body.tokens result.statements [] := result.grammar

theorem guard_method_sound (input : ByteArray) (function : Function) (fieldDecls : List Formal)
    (result : GuardMethod input function fieldDecls) (_accepted : guardMethod input function fieldDecls = some result) :
    StatementsSyntax input false function.body.tokens result.parsed.statements [] ∧
    GuardEnvironment fieldDecls function.formals ∧
    result.parsed.statements = .ifThen result.sourceGuard [.returnValue (.boolean false)] :: result.next :: result.tail ∧
    TypedGuard fieldDecls function.formals result.sourceGuard result.guard :=
  ⟨result.parsed.grammar,result.environment,result.leading,result.typing⟩

/-- Reusable public composition: no independently supplied fields, function tokens or source bytes. -/
structure SelectedGuard (files : List SourceFile) (root module path : Name) (member : ByteArray) where
  selected : CheckedSelection files root module path member
  method : GuardMethod selected.selected.file.file.bytes selected.selected.method.function
    (fields selected.selected.classDecl.members)

def selectGuard (files : List SourceFile) (root module path : Name) (member : ByteArray) :
    Option (SelectedGuard files root module path member) := do
  let selected ← checkedSelection files root module path member
  let method ← guardMethod selected.selected.file.file.bytes selected.selected.method.function
    (fields selected.selected.classDecl.members)
  return ⟨selected,method⟩

theorem selected_guard_sound (files : List SourceFile) (root module path : Name) (member : ByteArray)
    (result : SelectedGuard files root module path member)
    (_accepted : selectGuard files root module path member = some result) :
    GraphReady files root ∧
    StatementsSyntax result.selected.selected.file.file.bytes false result.selected.selected.method.function.body.tokens
      result.method.parsed.statements [] ∧
    GuardEnvironment (fields result.selected.selected.classDecl.members) result.selected.selected.method.function.formals ∧
    result.method.parsed.statements = .ifThen result.method.sourceGuard [.returnValue (.boolean false)] ::
      result.method.next :: result.method.tail ∧
    TypedGuard (fields result.selected.selected.classDecl.members) result.selected.selected.method.function.formals
      result.method.sourceGuard result.method.guard :=
  ⟨result.selected.graph,result.method.parsed.grammar,result.method.environment,result.method.leading,result.method.typing⟩

end Aurora.SourceBinding
