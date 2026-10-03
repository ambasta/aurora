CXX ?= g++
CXXFLAGS ?= -std=c++23 -O2 -Wall -Wextra -Wpedantic -Werror
OUT ?= ../build/aurorac
.PHONY: all test
all: $(OUT)
$(OUT): main.cpp $(wildcard *.hpp)
	mkdir -p $(dir $(OUT))
	$(CXX) $(CXXFLAGS) $< -o $@
test: $(OUT)
	python3 ../tests/compiler/run.py $(abspath $(OUT))
	python3 ../tests/compiler/classes.py $(abspath $(OUT))
	python3 ../tests/compiler/value_calls.py $(abspath $(OUT))
	python3 ../tests/compiler/integers.py $(abspath $(OUT))
	python3 ../tests/compiler/unsigned.py $(abspath $(OUT))
	CXX="$(CXX)" python3 ../tests/compiler/unsigned_oracle.py $(abspath $(OUT))
	CXX="$(CXX)" python3 ../tests/compiler/integer_oracle.py $(abspath $(OUT))
	$(CXX) $(CXXFLAGS) -I. ../tests/compiler/ir_tests.cpp -o $(dir $(OUT))ir-tests
	$(dir $(OUT))ir-tests
	CXX="$(CXX)" python3 ../tests/compiler/ir_exhaustive.py
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
