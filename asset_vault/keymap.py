"""The keyboard route into the menu: one shortcut, owned by the user.

Blender's keymap editor can rebind anything, but an add-on that hides its one
entry point behind a key has to be able to say what that key is and to change it
without a trip through the global keymap - so the shortcut lives in the add-on's
preferences and the keymap item is rebuilt from those whenever they change.

The item goes into the add-on keyconfig (`keyconfigs.addon`), which is the layer
Blender reserves for add-ons: it never rewrites the user's own keymap, and the
binding disappears with the add-on instead of lingering in Preferences.
"""
from __future__ import annotations

import bpy
from bpy.props import BoolProperty

from . import props

#: The menu this shortcut opens, and the operator that opens it.  Kept here
#: because this module is what binds the key; `menu` imports them from here.
MENU_IDNAME = "ASSETVAULT_MT_menu"
OPEN_OPERATOR = "asset_vault.menu"

#: Keymaps the binding is added to: every node editor (geometry, shader, compositor).
KEYMAP_NAME = "Node Editor"
KEYMAP_SPACE = 'NODE_EDITOR'

#: Keys that only qualify a combination; the capture keeps waiting for a real key.
MODIFIER_KEYS = {
    "LEFT_SHIFT",
    "RIGHT_SHIFT",
    "LEFT_CTRL",
    "RIGHT_CTRL",
    "LEFT_ALT",
    "RIGHT_ALT",
    "LEFT_OSKEY",
    "RIGHT_OSKEY",
    "OSKEY",
    "HYPER",
    "SUPER",
    "META",
}

#: Events a capture ignores outright - they are not keys the user pressed.
_IGNORED_EVENTS = {"MOUSEMOVE", "INBETWEEN_MOUSEMOVE", "TIMER", "TIMER_REPORT", "WINDOW_DEACTIVATE"}

_owned: list = []


def is_modifier_only(event_type: str) -> bool:
    """True for Shift/Ctrl/Alt on their own - a combination, not a key yet."""
    return (event_type or "").upper() in MODIFIER_KEYS


def is_ignorable(event_type: str) -> bool:
    return (event_type or "").upper() in _IGNORED_EVENTS


def unregister() -> None:
    """Take our keymap items back out, leaving any other add-on's items alone."""
    for keymap, item in _owned:
        try:
            keymap.keymap_items.remove(item)
        except Exception:
            pass
    _owned.clear()


def register(key: str = props.DEFAULT_SHORTCUT, ctrl=False, shift=False, alt=False):
    """Bind `key` to the menu.  An empty key means "no shortcut"."""
    unregister()
    key = (key or "").strip().upper()
    if not key:
        return None

    manager = getattr(bpy.context, "window_manager", None)
    configs = getattr(manager, "keyconfigs", None) if manager is not None else None
    config = getattr(configs, "addon", None) if configs is not None else None
    if config is None:
        # Background or headless session with no add-on keyconfig: nothing to bind to.
        return None

    keymap = config.keymaps.get(KEYMAP_NAME)
    if keymap is None:
        keymap = config.keymaps.new(name=KEYMAP_NAME, space_type=KEYMAP_SPACE)
    item = keymap.keymap_items.new(OPEN_OPERATOR, key, 'PRESS', ctrl=ctrl, shift=shift, alt=alt)
    _owned.append((keymap, item))
    return item


def apply_shortcut(context, key: str, ctrl=False, shift=False, alt=False) -> tuple[bool, str]:
    """Store a new shortcut in the preferences and bind it right away.

    Separated from the capture operator on purpose: this is the whole effect of
    choosing a key, and it can be exercised without a keyboard.
    """
    key = (key or "").strip().upper()
    preferences = props.get_preferences(context)
    if preferences is None:
        return False, "Asset Vault is not enabled - no preferences to store the shortcut in"

    preferences.shortcut_key = key
    preferences.shortcut_ctrl = bool(ctrl)
    preferences.shortcut_shift = bool(shift)
    preferences.shortcut_alt = bool(alt)

    if not key:
        unregister()
        return True, "Shortcut cleared"
    if register(key, ctrl=ctrl, shift=shift, alt=alt) is None:
        return False, "Could not bind %s in this session" % props.shortcut_label(preferences)
    return True, "Asset Vault menu: %s" % props.shortcut_label(preferences)


def register_from_preferences(prefs=None) -> None:
    """Bind whatever the preferences say - the default when there are none."""
    if prefs is None:
        register()
        return
    register(
        getattr(prefs, "shortcut_key", props.DEFAULT_SHORTCUT),
        ctrl=getattr(prefs, "shortcut_ctrl", False),
        shift=getattr(prefs, "shortcut_shift", False),
        alt=getattr(prefs, "shortcut_alt", False),
    )


class ASSETVAULT_OT_set_shortcut(bpy.types.Operator):
    """Press the key that should open the Asset Vault menu"""

    bl_idname = "asset_vault.set_shortcut"
    bl_label = "Set Shortcut"
    bl_options = {'REGISTER'}

    reset: BoolProperty(name="Back to the default", default=False)

    def invoke(self, context, event):
        if self.reset or getattr(context, "window_manager", None) is None:
            return self.execute(context)
        context.window_manager.modal_handler_add(self)
        workspace = getattr(context, "workspace", None)
        if workspace is not None:
            workspace.status_text_set(
                "Press the key for the Asset Vault menu   (Esc cancels, Delete clears)"
            )
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if is_ignorable(event.type):
            return {'RUNNING_MODAL'}
        if event.type in {'ESC', 'RIGHTMOUSE'}:
            self._status(context, None)
            return {'CANCELLED'}
        if event.value != 'PRESS' or is_modifier_only(event.type):
            return {'RUNNING_MODAL'}

        self._status(context, None)
        if event.type in {'BACKSPACE', 'DELETE'}:
            ok, message = apply_shortcut(context, "")
        else:
            ok, message = apply_shortcut(
                context, event.type, ctrl=event.ctrl, shift=event.shift, alt=event.alt
            )
        self.report({'INFO'} if ok else {'WARNING'}, message)
        return {'FINISHED'} if ok else {'CANCELLED'}

    def execute(self, context):
        ok, message = apply_shortcut(context, props.DEFAULT_SHORTCUT)
        self.report({'INFO'} if ok else {'WARNING'}, message)
        return {'FINISHED'} if ok else {'CANCELLED'}

    @staticmethod
    def _status(context, text):
        workspace = getattr(context, "workspace", None)
        if workspace is not None:
            workspace.status_text_set(text)


classes = (ASSETVAULT_OT_set_shortcut,)


def register_classes() -> None:
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister_classes() -> None:
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
