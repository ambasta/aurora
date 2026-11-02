import SourceBinding.SourceStatementEquality
import SourceBinding.RuntimeTypes

namespace Aurora.SourceBinding.FramePolicyAttachment

/-! Exact reviewed syntax of the ten selected frame-policy functions. These are
whole existing raw ASTs, not a new evaluator, digest oracle or source excerpt.
The enclosing byte-backed profile must check every shape against actual parsed
source; these syntax data alone establish no execution or policy result. -/

def bytes (s : String) : ByteArray := s.toUTF8
def names (ss : List String) : Name := ss.map bytes
def v (s : String) : SourceExpr := .name [bytes s]
def enumCase (e c : String) : SourceExpr := .name (names [e,c])
def op (c : String) := enumCase "FrameOperation" c
def reason (c : String) := enumCase "FrameRejection" c
def call (s : String) (args : List SourceExpr := []) : SourceExpr :=
  .call (.named [bytes s]) args
def bin := SourceExpr.binary
def cmp (c : CompareOp) := bin (.compare c)
def ret := SourceStatement.returnValue
def branch := SourceStatement.ifThen
def reject (s : String) := ret (call "frame_reject" [reason s])
def packed (s : String) (g w : SourceExpr) :=
  ret (call "frame_record" [call s,g,w])
def u64 : SourceType := .named (names ["u64"])
def bool : SourceType := .named (names ["bool"])
def formal (s : String) (t : SourceType := u64) : Formal := ⟨bytes s,t⟩
def localDecl (s : String) (constant : Bool) (e : SourceExpr) : SourceStatement :=
  .localDecl (formal s (if constant then .constant u64 else u64)) e

/-- These are syntax data, never an alternative evaluator. -/
structure RawShape where
  name : ByteArray
  formals : List Formal
  result : SourceType
  body : List SourceStatement

def constant (n : String) (value : Nat) : RawShape :=
  ⟨bytes n,[],u64,[ret (.word value)]⟩

def kernelOwnerShape : RawShape :=
  ⟨bytes "kernel_owner",[formal "owner"],bool,
    [ret (bin .and (cmp .ge (v "owner") (.word 1)) (cmp .le (v "owner") (.word 15)))]⟩

def frameRecordShape : RawShape :=
  ⟨bytes "frame_record",[formal "state",formal "generation",formal "word"],u64,
    [ret (bin .bitOr
      (bin .bitOr (v "state") (bin .shift (v "generation") (.signedCount 4)))
      (bin .shift (v "word") (.signedCount 32)))]⟩

def frameRejectShape : RawShape :=
  ⟨bytes "frame_reject",[formal "reason" (.named (names ["FrameRejection"]))],u64,
    [localDecl "code" false (.word 1)] ++
    ([ ("record",2), ("owner",3), ("link",4), ("not_free",5),
       ("not_allocated",6), ("kernel",7), ("retired",8),
       ("wrong_owner",9), ("stale",10) ] : List (String × Nat)).map
      (fun pair => branch (cmp .eq (v "reason") (reason pair.1))
        [.assign (bytes "code") (.word pair.2)]) ++
    [ret (bin .shift (v "code") (.signedCount 4))]⟩

def recordValidShape : RawShape :=
  ⟨bytes "record_valid",[formal "record"],bool,
   [localDecl "state" true (bin .bitAnd (v "record") (.word 15)),
    localDecl "word" true (bin .rightShift (v "record") (.signedCount 32)),
    branch (cmp .eq (v "state") (call "frame_free")) [ret (.boolean true)],
    branch (cmp .eq (v "state") (call "frame_allocated"))
      [ret (bin .and (cmp .ne (v "word") (.word 0)) (.not (call "kernel_owner" [v "word"])))],
    branch (cmp .eq (v "state") (call "frame_kernel")) [ret (call "kernel_owner" [v "word"])],
    ret (bin .and (cmp .eq (v "state") (call "frame_retired")) (cmp .eq (v "word") (.word 0)))]⟩

