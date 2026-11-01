import B.Witnesses
import B.Effects
namespace Aurora.B.Mutants
open Witnesses

/-- These heap updates are deliberately NOT B transitions. They exhibit the
    failures prevented by the corresponding guards, not alternative safe models. -/
def extraWrite : State Unit := {s2 with heap := store s2.heap 0 ⟨0,by decide⟩}
def continued : State Unit := copy extraWrite 1 (advance c0)

theorem same_ticket_still_enabled : A.Enabled s2.authority 1 0 true :=
  admitted_authorized.enabled (offset := 0) (by decide)

theorem same_ticket_write_denied : ¬ Step () () config s2 (.write 0 1 0 ⟨0,by decide⟩) extraWrite := by
  intro action
  cases action with
  | write next generation ticket cell value action idle =>
    change some (advance c0) = none at idle
    cases idle

/-- One unguarded mutant write followed by an ORIGINAL payload step. The second
    byte still copies normally, but it cannot repair the overwritten first byte. -/
theorem original_continuation :
    Step () () config extraWrite (.payload 0 1 4097 1 ⟨9,by decide⟩) continued :=
  .payload extraWrite 1 (advance c0) rfl rfl (by decide)

theorem continued_wrong_bytes : continued.heap 0 ≠ initialHeap 4096 ∧
    continued.heap 1 = initialHeap 4097 ∧ continued.cursors 1 = some ⟨descriptor,2,.done⟩ := by decide

theorem extra_write_breaks_prefix : ¬ Invariant config initialHeap extraWrite := by
  intro invariant
  have copied :=  (invariant.cursors 1 (advance c0) rfl).2.2.2.2 0 (by decide)
  have wrong : extraWrite.heap 0 ≠ initialHeap 4096 := by decide
  exact wrong copied

theorem continuation_breaks_prefix : ¬ Invariant config initialHeap continued := by
  intro invariant
  have copied :=  (invariant.cursors 1 ⟨descriptor,2,.done⟩ rfl).2.2.2.2 0 (by decide)
  exact continued_wrong_bytes.1 copied

/-- Control writes share canonical addresses with payload writes; a control tag
    alone cannot justify the alias. Config.Valid rules this configuration out. -/
def controlAlias : Config := {config with control := [0]}
def controlOverwrite : State Unit := {s2 with heap := store s2.heap 0 ⟨0,by decide⟩}
theorem alias_control_step : Step () () controlAlias s2 (.control 0 ⟨0,by decide⟩) controlOverwrite :=
  .control s2 0 ⟨0,by decide⟩ (by exact List.mem_cons_self)
theorem alias_control_wrong_byte : controlOverwrite.heap 0 ≠ initialHeap 4096 := by decide
theorem control_alias_invalid : ¬ controlAlias.Valid := by
  intro valid
  exact (valid.2.2.2 0 (by exact List.mem_cons_self)).1 (by exact List.mem_cons_self)

/-- Even a range-valid descriptor is insufficient when the registered source
    aliases the allocation. Registration separation is a whole-config property. -/
def sourceAlias : Config := {config with source := 0}
def selfCopy : Descriptor := {descriptor with source := 0}
theorem self_copy_range_valid : selfCopy.Valid sourceAlias := by
  unfold Descriptor.Valid selfCopy sourceAlias descriptor config wordLimit
  decide
theorem source_alias_invalid : ¬ sourceAlias.Valid := by
  intro valid
  exact valid.2.2.1 0 (by constructor <;> decide) (by exact List.mem_cons_self)

/-- A fabricated rollback after the real partial-fault trace erases a completed
    byte. Original B faults retain it and do not perform this assignment. -/
def rolledBack : State Unit := {failed with heap := initialHeap}
theorem rollback_loses_completed_byte : failed.heap 0 = ⟨7,by decide⟩ ∧
    rolledBack.heap 0 ≠ failed.heap 0 := by decide
theorem rollback_breaks_prefix : ¬ Invariant config initialHeap rolledBack := by
  intro invariant
  have copied :=  (invariant.cursors 1 {advance c0 with phase := .faulted} rfl).2.2.2.2 0 (by decide)
  have wrong : rolledBack.heap 0 ≠ initialHeap 4096 := by decide
  exact wrong copied

def outside : Descriptor := {descriptor with destination := 2}
theorem wrong_destination_not_enabled : ¬ A.Enabled admitted 1 2 true := by
  intro enabled
  have member := A.reachable_effect_bounds admitted_reachable enabled
  change 2 ∈ [0,1] at member
  simp at member
theorem wrong_destination_not_authorized : ¬ Authorized admitted 1 outside := by
  intro authorized
  exact wrong_destination_not_enabled (authorized.enabled (offset := 0) (by decide))

/-- Releasing the cursor does not clear spent: restart remains forbidden even
    after the empty-cursor guard itself becomes true. -/
def released : State Unit := putCursor s3 1 none
theorem release_step : Step () () config s3 (.release 1) released :=
  .release s3 1 ⟨descriptor,2,.done⟩ rfl (by decide)
theorem released_empty_spent : released.cursors 1 = none ∧ released.spent 1 = true := ⟨rfl,rfl⟩
theorem duplicate_restart_denied (after : State Unit) :
    ¬ Step () () config released (.beginCopy 1) after := by
  intro action
  cases action with
  | beginCopy ticket descriptor fresh empty valid authorized =>
    change true = false at fresh
    cases fresh

end Aurora.B.Mutants
