import A.Invariants
namespace Aurora.A

/-- Effects consult admitted immutable metadata and local outstanding work only. -/
def Enabled (s : State Agent) (i cell : Nat) (write : Bool) : Prop :=
  ∃ e g, s.protocol.entries i = some e ∧ s.grants i = some g ∧
    e.kind = .use g.subject ∧ 0 < e.work ∧ g.footprint.Contains cell ∧ g.writable = write

variable {s : State Agent} {allocation : Footprint}

theorem enabled_current (h : Invariant allocation s) (enabled : Enabled s i cell write) :
    ∃ e g, s.protocol.entries i = some e ∧ s.grants i = some g ∧
      e.kind = .use g.subject ∧ e.sealed = false ∧
      g.generation = s.protocol.generation ∧ g.writable = write ∧ cell ∈ g.footprint := by
  obtain ⟨e,g,he,hg,use,work,hc,hw⟩ := enabled
  have unsealed := R.work_unsealed h.protocol.2 he use work
  have current := Q.possible_current h.protocol.1 (R.project_found he)
    (by simp [R.abstractEntry,unsealed])
  exact ⟨e,g,he,hg,use,unsealed,(grant_entry h hg he).1.symm.trans current,hw,hc⟩

theorem enabled_writer_owns (h : Invariant allocation s) (enabled : Enabled s i cell true) :
    cell ∈ s.holdings s.protocol.generation (.use i) ∧ s.issued s.protocol.generation = true := by
  obtain ⟨e,g,he,hg,use,unsealed,current,hw,hc⟩ := enabled_current h enabled
  have unreturned := unsealed_unreturned h he unsealed
  have owned := (use_holding h hg he use hw unreturned cell).2 hc
  exact ⟨by simpa [current] using owned, by simpa [current] using h.grantsIssued i g hg⟩

theorem enabled_reader_frozen (h : Invariant allocation s) (enabled : Enabled s i cell false) :
    cell ∈ s.holdings s.protocol.generation .frozen := by
  obtain ⟨e,g,he,hg,use,unsealed,current,hw,hc⟩ := enabled_current h enabled
  simpa [current] using h.readerGrant i g hg hw hc

/-- Overlap exclusion, not whole-allocation serialization. Different cells may
be served by independent simultaneous writers. Within-job race freedom remains
an implementation obligation of each admitted sequential stream. -/
theorem overlapping_enabled_streams_are_readers (h : Invariant allocation s)
    (left : Enabled s i cell wi) (right : Enabled s j cell wj) (distinct : i ≠ j) :
    wi = false ∧ wj = false := by
  have one (a b : Nat) (wa wb : Bool) (ha : Enabled s a cell wa)
      (hb : Enabled s b cell wb) (ne : a ≠ b) : wa = false := by
    cases wa with
    | false => rfl
    | true =>
      obtain ⟨owned,issued⟩ := enabled_writer_owns h ha
      cases wb with
      | true =>
        have other := (enabled_writer_owns h hb).1
        have eq := (h.partition _ issued).unique (.use a) (.use b) cell owned other
        exact False.elim (ne (Location.use.inj eq))
      | false =>
        have other := enabled_reader_frozen h hb
        have eq := (h.partition _ issued).unique (.use a) .frozen cell owned other
        contradiction
  exact ⟨one i j wi wj left right distinct, one j i wj wi right left (Ne.symm distinct)⟩

theorem frozen_cell_excludes_enabled_write (h : Invariant allocation s)
    (frozen : cell ∈ s.holdings s.protocol.generation .frozen) : ¬Enabled s i cell true := by
  intro enabled
  obtain ⟨owned,issued⟩ := enabled_writer_owns h enabled
  have eq := (h.partition _ issued).unique (.use i) .frozen cell owned frozen
  contradiction

theorem enabled_within_allocation (h : Invariant allocation s)
    (enabled : Enabled s i cell write) : allocation.Contains cell := by
  obtain ⟨e,g,he,hg,use,work,hc,hw⟩ := enabled
  exact (grant_entry h hg he).2.2 hc

/-- A0's serial safety consequence recovered as an explicit restricted profile,
not a claim that all generalized traces refine the former scalar-token model. -/
def WholeWriterProfile (allocation : Footprint) (s : State Agent) : Prop :=
  ∀ i g, s.grants i = some g → g.writable = true → allocation.Within g.footprint

theorem whole_writer_profile_exclusion (h : Invariant allocation s)
    (profile : WholeWriterProfile allocation s)
    (left : Enabled s i x wi) (right : Enabled s j y wj) (distinct : i ≠ j) :
    wi = false ∧ wj = false := by
  have one (a b ca cb : Nat) (wa wb : Bool) (ha : Enabled s a ca wa)
      (hb : Enabled s b cb wb) (ne : a ≠ b) : wa = false := by
    cases wa with
    | false => rfl
    | true =>
      obtain ⟨e,g,he,hg,use,work,_,hw⟩ := ha
      have newCell := profile a g hg hw (enabled_within_allocation h hb)
      have atOther : Enabled s a cb true := ⟨e,g,he,hg,use,work,newCell,hw⟩
      have no := (overlapping_enabled_streams_are_readers h atOther hb ne).1
      contradiction
  exact ⟨one i j x y wi wj left right distinct,one j i y x wj wi right left (Ne.symm distinct)⟩
end Aurora.A
