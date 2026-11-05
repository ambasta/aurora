import SourceBinding.RuntimeSourceTyping
import SourceBinding.MethodSyntax
import SourceBinding.ScopeProfile
namespace Aurora.SourceBinding
open Aurora.Publication

structure SourceLocal where
  name : ByteArray
  kind : RuntimeType
  mutable : Bool
  scope : Nat
  slot : Nat
  deriving BEq, DecidableEq

/-- External names are derived from declaredItems, not an unchecked resolver map. -/
def enumValueNames (members : List Declaration) (path : Name) : List Name :=
  members.flatMap fun member => match member with
  | .enumDecl name cases => cases.flatMap fun item => [[name,item],path ++ [name,item]]
  | _ => []
def localCallNames (members : List Declaration) (path : Name) : List Name :=
  members.flatMap fun member => match member with
  | .functionDecl f => [[f.name],path ++ [f.name]]
  | _ => []
def visibleNames (formals : List Formal) (locals : List SourceLocal) : List ByteArray :=
  formals.map (·.name) ++ locals.map (·.name)

def Unshadowed (formals : List Formal) (locals : List SourceLocal) (name : Name) : Prop :=
  ∀ first ∈ name.head?.toList, first ∉ visibleNames formals locals
instance (formals : List Formal) (locals : List SourceLocal) (name : Name) :
    Decidable (Unshadowed formals locals name) := by unfold Unshadowed; infer_instance

def sourceTypeHead : SourceType → Option ByteArray
  | .named name | .applied name _ => name.head?
  | .constant inner | .reference inner => sourceTypeHead inner

def TypeUnshadowed (formals : List Formal) (locals : List SourceLocal) (typ : SourceType) : Prop :=
  ∀ first ∈ (sourceTypeHead typ).toList, first ∉ visibleNames formals locals
instance (formals : List Formal) (locals : List SourceLocal) (typ : SourceType) :
    Decidable (TypeUnshadowed formals locals typ) := by unfold TypeUnshadowed; infer_instance

/-- Only lexical use identity. Expression types, operator legality and call
    evaluation are deliberately supplied by the later call-aware relation. -/
inductive ExpressionNames (members : List Declaration) (path : Name) (formals : List Formal)
    (locals : List SourceLocal) : SourceExpr → Prop
  | word : ExpressionNames members path formals locals (.word value)
  | boolean : ExpressionNames members path formals locals (.boolean value)
  | count12 : ExpressionNames members path formals locals .signed12
  | count : (value = 4 ∨ value = 32) → ExpressionNames members path formals locals (.signedCount value)
  | boundVariable : name ∈ visibleNames formals locals → ExpressionNames members path formals locals (.name [name])
  | nominal : name ∈ enumValueNames members path → Unshadowed formals locals name →
      ExpressionNames members path formals locals (.name name)
  | not : ExpressionNames members path formals locals expression →
      ExpressionNames members path formals locals (.not expression)
  | binary : ExpressionNames members path formals locals left → ExpressionNames members path formals locals right →
      ExpressionNames members path formals locals (.binary operator left right)
  | call : name ∈ localCallNames members path → Unshadowed formals locals name →
      (∀ argument ∈ arguments, ExpressionNames members path formals locals argument) →
      ExpressionNames members path formals locals (.call (.named name) arguments)

