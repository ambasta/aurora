import SourceBinding.CallIdentity
namespace Aurora.SourceBinding
open Aurora.Publication

/-- Ordered pure arguments. No new arithmetic or effectful expression language. -/
inductive CallArguments : List GuardType → Type where
  | nil : CallArguments []
  | cons : GuardExpr kind → CallArguments kinds → CallArguments (kind :: kinds)

inductive TypedArguments (fields formals : List Formal) :
    List SourceExpr → {kinds : List GuardType} → CallArguments kinds → Prop
  | nil : TypedArguments fields formals [] .nil
  | cons : TypedGuard fields formals source value → TypedArguments fields formals sources values →
      TypedArguments fields formals (source :: sources) (.cons value values)

structure BoundArguments (fields formals : List Formal) (kinds : List GuardType) (sources : List SourceExpr) where
  values : CallArguments kinds
  typing : TypedArguments fields formals sources values

def inferArguments (fields formals : List Formal) : (kinds : List GuardType) → (sources : List SourceExpr) →
    Option (BoundArguments fields formals kinds sources)
  | [], [] => some ⟨.nil,.nil⟩
  | kind :: kinds, source :: sources => do
    let value ← inferGuard fields formals source
    if same : value.kind = kind then
      let rest ← inferArguments fields formals kinds sources
      return ⟨.cons (same ▸ value.expression) rest.values,.cons (value.typing.cast same) rest.typing⟩
    else none
  | _, _ => none

/-- Resource invocation here means the exact single resource-call argument of
    builtin::require; arbitrary nested calls are not part of this profile. -/
inductive TypedInvocation where
  | ordinary (target : ScalarOrdinary) (arguments : CallArguments target.parameters)
  | resourceAssert (target : ResourceDescriptor) (arguments : CallArguments target.parameters)
inductive CallPiece where
  | localBody (body : EffectBody)
  | invoke (call : TypedInvocation)

/-- Existing source statements are reused verbatim, not reconstructed from IR. -/
inductive TypedCallStatement (t : Tables) (caller : Int) (module path : Name)
    (members : List Declaration) (formals : List Formal) (result : GuardType) :
    SourceStatement → CallPiece → Prop
  | localBody : TypedStatement (fields members) formals result statement body →
      TypedCallStatement t caller module path members formals result statement (.localBody body)
  | ordinary : OrdinaryCallIdentity t module path members target → target.member = name →
      (∀ formal ∈ formals, formal.name ≠ name) →
      TypedArguments (fields members) formals sources arguments →
      TypedCallStatement t caller module path members formals result
        (.call (.named [name]) sources) (.invoke (.ordinary target arguments))
  | resourceAssert : ResourceCallIdentity t caller members target →
      target.fieldName = field → target.sourceMethod = method → target.result = .boolean →
      TypedArguments (fields members) formals sources arguments →
      TypedCallStatement t caller module path members formals result
        (.call (.named ["builtin".toUTF8,"require".toUTF8]) [.call (.receiver field method) sources])
        (.invoke (.resourceAssert target arguments))

structure BoundCallStatement (t : Tables) (caller : Int) (module path : Name)
    (members : List Declaration) (formals : List Formal) (result : GuardType) (source : SourceStatement) where
  piece : CallPiece
  typing : TypedCallStatement t caller module path members formals result source piece

def inferCallStatement (t : Tables) (caller : Int) (module path : Name)
    (members : List Declaration) (formals : List Formal) (result : GuardType) (source : SourceStatement) :
    Option (BoundCallStatement t caller module path members formals result source) := do
  match inferStatement (fields members) formals result 4096 source with
  | some pure => return ⟨.localBody pure.body,.localBody pure.typing⟩
  | none =>
    match source with
    | .call (.named [name]) sources => do
      if unshadowed : ∀ formal ∈ formals, formal.name ≠ name then
        let target ← bindOrdinaryCall t module path members name
        let args ← inferArguments (fields members) formals target.target.parameters sources
        return ⟨.invoke (.ordinary target.target args.values),
          .ordinary target.identity target.named unshadowed args.typing⟩
      else none
    | .call (.named names) [.call (.receiver field method) sources] => do
      if intrinsic : names = ["builtin".toUTF8,"require".toUTF8] then
        let target ← bindResourceCall t caller members field method
        if boolean : target.target.result = .boolean then
          let args ← inferArguments (fields members) formals target.target.parameters sources
          return ⟨.invoke (.resourceAssert target.target args.values),by
            subst names
            exact .resourceAssert target.identity target.fieldNamed target.methodNamed boolean args.typing⟩
        else none
      else none
    | _ => none

