import A.Completion
namespace Aurora.B
open Aurora.A

variable {Agent : Type}

/-- The admitted use starts unpublished and has no outstanding work. -/
def useEntry (generation : Nat) (subject : Agent) : R.Entry Agent :=
  { generation, kind := .use subject }

def writerEntry (generation : Nat) (subject : Agent) : R.Entry Agent :=
  { generation, kind := .use subject, published := true, work := 1 }

def acceptWriter (s : State Agent) (source nonce ticket : Nat) : State Agent :=
  atProtocol s (R.enqueue (R.putRequest s.protocol (source,nonce) ⟨none,true⟩) (.publish ticket))

def publishWriter (s : State Agent) (ticket : Nat) (e : R.Entry Agent) : State Agent :=
  atProtocol s (R.put s.protocol ticket { e with published := true })

/-- Actual request, registration, grant delivery, publication and submission.
    No byte state or assumed Enabled fact participates in admission. -/
def writerState (s : State Agent) (source nonce : Nat) (e : R.Entry Agent)
    (g : Grant Agent) (footprint : Footprint) : State Agent :=
  let a := requestState s source nonce g none footprint true false
  let b := registeredState a (source,nonce) none e g.subject ⟨child g none footprint true false,source⟩
  let c := acceptWriter b source nonce s.protocol.next
  let d := publishWriter c s.protocol.next (useEntry e.generation g.subject)
  atProtocol d (R.put d.protocol s.protocol.next (writerEntry e.generation g.subject))

private theorem append_trace (first : Trace issuer owner allocation s xs t)
    (second : Trace issuer owner allocation t ys u) : Trace issuer owner allocation s (xs ++ ys) u := by
  induction first with
  | nil => exact second
  | cons step tail ih => exact .cons step (ih second)

/-- Operational construction is generic in agent, allocation, gate ID and nonce. -/
theorem writer_trace (s : State Agent) (source nonce : Nat) (e : R.Entry Agent)
    (g : Grant Agent) (footprint : Footprint)
    (found : s.protocol.entries source = some e) (gate : e.kind = .gate g.subject)
    (granted : s.grants source = some g) (published : e.published = true) (openGate : e.closed = false)
    (fresh : s.protocol.requests (source,nonce) = none)
    (unregistered : s.protocol.registrations (source,nonce) = none)
    (within : footprint.Within g.footprint) (writable : g.writable = true)
    (free : footprint.Within (s.holdings g.generation (.gate source))) :
    Trace issuer owner allocation s [.internal,.internal,.internal,.internal,.internal]
      (writerState s source nonce e g footprint) := by
  let a := requestState s source nonce g none footprint true false
  let b := registeredState a (source,nonce) none e g.subject ⟨child g none footprint true false,source⟩
  let c := acceptWriter b source nonce s.protocol.next
  let d := publishWriter c s.protocol.next (useEntry e.generation g.subject)
  have h1 : Step issuer owner allocation s .internal a := .request s source nonce e g none footprint true false
    found gate granted published openGate fresh within (by simp) (by simp) ⟨writable,free⟩
  have h2 : Step issuer owner allocation a .internal b := .register a (source,nonce) none e g.subject
    ⟨child g none footprint true false,source⟩
    (by simp [a,requestState,putPayload,atProtocol,move,R.enqueue])
    (by simpa [a,requestState,putPayload,atProtocol,move,R.enqueue,R.putRequest] using unregistered)
    (by simpa [a,requestState,putPayload,atProtocol,move,R.enqueue,R.putRequest] using found)
    gate (by simp [a,requestState,putPayload,atProtocol,move])
  have h3 : Step issuer owner allocation b .internal c := .passive _ _ (.grant _ (source,nonce)
    s.protocol.next ⟨none,false⟩
    (by simp [a,b,requestState,registeredState,child,putGrant,putPayload,atProtocol,move,R.enqueue,R.issue,R.registerId,R.putRequest])
    (by simp [a,b,requestState,registeredState,child,putGrant,putPayload,atProtocol,move,R.enqueue,R.issue,R.registerId,R.putRequest,R.put]))
  have h4 : Step issuer owner allocation c .internal d := .passive _ _ (.publish _ s.protocol.next
    (useEntry e.generation g.subject) (by simp [c,acceptWriter,atProtocol,R.enqueue])
    (by simp [a,b,c,acceptWriter,requestState,registeredState,child,putGrant,putPayload,atProtocol,move,R.enqueue,R.issue,R.registerId,R.putRequest,R.put,R.requestedKind,useEntry])
    (by trivial) rfl)
  have h5 : Step issuer owner allocation d .internal (writerState s source nonce e g footprint) :=
    .submit _ s.protocol.next { useEntry e.generation g.subject with published := true }
      (child g none footprint true false) (by simp [d,publishWriter,atProtocol,R.put]) rfl
      (by simp [a,b,c,d,publishWriter,acceptWriter,requestState,registeredState,child,putGrant,putPayload,atProtocol,move,R.issue,R.enqueue,R.registerId,R.putRequest])
      rfl rfl (by intro _; rfl)
  exact .cons h1 (.cons h2 (.cons h3 (.cons h4 (.cons h5 (.nil _)))))

