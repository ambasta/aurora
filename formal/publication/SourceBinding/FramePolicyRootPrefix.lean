import SourceBinding.FramePolicyInitialize
import SourceBinding.FramePolicyValid
import SourceBinding.LocalCursorFacts

namespace Aurora.SourceBinding.FramePolicyAttachment
open Aurora.Publication
variable {input : ByteArray} {files : List SourceFile} {root : Name}
variable {bound : RuntimeDAGBinding input files root frameModule framePath rootName}
variable {profile : ExactProfile bound}

/-- Internal proof composition over the actual remaining source statements.
The final root theorem must construct this continuation, not assume it. -/
def PrefixContinuation (profile : ExactProfile bound)
    (operation : FramePolicy.Operation) (record owner generation link : Nat) : Prop :=
  ∀ (before : LocalContext) (state : RuntimeLocals) (after : LocalContext)
    (outcome : RuntimeBodyOutcome) (events : List RuntimeSourceEvent),
    before.visible = [] → 5 ≤ before.nextSlot →
    RootInputState profile operation record owner generation link state →
    (operation = .allocate ∨ operation = .release) →
    FramePolicy.RecordValid record → FramePolicy.UserOwner owner →
    InitializationEvaluation profile before state (transitionShape.body.drop 4) after outcome events →
    ∃ final, outcome = .returned
      (.word (FramePolicy.encode (FramePolicy.transition operation record owner generation link))) final

private theorem prefix_operation_test
    (facts : RootInputState profile operation record owner generation link state)
    (other : FramePolicy.Operation) (equal : Bool) :
    RuntimeExpressionResult (bound.checked.shape.nodes.map (·.source)) (rootInputContext profile) state
      (cmp (if equal then .eq else .ne) (v "operation") (.name [operationName,operationSourceName other]))
      (.scalar .boolean) (.value (.boolean (if equal then decide (operation = other) else decide (operation ≠ other)))) := by
  have expression := RuntimeExpressionResult.enumCompare (equal := equal)
    facts.operation_result (profile.operation_constant_result other)
  cases equal <;> cases operation <;> cases other <;>
    simpa only [Outcome.then,compareNominal,operationValue,readRuntime,
      profile.operation_cardinality,FramePolicy.Operation.ordinal,
      Nat.reduceLT,eq_self,true_and,if_true,if_false,Bool.true_eq,
      Nat.reduceBEq,reduceCtorEq,decide_true,decide_false,ne_eq,
      not_true_eq_false,not_false_eq_true,bne,Bool.not_true,Bool.not_false] using expression

private theorem prefix_or
    (left : RuntimeExpressionResult functions context state lhs (.scalar .boolean) (.value (.boolean a)))
    (right : RuntimeExpressionResult functions context state rhs (.scalar .boolean) (.value (.boolean b))) :
    RuntimeExpressionResult functions context state (bin .or lhs rhs) (.scalar .boolean)
      (.value (.boolean (a || b))) := by
  cases a
  · exact RuntimeExpressionResult.or_false left right
  · exact RuntimeExpressionResult.or_true left

private theorem prefix_and
    (left : RuntimeExpressionResult functions context state lhs (.scalar .boolean) (.value (.boolean a)))
    (right : RuntimeExpressionResult functions context state rhs (.scalar .boolean) (.value (.boolean b))) :
    RuntimeExpressionResult functions context state (bin .and lhs rhs) (.scalar .boolean)
      (.value (.boolean (a && b))) := by
  cases a
  · exact RuntimeExpressionResult.and_false left
  · exact RuntimeExpressionResult.and_true left right

private theorem prefix_reject (reason : FramePolicy.Rejection)
    (empty : before.visible = [])
    (evaluated : InitializationEvaluation profile before state [reject (match reason with
      | .operation => "operation" | .record => "record" | .owner => "owner"
      | .link => "link" | .notFree => "not_free" | .notAllocated => "not_allocated"
      | .kernel => "kernel" | .retired => "retired" | .wrongOwner => "wrong_owner" | .stale => "stale")]
      after outcome events) :
    outcome = .returned (.word (FramePolicy.encode (.reject reason))) state := by
  have expression := root_reject_value profile reason (profile.rejection_constant_result (state := state) reason)
  rw [← profile.root_input_cursor before empty] at expression
  cases reason <;> exact RuntimeExpressionResult.singleton (before := before) expression evaluated

