import SourceBinding.RuntimeStatementSimulation
import SourceBinding.RuntimeStatementFacts
import SourceBinding.RuntimeScopeFacts
import SourceBinding.RuntimeCallExpressionProof
namespace Aurora.SourceBinding

/-- Both concrete branch layouts reduce to the same source rule. The supplied
    continuation is the already checked label/jump suffix, not a body outcome. -/
theorem runtime_branch_simulates
    {leaves : List (RuntimeCallLeaf t files root module path)}
    (scope : ScopedStatements members module path formals (enterLocalScope before) body child declaredItems)
    (valid : RuntimeContextValid (runtimeStatementContext members module path formals before))
    (condition : RuntimeCallExpressionCode program caller (leaves.map (·.toCallable))
      (runtimeStatementContext members module path formals before) raw (.scalar .boolean) start conditionEnd)
    (branch : localProgram program caller conditionEnd = some (.pure (.branchFalse falsePC)))
    (falseLabels : RuntimeLabelRun program caller falsePC stop)
    (bodySim : RuntimeStatementsSimulates program caller leaves members formals result
      (enterLocalScope before) body child (conditionEnd+1) bodyEnd base saved world external)
    (suffix : ∀ source accumulator next events,
      RuntimeBodyRun program external caller saved world base source (conditionEnd+1) bodyEnd accumulator (.continued next) events →
      RuntimeBodyRun program external caller saved world base source (conditionEnd+1) stop accumulator (.continued next) events)
    (projection : ∀ leaf ∈ leaves, localProgram program leaf.target.id = canonicalEffects t leaf.identified.id) :
    RuntimeStatementSimulates program caller leaves members formals result before (.ifThen raw body)
      (leaveLocalScope before child) start stop base saved world external := by
  intro source ancestors stateAt
  obtain ⟨conditionOut,se,me,evaluated,trace,run⟩ := condition.evaluates_and_runs projection source
    (runtimeExpressionBase base source) stateAt.2.2.2.1 (fun _ => rfl) saved world external
  cases conditionOut with
  | trap fault =>
    exact ⟨_,se,me,.branchFault scope evaluated,trace,trivial,
      fun acc => runtime_body_expression_fault (run acc base.stack)⟩
  | value value =>
    have typed := evaluated.outcome_typed
    cases value with
    | word _ | signedCount4 | signedCount12 | signedCount32 | nominal _ _ => cases typed
    | boolean value => cases value with
      | false =>
        have slots : before.nextSlot ≤ (leaveLocalScope before child).nextSlot := scope.cursors.2
        have scopes : before.nextScope ≤ (leaveLocalScope before child).nextScope := Nat.le_trans (Nat.le_succ _) scope.cursors.1
        obtain ⟨next,reserved,nextAt,declared,sameValues,active⟩ := stateAt.reserve (after := leaveLocalScope before child) rfl rfl slots scopes
        refine ⟨_,se,me,.branchFalse scope evaluated reserved,trace,nextAt,?_⟩
        intro acc
        have tested := (run acc base.stack).value_run.trans (runtime_body_branch branch base source false saved world external)
        have atFalse : RuntimeBodyRun program external caller saved world base source start falsePC acc (.continued source) me :=
          ⟨_,by simpa only [List.append_nil] using tested,some (.boolean false),rfl⟩
        exact (atFalse.labels falseLabels).continued_values sameValues
      | true =>
        obtain ⟨entered,enteredAt⟩ := stateAt.enter
        obtain ⟨bodyOut,sb,mb,bodyEval,bodyTrace,bodyAt,bodyRun⟩ := bodySim source.enter (before.scope::ancestors) enteredAt
        have clear : ∀ item ∈ child.visible, item.name ∉ formals.map (·.name) :=
          scope.formal_clear (fun item present => (valid.names.2.2.2.1 item present).2.1)
        have initialRun : ∀ acc, CallRuns program external
            (.running (activeAt caller saved world (runtimeBodyFrame base source start acc))) me
            (.running (activeAt caller saved world (runtimeBodyFrame base source.enter (conditionEnd+1) (some (.boolean true))))) := by
          intro acc
          simpa only [List.append_nil] using (run acc base.stack).value_run.trans
            (runtime_body_branch branch base source true saved world external)
        cases bodyOut with
        | continued finished =>
          have left := stateAt.leave_restore scope clear bodyAt
          obtain ⟨next,reserved,nextAt,declared,sameValues,active⟩ := left.reserve rfl rfl (Nat.le_refl _) (Nat.le_refl _)
          refine ⟨_,se++sb,me++mb,.branchTrueContinue scope evaluated entered bodyEval reserved,
            trace.append bodyTrace,nextAt,?_⟩
          intro acc
          have continued := suffix source.enter (some (.boolean true)) finished mb (bodyRun (some (.boolean true)))
          have changed := continued.continued_values sameValues
          exact changed.prepend (initialRun acc)
        | returned value finished =>
          exact ⟨_,se++sb,me++mb,.branchTrueReturn scope evaluated entered bodyEval,trace.append bodyTrace,trivial,
            fun acc => (bodyRun (some (.boolean true))).return_stop.prepend (initialRun acc)⟩
        | trapped fault finished =>
          exact ⟨_,se++sb,me++mb,.branchTrueFault scope evaluated entered bodyEval,trace.append bodyTrace,trivial,
            fun acc => (bodyRun (some (.boolean true))).fault_stop.prepend (initialRun acc)⟩

end Aurora.SourceBinding
