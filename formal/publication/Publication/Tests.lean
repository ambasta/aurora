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
  "aurora-published-ir 2 types fields callables operands cfg resources\n" ++
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

-- Small kernel checks for type-information joins, not value semantics.
example : FlowsTo ⟨some .word, [],false⟩ ⟨none, [],false⟩ := by decide
example : ¬ FlowsTo ⟨some .word, [],false⟩ ⟨some .boolean, [],false⟩ := by decide
example : ¬ FlowsTo ⟨some .word, [.word],false⟩ ⟨none, [],false⟩ := by decide

def formOnly (form : Int) : Record :=
  ⟨"ir-code", ([0, 0, 1, -1, 6, 1, form] : List Int).map Field.integer, false⟩
example : ¬ TypeTransfer (tables []) 0 (formOnly 91) {} {} := by decide
example : ¬ TypeTransfer (tables []) 0 (formOnly 9) {} {} := by decide
example : ¬ TypeTransfer (tables []) 0 (formOnly 42) {} {} := by decide
example : TypeTransfer (tables []) 0 (formOnly 91) ⟨some .boolean, [],false⟩ ⟨none, [],false⟩ := by decide
example : ¬ TypeTransfer (tables []) 0 (formOnly 91) ⟨some .boolean, [],false⟩ ⟨some .boolean, [],false⟩ := by decide
example : (checkRows (tables []) 0 [formOnly 91, formOnly 9]
    [(⟨some .boolean, [],false⟩, ⟨none, [],false⟩), (⟨none, [],false⟩, ⟨none, [],false⟩)]).isSome = false := by decide
example : (checkRows (tables []) 0 [formOnly 91] [({}, {})]).isSome = false := by decide
example : CallTransfer true [some .word] (some .boolean)
    ⟨some .word, [.boolean],false⟩ ⟨some .boolean, [.boolean],false⟩ := by decide
example : ¬ CallTransfer true [some .word] (some .boolean)
    ⟨none, [.word],false⟩ ⟨some .boolean, [],false⟩ := by decide
example : CallTransfer false [some .word] (some .boolean)
    ⟨none, [.word],false⟩ ⟨some .boolean, [],false⟩ := by decide
example : CallTransfer true [] (some .word) ⟨none, [],false⟩ ⟨some .word, [],false⟩ := by decide
example : CallTransfer true [some .word, some .word] (some .boolean)
    ⟨none, [.word, .word],false⟩ ⟨some .boolean, [],false⟩ := by decide

-- Version-2 source method identity is exact wire data, not a resolver proof.
def recordAdmitted (text : String) : Bool :=
  (recordText text.toUTF8 ⟨0, text.toUTF8.size⟩).isSome

def methodFixture (kind ordinal : Int) (name : String) : Record :=
  ⟨"ir-resource-method", [.integer kind, .integer ordinal] ++
    List.replicate 6 (.integer 0) ++ [.bytes "native".toUTF8, .bytes name.toUTF8], false⟩

def resourceFixture (kind count : Int) : Record :=
  ⟨"ir-resource", [.integer kind, .integer 0, .integer count, .bytes "Resource".toUTF8], false⟩

def nameTables (methods : List Record) : Tables :=
  tables (⟨"ir-catalog-type", [.integer 0, .integer 0, .bytes "bool".toUTF8], false⟩ ::
    resourceFixture 0 2 :: resourceFixture 1 1 :: methods)

example : SourceMethodName "fill_snapshot_chunk".toUTF8 := by decide
example : SourceMethodName "_a9".toUTF8 := by decide
example : ¬ SourceMethodName "".toUTF8 := by decide
example : ¬ SourceMethodName "9start".toUTF8 := by decide
example : ¬ SourceMethodName "a:b".toUTF8 := by decide
example : ¬ SourceMethodName ⟨#[128]⟩ := by decide
example : ¬ resourceRanges (nameTables [methodFixture 0 0 "finish", methodFixture 0 1 "finish"])
    (resourceFixture 0 2) := by decide
example : resourceRanges (nameTables [methodFixture 0 0 "finish", methodFixture 0 1 "start",
    methodFixture 1 0 "finish"]) (resourceFixture 0 2) := by decide
example : ¬ resourceRanges (nameTables [methodFixture 0 0 "finish"])
    (resourceFixture 0 2) := by decide
example : ¬ resourceRanges (nameTables [methodFixture 0 0 "finish", methodFixture 0 0 "start"])
    (resourceFixture 0 2) := by decide

-- Existing producer display tag, never canonical payload.
example : "array" ∈ displayTags := by decide
example : "ir-array" ∉ displayTags := by decide
