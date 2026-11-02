import SourceBinding.RuntimeExpressionCode
import SourceBinding.RuntimeEvaluationFacts
namespace Aurora.SourceBinding

/-- Expression execution preserves the private local frame as well as shared
    receiver and arguments, including the actual terminal state on a fault. -/
def RuntimeRun (program : EffectProgram) (base : Machine) (start stop : Nat)
    (accumulator : Option Value) (stack : List Value) : Outcome Value → Prop
  | .value value => EffectRuns program (frameState base start accumulator stack) []
      (.next (frameState base stop (some value) stack))
  | .trap fault => ∃ final,
      EffectRuns program (frameState base start accumulator stack) [] (.trap (.scalar fault) final) ∧
      final.locals = base.locals ∧ final.receiver = base.receiver ∧ final.arguments = base.arguments

/-- Sequence an already completed prior without fabricating a new terminal
    frame on a subsequent failure. -/
theorem RuntimeRun.prior
    (prior : EffectRuns program (frameState base start accumulator stack) []
      (.next (frameState base middle nextAccumulator nextStack)))
    (run : RuntimeRun program base middle stop nextAccumulator nextStack outcome)
    (restored : nextStack = stack) :
    RuntimeRun program base start stop accumulator stack outcome := by
  subst nextStack
  cases outcome with
  | value value => exact prior.trans run
  | trap fault =>
    obtain ⟨final,tail,locals,receiver,arguments⟩ := run
    exact ⟨final,prior.trans tail,locals,receiver,arguments⟩

theorem runtime_prefix_fault
    (prior : EffectRuns program (frameState base start accumulator stack) []
      (.next (frameState base middle nextAccumulator nextStack)))
    (tail : RuntimeRun program base middle stop nextAccumulator nextStack (.trap fault)) :
    RuntimeRun program base start finalStop accumulator stack (.trap fault) := by
  obtain ⟨final,run,locals,receiver,arguments⟩ := tail
  exact ⟨final,prior.trans run,locals,receiver,arguments⟩

/-- A single checked expression operation. The supplied equation is an actual
    step equation, not an arithmetic or source-evaluation assumption. -/
theorem runtime_single
    (step : effectStep program (frameState base start accumulator stack) =
      ⟨retainState (frameState base start accumulator stack)
        (finish base stop stack outcome),[]⟩) :
    RuntimeRun program base start stop accumulator stack outcome := by
  cases outcome with
  | value value => exact .next step .reflexive
  | trap fault => exact ⟨frameState base start accumulator stack,.trap step,rfl,rfl,rfl⟩

theorem RuntimeExpressionCode.variable_run {binding : SourceLocal} {state : RuntimeLocals}
    (code : program start = some (runtimeLoad binding.kind binding.slot))
    (declared : state.declarations binding.slot = some binding.runtimeDeclaration)
    (active : binding.scope ∈ state.scopes)
    (locals : ∀ slot, base.locals slot = state.values slot) :
    RuntimeRun program base start (start+1) accumulator stack (state.readBound binding) := by
  rw [RuntimeLocals.readBound_eq state binding declared active]
  apply runtime_single
  cases kind : binding.kind with
  | scalar scalar =>
    simp only [runtimeLoad,kind] at code
    simp only [effectStep,frameState,code,pureView,step,locals,readRuntime]
    cases readScalar scalar (state.values binding.slot) <;> rfl
  | nominal identity =>
    simp only [runtimeLoad,kind] at code
    simp only [effectStep,frameState,code,locals,readRuntime]
    cases readRuntime (.nominal identity) (state.values binding.slot) <;> rfl

theorem RuntimeRun.bind
    (run : RuntimeRun program base start middle accumulator stack outcome)
    (tail : ∀ value, RuntimeRun program base middle stop (some value) stack (next value)) :
    RuntimeRun program base start stop accumulator stack (outcome.then next) := by
  cases outcome with
  | trap fault => exact run
  | value value => exact RuntimeRun.prior run (tail value) rfl

theorem RuntimeRun.negate
    (run : RuntimeRun program base start middle accumulator stack outcome)
    (code : program middle = some (.pure .negate)) :
    RuntimeRun program base start (middle+1) accumulator stack (outcome.then notValue) := by
  apply run.bind
  intro value
  apply runtime_single
  simp only [effectStep,frameState,code,pureView,step]
  cases value <;> rfl

