import SourceBinding.ArgumentValues
import SourceBinding.ArgumentCode
namespace Aurora.SourceBinding

/-- Left-to-right evaluation of the already typed pure arguments, in the current
    shared receiver. A failed argument prevents evaluation of the suffix. -/
def evalCallArguments (state : SourceState) : {kinds : List GuardType} → CallArguments kinds → Outcome (List Value)
  | _, .nil => .value []
  | _, .cons first rest => (evalGuard state first).then fun value =>
      (evalCallArguments state rest).then fun values => .value (value :: values)

inductive ReadyArguments : List GuardType → List Value → Prop
  | nil : ReadyArguments [] []
  | cons : readScalar kind (some value) = .value value → ReadyArguments kinds values →
      ReadyArguments (kind :: kinds) (value :: values)

theorem eval_call_arguments_ready (state : SourceState) {kinds : List GuardType}
    (arguments : CallArguments kinds) {values : List Value}
    (evaluated : evalCallArguments state arguments = .value values) : ReadyArguments kinds values := by
  induction arguments generalizing values with
  | nil => cases evaluated; exact .nil
  | cons first rest ih =>
    cases firstResult : evalGuard state first with
    | trap fault => simp only [evalCallArguments,firstResult,Outcome.then] at evaluated; cases evaluated
    | value value =>
      cases restResult : evalCallArguments state rest with
      | trap fault => simp only [evalCallArguments,firstResult,Outcome.then,restResult] at evaluated; cases evaluated
      | value tail =>
        simp only [evalCallArguments,firstResult,Outcome.then,restResult,Outcome.value.injEq] at evaluated
        subst values
        exact .cons (eval_value_typed state first value firstResult) (ih restResult)

theorem ReadyArguments.length (ready : ReadyArguments kinds values) : kinds.length = values.length := by
  induction ready with
  | nil => rfl
  | cons typed rest ih => exact congrArg Nat.succ ih

theorem ReadyArguments.lookup (ready : ReadyArguments kinds values) {index : Nat} {kind : GuardType}
    (atKind : kinds[index]? = some kind) : ∃ value, values[index]? = some value ∧
      readScalar kind (some value) = .value value := by
  induction ready generalizing index with
  | nil => cases atKind
  | @cons kind' value kinds values typed rest ih =>
    cases index with
    | zero => cases atKind; exact ⟨value,rfl,typed⟩
    | succ index => exact ih atKind
end Aurora.SourceBinding
