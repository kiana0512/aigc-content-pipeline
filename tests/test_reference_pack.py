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


def test_reference_pack_scans_roles_source_type_and_priority(tmp_path):
    init = tmp_path / "selected" / "init" / "hero.png"
    style = tmp_path / "style" / "style.png"
    screen = tmp_path / "raw" / "screenshots" / "screen.png"
    for path in [init, style, screen]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fake")

    pack = scan_reference_pack(tmp_path)
    init_asset = next(asset for asset in pack.assets if asset.path == init)
    screen_asset = next(asset for asset in pack.assets if asset.path == screen)

    assert pack.by_role("init") == [init]
    assert pack.by_role("style") == [style]
    assert init_asset.source_type == "selected"
    assert screen_asset.source_type == "screenshot"
    assert screen_asset.priority > init_asset.priority
    assert init_asset.workspace_id
    assert screen_asset.workspace_id


def test_prepare_assets_duplicate_bytes_canonical_prefers_selected_init(tmp_path):
    from aigc2d.reference_pack import image_file_digest, prepare_assets_for_duplicate_byte_dedup

    blob = b"same-content"
    init = tmp_path / "selected" / "init" / "poster.jpg"
    identity = tmp_path / "selected" / "identity" / "poster.jpg"
    official = tmp_path / "raw" / "official" / "poster.jpg"
    fan = tmp_path / "raw" / "fanart" / "1.png"
    for p in [init, identity, official]:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(blob)
    fan.parent.mkdir(parents=True, exist_ok=True)
    fan.write_bytes(b"f")

    pack = scan_reference_pack(tmp_path)
    assert image_file_digest(init) == image_file_digest(identity) == image_file_digest(official)
    ordered = prepare_assets_for_duplicate_byte_dedup(pack.assets)

    trio = [a for a in ordered if a.rel_path.endswith("poster.jpg")]
    assert len(trio) == 3
    assert trio[0].rel_path.startswith("selected/init")
    fan_only = next(a for a in ordered if a.path == fan)
    assert ordered.index(fan_only) < ordered.index(trio[0])


def test_fanart_prioritized_over_selected_init_when_distinct(tmp_path):
    init = tmp_path / "selected" / "init" / "hero.png"
    fan = tmp_path / "raw" / "fanart" / "a.png"
    init.parent.mkdir(parents=True, exist_ok=True)
    fan.parent.mkdir(parents=True, exist_ok=True)
    init.write_bytes(b"init-bytes")
    fan.write_bytes(b"fan-bytes")

    pack = scan_reference_pack(tmp_path)
    ia = next(a for a in pack.assets if a.path == init)
    fa = next(a for a in pack.assets if a.path == fan)
    assert fa.priority > ia.priority


def test_scan_finds_raw_fanart_and_recursive(tmp_path):
    root_f = tmp_path / "raw" / "fanart"
    deep = tmp_path / "raw" / "fanart" / "extras" / "deep.png"
    for p in [root_f / "1.png", deep]:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"f")

    pack = scan_reference_pack(tmp_path)
    rels = sorted({asset.rel_path for asset in pack.assets})
    assert "raw/fanart/1.png" in rels
    assert "raw/fanart/extras/deep.png" in rels
    ws = {asset.path: asset.workspace_id for asset in pack.assets}
    assert ws[root_f / "1.png"] != ws[deep]


def test_make_workspace_slug_collision_free(tmp_path):
    from aigc2d.reference_pack import make_workspace_slug

    a = make_workspace_slug("raw/fanart/1.png")
    b = make_workspace_slug("raw/screenshots/1.png")
    assert a != b
