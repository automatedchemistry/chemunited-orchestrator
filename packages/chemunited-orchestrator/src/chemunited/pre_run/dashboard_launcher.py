from __future__ import annotations

import importlib.util
import json
import os
import secrets
import socket
import subprocess
import sys
import webbrowser
from pathlib import Path
from typing import TYPE_CHECKING
from urllib import error as urllib_error
from urllib import request as urllib_request

from loguru import logger
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    CardWidget,
    FluentIcon,
    InfoBar,
    InfoBarPosition,
    LineEdit,
    PasswordLineEdit,
    PrimaryPushButton,
    PushButton,
    ScrollArea,
    SpinBox,
    StrongBodyLabel,
    SwitchButton,
    TransparentPushButton,
)

if TYPE_CHECKING:
    from chemunited.pre_run.pre_run_frame import PreRunFrame

_IS_WINDOWS = sys.platform == "win32"
DEFAULT_PORT = 3116
DEFAULT_HOST = "127.0.0.1"


def inpect_execution_address(
    host: str = DEFAULT_HOST, port: int = DEFAULT_PORT
) -> bool:
    """Return True if the port is already in use."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


# ---------------------------------------------------------------------------
# Private helper widgets
# ---------------------------------------------------------------------------


class _SectionSeparator(QFrame):
    """1-px horizontal divider."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.HLine)
        self.setFrameShadow(QFrame.Sunken)
        self.setFixedHeight(1)
        self.setStyleSheet("QFrame { border: none; background: rgba(0, 0, 0, 0.08); }")


