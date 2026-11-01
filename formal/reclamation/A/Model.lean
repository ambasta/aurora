import R.Preservation
namespace Aurora.A

structure Extent where
  first : Nat
  limit : Nat
  deriving DecidableEq, Repr

def Extent.Within (c p : Extent) : Prop := p.first ≤ c.first ∧ c.first ≤ c.limit ∧ c.limit ≤ p.limit
def Extent.Contains (e : Extent) (cell : Nat) : Prop := e.first ≤ cell ∧ cell < e.limit

instance (c p : Extent) : Decidable (c.Within p) :=
  inferInstanceAs (Decidable (p.first ≤ c.first ∧ c.first ≤ c.limit ∧ c.limit ≤ p.limit))
instance (e : Extent) (cell : Nat) : Decidable (e.Contains cell) :=
  inferInstanceAs (Decidable (e.first ≤ cell ∧ cell < e.limit))

structure Grant (Agent : Type) where
  issuer : Agent
  subject : Agent
  generation : Nat
  extent : Extent
  writable : Bool
  delegates : Bool
  deriving Repr

/-- Immutable extra wire payload, decoded by stable request ID; not remote
mutable endpoint state. Original origin/ceiling survive narrower use requests. -/
structure Payload (Agent : Type) where
  grant : Grant Agent
  origin : Nat
  deriving Repr

inductive Location where
  | unissued | gate (ticket : Nat) | request (id : R.RequestId)
  | transfer (ticket : Nat) | use (ticket : Nat) | frozen (issuerGate : Nat)
  deriving DecidableEq, Repr

structure State (Agent : Type) where
  protocol : R.State Agent := R.initial
  grants : Nat → Option (Grant Agent) := fun _ => none
  payloads : R.RequestId → Option (Payload Agent) := fun _ => none
  readable : Nat → Bool := fun _ => false
  tokens : Nat → Location := fun _ => .unissued

def initial : State Agent := {}
def atProtocol (s : State Agent) (p : R.State Agent) : State Agent := { s with protocol := p }
def putGrant (s : State Agent) (i : Nat) (g : Grant Agent) : State Agent :=
  { s with grants := fun j => if j = i then some g else s.grants j }
def putPayload (s : State Agent) (r : R.RequestId) (p : Payload Agent) : State Agent :=
  { s with payloads := fun q => if q = r then some p else s.payloads q }
def move (s : State Agent) (generation : Nat) (whereTo : Location) : State Agent :=
  { s with tokens := fun g => if g = generation then whereTo else s.tokens g }
def readEnable (s : State Agent) (i : Nat) : State Agent :=
  { s with readable := fun j => if j = i then true else s.readable j }
def child (g : Grant Agent) (destination : Option Agent) (extent : Extent)
    (writable delegates : Bool) : Grant Agent :=
  { issuer := g.subject, subject := destination.getD g.subject,
    generation := g.generation, extent, writable, delegates }
def registerLocation (destination : Option Agent) (i : Nat) : Location :=
  match destination with | none => .use i | some _ => .transfer i
def Frozen (s : State Agent) (generation : Nat) : Prop := ∃ i, s.tokens generation = .frozen i

inductive Event where
  | internal | refused
  | access (generation ticket cell : Nat) (write : Bool)
  | reuse (oldGeneration : Nat)
  deriving DecidableEq, Repr

def erase : Event → Q.Event
  | .internal | .refused => .internal
  | .access generation ticket _ _ => .access generation ticket
  | .reuse generation => .reuse generation

