import SourceBinding.IRSemantics
open Aurora.SourceBinding Aurora.Publication
namespace PrimitiveFixtures
-- Synthetic primitive inputs only: not full publication, entry binding, or whole guard certificates.
def source : SourceState := ⟨fun _ => some (.word 9), fun _ => some (.word 2)⟩
def underflow : GuardExpr .boolean := .compare .eq (.sub (.wordLit 0) (.wordLit 1)) (.wordLit 0)
example : evalGuard source (.or (.boolLit true) underflow) = .value (.boolean true) := by decide
example : evalGuard source (.and (.boolLit false) underflow) = .value (.boolean false) := by decide
example : evalGuard source (.or (.boolLit false) underflow) = .trap .underflow := by decide
example : evalGuard source (.and (.boolLit true) underflow) = .trap .underflow := by decide

def expression : GuardExpr .word := .sub (.wordLit 9) (.wordLit 2)
def program : Program := fun pc => match pc with
  | 0 => some (.constant .word (.word 9))
  | 1 => some .push
  | 2 => some (.constant .word (.word 2))
  | 3 => some (.binary .sub)
  | _ => none

def base : Machine := ⟨0, some (.boolean false), [.word 100, .boolean true],
  source.parameters, source.fields, fun _ => some (.word 77)⟩
-- Tiny kernel instantiation of generic simulation with a nonempty caller stack.
example : Runs program base (finish base 4 base.stack (evalGuard source expression)) := by
  have code : ExprCode program id expression 0 4 :=
    .sub (.word rfl) rfl (.word rfl) rfl
  exact code.simulates source base ⟨fun _ => rfl, fun _ => rfl⟩ base.accumulator base.stack

-- Test observation only: fuel exhaustion is not a divergence proof.
inductive Observation where
  | cut (pc : Nat) (accumulator : Option Value) (stack : List Value)
      (localValue fieldValue argumentValue : Option Value)
  | trapped (fault : Fault) | returned (value : Value)
  deriving BEq, Repr

def run (program : Program) : Nat → Machine → Observation
  | 0, machine => .cut machine.pc machine.accumulator machine.stack
      (machine.locals 0) (machine.receiver 43) (machine.arguments 0)
  | fuel + 1, machine => match step program machine with
    | .next next => run program fuel next
    | .trap fault => .trapped fault
    | .returned value => .returned value

def accepts {kind : GuardType} (code : Program) (expr : GuardExpr kind) : Bool :=
  (checkExprCode code id expr 0).isSome

def fieldProgram (ordinal : Nat) : Program := fun pc =>
  if pc = 0 then some (.receiver .word ordinal) else none

def fieldExpr : GuardExpr .word := .field .word "snapshot_phase".toUTF8 43

def ints (tag : String) (values : List Int) : Record := ⟨tag,values.map Field.integer,false⟩
def constantRow : Record := ints "ir-code" [0,0,0,-1,7,1,5,0,0,0,0,0,2]
def returnRow : Record := ints "ir-code" [0,1,0,-1,4,1,43,0,0,0,0,2,0]
def literalTables (signed unsigned : Int) : Tables := tables [
  ints "ir-type" [0,7,0,0,0,0,0,0,0], constantRow, returnRow,
  ints "ir-operand" [0,11,signed,unsigned,0,0],
  ints "ir-operand" [1,12,0,0,0,0]]
def decodedLiteral (signed unsigned : Int) : Option Op :=
  (decodeOperation (literalTables signed unsigned) 0 constantRow).map (·.operation)

def checks : List (String × Bool) := [
  ("OR skips underflow", evalGuard source (.or (.boolLit true) underflow) == .value (.boolean true)),
  ("AND skips underflow", evalGuard source (.and (.boolLit false) underflow) == .value (.boolean false)),
  ("OR reaches underflow", evalGuard source (.or (.boolLit false) underflow) == .trap .underflow),
  ("AND reaches underflow", evalGuard source (.and (.boolLit true) underflow) == .trap .underflow),
  ("word boundary rejects", evalGuard source (.wordLit wordLimit) == .trap .range),
  ("subtraction order", evalGuard source expression == .value (.word 7)),
  ("primitive code accepted", accepts program expression),
  ("nonempty stack and frame preserved", run program 4 base ==
    .cut 4 (some (.word 7)) [.word 100,.boolean true] (some (.word 2)) (some (.word 9)) (some (.word 77))),
  ("actual field ordinal accepted", accepts (fieldProgram 43) fieldExpr),
  ("same-typed field ordinal swap rejected", !(accepts (fieldProgram 42) fieldExpr)),
  ("primitive does not claim OR lowering", !(accepts program (.or (.boolLit true) underflow))),
  ("missing push rejects", !(accepts (fun pc => if pc = 1 then some .label else program pc) expression)),
  ("wrong binary rejects", !(accepts (fun pc => if pc = 3 then some (.binary (.compare .eq)) else program pc) expression)),
  ("IR underflow trap", run (fun pc => if pc = 0 then some (.constant .word (.word 1)) else program pc) 4 base == .trapped .underflow),
  ("unsupported instruction traps", run (fun _ => none) 1 base == .trapped .unsupported),
  ("unsigned slot3 literal", decodedLiteral 0 17 == some (.constant .word (.word 17))),
  ("unsigned maximum literal", decodedLiteral 0 18446744073709551615 == some (.constant .word (.word 18446744073709551615))),
  ("negative unsigned rejects", decodedLiteral 0 (-1) == none),
  ("unsigned overflow rejects", decodedLiteral 0 18446744073709551616 == none),
  ("noncanonical signed slot rejects", decodedLiteral 17 23 == none),
  ("candidate reads unsigned slot despite signed decoy", operationCandidate (literalTables 17 23) constantRow == some (.constant .word (.word 23))),
  ("canonical PC projection", canonicalProgram (literalTables 0 17) 0 0 == some (.constant .word (.word 17)))]

#eval do
  for (label, passed) in checks do
    unless passed do throw (IO.userError s!"primitive fixture failed: {label}")
  IO.println s!"NATIVE primitive fixtures: {checks.length} passed; no whole guard or entry-binding claim"
end PrimitiveFixtures
