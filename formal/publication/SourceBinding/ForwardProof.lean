import SourceBinding.ForwardWrapper
import SourceBinding.CallArgumentProof
import SourceBinding.CallTraceProof
namespace Aurora.SourceBinding
open Aurora.Publication

def ForwardWrapper.target (checked : ForwardWrapper t files root targetModule targetPath wrapperName targetName) :
    OrdinaryDescriptor := ⟨targetName,checked.leaf.identified.id,List.replicate 6 .word,.boolean⟩
def ForwardWrapper.program (checked : ForwardWrapper t files root targetModule targetPath wrapperName targetName) :
    CallProgram := freeCalls t checked.target

theorem ForwardWrapper.call_at (checked : ForwardWrapper t files root targetModule targetPath wrapperName targetName) :
    checked.program checked.wrapper.id checked.callPC = some (.ordinary checked.target) := by
  simp only [ForwardWrapper.program,freeCalls,checked.notLocal]
  exact if_pos checked.invocation

/-- Actual entry and ordered argument evaluation, rather than an assumed call frame. -/
theorem ForwardWrapper.arguments_run
    (checked : ForwardWrapper t files root targetModule targetPath wrapperName targetName)
    (base : Machine) (ready : EntryArguments checked.bindings base.arguments)
    (values : List Value)
    (evaluated : evalCallArguments (entrySource base checked.bindings.length) checked.arguments = .value values) :
    ∃ acc stack,
      EffectRuns (canonicalEffects t checked.wrapper.id)
        (preparedEntry base (parameterSlot checked.bindings) 0) []
        (.next (frameState (preparedEntry base (parameterSlot checked.bindings) checked.bindings.length)
          checked.callPC acc stack)) ∧
      collectArguments false 6 (CallFrame.ofMachine
        (frameState (preparedEntry base (parameterSlot checked.bindings) checked.bindings.length)
          checked.callPC acc stack)) = some (values,[]) := by
  have entry := pure_next_lift (entry_runs checked.entry base ready)
  have args : ArgumentsCode (pureView (canonicalEffects t checked.wrapper.id))
      (parameterSlot checked.bindings) false checked.arguments
      checked.wrapper.selected.function.function.formals.length checked.callPC :=
    .pushed (Or.inl rfl) checked.argumentCode
  obtain ⟨acc,stack,run,collected⟩ := args.effect_values
    (entrySource base checked.bindings.length)
    (preparedEntry base (parameterSlot checked.bindings) checked.bindings.length)
    (entry_context checked.entry base) none [] values evaluated
  rw [← checked.entry.1,prepared_frame] at run
  exact ⟨acc,stack,by simpa using entry.trans run,by simpa using collected⟩

theorem ParameterArguments.word_values {kinds : List GuardType} {args : CallArguments kinds}
    (ordered : ParameterArguments start args) (allWords : kinds = List.replicate kinds.length .word)
    (source : SourceState)
    (ready : ∀ index, start ≤ index → index < start + kinds.length →
      ∃ value, readScalar .word (source.parameters index) = .value value) :
    ∃ values, evalCallArguments source args = .value values := by
  induction ordered with
  | nil => exact ⟨[],rfl⟩
  | @cons start kinds tail kind name ordered ih =>
    have head : kind = .word := by
      have equal := congrArg List.head? allWords
      simpa only [List.length_cons,List.replicate_succ,List.head?_cons,Option.some.injEq] using equal
    have rest : kinds = List.replicate kinds.length .word := by
      have equal := congrArg List.tail allWords
      simpa using equal
    subst kind
    obtain ⟨value,read⟩ := ready start (Nat.le_refl _) (by simp only [List.length_cons]; omega)
    obtain ⟨values,evaluated⟩ := ih rest (fun index lower upper => ready index (by omega) (by simp only [List.length_cons]; omega))
    exact ⟨value :: values,by simp only [evalCallArguments,evalGuard,read,Outcome.then,evaluated]⟩

