from typing import Union

from chemunited_core.connections import ConnectionType

from .component.component_factory import ElectronicManager, UtensilManager
from .connection.connection import BaseConnectionItem


class Components:
    def __init__(self):
        self._utensil: dict[str, UtensilManager] = {}
        self._electronic: dict[str, ElectronicManager] = {}

    @property
    def utensil(self) -> dict[str, UtensilManager]:
        return self._utensil

    @property
    def electronic(self) -> dict[str, ElectronicManager]:
        return self._electronic

    def __getitem__(self, item: str):
        if item in self._utensil:
            return self._utensil[item]
        elif item in self._electronic:
            return self._electronic[item]
        else:
            raise KeyError(f"{item} not found in components.")

    def __setitem__(self, key: str, value: Union[UtensilManager, ElectronicManager]):
        if isinstance(value, ElectronicManager):
            self._electronic[key] = value
        elif isinstance(value, UtensilManager):
            self._utensil[key] = value
        else:
            raise ValueError("Value must be either UtensilManager or ElectronicManager")

    def __delitem__(self, key: str):
        if key in self._utensil:
            del self._utensil[key]
        elif key in self._electronic:
            del self._electronic[key]
        else:
            raise KeyError(f"{key} not found in components.")

    def __iter__(self):
        return iter(list(self._utensil) + list(self._electronic))

    def __len__(self):
        return len(self._utensil) + len(self._electronic)

    def __contains__(self, key):
        return key in self._utensil or key in self._electronic

    def keys(self):
        return list(self._utensil.keys()) + list(self._electronic.keys())

    def values(self):
        return list(self._utensil.values()) + list(self._electronic.values())

    def items(self):
        return list(self._utensil.items()) + list(self._electronic.items())

    def pop(self, key, default=None):
        if key in self._utensil:
            return self._utensil.pop(key)
        elif key in self._electronic:
            return self._electronic.pop(key)
        elif default is not None:
            return default
        else:
            raise KeyError(f"{key} not found in components")

    def get(self, key, default=None):
        if key in self._utensil:
            return self._utensil[key]
        elif key in self._electronic:
            return self._electronic[key]
        return default

    def clear(self):
        self._utensil.clear()
        self._electronic.clear()


_MISSING = object()


class Connections:
    def __init__(self):
        self._connection: dict[ConnectionType, dict[str, BaseConnectionItem]] = {
            ConnectionType.HYDRAULIC: {},
            ConnectionType.HEAT: {},
            ConnectionType.ELECTRONIC: {},
            ConnectionType.MOVEMENT: {},
        }

    # ── per-category views ────────────────────────────────────────────────

    @property
    def hydraulic(self) -> dict[str, BaseConnectionItem]:
        return self._connection[ConnectionType.HYDRAULIC]

    @property
    def heat(self) -> dict[str, BaseConnectionItem]:
        return self._connection[ConnectionType.HEAT]

    @property
    def electronic(self) -> dict[str, BaseConnectionItem]:
        return self._connection[ConnectionType.ELECTRONIC]

    @property
    def movement(self) -> dict[str, BaseConnectionItem]:
        return self._connection[ConnectionType.MOVEMENT]

    # ── internal helpers ──────────────────────────────────────────────────

    def _dicts(self):
        return self._connection.values()

    def connection_category(self, key: str) -> ConnectionType:
        for category, d in self._connection.items():
            if key in d:
                return category
        raise KeyError(f"{key} not found in connections.")

    # ── mapping protocol ──────────────────────────────────────────────────

    def __getitem__(self, key: str) -> BaseConnectionItem:
        for d in self._dicts():
            if key in d:
                return d[key]
        raise KeyError(f"{key} not found in connections.")

    def __setitem__(self, key: str, value: BaseConnectionItem) -> None:
        self._connection[value.CATEGORY][key] = value

    def __delitem__(self, key: str) -> None:
        del self._connection[self.connection_category(key)][key]

    def __iter__(self):
        for d in self._dicts():
            yield from d

    def __len__(self):
        return sum(len(d) for d in self._dicts())

    def __contains__(self, key):
        return any(key in d for d in self._dicts())

    def keys(self):
        return [k for d in self._dicts() for k in d]

    def values(self):
        return [v for d in self._dicts() for v in d.values()]

    def items(self):
        return [(k, v) for d in self._dicts() for k, v in d.items()]

    def pop(self, key, default=_MISSING):
        for d in self._dicts():
            if key in d:
                return d.pop(key)
        if default is _MISSING:
            raise KeyError(f"{key} not found in connections")
        return default

    def get(self, key, default=None):
        for d in self._dicts():
            if key in d:
                return d[key]
        return default

    def clear(self):
        for d in self._dicts():
            d.clear()
