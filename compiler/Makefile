CXX ?= g++
CXXFLAGS ?= -std=c++23 -O2 -Wall -Wextra -Wpedantic -Werror
IR_TEST_CXXFLAGS ?= $(CXXFLAGS)
IR_TEST_BUILD_PREFIX ?=
UTF8_TEST_FLAGS ?=
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
$(OUT): main.cpp $(wildcard *.hpp)
	mkdir -p $(dir $(OUT))
	$(CXX) $(CXXFLAGS) $< -o $@
test: $(OUT) test-xfs-root
	python3 ../tests/compiler/run.py $(abspath $(OUT))
	python3 ../tests/compiler/classes.py $(abspath $(OUT))
	python3 ../tests/compiler/value_calls.py $(abspath $(OUT))
	python3 ../tests/compiler/templates.py $(abspath $(OUT))
	python3 -O ../tests/compiler/function_templates.py $(abspath $(OUT))
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
	python3 ../tests/compiler/packed_values.py $(abspath $(OUT))
	python3 ../tests/compiler/readonly_spans.py $(abspath $(OUT))
	python3 -O ../tests/compiler/storage_binary.py $(abspath $(OUT))
	python3 -O ../tests/compiler/xfs_geometry.py $(abspath $(OUT)) --mutation-controls $(XFS_GEOMETRY_TEST_FLAGS)
	python3 -O ../tests/compiler/utf8.py $(abspath $(OUT)) $(UTF8_TEST_FLAGS)
	python3 -O ../tests/compiler/utf8_encoding.py $(abspath $(OUT)) $(UTF8_TEST_FLAGS)
	python3 -O ../fixtures/xfs-offline/verify_native.py --compiler $(abspath $(OUT)) --compiler-sha256 "$$(sha256sum $(abspath $(OUT)) | cut -d ' ' -f 1)"
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
	python3 -O ../fixtures/xfs-offline/verify_native.py --compiler $(abspath $(OUT)) --compiler-sha256 "$$(sha256sum $(abspath $(OUT)) | cut -d ' ' -f 1)"

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
	python3 -O ../tests/compiler/xfs_geometry.py $(abspath $(OUT)) --mutation-controls $(XFS_GEOMETRY_TEST_FLAGS)

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
	pin="$$(sha256sum -- "$$compiler" | cut -d ' ' -f 1)"; \
	if [ -n "$(XFS_ROOT_COMPILER_SHA256)" ]; then test "$$pin" = "$(XFS_ROOT_COMPILER_SHA256)"; fi; \
	work="$$(mktemp -d "$$parent/xfs-root.XXXXXXXX")"; \
	printf '%s\n' "$$pin" > "$$work/compiler.sha256"; \
	python3 -B -O "$$repo/tests/compiler/xfs_root.py" --repo-root "$$repo" --fixture-root "$$fixtures" --artifact-root "$$work/lookup" --compiler "$$compiler" --compiler-sha256 "$$pin" $(XFS_ROOT_TEST_FLAGS); \
	python3 -B -O "$$repo/tests/compiler/xfs_root_api.py" --repo-root "$$repo" --fixture-root "$$fixtures" --artifact-root "$$work/api" --compiler "$$compiler" --compiler-sha256 "$$pin" $(XFS_ROOT_API_TEST_FLAGS); \
	test "$$(sha256sum -- "$$compiler" | cut -d ' ' -f 1)" = "$$pin"; \
	printf 'PASS XFS root Make recipe: %s\n' "$$work"
