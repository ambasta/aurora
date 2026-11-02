import SourceBinding.LocalBinding
import SourceBinding.RuntimePrimitives
namespace Aurora.SourceBinding

/-- Lexical data only. The enclosing selected-function certificate supplies the
    actual namespace/formals/visible source declarations. -/
structure RuntimeExprContext where
  members : List Declaration
  module : Name
  path : Name
  formals : List Formal
  visible : List SourceLocal

def RuntimeContextNames (context : RuntimeExprContext) : Prop :=
  FormalNames context.formals ∧ (context.visible.map (·.name)).Nodup ∧
  (context.visible.map (·.slot)).Nodup ∧
  (∀ binding ∈ context.visible, NameAllowed binding.name ∧
    binding.name ∉ context.formals.map (·.name) ∧
    8 * context.formals.length < binding.slot ∧ binding.slot % 8 = 0) ∧
  (∀ formal ∈ context.formals, TypeUnshadowed context.formals [] formal.type)
instance (context : RuntimeExprContext) : Decidable (RuntimeContextNames context) := by
  unfold RuntimeContextNames; infer_instance

structure RuntimeContextValid (context : RuntimeExprContext) : Prop where
  scope : ScopeBindings context.members
  names : RuntimeContextNames context

def checkRuntimeContext (context : RuntimeExprContext) : Option { _witness : Unit // RuntimeContextValid context } := do
  let scope ← checkScopeBindings 4096 context.members
  if names : RuntimeContextNames context then return ⟨(),⟨scope.property,names⟩⟩ else none

/-- Formal cells are immutable in scope zero. Locals retain their exact source
    type, mutability, scope and physical private-slot identity. -/
inductive RuntimeVariableBinding (context : RuntimeExprContext) (name : ByteArray) : SourceLocal → Prop
  | formal {declaration : Formal} : context.formals[index]? = some declaration → declaration.name = name →
      RuntimeSourceType context.members context.module context.path declaration.type kind →
      name ∉ context.visible.map (·.name) →
      RuntimeVariableBinding context name ⟨name,kind,false,0,8 * (index + 1)⟩
  | localValue : binding ∈ context.visible → binding.name = name →
      name ∉ context.formals.map (·.name) → RuntimeVariableBinding context name binding

structure ResolvedRuntimeVariable (context : RuntimeExprContext) (name : ByteArray) where
  binding : SourceLocal
  grammar : RuntimeVariableBinding context name binding

def resolveRuntimeVariable (context : RuntimeExprContext) (name : ByteArray) :
    Option (ResolvedRuntimeVariable context name) := do
  match context.formals.zipIdx.find? (fun item => item.1.name == name) with
  | some (declaration,index) =>
    if present : context.formals[index]? = some declaration then
      if named : declaration.name = name then
        if clear : name ∉ context.visible.map (·.name) then
          let typ ← resolveRuntimeType context.members context.module context.path declaration.type
          return ⟨⟨name,typ.kind,false,0,8 * (index + 1)⟩,.formal present named typ.typing clear⟩
        else none
      else none
    else none
  | none =>
    match foundLocal : context.visible.find? (fun item => item.name == name) with
    | none => none
    | some binding =>
      if named : binding.name = name then
        if clear : name ∉ context.formals.map (·.name) then
          return ⟨binding,.localValue (List.mem_of_find?_eq_some foundLocal) named clear⟩
        else none
      else none

inductive RuntimeEnumValue (context : RuntimeExprContext) : Name → NominalIdentity → Nat → Prop
  | caseValue {enumName caseName : ByteArray} {cases : List ByteArray} :
      Declaration.enumDecl enumName cases ∈ context.members → cases[ordinal]? = some caseName →
      (source = [enumName,caseName] ∨ source = context.path ++ [enumName,caseName]) →
      Unshadowed context.formals context.visible source →
      RuntimeEnumValue context source ⟨enumSymbol context.module context.path enumName,cases.length⟩ ordinal

structure ResolvedRuntimeEnum (context : RuntimeExprContext) (source : Name) where
  identity : NominalIdentity
  ordinal : Nat
  grammar : RuntimeEnumValue context source identity ordinal

def resolveRuntimeEnum (context : RuntimeExprContext) (source : Name) : Option (ResolvedRuntimeEnum context source) := do
  let caseName ← source.getLast?
  let enumName ← source.dropLast.getLast?
  let found ← findEnum context.members enumName
  let ordinal ← found.cases.findIdx? (· == caseName)
  if present : found.cases[ordinal]? = some caseName then
    if named : source = [enumName,caseName] ∨ source = context.path ++ [enumName,caseName] then
      if clear : Unshadowed context.formals context.visible source then
        return ⟨⟨enumSymbol context.module context.path enumName,found.cases.length⟩,ordinal,
          .caseValue found.present present named clear⟩
      else none
    else none
  else none

/-- Transient counts only occur syntactically as the right operand of a shift.
    They are not ordinary expression values, variables, arguments or returns. -/
inductive SourceShiftCount : SourceExpr → SignedLiteralCount → Prop
  | four : SourceShiftCount (.signedCount 4) .four
  | twelve : SourceShiftCount .signed12 .twelve
  | thirtyTwo : SourceShiftCount (.signedCount 32) .thirtyTwo

def sourceShiftCount : (source : SourceExpr) → Option { count : SignedLiteralCount // SourceShiftCount source count }
  | .signed12 => some ⟨.twelve,.twelve⟩
  | .signedCount 4 => some ⟨.four,.four⟩
  | .signedCount 32 => some ⟨.thirtyTwo,.thirtyTwo⟩
  | _ => none

/-- Shared primitive operator selection, separate from operand evaluation. -/
inductive RuntimeWordOperator : SourceBinOp → Binary → GuardType → Prop
  | add : RuntimeWordOperator .add .add .word
  | subtract : RuntimeWordOperator .subtract .sub .word
  | bitAnd : RuntimeWordOperator .bitAnd .bitAnd .word
  | bitOr : RuntimeWordOperator .bitOr .bitOr .word
  | compare : RuntimeWordOperator (.compare comparison) (.compare comparison) .boolean

inductive RuntimeExprTyped (context : RuntimeExprContext) : SourceExpr → RuntimeType → Prop
  | word : value < wordLimit → RuntimeExprTyped context (.word value) (.scalar .word)
  | boolean : RuntimeExprTyped context (.boolean value) (.scalar .boolean)
  | readVariable : RuntimeVariableBinding context name binding →
      RuntimeExprTyped context (.name [name]) binding.kind
  | enumValue : RuntimeEnumValue context source identity ordinal →
      RuntimeExprTyped context (.name source) (.nominal identity)
  | not : RuntimeExprTyped context inner (.scalar .boolean) →
      RuntimeExprTyped context (.not inner) (.scalar .boolean)
  | wordBinary : RuntimeWordOperator operator primitive result →
      RuntimeExprTyped context left (.scalar .word) → RuntimeExprTyped context right (.scalar .word) →
      RuntimeExprTyped context (.binary operator left right) (.scalar result)
  | enumCompare {equal : Bool} : RuntimeExprTyped context left (.nominal identity) →
      RuntimeExprTyped context right (.nominal identity) →
      RuntimeExprTyped context (.binary (.compare (if equal then .eq else .ne)) left right) (.scalar .boolean)
  | shiftLeft : RuntimeExprTyped context left (.scalar .word) → SourceShiftCount right count →
      RuntimeExprTyped context (.binary .shift left right) (.scalar .word)
  | shiftRight : RuntimeExprTyped context left (.scalar .word) → SourceShiftCount right count →
      RuntimeExprTyped context (.binary .rightShift left right) (.scalar .word)
  | and : RuntimeExprTyped context left (.scalar .boolean) → RuntimeExprTyped context right (.scalar .boolean) →
      RuntimeExprTyped context (.binary .and left right) (.scalar .boolean)
  | or : RuntimeExprTyped context left (.scalar .boolean) → RuntimeExprTyped context right (.scalar .boolean) →
      RuntimeExprTyped context (.binary .or left right) (.scalar .boolean)

structure InferredRuntimeExpression (context : RuntimeExprContext) (source : SourceExpr) where
  kind : RuntimeType
  typing : RuntimeExprTyped context source kind

def RuntimeExprTyped.cast (typed : RuntimeExprTyped context source kind) (same : kind = other) :
    RuntimeExprTyped context source other := same ▸ typed

/-- Candidate type inference returns an independent source typing certificate.
    Calls are intentionally absent from this first slice. -/
def inferRuntimeExpression (context : RuntimeExprContext) : (fuel : Nat) → (source : SourceExpr) →
    Option (InferredRuntimeExpression context source)
  | 0, _ => none
  | fuel + 1, source => match source with
    | .word value => if bound : value < wordLimit then some ⟨.scalar .word,.word bound⟩ else none
    | .boolean _ => some ⟨.scalar .boolean,.boolean⟩
    | .signed12 | .signedCount _ | .call _ _ => none
    | .name [name] => do
      let resolved ← resolveRuntimeVariable context name
      return ⟨resolved.binding.kind,.readVariable resolved.grammar⟩
    | .name name => do
      let nominal ← resolveRuntimeEnum context name
      return ⟨.nominal nominal.identity,.enumValue nominal.grammar⟩
    | .not inner => do
      let checked ← inferRuntimeExpression context fuel inner
      if boolean : checked.kind = .scalar .boolean then return ⟨.scalar .boolean,.not (checked.typing.cast boolean)⟩
      else none
    | .binary .shift left right => do
      let checked ← inferRuntimeExpression context fuel left
      let count ← sourceShiftCount right
      if word : checked.kind = .scalar .word then return ⟨.scalar .word,.shiftLeft (checked.typing.cast word) count.property⟩
      else none
    | .binary .rightShift left right => do
      let checked ← inferRuntimeExpression context fuel left
      let count ← sourceShiftCount right
      if word : checked.kind = .scalar .word then return ⟨.scalar .word,.shiftRight (checked.typing.cast word) count.property⟩
      else none
    | .binary operator left right => do
      let l ← inferRuntimeExpression context fuel left
      let r ← inferRuntimeExpression context fuel right
      match operator with
      | .shift | .rightShift => none
      | .and =>
        if lb : l.kind = .scalar .boolean then
          if rb : r.kind = .scalar .boolean then return ⟨.scalar .boolean,.and (l.typing.cast lb) (r.typing.cast rb)⟩
          else none
        else none
      | .or =>
        if lb : l.kind = .scalar .boolean then
          if rb : r.kind = .scalar .boolean then return ⟨.scalar .boolean,.or (l.typing.cast lb) (r.typing.cast rb)⟩
          else none
        else none
      | .compare comparison =>
        match lk : l.kind, rk : r.kind with
        | .scalar .word, .scalar .word =>
          return ⟨.scalar .boolean,.wordBinary .compare (l.typing.cast lk) (r.typing.cast rk)⟩
        | .nominal a, .nominal b =>
          if same : b = a then
            if equal : comparison = .eq then
              return ⟨.scalar .boolean,by
                simpa only [equal] using (RuntimeExprTyped.enumCompare (equal := true) (l.typing.cast lk) (r.typing.cast (rk.trans (congrArg RuntimeType.nominal same))))⟩
            else if different : comparison = .ne then
              return ⟨.scalar .boolean,by
                simpa only [different] using (RuntimeExprTyped.enumCompare (equal := false) (l.typing.cast lk) (r.typing.cast (rk.trans (congrArg RuntimeType.nominal same))))⟩
            else none
          else none
        | _, _ => none
      | .add =>
        if lw : l.kind = .scalar .word then
          if rw : r.kind = .scalar .word then
            return ⟨.scalar .word,.wordBinary .add (l.typing.cast lw) (r.typing.cast rw)⟩
          else none
        else none
      | .subtract =>
        if lw : l.kind = .scalar .word then
          if rw : r.kind = .scalar .word then
            return ⟨.scalar .word,.wordBinary .subtract (l.typing.cast lw) (r.typing.cast rw)⟩
          else none
        else none
      | .bitAnd =>
        if lw : l.kind = .scalar .word then
          if rw : r.kind = .scalar .word then
            return ⟨.scalar .word,.wordBinary .bitAnd (l.typing.cast lw) (r.typing.cast rw)⟩
          else none
        else none
      | .bitOr =>
        if lw : l.kind = .scalar .word then
          if rw : r.kind = .scalar .word then
            return ⟨.scalar .word,.wordBinary .bitOr (l.typing.cast lw) (r.typing.cast rw)⟩
          else none
        else none

structure CheckedRuntimeExpression (context : RuntimeExprContext) (source : SourceExpr) where
  valid : RuntimeContextValid context
  inferred : InferredRuntimeExpression context source

def checkRuntimeExpression (context : RuntimeExprContext) (source : SourceExpr) :
    Option (CheckedRuntimeExpression context source) := do
  let valid ← checkRuntimeContext context
  let inferred ← inferRuntimeExpression context 4096 source
  return ⟨valid.property,inferred⟩

/-- Ordered source argument typing, without invoking or summarizing any callee. -/
inductive RuntimeArgumentsTyped (context : RuntimeExprContext) : List SourceExpr → List RuntimeType → Prop
  | nil : RuntimeArgumentsTyped context [] []
  | cons : RuntimeExprTyped context first kind → RuntimeArgumentsTyped context rest kinds →
      RuntimeArgumentsTyped context (first :: rest) (kind :: kinds)

end Aurora.SourceBinding
