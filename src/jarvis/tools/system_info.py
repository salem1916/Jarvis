import platform
import socket
from collections.abc import Mapping

from jarvis.security.capabilities import Capability
from jarvis.tools.base import Tool


class SystemInfoTool(Tool):
    name = "system_info"
    description = "Read basic information about the local computer."
    required_capability = Capability.READ_SYSTEM_INFO

    def execute(self, arguments: Mapping[str, object]) -> object:
        return {
            "computer_name": socket.gethostname(),
            "operating_system": platform.system(),
            "os_release": platform.release(),
            "architecture": platform.machine(),
            "python_version": platform.python_version(),
        }