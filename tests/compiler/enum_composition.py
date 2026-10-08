#!/usr/bin/env python3
"""Combined enum/Value composition and independent class method-result checks.

Expectations come from source-level values and an ordinary Python snapshot model,
never compiler IR or generated assembly. Native observations must exit normally
and contain exactly eight result bytes. Every rejection is checked with both an
absent output and a pre-existing byte-exact output, preserving all source inputs.
No kernel, fault injection, trap observer, or experimental compiler API is used.
Explicit require calls keep checks active under python3 -O.

Run: python3 tests/compiler/enum_composition.py build/aurorac
Optional reproducible model: --seed 12012 --steps 24
"""
from __future__ import annotations

import argparse
import hashlib
from itertools import product
from pathlib import Path
import random
import resource
import subprocess
import tempfile
import time


ROOT = Path(__file__).resolve().parents[2]
MAX_U64 = (1 << 64) - 1
HIGH_U64 = 1 << 63
ENUMS = "enum class Status{ok,error};enum class Other{ok,error};"
EMPTY = "class Empty{public:Empty(){}auto answer()const->i64{return 42;}};"
LEAF = """class Leaf{
    Status state;u64 value;
public:
    Leaf(Status s,u64 n):state(s),value(n){}
    auto status()const->Status{return state;}
    auto get()const->u64{return value;}
    auto set(Status s,u64 n)->u64{state=s;value=n;return value;}
    auto change(Status s)->Status{state=s;return state;}
    auto snapshot()const->Leaf{const Leaf result=Leaf(state,value);return result;}
};"""
PACKET = """class Packet{
public:
    Status tag;Leaf item;Empty empty;bool valid;
    Packet(Status s,Leaf source,Empty zero,bool flag)
        :tag(s),item(source),empty(zero),valid(flag){}
};"""
FACTORY = """class Factory{
    Status state;u64 value;
public:
    Factory(Status s,u64 n):state(s),value(n){}
    auto get()const->u64{return value;}
    auto status()const->Status{return state;}
    auto set(Status s,u64 n)->u64{state=s;value=n;return value;}
    auto snapshot()const->Packet{
        const Leaf leaf=Leaf(state,value);const Empty zero=Empty();
        const Packet result=Packet(state,leaf,zero,true);return result;
    }
    auto advance(u64 n)->Packet{
        value=value+n;state=Status::error;
        const Packet result=snapshot();return result;
    }
    auto forwarded()const->Packet{const Packet result=snapshot();return result;}
};"""
BASE = ENUMS + EMPTY + LEAF + PACKET + FACTORY


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def program(body, definitions="", helpers="", imports="", result="i64"):
    return ("module app;" + imports + definitions + helpers +
            f"auto test()->{result}{{{body}}}")


def validate_native(observed, expected):
    require(observed.returncode == 0, f"native exit {observed.returncode}: {observed.stderr!r}")
    require(observed.stderr == b"", f"unexpected native stderr: {observed.stderr!r}")
    require(len(observed.stdout) == 8, f"expected eight result bytes: {observed.stdout!r}")
    actual = int.from_bytes(observed.stdout, "little", signed=False)
    require(actual == expected % (1 << 64), f"expected {expected % (1 << 64)}, got {actual}")


ENTRY = """.text
.globl _start
_start:
    call test
    pushq %rax
    movq $1, %rax
    movq $1, %rdi
    movq %rsp, %rsi
    movq $8, %rdx
    syscall
    cmpq $8, %rax
    jne .Lwrite_failed
    movq $60, %rax
    xorq %rdi, %rdi
    syscall
.Lwrite_failed:
    movq $60, %rax
    movq $1, %rdi
    syscall
.section .note.GNU-stack,"",@progbits
"""


def run(command):
    return subprocess.run([str(x) for x in command], capture_output=True, timeout=8,
                          preexec_fn=lambda: resource.setrlimit(resource.RLIMIT_CORE, (0, 0)))


def execute(directory, assembly):
    entry = directory / "entry.s"
    entry.write_text(ENTRY)
    for command in (("as", "--64", assembly, "-o", directory / "program.o"),
                    ("as", "--64", entry, "-o", directory / "entry.o"),
                    ("ld", "-o", directory / "program", directory / "entry.o",
                     directory / "program.o")):
        built = run(command)
        require(built.returncode == 0, f"{command[0]} failed: {built.stderr!r}")
    return run([directory / "program"])


def harness_self_test():
    good = subprocess.CompletedProcess([], 0, (MAX_U64).to_bytes(8, "little"), b"")
    validate_native(good, MAX_U64)
    invalid = [subprocess.CompletedProcess([], code, payload, diagnostic)
               for code, payload, diagnostic in
               ((1, good.stdout, b""), (-11, good.stdout, b""),
                (0, b"", b""), (0, good.stdout[:-1], b""),
                (0, good.stdout + b"x", b""), (0, b"\x00" * 8, b""),
                (0, good.stdout, b"unexpected"))]
    for observed in invalid:
        try:
            validate_native(observed, MAX_U64)
        except AssertionError:
            pass
        else:
            raise AssertionError("invalid native observation accepted")
    with tempfile.TemporaryDirectory(prefix="aurora-enum-harness-") as temporary:
        directory = Path(temporary)
        for value in (0, 42, HIGH_U64, MAX_U64):
            assembly = directory / "program.s"
            assembly.write_text(f'.text\n.globl test\ntest:\nmovabsq ${value}, %rax\nret\n'
                                '.section .note.GNU-stack,"",@progbits\n')
            validate_native(execute(directory, assembly), value)
    print("PASS enum composition harness: exact 64-bit native values and rejected invalid observations",
          flush=True)


