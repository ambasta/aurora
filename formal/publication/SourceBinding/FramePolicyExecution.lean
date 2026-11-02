import SourceBinding.FramePolicyRoot
import SourceBinding.RuntimeDAGPublic

namespace Aurora.SourceBinding.FramePolicyAttachment
open Aurora.Publication
variable {input : ByteArray} {files : List SourceFile} {root : Name}
variable {bound : RuntimeDAGBinding input files root frameModule framePath rootName}
variable {World ExternalFault : Type}

/-- A proof-only package of existing source and IR execution judgments.
The actual source/IR traces are chosen before arbitrary shared contexts. This
is not another evaluator, nor a statement about native execution or storage. -/
def PolicyExecution (profile : ExactProfile bound) (World ExternalFault : Type)
    (operation : FramePolicy.Operation) (record owner generation link result : Nat) : Prop :=
  ∃ sourceFinal sourceEvents machineEvents,
    FunctionEvaluation profile bound.checked.shape.rootNode
      (arguments profile operation record owner generation link)
      bound.checked.shape.rootNode.identified.details.lexical.lexical.after
      (.returned (.word result) sourceFinal) sourceEvents ∧
    RuntimeCallTraceRelated bound.checked.shape.nodes sourceEvents machineEvents ∧
    ∀ (shared : CallShared World) (external : ExternalRelation World ExternalFault),
      ∃ active, CallRuns (canonicalRuntimeCalls (tables bound.artifact.document.reversed.reverse)
          (bound.checked.shape.nodes.map (·.target))) external
        (.running (activeAt bound.checked.shape.rootNode.target.id [] shared.world
          ((freshCallFrame (arguments profile operation record owner generation link)).inject shared)))
        machineEvents (.returned (.word result) active) ∧
        active.frame.locals = sourceFinal.values ∧ active.shared = shared ∧ active.saved = []

/-- Total execution of the exact checked ten-helper policy closure. Bounded
inputs and the exact profile are the only premises: source/IR outcomes and
traces are obtained from the DAG theorem, and the actual root proof excludes
faults and identifies the prioritized numerical result. -/
theorem ExactProfile.executes (profile : ExactProfile bound)
    (bounded : FramePolicy.InputsBounded record owner generation link) :
    PolicyExecution profile World ExternalFault operation record owner generation link
      (FramePolicy.encode (FramePolicy.transition operation record owner generation link)) := by
  obtain ⟨outcome,se,me,evaluated,trace,run⟩ := bound.checked.executes
    (World := World) (ExternalFault := ExternalFault)
    (arguments profile operation record owner generation link) (profile.arguments_ready bounded)
  obtain ⟨sourceFinal,result⟩ := profile.source_result bounded evaluated
  rw [result] at evaluated run
  refine ⟨sourceFinal,se,me,evaluated,trace,?_⟩
  intro shared external
  obtain ⟨final,actual,terminal⟩ := run shared external
  cases final with
  | running active => cases terminal
  | waiting pending => cases terminal
  | trapped fault active => cases terminal
  | returned value active =>
    obtain ⟨same,locals,sharedEq,saved⟩ := terminal
    subst value
    exact ⟨active,actual,locals,sharedEq,saved⟩

/-- The main execution result satisfies the independent exact ResultSpec and
its u64 bound, without assuming a source return or a desired result. -/
theorem ExactProfile.executes_spec (profile : ExactProfile bound)
    (bounded : FramePolicy.InputsBounded record owner generation link) :
    ∃ result, FramePolicy.ResultSpec operation record owner generation link result ∧
      result < FramePolicy.u64Modulus ∧
      PolicyExecution profile World ExternalFault operation record owner generation link result := by
  refine ⟨_,rfl,FramePolicy.result_bounded rfl,profile.executes bounded⟩

/-- Allocation on a valid free copied record preserves its decoded generation.
No statement here says a ledger stores the returned record. -/
theorem ExactProfile.allocate_preserves_generation (profile : ExactProfile bound)
    (bounded : FramePolicy.InputsBounded record owner generation link)
    (free : FramePolicy.stateOf record = 1) (user : FramePolicy.UserOwner owner) :
    PolicyExecution profile World ExternalFault .allocate record owner generation link
      (FramePolicy.pack 2 (FramePolicy.generationOf record) owner) ∧
    FramePolicy.generationOf (FramePolicy.pack 2 (FramePolicy.generationOf record) owner) =
      FramePolicy.generationOf record := by
  have valid : FramePolicy.RecordValid record := Or.inl free
  have run := profile.executes (World := World) (ExternalFault := ExternalFault)
    (operation := FramePolicy.Operation.allocate) bounded
  constructor
  · simpa only [FramePolicy.transition,if_neg (not_not_intro valid),if_neg (not_not_intro user),
      free,Nat.reduceEqDiff,if_false,if_true,ne_eq,not_true_eq_false,FramePolicy.encode] using run
  · exact (FramePolicy.pack_fields 2 _ owner (by decide) (FramePolicy.generation_bound record)).2.1

