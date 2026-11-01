import SourceBinding.CallMachine
namespace Aurora.SourceBinding
open Aurora.Publication

deriving instance DecidableEq for CallTarget

def pieceTargets : List CallPiece → List CallTarget
  | [] => []
  | .localBody _ :: rest => pieceTargets rest
  | .invoke (.ordinary target _) :: rest => .ordinary target :: pieceTargets rest
  | .invoke (.resourceAssert target _) :: rest => .resource target :: pieceTargets rest

def targetOperation : CallTarget → CallOp
  | .ordinary target => .ordinary target
  | .resource target => .resource target

/-- Matching descriptors must agree in FULL, not merely in scalar signature or
    target ordinal. Identical repeated source calls are harmless. -/
def UniqueCallTarget (t : Tables) (targets : List CallTarget) (id : Int) (pc : Nat) (target : CallTarget) : Prop :=
  target ∈ targets ∧ InvocationAt t id pc target ∧
  ∀ other ∈ targets, InvocationAt t id pc other → other = target
instance (t : Tables) (targets : List CallTarget) (id : Int) (pc : Nat) (target : CallTarget) :
    Decidable (UniqueCallTarget t targets id pc target) := by unfold UniqueCallTarget; infer_instance
structure ResolvedCall (t : Tables) (targets : List CallTarget) (id : Int) (pc : Nat) where
  target : CallTarget
  valid : UniqueCallTarget t targets id pc target

def resolveCall (t : Tables) (targets : List CallTarget) (id : Int) (pc : Nat) :
    Option (ResolvedCall t targets id pc) := do
  let candidate ← targets.find? (fun target => decide (InvocationAt t id pc target))
  if checked : UniqueCallTarget t targets id pc candidate then return ⟨candidate,checked⟩ else none

/-- Local projection takes priority and is unchanged globally. A failed local
    decoder admits only a positively checked call, never a fabricated local op. -/
def canonicalCalls (t : Tables) (targets : List CallTarget) : CallProgram := fun id pc =>
  match canonicalEffects t id pc with
  | some operation => some (.local operation)
  | none => (resolveCall t targets id pc).map (fun checked => targetOperation checked.target)

theorem canonical_calls_local (t : Tables) (targets : List CallTarget) (id : Int) :
    localProgram (canonicalCalls t targets) id = canonicalEffects t id := by
  funext pc
  unfold localProgram canonicalCalls
  cases effect : canonicalEffects t id pc with
  | some operation => rfl
  | none =>
    cases resolved : resolveCall t targets id pc with
    | none => rfl
    | some checked => cases checked with
      | mk target valid => cases target <;> rfl

theorem InvocationAt.no_effect {t : Tables} {id : Int} {pc : Nat} {target : CallTarget}
    (meaning : InvocationAt t id pc target) : canonicalEffects t id pc = none := by
  unfold InvocationAt at meaning
  cases rowEq : (functionCode t id)[pc]? with
  | none => simp only [rowEq] at meaning
  | some row =>
    simp only [rowEq] at meaning
    obtain ⟨position,binding⟩ := meaning
    have form : row.integer 6 = 38 ∨ row.integer 6 = 89 := by
      cases target with
      | ordinary descriptor => exact Or.inl binding.2.2.2.1
      | resource descriptor => exact Or.inr binding.2.2.2.1
    rcases form with form | form <;>
      simp [canonicalEffects,rowEq,position,decodeEffect,effectCandidate,operationCandidate,form]

theorem resolve_call_complete {t : Tables} {targets : List CallTarget} {id : Int} {pc : Nat} {target : CallTarget}
    (valid : UniqueCallTarget t targets id pc target) :
    ∃ checked, resolveCall t targets id pc = some checked ∧ checked.target = target := by
  have found : targets.find? (fun target => decide (InvocationAt t id pc target)) = some target := by
    cases result : targets.find? (fun target => decide (InvocationAt t id pc target)) with
    | none =>
      have absent := List.find?_eq_none.mp result target valid.1
      exact False.elim (absent (decide_eq_true valid.2.1))
    | some candidate =>
      have member := List.mem_of_find?_eq_some result
      have matching : InvocationAt t id pc candidate := of_decide_eq_true (List.find?_some (p := fun target => decide (InvocationAt t id pc target)) result)
      have same := valid.2.2 candidate member matching
      exact congrArg some same
  unfold resolveCall
  simp only [found,bind,Option.bind]
  exact ⟨⟨target,valid⟩,by simp only [dif_pos valid,pure],rfl⟩

