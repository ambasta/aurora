import A.Invariants
namespace Aurora.A

/-- Operationally enabled effects inspect only the admitted descriptor and local
actual work. This definition does not inspect the permission token or freeze. -/
def Enabled (s : State Agent) (i cell : Nat) (write : Bool) : Prop :=
  ∃ e g, s.protocol.entries i = some e ∧ s.grants i = some g ∧
    e.kind = .use g.subject ∧ 0 < e.work ∧ g.extent.Contains cell ∧ g.writable = write

variable {s : State Agent} {allocation : Extent}

theorem enabled_current (h : Invariant allocation s) (enabled : Enabled s i cell write) :
    ∃ e g, s.protocol.entries i = some e ∧ s.grants i = some g ∧
      e.kind = .use g.subject ∧ e.sealed = false ∧
      g.generation = s.protocol.generation ∧ g.writable = write := by
  obtain ⟨e, g, he, hg, use, work, _, hw⟩ := enabled
  have unsealed := R.work_unsealed h.protocol.2 he use work
  have current := Q.possible_current h.protocol.1 (R.project_found he)
    (by simp [R.abstractEntry, unsealed])
  have bound := (grant_entry h hg he).1
  exact ⟨e, g, he, hg, use, unsealed, bound.symm.trans current, hw⟩

theorem enabled_writer_owns (h : Invariant allocation s) (enabled : Enabled s i cell true) :
    s.tokens s.protocol.generation = .use i := by
  obtain ⟨e, g, he, hg, use, unsealed, current, hw⟩ := enabled_current h enabled
  have own := h.executingWriter i g e hg he hw unsealed (by simp [use, Executing])
  simpa [current, use, executingLocation] using own

theorem enabled_reader_frozen (h : Invariant allocation s) (enabled : Enabled s i cell false) :
    Frozen s s.protocol.generation := by
  obtain ⟨e, g, he, hg, use, unsealed, current, hw⟩ := enabled_current h enabled
  simpa [current] using h.readerGrant i g hg hw

/-- Whole-allocation exclusion, stronger than overlap-only exclusion. Distinct
leases cannot contain a writer simultaneously; disjoint-writer splitting remains
outside A0. Within-stream/job race freedom is not inferred from this theorem. -/
theorem distinct_enabled_streams_are_readers (h : Invariant allocation s)
    (left : Enabled s i x wi) (right : Enabled s j y wj) (distinct : i ≠ j) :
    wi = false ∧ wj = false := by
  have one (a b ca cb : Nat) (wa wb : Bool) (ha : Enabled s a ca wa)
      (hb : Enabled s b cb wb) (ne : a ≠ b) : wa = false := by
    cases wa with
    | false => rfl
    | true =>
      have own := enabled_writer_owns h ha
      cases wb with
      | true =>
        have other := enabled_writer_owns h hb
        have same : a = b := Location.use.inj (own.symm.trans other)
        exact False.elim (ne same)
      | false =>
        obtain ⟨gate, frozen⟩ := enabled_reader_frozen h hb
        simp [own] at frozen
  exact ⟨one i j x y wi wj left right distinct,
    one j i y x wj wi right left (Ne.symm distinct)⟩

theorem frozen_excludes_enabled_write (h : Invariant allocation s)
    (frozen : Frozen s s.protocol.generation) : ¬Enabled s i cell true := by
  intro enabled
  obtain ⟨gate, hg⟩ := frozen
  have own := enabled_writer_owns h enabled
  simp [own] at hg

theorem enabled_within_allocation (h : Invariant allocation s)
    (enabled : Enabled s i cell write) : allocation.Contains cell := by
  obtain ⟨e, g, he, hg, use, work, bounds, hw⟩ := enabled
  have outer := (grant_entry h hg he).2.2
  exact ⟨Nat.le_trans outer.1 bounds.1, Nat.lt_of_lt_of_le bounds.2 outer.2.2⟩

end Aurora.A
