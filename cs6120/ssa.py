#!/usr/bin/env python3

import argparse
import copy
import json
import sys
from collections import defaultdict, namedtuple
from typing import Any, DefaultDict, Dict, List, Optional, Set, Tuple

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
        if instr.get("dest") == var:
            return instr.get("type")
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
            for f in front[d]:
                block = cfg.blocks[f]
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
                        defs[v].add(f)


def is_phi(instr: Instr) -> bool:
    return instr.get("op") == "phi"


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
        """Renames the arguments of an instruction."""
        for i, arg in enumerate(instr.get("args", [])):
            if stack[arg]:
                instr["args"][i] = stack[arg][TOP]

    dtree = dom_tree(cfg)

    def rename_recur(block_name: str) -> None:
        """Recursively renames variables in the dominator tree."""
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
        for succ in cfg.successors_of(block_name):
            for p in filter(is_phi, cfg.blocks[succ]):
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
        cfg.remove_unreachable_blocks()
        vars = list(defsites(cfg).keys())
        func_args = [arg["name"] for arg in func.get("args", [])]

        insert_phi_nodes(cfg, vars, func_args)
        rename_variable(cfg, vars, func_args)

        func["instrs"] = cfg.flatten()
    json.dump(prog, indent=2, fp=sys.stdout)


Def = namedtuple("Def", ["dest", "type", "src"])


def out_ssa() -> None:
    prog: Dict[str, List[Dict[str, Any]]] = json.load(sys.stdin)
    for func in prog["functions"]:
        cfg = ControlFlowGraph(func["instrs"])
        # NOTE: Unreachable blocks affect dominance analysis and may result in undefined identifiers.
        cfg.remove_unreachable_blocks()
        orig_blocks = cfg.block_names
        # We may have to add multiple definitions from a single path, so we record them and add them in the end instead of adding them on the fly.
        # (pred, succ) -> (dest, type, src)
        defs_to_add: DefaultDict[Tuple[str, str], List[Def]] = defaultdict(list)
        # Collect the definitions to add and remove the phi-nodes.
        for block in orig_blocks:
            phi_idx: List[int] = []
            for i, instr in enumerate(cfg.blocks[block]):
                if not is_phi(instr):
                    continue
                phi_idx.append(i)
                for pred, arg in zip(instr["labels"], instr["args"]):
                    # Skip the undefined variables.
                    if arg.endswith(".undef"):
                        continue
                    defs_to_add[(pred, block)].append(
                        Def(instr["dest"], instr["type"], arg)
                    )
            # We remove in reverse order so the index are kept.
            for i in reversed(phi_idx):
                cfg.blocks[block].pop(i)

        # FIXME: May remove necessary id instructions.
        remove_circular_id_instrs(defs_to_add)

        # Add the definitions.
        for (pred, succ), defs in defs_to_add.items():
            new_label = f"b.{pred}.{succ}"
            new_block = [{"label": new_label}] + [
                {"dest": def_.dest, "type": def_.type, "op": "id", "args": [def_.src]}
                for def_ in defs
            ]
            cfg.insert_between(pred, succ, new_block)  # type: ignore

        func["instrs"] = cfg.flatten()
    json.dump(prog, indent=2, fp=sys.stdout)


def remove_circular_id_instrs(
    defs_to_add: DefaultDict[Tuple[str, str], List[Def]]
) -> None:
    """Removes id instructions which renames variables between each other."""
    # To detect circular id instructions, we convert the defs to add in to a directed graph, of which the nodes are the definitions and the edges are the uses.
    # Since we are no more in SSA form, the variable names are augmented with the block names, (pred, succ) pair.
    id_graph: Dict[Tuple[Tuple[str, str], str], Set[Tuple[Tuple[str, str], str]]] = {}
    for pred_succ, defs in defs_to_add.items():
        for def_ in defs:
            id_graph[(pred_succ, def_.dest)] = set()
            for pred_succ_chd, defs_chd in defs_to_add.items():
                for def_chd in defs_chd:
                    if (
                        def_chd.src == def_.dest
                        # exclude self
                        and def_chd.dest != def_.dest
                    ):
                        id_graph[(pred_succ, def_.dest)].add(
                            (pred_succ_chd, def_chd.dest)
                        )
    # Do DFS to detect circular id instructions.
    visited: Set[Tuple[Tuple[str, str], str]] = set()
    # A list of paths that form a cycle.
    cycles: List[List[Tuple[Tuple[str, str], str]]] = []
    path: List[Tuple[Tuple[str, str], str]] = []

    def dfs(pred_succ: Tuple[str, str], var: str) -> None:
        if path and (pred_succ, var) == path[0]:
            cycles.append(copy.deepcopy(path))
            return
        if (pred_succ, var) in visited:
            return
        visited.add((pred_succ, var))
        path.append((pred_succ, var))
        for pred_succ_chd, var_chd in id_graph[(pred_succ, var)]:
            dfs(pred_succ_chd, var_chd)
        path.pop()

    for pred_succ, defs in defs_to_add.items():
        for def_ in defs:
            dfs(pred_succ, def_.dest)
    # Remove the circular id instructions.
    for cycle in cycles:
        for pred_succ, var in cycle:
            try:
                defs_to_add[pred_succ].remove(
                    # NOTE: This syntax remove the first element that satisfies the condition.
                    next(def_ for def_ in defs_to_add[pred_succ] if def_.dest == var)
                )
            except StopIteration:
                # A single definition may participate in multiple cycles.
                pass


def clean_circular_id_instrs(cfg: ControlFlowGraph) -> None:
    """Removes id instructions which renames variables between each other."""
    # Record each id instructions and its block.
    id_instrs: Dict[str, str] = {}
    for block_name, block in cfg.blocks.items():
        for instr in block:
            if instr.get("op") == "id":
                id_instrs[instr["dest"]] = block_name
    # Record uses of each variable.
    uses: Dict[str, List[Instr]] = {v: [] for v in id_instrs.keys()}
    for block_name, block in cfg.blocks.items():
        for instr in block:
            for arg in instr.get("args", []):
                if arg in uses:
                    uses[arg].append(instr)
    to_remove: Set[str] = set()
    # If the variable is used by another id instruction, and the variable defined by such id instruction is used by the current instruction, they formed a circular dependency and can be removed.
    for v, instrs in uses.items():
        # NOTE: Assume that circular dependencies are only between two id instructions.
        if len(instrs) == 1 and instrs[0].get("op") == "id":
            dep_instrs = uses[instrs[0]["dest"]]
            if len(dep_instrs) == 1:
                dep_instr = dep_instrs[0]
                if dep_instr.get("op") == "id" and dep_instr["dest"] == v:
                    to_remove.add(v)
                    to_remove.add(instrs[0]["dest"])

    for v in to_remove:
        block_name = id_instrs[v]
        block = cfg.blocks[block_name]
        for i, instr in enumerate(block):
            if instr.get("dest") == v:
                # NOTE: id instructions can be removed easily because they are not used,
                # nor do they effect the relations between blocks.
                block.pop(i)


CMDS = {
    "to": to_ssa,
    "out": out_ssa,
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
