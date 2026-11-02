import Publication.Tests
open Aurora.Publication

-- Execution tests, not kernel theorems of concrete document acceptance.
#eval do
  let cases : List (String × Bool) :=
    [(emptyArtifact, true), (emptyArtifact ++ "ir-end 0\n", false),
     ("unknown\n" ++ emptyArtifact, false),
     ("origin harmless\n" ++ emptyArtifact, false),
     (emptyArtifact ++ "origin harmless\n", false), ("", false)]
  for (text, expected) in cases do
    unless admitted text == expected do
      throw (IO.userError "runtime document fixture mismatch")
  IO.println s!"{cases.length} runtime document checks passed (not concrete kernel proofs)"

#eval do
  let cases : List (String × Bool) :=
    [("aurora-published-ir 2 types fields callables operands cfg resources", true),
     ("aurora-published-ir 1 types fields callables operands cfg resources", false),
     ("ir-resource-method 0 0 0 0 0 0 0 0 6e 66", true),
     ("ir-resource-method 0 0 0 0 0 0 0 0 6e", false),
     ("ir-resource-method 0 0 0 0 0 0 0 0 6e 66 66", false)]
  for (text, expected) in cases do
    unless recordAdmitted text == expected do
      throw (IO.userError "v2 source-method wire fixture mismatch")
  IO.println s!"{cases.length} v2 record checks passed (not concrete kernel proofs)"

#eval do
  for text in ["array harmless 40 16", "array ir-code 0 0 1 -1 6 1 5 0 0"] do
    match recordText text.toUTF8 ⟨0,text.toUTF8.size⟩ with
    | none => throw (IO.userError "existing array display tag refused")
    | some record =>
      unless record.value.display && record.value.fields.isEmpty &&
          (rows [record.value] "ir-code").isEmpty do
        throw (IO.userError "array display interpreted as canonical payload")
  unless !(recordAdmitted "ir-array harmless 40 16") && !(recordAdmitted "ir-field malformed") do
    throw (IO.userError "malformed/unknown canonical record accepted")
  IO.println "array display-only and canonical-refusal controls passed"
