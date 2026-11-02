import SourceBinding.CallArgumentProof
import SourceBinding.RuntimeCallControl
import SourceBinding.RuntimeCallTrace
import SourceBinding.RuntimeCallCode
namespace Aurora.SourceBinding

def RuntimeCallArgumentsRun (program : CallProgram) (external : ExternalRelation World ExternalFault)
    (base : Machine) (caller : Int) (saved : List SavedCall) (world : World)
    (start stop : Nat) (accumulator : Option Value) (stack : List Value) :
    Outcome (List Value) → List (CallEvent World ExternalFault) → Prop
  | .value values,events => CallRuns program external
      (.running (activeAt caller saved world (frameState base start accumulator stack))) events
      (.running (activeAt caller saved world (frameState base stop
        (argumentAccumulator values accumulator) (values.reverse++stack))))
  | .trap fault,events => RuntimeCallRun program external base caller saved world start stop accumulator stack (.trap fault) events

/-- Constructive finite expression correspondence, uniformly in the caller's
    accumulator and residual operand stack. The source trace records exactly
    the matched ordinary invokes/returns; a callee fault has no return event. -/
theorem RuntimeCallExpressionCode.evaluates_and_runs
    {leaves : List (RuntimeCallLeaf t files root module path)}
    (code : RuntimeCallExpressionCode program caller leaves context raw kind start stop)
    (projection : ∀ leaf ∈ leaves, localProgram program leaf.target.id = canonicalEffects t leaf.identified.id)
    (source : RuntimeLocals) (base : Machine)
    (bindings : RuntimeBindingsPresent context source)
    (locals : ∀ slot, base.locals slot = source.values slot)
    (saved : List SavedCall) (world : World) (external : ExternalRelation World ExternalFault) :
    ∃ outcome sourceEvents machineEvents,
      RuntimeEvaluatesWith (leaves.map RuntimeCallLeaf.source) context source raw kind outcome sourceEvents ∧
      RuntimeCallTraceRelated leaves sourceEvents machineEvents ∧
      ∀ accumulator stack, RuntimeCallRun program external base caller saved world start stop accumulator stack outcome machineEvents := by
  induction code using RuntimeCallExpressionCode.rec
      (motive_2 := fun raws kinds start stop _ =>
        ∃ outcome sourceEvents machineEvents,
          RuntimeArgumentsEvaluateWith (leaves.map RuntimeCallLeaf.source) context source raws kinds outcome sourceEvents ∧
          RuntimeCallTraceRelated leaves sourceEvents machineEvents ∧
          ∀ accumulator stack, RuntimeCallArgumentsRun program external base caller saved world start stop accumulator stack outcome machineEvents) with
  | «local» code =>
    obtain ⟨outcome,evaluated,run⟩ := code.evaluates_and_runs source base bindings locals
    exact ⟨outcome,[],[],evaluated.in_environment _,.nil,
      fun accumulator stack => (run accumulator stack).call_run evaluated.supported saved world external⟩
  | @call leaf name arguments start callPC member resolves args atCall ih =>
    obtain ⟨argumentOutcome,sourceEvents,machineEvents,evaluated,trace,run⟩ := ih
    have sourceMember : leaf.source ∈ leaves.map RuntimeCallLeaf.source := List.mem_map.mpr ⟨leaf,member,rfl⟩
    cases argumentOutcome with
    | trap fault =>
      exact ⟨_,_,_,.callArgumentsFault sourceMember resolves evaluated,trace,
        fun accumulator stack => (run accumulator stack).fault_stop⟩
    | value values =>
      obtain ⟨outcome,body,invoked⟩ := leaf.invoke program (projection leaf member) atCall base values evaluated.ready saved world external _
      cases outcome with
      | value value =>
        refine ⟨_,sourceEvents++[.invoke leaf.source.key values]++[]++[.returned leaf.source.key value],
          machineEvents++([.ordinaryInvoke leaf.target values]++[.ordinaryReturn leaf.target value]),
          .callValue sourceMember resolves evaluated body,?_,?_⟩
        · simpa only [List.append_nil,List.append_assoc] using trace.append
            (.cons (.invoke member) (.cons (.returned member) .nil))
        · intro accumulator stack
          obtain ⟨final,actual,result⟩ := invoked (argumentAccumulator values accumulator) stack
          exact ⟨final,(run accumulator stack).trans actual,result⟩
      | trap fault =>
        refine ⟨_,sourceEvents++[.invoke leaf.source.key values]++[],
          machineEvents++([.ordinaryInvoke leaf.target values]++[]),
          .callFault sourceMember resolves evaluated body,?_,?_⟩
        · simpa only [List.append_nil] using trace.append (.cons (.invoke member) .nil)
        · intro accumulator stack
          obtain ⟨final,actual,result⟩ := invoked (argumentAccumulator values accumulator) stack
          exact ⟨final,(run accumulator stack).trans actual,result⟩
  | not child operation ih =>
    obtain ⟨outcome,se,me,evaluated,trace,run⟩ := ih
    exact ⟨_,se,me,.not evaluated,trace,fun accumulator stack => (run accumulator stack).negate operation⟩
  | wordBinary operator left push right operation leftIH rightIH =>
    obtain ⟨leftOut,se,me,leftEval,leftTrace,leftRun⟩ := leftIH
    cases leftOut with
    | trap fault => exact ⟨_,se,me,.wordBinaryFault operator leftEval,leftTrace,fun a s => (leftRun a s).fault_stop⟩
    | value value =>
      obtain ⟨rightOut,sr,mr,rightEval,rightTrace,rightRun⟩ := rightIH
      exact ⟨_,se++sr,me++mr,.wordBinary operator leftEval rightEval,leftTrace.append rightTrace,
        fun a s => runtime_call_binary (leftRun a s) push (rightRun (some value) (value::s)) operation⟩
  | enumCompare left push right operation leftIH rightIH =>
    obtain ⟨leftOut,se,me,leftEval,leftTrace,leftRun⟩ := leftIH
    cases leftOut with
    | trap fault => exact ⟨_,se,me,.enumCompareFault leftEval,leftTrace,fun a s => (leftRun a s).fault_stop⟩
    | value value =>
      obtain ⟨rightOut,sr,mr,rightEval,rightTrace,rightRun⟩ := rightIH
      exact ⟨_,se++sr,me++mr,.enumCompare leftEval rightEval,leftTrace.append rightTrace,
        fun a s => runtime_call_enum_compare (leftRun a s) push (rightRun (some value) (value::s)) operation⟩
  | shiftLeft left count push literal operation ih =>
    obtain ⟨outcome,se,me,evaluated,trace,run⟩ := ih
    exact ⟨_,se,me,.shiftLeft evaluated count,trace,
      fun a s => runtime_call_shift (run a s) push literal operation⟩
  | shiftRight left count push literal operation ih =>
    obtain ⟨outcome,se,me,evaluated,trace,run⟩ := ih
    exact ⟨_,se,me,.shiftRight evaluated count,trace,
      fun a s => runtime_call_shift (run a s) push literal operation⟩
  | and left branch right label leftIH rightIH =>
    obtain ⟨outcome,se,me,evaluated,trace,run⟩ := leftIH
    cases outcome with
    | trap fault => exact ⟨_,se,me,.andFault evaluated,trace,fun a s => (run a s).fault_stop⟩
    | value value =>
      have typed := evaluated.outcome_typed
      cases value with
      | word _ | signedCount4 | signedCount12 | signedCount32 | nominal _ _ => cases typed
      | boolean value => cases value with
        | false => exact ⟨_,se,me,.andStop evaluated,trace,fun a s => runtime_call_and_stop (run a s) branch label⟩
        | true =>
          obtain ⟨rightOut,sr,mr,rightEval,rightTrace,rightRun⟩ := rightIH
          exact ⟨_,se++sr,me++mr,.andContinue evaluated rightEval,trace.append rightTrace,
            fun a s => runtime_call_and_continue (run a s) branch (rightRun _ s) label⟩
  | or left branch jump begin right label leftIH rightIH =>
    obtain ⟨outcome,se,me,evaluated,trace,run⟩ := leftIH
    cases outcome with
    | trap fault => exact ⟨_,se,me,.orFault evaluated,trace,fun a s => (run a s).fault_stop⟩
    | value value =>
      have typed := evaluated.outcome_typed
      cases value with
      | word _ | signedCount4 | signedCount12 | signedCount32 | nominal _ _ => cases typed
      | boolean value => cases value with
        | true => exact ⟨_,se,me,.orStop evaluated,trace,fun a s => runtime_call_or_stop (run a s) branch jump label⟩
        | false =>
          obtain ⟨rightOut,sr,mr,rightEval,rightTrace,rightRun⟩ := rightIH
          exact ⟨_,se++sr,me++mr,.orContinue evaluated rightEval,trace.append rightTrace,
            fun a s => runtime_call_or_continue (run a s) branch begin (rightRun _ s) label⟩
  | nil => exact ⟨.value [],[],[],.nil,.nil,fun _ _ => .reflexive⟩
  | cons first push rest firstIH restIH =>
    obtain ⟨firstOut,se,me,firstEval,firstTrace,firstRun⟩ := firstIH
    cases firstOut with
    | trap fault => exact ⟨_,se,me,.fault firstEval,firstTrace,fun a s => (firstRun a s).fault_stop⟩
    | value value =>
      obtain ⟨restOut,sr,mr,restEval,restTrace,restRun⟩ := restIH
      refine ⟨_,se++sr,me++mr,.cons firstEval restEval,firstTrace.append restTrace,?_⟩
      intro a s
      have pushed := runtime_call_push (firstRun a s) push
      cases restOut with
      | trap fault => exact runtime_call_prefix_fault pushed (restRun _ _)
      | value values =>
        simpa only [RuntimeCallArgumentsRun,Outcome.then,argumentAccumulator,List.reverse_cons,
          List.append_assoc,List.singleton_append] using pushed.trans (restRun (some value) (value::s))

end Aurora.SourceBinding
