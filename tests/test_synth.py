from jeju_agent.synth import enum_from_note, generate, get_table, load_catalog

CAT = load_catalog()


def test_enum_from_note_nested_parens():
    note = "7개 권역 (제주시 동부, 제주시 중부(동), 제주시 중부(서), 제주시 서부, 서귀포시 동부, 서귀포시 중부, 서귀포시 서부)"
    assert len(enum_from_note(note)) == 7
    assert enum_from_note("도시, 읍면") == ["도시", "읍면"]
    assert enum_from_note("이용자수 (명)") == []


def test_card_bjd_matches_spec_and_is_reproducible():
    spec_cols = [c["name"] for c in get_table(CAT, "1-08")["columns"]]
    a = generate("1-08", "202601-202601", seed=7, cat=CAT)
    b = generate("1-08", "202601-202601", seed=7, cat=CAT)
    assert list(a.columns) == spec_cols
    assert a.equals(b)
    biz = {r[0]: r[1] for r in get_table(CAT, "1-08")["references"][1]["rows"]}
    assert all(biz[c] == n for c, n in zip(a.biz_cd, a.biz_nm))
    assert (a.use_cnt >= a.user_cnt).all()
    assert set(a.dstrct_se) <= {"제주시 동부", "제주시 중부(동)", "제주시 중부(서)", "제주시 서부",
                                "서귀포시 동부", "서귀포시 중부", "서귀포시 서부"}


def test_pop_emd_matches_spec():
    spec_cols = [c["name"] for c in get_table(CAT, "4-11")["columns"]]
    d = generate("4-11", "20260401-20260401", seed=1, cat=CAT)
    assert list(d.columns) == spec_cols
    assert d.emd_cd.nunique() == 43
