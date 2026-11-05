import SourceBinding.LegacyEffectSemantics
import SourceBinding.RuntimePrimitiveTyping
import SourceBinding.EffectSourceOperations
namespace Aurora.SourceBinding

theorem LegacyEffectEvaluation.outcome_typed
    (evaluated : LegacyEffectEvaluation functions context state raw kind outcome events) :
    RuntimeOutcomeTyped kind outcome := by
  induction evaluated using LegacyEffectEvaluation.rec
      (motive_2 := fun _ _ _ _ _ _ _ => True)
      (motive_3 := fun _ _ _ _ result _ _ _ _ outcome _ _ => RuntimeBodyOutcomeTyped result outcome)
      (motive_4 := fun _ _ _ _ result _ _ _ _ outcome _ _ => RuntimeBodyOutcomeTyped result outcome) with
  | word => rw [runtime_scalar_outcome]; exact read_typed _ _
  | boolean => rfl
  | readVariable binding => exact RuntimeLocals.readBound_typed _ _
  | enumValue binding => exact runtime_read_outcome _ _
  | not child ih =>
    apply runtime_then_typed
    intro value
    rw [runtime_scalar_outcome]
    exact not_typed value
  | wordBinaryFault => trivial
  | wordBinary operator left right ihLeft ihRight =>
    apply runtime_then_typed
    intro value
    exact runtime_word_operator_typed operator _ _
  | enumCompareFault => trivial
  | enumCompare left right ihLeft ihRight =>
    apply runtime_then_typed
    intro value
    exact runtime_nominal_compare_typed _ _ _ _
  | shiftLeft left count ih | shiftRight left count ih =>
    apply runtime_then_typed
    intro value
    rw [runtime_scalar_outcome]
    exact binary_typed _ _ _
  | andFault | orFault => trivial
  | andStop | orStop => rfl
  | andContinue _ _ _ right | orContinue _ _ _ right => exact right
  | callArgumentsFault => trivial
  | callValue _ _ _ _ _ bodyTyped => exact bodyTyped
  | callFault => trivial
  | returnValue _ ih => exact ih
  | branchTrueReturn _ _ _ _ _ ih => exact ih
  | next _ _ _ ih => exact ih
  | returned _ _ ih => exact ih
  | _ => intros; trivial


theorem LegacyEffectArgumentEvaluation.checked
    (evaluated : LegacyEffectArgumentEvaluation functions context state raws kinds outcome events) :
    match outcome with
    | .value values => checkSourceArguments kinds values = .value ()
    | .trap _ => True := by
  induction evaluated using LegacyEffectArgumentEvaluation.rec
      (motive_1 := fun _ _ _ _ _ _ _ => True)
      (motive_3 := fun _ _ _ _ _ _ _ _ _ _ _ _ => True)
      (motive_4 := fun _ _ _ _ _ _ _ _ _ _ _ _ => True) with
  | nil => rfl
  | fault => trivial
  | @cons context state firstSource kind value firstEvents restSources kinds tailOutcome restEvents first rest _ ih =>
      have valid := first.outcome_typed
      change readRuntime kind (some value) = .value value at valid
      cases tailOutcome with
      | trap fault => trivial
      | value values =>
          change checkSourceArguments (kind :: kinds) (value :: values) = .value ()
          simp only [checkSourceArguments,valid]
          exact ih
  | _ => intros; trivial

end Aurora.SourceBinding
