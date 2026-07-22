# Stage 6: Toggle Panel Enhancements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add three small UI additions to the already-deployed Stage 6 web
app: verdict-category (Pass/Fail/Prohibited) filter checkboxes, a
bilingual strict-vs-lenient explainer, and a visible page title.

**Architecture:** All three additions are inline edits to the existing
three files under `web/` (`index.html`, `style.css`, `app.js`) — no new
files, no build step, no new dependencies. Full design rationale:
`docs/superpowers/specs/2026-07-22-stage6-toggle-panel-enhancements-design.md`.

**Tech Stack:** Plain HTML/CSS/JS (MapLibre GL JS, already loaded).

## Global Constraints

- No backend, no build step for the site itself — plain HTML/CSS/JS, no
  npm/webpack/vite.
- No automated browser/JS tests — this repo has no JS test tooling; JS
  changes are verified by hand against a documented checklist per task
  (same pattern as every other Stage 6 web task).
- Category membership for the filter checkboxes is computed dynamically
  from `currentVerdictPrefix` (`"strict"` or `"lenient"`) — never
  hardcoded to one verdict, per the confirmed design decision.
- The bilingual explainer shows English then Spanish stacked in one
  disclosure — no language switcher, no i18n framework (explicitly out
  of scope per the spec).
- The on-page `<h1>` title text must match the existing `<title>` tag
  text exactly: `ZPAE Café Viability Map`.

---

### Task 1: Verdict-category filter checkboxes

**Files:**
- Modify: `web/index.html`
- Modify: `web/style.css`
- Modify: `web/app.js`

**Interfaces:**
- Consumes: `map`, `currentVerdictPrefix` (from the existing
  `verdict-toggle` listener in `web/app.js`), the `candidate-points` and
  `candidate-disagreement-highlight` layers (added in `map.on("load",
  ...)`).
- Produces: `visibleCategories` (module-level `Set`), `categoryFilterExpression(prefix, visible)`,
  `applyCategoryFilters()` — the last is also called from Task 1's own
  new checkbox listeners and from the existing `verdict-toggle`
  listener (modified in Step 3 below).

- [ ] **Step 1: Add the checkboxes to `web/index.html`**

In `web/index.html`, inside the existing `#toggles` div, add a new block
immediately after the `regulatory-toggle` label (i.e. as the last child
of `#toggles`, replacing the current closing `</div>` of `#toggles`):

```html
  <div id="toggles">
    <label><input type="checkbox" id="verdict-toggle" /> Lenient verdict</label>
    <label><input type="checkbox" id="disagreement-toggle" /> Highlight strict/lenient disagreements</label>
    <label><input type="checkbox" id="regulatory-toggle" /> Show zoning rules</label>
    <div id="category-filters">
      <span>Filter by verdict</span>
      <label><input type="checkbox" id="filter-pass" checked /> Pass</label>
      <label><input type="checkbox" id="filter-fail" checked /> Fail</label>
      <label><input type="checkbox" id="filter-prohibited" checked /> Prohibited</label>
    </div>
  </div>
```

- [ ] **Step 2: Add styling to `web/style.css`**

Append to `web/style.css`:

```css
#category-filters {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-top: 4px;
  padding-top: 8px;
  border-top: 1px solid #eee;
}

#category-filters span {
  font-weight: 600;
  font-size: 12px;
  color: #555;
}
```

- [ ] **Step 3: Add the filter logic to `web/app.js`**

Add this block to `web/app.js` immediately after the existing
`verdictColorExpression` function (i.e. after its closing `}` around
line 31, before `function buildPopupHTML(properties) {`):

```javascript
let visibleCategories = new Set(["pass", "fail", "prohibited"]);

function categoryFilterExpression(prefix, visible) {
  const branches = [];
  if (visible.has("prohibited")) {
    branches.push(["==", ["get", "prohibited_outright"], true]);
  }
  if (visible.has("pass")) {
    branches.push([
      "all",
      ["!=", ["get", "prohibited_outright"], true],
      ["==", ["get", `${prefix}_pass`], true],
    ]);
  }
  if (visible.has("fail")) {
    branches.push([
      "all",
      ["!=", ["get", "prohibited_outright"], true],
      ["==", ["get", `${prefix}_pass`], false],
    ]);
  }
  return ["any", ...branches];
}

function applyCategoryFilters() {
  const categoryFilter = categoryFilterExpression(currentVerdictPrefix, visibleCategories);
  if (map.getLayer("candidate-points")) {
    map.setFilter("candidate-points", categoryFilter);
  }
  if (map.getLayer("candidate-disagreement-highlight")) {
    map.setFilter("candidate-disagreement-highlight", [
      "all",
      ["==", ["get", "interpretations_disagree"], true],
      categoryFilter,
    ]);
  }
}
```

