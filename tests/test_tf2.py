import os
import struct
import tempfile
import threading
import unittest
import zlib
from types import SimpleNamespace
from unittest.mock import patch

from schema_workshop.tf2 import Schema, TF2Files, VPK, decode_text, decode_vtf, parse_kv, parse_localization
from schema_workshop.editing import export_copy
from schema_workshop.tf2 import _item_category
from schema_workshop.app import Workshop


class KeyValuesTests(unittest.TestCase):
    def test_nested_keyvalues_and_english_localization(self):
        parsed = parse_kv('"items_game" { "items" { "42" { "item_name" "#TF_Test" } } }')
        self.assertEqual(parsed["items_game"]["items"]["42"]["item_name"], "#TF_Test")
        localized = parse_localization('"lang" { "Tokens" { "TF_Test" "Translated Name" } }')
        self.assertEqual(localized["tf_test"], "Translated Name")


class SchemaEditingTests(unittest.TestCase):
    SOURCE = (
        '"items_game"\n{\n'
        '\t"items"\n\t{\n'
        '\t\t"42"\n\t\t{\n'
        '\t\t\t"name"\t\t"test_item"\n'
        '\t\t\t"item_type_name"\t\t"#Old_Type"\n'
        '\t\t\t"drop_sound"\t\t"Old_Drop"\n'
        '\t\t\t"capabilities"\n\t\t\t{\n'
        '\t\t\t\t"can_be_traded"\t\t"1"\n'
        '\t\t\t}\n'
        '\t\t\t"static_attrs"\n\t\t\t{\n'
        '\t\t\t\t"is marketable"\t\t"1"\n'
        '\t\t\t}\n'
        '\t\t\t"attributes"\n\t\t\t{\n'
        '\t\t\t\t"damage bonus" { "attribute_class" "mult_dmg" "value" "1.1" }\n'
        '\t\t\t}\n'
        '\t\t}\n\t}\n}\n'
    ).encode("utf-8")

    def test_export_copy_merges_blocks_without_modifying_input(self):
        source_before = self.SOURCE[:]
        exported = export_copy(self.SOURCE, {
            "42": {
                "attributes": {
                    "damage bonus": {"attribute_class": "mult_dmg", "value": "1.2"},
                    "move speed bonus": {"attribute_class": "mult_move_speed", "value": "1.05"},
                },
                "properties": {"pyroland_compat": "1"},
                "item_fields": {
                    "item_type_name": "New Hat",
                    "drop_sound": "New_Drop",
                },
                "capabilities": {"can_be_traded": "0"},
                "static_attrs": {"is marketable": "0"},
            }
        })
        item = parse_kv(exported.decode("utf-8"))["items_game"]["items"]["42"]
        self.assertEqual(item["attributes"]["damage bonus"]["value"], "1.2")
        self.assertEqual(item["attributes"]["move speed bonus"]["value"], "1.05")
        self.assertEqual(item["pyroland_compat"], "1")
        self.assertEqual(item["item_type_name"], "New Hat")
        self.assertEqual(item["drop_sound"], "New_Drop")
        self.assertEqual(item["capabilities"]["can_be_traded"], "0")
        self.assertEqual(item["static_attrs"]["is marketable"], "0")
        self.assertEqual(self.SOURCE, source_before)

    def test_export_copy_preserves_utf16_and_other_definitions(self):
        text = self.SOURCE.decode("utf-8").replace('"42"', '"42"', 1)
        source = b"\xff\xfe" + text.encode("utf-16-le")
        exported = export_copy(source, {"42": {"properties": {"assist_compat": "1"}}})
        self.assertTrue(exported.startswith(b"\xff\xfe"))
        parsed = parse_kv(exported.decode("utf-16"))["items_game"]["items"]["42"]
        self.assertEqual(parsed["assist_compat"], "1")

    def test_export_preserves_item_type_localization_token(self):
        exported = export_copy(self.SOURCE, {
            "42": {"item_fields": {"item_type_name": "#TF_Wearable_FacialHair"}}
        })
        item = parse_kv(exported.decode("utf-8"))["items_game"]["items"]["42"]
        self.assertEqual(item["item_type_name"], "#TF_Wearable_FacialHair")


