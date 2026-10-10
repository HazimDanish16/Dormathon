"""Offline tests for the data-prep pipeline. All fixtures are synthetic and built inline."""
import io

import httpx
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from newsprice.dataprep import checks as ck
from newsprice.dataprep import mapping as mp
from newsprice.dataprep import news_cleaning as nc
from newsprice.dataprep import price_cleaning as pc
from newsprice.dataprep import price_index as pi
from newsprice.dataprep import reports
from newsprice.dataprep.download import SchemaError, acquire_prices, filter_month, http_download
from newsprice.dataprep.paths import DataPaths


def lookup():
    return pd.DataFrame(
        [
            (1, "BERAS IMPORT SST 5% (WANGI) 10KG", "10 KG", "BARANGAN SEGAR", "BERAS"),
            (2, "BERAS PULUT 1KG", "1 KG", "BARANGAN SEGAR", "BERAS"),
            (3, "BERAS TEMPATAN 5KG", "5 KG", "BARANGAN SEGAR", "BERAS"),
            (4, "TELUR AYAM GRED A", "10 biji", "BARANGAN SEGAR", "TELUR"),
            (5, "TELUR PUYUH", "10 biji", "BARANGAN SEGAR", "TELUR"),
            (6, "AYAM BERSIH - STANDARD", "1 KG", "BARANGAN SEGAR", "AYAM"),
            (7, "AYAM HIDUP", "1 KG", "BARANGAN SEGAR", "AYAM"),
            (8, "MINYAK MASAK SEBATIAN BOTOL", "1 KG", "BARANGAN KERING", "MINYAK DAN LEMAK"),
            (9, "MINYAK MASAK PAKET 1KG", "1 KG", "BARANGAN KERING", "MINYAK DAN LEMAK"),
            (10, "LAPTOP", "1 unit", "ELEKTRONIK", "KOMPUTER"),
        ],
        columns=["item_code", "item", "unit", "item_group", "item_category"],
    )


# ---------------- mapping ----------------
def test_mapping_proposes_and_requires_approval():
    review = mp.build_mapping(lookup())
    assert 10 not in set(review["item_code"])
    assert review.set_index("item_code").loc[2, "include"] == "no"
    assert (review["include"] == "review").any()
    with pytest.raises(mp.MappingNotApproved):
        mp.approve_mapping(review)
    approved = mp.approve_mapping(review, accept_suggestions=True)
    assert set(approved["include"]) <= {"yes", "no"}
    assert "suggestion_accepted" in set(approved["approval"])
    assert not ck.check_mapping(approved, lookup()) or all(c.passed for c in ck.check_mapping(approved, lookup()))


# ---------------- price cleaning ----------------
def make_obs(days=60, item=4, base=10.0, premises=(1, 2, 3)):
    rows = []
    for d in pd.date_range("2024-01-01", periods=days):
        for p in premises:
            rows.append((d, p, item, base + 0.01 * p))
    return pd.DataFrame(rows, columns=["date", "premise_code", "item_code", "price"])


def test_rejects_invalid_and_conflicting_rows():
    obs = make_obs(20)
    bad = pd.DataFrame(
        {
            "date": [pd.Timestamp("2024-01-05")] * 4 + [None],
            "premise_code": [1, 2, 3, 99, 5],
            "item_code": [4] * 5,
            "price": [np.nan, 0.0, -1.0, np.inf, 5.0],
        }
    )
    res = pc.clean_observations(pd.concat([obs, bad], ignore_index=True))
    reasons = res.stats["rejected_by_reason"]
    assert reasons["null_price"] == 1 and reasons["non_positive_price"] == 2 and reasons["non_finite_price"] == 1
    assert reasons["invalid_date"] == 1
    conflict = pd.concat([obs, obs.iloc[[0]].assign(price=99.0)], ignore_index=True)
    res = pc.clean_observations(conflict)
    assert res.stats["key_conflict_rows_rejected"] == 2
    dup = pd.concat([obs, obs.iloc[[0]]], ignore_index=True)
    assert pc.clean_observations(dup).stats["exact_duplicates_dropped"] == 1


