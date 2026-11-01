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
