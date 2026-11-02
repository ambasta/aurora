import SourceBinding.RuntimeUniformBranch
namespace Aurora.SourceBinding

/-- Every supported raw statement is executed, not summarized. Initialization,
    mutability and lexical-state preservation are derived from the current
    source invariant; calls delegate the actual checked callable bodies. -/
theorem RuntimeStatementCode.simulates_uniform
    {nodes direct : List (RuntimeCallable t files root module path)}
    (code : RuntimeStatementCode program caller direct members formals result before raw after declaredItems start stop)
    (included : ∀ callable ∈ direct, callable ∈ nodes)
    (callees : ∀ callable ∈ direct, RuntimeCalleeExecutes program nodes callable World ExternalFault) :
    RuntimeUniformStatement program caller nodes members formals result before raw after start stop World ExternalFault := by
  induction code using RuntimeStatementCode.rec
      (motive_2 := fun before raws after items start stop _ =>
        RuntimeUniformStatements program caller nodes members formals result before raws after start stop World ExternalFault) with
  | declare scope valid expression store =>
    intro source ancestors stateAt
    obtain ⟨outcome,se,me,evaluated,trace,run⟩ := expression.evaluates_uniform included callees source stateAt.2.2.2.1
    cases outcome with
    | trap fault => exact ⟨_,se,me,.declarationFault scope evaluated,trace,trivial,
        fun base saved world external acc => runtime_body_expression_fault (run (runtimeExpressionBase base source) (fun _ => rfl) saved world external acc base.stack)⟩
    | value value =>
      obtain ⟨next,accepted,nextAt,values⟩ := stateAt.initialize evaluated.outcome_typed
      exact ⟨_,se,me,.declarationValue scope evaluated accepted,trace,nextAt,
        fun base saved world external acc => runtime_body_store (run (runtimeExpressionBase base source) (fun _ => rfl) saved world external acc base.stack) store evaluated.outcome_typed values⟩
  | assign scope member named mutable valid expression store =>
    intro source ancestors stateAt
    obtain ⟨outcome,se,me,evaluated,trace,run⟩ := expression.evaluates_uniform included callees source stateAt.2.2.2.1
    cases outcome with
    | trap fault => exact ⟨_,se,me,.assignmentFault member named mutable evaluated,trace,trivial,
        fun base saved world external acc => runtime_body_expression_fault (run (runtimeExpressionBase base source) (fun _ => rfl) saved world external acc base.stack)⟩
    | value value =>
      have clear := (valid.names.2.2.2.1 _ member).2.1
      have binding : RuntimeVariableBinding _ _ _ := .localValue member named (named ▸ clear)
      obtain ⟨next,accepted,nextAt,values⟩ := stateAt.assign binding mutable evaluated.outcome_typed
      exact ⟨_,se,me,.assignmentValue member named mutable evaluated accepted,trace,nextAt,
        fun base saved world external acc => runtime_body_store (run (runtimeExpressionBase base source) (fun _ => rfl) saved world external acc base.stack) store evaluated.outcome_typed values⟩
  | returned scope valid expression returning =>
    intro source ancestors stateAt
    obtain ⟨outcome,se,me,evaluated,trace,run⟩ := expression.evaluates_uniform included callees source stateAt.2.2.2.1
    cases outcome with
    | trap fault => exact ⟨_,se,me,.returnFault evaluated,trace,trivial,
        fun base saved world external acc => runtime_body_expression_fault (run (runtimeExpressionBase base source) (fun _ => rfl) saved world external acc base.stack)⟩
    | value value => exact ⟨_,se,me,.returnValue evaluated,trace,trivial,
        fun base saved world external acc => runtime_body_return (run (runtimeExpressionBase base source) (fun _ => rfl) saved world external acc base.stack) returning⟩
  | branchLinear scope valid condition branch body nonempty labels ih =>
    exact runtime_branch_uniform body.scope_proof valid condition branch labels ih
      (fun base saved world external source acc next events run => run.labels labels) included callees
  | branchJoined scope valid condition branch body jump lower upper labels ih =>
    exact runtime_branch_uniform body.scope_proof valid condition branch labels ih
      (fun base saved world external source acc next events run => run.jump_labels jump (labels.suffix lower (Nat.le_of_lt upper))) included callees
  | nil =>
    intro source ancestors stateAt
    exact ⟨.continued source,[],[],.nil,.nil,stateAt,fun base saved world external acc => ⟨_,.reflexive,acc,rfl⟩⟩
  | cons first rest firstIH restIH =>
    intro source ancestors stateAt
    obtain ⟨firstOut,se,me,firstEval,firstTrace,firstAt,firstRun⟩ := firstIH source ancestors stateAt
    cases firstOut with
    | returned value final => exact ⟨_,se,me,.returned firstEval rest.scope_proof,firstTrace,trivial,
        fun base saved world external acc => (firstRun base saved world external acc).return_stop⟩
    | trapped fault final => exact ⟨_,se,me,.trapped firstEval rest.scope_proof,firstTrace,trivial,
        fun base saved world external acc => (firstRun base saved world external acc).fault_stop⟩
    | continued next =>
      obtain ⟨restOut,sr,mr,restEval,restTrace,restAt,restRun⟩ := restIH next ancestors firstAt
      exact ⟨_,se++sr,me++mr,.next firstEval restEval,firstTrace.append restTrace,restAt,
        fun base saved world external acc => (firstRun base saved world external acc).then_run (restRun base saved world external)⟩

theorem RuntimeStatementsCode.simulates_uniform
    {nodes direct : List (RuntimeCallable t files root module path)}
    (code : RuntimeStatementsCode program caller direct members formals result before raws after declaredItems start stop)
    (included : ∀ callable ∈ direct, callable ∈ nodes)
    (callees : ∀ callable ∈ direct, RuntimeCalleeExecutes program nodes callable World ExternalFault) :
    RuntimeUniformStatements program caller nodes members formals result before raws after start stop World ExternalFault := by
  induction raws generalizing before after declaredItems start stop with
  | nil =>
    cases code
    intro source ancestors stateAt
    exact ⟨.continued source,[],[],.nil,.nil,stateAt,fun base saved world external acc => ⟨_,.reflexive,acc,rfl⟩⟩
  | cons first rest ih =>
    cases code with
    | cons head tail =>
      intro source ancestors stateAt
      obtain ⟨firstOut,se,me,firstEval,firstTrace,firstAt,firstRun⟩ :=
        head.simulates_uniform included callees source ancestors stateAt
      cases firstOut with
      | returned value final => exact ⟨_,se,me,.returned firstEval tail.scope_proof,firstTrace,trivial,
          fun base saved world external acc => (firstRun base saved world external acc).return_stop⟩
      | trapped fault final => exact ⟨_,se,me,.trapped firstEval tail.scope_proof,firstTrace,trivial,
          fun base saved world external acc => (firstRun base saved world external acc).fault_stop⟩
      | continued next =>
        obtain ⟨restOut,sr,mr,restEval,restTrace,restAt,restRun⟩ := ih tail next ancestors firstAt
        exact ⟨_,se++sr,me++mr,.next firstEval restEval,firstTrace.append restTrace,restAt,
          fun base saved world external acc => (firstRun base saved world external acc).then_run (restRun base saved world external)⟩

end Aurora.SourceBinding