class Suite:
    def __init__(self, compiler, keep_going=False):
        self.compiler = compiler
        self.keep_going = keep_going
        self.count = 0
        self.executions = 0
        self.rejections = 0
        self.rejection_compiles = 0
        self.modeled_steps = 0
        self.failures = []
        self.library_inputs = {p: p.read_bytes() for p in (ROOT / "library").rglob("*.au")}

    def check(self, name, source, expected=42, reject=False, modules=None):
        with tempfile.TemporaryDirectory(prefix="aurora-enum-composition-") as temporary:
            directory = Path(temporary)
            input_path = directory / "input.au"
            output = directory / "program.s"
            input_path.write_text(source)
            inputs = dict(self.library_inputs)
            inputs[input_path] = source.encode()
            roots = [ROOT / "library"]
            if modules:
                module_root = directory / "modules"
                roots.insert(0, module_root)
                for module, content in modules.items():
                    path = module_root / (module.replace(".", "/") + ".au")
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(content)
                    inputs[path] = content.encode()
            command = [self.compiler, input_path, "-o", output]
            for root in roots:
                command.extend(["--module-root", root])
            try:
                artifacts = (None, b"previous verified artifact\x00\xff\n") if reject else (None,)
                for original in artifacts:
                    if original is not None:
                        output.write_bytes(original)
                    compiled = run(command)
                    for path, before in inputs.items():
                        require(path.read_bytes() == before, "source input changed: " + str(path))
                    if reject:
                        require(compiled.returncode == 1,
                                f"expected ordinary rejection exit 1, got {compiled.returncode}: "
                                f"{compiled.stderr!r}")
                        require(bool(compiled.stderr.strip()), "missing type/syntax diagnostic")
                        if original is None:
                            require(not output.exists(), "rejection created output artifact")
                        else:
                            require(output.read_bytes() == original, "rejection changed prior artifact")
                        self.rejection_compiles += 1
                    else:
                        require(compiled.returncode == 0,
                                f"compiler exit {compiled.returncode}: {compiled.stderr!r}")
                        validate_native(execute(directory, output), expected)
                        self.executions += 1
                self.count += 1
                self.rejections += int(reject)
                print("PASS enum composition", name, flush=True)
            except (AssertionError, subprocess.TimeoutExpired) as failure:
                details = f"{name}: {failure}\nSource:\n{source}"
                if modules:
                    details += "\nModules:\n" + repr(modules)
                if not self.keep_going:
                    raise AssertionError(details) from failure
                self.failures.append(details)
                print("FAIL enum composition", details, flush=True)


def value_cases(suite):
    for first, second in product(("Status", "Other"), repeat=2):
        concrete = f"std::pair<{first},{second}>"
        suite.check(f"Value enum pair {first} {second}", program(
            f"{concrete} original={concrete}({first}::ok,{second}::error);"
            f"{concrete} copied=identity(original);copied.first={first}::error;"
            f"if(original.first!={first}::ok){{return 1;}}"
            f"if(copied.second!={second}::error){{return 2;}}"
            f"static_assert(size_of({concrete})==16);"
            f"static_assert(field_count({concrete})==2);return 42;", ENUMS,
            f"auto identity({concrete} value)->{concrete}{{return value;}}",
            "import std.utility;"))
    for scalar, value in (("i64", "-9223372036854775808"),
                          ("u64", f"{MAX_U64}u64"), ("bool", "true")):
        for enum_first in (True, False):
            concrete = f"std::pair<Status,{scalar}>" if enum_first else f"std::pair<{scalar},Status>"
            arguments = f"Status::error,{value}" if enum_first else f"{value},Status::error"
            enum_field, scalar_field = ("first", "second") if enum_first else ("second", "first")
            suite.check(f"Value mixed enum {scalar} enum_first={enum_first}", program(
                f"const {concrete} original={concrete}({arguments});"
                f"const {concrete} copy=identity(original);"
                f"if(copy.{enum_field}!=Status::error){{return 0;}}"
                f"if(copy.{scalar_field}!={value}){{return 1;}}return 42;", ENUMS,
                f"auto identity({concrete} value)->{concrete}{{return value;}}",
                "import std.utility;"))
    for enum_first in (True, False):
        concrete = "std::pair<Status,Leaf>" if enum_first else "std::pair<Leaf,Status>"
        args = "Status::error,source" if enum_first else "source,Status::error"
        enum_field, leaf_field = ("first", "second") if enum_first else ("second", "first")
        suite.check(f"Value enum class pair enum_first={enum_first}", program(
            f"Leaf source=Leaf(Status::ok,{MAX_U64}u64);"
            f"const {concrete} original={concrete}({args});"
            "source.set(Status::error,0u64);"
            f"const {concrete} copied=identity(original);Leaf child=copied.{leaf_field};"
            f"const Leaf saved=original.{leaf_field};child.set(Status::error,42u64);"
            f"if(copied.{enum_field}!=Status::error){{return 0u64;}}"
            "if(saved.status()!=Status::ok){return 0u64;}"
            "if(child.get()!=42u64){return 0u64;}return saved.get();", ENUMS + LEAF,
            f"auto identity({concrete} value)->{concrete}{{return value;}}",
            "import std.utility;", "u64"), MAX_U64)
    suite.check("enum specialization identity includes ordered nominal arguments", program(
        "static_assert(type_id(std::pair<Status,Other>)!=type_id(std::pair<Other,Status>));"
        "static_assert(type_id(std::pair<Status,Status>)!=type_id(std::pair<Other,Other>));"
        "static_assert(type_id(std::pair<Status,i64>)!=type_id(std::pair<i64,Status>));"
        "static_assert(type_id(std::pair<Status,Leaf>)!=type_id(std::pair<Other,Leaf>));"
        "if(reflect_size(type_id(std::pair<Status,Leaf>))!=24){return 1;}"
        "if(reflect_field_count(type_id(std::pair<Status,Leaf>))!=2){return 2;}return 42;",
        ENUMS + LEAF, imports="import std.utility;"))
    suite.check("Value substituted enum method and class constructor", program(
        "Box<Status> box=Box<Status>(Status::ok);"
        "if(box.replace(Status::error)!=Status::ok){return 1;}"
        "if(box.get()!=Status::error){return 2;}return 42;", ENUMS +
        "template<Value T>class Box{T item;public:Box(T value):item(value){}"
        "auto get()const->T{return item;}auto replace(T next)->T{"
        "const T old=item;item=next;return old;}};"))
    suite.check("Value substituted class result copies complete named local", program(
        f"Leaf source=Leaf(Status::ok,{MAX_U64}u64);Box<Leaf> box=Box<Leaf>(source);"
        "Leaf copied=box.get();copied.set(Status::error,0u64);"
        "const Leaf saved=box.get();if(saved.status()!=Status::ok){return 0u64;}return saved.get();",
        ENUMS + LEAF + "template<Value T>class Box{T item;public:Box(T value):item(value){}"
        "auto get()const->T{const T result=item;return result;}};", result="u64"), MAX_U64)


