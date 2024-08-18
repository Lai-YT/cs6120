#!/usr/bin/env python3

import argparse
import json
import sys
from typing import Any, Dict, List, Optional, Set

from cfg import ControlFlowGraph
from dom import dom_front, dom_tree
from type import Block


def defsites(cfg: ControlFlowGraph) -> Dict[str, Set[str]]:
    """Determines the definition sites of variables in the control flow graph.

    Args:
        cfg: The ControlFlowGraph object representing the function.

    Returns:
        A dictionary mapping variable names to the set of block names where they are defined.
    """
    map: Dict[str, Set[str]] = {}
    for block_name, block in cfg.blocks.items():
        for instr in block:
            if (dest := instr.get("dest", None)) is not None:
                if dest not in map:
                    map[dest] = set()
                map[dest].add(block_name)
    return map


def deforig(cfg: ControlFlowGraph) -> Dict[str, Set[str]]:
    """Determines the original definition blocks for each variable.

    Args:
        cfg: The ControlFlowGraph object representing the function.

    Returns:
        A dictionary mapping block names to the set of variables defined within those blocks.
    """
    map: Dict[str, Set[str]] = {n: set() for n in cfg.block_names}
    for block_name, block in cfg.blocks.items():
        for instr in block:
            if (dest := instr.get("dest", None)) is not None:
                map[block_name].add(dest)
    return map


def type_of(var: str, def_block: Block) -> Optional[str]:
    """Retrieves the type of a variable from its definition block.

    Args:
        var: The name of the variable to determine the type of.
        def_block: The block that contains the definition of the variable.

    Returns:
        The type of the variable as a string, or None if the block does not define the variable.
    """
    for instr in def_block:
        if "dest" in instr and instr["dest"] == var:
            return instr["type"]
    return None


def old_name(var: str) -> str:
    """Strips any renaming suffix from a variable name to get the original name.

    Args:
        var: The potentially renamed variable (e.g., "x.1").

    Returns:
        The original variable name without suffix (e.g., "x").
    """
    s = var.split(".")
    if len(s) == 1:
        return var
    return ".".join(s[:-1])


def to_ssa() -> None:
    """Converts a program into Static Single Assignment (SSA) form.

    Reads a program from stdin, transforms each function into SSA form,
    and writes the modified program to stdout.
    """
    prog: Dict[str, List[Dict[str, Any]]] = json.load(sys.stdin)
    for func in prog["functions"]:
        cfg = ControlFlowGraph(func["instrs"])
        defs = defsites(cfg)
        orig = deforig(cfg)
        # Function arguments are considered to be defined in the entry block.
        for arg in func.get("args", []):
            arg_name = arg["name"]
            defs[arg_name] = defs.get(arg_name, set()).union([cfg.entry])
            orig[cfg.entry].add(arg_name)
        vars = list(defs.keys())
        front = dom_front(cfg)
        # Records the destination of phi-nodes that a block has, to avoid adding duplicates.
        phi: Dict[str, Set[str]] = {}
        #
        # Insert Phi-nodes.
        #
        for v in vars:
            while defs[v]:
                d = defs[v].pop()
                for f, block in map(lambda f: (f, cfg.blocks[f]), front[d]):
                    # Add a new phi-node for the variable if it doesn't have one.
                    if v not in phi.get(f, set()):
                        block.insert(
                            0,
                            {
                                "op": "phi",
                                "type": type_of(v, cfg.blocks[d]),
                                "dest": v,
                                "args": [v] * len(cfg.predecessors_of(f)),
                                "labels": cfg.predecessors_of(f),
                            },
                        )
                        if f not in phi:
                            phi[f] = {v}
                        else:
                            phi[f].add(v)
                        if v not in orig[f]:
                            # This is a new definition of the variable.
                            defs[v].add(f)
        #
        # Rename variables.
        #
        dtree = dom_tree(cfg)
        # NOTE: A variable is not defined in a path if you access stack[v] and it is empty.
        stack = {v: [] for v in vars}
        # The suffix number for renaming.
        num = {v: 0 for v in vars}
        TOP = -1

        def rename_recur(block_name: str) -> None:
            """Recursively renames variables in the dominator tree.

            Args:
                block_name: The name of the current block in the dominator tree.
            """
            # Tracks the number of times a variable is renamed to restore the stack later.
            rename_count: Dict[str, int] = {}
            for instr in cfg.blocks[block_name]:
                # First, rename the use of variables in the arguments.
                for i, arg in enumerate(instr.get("args", [])):
                    if stack[old_name(arg)]:
                        instr["args"][i] = stack[old_name(arg)][TOP]
                # Then, rename the destination variable.
                if "dest" in instr:
                    v = instr["dest"]
                    stack[v].append(f"{v}.{num[v]}")
                    rename_count[v] = rename_count.get(v, 0) + 1
                    num[v] += 1
                    instr["dest"] = stack[v][TOP]
            # Rename phi-node arguments in successor blocks.
            for succ in map(lambda bn: cfg.blocks[bn], cfg.successors_of(block_name)):
                for p in filter(lambda instr: instr.get("op", "") == "phi", succ):
                    for i, lbl in enumerate(p["labels"]):
                        if lbl == block_name:
                            # Rename the argument of the phi-node.
                            # If the variable is not defined in this path, suffix with .undef.
                            name = (
                                stack[old_name(p["args"][i])][TOP]
                                if stack[old_name(p["args"][i])]
                                else f'{p["args"][i]}.undef'
                            )
                            p["args"][i] = name
                            break
            for b in dtree[block_name]:
                rename_recur(b)
            # Restore the stack after processing the block.
            for v, cnt in rename_count.items():
                for _ in range(cnt):
                    stack[v].pop()

        rename_recur(cfg.entry)

        func["instrs"] = cfg.flatten()
    json.dump(prog, indent=2, fp=sys.stdout)


def from_ssa():
    pass


CMDS = {
    "to": to_ssa,
    "from": from_ssa,
}


def main() -> None:
    parser = argparse.ArgumentParser(sys.argv[0])
    parser.add_argument(
        "cmd", metavar="CMD", choices=CMDS.keys(), help=f"[{'|'.join(CMDS.keys())}]"
    )
    args = parser.parse_args()
    CMDS[args.cmd]()


if __name__ == "__main__":
    main()
