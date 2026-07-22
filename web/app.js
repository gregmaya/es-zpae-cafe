const protocol = new pmtiles.Protocol();
maplibregl.addProtocol("pmtiles", protocol.tile);

const map = new maplibregl.Map({
  container: "map",
  style: "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
  center: [-3.7038, 40.4168],
  zoom: 13,
});

map.addControl(new maplibregl.NavigationControl(), "top-right");

let currentVerdictPrefix = "strict";

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function verdictColorExpression(prefix) {
  return [
    "case",
    ["==", ["get", "prohibited_outright"], true], "#6b7280",
    ["==", ["get", `${prefix}_pass`], true], "#16a34a",
    "#dc2626",
  ];
}

function buildPopupHTML(properties) {
  const prefix = currentVerdictPrefix;
  const pass = properties[`${prefix}_pass`];
  const margin = properties[`${prefix}_margin_m`];
  const verdictText = properties.prohibited_outright
    ? "Prohibited outright (Alta street)"
    : pass
      ? margin === null || margin === undefined
        ? "Pass (no distance requirement)"
        : `Pass (margin ${Number(margin).toFixed(1)}m)`
      : `Fail (short by ${Math.abs(Number(margin)).toFixed(1)}m)`;

  const bindingRotulo = properties[`${prefix}_nearest_binding_rotulo`];
  const overallRotulo = properties[`${prefix}_nearest_overall_rotulo`];
  const competitorRotulo = bindingRotulo || overallRotulo;
  const competitorDistance = bindingRotulo
    ? properties[`${prefix}_nearest_binding_distance_m`]
    : properties[`${prefix}_nearest_overall_distance_m`];
  const competitorLine = competitorRotulo
    ? `<p>Nearest: ${escapeHtml(competitorRotulo)} (${Number(competitorDistance).toFixed(1)}m)</p>`
    : "";

  return `
    <strong>${escapeHtml(properties.address ?? "Unknown address")}</strong>
    <p>${escapeHtml(properties.zpae_zone)} — ${escapeHtml(properties.classification)} street</p>
    <p>${verdictText}</p>
    ${competitorLine}
  `;
}

let errorBannerVisible = false;

function showError(message) {
  const banner = document.getElementById("error-banner");
  banner.textContent = message;
  banner.hidden = false;
  errorBannerVisible = true;
}

function hideError() {
  if (!errorBannerVisible) return;
  const banner = document.getElementById("error-banner");
  banner.hidden = true;
  errorBannerVisible = false;
}

map.on("load", () => {
  map.addSource("candidates", {
    type: "vector",
    url: "pmtiles://data/zpae.pmtiles",
  });

  map.addLayer({
    id: "candidate-points",
    type: "circle",
    source: "candidates",
    "source-layer": "candidates",
    paint: {
      "circle-radius": 5,
      "circle-color": verdictColorExpression(currentVerdictPrefix),
      "circle-stroke-width": 1,
      "circle-stroke-color": "#ffffff",
    },
  });

  map.on("click", "candidate-points", (e) => {
    const properties = e.features[0].properties;
    new maplibregl.Popup()
      .setLngLat(e.lngLat)
      .setHTML(buildPopupHTML(properties))
      .addTo(map);
  });

  map.on("mouseenter", "candidate-points", () => {
    map.getCanvas().style.cursor = "pointer";
  });
  map.on("mouseleave", "candidate-points", () => {
    map.getCanvas().style.cursor = "";
  });

  map.addLayer({
    id: "candidate-disagreement-highlight",
    type: "circle",
    source: "candidates",
    "source-layer": "candidates",
    filter: ["==", ["get", "interpretations_disagree"], true],
    layout: { visibility: "none" },
    paint: {
      "circle-radius": 9,
      "circle-color": "transparent",
      "circle-stroke-width": 3,
      "circle-stroke-color": "#7c3aed",
    },
  });

  map.addSource("zpae-zones", { type: "geojson", data: "data/zpae_zones.geojson" });
  map.addSource("zpae-streets", { type: "geojson", data: "data/zpae_streets.geojson" });

  map.addLayer({
    id: "zpae-zone-outline",
    type: "line",
    source: "zpae-zones",
    layout: { visibility: "none" },
    paint: { "line-color": "#374151", "line-width": 2, "line-dasharray": [2, 2] },
  });

  map.addLayer({
    id: "zpae-street-classification",
    type: "line",
    source: "zpae-streets",
    layout: { visibility: "none" },
    paint: {
      "line-width": 3,
      "line-color": [
        "match",
        ["get", "Clasifica"],
        "Alta", "#dc2626",
        "Moderada", "#f97316",
        "Baja", "#eab308",
        "#9ca3af",
      ],
    },
  });

  map.on("click", "zpae-street-classification", (e) => {
    const p = e.features[0].properties;
    new maplibregl.Popup()
      .setLngLat(e.lngLat)
      .setHTML(`<strong>${escapeHtml(p.ZPAE)}</strong><p>Classification: ${escapeHtml(p.Clasifica)}</p>`)
      .addTo(map);
  });

  map.on("idle", () => hideError());
});

