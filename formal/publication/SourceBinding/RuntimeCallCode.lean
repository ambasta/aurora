import SourceBinding.RuntimeCallProjection
import SourceBinding.RuntimeCallable
namespace Aurora.SourceBinding

deriving instance DecidableEq for CallOp

/- Call-containing expression certificates reuse the complete call-free grammar
    as atoms. This is a relation on the SAME raw AST and CallMachine, not a new
    expression language or arithmetic semantics. -/
mutual
inductive RuntimeCallExpressionCode (program : CallProgram) (caller : Int)
    (leaves : List (RuntimeCallable t files root module path)) (context : RuntimeExprContext) :
    SourceExpr → RuntimeType → Nat → Nat → Prop
  | local : RuntimeExpressionCode (localProgram program caller) context raw kind start stop →
      RuntimeCallExpressionCode program caller leaves context raw kind start stop
  | call : leaf ∈ leaves → leaf.source.Resolves context name →
      RuntimeCallArgumentsCode program caller leaves context arguments leaf.source.parameters start callPC →
      program caller callPC = some (.ordinary leaf.target) →
      RuntimeCallExpressionCode program caller leaves context (.call (.named name) arguments)
        leaf.source.result start (callPC + 1)
  | not : RuntimeCallExpressionCode program caller leaves context inner (.scalar .boolean) start middle →
      localProgram program caller middle = some (.pure .negate) →
      RuntimeCallExpressionCode program caller leaves context (.not inner) (.scalar .boolean) start (middle + 1)
  | wordBinary : RuntimeWordOperator operator primitive result →
      RuntimeCallExpressionCode program caller leaves context left (.scalar .word) start middle →
      localProgram program caller middle = some (.pure .push) →
      RuntimeCallExpressionCode program caller leaves context right (.scalar .word) (middle + 1) endPC →
      localProgram program caller endPC = some (.pure (.binary primitive)) →
      RuntimeCallExpressionCode program caller leaves context (.binary operator left right) (.scalar result) start (endPC + 1)
  | enumCompare {equal : Bool} : RuntimeCallExpressionCode program caller leaves context left (.nominal identity) start middle →
      localProgram program caller middle = some (.pure .push) →
      RuntimeCallExpressionCode program caller leaves context right (.nominal identity) (middle + 1) endPC →
      localProgram program caller endPC = some (.enumCompare identity equal) →
      RuntimeCallExpressionCode program caller leaves context (.binary (.compare (if equal then .eq else .ne)) left right)
        (.scalar .boolean) start (endPC + 1)
  | shiftLeft : RuntimeCallExpressionCode program caller leaves context left (.scalar .word) start middle →
      SourceShiftCount right count → localProgram program caller middle = some (.pure .push) →
      localProgram program caller (middle + 1) = some (runtimeCount count) →
      localProgram program caller (middle + 2) = some (.pure (.binary .leftShift)) →
      RuntimeCallExpressionCode program caller leaves context (.binary .shift left right) (.scalar .word) start (middle + 3)
  | shiftRight : RuntimeCallExpressionCode program caller leaves context left (.scalar .word) start middle →
      SourceShiftCount right count → localProgram program caller middle = some (.pure .push) →
      localProgram program caller (middle + 1) = some (runtimeCount count) →
      localProgram program caller (middle + 2) = some (.pure (.binary .rightShift)) →
      RuntimeCallExpressionCode program caller leaves context (.binary .rightShift left right) (.scalar .word) start (middle + 3)
  | and : RuntimeCallExpressionCode program caller leaves context left (.scalar .boolean) start middle →
      localProgram program caller middle = some (.pure (.branchFalse endPC)) →
      RuntimeCallExpressionCode program caller leaves context right (.scalar .boolean) (middle + 1) endPC →
      localProgram program caller endPC = some (.pure .label) →
      RuntimeCallExpressionCode program caller leaves context (.binary .and left right) (.scalar .boolean) start (endPC + 1)
  | or : RuntimeCallExpressionCode program caller leaves context left (.scalar .boolean) start middle →
      localProgram program caller middle = some (.pure (.branchFalse (middle + 2))) →
      localProgram program caller (middle + 1) = some (.pure (.jump endPC)) →
      localProgram program caller (middle + 2) = some (.pure .label) →
      RuntimeCallExpressionCode program caller leaves context right (.scalar .boolean) (middle + 3) endPC →
      localProgram program caller endPC = some (.pure .label) →
      RuntimeCallExpressionCode program caller leaves context (.binary .or left right) (.scalar .boolean) start (endPC + 1)


