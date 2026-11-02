import SourceBinding.RuntimeCallableInvoke
import SourceBinding.RuntimeCallControl
import SourceBinding.RuntimeCallCode
namespace Aurora.SourceBinding

/-- Uniform generic composition. Only direct callees require the internally
    derived execution hypothesis; their source bodies run in the GLOBAL env.
    No source result or trace depends on a caller machine context. -/
theorem RuntimeCallExpressionCode.evaluates_uniform
    {nodes direct : List (RuntimeCallable t files root module path)}
    (code : RuntimeCallExpressionCode program caller direct context raw kind start stop)
    (included : ∀ callable ∈ direct, callable ∈ nodes)
    (callees : ∀ callable ∈ direct, RuntimeCalleeExecutes program nodes callable World ExternalFault)
    (source : RuntimeLocals) (bindings : RuntimeBindingsPresent context source) :
    ∃ outcome sourceEvents machineEvents,
      RuntimeEvaluation (nodes.map RuntimeCallable.source) context source raw kind outcome sourceEvents ∧
      RuntimeCallTraceRelated nodes sourceEvents machineEvents ∧
      ∀ (base : Machine), (∀ slot, base.locals slot = source.values slot) →
      ∀ (saved : List SavedCall) (world : World) (external : ExternalRelation World ExternalFault) accumulator stack,
        RuntimeCallRun program external base caller saved world start stop accumulator stack outcome machineEvents := by
  induction code using RuntimeCallExpressionCode.rec
      (motive_2 := fun raws kinds start stop _ =>
        ∃ outcome sourceEvents machineEvents,
          RuntimeArgumentEvaluation (nodes.map RuntimeCallable.source) context source raws kinds outcome sourceEvents ∧
          RuntimeCallTraceRelated nodes sourceEvents machineEvents ∧
          ∀ (base : Machine), (∀ slot, base.locals slot = source.values slot) →
          ∀ (saved : List SavedCall) (world : World) (external : ExternalRelation World ExternalFault) accumulator stack, RuntimeCallArgumentsRun program external base caller saved world start stop accumulator stack outcome machineEvents) with
  | «local» code =>
    obtain ⟨outcome,evaluated,run⟩ := code.evaluates_uniform source bindings
    exact ⟨outcome,[],[],RuntimeEvaluation.in_environment evaluated _,.nil,
      fun base locals saved world external accumulator stack =>
        (run base locals accumulator stack).call_run evaluated.supported saved world external⟩
  | @call callable name arguments start callPC member resolves args atCall ih =>
    obtain ⟨argumentOutcome,sourceEvents,machineEvents,evaluated,trace,run⟩ := ih
    have globalMember := included callable member
    have sourceMember : callable.source ∈ nodes.map RuntimeCallable.source := List.mem_map.mpr ⟨callable,globalMember,rfl⟩
    cases argumentOutcome with
    | trap fault =>
      exact ⟨_,_,_,.callArgumentsFault sourceMember resolves evaluated,trace,
        fun base locals saved world external accumulator stack => (run base locals saved world external accumulator stack).fault_stop⟩
    | value values =>
      obtain ⟨outcome,finalSource,sb,mb,body,bodyTrace,invoked⟩ :=
        callable.invoke_uniform (callees callable member) atCall values evaluated.outcome_typed
      cases outcome with
      | value value =>
        refine ⟨_,sourceEvents++[.invoke callable.source.key values]++sb++[.returned callable.source.key value],
          machineEvents++([.ordinaryInvoke callable.target values]++mb++[.ordinaryReturn callable.target value]),
          .callValue sourceMember resolves evaluated body,?_,?_⟩
        · simpa only [List.append_assoc,List.singleton_append] using trace.append
            (.cons (.invoke globalMember) (bodyTrace.append (.cons (.returned globalMember) .nil)))
        · intro base locals saved world external accumulator stack
          obtain ⟨final,actual,result⟩ := invoked base saved world external (argumentAccumulator values accumulator) stack
          exact ⟨final,(run base locals saved world external accumulator stack).trans actual,result⟩
      | trap fault =>
        refine ⟨_,sourceEvents++[.invoke callable.source.key values]++sb,
          machineEvents++([.ordinaryInvoke callable.target values]++mb),
          .callFault sourceMember resolves evaluated body,?_,?_⟩
        · simpa only [List.append_assoc,List.singleton_append] using trace.append (.cons (.invoke globalMember) bodyTrace)
        · intro base locals saved world external accumulator stack
          obtain ⟨final,actual,result⟩ := invoked base saved world external (argumentAccumulator values accumulator) stack
          refine ⟨final,?_,result⟩
          simpa only [runtimeReturnEvents,List.append_nil] using
            (run base locals saved world external accumulator stack).trans actual
  | not child operation ih =>
    obtain ⟨outcome,se,me,evaluated,trace,run⟩ := ih
    exact ⟨_,se,me,.not evaluated,trace,fun base locals saved world external accumulator stack => (run base locals saved world external accumulator stack).negate operation⟩
  | wordBinary operator left push right operation leftIH rightIH =>
    obtain ⟨leftOut,se,me,leftEval,leftTrace,leftRun⟩ := leftIH
    cases leftOut with
    | trap fault => exact ⟨_,se,me,.wordBinaryFault operator leftEval,leftTrace,fun base locals saved world external a s => (leftRun base locals saved world external a s).fault_stop⟩
    | value value =>
      obtain ⟨rightOut,sr,mr,rightEval,rightTrace,rightRun⟩ := rightIH
      exact ⟨_,se++sr,me++mr,.wordBinary operator leftEval rightEval,leftTrace.append rightTrace,
        fun base locals saved world external a s => runtime_call_binary (leftRun base locals saved world external a s) push (rightRun base locals saved world external (some value) (value::s)) operation⟩
  | enumCompare left push right operation leftIH rightIH =>
    obtain ⟨leftOut,se,me,leftEval,leftTrace,leftRun⟩ := leftIH
    cases leftOut with
    | trap fault => exact ⟨_,se,me,.enumCompareFault leftEval,leftTrace,fun base locals saved world external a s => (leftRun base locals saved world external a s).fault_stop⟩
    | value value =>
      obtain ⟨rightOut,sr,mr,rightEval,rightTrace,rightRun⟩ := rightIH
      exact ⟨_,se++sr,me++mr,.enumCompare leftEval rightEval,leftTrace.append rightTrace,
        fun base locals saved world external a s => runtime_call_enum_compare (leftRun base locals saved world external a s) push (rightRun base locals saved world external (some value) (value::s)) operation⟩
  | shiftLeft left count push literal operation ih =>
    obtain ⟨outcome,se,me,evaluated,trace,run⟩ := ih
    exact ⟨_,se,me,.shiftLeft evaluated count,trace,
      fun base locals saved world external a s => runtime_call_shift (run base locals saved world external a s) push literal operation⟩
  | shiftRight left count push literal operation ih =>
    obtain ⟨outcome,se,me,evaluated,trace,run⟩ := ih
    exact ⟨_,se,me,.shiftRight evaluated count,trace,
      fun base locals saved world external a s => runtime_call_shift (run base locals saved world external a s) push literal operation⟩
  | and left branch right label leftIH rightIH =>
    obtain ⟨outcome,se,me,evaluated,trace,run⟩ := leftIH
    cases outcome with
    | trap fault => exact ⟨_,se,me,.andFault evaluated,trace,fun base locals saved world external a s => (run base locals saved world external a s).fault_stop⟩
    | value value =>
      have typed := evaluated.outcome_typed
      cases value with
      | word _ | signedCount4 | signedCount12 | signedCount32 | nominal _ _ => cases typed
      | boolean value => cases value with
        | false => exact ⟨_,se,me,.andStop evaluated,trace,fun base locals saved world external a s => runtime_call_and_stop (run base locals saved world external a s) branch label⟩
        | true =>
          obtain ⟨rightOut,sr,mr,rightEval,rightTrace,rightRun⟩ := rightIH
          exact ⟨_,se++sr,me++mr,.andContinue evaluated rightEval,trace.append rightTrace,
            fun base locals saved world external a s => runtime_call_and_continue (run base locals saved world external a s) branch (rightRun base locals saved world external _ s) label⟩
  | or left branch jump begin right label leftIH rightIH =>
    obtain ⟨outcome,se,me,evaluated,trace,run⟩ := leftIH
    cases outcome with
    | trap fault => exact ⟨_,se,me,.orFault evaluated,trace,fun base locals saved world external a s => (run base locals saved world external a s).fault_stop⟩
    | value value =>
      have typed := evaluated.outcome_typed
      cases value with
      | word _ | signedCount4 | signedCount12 | signedCount32 | nominal _ _ => cases typed
      | boolean value => cases value with
        | true => exact ⟨_,se,me,.orStop evaluated,trace,fun base locals saved world external a s => runtime_call_or_stop (run base locals saved world external a s) branch jump label⟩
        | false =>
          obtain ⟨rightOut,sr,mr,rightEval,rightTrace,rightRun⟩ := rightIH
          exact ⟨_,se++sr,me++mr,.orContinue evaluated rightEval,trace.append rightTrace,
            fun base locals saved world external a s => runtime_call_or_continue (run base locals saved world external a s) branch begin (rightRun base locals saved world external _ s) label⟩
  | nil => exact ⟨.value [],[],[],.nil,.nil,fun _ _ _ _ _ _ _ => .reflexive⟩
  | cons first push rest firstIH restIH =>
    obtain ⟨firstOut,se,me,firstEval,firstTrace,firstRun⟩ := firstIH
    cases firstOut with
    | trap fault => exact ⟨_,se,me,.fault firstEval,firstTrace,fun base locals saved world external a s => (firstRun base locals saved world external a s).fault_stop⟩
    | value value =>
      obtain ⟨restOut,sr,mr,restEval,restTrace,restRun⟩ := restIH
      refine ⟨_,se++sr,me++mr,.cons firstEval restEval,firstTrace.append restTrace,?_⟩
      intro base locals saved world external a s
      have pushed := runtime_call_push (firstRun base locals saved world external a s) push
      cases restOut with
      | trap fault => exact runtime_call_prefix_fault pushed (restRun base locals saved world external _ _)
      | value values =>
        simpa only [RuntimeCallArgumentsRun,Outcome.then,argumentAccumulator,List.reverse_cons,
          List.append_assoc,List.singleton_append] using pushed.trans (restRun base locals saved world external (some value) (value::s))

end Aurora.SourceBinding
