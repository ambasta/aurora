import SourceBinding.LegacyLeafSemantics
import SourceBinding.RuntimeSingleton
namespace Aurora.SourceBinding

/-- Every old derivation, with arbitrary environment and faults, remains valid. -/
theorem LegacyLeafEvaluation.forward
    (evaluated : LegacyLeafEvaluation functions context state raw kind outcome events) :
    RuntimeEvaluatesWith functions context state raw kind outcome events := by
  induction evaluated using LegacyLeafEvaluation.rec
      (motive_2 := fun context state raws kinds outcome events _ =>
        RuntimeArgumentsEvaluateWith functions context state raws kinds outcome events) with
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
  | callArgumentsFault member resolves _ ih => exact RuntimeEvaluation.callArgumentsFault (leaf := _) (List.mem_map.mpr ⟨_,member,rfl⟩) resolves ih
  | callValue member resolves _ _ args body => exact RuntimeEvaluatesWith.callValue member resolves args body
  | callFault member resolves _ _ args body => exact RuntimeEvaluatesWith.callFault member resolves args body
  | nil => exact .nil
  | fault _ ih => exact .fault ih
  | cons _ _ first rest => exact .cons first rest

theorem LegacyLeafArguments.forward
    (evaluated : LegacyLeafArguments functions context state raws kinds outcome events) :
    RuntimeArgumentsEvaluateWith functions context state raws kinds outcome events := by
  induction evaluated using LegacyLeafArguments.rec
      (motive_1 := fun _ _ _ _ _ _ _ => True) with
  | nil => exact .nil
  | fault first _ => exact .fault first.forward
  | cons first rest _ ih => exact .cons first.forward ih
  | _ => trivial

theorem LegacyLeafStatement.forward
    (evaluated : LegacyLeafStatement functions members module path formals result before state raw after outcome events) :
    RuntimeStatementEvaluates functions members module path formals result before state raw after outcome events := by
  induction evaluated using LegacyLeafStatement.rec
      (motive_2 := fun before state raws after outcome events _ =>
        RuntimeStatementsEvaluate functions members module path formals result before state raws after outcome events) with
  | declarationFault scope expression => exact .declarationFault scope expression.forward
  | declarationValue scope expression initialized => exact .declarationValue scope expression.forward initialized
  | assignmentFault member named mutable expression => exact .assignmentFault member named mutable expression.forward
  | assignmentValue member named mutable expression assigned => exact .assignmentValue member named mutable expression.forward assigned
  | returnFault expression => exact .returnFault expression.forward
  | returnValue expression => exact .returnValue expression.forward
  | branchFault scope expression => exact .branchFault scope expression.forward
  | branchFalse scope expression reserved => exact .branchFalse scope expression.forward reserved
  | branchTrueContinue scope expression entered body reserved ih =>
      exact .branchTrueContinue scope expression.forward entered ih reserved
  | branchTrueReturn scope expression entered body ih => exact .branchTrueReturn scope expression.forward entered ih
  | branchTrueFault scope expression entered body ih => exact .branchTrueFault scope expression.forward entered ih
  | nil => exact .nil
  | next first rest ih tail => exact .next ih tail
  | returned first scope ih => exact .returned ih scope
  | trapped first scope ih => exact .trapped ih scope

theorem LegacyLeafStatements.forward
    (evaluated : LegacyLeafStatements functions members module path formals result before state raws after outcome events) :
    RuntimeStatementsEvaluate functions members module path formals result before state raws after outcome events := by
  induction evaluated using LegacyLeafStatements.rec
      (motive_1 := fun _ _ _ _ _ _ _ => True) with
  | nil => exact .nil
  | next first rest _ ih => exact .next first.forward ih
  | returned first scope _ => exact .returned first.forward scope
  | trapped first scope _ => exact .trapped first.forward scope
  | _ => trivial

theorem legacy_singleton_return_iff :
    LegacyLeafStatements functions members module path formals result before state
      [.returnValue raw] after (.returned value final) events ↔
    after = before ∧ final = state ∧
      LegacyLeafEvaluation functions (runtimeStatementContext members module path formals before)
        state raw result (.value value) events := by
  constructor
  · intro evaluated
    cases evaluated with
    | next first rest => cases first
    | returned first tail =>
      cases first with
      | returnValue expression => cases tail; exact ⟨rfl,rfl,expression⟩
  · rintro ⟨rfl,rfl,evaluated⟩
    exact .returned (.returnValue evaluated) .nil