def test_outlier_flag_is_causal():
    obs = make_obs(60)
    spike = obs.copy()
    spike.loc[(spike["date"] == "2024-02-15") & (spike["premise_code"] == 1), "price"] = 500.0
    a = pc.clean_observations(spike).observations
    row = a[(a["date"] == "2024-02-15") & (a["premise_code"] == 1)].iloc[0]
    assert row["outlier_flag"]
    # Changing FUTURE prices must not alter earlier flags or baselines.
    future = spike.copy()
    future.loc[future["date"] > "2024-02-15", "price"] *= 50
    b = pc.clean_observations(future).observations
    cut = pd.Timestamp("2024-02-15")
    cols = ["date", "premise_code", "item_code", "baseline_median", "outlier_flag"]
    pd.testing.assert_frame_equal(
        a[a["date"] <= cut][cols].reset_index(drop=True), b[b["date"] <= cut][cols].reset_index(drop=True)
    )


def test_no_baseline_means_not_flagged():
    res = pc.clean_observations(make_obs(3)).observations
    assert not res["baseline_ok"].any() and not res["outlier_flag"].any()


def test_daily_stats_exclude_outliers_and_checks_pass():
    obs = make_obs(60)
    obs.loc[(obs["date"] == "2024-02-15") & (obs["premise_code"] == 1), "price"] = 500.0
    res = pc.clean_observations(obs)
    daily = pc.daily_item_stats(res.observations)
    d = daily[daily["date"] == "2024-02-15"].iloc[0]
    assert d["n_outliers_flagged"] == 1 and d["n_obs"] == 2 and d["median_price"] < 11
    assert all(c.passed for c in ck.check_observations(res.observations))
    assert all(c.passed for c in ck.check_daily(daily))


# ---------------- price index ----------------
def make_daily(days=120):
    rows = []
    for item, base in ((1, 10.0), (2, 20.0)):
        for i, d in enumerate(pd.date_range("2024-01-01", periods=days)):
            rows.append((d, item, base * (1 + 0.001 * i), base, base, 3, 3, 0))
    return pd.DataFrame(rows, columns=pc.DAILY_COLUMNS)


def test_index_reference_trailing_smoothing_and_flags():
    daily = make_daily()
    items = pd.DataFrame({"item_code": [1, 2], "product": ["rice", "rice"]})
    cfg = pi.IndexConfig.from_strings("2024-01-01", "2024-02-15", min_ref_days=30, per_item_days=None)
    ppd = pd.DataFrame({"product": "rice", "date": daily["date"].unique(), "n_premises": 3})
    index, baselines = pi.build_price_index(daily, items, ppd, cfg)
    assert baselines["eligible"].all()
    assert index.loc[index["date"] <= cfg.ref_end, "data_quality_flag"].str.contains("reference_period").all()
    assert not index.loc[index["date"] > cfg.ref_end, "data_quality_flag"].str.contains("reference_period").any()
    g = index.set_index("date")["price_index_raw"]
    expect = g.rolling("7D", min_periods=3).mean()
    np.testing.assert_allclose(index.set_index("date")["price_index_smoothed"].dropna(), expect.dropna())
    # Changing future prices must not change past index values (no look-ahead).
    d2 = daily.copy()
    d2.loc[d2["date"] > "2024-03-01", "median_price"] *= 3
    idx2, _ = pi.build_price_index(d2, items, ppd, cfg)
    past = index["date"] <= "2024-03-01"
    cols = ["price_index_raw", "price_index_smoothed", "price_index_chained"]
    np.testing.assert_allclose(index.loc[past, cols].to_numpy(dtype=float), idx2.loc[past, cols].to_numpy(dtype=float), equal_nan=True)