private theorem prefix_owner_tail (profile : ExactProfile bound)
    (bounded : FramePolicy.InputsBounded record owner generation link)
    (facts : RootInputState profile operation record owner generation link state)
    (allowed : operation = .allocate ∨ operation = .release)
    (validRecord : FramePolicy.RecordValid record)
    (empty : before.visible = []) (lower : 5 ≤ before.nextSlot)
    (continuation : PrefixContinuation profile operation record owner generation link)
    (evaluated : InitializationEvaluation profile before state (transitionShape.body.drop 3) after outcome events) :
    ∃ final, outcome = .returned
      (.word (FramePolicy.encode (FramePolicy.transition operation record owner generation link))) final := by
  have zeroTest := root_compare (comparison := CompareOp.eq) facts.owner_result
    (root_word (value := 0) (by decide)) bounded.2.1 (by decide)
  have largeTest := root_compare (comparison := CompareOp.gt) facts.owner_result
    (root_word (value := 4294967295) (by decide)) bounded.2.1 (by decide)
  have kernelTest := profile.call_result .kernelOwner (.cons facts.owner_result .nil)
    (fun node member named after outcome events evaluated =>
      profile.kernel_owner_result node member named bounded.2.1 evaluated)
  have test := prefix_or (prefix_or zeroTest largeTest) kernelTest
  simp only [compareWords,Bool.beq_eq_decide_eq,← Bool.decide_or,or_assoc,← FramePolicy.user_owner_guard] at test
  rw [← profile.root_input_cursor before empty] at test
  by_cases validOwner : FramePolicy.UserOwner owner
  · have falseTest := test
    simp only [decide_eq_false (not_not_intro validOwner)] at falseTest
    obtain ⟨child,items,next,se,scopeProof,reserve,tail⟩ := false_branch_tail falseTest evaluated
    exact continuation (leaveLocalScope before child) _ _ _ _ empty (Nat.le_trans lower scopeProof.cursors.2)
      (facts.reserved reserve) allowed validRecord validOwner tail
  · have trueTest := test
    simp only [decide_eq_true validOwner] at trueTest
    obtain ⟨child,entered,se,enter,body⟩ := true_branch_body trueTest .returned evaluated
    have same := prefix_reject (before := enterLocalScope before) (profile := profile) .owner empty body
    refine ⟨entered,?_⟩
    rcases allowed with allocated | released <;> subst operation <;>
      simpa only [FramePolicy.transition,if_neg (not_not_intro validRecord),if_pos validOwner] using same

private theorem prefix_valid_tail (profile : ExactProfile bound)
    (bounded : FramePolicy.InputsBounded record owner generation link)
    (facts : RootInputState profile operation record owner generation link state)
    (allowed : operation = .allocate ∨ operation = .release)
    (empty : before.visible = []) (lower : 5 ≤ before.nextSlot)
    (continuation : PrefixContinuation profile operation record owner generation link)
    (evaluated : InitializationEvaluation profile before state (transitionShape.body.drop 2) after outcome events) :
    ∃ final, outcome = .returned
      (.word (FramePolicy.encode (FramePolicy.transition operation record owner generation link))) final := by
  have validCall := profile.call_result .recordValid (.cons facts.record_result .nil)
    (fun node member named after outcome events evaluated =>
      profile.record_valid_result node member named bounded.1 evaluated)
  have test := RuntimeExpressionResult.not validCall
  simp only [Outcome.then,notValue] at test
  rw [← profile.root_input_cursor before empty] at test
  by_cases validRecord : FramePolicy.RecordValid record
  · have falseTest := test
    simp only [decide_eq_true validRecord,Bool.not_true] at falseTest
    obtain ⟨child,items,next,se,scopeProof,reserve,tail⟩ := false_branch_tail falseTest evaluated
    exact prefix_owner_tail (before := leaveLocalScope before child) profile bounded (facts.reserved reserve) allowed validRecord empty
      (Nat.le_trans lower scopeProof.cursors.2) continuation tail
  · have trueTest := test
    simp only [decide_eq_false validRecord,Bool.not_false] at trueTest
    obtain ⟨child,entered,se,enter,body⟩ := true_branch_body trueTest .returned evaluated
    have same := prefix_reject (before := enterLocalScope before) (profile := profile) .record empty body
    refine ⟨entered,?_⟩
    rcases allowed with allocated | released <;> subst operation <;>
      simpa only [FramePolicy.transition,if_pos validRecord] using same

