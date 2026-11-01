import SourceBinding.CallProgress
namespace Aurora.SourceBinding
open Aurora.Publication

/-- Byte-backed complete root and actual call-free leaf bodies, plus the checked
    finite descriptor ambiguity guard. No execution summary is a constructor field. -/
structure CallBinding (files : List SourceFile) (root module path : Name) (member bytes : ByteArray) where
  family : CallFamilyBinding files root module path member bytes
  projection : CallProjectionBinding family

def bindCalls (files : List SourceFile) (root module path : Name) (member bytes : ByteArray) :
    Option (CallBinding files root module path member bytes) := do
  let family ← bindCallFamily files root module path member bytes
  return ⟨family,← checkCallProjection family⟩

def CallBinding.sourceInitial (checked : CallBinding files root module path member bytes)
    (world : World) (base : Machine) : SourceCallActive World :=
  ⟨checked.family.shape.source.pieces,(entrySource base checked.family.shape.bindings.length).parameters,
    ⟨base.receiver,world⟩⟩

def CallBinding.machineInitial (checked : CallBinding files root module path member bytes)
    (world : World) (base : Machine) : ActiveCall World :=
  activeAt checked.family.shape.ir.id [] world (preparedEntry base (parameterSlot checked.family.shape.bindings) 0)

def CallBinding.machineEntered (checked : CallBinding files root module path member bytes)
    (world : World) (base : Machine) : ActiveCall World :=
  activeAt checked.family.shape.ir.id [] world
    (preparedEntry base (parameterSlot checked.family.shape.bindings) checked.family.shape.bindings.length)

theorem CallBinding.entry {World ExternalFault : Type}
    (checked : CallBinding files root module path member bytes) (world : World) (base : Machine)
    (arguments : EntryArguments checked.family.shape.bindings base.arguments) :
    LocalCallRuns checked.family.program
        (.running (checked.machineInitial world base) : CallPhase World ExternalFault) []
        (.running (checked.machineEntered world base)) ∧
      CallContext checked.family (checked.sourceInitial world base) (checked.machineEntered world base) := by
  let shape := checked.family.shape
  have run := pure_next_lift (entry_runs shape.entry base arguments)
  rw [← canonical_calls_local (tables shape.ir.publication.artifact.document.reversed.reverse)
    (pieceTargets shape.source.pieces) shape.ir.id] at run
  have lifted := run.local_call_lift (ExternalFault := ExternalFault) (by trivial) [] world
  refine ⟨lifted,⟨rfl,rfl,?_,?_,?_,shape.source.returns,fun _ member => member,?_⟩⟩
  · simp only [machineEntered,sourceInitial,activeAt,prepared_receiver]
  · exact prepared_stack _ _ _
  · change ContextRelated (entrySource base shape.bindings.length)
      ((activeAt shape.ir.id [] world (preparedEntry base (parameterSlot shape.bindings) shape.bindings.length)).frame.inject
        (activeAt shape.ir.id [] world (preparedEntry base (parameterSlot shape.bindings) shape.bindings.length)).shared)
      (parameterSlot shape.bindings)
    rw [activeAt_inject]
    exact entry_context shape.entry base
  · have code := shape.code
    rw [← shape.entry.1] at code
    simpa only [machineEntered,activeAt,CallFrame.ofMachine,prepared_pc] using code

/-- From fresh PC zero, every source execution is realized with the SAME external
    choices and exact ordered trace. Only bounded supplied entry arguments are
    required; assertion success and receiver preservation are not premises. -/
theorem CallBinding.forward {World ExternalFault : Type} {external : ExternalRelation World ExternalFault}
    {events : List (CallEvent World ExternalFault)} {final : SourceCallPhase World ExternalFault}
    (checked : CallBinding files root module path member bytes) (world : World) (base : Machine)
    (arguments : EntryArguments checked.family.shape.bindings base.arguments)
    (run : SourceCallRuns checked.family.sourceBodies external (.running (checked.sourceInitial world base)) events final) :
    ∃ result, CallRuns checked.family.program external (.running (checked.machineInitial world base)) events result ∧
      ExecutionRelated checked.family final result := by
  obtain ⟨entry,context⟩ := checked.entry (ExternalFault := ExternalFault) world base arguments
  obtain ⟨result,later,related⟩ := run.forward checked.projection (.running context)
  exact ⟨result,by simpa only [List.nil_append] using (entry.embed external).trans later,related⟩

/-- Converse finite boundary traces, including suspended requests and all actual
    local/external faults. Nondeterministic outcomes are reflected, not collapsed. -/
