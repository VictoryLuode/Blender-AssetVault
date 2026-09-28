"""Add-on preferences: which library new groups go into, and under which catalog."""
from __future__ import annotations

import bpy

from . import library

# Identifier used when this machine has no asset library configured at all.
_NO_LIBRARY = "__none__"


def library_items(self, context):
    items = [(name, name, path) for name, path in library.user_libraries()]
    if not items:
        return [(_NO_LIBRARY, "No asset library configured", "Edit > Preferences > File Paths")]
    return items


def get_preferences(context):
    """This add-on's preferences, or None when it is not enabled."""
    addons = getattr(getattr(context, "preferences", None), "addons", None)
    if not addons:
        return None
    entry = addons.get(__package__)
    return entry.preferences if entry else None


class ASSETVAULT_AP_preferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    follow_asset_browser: bpy.props.BoolProperty(
        name="Follow the Asset Browser",
        description=(
            "Save into the library currently selected in the Asset Browser. "
            "The library below is used whenever no Asset Browser is open"
        ),
        default=True,
    )
    default_library: bpy.props.EnumProperty(
        name="Library",
        description="Asset library that groups are written into",
        items=library_items,
    )
    catalog_path: bpy.props.StringProperty(
        name="Catalog",
        description=(
            'Catalog these groups are filed under. "Group" is the catalog name '
            "the node editor's Add menu reads, which is why it is the default"
        ),
        default=library.DEFAULT_CATALOG,
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "follow_asset_browser")
        row = layout.row()
        row.enabled = not self.follow_asset_browser
        row.prop(self, "default_library")
        layout.prop(self, "catalog_path")

        layout.separator()
        box = layout.box()
        box.label(text="Right-click a Group node in the node editor.", icon='INFO')
        box.label(text="Saved groups show up in the Add menu (Shift+A > Group).")


classes = (ASSETVAULT_AP_preferences,)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