class CategoryTests(unittest.TestCase):
    def test_editor_data_includes_item_types_from_the_full_schema(self):
        workshop = Workshop.__new__(Workshop)
        workshop.lock = threading.RLock()
        workshop.schema = SimpleNamespace(
            items=[
                {
                    "defindex": 1, "category": "cosmetics", "type_value": "#TF_Hat", "type": "Hat",
                    "name": "First Hat", "metadata": {"name": "first_hat"}, "image_inventory": "",
                    "sounds": {"drop_sound": "Shared.Sound"},
                },
                {
                    "defindex": 2, "category": "weapons", "type_value": "#TF_Weapon", "type": "Weapon",
                    "name": "Weapon", "metadata": {"name": "weapon"}, "image_inventory": "weapon/icon",
                    "sounds": {"equip_sound": "Weapon.Sound", "drop_sound": "Shared.Drop"},
                },
                {
                    "defindex": 3, "category": "cosmetics", "type_value": "#TF_Hat", "type": "Hat",
                    "name": "Icon Hat", "metadata": {"name": "icon_hat"}, "image_inventory": "hat/icon",
                    "sounds": {"drop_sound": "Shared.Sound"},
                },
                {
                    "defindex": 4, "category": "tools", "type_value": "#TF_NoiseMaker", "type": "Noise Maker",
                    "name": "Noise Maker - Example",
                    "metadata": {"name": "Halloween Noise Maker - Example"},
                    "image_inventory": "noise_maker/icon",
                    "sounds": {"mouse_pressed_sound": "NoiseMaker.Only", "drop_sound": "Shared.Drop"},
                },
            ],
            attribute_definitions=[],
        )
        workshop.drafts = {}
        workshop.schema_source = ""
        workshop.user_dir = ""

        data = workshop.editor_data()

        self.assertEqual(
            data["item_types"],
            [
                {"value": "#TF_Hat", "label": "Hat"},
                {"value": "#TF_NoiseMaker", "label": "Noise Maker"},
                {"value": "#TF_Weapon", "label": "Weapon"},
            ],
        )
        self.assertEqual(
            data["sound_item_examples"]["Shared.Sound"],
            {
                "defindex": 3,
                "name": "Icon Hat",
                "image_inventory": "hat/icon",
                "field": "drop_sound",
            },
        )
        self.assertEqual(
            data["sound_item_examples"]["Weapon.Sound"]["defindex"],
            2,
        )
        self.assertNotIn("NoiseMaker.Only", data["sound_references"])
        self.assertNotIn("NoiseMaker.Only", data["sound_item_examples"])
        self.assertIn("Shared.Drop", data["sound_references"])
        self.assertEqual(data["sound_item_examples"]["Shared.Drop"]["defindex"], 2)
        self.assertEqual(
            data["sound_fields_used"],
            ["drop_sound", "equip_sound", "mouse_pressed_sound"],
        )

    def test_mannual_style_item_categories(self):
        self.assertEqual(_item_category({"item_slot": "head"}, "Cosmetic"), "cosmetics")
        self.assertEqual(
            _item_category({"item_slot": "head", "holiday_restriction": "halloween_or_fullmoon"}, "Cosmetic"),
            "halloween restricted",
        )
        self.assertEqual(_item_category({"item_slot": "misc"}, "Tournament Medal"), "tournament medals")
        self.assertEqual(_item_category({"item_slot": "misc"}, "Community Medal"), "community medals")
        self.assertEqual(_item_category({"item_slot": "misc"}, "Func_Medal"), "other medals")
        self.assertEqual(_item_category({"item_slot": "taunt"}, ""), "taunts")
        self.assertEqual(_item_category({"item_slot": "primary", "baseitem": "1"}, ""), "stock weapons")
        self.assertEqual(_item_category({"item_slot": "primary"}, ""), "weapons")
        self.assertEqual(_item_category({"item_class": "tool"}, ""), "tools")

    def test_workshop_items_can_be_scoped_to_one_category(self):
        workshop = Workshop.__new__(Workshop)
        workshop.lock = threading.RLock()
        workshop.drafts = {}
        workshop.schema = SimpleNamespace(items=[
            {"defindex": 1, "category": "cosmetics"},
            {"defindex": 2, "category": "halloween restricted"},
            {"defindex": 3, "category": "tournament medals"},
            {"defindex": 4, "category": "community medals"},
        ])

        self.assertEqual([item["defindex"] for item in workshop.items("cosmetics")], [1])
        self.assertEqual(
            [item["defindex"] for item in workshop.items("tournament medals")], [3]
        )
        self.assertEqual(
            [item["defindex"] for item in workshop.items("halloween restricted")], [2]
        )
        self.assertEqual(len(workshop.items()), 4)

    def test_ui_fonts_are_served_only_from_selected_tf2_resource_folder(self):
        with tempfile.TemporaryDirectory() as folder:
            resource = os.path.join(folder, "resource")
            os.makedirs(resource)
            with open(os.path.join(resource, "tf2build.ttf"), "wb") as target:
                target.write(b"local font")
            workshop = Workshop.__new__(Workshop)
            workshop.lock = threading.RLock()
            workshop.tf_dir = folder

            self.assertEqual(workshop.ui_font("tf2build.ttf"), b"local font")
            with self.assertRaises(ValueError):
                workshop.ui_font("tflogo.ttf")
            with self.assertRaises(ValueError):
                workshop.ui_font("..\\secret.ttf")

    def test_uses_the_actual_logo_from_steam_artwork_cache(self):
        with tempfile.TemporaryDirectory() as folder:
            logo_path = os.path.join(folder, "appcache", "librarycache", "440")
            os.makedirs(logo_path)
            with open(os.path.join(logo_path, "logo.png"), "wb") as target:
                target.write(b"official cached logo")
            workshop = Workshop.__new__(Workshop)
            with patch("schema_workshop.app._steam_roots", return_value=[folder]):
                self.assertEqual(workshop.tf2_logo(), b"official cached logo")


