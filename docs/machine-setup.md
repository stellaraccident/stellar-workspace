# Machine setup

## Windows Terminal setup

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
