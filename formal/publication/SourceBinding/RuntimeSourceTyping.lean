import SourceBinding.EnumBinding
namespace Aurora.SourceBinding
open Aurora.Publication

/-- Bounded lexical resolution in the actual selected namespace. No imports are
    searched implicitly and no qualified nominal identity is reduced to u64. -/
inductive RuntimeSourceType (members : List Declaration) (module path : Name) : SourceType → RuntimeType → Prop
  | word : RuntimeSourceType members module path (.named ["u64".toUTF8]) (.scalar .word)
  | boolean : RuntimeSourceType members module path (.named ["bool".toUTF8]) (.scalar .boolean)
  | nominal : Declaration.enumDecl name cases ∈ members → EnumSourceName path name source →
      RuntimeSourceType members module path source (.nominal ⟨enumSymbol module path name,cases.length⟩)

structure ResolvedRuntimeType (members : List Declaration) (module path : Name) (source : SourceType) where
  kind : RuntimeType
  typing : RuntimeSourceType members module path source kind

def resolveRuntimeType (members : List Declaration) (module path : Name) (source : SourceType) :
    Option (ResolvedRuntimeType members module path source) := do
  if word : source = .named ["u64".toUTF8] then return ⟨.scalar .word,word ▸ .word⟩
  else if boolean : source = .named ["bool".toUTF8] then return ⟨.scalar .boolean,boolean ▸ .boolean⟩
  else
    let .named names := source | none
    let name ← names.getLast?
    let found ← findEnum members name
    if named : EnumSourceName path name (.named names) then
      return ⟨.nominal ⟨enumSymbol module path name,found.cases.length⟩,.nominal found.present named⟩
    else none

/-- A local's const qualifier is interpreted only in the two admitted outer
    forms. References, nested const, and implicit inference remain unsupported. -/
inductive LocalSourceType (members : List Declaration) (module path : Name) : SourceType → RuntimeType → Bool → Prop
  | mutable : RuntimeSourceType members module path source kind →
      LocalSourceType members module path source kind true
  | constant : RuntimeSourceType members module path source kind →
      LocalSourceType members module path (.constant source) kind false

structure ResolvedLocalType (members : List Declaration) (module path : Name) (source : SourceType) where
  kind : RuntimeType
  mutable : Bool
  typing : LocalSourceType members module path source kind mutable

def resolveLocalType (members : List Declaration) (module path : Name) (source : SourceType) :
    Option (ResolvedLocalType members module path source) :=
  match source with
  | .constant inner => do
    let resolved ← resolveRuntimeType members module path inner
    return ⟨resolved.kind,false,.constant resolved.typing⟩
  | other => do
    let resolved ← resolveRuntimeType members module path other
    return ⟨resolved.kind,true,.mutable resolved.typing⟩

end Aurora.SourceBinding
