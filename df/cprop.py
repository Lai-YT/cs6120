"""The Constant Propagation analysis.

- At the entry and exit of each basic block, the analysis determines which variable contains a constant value.
- This is a forward analysis.
- For blocks with multiple predecessors, the sets are merged using `Intersection`.
"""

import operator
from typing import Any, Callable, Dict, List

from cfg import Block

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


def out(b: Block, in_: Dict[str, Any]) -> Dict[str, Any]:
    """Computes the OUT set (a dict is a kind of set) for a block, performing constant propagation.

    Args:
        b: The basic block being analyzed.
        in_: The IN set of constant value mappings for the block.

    Returns:
        The OUT set that maps names to their constant values.
    """
    res = in_.copy()  # not to modify the input
    for instr in b:
        if "op" not in instr:
            continue
        op: str = instr["op"]
        if op == "const":
            res[instr["dest"]] = instr["value"]
        elif op == "id":
            arg: str = instr["args"][0]
            if arg in res:
                # Propagate the constant.
                res[instr["dest"]] = res[arg]
            else:
                # Assigned with a non-constant variable; no longer a constant.
                res.pop(instr["dest"], None)
        elif op in EVAL_OPS:
            # If all of the arguments are constants, calculate them.
            args: List[str] = instr["args"]
            if all(arg in res for arg in args):
                vals: List[Any] = [res[arg] for arg in args]
                res[instr["dest"]] = EVAL_OPS[op](*vals)
            else:
                # Assigned with a non-constant variable; no longer a constant.
                res.pop(instr["dest"], None)
    return res