def certifyEach {α : Type} (property : α → Prop)
    (check : (item : α) → Option { _witness : Unit // property item }) :
    (items : List α) → Option { _witness : Unit // ∀ item ∈ items, property item }
  | [] => some ⟨(),by simp⟩
  | first :: rest => do
    let head ← check first
    let tail ← certifyEach property check rest
    return ⟨(),by
      intro item present
      rcases List.mem_cons.mp present with same | later
      · subst item; exact head.property
      · exact tail.property item later⟩

/-- Fuel bounds executable work; acceptance carries the independent relation. -/
def checkExpressionNames (members : List Declaration) (path : Name) (formals : List Formal)
    (locals : List SourceLocal) : (fuel : Nat) → (source : SourceExpr) →
    Option { _witness : Unit // ExpressionNames members path formals locals source }
  | 0, _ => none
  | fuel + 1, source => match source with
    | .word _ => some ⟨(),.word⟩
    | .boolean _ => some ⟨(),.boolean⟩
    | .signed12 => some ⟨(),.count12⟩
    | .signedCount value => if allowed : value = 4 ∨ value = 32 then some ⟨(),.count allowed⟩ else none
    | .name [name] =>
      if present : name ∈ visibleNames formals locals then some ⟨(),.boundVariable present⟩ else none
    | .name name =>
      if present : name ∈ enumValueNames members path then
        if clear : Unshadowed formals locals name then some ⟨(),.nominal present clear⟩ else none
      else none
    | .not inner => do
      let checked ← checkExpressionNames members path formals locals fuel inner
      return ⟨(),.not checked.property⟩
    | .binary _ left right => do
      let l ← checkExpressionNames members path formals locals fuel left
      let r ← checkExpressionNames members path formals locals fuel right
      return ⟨(),.binary l.property r.property⟩
    | .call (.receiver _ _) _ => none
    | .call (.named name) arguments => do
      if present : name ∈ localCallNames members path then
        if clear : Unshadowed formals locals name then
          let checked ← certifyEach (ExpressionNames members path formals locals)
            (checkExpressionNames members path formals locals fuel) arguments
          return ⟨(),.call present clear checked.property⟩
        else none
      else none

structure LocalContext where
  visible : List SourceLocal
  scope : Nat
  nextScope : Nat
  nextSlot : Nat

def declaredLocal (context : LocalContext) (name : ByteArray) (kind : RuntimeType) (mutable : Bool) : SourceLocal :=
  ⟨name,kind,mutable,context.scope,8 * (context.nextSlot + 1)⟩
def addLocal (context : LocalContext) (binding : SourceLocal) : LocalContext :=
  { context with visible := binding :: context.visible, nextSlot := context.nextSlot + 1 }
def enterLocalScope (context : LocalContext) : LocalContext :=
  { context with scope := context.nextScope, nextScope := context.nextScope + 1 }
def leaveLocalScope (before after : LocalContext) : LocalContext :=
  { after with visible := before.visible, scope := before.scope }

mutual
  inductive ScopedStatementWith (profile : ScopeProfile) (uses : LocalContext → SourceExpr → Prop)
      (writes : LocalContext → ByteArray → Prop)
      (members : List Declaration) (module path : Name) (formals : List Formal) :
      LocalContext → SourceStatement → LocalContext → List SourceLocal → Prop
    | declare {declaration : Formal} : LocalSourceType members module path declaration.type kind mutable → NameAllowed declaration.name →
        declaration.name ∉ visibleNames formals before.visible →
        TypeUnshadowed formals before.visible declaration.type →
        uses before value →
        ScopedStatementWith profile uses writes members module path formals before (.localDecl declaration value)
          (addLocal before (declaredLocal before declaration.name kind mutable))
          [declaredLocal before declaration.name kind mutable]
    | assign : binding ∈ before.visible → binding.name = name → binding.mutable = true →
        uses before value →
        ScopedStatementWith profile uses writes members module path formals before (.assign name value) before []
    | receiverAssign : profile = .receiverEffects → writes before name → uses before value →
        ScopedStatementWith profile uses writes members module path formals before (.assign name value) before []
    | returnValue : uses before value →
        ScopedStatementWith profile uses writes members module path formals before (.returnValue value) before []
    | call {callee : Callee} : uses before (.call callee arguments) →
        ScopedStatementWith profile uses writes members module path formals before (.call callee arguments) before []
    | branch : uses before condition →
        ScopedStatementsWith profile uses writes members module path formals (enterLocalScope before) body child declaredItems →
        ScopedStatementWith profile uses writes members module path formals before (.ifThen condition body)
          (leaveLocalScope before child) declaredItems
    | branchElse : profile = .receiverEffects → uses before condition →
        ScopedStatementsWith profile uses writes members module path formals
          (enterLocalScope before) yes yesAfter yesItems →
        ScopedStatementsWith profile uses writes members module path formals
          (enterLocalScope (leaveLocalScope before yesAfter)) no noAfter noItems →
        ScopedStatementWith profile uses writes members module path formals before (.ifElse condition yes no)
          (leaveLocalScope before noAfter) (yesItems ++ noItems)
  inductive ScopedStatementsWith (profile : ScopeProfile) (uses : LocalContext → SourceExpr → Prop)
      (writes : LocalContext → ByteArray → Prop)
      (members : List Declaration) (module path : Name) (formals : List Formal) :
      LocalContext → List SourceStatement → LocalContext → List SourceLocal → Prop
    | nil : ScopedStatementsWith profile uses writes members module path formals before [] before []
    | cons : ScopedStatementWith profile uses writes members module path formals before first middle declaredItems →
        ScopedStatementsWith profile uses writes members module path formals middle rest after remaining →
        ScopedStatementsWith profile uses writes members module path formals before (first :: rest) after (declaredItems ++ remaining)
end

-- Old aliases FIX both supported forms and name/write predicates, even in dead branches.
abbrev ScopedStatement (members : List Declaration) (module path : Name) (formals : List Formal) :=
  ScopedStatementWith .legacy
    (fun cursor raw => ExpressionNames members path formals cursor.visible raw)
    (fun _ _ => False) members module path formals
abbrev ScopedStatements (members : List Declaration) (module path : Name) (formals : List Formal) :=
  ScopedStatementsWith .legacy
    (fun cursor raw => ExpressionNames members path formals cursor.visible raw)
    (fun _ _ => False) members module path formals

structure ScopedResultWith (profile : ScopeProfile) (uses : LocalContext → SourceExpr → Prop) (writes : LocalContext → ByteArray → Prop) (members : List Declaration) (module path : Name) (formals : List Formal)
    (before : LocalContext) (statements : List SourceStatement) where
  after : LocalContext
  declaredItems : List SourceLocal
  grammar : ScopedStatementsWith profile uses writes members module path formals before statements after declaredItems
structure ScopedOneWith (profile : ScopeProfile) (uses : LocalContext → SourceExpr → Prop) (writes : LocalContext → ByteArray → Prop) (members : List Declaration) (module path : Name) (formals : List Formal)
    (before : LocalContext) (statement : SourceStatement) where
  after : LocalContext
  declaredItems : List SourceLocal
  grammar : ScopedStatementWith profile uses writes members module path formals before statement after declaredItems

mutual
  def scopeStatementsWith (profile : ScopeProfile) (uses : LocalContext → SourceExpr → Prop) (writes : LocalContext → ByteArray → Prop)
      (checkUses : (cursor : LocalContext) → (raw : SourceExpr) → Option { _witness : Unit // uses cursor raw })
      (checkWrites : (cursor : LocalContext) → (name : ByteArray) → Option { _witness : Unit // writes cursor name }) (members : List Declaration) (module path : Name) (formals : List Formal) :
      (fuel : Nat) → (before : LocalContext) → (statements : List SourceStatement) →
      Option (ScopedResultWith profile uses writes members module path formals before statements)
    | 0, _, _ => none
    | _ + 1, before, [] => some ⟨before,[],.nil⟩
    | fuel + 1, before, first :: rest => do
      let head ← scopeStatementWith profile uses writes checkUses checkWrites members module path formals fuel before first
      let tail ← scopeStatementsWith profile uses writes checkUses checkWrites members module path formals fuel head.after rest
      return ⟨tail.after,head.declaredItems ++ tail.declaredItems,.cons head.grammar tail.grammar⟩
  def scopeStatementWith (profile : ScopeProfile) (uses : LocalContext → SourceExpr → Prop) (writes : LocalContext → ByteArray → Prop)
      (checkUses : (cursor : LocalContext) → (raw : SourceExpr) → Option { _witness : Unit // uses cursor raw })
      (checkWrites : (cursor : LocalContext) → (name : ByteArray) → Option { _witness : Unit // writes cursor name }) (members : List Declaration) (module path : Name) (formals : List Formal) :
      (fuel : Nat) → (before : LocalContext) → (statement : SourceStatement) →
      Option (ScopedOneWith profile uses writes members module path formals before statement)
    | 0, _, _ => none
    | fuel + 1, before, statement => match statement with
      | .localDecl declaration value => do
        let typ ← resolveLocalType members module path declaration.type
        if allowed : NameAllowed declaration.name then
          if fresh : declaration.name ∉ visibleNames formals before.visible then
            if typeClear : TypeUnshadowed formals before.visible declaration.type then
              let checked ← checkUses before value
              let binding := declaredLocal before declaration.name typ.kind typ.mutable
              return ⟨addLocal before binding,[binding],.declare typ.typing allowed fresh typeClear checked.property⟩
            else none
          else none
        else none
      | .assign name value =>
        match found : before.visible.find? (fun item => item.name == name) with
        | none => do
          if enabled : profile = .receiverEffects then
            let write ← checkWrites before name
            let checked ← checkUses before value
            return ⟨before,[],.receiverAssign enabled write.property checked.property⟩
          else none
        | some binding => do
          if named : binding.name = name then
            if mutable : binding.mutable = true then
              let checked ← checkUses before value
              return ⟨before,[],.assign (List.mem_of_find?_eq_some found) named mutable checked.property⟩
            else none
          else none
      | .returnValue value => do
        let checked ← checkUses before value
        return ⟨before,[],.returnValue checked.property⟩
      | .call callee arguments => do
        let checked ← checkUses before (.call callee arguments)
        return ⟨before,[],.call checked.property⟩
      | .ifElse condition yes no => do
        if enabled : profile = .receiverEffects then
          let checked ← checkUses before condition
          let yesBody ← scopeStatementsWith profile uses writes checkUses checkWrites members module path formals fuel
            (enterLocalScope before) yes
          let noBody ← scopeStatementsWith profile uses writes checkUses checkWrites members module path formals fuel
            (enterLocalScope (leaveLocalScope before yesBody.after)) no
          return ⟨leaveLocalScope before noBody.after,yesBody.declaredItems ++ noBody.declaredItems,
            .branchElse enabled checked.property yesBody.grammar noBody.grammar⟩
        else none
      | .ifThen condition body => do
        let checked ← checkUses before condition
        let child ← scopeStatementsWith profile uses writes checkUses checkWrites members module path formals fuel (enterLocalScope before) body
        return ⟨leaveLocalScope before child.after,child.declaredItems,.branch checked.property child.grammar⟩
end

abbrev ScopedResult (members : List Declaration) (module path : Name) (formals : List Formal) :=
  ScopedResultWith .legacy (fun cursor raw => ExpressionNames members path formals cursor.visible raw)
    (fun _ _ => False) members module path formals
abbrev ScopedOne (members : List Declaration) (module path : Name) (formals : List Formal) :=
  ScopedOneWith .legacy (fun cursor raw => ExpressionNames members path formals cursor.visible raw)
    (fun _ _ => False) members module path formals

def scopeStatements (members : List Declaration) (module path : Name) (formals : List Formal) :=
  scopeStatementsWith .legacy (fun cursor raw => ExpressionNames members path formals cursor.visible raw)
    (fun _ _ => False) (fun cursor raw => checkExpressionNames members path formals cursor.visible 4096 raw)
    (fun _ _ => none) members module path formals

def scopeStatement (members : List Declaration) (module path : Name) (formals : List Formal) :=
  scopeStatementWith .legacy (fun cursor raw => ExpressionNames members path formals cursor.visible raw)
    (fun _ _ => False) (fun cursor raw => checkExpressionNames members path formals cursor.visible 4096 raw)
    (fun _ _ => none) members module path formals

/-- Exact binding slot type/offset; mutability comes only from source typing. -/
def SourceLocalSlot (t : Tables) (id : Int) (binding : SourceLocal) : Prop :=
  ∃ slot ∈ (frameSlots t (atRow t.callables id)).toList,
    slot.integer 1 = 10 ∧ slot.integer 2 = Int.ofNat binding.slot ∧
    RuntimeTypeIdentity t (slot.integer 3) binding.kind ∧
    slot.integer 4 = 0 ∧ slot.integer 5 = 0 ∧
    slot.integer 2 ≤ (atRow t.callables id).integer 13
instance (t : Tables) (id : Int) (binding : SourceLocal) : Decidable (SourceLocalSlot t id binding) := by
  unfold SourceLocalSlot; infer_instance

/-- Full syntax and scoping, not expression typing or execution. Slots cover all
    declaredItems including unreachable suffixes and branch-binding declaredItems. -/
structure ScopedMethod (input : ByteArray) (function : Function) (members : List Declaration)
    (module path : Name) where
  parsed : ParsedMethod input function
  formals : FormalNames function.formals
  typeNames : ∀ formal ∈ function.formals, TypeUnshadowed function.formals [] formal.type
  lexical : ScopedResult members module path function.formals ⟨[],0,1,function.formals.length⟩ parsed.statements

def scopeMethod (input : ByteArray) (function : Function) (members : List Declaration) (module path : Name) :
    Option (ScopedMethod input function members module path) := do
  let parsed ← methodSyntax input function
  if formals : FormalNames function.formals then
    if typeNames : ∀ formal ∈ function.formals, TypeUnshadowed function.formals [] formal.type then
      let lexical ← scopeStatements members module path function.formals 4096
        ⟨[],0,1,function.formals.length⟩ parsed.statements
      return ⟨parsed,formals,typeNames,lexical⟩
    else none
  else none

end Aurora.SourceBinding
