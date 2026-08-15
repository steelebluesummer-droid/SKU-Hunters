from app.planning.live_data import build_live_data_board
from app.planning.live_insights import build_live_insight_bundle
from app.schemas.base_data import BaseRecord


def _record(record_id: str, *, category: str, platform: str, heat: float, price: str | None = "39-99") -> BaseRecord:
    return BaseRecord(
        record_id=record_id,
        keyword=f"关键词-{record_id}",
        platform=platform,
        category=category,
        summary=f"真实摘要-{record_id}",
        heat_index=heat,
        interaction=100,
        brand="品牌A",
        price_range=price,
        record_date="2026-08-01",
        source_url=f"https://example.com/{record_id}",
        snapshot_id="snap-1",
        ingested_at="2026-08-02T00:00:00+00:00",
    )


class _Adapter:
    def __init__(self, records):
        self.records = records

    def search_all(self, keyword="", category=None):
        assert keyword == ""
        if category is None:
            return self.records
        return [record for record in self.records if record.category == category]

    def build_evidence_refs(self, records):
        return [{"url": record.source_url} for record in records if record.source_url]


def test_live_data_board_aggregates_records_without_fixture_values():
    data = build_live_data_board(
        _Adapter([
            _record("1", category="便携小风扇", platform="xiaohongshu", heat=91),
            _record("2", category="手持小风扇", platform="tiktok", heat=73, price="120-149"),
        ])
    )

    assert data["dataSource"] == "feishu"
    assert data["recordCount"] == 2
    assert {row["name"] for row in data["categoryRank"]} == {"便携小风扇", "手持小风扇"}
    assert data["hotProducts"][0]["heat"] == 91  # 热度指标，非销量
    assert data["voiceTrend"]["xhs"] == [1]
    assert data["voiceTrend"]["douyin"] == [1]
    assert sum(row["recordCount"] for row in data["priceBands"]) == 2


def test_live_insights_use_matching_category_records_and_leave_unavailable_fields_empty():
    data = build_live_insight_bundle(
        "小风扇",
        adapter=_Adapter([
            _record("1", category="便携小风扇", platform="xiaohongshu", heat=91),
            _record("ip", category="IP", platform="weibo", heat=88, price=None),
        ]),
    )

    assert data["dataSource"] == "feishu"
    assert data["recordCount"] == 1
    assert data["trendRadar"]["signals"]
    assert data["insightBase"]["ipPool"]
    assert data["consumerVoice"]["painPoints"] == []
    assert data["trendGallery"]["colors"] == []