theorem CallBinding.reflect {World ExternalFault : Type} {external : ExternalRelation World ExternalFault}
    {events : List (CallEvent World ExternalFault)} {final : CallPhase World ExternalFault}
    (checked : CallBinding files root module path member bytes) (world : World) (base : Machine)
    (arguments : EntryArguments checked.family.shape.bindings base.arguments)
    (run : CallRuns checked.family.program external (.running (checked.machineInitial world base)) events final)
    (boundary : CallBoundary final) :
    ∃ result, SourceCallRuns checked.family.sourceBodies external (.running (checked.sourceInitial world base)) events result ∧
      ExecutionRelated checked.family result final := by
  obtain ⟨entry,context⟩ := checked.entry (ExternalFault := ExternalFault) world base arguments
  obtain ⟨remaining,same,rest⟩ := entry.decompose run boundary
  simp only [List.nil_append] at same
  subst events
  exact rest.reflect checked.projection (.running context) boundary

/-- Local execution reaches its next external suspension or terminal outcome;
    this does not assert a response exists or that external work terminates. -/
theorem CallBinding.first_boundary {World ExternalFault : Type}
    (checked : CallBinding files root module path member bytes) (world : World) (base : Machine)
    (arguments : EntryArguments checked.family.shape.bindings base.arguments)
    (external : ExternalRelation World ExternalFault) :
    ∃ sourceFinal machineFinal events,
      SourceCallRuns checked.family.sourceBodies external (.running (checked.sourceInitial world base)) events sourceFinal ∧
      LocalCallRuns checked.family.program (.running (checked.machineInitial world base)) events machineFinal ∧
      ExecutionRelated checked.family sourceFinal machineFinal ∧ CallBoundary machineFinal := by
  obtain ⟨entry,context⟩ := checked.entry (ExternalFault := ExternalFault) world base arguments
  obtain ⟨sourceFinal,machineFinal,events,sourceRun,machineRun,related,boundary⟩ :=
    context.first_boundary checked.projection external
  exact ⟨sourceFinal,machineFinal,events,sourceRun,
    by simpa only [List.nil_append] using entry.trans machineRun,related,boundary⟩

theorem ExecutionRelated.classification {World ExternalFault : Type}
    {source : SourceCallPhase World ExternalFault} {machine : CallPhase World ExternalFault} (related : ExecutionRelated family source machine)
    (classification : ExternalRequest World → Prop) :
    SourcePendingClassified classification source ↔ PendingClassified classification machine := by
  cases related with
  | running context | returned context | trapped context => exact Iff.rfl
  | waiting context => simp only [SourcePendingClassified,PendingClassified,context.request]
theorem ExecutionRelated.observations (related : ExecutionRelated family source machine) :
    sourceBoundary source = machineBoundary machine := by
  cases related with
  | running context => rfl
  | waiting context => simp only [sourceBoundary,machineBoundary,context.request]
  | returned shared | trapped shared => simp only [sourceBoundary,machineBoundary,shared]

/-- Equality of finite observable trace sets, not uniqueness of an external
    outcome. Both sides use the SAME parameterized external transition relation. -/
theorem CallBinding.finite_correspondence {World ExternalFault : Type}
    (checked : CallBinding files root module path member bytes) (world : World) (base : Machine)
    (arguments : EntryArguments checked.family.shape.bindings base.arguments)
    (external : ExternalRelation World ExternalFault) (events : List (CallEvent World ExternalFault))
    (observation : BoundaryObservation World ExternalFault) :
    (∃ final, SourceCallRuns checked.family.sourceBodies external (.running (checked.sourceInitial world base)) events final ∧
      sourceBoundary final = some observation) ↔
    (∃ final, CallRuns checked.family.program external (.running (checked.machineInitial world base)) events final ∧
      machineBoundary final = some observation) := by
  constructor
  · rintro ⟨final,run,observed⟩
    obtain ⟨result,actual,related⟩ := checked.forward world base arguments run
    exact ⟨result,actual,related.boundary observed⟩
  · rintro ⟨final,run,observed⟩
    have boundary : CallBoundary final := by cases final <;> first | trivial | cases observed
    obtain ⟨result,actual,related⟩ := checked.reflect world base arguments run boundary
    exact ⟨result,actual,related.observations.trans observed⟩
theorem CallBinding.not_locally_diverges {World ExternalFault : Type}
    (checked : CallBinding files root module path member bytes) (world : World) (base : Machine)
    (arguments : EntryArguments checked.family.shape.bindings base.arguments) :
    ¬ LocalCallDiverges checked.family.program
      (.running (checked.machineInitial world base) : CallPhase World ExternalFault) := by
  obtain ⟨_,_,_,_,run,_,boundary⟩ := checked.first_boundary world base arguments
    (fun _ _ _ => False : ExternalRelation World ExternalFault)
  exact run.not_diverges boundary

theorem call_binding_sound (checked : CallBinding files root module path member bytes) :
    GraphReady files root ∧ CallReturns checked.family.shape.source.pieces ∧
      checked.family.shape.stop =
        (functionCode (tables checked.family.shape.ir.publication.artifact.document.reversed.reverse)
          checked.family.shape.ir.id).size :=
  ⟨checked.family.shape.selected.graph,checked.family.shape.source.returns,checked.family.shape.complete⟩
end Aurora.SourceBinding
