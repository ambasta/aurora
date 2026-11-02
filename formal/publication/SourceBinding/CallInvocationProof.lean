import SourceBinding.CallLocalProof
namespace Aurora.SourceBinding
open Aurora.Publication

theorem ArgumentsCode.root_prefix {kinds : List GuardType} {arguments : CallArguments kinds}
    {family : CallFamilyBinding files root module path member bytes}
    (code : ArgumentsCode (pureView (canonicalEffects
      (tables family.shape.ir.publication.artifact.document.reversed.reverse) family.shape.ir.id))
      (parameterSlot family.shape.bindings) resource arguments start stop)
    (source : SourceState) (base : Machine) (context : ContextRelated source base (parameterSlot family.shape.bindings))
    (world : World) (external : ExternalRelation World ExternalFault) (values : List Value)
    (evaluated : evalCallArguments source arguments = .value values) :
    ∃ acc stack, CallRuns family.program external
        (.running (activeAt family.shape.ir.id [] world (frameState base start base.accumulator []))) []
        (.running (activeAt family.shape.ir.id [] world (frameState base stop acc stack))) ∧
      collectArguments resource kinds.length (CallFrame.ofMachine (frameState base stop acc stack)) = some (values,[]) := by
  obtain ⟨acc,stack,run,collected⟩ := code.effect_values source base context base.accumulator [] values evaluated
  rw [← canonical_calls_local (tables family.shape.ir.publication.artifact.document.reversed.reverse)
    (pieceTargets family.shape.source.pieces) family.shape.ir.id] at run
  have lifted := run.call_lift (by trivial) [] world external
  exact ⟨acc,stack,lifted,collected⟩

theorem ArgumentsCode.root_fault
    {family : CallFamilyBinding files root module path member bytes}
    {kinds : List GuardType} {arguments : CallArguments kinds}
    (code : ArgumentsCode (pureView (canonicalEffects
      (tables family.shape.ir.publication.artifact.document.reversed.reverse) family.shape.ir.id))
      (parameterSlot family.shape.bindings) resource arguments start stop)
    (source : SourceCallActive World) (base : Machine)
    (context : ContextRelated (source.shared.source source.arguments) base (parameterSlot family.shape.bindings))
    (external : ExternalRelation World ExternalFault) (fault : Fault)
    (evaluated : evalCallArguments (source.shared.source source.arguments) arguments = .trap fault) :
    ∃ final, CallRuns family.program external
        (.running (activeAt family.shape.ir.id [] source.shared.world (frameState base start base.accumulator []))) [] final ∧
      ExecutionRelated family (.trapped (.local (.scalar fault)) source.shared) final := by
  obtain ⟨machine,run,receiver,parameters⟩ := code.effect_fault (source.shared.source source.arguments) base context
    base.accumulator [] fault evaluated
  rw [← canonical_calls_local (tables family.shape.ir.publication.artifact.document.reversed.reverse)
    (pieceTargets family.shape.source.pieces) family.shape.ir.id] at run
  have supported : LocalSupported (.trap (.scalar fault) machine) := by
    cases fault <;> try trivial
    exact False.elim (eval_call_arguments_supported _ arguments evaluated)
  have lifted := run.call_lift supported [] source.shared.world external
  refine ⟨.trapped (.local (.scalar fault)) (activeAt family.shape.ir.id [] source.shared.world machine),lifted,.trapped ?_⟩
  change CallShared.mk machine.receiver source.shared.world = source.shared
  rw [receiver,funext context.fields]
  rfl

/-- Invoking a resource freezes the exact checked descriptor and evaluated
    arguments. No response, mutation or favorable result is chosen here. -/
