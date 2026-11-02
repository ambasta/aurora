import SourceBinding.ArgumentValues
import SourceBinding.GuardSafety
namespace Aurora.SourceBinding

/-- Pure typed range rejection shape, independent of source names and IR IDs. -/
def requestRange (prior : GuardExpr .boolean) (offset bytes count : GuardExpr .word) : GuardExpr .boolean :=
  .or (.or (.or prior (.compare .eq count (.wordLit 0))) (.compare .gt offset bytes))
    (.compare .gt count (.sub bytes offset))

/-- False disjunction necessarily evaluated both operands successfully. -/
theorem eval_or_false (state : SourceState) (left right : GuardExpr .boolean)
    (evaluated : evalGuard state (.or left right) = .value (.boolean false)) :
    evalGuard state left = .value (.boolean false) ∧
      evalGuard state right = .value (.boolean false) := by
  cases first : evalGuard state left with
  | trap fault => simp [evalGuard,first,Outcome.then] at evaluated
  | value value =>
    cases value with
    | word _ | signedCount12 | signedCount4 | signedCount32 | nominal _ _ => simp [evalGuard,first,Outcome.then] at evaluated
    | boolean b =>
      cases b with
      | true => simp [evalGuard,first,Outcome.then] at evaluated
      | false => exact ⟨rfl,by simpa only [evalGuard,first,Outcome.then] using evaluated⟩

/-- Successful comparison exposes bounded operands by evaluator inversion, not
    by a readiness assumption on the receiver or on all expression leaves. -/
theorem eval_compare_words (state : SourceState) (operation : CompareOp)
    (left right : GuardExpr .word) (result : Bool)
    (evaluated : evalGuard state (.compare operation left right) = .value (.boolean result)) :
    ∃ a b, evalGuard state left = .value (.word a) ∧
      evalGuard state right = .value (.word b) ∧ a < wordLimit ∧ b < wordLimit ∧
      compareWords operation a b = result := by
  cases first : evalGuard state left with
  | trap fault => simp [evalGuard,first,Outcome.then] at evaluated
  | value l =>
    cases second : evalGuard state right with
    | trap fault => simp [evalGuard,first,second,Outcome.then] at evaluated
    | value r =>
      cases l with
      | boolean _ | signedCount12 | signedCount4 | signedCount32 | nominal _ _ => simp [evalGuard,first,second,Outcome.then,binaryValue] at evaluated
      | word a =>
        cases r with
        | boolean _ | signedCount12 | signedCount4 | signedCount32 | nominal _ _ => simp [evalGuard,first,second,Outcome.then,binaryValue] at evaluated
        | word b =>
          have ab : a < wordLimit := by
            have typed := eval_value_typed state left (.word a) first
            simpa [readScalar] using typed
          have bb : b < wordLimit := by
            have typed := eval_value_typed state right (.word b) second
            simpa [readScalar] using typed
          exact ⟨a,b,rfl,rfl,ab,bb,by
            simpa [evalGuard,first,second,Outcome.then,binaryValue,ab,bb] using evaluated⟩

/-- Reaching admission alone supplies successful bounded evaluations and the
    range inequalities. No initial no-underflow or leaf-readiness premise. -/
theorem request_range_bounds (state : SourceState) (prior : GuardExpr .boolean)
    (offset bytes count : GuardExpr .word)
    (admitted : evalGuard state (requestRange prior offset bytes count) = .value (.boolean false)) :
    ∃ o b c, evalGuard state offset = .value (.word o) ∧
      evalGuard state bytes = .value (.word b) ∧ evalGuard state count = .value (.word c) ∧
      0 < c ∧ o ≤ b ∧ c ≤ b - o ∧ o + c ≤ b ∧ b < wordLimit ∧ o < wordLimit ∧ c < wordLimit := by
  have outer := eval_or_false state _ _ admitted
  have middle := eval_or_false state _ _ outer.1
  have earlier := eval_or_false state _ _ middle.1
  obtain ⟨o,b,eo,eb,ob,bb,order⟩ := eval_compare_words state .gt offset bytes false middle.2
  obtain ⟨c,z,ec,ez,cb,zb,nonzero⟩ := eval_compare_words state .eq count (.wordLit 0) false earlier.2
  have zero : z = 0 := by
    have lit : evalGuard state (.wordLit 0) = .value (.word 0) := rfl
    exact (Value.word.inj (Outcome.value.inj (ez.symm.trans lit)))
  subst z
  have positive : 0 < c := by
    have nonzeroNat : c ≠ 0 := by
      intro zero
      subst c
      exact Bool.noConfusion nonzero
    omega
  have bounds := range_admission_bounds state (.or prior (.compare .eq count (.wordLit 0)))
    offset bytes count false o b c middle.1 eo eb ec ob bb cb admitted
  exact ⟨o,b,c,eo,eb,ec,positive,bounds.1,bounds.2,by omega,bb,ob,cb⟩

-- Tiny structural controls, not a substitute for actual byte-backed instantiation.
example : evalGuard ⟨fun _ => none,fun _ => none⟩
    (requestRange (.boolLit false) (.wordLit 3) (.wordLit 8) (.wordLit 5)) =
      .value (.boolean false) := by decide
example : evalGuard ⟨fun _ => none,fun _ => none⟩
    (requestRange (.boolLit false) (.wordLit 9) (.wordLit 8) (.wordLit 1)) =
      .value (.boolean true) := by decide
example : evalGuard ⟨fun _ => none,fun _ => none⟩
    (requestRange (.boolLit false) (.wordLit 0) (.wordLit 8) (.wordLit 0)) =
      .value (.boolean true) := by decide

end Aurora.SourceBinding
