import R.Preservation
import A.Footprint
namespace Aurora.A

structure Grant (Agent : Type) where
  issuer : Agent
  subject : Agent
  generation : Nat
  footprint : Footprint
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
  | gate (ticket : Nat) | request (id : R.RequestId)
  | transfer (ticket : Nat) | use (ticket : Nat) | frozen
  deriving DecidableEq, Repr

structure State (Agent : Type) where
  protocol : R.State Agent := R.initial
  grants : Nat → Option (Grant Agent) := fun _ => none
  payloads : R.RequestId → Option (Payload Agent) := fun _ => none
  readable : Nat → Footprint := fun _ => []
  issued : Nat → Bool := fun _ => false
  returned : Nat → Bool := fun _ => false
  /-- Gate holdings are endpoint-local free inventory. Other locations are
  abstract protocol escrow accounting, not remotely read admission oracles. -/
  holdings : Nat → Location → Footprint := fun _ _ => []

def initial : State Agent := {}
def atProtocol (s : State Agent) (p : R.State Agent) : State Agent := { s with protocol := p }
def putGrant (s : State Agent) (i : Nat) (g : Grant Agent) : State Agent :=
  { s with grants := fun j => if j = i then some g else s.grants j }
def putPayload (s : State Agent) (r : R.RequestId) (p : Payload Agent) : State Agent :=
  { s with payloads := fun q => if q = r then some p else s.payloads q }
/-- Total accounting update. Membership at the source is PROVED, never an
extra guard at registration, activation or return. Destination credit uses the
immutable moved footprint, not a remote source-inventory read. -/
def move (s : State Agent) (generation : Nat) (source destination : Location)
    (footprint : Footprint) : State Agent :=
  { s with holdings := fun gen => if gen = generation then
      Inventory.move (s.holdings gen) source destination footprint else s.holdings gen }
def mint (s : State Agent) (generation gate : Nat) (allocation : Footprint) : State Agent :=
  { s with
    issued := fun gen => if gen = generation then true else s.issued gen
    holdings := fun gen loc => if gen = generation then
      (if loc = .gate gate then allocation else []) else s.holdings gen loc }
def readEnable (s : State Agent) (i : Nat) (footprint : Footprint) : State Agent :=
  { s with readable := fun j => if j = i then s.readable j ++ footprint else s.readable j }
def markReturned (s : State Agent) (i : Nat) : State Agent :=
  { s with returned := fun j => if j = i then true else s.returned j }
def child (g : Grant Agent) (destination : Option Agent) (footprint : Footprint)
    (writable delegates : Bool) : Grant Agent :=
  { issuer := g.subject, subject := destination.getD g.subject,
    generation := g.generation, footprint, writable, delegates }
def registerLocation (destination : Option Agent) (i : Nat) : Location :=
  match destination with | none => .use i | some _ => .transfer i
