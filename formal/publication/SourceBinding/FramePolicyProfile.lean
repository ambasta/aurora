import SourceBinding.FramePolicySyntax
import SourceBinding.FramePolicySpec
import SourceBinding.RuntimeDAGBinding

namespace Aurora.SourceBinding.FramePolicyAttachment
open Aurora.Publication

/-- Finite checked role selection, with no semantic result or success premise.
The node, full parsed body and runtime signature belong to the same DAG. -/
structure RoleNode (dag : RuntimeDAGCertificate t files root frameModule framePath rootName)
    (operations rejections : NominalIdentity) (role : Role) where
  node : RuntimeCallable t files root frameModule framePath
  member : node ∈ dag.shape.nodes
  named : node.name = role.name
  formals : node.source.function.formals = role.shape.formals
  resultSyntax : node.source.function.result = role.shape.result
  body : node.source.parsed.statements = role.shape.body
  parameters : node.source.parameters = role.parameterKinds operations rejections
  resultKind : node.source.result = role.resultKind
  members : node.source.context.members = dag.shape.rootNode.source.context.members

/-- Exact policy attachment to actual supplied bytes. The graph root is
independent of the selected kernel.frames module. Whole AST/name/type equalities
are checked, not hashes. No helper result, favorable run or no-fault assumption
appears in this certificate. -/
structure ExactProfile
    (bound : RuntimeDAGBinding input files root frameModule framePath rootName) where
  operations : SelectedEnum files root frameModule framePath operationName
  rejections : SelectedEnum files root frameModule framePath rejectionName
  operationsCases : operations.declaration.cases = operationCases
  rejectionsCases : rejections.declaration.cases = rejectionCases
  operationsScope : operations.scope.members = bound.checked.shape.rootNode.source.context.members
  rejectionsScope : rejections.scope.members = bound.checked.shape.rootNode.source.context.members
  roles : (role : Role) → RoleNode bound.checked operations.nominal rejections.nominal role
  uniqueNames : (bound.checked.shape.nodes.map (·.name)).Nodup
  coverage : ∀ node ∈ bound.checked.shape.nodes, ∃ role ∈ Role.all, node.name = role.name
  rootParameters : bound.checked.shape.rootNode.source.parameters =
    [.nominal operations.nominal,.scalar .word,.scalar .word,.scalar .word,.scalar .word]
  rootResult : bound.checked.shape.rootNode.source.result = .scalar .word

variable {input : ByteArray} {files : List SourceFile} {root : Name}
variable {bound : RuntimeDAGBinding input files root frameModule framePath rootName}

def ExactProfile.nodeFor (profile : ExactProfile bound) (role : Role) :
    RuntimeCallable (tables bound.artifact.document.reversed.reverse) files root frameModule framePath :=
  (profile.roles role).node

/-- Embedding in the selected nominal type; not an enum-to-word conversion.
Exact source-case correspondence is a separate derived lemma. -/
def operationValue (profile : ExactProfile bound) (operation : FramePolicy.Operation) : Value :=
  .nominal profile.operations.nominal.name operation.ordinal

def arguments (profile : ExactProfile bound) (operation : FramePolicy.Operation)
    (record owner generation link : Nat) : List Value :=
  [operationValue profile operation,.word record,.word owner,.word generation,.word link]

/-- Merely the existing source judgment with actual formal initialization.
`after` is arbitrary: nested source calls do not assume the certificate's final
lexical cursor. Root composition specializes it to the cursor provided by DAG
execution. No source evaluation or call outcome is manufactured here. -/
abbrev FunctionEvaluation (_profile : ExactProfile bound)
    (node : RuntimeCallable (tables bound.artifact.document.reversed.reverse)
      files root frameModule framePath)
    (values : List Value) (after : LocalContext) (outcome : RuntimeBodyOutcome)
    (events : List RuntimeSourceEvent) : Prop :=
  RuntimeStatementsEvaluation (bound.checked.shape.nodes.map (·.source))
    node.source.context.members node.source.context.module node.source.context.path
    node.source.context.formals node.source.result
    ⟨[],0,1,node.source.context.formals.length⟩
    (formalSourceLocals node.source.parameters (fun index => values[index]?))
    node.source.parsed.statements after outcome events


private theorem mapped_nodup_unique (xs : List α) (f : α → β)
    (unique : (xs.map f).Nodup) (a b : α) (ha : a ∈ xs) (hb : b ∈ xs)
    (same : f a = f b) : a = b := by
  induction xs with
  | nil => cases ha
  | cons x xs ih =>
    simp only [List.map_cons, List.nodup_cons] at unique
    rcases List.mem_cons.mp ha with ax | laterA
    · subst a
      rcases List.mem_cons.mp hb with bx | laterB
      · exact bx.symm
      · exact False.elim (unique.1 (same.symm ▸ List.mem_map_of_mem laterB))
    · rcases List.mem_cons.mp hb with bx | laterB
      · subst b
        exact False.elim (unique.1 (same ▸ List.mem_map_of_mem laterA))
      · exact ih unique.2 laterA laterB

theorem ExactProfile.node_eq_role (profile : ExactProfile bound) {role : Role}
    (node : RuntimeCallable (tables bound.artifact.document.reversed.reverse)
      files root frameModule framePath)
    (member : node ∈ bound.checked.shape.nodes) (named : node.name = role.name) :
    node = profile.nodeFor role := by
  apply mapped_nodup_unique _ (·.name) profile.uniqueNames node (profile.nodeFor role)
    member (profile.roles role).member
  exact named.trans (profile.roles role).named.symm

