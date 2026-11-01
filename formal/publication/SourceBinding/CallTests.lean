import SourceBinding.CallCode
import SourceBinding.IdentityTests
open Aurora.SourceBinding Aurora.Publication
namespace CallFixtures
open IdentityFixtures
-- Synthetic relation inputs, NOT full D1/D2 admission or production-byte proofs.
def resourceMethod (native : ByteArray := "__external".toUTF8) (effect : Int := 1) : Record :=
  ⟨"ir-resource-method",[.integer 0,.integer 0,.integer 1,.integer 1,.integer 2,.integer 2,
    .integer 7,.integer effect,.bytes native,.bytes "fill".toUTF8],false⟩
def callTables : Tables := { base with
  resources := #[setInt (resource 0 0 sourceResource) 2 1]
  catalogs := #[catalog 0 nativeName,⟨"ir-catalog-type",[.integer 1,.integer 1,.bytes ByteArray.empty],false⟩,
    ⟨"ir-catalog-type",[.integer 2,.integer 7,.bytes ByteArray.empty],false⟩]
  methods := #[resourceMethod] }
def ordinary := bindOrdinaryCall callTables moduleName classPath members memberName
def retained (t : Tables := callTables) := bindResourceCall t 0 members "authority".toUTF8 "fill".toUTF8

def parsed (body : String) (formal : String := "p") : Option (List CallPiece) := do
  let input := ("module m; namespace n { class C { builtin::Resource authority; u64 first; public: auto f(u64 " ++
    formal ++ ") -> bool { " ++ body ++ " } u64 last; }; }").toUTF8
  let file ← namedSource input
  let source ← checkedSelection [⟨input,file⟩] moduleName moduleName classPath memberName
  let typed ← callMethod callTables 0 moduleName classPath source.selected.classDecl.members input
    source.selected.method.function
  return typed.pieces

def program (ops : List Op) : Program := fun pc => ops[pc]?
def pair : CallArguments [.word,.boolean] := .cons (.wordLit 2) (.cons (.boolLit false) .nil)
def singleton : CallArguments [.word] := .cons (.wordLit 2) .nil
def pairCode : List Op := [.constant .word (.word 2),.push,.constant .boolean (.boolean false),.push]
def argsAccepted {kinds} (resource : Bool) (args : CallArguments kinds) (ops : List Op) : Bool :=
  match checkArguments (program ops) id resource args 0 with
  | some checked => checked.stop == ops.length
  | none => false

def callRow : Record := ints "ir-code" [0,0,0,-1,7,1,38,0,0,0,0,0,6]
def retRow : Record := ints "ir-code" [0,1,1,-1,4,1,43,0,0,0,0,6,0]
def ordinaryTables : Tables := { callTables with codes := #[callRow,retRow], operands := #[
  ints "ir-operand" [0,100,0,0,Int.ofNat cls.size,Int.ofNat meth.size],
  ints "ir-operand" [1,26,0,0,0,0],ints "ir-operand" [2,21,0,0,0,0],
  ints "ir-operand" [3,6,0,0,0,0],ints "ir-operand" [4,27,-1,0,0,0],ints "ir-operand" [5,8,0,0,0,0]] }
def resourceRow : Record := ints "ir-code" [0,0,0,-1,7,1,89,0,0,0,0,0,5]
def resourceTables : Tables := { callTables with codes := #[resourceRow,retRow], operands := #[
  ints "ir-operand" [0,24,0,0,0,0],ints "ir-operand" [1,23,0,0,0,0],
  ints "ir-operand" [2,106,0,0,0,0],ints "ir-operand" [3,6,0,0,0,0],ints "ir-operand" [4,105,0,0,0,0]] }

def returnPiece : List CallPiece := [.localBody (.returnValue .boolean (.boolLit true))]
def simpleTables : Tables := { callTables with
  codes := #[ints "ir-code" [0,0,0,-1,7,1,5,0,0,0,0,0,2],setInt retRow 11 2]
  operands := #[ints "ir-operand" [0,10,1,0,0,0],ints "ir-operand" [1,12,0,0,0,0]] }
def trailingTables : Tables := { simpleTables with codes := simpleTables.codes ++ #[
  ints "ir-code" [0,2,2,-1,7,1,5,0,0,0,0,0,2],
  ints "ir-code" [0,3,3,-1,4,1,43,0,0,0,0,2,0]] }
def labelledTables : Tables := { simpleTables with
  codes := #[ints "ir-code" [0,0,0,-1,7,1,40,0,0,0,0,0,1],
    ints "ir-code" [0,1,1,-1,6,1,5,0,0,0,0,1,2],ints "ir-code" [0,2,2,-1,4,1,43,0,0,0,0,3,0]]
  operands := #[ints "ir-operand" [0,29,99,0,0,0]] ++ simpleTables.operands }
def shapeAccepted (t : Tables) : Bool :=
  match checkCallPieces t 0 id returnPiece 0 with
  | some checked => checked.stop == (functionCode t 0).size
  | none => false

-- Tiny constructor proofs: independent grammar, no native_decide or concrete large reduction.
example : TypedArguments [] [] [] CallArguments.nil := .nil
example : PushedArgumentsCode (fun _ => none) id CallArguments.nil 0 0 := .nil
example : LabelRun (fun _ => some .label) 0 2 := .cons rfl (.cons rfl .nil)
example : CallReturns [.localBody (.returnValue .boolean (.boolLit true))] := .here .returnValue

