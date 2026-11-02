import SourceBinding.RuntimeCallSourceFacts
import SourceBinding.RuntimeScopeOperations
namespace Aurora.SourceBinding

/-- Only actually executed declarations are initialized. Hidden past cells may
    remain stored; every future static slot is fresh. This is a source-state
    invariant, not an assumption about an arbitrary saved caller frame. -/
def RuntimeStateAt (members : List Declaration) (module path : Name) (formals : List Formal)
    (cursor : LocalContext) (ancestors : List Nat) (state : RuntimeLocals) : Prop :=
  state.WellFormed ∧ state.scopes = cursor.scope :: ancestors ∧
  state.nextScope = cursor.nextScope ∧
  RuntimeBindingsPresent (runtimeStatementContext members module path formals cursor) state ∧
  (∀ name binding, RuntimeVariableBinding (runtimeStatementContext members module path formals cursor) name binding →
    ∃ value, state.values binding.slot = some value ∧ readRuntime binding.kind (some value) = .value value) ∧
  (∀ slot, 8 * (cursor.nextSlot + 1) ≤ slot → state.declarations slot = none ∧ state.values slot = none)

end Aurora.SourceBinding
