from typing import Any, List, MutableMapping, TypeAlias

Instr: TypeAlias = MutableMapping[str, Any]
Block: TypeAlias = List[Instr]
