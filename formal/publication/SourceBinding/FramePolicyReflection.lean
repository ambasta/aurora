import SourceBinding.FramePolicyExecution
import SourceBinding.ForwardPolicy

namespace Aurora.SourceBinding.FramePolicyAttachment
open Aurora.Publication
variable {input : ByteArray} {files : List SourceFile} {root : Name}
variable {bound : RuntimeDAGBinding input files root frameModule framePath rootName}
variable {World ExternalFault : Type}

/-- Every canonical-machine run that reaches a boundary returns the same exact
policy result. The ambient external relation may be arbitrary: the constructed
complete local run has no external response and fixes the entire first exit. -/
theorem ExactProfile.terminal_correspondence (profile : ExactProfile bound)
    (bounded : FramePolicy.InputsBounded record owner generation link)
    (shared : CallShared World) (external : ExternalRelation World ExternalFault)
    (run : CallRuns (canonicalRuntimeCalls (tables bound.artifact.document.reversed.reverse)
        (bound.checked.shape.nodes.map (·.target))) external
      (.running (activeAt bound.checked.shape.rootNode.target.id [] shared.world
        ((freshCallFrame (arguments profile operation record owner generation link)).inject shared)))
      events final)
    (terminal : CallBoundary final) :
    ∃ active, final = .returned (.word (FramePolicy.encode
      (FramePolicy.transition operation record owner generation link))) active ∧
      active.shared = shared ∧ active.saved = [] := by
  obtain ⟨sourceFinal,se,me,evaluated,trace,runs⟩ := profile.executes
    (World := World) (ExternalFault := ExternalFault) (operation := operation) bounded
  obtain ⟨active,actual,locals,sharedEq,saved⟩ := runs shared (fun _ _ _ => False)
  obtain ⟨remaining,eventsEq,tail⟩ := actual.false_local.decompose run terminal
  obtain ⟨empty,finalEq⟩ := tail.from_returned
  exact ⟨active,finalEq,sharedEq,saved⟩

/-- The same complete local run excludes local infinite execution. This does
not assert anything about a native backend or persistent frame-bank storage. -/
theorem ExactProfile.not_locally_diverges (profile : ExactProfile bound)
    (bounded : FramePolicy.InputsBounded record owner generation link)
    (shared : CallShared World) :
    ¬ LocalCallDiverges (ExternalFault := ExternalFault)
      (canonicalRuntimeCalls (tables bound.artifact.document.reversed.reverse)
        (bound.checked.shape.nodes.map (·.target)))
      (.running (activeAt bound.checked.shape.rootNode.target.id [] shared.world
        ((freshCallFrame (arguments profile operation record owner generation link)).inject shared))) := by
  obtain ⟨sourceFinal,se,me,evaluated,trace,runs⟩ := profile.executes
    (World := World) (ExternalFault := ExternalFault) (operation := operation) bounded
  obtain ⟨active,actual,locals,sharedEq,saved⟩ := runs shared (fun _ _ _ => False)
  exact actual.false_local.not_diverges (by trivial)

end Aurora.SourceBinding.FramePolicyAttachment