inductive RuntimeCallArgumentsCode (program : CallProgram) (caller : Int)
    (leaves : List (RuntimeCallable t files root module path)) (context : RuntimeExprContext) :
    List SourceExpr → List RuntimeType → Nat → Nat → Prop
  | nil : RuntimeCallArgumentsCode program caller leaves context [] [] start start
  | cons : RuntimeCallExpressionCode program caller leaves context first kind start middle →
      localProgram program caller middle = some (.pure .push) →
      RuntimeCallArgumentsCode program caller leaves context rest kinds (middle + 1) stop →
      RuntimeCallArgumentsCode program caller leaves context (first :: rest) (kind :: kinds) start stop
end

structure ParsedRuntimeCallExpression (program : CallProgram) (caller : Int)
    (leaves : List (RuntimeCallable t files root module path)) (context : RuntimeExprContext)
    (raw : SourceExpr) (start : Nat) where
  kind : RuntimeType
  stop : Nat
  grammar : RuntimeCallExpressionCode program caller leaves context raw kind start stop

structure ParsedRuntimeCallArguments (program : CallProgram) (caller : Int)
    (leaves : List (RuntimeCallable t files root module path)) (context : RuntimeExprContext)
    (raw : List SourceExpr) (start : Nat) where
  kinds : List RuntimeType
  stop : Nat
  grammar : RuntimeCallArgumentsCode program caller leaves context raw kinds start stop

def RuntimeCallExpressionCode.cast
    (code : RuntimeCallExpressionCode program caller leaves context raw kind start stop)
    (same : kind = other) : RuntimeCallExpressionCode program caller leaves context raw other start stop := same ▸ code

def RuntimeCallArgumentsCode.cast
    (code : RuntimeCallArgumentsCode program caller leaves context raw kinds start stop)
    (same : kinds = other) : RuntimeCallArgumentsCode program caller leaves context raw other start stop := same ▸ code

mutual
/-- Prefer the existing call-free checker; only call-containing raw syntax needs
    the compositional cases below. No source result is an input to checking. -/
