from loguru import logger
from pydantic import AnyHttpUrl, TypeAdapter, ValidationError

from chemunited.connectivity.openapi_commands import (
    apply_openapi_commands,
    reset_protocol_to_default,
)
from chemunited.utils.flowchem_listener import FLOWCHEM_SERVERS, access_url

from .protocols import OrchestratorProtocols


class OrchestratorConnectivity(OrchestratorProtocols):
    def _apply_component_connectivity(
        self,
        name: str,
        urlc: AnyHttpUrl | str,
        *,
        update_online_list: bool = False,
        inspect_commands: bool = True,
    ) -> bool:
        try:
            validated_url = TypeAdapter(AnyHttpUrl).validate_python(urlc)
        except ValidationError:
            logger.error(f"Invalid URL for component {name}.")
            return False

        component = self.components.electronic[name]
        component.connectivity.url = validated_url
        online = component.graph.set_online(component.is_online, str(component.url))
        if inspect_commands and online:
            self._inspect_component_commands(name)

        parent_ref = getattr(self, "parent_ref", None)
        if (
            update_online_list
            and parent_ref is not None
            and hasattr(parent_ref, "online_list")
        ):
            parent_ref.online_list.associate_item(
                component=name,
                text=component.url_component,
            )

        return True

    def _inspect_component_commands(self, name: str) -> None:
        component = self.components[name]
        openapi = self._openapi_for_component(component)
        if openapi is None:
            reset_protocol_to_default(component)
            self._refresh_command_list()
            logger.warning(
                f"Could not inspect FlowChem commands for component {name!r}; "
                "using default commands."
            )
            return

        added = apply_openapi_commands(component, openapi)
        self._refresh_command_list()
        if added:
            logger.info(
                f"Added {added} dynamic FlowChem command(s) for component {name!r}."
            )

    def _openapi_for_component(self, component) -> dict | None:
        base_url = component.connectivity.base_url.rstrip("/")
        cached = FLOWCHEM_SERVERS.get_openapi(base_url)
        if cached is not None:
            return cached

        ok, data = access_url(f"{base_url}/openapi.json", timeout=1)
        if (
            not ok
            or not isinstance(data, dict)
            or not isinstance(data.get("paths"), dict)
        ):
            return None

        FLOWCHEM_SERVERS.register_openapi(base_url, data)
        return data

    def _refresh_command_list(self) -> None:
        parent_ref = getattr(self, "parent_ref", None)
        command_list = getattr(parent_ref, "command_list", None)
        sync_protocols = getattr(command_list, "sync_protocols", None)
        if callable(sync_protocols):
            sync_protocols()

    def associate_component(self, name: str, urlc: AnyHttpUrl, validate_object=True):

        if name not in self.components:
            logger.error(f"Component {name} not found.")
            return

        if not hasattr(self.components[name], "connectivity"):
            logger.error(f"Component {name} is not a electronic component.")
            return

        connectivity = self.components.electronic[name].connectivity

        if connectivity.is_online:
            logger.error(f"Component {name} is already connected.")
            return

        try:
            validated_url = TypeAdapter(AnyHttpUrl).validate_python(urlc)
        except ValidationError:
            logger.error(f"Invalid URL for component {name}.")
            return

        if validate_object:
            _, info = access_url(str(validated_url))
            if not isinstance(info, dict):
                info = {}
            # Try to find a component-specific icon based on theme
            possibles_mach: list[str] = [
                c.lower()
                for c in info.get("corresponding_class", [])
                if c not in {"FlowchemComponent", "object"}
            ]
            if self.components[name].inf.figure.lower() not in possibles_mach:
                logger.warning(
                    "Association not possible: It was not possible associate the component {name} that represent a "
                    f"{self.components[name].inf.figure} with the online device {validated_url}. "
                    "It does not corresponding to each other. Be aware that the component type expected should "
                    f"belong to the follow list: {possibles_mach}"
                )
                return

        self._apply_component_connectivity(
            name,
            validated_url,
            update_online_list=True,
        )

    def disassociate_component(self, name: str):
        if name not in self.components:
            logger.error(f"Component {name} not found.")
            return

        if not hasattr(self.components[name], "connectivity"):
            logger.error(f"Component {name} is not a electronic component.")
            return

        self._apply_component_connectivity(
            name,
            "http://0.0.0.0:0000",
            inspect_commands=False,
        )
        reset_protocol_to_default(self.components[name])
        self._refresh_command_list()
