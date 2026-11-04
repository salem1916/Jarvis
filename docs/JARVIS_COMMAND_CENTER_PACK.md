# JARVIS Command Center Pack

This pack moves JARVIS toward the real assistant experience:

- Hermes is the conversation and planning brain.
- Local trusted tools are the hands for Windows, files, browser tabs, memory,
  and approvals.
- The Chat screen now has a visible Command Center with quick actions.
- The Desktop Note action proves local hands can execute without waiting for
  the model.
- Windows launcher scripts let Salem create a desktop shortcut and start JARVIS
  without typing the Python module command every time.

## New chat commands

```text
command center
```

```text
jarvis status
```

```text
daily brief
```

```text
what can you do
```

```text
assistant plan
```

```text
create a file in my desktop and say hi in there
```

## Launcher scripts

Create the shortcut once:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\create_desktop_shortcut.ps1
```

After that, open JARVIS from the desktop shortcut.
