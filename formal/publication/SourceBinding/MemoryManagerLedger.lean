import SourceBinding.FramePolicySpec

namespace Aurora.SourceBinding.MemoryManagerRelease

/-! Mathematical definitions only; preservation and actual-source attachment
are not yet proved.
Finite-bank abstraction for the COMPLETE production MemoryManager.release.
There is no policy evaluator here: all policy decisions reuse FramePolicy.
Actual source/IR field/resource identity and primitive effects are separate
obligations. A value of these structures is not evidence of native authority. -/

abbrev Bank (extent : Nat) := Fin extent → Nat

/-- Exactly the scalar ledger projection; the other receiver fields/resources
are NOT erased by execution. Their framing belongs to the actual-state binding. -/
structure LedgerFields where
  head : Nat
  freeCount : Nat
  allocatedCount : Nat
  reservedCount : Nat
  owner0 : Nat
  count0 : Nat
  owner1 : Nat
  count1 : Nat
  initialized : Bool
  poison : Bool

structure Ledger (extent : Nat) where
  bank : Bank extent
  fields : LedgerFields

/-- Constructive finite census, no choice or finite-set oracle. -/
def stateCount (bank : Bank extent) (state : Nat) : Nat :=
  ((List.finRange extent).filter fun i => FramePolicy.stateOf (bank i) == state).length

def ownerCount (bank : Bank extent) (owner : Nat) : Nat :=
  ((List.finRange extent).filter fun i =>
    FramePolicy.stateOf (bank i) == 2 && FramePolicy.wordOf (bank i) == owner).length

def chainHead : List (Fin extent) → Nat
  | [] => 0
  | index :: _ => index.val + 1

/-- Successor equations use actual record words, with a one-based head and
zero terminator; a list merely witnesses finite traversal, not a new machine. -/
def ChainLinks (bank : Bank extent) : List (Fin extent) → Prop
  | [] => True
  | index :: rest => FramePolicy.wordOf (bank index) = chainHead rest ∧ ChainLinks bank rest

structure CompleteFreeChain (ledger : Ledger extent) (chain : List (Fin extent)) : Prop where
  simple : chain.Nodup
  head : ledger.fields.head = chainHead chain
  links : ChainLinks ledger.bank chain
  complete : ∀ index, index ∈ chain ↔ FramePolicy.stateOf (ledger.bank index) = 1
  count : ledger.fields.freeCount = chain.length

structure OwnerCensus (bank : Bank extent) (owner count : Nat) : Prop where
  empty : count = 0 ↔ owner = 0
  activeOwner : owner ≠ 0 → FramePolicy.UserOwner owner
  exactCount : count = ownerCount bank owner

