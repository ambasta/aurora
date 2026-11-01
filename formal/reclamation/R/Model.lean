import Q.Safety

/-! Asynchronous endpoint protocol over a per-root sequential registration service.
No ISA, durable recovery, fairness or decentralized-registration claim. Immutable
metadata is carried with messages; mutable endpoint and coordinator fields have
separate owners despite appearing in one mathematical state. -/
namespace Aurora.R

abbrev RequestId := Nat × Nat -- source activation ticket, endpoint-local nonce

structure Entry (Agent : Type) where
  generation : Nat
  kind : Q.Kind Agent
  live : Bool := true                 -- coordinator
  receipt : Bool := false             -- coordinator
  receiver : Option Nat := none       -- coordinator transfer commit/dedup
  published : Bool := false           -- endpoint: historical publication
  closed : Bool := false              -- endpoint: admission/submission disabled
  sealed : Bool := false              -- endpoint: permanent completion tombstone
  work : Nat := 0                     -- endpoint: actual outstanding work
  deriving Repr

structure Request (Agent : Type) where
  destination : Option Agent         -- none = use at source; some = delegation
  settled : Bool := false            -- endpoint-owned, never read by coordinator
  deriving Repr

inductive Packet (Agent : Type) where
  | register (request : RequestId) (destination : Option Agent)
  | grant (request : RequestId) (ticket : Nat)
  | publish (ticket : Nat)
  | activate (ticket : Nat)
  | close (ticket : Nat)
  | receipt (generation ticket : Nat)
  deriving Repr

structure State (Agent : Type) where
  generation : Nat := 0
  phase : Q.Phase := .active
  next : Nat := 0
  entries : Nat → Option (Entry Agent) := fun _ => none
  requests : RequestId → Option (Request Agent) := fun _ => none
  registrations : RequestId → Option Nat := fun _ => none -- coordinator only
  packets : List (Packet Agent) := []

def initial : State Agent := {}

def abstractEntry (e : Entry Agent) : Q.Entry Agent :=
  ⟨e.generation, e.kind, e.live, !e.sealed, e.receipt⟩

def project (s : State Agent) : Q.State Agent :=
  { generation := s.generation, phase := s.phase, next := s.next,
    entries := fun i => (s.entries i).map abstractEntry }

def put (s : State Agent) (i : Nat) (e : Entry Agent) : State Agent :=
  { s with entries := fun j => if j = i then some e else s.entries j }

def putRequest (s : State Agent) (r : RequestId) (q : Request Agent) : State Agent :=
  { s with requests := fun a => if a = r then some q else s.requests a }

def registerId (s : State Agent) (r : RequestId) (i : Nat) : State Agent :=
  { s with registrations := fun a => if a = r then some i else s.registrations a }

def enqueue (s : State Agent) (p : Packet Agent) : State Agent :=
  { s with packets := p :: s.packets }

/-- Fresh reserved endpoints denote untouched default state, not atomic remote
publication. Only delivery of publication/close messages exposes/tombstones them. -/
def issue (s : State Agent) (generation : Nat) (kind : Q.Kind Agent) : State Agent :=
  { put s s.next { generation, kind } with next := s.next + 1 }

def requestedKind (owner : Agent) : Option Agent → Q.Kind Agent
  | none => .use owner
  | some destination => .transfer destination

def grantPacket (q : Request Agent) (i : Nat) : Packet Agent :=
  match q.destination with
  | none => .publish i
  | some _ => .activate i

def resolved (e : Entry Agent) (receiver : Nat) : Entry Agent :=
  { e with live := false, receipt := true, receiver := some receiver, closed := true, sealed := true }

def Closable : Q.Kind Agent → Prop
  | .gate _ | .use _ => True
  | .transfer _ => False

/-- Reads only source endpoint's retained pending-operation records. -/
def Settled (s : State Agent) (source : Nat) : Prop :=
  ∀ r q, s.requests r = some q → r.1 = source → q.settled = true

def LedgerEmpty (s : State Agent) : Prop :=
  ∀ i e, s.entries i = some e → e.live = false

def GatesAcknowledged (s : State Agent) : Prop :=
  ∀ i e c, s.entries i = some e → e.kind = .gate c → e.receipt = true

