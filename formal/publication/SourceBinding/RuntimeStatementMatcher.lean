import SourceBinding.RuntimeStatementCode
namespace Aurora.SourceBinding

deriving instance DecidableEq for LocalContext

structure ParsedRuntimeStatement (program : CallProgram) (caller : Int)
    (leaves : List (RuntimeCallable t files root module path))
    (members : List Declaration) (formals : List Formal) (result : RuntimeType)
    (before : LocalContext) (raw : SourceStatement) (start : Nat) where
  after : LocalContext
  declaredItems : List SourceLocal
  stop : Nat
  scopeProof : ScopedStatement members module path formals before raw after declaredItems
  grammar : RuntimeStatementCode program caller leaves members formals result before raw after declaredItems start stop

structure ParsedRuntimeStatements (program : CallProgram) (caller : Int)
    (leaves : List (RuntimeCallable t files root module path))
    (members : List Declaration) (formals : List Formal) (result : RuntimeType)
    (before : LocalContext) (raw : List SourceStatement) (start : Nat) where
  after : LocalContext
  declaredItems : List SourceLocal
  stop : Nat
  scopeProof : ScopedStatements members module path formals before raw after declaredItems
  grammar : RuntimeStatementsCode program caller leaves members formals result before raw after declaredItems start stop

/-- Rechecking exact scopeProof cursor endpoints avoids treating a computed local
    table as an unchecked typing oracle. -/
