"""Headless suite for Asset Vault.

    blender --background --factory-startup --python tests/test_asset_vault.py -- --report out.json --work <dir>

The add-on is enabled from a throwaway BLENDER_USER_SCRIPTS folder (see
tests/run_tests.sh) and every library this suite writes into is a temp folder, so
neither the real Blender configuration nor the real asset libraries are touched.

What is NOT covered here: the menu as it appears in a window - the draw code is
driven through a recording fake layout - and Blender's asset index noticing the new
file by itself.  Both are checked by hand in the GUI.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import sys
import tempfile
import traceback
from types import SimpleNamespace

import addon_utils
import bpy

RESULTS = []
LIBRARY_NAME = "Asset Vault Test Library"


def check(name, condition, detail=""):
    ok = bool(condition)
    # a tuple detail would be swallowed by the % formatting below - normalise first
    detail = detail if isinstance(detail, str) else repr(detail)
    RESULTS.append({"name": name, "passed": ok, "detail": str(detail)})
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name, ("   [%s]" % detail) if detail else ""))
    return ok


def section(title):
    print("\n--- %s" % title)


def guarded(name, fn):
    try:
        fn()
    except Exception:
        RESULTS.append({"name": name, "passed": False, "detail": traceback.format_exc()})
        print("FAIL  %s   [raised]" % name)
        traceback.print_exc()


# --------------------------------------------------------------------------- fixtures

def make_group(name, node_count=2, nested=None):
    """A geometry node group with a couple of real nodes in it."""
    tree = bpy.data.node_groups.new(name, "GeometryNodeTree")
    tree.nodes.new("NodeGroupInput")
    tree.nodes.new("NodeGroupOutput")
    for _ in range(node_count):
        tree.nodes.new("GeometryNodeTransform")
    if nested is not None:
        node = tree.nodes.new("GeometryNodeGroup")
        node.node_tree = nested
    return tree


def register_library(name, directory):
    filepaths = bpy.context.preferences.filepaths
    for existing in list(filepaths.asset_libraries):
        if existing.name == name:
            filepaths.asset_libraries.remove(existing)
    return filepaths.asset_libraries.new(name=name, directory=directory)


def drop_library(name):
    filepaths = bpy.context.preferences.filepaths
    for existing in list(filepaths.asset_libraries):
        if existing.name == name:
            filepaths.asset_libraries.remove(existing)


class FakePrefs:
    """Only the three preferences the core reads."""

    def __init__(self, library_name=LIBRARY_NAME, catalog="Group", follow=False):
        self.follow_asset_browser = follow
        self.default_library = library_name
        self.catalog_path = catalog


class FakeNode:
    def __init__(self, node_type="GROUP", tree=None):
        self.type = node_type
        self.node_tree = tree


class RecordedCall:
    def __init__(self, idname, text='', icon=''):
        self.idname = idname
        self.text = text
        self.icon = icon
        self.group_name = None
        self.enabled = True


class FakeRow:
    """A sub-layout: only `enabled` matters, and it sticks to what it draws."""

    def __init__(self, parent, align=False):
        self.parent = parent
        self.enabled = True

    def operator(self, idname, text='', icon=''):
        call = RecordedCall(idname, text, icon)
        call.enabled = self.enabled
        self.parent.calls.append(call)
        return call

    def label(self, text='', icon=''):
        self.parent.labels.append(text)


class FakeLayout:
    def __init__(self):
        self.calls = []
        self.labels = []
        self.separators = 0
        self.enabled = True

    def separator(self):
        self.separators += 1

    def operator(self, idname, text='', icon=''):
        call = RecordedCall(idname, text, icon)
        call.enabled = self.enabled
        self.calls.append(call)
        return call

    def label(self, text='', icon=''):
        self.labels.append(text)

    def row(self, align=False):
        return FakeRow(self, align)


def fake_context(node=None, preferences=None):
    return SimpleNamespace(
        active_node=node,
        selected_nodes={} if node is None else {0: node},
        screen=None,
        preferences=preferences if preferences is not None else bpy.context.preferences,
    )


def load_groups(filepath):
    """(names in the file, loaded datablocks) without disturbing the session.

    The names list is copied before it is handed to Blender: that list object comes
    back holding the loaded datablocks instead of the names.
    """
    with bpy.data.libraries.load(str(filepath), link=False) as (src, dst):
        names = [
            entry if isinstance(entry, str) else entry.name for entry in (src.node_groups or [])
        ]
        dst.node_groups = list(names)
    return names, [entry for entry in (dst.node_groups or [])]


# --------------------------------------------------------------------------- tests

def test_addon(asset_vault):
    section("add-on")

    loaded, enabled = addon_utils.check("asset_vault")
    check("add-on is enabled", enabled, "loaded=%s" % loaded)
    check("save operator is registered", hasattr(bpy.ops.asset_vault, "save_group"))
    check("update operator is registered", hasattr(bpy.ops.asset_vault, "update_group"))
    check("the menu operator is registered", hasattr(bpy.ops.asset_vault, "menu"))
    check("the visibility command is registered", hasattr(bpy.ops.asset_vault, "set_menu_visibility"))
    check("the shortcut capture is registered", hasattr(bpy.ops.asset_vault, "set_shortcut"))

    source = open(asset_vault.__file__, encoding="utf-8").read()
    module = ast.parse(source)
    literal = None
    for node in module.body:
        if isinstance(node, ast.Assign) and any(
            getattr(target, "id", "") == "bl_info" for target in node.targets
        ):
            literal = ast.literal_eval(node.value)
    check("bl_info parses as a literal", isinstance(literal, dict))
    check(
        "bl_info version matches __version__",
        literal and tuple(literal["version"]) == tuple(int(p) for p in asset_vault.__version__.split(".")),
        "%s vs %s" % (literal.get("version") if literal else None, asset_vault.__version__),
    )
    entry = bpy.context.preferences.addons.get("asset_vault")
    check("the add-on has a preferences entry", entry is not None, list(bpy.context.preferences.addons.keys()))
    check(
        "the preferences entry is this add-on's",
        entry is not None and type(entry.preferences).__name__ == "ASSETVAULT_AP_preferences",
        type(entry.preferences).__name__ if entry else "",
    )


def test_file_names(library, work):
    section("file names")

    check("a plain name is kept", library.sanitize("Scatter Trees") == "Scatter Trees")
    check(
        "invalid characters become underscores",
        library.sanitize('a<b>c:d"e/f\\g|h?i*j') == "a_b_c_d_e_f_g_h_i_j",
        library.sanitize('a<b>c:d"e/f\\g|h?i*j'),
    )
    check("trailing dots and spaces go", library.sanitize("Group. ") == "Group")
    check("an empty name falls back", library.sanitize("") == "Unnamed")
    check("a long name is capped", len(library.sanitize("x" * 400)) == 150)
    check(
        "the file lands next to the library",
        str(library.asset_path(work, "My Group")) == os.path.join(work, "My Group.blend"),
    )


def test_catalogs(library, work):
    section("catalog file")

    library_dir = os.path.join(work, "catalog_library")
    os.makedirs(library_dir, exist_ok=True)

    uuid_one = library.ensure_catalog(library_dir, "Group")
    catalog_file = os.path.join(library_dir, library.CATALOG_FILE)
    check("the catalog file is created", os.path.isfile(catalog_file))
    check("the uuid is a string", isinstance(uuid_one, str) and len(uuid_one) == 36, uuid_one)
    rows = library.read_catalogs(library_dir)
    check("the catalog is in it, path and all", rows == [(uuid_one, "Group")], rows)
    check("asking again returns the same uuid", library.ensure_catalog(library_dir, "Group") == uuid_one)
    check(
        "no duplicate line was written",
        open(catalog_file, "rb").read().count(b"Group") == 2,  # uuid line + simple name
    )

    nested_uuid = library.ensure_catalog(library_dir, "Group/Scatter")
    rows = library.read_catalogs(library_dir)
    check("a nested catalog is created", (nested_uuid, "Group/Scatter") in rows, rows)
    check(
        "its simple name joins the path",
        b"Group-Scatter" in open(catalog_file, "rb").read(),
    )
    check("the version line is written once", open(catalog_file, "rb").read().count(b"VERSION 1") == 1)

    # an existing catalog file (Blender's own, CRLF, non-ASCII) is appended to, not rewritten
    other_dir = os.path.join(work, "foreign_library")
    os.makedirs(other_dir, exist_ok=True)
    original = (
        b"# This is an Asset Catalog Definition file for Blender.\r\n"
        b"VERSION 1\r\n"
        b"\r\n"
        b"11111111-2222-3333-4444-555555555555:\xe5\x9c\xb0\xe6\xaf\xaf:\xe5\x9c\xb0\xe6\xaf\xaf\r\n"
    )
    with open(os.path.join(other_dir, library.CATALOG_FILE), "wb") as handle:
        handle.write(original)
    library.ensure_catalog(other_dir, "Mine")
    after = open(os.path.join(other_dir, library.CATALOG_FILE), "rb").read()
    check("an existing catalog file keeps its bytes", after.startswith(original), after[:40])
    check("the new catalog is appended with the file's own line ending", b":Mine:Mine\r\n" in after)
    check(
        "existing catalogs are still read",
        ("11111111-2222-3333-4444-555555555555", "\u5730\u6bef") in library.read_catalogs(other_dir),
    )

    no_trailing_newline = os.path.join(work, "no_newline_library")
    os.makedirs(no_trailing_newline, exist_ok=True)
    with open(os.path.join(no_trailing_newline, library.CATALOG_FILE), "wb") as handle:
        handle.write(b"VERSION 1\n99999999-2222-3333-4444-555555555555:A:A")
    library.ensure_catalog(no_trailing_newline, "B")
    raw = open(os.path.join(no_trailing_newline, library.CATALOG_FILE), "rb").read()
    check("a half-written last line is never glued together", b":A:B\n" not in raw and b"A\n" in raw, raw)
    check("both catalogs read back", len(library.read_catalogs(no_trailing_newline)) == 2)


def test_write(library, work):
    section("writing a group")

    library_dir = os.path.join(work, "write_library")
    os.makedirs(library_dir, exist_ok=True)
    catalog_uuid = library.ensure_catalog(library_dir, "Group")

    nested = make_group("Nested Helper", node_count=0)
    tree = make_group("Saved Group", node_count=3, nested=nested)
    path = library.write_group(library_dir, tree, catalog_uuid)

    check("the file is written", os.path.isfile(path), str(path))
    names, loaded = load_groups(path)
    check("the group is in the file", "Saved Group" in names, names)
    root = loaded[names.index("Saved Group")] if "Saved Group" in names else None
    check("it is marked as an asset", bool(root and root.asset_data))
    check(
        "it kept the catalog",
        bool(root and root.asset_data) and str(root.asset_data.catalog_id) == catalog_uuid,
        str(root.asset_data.catalog_id) if root and root.asset_data else "",
    )
    check("it is protected in the library file", bool(root and root.use_fake_user))
    check("the nodes are there", bool(root) and len(root.nodes) == 6, len(root.nodes) if root else "no group")
    check("the nested group came along", "Nested Helper" in names, names)

    check("the source group was left alone", tree.asset_data is None)
    check("the source group still has its nodes", len(tree.nodes) == 6)

    # a group that is already an asset in this file keeps its own catalog
    tree.asset_mark()
    own_uuid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    tree.asset_data.catalog_id = own_uuid
    library.write_group(library_dir, tree, catalog_uuid)
    check("its own catalog is restored after the save", str(tree.asset_data.catalog_id) == own_uuid)
    names, loaded = load_groups(path)
    root = loaded[names.index("Saved Group")] if "Saved Group" in names else None
    check(
        "the file still gets the library catalog",
        bool(root and root.asset_data) and str(root.asset_data.catalog_id) == catalog_uuid,
    )
    tree.asset_clear()

    check("our own file is recognised", library.contains_group(path, "Saved Group"))
    check("a foreign file is not", not library.contains_group(path, "Some Other Group"))
    check("a missing file is not", not library.contains_group(os.path.join(library_dir, "nope.blend"), "x"))


def test_save_and_update(library, operators, work):
    section("save and update")

    library_dir = os.path.join(work, "save_library")
    os.makedirs(library_dir, exist_ok=True)
    register_library(LIBRARY_NAME, library_dir)
    prefs = FakePrefs()
    context = fake_context()

    tree = make_group("Round Trip", node_count=2)
    ok, message = operators.save_group(context, tree, prefs)
    path = library.asset_path(library_dir, "Round Trip")
    check("save reports success", ok, message)
    check("save says it saved", message.startswith("Saved"), message)
    check("the file is there", path.is_file(), str(path))
    check("the menu would now offer an update", library.find_copy(library_dir, "Round Trip") is not None)

    # change the group, then update: the library copy must follow
    tree.nodes.new("GeometryNodeTransform")
    ok, message = operators.save_group(context, tree, prefs, update=True)
    check("update reports success", ok, message)
    check("update says it updated", message.startswith("Updated"), message)
    _, loaded = load_groups(path)
    check("the library copy has the new node", len(loaded[0].nodes) == 5, len(loaded[0].nodes))

    # a file at the target path that this add-on did not write is never replaced
    stranded_name = "Stranded"
    stranded_path = library.asset_path(library_dir, stranded_name)
    library.write_group(
        library_dir,
        make_group("Something Else"),
        library.ensure_catalog(library_dir, "Group"),
        stranded_path,
    )
    stranded_tree = make_group(stranded_name)
    ok, message = operators.save_group(context, stranded_tree, prefs, update=True)
    check("a foreign file with our name is refused", not ok, message)
    check("and the refusal says why", "holds no group" in message, message)
    check("the foreign file is untouched", library.contains_group(stranded_path, "Something Else"))
    check("nothing was written for the refused save", not library.contains_group(stranded_path, stranded_name))

    # the operator that wraps it, driven directly
    ok, message = operators.save_group(context, tree, prefs)
    check("saving twice is harmless", ok and message.startswith("Updated"), message)


def test_no_library(library, operators, work):
    section("no library configured")

    filepaths = bpy.context.preferences.filepaths
    saved = [(lib.name, lib.path) for lib in filepaths.asset_libraries]
    try:
        for lib in list(filepaths.asset_libraries):
            filepaths.asset_libraries.remove(lib)
        ok, message = operators.save_group(fake_context(), make_group("Homeless"), FakePrefs(library_name=""))
        check("saving fails instead of guessing", not ok, message)
        check("and explains what to do", "no asset library configured" in message.lower(), message)
    finally:
        for name, path in saved:
            filepaths.asset_libraries.new(name=name, directory=path)
    check("the libraries are back", len(bpy.context.preferences.filepaths.asset_libraries) == len(saved))


def test_library_resolution(library, operators, work):
    section("library resolution")

    library_dir = os.path.join(work, "resolution_library")
    os.makedirs(library_dir, exist_ok=True)
    register_library(LIBRARY_NAME, library_dir)

    check("no Asset Browser open means no active library", library.active_library_name(fake_context()) is None)
    check(
        "the preference decides when not following the Asset Browser",
        library.target_library(fake_context(), FakePrefs()) == (LIBRARY_NAME, library_dir),
    )
    check(
        "a library name that is gone is refused rather than guessed",
        library.target_library(fake_context(), FakePrefs(library_name="Does Not Exist")) is None,
    )
    ok, message = operators.save_group(fake_context(), make_group("Stale"), FakePrefs(library_name="Does Not Exist"))
    check("and saving says which name went stale", not ok and "not configured any more" in message, message)
    check("the path is looked up by name", library.library_path(LIBRARY_NAME) == library_dir)


def test_menu(ui, library, operators, work):
    section("node editor menu")

    library_dir = os.path.join(work, "menu_library")
    os.makedirs(library_dir, exist_ok=True)
    register_library(LIBRARY_NAME, library_dir)

    # the draw code goes through the add-on's own preferences: use the real ones so
    # that lookup is exercised, not a stand-in for it
    entry = bpy.context.preferences.addons.get("asset_vault")
    check("the menu can find the preferences", entry is not None and entry.preferences is not None)
    addon_prefs = entry.preferences if entry else FakePrefs()
    check(
        "the library preference defaults to a configured one",
        addon_prefs.default_library in [name for name, _path in library.user_libraries()],
        addon_prefs.default_library,
    )
    addon_prefs.follow_asset_browser = False
    addon_prefs.default_library = LIBRARY_NAME
    addon_prefs.catalog_path = "Group"
    preferences = bpy.context.preferences

    tree = make_group("Menu Group", node_count=1)
    node = FakeNode("GROUP", tree)

    layout = FakeLayout()
    ui.draw_node_context_menu(SimpleNamespace(layout=layout), fake_context(node, preferences))
    check("one entry before the group is in the library", len(layout.calls) == 1, [c.idname for c in layout.calls])
    if layout.calls:
        check("it offers to save", layout.calls[0].idname == "asset_vault.save_group")
        check("it names the group it would save", layout.calls[0].group_name == "Menu Group")

    operators.save_group(fake_context(), tree, addon_prefs)
    layout = FakeLayout()
    ui.draw_node_context_menu(SimpleNamespace(layout=layout), fake_context(node, preferences))
    check("two entries once it is", len(layout.calls) == 2, [c.idname for c in layout.calls])
    check(
        "the second one updates",
        [c.idname for c in layout.calls] == ["asset_vault.save_group", "asset_vault.update_group"],
        [c.idname for c in layout.calls],
    )

    layout = FakeLayout()
    ui.draw_node_context_menu(
        SimpleNamespace(layout=layout), fake_context(FakeNode("TRANSFORM"), preferences)
    )
    check("a non-group node gets no entries", layout.calls == [], layout.calls)

    layout = FakeLayout()
    ui.draw_node_context_menu(SimpleNamespace(layout=layout), fake_context(None, preferences))
    check("an empty selection gets no entries", layout.calls == [], layout.calls)


def addon_preferences():
    entry = bpy.context.preferences.addons.get("asset_vault")
    return entry.preferences if entry is not None else None


def keymap_items(keymap):
    """Every binding of ours that Blender actually holds, read back out of it."""
    manager = getattr(bpy.context, "window_manager", None)
    config = getattr(getattr(manager, "keyconfigs", None), "addon", None)
    if config is None:
        return []
    keymap_map = config.keymaps.get(keymap.KEYMAP_NAME)
    if keymap_map is None:
        return []
    return [
        (item.type, item.ctrl, item.shift, item.alt)
        for item in keymap_map.keymap_items
        if item.idname == keymap.OPEN_OPERATOR
    ]


def test_shortcut(keymap, props, menu, work):
    section("the shortcut")

    check("the default key is T", props.DEFAULT_SHORTCUT == "T")
    check("a modifier on its own is not a key", keymap.is_modifier_only("LEFT_SHIFT"))
    check("a real key is not a modifier", not keymap.is_modifier_only("T"))
    check("mouse movement is ignored", keymap.is_ignorable("MOUSEMOVE"))
    check("the menu operator is registered", hasattr(bpy.ops.asset_vault, "menu"))
    check("the capture operator is registered", hasattr(bpy.ops.asset_vault, "set_shortcut"))
    check("the menu itself is registered", hasattr(bpy.types, "ASSETVAULT_MT_menu"))

    prefs = addon_preferences()
    check("the preferences carry the shortcut", prefs is not None and hasattr(prefs, "shortcut_key"))
    if prefs is None:
        return

    bound = keymap_items(keymap)
    check("enabling the add-on bound the menu to a key", bound == [("T", False, False, False)], bound)

    ok, message = keymap.apply_shortcut(bpy.context, "F9", ctrl=True)
    check("the shortcut can be changed", ok, message)
    bound = keymap_items(keymap)
    check("exactly one binding is kept", len(bound) == 1, bound)
    check("the new binding is the one asked for", bound == [("F9", True, False, False)], bound)
    check("the preference followed", prefs.shortcut_key == "F9" and prefs.shortcut_ctrl is True,
          (prefs.shortcut_key, prefs.shortcut_ctrl))
    check("the label reads back", props.shortcut_label(prefs) == "Ctrl+F9", props.shortcut_label(prefs))
    check("the menu names the shortcut", menu.draw_menu.__doc__ is not None)

    ok, message = keymap.apply_shortcut(bpy.context, "")
    check("an empty key clears the binding", ok and keymap_items(keymap) == [], keymap_items(keymap))
    check("the label says so", props.shortcut_label(prefs) == "not set", props.shortcut_label(prefs))

    ok, message = keymap.apply_shortcut(bpy.context, "T")
    check("the default can be put back", ok and prefs.shortcut_key == "T", message)
    check("and it is bound again", keymap_items(keymap) == [("T", False, False, False)], keymap_items(keymap))


def test_menu_visibility(library, operators, work):
    section("Add menu visibility")

    library_dir = os.path.join(work, "visibility_library")
    os.makedirs(library_dir, exist_ok=True)

    # The tree-type numbers belong to Blender, not to us: read them back out of it
    # so a change there fails here instead of quietly doing nothing in the GUI.
    wrong = []
    for idname, expected in library.TREE_TYPE_VALUES.items():
        probe = bpy.data.node_groups.new("Probe " + idname, idname)
        probe.asset_mark()
        actual = probe.asset_data[library.MENU_TYPE_PROP]
        if actual != expected:
            wrong.append((idname, expected, actual))
        bpy.data.node_groups.remove(probe)
    check("the tree type values match this Blender", not wrong, wrong)

    entry = bpy.context.preferences.addons.get("asset_vault")
    prefs = entry.preferences if entry is not None else FakePrefs()
    register_library(LIBRARY_NAME, library_dir)
    prefs.follow_asset_browser = False
    prefs.default_library = LIBRARY_NAME
    prefs.catalog_path = "Group"

    tree = make_group("Hidden Helper", node_count=1)
    catalog_uuid = library.ensure_catalog(library_dir, "Group")
    path = library.write_group(library_dir, tree, catalog_uuid)

    check("a saved group starts out in the Add menu", library.menu_visibility(path, tree.name) is True)
    check("a group that is not ours reads as unknown", library.menu_visibility(path, "Nope") is None)

    before = len(bpy.data.node_groups)
    ok, message = library.set_menu_visibility(path, tree.name, False)
    check("it can be hidden", ok, message)
    check("the file agrees", library.menu_visibility(path, tree.name) is False)
    check("nothing was left behind in the session", len(bpy.data.node_groups) == before,
          "%d -> %d" % (before, len(bpy.data.node_groups)))
    check("the group is still in the library", library.contains_group(path, tree.name))

    groups = library.load_library_groups(path)
    try:
        found = groups.get(tree.name)
        check("it is still an asset", found is not None and found.asset_data is not None)
        check(
            "its catalog survived",
            found is not None and str(found.asset_data.catalog_id) == catalog_uuid,
            str(found.asset_data.catalog_id) if found is not None else "",
        )
    finally:
        library.release_groups(groups)

    ok, message = library.set_menu_visibility(path, tree.name, True)
    check("it can be shown again", ok and library.menu_visibility(path, tree.name) is True, message)

    # A save must not undo a deliberate hide.
    library.set_menu_visibility(path, tree.name, False)
    operators.save_group(fake_context(), tree, prefs)
    check("an update keeps it hidden", library.menu_visibility(path, tree.name) is False)
    check("and the session's group was not touched", tree.name == "Hidden Helper", tree.name)

    result = bpy.ops.asset_vault.set_menu_visibility(group_name=tree.name, visible=False)
    check("the command does the same from the operator", result == {'FINISHED'}, result)
    check("and the file reflects it", library.menu_visibility(path, tree.name) is False)

    # A file with anything but node groups in it is somebody else's - never rewritten.
    bpy.ops.mesh.primitive_cube_add()
    cube = bpy.context.active_object
    foreign = os.path.join(library_dir, "not ours.blend")
    bpy.data.libraries.write(foreign, {cube}, fake_user=True)
    ok, message = library.set_menu_visibility(foreign, tree.name, False)
    check("a file holding more than node groups is refused", not ok, message)
    bpy.data.objects.remove(cube, do_unlink=True)


def test_vault_menu(menu, library, operators, work):
    section("the one menu")

    library_dir = os.path.join(work, "vault_menu_library")
    os.makedirs(library_dir, exist_ok=True)
    register_library(LIBRARY_NAME, library_dir)

    entry = bpy.context.preferences.addons.get("asset_vault")
    prefs = entry.preferences if entry is not None else FakePrefs()
    prefs.follow_asset_browser = False
    prefs.default_library = LIBRARY_NAME
    prefs.catalog_path = "Group"
    preferences = bpy.context.preferences

    layout = FakeLayout()
    menu.draw_menu(layout, fake_context(None, preferences))
    saved = [call for call in layout.calls if call.idname == "asset_vault.save_group"]
    check("saving is on the menu but out of reach with nothing selected",
          bool(saved) and saved[0].enabled is False, [(c.idname, c.enabled) for c in layout.calls])
    check("it says what to do instead", any("Select" in text for text in layout.labels), layout.labels)
    check("the settings entries are always on it",
          [call.idname for call in layout.calls][-2:] ==
          ["asset_vault.set_shortcut", "preferences.addon_show"],
          [call.idname for call in layout.calls])

    tree = make_group("Menu Draw Group", node_count=1)
    operators.save_group(fake_context(), tree, prefs)
    node = FakeNode("GROUP", tree)

    layout = FakeLayout()
    menu.draw_menu(layout, fake_context(node, preferences))
    check(
        "a saved group gets the whole menu",
        [call.idname for call in layout.calls] == [
            "asset_vault.save_group",
            "asset_vault.update_group",
            "asset_vault.set_menu_visibility",
            "asset_vault.set_shortcut",
            "preferences.addon_show",
        ],
        [call.idname for call in layout.calls],
    )
    switch = layout.calls[2]
    check("the switch offers to hide it", switch.text == "Hide from the Add Menu", switch.text)
    check("and would show it again if used", switch.visible is False, switch.visible)

    library.set_menu_visibility(library.find_copy(library_dir, tree.name), tree.name, False)
    layout = FakeLayout()
    menu.draw_menu(layout, fake_context(node, preferences))
    switch = layout.calls[2]
    check("once hidden, the menu offers the way back", switch.text == "Show in the Add Menu", switch.text)
    check("and would hide it if used", switch.visible is True, switch.visible)

    layout = FakeLayout()
    menu.draw_menu(layout, fake_context(FakeNode("TRANSFORM"), preferences))
    check("a non-group node still gets the settings half",
          "asset_vault.save_group" in [call.idname for call in layout.calls],
          [call.idname for call in layout.calls])


# --------------------------------------------------------------------------- main

def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", default="")
    parser.add_argument("--work", default="")
    args = parser.parse_args(argv)

    work = args.work or tempfile.mkdtemp(prefix="assetvault_test.")
    os.makedirs(work, exist_ok=True)

    addon_utils.enable("asset_vault", default_set=False, persistent=False)
    # Enable the way Blender's own Preferences do it, so the add-on gets a real
    # entry in preferences.addons: that entry is the code path the add-on's own
    # preferences are read through, and addon_utils.enable() alone does not make one.
    try:
        bpy.ops.preferences.addon_enable(module="asset_vault")
    except Exception:
        pass
    import importlib

    asset_vault = importlib.import_module("asset_vault")
    library = importlib.import_module("asset_vault.library")
    operators = importlib.import_module("asset_vault.operators")
    ui = importlib.import_module("asset_vault.ui")
    keymap = importlib.import_module("asset_vault.keymap")
    menu = importlib.import_module("asset_vault.menu")
    props = importlib.import_module("asset_vault.props")

    guarded("add-on", lambda: test_addon(asset_vault))
    guarded("file names", lambda: test_file_names(library, work))
    guarded("catalog file", lambda: test_catalogs(library, work))
    guarded("writing a group", lambda: test_write(library, work))
    guarded("save and update", lambda: test_save_and_update(library, operators, work))
    guarded("no library", lambda: test_no_library(library, operators, work))
    guarded("library resolution", lambda: test_library_resolution(library, operators, work))
    guarded("menu", lambda: test_menu(ui, library, operators, work))
    guarded("shortcut", lambda: test_shortcut(keymap, props, menu, work))
    guarded("Add menu visibility", lambda: test_menu_visibility(library, operators, work))
    guarded("the one menu", lambda: test_vault_menu(menu, library, operators, work))

    failed = [r for r in RESULTS if not r["passed"]]
    print("\n%d checks, %d failed" % (len(RESULTS), len(failed)))
    for result in failed:
        print("  FAILED: %s   [%s]" % (result["name"], result["detail"]))

    if args.report:
        with open(args.report, "w", encoding="utf-8") as handle:
            json.dump({"blender": bpy.app.version_string, "results": RESULTS}, handle, indent=1)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
