# Bootstrap commands share the image/output directory; serialize their execution.
.NOTPARALLEL:
.PHONY: all compiler kernel test test-compiler test-image test-kernel test-semantics test-semantics-stress smoke smoke-fault smoke-page-fault smoke-scheduling smoke-uefi test-uefi test-acpi test-division smoke-acpi smoke-division smoke-all

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

test-uefi:
	./scripts/kernel-uefi-tests.sh

test-acpi:
	./scripts/kernel-acpi-tests.sh

test-division:
	./scripts/kernel-division-tests.sh

test: test-compiler test-image test-kernel test-uefi test-acpi test-division test-semantics

# QEMU is intentionally a separate acceptance gate, never silently skipped.
smoke:
	./scripts/kernel-smoke.sh

smoke-fault:
	./scripts/kernel-smoke.sh --fault

smoke-page-fault:
	./scripts/kernel-smoke.sh --page-fault

smoke-scheduling:
	./scripts/kernel-scheduling-smoke.sh

smoke-uefi:
	./scripts/kernel-uefi-all.sh

smoke-acpi:
	./scripts/kernel-acpi-all.sh

smoke-division:
	./scripts/kernel-division-smoke.sh

smoke-all:
	./scripts/kernel-protection-smoke.sh
	./scripts/kernel-scheduling-smoke.sh
	./scripts/kernel-uefi-all.sh
	./scripts/kernel-acpi-all.sh
	./scripts/kernel-division-smoke.sh
