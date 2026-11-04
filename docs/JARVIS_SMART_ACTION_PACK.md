# JARVIS Smart Action Pack

This pack improves the part that made JARVIS feel slow and useless in chat:
trusted local actions.

## What changed

- `create a file in my desktop and say hi in there` now routes directly to
  the trusted `write_file` tool.
- Simple file writes no longer wait for cloud chat reasoning.
- If Desktop is not approved as a filesystem scope, JARVIS says that directly
  instead of falling through to a vague AI answer.
- Normal chat stays on Hermes. Local deterministic tools are for actions,
  not for replacing the talking brain.

## API decision

Do not buy or add more APIs yet.

The current bottleneck is not intelligence. It is reliability:

1. deterministic local actions
2. filesystem permissions and scopes
3. app/window/browser control
4. Hermes Gateway startup/reliability

After those are solid, add one hosted model provider for speed and quality.
OpenRouter is the best first commercial-style choice because it gives access
to many models from one API key. Groq is good later for very fast small replies.

## Commands to test

Try these in the JARVIS chat:

```text
yo
```

```text
create a file in my desktop and say hi in there
```

```text
jarvis status
```

```text
what can you do
```

If the desktop file command says the path is outside approved scopes, open the
Permissions page and add:

```text
C:\Users\salem\Desktop
```
