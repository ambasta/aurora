import A.Model

namespace Aurora.A

variable {Agent : Type} {p q : R.State Agent} {s t u v : State Agent}
variable {issuer initialSubject : Agent} {allocation : Footprint}

/-- The explicit passive whitelist contains only actual protocol actions. -/
theorem passive_erases (operation : Passive p q) : R.Step p .internal q := by
  cases operation with
  | retransmit r request found => exact .retransmit p r request found
  | duplicateRegister r destination i packet registered =>
      exact .duplicateRegister p r destination i packet registered
  | grant r i request packet found => exact .grant p r i request packet found
  | publish i e packet found kind unsealed => exact .publish p i e packet found kind unsealed
  | duplicateActivate i j e destination packet found transfer committed =>
      exact .duplicateActivate p i j e destination packet found transfer committed
  | beginClose active => exact .beginClose p active
  | requestClose i e closing found kind => exact .requestClose p i e closing found kind
  | requestUseClose i e owner found use published =>
      exact .requestUseClose p i e owner found use published
  | close i e packet found kind => exact .close p i e packet found kind
  | finishOne i n e a found use work => exact .finishOne p i n e a found use work
  | sealGate i e a found gate closed settled => exact .sealGate p i e a found gate closed settled
  | sealUse i e a found use closed drained => exact .sealUse p i e a found use closed drained
  | sendReceipt i e found kind sealed => exact .sendReceipt p i e found kind sealed
  | receiveReceipt i generation e packet found bound =>
      exact .receiveReceipt p i generation e packet found bound
  | retire i e found receipt => exact .retire p i e found receipt
  | quiesce closing empty gates => exact .quiesce p closing empty gates
  | duplicate packet present => exact .duplicate p packet present
  | lose packets subset => exact .lose p packets subset
  | stutter => exact .stutter p

@[simp] theorem initial_protocol : (initial : State Agent).protocol = R.initial := rfl

/-- Erasure forgets permission metadata, cell and access mode, not resource
    generation, ticket or observable access/reuse. No invariant is needed. -/
theorem step_erases (step : Step issuer initialSubject allocation s event t) :
    R.Step s.protocol (erase event) t.protocol := by
  cases step with
  | root active available => exact .root s.protocol initialSubject active
  | request i nonce e g destination footprint writable delegates found gate granted
      published notClosed fresh within delegation attenuate permission =>
      cases writable <;>
        exact R.Step.request s.protocol i nonce e g.subject destination found gate published notClosed fresh
  | register r destination e a payload packet absent found gate hasPayload =>
      cases writable : payload.grant.writable <;>
        simpa [writable, putGrant, atProtocol, move, mint, erase] using
          R.Step.register s.protocol r destination e a packet absent found gate
  | activate i e destination g packet found transfer pending granted =>
      cases writable : g.writable <;>
        simpa [writable, putGrant, atProtocol, move, readEnable, erase] using
          R.Step.activate s.protocol i e destination packet found transfer pending
  | submit i e g found use granted published notClosed sequential =>
      exact .submit s.protocol i e g.subject found use published notClosed
  | effect i e g cell found use granted work within =>
      exact .effect s.protocol i e g.subject found use work
  | returnUse r i e payload registered hasPayload writer origin found use bound receipt fresh =>
      exact .stutter s.protocol
  | freeze i e g footprint found gate granted within available => exact .stutter s.protocol
  | passive protocol operation => exact passive_erases operation
  | reuse quiet => exact .reuse s.protocol quiet
  | refuse => exact .stutter s.protocol

/-- Forward simulation for every finite A trace; refusal becomes protocol stutter. -/
theorem trace_erases (trace : Trace issuer initialSubject allocation s events t) :
    R.Trace s.protocol (events.map erase) t.protocol := by
  induction trace with
  | nil => exact .nil _
  | cons step tail ih => exact .cons (step_erases step) ih

theorem reachable_erases (reachable : Reachable issuer initialSubject allocation s) :
    R.Reachable s.protocol := by
  obtain ⟨events, trace⟩ := reachable
  exact ⟨events.map erase, trace_erases trace⟩

theorem reachable_protocol_invariant
    (reachable : Reachable issuer initialSubject allocation s) : R.Invariant s.protocol :=
  R.reachable_invariant (reachable_erases reachable)

/-- Reclamation safety is inherited without assuming authorization preservation.
    Authorization/non-aliasing remain separate A-layer proof obligations. -/
theorem after_reuse_no_old_access
    (reachable : Reachable issuer initialSubject allocation s)
    (reuse : Step issuer initialSubject allocation s (.reuse old) t)
    (future : Trace issuer initialSubject allocation t events u)
    (access : Step issuer initialSubject allocation u (.access generation ticket cell write) v) :
    old < generation :=
  R.after_reuse_no_old_access (reachable_protocol_invariant reachable)
    (step_erases reuse) (trace_erases future) (step_erases access)

end Aurora.A
