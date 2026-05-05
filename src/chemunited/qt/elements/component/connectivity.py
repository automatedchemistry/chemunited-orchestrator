import requests
<<<<<<< HEAD
from pydantic import BaseModel, AnyHttpUrl, ConfigDict, Field
=======
from pydantic import BaseModel, AnyHttpUrl, Field
>>>>>>> 4b4729a4d8f98026cfe0203cc24014335f1636d3
from urllib.parse import urlsplit


class ComponentConnnectivity(BaseModel):
<<<<<<< HEAD
    model_config = ConfigDict(validate_assignment=True)

=======
>>>>>>> 4b4729a4d8f98026cfe0203cc24014335f1636d3
    url: AnyHttpUrl = Field(
        default=AnyHttpUrl("http://0.0.0.0:0000"),
        title="Component URL access",
        description="URL for accessing the component.",
    )

    @property
    def is_online(self) -> bool:
        """Check if the component is online."""
        try:
            response = requests.get(self.url, timeout=0.1)
            return response.status_code == 200
        except requests.exceptions.RequestException:
            return False
    
    @property
    def url_component(self) -> str:
        """Get the url of the component."""
        split_url = urlsplit(str(self.url))
        component = split_url.path.lstrip("/")

        if split_url.query:
            component = f"{component}?{split_url.query}"
        if split_url.fragment:
            component = f"{component}#{split_url.fragment}"

        return component


if __name__ == "__main__":
    component = ComponentConnnectivity(url="http://localhost:8000/flume/123456")
    print(component.is_online)
    print(component.url_component)
    
    component_2 = ComponentConnnectivity(url="http://127.0.0.1:1258/spectrometer/123456")
    print(component_2.is_online)
    print(component_2.url_component)
