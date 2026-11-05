import SourceBinding.RuntimePureAliases
namespace Aurora.SourceBinding

/-- Constructor closure of the uniform pure specialization, built directly
    from the single effectful judgment. No frozen reference relation is used. -/
theorem pureRuntimeAlgebra (functions : List RuntimeSourceFunction) :
    PureEffectAlgebra functions (PureRuntimeEvaluation functions) (PureRuntimeArgumentEvaluation functions)
      (PureRuntimeStatementEvaluation functions) (PureRuntimeStatementsEvaluation functions) where
  expression_word := by
    intro context state value World ExternalFault response shared
    exact .word
  expression_boolean := by
    intro context state value World ExternalFault response shared
    exact .boolean
  expression_readVariable := by
    intro context name binding state h0 World ExternalFault response shared
    exact .readVariable h0
  expression_enumValue := by
    intro context name identity ordinal state h0 World ExternalFault response shared
    exact .enumValue (.localValue h0)
  expression_not := by
    intro context state inner outcome events h0 World ExternalFault response shared
    have ih0 := h0 World ExternalFault response shared
    simpa only [sourceThen_sourceLift] using EffectEvaluation.not ih0
  expression_wordBinaryFault := by
    intro operator primitive result context state left fault events right h0 h1 World ExternalFault response shared
    have ih1 := h1 World ExternalFault response shared
    exact .wordBinaryStop h0 ih1
  expression_wordBinary := by
    intro operator primitive result context state left value leftEvents right outcome rightEvents h0 h1 h2 World ExternalFault response shared
    have ih1 := h1 World ExternalFault response shared
    have ih2 := h2 World ExternalFault response shared
    simpa only [sourceThen_sourceLift, List.map_append] using EffectEvaluation.wordBinary h0 ih1 ih2
  expression_enumCompareFault := by
    intro context state left identity fault events right equal h0 World ExternalFault response shared
    have ih0 := h0 World ExternalFault response shared
    exact .enumCompareStop ih0
  expression_enumCompare := by
    intro context state left identity value leftEvents right outcome rightEvents equal h0 h1 World ExternalFault response shared
    have ih0 := h0 World ExternalFault response shared
    have ih1 := h1 World ExternalFault response shared
    simpa only [sourceThen_sourceLift, List.map_append] using EffectEvaluation.enumCompare ih0 ih1
  expression_shiftLeft := by
    intro context state left outcome events right count h0 h1 World ExternalFault response shared
    have ih0 := h0 World ExternalFault response shared
    simpa only [sourceThen_sourceLift] using EffectEvaluation.shiftLeft ih0 h1
  expression_shiftRight := by
    intro context state left outcome events right count h0 h1 World ExternalFault response shared
    have ih0 := h0 World ExternalFault response shared
    simpa only [sourceThen_sourceLift] using EffectEvaluation.shiftRight ih0 h1
  expression_andFault := by
    intro context state left fault events right h0 World ExternalFault response shared
    have ih0 := h0 World ExternalFault response shared
    exact .andStopped ih0
  expression_andStop := by
    intro context state left events right h0 World ExternalFault response shared
    have ih0 := h0 World ExternalFault response shared
    exact .andStop ih0
  expression_andContinue := by
    intro context state left leftEvents right outcome rightEvents h0 h1 World ExternalFault response shared
    have ih0 := h0 World ExternalFault response shared
    have ih1 := h1 World ExternalFault response shared
    simpa only [List.map_append] using EffectEvaluation.andContinue ih0 ih1
  expression_orFault := by
    intro context state left fault events right h0 World ExternalFault response shared
    have ih0 := h0 World ExternalFault response shared
    exact .orStopped ih0
  expression_orStop := by
    intro context state left events right h0 World ExternalFault response shared
    have ih0 := h0 World ExternalFault response shared
    exact .orStop ih0
  expression_orContinue := by
    intro context state left leftEvents right outcome rightEvents h0 h1 World ExternalFault response shared
    have ih0 := h0 World ExternalFault response shared
    have ih1 := h1 World ExternalFault response shared
    simpa only [List.map_append] using EffectEvaluation.orContinue ih0 ih1
  expression_callArgumentsFault := by
    intro leaf context name state sources fault events h0 h1 h2 World ExternalFault response shared
    have ih2 := h2 World ExternalFault response shared
    exact .callArgumentsStop (List.mem_map.mpr ⟨_,h0,rfl⟩) ((RuntimeSourceFunction.toEffect_resolves _ _ _).mpr h1) ih2
  expression_callValue := by
    intro leaf context name state sources values argumentEvents after value finished bodyEvents h0 h1 h2 h3 World ExternalFault response shared
    have ih2 := h2 World ExternalFault response shared
    have ih3 := h3 World ExternalFault response shared leaf.context.visible
    simpa only [List.map_append,List.map_cons,List.map_nil,RuntimeSourceEvent.toEffect] using EffectEvaluation.callValue (List.mem_map.mpr ⟨_,h0,rfl⟩) ((RuntimeSourceFunction.toEffect_resolves _ _ _).mpr h1) ih2 ih2.checked ih3
  expression_callFault := by
    intro leaf context name state sources values argumentEvents after fault finished bodyEvents h0 h1 h2 h3 World ExternalFault response shared
    have ih2 := h2 World ExternalFault response shared
    have ih3 := h3 World ExternalFault response shared leaf.context.visible
    simpa only [List.map_append,List.map_cons,List.map_nil,RuntimeSourceEvent.toEffect] using EffectEvaluation.callStop (List.mem_map.mpr ⟨_,h0,rfl⟩) ((RuntimeSourceFunction.toEffect_resolves _ _ _).mpr h1) ih2 ih2.checked ih3
  arguments_nil := by
    intro context state World ExternalFault response shared
    exact .nil
  arguments_fault := by
    intro context state first kind fault events rest kinds h0 World ExternalFault response shared
    have ih0 := h0 World ExternalFault response shared
    exact .stopped ih0
  arguments_cons := by
    intro context state first kind value firstEvents rest kinds outcome restEvents h0 h1 World ExternalFault response shared
    have ih0 := h0 World ExternalFault response shared
    have ih1 := h1 World ExternalFault response shared
    simpa only [effect_prepend_legacy,List.map_append] using EffectArguments.cons ih0 ih1
  statement_declarationFault := by
    intro members module path formals before raw after binding state fault events result declaration h0 h1 World ExternalFault response shared visible
    have ih1 := h1 World ExternalFault response shared
    exact .declarationStop h0 ih1
  statement_declarationValue := by
    intro members module path formals before raw after binding state value events next result declaration h0 h1 h2 World ExternalFault response shared visible
    have ih1 := h1 World ExternalFault response shared
    exact .declarationValue h0 ih1 ih1.outcome_typed h2
  statement_assignmentFault := by
    intro binding name members module path formals before state raw fault events result h0 h1 h2 h3 World ExternalFault response shared visible
    have ih3 := h3 World ExternalFault response shared
    exact .assignmentStop h0 h1 h2 ih3
  statement_assignmentValue := by
    intro binding name members module path formals before state raw value events next result h0 h1 h2 h3 h4 World ExternalFault response shared visible
    have ih3 := h3 World ExternalFault response shared
    exact .assignmentValue h0 h1 h2 ih3 ih3.outcome_typed h4
  statement_returnFault := by
    intro members module path formals before state raw result fault events h0 World ExternalFault response shared visible
    have ih0 := h0 World ExternalFault response shared
    exact .returnStop ih0
  statement_returnValue := by
    intro members module path formals before state raw result value events h0 World ExternalFault response shared visible
    have ih0 := h0 World ExternalFault response shared
    exact .returnValue ih0
  statement_branchFault := by
    intro members module path formals before body child declaredItems state condition fault events result h0 h1 World ExternalFault response shared visible
    have ih1 := h1 World ExternalFault response shared
    exact .branchStop h0 ih1
  statement_branchFalse := by
    intro members module path formals before body child declaredItems state condition events next result h0 h1 h2 World ExternalFault response shared visible
    have ih1 := h1 World ExternalFault response shared
    exact .branchFalse h0 ih1 h2
  statement_branchTrueContinue := by
    intro members module path formals before body child declaredItems state condition firstEvents entered result finished bodyEvents next h0 h1 h2 h3 h4 World ExternalFault response shared visible
    have ih1 := h1 World ExternalFault response shared
    have ih3 := h3 World ExternalFault response shared visible
    simpa only [List.map_append] using EffectStatement.branchTrueContinue h0 ih1 h2 ih3 h4
  statement_branchTrueReturn := by
    intro members module path formals before body child declaredItems state condition firstEvents entered result value finished bodyEvents h0 h1 h2 h3 World ExternalFault response shared visible
    have ih1 := h1 World ExternalFault response shared
    have ih3 := h3 World ExternalFault response shared visible
    simpa only [List.map_append] using EffectStatement.branchTrueReturn h0 ih1 h2 ih3
  statement_branchTrueFault := by
    intro members module path formals before body child declaredItems state condition firstEvents entered result fault finished bodyEvents h0 h1 h2 h3 World ExternalFault response shared visible
    have ih1 := h1 World ExternalFault response shared
    have ih3 := h3 World ExternalFault response shared visible
    simpa only [List.map_append] using EffectStatement.branchTrueStop h0 ih1 h2 ih3
  statements_nil := by
    intro members module path formals result before state World ExternalFault response shared visible
    exact .nil
  statements_next := by
    intro members module path formals result before state first middle next firstEvents rest after outcome restEvents h0 h1 World ExternalFault response shared visible
    have ih0 := h0 World ExternalFault response shared visible
    have ih1 := h1 World ExternalFault response shared visible
    simpa only [List.map_append] using EffectStatements.next ih0 ih1
  statements_returned := by
    intro members module path formals result before state first middle value final events rest after declaredItems h0 h1 World ExternalFault response shared visible
    have ih0 := h0 World ExternalFault response shared visible
    exact .returned ih0 h1
  statements_trapped := by
    intro members module path formals result before state first middle fault final events rest after declaredItems h0 h1 World ExternalFault response shared visible
    have ih0 := h0 World ExternalFault response shared visible
    exact .stopped ih0 h1

