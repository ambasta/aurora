import SourceBinding.ForwardProof
import SourceBinding.LeafBinding
namespace Aurora.SourceBinding

/-- Total numerical policy at the actual wrapper PC zero. Actual argument values,
    source evaluation and callee return are derived, not assumed successful. -/
theorem ForwardWrapper.numeric_run
    (checked : ForwardWrapper t files root targetModule targetPath wrapperName targetName)
    (shape : LeafShape checked.leaf) (base : Machine) (world : World)
    (ready : EntryArguments checked.bindings base.arguments) :
    ∃ l p m b s x values final,
      base.arguments 0 = some (.word l) ∧ base.arguments 1 = some (.word p) ∧
      base.arguments 2 = some (.word m) ∧ base.arguments 3 = some (.word b) ∧
      base.arguments 4 = some (.word s) ∧ base.arguments 5 = some (.word x) ∧
      LocalCallRuns (ExternalFault := ExternalFault) checked.program
        (.running (activeAt checked.wrapper.id [] world (preparedEntry base (parameterSlot checked.bindings) 0)))
        [.ordinaryInvoke checked.target values,
          .ordinaryReturn checked.target (.boolean (leafNumeric l p m b s x))]
        (.returned (.boolean (leafNumeric l p m b s x)) final) ∧
      final.shared.receiver = base.receiver ∧
      (leafNumeric l p m b s x = true ↔ LeafAccepted l p m b s x) := by
  obtain ⟨values,evaluated⟩ := checked.arguments_total base ready
  let calleeBase := (freshCallFrame values).inject (⟨base.receiver,world⟩ : CallShared World)
  have leafReady : EntryArguments checked.leaf.core.bindings calleeBase.arguments :=
    checked.leaf.core.entry.evaluated_arguments
      (kinds := List.replicate 6 .word) (by simpa using checked.leafParameters)
      checked.arguments (entrySource base checked.bindings.length) values evaluated
  obtain ⟨l,p,m,b,s,x,hl,hp,hm,hb,hs,hx,vl,vp,vm,vb,vs,vx,body⟩ :=
    shape.evaluates calleeBase leafReady
  obtain ⟨final,run,receiver⟩ := checked.returned_run base world ready values evaluated
    (.boolean (leafNumeric l p m b s x)) body
  have lookup := checked.ordered.values_lookup (entrySource base checked.bindings.length) values evaluated
  have length : checked.bindings.length = 6 := by
    have h := congrArg List.length checked.wrapperParameters
    simp only [List.length_map,List.length_replicate] at h
    exact checked.entry.1.trans h
  have input (index : Nat) (bound : index < 6) :
      base.arguments index = calleeBase.arguments index := by
    simpa [entrySource,length,bound,calleeBase,freshCallFrame,CallFrame.inject] using
      lookup index (by simpa using bound)
  refine ⟨l,p,m,b,s,x,values,final,?_,?_,?_,?_,?_,?_,run,receiver,?_⟩
  · exact (input 0 (by decide)).trans vl
  · exact (input 1 (by decide)).trans vp
  · exact (input 2 (by decide)).trans vm
  · exact (input 3 (by decide)).trans vb
  · exact (input 4 (by decide)).trans vs
  · exact (input 5 (by decide)).trans vx
  · exact leaf_numeric_iff

theorem CallRuns.from_returned
    (run : CallRuns program external (.returned value active) events final) :
    events = [] ∧ final = .returned value active := by
  cases run with
  | reflexive => exact ⟨rfl,rfl⟩
  | step first rest => cases first

/-- Every actual true-returning run, not merely the constructed favorable run. -/
theorem ForwardWrapper.accepted_true {World ExternalFault : Type}
    {external : ExternalRelation World ExternalFault}
    {actual : ActiveCall World} {events : List (CallEvent World ExternalFault)}
    (checked : ForwardWrapper t files root targetModule targetPath wrapperName targetName)
    (shape : LeafShape checked.leaf) (base : Machine) (world : World)
    (ready : EntryArguments checked.bindings base.arguments)
    (run : CallRuns checked.program external
      (.running (activeAt checked.wrapper.id [] world (preparedEntry base (parameterSlot checked.bindings) 0)))
      events (.returned (.boolean true) actual)) :
    ∃ l p m b s x,
      base.arguments 0 = some (.word l) ∧ base.arguments 1 = some (.word p) ∧
      base.arguments 2 = some (.word m) ∧ base.arguments 3 = some (.word b) ∧
      base.arguments 4 = some (.word s) ∧ base.arguments 5 = some (.word x) ∧
      LeafAccepted l p m b s x := by
  obtain ⟨l,p,m,b,s,x,values,final,vl,vp,vm,vb,vs,vx,localRun,receiver,numeric⟩ :=
    checked.numeric_run shape base world ready (ExternalFault := ExternalFault)
  obtain ⟨rest,trace,tail⟩ := localRun.decompose run (by trivial)
  obtain ⟨empty,equal⟩ := tail.from_returned
  have value := (CallPhase.returned.inj equal).1
  have accepted : leafNumeric l p m b s x = true := (Value.boolean.inj value).symm
  exact ⟨l,p,m,b,s,x,vl,vp,vm,vb,vs,vx,numeric.mp accepted⟩

theorem ForwardWrapper.not_locally_diverges
    (checked : ForwardWrapper t files root targetModule targetPath wrapperName targetName)
    (shape : LeafShape checked.leaf) (base : Machine) (world : World)
    (ready : EntryArguments checked.bindings base.arguments) :
    ¬ LocalCallDiverges (ExternalFault := ExternalFault) checked.program
      (.running (activeAt checked.wrapper.id [] world (preparedEntry base (parameterSlot checked.bindings) 0))) := by
  obtain ⟨l,p,m,b,s,x,values,final,vl,vp,vm,vb,vs,vx,run,receiver,numeric⟩ :=
    checked.numeric_run shape base world ready (ExternalFault := ExternalFault)
  exact run.not_diverges (by trivial)

end Aurora.SourceBinding