def snapshot_cases(suite):
    repeat = """class Repeated{public:Leaf first;Status middle;Leaf second;
        Repeated(Leaf a,Status s,Leaf b):second(b),middle(s),first(a){}
    };"""
    suite.check("enum side effect separates class constructor snapshots", program(
        f"Leaf source=Leaf(Status::ok,{MAX_U64}u64);"
        "Repeated value=Repeated(source,source.change(Status::error),source);"
        "const Leaf first=value.first;const Leaf second=value.second;"
        "if(first.status()!=Status::ok){return 0u64;}"
        "if(second.status()!=Status::error){return 0u64;}"
        "if(value.middle!=Status::error){return 0u64;}return first.get();",
        ENUMS + LEAF + repeat, result="u64"), MAX_U64)
    suite.check("later class result call cannot overwrite enum constructor snapshot", program(
        "Leaf source=Leaf(Status::ok,42u64);"
        "Repeated value=Repeated(source,clobber(),source);"
        "const Leaf first=value.first;const Leaf second=value.second;"
        "if(value.middle!=Status::error){return 0u64;}"
        "if(first.status()!=Status::ok){return 0u64;}return second.get();",
        BASE + repeat,
        "auto clobber()->Status{const Factory factory=Factory(Status::error,999u64);"
        "const Packet packet=factory.snapshot();const Leaf leaf=packet.item;return leaf.status();}",
        result="u64"))
    suite.check("readonly constructor parameter permits copied class result", program(
        "const Factory source=Factory(Status::ok,42u64);Holder holder=Holder(source);"
        "const Factory copied=holder.item;const Packet packet=copied.snapshot();"
        "const Leaf leaf=packet.item;return leaf.get();",
        BASE + "class Holder{public:Factory item;Holder(Factory source):item(source){} };",
        result="u64"))


def owned_field_cases(suite):
    # Direct owned replacement and receivers are supported by
    # compiler/OWNED-FIELD-MUTATION.md. Keep their enum/value invariants native.
    for enum_first in (True, False):
        concrete = "std::pair<Status,Leaf>" if enum_first else "std::pair<Leaf,Status>"
        arguments = "Status::ok,source" if enum_first else "source,Status::ok"
        enum_field, leaf_field = ("first", "second") if enum_first else ("second", "first")
        suite.check(f"direct owned enum class replacement enum_first={enum_first}", program(
            f"Leaf source=Leaf(Status::ok,{HIGH_U64}u64);"
            f"{concrete} pair={concrete}({arguments});const {concrete} before=pair;"
            f"Leaf replacement=Leaf(Status::error,{MAX_U64}u64);"
            f"pair.{leaf_field}=replacement;replacement.set(Status::ok,0u64);"
            f"const Leaf copied=pair.{leaf_field};const Leaf saved=before.{leaf_field};"
            f"if(pair.{enum_field}!=Status::ok){{return 1u64;}}"
            f"if(before.{enum_field}!=Status::ok){{return 2u64;}}"
            "if(copied.status()!=Status::error){return 3u64;}"
            f"if(saved.status()!=Status::ok||saved.get()!={HIGH_U64}u64){{return 4u64;}}"
            f"if(source.status()!=Status::ok||source.get()!={HIGH_U64}u64){{return 5u64;}}"
            "if(replacement.status()!=Status::ok||replacement.get()!=0u64){return 6u64;}"
            "return copied.get();", ENUMS + LEAF, imports="import std.utility;", result="u64"),
            MAX_U64)
        suite.check(f"direct owned enum class result enum_first={enum_first}", program(
            f"Leaf source=Leaf(Status::error,{MAX_U64}u64);"
            f"{concrete} pair={concrete}({arguments});"
            f"const Leaf saved=pair.{leaf_field}.snapshot();"
            f"Leaf changed=pair.{leaf_field}.snapshot();changed.set(Status::ok,0u64);"
            f"if(pair.{leaf_field}.status()!=Status::error){{return 1u64;}}"
            f"if(pair.{leaf_field}.get()!={MAX_U64}u64){{return 2u64;}}"
            f"pair.{leaf_field}.set(Status::ok,{HIGH_U64}u64);source.set(Status::ok,0u64);"
            f"if(pair.{enum_field}!=Status::ok){{return 3u64;}}"
            f"if(pair.{leaf_field}.status()!=Status::ok){{return 4u64;}}"
            f"if(pair.{leaf_field}.get()!={HIGH_U64}u64){{return 5u64;}}"
            "if(changed.status()!=Status::ok||changed.get()!=0u64){return 6u64;}"
            "if(saved.status()!=Status::error){return 7u64;}return saved.get();",
            ENUMS + LEAF, imports="import std.utility;", result="u64"), MAX_U64)


