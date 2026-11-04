import asyncio
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from jarvis.bootstrap import build_application
from jarvis.core.config import JarvisSettings
from jarvis.core.interaction import InteractionSession, action_event, build_reply
from jarvis.core.tool_request import ToolRequest
from jarvis.security.capabilities import Capability
from jarvis.security.policy import PermissionDecision
from jarvis.tools.browser_mcp import BrowserClickTool, BrowserMCPTool, BrowserTypeTool
from jarvis.tools.executor import PermissionDeniedError
from jarvis.tools.mcp_client import StdioMCPClient
from jarvis.tools.screen_observation import ScreenObservationTool
from jarvis.tools.windows_mcp import WindowsMCP, WindowsSnapshotTool
from jarvis.voice.endpointer import SpeechEndpointer

PAGE = '### Page\n- Page URL: https://example.com/\n- Page Title: Example\n### Snapshot\n- textbox "Search" [ref=e1]\n- button "Search" [ref=e2]\n'


@pytest.fixture(autouse=True)
def fixture_browser_addresses(monkeypatch):
    # These are in-memory browser fixtures, not internet connectivity checks.
    monkeypatch.setattr('jarvis.tools.browser_mcp.public_url',lambda url:url.startswith('https://example.com/'))


class BrowserClient:
    def __init__(self):self.page = PAGE;self.calls = []
    def call(self,name,args):
        self.calls.append((name,args))
        if name == "browser_click":self.page = PAGE.replace('https://example.com/','https://example.com/result')
        return self.page
    def close(self):pass


def test_browser_click_uses_observed_ref_and_records_new_page():
    client = BrowserClient();browser = BrowserMCPTool(client)
    with patch('jarvis.tools.browser_mcp.public_url',return_value=True):
        browser.execute({'action':'snapshot'})
        result = BrowserClickTool(browser).execute({'target':'e2'})
    assert client.calls[-2] == ('browser_click',{'target':'e2'})
    session = InteractionSession();session.record(build_reply('Opened the result',[action_event('browser_click',{},result)]))
    assert session.focus_url == 'https://example.com/result'


def test_browser_rejects_stale_or_invented_refs_before_click():
    client = BrowserClient();browser = BrowserMCPTool(client)
    browser.execute({'action':'snapshot'})
    client.page = PAGE.replace('button "Search"','button "Delete"')
    with pytest.raises(ValueError,match='page changed'):
        BrowserClickTool(browser).execute({'target':'e2'})
    with pytest.raises(ValueError,match='exact element'):
        BrowserClickTool(browser).execute({'target':"getByText('Delete')"})
    assert not any(name == 'browser_click' for name,_ in client.calls)


def test_browser_typing_never_submits_implicitly():
    client = BrowserClient();browser = BrowserMCPTool(client)
    browser.execute({'action':'snapshot'})
    BrowserTypeTool(browser).execute({'target':'e1','text':'Java tutorials'})
    assert ('browser_type',{'target':'e1','text':'Java tutorials','submit':False}) in client.calls
    assert not any(name == 'browser_press_key' for name,_ in client.calls)


@pytest.mark.parametrize('denied',[Capability.USE_BROWSER,Capability.CLICK_UI])
def test_browser_interactions_respect_both_permissions(tmp_path,denied):
    app = build_application(JarvisSettings(workspace_dir=tmp_path))
    try:
        for cap in (Capability.USE_BROWSER,Capability.CLICK_UI):app.tool_service.executor.policy.set_decision(cap,PermissionDecision.ALLOW)
        app.tool_service.executor.policy.set_decision(denied,PermissionDecision.DENY)
        with patch.object(app.tool_service.registry.get('browser_click'),'execute',side_effect=AssertionError('Input reached server')), pytest.raises(PermissionDeniedError):
            app.tool_service.execute(ToolRequest(tool_name='browser_click',arguments={'target':'e1'}),confirmed=True)
    finally:app.shutdown()


def test_mcp_sdk_snake_case_error_is_not_success():
    client = StdioMCPClient('fixture',{'Snapshot'})
    value = SimpleNamespace(is_error=True,content=[SimpleNamespace(type='text',text='Tool refused')])
    with pytest.raises(ValueError,match='Tool refused'):client.decode_result(value)
    with pytest.raises(ValueError,match='not exposed'):client.call('PowerShell',{'command':'anything'})


