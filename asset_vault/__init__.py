"""Asset Vault - put node groups from this file into an asset library, and keep them updated.

Blender can already store assets in a library, but the route goes through the
Asset Browser: mark, pick a library, pick a catalog, confirm, and repeat the
whole thing when the group changes.  Asset Vault keeps the two steps that
actually matter and puts them where the group is:

    right-click a Group node  ->  Save to Asset Library
    (edit the group)          ->  right-click  ->  Update Library Copy

The group is written as one .blend file inside the library, catalogued under
"Group", which is the catalog name the node editor's Add menu reads - so a saved
group is immediately available from Shift+A > Group, in every file.

Nothing about the current file is changed by a save: the node group is marked as
an asset only for the duration of the write.
"""
from __future__ import annotations

import bpy

__version__ = "0.1.0"

# Blender reads bl_info with ast.literal_eval() (5.x: scripts/modules/addon_utils.py),
# so it has to stay a plain literal - a computed value makes the add-on invisible in
# Preferences with no other symptom.  Keep the version here, in __version__ and in the
# top entry of CHANGELOG.md in step; tests/test_asset_vault.py checks all three.
bl_info = {
    "name": "Asset Vault",
    "author": "victoryluode",
    "version": (0, 1, 0),
    "blender": (4, 2, 0),
    "location": "Node editor > right-click a Group node",
    "description": "Save and update node groups in an asset library without leaving the node editor",
    "category": "Asset Management",
}

from . import library, operators, props, ui  # noqa: E402,F401


def register():
    props.register()
    operators.register()
    ui.register()


def unregister():
    ui.unregister()
    operators.unregister()
    props.unregister()
