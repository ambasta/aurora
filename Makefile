# Bootstrap commands share the image/output directory; serialize their execution.
.NOTPARALLEL:
.PHONY: all compiler kernel test test-compiler test-image test-kernel smoke smoke-fault smoke-page-fault

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

test: test-compiler test-image test-kernel

# QEMU is intentionally a separate acceptance gate, never silently skipped.
smoke:
	./scripts/kernel-smoke.sh

smoke-fault:
	./scripts/kernel-smoke.sh --fault

smoke-page-fault:
	./scripts/kernel-smoke.sh --page-fault
