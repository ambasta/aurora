import SourceBinding.FramePolicyHelpers
import SourceBinding.FramePolicyCalls
import SourceBinding.FramePolicyStateUpdates
import SourceBinding.FramePolicyFlow

namespace Aurora.SourceBinding.FramePolicyAttachment
open Aurora.Publication

variable {input : ByteArray} {files : List SourceFile} {root : Name}
variable {bound : RuntimeDAGBinding input files root frameModule framePath rootName}

private theorem read_active {state : RuntimeLocals} {binding : SourceLocal}
    (read : state.readBound binding = .value value) : binding.scope ∈ state.scopes := by
  unfold RuntimeLocals.readBound at read
  split at read
  next declared =>
    simp only [RuntimeLocals.read,declared,SourceLocal.runtimeDeclaration] at read
    split at read
    next active => exact active
    next absent => cases read
  next absent => cases read

private theorem entered_read {state next : RuntimeLocals} {binding : SourceLocal}
    (read : state.readBound binding = .value value) (entered : state.enterAt scope = some next) :
    next.readBound binding = .value value := (enter_read (read_active read) entered).trans read

private theorem constant_call (profile : ExactProfile bound) (role : Role)
    (valueEq : role.constantValue = some value) :
    RuntimeExpressionResult (bound.checked.shape.nodes.map (·.source)) context state
      (.call (.named [role.name]) []) (.scalar .word) (.value (.word value)) := by
  have facts : role.parameterKinds profile.operations.nominal profile.rejections.nominal = [] ∧
      role.resultKind = .scalar .word := by
    cases role <;> simp_all [Role.constantValue,Role.parameterKinds,Role.resultKind]
  have args : ArgumentsResult (bound.checked.shape.nodes.map (·.source)) context state []
      (role.parameterKinds profile.operations.nominal profile.rejections.nominal) [] := by
    rw [facts.1]
    exact ArgumentsResult.nil
  have result := profile.call_result role args
    (fun node member named after outcome events evaluated =>
      profile.constant_result node member named valueEq evaluated)
  simpa only [facts.2] using result

private theorem local_word (valid : RuntimeContextValid context)
    (binding : RuntimeVariableBinding context name declared)
    (kind : declared.kind = .scalar .word)
    (read : state.readBound declared = .value (.word value)) :
    RuntimeExpressionResult functions context state (.name [name]) (.scalar .word) (.value (.word value)) := by
  have result := RuntimeExpressionResult.readVariable (functions := functions) (state := state) valid binding
  rw [kind,read] at result
  exact result

private theorem owner_call (profile : ExactProfile bound)
    (argument : RuntimeExpressionResult (bound.checked.shape.nodes.map (·.source)) context state raw
      (.scalar .word) (.value (.word owner))) (bounded : owner < FramePolicy.u64Modulus) :
    RuntimeExpressionResult (bound.checked.shape.nodes.map (·.source)) context state
      (call "kernel_owner" [raw]) (.scalar .boolean)
      (.value (.boolean (decide (FramePolicy.KernelOwner owner)))) := by
  exact profile.call_result .kernelOwner (.cons argument .nil)
    (fun node member named after outcome events evaluated =>
      profile.kernel_owner_result node member named bounded evaluated)

private theorem compare_values
    (left : RuntimeExpressionResult functions context state lhs (.scalar .word) (.value (.word a)))
    (right : RuntimeExpressionResult functions context state rhs (.scalar .word) (.value (.word b)))
    (aBound : a < wordLimit) (bBound : b < wordLimit) :
    RuntimeExpressionResult functions context state (cmp comparison lhs rhs) (.scalar .boolean)
      (.value (.boolean (compareWords comparison a b))) := by
  have result := RuntimeExpressionResult.wordBinary (RuntimeWordOperator.compare (comparison := comparison)) left right
  simpa [Outcome.then,binaryValue,aBound,bBound] using result

private theorem and_values
    (left : RuntimeExpressionResult functions context state lhs (.scalar .boolean) (.value (.boolean a)))
    (right : RuntimeExpressionResult functions context state rhs (.scalar .boolean) (.value (.boolean b))) :
    RuntimeExpressionResult functions context state (bin .and lhs rhs) (.scalar .boolean)
      (.value (.boolean (a && b))) := by
  cases a
  · exact RuntimeExpressionResult.and_false left
  · exact RuntimeExpressionResult.and_true left right

