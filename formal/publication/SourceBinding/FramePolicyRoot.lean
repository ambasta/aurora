import SourceBinding.FramePolicyRootCalls
import SourceBinding.FramePolicyPacking
import SourceBinding.FramePolicyReject
import SourceBinding.FramePolicyCalls
import SourceBinding.FramePolicyFlow
import SourceBinding.FramePolicyStateUpdates
import SourceBinding.FramePolicyInputs
import SourceBinding.FramePolicyDecoding
import SourceBinding.FramePolicyRootInputs
import SourceBinding.FramePolicyRootLocalContext
import SourceBinding.FramePolicyRootPrefix

namespace Aurora.SourceBinding.FramePolicyAttachment
open Aurora.Publication
variable {input : ByteArray} {files : List SourceFile} {root : Name}
variable {bound : RuntimeDAGBinding input files root frameModule framePath rootName}

/-- Internal evidence about an actual resolved source cell, not an alternate
    policy state. The root proof constructs it from actual declarations/reads. -/
private structure RootWordRead (context : RuntimeExprContext) (state : RuntimeLocals)
    (name : String) (value : Nat) where
  binding : SourceLocal
  resolved : RuntimeVariableBinding context (bytes name) binding
  kind : binding.kind = .scalar .word
  reading : state.readBound binding = .value (.word value)

private theorem root_read_active {state : RuntimeLocals} {binding : SourceLocal}
    (read : state.readBound binding = .value value) : binding.scope ∈ state.scopes := by
  unfold RuntimeLocals.readBound at read
  split at read
  next declared =>
    simp only [RuntimeLocals.read,declared,SourceLocal.runtimeDeclaration] at read
    split at read
    next active => exact active
    next => cases read
  next => cases read

private def RootWordRead.reserved (facts : RootWordRead context state name value)
    (accepted : state.reserveScopes limit = some next) : RootWordRead context next name value :=
  { facts with reading := (reserve_read accepted).trans facts.reading }

private def RootWordRead.entered (facts : RootWordRead context state name value)
    (accepted : state.enterAt scope = some next) : RootWordRead context next name value :=
  { facts with reading := (enter_read (root_read_active facts.reading) accepted).trans facts.reading }

private theorem RootWordRead.expression (facts : RootWordRead context state name value)
    (valid : RuntimeContextValid context) :
    RuntimeExpressionResult functions context state (v name) (.scalar .word) (.value (.word value)) := by
  have expression := RuntimeExpressionResult.readVariable (functions := functions) (state := state) valid facts.resolved
  rw [facts.kind,facts.reading] at expression
  exact expression

private structure RootOperationRead (profile : ExactProfile bound) (context : RuntimeExprContext)
    (state : RuntimeLocals) (operation : FramePolicy.Operation) where
  resolved : RuntimeVariableBinding context (bytes "operation") (rootOperationBinding profile)
  reading : state.readBound (rootOperationBinding profile) = .value (operationValue profile operation)

private def RootOperationRead.reserved (facts : RootOperationRead profile context state operation)
    (accepted : state.reserveScopes limit = some next) : RootOperationRead profile context next operation :=
  { facts with reading := (reserve_read accepted).trans facts.reading }

private def RootOperationRead.entered (facts : RootOperationRead profile context state operation)
    (accepted : state.enterAt scope = some next) : RootOperationRead profile context next operation :=
  { facts with reading := (enter_read (root_read_active facts.reading) accepted).trans facts.reading }

private theorem RootOperationRead.expression (facts : RootOperationRead profile context state operation)
    (valid : RuntimeContextValid context) :
    RuntimeExpressionResult functions context state (v "operation") (.nominal profile.operations.nominal)
      (.value (operationValue profile operation)) := by
  have result := RuntimeExpressionResult.readVariable (functions := functions) (state := state) valid facts.resolved
  rw [facts.reading] at result
  exact result

/-- The final release continuation uses the actual checked addition and packing
    calls. Its bounds are consequences of the preceding not-at-limit branch. -/
private theorem root_release_final (profile : ExactProfile bound)
    (valid : RuntimeContextValid (runtimeStatementContext members module path formals before))
    (currentRead : RootWordRead (runtimeStatementContext members module path formals before) state "current" current)
    (linkRead : RootWordRead (runtimeStatementContext members module path formals before) state "link" link)
    (below : current < FramePolicy.generationMax) (linkBound : link ≤ FramePolicy.wordMax)
    (evaluated : RuntimeStatementsEvaluation (bound.checked.shape.nodes.map (·.source))
      members module path formals (.scalar .word) before state
      [packed "frame_free" (bin .add (v "current") (.word 1)) (v "link")]
      after outcome events) :
    ∃ final, outcome = .returned (.word (FramePolicy.pack 1 (current+1) link)) final := by
  have currentBound : current < wordLimit := by simp only [FramePolicy.generationMax,wordLimit] at *; omega
  have incrementBound : current+1 < wordLimit := by simp only [FramePolicy.generationMax,wordLimit] at *; omega
  change current < 18446744073709551616 at currentBound
  change current+1 < 18446744073709551616 at incrementBound
  have increment := RuntimeExpressionResult.wordBinary (functions := bound.checked.shape.nodes.map (·.source)) RuntimeWordOperator.add
    (currentRead.expression valid) (root_word (value := 1) (by decide))
  have incrementResult : RuntimeExpressionResult (bound.checked.shape.nodes.map (·.source))
      (runtimeStatementContext members module path formals before) state
      (bin .add (v "current") (.word 1)) (.scalar .word) (.value (.word (current+1))) := by
    simpa [Outcome.then,binaryValue,currentBound,incrementBound,wordLimit] using increment
  have expression := root_pack profile (root_constant profile .free rfl) incrementResult
    (linkRead.expression valid) (by decide) (by omega) linkBound
  have same := RuntimeExpressionResult.singleton expression evaluated
  exact ⟨_,same⟩

