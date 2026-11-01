"""Loopback-only HTTP server for TF2 Schema Workshop."""

import json
import os
import sys
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import __version__
from .app import ITEM_CATEGORIES, Workshop


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_ROOT = os.path.join(ROOT, "web")
STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/favicon.svg": ("favicon.svg", "image/svg+xml"),
}
APP = None


class Handler(BaseHTTPRequestHandler):
    server_version = "TF2SchemaWorkshop/" + __version__

    def log_message(self, fmt, *args):
        pass

    def _send(self, code, body, content_type="application/json; charset=utf-8", headers=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _json_body(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            raise ValueError("Invalid request body size")
        if length > 1024 * 1024:
            raise ValueError("Request body is too large")
        try:
            value = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, UnicodeDecodeError):
            raise ValueError("Request body must be valid JSON")
        if not isinstance(value, dict):
            raise ValueError("Request body must be a JSON object")
        return value

    def do_GET(self):
        url = urllib.parse.urlsplit(self.path)
        path = urllib.parse.unquote(url.path)
        try:
            if path in STATIC_FILES:
                filename, content_type = STATIC_FILES[path]
                with open(os.path.join(WEB_ROOT, filename), "rb") as source:
                    return self._send(200, source.read(), content_type)
            if path == "/api/status":
                return self._send(200, APP.status())
            if path == "/api/logo/tf2":
                logo = APP.tf2_logo()
                if logo is None:
                    return self._send(404, {"error": "The TF2 logo was not found in Steam's local artwork cache."})
                return self._send(200, logo, "image/png", {"Cache-Control": "public, max-age=3600"})
            if path.startswith("/api/font/"):
                filename = path[len("/api/font/"):]
                if "/" in filename or "\\" in filename:
                    return self._send(400, {"error": "Invalid TF2 font name."})
                font = APP.ui_font(filename)
                if font is None:
                    return self._send(404, {"error": "This TF2 UI font was not found in the selected installation."})
                return self._send(200, font, "font/ttf", {"Cache-Control": "public, max-age=3600"})
            if path == "/api/items":
                query = urllib.parse.parse_qs(url.query)
                category = query.get("category", [""])[0]
                if category and category not in {category_id for category_id, _ in ITEM_CATEGORIES}:
                    return self._send(400, {"error": "Unknown item category."})
                items = APP.items(category or None)
                if items is None:
                    return self._send(409, {"error": "Synchronize with TF2 before loading item definitions."})
                return self._send(200, items, headers={"Cache-Control": "no-store"})
            if path == "/api/editor":
                return self._send(200, APP.editor_data())
            if path == "/api/blocks":
                return self._send(200, APP.blocks)
            if path == "/api/icon":
                query = urllib.parse.parse_qs(url.query)
                try:
                    defindex = int(query.get("id", [""])[0])
                except ValueError:
                    return self._send(400, {"error": "A numeric item definition index is required."})
                png, asset_path = APP.icon(defindex)
                if png is None:
                    return self._send(404, {
                        "error": "No decodable backpack icon was found for this item.",
                        "asset_path": asset_path or "",
                    })
                return self._send(200, png, "image/png", {
                    "Cache-Control": "public, max-age=3600",
                    "X-Asset-Path": urllib.parse.quote(asset_path or "", safe="/"),
                })
            if path == "/api/sound":
                query = urllib.parse.parse_qs(url.query)
                reference = query.get("reference", [""])[0].strip()
                if reference:
                    if len(reference) > 512 or any(ord(char) < 32 for char in reference):
                        return self._send(400, {"error": "Invalid sound reference."})
                    data, asset_path = APP.sound_reference(reference)
                else:
                    try:
                        defindex = int(query.get("id", [""])[0])
                    except ValueError:
                        return self._send(400, {"error": "A numeric item definition index or sound reference is required."})
                    field = query.get("field", [""])[0]
                    if field not in ("drop_sound", "equip_sound", "pickup_sound", "sound_pickup", "mouse_pressed_sound"):
                        return self._send(400, {"error": "Unsupported item sound field."})
                    data, asset_path = APP.sound(defindex, field)
                if data is None:
                    return self._send(404, {
                        "error": "No audio file was found for this sound reference.",
                        "asset_path": asset_path or "",
                    })
                extension = os.path.splitext(asset_path or "")[1].lower()
                content_type = {
                    ".wav": "audio/wav",
                    ".mp3": "audio/mpeg",
                    ".ogg": "audio/ogg",
                }.get(extension, "application/octet-stream")
                return self._send(200, data, content_type, {
                    "Cache-Control": "public, max-age=3600",
                    "X-Asset-Path": urllib.parse.quote(asset_path or "", safe="/"),
                })
            return self._send(404, {"error": "Not found."})
        except (OSError, ValueError) as error:
            return self._send(500, {"error": str(error)})
        except Exception as error:
            print("Request failed: %s" % error, file=sys.stderr)
            return self._send(500, {"error": "The local server could not complete this request."})

    def do_POST(self):
        path = urllib.parse.urlsplit(self.path).path
        try:
            body = self._json_body()
            if path == "/api/sync":
                selected = APP.start_sync(body.get("path"))
                return self._send(202, {"tf_dir": selected, "state": "scanning"})
            if path == "/api/blocks":
                block = APP.create_block(
                    body.get("source_id"),
                    body.get("title"),
                    body.get("selections"),
                    body.get("custom_properties"),
                )
                return self._send(201, block)
            if path == "/api/editor/apply":
                count = APP.apply_block(body.get("block_id"), body.get("target_ids"))
                return self._send(200, {"applied": count, "draft_count": APP.status()["draft_count"]})
            if path == "/api/editor/item":
                item = APP.update_item(
                    body.get("defindex"),
                    body.get("item_fields"),
                    body.get("capabilities"),
                    body.get("static_attrs"),
                    body.get("attributes"),
                )
                return self._send(200, {
                    "defindex": item["defindex"],
                    "draft_count": APP.status()["draft_count"],
                })
            if path == "/api/editor/revert":
                reverted = APP.revert_item(body.get("defindex"))
                return self._send(200, {
                    "reverted": reverted,
                    "draft_count": APP.status()["draft_count"],
                })
            if path == "/api/editor/reset-section":
                item = APP.reset_item_section(body.get("defindex"), body.get("section"))
                return self._send(200, {
                    "defindex": item["defindex"],
                    "draft_count": APP.status()["draft_count"],
                })
            if path == "/api/editor/export":
                destination = APP.choose_export_path()
                if not destination:
                    return self._send(200, {"cancelled": True})
                destination = APP.export_draft_copy(destination)
                return self._send(200, {"path": destination})
            if path == "/api/editor/open":
                source_path = body.get("source_path") or APP.choose_schema_file()
                if not source_path:
                    return self._send(200, {"cancelled": True})
                return self._send(200, APP.load_schema_copy(source_path))
            if path == "/api/browse":
                try:
                    import tkinter
                    from tkinter import filedialog
                    root = tkinter.Tk()
                    root.withdraw()
                    root.attributes("-topmost", True)
                    selected = filedialog.askdirectory(
                        parent=root,
                        title="Select your Team Fortress 2 folder or tf folder",
                    )
                    root.destroy()
                except Exception as error:
                    return self._send(501, {
                        "error": "The native folder picker is unavailable (%s). Enter the TF2 path manually." % error
                    })
                return self._send(200, {"path": selected})
            return self._send(404, {"error": "Not found."})
        except ValueError as error:
            return self._send(400, {"error": str(error)})
        except RuntimeError as error:
            return self._send(409, {"error": str(error)})
        except OSError as error:
            return self._send(500, {"error": str(error)})
        except Exception as error:
            print("Request failed: %s" % error, file=sys.stderr)
            return self._send(500, {"error": "The local server could not complete this request."})


class LocalHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main(argv=None):
    global APP
    argv = sys.argv[1:] if argv is None else argv
    APP = Workshop()
    if "--tf" in argv:
        index = argv.index("--tf")
        if index + 1 >= len(argv):
            print("--tf requires a TF2 folder path.", file=sys.stderr)
            return 2
        from .app import normalize_tf_dir
        selected = normalize_tf_dir(argv[index + 1])
        if not selected:
            print("The --tf path is not a valid TF2 installation.", file=sys.stderr)
            return 2
        APP.tf_dir = selected
        APP.settings["tf_dir"] = selected
    server = None
    for port in range(8765, 8795):
        try:
            server = LocalHTTPServer(("127.0.0.1", port), Handler)
            break
        except OSError:
            continue
    if server is None:
        print("Couldn't open a local web server port between 8765 and 8794.", file=sys.stderr)
        return 1
    address = "http://127.0.0.1:%d/" % server.server_address[1]
    print("TF2 Schema Workshop %s" % __version__)
    print("TF2 installation: %s" % (APP.tf_dir or "not detected; use Browse or enter its path"))
    print("Open %s  (Ctrl+C to quit)" % address)
    if "--no-browser" not in argv:
        threading.Timer(0.7, lambda: webbrowser.open(address)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
