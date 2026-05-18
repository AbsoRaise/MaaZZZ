from backend.main import DesktopApi


def test_desktop_api_exposes_maa_profile_and_locate_disk():
    api = DesktopApi()

    profile = api.get_maa_scan_profile()
    located = api.locate_disk({"inventory_pos": {"page": 1, "row": 2, "column": 3}})

    assert profile["success"] is True
    assert profile["data"]["inventory_grid"]["rows"] > 0
    assert located["success"] is True
    assert located["data"]["target"]["x"] == 660
