from typing import (
    Any,
    Dict,
    Generator,
    Iterable,
    List,
    MutableMapping,
    OrderedDict,
    TypeAlias,
)

Instr: TypeAlias = MutableMapping[str, Any]
Block: TypeAlias = List[Instr]

def form_blocks(body: Iterable[Instr]) -> Generator[Block, None, None]: ...
def name_blocks(blocks: Iterable[Block]) -> OrderedDict[str, Block]: ...
def get_cfg(name_to_block: OrderedDict[str, Block]) -> Dict[str, List[str]]: ...
def graph(func_name: str, cfg: Dict[str, List[str]]) -> None: ...
