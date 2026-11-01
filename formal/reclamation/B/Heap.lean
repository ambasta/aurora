import B.Basic
namespace Aurora.B
variable {Agent : Type} {config : Config} {s : State Agent} {original : Heap}

/-- Source contents are stable only during this admitted source-loan trace,
not throughout the lifetime of the native registered endpoint buffer. -/
theorem source_store (stable : ∀ x, inRange config.source config.sourceBytes x → s.heap x = original x)
    (outside : ¬ inRange config.source config.sourceBytes cell) :
    ∀ x, inRange config.source config.sourceBytes x → store s.heap cell value x = original x := by
  intro x inside
  rw [store_other _ _ _ _ (by intro eq; subst x; exact outside inside)]
  exact stable x inside

theorem allocation_outside_source (valid : config.Valid) (member : cell ∈ config.allocation) :
    ¬ inRange config.source config.sourceBytes cell := fun inside => valid.2.2.1 cell inside member

theorem cursor_store (h : Invariant config original s) (found : s.cursors ticket = some c)
    (disjoint : ∀ offset, offset < c.copied → c.descriptor.destination + offset ≠ cell) :
    ∀ offset, offset < c.copied → store s.heap cell value (c.descriptor.destination + offset) =
      original (c.descriptor.source + offset) := by
  intro offset bound
  rw [store_other _ _ _ _ (disjoint offset bound)]
  exact (h.cursors ticket c found).2.2.2.2 offset bound

theorem copy_prefix (h : Invariant config original s) (found : s.cursors ticket = some c)
    (remaining : c.copied < c.descriptor.count) :
    ∀ offset, offset < (advance c).copied →
      (copy s ticket c).heap ((advance c).descriptor.destination + offset) =
        original ((advance c).descriptor.source + offset) := by
  intro offset bound
  have hc := h.cursors ticket c found
  change offset < c.copied + 1 at bound
  change store s.heap (c.descriptor.destination + c.copied) (s.heap (c.descriptor.source + c.copied))
    (c.descriptor.destination + offset) = original (c.descriptor.source + offset)
  by_cases last : offset = c.copied
  · subst offset
    rw [store_same]
    exact h.source _ (Descriptor.source_inside hc.1 remaining)
  · rw [store_other _ _ _ _ (by omega)]
    exact hc.2.2.2.2 offset (by omega)

end Aurora.B
