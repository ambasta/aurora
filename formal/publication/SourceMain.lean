import SourceBinding
import SourceBinding.SemanticBinding
import SourceBinding.SnapshotExamples
import SourceBinding.BodyExamples
import SourceBinding.CallExamples
import SourceBinding.ForwardWrapper
import SourceBinding.LeafBinding
import SourceBinding.NominalFreeIdentity
import SourceBinding.RuntimeReturnBinding
import SourceBinding.RuntimeCallFormalBinding
import SourceBinding.RuntimeBodyPublic
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
  let (runtimeBody, args) := match args with
    | "--runtime-body" :: rest => (true,rest)
    | _ => (false,args)
  let (runtimeCall, args) := match args with
    | "--runtime-call-expression" :: path :: start :: rest => (some (path,start),rest)
    | _ => (none,args)
  let (runtimeExpression, args) := match args with
    | "--runtime-expression" :: rest => (true,rest)
    | _ => (false,args)
  let (runtimeIdentity, args) := match args with
    | "--runtime-identity" :: rest => (true,rest)
    | _ => (false,args)
  let (forward, args) := match args with
    | "--forward-leaf" :: name :: rest => (some name,rest)
    | _ => (none,args)
  let (callMode, callExamples, args) := match args with
    | "--calls" :: rest => (true,false,rest)
    | "--call-examples" :: rest => (true,true,rest)
    | _ => (false,false,args)
  let (bodyMode, bodyExamples, args) := match args with
    | "--body" :: rest => (true,false,rest)
    | "--body-examples" :: rest => (true,true,rest)
    | _ => (false,false,args)
  let (examples, args) := match args with
    | "--snapshot-examples" :: rest => (true,rest)
    | _ => (false,args)
  let (irPath, arguments) := match args with
    | "--ir" :: path :: rest => (some path,rest)
    | _ => (none,args)
  let root :: module :: classPath :: member :: paths := arguments |
    throw (IO.userError "usage: source-binding-probe [--runtime-body|--runtime-call-expression PATH START|--runtime-expression|--runtime-identity|--forward-leaf WRAPPER|--calls|--call-examples|--body|--body-examples|--snapshot-examples] [--ir PUBLICATION] ROOT_MODULE SELECT_MODULE CLASS_PATH MEMBER SOURCE ...")
  if runtimeBody && (runtimeCall.isSome || runtimeExpression || runtimeIdentity || forward.isSome || callMode || bodyMode || examples) then
    throw (IO.userError "runtime body and other modes are distinct")
  if runtimeBody && irPath.isNone then throw (IO.userError "runtime body requires --ir")
  if runtimeCall.isSome && (runtimeExpression || runtimeIdentity || forward.isSome || callMode || bodyMode || examples) then
    throw (IO.userError "runtime call interval and other modes are distinct")
  if runtimeCall.isSome && irPath.isNone then throw (IO.userError "runtime call interval requires --ir")
  if runtimeExpression && (runtimeIdentity || forward.isSome || callMode || bodyMode || examples) then
    throw (IO.userError "runtime expression and other modes are distinct")
  if runtimeExpression && irPath.isNone then throw (IO.userError "runtime expression requires --ir")
  if runtimeIdentity && (forward.isSome || callMode || bodyMode || examples) then
    throw (IO.userError "runtime identity and semantic modes are distinct")
  if runtimeIdentity && irPath.isNone then throw (IO.userError "runtime identity requires --ir")
  if forward.isSome && (callMode || bodyMode || examples) then
    throw (IO.userError "forward/call/body/snapshot modes are distinct")
  if forward.isSome && irPath.isNone then throw (IO.userError "forward mode requires --ir")
  if callMode && (bodyMode || examples) then throw (IO.userError "call/body/snapshot modes are distinct")
  if callMode && irPath.isNone then throw (IO.userError "call mode requires --ir")
  if bodyMode && examples then throw (IO.userError "body and snapshot modes are distinct")
  if bodyMode && irPath.isNone then throw (IO.userError "body mode requires --ir")
  if examples && irPath.isNone then throw (IO.userError "snapshot examples require --ir")
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
  if runtimeBody then
    let some path := irPath | throw (IO.userError "runtime body requires --ir")
    let publication ← readSource path 16777216
    let some checked := bindRuntimeBody files rootName selectedModule selectedPath member.toUTF8 publication |
      throw (IO.userError "source/runtime body correspondence rejected")
    let t := Aurora.Publication.tables checked.bound.artifact.document.reversed.reverse
    IO.println s!"SOURCE-RUNTIME-BODY callable={checked.bound.checked.id} entry=0 stop={(Aurora.Publication.functionCode t checked.bound.checked.id).size} complete=true leaves={checked.body.leaves.map (fun leaf => leaf.identified.id)} publication_bytes={publication.size}"
    IO.println s!"SOURCE-GRAPH files={files.length} bytes={total} ms={(← IO.monoMsNow) - start}"
    IO.println "NATIVE full-input complete body certificate receipt. Generic theorem derives actual PC0 execution for typed arguments, matching source outcome and ordered call trace, including faults. No general closed DAG, lifecycle ResultSpec, concrete kernel acceptance, capture/backend/native ABI or authority proof."
    return 0
  if let some (sourcePath,startText) := runtimeCall then
    let some indices := (sourcePath.splitOn ",").mapM String.toNat? |
      throw (IO.userError "invalid source statement path")
    let some startPC := startText.toNat? | throw (IO.userError "invalid interval start")
    let some path := irPath | throw (IO.userError "runtime call interval requires --ir")
    let publication ← readSource path 16777216
    let some checked := bindRuntimeFormalCallInterval files rootName selectedModule selectedPath member.toUTF8
        indices startPC publication | throw (IO.userError "source/runtime call interval rejected")
    let interval := checked.checked.interval
    IO.println s!"SOURCE-RUNTIME-CALL-INTERVAL formal_entry=true callable={checked.bound.checked.id} source_path={indices} start={interval.start} stop={interval.code.stop} leaves={interval.leaves.map (fun leaf => leaf.identified.id)} publication_bytes={publication.size}"
    IO.println s!"SOURCE-GRAPH files={files.length} bytes={total} ms={(← IO.monoMsNow) - start}"
    IO.println "NATIVE full-input contextual interval/callee certificate receipt only. Candidate PC is checked, not proved reachable or correctly placed for the lexical branch. No complete caller/DAG/lifecycle, concrete kernel acceptance, native ABI or backend claim."
    return 0
  if runtimeExpression then
    let some path := irPath | throw (IO.userError "runtime expression requires --ir")
    let publication ← readSource path 16777216
    let some checked := bindRuntimeReturn files rootName selectedModule selectedPath member.toUTF8 publication |
      throw (IO.userError "source/runtime return correspondence rejected")
    IO.println s!"SOURCE-RUNTIME-EXPRESSION callable={checked.bound.checked.id} entry=0 expression={checked.body.parameters.kinds.length} stop={checked.body.stop + 1} complete=true publication_bytes={publication.size}"
    IO.println s!"SOURCE-GRAPH files={files.length} bytes={total} ms={(← IO.monoMsNow) - start}"
    IO.println "NATIVE full-input receipt only. Complete single-return source/IR certificate for typed initial arguments, matching values OR faults; no ten-helper DAG, lifecycle ResultSpec, concrete kernel acceptance, capture/backend/native ABI or authority proof."
    return 0
  if runtimeIdentity then
    let some path := irPath | throw (IO.userError "runtime identity requires --ir")
    let publication ← readSource path 16777216
    let some bound := bindRuntimeFree files rootName selectedModule selectedPath member.toUTF8 publication |
      throw (IO.userError "source/runtime identity rejected")
    let checked := bound.checked
    let t := Aurora.Publication.tables bound.artifact.document.reversed.reverse
    let declarations := checked.details.lexical.lexical.declaredItems
    IO.println s!"SOURCE-RUNTIME-IDENTITY callable={checked.id} rows={(Aurora.Publication.functionCode t checked.id).size} nominal_signature={hasNominal checked.details.types.kinds} locals={declarations.length} local_slots={declarations.map (fun (item : SourceLocal) => item.slot)} publication_bytes={publication.size}"
    IO.println s!"SOURCE-GRAPH files={files.length} bytes={total} ms={(← IO.monoMsNow) - start}"
    IO.println "NATIVE full-input identity/scope/complete-slot receipt only. No expression/call/body execution certificate, concrete kernel acceptance, native enum conversion, producer/backend or lifecycle authority proof."
    return 0
  if let some wrapper := forward then
    let some path := irPath | throw (IO.userError "forward mode requires --ir")
    let publication ← readSource path 16777216
    let some bound := bindForwardWrapper files rootName selectedModule selectedPath
        wrapper.toUTF8 member.toUTF8 publication |
      throw (IO.userError "source/publication forward semantics rejected")
    let checked := bound.checked
    IO.println s!"SOURCE-IR-FORWARD wrapper={checked.wrapper.id} entry=0 stop={checked.callPC + 2} call={checked.callPC} leaf={checked.leaf.identified.id} leaf_stop={checked.leaf.core.stop} complete=true publication_bytes={publication.size}"
    let some _shape := checkLeafShape checked.leaf |
      throw (IO.userError "exact leaf policy rejected")
    IO.println "LEAF-POLICY exact=true six_word_parameters=true"
    IO.println s!"SOURCE-GRAPH files={files.length} bytes={total} ms={(← IO.monoMsNow) - start}"
    IO.println "NATIVE full-input receipt only. Complete free/forward certificates and exact numeric policy; no concrete kernel acceptance, general D2 closure, capture/backend/native ABI or authority proof."
    return 0
  if callMode then
    let some path := irPath | throw (IO.userError "call mode requires --ir")
    let publication ← readSource path 16777216
    let some checked := bindCalls files rootName selectedModule selectedPath member.toUTF8 publication |
      throw (IO.userError "source/publication call semantics rejected")
    if callExamples then runCallExamples checked
    IO.println s!"SOURCE-IR-CALLS callable={checked.family.shape.ir.id} entry=0 stop={checked.family.shape.stop} complete=true publication_bytes={publication.size}"
    IO.println s!"SOURCE-GRAPH files={files.length} bytes={total} ms={(← IO.monoMsNow) - start}"
    IO.println "NATIVE full-input receipt only. Generic finite source/IR trace correspondence with SAME external responses; no concrete kernel acceptance, producer/backend/native API fidelity, external framing or environmental liveness."
    return 0
  if bodyMode then
    let some path := irPath | throw (IO.userError "body mode requires --ir")
    let publication ← readSource path 16777216
    let some checked := bindBody files rootName selectedModule selectedPath member.toUTF8 publication |
      throw (IO.userError "source/publication body semantics rejected")
    let selected := checked.source.selected.selected
    let method := selected.method.function
    IO.println s!"SOURCE-BODY member={member} fields={(fields selected.classDecl.members).length} formals={method.formals.length} body_begin={method.body.opening.span.first} body_end={method.body.closing.span.last} statements={checked.source.method.parsed.statements.length}"
    if bodyExamples then runBodyExamples checked
    IO.println s!"SOURCE-IR-BODY callable={checked.ir.id} entry=0 body_start={method.formals.length} stop={checked.stop} complete=true publication_bytes={publication.size}"
    IO.println s!"SOURCE-GRAPH files={files.length} bytes={total} ms={(← IO.monoMsNow) - start}"
    IO.println "NATIVE full-input receipt only. Checked local body execution/ordered-store correspondence; no concrete kernel acceptance, capture/backend fidelity, external resource-call or native API proof."
    return 0
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
    let some safe := bindSafeSemantics files rootName selectedModule selectedPath member.toUTF8 publication |
      throw (IO.userError "source/publication guard semantics rejected")
    if examples then runSnapshotExamples safe
    let semantic := safe.semantic
    IO.println s!"SOURCE-IR-GUARD callable={semantic.ir.id} fields={declared.length} publication_bytes={publication.size} entry=0 expression_end={semantic.endExpr} continuation={semantic.endExpr + 4}"
    IO.println "SAFE GUARD: checked short-circuit range certificate; first-exit includes binding and false-return. Tail instructions/effects unproved."
  IO.println s!"SOURCE-GRAPH files={files.length} bytes={total} ms={(← IO.monoMsNow) - start}"
  IO.println "NATIVE receipt only. Full selected body syntax + pure guard typing; tail untyped. Guard-prefix semantics only; no tail effects, capture/backend fidelity or concrete kernel acceptance."
  return 0
