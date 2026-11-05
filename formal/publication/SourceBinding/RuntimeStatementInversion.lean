import SourceBinding.RuntimeEvaluation
namespace Aurora.SourceBinding
open Aurora.Publication

private def StatementCases (functions : List RuntimeSourceFunction)
    (members : List Declaration) (module path : Name) (formals : List Formal) (result : RuntimeType)
    (before : LocalContext) (state : RuntimeLocals) (raw : SourceStatement) (after : LocalContext)
    (outcome : RuntimeBodyOutcome) (events : List RuntimeSourceEvent) : Prop :=
  match raw with
  | .localDecl declaration value =>
    ∃ binding, ScopedStatement members module path formals before (.localDecl declaration value) after [binding] ∧
      ((∃ fault, RuntimeEvaluation functions (runtimeStatementContext members module path formals before)
          state value binding.kind (.trap fault) events ∧ outcome = .trapped fault state) ∨
       (∃ result next, RuntimeEvaluation functions (runtimeStatementContext members module path formals before)
          state value binding.kind (.value result) events ∧
          state.initialize binding.slot binding.runtimeDeclaration result = some next ∧ outcome = .continued next))
  | .assign name value =>
    after = before ∧ ∃ binding ∈ before.visible, binding.name = name ∧ binding.mutable = true ∧
      ((∃ fault, RuntimeEvaluation functions (runtimeStatementContext members module path formals before)
          state value binding.kind (.trap fault) events ∧ outcome = .trapped fault state) ∨
       (∃ result next, RuntimeEvaluation functions (runtimeStatementContext members module path formals before)
          state value binding.kind (.value result) events ∧ state.assign binding.slot result = some next ∧ outcome = .continued next))
  | .returnValue value =>
    after = before ∧
      ((∃ fault, RuntimeEvaluation functions (runtimeStatementContext members module path formals before)
          state value result (.trap fault) events ∧ outcome = .trapped fault state) ∨
       (∃ returned, RuntimeEvaluation functions (runtimeStatementContext members module path formals before)
          state value result (.value returned) events ∧ outcome = .returned returned state))
  | .ifThen condition body =>
    ∃ child items, ScopedStatements members module path formals (enterLocalScope before) body child items ∧
      after = leaveLocalScope before child ∧
      ((∃ fault, RuntimeEvaluation functions (runtimeStatementContext members module path formals before)
          state condition (.scalar .boolean) (.trap fault) events ∧ outcome = .trapped fault state) ∨
       (∃ next, RuntimeEvaluation functions (runtimeStatementContext members module path formals before)
          state condition (.scalar .boolean) (.value (.boolean false)) events ∧
          state.reserveScopes child.nextScope = some next ∧ outcome = .continued next) ∨
       (∃ entered finished next conditionEvents bodyEvents,
          RuntimeEvaluation functions (runtimeStatementContext members module path formals before)
            state condition (.scalar .boolean) (.value (.boolean true)) conditionEvents ∧
          state.enterAt before.nextScope = some entered ∧
          RuntimeStatementsEvaluation functions members module path formals result (enterLocalScope before) entered
            body child (.continued finished) bodyEvents ∧ finished.leave.reserveScopes child.nextScope = some next ∧
          outcome = .continued next ∧ events = conditionEvents ++ bodyEvents) ∨
       (∃ entered value finished conditionEvents bodyEvents,
          RuntimeEvaluation functions (runtimeStatementContext members module path formals before)
            state condition (.scalar .boolean) (.value (.boolean true)) conditionEvents ∧
          state.enterAt before.nextScope = some entered ∧
          RuntimeStatementsEvaluation functions members module path formals result (enterLocalScope before) entered
            body child (.returned value finished) bodyEvents ∧
          outcome = .returned value finished ∧ events = conditionEvents ++ bodyEvents) ∨
       (∃ entered fault finished conditionEvents bodyEvents,
          RuntimeEvaluation functions (runtimeStatementContext members module path formals before)
            state condition (.scalar .boolean) (.value (.boolean true)) conditionEvents ∧
          state.enterAt before.nextScope = some entered ∧
          RuntimeStatementsEvaluation functions members module path formals result (enterLocalScope before) entered
            body child (.trapped fault finished) bodyEvents ∧
          outcome = .trapped fault finished ∧ events = conditionEvents ++ bodyEvents))
  | _ => True