/-- Proof bookkeeping for the actual two initialized cells. No alternate state
or transition relation: cells and reads must be witnessed in RuntimeLocals. -/
private structure RecordReadFacts (context : RuntimeExprContext) (state : RuntimeLocals) (record : Nat) where
  stateCell : SourceLocal
  wordCell : SourceLocal
  valid : RuntimeContextValid context
  stateVariable : RuntimeVariableBinding context (bytes "state") stateCell
  wordVariable : RuntimeVariableBinding context (bytes "word") wordCell
  stateKind : stateCell.kind = .scalar .word
  wordKind : wordCell.kind = .scalar .word
  stateRead : state.readBound stateCell = .value (.word (FramePolicy.stateOf record))
  wordRead : state.readBound wordCell = .value (.word (FramePolicy.wordOf record))

private def RecordReadFacts.reserved (facts : RecordReadFacts context state record)
    (accepted : state.reserveScopes limit = some next) : RecordReadFacts context next record :=
  { facts with stateRead := (reserve_read accepted).trans facts.stateRead
               wordRead := (reserve_read accepted).trans facts.wordRead }

private def RecordReadFacts.entered (facts : RecordReadFacts context state record)
    (accepted : state.enterAt scope = some next) : RecordReadFacts context next record :=
  { facts with stateRead := entered_read facts.stateRead accepted
               wordRead := entered_read facts.wordRead accepted }

private theorem RecordReadFacts.state_expr (facts : RecordReadFacts context state record) :
    RuntimeExpressionResult functions context state (v "state") (.scalar .word)
      (.value (.word (FramePolicy.stateOf record))) :=
  local_word facts.valid facts.stateVariable facts.stateKind facts.stateRead

private theorem RecordReadFacts.word_expr (facts : RecordReadFacts context state record) :
    RuntimeExpressionResult functions context state (v "word") (.scalar .word)
      (.value (.word (FramePolicy.wordOf record))) :=
  local_word facts.valid facts.wordVariable facts.wordKind facts.wordRead

private theorem decoded_state_bound (record : Nat) : FramePolicy.stateOf record < wordLimit := by
  have small := Nat.mod_lt record (by decide : 0 < 16)
  simp only [FramePolicy.stateOf,wordLimit]
  omega

private theorem decoded_word_bound (bounded : record < FramePolicy.u64Modulus) :
    FramePolicy.wordOf record < wordLimit := by
  have small := word_bound bounded
  simp only [FramePolicy.wordMax,wordLimit] at *
  omega

private theorem RecordReadFacts.state_test (facts : RecordReadFacts context state record)
    (profile : ExactProfile bound) (role : Role) (valueEq : role.constantValue = some value)
    (small : value < wordLimit) :
    RuntimeExpressionResult (bound.checked.shape.nodes.map (·.source)) context state
      (cmp .eq (v "state") (.call (.named [role.name]) [])) (.scalar .boolean)
      (.value (.boolean (decide (FramePolicy.stateOf record = value)))) := by
  exact compare_values facts.state_expr (constant_call profile role valueEq) (decoded_state_bound record) small

private theorem valid_final (profile : ExactProfile bound)
    (bounded : record < FramePolicy.u64Modulus)
    (facts : RecordReadFacts (runtimeStatementContext members module path formals before) state record)
    (notFree : FramePolicy.stateOf record ≠ 1) (notAllocated : FramePolicy.stateOf record ≠ 2)
    (notKernel : FramePolicy.stateOf record ≠ 3)
    (evaluated : RuntimeStatementsEvaluation (bound.checked.shape.nodes.map (·.source))
      members module path formals (.scalar .boolean) before state
      [ret (bin .and (cmp .eq (v "state") (call "frame_retired")) (cmp .eq (v "word") (.word 0)))]
      after outcome events) :
    ∃ final, outcome = .returned (.boolean (decide (FramePolicy.RecordValid record))) final := by
  have left := facts.state_test profile .retired rfl (by decide)
  have zero : RuntimeExpressionResult (bound.checked.shape.nodes.map (·.source))
      (runtimeStatementContext members module path formals before) state (.word 0)
      (.scalar .word) (.value (.word 0)) := by
    simpa [readScalar,wordLimit] using (RuntimeExpressionResult.word (value := 0)
      (functions := bound.checked.shape.nodes.map (·.source))
      (context := runtimeStatementContext members module path formals before) (state := state))
  have right := compare_values (comparison := CompareOp.eq) facts.word_expr zero
    (decoded_word_bound bounded) (by decide)
  have both := and_values left right
  have same := RuntimeExpressionResult.singleton both evaluated
  refine ⟨state,?_⟩
  simpa [FramePolicy.RecordValid,notFree,notAllocated,notKernel,compareWords,Bool.decide_and] using same

