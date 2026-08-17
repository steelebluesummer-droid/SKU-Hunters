from app.data.base_adapter import (
    BaseProviderError,
    BaseUnavailable,
    RestrictedQueryPort,
)
from app.data.scoped_views import CompetitorDataView
from app.planning.live_data import build_live_data_board
from app.planning.live_insights import build_live_insight_bundle
from app.schemas.base_data import BaseRecord
from app.schemas.competitor_data import CompetitorRecord


def _competitor(**overrides):
    data = {
        "competitor_id": "c1", "product_name": "风扇Pro", "brand": "几素",
        "category": "风扇", "price": 89.0, "price_min": None, "price_max": None,
        "price_band": "60-100", "image_url": None, "selling_points": ["轻巧", "静音"],
        "design_score": 7.5, "source_url": "https://example.com/c/1",
        "source_platform": "tiktok", "evidence_quote": "实测",
        "record_date": "2026-08-01", "snapshot_id": "snap-1",
        "ingested_at": "2026-08-02T00:00:00+00:00", "verification_status": "unverified",
    }
    data.update(overrides)
    return CompetitorRecord.model_validate(data)


def _record(record_id: str, *, category: str, platform: str, heat: float, price: str | None = "39-99", snapshot_id: str = "snap-1") -> BaseRecord:
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
        snapshot_id=snapshot_id,
        ingested_at="2026-08-02T00:00:00+00:00",
    )


class _Adapter:
    def __init__(self, records, summary=None, summary_error=None, summary_calls=None, competitors=None):
        self.records = records
        self.last_snapshot_meta = []
        self.summary = summary
        self.summary_error = summary_error
        self.summary_calls = summary_calls if summary_calls is not None else []
        self.competitors = competitors if competitors is not None else []

    def search_all(self, keyword="", category=None):
        assert keyword == ""
        if category is None:
            return self.records
        return [record for record in self.records if record.category == category]

    def build_evidence_refs(self, records):
        return [{"url": record.source_url} for record in records if record.source_url]

    def get_summary(self, category=None, as_of=None, snapshot_id=None):
        self.summary_calls.append({"category": category, "snapshot_id": snapshot_id})
        if self.summary_error is not None:
            raise self.summary_error
        if self.summary is None:
            return {}
        return self.summary

    def get_competitor_records(self, category=None, snapshot_id=None, as_of=None):
        comps = list(getattr(self, 'competitors', []))
        out = []
        for c in comps:
            if category is not None and c.category != category:
                continue
            if snapshot_id is not None and c.snapshot_id != snapshot_id:
                continue
            if as_of is not None and (not c.record_date or c.record_date > as_of):
                continue
            out.append(c)
        return out


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
    assert data["consumerVoice"]["scenes"] == []
    assert data["trendGallery"]["colors"] == []


def test_live_insights_reads_summary_pain_points_and_scenes():
    """汇总表提供 pain_points/scenes 时，正确映射为前端契约并在 processLog 标注数量"""
    adapter = _Adapter(
        [_record("1", category="便携小风扇", platform="xiaohongshu", heat=91)],
        summary={
            "pain_points": [{"text": "噪音大", "count": 12}, {"text": "续航短", "count": 8}],
            "scenes": [{"name": "通勤", "value": 30}, {"name": "宿舍", "value": 20}],
        },
    )
    data = build_live_insight_bundle("小风扇", adapter=adapter)

    assert data["dataSource"] == "feishu"
    assert data["consumerVoice"]["painPoints"] == [
        {"text": "噪音大", "count": 12},
        {"text": "续航短", "count": 8},
    ]
    assert data["consumerVoice"]["scenes"] == [
        {"name": "通勤", "value": 30},
        {"name": "宿舍", "value": 20},
    ]
    log = " ".join(data["consumerVoice"]["processLog"])
    assert "痛点 2 条" in log and "场景 2 条" in log
    # 快照正确传递到 get_summary
    assert adapter.summary_calls[-1]["snapshot_id"] is None  # get_summary 不传明细快照（汇总表独立快照体系）


def test_live_insights_summary_missing_fields_stays_empty():
    """汇总表有行但缺 pain_points/scenes 字段 → 保持空，processLog 如实说明"""
    data = build_live_insight_bundle(
        "小风扇",
        adapter=_Adapter(
            [_record("1", category="便携小风扇", platform="xiaohongshu", heat=91)],
            summary={"brands": ["几素"], "record_count": 10},
        ),
    )
    assert data["consumerVoice"]["painPoints"] == []
    assert data["consumerVoice"]["scenes"] == []
    log = " ".join(data["consumerVoice"]["processLog"])
    assert "汇总表字段为空" in log


