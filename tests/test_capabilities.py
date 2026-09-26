from jarvis.security.capabilities import Capability


def test_read_file_capability_value():
    assert Capability.READ_FILE == "READ_FILE"


def test_send_email_capability_value():
    assert Capability.SEND_EMAIL == "SEND_EMAIL"    