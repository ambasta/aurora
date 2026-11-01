import R.Invariants

namespace Aurora.R

variable {Agent : Type} {s : State Agent} {e : Entry Agent}

@[simp] theorem project_initial : project (initial : State Agent) = Q.initial := rfl

@[simp] theorem project_enqueue (s : State Agent) (p : Packet Agent) :
    project (enqueue s p) = project s := rfl

@[simp] theorem project_request (s : State Agent) (r : RequestId) (q : Request Agent) :
    project (putRequest s r q) = project s := rfl

@[simp] theorem project_registration (s : State Agent) (r : RequestId) (i : Nat) :
    project (registerId s r i) = project s := rfl

theorem project_found (found : s.entries i = some e) :
    (project s).entries i = some (abstractEntry e) := by
  simp [project, found]

@[simp] theorem project_put (s : State Agent) (i : Nat) (e : Entry Agent) :
    project (put s i e) = Q.put (project s) i (abstractEntry e) := by
  cases s
  simp only [project, put, Q.put, Q.State.mk.injEq, eq_self, true_and]
  funext j
  split <;> rfl

@[simp] theorem project_issue (s : State Agent) (g : Nat) (k : Q.Kind Agent) :
    project (issue s g k) = Q.issue (project s) g k := by
  cases s
  simp only [project, issue, put, Q.issue, Q.put, Q.State.mk.injEq, eq_self, true_and]
  funext j
  split <;> rfl

theorem project_unchanged_put (found : s.entries i = some e)
    (unchanged : abstractEntry replacement = abstractEntry e) :
    project (put s i replacement) = project s := by
  rw [project_put, unchanged]
  exact Q.put_existing (project_found found)

theorem initial_invariant : Invariant (initial : State Agent) := by
  exact ⟨Q.initial_invariant, initial_local⟩

/-- Every concrete local/coordinator action has the same observable label as an
    abstract Q action. Receipt soundness is DERIVED from permanent packet origin;
    no receiver completion-oracle test or target-state invariant is assumed. -/
theorem step_refines (h : LocalInvariant s) (step : Step s event t) :
    Q.Step (project s) event (project t) := by
  cases step with
  | root a active =>
      simpa using Q.Step.root (project s) a active
  | request i nonce e a destination found gate published notClosed fresh =>
      simpa using Q.Step.stutter (project s)
  | retransmit r q found =>
      simpa using Q.Step.stutter (project s)
  | register r destination e a packet absent found gate =>
      have unsealed := registration_unsealed h packet absent found gate
      have possible : (abstractEntry e).possible = true := by simp [abstractEntry, unsealed]
      cases destination with
      | none =>
          simpa [requestedKind] using
            Q.Step.admit (project s) r.1 (abstractEntry e) a (project_found found) gate possible
      | some d =>
          simpa [requestedKind] using
            Q.Step.send (project s) r.1 (abstractEntry e) a d (project_found found) gate possible
  | duplicateRegister r destination i packet registered =>
      simpa using Q.Step.stutter (project s)
  | grant r i q packet found =>
      simpa using Q.Step.stutter (project s)
  | publish i e packet found kind unsealed =>
      rw [project_unchanged_put (replacement := { e with published := true }) found rfl]
      exact Q.Step.stutter (project s)
  | activate i e destination packet found transfer pending =>
      have unsealed : e.sealed = false := by
        simpa [pending] using h.transferSeal i e destination found transfer
      have possible : (abstractEntry e).possible = true := by simp [abstractEntry, unsealed]
      have resolved_project : abstractEntry (resolved e s.next) = Q.resolved (abstractEntry e) := rfl
      simpa [resolved_project] using
        Q.Step.activate (project s) i (abstractEntry e) destination (project_found found) transfer possible
  | duplicateActivate i j e destination packet found transfer committed =>
      simpa using Q.Step.stutter (project s)
  | beginClose active =>
      exact Q.Step.beginClose (project s) active
  | requestClose i e closing found kind =>
      simpa using Q.Step.stutter (project s)
  | requestUseClose i e owner found use published =>
      simpa using Q.Step.stutter (project s)
  | close i e packet found kind =>
      rw [project_unchanged_put (replacement := { e with closed := true }) found rfl]
      exact Q.Step.stutter (project s)
  | submit i e a found use published notClosed =>
      rw [project_unchanged_put (replacement := { e with work := e.work + 1 }) found rfl]
      exact Q.Step.stutter (project s)
  | effect i e a found use work =>
      have unsealed := work_unsealed h found use work
      exact Q.Step.access (project s) i (abstractEntry e) a (project_found found) use
        (by simp [abstractEntry, unsealed])
  | finishOne i n e a found use work =>
      rw [project_unchanged_put (replacement := { e with work := n }) found rfl]
      exact Q.Step.stutter (project s)
  | sealGate i e a found gate closed settled =>
      rw [project_put]
      exact Q.Step.hardwareStop (project s) i (abstractEntry e) (project_found found)
  | sealUse i e a found use closed drained =>
      rw [project_put]
      exact Q.Step.hardwareStop (project s) i (abstractEntry e) (project_found found)
  | sendReceipt i e found kind sealed =>
      simpa using Q.Step.stutter (project s)
  | receiveReceipt i generation e packet found bound =>
      have sealed := receipt_sealed h packet found
      rw [project_put]
      exact Q.Step.ack (project s) i generation (abstractEntry e) (project_found found) bound
        (by simp [abstractEntry, sealed])
  | retire i e found receipt =>
      rw [project_put]
      exact Q.Step.retire (project s) i (abstractEntry e) (project_found found) receipt
  | quiesce closing empty gates =>
      apply Q.Step.quiesce (project s) closing
      · intro i e found
        simp only [project] at found
        cases concrete : s.entries i with
        | none => simp [concrete] at found
        | some c =>
            simp only [concrete, Option.map_some, Option.some.injEq] at found
            subst e
            exact empty i c concrete
      · intro i e a found gate
        simp only [project] at found
        cases concrete : s.entries i with
        | none => simp [concrete] at found
        | some c =>
            simp only [concrete, Option.map_some, Option.some.injEq] at found
            subst e
            exact gates i c a concrete gate
  | reuse quiet =>
      exact Q.Step.reuse (project s) quiet
  | duplicate p present =>
      simpa using Q.Step.stutter (project s)
  | lose packets subset =>
      exact Q.Step.stutter (project s)
  | stutter => exact Q.Step.stutter (project s)

end Aurora.R
