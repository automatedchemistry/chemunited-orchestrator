from __future__ import annotations

import asyncio
import json
from typing import Annotated

from pydantic import BaseModel

from chemunited_quantities import ChemQuantityValidator, ChemUnitQuantity
from chemunited_workflow.api.project_holder import ProjectHolder
from chemunited_workflow.mcp import create_mcp_server
from chemunited_workflow.project_loader import ProjectModules

FlowRate = Annotated[ChemUnitQuantity, ChemQuantityValidator("ml/min")]


def test_create_mcp_server_configures_http_transport_settings():
    server = create_mcp_server(
        host="0.0.0.0",
        port=3117,
        streamable_http_path="/custom-mcp",
    )

    assert server.settings.host == "0.0.0.0"
    assert server.settings.port == 3117
    assert server.settings.streamable_http_path == "/custom-mcp"


def _mcp_payload(result):
    content = result[0] if isinstance(result, tuple) else result
    return json.loads(content[0].text)


def test_process_schema_tools_return_serialized_typed_defaults(tmp_path):
    class Config(BaseModel):
        flow_rate: FlowRate = ChemUnitQuantity("0.1 ml/min")

    class MainParameter(BaseModel):
        main_flow_rate: FlowRate = ChemUnitQuantity("0.2 ml/min")

    class FakeProcess:
        pass

    holder = ProjectHolder()
    holder.load(
        ProjectModules(
            project_dir=tmp_path,
            processes={"fake": FakeProcess},
            configs={"fake": Config},
            main_parameter_class=MainParameter,
        )
    )
    server = create_mcp_server(holder=holder)

    listed = _mcp_payload(asyncio.run(server.call_tool("list_processes", {})))
    schema = _mcp_payload(
        asyncio.run(server.call_tool("get_process_schema", {"name": "fake"}))
    )

    assert listed["config_schema"]["properties"]["flow_rate"]["default"] == (
        "0.1 milliliter / minute"
    )
    assert schema["config_schema"]["properties"]["flow_rate"]["default"] == (
        "0.1 milliliter / minute"
    )
    assert (
        schema["main_parameter_schema"]["properties"]["main_flow_rate"]["default"]
        == "0.2 milliliter / minute"
    )


def _write_valid_protocols_package(project_dir):
    protocols_dir = project_dir / "protocols"
    protocols_dir.mkdir()
    (protocols_dir / "__init__.py").write_text(
        "PROCESSES = {}\nCONFIGS = {}\n", encoding="utf-8"
    )
    (protocols_dir / "main_parameters.py").write_text(
        "class MainParameter:\n    pass\n", encoding="utf-8"
    )


def test_load_project_tool_success(tmp_path):
    _write_valid_protocols_package(tmp_path)

    holder = ProjectHolder()
    server = create_mcp_server(holder=holder)

    result = _mcp_payload(
        asyncio.run(server.call_tool("load_project", {"project_dir": str(tmp_path)}))
    )

    assert result["project_dir"] == str(tmp_path.resolve())
    assert holder.is_loaded()


def test_load_project_tool_syntax_error(tmp_path):
    protocols_dir = tmp_path / "protocols"
    protocols_dir.mkdir()
    (protocols_dir / "__init__.py").write_text(
        "def broken(:\n    pass\n", encoding="utf-8"
    )
    (protocols_dir / "main_parameters.py").write_text(
        "class MainParameter:\n    pass\n", encoding="utf-8"
    )

    holder = ProjectHolder()
    server = create_mcp_server(holder=holder)

    result = _mcp_payload(
        asyncio.run(server.call_tool("load_project", {"project_dir": str(tmp_path)}))
    )

    assert "SyntaxError" in result["error"]
    assert not holder.is_loaded()


def test_load_project_tool_service_init_failure(tmp_path, mocker):
    _write_valid_protocols_package(tmp_path)
    mocker.patch(
        "chemunited_workflow.api.project_holder.ProtocolService",
        side_effect=RuntimeError("boom"),
    )

    holder = ProjectHolder()
    server = create_mcp_server(holder=holder)

    result = _mcp_payload(
        asyncio.run(server.call_tool("load_project", {"project_dir": str(tmp_path)}))
    )

    assert "Failed to initialize services" in result["error"]
    assert "RuntimeError: boom" in result["error"]
    assert not holder.is_loaded()


def _load_project_holder(tmp_path) -> ProjectHolder:
    (tmp_path / "connectivity").mkdir()
    (tmp_path / "connectivity" / "associations.json").write_text(
        json.dumps({"associations": []}), encoding="utf-8"
    )

    class FakeProcess:
        pass

    class Config(BaseModel):
        pass

    class MainParameter(BaseModel):
        pass

    holder = ProjectHolder()
    holder.load(
        ProjectModules(
            project_dir=tmp_path,
            processes={"fake": FakeProcess},
            configs={"fake": Config},
            main_parameter_class=MainParameter,
        )
    )
    return holder


def test_discover_custom_routes_tool_no_project():
    server = create_mcp_server(holder=ProjectHolder())
    result = _mcp_payload(asyncio.run(server.call_tool("discover_custom_routes", {})))
    assert result == {"error": "No project loaded. Use the load_project tool first."}


def test_discover_custom_routes_tool_lists_registered_routes(tmp_path):
    holder = _load_project_holder(tmp_path)
    hook_dir = tmp_path / "customizations" / "routers"
    hook_dir.mkdir(parents=True)
    (hook_dir / "router_hook.py").write_text(
        "def double(x):\n    return x * 2\nCUSTOM_ROUTES = {'double': double}\n",
        encoding="utf-8",
    )
    server = create_mcp_server(holder=holder)

    result = _mcp_payload(asyncio.run(server.call_tool("discover_custom_routes", {})))

    assert result == {
        "name": "double",
        "parameters": [{"name": "x", "required": True, "default": None}],
    }


def test_call_custom_route_tool_no_project():
    server = create_mcp_server(holder=ProjectHolder())
    result = _mcp_payload(
        asyncio.run(server.call_tool("call_custom_route", {"name": "anything"}))
    )
    assert result == {"error": "No project loaded. Use the load_project tool first."}


def test_call_custom_route_tool_unknown_name(tmp_path):
    holder = _load_project_holder(tmp_path)
    server = create_mcp_server(holder=holder)

    result = _mcp_payload(
        asyncio.run(server.call_tool("call_custom_route", {"name": "missing"}))
    )

    assert "not registered" in result["error"]


def test_call_custom_route_tool_success(tmp_path):
    holder = _load_project_holder(tmp_path)
    hook_dir = tmp_path / "customizations" / "routers"
    hook_dir.mkdir(parents=True)
    (hook_dir / "router_hook.py").write_text(
        "def double(x):\n    return x * 2\nCUSTOM_ROUTES = {'double': double}\n",
        encoding="utf-8",
    )
    server = create_mcp_server(holder=holder)

    result = _mcp_payload(
        asyncio.run(
            server.call_tool(
                "call_custom_route", {"name": "double", "kwargs": {"x": 3}}
            )
        )
    )

    assert result["ok"] is True
    assert result["result"] == 6