private theorem root_release_generation (profile : ExactProfile bound)
    (valid : RuntimeContextValid (runtimeStatementContext members module path formals before))
    (currentRead : RootWordRead (runtimeStatementContext members module path formals before) state "current" current)
    (linkRead : RootWordRead (runtimeStatementContext members module path formals before) state "link" link)
    (generationBound : current ≤ FramePolicy.generationMax) (linkBound : link ≤ FramePolicy.wordMax)
    (evaluated : RuntimeStatementsEvaluation (bound.checked.shape.nodes.map (·.source))
      members module path formals (.scalar .word) before state (transitionShape.body.drop 13)
      after outcome events) :
    ∃ final, outcome = .returned (.word (if current = FramePolicy.generationMax then
      FramePolicy.pack 4 current 0 else FramePolicy.pack 1 (current+1) link)) final := by
  have currentBound : current < wordLimit := by simp only [FramePolicy.generationMax,wordLimit] at *; omega
  change current < 18446744073709551616 at currentBound
  have comparison := RuntimeExpressionResult.wordBinary (RuntimeWordOperator.compare (comparison := .eq))
    (currentRead.expression valid) (root_constant profile .generationLimit rfl)
  have test : RuntimeExpressionResult (bound.checked.shape.nodes.map (·.source))
      (runtimeStatementContext members module path formals before) state
      (cmp .eq (v "current") (call "generation_limit")) (.scalar .boolean)
      (.value (.boolean (decide (current = FramePolicy.generationMax)))) := by
    simpa [Outcome.then,binaryValue,compareWords,currentBound,FramePolicy.generationMax,wordLimit] using comparison
  change RuntimeStatementsEvaluation _ _ _ _ _ _ _ _
    [branch (cmp .eq (v "current") (call "generation_limit"))
      [packed "frame_retired" (v "current") (.word 0)],
     packed "frame_free" (bin .add (v "current") (.word 1)) (v "link")] _ _ _ at evaluated
  by_cases full : current = FramePolicy.generationMax
  · simp only [full,decide_true] at test
    obtain ⟨child,entered,se,enter,body⟩ := true_branch_body test (.returned) evaluated
    have expression := root_pack profile (root_constant profile .retired rfl)
      ((currentRead.entered enter).expression valid) (root_word (value := 0) (by decide))
      (by decide) generationBound (by decide)
    have same := RuntimeExpressionResult.singleton (before := enterLocalScope before) expression body
    exact ⟨_,by simpa only [if_pos full] using same⟩
  · simp only [decide_eq_false full] at test
    obtain ⟨child,items,next,se,scopeProof,reserve,tail⟩ := false_branch_tail test evaluated
    obtain ⟨final,same⟩ := root_release_final (before := leaveLocalScope before child) profile valid (currentRead.reserved reserve)
      (linkRead.reserved reserve) (by omega) linkBound tail
    exact ⟨final,by simpa only [if_neg full] using same⟩

private theorem root_release_link (profile : ExactProfile bound)
    (valid : RuntimeContextValid (runtimeStatementContext members module path formals before))
    (currentRead : RootWordRead (runtimeStatementContext members module path formals before) state "current" current)
    (linkRead : RootWordRead (runtimeStatementContext members module path formals before) state "link" link)
    (rejections : ∀ reason, RuntimeEnumValue (runtimeStatementContext members module path formals before)
      [rejectionName,rejectionSourceName reason] profile.rejections.nominal reason.ordinal)
    (generationBound : current ≤ FramePolicy.generationMax) (linkBound : link < wordLimit)
    (evaluated : RuntimeStatementsEvaluation (bound.checked.shape.nodes.map (·.source))
      members module path formals (.scalar .word) before state (transitionShape.body.drop 12)
      after outcome events) :
    ∃ final, outcome = .returned (.word (if link > FramePolicy.wordMax then
      FramePolicy.encode (.reject .link) else if current = FramePolicy.generationMax then
      FramePolicy.pack 4 current 0 else FramePolicy.pack 1 (current+1) link)) final := by
  have test := root_compare (functions := bound.checked.shape.nodes.map (·.source)) (comparison := CompareOp.gt) (linkRead.expression valid)
    (root_word (value := FramePolicy.wordMax) (by decide)) linkBound (by decide)
  change RuntimeStatementsEvaluation _ _ _ _ _ _ _ _
    (branch (cmp .gt (v "link") (.word 4294967295)) [reject "link"] :: _) _ _ _ at evaluated
  by_cases large : link > FramePolicy.wordMax
  · have trueTest : compareWords .gt link FramePolicy.wordMax = true := by simpa [compareWords] using large
    rw [trueTest] at test
    obtain ⟨child,entered,se,enter,body⟩ := true_branch_body test (.returned) evaluated
    have expression := root_reject (state := entered) profile valid .link (rejections .link)
    have same := RuntimeExpressionResult.singleton (before := enterLocalScope before) expression body
    exact ⟨_,by simpa only [if_pos large] using same⟩
  · have falseTest : compareWords .gt link FramePolicy.wordMax = false := by simpa [compareWords] using large
    rw [falseTest] at test
    obtain ⟨child,items,next,se,scopeProof,reserve,tail⟩ := false_branch_tail test evaluated
    obtain ⟨final,same⟩ := root_release_generation (before := leaveLocalScope before child) profile valid
      (currentRead.reserved reserve) (linkRead.reserved reserve) generationBound (by omega) tail
    exact ⟨final,by simpa only [if_neg large] using same⟩

