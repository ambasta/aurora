import SourceBinding.FramePolicyRootInputs
import SourceBinding.FramePolicyRootCalls
import SourceBinding.FramePolicyFlow

namespace Aurora.SourceBinding.FramePolicyAttachment
open Aurora.Publication

variable {input : ByteArray} {files : List SourceFile} {root : Name}
variable {bound : RuntimeDAGBinding input files root frameModule framePath rootName}

/-- Extract the complete first branch from the reviewed whole root AST. This is
syntax projection, not an alternative evaluator or a new policy definition. -/
def initializationBody : List SourceStatement :=
  match transitionShape.body with
  | .ifThen _ body :: _ => body
  | _ => []

abbrev InitializationEvaluation (profile : ExactProfile bound) (before : LocalContext) (state : RuntimeLocals)
    (body : List SourceStatement) (after : LocalContext) (outcome : RuntimeBodyOutcome)
    (events : List RuntimeSourceEvent) : Prop :=
  RuntimeStatementsEvaluation (bound.checked.shape.nodes.map (·.source))
    bound.checked.shape.rootNode.source.context.members frameModule framePath
    bound.checked.shape.rootNode.source.context.formals (.scalar .word)
    before state body after outcome events

private theorem initialization_operation_test {profile : ExactProfile bound}
    (facts : RootInputState profile operation record owner generation link state) (other : FramePolicy.Operation) :
    RuntimeExpressionResult (bound.checked.shape.nodes.map (·.source)) (rootInputContext profile) state
      (cmp .eq (v "operation") (.name [operationName,operationSourceName other])) (.scalar .boolean)
      (.value (.boolean (decide (operation = other)))) := by
  have expression := RuntimeExpressionResult.enumCompare (equal := true)
    facts.operation_result (profile.operation_constant_result other)
  cases operation <;> cases other <;>
    simpa only [Outcome.then,compareNominal,operationValue,readRuntime,
      profile.operation_cardinality,FramePolicy.Operation.ordinal,
      Nat.reduceLT,eq_self,true_and,if_true,Bool.true_eq,
      Nat.reduceBEq,reduceCtorEq,decide_true,decide_false] using expression

private theorem initialization_reject (profile : ExactProfile bound) (reason : FramePolicy.Rejection) :
    RuntimeExpressionResult (bound.checked.shape.nodes.map (·.source)) (rootInputContext profile) state
      (call "frame_reject" [.name [rejectionName,rejectionSourceName reason]]) (.scalar .word)
      (.value (.word (FramePolicy.encode (.reject reason)))) := by
  exact root_reject_value profile reason (profile.rejection_constant_result reason)

private theorem initialization_free_tail (profile : ExactProfile bound)
    (bounded : FramePolicy.InputsBounded record owner generation link)
    (facts : RootInputState profile .initializeFree record owner generation link state)
    (empty : before.visible = [])
    (evaluated : InitializationEvaluation profile before state (initializationBody.drop 2) after outcome events) :
    ∃ final, outcome = .returned
      (.word (FramePolicy.encode (FramePolicy.transition .initializeFree 0 owner generation link))) final := by
  have test := root_compare (comparison := CompareOp.gt) facts.link_result
    (root_word (value := 4294967295) (by decide)) bounded.2.2.2 (by decide)
  have cursor := profile.root_input_cursor before empty
  rw [← cursor] at test
  by_cases badLink : link > FramePolicy.wordMax
  · have trueTest := test
    simp only [compareWords,decide_eq_true badLink] at trueTest
    obtain ⟨child,entered,se,enter,body⟩ := true_branch_body trueTest .returned evaluated
    have expression := initialization_reject (state := entered) profile .link
    rw [← profile.root_input_cursor (enterLocalScope before) empty] at expression
    have same := RuntimeExpressionResult.singleton (before := enterLocalScope before) expression body
    refine ⟨entered,?_⟩
    simpa [FramePolicy.transition,badLink,FramePolicy.encode] using same
  · have falseTest := test
    simp only [compareWords,decide_eq_false badLink] at falseTest
    obtain ⟨child,items,next,se,scopeProof,reserve,tail⟩ := false_branch_tail falseTest evaluated
    have nextFacts := facts.reserved reserve
    have linkBound : link ≤ FramePolicy.wordMax := by omega
    have expression := root_pack profile (root_constant profile .free rfl)
      (root_word (value := 0) (by decide)) nextFacts.link_result (by decide) (by decide) linkBound
    rw [← profile.root_input_cursor (leaveLocalScope before child) empty] at expression
    have same := RuntimeExpressionResult.singleton (before := leaveLocalScope before child) expression tail
    refine ⟨next,?_⟩
    simpa [FramePolicy.transition,badLink,FramePolicy.encode] using same

