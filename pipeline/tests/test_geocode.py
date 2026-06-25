from pipeline.geocode import extract_pincode, make_geocoder, attach_coords


def test_extract_pincode():
    assert extract_pincode("Modern College Road, Shivaji Nagar, Pune, 411005") == "411005"
    assert extract_pincode("no pin here") is None
    assert extract_pincode(None) is None


def test_geocode_known_pincode():
    g = make_geocoder()
    res = g("411005")  # Pune
    assert res is not None
    lat, lng = res
    assert 17 < lat < 20 and 72 < lng < 75


def test_attach_coords_from_address():
    g = make_geocoder()
    recs = [{"city": "Pune", "name": "X", "addr": "Kharadi Road, Pune, 411014"}]
    stats = attach_coords(recs, pin_key="pincode", addr_key="addr", geocode=g)
    assert recs[0]["lat"] is not None
    assert stats["hit"] == 1 and stats["total"] == 1
