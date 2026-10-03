#!/usr/bin/env python3
"""Bounded differential tests. No compiler implementation is imported."""
import argparse
from collections import Counter
import hashlib
import itertools
import json
from pathlib import Path
import platform
import random
import resource
import shutil
import signal
import struct
import subprocess
import tempfile

MIN, MAX = -(1 << 63), (1 << 63) - 1


class Trap(Exception):
    pass


def checked(value):
    if not MIN <= value <= MAX:
        raise Trap('overflow')
    return value


def evaluate(node, env):
    """Mathematical integers, explicit bounds, left-to-right evaluation."""
    tag, *args = node
    if tag == 'lit':
        return args[0]
    if tag == 'var':
        return env[args[0]]
    if tag == 'get':
        index = evaluate(args[1], env)
        array = env[args[0]]
        if not 0 <= index < len(array):
            raise Trap('bounds')
        return array[index]
    left = evaluate(args[0], env)
    if tag == 'neg':
        return checked(-left)
    if tag == 'not':
        return not left
    right = evaluate(args[1], env)
    if tag == '+':
        return checked(left + right)
    if tag == '-':
        return checked(left - right)
    if tag == '*':
        return checked(left * right)
    return {'==': lambda: left == right, '!=': lambda: left != right,
            '<': lambda: left < right, '>': lambda: left > right,
            '<=': lambda: left <= right, '>=': lambda: left >= right}[tag]()


def expr(node):
    tag, *args = node
    if tag == 'lit':
        return str(args[0]).lower()
    if tag == 'var':
        return args[0]
    if tag == 'get':
        return f'{args[0]}[{expr(args[1])}]'
    if tag in ('neg', 'not'):
        return f"({'-' if tag == 'neg' else '!'}({expr(args[0])}))"
    return f'({expr(args[0])} {tag} {expr(args[1])})'


def execute(statements, env):
    for statement in statements:
        tag, *args = statement
        if tag == 'set':
            env[args[0]] = evaluate(args[1], env)
        elif tag == 'store':
            index = evaluate(args[1], env)
            if not 0 <= index < len(env[args[0]]):
                raise Trap('bounds')
            value = evaluate(args[2], env)
            env[args[0]][index] = value
        elif tag == 'if':
            execute(args[1] if evaluate(args[0], env) else args[2], env)
        elif tag == 'loop':
            # Generator supplies literal bounds in [0, 8]; no arbitrary loops.
            env['i'] = 0
            while env['i'] < args[0]:
                execute(args[1], env)
                env['i'] += 1
        else:
            raise AssertionError(tag)


def render(statements):
    lines = []
    for tag, *args in statements:
        if tag == 'set':
            lines.append(f'{args[0]} = {expr(args[1])};')
        elif tag == 'store':
            lines.append(f'{args[0]}[{expr(args[1])}] = {expr(args[2])};')
        elif tag == 'if':
            lines.append(f'if ({expr(args[0])}) {{ {render(args[1])} }} else {{ {render(args[2])} }}')
        elif tag == 'loop':
            lines.append(f'i = 0; while (i < {args[0]}) {{ {render(args[1])} i = i + 1; }}')
    return '\n'.join(lines)


def source(body):
    return 'module semantics; auto test() -> i64 {\n' + body + '\n}\n'


def expected_expr(node, env=None):
    try:
        return {'value': evaluate(node, env or {})}
    except Trap as trap:
        return {'trap': str(trap)}


def numeric(rng, depth, n, edges=False):
    if depth == 0 or rng.randrange(4) == 0:
        leaves = [('lit', rng.randint(-20, 20)), ('var', 'x'),
                  ('get', 'a', ('lit', rng.randrange(n)))]
        if edges:
            leaves += [('lit', value) for value in (MIN, MAX, -1, 0, 1)]
        return rng.choice(leaves)
    if rng.randrange(5) == 0:
        return ('neg', numeric(rng, depth - 1, n, edges))
    return (rng.choice(['+', '-', '*']), numeric(rng, depth - 1, n, edges),
            numeric(rng, depth - 1, n, edges))


