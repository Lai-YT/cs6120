#!/usr/bin/env python3
"""The basic local value numbering."""

import argparse
import json
import sys
from collections import namedtuple
from typing import Any, Dict, List, Tuple, Union

from cfg import form_blocks
from type import Instr

Value = namedtuple("Value", ["op", "args"])


def rename_args_between(instrs: List[Instr], old_name: str, new_name: str) -> None:
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


def extract_value_repr(instr: Instr, var2num: Dict[str, int]) -> Value:
    """
    Returns:
        A Value namedtuple containing the operation and its arguments.
        For constant operations, the tuple includes the constant value and type.
        For other operations, the arguments are replaced with their corresponding
        row numbers if available, and sorted if the operation is commutative.
    """
    if instr["op"] == "const":
        # NOTE: Since False is equal to 0 in Python, we have to include the type.
        return Value("const", (instr["value"], instr["type"]))
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
        return Value(*sorted(row_nums, key=lambda x: str(x)))
    return Value(op, row_nums)


def rename_if_will_be_reassigned(
    instr: Instr, later_instrs: List[Instr], next_lvn_number: int
) -> str:
    """Renames a variable if it will be reassigned in subsequent instructions.

    Checks if the destination variable of the given instruction will be
    reassigned in any of the later instructions. If so, generates a new
    unique name for the variable and updates all references to the variable
    in the instructions up to and including the reassignment.

    Args:
        instr: The current instruction whose destination variable may be reassigned.
        later_instrs: A list of subsequent instructions to check for reassignment.
        next_lvn_number: The next available unique number for renaming variables.

    Returns:
        The new name of the variable if it was reassigned, otherwise the original name.
    """
    for i, later_instr in enumerate(later_instrs):  # peek the later instructions
        if instr["dest"] == later_instr.get("dest", None):
            new_name = f"{instr['dest']}.{next_lvn_number}"
            # all args between should be updated to use the new name.
            # i + 1 because may be used in the reassignment.
            rename_args_between(later_instrs[: i + 1], instr["dest"], new_name)
            return new_name
    return instr["dest"]


def lvn() -> None:
    prog: Dict[str, List[Dict[str, Any]]] = json.load(sys.stdin)

    for func in prog["functions"]:
        # The l of lvn is for local.
        for block in form_blocks(func["instrs"]):
            row_num = 0
            # Map the tuple value to its canonical variable with the row number wrapped together.
            # A value consists of an operator, along with its row number (or constant value).
            val2var: Dict[Value, Tuple[str, int]] = {}
            # Map the variable to the row number of its value.
            var2num: Dict[str, int] = {}

            def replace_args_with_canonical(instr: Instr) -> None:
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

                replace_args_with_canonical(instr)
                val: Value = extract_value_repr(instr, var2num)

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
                    dest = rename_if_will_be_reassigned(
                        instr, block[i + 1 :], lvn_number
                    )
                    if dest != instr["dest"]:
                        instr["dest"] = dest
                        lvn_number += 1

                    # A new value.
                    the_row_num = row_num
                    row_num += 1
                    val2var[val] = dest, the_row_num

                var2num[instr["dest"]] = the_row_num

    json.dump(prog, indent=2, fp=sys.stdout)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(sys.argv[0])
    parser.parse_args()
    lvn()
