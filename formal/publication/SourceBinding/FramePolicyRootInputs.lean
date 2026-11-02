import SourceBinding.FramePolicyInputs
import SourceBinding.FramePolicyStateUpdates
namespace Aurora.SourceBinding.FramePolicyAttachment
open Aurora.Publication
variable {input : ByteArray} {files : List SourceFile} {root : Name}
variable {bound : RuntimeDAGBinding input files root frameModule framePath rootName}

def rootInputContext (_profile : ExactProfile bound) : RuntimeExprContext :=
  bound.checked.shape.rootNode.source.context

def rootOperationBinding (profile : ExactProfile bound) : SourceLocal :=
  ⟨bytes "operation",.nominal profile.operations.nominal,false,0,runtimeParameterSlot 0⟩
def rootWordBinding (name : String) (index : Nat) : SourceLocal :=
  ⟨bytes name,.scalar .word,false,0,runtimeParameterSlot index⟩

/-- Internal facts about the five actual source cells. The initial constructor
    derives them from the checked signature and typed inputs, not an oracle. -/
structure RootInputState (profile : ExactProfile bound) (operation : FramePolicy.Operation)
    (record owner generation link : Nat) (state : RuntimeLocals) : Prop where
  operation_read : state.readBound (rootOperationBinding profile) = .value (operationValue profile operation)
  record_read : state.readBound (rootWordBinding "record" 1) = .value (.word record)
  owner_read : state.readBound (rootWordBinding "owner" 2) = .value (.word owner)
  generation_read : state.readBound (rootWordBinding "generation" 3) = .value (.word generation)
  link_read : state.readBound (rootWordBinding "link" 4) = .value (.word link)

variable {profile : ExactProfile bound}

private theorem read_active {state : RuntimeLocals} {binding : SourceLocal}
    (read : state.readBound binding = .value value) : binding.scope ∈ state.scopes := by
  unfold RuntimeLocals.readBound at read
  split at read
  next declared =>
    simp only [RuntimeLocals.read,declared,SourceLocal.runtimeDeclaration] at read
    split at read
    next active => exact active
    next => cases read
  next => cases read

theorem RootInputState.reserved (facts : RootInputState profile operation record owner generation link state)
    (accepted : state.reserveScopes limit = some next) : RootInputState profile operation record owner generation link next :=
  ⟨(reserve_read accepted).trans facts.operation_read,
   (reserve_read accepted).trans facts.record_read,(reserve_read accepted).trans facts.owner_read,
   (reserve_read accepted).trans facts.generation_read,(reserve_read accepted).trans facts.link_read⟩

theorem RootInputState.entered (facts : RootInputState profile operation record owner generation link state)
    (accepted : state.enterAt scope = some next) : RootInputState profile operation record owner generation link next :=
  ⟨(enter_read (read_active facts.operation_read) accepted).trans facts.operation_read,
   (enter_read (read_active facts.record_read) accepted).trans facts.record_read,
   (enter_read (read_active facts.owner_read) accepted).trans facts.owner_read,
   (enter_read (read_active facts.generation_read) accepted).trans facts.generation_read,
   (enter_read (read_active facts.link_read) accepted).trans facts.link_read⟩

theorem RootInputState.initial (profile : ExactProfile bound) (operation : FramePolicy.Operation)
    (bounded : FramePolicy.InputsBounded record owner generation link) :
    RootInputState profile operation record owner generation link
      (formalSourceLocals bound.checked.shape.rootNode.source.parameters
        (fun index => (arguments profile operation record owner generation link)[index]?)) := by
  have generic (index : Nat) (kind : RuntimeType) (name : ByteArray)
      (found : bound.checked.shape.rootNode.source.parameters[index]? = some kind) :=
    formal_read (name := name) (arguments := fun i => (arguments profile operation record owner generation link)[i]?) found
  constructor
  · have reading := generic 0 (.nominal profile.operations.nominal) (bytes "operation") (by rw [profile.rootParameters]; rfl)
    simpa only [arguments,List.getElem?_cons_zero,profile.operation_ready operation] using reading
  · have reading := generic 1 (.scalar .word) (bytes "record") (by rw [profile.rootParameters]; rfl)
    simpa [arguments,readRuntime,readScalar,wordLimit,bounded.1] using reading
  · have reading := generic 2 (.scalar .word) (bytes "owner") (by rw [profile.rootParameters]; rfl)
    simpa [arguments,readRuntime,readScalar,wordLimit,bounded.2.1] using reading
  · have reading := generic 3 (.scalar .word) (bytes "generation") (by rw [profile.rootParameters]; rfl)
    simpa [arguments,readRuntime,readScalar,wordLimit,bounded.2.2.1] using reading
  · have reading := generic 4 (.scalar .word) (bytes "link") (by rw [profile.rootParameters]; rfl)
    simpa [arguments,readRuntime,readScalar,wordLimit,bounded.2.2.2] using reading