class _OptionRow(QWidget):
    """Left: title + description stacked vertically.  Right: control widget."""

    def __init__(
        self,
        title: str,
        description: str,
        widget: QWidget,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(16)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(2)
        left_layout.addWidget(StrongBodyLabel(title))
        desc = BodyLabel(description)
        desc.setWordWrap(True)
        left_layout.addWidget(desc)

        layout.addWidget(left, 1)
        layout.addWidget(widget, 0)


class _StatusBadge(QWidget):
    """Coloured dot + status text."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._dot = QFrame()
        self._dot.setFixedSize(10, 10)
        self._dot.setStyleSheet("border-radius: 5px; background: #888;")

        self._label = BodyLabel("Not Running")

        layout.addWidget(self._dot)
        layout.addWidget(self._label)

    def set_running(self, running: bool) -> None:
        if running:
            self._dot.setStyleSheet("border-radius: 5px; background: #0f7b0f;")
            self._label.setText("Running")
        else:
            self._dot.setStyleSheet("border-radius: 5px; background: #888;")
            self._label.setText("Not Running")


# ---------------------------------------------------------------------------
# Main frame
# ---------------------------------------------------------------------------


class DashBoardLauncherFrame(QFrame):

    def __init__(self, parent: "PreRunFrame") -> None:
        super().__init__(parent)
        self._pre_run_ref = parent
        self._is_running = False
        self._launched_token: str | None = None
        self._init_ui()
        self._connect_signals()
        self._update_address_display()

    # ------------------------------------------------------------------ build

    def _init_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = ScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)  # type: ignore[attr-defined]
        scroll.enableTransparentBackground()

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        layout.setAlignment(Qt.AlignTop)  # type: ignore[attr-defined]

        layout.addWidget(self._build_status_card())
        layout.addWidget(self._build_options_card())
        layout.addLayout(self._build_command_preview())

        self._launch_btn = PrimaryPushButton("Launch Dashboard")
        self._launch_btn.setFixedHeight(40)
        layout.addWidget(self._launch_btn)

        self._refresh_btn = TransparentPushButton(FluentIcon.SYNC, "Refresh Status")
        layout.addWidget(self._refresh_btn, 0, Qt.AlignHCenter)  # type: ignore[attr-defined]

        layout.addWidget(self._build_mcp_card())
        layout.addStretch(1)

        scroll.setWidget(content)
        outer.addWidget(scroll)

    # -- Status card -----------------------------------------------------------

    def _build_status_card(self) -> CardWidget:
        card = CardWidget()
        vlay = QVBoxLayout(card)
        vlay.setContentsMargins(16, 16, 16, 16)
        vlay.setSpacing(10)

        title_row = QWidget()
        tr_lay = QHBoxLayout(title_row)
        tr_lay.setContentsMargins(0, 0, 0, 0)
        tr_lay.addWidget(StrongBodyLabel("Dashboard Status"))
        tr_lay.addStretch(1)
        self._status_badge = _StatusBadge()
        tr_lay.addWidget(self._status_badge)
        vlay.addWidget(title_row)

        vlay.addWidget(_SectionSeparator())

        self._local_addr_label = self._addr_label(
            f"http://{DEFAULT_HOST}:{DEFAULT_PORT}/"
        )
        vlay.addWidget(self._labeled_row("Local:", self._local_addr_label))

        self._network_addr_label = self._addr_label("")
        self._network_addr_row = self._labeled_row("Network:", self._network_addr_label)
        self._network_addr_row.setVisible(False)
        vlay.addWidget(self._network_addr_row)

        self._mcp_addr_label = self._addr_label("")
        self._mcp_addr_row = self._labeled_row("MCP:", self._mcp_addr_label)
        self._mcp_addr_row.setVisible(False)
        vlay.addWidget(self._mcp_addr_row)

        self._status_token_label = self._addr_label("")
        self._status_token_copy_btn = PushButton("Copy")
        self._status_token_copy_btn.setFixedWidth(70)
        self._status_token_copy_btn.clicked.connect(self._copy_running_token)  # type: ignore[attr-defined]
        self._status_token_row = self._labeled_row(
            "API Token:", self._status_token_label, self._status_token_copy_btn
        )
        self._status_token_row.setVisible(False)
        vlay.addWidget(self._status_token_row)

        vlay.addWidget(_SectionSeparator())

        btn_row = QWidget()
        btn_lay = QHBoxLayout(btn_row)
        btn_lay.setContentsMargins(0, 0, 0, 0)
        btn_lay.setSpacing(8)

        self._link_btn = PushButton("Open Dashboard")
        self._link_btn.setEnabled(False)
        btn_lay.addWidget(self._link_btn)

        self._set_project_btn = PushButton("Send Project to Dashboard")
        self._set_project_btn.setVisible(False)
        btn_lay.addWidget(self._set_project_btn)

        btn_lay.addStretch(1)
        vlay.addWidget(btn_row)

        return card

    @staticmethod
    def _addr_label(text: str) -> BodyLabel:
        lbl = BodyLabel(text)
        lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)  # type: ignore[attr-defined]
        return lbl

    @staticmethod
    def _labeled_row(caption: str, value_widget: QWidget, *extra: QWidget) -> QWidget:
        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 2, 0, 2)
        lay.setSpacing(8)
        lay.addWidget(CaptionLabel(caption))
        lay.addWidget(value_widget)
        for widget in extra:
            lay.addWidget(widget)
        lay.addStretch(1)
        return row

    # -- Options card ----------------------------------------------------------

    def _build_options_card(self) -> CardWidget:
        card = CardWidget()
        vlay = QVBoxLayout(card)
        vlay.setContentsMargins(0, 16, 0, 16)
        vlay.setSpacing(0)

        hdr = StrongBodyLabel("Launch Options")
        hdr.setContentsMargins(16, 0, 16, 8)
        vlay.addWidget(hdr)
        vlay.addWidget(_SectionSeparator())

        self._port_spin = SpinBox()
        self._port_spin.setRange(1024, 65535)
        self._port_spin.setValue(DEFAULT_PORT)
        self._port_spin.setFixedWidth(150)
        vlay.addWidget(_OptionRow("Port", "Dashboard listening port", self._port_spin))
        vlay.addWidget(_SectionSeparator())

        self._host_edit = LineEdit()
        self._host_edit.setText(DEFAULT_HOST)
        self._host_edit.setFixedWidth(180)
        self._host_edit.setEnabled(False)
        vlay.addWidget(
            _OptionRow(
                "Host",
                "Managed automatically (0.0.0.0 when LAN advertisement is on)",
                self._host_edit,
            )
        )
        vlay.addWidget(_SectionSeparator())

        self._tray_switch = SwitchButton()
        self._tray_switch.setChecked(True)
        vlay.addWidget(
            _OptionRow(
                "System Tray",
                "Run as a tray icon — the dashboard keeps running after the window and terminal are closed",
                self._tray_switch,
            )
        )
        vlay.addWidget(_SectionSeparator())

        self._silent_switch = SwitchButton()
        self._silent_switch.setChecked(True)
        self._silent_row = _OptionRow(
            "Silent Mode",
            "Detach from the terminal on launch — no console window (Windows only)",
            self._silent_switch,
        )
        self._silent_sep = _SectionSeparator()
        self._silent_row.setVisible(_IS_WINDOWS)
        self._silent_sep.setVisible(_IS_WINDOWS)
        vlay.addWidget(self._silent_row)
        vlay.addWidget(self._silent_sep)

        self._advertise_switch = SwitchButton()
        self._advertise_switch.setChecked(False)
        vlay.addWidget(
            _OptionRow(
                "LAN Advertisement",
                "Broadcast the dashboard on the local network via mDNS — other devices can reach it by name",
                self._advertise_switch,
            )
        )
        vlay.addWidget(_SectionSeparator())

        self._advertise_name_edit = LineEdit()
        self._advertise_name_edit.setFixedWidth(240)
        self._advertise_name_edit.setPlaceholderText("ChemUnited @ <hostname>")
        self._advertise_name_row = _OptionRow(
            "Network Name",
            "Custom name shown in mDNS discovery",
            self._advertise_name_edit,
        )
        self._advertise_name_sep = _SectionSeparator()
        self._advertise_name_row.setVisible(False)
        self._advertise_name_sep.setVisible(False)
        vlay.addWidget(self._advertise_name_row)
        vlay.addWidget(self._advertise_name_sep)

        self._token_edit = PasswordLineEdit()
        self._token_edit.setFixedWidth(220)
        self._token_edit.setPlaceholderText("Bearer token for remote clients")
        self._token_copy_btn = PushButton("Copy")
        self._token_copy_btn.setFixedWidth(70)
        token_row_widget = QWidget()
        token_row_layout = QHBoxLayout(token_row_widget)
        token_row_layout.setContentsMargins(0, 0, 0, 0)
        token_row_layout.setSpacing(6)
        token_row_layout.addWidget(self._token_edit)
        token_row_layout.addWidget(self._token_copy_btn)
        self._advertise_token_row = _OptionRow(
            "API Token",
            "Required for remote (non-loopback) clients to start/cancel runs, load "
            "projects, or send device commands. Auto-generated; edit or paste your "
            "own. Passed via environment variable — never shown in the command "
            "preview below.",
            token_row_widget,
        )
        self._advertise_token_sep = _SectionSeparator()
        self._advertise_token_row.setVisible(False)
        self._advertise_token_sep.setVisible(False)
        vlay.addWidget(self._advertise_token_row)
        vlay.addWidget(self._advertise_token_sep)

        self._mcp_switch = SwitchButton()
        self._mcp_switch.setChecked(False)
        vlay.addWidget(
            _OptionRow(
                "Expose MCP Endpoint",
                "Also serve a Model Context Protocol (MCP) endpoint at /mcp for LLM agent access",
                self._mcp_switch,
            )
        )

        self._options_card = card
        return card

    # -- Command preview -------------------------------------------------------

    def _build_command_preview(self) -> QVBoxLayout:
        vlay = QVBoxLayout()
        vlay.setSpacing(4)

        hdr_row = QWidget()
        hdr_lay = QHBoxLayout(hdr_row)
        hdr_lay.setContentsMargins(0, 0, 0, 0)
        hdr_lay.addWidget(CaptionLabel("Generated command:"))
        hdr_lay.addStretch(1)
        vlay.addWidget(hdr_row)

        self._command_preview = LineEdit()
        self._command_preview.setReadOnly(True)
        self._command_preview.setFont(QFont("Consolas", 9))
        vlay.addWidget(self._command_preview)

        self._token_env_note = CaptionLabel("")
        self._token_env_note.setWordWrap(True)
        self._token_env_note.setVisible(False)
        vlay.addWidget(self._token_env_note)

        if not _IS_WINDOWS:
            note = CaptionLabel(
                "System Tray mode may have limited support on this platform. "
                "Copy the command above and run it directly in your terminal."
            )
            note.setWordWrap(True)
            vlay.addWidget(note)

        return vlay

    # -- MCP streamable-http card ----------------------------------------------

    def _build_mcp_card(self) -> CardWidget:
        self._mcp_card = CardWidget()
        vlay = QVBoxLayout(self._mcp_card)
        vlay.setContentsMargins(16, 16, 16, 16)
        vlay.setSpacing(10)

        vlay.addWidget(StrongBodyLabel("MCP Client Configuration"))

        desc = BodyLabel(
            "Add this block to your MCP client's settings file "
            "(e.g. claude_desktop_config.json). "
            "The dashboard exposes a streamable-HTTP MCP endpoint at /mcp."
        )
        desc.setWordWrap(True)
        vlay.addWidget(desc)

        vlay.addWidget(_SectionSeparator())

        initial_url = f"http://127.0.0.1:{DEFAULT_PORT}/mcp"
        initial_json = json.dumps(
            {
                "mcpServers": {
                    "chemunited-project": {
                        "type": "streamable-http",
                        "url": initial_url,
                    }
                }
            },
            indent=2,
        )

        self._mcp_json_browser = QTextBrowser()
        self._mcp_json_browser.setPlainText(initial_json)
        self._mcp_json_browser.setFont(QFont("Consolas", 9))
        self._mcp_json_browser.setFixedHeight(120)
        self._mcp_json_browser.setReadOnly(True)
        vlay.addWidget(self._mcp_json_browser)

        copy_btn = PushButton("Copy Config")
        copy_btn.clicked.connect(  # type: ignore[attr-defined]
            lambda: self._copy_mcp_config(self._mcp_json_browser.toPlainText())
        )
        vlay.addWidget(copy_btn, 0, Qt.AlignLeft)  # type: ignore[attr-defined]

        self._mcp_card.setVisible(False)
        return self._mcp_card

    # ------------------------------------------------------------------ signals

    def _connect_signals(self) -> None:
        self._tray_switch.checkedChanged.connect(self._on_tray_changed)  # type: ignore[attr-defined]
        self._advertise_switch.checkedChanged.connect(self._on_advertise_changed)  # type: ignore[attr-defined]
        self._mcp_switch.checkedChanged.connect(self._update_address_display)  # type: ignore[attr-defined]
        self._port_spin.valueChanged.connect(self._update_address_display)  # type: ignore[attr-defined]
        self._advertise_name_edit.textChanged.connect(self._update_address_display)  # type: ignore[attr-defined]
        self._token_edit.textChanged.connect(self._update_address_display)  # type: ignore[attr-defined]
        self._token_copy_btn.clicked.connect(self._copy_token)  # type: ignore[attr-defined]
        self._link_btn.clicked.connect(self._open_browser)  # type: ignore[attr-defined]
        self._set_project_btn.clicked.connect(self._send_project_to_dashboard)  # type: ignore[attr-defined]
        self._launch_btn.clicked.connect(self._launch_dashboard)  # type: ignore[attr-defined]
        self._refresh_btn.clicked.connect(self.refresh_status)  # type: ignore[attr-defined]

    def _on_tray_changed(self, checked: bool) -> None:
        self._silent_switch.setEnabled(checked)
        if not checked:
            self._silent_switch.setChecked(False)
        self._update_address_display()

    def _on_advertise_changed(self, checked: bool) -> None:
        self._advertise_name_row.setVisible(checked)
        self._advertise_name_sep.setVisible(checked)
        self._advertise_token_row.setVisible(checked)
        self._advertise_token_sep.setVisible(checked)
        if checked and not self._token_edit.text().strip():
            self._token_edit.setText(secrets.token_urlsafe(32))
        self._update_address_display()

    # ------------------------------------------------------------------ display

    def _mcp_url(self) -> str:
        port = self._port_spin.value()
        if self._advertise_switch.isChecked():
            name = self._advertise_name_edit.text().strip()
            mdns_host = name.replace(" ", "-") if name else socket.gethostname()
            return f"http://{mdns_host}.local:{port}/mcp/"
        return f"http://127.0.0.1:{port}/mcp/"

    def _update_address_display(self) -> None:
        port = self._port_spin.value()
        advertise_on = self._advertise_switch.isChecked()

        self._host_edit.setText(
            "0.0.0.0"
            if advertise_on
            else DEFAULT_HOST  # nosec B104 # user opt-in via "Advertise" switch, not a default
        )
        self._local_addr_label.setText(f"http://127.0.0.1:{port}/")

        if advertise_on:
            name = self._advertise_name_edit.text().strip()
            mdns_host = name.replace(" ", "-") if name else socket.gethostname()
            self._network_addr_label.setText(f"http://{mdns_host}.local:{port}/")
            self._network_addr_row.setVisible(True)
        else:
            self._network_addr_row.setVisible(False)

        mcp_on = self._mcp_switch.isChecked()
        self._mcp_addr_row.setVisible(mcp_on)
        self._mcp_card.setVisible(mcp_on)
        if mcp_on:
            url = self._mcp_url()
            self._mcp_addr_label.setText(url)
            self._mcp_json_browser.setPlainText(
                json.dumps(
                    {
                        "mcpServers": {
                            "chemunited-project": {
                                "type": "streamable-http",
                                "url": url,
                            }
                        }
                    },
                    indent=2,
                )
            )

        self._update_command_preview()

    def _update_command_preview(self) -> None:
        args = self._build_args()
        options = args[
            4:
        ]  # skip [sys.executable, "-m", "chemunited_workflow.cli", "serve"]
        exe_name = "chemunited-workflow.exe" if _IS_WINDOWS else "chemunited-workflow"
        cmd = exe_name + " serve"
        if options:
            cmd += " " + " ".join(options)
        self._command_preview.setText(cmd)

        advertise_on = self._advertise_switch.isChecked()
        token_set = bool(self._token_edit.text().strip())
        if advertise_on and token_set:
            self._token_env_note.setText(
                "The API token is passed via the CHEMUNITED_API_TOKEN environment "
                "variable — it is not included in the command above."
            )
            self._token_env_note.setVisible(True)
        elif advertise_on and not token_set:
            self._token_env_note.setText(
                "Warning: LAN Advertisement is on with no API token set — remote "
                "clients will be unable to start/cancel runs, load projects, or "
                "send device commands on this instance."
            )
            self._token_env_note.setVisible(True)
        else:
            self._token_env_note.setVisible(False)

    # ------------------------------------------------------------------ status

    def refresh_status(self) -> None:
        port = self._port_spin.value()
        self._is_running = inpect_execution_address(DEFAULT_HOST, port)
        if not self._is_running:
            self._launched_token = None
        self._apply_running_state()

    def _apply_running_state(self) -> None:
        running = self._is_running
        self._status_badge.set_running(running)
        self._link_btn.setEnabled(running)
        self._set_project_btn.setVisible(running)
        self._options_card.setEnabled(not running)
        self._launch_btn.setVisible(not running)

        show_token = running and bool(self._launched_token)
        self._status_token_row.setVisible(show_token)
        if show_token:
            self._status_token_label.setText(self._launched_token)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.refresh_status()

    # ------------------------------------------------------------------ actions

    def _open_browser(self) -> None:
        port = self._port_spin.value()
        webbrowser.open(f"http://127.0.0.1:{port}/")

    def _send_project_to_dashboard(self) -> None:
        try:
            project_dir: Path | None = (
                self._pre_run_ref.parent_ref.orchestrator.working_dir
            )
        except AttributeError:
            project_dir = None

        if project_dir is None:
            InfoBar.warning(
                "No Project Loaded",
                "Open a project in the orchestrator first.",
                orient=Qt.Horizontal,  # type: ignore[attr-defined]
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=4000,
                parent=self,
            )
            return

        port = self._port_spin.value()
        data = json.dumps({"project_dir": str(project_dir)}).encode()
        req = urllib_request.Request(
            f"http://127.0.0.1:{port}/project/",
            data=data,
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        try:
            with urllib_request.urlopen(
                req, timeout=5
            ):  # nosec B310 # fixed http://127.0.0.1 scheme/host, not user-controlled
                InfoBar.success(
                    "Project Loaded",
                    "Dashboard is now serving this project.",
                    orient=Qt.Horizontal,  # type: ignore[attr-defined]
                    isClosable=True,
                    position=InfoBarPosition.TOP,
                    duration=4000,
                    parent=self,
                )
        except urllib_error.HTTPError as exc:
            if exc.code == 409:
                logger.warning(
                    "Dashboard blocked — An execution run is currently active. "
                    "Switch the project after the run finishes."
                )
            else:
                InfoBar.error(
                    "Set Project Failed",
                    f"HTTP {exc.code}: {exc.reason}",
                    orient=Qt.Horizontal,  # type: ignore[attr-defined]
                    isClosable=True,
                    position=InfoBarPosition.BOTTOM_RIGHT,
                    duration=6000,
                    parent=self,
                )
        except Exception as exc:
            InfoBar.error(
                "Set Project Failed",
                str(exc),
                orient=Qt.Horizontal,  # type: ignore[attr-defined]
                isClosable=True,
                position=InfoBarPosition.BOTTOM_RIGHT,
                duration=6000,
                parent=self,
            )

    def _build_args(self) -> list[str]:
        args = [sys.executable, "-m", "chemunited_workflow.cli", "serve"]
        if self._tray_switch.isChecked():
            args.append("--tray")
        if (
            _IS_WINDOWS
            and self._silent_switch.isChecked()
            and self._tray_switch.isChecked()
        ):
            args.append("--silent")
        if self._advertise_switch.isChecked():
            args.append("--advertise")
            name = self._advertise_name_edit.text().strip()
            if name:
                args += ["--advertise-name", name]
        if self._mcp_switch.isChecked():
            args.append("--with-mcp")
        port = self._port_spin.value()
        if port != DEFAULT_PORT:
            args += ["--port", str(port)]
        return args

    def _launch_dashboard(self) -> None:
        self.refresh_status()
        if self._is_running:
            InfoBar.warning(
                "Already Running",
                "The dashboard is already accessible at the configured address.",
                orient=Qt.Horizontal,  # type: ignore[attr-defined]
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=4000,
                parent=self,
            )
            return

        if importlib.util.find_spec("chemunited_workflow") is None:
            logger.error(
                "Dashboard unavailable — chemunited_workflow is not installed in this environment."
            )
            return

        args = self._build_args()

        if (
            self._tray_switch.isChecked()
            and importlib.util.find_spec("pystray") is None
        ):
            logger.warning(
                "System Tray requires pystray — launching without tray support. "
                "Install it with: pip install chemunited-workflow[tray]"
            )
            args = [a for a in args if a not in ("--tray", "--silent")]

        token: str | None = None
        if self._advertise_switch.isChecked():
            candidate = self._token_edit.text().strip()
            if candidate:
                token = candidate

        env = None
        if token is not None:
            env = os.environ.copy()
            env["CHEMUNITED_API_TOKEN"] = token

        try:
            subprocess.Popen(  # nosec B603 # shell=False; args built from sys.executable + fixed subcommand list
                args,
                close_fds=True,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=env,
            )
            self._launched_token = token
            InfoBar.success(
                "Dashboard Launched",
                "Server is starting — click Refresh in a few seconds to verify.",
                orient=Qt.Horizontal,  # type: ignore[attr-defined]
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=5000,
                parent=self,
            )
        except FileNotFoundError:
            logger.error(
                "Launch Failed — Python executable not found. Check your virtual environment."
            )
        except PermissionError:
            logger.error(
                "Launch Failed — Permission denied when starting the server process."
            )
        except OSError as exc:
            logger.error(f"Launch Failed — {exc}")
        except Exception as exc:
            logger.error(f"Launch Failed — {exc}")

    def _copy_to_clipboard(self, text: str, *, subject: str) -> None:
        if not text:
            return
        QApplication.clipboard().setText(text)  # type: ignore[union-attr]
        InfoBar.success(
            "Copied",
            f"{subject} copied to clipboard.",
            orient=Qt.Horizontal,  # type: ignore[attr-defined]
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=2500,
            parent=self,
        )

    def _copy_mcp_config(self, json_text: str) -> None:
        self._copy_to_clipboard(json_text, subject="MCP configuration")

    def _copy_token(self) -> None:
        self._copy_to_clipboard(self._token_edit.text().strip(), subject="API token")

    def _copy_running_token(self) -> None:
        self._copy_to_clipboard(self._launched_token or "", subject="API token")
