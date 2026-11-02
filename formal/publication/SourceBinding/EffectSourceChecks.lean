import SourceBinding.EffectCallableBinding
import SourceBinding.DeclarationEquality
namespace Aurora.SourceBinding

deriving instance DecidableEq for RuntimeReceiverScope
deriving instance DecidableEq for RuntimeReceiverContext
deriving instance DecidableEq for RuntimeSourceResource

instance : Decidable (ReceiverAllowsResource receiver mode) := by
  unfold ReceiverAllowsResource; infer_instance
instance : Decidable (EffectContext.UnshadowedName context name) := by
  unfold EffectContext.UnshadowedName; infer_instance

structure CheckedEffectField (context : EffectContext) (name : ByteArray) where
  field : EffectField
  binding : EffectFieldResolved context name field

def checkEffectField (context : EffectContext) (name : ByteArray) : Option (CheckedEffectField context name) := do
  if enabled : context.profile = .receiverEffects then
    let receiver ← context.receiver
    if current : context.receiver = some receiver then
      if members : context.lexical.members = receiver.scope.members then
        let found ← fieldAt receiver.scope.members name
        let kind ← sourceScalarKind found.field.type
        if scalar : found.field.type = guardSourceType kind then
          if clear : context.UnshadowedName name then
            return ⟨⟨name,kind,found.ordinal⟩,⟨enabled,receiver,current,members,found,rfl,rfl,scalar,clear⟩⟩
          else none
        else none
      else none
    else none
  else none

