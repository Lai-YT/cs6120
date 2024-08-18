#!/usr/bin/env python3

import argparse
import json
import sys
from collections import defaultdict
from typing import Any, DefaultDict, Dict, List, Optional, Set

from cfg import ControlFlowGraph
from dom import dom_front, dom_tree
from type import Block, Instr


def defsites(cfg: ControlFlowGraph) -> Dict[str, Set[str]]:
    """Determines the definition sites of variables in the control flow graph.

    Args:
        cfg: The ControlFlowGraph object representing the function.

    Returns:
        A dictionary mapping variable names to the set of block names where they are defined.
    """
    map: DefaultDict[str, Set[str]] = defaultdict(set)
    for block_name, block in cfg.blocks.items():
        for instr in block:
            if "dest" in instr:
                map[instr["dest"]].add(block_name)
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
            if "dest" in instr:
                map[block_name].add(instr["dest"])
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


def insert_phi_nodes(
    cfg: ControlFlowGraph,
    vars: List[str],
    func_args: List[str],
) -> None:
    """Inserts Phi nodes into the control flow graph.

    The arguments of the phi-nodes will be the same as the variable name, which should be renamed later.

    Args:
        cfg: The control flow graph of the function.
        vars: The list of all variables in the function.
        func_args: The list of arguments of the function.
    """
    defs = defsites(cfg)
    orig = deforig(cfg)
    # Consider function arguments as defined in the entry block.
    for arg in func_args:
        defs[arg].add(cfg.entry)
        orig[cfg.entry].add(arg)

    front = dom_front(cfg)
    # Records the destination of phi-nodes that a block has, to avoid adding duplicates.
    phi: DefaultDict[str, Set[str]] = defaultdict(set)
    for v in vars:
        while defs[v]:
            d = defs[v].pop()
            for f, block in map(lambda f: (f, cfg.blocks[f]), front[d]):
                # Add a new phi-node for the variable if it doesn't have one.
                if v not in phi[f]:
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
                    phi[f].add(v)
                    if v not in orig[f]:
                        # This is a new definition of the variable.
                        defs[v].add(f)


def is_phi(instr: Instr) -> bool:
    return instr.get("op", "") == "phi"


def rename_variable(
    cfg: ControlFlowGraph, vars: List[str], func_args: List[str]
) -> None:
    """Renames variables in the control flow graph.

    The arguments of the phi-nodes will be renamed to their corresponding definitions.

    Args:
        cfg: The control flow graph of the function.
        vars: The list of all variables in the function.
        func_args: The list of arguments of the function.
    """
    # NOTE: A variable is not defined in a path if you access stack[v] and it is empty.
    stack: Dict[str, List[str]] = {v: [] for v in vars}
    for arg in func_args:
        # Function arguments are defined in the beginning.
        stack[arg] = [arg]
    TOP = -1

    # The suffix number for renaming.
    num = {v: 0 for v in stack.keys()}

    def fresh_name(v: str, num: Dict[str, int]) -> str:
        """Generates a fresh name for a variable and pushes it onto the stack."""
        stack[v].append(f"{v}.{num[v]}")
        num[v] += 1
        return stack[v][TOP]

    def rename_args(instr: Instr) -> None:
        for i, arg in enumerate(instr.get("args", [])):
            if stack[arg]:
                instr["args"][i] = stack[arg][TOP]

    dtree = dom_tree(cfg)

    def rename_recur(block_name: str) -> None:
        """Recursively renames variables in the dominator tree.

        Args:
            block_name: The name of the current block in the dominator tree.
        """
        # Tracks the number of times a variable is renamed to restore the stack later.
        rename_count: DefaultDict[str, int] = defaultdict(int)
        for instr in cfg.blocks[block_name]:
            # First, rename the use of variables in the arguments.
            # NOTE: We have to skip the phi-node instructions here, as they were already renamed.
            # Otherwise, looking up a renamed variable in the stack can cause an error.
            if not is_phi(instr):
                rename_args(instr)
            # Then, rename the destination variable.
            if "dest" in instr:
                v = instr["dest"]
                rename_count[v] += 1
                instr["dest"] = fresh_name(v, num)
        # Rename phi-node arguments in successor blocks.
        successor_blocks = list(
            map(cfg.blocks.__getitem__, cfg.successors_of(block_name))
        )
        for succ in successor_blocks:
            for p in filter(is_phi, succ):
                # Rename the argument that comes from the current block.
                for i, lbl in enumerate(p["labels"]):
                    if lbl != block_name:
                        continue
                    # If the variable is not defined in this path, suffix with .undef.
                    arg = p["args"][i]
                    p["args"][i] = stack[arg][TOP] if stack[arg] else f"{arg}.undef"
                    break
        for b in dtree[block_name]:
            rename_recur(b)
        # Restore the stack after processing the block.
        for v, cnt in rename_count.items():
            for _ in range(cnt):
                stack[v].pop()

    rename_recur(cfg.entry)


def to_ssa() -> None:
    """Converts a program into Static Single Assignment (SSA) form.

    Reads a program from stdin, transforms each function into SSA form,
    and writes the modified program to stdout.
    """
    prog: Dict[str, List[Dict[str, Any]]] = json.load(sys.stdin)
    for func in prog["functions"]:
        cfg = ControlFlowGraph(func["instrs"])
        vars = list(defsites(cfg).keys())
        func_args = [arg["name"] for arg in func.get("args", [])]

        insert_phi_nodes(cfg, vars, func_args)
        rename_variable(cfg, vars, func_args)

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