def generated(rng, number):
    n = rng.randint(1, 8)
    array = [rng.randint(-20, 20) for _ in range(n)]
    x = rng.randint(-20, 20)
    statements = []
    for _ in range(rng.randint(1, 4)):
        condition = (rng.choice(['==', '!=', '<', '>', '<=', '>=']),
                     numeric(rng, 2, n), numeric(rng, 2, n))
        if rng.randrange(2):
            condition = ('not', condition)
        statements.append(('if', condition,
                           [('set', 'x', numeric(rng, 3, n))],
                           [('store', 'a', ('lit', rng.randrange(n)), numeric(rng, 3, n))]))
    statements.append(('loop', n, [('set', 'x', ('+', ('var', 'x'), ('get', 'a', ('var', 'i')))),
                                   ('store', 'a', ('var', 'i'), ('-', ('var', 'x'), ('var', 'i')))]))
    # Copy isolation contributes directly to every result.
    result = ('+', numeric(rng, 3, n, number % 3 == 0), ('get', 'snapshot', ('lit', rng.randrange(n))))
    if number % 5 == 0:
        result = ('get', 'a', ('lit', rng.choice([-1, n, MAX, MIN])))
    env = {'a': array[:], 'snapshot': array[:], 'x': x, 'i': 0}
    try:
        execute(statements, env)
        expected = expected_expr(result, env)
    except Trap as trap:
        expected = {'trap': str(trap)}
    body = (f'array<i64, {n}> a = {{{", ".join(map(str, array))}}};\n'
            f'const array<i64, {n}> snapshot = a; i64 x = {x}; i64 i = 0;\n'
            + render(statements) + '\nreturn ' + expr(result) + ';')
    return source(body), expected


def fixed_cases():
    values = [MIN, MIN + 1, -3037000500, -1, 0, 1, 3037000500, MAX - 1, MAX]
    for op in ['+', '-', '*']:
        for a, b in itertools.product(values, repeat=2):
            node = (op, ('lit', a), ('lit', b))
            yield f'boundary-{op}-{a}-{b}', source('return ' + expr(node) + ';'), expected_expr(node)
    for value in values:
        node = ('neg', ('lit', value))
        yield f'neg-{value}', source('return ' + expr(node) + ';'), expected_expr(node)
    for n in (1, 2, 8):
        for index in (MIN, -1, 0, n-1, n, MAX):
            for store in (False, True):
                body = f'array<i64, {n}> a = {{{", ".join(str(i) for i in range(n))}}}; '
                body += f'a[{index}] = 42; return a[{index}];' if store else f'return a[{index}];'
                expectation = {'trap': 'bounds'} if not 0 <= index < n else {'value': 42 if store else index}
                yield f'bounds-{n}-{index}-{store}', source(body), expectation
    yield 'bool-array-loop', source('array<bool, 3> a = {true, false, true}; i64 i = 0; i64 x = 0; while (i < 3) { if (!a[i]) { x = x + 2; } else { x = x + 1; } a[i] = !a[i]; i = i + 1; } if (a[1]) { return x; } return -1;'), {'value': 4}


def ownership_cases():
    """Exhaust all 4^3 operation traces with lexical borrow scope release."""
    for trace in itertools.product(('read', 'shared', 'exclusive', 'move'), repeat=3):
        live, shared, exclusive, valid = True, 0, False, True
        lines = ['own<i64> owner = own(42);']
        for index, action in enumerate(trace):
            legal = live and (not exclusive if action in ('read', 'shared') else not exclusive and not shared)
            valid = valid and legal
            if action == 'read':
                lines.append(f'i64 value{index} = read(owner);')
            elif action == 'shared':
                lines.append(f'ref<i64> reference{index} = borrow(owner);')
                shared += 1
            elif action == 'exclusive':
                lines.append(f'mutref<i64> reference{index} = borrow_mut(owner);')
                exclusive = True
            else:
                lines.append(f'own<i64> moved{index} = move(owner);')
                live = False
        yield 'ownership-' + '-'.join(trace), source(' '.join(lines) + ' return 42;'), {'value': 42} if valid else {'reject': True}
    for borrow in ('ref<i64> r = borrow(owner);', 'mutref<i64> r = borrow_mut(owner);'):
        yield 'scope-release-' + borrow.split()[0], source('own<i64> owner = own(42); { ' + borrow + ' } own<i64> moved = move(owner); return read(moved);'), {'value': 42}
    for condition in ('true', 'false'):
        yield 'loop-backedge-' + condition, source(f'own<i64> owner = own(42); while ({condition}) {{ own<i64> moved = move(owner); }} return 0;'), {'reject': True}
        yield 'returning-move-' + condition, source(f'own<i64> owner = own(42); while ({condition}) {{ own<i64> moved = move(owner); return read(moved); }} return read(owner);'), {'value': 42}


def invalid_cases():
    bodies = ['bool x = 3; return 0;', 'i64 x = true; return x;',
              'if (1) { return 0; } return 1;', 'while (0) {} return 0;',
              'array<i64, 1> a = {0}; return a[false];',
              'array<bool, 1> a = {false}; a[0] = 1; return 0;',
              'const array<i64, 1> a = {0}; a[0] = 1; return 0;',
              'array<i64, 0> a = {}; return 0;',
              'array<i64, 4097> a = {}; return 0;',
              'array<i64, 2> a = {1}; return 0;',
              'return 9223372036854775808;', 'return -9223372036854775809;',
              'i64 x; return x;', 'return missing;', 'return 0; return 1;']
    for index, body in enumerate(bodies):
        yield f'invalid-type-{index}', source(body), {'reject': True}
    complete = source('array<i64, 2> a = {1, 2}; i64 x = 0; while (x < 2) { x = x + 1; } return a[1];').rstrip()
    # Every proper character prefix lacks a complete module/function.
    for index in range(len(complete)):
        yield f'truncated-{index}', complete[:index], {'reject': True}
    for index, token in enumerate(['@', '#', '\x00', '"', "'", '`', '\\', '/*', '/* unfinished']):
        yield f'malformed-token-{index}', source(token + ' return 0;'), {'reject': True}


