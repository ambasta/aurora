import SourceBinding.FreeIdentity
import SourceBinding.LocalBodyCertificate
namespace Aurora.SourceBinding
open Aurora.Publication

/-- Same-table source identity plus a complete call-free body certificate. -/
structure LocalFreeBinding (t : Tables) (files : List SourceFile) (root module path : Name) (name : ByteArray) where
  identified : IdentifiedFree t files root module path name
  method : BodyMethod identified.selected.file.file.bytes identified.selected.function.function []
  core : LocalBodyCertificate t identified.id method

def bindLocalFree (t : Tables) (files : List SourceFile) (root module path : Name) (name : ByteArray) :
    Option (LocalFreeBinding t files root module path name) := do
  let identified ← identifyFree t files root module path name
  let method ← bodyMethod identified.selected.file.file.bytes identified.selected.function.function []
  let core ← checkLocalBody t identified.id method
  return ⟨identified,method,core⟩

structure FreeBinding (files : List SourceFile) (root module path : Name) (name : ByteArray) (bytes : ByteArray) where
  artifact : CheckedArtifact bytes
  checked : LocalFreeBinding (tables artifact.document.reversed.reverse) files root module path name

def bindFree (files : List SourceFile) (root module path : Name) (name : ByteArray) (bytes : ByteArray) :
    Option (FreeBinding files root module path name bytes) := do
  let artifact ← decodeArtifact {} bytes
  let checked ← bindLocalFree (tables artifact.document.reversed.reverse) files root module path name
  return ⟨artifact,checked⟩

theorem LocalFreeBinding.executes (checked : LocalFreeBinding t files root module path name)
    (base : Machine) (arguments : EntryArguments checked.core.bindings base.arguments) :
    ∃ result,
      EffectRuns (canonicalEffects t checked.identified.id)
        (preparedEntry base (parameterSlot checked.core.bindings) 0)
        (evalBody checked.method.body (entrySource base checked.core.bindings.length)).stores result ∧
      BodyResultRelated (parameterSlot checked.core.bindings) [] checked.core.stop
        (evalBody checked.method.body (entrySource base checked.core.bindings.length)).execution result ∧
      EffectTerminal result := checked.core.executes base arguments

end Aurora.SourceBinding
