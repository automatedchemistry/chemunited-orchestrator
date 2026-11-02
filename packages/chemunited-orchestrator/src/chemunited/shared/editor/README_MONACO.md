# Monaco Editor Integration

This directory contains the Monaco Editor integration for the ChemUnited Orchestrator. Monaco Editor is the same code editor engine that powers VS Code, providing a rich IDE-like experience.

## Features

✅ **VS Code Experience**
- IntelliSense and auto-completion
- Syntax highlighting for Python and 100+ languages
- Code folding and minimap
- Bracket matching and auto-closing
- Multi-cursor editing
- Find/Replace with regex support

✅ **Integration Features**
- Dark/Light theme support (follows the application theme: the Setup window's
  Theme menu with Follow System / Dark / Light; the editor re-themes live when
  the app theme changes)
- Method focusing: the cursor jumps to the block's method when a node is opened
- Auto-save with debouncing
- Drag-and-drop support for commands and parameters
- Black code formatting
- Same API as QScintilla-based editor

✅ **Tabs (IDE Mode)**
- Multiple scripts open at once as editor tabs (Monaco models)
- Per-tab dirty state with autosave; dirty tabs save on close
- Window reuse: double-clicking a different process opens a tab
  in the same window instead of a new window
- Last tab can never be closed (keeps Python's path binding safe)

✅ **IDE-like Features**
- Go to definition (Ctrl+Click)
- Find references
- Peek definition
- Quick fix suggestions
- Parameter hints
- Hover documentation

## Installation

Monaco Editor requires PyQt5 WebEngine:

```bash
pip install PyQtWebEngine
# or with uv (project venv):
uv pip install --python .venv/Scripts/python.exe PyQtWebEngine
```

### Two hard constraints (learned the hard way)

1. **Import order**: PyQt5 requires `QtWebEngineWidgets` to be imported
   *before* `QApplication` is created. The app entry point
   (`chemunited/__main__.py`) already does this with a guarded import —
   don't remove it.

2. **Monaco version is pinned to 0.22.3** (vendored in
   `shared/resources/monaco/vs/`). QtWebEngine 5.15 ships Chromium 87,
   which cannot parse newer Monaco bundles (they use class static blocks,
   Chrome 93+ syntax) — the script fails with `SyntaxError` and the editor
   silently never appears. If you ever upgrade to Qt6/PySide6, you can
   bump Monaco to the latest.

3. **Bridge methods need `@pyqtSlot`**: QWebChannel only exposes
   `@pyqtSlot`-decorated methods and signals to JavaScript — plain Python
   methods are invisible in JS.

## Usage

### Basic Usage

Replace your existing `EditorBase` import with `MonacoEditorBase`:

```python
# Old
from chemunited.shared.editor.base import EditorBase

# New
from chemunited.shared.editor.monaco_base import MonacoEditorBase

# Usage is identical
editor = MonacoEditorBase(parent=self, path=file_path)
```

### Process Script Editor

For process-specific editors with method focusing:

```python
# Old
from chemunited.protocols.workflows.editor import ProcessScriptEditorWindow

# New
from chemunited.protocols.workflows.monaco_editor import MonacoProcessScriptEditorWindow

# Usage is identical
window = MonacoProcessScriptEditorWindow(
    path=script_path,
    class_name="CustomProcess",
    parent=self,
)
window.focus_method("run")
window.show()
```

### API Compatibility

The Monaco editor provides the same API as the QScintilla editor:

| Method | QScintilla | Monaco |
|--------|-----------|--------|
| Get text | `editor.text()` | `editor.text()` |
| Set text | `editor.setText(str)` | `editor.setText(str)` |
| Cursor position | `editor.getCursorPosition()` | `editor.getCursorPosition()` |
| Set cursor | `editor.setCursorPosition(line, col)` | `editor.setCursorPosition(line, col)` |
| Insert text | `editor.insertAt(text, line, col)` | `editor.insertAt(text, line, col)` |
| Get selection | `editor.getSelection()` | `editor.getSelection()` |
| Undo | `editor.undo()` | `editor.undo()` |
| Redo | `editor.redo()` | `editor.redo()` |
| Find | `editor.find()` | `editor.find()` |
| Autosave | `editor.set_autosave(bool)` | `editor.set_autosave(bool)` |
| Save now | `editor.save_now()` | `editor.save_now()` |

`focus_method(name)` moves the cursor to the method's body on both window
types; the code itself is never restyled or locked.

## Keyboard Shortcuts

Monaco Editor supports all standard VS Code shortcuts:

- `Ctrl+S` - Save
- `Ctrl+F` - Find
- `Ctrl+H` - Replace
- `Ctrl+D` - Select next occurrence
- `Ctrl+Shift+L` - Select all occurrences
- `Alt+Click` - Add cursor
- `Ctrl+/` - Toggle line comment
- `Ctrl+Shift+P` - Command palette
- `F12` - Go to definition
- `Shift+F12` - Show references
- `Ctrl+` ` - Toggle terminal (if integrated)

## Customization

### Themes

The editor automatically detects your system theme (light/dark). You can also set it manually:

```python
# In your initialization code
from qfluentwidgets import isDarkTheme
theme = "dark" if isDarkTheme() else "light"
editor._call_js(f"monacoEditor.setTheme('{theme}')")
```

### Editor Options

You can customize Monaco Editor options by modifying the `editor.html` file:

```javascript
// In editor.html, modify the editor creation options
editor = monaco.editor.create(document.getElementById('container'), {
    // ... existing options
    fontSize: 16,              // Change font size
    minimap: { enabled: false }, // Disable minimap
    wordWrap: 'on',            // Enable word wrap
    rulers: [80, 100],        // Add column rulers
});
```

### Adding Language Support

Monaco supports 100+ languages out of the box. To add completions for a specific language:

```javascript
// In editor.html, add language-specific completions
monaco.languages.registerCompletionItemProvider('python', {
    provideCompletionItems: function(model, position) {
        return {
            suggestions: [
                {
                    label: 'my_custom_function',
                    kind: monaco.languages.CompletionItemKind.Function,
                    insertText: 'my_custom_function(${1:args})',
                    insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
                }
            ]
        };
    }
});
```

## Migration Guide

### Step 1: Install Dependencies

```bash
pip install PyQt5-WebEngine
```

### Step 2: Test Monaco Editor

Run the test script:

```bash
python -m chemunited.shared.editor.monaco_base
```

### Step 3: Replace Editor Classes

In your workflow frames or editor code:

```python
# Option A: Use Monaco for new windows only
from chemunited.protocols.workflows.monaco_editor import MonacoProcessScriptEditorWindow

if use_monaco:
    self._script_editor = MonacoProcessScriptEditorWindow(...)
else:
    self._script_editor = ProcessScriptEditorWindow(...)

# Option B: Complete replacement (update imports)
# Find and replace:
# - EditorBase → MonacoEditorBase
# - ScriptEditor → MonacoScriptEditor
# - ProcessScriptEditorWindow → MonacoProcessScriptEditorWindow
```

### Step 4: Test Thoroughly

Test all editor features:
- ✅ Opening files
- ✅ Editing and saving
- ✅ Method focusing (cursor jump)
- ✅ Drag-and-drop
- ✅ Code formatting
- ✅ Auto-save

## Troubleshooting

### Editor doesn't load

1. Check if PyQt5-WebEngine is installed: `pip show PyQt5-WebEngine`
2. Verify the `editor.html` file exists in the resources/monaco directory
3. Check the application logs for load errors

### Text doesn't appear

1. Ensure the file path is correct
2. Check file encoding (should be UTF-8)
3. Verify the Monaco loader is working (check browser console if debugging)

### Cursor doesn't jump to the method

1. Method focusing waits for the Monaco page to load; it is replayed when
   the editor is ready
2. Verify the method exists in the file

### Performance issues

Monaco Editor is heavier than QScintilla. If you experience performance issues:

1. Disable minimap: `minimap: { enabled: false }`
2. Reduce font size
3. Disable some editor features in `editor.html`

## Advanced Features

### Tabs (shipped)

The tab bar renders inside the same Monaco WebView (`editor.html`); each
open file is a Monaco *model* in one renderer process, so tab switching is
instant and memory-light. Files open only as requested by the application
(there is no file browser).

Python controls (all optional):

```python
# Open/activate another file as a tab (reuses the window)
win.open_file(other_script, class_name="OtherProcess")

# Signal fired whenever the active tab changes
win.editor.active_file_changed.connect(lambda path: ...)
```

Bridge slot (QWebChannel, `@pyqtSlot(str, result=str)`): `readFile(path)`
returns a JSON string `{ok: True, content, error?}` and is used when a file
is opened in a new tab; `onTextChanged(path, content)` and
`onActiveFileChanged(path, content)` keep Python-side caches tracking the
*active* file.

### Git Integration

Monaco Editor can integrate with Git for version control:

1. Use `monaco-editor-diff` for showing diffs
2. Integrate with GitPython for repository operations

### Extensions

Monaco supports extensions similar to VS Code. You can add:

- Linting (pylint, flake8)
- Code formatting (black, isort)
- Debugging integration
- Terminal integration

## Resources

- [Monaco Editor Documentation](https://microsoft.github.io/monaco-editor/)
- [Monaco Editor API](https://microsoft.github.io/monaco-editor/api/index.html)
- [PyQt5 WebEngine Docs](https://www.riverbankcomputing.com/static/Docs/PyQt5/QtWebEngine/)
- [VS Code Keyboard Shortcuts](https://code.visualstudio.com/docs/getstarted/keybindings)

## Contributing

When contributing to the Monaco integration:

1. Maintain API compatibility with QScintilla editor
2. Test both light and dark themes
3. Ensure method focusing (cursor jump) works correctly
4. Verify drag-and-drop functionality
5. Test with large files (>1000 lines)

## License

Same as the main ChemUnited Orchestrator project.