class ReusableBlockTests(unittest.TestCase):
    def test_block_applies_to_targets_and_exports_outside_game_folder(self):
        source_text = (
            '"items_game" { "items" { '
            '"42" { "name" "source" "attributes" { "damage bonus" { "value" "1.1" } } } '
            '"43" { "name" "target" } } }'
        ).encode("utf-8")
        source = {
            "defindex": 42,
            "name": "Source Item",
            "attributes": {"damage bonus": {"value": "1.1"}, "other": {"value": "2"}},
            "static_attrs": {"set item tint RGB": "123"},
            "properties": {"pyroland_compat": "1"},
        }
        target = {
            "defindex": 43,
            "name": "Target Item",
            "attributes": {},
            "static_attrs": {},
            "properties": {},
        }
        schema = SimpleNamespace(
            items=[source, target],
            by_id={42: source, 43: target},
            attribute_definitions=[],
            source_bytes=source_text,
        )
        with tempfile.TemporaryDirectory() as folder:
            workshop = Workshop.__new__(Workshop)
            workshop.user_dir = folder
            workshop.tf_dir = os.path.join(folder, "game")
            os.makedirs(workshop.tf_dir)
            workshop.blocks_path = os.path.join(folder, "blocks.json")
            workshop.drafts_path = os.path.join(folder, "drafts.json")
            workshop.blocks = []
            workshop.drafts = {}
            workshop.schema = schema
            workshop.lock = threading.RLock()
            block = workshop.create_block(
                42,
                "Pyroland hat block",
                {"attributes": ["damage bonus"], "static_attrs": [], "properties": ["pyroland_compat"]},
            )
            applied = workshop.apply_block(block["id"], [43])
            self.assertEqual(applied, 1)
            self.assertEqual(target["attributes"]["damage bonus"]["value"], "1.1")
            self.assertEqual(target["properties"]["pyroland_compat"], "1")
            output_path = workshop.export_draft_copy(
                os.path.join(folder, "somewhere", "my_schema.txt")
            )
            self.assertEqual(output_path, os.path.join(folder, "somewhere", "my_schema.txt"))
            self.assertNotEqual(os.path.commonpath((output_path, workshop.tf_dir)), workshop.tf_dir)
            with open(output_path, "rb") as exported:
                exported_root = parse_kv(exported.read().decode("utf-8"))["items_game"]["items"]
            self.assertEqual(exported_root["43"]["attributes"]["damage bonus"]["value"], "1.1")
            self.assertEqual(exported_root["43"]["pyroland_compat"], "1")


