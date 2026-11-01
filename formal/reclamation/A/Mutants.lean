import A.Witnesses
import A.Invariants
namespace Aurora.A.Mutants
open Witness

/-- Faulty request accounting retains the reserved cells in local free inventory.
This is NOT an A transition. All later actions below are original transitions. -/
def credit (s : State CPU) (f : Footprint) : State CPU :=
  { s with holdings := fun gen loc => if gen = 0 ∧ loc = .gate 0 then s.holdings gen loc ++ f else s.holdings gen loc }
def pending := ask s2 0 defaultGrant left true
def copiedRequest := credit pending left
def copiedRegistered := reg copiedRequest 0 rootEntry (child defaultGrant none left true false)
def copiedGranted := accept copiedRegistered 0 1
def copiedPublished := publish copiedGranted 1 (useEntry 0 1)
def duplicateOwner := submit copiedPublished 1 { useEntry 0 1 with published := true }
def copiedConflict := admit duplicateOwner 1 rootEntry defaultGrant left true

theorem pending_reached : Reached pending := by
  apply Reaches.trans reaches2
  exact Reaches.single (.request s2 0 0 rootEntry defaultGrant none left true false
    rfl rfl rfl rfl rfl rfl (by decide) (by simp) (by simp) (by decide))
theorem duplicate_owner_continuation : Goes copiedRequest copiedConflict := by
  apply (Reaches.single (.register copiedRequest (0,0) none rootEntry 1
    ⟨child defaultGrant none left true false,0⟩ (by decide) rfl rfl rfl rfl)).trans
  apply (Reaches.single (.passive _ _ (.grant _ (0,0) 1 ⟨none,false⟩ (by decide) rfl))).trans
  apply (Reaches.single (.passive _ _ (.publish _ 1 (useEntry 0 1) (by decide) rfl (by trivial) rfl))).trans
  apply (Reaches.single (.submit _ 1 { useEntry 0 1 with published := true }
    (child defaultGrant none left true false) rfl rfl rfl rfl rfl (by intro _; rfl))).trans
  exact admit_reaches _ _ _ _ _ _ rfl rfl rfl rfl rfl rfl rfl (by decide) (by decide)
theorem duplicate_owner_actual_conflict : Reached pending ∧ Goes copiedRequest copiedConflict ∧
    Step 0 1 allocation copiedConflict (.access 0 1 11 true) copiedConflict ∧
    Step 0 1 allocation copiedConflict (.access 0 2 11 true) copiedConflict := by
  exact ⟨pending_reached,duplicate_owner_continuation,
    .effect _ 1 busyUse (child defaultGrant none left true false) 11 rfl rfl rfl (by decide) (by decide),
    .effect _ 2 busyUse (child defaultGrant none left true false) 11 rfl rfl rfl (by decide) (by decide)⟩

/-- The old receipt is genuine, but its permanent use-ticket return marker has
already been consumed. Omitting just that guard credits cells owned by reborrow3. -/
def duplicateReturn := returnCells s7 1 left
def replayConflict := admit duplicateReturn 3 rootEntry defaultGrant left true

theorem duplicate_return_continuation : Goes duplicateReturn replayConflict :=
  admit_reaches _ _ _ _ _ _ rfl rfl rfl rfl rfl rfl rfl (by decide) (by decide)
theorem duplicate_return_after_reborrow_actual_conflict : Reached s7 ∧
    (entry s7 1).receipt = true ∧ s7.returned 1 = true ∧ Goes duplicateReturn replayConflict ∧
    Step 0 1 allocation replayConflict (.access 0 3 11 true) replayConflict ∧
    Step 0 1 allocation replayConflict (.access 0 4 11 true) replayConflict := by
  exact ⟨reaches7,rfl,rfl,duplicate_return_continuation,
    .effect _ 3 busyUse (child defaultGrant none left true false) 11 rfl rfl rfl (by decide) (by decide),
    .effect _ 4 busyUse (child defaultGrant none left true false) 11 rfl rfl rfl (by decide) (by decide)⟩

