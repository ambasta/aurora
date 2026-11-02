import SourceBinding.NominalFreeIdentity
namespace Aurora.SourceBinding

private def scopedFixture (body : String) (formals : String := "u64 input") : Option (List SourceLocal) := do
  let text := "module r; namespace n { enum class E { zero, one }; auto g(u64 x) -> u64 { return x; } auto f(" ++
    formals ++ ") -> u64 { " ++ body ++ " } }"
  let checked ← namedSource text.toUTF8
  let source : SourceFile := ⟨text.toUTF8,checked⟩
  let selected ← checkFreeSelection [source] ["r".toUTF8] ["r".toUTF8] ["n".toUTF8] "f".toUTF8
  let result ← scopeMethod text.toUTF8 selected.function.function selected.scope.members ["r".toUTF8] ["n".toUTF8]
  return result.lexical.declaredItems

/- Full parser/scoping controls are executable native checks, not concrete kernel
   acceptance. They certify lexical binding only, not expression type/execution. -/
#eval do
  let cases := [
    ("u64 code = 1u64; code = 2u64; return code;", true),
    ("const u64 code = input; return code;", true),
    ("const u64 code = input; code = 2u64; return code;", false),
    ("return code; u64 code = 1u64;", false),
    ("u64 code = code; return code;", false),
    ("u64 input = 1u64; return input;", false),
    ("if (true) { u64 code = 1u64; } return code;", false),
    ("if (true) { u64 code = 1u64; } if (false) { u64 code = 2u64; } return input;", true),
    ("u64 code = g(input); return code + (input >> 32);", true),
    ("return input << 4;", true),
    ("return input >> 11;", false),
    ("u64 g = 1u64; return g(input);", false),
    ("u64 E = 1u64; if (E::zero == E::one) { return input; } return input;", false),
    ("if (E::zero == n::E::one) { return input; } return input;", true),
    ("return Unknown::zero;", false),
    ("u64 E = input; E value = E::zero; return input;", false)]
  for (body,expected) in cases do
    unless (scopedFixture body).isSome == expected do
      throw (IO.userError s!"local binding control failed: {body}")
  let some declarations := scopedFixture
    "if (true) { u64 a = input; } if (false) { const u64 b = input; } return input;"
    | throw (IO.userError "lexical slot fixture rejected")
  unless declarations.map (fun (item : SourceLocal) => item.slot) == [16,24] && declarations.map (fun (item : SourceLocal) => item.scope) == [1,2] &&
      declarations.map (fun (item : SourceLocal) => item.mutable) == [true,false] do
    throw (IO.userError "scope freshness/complete local slot order failed")

example : enumSymbol ["m".toUTF8] ["n".toUTF8] "E".toUTF8 =
    "__au_e_m1_1m_n1_1n_d1E".toUTF8 := by decide
example : runtimeFreeSymbol ["r".toUTF8] ["m".toUTF8] ["n".toUTF8] "f".toUTF8
    [.scalar .word,.nominal ⟨"enum".toUTF8,2⟩] = "__au_v_m1_1m_n1_1n_d1f".toUTF8 := by decide
example : runtimeFreeSymbol ["r".toUTF8] ["m".toUTF8] ["n".toUTF8] "f".toUTF8
    [.scalar .word,.scalar .word] = "__au_f_m1_1m_n1_1n_d1f".toUTF8 := by decide
example : runtimeFreeSymbol ["r".toUTF8] ["r".toUTF8] [] "f".toUTF8
    [.scalar .word,.nominal ⟨"enum".toUTF8,2⟩] = "__au_v_m1_1r_n0__d1f".toUTF8 := by decide
example : (inferGuard [] [] (.binary .add (.word 1) (.word 2))).isNone = true := by decide
example : (inferGuard [] [] (.signedCount 4)).isNone = true := by decide

namespace NominalFixtures
open Aurora.Publication
-- Isolated relations only; these synthetic rows are NOT D1-admitted artifacts.
private def row (tag : String) (values : List Int) : Record := ⟨tag,values.map Field.integer,false⟩
private def enumRow : Record := row "ir-enum" [0,0,1,2]
private def typ : Record := row "ir-type" [0,9,0,1,0,0,0,0,0]
private def base : Tables := tables [⟨"ir-name-bytes",[.bytes "E".toUTF8],false⟩,typ,enumRow,
  row "ir-operand" [0,12,0,0,0,0],row "ir-operand" [1,13,1,0,0,0]]
private def code : Record := row "ir-code" [0,0,0,0,0,1,6,0,0,0,0,0,2]
private def identity : NominalIdentity := ⟨"E".toUTF8,2⟩
#eval do
  let checks := [
    decide (EnumConstantIdentity base code identity 1),
    !decide (EnumConstantIdentity base code identity 2),
    !decide (NominalTypeIdentity base 0 ⟨"F".toUTF8,2⟩),
    !decide (NominalTypeIdentity base 0 ⟨"E".toUTF8,3⟩),
    !decide (NominalTypeIdentity {base with enums := #[enumRow,enumRow]} 0 identity),
    !decide (NominalTypeIdentity {base with types := #[row "ir-type" [0,7,0,0,0,0,0,0,0]]} 0 identity),
    !decide (EnumConstantIdentity {base with operands :=
      #[row "ir-operand" [0,12,0,0,0,0],row "ir-operand" [1,11,0,1,0,0]]} code identity 1)]
  unless checks.all id do throw (IO.userError "nominal identity control failed")
end NominalFixtures

end Aurora.SourceBinding