class SchemaCopyTests(unittest.TestCase):
    SOURCE = (
        '"items_game" { "items" { "42" { "name" "test_item" '
        '"item_name" "Test Item" } } }'
    ).encode("utf-8")

    def test_save_copy_to_custom_location_without_draft_edits(self):
        with tempfile.TemporaryDirectory() as folder:
            workshop = Workshop.__new__(Workshop)
            workshop.user_dir = folder
            workshop.tf_dir = os.path.join(folder, "game")
            os.makedirs(workshop.tf_dir)
            workshop.schema = SimpleNamespace(source_bytes=self.SOURCE)
            workshop.drafts = {}
            workshop.lock = threading.RLock()
            destination = os.path.join(folder, "exports", "continued", "items_game.txt")

            saved_path = workshop.export_draft_copy(destination)

            self.assertEqual(saved_path, destination)
            with open(saved_path, "rb") as saved:
                self.assertEqual(saved.read(), self.SOURCE)

    def test_save_copy_rejects_destinations_inside_tf2(self):
        with tempfile.TemporaryDirectory() as folder:
            tf_dir = os.path.join(folder, "game")
            os.makedirs(tf_dir)
            workshop = Workshop.__new__(Workshop)
            workshop.tf_dir = tf_dir
            workshop.schema = SimpleNamespace(source_bytes=self.SOURCE)
            workshop.drafts = {}
            workshop.lock = threading.RLock()

            with self.assertRaisesRegex(ValueError, "outside the TF2 installation"):
                workshop.export_draft_copy(os.path.join(tf_dir, "items_game.txt"))

    def test_opening_saved_copy_imports_changes_against_live_schema(self):
        with tempfile.TemporaryDirectory() as folder:
            tf_dir = os.path.join(folder, "game")
            os.makedirs(os.path.join(tf_dir, "resource"))
            os.makedirs(os.path.join(tf_dir, "scripts", "items"))
            with open(os.path.join(tf_dir, "resource", "tf_english.txt"), "w", encoding="utf-8") as target:
                target.write('"lang" { "Tokens" { "test_item" "Test Item" } }')
            with open(os.path.join(tf_dir, "scripts", "items", "items_game.txt"), "wb") as target:
                target.write(SchemaEditingTests.SOURCE)
            files = TF2Files(tf_dir)
            files.index_loose_files()
            base_schema = Schema(files)
            schema_path = os.path.join(folder, "saved", "items_game.txt")
            os.makedirs(os.path.dirname(schema_path))
            schema_text = export_copy(SchemaEditingTests.SOURCE, {
                "42": {
                    "item_fields": {
                        "item_type_name": "Saved Type",
                        "drop_sound": "Saved_Drop",
                    },
                    "capabilities": {"can_be_traded": "0"},
                    "static_attrs": {"is marketable": "0"},
                    "attributes": {
                        "damage bonus": {"attribute_class": "mult_dmg", "value": "1.2"}
                    },
                    "properties": {"pyroland_compat": "1"},
                }
            })
            with open(schema_path, "wb") as target:
                target.write(schema_text)

            workshop = Workshop.__new__(Workshop)
            workshop.files = files
            workshop.tf_dir = tf_dir
            workshop.schema = base_schema
            workshop.base_schema = base_schema
            workshop.schema_source = ""
            workshop.drafts = {
                "42": {
                    "attributes": {
                        "damage bonus": {"attribute_class": "mult_dmg", "value": "1.3"}
                    },
                    "properties": {"assist_compat": "1"},
                }
            }
            workshop.drafts_path = os.path.join(folder, "drafts.json")
            workshop.lock = threading.RLock()
            workshop.job = {"state": "ready", "message": "", "error": ""}
            workshop._save_json(workshop.drafts_path, workshop.drafts)

            result = workshop.load_schema_copy(schema_path)
            self.assertEqual(result["item_count"], 1)
            self.assertEqual(result["imported_item_count"], 1)
            self.assertEqual(result["draft_count"], 1)
            self.assertEqual(workshop.schema.source_bytes, SchemaEditingTests.SOURCE)
            self.assertEqual(workshop.schema.by_id[42]["name"], "Test Item")
            self.assertEqual(workshop.schema.by_id[42]["type"], "Saved Type")
            self.assertEqual(workshop.schema.by_id[42]["sounds"]["drop_sound"], "Saved_Drop")
            self.assertEqual(workshop.schema.by_id[42]["capabilities"]["can_be_traded"], "0")
            self.assertEqual(workshop.schema.by_id[42]["static_attrs"]["is marketable"], "0")
            self.assertEqual(workshop.schema.by_id[42]["attributes"]["damage bonus"]["value"], "1.2")
            self.assertEqual(workshop.schema.by_id[42]["properties"]["assist_compat"], "1")
            self.assertEqual(workshop.schema.by_id[42]["properties"]["pyroland_compat"], "1")
            self.assertEqual(workshop.schema_source, schema_path)
            self.assertEqual(
                workshop.drafts["42"]["item_fields"]["item_type_name"],
                "Saved Type",
            )
            self.assertEqual(
                workshop._load_json(workshop.drafts_path, {}),
                workshop.drafts,
            )
            item = next(item for item in workshop.items() if item["defindex"] == 42)
            self.assertIn("item_type_name", item["changed_fields"]["item_fields"])
            workshop.update_item(42, item_fields={"item_type_name": "Continued Type"})
            continued_path = os.path.join(folder, "next", "continued.txt")
            workshop.export_draft_copy(continued_path)
            with open(continued_path, "rb") as continued:
                continued_schema = parse_kv(continued.read().decode("utf-8"))
            self.assertEqual(
                continued_schema["items_game"]["items"]["42"]["item_type_name"],
                "Continued Type",
            )
            self.assertEqual(
                continued_schema["items_game"]["items"]["42"]["attributes"]["damage bonus"]["value"],
                "1.2",
            )
            self.assertEqual(
                continued_schema["items_game"]["items"]["42"]["assist_compat"],
                "1",
            )
            self.assertEqual(
                continued_schema["items_game"]["items"]["42"]["pyroland_compat"],
                "1",
            )

    def test_invalid_saved_copy_does_not_discard_draft(self):
        with tempfile.TemporaryDirectory() as folder:
            source_path = os.path.join(folder, "invalid.txt")
            with open(source_path, "w", encoding="utf-8") as target:
                target.write('"not_items_game" { }')
            workshop = Workshop.__new__(Workshop)
            workshop.files = SimpleNamespace(read=lambda _path: None)
            workshop.tf_dir = folder
            workshop.schema = SimpleNamespace(source_bytes=b"original")
            workshop.base_schema = SimpleNamespace()
            workshop.schema_source = ""
            workshop.drafts = {"42": {"attributes": {"damage bonus": {"value": "1.1"}}}}
            workshop.drafts_path = os.path.join(folder, "drafts.json")
            workshop.lock = threading.RLock()
            workshop.job = {"state": "ready", "message": "", "error": ""}
            workshop._save_json(workshop.drafts_path, workshop.drafts)

            with self.assertRaises(ValueError):
                workshop.load_schema_copy(source_path)
            self.assertIn("42", workshop.drafts)
            self.assertEqual(workshop.schema.source_bytes, b"original")