theorem ForwardWrapper.arguments_total
    (checked : ForwardWrapper t files root targetModule targetPath wrapperName targetName)
    (base : Machine) (ready : EntryArguments checked.bindings base.arguments) :
    ∃ values, evalCallArguments (entrySource base checked.bindings.length) checked.arguments = .value values := by
  apply checked.ordered.word_values (by simp)
  intro index lower upper
  have size : checked.bindings.length = 6 := by
    have h := congrArg List.length checked.wrapperParameters
    simp only [List.length_map,List.length_replicate] at h
    exact checked.entry.1.trans h
  have bound : index < checked.bindings.length := by simpa [size] using upper
  have kind := checked.entry.argument_kinds (kinds := List.replicate 6 .word)
    (by simpa using checked.wrapperParameters) bound
  have word : parameterKind checked.bindings index = .word := by
    simpa only [List.getElem?_replicate,if_pos (show index < 6 by omega),Option.some.injEq] using kind.symm
  obtain ⟨value,actual,typed⟩ := ready index bound
  exact ⟨value,by simpa [entrySource,bound,actual,word] using typed⟩

theorem read_value_input (kind : GuardType) (input : Option Value) (value : Value)
    (read : readScalar kind input = .value value) : input = some value := by
  cases input with
  | none => cases read
  | some actual =>
    cases kind <;> cases actual <;> simp_all [readScalar]
    all_goals split at read <;> simp_all

/-- Evaluation of ordered parameter expressions retains actual caller values. -/
theorem ParameterArguments.values_lookup {kinds : List GuardType} {args : CallArguments kinds}
    (ordered : ParameterArguments start args) (source : SourceState) (values : List Value)
    (evaluated : evalCallArguments source args = .value values) :
    ∀ index, index < kinds.length → source.parameters (start + index) = values[index]? := by
  induction ordered generalizing values with
  | nil => intro index bound; simp at bound
  | @cons start kinds tail kind name ordered ih =>
    cases first : evalGuard source (.parameter kind name start) with
    | trap fault => simp only [evalCallArguments,first,Outcome.then] at evaluated; cases evaluated
    | value value =>
      cases rest : evalCallArguments source tail with
      | trap fault => simp only [evalCallArguments,first,Outcome.then,rest] at evaluated; cases evaluated
      | value vals =>
        simp only [evalCallArguments,first,Outcome.then,rest,Outcome.value.injEq] at evaluated
        subst values
        intro index bound
        cases index with
        | zero => simpa using read_value_input kind _ value first
        | succ index => simpa [Nat.add_assoc,Nat.add_comm,Nat.add_left_comm] using
            (ih vals rest index (by simpa using bound))

/-- Internal composition helper. The public exact-policy theorem discharges the
    source evaluation premise from bounded actual arguments, for both booleans. -/
