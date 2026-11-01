import A.Invariants
import A.Simulation
import A.Metadata
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

/-- Token changes are proved safe from the concrete old location, never supplied
as operational authorization postconditions. -/
theorem move_invariant (h : Invariant allocation s)
    (pending : ∀ r p, s.payloads r = some p → p.grant.writable = true →
      s.protocol.registrations r = none →
      (move s generation location).tokens p.grant.generation = .request r)
    (executing : ∀ i g e, s.grants i = some g → s.protocol.entries i = some e →
      g.writable = true → e.sealed = false → Executing e.kind →
      (move s generation location).tokens g.generation = executingLocation e.kind i)
    (frozen : ∀ g, Frozen s g → Frozen (move s generation location) g) :
    Invariant allocation (move s generation location) := by
  constructor
  · exact h.protocol
  · exact h.grantsBound
  · exact h.grantsTotal
  · exact h.payloadBound
  · exact h.payloadTotal
  · exact h.registeredBound
  · exact pending
  · exact executing
  · intro r p hp hr; exact frozen _ (h.readerPayload r p hp hr)
  · intro i g hg hr; exact frozen _ (h.readerGrant i g hg hr)
  · intro i hi
    obtain ⟨g, hg, hf⟩ := h.readableSound i hi
    exact ⟨g, hg, frozen _ hf⟩
  · exact h.sequential

theorem gate_move_preserves (h : Invariant allocation s)
    (held : s.tokens generation = .gate owner) :
    Invariant allocation (move s generation location) := by
  apply move_invariant h
  · intro r p hp hw absent
    have old := h.pendingWriter r p hp hw absent
    apply token_move_other old
    simp [held]
  · intro i g e hg he hw hu hx
    have old := h.executingWriter i g e hg he hw hu hx
    apply token_move_other old
    cases hk : e.kind <;> simp_all [Executing, executingLocation]
  · intro g hf
    exact move_frozen hf (by intro i; simp [held])

theorem enable_preserves (h : Invariant allocation s) (hg : s.grants i = some g)
    (hf : Frozen s g.generation) : Invariant allocation (readEnable s i) := by
  constructor
  · exact h.protocol
  · exact h.grantsBound
  · exact h.grantsTotal
  · exact h.payloadBound
  · exact h.payloadTotal
  · exact h.registeredBound
  · exact h.pendingWriter
  · exact h.executingWriter
  · exact h.readerPayload
  · exact h.readerGrant
  · intro j hj
    by_cases same : j = i
    · subst j; exact ⟨g, hg, hf⟩
    · exact h.readableSound j (by simpa [readEnable, same] using hj)
  · exact h.sequential

theorem freeze_preserves (h : Invariant allocation s) (hg : s.grants i = some g)
    (held : s.tokens g.generation = .gate i) :
    Invariant allocation (readEnable (move s g.generation (.frozen i)) i) := by
  apply enable_preserves (gate_move_preserves h held) hg
  exact ⟨i, by simp [move]⟩

theorem receipt_is_sealed (h : Invariant allocation s)
    (found : s.protocol.entries i = some e) (receipt : e.receipt = true) : e.sealed = true := by
  have stopped := (h.protocol.1.entriesOK i (R.abstractEntry e) (R.project_found found)).receiptSound receipt
  cases hs : e.sealed <;> simp_all [R.abstractEntry]

theorem return_preserves (h : Invariant allocation s)
    (found : s.protocol.entries i = some e) ( _use : e.kind = .use owner)
    (receipt : e.receipt = true) (held : s.tokens generation = .use i) :
    Invariant allocation (move s generation (.gate origin)) := by
  have sealed := receipt_is_sealed h found receipt
  apply move_invariant h
  · intro r p hp hw absent
    have old := h.pendingWriter r p hp hw absent
    apply token_move_other old
    simp [held]
  · intro j g n hg hn hw hu hx
    have old := h.executingWriter j g n hg hn hw hu hx
    by_cases same : g.generation = generation
    · have loc : executingLocation n.kind j = .use i := by rw [same, held] at old; exact old.symm
      cases kind : n.kind with
      | gate a => simp [kind, Executing] at hx
      | transfer a => simp [kind, executingLocation] at loc
      | use a =>
        have ji : j = i := by simpa [kind, executingLocation] using loc
        subst j
        have ne : n = e := Option.some.inj (hn.symm.trans found)
        simp [ne, sealed] at hu
    · simpa [move, same] using old
  · intro g hf
    exact move_frozen hf (by intro j; simp [held])