class ItemEditTests(unittest.TestCase):
    def test_editing_type_sound_and_capability_tracks_live_schema_differences(self):
        with tempfile.TemporaryDirectory() as tf_dir:
            files = {
                "scripts/items/items_game.txt": (
                    '"items_game" { "prefabs" { "base" { "item_type_name" "#TF_Hat" '
                    '"drop_sound" "Old_Drop" "capabilities" { "nameable" "1" } '
                    '"static_attrs" { "is marketable" "1" "cosmetic_allow_inspect" "0" } '
                    '"first_sale_date" "2010/09/29" } } '
                    '"items" { "42" { "name" "test_hat" "prefab" "base" } } }'
                ),
                "resource/tf_english.txt": (
                    '"lang" { "Tokens" { "TF_Hat" "Helmet" } }'
                ),
            }
            for relative, content in files.items():
                target = os.path.join(tf_dir, *relative.split("/"))
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with open(target, "w", encoding="utf-8") as destination:
                    destination.write(content)
            indexed = TF2Files(tf_dir)
            indexed.index_loose_files()
            schema = Schema(indexed)
            schema.attribute_definitions.append({
                "id": "415",
                "name": "counts as assister is some kind of pet this update is going to be awesome",
                "attribute_class": "counts_as_assister",
                "stored_as_integer": "0",
            })
            schema.attribute_definitions.append({
                "id": "334",
                "name": "bombinomicon effect on death",
                "attribute_class": "bombinomicon_effect_on_death",
                "stored_as_integer": "0",
            })
            schema.attribute_definitions.append({
                "id": "900",
                "name": "test integer attribute",
                "attribute_class": "test_integer_attribute",
                "stored_as_integer": "1",
            })

            with tempfile.TemporaryDirectory() as user_dir:
                workshop = Workshop.__new__(Workshop)
                workshop.user_dir = user_dir
                workshop.tf_dir = tf_dir
                workshop.drafts_path = os.path.join(user_dir, "drafts.json")
                workshop.drafts = {}
                workshop.schema = schema
                workshop.lock = threading.RLock()
                workshop.update_item(
                    42,
                    {"item_type_name": "New Hat", "drop_sound": "New_Drop"},
                    {"nameable": "0"},
                    {"is marketable": "0"},
                )
                edited = workshop.items()[0]
                self.assertEqual(edited["type"], "New Hat")
                self.assertEqual(edited["sounds"]["drop_sound"], "New_Drop")
                self.assertEqual(edited["capabilities"]["nameable"], "0")
                self.assertEqual(edited["static_attrs"]["is marketable"], "0")
                self.assertEqual(edited["metadata"]["first_sale_date"], "2010/09/29")
                self.assertIn("drop_sound", edited["changed_fields"]["item_fields"])
                self.assertIn("item_type_name", edited["changed_fields"]["item_fields"])
                self.assertIn("nameable", edited["changed_fields"]["capabilities"])
                self.assertIn("is marketable", edited["changed_fields"]["static_attrs"])

                assist_attribute = "counts as assister is some kind of pet this update is going to be awesome"
                workshop.update_item(
                    42,
                    attributes={
                        assist_attribute: {"value": "1"},
                        "bombinomicon effect on death": {"value": "1"},
                    },
                )
                assist_item = workshop.items()[0]
                self.assertEqual(assist_item["attributes"][assist_attribute]["value"], "1")
                self.assertEqual(assist_item["attributes"][assist_attribute]["attribute_class"], "counts_as_assister")
                self.assertEqual(
                    assist_item["attributes"]["bombinomicon effect on death"]["attribute_class"],
                    "bombinomicon_effect_on_death",
                )
                self.assertIn(assist_attribute, assist_item["changed_fields"]["attributes"])
                with self.assertRaisesRegex(ValueError, "whole-number"):
                    workshop.update_item(42, attributes={"test integer attribute": {"value": "1.5"}})
                with self.assertRaisesRegex(ValueError, "local TF2 schema"):
                    workshop.update_item(42, attributes={"unknown attribute": {"value": "1"}})

                workshop.reset_item_section(42, "attributes")
                reset_assist = workshop.items()[0]
                self.assertNotIn(assist_attribute, reset_assist["attributes"])
                self.assertNotIn("bombinomicon effect on death", reset_assist["attributes"])
                self.assertEqual(reset_assist["type"], "New Hat")

                reset_sound = workshop.reset_item_section(42, "sound:drop_sound")
                self.assertEqual(reset_sound["sounds"]["drop_sound"], "Old_Drop")
                self.assertEqual(reset_sound["type"], "New Hat")

                workshop.reset_item_section(42, "sounds")
                sounds_reset = workshop.items()[0]
                self.assertEqual(sounds_reset["sounds"]["drop_sound"], "Old_Drop")
                self.assertEqual(sounds_reset["type"], "New Hat")
                self.assertIn("item_type_name", sounds_reset["changed_fields"]["item_fields"])
                self.assertNotIn("drop_sound", sounds_reset["changed_fields"]["item_fields"])

                workshop.reset_item_section(42, "type")
                type_reset = workshop.items()[0]
                self.assertEqual(type_reset["type"], "Helmet")
                self.assertEqual(type_reset["capabilities"]["nameable"], "0")
                self.assertEqual(type_reset["static_attrs"]["is marketable"], "0")

                workshop.update_item(
                    42,
                    {"item_type_name": "Draft Type", "drop_sound": "Draft_Drop"},
                    {"nameable": "0"},
                    {"is marketable": "0"},
                )
                workshop.drafts["42"]["attributes"] = {"draft attribute": {"value": "1"}}
                workshop.drafts["42"]["properties"] = {"pyroland_compat": "1"}
                workshop.drafts["42"]["static_attrs"]["cosmetic_allow_inspect"] = "1"
                schema.by_id[42]["attributes"]["draft attribute"] = {"value": "1"}
                schema.by_id[42]["properties"]["pyroland_compat"] = "1"
                schema.by_id[42]["static_attrs"]["cosmetic_allow_inspect"] = "1"

                workshop.reset_item_section(42, "capabilities")
                capabilities_reset = workshop.items()[0]
                self.assertEqual(capabilities_reset["capabilities"]["nameable"], "1")
                self.assertEqual(capabilities_reset["static_attrs"]["is marketable"], "1")
                self.assertEqual(capabilities_reset["static_attrs"]["cosmetic_allow_inspect"], "1")
                self.assertEqual(capabilities_reset["type"], "Draft Type")

                workshop.reset_item_section(42, "attributes")
                attributes_reset = workshop.items()[0]
                self.assertNotIn("draft attribute", attributes_reset["attributes"])
                self.assertNotIn("pyroland_compat", attributes_reset["properties"])
                self.assertEqual(attributes_reset["static_attrs"]["cosmetic_allow_inspect"], "0")
                self.assertEqual(attributes_reset["type"], "Draft Type")

                workshop.update_item(
                    42,
                    attributes={assist_attribute: {"value": "1"}},
                )
                direct_assist = workshop.items()[0]
                self.assertEqual(direct_assist["attributes"][assist_attribute]["value"], "1")
                exported = export_copy(schema.source_bytes, workshop.drafts)
                exported_game = parse_kv(decode_text(exported))["items_game"]
                self.assertEqual(
                    exported_game["items"]["42"]["attributes"][assist_attribute]["value"],
                    "1",
                )
                workshop.update_item(42, attributes={"bombinomicon effect on death": {"value": "1"}})
                exported = export_copy(schema.source_bytes, workshop.drafts)
                exported_game = parse_kv(decode_text(exported))["items_game"]
                self.assertEqual(
                    exported_game["items"]["42"]["attributes"]["bombinomicon effect on death"]["attribute_class"],
                    "bombinomicon_effect_on_death",
                )

                self.assertTrue(workshop.revert_item(42))
                restored = workshop.items()[0]
                self.assertEqual(restored["type"], "Helmet")
                self.assertEqual(restored["sounds"]["drop_sound"], "Old_Drop")
                self.assertEqual(restored["capabilities"]["nameable"], "1")
                self.assertEqual(restored["static_attrs"]["is marketable"], "1")
                self.assertNotIn("draft attribute", restored["attributes"])
                self.assertNotIn("pyroland_compat", restored["properties"])
                self.assertNotIn(assist_attribute, restored["attributes"])
                self.assertFalse(any(restored["changed_fields"].values()))
                self.assertFalse(workshop.revert_item(42))


