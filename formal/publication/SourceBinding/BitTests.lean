import SourceBinding.LeafEvaluation
import SourceBinding.MethodSyntax
import Publication.Typing
namespace Aurora.SourceBinding
open Aurora.Publication
example : binaryValue .leftShift (.word 511) .signedCount12 = .value (.word 2093056) := by decide
example : binaryValue .leftShift (.word 4503599627370496) .signedCount12 = .trap .overflow := by decide
example : binaryValue .leftShift (.word 1) (.word 12) = .trap .type := by decide
example : binaryValue .sub (.word 1) .signedCount12 = .trap .type := by decide
example : readScalar .word (some .signedCount12) = .trap .type := by decide
example : binaryValue .bitAnd (.word 255) (.word 96) = .value (.word 96) := by decide
example : binaryValue .bitOr (.word 4096) (.word 3) = .value (.word 4099) := by decide
example : binaryValue .bitAnd (.word 18446744073709551616) (.word 1) = .trap .range := by decide
private def row (form operation : Int) : Record :=
  ⟨"ir-code", ([0,0,1,-1,6,1,form,0,operation] : List Int).map Field.integer,false⟩
example : TypeTransfer (tables []) 0 (row 12 8) ⟨none,[.word],true⟩ ⟨some .word,[],false⟩ := by decide
example : ¬ TypeTransfer (tables []) 0 (row 12 8) ⟨some .word,[.word],false⟩ ⟨some .word,[],false⟩ := by decide
example : ¬ TypeTransfer (tables []) 0 (row 9 0) ⟨none,[],true⟩ ⟨none,[],true⟩ := by decide
example : ¬ TypeTransfer (tables []) 0 (row 40 0) ⟨none,[],true⟩ ⟨none,[],true⟩ := by decide
example : ¬ TypeTransfer (tables []) 0 (row 43 0) ⟨none,[],true⟩ ⟨none,[],true⟩ := by decide
example : ¬ CallTransfer false [] none ⟨none,[],true⟩ ⟨none,[],false⟩ := by decide
example : ¬ FlowsTo ⟨none,[],false⟩ ⟨none,[],true⟩ := by decide
example : ¬ FlowsTo ⟨none,[],true⟩ ⟨none,[],false⟩ := by decide
example : leafNumeric 9223372036854780003 4096 4194307 4194304 0 8192 = true := by decide
example : leafNumeric 9223372036854780003 4096 4194307 4194304 512 8192 = false := by decide
example : leafNumeric 9223372036854780003 4096 4194307 4194305 0 8192 = false := by decide
example : leafNumeric 9223372036854780003 4096 4194307 4194304 0 4096 = false := by decide
example : TypedGuard [] [] (.binary .shift (.word 1) .signed12) (.shift12 (.wordLit 1)) :=
  .shift12 (.word (by decide))
example : (inferGuard [] [] (.binary .shift (.word 1) (.word 12))).isSome = false := by decide
example : (inferGuard [] [] (.binary .shift (.boolean true) .signed12)).isSome = false := by decide
example : (inferGuard [] [] .signed12).isSome = false := by decide
example : precedence .or < precedence .bitOr ∧ precedence .bitOr < precedence .bitAnd ∧
    precedence .bitAnd < precedence (.compare .eq) ∧ precedence (.compare .lt) < precedence .shift ∧
    precedence .shift < precedence .subtract := by decide
end Aurora.SourceBinding