/-- Matching release increments below the generation maximum. Link admission
is an explicit reached-path condition, including at exhaustion. -/
theorem ExactProfile.release_increments (profile : ExactProfile bound)
    (bounded : FramePolicy.InputsBounded record owner generation link)
    (allocated : FramePolicy.stateOf record = 2) (owned : FramePolicy.wordOf record = owner)
    (user : FramePolicy.UserOwner owner) (matching : generation = FramePolicy.generationOf record)
    (linkBound : link ≤ FramePolicy.wordMax) (room : FramePolicy.generationOf record < FramePolicy.generationMax) :
    PolicyExecution profile World ExternalFault .release record owner generation link
      (FramePolicy.pack 1 (FramePolicy.generationOf record + 1) link) := by
  have run := profile.executes (World := World) (ExternalFault := ExternalFault)
    (operation := FramePolicy.Operation.release) bounded
  rw [FramePolicy.matching_release_increments allocated owned user matching linkBound room] at run
  exact run

/-- Matching maximum-generation release returns the canonical retired record.
This is an actual invocation result, not persistent retirement or ABA safety. -/
theorem ExactProfile.release_retires (profile : ExactProfile bound)
    (bounded : FramePolicy.InputsBounded record owner generation link)
    (allocated : FramePolicy.stateOf record = 2) (owned : FramePolicy.wordOf record = owner)
    (user : FramePolicy.UserOwner owner) (matching : generation = FramePolicy.generationOf record)
    (linkBound : link ≤ FramePolicy.wordMax) (full : FramePolicy.generationOf record = FramePolicy.generationMax) :
    PolicyExecution profile World ExternalFault .release record owner generation link FramePolicy.retiredRecord := by
  have run := profile.executes (World := World) (ExternalFault := ExternalFault)
    (operation := FramePolicy.Operation.release) bounded
  have result : FramePolicy.retiredRecord = FramePolicy.encode
      (FramePolicy.transition .release record owner generation link) :=
    FramePolicy.matching_release_retires allocated owned user matching linkBound full
  rw [← result] at run
  exact run

/-- Every later policy invocation on the canonical retired copied record
returns a rejection, including initialization. Earlier guards determine the
reason: it is deliberately not asserted to be always `retired`. -/
theorem ExactProfile.retired_refuses (profile : ExactProfile bound)
    (operation : FramePolicy.Operation)
    (ownerBound : owner < FramePolicy.u64Modulus)
    (generationBound : generation < FramePolicy.u64Modulus)
    (linkBound : link < FramePolicy.u64Modulus) :
    PolicyExecution profile World ExternalFault operation FramePolicy.retiredRecord owner generation link
      (FramePolicy.encode (.reject (match operation with
       | .none => .operation
       | .initializeFree | .initializeKernel => .record
       | .allocate | .release => if FramePolicy.UserOwner owner then .retired else .owner))) := by
  have bounded : FramePolicy.InputsBounded FramePolicy.retiredRecord owner generation link :=
    ⟨by decide,ownerBound,generationBound,linkBound⟩
  have run := profile.executes (World := World) (ExternalFault := ExternalFault)
    (operation := operation) bounded
  rw [FramePolicy.retired_priority] at run
  exact run

/-- Any bounded input whose state nibble is retired refuses every operation,
including malformed retired records. Validity and owner guards still precede
the retired-state guard, so the rejection reason is not fixed. -/
theorem ExactProfile.retired_input_refuses (profile : ExactProfile bound)
    (operation : FramePolicy.Operation)
    (bounded : FramePolicy.InputsBounded record owner generation link)
    (retired : FramePolicy.stateOf record = 4) :
    ∃ reason, PolicyExecution profile World ExternalFault operation record owner generation link
      (FramePolicy.encode (.reject reason)) := by
  have nonzero : record ≠ 0 := by
    intro zero
    subst record
    cases retired
  have rejects : ∃ reason, FramePolicy.transition operation record owner generation link = .reject reason := by
    cases operation with
    | none => exact ⟨.operation,rfl⟩
    | initializeFree | initializeKernel =>
      exact ⟨.record,by simp only [FramePolicy.transition,if_pos nonzero]⟩
    | allocate | release =>
      by_cases valid : FramePolicy.RecordValid record
      · by_cases user : FramePolicy.UserOwner owner
        · exact ⟨.retired,by simp only [FramePolicy.transition,if_neg (not_not_intro valid),
            if_neg (not_not_intro user),retired,Nat.reduceEqDiff,if_false,if_true]⟩
        · exact ⟨.owner,by simp only [FramePolicy.transition,if_neg (not_not_intro valid),if_pos user]⟩
      · exact ⟨.record,by simp only [FramePolicy.transition,if_pos valid]⟩
  obtain ⟨reason,result⟩ := rejects
  have run := profile.executes (World := World) (ExternalFault := ExternalFault)
    (operation := operation) bounded
  rw [result] at run
  exact ⟨reason,run⟩

end Aurora.SourceBinding.FramePolicyAttachment