private theorem root_release_stale (profile : ExactProfile bound)
    (valid : RuntimeContextValid (runtimeStatementContext members module path formals before))
    (currentRead : RootWordRead (runtimeStatementContext members module path formals before) state "current" (FramePolicy.generationOf record))
    (generationRead : RootWordRead (runtimeStatementContext members module path formals before) state "generation" generation)
    (linkRead : RootWordRead (runtimeStatementContext members module path formals before) state "link" link)
    (rejections : ∀ reason, RuntimeEnumValue (runtimeStatementContext members module path formals before)
      [rejectionName,rejectionSourceName reason] profile.rejections.nominal reason.ordinal)
    (bounded : FramePolicy.InputsBounded record owner generation link)
    (recordValid : FramePolicy.RecordValid record) (user : FramePolicy.UserOwner owner)
    (allocated : FramePolicy.stateOf record = 2) (owned : FramePolicy.wordOf record = owner)
    (evaluated : RuntimeStatementsEvaluation (bound.checked.shape.nodes.map (·.source))
      members module path formals (.scalar .word) before state (transitionShape.body.drop 11)
      after outcome events) :
    ∃ final, outcome = .returned (.word (FramePolicy.encode (FramePolicy.transition .release record owner generation link))) final := by
  have genBound := FramePolicy.generation_bound record
  have currentBound : FramePolicy.generationOf record < wordLimit := by
    simp only [FramePolicy.generationMax,wordLimit] at *; omega
  have test := root_compare (functions := bound.checked.shape.nodes.map (·.source)) (comparison := CompareOp.ne)
    (generationRead.expression valid) (currentRead.expression valid) bounded.2.2.1 currentBound
  change RuntimeStatementsEvaluation _ _ _ _ _ _ _ _
    (branch (cmp .ne (v "generation") (v "current")) [reject "stale"] :: _) _ _ _ at evaluated
  by_cases stale : generation ≠ FramePolicy.generationOf record
  · have trueTest : compareWords .ne generation (FramePolicy.generationOf record) = true := by
      simpa [compareWords] using stale
    rw [trueTest] at test
    obtain ⟨child,entered,se,enter,body⟩ := true_branch_body test (.returned) evaluated
    have expression := root_reject (state := entered) profile valid .stale (rejections .stale)
    have same := RuntimeExpressionResult.singleton (before := enterLocalScope before) expression body
    exact ⟨_,by simpa [FramePolicy.transition,recordValid,user,allocated,owned,stale,FramePolicy.encode] using same⟩
  · have equal : generation = FramePolicy.generationOf record := Decidable.byContradiction stale
    have falseTest : compareWords .ne generation (FramePolicy.generationOf record) = false := by
      simp only [equal,compareWords,bne_self_eq_false]
    rw [falseTest] at test
    obtain ⟨child,items,next,se,scopeProof,reserve,tail⟩ := false_branch_tail test evaluated
    obtain ⟨final,same⟩ := root_release_link (before := leaveLocalScope before child) profile valid
      (currentRead.reserved reserve) (linkRead.reserved reserve) rejections genBound bounded.2.2.2 tail
    refine ⟨final,?_⟩
    by_cases large : link > FramePolicy.wordMax
    · simpa [FramePolicy.transition,recordValid,user,allocated,owned,equal,FramePolicy.encode,large] using same
    · by_cases full : FramePolicy.generationOf record = FramePolicy.generationMax
      · simpa [FramePolicy.transition,recordValid,user,allocated,owned,equal,FramePolicy.encode,large,full] using same
      · simpa [FramePolicy.transition,recordValid,user,allocated,owned,equal,FramePolicy.encode,large,full] using same

private theorem root_release_owner (profile : ExactProfile bound)
    (valid : RuntimeContextValid (runtimeStatementContext members module path formals before))
    (recordRead : RootWordRead (runtimeStatementContext members module path formals before) state "record" record)
    (ownerRead : RootWordRead (runtimeStatementContext members module path formals before) state "owner" owner)
    (currentRead : RootWordRead (runtimeStatementContext members module path formals before) state "current" (FramePolicy.generationOf record))
    (generationRead : RootWordRead (runtimeStatementContext members module path formals before) state "generation" generation)
    (linkRead : RootWordRead (runtimeStatementContext members module path formals before) state "link" link)
    (rejections : ∀ reason, RuntimeEnumValue (runtimeStatementContext members module path formals before)
      [rejectionName,rejectionSourceName reason] profile.rejections.nominal reason.ordinal)
    (bounded : FramePolicy.InputsBounded record owner generation link)
    (recordValid : FramePolicy.RecordValid record) (user : FramePolicy.UserOwner owner)
    (allocated : FramePolicy.stateOf record = 2)
    (evaluated : RuntimeStatementsEvaluation (bound.checked.shape.nodes.map (·.source))
      members module path formals (.scalar .word) before state (transitionShape.body.drop 10)
      after outcome events) :
    ∃ final, outcome = .returned (.word (FramePolicy.encode (FramePolicy.transition .release record owner generation link))) final := by
  have shifted := RuntimeExpressionResult.shiftRight (functions := bound.checked.shape.nodes.map (·.source))
    (recordRead.expression valid) SourceShiftCount.thirtyTwo
  have shiftedResult : RuntimeExpressionResult (bound.checked.shape.nodes.map (·.source))
      (runtimeStatementContext members module path formals before) state
      (bin .rightShift (v "record") (.signedCount 32)) (.scalar .word)
      (.value (.word (FramePolicy.wordOf record))) := by
    simpa [Outcome.then,binaryValue,SignedLiteralCount.runtimeValue,signedLiteralCount,checkedShift,bounded.1,wordLimit,FramePolicy.wordOf,FramePolicy.wordModulus] using shifted
  have wordBound := word_bound bounded.1
  have test := root_compare (functions := bound.checked.shape.nodes.map (·.source)) (comparison := CompareOp.ne)
    shiftedResult (ownerRead.expression valid) (by simp only [FramePolicy.wordMax,wordLimit] at *; omega) bounded.2.1
  change RuntimeStatementsEvaluation _ _ _ _ _ _ _ _
    (branch (cmp .ne (bin .rightShift (v "record") (.signedCount 32)) (v "owner")) [reject "wrong_owner"] :: _) _ _ _ at evaluated
  by_cases wrong : FramePolicy.wordOf record ≠ owner
  · have trueTest : compareWords .ne (FramePolicy.wordOf record) owner = true := by simpa [compareWords] using wrong
    rw [trueTest] at test
    obtain ⟨child,entered,se,enter,body⟩ := true_branch_body test (.returned) evaluated
    have expression := root_reject (state := entered) profile valid .wrongOwner (rejections .wrongOwner)
    have same := RuntimeExpressionResult.singleton (before := enterLocalScope before) expression body
    exact ⟨_,by simpa [FramePolicy.transition,recordValid,user,allocated,wrong,FramePolicy.encode] using same⟩
  · have owned : FramePolicy.wordOf record = owner := Decidable.byContradiction wrong
    have falseTest : compareWords .ne (FramePolicy.wordOf record) owner = false := by simp only [owned,compareWords,bne_self_eq_false]
    rw [falseTest] at test
    obtain ⟨child,items,next,se,scopeProof,reserve,tail⟩ := false_branch_tail test evaluated
    exact root_release_stale (before := leaveLocalScope before child) profile valid
      (currentRead.reserved reserve) (generationRead.reserved reserve) (linkRead.reserved reserve)
      rejections bounded recordValid user allocated owned tail

