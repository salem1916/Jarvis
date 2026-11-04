# Assistant interface

This is a presentation update. User-reported HTTP 400 failures and inconsistent
browser behavior remain open reliability issues. Local UI tests do not establish
that those workflows work with the selected live provider.

## November 3 polish

Controls now uses a separate scrollable dialog with Actions, Voice, Screen and
Appearance tabs. Voice settings are embedded in that dialog. Device names no
longer force controls outside the viewport. Tasks has collapsible agent setup;
Tasks and Updates scroll instead of compressing tables into their result panes.
API assistant uses shorter controls; section spacing, wrapped labels, table rows,
contrast and scrollbars are consistent across the workspace.

The desktop companion is a compact orb and caption pill. It expands to microphone,
screen, stop and open controls; its content scrolls on smaller screens. Captions,
background dots and reduced motion are remembered locally. Speaking has a visible
pulse between buffered audio samples; this visual pulse is not a microphone meter.
Hidden/reduced-motion graphics stop their animation timers.

Explicit literal requests such as “Open Facebook in it” now use a zero-model
same-tab route. A browser is identified by its actual process before local input;
browser, keyboard and text permissions still apply. This route navigates a known
website; it does not infer an unknown link or claim to read the destination page.
Other complex screen workflows and provider failures remain separate work.

Verified with 605 software tests and an isolated native Chromium window on a
loopback page: one tab before and after, correct destination, no cloud model call,
no microphone or screenshot capture. All eight sections were rendered at 900×600
logical pixels. The companion remained visible when the main window minimized and
restored it correctly. A delayed provider-review timer was made cancellable so
closing the UI cannot run that review against a closed memory database.

## The interface

The main page centers a native animated orb and the current response. Conversation
opens the full text history; Show details keeps provider errors and tool results
available. Copy reply and Copy conversation retain their existing clipboard path.
Controls contains the existing command center, screen permission and reduced
animation option. The selected AI remains visible above the assistant.

The orb uses pastel blue at rest, mint while listening, lilac while thinking and
rose while speaking. Approval, paused/stopped and error states have distinct text
labels as well as colors. Native painting runs only while visible; reduced motion
stops the animation. Captions display actual streamed response text and queued
spoken phrases. They are not word-timed karaoke captions.

## Desktop companion

Desktop orb shows a movable companion near the bottom-right of the desktop. It
remains a separate window when the main app is minimized. Click to expand it,
drag its background to move it, and use Open Jarvis to return to the main page.
It runs only while Jarvis is running; no separate startup service is installed.

Opening the panel does not enable microphone or screen access. Start listening
uses the existing local voice engine after an explicit click. If its models are
loading, clicking again cancels the pending microphone start. Screen off opens a
local permission explanation; Allow screen access enables the existing screen
session. Screen access on means permission for requested tasks, not continuous
background screen streaming. Stop task and voice uses the existing cancellation
and microphone-stop path.

## Verification scope

The complete regression suite passed 592 tests during this update. New checks
cover real frame changes, reduced-motion behavior, microphone/screen default-off
state, screen approval, cancelled pending voice startup, companion recall and
failed-request visibility. The main page, companion and state colors were rendered
locally and visually inspected. No cloud-model test requests were made for this
presentation pass. A complete live-provider usability pass is still required.
An isolated native Windows shell check also passed: the companion remained
visible while the main window was minimized, Open Jarvis restored the window,
and no voice process or screen capture started.

Local preview: `scripts/preview_assistant_ui.py --output <folder>`. It renders the
actual native widgets using an in-memory application, with no microphone, screen
capture or model calls. The preview is labeled as a design preview.
