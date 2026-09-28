# Asset Vault

Save a node group from the file you are working in straight into an asset library — and
keep the library copy up to date — without leaving the node editor.

Blender can already store assets in a library, but the route goes through the Asset
Browser: mark, pick a library, pick a catalog, confirm, and repeat all of it when the
group changes.  Asset Vault keeps the two steps that matter and puts them where the group
is: the node editor's right-click menu.

| | |
|---|---|
| Version | 0.1.0 |
| Blender | 4.2 LTS or newer (tested on 4.2.23, 4.5.14, 5.2.2) |
| Scope | Node groups (geometry, shader, compositor) |

## How it goes

1. Right-click a **Group** node in the node editor.
2. **Save to Asset Library** — the group is written into the target library as its own
   `.blend` file, filed under the `Group` catalog.
3. It is now in the library, so it appears in the node editor's Add menu
   (**Shift+A ▸ Group**) and in the Asset Browser — in this file and every other one.
4. Change the group, right-click it again → **Update Library Copy** replaces the copy in
   the library.

The second entry only appears once the group is actually in the library.

## What it deliberately does not do

- **No 3D assets yet** — objects, materials and collections are a later step; this is the
  node group pass.
- **No asset housekeeping** — renaming, moving, tagging or deleting assets already in a
  library is not its job.
- **No guessing where things go.** No Asset Browser open and no library chosen in the
  preferences: it says so instead of dropping the file somewhere.
- **Never overwrites a file it did not write.** If a same-named file holds something else,
  the save is refused; the check reads the file's contents, not its name.
- **Saving does not touch your file.** The asset mark and the catalog exist only for the
  duration of the write.

## Install

```bash
./install.sh                 # newest Blender on this machine
./install.sh "<...>/scripts/addons"   # or a specific one
```

Then enable **Asset Vault** in `Edit ▸ Preferences ▸ Add-ons`.

## Preferences

| Setting | What it does |
|---|---|
| Follow the Asset Browser | Save into the library currently selected in the Asset Browser; the library below is used when no Asset Browser is open |
| Library | Where groups are written when the Asset Browser is not the answer. Defaults to the first configured library |
| Catalog | Defaults to `Group`. That name is the catalog the node editor's Add menu reads, so moving the groups out of it also moves them out of Shift+A |

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

## Tests

```bash
tests/run_tests.sh                    # newest Blender
tests/run_tests.sh /path/to/blender.exe
```

Headless, with a throwaway Blender configuration: the real preferences, the real add-ons
folder and the real asset libraries are never touched.  69 checks, all green on Blender
4.2.23, 4.5.14 and 5.2.2.
