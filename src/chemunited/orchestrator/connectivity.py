from loguru import logger
from pydantic import AnyHttpUrl, TypeAdapter, ValidationError

from chemunited.utils.flowchem_listener import access_url

from .protocols import OrchestratorProtocols


class OrchestratorConnectivity(OrchestratorProtocols):
    def _apply_component_connectivity(
        self,
        name: str,
        urlc: AnyHttpUrl | str,
        *,
        update_online_list: bool = False,
    ) -> bool:
        try:
            validated_url = TypeAdapter(AnyHttpUrl).validate_python(urlc)
        except ValidationError:
            logger.error(f"Invalid URL for component {name}.")
            return False

        component = self.components[name]
        component.connectivity.url = validated_url
        component.graph.set_online(component.is_online, str(component.url))

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

    def associate_component(self, name: str, urlc: AnyHttpUrl, validate_object=True):

        if name not in self.components:
            logger.error(f"Component {name} not found.")
            return

        if not hasattr(self.components[name], "connectivity"):
            logger.error(f"Component {name} is not a electronic component.")
            return

        connectivity = self.components[name].connectivity

        if connectivity.is_online:
            logger.error(f"Component {name} is already connected.")
            return

        try:
            validated_url = TypeAdapter(AnyHttpUrl).validate_python(urlc)
        except ValidationError:
            logger.error(f"Invalid URL for component {name}.")
            return

        if validate_object:
            status, info = access_url(str(validated_url))
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

        self._apply_component_connectivity(name, "http://0.0.0.0:0000")
