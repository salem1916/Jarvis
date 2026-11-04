# JARVIS: ChatGPT plan access, free APIs, and fast interaction

Research checked 27 October 2026. Prices, model availability, eligibility, and quotas change.
This report separates official provider rules from community experience and from my recommendations.

## What I recommend for your laptop

Use **local deterministic commands** for opening applications and other recognized PC actions;
**ChatGPT plan sign-in** for deeper reasoning using the account you already have;
and **Groq's Free tier** as the first API to test for short, interactive replies.
Keep **Gemini** as another candidate if your project is eligible for its free tier, and
**OpenRouter's free-only router** as an additional option rather than the only engine
behind a long agent workflow. This is my assessment of the documented options, not an
end-to-end latency benchmark on your accounts.

Do not equate a free agent framework, a free chatbot website, a recurring API allowance,
and a temporary API trial. They are different offers.

## Can JARVIS use your ChatGPT subscription and credits?

**Yes, through the documented Sign in with ChatGPT integration, when your account grants
the required access.** OpenAI explicitly documents this for open-source apps and personal
projects that run locally. This is separate from configuring an OpenAI API key. It does
not import your ChatGPT chat history or memories. [Official overview](https://developers.openai.com/siwc/token-sharing-open-source)

There are two distinct choices in JARVIS:

| Connection | What pays for requests | What you provide |
| --- | --- | --- |
| ChatGPT plan | Eligible included ChatGPT plan usage; available ChatGPT credits only under your account's permissions | Browser sign-in and consent |
| OpenAI API | Separate API-platform billing or API credits | An API key |

Plan usage is not a new allowance created for JARVIS. Shared usage limits still apply.
The app links to ChatGPT's Usage settings so you can manage access and review available
controls. JARVIS does not enable credit spending or automatic purchases for you.
[Accounts and sessions](https://developers.openai.com/siwc/token-sharing-open-source/profiles-and-sessions),
[official integration walkthrough](https://developers.openai.com/cookbook/articles/sign-in-with-chatgpt)

The implementation uses browser authorization with PKCE, state and nonce checks, issued
client IDs, signature-verified identity tokens, and refresh-token renewal. Tokens are
stored encrypted for your Windows account. It does not copy another application's
credentials or use private ChatGPT backend endpoints.
[Registration protocol](https://developers.openai.com/siwc/token-sharing-open-source/sign-in)

Account-specific model discovery is important: JARVIS loads the signed-in account's
available models instead of promising a model your plan may not offer. Requests use
the public Responses API with streaming and server-side storage disabled.
[Models and inference](https://developers.openai.com/siwc/token-sharing-open-source/models-and-inference)

## Free-access comparison

| Option | Nature of the allowance | Good use in JARVIS | Material limitation |
| --- | --- | --- | --- |
| Existing eligible ChatGPT plan | Included usage in an existing subscription | Deeper reasoning without setting up API billing | Shared plan limits; eligibility and credit permissions apply |
| Groq | Free API tier; model-specific quotas | First candidate for short replies and lightweight reasoning | Check your actual account Limits page; tokens and requests both matter |
| Gemini Developer API | Free access for eligible projects/models | General reasoning and comparison tests | Account/project eligibility and model quotas vary |
| OpenRouter free-only | Free model routes with account-level request caps | Experimenting with multiple models and backup access | Capacity, model choice, and quotas can interrupt long tasks |
| Cloudflare Workers AI | Recurring 10,000 Neurons/day allocation | Another development option if the first choices do not suit you | Compute units are not a fixed number of chats; some models require paid access |
| Cerebras | One-time promotional credit, not an ongoing free budget | A short speed experiment | Current pricing requires a payment method for $5 credit; expires after 30 days |
| Local Ollama | No hosted inference bill | Offline use on a suitable PC, or a stronger workstation later | RAM/GPU and model size determine speed; small models still have quality limits |
| Hermes | An agent harness, not a separate unlimited model allowance | Explicit agent tasks using its configured provider | The chosen model/provider still determines cost, quality, and limits |

### Groq: the first free API I would test

Groq's official billing documentation distinguishes its Free and paid Developer tiers.
Its model catalog and OpenAI-compatible API make it a straightforward fit for JARVIS.
Start with a short conversational task on an available model such as
`openai/gpt-oss-20b`, then compare answer quality with the larger option available to
your account. This is a test candidate, not a guarantee it is fastest on your network.
[Billing](https://console.groq.com/docs/billing-faqs),
[model catalog](https://console.groq.com/docs/models)

The public limits table currently shows figures such as 30 requests/minute and
1,000/day for the GPT-OSS entries, alongside token limits. The page has plan tabs and
account exceptions: **your account's Limits page is authoritative**, not a fixed number
copied from a tutorial. A long prompt can exhaust a token limit before the request count.
[Rate limits](https://console.groq.com/docs/rate-limits)

### Gemini: a useful second candidate

Google lists free pricing for selected models, but free access is not available to
every project. Quotas vary by model and project and are shown in AI Studio. Moving to
paid billing does not create a free-tier quota. JARVIS supports Google's documented
OpenAI-compatible endpoint, so there is no need for a separate desktop application.
Choose a free-eligible model in your own account rather than assuming every model in
the catalog is free.
[Pricing](https://ai.google.dev/gemini-api/docs/pricing),
[limits](https://ai.google.dev/gemini-api/docs/rate-limits),
[eligibility troubleshooting](https://ai.google.dev/gemini-api/docs/troubleshooting),
[API compatibility](https://ai.google.dev/gemini-api/docs/openai)

### OpenRouter: useful, with a strict free-only choice

The `openrouter/free` router routes among free models. Individual model capacity and
free-model request caps still apply; rotating models does not remove the account's
overall ceiling. OpenRouter's key endpoint exposes the current daily free-model
counter and limit. I would use it for experimentation and occasional backup work,
not assume it can sustain continuous parallel agents.
[Free router](https://openrouter.ai/docs/guides/routing/routers/free-router),
[limits and account counters](https://openrouter.ai/docs/api_reference/limits)

JARVIS's **OpenRouter · free models only** option rejects model IDs other than
`openrouter/free` or IDs ending in `:free`. It does not switch to a paid model when
capacity is unavailable.

### Cloudflare and Cerebras

Cloudflare's daily 10,000-Neuron allocation is recurring. Its pricing page explains
the per-model compute costs and which models require a payment method or paid plan.
It is a credible extra development option, but the allocation is not directly
comparable to 10,000 requests. No dedicated Cloudflare connection was added in this
update. [Workers AI pricing](https://developers.cloudflare.com/workers-ai/platform/pricing/)

Cerebras advertises a one-time $5 promotional credit after adding a valid payment
method. It expires after 30 days; the provider states access pauses when that credit
ends unless you separately buy PayGo credits. This can be useful for a speed trial,
but it is not the best foundation for your goal of recurring free access.
[Current pricing](https://www.cerebras.ai/pricing)

### Hermes and NVIDIA-hosted models

Hermes supports multiple providers, including subscription authentication and custom
local endpoints. Its own provider flow remains available through the Hermes option;
JARVIS's new ChatGPT connection uses a separate official sign-in.
[Hermes quickstart and provider choices](https://hermes-agent.nousresearch.com/docs/getting-started/quickstart)

I would not make a temporary hosted-model promotion the only backend. NVIDIA's AI-Q
documentation explicitly warns of limited availability and 429/503 errors for a
hosted Build endpoint. Treat such endpoints as candidates to test, not a promise of
unlimited reliable free inference.
[NVIDIA hosted-endpoint availability](https://docs.nvidia.com/aiq-blueprint/2.2.0-rc1/customization/swapping-models.html)

## What Reddit and the video material added

I reviewed dated Reddit reports and accessible video material as practical experience,
not as authoritative pricing or benchmark evidence.

- A May 2026 Hermes thread recommends several providers plus local inference rather
  than relying on one free endpoint. Replies also describe slowness and capacity limits.
  [Community discussion](https://www.reddit.com/r/hermesagent/comments/1tqzwl9/how_to_run_hermes_agent_for_free_and_not_hit_rate/)
- An August 2026 user reports exhausting free-model limits after only a few agent
  tasks. This illustrates why the number of user messages is not the number of model
  requests. It does not establish a universal quota.
  [User report](https://www.reddit.com/r/hermesagent/comments/1vgpjjr/free_models_are_useless_or_am_i_doing_something/)
- Damian Malliaros's July 2026 video, *How to Run Hermes Agent Free With OpenRouter*,
  demonstrates free-model setup. I could inspect an indexed summary and transcript
  preview; the direct YouTube page was not retrievable. I did not watch the full video.
  Its free-router advice does not override the provider's published limits.
  [Video](https://www.youtube.com/watch?v=QiVk5g2X-9o),
  [accessible summary and transcript preview](https://glasp.co/youtube/QiVk5g2X-9o)

The engineering lesson is to spend scarce requests on reasoning, keep simple commands
deterministic, shorten context, and assign parallel agents only when their work is
independent enough to justify the additional calls.

## What changed in your app

- A grouped Settings page with light/dark appearance, native switches, account controls,
  provider selection, model loading, and an always-visible Apply action.
- ChatGPT browser sign-in, account switching, model discovery, refresh, sign-out, and
  a link to usage/credit controls. Real account authorization is still your action.
- Groq, Gemini, OpenRouter free-only, OpenAI API, local Ollama, and configured Hermes
  choices. API keys entered in Settings are stored encrypted, not in personal memory.
- A one-request path for ordinary cloud reasoning, without the full tool-schema catalog.
  Text streams into the chat rather than waiting for the complete answer.
- A Stop control with cooperative cancellation. Cancelled partial replies are not saved
  as completed conversation turns. New tool execution is blocked after cancellation,
  including calls arriving through the Hermes bridge.
- Built-in application resolution skips Start Menu traversal. Recognized local commands
  continue to avoid model calls entirely.
- First-text timing in chat telemetry, plus total inference duration.
- Additional worker backends: `plan`, `groq`, `gemini`, and `openrouter_free`.

A stalled network operation can still take up to its read timeout to release. Stop
does not undo an action already completed. Background task cancellation remains queued-job
cancellation; this update's new Stop control is for the main chat.

## Connect and try it

1. Start JARVIS from its project folder using `.venv\Scripts\python.exe -m jarvis.ui`.
2. Open **Settings → ChatGPT account → Continue with ChatGPT**. Review the browser's
   consent and account eligibility. No API key is needed for this choice.
3. Select **ChatGPT plan** under Intelligence, load models, choose one, and Apply.
   Leave **Local only** off when using cloud providers.
4. For the free API test, create a Groq Free-tier account/key through its own console.
   Save the key in **API connections**, choose Groq under Intelligence, load models,
   and Apply. Remain on the provider's Free tier if that is your budget requirement.
5. For an independent agent, try `assign coder to plan`, then
   `delegate to coder: Explain dependency injection with a Java example`.
6. Use `@plan`, `@groq`, `@gemini`, or `@free` to request one connection explicitly.
   The older `@chatgpt` shortcut still means the separate OpenAI API-key connection.

The current ChatGPT plan adapter is for reasoning. Simple local actions still run;
complex PC tool tasks can use an API connection or the configured Hermes bridge.

## Voice: what should happen next

First benchmark 10 real tasks on your laptop after connecting an account: record route,
time to first text, total duration, whether the answer was useful, and any quota error.
Do not compare providers using advertised tokens/second alone; network latency and
prompt size affect responsiveness too.

Then build push-to-talk with local speech recognition, sentence-by-sentence speech
output from the text stream, and interruption that cancels both generation and playback.
Add a wake word after that works reliably. ChatGPT plan usage currently does not support
audio input or the transcription API on this integration route, so speech needs a
separate component. [Preview limitations](https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations)

Live sign-in and account-specific inference cannot be established by mocked tests.
The implementation is tested locally, but eligibility, actual quotas, model access,
and end-to-end provider latency must be checked after you connect your own accounts.

## Verification for this update

270 automated tests pass. Ruff passes; Pyright reports zero errors and warnings.
Desktop checks cover light/dark appearance, saved source/model selection, streamed
text without duplicate replies, and clean shutdown. OAuth tests use signed test
identities and simulated provider responses; no live ChatGPT sign-in or credit
spending was performed. These changes are local to your project.