abbrev PureRuntimeEvaluation.word {functions : List RuntimeSourceFunction} :=
  @PureEffectAlgebra.expression_word functions _ _ _ _ (pureRuntimeAlgebra functions)
abbrev PureRuntimeEvaluation.boolean {functions : List RuntimeSourceFunction} :=
  @PureEffectAlgebra.expression_boolean functions _ _ _ _ (pureRuntimeAlgebra functions)
abbrev PureRuntimeEvaluation.readVariable {functions : List RuntimeSourceFunction} :=
  @PureEffectAlgebra.expression_readVariable functions _ _ _ _ (pureRuntimeAlgebra functions)
abbrev PureRuntimeEvaluation.enumValue {functions : List RuntimeSourceFunction} :=
  @PureEffectAlgebra.expression_enumValue functions _ _ _ _ (pureRuntimeAlgebra functions)
abbrev PureRuntimeEvaluation.not {functions : List RuntimeSourceFunction} :=
  @PureEffectAlgebra.expression_not functions _ _ _ _ (pureRuntimeAlgebra functions)
abbrev PureRuntimeEvaluation.wordBinaryFault {functions : List RuntimeSourceFunction} :=
  @PureEffectAlgebra.expression_wordBinaryFault functions _ _ _ _ (pureRuntimeAlgebra functions)
