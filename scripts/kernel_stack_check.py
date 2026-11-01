#!/usr/bin/env python3
"""Whole-image stack bound from compiler stack facts (an objtool-like build step).

Each linked image gets one call graph. Compiled functions use the facts their
compiler emitted with the code: GCC `-fstack-usage`/`-fcallgraph-info` for C++
and Aurora `.stack.json` for generated code. Only the remaining handwritten
assembly is decoded instruction by instruction. Every direct call or tail jump
in compiled code must be a compiler call edge; indirect calls must be declared
callbacks in the image policy table; call cycles reject.

Kernel images declare hardware entry domains explicitly. Shared exception
vectors can enter from either CPL0 or CPL3; the normalized hardware CS load and
its RPL test select separate native dispatch edges. CPL3 uses TSS.RSP0, not the
suspended supervisor stack. Named saved continuations and bounded full-frame
resume arguments are the only nonlocal stack authorities. IRET consumes an
admitted frame; arbitrary stack-pointer writes reject.

A supervisor-only physical guard bounds recursive traps. Its busy branch must
lead to a proven stack-free, nonreturning emergency CFG. Each domain includes
another 48-byte hardware frame plus the largest pre-guard vector/error prelude;
the guard never makes the hardware frame free. Supervisor/STI paths include a
kernel-origin handler, while RSP0 and double-fault IST are bounded separately.

Policy `reachable` symbols (Aurora policy entries) must be called from the
image entry or an asynchronous entry. User program images check
peak(entry) <= limit. Unreachable code must still be
acyclic and fit the limit on its own.

Usage:
  kernel_stack_check.py --limit BYTES --output JSON --policy FILE --profile ID
      [--image ELF [--facts OBJECT.ci | GENERATED.stack.json ...]]
      [--user ELF --facts GENERATED.stack.json ...]
"""

from collections import deque
from fnmatch import fnmatch
from pathlib import Path
import json
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kernel_elf import SHF_EXECINSTR, Elf, image_policy  # noqa: E402

CPU_FRAME = 48
BRANCHES = frozenset(
    "ja jae jb jbe jc je jg jge jl jle jna jnae jnb jnbe jnc jne jng jnge jnl jnle jno jnp jns jnz jo jp jpe jpo "
    "js jz jecxz jrcxz loop loope loopne".split()
)
STACK_REGISTERS = ("%rsp", "%esp", "%sp", "%spl")
FRAME_REGISTERS = ("%rbp", "%ebp", "%bp", "%bpl")
TERMINAL = frozenset("ud2".split())
INTERRUPT_RETURN = frozenset("iretq iret iretl".split())
CALLEE_SAVED = frozenset(("%rbx", "%rbp", "%r12", "%r13", "%r14", "%r15"))
PREFIXES = frozenset("rep repz repe repnz repne lock notrack bnd".split())
QUOTED = r'"(?:[^"\\]|\\.)*"'


class CheckError(ValueError):
    pass


def need(condition, message):
    if not condition:
        raise CheckError(message)


def register_owner(register):
    for full, aliases in REGISTER_ALIASES.items():
        if register in aliases:
            return full
    return register


REGISTER_ALIASES = {
    "%" + full: tuple("%" + item for item in aliases.split())
    for full, aliases in (
        ("rax", "rax eax ax al ah"),
        ("rbx", "rbx ebx bx bl bh"),
        ("rcx", "rcx ecx cx cl ch"),
        ("rdx", "rdx edx dx dl dh"),
        ("rsi", "rsi esi si sil"),
        ("rdi", "rdi edi di dil"),
        ("rbp", "rbp ebp bp bpl"),
        ("rsp", "rsp esp sp spl"),
        *((f"r{i}", f"r{i} r{i}d r{i}w r{i}b") for i in range(8, 16)),
    )
}


def operands(text):
    return re.split(r",(?![^()]*\))", text) if text else []


def disassemble(path):
    rows = {}
    pattern = re.compile(r"\s*([0-9a-f]+):\s+((?:[0-9a-f]{2} )+)\s*(\S+)\s*(.*?)\s*")
    for line in subprocess.check_output(["objdump", "-dw", str(path)], text=True).splitlines():
        match = pattern.fullmatch(line)
        if match:
            address, raw, op, args = match.groups()
            while op in PREFIXES and args:
                op, _, args = args.partition(" ")
            rows[int(address, 16)] = (len(raw.split()), op, args.split("#", 1)[0].strip())
    return rows


def direct_target(args):
    match = re.fullmatch(r"([0-9a-f]+) <[^>]+>", args)
    return int(match[1], 16) if match else None


def execution_authority_calls(path, name, fact):
    """Admit the emitted private field-effect ABI, not a source-selected pointer."""
    prefix = "__au_runtime_execution_authority_"
    expected = {
        prefix + method: {"sysv_arguments": 5, "result_max": (1 << 64) - 1}
        for method in ("prepare", "activate", "complete", "force")
    }
    expected[prefix + "retire"] = {"sysv_arguments": 4, "result_max": 1}
    expected[prefix + "finish"] = {"sysv_arguments": 3, "result_max": 1}
    calls = fact["calls"]
    signatures = fact.get("service_abi", {}).get("calls", {})
    for callee in calls.keys() | signatures.keys():
        if not callee.startswith(prefix):
            continue
        need(callee in expected, f"{path}: unknown execution authority effect {name}->{callee}")
        need(callee in calls, f"{path}: execution authority signature without call {name}->{callee}")
        need(
            signatures.get(callee) == expected[callee],
            f"{path}: execution authority signature mismatch {name}->{callee}",
        )