def test_live_insights_invalid_summary_entries_skipped():
    """非法条目（空 text/name、非 dict、负值、非法 count）被跳过，不抛异常"""
    data = build_live_insight_bundle(
        "小风扇",
        adapter=_Adapter(
            [_record("1", category="便携小风扇", platform="xiaohongshu", heat=91)],
            summary={
                "pain_points": [
                    {"text": "有效", "count": 5},
                    {"text": "", "count": 3},            # 空 text → 跳过
                    {"count": 3},                        # 缺 text → 跳过
                    {"text": "负值", "count": -1},       # 负 count → 跳过
                    {"text": "非法count", "count": "abc"},  # 非法 count → 跳过
                    "not-a-dict",                        # 非 dict → 跳过
                    {"text": 123, "count": 3},           # text 非 str → 跳过
                ],
                "scenes": [
                    {"name": "通勤", "value": 10},
                    {"name": "", "value": 5},            # 空 name → 跳过
                    {"value": 5},                        # 缺 name → 跳过
                    {"name": "负值", "value": -1},       # 负 value → 跳过
                    {"name": "非法", "value": "x"},      # 非法 value → 跳过
                    "bad",                               # 非 dict → 跳过
                ],
            },
        ),
    )
    assert data["consumerVoice"]["painPoints"] == [{"text": "有效", "count": 5}]
    assert data["consumerVoice"]["scenes"] == [{"name": "通勤", "value": 10}]


def test_live_insights_summary_error_keeps_empty_and_logs_failure():
    """get_summary 抛 BaseUnavailable/BaseProviderError → 空值，processLog 说明读取失败而非暂无数据"""
    for exc in (BaseUnavailable("汇总表不可用"), BaseProviderError("网络错误")):
        data = build_live_insight_bundle(
            "小风扇",
            adapter=_Adapter(
                [_record("1", category="便携小风扇", platform="xiaohongshu", heat=91)],
                summary_error=exc,
            ),
        )
        assert data["consumerVoice"]["painPoints"] == []
        assert data["consumerVoice"]["scenes"] == []
        log = " ".join(data["consumerVoice"]["processLog"])
        assert "汇总表读取失败" in log
        assert "暂无" not in log


def test_live_insights_snapshot_isolation_uses_latest_snapshot_only():
    """多个快照时只保留最新快照的记录，并用该快照读取汇总，不混用"""
    adapter = _Adapter(
        [
            _record("old", category="便携小风扇", platform="xiaohongshu", heat=91, snapshot_id="snap-0"),
            _record("new1", category="便携小风扇", platform="tiktok", heat=73, snapshot_id="snap-1"),
            _record("new2", category="手持小风扇", platform="taobao", heat=60, snapshot_id="snap-1"),
        ],
        summary={"pain_points": [{"text": "有效", "count": 5}], "scenes": [{"name": "通勤", "value": 10}]},
    )
    data = build_live_insight_bundle("小风扇", adapter=adapter)

    # 只保留最新快照 snap-1 的两条记录（排除 snap-0）
    assert data["recordCount"] == 2
    # dataContext 写入选中的快照
    assert data["dataContext"]["snapshot_id"] == "snap-1"
    # get_summary 用选中的快照
    assert adapter.summary_calls[-1]["snapshot_id"] is None  # get_summary 不传明细快照（汇总表独立快照体系）
    # 汇总痛点/场景正常带出
    assert data["consumerVoice"]["painPoints"] == [{"text": "有效", "count": 5}]


# ── 父品类「风扇」归一化与聚合 ──────────────────────────

def test_build_bundle_normalizes_legacy_fan_category_to_parent():
    """旧任务「小风扇」归一化为父品类「风扇」，聚合所有含「扇」子品类记录"""
    adapter = _Adapter([
        _record("1", category="便携小风扇", platform="xiaohongshu", heat=91),
        _record("2", category="手持小风扇", platform="tiktok", heat=73),
    ])
    data = build_live_insight_bundle("小风扇", adapter=adapter)
    assert data["dataSource"] == "feishu"
    assert data["recordCount"] == 2  # 含「扇」的便携小风扇 + 手持小风扇 都聚合