theorem ExactProfile.root_input_formals (profile : ExactProfile bound) :
    (rootInputContext profile).formals = transitionShape.formals := by
  have named : bound.checked.shape.rootNode.name = Role.transition.name := bound.checked.shape.rootNameEq
  change bound.checked.shape.rootNode.source.context.formals = _
  rw [profile.node_eq_role _ bound.checked.shape.rootMember named]
  exact (profile.roles .transition).formals

theorem ExactProfile.root_input_context (profile : ExactProfile bound) : RuntimeContextValid (rootInputContext profile) :=
  profile.initial_context _ bound.checked.shape.rootMember

/-- Scoped cursors with no visible locals have exactly the selected expression
    context, without assuming a dynamic execution reaches any particular cursor. -/
theorem ExactProfile.root_input_cursor (profile : ExactProfile bound) (cursor : LocalContext)
    (empty : cursor.visible = []) :
    runtimeStatementContext bound.checked.shape.rootNode.source.context.members frameModule framePath
      bound.checked.shape.rootNode.source.context.formals cursor = rootInputContext profile := by
  unfold runtimeStatementContext rootInputContext
  rw [empty]
  rfl

private theorem root_formal_result (profile : ExactProfile bound) {declaration : Formal} {kind : RuntimeType}
    (formalAt : (rootInputContext profile).formals[index]? = some declaration)
    (kindAt : bound.checked.shape.rootNode.source.parameters[index]? = some kind)
    (reading : state.readBound ⟨declaration.name,kind,false,0,runtimeParameterSlot index⟩ = .value value) :
    RuntimeExpressionResult (bound.checked.shape.nodes.map (·.source)) (rootInputContext profile) state
      (.name [declaration.name]) kind (.value value) := by
  have sourceAt := congrArg (Option.map (·.type)) formalAt
  rw [← List.getElem?_map] at sourceAt
  obtain ⟨actual,found,declared⟩ := bound.checked.shape.rootNode.parameters.grammar.lookup sourceAt
  have same := Option.some.inj (found.symm.trans kindAt)
  subst actual
  have binding : RuntimeVariableBinding (rootInputContext profile) declaration.name
      ⟨declaration.name,kind,false,0,runtimeParameterSlot index⟩ := by
    apply RuntimeVariableBinding.formal formalAt rfl declared
    simp only [rootInputContext,RuntimeCallable.source,runtimeReturnContext,List.map_nil,List.not_mem_nil,not_false_eq_true]
  have expression := RuntimeExpressionResult.readVariable (functions := bound.checked.shape.nodes.map (·.source))
    (state := state) profile.root_input_context binding
  rw [reading] at expression
  exact expression

theorem RootInputState.operation_result (facts : RootInputState profile operation record owner generation link state) :
    RuntimeExpressionResult (bound.checked.shape.nodes.map (·.source)) (rootInputContext profile) state
      (v "operation") (.nominal profile.operations.nominal) (.value (operationValue profile operation)) :=
  root_formal_result profile (declaration := formal "operation" (.named [operationName])) (index := 0) (by rw [profile.root_input_formals]; rfl)
    (by rw [profile.rootParameters]; rfl) facts.operation_read

theorem RootInputState.record_result (facts : RootInputState profile operation record owner generation link state) :
    RuntimeExpressionResult (bound.checked.shape.nodes.map (·.source)) (rootInputContext profile) state
      (v "record") (.scalar .word) (.value (.word record)) :=
  root_formal_result profile (declaration := formal "record") (index := 1) (by rw [profile.root_input_formals]; rfl)
    (by rw [profile.rootParameters]; rfl) facts.record_read

theorem RootInputState.owner_result (facts : RootInputState profile operation record owner generation link state) :
    RuntimeExpressionResult (bound.checked.shape.nodes.map (·.source)) (rootInputContext profile) state
      (v "owner") (.scalar .word) (.value (.word owner)) :=
  root_formal_result profile (declaration := formal "owner") (index := 2) (by rw [profile.root_input_formals]; rfl)
    (by rw [profile.rootParameters]; rfl) facts.owner_read