private theorem statementAlgebra (functions : List RuntimeSourceFunction) :
    PureEffectAlgebra functions (RuntimeEvaluation functions) (RuntimeArgumentEvaluation functions)
      (fun members module path formals result before state raw after outcome events =>
        RuntimeStatementEvaluation functions members module path formals result before state raw after outcome events ∧
        StatementCases functions members module path formals result before state raw after outcome events)
      (RuntimeStatementsEvaluation functions) where
  expression_word := (pureRuntimeAlgebra functions).expression_word
  expression_boolean := (pureRuntimeAlgebra functions).expression_boolean
  expression_readVariable := (pureRuntimeAlgebra functions).expression_readVariable
  expression_enumValue := (pureRuntimeAlgebra functions).expression_enumValue
  expression_not := (pureRuntimeAlgebra functions).expression_not
  expression_wordBinaryFault := (pureRuntimeAlgebra functions).expression_wordBinaryFault
  expression_wordBinary := (pureRuntimeAlgebra functions).expression_wordBinary
  expression_enumCompareFault := (pureRuntimeAlgebra functions).expression_enumCompareFault
  expression_enumCompare := (pureRuntimeAlgebra functions).expression_enumCompare
  expression_shiftLeft := (pureRuntimeAlgebra functions).expression_shiftLeft
  expression_shiftRight := (pureRuntimeAlgebra functions).expression_shiftRight
  expression_andFault := (pureRuntimeAlgebra functions).expression_andFault
  expression_andStop := (pureRuntimeAlgebra functions).expression_andStop
  expression_andContinue := (pureRuntimeAlgebra functions).expression_andContinue
  expression_orFault := (pureRuntimeAlgebra functions).expression_orFault
  expression_orStop := (pureRuntimeAlgebra functions).expression_orStop
  expression_orContinue := (pureRuntimeAlgebra functions).expression_orContinue
  expression_callArgumentsFault := (pureRuntimeAlgebra functions).expression_callArgumentsFault
  expression_callValue := (pureRuntimeAlgebra functions).expression_callValue
  expression_callFault := (pureRuntimeAlgebra functions).expression_callFault
  arguments_nil := (pureRuntimeAlgebra functions).arguments_nil
  arguments_fault := (pureRuntimeAlgebra functions).arguments_fault
  arguments_cons := (pureRuntimeAlgebra functions).arguments_cons
  statement_declarationFault := by
    intro members module path formals before raw after binding state fault events result declaration scope expression
    exact ⟨(pureRuntimeAlgebra functions).statement_declarationFault scope expression,
      binding,scope,Or.inl ⟨fault,expression,rfl⟩⟩
  statement_declarationValue := by
    intro members module path formals before raw after binding state value events next result declaration scope expression accepted
    exact ⟨(pureRuntimeAlgebra functions).statement_declarationValue scope expression accepted,
      binding,scope,Or.inr ⟨value,next,expression,accepted,rfl⟩⟩
  statement_assignmentFault := by
    intro binding name members module path formals before state raw fault events result present named mutable expression
    exact ⟨(pureRuntimeAlgebra functions).statement_assignmentFault present named mutable expression,
      rfl,binding,present,named,mutable,Or.inl ⟨fault,expression,rfl⟩⟩
  statement_assignmentValue := by
    intro binding name members module path formals before state raw value events next result present named mutable expression accepted
    exact ⟨(pureRuntimeAlgebra functions).statement_assignmentValue present named mutable expression accepted,
      rfl,binding,present,named,mutable,Or.inr ⟨value,next,expression,accepted,rfl⟩⟩
  statement_returnFault := by
    intro members module path formals before state raw result fault events expression
    exact ⟨(pureRuntimeAlgebra functions).statement_returnFault expression,rfl,Or.inl ⟨fault,expression,rfl⟩⟩
  statement_returnValue := by
    intro members module path formals before state raw result value events expression
    exact ⟨(pureRuntimeAlgebra functions).statement_returnValue expression,rfl,Or.inr ⟨value,expression,rfl⟩⟩
  statement_branchFault := by
    intro members module path formals before body child items state condition fault events result scope expression
    exact ⟨(pureRuntimeAlgebra functions).statement_branchFault scope expression,
      child,items,scope,rfl,Or.inl ⟨fault,expression,rfl⟩⟩
  statement_branchFalse := by
    intro members module path formals before body child items state condition events next result scope expression reserve
    exact ⟨(pureRuntimeAlgebra functions).statement_branchFalse scope expression reserve,
      child,items,scope,rfl,Or.inr (Or.inl ⟨next,expression,reserve,rfl⟩)⟩
  statement_branchTrueContinue := by
    intro members module path formals before body child items state condition ce entered result finished be next scope expression enter evaluated reserve
    exact ⟨(pureRuntimeAlgebra functions).statement_branchTrueContinue scope expression enter evaluated reserve,
      child,items,scope,rfl,Or.inr (Or.inr (Or.inl ⟨entered,finished,next,ce,be,expression,enter,evaluated,reserve,rfl,rfl⟩))⟩
  statement_branchTrueReturn := by
    intro members module path formals before body child items state condition ce entered result value finished be scope expression enter evaluated
    exact ⟨(pureRuntimeAlgebra functions).statement_branchTrueReturn scope expression enter evaluated,
      child,items,scope,rfl,Or.inr (Or.inr (Or.inr (Or.inl ⟨entered,value,finished,ce,be,expression,enter,evaluated,rfl,rfl⟩)))⟩
  statement_branchTrueFault := by
    intro members module path formals before body child items state condition ce entered result fault finished be scope expression enter evaluated
    exact ⟨(pureRuntimeAlgebra functions).statement_branchTrueFault scope expression enter evaluated,
      child,items,scope,rfl,Or.inr (Or.inr (Or.inr (Or.inr ⟨entered,fault,finished,ce,be,expression,enter,evaluated,rfl,rfl⟩)))⟩
  statements_nil := (pureRuntimeAlgebra functions).statements_nil
  statements_next := by
    intro members module path formals result before state first middle next fe rest after outcome re firstEval tail
    exact (pureRuntimeAlgebra functions).statements_next firstEval.1 tail
  statements_returned := by
    intro members module path formals result before state first middle value final events rest after items firstEval scope
    exact (pureRuntimeAlgebra functions).statements_returned firstEval.1 scope
  statements_trapped := by
    intro members module path formals result before state first middle fault final events rest after items firstEval scope
    exact (pureRuntimeAlgebra functions).statements_trapped firstEval.1 scope