#eval do
  let cases : List (String × Bool × Bool) := [
    ("complete pure piece boundary",shapeAccepted simpleTables,true),
    ("label-only prefix consumed",shapeAccepted labelledTables,true),
    ("unmatched trailing return suffix",shapeAccepted trailingTables,false),
    ("nonlabel cannot masquerade as padding",shapeAccepted { labelledTables with
      codes := labelledTables.codes.set! 0 (ints "ir-code" [0,0,0,-1,7,1,9,0,0,0,0,0,0]) },false),
    ("trailing ordinary call not omitted",shapeAccepted { simpleTables with codes := simpleTables.codes ++ #[callRow] },false),
    ("ordinary identity",ordinary.isSome,true),
    ("unknown self method",(bindOrdinaryCall callTables moduleName classPath members "missing".toUTF8).isSome,false),
    ("resource identity",(retained).isSome,true),
    ("resource missing source method",(bindResourceCall callTables 0 members "authority".toUTF8 "other".toUTF8).isSome,false),
    ("resource wrong field",(bindResourceCall callTables 0 members "first".toUTF8 "fill".toUTF8).isSome,false),
    ("unique source method",(retained { callTables with methods := #[resourceMethod,resourceMethod] }).isSome,false),
    ("effect0 unsupported",(retained { callTables with methods := #[resourceMethod "__external".toUTF8 0] }).isSome,false),
    ("effect2 unsupported",(retained { callTables with methods := #[resourceMethod "__external".toUTF8 2] }).isSome,false),
    ("changed nonempty native is a different valid interface",
      (retained { callTables with methods := #[resourceMethod "__changed".toUTF8] }).isSome,true),
    ("empty native rejected",(retained { callTables with methods := #[resourceMethod ByteArray.empty] }).isSome,false),
    ("argument count bounded",(retained { callTables with methods := #[setInt resourceMethod 4 65] }).isSome,false),
    ("negative argument count",(retained { callTables with methods := #[setInt resourceMethod 4 (-1)] }).isSome,false),
    ("ordinary args push all",argsAccepted false pair pairCode,true),
    ("resource multiple args push all",argsAccepted true pair pairCode,true),
    ("same typed value mismatch",argsAccepted false pair [.constant .word (.word 3),.push,.constant .boolean (.boolean false),.push],false),
    ("argument order",argsAccepted false pair [.constant .boolean (.boolean false),.push,.constant .word (.word 2),.push],false),
    ("missing final push",argsAccepted false pair pairCode.dropLast,false),
    ("ordinary singleton pushes",argsAccepted false singleton [.constant .word (.word 2),.push],true),
    ("ordinary singleton missing push",argsAccepted false singleton [.constant .word (.word 2)],false),
    ("resource singleton accumulator",argsAccepted true singleton [.constant .word (.word 2)],true),
    ("resource singleton rejects extra push at full boundary",argsAccepted true singleton [.constant .word (.word 2),.push],false),
    ("zero ordinary args",argsAccepted false CallArguments.nil [],true),
    ("zero resource args",argsAccepted true CallArguments.nil [],true)]
  for (label, actual, expected) in cases do
    unless actual == expected do throw (IO.userError s!"call fixture failed: {label}")
  let sourceCases : List (String × Bool) := [
    ("return true;",true),
    ("f(p); return true;",true),
    ("if (p == 0u64) { return false; } f(2u64); builtin::require(authority.fill(p,0u64)); f(p); return true;",true),
    ("f(true); return true;",false),
    ("f(); return true;",false),
    ("f(p,p); return true;",false),
    ("other::f(p); return true;",false),
    ("if (p == 0u64) { f(p); } return true;",false),
    ("f(f(p)); return true;",false),
    ("return f(p);",false),
    ("builtin::require(authority.fill(p)); return true;",false),
    ("builtin::require(authority.fill(p,true)); return true;",false),
    ("builtin::require(authority.other(p,0u64)); return true;",false),
    ("authority.fill(p,0u64); return true;",false),
    ("require(authority.fill(p,0u64)); return true;",false),
    ("builtin::require(authority.fill(p,0u64),true); return true;",false),
    ("return true; missing(p);",false),
    ("f(p);",false)]
  for (source, expected) in sourceCases do
    unless (parsed source).isSome == expected do throw (IO.userError s!"source call fixture failed: {source}")
  unless !(parsed "f(1u64); return true;" "f").isSome do throw (IO.userError "formal shadows method")
  let labels := checkLabels (program [.label,.label,.push,.label]) 20 0
  unless labels.stop == 2 do throw (IO.userError "nonlabel skipped")
  let limited := checkLabels (program [.label,.label]) 1 0
  unless limited.stop == 1 do throw (IO.userError "label fuel ignored")
  let some ordinary := ordinary | throw (IO.userError "ordinary descriptor absent")
  unless decide (InvocationAt ordinaryTables 0 0 (.ordinary ordinary.target)) do throw (IO.userError "ordinary row identity")
  unless !(decide (InvocationAt ordinaryTables 0 0 (.ordinary { ordinary.target with id := 1 }))) do
    throw (IO.userError "wrong callable accepted")
  let some resource := retained | throw (IO.userError "resource descriptor absent")
  unless decide (InvocationAt resourceTables 0 0 (.resource resource.target)) do throw (IO.userError "resource row identity")
  for target in [{ resource.target with fieldOrdinal := 1 },{ resource.target with method := 1 },
    { resource.target with resource := 1 },{ resource.target with native := "__other".toUTF8 },
    { resource.target with sourceType := ["builtin".toUTF8,"Other".toUTF8] },
    { resource.target with resourceCatalog := 1 },{ resource.target with resultCatalog := 2 },{ resource.target with parameterCatalog := 1 }] do
    unless !(decide (InvocationAt resourceTables 0 0 (.resource target))) do throw (IO.userError "descriptor mismatch accepted")
  IO.println s!"NATIVE call source/identity/argument fixtures: {cases.length + sourceCases.length + 14} passed"
end CallFixtures