private theorem valid_kernel (profile : ExactProfile bound)
    (bounded : record < FramePolicy.u64Modulus)
    (facts : RecordReadFacts (runtimeStatementContext members module path formals before) state record)
    (notFree : FramePolicy.stateOf record ≠ 1) (notAllocated : FramePolicy.stateOf record ≠ 2)
    (evaluated : RuntimeStatementsEvaluation (bound.checked.shape.nodes.map (·.source))
      members module path formals (.scalar .boolean) before state
      [branch (cmp .eq (v "state") (call "frame_kernel")) [ret (call "kernel_owner" [v "word"])],
       ret (bin .and (cmp .eq (v "state") (call "frame_retired")) (cmp .eq (v "word") (.word 0)))]
      after outcome events) :
    ∃ final, outcome = .returned (.boolean (decide (FramePolicy.RecordValid record))) final := by
  have test := facts.state_test profile .kernel rfl (by decide)
  by_cases kernel : FramePolicy.stateOf record = 3
  · simp only [kernel,decide_true] at test
    obtain ⟨child,entered,se,enter,body⟩ := true_branch_body test (.returned) evaluated
    have childFacts := facts.entered enter
    have expression := owner_call profile childFacts.word_expr (decoded_word_bound bounded)
    have same := RuntimeExpressionResult.singleton (before := enterLocalScope before) expression body
    refine ⟨entered,?_⟩
    simpa [FramePolicy.RecordValid,kernel] using same
  · simp only [decide_eq_false kernel] at test
    obtain ⟨child,items,next,se,scopeProof,reserve,tail⟩ := false_branch_tail test evaluated
    exact valid_final (before := leaveLocalScope before child) profile bounded (facts.reserved reserve) notFree notAllocated kernel tail

private theorem valid_allocated (profile : ExactProfile bound)
    (bounded : record < FramePolicy.u64Modulus)
    (facts : RecordReadFacts (runtimeStatementContext members module path formals before) state record)
    (notFree : FramePolicy.stateOf record ≠ 1)
    (evaluated : RuntimeStatementsEvaluation (bound.checked.shape.nodes.map (·.source))
      members module path formals (.scalar .boolean) before state (recordValidShape.body.drop 3)
      after outcome events) :
    ∃ final, outcome = .returned (.boolean (decide (FramePolicy.RecordValid record))) final := by
  have test := facts.state_test profile .allocated rfl (by decide)
  by_cases allocated : FramePolicy.stateOf record = 2
  · simp only [allocated,decide_true] at test
    obtain ⟨child,entered,se,enter,body⟩ := true_branch_body test (.returned) evaluated
    have childFacts := facts.entered enter
    have zero : RuntimeExpressionResult (bound.checked.shape.nodes.map (·.source))
        (runtimeStatementContext members module path formals (enterLocalScope before)) entered (.word 0)
        (.scalar .word) (.value (.word 0)) := by
      simpa [readScalar,wordLimit] using (RuntimeExpressionResult.word (value := 0)
        (functions := bound.checked.shape.nodes.map (·.source))
        (context := runtimeStatementContext members module path formals (enterLocalScope before)) (state := entered))
    have left := compare_values (comparison := CompareOp.ne) childFacts.word_expr zero
      (decoded_word_bound bounded) (by decide)
    have right := RuntimeExpressionResult.not
      (owner_call profile childFacts.word_expr (decoded_word_bound bounded))
    simp only [Outcome.then,notValue] at right
    have expression := and_values left right
    have same := RuntimeExpressionResult.singleton (before := enterLocalScope before) expression body
    refine ⟨entered,?_⟩
    have validity : FramePolicy.RecordValid record =
        (FramePolicy.wordOf record ≠ 0 ∧ ¬ FramePolicy.KernelOwner (FramePolicy.wordOf record)) := by
      apply propext
      simp only [FramePolicy.RecordValid,allocated,Nat.reduceEqDiff,eq_self,true_and,
        false_and,false_or,or_false]
    simpa only [validity,compareWords,bne,Bool.beq_eq_decide_eq,Bool.decide_and,decide_not] using same
  · simp only [decide_eq_false allocated] at test
    obtain ⟨child,items,next,se,scopeProof,reserve,tail⟩ := false_branch_tail test evaluated
    exact valid_kernel (before := leaveLocalScope before child) profile bounded (facts.reserved reserve) notFree allocated tail

