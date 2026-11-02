import SourceBinding.RuntimeCallCode
import SourceBinding.RuntimeScopeReservation
namespace Aurora.SourceBinding

/-- Consecutive administrative labels only; no arbitrary instruction can be
    hidden in a branch join or in a syntactically unreachable suffix. -/
inductive RuntimeLabelRun (program : CallProgram) (caller : Int) : Nat → Nat → Prop
  | nil : RuntimeLabelRun program caller pc pc
  | cons : localProgram program caller pc = some (.pure .label) →
      RuntimeLabelRun program caller (pc + 1) stop → RuntimeLabelRun program caller pc stop

/-- Independent syntactic absence of normal fallthrough. A one-arm conditional
    alone does not establish this property. This says nothing about success. -/
inductive RuntimeNoFallthrough : List SourceStatement → Prop
  | returned : RuntimeNoFallthrough (.returnValue value :: rest)
  | later : RuntimeNoFallthrough rest → RuntimeNoFallthrough (first :: rest)

mutual
inductive RuntimeStatementCode (program : CallProgram) (caller : Int)
    (leaves : List (RuntimeCallLeaf t files root module path))
    (members : List Declaration) (formals : List Formal) (result : RuntimeType) :
    LocalContext → SourceStatement → LocalContext → List SourceLocal → Nat → Nat → Prop
  | declare {declaration : Formal} :
      ScopedStatement members module path formals before (.localDecl declaration value)
        (addLocal before (declaredLocal before declaration.name kind mutable))
        [declaredLocal before declaration.name kind mutable] →
      RuntimeContextValid (runtimeStatementContext members module path formals before) →
      RuntimeCallExpressionCode program caller leaves
        (runtimeStatementContext members module path formals before) value kind start middle →
      localProgram program caller middle = some (.localStore kind (8 * (before.nextSlot + 1))) →
      RuntimeStatementCode program caller leaves members formals result before (.localDecl declaration value)
        (addLocal before (declaredLocal before declaration.name kind mutable))
        [declaredLocal before declaration.name kind mutable] start (middle + 1)
  | assign : ScopedStatement members module path formals before (.assign name value) before [] →
      binding ∈ before.visible → binding.name = name → binding.mutable = true →
      RuntimeContextValid (runtimeStatementContext members module path formals before) →
      RuntimeCallExpressionCode program caller leaves
        (runtimeStatementContext members module path formals before) value binding.kind start middle →
      localProgram program caller middle = some (.localStore binding.kind binding.slot) →
      RuntimeStatementCode program caller leaves members formals result before (.assign name value)
        before [] start (middle + 1)
  | returned : ScopedStatement members module path formals before (.returnValue value) before [] →
      RuntimeContextValid (runtimeStatementContext members module path formals before) →
      RuntimeCallExpressionCode program caller leaves
        (runtimeStatementContext members module path formals before) value result start middle →
      localProgram program caller middle = some (.pure .ret) →
      RuntimeStatementCode program caller leaves members formals result before (.returnValue value)
        before [] start (middle + 1)
  | branchLinear : ScopedStatement members module path formals before (.ifThen condition body)
        (leaveLocalScope before child) declaredItems →
      RuntimeContextValid (runtimeStatementContext members module path formals before) →
      RuntimeCallExpressionCode program caller leaves
        (runtimeStatementContext members module path formals before) condition (.scalar .boolean) start conditionEnd →
      localProgram program caller conditionEnd = some (.pure (.branchFalse falsePC)) →
      RuntimeStatementsCode program caller leaves members formals result (enterLocalScope before)
        body child declaredItems (conditionEnd + 1) falsePC →
      falsePC < stop → RuntimeLabelRun program caller falsePC stop →
      RuntimeStatementCode program caller leaves members formals result before (.ifThen condition body)
        (leaveLocalScope before child) declaredItems start stop
  | branchJoined : ScopedStatement members module path formals before (.ifThen condition body)
        (leaveLocalScope before child) declaredItems →
      RuntimeContextValid (runtimeStatementContext members module path formals before) →
      RuntimeCallExpressionCode program caller leaves
        (runtimeStatementContext members module path formals before) condition (.scalar .boolean) start conditionEnd →
      localProgram program caller conditionEnd = some (.pure (.branchFalse (bodyEnd + 1))) →
      RuntimeStatementsCode program caller leaves members formals result (enterLocalScope before)
        body child declaredItems (conditionEnd + 1) bodyEnd →
      localProgram program caller bodyEnd = some (.pure (.jump joinPC)) →
      bodyEnd + 1 ≤ joinPC → joinPC < stop → RuntimeLabelRun program caller (bodyEnd + 1) stop →
      RuntimeStatementCode program caller leaves members formals result before (.ifThen condition body)
        (leaveLocalScope before child) declaredItems start stop

inductive RuntimeStatementsCode (program : CallProgram) (caller : Int)
    (leaves : List (RuntimeCallLeaf t files root module path))
    (members : List Declaration) (formals : List Formal) (result : RuntimeType) :
    LocalContext → List SourceStatement → LocalContext → List SourceLocal → Nat → Nat → Prop
  | nil : RuntimeStatementsCode program caller leaves members formals result before [] before [] pc pc
  | cons : RuntimeStatementCode program caller leaves members formals result before first middle declaredItems start next →
      RuntimeStatementsCode program caller leaves members formals result middle rest after remaining next stop →
      RuntimeStatementsCode program caller leaves members formals result before (first :: rest) after
        (declaredItems ++ remaining) start stop
end

end Aurora.SourceBinding
