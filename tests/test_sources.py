from jeju_agent.sources import guide_for, preloaded, scan_folder
from jeju_agent.synth import generate, get_table, load_catalog

CAT = load_catalog()


def test_guide_without_config_gives_exact_name_and_period():
    g = guide_for(get_table(CAT, "1-08"), {"tables": {}}, "202505", "202604")
    assert not g.configured and not g.url
    assert "1-08" in g.steps[0] and "2025년 5월" in g.steps[1]


def test_guide_with_operator_link_fills_placeholders():
    cfg = {"tables": {"1-08": {"url": "https://center.example/data/108?from={from_ym}&to={to_ym}",
                               "query": "SELECT * FROM card WHERE pt_year BETWEEN '{from_year}' AND '{to_year}'"}}}
    g = guide_for(get_table(CAT, "1-08"), cfg, "202505", "202604", ["애월읍"])
    assert g.url.endswith("from=202505&to=202604")
    assert "'2025' AND '2026'" in g.query


def test_scan_folder_identifies_tables_and_period(tmp_path):
    generate("1-08", "202601-202602", seed=1, cat=CAT).to_csv(tmp_path / "a.csv", index=False, encoding="cp949")
    generate("1-14", "202601-202601", seed=1, cat=CAT).to_csv(tmp_path / "b.csv", index=False, encoding="utf-8-sig")
    (tmp_path / "other.csv").write_text("x,y\n1,2\n", encoding="utf-8")
    found = {f.table_id: f for f in scan_folder(tmp_path, CAT, with_period=True)}
    assert set(found) == {"1-08", "1-14"}
    assert found["1-08"].period == "202601~202602"
    pre = preloaded({"preload_dir": str(tmp_path)}, CAT)
    assert set(pre) == {"1-08", "1-14"}