const MANAGED_SOURCE_IDS = new Set(["candidates", "zpae-zones", "zpae-streets"]);

map.on("error", (e) => {
  if (!e.sourceId || !MANAGED_SOURCE_IDS.has(e.sourceId)) return;
  showError(`Failed to load map layer (${e.sourceId}): ${e.error?.message ?? "unknown error"}`);
});

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

document.getElementById("regulatory-toggle").addEventListener("change", (e) => {
  const visibility = e.target.checked ? "visible" : "none";
  for (const layerId of ["zpae-zone-outline", "zpae-street-classification"]) {
    if (map.getLayer(layerId)) {
      map.setLayoutProperty(layerId, "visibility", visibility);
    }
  }
});

document.getElementById("disagreement-toggle").addEventListener("change", (e) => {
  if (map.getLayer("candidate-disagreement-highlight")) {
    map.setLayoutProperty(
      "candidate-disagreement-highlight",
      "visibility",
      e.target.checked ? "visible" : "none"
    );
  }
});

let searchIndex = [];

fetch("data/search_index.json")
  .then((r) => {
    if (!r.ok) throw new Error(`search_index.json: HTTP ${r.status}`);
    return r.json();
  })
  .then((data) => {
    searchIndex = data;
  })
  .catch((err) => showError(`Failed to load search index: ${err.message}`));

const searchInput = document.getElementById("search-input");
const searchResults = document.getElementById("search-results");

searchInput.addEventListener("input", () => {
  const query = searchInput.value.trim().toLowerCase();
  searchResults.innerHTML = "";
  if (query.length < 3) return;

  const matches = searchIndex
    .filter((entry) => entry.address && entry.address.toLowerCase().includes(query))
    .slice(0, 10);

  for (const match of matches) {
    const li = document.createElement("li");
    li.textContent = match.address;
    li.addEventListener("click", () => selectSearchResult(match));
    searchResults.appendChild(li);
  }
});

function selectSearchResult(match) {
  searchResults.innerHTML = "";
  searchInput.value = match.address;
  map.flyTo({ center: [match.lon, match.lat], zoom: 18 });

  map.once("idle", () => {
    const point = map.project([match.lon, match.lat]);
    const features = map.queryRenderedFeatures(
      [
        [point.x - 6, point.y - 6],
        [point.x + 6, point.y + 6],
      ],
      { layers: ["candidate-points"] }
    );
    const feature = features.find((f) => f.properties.id_porpk === match.id_porpk);
    if (feature) {
      new maplibregl.Popup()
        .setLngLat([match.lon, match.lat])
        .setHTML(buildPopupHTML(feature.properties))
        .addTo(map);
    }
  });
}
