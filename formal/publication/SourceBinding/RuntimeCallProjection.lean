import SourceBinding.RuntimeCallIdentity
import SourceBinding.SourceExpressionEquality
namespace Aurora.SourceBinding
open Aurora.Publication

instance (target : OrdinaryDescriptor) (targets : List OrdinaryDescriptor) :
    Decidable (target ∈ targets) := memberDecision target targets

/-- The finite source-key/target map must be unambiguous in both directions.
    Equal duplicates are allowed; no source-symbol injectivity axiom is used. -/
def RuntimeLeavesCompatible (leaves : List (RuntimeCallLeaf t files root module path)) : Prop :=
  ∀ first ∈ leaves, ∀ second ∈ leaves,
    (first.source.key = second.source.key →
      first.source.function = second.source.function ∧
      first.source.context.members = second.source.context.members ∧
      first.source.raw = second.source.raw ∧ first.target = second.target) ∧
    (first.identified.id = second.identified.id → first.source.key = second.source.key)
instance (leaves : List (RuntimeCallLeaf t files root module path)) : Decidable (RuntimeLeavesCompatible leaves) := by
  unfold RuntimeLeavesCompatible; infer_instance

def UniqueRuntimeCall (t : Tables) (targets : List OrdinaryDescriptor) (caller : Int) (pc : Nat)
    (target : OrdinaryDescriptor) : Prop :=
  target ∈ targets ∧ RuntimeFreeInvocationAt t caller pc target ∧
  ∀ other ∈ targets, RuntimeFreeInvocationAt t caller pc other → other = target
instance (t : Tables) (targets : List OrdinaryDescriptor) (caller : Int) (pc : Nat) (target : OrdinaryDescriptor) :
    Decidable (UniqueRuntimeCall t targets caller pc target) := by unfold UniqueRuntimeCall; infer_instance

structure ResolvedRuntimeCall (t : Tables) (targets : List OrdinaryDescriptor) (caller : Int) (pc : Nat) where
  target : OrdinaryDescriptor
  valid : UniqueRuntimeCall t targets caller pc target

def resolveRuntimeCall (t : Tables) (targets : List OrdinaryDescriptor) (caller : Int) (pc : Nat) :
    Option (ResolvedRuntimeCall t targets caller pc) := do
  let candidate ← targets.find? (fun target => decide (RuntimeFreeInvocationAt t caller pc target))
  if valid : UniqueRuntimeCall t targets caller pc candidate then return ⟨candidate,valid⟩ else none

/-- SAME canonical local instructions, followed only by positive checked Call19
    admission. Unknown operations never become fabricated local instructions. -/
def canonicalRuntimeCalls (t : Tables) (targets : List OrdinaryDescriptor) : CallProgram := fun caller pc =>
  match canonicalEffects t caller pc with
  | some operation => some (.local operation)
  | none => (resolveRuntimeCall t targets caller pc).map fun resolved => .ordinary resolved.target

theorem canonical_runtime_calls_local (t : Tables) (targets : List OrdinaryDescriptor) (caller : Int) :
    localProgram (canonicalRuntimeCalls t targets) caller = canonicalEffects t caller := by
  funext pc
  unfold localProgram canonicalRuntimeCalls
  cases effect : canonicalEffects t caller pc with
  | some operation => rfl
  | none => cases resolved : resolveRuntimeCall t targets caller pc <;> rfl

theorem RuntimeFreeInvocationAt.no_effect {t : Tables} {caller : Int} {pc : Nat} {target : OrdinaryDescriptor}
    (meaning : RuntimeFreeInvocationAt t caller pc target) : canonicalEffects t caller pc = none := by
  unfold RuntimeFreeInvocationAt at meaning
  cases rowEq : (functionCode t caller)[pc]? with
  | none => simp only [rowEq] at meaning
  | some row =>
    simp only [rowEq] at meaning
    have position := meaning.2.1
    have form := meaning.2.2.1
    simp [canonicalEffects,rowEq,position,decodeEffect,effectCandidate,operationCandidate,form]

theorem canonical_runtime_call_sound
    (accepted : canonicalRuntimeCalls t targets caller pc = some (.ordinary target)) :
    UniqueRuntimeCall t targets caller pc target := by
  unfold canonicalRuntimeCalls at accepted
  cases effect : canonicalEffects t caller pc with
  | some operation => simp [effect] at accepted
  | none =>
    simp only [effect] at accepted
    cases resolved : resolveRuntimeCall t targets caller pc with
    | none => simp [resolved] at accepted
    | some checked =>
      simp only [resolved,Option.map,Option.some.injEq,CallOp.ordinary.injEq] at accepted
      exact accepted ▸ checked.valid

end Aurora.SourceBinding
