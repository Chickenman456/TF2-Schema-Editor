"""Local TF2 schema, localization, VPK, image, and sound support."""

import os
import re
import struct
import zlib
from collections import OrderedDict


_TOKEN = re.compile(r'"((?:[^"\\]|\\.)*)"|([{}])|(//[^\n]*)|([^\s{}"]+)')
_SOUND_EXTENSIONS = (".wav", ".mp3", ".ogg")
_ITEM_SOUND_FIELDS = (
    "drop_sound", "equip_sound", "pickup_sound", "sound_pickup", "mouse_pressed_sound",
)
_SKIP_DIRS = {"custom", "download", "downloads", "cache", "logs", "temp"}
_IMAGE_FORMATS = {
    0: ("RGBA", 4),
    1: ("ABGR", 4),
    2: ("RGB", 3),
    3: ("BGR", 3),
    11: ("ARGB", 4),
    12: ("BGRA", 4),
    16: ("BGRX", 4),
}
_IMAGE_DXT = {13: "DXT1", 14: "DXT3", 15: "DXT5"}
_WEAPON_SLOTS = {"primary", "secondary", "melee", "pda", "pda2", "building", "utility"}


def _item_category(item, item_type):
    restriction = str(item.get("holiday_restriction") or "").casefold()
    if "halloween" in restriction or "fullmoon" in restriction:
        return "halloween restricted"
    slot = str(item.get("item_slot") or "").lower()
    item_class = str(item.get("item_class") or "").lower()
    if slot in ("head", "misc"):
        medal_type = str(item_type or "").casefold()
        if medal_type == "tournament medal":
            return "tournament medals"
        if medal_type == "community medal":
            return "community medals"
        if medal_type == "func_medal":
            return "other medals"
        return "cosmetics"
    if slot == "taunt":
        return "taunts"
    if slot == "action":
        return "stock items" if str(item.get("baseitem") or "") == "1" else "action items"
    if slot in _WEAPON_SLOTS:
        return "stock weapons" if str(item.get("baseitem") or "") == "1" else "weapons"
    if item_class == "tool" or item_class == "supply_crate":
        return "tools"
    return "other"


def _compatibility_properties(item):
    return {
        key: value for key, value in item.items()
        if re.search(r"(compat|pyro|vision|assist)", str(key), re.IGNORECASE)
        and not isinstance(value, dict)
    }


def decode_text(raw):
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16")
    if raw[:3] == b"\xef\xbb\xbf":
        raw = raw[3:]
    return raw.decode("utf-8", "replace")


def _unescape(value):
    return re.sub(r"\\(.)", lambda match: {"n": "\n", "t": "\t", "r": "\r"}.get(match.group(1), match.group(1)), value)


def parse_kv(text):
    root = {}
    stack = [root]
    key = None
    for match in _TOKEN.finditer(text):
        quoted, brace, comment, bare = match.groups()
        if comment:
            continue
        if brace == "{":
            current = stack[-1]
            child = current.get(key)
            if not isinstance(child, dict):
                child = {}
                if key is not None:
                    current[key] = child
            stack.append(child)
            key = None
        elif brace == "}":
            if len(stack) > 1:
                stack.pop()
            key = None
        else:
            value = _unescape(quoted if quoted is not None else bare)
            if key is None:
                key = value
            else:
                if not (value.startswith("[$") and value.endswith("]")):
                    stack[-1].setdefault(key, value)
                key = None
    return root


def parse_localization(text):
    parsed = parse_kv(text)
    lang = parsed.get("lang", parsed)
    tokens = lang.get("Tokens", lang) if isinstance(lang, dict) else {}
    return {str(key).lower(): value for key, value in tokens.items() if isinstance(value, str)}


def _read_cstring(data, offset):
    end = data.find(b"\0", offset)
    if end < 0:
        raise ValueError("Malformed VPK directory tree: missing string terminator")
    return data[offset:end].decode("utf-8", "replace"), end + 1


