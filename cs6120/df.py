#!/usr/bin/env python3
"""The data flow solver."""

import argparse
import json
import sys
from copy import deepcopy
from enum import Enum, auto
from typing import Any, Callable, Dict, Iterable, List, Set, Tuple, TypeVar

import cprop
import defined
import live
from cfg import ControlFlowGraph
from type import Block, Instr

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
                self._instrs, Flow.FORWARD, dict(), cprop.out, cprop.merge
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
        cfg = ControlFlowGraph(instrs)
        succs_of: Callable = cfg.successors_of
        preds_of: Callable = cfg.predecessors_of

        if flow is Flow.BACKWARD:
            entry_name = cfg.exit
        else:
            entry_name = cfg.entry

        # in[entry] = init
        ins: Dict[str, T] = {entry_name: deepcopy(init)}
        # out[*] = init
        outs: Dict[str, T] = {n: deepcopy(init) for n in cfg.block_names}

        if flow is Flow.BACKWARD:
            succs_of, preds_of = preds_of, succs_of

        # Represent the blocks with their names.
        worklist: Set[str] = set(cfg.block_names)
        while worklist:
            # We can pick any block here.
            block_name = worklist.pop()
            block = cfg.blocks[block_name]

            in_ = merge([outs[pred] for pred in preds_of(block_name)])
            out = transfer(block, in_)

            # Until the basic block converges.
            if out != outs[block_name]:
                worklist.update(succs_of(block_name))

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