/-- Healthy INITIAL structural invariant, not a claim about initialization or
about every intermediate store prefix. Retired maximum generation is separate. -/
structure LedgerInv (ledger : Ledger extent) : Prop where
  nonempty : 0 < extent
  extentBound : extent ≤ FramePolicy.wordMax
  initialized : ledger.fields.initialized = true
  unpoisoned : ledger.fields.poison = false
  scalarBounds : ∀ value ∈ [ledger.fields.head,ledger.fields.freeCount,
      ledger.fields.allocatedCount,ledger.fields.reservedCount,ledger.fields.owner0,
      ledger.fields.count0,ledger.fields.owner1,ledger.fields.count1],
    value < FramePolicy.u64Modulus
  cells : ∀ index, ledger.bank index < FramePolicy.u64Modulus ∧
    FramePolicy.RecordValid (ledger.bank index)
  reservedBound : ledger.fields.reservedCount ≤ extent
  reservedPrefix : ∀ index, FramePolicy.stateOf (ledger.bank index) = 3 ↔
    index.val < ledger.fields.reservedCount
  reservedExact : ledger.fields.reservedCount = stateCount ledger.bank 3
  freeExact : ledger.fields.freeCount = stateCount ledger.bank 1
  allocatedExact : ledger.fields.allocatedCount = stateCount ledger.bank 2
  partition : ledger.fields.reservedCount + ledger.fields.freeCount +
    ledger.fields.allocatedCount + stateCount ledger.bank 4 = extent
  freeChain : ∃ chain, CompleteFreeChain ledger chain
  firstOwner : OwnerCensus ledger.bank ledger.fields.owner0 ledger.fields.count0
  secondOwner : OwnerCensus ledger.bank ledger.fields.owner1 ledger.fields.count1
  distinctOwners : ledger.fields.owner0 ≠ 0 → ledger.fields.owner1 ≠ 0 →
    ledger.fields.owner0 ≠ ledger.fields.owner1
  noOrphanAllocated : ∀ index, FramePolicy.stateOf (ledger.bank index) = 2 →
    (ledger.fields.owner0 ≠ 0 ∧ FramePolicy.wordOf (ledger.bank index) = ledger.fields.owner0) ∨
    (ledger.fields.owner1 ≠ 0 ∧ FramePolicy.wordOf (ledger.bank index) = ledger.fields.owner1)
  allocatedOwners : ledger.fields.allocatedCount = ledger.fields.count0 + ledger.fields.count1

/-- Optional reachable-state strengthening, NOT silently built into RecordValid
or the base invariant. Complete release preserves this if supplied initially. -/
def CanonicalRetired (ledger : Ledger extent) : Prop :=
  ∀ index, FramePolicy.stateOf (ledger.bank index) = 4 →
    ledger.bank index = FramePolicy.retiredRecord

/-- Release-only preservation target: old retired cells are bit-for-bit
unchanged. This is deliberately not induction over allocation/initialization,
rebinding, direct writes, or arbitrary operation histories. -/
def RetiredPreserved (before after : Ledger extent) : Prop :=
  ∀ index, FramePolicy.stateOf (before.bank index) = 4 → after.bank index = before.bank index

inductive OwnerSlot where
  | first | second
  deriving DecidableEq

/-- The priority of the real owner_slot method, not arbitrary owner selection. -/
def SlotMatches (fields : LedgerFields) (owner : Nat) : OwnerSlot → Prop
  | .first => fields.owner0 = owner
  | .second => fields.owner0 ≠ owner ∧ fields.owner1 = owner

def heldCount (fields : LedgerFields) : OwnerSlot → Nat
  | .first => fields.count0
  | .second => fields.count1

/-- Pure relation on two finite banks; it does not assert that a store occurred. -/
def OneCellReplacement (before after : Bank extent) (index : Fin extent) (next : Nat) : Prop :=
  after index = next ∧ ∀ other, other ≠ index → after other = before other

/-- Exact completed scalar bookkeeping. Subtraction safety is explicit; a
proof cannot exploit Nat's saturating subtraction to hide an unguarded underflow.
This equality relation does NOT encode or assert the order of machine stores. -/
structure ReleaseDelta (before after : Ledger extent) (index : Fin extent)
    (next : Nat) (slot : OwnerSlot) (reusable : Bool) : Prop where
  allocatedPositive : 0 < before.fields.allocatedCount
  heldPositive : 0 < heldCount before.fields slot
  reusableRoom : reusable = true → before.fields.freeCount < extent
  bankWrite : OneCellReplacement before.bank after.bank index next
  allocated : after.fields.allocatedCount = before.fields.allocatedCount - 1
  firstCount : after.fields.count0 = if slot = .first then before.fields.count0 - 1 else before.fields.count0
  secondCount : after.fields.count1 = if slot = .second then before.fields.count1 - 1 else before.fields.count1
  firstOwner : after.fields.owner0 =
    if slot = .first ∧ before.fields.count0 = 1 then 0 else before.fields.owner0
  secondOwner : after.fields.owner1 =
    if slot = .second ∧ before.fields.count1 = 1 then 0 else before.fields.owner1
  head : after.fields.head = if reusable then index.val + 1 else before.fields.head
  free : after.fields.freeCount = if reusable then before.fields.freeCount + 1 else before.fields.freeCount
  reserved : after.fields.reservedCount = before.fields.reservedCount
  initialized : after.fields.initialized = before.fields.initialized
  poison : after.fields.poison = before.fields.poison

