import SourceBinding.CallGuardPrefix
namespace Aurora.SourceBinding

/-- A finite source path before any external response. This is a projection of
    an actual local machine path, not an assumption of guard/callee success. -/
def ReachesRequest (bodies : SourceCallProgram) (phase : SourceCallPhase World ExternalFault)
    (request : SourceWaiting World) : Prop :=
  ∃ events, SourceCallRuns bodies (fun _ _ _ => False) phase events (.waiting request)

theorem ReachesRequest.step
    (reached : ReachesRequest bodies (.running active : SourceCallPhase World ExternalFault) request) :
    ReachesRequest bodies (sourceCallStep (ExternalFault := ExternalFault) bodies active).1 request := by
  obtain ⟨events,run⟩ := reached
  cases run with
  | step first tail =>
    cases first with
    | «local» actual => exact ⟨_,by simpa only [actual] using tail⟩

theorem ReachesRequest.waiting
    (reached : ReachesRequest bodies (.waiting pending : SourceCallPhase World ExternalFault) request) : pending = request := by
  obtain ⟨events,run⟩ := reached
  cases run with
  | reflexive => rfl
  | step first tail => cases first with | resume impossible actual => exact False.elim impossible

theorem ReachesRequest.not_returned :
    ¬ ReachesRequest bodies (.returned value shared : SourceCallPhase World ExternalFault) request := by
  rintro ⟨events,run⟩
  cases run with | step first tail => cases first

theorem ReachesRequest.not_trapped :
    ¬ ReachesRequest bodies (.trapped fault shared : SourceCallPhase World ExternalFault) request := by
  rintro ⟨events,run⟩
  cases run with | step first tail => cases first

theorem ReachesRequest.not_exhausted :
    ¬ ReachesRequest bodies (.exhausted shared : SourceCallPhase World ExternalFault) request := by
  rintro ⟨events,run⟩
  cases run with | step first tail => cases first

theorem ReachesRequest.rejection {guard : GuardExpr .boolean}
    (reached : ReachesRequest bodies (.running ⟨.localBody
      (.branch guard (.seq (.returnValue .boolean (.boolLit false)) .skip)) :: rest,arguments,shared⟩ :
        SourceCallPhase World ExternalFault) request) :
    evalGuard (shared.source arguments) guard = .value (.boolean false) ∧
      ReachesRequest bodies (.running ⟨rest,arguments,shared⟩ : SourceCallPhase World ExternalFault) request := by
  have later := reached.step
  cases evaluated : evalGuard (shared.source arguments) guard with
  | trap fault =>
    simp only [sourceCallStep,evalBody,sourceExpression,evaluated,sourceBodyResult] at later
    exact False.elim (ReachesRequest.not_trapped later)
  | value value =>
    cases value with
    | word value =>
      simp only [sourceCallStep,evalBody,sourceExpression,evaluated,sourceBodyResult] at later
      exact False.elim (ReachesRequest.not_trapped later)
    | boolean boolean =>
      cases boolean with
      | true =>
        simp only [sourceCallStep,evalBody,sourceExpression,evaluated,evalGuard,sourceBodyResult] at later
        exact False.elim (ReachesRequest.not_returned later)
      | false =>
        refine ⟨rfl,?_⟩
        simpa only [sourceCallStep,evalBody,sourceExpression,evaluated,sourceBodyResult,SourceExecution.state] using later

/-- Reaching a subsequent request forces an actual ordinary return, not an
    assumed assertion truth or successful callee summary. -/
theorem ReachesRequest.ordinary {parameters : Nat → Option Value}
    {target : OrdinaryDescriptor} {arguments : CallArguments target.parameters}
    (reached : ReachesRequest bodies (.running ⟨.invoke (.ordinary target arguments) :: rest,parameters,shared⟩ :
      SourceCallPhase World ExternalFault) request) :
    ∃ values body value final,
      evalCallArguments (shared.source parameters) arguments = .value values ∧ bodies target = some body ∧
      (evalBody body (shared.source (fun index => values[index]?))).execution = .returned value final ∧
      ReachesRequest bodies (.running ⟨rest,parameters,⟨final.fields,shared.world⟩⟩ :
        SourceCallPhase World ExternalFault) request := by
  have later := reached.step
  cases evaluated : evalCallArguments (shared.source parameters) arguments with
  | trap fault =>
    simp only [sourceCallStep,evaluated] at later
    exact False.elim (ReachesRequest.not_trapped later)
  | value values =>
    simp only [sourceCallStep,evaluated,sourceOrdinary] at later
    cases bodyEq : bodies target with
    | none => simp only [bodyEq] at later; exact False.elim (ReachesRequest.not_trapped later)
    | some body =>
      simp only [bodyEq] at later
      cases bodyResult : (evalBody body (shared.source (fun index => values[index]?))).execution with
      | next final =>
        simp only [bodyResult] at later
        exact False.elim (ReachesRequest.not_exhausted later)
      | trap fault final =>
        simp only [bodyResult] at later
        exact False.elim (ReachesRequest.not_trapped later)
      | returned value final =>
        exact ⟨values,body,value,final,rfl,rfl,bodyResult,
          by simpa only [bodyResult,SourceExecution.state] using later⟩

