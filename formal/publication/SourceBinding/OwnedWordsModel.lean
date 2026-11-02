import SourceBinding.EffectSourceData
import SourceBinding.MemoryManagerLedger
namespace Aurora.SourceBinding

/-- Finite mathematical backing, sharing the ledger's sole Bank definition.
    This is not a native pointer, borrowed span, or physical ownership proof. -/
structure OwnedWordsBank where
  size : Nat
  cells : MemoryManagerRelease.Bank size

def OwnedWordsBank.Valid (bank : OwnedWordsBank) : Prop :=
  0 < bank.size ∧ bank.size < 2^32 ∧ ∀ index, bank.cells index < wordLimit

def OwnedWordsBank.write (bank : OwnedWordsBank) (index : Fin bank.size)
    (value : Nat) : OwnedWordsBank :=
  ⟨bank.size,fun other => if other = index then value else bank.cells other⟩

structure OwnedWordsWorld (Other : Type) where
  banks : Nat → Option OwnedWordsBank
  other : Other

def OwnedWordsWorld.write (world : OwnedWordsWorld Other) (identity : Nat)
    (bank : OwnedWordsBank) : OwnedWordsWorld Other :=
  {world with banks := fun other => if other = identity then some bank else world.banks other}

/-- A fixed abstract admission for the selected resource field during one
    serialized operation. Source/catalogue binding proves these three keys are
    the actual size/at/set interface; native admission into this model is TCB.
    The model contains no invented native token/epoch machinery and no release
    result, ledger invariant, counter law, or supplied successful-set premise. -/
structure OwnedWordsInterface where
  sizeMethod : RuntimeSourceResource
  atMethod : RuntimeSourceResource
  setMethod : RuntimeSourceResource
  bank : Nat
  writable : Bool

inductive OwnedWordsFault where
  | admission
  | bounds
  | writeDenied
  deriving BEq, DecidableEq

/-- Concrete primitive transition relation ONLY. The generic source/machine
    external relation remains unrestricted. All operations frame the receiver,
    other banks and Other. Normal set performs one actual finite-bank update.
    Admission stability is derived because these operations preserve extent and
    bounded contents; no revocation or competing writer is hidden in this model. -/
inductive OwnedWordsResponse (interface : OwnedWordsInterface) :
    SourceResourceRequest (OwnedWordsWorld Other) →
      SourceExternalOutcome OwnedWordsFault → SourceShared (OwnedWordsWorld Other) → Prop
  | size (found : before.world.banks interface.bank = some bank)
      (valid : bank.Valid) :
      OwnedWordsResponse interface ⟨interface.sizeMethod,[],before⟩
        (.returned (some (.word bank.size))) before
  | read (found : before.world.banks interface.bank = some bank)
      (valid : bank.Valid) (inside : index < bank.size) :
      OwnedWordsResponse interface ⟨interface.atMethod,[.word index],before⟩
        (.returned (some (.word (bank.cells ⟨index,inside⟩)))) before
  | set (found : before.world.banks interface.bank = some bank)
      (valid : bank.Valid) (write : interface.writable = true)
      (inside : index < bank.size) (bounded : value < wordLimit) :
      OwnedWordsResponse interface ⟨interface.setMethod,[.word index,.word value],before⟩
        (.returned (some (.boolean true)))
        {before with world := before.world.write interface.bank (bank.write ⟨index,inside⟩ value)}
  | missing (selected : key = interface.sizeMethod ∨ key = interface.atMethod ∨ key = interface.setMethod)
      (absent : before.world.banks interface.bank = none) :
      OwnedWordsResponse interface ⟨key,arguments,before⟩ (.fault .admission) before
  | invalid (selected : key = interface.sizeMethod ∨ key = interface.atMethod ∨ key = interface.setMethod)
      (found : before.world.banks interface.bank = some bank) (invalid : ¬ bank.Valid) :
      OwnedWordsResponse interface ⟨key,arguments,before⟩ (.fault .admission) before
  | atBounds (found : before.world.banks interface.bank = some bank)
      (valid : bank.Valid) (outside : bank.size ≤ index) :
      OwnedWordsResponse interface ⟨interface.atMethod,[.word index],before⟩ (.fault .bounds) before
  | setBounds (found : before.world.banks interface.bank = some bank)
      (valid : bank.Valid) (write : interface.writable = true) (outside : bank.size ≤ index) :
      OwnedWordsResponse interface ⟨interface.setMethod,[.word index,.word value],before⟩ (.fault .bounds) before
  | denied (found : before.world.banks interface.bank = some bank)
      (valid : bank.Valid) (readOnly : interface.writable = false) :
      OwnedWordsResponse interface ⟨interface.setMethod,[.word index,.word value],before⟩ (.fault .writeDenied) before

end Aurora.SourceBinding
