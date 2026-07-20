"""
Assembles Stage 5's static web layer: joins Stage 4's pass/fail +
competitor-identity results with a human-readable address label (from
Stage 2's raw portal-point pull) and today's occupancy context (from
Stage 2/7's tagged candidate addresses), then reprojects everything to
EPSG:4326 for the web. See
docs/superpowers/specs/2026-07-20-stage5-web-layer-design.md.
"""

import json

import geopandas as gpd
from pyproj import Transformer


def build_address_label(tvia: str | None, nombre: str, numero: str) -> str:
    """Build a human-readable address label, e.g.
    ("CALLE", "ARGANZUELA", "2") -> "Calle Arganzuela, 2". numero ==
    "Desconocido" (a real placeholder in the source data for an unknown
    house number) is omitted rather than printed verbatim. A null tvia
    (present for a small number of real rows) falls back to just the
    street name."""
    street = nombre.title()
    if tvia:
        street = f"{tvia.title()} {street}"
    if numero and numero != "Desconocido":
        return f"{street}, {numero}"
    return street
