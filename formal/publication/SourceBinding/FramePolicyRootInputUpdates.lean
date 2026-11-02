import SourceBinding.FramePolicyRootInputs
namespace Aurora.SourceBinding.FramePolicyAttachment
open Aurora.Publication
variable {input : ByteArray} {files : List SourceFile} {root : Name}
variable {bound : RuntimeDAGBinding input files root frameModule framePath rootName}
variable {profile : ExactProfile bound}

def rootCursorContext (profile : ExactProfile bound) (cursor : LocalContext) : RuntimeExprContext :=
  runtimeStatementContext (rootInputContext profile).members frameModule framePath
    (rootInputContext profile).formals cursor

theorem root_parameter_slot_ne (lower : 5 ≤ nextSlot) (indexBound : index < 5) :
    runtimeParameterSlot index ≠ runtimeParameterSlot nextSlot := by
  unfold runtimeParameterSlot
  omega

/-- Only accepted initialization outside the actual five formal cells. -/
theorem RootInputState.initialized
    {declaration : RuntimeLocalDecl}
    (facts : RootInputState profile operation record owner generation link state)
    (accepted : state.initialize slot declaration value = some next)
    (distinct : ∀ i, i < 5 → runtimeParameterSlot i ≠ slot) :
    RootInputState profile operation record owner generation link next :=
  ⟨(initialize_other_read accepted (distinct 0 (by decide))).trans facts.operation_read,
   (initialize_other_read accepted (distinct 1 (by decide))).trans facts.record_read,
   (initialize_other_read accepted (distinct 2 (by decide))).trans facts.owner_read,
   (initialize_other_read accepted (distinct 3 (by decide))).trans facts.generation_read,
   (initialize_other_read accepted (distinct 4 (by decide))).trans facts.link_read⟩

theorem ExactProfile.root_formal_binding_at_cursor (profile : ExactProfile bound)
    {declaration : Formal} {kind : RuntimeType} (cursor : LocalContext)
    (formalAt : (rootInputContext profile).formals[index]? = some declaration)
    (kindAt : bound.checked.shape.rootNode.source.parameters[index]? = some kind)
    (clear : declaration.name ∉ cursor.visible.map (·.name)) :
    RuntimeVariableBinding (rootCursorContext profile cursor) declaration.name
      ⟨declaration.name,kind,false,0,runtimeParameterSlot index⟩ := by
  have sourceAt := congrArg (Option.map (·.type)) formalAt
  rw [← List.getElem?_map] at sourceAt
  obtain ⟨actual,found,declared⟩ := bound.checked.shape.rootNode.parameters.grammar.lookup sourceAt
  have same := Option.some.inj (found.symm.trans kindAt)
  subst actual
  exact RuntimeVariableBinding.formal formalAt rfl declared clear

/-- Context validity and no-shadow facts concern the actual source cursor;
    final root composition derives them, never assumes a code cursor equality. -/
theorem ExactProfile.root_formal_result_at_cursor (profile : ExactProfile bound)
    {declaration : Formal} {kind : RuntimeType} (cursor : LocalContext)
    (valid : RuntimeContextValid (rootCursorContext profile cursor))
    (formalAt : (rootInputContext profile).formals[index]? = some declaration)
    (kindAt : bound.checked.shape.rootNode.source.parameters[index]? = some kind)
    (clear : declaration.name ∉ cursor.visible.map (·.name))
    (reading : state.readBound ⟨declaration.name,kind,false,0,runtimeParameterSlot index⟩ = .value value) :
    RuntimeExpressionResult (bound.checked.shape.nodes.map (·.source)) (rootCursorContext profile cursor) state
      (.name [declaration.name]) kind (.value value) := by
  have expression := RuntimeExpressionResult.readVariable
    (functions := bound.checked.shape.nodes.map (·.source)) (state := state) valid
    (profile.root_formal_binding_at_cursor cursor formalAt kindAt clear)
  rw [reading] at expression
  exact expression