def test_index_excludes_item_without_baseline_and_late_entry_does_not_jump():
    daily = make_daily()
    late = daily[(daily["item_code"] == 2) & (daily["date"] >= "2024-03-01")]
    daily = pd.concat([daily[daily["item_code"] == 1], late], ignore_index=True)
    items = pd.DataFrame({"item_code": [1, 2], "product": ["egg", "egg"]})
    cfg = pi.IndexConfig.from_strings("2024-01-01", "2024-02-15", min_ref_days=30, per_item_days=None)
    ppd = pd.DataFrame({"product": "egg", "date": daily["date"].unique(), "n_premises": 3})
    index, baselines = pi.build_price_index(daily, items, ppd, cfg)
    assert baselines.set_index("item_code").loc[2, "eligible"] == False  # noqa: E712
    assert (index["n_items"] <= 1).all()
    ch = index["price_index_chained"].dropna()
    assert ch.pct_change().abs().max() < 0.02  # no jump when item 2 enters
    assert all(c.passed for c in ck.check_index(index.assign(product="egg"), ref_end=cfg.ref_end) if "all four" not in c.name)


# ---------------- news ----------------
def news_csv(tmp_path, dates, tz_shift=False, long_text=True):
    text = "word " * 40 if long_text else "short"
    rows = []
    for i, d in enumerate(dates):
        rows.append(
            {
                "content_id": f"id{i}",
                "title": f"Title {i}",
                "text": f"<p>{text}</p>",
                "section": "s",
                "category": "c",
                "content_tier": "free",
                "content_length": 100,
                "authors": "a",
                "published_date": f"{d} 00:00:00",
                "keywords": "k",
                "summary": "s",
                "url": f"https://www.thestar.com.my/news/{d.replace('-', '/')}/story-{i}",
                "top_image": "",
            }
        )
    p = tmp_path / "news.csv"
    pd.DataFrame(rows).to_csv(p, index=False)
    return p


def test_news_cleaning_end_to_end(tmp_path):
    p = news_csv(tmp_path, ["2024-01-02", "2024-01-03", "2024-01-03"])
    df = pd.read_csv(p)
    df.loc[2, "url"] = df.loc[1, "url"] + "/?utm_source=x"  # duplicate URL
    df.loc[0, "title"] = "Title 0 <b>bold</b>"
    df.to_csv(p, index=False)
    stats = nc.clean_news_csv(p, tmp_path / "out.parquet", tmp_path / "rej.csv", today=pd.Timestamp("2024-06-01").date())
    assert stats["rows_kept"] == 2 and stats["rejected_by_reason"] == {"duplicate_url": 1}
    assert stats["time_convention"]["name"] == "date_only"
    out = pd.read_parquet(tmp_path / "out.parquet")
    assert str(out["published_at"].dt.tz) == "Asia/Kuala_Lumpur"
    assert not out["text_clean"].str.contains("<").any()
    cols = list(pq.ParquetFile(tmp_path / "out.parquet").schema_arrow.names)
    assert all(c.passed for c in ck.check_news(out, all_columns=cols))


def test_news_rejects_short_text_and_refuses_unverifiable_dates(tmp_path):
    p = news_csv(tmp_path, ["2024-01-02"], long_text=False)
    stats = nc.clean_news_csv(p, tmp_path / "o.parquet", tmp_path / "r.csv", today=pd.Timestamp("2024-06-01").date())
    assert stats["rows_kept"] == 0 and stats["rejected_by_reason"] == {"insufficient_text": 1}
    p2 = news_csv(tmp_path, ["2024-01-02"])
    df = pd.read_csv(p2)
    df["url"] = "https://www.thestar.com.my/news/2020/05/05/x"  # URL date disagrees
    df.to_csv(p2, index=False)
    with pytest.raises(nc.NewsTimezoneError):
        nc.clean_news_csv(p2, tmp_path / "o2.parquet", tmp_path / "r2.csv")
    df.drop(columns=["title"]).to_csv(p2, index=False)
    with pytest.raises(nc.NewsSchemaError):
        nc.clean_news_csv(p2, tmp_path / "o3.parquet", tmp_path / "r3.csv")


# ---------------- download ----------------
def month_parquet(rows) -> bytes:
    buf = io.BytesIO()
    pq.write_table(pa.table({"date": [r[0] for r in rows], "premise_code": [r[1] for r in rows], "item_code": [r[2] for r in rows], "price": [r[3] for r in rows]}), buf)
    return buf.getvalue()