private theorem root_release_allocated (profile : ExactProfile bound)
    (valid : RuntimeContextValid (runtimeStatementContext members module path formals before))
    (stateRead : RootWordRead (runtimeStatementContext members module path formals before) state "state" (FramePolicy.stateOf record))
    (recordRead : RootWordRead (runtimeStatementContext members module path formals before) state "record" record)
    (ownerRead : RootWordRead (runtimeStatementContext members module path formals before) state "owner" owner)
    (currentRead : RootWordRead (runtimeStatementContext members module path formals before) state "current" (FramePolicy.generationOf record))
    (generationRead : RootWordRead (runtimeStatementContext members module path formals before) state "generation" generation)
    (linkRead : RootWordRead (runtimeStatementContext members module path formals before) state "link" link)
    (rejections : ∀ reason, RuntimeEnumValue (runtimeStatementContext members module path formals before)
      [rejectionName,rejectionSourceName reason] profile.rejections.nominal reason.ordinal)
    (bounded : FramePolicy.InputsBounded record owner generation link)
    (recordValid : FramePolicy.RecordValid record) (user : FramePolicy.UserOwner owner)
    (notKernel : FramePolicy.stateOf record ≠ 3) (notRetired : FramePolicy.stateOf record ≠ 4)
    (evaluated : RuntimeStatementsEvaluation (bound.checked.shape.nodes.map (·.source))
      members module path formals (.scalar .word) before state (transitionShape.body.drop 9)
      after outcome events) :
    ∃ final, outcome = .returned (.word (FramePolicy.encode (FramePolicy.transition .release record owner generation link))) final := by
  have stateBound : FramePolicy.stateOf record < wordLimit := by
    exact Nat.lt_trans (Nat.mod_lt record (by decide : 0 < 16))
      (by decide : 16 < wordLimit)
  have test := root_compare (functions := bound.checked.shape.nodes.map (·.source)) (comparison := CompareOp.ne)
    (stateRead.expression valid) (root_constant profile .allocated rfl) stateBound (by decide)
  change RuntimeStatementsEvaluation _ _ _ _ _ _ _ _
    (branch (cmp .ne (v "state") (call "frame_allocated")) [reject "not_allocated"] :: _) _ _ _ at evaluated
  by_cases wrong : FramePolicy.stateOf record ≠ 2
  · have trueTest : compareWords .ne (FramePolicy.stateOf record) 2 = true := by simpa [compareWords] using wrong
    rw [trueTest] at test
    obtain ⟨child,entered,se,enter,body⟩ := true_branch_body test (.returned) evaluated
    have expression := root_reject (state := entered) profile valid .notAllocated (rejections .notAllocated)
    have same := RuntimeExpressionResult.singleton (before := enterLocalScope before) expression body
    exact ⟨_,by simpa [FramePolicy.transition,recordValid,user,notKernel,notRetired,wrong,FramePolicy.encode] using same⟩
  · have allocated : FramePolicy.stateOf record = 2 := Decidable.byContradiction wrong
    have falseTest : compareWords .ne (FramePolicy.stateOf record) 2 = false := by simp only [allocated,compareWords,bne_self_eq_false]
    rw [falseTest] at test
    obtain ⟨child,items,next,se,scopeProof,reserve,tail⟩ := false_branch_tail test evaluated
    exact root_release_owner (before := leaveLocalScope before child) profile valid
      (recordRead.reserved reserve) (ownerRead.reserved reserve) (currentRead.reserved reserve)
      (generationRead.reserved reserve) (linkRead.reserved reserve)
      rejections bounded recordValid user allocated tail

