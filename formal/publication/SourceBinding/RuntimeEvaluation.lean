import SourceBinding.RuntimeExpressions
import SourceBinding.RuntimeSourceLeaf
import SourceBinding.RuntimeFormals
namespace Aurora.SourceBinding

def SourceLocal.runtimeDeclaration (binding : SourceLocal) : RuntimeLocalDecl :=
  ⟨binding.kind,binding.mutable,binding.scope⟩

def RuntimeLocals.readBound (state : RuntimeLocals) (binding : SourceLocal) : Outcome Value :=
  if state.declarations binding.slot = some binding.runtimeDeclaration then
    state.read binding.slot
  else .trap .type

/-- Source-visible calls are keyed by source module/namespace/name. No IR id,
    target machine state or supplied callee result appears in an event. -/
inductive RuntimeSourceEvent where
  | invoke (key : RuntimeSourceKey) (arguments : List Value)
  | returned (key : RuntimeSourceKey) (value : Value)
  deriving BEq, DecidableEq

/- ONE source judgement on the existing raw AST. The environment contains actual
    parsed source functions, not IR outcomes or successful-call summaries.
    Arguments are evaluated once in order. A fault emits no fictitious return. -/
mutual
  inductive RuntimeEvaluatesWith (functions : List RuntimeSourceLeaf) :
      RuntimeExprContext → RuntimeLocals → SourceExpr → RuntimeType → Outcome Value →
      List RuntimeSourceEvent → Prop
    | word : RuntimeEvaluatesWith functions context state (.word value) (.scalar .word)
        (readScalar .word (some (.word value))) []
    | boolean : RuntimeEvaluatesWith functions context state (.boolean value) (.scalar .boolean)
        (.value (.boolean value)) []
    | readVariable : RuntimeVariableBinding context name binding →
        RuntimeEvaluatesWith functions context state (.name [name]) binding.kind (state.readBound binding) []
    | enumValue : RuntimeEnumValue context name identity ordinal →
        RuntimeEvaluatesWith functions context state (.name name) (.nominal identity)
          (readRuntime (.nominal identity) (some (.nominal identity.name ordinal))) []
    | not : RuntimeEvaluatesWith functions context state inner (.scalar .boolean) outcome events →
        RuntimeEvaluatesWith functions context state (.not inner) (.scalar .boolean) (outcome.then notValue) events
    | wordBinaryFault : RuntimeWordOperator operator primitive result →
        RuntimeEvaluatesWith functions context state left (.scalar .word) (.trap fault) events →
        RuntimeEvaluatesWith functions context state (.binary operator left right) (.scalar result) (.trap fault) events
    | wordBinary : RuntimeWordOperator operator primitive result →
        RuntimeEvaluatesWith functions context state left (.scalar .word) (.value value) leftEvents →
        RuntimeEvaluatesWith functions context state right (.scalar .word) outcome rightEvents →
        RuntimeEvaluatesWith functions context state (.binary operator left right) (.scalar result)
          (outcome.then (binaryValue primitive value)) (leftEvents ++ rightEvents)
    | enumCompareFault {equal : Bool} :
        RuntimeEvaluatesWith functions context state left (.nominal identity) (.trap fault) events →
        RuntimeEvaluatesWith functions context state (.binary (.compare (if equal then .eq else .ne)) left right)
          (.scalar .boolean) (.trap fault) events
    | enumCompare {equal : Bool} :
        RuntimeEvaluatesWith functions context state left (.nominal identity) (.value value) leftEvents →
        RuntimeEvaluatesWith functions context state right (.nominal identity) outcome rightEvents →
        RuntimeEvaluatesWith functions context state (.binary (.compare (if equal then .eq else .ne)) left right)
          (.scalar .boolean) (outcome.then (compareNominal identity equal value)) (leftEvents ++ rightEvents)
    | shiftLeft : RuntimeEvaluatesWith functions context state left (.scalar .word) outcome events → SourceShiftCount right count →
        RuntimeEvaluatesWith functions context state (.binary .shift left right) (.scalar .word)
          (outcome.then fun value => binaryValue .leftShift value count.runtimeValue) events
    | shiftRight : RuntimeEvaluatesWith functions context state left (.scalar .word) outcome events → SourceShiftCount right count →
        RuntimeEvaluatesWith functions context state (.binary .rightShift left right) (.scalar .word)
          (outcome.then fun value => binaryValue .rightShift value count.runtimeValue) events
    | andFault : RuntimeEvaluatesWith functions context state left (.scalar .boolean) (.trap fault) events →
        RuntimeEvaluatesWith functions context state (.binary .and left right) (.scalar .boolean) (.trap fault) events
    | andStop : RuntimeEvaluatesWith functions context state left (.scalar .boolean) (.value (.boolean false)) events →
        RuntimeEvaluatesWith functions context state (.binary .and left right) (.scalar .boolean) (.value (.boolean false)) events
    | andContinue : RuntimeEvaluatesWith functions context state left (.scalar .boolean) (.value (.boolean true)) leftEvents →
        RuntimeEvaluatesWith functions context state right (.scalar .boolean) outcome rightEvents →
        RuntimeEvaluatesWith functions context state (.binary .and left right) (.scalar .boolean) outcome (leftEvents ++ rightEvents)
    | orFault : RuntimeEvaluatesWith functions context state left (.scalar .boolean) (.trap fault) events →
        RuntimeEvaluatesWith functions context state (.binary .or left right) (.scalar .boolean) (.trap fault) events
    | orStop : RuntimeEvaluatesWith functions context state left (.scalar .boolean) (.value (.boolean true)) events →
        RuntimeEvaluatesWith functions context state (.binary .or left right) (.scalar .boolean) (.value (.boolean true)) events
    | orContinue : RuntimeEvaluatesWith functions context state left (.scalar .boolean) (.value (.boolean false)) leftEvents →
        RuntimeEvaluatesWith functions context state right (.scalar .boolean) outcome rightEvents →
        RuntimeEvaluatesWith functions context state (.binary .or left right) (.scalar .boolean) outcome (leftEvents ++ rightEvents)
    | callArgumentsFault : leaf ∈ functions → leaf.Resolves context name →
        RuntimeArgumentsEvaluateWith functions context state sources leaf.parameters (.trap fault) events →
        RuntimeEvaluatesWith functions context state (.call (.named name) sources) leaf.result (.trap fault) events
    | callValue : leaf ∈ functions → leaf.Resolves context name →
        RuntimeArgumentsEvaluateWith functions context state sources leaf.parameters (.value values) argumentEvents →
        RuntimeEvaluatesWith functions leaf.context (formalSourceLocals leaf.parameters (fun index => values[index]?))
          leaf.raw leaf.result (.value value) bodyEvents →
        RuntimeEvaluatesWith functions context state (.call (.named name) sources) leaf.result (.value value)
          (argumentEvents ++ [.invoke leaf.key values] ++ bodyEvents ++ [.returned leaf.key value])
    | callFault : leaf ∈ functions → leaf.Resolves context name →
        RuntimeArgumentsEvaluateWith functions context state sources leaf.parameters (.value values) argumentEvents →
        RuntimeEvaluatesWith functions leaf.context (formalSourceLocals leaf.parameters (fun index => values[index]?))
          leaf.raw leaf.result (.trap fault) bodyEvents →
        RuntimeEvaluatesWith functions context state (.call (.named name) sources) leaf.result (.trap fault)
          (argumentEvents ++ [.invoke leaf.key values] ++ bodyEvents)

  inductive RuntimeArgumentsEvaluateWith (functions : List RuntimeSourceLeaf) :
      RuntimeExprContext → RuntimeLocals → List SourceExpr → List RuntimeType →
      Outcome (List Value) → List RuntimeSourceEvent → Prop
    | nil : RuntimeArgumentsEvaluateWith functions context state [] [] (.value []) []
    | fault : RuntimeEvaluatesWith functions context state first kind (.trap fault) events →
        RuntimeArgumentsEvaluateWith functions context state (first :: rest) (kind :: kinds) (.trap fault) events
    | cons : RuntimeEvaluatesWith functions context state first kind (.value value) firstEvents →
        RuntimeArgumentsEvaluateWith functions context state rest kinds outcome restEvents →
        RuntimeArgumentsEvaluateWith functions context state (first :: rest) (kind :: kinds)
          (outcome.then fun values => .value (value :: values)) (firstEvents ++ restEvents)
