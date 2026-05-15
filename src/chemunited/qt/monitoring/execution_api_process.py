import json
import sys
import requests

from pathlib import Path
from typing import Any
from pydantic import (
    BaseModel,
    Field,
    AnyHttpUrl,
    field_validator,
    ValidationInfo,
)

from PyQt5.QtCore import QObject, QProcess, QTimer, QUrl, pyqtSignal
from PyQt5.QtNetwork import QNetworkAccessManager, QNetworkRequest

from qfluentwidgets import TextBrowser

from chemunited.qt.shared.widgets.base_mode_editor.dialog import BaseModeDialog
from chemunited.qt.utils.flowchem_listener import access_url
from chemunited.workflow.api import PORT

BASE_URL = f"http://localhost:{PORT}"


class ApiClient:
    """Basic client for the execution API."""
    def __init__(self, url: AnyHttpUrl):
        self.url = url
        self.session = requests.Session()
    
    def get(self, endpoint: str, params: dict | None = None, timeout: int = 10) -> Any:
        return self.session.get(f"{self.url}/{endpoint}", params=params, timeout=timeout).json()

    def put(self, endpoint: str, params: dict | None = None, timeout: int = 10) -> Any:
        return self.session.put(f"{self.url}/{endpoint}", params=params, timeout=timeout).json()

    def post(self, endpoint: str, data: dict | None = None, timeout: int = 10) -> Any:
        return self.session.post(f"{self.url}/{endpoint}", json=data, timeout=timeout).json()
        

class APIAddress(BaseModel):
    already_running: bool = Field(
        default=False,
        description="Don't start API, just connect to the existing one",
    )
    address: AnyHttpUrl = Field(
        default=AnyHttpUrl(BASE_URL),
        description="API Address",
        json_schema_extra={"editable": False},
    )

    @field_validator("address", mode="after")
    @classmethod
    def validate_address(cls, v: AnyHttpUrl, info: ValidationInfo) -> AnyHttpUrl:
        if info.data.get("already_running") and not access_url(str(v), timeout=2)[0]:
            raise ValueError(f"Cannot reach {v}")
        return v


class APIDialog(BaseModeDialog):
    def __init__(self, parent=None):
        super().__init__(
            model_class=APIAddress,
            instance=APIAddress(),
            parent=parent,
            title="API Address",
        )
        already_running_card = self.editor_widget._cards["already_running"]
        already_running_card.value_changed.connect(self._on_already_running_changed)  # type: ignore[attr-defined]

    def _on_already_running_changed(self, checked: bool):
        self.editor_widget._cards["address"].setEnabled(checked)


class ApiProcess(QObject):
    api_alive = pyqtSignal(bool)

    def __init__(self, working_dir: Path, log_browser: TextBrowser, parent=None):
        super().__init__(parent)
        self._parent_widget = parent
        self._log_browser = log_browser
        self._process = QProcess(self)
        self._nam = QNetworkAccessManager(self)
        self.client = ApiClient(AnyHttpUrl(BASE_URL)) # default value

        self._ping_timer = QTimer(self)
        self._ping_timer.setInterval(5000)
        self._ping_timer.timeout.connect(self._ping)

        self._process.setWorkingDirectory(str(working_dir))
        self._process.readyReadStandardOutput.connect(self._on_stdout)
        self._process.readyReadStandardError.connect(self._on_stderr)
        self._process.started.connect(self._on_started)

    @property
    def url(self) -> str:       
        return str(self.client.url)

    def start_api(self) -> bool:
        dialog = APIDialog(parent=self._parent_widget)
        if dialog.exec() != dialog.Accepted:
            return False
        if result := dialog.get_result_instance():
            self.client.url = getattr(result, "address")
        else:
            return False
            
        if getattr(result, "already_running"):
            self._ping_timer.start()
            QTimer.singleShot(2000, self._fetch_log_address)
        else:
            self._process.start(sys.executable, ["api.py"])
        return True

    def stop_api(self):
        self._ping_timer.stop()
        if self._process.state() != QProcess.ProcessState.NotRunning:  # type: ignore[attr-defined]
            self._process.terminate()
            if not self._process.waitForFinished(3000):
                self._process.kill()

    def _on_stdout(self):
        data = self._process.readAllStandardOutput().data().decode(errors="replace")
        self._append(data)

    def _on_stderr(self):
        data = self._process.readAllStandardError().data().decode(errors="replace")
        self._append(data)

    def _append(self, text: str):
        self._log_browser.append(text.rstrip())

    def _on_started(self):
        QTimer.singleShot(2000, self._fetch_log_address)
        self._ping_timer.start()

    def _ping(self):
        req = QNetworkRequest(QUrl(f"{self.client.url}/ping"))
        reply = self._nam.get(req)
        if reply is not None:
            reply.finished.connect(lambda: self._on_ping_reply(reply))

    def _on_ping_reply(self, reply):
        alive = reply.error() == reply.NetworkError.NoError  # type: ignore[attr-defined]
        self.api_alive.emit(alive)

    def _fetch_log_address(self):
        req = QNetworkRequest(QUrl(f"{self.client.url}/log_address"))
        reply = self._nam.get(req)
        if reply is not None:
            reply.finished.connect(lambda: self._on_log_address_reply(reply))

    def _on_log_address_reply(self, reply):
        raw = reply.readAll().data().decode(errors="replace")
        try:
            path = Path(json.loads(raw))
            self._read_log_file(path)
        except Exception as e:
            self._append(f"[log_address error] {e}: {raw}")

    def _read_log_file(self, path: Path):
        if path.exists():
            self._append(f"\n--- Log file: {path} ---\n")
            self._append(path.read_text(errors="replace"))
        else:
            self._append(f"[log file not found] {path}")

