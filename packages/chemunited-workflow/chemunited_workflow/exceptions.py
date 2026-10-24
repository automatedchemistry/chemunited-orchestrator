"""Package-level exceptions for chemunited-workflow."""


class ConcurrentClientAccessError(RuntimeError):
    """Raised when a ComponentClient is accessed from more than one thread at a time."""


class RunCancelledError(RuntimeError):
    """Raised internally when a workflow run is cancelled cooperatively."""


class OperatorInputTimeoutError(RuntimeError):
    """Raised when a request_operator_input() call gets no reply within its timeout."""


class DeviceCommunicationError(RuntimeError):
    """Base for transport-level device communication failures across all client protocols."""


class DeviceBusyError(DeviceCommunicationError):
    """Raised when another request to the same device didn't finish within the lock timeout."""


class SilaDeviceError(DeviceCommunicationError):
    """Wraps a sila2 client-side connection/RPC/framework error."""


class OpcUaDeviceError(DeviceCommunicationError):
    """Wraps an asyncua client-side connection/status-code error."""
