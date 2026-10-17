# Builds the firmware logic (boat/src/) for the laptop.
#
#   make -C boat-arduino test   run the unit tests
#   make -C boat-arduino host   build build/boat-host, the firmware the simulator runs
#
# This does NOT build for the board; use the Arduino IDE or arduino-cli for
# that (see README.md). sim/run.py builds build/boat-host on its own with the
# same flags, so you don't need make to run the simulator.

CXX ?= c++
CXXFLAGS ?= -std=c++17 -O2 -Wall -Wextra

CORE_SRC := $(wildcard boat/src/*.cpp)
CORE_HDR := $(wildcard boat/src/*.h)

.PHONY: all host test clean

all: host test

host: build/boat-host

build/boat-host: host/host_main.cpp $(CORE_SRC) $(CORE_HDR)
	@mkdir -p build
	$(CXX) $(CXXFLAGS) -o $@ host/host_main.cpp $(CORE_SRC)

build/test-core: tests/test_core.cpp $(CORE_SRC) $(CORE_HDR)
	@mkdir -p build
	$(CXX) $(CXXFLAGS) -o $@ tests/test_core.cpp $(CORE_SRC)

test: build/test-core
	./build/test-core

clean:
	rm -rf build
