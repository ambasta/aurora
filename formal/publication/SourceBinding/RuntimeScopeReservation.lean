import SourceBinding.RuntimeCallSourceFacts
namespace Aurora.SourceBinding

/-- Erased source bookkeeping only. Reserving skipped lexical scope identities
    changes neither active scopes nor declarations nor values. It cannot move
    the freshness cursor backward. The statement rule supplies its bound from
    the SAME source-scoped subtree, never a proposed machine poststate. -/
def RuntimeLocals.reserveScopes (state : RuntimeLocals) (limit : Nat) : Option RuntimeLocals :=
  if state.nextScope ≤ limit then some { state with nextScope := limit } else none

/-- Enter exactly the next certified static scope. Skipped siblings are handled
    by reserveScopes, not by resurrecting an earlier scope or initializing it. -/
def RuntimeLocals.enterAt (state : RuntimeLocals) (scope : Nat) : Option RuntimeLocals :=
  if state.nextScope = scope then some state.enter else none

def runtimeStatementContext (members : List Declaration) (module path : Name)
    (formals : List Formal) (cursor : LocalContext) : RuntimeExprContext :=
  ⟨members,module,path,formals,cursor.visible⟩

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
