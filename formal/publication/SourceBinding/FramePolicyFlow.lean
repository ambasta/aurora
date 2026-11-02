import SourceBinding.RuntimeEvaluationResults
import SourceBinding.RuntimeNodeExecution
import SourceBinding.RuntimeStatementInversion
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
  have invert {middle final firstEvents}
      (first : RuntimeStatementEvaluation functions members module path formals result
        before state (.localDecl declaration raw) middle final firstEvents) :
      ∃ binding next, ScopedStatement members module path formals before (.localDecl declaration raw) middle [binding] ∧
        binding.kind = kind ∧ state.initialize binding.slot binding.runtimeDeclaration value = some next ∧
        final = .continued next := by
    obtain ⟨binding,scope,alternatives⟩ := first.declaration_cases
    rcases alternatives with faultCase | valueCase
    · obtain ⟨fault,expression,equal⟩ := faultCase
      have impossible := (initializer _ _ _ expression).2
      cases impossible
    · obtain ⟨actual,next,expression,accepted,equal⟩ := valueCase
      obtain ⟨kindEq,valueEq⟩ := initializer _ _ _ expression
      cases valueEq
      exact ⟨binding,next,scope,kindEq,accepted,equal⟩
  rcases evaluated.cons_cases with normal | returned | trapped
  · obtain ⟨middle,next,firstEvents,restEvents,first,tail,eventEq⟩ := normal
    obtain ⟨binding,initialized,scope,kindEq,accepted,equal⟩ := invert first
    cases equal
    exact ⟨_,_,_,_,scope,kindEq,accepted,tail⟩
  · obtain ⟨middle,value,finished,items,first,tail,outcomeEq⟩ := returned
    obtain ⟨binding,next,scope,kindEq,accepted,equal⟩ := invert first
    cases equal
  · obtain ⟨middle,fault,finished,items,first,tail,outcomeEq⟩ := trapped
    obtain ⟨binding,next,scope,kindEq,accepted,equal⟩ := invert first
    cases equal

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
  have invert {middle final firstEvents}
      (first : RuntimeStatementEvaluation functions members module path formals result
        before state (.ifThen condition body) middle final firstEvents) :
      ∃ child items next, ScopedStatements members module path formals (enterLocalScope before) body child items ∧
        state.reserveScopes child.nextScope = some next ∧
        middle = leaveLocalScope before child ∧ final = .continued next := by
    obtain ⟨child,items,scope,cursor,alternatives⟩ := first.branch_cases
    rcases alternatives with faultCase | falseCase | continuedCase | returnedCase | trappedCase
    · obtain ⟨fault,expression,equal⟩ := faultCase
      have impossible := (conditionResult _ _ _ expression).2
      cases impossible
    · obtain ⟨next,expression,reserve,equal⟩ := falseCase
      exact ⟨child,items,next,scope,reserve,cursor,equal⟩
    · obtain ⟨entered,finished,next,ce,be,expression,enter,bodyEval,reserve,equal,trace⟩ := continuedCase
      have impossible := (conditionResult _ _ _ expression).2
      cases impossible
    · obtain ⟨entered,value,finished,ce,be,expression,enter,bodyEval,equal,trace⟩ := returnedCase
      have impossible := (conditionResult _ _ _ expression).2
      cases impossible
    · obtain ⟨entered,fault,finished,ce,be,expression,enter,bodyEval,equal,trace⟩ := trappedCase
      have impossible := (conditionResult _ _ _ expression).2
      cases impossible
  rcases evaluated.cons_cases with normal | returned | trapped
  · obtain ⟨middle,next,firstEvents,restEvents,first,tail,eventEq⟩ := normal
    obtain ⟨child,items,actual,scope,reserve,cursor,equal⟩ := invert first
    cases equal
    rw [cursor] at tail
    exact ⟨child,items,_,restEvents,scope,reserve,tail⟩
  · obtain ⟨middle,value,finished,items,first,tail,outcomeEq⟩ := returned
    obtain ⟨child,items,actual,scope,reserve,cursor,equal⟩ := invert first
    cases equal
  · obtain ⟨middle,fault,finished,items,first,tail,outcomeEq⟩ := trapped
    obtain ⟨child,items,actual,scope,reserve,cursor,equal⟩ := invert first
    cases equal

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
  have invert {middle final firstEvents}
      (first : RuntimeStatementEvaluation functions members module path formals result
        before state (.ifThen condition body) middle final firstEvents) :
      ∃ child entered bodyEvents, state.enterAt before.nextScope = some entered ∧
        RuntimeStatementsEvaluation functions members module path formals result
          (enterLocalScope before) entered body child final bodyEvents := by
    obtain ⟨child,items,scope,cursor,alternatives⟩ := first.branch_cases
    rcases alternatives with faultCase | falseCase | continuedCase | returnedCase | trappedCase
    · obtain ⟨fault,expression,equal⟩ := faultCase
      have impossible := (conditionResult _ _ _ expression).2
      cases impossible
    · obtain ⟨next,expression,reserve,equal⟩ := falseCase
      have impossible := (conditionResult _ _ _ expression).2
      cases impossible
    · obtain ⟨entered,finished,next,ce,be,expression,enter,bodyEval,reserve,equal,trace⟩ := continuedCase
      exact False.elim (terminal.not_continued_general bodyEval)
    · obtain ⟨entered,value,finished,ce,be,expression,enter,bodyEval,equal,trace⟩ := returnedCase
      cases equal
      exact ⟨child,entered,be,enter,bodyEval⟩
    · obtain ⟨entered,fault,finished,ce,be,expression,enter,bodyEval,equal,trace⟩ := trappedCase
      cases equal
      exact ⟨child,entered,be,enter,bodyEval⟩
  rcases evaluated.cons_cases with normal | returned | trapped
  · obtain ⟨middle,next,firstEvents,restEvents,first,tail,eventEq⟩ := normal
    obtain ⟨child,entered,be,enter,bodyEval⟩ := invert first
    exact False.elim (terminal.not_continued_general bodyEval)
  · obtain ⟨middle,value,finished,items,first,tail,outcomeEq⟩ := returned
    subst outcome
    exact invert first
  · obtain ⟨middle,fault,finished,items,first,tail,outcomeEq⟩ := trapped
    subst outcome
    exact invert first

end Aurora.SourceBinding.FramePolicyAttachment
