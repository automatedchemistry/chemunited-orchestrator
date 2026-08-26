from importlib import import_module


def test_public_packages_import() -> None:
    module_names = [
        "chemunited_core.common",
        "chemunited_core.compounds",
        "chemunited_core.components",
        "chemunited_core.connections",
        "chemunited_core.utils",
        "chemunited_core.protocols",
    ]

    for module_name in module_names:
        assert import_module(module_name).__name__ == module_name
