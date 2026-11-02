import SourceBinding.RuntimeExpressionProof
import SourceBinding.CallArgumentProof
namespace Aurora.SourceBinding

def RuntimeArgumentRun (program : EffectProgram) (base : Machine) (start stop : Nat)
    (accumulator : Option Value) (stack : List Value) : Outcome (List Value) → Prop
  | .value values => EffectRuns program (frameState base start accumulator stack) []
      (.next (frameState base stop (argumentAccumulator values accumulator) (values.reverse ++ stack)))
  | .trap fault => ∃ final,
      EffectRuns program (frameState base start accumulator stack) [] (.trap (.scalar fault) final) ∧
      final.locals = base.locals ∧ final.receiver = base.receiver ∧ final.arguments = base.arguments

/-- Arguments are evaluated once, left to right, preserving the residual caller
    stack below their reversed pushed values. A fault retains its actual frame. -/
theorem RuntimeArgumentsCode.evaluates_and_runs
    (code : RuntimeArgumentsCode program context raws kinds start stop)
    (source : RuntimeLocals) (base : Machine)
    (bindings : RuntimeBindingsPresent context source)
    (locals : ∀ slot, base.locals slot = source.values slot) :
    ∃ outcome, RuntimeArgumentsEvaluate context source raws kinds outcome ∧
      ∀ accumulator stack, RuntimeArgumentRun program base start stop accumulator stack outcome := by
  induction code with
  | nil => exact ⟨.value [],.nil,fun _ _ => .reflexive⟩
  | cons first push rest ih =>
    obtain ⟨firstOut,firstEval,firstRun⟩ := first.evaluates_and_runs source base bindings locals
    cases firstOut with
    | trap fault => exact ⟨_,.fault firstEval,fun accumulator stack => firstRun accumulator stack⟩
    | value value =>
      obtain ⟨restOut,restEval,restRun⟩ := ih
      refine ⟨restOut.then (fun values => .value (value::values)),.cons firstEval restEval,?_⟩
      intro accumulator stack
      have pushed := (firstRun accumulator stack).trans
        (EffectRuns.next (runtime_push_step push) .reflexive)
      have tail := restRun (some value) (value::stack)
      cases restOut with
      | trap fault =>
        obtain ⟨final,run,localsEq,receiver,arguments⟩ := tail
        exact ⟨final,pushed.trans run,localsEq,receiver,arguments⟩
      | value values =>
        have all := pushed.trans tail
        simpa only [RuntimeArgumentRun,Outcome.then,argumentAccumulator,List.foldl_cons,
          List.reverse_cons,List.append_assoc,List.singleton_append] using all

end Aurora.SourceBinding
