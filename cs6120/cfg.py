#!/usr/bin/env python3
"""Processing control-flow."""

import argparse
import json
import sys
import typing
from collections import OrderedDict
from typing import Any, Dict, Generator, Iterable, List, Mapping

from type import Block, Instr

# NOTE: `call` is not considered a terminator because it transfers control back
# to the next instruction.
TERMINATORS = "jmp", "br", "ret"


class ControlFlowGraph:
    """Represents a Control Flow Graph (CFG) for a function.

    This class is responsible for constructing a CFG from a sequence of instructions,
    identifying the basic blocks, and determining the successor and predecessor relationships
    between blocks. It also supports flattening the CFG back into a linear sequence of instructions
    with appropriate labels.
    """

    def __init__(self, func: Iterable[Instr]) -> None:
        """
        Args:
            func: An iterable of instructions representing the function.
        """
        self._blocks = name_blocks(form_blocks(func))
        self._successors = get_cfg(self._blocks)
        self._predecessors = find_predecessors(self._successors)
        self._add_entry()

    def successors_of(self, block: str) -> List[str]:
        """Returns the block names of the successors.

        Args:
            block: The name of the block for which to retrieve successors.

        Returns:
            A list of block names that are successors of the specified block.
        """
        return self._successors[block]

    def predecessors_of(self, block: str) -> List[str]:
        """Returns the block names of the predecessors.

        Args:
            block: The name of the block for which to retrieve predecessors.

        Returns:
            A list of block names that are predecessors of the specified block.
        """
        return self._predecessors[block]

    def flatten(self) -> List[Instr]:
        """Flattens the control flow graph back to a sequence of instructions.

        The flattened sequence includes labels indicating the entry points of blocks.

        Returns:
            A list of instructions representing the flattened control flow graph.
        """
        return [i for bn in self.block_names for i in self._flatten_block(bn)]

    def _flatten_block(self, block_name: str) -> List[Instr]:
        """Flattens a single block to a sequence of instructions.

        Args:
            block_name: The name of the block to flatten.

        Returns:
            A list of instructions, including a label for the block entry.
        """
        return [{"label": block_name}, *self._blocks[block_name]]

    def _add_entry(self) -> None:
        """Adds an entry block to the control flow graph.

        If the original entry block has predecessors, a new entry block is added that jumps
        to the original entry block. This is done to avoid confusion in algorithms that
        process the CFG.
        """
        if not self._predecessors[self.entry]:
            return
        instr: Instr = {
            "op": "jmp",
            "labels": [self.entry],
        }
        # FIXME: Possible name conflict.
        blk_name = "entry.1"
        blk: Block = [instr]
        self._predecessors[blk_name] = []
        self._successors[blk_name] = [self.entry]
        self._predecessors[self.entry].append(blk_name)
        self._blocks[blk_name] = blk
        self._blocks.move_to_end(blk_name, last=False)

    @property
    def block_names(self) -> List[str]:
        """List of block names in the control flow graph.

        Returns:
            A list of block names in the order they appear in the CFG.
        """
        return list(self._blocks.keys())

    @property
    def blocks(self) -> Mapping[str, Block]:
        """Mapping of block names to blocks."""
        return self._blocks

    @property
    def entry(self) -> str:
        """Name of the entry block."""
        return self.block_names[0]

    @property
    def exit(self) -> str:
        """Name of the exit block."""
        return self.block_names[-1]


def form_blocks(body: Iterable[Instr]) -> Generator[Block, None, None]:
    """Converts a list of instructions into a list of basic blocks.

    For blocks that have a label at the beginning, such label will be the first instruction inside the block.

    Args:
        body: An iterable of instructions.

    Yields:
        Block of instructions.
    """

    def is_label(instr: Instr) -> bool:
        return "op" not in instr

    cur_block: Block = []

    for instr in body:
        if not is_label(instr):
            cur_block.append(instr)

            if instr["op"] in TERMINATORS:
                yield cur_block
                cur_block = []
        else:
            # A terminator followed by a label forms an empty basic block between them,
            # skip such block.
            if cur_block:
                yield cur_block
            cur_block = [instr]
    # tail case
    if cur_block:
        yield cur_block


def name_blocks(blocks: Iterable[Block]) -> typing.OrderedDict[str, Block]:
    """Assigns names to blocks. A block may or may not start with a label.

    For those without a label, a name will be created; for those with a label, the label is used
    as its name. The label is then removed since the name will be used for reference.
    Additionally, blocks without a terminator are fixed.

    Args:
        blocks: An iterable of blocks.

    Returns:
        An ordered dictionary mapping block names to blocks.
    """
    # Preserve the ordering of blocks for CFG construction.
    name_to_block = OrderedDict()
    next_label_number = 0
    for block in blocks:
        if "label" in block[0]:
            name = block[0]["label"]
            # remove the label
            block = block[1:]
        else:
            name = f"b{next_label_number}"
            next_label_number += 1

        name_to_block[name] = block

    add_terminators(name_to_block)
    return name_to_block


