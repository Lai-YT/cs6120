#!/usr/bin/env python3

import argparse
import functools
import json
import operator
import sys
from typing import Any, Dict, List, Set

from cfg import ControlFlowGraph


def get_dom(cfg: ControlFlowGraph) -> Dict[str, Set[str]]:
    # The operator is set intersection; initialized with the set of all blocks.
    dom: Dict[str, Set[str]] = {b: set(cfg.blocks) for b in cfg.blocks}
    dom[cfg.entry] = {cfg.entry}
    changed = True
    while changed:
        changed = False
        for vertex in cfg.blocks:
            new_dom = set([vertex])
            try:
                new_dom |= functools.reduce(
                    operator.and_, (dom[x] for x in cfg.predecessors_of(vertex))
                )
            except TypeError:
                # The vertex has no predecessor.
                # It's the entry block, or it's unreachable.
                pass
            if new_dom != dom[vertex]:
                dom[vertex] = new_dom
                changed = True
    return dom


def set2sortedlist(o) -> List:
    if isinstance(o, set):
        return sorted(list(o))
    raise TypeError(f"Object of type {o.__class__.__name__} is not JSON serializable")


COMMANDS = {
    "dom": get_dom,
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
        cfg.ensure_entry()
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