end

/-- Conservative old profile: empty function environment and empty call trace.
    This is a specialization of the ONE judgement, not a parallel evaluator. -/
abbrev RuntimeEvaluates (context : RuntimeExprContext) (state : RuntimeLocals)
    (raw : SourceExpr) (kind : RuntimeType) (outcome : Outcome Value) : Prop :=
  RuntimeEvaluatesWith [] context state raw kind outcome []
abbrev RuntimeArgumentsEvaluate (context : RuntimeExprContext) (state : RuntimeLocals)
    (raws : List SourceExpr) (kinds : List RuntimeType) (outcome : Outcome (List Value)) : Prop :=
  RuntimeArgumentsEvaluateWith [] context state raws kinds outcome []

abbrev RuntimeEvaluates.readVariable (binding : RuntimeVariableBinding context name declared) :
    RuntimeEvaluates context state (.name [name]) declared.kind (state.readBound declared) :=
  RuntimeEvaluatesWith.readVariable binding

def RuntimeBindingsPresent (context : RuntimeExprContext) (state : RuntimeLocals) : Prop :=
  ∀ name binding, RuntimeVariableBinding context name binding →
    state.declarations binding.slot = some binding.runtimeDeclaration ∧ binding.scope ∈ state.scopes

theorem RuntimeLocals.readBound_eq (state : RuntimeLocals) (binding : SourceLocal)
    (declared : state.declarations binding.slot = some binding.runtimeDeclaration)
    (active : binding.scope ∈ state.scopes) :
    state.readBound binding = readRuntime binding.kind (state.values binding.slot) := by
  simp only [RuntimeLocals.readBound, declared, if_pos, RuntimeLocals.read,
    SourceLocal.runtimeDeclaration, active]

end Aurora.SourceBinding