/-- Pointwise ordered relation (Forall₂), including every original statement. -/
inductive TypedCallStatements (t : Tables) (caller : Int) (module path : Name)
    (members : List Declaration) (formals : List Formal) (result : GuardType) :
    List SourceStatement → List CallPiece → Prop
  | nil : TypedCallStatements t caller module path members formals result [] []
  | cons : TypedCallStatement t caller module path members formals result source piece →
      TypedCallStatements t caller module path members formals result sources pieces →
      TypedCallStatements t caller module path members formals result (source :: sources) (piece :: pieces)
structure BoundCallStatements (t : Tables) (caller : Int) (module path : Name)
    (members : List Declaration) (formals : List Formal) (result : GuardType) (source : List SourceStatement) where
  pieces : List CallPiece
  typing : TypedCallStatements t caller module path members formals result source pieces

def inferCallStatements (t : Tables) (caller : Int) (module path : Name)
    (members : List Declaration) (formals : List Formal) (result : GuardType) :
    (sources : List SourceStatement) →
    Option (BoundCallStatements t caller module path members formals result sources)
  | [] => some ⟨[],.nil⟩
  | source :: sources => do
    let first ← inferCallStatement t caller module path members formals result source
    let rest ← inferCallStatements t caller module path members formals result sources
    return ⟨first.piece :: rest.pieces,.cons first.typing rest.typing⟩

/-- No normal fallthrough, not guaranteed successful return or external response. -/
inductive CallReturns : List CallPiece → Prop
  | here : DefinitelyReturns body → CallReturns (.localBody body :: rest)
  | later : CallReturns rest → CallReturns (first :: rest)
def checkCallReturn : (pieces : List CallPiece) → Option { _u : Unit // CallReturns pieces }
  | [] => none
  | .localBody body :: rest =>
    match checkReturn body with
    | some found => some ⟨(),.here found.returns⟩
    | none => do return ⟨(),.later (← checkCallReturn rest).property⟩
  | .invoke _ :: rest => do return ⟨(),.later (← checkCallReturn rest).property⟩

structure CallMethod (t : Tables) (caller : Int) (module path : Name) (members : List Declaration)
    (input : ByteArray) (function : Function) where
  parsed : ParsedMethod input function
  environment : GuardEnvironment (fields members) function.formals
  mutable : function.mode = .ordinary
  kind : GuardType
  resultType : function.result = guardSourceType kind
  pieces : List CallPiece
  typing : TypedCallStatements t caller module path members function.formals kind parsed.statements pieces
  returns : CallReturns pieces

def callMethod (t : Tables) (caller : Int) (module path : Name) (members : List Declaration)
    (input : ByteArray) (function : Function) : Option (CallMethod t caller module path members input function) := do
  let parsed ← methodSyntax input function
  if environment : GuardEnvironment (fields members) function.formals then
    if mutable : function.mode = .ordinary then
      let kind ← sourceScalarKind function.result
      if resultType : function.result = guardSourceType kind then
        let pieces ← inferCallStatements t caller module path members function.formals kind parsed.statements
        let returns ← checkCallReturn pieces.pieces
        return ⟨parsed,environment,mutable,kind,resultType,pieces.pieces,pieces.typing,returns.property⟩
      else none
    else none
  else none

structure SelectedCallBody (files : List SourceFile) (root module path : Name) (member : ByteArray)
    (t : Tables) (caller : Int) where
  selected : CheckedSelection files root module path member
  method : CallMethod t caller module path selected.selected.classDecl.members
    selected.selected.file.file.bytes selected.selected.method.function

theorem call_method_sound (checked : CallMethod t caller module path members input function) :
    StatementsSyntax input false function.body.tokens checked.parsed.statements [] ∧
    TypedCallStatements t caller module path members function.formals checked.kind checked.parsed.statements
      checked.pieces ∧ CallReturns checked.pieces :=
  ⟨checked.parsed.grammar,checked.typing,checked.returns⟩
end Aurora.SourceBinding
