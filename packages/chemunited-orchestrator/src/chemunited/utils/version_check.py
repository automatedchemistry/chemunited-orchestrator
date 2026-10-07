from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from json import loads
from urllib.request import Request, urlopen

from packaging.version import Version
from PyQt5.QtCore import QThread, pyqtSignal

TRACKED = [
    "chemunited-core",
    "chemunited-workflow",
    "chemunited-sim",
    "chemunited-quantities",
    "chemunited",
]


@dataclass
class UpdateAvailable:
    package: str
    installed: str
    latest: str


class VersionCheckThread(QThread):
    updates_found: pyqtSignal = pyqtSignal(list)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._stop_requested = False

    def stop(self) -> None:
        """Ask run() to skip any package it hasn't started checking yet.

        Doesn't interrupt a urlopen() already in flight (bounded by its own
        5s timeout) - callers that need the thread fully stopped still need
        to wait() after this.
        """
        self._stop_requested = True

    def run(self) -> None:
        updates = []
        for pkg in TRACKED:
            if self._stop_requested:
                return
            try:
                installed = Version(version(pkg))
            except PackageNotFoundError:
                continue
            try:
                req = Request(
                    f"https://pypi.org/pypi/{pkg}/json",
                    headers={"User-Agent": "chemunited-orchestrator"},
                )
                with urlopen(
                    req, timeout=5
                ) as resp:  # nosec B310 # fixed https://pypi.org scheme/host, not user-controlled
                    latest = Version(loads(resp.read())["info"]["version"])
                if latest > installed:
                    updates.append(UpdateAvailable(pkg, str(installed), str(latest)))
            except (
                Exception
            ):  # nosec B110 # best-effort update check; network/parse failures just skip the package
                pass
        if updates:
            self.updates_found.emit(updates)
