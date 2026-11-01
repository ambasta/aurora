import SourceBinding.GuardSafety
open Aurora.SourceBinding

def off : GuardExpr .word := .parameter .word "offset".toUTF8 0
def bytes : GuardExpr .word := .field .word "bytes".toUTF8 4
def count : GuardExpr .word := .parameter .word "count".toUTF8 1
def rangeExpr (prior : Bool) : GuardExpr .boolean :=
  .or (.or (.boolLit prior) (.compare .gt off bytes)) (.compare .gt count (.sub bytes off))
example : (checkSimple (.wordLit 0)).isSome = true := by decide
example : (checkRange (.or (.or (.boolLit false) (.compare .gt (.wordLit 0) (.wordLit 1)))
  (.compare .gt (.wordLit 1) (.sub (.wordLit 1) (.wordLit 0))))).isSome = true := by decide
#eval do
  unless (checkRange (rangeExpr false)).isSome do throw (IO.userError "valid rejected")
  let altered : GuardExpr .boolean := .or (.or (.boolLit false) (.compare .gt off bytes))
    (.compare .gt count (.sub bytes (.parameter .word "different".toUTF8 0)))
  unless (checkRange altered).isNone do throw (IO.userError "different source name accepted")
  let unsound : GuardExpr .boolean := .or (.or (.boolLit false) (.compare .lt off bytes)) (.compare .gt count (.sub bytes off))
  unless (checkRange unsound).isNone do throw (IO.userError "wrong bound comparison accepted")
  for prior in [false,true] do
    for o in [0,1,2,3,18446744073709551615] do
      for b in [0,1,2,3,18446744073709551615] do
        for c in [0,1,2,3,18446744073709551615] do
          let state : SourceState := ⟨fun _ => some (.word b),fun index => some (.word (if index == 0 then o else c))⟩
          unless evalGuard state (rangeExpr prior) == Outcome.value (Value.boolean (prior || o > b || c > b-o)) do
            throw (IO.userError "range result mismatch")
  IO.println "range safety253 native checks and2 tiny kernel fixtures passed"