def test_download_filters_resumes_and_handles_404(tmp_path):
    good = month_parquet([("2024-01-01", 1, 4, 10.0), ("2024-01-01", 1, 999, 5.0), ("2024-01-02", 2, 4, 11.0)])
    calls = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("2024-02.parquet"):
            return httpx.Response(404)
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503)
        rng = req.headers.get("range")
        if rng:
            start = int(rng.split("=")[1].split("-")[0])
            return httpx.Response(206, content=good[start:])
        return httpx.Response(200, content=good)

    paths = DataPaths(tmp_path)
    client = httpx.Client(transport=httpx.MockTransport(handler))
    s = acquire_prices(paths, ["2024-01", "2024-02"], [4], client=client, sleep=lambda _: None)
    assert s.downloaded == ["2024-01"] and s.unavailable == ["2024-02"] and s.rows_kept == 2
    kept = pd.read_parquet(paths.raw_price_items / "pricecatcher_items_2024-01.parquet")
    assert set(kept["item_code"]) == {4}
    assert not (paths.raw_prices_full / "pricecatcher_2024-01.parquet").exists()
    assert paths.download_log.read_text().count("\n") == 2
    # re-run skips existing months
    s2 = acquire_prices(paths, ["2024-01"], [4], client=client, sleep=lambda _: None)
    assert s2.skipped_existing == ["2024-01"]
    # resume from a partial file
    part = tmp_path / "x.parquet.part"
    part.write_bytes(good[:20])
    res = http_download("https://x/x.parquet", tmp_path / "x.parquet", client=client, sleep=lambda _: None)
    assert res["status"] == "ok" and (tmp_path / "x.parquet").read_bytes() == good


def test_schema_error_lists_actual_columns(tmp_path):
    f = tmp_path / "m.parquet"
    pq.write_table(pa.table({"tarikh": [1], "harga": [2.0]}), f)
    with pytest.raises(SchemaError, match="tarikh"):
        filter_month(f, [1])


# ---------------- reports ----------------
def test_overlap_report():
    idx = pd.DataFrame({"date": pd.date_range("2024-01-01", "2024-06-30")})
    ov = reports.compute_overlap("2023-05-01", "2024-12-31", idx, "2024-01-15")
    assert ov["overlap"] == ["2024-01-15", "2024-06-30"]
    assert ov["usable_news_end_for_outcome_horizon_days"]["14"] == "2024-06-16"
    assert not reports.compute_overlap(None, None, None, None)["available"]


def test_per_item_baseline_is_point_in_time_and_admits_late_items():
    daily = make_daily(300)
    late = daily[(daily["item_code"] == 2) & (daily["date"] >= "2024-04-01")]
    daily = pd.concat([daily[daily["item_code"] == 1], late], ignore_index=True)
    items = pd.DataFrame({"item_code": [1, 2], "product": ["rice", "rice"]})
    cfg = pi.IndexConfig.from_strings("2024-01-01", "2024-02-15", min_ref_days=30, per_item_days=60)
    ppd = pd.DataFrame({"product": "rice", "date": daily["date"].unique(), "n_premises": 3})
    index, bl = pi.build_price_index(daily, items, ppd, cfg)
    assert bl["eligible"].all()
    b2 = bl.set_index("item_code").loc[2]
    assert b2["ref_end"] == "2024-05-30"
    idx = index.set_index("date")
    assert idx.loc["2024-05-30", "n_items"] == 1 and idx.loc["2024-05-31", "n_items"] == 2
    assert idx.loc["2024-02-29", "data_quality_flag"].startswith("no_eligible_items") or "reference_period" in idx.loc["2024-02-29", "data_quality_flag"]
    # changing prices after an item's baseline window must not change its baseline
    d2 = daily.copy()
    d2.loc[(d2["item_code"] == 1) & (d2["date"] > "2024-03-01"), "median_price"] *= 2
    _, bl2 = pi.build_price_index(d2, items, ppd, cfg)
    assert bl2.set_index("item_code").loc[1, "baseline_median"] == bl.set_index("item_code").loc[1, "baseline_median"]