/-- The payload of a transient literal is never interpreted as an ordinary
    expression value or variable. -/
theorem runtime_count_step (count : SignedLiteralCount)
    (code : program pc = some (runtimeCount count)) :
    effectStep program (frameState base pc accumulator stack) =
      ⟨.next (frameState base (pc+1) (some count.runtimeValue) stack),[]⟩ := by
  cases count <;> simp only [runtimeCount] at code
  all_goals simp only [effectStep,frameState,code,pureView,step,SignedLiteralCount.runtimeValue,retainState]

theorem runtime_push_step (code : program pc = some (.pure .push)) :
    effectStep program (frameState base pc (some value) stack) =
      ⟨.next (frameState base (pc+1) (some value) (value::stack)),[]⟩ := by
  simp only [effectStep,frameState,code,pureView,step,retainState]

theorem runtime_apply
    (prior : EffectRuns program (frameState base start accumulator stack) []
      (.next (frameState base pc input inputStack)))
    (step : effectStep program (frameState base pc input inputStack) =
      ⟨retainState (frameState base pc input inputStack) (finish base stop stack outcome),[]⟩) :
    RuntimeRun program base start stop accumulator stack outcome := by
  cases outcome with
  | value value => exact prior.trans (.next step .reflexive)
  | trap fault => exact ⟨_,prior.trans (.trap step),rfl,rfl,rfl⟩

theorem runtime_binary_run
    (leftRun : RuntimeRun program base start middle accumulator stack leftOutcome)
    (push : program middle = some (.pure .push))
    (rightRun : ∀ value, RuntimeRun program base (middle+1) endPC (some value) (value::stack) rightOutcome)
    (operation : program endPC = some (.pure (.binary primitive))) :
    RuntimeRun program base start (endPC+1) accumulator stack
      (leftOutcome.then fun a => rightOutcome.then (binaryValue primitive a)) := by
  cases leftOutcome with
  | trap fault => exact leftRun
  | value left =>
    have pushed : EffectRuns program (frameState base start accumulator stack) []
        (.next (frameState base (middle+1) (some left) (left::stack))) :=
      leftRun.trans (.next (runtime_push_step push) .reflexive)
    have right := rightRun left
    cases rightOutcome with
    | trap fault => exact runtime_prefix_fault pushed right
    | value rightValue =>
      apply runtime_apply (pushed.trans right)
      simp only [effectStep,frameState,operation,pureView,step,Outcome.then]
      cases binaryValue primitive left rightValue <;> rfl

theorem runtime_enum_compare_run
    (leftRun : RuntimeRun program base start middle accumulator stack leftOutcome)
    (push : program middle = some (.pure .push))
    (rightRun : ∀ value, RuntimeRun program base (middle+1) endPC (some value) (value::stack) rightOutcome)
    (operation : program endPC = some (.enumCompare identity equal)) :
    RuntimeRun program base start (endPC+1) accumulator stack
      (leftOutcome.then fun a => rightOutcome.then (compareNominal identity equal a)) := by
  cases leftOutcome with
  | trap fault => exact leftRun
  | value left =>
    have pushed : EffectRuns program (frameState base start accumulator stack) []
        (.next (frameState base (middle+1) (some left) (left::stack))) :=
      leftRun.trans (.next (runtime_push_step push) .reflexive)
    have right := rightRun left
    cases rightOutcome with
    | trap fault => exact runtime_prefix_fault pushed right
    | value rightValue =>
      apply runtime_apply (pushed.trans right)
      simp only [effectStep,frameState,operation,Outcome.then]
      cases compareNominal identity equal left rightValue <;> rfl

theorem runtime_shift_run
    (leftRun : RuntimeRun program base start middle accumulator stack outcome)
    (push : program middle = some (.pure .push))
    (countCode : program (middle+1) = some (runtimeCount count))
    (operation : program (middle+2) = some (.pure (.binary primitive))) :
    RuntimeRun program base start (middle+3) accumulator stack
      (outcome.then fun a => binaryValue primitive a count.runtimeValue) := by
  cases outcome with
  | trap fault => exact leftRun
  | value left =>
    have pushed : EffectRuns program (frameState base start accumulator stack) []
        (.next (frameState base (middle+1) (some left) (left::stack))) :=
      leftRun.trans (.next (runtime_push_step push) .reflexive)
    have counted : EffectRuns program (frameState base start accumulator stack) []
        (.next (frameState base (middle+2) (some count.runtimeValue) (left::stack))) :=
      pushed.trans (.next (runtime_count_step count countCode) .reflexive)
    apply runtime_apply counted
    simp only [effectStep,frameState,operation,pureView,step,Outcome.then]
    cases binaryValue primitive left count.runtimeValue <;> rfl

