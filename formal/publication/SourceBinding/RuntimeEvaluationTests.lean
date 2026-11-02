import SourceBinding.RuntimeCompatibility
import SourceBinding.RuntimeExpressionProof
namespace Aurora.SourceBinding.RuntimeEvaluationTests

def context : RuntimeExprContext := ⟨[],[],[],[],[]⟩
def empty : RuntimeLocals := ⟨1,[0],fun _ => none,fun _ => none⟩
def zero : SourceExpr := .word 0
def one : SourceExpr := .word 1
def underflow : SourceExpr := .binary .subtract zero one

example : RuntimeEvaluates context empty underflow (.scalar .word) (.trap .underflow) :=
  .wordBinary .subtract (.word (value := 0)) (.word (value := 1))

/-- First-fault semantics does not inspect an unevaluated later operand.
    This operational example alone is NOT an admission of an untyped program. -/
example : RuntimeEvaluates context empty (.binary .add underflow (.name ["missing".toUTF8]))
    (.scalar .word) (.trap .underflow) :=
  .wordBinaryFault .add (.wordBinary .subtract (.word (value := 0)) (.word (value := 1)))

example : RuntimeEvaluates context empty (.binary .and (.boolean false)
    (.binary (.compare .eq) underflow zero)) (.scalar .boolean) (.value (.boolean false)) :=
  .andStop .boolean
example : RuntimeEvaluates context empty (.binary .or (.boolean true)
    (.binary (.compare .eq) underflow zero)) (.scalar .boolean) (.value (.boolean true)) :=
  .orStop .boolean

example : RuntimeEvaluates context empty (.binary .add (.word 18446744073709551615) one)
    (.scalar .word) (.trap .overflow) :=
  .wordBinary .add (.word (value := 18446744073709551615)) (.word (value := 1))
example : RuntimeEvaluates context empty (.binary .rightShift (.word 4294967296) (.signedCount 32))
    (.scalar .word) (.value (.word 1)) :=
  .shiftRight (.word (value := 4294967296)) .thirtyTwo

example : RuntimeEvaluates context empty (.binary .shift (.word 4294967296) (.signedCount 32))
    (.scalar .word) (.trap .overflow) :=
  .shiftLeft (.word (value := 4294967296)) .thirtyTwo

/-- Metadata mismatch and ended scopes cannot borrow a coincidentally numbered
    initialized cell. Malformed values remain faults, not wellformedness premises. -/
def binding : SourceLocal := ⟨"x".toUTF8,.scalar .word,false,0,8⟩
def declared : RuntimeLocals := ⟨1,[0],fun i => if i=8 then some binding.runtimeDeclaration else none,
  fun i => if i=8 then some (.boolean true) else none⟩
example : declared.readBound binding = .trap .type := by decide
example : {declared with values := fun _ => none}.readBound binding = .trap .type := by decide
example : {declared with scopes := []}.readBound binding = .trap .type := by decide
example : declared.readBound {binding with mutable := true} = .trap .type := by decide
example : {declared with values := fun _ => some (.word 7)}.readBound binding = .value (.word 7) := by decide

end Aurora.SourceBinding.RuntimeEvaluationTests