def method_result_cases(suite):
    for method in ("snapshot", "forwarded"):
        suite.check("nested enum class result " + method, program(
            f"const Factory factory=Factory(Status::ok,{MAX_U64}u64);"
            f"Packet first=factory.{method}();first.tag=Status::error;"
            "Leaf changed=first.item;changed.set(Status::error,0u64);"
            "const Packet second=factory.snapshot();const Leaf leaf=second.item;"
            "const Empty zero=second.empty;if(zero.answer()!=42){return 0u64;}"
            "if(second.tag!=Status::ok){return 0u64;}if(!second.valid){return 0u64;}"
            "if(leaf.status()!=Status::ok){return 0u64;}return leaf.get();",
            BASE, result="u64"), MAX_U64)
    suite.check("mutable result independent of later receiver and result mutation", program(
        "Factory factory=Factory(Status::ok,20u64);Packet first=factory.advance(22u64);"
        "Packet second=factory.advance(1u64);first.tag=Status::ok;"
        "factory.set(Status::ok,0u64);const Leaf a=first.item;const Leaf b=second.item;"
        "if(second.tag!=Status::error){return 0u64;}if(a.get()!=42u64){return 0u64;}return b.get();",
        BASE, result="u64"), 43)
    suite.check("nested result survives receiver and method stack lifetimes", program(
        "const Packet packet=make();const Leaf leaf=packet.item;"
        "if(packet.tag!=Status::error){return 0u64;}return leaf.get();", BASE,
        f"auto make()->Packet{{const Factory factory=Factory(Status::error,{HIGH_U64}u64);"
        "const Packet local=factory.forwarded();return local;}", result="u64"), HIGH_U64)
    suite.check("class-result hidden receiver survives nested and ordinary result calls", program(
        "Factory factory=Factory(Status::ok,10u64);const Packet packet=factory.combined(6u64);"
        "const Leaf leaf=packet.item;if(factory.get()!=16u64){return 0u64;}"
        "if(packet.tag!=Status::error){return 0u64;}return leaf.get();",
        BASE.replace("auto forwarded()", "auto combined(u64 delta)->Packet{"
                     "const Packet before=snapshot();const Packet after=advance(delta);"
                     "const Packet copied=copy_packet(after);const Leaf a=before.item;"
                     "const Leaf b=copied.item;const Leaf leaf=Leaf(state,a.get()+b.get()+value);"
                     "const Empty zero=Empty();const Packet result=Packet(state,leaf,zero,true);"
                     "return result;}auto forwarded()"),
        "auto copy_packet(Packet source)->Packet{return source;}", result="u64"))
    suite.check("class-result hidden destination survives two nested receivers", program(
        "const Mixer source=Mixer(10u64);const Packet packet=source.mix();"
        "const Leaf leaf=packet.item;return leaf.get();", BASE +
        "class Mixer{u64 base;public:Mixer(u64 n):base(n){}auto mix()const->Packet{"
        "Factory left=Factory(Status::ok,20u64);Factory right=Factory(Status::error,12u64);"
        "const Packet a=left.snapshot();const Packet b=right.forwarded();"
        "const Packet c=copy_packet(a);const Leaf x=c.item;const Leaf y=b.item;"
        "const Leaf leaf=Leaf(Status::ok,x.get()+y.get()+base);const Empty zero=Empty();"
        "const Packet result=Packet(Status::ok,leaf,zero,true);return result;}};",
        "auto copy_packet(Packet source)->Packet{return source;}", result="u64"))
    suite.check("six explicit method arguments plus receiver and result preserve order", program(
        "Factory factory=Factory(Status::ok,0u64);const Packet packet=factory.six("
        "factory.set(Status::ok,1u64),factory.set(Status::error,2u64),"
        "factory.set(Status::ok,3u64),factory.set(Status::error,4u64),"
        "factory.set(Status::ok,5u64),factory.set(Status::error,6u64));"
        "const Leaf leaf=packet.item;if(packet.tag!=Status::error){return 0u64;}return leaf.get();",
        BASE.replace("auto forwarded()", "auto six(u64 a,u64 b,u64 c,u64 d,u64 e,u64 f)"
                     "const->Packet{const Leaf leaf=Leaf(state,"
                     "a+10u64*b+100u64*c+1000u64*d+10000u64*e+100000u64*f+1000000u64*value);"
                     "const Empty zero=Empty();const Packet result=Packet(state,leaf,zero,true);"
                     "return result;}auto forwarded()"), result="u64"), 6654321)
    suite.check("method result can return complete branch copies", program(
        "const Factory factory=Factory(Status::ok,42u64);const Packet chosen=factory.choose(false);"
        "const Leaf leaf=chosen.item;if(chosen.tag!=Status::error){return 0u64;}return leaf.get();",
        BASE.replace("auto forwarded()", "auto choose(bool first)const->Packet{"
                     "if(first){const Packet yes=snapshot();return yes;}"
                     "const Factory other=Factory(Status::error,value);"
                     "const Packet no=other.snapshot();return no;}auto forwarded()"), result="u64"))
    suite.check("zero-leaf nested method result preserves logical completion", program(
        "const EmptyFactory factory=EmptyFactory();const EmptyRoot root=factory.make();"
        "const EmptyMiddle middle=root.item;const EmptyLeaf leaf=middle.item;"
        "const Empty zero=leaf.item;static_assert(size_of(EmptyRoot)==8);return zero.answer();",
        EMPTY + "class EmptyLeaf{public:Empty item;EmptyLeaf(Empty x):item(x){} };"
        "class EmptyMiddle{public:EmptyLeaf item;EmptyMiddle(EmptyLeaf x):item(x){} };"
        "class EmptyRoot{public:EmptyMiddle item;EmptyRoot(EmptyMiddle x):item(x){} };"
        "class EmptyFactory{public:EmptyFactory(){}auto make()const->EmptyRoot{"
        "const Empty a=Empty();const EmptyLeaf b=EmptyLeaf(a);const EmptyMiddle c=EmptyMiddle(b);"
        "const EmptyRoot result=EmptyRoot(c);return result;}};"))


