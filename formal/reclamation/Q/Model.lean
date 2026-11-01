import Std

/-!
One physical backing root, arbitrary CPU type, mathematical generations and
fresh ticket IDs. All aliases of this backing share this registry. `possible`
is hardware-semantic state, not computed from the live ledger or current epoch.
The three tags have DIFFERENT effects: gate admission, use execution, transfer
activation. Hardware fence/drain/cancel semantics are assumptions of this LTS,
not a proof of the software producing an acknowledgment or of any CPU ISA.
-/
namespace Aurora.Q

inductive Phase where
  | active | closing | quiescent
  deriving DecidableEq, Repr

inductive Kind (Cpu : Type) where
  | gate (cpu : Cpu)
  | use (cpu : Cpu)
  | transfer (destination : Cpu)
  deriving DecidableEq, Repr

structure Entry (Cpu : Type) where
  generation : Nat
  kind : Kind Cpu
  live : Bool := true
  possible : Bool := true
  receipt : Bool := false
  deriving DecidableEq, Repr

structure State (Cpu : Type) where
  generation : Nat := 0
  phase : Phase := .active
  next : Nat := 0
  entries : Nat → Option (Entry Cpu) := fun _ => none

def initial : State Cpu := {}

def put (s : State Cpu) (i : Nat) (e : Entry Cpu) : State Cpu :=
  { s with entries := fun j => if j = i then some e else s.entries j }

def issue (s : State Cpu) (generation : Nat) (kind : Kind Cpu) : State Cpu :=
  { put s s.next ⟨generation, kind, true, true, false⟩ with next := s.next + 1 }

def stopped (e : Entry Cpu) : Entry Cpu := { e with possible := false }
def acknowledged (e : Entry Cpu) : Entry Cpu := { e with receipt := true }
def retired (e : Entry Cpu) : Entry Cpu := { e with live := false }
def resolved (e : Entry Cpu) : Entry Cpu :=
  { e with possible := false, receipt := true, live := false }

/-- Protocol-observable conditions: deliberately do not inspect `possible`. -/
def LedgerEmpty (s : State Cpu) : Prop :=
  ∀ i e, s.entries i = some e → e.live = false

def GatesAcknowledged (s : State Cpu) : Prop :=
  ∀ i e c, s.entries i = some e → e.kind = .gate c → e.receipt = true

inductive Event where
  | internal
  | access (generation ticket : Nat)
  | reuse (oldGeneration : Nat)
  deriving DecidableEq, Repr

/-- Atomic protocol linearization points, not atomic CPU instruction claims. -/
inductive Step : State Cpu → Event → State Cpu → Prop where
  | root (s : State Cpu) (c : Cpu) (active : s.phase = .active) :
      Step s .internal (issue s s.generation (.gate c))
  | admit (s : State Cpu) (i : Nat) (e : Entry Cpu) (c : Cpu)
      (found : s.entries i = some e) (gate : e.kind = .gate c)
      (unfenced : e.possible = true) :
      Step s .internal (issue s e.generation (.use c))
  | send (s : State Cpu) (i : Nat) (e : Entry Cpu) (c d : Cpu)
      (found : s.entries i = some e) (gate : e.kind = .gate c)
      (unfenced : e.possible = true) :
      Step s .internal (issue s e.generation (.transfer d))
  | activate (s : State Cpu) (i : Nat) (e : Entry Cpu) (d : Cpu)
      (found : s.entries i = some e) (transfer : e.kind = .transfer d)
      (deliverable : e.possible = true) :
      Step s .internal (issue (put s i (resolved e)) e.generation (.gate d))
  | beginClose (s : State Cpu) (active : s.phase = .active) :
      Step s .internal { s with phase := .closing }
  /- The exact ticket's physical completion event establishes that its tagged
     effect cannot recur. Transfer completion means cancellation at EVERY
     possible destination, not loss of its message/reply. -/
  | hardwareStop (s : State Cpu) (i : Nat) (e : Entry Cpu)
      (found : s.entries i = some e) :
      Step s .internal (put s i (stopped e))
  /- The receipt is keyed by backing (implicit single root), generation and ID.
     Receiving a packet alone is NOT evidence of physical completion. -/
  | ack (s : State Cpu) (i generation : Nat) (e : Entry Cpu)
      (found : s.entries i = some e) (bound : e.generation = generation)
      (complete : e.possible = false) :
      Step s .internal (put s i (acknowledged e))
  | retire (s : State Cpu) (i : Nat) (e : Entry Cpu)
      (found : s.entries i = some e) (receipt : e.receipt = true) :
      Step s .internal (put s i (retired e))
  | quiesce (s : State Cpu) (closing : s.phase = .closing)
      (empty : LedgerEmpty s) (gates : GatesAcknowledged s) :
      Step s .internal { s with phase := .quiescent }
  | reuse (s : State Cpu) (quiet : s.phase = .quiescent) :
      Step s (.reuse s.generation)
        { s with generation := s.generation + 1, phase := .active }
  /- Hardware accesses do NOT check the current generation, phase, or ledger. -/
  | access (s : State Cpu) (i : Nat) (e : Entry Cpu) (c : Cpu)
      (found : s.entries i = some e) (use : e.kind = .use c)
      (executable : e.possible = true) :
      Step s (.access e.generation i) s
  /- Loss, delay, timeout, crash without forgetting liabilities, rejected stale
     ACKs and duplicate deliveries after resolution are stutters. No recovery
     implementation, fairness, or durable-crash refinement is claimed. -/
  | stutter (s : State Cpu) : Step s .internal s

inductive Trace : State Cpu → List Event → State Cpu → Prop where
  | nil (s) : Trace s [] s
  | cons : Step s a t → Trace t as u → Trace s (a :: as) u

def Reachable (s : State Cpu) : Prop := ∃ events, Trace initial events s

end Aurora.Q
