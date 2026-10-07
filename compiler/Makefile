# Test goals enter one controlled compiler run. Ordinary builds and compiler-free
# focused gates retain their existing behavior. A dry run only prints this route.
override .DEFAULT_GOAL := all
ifneq ($(strip $(foreach name,MAKECMDGOALS CURDIR MAKEFILE_LIST,$(if $(filter command,$(origin $(name))),$(name)))),)
$(error Make goal, directory, and makefile-list overrides are unsupported)
endif
override _AURORA_TEST_GOALS := $(filter test test-modules test-storage test-utf8 test-utf8-encoding test-xfs-geometry test-xfs-root test-utf8-range test-utf8-lines test-function-overloads test-readonly-windows test-short-circuit test-token-scan,$(MAKECMDGOALS))
override _AURORA_DISPATCH :=

# Export supplied controls before defaults are introduced in the inner graph.
# In particular, default path aliases must not select a different compiler.
override _AURORA_USER_CONTROLS := CXX CXXFLAGS IR_TEST_CXXFLAGS IR_TEST_BUILD_PREFIX OUT AURORAC \
    ACCEPTANCE_COMPILER ACCEPTANCE_COMPILER_SHA256 PACKAGE_IDENTITY_COMPILER \
    PACKAGE_IDENTITY_COMPILER_SHA256 PACKAGE_IDENTITY_TEST_FLAGS PACKAGE_IDENTITY_CAP_MIB \
    PACKAGE_MANIFEST_COMPILER PACKAGE_MANIFEST_COMPILER_SHA256 PACKAGE_MANIFEST_TEST_FLAGS \
    PACKAGE_MANIFEST_CAP_MIB PACKAGE_GRAPH_COMPILER PACKAGE_GRAPH_COMPILER_SHA256 PACKAGE_GRAPH_TEST_FLAGS \
    PACKAGE_GRAPH_CAP_MIB KERNEL_BUDGET_COMPILER KERNEL_BUDGET_COMPILER_SHA256 KERNEL_BUDGET_CAP_MIB ROUND_ROBIN_TEST_CAP_MIB \
    IPC_TRANSACTION_COMPILER IPC_TRANSACTION_COMPILER_SHA256 IPC_TRANSACTION_CAP_MIB \
    UTF8_TEST_FLAGS UTF8_LINES_TEST_FLAGS UTF8_LINES_COMPILER_SHA256 UTF8_LINES_ARTIFACT_PARENT \
    UTF8_RANGE_TEST_FLAGS UTF8_RANGE_COMPILER_SHA256 UTF8_RANGE_ARTIFACT_PARENT XFS_GEOMETRY_TEST_FLAGS \
    XFS_ROOT_TEST_FLAGS XFS_ROOT_API_TEST_FLAGS XFS_ROOT_REPO XFS_ROOT_FIXTURES XFS_ROOT_ARTIFACT_PARENT \
    XFS_ROOT_COMPILER_SHA256 SANITIZE ASAN_OPTIONS UBSAN_OPTIONS
# Raw user flags are data: reject Make expansion before export can evaluate them.
# Diagnostics contain control names only. The Python policy validates full grammar.
override define _AURORA_RAW_FLAG_NEWLINE


