import B.Effects
import B.Generation
namespace Aurora.B

/-- Same-live-generation byte stability. Control cells are physically disjoint
from the managed allocation; they are not hidden by a payload/control tag. -/
theorem frozen_step_heap (valid : config.Valid) (h : Invariant config original s)
    (frozen : A.Frozen s.authority generation footprint)
    (current : generation = s.authority.protocol.generation) (member : cell ∈ footprint)
    (allocated : cell ∈ config.allocation) (step : Step issuer subject config s event t) :
    t.heap cell = s.heap cell := by
  have blocked : ∀ ticket, ¬ A.Enabled s.authority ticket cell true := fun ticket =>
    A.frozen_cell_excludes_enabled_write h.authority (by simpa only [current] using frozen member)
  cases step with
  | protocol | beginCopy | fault | release => rfl
  | payload ticket c found running remaining =>
    have admitted := (h.cursors ticket c found).2.2.1.enabled remaining
    exact store_other _ _ _ _ (by intro eq; exact blocked ticket (eq ▸ admitted))
  | write next generation ticket destination value action idle =>
    exact store_other _ _ _ _ (by intro eq; exact blocked ticket (eq ▸ write_enabled action))
  | control destination value allowed =>
    exact store_other _ _ _ _ (by intro eq; exact (valid.2.2.2 destination allowed).1 (eq ▸ allocated))
end Aurora.B
