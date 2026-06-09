from __future__ import annotations

from PyQt5.QtCore import QMimeData

from chemunited.qt.shared.editor.protocols.command_list import CommandList
from chemunited.qt.shared.editor.protocols.script import (
    _build_statement_insert_text,
    _drop_text_from_mime,
    _insertion_for_method_end_drop,
)

SOURCE = """\
class CustomProcess:
    def script_1(self, ctx: NodeExecutionContext) -> bool:
        ctx.runtime.status_message = "Script 1 ran."
        self.platform['AS injection'].put(
            'position',
            connect='[[1, 2]]',
            disconnect='',
        )
        return True
"""

SNIPPET = (
    "self.platform['AS injection'].put("
    "'position', connect='[[1, 4]]', disconnect=''"
    ")"
)


def _line_index(text: str, needle: str) -> int:
    return next(index for index, line in enumerate(text.splitlines()) if needle in line)


def _insert(source: str, drop_line: int) -> str:
    insertion = _insertion_for_method_end_drop(source, drop_line)
    assert insertion is not None
    insert_line, indent = insertion
    lines = source.splitlines(keepends=True)
    lines.insert(insert_line, _build_statement_insert_text(SNIPPET, indent, "\n"))
    return "".join(lines)


def test_drop_on_method_header_inserts_before_final_return() -> None:
    result = _insert(SOURCE, _line_index(SOURCE, "def script_1"))

    assert result.index("disconnect='',\n        )") < result.index(SNIPPET)
    assert result.index(SNIPPET) < result.index("return True")


def test_drop_inside_method_signature_inserts_before_final_return() -> None:
    source = """\
class CustomProcess:
    def script_1(
        self,
        ctx: NodeExecutionContext,
    ) -> bool:
        ctx.runtime.status_message = "Script 1 ran."
        return True
"""

    result = _insert(source, _line_index(source, "ctx: NodeExecutionContext"))

    assert result.index("ctx.runtime.status_message") < result.index(SNIPPET)
    assert result.index(SNIPPET) < result.index("return True")


def test_drop_inside_call_inserts_before_final_return() -> None:
    result = _insert(SOURCE, _line_index(SOURCE, "connect='[[1, 2]]'"))

    assert result.index("disconnect='',\n        )") < result.index(SNIPPET)
    assert result.index(SNIPPET) < result.index("return True")


def test_drop_on_return_inserts_above_return() -> None:
    result = _insert(SOURCE, _line_index(SOURCE, "return True"))

    assert result.index(SNIPPET) < result.index("return True")


def test_method_without_final_return_inserts_after_last_body_statement() -> None:
    source = """\
class CustomProcess:
    def script_1(self, ctx: NodeExecutionContext) -> bool:
        ctx.runtime.status_message = "Script 1 ran."
        self.platform['AS injection'].put('position')
"""

    result = _insert(source, _line_index(source, "ctx.runtime.status_message"))

    assert result.index("self.platform['AS injection'].put('position')") < result.index(
        SNIPPET
    )


def test_drop_outside_method_has_no_insertion_target() -> None:
    insertion = _insertion_for_method_end_drop(
        SOURCE,
        _line_index(SOURCE, "class CustomProcess"),
    )

    assert insertion is None


def test_command_mime_takes_priority_over_indented_plain_text() -> None:
    mime_data = QMimeData()
    mime_data.setData(CommandList.MIME, SNIPPET.encode("utf-8"))
    mime_data.setText(f"\n        {SNIPPET}")

    assert _drop_text_from_mime(mime_data) == SNIPPET
