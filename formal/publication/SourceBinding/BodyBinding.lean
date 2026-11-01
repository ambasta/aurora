import SourceBinding.LocalBodyCertificate
namespace Aurora.SourceBinding
open Aurora.Publication

/-- Same selected source member and metadata identity, actual typed entry, and
    complete canonical body coverage. No independently supplied field catalogue,
    source AST, callee summary or successful-assertion assumption is accepted. -/
structure BodyBinding (files : List SourceFile) (root module path : Name) (member : ByteArray) (bytes : ByteArray) where
  source : SelectedBody files root module path member
  ir : BoundIR files root module path member source.selected bytes
  core : LocalBodyCertificate (tables ir.publication.artifact.document.reversed.reverse) ir.id source.method

def BodyBinding.bindings (checked : BodyBinding files root module path member bytes) := checked.core.bindings
def BodyBinding.stop (checked : BodyBinding files root module path member bytes) := checked.core.stop
def BodyBinding.entry (checked : BodyBinding files root module path member bytes) := checked.core.entry
def BodyBinding.code (checked : BodyBinding files root module path member bytes) := checked.core.code
def BodyBinding.complete (checked : BodyBinding files root module path member bytes) := checked.core.complete

def bindBody (files : List SourceFile) (root module path : Name) (member : ByteArray) (bytes : ByteArray) :
    Option (BodyBinding files root module path member bytes) := do
  let source ← selectBody files root module path member
  let ir ← bindIR files root module path member source.selected bytes
  let core ← checkLocalBody (tables ir.publication.artifact.document.reversed.reverse) ir.id source.method
  return ⟨source,ir,core⟩

theorem BodyBinding.executes (checked : BodyBinding files root module path member bytes)
    (base : Machine) (arguments : EntryArguments checked.bindings base.arguments) :
    ∃ result,
      EffectRuns (canonicalEffects (tables checked.ir.publication.artifact.document.reversed.reverse) checked.ir.id)
        (preparedEntry base (parameterSlot checked.bindings) 0)
        (evalBody checked.source.method.body (entrySource base checked.bindings.length)).stores result ∧
      BodyResultRelated (parameterSlot checked.bindings) [] checked.stop
        (evalBody checked.source.method.body (entrySource base checked.bindings.length)).execution result ∧
      EffectTerminal result := checked.core.executes base arguments

theorem BodyBinding.terminal_correspondence (checked : BodyBinding files root module path member bytes)
    (base : Machine) (arguments : EntryArguments checked.bindings base.arguments)
    (run : EffectRuns (canonicalEffects (tables checked.ir.publication.artifact.document.reversed.reverse) checked.ir.id)
      (preparedEntry base (parameterSlot checked.bindings) 0) events result)
    (terminal : EffectTerminal result) :
    events = (evalBody checked.source.method.body (entrySource base checked.bindings.length)).stores ∧
    BodyResultRelated (parameterSlot checked.bindings) [] checked.stop
      (evalBody checked.source.method.body (entrySource base checked.bindings.length)).execution result := checked.core.terminal_correspondence base arguments run terminal

theorem BodyBinding.terminates (checked : BodyBinding files root module path member bytes)
    (base : Machine) (arguments : EntryArguments checked.bindings base.arguments) :
    ¬ EffectDiverges (canonicalEffects (tables checked.ir.publication.artifact.document.reversed.reverse) checked.ir.id)
      (preparedEntry base (parameterSlot checked.bindings) 0) := checked.core.terminates base arguments

theorem bind_body_sound (files : List SourceFile) (root module path : Name) (member : ByteArray) (bytes : ByteArray)
    (checked : BodyBinding files root module path member bytes) (_accepted : bindBody files root module path member bytes = some checked) :
    BodyCode (canonicalEffects (tables checked.ir.publication.artifact.document.reversed.reverse) checked.ir.id)
      (parameterSlot checked.bindings) checked.source.method.body
      checked.source.selected.selected.method.function.formals.length checked.stop ∧
    checked.stop = (functionCode (tables checked.ir.publication.artifact.document.reversed.reverse) checked.ir.id).size :=
  ⟨checked.code,checked.complete⟩

end Aurora.SourceBinding
