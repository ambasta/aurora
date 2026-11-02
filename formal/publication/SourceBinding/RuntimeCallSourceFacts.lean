import SourceBinding.RuntimeEvaluationFacts
namespace Aurora.SourceBinding

/-- Adding source functions does not alter any already witnessed evaluation.
    In particular the old empty-environment fragment embeds with its entire
    outcome (including faults) and exactly the same empty trace. -/
theorem RuntimeEvaluation.weaken
    (evaluated : RuntimeEvaluation functions context state raw kind outcome events)
    (included : ∀ leaf, leaf ∈ functions → leaf ∈ larger) :
    RuntimeEvaluation larger context state raw kind outcome events := by
  induction evaluated using RuntimeEvaluation.rec
      (motive_2 := fun context state raws kinds outcome events _ =>
        RuntimeArgumentEvaluation larger context state raws kinds outcome events)
      (motive_3 := fun members module path formals result before state raw after outcome events _ =>
        RuntimeStatementEvaluation larger members module path formals result before state raw after outcome events)
      (motive_4 := fun members module path formals result before state raws after outcome events _ =>
        RuntimeStatementsEvaluation larger members module path formals result before state raws after outcome events) with
  | word => exact .word
  | boolean => exact .boolean
  | readVariable binding => exact .readVariable binding
  | enumValue binding => exact .enumValue binding
  | not _ ih => exact .not ih
  | wordBinaryFault operator _ ih => exact .wordBinaryFault operator ih
  | wordBinary operator _ _ left right => exact .wordBinary operator left right
  | enumCompareFault _ ih => exact .enumCompareFault ih
  | enumCompare _ _ left right => exact .enumCompare left right
  | shiftLeft _ count ih => exact .shiftLeft ih count
  | shiftRight _ count ih => exact .shiftRight ih count
  | andFault _ ih => exact .andFault ih
  | andStop _ ih => exact .andStop ih
  | andContinue _ _ left right => exact .andContinue left right
  | orFault _ ih => exact .orFault ih
  | orStop _ ih => exact .orStop ih
  | orContinue _ _ left right => exact .orContinue left right
  | callArgumentsFault member resolves _ ih => exact .callArgumentsFault (included _ member) resolves ih
  | callValue member resolves _ _ args body => exact .callValue (included _ member) resolves args body
  | callFault member resolves _ _ args body => exact .callFault (included _ member) resolves args body
  | fault _ ih => exact .fault ih
  | cons _ _ first rest => exact .cons first rest
  | declarationFault scope _ ih => exact .declarationFault scope ih
  | declarationValue scope _ initialized ih => exact .declarationValue scope ih initialized
  | assignmentFault member named mutable _ ih => exact .assignmentFault member named mutable ih
  | assignmentValue member named mutable _ assigned ih => exact .assignmentValue member named mutable ih assigned
  | returnFault _ ih => exact .returnFault ih
  | returnValue _ ih => exact .returnValue ih
  | branchFault scope _ ih => exact .branchFault scope ih
  | branchFalse scope _ reserved ih => exact .branchFalse scope ih reserved
  | branchTrueContinue scope _ entered _ reserved first body => exact .branchTrueContinue scope first entered body reserved
  | branchTrueReturn scope _ entered _ first body => exact .branchTrueReturn scope first entered body
  | branchTrueFault scope _ entered _ first body => exact .branchTrueFault scope first entered body
  | next _ _ first rest => exact .next first rest
  | returned _ scope ih => exact .returned ih scope
  | trapped _ scope ih => exact .trapped ih scope
  | _ => intros; exact .nil

theorem RuntimeEvaluatesWith.weaken
    (evaluated : RuntimeEvaluatesWith functions context state raw kind outcome events)
    (included : ∀ leaf, leaf ∈ functions → leaf ∈ larger) :
    RuntimeEvaluatesWith larger context state raw kind outcome events := by
  apply RuntimeEvaluation.weaken evaluated
  intro source member
  obtain ⟨leaf,present,equal⟩ := List.mem_map.mp member
  exact List.mem_map.mpr ⟨leaf,included leaf present,equal⟩

theorem RuntimeEvaluation.in_environment
    (evaluated : RuntimeEvaluation [] context state raw kind outcome events) (functions : List RuntimeSourceFunction) :
    RuntimeEvaluation functions context state raw kind outcome events :=
  evaluated.weaken (fun _ impossible => False.elim (List.not_mem_nil impossible))

theorem RuntimeEvaluates.in_environment
    (evaluated : RuntimeEvaluates context state raw kind outcome) (functions : List RuntimeSourceLeaf) :
    RuntimeEvaluatesWith functions context state raw kind outcome [] :=
  evaluated.weaken (fun _ impossible => False.elim (List.not_mem_nil impossible))

inductive RuntimeReadyArguments : List RuntimeType → List Value → Prop
  | nil : RuntimeReadyArguments [] []
  | cons : readRuntime kind (some value) = .value value → RuntimeReadyArguments kinds values →
      RuntimeReadyArguments (kind :: kinds) (value :: values)

theorem RuntimeReadyArguments.length (ready : RuntimeReadyArguments kinds values) : kinds.length = values.length := by
  induction ready with
  | nil => rfl
  | cons _ _ ih => exact congrArg Nat.succ ih

theorem RuntimeReadyArguments.lookup {index : Nat} (ready : RuntimeReadyArguments kinds values)
    (found : kinds[index]? = some kind) :
    ∃ value, values[index]? = some value ∧ readRuntime kind (some value) = .value value := by
  induction ready generalizing index with
  | nil => simp at found
  | cons typed rest ih =>
    cases index with
    | zero => simp only [List.getElem?_cons_zero,Option.some.injEq] at found; subst kind; exact ⟨_,rfl,typed⟩
    | succ index => exact ih found

def RuntimeArgumentsOutcomeTyped (kinds : List RuntimeType) : Outcome (List Value) → Prop
  | .trap _ => True
  | .value values => RuntimeReadyArguments kinds values

/-- Argument readiness is a consequence of actual ordered source evaluation,
    not a successful-callee or entry-readiness assumption. -/
theorem RuntimeArgumentEvaluation.outcome_typed
    (evaluated : RuntimeArgumentEvaluation functions context state raws kinds outcome events) :
    RuntimeArgumentsOutcomeTyped kinds outcome := by
  induction evaluated using RuntimeArgumentEvaluation.rec
      (motive_1 := fun _ _ _ _ _ _ _ => True)
      (motive_3 := fun _ _ _ _ _ _ _ _ _ _ _ _ => True)
      (motive_4 := fun _ _ _ _ _ _ _ _ _ _ _ _ => True) with
  | fault => trivial
  | @cons context state first kind value firstEvents rest kinds outcome restEvents firstEval restEval firstIH restIH =>
    cases outcome with
    | trap fault => trivial
    | value tail => exact .cons firstEval.outcome_typed restIH
  | _ => all_goals intros; first | exact True.intro | exact RuntimeReadyArguments.nil

theorem RuntimeArgumentsEvaluateWith.outcome_typed
    (evaluated : RuntimeArgumentsEvaluateWith functions context state raws kinds outcome events) :
    RuntimeArgumentsOutcomeTyped kinds outcome := RuntimeArgumentEvaluation.outcome_typed evaluated

theorem RuntimeArgumentsEvaluateWith.ready
    (evaluated : RuntimeArgumentsEvaluateWith functions context state raws kinds (.value values) events) :
    RuntimeReadyArguments kinds values := evaluated.outcome_typed

end Aurora.SourceBinding
