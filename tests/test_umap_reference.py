from sarcade.reference.umap import parse_umap_reference_sites


def test_parses_two_reference_categories():
    document = {
        "layers": [
            {
                "properties": {"name": "Points hauts"},
                "layers": [{
                    "properties": {"name": "PH"},
                    "features": [{
                        "id": "ph1",
                        "geometry": {"type": "Point", "coordinates": [1.8, 48.7]},
                        "properties": {"nom": "Point A", "altitude_m": "180,5", "type": "Sommet"},
                    }],
                }],
            },
            {
                "properties": {"name": "Infra"},
                "layers": [{
                    "properties": {"name": "Infra 78"},
                    "features": [{
                        "id": "r1",
                        "geometry": {"type": "Point", "coordinates": [2.0, 48.8]},
                        "properties": {
                            "name": "Transpondeur Test",
                            "qrg_entree": "439.350",
                            "qrg_sortie": "145.475",
                            "ctcss_entree": "85.4",
                            "mode": "FM",
                        },
                    }],
                }],
            },
        ]
    }

    sites = parse_umap_reference_sites(document)
    assert len(sites) == 2

    high = next(s for s in sites if s["category"] == "HIGH_POINT")
    assert high["name"] == "Point A"
    assert high["alt_m"] == 180.5

    relay = next(s for s in sites if s["category"] == "RELAY")
    assert relay["subtype"] == "transponder"
    assert relay["rx_mhz"] == 439.35
    assert relay["tx_mhz"] == 145.475


def test_ignores_linestrings_in_reference_layers():
    document = {
        "layers": [{
            "properties": {"name": "Infra"},
            "layers": [{
                "properties": {"name": "Infra 78"},
                "features": [{
                    "id": "line1",
                    "geometry": {"type": "LineString", "coordinates": [[1.0, 48.0], [2.0, 49.0]]},
                    "properties": {"name": "Liaison"},
                }],
            }],
        }]
    }
    assert parse_umap_reference_sites(document) == []
