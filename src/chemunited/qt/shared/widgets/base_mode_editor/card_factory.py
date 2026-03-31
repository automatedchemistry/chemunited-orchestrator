from __future__ import annotations

import typing

from pydantic.fields import FieldInfo

from .cards.base_card import BaseFieldCard
from .cards.bool_card import BoolFieldCard
from .cards.choice_card import ChoiceFieldCard
from .cards.float_card import FloatFieldCard
from .cards.int_card import IntFieldCard
from .cards.list_card import ListFieldCard
from .cards.quantity_card import ChemUnitQuantityCard
from .cards.str_card import StrFieldCard


class CardFactory:
    """Builds the appropriate ``BaseFieldCard`` subclass for a given Pydantic field.

    Detection priority (first match wins):
    1. ``ChemQuantityValidator`` found in ``field_info.metadata``  → ChemUnitQuantityCard
    2. ``"Options"`` key in ``json_schema_extra``                  → ChoiceFieldCard
    3. annotation resolves to ``bool``                             → BoolFieldCard
    4. annotation resolves to ``int``                              → IntFieldCard
    5. annotation resolves to ``float``                            → FloatFieldCard
    6. annotation resolves to ``list[...]``                        → ListFieldCard
    7. fallback                                                    → StrFieldCard
    """

    @staticmethod
    def build(
        field_name: str,
        field_info: FieldInfo,
        parent: "QWidget | None" = None,
    ) -> BaseFieldCard:
        card = CardFactory._make_card(field_name, field_info, parent)

        # Apply visibility / editability from json_schema_extra
        extras = field_info.json_schema_extra or {}
        card.setVisible(bool(extras.get("visible", True)))
        card.setEnabled(bool(extras.get("editable", True)))

        return card

    @staticmethod
    def _make_card(
        field_name: str,
        field_info: FieldInfo,
        parent: "QWidget | None" = None,
    ) -> BaseFieldCard:
        # 1. ChemQuantityValidator in metadata
        try:
            from chemunited_core.utils import ChemQuantityValidator

            for meta in (field_info.metadata or []):
                if isinstance(meta, ChemQuantityValidator):
                    return ChemUnitQuantityCard(field_name, field_info, parent)
        except ImportError:
            pass

        # 2. Options in json_schema_extra
        extras = field_info.json_schema_extra or {}
        if "Options" in extras:
            return ChoiceFieldCard(field_name, field_info, parent)

        # 3–6. Resolve the annotation type
        annotation = field_info.annotation
        origin = typing.get_origin(annotation)

        # Unwrap Optional[X] / Union[X, None]
        if origin is typing.Union:
            args = [a for a in typing.get_args(annotation) if a is not type(None)]
            annotation = args[0] if args else annotation
            origin = typing.get_origin(annotation)

        if annotation is bool:
            return BoolFieldCard(field_name, field_info, parent)
        if annotation is int:
            return IntFieldCard(field_name, field_info, parent)
        if annotation is float:
            return FloatFieldCard(field_name, field_info, parent)
        if origin is list:
            return ListFieldCard(field_name, field_info, parent)

        return StrFieldCard(field_name, field_info, parent)