theorem RootInputState.generation_result (facts : RootInputState profile operation record owner generation link state) :
    RuntimeExpressionResult (bound.checked.shape.nodes.map (·.source)) (rootInputContext profile) state
      (v "generation") (.scalar .word) (.value (.word generation)) :=
  root_formal_result profile (declaration := formal "generation") (index := 3) (by rw [profile.root_input_formals]; rfl)
    (by rw [profile.rootParameters]; rfl) facts.generation_read

theorem RootInputState.link_result (facts : RootInputState profile operation record owner generation link state) :
    RuntimeExpressionResult (bound.checked.shape.nodes.map (·.source)) (rootInputContext profile) state
      (v "link") (.scalar .word) (.value (.word link)) :=
  root_formal_result profile (declaration := formal "link") (index := 4) (by rw [profile.root_input_formals]; rfl)
    (by rw [profile.rootParameters]; rfl) facts.link_read

theorem ExactProfile.operation_constant_result (profile : ExactProfile bound) (operation : FramePolicy.Operation) :
    RuntimeExpressionResult (bound.checked.shape.nodes.map (·.source)) (rootInputContext profile) state
      (.name [operationName,operationSourceName operation]) (.nominal profile.operations.nominal)
      (.value (operationValue profile operation)) := by
  have present : Declaration.enumDecl operationName profile.operations.declaration.cases ∈
      (rootInputContext profile).members :=
    Eq.mp (congrArg (fun members => Declaration.enumDecl operationName profile.operations.declaration.cases ∈ members)
      profile.operationsScope) profile.operations.declaration.present
  have caseAt : profile.operations.declaration.cases[operation.ordinal]? = some (operationSourceName operation) := by
    cases operation <;> rw [profile.operationsCases] <;> rfl
  have known : RuntimeEnumValue (rootInputContext profile) [operationName,operationSourceName operation]
      profile.operations.nominal operation.ordinal := by
    apply RuntimeEnumValue.caseValue (context := rootInputContext profile) present caseAt (Or.inl rfl)
    change Unshadowed (rootInputContext profile).formals [] [operationName,operationSourceName operation]
    rw [profile.root_input_formals]
    simp [Unshadowed,visibleNames,transitionShape,formal,operationName,bytes]
    decide
  have expression := RuntimeExpressionResult.enumValue (functions := bound.checked.shape.nodes.map (·.source))
    (state := state) profile.root_input_context known
  have ready := profile.operation_ready operation
  change readRuntime (.nominal profile.operations.nominal) (some (.nominal profile.operations.nominal.name operation.ordinal)) = _ at ready
  rw [ready] at expression
  exact expression

theorem ExactProfile.rejection_constant_result (profile : ExactProfile bound) (rejection : FramePolicy.Rejection) :
    RuntimeExpressionResult (bound.checked.shape.nodes.map (·.source)) (rootInputContext profile) state
      (.name [rejectionName,rejectionSourceName rejection]) (.nominal profile.rejections.nominal)
      (.value (.nominal profile.rejections.nominal.name rejection.ordinal)) := by
  have present : Declaration.enumDecl rejectionName profile.rejections.declaration.cases ∈
      (rootInputContext profile).members :=
    Eq.mp (congrArg (fun members => Declaration.enumDecl rejectionName profile.rejections.declaration.cases ∈ members)
      profile.rejectionsScope) profile.rejections.declaration.present
  have caseAt : profile.rejections.declaration.cases[rejection.ordinal]? = some (rejectionSourceName rejection) := by
    cases rejection <;> rw [profile.rejectionsCases] <;> rfl
  have known : RuntimeEnumValue (rootInputContext profile) [rejectionName,rejectionSourceName rejection]
      profile.rejections.nominal rejection.ordinal := by
    apply RuntimeEnumValue.caseValue (context := rootInputContext profile) present caseAt (Or.inl rfl)
    change Unshadowed (rootInputContext profile).formals [] [rejectionName,rejectionSourceName rejection]
    rw [profile.root_input_formals]
    simp [Unshadowed,visibleNames,transitionShape,formal,rejectionName,bytes]
    decide
  have expression := RuntimeExpressionResult.enumValue (functions := bound.checked.shape.nodes.map (·.source))
    (state := state) profile.root_input_context known
  have ordinalBound : rejection.ordinal < profile.rejections.nominal.cases := by
    rw [profile.rejection_cardinality]
    cases rejection <;> decide
  rw [readRuntime_nominal _ _ ordinalBound] at expression
  exact expression

end Aurora.SourceBinding.FramePolicyAttachment
