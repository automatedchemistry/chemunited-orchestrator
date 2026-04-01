from dataclasses import dataclass
from typing import override

from ..component import ComponentData


@dataclass
class NeutralComponentData(ComponentData):
    @override
    def internal_structure(self):
        pass
