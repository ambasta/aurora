import SourceBinding.RuntimeExpressions
import SourceBinding.EffectCode
namespace Aurora.SourceBinding

/-- Reuses the existing canonical effect machine. No alternative decoder or
    scalar arithmetic is introduced by this source-use relation. -/
def runtimeLoad (kind : RuntimeType) (slot : Nat) : EffectOp :=
  match kind with
  | .scalar scalar => .pure (.load scalar slot)
  | .nominal identity => .enumLoad identity slot

def runtimeCount : SignedLiteralCount → EffectOp
  | .four => .pure .count4
  | .twelve => .pure .count12
  | .thirtyTwo => .pure .count32

inductive RuntimeExpressionCode (program : EffectProgram) (context : RuntimeExprContext) :
    SourceExpr → RuntimeType → Nat → Nat → Prop
  | word : value < wordLimit → program start = some (.pure (.constant .word (.word value))) →
      RuntimeExpressionCode program context (.word value) (.scalar .word) start (start + 1)
  | boolean : program start = some (.pure (.constant .boolean (.boolean value))) →
      RuntimeExpressionCode program context (.boolean value) (.scalar .boolean) start (start + 1)
  | readVariable : RuntimeVariableBinding context name binding →
      program start = some (runtimeLoad binding.kind binding.slot) →
      RuntimeExpressionCode program context (.name [name]) binding.kind start (start + 1)
  | enumValue : RuntimeEnumValue context name identity ordinal →
      program start = some (.enumConstant identity ordinal) →
      RuntimeExpressionCode program context (.name name) (.nominal identity) start (start + 1)
  | not : RuntimeExpressionCode program context inner (.scalar .boolean) start middle →
      program middle = some (.pure .negate) →
      RuntimeExpressionCode program context (.not inner) (.scalar .boolean) start (middle + 1)
  | wordBinary : RuntimeWordOperator operator primitive result →
      RuntimeExpressionCode program context left (.scalar .word) start middle →
      program middle = some (.pure .push) →
      RuntimeExpressionCode program context right (.scalar .word) (middle + 1) endPC →
      program endPC = some (.pure (.binary primitive)) →
      RuntimeExpressionCode program context (.binary operator left right) (.scalar result) start (endPC + 1)
  | enumCompare {equal : Bool} : RuntimeExpressionCode program context left (.nominal identity) start middle →
      program middle = some (.pure .push) →
      RuntimeExpressionCode program context right (.nominal identity) (middle + 1) endPC →
      program endPC = some (.enumCompare identity equal) →
      RuntimeExpressionCode program context (.binary (.compare (if equal then .eq else .ne)) left right)
        (.scalar .boolean) start (endPC + 1)
  | shiftLeft : RuntimeExpressionCode program context left (.scalar .word) start middle →
      SourceShiftCount right count → program middle = some (.pure .push) →
      program (middle + 1) = some (runtimeCount count) →
      program (middle + 2) = some (.pure (.binary .leftShift)) →
      RuntimeExpressionCode program context (.binary .shift left right) (.scalar .word) start (middle + 3)
  | shiftRight : RuntimeExpressionCode program context left (.scalar .word) start middle →
      SourceShiftCount right count → program middle = some (.pure .push) →
      program (middle + 1) = some (runtimeCount count) →
      program (middle + 2) = some (.pure (.binary .rightShift)) →
      RuntimeExpressionCode program context (.binary .rightShift left right) (.scalar .word) start (middle + 3)
  | and : RuntimeExpressionCode program context left (.scalar .boolean) start middle →
      program middle = some (.pure (.branchFalse endPC)) →
      RuntimeExpressionCode program context right (.scalar .boolean) (middle + 1) endPC →
      program endPC = some (.pure .label) →
      RuntimeExpressionCode program context (.binary .and left right) (.scalar .boolean) start (endPC + 1)
  | or : RuntimeExpressionCode program context left (.scalar .boolean) start middle →
      program middle = some (.pure (.branchFalse (middle + 2))) →
      program (middle + 1) = some (.pure (.jump endPC)) →
      program (middle + 2) = some (.pure .label) →
      RuntimeExpressionCode program context right (.scalar .boolean) (middle + 3) endPC →
      program endPC = some (.pure .label) →
      RuntimeExpressionCode program context (.binary .or left right) (.scalar .boolean) start (endPC + 1)

/-- The instruction/use grammar itself entails source typing; a separate claimed
    type cannot disguise a word comparison of nominal enum values. -/
theorem RuntimeExpressionCode.typed (code : RuntimeExpressionCode program context source kind start stop) :
    RuntimeExprTyped context source kind := by
  induction code with
  | word bound _ => exact .word bound
  | boolean _ => exact .boolean
  | readVariable binding _ => exact .readVariable binding
  | enumValue binding _ => exact .enumValue binding
  | not _ _ ih => exact .not ih
  | wordBinary operator _ _ _ _ left right => exact .wordBinary operator left right
  | enumCompare _ _ _ _ left right => exact .enumCompare left right
  | shiftLeft _ count _ _ _ ih => exact .shiftLeft ih count
  | shiftRight _ count _ _ _ ih => exact .shiftRight ih count
  | and _ _ _ _ left right => exact .and left right
  | or _ _ _ _ _ _ left right => exact .or left right

