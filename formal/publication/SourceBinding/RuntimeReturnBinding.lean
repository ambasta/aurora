import SourceBinding.RuntimeReturnProof
namespace Aurora.SourceBinding
open Aurora.Publication

/-- This context is derived from the selected declaration, not supplied by a
    caller. The supported complete body has no local declarations. -/
def runtimeReturnContext (identified : IdentifiedRuntimeFree t files root module path name) : RuntimeExprContext :=
  ⟨identified.selected.scope.members,module,path,
    identified.selected.function.function.formals,[]⟩

structure RuntimeReturnCertificate (identified : IdentifiedRuntimeFree t files root module path name) where
  raw : SourceExpr
  source : identified.details.lexical.parsed.statements = [.returnValue raw]
  noLocals : identified.details.lexical.lexical.declaredItems = []
  valid : RuntimeContextValid (runtimeReturnContext identified)
  parameters : CheckedRuntimeSignature t identified.selected.scope.members module path
    ((atRow t.callables identified.id).integer 4 + 1)
    (identified.selected.function.function.formals.map (·.type))
  resultKind : RuntimeType
  resultSource : RuntimeSourceType identified.selected.scope.members module path
    identified.selected.function.function.result resultKind
  resultIdentity : RuntimeTypeIdentity t ((atRow t.callables identified.id).integer 4) resultKind
  entry : RuntimeEntryCode (canonicalEffects t identified.id) parameters.kinds
  stop : Nat
  expression : RuntimeExpressionCode (canonicalEffects t identified.id)
    (runtimeReturnContext identified) raw resultKind parameters.kinds.length stop
  returns : canonicalEffects t identified.id stop = some (.pure .ret)
  complete : stop + 1 = (functionCode t identified.id).size

def checkRuntimeReturn (identified : IdentifiedRuntimeFree t files root module path name) :
    Option (RuntimeReturnCertificate identified) := do
  match shape : identified.details.lexical.parsed.statements with
  | [.returnValue raw] =>
    if noLocals : identified.details.lexical.lexical.declaredItems = [] then
      let context := runtimeReturnContext identified
      let valid ← checkRuntimeContext context
      let parameters ← checkRuntimeSignature t identified.selected.scope.members module path
        ((atRow t.callables identified.id).integer 4 + 1)
        (identified.selected.function.function.formals.map (·.type))
      let result ← resolveRuntimeType identified.selected.scope.members module path
        identified.selected.function.function.result
      if resultIdentity : RuntimeTypeIdentity t ((atRow t.callables identified.id).integer 4) result.kind then
        if entry : RuntimeEntryCode (canonicalEffects t identified.id) parameters.kinds then
          let parsed ← checkRuntimeExpressionCode (canonicalEffects t identified.id) context 4096 raw parameters.kinds.length
          if same : parsed.kind = result.kind then
            if returns : canonicalEffects t identified.id parsed.stop = some (.pure .ret) then
              if complete : parsed.stop + 1 = (functionCode t identified.id).size then
                return ⟨raw,shape,noLocals,valid.property,parameters,result.kind,result.typing,
                  resultIdentity,entry,parsed.stop,parsed.grammar.cast same,returns,complete⟩
              else none
            else none
          else none
        else none
      else none
    else none
  | _ => none

/-- Full actual entry/body/return, including expression faults such as overflow. Initial arguments are runtime-typed;
    no body success, expression value or formal metadata oracle is assumed. -/
theorem RuntimeReturnCertificate.executes {identified : IdentifiedRuntimeFree t files root module path name} (checked : RuntimeReturnCertificate identified)
    (base : Machine) (arguments : RuntimeEntryArguments checked.parameters.kinds base.arguments) :
    ∃ outcome result,
      RuntimeEvaluates (runtimeReturnContext identified)
        (formalRuntimeLocals checked.parameters.kinds base) checked.raw checked.resultKind outcome ∧
      EffectRuns (canonicalEffects t identified.id) (preparedEntry base runtimeParameterSlot 0) [] result ∧
      RuntimeTerminal (preparedEntry base runtimeParameterSlot checked.parameters.kinds.length) outcome result := by
  exact runtime_entry_expression_returned checked.valid checked.parameters.grammar rfl
    checked.entry checked.expression checked.returns base arguments

/-- Every actual terminal run has the constructed source outcome and no stores.
    This is deterministic-machine reflection, not general source determinism. -/
theorem RuntimeReturnCertificate.terminal_correspondence
    {identified : IdentifiedRuntimeFree t files root module path name}
    (checked : RuntimeReturnCertificate identified) (base : Machine)
    (arguments : RuntimeEntryArguments checked.parameters.kinds base.arguments)
    (actual : EffectRuns (canonicalEffects t identified.id)
      (preparedEntry base runtimeParameterSlot 0) events result)
    (terminal : EffectTerminal result) :
    ∃ outcome, RuntimeEvaluates (runtimeReturnContext identified)
      (formalRuntimeLocals checked.parameters.kinds base) checked.raw checked.resultKind outcome ∧
      events = [] ∧ RuntimeTerminal
        (preparedEntry base runtimeParameterSlot checked.parameters.kinds.length) outcome result := by
  obtain ⟨outcome,expected,evaluated,run,related⟩ := checked.executes base arguments
  have ends : EffectTerminal expected := by
    cases expected with
    | next state => exact False.elim (related.terminal state rfl)
    | returned _ _ => trivial
    | trap _ _ => trivial
  obtain ⟨sameEvents,sameResult⟩ := actual.terminal_unique terminal run ends
  subst result
  exact ⟨outcome,evaluated,sameEvents,related⟩

structure RuntimeReturnBinding (input : ByteArray) (files : List SourceFile)
    (root module path : Name) (name : ByteArray) where
  bound : RuntimeFreeBinding input files root module path name
  body : RuntimeReturnCertificate bound.checked

def bindRuntimeReturn (files : List SourceFile) (root module path : Name) (name : ByteArray)
    (input : ByteArray) : Option (RuntimeReturnBinding input files root module path name) := do
  let bound ← bindRuntimeFree files root module path name input
  let body ← checkRuntimeReturn bound.checked
  return ⟨bound,body⟩

end Aurora.SourceBinding