def transitionShape : RawShape :=
  ⟨bytes "frame_transition",
   [formal "operation" (.named (names ["FrameOperation"])),formal "record",
    formal "owner",formal "generation",formal "link"],u64,
   [branch (bin .or (cmp .eq (v "operation") (op "initialize_free"))
                   (cmp .eq (v "operation") (op "initialize_kernel")))
     [branch (cmp .ne (v "record") (.word 0)) [reject "record"],
      branch (cmp .eq (v "operation") (op "initialize_kernel"))
        [branch (.not (call "kernel_owner" [v "owner"])) [reject "owner"],
         packed "frame_kernel" (.word 0) (v "owner")],
      branch (cmp .gt (v "link") (.word 4294967295)) [reject "link"],
      packed "frame_free" (.word 0) (v "link")],
    branch (bin .and (cmp .ne (v "operation") (op "allocate"))
                    (cmp .ne (v "operation") (op "release"))) [reject "operation"],
    branch (.not (call "record_valid" [v "record"])) [reject "record"],
    branch (bin .or
      (bin .or (cmp .eq (v "owner") (.word 0)) (cmp .gt (v "owner") (.word 4294967295)))
      (call "kernel_owner" [v "owner"])) [reject "owner"],
    localDecl "state" true (bin .bitAnd (v "record") (.word 15)),
    localDecl "current" true (bin .bitAnd
      (bin .rightShift (v "record") (.signedCount 4)) (call "generation_limit")),
    branch (cmp .eq (v "state") (call "frame_kernel")) [reject "kernel"],
    branch (cmp .eq (v "state") (call "frame_retired")) [reject "retired"],
    branch (cmp .eq (v "operation") (op "allocate"))
      [branch (cmp .ne (v "state") (call "frame_free")) [reject "not_free"],
       packed "frame_allocated" (v "current") (v "owner")],
    branch (cmp .ne (v "state") (call "frame_allocated")) [reject "not_allocated"],
    branch (cmp .ne (bin .rightShift (v "record") (.signedCount 32)) (v "owner")) [reject "wrong_owner"],
    branch (cmp .ne (v "generation") (v "current")) [reject "stale"],
    branch (cmp .gt (v "link") (.word 4294967295)) [reject "link"],
    branch (cmp .eq (v "current") (call "generation_limit"))
      [packed "frame_retired" (v "current") (.word 0)],
    packed "frame_free" (bin .add (v "current") (.word 1)) (v "link")]⟩

def shapes : List RawShape :=
  [constant "frame_free" 1,constant "frame_allocated" 2,
   constant "frame_kernel" 3,constant "frame_retired" 4,
   constant "generation_limit" 268435455,kernelOwnerShape,frameRecordShape,
   frameRejectShape,recordValidShape,transitionShape]

def frameModule : Name := names ["kernel","frames"]
def framePath : Name := names ["kernel"]
def operationCases : List ByteArray :=
  names ["none","initialize_free","initialize_kernel","allocate","release"]
def rejectionCases : List ByteArray :=
  names ["none","operation","record","owner","link","not_free","not_allocated",
    "kernel","retired","wrong_owner","stale"]

def operationName : ByteArray := bytes "FrameOperation"
def rejectionName : ByteArray := bytes "FrameRejection"
def rootName : ByteArray := bytes "frame_transition"

inductive Role where
  | free | allocated | kernel | retired | generationLimit
  | kernelOwner | frameRecord | frameReject | recordValid | transition
  deriving DecidableEq, Repr

def Role.all : List Role :=
  [.free,.allocated,.kernel,.retired,.generationLimit,.kernelOwner,
   .frameRecord,.frameReject,.recordValid,.transition]

def Role.shape : Role → RawShape
  | .free => constant "frame_free" 1
  | .allocated => constant "frame_allocated" 2
  | .kernel => constant "frame_kernel" 3
  | .retired => constant "frame_retired" 4
  | .generationLimit => constant "generation_limit" 268435455
  | .kernelOwner => kernelOwnerShape
  | .frameRecord => frameRecordShape
  | .frameReject => frameRejectShape
  | .recordValid => recordValidShape
  | .transition => transitionShape

def Role.name (role : Role) : ByteArray := role.shape.name

def Role.parameterKinds (role : Role) (operations rejections : NominalIdentity) : List RuntimeType :=
  match role with
  | .free | .allocated | .kernel | .retired | .generationLimit => []
  | .kernelOwner | .recordValid => [.scalar .word]
  | .frameRecord => [.scalar .word,.scalar .word,.scalar .word]
  | .frameReject => [.nominal rejections]
  | .transition => [.nominal operations,.scalar .word,.scalar .word,.scalar .word,.scalar .word]

def Role.resultKind : Role → RuntimeType
  | .kernelOwner | .recordValid => .scalar .boolean
  | _ => .scalar .word

def Role.constantValue : Role → Option Nat
  | .free => some 1 | .allocated => some 2 | .kernel => some 3
  | .retired => some 4 | .generationLimit => some 268435455
  | _ => none

end Aurora.SourceBinding.FramePolicyAttachment