Then, inside the existing `map.on("load", () => { ... })` callback, add
a call to `applyCategoryFilters()` as the last line before the
callback's closing `});` (i.e. immediately after the existing
`map.on("idle", () => hideError());` line, still inside the `load`
callback):

```javascript
  map.on("idle", () => hideError());
  applyCategoryFilters();
});
```

Then, modify the existing `verdict-toggle` listener (currently reading):

```javascript
document.getElementById("verdict-toggle").addEventListener("change", (e) => {
  currentVerdictPrefix = e.target.checked ? "lenient" : "strict";
  if (map.getLayer("candidate-points")) {
    map.setPaintProperty(
      "candidate-points",
      "circle-color",
      verdictColorExpression(currentVerdictPrefix)
    );
  }
});
```

to also reapply the category filters, since flipping strict/lenient can
move the ~32 borderline addresses between Pass and Fail buckets:

```javascript
document.getElementById("verdict-toggle").addEventListener("change", (e) => {
  currentVerdictPrefix = e.target.checked ? "lenient" : "strict";
  if (map.getLayer("candidate-points")) {
    map.setPaintProperty(
      "candidate-points",
      "circle-color",
      verdictColorExpression(currentVerdictPrefix)
    );
  }
  applyCategoryFilters();
});
```

Finally, add three new listeners. Place them immediately after the
existing `disagreement-toggle` listener block (after its closing `});`,
before the `let searchIndex = [];` line):

```javascript
function setupCategoryFilterCheckbox(id, category) {
  document.getElementById(id).addEventListener("change", (e) => {
    if (e.target.checked) {
      visibleCategories.add(category);
    } else {
      visibleCategories.delete(category);
    }
    applyCategoryFilters();
  });
}

setupCategoryFilterCheckbox("filter-pass", "pass");
setupCategoryFilterCheckbox("filter-fail", "fail");
setupCategoryFilterCheckbox("filter-prohibited", "prohibited");
```

- [ ] **Step 4: Check syntax**

Run: `node --check web/app.js`
Expected: no output, exit code 0.

- [ ] **Step 5: Verify in browser**

Serve the site with a Range-request-capable static server (Python's
`http.server` does NOT support Range requests, which PMTiles requires —
use e.g. `npx http-server web -p 8000 --cors -c-1` from the repo root,
or any other server that returns `206 Partial Content` for a `Range`
request):

```bash
npx http-server web -p 8000 --cors -c-1
```

Open `http://localhost:8000`. Expected, in order:
1. All candidate dots visible, all three "Filter by verdict" checkboxes
   checked by default.
2. Uncheck "Fail": red dots disappear; green (pass) and grey
   (prohibited) dots remain.
3. Re-check "Fail", uncheck "Pass": green dots disappear, red and grey
   remain.
4. Uncheck all three: the map shows zero candidate dots (basemap and
   regulatory layers, if enabled, remain visible — this is the expected
   "hide everything" state, not a bug).
5. Re-check all three. Check "Highlight strict/lenient disagreements":
   purple rings appear around the ~32 disagreement dots. Uncheck "Fail":
   confirm any purple ring around a now-hidden red dot also disappears
   (the ring and its dot hide together).
6. With "Highlight..." still on, toggle "Lenient verdict" on and off a
   few times: confirm the set of visible dots updates correctly each
   time (a dot that flips from fail to pass when toggling should
   reappear if "Pass" is checked, even if "Fail" was unchecked).
No console errors at any point.

- [ ] **Step 6: Commit**

```bash
git add web/index.html web/style.css web/app.js
git commit -m "Add verdict-category filter checkboxes (Pass/Fail/Prohibited)"
```

---

### Task 2: Strict/lenient bilingual explainer

**Files:**
- Modify: `web/index.html`
- Modify: `web/style.css`

