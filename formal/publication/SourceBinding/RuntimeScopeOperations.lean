import SourceBinding.RuntimeExpressions
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

end Aurora.SourceBinding
