import platform
import socket

from jarvis.security.capabilities import Capability
from jarvis.tools.system_info import SystemInfoTool


def test_system_info_tool_requires_system_info_capability():
    assert SystemInfoTool.required_capability == Capability.READ_SYSTEM_INFO


def test_system_info_returns_expected_information(monkeypatch):
    monkeypatch.setattr(socket, "gethostname", lambda: "JARVIS-PC")
    monkeypatch.setattr(platform, "system", lambda: "Windows")
    monkeypatch.setattr(platform, "release", lambda: "11")
    monkeypatch.setattr(platform, "machine", lambda: "AMD64")
    monkeypatch.setattr(platform, "python_version", lambda: "3.14.7")

    tool = SystemInfoTool()

    result = tool.execute({})

    assert result == {
        "computer_name": "JARVIS-PC",
        "operating_system": "Windows",
        "os_release": "11",
        "architecture": "AMD64",
        "python_version": "3.14.7",
    }