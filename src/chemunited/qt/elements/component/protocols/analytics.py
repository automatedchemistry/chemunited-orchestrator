from typing import Literal

from pydantic import Field

from .models import CommandSignature, ComponentProtocol

# --- HPLC ---


class HPLCSendMethodParameter(CommandSignature):
    command: str = "send-method"
    description: str = "Send a method to the instrument."
    method_name: str = Field(
        title="Method Name",
        description="The name of the method file to be sent.",
        default="",
    )


class HPLCRunSampleParameter(CommandSignature):
    command: str = "run-sample"
    description: str = (
        "Run an analysis on the instrument with the specified sample and method."
    )
    sample_name: str = Field(
        title="Sample Name",
        description="The name of the sample to be analyzed.",
        default="",
    )
    method_name: str = Field(
        title="Method Name",
        description="The name of the method file to be sent.",
        default="",
    )


class HPLCControlProtocols(ComponentProtocol):

    def __init__(self, name: str):
        super().__init__(name)
        self.commands["send-method"] = HPLCSendMethodParameter
        self.commands["run-sample"] = HPLCRunSampleParameter


# --- MS ---
# run-sample for MS only needs sample_name — different from HPLC, so separate class.


class MSRunSampleParameter(CommandSignature):
    command: str = "run-sample"
    description: str = "Run an analysis on the instrument with the specified sample."
    sample_name: str = Field(
        title="Sample Name",
        description="The name of the sample to be analyzed.",
        default="",
    )


class MSControlProtocols(ComponentProtocol):

    def __init__(self, name: str):
        super().__init__(name)
        self.commands["run-sample"] = MSRunSampleParameter


# --- NMR ---


class NMRSolventParameter(CommandSignature):
    command: str = "solvent"
    method: Literal["GET", "PUT"] = "GET"


class NMRSampleNameParameter(CommandSignature):
    command: str = "sample-name"
    method: Literal["GET", "PUT"] = "GET"


class NMRUserDataParameter(CommandSignature):
    command: str = "user-data"
    method: Literal["GET", "PUT"] = "GET"


class NMRProtocolListParameter(CommandSignature):
    command: str = "protocol-list"
    method: Literal["GET", "PUT"] = "GET"


class NMRSpectrumFolderParameter(CommandSignature):
    command: str = "spectrum-folder"
    method: Literal["GET", "PUT"] = "GET"


class NMRIsBusyParameter(CommandSignature):
    command: str = "is-busy"
    method: Literal["GET", "PUT"] = "GET"


class NMRAcquireSpectrumParameter(CommandSignature):
    command: str = "acquire-spectrum"
    background_tasks: str = Field(
        title="Background Tasks",
        description="Background tasks to use for acquisition.",
        default="",
    )
    protocol: str = Field(
        title="Protocol",
        description="Protocol to use for acquisition.",
        default="",
    )
    options: str = Field(
        title="Options",
        description="Additional acquisition options.",
        default="",
    )


class NMRStopParameter(CommandSignature):
    command: str = "stop"


class NMRControlProtocols(ComponentProtocol):

    def __init__(self, name: str):
        super().__init__(name)
        self.commands["solvent"] = NMRSolventParameter
        self.commands["sample-name"] = NMRSampleNameParameter
        self.commands["user-data"] = NMRUserDataParameter
        self.commands["protocol-list"] = NMRProtocolListParameter
        self.commands["spectrum-folder"] = NMRSpectrumFolderParameter
        self.commands["is-busy"] = NMRIsBusyParameter
        self.commands["acquire-spectrum"] = NMRAcquireSpectrumParameter
        self.commands["stop"] = NMRStopParameter


# --- IR ---
# acquire-spectrum for IR takes no parameters — different from NMR, so separate class.


class IRAcquireSpectrumParameter(CommandSignature):
    command: str = "acquire-spectrum"


class IRStartExperimentParameter(CommandSignature):
    command: str = "start-experiment"


class IRControlProtocols(ComponentProtocol):

    def __init__(self, name: str):
        super().__init__(name)
        self.commands["acquire-spectrum"] = IRAcquireSpectrumParameter
        self.commands["start-experiment"] = IRStartExperimentParameter
        self.commands["stop"] = NMRStopParameter  # identical — reuse
