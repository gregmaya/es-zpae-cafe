const protocol = new pmtiles.Protocol();
maplibregl.addProtocol("pmtiles", protocol.tile);

const map = new maplibregl.Map({
  container: "map",
  style: "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
  center: [-3.7038, 40.4168],
  zoom: 13,
});

map.addControl(new maplibregl.NavigationControl(), "top-right");