structure ParsedRuntimeExpressionCode (program : EffectProgram) (context : RuntimeExprContext)
    (source : SourceExpr) (start : Nat) where
  kind : RuntimeType
  stop : Nat
  grammar : RuntimeExpressionCode program context source kind start stop

def RuntimeExpressionCode.cast (code : RuntimeExpressionCode program context source kind start stop)
    (same : kind = other) : RuntimeExpressionCode program context source other start stop := same ▸ code

structure RuntimeWordChoice (operator : SourceBinOp) where
  primitive : Binary
  result : GuardType
  grammar : RuntimeWordOperator operator primitive result

def runtimeWordChoice : (operator : SourceBinOp) → Option (RuntimeWordChoice operator)
  | .add => some ⟨.add,.word,.add⟩
  | .subtract => some ⟨.sub,.word,.subtract⟩
  | .bitAnd => some ⟨.bitAnd,.word,.bitAnd⟩
  | .bitOr => some ⟨.bitOr,.word,.bitOr⟩
  | .compare comparison => some ⟨.compare comparison,.boolean,.compare⟩
  | _ => none

/-- Candidate structural lowering is checked against the independent relation.
    No successful source evaluation is an input to this matcher. -/
def checkRuntimeExpressionCode (program : EffectProgram) (context : RuntimeExprContext) :
    (fuel : Nat) → (source : SourceExpr) → (start : Nat) →
    Option (ParsedRuntimeExpressionCode program context source start)
  | 0, _, _ => none
  | fuel + 1, source, start => match source with
    | .word value =>
      if bound : value < wordLimit then
        if code : program start = some (.pure (.constant .word (.word value))) then
          some ⟨.scalar .word,start + 1,.word bound code⟩
        else none
      else none
    | .boolean value =>
      if code : program start = some (.pure (.constant .boolean (.boolean value))) then
        some ⟨.scalar .boolean,start + 1,.boolean code⟩
      else none
    | .signed12 | .signedCount _ | .call _ _ => none
    | .name [name] => do
      let resolved ← resolveRuntimeVariable context name
      if code : program start = some (runtimeLoad resolved.binding.kind resolved.binding.slot) then
        return ⟨resolved.binding.kind,start + 1,.readVariable resolved.grammar code⟩
      else none
    | .name name => do
      let resolved ← resolveRuntimeEnum context name
      if code : program start = some (.enumConstant resolved.identity resolved.ordinal) then
        return ⟨.nominal resolved.identity,start + 1,.enumValue resolved.grammar code⟩
      else none
    | .not inner => do
      let child ← checkRuntimeExpressionCode program context fuel inner start
      if boolean : child.kind = .scalar .boolean then
        if code : program child.stop = some (.pure .negate) then
          return ⟨.scalar .boolean,child.stop + 1,.not (child.grammar.cast boolean) code⟩
        else none
      else none
    | .binary .shift left right => do
      let child ← checkRuntimeExpressionCode program context fuel left start
      let count ← sourceShiftCount right
      if word : child.kind = .scalar .word then
        if push : program child.stop = some (.pure .push) then
          if literal : program (child.stop + 1) = some (runtimeCount count.val) then
            if operation : program (child.stop + 2) = some (.pure (.binary .leftShift)) then
              return ⟨.scalar .word,child.stop + 3,.shiftLeft (child.grammar.cast word) count.property push literal operation⟩
            else none
          else none
        else none
      else none
    | .binary .rightShift left right => do
      let child ← checkRuntimeExpressionCode program context fuel left start
      let count ← sourceShiftCount right
      if word : child.kind = .scalar .word then
        if push : program child.stop = some (.pure .push) then
          if literal : program (child.stop + 1) = some (runtimeCount count.val) then
            if operation : program (child.stop + 2) = some (.pure (.binary .rightShift)) then
              return ⟨.scalar .word,child.stop + 3,.shiftRight (child.grammar.cast word) count.property push literal operation⟩
            else none
          else none
        else none
      else none
    | .binary .and left right => do
      let l ← checkRuntimeExpressionCode program context fuel left start
      let r ← checkRuntimeExpressionCode program context fuel right (l.stop + 1)
      if lb : l.kind = .scalar .boolean then
        if rb : r.kind = .scalar .boolean then
          if branch : program l.stop = some (.pure (.branchFalse r.stop)) then
            if label : program r.stop = some (.pure .label) then
              return ⟨.scalar .boolean,r.stop + 1,.and (l.grammar.cast lb) branch (r.grammar.cast rb) label⟩
            else none
          else none
        else none
      else none
    | .binary .or left right => do
      let l ← checkRuntimeExpressionCode program context fuel left start
      let r ← checkRuntimeExpressionCode program context fuel right (l.stop + 3)
      if lb : l.kind = .scalar .boolean then
        if rb : r.kind = .scalar .boolean then
          if branch : program l.stop = some (.pure (.branchFalse (l.stop + 2))) then
            if jump : program (l.stop + 1) = some (.pure (.jump r.stop)) then
              if rightLabel : program (l.stop + 2) = some (.pure .label) then
                if label : program r.stop = some (.pure .label) then
                  return ⟨.scalar .boolean,r.stop + 1,.or (l.grammar.cast lb) branch jump rightLabel (r.grammar.cast rb) label⟩
                else none
              else none
            else none
          else none
        else none
      else none
    | .binary (.compare comparison) left right => do
      let l ← checkRuntimeExpressionCode program context fuel left start
      if push : program l.stop = some (.pure .push) then
        let r ← checkRuntimeExpressionCode program context fuel right (l.stop + 1)
        match lk : l.kind, rk : r.kind with
        | .scalar .word, .scalar .word =>
          if operation : program r.stop = some (.pure (.binary (.compare comparison))) then
            return ⟨.scalar .boolean,r.stop + 1,.wordBinary .compare (l.grammar.cast lk) push (r.grammar.cast rk) operation⟩
          else none
        | .nominal a, .nominal b =>
          if same : b = a then
            if equal : comparison = .eq then
              if operation : program r.stop = some (.enumCompare a true) then
                return ⟨.scalar .boolean,r.stop + 1,by
                  simpa only [equal] using (RuntimeExpressionCode.enumCompare (equal := true)
                    (l.grammar.cast lk) push (r.grammar.cast (rk.trans (congrArg RuntimeType.nominal same))) operation)⟩
              else none
            else if different : comparison = .ne then
              if operation : program r.stop = some (.enumCompare a false) then
                return ⟨.scalar .boolean,r.stop + 1,by
                  simpa only [different] using (RuntimeExpressionCode.enumCompare (equal := false)
                    (l.grammar.cast lk) push (r.grammar.cast (rk.trans (congrArg RuntimeType.nominal same))) operation)⟩
              else none
            else none
          else none
        | _, _ => none
      else none
    | .binary operator left right => do
      let choice ← runtimeWordChoice operator
      let l ← checkRuntimeExpressionCode program context fuel left start
      if lw : l.kind = .scalar .word then
        if push : program l.stop = some (.pure .push) then
          let r ← checkRuntimeExpressionCode program context fuel right (l.stop + 1)
          if rw : r.kind = .scalar .word then
            if operation : program r.stop = some (.pure (.binary choice.primitive)) then
              return ⟨.scalar choice.result,r.stop + 1,
                .wordBinary choice.grammar (l.grammar.cast lw) push (r.grammar.cast rw) operation⟩
            else none
          else none
        else none
      else none

