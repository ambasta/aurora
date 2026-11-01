import SourceBinding.Stateful
namespace Aurora.SourceBinding

def SupportedOutcome (outcome : Outcome Value) : Prop := outcome ≠ .trap .unsupported

theorem read_supported (kind : GuardType) (input : Option Value) : SupportedOutcome (readScalar kind input) := by
  cases input with
  | none => simp [SupportedOutcome,readScalar]
  | some value =>
    cases value <;> simp only [readScalar]
    all_goals split <;> simp_all [SupportedOutcome]
    split <;> simp

theorem binary_supported (operation : Binary) (left right : Value) : SupportedOutcome (binaryValue operation left right) := by
  cases operation <;> cases left <;> cases right <;> simp only [binaryValue,SupportedOutcome]
  all_goals try simp
  all_goals split <;> try simp_all
  split <;> simp_all

theorem not_supported (value : Value) : SupportedOutcome (notValue value) := by
  cases value <;> simp [SupportedOutcome,notValue]

theorem then_supported (out : Outcome Value) (next : Value → Outcome Value)
    (first : SupportedOutcome out) (rest : ∀ value, SupportedOutcome (next value)) :
    SupportedOutcome (out.then next) := by
  cases out with
  | trap fault => exact first
  | value value => exact rest value

theorem eval_supported (state : SourceState) {kind : GuardType} (expression : GuardExpr kind) :
    SupportedOutcome (evalGuard state expression) := by
  induction expression with
  | wordLit value => exact read_supported _ _
  | boolLit value => simp [evalGuard,SupportedOutcome]
  | parameter kind name index | field kind name index => exact read_supported _ _
  | not child ih => exact then_supported _ _ ih not_supported
  | sub left right leftIH rightIH =>
    exact then_supported _ _ leftIH (fun a => then_supported _ _ rightIH (fun b => binary_supported _ a b))
  | compare operation left right leftIH rightIH =>
    exact then_supported _ _ leftIH (fun a => then_supported _ _ rightIH (fun b => binary_supported _ a b))
  | and left right leftIH rightIH =>
    apply then_supported _ _ leftIH
    intro value; cases value with
    | word _ => simp [SupportedOutcome]
    | boolean b => cases b <;> first | exact rightIH | simp [SupportedOutcome]
  | or left right leftIH rightIH =>
    apply then_supported _ _ leftIH
    intro value; cases value with
    | word _ => simp [SupportedOutcome]
    | boolean b => cases b <;> first | exact rightIH | simp [SupportedOutcome]

/-- Successful expression completion has an exact frame. Fault completion keeps
    the actual terminal frame and equates its receiver/arguments, not its PC. -/
def ExpressionResult (base : Machine) (stop : Nat) (stack : List Value)
    (outcome : Outcome Value) (result : EffectExecution) : Prop :=
  match outcome with
  | .value value => result = .next (frameState base stop (some value) stack)
  | .trap fault => ∃ final, result = .trap (.scalar fault) final ∧
      final.receiver = base.receiver ∧ final.arguments = base.arguments

theorem ExprCode.effect_simulates {program : EffectProgram} {slots : Nat → Nat} {kind : GuardType}
    {expression : GuardExpr kind} {start stop : Nat}
    (code : ExprCode (pureView program) slots expression start stop)
    (source : SourceState) (base : Machine) (context : ContextRelated source base slots)
    (accumulator : Option Value) (stack : List Value) :
    ∃ result, EffectRuns program (frameState base start accumulator stack) [] result ∧
      ExpressionResult base stop stack (evalGuard source expression) result := by
  have run := code.simulates source base context accumulator stack
  have supported : finish base stop stack (evalGuard source expression) ≠ .trap .unsupported := by
    cases outcome : evalGuard source expression with
    | value value => intro h; cases h
    | trap fault =>
      have safe := eval_supported source expression
      simp only [SupportedOutcome,outcome,ne_eq,Outcome.trap.injEq] at safe
      simpa only [finish,ne_eq,Execution.trap.injEq] using safe
  obtain ⟨result,actual,erased,receiver,arguments⟩ := pure_runs_lift run supported
  refine ⟨result,actual,?_⟩
  cases outcome : evalGuard source expression with
  | value value =>
    simp only [outcome,finish] at erased
    cases result <;> simp_all [eraseEffect,ExpressionResult]
    case trap fault state => cases fault <;> simp_all
  | trap fault =>
    simp only [outcome,finish] at erased
    cases result with
    | next state => cases erased
    | returned value state => cases erased
    | trap error state =>
      cases error with
      | assertion => cases erased
      | scalar error =>
        simp only [eraseEffect,Option.some.injEq,Execution.trap.injEq] at erased
        subst error
        exact ⟨state,rfl,receiver,arguments⟩

end Aurora.SourceBinding
