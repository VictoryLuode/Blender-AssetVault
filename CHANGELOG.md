## 0.1.0

First public version: node groups only.

- Right-click a Group node in the node editor, "Save to Asset Library" writes the
  group into the target library as its own `.blend`, catalogued under `Group`.
- "Update Library Copy" appears for a group that is already in the library and
  replaces that copy with the version in the current file.
- Saving changes nothing in the current file: the asset mark and catalog exist only
  for the duration of the write.
- A same-named file the add-on did not write is never overwritten (checked by
  reading the file, not by trusting its name).
- Target library follows the Asset Browser's selection, with a library in the
  add-on preferences as the fallback.
- Nested groups travel with the group that uses them.
- Every command also lives in a single menu, opened with a shortcut (`T` by
  default) in any node editor.  The key is an add-on preference: **Asset Vault
  Settings ▸ Set** captures the next key you press, or the menu's `Shortcut: …`
  entry starts the same capture, and the binding is rebuilt from that value.
- **Hide from the Add Menu** / **Show in the Add Menu** keeps a library copy in the
  Asset Browser while taking it out of the node Add menus (and the Add Modifier
  menu, which filters the same way).  A save or update does not undo a deliberate
  hide.
- The right-click entries stay where they are, and can be turned off in the
  preferences for a strictly one-menu add-on.
- The hidden tree-type field the Add menu filters on is written explicitly on save,
  and the visibility switch rewrites a library file in place — parking a same-named
  group held by the session for the duration, so the name inside the file cannot
  drift.