/-- Left-to-right argument evaluation followed by one push per argument. This
    profile does not invoke a callee or use resource accumulator conventions. -/
inductive RuntimeArgumentsCode (program : EffectProgram) (context : RuntimeExprContext) :
    List SourceExpr → List RuntimeType → Nat → Nat → Prop
  | nil : RuntimeArgumentsCode program context [] [] start start
  | cons : RuntimeExpressionCode program context first kind start middle →
      program middle = some (.pure .push) →
      RuntimeArgumentsCode program context rest kinds (middle + 1) stop →
      RuntimeArgumentsCode program context (first :: rest) (kind :: kinds) start stop

theorem RuntimeArgumentsCode.typed (code : RuntimeArgumentsCode program context sources kinds start stop) :
    RuntimeArgumentsTyped context sources kinds := by
  induction code with
  | nil => exact .nil
  | cons first _ _ rest => exact .cons first.typed rest

structure ParsedRuntimeArgumentsCode (program : EffectProgram) (context : RuntimeExprContext)
    (sources : List SourceExpr) (start : Nat) where
  kinds : List RuntimeType
  stop : Nat
  grammar : RuntimeArgumentsCode program context sources kinds start stop

def checkRuntimeArgumentsCode (program : EffectProgram) (context : RuntimeExprContext) :
    (sources : List SourceExpr) → (start : Nat) → Option (ParsedRuntimeArgumentsCode program context sources start)
  | [], start => some ⟨[],start,.nil⟩
  | first :: rest, start => do
    let head ← checkRuntimeExpressionCode program context 4096 first start
    if push : program head.stop = some (.pure .push) then
      let tail ← checkRuntimeArgumentsCode program context rest (head.stop + 1)
      return ⟨head.kind :: tail.kinds,tail.stop,.cons head.grammar push tail.grammar⟩
    else none

structure CheckedRuntimeExpressionCode (program : EffectProgram) (context : RuntimeExprContext)
    (source : SourceExpr) (start : Nat) where
  valid : RuntimeContextValid context
  code : ParsedRuntimeExpressionCode program context source start

def bindRuntimeExpressionCode (program : EffectProgram) (context : RuntimeExprContext)
    (source : SourceExpr) (start : Nat) : Option (CheckedRuntimeExpressionCode program context source start) := do
  let valid ← checkRuntimeContext context
  let code ← checkRuntimeExpressionCode program context 4096 source start
  return ⟨valid.property,code⟩

end Aurora.SourceBinding
