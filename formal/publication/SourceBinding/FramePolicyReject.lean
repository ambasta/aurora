import SourceBinding.FramePolicyHelpers
import SourceBinding.FramePolicyStateUpdates
import SourceBinding.FramePolicyFlow
namespace Aurora.SourceBinding.FramePolicyAttachment
open Aurora.Publication

private def codeBinding : SourceLocal := ⟨bytes "code",.scalar .word,true,0,16⟩
private def reasonBinding (identity : NominalIdentity) : SourceLocal :=
  ⟨bytes "reason",.nominal identity,false,0,8⟩
private def rejectFormals : List Formal := [formal "reason" (.named (names ["FrameRejection"]))]
private def rejectCursor (nextScope : Nat) : LocalContext := ⟨[codeBinding],0,nextScope,2⟩
private def rejectContext (members : List Declaration) : RuntimeExprContext :=
  ⟨members,frameModule,framePath,rejectFormals,[codeBinding]⟩

/-- Helper-private invariant about actual source locals, not an evaluator. -/
private structure RejectState (identity : NominalIdentity) (ordinal code : Nat) (state : RuntimeLocals) : Prop where
  scopes : state.scopes = [0]
  reason : state.readBound (reasonBinding identity) = .value (.nominal identity.name ordinal)
  code : state.readBound codeBinding = .value (.word code)
  declaration : state.declarations 16 = some codeBinding.runtimeDeclaration

private theorem reject_valid (scope : ScopeBindings members) : RuntimeContextValid (rejectContext members) :=
  ⟨scope,by change RuntimeContextNames (rejectContext []); decide⟩

private theorem word_result (bounded : value < wordLimit) :
    RuntimeExpressionResult functions context state (.word value) (.scalar .word) (.value (.word value)) := by
  simpa [readScalar,bounded] using
    (RuntimeExpressionResult.word (functions := functions) (context := context) (state := state) (value := value))

private theorem nil_terminal
    (evaluated : RuntimeStatementsEvaluation functions members module path formals result before state [] after outcome events) :
    after = before ∧ outcome = .continued state := by
  have actual := evaluated PUnit PUnit (fun _ _ _ => False) ⟨fun _ => none,PUnit.unit⟩ []
  generalize traceEq : events.map (RuntimeSourceEvent.toEffect (World := PUnit) (ExternalFault := PUnit)) = actualEvents at actual
  cases outcome <;> cases actual <;> exact ⟨rfl,rfl⟩

private theorem assign_singleton
    (visible : before.visible = [codeBinding]) (bounded : value < wordLimit)
    (evaluated : RuntimeStatementsEvaluation functions members module path formals result before state
      [.assign (bytes "code") (.word value)] after outcome events) :
    ∃ next, after = before ∧ outcome = .continued next ∧ state.assign 16 (.word value) = some next := by
  have invert {middle final firstEvents}
      (first : RuntimeStatementEvaluation functions members module path formals result before state
        (.assign (bytes "code") (.word value)) middle final firstEvents) :
      ∃ next, middle = before ∧ final = .continued next ∧ state.assign 16 (.word value) = some next := by
    obtain ⟨cursor,binding,member,named,mutable,alternatives⟩ := first.assignment_cases
    rw [visible] at member
    have same := List.mem_singleton.mp member
    subst binding
    rcases alternatives with faultCase | valueCase
    · obtain ⟨fault,expression,equal⟩ := faultCase
      have impossible := ((word_result bounded) _ _ _ expression).2
      cases impossible
    · obtain ⟨actual,next,expression,accepted,equal⟩ := valueCase
      have sameValue := ((word_result bounded) _ _ _ expression).2
      cases sameValue
      exact ⟨next,cursor,equal,accepted⟩
  rcases evaluated.cons_cases with normal | returned | trapped
  · obtain ⟨middle,next,fe,re,first,tail,trace⟩ := normal
    obtain ⟨actual,cursor,equal,accepted⟩ := invert first
    cases equal
    obtain ⟨endpoint,resultEq⟩ := nil_terminal tail
    exact ⟨_,endpoint.trans cursor,resultEq,accepted⟩
  · obtain ⟨middle,value,finished,items,first,tail,outcomeEq⟩ := returned
    obtain ⟨next,cursor,impossible,accepted⟩ := invert first
    cases impossible
  · obtain ⟨middle,fault,finished,items,first,tail,outcomeEq⟩ := trapped
    obtain ⟨next,cursor,impossible,accepted⟩ := invert first
    cases impossible

