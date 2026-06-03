from pydantic import BaseModel, Field, field_validator

from chemunited_core.utils.internal_quantity import ChemUnitQuantity


class BasicVariableBuildMode(BaseModel):
    """Base information shared by all variable types."""

    name: str = Field(
        default="x",
        title="Variable Name",
        description="Name of the variable (letters, digits, underscores; must not start with a digit).",
        pattern=r"^[A-Za-z_][A-Za-z0-9_]*$",
        json_schema_extra={"group": "General"},
    )

    title: str = Field(
        default="",
        title="Variable Title",
        description="Label that will appear in the GUI for this variable.",
        json_schema_extra={"group": "General"},
    )

    description: str = Field(
        default="",
        title="Variable Description",
        description="Short description of what this variable represents.",
        json_schema_extra={"group": "General"},
    )

    group: str = Field(
        default="General",
        title="Group",
        description="Name of the group where this variable appears (for organization).",
        json_schema_extra={"group": "Organization", "extra": True},
    )

    editable: bool = Field(
        default=True,
        title="Editable",
        description="Whether the variable can be edited by the user (default: True).",
        json_schema_extra={"group": "Behavior", "extra": True},
    )

    visible: bool = Field(
        default=True,
        title="Visible",
        description="Whether the variable is visible to the user (default: True).",
        json_schema_extra={"group": "Behavior", "extra": True},
    )


class StringVariableBuildMode(BasicVariableBuildMode):
    """Configuration for string variables."""

    default: str = Field(
        default="",
        title="Default Value",
        description="Initial value for this variable.",
        json_schema_extra={"group": "General"},
    )

    pattern: str = Field(
        default="",
        title="Validation Pattern (Regex)",
        description="Regular expression to validate input (optional).",
        json_schema_extra={"group": "Validation"},
    )

    min_length: int = Field(
        default=1,
        title="Minimum Length",
        description="Minimum allowed length of the string (in characters).",
        ge=0,
        json_schema_extra={"group": "Validation"},
    )

    max_length: int = Field(
        default=50,
        title="Maximum Length",
        description="Maximum allowed length of the string (in characters).",
        ge=1,
        json_schema_extra={"group": "Validation"},
    )


class IntVariableBuildMode(BasicVariableBuildMode):
    default: int = Field(
        default=0, title="Default Value", json_schema_extra={"group": "General"}
    )
    ge: int = Field(
        default=0, title="Minimum Value", json_schema_extra={"group": "Validation"}
    )
    le: int = Field(
        default=100, title="Maximum Value", json_schema_extra={"group": "Validation"}
    )


class FloatVariableBuildMode(BasicVariableBuildMode):
    default: float = Field(
        default=0.0, title="Default Value", json_schema_extra={"group": "General"}
    )
    ge: float = Field(
        default=0, title="Minimum Value", json_schema_extra={"group": "Validation"}
    )
    le: float = Field(
        default=100, title="Maximum Value", json_schema_extra={"group": "Validation"}
    )


class BoolVariableBuildMode(BasicVariableBuildMode):
    """Configuration for boolean variables."""

    default: bool = Field(
        default=False,
        title="Default Value",
        json_schema_extra={"group": "General"},
    )

    on_text: str = Field(
        default="On",
        title="On Text",
        description="Caption shown when the switch is enabled.",
        json_schema_extra={"group": "Display"},
    )

    off_text: str = Field(
        default="Off",
        title="Off Text",
        description="Caption shown when the switch is disabled.",
        json_schema_extra={"group": "Display"},
    )


class ListVariableBuildMode(BasicVariableBuildMode):
    default: list = Field(
        default=["A", "B", "C"], json_schema_extra={"group": "General"}
    )
    min_items: int = Field(
        default=0, title="Minimum Items", json_schema_extra={"group": "Validation"}
    )
    max_items: int = Field(
        default=10, title="Maximum Items", json_schema_extra={"group": "Validation"}
    )


class ChoiceVariableBuildMode(BasicVariableBuildMode):
    default: str = Field(default="", json_schema_extra={"group": "General"})
    Options: list = Field(
        default=[], json_schema_extra={"group": "General", "extra": True}
    )
    multi: bool = Field(
        default=False,
        title="Multiple choices",
        description="Allow multiple choices",
        json_schema_extra={"group": "General", "extra": True},
    )


class PhysicalQuantitiesMode(BasicVariableBuildMode):
    """Configuration for physical quantity variables."""

    unit: str = Field(
        default="ml",
        title="Unit",
        description="Pint-compatible unit string, e.g. 'ml', 's', 'bar', 'ml/min'.",
        json_schema_extra={"group": "General"},
    )

    default: str = Field(
        default="0 ml",
        title="Default Value",
        description="Initial value for this variable with unit.",
        json_schema_extra={"group": "General"},
    )

    @field_validator("default")
    def validate_quantity_string(cls, v):
        """
        Validate that the provided string is a valid Pint quantity.
        Examples of valid input: '0 ml', '5.2 g', '300 K', '1.5 mol/L'
        """
        if not isinstance(v, str):
            raise ValueError(
                "Value must be a string representing a quantity, e.g. '5 ml'."
            )
        try:
            # Pint will parse "value unit" into a Quantity
            u = ChemUnitQuantity(v)
            if not isinstance(u, ChemUnitQuantity):
                raise ValueError(
                    "The value provided can not be converted into a ChemUnitQuantity!"
                )
        except Exception as e:
            raise ValueError(
                f"Invalid quantity string '{v}'. Must be parseable by Pint. Error: {e}"
            )
        return v