def Frozen (s : State Agent) (generation : Nat) (footprint : Footprint) : Prop :=
  footprint.Within (s.holdings generation .frozen)

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
inductive Step (issuer initialSubject : Agent) (allocation : Footprint) :
    State Agent → Event → State Agent → Prop where
  | root (s : State Agent) (active : s.protocol.phase = .active)
      (available : s.issued s.protocol.generation = false) :
      Step issuer initialSubject allocation s .internal
        (mint (putGrant (atProtocol s
          (R.enqueue (R.issue s.protocol s.protocol.generation (.gate initialSubject))
            (.publish s.protocol.next))) s.protocol.next
          ⟨issuer, initialSubject, s.protocol.generation, allocation, true, true⟩)
          s.protocol.generation s.protocol.next allocation)
  | request (s : State Agent) i nonce e g destination footprint writable delegates
      (found : s.protocol.entries i = some e) (gate : e.kind = .gate g.subject)
      (granted : s.grants i = some g) (published : e.published = true)
      (notClosed : e.closed = false) (fresh : s.protocol.requests (i, nonce) = none)
      (within : footprint.Within g.footprint)
      (delegation : destination.isSome = true → g.delegates = true)
      (attenuate : delegates = true → g.delegates = true)
      (permission : if writable then g.writable = true ∧ footprint.Within (s.holdings g.generation (.gate i))
                    else footprint.Within (s.readable i)) :
      Step issuer initialSubject allocation s .internal
        (let t := putPayload (atProtocol s
            (R.enqueue (R.putRequest s.protocol (i, nonce) ⟨destination, false⟩)
              (.register (i, nonce) destination))) (i, nonce)
            ⟨child g destination footprint writable delegates, i⟩
         if writable then move t g.generation (.gate i) (.request (i, nonce)) footprint else t)
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
         if p.grant.writable then move t p.grant.generation (.request r)
           (registerLocation destination s.protocol.next) p.grant.footprint else t)
  | activate (s : State Agent) i e destination g
      (packet : R.Packet.activate i ∈ s.protocol.packets)
      (found : s.protocol.entries i = some e) (transfer : e.kind = .transfer destination)
      (pending : e.receiver = none) (granted : s.grants i = some g) :
      Step issuer initialSubject allocation s .internal
        (let t := putGrant (atProtocol s
            (R.enqueue (R.issue (R.put s.protocol i (R.resolved e s.protocol.next))
              e.generation (.gate destination)) (.publish s.protocol.next))) s.protocol.next g
         if g.writable then move t g.generation (.transfer i) (.gate s.protocol.next) g.footprint
         else readEnable t s.protocol.next g.footprint)
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
      (work : 0 < e.work) (within : g.footprint.Contains cell) :
      Step issuer initialSubject allocation s (.access e.generation i cell g.writable) s
  /-- Abstract atomic authority return, not a decentralized receipt transport.
  The exact fresh use-ticket marker is permanent, including after reborrow/reuse. -/
  | returnUse (s : State Agent) r i e p
      (registered : s.protocol.registrations r = some i)
      (payload : s.payloads r = some p) (writer : p.grant.writable = true)
      (origin : p.origin = r.1)
      (found : s.protocol.entries i = some e) (use : e.kind = .use p.grant.subject)
      (bound : e.generation = p.grant.generation)
      (receipt : e.receipt = true) (fresh : s.returned i = false) :
      Step issuer initialSubject allocation s .internal
        (markReturned (move s p.grant.generation (.use i) (.gate p.origin) p.grant.footprint) i)
  /-- Owner-initiated freeze consumes only locally free cells; immutable read
  aliases are not additional exclusive backing claims. No thaw exists. -/
  | freeze (s : State Agent) i e g footprint
      (found : s.protocol.entries i = some e) (gate : e.kind = .gate g.subject)
      (granted : s.grants i = some g) (within : footprint.Within g.footprint)
      (available : footprint.Within (s.holdings g.generation (.gate i))) :
      Step issuer initialSubject allocation s .internal
        (readEnable (move s g.generation (.gate i) .frozen footprint) i footprint)
  | passive (s : State Agent) p (operation : Passive s.protocol p) :
      Step issuer initialSubject allocation s .internal (atProtocol s p)
  | reuse (s : State Agent) (quiet : s.protocol.phase = .quiescent) :
      Step issuer initialSubject allocation s (.reuse s.protocol.generation)
        (atProtocol s { s.protocol with generation := s.protocol.generation + 1, phase := .active })
  | refuse (s : State Agent) : Step issuer initialSubject allocation s .refused s

inductive Trace (issuer initialSubject : Agent) (allocation : Footprint) :
    State Agent → List Event → State Agent → Prop where
  | nil (s) : Trace issuer initialSubject allocation s [] s
  | cons : Step issuer initialSubject allocation s event t →
      Trace issuer initialSubject allocation t events u →
      Trace issuer initialSubject allocation s (event :: events) u

def Reachable (issuer initialSubject : Agent) (allocation : Footprint) (s : State Agent) : Prop :=
  ∃ events, Trace issuer initialSubject allocation initial events s
end Aurora.A
