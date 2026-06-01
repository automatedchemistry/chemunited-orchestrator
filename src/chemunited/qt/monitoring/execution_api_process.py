import json
import sys
from pathlib import Path
from typing import Any

import requests
from chemunited_workflow.api.schemas import RunRequest
from loguru import logger
from pydantic import (
    AnyHttpUrl,
    BaseModel,
    Field,
    ValidationInfo,
    field_validator,
)
from PyQt5.QtCore import QObject, QProcess, QTimer, QUrl, pyqtSignal
from PyQt5.QtNetwork import QNetworkAccessManager, QNetworkRequest
from qfluentwidgets import TextBrowser

from chemunited.qt.shared.widgets.base_mode_editor.dialog import BaseModeDialog
from chemunited.qt.utils.flowchem_listener import access_url

DEFAULT_API_PORT = 3116
BASE_URL = f"http://localhost:{DEFAULT_API_PORT}"


class ApiClient:
    """Basic client for the execution API."""

    def __init__(self, url: AnyHttpUrl):
        self.url = url
        self.session = requests.Session()
        # Disable system proxy for loopback requests — on some machines a corporate
        # or OS-level proxy intercepts http://localhost traffic and returns 403.
        self.session.trust_env = False
        self.session.proxies.update({"http": "", "https": ""})

    def _request(
        self,
        method: str,
        endpoint: str,
        *,
        params: dict | None = None,
        data: dict | None = None,
        timeout: int = 10,
    ) -> Any:
        url = _api_url(self.url, endpoint)
        try:
            response = self.session.request(
                method,
                url,
                params=params,
                json=data,
                timeout=timeout,
            )
            if response.status_code == 204:
                return {"status": "ok"}
            response.raise_for_status()
            if not response.content:
                return {"status": "ok"}
            return response.json()
        except requests.HTTPError as exc:
            response = exc.response
            status_code = response.status_code if response is not None else None
            logger.warning("{} {} failed: {}", method.upper(), url, exc)
            return {"error": str(exc), "status_code": status_code}
        except requests.RequestException as exc:
            logger.warning("{} {} failed: {}", method.upper(), url, exc)
        except ValueError as exc:
            logger.warning("{} {} returned invalid JSON: {}", method.upper(), url, exc)
        return None

    def get(self, endpoint: str, params: dict | None = None, timeout: int = 10) -> Any:
        return self._request("GET", endpoint, params=params, timeout=timeout)

    def stream(self, endpoint: str, timeout: int | tuple[float, float | None] = 10):
        url = _api_url(self.url, endpoint)
        try:
            response = self.session.get(url, stream=True, timeout=timeout)
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            logger.warning("GET {} stream failed: {}", url, exc)
            raise

    def put(self, endpoint: str, params: dict | None = None, timeout: int = 10) -> Any:
        return self._request("PUT", endpoint, params=params, timeout=timeout)

    def post(self, endpoint: str, data: dict | None = None, timeout: int = 10) -> Any:
        return self._request("POST", endpoint, data=data, timeout=timeout)

    def delete(self, endpoint: str, timeout: int = 10) -> Any:
        return self._request("DELETE", endpoint, timeout=timeout)


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


class RunRequestDialog(BaseModeDialog):
    def __init__(self, snapshot: str, parent=None):
        super().__init__(
            model_class=RunRequest,
            instance=RunRequest(snapshot=snapshot),
            field_overrides={"snapshot": {"editable": False}},
            parent=parent,
            title="Run Configuration",
        )


class ApiProcess(QObject):
    api_alive = pyqtSignal(bool)

    def __init__(self, working_dir: Path, log_browser: TextBrowser, parent=None):
        super().__init__(parent)
        self._working_dir = working_dir
        self._parent_widget = parent
        self._log_browser = log_browser
        self._process = QProcess(self)
        self._nam = QNetworkAccessManager(self)
        self.client = ApiClient(AnyHttpUrl(BASE_URL))  # default value

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
            QTimer.singleShot(2000, self._fetch_logs)
        else:
            self._process.start(
                _workflow_cli_executable(),
                [str(self._working_dir), "--fastapi", "--port", str(DEFAULT_API_PORT)],
            )
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
        QTimer.singleShot(2000, self._fetch_logs)
        self._ping_timer.start()

    def _ping(self):
        req = QNetworkRequest(QUrl(_api_url(self.client.url, "processes")))
        reply = self._nam.get(req)
        if reply is not None:
            reply.finished.connect(lambda: self._on_ping_reply(reply))

    def _on_ping_reply(self, reply):
        alive = reply.error() == reply.NetworkError.NoError  # type: ignore[attr-defined]
        self.api_alive.emit(alive)

    def _fetch_logs(self):
        req = QNetworkRequest(QUrl(_api_url(self.client.url, "logs/")))
        reply = self._nam.get(req)
        if reply is not None:
            reply.finished.connect(lambda: self._on_logs_reply(reply))

    def _on_logs_reply(self, reply):
        raw = reply.readAll().data().decode(errors="replace")
        try:
            logs = json.loads(raw)
            if logs:
                self._append(f"Available API logs: {logs}")
        except Exception as e:
            self._append(f"[logs error] {e}: {raw}")


def _workflow_cli_executable() -> str:
    executable = Path(sys.executable)
    name = (
        "chemunited-workflow.exe"
        if sys.platform.startswith("win")
        else "chemunited-workflow"
    )
    candidate = executable.parent / name
    if candidate.exists():
        return str(candidate)
    return name


def _api_url(base_url: AnyHttpUrl, endpoint: str) -> str:
    return f"{str(base_url).rstrip('/')}/{endpoint.lstrip('/')}"
