import SourceBinding.FramePolicyHelpers

namespace Aurora.SourceBinding.FramePolicyAttachment
open Aurora.Publication

variable {input : ByteArray} {files : List SourceFile} {root : Name}
variable {bound : RuntimeDAGBinding input files root frameModule framePath rootName}

/-- Actual checked packing remains partial for arbitrary typed words. Only
checked shifts overflow; overlapping, shift-safe fields still return their OR.
This theorem covers ANY source derivation, including faults, without assuming a
callee return or replacing the source body by a semantic summary. -/
theorem ExactProfile.frame_record_result (profile : ExactProfile bound)
    (node : RuntimeCallable (tables bound.artifact.document.reversed.reverse)
      files root frameModule framePath)
    (member : node ∈ bound.checked.shape.nodes) (named : node.name = Role.frameRecord.name)
    (hs : state < FramePolicy.u64Modulus) (hg : generation < FramePolicy.u64Modulus)
    (hw : word < FramePolicy.u64Modulus)
    (evaluated : FunctionEvaluation profile node [.word state,.word generation,.word word] after outcome events) :
    ∃ final, outcome =
      if generation * 16 < FramePolicy.u64Modulus then
        if word * FramePolicy.wordModulus < FramePolicy.u64Modulus then
          .returned (.word (state ||| (generation * 16) ||| (word * FramePolicy.wordModulus))) final
        else .trapped .overflow final
      else .trapped .overflow final := by
  have nodeEq := profile.node_eq_role node member named
  have formals : node.source.context.formals = [formal "state",formal "generation",formal "word"] := by
    rw [nodeEq]
    exact (profile.roles .frameRecord).formals
  have kinds := profile.node_parameters node member named
  let values : List Value := [.word state,.word generation,.word word]
  have stateExpression := profile.formal_word_result node member 0 "state"
    (by rw [formals]; rfl) (by rw [kinds]; rfl) (values := values) rfl hs
  have generationExpression := profile.formal_word_result node member 1 "generation"
    (by rw [formals]; rfl) (by rw [kinds]; rfl) (values := values) rfl hg
  have wordExpression := profile.formal_word_result node member 2 "word"
    (by rw [formals]; rfl) (by rw [kinds]; rfl) (values := values) rfl hw
  have generationShift := RuntimeExpressionResult.shiftLeft generationExpression SourceShiftCount.four
  have wordShift := RuntimeExpressionResult.shiftLeft wordExpression SourceShiftCount.thirtyTwo
  have hs' : state < 18446744073709551616 := hs
  have hg' : generation < 18446744073709551616 := hg
  have hw' : word < 18446744073709551616 := hw
  simp [Outcome.then,binaryValue,checkedShift,SignedLiteralCount.runtimeValue,
    SignedLiteralCount.value,signedLiteralCount,wordLimit,hg'] at generationShift
  simp [Outcome.then,binaryValue,checkedShift,SignedLiteralCount.runtimeValue,
    SignedLiteralCount.value,signedLiteralCount,wordLimit,hw'] at wordShift
  unfold FunctionEvaluation at evaluated
  rw [profile.node_body node member named,profile.node_result node member named] at evaluated
  by_cases gs : generation * 16 < 18446744073709551616
  · simp only [if_pos gs] at generationShift
    have inner := RuntimeExpressionResult.wordBinary RuntimeWordOperator.bitOr stateExpression generationShift
    simp [Outcome.then,binaryValue,wordLimit,hs',gs] at inner
    have innerBound : state ||| (generation * 16) < 18446744073709551616 :=
      Nat.or_lt_two_pow (n := 64) hs' gs
    by_cases ws : word * 4294967296 < 18446744073709551616
    · simp only [if_pos ws] at wordShift
      have outer := RuntimeExpressionResult.wordBinary RuntimeWordOperator.bitOr inner wordShift
      simp [Outcome.then,binaryValue,wordLimit,innerBound,ws] at outer
      have same := RuntimeExpressionResult.singleton outer evaluated
      refine ⟨formalSourceLocals node.source.parameters (fun index => values[index]?),?_⟩
      simpa only [FramePolicy.u64Modulus,FramePolicy.wordModulus,if_pos gs,if_pos ws] using same
    · simp only [if_neg ws] at wordShift
      have outer := RuntimeExpressionResult.wordBinary RuntimeWordOperator.bitOr inner wordShift
      simp only [Outcome.then] at outer
      have same := RuntimeExpressionResult.singleton outer evaluated
      refine ⟨formalSourceLocals node.source.parameters (fun index => values[index]?),?_⟩
      simpa only [FramePolicy.u64Modulus,FramePolicy.wordModulus,if_pos gs,if_neg ws] using same
  · simp only [if_neg gs] at generationShift
    have inner := RuntimeExpressionResult.wordBinary RuntimeWordOperator.bitOr stateExpression generationShift
    simp only [Outcome.then] at inner
    have outer := RuntimeExpressionResult.wordBinaryFault (rhs := bin .shift (v "word") (.signedCount 32))
      RuntimeWordOperator.bitOr inner
    have same := RuntimeExpressionResult.singleton outer evaluated
    refine ⟨formalSourceLocals node.source.parameters (fun index => values[index]?),?_⟩
    simpa only [FramePolicy.u64Modulus,if_neg gs] using same

/-- The root must derive these field bounds at each reached packing call.
This corollary does not make the general packing helper total. -/
theorem ExactProfile.frame_record_bounded (profile : ExactProfile bound)
    (node : RuntimeCallable (tables bound.artifact.document.reversed.reverse)
      files root frameModule framePath)
    (member : node ∈ bound.checked.shape.nodes) (named : node.name = Role.frameRecord.name)
    (hs : state < 16) (hg : generation ≤ FramePolicy.generationMax) (hw : word ≤ FramePolicy.wordMax)
    (evaluated : FunctionEvaluation profile node [.word state,.word generation,.word word] after outcome events) :
    ∃ final, outcome = .returned (.word (FramePolicy.pack state generation word)) final := by
  have shifts := FramePolicy.packing_shift_bounds hg hw
  have hs' : state < FramePolicy.u64Modulus := by simp only [FramePolicy.u64Modulus]; omega
  have hg' : generation < FramePolicy.u64Modulus := by
    simp only [FramePolicy.u64Modulus,FramePolicy.generationMax] at *; omega
  have hw' : word < FramePolicy.u64Modulus := by
    simp only [FramePolicy.u64Modulus,FramePolicy.wordMax] at *; omega
  obtain ⟨final,same⟩ := profile.frame_record_result node member named hs' hg' hw' evaluated
  rw [if_pos shifts.1,if_pos shifts.2,FramePolicy.packing_or hs hg] at same
  exact ⟨final,same⟩

end Aurora.SourceBinding.FramePolicyAttachment
