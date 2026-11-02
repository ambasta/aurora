import SourceBinding.RuntimeFacts
import SourceBinding.Stateful
namespace Aurora.SourceBinding.RuntimePrimitiveTests

private def operation : NominalIdentity := ⟨"Operation".toUTF8,5⟩
private def rejection : NominalIdentity := ⟨"Rejection".toUTF8,11⟩
example : readRuntime (.nominal operation) (some (.nominal operation.name 4)) =
    .value (.nominal operation.name 4) := by decide
example : readRuntime (.nominal operation) (some (.nominal operation.name 5)) = .trap .type := by decide
example : readRuntime (.nominal operation) (some (.nominal rejection.name 4)) = .trap .type := by decide
example : readRuntime (.nominal operation) (some (.word 4)) = .trap .type := by decide
example : readScalar .word (some (.nominal operation.name 4)) = .trap .type := by decide
example : compareNominal operation true (.nominal operation.name 4) (.nominal operation.name 4) =
    .value (.boolean true) := by decide
example : compareNominal operation false (.nominal operation.name 4) (.nominal operation.name 3) =
    .value (.boolean true) := by decide
example : compareNominal operation true (.nominal operation.name 4) (.nominal rejection.name 4) =
    .trap .type := by decide
example : binaryValue .leftShift (.word 7) .signedCount4 = .value (.word 112) := by decide
example : binaryValue .leftShift (.word 7) .signedCount12 = .value (.word 28672) := by decide
example : binaryValue .leftShift (.word 7) .signedCount32 = .value (.word 30064771072) := by decide
example : binaryValue .rightShift (.word 47) .signedCount4 = .value (.word 2) := by decide
example : binaryValue .leftShift (.word 7) (.word 4) = .trap .type := by decide
example : binaryValue .leftShift (.word 4294967296) .signedCount32 = .trap .overflow := by decide
example : binaryValue .add (.word 18446744073709551615) (.word 1) = .trap .overflow := by decide
example : binaryValue .add (.word 268435454) (.word 1) = .value (.word 268435455) := by decide

private def empty : RuntimeLocals := ⟨1,[0],fun _ => none,fun _ => none⟩
private def constant : RuntimeLocalDecl := ⟨.scalar .word,false,0⟩
private def mutableWord : RuntimeLocalDecl := ⟨.scalar .word,true,0⟩
example : empty.read 16 = .trap .type := by decide
example : (empty.assign 16 (.word 3)).isNone = true := by decide
example : ((empty.initialize 16 constant (.word 2)).bind (fun s => s.assign 16 (.word 3))).isNone = true := by decide
example : ((empty.initialize 16 mutableWord (.word 2)).bind (fun s => s.assign 16 (.boolean true))).isNone = true := by decide
example : ((empty.initialize 16 mutableWord (.word 2)).map (fun s => s.read 16)) =
    some (.value (.word 2)) := by decide
example : ((empty.initialize 16 constant (.word 2)).map (fun s => s.leave.read 16)) =
    some (.trap .type) := by decide
example : ((empty.initialize 16 constant (.word 2)).map (fun s => s.leave.enter.read 16)) =
    some (.trap .type) := by decide

private def frame : Machine := ⟨0,some (.word 9),[.word 4],fun _ => none,
  fun _ => some (.word 7),fun _ => some (.boolean true)⟩
private def storeProgram : EffectProgram := fun _ => some (.localStore (.scalar .word) 16)
example : (effectStep storeProgram frame).stores = [] ∧
    (effectStep storeProgram frame).execution.state.locals 16 = some (.word 9) ∧
    (effectStep storeProgram frame).execution.state.receiver 0 = some (.word 7) ∧
    (effectStep storeProgram frame).execution.state.accumulator = some (.word 9) := by decide

end Aurora.SourceBinding.RuntimePrimitiveTests