class VPK:
    def __init__(self, path):
        self.path = path
        self.prefix = path[:-len("_dir.vpk")]
        self.entries = {}
        self.data_offset = 0
        self._handle = None
        self._load()

    def _load(self):
        with open(self.path, "rb") as source:
            header = source.read(28)
            if len(header) < 12:
                raise ValueError("VPK directory file is truncated")
            signature, version, tree_size = struct.unpack_from("<III", header)
            if signature != 0x55AA1234:
                raise ValueError("Not a VPK directory file")
            if version not in (1, 2):
                raise ValueError("Unsupported VPK version %d" % version)
            header_size = 12 if version == 1 else 28
            if len(header) < header_size:
                raise ValueError("VPK directory header is truncated")
            source.seek(header_size)
            tree = source.read(tree_size)
        if len(tree) != tree_size:
            raise ValueError("VPK directory tree is truncated")
        self.data_offset = header_size + tree_size

        offset = 0
        while offset < len(tree):
            extension, offset = _read_cstring(tree, offset)
            if not extension:
                break
            while offset < len(tree):
                folder, offset = _read_cstring(tree, offset)
                if not folder:
                    break
                while offset < len(tree):
                    name, offset = _read_cstring(tree, offset)
                    if not name:
                        break
                    if offset + 18 > len(tree):
                        raise ValueError("VPK directory entry is truncated")
                    _crc, preload_size, archive_index, data_offset, length, _terminator = struct.unpack_from(
                        "<IHHIIH", tree, offset
                    )
                    offset += 18
                    end = offset + preload_size
                    if end > len(tree):
                        raise ValueError("VPK preload data is truncated")
                    preload = tree[offset:end]
                    offset = end
                    relative = (folder + "/" if folder != " " else "") + name + "." + extension
                    self.entries[relative.replace("\\", "/").lower()] = (
                        archive_index, data_offset, length, preload
                    )

    def read(self, relative_path):
        archive, offset, length, preload = self.entries[relative_path.lower()]
        if not length:
            return preload
        if archive == 0x7FFF:
            filename, offset = self.path, offset + self.data_offset
        else:
            filename = "%s_%03d.vpk" % (self.prefix, archive)
        with open(filename, "rb") as source:
            source.seek(offset)
            data = source.read(length)
        if len(data) != length:
            raise OSError("VPK archive entry is truncated: %s" % relative_path)
        return preload + data