/-- Faulty freeze consumes a live use reservation instead of locally free cells.
The admitted writer still has actual work: effects do not consult global freeze. -/
def prematureFreeze := readEnable (move s3 0 (.use 1) .frozen left) 0 left
def frozenConflict := admit prematureFreeze 1 rootEntry defaultGrant left false

theorem premature_freeze_continuation : Goes prematureFreeze frozenConflict :=
  admit_reaches _ _ _ _ _ _ rfl rfl rfl rfl rfl rfl rfl (by decide) (by decide)
theorem premature_freeze_actual_conflict : Reached s3 ∧ Goes prematureFreeze frozenConflict ∧
    Step 0 1 allocation frozenConflict (.access 0 1 11 true) frozenConflict ∧
    Step 0 1 allocation frozenConflict (.access 0 2 11 false) frozenConflict := by
  exact ⟨Reaches.trans reaches2 step3,premature_freeze_continuation,
    .effect _ 1 busyUse (child defaultGrant none left true false) 11 rfl rfl rfl (by decide) (by decide),
    .effect _ 2 busyUse (child defaultGrant none left false false) 11 rfl rfl rfl (by decide) (by decide)⟩

/-- A timeout cannot return an unregistered reservation. The two different
claim locations containing cell11 expose an ownership failure, not a claimed
complete native-unsafety execution. -/
def timeoutRestore := credit pending left
theorem timeout_duplicates_escrow : Reached pending ∧
    11 ∈ timeoutRestore.holdings 0 (.gate 0) ∧
    11 ∈ timeoutRestore.holdings 0 (.request (0,0)) := by
  exact ⟨pending_reached,by decide,by decide⟩

theorem timeout_loses_escrow : Reached pending ∧ ¬Invariant allocation timeoutRestore := by
  refine ⟨timeout_duplicates_escrow.1,?_⟩
  intro h
  have incompatible := (h.partition 0 rfl).unique (.gate 0) (.request (0,0)) 11
    timeout_duplicates_escrow.2.1 timeout_duplicates_escrow.2.2
  contradiction

/-- Different view names do not separate their canonical backing images.
This checks the boundary requirement, not a native address decoder. -/
def viewImage : Nat → Footprint
  | 101 => [7,9]
  | 202 => [9,11]
  | _ => []
def firstAliasReserved := ask s2 0 defaultGrant (viewImage 101) true
theorem alias_image_overlap_refused : (101 : Nat) ≠ 202 ∧
    9 ∈ viewImage 101 ∧ 9 ∈ viewImage 202 ∧
    ¬(viewImage 202).Within (firstAliasReserved.holdings 0 (.gate 0)) := by decide

def staleRebind := putGrant s3 1 { child defaultGrant none left true false with generation := 1 }
theorem stale_descriptor_identity_mismatch : Reached s3 ∧
    (entry staleRebind 1).generation = 0 ∧ (cap staleRebind 1).generation = 1 :=
  ⟨Reaches.trans reaches2 step3,rfl,rfl⟩
theorem stale_descriptor_rebinding_breaks_identity : Reached s3 ∧ ¬Invariant allocation staleRebind := by
  refine ⟨Reaches.trans reaches2 step3,?_⟩
  intro h
  have bound := (grant_entry h (i := 1) (g := { child defaultGrant none left true false with generation := 1 })
    (e := busyUse) rfl rfl).1
  have impossible : (0 : Nat) = 1 := bound
  contradiction

theorem checked_attenuation_refusals :
    ¬Footprint.Within [7,14] allocation ∧
    ¬(child defaultGrant none left false false).writable = true ∧
    ¬left.Within (s3.holdings 0 (.gate 0)) ∧
    ¬allocation.Within (child defaultGrant (some 2) left true false).footprint ∧
    ¬(child defaultGrant (some 2) left true false).delegates = true := by decide
end Aurora.A.Mutants
