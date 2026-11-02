"""Application-wide theme plumbing for ChemUnited.

Built on qfluentwidgets' own mechanism:

- ``qconfig.themeMode`` holds the persisted mode (``Theme.AUTO``, ``LIGHT``
  or ``DARK``); ``Theme.AUTO`` resolves to the Windows system theme via
  darkdetect.
- ``setTheme(theme, save=True)`` persists the mode and emits
  ``qconfig.themeChangedFinished`` once the library stylesheets are updated.
- The library never loads a config file by itself, and nothing in the app
  ever called ``setTheme`` — so this module owns that wiring.

Responsibilities:

- ``init_theme()``: load the persisted config (project-managed JSON), apply
  the saved mode (first run: ``AUTO``), and hook the global broadcast so
  that every later change re-applies across open windows.
- ``set_theme_mode()``: apply and persist a manual override.
- ``apply_theme_change()``: the broadcast — re-applies window-level QSS
  (``setQss`` on our window bases), schedules repaints for widgets that
  derive their colors from ``isDarkTheme()`` at paint time, and calls
  opt-in observers.
- ``register_theme_observer()``: opt-in hook for widgets that bake theme
  decisions into their *content* at construction time and therefore must
  rebuild it on a change (Monaco editor pages, the loggings HTML, ...).
  Observers are held weakly; widgets that are destroyed are pruned at the
  next broadcast, and nothing keeps them alive.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Callable
from weakref import WeakMethod

from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QApplication, QWidget
from qfluentwidgets import Theme, isDarkTheme, qconfig
from qfluentwidgets.common.style_sheet import setTheme

logger = logging.getLogger(__name__)

_CONFIG_FILE_NAME = "theme_config.json"

# Weakly-held bound methods that re-apply theme-dependent content.
_observers: list[WeakMethod] = []
# Plain callables (functions/lambdas): held strongly, caller manages lifetime.
_strong_observers: list[Callable[[], None]] = []

_broadcast_connected = False

# Window chrome colors, mirroring shared/resources/qss/main_window.qss.
_LIGHT_WINDOW_BG = "rgb(249, 249, 249)"
_DARK_WINDOW_BG = "rgb(39, 39, 39)"


def _config_path() -> Path:
    """Project-managed location for the persisted theme config."""
    base: str
    try:
        import platformdirs

        base = platformdirs.user_data_dir(
            appname="chemunited-orchestrator", appauthor=False
        )
    except Exception:
        from PyQt5.QtCore import QStandardPaths

        base = str(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation))
    return Path(base) / _CONFIG_FILE_NAME


def current_theme_mode() -> Theme:
    """The persisted theme mode (AUTO / LIGHT / DARK), not the resolved one."""
    mode = qconfig.get(qconfig.themeMode)
    return mode if isinstance(mode, Theme) else Theme.AUTO


def register_theme_observer(callback: Callable[[], None]) -> None:
    """Register a zero-argument callback invoked after every theme change.

    Bound methods are held weakly, so widgets are not kept alive by this
    module and destroyed objects are pruned at the next broadcast. Other
    callables are held strongly until unregister_theme_observer().
    """
    try:
        entry = WeakMethod(callback)
    except TypeError:
        if callback not in _strong_observers:
            _strong_observers.append(callback)
        return

    if entry not in _observers:
        _observers.append(entry)


def unregister_theme_observer(callback: Callable[[], None]) -> None:
    """Best-effort removal of a callback (idempotent)."""
    try:
        _strong_observers.remove(callback)
    except ValueError:
        pass
    for entry in list(_observers):
        bound = entry()
        if bound is not None and getattr(bound, "__func__", None) is getattr(
            callback, "__func__", None
        ):
            _observers.remove(entry)


def apply_theme_change() -> None:
    """Re-apply the current theme across the application.

    Emitted after ``themeChangedFinished``, i.e. after qfluentwidgets has
    already swapped its own stylesheets.
    """
    # Window-level QSS on our window bases (loads :/styles/qss/{color}/...).
    for window in QApplication.topLevelWidgets():
        apply_native_titlebar_theme(window)

        set_qss = getattr(window, "setQss", None)
        if callable(set_qss):
            try:
                set_qss()
            except Exception:
                logger.exception(
                    "theme re-apply failed for window %s", window.objectName()
                )

    # Widgets that derive colors at paint time from isDarkTheme().
    for widget in QApplication.allWidgets():
        widget.update()

    # Widgets that must rebuild theme-dependent content.
    for entry in list(_observers):
        callback = entry()
        if callback is None:
            try:
                _observers.remove(entry)
            except ValueError:
                pass
            continue
        try:
            callback()
        except Exception:
            logger.exception("theme observer failed after a theme change")
    for callback in list(_strong_observers):
        try:
            callback()
        except Exception:
            logger.exception("theme observer failed after a theme change")


def set_theme_mode(theme: Theme) -> None:
    """Apply and persist a manual theme (Theme.AUTO / LIGHT / DARK)."""
    setTheme(theme, save=True)
    apply_theme_change()


def init_theme() -> None:
    """Load the persisted theme config, apply it and start the broadcast.

    Call once, after the QApplication exists and before windows are built.
    """
    global _broadcast_connected

    config_path = _config_path()
    first_run = not config_path.exists()

    # load() binds config_path for later save=True writes, tolerates an
    # absent file (empty dict) and re-resolves the loaded mode onto
    # qconfig.theme itself.
    qconfig.load(str(config_path))

    saved = None if first_run else qconfig.get(qconfig.themeMode)

    # First run (or broken config): follow the system theme by default.
    # save=False: persistence only happens through explicit user overrides.
    setTheme(saved if isinstance(saved, Theme) else Theme.AUTO, save=False)

    if not _broadcast_connected:
        qconfig.themeChangedFinished.connect(apply_theme_change)
        _broadcast_connected = True


# ---------------------------------------------------------------------------
# Window chrome for windows outside WindowBase / qfluentwidgets' styling
# ---------------------------------------------------------------------------


def window_chrome_qss() -> str:
    """Chrome QSS mirroring ``:/styles/qss/{color}/main_window.qss``.

    Used by windows that do not run through ``WindowBase`` (plain QMainWindow
    windows and frameless dialogs) so that every window paints the same
    background in both themes.
    """
    bg = _DARK_WINDOW_BG if isDarkTheme() else _LIGHT_WINDOW_BG
    return f"""
        QWidget {{
            border-right: none;
            border-bottom: none;
            border-top: none;
            border-left: none;
            background-color: {bg};
        }}

        QGraphicsView {{
            border-right: none;
            border-bottom: none;
            border-top: none;
            border-left: none;
            background-color: {bg};
        }}
        """


def apply_native_titlebar_theme(widget: QWidget) -> None:
    """Windows-only: force the native title bar to match the application theme.

    Plain QMainWindow pages keep the OS-drawn title bar; without this call the
    bar follows the *system* theme instead of the in-app override. Frameless
    windows accept the call as a harmless no-op.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes

        hwnd = int(widget.winId())
        value = ctypes.c_int(1 if isDarkTheme() else 0)
        # DWMWA_USE_IMMERSIVE_DARK_MODE: attr 20 on Win10 2004+, 19 on older
        # builds. Try both and keep whichever succeeds.
        for attribute in (20, 19):
            if (
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, attribute, ctypes.byref(value), ctypes.sizeof(value)
                )
                == 0
            ):
                break
    except Exception:
        logger.debug("could not set native title bar theme", exc_info=True)


