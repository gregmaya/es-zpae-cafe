# Stage 6: Toggle Panel Enhancements Design

**Status:** Approved
**Context:** Post-launch refinements to the Stage 6 web app (see
`2026-07-20-stage6-web-app-design.md` and
`2026-07-21-stage6-web-app.md`), requested after manual browser
verification of the deployed app.

## Goal

Two small, independent additions to the existing `#toggles` panel in
`web/index.html` / `web/app.js`:

1. **Verdict-category filters** — checkboxes to hide/show Pass, Fail, and
   Prohibited candidates independently, to make the map easier to read
   when there are ~9,838 points on screen.
2. **Strict/lenient explainer** — a short, non-technical, bilingual
   (English + Spanish) explanation of what "strict" and "lenient" mean,
   since visitors have no other source for this distinction.

Both are additive UI changes to the existing `web/app.js`; no new files,
no build step, no new dependencies.

## 1. Verdict-category filters

**UI:** three new checkboxes in `#toggles`, below the existing
verdict/disagreement/regulatory toggles, grouped under a small label:

```html
<div id="category-filters">
  <span>Filter by verdict</span>
  <label><input type="checkbox" id="filter-pass" checked /> Pass</label>
  <label><input type="checkbox" id="filter-fail" checked /> Fail</label>
  <label><input type="checkbox" id="filter-prohibited" checked /> Prohibited</label>
</div>
```

All three checked by default (nothing hidden — same as current behavior).

**Behavior:** category membership is computed dynamically from whichever
verdict is currently active, per the confirmed design decision:

- `prohibited_outright == true` → **Prohibited** (regardless of
  strict/lenient).
- else `${currentVerdictPrefix}_pass == true` → **Pass**.
- else → **Fail**.

A module-level `visibleCategories` Set (default `{"pass","fail",
"prohibited"}`) tracks checkbox state. A pure function builds the
MapLibre filter expression:

```javascript
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
```

If `branches` is empty, `["any"]` evaluates to `false` for every
feature — an intentional "hide everything" state when all three boxes
are unchecked, not an error.

This filter is applied to **both** `candidate-points` and
`candidate-disagreement-highlight` (via `map.setFilter(layerId, ...)`),
combining with the highlight layer's existing
`["==", ["get", "interpretations_disagree"], true]` filter using `all`,
so a disagreement ring never appears over a category the user has
hidden:

```javascript
map.setFilter("candidate-disagreement-highlight", [
  "all",
  ["==", ["get", "interpretations_disagree"], true],
  categoryFilterExpression(currentVerdictPrefix, visibleCategories),
]);
```

**Recompute triggers:** the filter is reapplied whenever

- any of the three category checkboxes changes, or
- the existing `verdict-toggle` changes (since flipping strict/lenient
  can move the ~32 borderline addresses between Pass and Fail buckets).

The existing `verdict-toggle` listener gains a call to reapply both
filters after its current `setPaintProperty` call; the new checkboxes'
listeners update `visibleCategories` and reapply both filters.

## 2. Strict/lenient explainer

**UI:** a native `<details>`/`<summary>` disclosure directly under the
existing "Lenient verdict" checkbox — collapsed by default, no
JavaScript required for the show/hide behavior:

```html
<details id="verdict-explainer">
  <summary>What's strict vs. lenient?</summary>
  <p lang="en">Strict counts the full walk from a location's door to the
  nearest street, plus the street-network distance to the other
  business. Lenient counts only the street-to-street distance, as if
  both doors sat right on the road.</p>
  <p lang="es">Estricta cuenta el camino completo desde la puerta del
  local hasta la calle más cercana, más la distancia por la red de
  calles hasta el otro negocio. Flexible cuenta solo la distancia calle
  a calle, como si ambas puertas estuvieran justo sobre la calle.</p>
</details>
```

Both languages are shown stacked (English then Spanish) inside the same
disclosure — this is a small, no-build, no-i18n-framework site, so a
language switcher for one paragraph would be overkill. `lang` attributes
are set per paragraph for accessibility/screen-reader correctness, no
functional behavior depends on them.

No JavaScript changes needed for this part — pure HTML/CSS. `style.css`
gets a few rules to keep the disclosure visually consistent with the
rest of the `#toggles` panel (font size, spacing, matching the existing
box's white background/shadow if it renders outside `#toggles`, or
inherits it if nested inside).

## Testing

No JS test tooling in this repo (existing constraint) — verified by hand
per the existing per-task checklist pattern: load the page, toggle each
category checkbox individually and in combination (including all three
off), toggle strict/lenient with a category unchecked to confirm the
filter follows the active verdict, expand/collapse the explainer.

## Out of scope

- A real i18n system / language switcher.
- Filtering by zone or street classification (only verdict category, per
  this request).
- Persisting checkbox state across page reloads.
