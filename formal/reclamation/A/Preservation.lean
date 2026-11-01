import A.Invariants
import A.Simulation
namespace Aurora.A

variable {Agent : Type} {allocation : Extent} {s t : State Agent}

/-- A proof transport lemma, not a transition guard. -/
theorem protocol_transport (h : Invariant allocation s) (p : R.State Agent)
    (hp : R.Invariant p)
    (forward : ∀ i e, s.protocol.entries i = some e →
      ∃ n, p.entries i = some n ∧ n.generation = e.generation ∧ n.kind = e.kind)
    (backward : ∀ i n, p.entries i = some n →
      ∃ e, s.protocol.entries i = some e ∧ n.generation = e.generation ∧ n.kind = e.kind ∧
        (n.sealed = false → e.sealed = false))
    (reqForward : ∀ r q, s.protocol.requests r = some q →
      ∃ n, p.requests r = some n ∧ n.destination = q.destination)
    (reqBackward : ∀ r n, p.requests r = some n → ∃ q, s.protocol.requests r = some q)
    (registrations : p.registrations = s.protocol.registrations)
    (sequential : ∀ i g e, s.grants i = some g → p.entries i = some e →
      g.writable = true → e.work ≤ 1) :
    Invariant allocation (atProtocol s p) := by
  constructor
  · exact hp
  · intro i g hg
    obtain ⟨e, he, hgen, hsub, hb⟩ := h.grantsBound i g hg
    obtain ⟨n, hn, ngen, nkind⟩ := forward i e he
    exact ⟨n, hn, ngen.trans hgen, by simpa [nkind] using hsub, hb⟩
  · intro i n hn
    obtain ⟨e, he, _⟩ := backward i n hn
    exact h.grantsTotal i e he
  · intro r payload hpayload
    obtain ⟨q, parent, hq, hg, origin, derived⟩ := h.payloadBound r payload hpayload
    obtain ⟨n, hn, ndest⟩ := reqForward r q hq
    exact ⟨n, parent, hn, hg, origin, by simpa [ndest] using derived⟩
  · intro r n hn
    obtain ⟨q, hq⟩ := reqBackward r n hn
    exact h.payloadTotal r q hq
  · intro r i hi
    exact h.registeredBound r i (by simpa [atProtocol, registrations] using hi)
  · intro r payload hpayload hw absent
    exact h.pendingWriter r payload hpayload hw (by simpa [atProtocol, registrations] using absent)
  · intro i g n hg hn hw unsealed executing
    obtain ⟨e, he, ngen, nkind, hseal⟩ := backward i n hn
    have old := h.executingWriter i g e hg he hw (hseal unsealed) (by simpa [nkind] using executing)
    simpa [atProtocol, nkind] using old
  · exact h.readerPayload
  · exact h.readerGrant
  · exact h.readableSound
  · exact sequential

theorem move_frozen (frozen : Frozen s generation)
    (notFrozen : ∀ i, s.tokens changed ≠ .frozen i) :
    Frozen (move s changed location) generation := by
  obtain ⟨i, hi⟩ := frozen
  by_cases same : generation = changed
  · subst generation
    exact False.elim (notFrozen i hi)
  · exact ⟨i, by simpa [move, same] using hi⟩

theorem token_move_other (h : s.tokens generation = old)
    (different : old ≠ s.tokens changed) :
    (move s changed location).tokens generation = old := by
  have ne : generation ≠ changed := by intro eq; subst generation; exact different h.symm
  simpa [move, ne] using h

end Aurora.A