theorem resource_piece_value
    {family : CallFamilyBinding files root module path member bytes}
    (projection : CallProjectionBinding family) {target : ResourceDescriptor}
    {arguments : CallArguments target.parameters} {rest : List CallPiece}
    (code : ArgumentsCode (pureView (canonicalEffects
      (tables family.shape.ir.publication.artifact.document.reversed.reverse) family.shape.ir.id))
      (parameterSlot family.shape.bindings) true arguments start middle)
    (meaning : InvocationAt (tables family.shape.ir.publication.artifact.document.reversed.reverse)
      family.shape.ir.id middle (.resource target))
    (require : canonicalEffects (tables family.shape.ir.publication.artifact.document.reversed.reverse)
      family.shape.ir.id (middle + 1) = some .require)
    (tail : CallPiecesCode (tables family.shape.ir.publication.artifact.document.reversed.reverse)
      family.shape.ir.id (parameterSlot family.shape.bindings) rest (middle + 2) family.shape.stop)
    (source : SourceCallActive World) (base : Machine)
    (pieces : source.pieces = .invoke (.resourceAssert target arguments) :: rest)
    (context : ContextRelated (source.shared.source source.arguments) base (parameterSlot family.shape.bindings))
    (returns : CallReturns source.pieces)
    (members : ∀ piece ∈ source.pieces, piece ∈ family.shape.source.pieces)
    (external : ExternalRelation World ExternalFault) (values : List Value)
    (evaluated : evalCallArguments (source.shared.source source.arguments) arguments = .value values) :
    ∃ final, CallRuns family.program external
        (.running (activeAt family.shape.ir.id [] source.shared.world (frameState base start base.accumulator [])))
        (sourceCallStep family.sourceBodies source).2 final ∧
      ExecutionRelated family (sourceCallStep family.sourceBodies source).1 final := by
  obtain ⟨acc,stack,run,collected⟩ := code.root_prefix (source.shared.source source.arguments) base context
    source.shared.world external values evaluated
  have present : .invoke (.resourceAssert target arguments) ∈ family.shape.source.pieces :=
    members _ (pieces ▸ List.mem_cons_self)
  have atCall := projection.root_call (pieceTargets.member _ present) meaning
  let frame := frameState base middle acc stack
  let active := activeAt family.shape.ir.id [] source.shared.world frame
  have receiver : base.receiver = source.shared.receiver := funext context.fields
  have shared : CallShared.mk base.receiver source.shared.world = source.shared := by
    rw [receiver]
  let request : ExternalRequest World := ⟨target,values,source.shared⟩
  let continuation : CallFrame := {CallFrame.ofMachine frame with pc := middle + 1,stack := []}
  let waiting : WaitingCall World := ⟨request,family.shape.ir.id,continuation,[]⟩
  have called : callStep (ExternalFault := ExternalFault) family.program active =
      (.waiting waiting,[.externalInvoke request]) := by
    simp only [callStep,active,activeAt,frame,frameState,CallFrame.ofMachine,atCall,TypedInvocation.target,
      targetOperation] at *
    simp only [collected,waiting,request,continuation,frame,frameState,CallFrame.ofMachine,shared]
  have last := CallRuns.one (external := external) (.local called)
  refine ⟨.waiting waiting,?_,?_⟩
  · simpa only [sourceCallStep,pieces,evaluated,List.nil_append,request] using run.trans last
  · simp only [sourceCallStep,pieces,evaluated]
    apply ExecutionRelated.waiting
    refine ⟨rfl,rfl,rfl,rfl,?_,CallReturns.invoke_tail (pieces ▸ returns),?_,require,?_⟩
    · exact ⟨fun _ => rfl,context.parameters⟩
    · intro piece member
      exact members piece (pieces ▸ List.mem_cons_of_mem _ member)
    · simpa only [waiting,continuation,Nat.add_assoc] using tail
