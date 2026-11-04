# Contextual search correction

Updated 2 November 2026.

The reported exchange was reproduced from the local conversation record. The original user request contained both the topic and a video request. A later follow-up, `search for a video that i asked for`, reached the literal browser shortcut and opened Google for those exact words. Smart mode changed model routing but never supplied context to that shortcut.

A second defect discarded the appended assistant-behavior and task-context instructions whenever the plain-reasoning adapter removed the desktop's long tool catalog. The adapter now keeps those trusted instructions and personal context while continuing to omit action schemas from ordinary answers.

## Updated behavior

- Fully specified searches stay local and immediate. Explicit video requests use YouTube unless a different supported destination was requested.
- References are resolved before execution. A small read-only understanding step receives earlier user messages and returns a typed search topic, destination, and source-turn references. It cannot request arbitrary tools or launch actions itself.
- A resolved search goal can be reused locally for straightforward follow-ups, including after changing AI modes. An unrelated new topic invalidates blind reuse. Format constraints go through understanding rather than being dropped.
- A missing topic produces one focused question; the answer completes the pending request. Previous duration or language constraints are retained.
- Bad JSON, unsupported destinations, unresolved references, low-confidence plans, missing source IDs, and provider failures do not fall back to a literal search of the unresolved wording.
- The actual topic is included in the acknowledgment. A search opens a results page; it does not claim that a particular video was selected, watched, or verified.
- Fully quoted titles can still be searched literally.
- Understanding respects the selected local/API route. A Hermes intent reader receives no JARVIS action bridge. Browser permissions and existing request limits still apply.

The assistant's general instructions now favor practical help for ordinary lawful informational questions, without treating the mere possibility of risk or scams as grounds for refusing an entire topic. Relevant uncertainty is still stated. Known personal/location context is retained; unsupported country assumptions are discouraged. No provider safety setting was disabled and no content-refusal workaround or automatic model hopping was added.

## Try it

Restart JARVIS. Examples:

1. `How can I learn SQL joins?`
2. `Find a video about that.`
3. `Search for a video in German under 10 minutes.`

Or give a combined request such as `Explain SQL joins and maybe show me a video.` The same mechanism applies to other subjects; the implementation contains no topic-specific income, cooking, or coding search list.

Smart controls AI/model routing. Google and YouTube are search destinations chosen from the request. Changing modes preserves the conversation; it is not a substitute for understanding a contextual reference.

## Validation

497 automated tests pass, with clean Ruff and Pyright checks. New conversation cases cover the exact reported exchange and unrelated topics; explicit searches; stale topics; language/duration constraints; missing-topic answers; quoted titles; malformed plans; local routing; denied permissions; Hermes isolation; and continuing a failed compound request without repeating its completed search.

Live Gemini verification recovered the original income-related topic from the reported follow-up and produced a YouTube search query for `fastest way to make money`. A second related request reused it without another model call, including after changing to Smart mode. A separate ordinary student-income question received practical options instead of the earlier blanket refusal. Another conversation produced the German search `Sauerteigbrot backen kurz` from a sourdough question and a request for a short German video. A separate live intent test retained both parts of the original `fastest way to make money and maybe show me a vd` request: a research question and a video search.

Navigation was captured during these live intent tests to avoid opening extra personal-browser tabs; the real model, context resolution, trusted execution path, and generated search URLs were exercised. Cloud understanding/answer calls still took several seconds. Model quality and availability remain relevant, and uncertain interpretation can still require clarification.