def test_integration_preferences_survive_app_restart_without_starting_capture(tmp_path):
    settings = JarvisSettings(workspace_dir=tmp_path,state_dir=tmp_path/'state',persist_personal_memory=True)
    app = build_application(settings)
    app.integrations.apply('extension','Default',True)
    assert app.integrations.browser.client.thread is None and not app.screen_control_enabled
    app.shutdown();app = build_application(settings)
    try:
        assert app.integrations.status()['browser_mode'] == 'extension'
        assert app.integrations.status()['profile'] == 'Default'
        assert app.integrations.windows.enabled and app.integrations.windows.client.thread is None
    finally:app.shutdown()


class WindowsClient:
    def __init__(self):self.calls = [];self.tree = '0 Button Save at (100,100)'
    def call(self,name,args):
        self.calls.append((name,args))
        return {'text':'Opened Windows: PRIVATE OTHER APP\nUI Tree:\n'+self.tree,'images':[]}
    def close(self):pass


@pytest.fixture
def windows(monkeypatch):
    screen = ScreenObservationTool();screen.enabled = True;screen.window_handle = 12
    backend = WindowsMCP(screen,WindowsClient());backend.enabled = True
    monkeypatch.setattr('win32gui.IsWindow',lambda _:True)
    monkeypatch.setattr('win32gui.GetWindowText',lambda _:'Fixture')
    monkeypatch.setattr('win32gui.GetWindowRect',lambda _:(0,0,400,300))
    monkeypatch.setattr('win32gui.GetForegroundWindow',lambda:12)
    return backend


def test_windows_observation_requires_capture_scope_and_omits_other_windows(windows):
    tool = WindowsSnapshotTool(windows)
    with pytest.raises(PermissionError):tool.execute({})
    with windows.screen.capture_scope():page = tool.execute({})
    assert 'PRIVATE OTHER APP' not in str(page) and 'Button Save' in page['controls']
    assert windows.client.calls[0][1]['region'] == [0,0,400,300]


def test_windows_action_is_one_bounded_observed_input(windows):
    windows.snapshot()
    windows.act('Click',{'x':100,'y':100})
    assert windows.client.calls[-1] == ('Click',{'loc':[100,100],'button':'left','clicks':1})
    assert windows.last is None
    with pytest.raises(ValueError,match='Observe'):windows.act('Click',{'x':100,'y':100})


def test_windows_changed_controls_and_outside_coordinates_stop_input(windows):
    windows.snapshot()
    with pytest.raises(ValueError,match='outside'):windows.act('Click',{'x':600,'y':100})
    windows.client.tree = '0 Button Delete at (100,100)'
    with pytest.raises(ValueError,match='controls changed'):windows.act('Click',{'x':100,'y':100})
    assert all(name == 'Snapshot' for name,_ in windows.client.calls)


class Vad:
    def __init__(self,states):self.states = iter(states)
    async def analyze_audio(self,_):return SimpleNamespace(name=next(self.states))
    async def cleanup(self):pass


class Turn:
    def __init__(self,states):self.states = iter(states);self.cleared = False
    def append_audio(self,*_a,**_k):pass
    async def analyze_end_of_turn(self):return SimpleNamespace(name=next(self.states)),None
    def clear(self):self.cleared = True
    async def cleanup(self):pass


def test_smart_turn_holds_short_pause_and_keeps_continued_speech_together():
    async def run():
        turn = Turn(['INCOMPLETE','COMPLETE'])
        endpoint = SpeechEndpointer(Vad(['SPEAKING','QUIET','SPEAKING','QUIET']),turn)
        chunk = b'\0\0'*8000
        results = [await endpoint.feed(chunk) for _ in range(4)]
        assert [started for started,_ in results] == [True,False,False,False]
        assert all(segment is None for _,segment in results[:3])
        assert results[-1][1] == chunk*4 and turn.cleared
        await endpoint.close()
    asyncio.run(run())


def test_smart_turn_has_bounded_wait_even_if_model_always_says_incomplete():
    async def run():
        endpoint = SpeechEndpointer(Vad(['SPEAKING','QUIET','QUIET','QUIET']),Turn(['INCOMPLETE']*3))
        chunk = b'\0\0'*8000
        results = [await endpoint.feed(chunk) for _ in range(4)]
        assert results[-1][1] == chunk*4
        await endpoint.close()
    asyncio.run(run())


def test_smart_turn_inference_failure_falls_back_without_losing_the_utterance():
    class FailedTurn(Turn):
        async def analyze_end_of_turn(self):raise RuntimeError('Local inference failed')
    async def run():
        endpoint = SpeechEndpointer(Vad(['SPEAKING','QUIET']),FailedTurn([]))
        chunk = b'\0\0'*8000
        await endpoint.feed(chunk)
        _,segment = await endpoint.feed(chunk)
        assert segment == chunk*2 and endpoint.turn_failed and endpoint.turn_analyzer is None
        await endpoint.close()
    asyncio.run(run())