theorem RuntimeRun.label
    (run : RuntimeRun program base start middle accumulator stack outcome)
    (code : program middle = some (.pure .label)) :
    RuntimeRun program base start (middle+1) accumulator stack outcome := by
  cases outcome with
  | trap fault => exact run
  | value value =>
    apply run.trans
    apply EffectRuns.next (events := []) (later := []) (middle := frameState base (middle+1) (some value) stack) _ .reflexive
    simp only [effectStep,frameState,code,pureView,step,retainState]

theorem runtime_branch_false
    (code : program pc = some (.pure (.branchFalse target))) :
    effectStep program (frameState base pc (some (.boolean value)) stack) =
      ⟨.next (frameState base (if value then pc+1 else target) (some (.boolean value)) stack),[]⟩ := by
  cases value <;> simp only [effectStep,frameState,code,pureView,step,retainState,Bool.false_eq_true,if_false,if_true]

theorem runtime_jump
    (code : program pc = some (.pure (.jump target))) :
    effectStep program (frameState base pc accumulator stack) =
      ⟨.next (frameState base target accumulator stack),[]⟩ := by
  simp only [effectStep,frameState,code,pureView,step,retainState]

theorem runtime_and_stop
    (left : RuntimeRun program base start middle accumulator stack (.value (.boolean false)))
    (branch : program middle = some (.pure (.branchFalse endPC)))
    (label : program endPC = some (.pure .label)) :
    RuntimeRun program base start (endPC+1) accumulator stack (.value (.boolean false)) := by
  have jumped : RuntimeRun program base start endPC accumulator stack (.value (.boolean false)) :=
    left.trans (.next (runtime_branch_false branch) .reflexive)
  exact jumped.label label

theorem runtime_and_continue
    (left : RuntimeRun program base start middle accumulator stack (.value (.boolean true)))
    (branch : program middle = some (.pure (.branchFalse endPC)))
    (right : RuntimeRun program base (middle+1) endPC (some (.boolean true)) stack outcome)
    (label : program endPC = some (.pure .label)) :
    RuntimeRun program base start (endPC+1) accumulator stack outcome := by
  have advanced : EffectRuns program (frameState base start accumulator stack) []
      (.next (frameState base (middle+1) (some (.boolean true)) stack)) :=
    left.trans (.next (runtime_branch_false branch) .reflexive)
  exact (RuntimeRun.prior advanced right rfl).label label

theorem runtime_or_stop
    (left : RuntimeRun program base start middle accumulator stack (.value (.boolean true)))
    (branch : program middle = some (.pure (.branchFalse (middle+2))))
    (jump : program (middle+1) = some (.pure (.jump endPC)))
    (label : program endPC = some (.pure .label)) :
    RuntimeRun program base start (endPC+1) accumulator stack (.value (.boolean true)) := by
  have advanced : EffectRuns program (frameState base start accumulator stack) []
      (.next (frameState base (middle+1) (some (.boolean true)) stack)) :=
    left.trans (.next (runtime_branch_false branch) .reflexive)
  have jumped : RuntimeRun program base start endPC accumulator stack (.value (.boolean true)) :=
    advanced.trans (.next (runtime_jump jump) .reflexive)
  exact jumped.label label

theorem runtime_or_continue
    (left : RuntimeRun program base start middle accumulator stack (.value (.boolean false)))
    (branch : program middle = some (.pure (.branchFalse (middle+2))))
    (begin : program (middle+2) = some (.pure .label))
    (right : RuntimeRun program base (middle+3) endPC (some (.boolean false)) stack outcome)
    (label : program endPC = some (.pure .label)) :
    RuntimeRun program base start (endPC+1) accumulator stack outcome := by
  have jumped : RuntimeRun program base start (middle+2) accumulator stack (.value (.boolean false)) :=
    left.trans (.next (runtime_branch_false branch) .reflexive)
  have advanced := jumped.label begin
  exact (RuntimeRun.prior advanced right rfl).label label

end Aurora.SourceBinding