private theorem scoped_assign_singleton
    (proof : ScopedStatements members module path formals before
      [.assign name value] after items) : after = before := by
  cases proof with
  | cons first rest =>
    cases first with
    | assign => cases rest; rfl
    | receiverAssign enabled _ _ => cases enabled

private theorem reserve_state (valid : RejectState identity ordinal code state)
    (accepted : state.reserveScopes scope = some next) : RejectState identity ordinal code next := by
  unfold RuntimeLocals.reserveScopes at accepted
  split at accepted
  next => cases accepted; exact ⟨valid.scopes,valid.reason,valid.code,valid.declaration⟩
  next => cases accepted

private theorem entered_assignment_state (valid : RejectState identity ordinal code state)
    (entered : state.enterAt scope = some child)
    (assigned : child.assign 16 (.word value) = some finished)
    (reserved : finished.leave.reserveScopes limit = some next)
    (bounded : value < wordLimit) : RejectState identity ordinal value next := by
  obtain ⟨declaration,found,mutable,active,typed,update⟩ := assign_update assigned
  have enterEq : child = state.enter := by
    unfold RuntimeLocals.enterAt at entered
    split at entered
    next => exact Option.some.inj entered.symm
    next => cases entered
  subst child
  rw [update] at reserved
  have left : RejectState identity ordinal value
      ({state.enter with values := fun i => if i = 16 then some (.word value) else state.enter.values i}.leave) := by
    constructor
    · simp [RuntimeLocals.enter,RuntimeLocals.leave,valid.scopes]
    · simpa only [RuntimeLocals.enter,RuntimeLocals.leave,reasonBinding,RuntimeLocals.readBound,
        RuntimeLocals.read,SourceLocal.runtimeDeclaration,show (8:Nat) ≠ 16 by decide,if_false]
        using valid.reason
    · simp [RuntimeLocals.enter,RuntimeLocals.leave,RuntimeLocals.readBound,RuntimeLocals.read,
        codeBinding,SourceLocal.runtimeDeclaration,valid.declaration,valid.scopes,readRuntime,readScalar,bounded]
    · exact valid.declaration
  exact reserve_state left reserved

variable {input : ByteArray} {files : List SourceFile} {root : Name}
variable {bound : RuntimeDAGBinding input files root frameModule framePath rootName}

private theorem reject_guard (profile : ExactProfile bound)
    (valid : RejectState profile.rejections.nominal ordinal code state)
    (ordinalBound : ordinal < profile.rejections.nominal.cases)
    (caseAt : profile.rejections.declaration.cases[value]? = some caseName) :
    RuntimeExpressionResult (bound.checked.shape.nodes.map (·.source))
      (rejectContext bound.checked.shape.rootNode.source.context.members) state
      (cmp .eq (v "reason") (.name [rejectionName,caseName])) (.scalar .boolean)
      (.value (.boolean (decide (ordinal = value)))) := by
  have scope := (profile.initial_context bound.checked.shape.rootNode bound.checked.shape.rootMember).scope
  have present : Declaration.enumDecl rejectionName profile.rejections.declaration.cases ∈
      bound.checked.shape.rootNode.source.context.members :=
    Eq.mp (congrArg (fun members => Declaration.enumDecl rejectionName profile.rejections.declaration.cases ∈ members)
      profile.rejectionsScope) profile.rejections.declaration.present
  have typed : RuntimeSourceType bound.checked.shape.rootNode.source.context.members frameModule framePath
      (.named [rejectionName]) (.nominal profile.rejections.nominal) :=
    .nominal present (Or.inl rfl)
  have binding : RuntimeVariableBinding (rejectContext bound.checked.shape.rootNode.source.context.members)
      (bytes "reason") (reasonBinding profile.rejections.nominal) := by
    exact RuntimeVariableBinding.formal (context := rejectContext bound.checked.shape.rootNode.source.context.members)
      (declaration := formal "reason" (.named [rejectionName])) (index := 0) rfl rfl typed (by change bytes "reason" ∉ [bytes "code"]; decide)
  have left := RuntimeExpressionResult.readVariable (functions := bound.checked.shape.nodes.map (·.source))
    (state := state) (reject_valid scope) binding
  rw [valid.reason] at left
  have constant : RuntimeEnumValue (rejectContext bound.checked.shape.rootNode.source.context.members)
      [rejectionName,caseName] profile.rejections.nominal value := by
    apply RuntimeEnumValue.caseValue (context := rejectContext bound.checked.shape.rootNode.source.context.members) present caseAt (Or.inl rfl)
    change Unshadowed rejectFormals [codeBinding] [rejectionName,caseName]
    simp [Unshadowed,rejectFormals,codeBinding,formal,rejectionName,bytes,visibleNames]
    decide
  have right := RuntimeExpressionResult.enumValue (functions := bound.checked.shape.nodes.map (·.source))
    (state := state) (reject_valid scope) constant
  have valueBound : value < profile.rejections.nominal.cases := (List.getElem?_eq_some_iff.mp caseAt).1
  simp only [readRuntime_nominal _ _ valueBound] at right
  have both := RuntimeExpressionResult.enumCompare (equal := true) left right
  simpa [Outcome.then,compareNominal,readRuntime_nominal _ _ ordinalBound,
    readRuntime_nominal _ _ valueBound] using both

