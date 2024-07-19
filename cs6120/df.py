"""The data flow solver."""

import argparse
import json
import sys
from collections import deque
from copy import deepcopy
from enum import Enum, auto
from typing import (
    Any,
    Callable,
    Deque,
    Dict,
    Iterable,
    List,
    OrderedDict,
    Set,
    Tuple,
    TypeVar,
)

import cprop
import defined
import live
from cfg import form_blocks, get_cfg, name_blocks
from type import Block, Instr


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


T = TypeVar("T")


def set_union(iterable: Iterable[Set[T]]) -> Set[T]:
    return set().union(*iterable)


def set_intersection(iterable: Iterable[Set[T]]) -> Set[T]:
    it = iter(iterable)
    try:
        first = next(it)
        return first.intersection(*it)
    except StopIteration:
        # The iterable contains no sets.
        return set()


def dict_intersection(dicts: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Note:
        The key-value pairs have to be the same to be considered as intersected.
    """
    # Converts the dictionaries into sets of tuples to perform intersections.
    intersections: Set[Tuple[str, Any]] = set_intersection(
        set((k, v) for k, v in d.items()) for d in dicts
    )
    res: Dict[str, Any] = {}
    for dict_ in dicts:
        for k, v in dict_.items():
            if (k, v) in intersections:
                res[k] = v
    return res


class Analysis(Enum):
    # Reaching Definitions.
    DEFINED = auto()
    # Constant Propagation.
    CPROP = auto()
    # Live Variables.
    LIVE = auto()

    def __str__(self) -> str:
        return self.name.lower()


class Flow(Enum):
    FORWARD = auto()
    BACKWARD = auto()


class DataFlowSolver:
    def __init__(self, instrs: List[Instr], analysis: Analysis) -> None:
        """
        Note:
            The DataFlowSolver knows the flow of each analyses.
        """
        self._instrs = instrs
        self._analysis = analysis

    def solve(self) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        if self._analysis is Analysis.DEFINED:
            return self._solve(
                self._instrs, Flow.FORWARD, set(), defined.out, set_union
            )
        elif self._analysis is Analysis.CPROP:
            return self._solve(
                self._instrs, Flow.FORWARD, dict(), cprop.out, dict_intersection
            )
        elif self._analysis is Analysis.LIVE:
            return self._solve(self._instrs, Flow.BACKWARD, set(), live.in_, set_union)
        else:
            raise ValueError(f"unknonw analysis {self._analysis}")

    def _solve(
        self,
        instrs: List[Instr],
        flow: Flow,
        init: T,
        transfer: Callable[[Block, T], T],
        merge: Callable[[Iterable[T]], T],
    ) -> Tuple[Dict[str, T], Dict[str, T]]:
        """Solves the data flow analysis.

        Args:
            instrs: A list of instructions.
            flow: The flow direction of the analysis.
            init: The initial set (doesn't necessarily have to be a `set`) of data flow values. Will be copied with `deepcopy`.
            transfer: A function to compute the OUT set from the IN set for a block.
            merge: A function to merge multiple IN sets.

        Returns:
            A tuple containing two dictionaries:
                - IN sets for each block.
                - OUT sets for each block.
        """
        # The first block is the entry block.
        blocks: OrderedDict[str, Block] = name_blocks(form_blocks(instrs))
        name2successors: Dict[str, List[str]] = get_cfg(blocks)
        name2predecessors: Dict[str, List[str]] = find_predecessors(name2successors)

        if flow is Flow.BACKWARD:
            entry_name = list(blocks.keys())[-1]
        else:
            entry_name = list(blocks.keys())[0]

        # in[entry] = init
        ins: Dict[str, T] = {entry_name: deepcopy(init)}
        # out[*] = init
        outs: Dict[str, T] = {n: deepcopy(init) for n in blocks}

        if flow is Flow.BACKWARD:
            name2successors, name2predecessors = name2predecessors, name2successors

        # Represent the blocks with their names.
        worklist: Deque[str] = deque(blocks.keys())
        while worklist:
            # We can pick any block here.
            block_name = worklist.popleft()
            block = blocks[block_name]

            in_ = merge([outs[pred] for pred in name2predecessors[block_name]])
            out = transfer(block, in_)

            # Until the basic block converges.
            if out != outs[block_name]:
                worklist += name2successors[block_name]

            ins[block_name] = in_
            outs[block_name] = out
        assert len(ins) == len(outs)

        if flow is Flow.BACKWARD:
            ins, outs = outs, ins
        return ins, outs


if __name__ == "__main__":
    parser = argparse.ArgumentParser(sys.argv[0])
    parser.add_argument(
        "analysis", choices=Analysis, type=lambda x: Analysis[x.upper()]
    )
    args = parser.parse_args()

    prog: Dict[str, List[Dict[str, Any]]] = json.load(sys.stdin)

    if args.analysis in (Analysis.DEFINED, Analysis.LIVE):
        for func in prog["functions"]:
            solver = DataFlowSolver(func["instrs"], args.analysis)
            ins, outs = solver.solve()
            for block_name in ins.keys():
                print(f"{block_name}:")
                print("  in:  ", end="")
                print(*sorted(ins[block_name]), sep=", ")
                print("  out: ", end="")
                print(*sorted(outs[block_name]), sep=", ")
    elif args.analysis is Analysis.CPROP:
        for func in prog["functions"]:
            solver = DataFlowSolver(func["instrs"], Analysis.CPROP)
            ins, outs = solver.solve()
            for block_name in ins.keys():
                print(f"{block_name}:")
                print(
                    "  in: ",
                    ", ".join(
                        f"{name}: {val}" for name, val in ins[block_name].items()
                    ),
                )
                print(
                    "  out:",
                    ", ".join(
                        f"{name}: {val}" for name, val in outs[block_name].items()
                    ),
                )
