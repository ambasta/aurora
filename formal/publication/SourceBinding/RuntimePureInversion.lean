import SourceBinding.RuntimeEvaluation
namespace Aurora.SourceBinding

private def CallCases (functions : List RuntimeSourceFunction) (context : RuntimeExprContext)
    (state : RuntimeLocals) (raw : SourceExpr) (kind : RuntimeType)
    (outcome : Outcome Value) (events : List RuntimeSourceEvent) : Prop :=
  ∀ name arguments, raw = .call (.named name) arguments →
    ∃ callee ∈ functions, callee.Resolves context name ∧ kind = callee.result ∧
      ((∃ fault, outcome = .trap fault ∧
          RuntimeArgumentEvaluation functions context state arguments callee.parameters (.trap fault) events) ∨
       (∃ values argumentEvents after finished bodyEvents value,
          RuntimeArgumentEvaluation functions context state arguments callee.parameters (.value values) argumentEvents ∧
          RuntimeStatementsEvaluation functions callee.context.members callee.context.module callee.context.path
            callee.context.formals callee.result ⟨[],0,1,callee.context.formals.length⟩
            (formalSourceLocals callee.parameters (fun index => values[index]?))
            callee.parsed.statements after (.returned value finished) bodyEvents ∧
          outcome = .value value ∧ events = argumentEvents ++ [.invoke callee.key values] ++ bodyEvents ++ [.returned callee.key value]) ∨
       (∃ values argumentEvents after finished bodyEvents fault,
          RuntimeArgumentEvaluation functions context state arguments callee.parameters (.value values) argumentEvents ∧
          RuntimeStatementsEvaluation functions callee.context.members callee.context.module callee.context.path
            callee.context.formals callee.result ⟨[],0,1,callee.context.formals.length⟩
            (formalSourceLocals callee.parameters (fun index => values[index]?))
            callee.parsed.statements after (.trapped fault finished) bodyEvents ∧
          outcome = .trap fault ∧ events = argumentEvents ++ [.invoke callee.key values] ++ bodyEvents))

private def ConsCases (functions : List RuntimeSourceFunction)
    (members : List Declaration) (module path : Name) (formals : List Formal) (result : RuntimeType)
    (before : LocalContext) (state : RuntimeLocals) (raws : List SourceStatement) (after : LocalContext)
    (outcome : RuntimeBodyOutcome) (events : List RuntimeSourceEvent) : Prop :=
  ∀ first rest, raws = first :: rest →
    (∃ middle next firstEvents restEvents,
      RuntimeStatementEvaluation functions members module path formals result before state first middle (.continued next) firstEvents ∧
      RuntimeStatementsEvaluation functions members module path formals result middle next rest after outcome restEvents ∧
      events = firstEvents ++ restEvents) ∨
    (∃ middle value finished items,
      RuntimeStatementEvaluation functions members module path formals result before state first middle (.returned value finished) events ∧
      ScopedStatements members module path formals middle rest after items ∧ outcome = .returned value finished) ∨
    (∃ middle fault finished items,
      RuntimeStatementEvaluation functions members module path formals result before state first middle (.trapped fault finished) events ∧
      ScopedStatements members module path formals middle rest after items ∧ outcome = .trapped fault finished)

