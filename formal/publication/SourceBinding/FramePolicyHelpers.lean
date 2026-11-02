import SourceBinding.FramePolicyProfile
import SourceBinding.FramePolicyDecoding
import SourceBinding.RuntimeEvaluationResults
import SourceBinding.FramePolicyState
import SourceBinding.RuntimeBodyContext

namespace Aurora.SourceBinding.FramePolicyAttachment
open Aurora.Publication

variable {input : ByteArray} {files : List SourceFile} {root : Name}
variable {bound : RuntimeDAGBinding input files root frameModule framePath rootName}

/-- The initial context follows from the actual whole checked source body. -/
theorem ExactProfile.initial_context (profile : ExactProfile bound)
    (node : RuntimeCallable (tables bound.artifact.document.reversed.reverse)
      files root frameModule framePath)
    (member : node ∈ bound.checked.shape.nodes) : RuntimeContextValid node.source.context := by
  obtain ⟨direct,_,_,code⟩ := (bound.checked.bodies node member).code
  exact code.initial_context (bound.checked.bodies node member).noFallthrough

private theorem word_literal (bounded : value < wordLimit) :
    RuntimeExpressionResult functions context state (.word value) (.scalar .word) (.value (.word value)) := by
  simpa [readScalar,bounded] using
    (RuntimeExpressionResult.word (functions := functions) (context := context) (state := state) (value := value))

/-- Every actual evaluation of each of the five constant helper bodies returns
its reviewed value. The complete source body and membership are derived from
the profile; no helper evaluation summary or no-fault premise is supplied. -/
theorem ExactProfile.constant_result (profile : ExactProfile bound) {role : Role}
    (node : RuntimeCallable (tables bound.artifact.document.reversed.reverse)
      files root frameModule framePath)
    (member : node ∈ bound.checked.shape.nodes) (named : node.name = role.name)
    (valueEq : role.constantValue = some value)
    (evaluated : FunctionEvaluation profile node [] after outcome events) :
    ∃ final, outcome = .returned (.word value) final := by
  have facts : role.shape.body = [.returnValue (.word value)] ∧
      role.resultKind = .scalar .word ∧ value < wordLimit := by
    cases role <;> simp_all [Role.constantValue,Role.shape,constant,ret,Role.resultKind,wordLimit] <;> omega
  unfold FunctionEvaluation at evaluated
  rw [profile.node_body node member named, facts.1,
    profile.node_result node member named, facts.2.1] at evaluated
  have same := RuntimeExpressionResult.singleton (word_literal facts.2.2) evaluated
  exact ⟨_,same⟩

/-- A bounded word formal is read from the actual source seed, with declaration
identity derived from the checked context and exact formal position. -/
theorem ExactProfile.formal_word_result (profile : ExactProfile bound) {values : List Value} {value : Nat}
    (node : RuntimeCallable (tables bound.artifact.document.reversed.reverse)
      files root frameModule framePath)
    (member : node ∈ bound.checked.shape.nodes) (index : Nat) (name : String)
    (formalAt : node.source.context.formals[index]? = some (formal name))
    (kindAt : node.source.parameters[index]? = some (.scalar .word))
    (valueAt : values[index]? = some (.word value)) (bounded : value < wordLimit) :
    RuntimeExpressionResult (bound.checked.shape.nodes.map (·.source)) node.source.context
      (formalSourceLocals node.source.parameters (fun index => values[index]?)) (v name)
      (.scalar .word) (.value (.word value)) := by
  have binding : RuntimeVariableBinding node.source.context (bytes name)
      ⟨bytes name,.scalar .word,false,0,runtimeParameterSlot index⟩ := by
    apply RuntimeVariableBinding.formal formalAt rfl RuntimeSourceType.word
    simp [RuntimeCallable.source,runtimeReturnContext]
  have expression := RuntimeExpressionResult.readVariable
    (functions := bound.checked.shape.nodes.map (·.source))
    (state := formalSourceLocals node.source.parameters (fun index => values[index]?))
    (profile.initial_context node member) binding
  have reading := formal_read (name := bytes name) (arguments := fun index => values[index]?) kindAt
  dsimp only at reading
  rw [valueAt] at reading
  simp only [readRuntime,readScalar,if_pos rfl,if_pos bounded] at reading
  rw [reading] at expression
  exact expression


theorem ExactProfile.kernel_owner_result (profile : ExactProfile bound)
    (node : RuntimeCallable (tables bound.artifact.document.reversed.reverse)
      files root frameModule framePath)
    (member : node ∈ bound.checked.shape.nodes) (named : node.name = Role.kernelOwner.name)
    (bounded : owner < FramePolicy.u64Modulus)
    (evaluated : FunctionEvaluation profile node [.word owner] after outcome events) :
    ∃ final, outcome = .returned (.boolean (decide (FramePolicy.KernelOwner owner))) final := by
  have nodeEq := profile.node_eq_role node member named
  have formals : node.source.context.formals = [formal "owner"] := by
    rw [nodeEq]
    exact (profile.roles .kernelOwner).formals
  have kinds := profile.node_parameters node member named
  have ownerExpression := profile.formal_word_result node member 0 "owner"
    (by rw [formals]; rfl) (by rw [kinds]; rfl) (values := [.word owner]) rfl bounded
  have lower := RuntimeExpressionResult.wordBinary
    (RuntimeWordOperator.compare (comparison := CompareOp.ge)) ownerExpression (word_literal (by decide : 1 < wordLimit))
  have upper := RuntimeExpressionResult.wordBinary
    (RuntimeWordOperator.compare (comparison := CompareOp.le)) ownerExpression (word_literal (by decide : 15 < wordLimit))
  have bounded' : owner < 18446744073709551616 := bounded
  simp [Outcome.then,binaryValue,compareWords,wordLimit,bounded'] at lower upper
  have both : RuntimeExpressionResult (bound.checked.shape.nodes.map (·.source)) node.source.context
      (formalSourceLocals node.source.parameters (fun index => ([.word owner] : List Value)[index]?))
      (bin .and (cmp .ge (v "owner") (.word 1)) (cmp .le (v "owner") (.word 15)))
      (.scalar .boolean) (.value (.boolean (decide (FramePolicy.KernelOwner owner)))) := by
    by_cases low : 1 ≤ owner
    · have lowerTrue := lower
      simp [low] at lowerTrue
      simpa [FramePolicy.KernelOwner,low] using RuntimeExpressionResult.and_true lowerTrue upper
    · have lowerFalse := lower
      simp [low] at lowerFalse
      simpa [FramePolicy.KernelOwner,low] using
        (RuntimeExpressionResult.and_false (rhs := cmp .le (v "owner") (.word 15)) lowerFalse)
  unfold FunctionEvaluation at evaluated
  rw [profile.node_body node member named,profile.node_result node member named] at evaluated
  have same := RuntimeExpressionResult.singleton both evaluated
  exact ⟨_,same⟩

end Aurora.SourceBinding.FramePolicyAttachment
