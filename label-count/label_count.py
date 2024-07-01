"""
Prints out the label count for each of the functions in the program.
"""

__version__ = "0.1.0"

import json
import sys
from typing import Any, Dict, List, Mapping, TypeAlias

Instr: TypeAlias = Mapping[str, Any]


def label_count(instrs: List[Instr]) -> int:
    count = 0
    for instr in instrs:
        if "op" not in instr:
            count += 1
    return count


# Command-line entry points.


def main() -> None:
    prog: Dict[str, List[Dict[str, Any]]] = json.load(sys.stdin)

    print("Label Count:")
    for func in prog["functions"]:
        print(f"\t@{func['name']}: {label_count(func['instrs'])}")
