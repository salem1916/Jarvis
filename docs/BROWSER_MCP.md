# Browser tools in JARVIS

Implemented 1 November 2026.

## What each part does

- **The model** (your selected Gemini, another API, or a local model) decides the next step.
- **Tavily** searches the web and extracts public page content. It is connected directly through its keyless API; no Tavily account is needed for this mode. Shared rate limits apply.
- **MCP** means Model Context Protocol. It is the message format that lets JARVIS discover and call an external tool server. MCP itself is not an AI model or a search service.
- **Playwright MCP** controls a separate browser for JARVIS. JARVIS starts Microsoft's server locally and exposes a small set of its tools to the browser workflow.

For example: you ask for a website's contact information → JARVIS opens the site → the model reads a structured snapshot of the page → chooses an observed contact link → JARVIS checks browser permission and follows that link → the model summarizes what it read. No website-specific rule is needed.

## Try it now

1. Restart JARVIS to load the updated code.
2. Keep your working Gemini model selected in **Settings → Intelligence**.
3. Under **Settings → Web research**, click **Check Playwright MCP connection**. This checks tool discovery; the browser opens when a navigation task starts.
4. Under **Permissions**, choose your preferred browser setting. **Always allow** avoids repeated browser approval prompts; **Ask** requests approval for operations; **Deny** blocks the workflow before model planning.
5. In Chat, send: `browser: Open https://www.python.org and find its general contact information. Read the contact page and summarize where to ask questions.`

The `browser:` prefix explicitly chooses browser navigation. Leading spaces and copied list markers such as `1.`, `2)`, or `-` are accepted too; you do not need to remove them. An instruction starting with open/visit/browse, containing a full HTTPS URL and “and” or “then”, also chooses this path. An ordinary `open Google` keeps the fast local opening path. A request to research a topic uses Tavily search and source checking.

Navigation uses an isolated browser rather than your existing signed-in Chrome tabs. It can open public HTTPS pages, read snapshots, follow observed links, and list its own tabs. Typing into forms, arbitrary button clicks, uploads, downloads, login automation, and arbitrary JavaScript are not exposed. Some sites require those features or block automation, so this stage cannot complete every browser task.

The model has at most six decision steps. It receives the current page snapshot and observed links, and JARVIS rechecks the page before following a link. Answers include the pages actually observed. This records evidence; it does not guarantee the model's interpretation is correct. Stop cancels the pending host request and prevents further workflow steps; navigation already started may have occurred.

## Installed components and reproducible setup

This computer already has the required components. The following is for a fresh checkout, from the repository root in PowerShell, after installing Python dependencies and Node.js 18 or later:

```powershell
npm.cmd --prefix .mcp ci --ignore-scripts --no-audit --no-fund
$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path (Get-Location) '.browsers'
.venv\Scripts\python.exe -m playwright install chromium
```

`.mcp/package.json` and its lockfile pin `@playwright/mcp` to 0.0.84. Generated dependencies, browser files, snapshots, configuration, and server logs are ignored by Git. The server starts on demand over local standard input/output; no publicly listening MCP port or extra API key is needed. The model still consumes its own API allowance.

The connection lives in `src/jarvis/tools/browser_mcp.py`; the bounded model workflow is in `src/jarvis/agents/browser_workflow.py`. Calls pass through JARVIS's normal browser capability checks. The wrapper exposes only `browser_navigate`, `browser_snapshot`, and tab listing. It validates public HTTPS navigation targets; this is not operating-system network isolation and does not prefilter every redirect or page subresource.

## Verification

A live end-to-end test using the saved Gemini connection opened Python.org, selected its observed “Help / Help & General Contact” link, navigated to `/about/help/`, and summarized the help and contact options from that page. No live credentials are included in source or tests.

Automated tests cover changed-page rejection, observed link selection, public URL validation, unsupported tool rejection, snapshot file path confinement, denied browser permission, pending request cancellation, and model-directed navigation. The broader existing suite also covers routing and desktop controls.

Official references: [Playwright MCP](https://github.com/microsoft/playwright-mcp), [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk), [Tavily keyless API](https://docs.tavily.com/documentation/keyless).


## Follow-up fix: copied commands and Gemini tool results

A copied `1. browser: ...` request previously missed browser routing and entered the general action bridge. A live diagnostic reproduced the subsequent Gemini HTTP 400: the adapter had dropped the opaque thought signature from a model-generated function call. Gemini requires that state in the following tool-result request. The adapter now preserves each signature with its original call, retains it when conversation messages are copied, and sends it back only through the Gemini adapter. No signature is invented, and permission checks still apply.

The exact numbered Python.org request now completed in a live test in 5.5 seconds, visiting both the homepage and help/contact page. A separate real Gemini function-call/result round trip passed. This is one measured run, not a guaranteed response time. A stream-cancellation cleanup race discovered in validation was also fixed: pending readers now unwind before their response closes.

Reference: [Google's Gemini compatibility documentation](https://ai.google.dev/gemini-api/docs/openai).


## Temporary service failures and partial completion

Updated 2 November 2026.

Gemini requests now retry HTTP 502, 503, and 504 up to twice, sharing that allowance across the entire chat turn and its internal planning steps. Typical waits are about 1 and 2 seconds, with small random variation. The same model and connection are used. A short Retry-After instruction is respected; a server-requested delay over 5 seconds ends automatic recovery so the app does not wait indefinitely. Each extra attempt counts towards managed daily request limits and rechecks connection approval.

Retries repeat only the failed AI request. JARVIS does not replay a completed navigation or other PC action. Invalid requests, authentication failures, quota errors, network timeouts, and interrupted/partial streams are not retried by this feature. Stop interrupts a retry wait and prevents another attempt.

During browser work, the status shows which page was read and when Gemini is being retried. If the provider remains unavailable, the final chat message says **Task partly completed**, lists the pages actually opened and read, and explains that AI analysis is unfinished. If no page was observed, it says so. Stopping a browser workflow also includes the completed pages in the stop message.

Validation used controlled HTTP failures rather than waiting for a real Gemini outage. Tests verify recovery after two failures, the retry limit, shared limits across planning steps, unchanged request contents, no repeated browser actions, partial-completion messages through the desktop worker, cancellation during backoff, and managed daily caps. The full suite passes: 421 tests, with Ruff and Pyright checks clean.

Retry strategy reference: [Google's troubleshooting guide](https://aistudio.google.com/docs/troubleshooting#retry-strategy).
