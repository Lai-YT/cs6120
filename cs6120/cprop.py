"""The Constant Propagation analysis.

- At the entry and exit of each basic block, the analysis determines which variable contains a constant value.
- This is a forward analysis.
- For blocks with multiple predecessors, the sets are merged using a special `Intersection`.
"""

import operator
from typing import Any, Callable, Dict, Final, Iterable, List

from type import Block

# By evaluating the operation, constant folding is performed.
EVAL_OPS: Dict[str, Callable] = {
    #
    # Arithmetic
    #
    "add": operator.add,
    "mul": operator.mul,
    "sub": operator.sub,
    "div": operator.floordiv,
    #
    # Comparison
    #
    "eq": operator.eq,
    "lt": operator.lt,
    "gt": operator.gt,
    "le": operator.le,
    "ge": operator.ge,
    #
    # Logic
    #
    "not": operator.not_,
    "and": operator.and_,
    "or": operator.or_,
}

UNKNOWN: Final = "?"


def is_const(v: Any) -> bool:
    return v != UNKNOWN


def merge(dicts: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """
    A variable can be missing from some of the predecessors as long as it is always present with the same known constant value.
    """
    res = {}
    for d in dicts:
        for k, v in d.items():
            if k not in res:
                res[k] = v
            elif v != res[k]:
                # The value diverges; mark as unknown.
                res[k] = UNKNOWN
    return res


def out(b: Block, in_: Dict[str, Any]) -> Dict[str, Any]:
    """Computes the OUT set (a dict is a kind of set) for a block, performing constant propagation.

    Args:
        b: The basic block being analyzed.
        in_: The IN set of constant value mappings for the block.

    Returns:
        The OUT set that maps names to their constant values, with unknowns mapping to "?".
    """
    # NOTE: Function arguments are not included in the IN set; they are considered as unknowns.
    res = in_.copy()  # not to modify the input
    for instr in b:
        if "op" not in instr or "dest" not in instr:
            continue

        op: str = instr["op"]
        dest: str = instr["dest"]
        if op == "const":
            res[dest] = instr["value"]
        elif op == "id" and instr["args"][0] in res and is_const(res[instr["args"][0]]):
            # Propagate the constant.
            res[dest] = res[instr["args"][0]]
        elif op in EVAL_OPS and all(
            arg in res and is_const(res[arg]) for arg in instr["args"]
        ):
            # If all of the arguments are constants, calculate them.
            vals = [res[arg] for arg in instr["args"]]
            res[dest] = EVAL_OPS[op](*vals)
        else:
            # Assigned with a non-constant variable; no longer a constant.
            res[dest] = UNKNOWN
    return res