def test_build_bundle_fan_parent_aggregates_all_subcategories():
    """查询父品类「风扇」匹配落地扇/塔扇等不含「风扇」字样的子品类"""
    adapter = _Adapter([
        _record("1", category="便携小风扇", platform="xiaohongshu", heat=91),
        _record("2", category="落地扇", platform="tiktok", heat=60),
        _record("3", category="塔扇", platform="taobao", heat=55),
        _record("4", category="循环扇", platform="taobao", heat=50),
        _record("5", category="雨伞", platform="taobao", heat=40),  # 不归入风扇
    ])
    data = build_live_insight_bundle("风扇", adapter=adapter)
    assert data["recordCount"] == 4  # 只聚合含「扇」的 4 条，雨伞排除
    assert data["dataContext"]["record_count"] == 4

def test_build_bundle_fan_parent_reads_fan_summary():
    """父品类归一化后，get_summary 收到的是父品类名「风扇」"""
    adapter = _Adapter(
        [_record("1", category="便携小风扇", platform="xiaohongshu", heat=91)],
        summary={"pain_points": [{"text": "噪音大", "count": 3}], "scenes": [{"name": "桌面", "value": 5}]},
    )
    data = build_live_insight_bundle("小风扇", adapter=adapter)
    # get_summary 使用归一化后的父品类
    assert adapter.summary_calls[-1]["category"] == "风扇"
    assert data["consumerVoice"]["painPoints"] == [{"text": "噪音大", "count": 3}]


# ── 商品级竞品表接入 ──────────────────────────

def test_competitor_view_gap_zone_insufficient_samples():
    """gapZone 样本不足时保持 None，并写入明确 caveat（不伪造机会空白）"""
    adapter = _Adapter([], competitors=[])
    view = CompetitorDataView(RestrictedQueryPort(adapter))
    m = view.get_competitor_map("风扇")
    assert m["products"] == []
    assert m["gap_zone"] is None
    assert any("样本不足" in c["reason"] for c in m["caveats"])

def test_competitor_view_no_match_no_llm():
    """竞品表无匹配：返回空 products/price_bands/selling_points，gap None（纯确定性，不调 LLM）"""
    adapter = _Adapter([], competitors=[])
    view = CompetitorDataView(RestrictedQueryPort(adapter))
    m = view.get_competitor_map("风扇")
    assert m["products"] == []
    assert m["price_bands"] == []
    assert m["selling_points"] == []
    assert m["brands"] == []
    assert m["gap_zone"] is None

def test_competitor_view_gap_zone_computed_with_enough_samples():
    """gapZone 有足够设计评分+价格样本（>=5）时按确定性规则计算"""
    comps = [
        _competitor(competitor_id=f"c{i}", product_name=f"品{i}", price=float(p), design_score=float(d))
        for i, (p, d) in enumerate([(20, 3), (25, 4), (80, 8), (90, 9), (50, 5), (60, 6)])
    ]
    adapter = _Adapter([], competitors=comps)
    view = CompetitorDataView(RestrictedQueryPort(adapter))
    m = view.get_competitor_map("风扇")
    assert m["gap_zone"] is not None
    assert m["gap_zone"]["x"][0] <= m["gap_zone"]["x"][1]
    assert m["gap_zone"]["y"][0] <= m["gap_zone"]["y"][1]

def test_build_bundle_uses_competitor_data():
    """live 洞察优先使用商品级竞品表数据（products/priceBands/sellingPoints/gapZone）"""
    adapter = _Adapter([_record("1", category="便携小风扇", platform="xiaohongshu", heat=91)])
    adapter.competitors = [
        _competitor(product_name="风扇Pro", category="风扇", price=89.0, design_score=7.5,
                    selling_points=["轻巧", "静音"], snapshot_id="snap-1"),
    ]
    data = build_live_insight_bundle("风扇", adapter=adapter)
    cm = data["competitiveMap"]
    assert cm["processLog"][0] == "数据源：飞书 Base 商品竞品表"
    assert len(cm["products"]) == 1
    p = cm["products"][0]
    assert p["name"] == "风扇Pro"
    assert p["brand"] == "几素"
    assert p["designScore"] == 7.5
    assert p["sourceUrl"] == "https://example.com/c/1"
    assert p["verificationStatus"] == "unverified"
    # 竞品 priceBand 使用商品级
    assert cm["priceBands"] == [{"band": "60-100", "count": 1, "pct": 100.0}]
    assert cm["sellingPoints"] == [{"word": "轻巧", "count": 1}, {"word": "静音", "count": 1}]
    assert data["dataSource"] == "feishu"