def apply_titlebar_theme(titlebar: QWidget) -> None:
    """Recolor a qframelesswindow StandardTitleBar for the current theme.

    The title label and min/max/close icons are otherwise black in both
    themes, which is invisible on the dark background.
    """
    dark = isDarkTheme()
    fg = QColor("#F3F4F6") if dark else QColor("#000000")
    hover_bg = QColor(255, 255, 255, 26) if dark else QColor(0, 0, 0, 26)
    pressed_bg = QColor(255, 255, 255, 51) if dark else QColor(0, 0, 0, 51)

    title_label = getattr(titlebar, "titleLabel", None)
    if title_label is not None:
        title_label.setStyleSheet(f"""
            QLabel{{
                background: transparent;
                color: {fg.name()};
                font: 13px 'Segoe UI', 'Microsoft YaHei', 'PingFang SC';
                padding: 0 4px
            }}
        """)

    for name in ("minBtn", "maxBtn", "closeBtn"):
        button = getattr(titlebar, name, None)
        if button is None:
            continue
        button.setNormalColor(fg)
        button.setHoverColor(fg)
        button.setPressedColor(fg)
        button.setNormalBackgroundColor(QColor(0, 0, 0, 0))
        button.setHoverBackgroundColor(hover_bg)
        button.setPressedBackgroundColor(pressed_bg)


class ThemedChromeMixin:
    """Themed chrome for windows that do not run through ``WindowBase``.

    Plain ``QMainWindow`` windows and ``qframelesswindow.FramelessDialog``
    dialogs do not inherit ``WindowBase.setQss``; mixing this in provides the
    same seam: the application-wide theme broadcast re-applies their chrome on
    every toggle, and ``showEvent`` applies the current theme for windows that
    open later or were closed and re-shown between broadcasts.

    Put it before the Qt base class::

        class MyWindow(ThemedChromeMixin, QMainWindow):
    """

    def setQss(self) -> None:
        from typing import cast

        from PyQt5.QtWidgets import QWidget

        widget = cast(QWidget, self)
        widget.setStyleSheet(window_chrome_qss())
        apply_native_titlebar_theme(widget)

    def showEvent(self, event):
        # Cheap re-apply: windows opened after a theme toggle (without a
        # broadcast having run) still come up themed.
        self.setQss()
        return super().showEvent(event)