theorem ordinary_piece_value
    {family : CallFamilyBinding files root module path member bytes}
    (projection : CallProjectionBinding family) {target : ScalarOrdinary}
    {arguments : CallArguments target.parameters} {rest : List CallPiece}
    (code : ArgumentsCode (pureView (canonicalEffects
      (tables family.shape.ir.publication.artifact.document.reversed.reverse) family.shape.ir.id))
      (parameterSlot family.shape.bindings) false arguments start middle)
    (meaning : InvocationAt (tables family.shape.ir.publication.artifact.document.reversed.reverse)
      family.shape.ir.id middle (.ordinary target))
    (tail : CallPiecesCode (tables family.shape.ir.publication.artifact.document.reversed.reverse)
      family.shape.ir.id (parameterSlot family.shape.bindings) rest (middle + 1) family.shape.stop)
    (source : SourceCallActive World) (base : Machine)
    (pieces : source.pieces = .invoke (.ordinary target arguments) :: rest)
    (context : ContextRelated (source.shared.source source.arguments) base (parameterSlot family.shape.bindings))
    (returns : CallReturns source.pieces)
    (members : ∀ piece ∈ source.pieces, piece ∈ family.shape.source.pieces)
    (external : ExternalRelation World ExternalFault) (values : List Value)
    (evaluated : evalCallArguments (source.shared.source source.arguments) arguments = .value values) :
    ∃ final, CallRuns family.program external
        (.running (activeAt family.shape.ir.id [] source.shared.world (frameState base start base.accumulator [])))
        (sourceCallStep family.sourceBodies source).2 final ∧
      ExecutionRelated family (sourceCallStep family.sourceBodies source).1 final := by
  obtain ⟨acc,stack,run,collected⟩ := code.root_prefix (source.shared.source source.arguments) base context
    source.shared.world external values evaluated
  have present : .invoke (.ordinary target arguments) ∈ family.shape.source.pieces :=
    members _ (pieces ▸ List.mem_cons_self)
  obtain ⟨leaf,found,bodyPresent⟩ := family.source_body_present (OrdinaryOccurs.of_member present)
  have atCall := projection.root_call (pieceTargets.member _ present) meaning
  let frame := frameState base middle acc stack
  let active := activeAt family.shape.ir.id [] source.shared.world frame
  have receiver : base.receiver = source.shared.receiver := funext context.fields
  have shared : CallShared.mk base.receiver source.shared.world = source.shared := by rw [receiver]
  let continuation : CallFrame := {CallFrame.ofMachine frame with pc := middle + 1,stack := []}
  let saved : SavedCall := ⟨target,family.shape.ir.id,continuation⟩
  let callee := activeAt target.id [saved] source.shared.world ((freshCallFrame values).inject source.shared)
  have called : callStep (ExternalFault := ExternalFault) family.program active =
      (.running callee,[.ordinaryInvoke target values]) := by
    simp only [callStep,active,activeAt,frame,frameState,CallFrame.ofMachine,atCall,TypedInvocation.target,
      targetOperation] at *
    simp only [ScalarOrdinary.arity,collected,callee,activeAt,saved,continuation,frame,frameState,CallFrame.ofMachine,
      freshCallFrame,CallFrame.inject,shared,ScalarOrdinary.id]
  have invoked := run.trans (CallRuns.one (external := external) (.local called))
  obtain ⟨result,executed,related,terminal⟩ := leaf.call_executes family.program
    (canonical_calls_local _ _ _) source.shared values
    (eval_call_arguments_ready _ arguments evaluated) [saved] external
  have full := invoked.trans executed
  cases outcome : (evalBody leaf.source.body (source.shared.source (fun index => values[index]?))).execution with
  | next next => exact False.elim (leaf.source.returns.no_fallthrough _ next outcome)
  | returned value state =>
    cases result with
    | next _ | trap _ _ => simp only [outcome,BodyResultRelated] at related
    | returned actual machine =>
      have same : value = actual ∧ machine.receiver = state.fields ∧ machine.stack = [] := by
        simpa only [outcome,BodyResultRelated] using related
      have valueSame := same.1
      subst actual
      let final : ActiveCall World := ⟨family.shape.ir.id,{continuation with accumulator := some value},[],
        ⟨machine.receiver,source.shared.world⟩⟩
      simp only [sourceCallStep,pieces,evaluated,sourceOrdinary,bodyPresent,outcome]
      refine ⟨.running final,?_,.running ?_⟩
      · simpa only [finishEffect,returnToCaller,activeAt,saved,final,List.nil_append,List.cons_append,
          List.append_assoc,List.append_nil] using full
      · refine ⟨rfl,rfl,?_,rfl,?_,CallReturns.invoke_tail (pieces ▸ returns),?_,?_⟩
        · exact congrArg (fun fields => CallShared.mk fields source.shared.world) same.2.1
        · exact ⟨fun index => congrFun same.2.1 index,context.parameters⟩
        · intro piece member; exact members piece (pieces ▸ List.mem_cons_of_mem _ member)
        · exact tail
  | trap fault state =>
    cases result with
    | next _ | returned _ _ => simp only [outcome,BodyResultRelated] at related
    | trap actual machine =>
      have same : fault = actual ∧ machine.receiver = state.fields := by
        simpa only [outcome,BodyResultRelated] using related
      have faultSame := same.1
      subst actual
      simp only [sourceCallStep,pieces,evaluated,sourceOrdinary,bodyPresent,outcome]
      refine ⟨.trapped (.local fault) (activeAt target.id [saved] source.shared.world machine),?_,.trapped ?_⟩
      · simpa only [finishEffect,List.nil_append,List.cons_append,List.append_nil] using full
      · exact congrArg (fun fields => CallShared.mk fields source.shared.world) same.2
end Aurora.SourceBinding
