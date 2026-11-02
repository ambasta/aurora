import SourceBinding.RuntimeBodyPrimitive
import SourceBinding.RuntimeUniformExpression
namespace Aurora.SourceBinding

def RuntimeUniformStatement (program : CallProgram) (caller : Int)
    (leaves : List (RuntimeCallable t files root module path))
    (members : List Declaration) (formals : List Formal) (result : RuntimeType)
    (before : LocalContext) (raw : SourceStatement) (after : LocalContext) (start stop : Nat)
    (World ExternalFault : Type) : Prop :=
  ∀ source ancestors, RuntimeStateAt members module path formals before ancestors source →
    ∃ outcome sourceEvents machineEvents,
      RuntimeStatementEvaluation (leaves.map RuntimeCallable.source) members module path formals result before source raw after outcome sourceEvents ∧
      RuntimeCallTraceRelated leaves sourceEvents machineEvents ∧
      RuntimeContinuationAt members module path formals after ancestors outcome ∧
      ∀ (base : Machine) (saved : List SavedCall) (world : World) (external : ExternalRelation World ExternalFault)
        accumulator, RuntimeBodyRun program external caller saved world base source start stop accumulator outcome machineEvents

def RuntimeUniformStatements (program : CallProgram) (caller : Int)
    (leaves : List (RuntimeCallable t files root module path))
    (members : List Declaration) (formals : List Formal) (result : RuntimeType)
    (before : LocalContext) (raw : List SourceStatement) (after : LocalContext) (start stop : Nat)
    (World ExternalFault : Type) : Prop :=
  ∀ source ancestors, RuntimeStateAt members module path formals before ancestors source →
    ∃ outcome sourceEvents machineEvents,
      RuntimeStatementsEvaluation (leaves.map RuntimeCallable.source) members module path formals result before source raw after outcome sourceEvents ∧
      RuntimeCallTraceRelated leaves sourceEvents machineEvents ∧
      RuntimeContinuationAt members module path formals after ancestors outcome ∧
      ∀ (base : Machine) (saved : List SavedCall) (world : World) (external : ExternalRelation World ExternalFault)
        accumulator, RuntimeBodyRun program external caller saved world base source start stop accumulator outcome machineEvents

end Aurora.SourceBinding
