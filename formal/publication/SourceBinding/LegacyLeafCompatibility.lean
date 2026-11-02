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

theorem RuntimeEvaluatesWith.backward
    (evaluated : RuntimeEvaluatesWith functions context state raw kind outcome events) :
    LegacyLeafEvaluation functions context state raw kind outcome events := by
  induction evaluated using RuntimeEvaluation.rec
      (motive_2 := fun context state raws kinds outcome events _ =>
        LegacyLeafArguments functions context state raws kinds outcome events)
      (motive_3 := fun members module path formals result before state raw after outcome events _ =>
        LegacyLeafStatement functions members module path formals result before state raw after outcome events)
      (motive_4 := fun members module path formals result before state raws after outcome events _ =>
        LegacyLeafStatements functions members module path formals result before state raws after outcome events) with
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
  | callArgumentsFault member resolves _ ih =>
    obtain ⟨leaf,oldMember,equal⟩ := List.mem_map.mp member
    cases equal
    exact .callArgumentsFault oldMember resolves ih
  | callValue member resolves _ _ args body =>
    obtain ⟨leaf,oldMember,equal⟩ := List.mem_map.mp member
    cases equal
    simp only [RuntimeSourceLeaf.toFunction] at body
    rw [leaf.singleton] at body
    have old := (legacy_singleton_return_iff.mp body).2.2
    exact .callValue oldMember resolves args (by simpa only [leaf.initial_context] using old)
  | callFault member resolves _ _ args body =>
    obtain ⟨leaf,oldMember,equal⟩ := List.mem_map.mp member
    cases equal
    simp only [RuntimeSourceLeaf.toFunction] at body
    rw [leaf.singleton] at body
    have old := (legacy_singleton_trap_iff.mp body).2.2
    exact .callFault oldMember resolves args (by simpa only [leaf.initial_context] using old)
  | fault _ ih => exact .fault ih
  | cons _ _ first rest => exact .cons first rest
  | declarationFault scope expression ih => exact .declarationFault scope ih
  | declarationValue scope expression initialized ih => exact .declarationValue scope ih initialized
  | assignmentFault member named mutable expression ih => exact .assignmentFault member named mutable ih
  | assignmentValue member named mutable expression assigned ih => exact .assignmentValue member named mutable ih assigned
  | returnFault expression ih => exact .returnFault ih
  | returnValue expression ih => exact .returnValue ih
  | branchFault scope expression ih => exact .branchFault scope ih
  | branchFalse scope expression reserved ih => exact .branchFalse scope ih reserved
  | branchTrueContinue scope expression entered body reserved first ih =>
      exact .branchTrueContinue scope first entered ih reserved
  | branchTrueReturn scope expression entered body first ih => exact .branchTrueReturn scope first entered ih
  | branchTrueFault scope expression entered body first ih => exact .branchTrueFault scope first entered ih
  | next first rest ih tail => exact .next ih tail
  | returned first scope ih => exact .returned ih scope
  | trapped first scope ih => exact .trapped ih scope

  | _ => exact .nil

theorem RuntimeArgumentsEvaluateWith.backward
    (evaluated : RuntimeArgumentsEvaluateWith functions context state raws kinds outcome events) :
    LegacyLeafArguments functions context state raws kinds outcome events := by
  induction evaluated using RuntimeArgumentEvaluation.rec
      (motive_1 := fun _ _ _ _ _ _ _ => True)
      (motive_3 := fun _ _ _ _ _ _ _ _ _ _ _ _ => True)
      (motive_4 := fun _ _ _ _ _ _ _ _ _ _ _ _ => True) with
  | fault first _ => exact .fault (RuntimeEvaluatesWith.backward first)
  | cons first rest _ ih => exact .cons (RuntimeEvaluatesWith.backward first) ih
  | _ => all_goals first | exact True.intro | exact LegacyLeafArguments.nil | exact LegacyLeafStatements.nil

theorem RuntimeStatementEvaluates.backward
    (evaluated : RuntimeStatementEvaluates functions members module path formals result before state raw after outcome events) :
    LegacyLeafStatement functions members module path formals result before state raw after outcome events := by
  induction evaluated using RuntimeStatementEvaluation.rec
      (motive_1 := fun _ _ _ _ _ _ _ => True)
      (motive_2 := fun _ _ _ _ _ _ _ => True)
      (motive_4 := fun members module path formals result before state raws after outcome events _ =>
        LegacyLeafStatements functions members module path formals result before state raws after outcome events) with
  | declarationFault scope expression _ => exact .declarationFault scope (RuntimeEvaluatesWith.backward expression)
  | declarationValue scope expression initialized _ => exact .declarationValue scope (RuntimeEvaluatesWith.backward expression) initialized
  | assignmentFault member named mutable expression _ => exact .assignmentFault member named mutable (RuntimeEvaluatesWith.backward expression)
  | assignmentValue member named mutable expression assigned _ => exact .assignmentValue member named mutable (RuntimeEvaluatesWith.backward expression) assigned
  | returnFault expression _ => exact .returnFault (RuntimeEvaluatesWith.backward expression)
  | returnValue expression _ => exact .returnValue (RuntimeEvaluatesWith.backward expression)
  | branchFault scope expression _ => exact .branchFault scope (RuntimeEvaluatesWith.backward expression)
  | branchFalse scope expression reserved _ => exact .branchFalse scope (RuntimeEvaluatesWith.backward expression) reserved
  | branchTrueContinue scope expression entered body reserved _ ih =>
      exact .branchTrueContinue scope (RuntimeEvaluatesWith.backward expression) entered ih reserved
  | branchTrueReturn scope expression entered body _ ih => exact .branchTrueReturn scope (RuntimeEvaluatesWith.backward expression) entered ih
  | branchTrueFault scope expression entered body _ ih => exact .branchTrueFault scope (RuntimeEvaluatesWith.backward expression) entered ih
  | next first rest ih tail => exact .next ih tail
  | returned first scope ih => exact .returned ih scope
  | trapped first scope ih => exact .trapped ih scope
  | _ => all_goals first | exact True.intro | exact LegacyLeafArguments.nil | exact LegacyLeafStatements.nil

theorem RuntimeStatementsEvaluate.backward
    (evaluated : RuntimeStatementsEvaluate functions members module path formals result before state raws after outcome events) :
    LegacyLeafStatements functions members module path formals result before state raws after outcome events := by
  induction evaluated using RuntimeStatementsEvaluation.rec
      (motive_1 := fun _ _ _ _ _ _ _ => True)
      (motive_2 := fun _ _ _ _ _ _ _ => True)
      (motive_3 := fun _ _ _ _ _ _ _ _ _ _ _ _ => True) with
  | next first rest _ ih => exact .next (RuntimeStatementEvaluates.backward first) ih
  | returned first scope _ => exact .returned (RuntimeStatementEvaluates.backward first) scope
  | trapped first scope _ => exact .trapped (RuntimeStatementEvaluates.backward first) scope
  | _ => all_goals first | exact True.intro | exact LegacyLeafArguments.nil | exact LegacyLeafStatements.nil

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
