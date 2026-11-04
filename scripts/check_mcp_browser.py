"""Real MCP browser interactions against a local fixture, with no desktop input.

Uses a separate headless Chromium profile and a scripted planner; no cloud model,
personal tabs, accounts, microphone or third-party form submission.
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from jarvis.agents.browser_workflow import run_browser
from jarvis.models.base import ModelProvider, ModelResponse
from jarvis.tools.browser_mcp import (
    BrowserClickTool,
    BrowserKeyTool,
    BrowserMCPTool,
    BrowserTypeTool,
    PlaywrightMCP,
)


class Fixture(BaseHTTPRequestHandler):
    def do_GET(self):
        body = b'''<title>Jarvis local MCP check</title><h1>Local search fixture</h1>
        <label>Search topic<input aria-label="Search topic" id="query"></label>
        <button onclick="document.getElementById('result').textContent=document.getElementById('query').value">Search</button>
        <h2 id="result">No results yet</h2><a href="/details">Details</a>'''
        self.send_response(200);self.send_header('Content-Type','text/html');self.end_headers();self.wfile.write(body)
    def log_message(self,format,*args):pass


class Planner(ModelProvider):
    name = 'local-test-planner'
    calls = 0
    def generate(self,request):
        data = json.loads(request.prompt);elements = data['page']['elements']
        self.calls += 1
        if self.calls == 1:
            ref = next(ref for ref,label in elements.items() if 'textbox' in label and 'Search topic' in label)
            action = {'action':'type','target':ref,'text':'Java tutorials'}
        elif self.calls == 2:
            ref = next(ref for ref,label in elements.items() if 'button "Search"' in label)
            action = {'action':'click','target':ref}
        else:
            assert 'heading "Java tutorials"' in data['page']['snapshot']
            action = {'action':'finish','answer':'The page shows Java tutorials.','spoken':'The page shows Java tutorials.'}
        return ModelResponse(text=json.dumps(action),provider=self.name,model='fixture')


def main():
    server = ThreadingHTTPServer(('127.0.0.1',0),Fixture)
    thread = threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    base = f'http://127.0.0.1:{server.server_port}'
    client = PlaywrightMCP(headless=True,mode='isolated')
    browser = BrowserMCPTool(client)
    tools = {'click':BrowserClickTool(browser),'type':BrowserTypeTool(browser),'key':BrowserKeyTool(browser)}
    def execute(arguments):
        action = arguments.get('action')
        if action in tools:return tools[action].execute({k:v for k,v in arguments.items() if k!='action'})
        return browser.execute(arguments)
    try:
        # The localhost exception is restricted to this fixture process. The
        # production public-HTTPS navigation policy is not changed.
        with patch('jarvis.tools.browser_mcp.public_url',side_effect=lambda url:url.startswith(base+'/') or url==base):
            browser.execute({'action':'navigate','url':base})
            planner = Planner()
            result = run_browser(planner,execute,'Search this page for Java tutorials and tell me the result.',resume_url=base+'/')
            assert 'Java tutorials' in result
            current = browser.last['url']
            ref = next(ref for ref,label in browser.last['elements'].items() if 'link "Details"' in label)
            BrowserClickTool(browser).execute({'target':ref})
            assert browser.last['url']==base+'/details'
            browser.execute({'action':'back'})
            assert browser.last['url']==current
            tabs = browser.execute({'action':'tabs'})['tabs']
            assert '- 0:' in tabs and '- 1:' not in tabs
            print(json.dumps({'real_mcp_typing':True,'real_mcp_click':True,'observed_result':True,
                'same_tab':True,'back':True,'cloud_calls':0,'desktop_input':False,'planner_steps':planner.calls}))
    finally:
        client.close();server.shutdown();server.server_close()


if __name__=='__main__':main()
