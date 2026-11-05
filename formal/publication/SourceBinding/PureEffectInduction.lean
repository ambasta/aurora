import SourceBinding.EffectPureEmbedding
import SourceBinding.PureEffectAlgebra
import SourceBinding.EffectEvaluationTyping
import SourceBinding.EffectLegacyContext
namespace Aurora.SourceBinding

private theorem effect_value_not_trap
    (typed : EffectOutcomeTyped kind (.value raw : SourceEffectOutcome World ExternalFault))
    (malformed : readRuntime kind raw = .trap fault) : False := by
  cases raw with
  | none => exact typed
  | some value =>
    change readRuntime kind (some value) = .value value at typed
    rw [typed] at malformed
    contradiction

set_option hygiene false in
macro "pure_effect_induction " h:ident " using " rec:ident
    " with " expr:term ", " args:term ", " stmt:term ", " stmts:term ", " alg:term : tactic => do
  let recursor ←
    if rec.getId == `EffectEvaluation.rec then
      `(term| $rec (motive_2 := fun context state raws kinds outcome after events _ =>
      ∀ oldContext, context = .pure oldContext → ∃ oldOutcome oldEvents,
        $args oldContext state.locals raws kinds oldOutcome oldEvents ∧
        outcome = legacyEffectArguments oldOutcome ∧ after = state.shared ∧
        events = oldEvents.map RuntimeSourceEvent.toEffect) (motive_3 := fun context result before state raw after outcome events _ =>
      ∀ oldContext, context = .pure oldContext → ∃ oldOutcome oldEvents,
        $stmt oldContext.members oldContext.module oldContext.path oldContext.formals
          result before state.locals raw after oldOutcome oldEvents ∧
        outcome = legacyEffectBody state.shared oldOutcome ∧
        events = oldEvents.map RuntimeSourceEvent.toEffect) (motive_4 := fun context result before state raws after outcome events _ =>
      ∀ oldContext, context = .pure oldContext → ∃ oldOutcome oldEvents,
        $stmts oldContext.members oldContext.module oldContext.path oldContext.formals
          result before state.locals raws after oldOutcome oldEvents ∧
        outcome = legacyEffectBody state.shared oldOutcome ∧
        events = oldEvents.map RuntimeSourceEvent.toEffect))
    else if rec.getId == `EffectArguments.rec then
      `(term| $rec (motive_1 := fun context state raw kind outcome after events _ =>
      ∀ oldContext, context = .pure oldContext → ∃ oldOutcome oldEvents,
        $expr oldContext state.locals raw kind oldOutcome oldEvents ∧
        outcome = sourceLift oldOutcome ∧ after = state.shared ∧
        events = oldEvents.map RuntimeSourceEvent.toEffect) (motive_3 := fun context result before state raw after outcome events _ =>
      ∀ oldContext, context = .pure oldContext → ∃ oldOutcome oldEvents,
        $stmt oldContext.members oldContext.module oldContext.path oldContext.formals
          result before state.locals raw after oldOutcome oldEvents ∧
        outcome = legacyEffectBody state.shared oldOutcome ∧
        events = oldEvents.map RuntimeSourceEvent.toEffect) (motive_4 := fun context result before state raws after outcome events _ =>
      ∀ oldContext, context = .pure oldContext → ∃ oldOutcome oldEvents,
        $stmts oldContext.members oldContext.module oldContext.path oldContext.formals
          result before state.locals raws after oldOutcome oldEvents ∧
        outcome = legacyEffectBody state.shared oldOutcome ∧
        events = oldEvents.map RuntimeSourceEvent.toEffect))
    else if rec.getId == `EffectStatement.rec then
      `(term| $rec (motive_1 := fun context state raw kind outcome after events _ =>
      ∀ oldContext, context = .pure oldContext → ∃ oldOutcome oldEvents,
        $expr oldContext state.locals raw kind oldOutcome oldEvents ∧
        outcome = sourceLift oldOutcome ∧ after = state.shared ∧
        events = oldEvents.map RuntimeSourceEvent.toEffect) (motive_2 := fun context state raws kinds outcome after events _ =>
      ∀ oldContext, context = .pure oldContext → ∃ oldOutcome oldEvents,
        $args oldContext state.locals raws kinds oldOutcome oldEvents ∧
        outcome = legacyEffectArguments oldOutcome ∧ after = state.shared ∧
        events = oldEvents.map RuntimeSourceEvent.toEffect) (motive_4 := fun context result before state raws after outcome events _ =>
      ∀ oldContext, context = .pure oldContext → ∃ oldOutcome oldEvents,
        $stmts oldContext.members oldContext.module oldContext.path oldContext.formals
          result before state.locals raws after oldOutcome oldEvents ∧
        outcome = legacyEffectBody state.shared oldOutcome ∧
        events = oldEvents.map RuntimeSourceEvent.toEffect))
    else if rec.getId == `EffectStatements.rec then
      `(term| $rec (motive_1 := fun context state raw kind outcome after events _ =>
      ∀ oldContext, context = .pure oldContext → ∃ oldOutcome oldEvents,
        $expr oldContext state.locals raw kind oldOutcome oldEvents ∧
        outcome = sourceLift oldOutcome ∧ after = state.shared ∧
        events = oldEvents.map RuntimeSourceEvent.toEffect) (motive_2 := fun context state raws kinds outcome after events _ =>
      ∀ oldContext, context = .pure oldContext → ∃ oldOutcome oldEvents,
        $args oldContext state.locals raws kinds oldOutcome oldEvents ∧
        outcome = legacyEffectArguments oldOutcome ∧ after = state.shared ∧
        events = oldEvents.map RuntimeSourceEvent.toEffect) (motive_3 := fun context result before state raw after outcome events _ =>
      ∀ oldContext, context = .pure oldContext → ∃ oldOutcome oldEvents,
        $stmt oldContext.members oldContext.module oldContext.path oldContext.formals
          result before state.locals raw after oldOutcome oldEvents ∧
        outcome = legacyEffectBody state.shared oldOutcome ∧
        events = oldEvents.map RuntimeSourceEvent.toEffect))
    else Lean.Macro.throwError "expected an effect mutual recursor"
  `(tactic| induction ($h) using $recursor with
  | word =>
    first | intro oldContext pure | rename_i oldContext pure
    cases pure
    exact ⟨_,_,($alg).expression_word,rfl,rfl,rfl⟩
  | boolean =>
    first | intro oldContext pure | rename_i oldContext pure
    cases pure
    exact ⟨_,_,($alg).expression_boolean,rfl,rfl,rfl⟩
  | readVariable binding =>
    first | intro oldContext pure | rename_i oldContext pure
    cases pure
    exact ⟨_,_,($alg).expression_readVariable binding,rfl,rfl,rfl⟩
  | readField binding =>
    first | intro oldContext pure | rename_i oldContext pure
    cases pure
    cases binding.enabled
  | enumValue binding =>
    first | intro oldContext pure | rename_i oldContext pure
    cases pure
    exact ⟨_,_,($alg).expression_enumValue ((EffectEnumValue.pure_iff _).mp binding),rfl,rfl,rfl⟩
  | not inner ih =>
    first | intro oldContext pure | rename_i oldContext pure
    cases pure
    rcases ih _ rfl with ⟨out,ev,old,rfl,rfl,rfl⟩
    exact ⟨_,_,($alg).expression_not old,sourceThen_sourceLift _ _,rfl,rfl⟩
  | wordBinaryStop operator inner ih =>
    first | intro oldContext pure | rename_i oldContext pure
    cases pure
    rcases ih _ rfl with ⟨out,ev,old,same,rfl,rfl⟩
    cases out <;> cases same
    exact ⟨_,_,($alg).expression_wordBinaryFault operator old,rfl,rfl,rfl⟩
  | enumCompareStop inner ih =>
    first | intro oldContext pure | rename_i oldContext pure
    cases pure
    rcases ih _ rfl with ⟨out,ev,old,same,rfl,rfl⟩
    cases out <;> cases same
    exact ⟨_,_,($alg).expression_enumCompareFault old,rfl,rfl,rfl⟩
  | andStopped inner ih =>
    first | intro oldContext pure | rename_i oldContext pure
    cases pure
    rcases ih _ rfl with ⟨out,ev,old,same,rfl,rfl⟩
    cases out <;> cases same
    exact ⟨_,_,($alg).expression_andFault old,rfl,rfl,rfl⟩
  | orStopped inner ih =>
    first | intro oldContext pure | rename_i oldContext pure
    cases pure
    rcases ih _ rfl with ⟨out,ev,old,same,rfl,rfl⟩
    cases out <;> cases same
    exact ⟨_,_,($alg).expression_orFault old,rfl,rfl,rfl⟩
  | wordBinaryMissing operator inner ih =>
    first | intro oldContext pure | rename_i oldContext pure
    cases pure
    exact False.elim inner.outcome_typed
  | enumCompareMissing inner ih =>
    first | intro oldContext pure | rename_i oldContext pure
    cases pure
    exact False.elim inner.outcome_typed
  | missing inner ih =>
    first | intro oldContext pure | rename_i oldContext pure
    cases pure
    exact False.elim inner.outcome_typed
  | returnMissing inner ih =>
    first | intro oldContext pure | rename_i oldContext pure
    cases pure
    exact False.elim inner.outcome_typed
  | wordBinary operator left right leftIH rightIH =>
    first | intro oldContext pure | rename_i oldContext pure
    cases pure
    rcases leftIH _ rfl with ⟨out,ev,old,same,rfl,rfl⟩
    cases out <;> cases same
    rcases rightIH _ rfl with ⟨out,rest,rightOld,rfl,rfl,rfl⟩
    exact ⟨_,_,($alg).expression_wordBinary operator old rightOld,
      sourceThen_sourceLift _ _,rfl,List.map_append.symm⟩
  | enumCompare left right leftIH rightIH =>
    first | intro oldContext pure | rename_i oldContext pure
    cases pure
    rcases leftIH _ rfl with ⟨out,ev,old,same,rfl,rfl⟩
    cases out <;> cases same
    rcases rightIH _ rfl with ⟨out,rest,rightOld,rfl,rfl,rfl⟩
    exact ⟨_,_,($alg).expression_enumCompare old rightOld,
      sourceThen_sourceLift _ _,rfl,List.map_append.symm⟩
  | shiftLeft inner count ih =>
    first | intro oldContext pure | rename_i oldContext pure
    cases pure
    rcases ih _ rfl with ⟨out,ev,old,rfl,rfl,rfl⟩
    exact ⟨_,_,($alg).expression_shiftLeft old count,sourceThen_sourceLift _ _,rfl,rfl⟩
  | shiftRight inner count ih =>
    first | intro oldContext pure | rename_i oldContext pure
    cases pure
    rcases ih _ rfl with ⟨out,ev,old,rfl,rfl,rfl⟩
    exact ⟨_,_,($alg).expression_shiftRight old count,sourceThen_sourceLift _ _,rfl,rfl⟩
  | andMalformed inner malformed ih =>
    first | intro oldContext pure | rename_i oldContext pure
    cases pure
    exact False.elim (effect_value_not_trap inner.outcome_typed malformed)
  | orMalformed inner malformed ih =>
    first | intro oldContext pure | rename_i oldContext pure
    cases pure
    exact False.elim (effect_value_not_trap inner.outcome_typed malformed)
  | andStop inner ih =>
    first | intro oldContext pure | rename_i oldContext pure
    cases pure
    rcases ih _ rfl with ⟨out,ev,old,same,rfl,rfl⟩
    cases out <;> cases same
    exact ⟨_,_,($alg).expression_andStop old,rfl,rfl,rfl⟩
  | orStop inner ih =>
    first | intro oldContext pure | rename_i oldContext pure
    cases pure
    rcases ih _ rfl with ⟨out,ev,old,same,rfl,rfl⟩
    cases out <;> cases same
    exact ⟨_,_,($alg).expression_orStop old,rfl,rfl,rfl⟩
  | andContinue left right leftIH rightIH =>
    first | intro oldContext pure | rename_i oldContext pure
    cases pure
    rcases leftIH _ rfl with ⟨out,ev,old,same,rfl,rfl⟩
    cases out <;> cases same
    rcases rightIH _ rfl with ⟨out,rest,rightOld,rfl,rfl,rfl⟩
    exact ⟨_,_,($alg).expression_andContinue old rightOld,rfl,rfl,List.map_append.symm⟩
  | orContinue left right leftIH rightIH =>
    first | intro oldContext pure | rename_i oldContext pure
    cases pure
    rcases leftIH _ rfl with ⟨out,ev,old,same,rfl,rfl⟩
    cases out <;> cases same
    rcases rightIH _ rfl with ⟨out,rest,rightOld,rfl,rfl,rfl⟩
    exact ⟨_,_,($alg).expression_orContinue old rightOld,rfl,rfl,List.map_append.symm⟩
  | callArgumentsStop member resolves arguments ih =>
    first | intro oldContext pure | rename_i oldContext pure
    cases pure
    rcases List.mem_map.mp member with ⟨callee,oldMember,rfl⟩
    rcases ih _ rfl with ⟨out,ev,old,same,rfl,rfl⟩
    cases out <;> cases same
    exact ⟨_,_,($alg).expression_callArgumentsFault oldMember
      ((callee.toEffect_resolves _ _).mp resolves) old,rfl,rfl,rfl⟩
  | callEntryFault member resolves arguments failed ih =>
    first | intro oldContext pure | rename_i oldContext pure
    cases pure
    have checked := arguments.checked
    rw [checked] at failed
    contradiction
  | callValue member resolves arguments ready body argumentsIH bodyIH =>
    first | intro oldContext pure | rename_i oldContext pure
    cases pure
    rcases List.mem_map.mp member with ⟨callee,oldMember,rfl⟩
    rcases argumentsIH _ rfl with ⟨out,ev,old,same,rfl,rfl⟩
    cases out <;> cases same
    rcases bodyIH _ rfl with ⟨bodyOut,bodyEvents,bodyOld,same,trace⟩
    cases bodyOut <;> cases same
    refine ⟨_,_,($alg).expression_callValue oldMember
      ((callee.toEffect_resolves _ _).mp resolves) old bodyOld,rfl,rfl,?_⟩
    subst trace
    simp only [List.map_append,List.map_cons,List.map_nil,RuntimeSourceEvent.toEffect,
      RuntimeSourceFunction.toEffect_key]
  | callStop member resolves arguments ready body argumentsIH bodyIH =>
    first | intro oldContext pure | rename_i oldContext pure
    cases pure
    rcases List.mem_map.mp member with ⟨callee,oldMember,rfl⟩
    rcases argumentsIH _ rfl with ⟨out,ev,old,same,rfl,rfl⟩
    cases out <;> cases same
    rcases bodyIH _ rfl with ⟨bodyOut,bodyEvents,bodyOld,same,trace⟩
    cases bodyOut <;> cases same
    refine ⟨_,_,($alg).expression_callFault oldMember
      ((callee.toEffect_resolves _ _).mp resolves) old bodyOld,rfl,rfl,?_⟩
    subst trace
    simp only [List.map_append,List.map_cons,List.map_nil,RuntimeSourceEvent.toEffect,
      RuntimeSourceFunction.toEffect_key]
  | cons head tail headIH tailIH =>
    first | intro oldContext pure | rename_i oldContext pure
    cases pure
    rcases headIH _ rfl with ⟨out,ev,old,same,rfl,rfl⟩
    cases out <;> cases same
    rcases tailIH _ rfl with ⟨out,rest,tailOld,rfl,rfl,rfl⟩
    exact ⟨_,_,($alg).arguments_cons old tailOld,effect_prepend_legacy _ _,rfl,List.map_append.symm⟩
  | declarationStop scope inner ih =>
    first | intro oldContext pure | rename_i oldContext pure
    cases pure
    rcases ih _ rfl with ⟨out,ev,old,same,rfl,rfl⟩
    cases out <;> cases same
    exact ⟨_,_,($alg).statement_declarationFault scope old,rfl,rfl⟩
  | assignmentStop member named mutable inner ih =>
    first | intro oldContext pure | rename_i oldContext pure
    cases pure
    rcases ih _ rfl with ⟨out,ev,old,same,rfl,rfl⟩
    cases out <;> cases same
    exact ⟨_,_,($alg).statement_assignmentFault member named mutable old,rfl,rfl⟩
  | returnStop inner ih =>
    first | intro oldContext pure | rename_i oldContext pure
    cases pure
    rcases ih _ rfl with ⟨out,ev,old,same,rfl,rfl⟩
    cases out <;> cases same
    exact ⟨_,_,($alg).statement_returnFault  old,rfl,rfl⟩
  | branchStop scope inner ih =>
    first | intro oldContext pure | rename_i oldContext pure
    cases pure
    rcases ih _ rfl with ⟨out,ev,old,same,rfl,rfl⟩
    cases out <;> cases same
    exact ⟨_,_,($alg).statement_branchFault scope old,rfl,rfl⟩
  | declarationMalformed scope inner malformed ih =>
    first | intro oldContext pure | rename_i oldContext pure
    cases pure
    exact False.elim (effect_value_not_trap inner.outcome_typed malformed)
  | assignmentMalformed member named mutable inner malformed ih =>
    first | intro oldContext pure | rename_i oldContext pure
    cases pure
    exact False.elim (effect_value_not_trap inner.outcome_typed malformed)
  | branchMalformed scope inner malformed ih =>
    first | intro oldContext pure | rename_i oldContext pure
    cases pure
    exact False.elim (effect_value_not_trap inner.outcome_typed malformed)
  | declarationValue scope inner typed initialized ih =>
    first | intro oldContext pure | rename_i oldContext pure
    cases pure
    rcases ih _ rfl with ⟨out,ev,old,same,rfl,rfl⟩
    cases out <;> cases same
    have valid := inner.outcome_typed
    change readRuntime _ (some _) = .value _ at valid
    rw [valid] at typed
    cases typed
    exact ⟨_,_,($alg).statement_declarationValue scope old initialized,rfl,rfl⟩
  | assignmentValue member named mutable inner typed initialized ih =>
    first | intro oldContext pure | rename_i oldContext pure
    cases pure
    rcases ih _ rfl with ⟨out,ev,old,same,rfl,rfl⟩
    cases out <;> cases same
    have valid := inner.outcome_typed
    change readRuntime _ (some _) = .value _ at valid
    rw [valid] at typed
    cases typed
    exact ⟨_,_,($alg).statement_assignmentValue member named mutable old initialized,rfl,rfl⟩
  | returnValue inner ih =>
    first | intro oldContext pure | rename_i oldContext pure
    cases pure
    rcases ih _ rfl with ⟨out,ev,old,same,rfl,rfl⟩
    cases out <;> cases same
    exact ⟨_,_,($alg).statement_returnValue old,rfl,rfl⟩
  | branchFalse scope inner reserved ih =>
    first | intro oldContext pure | rename_i oldContext pure
    cases pure
    rcases ih _ rfl with ⟨out,ev,old,same,rfl,rfl⟩
    cases out <;> cases same
    exact ⟨_,_,($alg).statement_branchFalse scope old reserved,rfl,rfl⟩
  | branchTrueContinue scope inner entered body reserved innerIH bodyIH =>
    first | intro oldContext pure | rename_i oldContext pure
    cases pure
    rcases innerIH _ rfl with ⟨out,ev,old,same,rfl,rfl⟩
    cases out <;> cases same
    rcases bodyIH _ rfl with ⟨bodyOut,bodyEvents,bodyOld,same,rfl⟩
    cases bodyOut <;> cases same
    exact ⟨_,_,($alg).statement_branchTrueContinue scope old entered bodyOld reserved,rfl,List.map_append.symm⟩
  | branchTrueReturn scope inner entered body innerIH bodyIH =>
    first | intro oldContext pure | rename_i oldContext pure
    cases pure
    rcases innerIH _ rfl with ⟨out,ev,old,same,rfl,rfl⟩
    cases out <;> cases same
    rcases bodyIH _ rfl with ⟨bodyOut,bodyEvents,bodyOld,same,rfl⟩
    cases bodyOut <;> cases same
    exact ⟨_,_,($alg).statement_branchTrueReturn scope old entered bodyOld,rfl,List.map_append.symm⟩
  | branchTrueStop scope inner entered body innerIH bodyIH =>
    first | intro oldContext pure | rename_i oldContext pure
    cases pure
    rcases innerIH _ rfl with ⟨out,ev,old,same,rfl,rfl⟩
    cases out <;> cases same
    rcases bodyIH _ rfl with ⟨bodyOut,bodyEvents,bodyOld,same,rfl⟩
    cases bodyOut <;> cases same
    exact ⟨_,_,($alg).statement_branchTrueFault scope old entered bodyOld,rfl,List.map_append.symm⟩
  | resourceDeclareArgumentsStop enabled =>
    first | intro oldContext pure | rename_i oldContext pure
    cases pure
    cases enabled
  | resourceDeclare enabled =>
    first | intro oldContext pure | rename_i oldContext pure
    cases pure
    cases enabled
  | resourceRequireArgumentsStop enabled =>
    first | intro oldContext pure | rename_i oldContext pure
    cases pure
    cases enabled
  | resourceRequire enabled =>
    first | intro oldContext pure | rename_i oldContext pure
    cases pure
    cases enabled
  | branchElseStop enabled =>
    first | intro oldContext pure | rename_i oldContext pure
    cases pure
    cases enabled
  | branchElseMalformed enabled =>
    first | intro oldContext pure | rename_i oldContext pure
    cases pure
    cases enabled
  | branchElseTrueContinue enabled =>
    first | intro oldContext pure | rename_i oldContext pure
    cases pure
    cases enabled
  | branchElseTrueReturn enabled =>
    first | intro oldContext pure | rename_i oldContext pure
    cases pure
    cases enabled
  | branchElseTrueStop enabled =>
    first | intro oldContext pure | rename_i oldContext pure
    cases pure
    cases enabled
  | branchElseFalseContinue enabled =>
    first | intro oldContext pure | rename_i oldContext pure
    cases pure
    cases enabled
  | branchElseFalseReturn enabled =>
    first | intro oldContext pure | rename_i oldContext pure
    cases pure
    cases enabled
  | branchElseFalseStop enabled =>
    first | intro oldContext pure | rename_i oldContext pure
    cases pure
    cases enabled
  | fieldAssignmentStop field =>
    first | intro oldContext pure | rename_i oldContext pure
    cases pure
    cases field.enabled
  | fieldAssignmentMalformed field =>
    first | intro oldContext pure | rename_i oldContext pure
    cases pure
    cases field.enabled
  | fieldAssignmentValue field =>
    first | intro oldContext pure | rename_i oldContext pure
    cases pure
    cases field.enabled
  | next first rest firstIH restIH =>
    first | intro oldContext pure | rename_i oldContext pure
    cases pure
    rcases firstIH _ rfl with ⟨out,ev,old,same,rfl⟩
    cases out <;> cases same
    rcases restIH _ rfl with ⟨out,restEvents,restOld,rfl,rfl⟩
    exact ⟨_,_,($alg).statements_next old restOld,rfl,List.map_append.symm⟩
  | returned first scope firstIH =>
    first | intro oldContext pure | rename_i oldContext pure
    cases pure
    rcases firstIH _ rfl with ⟨out,ev,old,same,rfl⟩
    cases out <;> cases same
    exact ⟨_,_,($alg).statements_returned old scope,rfl,rfl⟩
  | _ =>
    intros
    rename_i oldContext pure
    cases pure
    first
    | exact ⟨_,_,($alg).arguments_nil,rfl,rfl,rfl⟩
    | exact ⟨_,_,($alg).statements_nil,rfl,rfl⟩
    | rename_i inner innerIH
      rcases innerIH _ rfl with ⟨out,ev,old,same,rfl,rfl⟩
      cases out <;> cases same
      exact ⟨_,_,($alg).arguments_fault old,rfl,rfl,rfl⟩
    | rename_i first scope firstIH
      rcases firstIH _ rfl with ⟨out,ev,old,same,rfl⟩
      cases out <;> cases same
      exact ⟨_,_,($alg).statements_trapped old scope,rfl,rfl⟩)

variable {functions : List RuntimeSourceFunction}
    {Expression : RuntimeExprContext → RuntimeLocals → SourceExpr → RuntimeType → Outcome Value → List RuntimeSourceEvent → Prop}
    {Arguments : RuntimeExprContext → RuntimeLocals → List SourceExpr → List RuntimeType → Outcome (List Value) → List RuntimeSourceEvent → Prop}
    {Statement : List Declaration → Name → Name → List Formal → RuntimeType → LocalContext → RuntimeLocals → SourceStatement → LocalContext → RuntimeBodyOutcome → List RuntimeSourceEvent → Prop}
    {Statements : List Declaration → Name → Name → List Formal → RuntimeType → LocalContext → RuntimeLocals → List SourceStatement → LocalContext → RuntimeBodyOutcome → List RuntimeSourceEvent → Prop}

theorem EffectEvaluation.pure_induction
    (algebra : PureEffectAlgebra functions Expression Arguments Statement Statements)
    (evaluated : EffectEvaluation (functions.map RuntimeSourceFunction.toEffect) response context state raw kind outcome after events) :
      ∀ oldContext, context = .pure oldContext → ∃ oldOutcome oldEvents,
        Expression oldContext state.locals raw kind oldOutcome oldEvents ∧
        outcome = sourceLift oldOutcome ∧ after = state.shared ∧
        events = oldEvents.map RuntimeSourceEvent.toEffect := by
  pure_effect_induction evaluated using EffectEvaluation.rec with Expression, Arguments, Statement, Statements, algebra

theorem EffectArguments.pure_induction
    (algebra : PureEffectAlgebra functions Expression Arguments Statement Statements)
    (evaluated : EffectArguments (functions.map RuntimeSourceFunction.toEffect) response context state raws kinds outcome after events) :
      ∀ oldContext, context = .pure oldContext → ∃ oldOutcome oldEvents,
        Arguments oldContext state.locals raws kinds oldOutcome oldEvents ∧
        outcome = legacyEffectArguments oldOutcome ∧ after = state.shared ∧
        events = oldEvents.map RuntimeSourceEvent.toEffect := by
  pure_effect_induction evaluated using EffectArguments.rec with Expression, Arguments, Statement, Statements, algebra

theorem EffectStatement.pure_induction
    (algebra : PureEffectAlgebra functions Expression Arguments Statement Statements)
    (evaluated : EffectStatement (functions.map RuntimeSourceFunction.toEffect) response context result before state raw after outcome events) :
      ∀ oldContext, context = .pure oldContext → ∃ oldOutcome oldEvents,
        Statement oldContext.members oldContext.module oldContext.path oldContext.formals
          result before state.locals raw after oldOutcome oldEvents ∧
        outcome = legacyEffectBody state.shared oldOutcome ∧
        events = oldEvents.map RuntimeSourceEvent.toEffect := by
  pure_effect_induction evaluated using EffectStatement.rec with Expression, Arguments, Statement, Statements, algebra

theorem EffectStatements.pure_induction
    (algebra : PureEffectAlgebra functions Expression Arguments Statement Statements)
    (evaluated : EffectStatements (functions.map RuntimeSourceFunction.toEffect) response context result before state raws after outcome events) :
      ∀ oldContext, context = .pure oldContext → ∃ oldOutcome oldEvents,
        Statements oldContext.members oldContext.module oldContext.path oldContext.formals
          result before state.locals raws after oldOutcome oldEvents ∧
        outcome = legacyEffectBody state.shared oldOutcome ∧
        events = oldEvents.map RuntimeSourceEvent.toEffect := by
  pure_effect_induction evaluated using EffectStatements.rec with Expression, Arguments, Statement, Statements, algebra

end Aurora.SourceBinding
