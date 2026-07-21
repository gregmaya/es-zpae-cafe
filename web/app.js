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
    ? `<p>Nearest: ${competitorRotulo} (${Number(competitorDistance).toFixed(1)}m)</p>`
    : "";

  return `
    <strong>${properties.address ?? "Unknown address"}</strong>
    <p>${properties.zpae_zone} — ${properties.classification} street</p>
    <p>${verdictText}</p>
    ${competitorLine}
  `;
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
});