def test_outlier_flagged_for_sparsely_surveyed_item():
    rows = []
    for d in pd.date_range("2024-01-01", periods=90, freq="7D"):  # weekly survey
        rows.append((d, 1, 9, 35.0))
    rows.append((pd.Timestamp("2024-01-01") + pd.Timedelta(days=7 * 90 + 1), 1, 9, 3.0))
    res = pc.clean_observations(pd.DataFrame(rows, columns=["date", "premise_code", "item_code", "price"]))
    last = res.observations.iloc[-1]
    assert last["baseline_ok"] and last["outlier_flag"]


def test_chained_index_has_no_upward_drift_on_noise():
    rng = np.random.default_rng(1)
    dates = pd.date_range("2024-01-01", periods=400)
    rows = [(d, i, 10 * np.exp(rng.normal(0, 0.05))) for i in range(5) for d in dates]
    df = pd.DataFrame(rows, columns=["date", "item_code", "median_price"])
    out = pi.chained_index(df, 3)
    assert 80 < out["price_index_chained"].iloc[-1] < 125


def test_low_item_days_excluded_from_smoothing():
    daily = make_daily(120)
    daily = daily[~((daily["item_code"] == 2) & (daily["date"] == "2024-04-10"))]  # only 1 of 2 items that day
    items = pd.DataFrame({"item_code": [1, 2], "product": ["rice", "rice"]})
    cfg = pi.IndexConfig.from_strings("2024-01-01", "2024-02-15", min_ref_days=30, per_item_days=None)
    ppd = pd.DataFrame({"product": "rice", "date": daily["date"].unique(), "n_premises": 3})
    index, _ = pi.build_price_index(daily, items, ppd, cfg)
    row = index[index["date"] == "2024-04-10"].iloc[0]
    assert "low_items" in row["data_quality_flag"] and pd.isna(row["price_index_smoothed"])
    assert all(c.passed for c in ck.check_index(index.assign(product="rice"), ref_end=cfg.ref_end) if "all four" not in c.name)


# ---------------- examples ----------------
from newsprice.dataprep import examples as ex


def test_match_products_rules():
    assert ex.match_products("Egg prices up") == ["egg"]
    assert ex.match_products("Nasi lemak stalls and rice cooker") == []  # excluded phrase
    assert ex.match_products("Harga ayam naik, telur juga") == ["egg", "chicken"] or set(ex.match_products("Harga ayam naik, telur juga")) == {"egg", "chicken"}
    assert ex.match_products("a bricey surprise") == []  # word boundary


def test_build_examples_returns_and_exclusions():
    dates = pd.date_range("2024-02-20", periods=50)
    index = pd.DataFrame({"product": "egg", "date": dates, "index": np.linspace(100, 140, 50), "n_premises": 50})
    index = index[index["date"] != "2024-03-25"]  # hole at an endpoint
    news = pd.DataFrame(
        {
            "article_id": ["a1", "a2", "a3"],
            "title": ["Egg prices rise", "Egg supply", "Egg news"],
            "summary": ["s", "s", "s"],
            "body": ["b" * 10] * 3,
            # 2024-03-16 00:00 +08 stored as UTC previous day 16:00
            "published_at": pd.to_datetime(["2024-03-15 16:00", "2024-03-10 16:00", "2024-03-09 16:00"], utc=True),
        }
    )
    out, st = ex.build_examples(news, index, horizon=14, min_premises=10)
    # a1: d = 2024-03-16, fut = 03-30 ok; a2: d=03-11, fut=03-25 missing -> dropped; a3: d=03-10 ok
    assert set(out["article_id"]) == {"a1", "a3"}
    a1 = out[out["article_id"] == "a1"].iloc[0]
    I = index.set_index("date")["index"]
    assert abs(a1["realized_return"] - (I["2024-03-30"] / I["2024-03-15"] - 1)) < 1e-12
    assert abs(a1["momentum_return"] - (I["2024-03-15"] / I["2024-03-01"] - 1)) < 1e-12
    assert st["dropped_missing_endpoint"] == 1
    low = index.assign(n_premises=3)
    assert len(ex.build_examples(news, low, 14, 10)[0]) == 0
