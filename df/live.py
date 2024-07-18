"""The Live Variables analysis.

- At the entry and exit of each basic block, the analysis determines which variables needs to be kept alive, as they will possibly be used later.
- This is a backward analysis with the equation: `IN(b) = Union(Defs(b), Uses(b) - Kills(b))`.
- For blocks with multiple successors, the sets are merged using `Union`.
"""

from typing import Set

from cfg import Block


def uses(b: Block) -> Set[str]:
    """Determines the set of variables used in a block.

    Args:
        b: The basic block being analyzed.

    Returns:
        A set of variable names that are used in the block.

    Note:
        The use of a variable is discarded if we see its reassignment and added if we see its use.
    """
    u: Set[str] = set()
    for instr in reversed(b):
        # Since we're going backward, check 'dest' (reassignment) first.
        if "dest" in instr:
            u.discard(instr["dest"])
        if "args" in instr:
            u.update(instr["args"])
    return u


def kills(b: Block) -> Set[str]:
    """Determines the set of variables killed in a block.

    Args:
        b: The basic block being analyzed.

    Returns:
        A set of variable names that are killed in the block.

    Note:
        A redefinition kills the previous use.
    """
    k: Set[str] = set()
    for instr in reversed(b):
        if "dest" in instr:
            k.add(instr["dest"])
    return k


def in_(b: Block, out: Set[str]) -> Set[str]:
    """Computes the IN set for a block, determining which variables are alive.

    Args:
        b: The basic block being analyzed.
        out: The OUT set of the block.

    Returns:
        The IN set of the block.

    Note:
        A variable is considered alive if it may be used later. If we see a use
        of it, we know it's live before the use. If we do not see a use, we do
        not add it to the IN set, which means it's alive only if it's already
        alive in the OUT set. If we see a reassignment, such a variable is dead
        between the previous use, which means if we didn't see a previous use,
        the variable will not be in the IN set, and so we clean them from the
        OUT set.
    """
    return uses(b).union(out - kills(b))
