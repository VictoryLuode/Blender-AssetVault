"""The entry point: two entries in the node editor's right-click menu."""
from __future__ import annotations

import bpy

from . import library, operators
from .props import get_preferences


def draw_node_context_menu(self, context):
    """Save / update, right where the group is.

    Added at the end of Blender's own node menu, and only when a group node is
    active - right-clicking anything else leaves that menu exactly as it was.
    """
    tree = operators.active_group_tree(context)
    if tree is None:
        return

    layout = self.layout

    layout.separator()
    layout.operator(
        "asset_vault.save_group",
        text="Save to Asset Library",
        icon='FILE_TICK',
    ).group_name = tree.name

    target = library.target_library(context, get_preferences(context))
    if target is not None and library.find_copy(target[1], tree.name):
        layout.operator(
            "asset_vault.update_group",
            text="Update Library Copy",
            icon='FILE_REFRESH',
        ).group_name = tree.name


def register():
    bpy.types.NODE_MT_context_menu.append(draw_node_context_menu)


def unregister():
    bpy.types.NODE_MT_context_menu.remove(draw_node_context_menu)