/-- A SUCCESS POSTCONDITION, to be derived from the complete actual method.
`policy` is output evidence within this postcondition, never a public theorem
premise prescribing a desired callee result or store. -/
def ReleaseSuccess (before after : Ledger extent)
    (index generation owner code : Nat) : Prop :=
  ∃ (position : Fin extent) (slot : OwnerSlot) (next : Nat),
    position.val = index ∧ SlotMatches before.fields owner slot ∧
    FramePolicy.ResultSpec .release (before.bank position) owner generation before.fields.head next ∧
    (FramePolicy.stateOf next = 1 ∨ FramePolicy.stateOf next = 4) ∧
    ReleaseDelta before after position next slot (FramePolicy.stateOf next == 1) ∧ code = 0

/-- Healthy-state ordinary refusals. Index admission precedes the existing
policy; no copied branch-by-branch policy decision procedure is introduced. -/
def NormalRefusal (before after : Ledger extent) (index generation owner code : Nat) : Prop :=
  after = before ∧
    ((extent ≤ index ∧ code = 65) ∨
      ∃ (position : Fin extent) (reason : FramePolicy.Rejection), position.val = index ∧
        FramePolicy.transition .release (before.bank position) owner generation before.fields.head = .reject reason ∧
        code = reason.ordinal)

/-- Only normal method returns under the explicit lawful primitive model.
A primitive fault is a different actual source/machine outcome, NOT this code.
The complete-operation theorem must separately retain its actual failure prefix. -/
def HealthyReleasePost (before after : Ledger extent) (index generation owner code : Nat) : Prop :=
  (NormalRefusal before after index generation owner code ∨
    ReleaseSuccess before after index generation owner code) ∧ LedgerInv after

/-- General malformed-state consistency-denial EFFECT SHAPE, not a fabricated
condition explaining why the source selected the poison branch. The exact
checked source derivation must establish that guard and its pre-store ordering.
Here `before` is the state AT that guard, not necessarily original entry after
arbitrary resource responses. Equality to entry is derived only under the
read-only laws of the concrete lawful size/at primitive. -/
def PoisonOnly (before after : Ledger extent) (code : Nat) : Prop :=
  code = 64 ∧ after.bank = before.bank ∧
    after.fields = { before.fields with poison := true }

/-- Entry denial has no receiver or bank mutation. It is distinct from the
later consistency denial which really writes poison. -/
def EntryRefusal (before after : Ledger extent) (code : Nat) : Prop :=
  (before.fields.initialized = false ∨ before.fields.poison = true) ∧
    code = 64 ∧ after = before

/- No primitive-fault constructor is invented here. Generic effectful evaluation
must retain arbitrary response poststate (including mutate-then-false then
require trap). Under the concrete bank primitive, admission/index faults precede
its write; invalidation between size/read/set remains possible unless stable
grant evidence is provided. Post-set arithmetic safety is to be DERIVED from
position<extent≤wordMax and actual guarded counts. Prefix bookkeeping must be
indexed by actual source/CallRuns events; ReleaseDelta alone proves neither
write ordering nor rollback/crash atomicity.

Native TCB remains explicit: admitted binding/epoch/extent/field identity,
physical accessibility, C++ primitive and ABI refinement, and serialization.
The initial LedgerInv is assumed, not established by an unproved audit/init.
Release preserves already-retired cells; arbitrary allocator-history exclusion
requires the later allocation proof and an explicitly closed operation alphabet. -/

end Aurora.SourceBinding.MemoryManagerRelease
