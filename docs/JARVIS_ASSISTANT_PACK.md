# JARVIS Assistant Pack

This pack moves JARVIS from a simple chat-and-tools app toward a command-center assistant.

## What changed now

- Fast command-center replies:
  - `jarvis status`
  - `daily brief`
  - `what can you do`
  - `assistant plan`
- Action Memory:
  - remembers trusted open actions
  - supports `what did you open`
  - supports `close the last thing you opened`
  - supports `close facebook` when JARVIS remembers opening Facebook
  - persists action memory in real desktop mode
- Browser safety:
  - website follow-ups close the tab with trusted `close_tab`
  - apps still close through trusted `close_window`

## Product direction from the reference videos

JARVIS should become a desktop AI command center, not only a prompt box.

The intended modules are:

1. Today: briefing, calendar, reminders, important alerts.
2. Tasks: workflows, routines, background jobs, and progress.
3. Memory: what JARVIS knows, opened, changed, or is tracking.
4. Approvals: emails, calls, messages, file writes, and risky actions wait for Salem.
5. Connectors: Gmail, Google Calendar, browser, local files, phone/calls.
6. Voice: configurable local/cloud voices and languages.
7. Commercial layer: rename, installer, privacy, licensing, onboarding.

## Safety rule

JARVIS should prepare and propose high-impact actions, but Salem approves before sending messages, making calls, deleting data, or contacting people.