theorem ExactProfile.node_body (profile : ExactProfile bound) {role : Role}
    (node : RuntimeCallable (tables bound.artifact.document.reversed.reverse)
      files root frameModule framePath)
    (member : node ∈ bound.checked.shape.nodes) (named : node.name = role.name) :
    node.source.parsed.statements = role.shape.body := by
  rw [profile.node_eq_role node member named]
  exact (profile.roles role).body

theorem ExactProfile.node_parameters (profile : ExactProfile bound) {role : Role}
    (node : RuntimeCallable (tables bound.artifact.document.reversed.reverse)
      files root frameModule framePath)
    (member : node ∈ bound.checked.shape.nodes) (named : node.name = role.name) :
    node.source.parameters = role.parameterKinds profile.operations.nominal profile.rejections.nominal := by
  rw [profile.node_eq_role node member named]
  exact (profile.roles role).parameters

theorem ExactProfile.node_result (profile : ExactProfile bound) {role : Role}
    (node : RuntimeCallable (tables bound.artifact.document.reversed.reverse)
      files root frameModule framePath)
    (member : node ∈ bound.checked.shape.nodes) (named : node.name = role.name) :
    node.source.result = role.resultKind := by
  rw [profile.node_eq_role node member named]
  exact (profile.roles role).resultKind


def operationSourceName : FramePolicy.Operation → ByteArray
  | .none => bytes "none"
  | .initializeFree => bytes "initialize_free"
  | .initializeKernel => bytes "initialize_kernel"
  | .allocate => bytes "allocate"
  | .release => bytes "release"

def rejectionSourceName : FramePolicy.Rejection → ByteArray
  | .operation => bytes "operation" | .record => bytes "record"
  | .owner => bytes "owner" | .link => bytes "link"
  | .notFree => bytes "not_free" | .notAllocated => bytes "not_allocated"
  | .kernel => bytes "kernel" | .retired => bytes "retired"
  | .wrongOwner => bytes "wrong_owner" | .stale => bytes "stale"

theorem ExactProfile.operation_case (profile : ExactProfile bound) (op : FramePolicy.Operation) :
    EnumCaseAt profile.operations [operationName,operationSourceName op] op.ordinal := by
  cases op <;> apply EnumCaseAt.unqualified <;> rw [profile.operationsCases] <;> rfl

theorem ExactProfile.rejection_case (profile : ExactProfile bound) (reason : FramePolicy.Rejection) :
    EnumCaseAt profile.rejections [rejectionName,rejectionSourceName reason] reason.ordinal := by
  cases reason <;> apply EnumCaseAt.unqualified <;> rw [profile.rejectionsCases] <;> rfl

theorem ExactProfile.rejection_none (profile : ExactProfile bound) :
    EnumCaseAt profile.rejections [rejectionName,bytes "none"] 0 := by
  apply EnumCaseAt.unqualified
  rw [profile.rejectionsCases]
  rfl

theorem ExactProfile.operation_cardinality (profile : ExactProfile bound) :
    profile.operations.nominal.cases = 5 := by
  change profile.operations.declaration.cases.length = 5
  rw [profile.operationsCases]
  rfl

theorem ExactProfile.rejection_cardinality (profile : ExactProfile bound) :
    profile.rejections.nominal.cases = 11 := by
  change profile.rejections.declaration.cases.length = 11
  rw [profile.rejectionsCases]
  rfl

theorem ExactProfile.operation_ready (profile : ExactProfile bound) (op : FramePolicy.Operation) :
    readRuntime (.nominal profile.operations.nominal) (some (operationValue profile op)) =
      .value (operationValue profile op) := by
  have bounded := (profile.operation_case op).bounded
  simp [readRuntime,operationValue,bounded]

theorem ExactProfile.operation_complete (profile : ExactProfile bound)
    (typed : readRuntime (.nominal profile.operations.nominal) (some value) = .value value) :
    ∃ op, operationValue profile op = value := by
  cases value with
  | nominal name ordinal =>
    simp only [readRuntime] at typed
    split at typed
    · rename_i ready
      obtain ⟨rfl,bounded⟩ := ready
      rw [profile.operation_cardinality] at bounded
      have cases : ordinal = 0 ∨ ordinal = 1 ∨ ordinal = 2 ∨ ordinal = 3 ∨ ordinal = 4 := by omega
      rcases cases with h | h | h | h | h <;> subst ordinal
      · exact ⟨.none,rfl⟩
      · exact ⟨.initializeFree,rfl⟩
      · exact ⟨.initializeKernel,rfl⟩
      · exact ⟨.allocate,rfl⟩
      · exact ⟨.release,rfl⟩
    · cases typed
  | word value => cases typed
  | boolean value => cases typed
  | signedCount4 => cases typed
  | signedCount12 => cases typed
  | signedCount32 => cases typed

theorem ExactProfile.arguments_ready (profile : ExactProfile bound) {operation : FramePolicy.Operation}
    (bounded : FramePolicy.InputsBounded record owner generation link) :
    RuntimeReadyArguments bound.checked.shape.rootNode.source.parameters
      (arguments profile operation record owner generation link) := by
  rw [profile.rootParameters]
  refine .cons (profile.operation_ready operation) (.cons ?_ (.cons ?_ (.cons ?_ (.cons ?_ .nil))))
  · simp [readRuntime,readScalar,wordLimit] at bounded ⊢
    exact bounded.1
  · simp [readRuntime,readScalar,wordLimit] at bounded ⊢
    exact bounded.2.1
  · simp [readRuntime,readScalar,wordLimit] at bounded ⊢
    exact bounded.2.2.1
  · simp [readRuntime,readScalar,wordLimit] at bounded ⊢
    exact bounded.2.2.2

end Aurora.SourceBinding.FramePolicyAttachment