abbrev PureRuntimeEvaluation.wordBinary {functions : List RuntimeSourceFunction} :=
  @PureEffectAlgebra.expression_wordBinary functions _ _ _ _ (pureRuntimeAlgebra functions)
abbrev PureRuntimeEvaluation.enumCompareFault {functions : List RuntimeSourceFunction} :=
  @PureEffectAlgebra.expression_enumCompareFault functions _ _ _ _ (pureRuntimeAlgebra functions)
abbrev PureRuntimeEvaluation.enumCompare {functions : List RuntimeSourceFunction} :=
  @PureEffectAlgebra.expression_enumCompare functions _ _ _ _ (pureRuntimeAlgebra functions)
abbrev PureRuntimeEvaluation.shiftLeft {functions : List RuntimeSourceFunction} :=
  @PureEffectAlgebra.expression_shiftLeft functions _ _ _ _ (pureRuntimeAlgebra functions)
abbrev PureRuntimeEvaluation.shiftRight {functions : List RuntimeSourceFunction} :=
  @PureEffectAlgebra.expression_shiftRight functions _ _ _ _ (pureRuntimeAlgebra functions)
abbrev PureRuntimeEvaluation.andFault {functions : List RuntimeSourceFunction} :=
  @PureEffectAlgebra.expression_andFault functions _ _ _ _ (pureRuntimeAlgebra functions)
abbrev PureRuntimeEvaluation.andStop {functions : List RuntimeSourceFunction} :=
  @PureEffectAlgebra.expression_andStop functions _ _ _ _ (pureRuntimeAlgebra functions)
abbrev PureRuntimeEvaluation.andContinue {functions : List RuntimeSourceFunction} :=
  @PureEffectAlgebra.expression_andContinue functions _ _ _ _ (pureRuntimeAlgebra functions)
abbrev PureRuntimeEvaluation.orFault {functions : List RuntimeSourceFunction} :=
  @PureEffectAlgebra.expression_orFault functions _ _ _ _ (pureRuntimeAlgebra functions)
abbrev PureRuntimeEvaluation.orStop {functions : List RuntimeSourceFunction} :=
  @PureEffectAlgebra.expression_orStop functions _ _ _ _ (pureRuntimeAlgebra functions)
abbrev PureRuntimeEvaluation.orContinue {functions : List RuntimeSourceFunction} :=
  @PureEffectAlgebra.expression_orContinue functions _ _ _ _ (pureRuntimeAlgebra functions)
abbrev PureRuntimeEvaluation.callArgumentsFault {functions : List RuntimeSourceFunction} :=
  @PureEffectAlgebra.expression_callArgumentsFault functions _ _ _ _ (pureRuntimeAlgebra functions)