theorem passive_preserves (h : Invariant allocation s) (op : Passive s.protocol p) :
    Invariant allocation (atProtocol s p) := by
  apply protocol_transport h p (R.step_preserves_invariant h.protocol (passive_erases op))
  · intro i e he; exact passive_entry_forward op he
  · intro i e he
    obtain ⟨old, ho, hg, hk, hs, _⟩ := passive_entry_backward op he
    exact ⟨old, ho, hg, hk, hs⟩
  · intro r q hq; exact passive_request_forward op hq
  · intro r q hq
    obtain ⟨old, ho, _⟩ := passive_request_backward op hq
    exact ⟨old, ho⟩
  · exact passive_registrations op
  · intro i g e hg he hw
    obtain ⟨old, ho, _, _, _, work⟩ := passive_entry_backward op he
    exact Nat.le_trans work (h.sequential i g old hg ho hw)

theorem replace_preserves (h : Invariant allocation s)
    (found : s.protocol.entries k = some old) (kind : fresh.kind = old.kind)
    (generation : fresh.generation = old.generation)
    (unsealed : fresh.sealed = false → old.sealed = false)
    (bounded : ∀ g, s.grants k = some g → g.writable = true → fresh.work ≤ 1)
    (hp : R.Invariant (R.put s.protocol k fresh)) :
    Invariant allocation (atProtocol s (R.put s.protocol k fresh)) := by
  apply protocol_transport h _ hp
  · intro i e he
    by_cases same : i = k
    · subst i
      have eq : e = old := Option.some.inj (he.symm.trans found)
      exact ⟨fresh, by simp [R.put], by simpa [eq] using generation, by simpa [eq] using kind⟩
    · exact ⟨e, by simpa [R.put, same] using he, rfl, rfl⟩
  · intro i e he
    by_cases same : i = k
    · subst i
      have eq : e = fresh := by simpa [R.put] using he.symm
      subst e
      exact ⟨old, found, generation, kind, unsealed⟩
    · exact ⟨e, by simpa [R.put, same] using he, rfl, rfl, fun x => x⟩
  · intro r q hq; exact ⟨q, hq, rfl⟩
  · intro r q hq; exact ⟨q, hq⟩
  · rfl
  · intro i g e hg he hw
    by_cases same : i = k
    · subst i
      have eq : e = fresh := by simpa [R.put] using he.symm
      subst e; exact bounded g hg hw
    · exact h.sequential i g e hg (by simpa [R.put, same] using he) hw

theorem submit_preserves (h : Invariant allocation s)
    (found : s.protocol.entries i = some e) (use : e.kind = .use g.subject)
    (granted : s.grants i = some g) (published : e.published = true)
    (notClosed : e.closed = false) (sequential : g.writable = true → e.work = 0) :
    Invariant allocation (atProtocol s (R.put s.protocol i { e with work := e.work + 1 })) := by
  apply replace_preserves (fresh := { e with work := e.work + 1 }) h found rfl rfl (fun x => x)
  · intro grant hg hw
    have same : grant = g := Option.some.inj (hg.symm.trans granted)
    have zero := sequential (by simpa [same] using hw)
    simp [zero]
  · exact R.step_preserves_invariant h.protocol
      (.submit s.protocol i e g.subject found use published notClosed)

theorem reuse_preserves (h : Invariant allocation s)
    (quiet : s.protocol.phase = .quiescent) :
    Invariant allocation (atProtocol s
      { s.protocol with generation := s.protocol.generation + 1, phase := .active }) := by
  apply protocol_transport h _ (R.step_preserves_invariant h.protocol (.reuse s.protocol quiet))
  · intro i e he; exact ⟨e, he, rfl, rfl⟩
  · intro i e he; exact ⟨e, he, rfl, rfl, fun x => x⟩
  · intro r q hq; exact ⟨q, hq, rfl⟩
  · intro r q hq; exact ⟨q, hq⟩
  · rfl
  · exact h.sequential

end Aurora.A
