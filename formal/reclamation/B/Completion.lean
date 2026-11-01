import B.Preservation
import B.Frozen
import B.Phase
namespace Aurora.B

theorem trace_erases (valid : config.Valid) (h : Invariant config original s)
    (trace : Trace issuer subject config s events t) :
    A.Trace issuer subject config.allocation s.authority (events.map erase) t.authority := by
  induction trace with
  | nil => exact .nil _
  | cons step tail ih => exact .cons (step_erases h step) (ih (step_preserves valid h step))

/-- One source-loan epoch, arbitrary admitted interleaving; not all A traces lift. -/
theorem invariant (valid : config.Valid) (reachable : A.Reachable issuer subject config.allocation authority)
    (trace : Trace issuer subject config (initial authority original) events t) : Invariant config original t :=
  trace_preserves valid (initial_invariant (A.reachable_invariant reachable)) trace

theorem copied_prefix (valid : config.Valid) (reachable : A.Reachable issuer subject config.allocation authority)
    (trace : Trace issuer subject config (initial authority original) events t)
    (found : t.cursors ticket = some c) (bound : offset < c.copied) :
    t.heap (c.descriptor.destination + offset) = original (c.descriptor.source + offset) :=
  ((invariant valid reachable trace).cursors ticket c found).2.2.2.2 offset bound

theorem completed_copy (valid : config.Valid) (reachable : A.Reachable issuer subject config.allocation authority)
    (trace : Trace issuer subject config (initial authority original) events t)
    (found : t.cursors ticket = some c) (done : c.phase = .done) (bound : offset < c.descriptor.count) :
    t.heap (c.descriptor.destination + offset) = original (c.descriptor.source + offset) := by
  have count := (trace_phase initial_phase trace ticket c found).1 done
  exact copied_prefix valid reachable trace found (count ▸ bound)

theorem frozen_in_allocation (h : A.Invariant allocation s) (frozen : A.Frozen s generation footprint)
    (member : cell ∈ footprint) : cell ∈ allocation := by
  have held := frozen member
  have issued : s.issued generation = true := by
    cases flag : s.issued generation with
    | true => rfl
    | false => rw [h.unissuedEmpty generation flag .frozen] at held; cases held
  exact (h.partition generation issued).bound .frozen held

/-- Frozen bytes remain equal while this generation lives. Syntactic NoReuse
excludes reuse transitions, NOT writes; authority proves write exclusion. -/
theorem frozen_trace_heap (valid : config.Valid) (h : Invariant config original s)
    (frozen : A.Frozen s.authority generation footprint)
    (current : generation = s.authority.protocol.generation) (member : cell ∈ footprint)
    (trace : Trace issuer subject config s events t)
    (noReuse : ∀ event ∈ events, NoReuse event) : t.heap cell = s.heap cell := by
  induction trace with
  | nil => rfl
  | cons step tail ih =>
    have erased := step_erases h step
    have nextFrozen := A.step_preserves_frozen h.authority frozen erased
    have nextCurrent := current.trans (step_generation step (noReuse _ List.mem_cons_self)).symm
    have rest := ih (step_preserves valid h step) nextFrozen nextCurrent
      (fun event member => noReuse event (List.mem_cons_of_mem _ member))
    exact rest.trans (frozen_step_heap valid h frozen current member
      (frozen_in_allocation h.authority frozen member) step)
end Aurora.B
