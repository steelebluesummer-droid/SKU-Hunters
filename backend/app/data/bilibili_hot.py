"""B站连接器 — 真实 UGC 趋势信号

数据源：B站公开 API
- 热门视频榜: 全站真实热门内容
- 搜索接口: 关键词相关视频的播放/互动数据

B站是 Z 世代浓度最高的中文内容平台，
其数据对名创优品核心客群（18-25岁）的趋势判断价值极高。
"""

from __future__ import annotations

from typing import Any

import httpx


class BilibiliConnector:
    """B站趋势数据连接器"""

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
        ),
        "Referer": "https://www.bilibili.com",
    }

    def __init__(self, timeout: float = 10.0):
        self.timeout = timeout

    def get_popular_videos(self, page: int = 1, page_size: int = 20) -> list[dict[str, Any]]:
        """获取全站热门视频（真实榜单数据）"""
        url = "https://api.bilibili.com/x/web-interface/popular"
        params = {"ps": page_size, "pn": page}
        try:
            resp = httpx.get(url, params=params, headers=self.HEADERS, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError):
            return []

        if data.get("code") != 0:
            return []

        return [
            {
                "title": item.get("title", ""),
                "bvid": item.get("bvid", ""),
                "view": item.get("stat", {}).get("view", 0),
                "like": item.get("stat", {}).get("like", 0),
                "danmaku": item.get("stat", {}).get("danmaku", 0),
                "tname": item.get("tname", ""),  # 分区名
                "url": f"https://www.bilibili.com/video/{item.get('bvid', '')}",
            }
            for item in data.get("data", {}).get("list", [])
        ]

    # 与潮玩/IP消费最相关的分区
    RANKING_PARTITIONS = {
        160: "生活",
        155: "时尚",
        1: "动画",
        4: "游戏",
        119: "鬼畜",
    }

    def get_ranking_videos(self, rid: int) -> list[dict[str, Any]]:
        """获取分区排行榜（真实榜单数据，动态更新）"""
        url = "https://api.bilibili.com/x/web-interface/ranking/v2"
        params = {"rid": rid, "type": "all"}
        try:
            resp = httpx.get(url, params=params, headers=self.HEADERS, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError):
            return []

        if data.get("code") != 0:
            return []

        return [
            {
                "title": item.get("title", ""),
                "bvid": item.get("bvid", ""),
                "view": item.get("stat", {}).get("view", 0),
                "like": item.get("stat", {}).get("like", 0),
                "danmaku": item.get("stat", {}).get("danmaku", 0),
                "tname": item.get("tname", ""),
                "url": f"https://www.bilibili.com/video/{item.get('bvid', '')}",
            }
            for item in data.get("data", {}).get("list", [])
        ]

    def search_keyword(self, keyword: str) -> dict[str, Any]:
        """关键词在分区热门内容中的曝光信号

        策略：扫描生活/时尚/动画/游戏/鬼畜五个分区的实时排行榜，
        统计提及关键词的视频数与播放量。
        分区榜比全站热门对 IP 级趋势更敏感。
        """
        all_videos: list[dict[str, Any]] = []
        for rid in self.RANKING_PARTITIONS:
            all_videos.extend(self.get_ranking_videos(rid))

        kw = keyword.lower()
        matched = [
            v for v in all_videos
            if kw in v["title"].lower() or kw in v["tname"].lower()
        ]
        total_views = sum(v["view"] for v in matched)

        return {
            "keyword": keyword,
            "scanned_videos": len(all_videos),
            "total_results": len(matched),
            "total_views": total_views,
            "avg_views": round(total_views / max(len(matched), 1), 0),
            "top_videos": sorted(matched, key=lambda x: x["view"], reverse=True)[:5],
        }