private theorem prefix_operation_tail (profile : ExactProfile bound)
    (bounded : FramePolicy.InputsBounded record owner generation link)
    (facts : RootInputState profile operation record owner generation link state)
    (notInit : ¬ (operation = .initializeFree ∨ operation = .initializeKernel))
    (empty : before.visible = []) (lower : 5 ≤ before.nextSlot)
    (continuation : PrefixContinuation profile operation record owner generation link)
    (evaluated : InitializationEvaluation profile before state (transitionShape.body.drop 1) after outcome events) :
    ∃ final, outcome = .returned
      (.word (FramePolicy.encode (FramePolicy.transition operation record owner generation link))) final := by
  have test := prefix_and (prefix_operation_test facts .allocate false)
    (prefix_operation_test facts .release false)
  rw [← profile.root_input_cursor before empty] at test
  by_cases allowed : operation = .allocate ∨ operation = .release
  · have falseTest := test
    have falseEq : (decide (operation ≠ .allocate) && decide (operation ≠ .release)) = false := by
      rcases allowed with h | h <;> subst operation <;> decide
    simp only [Bool.false_eq_true,if_false,falseEq] at falseTest
    obtain ⟨child,items,next,se,scopeProof,reserve,tail⟩ := false_branch_tail falseTest evaluated
    exact prefix_valid_tail (before := leaveLocalScope before child) profile bounded (facts.reserved reserve) allowed empty
      (Nat.le_trans lower scopeProof.cursors.2) continuation tail
  · have none : operation = .none := by
      cases operation <;> simp_all only [reduceCtorEq,true_or,or_true,not_true_eq_false,false_or]
    subst operation
    simp only [Bool.false_eq_true,if_false,reduceCtorEq,ne_eq,not_false_eq_true,decide_true,Bool.and_self] at test
    obtain ⟨child,entered,se,enter,body⟩ := true_branch_body test .returned evaluated
    exact ⟨entered,prefix_reject (before := enterLocalScope before) (profile := profile) .operation empty body⟩

/-- Internal modular root prefix: the source-result theorem discharges its
continuation with the actual local declarations and remaining source proof. -/
theorem ExactProfile.root_prefix_result (profile : ExactProfile bound)
    (bounded : FramePolicy.InputsBounded record owner generation link)
    (continuation : PrefixContinuation profile operation record owner generation link)
    (evaluated : FunctionEvaluation profile bound.checked.shape.rootNode
      (arguments profile operation record owner generation link) after outcome events) :
    ∃ final, outcome = .returned
      (.word (FramePolicy.encode (FramePolicy.transition operation record owner generation link))) final := by
  have bodyEq := profile.node_body (role := .transition) _ bound.checked.shape.rootMember bound.checked.shape.rootNameEq
  have facts := RootInputState.initial profile operation bounded
  unfold FunctionEvaluation at evaluated
  rw [profile.rootResult] at evaluated
  change InitializationEvaluation profile
    ⟨[],0,1,bound.checked.shape.rootNode.source.context.formals.length⟩ _
    bound.checked.shape.rootNode.source.parsed.statements after outcome events at evaluated
  rw [bodyEq] at evaluated
  have test := prefix_or (prefix_operation_test facts .initializeFree true)
    (prefix_operation_test facts .initializeKernel true)
  simp only [Bool.true_eq,if_true,← Bool.decide_or] at test
  rw [← profile.root_input_cursor ⟨[],0,1,bound.checked.shape.rootNode.source.context.formals.length⟩ rfl] at test
  by_cases initializing : operation = .initializeFree ∨ operation = .initializeKernel
  · have trueTest := test
    simp only [decide_eq_true initializing] at trueTest
    obtain ⟨child,entered,se,enter,body⟩ := true_branch_body trueTest (.later (.later (.later .returned))) evaluated
    exact profile.initialization_result bounded (facts.entered enter) initializing rfl body
  · have falseTest := test
    simp only [decide_eq_false initializing] at falseTest
    obtain ⟨child,items,next,se,scopeProof,reserve,tail⟩ := false_branch_tail falseTest evaluated
    have lower : 5 ≤ child.nextSlot := by
      have monotone := scopeProof.cursors.2
      have formals := profile.root_input_formals
      change bound.checked.shape.rootNode.source.context.formals = _ at formals
      simpa only [enterLocalScope,formals,transitionShape,List.length_cons,List.length_nil] using monotone
    exact prefix_operation_tail (before := leaveLocalScope
      ⟨[],0,1,bound.checked.shape.rootNode.source.context.formals.length⟩ child) profile bounded (facts.reserved reserve) initializing rfl lower continuation tail

end Aurora.SourceBinding.FramePolicyAttachment
