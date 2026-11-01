"""Safe, copy-only editing helpers for item definitions in items_game.txt."""

import json
import re

from .tf2 import _TOKEN, decode_text, parse_kv


_COMPATIBILITY_KEY = re.compile(r"(compat|pyro|vision|assist)", re.IGNORECASE)
_ITEM_FIELDS = {
    "item_type_name",
    "drop_sound",
    "equip_sound",
    "pickup_sound",
    "sound_pickup",
    "mouse_pressed_sound",
}


def decode_schema(raw):
    return decode_text(raw)


def encode_schema(text, original):
    if original.startswith(b"\xff\xfe"):
        return b"\xff\xfe" + text.encode("utf-16-le")
    if original.startswith(b"\xfe\xff"):
        return b"\xfe\xff" + text.encode("utf-16-be")
    if original.startswith(b"\xef\xbb\xbf"):
        return b"\xef\xbb\xbf" + text.encode("utf-8")
    return text.encode("utf-8")


def _tokens(text):
    for match in _TOKEN.finditer(text):
        quoted, brace, comment, bare = match.groups()
        if comment:
            continue
        if brace:
            yield (brace, brace, match.start(), match.end())
        else:
            yield ("value", quoted if quoted is not None else bare, match.start(), match.end())


def _definition_spans(text):
    spans = {}
    stack = [{"path": (), "pending": None, "defindex": None, "body_start": None}]
    for kind, value, start, end in _tokens(text):
        frame = stack[-1]
        if kind == "{":
            key = frame["pending"]
            frame["pending"] = None
            parent_path = frame["path"]
            path = parent_path + ((key[0] if key else ""),)
            defindex = None
            body_start = None
            if parent_path == ("items_game", "items") and key and key[0].isdigit():
                defindex = int(key[0])
                body_start = end
            stack.append({
                "path": path,
                "pending": None,
                "defindex": defindex,
                "body_start": body_start,
            })
        elif kind == "}":
            if len(stack) > 1:
                closed = stack.pop()
                if closed["defindex"] is not None:
                    spans[closed["defindex"]] = (closed["body_start"], start)
        elif frame["pending"] is None:
            frame["pending"] = (value, start, end)
        else:
            frame["pending"] = None
    return spans


def _field_spans(body):
    fields = {}
    stack = [{"pending": None, "key_start": None, "field_key": None, "start": None}]
    for kind, value, start, end in _tokens(body):
        frame = stack[-1]
        if kind == "{":
            key = frame["pending"]
            key_start = frame["key_start"]
            frame["pending"] = frame["key_start"] = None
            stack.append({
                "pending": None,
                "key_start": None,
                "field_key": key if len(stack) == 1 else None,
                "start": key_start if len(stack) == 1 else None,
            })
        elif kind == "}":
            if len(stack) > 1:
                closed = stack.pop()
                if closed["field_key"] is not None:
                    fields[closed["field_key"]] = {
                        "start": closed["start"],
                        "end": end,
                        "block": True,
                    }
        elif frame["pending"] is None:
            frame["pending"] = value
            frame["key_start"] = start
        else:
            if len(stack) == 1:
                fields[frame["pending"]] = {
                    "start": frame["key_start"],
                    "end": end,
                    "block": False,
                    "value": value,
                    "value_start": start,
                    "value_end": end,
                }
            frame["pending"] = frame["key_start"] = None
    return fields


def _serialize(value, indent):
    if isinstance(value, dict):
        lines = ["{"]
        child_indent = indent + "\t"
        for key in sorted(value, key=str.casefold):
            child = value[key]
            encoded_key = json.dumps(str(key), ensure_ascii=False)
            if isinstance(child, dict):
                lines.append(child_indent + encoded_key)
                lines.append(child_indent + _serialize(child, child_indent))
            else:
                lines.append(
                    child_indent + encoded_key + "\t\t" +
                    json.dumps(str(child), ensure_ascii=False)
                )
        lines.append(indent + "}")
        return "\n".join(lines)
    return json.dumps(str(value), ensure_ascii=False)


def _make_block(key, value, indent):
    encoded_key = json.dumps(str(key), ensure_ascii=False)
    if isinstance(value, dict):
        return encoded_key + "\n" + indent + _serialize(value, indent)
    return encoded_key + "\t\t" + json.dumps(str(value), ensure_ascii=False)


