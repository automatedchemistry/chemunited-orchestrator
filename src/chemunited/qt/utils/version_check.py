from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from json import loads
from urllib.request import Request, urlopen

from packaging.version import Version
from PyQt5.QtCore import QThread, pyqtSignal

TRACKED = ["chemunited-core", "chemunited-workflow"]


@dataclass
class UpdateAvailable:
    package: str
    installed: str
    latest: str


class VersionCheckThread(QThread):
    updates_found: pyqtSignal = pyqtSignal(list)

    def run(self) -> None:
        updates = []
        for pkg in TRACKED:
            try:
                installed = Version(version(pkg))
            except PackageNotFoundError:
                continue
            try:
                req = Request(
                    f"https://pypi.org/pypi/{pkg}/json",
                    headers={"User-Agent": "chemunited-orchestrator"},
                )
                with urlopen(req, timeout=5) as resp:
                    latest = Version(loads(resp.read())["info"]["version"])
                if latest > installed:
                    updates.append(UpdateAvailable(pkg, str(installed), str(latest)))
            except Exception:
                pass
        if updates:
            self.updates_found.emit(updates)