def checkEffectWrite (context : EffectContext) (name : ByteArray) :
    Option { field : EffectField // Nonempty (EffectFieldWritable context name field) } := do
  let checked ← checkEffectField context name
  if mutable : checked.binding.receiver.mode = .ordinary then
    return ⟨checked.field,⟨⟨checked.binding,mutable⟩⟩⟩
  else none

structure CheckedEffectEnum (context : EffectContext) (name : Name) where
  identity : NominalIdentity
  ordinal : Nat
  binding : EffectEnumValue context name identity ordinal

def checkEffectEnum (context : EffectContext) (name : Name) : Option (CheckedEffectEnum context name) :=
  match resolveRuntimeEnum context.lexical name with
  | some localValue => some ⟨localValue.identity,localValue.ordinal,.localValue localValue.grammar⟩
  | none => do
    if enabled : context.profile = .receiverEffects then
      if clear : ∀ first ∈ name.head?.toList, first ∉ context.lexical.members.filterMap declarationName then
        let enclosing := context.enclosing.attach.findSome? fun item => do
          let value ← resolveRuntimeEnum ⟨item.val.members,item.val.module,item.val.path,context.lexical.formals,context.lexical.visible⟩ name
          return (⟨value.identity,value.ordinal,.enclosing enabled item.property value.grammar clear⟩ : CheckedEffectEnum context name)
        match enclosing with
        | some value => some value
        | none =>
          if outerClear : ∀ scope ∈ context.enclosing, ∀ first ∈ name.head?.toList,
              first ∉ scope.members.filterMap declarationName then
            context.imported.attach.findSome? fun item => do
              let value ← resolveRuntimeEnum ⟨item.val.members,item.val.module,item.val.path,context.lexical.formals,context.lexical.visible⟩ name
              return ⟨value.identity,value.ordinal,.imported enabled item.property value.grammar clear outerClear⟩
          else none
      else none
    else none

def checkEffectNamedCall (context : EffectContext) (name : Name) :
    Option { _witness : Unit // EffectNamedCall context name } := do
  if localName : name ∈ localCallNames context.lexical.members context.lexical.path then
    if clear : Unshadowed context.lexical.formals context.lexical.visible name then
      return ⟨(),.localCall localName clear⟩
    else none
  else
    let bare ← name[0]?
    if singleton : name = [bare] then
      if clear : context.UnshadowedName bare then
        if localClear : bare ∉ context.lexical.members.filterMap declarationName then
          let enclosing := context.enclosing.attach.findSome? fun item => do
            let found ← findFunction item.val.members bare
            if ordinary : found.function.mode = .ordinary then
              return (⟨(),.enclosing item.property found.present ordinary
                (singleton.trans (congrArg (fun value => [value]) found.named.symm))
                (by simpa only [found.named] using clear)
                (by simpa only [found.named] using localClear)⟩ : { _witness : Unit // EffectNamedCall context name })
            else none
          match enclosing with
          | some value => some value
          | none =>
            if outerClear : ∀ scope ∈ context.enclosing, bare ∉ scope.members.filterMap declarationName then
              context.imported.attach.findSome? fun item => do
                let found ← findFunction item.val.members bare
                if ordinary : found.function.mode = .ordinary then
                  return ⟨(),.imported item.property found.present ordinary
                    (singleton.trans (congrArg (fun value => [value]) found.named.symm))
                    (by simpa only [found.named] using clear)
                    (by simpa only [found.named] using localClear)
                    (by simpa only [found.named] using outerClear)⟩
                else none
            else none
        else none
      else none
    else none

structure CheckedEffectResourceUse (context : EffectContext) (field method : ByteArray) where
  resource : RuntimeSourceResource
  fieldName : resource.field = field
  methodName : resource.method = method
  binding : EffectResourceResolved context resource

def checkEffectResourceUse (context : EffectContext) (field method : ByteArray) :
    Option (CheckedEffectResourceUse context field method) :=
  context.resources.attach.findSome? fun item => do
    if fieldName : item.val.field = field then
      if methodName : item.val.method = method then
        let receiver ← context.receiver
        if current : context.receiver = some receiver then
          if sameScope : item.val.receiver = receiver.scope then
            if permitted : ReceiverAllowsResource receiver item.val.mode then
              let found ← fieldAt item.val.receiver.members item.val.field
              if typ : found.field.type = .named item.val.sourceType then
                if clear : item.val.field ∉ context.lexical.formals.map (·.name) ∧
                    item.val.field ∉ context.lexical.visible.map (·.name) then
                  return ⟨item.val,fieldName,methodName,
                    ⟨item.property,receiver,current,sameScope,permitted,⟨found,typ⟩,clear⟩⟩
                else none
              else none
            else none
          else none
        else none
      else none
    else none

mutual
  def checkEffectPureNames (context : EffectContext) : (fuel : Nat) → (raw : SourceExpr) →
      Option { _witness : Unit // EffectPureNames context raw }
    | 0,_ => none
    | fuel + 1,raw => match raw with
      | .word _ => some ⟨(),.word⟩
      | .boolean _ => some ⟨(),.boolean⟩
      | .signed12 => some ⟨(),.count12⟩
      | .signedCount value => if allowed : value = 4 ∨ value = 32 then some ⟨(),.count allowed⟩ else none
      | .name name =>
        match name with
        | [single] =>
          if known : single ∈ visibleNames context.lexical.formals context.lexical.visible then
            some ⟨(),.variable known⟩
          else do
            let field ← checkEffectField context single
            return ⟨(),.field field.binding⟩
        | other => do
          let value ← checkEffectEnum context other
          return ⟨(),.nominal value.binding⟩
      | .not inner => do
        let checked ← checkEffectPureNames context fuel inner
        return ⟨(),.not checked.property⟩
      | .binary _ left right => do
        let first ← checkEffectPureNames context fuel left
        let second ← checkEffectPureNames context fuel right
        return ⟨(),.binary first.property second.property⟩
      | .call (.named name) arguments => do
        let called ← checkEffectNamedCall context name
        let arguments ← checkEffectPureArguments context fuel arguments
        return ⟨(),.call called.property arguments.property⟩
      | .call (.receiver _ _) _ => none
  def checkEffectPureArguments (context : EffectContext) : (fuel : Nat) → (raws : List SourceExpr) →
      Option { _witness : Unit // ∀ raw ∈ raws, EffectPureNames context raw }
    | 0,_ => none
    | _ + 1,[] => some ⟨(),by intro raw member; cases member⟩
    | fuel + 1,head :: tail => do
      let first ← checkEffectPureNames context fuel head
      let rest ← checkEffectPureArguments context fuel tail
      return ⟨(),by intro raw member; rcases List.mem_cons.mp member with rfl | member
                    · exact first.property
                    · exact rest.property raw member⟩
end

def checkEffectStatementNames (context : EffectContext) (raw : SourceExpr) :
    Option { _witness : Unit // EffectStatementNames context raw } :=
  match equation : raw with
  | .call (.receiver field method) arguments => do
    let resource ← checkEffectResourceUse context field method
    let args ← checkEffectPureArguments context 4096 arguments
    return ⟨(),by simpa only [resource.fieldName,resource.methodName] using
      (EffectStatementNames.resource (arguments := arguments) resource.binding args.property)⟩
  | .call (.named [a,b]) [.call (.receiver field method) arguments] =>
    if require : a = "builtin".toUTF8 ∧ b = "require".toUTF8 then do
      let resource ← checkEffectResourceUse context field method
      let args ← checkEffectPureArguments context 4096 arguments
      return ⟨(),by rcases require with ⟨rfl,rfl⟩
                    simpa only [resource.fieldName,resource.methodName] using
                      (EffectStatementNames.requireResource (arguments := arguments) resource.binding args.property)⟩
    else do
      let pure ← checkEffectPureNames context 4096 raw
      return ⟨(),by simpa only [equation] using EffectStatementNames.pure pure.property⟩
  | _ => do
    let pure ← checkEffectPureNames context 4096 raw
    return ⟨(),by simpa only [equation] using EffectStatementNames.pure pure.property⟩

def checkEffectUses (context : EffectContext) (cursor : LocalContext) (raw : SourceExpr) :
    Option { _witness : Unit // context.uses cursor raw } :=
  match h : context.profile with
  | .legacy => do
    let checked ← checkExpressionNames context.lexical.members context.lexical.path context.lexical.formals cursor.visible 4096 raw
    return ⟨(),by simpa only [EffectContext.uses,h] using checked.property⟩
  | .receiverEffects => do
    let checked ← checkEffectStatementNames (context.atCursor cursor) raw
    return ⟨(),by simpa only [EffectContext.uses,h] using checked.property⟩

def checkEffectWrites (context : EffectContext) (cursor : LocalContext) (name : ByteArray) :
    Option { _witness : Unit // context.writes cursor name } := do
  if enabled : context.profile = .receiverEffects then
    let checked ← checkEffectWrite (context.atCursor cursor) name
    return ⟨(),by simp only [EffectContext.writes,enabled]; exact ⟨checked.val,checked.property⟩⟩
  else none

end Aurora.SourceBinding
