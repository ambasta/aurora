import SourceBinding.CallSyntax
import SourceBinding.EffectCode
namespace Aurora.SourceBinding

/-- Every pushed argument has its own exact expression interval, in source order. -/
inductive PushedArgumentsCode (program : Program) (slots : Nat → Nat) :
    {kinds : List GuardType} → CallArguments kinds → Nat → Nat → Prop
  | nil : PushedArgumentsCode program slots .nil start start
  | cons : ExprCode program slots value start middle → program middle = some .push →
      PushedArgumentsCode program slots values (middle + 1) stop →
      PushedArgumentsCode program slots (.cons value values) start stop

/-- The one-argument retained-resource convention is accumulator-only. Ordinary
    calls and all other retained arities push every argument, including the last. -/
inductive ArgumentsCode (program : Program) (slots : Nat → Nat) :
    Bool → {kinds : List GuardType} → CallArguments kinds → Nat → Nat → Prop
  | pushed {kinds : List GuardType} {values : CallArguments kinds} : (resource = false ∨ kinds.length ≠ 1) →
      PushedArgumentsCode program slots values start stop → ArgumentsCode program slots resource values start stop
  | single : ExprCode program slots value start stop →
      ArgumentsCode program slots true (.cons value .nil) start stop

structure CheckedPushedArguments (program : Program) (slots : Nat → Nat) {kinds : List GuardType}
    (values : CallArguments kinds) (start : Nat) where
  stop : Nat
  code : PushedArgumentsCode program slots values start stop

def checkPushedArguments (program : Program) (slots : Nat → Nat) : {kinds : List GuardType} →
    (values : CallArguments kinds) → (start : Nat) → Option (CheckedPushedArguments program slots values start)
  | _, .nil, start => some ⟨start,.nil⟩
  | _, .cons value values, start => do
    let expression ← checkExprCode program slots value start
    if push : program expression.stop = some .push then
      let rest ← checkPushedArguments program slots values (expression.stop + 1)
      return ⟨rest.stop,.cons expression.grammar push rest.code⟩
    else none
structure CheckedArguments (program : Program) (slots : Nat → Nat) (resource : Bool) {kinds : List GuardType}
    (values : CallArguments kinds) (start : Nat) where
  stop : Nat
  code : ArgumentsCode program slots resource values start stop

def checkArguments (program : Program) (slots : Nat → Nat) (resource : Bool) : {kinds : List GuardType} →
    (values : CallArguments kinds) → (start : Nat) → Option (CheckedArguments program slots resource values start)
  | kinds, values, start =>
    if ordinary : resource = false then do
      let checked ← checkPushedArguments program slots values start
      return ⟨checked.stop,.pushed (Or.inl ordinary) checked.code⟩
    else
      match kinds, values with
      | [_], .cons value .nil => do
        let expression ← checkExprCode program slots value start
        return ⟨expression.stop,by
          have same : resource = true := by
            cases resource with
            | false => exact False.elim (ordinary rfl)
            | true => rfl
          subst resource
          exact .single expression.grammar⟩
      | [], .nil => some ⟨start,.pushed (Or.inr (by decide)) .nil⟩
      | _ :: _ :: _, .cons value (.cons next rest) => do
        let checked ← checkPushedArguments program slots (.cons value (.cons next rest)) start
        return ⟨checked.stop,.pushed (Or.inr (by simp only [List.length_cons]; omega)) checked.code⟩

/-- Finite administrative stuttering. No decoder fallback or arbitrary skipped row. -/
inductive LabelRun (program : Program) : Nat → Nat → Prop
  | nil : LabelRun program start start
  | cons : program start = some .label → LabelRun program (start + 1) stop → LabelRun program start stop
structure CheckedLabels (program : Program) (start : Nat) where
  stop : Nat
  code : LabelRun program start stop

def checkLabels (program : Program) : Nat → (start : Nat) → CheckedLabels program start
  | 0, start => ⟨start,.nil⟩
  | fuel + 1, start =>
    if label : program start = some .label then
      let rest := checkLabels program fuel (start + 1)
      ⟨rest.stop,.cons label rest.code⟩
    else ⟨start,.nil⟩

theorem LabelRun.forward (run : LabelRun program start stop) : start ≤ stop := by
  induction run with
  | nil => exact Nat.le_refl _
  | cons label run ih => omega

theorem checked_arguments_sound (checked : CheckedArguments program slots resource values start) :
    ArgumentsCode program slots resource values start checked.stop := checked.code

theorem checked_labels_sound (checked : CheckedLabels program start) : LabelRun program start checked.stop := checked.code
end Aurora.SourceBinding
