"""Editor configuration and utilities."""


def get_editor_class():
    """Get the editor widget class (Monaco)."""
    from chemunited.shared.editor.monaco_base import MonacoEditorBase

    return MonacoEditorBase


def get_script_editor_class():
    """Get the script editor widget class (Monaco)."""
    from chemunited.shared.editor.monaco_script import MonacoScriptEditor

    return MonacoScriptEditor


def get_process_editor_window_class():
    """Get the process editor window class (Monaco)."""
    from chemunited.protocols.workflows.monaco_editor import (
        MonacoProcessScriptEditorWindow,
    )

    return MonacoProcessScriptEditorWindow