private theorem initialization_kernel_tail (profile : ExactProfile bound)
    (bounded : FramePolicy.InputsBounded record owner generation link)
    (facts : RootInputState profile .initializeKernel record owner generation link state)
    (empty : before.visible = [])
    (evaluated : InitializationEvaluation profile before state
      [branch (.not (call "kernel_owner" [v "owner"])) [reject "owner"],
       packed "frame_kernel" (.word 0) (v "owner")] after outcome events) :
    ∃ final, outcome = .returned
      (.word (FramePolicy.encode (FramePolicy.transition .initializeKernel 0 owner generation link))) final := by
  have ownerCall := profile.call_result .kernelOwner (.cons facts.owner_result .nil)
    (fun node member named after outcome events evaluated =>
      profile.kernel_owner_result node member named bounded.2.1 evaluated)
  have test := RuntimeExpressionResult.not ownerCall
  simp only [Outcome.then,notValue] at test
  have cursor := profile.root_input_cursor before empty
  rw [← cursor] at test
  by_cases kernelOwner : FramePolicy.KernelOwner owner
  · have falseTest := test
    simp only [decide_eq_true kernelOwner,Bool.not_true] at falseTest
    obtain ⟨child,items,next,se,scopeProof,reserve,tail⟩ := false_branch_tail falseTest evaluated
    have nextFacts := facts.reserved reserve
    have ownerBound : owner ≤ FramePolicy.wordMax := by
      simp only [FramePolicy.KernelOwner,FramePolicy.wordMax] at *
      omega
    have expression := root_pack profile (root_constant profile .kernel rfl)
      (root_word (value := 0) (by decide)) nextFacts.owner_result (by decide) (by decide) ownerBound
    rw [← profile.root_input_cursor (leaveLocalScope before child) empty] at expression
    have same := RuntimeExpressionResult.singleton (before := leaveLocalScope before child) expression tail
    refine ⟨next,?_⟩
    simpa only [FramePolicy.transition,ne_eq,not_true_eq_false,if_false,
      if_neg (not_not_intro kernelOwner),FramePolicy.encode] using same
  · have trueTest := test
    simp only [decide_eq_false kernelOwner,Bool.not_false] at trueTest
    obtain ⟨child,entered,se,enter,body⟩ := true_branch_body trueTest .returned evaluated
    have expression := initialization_reject (state := entered) profile .owner
    rw [← profile.root_input_cursor (enterLocalScope before) empty] at expression
    have same := RuntimeExpressionResult.singleton (before := enterLocalScope before) expression body
    refine ⟨entered,?_⟩
    simpa only [FramePolicy.transition,ne_eq,not_true_eq_false,if_false,
      if_pos kernelOwner,FramePolicy.encode] using same

/-- Internal root-branch lemma, universally quantified over actual source
execution. The enclosing root theorem derives the five read facts from its
actual formal seed and entered scope; no callee summary or no-fault premise is
accepted. Every reached packing bound is derived from the preceding guards. -/
theorem ExactProfile.initialization_result (profile : ExactProfile bound)
    (bounded : FramePolicy.InputsBounded record owner generation link)
    (facts : RootInputState profile operation record owner generation link state)
    (initializing : operation = .initializeFree ∨ operation = .initializeKernel)
    (empty : before.visible = [])
    (evaluated : InitializationEvaluation profile before state initializationBody after outcome events) :
    ∃ final, outcome = .returned
      (.word (FramePolicy.encode (FramePolicy.transition operation record owner generation link))) final := by
  have test := root_compare (comparison := CompareOp.ne) facts.record_result
    (root_word (value := 0) (by decide)) bounded.1 (by decide)
  have cursor := profile.root_input_cursor before empty
  rw [← cursor] at test
  by_cases clear : record = 0
  · have falseTest := test
    simp only [compareWords,clear,bne_self_eq_false] at falseTest
    obtain ⟨child,items,next,se,scopeProof,reserve,tail⟩ := false_branch_tail falseTest evaluated
    have nextFacts := facts.reserved reserve
    rcases initializing with free | kernel
    · subst operation
      have operationTest := initialization_operation_test nextFacts .initializeKernel
      simp only [reduceCtorEq,decide_false] at operationTest
      rw [← profile.root_input_cursor (leaveLocalScope before child) empty] at operationTest
      obtain ⟨child2,items2,next2,se2,scope2,reserve2,tail2⟩ := false_branch_tail operationTest tail
      obtain ⟨final,result⟩ := initialization_free_tail
        (before := leaveLocalScope (leaveLocalScope before child) child2)
        profile bounded (nextFacts.reserved reserve2) empty tail2
      exact ⟨final,by simpa only [clear] using result⟩
    · subst operation
      have operationTest := initialization_operation_test nextFacts .initializeKernel
      simp only [decide_true] at operationTest
      rw [← profile.root_input_cursor (leaveLocalScope before child) empty] at operationTest
      obtain ⟨child2,entered,se2,enter2,body2⟩ := true_branch_body operationTest (.later .returned) tail
      obtain ⟨final,result⟩ := initialization_kernel_tail
        (before := enterLocalScope (leaveLocalScope before child))
        profile bounded (nextFacts.entered enter2) empty body2
      exact ⟨final,by simpa only [clear] using result⟩
  · have trueTest := test
    simp only [compareWords,bne,beq_eq_false_iff_ne.mpr clear,Bool.not_false] at trueTest
    obtain ⟨child,entered,se,enter,body⟩ := true_branch_body trueTest .returned evaluated
    have expression := initialization_reject (state := entered) profile .record
    rw [← profile.root_input_cursor (enterLocalScope before) empty] at expression
    have same := RuntimeExpressionResult.singleton (before := enterLocalScope before) expression body
    refine ⟨entered,?_⟩
    rcases initializing with free | kernel <;> subst operation <;>
      simpa [FramePolicy.transition,clear,FramePolicy.encode] using same

end Aurora.SourceBinding.FramePolicyAttachment
