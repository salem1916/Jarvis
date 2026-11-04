# JARVIS API assistant and product plan

The new API assistant researches supported providers, prepares connection proposals, requires your approval, and verifies a selected model before enabling it. It is implemented in the desktop app; it is not a background subscription-purchasing service.

## Start using it

1. Launch JARVIS and open **API assistant**.
2. Turn on **Manage API connections with approvals** and save the policy. Unapproved default cloud connections return to local inference. Your separate personal ChatGPT connection can remain selected outside product mode.
3. Choose **Research current offers**. Read the selected provider's official documentation and terms. The assistant checks Groq, Gemini, OpenRouter, xAI/Grok, and OpenAI API documentation. Groq, Gemini, and verified OpenRouter free routes support managed activation. xAI and OpenAI API remain informational under this free-provider policy.
4. Choose **Review & approve connection**. Confirm your account/model's free-tier status and the terms for your intended use. This approves setup, not inference yet.
5. Open **Set up approved account**. Sign in or register yourself, create a key, and paste it into **Save key securely**. Windows encrypts saved keys for your user account. JARVIS does not create accounts, accept provider contracts, enter payment details, or purchase credits.
6. Choose **Load account models**, select an available model, and **Test connection & enable model**. This verifies the model catalog with your key; it does not run a paid test prompt. The next assigned inference uses the selected connection and its quota.
7. Optionally allow an approved provider to receive fallback work, then enable the global fallback switch. Existing workers still need an approved exact model. Local PC commands continue through the fast local command path.

Approvals last seven days and pause if the reviewed documentation changes. Changing between personal and product scope requires renewed approval. Replacing an active account key also requires approval. Turning management on does not automatically approve any provider. Use **Revoke selected** to stop new managed requests.

## What is automatic

- Official documentation refreshes approximately daily while the app is open, management and automatic review are enabled, and Local-only mode is off. Nothing runs after the app closes.
- OpenRouter's live catalog is checked for explicit zero pricing, including additional advertised price fields. Individual model IDs must end in `:free`; the `openrouter/free` router is also supported. Catalog changes do not silently switch your selected model.
- A per-provider daily request allowance is shared by chat and workers. Failed attempts and tool follow-up requests count. Limits use UTC days and are enforced within the running JARVIS process. Multiple simultaneous app instances are not a supported shared-budget system.
- Failed connections cool down. Optional failover tries only approved fallback connections, then the configured local model. It does not use your personal ChatGPT plan as a fallback. It does not retry tool actions or mix another provider into a partly streamed reply.
- Prompts and relevant assistant memory go only to the selected or explicitly permitted fallback backend. Public research requests carry no API credentials. Downloaded pages are treated as evidence; JARVIS never executes integration code from them.

## Limits that matter

The assistant manages existing reviewed adapters. It cannot integrate every new API format automatically. A new provider needs a reviewed adapter, tests, and a release. Researching official sources is useful; automatically installing website-provided code is not part of this feature.

Groq and Gemini free access depends on your account, selected model, eligibility, quota, and current provider terms. JARVIS cannot independently verify their account billing tier. Confirm free access in the provider console and leave billing disabled if you want no paid usage. Its request allowance is not a provider-side spending limit and does not protect against later billing changes in your provider account. Free quotas cannot guarantee uptime, capacity, or unlimited commercial usage.

Hermes is an agent runtime, not a free API subscription. It still needs a model backend. Its separately configured cloud path is blocked while managed API policy is enabled, because this version cannot enforce that external runtime's account and billing configuration. Use an approved direct API or local inference for managed work.

## A practical product direction

Start with a downloadable Windows product: local app commands, local memory, optional local inference, and customer-owned cloud connections. Package no developer keys, personal tokens, account sessions, or private memory. **Product preview** excludes personal ChatGPT plan access and ignores developer environment keys; users must supply their own encrypted connections and approve their intended commercial use. This preview is a runtime boundary, not a commercial license or a finished distribution system.

Your personal ChatGPT plan remains a separate option for your own use. OpenAI's current Sign in with ChatGPT documentation covers open-source and locally hosted integrations and directs paid or remotely hosted apps to a separate access process. Do not distribute your personal session as a shared customer backend.

Before selling, prioritize a Windows installer and secure update process, privacy documentation and data deletion, customer onboarding, usage visibility, and measured reliability/latency. Add voice after measuring local command latency and cloud first-text latency. For a hosted service later, use an explicitly funded provider agreement, per-customer authentication, server-side usage accounting, and enforced budgets. Free tiers can supplement that service, not underwrite an unlimited promise.

## Verification

On 31 October 2026, live read-only research fetched all five official documentation sources successfully and found 14 eligible zero-price OpenRouter catalog models. This is a snapshot, not a guaranteed future offer. The full suite passed **296 tests**, including approval expiry, scope and key changes, concurrent request allowances, revoked/free-model removal, fallback, and product mode. Static checks and desktop visual checks were also performed. No account registration, API inference, subscription purchase, or credit spending was performed during verification.

## Official sources

- [Groq billing and free tier](https://console.groq.com/docs/billing-faqs)
- [Gemini API billing](https://ai.google.dev/gemini-api/docs/billing) and [terms](https://ai.google.dev/gemini-api/terms)
- [OpenRouter free router](https://openrouter.ai/docs/guides/routing/routers/free-router) and [public model catalog](https://openrouter.ai/api/v1/models)
- [xAI API billing](https://docs.x.ai/console/billing)
- [OpenAI Sign in with ChatGPT scope](https://developers.openai.com/siwc/token-sharing-open-source)
