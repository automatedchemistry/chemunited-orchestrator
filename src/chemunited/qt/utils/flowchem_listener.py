from zeroconf import Zeroconf, ServiceBrowser, ServiceListener
from flowchem.client.common import FLOWCHEM_TYPE
from collections import defaultdict
from loguru import logger
from typing import Any
import requests
import ipaddress
import time


def access_url(url: str, timeout=5) -> tuple[bool, Any]:
    try:
        response = requests.get(
            url=url, timeout=timeout
        )
        if response.status_code == 200:
            try:
                return True, response.json()
            except ValueError:
                return True, response.text
        else:
            return False, response
    except requests.exceptions.RequestException as error:
        print(f"Error while trying to access the URL '{url}': {error}")
        return False, None


class SimpleListener(ServiceListener):
    def __init__(self):
        self.addresses = set()

    def add_service(self, zc: Zeroconf, type_: str, name: str):
        info = zc.get_service_info(type_, name)
        url = base_url_from_service_info(info)
        if url:
            self.addresses.add(url)

    def update_service(self, zc: Zeroconf, type_: str, name: str):
        self.add_service(zc, type_, name)

    def remove_service(self, zc: Zeroconf, type_: str, name: str):
        # optional: could remove from set
        pass


def base_url_from_service_info(info) -> str | None:
    if not info or not info.addresses:
        return None
    ip = ipaddress.ip_address(info.addresses[0])
    return f"http://{ip}:{info.port}"


def list_flowchem_addresses(timeout_ms: int = 2000) -> list[str]:
    """Discover FlowChem services via Zeroconf within a timeout."""
    zc = Zeroconf()
    try:
        listener = SimpleListener()
        browser = ServiceBrowser(zc, FLOWCHEM_TYPE, listener)
        try:
            time.sleep(timeout_ms / 1000)
        finally:
            browser.cancel()
        return sorted(listener.addresses)
    finally:
        zc.close()


def paths_to_device_components(paths: dict) -> dict[str, list[str]]:
    """
    Convert OpenAPI paths into { device: [components...] }.
    Example: '/O2MFC/MFC/get-flow-rate' -> { 'O2MFC': ['MFC'] }
    """
    devices = defaultdict(set)

    for raw_path in paths.keys():
        seg = [s for s in raw_path.strip("/").split("/") if s]
        if len(seg) >= 2:
            device, component = seg[0], seg[1]
            devices[device].add(component)
        elif len(seg) == 1:
            # Device-only path like "/O2MFC/"
            _ = devices[seg[0]]

    # convert sets → sorted lists
    return {dev: sorted(list(comps)) for dev, comps in devices.items()}


def flowchem_addresses_dict(timeout_ms=2000) -> dict[str, dict[str, list[str]]]:
    result = {}
    flowchem_address = list_flowchem_addresses(timeout_ms)
    for url in flowchem_address:
        ok, data = access_url(f"{url}/openapi.json", timeout=1)
        if not ok:
            logger.warning(
                f"There is a flowchem running in the address: {url}, however openapi.json is not accessible!"
            )
            continue
        elif "paths" not in data:
            logger.warning(
                f"There is a flowchem running in the address: {url}, however this version does not allow access to "
            )
            continue
        elif "/startup_config" not in data["paths"]:
            logger.warning(
                f"There is a flowchem running in the address: {url}, however this version does not allow access to "
                f"configuration file. Update the version to allow a smooth connection with chemunited."
            )
            continue
        result[url] = paths_to_device_components(data["paths"])
    return result


class flowchem_servers:

    def __init__(self):

        self.servers: dict[str, dict[str, list[str]]] = {}

        self.correspondent: dict[str, str] = {}

    def match_component(self, url, abstract_component):

        if url not in self.correspondent or not self.correspondent[url]:
            self.correspondent[url] = abstract_component
            return True
        else:
            return False

    def mismatch_component(self, abstract_component):
        url = ""
        for key, value in self.correspondent.items():
            if value == abstract_component:
                url = key
                break
        if url:
            self.correspondent[url] = ""

    def get_matched_component(self, url) -> str | None:

        if url in self.correspondent:

            return self.correspondent[url]

        return None

    def update(self):

        self.servers = flowchem_addresses_dict()


FLOWCHEM_SERVERS = flowchem_servers()


if __name__ == "__main__":
    FLOWCHEM_SERVERS.update()
    print(FLOWCHEM_SERVERS.servers)
