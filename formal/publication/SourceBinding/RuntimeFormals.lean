import SourceBinding.RuntimePrimitives
namespace Aurora.SourceBinding

/-- Source-only declaration/argument installation. No instruction, machine state
    or IR outcome defines this environment. Its correspondence to actual entry
    execution is proved separately in RuntimeEntry. -/
def formalSourceLocals (kinds : List RuntimeType) (arguments : Nat → Option Value) : RuntimeLocals :=
  ⟨1,[0],fun slot =>
    if slot % 8 = 0 ∧ 0 < slot then
      (kinds[slot/8-1]?).map fun kind => ⟨kind,false,0⟩
    else none,
    fun slot => if slot % 8 = 0 ∧ 0 < slot ∧ slot/8-1 < kinds.length then
      arguments (slot/8-1) else none⟩

end Aurora.SourceBinding