private theorem reject_branch (profile : ExactProfile bound)
    (valid : RejectState profile.rejections.nominal ordinal code state)
    (ordinalBound : ordinal < profile.rejections.nominal.cases)
    (caseAt : profile.rejections.declaration.cases[value]? = some caseName)
    (valueBound : value < wordLimit)
    (evaluated : RuntimeStatementEvaluation (bound.checked.shape.nodes.map (·.source))
      bound.checked.shape.rootNode.source.context.members frameModule framePath rejectFormals (.scalar .word)
      (rejectCursor scope) state
      (.ifThen (cmp .eq (v "reason") (.name [rejectionName,caseName])) [.assign (bytes "code") (.word value)])
      after outcome events) :
    ∃ next, after = rejectCursor (scope+1) ∧ outcome = .continued next ∧
      RejectState profile.rejections.nominal ordinal (if ordinal = value then value else code) next := by
  have guard := reject_guard profile valid ordinalBound caseAt
  obtain ⟨child,items,scopedBody,cursor,alternatives⟩ := evaluated.branch_cases
  have childEq := scoped_assign_singleton scopedBody
  subst child
  subst after
  rcases alternatives with faultCase | falseCase | continuedCase | returnedCase | trappedCase
  · obtain ⟨fault,expression,equal⟩ := faultCase
    have impossible := (guard _ _ _ expression).2
    cases impossible
  · obtain ⟨next,expression,reserved,equal⟩ := falseCase
    subst outcome
    have same := (guard _ _ _ expression).2
    have different : ordinal ≠ value := by
      intro equal; simp [equal] at same
    exact ⟨_,rfl,rfl,by simpa [different] using reserve_state valid reserved⟩
  · obtain ⟨entered,finished,next,ce,be,expression,enter,body,reserved,equal,trace⟩ := continuedCase
    subst outcome
    have same := (guard _ _ _ expression).2
    have equal : ordinal = value := by
      by_cases equal : ordinal = value
      · exact equal
      · simp [equal] at same
    obtain ⟨assignedNext,afterEq,outcomeEq,assigned⟩ := assign_singleton rfl valueBound body
    cases outcomeEq
    exact ⟨_,rfl,rfl,by simpa [equal] using entered_assignment_state valid enter assigned reserved valueBound⟩
  · obtain ⟨entered,returned,finished,ce,be,expression,enter,body,equal,trace⟩ := returnedCase
    obtain ⟨next,afterEq,impossible,assigned⟩ := assign_singleton rfl valueBound body
    cases impossible
  · obtain ⟨entered,fault,finished,ce,be,expression,enter,body,equal,trace⟩ := trappedCase
    obtain ⟨next,afterEq,impossible,assigned⟩ := assign_singleton rfl valueBound body
    cases impossible

private def rejectTail (pairs : List (String × Nat)) : List SourceStatement :=
  pairs.map (fun pair => branch (cmp .eq (v "reason") (reason pair.1))
    [.assign (bytes "code") (.word pair.2)]) ++
  [ret (bin .shift (v "code") (.signedCount 4))]