theorem legacy_singleton_trap_iff :
    LegacyLeafStatements functions members module path formals result before state
      [.returnValue raw] after (.trapped fault final) events ↔
    after = before ∧ final = state ∧
      LegacyLeafEvaluation functions (runtimeStatementContext members module path formals before)
        state raw result (.trap fault) events := by
  constructor
  · intro evaluated
    cases evaluated with
    | next first rest => cases first
    | trapped first tail =>
      cases first with
      | returnFault expression => cases tail; exact ⟨rfl,rfl,expression⟩
  · rintro ⟨rfl,rfl,evaluated⟩
    exact .trapped (.returnFault evaluated) .nil

private theorem legacyLeafAlgebra (functions : List RuntimeSourceLeaf) :
    PureEffectAlgebra (functions.map RuntimeSourceLeaf.toFunction)
      (LegacyLeafEvaluation functions) (LegacyLeafArguments functions)
      (LegacyLeafStatement functions) (LegacyLeafStatements functions) where
  expression_word := by
    intro context state value
    exact LegacyLeafEvaluation.word
  expression_boolean := by
    intro context state value
    exact LegacyLeafEvaluation.boolean
  expression_readVariable := by
    intro context name binding state h0
    exact LegacyLeafEvaluation.readVariable h0
  expression_enumValue := by
    intro context name identity ordinal state h0
    exact LegacyLeafEvaluation.enumValue h0
  expression_not := by
    intro context state inner outcome events h0
    exact LegacyLeafEvaluation.not h0
  expression_wordBinaryFault := by
    intro operator primitive result context state left fault events right h0 h1
    exact LegacyLeafEvaluation.wordBinaryFault h0 h1
  expression_wordBinary := by
    intro operator primitive result context state left value leftEvents right outcome rightEvents h0 h1 h2
    exact LegacyLeafEvaluation.wordBinary h0 h1 h2
  expression_enumCompareFault := by
    intro context state left identity fault events right equal h0
    exact LegacyLeafEvaluation.enumCompareFault h0
  expression_enumCompare := by
    intro context state left identity value leftEvents right outcome rightEvents equal h0 h1
    exact LegacyLeafEvaluation.enumCompare h0 h1
  expression_shiftLeft := by
    intro context state left outcome events right count h0 h1
    exact LegacyLeafEvaluation.shiftLeft h0 h1
  expression_shiftRight := by
    intro context state left outcome events right count h0 h1
    exact LegacyLeafEvaluation.shiftRight h0 h1
  expression_andFault := by
    intro context state left fault events right h0
    exact LegacyLeafEvaluation.andFault h0
  expression_andStop := by
    intro context state left events right h0
    exact LegacyLeafEvaluation.andStop h0
  expression_andContinue := by
    intro context state left leftEvents right outcome rightEvents h0 h1
    exact LegacyLeafEvaluation.andContinue h0 h1
  expression_orFault := by
    intro context state left fault events right h0
    exact LegacyLeafEvaluation.orFault h0
  expression_orStop := by
    intro context state left events right h0
    exact LegacyLeafEvaluation.orStop h0
  expression_orContinue := by
    intro context state left leftEvents right outcome rightEvents h0 h1
    exact LegacyLeafEvaluation.orContinue h0 h1
  expression_callArgumentsFault := by
    intro leaf context name state sources fault events h0 h1 h2
    obtain ⟨source,member,equal⟩ := List.mem_map.mp h0
    cases equal
    exact .callArgumentsFault member h1 h2
  expression_callValue := by
    intro leaf context name state sources values argumentEvents after value finished bodyEvents h0 h1 h2 h3
    obtain ⟨source,member,equal⟩ := List.mem_map.mp h0
    cases equal
    simp only [RuntimeSourceLeaf.toFunction] at h3
    rw [source.singleton] at h3
    have old := (legacy_singleton_return_iff.mp h3).2.2
    exact .callValue member h1 h2 (by simpa only [source.initial_context] using old)
  expression_callFault := by
    intro leaf context name state sources values argumentEvents after fault finished bodyEvents h0 h1 h2 h3
    obtain ⟨source,member,equal⟩ := List.mem_map.mp h0
    cases equal
    simp only [RuntimeSourceLeaf.toFunction] at h3
    rw [source.singleton] at h3
    have old := (legacy_singleton_trap_iff.mp h3).2.2
    exact .callFault member h1 h2 (by simpa only [source.initial_context] using old)
  arguments_nil := by
    intro context state
    exact LegacyLeafArguments.nil
  arguments_fault := by
    intro context state first kind fault events rest kinds h0
    exact LegacyLeafArguments.fault h0
  arguments_cons := by
    intro context state first kind value firstEvents rest kinds outcome restEvents h0 h1
    exact LegacyLeafArguments.cons h0 h1
  statement_declarationFault := by
    intro members module path formals before raw after binding state fault events result declaration h0 h1
    exact LegacyLeafStatement.declarationFault h0 h1
  statement_declarationValue := by
    intro members module path formals before raw after binding state value events next result declaration h0 h1 h2
    exact LegacyLeafStatement.declarationValue h0 h1 h2
  statement_assignmentFault := by
    intro binding name members module path formals before state raw fault events result h0 h1 h2 h3
    exact LegacyLeafStatement.assignmentFault h0 h1 h2 h3
  statement_assignmentValue := by
    intro binding name members module path formals before state raw value events next result h0 h1 h2 h3 h4
    exact LegacyLeafStatement.assignmentValue h0 h1 h2 h3 h4
  statement_returnFault := by
    intro members module path formals before state raw result fault events h0
    exact LegacyLeafStatement.returnFault h0
  statement_returnValue := by
    intro members module path formals before state raw result value events h0
    exact LegacyLeafStatement.returnValue h0
  statement_branchFault := by
    intro members module path formals before body child declaredItems state condition fault events result h0 h1
    exact LegacyLeafStatement.branchFault h0 h1
  statement_branchFalse := by
    intro members module path formals before body child declaredItems state condition events next result h0 h1 h2
    exact LegacyLeafStatement.branchFalse h0 h1 h2
  statement_branchTrueContinue := by
    intro members module path formals before body child declaredItems state condition firstEvents entered result finished bodyEvents next h0 h1 h2 h3 h4
    exact LegacyLeafStatement.branchTrueContinue h0 h1 h2 h3 h4
  statement_branchTrueReturn := by
    intro members module path formals before body child declaredItems state condition firstEvents entered result value finished bodyEvents h0 h1 h2 h3
    exact LegacyLeafStatement.branchTrueReturn h0 h1 h2 h3
  statement_branchTrueFault := by
    intro members module path formals before body child declaredItems state condition firstEvents entered result fault finished bodyEvents h0 h1 h2 h3
    exact LegacyLeafStatement.branchTrueFault h0 h1 h2 h3
  statements_nil := by
    intro members module path formals result before state
    exact LegacyLeafStatements.nil
  statements_next := by
    intro members module path formals result before state first middle next firstEvents rest after outcome restEvents h0 h1
    exact LegacyLeafStatements.next h0 h1
  statements_returned := by
    intro members module path formals result before state first middle value final events rest after declaredItems h0 h1
    exact LegacyLeafStatements.returned h0 h1
  statements_trapped := by
    intro members module path formals result before state first middle fault final events rest after declaredItems h0 h1
    exact LegacyLeafStatements.trapped h0 h1