class TF2Files:
    def __init__(self, tf_dir):
        self.tf_dir = tf_dir
        self.vpks = []
        self.warnings = []
        self.loose_files = {}
        self.asset_paths = set()
        self.sound_definitions = {}
        for filename in sorted(os.listdir(tf_dir)):
            if filename.lower().endswith("_dir.vpk"):
                full_path = os.path.join(tf_dir, filename)
                try:
                    self.vpks.append(VPK(full_path))
                except (OSError, ValueError, struct.error) as error:
                    self.warnings.append("%s: %s" % (filename, error))

    def read(self, relative_path):
        relative = relative_path.replace("\\", "/").lstrip("/")
        if ".." in relative.split("/"):
            return None
        key = relative.lower()
        loose = self.loose_files.get(key)
        if loose is None:
            candidate = os.path.join(self.tf_dir, *relative.split("/"))
            if os.path.isfile(candidate):
                loose = candidate
        if loose:
            try:
                with open(loose, "rb") as source:
                    return source.read()
            except OSError as error:
                self.warnings.append("%s: %s" % (relative, error))
        for vpk in self.vpks:
            if key in vpk.entries:
                try:
                    return vpk.read(key)
                except OSError as error:
                    self.warnings.append("%s: %s" % (relative, error))
                    return None
        return None

    def index_loose_files(self, progress=None):
        count = 0
        for root, dirs, filenames in os.walk(self.tf_dir):
            dirs[:] = [name for name in dirs if name.lower() not in _SKIP_DIRS]
            for filename in filenames:
                lower = filename.lower()
                if not lower.endswith((".vtf", ".vmt", *_SOUND_EXTENSIONS, ".txt")):
                    continue
                absolute = os.path.join(root, filename)
                relative = os.path.relpath(absolute, self.tf_dir).replace("\\", "/")
                key = relative.lower()
                self.loose_files.setdefault(key, absolute)
                if lower.endswith((".vtf", ".vmt", *_SOUND_EXTENSIONS)) or (
                    key.startswith("scripts/game_sounds") and lower.endswith(".txt")
                ):
                    self.asset_paths.add(key)
                count += 1
                if progress and count % 2000 == 0:
                    progress("Indexing loose files (%d)" % count)
        for vpk in self.vpks:
            for path in vpk.entries:
                if path.endswith((".vtf", ".vmt", *_SOUND_EXTENSIONS)) or (
                    path.startswith("scripts/game_sounds") and path.endswith(".txt")
                ):
                    self.asset_paths.add(path)
        return count

    def parse_sound_definitions(self, progress=None):
        scripts = sorted(path for path in self.asset_paths
                         if path.startswith("scripts/game_sounds") and path.endswith(".txt"))
        for index, path in enumerate(scripts):
            raw = self.read(path)
            if raw is None:
                continue
            try:
                root = parse_kv(decode_text(raw))
            except (UnicodeError, ValueError):
                continue
            self._collect_sound_definitions(root)
            if progress and index and index % 20 == 0:
                progress("Reading sound references (%d/%d)" % (index, len(scripts)))

    def _collect_sound_definitions(self, node):
        if not isinstance(node, dict):
            return
        for name, value in node.items():
            if not isinstance(value, dict):
                continue
            waves = []
            wave = value.get("wave")
            if isinstance(wave, str):
                waves.append(wave)
            rndwave = value.get("rndwave")
            if isinstance(rndwave, dict):
                waves.extend(item for item in rndwave.values() if isinstance(item, str))
            if waves:
                self.sound_definitions[name.lower()] = waves
            self._collect_sound_definitions(value)

    def find_icon(self, inventory_path):
        if not inventory_path:
            return None, None
        material = inventory_path.replace("\\", "/").strip().lstrip("/")
        if material.lower().startswith("materials/"):
            material = material[len("materials/"):]
        material = os.path.splitext(material)[0]
        candidates = ["materials/" + material + ".vtf", "materials/" + material + ".vmt"]
        for path in candidates:
            raw = self.read(path)
            if raw is None:
                continue
            if path.endswith(".vtf"):
                return raw, path
            base = re.search(r'(?im)^\s*\$basetexture\s+"?([^"\s]+)', decode_text(raw))
            if base:
                texture = base.group(1).replace("\\", "/").lstrip("/")
                if texture.lower().startswith("materials/"):
                    texture = texture[len("materials/"):]
                texture_path = "materials/" + os.path.splitext(texture)[0] + ".vtf"
                texture_data = self.read(texture_path)
                if texture_data is not None:
                    return texture_data, texture_path
        return None, candidates[0]

    def find_sound(self, reference):
        if not reference:
            return None, None
        reference = reference.strip().replace("\\", "/").lstrip("/")
        candidates = []
        mapped = self.sound_definitions.get(reference.lower())
        if not mapped and "/" not in reference and not os.path.splitext(reference)[1]:
            return None, None
        refs = mapped if mapped else [reference]
        for ref in refs:
            ref = ref.strip().replace("\\", "/").lstrip("/")
            if ref.startswith(")"):
                ref = ref[1:]
            if ref.lower().startswith("sound/"):
                ref = ref[6:]
            if os.path.splitext(ref)[1]:
                candidates.append("sound/" + ref)
            else:
                candidates.extend("sound/" + ref + ext for ext in _SOUND_EXTENSIONS)
        for path in candidates:
            data = self.read(path)
            if data is not None:
                return data, path
        return None, candidates[0] if candidates else reference


def _rgba_pixel(raw, offset, fmt):
    if fmt == "RGBA":
        return raw[offset:offset + 4]
    if fmt == "BGRA":
        b, g, r, a = raw[offset:offset + 4]
        return bytes((r, g, b, a))
    if fmt == "ABGR":
        a, b, g, r = raw[offset:offset + 4]
        return bytes((r, g, b, a))
    if fmt == "ARGB":
        a, r, g, b = raw[offset:offset + 4]
        return bytes((r, g, b, a))
    if fmt == "BGRX":
        b, g, r, _unused = raw[offset:offset + 4]
        return bytes((r, g, b, 255))
    if fmt == "RGB":
        return raw[offset:offset + 3] + b"\xff"
    if fmt == "BGR":
        b, g, r = raw[offset:offset + 3]
        return bytes((r, g, b, 255))
    raise ValueError("Unsupported VTF image format")


