"""The Reaching Definitions analysis.

- At the entry and exit of each basic block, the analysis determines which variable definitions are reachable.
- This is a forward analysis with the equation: `OUT(b) = Union(Defs(b), IN(b) - Kills(b))`.
- For blocks with multiple predecessors, the sets are merged using `Union`.
"""

from typing import Set

from cfg import Block


def defs(b: Block) -> Set[str]:
    """Returns the names of the variables defined in the block.

    Args:
        b: The basic block being analyzed.

    Returns:
        A set of variable names defined in the block.
    """
    d: Set[str] = set()
    for instr in b:
        if "dest" in instr:
            d.add(instr["dest"])
    return d


def kills(b: Block) -> Set[str]:
    """Returns the names of the variables killed in the block.

    Args:
        b: The basic block being analyzed.

    Returns:
        A set of variable names killed in the block.

    Note:
        A re-definition kills the previous definition.
        This implementation is identical to `defs()`.
    """
    k: Set[str] = set()
    for instr in b:
        if "dest" in instr:
            k.add(instr["dest"])
    return k


def out(b: Block, in_: Set[str]) -> Set[str]:
    """Computes the OUT set for a block.

    Args:
        b: The basic block being analyzed.
        in_: The IN set of the block.

    Returns:
        The OUT set of the block.
    """
    return defs(b).union(in_ - kills(b))
