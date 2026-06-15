import pytest
from pytestqt.qtbot import QtBot

from chemunited.connectivity import online_list
from chemunited.connectivity.online_list import OnlineComponent


@pytest.fixture(autouse=True)
def reset_flowchem_servers():
    original_servers = dict(online_list.FLOWCHEM_SERVERS.servers)
    original_correspondent = dict(online_list.FLOWCHEM_SERVERS.correspondent)
    online_list.FLOWCHEM_SERVERS.servers = {}
    online_list.FLOWCHEM_SERVERS.correspondent = {}
    yield
    online_list.FLOWCHEM_SERVERS.servers = original_servers
    online_list.FLOWCHEM_SERVERS.correspondent = original_correspondent


def _make_widget(qtbot: QtBot) -> OnlineComponent:
    widget = OnlineComponent(parent=None)
    qtbot.addWidget(widget)
    return widget


def _openapi_payload() -> dict:
    return {
        "paths": {
            "/startup_config": {},
            "/Pump/device/get-status": {},
            "/Pump/device/set-flow-rate": {},
        }
    }


def test_manual_typing_disables_update_button(qtbot: QtBot) -> None:
    widget = _make_widget(qtbot)

    assert widget.update_button.isEnabled()

    widget.api.setFocus()
    qtbot.keyClicks(widget.api, "192.168.1.2:8000")

    assert not widget.update_button.isEnabled()


def test_manual_enter_normalizes_registers_and_populates(
    qtbot: QtBot, monkeypatch
) -> None:
    widget = _make_widget(qtbot)
    calls: list[tuple[str, int]] = []

    def fake_access_url(url: str, timeout=5):
        calls.append((url, timeout))
        if url == "http://192.168.1.2:8000/openapi.json":
            return True, _openapi_payload()
        if url == "http://192.168.1.2:8000/Pump/device":
            return True, {"corresponding_class": ["Pump"]}
        return False, None

    monkeypatch.setattr(online_list, "access_url", fake_access_url)

    widget.api.setText("192.168.1.2:8000")
    widget.api.textEdited.emit(widget.api.text())
    widget.api.returnPressed.emit()

    assert widget.update_button.isEnabled()
    assert widget.api.currentText() == "http://192.168.1.2:8000"
    assert widget.api.findText("192.168.1.2:8000") == -1
    assert "http://192.168.1.2:8000" in online_list.FLOWCHEM_SERVERS.servers
    assert widget.OnlineList.count() == 1
    assert widget.OnlineList.item(0).text() == "Pump/device"
    assert ("http://192.168.1.2:8000/openapi.json", 1) in calls


def test_manual_enter_unreachable_clears_list_reenables_and_logs_warning(
    qtbot: QtBot, monkeypatch
) -> None:
    widget = _make_widget(qtbot)
    widget.OnlineList.addItem("stale/device")
    warnings: list[tuple] = []

    monkeypatch.setattr(
        online_list, "access_url", lambda *args, **kwargs: (False, None)
    )
    monkeypatch.setattr(
        online_list.logger, "warning", lambda *args: warnings.append(args)
    )

    widget.api.setText("192.168.1.2:8000")
    widget.api.textEdited.emit(widget.api.text())
    widget.api.returnPressed.emit()

    assert widget.update_button.isEnabled()
    assert widget.OnlineList.count() == 0
    assert widget.api.findText("192.168.1.2:8000") == -1
    assert warnings
    assert "not reachable" in warnings[0][0]


def test_selecting_discovered_server_populates_list(qtbot: QtBot, monkeypatch) -> None:
    widget = _make_widget(qtbot)
    online_list.FLOWCHEM_SERVERS.servers = {
        "http://10.0.0.1:8000": {"Reactor": ["heater"]}
    }

    def fake_access_url(url: str, timeout=5):
        if url == "http://10.0.0.1:8000/Reactor/heater":
            return True, {"corresponding_class": ["Heater"]}
        return False, None

    monkeypatch.setattr(online_list, "access_url", fake_access_url)

    widget.api.addItem("http://10.0.0.1:8000")

    assert widget.OnlineList.count() == 1
    assert widget.OnlineList.item(0).text() == "Reactor/heater"
