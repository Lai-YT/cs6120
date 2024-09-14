CC = clang-17
CFLAGS ?= -fpass-plugin="../../build/pass/TrivialConstantFoldingPass.so"

SRC = $(wildcard *.c)
EXE = $(SRC:.c=.out)

all: $(EXE)

%.out: %.c
	$(CC) $(CFLAGS) -o $@ $<

clean:
	$(RM) $(EXE)
.PHONY: clean
