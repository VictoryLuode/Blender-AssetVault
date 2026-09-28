## 0.1.0

First working version: node groups only.

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
