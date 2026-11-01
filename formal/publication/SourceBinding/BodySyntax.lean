import SourceBinding.MethodSyntax
namespace Aurora.SourceBinding

/-- Bounded stateful source AST. This layer assigns syntax/types only; operational
    behavior, intrinsic adequacy and IR correspondence are separate obligations. -/
inductive EffectBody where
  | skip
  | seq (first rest : EffectBody)
  | branch (condition : GuardExpr .boolean) (body : EffectBody)
  | assign (kind : GuardType) (ordinal : Nat) (value : GuardExpr kind)
  | require (condition : GuardExpr .boolean)
  | returnValue (kind : GuardType) (value : GuardExpr kind)

mutual
  /-- Every assignment resolves the actual scalar field declaration. Every RHS,
      condition and return is in the pure TypedGuard fragment, excluding calls. -/
  inductive TypedStatement (fieldDecls formalDecls : List Formal) (result : GuardType) :
      SourceStatement → EffectBody → Prop
    | branch : TypedGuard fieldDecls formalDecls condition typedCondition →
        TypedStatements fieldDecls formalDecls result statements body →
        TypedStatement fieldDecls formalDecls result (.ifThen condition statements) (.branch typedCondition body)
    | assign : fieldDecls[ordinal]? = some decl → decl.name = name →
        decl.type = guardSourceType kind → TypedGuard fieldDecls formalDecls value typedValue →
        TypedStatement fieldDecls formalDecls result (.assign name value) (.assign kind ordinal typedValue)
    | require : TypedGuard fieldDecls formalDecls condition typedCondition →
        TypedStatement fieldDecls formalDecls result
          (.call (.named ["builtin".toUTF8,"require".toUTF8]) [condition]) (.require typedCondition)
    | returnValue : TypedGuard fieldDecls formalDecls value typedValue →
        TypedStatement fieldDecls formalDecls result (.returnValue value) (.returnValue result typedValue)
  /-- Source list order is preserved exactly, including a trailing skip. -/
  inductive TypedStatements (fieldDecls formalDecls : List Formal) (result : GuardType) :
      List SourceStatement → EffectBody → Prop
    | nil : TypedStatements fieldDecls formalDecls result [] .skip
    | cons : TypedStatement fieldDecls formalDecls result statement first →
        TypedStatements fieldDecls formalDecls result statements rest →
        TypedStatements fieldDecls formalDecls result (statement :: statements) (.seq first rest)
end

structure InferredStatement (fieldDecls formalDecls : List Formal) (result : GuardType) (source : SourceStatement) where
  body : EffectBody
  typing : TypedStatement fieldDecls formalDecls result source body
structure InferredStatements (fieldDecls formalDecls : List Formal) (result : GuardType) (source : List SourceStatement) where
  body : EffectBody
  typing : TypedStatements fieldDecls formalDecls result source body

mutual
  def inferStatement (fieldDecls formalDecls : List Formal) (result : GuardType) :
      Nat → (source : SourceStatement) → Option (InferredStatement fieldDecls formalDecls result source)
    | 0, _ => none
    | fuel + 1, .ifThen condition statements => do
      let typed ← inferGuard fieldDecls formalDecls condition
      match eq : typed.kind with
      | .word => none
      | .boolean =>
        let body ← inferStatements fieldDecls formalDecls result fuel statements
        return ⟨.branch (eq ▸ typed.expression) body.body,.branch (typed.typing.cast eq) body.typing⟩
    | _ + 1, .assign name value => do
      let field ← scalarBinding fieldDecls name
      let typed ← inferGuard fieldDecls formalDecls value
      if same : typed.kind = field.kind then
        return ⟨.assign field.kind field.index (same ▸ typed.expression),
          .assign field.present field.named field.scalar (typed.typing.cast same)⟩
      else none
    | _ + 1, .call callee arguments =>
      match calleeEq : callee, argumentsEq : arguments with
      | .named name, [condition] =>
        if intrinsic : name = ["builtin".toUTF8,"require".toUTF8] then do
          let typed ← inferGuard fieldDecls formalDecls condition
          match eq : typed.kind with
          | .word => none
          | .boolean =>
            return ⟨.require (eq ▸ typed.expression),by
              subst name
              exact .require (typed.typing.cast eq)⟩
        else none
      | _, _ => none
    | _ + 1, .returnValue value => do
      let typed ← inferGuard fieldDecls formalDecls value
      if same : typed.kind = result then
        return ⟨.returnValue result (same ▸ typed.expression),.returnValue (typed.typing.cast same)⟩
      else none
  def inferStatements (fieldDecls formalDecls : List Formal) (result : GuardType) :
      Nat → (source : List SourceStatement) → Option (InferredStatements fieldDecls formalDecls result source)
    | 0, _ => none
    | _ + 1, [] => some ⟨.skip,.nil⟩
    | fuel + 1, first :: rest => do
      let head ← inferStatement fieldDecls formalDecls result fuel first
      let tail ← inferStatements fieldDecls formalDecls result fuel rest
      return ⟨.seq head.body tail.body,.cons head.typing tail.typing⟩
