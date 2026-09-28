# Asset Vault

Save a node group from the file you are working in straight into an asset library — and
keep the library copy up to date — without leaving the node editor.  Everything the add-on
can do is on one menu, on one key.

Blender can already store assets in a library, but the route goes through the Asset
Browser: mark, pick a library, pick a catalog, confirm, and repeat all of it when the
group changes.  Asset Vault keeps the steps that matter and puts them where the group is:
one key in the node editor, and the group's own right-click menu.

| | |
|---|---|
| Version | 0.1.0 |
| Blender | 4.2 LTS or newer (tested on 4.2.23, 4.5.14, 5.2.2) |
| Scope | Node groups (geometry, shader, compositor) |

## How it goes

1. Select a **Group** node in the node editor and press **T** — the Asset Vault menu.
2. **Save to Asset Library** — the group is written into the target library as its own
   `.blend` file, filed under the `Group` catalog.
3. It is now in the library, so it appears in the node editor's Add menu
   (**Shift+A ▸ Group**) and in the Asset Browser — in this file and every other one.
4. Change the group, press **T** again → **Update Library Copy** replaces the copy in
   the library.

The same two commands are on the node editor's right-click menu, where the group is;
that half can be turned off in the preferences.  *Update* only shows up once the group is
actually in the library.

## Keeping an asset out of the Add menu

An asset in a library is normally offered to the node Add menus as well as the Asset
Browser.  The menu's **Hide from the Add Menu** takes it out of the menus and leaves it in
the browser, where it can still be dragged in; **Show in the Add Menu** puts it back.

Blender has no supported switch for this.  It filters the Add menu (and the Add Modifier
menu) on a hidden tree-type field on the asset metadata — `build_catalog_tree()` in
`space_node/add_menu_assets.cc` — and an asset without that field is simply skipped.
Asset Vault writes the field on save, and the switch adds or removes it, so nothing else
about the asset changes.  Two consequences worth knowing: re-marking the asset elsewhere
can put the field back, and a future Blender may replace this mechanism.

## What it deliberately does not do

- **No 3D assets yet** — objects, materials and collections are a later step; this is the
  node group pass.
- **No asset housekeeping** — renaming, moving, tagging or deleting assets already in a
  library is not its job.  (The Add menu visibility switch is the one exception: it is
  about the group this add-on wrote.)
- **No guessing where things go.** No Asset Browser open and no library chosen in the
  preferences: it says so instead of dropping the file somewhere.
- **Never overwrites a file it did not write.** If a same-named file holds something else,
  the save is refused; the check reads the file's contents, not its name.
- **Saving does not touch your file.** The asset mark and the catalog exist only for the
  duration of the write.

## Install

The add-on's folder goes into Blender's user `scripts/addons`; the installer works out
which one, or takes the path.  On Windows, PowerShell is enough — no bash, no git:

```powershell
.\install.ps1                 # newest Blender on this machine
.\install.ps1 "<...>\scripts\addons"   # or a specific one
```

git-bash / MSYS / WSL:

```bash
./install.sh                  # newest Blender on this machine
./install.sh "<...>/scripts/addons"    # or a specific one
```

If Windows refuses to run the script:
`powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1`

Then enable **Asset Vault** in `Edit ▸ Preferences ▸ Add-ons`.

## Preferences

| Setting | What it does |
|---|---|
| Follow the Asset Browser | Save into the library currently selected in the Asset Browser; the library below is used when no Asset Browser is open |
| Library | Where groups are written when the Asset Browser is not the answer. Defaults to the first configured library |
| Catalog | Defaults to `Group`. That name is the catalog the node editor's Add menu reads, so moving the groups out of it also moves them out of Shift+A |
| Shortcut | The key that opens the menu in any node editor. `Set` captures the next key you press (Esc cancels, Delete clears), the arrow resets it to `T` |
| Also in the node right-click menu | Keep **Save** and **Update** on the node editor's own context menu; clear it for a strictly one-menu add-on |

## What a saved asset looks like on disk

One group per file:

```
<library>/
├── blender_assets.cats.txt      # the `Group` catalog is added here on the first save
├── My Scatter Group.blend       # the saved group (+ any groups it nests inside)
└── ...
```

Save and update are the same write, which is what keeps the model predictable: there is
exactly one copy in the library, and it is always the last one saved.
