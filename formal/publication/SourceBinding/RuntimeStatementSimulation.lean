import SourceBinding.RuntimeBodyPrimitive
import SourceBinding.RuntimeCallTrace
namespace Aurora.SourceBinding

def RuntimeStatementSimulates (program : CallProgram) (caller : Int)
    (leaves : List (RuntimeCallLeaf t files root module path))
    (members : List Declaration) (formals : List Formal) (result : RuntimeType)
    (before : LocalContext) (raw : SourceStatement) (after : LocalContext) (start stop : Nat)
    (base : Machine) (saved : List SavedCall) (world : World) (external : ExternalRelation World ExternalFault) : Prop :=
  ∀ source ancestors, RuntimeStateAt members module path formals before ancestors source →
    ∃ outcome sourceEvents machineEvents,
      RuntimeStatementEvaluates (leaves.map RuntimeCallLeaf.source) members module path formals result before source raw after outcome sourceEvents ∧
      RuntimeLeafCallTraceRelated leaves sourceEvents machineEvents ∧
      RuntimeContinuationAt members module path formals after ancestors outcome ∧
      ∀ accumulator, RuntimeBodyRun program external caller saved world base source start stop accumulator outcome machineEvents

def RuntimeStatementsSimulates (program : CallProgram) (caller : Int)
    (leaves : List (RuntimeCallLeaf t files root module path))
    (members : List Declaration) (formals : List Formal) (result : RuntimeType)
    (before : LocalContext) (raw : List SourceStatement) (after : LocalContext) (start stop : Nat)
    (base : Machine) (saved : List SavedCall) (world : World) (external : ExternalRelation World ExternalFault) : Prop :=
  ∀ source ancestors, RuntimeStateAt members module path formals before ancestors source →
    ∃ outcome sourceEvents machineEvents,
      RuntimeStatementsEvaluate (leaves.map RuntimeCallLeaf.source) members module path formals result before source raw after outcome sourceEvents ∧
      RuntimeLeafCallTraceRelated leaves sourceEvents machineEvents ∧
      RuntimeContinuationAt members module path formals after ancestors outcome ∧
      ∀ accumulator, RuntimeBodyRun program external caller saved world base source start stop accumulator outcome machineEvents

end Aurora.SourceBinding
