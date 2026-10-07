# Source style

Use four spaces, a 120-column target, one statement per line and descriptive
names. Break long calls and collections across lines. Group related operations
with blank lines; a smaller line count is not a readability goal. Make recipes
keep their required tabs.

## Host tools

Python uses Ruff 0.16.7; bootstrap C++ uses clang-format 22.1.8. Exact versions
and repository configuration keep editor and command-line results consistent.
These tools do not implement an Aurora formatter, linter or language server.
Never pass `.au` files to clang-format or format source strings as Python.

Optional installation into a disposable virtual environment, using PyPI wheels:

```sh
python3 -m venv /path/to/aurora-style-tools
/path/to/aurora-style-tools/bin/python -m pip install --only-binary=:all: --no-deps --no-cache-dir -r requirements-style.txt
export PATH="/path/to/aurora-style-tools/bin:$PATH"
```

The build and test commands do not install these tools. A matching existing
installation is sufficient; no system-wide package or editor setting is needed.
Review version upgrades as their own changes because formatting can change.

From the repository root, check or format explicitly selected files:

```sh
python3 -B scripts/style.py check scripts/package_native_runner.py tests/compiler/package_graph.py
python3 -B scripts/style.py format scripts/package_native_runner.py tests/compiler/package_graph.py
python3 -B scripts/style.py check compiler/lexer.hpp compiler/parser.hpp
```

The entrypoint checks exact tool versions, rejects non-host files, and delegates
to the real formatters. Check mode never rewrites source; format mode runs the
formatter and then reports remaining Python style violations. Neither runs
semantic lint fixes, import sorting, builds or tests. Direct editor integrations
should use the same pinned tools and repository configuration.

## Review and exceptions

Format each touched host file. Keep mechanical formatting separate from behavior
changes where practical, and rerun affected tests after combining them. The
initial rollout does not claim the entire historical tree already passes.

Ruff formatting is best-effort at 120 columns; its E501 check catches remaining
long lines except documented cases such as an unbroken word or trailing URL.
Long literal fixtures often need manual adjacent-string wrapping that preserves
their exact value. Do not reflow generated source, snapshots or protocol bytes.
Rare required exceptions need a nearby reason and the narrowest suppression;
do not exclude a whole file to hide ordinary long expressions. C++ formatting
also needs review for unsplittable tokens and exact-layout fixtures.

The [Aurora language-tooling plan](language-tooling.md) describes the compiler
work needed for native `.au` support.

Tool references: [Ruff configuration](https://docs.astral.sh/ruff/configuration/),
[line-length behavior](https://docs.astral.sh/ruff/rules/line-too-long/), and
[clang-format options](https://releases.llvm.org/22.1.0/tools/clang/docs/ClangFormatStyleOptions.html).