def wide_definitions(capacity=59, extra_level=False):
    definitions = ENUMS + EMPTY + f"""class Storage{{
        Status state;builtin::array<u64,{capacity}> data;u64 high;bool valid;Empty empty;
    public:
        Storage(Status s,u64 n,bool flag,Empty zero):state(s),data{{}},high(n),valid(flag),empty(zero){{}}
        auto status()const->Status{{return state;}}
        auto first()const->u64{{return high;}}
        auto flag()const->bool{{return valid;}}
        auto at(i64 index)const->u64{{return data[index];}}
        auto set(i64 index,u64 n)->u64{{data[index]=n;return data[index];}}
        auto zero()const->Empty{{const Empty result=empty;return result;}}
    }};class Middle{{public:Storage item;Status marker;
        Middle(Storage source,Status s):item(source),marker(s){{}}
    }};class Root{{public:Status marker;Middle item;
        Root(Status s,Middle source):marker(s),item(source){{}}
    }};"""
    if extra_level:
        definitions += "class Beyond{Root item;public:Beyond(Root source):item(source){} };"
    return definitions


def wide_cases(suite):
    factory = """class WideFactory{u64 seed;public:WideFactory(u64 n):seed(n){}
        auto make()const->Root{
            const Empty zero=Empty();Storage leaf=Storage(Status::ok,seed,true,zero);
            i64 i=0;while(i<59){leaf.set(i,seed^u64(i));i=i+1;}
            const Middle middle=Middle(leaf,Status::error);
            const Root result=Root(Status::ok,middle);return result;
        }
        auto forwarded()const->Root{
            const Root first=make();const Root copy=copy_root(first);return copy;
        }
    };"""
    for method in ("make", "forwarded"):
        body = (f"const WideFactory factory=WideFactory({MAX_U64}u64);"
                f"const Root root=factory.{method}();const Middle middle=root.item;"
                "Storage leaf=middle.item;const Empty zero=leaf.zero();"
                "if(zero.answer()!=42){return 0u64;}if(!leaf.flag()){return 0u64;}"
                "if(leaf.status()!=Status::ok){return 0u64;}"
                "if(root.marker!=Status::ok){return 0u64;}"
                "if(middle.marker!=Status::error){return 0u64;}")
        for index in range(59):
            body += f"if(leaf.at({index})!={MAX_U64 ^ index}u64){{return 0u64;}}"
        body += ("leaf.set(0,0u64);const Storage saved=middle.item;"
                 f"if(saved.at(0)!={MAX_U64}u64){{return 0u64;}}"
                 "static_assert(size_of(Root)==512);static_assert(field_count(Root)==2);"
                 "if(reflect_size(type_id(Root))!=512){return 0u64;}return leaf.first();")
        suite.check("four-level 64-leaf enum array empty result " + method,
                    program(body, wide_definitions() + factory,
                            "auto copy_root(Root source)->Root{return source;}", result="u64"), MAX_U64)
    suite.check("enum leaves count toward composed 64-leaf limit", program(
        "return 42;", wide_definitions(60)), reject=True)
    suite.check("empty descendant counts toward composed four-level limit", program(
        "return 42;", wide_definitions(extra_level=True)), reject=True)
    suite.check("named wrapper around std array is a Value argument and method result", program(
        "const ArrayFactory factory=ArrayFactory();const Wrapper result=factory.make();"
        "const std::pair<Status,ArrayValue> pair=result.item;ArrayValue value=pair.second;"
        "std::array<u64,2> elements=value.item;elements.set(0,0u64);"
        "const std::array<u64,2> saved=value.item;if(pair.first!=Status::ok){return 0u64;}"
        "if(saved.at(1)!=9223372036854775808u64){return 0u64;}return saved.at(0);",
        ENUMS + "class ArrayValue{public:std::array<u64,2> item;"
        "ArrayValue(std::array<u64,2> source):item(source){} };"
        "class Wrapper{public:std::pair<Status,ArrayValue> item;"
        "Wrapper(std::pair<Status,ArrayValue> source):item(source){} };"
        "class ArrayFactory{public:ArrayFactory(){}auto make()const->Wrapper{"
        "std::array<u64,2> a=std::array<u64,2>();a.set(0,18446744073709551615u64);"
        "a.set(1,9223372036854775808u64);const ArrayValue value=ArrayValue(a);"
        "const std::pair<Status,ArrayValue> pair=std::pair<Status,ArrayValue>(Status::ok,value);"
        "const Wrapper result=Wrapper(pair);return result;}};",
        imports="import std.array;import std.utility;", result="u64"), MAX_U64)


def modeled_copies(suite, seed, steps):
    rng = random.Random(seed)
    body = "Factory factory=Factory(Status::ok,0u64);"
    saved = []
    for index in range(steps):
        state = rng.choice(("ok", "error"))
        value = rng.choice((0, 42, HIGH_U64, MAX_U64, rng.randrange(1 << 64)))
        body += (f"factory.set(Status::{state},{value}u64);"
                 f"const Packet saved{index}=factory.forwarded();")
        saved.append((state, value))
    body += "factory.set(Status::error,1u64);"
    for index, (state, value) in enumerate(saved):
        body += (f"{{Packet copy=saved{index};copy.tag=Status::{state};"
                 "Leaf changed=copy.item;changed.set(Status::error,2u64);"
                 f"const Leaf original=saved{index}.item;"
                 f"if(original.get()!={value}u64){{return 0u64;}}"
                 f"if(original.status()!=Status::{state}){{return 0u64;}}"
                 f"if(saved{index}.tag!=Status::{state}){{return 0u64;}}}}")
    body += f"return {MAX_U64}u64;"
    suite.check(f"independent enum/class snapshot model seed={seed} steps={steps}",
                program(body, BASE, result="u64"), MAX_U64)
    suite.modeled_steps += steps


