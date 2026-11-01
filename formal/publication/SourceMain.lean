import SourceBinding
open Aurora.SourceBinding

def readSource (path : System.FilePath) (limit : Nat := 1048576) : IO ByteArray :=
  IO.FS.withFile path .read fun handle => do
    let mut bytes := ByteArray.empty
    for _ in [0:limit + 1] do
      let chunk ← handle.read (USize.ofNat (min 65536 (limit + 1 - bytes.size)))
      if chunk.size == 0 then return bytes
      bytes := bytes ++ chunk
      if bytes.size > limit then throw (IO.userError "source exceeds byte limit")
    throw (IO.userError "file-read budget exhausted")

def showName (name : Name) : String :=
  String.intercalate "." (name.map String.fromUTF8!)

def main (args : List String) : IO UInt32 := do
  let (irPath, arguments) := match args with
    | "--ir" :: path :: rest => (some path,rest)
    | _ => (none,args)
  let root :: module :: classPath :: member :: paths := arguments |
    throw (IO.userError "usage: source-binding-probe [--ir PUBLICATION] ROOT_MODULE SELECT_MODULE CLASS_PATH MEMBER SOURCE ...")
  if paths.isEmpty then throw (IO.userError "no source files")
  let start ← IO.monoMsNow
  let mut total := 0
  let mut files : List SourceFile := []
  for path in paths do
    let bytes ← readSource path
    let some result := namedSource bytes | throw (IO.userError s!"source shell/bindings rejected: {path}")
    let h := result.source.header.declarations
    total := total + bytes.size
    files := files ++ [⟨bytes,result⟩]
    IO.println s!"SOURCE-SHELL module={showName h.module.name} imports={h.imports.names.map showName} bytes={bytes.size} top_declarations={result.source.shell.declarations.length}"
  let rootName := (root.splitOn ".").map String.toUTF8
  let selectedModule := (module.splitOn ".").map String.toUTF8
  let selectedPath := (classPath.splitOn "::").map String.toUTF8
  let some guarded := selectGuard files rootName selectedModule selectedPath member.toUTF8 |
    throw (IO.userError "graph, selected body syntax or pure leading guard rejected")
  let selected := guarded.selected.selected
  let method := selected.method.function
  let declared := fields selected.classDecl.members
  IO.println s!"SOURCE-MEMBER class={classPath} member={member} fields={declared.length} formals={method.formals.length} body_begin={method.body.opening.span.first} body_end={method.body.closing.span.last} body_tokens={method.body.tokens.length}"
  for (field, index) in declared.zipIdx do
    IO.println s!"SOURCE-FIELD ordinal={index} name={String.fromUTF8! field.name}"
  IO.println s!"SOURCE-GUARD body_statements={guarded.method.parsed.statements.length} tail_statements={guarded.method.tail.length + 1} pure_typed_guard=true"
  if let some path := irPath then
    let publication ← readSource path 16777216
    let some bound := bindIR files rootName selectedModule selectedPath member.toUTF8 guarded.selected publication |
      throw (IO.userError "source/publication identity rejected")
    IO.println s!"SOURCE-IR-IDENTITY callable={bound.id} fields={declared.length} publication_bytes={publication.size}"
    IO.println "IDENTITY ONLY: same-typed field-use swaps remain admissible; no semantic correspondence claim."
  IO.println s!"SOURCE-GRAPH files={files.length} bytes={total} ms={(← IO.monoMsNow) - start}"
  IO.println "NATIVE receipt only. Full selected body syntax + pure guard typing; tail untyped. No source/IR execution equivalence, capture/backend fidelity or concrete kernel acceptance."
  return 0
