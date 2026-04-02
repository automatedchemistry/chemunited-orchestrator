from typing import Union

from .component.component_factory import ElectronicManager, UtensilManager


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