private theorem root_allocate_body (profile : ExactProfile bound)
    (valid : RuntimeContextValid (runtimeStatementContext members module path formals before))
    (stateRead : RootWordRead (runtimeStatementContext members module path formals before) state "state" (FramePolicy.stateOf record))
    (ownerRead : RootWordRead (runtimeStatementContext members module path formals before) state "owner" owner)
    (currentRead : RootWordRead (runtimeStatementContext members module path formals before) state "current" (FramePolicy.generationOf record))
    (rejections : ∀ reason, RuntimeEnumValue (runtimeStatementContext members module path formals before)
      [rejectionName,rejectionSourceName reason] profile.rejections.nominal reason.ordinal)
    (recordValid : FramePolicy.RecordValid record) (user : FramePolicy.UserOwner owner)
    (notKernel : FramePolicy.stateOf record ≠ 3) (notRetired : FramePolicy.stateOf record ≠ 4)
    (evaluated : RuntimeStatementsEvaluation (bound.checked.shape.nodes.map (·.source))
      members module path formals (.scalar .word) before state
      [branch (cmp .ne (v "state") (call "frame_free")) [reject "not_free"],
       packed "frame_allocated" (v "current") (v "owner")]
      after outcome events) :
    ∃ final, outcome = .returned (.word (FramePolicy.encode (FramePolicy.transition .allocate record owner generation link))) final := by
  have stateBound : FramePolicy.stateOf record < wordLimit := by
    exact Nat.lt_trans (Nat.mod_lt record (by decide : 0 < 16))
      (by decide : 16 < wordLimit)
  have test := root_compare (functions := bound.checked.shape.nodes.map (·.source)) (comparison := CompareOp.ne)
    (stateRead.expression valid) (root_constant profile .free rfl) stateBound (by decide)
  by_cases wrong : FramePolicy.stateOf record ≠ 1
  · have trueTest : compareWords .ne (FramePolicy.stateOf record) 1 = true := by simpa [compareWords] using wrong
    rw [trueTest] at test
    obtain ⟨child,entered,se,enter,body⟩ := true_branch_body test (.returned) evaluated
    have expression := root_reject (state := entered) profile valid .notFree (rejections .notFree)
    have same := RuntimeExpressionResult.singleton (before := enterLocalScope before) expression body
    exact ⟨_,by simpa [FramePolicy.transition,recordValid,user,notKernel,notRetired,wrong,FramePolicy.encode] using same⟩
  · have free : FramePolicy.stateOf record = 1 := Decidable.byContradiction wrong
    have falseTest : compareWords .ne (FramePolicy.stateOf record) 1 = false := by simp only [free,compareWords,bne_self_eq_false]
    rw [falseTest] at test
    obtain ⟨child,items,next,se,scopeProof,reserve,tail⟩ := false_branch_tail test evaluated
    have expression := root_pack profile (root_constant profile .allocated rfl)
      ((currentRead.reserved reserve).expression valid) ((ownerRead.reserved reserve).expression valid)
      (by decide) (FramePolicy.generation_bound record) user.2
    have same := RuntimeExpressionResult.singleton (before := leaveLocalScope before child) expression tail
    exact ⟨_,by simpa [FramePolicy.transition,recordValid,user,notKernel,notRetired,free,FramePolicy.encode] using same⟩

private theorem root_dispatch (profile : ExactProfile bound)
    (valid : RuntimeContextValid (runtimeStatementContext members module path formals before))
    (operationRead : RootOperationRead profile (runtimeStatementContext members module path formals before) state operation)
    (stateRead : RootWordRead (runtimeStatementContext members module path formals before) state "state" (FramePolicy.stateOf record))
    (recordRead : RootWordRead (runtimeStatementContext members module path formals before) state "record" record)
    (ownerRead : RootWordRead (runtimeStatementContext members module path formals before) state "owner" owner)
    (currentRead : RootWordRead (runtimeStatementContext members module path formals before) state "current" (FramePolicy.generationOf record))
    (generationRead : RootWordRead (runtimeStatementContext members module path formals before) state "generation" generation)
    (linkRead : RootWordRead (runtimeStatementContext members module path formals before) state "link" link)
    (rejections : ∀ reason, RuntimeEnumValue (runtimeStatementContext members module path formals before)
      [rejectionName,rejectionSourceName reason] profile.rejections.nominal reason.ordinal)
    (allocateCase : RuntimeEnumValue (runtimeStatementContext members module path formals before)
      [operationName,operationSourceName .allocate] profile.operations.nominal FramePolicy.Operation.allocate.ordinal)
    (bounded : FramePolicy.InputsBounded record owner generation link)
    (recordValid : FramePolicy.RecordValid record) (user : FramePolicy.UserOwner owner)
    (notKernel : FramePolicy.stateOf record ≠ 3) (notRetired : FramePolicy.stateOf record ≠ 4)
    (allowed : operation = .allocate ∨ operation = .release)
    (evaluated : RuntimeStatementsEvaluation (bound.checked.shape.nodes.map (·.source))
      members module path formals (.scalar .word) before state (transitionShape.body.drop 8)
      after outcome events) :
    ∃ final, outcome = .returned (.word (FramePolicy.encode (FramePolicy.transition operation record owner generation link))) final := by
  have constant := RuntimeExpressionResult.enumValue (functions := bound.checked.shape.nodes.map (·.source))
    (state := state) valid allocateCase
  have ready := profile.operation_ready .allocate
  change readRuntime (.nominal profile.operations.nominal)
    (some (.nominal profile.operations.nominal.name FramePolicy.Operation.allocate.ordinal)) = _ at ready
  rw [ready] at constant
  have comparison := RuntimeExpressionResult.enumCompare (equal := true) (operationRead.expression valid) constant
  change RuntimeStatementsEvaluation _ _ _ _ _ _ _ _
    (branch (cmp .eq (v "operation") (op "allocate"))
      [branch (cmp .ne (v "state") (call "frame_free")) [reject "not_free"],
       packed "frame_allocated" (v "current") (v "owner")] :: _) _ _ _ at evaluated
  rcases allowed with allocate | release
  · subst operation
    have test : RuntimeExpressionResult (bound.checked.shape.nodes.map (·.source))
        (runtimeStatementContext members module path formals before) state
        (cmp .eq (v "operation") (op "allocate")) (.scalar .boolean) (.value (.boolean true)) := by
      simp only [Outcome.then,compareNominal,profile.operation_ready] at comparison
      exact comparison
    obtain ⟨child,entered,se,enter,body⟩ := true_branch_body test (.later (.returned)) evaluated
    exact root_allocate_body (before := enterLocalScope before) profile valid
      (stateRead.entered enter) (ownerRead.entered enter) (currentRead.entered enter)
      rejections recordValid user notKernel notRetired body
  · subst operation
    have test : RuntimeExpressionResult (bound.checked.shape.nodes.map (·.source))
        (runtimeStatementContext members module path formals before) state
        (cmp .eq (v "operation") (op "allocate")) (.scalar .boolean) (.value (.boolean false)) := by
      simp only [Outcome.then,compareNominal,profile.operation_ready] at comparison
      exact comparison
    obtain ⟨child,items,next,se,scopeProof,reserve,tail⟩ := false_branch_tail test evaluated
    exact root_release_allocated (before := leaveLocalScope before child) profile valid
      (stateRead.reserved reserve) (recordRead.reserved reserve) (ownerRead.reserved reserve)
      (currentRead.reserved reserve) (generationRead.reserved reserve) (linkRead.reserved reserve)
      rejections bounded recordValid user notKernel notRetired tail