def _patch_definition(source, defindex, patch, spans):
    span = spans.get(int(defindex))
    if not span:
        raise ValueError("Definition %s was not present in the source schema." % defindex)
    start, end = span
    body = source[start:end]
    fields = _field_spans(body)
    replacements = []
    additions = []

    for section in ("attributes", "static_attrs"):
        changes = patch.get(section) or {}
        if not changes:
            continue
        current = {}
        existing = fields.get(section)
        if existing and existing["block"]:
            parsed = parse_kv('"WorkshopBlock"\n{\n' + body[existing["start"]:existing["end"]] + "\n}")
            block = parsed.get("WorkshopBlock", {})
            values = block.get(section, {}) if isinstance(block, dict) else {}
            if isinstance(values, dict):
                current = values
        current.update(changes)
        line_start = body.rfind("\n", 0, existing["start"] if existing else len(body)) + 1 if existing else None
        key_indent = ""
        if existing:
            key_indent = re.match(r"[ \t]*", body[line_start:]).group(0)
            replacements.append((existing["start"], existing["end"], _make_block(section, current, key_indent)))
        else:
            additions.append((section, current))

    property_changes = patch.get("properties") or {}
    for key, value in property_changes.items():
        if not _COMPATIBILITY_KEY.search(str(key)):
            raise ValueError("Only compatibility-related item properties can be applied as property blocks.")
        existing = fields.get(key)
        if existing and existing["block"]:
            raise ValueError("Compatibility field %s is a block, not a scalar property." % key)
        if existing:
            replacements.append((
                existing["value_start"],
                existing["value_end"],
                json.dumps(str(value), ensure_ascii=False),
            ))
        else:
            additions.append((key, value))

    item_fields = patch.get("item_fields") or {}
    if not isinstance(item_fields, dict):
        raise ValueError("Item field changes must be an object.")
    for key, value in item_fields.items():
        if key not in _ITEM_FIELDS:
            raise ValueError("Unsupported item field: %s" % key)
        existing = fields.get(key)
        if existing and existing["block"]:
            raise ValueError("Item field %s is a block, not a scalar property." % key)
        if existing:
            replacements.append((
                existing["value_start"],
                existing["value_end"],
                json.dumps(str(value), ensure_ascii=False),
            ))
        else:
            additions.append((key, value))

    capability_changes = patch.get("capabilities") or {}
    if not isinstance(capability_changes, dict):
        raise ValueError("Capability changes must be an object.")
    if capability_changes:
        existing = fields.get("capabilities")
        current = {}
        if existing and existing["block"]:
            parsed = parse_kv(
                '"WorkshopBlock"\n{\n' +
                body[existing["start"]:existing["end"]] +
                "\n}"
            )
            block = parsed.get("WorkshopBlock", {})
            values = block.get("capabilities", {}) if isinstance(block, dict) else {}
            if isinstance(values, dict):
                current = values
        current.update(capability_changes)
        if existing:
            line_start = body.rfind("\n", 0, existing["start"]) + 1
            key_indent = re.match(r"[ \t]*", body[line_start:]).group(0)
            replacements.append((
                existing["start"],
                existing["end"],
                _make_block("capabilities", current, key_indent),
            ))
        else:
            additions.append(("capabilities", current))

    for replace_start, replace_end, value in sorted(replacements, reverse=True):
        body = body[:replace_start] + value + body[replace_end:]

    for section, value in additions:
        direct = next(iter(fields.values()), None)
        prop_indent = ""
        if direct:
            line_start = body.rfind("\n", 0, direct["start"]) + 1
            prop_indent = re.match(r"[ \t]*", body[line_start:]).group(0)
        close_line = body.rfind("\n") + 1
        additions_text = prop_indent + _make_block(section, value, prop_indent) + "\n"
        body = body[:close_line] + additions_text + body[close_line:]
    return source[:start] + body + source[end:]


def export_copy(original_bytes, patches):
    text = decode_schema(original_bytes)
    spans = _definition_spans(text)
    for defindex, patch in sorted(patches.items(), key=lambda entry: int(entry[0]), reverse=True):
        text = _patch_definition(text, int(defindex), patch, spans)
    return encode_schema(text, original_bytes)