private theorem inversionAlgebra (functions : List RuntimeSourceFunction) :
    PureEffectAlgebra functions
      (fun context state raw kind outcome events =>
        RuntimeEvaluation functions context state raw kind outcome events ∧ CallCases functions context state raw kind outcome events)
      (RuntimeArgumentEvaluation functions) (RuntimeStatementEvaluation functions)
      (fun members module path formals result before state raws after outcome events =>
        RuntimeStatementsEvaluation functions members module path formals result before state raws after outcome events ∧
        ConsCases functions members module path formals result before state raws after outcome events) where
  expression_word := by
    intro context state value
    refine ⟨(pureRuntimeAlgebra functions).expression_word ,?_⟩
    intro actualName actualArgs same
    cases same
  expression_boolean := by
    intro context state value
    refine ⟨(pureRuntimeAlgebra functions).expression_boolean ,?_⟩
    intro actualName actualArgs same
    cases same
  expression_readVariable := by
    intro context name binding state h0
    refine ⟨(pureRuntimeAlgebra functions).expression_readVariable h0,?_⟩
    intro actualName actualArgs same
    cases same
  expression_enumValue := by
    intro context name identity ordinal state h0
    refine ⟨(pureRuntimeAlgebra functions).expression_enumValue h0,?_⟩
    intro actualName actualArgs same
    cases same
  expression_not := by
    intro context state inner outcome events h0
    refine ⟨(pureRuntimeAlgebra functions).expression_not h0.1,?_⟩
    intro actualName actualArgs same
    cases same
  expression_wordBinaryFault := by
    intro operator primitive result context state left fault events right h0 h1
    refine ⟨(pureRuntimeAlgebra functions).expression_wordBinaryFault h0 h1.1,?_⟩
    intro actualName actualArgs same
    cases same
  expression_wordBinary := by
    intro operator primitive result context state left value leftEvents right outcome rightEvents h0 h1 h2
    refine ⟨(pureRuntimeAlgebra functions).expression_wordBinary h0 h1.1 h2.1,?_⟩
    intro actualName actualArgs same
    cases same
  expression_enumCompareFault := by
    intro context state left identity fault events right equal h0
    refine ⟨(pureRuntimeAlgebra functions).expression_enumCompareFault h0.1,?_⟩
    intro actualName actualArgs same
    cases same
  expression_enumCompare := by
    intro context state left identity value leftEvents right outcome rightEvents equal h0 h1
    refine ⟨(pureRuntimeAlgebra functions).expression_enumCompare h0.1 h1.1,?_⟩
    intro actualName actualArgs same
    cases same
  expression_shiftLeft := by
    intro context state left outcome events right count h0 h1
    refine ⟨(pureRuntimeAlgebra functions).expression_shiftLeft h0.1 h1,?_⟩
    intro actualName actualArgs same
    cases same
  expression_shiftRight := by
    intro context state left outcome events right count h0 h1
    refine ⟨(pureRuntimeAlgebra functions).expression_shiftRight h0.1 h1,?_⟩
    intro actualName actualArgs same
    cases same
  expression_andFault := by
    intro context state left fault events right h0
    refine ⟨(pureRuntimeAlgebra functions).expression_andFault h0.1,?_⟩
    intro actualName actualArgs same
    cases same
  expression_andStop := by
    intro context state left events right h0
    refine ⟨(pureRuntimeAlgebra functions).expression_andStop h0.1,?_⟩
    intro actualName actualArgs same
    cases same
  expression_andContinue := by
    intro context state left leftEvents right outcome rightEvents h0 h1
    refine ⟨(pureRuntimeAlgebra functions).expression_andContinue h0.1 h1.1,?_⟩
    intro actualName actualArgs same
    cases same
  expression_orFault := by
    intro context state left fault events right h0
    refine ⟨(pureRuntimeAlgebra functions).expression_orFault h0.1,?_⟩
    intro actualName actualArgs same
    cases same
  expression_orStop := by
    intro context state left events right h0
    refine ⟨(pureRuntimeAlgebra functions).expression_orStop h0.1,?_⟩
    intro actualName actualArgs same
    cases same
  expression_orContinue := by
    intro context state left leftEvents right outcome rightEvents h0 h1
    refine ⟨(pureRuntimeAlgebra functions).expression_orContinue h0.1 h1.1,?_⟩
    intro actualName actualArgs same
    cases same
  expression_callArgumentsFault := by
    intro leaf context name state sources fault events h0 h1 h2
    refine ⟨(pureRuntimeAlgebra functions).expression_callArgumentsFault h0 h1 h2,?_⟩
    intro actualName actualArgs same
    cases same
    exact ⟨_,h0,h1,rfl,Or.inl ⟨_,rfl,h2⟩⟩
  expression_callValue := by
    intro leaf context name state sources values argumentEvents after value finished bodyEvents h0 h1 h2 h3
    refine ⟨(pureRuntimeAlgebra functions).expression_callValue h0 h1 h2 h3.1,?_⟩
    intro actualName actualArgs same
    cases same
    exact ⟨_,h0,h1,rfl,Or.inr (Or.inl ⟨_,_,_,_,_,_,h2,h3.1,rfl,rfl⟩)⟩
  expression_callFault := by
    intro leaf context name state sources values argumentEvents after fault finished bodyEvents h0 h1 h2 h3
    refine ⟨(pureRuntimeAlgebra functions).expression_callFault h0 h1 h2 h3.1,?_⟩
    intro actualName actualArgs same
    cases same
    exact ⟨_,h0,h1,rfl,Or.inr (Or.inr ⟨_,_,_,_,_,_,h2,h3.1,rfl,rfl⟩)⟩
  arguments_nil := by
    intro context state
    exact (pureRuntimeAlgebra functions).arguments_nil
  arguments_fault := by
    intro context state first kind fault events rest kinds h0
    exact (pureRuntimeAlgebra functions).arguments_fault h0.1
  arguments_cons := by
    intro context state first kind value firstEvents rest kinds outcome restEvents h0 h1
    exact (pureRuntimeAlgebra functions).arguments_cons h0.1 h1
  statement_declarationFault := by
    intro members module path formals before raw after binding state fault events result declaration h0 h1
    exact (pureRuntimeAlgebra functions).statement_declarationFault h0 h1.1
  statement_declarationValue := by
    intro members module path formals before raw after binding state value events next result declaration h0 h1 h2
    exact (pureRuntimeAlgebra functions).statement_declarationValue h0 h1.1 h2
  statement_assignmentFault := by
    intro binding name members module path formals before state raw fault events result h0 h1 h2 h3
    exact (pureRuntimeAlgebra functions).statement_assignmentFault h0 h1 h2 h3.1
  statement_assignmentValue := by
    intro binding name members module path formals before state raw value events next result h0 h1 h2 h3 h4
    exact (pureRuntimeAlgebra functions).statement_assignmentValue h0 h1 h2 h3.1 h4
  statement_returnFault := by
    intro members module path formals before state raw result fault events h0
    exact (pureRuntimeAlgebra functions).statement_returnFault h0.1
  statement_returnValue := by
    intro members module path formals before state raw result value events h0
    exact (pureRuntimeAlgebra functions).statement_returnValue h0.1
  statement_branchFault := by
    intro members module path formals before body child declaredItems state condition fault events result h0 h1
    exact (pureRuntimeAlgebra functions).statement_branchFault h0 h1.1
  statement_branchFalse := by
    intro members module path formals before body child declaredItems state condition events next result h0 h1 h2
    exact (pureRuntimeAlgebra functions).statement_branchFalse h0 h1.1 h2
  statement_branchTrueContinue := by
    intro members module path formals before body child declaredItems state condition firstEvents entered result finished bodyEvents next h0 h1 h2 h3 h4
    exact (pureRuntimeAlgebra functions).statement_branchTrueContinue h0 h1.1 h2 h3.1 h4
  statement_branchTrueReturn := by
    intro members module path formals before body child declaredItems state condition firstEvents entered result value finished bodyEvents h0 h1 h2 h3
    exact (pureRuntimeAlgebra functions).statement_branchTrueReturn h0 h1.1 h2 h3.1
  statement_branchTrueFault := by
    intro members module path formals before body child declaredItems state condition firstEvents entered result fault finished bodyEvents h0 h1 h2 h3
    exact (pureRuntimeAlgebra functions).statement_branchTrueFault h0 h1.1 h2 h3.1
  statements_nil := by
    intro members module path formals result before state
    refine ⟨(pureRuntimeAlgebra functions).statements_nil ,?_⟩
    intro actualFirst actualRest same
    cases same
  statements_next := by
    intro members module path formals result before state first middle next firstEvents rest after outcome restEvents h0 h1
    refine ⟨(pureRuntimeAlgebra functions).statements_next h0 h1.1,?_⟩
    intro actualFirst actualRest same
    cases same
    exact Or.inl ⟨_,_,_,_,h0,h1.1,rfl⟩
  statements_returned := by
    intro members module path formals result before state first middle value final events rest after declaredItems h0 h1
    refine ⟨(pureRuntimeAlgebra functions).statements_returned h0 h1,?_⟩
    intro actualFirst actualRest same
    cases same
    exact Or.inr (Or.inl ⟨_,_,_,_,h0,h1,rfl⟩)
  statements_trapped := by
    intro members module path formals result before state first middle fault final events rest after declaredItems h0 h1
    refine ⟨(pureRuntimeAlgebra functions).statements_trapped h0 h1,?_⟩
    intro actualFirst actualRest same
    cases same
    exact Or.inr (Or.inr ⟨_,_,_,_,h0,h1,rfl⟩)

