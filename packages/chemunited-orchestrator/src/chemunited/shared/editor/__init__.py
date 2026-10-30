"""Editor configuration and utilities."""

# Editor selection flag
# Set to True to use Monaco Editor instead of QScintilla
USE_MONACO_EDITOR = True

# Monaco Editor settings
MONACO_SETTINGS = {
    "fontSize": 14,
    "minimap": True,
    "autosave": True,
    "autosaveDelay": 2000,  # milliseconds
    "theme": "auto",  # "auto", "dark", or "light"
    "folding": True,
    "wordWrap": False,
    "rulers": [],  # Column rulers, e.g., [80, 100]
}


def get_editor_class():
    """Get the appropriate editor class based on configuration."""
    if USE_MONACO_EDITOR:
        try:
            from chemunited.shared.editor.monaco_base import MonacoEditorBase

            return MonacoEditorBase
        except ImportError as e:
            print(
                f"Warning: Monaco Editor not available ({e}), falling back to QScintilla"
            )
            from chemunited.shared.editor.base import EditorBase

            return EditorBase
    else:
        from chemunited.shared.editor.base import EditorBase

        return EditorBase


def get_script_editor_class():
    """Get the appropriate script editor class based on configuration."""
    if USE_MONACO_EDITOR:
        try:
            from chemunited.shared.editor.monaco_script import MonacoScriptEditor

            return MonacoScriptEditor
        except ImportError as e:
            print(
                f"Warning: Monaco Script Editor not available ({e}), falling back to QScintilla"
            )
            from chemunited.shared.editor.protocols.script import ScriptEditor

            return ScriptEditor
    else:
        from chemunited.shared.editor.protocols.script import ScriptEditor

        return ScriptEditor


def get_process_editor_window_class():
    """Get the appropriate process editor window class based on configuration."""
    if USE_MONACO_EDITOR:
        try:
            from chemunited.protocols.workflows.monaco_editor import (
                MonacoProcessScriptEditorWindow,
            )

            return MonacoProcessScriptEditorWindow
        except ImportError as e:
            print(
                f"Warning: Monaco Process Editor not available ({e}), falling back to QScintilla"
            )
            from chemunited.protocols.workflows.editor import ProcessScriptEditorWindow

            return ProcessScriptEditorWindow
    else:
        from chemunited.protocols.workflows.editor import ProcessScriptEditorWindow

        return ProcessScriptEditorWindow
