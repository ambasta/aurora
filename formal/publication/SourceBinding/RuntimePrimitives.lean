import SourceBinding.GuardSemantics
namespace Aurora.SourceBinding

/-- Nominal values preserve identity. Cardinality comes from the checked
    declaration/type binding, not from coercing an enum to a machine word. -/
def readRuntime (kind : RuntimeType) (value : Option Value) : Outcome Value :=
  match kind with
  | .scalar scalar => readScalar scalar value
  | .nominal identity => match value with
    | some (.nominal name ordinal) =>
      if name = identity.name ∧ ordinal < identity.cases then .value (.nominal name ordinal)
      else .trap .type
    | _ => .trap .type

def compareNominal (identity : NominalIdentity) (equal : Bool) (left right : Value) : Outcome Value :=
  (readRuntime (.nominal identity) (some left)).then fun a =>
    (readRuntime (.nominal identity) (some right)).then fun b =>
      match a,b with
      | .nominal _ x, .nominal _ y => .value (.boolean (if equal then x == y else x != y))
      | _,_ => .trap .type

/-- Source local metadata is retained separately from the raw IR slot. An IR
    slot's flags do not establish source constness or lexical visibility. -/
structure RuntimeLocalDecl where
  kind : RuntimeType
  mutable : Bool
  scope : Nat
  deriving BEq, DecidableEq, Repr

structure RuntimeLocals where
  nextScope : Nat
  scopes : List Nat
  declarations : Nat → Option RuntimeLocalDecl
  values : Nat → Option Value

/-- Scope identities are monotone and are never re-entered after leaving.
    Scope-changing transitions use these operations, not arbitrary list edits. -/
def RuntimeLocals.enter (state : RuntimeLocals) : RuntimeLocals :=
  {state with nextScope := state.nextScope + 1, scopes := state.nextScope :: state.scopes}

def RuntimeLocals.leave (state : RuntimeLocals) : RuntimeLocals :=
  {state with scopes := state.scopes.tail}

def RuntimeLocals.WellFormed (state : RuntimeLocals) : Prop :=
  state.scopes.Nodup ∧
  (∀ scope ∈ state.scopes, scope < state.nextScope) ∧
  (∀ slot declaration, state.declarations slot = some declaration → declaration.scope < state.nextScope) ∧
  (∀ slot value, state.values slot = some value →
    ∃ declaration, state.declarations slot = some declaration ∧
      readRuntime declaration.kind (some value) = .value value)

/-- A declaration's initializer is evaluated before this operation. Freshness
    prohibits replacing another declaration, even when its scope has ended. -/
def RuntimeLocals.initialize (state : RuntimeLocals) (slot : Nat)
    (declaration : RuntimeLocalDecl) (value : Value) : Option RuntimeLocals := do
  if state.scopes.head? ≠ some declaration.scope then none else
  if state.declarations slot ≠ none ∨ state.values slot ≠ none then none else
  match readRuntime declaration.kind (some value) with
  | .trap _ => none
  | .value checked => some { state with
      declarations := fun i => if i = slot then some declaration else state.declarations i
      values := fun i => if i = slot then some checked else state.values i }

def RuntimeLocals.read (state : RuntimeLocals) (slot : Nat) : Outcome Value :=
  match state.declarations slot with
  | none => .trap .type
  | some declaration =>
    if declaration.scope ∈ state.scopes then readRuntime declaration.kind (state.values slot)
    else .trap .type

/-- Assignment is not initialization: the declaration must be visible, mutable
    and already initialized. Its metadata is never changed by assignment. -/
def RuntimeLocals.assign (state : RuntimeLocals) (slot : Nat) (value : Value) : Option RuntimeLocals := do
  let declaration ← state.declarations slot
  if declaration.mutable ≠ true ∨ declaration.scope ∉ state.scopes ∨ state.values slot = none then none else
  match readRuntime declaration.kind (some value) with
  | .trap _ => none
  | .value checked => some { state with values := fun i => if i = slot then some checked else state.values i }

@[simp] theorem readRuntime_scalar (kind : GuardType) (value : Option Value) :
    readRuntime (.scalar kind) value = readScalar kind value := rfl

@[simp] theorem readScalar_nominal (kind : GuardType) (name : ByteArray) (ordinal : Nat) :
    readScalar kind (some (.nominal name ordinal)) = .trap .type := rfl

@[simp] theorem readRuntime_nominal (identity : NominalIdentity) (ordinal : Nat)
    (valid : ordinal < identity.cases) :
    readRuntime (.nominal identity) (some (.nominal identity.name ordinal)) =
      .value (.nominal identity.name ordinal) := by
  simp only [readRuntime, and_self, if_pos, valid]

end Aurora.SourceBinding