def compiler_facts(paths):
    """Compiler frames, call edges, signatures and separate GCC alias relations."""
    frames, edges, signatures, aliases, sources = {}, {}, {}, {}, set()
    for path in map(Path, paths):
        if path.name.endswith(".stack.json"):
            document = json.loads(path.read_text())
            need(document.get("version") in (1, 2), f"{path}: unknown Aurora stack-fact version")
            for name, fact in document["functions"].items():
                sources.add(name)
                execution_authority_calls(path, name, fact)
                local = fact["local_bytes"]
                need(type(local) is int and local >= 8, f"{path}: invalid frame for {name}")
                frames[name] = max(local, frames.get(name, 0))
                for callee, live in fact["calls"].items():
                    need(type(live) is int and 8 <= live <= local, f"{path}: invalid live bytes {name}->{callee}")
                    # HostFiles' Linux binding enters the host kernel directly and the
                    # Aurora binding (--target aurora) enters the Aurora kernel's
                    # INT 0x83 gate; both programs run only as processes, never
                    # linked into a kernel or user image profile.
                    need(callee != "__au_linux_system_call", f"{path}: {name} makes hosted Linux system calls")
                    need(callee != "__au_kernel_service_call", f"{path}: {name} makes Aurora process calls")
                    calls = edges.setdefault(name, {})
                    calls[callee] = max(live, calls.get(callee) or 0)
            continue
        lines = path.read_text().splitlines()
        source = json.loads(re.fullmatch(r"graph: \{ title: (" + QUOTED + ")", lines[0])[1])

        def name_of(title):
            return title.removeprefix(source + ":").removeprefix("*")

        graph_aliases, graph_edges = set(), {}
        for line in lines[1:-1]:
            node = re.fullmatch(
                r"node: \{ title: (" + QUOTED + ") label: (" + QUOTED + r")(?: shape : (ellipse|triangle))? \}",
                line,
            )
            if node:
                if node[3] == "ellipse":
                    continue  # Defined elsewhere; its own facts or decoding supply its frame.
                name = name_of(json.loads(node[1]))
                if node[3] == "triangle":
                    need(name not in graph_aliases, f"{path}: duplicate alias {name}")
                    graph_aliases.add(name)
                    continue
                signature, _, bound = json.loads(node[2]).split("\n")
                match = re.fullmatch(r"([0-9]+) bytes \((static|dynamic,bounded)\)", bound)
                need(match, f"{path}: unbounded stack frame in {signature}")
                frames[name] = max(int(match[1]), frames.get(name, 0))
                signatures[name] = signature
                continue
            edge = re.fullmatch(
                r"edge: \{ sourcename: (" + QUOTED + ") targetname: (" + QUOTED + ")(?: label: " + QUOTED + r")? \}",
                line,
            )
            need(edge, f"{path}: malformed callgraph line: {line[:80]}")
            caller, callee = name_of(json.loads(edge[1])), name_of(json.loads(edge[2]))
            graph_edges.setdefault(caller, []).append(callee)
        for name in graph_aliases:
            targets = graph_edges.pop(name, [])
            need(len(targets) == 1, f"{path}: alias {name} needs exactly one target edge")
            target = targets[0]
            need(aliases.setdefault(name, target) == target, f"{path}: conflicting alias target for {name}")
        for caller, callees in graph_edges.items():
            # GCC retains the caller's full frame across every call.
            for callee in callees:
                edges.setdefault(caller, {}).setdefault(callee, None)
    for name in aliases:
        need(name not in frames and name not in edges, f"alias {name} conflicts with compiled body facts")
    return frames, edges, signatures, aliases, sources


