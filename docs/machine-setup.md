# Machine setup

## Codex on the remote SSH host

### Preserve the sandbox PATH

Login-shell startup files can replace the sandbox's prepared `PATH`, causing
Codex shell commands to miss workspace tools or use a system Python instead of
the workspace venv. Set this at the top level of `~/.codex/config.toml` on the
remote host, before any table headers such as `[tui]`:

```toml
allow_login_shell = false
```

This makes shell commands default to non-login shells and rejects explicit
`login: true` requests. It avoids login-shell startup files resetting the
sandbox's prepared `PATH`, including the workspace `.venv/bin` entry.

For isolated agent profiles that use a separate `CODEX_HOME`, put the setting
in that profile's `config.toml` too; host configuration is not shared there.

Reference: [Official OpenAI configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference).

## Windows Terminal setup

### Copy and paste across tmux sessions

When using the Codex TUI over SSH inside tmux, use Windows Terminal's clipboard
shortcuts to copy and paste between sessions:

1. Hold **Shift** while dragging the mouse to select text. This keeps selection
   in Windows Terminal instead of sending the mouse events to Codex or tmux.
2. Press **Ctrl+Shift+C** to copy to the Windows clipboard.
3. Switch to the destination tmux session.
4. Press **Ctrl+Shift+V** to paste from the Windows clipboard.

Reference: [Windows Terminal selection](https://learn.microsoft.com/en-us/windows/terminal/selection)
and [clipboard actions](https://learn.microsoft.com/en-us/windows/terminal/customize-settings/actions#clipboard-integration-commands).

### Multiline input in Codex

If Shift+Enter and Ctrl+Enter submit the prompt instead of inserting a newline,
map both shortcuts to the same input as Ctrl+J. This preserves plain Enter for
submission and works in the tested Codex session through SSH and tmux without
changing Codex key bindings or tmux settings.

First, press Ctrl+J in the Codex composer and confirm that it inserts a newline.
Then configure Windows Terminal:

1. Click the **▼ beside the tabs**, then **Settings**.
2. Click **Open JSON file** at the bottom left.
3. Find the top-level `"actions"` and `"keybindings"` arrays. Merge the entries
   below into those arrays, preserving existing actions, bindings, and settings.
   Replace any existing bindings for Shift+Enter or Ctrl+Enter to avoid duplicates.
4. Save with **Ctrl+S**, then test both shortcuts in Codex.

The relevant settings are:

```json
{
  "actions": [
    {
      "command": {
        "action": "sendInput",
        "input": "\n"
      },
      "id": "User.sendInput.DFCDAF06"
    }
  ],
  "keybindings": [
    {
      "id": "User.sendInput.DFCDAF06",
      "keys": "shift+enter"
    },
    {
      "id": "User.sendInput.DFCDAF06",
      "keys": "ctrl+enter"
    }
  ]
}
```

This is a fragment to merge, not a replacement for the whole settings file.
Both bindings reference the same action ID. Windows Terminal may generate a
different ID when saving; the action and its bindings must use the same value.
It may also move inline commands from key bindings into the `"actions"` array.

`"\n"` and `"\u000a"` encode the same line-feed byte, equivalent to Ctrl+J.
Windows Terminal may normalize `"\u000a"` to `"\n"` when saving.

Expected behavior, verified in the affected session:

| Shortcut | Result in the Codex composer |
| --- | --- |
| Enter | Submit the prompt |
| Shift+Enter | Insert a newline |
| Ctrl+Enter | Insert a newline |
| Ctrl+J | Insert a newline |

These are Windows Terminal shortcuts and apply to other applications running
in it as well. To undo the setup, remove the two key bindings and remove the
action if no other bindings reference it.

Reference: [Windows Terminal sendInput action](https://learn.microsoft.com/en-us/windows/terminal/customize-settings/actions#send-input).