private theorem root_retired (profile : ExactProfile bound)
    (valid : RuntimeContextValid (runtimeStatementContext members module path formals before))
    (operationRead : RootOperationRead profile (runtimeStatementContext members module path formals before) state operation)
    (stateRead : RootWordRead (runtimeStatementContext members module path formals before) state "state" (FramePolicy.stateOf record))
    (recordRead : RootWordRead (runtimeStatementContext members module path formals before) state "record" record)
    (ownerRead : RootWordRead (runtimeStatementContext members module path formals before) state "owner" owner)
    (currentRead : RootWordRead (runtimeStatementContext members module path formals before) state "current" (FramePolicy.generationOf record))
    (generationRead : RootWordRead (runtimeStatementContext members module path formals before) state "generation" generation)
    (linkRead : RootWordRead (runtimeStatementContext members module path formals before) state "link" link)
    (rejections : ∀ reason, RuntimeEnumValue (runtimeStatementContext members module path formals before)
      [rejectionName,rejectionSourceName reason] profile.rejections.nominal reason.ordinal)
    (allocateCase : RuntimeEnumValue (runtimeStatementContext members module path formals before)
      [operationName,operationSourceName .allocate] profile.operations.nominal FramePolicy.Operation.allocate.ordinal)
    (bounded : FramePolicy.InputsBounded record owner generation link)
    (recordValid : FramePolicy.RecordValid record) (user : FramePolicy.UserOwner owner)
    (notKernel : FramePolicy.stateOf record ≠ 3)
    (allowed : operation = .allocate ∨ operation = .release)
    (evaluated : RuntimeStatementsEvaluation (bound.checked.shape.nodes.map (·.source))
      members module path formals (.scalar .word) before state (transitionShape.body.drop 7)
      after outcome events) :
    ∃ final, outcome = .returned (.word (FramePolicy.encode (FramePolicy.transition operation record owner generation link))) final := by
  have stateBound : FramePolicy.stateOf record < wordLimit := by
    exact Nat.lt_trans (Nat.mod_lt record (by decide : 0 < 16))
      (by decide : 16 < wordLimit)
  have test := root_compare (functions := bound.checked.shape.nodes.map (·.source)) (comparison := CompareOp.eq)
    (stateRead.expression valid) (root_constant profile .retired rfl) stateBound (by decide)
  change RuntimeStatementsEvaluation _ _ _ _ _ _ _ _
    (branch (cmp .eq (v "state") (call "frame_retired")) [reject "retired"] :: _) _ _ _ at evaluated
  by_cases matched : FramePolicy.stateOf record = 4
  · have trueTest : compareWords .eq (FramePolicy.stateOf record) 4 = true := by
      change (_ == _) = true
      rw [matched]
      rfl
    rw [trueTest] at test
    obtain ⟨child,entered,se,enter,body⟩ := true_branch_body test (.returned) evaluated
    have expression := root_reject (state := entered) profile valid .retired (rejections .retired)
    have same := RuntimeExpressionResult.singleton (before := enterLocalScope before) expression body
    refine ⟨entered,?_⟩
    change outcome = .returned (.word (FramePolicy.encode (.reject .retired))) entered at same
    rcases allowed with rfl | rfl <;>
      simpa only [FramePolicy.transition,if_neg (not_not_intro recordValid),
        if_neg (not_not_intro user),if_neg notKernel,if_pos matched] using same
  · have different : FramePolicy.stateOf record ≠ 4 := matched
    have falseTest : compareWords .eq (FramePolicy.stateOf record) 4 = false := by
      change (_ == _) = false
      exact beq_eq_false_iff_ne.mpr different
    rw [falseTest] at test
    obtain ⟨child,items,next,se,scopeProof,reserve,tail⟩ := false_branch_tail test evaluated
    exact root_dispatch (before := leaveLocalScope before child) profile valid
      (operationRead.reserved reserve) (stateRead.reserved reserve) (recordRead.reserved reserve)
      (ownerRead.reserved reserve) (currentRead.reserved reserve)
      (generationRead.reserved reserve) (linkRead.reserved reserve)
      rejections allocateCase bounded recordValid user notKernel different allowed tail

