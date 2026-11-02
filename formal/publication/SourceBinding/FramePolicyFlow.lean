import SourceBinding.RuntimeEvaluationResults
import SourceBinding.RuntimeNodeExecution
namespace Aurora.SourceBinding.FramePolicyAttachment

/-- A successful initializer is evaluated before the real guarded declaration.
    Any actual derivation then continues from that operation's resulting state. -/
theorem declaration_tail {declaration : Formal}
    (initializer : RuntimeExpressionResult functions
      (runtimeStatementContext members module path formals before) state raw kind (.value value))
    (evaluated : RuntimeStatementsEvaluation functions members module path formals result
      before state (.localDecl declaration raw :: rest) after outcome events) :
    ∃ binding middle next restEvents,
      ScopedStatement members module path formals before (.localDecl declaration raw) middle [binding] ∧
      binding.kind = kind ∧
      state.initialize binding.slot binding.runtimeDeclaration value = some next ∧
      RuntimeStatementsEvaluation functions members module path formals result middle next rest after outcome restEvents := by
  rcases evaluated.cons_cases with normal | returned | trapped
  · obtain ⟨middle,next,firstEvents,restEvents,first,tail,eventEq⟩ := normal
    cases first with
    | declarationValue scopeProof expression accepted =>
      obtain ⟨kindEq,valueEq⟩ := initializer _ _ _ expression
      cases valueEq
      exact ⟨_,_,_,_,scopeProof,kindEq,accepted,tail⟩
  · obtain ⟨middle,value,finished,items,first,tail,outcomeEq⟩ := returned
    cases first
  · obtain ⟨middle,fault,finished,items,first,tail,outcomeEq⟩ := trapped
    cases first with
    | declarationFault scopeProof expression =>
      have impossible := (initializer _ _ _ expression).2
      cases impossible

/-- An actually false condition evaluates only the tail. Scope reservation is
    retained as its real source operation; no skipped body is initialized. -/
theorem false_branch_tail
    (conditionResult : RuntimeExpressionResult functions
      (runtimeStatementContext members module path formals before) state condition
      (.scalar .boolean) (.value (.boolean false)))
    (evaluated : RuntimeStatementsEvaluation functions members module path formals result
      before state (.ifThen condition body :: rest) after outcome events) :
    ∃ child items next restEvents,
      ScopedStatements members module path formals (enterLocalScope before) body child items ∧
      state.reserveScopes child.nextScope = some next ∧
      RuntimeStatementsEvaluation functions members module path formals result
        (leaveLocalScope before child) next rest after outcome restEvents := by
  rcases evaluated.cons_cases with normal | returned | trapped
  · obtain ⟨middle,next,firstEvents,restEvents,first,tail,eventEq⟩ := normal
    cases first with
    | branchFalse scopeProof conditionEval reserve => exact ⟨_,_,_,_,scopeProof,reserve,tail⟩
    | branchTrueContinue scopeProof conditionEval enter bodyEval reserve =>
      have impossible := (conditionResult _ _ _ conditionEval).2
      cases impossible
  · obtain ⟨middle,value,finished,items,first,tail,outcomeEq⟩ := returned
    cases first with
    | branchTrueReturn scopeProof conditionEval enter bodyEval =>
      have impossible := (conditionResult _ _ _ conditionEval).2
      cases impossible
  · obtain ⟨middle,fault,finished,items,first,tail,outcomeEq⟩ := trapped
    cases first with
    | branchFault scopeProof conditionEval =>
      have impossible := (conditionResult _ _ _ conditionEval).2
      cases impossible
    | branchTrueFault scopeProof conditionEval enter bodyEval =>
      have impossible := (conditionResult _ _ _ conditionEval).2
      cases impossible

/-- A true, structurally terminal branch evaluates its actual entered body and
    never the suffix. Its terminal source state is not cleaned up. -/
theorem true_branch_body
    (conditionResult : RuntimeExpressionResult functions
      (runtimeStatementContext members module path formals before) state condition
      (.scalar .boolean) (.value (.boolean true)))
    (terminal : RuntimeNoFallthrough body)
    (evaluated : RuntimeStatementsEvaluation functions members module path formals result
      before state (.ifThen condition body :: rest) after outcome events) :
    ∃ child entered bodyEvents,
      state.enterAt before.nextScope = some entered ∧
      RuntimeStatementsEvaluation functions members module path formals result
        (enterLocalScope before) entered body child outcome bodyEvents := by
  rcases evaluated.cons_cases with normal | returned | trapped
  · obtain ⟨middle,next,firstEvents,restEvents,first,tail,eventEq⟩ := normal
    cases first with
    | branchFalse scopeProof conditionEval reserve =>
      have impossible := (conditionResult _ _ _ conditionEval).2
      cases impossible
    | branchTrueContinue scopeProof conditionEval enter bodyEval reserve =>
      exact False.elim (terminal.not_continued_general bodyEval)
  · obtain ⟨middle,value,finished,items,first,tail,outcomeEq⟩ := returned
    cases first with
    | branchTrueReturn scopeProof conditionEval enter bodyEval =>
      subst outcome
      exact ⟨_,_,_,enter,bodyEval⟩
  · obtain ⟨middle,fault,finished,items,first,tail,outcomeEq⟩ := trapped
    cases first with
    | branchFault scopeProof conditionEval =>
      have impossible := (conditionResult _ _ _ conditionEval).2
      cases impossible
    | branchTrueFault scopeProof conditionEval enter bodyEval =>
      subst outcome
      exact ⟨_,_,_,enter,bodyEval⟩

end Aurora.SourceBinding.FramePolicyAttachment
