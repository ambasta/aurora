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
  induction evaluated using RuntimeEvaluation.rec
      (motive_2 := fun context state raws kinds outcome events _ =>
        ∀ next, RuntimeReadsEqual context state next →
          RuntimeArgumentEvaluation functions context next raws kinds outcome events)
      (motive_3 := fun _ _ _ _ _ _ _ _ _ _ _ _ => True)
      (motive_4 := fun _ _ _ _ _ _ _ _ _ _ _ _ => True) with
  | word => intro next same; exact .word
  | boolean => intro next same; exact .boolean
  | readVariable binding =>
    intro next same
    rw [← same _ _ binding]
    exact .readVariable binding
  | enumValue binding => intro next same; exact .enumValue binding
  | not _ ih => intro next same; exact .not (ih next same)
  | wordBinaryFault operator _ ih => intro next same; exact .wordBinaryFault operator (ih next same)
  | wordBinary operator _ _ left right => intro next same; exact .wordBinary operator (left next same) (right next same)
  | enumCompareFault _ ih => intro next same; exact .enumCompareFault (ih next same)
  | enumCompare _ _ left right => intro next same; exact .enumCompare (left next same) (right next same)
  | shiftLeft _ count ih => intro next same; exact .shiftLeft (ih next same) count
  | shiftRight _ count ih => intro next same; exact .shiftRight (ih next same) count
  | andFault _ ih => intro next same; exact .andFault (ih next same)
  | andStop _ ih => intro next same; exact .andStop (ih next same)
  | andContinue _ _ left right => intro next same; exact .andContinue (left next same) (right next same)
  | orFault _ ih => intro next same; exact .orFault (ih next same)
  | orStop _ ih => intro next same; exact .orStop (ih next same)
  | orContinue _ _ left right => intro next same; exact .orContinue (left next same) (right next same)
  | callArgumentsFault member resolves _ args => intro next same; exact .callArgumentsFault member resolves (args next same)
  | callValue member resolves _ body args bodyIH => intro next same; exact .callValue member resolves (args next same) body
  | callFault member resolves _ body args bodyIH => intro next same; exact .callFault member resolves (args next same) body
  | fault _ ih next same => exact .fault (ih next same)
  | cons _ _ first rest next same => exact .cons (first next same) (rest next same)
  | nil => intros; exact .nil
  | _ => intros; trivial

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
