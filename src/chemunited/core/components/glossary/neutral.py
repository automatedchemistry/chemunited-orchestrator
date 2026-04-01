from ..component import ComponentData
from dataclasses import dataclass
from typing import override

@dataclass
class NeutralComponentData(ComponentData):

    @override
    def internal_structure(self):
        pass