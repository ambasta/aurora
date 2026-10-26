#!/usr/bin/env python3
"""Whole-image stack bound from compiler stack facts (an objtool-like build step).

Each linked image gets one call graph. Compiled functions use the facts their
compiler emitted with the code: GCC `-fstack-usage`/`-fcallgraph-info` for C++
and Aurora `.stack.json` for generated code. Only the remaining handwritten
assembly is decoded instruction by instruction. Every direct call or tail jump
in compiled code must be a compiler call edge; indirect calls must be declared
callbacks in the image policy table; call cycles reject.

Kernel images have asynchronous entries: handwritten symbols that nothing calls
(exception, interrupt and trap vectors). Entries the policy names `user_traps`
are taken only from user mode on the separate TSS.RSP0 stack; all others can
interrupt any kernel code. Interrupts are enabled only in functions containing
STI. With a 48-byte CPU frame (including an error code), the checked bounds are

    peak(entry) + max(48 + peak(kernel-mode entry))            <= limit
    retained(entry -> STI window) + max(48 + peak(any entry))   <= limit
    48 + peak(user trap)                                        <= limit

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
TERMINAL = frozenset("ud2 iretq iret iretl sysretq sysexit lretq lret".split())
PREFIXES = frozenset("rep repz repe repnz repne lock notrack bnd".split())
QUOTED = r'"(?:[^"\\]|\\.)*"'


class CheckError(ValueError):
    pass


def need(condition, message):
    if not condition:
        raise CheckError(message)


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


def compiler_facts(paths):
    """Compiler frames, call edges, signatures and separate GCC alias relations."""
    frames, edges, signatures, aliases = {}, {}, {}, {}
    for path in map(Path, paths):
        if path.name.endswith(".stack.json"):
            document = json.loads(path.read_text())
            need(document.get("version") in (1, 2), f"{path}: unknown Aurora stack-fact version")
            for name, fact in document["functions"].items():
                local = fact["local_bytes"]
                need(type(local) is int and local >= 8, f"{path}: invalid frame for {name}")
                frames[name] = max(local, frames.get(name, 0))
                for callee, live in fact["calls"].items():
                    need(type(live) is int and 8 <= live <= local, f"{path}: invalid live bytes {name}->{callee}")
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
    return frames, edges, signatures, aliases


class Image:
    def __init__(self, path, facts, policy, user):
        self.path, self.user = Path(path), user
        self.elf = Elf(path)
        self.code = disassemble(path)
        self.frames, self.edges, self.signatures, aliases = compiler_facts(facts)
        self.callbacks = [entry.partition("=")[::2] for entry in policy.get("callbacks", [])]
        self.user_traps = policy.get("user_traps", [])
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

    def function(self, address):
        if address not in self.functions:
            if address in self.compiled:
                self.functions[address] = self.compiled_function(address)
            else:
                self.functions[address] = self.handwritten_function(address)
        return self.functions[address]

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
        return dict(local=frame + pushf, calls=[(t, live + pushf) for t, live in declared.items()])

    def handwritten_function(self, address):
        """Abstract interpretation of stack depth over the handwritten CFG."""
        end = self.extent[address]
        states = {address: (0, None, False)}  # depth, frame-pointer depth, switched stack
        queue = deque([address])
        peak, calls = 8, {}
        name = self.describe(address)
        need(address in self.code, self.where(f"{name} does not start with an instruction"))

        def schedule(target, state):
            need(target in self.code, self.where(f"{name} branches into a non-instruction"))
            previous = states.setdefault(target, state)
            if previous is state:
                queue.append(target)
            need(previous == state, self.where(f"inconsistent stack depth at a join in {name}"))

        def transfer(target, live):
            """Leave this symbol; the interior of other assembly becomes its own fragment."""
            if target not in self.extent:
                owner = next((a for a in self.handwritten if a < target < self.extent[a]), None)
                need(
                    owner is not None and target in self.code,
                    self.where(f"{name} enters the interior of {self.describe(target)}"),
                )
                self.handwritten.add(target)
                self.extent[target] = self.extent[owner]
                self.label[target] = self.label[owner] + "+" + hex(target - owner)
            calls[target] = max(calls.get(target, 0), live)

        while queue:
            at = queue.popleft()
            depth, frame, switched = states[at]
            size, op, args = self.code[at]
            following = at + size
            parts = operands(args)
            destination = parts[-1] if parts else ""
            if op in TERMINAL:
                continue
            if op == "sti":
                self.windows.add(address)
            if op.startswith("push"):
                need(not op.startswith("pushw") and op != "pusha", self.where(f"narrow push in {name}"))
                depth += 8
            elif op.startswith("pop"):
                need(destination not in STACK_REGISTERS, self.where(f"pop into %rsp in {name}"))
                depth -= 8
                if destination in FRAME_REGISTERS:
                    frame = None
            elif op == "leave":
                need(frame is not None, self.where(f"leave without a known frame in {name}"))
                depth, frame = frame - 8, None
            elif op == "enter":
                raise CheckError(self.where(f"enter is unsupported in {name}"))
            elif op in ("ret", "retq"):
                need(switched or depth == 0, self.where(f"unbalanced return in {name}"))
                continue
            elif op == "call":
                target = direct_target(args)
                if target is None and self.user:
                    continue  # User hostile-probe fixtures; the user stack has its own guard page.
                need(target is not None, self.where(f"indirect call in handwritten {name}"))
                transfer(target, 8 + depth)
                if following >= end:
                    continue  # A final call does not return (fail-stop paths).
            elif op == "jmp" or op in BRANCHES:
                target = direct_target(args)
                if target is None and self.user:
                    continue  # User hostile-probe fixtures; the user stack has its own guard page.
                need(target is not None, self.where(f"indirect jump in handwritten {name}"))
                if address <= target < end:
                    schedule(target, (depth, frame, switched))
                else:
                    transfer(target, depth)
                if op == "jmp":
                    continue
            elif destination in STACK_REGISTERS:
                value = re.fullmatch(r"\$(0x[0-9a-f]+|[0-9]+)", parts[0]) if len(parts) == 2 else None
                if op in ("add", "sub") and value:
                    depth += int(value[1], 0) if op == "sub" else -int(value[1], 0)
                elif op == "and" and value and int(value[1], 0) >= 0xFFFFFFFFFFFFF000:
                    depth += 0xFFFFFFFFFFFFFFFF - int(value[1], 0)  # Worst-case downward alignment.
                elif op == "lea" and re.fullmatch(r"(-?0x[0-9a-f]+|-?[0-9]+)?\(%rsp\)", parts[0]):
                    depth -= int(parts[0].split("(")[0] or "0", 0)
                elif op in ("mov", "movq", "lea", "xchg"):
                    depth, frame, switched = 0, None, True  # Stack switch: count from its new top.
                else:
                    raise CheckError(self.where(f"unknown stack adjustment {op} {args} in {name}"))
            elif op in ("mov", "movq") and args == "%rsp,%rbp":
                frame = depth
            elif destination in FRAME_REGISTERS and op not in ("cmp", "test", "cmpq", "testq", "bt"):
                frame = None
            need(depth <= 1 << 20, self.where(f"runaway stack depth in {name}"))
            peak = max(peak, 8 + depth)
            if following >= end:
                transfer(following, depth)  # Falls through into the next symbol.
            else:
                schedule(following, (depth, frame, switched))
        return dict(local=peak, calls=list(calls.items()))

    def peak(self, address, path=()):
        need(address not in path, self.where("call cycle " + " -> ".join(map(self.describe, (*path, address)))))
        if address not in self.memo:
            body = self.function(address)
            best = (body["local"], [address])
            for target, live in body["calls"]:
                child = self.peak(target, (*path, address))
                if live + child[0] > best[0]:
                    best = (live + child[0], [address] + child[1])
            self.memo[address] = best
        return self.memo[address]

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

    def check(self, limit):
        entry = self.elf.entry
        need(entry in self.extent, self.where(f"no function at the ELF entry {entry:#x}"))
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
        called = self.closure([t for a in others for t, _ in self.function(a)["calls"]])
        entries = [a for a in others if a in self.handwritten and a not in called]
        trap = {a for a in entries if any(fnmatch(self.label[a], pattern) for pattern in self.user_traps)}

        def worst(roots):
            return max(((CPU_FRAME + self.peak(a)[0], self.peak(a)[1]) for a in roots), default=(0, []))

        kernel, any_entry = worst(set(entries) - trap), worst(entries)
        total = normal[0] + kernel[0]
        need(
            total <= limit,
            self.where(
                f"stack {normal[0]} + interrupt {kernel[0]} = {total} exceeds {limit}; "
                f"{self.chain(normal[1])}; interrupt {self.chain(kernel[1])}"
            ),
        )
        for address in trap:
            need(
                CPU_FRAME + self.peak(address)[0] <= limit,
                self.where(f"user trap {self.chain(self.peak(address)[1])} exceeds {limit}"),
            )
        result.update(interrupt=kernel[0], interrupt_path=self.chain(kernel[1]), user_trap=worst(trap)[0])
        live = {name for a in self.closure([entry, *entries]) for name in self.address_names.get(a, [self.label[a]])}
        missing = sorted(set(self.reachable) - live)
        need(not missing, self.where(f"policy entry points never called: {missing}"))
        for window in sorted(self.windows & reached):
            retained = self.retained(entry, window)
            combined = retained[0] + any_entry[0]
            need(
                combined <= limit,
                self.where(
                    f"interrupt window {self.chain(retained[1])} + {self.chain(any_entry[1])}"
                    f" = {combined} exceeds {limit}"
                ),
            )
            total = max(total, combined)
        return dict(result, total=total, windows=len(self.windows & reached))


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