/-- One-step inversion of the SAME pure specialization of effectful source evaluation. -/
theorem PureRuntimeStatementEvaluation.declaration_cases {declaration : Formal}
    (evaluated : RuntimeStatementEvaluation functions members module path formals result
      before state (.localDecl declaration value) after outcome events) :
    ∃ binding, ScopedStatement members module path formals before (.localDecl declaration value) after [binding] ∧
      ((∃ fault, RuntimeEvaluation functions (runtimeStatementContext members module path formals before)
          state value binding.kind (.trap fault) events ∧ outcome = .trapped fault state) ∨
       (∃ result next, RuntimeEvaluation functions (runtimeStatementContext members module path formals before)
          state value binding.kind (.value result) events ∧
          state.initialize binding.slot binding.runtimeDeclaration result = some next ∧ outcome = .continued next)) :=
  (evaluated.induct (statementAlgebra functions)).2

/-- One-step inversion of the SAME pure specialization of effectful source evaluation. -/
theorem PureRuntimeStatementEvaluation.assignment_cases
    (evaluated : RuntimeStatementEvaluation functions members module path formals result
      before state (.assign name value) after outcome events) :
    after = before ∧ ∃ binding ∈ before.visible, binding.name = name ∧ binding.mutable = true ∧
      ((∃ fault, RuntimeEvaluation functions (runtimeStatementContext members module path formals before)
          state value binding.kind (.trap fault) events ∧ outcome = .trapped fault state) ∨
       (∃ result next, RuntimeEvaluation functions (runtimeStatementContext members module path formals before)
          state value binding.kind (.value result) events ∧ state.assign binding.slot result = some next ∧ outcome = .continued next)) :=
  (evaluated.induct (statementAlgebra functions)).2