/-- Syntactic whitelist: no new admission, registration, activation, submission
or effect can bypass permission bookkeeping. These are not invariant premises. -/
inductive Passive : R.State Agent → R.State Agent → Prop where
  | retransmit (s : R.State Agent) r q (found : s.requests r = some q) :
      Passive s (R.enqueue s (.register r q.destination))
  | duplicateRegister (s : R.State Agent) r destination i
      (packet : R.Packet.register r destination ∈ s.packets)
      (registered : s.registrations r = some i) : Passive s (R.enqueue s (.grant r i))
  | grant (s : R.State Agent) r i q (packet : R.Packet.grant r i ∈ s.packets)
      (found : s.requests r = some q) :
      Passive s (R.enqueue (R.putRequest s r { q with settled := true }) (R.grantPacket q i))
  | publish (s : R.State Agent) i e (packet : R.Packet.publish i ∈ s.packets)
      (found : s.entries i = some e) (kind : R.Closable e.kind) (unsealed : e.sealed = false) :
      Passive s (R.put s i { e with published := true })
  | duplicateActivate (s : R.State Agent) i j e destination
      (packet : R.Packet.activate i ∈ s.packets) (found : s.entries i = some e)
      (transfer : e.kind = .transfer destination) (committed : e.receiver = some j) :
      Passive s (R.enqueue s (.publish j))
  | beginClose (s : R.State Agent) (active : s.phase = .active) :
      Passive s { s with phase := .closing }
  | requestClose (s : R.State Agent) i e (closing : s.phase = .closing)
      (found : s.entries i = some e) (kind : R.Closable e.kind) : Passive s (R.enqueue s (.close i))
  | requestUseClose (s : R.State Agent) i e owner (found : s.entries i = some e)
      (use : e.kind = .use owner) (published : e.published = true) :
      Passive s (R.enqueue s (.close i))
  | close (s : R.State Agent) i e (packet : R.Packet.close i ∈ s.packets)
      (found : s.entries i = some e) (kind : R.Closable e.kind) :
      Passive s (R.put s i { e with closed := true })
  | finishOne (s : R.State Agent) i n e a (found : s.entries i = some e)
      (use : e.kind = .use a) (work : e.work = n + 1) : Passive s (R.put s i { e with work := n })
  | sealGate (s : R.State Agent) i e a (found : s.entries i = some e)
      (gate : e.kind = .gate a) (closed : e.closed = true) (settled : R.Settled s i) :
      Passive s (R.put s i { e with sealed := true })
  | sealUse (s : R.State Agent) i e a (found : s.entries i = some e)
      (use : e.kind = .use a) (closed : e.closed = true) (drained : e.work = 0) :
      Passive s (R.put s i { e with sealed := true })
  | sendReceipt (s : R.State Agent) i e (found : s.entries i = some e)
      (kind : R.Closable e.kind) (sealed : e.sealed = true) :
      Passive s (R.enqueue s (.receipt e.generation i))
  | receiveReceipt (s : R.State Agent) i generation e
      (packet : R.Packet.receipt generation i ∈ s.packets)
      (found : s.entries i = some e) (bound : e.generation = generation) :
      Passive s (R.put s i { e with receipt := true })
  | retire (s : R.State Agent) i e (found : s.entries i = some e)
      (receipt : e.receipt = true) : Passive s (R.put s i { e with live := false })
  | quiesce (s : R.State Agent) (closing : s.phase = .closing)
      (empty : R.LedgerEmpty s) (gates : R.GatesAcknowledged s) :
      Passive s { s with phase := .quiescent }
  | duplicate (s : R.State Agent) p (present : p ∈ s.packets) : Passive s (R.enqueue s p)
  | lose (s : R.State Agent) packets (subset : ∀ p, p ∈ packets → p ∈ s.packets) :
      Passive s { s with packets }
  | stutter (s : R.State Agent) : Passive s s

