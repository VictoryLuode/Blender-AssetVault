"""The one entry point: every command the add-on has, in one menu.

The right-click menu puts the two group commands where the group is, which is
useful; this menu is the other half - one key, one list, and everything the
add-on can do is on it.  It is a plain function (`draw_menu`) wrapped by a Menu
class, so the tests can drive it with a recording layout exactly like the
right-click menu is driven.

Nothing here decides anything on its own: the menu reads the same helpers the
commands do, and shows an item only when it would work.
"""
from __future__ import annotations

import bpy

from . import keymap, library, operators, props


def draw_menu(layout, context):
    """The whole add-on, as a list."""
    prefs = props.get_preferences(context)
    tree = operators.active_group_tree(context)
    target = library.target_library(context, prefs)

    copy_file = None
    if tree is not None and target is not None:
        copy_file = library.find_copy(target[1], tree.name)

    row = layout.row()
    row.enabled = tree is not None
    operator = row.operator(
        "asset_vault.save_group", text="Save to Asset Library", icon='FILE_TICK'
    )
    operator.group_name = tree.name if tree is not None else ""

    if copy_file is None:
        layout.separator()
        layout.label(
            text="Select a Group node to save it" if tree is None else "Not in the library yet",
            icon='INFO',
        )
    else:
        layout.operator(
            "asset_vault.update_group", text="Update Library Copy", icon='FILE_REFRESH'
        ).group_name = tree.name

        # Hidden is not a state the file announces - it is the absence of the
        # field the Add menu filters on - so the item says what it will do.
        hidden = library.menu_visibility(copy_file, tree.name) is False
        operator = layout.operator(
            "asset_vault.set_menu_visibility",
            text="Show in the Add Menu" if hidden else "Hide from the Add Menu",
            icon='HIDE_OFF' if hidden else 'HIDE_ON',
        )
        operator.group_name = tree.name
        operator.visible = hidden

    layout.separator()
    layout.operator(
        "asset_vault.set_shortcut", text="Shortcut: %s" % props.shortcut_label(prefs), icon='KEYINGSET'
    )
    layout.operator(
        "preferences.addon_show", text="Asset Vault Settings", icon='PREFERENCES'
    ).module = __package__


class ASSETVAULT_MT_menu(bpy.types.Menu):
    """Everything Asset Vault can do, on one key"""

    bl_idname = keymap.MENU_IDNAME
    bl_label = "Asset Vault"

    def draw(self, context):
        draw_menu(self.layout, context)


class ASSETVAULT_OT_menu(bpy.types.Operator):
    """Open the Asset Vault menu"""

    bl_idname = keymap.OPEN_OPERATOR
    bl_label = "Asset Vault Menu"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return getattr(context, "space_data", None) is not None or context.area is not None

    def execute(self, context):
        bpy.ops.wm.call_menu(name=keymap.MENU_IDNAME)
        return {'FINISHED'}


classes = (ASSETVAULT_MT_menu, ASSETVAULT_OT_menu)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