private theorem valid_suffix (profile : ExactProfile bound)
    (bounded : record < FramePolicy.u64Modulus)
    (facts : RecordReadFacts (runtimeStatementContext members module path formals before) state record)
    (evaluated : RuntimeStatementsEvaluation (bound.checked.shape.nodes.map (·.source))
      members module path formals (.scalar .boolean) before state (recordValidShape.body.drop 2)
      after outcome events) :
    ∃ final, outcome = .returned (.boolean (decide (FramePolicy.RecordValid record))) final := by
  have test := facts.state_test profile .free rfl (by decide)
  by_cases free : FramePolicy.stateOf record = 1
  · simp only [free,decide_true] at test
    obtain ⟨child,entered,se,enter,body⟩ := true_branch_body test (.returned) evaluated
    have same := RuntimeExpressionResult.singleton RuntimeExpressionResult.boolean body
    refine ⟨entered,?_⟩
    simpa [FramePolicy.RecordValid,free] using same
  · simp only [decide_eq_false free] at test
    obtain ⟨child,items,next,se,scopeProof,reserve,tail⟩ := false_branch_tail test evaluated
    exact valid_allocated (before := leaveLocalScope before child) profile bounded (facts.reserved reserve) free tail

private theorem const_word_declaration
    (scopeProof : ScopedStatement members module path formals before (localDecl name true raw) after [binding])
    (kind : binding.kind = .scalar .word) :
    binding = declaredLocal before (bytes name) (.scalar .word) false ∧
    after = addLocal before (declaredLocal before (bytes name) (.scalar .word) false) := by
  cases scopeProof with
  | declare typing allowed fresh clear named =>
    simp only [declaredLocal] at kind
    cases kind
    cases typing with
    | constant typing => exact ⟨rfl,rfl⟩
    | mutable typing => cases typing

