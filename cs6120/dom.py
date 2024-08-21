#!/usr/bin/env python3

import argparse
import functools
import json
import operator
import sys
from typing import Any, Dict, List, Optional, Set

from cfg import ControlFlowGraph


def get_dom(cfg: ControlFlowGraph) -> Dict[str, Set[str]]:
    """Computes the dominators for each block in the control flow graph.

    A block A dominates block B if every path from the entry block to B must
    go through A. This function initializes each block's dominator set with
    all blocks and iteratively refines it using set intersection.

    Args:
        cfg: The control flow graph for which dominators are computed.

    Returns:
        A dictionary where the keys are block names and the values are sets of
        block names that dominate the key block.
    """
    dom: Dict[str, Set[str]] = {b: set(cfg.block_names) for b in cfg.block_names}
    dom[cfg.entry] = {cfg.entry}
    changed = True
    worklist = cfg.block_names
    worklist.remove(cfg.entry)  # Entry block has no predecessors.

    while changed:
        changed = False
        for vertex in worklist:
            new_dom = {vertex}
            try:
                new_dom |= functools.reduce(
                    operator.and_, (dom[x] for x in cfg.predecessors_of(vertex))
                )
            except TypeError:
                # NOTE: Block has no predecessor, thus unreachable.
                # Keep dominators as all blocks for unreachable blocks to avoid
                # affecting other blocks. This won't impact finding the
                # dominance tree or frontiers since those algorithms reassess
                # predecessors and recognize spurious dominators.
                continue

            if new_dom != dom[vertex]:
                dom[vertex] = new_dom
                changed = True

    return dom


def dom_tree(cfg: ControlFlowGraph) -> Dict[str, List[str]]:
    """Constructs the dominance tree from the control flow graph.

    The dominance tree is a structure where each block's immediate dominator
    (its closest dominator) is its parent in the tree.

    Args:
        cfg: The control flow graph for which the dominance tree is computed.

    Returns:
        A dictionary where the keys are block names and the values are lists
        of block names that are immediately dominated by the key block.
    """
    dom = get_dom(cfg)
    tree: Dict[str, List[str]] = {b: [] for b in cfg.block_names}

    for b in cfg.block_names:
        idom = intermediate_dominator_of(dom, b)
        if idom is not None:
            tree[idom].append(b)

    return {b: sorted(l) for b, l in tree.items()}


def intermediate_dominator_of(dom: Dict[str, Set[str]], y: str) -> Optional[str]:
    """Finds the immediate dominator of a block.

    The immediate dominator is the closest dominator to a block in the
    dominator tree.

    Args:
        dom: A dictionary of dominators where the keys are block names and
             the values are sets of blocks that dominate the key block.
        y: The block for which to find the immediate dominator.

    Returns:
        The block name that is the immediate dominator of `y`, or None if `y`
        is the entry block (which has no immediate dominator).
    """
    # A block x is the immediate dominator of y if all other dominators of y
    # also dominate x.
    strict_dom_y = dom[y] - {y}

    for x in strict_dom_y:
        if all(xx in dom[x] for xx in strict_dom_y):
            return x

    return None


def dom_front(cfg: ControlFlowGraph) -> Dict[str, List[str]]:
    """Computes the dominance frontiers for each block in the control flow graph.

    A block C is in the dominance frontier of block A if A dominates a
    predecessor B of C, but does not strictly dominate C itself. This
    typically occurs at loop headers.

    Args:
        cfg: The control flow graph for which dominance frontiers are computed.

    Returns:
        A dictionary where the keys are block names and the values are lists
        of block names that are in the dominance frontier of the key block.
    """
    dom = get_dom(cfg)
    front: Dict[str, List[str]] = {b: [] for b in cfg.block_names}

    for c in cfg.block_names:
        for b in cfg.predecessors_of(c):
            for a in dom[b]:
                # If a == c, there's a loop and c is the header.
                # It's a frontier of itself.
                if a not in dom[c] or a == c:
                    front[a].append(c)

    return {b: sorted(l) for b, l in front.items()}


def set2sortedlist(o) -> List:
    """Converts a set to a sorted list for JSON serialization.

    Args:
        o: The object to convert, expected to be a set.

    Returns:
        A sorted list representation of the set.

    Raises:
        TypeError: If the provided object is not a set.
    """
    if isinstance(o, set):
        return sorted(list(o))
    raise TypeError(f"Object of type {o.__class__.__name__} is not JSON serializable")


COMMANDS = {
    "dom": get_dom,
    "tree": dom_tree,
    "front": dom_front,
}


def main() -> None:
    parser = argparse.ArgumentParser(sys.argv[0])
    parser.add_argument(
        "cmd",
        choices=COMMANDS.keys(),
        metavar="CMD",
        help=f"[{'|'.join(COMMANDS.keys())}]",
    )
    args = parser.parse_args()

    prog: Dict[str, List[Dict[str, Any]]] = json.load(sys.stdin)

    for func in prog["functions"]:
        cfg = ControlFlowGraph(func["instrs"])
        # Dominance analyses can be affected by unreachable block.
        cfg.remove_unreachable_blocks()
        print(
            json.dumps(
                COMMANDS[args.cmd](cfg),
                default=set2sortedlist,
                indent=2,
                sort_keys=True,
            )
        )


if __name__ == "__main__":
    main()
