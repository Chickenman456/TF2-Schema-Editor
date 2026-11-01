(() => {
  "use strict";

  const ROW_HEIGHT = 88;
  const state = {
    items: [],
    categoryItems: [],
    allItemsCache: null,
    filtered: [],
    listView: "all",
    hideEdited: false,
    selectedId: null,
    targets: new Set(),
    blocks: [],
    soundReferences: [],
    soundFieldsUsed: new Set(),
    soundItemExamples: {},
    pendingEdits: new Map(),
    editor: null,
    attributeDefinitionsByName: new Map(),
    customProperties: {},
    selectedClasses: new Set(),
    selectedCategories: new Set(),
    categoryCache: new Map(),
    ready: false,
    rendering: false,
    categoryRequest: 0,
    listViewRequest: 0,
    audioUrls: new Map(),
    previewAudioUrl: null,
    workspacePage: "items",
    statusTimer: null
  };
  const el = (id) => document.getElementById(id);
  const controls = ["searchInput", "slotFilter", "typeFilter", "attributeFilter", "sortFilter", "attributeSort"];
  const soundFields = ["drop_sound", "equip_sound", "pickup_sound", "sound_pickup", "mouse_pressed_sound"];
  const searchableSelects = new WeakMap();
  const checkboxFilters = new Map();
  let searchableSelectId = 0;
  let openPopup = null;
  let uiHoverAudio = null;
  let uiSoundsEnabled = false;
  let uiSoundVolume = 0.1;

  function syncSearchableSelect(select) {
    const enhanced = searchableSelects.get(select);
    if (!enhanced) return;
    const { input } = enhanced;
    const selected = select.selectedOptions[0];
    input.value = selected && selected.value ? selected.textContent.trim() : "";
    input.disabled = select.disabled;
  }

  function positionPopup(anchor, popup) {
    const rect = anchor.getBoundingClientRect();
    const width = Math.min(Math.max(rect.width, 190), window.innerWidth - 16);
    const left = Math.max(8, Math.min(rect.left, window.innerWidth - width - 8));
    const below = window.innerHeight - rect.bottom - 8;
    const above = rect.top - 8;
    const maxHeight = Math.min(320, Math.max(90, Math.max(below, above)));
    popup.style.left = `${left}px`;
    popup.style.width = `${width}px`;
    popup.style.maxHeight = `${maxHeight}px`;
    if (below >= Math.min(180, above)) {
      popup.style.top = `${rect.bottom + 3}px`;
      popup.style.bottom = "auto";
    } else {
      popup.style.top = "auto";
      popup.style.bottom = `${window.innerHeight - rect.top + 3}px`;
    }
  }

  function closePopup() {
    if (!openPopup) return;
    openPopup.popup.hidden = true;
    openPopup.anchor.setAttribute("aria-expanded", "false");
    openPopup = null;
  }

  function openAnchoredPopup(anchor, popup) {
    closePopup();
    popup.hidden = false;
    anchor.setAttribute("aria-expanded", "true");
    positionPopup(anchor, popup);
    openPopup = { anchor, popup };
  }

  function renderOptionPopup(select, input, popup) {
    const query = input.value.trim().toLocaleLowerCase();
    const options = [...select.options].filter((option) =>
      option.textContent.trim().toLocaleLowerCase().includes(query)
    );
    popup.replaceChildren();
    if (!options.length) {
      const empty = document.createElement("div");
      empty.className = "no-options";
      empty.textContent = "No matching options";
      popup.append(empty);
      return;
    }
    options.forEach((option) => {
      const choice = document.createElement("button");
      choice.type = "button";
      choice.textContent = option.textContent.trim();
      choice.dataset.value = option.value;
      choice.setAttribute("aria-selected", String(option.selected));
      popup.append(choice);
    });
  }

  function enhanceSearchableSelect(select) {
    if (searchableSelects.has(select)) {
      syncSearchableSelect(select);
      return searchableSelects.get(select).wrapper;
    }
    const wrapper = document.createElement("span");
    wrapper.className = "searchable-select";
    const input = document.createElement("input");
    input.className = "field select-search";
    input.type = "text";
    input.autocomplete = "off";
    input.placeholder = "Type to filter…";
    input.setAttribute("aria-label", select.getAttribute("aria-label") ||
      select.parentElement?.textContent?.trim().replace(/\s+/g, " ") || "Filter options");
    const popup = document.createElement("div");
    popup.className = "option-popup";
    popup.hidden = true;
    popup.setAttribute("role", "listbox");
    popup.id = `select-options-${++searchableSelectId}`;
    input.setAttribute("aria-controls", popup.id);
    input.setAttribute("aria-autocomplete", "list");
    input.setAttribute("aria-expanded", "false");
    select.tabIndex = -1;
    select.setAttribute("aria-hidden", "true");
    select.insertAdjacentElement("beforebegin", wrapper);
    wrapper.append(input, select);
    document.body.append(popup);
    searchableSelects.set(select, { input, popup, wrapper });

    const choose = (option) => {
      if (!option) return;
      const nextValue = option.value;
      const changed = select.value !== nextValue;
      select.value = nextValue;
      syncSearchableSelect(select);
      closePopup();
      if (changed) select.dispatchEvent(new Event("change", { bubbles: true }));
    };
    input.addEventListener("focus", () => {
      input.value = "";
      renderOptionPopup(select, input, popup);
      openAnchoredPopup(input, popup);
    });
    input.addEventListener("blur", () => syncSearchableSelect(select));
    input.addEventListener("click", () => {
      if (popup.hidden) {
        input.value = "";
        renderOptionPopup(select, input, popup);
        openAnchoredPopup(input, popup);
      }
    });
    input.addEventListener("input", () => {
      renderOptionPopup(select, input, popup);
      if (popup.hidden) openAnchoredPopup(input, popup);
      else positionPopup(input, popup);
    });
    input.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        closePopup();
        syncSearchableSelect(select);
      } else if (event.key === "Enter") {
        event.preventDefault();
        const query = input.value.trim().toLocaleLowerCase();
        const options = [...select.options].filter((option) =>
          option.textContent.trim().toLocaleLowerCase().includes(query)
        );
        choose(options.find((option) => option.textContent.trim().toLocaleLowerCase() === query) || options[0]);
      } else if (event.key === "ArrowDown" && popup.hidden) {
        renderOptionPopup(select, input, popup);
        openAnchoredPopup(input, popup);
      }
    });
    popup.addEventListener("mousedown", (event) => event.preventDefault());
    popup.addEventListener("click", (event) => {
      const choice = event.target.closest("button[data-value]");
      if (choice) choose([...select.options].find((option) => option.value === choice.dataset.value));
    });
    select.addEventListener("change", () => syncSearchableSelect(select));
    syncSearchableSelect(select);
    return wrapper;
  }

  function refreshSearchableSelects(root = document) {
    root.querySelectorAll("select").forEach(enhanceSearchableSelect);
  }

  function checkboxFilterOptions(kind) {
    if (kind === "class") return [
      ["scout", "Scout"], ["soldier", "Soldier"], ["pyro", "Pyro"],
      ["demoman", "Demoman"], ["heavy", "Heavy"], ["engineer", "Engineer"],
      ["medic", "Medic"], ["sniper", "Sniper"], ["spy", "Spy"],
      ["__multi__", "Multi-class"],
      ["__all_classes__", "All nine classes / unrestricted"]
    ];
    return state.editor?.categories || [];
  }

  function renderCheckboxFilter(kind) {
    const container = el(`${kind}Filter`);
    const menu = container.querySelector(".checkbox-filter-menu");
    const selected = kind === "class" ? state.selectedClasses : state.selectedCategories;
    const options = checkboxFilterOptions(kind);
    menu.replaceChildren();
    const actions = document.createElement("div");
    actions.className = "checkbox-filter-actions";
    const clear = document.createElement("button");
    clear.type = "button";
    clear.dataset.filterAction = "clear";
    clear.textContent = "Clear";
    const all = document.createElement("button");
    all.type = "button";
    all.dataset.filterAction = "all";
    all.textContent = kind === "class" ? "Any class" : "All categories";
    const done = document.createElement("button");
    done.type = "button";
    done.dataset.filterAction = "done";
    done.textContent = "Done";
    actions.append(clear, all, done);
    menu.append(actions);
    options.forEach(([value, label]) => {
      const row = document.createElement("label");
      row.className = "checkbox-filter-option";
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.value = value;
      checkbox.dataset.filterKind = kind;
      checkbox.checked = selected.has(value);
      const text = document.createElement("span");
      text.textContent = label;
      row.append(checkbox, text);
      menu.append(row);
    });
    updateCheckboxFilterLabel(kind);
  }

  function updateCheckboxFilterLabel(kind) {
    const container = el(`${kind}Filter`);
    const selected = kind === "class" ? state.selectedClasses : state.selectedCategories;
    const labels = new Map(checkboxFilterOptions(kind));
    const button = container.querySelector(".checkbox-filter-trigger");
    if (!selected.size) {
      button.textContent = kind === "class" ? "Any class" : "No categories";
      return;
    }
    if (selected.size === 1) button.textContent = labels.get([...selected][0]) || "1 selected";
    else button.textContent = `${selected.size} selected`;
  }

  function initializeCheckboxFilters() {
    for (const kind of ["class", "category"]) {
      const container = el(`${kind}Filter`);
      const button = container.querySelector(".checkbox-filter-trigger");
      const menu = container.querySelector(".checkbox-filter-menu");
      checkboxFilters.set(kind, { button, menu });
      button.addEventListener("click", () => {
        renderCheckboxFilter(kind);
        if (menu.hidden) openAnchoredPopup(button, menu);
        else closePopup();
      });
      menu.addEventListener("click", async (event) => {
        const action = event.target.closest("button[data-filter-action]")?.dataset.filterAction;
        if (action === "done") {
          closePopup();
          return;
        }
        if (!action) return;
        const selected = kind === "class" ? state.selectedClasses : state.selectedCategories;
        if (action === "clear") selected.clear();
        else if (action === "all" && kind === "category") {
          state.editor.categories.forEach(([value]) => selected.add(value));
        } else if (action === "all") selected.clear();
        renderCheckboxFilter(kind);
        if (kind === "category") await loadSelectedCategories();
        else applyFilters();
      });
      menu.addEventListener("change", async (event) => {
        const checkbox = event.target.closest("input[data-filter-kind]");
        if (!checkbox) return;
        const selected = kind === "class" ? state.selectedClasses : state.selectedCategories;
        if (checkbox.checked) selected.add(checkbox.value);
        else selected.delete(checkbox.value);
        renderCheckboxFilter(kind);
        if (kind === "category") await loadSelectedCategories();
        else applyFilters();
      });
    }
    document.addEventListener("pointerdown", (event) => {
      if (openPopup && !openPopup.popup.contains(event.target) && !openPopup.anchor.contains(event.target)) {
        closePopup();
      }
    });
    window.addEventListener("resize", () => {
      if (openPopup) positionPopup(openPopup.anchor, openPopup.popup);
    });
    window.addEventListener("scroll", () => {
      if (openPopup) positionPopup(openPopup.anchor, openPopup.popup);
    }, true);
  }

  function updateUiSoundsToggle() {
    const button = el("uiSoundsToggle");
    button.textContent = `Hover sounds: ${uiSoundsEnabled ? "On" : "Off"}`;
    button.setAttribute("aria-pressed", String(uiSoundsEnabled));
  }

  function updateUiSoundVolume() {
    const slider = el("uiSoundVolume");
    const output = el("uiSoundVolumeValue");
    slider.value = String(Math.round(uiSoundVolume * 100));
    output.value = `${slider.value}%`;
    output.textContent = output.value;
    if (uiHoverAudio) uiHoverAudio.volume = uiSoundVolume;
  }

  function playUiSound(audio) {
    if (!uiSoundsEnabled || !audio) return;
    audio.currentTime = 0;
    audio.play().catch((error) => console.debug("TF2 UI sound could not play:", error.message));
  }

  function initializeUiSounds() {
    try {
      uiSoundsEnabled = window.localStorage.getItem("tf2-workshop-hover-sounds") === "on";
      const savedVolumeValue = window.localStorage.getItem("tf2-workshop-hover-volume");
      const savedVolume = Number(savedVolumeValue);
      if (savedVolumeValue !== null && Number.isFinite(savedVolume) && savedVolume >= 0 && savedVolume <= 100) {
        uiSoundVolume = savedVolume / 100;
      }
    } catch (error) {
      console.debug("Could not read the UI sound preferences:", error.message);
    }
    updateUiSoundsToggle();
    updateUiSoundVolume();
  }

  function loadUiSoundAssets() {
    if (uiHoverAudio) return;
    uiHoverAudio = new Audio("/api/sound?reference=ui/buttonrollover.wav");
    uiHoverAudio.preload = "auto";
    uiHoverAudio.volume = uiSoundVolume;
  }

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (char) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    })[char]);
  }

  async function requestJson(url, options) {
    const response = await fetch(url, options);
    let payload;
    try { payload = await response.json(); }
    catch { payload = {}; }
    if (!response.ok) throw new Error(payload.error || `Request failed (${response.status})`);
    return payload;
  }

  function updateHeader(status) {
    const light = el("statusLight");
    light.className = "status-light";
    if (status.state.state === "scanning") {
      light.classList.add("busy");
      el("headerStatus").textContent = "Sync in progress";
    } else if (status.state.state === "ready") {
      light.classList.add("ready");
      el("headerStatus").textContent = `${status.item_count.toLocaleString()} definitions loaded`;
    } else if (status.state.state === "error") {
      light.classList.add("error");
      el("headerStatus").textContent = "Sync needs attention";
    } else if (status.tf_dir) {
      el("headerStatus").textContent = "TF2 installation detected";
    } else {
      el("headerStatus").textContent = "Not synchronized";
    }

    el("syncMessage").textContent = status.state.message;
    el("syncError").hidden = !status.state.error;
    el("syncError").textContent = status.state.error || "";
    el("syncButton").disabled = status.state.state === "scanning";
    el("syncButton").textContent = status.state.state === "scanning" ? "Syncing…" : "Sync TF2";
    el("exportButton").disabled = status.state.state !== "ready" || state.pendingEdits.size > 0;
    el("openSchemaButton").disabled = status.state.state !== "ready";
    el("draftCount").textContent = `${status.draft_count.toLocaleString()} edited item${status.draft_count === 1 ? "" : "s"}`;
    if (status.tf_dir && document.activeElement !== el("tfPath")) {
      el("tfPath").value = status.tf_dir;
    }
    el("archiveInfo").textContent = status.state.state === "ready"
      ? `${status.archive_count} VPK archives indexed${status.warning_count ? ` · ${status.warning_count} scan warning(s)` : ""}`
      : "";
    if (status.state.state === "ready") loadUiSoundAssets();
    if (status.state.state === "ready" && !state.ready) loadItems();
    if (status.state.state !== "scanning" && state.statusTimer) {
      clearInterval(state.statusTimer);
      state.statusTimer = null;
    }
  }

  async function refreshStatus() {
    try {
      const status = await requestJson("/api/status");
      updateHeader(status);
    } catch (error) {
      el("syncMessage").textContent = "The local application server could not be reached.";
      el("syncError").hidden = false;
      el("syncError").textContent = error.message;
    }
  }

  async function loadItems() {
    if (state.rendering) return;
    state.rendering = true;
    el("syncError").hidden = true;
    el("resultCount").textContent = "Loading local item data…";
    el("emptyList").hidden = false;
    el("emptyList").textContent = "Loading local item definitions…";
    try {
      const [editor, blocks] = await Promise.all([
        requestJson("/api/editor"),
        requestJson("/api/blocks")
      ]);
      state.editor = editor;
      state.soundReferences = editor.sound_references || [];
      state.soundFieldsUsed = new Set(editor.sound_fields_used || [
        ...new Set(Object.values(editor.sound_item_examples || {}).map((example) => example.field))
      ]);
      [...el("soundLibraryField").options].forEach((option) => {
        option.hidden = !state.soundFieldsUsed.has(option.value);
      });
      if (!state.soundFieldsUsed.has(el("soundLibraryField").value)) {
        el("soundLibraryField").value = soundFields.find((field) => state.soundFieldsUsed.has(field)) || "";
      }
      state.soundItemExamples = editor.sound_item_examples || {};
      state.attributeDefinitionsByName = new Map(
        (editor.attribute_definitions || []).map((definition) => [definition.name, definition])
      );
      const addAttributeSelect = el("addAttributeSelect");
      addAttributeSelect.replaceChildren(new Option("Choose an attribute…", ""));
      [...state.attributeDefinitionsByName.values()]
        .sort((a, b) => a.name.localeCompare(b.name))
        .forEach((definition) => {
          const label = [
            `#${definition.id}`,
            definition.name,
            definition.description
          ].filter(Boolean).join(" · ");
          addAttributeSelect.add(new Option(label, definition.name));
        });
      state.blocks = blocks;
      state.listView = "all";
      state.categoryItems = [];
      state.allItemsCache = null;
      document.querySelectorAll(".item-view-tab").forEach((tab) => {
        const active = tab.dataset.itemView === "all";
        tab.classList.toggle("active", active);
        tab.setAttribute("aria-pressed", String(active));
      });
      state.selectedCategories = new Set(["cosmetics"]);
      state.categoryCache.clear();
      renderBlockShelf();
      await loadSelectedCategories(true);
      state.ready = true;
      controls.forEach((id) => { el(id).disabled = false; });
      el("soundLibraryTab").disabled = false;
      el("saveBlockButton").disabled = false;
      el("addCustomProperty").disabled = false;
      el("selectVisibleTargets").disabled = false;
      el("clearTargets").disabled = false;
      el("selectAllAttributes").disabled = false;
      el("addAttributeSelect").disabled = false;
      el("addAttributeValue").disabled = false;
      el("addAttributeButton").disabled = false;
      el("toggleCurrentTarget").disabled = false;
      el("itemTypeSelect").disabled = false;
      el("saveItemType").disabled = false;
      el("classFilter").querySelector(".checkbox-filter-trigger").disabled = false;
      el("categoryFilter").querySelector(".checkbox-filter-trigger").disabled = false;
      el("exportButton").disabled = state.pendingEdits.size > 0;
      refreshSearchableSelects();
      applyFilters();
    } catch (error) {
      state.ready = false;
      el("syncError").hidden = false;
      el("syncError").textContent = error.message;
      el("resultCount").textContent = "Could not load item data";
      el("emptyList").hidden = false;
      el("emptyList").textContent = "Local item definitions could not be loaded. Check the sync status and try again.";
    } finally {
      state.rendering = false;
    }
  }

  async function loadSelectedCategories(required = false) {
    const requestId = ++state.categoryRequest;
    state.items = [];
    state.filtered = [];
    state.selectedId = null;
    el("detailContent").hidden = true;
    el("detailEmpty").hidden = false;
    el("resultCount").textContent = "Loading item category…";
    el("emptyList").hidden = false;
    el("emptyList").textContent = "Loading local item definitions…";
    el("itemSpacer").style.height = "0px";
    el("itemRows").replaceChildren();
    const categories = [...state.selectedCategories];
    try {
      const missing = categories.filter((category) => !state.categoryCache.has(category));
      const loaded = await Promise.all(missing.map(async (category) => {
        const items = await requestJson(`/api/items?category=${encodeURIComponent(category)}`);
        return [category, items];
      }));
      loaded.forEach(([category, items]) => state.categoryCache.set(category, items));
      if (requestId !== state.categoryRequest) return;
      state.items = categories.flatMap((category) => state.categoryCache.get(category) || []);
      state.categoryItems = state.items;
      state.pendingEdits.forEach((patch, defindex) => {
        const item = state.categoryItems.find((candidate) => candidate.defindex === defindex);
        if (item) applyPendingPatch(item);
      });
      if (state.listView !== "all" && state.allItemsCache) state.items = state.allItemsCache;
      populateFilters();
      refreshSearchableSelects();
      applyFilters();
    } catch (error) {
      if (requestId !== state.categoryRequest) return;
      el("syncError").hidden = false;
      el("syncError").textContent = error.message;
      el("resultCount").textContent = "Could not load this category";
      el("emptyList").textContent = "One or more selected categories could not be loaded.";
      if (required) throw error;
    }
  }

  async function refreshCurrentItems() {
    const categories = [...state.selectedCategories];
    const loaded = await Promise.all(categories.map(async (category) => {
      const items = await requestJson(`/api/items?category=${encodeURIComponent(category)}`);
      return [category, items];
    }));
    loaded.forEach(([category, items]) => state.categoryCache.set(category, items));
    state.categoryItems = categories.flatMap((category) => state.categoryCache.get(category) || []);
    state.allItemsCache = null;
    state.items = state.categoryItems;
    state.pendingEdits.forEach((patch, defindex) => {
      const item = state.categoryItems.find((candidate) => candidate.defindex === defindex);
      if (item) applyPendingPatch(item);
    });
    if (state.listView !== "all") {
      state.allItemsCache = await requestJson("/api/items");
      state.pendingEdits.forEach((patch, defindex) => {
        const item = state.allItemsCache.find((candidate) => candidate.defindex === defindex);
        if (item) applyPendingPatch(item);
      });
      state.items = state.allItemsCache;
    }
    populateFilters();
    refreshSearchableSelects();
    applyFilters();
  }

  function pendingPatch(defindex) {
    return state.pendingEdits.get(defindex) || {};
  }

  function changedKeys(item, section) {
    return [...new Set([
      ...(item.changed_fields?.[section] || []),
      ...Object.keys(pendingPatch(item.defindex)[section] || {})
    ])];
  }

  function hasSavedChanges(item) {
    return Object.values(item.changed_fields || {}).some((fields) => fields.length);
  }

  function hasEdits(item) {
    return hasSavedChanges(item) || hasPendingChanges(item);
  }

  function hasPendingChanges(item) {
    return Object.values(pendingPatch(item.defindex)).some((fields) =>
      fields && typeof fields === "object" && Object.keys(fields).length);
  }

  function sectionHasChanges(item, section) {
    if (section === "type") return changedKeys(item, "item_fields").includes("item_type_name");
    if (section === "sounds") return soundFields.some((field) => changedKeys(item, "item_fields").includes(field));
    if (section === "attributes") {
      return changedKeys(item, "attributes").length > 0 ||
        changedKeys(item, "properties").length > 0 ||
        changedKeys(item, "static_attrs").some((key) => key.toLowerCase() !== "is marketable");
    }
    if (section === "capabilities") {
      return changedKeys(item, "capabilities").length > 0 ||
        changedKeys(item, "static_attrs").some((key) => key.toLowerCase() === "is marketable");
    }
    if (section.startsWith("sound:")) {
      return changedKeys(item, "item_fields").includes(section.slice(6));
    }
    return false;
  }

  function applyPendingPatch(item) {
    const patch = pendingPatch(item.defindex);
    if (patch.item_fields) {
      if (Object.prototype.hasOwnProperty.call(patch.item_fields, "item_type_name")) {
        item.type_value = patch.item_fields.item_type_name;
        const knownType = (state.editor?.item_types || [])
          .find((itemType) => itemType.value === item.type_value);
        item.type = knownType?.label || item.type_value.replace(/^#/, "").replace(/_/g, " ");
      }
      Object.entries(patch.item_fields).forEach(([field, value]) => {
        if (Object.prototype.hasOwnProperty.call(item.sounds || {}, field)) item.sounds[field] = value;
      });
    }
    if (patch.static_attrs) item.static_attrs = { ...item.static_attrs, ...patch.static_attrs };
    if (patch.capabilities) item.capabilities = { ...item.capabilities, ...patch.capabilities };
    if (patch.attributes) item.attributes = { ...item.attributes, ...patch.attributes };
    if (patch.properties) item.properties = { ...item.properties, ...patch.properties };
  }

  function populateFilters() {
    const previous = {
      slot: el("slotFilter").value,
      type: el("typeFilter").value,
      attribute: el("attributeFilter").value
    };
    const slots = [...new Set(state.items.map((item) => item.slot).filter(Boolean))]
      .sort((a, b) => a.localeCompare(b));
    const slotSelect = el("slotFilter");
    slotSelect.replaceChildren(new Option("All slots", ""));
    slots.forEach((slot) => slotSelect.add(new Option(slot.replace(/_/g, " "), slot)));
    if (previous.slot && !slots.includes(previous.slot)) {
      slotSelect.add(new Option(previous.slot.replace(/_/g, " "), previous.slot));
    }
    slotSelect.value = previous.slot;

    const types = [...new Set([
      ...(state.editor.item_types || []).map((itemType) => itemType.label),
      ...state.items.map((item) => item.type)
    ].filter(Boolean))].sort((a, b) => a.localeCompare(b));
    const typeSelect = el("typeFilter");
    typeSelect.replaceChildren(new Option("All types", ""));
    types.forEach((type) => typeSelect.add(new Option(type, type)));
    if (previous.type && !types.includes(previous.type)) {
      typeSelect.add(new Option(previous.type, previous.type));
    }
    typeSelect.value = previous.type;

    const attributeKeys = new Set();
    state.items.forEach((item) => {
      Object.keys(item.attributes || {}).forEach((key) => attributeKeys.add(key));
      Object.keys(item.static_attrs || {}).forEach((key) => attributeKeys.add(key));
    });
    const attributeSelect = el("attributeFilter");
    attributeSelect.replaceChildren(new Option("Any attribute", ""));
    [...attributeKeys].sort((a, b) => {
      const aName = attributeDefinition(a)?.name || a;
      const bName = attributeDefinition(b)?.name || b;
      return aName.localeCompare(bName) || a.localeCompare(b);
    }).forEach((key) => {
      const definition = attributeDefinition(key);
      const option = new Option(definition?.name || key, key);
      option.title = attributeExplanation(definition, key);
      attributeSelect.add(option);
    });
    if (previous.attribute && !attributeKeys.has(previous.attribute)) {
      const definition = attributeDefinition(previous.attribute);
      const option = new Option(definition?.name || previous.attribute, previous.attribute);
      option.title = attributeExplanation(definition, previous.attribute);
      attributeSelect.add(option);
    }
    attributeSelect.value = previous.attribute;

    const typeValues = new Map((state.editor.item_types || [])
      .map((itemType) => [itemType.value, itemType.label]));
    state.items.forEach((item) => {
      if (item.type_value) typeValues.set(item.type_value, item.type || item.type_value.replace(/^#/, ""));
    });
    const itemTypeSelect = el("itemTypeSelect");
    itemTypeSelect.replaceChildren(new Option("No item type", ""));
    [...typeValues.entries()].sort((a, b) => a[1].localeCompare(b[1]))
      .forEach(([value, label]) => itemTypeSelect.add(new Option(label, value)));
    renderCheckboxFilter("class");
    renderCheckboxFilter("category");
    refreshSearchableSelects();
  }

  function applyFilters() {
    const query = el("searchInput").value.trim().toLocaleLowerCase();
    const classScopes = state.selectedClasses;
    const slot = el("slotFilter").value;
    const categories = state.selectedCategories;
    const type = el("typeFilter").value;
    const attribute = el("attributeFilter").value;
    const sort = el("sortFilter").value;
    const scopedItems = state.listView === "edited"
      ? state.items.filter(hasEdits)
      : state.listView === "unsaved"
        ? state.items.filter(hasPendingChanges)
        : state.items;
    const filtered = scopedItems.filter((item) => {
      if (state.hideEdited && state.listView === "all" &&
          (hasSavedChanges(item) || hasPendingChanges(item))) return false;
      if (query && !item.name.toLocaleLowerCase().includes(query) &&
          !String(item.defindex).includes(query) &&
          !item.item_class.toLocaleLowerCase().includes(query) &&
          !String(item.metadata.name || "").toLocaleLowerCase().includes(query)) return false;
      if (classScopes.size && ![...classScopes].some((className) => {
        if (className === "__multi__") return item.classes.length >= 2 && item.classes.length < 9;
        if (className === "__all_classes__") return item.classes.length === 0 || item.classes.length >= 9;
        return item.classes.length === 1 && item.classes[0] === className;
      })) return false;
      if (slot && item.slot !== slot) return false;
      if (state.listView === "all" && categories.size && !categories.has(item.category)) return false;
      if (type && item.type !== type) return false;
      if (attribute && !Object.prototype.hasOwnProperty.call(item.attributes || {}, attribute) &&
          !Object.prototype.hasOwnProperty.call(item.static_attrs || {}, attribute)) return false;
      return true;
    });
    if (sort === "defindex") filtered.sort((a, b) => a.defindex - b.defindex);
    else if (sort === "class") filtered.sort((a, b) => {
      const classGroup = (item) => item.classes.length === 0 || item.classes.length >= 9
        ? [2, ""] : item.classes.length > 1 ? [1, item.classes.join(", ")] : [0, item.classes[0]];
      const aGroup = classGroup(a);
      const bGroup = classGroup(b);
      return aGroup[0] - bGroup[0] || aGroup[1].localeCompare(bGroup[1]) || a.name.localeCompare(b.name);
    });
    else if (sort === "category") filtered.sort((a, b) =>
      a.category.localeCompare(b.category) || a.name.localeCompare(b.name));
    else if (sort === "type") filtered.sort((a, b) =>
      a.type.localeCompare(b.type) || a.name.localeCompare(b.name));
    else if (sort === "year-added" || sort === "year-added-desc") {
      const year = (item) => {
        const match = String(item.metadata.first_sale_date || "").match(/^(\d{4})\/\d{1,2}\/\d{1,2}$/);
        return match ? Number(match[1]) : null;
      };
      filtered.sort((a, b) => {
        const aYear = year(a);
        const bYear = year(b);
        if (aYear === null || bYear === null) {
          if (aYear === null && bYear !== null) return 1;
          if (bYear === null && aYear !== null) return -1;
        } else if (aYear !== bYear) {
          return sort === "year-added" ? aYear - bYear : bYear - aYear;
        }
        return a.name.localeCompare(b.name) || a.defindex - b.defindex;
      });
    }
    else if (sort === "attributes" || sort === "attributes-asc") {
      const count = (item) => Object.keys(item.attributes || {}).length + Object.keys(item.static_attrs || {}).length;
      filtered.sort((a, b) => (sort === "attributes" ? count(b) - count(a) : count(a) - count(b)) ||
        a.name.localeCompare(b.name));
    }
    else filtered.sort((a, b) => a.name.localeCompare(b.name) || a.defindex - b.defindex);
    state.filtered = filtered;
    const categoryTotal = state.listView === "all"
      ? [...categories].reduce((total, category) => total + (state.editor.category_counts?.[category] || 0), 0)
      : scopedItems.length;
    el("resultCount").textContent = state.ready
      ? `${filtered.length.toLocaleString()} of ${categoryTotal.toLocaleString()} items`
      : "Sync TF2 to browse";
    el("totalCount").textContent = state.ready ? scopedItems.length.toLocaleString() : "—";
    el("itemSpacer").style.height = `${filtered.length * ROW_HEIGHT}px`;
    const empty = el("emptyList");
    empty.hidden = filtered.length !== 0;
    empty.textContent = state.ready
      ? (state.listView === "all" && !categories.size
        ? "Select one or more categories to browse items."
        : state.listView === "unsaved" && !scopedItems.length
          ? "There are no unsaved item changes."
          : state.listView === "edited" && !scopedItems.length
            ? "There are no edited items."
            : "No local item definitions match these filters.")
      : "Items from your local TF2 schema will appear here after sync.";
    const viewport = el("itemViewport");
    const selectionVisible = filtered.some((item) => item.defindex === state.selectedId);
    renderRows(viewport.scrollTop);
    if (!selectionVisible && filtered.length) {
      selectItem(filtered[0].defindex, false);
    } else if (!filtered.length && !selectionVisible) {
      state.selectedId = null;
      el("detailContent").hidden = true;
      el("detailEmpty").hidden = false;
    }
  }

  function renderRows(scrollTop) {
    const viewport = el("itemViewport");
    const start = Math.max(0, Math.floor(scrollTop / ROW_HEIGHT) - 2);
    const visible = Math.ceil(viewport.clientHeight / ROW_HEIGHT) + 5;
    const rows = state.filtered.slice(start, start + visible);
    const rowContainer = el("itemRows");
    rowContainer.style.transform = `translateY(${start * ROW_HEIGHT}px)`;
    rowContainer.innerHTML = rows.map((item) => {
      const classes = item.classes.length ? item.classes.map((name) => name[0].toUpperCase() + name.slice(1)).join(", ") : "Class unspecified";
      const slot = item.slot ? item.slot.replace(/_/g, " ") : "Unslotted";
      const changed = Object.keys(item.changed_fields || {})
        .flatMap((section) => changedKeys(item, section).map((key) => `${section}: ${key}`));
      const pending = hasPendingChanges(item);
      const edited = changed.length > 0 || pending;
      const icon = item.image_inventory
        ? `<img loading="lazy" src="/api/icon?id=${item.defindex}" alt="">`
        : "";
      const wikiUrl = `https://wiki.teamfortress.com/wiki/${encodeURIComponent(item.name.trim().replace(/\s+/g, "_"))}`;
      return `<div class="item-row${item.defindex === state.selectedId ? " selected" : ""}${edited ? " has-changes" : ""}${pending ? " has-unsaved" : ""}" data-id="${item.defindex}">
        <input class="target-toggle" type="checkbox" aria-label="Add ${escapeHtml(item.name)} to block targets" title="Select this item as a target for applying reusable blocks." ${state.targets.has(item.defindex) ? "checked" : ""}>
        <div class="row-content">
          <button type="button" class="row-open" aria-label="Inspect ${escapeHtml(item.name)}, definition ${item.defindex}">
            <span class="list-icon${item.image_inventory ? "" : " icon-fallback"}" title="${escapeHtml(item.image_inventory)}">${icon}</span>
            <span class="row-main"><span class="row-name">${escapeHtml(item.name)}${edited ? '<span class="edited-badge row-edited" title="' + escapeHtml(changed.join(", ") || "This item has unsaved changes.") + '">Edited</span>' : ""}${pending ? '<span class="edited-badge unsaved-badge row-edited" title="Save this item to keep the unsaved changes.">Unsaved</span>' : ""}</span><span class="row-sub"><span>${escapeHtml(item.category)}</span><span>·</span><span>${escapeHtml(item.type || slot)}</span><span>·</span><span>${escapeHtml(classes)}</span></span></span>
            <span class="row-index">#${item.defindex}</span>
          </button>
          <a class="row-wiki-link" href="${escapeHtml(wikiUrl)}" target="_blank" rel="noopener noreferrer" aria-label="Open ${escapeHtml(item.name)} on the Team Fortress 2 Wiki">TF2 Wiki ↗</a>
        </div>
      </div>`;
    }).join("");
    rowContainer.querySelectorAll(".list-icon img").forEach((image) => {
      image.addEventListener("error", () => {
        image.parentElement.classList.add("icon-fallback");
        image.hidden = true;
      }, { once: true });
    });
    el("targetCount").textContent = `${state.targets.size.toLocaleString()} target${state.targets.size === 1 ? "" : "s"}`;
    el("selectVisibleTargets").textContent = `Add filtered (${state.filtered.length.toLocaleString()})`;
  }

  async function setItemListView(view) {
    if (!["all", "edited", "unsaved"].includes(view)) return;
    const requestId = ++state.listViewRequest;
    state.listView = view;
    document.querySelectorAll(".item-view-tab").forEach((tab) => {
      const active = tab.dataset.itemView === view;
      tab.classList.toggle("active", active);
      tab.setAttribute("aria-pressed", String(active));
    });
    el("hideEditedFilter").hidden = view !== "all";
    el("searchInput").value = "";
    el("itemViewport").scrollTop = 0;
    if (view === "all") {
      state.items = state.categoryItems;
    } else {
      el("resultCount").textContent = "Loading edited items…";
      try {
        if (!state.allItemsCache) state.allItemsCache = await requestJson("/api/items");
        if (requestId !== state.listViewRequest) return;
        state.pendingEdits.forEach((patch, defindex) => {
          const item = state.allItemsCache.find((candidate) => candidate.defindex === defindex);
          if (item) applyPendingPatch(item);
        });
        state.items = state.allItemsCache;
      } catch (error) {
        if (requestId !== state.listViewRequest) return;
        el("syncError").hidden = false;
        el("syncError").textContent = error.message;
        return;
      }
    }
    applyFilters();
  }

  function selectItem(defindex, scrollIntoView = true) {
    const item = state.items.find((candidate) => candidate.defindex === defindex);
    if (!item) return;
    state.selectedId = defindex;
    el("detailEmpty").hidden = true;
    el("detailContent").hidden = false;
    el("detailDefindex").textContent = `#${item.defindex}`;
    const changed = item.changed_fields || {};
    const hasChanges = hasSavedChanges(item);
    const hasPending = hasPendingChanges(item);
    el("detailEdited").hidden = !hasChanges;
    el("detailUnsaved").hidden = !hasPending;
    el("saveItemButton").hidden = !hasPending;
    el("revertItemButton").hidden = !hasChanges && !hasPending;
    el("resetTypeButton").hidden = !sectionHasChanges(item, "type");
    el("resetSoundsButton").hidden = !sectionHasChanges(item, "sounds");
    el("resetAttributesButton").hidden = !sectionHasChanges(item, "attributes");
    el("resetCapabilitiesButton").hidden = !sectionHasChanges(item, "capabilities");
    el("toggleCurrentTarget").textContent = state.targets.has(item.defindex) ? "Remove block target" : "Target inspected item";
    el("toggleCurrentTarget").title = "Mark this item as a target for applying a reusable attribute block.";
    el("detailName").textContent = item.name;
    if (state.workspacePage === "sounds") updateSoundLibraryTarget();
    el("viewTypeItems").textContent = item.type || "Type not specified in schema";
    el("viewTypeItems").disabled = !item.type;
    el("viewTypeItems").title = item.type
      ? `Show all ${item.type} items`
      : "This item has no item type in the schema.";
    el("detailCategory").textContent = (state.editor.categories.find(([id]) => id === item.category) || [null, "Other"])[1];
    el("detailClass").textContent = item.classes.length
      ? item.classes.map((name) => name[0].toUpperCase() + name.slice(1)).join(" · ")
      : "Class restrictions not specified";
    el("detailDescription").hidden = !item.description;
    el("detailDescription").textContent = item.description;

    const image = el("detailIcon");
    const iconWrap = el("detailIconWrap");
    image.hidden = true;
    iconWrap.classList.add("icon-fallback");
    iconWrap.title = item.image_inventory ? `Local material: ${item.image_inventory}` : "No image_inventory value in this item definition.";
    image.onload = () => {
      image.hidden = false;
      iconWrap.classList.remove("icon-fallback");
    };
    image.onerror = async () => {
      image.hidden = true;
      iconWrap.classList.add("icon-fallback");
      try {
        const response = await fetch(`/api/icon?id=${item.defindex}`);
        const result = await response.json();
        el("assetDebug").textContent = `Icon unavailable: ${result.asset_path || item.image_inventory || "no matching local asset"}`;
      } catch {
        el("assetDebug").textContent = `Icon unavailable. Schema material reference: ${item.image_inventory || "none"}`;
      }
    };
    if (item.image_inventory) image.src = `/api/icon?id=${item.defindex}`;
    else image.removeAttribute("src");
    applyPendingPatch(item);
    renderSounds(item);
    renderItemType(item);
    renderAttributeEditor(item);
    renderCapabilities(item);
    renderMetadata(item);
    el("assetDebug").textContent = item.image_inventory
      ? `Icon material reference: ${item.image_inventory}`
      : "Icon material reference: none defined in the local schema.";
    renderRows(el("itemViewport").scrollTop);
    if (scrollIntoView) {
      const index = state.filtered.findIndex((candidate) => candidate.defindex === defindex);
      if (index >= 0) {
        const viewport = el("itemViewport");
        const top = index * ROW_HEIGHT;
        if (top < viewport.scrollTop || top + ROW_HEIGHT > viewport.scrollTop + viewport.clientHeight) {
          viewport.scrollTop = Math.max(0, top - Math.floor(viewport.clientHeight / 3));
        }
      }
    }
  }

  function renderMetadata(item) {
    const rows = [
      ["Definition index", String(item.defindex)],
      ["Item class", item.item_class || "Not specified"],
      ["Item slot", item.slot || "Not specified"],
      ["Item type", item.type || "Not specified"],
      ["Category", item.category],
      ["Used by", item.classes.length ? item.classes.join(", ") : "Not specified"],
      ["Name token", item.name_token || "Not specified"],
      ...Object.entries(item.metadata).filter(([key]) =>
        !["item_name", "item_type_name", "item_description"].includes(key))
        .map(([key, value]) => [key, typeof value === "object" ? JSON.stringify(value) : String(value)])
    ];
    const list = el("metadataList");
    list.replaceChildren();
    rows.forEach(([label, value]) => {
      const term = document.createElement("dt");
      const description = document.createElement("dd");
      term.textContent = label.replace(/_/g, " ");
      description.textContent = value;
      list.append(term, description);
    });
  }

  function renderItemType(item) {
    el("itemTypeSelect").value = item.type_value || "";
    el("newItemType").value = "";
    syncSearchableSelect(el("itemTypeSelect"));
    const changed = changedKeys(item, "item_fields").includes("item_type_name");
    el("typeChangeMarker").hidden = !changed;
  }

  function capabilityLabel(key) {
    return ({
      can_be_marketable: "Can be marketed",
      can_be_traded: "Can be traded",
      can_be_crafted: "Can be crafted",
      can_be_restored: "Can be restored",
      can_be_gifted: "Can be gifted"
    })[key] || key.replace(/^can_be_/, "Can be ").replace(/_/g, " ");
  }

  function renderCapabilities(item) {
    const container = el("capabilityEntries");
    container.replaceChildren();
    const capabilities = item.capabilities || {};
    const changed = new Set(changedKeys(item, "capabilities"));
    const staticAttrs = item.static_attrs || {};
    const marketabilityKey = Object.keys(staticAttrs).find((key) => key.toLowerCase() === "is marketable") || "is marketable";
    const marketabilitySpecified = Object.prototype.hasOwnProperty.call(staticAttrs, marketabilityKey);
    const marketability = document.createElement("label");
    const marketabilityChanged = changedKeys(item, "static_attrs").includes(marketabilityKey);
    marketability.className = `capability-row marketability-row${marketabilityChanged ? " changed" : ""}`;
    const marketabilityCheckbox = document.createElement("input");
    marketabilityCheckbox.type = "checkbox";
    marketabilityCheckbox.checked = ["1", "true", "yes"].includes(String(staticAttrs[marketabilityKey] || "").toLowerCase());
    marketabilityCheckbox.indeterminate = !marketabilitySpecified;
    marketabilityCheckbox.title = marketabilitySpecified
      ? "Marketability is set by the item's static attribute."
      : "This item and its inherited prefab do not specify marketability.";
    marketabilityCheckbox.addEventListener("change", () => {
      saveItemEdits(item.defindex, { static_attrs: { "is marketable": marketabilityCheckbox.checked ? "1" : "0" } });
    });
    const marketabilityName = document.createElement("span");
    marketabilityName.textContent = "Marketable";
    const marketabilityState = document.createElement("span");
    marketabilityState.className = "live-state";
    marketabilityState.textContent = !marketabilitySpecified
      ? "Not specified"
      : marketabilityCheckbox.checked ? "Yes" : "No";
    const marketabilityKeyLabel = document.createElement("code");
    marketabilityKeyLabel.textContent = "is marketable";
    marketability.append(marketabilityCheckbox, marketabilityName, marketabilityState, marketabilityKeyLabel);
    if (marketabilityChanged) marketability.append(makeChangeMarker());
    container.append(marketability);

    const keys = Object.keys(capabilities)
      .sort((a, b) => a.localeCompare(b));
    keys.forEach((key) => {
      const row = document.createElement("label");
      row.className = `capability-row${changed.has(key) ? " changed" : ""}`;
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.checked = ["1", "true", "yes"].includes(String(capabilities[key] || "").toLowerCase());
      checkbox.indeterminate = !Object.prototype.hasOwnProperty.call(capabilities, key);
      checkbox.title = checkbox.indeterminate
        ? "This capability is not explicitly set in the item or its inherited prefab."
        : `${capabilityLabel(key)}: ${checkbox.checked ? "enabled in the live schema" : "disabled in the live schema"}`;
      checkbox.addEventListener("change", () => {
        saveItemEdits(item.defindex, { capabilities: { [key]: checkbox.checked ? "1" : "0" } });
      });
      const name = document.createElement("span");
      name.textContent = capabilityLabel(key);
      const stateLabel = document.createElement("span");
      stateLabel.className = "live-state";
      stateLabel.textContent = checkbox.checked ? "On" : "Off";
      const schemaKey = document.createElement("code");
      schemaKey.textContent = key;
      row.append(checkbox, name, stateLabel, schemaKey);
      if (changed.has(key)) row.append(makeChangeMarker());
      container.append(row);
    });
  }

  function makeChangeMarker() {
    const marker = document.createElement("span");
    marker.className = "change-marker";
    marker.textContent = "Changed";
    marker.title = "This draft value differs from the live TF2 schema.";
    return marker;
  }

  function attributeDefinition(name) {
    return state.attributeDefinitionsByName.get(name);
  }

  function attributeExplanation(definition, key) {
    if (definition?.description) return definition.description;
    const note = definition?.hidden === "1"
      ? "TF2 marks this as a hidden attribute."
      : "The local TF2 schema does not provide an English description for this attribute.";
    return `${note} Schema key: ${key}${definition?.attribute_class ? ` (class: ${definition.attribute_class})` : ""}.`;
  }

  function renderAttributeEditor(item) {
    const sort = el("attributeSort").value;
    const entries = [
      ...Object.entries(item.attributes || {}).map(([key, value]) => ({ section: "attributes", key, value })),
      ...Object.entries(item.static_attrs || {}).map(([key, value]) => ({ section: "static_attrs", key, value }))
    ];
    const valueText = (value) => {
      if (value && typeof value === "object" && Object.prototype.hasOwnProperty.call(value, "value")) {
        return String(value.value);
      }
      return typeof value === "object" ? JSON.stringify(value) : String(value);
    };
    entries.sort((a, b) => {
      const aDef = attributeDefinition(a.key) || {};
      const bDef = attributeDefinition(b.key) || {};
      if (sort === "type") return (aDef.attribute_class || a.section).localeCompare(bDef.attribute_class || b.section) || a.key.localeCompare(b.key);
      if (sort === "effect") return (aDef.effect_type || "").localeCompare(bDef.effect_type || "") || a.key.localeCompare(b.key);
      return a.key.localeCompare(b.key);
    });
    const attributeList = el("attributeEntries");
    if (!entries.length) {
      attributeList.innerHTML = '<p class="empty-attributes">This item has no item-specific attributes. Its inherited prefab fields are not editable as direct item attributes.</p>';
    } else {
      attributeList.innerHTML = entries.map((entry, index) => {
        const definition = attributeDefinition(entry.key) || {};
        const sectionName = entry.section === "static_attrs" ? "Static" : "Attribute";
        const meta = definition.attribute_class || sectionName;
        const effect = definition.effect_type || sectionName;
        let liveState = "";
        const normalizedValue = valueText(entry.value).toLowerCase();
        if (entry.section === "static_attrs" && entry.key.toLowerCase() === "is marketable") {
          liveState = ["1", "true", "yes"].includes(normalizedValue) ? "Marketable" : "Not marketable";
        } else if (entry.section === "static_attrs" && entry.key.toLowerCase() === "cosmetic_allow_inspect") {
          liveState = ["1", "true", "yes"].includes(normalizedValue) ? "Inspect allowed" : "Inspect not allowed";
        }
        const explanation = definition.description || (definition.hidden === "1"
          ? "TF2 marks this as a hidden attribute; no description is available in the local schema."
          : "No English description is available in the local TF2 schema.");
        return `<div class="attribute-row" title="${escapeHtml(attributeExplanation(definition, entry.key))}">
            <span class="block-copy-pick"><input class="block-attribute" type="checkbox" data-section="${entry.section}" data-key="${escapeHtml(entry.key)}" aria-label="Copy ${escapeHtml(entry.key)} into a reusable block"><span>Copy</span></span>
              <strong>${escapeHtml(entry.key)}${changedKeys(item, entry.section).includes(entry.key) ? '<span class="change-marker" title="This value differs from the live TF2 schema.">Changed</span>' : ""}</strong>
            <code>${escapeHtml(meta)}</code>
            <span class="attribute-value" title="${escapeHtml(valueText(entry.value))}">${escapeHtml(valueText(entry.value))}${liveState ? `<span class="live-state">${escapeHtml(liveState)}</span>` : ""}</span>
          <span class="section-note">${escapeHtml(effect)}</span>
          <span class="attribute-description">${escapeHtml(explanation)}</span>
        </div>`;
      }).join("");
    }

    const props = Object.entries(item.properties || {})
      .sort(([a], [b]) => a.localeCompare(b));
    const compatibility = el("compatibilityEntries");
    compatibility.replaceChildren();
    const customProperties = Object.entries(state.customProperties);
    compatibility.hidden = !props.length && !customProperties.length;
    if (compatibility.hidden) return;
    const heading = document.createElement("h4");
    heading.className = "compatibility-heading";
    heading.textContent = "Compatibility properties";
    compatibility.append(heading);
    props.forEach(([key, value]) => {
      const row = document.createElement("label");
      const isChanged = changedKeys(item, "properties").includes(key);
      row.className = `compatibility-row${isChanged ? " changed" : ""}`;
      const pick = document.createElement("span");
      pick.className = "block-copy-pick";
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.className = "block-property";
      checkbox.dataset.key = key;
      checkbox.setAttribute("aria-label", `Copy ${key} into a reusable block`);
      const pickLabel = document.createElement("span");
      pickLabel.textContent = "Copy";
      pick.append(checkbox, pickLabel);
      const name = document.createElement("strong");
      name.textContent = key;
      const rawValue = document.createElement("code");
      rawValue.textContent = valueText(value);
      row.append(pick, name, rawValue);
      if (isChanged) row.append(makeChangeMarker());
      compatibility.append(row);
    });
    customProperties.forEach(([key, value]) => {
      const row = document.createElement("div");
      row.className = "compatibility-row";
      const pick = document.createElement("span");
      pick.className = "block-copy-pick";
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.className = "custom-property-toggle";
      checkbox.dataset.key = key;
      checkbox.checked = true;
      checkbox.setAttribute("aria-label", `Copy custom ${key} property into a reusable block`);
      const pickLabel = document.createElement("span");
      pickLabel.textContent = "Copy";
      pick.append(checkbox, pickLabel);
      const name = document.createElement("strong");
      name.textContent = key;
      const rawValue = document.createElement("code");
      rawValue.textContent = value;
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "tiny-button";
      remove.textContent = "Remove";
      remove.addEventListener("click", () => {
        delete state.customProperties[key];
        renderAttributeEditor(item);
      });
      row.append(pick, name, rawValue, remove);
      compatibility.append(row);
    });
  }

  function renderBlockShelf() {
    const shelf = el("blockShelf");
    shelf.replaceChildren();
    if (!state.blocks.length) {
      const note = document.createElement("p");
      note.className = "muted";
      note.textContent = "Save an attribute block to reuse it.";
      shelf.append(note);
      return;
    }
    state.blocks.forEach((block) => {
      const patch = block.patch || {};
      const attributeCount = Object.keys(patch.attributes || {}).length;
      const staticCount = Object.keys(patch.static_attrs || {}).length;
      const propertyCount = Object.keys(patch.properties || {}).length;
      const card = document.createElement("article");
      card.className = "block-card";
      const title = document.createElement("strong");
      title.textContent = block.title;
      const summary = document.createElement("span");
      summary.className = "block-summary";
      summary.textContent = `${attributeCount} attributes · ${staticCount} static · ${propertyCount} compatibility fields`;
      const explanations = [];
      for (const section of ["attributes", "static_attrs"]) {
        for (const [key, value] of Object.entries(patch[section] || {})) {
          const definition = attributeDefinition(key) || {};
          const details = [
            attributeExplanation(definition, key),
            definition.attribute_class ? `Class: ${definition.attribute_class}` : "",
            `Value: ${typeof value === "object" ? JSON.stringify(value) : String(value)}`
          ].filter(Boolean);
          explanations.push(`${key}: ${details.join(" · ")}`);
        }
      }
      for (const [key, value] of Object.entries(patch.properties || {})) {
        explanations.push(`${key}: compatibility property (${String(value)})`);
      }
      card.title = explanations.length
        ? explanations.join("\n")
        : "This reusable block has no attribute explanation available.";
      summary.title = card.title;
      const source = document.createElement("span");
      source.className = "block-source";
      source.textContent = `Source: ${block.source_name} (#${block.source_id})`;
      source.title = card.title;
      const apply = document.createElement("button");
      apply.className = "tiny-button";
      apply.type = "button";
      apply.textContent = `Apply to ${state.targets.size} target${state.targets.size === 1 ? "" : "s"}`;
      apply.disabled = !state.targets.size;
      apply.addEventListener("click", () => applyBlock(block.id));
      card.append(title, summary, source, apply);
      shelf.append(card);
    });
  }

  function renderSounds(item) {
    const container = el("soundList");
    container.replaceChildren();
    state.audioUrls.forEach((url) => URL.revokeObjectURL(url));
    state.audioUrls.clear();
    soundFields.forEach((field) => {
      if (!state.soundFieldsUsed.has(field)) return;
      const reference = item.sounds[field] || "";
      const isChanged = changedKeys(item, "item_fields").includes(field);
      const row = document.createElement("div");
      row.className = `sound-row${isChanged ? " changed" : ""}`;
      const label = document.createElement("span");
      label.className = "sound-name";
      label.textContent = ({
        sound_pickup: "pickup",
        mouse_pressed_sound: "button"
      })[field] || field.replace("_sound", "").replace(/_/g, " ");
      if (isChanged) label.append(makeChangeMarker());
      const audio = document.createElement("audio");
      audio.controls = true;
      audio.preload = "none";
      audio.hidden = !reference;
      const button = document.createElement("button");
      button.className = "sound-preview";
      button.type = "button";
      button.textContent = "Load preview";
      button.disabled = !reference;
      const path = document.createElement("span");
      path.className = "sound-path";
      path.textContent = reference ? `Schema reference: ${reference}` : "No sound reference set.";
      button.addEventListener("click", async () => {
        button.disabled = true;
        button.textContent = "Loading…";
        try {
          const response = await fetch(`/api/sound?reference=${encodeURIComponent(reference)}`);
          if (!response.ok) {
            let payload = {};
            try { payload = await response.json(); } catch {}
            path.textContent = `${payload.error || "Audio file unavailable."}${payload.asset_path ? ` Asset: ${payload.asset_path}` : ` Sound event: ${reference}`}`;
            button.textContent = "Unavailable";
            return;
          }
          const blob = await response.blob();
          const objectUrl = URL.createObjectURL(blob);
          state.audioUrls.set(audio, objectUrl);
          audio.src = objectUrl;
          audio.hidden = false;
          path.textContent = `Local asset: ${decodeURIComponent(response.headers.get("X-Asset-Path") || reference)}`;
          button.textContent = "Play";
          await audio.play();
        } catch (error) {
          path.textContent = `Could not load preview: ${error.message}`;
          button.textContent = "Retry";
        } finally {
          button.disabled = false;
        }
      });
      audio.addEventListener("ended", () => { button.textContent = "Play again"; });
      const replacement = document.createElement("select");
      replacement.className = "field sound-source";
      replacement.setAttribute("aria-label", `Choose a replacement ${label.textContent} sound`);
      replacement.add(new Option("Choose a local sound…", ""));
      state.soundReferences.forEach((soundReference) => {
        replacement.add(new Option(soundReference, soundReference));
      });
      if (reference && !state.soundReferences.includes(reference)) {
        const current = new Option(`Current (not available for selection): ${reference}`, reference);
        current.disabled = true;
        replacement.add(current);
      }
      replacement.value = reference;
      const replacementControl = enhanceSearchableSelect(replacement);
      replacement.addEventListener("change", () => {
        if (replacement.value) saveItemEdits(item.defindex, { item_fields: { [field]: replacement.value } });
      });
      const clearButton = document.createElement("button");
      clearButton.className = "sound-clear tiny-button";
      clearButton.type = "button";
      clearButton.textContent = "Clear";
      clearButton.disabled = !reference;
      clearButton.title = `Remove this item's ${label.textContent} sound reference from the draft.`;
      clearButton.addEventListener("click", () => {
        saveItemEdits(item.defindex, { item_fields: { [field]: "" } });
      });
      const resetButton = document.createElement("button");
      resetButton.className = "sound-clear tiny-button sound-reset";
      resetButton.type = "button";
      resetButton.textContent = "Reset";
      resetButton.disabled = !isChanged;
      resetButton.title = "Restore this sound field to the current schema source value.";
      resetButton.addEventListener("click", () => resetItemSection(`sound:${field}`));
      row.append(label, audio, button, replacementControl, clearButton, resetButton, path);
      container.append(row);
    });
  }

  function updateSoundLibraryTarget() {
    const item = state.items.find((candidate) => candidate.defindex === state.selectedId);
    el("soundLibraryTarget").textContent = item
      ? `${item.name} (#${item.defindex})`
      : "Choose an item in Item Workshop first";
    el("soundLibraryField").disabled = !item;
  }

  function switchWorkspacePage(page) {
    state.workspacePage = page;
    document.querySelectorAll(".page-items").forEach((section) => {
      section.hidden = page !== "items";
    });
    el("soundLibraryPage").hidden = page !== "sounds";
    document.querySelectorAll(".workspace-tab").forEach((tab) => {
      const active = tab.dataset.workspacePage === page;
      tab.classList.toggle("active", active);
      tab.setAttribute("aria-current", String(active));
    });
    if (page === "sounds") {
      updateSoundLibraryTarget();
      renderSoundLibraryResults();
      el("soundLibrarySearch").focus();
    } else {
      const audio = el("soundLibraryAudio");
      audio.pause();
      audio.removeAttribute("src");
      audio.load();
      audio.hidden = true;
      el("soundLibraryStatus").hidden = true;
      if (state.previewAudioUrl) URL.revokeObjectURL(state.previewAudioUrl);
      state.previewAudioUrl = null;
    }
  }

  function renderSoundLibraryResults() {
    const query = el("soundLibrarySearch").value.trim().toLocaleLowerCase();
    const matches = state.soundReferences.filter((reference) =>
      reference.toLocaleLowerCase().includes(query)
    );
    const maxResults = 100;
    const visible = matches.slice(0, maxResults);
    el("soundLibraryCount").textContent = matches.length > maxResults
      ? `Showing the first ${maxResults} of ${matches.length.toLocaleString()} matches. Refine your search to see more.`
      : `${matches.length.toLocaleString()} sound${matches.length === 1 ? "" : "s"} found`;
    const results = el("soundLibraryResults");
    results.replaceChildren();
    if (!visible.length) {
      const empty = document.createElement("p");
      empty.className = "muted";
      empty.textContent = query
        ? "No local sound references match that search."
        : "No local TF2 sound references were found. Sync with a TF2 installation first.";
      results.append(empty);
      return;
    }
    visible.forEach((reference) => {
      const row = document.createElement("div");
      row.className = "sound-library-row";
      const name = document.createElement("code");
      name.className = "sound-library-reference";
      name.textContent = reference;
      name.title = reference;
      const example = state.soundItemExamples[reference];
      const itemPreview = document.createElement("div");
      itemPreview.className = "sound-library-item";
      if (example) {
        const icon = document.createElement("span");
        icon.className = `sound-library-item-icon${example.image_inventory ? "" : " icon-fallback"}`;
        if (example.image_inventory) {
          const image = document.createElement("img");
          image.src = `/api/icon?id=${example.defindex}`;
          image.alt = "";
          image.loading = "lazy";
          image.addEventListener("error", () => {
            image.hidden = true;
            icon.classList.add("icon-fallback");
          }, { once: true });
          icon.append(image);
        }
        const itemName = document.createElement("span");
        itemName.className = "sound-library-item-name";
        itemName.textContent = `${example.name} (#${example.defindex})`;
        itemName.title = `${example.name} (#${example.defindex}); schema field: ${example.field}`;
        itemPreview.append(icon, itemName);
      } else {
        itemPreview.classList.add("sound-library-no-item");
        itemPreview.textContent = "No item directly references this sound";
      }
      const preview = document.createElement("button");
      preview.className = "tiny-button";
      preview.type = "button";
      preview.dataset.soundPreview = reference;
      preview.textContent = "Play";
      const use = document.createElement("button");
      use.className = "tiny-button sound-use";
      use.type = "button";
      use.dataset.soundUse = reference;
      use.textContent = "Apply to selected item";
      use.disabled = !state.items.some((item) => item.defindex === state.selectedId);
      row.append(name, itemPreview, preview, use);
      results.append(row);
    });
  }

  async function previewLibrarySound(reference, button) {
    const status = el("soundLibraryStatus");
    const audio = el("soundLibraryAudio");
    button.disabled = true;
    button.textContent = "Loading…";
    status.hidden = true;
    try {
      const response = await fetch(`/api/sound?reference=${encodeURIComponent(reference)}`);
      if (!response.ok) {
        let payload = {};
        try { payload = await response.json(); } catch {}
        throw new Error(
          `${payload.error || `Audio request failed (${response.status})`}` +
          `${payload.asset_path ? ` Asset: ${payload.asset_path}` : ` Sound reference: ${reference}`}`
        );
      }
      const blob = await response.blob();
      if (state.previewAudioUrl) URL.revokeObjectURL(state.previewAudioUrl);
      state.previewAudioUrl = URL.createObjectURL(blob);
      audio.pause();
      audio.src = state.previewAudioUrl;
      audio.hidden = false;
      audio.load();
      await audio.play();
      const assetPath = decodeURIComponent(response.headers.get("X-Asset-Path") || reference);
      status.textContent = `Playing: ${assetPath}`;
      status.hidden = false;
      button.textContent = "Play again";
    } catch (error) {
      status.textContent = `Preview unavailable: ${error.message}`;
      status.hidden = false;
      button.textContent = "Retry";
    } finally {
      button.disabled = false;
    }
  }

  async function startSync() {
    if (state.pendingEdits.size && !window.confirm("You have unsaved item changes. Syncing now will discard them. Continue?")) {
      return;
    }
    const button = el("syncButton");
    button.disabled = true;
    el("syncError").hidden = true;
    try {
      state.categoryRequest += 1;
      await requestJson("/api/sync", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: el("tfPath").value.trim() })
      });
      state.ready = false;
      state.pendingEdits.clear();
      state.items = [];
      state.filtered = [];
      state.selectedId = null;
      controls.forEach((id) => { el(id).disabled = true; });
      el("soundLibraryTab").disabled = true;
      el("classFilter").querySelector(".checkbox-filter-trigger").disabled = true;
      el("categoryFilter").querySelector(".checkbox-filter-trigger").disabled = true;
      el("itemTypeSelect").disabled = true;
      el("saveItemType").disabled = true;
      el("detailContent").hidden = true;
      el("detailEmpty").hidden = false;
      el("itemRows").replaceChildren();
      el("emptyList").hidden = false;
      el("emptyList").textContent = "Reading item definitions from the TF2 installation…";
      el("resultCount").textContent = "Sync in progress";
      await refreshStatus();
      if (!state.statusTimer) state.statusTimer = setInterval(refreshStatus, 900);
    } catch (error) {
      el("syncError").hidden = false;
      el("syncError").textContent = error.message;
      button.disabled = false;
    }
  }

  async function saveSelectedBlock() {
    const item = state.items.find((candidate) => candidate.defindex === state.selectedId);
    if (!item) return;
    const selections = { attributes: [], static_attrs: [], properties: [] };
    document.querySelectorAll(".block-attribute:checked").forEach((checkbox) => {
      selections[checkbox.dataset.section].push(checkbox.dataset.key);
    });
    document.querySelectorAll(".block-property:checked").forEach((checkbox) => {
      selections.properties.push(checkbox.dataset.key);
    });
    document.querySelectorAll(".custom-property-toggle:checked").forEach((checkbox) => {
      selections.properties.push(checkbox.dataset.key);
    });
    const customProperties = {};
    document.querySelectorAll(".custom-property-toggle:checked").forEach((checkbox) => {
      customProperties[checkbox.dataset.key] = state.customProperties[checkbox.dataset.key];
    });
    el("editorError").hidden = true;
    const title = el("blockName").value.trim() || `${item.name} attribute block`;
    try {
      const block = await requestJson("/api/blocks", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          source_id: item.defindex,
          title,
          selections,
          custom_properties: customProperties
        })
      });
      state.blocks.push(block);
      el("blockName").value = "";
      renderBlockShelf();
      el("exportMessage").hidden = false;
      el("exportMessage").textContent = `Saved "${block.title}" from ${item.name}. Check target items, then apply this block.`;
    } catch (error) {
      el("editorError").hidden = false;
      el("editorError").textContent = error.message;
    }
  }

  async function applyBlock(blockId) {
    el("editorError").hidden = true;
    const unsavedTargets = [...state.targets].filter((defindex) => state.pendingEdits.has(defindex));
    if (unsavedTargets.length) {
      el("editorError").hidden = false;
      el("editorError").textContent = "Save pending item changes before applying a block to those targets.";
      return;
    }
    const block = state.blocks.find((candidate) => candidate.id === blockId);
    if (!block || !state.targets.size) return;
    const knownItems = new Map([
      ...[...state.categoryCache.values()].flat(),
      ...(state.allItemsCache || [])
    ].map((item) => [item.defindex, item]));
    const targetNames = [...state.targets].slice(0, 5).map((defindex) => {
      const item = knownItems.get(defindex);
      return item ? `${item.name} (#${defindex})` : `#${defindex}`;
    });
    const remaining = state.targets.size - targetNames.length;
    const patch = block.patch || {};
    const valueCount = ["attributes", "static_attrs", "properties"]
      .reduce((count, section) => count + Object.keys(patch[section] || {}).length, 0);
    const confirmation = [
      `Apply "${block.title}" (${valueCount} selected values) to ${state.targets.size} target item${state.targets.size === 1 ? "" : "s"}?`,
      "",
      `Targets: ${targetNames.join(", ")}${remaining > 0 ? `, and ${remaining} more` : ""}.`,
      "",
      "This creates Workshop draft edits only. It does not change installed TF2 files."
    ].join("\n");
    if (!window.confirm(confirmation)) return;
    try {
      const result = await requestJson("/api/editor/apply", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ block_id: blockId, target_ids: [...state.targets] })
      });
      const [, status] = await Promise.all([
        refreshCurrentItems(),
        requestJson("/api/status")
      ]);
      state.editor.draft_count = status.draft_count;
      el("draftCount").textContent = `${status.draft_count.toLocaleString()} edited item${status.draft_count === 1 ? "" : "s"}`;
      el("exportButton").disabled = state.pendingEdits.size > 0;
      applyFilters();
      if (state.selectedId !== null) selectItem(state.selectedId, false);
      el("exportMessage").hidden = false;
      el("exportMessage").textContent = `Applied "${block.title}" to ${result.applied} item${result.applied === 1 ? "" : "s"} as a draft. The installed TF2 schema is untouched.`;
      renderBlockShelf();
    } catch (error) {
      el("editorError").hidden = false;
      el("editorError").textContent = error.message;
    }
  }

  function saveItemEdits(defindex, changes) {
    const item = state.items.find((candidate) => candidate.defindex === defindex);
    if (!item) return false;
    const patch = pendingPatch(defindex);
    for (const [section, values] of Object.entries(changes)) {
      patch[section] = { ...(patch[section] || {}), ...values };
    }
    state.pendingEdits.set(defindex, patch);
    applyPendingPatch(item);
    if (patch.item_fields?.item_type_name && el("typeFilter").value !== item.type) {
      el("typeFilter").value = "";
    }
    el("editorError").hidden = true;
    el("exportMessage").hidden = false;
    el("exportMessage").textContent = `Unsaved changes for ${item.name}. Select Save item changes to keep them in your Workshop draft.`;
    populateFilters();
    applyFilters();
    selectItem(defindex, false);
    return true;
  }

  function addSchemaAttribute() {
    const item = state.items.find((candidate) => candidate.defindex === state.selectedId);
    const name = el("addAttributeSelect").value;
    const value = el("addAttributeValue").value.trim();
    const definition = attributeDefinition(name);
    if (!item) {
      el("editorError").hidden = false;
      el("editorError").textContent = "Select an item before adding an attribute.";
      return;
    }
    if (!definition) {
      el("editorError").hidden = false;
      el("editorError").textContent = "Choose an attribute from the local TF2 schema.";
      return;
    }
    if (!value) {
      el("editorError").hidden = false;
      el("editorError").textContent = "Enter a value for the selected attribute.";
      return;
    }
    if (definition.stored_as_integer === "1" && !/^[+-]?\d+$/.test(value)) {
      el("editorError").hidden = false;
      el("editorError").textContent = "This attribute stores an integer; enter a whole-number value.";
      return;
    }
    if (saveItemEdits(item.defindex, {
      attributes: { [name]: { value } }
    })) {
      el("addAttributeValue").value = "";
      el("addAttributeSelect").value = "";
      syncSearchableSelect(el("addAttributeSelect"));
      el("addAttributeHelp").textContent = "Choose a schema attribute to see its description and value format.";
    }
  }

  async function saveCurrentItem() {
    const defindex = state.selectedId;
    const item = state.items.find((candidate) => candidate.defindex === defindex);
    const patch = pendingPatch(defindex);
    if (!item || !hasPendingChanges(item)) return;
    const button = el("saveItemButton");
    button.disabled = true;
    el("editorError").hidden = true;
    try {
      await requestJson("/api/editor/item", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ defindex, ...patch })
      });
      if (patch.attributes) {
        const categoryItems = await requestJson(
          `/api/items?category=${encodeURIComponent(item.category)}`
        );
        const savedItem = categoryItems.find((candidate) => candidate.defindex === defindex);
        const missingAttributes = Object.entries(patch.attributes).filter(([key, value]) =>
          String(savedItem?.attributes?.[key]?.value ?? "") !== String(value.value ?? "")
        );
        if (missingAttributes.length) {
          throw new Error(
            `The server did not confirm saving ${missingAttributes.map(([key]) => key).join(", ")}. Your unsaved change has been kept; try restarting TF2 Schema Workshop and saving again.`
          );
        }
      }
      const [, status] = await Promise.all([
        refreshCurrentItems(),
        requestJson("/api/status")
      ]);
      state.pendingEdits.delete(defindex);
      state.editor.draft_count = status.draft_count;
      el("draftCount").textContent = `${status.draft_count.toLocaleString()} edited item${status.draft_count === 1 ? "" : "s"}`;
      el("exportButton").disabled = state.pendingEdits.size > 0;
      populateFilters();
      applyFilters();
      if (state.items.some((candidate) => candidate.defindex === defindex)) selectItem(defindex, false);
      el("exportMessage").hidden = false;
      el("exportMessage").textContent = `Saved changes for ${item.name} to the Workshop draft. The live TF2 schema is unchanged.`;
    } catch (error) {
      el("editorError").hidden = false;
      el("editorError").textContent = error.message;
    } finally {
      button.disabled = false;
    }
  }

  async function revertCurrentItem() {
    if (state.selectedId === null) return;
    const item = state.items.find((candidate) => candidate.defindex === state.selectedId);
    if (!item) return;
    if (!window.confirm(`Revert all Workshop draft changes for "${item.name}" and restore its current schema source values? Previously saved schema copies will not be changed.`)) {
      return;
    }
    const hadUnsavedChanges = state.pendingEdits.has(item.defindex);
    const button = el("revertItemButton");
    button.disabled = true;
    el("editorError").hidden = true;
    try {
      const result = await requestJson("/api/editor/revert", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ defindex: item.defindex })
      });
      state.pendingEdits.delete(item.defindex);
      const [, status] = await Promise.all([
        refreshCurrentItems(),
        requestJson("/api/status")
      ]);
      state.editor.draft_count = status.draft_count;
      el("draftCount").textContent = `${status.draft_count.toLocaleString()} edited item${status.draft_count === 1 ? "" : "s"}`;
      el("exportButton").disabled = state.pendingEdits.size > 0;
      populateFilters();
      applyFilters();
      if (state.items.some((candidate) => candidate.defindex === item.defindex)) selectItem(item.defindex, false);
      el("exportMessage").hidden = false;
      el("exportMessage").textContent = result.reverted || hadUnsavedChanges
        ? `Reverted all Workshop changes for ${item.name}. The live TF2 schema was never changed.`
        : `${item.name} had no Workshop changes to revert.`;
    } catch (error) {
      el("editorError").hidden = false;
      el("editorError").textContent = error.message;
    } finally {
      button.disabled = false;
    }
  }

  function saveItemType() {
    const customType = el("newItemType").value.trim();
    const value = customType || el("itemTypeSelect").value;
    if (state.selectedId === null) {
      el("editorError").hidden = false;
      el("editorError").textContent = "Select an item before editing its type.";
      return;
    }
    if (saveItemEdits(state.selectedId, { item_fields: { item_type_name: value } })) {
      el("newItemType").value = "";
    }
  }

  async function showItemsOfType(type) {
    if (!type) return;
    try {
      if (!state.allItemsCache) state.allItemsCache = await requestJson("/api/items");
      state.pendingEdits.forEach((patch, defindex) => {
        const item = state.allItemsCache.find((candidate) => candidate.defindex === defindex);
        if (item) applyPendingPatch(item);
      });
      state.listView = "all";
      document.querySelectorAll(".item-view-tab").forEach((tab) => {
        const active = tab.dataset.itemView === "all";
        tab.classList.toggle("active", active);
        tab.setAttribute("aria-pressed", String(active));
      });
      state.selectedCategories = new Set(state.editor.categories.map(([id]) => id));
      state.selectedClasses.clear();
      state.items = state.allItemsCache;
      state.categoryItems = state.allItemsCache;
      state.hideEdited = false;
      el("hideEditedCheckbox").checked = false;
      el("searchInput").value = "";
      el("slotFilter").value = "";
      el("attributeFilter").value = "";
      renderCheckboxFilter("class");
      renderCheckboxFilter("category");
      populateFilters();
      el("typeFilter").value = type;
      syncSearchableSelect(el("typeFilter"));
      applyFilters();
      el("itemViewport").scrollTop = 0;
    } catch (error) {
      el("syncError").hidden = false;
      el("syncError").textContent = error.message;
    }
  }

  async function exportDraftCopy() {
    const button = el("exportButton");
    button.disabled = true;
    el("exportMessage").hidden = true;
    try {
      const result = await requestJson("/api/editor/export", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}"
      });
      if (result.cancelled) return;
      el("exportMessage").hidden = false;
      el("exportMessage").textContent = `Saved a separate schema copy. The installed TF2 folder was not changed: ${result.path}`;
    } catch (error) {
      el("editorError").hidden = false;
      el("editorError").textContent = error.message;
    } finally {
      button.disabled = false;
    }
  }

  async function openSchemaCopy() {
    try {
      if (state.pendingEdits.size && !window.confirm(
        "You have unsaved item changes. Opening a schema copy will discard them. Continue?"
      )) return;
      const status = await requestJson("/api/status");
      if (status.draft_count && !window.confirm(
        "The selected copy will be compared with the currently synced TF2 schema and its changes imported into the Workshop draft. Existing drafts are kept; imported values replace any existing draft values for the same fields. Continue?"
      )) return;
      el("syncError").hidden = true;
      const result = await requestJson("/api/editor/open", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}"
      });
      if (result.cancelled) return;
      state.pendingEdits.clear();
      state.targets.clear();
      state.ready = false;
      await loadItems();
      await refreshStatus();
      el("exportMessage").hidden = false;
      el("exportMessage").textContent =
        `Imported changes for ${result.imported_item_count.toLocaleString()} item${result.imported_item_count === 1 ? "" : "s"} from ${result.path}, compared against the currently synced TF2 schema.`;
    } catch (error) {
      el("syncError").hidden = false;
      el("syncError").textContent = error.message;
    }
  }

  function addCustomProperty() {
    const key = el("customPropertyName").value.trim();
    const value = el("customPropertyValue").value.trim();
    if (!key || !/(compat|pyro|vision|assist)/i.test(key)) {
      el("editorError").hidden = false;
      el("editorError").textContent = "Property keys must identify compatibility, Pyroland, vision, or assist fields.";
      return;
    }
    if (!value) {
      el("editorError").hidden = false;
      el("editorError").textContent = "Enter a value for the compatibility property.";
      return;
    }
    state.customProperties[key] = value;
    el("customPropertyName").value = "";
    el("customPropertyValue").value = "";
    el("editorError").hidden = true;
    const item = state.items.find((candidate) => candidate.defindex === state.selectedId);
    if (item) renderAttributeEditor(item);
  }

  function setTarget(defindex, enabled) {
    if (enabled) state.targets.add(defindex);
    else state.targets.delete(defindex);
    renderRows(el("itemViewport").scrollTop);
    renderBlockShelf();
  }

  function clearPendingSection(defindex, section) {
    const patch = { ...pendingPatch(defindex) };
    const removeFields = (patchSection, fields) => {
      if (!patch[patchSection]) return;
      if (fields) fields.forEach((field) => { delete patch[patchSection][field]; });
      else delete patch[patchSection];
      if (patch[patchSection] && !Object.keys(patch[patchSection]).length) delete patch[patchSection];
    };
    if (section === "type") removeFields("item_fields", ["item_type_name"]);
    else if (section === "sounds") removeFields("item_fields", soundFields);
    else if (section.startsWith("sound:")) removeFields("item_fields", [section.slice(6)]);
    else if (section === "attributes") {
      removeFields("attributes");
      removeFields("properties");
      const staticFields = Object.keys(patch.static_attrs || {}).filter((field) => field.toLowerCase() !== "is marketable");
      removeFields("static_attrs", staticFields);
    } else if (section === "capabilities") {
      removeFields("capabilities");
      const marketability = Object.keys(patch.static_attrs || {}).filter((field) => field.toLowerCase() === "is marketable");
      removeFields("static_attrs", marketability);
    }
    if (Object.keys(patch).length) state.pendingEdits.set(defindex, patch);
    else state.pendingEdits.delete(defindex);
  }

  async function resetItemSection(section) {
    const defindex = state.selectedId;
    const item = state.items.find((candidate) => candidate.defindex === defindex);
    if (!item || !sectionHasChanges(item, section)) return;
    const description = section.startsWith("sound:")
      ? `${section.slice(6).replace(/_/g, " ")} sound`
      : ({
        type: "item type",
        sounds: "item sounds",
        attributes: "item attributes and compatibility properties",
        capabilities: "item capabilities and marketability"
      })[section];
    if (!window.confirm(`Reset ${description} for "${item.name}" to its current schema source values?`)) return;
    el("editorError").hidden = true;
    try {
      const result = await requestJson("/api/editor/reset-section", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ defindex, section })
      });
      clearPendingSection(defindex, section);
      const [, status] = await Promise.all([
        refreshCurrentItems(),
        requestJson("/api/status")
      ]);
      state.editor.draft_count = status.draft_count;
      el("draftCount").textContent = `${status.draft_count.toLocaleString()} edited item${status.draft_count === 1 ? "" : "s"}`;
      el("exportButton").disabled = state.pendingEdits.size > 0;
      if (state.items.some((candidate) => candidate.defindex === defindex)) selectItem(defindex, false);
      el("exportMessage").hidden = false;
      el("exportMessage").textContent = `Reset ${description} for ${item.name}. Other item changes are preserved; the installed TF2 schema is untouched.`;
      return result;
    } catch (error) {
      el("editorError").hidden = false;
      el("editorError").textContent = error.message;
    }
  }

  async function browseForFolder() {
    el("syncError").hidden = true;
    try {
      const result = await requestJson("/api/browse", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}"
      });
      if (result.path) el("tfPath").value = result.path;
    } catch (error) {
      el("syncError").hidden = false;
      el("syncError").textContent = error.message;
    }
  }

  el("searchInput").addEventListener("input", applyFilters);
  el("hideEditedCheckbox").addEventListener("change", (event) => {
    state.hideEdited = event.currentTarget.checked;
    applyFilters();
  });
  document.querySelectorAll(".item-view-tab").forEach((tab) => {
    tab.addEventListener("click", () => setItemListView(tab.dataset.itemView));
  });
  el("slotFilter").addEventListener("change", applyFilters);
  el("typeFilter").addEventListener("change", applyFilters);
  el("attributeFilter").addEventListener("change", applyFilters);
  el("viewTypeItems").addEventListener("click", () => {
    const item = state.items.find((candidate) => candidate.defindex === state.selectedId);
    if (!item || !item.type) return;
    showItemsOfType(item.type);
  });
  el("saveItemType").addEventListener("click", saveItemType);
  el("newItemType").addEventListener("keydown", (event) => {
    if (event.key === "Enter") saveItemType();
  });
  el("sortFilter").addEventListener("change", applyFilters);
  el("attributeSort").addEventListener("change", () => {
    const item = state.items.find((candidate) => candidate.defindex === state.selectedId);
    if (item) renderAttributeEditor(item);
  });
  el("addAttributeSelect").addEventListener("change", () => {
    const definition = attributeDefinition(el("addAttributeSelect").value);
    const value = el("addAttributeHelp");
    if (!definition) {
      value.textContent = "Choose a schema attribute to see its description and value format.";
      return;
    }
    const description = attributeExplanation(definition, definition.name);
    const valueType = definition.stored_as_integer === "1" ? "Whole-number value required." : "Enter the value expected by this attribute.";
    value.textContent = `${description} ${valueType} Class: ${definition.attribute_class || "unspecified"}.`;
  });
  el("addAttributeButton").addEventListener("click", addSchemaAttribute);
  el("addAttributeValue").addEventListener("keydown", (event) => {
    if (event.key === "Enter") addSchemaAttribute();
  });
  el("itemViewport").addEventListener("scroll", (event) => renderRows(event.currentTarget.scrollTop), { passive: true });
  el("itemRows").addEventListener("click", (event) => {
    const row = event.target.closest(".item-row");
    if (row && event.target.closest(".row-open")) selectItem(Number(row.dataset.id));
  });
  el("itemRows").addEventListener("change", (event) => {
    if (event.target.matches(".target-toggle")) {
      const row = event.target.closest(".item-row");
      if (row) setTarget(Number(row.dataset.id), event.target.checked);
    }
  });
  el("syncButton").addEventListener("click", startSync);
  el("browseButton").addEventListener("click", browseForFolder);
  document.querySelectorAll(".workspace-tab").forEach((tab) => {
    tab.addEventListener("click", () => switchWorkspacePage(tab.dataset.workspacePage));
  });
  el("backToItems").addEventListener("click", () => switchWorkspacePage("items"));
  el("soundLibrarySearch").addEventListener("input", renderSoundLibraryResults);
  el("soundLibraryResults").addEventListener("click", (event) => {
    const previewButton = event.target.closest("button[data-sound-preview]");
    if (previewButton) {
      previewLibrarySound(previewButton.dataset.soundPreview, previewButton);
      return;
    }
    const useButton = event.target.closest("button[data-sound-use]");
    if (!useButton) return;
    const defindex = state.selectedId;
    const field = el("soundLibraryField").value;
    const item = state.items.find((candidate) => candidate.defindex === defindex);
    if (!item) {
      el("soundLibraryStatus").textContent = "Choose an item in Item Workshop first, then return to the Sound Library.";
      el("soundLibraryStatus").hidden = false;
      return;
    }
    if (saveItemEdits(defindex, { item_fields: { [field]: useButton.dataset.soundUse } })) {
      switchWorkspacePage("items");
      el("exportMessage").hidden = false;
      el("exportMessage").textContent = `Staged the ${el("soundLibraryField").selectedOptions[0].textContent.toLowerCase()} for ${item.name}. Select Save item changes to keep it in your Workshop draft.`;
    }
  });
  el("soundLibraryField").addEventListener("change", renderSoundLibraryResults);
  el("soundLibraryAudio").addEventListener("ended", () => {
    el("soundLibraryStatus").textContent = "Preview finished.";
  });
  el("saveBlockButton").addEventListener("click", saveSelectedBlock);
  el("saveItemButton").addEventListener("click", saveCurrentItem);
  el("revertItemButton").addEventListener("click", revertCurrentItem);
  el("resetTypeButton").addEventListener("click", () => resetItemSection("type"));
  el("resetSoundsButton").addEventListener("click", () => resetItemSection("sounds"));
  el("resetAttributesButton").addEventListener("click", () => resetItemSection("attributes"));
  el("resetCapabilitiesButton").addEventListener("click", () => resetItemSection("capabilities"));
  el("addCustomProperty").addEventListener("click", addCustomProperty);
  el("exportButton").addEventListener("click", exportDraftCopy);
  el("openSchemaButton").addEventListener("click", openSchemaCopy);
  el("selectAllAttributes").addEventListener("click", () => {
    document.querySelectorAll(".block-attribute, .block-property, .custom-property-toggle")
      .forEach((checkbox) => { checkbox.checked = true; });
  });
  el("toggleCurrentTarget").addEventListener("click", () => {
    if (state.selectedId !== null) setTarget(state.selectedId, !state.targets.has(state.selectedId));
    el("toggleCurrentTarget").textContent = state.targets.has(state.selectedId) ? "Remove target" : "Target inspected item";
  });
  el("selectVisibleTargets").addEventListener("click", () => {
    state.filtered.forEach((item) => state.targets.add(item.defindex));
    renderRows(el("itemViewport").scrollTop);
    renderBlockShelf();
  });
  el("clearTargets").addEventListener("click", () => {
    state.targets.clear();
    renderRows(el("itemViewport").scrollTop);
    renderBlockShelf();
  });
  el("uiSoundsToggle").addEventListener("click", () => {
    uiSoundsEnabled = !uiSoundsEnabled;
    try {
      window.localStorage.setItem("tf2-workshop-hover-sounds", uiSoundsEnabled ? "on" : "off");
    } catch (error) {
      console.debug("Could not save the UI sound preference:", error.message);
    }
    updateUiSoundsToggle();
  });
  el("uiSoundVolume").addEventListener("input", (event) => {
    uiSoundVolume = Number(event.currentTarget.value) / 100;
    updateUiSoundVolume();
    try {
      window.localStorage.setItem("tf2-workshop-hover-volume", event.currentTarget.value);
    } catch (error) {
      console.debug("Could not save the hover sound volume:", error.message);
    }
  });
  el("itemRows").addEventListener("pointerover", (event) => {
    const row = event.target.closest(".item-row");
    if (row && !row.contains(event.relatedTarget)) playUiSound(uiHoverAudio);
  });
  initializeCheckboxFilters();
  refreshSearchableSelects();
  initializeUiSounds();
  el("tfPath").addEventListener("keydown", (event) => {
    if (event.key === "Enter") startSync();
  });
  window.addEventListener("beforeunload", () => {
    state.audioUrls.forEach((url) => URL.revokeObjectURL(url));
  });

  refreshStatus();
})();
