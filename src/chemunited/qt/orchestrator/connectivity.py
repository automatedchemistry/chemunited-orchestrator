from chemunited.qt.utils.flowchem_listener import access_url
from .protocols import OrchestratorProtocols
from pydantic import TypeAdapter, ValidationError, AnyHttpUrl
from loguru import logger


class OrchestratorConnectivity(OrchestratorProtocols):
    def associate_component(self, name: str, urlc: AnyHttpUrl):

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

        status, info = access_url(str(validated_url))
        # Try to find a component-specific icon based on theme
        possibles_mach = [
            c
            for c in info.get("corresponding_class", [])
            if c not in {"FlowchemComponent", "object"}
        ]
        if self.components[name].inf.figure not in info.get("corresponding_class", []):
            logger.warning(
                "Association not possible: It was not possible associate the component {name} that represent a "
                f"{self.components[name].inf.figure} with the online device {validated_url}. "
                "It does not corresponding to each other. Be aware that the component type expected should "
                f"belong to the follow list: {possibles_mach}"
            )
            return

        connectivity.url = validated_url
        
        if self.components[name].widget.connectivity_widget is not None:
            self.components[name].widget.connectivity_widget.save()

        self.parent_ref.online_list.associate_item(component=name)
        
    def disassociate_component(self, name: str):
        self.components[name].url = AnyHttpUrl("http://0.0.0.0:0000")
        self.components[name].widget.connectivity_widget.save()
        
        
        

            
        
        

