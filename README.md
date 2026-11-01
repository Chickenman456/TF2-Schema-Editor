# TF2 Schema Workshop

A standalone, local-first browser for item definitions and assets from your own Team Fortress 2 installation. It is separate from Mannual and does not change or require Mannual.

## Start on Windows

1. Install Python 3.8 or newer if it is not already available.
2. Double-click `run.bat`.
3. In the Workshop tab, press **Sync TF2**. The app attempts to find Steam's TF2 installation automatically.
4. If it is installed in another Steam library, use **Browse** or enter the Team Fortress 2 folder (or its `tf` subfolder), then press **Sync TF2**.

The app opens at `http://127.0.0.1:8765` (or the next available port through `8794`). Close its console window or press Ctrl+C to stop the server. You can also launch from a terminal with:

```powershell
python -m schema_workshop.server
```

The selected TF2 path is saved in `%LOCALAPPDATA%\TF2SchemaWorkshop\settings.json`. Nothing is uploaded; the server listens only on this computer.

### Portable Windows release

The GitHub Releases page can provide a portable ZIP that runs without a separate Python installation:

1. Download and extract `TF2SchemaWorkshop-windows-x64.zip`.
2. Double-click `TF2SchemaWorkshop.exe`.
3. Use **Sync TF2** to index a local Team Fortress 2 installation.

To build the ZIP from source on 64-bit Windows, install Python 3.10 or newer and run `build_windows.bat`. It installs the pinned build-only dependency from `requirements-build.txt` and writes the package to `dist\TF2SchemaWorkshop-windows-x64.zip`. The ZIP includes the runtime license notices and does not include Team Fortress 2 files. Windows may display a SmartScreen warning because the executable is not code-signed.

## Included features

- Steam library detection, manual folder selection, and remembered TF2 path.
- The TF2 Build font is served from the selected local TF2 installation for item names, buttons, previews, and top-bar text. The actual TF2 logo is served from Steam's local artwork cache; no artwork is bundled.
- Local loose-file and VPK indexing, `items_game.txt` parsing, and English localization from loose files or VPKs.
- Item search by translated in-game name, class, slot, category, item type, or existing attribute; sort by item metadata, most/fewest attributes, or year using the schema's `first_sale_date` (items without that date sort last).
- Each item listing includes a direct Team Fortress 2 Wiki link for cross-referencing item details.
- Class filters distinguish single-class items, multi-class items, and items usable by all classes or with no class restriction.
- Class and category filters use multi-select checkboxes, and choosing multiple categories loads only those local schema groups. Other searchable dropdowns show all options when opened, then narrow as you type; closing and reopening clears the temporary search.
- The item-list tabs show all items in the selected categories, every edited item (saved or unsaved), or every unsaved item change. In All items, **Hide edited** excludes items with saved or unsaved Workshop changes. Switching tabs clears the name search; edited/unsaved views search across the full local schema.
- Button clicks are always silent. Optional TF2 item-hover sounds are off by default and can be enabled with the top-bar toggle; their volume is adjustable and remembered between launches.
- Add any attribute defined by the local TF2 schema directly to the selected item by choosing it and entering a value; the editor displays the attribute's value rather than its raw schema object. For `counts_as_assister`, enter `1`. Reset individual item sections or individual sound fields to their editing-baseline values while preserving edits in other sections.
- “Add filtered” selects the currently visible items as targets for reusable blocks; “Clear all targets” removes that selection.
- Category-scoped loading starts with Cosmetics; other categories load only when selected. Halloween-restricted items are categorized from the schema's `holiday_restriction` field. Tournament and Community medals have separate categories. All category counts are computed from the local schema.
- View every item of a selected type, assign an existing type from the full local schema (not just currently loaded categories), or create a new type name for an item draft. Viewing or applying a type shows matching items across all categories.
- Existing attributes are displayed with their localized TF2 descriptions when the schema provides one. “Copy” selects a value for a reusable block; the Add attribute picker edits only the inspected item.
- Open the dedicated **Sound Library** tab to search the local TF2 sound-reference list and preview available audio before applying it. Noise Maker activation sounds are excluded unless the same reference is also used by another item. Where an item directly references an available sound, the library shows its backpack icon and name as an example. Select an item in Item Workshop first, then choose its sound field in the library; applying stages an edit and returns to the item editor, where **Save item changes** keeps it in the Workshop draft. Item sound fields also retain their searchable replacement dropdowns and direct preview controls.
- Item field edits are staged in the browser until you select **Save item changes**. Unsaved changes are marked separately from saved drafts; save them before closing or refreshing the page. Syncing prompts before discarding them.
- Marketability is shown from the actual `is marketable` static attribute; unspecified values are marked as unspecified rather than shown as unchecked. Capability values are read from the item and its inherited prefab.
- Saved attribute sets bundle only the values you explicitly check. Applying one requires selecting targets and confirming the item count; it creates Workshop drafts only. Compatibility flags are separate schema fields that may indicate support for features such as Pyroland; avoid changing unknown flags.
- Draft changes are marked on item rows and beside each changed field. The clearly labeled **Copy** checkboxes select values for reusable blocks; they do not represent whether an attribute is active. Marketability and capability controls show their live On/Off/unspecified state. Hover over a block to see its attribute descriptions and values.
- Revert all draft edits for the selected item with **Revert this item**; the confirmation restores the item's synced schema values without affecting other drafts or previously saved copies.
- **Save schema copy** opens a Save As dialog so you can choose any output location, even before making edits. It preserves the original schema structure outside edited item blocks, and refuses destinations inside the installed TF2 folder.
- **Open schema copy** compares a saved `items_game.txt` copy with the currently synced TF2 schema and imports supported differences into the Workshop draft. The installed schema remains the baseline for edited-item indicators, revert actions, and future exports. Existing saved drafts are kept; imported values take precedence when both contain changes to the same field. Unsaved browser edits require confirmation before they are discarded.
- Backpack material lookup and pure-Python decoding for common VTF RGBA/BGRA/ARGB/RGB/BGR and DXT1/DXT3/DXT5 formats.
- Local drop, equip, and pickup sound lookup from direct file paths or TF2 game-sound definitions.

## Notes

- The source application requires Python 3.8+ and uses only the Python standard library at runtime. Building the portable Windows package requires Python 3.10+ and PyInstaller. No TF2 assets or sample items are bundled.
- Items without a local `image_inventory` material, unsupported VTF texture format, missing VPK split file, or missing audio file remain browsable and show an explicit fallback/debug path.
- VPK indexing covers top-level `*_dir.vpk` archives and excludes loose files beneath `custom`, `download`, `downloads`, `cache`, `logs`, and `temp`.
- Browser support for audio playback depends on the audio format and browser.
- Some installations may contain only a reduced `items_game.txt`; the app reports the actual definition count and does not fabricate a full catalog. Sync with the full TF2 client files for the complete item schema.
- Saved attribute blocks and item drafts are stored in `%LOCALAPPDATA%\TF2SchemaWorkshop`. Applying a block changes the Workshop draft immediately; direct item field edits require **Save item changes** first. Select **Save schema copy** to write a separate schema copy, or **Open schema copy** to import its differences against the currently synced TF2 schema.
- Mannual's palette and layout conventions were used as visual reference. The Workshop uses its own frontend and backend files and does not load Mannual code or modify its project.
