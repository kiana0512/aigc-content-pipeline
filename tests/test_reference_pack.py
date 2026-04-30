from aigc2d.reference_pack import build_manifest_rows, scan_reference_pack


def test_reference_pack_scan_and_manifest(tmp_path):
    image = tmp_path / "selected" / "identity" / "firefly.png"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"fake")

    pack = scan_reference_pack(tmp_path)
    rows = build_manifest_rows(pack)

    assert pack.pack_id == tmp_path.name
    assert pack.by_role("identity") == [image]
    assert rows[0]["identity_refs"] == str(image)
    assert rows[0]["init_image"] == str(image)
