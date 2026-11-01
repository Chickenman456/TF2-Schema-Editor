"""Local application state and TF2 synchronization."""

import json
import os
import re
import sys
import threading
import uuid
from collections import Counter

from . import __version__
from .editing import export_copy
from .tf2 import Schema, TF2Files


ITEMS_MARKER = os.path.join("scripts", "items", "items_game.txt")
ITEM_CATEGORIES = (
    ("cosmetics", "Cosmetics"),
    ("halloween restricted", "Halloween restricted"),
    ("tournament medals", "Tournament medals"),
    ("community medals", "Community medals"),
    ("other medals", "Other medals"),
    ("taunts", "Taunts"),
    ("weapons", "Weapons"),
    ("stock weapons", "Stock weapons"),
    ("action items", "Action items"),
    ("stock items", "Stock items"),
    ("tools", "Tools"),
    ("other", "Other"),
)
TF2_UI_FONTS = {"tf2build.ttf"}
TF2_SOUND_FIELDS = (
    "drop_sound", "equip_sound", "pickup_sound", "sound_pickup", "mouse_pressed_sound",
)
EDITABLE_ITEM_FIELDS = {
    "item_type_name",
    *TF2_SOUND_FIELDS,
}
CAPABILITY_KEYS = {
    "can_be_traded",
    "can_be_crafted",
    "can_be_restored",
    "can_be_gifted",
}


def _is_tf_dir(path):
    if not path or not os.path.isdir(path):
        return False
    if os.path.isfile(os.path.join(path, ITEMS_MARKER)):
        return True
    try:
        return any(name.lower().endswith("_dir.vpk") for name in os.listdir(path))
    except OSError:
        return False


def normalize_tf_dir(path):
    if not path:
        return None
    path = os.path.expanduser(str(path).strip().strip('"'))
    candidates = (
        path,
        os.path.join(path, "tf"),
        os.path.join(path, "Team Fortress 2", "tf"),
        os.path.join(path, "steamapps", "common", "Team Fortress 2", "tf"),
    )
    for candidate in candidates:
        if _is_tf_dir(candidate):
            return os.path.abspath(candidate)
    return None