private theorem reject_suffix (profile : ExactProfile bound) (pairs : List (String × Nat))
    (casesValid : ∀ pair ∈ pairs,
      profile.rejections.declaration.cases[pair.2]? = some (bytes pair.1) ∧ pair.2 ≤ 10)
    (valid : RejectState profile.rejections.nominal ordinal code state)
    (ordinalBound : ordinal < profile.rejections.nominal.cases) (codeBound : code ≤ 10)
    (evaluated : RuntimeStatementsEvaluation (bound.checked.shape.nodes.map (·.source))
      bound.checked.shape.rootNode.source.context.members frameModule framePath rejectFormals (.scalar .word)
      (rejectCursor scope) state (rejectTail pairs) after outcome events) :
    ∃ final, outcome = .returned
      (.word ((pairs.foldl (fun current pair => if ordinal = pair.2 then pair.2 else current) code) * 16)) final := by
  induction pairs generalizing state code scope after outcome events with
  | nil =>
    have namesValid := reject_valid (profile.initial_context bound.checked.shape.rootNode bound.checked.shape.rootMember).scope
    have binding : RuntimeVariableBinding (rejectContext bound.checked.shape.rootNode.source.context.members)
        (bytes "code") codeBinding := by
      apply RuntimeVariableBinding.localValue (binding := codeBinding) (by exact List.mem_singleton_self _) rfl
      change bytes "code" ∉ [bytes "reason"]
      decide
    have expression := RuntimeExpressionResult.readVariable (functions := bound.checked.shape.nodes.map (·.source))
      (state := state) namesValid binding
    rw [valid.code] at expression
    have shifted := RuntimeExpressionResult.shiftLeft expression SourceShiftCount.four
    have small : code < wordLimit := by unfold wordLimit; omega
    have shiftedSmall : code * 16 < wordLimit := by unfold wordLimit; omega
    simp only [Outcome.then,binaryValue,signedLiteralCount,SignedLiteralCount.runtimeValue,
      checkedShift,SignedLiteralCount.value,if_true,show 2^4 = (16:Nat) by decide,small,shiftedSmall] at shifted
    have same := RuntimeExpressionResult.singleton shifted evaluated
    exact ⟨_,same⟩
  | cons pair rest ih =>
    have headValid := casesValid pair List.mem_cons_self
    have restValid : ∀ p ∈ rest, profile.rejections.declaration.cases[p.2]? = some (bytes p.1) ∧ p.2 ≤ 10 :=
      fun p member => casesValid p (List.mem_cons_of_mem _ member)
    change RuntimeStatementsEvaluation _ _ _ _ _ _ _ _ (_ :: rejectTail rest) _ _ _ at evaluated
    rcases evaluated.cons_cases with normal | returned | trapped
    · obtain ⟨middle,current,fe,re,first,tail,trace⟩ := normal
      obtain ⟨next,afterEq,resultEq,stateValid⟩ := reject_branch profile valid ordinalBound headValid.1
        (by unfold wordLimit; omega) first
      rw [afterEq] at tail
      cases resultEq
      have nextBound : (if ordinal = pair.2 then pair.2 else code) ≤ 10 := by
        split
        · exact headValid.2
        · exact codeBound
      exact ih restValid stateValid nextBound tail
    · obtain ⟨middle,value,finished,items,first,tail,outcomeEq⟩ := returned
      obtain ⟨next,afterEq,impossible,stateValid⟩ := reject_branch profile valid ordinalBound headValid.1
        (by unfold wordLimit; omega) first
      cases impossible
    · obtain ⟨middle,fault,finished,items,first,tail,outcomeEq⟩ := trapped
      obtain ⟨next,afterEq,impossible,stateValid⟩ := reject_branch profile valid ordinalBound headValid.1
        (by unfold wordLimit; omega) first
      cases impossible

private def rejectionSeed (identity : NominalIdentity) (ordinal : Nat) : RuntimeLocals :=
  formalSourceLocals [.nominal identity] (fun index => ([.nominal identity.name ordinal] : List Value)[index]?)

private theorem initialize_reject (ordinalBound : ordinal < identity.cases)
    (accepted : (rejectionSeed identity ordinal).initialize 16 codeBinding.runtimeDeclaration (.word 1) = some next) :
    RejectState identity ordinal 1 next := by
  obtain ⟨head,typed,update⟩ := initialize_update accepted
  constructor
  · rw [update]; rfl
  · rw [initialize_other_read accepted (by change (8:Nat) ≠ 16; decide)]
    have same := formal_read (name := bytes "reason") (kinds := [.nominal identity]) (index := 0)
      (arguments := fun i => ([.nominal identity.name ordinal] : List Value)[i]?) rfl
    simpa only [List.getElem?_cons_zero,readRuntime_nominal _ _ ordinalBound] using same
  · exact initialize_read accepted
  · rw [update]; rfl