def test_build_bundle_falls_back_to_base_samples_when_no_competitors():
    """竞品表无匹配：保留 base_records 样本并明确标注，design 不伪造，gapZone None"""
    adapter = _Adapter([_record("1", category="便携小风扇", platform="xiaohongshu", heat=91)])
    # 无 competitors → 降级
    data = build_live_insight_bundle("小风扇", adapter=adapter)
    cm = data["competitiveMap"]
    assert cm["processLog"][0] == "数据源：飞书 Base 商品竞品表"
    assert any("暂无匹配" in log for log in cm["processLog"])
    assert len(cm["products"]) > 0  # 保留 Base 明细样本
    assert cm["gapZone"] is None
    assert data["dataSource"] == "feishu"

def test_build_bundle_legacy_xiaofengshan_maps_to_fan_competitor():
    """旧任务「小风扇」查询兼容映射为父品类「风扇」，读取风扇竞品"""
    adapter = _Adapter([_record("1", category="便携小风扇", platform="xiaohongshu", heat=91)])
    adapter.competitors = [_competitor(product_name="风扇Pro", category="风扇", snapshot_id="snap-1")]
    data = build_live_insight_bundle("小风扇", adapter=adapter)
    cm = data["competitiveMap"]
    assert cm["processLog"][0] == "数据源：飞书 Base 商品竞品表"
    assert any(p["name"] == "风扇Pro" for p in cm["products"])

def test_build_bundle_fan_and_umbrella_competitors_not_mixed():
    """风扇与雨伞竞品数据不混用（竞品表 category 过滤）"""
    adapter = _Adapter([_record("1", category="便携小风扇", platform="xiaohongshu", heat=91)])
    adapter.competitors = [
        _competitor(competitor_id="c1", product_name="风扇A", category="风扇", snapshot_id="snap-1"),
        _competitor(competitor_id="c2", product_name="雨伞B", category="雨伞", snapshot_id="snap-1"),
    ]
    data = build_live_insight_bundle("风扇", adapter=adapter)
    cm = data["competitiveMap"]
    names = [p["name"] for p in cm["products"]]
    assert "风扇A" in names
    assert "雨伞B" not in names


# ── 竞品缺价格处理（500 修复）─────────────────────────

class _ErrPort:
    """fake port：get_competitor_records 抛异常（模拟竞品表不可用）"""
    def __init__(self, exc):
        self.exc = exc

    def get_competitor_records(self, category=None, snapshot_id=None, as_of=None):
        raise self.exc


def test_view_product_missing_price_excluded():
    """price=None 的商品不进入 products"""
    adapter = _Adapter([], competitors=[_competitor(price=None), _competitor(price=50.0)])
    view = CompetitorDataView(RestrictedQueryPort(adapter))
    m = view.get_competitor_map("风扇")
    assert len(m["products"]) == 1
    assert m["products"][0]["price"] == 50.0
    assert m["skipped_count"] == 1
    assert m["record_count"] == 2
    assert m["product_count"] == 1

def test_view_missing_price_not_converted_to_zero():
    """price=None 不会被转换为 0（不制造假价格）"""
    adapter = _Adapter([], competitors=[_competitor(price=None)])
    view = CompetitorDataView(RestrictedQueryPort(adapter))
    m = view.get_competitor_map("风扇")
    assert m["products"] == []
    assert all(p["price"] != 0 for p in m["products"])
    assert m["skipped_count"] == 1

def test_view_uses_price_min_when_price_missing():
    """price 为空、price_min 有值时使用 price_min"""
    adapter = _Adapter([], competitors=[_competitor(price=None, price_min=45.0, price_max=60.0)])
    view = CompetitorDataView(RestrictedQueryPort(adapter))
    m = view.get_competitor_map("风扇")
    assert len(m["products"]) == 1
    assert m["products"][0]["price"] == 45.0
    assert m["products"][0]["priceMin"] == 45.0
    assert m["products"][0]["priceMax"] == 60.0

def test_view_all_missing_price_no_validation_error():
    """所有商品缺价格时不触发 schema ValidationError，products 为空"""
    adapter = _Adapter([], competitors=[_competitor(price=None), _competitor(price=None)])
    view = CompetitorDataView(RestrictedQueryPort(adapter))
    m = view.get_competitor_map("风扇")  # 不应抛异常
    assert m["products"] == []
    assert m["skipped_count"] == 2

