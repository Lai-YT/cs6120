"""The Constant Propagation analysis.

- At the entry and exit of each basic block, the analysis determines which variable contains a constant value.
- This is a forward analysis.
- For blocks with multiple predecessors, the sets are merged using `Intersection`.
"""

import operator
from collections import namedtuple
from typing import Any, Callable, Dict, List, Set

from cfg import Block

Const = namedtuple("Const", ["name", "value"])

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


def out(b: Block, in_: Set[Const]) -> Set[Const]:
    """Computes the OUT set for a block, performing constant propagation.

    Args:
        b: The basic block being analyzed.
        in_: The IN set of constants for the block.

    Returns:
        The OUT set of constants for the block.
    """
    name2value: Dict[str, Any] = {c.name: c.value for c in in_}
    for instr in b:
        if "op" not in instr:
            continue
        op: str = instr["op"]
        if op == "const":
            name2value[instr["dest"]] = instr["value"]
        elif op == "id":
            arg: str = instr["args"][0]
            if arg in name2value:
                # Propagate the constant.
                name2value[instr["dest"]] = name2value[arg]
            else:
                # Assigned with a non-constant variable; no longer a constant.
                name2value.pop(instr["dest"], None)
        elif op in EVAL_OPS:
            # If all of the arguments are constants, calculate them.
            args: List[str] = instr["args"]
            if all(arg in name2value for arg in args):
                vals: List[Any] = [name2value[arg] for arg in args]
                name2value[instr["dest"]] = EVAL_OPS[op](*vals)
            else:
                # Assigned with a non-constant variable; no longer a constant.
                name2value.pop(instr["dest"], None)
    return set(Const(name, value) for name, value in name2value.items())