theorem RootInputState.operation_result_at_cursor
    (facts : RootInputState profile operation record owner generation link state)
    (cursor : LocalContext) (valid : RuntimeContextValid (rootCursorContext profile cursor))
    (clear : bytes "operation" ∉ cursor.visible.map (·.name)) :
    RuntimeExpressionResult (bound.checked.shape.nodes.map (·.source)) (rootCursorContext profile cursor) state
      (v "operation") (.nominal profile.operations.nominal) (.value (operationValue profile operation)) :=
  profile.root_formal_result_at_cursor (declaration := formal "operation" (.named [operationName])) (index := 0) cursor valid
    (by rw [profile.root_input_formals]; rfl) (by rw [profile.rootParameters]; rfl) clear facts.operation_read

theorem RootInputState.record_result_at_cursor
    (facts : RootInputState profile operation record owner generation link state)
    (cursor : LocalContext) (valid : RuntimeContextValid (rootCursorContext profile cursor))
    (clear : bytes "record" ∉ cursor.visible.map (·.name)) :
    RuntimeExpressionResult (bound.checked.shape.nodes.map (·.source)) (rootCursorContext profile cursor) state
      (v "record") (.scalar .word) (.value (.word record)) :=
  profile.root_formal_result_at_cursor (declaration := formal "record") (index := 1) cursor valid
    (by rw [profile.root_input_formals]; rfl) (by rw [profile.rootParameters]; rfl) clear facts.record_read

theorem RootInputState.owner_result_at_cursor
    (facts : RootInputState profile operation record owner generation link state)
    (cursor : LocalContext) (valid : RuntimeContextValid (rootCursorContext profile cursor))
    (clear : bytes "owner" ∉ cursor.visible.map (·.name)) :
    RuntimeExpressionResult (bound.checked.shape.nodes.map (·.source)) (rootCursorContext profile cursor) state
      (v "owner") (.scalar .word) (.value (.word owner)) :=
  profile.root_formal_result_at_cursor (declaration := formal "owner") (index := 2) cursor valid
    (by rw [profile.root_input_formals]; rfl) (by rw [profile.rootParameters]; rfl) clear facts.owner_read

theorem RootInputState.generation_result_at_cursor
    (facts : RootInputState profile operation record owner generation link state)
    (cursor : LocalContext) (valid : RuntimeContextValid (rootCursorContext profile cursor))
    (clear : bytes "generation" ∉ cursor.visible.map (·.name)) :
    RuntimeExpressionResult (bound.checked.shape.nodes.map (·.source)) (rootCursorContext profile cursor) state
      (v "generation") (.scalar .word) (.value (.word generation)) :=
  profile.root_formal_result_at_cursor (declaration := formal "generation") (index := 3) cursor valid
    (by rw [profile.root_input_formals]; rfl) (by rw [profile.rootParameters]; rfl) clear facts.generation_read

theorem RootInputState.link_result_at_cursor
    (facts : RootInputState profile operation record owner generation link state)
    (cursor : LocalContext) (valid : RuntimeContextValid (rootCursorContext profile cursor))
    (clear : bytes "link" ∉ cursor.visible.map (·.name)) :
    RuntimeExpressionResult (bound.checked.shape.nodes.map (·.source)) (rootCursorContext profile cursor) state
      (v "link") (.scalar .word) (.value (.word link)) :=
  profile.root_formal_result_at_cursor (declaration := formal "link") (index := 4) cursor valid
    (by rw [profile.root_input_formals]; rfl) (by rw [profile.rootParameters]; rfl) clear facts.link_read