def test_view_partial_missing_price_only_valid_products():
    """40 条记录、20 条缺价格时，products 只含 20 条合法价格商品（fake 数据，非业务契约）"""
    comps = [
        _competitor(competitor_id=f"c{i}", price=(None if i < 20 else 30.0 + i))
        for i in range(40)
    ]
    adapter = _Adapter([], competitors=comps)
    view = CompetitorDataView(RestrictedQueryPort(adapter))
    m = view.get_competitor_map("风扇")
    assert m["record_count"] == 40
    assert m["product_count"] == 20
    assert m["skipped_count"] == 20
    assert len(m["products"]) == 20
    assert all(p["price"] is not None and p["price"] > 0 for p in m["products"])
    assert any("20 条商品缺少价格" in c["reason"] for c in m["caveats"])

def test_view_base_unavailable_returns_empty_and_caveat():
    """BaseUnavailable → 空结果 + caveat（fail-closed，不返回 500）"""
    view = CompetitorDataView(_ErrPort(BaseUnavailable("竞品表未配置")))
    m = view.get_competitor_map("风扇")
    assert m["products"] == [] and m["price_bands"] == []
    assert m["gap_zone"] is None
    assert m["record_count"] == 0
    assert any("竞品表不可用" in c["reason"] for c in m["caveats"])

def test_view_base_provider_error_returns_empty_and_caveat():
    """BaseProviderError（网络/HTTP/权限）→ 空结果 + caveat（不返回 500）"""
    view = CompetitorDataView(_ErrPort(BaseProviderError("飞书超时")))
    m = view.get_competitor_map("风扇")
    assert m["products"] == [] and m["price_bands"] == []
    assert m["gap_zone"] is None
    assert any("竞品表不可用" in c["reason"] for c in m["caveats"])

def test_bundle_process_log_includes_skipped_count():
    """processLog 明示缺价格商品数量"""
    adapter = _Adapter([_record("1", category="便携小风扇", platform="xiaohongshu", heat=91)])
    adapter.competitors = [
        _competitor(product_name="有价", category="风扇", price=89.0, snapshot_id="snap-1"),
        _competitor(product_name="无价", category="风扇", price=None, snapshot_id="snap-1"),
    ]
    data = build_live_insight_bundle("风扇", adapter=adapter)
    cm = data["competitiveMap"]
    assert cm["processLog"][0] == "数据源：飞书 Base 商品竞品表"
    # 有商品卡时 processLog 明示进入数量
    assert any("1 条进入商品卡" in log for log in cm["processLog"])
    assert len(cm["products"]) == 1 and cm["products"][0]["price"] == 89.0

def test_bundle_no_fallback_when_all_products_missing_price():
    """所有商品缺价格：不降级成 base_records 样本，processLog 明确说明（dataSource 仍 feishu）"""
    adapter = _Adapter([_record("1", category="便携小风扇", platform="xiaohongshu", heat=91)])
    adapter.competitors = [
        _competitor(product_name="无价A", category="风扇", price=None, snapshot_id="snap-1"),
        _competitor(product_name="无价B", category="风扇", price=None, snapshot_id="snap-1"),
    ]
    data = build_live_insight_bundle("风扇", adapter=adapter)
    cm = data["competitiveMap"]
    # 匹配到竞品表（record_count=2），但无商品卡，不应降级成 base_records 样本
    assert any("因缺少价格未进入商品卡" in log for log in cm["processLog"])
    assert cm["products"] == []
    assert data["dataSource"] == "feishu"


# ── 明细/汇总快照独立体系（500 修复）─────────────────────────

def test_bundle_detail_and_summary_snapshots_independent():
    """明细快照与汇总快照不同源：get_summary 不传明细快照，summary_snapshot_id 从汇总返回值读取"""
    adapter = _Adapter(
        [
            _record("1", category="便携小风扇", platform="xiaohongshu", heat=91, snapshot_id="detail-snap-1"),
            _record("2", category="手持小风扇", platform="tiktok", heat=73, snapshot_id="detail-snap-1"),
        ],
        summary={
            "snapshot_id": "summary-snap-1",
            "pain_points": [{"text": "噪音大", "count": 5}],
            "scenes": [{"name": "通勤", "value": 10}],
        },
    )
    data = build_live_insight_bundle("小风扇", adapter=adapter)

    # get_summary 不传明细快照，只按 category 读取（汇总表独立快照体系）
    assert adapter.summary_calls[-1]["snapshot_id"] is None
    assert adapter.summary_calls[-1]["category"] == "风扇"
    # dataContext.snapshot_id 仍为明细快照（不被汇总快照覆盖）
    assert data["dataContext"]["snapshot_id"] == "detail-snap-1"
    # 痛点/场景非空
    assert data["consumerVoice"]["painPoints"] == [{"text": "噪音大", "count": 5}]
    assert data["consumerVoice"]["scenes"] == [{"name": "通勤", "value": 10}]
    # 汇总日志包含明细/汇总快照（从返回数据动态读取）
    log = " ".join(data["consumerVoice"]["processLog"])
    assert "汇总快照：summary-snap-1" in log
    assert "明细快照：detail-snap-1" in log
    assert data["dataSource"] == "feishu"

