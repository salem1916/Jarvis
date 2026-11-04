# Browser and conversation milestone — November 3, 2026

Jarvis now uses one configured browser connection for opening a website and
working with it afterward. This stage uses the separate Jarvis browser and does
not need the Chrome extension. The separate browser has its own session; it does
not automatically share personal Chrome tabs, cookies, or signed-in accounts.

The saved reasoning connection on this laptop is Groq, using the existing
`openai/gpt-oss-20b` model and saved credential. No new key, subscription, or billing
setting was created. Hermes remains an optional engine; its configured local
gateway was not listening during verification. The launcher no longer starts a
Hermes gateway automatically when opening Jarvis.

## Behavior

- Simple website openings and explicit same-tab navigation use the configured
  browser directly, without asking a language model to perform the opening.
- Back and numbered links/results operate on a fresh observed page without
  requiring an AI connection. A changed page triggers clarification before
  choosing a numbered target; an explicit Back command follows current history.
- Redirects update conversation focus using the destination actually observed.
- Compound browser requests and explicit `browser:` tasks keep their browser
  routing and conversation context, including when retrying incomplete work.
- Typed and spoken Wait/Continue commands hold and release the same task.
  Corrections cancel the old task and queue the latest instruction after it
  releases; a late model proposal cannot start a new action after cancellation.
- Cancelling does not undo an action that already completed. Cancellation of an
  in-flight external operation cannot guarantee that the external action did not
  take effect.
- A click or key whose result cannot be verified stops the workflow. Jarvis does
  not automatically repeat that input or mark it successful.
- Provider outages retain evidence of completed work and give a short spoken
  explanation. Provider diagnostics and observed URLs remain in Show details.
- Hermes can supply browser planning JSON without receiving the Jarvis action
  bridge. Its CLI planning requests now use cooperative cancellation even when
  token streaming is disabled.

## Verification

- Full local regression suite: **634 passed**.
- Ruff: passed. Pyright: no errors or warnings.
- Real Playwright MCP component check: typed into an observed field, clicked its
  button, verified the changed page, followed a link, used Back, and confirmed
  one browser tab. Separate invisible Chromium; no personal Chrome profile.
- Application-level browser check: opened the local fixture through the real
  application, completed a scripted browser task, opened another page in the
  same tab, and returned with a simulated spoken correction. The backend closed
  afterward.
- Live Groq application check: **one actual provider request** read the demo
  page's title successfully. Opening the other page and Back used no additional
  model requests. No provider failover or billing activation occurred.
- The microphone and speakers were **not opened**. Voice instruction tests
  injected recognized text. Real-room echo, recognition accuracy, and physical
  voice interruption still need an interactive device test.

The local test server's HTTP/localhost allowance exists only inside the check
scripts. Production browser navigation retains its public HTTPS policy.

## Try the updated app

Close and reopen Jarvis to load the changes. Settings should show Groq and
Separate Jarvis browser. Leave the Chrome extension uninstalled.

Try a short sequence such as:

1. “Open Google and search for Python tutorials.”
2. “Open the first result.”
3. “Go back.”
4. “What is SQL?”

Then try Wait, Continue, and a new instruction while a browser task is running.
These are examples for checking the general flow, not topic-specific code.
Some websites can still present login prompts or human-verification challenges;
Jarvis should report the actual blocker rather than guess or claim success.

## Reproduce checks

```powershell
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/ruff.exe check src tests scripts
.venv/Scripts/pyright.exe --pythonpath .venv/Scripts/python.exe src scripts
.venv/Scripts/python.exe scripts/check_mcp_browser.py
.venv/Scripts/python.exe scripts/check_browser_conversation.py
```

The optional live check makes one request using the existing Groq credential:

```powershell
.venv/Scripts/python.exe scripts/check_browser_conversation.py --live-groq
```

Groq quotas still apply. The local tests do not establish reliability for every
website or every future model response.