private theorem root_kernel (profile : ExactProfile bound)
    (valid : RuntimeContextValid (runtimeStatementContext members module path formals before))
    (operationRead : RootOperationRead profile (runtimeStatementContext members module path formals before) state operation)
    (stateRead : RootWordRead (runtimeStatementContext members module path formals before) state "state" (FramePolicy.stateOf record))
    (recordRead : RootWordRead (runtimeStatementContext members module path formals before) state "record" record)
    (ownerRead : RootWordRead (runtimeStatementContext members module path formals before) state "owner" owner)
    (currentRead : RootWordRead (runtimeStatementContext members module path formals before) state "current" (FramePolicy.generationOf record))
    (generationRead : RootWordRead (runtimeStatementContext members module path formals before) state "generation" generation)
    (linkRead : RootWordRead (runtimeStatementContext members module path formals before) state "link" link)
    (rejections : ∀ reason, RuntimeEnumValue (runtimeStatementContext members module path formals before)
      [rejectionName,rejectionSourceName reason] profile.rejections.nominal reason.ordinal)
    (allocateCase : RuntimeEnumValue (runtimeStatementContext members module path formals before)
      [operationName,operationSourceName .allocate] profile.operations.nominal FramePolicy.Operation.allocate.ordinal)
    (bounded : FramePolicy.InputsBounded record owner generation link)
    (recordValid : FramePolicy.RecordValid record) (user : FramePolicy.UserOwner owner)
    (allowed : operation = .allocate ∨ operation = .release)
    (evaluated : RuntimeStatementsEvaluation (bound.checked.shape.nodes.map (·.source))
      members module path formals (.scalar .word) before state (transitionShape.body.drop 6)
      after outcome events) :
    ∃ final, outcome = .returned (.word (FramePolicy.encode (FramePolicy.transition operation record owner generation link))) final := by
  have stateBound : FramePolicy.stateOf record < wordLimit := by
    exact Nat.lt_trans (Nat.mod_lt record (by decide : 0 < 16))
      (by decide : 16 < wordLimit)
  have test := root_compare (functions := bound.checked.shape.nodes.map (·.source)) (comparison := CompareOp.eq)
    (stateRead.expression valid) (root_constant profile .kernel rfl) stateBound (by decide)
  change RuntimeStatementsEvaluation _ _ _ _ _ _ _ _
    (branch (cmp .eq (v "state") (call "frame_kernel")) [reject "kernel"] :: _) _ _ _ at evaluated
  by_cases matched : FramePolicy.stateOf record = 3
  · have trueTest : compareWords .eq (FramePolicy.stateOf record) 3 = true := by
      change (_ == _) = true
      rw [matched]
      rfl
    rw [trueTest] at test
    obtain ⟨child,entered,se,enter,body⟩ := true_branch_body test (.returned) evaluated
    have expression := root_reject (state := entered) profile valid .kernel (rejections .kernel)
    have same := RuntimeExpressionResult.singleton (before := enterLocalScope before) expression body
    refine ⟨entered,?_⟩
    change outcome = .returned (.word (FramePolicy.encode (.reject .kernel))) entered at same
    rcases allowed with rfl | rfl <;>
      simpa only [FramePolicy.transition,if_neg (not_not_intro recordValid),
        if_neg (not_not_intro user),if_pos matched] using same
  · have different : FramePolicy.stateOf record ≠ 3 := matched
    have falseTest : compareWords .eq (FramePolicy.stateOf record) 3 = false := by
      change (_ == _) = false
      exact beq_eq_false_iff_ne.mpr different
    rw [falseTest] at test
    obtain ⟨child,items,next,se,scopeProof,reserve,tail⟩ := false_branch_tail test evaluated
    exact root_retired (before := leaveLocalScope before child) profile valid
      (operationRead.reserved reserve) (stateRead.reserved reserve) (recordRead.reserved reserve)
      (ownerRead.reserved reserve) (currentRead.reserved reserve)
      (generationRead.reserved reserve) (linkRead.reserved reserve)
      rejections allocateCase bounded recordValid user different allowed tail