end

/-- Structural definite return: an unconditionally reached sequence component
    returns. A one-armed conditional alone is never deemed definitely returning.
    Trap/failure/termination semantics are not asserted by this predicate. -/
inductive DefinitelyReturns : EffectBody → Prop
  | returnValue : DefinitelyReturns (.returnValue kind value)
  | first : DefinitelyReturns first → DefinitelyReturns (.seq first rest)
  | rest : DefinitelyReturns rest → DefinitelyReturns (.seq first rest)

structure CheckedReturn (body : EffectBody) : Type where
  returns : DefinitelyReturns body

def checkReturn : (body : EffectBody) → Option (CheckedReturn body)
  | .returnValue _ _ => some ⟨.returnValue⟩
  | .seq first rest =>
    match checkReturn first with
    | some checked => some ⟨.first checked.returns⟩
    | none => do return ⟨.rest (← checkReturn rest).returns⟩
  | _ => none

/-- Exact complete method syntax plus a typed body and finite declaration context.
    Intrinsic require is an explicit profile convention under graph no-shadowing,
    not a proof of general Aurora name resolution or native builtin behavior. -/
structure BodyMethod (input : ByteArray) (function : Function) (fieldDecls : List Formal) where
  parsed : ParsedMethod input function
  environment : GuardEnvironment fieldDecls function.formals
  kind : GuardType
  resultType : function.result = guardSourceType kind
  body : EffectBody
  typing : TypedStatements fieldDecls function.formals kind parsed.statements body
  returns : DefinitelyReturns body

def bodyMethod (input : ByteArray) (function : Function) (fieldDecls : List Formal) :
    Option (BodyMethod input function fieldDecls) := do
  let parsed ← methodSyntax input function
  if environment : GuardEnvironment fieldDecls function.formals then
    if word : function.result = guardSourceType .word then
      let typed ← inferStatements fieldDecls function.formals .word 4096 parsed.statements
      let returns ← checkReturn typed.body
      return ⟨parsed,environment,.word,word,typed.body,typed.typing,returns.returns⟩
    else if boolean : function.result = guardSourceType .boolean then
      let typed ← inferStatements fieldDecls function.formals .boolean 4096 parsed.statements
      let returns ← checkReturn typed.body
      return ⟨parsed,environment,.boolean,boolean,typed.body,typed.typing,returns.returns⟩
    else none
  else none

structure SelectedBody (files : List SourceFile) (root module path : Name) (member : ByteArray) where
  selected : CheckedSelection files root module path member
  method : BodyMethod selected.selected.file.file.bytes selected.selected.method.function
    (fields selected.selected.classDecl.members)

def selectBody (files : List SourceFile) (root module path : Name) (member : ByteArray) :
    Option (SelectedBody files root module path member) := do
  let selected ← checkedSelection files root module path member
  let method ← bodyMethod selected.selected.file.file.bytes selected.selected.method.function
    (fields selected.selected.classDecl.members)
  return ⟨selected,method⟩

theorem body_method_sound (input : ByteArray) (function : Function) (fieldDecls : List Formal)
    (result : BodyMethod input function fieldDecls) (_accepted : bodyMethod input function fieldDecls = some result) :
    StatementsSyntax input false function.body.tokens result.parsed.statements [] ∧
    GuardEnvironment fieldDecls function.formals ∧ function.result = guardSourceType result.kind ∧
    TypedStatements fieldDecls function.formals result.kind result.parsed.statements result.body ∧
    DefinitelyReturns result.body :=
  ⟨result.parsed.grammar,result.environment,result.resultType,result.typing,result.returns⟩

theorem selected_body_sound (files : List SourceFile) (root module path : Name) (member : ByteArray)
    (result : SelectedBody files root module path member)
    (_accepted : selectBody files root module path member = some result) :
    GraphReady files root ∧
    StatementsSyntax result.selected.selected.file.file.bytes false result.selected.selected.method.function.body.tokens
      result.method.parsed.statements [] ∧
    GuardEnvironment (fields result.selected.selected.classDecl.members) result.selected.selected.method.function.formals ∧
    TypedStatements (fields result.selected.selected.classDecl.members) result.selected.selected.method.function.formals
      result.method.kind result.method.parsed.statements result.method.body ∧ DefinitelyReturns result.method.body :=
  ⟨result.selected.graph,result.method.parsed.grammar,result.method.environment,result.method.typing,result.method.returns⟩

end Aurora.SourceBinding