def exactRuntimeScope (members : List Declaration) (module path : Name) (formals : List Formal)
    (before : LocalContext) (raw : SourceStatement) (after : LocalContext) (declaredItems : List SourceLocal) :
    Option { _witness : Unit // ScopedStatement members module path formals before raw after declaredItems } := do
  let checked ← scopeStatement members module path formals 4096 before raw
  if same : checked.after = after then
    if items : checked.declaredItems = declaredItems then
      return ⟨(),same ▸ items ▸ checked.grammar⟩
    else none
  else none

structure CheckedRuntimeLabels (program : CallProgram) (caller : Int) (start : Nat) where
  stop : Nat
  grammar : RuntimeLabelRun program caller start stop

def checkRuntimeLabels (program : CallProgram) (caller : Int) :
    Nat → (start : Nat) → CheckedRuntimeLabels program caller start
  | 0, start => ⟨start,.nil⟩
  | fuel + 1, start =>
    if label : localProgram program caller start = some (.pure .label) then
      let rest := checkRuntimeLabels program caller fuel (start + 1)
      ⟨rest.stop,.cons label rest.grammar⟩
    else ⟨start,.nil⟩

mutual
def checkRuntimeStatements (program : CallProgram) (caller : Int)
    (leaves : List (RuntimeCallable t files root module path))
    (members : List Declaration) (formals : List Formal) (result : RuntimeType) :
    Nat → (before : LocalContext) → (raw : List SourceStatement) → (start : Nat) →
    Option (ParsedRuntimeStatements program caller leaves members formals result before raw start)
  | 0, _, _, _ => none
  | _ + 1, before, [], start => some ⟨before,[],start,.nil,.nil⟩
  | fuel + 1, before, first :: rest, start => do
    let head ← checkRuntimeStatement program caller leaves members formals result fuel before first start
    let tail ← checkRuntimeStatements program caller leaves members formals result fuel head.after rest head.stop
    return ⟨tail.after,head.declaredItems ++ tail.declaredItems,tail.stop,
      .cons head.scopeProof tail.scopeProof,.cons head.grammar tail.grammar⟩

def checkRuntimeStatement (program : CallProgram) (caller : Int)
    (leaves : List (RuntimeCallable t files root module path))
    (members : List Declaration) (formals : List Formal) (result : RuntimeType) :
    Nat → (before : LocalContext) → (raw : SourceStatement) → (start : Nat) →
    Option (ParsedRuntimeStatement program caller leaves members formals result before raw start)
  | 0, _, _, _ => none
  | fuel + 1, before, raw, start => do
    let context := runtimeStatementContext members module path formals before
    let valid ← checkRuntimeContext context
    match raw with
    | .localDecl declaration value => do
      let typ ← resolveLocalType members module path declaration.type
      let binding := declaredLocal before declaration.name typ.kind typ.mutable
      let scopeProof ← exactRuntimeScope members module path formals before (.localDecl declaration value) (addLocal before binding) [binding]
      let expression ← checkRuntimeCallExpressionCode program caller leaves context 4096 value start
      if kind : expression.kind = typ.kind then
        if store : localProgram program caller expression.stop = some (.localStore typ.kind binding.slot) then
          return ⟨addLocal before binding,[binding],expression.stop + 1,scopeProof.property,
            .declare scopeProof.property valid.property (expression.grammar.cast kind) store⟩
        else none
      else none
    | .assign name value => do
      match found : before.visible.find? (fun binding => binding.name == name) with
      | none => none
      | some binding =>
        if named : binding.name = name then
          if mutable : binding.mutable = true then
            let scopeProof ← exactRuntimeScope members module path formals before (.assign name value) before []
            let expression ← checkRuntimeCallExpressionCode program caller leaves context 4096 value start
            if kind : expression.kind = binding.kind then
              if store : localProgram program caller expression.stop = some (.localStore binding.kind binding.slot) then
                return ⟨before,[],expression.stop + 1,scopeProof.property,
                  .assign scopeProof.property (List.mem_of_find?_eq_some found) named mutable valid.property
                    (expression.grammar.cast kind) store⟩
              else none
            else none
          else none
        else none
    | .returnValue value => do
      let scopeProof ← exactRuntimeScope members module path formals before (.returnValue value) before []
      let expression ← checkRuntimeCallExpressionCode program caller leaves context 4096 value start
      if kind : expression.kind = result then
        if returned : localProgram program caller expression.stop = some (.pure .ret) then
          return ⟨before,[],expression.stop + 1,scopeProof.property,
            .returned scopeProof.property valid.property (expression.grammar.cast kind) returned⟩
        else none
      else none
    | .ifThen condition body => do
      let expression ← checkRuntimeCallExpressionCode program caller leaves context 4096 condition start
      if boolean : expression.kind = .scalar .boolean then
        let child ← checkRuntimeStatements program caller leaves members formals result fuel
          (enterLocalScope before) body (expression.stop + 1)
        let after := leaveLocalScope before child.after
        let scopeProof ← exactRuntimeScope members module path formals before (.ifThen condition body) after child.declaredItems
        if linear : localProgram program caller expression.stop = some (.pure (.branchFalse child.stop)) then
          let labels := checkRuntimeLabels program caller 4096 child.stop
          if nonempty : child.stop < labels.stop then
            return ⟨after,child.declaredItems,labels.stop,scopeProof.property,
              .branchLinear scopeProof.property valid.property (expression.grammar.cast boolean)
                linear child.grammar nonempty labels.grammar⟩
          else none
        else
          if joined : localProgram program caller expression.stop = some (.pure (.branchFalse (child.stop + 1))) then
            match operation : localProgram program caller child.stop with
            | some (.pure (.jump joinPC)) =>
              let labels := checkRuntimeLabels program caller 4096 (child.stop + 1)
              if lower : child.stop + 1 ≤ joinPC then
                if upper : joinPC < labels.stop then
                  return ⟨after,child.declaredItems,labels.stop,scopeProof.property,
                    .branchJoined scopeProof.property valid.property (expression.grammar.cast boolean)
                      joined child.grammar operation lower upper labels.grammar⟩
                else none
              else none
            | _ => none
          else none
      else none
    | .call _ _ => none
end

def checkRuntimeNoFallthrough : (raw : List SourceStatement) →
    Option { _witness : Unit // RuntimeNoFallthrough raw }
  | [] => none
  | .returnValue _ :: _ => some ⟨(),.returned⟩
  | _ :: rest => do
    let tail ← checkRuntimeNoFallthrough rest
    return ⟨(),.later tail.property⟩

end Aurora.SourceBinding