**Interfaces:**
- None — pure HTML/CSS, no JavaScript.

- [ ] **Step 1: Add the disclosure to `web/index.html`**

In `web/index.html`, insert a `<details>` element immediately after the
`verdict-toggle` label and before the `disagreement-toggle` label inside
`#toggles`:

```html
  <div id="toggles">
    <label><input type="checkbox" id="verdict-toggle" /> Lenient verdict</label>
    <details id="verdict-explainer">
      <summary>What's strict vs. lenient?</summary>
      <p lang="en">Strict counts the full walk from a location's door to the nearest street, plus the street-network distance to the other business. Lenient counts only the street-to-street distance, as if both doors sat right on the road.</p>
      <p lang="es">Estricta cuenta el camino completo desde la puerta del local hasta la calle más cercana, más la distancia por la red de calles hasta el otro negocio. Flexible cuenta solo la distancia calle a calle, como si ambas puertas estuvieran justo sobre la calle.</p>
    </details>
    <label><input type="checkbox" id="disagreement-toggle" /> Highlight strict/lenient disagreements</label>
    <label><input type="checkbox" id="regulatory-toggle" /> Show zoning rules</label>
    <div id="category-filters">
      <span>Filter by verdict</span>
      <label><input type="checkbox" id="filter-pass" checked /> Pass</label>
      <label><input type="checkbox" id="filter-fail" checked /> Fail</label>
      <label><input type="checkbox" id="filter-prohibited" checked /> Prohibited</label>
    </div>
  </div>
```

(This shows the full `#toggles` block as it should read after both Task
1 and Task 2 are applied — Task 1 must be completed first for this
listing to match; if doing Task 2 alone against the pre-Task-1 file,
insert only the `<details>` block in the position shown, leaving the
rest of `#toggles` as it already is.)

- [ ] **Step 2: Add styling to `web/style.css`**

Append to `web/style.css`:

```css
#verdict-explainer {
  font-size: 12px;
  color: #333;
}

#verdict-explainer summary {
  cursor: pointer;
  color: #2563eb;
}

#verdict-explainer p {
  margin: 6px 0 0;
  line-height: 1.4;
}
```

- [ ] **Step 3: Verify in browser**

Refresh `http://localhost:8000` (server from Task 1 still running).
Expected:
1. A collapsed "What's strict vs. lenient?" line appears under the
   "Lenient verdict" checkbox, styled as a link-colored, clickable
   summary.
2. Clicking it expands two short paragraphs, English first then
   Spanish, both legible against the white toggle-panel background.
3. Clicking it again collapses both paragraphs.
No console errors.

- [ ] **Step 4: Commit**

```bash
git add web/index.html web/style.css
git commit -m "Add bilingual strict/lenient explainer"
```

---

### Task 3: Visible page title

**Files:**
- Modify: `web/index.html`
- Modify: `web/style.css`

**Interfaces:**
- None — pure HTML/CSS, no JavaScript.

- [ ] **Step 1: Add the heading to `web/index.html`**

In `web/index.html`, add an `<h1>` as the first child of `#controls`,
immediately before the existing `#search-box` div:

```html
<div id="controls">
  <h1 id="page-title">ZPAE Café Viability Map</h1>
  <div id="search-box">
```

(Nesting the `<h1>` inside `#controls`, rather than as a separate
absolutely-positioned sibling, lets it inherit `#controls`' existing
`display: flex; flex-direction: column; gap: 8px` layout — it stacks
above the search box automatically, top-left, with no extra positioning
math needed.)

- [ ] **Step 2: Add styling to `web/style.css`**

Append to `web/style.css`:

```css
#page-title {
  margin: 0;
  padding: 6px 10px;
  background: white;
  border-radius: 4px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.15);
  font-size: 15px;
  font-weight: 600;
  width: fit-content;
}
```

- [ ] **Step 3: Verify in browser**

Refresh `http://localhost:8000` (server from Task 1 still running).
Expected: a white pill reading "ZPAE Café Viability Map" appears above
the search box, top-left, styled consistently with the search box and
toggle panel below it (matching shadow/border-radius/font). No layout
overlap with the search box or toggles. No console errors.

- [ ] **Step 4: Commit**

```bash
git add web/index.html web/style.css
git commit -m "Add visible page title"
```
