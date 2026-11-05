import SourceBinding.RuntimeEvaluationResults
namespace Aurora.SourceBinding

/-- Only reads of bindings actually resolved by this lexical context matter.
    Values outside those bindings may differ; faults are compared exactly. -/
def RuntimeReadsEqual (context : RuntimeExprContext) (before after : RuntimeLocals) : Prop :=
  ∀ name binding, RuntimeVariableBinding context name binding →
    after.readBound binding = before.readBound binding

/-- Expressions do not mutate their caller's local state. Actual nested callee
    bodies keep the very same formal seed and derivation after argument transport. -/
theorem RuntimeEvaluation.transport_reads
    (evaluated : RuntimeEvaluation functions context state raw kind outcome events) :
    ∀ next, RuntimeReadsEqual context state next →
      RuntimeEvaluation functions context next raw kind outcome events := by
  apply PureRuntimeEvaluation.induct evaluated
    (Expression := fun context state raw kind outcome events =>
      ∀ next, RuntimeReadsEqual context state next → RuntimeEvaluation functions context next raw kind outcome events)
    (Arguments := fun context state raws kinds outcome events =>
      ∀ next, RuntimeReadsEqual context state next → RuntimeArgumentEvaluation functions context next raws kinds outcome events)
    (Statement := RuntimeStatementEvaluation functions)
    (Statements := RuntimeStatementsEvaluation functions)
  exact {
    expression_word := by
      intro context state value
      intro next same; exact .word
    expression_boolean := by
      intro context state value
      intro next same; exact .boolean
    expression_readVariable := by
      intro context name binding state h0
      intro next same
      rw [← same _ _ h0]
      exact .readVariable h0
    expression_enumValue := by
      intro context name identity ordinal state h0
      intro next same; exact .enumValue h0
    expression_not := by
      intro context state inner outcome events h0
      intro next same; exact .not (h0 next same)
    expression_wordBinaryFault := by
      intro operator primitive result context state left fault events right h0 h1
      intro next same; exact .wordBinaryFault h0 (h1 next same)
    expression_wordBinary := by
      intro operator primitive result context state left value leftEvents right outcome rightEvents h0 h1 h2
      intro next same; exact .wordBinary h0 (h1 next same) (h2 next same)
    expression_enumCompareFault := by
      intro context state left identity fault events right equal h0
      intro next same; exact .enumCompareFault (h0 next same)
    expression_enumCompare := by
      intro context state left identity value leftEvents right outcome rightEvents equal h0 h1
      intro next same; exact .enumCompare (h0 next same) (h1 next same)
    expression_shiftLeft := by
      intro context state left outcome events right count h0 h1
      intro next same; exact .shiftLeft (h0 next same) h1
    expression_shiftRight := by
      intro context state left outcome events right count h0 h1
      intro next same; exact .shiftRight (h0 next same) h1
    expression_andFault := by
      intro context state left fault events right h0
      intro next same; exact .andFault (h0 next same)
    expression_andStop := by
      intro context state left events right h0
      intro next same; exact .andStop (h0 next same)
    expression_andContinue := by
      intro context state left leftEvents right outcome rightEvents h0 h1
      intro next same; exact .andContinue (h0 next same) (h1 next same)
    expression_orFault := by
      intro context state left fault events right h0
      intro next same; exact .orFault (h0 next same)
    expression_orStop := by
      intro context state left events right h0
      intro next same; exact .orStop (h0 next same)
    expression_orContinue := by
      intro context state left leftEvents right outcome rightEvents h0 h1
      intro next same; exact .orContinue (h0 next same) (h1 next same)
    expression_callArgumentsFault := by
      intro leaf context name state sources fault events h0 h1 h2
      intro next same; exact .callArgumentsFault h0 h1 (h2 next same)
    expression_callValue := by
      intro leaf context name state sources values argumentEvents after value finished bodyEvents h0 h1 h2 h3
      intro next same; exact .callValue h0 h1 (h2 next same) h3
    expression_callFault := by
      intro leaf context name state sources values argumentEvents after fault finished bodyEvents h0 h1 h2 h3
      intro next same; exact .callFault h0 h1 (h2 next same) h3
    arguments_nil := by
      intro context state
      intro next same; exact .nil
    arguments_fault := by
      intro context state first kind fault events rest kinds h0
      intro next same; exact .fault (h0 next same)
    arguments_cons := by
      intro context state first kind value firstEvents rest kinds outcome restEvents h0 h1
      intro next same; exact .cons (h0 next same) (h1 next same)
    statement_declarationFault := by
      intro members module path formals before raw after binding state fault events result declaration h0 h1
      exact .declarationFault h0 (h1 state (fun _ _ _ => rfl))
    statement_declarationValue := by
      intro members module path formals before raw after binding state value events next result declaration h0 h1 h2
      exact .declarationValue h0 (h1 state (fun _ _ _ => rfl)) h2
    statement_assignmentFault := by
      intro binding name members module path formals before state raw fault events result h0 h1 h2 h3
      exact .assignmentFault h0 h1 h2 (h3 state (fun _ _ _ => rfl))
    statement_assignmentValue := by
      intro binding name members module path formals before state raw value events next result h0 h1 h2 h3 h4
      exact .assignmentValue h0 h1 h2 (h3 state (fun _ _ _ => rfl)) h4
    statement_returnFault := by
      intro members module path formals before state raw result fault events h0
      exact .returnFault (h0 state (fun _ _ _ => rfl))
    statement_returnValue := by
      intro members module path formals before state raw result value events h0
      exact .returnValue (h0 state (fun _ _ _ => rfl))
    statement_branchFault := by
      intro members module path formals before body child declaredItems state condition fault events result h0 h1
      exact .branchFault h0 (h1 state (fun _ _ _ => rfl))
    statement_branchFalse := by
      intro members module path formals before body child declaredItems state condition events next result h0 h1 h2
      exact .branchFalse h0 (h1 state (fun _ _ _ => rfl)) h2
    statement_branchTrueContinue := by
      intro members module path formals before body child declaredItems state condition firstEvents entered result finished bodyEvents next h0 h1 h2 h3 h4
      exact .branchTrueContinue h0 (h1 state (fun _ _ _ => rfl)) h2 h3 h4
    statement_branchTrueReturn := by
      intro members module path formals before body child declaredItems state condition firstEvents entered result value finished bodyEvents h0 h1 h2 h3
      exact .branchTrueReturn h0 (h1 state (fun _ _ _ => rfl)) h2 h3
    statement_branchTrueFault := by
      intro members module path formals before body child declaredItems state condition firstEvents entered result fault finished bodyEvents h0 h1 h2 h3
      exact .branchTrueFault h0 (h1 state (fun _ _ _ => rfl)) h2 h3
    statements_nil := by
      intro members module path formals result before state
      exact .nil
    statements_next := by
      intro members module path formals result before state first middle next firstEvents rest after outcome restEvents h0 h1
      exact .next h0 h1
    statements_returned := by
      intro members module path formals result before state first middle value final events rest after declaredItems h0 h1
      exact .returned h0 h1
    statements_trapped := by
      intro members module path formals result before state first middle fault final events rest after declaredItems h0 h1
      exact .trapped h0 h1
  }

theorem RuntimeExpressionResult.transport_reads
    (result : RuntimeExpressionResult functions context before raw kind outcome)
    (same : RuntimeReadsEqual context before after) :
    RuntimeExpressionResult functions context after raw kind outcome := by
  intro actualKind actual events evaluated
  apply result _ _ _
  apply evaluated.transport_reads before
  intro name binding resolved
  exact (same name binding resolved).symm

end Aurora.SourceBinding