/-- All actual evaluations of the checked record_valid body return its exact
numerical validity predicate. Both const declarations and every actual helper
call are inverted from source evaluation; no favorable local map is assumed. -/
theorem ExactProfile.record_valid_result (profile : ExactProfile bound)
    (node : RuntimeCallable (tables bound.artifact.document.reversed.reverse)
      files root frameModule framePath)
    (member : node ∈ bound.checked.shape.nodes) (named : node.name = Role.recordValid.name)
    (bounded : record < FramePolicy.u64Modulus)
    (evaluated : FunctionEvaluation profile node [.word record] after outcome events) :
    ∃ final, outcome = .returned (.boolean (decide (FramePolicy.RecordValid record))) final := by
  have nodeEq := profile.node_eq_role node member named
  have formals : node.source.context.formals = [formal "record"] := by
    rw [nodeEq]
    exact (profile.roles .recordValid).formals
  have kinds := profile.node_parameters node member named
  have initialValid := profile.initial_context node member
  let c0 : LocalContext := ⟨[],0,1,1⟩
  let stateCell := declaredLocal c0 (bytes "state") (.scalar .word) false
  let c1 := addLocal c0 stateCell
  let wordCell := declaredLocal c1 (bytes "word") (.scalar .word) false
  let c2 := addLocal c1 wordCell
  let recordCell : SourceLocal := ⟨bytes "record",.scalar .word,false,0,runtimeParameterSlot 0⟩
  let seed := formalSourceLocals [.scalar .word] (fun index => ([.word record] : List Value)[index]?)
  have boundedWord : record < wordLimit := bounded
  have initialRead : seed.readBound recordCell = .value (.word record) := by
    have reading := formal_read (kinds := [.scalar .word]) (index := 0) (name := bytes "record")
      (arguments := fun index => ([.word record] : List Value)[index]?) rfl
    simpa [readRuntime,readScalar,boundedWord] using reading
  have valid0 : RuntimeContextValid
      (runtimeStatementContext node.source.context.members frameModule framePath [formal "record"] c0) := by
    exact ⟨initialValid.scope,by simp only [RuntimeContextNames,runtimeStatementContext,c0]; decide⟩
  have binding0 : RuntimeVariableBinding
      (runtimeStatementContext node.source.context.members frameModule framePath [formal "record"] c0)
      (bytes "record") recordCell := by
    exact .formal (index := 0) rfl rfl .word (by simp only [runtimeStatementContext,c0]; decide)
  have recordExpression := local_word (functions := bound.checked.shape.nodes.map (·.source))
    valid0 binding0 rfl initialRead
  have literal15 : RuntimeExpressionResult (bound.checked.shape.nodes.map (·.source))
      (runtimeStatementContext node.source.context.members frameModule framePath [formal "record"] c0)
      seed (.word 15) (.scalar .word) (.value (.word 15)) := by
    simpa [readScalar,wordLimit] using (RuntimeExpressionResult.word (value := 15)
      (functions := bound.checked.shape.nodes.map (·.source))
      (context := runtimeStatementContext node.source.context.members frameModule framePath [formal "record"] c0)
      (state := seed))
  have stateExpression := RuntimeExpressionResult.wordBinary RuntimeWordOperator.bitAnd recordExpression literal15
  simp [Outcome.then,binaryValue,boundedWord] at stateExpression
  rw [state_mask] at stateExpression
  unfold FunctionEvaluation at evaluated
  rw [profile.node_body node member named,profile.node_result node member named,formals,kinds] at evaluated
  change RuntimeStatementsEvaluation _ _ frameModule framePath [formal "record"] (.scalar .boolean)
    c0 seed (localDecl "state" true (bin .bitAnd (v "record") (.word 15)) :: _) after outcome events at evaluated
  obtain ⟨first,middle,next,se,scopeProof,kind,initialized,tail⟩ := declaration_tail stateExpression evaluated
  obtain ⟨firstEq,middleEq⟩ := const_word_declaration scopeProof kind
  change first = stateCell at firstEq
  subst first
  change middle = c1 at middleEq
  subst middle
  have stateRead := initialize_read initialized
  have recordRead : next.readBound recordCell = .value (.word record) :=
    (initialize_other_read initialized (by decide : recordCell.slot ≠ stateCell.slot)).trans initialRead
  have valid1 : RuntimeContextValid
      (runtimeStatementContext node.source.context.members frameModule framePath [formal "record"] c1) :=
    ⟨initialValid.scope,by simp only [RuntimeContextNames,runtimeStatementContext,c0,c1,stateCell,addLocal,declaredLocal]; decide⟩
  have binding1 : RuntimeVariableBinding
      (runtimeStatementContext node.source.context.members frameModule framePath [formal "record"] c1)
      (bytes "record") recordCell := by
    exact .formal (index := 0) rfl rfl .word (by simp only [runtimeStatementContext,c0,c1,stateCell,addLocal,declaredLocal]; decide)
  have recordExpression1 := local_word (functions := bound.checked.shape.nodes.map (·.source))
    valid1 binding1 rfl recordRead
  have wordExpression := RuntimeExpressionResult.shiftRight recordExpression1 SourceShiftCount.thirtyTwo
  simp [Outcome.then,binaryValue,checkedShift,SignedLiteralCount.runtimeValue,
    SignedLiteralCount.value,signedLiteralCount,boundedWord] at wordExpression
  obtain ⟨second,middle2,next2,se2,scoped2,kind2,initialize2,tail2⟩ := declaration_tail wordExpression tail
  obtain ⟨secondEq,middle2Eq⟩ := const_word_declaration scoped2 kind2
  change second = wordCell at secondEq
  subst second
  change middle2 = c2 at middle2Eq
  subst middle2
  have wordRead := initialize_read initialize2
  have stateRead2 := (initialize_other_read initialize2 (by decide : stateCell.slot ≠ wordCell.slot)).trans stateRead
  have facts : RecordReadFacts
      (runtimeStatementContext node.source.context.members frameModule framePath [formal "record"] c2) next2 record := by
    refine ⟨stateCell,wordCell,⟨initialValid.scope,by simp only [RuntimeContextNames,runtimeStatementContext,c0,c1,c2,stateCell,wordCell,addLocal,declaredLocal]; decide⟩,?_,?_,rfl,rfl,stateRead2,wordRead⟩
    · exact .localValue (List.mem_cons_of_mem _ List.mem_cons_self) rfl (by simp only [runtimeStatementContext]; decide)
    · exact .localValue List.mem_cons_self rfl (by simp only [runtimeStatementContext]; decide)
  exact valid_suffix profile bounded facts tail2

end Aurora.SourceBinding.FramePolicyAttachment
