# Jarvis planner comparison

The first comparison ran on November 4, 2026 using the installed Jarvis application code and an isolated Pydantic AI 2.65.0 environment. Both paths used the saved Groq GPT-OSS 20B model for live reasoning. Jarvis executes navigation through its existing permission checks and observed-link validation. Simple commands, result ordinals and Back use the existing local path.

| Live scenario | Current Jarvis | Prototype |
| --- | --- | --- |
| Open Calculator and open the fixture page | Both passed, zero model requests | Both passed, zero model requests |
| Ask what SQL is | 1.56 s, 1 request, 809 tokens | 1.93 s, 1 request, 540 tokens |
| Show the returns guide and tell me the deadline | Stopped before opening the guide, 1 request | Opened the guide and answered 37 days, 2.55 s, 2 requests, 1,952 tokens |
| Redirect with “No, wait, go back” | Skipped because the guide had not opened | Returned to the help page, zero model requests |
| Open the second result | Passed, zero model requests | Passed, zero model requests |

The diagnostic repeat captured HTTP 400 for the current browser request. It did not establish the exact cause of the rejection. Both lanes disabled provider retries and failover for the trial, so the normal app may recover from some errors that were terminal here. A failed request returned no token usage. Seven live requests were made across the comparison and repeat.

Both flows passed the controlled cases, including cancellation after a model response, a quota error after verified navigation, and contextual navigation. The prototype also rejected a proposed link index absent from the observed page. These tests used simulated browser pages and a simulated Calculator launch. The live tests exercised the actual Groq API but used those same tool fixtures. Timings are single observations. The prototype is a lab entry point with a limited action vocabulary. The main app was left on its current flow, and live microphones, speakers and public websites were outside this comparison.

The result supports a limited next trial of typed decisions for multi-step browser work. The direct question took longer with the prototype, so these results do not support replacing general chat on speed grounds. The next comparison should cover several public pages and mixed follow-ups before broadening the prototype.

From the repository root, set up Jarvis's normal Windows environment with `uv sync --locked`. Then create a separate environment for the planner and run the comparison in PowerShell.

```powershell
$env:PYDANTIC_AI_NO_BANNER = '1'
uv venv .\experiments\browser-planner\.venv --python .\.venv\Scripts\python.exe
uv pip sync --python .\experiments\browser-planner\.venv\Scripts\python.exe .\experiments\browser-planner\requirements.lock
& .\experiments\browser-planner\.venv\Scripts\python.exe .\experiments\browser-planner\compare.py
```

`--live` uses the saved Groq connection, with a maximum of eight requests per comparison. The lab uses the existing Jarvis Windows dependencies. Set `JARVIS_BASE_VENV` to reuse the main `.venv` from another checkout on the same machine. The isolated dependency versions are in `requirements.lock`.

Recorded results are in `results/`. The public copy includes scores, timings, request counts and visited URLs. The original page excerpts stay in the local lab.

## Public-site pilot

The second trial used one real Playwright tab in a fresh profile and the saved Groq model. It exercised opening an observed link, answering from the destination, and a follow-up about the same page. The test browser closed at the end of every run.

| Case | Result | Time after starting page loaded | Groq requests |
| --- | --- | ---: | ---: |
| Python tutorial and intended audience | Opened the tutorial and correctly explained the prior programming knowledge it assumes | 1.43 s | 2 |
| Python follow-up about a first-time programmer | Answered using the same page with verified source lines | 0.58 s | 1 |
| SQLite Getting Started | Opened the guide and verified the `sqlite3` answer from the page | 1.65 s | 2 |
| W3C Accessibility Principles | Opened the correct page. Groq rate-limited the answer in the combined run. The isolated repeat reached Groq successfully, but Jarvis rejected the evidence references and returned partial completion. | 1.95 s on isolated repeat | 2 on isolated repeat |

The prototype ranks the links it has observed and retains their original indices for verification. This surfaced W3C's target at position 30, beyond the former first-20 cutoff. The text formatter joins words split by bold or emphasis and retains page link labels as evidence. The model supplies line numbers and Jarvis retrieves the text itself. The pilot allows one navigation per request, followed by a separate answer decision. This prevents the navigation loop seen in the earlier SQLite run and limits the kinds of browser tasks the pilot can complete.

The Python task went from 6,077 to 2,881 reported tokens across its two reasoning calls. The prompt size and Groq reasoning setting changed together, so this comparison measures their combined effect. All 22 controlled checks passed, including rejecting an unobserved source line. Back used zero Groq requests on both completed sites. The correction was simulated as a voice transcript. This round used 25 Groq requests across the initial run, debugging runs and final repeat.

The first three-site run covered a small sample of browser behavior. Microphone performance and signed-in sessions were outside that trial.

Run the browser-only preflight without `--live`. The live command uses the existing Groq connection.

```powershell
& .\experiments\browser-planner\.venv\Scripts\python.exe .\experiments\browser-planner\public_trial.py --live --limit 7
```

The public trial uses Jarvis's existing Playwright setup. See [browser setup](../../docs/BROWSER_MCP.md). Initial results are in `results/public-final-results.json`, `results/public-w3c-repeat.json` and `results/public-controlled-results.json`.

### Evidence fix and W3C retest

The response schema now restricts evidence IDs to lines actually present in the excerpt. Jarvis resolves and deduplicates those lines. Answers can cite more than four valid lines, within the existing excerpt limit. The prototype also preserves full numbered answers in chat and keeps their items together in spoken text. The previous sentence shortener cut off a numbered answer even when all four evidence lines had verified successfully.

The live W3C retest opened the correct page and returned all four principles with verified source lines in 1.73 seconds after the starting page loaded. It used two Groq requests. Back used zero requests and the test browser closed. All 25 controlled checks passed. The evidence fix and display fix were verified using four live requests in total across both W3C runs. The change lives in the prototype.

See `results/w3c-evidence-final.json` and `results/evidence-controlled-results.json` for the retest data. The next comparison should exercise corrections and follow-ups through the desktop UI on varied tasks, with the same model and permissions on both branches. Compare correct actions, response time and provider requests before choosing which code to adopt.
