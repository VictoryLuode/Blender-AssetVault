"""The commands: save the group into the library, update the copy already there,
and take that library copy in or out of the node Add menus."""
from __future__ import annotations

import bpy
from bpy.props import BoolProperty, StringProperty

from . import library, props


def group_tree_of(node):
    """The node group behind a node, or None for anything that is not a group node."""
    if getattr(node, "type", "") != 'GROUP':
        return None
    return getattr(node, "node_tree", None)


def active_group_tree(context):
    """The group the user is pointing at in the node editor.

    Blender's own group commands read context.active_node - right-clicking a node
    makes it the active one - and selected_nodes is the fallback for a menu opened
    over a selection.
    """
    tree = group_tree_of(getattr(context, "active_node", None))
    if tree is not None:
        return tree

    groups = [group_tree_of(node) for node in getattr(context, "selected_nodes", {}).values()]
    groups = [group for group in groups if group is not None]
    return groups[0] if len(groups) == 1 else None


def resolve_tree(context, group_name=""):
    """The group to act on: whatever is active now, else the one the menu named."""
    tree = active_group_tree(context)
    if tree is None and group_name:
        tree = bpy.data.node_groups.get(group_name)
    return tree


def save_group(context, tree, prefs, *, update=False):
    """Write `tree` into the target library. Returns (ok, message).

    Saving and updating do the same work - one .blend per group, written again -
    so they share this function and differ only in what they expect to find.
    """
    target = library.target_library(context, prefs)
    if target is None:
        configured = getattr(prefs, "default_library", "") if prefs is not None else ""
        if configured:
            return False, "The library '%s' is not configured any more - pick one in the add-on preferences" % configured
        return False, "No asset library configured - add one in Edit > Preferences > File Paths"
    library_name, library_dir = target

    filepath = library.asset_path(library_dir, tree.name)
    existing = filepath.is_file()

    # An update only ever replaces this add-on's own copy. A file with the same
    # name holding something else - a downloaded pack, a group saved by hand - is
    # left alone rather than overwritten.
    if existing and not library.contains_group(filepath, tree.name):
        return False, "Not overwriting %s in %s: it holds no group called '%s'" % (
            filepath.name,
            library_name,
            tree.name,
        )

    catalog_uuid = library.ensure_catalog(
        library_dir, getattr(prefs, "catalog_path", library.DEFAULT_CATALOG) or library.DEFAULT_CATALOG
    )
    library.write_group(library_dir, tree, catalog_uuid, filepath)
    library.refresh_libraries()

    return True, "%s '%s' in %s" % ("Updated" if existing else "Saved", tree.name, library_name)


class _GroupToLibrary:
    """Shared body of the two commands - neither is reachable for a non-group node."""

    bl_options = {'REGISTER'}

    group_name: StringProperty(name="Group", default="")

    #: True for the command that expects a copy to exist already.
    _update = False

    @classmethod
    def poll(cls, context):
        if resolve_tree(context) is None:
            cls.poll_message_set("Select a Group node in the node editor")
            return False
        return True

    def execute(self, context):
        tree = resolve_tree(context, self.group_name)
        if tree is None:
            self.report({'ERROR'}, "No node group to save")
            return {'CANCELLED'}

        ok, message = save_group(context, tree, props.get_preferences(context), update=self._update)
        self.report({'INFO'} if ok else {'WARNING'}, message)
        return {'FINISHED'} if ok else {'CANCELLED'}


class ASSETVAULT_OT_save_group(_GroupToLibrary, bpy.types.Operator):
    """Write this node group into the asset library as its own file"""

    bl_idname = "asset_vault.save_group"
    bl_label = "Save to Asset Library"


class ASSETVAULT_OT_update_group(_GroupToLibrary, bpy.types.Operator):
    """Replace the library's copy of this node group with the one in this file"""

    bl_idname = "asset_vault.update_group"
    bl_label = "Update Library Copy"
    _update = True


class ASSETVAULT_OT_set_menu_visibility(bpy.types.Operator):
    """Keep this group's library copy out of the node Add menus, or put it back"""

    bl_idname = "asset_vault.set_menu_visibility"
    bl_label = "Add Menu Visibility"
    bl_options = {'REGISTER'}

    group_name: StringProperty(name="Group", default="")
    visible: BoolProperty(name="Show in the Add menu", default=True)

    def execute(self, context):
        prefs = props.get_preferences(context)
        target = library.target_library(context, prefs)
        if target is None:
            configured = getattr(prefs, "default_library", "") if prefs is not None else ""
            if configured:
                self.report(
                    {'WARNING'},
                    "The library '%s' is not configured any more - pick one in the add-on preferences"
                    % configured,
                )
            else:
                self.report({'WARNING'}, "No asset library configured - add one in Edit > Preferences > File Paths")
            return {'CANCELLED'}

        tree = resolve_tree(context, self.group_name)
        name = tree.name if tree is not None else self.group_name
        filepath = library.find_copy(target[1], name)
        if filepath is None:
            self.report({'WARNING'}, "No copy of '%s' in %s yet - save it first" % (name, target[0]))
            return {'CANCELLED'}

        ok, message = library.set_menu_visibility(filepath, name, self.visible)
        if ok:
            library.refresh_libraries()
        self.report({'INFO'} if ok else {'WARNING'}, message)
        return {'FINISHED'} if ok else {'CANCELLED'}


classes = (
    ASSETVAULT_OT_save_group,
    ASSETVAULT_OT_update_group,
    ASSETVAULT_OT_set_menu_visibility,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
