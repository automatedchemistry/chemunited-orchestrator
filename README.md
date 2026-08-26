# chemunited-quantities

Lab-aware physical quantity primitive for the chemunited ecosystem.

Wraps [pint](https://pint.readthedocs.io/) with a chemistry-domain unit registry,
offset temperature handling (degC aliases), and Pydantic integration via
[pydantic-pint](https://github.com/tylerteichmann/pydantic-pint).

## Installation

```bash
pip install chemunited-quantities
```

## Usage

```python
from chemunited_quantities import ChemUnitQuantity

q = ChemUnitQuantity("5 ml")
print(q + ChemUnitQuantity("3 ml"))  # 8 milliliter

temp = ChemUnitQuantity("25 degC")
print(temp)
```

## License

MIT