def module_cases(suite):
    generic = {"boxes": "export module boxes;export template<Value T>class Box{T item;"
               "public:Box(T source):item(source){}auto get()const->T{const T result=item;return result;}"
               "auto forwarded()const->T{const T result=get();return result;}};"}
    suite.check("imported Value template forwards caller-private nominal enum", program(
        "const Box<Status> box=Box<Status>(Status::error);const Status value=box.forwarded();"
        "if(value!=Status::error){return 1;}return 42;", ENUMS,
        imports="import boxes;"), modules=generic)
    suite.check("imported Value template forwards caller-private nominal class", program(
        f"const Leaf source=Leaf(Status::ok,{MAX_U64}u64);const Box<Leaf> box=Box<Leaf>(source);"
        "Leaf copied=box.forwarded();copied.set(Status::error,0u64);"
        "const Leaf saved=box.forwarded();if(saved.status()!=Status::ok){return 0u64;}return saved.get();",
        ENUMS + LEAF, imports="import boxes;", result="u64"), MAX_U64, modules=generic)
    modules = {
        "states": "export module states;export " + ENUMS,
        "leaves": "export module leaves;import states;export " + LEAF,
        "factory": "export module factory;import states;import leaves;import std.utility;"
        "export class Maker{public:Maker(){}auto make()const->std::pair<Status,Leaf>{"
        "const Leaf leaf=Leaf(Status::error,18446744073709551615u64);"
        "const std::pair<Status,Leaf> result=std::pair<Status,Leaf>(Status::ok,leaf);return result;}};",
    }
    body = ("const Maker maker=Maker();const std::pair<Status,Leaf> result=maker.make();"
            "const Leaf leaf=result.second;if(result.first!=Status::ok){return 0u64;}"
            "if(leaf.status()!=Status::error){return 0u64;}return leaf.get();")
    suite.check("imported enum class template and result use exact direct identities", program(
        body, imports="import states;import leaves;import factory;import std.utility;", result="u64"),
        MAX_U64, modules=modules)
    for missing in ("states", "leaves", "std.utility"):
        imports = "".join(f"import {name};" for name in
                          ("states", "leaves", "factory", "std.utility") if name != missing)
        suite.check("class result requires direct visible import " + missing,
                    program(body, imports=imports, result="u64"), reject=True, modules=modules)
    private = "enum class Secret{ok,error};"
    exposures = {
        "enum Value result": "export auto make()->std::pair<Secret,i64>{"
            "const std::pair<Secret,i64> result=std::pair<Secret,i64>(Secret::ok,42);return result;}",
        "enum Value parameter": "export auto consume(std::pair<Secret,i64> input)->i64{return input.second;}",
        "enum public field": "export class Exposed{public:Secret state;};",
        "enum public constructor": "export class Exposed{Secret state;public:"
            "Exposed(Secret s):state(s){} };",
        "class result public method": "class Hidden{public:Secret state;};export class Exposed{"
            "public:Exposed(){}auto make()const->Hidden{const Hidden result=Hidden{.state=Secret::ok};"
            "return result;}};",
        "enum result public method": "export class Exposed{public:Exposed(){}"
            "auto status()const->Secret{return Secret::ok;}};",
    }
    for label, exposed in exposures.items():
        suite.check("export visibility rejects hidden " + label,
                    program("return 42;", imports="import hidden;"), reject=True,
                    modules={"hidden": "export module hidden;import std.utility;" + private + exposed})
    suite.check("private enum representation remains encapsulated", program(
        "const Opaque value=Opaque();return value.get();", imports="import hidden;"),
        modules={"hidden": "export module hidden;" + private +
        "export class Opaque{Secret state;public:Opaque():state(Secret::ok){}"
        "auto get()const->i64{if(state==Secret::ok){return 42;}return 0;}};"})
    sides = {}
    for name in ("left", "right"):
        sides[name] = (f"export module {name};import std.utility;" + ENUMS +
                       f"export auto {name}_id()->i64{{return type_id(std::pair<Status,i64>);}}"
                       f"export auto {name}_value()->i64{{"
                       "const std::pair<Status,i64> p=std::pair<Status,i64>(Status::ok,21);"
                       "if(p.first!=Status::ok){return 0;}return p.second;}")
    suite.check("same spelling private enum specializations keep defining module identity", program(
        "if(left_id()==right_id()){return 1;}return left_value()+right_value();",
        imports="import left;import right;"), modules=sides)
    exported = {name: f"export module {name};export namespace {name}{{{ENUMS}}}"
                for name in ("left", "right")}
    suite.check("same layout imported enums yield distinct pair identities", program(
        "static_assert(type_id(std::pair<left::Status,i64>)!="
        "type_id(std::pair<right::Status,i64>));"
        "static_assert(size_of(std::pair<left::Status,i64>)=="
        "size_of(std::pair<right::Status,i64>));return 42;",
        imports="import left;import right;import std.utility;"), modules=exported)
    suite.check("same layout imported enum pair copy rejects nominal substitution", program(
        "const std::pair<left::Status,i64> source=std::pair<left::Status,i64>(left::Status::ok,42);"
        "const std::pair<right::Status,i64> wrong=source;return 42;",
        imports="import left;import right;import std.utility;"), reject=True, modules=exported)


def decimal_cases(suite):
    imports = "import std.decimal;import std.utility;"
    for label, digits, status, value, position in (
        ("empty", (), "empty", 0, 0),
        ("zero", (0,), "success", 0, 1),
        ("success", (4, 2), "success", 42, 2),
        ("maximum", tuple(int(c) for c in str(MAX_U64)), "success", MAX_U64, 20),
        ("invalid", (4, 2, 10), "invalid_digit", 0, 2),
        ("overflow", tuple(int(c) for c in str(MAX_U64 + 1)), "out_of_range", 0, 19),
    ):
        concrete = "std::pair<std::DecimalStatus,std::DecimalResult>"
        expected = value if status == "success" else HIGH_U64
        body = "std::DecimalAccumulator accumulator=std::DecimalAccumulator();"
        body += "".join(f"accumulator.push_digit({digit}u64);" for digit in digits)
        body += ("const std::DecimalResult report=accumulator.finish();"
                 f"const {concrete} pair={concrete}(report.status(),report);"
                 "const DecimalBox box=DecimalBox(pair);accumulator.reset();"
                 "const DecimalBox returned=box.snapshot();"
                 f"const {concrete} copied=returned.item;const std::DecimalResult saved=copied.second;"
                 f"if(copied.first!=std::DecimalStatus::{status}){{return 1u64;}}"
                 f"if(saved.status()!=std::DecimalStatus::{status}){{return 2u64;}}"
                 f"if(saved.position()!={position}){{return 3u64;}}"
                 f"return saved.value_or({HIGH_U64}u64);")
        definitions = (f"class DecimalBox{{public:{concrete} item;"
                       f"DecimalBox({concrete} value):item(value){{}}"
                       "auto snapshot()const->DecimalBox{"
                       f"const {concrete} copy=item;const DecimalBox result=DecimalBox(copy);return result;}}}};")
        suite.check("std.decimal named result enum composition " + label,
                    program(body, definitions, imports=imports, result="u64"), expected)
    suite.check("std.decimal two different result snapshots share no state", program(
        "std::DecimalAccumulator accumulator=std::DecimalAccumulator();accumulator.push_digit(4u64);"
        "const std::DecimalResult first=accumulator.finish();accumulator.push_digit(2u64);"
        "const std::DecimalResult second=accumulator.finish();"
        "const std::pair<std::DecimalResult,std::DecimalResult> pair="
        "std::pair<std::DecimalResult,std::DecimalResult>(first,second);accumulator.reset();"
        "const std::DecimalResult a=pair.first;const std::DecimalResult b=pair.second;"
        "if(a.value_or(0u64)!=4u64){return 0u64;}return b.value_or(0u64);",
        imports=imports, result="u64"))


