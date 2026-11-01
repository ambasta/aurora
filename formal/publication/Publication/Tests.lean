import Publication
open Aurora.Publication

def frames (text : String) (limits : Limits := {}) : Bool :=
  (frame limits text.toUTF8).isSome

def ending (text : String) : Option Nat :=
  (decodeEnd text.toUTF8 ⟨0, text.toUTF8.size⟩).map (·.value)

-- Kernel reduction, never native_decide.
example : frames "ir-end 194\n" = true := by decide
example : frames "ir-end 194" = false := by decide
example : frames "ir-end 194\r\n" = false := by decide
example : frames "ir-end 194\ntrailing" = false := by decide
example : frames "\n\n" { lines := 1 } = false := by decide
example : frames "1234\n" { lineBytes := 4 } = false := by decide
example : frames "1234\n" { lineBytes := 5 } = true := by decide
example : frames "1234\n" { fileBytes := 4 } = false := by decide
example : ending "ir-end 194" = some 194 := by decide
example : ending "ir-end 0" = some 0 := by decide
example : ending "ir-end 00" = none := by decide
example : ending "ir-end +1" = none := by decide
example : ending "ir-end -1" = none := by decide
example : ending "ir-end 1 " = none := by decide
example : ending "ir-end " = none := by decide
example : ending "ir-end 9223372036854775807" = some 9223372036854775807 := by decide
example : ending "ir-end 9223372036854775808" = none := by decide
example : ending "ir-end 123456789012345678901" = none := by decide
-- Expected limitations: framing alone accepts unknown tags and extra records.
example : frames "unknown 9\nir-end 1\n" = true := by decide
example : frames "ir-end 1\nir-end 2\n" = true := by decide
example : frames "" = true := by decide
example : frames "\n\n" { lines := 2 } = true := by decide
example : (frame {} ⟨#[0, 10]⟩).isSome = false := by decide
example : (frame {} ⟨#[128, 10]⟩).isSome = false := by decide
example : (decodeEnd "ir-end 1".toUTF8 ⟨0, 9⟩).isSome = false := by decide

-- D1 wire/structure checks still say nothing about executable closure semantics.
def emptyArtifact : String :=
  "aurora-published-ir 1 types fields callables operands cfg resources\n" ++
  "ir-counts 0 0 0 0 0 0 0 0 0 0 0\nir-name-bytes \nir-literal-bytes \nir-end 0\n"
def admitted (text : String) : Bool := (decodeArtifact {} text.toUTF8).isSome
example : (fieldText "18446744073709551615".toUTF8 ⟨0, 20⟩ .unsigned).isSome = true := by decide
example : (fieldText "18446744073709551616".toUTF8 ⟨0, 20⟩ .unsigned).isSome = false := by decide
example : (fieldText "-9223372036854775808".toUTF8 ⟨0, 20⟩ .signed).isSome = true := by decide
example : (fieldText "-9223372036854775809".toUTF8 ⟨0, 20⟩ .signed).isSome = false := by decide
example : (fieldText "-0".toUTF8 ⟨0, 2⟩ .signed).isSome = false := by decide
example : (fieldText "0080ff0a".toUTF8 ⟨0, 8⟩ .hex).map (·.value) = some (.bytes ⟨#[0, 128, 255, 10]⟩) := by decide
example : (fieldText "FF".toUTF8 ⟨0, 2⟩ .hex).isSome = false := by decide
example : (fieldText "0".toUTF8 ⟨0, 1⟩ .hex).isSome = false := by decide
example : (fieldText "".toUTF8 ⟨0, 0⟩ .hex).isSome = true := by decide
example : (fieldText "".toUTF8 ⟨1, 0⟩ .hex).isSome = false := by decide
