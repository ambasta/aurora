import SourceBinding.RuntimeCallSourceFacts
import SourceBinding.EffectExpressions
namespace Aurora.SourceBinding

theorem runtime_read_supported (kind : RuntimeType) (input : Option Value) :
    SupportedOutcome (readRuntime kind input) := by
  cases kind with
  | scalar kind => exact read_supported _ _
  | nominal identity =>
    cases input with
    | none => intro h; cases h
    | some value => cases value <;> simp only [readRuntime,SupportedOutcome]
                    all_goals first | (intro h; cases h) | (split <;> (intro h; cases h))

theorem RuntimeLocals.readBound_supported (state : RuntimeLocals) (binding : SourceLocal) :
    SupportedOutcome (state.readBound binding) := by
  unfold RuntimeLocals.readBound
  split
  next declared =>
    simp only [RuntimeLocals.read,declared,SourceLocal.runtimeDeclaration]
    split
    · exact runtime_read_supported _ _
    · intro h; cases h
  next => intro h; cases h

theorem runtime_nominal_compare_supported (identity : NominalIdentity) (equal : Bool) (a b : Value) :
    SupportedOutcome (compareNominal identity equal a b) := by
  unfold compareNominal
  apply then_supported _ _ (runtime_read_supported _ _)
  intro left
  apply then_supported _ _ (runtime_read_supported _ _)
  intro right
  cases left <;> cases right <;> (intro h; cases h)

def RuntimeBodySupported : RuntimeBodyOutcome → Prop
  | .trapped fault _ => SupportedOutcome (.trap fault)
  | .continued _ | .returned _ _ => True

theorem RuntimeEvaluation.supported
    (evaluated : RuntimeEvaluation functions context state raw kind outcome events) :
    SupportedOutcome outcome := by
  apply PureRuntimeEvaluation.induct evaluated
    (Expression := fun _ _ _ _ outcome _ => SupportedOutcome outcome)
    (Arguments := fun _ _ _ _ outcome _ => outcome ≠ (Outcome.trap Fault.unsupported : Outcome (List Value)))
    (Statement := fun _ _ _ _ _ _ _ _ _ outcome _ => RuntimeBodySupported outcome)
    (Statements := fun _ _ _ _ _ _ _ _ _ outcome _ => RuntimeBodySupported outcome)
  exact {
    expression_word := by
      intro context state value
      exact read_supported _ _
    expression_boolean := by
      intro context state value
      intro h; cases h
    expression_readVariable := by
      intro context name binding state h0
      exact RuntimeLocals.readBound_supported _ _
    expression_enumValue := by
      intro context name identity ordinal state h0
      exact runtime_read_supported _ _
    expression_not := by
      intro context state inner outcome events h0
      exact then_supported _ _ h0 not_supported
    expression_wordBinaryFault := by
      intro operator primitive result context state left fault events right h0 h1
      exact h1
    expression_wordBinary := by
      intro operator primitive result context state left value leftEvents right outcome rightEvents h0 h1 h2
      exact then_supported _ _ h2 (fun _ => binary_supported _ _ _)
    expression_enumCompareFault := by
      intro context state left identity fault events right equal h0
      exact h0
    expression_enumCompare := by
      intro context state left identity value leftEvents right outcome rightEvents equal h0 h1
      exact then_supported _ _ h1 (fun _ => runtime_nominal_compare_supported _ _ _ _)
    expression_shiftLeft := by
      intro context state left outcome events right count h0 h1
      exact then_supported _ _ h0 (fun _ => binary_supported _ _ _)
    expression_shiftRight := by
      intro context state left outcome events right count h0 h1
      exact then_supported _ _ h0 (fun _ => binary_supported _ _ _)
    expression_andFault := by
      intro context state left fault events right h0
      exact h0
    expression_andStop := by
      intro context state left events right h0
      exact h0
    expression_andContinue := by
      intro context state left leftEvents right outcome rightEvents h0 h1
      exact h1
    expression_orFault := by
      intro context state left fault events right h0
      exact h0
    expression_orStop := by
      intro context state left events right h0
      exact h0
    expression_orContinue := by
      intro context state left leftEvents right outcome rightEvents h0 h1
      exact h1
    expression_callArgumentsFault := by
      intro leaf context name state sources fault events h0 h1 h2
      intro impossible; exact h2 (Outcome.trap.inj impossible ▸ rfl)
    expression_callValue := by
      intro leaf context name state sources values argumentEvents after value finished bodyEvents h0 h1 h2 h3
      intro h; cases h
    expression_callFault := by
      intro leaf context name state sources values argumentEvents after fault finished bodyEvents h0 h1 h2 h3
      exact h3
    arguments_nil := by
      intro context state
      intro h; cases h
    arguments_fault := by
      intro context state first kind fault events rest kinds h0
      intro impossible; exact h0 (Outcome.trap.inj impossible ▸ rfl)
    arguments_cons := by
      intro context state first kind value firstEvents rest kinds outcome restEvents h0 h1
      cases outcome with
      | trap fault => exact h1
      | value values => intro h; cases h
    statement_declarationFault := by
      intro members module path formals before raw after binding state fault events result declaration h0 h1
      exact h1
    statement_declarationValue := by
      intro members module path formals before raw after binding state value events next result declaration h0 h1 h2
      trivial
    statement_assignmentFault := by
      intro binding name members module path formals before state raw fault events result h0 h1 h2 h3
      exact h3
    statement_assignmentValue := by
      intro binding name members module path formals before state raw value events next result h0 h1 h2 h3 h4
      trivial
    statement_returnFault := by
      intro members module path formals before state raw result fault events h0
      exact h0
    statement_returnValue := by
      intro members module path formals before state raw result value events h0
      trivial
    statement_branchFault := by
      intro members module path formals before body child declaredItems state condition fault events result h0 h1
      exact h1
    statement_branchFalse := by
      intro members module path formals before body child declaredItems state condition events next result h0 h1 h2
      trivial
    statement_branchTrueContinue := by
      intro members module path formals before body child declaredItems state condition firstEvents entered result finished bodyEvents next h0 h1 h2 h3 h4
      trivial
    statement_branchTrueReturn := by
      intro members module path formals before body child declaredItems state condition firstEvents entered result value finished bodyEvents h0 h1 h2 h3
      trivial
    statement_branchTrueFault := by
      intro members module path formals before body child declaredItems state condition firstEvents entered result fault finished bodyEvents h0 h1 h2 h3
      exact h3
    statements_nil := by
      intro members module path formals result before state
      trivial
    statements_next := by
      intro members module path formals result before state first middle next firstEvents rest after outcome restEvents h0 h1
      exact h1
    statements_returned := by
      intro members module path formals result before state first middle value final events rest after declaredItems h0 h1
      trivial
    statements_trapped := by
      intro members module path formals result before state first middle fault final events rest after declaredItems h0 h1
      exact h0
  }

theorem RuntimeEvaluatesWith.supported
    (evaluated : RuntimeEvaluatesWith functions context state raw kind outcome events) :
    SupportedOutcome outcome := RuntimeEvaluation.supported evaluated

end Aurora.SourceBinding
