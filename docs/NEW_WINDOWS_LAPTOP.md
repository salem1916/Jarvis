# Set up Jarvis on another Windows laptop

Follow the [README setup](../README.md#run) to clone `experiment/grounded-browser-planner`
and create the JARVIS shortcut. Open the cloned project folder in your editor when you
want to develop Jarvis. Commit and push changes from one laptop before pulling them on
the other. Use `git pull --ff-only` from the project folder to bring down updates.

## Choose a model

- **Cloud.** Reconnect your provider or sign in again through Jarvis Settings.
- **Ollama.** Install [Ollama for Windows](https://ollama.com/download/windows), launch
  it, then run `ollama pull qwen3.5:4b` in a new terminal for the local model configured
  by default. In Jarvis, select Ollama. You can leave the model download until you want
  to use local reasoning.
- **Hermes.** Follow the [native Windows installer](https://hermes-agent.nousresearch.com/docs/user-guide/windows-native).
  Run `hermes setup` in a new terminal and configure its model provider. Then select
  Hermes in Jarvis. Hermes needs a configured cloud or local model. Jarvis can launch
  the Hermes CLI when selected. If you separately use a gateway, set `JARVIS_HERMES_GATEWAY_URL`
  and `JARVIS_HERMES_GATEWAY_KEY` on the new machine as needed.

## Move your personal memory if you want it

GitHub carries the code and setup instructions. Provider sign-ins, local models,
and your personal memory live on the machine. Windows protects Jarvis's saved keys
with DPAPI, so reconnect providers on the new laptop.

To move Jarvis memory privately, close Jarvis on both laptops. On the old laptop,
type `%APPDATA%\Jarvis` in the File Explorer address bar and copy
`personal_memory.sqlite3` to the matching location on the newer laptop. If the new
laptop already has memory, keep a separate copy of that file before replacing it.
Keep the database out of Git. Select your new microphone and speakers in Jarvis
and review permissions for folders on the new laptop.
