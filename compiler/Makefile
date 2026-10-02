CXX ?= g++
CXXFLAGS ?= -std=c++23 -O2 -Wall -Wextra -Wpedantic -Werror
OUT ?= ../build/aurorac
.PHONY: all test
all: $(OUT)
$(OUT): main.cpp
	mkdir -p $(dir $(OUT))
	$(CXX) $(CXXFLAGS) $< -o $@
test: $(OUT)
	python3 ../tests/compiler/run.py $(abspath $(OUT))
