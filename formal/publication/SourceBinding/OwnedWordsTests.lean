import SourceBinding.OwnedWordsFacts
import SourceBinding.ResourceStatementFacts
namespace Aurora.SourceBinding.OwnedWordsTests

/- Tiny primitive/model controls only: these do not claim source-method binding,
   complete release execution, native admission, or physical bank authority. -/
private def bank : OwnedWordsBank := ⟨3,fun index => index.val + 10⟩
private def changed : OwnedWordsBank := bank.write ⟨1,by decide⟩ 25
example : changed.size = 3 := rfl
example : changed.cells ⟨1,by decide⟩ = 25 := by decide
example : changed.cells ⟨0,by decide⟩ = 10 := by decide
example : changed.cells ⟨2,by decide⟩ = 12 := by decide

private def key (method : String) (parameters : List GuardType) (result : GuardType)
    (mode : RuntimeResourceMode) : RuntimeSourceResource :=
  ⟨⟨⟨["example".toUTF8],["Owner".toUTF8]⟩,[]⟩,"words".toUTF8,
    ["builtin".toUTF8,"OwnedWords".toUTF8],method.toUTF8,parameters,result,mode⟩
private def interface : OwnedWordsInterface :=
  ⟨key "size" [] .word .readonly,key "at" [.word] .word .readonly,
    key "set" [.word,.word] .boolean .mutable,0,true⟩
private def before : SourceShared (OwnedWordsWorld Nat) :=
  ⟨fun _ => none,⟨fun _ => some bank,37⟩⟩
private def after : SourceShared (OwnedWordsWorld Nat) :=
  ⟨fun _ => some (.word 99),⟨fun _ => some changed,41⟩⟩
private theorem valid : bank.Valid := by
  refine ⟨by decide,by decide,?_⟩
  intro index
  have bound := index.isLt
  change index.val + 10 < 18446744073709551616
  change index.val < 3 at bound
  omega

example : OwnedWordsResponse interface ⟨interface.setMethod,[.word 1,.word 25],before⟩
    (.returned (some (.boolean true))) {before with world := before.world.write 0 changed} :=
  .set rfl valid rfl (by decide) (by decide)
example : (before.world.write 0 changed).banks 1 = some bank := rfl
example : (before.world.write 0 changed).other = 37 := rfl

private def state : SourceEffectState (OwnedWordsWorld Nat) :=
  ⟨formalSourceLocals [] (fun _ => none),before⟩
private def adversarial : SourceExternalRelation (OwnedWordsWorld Nat) Unit := fun _ _ _ => True

-- False and absent responses may already have changed receiver AND bank world.
example : SourceResourceAssert adversarial interface.setMethod [.word 1,.word 25] state
    (.stopped (.localFault .assertion) {state with shared := after})
    [.externalInvoke ⟨interface.setMethod,[.word 1,.word 25],before⟩,
      .externalReturn (some (.boolean false)) after] :=
  SourceResourceAssert.false_retains_poststate True.intro
example : SourceResourceAssert adversarial interface.setMethod [.word 1,.word 25] state
    (.stopped (.localFault (.scalar .type)) {state with shared := after})
    [.externalInvoke ⟨interface.setMethod,[.word 1,.word 25],before⟩,
      .externalReturn none after] :=
  SourceResourceAssert.missing_retains_poststate True.intro

-- A finite pending observation does not assert unavailability of a response.
example :
    SourceResourceStep (OwnedWordsResponse interface) ⟨interface.sizeMethod,[],before⟩
      (.value (some (.word 3))) before
      [.externalInvoke ⟨interface.sizeMethod,[],before⟩,.externalReturn (some (.word 3)) before] ∧
    SourceResourceStep (OwnedWordsResponse interface) ⟨interface.sizeMethod,[],before⟩
      (.stopped (.waiting ⟨interface.sizeMethod,[],before⟩)) before
      [.externalInvoke ⟨interface.sizeMethod,[],before⟩] :=
  ⟨.returned (.size rfl valid),.pending⟩

end Aurora.SourceBinding.OwnedWordsTests