theorem ReachesRequest.resource {parameters : Nat → Option Value}
    {target : ResourceDescriptor} {arguments : CallArguments target.parameters}
    (reached : ReachesRequest bodies (.running ⟨.invoke (.resourceAssert target arguments) :: rest,parameters,shared⟩ :
      SourceCallPhase World ExternalFault) request) :
    ∃ values, evalCallArguments (shared.source parameters) arguments = .value values ∧
      request = ⟨⟨target,values,shared⟩,rest,parameters⟩ := by
  have later := reached.step
  cases evaluated : evalCallArguments (shared.source parameters) arguments with
  | trap fault =>
    simp only [sourceCallStep,evaluated] at later
    exact False.elim (ReachesRequest.not_trapped later)
  | value values =>
    simp only [sourceCallStep,evaluated] at later
    exact ⟨values,rfl,later.waiting.symm⟩
/-- The receiver from the actually returned source body, not a framed summary. -/
theorem GuardedCallPrefix.return_preserves_guard (guarded : GuardedCallPrefix checked)
    (caller : SourceState) (values : List Value)
    (evaluated : evalCallArguments caller guarded.arguments = .value values)
    (returned : (evalBody guarded.leaf.source.body ⟨caller.fields,fun index => values[index]?⟩).execution =
      .returned value final) :
    evalGuard ⟨final.fields,caller.parameters⟩ guarded.guard = evalGuard caller guarded.guard := by
  obtain ⟨result,run,terminal,preserved⟩ := guarded.preserves_guard caller values evaluated
  let base := (freshCallFrame values).inject (⟨caller.fields,()⟩ : CallShared Unit)
  have ready := eval_call_arguments_ready caller guarded.arguments evaluated
  have entry : EntryArguments guarded.leaf.body.bindings base.arguments :=
    ready.entry guarded.leaf.body.entry guarded.leaf.identity.parameters
  have sizes := congrArg List.length guarded.leaf.identity.parameters
  simp only [List.length_map] at sizes
  have length : guarded.leaf.body.bindings.length = values.length := by
    have entryLength := guarded.leaf.body.entry.1
    have valueLength := ready.length
    omega
  have sourceEq := entrySource_values (⟨caller.fields,()⟩ : CallShared Unit) values guarded.leaf.body.bindings length
  obtain ⟨_,related⟩ := guarded.leaf.body.terminal_correspondence base entry run terminal
  change entrySource base guarded.leaf.body.bindings.length = _ at sourceEq
  rw [sourceEq] at related
  simp only [CallShared.source] at related
  rw [returned] at related
  cases result with
  | next machine => cases related
  | trap fault machine => cases related
  | returned actual machine =>
    simp only [BodyResultRelated] at related
    simpa only [EffectExecution.state,related.2.1] using preserved
/-- Before any response, reaching the first request derives guard acceptance
    through the actual rejecting branch and returned ordinary callee. -/
theorem GuardedCallPrefix.reached_guard {World ExternalFault : Type} {pending : SourceWaiting World}
    (guarded : GuardedCallPrefix checked) (parameters : Nat → Option Value) (shared : CallShared World)
    (reached : ReachesRequest checked.family.sourceBodies
      (.running ⟨checked.family.shape.source.pieces,parameters,shared⟩ : SourceCallPhase World ExternalFault) pending) :
    pending.arguments = parameters ∧ pending.request.target = guarded.resource ∧
      evalCallArguments (pending.request.before.source parameters) guarded.resourceArguments =
        .value pending.request.arguments ∧
      evalGuard (pending.request.before.source parameters) guarded.guard = .value (.boolean false) := by
  rw [guarded.order] at reached
  obtain ⟨accepted,afterGuard⟩ := reached.rejection
  obtain ⟨values,body,value,final,evaluated,bodyEq,returned,afterCall⟩ := afterGuard.ordinary
  have selected : checked.family.sourceBodies guarded.target = some guarded.leaf.source.body := by
    simp only [CallFamilyBinding.sourceBodies,guarded.selected,Option.map_some]
  have same : body = guarded.leaf.source.body := Option.some.inj (bodyEq.symm.trans selected)
  subst body
  have preserved := guarded.return_preserves_guard (shared.source parameters) values evaluated returned
  obtain ⟨resourceValues,resourceEvaluated,pendingEq⟩ := afterCall.resource
  subst pending
  exact ⟨rfl,rfl,resourceEvaluated,preserved.trans accepted⟩
end Aurora.SourceBinding
