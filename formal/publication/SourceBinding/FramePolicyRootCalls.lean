import SourceBinding.FramePolicyPacking
import SourceBinding.FramePolicyReject
import SourceBinding.FramePolicyCalls
namespace Aurora.SourceBinding.FramePolicyAttachment
open Aurora.Publication
variable {input : ByteArray} {files : List SourceFile} {root : Name}
variable {bound : RuntimeDAGBinding input files root frameModule framePath rootName}

theorem root_word (bounded : value < wordLimit) :
    RuntimeExpressionResult functions context state (.word value) (.scalar .word) (.value (.word value)) := by
  simpa only [readScalar,if_pos bounded] using
    (RuntimeExpressionResult.word (functions := functions) (context := context) (state := state) (value := value))

theorem root_constant (profile : ExactProfile bound) (role : Role)
    (valueEq : role.constantValue = some value) :
    RuntimeExpressionResult (bound.checked.shape.nodes.map (·.source)) context state
      (.call (.named [role.name]) []) (.scalar .word) (.value (.word value)) := by
  have facts : role.parameterKinds profile.operations.nominal profile.rejections.nominal = [] ∧
      role.resultKind = .scalar .word := by
    cases role <;> simp_all [Role.constantValue,Role.parameterKinds,Role.resultKind]
  have args : ArgumentsResult (bound.checked.shape.nodes.map (·.source)) context state []
      (role.parameterKinds profile.operations.nominal profile.rejections.nominal) [] := by
    rw [facts.1]; exact .nil
  have callResult := profile.call_result role args
    (fun node member named after outcome events evaluated => profile.constant_result node member named valueEq evaluated)
  simpa only [facts.2] using callResult

theorem root_pack (profile : ExactProfile bound)
    (stateExpr : RuntimeExpressionResult (bound.checked.shape.nodes.map (·.source)) context source rawState
      (.scalar .word) (.value (.word state)))
    (generationExpr : RuntimeExpressionResult (bound.checked.shape.nodes.map (·.source)) context source rawGeneration
      (.scalar .word) (.value (.word generation)))
    (wordExpr : RuntimeExpressionResult (bound.checked.shape.nodes.map (·.source)) context source rawWord
      (.scalar .word) (.value (.word word)))
    (hs : state < 16) (hg : generation ≤ FramePolicy.generationMax) (hw : word ≤ FramePolicy.wordMax) :
    RuntimeExpressionResult (bound.checked.shape.nodes.map (·.source)) context source
      (call "frame_record" [rawState,rawGeneration,rawWord]) (.scalar .word)
      (.value (.word (FramePolicy.pack state generation word))) :=
  profile.call_result .frameRecord (.cons stateExpr (.cons generationExpr (.cons wordExpr .nil)))
    (fun node member named after outcome events evaluated => profile.frame_record_bounded node member named hs hg hw evaluated)

theorem root_reject_value (profile : ExactProfile bound) (reason : FramePolicy.Rejection)
    (argument : RuntimeExpressionResult (bound.checked.shape.nodes.map (·.source)) context state raw
      (.nominal profile.rejections.nominal)
      (.value (.nominal profile.rejections.nominal.name reason.ordinal))) :
    RuntimeExpressionResult (bound.checked.shape.nodes.map (·.source)) context state
      (call "frame_reject" [raw]) (.scalar .word)
      (.value (.word (FramePolicy.encode (.reject reason)))) := by
  have small : reason.ordinal < 11 := by cases reason <;> decide
  have nonzero : reason.ordinal ≠ 0 := by cases reason <;> decide
  have result := profile.call_result .frameReject (.cons argument .nil)
    (fun node member named after outcome events evaluated => profile.frame_reject_result node member named small evaluated)
  simpa only [if_neg nonzero,FramePolicy.encode] using result

theorem root_reject (profile : ExactProfile bound)
    (valid : RuntimeContextValid context) (reason : FramePolicy.Rejection)
    (constant : RuntimeEnumValue context [rejectionName,rejectionSourceName reason]
      profile.rejections.nominal reason.ordinal) :
    RuntimeExpressionResult (bound.checked.shape.nodes.map (·.source)) context state
      (call "frame_reject" [.name [rejectionName,rejectionSourceName reason]]) (.scalar .word)
      (.value (.word (FramePolicy.encode (.reject reason)))) := by
  have closed := (profile.rejection_case reason).bounded
  have argument := RuntimeExpressionResult.enumValue (functions := bound.checked.shape.nodes.map (·.source))
    (state := state) valid constant
  rw [readRuntime_nominal _ _ closed] at argument
  exact root_reject_value profile reason argument

theorem root_compare
    (left : RuntimeExpressionResult functions context state lhs (.scalar .word) (.value (.word a)))
    (right : RuntimeExpressionResult functions context state rhs (.scalar .word) (.value (.word b)))
    (aBound : a < wordLimit) (bBound : b < wordLimit) :
    RuntimeExpressionResult functions context state (cmp comparison lhs rhs) (.scalar .boolean)
      (.value (.boolean (compareWords comparison a b))) := by
  have result := RuntimeExpressionResult.wordBinary (RuntimeWordOperator.compare (comparison := comparison)) left right
  simpa [Outcome.then,binaryValue,aBound,bBound] using result

end Aurora.SourceBinding.FramePolicyAttachment