class VPKTests(unittest.TestCase):
    def test_reads_embedded_archive_entry(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "test_dir.vpk")
            entry = b"txt\0 \0hello\0" + struct.pack("<IHHIIH", 0, 0, 0x7FFF, 0, 5, 0xFFFF)
            tree = entry + b"\0\0\0"
            with open(path, "wb") as target:
                target.write(struct.pack("<III", 0x55AA1234, 1, len(tree)))
                target.write(tree)
                target.write(b"hello")
            archive = VPK(path)
            self.assertEqual(archive.read("hello.txt"), b"hello")


class VTFTests(unittest.TestCase):
    @staticmethod
    def texture(width, height, image_format, pixels):
        header = bytearray(64)
        header[:4] = b"VTF\0"
        struct.pack_into("<II", header, 4, 7, 2)
        struct.pack_into("<I", header, 12, 64)
        struct.pack_into("<HH", header, 16, width, height)
        struct.pack_into("<H", header, 24, 1)
        struct.pack_into("<i", header, 52, image_format)
        header[56] = 1
        struct.pack_into("<i", header, 57, -1)
        return bytes(header) + pixels

    def test_decodes_rgba_to_png(self):
        png = decode_vtf(self.texture(1, 1, 0, bytes((240, 20, 10, 255))))
        self.assertTrue(png.startswith(b"\x89PNG\r\n\x1a\n"))
        position = 8
        chunks = {}
        while position < len(png):
            length = struct.unpack_from(">I", png, position)[0]
            kind = png[position + 4:position + 8]
            chunks[kind] = png[position + 8:position + 8 + length]
            position += length + 12
        self.assertEqual(zlib.decompress(chunks[b"IDAT"]), b"\0\xf0\x14\x0a\xff")

    def test_decodes_dxt1_icon(self):
        red_565 = (31 << 11)
        block = struct.pack("<HHI", red_565, 0, 0)
        png = decode_vtf(self.texture(4, 4, 13, block))
        self.assertTrue(png.startswith(b"\x89PNG\r\n\x1a\n"))

    def test_uses_vtf_73_high_resolution_resource_offset(self):
        header = bytearray(88)
        header[:4] = b"VTF\0"
        struct.pack_into("<II", header, 4, 7, 3)
        struct.pack_into("<I", header, 12, 88)
        struct.pack_into("<HH", header, 16, 1, 1)
        struct.pack_into("<H", header, 24, 1)
        struct.pack_into("<i", header, 52, 0)
        header[56] = 1
        struct.pack_into("<i", header, 57, 2)
        header[61], header[62] = 1, 1
        struct.pack_into("<I", header, 68, 1)
        header[80:83] = b"\x30\x00\x00"
        struct.pack_into("<I", header, 84, 91)
        png = decode_vtf(bytes(header) + b"\x01\x02\x03" + bytes((240, 20, 10, 255)))
        self.assertTrue(png.startswith(b"\x89PNG\r\n\x1a\n"))