theorem canonical_call_complete {t : Tables} {targets : List CallTarget} {id : Int} {pc : Nat} {target : CallTarget}
    (valid : UniqueCallTarget t targets id pc target) :
    canonicalCalls t targets id pc = some (targetOperation target) := by
  obtain ⟨checked,accepted,same⟩ := resolve_call_complete valid
  simp only [canonicalCalls,valid.2.1.no_effect,accepted,Option.map,same]

theorem canonical_call_sound {t : Tables} {targets : List CallTarget} {id : Int} {pc : Nat} {target : CallTarget}
    (accepted : canonicalCalls t targets id pc = some (targetOperation target)) :
    UniqueCallTarget t targets id pc target := by
  unfold canonicalCalls at accepted
  cases effect : canonicalEffects t id pc with
  | some operation => cases target <;> simp [effect,targetOperation] at accepted
  | none =>
    simp only [effect] at accepted
    cases resolved : resolveCall t targets id pc with
    | none => simp [resolved] at accepted
    | some checked =>
      simp only [resolved,Option.map,Option.some.injEq] at accepted
      have injective : Function.Injective targetOperation := by
        intro a b equal
        cases a <;> cases b <;> cases equal <;> rfl
      have same := injective accepted
      exact same ▸ checked.valid

/-- A finite, independently stated ambiguity guard over the actual selected
    closure. It is checked, not an assumption imposed on arbitrary callers. -/
def ProjectionCompatible (t : Tables) (selected : List Int) (targets : List CallTarget) : Prop :=
  ∀ id ∈ selected, ∀ pc ∈ List.range (functionCode t id).size,
    ∀ first ∈ targets, ∀ second ∈ targets,
      InvocationAt t id pc first → InvocationAt t id pc second → second = first
instance (t : Tables) (selected : List Int) (targets : List CallTarget) :
    Decidable (ProjectionCompatible t selected targets) := by unfold ProjectionCompatible; infer_instance

theorem InvocationAt.bound {t : Tables} {id : Int} {pc : Nat} {target : CallTarget}
    (meaning : InvocationAt t id pc target) : pc < (functionCode t id).size := by
  by_cases bound : pc < (functionCode t id).size
  · exact bound
  · have absent : (functionCode t id)[pc]? = none := Array.getElem?_eq_none (Nat.le_of_not_gt bound)
    simp only [InvocationAt,absent] at meaning

theorem ProjectionCompatible.unique {t : Tables} {selected : List Int} {targets : List CallTarget}
    (compatible : ProjectionCompatible t selected targets) {id : Int} {pc : Nat} {target : CallTarget}
    (member : id ∈ selected) (present : target ∈ targets) (meaning : InvocationAt t id pc target) :
    UniqueCallTarget t targets id pc target :=
  ⟨present,meaning,fun other admitted matching =>
    compatible id member pc (List.mem_range.mpr meaning.bound) target present other admitted meaning matching⟩

structure CallProjectionBinding (family : CallFamilyBinding files root module path member bytes) : Type where
  compatible : ProjectionCompatible (tables family.shape.ir.publication.artifact.document.reversed.reverse)
    family.shape.ir.publication.slice.selected (pieceTargets family.shape.source.pieces)

def checkCallProjection (family : CallFamilyBinding files root module path member bytes) :
    Option (CallProjectionBinding family) :=
  if compatible : ProjectionCompatible (tables family.shape.ir.publication.artifact.document.reversed.reverse)
      family.shape.ir.publication.slice.selected (pieceTargets family.shape.source.pieces) then some ⟨compatible⟩ else none
end Aurora.SourceBinding