/-- One-step inversion of the SAME pure specialization of effectful source evaluation. -/
theorem PureRuntimeStatementEvaluation.return_cases
    (evaluated : RuntimeStatementEvaluation functions members module path formals result
      before state (.returnValue value) after outcome events) :
    after = before ∧
      ((∃ fault, RuntimeEvaluation functions (runtimeStatementContext members module path formals before)
          state value result (.trap fault) events ∧ outcome = .trapped fault state) ∨
       (∃ returned, RuntimeEvaluation functions (runtimeStatementContext members module path formals before)
          state value result (.value returned) events ∧ outcome = .returned returned state)) :=
  (evaluated.induct (statementAlgebra functions)).2

/-- One-step inversion of the SAME pure specialization of effectful source evaluation. -/
theorem PureRuntimeStatementEvaluation.branch_cases
    (evaluated : RuntimeStatementEvaluation functions members module path formals result
      before state (.ifThen condition body) after outcome events) :
    ∃ child items, ScopedStatements members module path formals (enterLocalScope before) body child items ∧
      after = leaveLocalScope before child ∧
      ((∃ fault, RuntimeEvaluation functions (runtimeStatementContext members module path formals before)
          state condition (.scalar .boolean) (.trap fault) events ∧ outcome = .trapped fault state) ∨
       (∃ next, RuntimeEvaluation functions (runtimeStatementContext members module path formals before)
          state condition (.scalar .boolean) (.value (.boolean false)) events ∧
          state.reserveScopes child.nextScope = some next ∧ outcome = .continued next) ∨
       (∃ entered finished next conditionEvents bodyEvents,
          RuntimeEvaluation functions (runtimeStatementContext members module path formals before)
            state condition (.scalar .boolean) (.value (.boolean true)) conditionEvents ∧
          state.enterAt before.nextScope = some entered ∧
          RuntimeStatementsEvaluation functions members module path formals result (enterLocalScope before) entered
            body child (.continued finished) bodyEvents ∧ finished.leave.reserveScopes child.nextScope = some next ∧
          outcome = .continued next ∧ events = conditionEvents ++ bodyEvents) ∨
       (∃ entered value finished conditionEvents bodyEvents,
          RuntimeEvaluation functions (runtimeStatementContext members module path formals before)
            state condition (.scalar .boolean) (.value (.boolean true)) conditionEvents ∧
          state.enterAt before.nextScope = some entered ∧
          RuntimeStatementsEvaluation functions members module path formals result (enterLocalScope before) entered
            body child (.returned value finished) bodyEvents ∧
          outcome = .returned value finished ∧ events = conditionEvents ++ bodyEvents) ∨
       (∃ entered fault finished conditionEvents bodyEvents,
          RuntimeEvaluation functions (runtimeStatementContext members module path formals before)
            state condition (.scalar .boolean) (.value (.boolean true)) conditionEvents ∧
          state.enterAt before.nextScope = some entered ∧
          RuntimeStatementsEvaluation functions members module path formals result (enterLocalScope before) entered
            body child (.trapped fault finished) bodyEvents ∧
          outcome = .trapped fault finished ∧ events = conditionEvents ++ bodyEvents)) :=
  (evaluated.induct (statementAlgebra functions)).2

end Aurora.SourceBinding