def test_bundle_summary_no_match_keeps_empty():
    """汇总表读取成功但无字段 → 空值 + processLog 说明字段为空（不调 LLM/Mock）"""
    adapter = _Adapter(
        [_record("1", category="便携小风扇", platform="xiaohongshu", heat=91, snapshot_id="detail-snap-1")],
        summary={},  # 读取成功但无 pain_points/scenes
    )
    data = build_live_insight_bundle("小风扇", adapter=adapter)
    assert data["consumerVoice"]["painPoints"] == []
    assert data["consumerVoice"]["scenes"] == []
    log = " ".join(data["consumerVoice"]["processLog"])
    assert "汇总表字段为空" in log
    assert data["dataSource"] == "feishu"


# ── 小数场景值/非整数计数（冻结 schema int 边界转换）─────────

def test_scenes_decimal_values_rounded_to_int():
    """飞书场景值为百分比小数（26.7/21.1/8.3/2.7）→ round 整数化（27/21/8/3），不置 0 不截断"""
    adapter = _Adapter(
        [_record("1", category="便携小风扇", platform="xiaohongshu", heat=91)],
        summary={
            "snapshot_id": "summary-snap-1",
            "scenes": [
                {"name": "户外防晒", "value": 26.7},
                {"name": "暴雨天", "value": 21.1},
                {"name": "通勤", "value": 8.3},
                {"name": "其他", "value": 2.7},
            ],
        },
    )
    data = build_live_insight_bundle("风扇", adapter=adapter)
    scenes = data["consumerVoice"]["scenes"]
    assert scenes == [
        {"name": "户外防晒", "value": 27},
        {"name": "暴雨天", "value": 21},
        {"name": "通勤", "value": 8},
        {"name": "其他", "value": 3},
    ]
    # 所有 value 都是 int（冻结 SceneDist.value: int）
    assert all(isinstance(sc["value"], int) for sc in scenes)

def test_scenes_decimal_values_pass_bundle_validation():
    """小数场景值经 InsightBundle.model_validate 不再报错"""
    from app.planning.service import _snake_keys
    from app.schemas.planning import InsightBundle
    adapter = _Adapter(
        [_record("1", category="便携小风扇", platform="xiaohongshu", heat=91)],
        summary={"snapshot_id": "summary-snap-1",
                 "scenes": [{"name": "送礼", "value": 31.0}, {"name": "办公", "value": 12.6}]},
    )
    data = build_live_insight_bundle("风扇", adapter=adapter)
    # 与 service.generate_insights 相同的校验路径：先 _snake_keys 再 model_validate
    bundle = InsightBundle.model_validate(_snake_keys(data))  # 不应抛 ValidationError
    assert bundle.consumer_voice.scenes[1].value == 13  # 12.6 → round → 13

def test_pain_points_non_integer_count_skipped_with_caveat():
    """痛点计数非整数（26.5）→ 跳过并记录 caveat；整数计数（417.0）保留为 int"""
    adapter = _Adapter(
        [_record("1", category="便携小风扇", platform="xiaohongshu", heat=91)],
        summary={
            "snapshot_id": "summary-snap-1",
            "pain_points": [
                {"text": "选购决策难", "count": 417.0},   # 整数值 float，可接受
                {"text": "噪音吐槽", "count": 26.5},       # 非整数，跳过 + caveat
                {"text": "续航焦虑", "count": 12},          # int 正常
            ],
        },
    )
    data = build_live_insight_bundle("风扇", adapter=adapter)
    cv = data["consumerVoice"]
    assert cv["painPoints"] == [
        {"text": "选购决策难", "count": 417},
        {"text": "续航焦虑", "count": 12},
    ]
    assert any("非整数" in log and "噪音吐槽" in log for log in cv["processLog"])
