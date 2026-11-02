import SourceBinding.CallMachineProof
namespace Aurora.SourceBinding

def SourceSupported : SourceExecution → Prop
  | .trap (.scalar .unsupported) _ => False
  | _ => True

theorem expression_body_supported (state : SourceState) (outcome : Outcome Value)
    (next : Value → BodyEvaluation) (supported : SupportedOutcome outcome)
    (later : ∀ value, SourceSupported (next value).execution) :
    SourceSupported (sourceExpression state outcome next).execution := by
  cases outcome with
  | value value => exact later value
  | trap fault =>
    cases fault <;> try trivial

theorem eval_body_supported (body : EffectBody) (state : SourceState) :
    SourceSupported (evalBody body state).execution := by
  induction body generalizing state with
  | skip => trivial
  | seq first rest firstIH restIH =>
    have firstSupport := firstIH state
    simp only [evalBody]
    cases firstEq : (evalBody first state).execution with
    | next next => exact restIH next
    | returned value next => trivial
    | trap fault next => simpa only [firstEq] using firstSupport
  | assign kind ordinal value =>
    apply expression_body_supported _ _ _ (eval_supported state value)
    intro scalar
    apply expression_body_supported _ _ _ (read_supported kind (some scalar))
    intro checked; trivial
  | require condition =>
    apply expression_body_supported _ _ _ (eval_supported state condition)
    intro value; cases value with
    | word _ | signedCount12 | signedCount4 | signedCount32 | nominal _ _ => trivial
    | boolean b => cases b <;> trivial
  | returnValue kind value =>
    apply expression_body_supported _ _ _ (eval_supported state value)
    intro scalar; trivial
  | branch condition body ih =>
    apply expression_body_supported _ _ _ (eval_supported state condition)
    intro value; cases value with
    | word _ | signedCount12 | signedCount4 | signedCount32 | nominal _ _ => trivial
    | boolean b => cases b with
      | false => trivial
      | true => exact ih state

theorem BodyResultRelated.supported (related : BodyResultRelated slots stack stop source machine)
    (supported : SourceSupported source) : LocalSupported machine := by
  cases source with
  | next state => cases machine <;> first | trivial | cases related
  | returned value state => cases machine <;> first | trivial | cases related
  | trap fault state =>
    cases machine with
    | next _ | returned _ _ => cases related
    | trap machineFault _ =>
      obtain ⟨same,_⟩ := related
      subst machineFault
      cases fault with
      | assertion => trivial
      | scalar scalar => cases scalar <;> first | trivial | exact supported
theorem expression_parameters (state : SourceState) (outcome : Outcome Value)
    (next : Value → BodyEvaluation)
    (preserved : ∀ value, (next value).execution.state.parameters = state.parameters) :
    (sourceExpression state outcome next).execution.state.parameters = state.parameters := by
  cases outcome with
  | trap fault => rfl
  | value value => exact preserved value

theorem eval_body_parameters (body : EffectBody) (state : SourceState) :
    (evalBody body state).execution.state.parameters = state.parameters := by
  induction body generalizing state with
  | skip => rfl
  | seq first rest firstIH restIH =>
    have initial := firstIH state
    simp only [evalBody]
    cases firstEq : (evalBody first state).execution with
    | next next => exact (restIH next).trans (by simpa only [firstEq,SourceExecution.state] using initial)
    | returned value next | trap value next => exact initial
  | assign kind ordinal value =>
    apply expression_parameters
    intro scalar
    apply expression_parameters
    intro checked; rfl
  | require condition =>
    apply expression_parameters
    intro value; cases value with
    | word _ | signedCount12 | signedCount4 | signedCount32 | nominal _ _ => rfl
    | boolean b => cases b <;> rfl
  | returnValue kind value => apply expression_parameters; intro scalar; rfl
  | branch condition body ih =>
    apply expression_parameters
    intro value; cases value with
    | word _ | signedCount12 | signedCount4 | signedCount32 | nominal _ _ => rfl
    | boolean b => cases b with
      | false => rfl
      | true => exact ih state
end Aurora.SourceBinding
