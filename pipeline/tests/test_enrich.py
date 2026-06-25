from pipeline.enrich import (
    parse_physical_infra,
    activation_venues,
    classify_archetype,
    health_ecosystem,
)


def test_parse_physical_infra():
    t = "Nearest metro station is Huda City Centre. IGI Airport can be accessed within 30-40 minutes."
    r = parse_physical_infra(t)
    assert r["metro_connected"] is True
    assert r["airport_min"] == 40


def test_activation_venues():
    loc = {"transport": "Sector 54 Chowk", "shopping": "Sapphire Mall, Omaxe Wedding Mall",
           "social_infra": "", "tourist": "N/A"}
    v = activation_venues(loc)
    types = {x["type"] for x in v}
    assert "metro" in types and "mall" in types
    assert any(x["name"] == "Sapphire Mall" for x in v)


def test_classify_archetype():
    assert classify_archetype({"corporate": 90, "affluence": 40, "youth": 20, "intro": "commercial corridor"}) == "Corporate Belt"
    assert classify_archetype({"corporate": 20, "affluence": 90, "youth": 20, "intro": "residential locality"}) == "Premium Residential"
    assert classify_archetype({"corporate": 20, "affluence": 30, "youth": 90, "intro": ""}) == "Student Hub"
    assert classify_archetype({"corporate": 10, "affluence": 10, "youth": 10, "intro": ""}) == "Emerging"


def test_health_ecosystem():
    assert health_ecosystem({"hospital": "Medanta, Artemis Hospital"}) is True
    assert health_ecosystem({"hospital": "N/A"}) is False
