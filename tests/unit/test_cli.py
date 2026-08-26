from __future__ import annotations

from pathlib import Path
import sys

from click.testing import CliRunner
import pytest

from chemunited_workflow import cli


def test_display_host_uses_loopback_for_unspecified_address():
    assert cli._display_host("0.0.0.0") == "127.0.0.1"


def test_display_host_wraps_ipv6_address():
    assert cli._display_host("::1") == "[::1]"


def test_display_host_preserves_hostname():
    assert cli._display_host("lab-machine.local") == "lab-machine.local"


def test_embedded_png_icon_can_be_loaded_from_svg(monkeypatch):
    pytest.importorskip("PIL")
    from PIL import Image

    monkeypatch.setattr(
        Path,
        "read_text",
        lambda self, encoding=None: (
            '<svg><image href="data:image/png;base64,'
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAFgwJ/"
            'lU4NfwAAAABJRU5ErkJggg=="/></svg>'
        ),
    )

    class OpenedImage:
        def __enter__(self):
            return Image.new("RGBA", (1, 1))

        def __exit__(self, exc_type, exc_value, traceback):
            return False

    monkeypatch.setattr(Image, "open", lambda image_bytes: OpenedImage())

    image = cli._load_embedded_png_icon(Path("embedded_icon.svg"))

    assert image.size == (64, 64)
    assert image.mode == "RGBA"


def test_tray_icon_uses_fallback_when_svg_cannot_be_loaded(monkeypatch):
    pytest.importorskip("PIL")
    monkeypatch.setattr(
        cli,
        "_load_embedded_png_icon",
        lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("invalid icon")),
    )

    image = cli._load_tray_icon(size=32)

    assert image.size == (32, 32)
    assert image.mode == "RGBA"


def test_tray_badge_icon_is_rgba():
    pytest.importorskip("PIL")

    image = cli._create_tray_badge_icon(size=16)

    assert image.size == (16, 16)
    assert image.mode == "RGBA"


def test_pythonw_executable_returns_adjacent_binary(monkeypatch, tmp_path):
    python = tmp_path / "python.exe"
    pythonw = tmp_path / "pythonw.exe"
    pythonw.touch()
    monkeypatch.setattr(sys, "executable", str(python))

    assert cli._pythonw_executable() == pythonw


def test_pythonw_executable_returns_none_when_already_windowless(monkeypatch):
    monkeypatch.setattr(sys, "executable", "C:/Python/pythonw.exe")

    assert cli._pythonw_executable() is None


def test_silent_requires_tray_mode():
    result = CliRunner().invoke(cli.main, ["serve", "--silent"])

    assert result.exit_code == 2
    assert "--silent requires --tray" in result.output


def test_reload_is_incompatible_with_tray_mode():
    result = CliRunner().invoke(cli.main, ["serve", "--tray", "--reload"])

    assert result.exit_code == 2
    assert "--reload is incompatible with --tray" in result.output
