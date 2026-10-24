"""Device pictures for the live platform view, from chemunited-core.

The only work-server module that uses chemunited-core, and only inside the
functions below — never at import time — so a plain ``pip install
chemunited-workflow`` stays a protocol executor. With the ``live`` extra,
``load_command_tracker`` rebuilds each pictured device's ``ComponentData``
from ``draw/setup.py`` (the drawing as last saved in the desktop app) and the
tracker follows it through the commands the device clients report.
"""

from __future__ import annotations

import importlib.util
import threading
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from loguru import logger

from .device_state import UnknownPicture

INSTALL_HINT = "pip install chemunited-workflow[live]"


class CommandTracker:
    """The picture deriver of the device state store (see ``PictureDeriver``)."""

    def __init__(self, pictures: Mapping[str, Any]) -> None:
        # name -> chemunited_core.components.live_state.LivePicture
        self._pictures = dict(pictures)
        self._lock = threading.Lock()

    def kind(self, component: str) -> str | None:
        picture = self._pictures.get(component)
        return None if picture is None else picture.kind

    def derive(
        self, component: str, command: str, params: Mapping[str, Any] | None
    ) -> dict[str, Any]:
        from chemunited_core.components.live_state import UnrecognisedCommand

        picture = self._pictures.get(component)
        if picture is None:
            raise UnknownPicture(f"{component} has no picture.")
        with self._lock:
            try:
                return picture.apply(command, params)
            except UnrecognisedCommand as exc:
                raise UnknownPicture(str(exc)) from exc


class _DrawRecorder:
    """Stands in for the platform builder ``build_draw(platform)`` is given.

    Keeps the components whose figure has a picture, built the way the
    simulator's ``PlatformBuilder.add_component`` builds them; every other
    call (connections, compounds, displays, …) does nothing.
    """

    def __init__(self) -> None:
        from chemunited_core.components.live_state import picture_kind_of
        from chemunited_core.figure_registry import COMPONENTS

        self._registry = COMPONENTS
        self._picture_kind_of = picture_kind_of
        self.components: dict[str, Any] = {}
        self.errors: list[str] = []

    def add_component(
        self,
        name: str,
        figure: str,
        position: tuple[float, float] = (0.0, 0.0),
        angle: int = 0,
        **kwargs: Any,
    ) -> Any:
        defn = self._registry.get(figure)
        if defn is None or self._picture_kind_of(defn.data_class) is None:
            return None
        try:
            mode = defn.mode_class(name=name, position=position, angle=angle, **kwargs)
            data = defn.data_class.from_mode(mode)
        except Exception as exc:
            self.errors.append(f"'{name}' ({figure}): {exc}")
            return None
        self.components[name] = data
        return data

    def __getitem__(self, name: str) -> Any:
        return self.components.get(name)

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        return _ignore


def _ignore(*args: Any, **kwargs: Any) -> None:
    return None


def _run_build_draw(setup_path: Path, platform: _DrawRecorder) -> None:
    spec = importlib.util.spec_from_file_location("_chemunited_live_draw", setup_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {setup_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.build_draw(platform)


def load_command_tracker(project_dir: Path) -> CommandTracker | None:
    """The tracker for *project_dir*, or None when the live view has no pictures.

    Never raises: a missing chemunited-core or a broken ``draw/setup.py``
    logs one line with the reason, and the live view still shows which device
    runs which command.
    """
    try:
        from chemunited_core.components.live_state import LivePicture
        from chemunited_core.figure_registry.project_loader import (
            load_project_components,
        )
    except ImportError as exc:
        logger.info(
            "Live platform view without device pictures: chemunited-core isn't "
            "installed ({}). Install it with `{}`.",
            exc,
            INSTALL_HINT,
        )
        return None

    setup_path = project_dir / "draw" / "setup.py"
    if not setup_path.is_file():
        logger.info(
            "Live platform view without device pictures: {} doesn't exist.",
            setup_path,
        )
        return None
    try:
        load_project_components(project_dir)
    except Exception as exc:
        logger.warning(
            "Live platform view: the project's custom components didn't load "
            "({}: {}), so their devices have no pictures.",
            type(exc).__name__,
            exc,
        )
    recorder = _DrawRecorder()
    try:
        _run_build_draw(setup_path, recorder)
    except Exception as exc:
        logger.warning(
            "Live platform view without device pictures: draw/setup.py failed "
            "({}: {}).",
            type(exc).__name__,
            exc,
        )
        return None
    for error in recorder.errors:
        logger.warning("Live platform view: no picture for {}", error)
    return CommandTracker(
        {name: LivePicture(data) for name, data in recorder.components.items()}
    )
