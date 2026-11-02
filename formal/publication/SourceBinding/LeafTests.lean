import SourceBinding.LeafBinding
namespace Aurora.SourceBinding
private def parameter (name : String) : Formal := ⟨name.toUTF8,guardSourceType .word⟩
private def exactPolicy := declaredLeafGuard (parameter "leaf") (parameter "physical")
  (parameter "mapping") (parameter "prefix") (parameter "slot") (parameter "limit")
-- AST-only controls; complete byte-backed production acceptance is separate.
example : exactPolicy ≠ .boolLit true := by decide
example : exactPolicy ≠ leafGuard (.parameter .word "leaf".toUTF8 0)
    (.parameter .word "physical".toUTF8 1) (.parameter .word "mapping".toUTF8 2)
    (.parameter .word "prefix".toUTF8 3) (.parameter .word "slot".toUTF8 5)
    (.parameter .word "limit".toUTF8 4) := by decide
example : exactPolicy ≠ declaredLeafGuard (parameter "physical") (parameter "leaf")
    (parameter "mapping") (parameter "prefix") (parameter "slot") (parameter "limit") := by decide
example : exactPolicy ≠ .and (.boolLit true) exactPolicy := by decide
example : leafNumeric 9223372036854780003 4096 6287363 4194304 511 8192 = true := by decide
example : leafNumeric 9223372036854780003 4096 6291459 4194304 512 8192 = false := by decide
end Aurora.SourceBinding