endef
override _AURORA_RAW_FLAG_CONTROLS := CXX CXXFLAGS IR_TEST_CXXFLAGS
override _AURORA_BAD_RAW_FLAGS := $(foreach name,$(_AURORA_RAW_FLAG_CONTROLS),$(if $(filter undefined default,$(origin $(name))),,$(if $(findstring $$,$(value $(name))),$(name),$(if $(findstring `,$(value $(name))),$(name),$(if $(findstring %,$(subst $(_AURORA_RAW_FLAG_NEWLINE),%,$(value $(name)))),$(name))))))
ifneq ($(strip $(_AURORA_BAD_RAW_FLAGS)),)
$(error unsupported raw flag syntax in controls: $(_AURORA_BAD_RAW_FLAGS))
endif

# Inspect raw cap data before export can expand a Make expression. Never echo it.
override _AURORA_CAP_CONTROLS := PACKAGE_IDENTITY_CAP_MIB PACKAGE_MANIFEST_CAP_MIB PACKAGE_GRAPH_CAP_MIB KERNEL_BUDGET_CAP_MIB ROUND_ROBIN_TEST_CAP_MIB IPC_TRANSACTION_CAP_MIB
override _AURORA_CAP_EMPTY :=
override _AURORA_CAP_SPACE := $(_AURORA_CAP_EMPTY) $(_AURORA_CAP_EMPTY)
override _AURORA_CAP_TAB := $(_AURORA_CAP_EMPTY)	$(_AURORA_CAP_EMPTY)
override _AURORA_BAD_CAPS := $(foreach name,$(_AURORA_CAP_CONTROLS),$(if $(filter undefined default,$(origin $(name))),,$(if $(value $(name)),$(if $(subst 9,,$(subst 8,,$(subst 7,,$(subst 6,,$(subst 5,,$(subst 4,,$(subst 3,,$(subst 2,,$(subst 1,,$(subst 0,,$(subst $(_AURORA_CAP_TAB),x,$(subst $(_AURORA_CAP_SPACE),x,$(value $(name)))))))))))))),$(name)),$(name))))
ifneq ($(strip $(_AURORA_BAD_CAPS)),)
$(error cap overrides must be unsigned decimal integers; invalid controls: $(_AURORA_BAD_CAPS))
endif

$(foreach name,$(_AURORA_USER_CONTROLS),$(if $(filter undefined default,$(origin $(name))),,$(eval export $(name))))

ifneq ($(strip $(_AURORA_TEST_GOALS) $(AURORA_TEST_CONTEXT)),)
# These modes can skip a rejecting wrapper or turn a failure into success.
override _AURORA_SHORT_MAKE_FLAGS := $(foreach name,MAKEFLAGS MFLAGS,$(if $(filter --%,$(firstword $($(name)))),,$(firstword $($(name)))))
ifneq ($(strip $(foreach flag,i q t e,$(findstring $(flag),$(_AURORA_SHORT_MAKE_FLAGS)))),)
$(error supervised tests do not support Make -i, -q, -t, or -e)
endif
ifneq ($(filter --eval% --file% --makefile% --old-file% --assume-old% --what-if% --new-file% --assume-new%,$(MAKEFLAGS) $(MFLAGS) $(GNUMAKEFLAGS)),)
$(error supervised tests do not support Make recipe or dependency overrides)
endif
ifneq ($(strip $(MAKEFILES)),)
$(error supervised tests do not support MAKEFILES)
endif
ifneq ($(words $(MAKEFILE_LIST)),1)
$(error supervised tests require this Makefile without additional makefiles)
endif
ifneq ($(strip $(foreach name,MAKEFLAGS MFLAGS GNUMAKEFLAGS MAKEOVERRIDES MAKEFILES MAKE_COMMAND,$(if $(filter command,$(origin $(name))),$(name)))),)
$(error supervised tests do not support command-line Make control overrides)
endif
ifneq ($(words $(SHELL)),1)
$(error supervised tests require one standard SHELL executable)
endif
ifeq ($(filter /bin/sh /bin/bash /usr/bin/sh /usr/bin/bash,$(SHELL)),)
$(error supervised tests require a standard sh or bash SHELL)
endif
ifneq ($(.SHELLFLAGS),-c)
$(error supervised tests do not support custom .SHELLFLAGS)
endif
ifneq ($(words $(MAKE)),1)
$(error supervised tests require one MAKE executable)
endif
ifeq ($(filter $(MAKE_COMMAND) make /usr/bin/make /bin/make,$(MAKE)),)
$(error supervised tests do not support a custom MAKE command)
endif
ifeq ($(strip $(AURORA_TEST_CONTEXT)),)
ifneq ($(words $(MAKECMDGOALS)),1)
$(error invoke one compiler-consuming test goal at a time; mixed goals are unsupported)
endif
override _AURORA_DISPATCH := yes
endif
endif

ifeq ($(_AURORA_DISPATCH),yes)
.PHONY: $(_AURORA_TEST_GOALS)
$(_AURORA_TEST_GOALS):
	python3 -B ../scripts/compiler_contract.py run --repo-root "$(abspath ..)" --entry compiler --goal "$@"
else
# The validated receipt, not a boolean flag, authorizes the sealed inner graph.
# Declare this prerequisite first, including on host-only aggregate prerequisites,
# so context rejection happens before any workload creates artifacts.
ifneq ($(strip $(AURORA_TEST_CONTEXT)),)
.NOTPARALLEL:
export AURORA_TEST_CONTEXT AURORA_TEST_MODE AURORA_TEST_COMPILER AURORA_TEST_IDENTITY_ARGS
export AURORAC OUT PACKAGE_IDENTITY_COMPILER PACKAGE_MANIFEST_COMPILER PACKAGE_GRAPH_COMPILER KERNEL_BUDGET_COMPILER
.PHONY: aurora-test-context
all test test-modules test-storage test-initialization-facts test-utf8 test-utf8-encoding \
    test-xfs-geometry test-xfs-root test-utf8-range test-utf8-lines test-function-overloads \
    test-readonly-windows test-short-circuit test-token-scan: aurora-test-context
aurora-test-context:
	python3 -B ../scripts/compiler_contract.py check --repo-root "$(abspath ..)" --context "$$AURORA_TEST_CONTEXT"
endif

CXX ?= g++
CXXFLAGS ?= -std=c++23 -O2 -Wall -Wextra -Wpedantic -Werror
IR_TEST_CXXFLAGS ?= $(CXXFLAGS)
IR_TEST_BUILD_PREFIX ?=
UTF8_TEST_FLAGS ?=
UTF8_LINES_TEST_FLAGS ?=
UTF8_LINES_COMPILER_SHA256 ?=
UTF8_LINES_ARTIFACT_PARENT ?= $(dir $(abspath $(OUT)))
UTF8_RANGE_TEST_FLAGS ?=
UTF8_RANGE_COMPILER_SHA256 ?=
UTF8_RANGE_ARTIFACT_PARENT ?= $(dir $(abspath $(OUT)))
XFS_GEOMETRY_TEST_FLAGS ?=
XFS_ROOT_TEST_FLAGS ?=
XFS_ROOT_API_TEST_FLAGS ?=
XFS_ROOT_REPO ?= ..
XFS_ROOT_FIXTURES ?=
XFS_ROOT_ARTIFACT_PARENT ?=
XFS_ROOT_COMPILER_SHA256 ?=
OUT ?= ../build/aurorac
.PHONY: all test
all: $(OUT)
ifneq ($(strip $(AURORA_TEST_CONTEXT)),)
# A sealed compiler is validated even when source timestamps are in the future.
# No source dependency or compile recipe may replace it in the inner graph.
$(OUT): aurora-test-context
else
$(OUT): main.cpp $(wildcard *.hpp)
	mkdir -p $(dir $(OUT))
	$(CXX) $(CXXFLAGS) $< -o $@
endif
test: $(OUT) test-xfs-root test-utf8-range test-utf8-lines
	$(CXX) $(CXXFLAGS) -I. ../tests/compiler/diagnostics.cpp -o $(dir $(OUT))diagnostics-tests
	python3 -B -O ../tests/compiler/diagnostics.py $(abspath $(OUT)) $(abspath $(dir $(OUT))diagnostics-tests)
	$(CXX) $(CXXFLAGS) -I. ../tests/compiler/lexer_trivia.cpp -o $(dir $(OUT))lexer-trivia-tests
	$(dir $(OUT))lexer-trivia-tests $(wildcard ../examples/*.au ../library/examples/*.au ../library/std/*.au)
	python3 ../tests/compiler/run.py $(abspath $(OUT))
	python3 ../tests/compiler/classes.py $(abspath $(OUT))
	python3 ../tests/compiler/value_calls.py $(abspath $(OUT))
	python3 ../tests/compiler/templates.py $(abspath $(OUT))
	python3 -O ../tests/compiler/function_templates.py $(abspath $(OUT))
	python3 -B -O ../tests/compiler/function_overloads.py $(abspath $(OUT))
	python3 ../tests/compiler/fixed_containers.py $(abspath $(OUT))
	python3 ../tests/compiler/composed_values.py $(abspath $(OUT))
	python3 -O ../tests/compiler/nested_values.py $(abspath $(OUT))
	python3 ../tests/compiler/decimal_values.py $(abspath $(OUT))
	python3 ../tests/compiler/enum_composition.py $(abspath $(OUT))
	python3 -O ../tests/compiler/method_values.py $(abspath $(OUT))
	python3 ../tests/compiler/integers.py $(abspath $(OUT))
	python3 ../tests/compiler/unsigned.py $(abspath $(OUT))
	python3 ../tests/compiler/u8_numeric.py $(abspath $(OUT))
	python3 ../tests/compiler/byte_codec.py $(abspath $(OUT))
	python3 -B ../tests/compiler/binary_writer.py $(abspath $(OUT))
	python3 ../tests/compiler/packed_values.py $(abspath $(OUT))
	python3 ../tests/compiler/readonly_spans.py $(abspath $(OUT))
	python3 -O ../tests/compiler/storage_binary.py $(abspath $(OUT))
	python3 -O ../tests/compiler/xfs_geometry.py $(abspath $(OUT)) $(AURORA_TEST_IDENTITY_ARGS) --mutation-controls $(XFS_GEOMETRY_TEST_FLAGS)
	python3 -O ../tests/compiler/utf8.py $(abspath $(OUT)) $(UTF8_TEST_FLAGS)
	python3 -O ../tests/compiler/utf8_encoding.py $(abspath $(OUT)) $(UTF8_TEST_FLAGS)
	python3 -O ../fixtures/xfs-offline/verify_native.py --compiler $(abspath $(OUT)) $(AURORA_TEST_IDENTITY_ARGS)
	CXX="$(CXX)" python3 ../tests/compiler/unsigned_oracle.py $(abspath $(OUT))
	CXX="$(CXX)" python3 ../tests/compiler/integer_oracle.py $(abspath $(OUT))
	$(CXX) $(CXXFLAGS) -I. ../tests/compiler/initialization_facts.cpp -o $(dir $(OUT))initialization-facts-tests
	$(dir $(OUT))initialization-facts-tests
	$(IR_TEST_BUILD_PREFIX) $(CXX) $(IR_TEST_CXXFLAGS) -I. ../tests/compiler/ir_tests.cpp -o $(dir $(OUT))ir-tests
	$(dir $(OUT))ir-tests
	CXX="$(CXX)" python3 ../tests/compiler/ir_exhaustive.py $(abspath $(dir $(OUT))ir-tests)
	$(CXX) $(CXXFLAGS) -I. ../tests/compiler/method_values_ir.cpp -o $(dir $(OUT))method-values-ir-tests
	$(dir $(OUT))method-values-ir-tests
	python3 -O ../tests/compiler/method_values_abi.py $(abspath $(dir $(OUT))method-values-ir-tests)
	python3 ../tests/modules/run.py $(abspath $(OUT))
	python3 ../tests/modules/robustness.py $(abspath $(OUT))
	$(CXX) $(CXXFLAGS) -pthread -I. ../tests/modules/host_sources_tests.cpp -o $(dir $(OUT))host-source-tests
	python3 ../tests/modules/host_sources.py $(abspath $(dir $(OUT))host-source-tests)
	$(CXX) $(CXXFLAGS) -I. ../tests/modules/host_output_tests.cpp -o $(dir $(OUT))host-output-tests
	python3 ../tests/modules/host_sources.py $(abspath $(dir $(OUT))host-output-tests)

.PHONY: test-modules
test-modules: $(OUT)
	python3 ../tests/modules/run.py $(abspath $(OUT))
	python3 ../tests/modules/robustness.py $(abspath $(OUT))
	$(CXX) $(CXXFLAGS) -pthread -I. ../tests/modules/host_sources_tests.cpp -o $(dir $(OUT))host-source-tests
	python3 ../tests/modules/host_sources.py $(abspath $(dir $(OUT))host-source-tests)
	$(CXX) $(CXXFLAGS) -I. ../tests/modules/host_output_tests.cpp -o $(dir $(OUT))host-output-tests
	python3 ../tests/modules/host_sources.py $(abspath $(dir $(OUT))host-output-tests)

.PHONY: test-storage
test-storage: $(OUT)
	python3 -O ../tests/compiler/storage_binary.py $(abspath $(OUT))
	python3 -O ../fixtures/xfs-offline/verify_native.py --compiler $(abspath $(OUT)) $(AURORA_TEST_IDENTITY_ARGS)

.PHONY: test-initialization-facts
test-initialization-facts:
	$(CXX) $(CXXFLAGS) -I. ../tests/compiler/initialization_facts.cpp -o $(dir $(OUT))initialization-facts-tests
	$(dir $(OUT))initialization-facts-tests

.PHONY: test-utf8
test-utf8: $(OUT)
	python3 -O ../tests/compiler/utf8.py $(abspath $(OUT)) $(UTF8_TEST_FLAGS)

.PHONY: test-utf8-encoding
test-utf8-encoding: $(OUT)
	python3 -O ../tests/compiler/utf8_encoding.py $(abspath $(OUT)) $(UTF8_TEST_FLAGS)

.PHONY: test-xfs-geometry
test-xfs-geometry: $(OUT)
	python3 -O ../tests/compiler/xfs_geometry.py $(abspath $(OUT)) $(AURORA_TEST_IDENTITY_ARGS) --mutation-controls $(XFS_GEOMETRY_TEST_FLAGS)

.PHONY: test-xfs-root
test-xfs-root: $(OUT)
	@set -eu; \
	compiler="$$(realpath -- "$(OUT)")"; \
	repo="$(XFS_ROOT_REPO)"; \
	fixtures="$(XFS_ROOT_FIXTURES)"; \
	if [ -z "$$fixtures" ]; then fixtures="$$repo/fixtures/xfs-root"; fi; \
	parent="$(XFS_ROOT_ARTIFACT_PARENT)"; \
	if [ -z "$$parent" ]; then parent="$$(dirname -- "$$compiler")"; fi; \
	python3 -B -c 'import pathlib,sys; roots=[pathlib.Path(s).absolute() for s in sys.argv[1:]]; bad=[p for p in roots if not p.is_dir() or any(x.is_symlink() for x in [p,*p.parents])]; sys.exit("invalid XFS root(s): "+", ".join(map(str,bad)) if bad else 0)' "$$repo" "$$fixtures" "$$parent"; \
	observed="$$(sha256sum -- "$$compiler" | cut -d ' ' -f 1)"; \
	work="$$(mktemp -d "$$parent/xfs-root.XXXXXXXX")"; \
	printf '%s\n' "$$observed" > "$$work/compiler.observed.sha256"; \
	python3 -B -O "$$repo/tests/compiler/xfs_root.py" --repo-root "$$repo" --fixture-root "$$fixtures" --artifact-root "$$work/lookup" --compiler "$$compiler" $(AURORA_TEST_IDENTITY_ARGS) $(XFS_ROOT_TEST_FLAGS); \
	python3 -B -O "$$repo/tests/compiler/xfs_root_api.py" --repo-root "$$repo" --fixture-root "$$fixtures" --artifact-root "$$work/api" --compiler "$$compiler" $(AURORA_TEST_IDENTITY_ARGS) $(XFS_ROOT_API_TEST_FLAGS); \
	python3 -B -O "$$repo/tests/compiler/xfs_root_entry.py" --repo-root "$$repo" --fixture-root "$$fixtures" --artifact-root "$$work/entries" --compiler "$$compiler" $(AURORA_TEST_IDENTITY_ARGS); \
	test "$$(sha256sum -- "$$compiler" | cut -d ' ' -f 1)" = "$$observed"; \
	printf 'PASS XFS root Make recipe: %s\n' "$$work"

.PHONY: test-utf8-range
test-utf8-range: $(OUT)
	@set -eu; \
	parent="$(UTF8_RANGE_ARTIFACT_PARENT)"; \
	test -d "$$parent"; \
	work="$$(mktemp -d "$$parent/utf8-range.XXXXXXXX")"; \
	python3 -B -O ../tests/compiler/utf8_range.py --compiler "$(abspath $(OUT))" $(AURORA_TEST_IDENTITY_ARGS) --artifacts "$$work/native" $(UTF8_RANGE_TEST_FLAGS); \
	printf 'PASS UTF-8 range Make recipe: %s\n' "$$work"

.PHONY: test-utf8-lines
test-utf8-lines: $(OUT)
	@set -eu; \
	parent="$(UTF8_LINES_ARTIFACT_PARENT)"; \
	test -d "$$parent"; \
	work="$$(mktemp -d "$$parent/utf8-lines.XXXXXXXX")"; \
	python3 -B -O ../tests/compiler/utf8_lines.py --compiler "$(abspath $(OUT))" $(AURORA_TEST_IDENTITY_ARGS) --artifacts "$$work/native" $(UTF8_LINES_TEST_FLAGS); \
	printf 'PASS UTF-8 lines Make recipe: %s\n' "$$work"

.PHONY: test-function-overloads
test-function-overloads: $(OUT)
	python3 -B -O ../tests/compiler/function_overloads.py $(abspath $(OUT))

.PHONY: test-readonly-windows
test: test-readonly-windows
test-readonly-windows: $(OUT)
	@set -eu; \
	work="$$(mktemp -d "$(dir $(abspath $(OUT)))readonly-windows.XXXXXXXX")"; \
	python3 -B -O ../tests/compiler/readonly_windows.py "$(abspath $(OUT))" --artifacts "$$work/source"; \
	$(CXX) $(IR_TEST_CXXFLAGS) -I. ../tests/compiler/readonly_windows_ir.cpp -o "$$work/ir-tests"; \
	"$$work/ir-tests"; \
	python3 -B -O ../tests/compiler/readonly_windows_ir_native.py "$$work/ir-tests" --artifacts "$$work/native"; \
	printf 'PASS readonly window Make recipe: %s\n' "$$work"

.PHONY: test-short-circuit
test: test-short-circuit
test-short-circuit: $(OUT)
	@set -eu; \
	work="$$(mktemp -d "$(dir $(abspath $(OUT)))short-circuit.XXXXXXXX")"; \
	python3 -B -O ../tests/compiler/short_circuit.py "$(abspath $(OUT))" --artifacts "$$work/source"; \
	$(CXX) $(IR_TEST_CXXFLAGS) -I. ../tests/compiler/short_circuit_ir.cpp -o "$$work/ir-tests"; \
	"$$work/ir-tests"; \
	python3 -B -O ../tests/compiler/short_circuit_ir_native.py "$$work/ir-tests" --artifacts "$$work/native"; \
	printf 'PASS short-circuit Make recipe: %s\n' "$$work"

.PHONY: test-token-scan
test: test-token-scan
test-token-scan: $(OUT)
	@set -eu; \
	work="$$(mktemp -d "$(dir $(abspath $(OUT)))token-scan.XXXXXXXX")"; \
	CXX="$(CXX)" CXXFLAGS="$(CXXFLAGS)" python3 -B -O ../tests/compiler/token_scan.py --compiler "$(abspath $(OUT))" $(AURORA_TEST_IDENTITY_ARGS) --artifacts "$$work/native"; \
	printf 'PASS token scanner Make recipe: %s\n' "$$work"

endif # controlled outer dispatcher / original inner graph
