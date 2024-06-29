"""
This module defines three commands:
(1) blocks: Form the basic blocks and add a `blocks` section for each of the functions in the program.
(2) cfg: Construct the control-flow graph and add a `cfg` section for each of the functions in the program.
(3) graph-cfg: Represent the cfg in GraphViz format.
"""

__version__ = "0.1.0"

import json
import sys
import typing
from collections import OrderedDict
from typing import Any, Dict, Generator, Iterable, List, Mapping

Block = List[Mapping[str, Any]]

# NOTE: `call` is not considered as a terminator because it transfers control back
# to the next instruction.
TERMINATORS = "jmp", "br", "ret"


def form_blocks(body: Iterable[Mapping[str, Any]]) -> Generator[Block, None, None]:
    """Converts a list of instructions into a list of basic blocks

    For blocks that have a label at the beginning, such label will be the first instruction inside the block.
    """

    def is_label(instr: Mapping[str, Any]) -> bool:
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
    yield cur_block


def name_blocks(blocks: Iterable[Block]) -> typing.OrderedDict[str, Block]:
    """
    A block may or may not be started with a label. For those without a label,
    we'll create a name for it; for those with a label, the label is used as
    its name. Label will then be removed since we'll refer to the name instead.
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

    return name_to_block


def get_cfg(name_to_block: typing.OrderedDict[str, Block]) -> Dict[str, Block]:
    """Produces a mapping from block name to its successor block names."""
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


def graph(func_name: str, cfg: Dict[str, Block]) -> None:
    print(f"digraph {func_name} {{")
    for block_name in cfg:
        print(f'  "{block_name}";')
    for block_name, successors in cfg.items():
        for successor_name in successors:
            print(f'  "{block_name}" -> "{successor_name}"')
    print("}")


# Command-line entry points.


def blocks() -> None:
    prog: Dict[str, List[Dict[str, Any]]] = json.load(sys.stdin)

    for func in prog["functions"]:
        func["blocks"] = name_blocks(form_blocks(func["instrs"]))

    json.dump(prog, indent=2, fp=sys.stdout)


def cfg() -> None:
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
    prog: Dict[str, List[Dict[str, Any]]] = json.load(sys.stdin)

    for func in prog["functions"]:
        if "cfg" not in func:
            print(
                "Missing `cfg` section; please construct the control-flow graph first.",
                file=sys.stderr,
            )
        graph(func["name"], func["cfg"])