def rejection_cases(suite):
    pair = "std::pair<Status,Leaf>"
    init = f"Leaf leaf=Leaf(Status::ok,42u64);{pair} pair={pair}(Status::ok,leaf);"
    for label, body in (
        ("wrong enum pair constructor", f"Leaf leaf=Leaf(Status::ok,42u64);{pair} p={pair}(Other::ok,leaf);return 42;"),
        ("wrong enum pair field assignment", init + "pair.first=Other::ok;return 42;"),
        ("wrong enum extracted pair field", init + "Other state=pair.first;return 42;"),
        ("integer extracted pair field", init + "i64 value=pair.first;return value;"),
        ("enum field used as condition", init + "if(pair.first){return 42;}return 0;"),
        ("enum field numeric conversion", init + "return i64(pair.first);"),
        ("enum field unsigned conversion", init + "u64 value=u64(pair.first);return 42;"),
        ("nested enum field wrong equality", init + "if(pair.first==Other::ok){return 42;}return 0;"),
        ("enum pair copied into different enum specialization", init +
         "std::pair<Other,Leaf> wrong=pair;return 42;"),
        ("enum pair copied into reordered specialization", init +
         "std::pair<Leaf,Status> wrong=pair;return 42;"),
        ("readonly root owned field replacement", init.replace(f"{pair} pair=", f"const {pair} pair=") +
         "pair.second=leaf;return 42;"),
        ("readonly root owned mutable receiver", init.replace(f"{pair} pair=", f"const {pair} pair=") +
         "pair.second.set(Status::error,0u64);return 42;"),
        ("same layout wrong nominal owned field replacement", init +
         "Factory other=Factory(Status::ok,42u64);pair.second=other;return 42;"),
        ("owned field result requires exact nominal destination", init +
         "Factory result=pair.second.snapshot();return 42;"),
        ("deeper owned field replacement remains rejected", init +
         f"std::pair<Status,{pair}> outer=std::pair<Status,{pair}>(Status::ok,pair);"
         "outer.second.second=leaf;return 42;"),
        ("deeper owned field receiver remains rejected", init +
         f"std::pair<Status,{pair}> outer=std::pair<Status,{pair}>(Status::ok,pair);"
         "Leaf result=outer.second.second.snapshot();return 42;"),
        ("enum builtin array", "array<Status,2> values={Status::ok,Status::error};return 42;"),
        ("enum std array", "std::array<Status,2> values=std::array<Status,2>();return 42;"),
        ("nested template value requires exact class constructor argument", "std::pair<Status,std::pair<Status,i64>> p="
         "std::pair<Status,std::pair<Status,i64>>(Status::ok,42);return 42;"),
    ):
        suite.check(label, program(body, BASE, imports="import std.utility;import std.array;"), reject=True)
    for label, action in (("replacement", "input.second=leaf;"),
                          ("mutable receiver", "input.second.set(Status::error,0u64);")):
        suite.check("readonly parameter owned field " + label, program(
            init + "return mutate(pair,leaf);", BASE,
            f"auto mutate({pair} input,Leaf leaf)->i64{{{action}return 42;}}",
            imports="import std.utility;"), reject=True)
    for operator in ("+", "-", "*", "/", "%", "&", "|", "^", "<<", ">>"):
        suite.check("composed enum arithmetic rejected " + operator, program(
            init + f"Status result=pair.first{operator}Status::error;return 42;", BASE,
            imports="import std.utility;"), reject=True)
    for operator in ("<", "<=", ">", ">="):
        suite.check("composed enum ordering rejected " + operator, program(
            init + f"if(pair.first{operator}Status::error){{return 42;}}return 0;", BASE,
            imports="import std.utility;"), reject=True)
    for label, argument in (("nominal enum", "Status"), ("named concrete class", "Leaf")):
        suite.check("Scalar rejects " + label, program(
            f"static_assert(size_of(Only<{argument}>)>0);return 42;", ENUMS + LEAF +
            "template<Scalar T>class Only{T item;public:Only(T source):item(source){} };"), reject=True)
    for constraints, concrete in (("Scalar T,Value U", "Status,Leaf"),
                                   ("Value T,Scalar U", "Leaf,Status")):
        suite.check("mixed constraints preserve Scalar exclusion " + constraints, program(
            f"static_assert(size_of(Mixed<{concrete}>)>0);return 42;", ENUMS + LEAF +
            f"template<{constraints}>class Mixed{{T a;U b;public:Mixed(T x,U y):a(x),b(y){{}}}};"),
            reject=True)
    method_init = "Factory factory=Factory(Status::ok,42u64);"
    for label, body, helpers in (
        ("class result cannot initialize scalar", method_init + "u64 wrong=factory.snapshot();return 42;", ""),
        ("class result requires exact nominal destination", method_init + "Leaf wrong=factory.snapshot();return 42;", ""),
        ("class result cannot be discarded", method_init + "factory.snapshot();return 42;", ""),
        ("class result requires fresh local", method_init + "Packet saved=factory.snapshot();saved=factory.snapshot();return 42;", ""),
        ("class result cannot be temporary argument", method_init + "return consume(factory.snapshot());",
         "auto consume(Packet value)->i64{return 42;}"),
        ("class result cannot be directly returned", method_init + "Packet p=forward(factory);return 42;",
         "auto forward(Factory source)->Packet{return source.snapshot();}"),
        ("mutable result method rejects const receiver", "const Factory factory=Factory(Status::ok,42u64);"
         "const Packet result=factory.advance(0u64);return 42;", ""),
        ("const result field cannot mutate", method_init + "const Packet result=factory.snapshot();"
         "result.tag=Status::error;return 42;", ""),
        ("wrong enum method argument", "Leaf leaf=Leaf(Status::ok,42u64);leaf.change(Other::ok);return 42;", ""),
    ):
        suite.check(label, program(body, BASE, helpers), reject=True)
    for label, declaration in (
        ("wrong nominal class return", "auto make()const->Packet{Leaf value=Leaf(Status::ok,42u64);return value;}"),
        ("wrong nominal enum return", "auto status()const->Status{return Other::ok;}"),
    ):
        suite.check(label + " remains rejected", program("return 42;", BASE +
                    "class Invalid{public:Invalid(){}" + declaration + "};"), reject=True)
    suite.check("direct class construction return preserves enum payload", program(
        "Maker maker=Maker();Leaf result=maker.make();"
        "if(result.status()!=Status::ok){return 1;}return i64(result.get());", BASE +
        "class Maker{public:Maker(){}auto make()const->Leaf{return Leaf(Status::ok,42u64);}};"))
    suite.check("copied class method parameter preserves enum payload", program(
        "Leaf source=Leaf(Status::ok,42u64);Receiver receiver=Receiver();Leaf result=receiver.take(source);"
        "source.change(Status::error);if(result.status()!=Status::ok){return 1;}return i64(result.get());", BASE +
        "class Receiver{public:Receiver(){}auto take(Leaf value)const->Leaf{return value;}};"))
    suite.check("nested class method parameter preserves copied result", program(
        "Factory factory=Factory(Status::ok,42u64);Packet source=factory.snapshot();Receiver receiver=Receiver();"
        "Packet result=receiver.take(source);const Leaf item=result.item;return i64(item.get());", BASE +
        "class Receiver{public:Receiver(){}auto take(Packet value)const->Packet{return value;}};"))
    suite.check("Value substitution authorizes copied class method parameter", program(
        "Leaf leaf=Leaf(Status::ok,42u64);Box<Leaf> box=Box<Leaf>(leaf);Leaf result=box.take(leaf);"
        "leaf.change(Status::error);if(result.status()!=Status::ok){return 1;}return i64(result.get());", ENUMS + LEAF +
        "template<Value T>class Box{T item;public:Box(T source):item(source){}"
        "auto take(T source)const->T{return source;}};"))
    suite.check("Value enum substitution does not authorize builtin enum arrays", program(
        "Box<Status> box=Box<Status>();return 42;", ENUMS +
        "template<Value T>class Box{builtin::array<T,2> data;public:Box():data{}{} };"), reject=True)
    suite.check("decimal enum cannot satisfy Scalar constraint", program(
        "static_assert(size_of(Only<std::DecimalStatus>)>0);return 42;",
        "template<Scalar T>class Only{T item;public:Only(T source):item(source){} };",
        imports="import std.decimal;"), reject=True)
    suite.check("decimal result private enum field remains private after composition", program(
        "std::DecimalAccumulator a=std::DecimalAccumulator();const std::DecimalResult result=a.finish();"
        "const std::pair<Status,std::DecimalResult> pair=std::pair<Status,std::DecimalResult>(Status::ok,result);"
        "const std::DecimalResult copy=pair.second;"
        "if(copy.outcome==std::DecimalStatus::empty){return 42;}return 0;", ENUMS,
        imports="import std.decimal;import std.utility;"), reject=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("compiler", type=Path, nargs="?", default=ROOT / "build/aurorac")
    parser.add_argument("--seed", type=int, default=12012)
    parser.add_argument("--steps", type=int, default=24)
    parser.add_argument("--self-test-only", action="store_true")
    parser.add_argument("--keep-going", action="store_true")
    args = parser.parse_args()
    require(1 <= args.steps <= 64, "steps must be between 1 and 64")
    harness_self_test()
    if args.self_test_only:
        return
    compiler = args.compiler.resolve()
    print(f"INFO enum composition compiler={compiler} "
          f"sha256={hashlib.sha256(compiler.read_bytes()).hexdigest()}", flush=True)
    for module in (ROOT / "library/std/utility.au", ROOT / "library/std/decimal.au"):
        print(f"INFO enum composition {module.name} sha256={hashlib.sha256(module.read_bytes()).hexdigest()}",
              flush=True)
    started = time.monotonic()
    suite = Suite(compiler, args.keep_going)
    value_cases(suite)
    snapshot_cases(suite)
    owned_field_cases(suite)
    method_result_cases(suite)
    wide_cases(suite)
    modeled_copies(suite, args.seed, args.steps)
    module_cases(suite)
    decimal_cases(suite)
    rejection_cases(suite)
    print(f"INFO enum composition: {suite.count} passed, {suite.executions} native executions, "
          f"{suite.rejections} ordinary rejections ({suite.rejection_compiles} artifact checks), "
          f"{suite.modeled_steps} snapshot model steps, {len(suite.failures)} failures; "
          f"seed={args.seed}; elapsed={time.monotonic()-started:.2f}s", flush=True)
    require(not suite.failures, f"{len(suite.failures)} enum-composition checks failed")
    print("PASS enum composition complete", flush=True)


if __name__ == "__main__":
    main()