theorem ForwardWrapper.returned_run
    (checked : ForwardWrapper t files root targetModule targetPath wrapperName targetName)
    (base : Machine) (world : World)
    (ready : EntryArguments checked.bindings base.arguments)
    (values : List Value)
    (evaluated : evalCallArguments (entrySource base checked.bindings.length) checked.arguments = .value values)
    (value : Value)
    (returned : evalBody checked.leaf.method.body
      (entrySource ((freshCallFrame values).inject ⟨base.receiver,world⟩) checked.leaf.core.bindings.length) =
      ⟨.returned value (entrySource ((freshCallFrame values).inject ⟨base.receiver,world⟩)
        checked.leaf.core.bindings.length),[]⟩) :
    ∃ final : ActiveCall World,
      LocalCallRuns (ExternalFault := ExternalFault) checked.program
        (.running (activeAt checked.wrapper.id [] world (preparedEntry base (parameterSlot checked.bindings) 0)))
        [.ordinaryInvoke checked.target values,.ordinaryReturn checked.target value]
        (.returned value final) ∧ final.shared.receiver = base.receiver := by
  obtain ⟨acc,stack,argsRun,collected⟩ := checked.arguments_run base ready values evaluated
  let before := frameState (preparedEntry base (parameterSlot checked.bindings) checked.bindings.length)
    checked.callPC acc stack
  let continuation : CallFrame := {CallFrame.ofMachine before with pc := checked.callPC + 1,stack := []}
  let saved : SavedCall := ⟨checked.target,checked.wrapper.id,continuation⟩
  let calleeBase := (freshCallFrame values).inject (⟨base.receiver,world⟩ : CallShared World)
  have projection : ∀ id, localProgram checked.program id = canonicalEffects t id :=
    fun id => free_calls_local t checked.target id
  rw [← projection checked.wrapper.id] at argsRun
  have prefixRun := argsRun.local_call_lift (by trivial) [] world (ExternalFault := ExternalFault)
  have called : callStep (ExternalFault := ExternalFault) checked.program
      (activeAt checked.wrapper.id [] world before) =
      (.running (activeAt checked.target.id [saved] world calleeBase),
        [.ordinaryInvoke checked.target values]) := by
    have count : checked.target.parameters.length = 6 := rfl
    simp only [callStep,activeAt,CallFrame.ofMachine,before,frameState,checked.call_at,count]
    simp only [frameState,CallFrame.ofMachine] at collected
    simp only [collected,continuation,saved,calleeBase,CallFrame.ofMachine,before,
      frameState,freshCallFrame,CallFrame.inject,prepared_receiver]
  have invoked := prefixRun.trans (LocalCallRuns.step called .reflexive)
  have leafReady : EntryArguments checked.leaf.core.bindings calleeBase.arguments :=
    checked.leaf.core.entry.evaluated_arguments
      (kinds := List.replicate 6 .word) (by simpa using checked.leafParameters)
      checked.arguments (entrySource base checked.bindings.length) values evaluated
  obtain ⟨result,leafRun,related,terminal⟩ := checked.leaf.core.executes calleeBase leafReady
  change evalBody checked.leaf.method.body (entrySource calleeBase checked.leaf.core.bindings.length) = _ at returned
  rw [returned] at leafRun related
  cases result with
  | next machine | trap fault machine => cases related
  | returned actual machine =>
    obtain ⟨same,receiver,emptyStack⟩ := related
    subst actual
    have fresh : preparedEntry calleeBase (parameterSlot checked.leaf.core.bindings) 0 = calleeBase := rfl
    rw [fresh,← projection checked.leaf.identified.id] at leafRun
    have executed := leafRun.local_call_lift (by trivial) [saved] world (ExternalFault := ExternalFault)
    have receiverBase : machine.receiver = base.receiver := receiver
    let resumed : ActiveCall World :=
      ⟨checked.wrapper.id,{continuation with accumulator := some value},[],⟨base.receiver,world⟩⟩
    have whole : LocalCallRuns (ExternalFault := ExternalFault) checked.program
        (.running (activeAt checked.wrapper.id [] world (preparedEntry base (parameterSlot checked.bindings) 0)))
        [.ordinaryInvoke checked.target values,.ordinaryReturn checked.target value] (.running resumed) := by
      simpa only [finishEffect,returnToCaller,activeAt,saved,resumed,receiverBase,
        List.nil_append,List.append_nil,List.cons_append] using invoked.trans executed
    let final : ActiveCall World := resumed
    have ret : callStep (ExternalFault := ExternalFault) checked.program resumed = (.returned value final,[]) := by
      have pure : localProgram checked.program checked.wrapper.id (checked.callPC + 1) = some (.pure .ret) := by
        rw [projection]; exact checked.returning
      have supported : LocalSupported (effectStep (localProgram checked.program resumed.callable)
          (resumed.frame.inject resumed.shared)).execution := by
        simp [resumed,continuation,CallFrame.inject,effectStep,pure,pureView,step,retainState,LocalSupported]
      rw [supported_local_step checked.program resumed supported]
      simp [localCallStep,resumed,final,continuation,CallFrame.inject,effectStep,pure,pureView,step,
        retainState,returnToCaller,CallFrame.ofMachine,CallShared.commit,EffectExecution.state]
    refine ⟨final,?_,rfl⟩
    simpa using whole.trans (LocalCallRuns.step ret .reflexive)

end Aurora.SourceBinding
