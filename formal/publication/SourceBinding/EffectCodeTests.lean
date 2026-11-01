import SourceBinding.EffectCode
open Aurora.SourceBinding Aurora.Publication
namespace EffectCodeFixtures
-- Synthetic relation/program fixtures, not D1/D2 artifact admission or execution proofs.
def program (operations : List EffectOp) : EffectProgram := fun pc => operations[pc]?
def accepted (operations : List EffectOp) (body : EffectBody) : Bool :=
  match checkBodyCode (program operations) id body 0 with
  | some checked => checked.stop == operations.length -- Caller must enforce complete coverage.
  | none => false

def write (ordinal n : Nat) : EffectBody := .assign .word ordinal (.wordLit n)
def ret : EffectBody := .returnValue .boolean (.boolLit true)
def sequential : EffectBody := .seq (write 0 1) (.seq (write 1 2) (.seq ret .skip))
def sequentialCode : List EffectOp := [
  .pure (.constant .word (.word 1)),.store .word 0,
  .pure (.constant .word (.word 2)),.store .word 1,
  .pure (.constant .boolean (.boolean true)),.pure .ret]
def conditional : EffectBody := .seq (.branch (.boolLit true) (.seq (write 0 1) .skip)) (.seq ret .skip)
def joined : List EffectOp := [
  .pure (.constant .boolean (.boolean true)),.pure (.branchFalse 5),
  .pure (.constant .word (.word 1)),.store .word 0,.pure (.jump 6),
  .pure .label,.pure .label,.pure (.constant .boolean (.boolean true)),.pure .ret]
def single : List EffectOp := [
  .pure (.constant .boolean (.boolean true)),.pure (.branchFalse 4),
  .pure (.constant .word (.word 1)),.store .word 0,.pure .label,
  .pure (.constant .boolean (.boolean true)),.pure .ret]

def ints (tag : String) (values : List Int) : Record := ⟨tag,values.map Field.integer,false⟩
def storeRow : Record := ints "ir-code" [0,0,0,-1,7,1,33,0,0,0,0,0,2]
def requireRow : Record := ints "ir-code" [0,0,0,-1,7,1,91,0,0,0,0,0,0]
def returnRow : Record := ints "ir-code" [0,1,0,-1,4,1,43,0,0,0,0,2,0]
def storeTables (ordinal typ : Int) : Tables := tables [
  ints "ir-type" [0,7,0,0,0,0,0,0,0],ints "ir-type" [1,1,0,0,0,0,0,0,0],
  ints "ir-class" [0,0,0],ints "ir-callable" [0,0,0,7,0,1,0,0],ints "ir-field" [0,0,0],
  storeRow,returnRow,ints "ir-operand" [0,23,ordinal,0,0,0],ints "ir-operand" [1,12,typ,0,0,0]]
def decodedStore (ordinal typ : Int) : Option EffectOp :=
  (decodeEffect (storeTables ordinal typ) 0 storeRow).map (·.operation)
def requireTables : Tables := tables [requireRow,returnRow]

def checks : List (String × Bool) := [
  ("ordered stores",accepted sequentialCode sequential),
  ("same-typed store swap rejects",!(accepted (sequentialCode.set 1 (.store .word 1)) sequential)),
  ("reordered source stores reject",!(accepted sequentialCode (.seq (write 1 2) (.seq (write 0 1) (.seq ret .skip))))),
  ("wrong store kind rejects",!(accepted (sequentialCode.set 1 (.store .boolean 0)) sequential)),
  ("require cannot replace store",!(accepted (sequentialCode.set 1 .require) sequential)),
  ("extra actual tail rejects complete check",!(accepted (sequentialCode ++ [.pure .label]) sequential)),
  ("unmatched source suffix after return rejects",!(accepted [.pure (.constant .boolean (.boolean true)),.pure .ret]
    (.seq ret (.seq (write 0 1) .skip)))),
  ("joined conditional",accepted joined conditional),
  ("single label conditional",accepted single conditional),
  ("wrong branch edge",!(accepted (joined.set 1 (.pure (.branchFalse 6))) conditional)),
  ("wrong join edge",!(accepted (joined.set 4 (.pure (.jump 5))) conditional)),
  ("missing join label",!(accepted (joined.set 6 (.pure .ret)) conditional)),
  ("effect hidden in expression",!(accepted (joined.set 0 (.store .boolean 0)) conditional)),
  ("require form accepted",accepted [.pure (.constant .boolean (.boolean true)),.require]
    (.seq (.require (.boolLit true)) .skip)),
  ("require cannot be label",!(accepted [.pure (.constant .boolean (.boolean true)),.pure .label]
    (.seq (.require (.boolLit true)) .skip))),
  ("canonical store projection",decodedStore 0 0 == some (.store .word 0)),
  ("store field type mismatch",decodedStore 0 1 == none),
  ("store ordinal out of range",decodedStore 1 0 == none),
  ("store negative ordinal",decodedStore (-1) 0 == none),
  ("canonical require projection",(decodeEffect requireTables 0 requireRow).map (·.operation) == some .require),
  ("require cannot decode pure",(decodeOperation requireTables 0 requireRow).isNone),
  ("store cannot decode pure",(decodeOperation (storeTables 0 0) 0 storeRow).isNone),
  ("wrong selected callable",(decodeEffect (storeTables 0 0) 1 storeRow).isNone),
  ("canonical exact position",canonicalEffects (storeTables 0 0) 0 0 == some (.store .word 0))]

example : BodyCode (fun _ => none) id .skip 3 3 := .skip
example : BodyCode (program [.pure (.constant .word (.word 1)),.store .word 0]) id (write 0 1) 0 2 :=
  .assign (.word rfl) rfl
#eval do
  for (name,success) in checks do
    unless success do throw (IO.userError s!"effect-code fixture failed: {name}")
  IO.println s!"NATIVE effect-code fixtures: {checks.length} passed; full-body boundary is explicit"
end EffectCodeFixtures
