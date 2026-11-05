import SourceBinding.EffectEvaluation
import SourceBinding.RuntimePrimitiveTyping
namespace Aurora.SourceBinding

def EffectOutcomeTyped (kind : RuntimeType) : SourceEffectOutcome World ExternalFault → Prop
  | .value none => False
  | .value (some value) => readRuntime kind (some value) = .value value
  | .stopped _ => True

def EffectBodyOutcomeTyped (kind : RuntimeType) : SourceEffectBodyOutcome World ExternalFault → Prop
  | .returned value _ => readRuntime kind (some value) = .value value
  | .continued _ | .stopped _ _ => True

theorem sourceLift_typed (typed : RuntimeOutcomeTyped kind result) :
    EffectOutcomeTyped kind (sourceLift (World := World) (ExternalFault := ExternalFault) result) := by
  cases result <;> exact typed

theorem sourceThen_typed (result : SourceEffectOutcome World ExternalFault)
    (next : Value → Outcome Value) (typed : ∀ value, RuntimeOutcomeTyped kind (next value)) :
    EffectOutcomeTyped kind (sourceThen result next) := by
  cases result with
  | stopped _ => trivial
  | value raw => cases raw with
    | none => trivial
    | some value => exact sourceLift_typed (typed value)

/-- In this narrow profile external raw responses only occur at direct statement
    consumers. Successful expressions therefore contain a present typed value;
    the conclusion is proved from ALL source constructors, not a signature axiom. -/
theorem EffectEvaluation.outcome_typed
    (evaluated : EffectEvaluation functions response context state raw kind outcome after events) :
    EffectOutcomeTyped kind outcome := by
  induction evaluated using EffectEvaluation.rec
      (motive_2 := fun _ _ _ _ _ _ _ _ => True)
      (motive_3 := fun _ result _ _ _ _ outcome _ _ => EffectBodyOutcomeTyped result outcome)
      (motive_4 := fun _ result _ _ _ _ outcome _ _ => EffectBodyOutcomeTyped result outcome) with
  | word => apply sourceLift_typed; rw [runtime_scalar_outcome]; exact read_typed _ _
  | boolean => rfl
  | readVariable binding => exact sourceLift_typed (RuntimeLocals.readBound_typed _ _)
  | readField binding => apply sourceLift_typed; rw [runtime_scalar_outcome]; exact read_typed _ _
  | enumValue binding => exact sourceLift_typed (runtime_read_outcome _ _)
  | not _ ih => apply sourceThen_typed; intro value; rw [runtime_scalar_outcome]; exact not_typed _
  | wordBinary operator _ _ _ _ => apply sourceThen_typed; intro value; exact runtime_word_operator_typed operator _ _
  | enumCompare _ _ _ _ => apply sourceThen_typed; intro value; exact runtime_nominal_compare_typed _ _ _ _
  | shiftLeft _ _ _ | shiftRight _ _ _ =>
      apply sourceThen_typed; intro value; rw [runtime_scalar_outcome]; exact binary_typed _ _ _
  | andStop | orStop => rfl
  | andContinue _ _ _ ih | orContinue _ _ _ ih => exact ih
  | resourceDeclare _ _ _ _ _ _ _ consumer _ => cases consumer <;> trivial
  | resourceRequire _ _ _ _ _ _ consumer _ => cases consumer <;> trivial
  | _ => intros; first | assumption | trivial

/-- Every successful ordered expression argument list passes the actual callee
    entry checks; this uses the narrow expression grammar, not a signature axiom. -/
theorem EffectArguments.checked {World ExternalFault : Type}
    {response : SourceExternalRelation World ExternalFault}
    {functions : List EffectSourceFunction} {context : EffectContext}
    {state : SourceEffectState World} {raws : List SourceExpr} {kinds : List RuntimeType}
    {outcome : EffectArgumentOutcome World ExternalFault} {after : SourceShared World}
    {events : List (SourceEffectEvent World ExternalFault)}
    (evaluated : EffectArguments functions response context state raws kinds outcome after events) :
    match outcome with
    | .values values => checkSourceArguments kinds values = Outcome.value ()
    | .stopped _ => True := by
  induction evaluated using EffectArguments.rec
      (motive_1 := fun _ _ _ _ _ _ _ _ => True)
      (motive_3 := fun _ _ _ _ _ _ _ _ _ => True)
      (motive_4 := fun _ _ _ _ _ _ _ _ _ => True) with
  | nil => rfl
  | stopped => trivial
  | missing => trivial
  | @cons context state raw kind value middle first rest kinds outcome after later head tail _ ih =>
      have valid := head.outcome_typed
      change readRuntime kind (some value) = .value value at valid
      cases outcome with
      | stopped stop => trivial
      | values values =>
          change checkSourceArguments (kind :: kinds) (value :: values) = Outcome.value ()
          simp only [checkSourceArguments, valid]
          exact ih
  | _ => intros; trivial

end Aurora.SourceBinding