inductive Step : State Agent → Q.Event → State Agent → Prop where
  | root (s : State Agent) (a : Agent) (active : s.phase = .active) :
      Step s .internal (enqueue (issue s s.generation (.gate a)) (.publish s.next))
  | request (s : State Agent) (i nonce : Nat) (e : Entry Agent) (a : Agent)
      (destination : Option Agent) (found : s.entries i = some e)
      (gate : e.kind = .gate a) (published : e.published = true)
      (notClosed : e.closed = false) (fresh : s.requests (i, nonce) = none) :
      Step s .internal (enqueue (putRequest s (i, nonce) ⟨destination, false⟩)
        (.register (i, nonce) destination))
  | retransmit (s : State Agent) (r : RequestId) (q : Request Agent)
      (found : s.requests r = some q) :
      Step s .internal (enqueue s (.register r q.destination))
  /- No endpoint settled/sealed/physical test in this coordinator handler. -/
  | register (s : State Agent) (r : RequestId) (destination : Option Agent)
      (e : Entry Agent) (a : Agent)
      (packet : Packet.register r destination ∈ s.packets)
      (absent : s.registrations r = none) (found : s.entries r.1 = some e)
      (gate : e.kind = .gate a) :
      Step s .internal (enqueue
        (registerId (issue s e.generation (requestedKind a destination)) r s.next)
        (.grant r s.next))
  | duplicateRegister (s : State Agent) (r : RequestId) (destination : Option Agent)
      (i : Nat) (packet : Packet.register r destination ∈ s.packets)
      (registered : s.registrations r = some i) :
      Step s .internal (enqueue s (.grant r i))
  /- Endpoint handler reads only its local request and received payload.
      Packet provenance, not a remote-table read, proves correct binding. -/
  | grant (s : State Agent) (r : RequestId) (i : Nat) (q : Request Agent)
      (packet : Packet.grant r i ∈ s.packets) (found : s.requests r = some q) :
      Step s .internal (enqueue (putRequest s r { q with settled := true })
        (grantPacket q i))
  | publish (s : State Agent) (i : Nat) (e : Entry Agent)
      (packet : Packet.publish i ∈ s.packets) (found : s.entries i = some e)
      (kind : Closable e.kind) (unsealed : e.sealed = false) :
      Step s .internal (put s i { e with published := true })
  | activate (s : State Agent) (i : Nat) (e : Entry Agent) (destination : Agent)
      (packet : Packet.activate i ∈ s.packets) (found : s.entries i = some e)
      (transfer : e.kind = .transfer destination) (pending : e.receiver = none) :
      Step s .internal (enqueue
        (issue (put s i (resolved e s.next)) e.generation (.gate destination))
        (.publish s.next))
  | duplicateActivate (s : State Agent) (i j : Nat) (e : Entry Agent)
      (destination : Agent) (packet : Packet.activate i ∈ s.packets)
      (found : s.entries i = some e) (transfer : e.kind = .transfer destination)
      (committed : e.receiver = some j) :
      Step s .internal (enqueue s (.publish j))
  | beginClose (s : State Agent) (active : s.phase = .active) :
      Step s .internal { s with phase := .closing }
  | requestClose (s : State Agent) (i : Nat) (e : Entry Agent)
      (closing : s.phase = .closing) (found : s.entries i = some e)
      (kind : Closable e.kind) :
      Step s .internal (enqueue s (.close i))
  | close (s : State Agent) (i : Nat) (e : Entry Agent)
      (packet : Packet.close i ∈ s.packets) (found : s.entries i = some e)
      (kind : Closable e.kind) :
      Step s .internal (put s i { e with closed := true })
  | submit (s : State Agent) (i : Nat) (e : Entry Agent) (a : Agent)
      (found : s.entries i = some e) (use : e.kind = .use a)
      (published : e.published = true) (notClosed : e.closed = false) :
      Step s .internal (put s i { e with work := e.work + 1 })
  /- Physical effects do not read current generation, phase, ledger or receipts. -/
  | effect (s : State Agent) (i : Nat) (e : Entry Agent) (a : Agent)
      (found : s.entries i = some e) (use : e.kind = .use a) (work : 0 < e.work) :
      Step s (.access e.generation i) s
  /- Primitive: removal of one ACTUAL outstanding work item, not receipt of a
      duplicate-prone completion packet. Removed work cannot produce later effects.
      This operational contract still needs a target-specific implementation proof. -/
  | finishOne (s : State Agent) (i n : Nat) (e : Entry Agent) (a : Agent)
      (found : s.entries i = some e) (use : e.kind = .use a) (work : e.work = n + 1) :
      Step s .internal (put s i { e with work := n })
  | sealGate (s : State Agent) (i : Nat) (e : Entry Agent) (a : Agent)
      (found : s.entries i = some e) (gate : e.kind = .gate a)
      (closed : e.closed = true) (settled : Settled s i) :
      Step s .internal (put s i { e with sealed := true })
  | sealUse (s : State Agent) (i : Nat) (e : Entry Agent) (a : Agent)
      (found : s.entries i = some e) (use : e.kind = .use a)
      (closed : e.closed = true) (drained : e.work = 0) :
      Step s .internal (put s i { e with sealed := true })
  | sendReceipt (s : State Agent) (i : Nat) (e : Entry Agent)
      (found : s.entries i = some e) (kind : Closable e.kind) (sealed : e.sealed = true) :
      Step s .internal (enqueue s (.receipt e.generation i))
  /- Checks only the immutable retained ticket binding. NO sealed/work oracle. -/
  | receiveReceipt (s : State Agent) (i generation : Nat) (e : Entry Agent)
      (packet : Packet.receipt generation i ∈ s.packets)
      (found : s.entries i = some e) (bound : e.generation = generation) :
      Step s .internal (put s i { e with receipt := true })
  | retire (s : State Agent) (i : Nat) (e : Entry Agent)
      (found : s.entries i = some e) (receipt : e.receipt = true) :
      Step s .internal (put s i { e with live := false })
  | quiesce (s : State Agent) (closing : s.phase = .closing)
      (empty : LedgerEmpty s) (gates : GatesAcknowledged s) :
      Step s .internal { s with phase := .quiescent }
  | reuse (s : State Agent) (quiet : s.phase = .quiescent) :
      Step s (.reuse s.generation)
        { s with generation := s.generation + 1, phase := .active }
  | duplicate (s : State Agent) (p : Packet Agent) (present : p ∈ s.packets) :
      Step s .internal (enqueue s p)
  | lose (s : State Agent) (packets : List (Packet Agent))
      (subset : ∀ p, p ∈ packets → p ∈ s.packets) :
      Step s .internal { s with packets }
  | stutter (s : State Agent) : Step s .internal s

inductive Trace : State Agent → List Q.Event → State Agent → Prop where
  | nil (s) : Trace s [] s
  | cons : Step s a t → Trace t as u → Trace s (a :: as) u

def Reachable (s : State Agent) : Prop := ∃ events, Trace initial events s

end Aurora.R
