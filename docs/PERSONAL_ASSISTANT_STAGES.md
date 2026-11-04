# JARVIS personal-assistant direction

31 October 2026

The product direction is one assistant that talks with you, uses your connected tools, works on assigned tasks while you continue chatting, and brings useful results back for your decision. It should show what it knows, where the information came from, and what it proposes to do next. GPU/local inference and API inference are interchangeable reasoning backends; the action and approval system stays consistent.

There is no business system to connect yet. Sales totals and client callbacks must remain unavailable until a real data source exists. They must never be generated from a model's guesses.

## Stage 1 — background updates: implemented

The **Updates** page collects completed, failed, and interrupted tasks from the existing background agent team. It provides a persistent unread count, quiet mode, review/dismiss controls, and a read-only draft preview on a selected connected display. Results are recorded once; reopening the app does not create duplicate notifications. Reading a draft never deploys or applies it.

Try it after restarting JARVIS:

1. In Tasks, choose a configured, working agent and assign a text-drafting task. For example: draft an outline for a personal portfolio home page, using the information you supply.
2. Continue using Chat. A completed task creates an Updates item and, unless quiet mode is enabled, a short in-app notice.
3. Open Updates, read the draft, and choose a display for its preview. With one monitor attached, the preview uses that monitor.
4. Mark it reviewed or dismiss it. Those actions change review state only.

Chat controls: `show updates`, `any updates`, `quiet mode on`, and `quiet mode off`. Existing explicit delegation also works: `delegate to gemini: Draft a portfolio home page outline based on these details: ...` once that agent's connection is configured.

Background workers currently draft and reason without PC action tools. They do not silently modify a repository or create a working website. Work continues while the desktop app is open; this stage is not an operating-system service, scheduled monitor, or always-on cloud agent. Running tasks still follow the existing shutdown protection.

Verified: 340 tests pass, static checks pass, and the Updates interface and read-only display preview were checked offscreen. Persistence, duplicate prevention, quiet mode, selection stability, and an actual background-thread completion are covered. Physical movement between two monitors still needs a two-monitor hardware check. The included UI screenshot uses an explicitly labeled sample draft, not a real website update.

## Stage 2 — Kokoro speech output

The confirmed engine is [Kokoro](https://github.com/hexgrad/kokoro), whose original [model page](https://huggingface.co/hexgrad/Kokoro-82M) describes an 82-million-parameter text-to-speech model with Apache-licensed weights. It is a speech-output component; understanding speech requires a separate recognizer.

Next, add an optional local Kokoro runtime, voice selection, sentence-level playback, and a Stop speaking control. Test CPU operation on this laptop before adding a GPU profile. Measure speech generation and first-audio latency. Do not claim superiority to paid engines without comparing the actual voice, language, latency, and pronunciation you need. No Kokoro runtime, model weights, microphone access, or audio playback was installed or enabled in Stage 1.

## Stage 3 — conversational voice and visible state

Start with push-to-talk, then speech recognition, silence detection, cancellation, and interruption while JARVIS is speaking. After that, add an optional wake phrase. Animate actual states—listening, thinking, speaking, awaiting a decision—instead of running an animation unrelated to the work. Voice commands must enter the same action router and permission checks as typed commands.

## Stage 4 — tools, proposals, and useful proactive work

Connect the browser session and project workspace first. Prepare a versioned patch or preview against a known website revision. Present the affected files, preview, and validation results before requesting permission to apply it. An approval must refer to that concrete proposal; a generic spoken yes must not authorize an unrelated operation.

Later business plugins can expose read-only sales and follow-up data. Each answer needs a source, retrieval time, business timezone, and explicit sales definitions such as gross/net/refunds. A callback reminder must come from a real recorded request or follow-up record. Add opt-in recurring checks with deduplication, quiet periods, and a bounded interruption policy after the connectors are working.

## Stage 5 — phone and WhatsApp access

Use a separately authenticated remote gateway so access can work when the laptop is asleep. Add a messaging channel first, then optional calling with the correct provider account and permission flow. [Twilio's WhatsApp Business Calling documentation](https://www.twilio.com/docs/voice/whatsapp-business-calling) describes a business calling integration, including permission requirements for outbound calls. A phone number alone does not configure that integration. Availability and costs must be checked at setup time.

No phone number, WhatsApp account, external messaging, calling subscription, publishing service, or sales account has been connected by Stage 1.