/-- Trusted allocation supplies one grant per fresh generation, not crypto or
arbitrary principal authentication. An allocation is not a global system lock. -/
inductive Step (issuer initialSubject : Agent) (allocation : Extent) :
    State Agent → Event → State Agent → Prop where
  | root (s : State Agent) (active : s.protocol.phase = .active)
      (valid : allocation.first ≤ allocation.limit)
      (available : s.tokens s.protocol.generation = .unissued) :
      Step issuer initialSubject allocation s .internal
        (move (putGrant (atProtocol s
          (R.enqueue (R.issue s.protocol s.protocol.generation (.gate initialSubject))
            (.publish s.protocol.next))) s.protocol.next
          ⟨issuer, initialSubject, s.protocol.generation, allocation, true, true⟩)
          s.protocol.generation (.gate s.protocol.next))
  | request (s : State Agent) i nonce e g destination extent writable delegates
      (found : s.protocol.entries i = some e) (gate : e.kind = .gate g.subject)
      (granted : s.grants i = some g) (published : e.published = true)
      (notClosed : e.closed = false) (fresh : s.protocol.requests (i, nonce) = none)
      (within : extent.Within g.extent)
      (delegation : destination.isSome = true → g.delegates = true)
      (attenuate : delegates = true → g.delegates = true)
      (permission : if writable then g.writable = true ∧ s.tokens g.generation = .gate i
                    else s.readable i = true) :
      Step issuer initialSubject allocation s .internal
        (let t := putPayload (atProtocol s
            (R.enqueue (R.putRequest s.protocol (i, nonce) ⟨destination, false⟩)
              (.register (i, nonce) destination))) (i, nonce)
            ⟨child g destination extent writable delegates, i⟩
         if writable then move t g.generation (.request (i, nonce)) else t)
  | register (s : State Agent) r destination e a p
      (packet : R.Packet.register r destination ∈ s.protocol.packets)
      (absent : s.protocol.registrations r = none)
      (found : s.protocol.entries r.1 = some e) (gate : e.kind = .gate a)
      (payload : s.payloads r = some p) :
      Step issuer initialSubject allocation s .internal
        (let t := putGrant (atProtocol s
            (R.enqueue (R.registerId
              (R.issue s.protocol e.generation (R.requestedKind a destination)) r s.protocol.next)
              (.grant r s.protocol.next))) s.protocol.next p.grant
         if p.grant.writable then move t p.grant.generation
           (registerLocation destination s.protocol.next) else t)
  | activate (s : State Agent) i e destination g
      (packet : R.Packet.activate i ∈ s.protocol.packets)
      (found : s.protocol.entries i = some e) (transfer : e.kind = .transfer destination)
      (pending : e.receiver = none) (granted : s.grants i = some g) :
      Step issuer initialSubject allocation s .internal
        (let t := putGrant (atProtocol s
            (R.enqueue (R.issue (R.put s.protocol i (R.resolved e s.protocol.next))
              e.generation (.gate destination)) (.publish s.protocol.next))) s.protocol.next g
         if g.writable then move t g.generation (.gate s.protocol.next)
         else readEnable t s.protocol.next)
  | submit (s : State Agent) i e g (found : s.protocol.entries i = some e)
      (use : e.kind = .use g.subject) (granted : s.grants i = some g)
      (published : e.published = true) (notClosed : e.closed = false)
      (sequential : g.writable = true → e.work = 0) :
      Step issuer initialSubject allocation s .internal
        (atProtocol s (R.put s.protocol i { e with work := e.work + 1 }))
  /- A writable work item is ONE sequential access stream, not an internally
     race-free GPU job inferred from its command count or endpoint identity. -/
  | effect (s : State Agent) i e g cell (found : s.protocol.entries i = some e)
      (use : e.kind = .use g.subject) (granted : s.grants i = some g)
      (work : 0 < e.work) (within : g.extent.Contains cell) :
      Step issuer initialSubject allocation s (.access e.generation i cell g.writable) s
  | returnUse (s : State Agent) r i e p
      (registered : s.protocol.registrations r = some i)
      (payload : s.payloads r = some p) (writer : p.grant.writable = true)
      (found : s.protocol.entries i = some e) (use : e.kind = .use p.grant.subject)
      (receipt : e.receipt = true) (held : s.tokens p.grant.generation = .use i) :
      Step issuer initialSubject allocation s .internal
        (move s p.grant.generation (.gate p.origin))
  | freeze (s : State Agent) i g (granted : s.grants i = some g)
      (held : s.tokens g.generation = .gate i) :
      Step issuer initialSubject allocation s .internal
        (readEnable (move s g.generation (.frozen i)) i)
  | passive (s : State Agent) p (operation : Passive s.protocol p) :
      Step issuer initialSubject allocation s .internal (atProtocol s p)
  | reuse (s : State Agent) (quiet : s.protocol.phase = .quiescent) :
      Step issuer initialSubject allocation s (.reuse s.protocol.generation)
        (atProtocol s { s.protocol with generation := s.protocol.generation + 1, phase := .active })
  | refuse (s : State Agent) : Step issuer initialSubject allocation s .refused s

inductive Trace (issuer initialSubject : Agent) (allocation : Extent) :
    State Agent → List Event → State Agent → Prop where
  | nil (s) : Trace issuer initialSubject allocation s [] s
  | cons : Step issuer initialSubject allocation s event t →
      Trace issuer initialSubject allocation t events u →
      Trace issuer initialSubject allocation s (event :: events) u

def Reachable (issuer initialSubject : Agent) (allocation : Extent) (s : State Agent) : Prop :=
  ∃ events, Trace issuer initialSubject allocation initial events s
end Aurora.A
