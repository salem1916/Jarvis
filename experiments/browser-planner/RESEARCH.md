# Jarvis: what to reuse next

November 4, 2026. This is a source review and code audit. No new dependency, browser extension, background service, or API request was run for this review.

## Decision

Prototype **Pydantic AI** as the decision layer for a small set of assistant conversations. Keep Jarvis's current permissions, Playwright actions, local Windows commands, session memory, and voice devices in place. Compare it with the existing flow before merging. Evaluate Browser Use only if the test shows that reading or interacting with complex pages remains the biggest problem.

The plugin catalog returned a hosted browser service, TinyFish, and a recording integration, Plaud. Those are integrations for ChatGPT, not drop-in libraries for Jarvis's Windows runtime. Neither addresses the main problem here: keeping the user's intent and the verified action state connected across turns. No catalog installation is needed for the proposed prototype.

## What the current app explains

- `src/jarvis/tools/browser_mcp.py` starts the separate browser with `--isolated`. Your personal Chrome session and that temporary browser have different login state. Seeing a login screen is expected. An optional dedicated **saved Jarvis profile** would let you sign in yourself and retain that session without reconnecting personal Chrome. Microsoft documents [persistent versus isolated profiles](https://github.com/microsoft/playwright-mcp#user-profile).
- `src/jarvis/core/application.py` coordinates several paths for conversation, search intent, screen tasks, and browser tasks. `src/jarvis/agents/browser_workflow.py` can request a new model decision at each of six planning steps. That is a potential source of latency and quota pressure, not a measured breakdown of this particular report.
- `src/jarvis/core/interaction.py` already has useful focus, search, and retry state. Build on it with a clear current goal, verified action receipts, and pending work. A new memory service alone cannot infer which prior result or pending action the user means.
- `src/jarvis/voice/worker.py` already uses Pipecat's Silero, Smart Turn, Whisper, and Kokoro components. The last milestone's real provider test checked a simple page title; voice redirection tests injected recognized text. Those checks don't establish natural live conversation, page competence on arbitrary sites, or speaker echo performance.

## Shortlist

| Project | What it would replace or improve | Decision |
| --- | --- | --- |
| [Pydantic AI](https://github.com/pydantic/pydantic-ai) | Validated model decisions, message history, and request/tool budgets. Supports [Groq](https://pydantic.dev/docs/ai/models/groq/) and can defer a proposed action for external execution or approval. | First experiment. Use `pydantic-ai-slim[groq]` in an isolated environment; compare with the same Groq model. Jarvis keeps control of side effects. |
| [Browser Use](https://github.com/browser-use/browser-use) | Python browser worker for open-ended page tasks. Documents [Groq support](https://docs.browser-use.com/open-source/supported-models) and [limits on actions, history and time](https://docs.browser-use.com/open-source/customize/agent/all-parameters). | Candidate for difficult pages only. Its own planning loop can also consume requests; use a test profile, allowlisted sites, short time limits, and no automatic model fallback. Do not hand it a personal signed-in profile for the trial. |
| [Stagehand](https://github.com/browserbase/stagehand) | Can [find and propose structured page actions](https://docs.stagehand.dev/v3/basics/observe) before execution, and [run a local browser](https://docs.stagehand.dev/v3/configuration/browser). | Alternative if the gap is finding controls or extracting data. Avoid adding a second browser engine alongside Browser Use. |
| [Pipecat examples](https://github.com/pipecat-ai/pipecat-examples) | Reference for one voice pipeline that clears pending audio and cancels work on an interruption. [Pipecat interruption design](https://docs.pipecat.ai/pipecat/fundamentals/interruptions). | Reuse what is already installed; no ZIP needed. Measure on the laptop speakers and improve turn timing and streaming where measurements show a problem. |

For the planner trial, use a small validated decision such as `reply`, `clarify`, or `propose_action`. Have Jarvis resolve and check the target before it acts. Keep deterministic commands such as opening known apps and Back out of the model loop. Share the same current goal and action receipts across text and voice. Never let “cancel” erase the record of an action already performed. The voice layer can give a short acknowledgment while a longer request works and speak the verified result separately from detailed text.

Groq documents [strict structured outputs](https://console.groq.com/docs/structured-outputs) for the currently selected GPT-OSS 20B. That mode should be tested as a decision-only request: Groq does not combine it with streaming or tool use. [Framework request limits](https://pydantic.dev/docs/ai/api/pydantic-ai/usage/) do not count every SDK retry, so count outgoing provider attempts too and disable silent retries or fallback in the comparison. A local browser still uses provider quota when Groq plans its next step.

## Trial that can decide whether to adopt it

Run the current app and the prototype against the same fixtures and model. Include public browsing as a separate smoke test so network variation does not dominate the comparison. Avoid personal accounts during the benchmark.

| Scenario | Pass condition |
| --- | --- |
| Open an installed app, then ask a direct question | Open uses zero model calls; the question uses the selected provider without taking an unrelated action. |
| Find information and show the supporting page | The displayed page and answer refer to the same observed source. |
| Follow up with “the second result”, then change the topic | Use the current result list; a new topic does not inherit a stale target. |
| Interrupt with “wait, go back instead” | Old speech stops; no new old-plan action starts; a completed action remains in history. |
| Simulate a provider limit after a tool succeeds | Tell the user what happened and what remains; don't replay the completed action or silently switch providers. |
| Finish, quit, and reopen | Owned test workers exit. If the saved-profile option is tested, only that dedicated browser's login survives. |

Record completion, wrong/duplicate actions, actual model requests and tokens, time to first visible response and final result, and idle CPU/memory after cleanup. On real speakers also record time from starting to speak until Jarvis falls silent. Adopt the prototype if it preserves correct actions and interruption behavior and improves measured speed, request count, or code clarity. If only hard pages lose, test one browser worker next. If voice dominates the delay, work on that pipeline next instead. These are acceptance criteria, not reported benchmark results.