def checkRuntimeCallExpressionCode (program : CallProgram) (caller : Int)
    (leaves : List (RuntimeCallable t files root module path)) (context : RuntimeExprContext) :
    (fuel : Nat) → (raw : SourceExpr) → (start : Nat) →
    Option (ParsedRuntimeCallExpression program caller leaves context raw start)
  | 0, _, _ => none
  | fuel + 1, raw, start =>
    match checkRuntimeExpressionCode (localProgram program caller) context 4096 raw start with
    | some localCode => some ⟨localCode.kind,localCode.stop,.local localCode.grammar⟩
    | none => match raw with
      | .call (.named name) arguments => do
        match found : leaves.find? (fun leaf => decide (leaf.source.Resolves context name)) with
        | none => none
        | some leaf =>
          if resolves : leaf.source.Resolves context name then
            let args ← checkRuntimeCallArgumentsCode program caller leaves context fuel arguments start
            if kinds : args.kinds = leaf.source.parameters then
              if invocation : program caller args.stop = some (.ordinary leaf.target) then
                return ⟨leaf.source.result,args.stop + 1,.call (List.mem_of_find?_eq_some found)
                  resolves (args.grammar.cast kinds) invocation⟩
              else none
            else none
          else none
      | .not inner => do
        let child ← checkRuntimeCallExpressionCode program caller leaves context fuel inner start
        if boolean : child.kind = .scalar .boolean then
          if code : localProgram program caller child.stop = some (.pure .negate) then
            return ⟨.scalar .boolean,child.stop + 1,.not (child.grammar.cast boolean) code⟩
          else none
        else none
      | .binary .shift left right => do
        let child ← checkRuntimeCallExpressionCode program caller leaves context fuel left start
        let count ← sourceShiftCount right
        if word : child.kind = .scalar .word then
          if push : localProgram program caller child.stop = some (.pure .push) then
            if literal : localProgram program caller (child.stop + 1) = some (runtimeCount count.val) then
              if operation : localProgram program caller (child.stop + 2) = some (.pure (.binary .leftShift)) then
                return ⟨.scalar .word,child.stop + 3,.shiftLeft (child.grammar.cast word) count.property push literal operation⟩
              else none
            else none
          else none
        else none
      | .binary .rightShift left right => do
        let child ← checkRuntimeCallExpressionCode program caller leaves context fuel left start
        let count ← sourceShiftCount right
        if word : child.kind = .scalar .word then
          if push : localProgram program caller child.stop = some (.pure .push) then
            if literal : localProgram program caller (child.stop + 1) = some (runtimeCount count.val) then
              if operation : localProgram program caller (child.stop + 2) = some (.pure (.binary .rightShift)) then
                return ⟨.scalar .word,child.stop + 3,.shiftRight (child.grammar.cast word) count.property push literal operation⟩
              else none
            else none
          else none
        else none
      | .binary .and left right => do
        let l ← checkRuntimeCallExpressionCode program caller leaves context fuel left start
        let r ← checkRuntimeCallExpressionCode program caller leaves context fuel right (l.stop + 1)
        if lb : l.kind = .scalar .boolean then
          if rb : r.kind = .scalar .boolean then
            if branch : localProgram program caller l.stop = some (.pure (.branchFalse r.stop)) then
              if label : localProgram program caller r.stop = some (.pure .label) then
                return ⟨.scalar .boolean,r.stop + 1,.and (l.grammar.cast lb) branch (r.grammar.cast rb) label⟩
              else none
            else none
          else none
        else none
      | .binary .or left right => do
        let l ← checkRuntimeCallExpressionCode program caller leaves context fuel left start
        let r ← checkRuntimeCallExpressionCode program caller leaves context fuel right (l.stop + 3)
        if lb : l.kind = .scalar .boolean then
          if rb : r.kind = .scalar .boolean then
            if branch : localProgram program caller l.stop = some (.pure (.branchFalse (l.stop + 2))) then
              if jump : localProgram program caller (l.stop + 1) = some (.pure (.jump r.stop)) then
                if rightLabel : localProgram program caller (l.stop + 2) = some (.pure .label) then
                  if label : localProgram program caller r.stop = some (.pure .label) then
                    return ⟨.scalar .boolean,r.stop + 1,.or (l.grammar.cast lb) branch jump rightLabel (r.grammar.cast rb) label⟩
                  else none
                else none
              else none
            else none
          else none
        else none
      | .binary (.compare comparison) left right => do
        let l ← checkRuntimeCallExpressionCode program caller leaves context fuel left start
        if push : localProgram program caller l.stop = some (.pure .push) then
          let r ← checkRuntimeCallExpressionCode program caller leaves context fuel right (l.stop + 1)
          match lk : l.kind, rk : r.kind with
          | .scalar .word, .scalar .word =>
            if operation : localProgram program caller r.stop = some (.pure (.binary (.compare comparison))) then
              return ⟨.scalar .boolean,r.stop + 1,.wordBinary .compare (l.grammar.cast lk) push (r.grammar.cast rk) operation⟩
            else none
          | .nominal a, .nominal b =>
            if same : b = a then
              if equal : comparison = .eq then
                if operation : localProgram program caller r.stop = some (.enumCompare a true) then
                  return ⟨.scalar .boolean,r.stop + 1,by
                    simpa only [equal] using (RuntimeCallExpressionCode.enumCompare (equal := true)
                      (l.grammar.cast lk) push (r.grammar.cast (rk.trans (congrArg RuntimeType.nominal same))) operation)⟩
                else none
              else if different : comparison = .ne then
                if operation : localProgram program caller r.stop = some (.enumCompare a false) then
                  return ⟨.scalar .boolean,r.stop + 1,by
                    simpa only [different] using (RuntimeCallExpressionCode.enumCompare (equal := false)
                      (l.grammar.cast lk) push (r.grammar.cast (rk.trans (congrArg RuntimeType.nominal same))) operation)⟩
                else none
              else none
            else none
          | _, _ => none
        else none
      | .binary operator left right => do
        let choice ← runtimeWordChoice operator
        let l ← checkRuntimeCallExpressionCode program caller leaves context fuel left start
        if lw : l.kind = .scalar .word then
          if push : localProgram program caller l.stop = some (.pure .push) then
            let r ← checkRuntimeCallExpressionCode program caller leaves context fuel right (l.stop + 1)
            if rw : r.kind = .scalar .word then
              if operation : localProgram program caller r.stop = some (.pure (.binary choice.primitive)) then
                return ⟨.scalar choice.result,r.stop + 1,
                  .wordBinary choice.grammar (l.grammar.cast lw) push (r.grammar.cast rw) operation⟩
              else none
            else none
          else none
        else none
      | _ => none

def checkRuntimeCallArgumentsCode (program : CallProgram) (caller : Int)
    (leaves : List (RuntimeCallable t files root module path)) (context : RuntimeExprContext) :
    (fuel : Nat) → (raw : List SourceExpr) → (start : Nat) →
    Option (ParsedRuntimeCallArguments program caller leaves context raw start)
  | 0, _, _ => none
  | _ + 1, [], start => some ⟨[],start,.nil⟩
  | fuel + 1, first :: rest, start => do
    let head ← checkRuntimeCallExpressionCode program caller leaves context fuel first start
    if push : localProgram program caller head.stop = some (.pure .push) then
      let tail ← checkRuntimeCallArgumentsCode program caller leaves context fuel rest (head.stop + 1)
      return ⟨head.kind :: tail.kinds,tail.stop,.cons head.grammar push tail.grammar⟩
    else none
end

end Aurora.SourceBinding
