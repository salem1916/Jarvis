# Voice, browser and screen actions

This upgrade addresses three connected gaps: holding a button for every message,
opening only the first part of a request, and reasoning without observing the app
the user is looking at. It adds general tools and an observation loop, not topic
rules for stocks, sports, weather or business figures.

## Use it

Restart Jarvis after updating.

**Voice:** enable Voice replies, then open Voice settings → Voice mode.

- **Click to talk** is the default. Click Talk, speak, then click Send.
- **Hands-free · pause to send:** choose this mode and click Listen once. Speak,
  then pause for roughly 0.6 seconds. Jarvis sends the utterance, responds, and
  keeps listening with **Interrupt by speaking · speaker echo cancellation** on.
  Stop voice ends the session. Speaking stops the old audio and pauses work so
  your next instruction can redirect it in the same conversation.
- **Hold to talk** remains optional. Press Hold while speaking and release.

Say **wait** to hold a task or **continue** to resume it without replaying actions.
The microphone and Kokoro playback share a local browser audio engine with echo
cancellation. Physical speaker/microphone performance still depends on devices,
volume and room acoustics. Turn off the interruption option to use the earlier
non-overlapping mode. Wake words and partial-transcript reasoning are not added.

**Screen:** turn on **Allow Jarvis to see my screen**. There is no app picker.
Jarvis follows the active app and remembers it when you return to Jarvis to talk.
During a requested task, a vision-capable model receives a fresh image of that
app; the planner can also request the active display. The ChatGPT plan connection
now accepts images, and its complete screen/action flow has been tested live.
Known text-only models, including Groq GPT-OSS, use Windows accessibility controls
instead of receiving unsupported image input. They can read exposed text and
operate named controls, but cannot inspect image-only or canvas content.
Screenshots stay out of saved chat history and are not saved to disk. Image
requests do not automatically fail over to other providers.

Ask for the full task, or follow up using the existing conversation. Screen mode
can inspect the active window and use named visible controls, literal typing,
window actions and a fixed set of keyboard navigation actions. A browser address
bar can be selected and searched through those tools. Each operation still goes
through Jarvis's existing permission gate. Screen mode is off at startup and
does not grant extra permissions. Unchecking it stops the current screen task.

Use Permissions for the capabilities you want to allow: inspect UI, control
windows, click controls, type text, keyboard actions and opening websites/apps.
They are independent. An actual denial now names the missing capability. Windows
microphone access is a separate OS setting.

The planner observes after each action and has a twelve-action limit. It can
request clarification or report a concrete blocker. It has no arbitrary code,
shell or coordinate-clicking tool. Some canvas interfaces, inaccessible controls,
protected windows, minimized apps and ambiguous windows remain unsupported.
Do not assume a business account or dashboard is connected just because a browser
is open: Jarvis must observe the real source before reporting account figures.
Before accepting a successful finish, Jarvis checks the original request against
actual operations and the current observation. A skipped requested action or
missing answer goes back to the bounded planner, without replaying completed
actions. This final check adds a model round trip for screen tasks; simple local
commands remain independent of it.

**Copy:** the main response and progress text are selectable. Use Copy reply for
the latest reply and details, or Copy conversation for the whole visible chat.
Buttons, selected-text Ctrl+C and the response context menu use verified Windows
Unicode copying. The button shows **Copied ✓**, or a concrete clipboard error.

**Relative navigation:** first/second-link and Back requests stay with the current
page. In the managed browser they use its fresh observed links and real history,
and finish after one navigation. Search-result ordering uses heading/link
structure, separate from navigation links; ambiguous ordering asks for a choice.
Desktop references cannot launch another app or perform another search. Back in
the active desktop app uses its standard keyboard action without cloud inference.
Search query generation is unchanged by these follow-up changes.

## Browser versus screen

An ordinary one-step open/search takes the fast local route even while screen
access is enabled; it does not need a working AI connection. A compound request such as opening a website and inspecting a topic
now stays in the visible managed-browser workflow. It no longer rewrites the
second part into a separate text-only research task. General search results can
come from the existing structured web search when a search page is blocked; the
browser can then navigate to a relevant real result. It does not bypass human
checks or claim the user's regular Chrome tab was inspected.