class Image:
    def __init__(self, path, facts, policy, user):
        self.path, self.user = Path(path), user
        self.elf = Elf(path)
        self.symbol_addresses = {}
        for symbol in self.elf.symbols:
            self.symbol_addresses.setdefault(symbol.name, set()).add(symbol.address)
        self.code = disassemble(path)
        self.frames, self.edges, self.signatures, aliases, self.source_names = compiler_facts(facts)
        self.callbacks = [entry.partition("=")[::2] for entry in policy.get("callbacks", [])]
        self.user_traps = policy.get("user_traps", [])
        self.async_entries = policy.get("async_entries", [])
        self.kernel_traps = policy.get("kernel_traps", [])
        self.ist_traps = policy.get("ist_traps", [])
        self.guards = [] if user else policy.get("stack_guards", [])
        self.guard_acquires = set()
        self.effect_scopes = [] if user else policy.get("effect_scopes", [])
        self.effect_native_entries = set(policy.get("effect_native_entries", []))
        self.continuations = [] if user else policy.get("stack_continuations", [])
        for rows, size in ((self.guards, 1), (self.continuations, 8)):
            for row in rows:
                self.check_storage(row["storage"], size)
        self.suspended = {}
        self.reachable = [] if user else policy.get("reachable", [])
        executable = [s for s in self.elf.sections if s.flags & SHF_EXECINSTR and s.size]
        starts = {}
        for symbol in self.elf.symbols:
            section = next((s for s in executable if s.address <= symbol.address < s.address + s.size), None)
            # Functions and global labels start code; local labels are interior jump targets.
            if section and symbol.name and symbol.section and (symbol.kind == 2 or symbol.kind == 0 and symbol.bind):
                starts.setdefault(symbol.address, []).append(symbol)
        self.names, self.extent = {}, {}
        ordered = sorted(starts)
        for index, address in enumerate(ordered):
            for symbol in starts[address]:
                self.names.setdefault(symbol.name, set()).add(address)
            section = next(s for s in executable if s.address <= address < s.address + s.size)
            end = section.address + section.size
            size = max(s.size for s in starts[address])
            self.extent[address] = (
                address + size if size else min(ordered[index + 1] if index + 1 < len(ordered) else end, end)
            )
        self.label = {a: min(symbols, key=lambda s: (s.bind == 0, s.name)).name for a, symbols in starts.items()}
        self.address_names = {a: [s.name for s in symbols] for a, symbols in starts.items()}
        self.check_aliases(aliases)
        self.compiled = {a for a in ordered if any(name in self.frames for name in self.address_names[a])}
        # Trap and site labels inside compiled functions are not separate functions.
        spans = sorted((a, self.extent[a]) for a in self.compiled)
        self.handwritten = {
            a for a in ordered if a not in self.compiled and not any(begin < a < end for begin, end in spans)
        }
        self.functions, self.memo, self.windows = {}, {}, set()

    def check_storage(self, name, size):
        symbols = [symbol for symbol in self.elf.symbols if symbol.name == name and symbol.section]
        if not symbols:
            return  # The composition may not contain this physical domain.
        need(len(symbols) == 1, self.where(f"ambiguous physical authority storage {name}"))
        symbol = symbols[0]
        section = self.elf.sections[symbol.section]
        need(
            symbol.kind == 1
            and symbol.size == size
            and symbol.address % 8 == 0
            and section.flags & 1
            and not section.flags & SHF_EXECINSTR
            and section.address <= symbol.address < symbol.address + size <= section.address + section.size,
            self.where(f"invalid physical authority storage {name}"),
        )

    def check_aliases(self, aliases):
        """Only same-body ELF aliases may use a bounded terminal's complete facts."""
        symbols, spans = {}, {}
        for symbol in self.elf.symbols:
            symbols.setdefault(symbol.name, []).append(symbol)

        def span(name):
            if name not in spans:
                matches = symbols.get(name, [])
                need(matches, self.where(f"alias relation has no linked symbol for {name}"))
                for symbol in matches:
                    need(
                        symbol.kind == 2 and 0 < symbol.section < len(self.elf.sections) and symbol.size > 0,
                        self.where(f"alias relation needs a defined, sized function: {name}"),
                    )
                    section = self.elf.sections[symbol.section]
                    need(
                        section.flags & SHF_EXECINSTR
                        and section.address
                        <= symbol.address
                        < symbol.address + symbol.size
                        <= section.address + section.size,
                        self.where(f"alias relation needs an executable function: {name}"),
                    )
                extents = {(s.address, s.address + s.size) for s in matches}
                need(len(extents) == 1, self.where(f"ambiguous linked alias relation for {name}"))
                address, end = spans[name] = extents.pop()
                need(
                    self.names.get(name) == {address} and self.extent.get(address) == end,
                    self.where(f"conflicting linked alias extent for {name}"),
                )
            return spans[name]

        for alias in aliases:
            chain, terminal = set(), alias
            while terminal in aliases:
                need(terminal not in chain, self.where(f"cyclic alias relation at {terminal}"))
                chain.add(terminal)
                terminal = aliases[terminal]
            need(terminal in self.frames, self.where(f"alias {alias} has no bounded compiled body: {terminal}"))
            body = span(terminal)
            for name in chain:
                need(span(name) == body, self.where(f"alias {name} does not share the body of {terminal}"))
                self.signatures[name] = self.signatures.get(terminal, terminal)
            # Address grouping supplies the body's full frame and call edges. The
            # alias relation is not a call, but real calls to an alias remain calls.

    def describe(self, address):
        name = self.label.get(address, hex(address))
        return self.signatures.get(name, name)

    def where(self, message):
        return f"{self.path.name}: {message}"

    def function(self, address, origin=None):
        key = (address, origin)
        if key not in self.functions:
            need(address in self.extent, self.where(f"unknown code edge to {address:#x}"))
            if address in self.compiled:
                self.functions[key] = self.compiled_function(address)
            else:
                self.functions[key] = self.handwritten_function(address, origin)
        return self.functions[key]

    def body(self, address):
        rows = [(a, *self.code[a]) for a in sorted(self.code) if address <= a < self.extent[address]]
        need(rows and rows[0][0] == address, self.where(f"no instructions at {self.describe(address)}"))
        return rows

    def compiled_function(self, address):
        names = [name for name in self.address_names[address] if name in self.frames]
        frame = max(self.frames[name] for name in names)
        signature = self.describe(address)
        declared, indirect, fault_call = {}, False, False
        for name in names:
            for callee, live in self.edges.get(name, {}).items():
                if callee == "__indirect_call":
                    allowed = [target for caller, target in self.callbacks if caller in signature]
                    need(allowed, self.where(f"undeclared indirect call in {signature}"))
                    targets = {
                        a
                        for n, s in self.signatures.items()
                        for t in allowed
                        if t and t in s
                        for a in self.names.get(n, ())
                    }
                    need(targets or allowed == [""], self.where(f"callback of {signature} is not linked"))
                    indirect, fault_call = True, fault_call or "" in allowed
                else:
                    targets = self.names.get(callee)
                    need(targets, self.where(f"{signature} calls undefined {callee}"))
                for target in targets:
                    declared[target] = max(declared.get(target, 0), live or frame)
        pushf = 0
        for at, size, op, args in self.body(address):
            if op.startswith("pushf"):
                pushf = 8  # Inline flag saves are outside GCC's frame accounting.
            elif op == "sti":
                self.windows.add(address)
            if op != "call" and op != "jmp" and op not in BRANCHES:
                continue
            target = direct_target(args)
            if target is None:
                need(op != "call" or indirect, self.where(f"undeclared indirect call in {signature}"))
                continue  # Indirect JMPs in compiled code are local jump tables.
            if op != "call" and (
                address <= target < self.extent[address] or self.code.get(target, ())[1:2] == ("ud2",)
            ):
                continue  # Local branch, or a local trap label of generated code.
            if fault_call and target not in self.code:
                continue  # Declared fault fixture: a call into data that must trap.
            need(
                target in declared,
                self.where(f"{signature} transfers to {self.describe(target)} without a compiler call edge"),
            )
        return dict(local=frame + pushf, calls=[(t, live + pushf) for t, live in declared.items()], indirect=indirect)

    def memory_address(self, at, size, operand):
        match = re.fullmatch(r"(-?0x[0-9a-f]+|-?[0-9]+)\(%rip\)", operand)
        return at + size + int(match[1], 0) if match else None

    def guard_for(self, name):
        matches = [row for row in self.guards if any(fnmatch(name, pattern) for pattern in row["entries"])]
        need(len(matches) <= 1, self.where(f"ambiguous physical trap guard for {name}"))
        return matches[0] if matches else None

    def check_emergency(self, address):
        """Prove the emergency CFG is stack-free and cannot return or call.

        This admits operations by semantics, not instruction bytes or a digest.
        Debug-exit is optional diagnostics: every continuation reaches HLT and
        remains in the same stack-free CFG if the emulator does not exit.
        """
        seen, queue, halted = set(), deque([address]), False
        end = self.extent[address]
        while queue:
            at = queue.popleft()
            if at in seen:
                continue
            seen.add(at)
            need(address <= at < end and at in self.code, self.where("emergency path escapes its function"))
            size, op, args = self.code[at]
            parts = operands(args)
            if op == "jmp":
                target = direct_target(args)
                need(target is not None, self.where("indirect emergency transfer"))
                queue.append(target)
                continue
            allowed = op in ("cli", "hlt", "nop") and not args
            if op in ("mov", "movb", "movw", "movl", "movq") and len(parts) == 2:
                allowed = (
                    parts[0].startswith("$")
                    and register_owner(parts[1]) in REGISTER_ALIASES
                    and register_owner(parts[1]) not in ("%rsp", "%rbp")
                )
            if op in ("out", "outb", "outw", "outl"):
                allowed = args in ("%al,%dx", "%ax,%dx", "%eax,%dx", "%al,(%dx)", "%ax,(%dx)", "%eax,(%dx)")
            need(allowed, self.where(f"emergency path is not stack-free: {op} {args}"))
            halted = halted or op == "hlt"
            queue.append(at + size)
        need(halted, self.where("emergency path has no halt"))

    def check_release_tail(self, address):
        """After releasing the physical guard, no work may reopen the stack."""
        seen = set()
        while True:
            need(address in self.code and address not in seen, self.where("physical guard release does not return"))
            seen.add(address)
            size, op, args = self.code[address]
            if op in INTERRUPT_RETURN or op in ("ret", "retq") and not args:
                return
            if op == "jmp":
                address = direct_target(args)
                need(address is not None, self.where("indirect transfer after physical guard release"))
                continue
            parts = operands(args)
            register_move = (
                op in ("mov", "movq", "movl", "movw", "movb")
                and len(parts) == 2
                and all(register_owner(part) in REGISTER_ALIASES for part in parts)
                and parts[1] not in STACK_REGISTERS
            )
            need(
                register_move or op.startswith("nop") or op in ("cli", "cld") and not args,
                self.where(f"work after physical guard release: {op} {args}"),
            )
            address += size

    def check_guard(self, address, row):
        """Prove every incoming path tests the owned guard before acquiring it.

        A busy branch goes straight to the separately proven stack-free sink.
        CPU frames precede this code; returned bytes count only the vector/error
        prelude, and are added to the hardware frame in the domain bound.
        """
        storage = self.symbol_addresses.get(row["storage"], set())
        emergency = self.names.get(row["emergency"], set())
        need(len(storage) == len(emergency) == 1, self.where(f"missing physical trap guard for {self.label[address]}"))
        emergency = next(iter(emergency))
        self.check_emergency(emergency)
        seen, queue, maximum, acquired = set(), deque([(address, 0, False, False)]), 0, False
        while queue:
            at, depth, compared, clear = queue.popleft()
            state = (at, depth, compared, clear)
            need(state not in seen, self.where("physical trap guard has an unguarded cycle"))
            seen.add(state)
            need(at in self.code, self.where("physical trap guard runs outside code"))
            size, op, args = self.code[at]
            parts = operands(args)
            source, destination = parts if len(parts) == 2 else ("", "")
            memory = self.memory_address(at, size, destination)
            if op in ("cmpb", "cmp") and source == "$0x0" and memory in storage:
                compared = True
            elif op in ("movb", "mov") and source == "$0x1" and memory in storage:
                need(clear, self.where("physical trap guard acquired without a clear observation"))
                self.guard_acquires.add(at)
                acquired = True
                continue
            elif op in BRANCHES:
                target = direct_target(args)
                need(
                    compared and op in ("jne", "jnz") and target == emergency,
                    self.where("physical trap guard has an unauthenticated branch"),
                )
                compared, clear = False, True
            elif op == "jmp":
                target = direct_target(args)
                need(target is not None, self.where("indirect physical trap prelude"))
                queue.append((target, depth, compared, clear))
                continue
            elif op.startswith("push"):
                need(
                    op not in ("pushw", "pusha", "pushaq") and (args.startswith("$") or args in REGISTER_ALIASES),
                    self.where("narrow or memory-reading physical trap prelude"),
                )
                depth += 8
            else:
                register_destination = (
                    register_owner(destination) in REGISTER_ALIASES and destination not in STACK_REGISTERS
                )
                register_source = register_owner(source) in REGISTER_ALIASES
                immediate_source = re.fullmatch(r"\$(?:0x[0-9a-f]+|[0-9]+)", source) is not None
                # The payload's page-fault entry observes only the hardware
                # error and RIP words before the guard; it performs no write.
                frame_source = source in ("(%rsp)", "0x8(%rsp)")
                allowed = op in ("cld", "nop") and not args
                if op in ("mov", "movq", "movl", "movw", "movb"):
                    allowed = register_destination and (register_source or immediate_source or frame_source)
                if op == "xor":
                    allowed = register_destination and register_source
                    compared = False
                need(allowed, self.where(f"unbounded physical trap prelude: {op} {args}"))
            maximum = max(maximum, depth)
            queue.append((at + size, depth, compared, clear))
        need(acquired, self.where("physical trap entry never acquires its guard"))
        return maximum

    def continuation(self, name, field):
        matches = [
            row for row in self.continuations if name in row.get(field, []) and row["storage"] in self.symbol_addresses
        ]
        need(len(matches) <= 1, self.where(f"ambiguous {field} stack authority for {name}"))
        return matches[0] if matches else None

    def handwritten_function(self, address, origin=None):
        """Interpret assembly jumps in the same state; only CALL makes a new frame.

        A register copy of RSP retains its domain and exact depth. An unrelated
        register, memory word or exchange cannot manufacture a fresh stack top.
        The only nonlocal authorities are the declared saved continuations and
        authenticated full-frame arguments of their resume entries.
        """
        name = self.label[address]
        entry = self.continuation(name, "entries")
        resume = self.continuation(name, "resumes")
        leave = self.continuation(name, "leaves")
        channel = entry or resume or leave
        registers = (("%rdi", "snapshot", resume["frame_bytes"]),) if resume else ()
        # depth, frame depth, domain, register provenance, saved continuation
        states = {address: (0, None, "entry", registers, None, None, True)}
        queue = deque([address])
        peaks, calls, transfers = {"entry": 8}, {}, set()
        need(address in self.code, self.where(f"{name} does not start with an instruction"))

        def schedule(target, state):
            need(target in self.code, self.where(f"{name} branches into a non-instruction"))
            if self.code[target][1] in TERMINAL:
                return  # No stack access or successor; predecessor peaks remain counted.
            previous = states.get(target)
            if previous is None:
                states[target] = state
                queue.append(target)
                return
            need(
                previous[:3] == state[:3] and previous[4] == state[4],
                self.where(f"inconsistent stack provenance at a join in {name}"),
            )
            # A register only remains a stack authority if every predecessor
            # carries precisely the same provenance. Losing it never creates
            # a replacement authority for a later RSP assignment.
            common = tuple(row for row in previous[3] if row in state[3])
            merged = (
                *previous[:3],
                common,
                previous[4],
                previous[5] if previous[5] == state[5] else None,
                previous[6] and state[6],
            )
            if merged != previous:
                states[target] = merged
                queue.append(target)

        while queue:
            at = queue.popleft()
            depth, frame, domain, registers, saved, condition, origin_intact = states[at]
            registers = {reg: (kind, offset) for reg, kind, offset in registers}
            size, op, args = self.code[at]
            containing = [a for a in self.handwritten if a <= at < self.extent[a]]
            if containing:
                owner = max(containing)
                if owner != address:
                    transfers.add(owner)
            following = at + size
            parts = operands(args)
            destination = parts[-1] if parts else ""
            source = parts[0] if len(parts) == 2 else ""
            written_register = register_owner(destination)
            if op.startswith("popf"):
                condition = None
            if (
                op in ("test", "testb", "testq")
                and source == "$0x3"
                and registers.get(written_register, (None,))[0] == "cs"
            ):
                condition = registers[written_register][1] == 0
            elif (
                op not in BRANCHES
                and op not in ("jmp", "mov", "movq", "movb", "movw", "movl", "lea", "nop", "cld", "std", "cli", "sti")
                and not op.startswith(("push", "pop"))
            ):
                condition = None
            need(
                not (op.startswith(("xchg", "xadd")) and any(part in STACK_REGISTERS for part in parts)),
                self.where(f"stack exchange in {name}"),
            )
            need(
                op
                not in (
                    "popa",
                    "popaq",
                    "pusha",
                    "pushaq",
                    "retf",
                    "retfq",
                    "syscall",
                    "sysenter",
                    "rsm",
                    "ljmp",
                    "lcall",
                    "xbegin",
                ),
                self.where(f"unsupported implicit stack operation in {name}"),
            )
            # Partial-register and implicit writes revoke the complete pointer
            # authority. A later 64-bit read may not reuse stale provenance.
            implicit = set()
            if op.startswith(("mul", "div", "idiv")) or op.startswith("imul") and len(parts) == 1:
                implicit.update(("%rax", "%rdx"))
            if op in ("cpuid",):
                implicit.update(("%rax", "%rbx", "%rcx", "%rdx"))
            if op in ("rdtsc", "rdtscp", "rdmsr", "rdpmc", "cqo", "cqto", "cdq", "cltd", "cwd"):
                implicit.update(("%rax", "%rdx", "%rcx"))
            if op.startswith(("movs", "cmps", "lods", "outs")):
                implicit.update(("%rsi", "%rcx"))
            if op.startswith(("movs", "cmps", "stos", "scas", "ins")):
                implicit.update(("%rdi", "%rcx"))
            if op.startswith(("lods", "xlat", "cmpxchg")) or op in ("cbw", "cwde", "cdqe", "cltq"):
                implicit.add("%rax")
            if op.startswith("loop"):
                implicit.add("%rcx")
            if op.startswith(("xchg", "xadd")) and parts:
                implicit.add(register_owner(parts[0]))
            for register in implicit:
                registers.pop(register, None)
                if register == "%rbp":
                    frame = None
            storage = self.memory_address(at, size, destination)
            readonly = op in ("cmp", "cmpb", "cmpw", "cmpl", "cmpq", "test", "testb", "testw", "testl", "testq", "bt")
            guard_rows = [row for row in self.guards if storage in self.symbol_addresses.get(row["storage"], ())]
            saved_rows = [row for row in self.continuations if storage in self.symbol_addresses.get(row["storage"], ())]
            if op.startswith(("xchg", "xadd", "cmpxchg")):
                touched = {self.memory_address(at, size, operand) for operand in parts}
                cells = {
                    value
                    for row in self.guards + self.continuations
                    for value in self.symbol_addresses.get(row["storage"], ())
                }
                need(not touched & cells, self.where(f"exchange writes a physical authority cell in {name}"))
            if guard_rows and not readonly:
                need(
                    op in ("movb", "mov") and len(guard_rows) == 1,
                    self.where(f"invalid physical guard write in {name}"),
                )
                if source == "$0x1":
                    need(at in self.guard_acquires, self.where(f"unadmitted physical guard acquisition in {name}"))
                elif source == "$0x0":
                    error = re.fullmatch(r"(?:aurora|uefi_process)_exception_(8|10|11|12|13|14|17|21|29|30)", name)
                    self.check_release_tail(following)
                    normal_return = self.guard_for(name) == guard_rows[0] and domain == "entry"
                    restored_return = domain == "continuation" and isinstance(saved, tuple) and saved[0] == "consumed"
                    need(
                        (normal_return or restored_return) and depth == (-8 if error and domain == "entry" else 0),
                        self.where(f"physical guard cleared before context restoration in {name}"),
                    )
                else:
                    raise CheckError(self.where(f"invalid physical guard write in {name}"))
            if saved_rows and not readonly:
                need(
                    op in ("mov", "movq") and len(saved_rows) == 1,
                    self.where(f"invalid saved-continuation write in {name}"),
                )
                authority = saved_rows[0]
                if source == "$0x0":
                    need(
                        domain == "continuation"
                        and saved == ("restored", authority["name"])
                        and depth == authority["saved_bytes"],
                        self.where(f"saved continuation invalidated without restoration in {name}"),
                    )
                    saved = ("consumed", authority["name"])
                else:
                    need(source == "%rsp", self.where(f"forged saved continuation in {name}"))
            # A CS load is an origin proof only while no earlier operation
            # could have overwritten its hardware frame. Register-only work,
            # downward pushes and the exact guard cell are the admitted prefix.
            if (
                not readonly
                and not guard_rows
                and not op.startswith(("push", "pop"))
                and ("(" in destination or op.startswith(("stos", "movs", "ins", "xchg", "xadd", "cmpxchg")))
            ):
                origin_intact = False
            if op == "call":
                origin_intact = False
            if op in TERMINAL:
                continue
            if op in INTERRUPT_RETURN:
                if entry or resume:
                    need(saved is not None, self.where(f"{name} enters user mode without a saved continuation"))
                    expected = saved + 40 if domain == "entry" else 40
                    need(depth == expected, self.where(f"{name} has an incomplete user IRET frame"))
                else:
                    # Error-code vectors arrive with one extra hardware word.
                    error = re.fullmatch(r"(?:aurora|uefi_process)_exception_(8|10|11|12|13|14|17|21|29|30)", name)
                    need(depth == (-8 if error else 0), self.where(f"unbalanced interrupt return in {name}"))
                continue
            need(
                op not in ("sysretq", "sysexit", "lretq", "lret"), self.where(f"unadmitted privilege return in {name}")
            )
            if op == "sti":
                self.windows.add(address)
            if op.startswith("push"):
                need(
                    not op.startswith("pushw")
                    and op != "pusha"
                    and (not destination.startswith("%") or register_owner(destination) == destination),
                    self.where(f"narrow push in {name}"),
                )
                depth += 8
                if depth <= 0:
                    origin_intact = False
            elif op.startswith("pop"):
                need(
                    not op.startswith("popw")
                    and (not destination.startswith("%") or register_owner(destination) == destination),
                    self.where(f"narrow pop in {name}"),
                )
                need(destination not in STACK_REGISTERS, self.where(f"pop into %rsp in {name}"))
                depth -= 8
                registers.pop(written_register, None)
                if destination in FRAME_REGISTERS:
                    frame = None
            elif op == "leave":
                need(frame is not None, self.where(f"leave without a known frame in {name}"))
                depth, frame = frame - 8, None
                registers.pop("%rbp", None)
            elif op == "enter":
                raise CheckError(self.where(f"enter is unsupported in {name}"))
            elif op in ("ret", "retq"):
                need(not args and depth == 0 and domain != "snapshot", self.where(f"unbalanced return in {name}"))
                need(
                    domain != "continuation" or isinstance(saved, tuple) and saved[0] == "consumed",
                    self.where(f"live saved continuation after return in {name}"),
                )
                continue
            elif op == "call":
                target = direct_target(args)
                if target is None and self.user:
                    continue  # User hostile probes have a separate guarded stack.
                need(target is not None, self.where(f"indirect call in handwritten {name}"))
                need(domain != "snapshot", self.where(f"call from a stopped-frame stack in {name}"))
                calls[target] = max(calls.get(target, 0), 8 + depth)
                registers = {reg: value for reg, value in registers.items() if reg in CALLEE_SAVED}
                # A call at the end of an assembly symbol is a fail-stop edge.
                if following not in self.code:
                    continue
            elif op == "jmp" or op in BRANCHES:
                target = direct_target(args)
                if target is None and self.user:
                    continue
                need(target is not None, self.where(f"indirect jump in handwritten {name}"))
                taken = (
                    condition
                    if op in ("je", "jz")
                    else not condition
                    if op in ("jne", "jnz") and condition is not None
                    else None
                )
                if taken is not False:
                    if target in self.compiled:
                        calls[target] = max(calls.get(target, 0), depth)
                    else:
                        schedule(
                            target,
                            (
                                depth,
                                frame,
                                domain,
                                tuple((r, *v) for r, v in sorted(registers.items())),
                                saved,
                                condition,
                                origin_intact,
                            ),
                        )
                if op == "jmp" or taken is True:
                    continue
            elif destination in STACK_REGISTERS:
                need(destination == "%rsp", self.where(f"partial stack-pointer write in {name}"))
                value = re.fullmatch(r"\$(0x[0-9a-f]+|[0-9]+)", source)
                if op in ("add", "sub") and value:
                    depth += int(value[1], 0) if op == "sub" else -int(value[1], 0)
                elif op == "and" and value and int(value[1], 0) >= 0xFFFFFFFFFFFFF000:
                    depth += 0xFFFFFFFFFFFFFFFF - int(value[1], 0)
                elif op == "lea" and re.fullmatch(r"(-?0x[0-9a-f]+|-?[0-9]+)?\(%rsp\)", source):
                    depth -= int(source.split("(")[0] or "0", 0)
                elif op in ("mov", "movq") and source in registers:
                    new_domain, new_depth = registers[source]
                    need(
                        new_domain in ("entry", "continuation", "snapshot"),
                        self.where(f"non-stack register authority in {name}"),
                    )
                    need(
                        new_domain != "snapshot" or resume and saved is not None,
                        self.where(f"unauthenticated stopped-frame switch in {name}"),
                    )
                    domain, depth, frame = new_domain, new_depth, None
                elif op in ("mov", "movq"):
                    storage = self.memory_address(at, size, source)
                    matches = [
                        row for row in self.continuations if storage in self.symbol_addresses.get(row["storage"], ())
                    ]
                    need(len(matches) == 1, self.where(f"unknown stack authority {op} {args} in {name}"))
                    authority = matches[0]
                    # A tail transfer to the named leave entry is still in this CFG.
                    owner = next((a for a in self.handwritten if a <= at < self.extent[a]), None)
                    need(
                        owner is not None and self.label[owner] in authority["leaves"],
                        self.where(f"continuation restore outside its leave entry in {name}"),
                    )
                    need(
                        saved != ("consumed", authority["name"]),
                        self.where(f"consumed continuation restored in {name}"),
                    )
                    domain, depth, frame = "continuation", authority["saved_bytes"], None
                    saved = ("restored", authority["name"])
                else:
                    raise CheckError(self.where(f"unknown stack adjustment {op} {args} in {name}"))
            elif op in ("mov", "movq") and source == "%rsp":
                if destination.startswith("%"):
                    registers[destination] = (domain, depth)
                    if destination == "%rbp":
                        frame = depth
                else:
                    storage = self.memory_address(at, size, destination)
                    need(
                        channel and (entry or resume) and storage in self.symbol_addresses.get(channel["storage"], ()),
                        self.where(f"undeclared saved stack in {name}"),
                    )
                    need(
                        domain == "entry" and depth == channel["saved_bytes"] and saved is None,
                        self.where(f"invalid suspended continuation depth in {name}"),
                    )
                    saved = depth
                    self.suspended[address] = depth
            elif destination.startswith("%") and op not in ("cmp", "test", "cmpq", "testq", "testb", "bt"):
                offset = re.fullmatch(r"(0x[0-9a-f]+|[0-9]+)\(%rsp\)", source)
                error = re.fullmatch(r"(?:aurora|uefi_process)_exception_(8|10|11|12|13|14|17|21|29|30)", name)
                hardware_cs = 16 if error else 8
                normalized = re.fullmatch(
                    r"(?:aurora|uefi_process)_(?:exception_[0-9]+|timer_interrupt|program_return|program_call|process_call|user_return|unexpected_interrupt)",
                    name,
                )
                if (
                    origin is not None
                    and origin_intact
                    and normalized
                    and domain == "entry"
                    and op in ("mov", "movq")
                    and destination == written_register
                    and offset
                    and int(offset[1], 0) - depth == hardware_cs
                ):
                    registers[destination] = ("cs", 0 if origin == "kernel" else 3)
                elif op in ("mov", "movq") and source in registers and destination == written_register:
                    registers[destination] = registers[source]
                else:
                    registers.pop(written_register, None)
                if destination in FRAME_REGISTERS:
                    frame = None
            need(-48 <= depth <= 1 << 20, self.where(f"runaway stack depth in {name}"))
            peaks[domain] = max(peaks.get(domain, 0), (0 if domain == "snapshot" else 8) + depth)
            if following in self.compiled:
                calls[following] = max(calls.get(following, 0), depth)
            else:
                schedule(
                    following,
                    (
                        depth,
                        frame,
                        domain,
                        tuple((r, *v) for r, v in sorted(registers.items())),
                        saved,
                        condition,
                        origin_intact,
                    ),
                )
        return dict(local=max(peaks.values()), calls=list(calls.items()), transfers=transfers)

    def peak(self, address, path=(), origin=None):
        need(address not in path, self.where("call cycle " + " -> ".join(map(self.describe, (*path, address)))))
        key = (address, origin)
        if key not in self.memo:
            body = self.function(address, origin)
            best = (body["local"], [address])
            for target, live in body["calls"]:
                child = self.peak(target, (*path, address), origin)
                if live + child[0] > best[0]:
                    best = (live + child[0], [address] + child[1])
            self.memo[key] = best
        return self.memo[key]

    def retained(self, entry, target):
        """Deepest stack on any path from entry into target, including target's own frame."""
        memo = {}

        def visit(address):
            if address not in memo:
                memo[address] = None
                body = self.function(address)
                best = (body["local"], [address]) if address == target else None
                for callee, live in body["calls"]:
                    child = visit(callee)
                    if child and (best is None or live + child[0] > best[0]):
                        best = (live + child[0], [address] + child[1])
                memo[address] = best
            return memo[address]

        return visit(entry)

    def closure(self, roots):
        seen, queue = set(), deque(roots)
        while queue:
            address = queue.popleft()
            if address not in seen:
                seen.add(address)
                queue.extend(target for target, _ in self.function(address)["calls"])
        return seen

    def chain(self, rows):
        return " -> ".join(map(self.describe, rows))

    def check_effect_scopes(self):
        """Closed synchronous effect boundaries, including physical IRET edges.

        All internal native and source nodes are traversed with their actual
        compiler/assembly edges. The catalogue admits only named source loans
        and physical ABI entries; it is not a claim about arbitrary new native
        code in the same trusted translation unit.
        """
        result = []
        for scope in self.effect_scopes:
            root = scope["root"]
            need(root in self.names, self.where(f"missing execution effect {root}"))
            allowed = self.effect_native_entries | set(scope["source_entries"]) | set(scope["physical"]) | {root}
            roots = set(self.names[root])
            for physical in scope["physical"]:
                need(physical in self.names, self.where(f"missing physical effect continuation {physical}"))
                roots.update(self.names[physical])
            closure = self.closure(roots)
            for address in closure:
                names = self.address_names[address]
                body = self.function(address)
                need(
                    not body.get("indirect", False),
                    self.where(f"indirect callback under {root}: {self.describe(address)}"),
                )
                for name in names:
                    if name.startswith("__au_runtime_"):
                        need(name in allowed, self.where(f"unadmitted effect boundary {root} -> {name}"))
                if address in self.handwritten:
                    need(
                        any(name in allowed for name in names),
                        self.where(f"unadmitted assembly effect boundary {root} -> {self.describe(address)}"),
                    )
                for target in body.get("transfers", ()):
                    need(
                        any(name in allowed for name in self.address_names[target]),
                        self.where(
                            f"unadmitted inline assembly transfer under {root}: "
                            f"{self.describe(address)} -> {self.describe(target)}"
                        ),
                    )
                caller_source = any(name in self.source_names for name in names)
                for target, _ in body["calls"]:
                    target_names = self.address_names[target]
                    source_target = any(name in self.source_names for name in target_names)
                    need(
                        not source_target or caller_source or any(name in scope["source_entries"] for name in names),
                        self.where(
                            f"native call bypasses admitted source entry under {root}: "
                            f"{self.describe(address)} -> {self.describe(target)}"
                        ),
                    )
            result.append(dict(root=root, nodes=len(closure), physical=scope["physical"]))
        return result

    def check(self, limit):
        entry = self.elf.entry
        need(entry in self.extent, self.where(f"no function at the ELF entry {entry:#x}"))
        guard_prefix = {}
        if not self.user:
            for address in sorted(self.handwritten):
                guard = self.guard_for(self.label[address])
                if guard:
                    guard_prefix[address] = self.check_guard(address, guard)
        normal = self.peak(entry)
        reached = self.closure([entry])
        result = dict(image=self.path.name, limit=limit, normal=normal[0], normal_path=self.chain(normal[1]))
        others = [a for a in sorted(self.compiled | self.handwritten) if a not in reached]
        if self.user:
            others = [a for a in others if a in self.compiled]  # Unreached labels may be data.
        for address in others:
            need(
                self.peak(address)[0] <= limit,
                self.where(f"{self.describe(address)} alone needs {self.peak(address)[0]} bytes"),
            )
        if self.user:
            need(normal[0] <= limit, self.where(f"stack {normal[0]} exceeds {limit}: {self.chain(normal[1])}"))
            return dict(result, total=normal[0])
        # A callable bridge that happens to be unused is not a hardware vector.
        # Hardware roots are explicit domain declarations; all other functions
        # still receive ordinary code/edge/standalone-stack admission above.
        entries = [
            a for a in self.handwritten if any(fnmatch(self.label[a], pattern) for pattern in self.async_entries)
        ]
        trap = {a for a in entries if any(fnmatch(self.label[a], pattern) for pattern in self.user_traps)}
        ist = {a for a in entries if any(fnmatch(self.label[a], pattern) for pattern in self.ist_traps)}
        kernel_entries = (set(entries) - trap - ist) | {
            a for a in entries if a not in ist and any(fnmatch(self.label[a], pattern) for pattern in self.kernel_traps)
        }
        nested = max((CPU_FRAME + prefix for prefix in guard_prefix.values()), default=0)

        def worst(roots, origin):
            return max(
                ((CPU_FRAME + self.peak(a, origin=origin)[0], self.peak(a, origin=origin)[1]) for a in roots),
                default=(0, []),
            )

        kernel, any_entry = worst(kernel_entries, "kernel"), worst(set(entries) - ist, "kernel")
        total = normal[0] + kernel[0] + nested
        need(
            total <= limit,
            self.where(
                f"stack {normal[0]} + interrupt {kernel[0]} + nested frame {nested} = {total} exceeds {limit}; "
                f"{self.chain(normal[1])}; interrupt {self.chain(kernel[1])}"
            ),
        )
        # IRET may fault before consuming its hardware frame after the guard
        # was released. That is a new kernel-origin trap on this same stack,
        # not a free transfer to the suspended supervisor. The kernel path
        # rejects that RIP rather than treating it as a timer-drain return.
        return_fault = 40 + kernel[0] + nested
        rsp0 = max(worst(trap - ist, "user")[0] + nested, return_fault if trap - ist else 0)
        emergency_stack = max(
            worst(ist, "kernel")[0] + nested, worst(ist, "user")[0] + nested, return_fault if ist else 0
        )
        need(rsp0 <= limit, self.where(f"RSP0 domain {rsp0} exceeds {limit}"))
        need(emergency_stack <= limit, self.where(f"IST domain {emergency_stack} exceeds {limit}"))
        suspended = []
        for address, depth in sorted(self.suspended.items()):
            retained = self.retained(entry, address)
            if retained:
                # Includes the entry's transient launch frame as a conservative
                # upper bound, never drops the suspended supervisor call chain.
                suspended.append(dict(entry=self.label[address], saved_bytes=depth, bound=retained[0]))
        result.update(
            interrupt=kernel[0],
            interrupt_path=self.chain(kernel[1]),
            user_trap=worst(trap, "user")[0],
            domains=dict(
                supervisor=total,
                rsp0=rsp0,
                ist=emergency_stack,
                nested_frame=nested,
                return_fault=return_fault,
            ),
            suspended=suspended,
        )
        live = {name for a in self.closure([entry, *entries]) for name in self.address_names.get(a, [self.label[a]])}
        missing = sorted(set(self.reachable) - live)
        need(not missing, self.where(f"policy entry points never called: {missing}"))
        for window in sorted(self.windows & reached):
            retained = self.retained(entry, window)
            combined = retained[0] + any_entry[0] + nested
            need(
                combined <= limit,
                self.where(
                    f"interrupt window {self.chain(retained[1])} + {self.chain(any_entry[1])}"
                    f" = {combined} exceeds {limit}"
                ),
            )
            total = max(total, combined)
        result["domains"]["supervisor"] = total
        return dict(
            result,
            total=max(total, rsp0, emergency_stack),
            windows=len(self.windows & reached),
            effects=self.check_effect_scopes(),
        )


def main(argv):
    options, images = {}, []
    arguments = iter(argv)
    try:
        for flag in arguments:
            value = next(arguments, None)
            need(value is not None and flag.startswith("--"), __doc__)
            if flag in ("--image", "--user"):
                images.append((value, [], flag == "--user"))
            elif flag == "--facts":
                need(images, "--facts must follow --image or --user")
                images[-1][1].append(value)
            else:
                options[flag[2:]] = value
        need(set(options) == {"limit", "output", "policy", "profile"} and images, __doc__)
        policy = image_policy(options["policy"], options["profile"])
        limit = int(options["limit"], 0)
        results = [Image(path, facts, policy, user).check(limit) for path, facts, user in images]
    except CheckError as error:
        print(f"FAIL: kernel stack check {options.get('profile', '')}: {error}", file=sys.stderr)
        return 1
    Path(options["output"]).write_text(json.dumps(results, indent=2) + "\n")
    print(f"PASS: {options['profile']} stack " + ", ".join(f"{r['image']} {r['total']}/{limit}" for r in results))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