def limits():
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_CPU, (3, 3))
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024,) * 2)
    resource.setrlimit(resource.RLIMIT_FSIZE, (8 * 1024 * 1024,) * 2)


def command(args):
    return subprocess.run(list(map(str, args)), capture_output=True, timeout=5, preexec_fn=limits)


def must_run(args):
    result = command(args)
    if result.returncode:
        raise AssertionError(f'tool failure {args}: status {result.returncode}, {result.stderr.decode(errors="replace")}')
    return result


BRIDGE = '''.text
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
    jne .Lfailed
    xorq %rdi, %rdi
    jmp .Lexit
.Lfailed:
    movq $97, %rdi
.Lexit:
    movq $60, %rax
    syscall
.section .note.GNU-stack,"",@progbits
'''


def check(compiler, directory, code, expected):
    src, asm = directory / 'input.au', directory / 'output.s'
    asm.unlink(missing_ok=True)
    src.write_text(code)
    result = command([compiler, src, '-o', asm])
    if 'reject' in expected:
        if not (result.returncode > 0 and result.stderr.strip() and not asm.exists()):
            raise AssertionError(f'expected clean rejection with diagnostic/no assembly, got status={result.returncode}, stderr={result.stderr!r}, assembly={asm.exists()}')
        return 'rejected'
    if result.returncode:
        raise AssertionError(f'expected compilation, got status={result.returncode}, stderr={result.stderr!r}')
    must_run(['as', '--64', asm, '-o', directory / 'output.o'])
    must_run(['ld', '-o', directory / 'program', directory / 'entry.o', directory / 'output.o'])
    result = command([directory / 'program'])
    if 'trap' in expected:
        if result.returncode != -signal.SIGILL or result.stdout:
            raise AssertionError(f'expected SIGILL ({expected["trap"]}), got status={result.returncode}, stdout={result.stdout!r}')
        return expected['trap']
    observed = struct.unpack('<q', result.stdout)[0] if len(result.stdout) == 8 else None
    if result.returncode != 0 or observed != expected['value']:
        raise AssertionError(f'expected value={expected["value"]}, observed value={observed}, status={result.returncode}, stdout={result.stdout!r}')
    return 'value'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('compiler', type=Path)
    parser.add_argument('--seed', type=int, default=20261002)
    parser.add_argument('--cases', type=int, default=128, help='random cases, plus fixed/model/invalid corpus (0..10000)')
    parser.add_argument('--failure-dir', type=Path, default=Path('build/semantics-failure'))
    args = parser.parse_args()
    if not 0 <= args.cases <= 10000:
        parser.error('--cases must be in [0, 10000]')
    if platform.system() != 'Linux' or platform.machine() not in ('x86_64', 'AMD64'):
        parser.error('native runner requires x86-64 Linux')
    rng, counts = random.Random(args.seed), Counter()
    with tempfile.TemporaryDirectory(prefix='aurora-semantics-') as temp:
        directory = Path(temp)
        compiler = directory / 'aurorac'
        shutil.copy2(args.compiler.resolve(), compiler)  # Pin executable during concurrent rebuilds.
        digest = hashlib.sha256(compiler.read_bytes()).hexdigest()
        print(f'seed={args.seed} generated={args.cases} compiler_sha256={digest}', flush=True)
        (directory / 'entry.s').write_text(BRIDGE)
        must_run(['as', '--64', directory / 'entry.s', '-o', directory / 'entry.o'])
        cases = itertools.chain(fixed_cases(), ownership_cases(), invalid_cases(),
                                ((f'generated-{i}', *generated(rng, i)) for i in range(args.cases)))
        for number, (name, code, expected) in enumerate(cases):
            try:
                counts[check(compiler, directory, code, expected)] += 1
            except (AssertionError, subprocess.TimeoutExpired) as error:
                args.failure_dir.mkdir(parents=True, exist_ok=True)
                (args.failure_dir / 'repro.au').write_text(code)
                report = dict(seed=args.seed, name=name, ordinal=number, expected=expected,
                              compiler_sha256=digest, error=str(error))
                (args.failure_dir / 'failure.json').write_text(json.dumps(report, indent=2) + '\n')
                print('FAIL ' + json.dumps(report), flush=True)
                print(f'reproducer: {args.failure_dir / "repro.au"}')
                return 1
        print(f'PASS {sum(counts.values())} cases ' + json.dumps(dict(counts), sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