The managed browser is a separate Jarvis browser session. Screen access operates
the actual active desktop window, including an existing Chrome window. This
distinction explains why opening a URL alone did not previously give Jarvis eyes
on the user's browser.

## How the implementation works

1. Qt owns user controls and click/hold audio. Interruptible hands-free capture
   and playback share a local Chromium audio engine with echo cancellation.
   Captured PCM streams to the separate local speech process.
2. Pipecat Silero detects the start and end of an utterance, with 0.4 s of pre-roll,
   a roughly 0.6 s end pause and a 20-second utterance cap. Whisper transcribes it.
3. Voice onset stops old playback and pauses work at a cooperative check. The
   resulting text enters the same conversation and permission checks as typing.
   A new instruction redirects the current turn; wait/continue holds/resumes it.
4. A screen task sends a fresh active-window PNG (or accessibility text for a
   known text-only model) plus the actual tool schemas,
   permission decisions, conversation and real action results to the selected model.
   Windows capture uses the foreground pixels, or the active app's own rendered
   window when an approval prompt covers it. A failed capture is reported.
5. The model selects one registered tool; Jarvis validates and executes it, then
   observes again. Screen text is evidence, not authority to change the goal.
6. Brief progress can be spoken while actions continue. Final structured replies
   use Kokoro. Old audio/transcripts are discarded after cancellation.

Image formats follow [OpenAI image input documentation](https://developers.openai.com/api/docs/guides/images-vision?api-mode=chat),
[Google image understanding](https://aistudio.google.com/docs/image-understanding),
and [Ollama vision](https://docs.ollama.com/capabilities/vision). Text-only models
cannot become vision models merely by enabling the screen option.

## Verification and practical limits

The regression suite covers unrelated browser goals, full-task routing,
first-result follow-ups, image attachment formats, opt-in and actual permission
denials, observation after actions, unsupported actions, copying, click-to-talk,
hands-free resume gating and bounded speech segmentation.

Live acceptance checks use a separate generated Windows test app, real saved
provider connections, Whisper recognition, the real ChatPage worker, real named
control clicks and Kokoro speech generation. They check microphone-status replies,
assistant identity, opening Google and reporting the exact reference/status after
clicking the test app. They assert that the requested value appears in speech as
well as details. The fixture restricts capture and clicks to its test window and
does not record the physical microphone or play through physical speakers.
The local voice smoke test also checks hands-free pause detection and interruption.
These checks cannot guarantee every real task; model quality, accessible controls,
provider availability and physical audio conditions still matter.

First manual check: activate an ordinary browser page and ask Jarvis to read its
heading. Then ask it to open a named visible link and confirm the new page. Test
an unrelated task next. Copy conversation if anything goes wrong; it includes
the context needed to investigate without guessing from a cropped screenshot.

## Connection and conversation reliability

The chat header shows the selected AI and model. Saving an API key does not
automatically replace the active connection: select the provider/model in Settings
and Apply. ChatGPT plan usage and an API key are separate connections.

Jarvis supplies current identity, voice/text origin, available tools and permission
facts with conversation requests. Historical incorrect claims about having no app
access do not override those facts. No memory prompt is required to enable tools.

ChatGPT streaming ends as soon as its completion event arrives. Groq screen
tasks use native function calls and receive real tool results through the matching
call IDs. Trusted Jarvis code validates each requested operation and checks its
permission. Groq GPT-OSS research/review requests use a strict JSON envelope.
Specific provider format rejections can regenerate a proposal
using the shared two-retry budget; completed PC actions are not replayed. Extra
attempts still pass the API assistant's approval and daily-cap checks. This follows
[Groq's tool protocol](https://console.groq.com/docs/tool-use/overview) and
[structured-output contract](https://console.groq.com/docs/structured-outputs).
Provider failures show their concrete reason instead of the same generic failure.
