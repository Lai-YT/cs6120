"""This module defines the basic local value numbering.

Constant propagation and folding are not supported.
"""

__version__ = "0.1.0"

import json
import sys
from collections import namedtuple
from typing import Any, Dict, List, Tuple, Union

import cfg

Value = namedtuple("Value", ["op", "args"])


def rename_args_between(instrs: List[cfg.Instr], old_name: str, new_name: str) -> None:
    for instr in instrs:
        args = instr.get("args", [])
        for i, arg in enumerate(args):
            if arg == old_name:
                args[i] = new_name


def has_side_effect(op: str) -> bool:
    """Returns whether the `op` may have side effect."""
    return op == "call"


def is_commutative(op: str) -> bool:
    # No short circuit for "add" and "or" at this level.
    return op in ("add", "mul", "eq", "add", "or")


def lvn() -> None:
    prog: Dict[str, List[Dict[str, Any]]] = json.load(sys.stdin)

    for func in prog["functions"]:
        # The l of lvn is for local.
        for block in cfg.form_blocks(func["instrs"]):
            row_num = 0
            # Map the tuple value to its canonical variable with the row number wrapped together.
            # A value consists of an operator, along with its row number (or constant value).
            val2var: Dict[Value, Tuple[str, int]] = {}
            # Map the variable to the row number of its value.
            var2num: Dict[str, int] = {}

            def replace_args_with_canonical(instr: cfg.Instr) -> None:
                for i, arg in enumerate(instr.get("args", [])):
                    # Def of arg is in other basic block; not to touch it.
                    if arg not in var2num:
                        continue
                    the_row_num = var2num[arg]
                    # NOTE: This requires the dict to be ordered, and the row number must exactly match the ordered we added.
                    var, _ = list(val2var.values())[the_row_num]
                    instr["args"][i] = var

            # Used to rename variables that are reassigned.
            lvn_number = 0

            for i, instr in enumerate(block):
                if "label" in instr:
                    continue

                if "dest" not in instr:
                    # Not an assignment.
                    replace_args_with_canonical(instr)
                    continue

                if instr["op"] == "const":
                    # NOTE: Since False is equal to 0 in Python, we have to include the type.
                    val = Value("const", (instr["value"], instr["type"]))
                else:
                    # NOTE: If the variable isn't record, it's because such variable is defined in another basic block.
                    # In such case, there's no column number, we use the variable name directly in the tuple value.

                    # For function calls, we postfix the function name to the op to differentiate.
                    op = instr["op"]
                    if "funcs" in instr:
                        op += instr["funcs"][0]

                    # Lookup the row numbers of the operands.
                    row_nums: Tuple[Union[str, int], ...] = tuple(
                        var2num.get(arg, arg) for arg in instr["args"]
                    )
                    if is_commutative(op):
                        # Commutativity; sort the args to canonicalize.
                        # NOTE: Row numbers can be str if is defined in other basic block.
                        val = Value(*sorted(row_nums, key=lambda x: str(x)))
                    val = Value(op, row_nums)

                if val in val2var and not has_side_effect(val.op):
                    # The value has been computed before;
                    # map it to the canonical variable without adding a new row.
                    var, the_row_num = val2var[val]
                    if val.op != "const":
                        # Replace the instruction as directly using the canonical variable to eliminate the computation.
                        instr["op"] = "id"
                        instr["args"] = [var]
                else:
                    # If the variable is going to be reassigned, we give it an unique name so that the value is correct when later instructions use it as the canonical variable.
                    dest = instr["dest"]
                    for j in range(i + 1, len(block)):  # peek the later instructions
                        later_instr = block[j]
                        if dest == later_instr.get("dest", None):
                            new_name = f"{dest}.{lvn_number}"
                            lvn_number += 1
                            # all args between should be updated to use the new name.
                            # j + 1 because may be used in the reassignment.
                            rename_args_between(block[i + 1 : j + 1], dest, new_name)
                            dest = new_name
                            instr["dest"] = dest
                            break

                    # A new value.
                    the_row_num = row_num
                    row_num += 1
                    val2var[val] = dest, the_row_num

                    replace_args_with_canonical(instr)

                var2num[instr["dest"]] = the_row_num

    json.dump(prog, indent=2, fp=sys.stdout)