private theorem root_local_continuation (profile : ExactProfile bound)
    (bounded : FramePolicy.InputsBounded record owner generation link) :
    PrefixContinuation profile operation record owner generation link := by
  intro before state after outcome events empty lower inputs allowed recordValid user evaluated
  let stateCell := declaredLocal before (bytes "state") (.scalar .word) false
  let c1 := addLocal before stateCell
  let currentCell := declaredLocal c1 (bytes "current") (.scalar .word) false
  let c2 := addLocal c1 currentCell
  have initialValid : RuntimeContextValid (rootCursorContext profile before) := by
    change RuntimeContextValid (runtimeStatementContext bound.checked.shape.rootNode.source.context.members
      frameModule framePath bound.checked.shape.rootNode.source.context.formals before)
    rw [profile.root_input_cursor before empty]
    exact profile.root_input_context
  have recordExpression := inputs.record_result
  rw [← profile.root_input_cursor before empty] at recordExpression
  have stateExpression := RuntimeExpressionResult.wordBinary RuntimeWordOperator.bitAnd recordExpression
    (root_word (value := 15) (by decide))
  have rb : record < wordLimit := bounded.1
  simp [Outcome.then,binaryValue,rb] at stateExpression
  rw [state_mask] at stateExpression
  change InitializationEvaluation profile before state
    (localDecl "state" true (bin .bitAnd (v "record") (.word 15)) :: _) after outcome events at evaluated
  obtain ⟨first,middle,next,se,stateDecl,kind1,initialize1,tail⟩ := declaration_tail stateExpression evaluated
  have firstShape := profile.root_const_declaration stateDecl
  have firstEq := (List.cons.inj firstShape.2).1
  change first = stateCell at firstEq
  subst first
  have middleEq : middle = c1 := firstShape.1
  subst middle
  have valid1 := profile.root_const_context initialValid stateDecl lower (by simp [empty])
  have inputs1 := inputs.initialized initialize1 (fun i hi => root_parameter_slot_ne lower hi)
  have recordExpression1 := inputs1.record_result_at_cursor c1 valid1 (by
    simp only [c1,stateCell,addLocal,declaredLocal,empty,List.map_cons,List.map_nil]
    decide)
  have shifted := RuntimeExpressionResult.shiftRight recordExpression1 SourceShiftCount.four
  simp [Outcome.then,binaryValue,SignedLiteralCount.runtimeValue,signedLiteralCount,checkedShift,
    SignedLiteralCount.value,rb] at shifted
  have currentExpression := RuntimeExpressionResult.wordBinary RuntimeWordOperator.bitAnd shifted
    (root_constant profile .generationLimit rfl)
  have shiftedBound : record / 16 < wordLimit := Nat.lt_of_le_of_lt (Nat.div_le_self record 16) rb
  have limitBound : FramePolicy.generationMax < wordLimit := by decide
  simp [Outcome.then,binaryValue,shiftedBound,limitBound] at currentExpression
  rw [generation_mask] at currentExpression
  obtain ⟨second,middle2,next2,se2,currentDecl,kind2,initialize2,tail2⟩ := declaration_tail currentExpression tail
  have secondShape := profile.root_const_declaration currentDecl
  have secondEq := (List.cons.inj secondShape.2).1
  change second = currentCell at secondEq
  subst second
  have middle2Eq : middle2 = c2 := secondShape.1
  subst middle2
  have lower1 : 5 ≤ c1.nextSlot := by change 5 ≤ before.nextSlot+1; omega
  have inputs2 := inputs1.initialized initialize2 (fun i hi => root_parameter_slot_ne lower1 hi)
  have valid2 := (profile.root_two_local_contexts empty lower stateDecl currentDecl).2
  have stateReading1 := initialize_read initialize1
  have stateReading := (initialize_other_read initialize2
    (show stateCell.slot ≠ currentCell.slot by
      change 8*(before.nextSlot+1) ≠ 8*(before.nextSlot+1+1); omega)).trans stateReading1
  have currentReading := initialize_read initialize2
  have stateRead : RootWordRead (rootCursorContext profile c2) next2 "state" (FramePolicy.stateOf record) := by
    refine ⟨stateCell,?_,rfl,stateReading⟩
    refine RuntimeVariableBinding.localValue (context := rootCursorContext profile c2)
      (binding := stateCell) (name := bytes "state") ?_ rfl ?_
    · change stateCell ∈ currentCell :: stateCell :: before.visible
      exact List.mem_cons_of_mem _ List.mem_cons_self
    change bytes "state" ∉ (rootInputContext profile).formals.map (·.name)
    rw [profile.root_input_formals]
    decide
  have currentRead : RootWordRead (rootCursorContext profile c2) next2 "current" (FramePolicy.generationOf record) := by
    refine ⟨currentCell,?_,rfl,currentReading⟩
    refine RuntimeVariableBinding.localValue (context := rootCursorContext profile c2)
      (binding := currentCell) (name := bytes "current") ?_ rfl ?_
    · exact List.mem_cons_self
    change bytes "current" ∉ (rootInputContext profile).formals.map (·.name)
    rw [profile.root_input_formals]
    decide
  have wordRead (name : String) (index : Nat) (value : Nat)
      (formalAt : (rootInputContext profile).formals[index]? = some (formal name))
      (kindAt : bound.checked.shape.rootNode.source.parameters[index]? = some (.scalar .word))
      (clear : bytes name ∉ c2.visible.map (·.name))
      (reading : next2.readBound (rootWordBinding name index) = .value (.word value)) :
      RootWordRead (rootCursorContext profile c2) next2 name value :=
    ⟨rootWordBinding name index,profile.root_formal_binding_at_cursor c2 formalAt kindAt clear,rfl,reading⟩
  have recordRead := wordRead "record" 1 record (by rw [profile.root_input_formals]; rfl)
    (by rw [profile.rootParameters]; rfl) (by
      simp only [c2,c1,currentCell,stateCell,addLocal,declaredLocal,empty,List.map_cons,List.map_nil]; decide) inputs2.record_read
  have ownerRead := wordRead "owner" 2 owner (by rw [profile.root_input_formals]; rfl)
    (by rw [profile.rootParameters]; rfl) (by
      simp only [c2,c1,currentCell,stateCell,addLocal,declaredLocal,empty,List.map_cons,List.map_nil]; decide) inputs2.owner_read
  have generationRead := wordRead "generation" 3 generation (by rw [profile.root_input_formals]; rfl)
    (by rw [profile.rootParameters]; rfl) (by
      simp only [c2,c1,currentCell,stateCell,addLocal,declaredLocal,empty,List.map_cons,List.map_nil]; decide) inputs2.generation_read
  have linkRead := wordRead "link" 4 link (by rw [profile.root_input_formals]; rfl)
    (by rw [profile.rootParameters]; rfl) (by
      simp only [c2,c1,currentCell,stateCell,addLocal,declaredLocal,empty,List.map_cons,List.map_nil]; decide) inputs2.link_read
  have operationRead : RootOperationRead profile (rootCursorContext profile c2) next2 operation := by
    refine ⟨profile.root_formal_binding_at_cursor (declaration := formal "operation" (.named [operationName]))
      (index := 0) c2 (by rw [profile.root_input_formals]; rfl)
      (by rw [profile.rootParameters]; rfl) ?_,inputs2.operation_read⟩
    simp only [c2,c1,currentCell,stateCell,addLocal,declaredLocal,empty,List.map_cons,List.map_nil]
    decide
  have rejections (reason : FramePolicy.Rejection) : RuntimeEnumValue (rootCursorContext profile c2)
      [rejectionName,rejectionSourceName reason] profile.rejections.nominal reason.ordinal := by
    apply profile.rejection_case_at_cursor reason c2
    rw [profile.root_input_formals]
    simp only [Unshadowed,visibleNames,c2,c1,currentCell,stateCell,addLocal,declaredLocal,empty,
      transitionShape,formal,List.map_cons,List.map_nil,List.head?_cons,Option.toList_some,List.mem_singleton]
    intro first equal
    subst first
    decide
  have allocateCase : RuntimeEnumValue (rootCursorContext profile c2)
      [operationName,operationSourceName .allocate] profile.operations.nominal FramePolicy.Operation.allocate.ordinal := by
    apply profile.operation_case_at_cursor .allocate c2
    rw [profile.root_input_formals]
    simp only [Unshadowed,visibleNames,c2,c1,currentCell,stateCell,addLocal,declaredLocal,empty,
      transitionShape,formal,List.map_cons,List.map_nil,List.head?_cons,Option.toList_some,List.mem_singleton]
    intro first equal
    subst first
    decide
  exact root_kernel (before := c2) profile valid2 operationRead stateRead recordRead ownerRead currentRead
    generationRead linkRead rejections allocateCase bounded recordValid user allowed tail2

/-- Every actual source derivation of the exact checked policy returns its
    prioritized mathematical result. No helper result or successful-run premise. -/
theorem ExactProfile.source_result (profile : ExactProfile bound)
    (bounded : FramePolicy.InputsBounded record owner generation link)
    (evaluated : FunctionEvaluation profile bound.checked.shape.rootNode
      (arguments profile operation record owner generation link) after outcome events) :
    ∃ final, outcome = .returned
      (.word (FramePolicy.encode (FramePolicy.transition operation record owner generation link))) final :=
  profile.root_prefix_result bounded (root_local_continuation profile bounded) evaluated

end Aurora.SourceBinding.FramePolicyAttachment
