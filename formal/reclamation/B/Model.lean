import A.Completion
namespace Aurora.B

abbrev Byte := Fin 256
abbrev Heap := Nat → Byte

def store (heap : Heap) (cell : Nat) (value : Byte) : Heap :=
  fun index => if index = cell then value else heap index

def wordLimit : Nat := 2^64

def inRange (base count cell : Nat) : Prop := base ≤ cell ∧ cell < base + count

/-- ONE canonical physical address space. Region tags do not establish separation.
The registered source is fixed for this interpretation's lifetime, like the boot
endpoint registration. Native registration/translation fidelity is not proved. -/
structure Config where
  allocation : A.Footprint
  source : Nat
  sourceBytes : Nat
  control : A.Footprint

def Config.Valid (c : Config) : Prop :=
  0 < c.sourceBytes ∧ c.source + c.sourceBytes ≤ wordLimit ∧
  (∀ cell, inRange c.source c.sourceBytes cell → cell ∉ c.allocation) ∧
  (∀ cell ∈ c.control, cell ∉ c.allocation ∧ ¬inRange c.source c.sourceBytes cell)

structure Descriptor where
  generation : Nat
  source : Nat
  destination : Nat
  count : Nat
  deriving DecidableEq

def Descriptor.Valid (config : Config) (d : Descriptor) : Prop :=
  0 < d.count ∧ config.source ≤ d.source ∧ d.source + d.count ≤ config.source + config.sourceBytes ∧
  d.destination + d.count ≤ wordLimit ∧ d.destination % 4096 + d.count ≤ 4096

/-- Concrete immutable entry/grant lookup and range check, not Enabled or a
post-state safety oracle. Generic A admission constructs these records. -/
def Authorized (s : A.State Agent) (ticket : Nat) (d : Descriptor) : Prop :=
  ∃ e g, s.protocol.entries ticket = some e ∧ s.grants ticket = some g ∧
    e.kind = .use g.subject ∧ 0 < e.work ∧ g.writable = true ∧
    e.generation = d.generation ∧
    ∀ offset, offset < d.count → d.destination + offset ∈ g.footprint

inductive Phase where
  | running | done | faulted
  deriving DecidableEq
structure Cursor where
  descriptor : Descriptor
  copied : Nat := 0
  phase : Phase := .running
  deriving DecidableEq

def advance (c : Cursor) : Cursor :=
  { c with copied := c.copied + 1, phase := if c.copied + 1 = c.descriptor.count then .done else .running }

structure State (Agent : Type) where
  authority : A.State Agent
  heap : Heap
  cursors : Nat → Option Cursor := fun _ => none
  spent : Nat → Bool := fun _ => false

def initial (authority : A.State Agent) (heap : Heap) : State Agent := { authority := authority, heap := heap }
def putCursor (s : State Agent) (ticket : Nat) (cursor : Option Cursor) : State Agent :=
  {s with cursors := fun i => if i = ticket then cursor else s.cursors i}
def start (s : State Agent) (ticket : Nat) (d : Descriptor) : State Agent :=
  {putCursor s ticket (some ⟨d,0,.running⟩) with spent := fun i => if i = ticket then true else s.spent i}
def copy (s : State Agent) (ticket : Nat) (c : Cursor) : State Agent :=
  {putCursor s ticket (some (advance c)) with heap := store s.heap (c.descriptor.destination + c.copied) (s.heap (c.descriptor.source + c.copied))}

/-- Only completion of a held stream is withheld. Close/publication/packet
transitions remain allowed: pending bytes drain after close. This is an explicit
sequential-stream refinement, not a post-state safety oracle. -/
inductive Finishes {Agent : Type} {issuer subject : Agent} {allocation : A.Footprint} : {before after : A.State Agent} →
    {event : A.Event} → A.Step issuer subject allocation before event after → Nat → Prop
  | finish (before : A.State Agent) ticket n e owner (found : before.protocol.entries ticket = some e)
      (use : e.kind = .use owner) (work : e.work = n + 1) :
      Finishes (A.Step.passive before _ (A.Passive.finishOne before.protocol ticket n e owner found use work)) ticket

def NoHeldFinish (s : State Agent)
    (action : A.Step issuer subject allocation s.authority event next) : Prop :=
  ∀ ticket, Finishes action ticket → s.cursors ticket = none

def Nonwrite : A.Event → Prop
  | .access _ _ _ true => False
  | _ => True

inductive Event where
  | protocol (event : A.Event)
  | beginCopy (ticket : Nat)
  | payload (generation ticket source destination : Nat) (value : Byte)
  | write (generation ticket destination : Nat) (value : Byte)
  | control (cell : Nat) (value : Byte)
  | fault (ticket : Nat)
  | release (ticket : Nat)
  deriving DecidableEq

def erase : Event → A.Event
  | .protocol event => event
  | .payload generation ticket _ destination _ | .write generation ticket destination _ =>
      .access generation ticket destination true
  | _ => .internal

/-- Every heap write has an explicit canonical address and event. Arbitrary A
writes are admitted only outside held cursors; a held ticket has ONE sequential
copy stream. Abort does not close a window, finish work, return authority or undo
bytes. Explicit release of done/faulted streams precedes separate A drainage. -/
inductive Step (issuer subject : Agent) (config : Config) : State Agent → Event → State Agent → Prop
  | protocol (s : State Agent) next event
      (action : A.Step issuer subject config.allocation s.authority event next)
      (nonwrite : Nonwrite event) (held : NoHeldFinish s action) :
      Step issuer subject config s (.protocol event) {s with authority := next}
  | beginCopy (s : State Agent) ticket d (fresh : s.spent ticket = false)
      (empty : s.cursors ticket = none) (valid : d.Valid config)
      (admission : Authorized s.authority ticket d) :
      Step issuer subject config s (.beginCopy ticket) (start s ticket d)
  | payload (s : State Agent) ticket c (found : s.cursors ticket = some c)
      (running : c.phase = .running) (remaining : c.copied < c.descriptor.count) :
      Step issuer subject config s
        (.payload c.descriptor.generation ticket (c.descriptor.source + c.copied)
          (c.descriptor.destination + c.copied) (s.heap (c.descriptor.source + c.copied))) (copy s ticket c)
  | write (s : State Agent) next generation ticket cell value
      (action : A.Step issuer subject config.allocation s.authority (.access generation ticket cell true) next)
      (idle : s.cursors ticket = none) :
      Step issuer subject config s (.write generation ticket cell value)
        {s with authority := next, heap := store s.heap cell value}
  | control (s : State Agent) cell value (allowed : cell ∈ config.control) :
      Step issuer subject config s (.control cell value) {s with heap := store s.heap cell value}
  | fault (s : State Agent) ticket c (found : s.cursors ticket = some c) (running : c.phase = .running) :
      Step issuer subject config s (.fault ticket) (putCursor s ticket (some {c with phase := .faulted}))
  | release (s : State Agent) ticket c (found : s.cursors ticket = some c) (stopped : c.phase ≠ .running) :
      Step issuer subject config s (.release ticket) (putCursor s ticket none)

inductive Trace (issuer subject : Agent) (config : Config) : State Agent → List Event → State Agent → Prop
  | nil (s) : Trace issuer subject config s [] s
  | cons : Step issuer subject config s event t → Trace issuer subject config t events u →
      Trace issuer subject config s (event :: events) u

end Aurora.B