def _color565(value):
    r = ((value >> 11) & 31) * 255 // 31
    g = ((value >> 5) & 63) * 255 // 63
    b = (value & 31) * 255 // 31
    return (r, g, b, 255)


def _dxt_color_block(block, allow_transparency):
    first, second = struct.unpack_from("<HH", block)
    c0, c1 = _color565(first), _color565(second)
    if first > second or not allow_transparency:
        colors = [c0, c1,
                  tuple((2 * c0[i] + c1[i]) // 3 for i in range(3)) + (255,),
                  tuple((c0[i] + 2 * c1[i]) // 3 for i in range(3)) + (255,)]
    else:
        colors = [c0, c1,
                  tuple((c0[i] + c1[i]) // 2 for i in range(3)) + (255,),
                  (0, 0, 0, 0)]
    indices = struct.unpack_from("<I", block, 4)[0]
    return [colors[(indices >> (2 * index)) & 3] for index in range(16)]


def _decode_dxt(data, width, height, fmt):
    output = bytearray(width * height * 4)
    block_size = 8 if fmt == "DXT1" else 16
    for by in range((height + 3) // 4):
        for bx in range((width + 3) // 4):
            offset = (by * ((width + 3) // 4) + bx) * block_size
            block = data[offset:offset + block_size]
            if len(block) != block_size:
                raise ValueError("VTF DXT image data is truncated")
            if fmt == "DXT1":
                colors = _dxt_color_block(block, True)
            else:
                colors = _dxt_color_block(block[8:16], False)
                if fmt == "DXT3":
                    alpha_bits = int.from_bytes(block[:8], "little")
                    alphas = [((alpha_bits >> (4 * i)) & 15) * 17 for i in range(16)]
                else:
                    a0, a1 = block[0], block[1]
                    if a0 > a1:
                        alpha_table = [a0, a1] + [((7 - i) * a0 + i * a1) // 7 for i in range(1, 7)]
                    else:
                        alpha_table = [a0, a1] + [((5 - i) * a0 + i * a1) // 5 for i in range(1, 5)] + [0, 255]
                    alpha_bits = int.from_bytes(block[2:8], "little")
                    alphas = [alpha_table[(alpha_bits >> (3 * i)) & 7] for i in range(16)]
                colors = [color[:3] + (alphas[i],) for i, color in enumerate(colors)]
            for py in range(4):
                y = by * 4 + py
                if y >= height:
                    continue
                for px in range(4):
                    x = bx * 4 + px
                    if x < width:
                        pixel = colors[py * 4 + px]
                        dest = (y * width + x) * 4
                        output[dest:dest + 4] = bytes(pixel)
    return bytes(output)


def _png_chunk(kind, data):
    payload = kind + data
    return struct.pack(">I", len(data)) + payload + struct.pack(">I", zlib.crc32(payload) & 0xFFFFFFFF)


def rgba_to_png(width, height, pixels):
    rows = b"".join(b"\0" + pixels[y * width * 4:(y + 1) * width * 4] for y in range(height))
    return (b"\x89PNG\r\n\x1a\n" +
            _png_chunk(b"IHDR", struct.pack(">2I5B", width, height, 8, 6, 0, 0, 0)) +
            _png_chunk(b"IDAT", zlib.compress(rows, 6)) +
            _png_chunk(b"IEND", b""))


def decode_vtf(raw):
    if len(raw) < 64 or raw[:4] != b"VTF\0":
        raise ValueError("Not a VTF texture")
    major, minor = struct.unpack_from("<II", raw, 4)
    header_size = struct.unpack_from("<I", raw, 12)[0]
    width, height = struct.unpack_from("<HH", raw, 16)
    frames = max(1, struct.unpack_from("<H", raw, 24)[0])
    high_format = struct.unpack_from("<i", raw, 52)[0]
    mip_count = max(1, raw[56])
    low_format = struct.unpack_from("<i", raw, 57)[0]
    low_width, low_height = raw[61], raw[62]
    if not width or not height or width * height > 16_777_216:
        raise ValueError("Invalid or oversized VTF dimensions")
    if header_size > len(raw) or header_size < 64:
        raise ValueError("Invalid VTF header size")

    image_offset = header_size
    has_resource_image_offset = False
    if major == 7 and minor >= 3 and header_size >= 80:
        resource_count = struct.unpack_from("<I", raw, 68)[0]
        if resource_count > 256 or 80 + resource_count * 8 > header_size:
            raise ValueError("Invalid VTF resource table")
        for index in range(resource_count):
            entry = 80 + index * 8
            resource_type = raw[entry:entry + 3]
            if resource_type == b"\x30\x00\x00":
                image_offset = struct.unpack_from("<I", raw, entry + 4)[0]
                has_resource_image_offset = True
                break
    if not has_resource_image_offset and low_format != 0xFFFFFFFF and low_width and low_height:
        if low_format in _IMAGE_FORMATS:
            _, bpp = _IMAGE_FORMATS[low_format]
            image_offset += low_width * low_height * bpp
        elif low_format == 13:
            image_offset += ((low_width + 3) // 4) * ((low_height + 3) // 4) * 8
        elif low_format in (14, 15):
            image_offset += ((low_width + 3) // 4) * ((low_height + 3) // 4) * 16
    for mip in range(mip_count - 1, 0, -1):
        mip_width, mip_height = max(1, width >> mip), max(1, height >> mip)
        if high_format in _IMAGE_FORMATS:
            _, bpp = _IMAGE_FORMATS[high_format]
            image_offset += mip_width * mip_height * bpp * frames
        elif high_format in _IMAGE_DXT:
            block = 8 if high_format == 13 else 16
            image_offset += ((mip_width + 3) // 4) * ((mip_height + 3) // 4) * block * frames
        else:
            raise ValueError("Unsupported VTF image format %d" % high_format)
    if high_format in _IMAGE_FORMATS:
        format_name, bpp = _IMAGE_FORMATS[high_format]
        size = width * height * bpp
        image_data = raw[image_offset:image_offset + size]
        if len(image_data) != size:
            raise ValueError("VTF image data is truncated")
        pixels = b"".join(_rgba_pixel(image_data, i, format_name) for i in range(0, size, bpp))
    elif high_format in _IMAGE_DXT:
        pixels = _decode_dxt(raw[image_offset:], width, height, _IMAGE_DXT[high_format])
    else:
        raise ValueError("Unsupported VTF image format %d" % high_format)
    return rgba_to_png(width, height, pixels)


def _resolve_name(token, localization, fallback):
    if not token:
        return fallback
    key = token[1:] if token.startswith("#") else token
    translated = localization.get(key.lower())
    return translated.strip() if translated and translated.strip() else fallback


def _description(token, localization):
    value = _resolve_name(token, localization, "")
    value = value.replace("\\n", "\n").replace("<br>", "\n").replace("<br/>", "\n")
    return re.sub(r"<[^>]*>", "", value).strip()


def _resolve_item_type(value, localization):
    value = str(value or "").strip()
    if not value:
        return ""
    key = value[1:] if value.startswith("#") else value
    translated = localization.get(key.lower())
    if translated and translated.strip():
        return translated.strip()
    return value[1:].replace("_", " ") if value.startswith("#") else value


def _merge_dicts(parent, child):
    merged = dict(parent)
    for key, value in child.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_dicts(merged[key], value)
        else:
            merged[key] = value
    return merged


class Schema:
    def __init__(self, tf_files, progress=None, source_bytes=None):
        self.files = tf_files
        self._source_bytes = source_bytes
        self.localization = {}
        self.items = []
        self.by_id = {}
        self.raw_items = {}
        self.resolved_items = {}
        self.attribute_definitions = []
        self.source_bytes = None
        self._icon_cache = OrderedDict()
        self._sound_cache = {}
        self._load(progress)

    def _load(self, progress):
        raw_schema = self._source_bytes
        if raw_schema is None:
            raw_schema = self.files.read("scripts/items/items_game.txt")
        if raw_schema is None:
            raise FileNotFoundError("scripts/items/items_game.txt was not found in loose files or VPK archives")
        self.source_bytes = raw_schema
        if progress:
            progress("Parsing items_game.txt")
        parsed = parse_kv(decode_text(raw_schema))
        game = parsed.get("items_game")
        if not isinstance(game, dict) or not isinstance(game.get("items"), dict):
            raise ValueError("items_game.txt does not contain an item definitions section")

        loc_data = self.files.read("resource/tf_english.txt")
        if loc_data is None:
            raise FileNotFoundError("resource/tf_english.txt was not found in loose files or VPK archives")
        self.localization = parse_localization(decode_text(loc_data))
        proto = self.files.read("resource/tf_proto_obj_defs_english.txt")
        if proto:
            self.localization.update(parse_localization(decode_text(proto)))

        prefabs = game.get("prefabs", {})
        prefab_cache = {}

        def resolve_prefab(name, depth=0):
            if name in prefab_cache:
                return prefab_cache[name]
            result = {}
            prefab = prefabs.get(name, {}) if isinstance(prefabs, dict) else {}
            if isinstance(prefab, dict) and depth < 16:
                for parent in str(prefab.get("prefab", "")).split():
                    result = _merge_dicts(result, resolve_prefab(parent, depth + 1))
                result = _merge_dicts(result, prefab)
            prefab_cache[name] = result
            return result

        definitions = game["items"]
        for raw_id, raw_item in definitions.items():
            if not raw_id.isdigit() or not isinstance(raw_item, dict):
                continue
            item = {}
            for parent in str(raw_item.get("prefab", "")).split():
                item = _merge_dicts(item, resolve_prefab(parent))
            item = _merge_dicts(item, raw_item)
            defindex = int(raw_id)
            self.raw_items[defindex] = raw_item
            self.resolved_items[defindex] = item
            internal_name = str(item.get("name") or "").strip()
            token = str(item.get("item_name") or "").strip()
            fallback = _resolve_name("", self.localization, "Item #%d" % defindex)
            if internal_name:
                localized_internal_name = self.localization.get(internal_name.lower())
                if localized_internal_name:
                    fallback = localized_internal_name.strip()
            name = _resolve_name(token, self.localization, fallback)
            if name.startswith("#"):
                name = fallback
            type_value = str(item.get("item_type_name") or "")
            resolved_type = _resolve_item_type(type_value, self.localization)
            classes = item.get("used_by_classes")
            class_names = sorted(key for key, enabled in classes.items()
                                 if str(enabled).lower() not in ("0", "false", "")) if isinstance(classes, dict) else []
            raw_sounds = {field: str(item.get(field) or "").strip()
                          for field in _ITEM_SOUND_FIELDS}
            metadata_keys = (
                "name", "item_name", "item_class", "item_slot", "item_type_name", "item_description",
                "image_inventory", "image_inventory_size_w", "image_inventory_size_h", "drop_sound",
                "equip_sound", "pickup_sound", "sound_pickup", "mouse_pressed_sound", "prefab",
                "baseitem", "equip_region", "equip_regions", "model_player", "capabilities",
                "holiday_restriction", "first_sale_date",
            )
            metadata = {key: item[key] for key in metadata_keys if key in item}
            self.items.append({
                "defindex": defindex,
                "name": name,
                "name_token": token,
                "item_class": str(item.get("item_class") or ""),
                "slot": str(item.get("item_slot") or ""),
                "type": resolved_type,
                "type_value": type_value,
                "category": _item_category(item, resolved_type),
                "description": _description(str(item.get("item_description") or ""), self.localization),
                "classes": class_names,
                "image_inventory": str(item.get("image_inventory") or "").replace("\\", "/"),
                "sounds": raw_sounds,
                "metadata": metadata,
                "capabilities": dict(item.get("capabilities") or {})
                    if isinstance(item.get("capabilities"), dict) else {},
                "attributes": item.get("attributes") if isinstance(item.get("attributes"), dict) else {},
                "static_attrs": item.get("static_attrs") if isinstance(item.get("static_attrs"), dict) else {},
                "properties": _compatibility_properties(item),
            })
        definitions = game.get("attributes", {})
        if isinstance(definitions, dict):
            for attribute_id, definition in definitions.items():
                if not attribute_id.isdigit() or not isinstance(definition, dict):
                    continue
                description_token = str(definition.get("description_string") or "")
                self.attribute_definitions.append({
                    "id": attribute_id,
                    "name": str(definition.get("name") or ""),
                    "attribute_class": str(definition.get("attribute_class") or ""),
                    "effect_type": str(definition.get("effect_type") or ""),
                    "description": _resolve_name(description_token, self.localization, ""),
                    "description_token": description_token,
                    "stored_as_integer": str(definition.get("stored_as_integer") or "0"),
                    "hidden": str(definition.get("hidden") or "0"),
                })
        self.attribute_definitions.sort(key=lambda attribute: (
            attribute["name"].casefold(), int(attribute["id"])
        ))
        self.items.sort(key=lambda item: (item["name"].casefold(), item["defindex"]))
        self.by_id = {item["defindex"]: item for item in self.items}
        if not self.items:
            raise ValueError("No numeric item definitions were found in items_game.txt")

    def apply_item_patch(self, defindex, patch):
        item = self.by_id.get(int(defindex))
        original = self.resolved_items.get(int(defindex))
        if not item or not original:
            raise ValueError("The item definition was not found.")

        item_fields = patch.get("item_fields") or {}
        for field in ("item_type_name",):
            item[field] = str(item_fields.get(field, original.get(field) or ""))
        item["type_value"] = item["item_type_name"]
        item["type"] = _resolve_item_type(item["type_value"], self.localization)

        for field in _ITEM_SOUND_FIELDS:
            item["sounds"][field] = str(item_fields.get(field, original.get(field) or "")).strip()
            self._sound_cache.pop((int(defindex), field), None)

        attributes = original.get("attributes")
        item["attributes"] = dict(attributes) if isinstance(attributes, dict) else {}
        item["attributes"].update(patch.get("attributes") or {})

        item["properties"] = _compatibility_properties(original)
        item["properties"].update(patch.get("properties") or {})

        static_attrs = original.get("static_attrs")
        item["static_attrs"] = dict(static_attrs) if isinstance(static_attrs, dict) else {}
        item["static_attrs"].update(patch.get("static_attrs") or {})

        capabilities = original.get("capabilities")
        item["capabilities"] = dict(capabilities) if isinstance(capabilities, dict) else {}
        item["capabilities"].update(patch.get("capabilities") or {})
        item["metadata"]["capabilities"] = item["capabilities"]

        for field in ("item_type_name",) + _ITEM_SOUND_FIELDS:
            if field in original:
                item["metadata"][field] = item[field] if field == "item_type_name" else item["sounds"][field]
            else:
                item["metadata"].pop(field, None)
        item["category"] = _item_category(original, item["type"])

    def reset_item(self, defindex):
        item = self.by_id.get(int(defindex))
        original = self.resolved_items.get(int(defindex))
        if not item or not original:
            raise ValueError("The item definition was not found.")
        for section in ("attributes", "static_attrs"):
            values = original.get(section)
            item[section] = dict(values) if isinstance(values, dict) else {}
        item["properties"] = _compatibility_properties(original)
        self.apply_item_patch(defindex, {})

    def icon(self, defindex):
        if defindex in self._icon_cache:
            self._icon_cache.move_to_end(defindex)
            return self._icon_cache[defindex]
        item = self.by_id.get(defindex)
        if not item or not item["image_inventory"]:
            return None, None
        raw, path = self.files.find_icon(item["image_inventory"])
        if raw is None:
            return None, path
        try:
            png = decode_vtf(raw)
        except (ValueError, struct.error, IndexError, zlib.error):
            return None, path
        self._icon_cache[defindex] = (png, path)
        self._icon_cache.move_to_end(defindex)
        while len(self._icon_cache) > 96:
            self._icon_cache.popitem(last=False)
        return png, path

    def sound(self, defindex, field):
        item = self.by_id.get(defindex)
        if not item or field not in item["sounds"]:
            return None, None
        key = (defindex, field)
        if key in self._sound_cache:
            return self._sound_cache[key]
        data, path = self.files.find_sound(item["sounds"][field])
        self._sound_cache[key] = (data, path)
        return data, path

    def sound_reference(self, reference):
        return self.files.find_sound(reference)