abbrev PureRuntimeEvaluation.callValue {functions : List RuntimeSourceFunction} :=
  @PureEffectAlgebra.expression_callValue functions _ _ _ _ (pureRuntimeAlgebra functions)
abbrev PureRuntimeEvaluation.callFault {functions : List RuntimeSourceFunction} :=
  @PureEffectAlgebra.expression_callFault functions _ _ _ _ (pureRuntimeAlgebra functions)
abbrev PureRuntimeArgumentEvaluation.nil {functions : List RuntimeSourceFunction} :=
  @PureEffectAlgebra.arguments_nil functions _ _ _ _ (pureRuntimeAlgebra functions)
abbrev PureRuntimeArgumentEvaluation.fault {functions : List RuntimeSourceFunction} :=
  @PureEffectAlgebra.arguments_fault functions _ _ _ _ (pureRuntimeAlgebra functions)
abbrev PureRuntimeArgumentEvaluation.cons {functions : List RuntimeSourceFunction} :=
  @PureEffectAlgebra.arguments_cons functions _ _ _ _ (pureRuntimeAlgebra functions)
abbrev PureRuntimeStatementEvaluation.declarationFault {functions : List RuntimeSourceFunction} :=
  @PureEffectAlgebra.statement_declarationFault functions _ _ _ _ (pureRuntimeAlgebra functions)
abbrev PureRuntimeStatementEvaluation.declarationValue {functions : List RuntimeSourceFunction} :=
  @PureEffectAlgebra.statement_declarationValue functions _ _ _ _ (pureRuntimeAlgebra functions)
abbrev PureRuntimeStatementEvaluation.assignmentFault {functions : List RuntimeSourceFunction} :=
  @PureEffectAlgebra.statement_assignmentFault functions _ _ _ _ (pureRuntimeAlgebra functions)
abbrev PureRuntimeStatementEvaluation.assignmentValue {functions : List RuntimeSourceFunction} :=
  @PureEffectAlgebra.statement_assignmentValue functions _ _ _ _ (pureRuntimeAlgebra functions)
abbrev PureRuntimeStatementEvaluation.returnFault {functions : List RuntimeSourceFunction} :=
  @PureEffectAlgebra.statement_returnFault functions _ _ _ _ (pureRuntimeAlgebra functions)
abbrev PureRuntimeStatementEvaluation.returnValue {functions : List RuntimeSourceFunction} :=
  @PureEffectAlgebra.statement_returnValue functions _ _ _ _ (pureRuntimeAlgebra functions)
abbrev PureRuntimeStatementEvaluation.branchFault {functions : List RuntimeSourceFunction} :=
  @PureEffectAlgebra.statement_branchFault functions _ _ _ _ (pureRuntimeAlgebra functions)
abbrev PureRuntimeStatementEvaluation.branchFalse {functions : List RuntimeSourceFunction} :=
  @PureEffectAlgebra.statement_branchFalse functions _ _ _ _ (pureRuntimeAlgebra functions)
abbrev PureRuntimeStatementEvaluation.branchTrueContinue {functions : List RuntimeSourceFunction} :=
  @PureEffectAlgebra.statement_branchTrueContinue functions _ _ _ _ (pureRuntimeAlgebra functions)
abbrev PureRuntimeStatementEvaluation.branchTrueReturn {functions : List RuntimeSourceFunction} :=
  @PureEffectAlgebra.statement_branchTrueReturn functions _ _ _ _ (pureRuntimeAlgebra functions)
abbrev PureRuntimeStatementEvaluation.branchTrueFault {functions : List RuntimeSourceFunction} :=
  @PureEffectAlgebra.statement_branchTrueFault functions _ _ _ _ (pureRuntimeAlgebra functions)
abbrev PureRuntimeStatementsEvaluation.nil {functions : List RuntimeSourceFunction} :=
  @PureEffectAlgebra.statements_nil functions _ _ _ _ (pureRuntimeAlgebra functions)
abbrev PureRuntimeStatementsEvaluation.next {functions : List RuntimeSourceFunction} :=
  @PureEffectAlgebra.statements_next functions _ _ _ _ (pureRuntimeAlgebra functions)
abbrev PureRuntimeStatementsEvaluation.returned {functions : List RuntimeSourceFunction} :=
  @PureEffectAlgebra.statements_returned functions _ _ _ _ (pureRuntimeAlgebra functions)
abbrev PureRuntimeStatementsEvaluation.trapped {functions : List RuntimeSourceFunction} :=
  @PureEffectAlgebra.statements_trapped functions _ _ _ _ (pureRuntimeAlgebra functions)

end Aurora.SourceBinding
