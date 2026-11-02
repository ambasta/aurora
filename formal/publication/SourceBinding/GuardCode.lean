import SourceBinding.ExprCode
import SourceBinding.PrefixRuns
namespace Aurora.SourceBinding

/-- The whole leading-if lowering profile: complete guard expression, false-return
    arm, and closing label. Cutpoint is derived as exactly the next instruction;
    its tail instruction is not inspected or executed. -/
structure GuardCode (program : Program) (slots : Nat → Nat) (guard : GuardExpr .boolean)
    (start endExpr : Nat) : Prop where
  expression : ExprCode (stallAt program (endExpr + 4)) slots guard start endExpr
  branch : program endExpr = some (.branchFalse (endExpr + 3))
  refusal : program (endExpr + 1) = some (.constant .boolean (.boolean false))
  returnFalse : program (endExpr + 2) = some .ret
  close : program (endExpr + 3) = some .label

structure CheckedGuardCode (program : Program) (slots : Nat → Nat) (guard : GuardExpr .boolean) (start : Nat) where
  endExpr : Nat
  grammar : GuardCode program slots guard start endExpr

def checkGuardCode (program : Program) (slots : Nat → Nat) (guard : GuardExpr .boolean) (start : Nat) :
    Option (CheckedGuardCode program slots guard start) := do
  let candidate ← checkExprCode program slots guard start
  let checked ← checkExprCode (stallAt program (candidate.stop + 4)) slots guard start
  if same : checked.stop = candidate.stop then
    if branch : program candidate.stop = some (.branchFalse (candidate.stop + 3)) then
      if refusal : program (candidate.stop + 1) = some (.constant .boolean (.boolean false)) then
        if returnFalse : program (candidate.stop + 2) = some .ret then
          if close : program (candidate.stop + 3) = some .label then
            return ⟨candidate.stop,⟨by simpa only [same] using checked.grammar,branch,refusal,returnFalse,close⟩⟩
          else none
        else none
      else none
    else none
  else none

/-- Source rejection-if outcome: true refuses, false continues; generic traps
    propagate. A nonboolean value is a type fault, not an admission. -/
def rejectionOutcome (base : Machine) (cut : Nat) : Outcome Value → Execution
  | .trap fault => .trap fault
  | .value (.word _) | .value .signedCount12 => .trap .type
  | .value (.boolean true) => .returned (.boolean false)
  | .value (.boolean false) => .next (frameState base cut (some (.boolean false)) [])

theorem rejection_at_exit (base : Machine) (cut : Nat) (value : Outcome Value) :
    AtExit cut (rejectionOutcome base cut value) := by
  cases value with
  | trap fault => trivial
  | value value => cases value with
    | word _ | signedCount12 => trivial
    | boolean b => cases b <;> trivial

variable {guard : GuardExpr .boolean}

theorem GuardCode.runs (code : GuardCode program slots guard start endExpr)
    (source : SourceState) (base : Machine) (context : ContextRelated source base slots)
    (accumulator : Option Value) :
    Runs (stallAt program (endExpr + 4)) (frameState base start accumulator [])
      (rejectionOutcome base (endExpr + 4) (evalGuard source guard)) := by
  have branch : stallAt program (endExpr + 4) endExpr = some (.branchFalse (endExpr + 3)) := by
    have away : endExpr ≠ endExpr + 4 := by omega
    simpa only [stallAt,if_neg away] using code.branch
  have refusal : stallAt program (endExpr + 4) (endExpr + 1) = some (.constant .boolean (.boolean false)) := by
    simp [stallAt,code.refusal]
  have ret : stallAt program (endExpr + 4) (endExpr + 2) = some .ret := by simp [stallAt,code.returnFalse]
  have close : stallAt program (endExpr + 4) (endExpr + 3) = some .label := by simp [stallAt,code.close]
  have expression := code.expression.simulates source base context accumulator []
  cases result : evalGuard source guard with
  | trap fault => simpa [result,finish,rejectionOutcome] using expression
  | value value =>
    rw [result] at expression
    cases value with
    | word _ | signedCount12 =>
      exact expression.trans (Runs.one (by simp [step,frameState,branch,rejectionOutcome]))
    | boolean b =>
      cases b with
      | false =>
        have branched : Runs (stallAt program (endExpr + 4)) (frameState base endExpr (some (.boolean false)) [])
            (.next (frameState base (endExpr + 3) (some (.boolean false)) [])) :=
          Runs.one (by simp [step,frameState,branch])
        exact (expression.trans branched).trans (Runs.one (by simp [step,frameState,close,rejectionOutcome,Nat.add_assoc]))
      | true =>
        have branched : Runs (stallAt program (endExpr + 4)) (frameState base endExpr (some (.boolean true)) [])
            (.next (frameState base (endExpr + 1) (some (.boolean true)) [])) :=
          Runs.one (by simp [step,frameState,branch])
        have refused : Runs (stallAt program (endExpr + 4)) (frameState base (endExpr + 1) (some (.boolean true)) [])
            (.next (frameState base (endExpr + 2) (some (.boolean false)) [])) :=
          Runs.one (by simp [step,frameState,refusal,finish,readScalar,Nat.add_assoc])
        exact ((expression.trans branched).trans refused).trans (Runs.one (by simp [step,frameState,ret,rejectionOutcome]))

/-- Exact outcome for the first exit, not merely one favorable finite path. -/
theorem GuardCode.first_exit (code : GuardCode program slots guard start endExpr)
    (source : SourceState) (base : Machine) (context : ContextRelated source base slots)
    (accumulator : Option Value) :
    FirstExit program (endExpr + 4) (frameState base start accumulator [])
      (rejectionOutcome base (endExpr + 4) (evalGuard source guard)) :=
  (code.runs source base context accumulator).stalled_first_exit (rejection_at_exit _ _ _)

theorem GuardCode.unique_outcome (code : GuardCode program slots guard start endExpr)
    (source : SourceState) (base : Machine) (context : ContextRelated source base slots)
    (accumulator : Option Value)
    (other : FirstExit program (endExpr + 4) (frameState base start accumulator []) result) :
    result = rejectionOutcome base (endExpr + 4) (evalGuard source guard) :=
  other.unique (code.first_exit source base context accumulator)

theorem GuardCode.terminates_before_tail (code : GuardCode program slots guard start endExpr)
    (source : SourceState) (base : Machine) (context : ContextRelated source base slots)
    (accumulator : Option Value) :
    ¬ DivergesBefore program (endExpr + 4) (frameState base start accumulator []) :=
  (code.first_exit source base context accumulator).not_diverges_before

end Aurora.SourceBinding