class LocalSchemaTests(unittest.TestCase):
    def test_localization_icon_and_sound_resolution(self):
        with tempfile.TemporaryDirectory() as tf_dir:
            files = {
                "scripts/items/items_game.txt": (
                    '"items_game" { "prefabs" { "base_item" { '
                    '"item_class" "tf_weapon_test" "item_slot" "primary" '
                    '"item_type_name" "TF_Test_Type" "image_inventory" "test/icon" '
                    '"drop_sound" "Test_Drop" "sound_pickup" "Test_Drop" '
                    '"used_by_classes" { "scout" "1" "soldier" "1" } } } '
                    '"items" { "42" { "name" "test_item" "item_name" "#TF_Test_Name" '
                    '"prefab" "base_item" "used_by_classes" { "scout" "1" } } } }'
                ),
                "resource/tf_english.txt": (
                    '"lang" { "Tokens" { "TF_Test_Name" "Localized Test Item" '
                    '"TF_Test_Type" "Test Weapon" } }'
                ),
                "scripts/game_sounds_test.txt": (
                    '"Test_Drop" { "channel" "CHAN_ITEM" "wave" ")ui/test_drop.wav" }'
                ),
            }
            for relative, content in files.items():
                target = os.path.join(tf_dir, *relative.split("/"))
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with open(target, "w", encoding="utf-8") as destination:
                    destination.write(content)
            material = os.path.join(tf_dir, "materials", "test", "icon.vtf")
            sound = os.path.join(tf_dir, "sound", "ui", "test_drop.wav")
            os.makedirs(os.path.dirname(material), exist_ok=True)
            os.makedirs(os.path.dirname(sound), exist_ok=True)
            with open(material, "wb") as target:
                target.write(VTFTests.texture(1, 1, 0, bytes((240, 20, 10, 255))))
            with open(sound, "wb") as target:
                target.write(b"RIFF-test-audio")

            indexed = TF2Files(tf_dir)
            indexed.index_loose_files()
            indexed.parse_sound_definitions()
            schema = Schema(indexed)
            item = schema.by_id[42]
            self.assertEqual(item["name"], "Localized Test Item")
            self.assertEqual(item["type"], "Test Weapon")
            self.assertEqual(item["type_value"], "TF_Test_Type")
            self.assertEqual(item["classes"], ["scout", "soldier"])
            png, material_path = schema.icon(42)
            self.assertTrue(png.startswith(b"\x89PNG\r\n\x1a\n"))
            self.assertEqual(material_path, "materials/test/icon.vtf")
            audio, audio_path = schema.sound(42, "drop_sound")
            self.assertEqual(audio, b"RIFF-test-audio")
            self.assertEqual(audio_path, "sound/ui/test_drop.wav")
            pickup_audio, pickup_path = schema.sound(42, "sound_pickup")
            self.assertEqual(pickup_audio, b"RIFF-test-audio")
            self.assertEqual(pickup_path, "sound/ui/test_drop.wav")
            direct_audio, direct_path = schema.sound_reference("ui/test_drop.wav")
            self.assertEqual(direct_audio, b"RIFF-test-audio")
            self.assertEqual(direct_path, "sound/ui/test_drop.wav")


if __name__ == "__main__":
    unittest.main()