def add_terminators(blocks: typing.OrderedDict[str, Block]) -> None:
    """Ensures each block ends with a terminator instruction.

    This function iterates over each block and checks if the last instruction
    is a terminator. If a block does not end with a terminator, it appends a
    jump to the next block or a return if it is the last block. This avoids
    fall-through by ensuring that each block has a clear transfer of control.

    Args:
        blocks: An ordered dictionary mapping block names to blocks.
    """
    for i, block in enumerate(blocks.values()):
        if not block or block[-1]["op"] not in TERMINATORS:
            if i == len(blocks) - 1:
                block.append({"op": "ret", "args": []})
            else:
                next = list(blocks.keys())[i + 1]
                block.append({"op": "jmp", "labels": [next]})


def find_predecessors(name2successors: Dict[str, List[str]]) -> Dict[str, List[str]]:
    """Finds the predecessors of blocks through their successors.

    Args:
        name2successors: A dictionary mapping block names to their successor block names.

    Returns:
        A dictionary mapping block names to their predecessor block names.
    """
    name2predecessors: Dict[str, List[str]] = {n: list() for n in name2successors}
    for name, successors in name2successors.items():
        for this_name in name2predecessors:
            if this_name in successors:
                name2predecessors[this_name].append(name)
    return name2predecessors


def get_cfg(name_to_block: typing.OrderedDict[str, Block]) -> Dict[str, List[str]]:
    """Produces a mapping from block names to their successor block names.

    Args:
        name_to_block: An ordered dictionary mapping block names to blocks.

    Returns:
        A dictionary mapping block names to lists of successor block names.
    """
    successors = {}
    for i, (name, block) in enumerate(name_to_block.items()):
        last = block[-1]
        if last["op"] in ("jmp", "br"):
            successor = last["labels"]
        elif last["op"] == "ret":
            successor = []
        # fallthrough
        else:
            if i == len(name_to_block) - 1:
                successor = []
            else:
                successor = [list(name_to_block)[i + 1]]
        successors[name] = successor
    return successors


def graph(func_name: str, cfg: Dict[str, List[str]]) -> None:
    """Represents the control-flow graph in GraphViz format.

    Args:
        func_name: The name of the function.
        cfg: The control-flow graph as a dictionary mapping block names to lists of successor block names.
    """
    print(f"digraph {func_name} {{")
    for block_name in cfg:
        print(f'  "{block_name}";')
    for block_name, successors in cfg.items():
        for successor_name in successors:
            print(f'  "{block_name}" -> "{successor_name}"')
    print("}")


# Command-line entry points.


def blocks() -> None:
    """Forms basic blocks for each function in the program and add a `blocks` section.

    Reads from stdin and writes to stdout.
    """
    prog: Dict[str, List[Dict[str, Any]]] = json.load(sys.stdin)

    for func in prog["functions"]:
        func["blocks"] = name_blocks(form_blocks(func["instrs"]))

    json.dump(prog, indent=2, fp=sys.stdout)


def cfg() -> None:
    """Constructs the control-flow graph for each function in the program and add a `cfg` section.

    Reads from stdin and writes to stdout.
    """
    prog: Dict[str, List[typing.OrderedDict[str, Any]]] = json.load(
        sys.stdin, object_pairs_hook=OrderedDict
    )

    for func in prog["functions"]:
        if "blocks" not in func:
            print(
                "Missing `blocks` section; please form the basic blocks first.",
                file=sys.stderr,
            )
            sys.exit(1)
        func["cfg"] = get_cfg(func["blocks"])

    json.dump(prog, indent=2, fp=sys.stdout)


def graph_cfg() -> None:
    """Represents the control-flow graph in GraphViz format for each function in the program.

    Reads from stdin and writes to stdout.
    """
    prog: Dict[str, List[Dict[str, Any]]] = json.load(sys.stdin)

    for func in prog["functions"]:
        if "cfg" not in func:
            print(
                "Missing `cfg` section; please construct the control-flow graph first.",
                file=sys.stderr,
            )
        graph(func["name"], func["cfg"])


MODES = {
    "blocks": blocks,
    "cfg": cfg,
    "graph-cfg": graph_cfg,
}

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        sys.argv[0],
        description="""
This module defines three commands for processing control-flow in programs:
(1) `blocks`: Forms the basic blocks and adds a `blocks` section for each function in the program.
(2) `cfg`: Constructs the control-flow graph and adds a `cfg` section for each function in the program.
(3) `graph-cfg`: Represents the control-flow graph in GraphViz format.
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("mode", choices=MODES)
    args = parser.parse_args()
    MODES[args.mode]()
