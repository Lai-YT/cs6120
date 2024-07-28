#!/usr/bin/env python3
"""The basic local value numbering."""

import argparse
import json
import sys
from collections import namedtuple
from typing import Any, Dict, List, Tuple, Union

from cfg import form_blocks, name_blocks
from cprop import is_const, lookup
from df import Analysis, DataFlowSolver
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
    return op in ("add", "mul", "eq", "and", "or")


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
        row_nums = tuple(sorted(row_nums, key=lambda x: str(x)))
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


def lvn(cprop: bool = False) -> None:
    prog: Dict[str, List[Dict[str, Any]]] = json.load(sys.stdin)

    for func in prog["functions"]:
        cprop_solver = DataFlowSolver(func["instrs"], Analysis.CPROP)
        in_consts, out_consts = cprop_solver.solve()
        # The l of lvn is for local.
        for block_name, block in name_blocks(form_blocks(func["instrs"])).items():
            row_num = 0
            # Map the tuple value to its canonical variable.
            # A value consists of an operator, along with its row number (or constant value).
            val2var: Dict[Value, str] = {}
            # Map the variable to the row number of its value.
            var2num: Dict[str, int] = {}
            # Map the row number to the canonical variable.
            num2var: Dict[int, str] = {}
            # Map the variable to its constant value, or unknown if not a constant.
            var2const = in_consts[block_name]

            def replace_args_with_canonical(instr: Instr) -> None:
                for i, arg in enumerate(instr.get("args", [])):
                    # Def of arg is in other basic block; not to touch it.
                    if arg not in var2num:
                        continue
                    the_row_num = var2num[arg]
                    instr["args"][i] = num2var[the_row_num]

            # Used to rename variables that are reassigned.
            lvn_number = 0

            for i, instr in enumerate(block):
                if "label" in instr:
                    continue

                if "dest" not in instr:
                    # Not an assignment.
                    replace_args_with_canonical(instr)
                    continue

                if cprop:
                    const = lookup(instr, var2const)
                    var2const[instr["dest"]] = const
                    if is_const(const):
                        # Replace the instruction with a constant operation.
                        instr["op"] = "const"
                        instr["value"] = const
                        instr.pop("args", None)

                if instr["op"] == "id" and instr["args"][0] not in var2num:
                    # The argument is defined in other basic blocks or is an input argument.
                    # Create a dummy value for it, which is an id operation on itself.
                    # This exploits more copy propagation opportunities.
                    arg = instr["args"][0]
                    # However, since there isn't an actual id operation, we cannot renamed it when its later reassigned. In such cases, we don't create a value for it.
                    # TODO: This is too conservative. If there's no use after the reassignment (but may at the successors), we can still add it.
                    if not any(
                        "dest" in later_instr and later_instr["dest"] == arg
                        for later_instr in block[i:]
                    ):
                        val2var[Value("id", (row_num,))] = arg
                        var2num[arg] = row_num
                        num2var[row_num] = arg
                        row_num += 1

                replace_args_with_canonical(instr)
                val: Value = extract_value_repr(instr, var2num)

                if val in val2var and not has_side_effect(val.op):
                    # The value has been computed before;
                    # map it to the canonical variable without adding a new row.
                    the_row_num = var2num[val2var[val]]
                    if val.op != "const":
                        # Replace the instruction as directly using the canonical variable to eliminate the computation.
                        instr["op"] = "id"
                        instr["args"] = [val2var[val]]
                else:
                    # If the variable is going to be reassigned, we give it an unique name so that the value is correct when later instructions use it as the canonical variable.
                    dest = rename_if_will_be_reassigned(
                        instr, block[i + 1 :], lvn_number
                    )
                    if dest != instr["dest"]:
                        # Update the constant mapping to use the new name.
                        if cprop:
                            var2const[dest] = var2const.pop(instr["dest"])

                        instr["dest"] = dest
                        lvn_number += 1

                    # For an id operation, the canonical variable is the argument. This allows copy propagation.
                    if val.op == "id" and instr["args"][0] in var2num:
                        the_row_num = var2num[instr["args"][0]]
                    else:
                        # A new value.
                        the_row_num = row_num
                        row_num += 1
                        num2var[the_row_num] = dest
                    val2var[val] = num2var[the_row_num]

                var2num[instr["dest"]] = the_row_num

            if cprop:
                # Ensure that we performed the constant propagation correctly.
                # NOTE: When there are reassignments, our mapping contains additional renamed variables. Variables other than these should have the same value.
                for k, v in out_consts[block_name].items():
                    assert var2const[k] == v

    json.dump(prog, indent=2, fp=sys.stdout)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(sys.argv[0])
    parser.add_argument(
        "-c",
        "--cprop",
        help="enable constant propagation and constant folding",
        action="store_true",
    )
    args = parser.parse_args()
    lvn(args.cprop)