/-- Every evaluation of the actual full mutable rejection helper returns the
    selected rejection code. Both none and operation retain the initial code 1;
    all nine later cases execute their actual assignment before the final shift.
    No successful-body, fixed lexical endpoint or cleanup premise is supplied. -/
theorem ExactProfile.frame_reject_result (profile : ExactProfile bound)
    (node : RuntimeCallable (tables bound.artifact.document.reversed.reverse)
      files root frameModule framePath)
    (member : node ∈ bound.checked.shape.nodes) (named : node.name = Role.frameReject.name)
    (ordinalBound : ordinal < 11)
    (evaluated : FunctionEvaluation profile node [.nominal profile.rejections.nominal.name ordinal]
      after outcome events) :
    ∃ final, outcome = .returned (.word ((if ordinal = 0 then 1 else ordinal) * 16)) final := by
  let pairs : List (String × Nat) := [("record",2),("owner",3),("link",4),("not_free",5),
    ("not_allocated",6),("kernel",7),("retired",8),("wrong_owner",9),("stale",10)]
  have validPairs : ∀ pair ∈ pairs,
      profile.rejections.declaration.cases[pair.2]? = some (bytes pair.1) ∧ pair.2 ≤ 10 := by
    rw [profile.rejectionsCases]
    change ∀ pair ∈ ([("record",2),("owner",3),("link",4),("not_free",5),
      ("not_allocated",6),("kernel",7),("retired",8),("wrong_owner",9),("stale",10)] : List (String × Nat)),
      rejectionCases[pair.2]? = some (bytes pair.1) ∧ pair.2 ≤ 10
    decide
  have foldValue : pairs.foldl (fun current pair => if ordinal = pair.2 then pair.2 else current) 1 =
      (if ordinal = 0 then 1 else ordinal) := by
    have values : ordinal = 0 ∨ ordinal = 1 ∨ ordinal = 2 ∨ ordinal = 3 ∨ ordinal = 4 ∨ ordinal = 5 ∨
      ordinal = 6 ∨ ordinal = 7 ∨ ordinal = 8 ∨ ordinal = 9 ∨ ordinal = 10 := by omega
    rcases values with rfl | rfl | rfl | rfl | rfl | rfl | rfl | rfl | rfl | rfl | rfl <;> rfl
  have actualBound : ordinal < profile.rejections.nominal.cases := by rw [profile.rejection_cardinality]; exact ordinalBound
  have nodeEq := profile.node_eq_role node member named
  have formals : node.source.context.formals = rejectFormals := by
    rw [nodeEq]
    exact (profile.roles .frameReject).formals
  have members : node.source.context.members = bound.checked.shape.rootNode.source.context.members := by
    rw [nodeEq]
    exact (profile.roles .frameReject).members
  unfold FunctionEvaluation at evaluated
  rw [profile.node_body node member named,profile.node_parameters node member named,
    profile.node_result node member named,formals,members] at evaluated
  change RuntimeStatementsEvaluation _ _ frameModule framePath rejectFormals (.scalar .word)
    ⟨[],0,1,1⟩ (rejectionSeed profile.rejections.nominal ordinal)
    (.localDecl (formal "code") (.word 1) :: rejectTail pairs) after outcome events at evaluated
  have initializer := word_result (functions := bound.checked.shape.nodes.map (·.source))
    (context := runtimeStatementContext bound.checked.shape.rootNode.source.context.members frameModule framePath rejectFormals ⟨[],0,1,1⟩)
    (state := rejectionSeed profile.rejections.nominal ordinal) (by decide : 1 < wordLimit)
  obtain ⟨binding,middle,next,restEvents,lexical,kindEq,accepted,tail⟩ := declaration_tail initializer evaluated
  cases lexical with
  | declare typing allowed clear unshadowed names =>
    cases typing with
    | mutable typ =>
      cases kindEq
      have initialized := initialize_reject actualBound accepted
      obtain ⟨final,result⟩ := reject_suffix profile pairs validPairs initialized actualBound (by decide : 1 ≤ 10) tail
      exact ⟨final,by simpa only [foldValue] using result⟩

end Aurora.SourceBinding.FramePolicyAttachment
