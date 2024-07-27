"""The Constant Propagation analysis.

- At the entry and exit of each basic block, the analysis determines which variable contains a constant value.
- This is a forward analysis.
- For blocks with multiple predecessors, the sets are merged using a special `Intersection`.
"""

import operator
from typing import Any, Callable, Dict, Final, Iterable, List, Optional

from type import Block, Instr

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


def fold(instr: Instr, var2const: Dict[str, Any]) -> Optional[Any]:
    """Attempts to fold a constant value from the instruction and variable constants.

    Args:
        instr: The instruction to process, containing operation and arguments.
        var2const: A dictionary mapping variable names to their constant values.

    Returns:
        The constant result of the operation if possible, otherwise None.
    """
    op = instr["op"]
    if op not in EVAL_OPS:
        return None

    args: List[str] = instr["args"]
    vals = [var2const.get(arg, UNKNOWN) for arg in args]
    if op in ("add", "mul", "sub", "div"):
        # For arithmetic operations, all arguments have to have constant value.
        # Additionally, for "div", the divisor cannot be 0.
        if op == "div" and vals[1] == 0:
            return None
    elif op in ("eq", "lt", "gt", "le", "ge"):
        # Comparison operations can be folded without knowning the value if the two arguments have the same name, i.e. are the same variable.
        if args[0] == args[1]:
            if op in ("eq", "le", "ge"):
                return True
            return False
    elif op in ("and", "or", "not"):
        # "and" and "or" can be folded if one of the arguments has certain constant value.
        if op == "and" and (vals[0] is False or vals[1] is False):
            return False
        if op == "or" and (vals[0] is True or vals[1] is True):
            return True
    else:
        assert False and "internal error: unhandled foldable operator"

    if not all(is_const(val) for val in vals):
        return None
    return EVAL_OPS[op](*vals)


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
    var2const = in_.copy()  # not to modify the input
    for instr in b:
        if "op" not in instr or "dest" not in instr:
            continue

        op: str = instr["op"]
        dest: str = instr["dest"]
        if op == "const":
            var2const[dest] = instr["value"]
        elif op == "id" and is_const(var2const.get(instr["args"][0], UNKNOWN)):
            # Propagate the constant.
            var2const[dest] = var2const[instr["args"][0]]
        elif (res := fold(instr, var2const)) is not None:
            var2const[dest] = res
        else:
            # Assigned with a non-constant variable; no longer a constant.
            var2const[dest] = UNKNOWN
    return var2const
