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
  induction evaluated using RuntimeEvaluation.rec
      (motive_2 := fun _ _ _ _ outcome _ _ =>
        outcome ≠ (Outcome.trap Fault.unsupported : Outcome (List Value)))
      (motive_3 := fun _ _ _ _ _ _ _ _ _ outcome _ _ => RuntimeBodySupported outcome)
      (motive_4 := fun _ _ _ _ _ _ _ _ _ outcome _ _ => RuntimeBodySupported outcome) with
  | word => exact read_supported _ _
  | boolean => intro h; cases h
  | readVariable _ => exact RuntimeLocals.readBound_supported _ _
  | enumValue _ => exact runtime_read_supported _ _
  | not _ ih => exact then_supported _ _ ih not_supported
  | wordBinaryFault _ _ ih => exact ih
  | wordBinary _ _ _ left right => exact then_supported _ _ right (fun _ => binary_supported _ _ _)
  | enumCompareFault _ ih => exact ih
  | enumCompare _ _ left right => exact then_supported _ _ right (fun _ => runtime_nominal_compare_supported _ _ _ _)
  | shiftLeft _ _ ih | shiftRight _ _ ih => exact then_supported _ _ ih (fun _ => binary_supported _ _ _)
  | andFault _ ih | orFault _ ih | andStop _ ih | orStop _ ih => exact ih
  | andContinue _ _ _ right | orContinue _ _ _ right => exact right
  | callArgumentsFault _ _ _ ih =>
    intro impossible
    exact ih (Outcome.trap.inj impossible ▸ rfl)
  | callValue => intro h; cases h
  | callFault _ _ _ _ _ body => exact body
  | fault first ih =>
    intro impossible
    exact ih (Outcome.trap.inj impossible ▸ rfl)
  | @cons context state first kind value firstEvents rest kinds outcome restEvents firstEval restEval firstIH restIH =>
    cases outcome with
    | trap fault => exact restIH
    | value values => intro h; cases h
  | declarationFault _ _ ih | assignmentFault _ _ _ _ ih | returnFault _ ih | branchFault _ _ ih => exact ih
  | branchTrueFault _ _ _ _ _ ih => exact ih
  | next _ _ _ ih => exact ih
  | trapped _ _ ih => exact ih
  | _ => all_goals intros; trivial

theorem RuntimeEvaluatesWith.supported
    (evaluated : RuntimeEvaluatesWith functions context state raw kind outcome events) :
    SupportedOutcome outcome := RuntimeEvaluation.supported evaluated

end Aurora.SourceBinding