theorem ExactProfile.operation_case_at_cursor (profile : ExactProfile bound)
    (operation : FramePolicy.Operation) (cursor : LocalContext)
    (clear : Unshadowed (rootInputContext profile).formals cursor.visible [operationName,operationSourceName operation]) :
    RuntimeEnumValue (rootCursorContext profile cursor) [operationName,operationSourceName operation]
      profile.operations.nominal operation.ordinal := by
  have present : Declaration.enumDecl operationName profile.operations.declaration.cases ∈
      (rootInputContext profile).members :=
    Eq.mp (congrArg (fun members => Declaration.enumDecl operationName profile.operations.declaration.cases ∈ members)
      profile.operationsScope) profile.operations.declaration.present
  have caseAt : profile.operations.declaration.cases[operation.ordinal]? = some (operationSourceName operation) := by
    cases operation <;> rw [profile.operationsCases] <;> rfl
  exact RuntimeEnumValue.caseValue present caseAt (Or.inl rfl) clear

theorem ExactProfile.operation_constant_result_at_cursor (profile : ExactProfile bound)
    (operation : FramePolicy.Operation) (cursor : LocalContext)
    (valid : RuntimeContextValid (rootCursorContext profile cursor))
    (clear : Unshadowed (rootInputContext profile).formals cursor.visible [operationName,operationSourceName operation]) :
    RuntimeExpressionResult (bound.checked.shape.nodes.map (·.source)) (rootCursorContext profile cursor) state
      (.name [operationName,operationSourceName operation]) (.nominal profile.operations.nominal)
      (.value (.nominal profile.operations.nominal.name operation.ordinal)) := by
  have known := profile.operation_case_at_cursor operation cursor clear
  have expression := RuntimeExpressionResult.enumValue (functions := bound.checked.shape.nodes.map (·.source))
    (state := state) valid known
  have ordinalBound : operation.ordinal < profile.operations.nominal.cases := by
    rw [profile.operation_cardinality]
    cases operation <;> decide
  rw [readRuntime_nominal _ _ ordinalBound] at expression
  exact expression

theorem ExactProfile.rejection_case_at_cursor (profile : ExactProfile bound)
    (rejection : FramePolicy.Rejection) (cursor : LocalContext)
    (clear : Unshadowed (rootInputContext profile).formals cursor.visible [rejectionName,rejectionSourceName rejection]) :
    RuntimeEnumValue (rootCursorContext profile cursor) [rejectionName,rejectionSourceName rejection]
      profile.rejections.nominal rejection.ordinal := by
  have present : Declaration.enumDecl rejectionName profile.rejections.declaration.cases ∈
      (rootInputContext profile).members :=
    Eq.mp (congrArg (fun members => Declaration.enumDecl rejectionName profile.rejections.declaration.cases ∈ members)
      profile.rejectionsScope) profile.rejections.declaration.present
  have caseAt : profile.rejections.declaration.cases[rejection.ordinal]? = some (rejectionSourceName rejection) := by
    cases rejection <;> rw [profile.rejectionsCases] <;> rfl
  exact RuntimeEnumValue.caseValue present caseAt (Or.inl rfl) clear

theorem ExactProfile.rejection_constant_result_at_cursor (profile : ExactProfile bound)
    (rejection : FramePolicy.Rejection) (cursor : LocalContext)
    (valid : RuntimeContextValid (rootCursorContext profile cursor))
    (clear : Unshadowed (rootInputContext profile).formals cursor.visible [rejectionName,rejectionSourceName rejection]) :
    RuntimeExpressionResult (bound.checked.shape.nodes.map (·.source)) (rootCursorContext profile cursor) state
      (.name [rejectionName,rejectionSourceName rejection]) (.nominal profile.rejections.nominal)
      (.value (.nominal profile.rejections.nominal.name rejection.ordinal)) := by
  have known := profile.rejection_case_at_cursor rejection cursor clear
  have expression := RuntimeExpressionResult.enumValue (functions := bound.checked.shape.nodes.map (·.source))
    (state := state) valid known
  have ordinalBound : rejection.ordinal < profile.rejections.nominal.cases := by
    rw [profile.rejection_cardinality]
    cases rejection <;> decide
  rw [readRuntime_nominal _ _ ordinalBound] at expression
  exact expression

end Aurora.SourceBinding.FramePolicyAttachment
