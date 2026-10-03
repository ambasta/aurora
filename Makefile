# Bootstrap commands share the image/output directory; serialize their execution.
.NOTPARALLEL:
.PHONY: all compiler kernel test test-compiler test-image test-kernel test-semantics test-semantics-stress smoke smoke-fault smoke-page-fault smoke-scheduling smoke-all

all: compiler kernel

compiler:
	$(MAKE) -C compiler

kernel: compiler
	./scripts/kernel-build.sh

test-compiler: compiler
	$(MAKE) -C compiler test

test-image: kernel
	python3 tests/kernel-image.py

test-kernel:
	./scripts/kernel-tests.sh

test-semantics: compiler
	python3 tests/semantics/test_runner.py
	python3 tests/semantics/run.py build/aurorac

test-semantics-stress: compiler
	python3 tests/semantics/run.py build/aurorac --seed 404 --cases 1024

test: test-compiler test-image test-kernel test-semantics

# QEMU is intentionally a separate acceptance gate, never silently skipped.
smoke:
	./scripts/kernel-smoke.sh

smoke-fault:
	./scripts/kernel-smoke.sh --fault

smoke-page-fault:
	./scripts/kernel-smoke.sh --page-fault

smoke-scheduling:
	./scripts/kernel-scheduling-smoke.sh

smoke-all:
	./scripts/kernel-protection-smoke.sh
	./scripts/kernel-scheduling-smoke.sh