def _steam_roots():
    roots = []
    if sys.platform.startswith("win"):
        try:
            import winreg
            for hive, key in (
                (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam"),
            ):
                try:
                    with winreg.OpenKey(hive, key) as steam_key:
                        for value in ("SteamPath", "InstallPath"):
                            try:
                                roots.append(winreg.QueryValueEx(steam_key, value)[0])
                            except OSError:
                                pass
                except OSError:
                    pass
        except ImportError:
            pass
        roots.extend((r"C:\Program Files (x86)\Steam", r"C:\Program Files\Steam"))
    home = os.path.expanduser("~")
    roots.extend((
        os.path.join(home, "Library", "Application Support", "Steam"),
        os.path.join(home, ".steam", "steam"),
        os.path.join(home, ".local", "share", "Steam"),
    ))
    return [root for root in roots if root and os.path.isdir(root)]


def find_tf_dir():
    configured = normalize_tf_dir(os.environ.get("TF2_DIR"))
    if configured:
        return configured
    seen = set()
    for root in _steam_roots():
        libraries = [root]
        library_file = os.path.join(root, "steamapps", "libraryfolders.vdf")
        try:
            with open(library_file, encoding="utf-8", errors="replace") as source:
                libraries.extend(path.replace("\\\\", "\\")
                                 for path in re.findall(r'"path"\s+"([^"]+)"', source.read()))
        except OSError:
            pass
        for library in libraries:
            key = os.path.normcase(os.path.abspath(library))
            if key in seen:
                continue
            seen.add(key)
            found = normalize_tf_dir(os.path.join(
                library, "steamapps", "common", "Team Fortress 2", "tf"
            ))
            if found:
                return found
    return None


def _settings_path():
    if sys.platform.startswith("win"):
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return os.path.join(base, "TF2SchemaWorkshop", "settings.json")
    return os.path.join(os.path.expanduser("~"), ".tf2-schema-workshop", "settings.json")


def _load_settings(path):
    try:
        with open(path, encoding="utf-8") as source:
            value = json.load(source)
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_settings(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as destination:
        json.dump(value, destination, indent=2)
    os.replace(temporary, path)


class Workshop:
    def __init__(self):
        self.settings_path = _settings_path()
        self.user_dir = os.path.dirname(self.settings_path)
        self.settings = _load_settings(self.settings_path)
        self.drafts_path = os.path.join(self.user_dir, "drafts.json")
        self.blocks_path = os.path.join(self.user_dir, "attribute_blocks.json")
        self.drafts = self._load_json(self.drafts_path, {})
        self.blocks = self._load_json(self.blocks_path, [])
        self.tf_dir = normalize_tf_dir(self.settings.get("tf_dir")) or find_tf_dir()
        self.files = None
        self.schema = None
        self.base_schema = None
        self.schema_source = ""
        self.lock = threading.RLock()
        self.job = {
            "state": "idle",
            "message": "Ready to synchronize with a local TF2 installation.",
            "error": "",
        }
        self.warnings = []

    @staticmethod
    def _load_json(path, default):
        try:
            with open(path, encoding="utf-8") as source:
                value = json.load(source)
            return value if isinstance(value, type(default)) else default
        except (OSError, ValueError):
            return default

    @staticmethod
    def _save_json(path, value):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        temporary = path + ".tmp"
        with open(temporary, "w", encoding="utf-8") as destination:
            json.dump(value, destination, ensure_ascii=False, indent=2)
        os.replace(temporary, path)

    def _overlay_drafts(self, schema, drafts=None):
        for item_id, patch in (self.drafts if drafts is None else drafts).items():
            item = schema.by_id.get(int(item_id)) if str(item_id).isdigit() else None
            if not item or not isinstance(patch, dict):
                continue
            for section in ("attributes", "static_attrs"):
                changes = patch.get(section)
                if isinstance(changes, dict):
                    item[section] = dict(item.get(section) or {})
                    item[section].update(changes)
            properties = patch.get("properties")
            if isinstance(properties, dict):
                item["properties"] = dict(item.get("properties") or {})
                item["properties"].update(properties)
            schema.apply_item_patch(item["defindex"], patch)

    def status(self):
        with self.lock:
            return {
                "version": __version__,
                "tf_dir": self.tf_dir or "",
                "state": dict(self.job),
                "item_count": len(self.schema.items) if self.schema else 0,
                "archive_count": len(self.files.vpks) if self.files else 0,
                "warning_count": len(self.warnings),
                "warnings": self.warnings[:12],
                "draft_count": len(self.drafts),
                "export_path": self.export_path(),
                "schema_source": self.schema_source,
            }

    def editor_data(self):
        with self.lock:
            item_types = {}
            sound_item_examples = {}
            items = self.schema.items if self.schema else []
            noise_maker_items = [
                item for item in items
                if re.search(
                    r"\bnoise maker\b",
                    str(item.get("metadata", {}).get("name") or item.get("name") or ""),
                    re.IGNORECASE,
                )
            ]
            noise_maker_sounds = {
                item.get("sounds", {}).get("mouse_pressed_sound")
                for item in noise_maker_items
                if item.get("sounds", {}).get("mouse_pressed_sound")
            }
            other_item_sounds = {
                reference
                for item in items
                if item not in noise_maker_items
                for reference in item.get("sounds", {}).values()
                if reference
            }
            noise_maker_sounds.difference_update(other_item_sounds)
            for item in items:
                value = item.get("type_value")
                label = item.get("type")
                if value and label:
                    item_types[value] = label
                for field, reference in item.get("sounds", {}).items():
                    if reference and reference not in noise_maker_sounds:
                        candidate = {
                            "defindex": item["defindex"],
                            "name": item["name"],
                            "image_inventory": item.get("image_inventory", ""),
                            "field": field,
                        }
                        current = sound_item_examples.get(reference)
                        if current is None or (
                                not current["image_inventory"] and candidate["image_inventory"]):
                            sound_item_examples[reference] = candidate
            return {
                "categories": [list(category) for category in ITEM_CATEGORIES],
                "category_counts": dict(Counter(item["category"] for item in self.schema.items)) if self.schema else {},
                "item_types": [
                    {"value": value, "label": label}
                    for value, label in sorted(item_types.items(), key=lambda entry: entry[1].casefold())
                ],
                "sound_references": sorted({
                    reference
                    for item in items
                    for reference in item.get("sounds", {}).values()
                    if reference and reference not in noise_maker_sounds
                }, key=str.casefold),
                "sound_fields_used": sorted({
                    field
                    for item in items
                    for field, reference in item.get("sounds", {}).items()
                    if reference
                }),
                "sound_item_examples": sound_item_examples,
                "attribute_definitions": self.schema.attribute_definitions if self.schema else [],
                "capability_keys": [],
                "draft_count": len(self.drafts),
                "export_path": self.export_path(),
                "schema_source": self.schema_source,
                "editing_enabled": self.schema is not None,
            }

    def export_path(self):
        return os.path.join(self.user_dir, "exports", "items_game.workshop.txt")

    def start_sync(self, path=None):
        with self.lock:
            if self.job["state"] == "scanning":
                raise RuntimeError("A TF2 sync is already running.")
            selected = normalize_tf_dir(path) if path else (normalize_tf_dir(self.tf_dir) or find_tf_dir())
            if not selected:
                raise ValueError(
                    "TF2 was not detected. Enter the Team Fortress 2 folder or its tf subfolder."
                )
            self.tf_dir = selected
            self.settings["tf_dir"] = selected
            _save_settings(self.settings_path, self.settings)
            self.files = None
            self.schema = None
            self.base_schema = None
            self.schema_source = ""
            self.warnings = []
            self.job = {"state": "scanning", "message": "Starting TF2 sync...", "error": ""}
            worker = threading.Thread(target=self._sync, args=(selected,), daemon=True)
            worker.start()
            return selected

    def _progress(self, message):
        with self.lock:
            if self.job["state"] == "scanning":
                self.job["message"] = message

    def _sync(self, selected):
        try:
            self._progress("Opening VPK archives")
            files = TF2Files(selected)
            self._progress("Indexing loose files and VPK assets")
            loose_count = files.index_loose_files(self._progress)
            self._progress("Reading sound definitions")
            files.parse_sound_definitions(self._progress)
            base_schema = Schema(files, self._progress)
            schema = Schema(files, source_bytes=base_schema.source_bytes)
            self._overlay_drafts(schema)
            warnings = files.warnings[:]
            if len(schema.items) < 10:
                count_label = "definition" if len(schema.items) == 1 else "definitions"
                verb = "was" if len(schema.items) == 1 else "were"
                warnings.append(
                    "Only %d item %s %s found; this is unusually small for a full TF2 schema."
                    % (len(schema.items), count_label, verb)
                )
            if not loose_count:
                warnings.append("No loose asset files were found; VPK assets were still indexed.")
            with self.lock:
                self.files = files
                self.schema = schema
                self.base_schema = base_schema
                self.schema_source = ""
                self.warnings = warnings
                message = "Sync complete: %d item definitions loaded." % len(schema.items)
                if len(schema.items) < 10:
                    count_label = "definition" if len(schema.items) == 1 else "definitions"
                    verb = "was" if len(schema.items) == 1 else "were"
                    message += " Warning: only %d %s %s found; the local schema may be incomplete." % (
                        len(schema.items), count_label, verb
                    )
                self.job = {
                    "state": "ready",
                    "message": message,
                    "error": "",
                }
        except (OSError, ValueError, UnicodeError) as error:
            with self.lock:
                self.files = None
                self.schema = None
                self.base_schema = None
                self.job = {"state": "error", "message": "TF2 sync failed.", "error": str(error)}
        except Exception as error:
            with self.lock:
                self.files = None
                self.schema = None
                self.base_schema = None
                self.job = {"state": "error", "message": "TF2 sync failed.", "error": str(error)}
            print("TF2 sync failed: %s" % error, file=sys.stderr)

    def icon(self, defindex):
        with self.lock:
            schema = self.schema
        return schema.icon(defindex) if schema else (None, None)

    def sound(self, defindex, field):
        with self.lock:
            schema = self.schema
        return schema.sound(defindex, field) if schema else (None, None)

    def sound_reference(self, reference):
        with self.lock:
            schema = self.schema
        return schema.sound_reference(reference) if schema else (None, None)

    def ui_font(self, filename):
        if filename not in TF2_UI_FONTS:
            raise ValueError("Unsupported TF2 UI font.")
        with self.lock:
            tf_dir = self.tf_dir
        if not tf_dir:
            return None
        path = os.path.join(tf_dir, "resource", filename)
        try:
            with open(path, "rb") as source:
                return source.read()
        except OSError:
            return None

    def tf2_logo(self):
        for root in _steam_roots():
            path = os.path.join(root, "appcache", "librarycache", "440", "logo.png")
            try:
                with open(path, "rb") as source:
                    return source.read()
            except FileNotFoundError:
                continue
        return None

    def items(self, category=None):
        with self.lock:
            if not self.schema:
                return None
            if category and category not in {category_id for category_id, _ in ITEM_CATEGORIES}:
                raise ValueError("Unknown item category.")
            items = [
                item for item in self.schema.items
                if not category or item["category"] == category
            ]
            for item in items:
                patch = self.drafts.get(str(item["defindex"]), {})
                item["changed_fields"] = {
                    section: sorted((patch.get(section) or {}).keys())
                    for section in (
                        "item_fields", "capabilities", "attributes", "static_attrs", "properties"
                    )
                }
            return items

    def update_item(self, defindex, item_fields=None, capabilities=None, static_attrs=None,
                    attributes=None):
        with self.lock:
            if not self.schema:
                raise RuntimeError("Synchronize with TF2 before editing an item.")
            try:
                defindex = int(defindex)
            except (TypeError, ValueError):
                raise ValueError("A valid item definition index is required.")
            item = self.schema.by_id.get(defindex)
            original = self.schema.resolved_items.get(defindex)
            if not item or not original:
                raise ValueError("The item definition was not found.")
            if item_fields is not None and not isinstance(item_fields, dict):
                raise ValueError("Item field changes must be an object.")
            if capabilities is not None and not isinstance(capabilities, dict):
                raise ValueError("Capability changes must be an object.")
            if static_attrs is not None and not isinstance(static_attrs, dict):
                raise ValueError("Static attribute changes must be an object.")
            if attributes is not None and not isinstance(attributes, dict):
                raise ValueError("Attribute changes must be an object.")

            key = str(defindex)
            normalized_fields = {}
            for field, raw_value in (item_fields or {}).items():
                if field not in EDITABLE_ITEM_FIELDS:
                    raise ValueError("Unsupported item field: %s" % field)
                value = str(raw_value or "").strip()
                if len(value) > 512 or any(ord(char) < 32 for char in value):
                    raise ValueError("Item field values must be under 512 characters and contain no control characters.")
                normalized_fields[field] = value
            normalized_capabilities = {}
            original_capabilities = original.get("capabilities")
            original_capabilities = original_capabilities if isinstance(original_capabilities, dict) else {}
            for field, raw_value in (capabilities or {}).items():
                if not isinstance(field, str) or not re.fullmatch(r"[A-Za-z0-9_]+", field):
                    raise ValueError("Capability keys may contain only letters, numbers, and underscores.")
                if field not in original_capabilities and field not in CAPABILITY_KEYS:
                    raise ValueError("That capability was not found in this item or the supported capability list.")
                value = str(raw_value).strip()
                if value not in ("0", "1"):
                    raise ValueError("Capability values must be 0 or 1.")
                normalized_capabilities[field] = value
            normalized_static_attrs = {}
            original_static_attrs = original.get("static_attrs")
            original_static_attrs = original_static_attrs if isinstance(original_static_attrs, dict) else {}
            for field, raw_value in (static_attrs or {}).items():
                if field != "is marketable":
                    raise ValueError("Only the is marketable static attribute can be edited directly.")
                value = str(raw_value).strip()
                if value not in ("0", "1"):
                    raise ValueError("The is marketable value must be 0 or 1.")
                normalized_static_attrs[field] = value

            original_attributes = original.get("attributes")
            original_attributes = original_attributes if isinstance(original_attributes, dict) else {}
            attribute_definitions = {
                definition.get("name"): definition
                for definition in self.schema.attribute_definitions
                if definition.get("name")
            }
            normalized_attributes = {}
            for field, raw_value in (attributes or {}).items():
                if not isinstance(field, str) or field not in attribute_definitions:
                    raise ValueError("Choose an attribute from the local TF2 schema.")
                if not isinstance(raw_value, dict) or set(raw_value) != {"value"}:
                    raise ValueError("Attribute changes must contain a value.")
                value = str(raw_value["value"]).strip()
                if (not value or len(value) > 512 or
                        any(ord(char) < 32 for char in value)):
                    raise ValueError("Attribute values must be non-empty, under 512 characters, and contain no control characters.")
                definition = attribute_definitions[field]
                if definition.get("stored_as_integer") == "1" and not re.fullmatch(r"[+-]?\d+", value):
                    raise ValueError("This attribute stores an integer; enter a whole-number value.")
                original_value = original_attributes.get(field)
                attribute_value = dict(original_value) if isinstance(original_value, dict) else {}
                attribute_value["attribute_class"] = definition.get("attribute_class") or field
                attribute_value["value"] = value
                normalized_attributes[field] = attribute_value

            draft = dict(self.drafts.get(key) or {})
            field_changes = dict(draft.get("item_fields") or {})
            for field, value in normalized_fields.items():
                if value == str(original.get(field) or "").strip():
                    field_changes.pop(field, None)
                else:
                    field_changes[field] = value
            if field_changes:
                draft["item_fields"] = field_changes
            else:
                draft.pop("item_fields", None)

            capability_changes = dict(draft.get("capabilities") or {})
            for field, value in normalized_capabilities.items():
                if str(original_capabilities.get(field, "")) == value:
                    capability_changes.pop(field, None)
                else:
                    capability_changes[field] = value
            if capability_changes:
                draft["capabilities"] = capability_changes
            else:
                draft.pop("capabilities", None)
            static_changes = dict(draft.get("static_attrs") or {})
            for field, value in normalized_static_attrs.items():
                if str(original_static_attrs.get(field, "")) == value:
                    static_changes.pop(field, None)
                else:
                    static_changes[field] = value
            if static_changes:
                draft["static_attrs"] = static_changes
            else:
                draft.pop("static_attrs", None)
            attribute_changes = dict(draft.get("attributes") or {})
            for field, value in normalized_attributes.items():
                original_value = original_attributes.get(field)
                if (isinstance(original_value, dict) and
                        str(original_value.get("value", "")).strip() == value["value"]):
                    attribute_changes.pop(field, None)
                else:
                    attribute_changes[field] = value
            if attribute_changes:
                draft["attributes"] = attribute_changes
            else:
                draft.pop("attributes", None)
            if not draft:
                self.drafts.pop(key, None)
                draft = {}
            else:
                self.drafts[key] = draft

            self.schema.apply_item_patch(defindex, draft)
            self._save_json(self.drafts_path, self.drafts)
            return item

    def revert_item(self, defindex):
        with self.lock:
            if not self.schema:
                raise RuntimeError("Synchronize with TF2 before reverting item changes.")
            try:
                defindex = int(defindex)
            except (TypeError, ValueError):
                raise ValueError("A valid item definition index is required.")
            if defindex not in self.schema.by_id:
                raise ValueError("The item definition was not found.")
            key = str(defindex)
            if key not in self.drafts:
                return False
            updated_drafts = dict(self.drafts)
            updated_drafts.pop(key)
            self._save_json(self.drafts_path, updated_drafts)
            self.drafts = updated_drafts
            self.schema.reset_item(defindex)
            return True

    def reset_item_section(self, defindex, section):
        with self.lock:
            if not self.schema:
                raise RuntimeError("Synchronize with TF2 before resetting item sections.")
            try:
                defindex = int(defindex)
            except (TypeError, ValueError):
                raise ValueError("A valid item definition index is required.")
            if defindex not in self.schema.by_id:
                raise ValueError("The item definition was not found.")

            if not isinstance(section, str):
                raise ValueError("A valid item section is required.")
            sound_field = section[6:] if section.startswith("sound:") else None
            section_fields = {
                "type": {"item_fields": {"item_type_name"}},
                "sounds": {"item_fields": set(TF2_SOUND_FIELDS)},
                "attributes": {"attributes": None, "properties": None},
                "capabilities": {"capabilities": None, "static_attrs": {"is marketable"}},
            }
            draft = dict(self.drafts.get(str(defindex)) or {})
            if section == "attributes":
                section_fields["attributes"]["static_attrs"] = (
                    set((draft.get("static_attrs") or {})) - {"is marketable"}
                )
            if sound_field is not None:
                if sound_field not in TF2_SOUND_FIELDS:
                    raise ValueError("Unsupported item sound field.")
                fields = {"item_fields": {sound_field}}
            elif section in section_fields:
                fields = section_fields[section]
            else:
                raise ValueError("Unknown item section.")
            key = str(defindex)
            key = str(defindex)
            for draft_section, names in fields.items():
                if names is None:
                    draft.pop(draft_section, None)
                    continue
                changes = dict(draft.get(draft_section) or {})
                for name in names:
                    changes.pop(name, None)
                if changes:
                    draft[draft_section] = changes
                else:
                    draft.pop(draft_section, None)

            if draft:
                self.drafts[key] = draft
            else:
                self.drafts.pop(key, None)
            self.schema.reset_item(defindex)
            for draft_section in ("attributes", "static_attrs"):
                changes = draft.get(draft_section)
                if changes:
                    self.schema.by_id[defindex][draft_section].update(changes)
            properties = draft.get("properties")
            if properties:
                self.schema.by_id[defindex]["properties"].update(properties)
            self.schema.apply_item_patch(defindex, draft)
            self._save_json(self.drafts_path, self.drafts)
            return self.schema.by_id[defindex]

    def create_block(self, source_id, title, selections, custom_properties=None):
        with self.lock:
            if not self.schema:
                raise RuntimeError("Synchronize with TF2 before creating attribute blocks.")
            try:
                source_id = int(source_id)
            except (TypeError, ValueError):
                raise ValueError("A valid source item definition is required.")
            source = self.schema.by_id.get(source_id)
            if not source:
                raise ValueError("The source item definition was not found.")
            if not isinstance(selections, dict):
                raise ValueError("Block selections must be a JSON object.")
            title = str(title or "").strip()[:100]
            if not title:
                raise ValueError("Enter a name for this reusable block.")
            patch = {}
            for section in ("attributes", "static_attrs"):
                keys = selections.get(section, [])
                if not isinstance(keys, list):
                    raise ValueError("%s selections must be a list." % section)
                available = source.get(section) or {}
                chosen = {}
                for key in keys:
                    if not isinstance(key, str) or key not in available:
                        raise ValueError("Selected %s field was not present on the source item." % section)
                    chosen[key] = available[key]
                if chosen:
                    patch[section] = chosen
            properties = {}
            selected_properties = selections.get("properties", [])
            if not isinstance(selected_properties, list):
                raise ValueError("Compatibility property selections must be a list.")
            available_properties = source.get("properties") or {}
            for key in selected_properties:
                if not isinstance(key, str) or key not in available_properties:
                    raise ValueError("Selected compatibility property was not present on the source item.")
                properties[key] = available_properties[key]
            for key, value in (custom_properties or {}).items():
                if not isinstance(key, str) or not re.search(r"(compat|pyro|vision|assist)", key, re.IGNORECASE):
                    raise ValueError("Custom properties must be compatibility, Pyroland, vision, or assist fields.")
                properties[key] = str(value)
            if properties:
                patch["properties"] = properties
            if not patch:
                raise ValueError("Select at least one attribute or compatibility property for this block.")
            block = {
                "id": uuid.uuid4().hex,
                "title": title,
                "source_id": source_id,
                "source_name": source["name"],
                "patch": patch,
            }
            self.blocks.append(block)
            self._save_json(self.blocks_path, self.blocks)
            return block

    def apply_block(self, block_id, target_ids):
        with self.lock:
            if not self.schema:
                raise RuntimeError("Synchronize with TF2 before applying attribute blocks.")
            block = next((entry for entry in self.blocks if entry.get("id") == block_id), None)
            if not block:
                raise ValueError("The reusable block was not found.")
            if not isinstance(target_ids, list) or not target_ids:
                raise ValueError("Select one or more target items before applying a block.")
            if len(target_ids) > 5000:
                raise ValueError("Apply blocks to at most 5,000 items at a time.")
            normalized_ids = []
            for target in target_ids:
                try:
                    target_id = int(target)
                except (TypeError, ValueError):
                    raise ValueError("Target item definition indices must be integers.")
                if target_id not in self.schema.by_id:
                    raise ValueError("Target item definition %d was not found." % target_id)
                normalized_ids.append(target_id)
            patch = block.get("patch") or {}
            for target_id in set(normalized_ids):
                key = str(target_id)
                draft = self.drafts.setdefault(key, {})
                item = self.schema.by_id[target_id]
                for section in ("attributes", "static_attrs", "properties"):
                    changes = patch.get(section) or {}
                    if not changes:
                        continue
                    if section == "properties":
                        item["properties"] = dict(item.get("properties") or {})
                        item["properties"].update(changes)
                    else:
                        item[section] = dict(item.get(section) or {})
                        item[section].update(changes)
                    draft.setdefault(section, {}).update(changes)
            self._save_json(self.drafts_path, self.drafts)
            return len(set(normalized_ids))

    def choose_schema_file(self):
        try:
            import tkinter
            from tkinter import filedialog

            root = tkinter.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            try:
                return filedialog.askopenfilename(
                    parent=root,
                    title="Open a saved TF2 items_game schema copy",
                    filetypes=(("TF2 schema text", "*.txt"), ("All files", "*.*")),
                )
            finally:
                root.destroy()
        except Exception as error:
            raise RuntimeError(
                "The native file picker is unavailable (%s)." % error
            ) from error

    def choose_export_path(self):
        try:
            import tkinter
            from tkinter import filedialog

            root = tkinter.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            try:
                return filedialog.asksaveasfilename(
                    parent=root,
                    title="Save a separate TF2 schema copy",
                    initialdir=os.path.dirname(self.export_path()),
                    initialfile="items_game.workshop.txt",
                    defaultextension=".txt",
                    filetypes=(("TF2 schema text", "*.txt"), ("All files", "*.*")),
                )
            finally:
                root.destroy()
        except Exception as error:
            raise RuntimeError(
                "The native save dialog is unavailable (%s)." % error
            ) from error

    def load_schema_copy(self, source_path):
        with self.lock:
            if not self.files:
                raise RuntimeError("Synchronize with TF2 before opening a schema copy.")
            base_schema = getattr(self, "base_schema", None)
            if not base_schema:
                raise RuntimeError("Synchronize with TF2 before opening a schema copy.")
            if self.job["state"] == "scanning":
                raise RuntimeError("Wait for TF2 synchronization to finish before opening a schema copy.")
            source_path = os.path.abspath(os.path.expanduser(str(source_path or "").strip().strip('"')))
            if not os.path.isfile(source_path):
                raise ValueError("The selected schema file does not exist.")
            with open(source_path, "rb") as source:
                source_bytes = source.read()
            imported_schema = Schema(self.files, source_bytes=source_bytes)
            imported_changes = self._schema_copy_changes(base_schema, imported_schema)
            updated_drafts = {
                item_id: dict(patch) for item_id, patch in self.drafts.items()
            }
            for item_id, patch in imported_changes.items():
                draft = updated_drafts.setdefault(item_id, {})
                for section, values in patch.items():
                    draft[section] = {**(draft.get(section) or {}), **values}
            schema = Schema(self.files, source_bytes=base_schema.source_bytes)
            self._overlay_drafts(schema, updated_drafts)
            self._save_json(self.drafts_path, updated_drafts)
            self.drafts = updated_drafts
            self.schema = schema
            self.schema_source = source_path
            self.job = {
                "state": "ready",
                "message": "Imported %d changed item definitions from schema copy against the current TF2 schema."
                % len(imported_changes),
                "error": "",
            }
        return {
            "path": source_path,
            "item_count": len(schema.items),
            "draft_count": len(updated_drafts),
            "imported_item_count": len(imported_changes),
        }

    @staticmethod
    def _schema_copy_changes(base_schema, imported_schema):
        changes_by_item = {}
        item_fields = ("item_type_name", *TF2_SOUND_FIELDS)
        for defindex in base_schema.by_id.keys() & imported_schema.by_id.keys():
            base = base_schema.resolved_items[defindex]
            imported = imported_schema.resolved_items[defindex]
            patch = {}
            changed_fields = {
                field: str(imported.get(field) or "").strip()
                for field in item_fields
                if str(imported.get(field) or "").strip() != str(base.get(field) or "").strip()
            }
            if changed_fields:
                patch["item_fields"] = changed_fields

            for section in ("attributes", "capabilities"):
                base_values = base.get(section)
                imported_values = imported.get(section)
                base_values = base_values if isinstance(base_values, dict) else {}
                imported_values = imported_values if isinstance(imported_values, dict) else {}
                value_changes = {
                    key: value for key, value in imported_values.items()
                    if base_values.get(key) != value
                }
                if value_changes:
                    patch[section] = value_changes

            base_static = base.get("static_attrs")
            imported_static = imported.get("static_attrs")
            base_static = base_static if isinstance(base_static, dict) else {}
            imported_static = imported_static if isinstance(imported_static, dict) else {}
            if imported_static.get("is marketable") != base_static.get("is marketable") and (
                "is marketable" in imported_static
            ):
                patch["static_attrs"] = {
                    "is marketable": imported_static["is marketable"]
                }

            base_properties = base_schema.by_id[defindex].get("properties") or {}
            imported_properties = imported_schema.by_id[defindex].get("properties") or {}
            property_changes = {
                key: value for key, value in imported_properties.items()
                if base_properties.get(key) != value
            }
            if property_changes:
                patch["properties"] = property_changes

            if patch:
                changes_by_item[str(defindex)] = patch
        return changes_by_item

    def export_draft_copy(self, destination=None):
        with self.lock:
            if not self.schema:
                raise RuntimeError("Synchronize with TF2 before exporting a schema copy.")
            destination = os.path.abspath(destination or self.export_path())
            source_dir = os.path.abspath(self.tf_dir)
            try:
                if os.path.commonpath((destination, source_dir)) == source_dir:
                    raise ValueError("The export copy must remain outside the TF2 installation.")
            except ValueError as error:
                if "export copy" in str(error):
                    raise
            os.makedirs(os.path.dirname(destination), exist_ok=True)
            base_schema = getattr(self, "base_schema", None) or self.schema
            output = export_copy(base_schema.source_bytes, self.drafts)
            temporary = destination + ".tmp"
            with open(temporary, "wb") as target:
                target.write(output)
            os.replace(temporary, destination)
            return destination