theorem RuntimeEvaluatesWith.backward
    (evaluated : RuntimeEvaluatesWith functions context state raw kind outcome events) :
    LegacyLeafEvaluation functions context state raw kind outcome events :=
  evaluated.induct (legacyLeafAlgebra functions)

theorem RuntimeArgumentsEvaluateWith.backward
    (evaluated : RuntimeArgumentsEvaluateWith functions context state raws kinds outcome events) :
    LegacyLeafArguments functions context state raws kinds outcome events :=
  evaluated.induct (legacyLeafAlgebra functions)

theorem RuntimeStatementEvaluates.backward
    (evaluated : RuntimeStatementEvaluates functions members module path formals result before state raw after outcome events) :
    LegacyLeafStatement functions members module path formals result before state raw after outcome events :=
  evaluated.induct (legacyLeafAlgebra functions)

theorem RuntimeStatementsEvaluate.backward
    (evaluated : RuntimeStatementsEvaluate functions members module path formals result before state raws after outcome events) :
    LegacyLeafStatements functions members module path formals result before state raws after outcome events :=
  evaluated.induct (legacyLeafAlgebra functions)

theorem legacy_expression_iff :
    LegacyLeafEvaluation functions context state raw kind outcome events ↔
    RuntimeEvaluatesWith functions context state raw kind outcome events :=
  ⟨LegacyLeafEvaluation.forward,RuntimeEvaluatesWith.backward⟩
theorem legacy_arguments_iff :
    LegacyLeafArguments functions context state raws kinds outcome events ↔
    RuntimeArgumentsEvaluateWith functions context state raws kinds outcome events :=
  ⟨LegacyLeafArguments.forward,RuntimeArgumentsEvaluateWith.backward⟩
theorem legacy_statement_iff :
    LegacyLeafStatement functions members module path formals result before state raw after outcome events ↔
    RuntimeStatementEvaluates functions members module path formals result before state raw after outcome events :=
  ⟨LegacyLeafStatement.forward,RuntimeStatementEvaluates.backward⟩
theorem legacy_statements_iff :
    LegacyLeafStatements functions members module path formals result before state raws after outcome events ↔
    RuntimeStatementsEvaluate functions members module path formals result before state raws after outcome events :=
  ⟨LegacyLeafStatements.forward,RuntimeStatementsEvaluate.backward⟩

end Aurora.SourceBinding