theorem writer_state_facts (s : State Agent) (source nonce : Nat) (e : R.Entry Agent)
    (g : Grant Agent) (footprint : Footprint) :
    (writerState s source nonce e g footprint).protocol.entries s.protocol.next =
      some (writerEntry e.generation g.subject) ∧
    (writerState s source nonce e g footprint).grants s.protocol.next =
      some (child g none footprint true false) := by
  simp [writerState,publishWriter,acceptWriter,requestState,registeredState,child,putGrant,putPayload,
    atProtocol,move,R.issue,R.enqueue,R.registerId,R.putRequest,R.put]

/-- A fresh nonce implies no existing registration in every reachable state.
    This is derived protocol metadata, not an additional remote admission check. -/
theorem fresh_unregistered (reachable : Reachable issuer owner allocation (s : State Agent))
    (fresh : s.protocol.requests request = none) : s.protocol.registrations request = none := by
  have invariant := reachable_invariant reachable
  cases found : s.protocol.registrations request with
  | none => rfl
  | some ticket =>
    obtain ⟨payload,present,_⟩ := invariant.registeredBound request ticket found
    obtain ⟨q,parent,requested,_⟩ := invariant.payloadBound request payload present
    rw [fresh] at requested
    cases requested

/-- One writable use is obtained through all five real A transitions. Arbitrary
    local free footprints are accepted; no fixed CPU, allocation or ticket IDs. -/
theorem admit_writer (reachable : Reachable issuer owner allocation (s : State Agent))
    (found : s.protocol.entries source = some e) (gate : e.kind = .gate g.subject)
    (granted : s.grants source = some g) (published : e.published = true) (openGate : e.closed = false)
    (fresh : s.protocol.requests (source,nonce) = none)
    (within : footprint.Within g.footprint) (writable : g.writable = true)
    (free : footprint.Within (s.holdings g.generation (.gate source))) :
    Reachable issuer owner allocation (writerState s source nonce e g footprint) ∧
    (writerState s source nonce e g footprint).protocol.entries s.protocol.next =
      some (writerEntry e.generation g.subject) ∧
    (writerState s source nonce e g footprint).grants s.protocol.next = some (child g none footprint true false) ∧
    (∀ cell, footprint.Contains cell → Enabled (writerState s source nonce e g footprint) s.protocol.next cell true) := by
  have trace := writer_trace (issuer := issuer) (owner := owner) (allocation := allocation)
    s source nonce e g footprint found gate granted published openGate fresh
    (fresh_unregistered reachable fresh) within writable free
  obtain ⟨events,history⟩ := reachable
  obtain ⟨entry,grant⟩ := writer_state_facts s source nonce e g footprint
  refine ⟨⟨_,append_trace history trace⟩,entry,grant,?_⟩
  intro cell member
  exact ⟨writerEntry e.generation g.subject,child g none footprint true false,entry,grant,rfl,(show 0 < 1 from Nat.zero_lt_succ 0),member,rfl⟩
end Aurora.B
