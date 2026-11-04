# JARVIS conversation and action flow

Updated 2 November 2026.

JARVIS now keeps a short assistant response separate from the full result. The assistant card shows what it is doing, a brief result, or the clarification it needs. Show details reveals the complete answer, sources, and completed action receipts. Ordinary questions continue to use the chat, with buffered text rendering to avoid a screen update for every tiny token.

## Try a complete conversation

Restart JARVIS and keep your working model selected. In Chat, try:

1. `Open https://www.python.org and find its general contact information.`
2. `Summarize that page.`
3. `What did you just read?`
4. `What is a SQL join?`
5. `Open the other one.`

The first request opens and reads the site using the existing browser tools. The second reuses the observed page through a fresh snapshot. The third answers from actual action receipts without calling a model. The fourth is an ordinary question. The fifth asks which page you mean when no clear selection exists.

Other useful conversations:

- `Open` → `Chrome`: asks for the missing target, then requests the installed application launch.
- `Open Google`: executes locally with a short acknowledgment; it does not ask an AI to decide how to launch a familiar website.
- `Open Google and check your research question`: opens Google and uses the existing Tavily research flow to obtain relevant evidence, without relying on scraping Google's challenge page.
- `Open the second one`: uses only the actual source options presented for the task. An out-of-range or ambiguous selection produces a clarification.
- `Try again`: resumes the unfinished browser/research goal when one exists. Browser work rechecks the current page before continuing; it does not blindly repeat completed actions. Provider overrides such as @local are retained.
- `What are you doing?` during a running task: displays the current status without cancelling it or making an API call.

## Change your instruction while JARVIS works

The input stays available. Type a replacement instruction and press **Interrupt & send**. JARVIS cancels the old request, waits for its worker to release, then starts the replacement. Only the latest submitted replacement is retained; an unsent draft stays in the input. Stop cancels the running request and removes any queued replacement.

This is sequential task replacement. Independent background work is still available through Tasks. This version does not run competing main-chat desktop actions at the same time.

Approval requests appear inline, with Approve once and Deny. Exact arguments remain under Show details. The request stays bound to its waiting worker; an old approval cannot authorize a replacement task. Stop or a replacement instruction can interrupt the approval wait. Typing `no` denies the displayed approval. Existing Always allow and Deny settings remain authoritative.

## Grounding and memory

The session tracks completed tool results, the observed browser page, the installed application target, the current approved file, presented source options, and unfinished read/research work. Reading or saving a file replaces stale browser focus; a later file reference keeps its observed path and the existing file permissions. It clears stale source choices when you change targets. A new chat clears this temporary focus while retaining your existing saved preferences and durable memory.

An ambiguous `yes`, `open it`, or `the other one` never supplies an invented target. Discussing code or asking how to open an application does not turn that discussion into an action. A browser page that changes between turns causes a clarification before further work.

App launches are reported as opening after Windows accepts the request; that does not prove the application has finished rendering. Opening a website through the default browser does not prove its page contents were read. Page-read receipts require the browser tool's returned snapshot. Browser tasks use JARVIS's isolated browser, which has no access to your existing signed-in Chrome session.

## Voice foundation

The desktop worker now receives a structured AssistantReply with a kind, a short message, spoken_text, full details, action events, and grounded choices. Browser completion can provide a short natural reply alongside its full result in one model call. Permission decisions and actions remain in the trusted host.

Pipecat, speech recognition, Kokoro playback, microphone input, wake-word detection, and spoken interruption are not enabled by this change. The typed interaction and cancellation contract is ready for that next stage. Spoken_text is an output channel, not an active audio engine.

## Verification and remaining limits

A real five-turn Gemini conversation opened Python.org, followed its contact/help link, reused that page for a summary without reopening it, answered a question about the previous page, clarified an ambiguous target, and answered a separate SQL question. Real HTTP 503 responses occurred and recovered within the existing retry limit. These calls also showed that cloud response latency remains variable; interface feedback and local state answers do not eliminate provider delays.

Automated tests cover mixed action/question conversations, source selection, stale and missing targets, negated instructions, source changes, failed and denied actions, changed pages, safe continuation, source overrides, inline approvals, stale approvals, cancellation, replacing tasks without overlap, preserving drafts, streamed-text deduplication, and small-window layout. Final validation: 467 tests pass; Ruff and Pyright report no errors. The small-window layout was rendered and checked at 900 × 600, including expanded details and accessible input controls.

The system remains bounded by its installed tools and chosen model. It cannot guarantee an accurate answer to every question or complete an unsupported website interaction. It asks for clarification or reports the blocker rather than inventing an observed target or claiming a rejected action succeeded.