theorem PureRuntimeEvaluation.call_cases
    (evaluated : RuntimeEvaluation functions context state (.call (.named name) arguments) kind outcome events) :
    ∃ callee ∈ functions, callee.Resolves context name ∧ kind = callee.result ∧
      ((∃ fault, outcome = .trap fault ∧
          RuntimeArgumentEvaluation functions context state arguments callee.parameters (.trap fault) events) ∨
       (∃ values argumentEvents after finished bodyEvents value,
          RuntimeArgumentEvaluation functions context state arguments callee.parameters (.value values) argumentEvents ∧
          RuntimeStatementsEvaluation functions callee.context.members callee.context.module callee.context.path
            callee.context.formals callee.result ⟨[],0,1,callee.context.formals.length⟩
            (formalSourceLocals callee.parameters (fun index => values[index]?))
            callee.parsed.statements after (.returned value finished) bodyEvents ∧
          outcome = .value value ∧ events = argumentEvents ++ [.invoke callee.key values] ++ bodyEvents ++ [.returned callee.key value]) ∨
       (∃ values argumentEvents after finished bodyEvents fault,
          RuntimeArgumentEvaluation functions context state arguments callee.parameters (.value values) argumentEvents ∧
          RuntimeStatementsEvaluation functions callee.context.members callee.context.module callee.context.path
            callee.context.formals callee.result ⟨[],0,1,callee.context.formals.length⟩
            (formalSourceLocals callee.parameters (fun index => values[index]?))
            callee.parsed.statements after (.trapped fault finished) bodyEvents ∧
          outcome = .trap fault ∧ events = argumentEvents ++ [.invoke callee.key values] ++ bodyEvents)) :=
  (evaluated.induct (inversionAlgebra functions)).2 name arguments rfl

theorem PureRuntimeStatementsEvaluation.cons_cases
    (evaluated : RuntimeStatementsEvaluation functions members module path formals result
      before state (first :: rest) after outcome events) :
    (∃ middle next firstEvents restEvents,
      RuntimeStatementEvaluation functions members module path formals result before state first middle (.continued next) firstEvents ∧
      RuntimeStatementsEvaluation functions members module path formals result middle next rest after outcome restEvents ∧
      events = firstEvents ++ restEvents) ∨
    (∃ middle value finished items,
      RuntimeStatementEvaluation functions members module path formals result before state first middle (.returned value finished) events ∧
      ScopedStatements members module path formals middle rest after items ∧ outcome = .returned value finished) ∨
    (∃ middle fault finished items,
      RuntimeStatementEvaluation functions members module path formals result before state first middle (.trapped fault finished) events ∧
      ScopedStatements members module path formals middle rest after items ∧ outcome = .trapped fault finished) :=
  (evaluated.induct (inversionAlgebra functions)).2 first rest rfl

end Aurora.SourceBinding
