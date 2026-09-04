"""MINISO IP 资源库（扩充）— 飞书 Base 合作情报 + 内置 seed 双档数据

定位：与 ip_resource.py（名创内部 12 个策展 IP）**并列**的扩充数据模块，
承载飞书 Base「base_ip_partnerships」的 33 条名创 IP 合作情报；
不 import 也不修改 ip_resource.py，原「名创内部」内容一行不改。

数据两档：
- feishu 档：BASE_PROVIDER_MODE=feishu 且配置 FEISHU_IP_PARTNERSHIP_TABLE_ID 时，
  从飞书多维表格拉取（app_token=FEISHU_BASE_APP_TOKEN，表 base_ip_partnerships）；
  网络/配置失败降级 seed，不抛错阻塞功能。
- seed 档：内置 33 条快照（2026-09-04），无飞书凭证时功能完整可用；两档结构一致。

展示字段映射规则（两档通用，规则式推演）：
- potential：ipHeat >= 9 → 5；7~8 → 4；6 及以下 → 3
- audienceGroup / styleGroup / styleTags / matrix：按 ipType 给默认值（见 _TYPE_PRESETS）
- matrix 坐标与风格分组为基于 IP 类型与历史商品特征的演示推演，非市场调研数据
  （与 ip_resource.py 同款口径）。

图片：feishu 档返回 ip_image 附件 file_token 数组（前端经飞书 drive media 下载接口取图）；
seed 档无图，前端沿用色块降级，支持 frontend/public/assets/ip-library/{slug}/ 本地图后补生效。
"""

from __future__ import annotations

import os
from typing import Any

import requests

# ── 展示字段映射预设（按 ipType；matrix x 女性向(0)→男性/ACG(1)，y 可爱萌系(0)→潮流个性(1)）──

_TYPE_PRESETS: dict[str, dict[str, Any]] = {
    "国际动漫影视": {
        "audienceGroup": "大众",
        "styleGroup": "大众经典",
        "styleTags": ["经典", "大众", "全龄"],
        "matrix": {"x": 0.50, "y": 0.45},
    },
    "日韩系": {
        "audienceGroup": "女性向",
        "styleGroup": "可爱萌系",
        "styleTags": ["可爱", "少女", "治愈"],
        "matrix": {"x": 0.28, "y": 0.25},
    },
    "潮玩艺人": {
        "audienceGroup": "女性向",
        "styleGroup": "潮流个性",
        "styleTags": ["潮流", "话题", "收藏向"],
        "matrix": {"x": 0.62, "y": 0.68},
    },
    "国潮": {
        "audienceGroup": "大众",
        "styleGroup": "大众经典",
        "styleTags": ["国风", "怀旧", "话题"],
        "matrix": {"x": 0.55, "y": 0.50},
    },
    "自有IP": {
        "audienceGroup": "大众",
        "styleGroup": "可爱萌系",
        "styleTags": ["治愈", "原创", "收藏向"],
        "matrix": {"x": 0.42, "y": 0.32},
    },
}


def _potential(heat: Any) -> int:
    """ipHeat → potential 5 档制：>=9→5；7~8→4；<=6→3"""
    try:
        h = float(heat)
    except (TypeError, ValueError):
        return 3
    if h >= 9:
        return 5
    if h >= 7:
        return 4
    return 3


def _slugify(name: str) -> str:
    """slug 生成：与 seed 附录一致（中文保留、分隔符转 -、空格去除）"""
    out = []
    for ch in name:
        if ch.isalnum() or "\u4e00" <= ch <= "\u9fff":
            out.append(ch)
        elif out and out[-1] != "-":
            out.append("-")
    return "".join(out).strip("-")


def apply_display_fields(record: dict[str, Any]) -> dict[str, Any]:
    """为一条 Base 字段结构的记录补展示层字段（potential/audienceGroup/styleGroup/styleTags/matrix）"""
    preset = _TYPE_PRESETS.get(str(record.get("ipType") or "").strip()) or _TYPE_PRESETS["国际动漫影视"]
    out = dict(record)
    out["potential"] = _potential(record.get("ipHeat"))
    out["audienceGroup"] = preset["audienceGroup"]
    out["styleGroup"] = preset["styleGroup"]
    out["styleTags"] = list(preset["styleTags"])
    out["audience"] = "年轻女性" if preset["audienceGroup"] == "女性向" else "大众全龄"
    out["matrix"] = dict(preset["matrix"])
    return out


# ── seed 数据（飞书 base_ip_partnerships 快照 2026-09-04，33 条）──────────────

IP_LIBRARY_SEED: list[dict[str, Any]] = [
    {"ipId": "ip-001", "slug": "迪士尼", "name": "迪士尼（含皮克斯）", "ipType": "国际动漫影视", "licensor": "华特迪士尼公司", "cooperationStatus": "持续合作", "cooperationSince": "2016年起", "latestSeries": "玩具总动员5系列（2026-6全球首发100+ SKU）", "productLines": "盲盒、搪胶毛绒、毛绒公仔、手办、箱包、服饰、家居日用", "starProducts": "史迪奇搪胶毛绒盲盒¥69、玩具总动员5系列100+款、皮克斯40周年盲盒¥43", "priceMin": 18.9, "priceMax": 599, "channelStrategy": ["全渠道通贩", "主题店"], "ipHeat": 10, "notes": "迪士尼100周年爆款系列；YOYO×玩具总动员5为自有IP首次联动；上海MINISO LAND壹号店IP占比超八成", "sourceUrl": "https://www.miniso.com/brand/news_198.html"},
    {"ipId": "ip-002", "slug": "哈利-波特", "name": "哈利·波特", "ipType": "国际动漫影视", "licensor": "华纳兄弟探索", "cooperationStatus": "持续合作", "cooperationSince": "2024-10", "latestSeries": "25周年系列（2026-8，三城快闪+全渠道）", "productLines": "盲盒（领带/魔药/腕表/键帽/戒指）、学院围巾浴袍、联名伞、毛毯、卡包、鼠标垫", "starProducts": "领带盲盒约¥60、食死徒遇水显影伞¥149、四学院浴袍、发光冰箱贴盲盒约¥40", "priceMin": 13, "priceMax": 599, "channelStrategy": ["全渠道通贩", "快闪店"], "ipHeat": 10, "notes": "连续三年四弹：2024-10第一弹500+款、2025-8返校季、2026-4魁地奇、2026-8 25周年；25周年销冠为拉文克劳伞", "sourceUrl": "https://post.m.smzdm.com/p/anvxpd87/"},
    {"ipId": "ip-003", "slug": "三丽鸥", "name": "三丽鸥（Sanrio）", "ipType": "日韩系", "licensor": "三丽鸥公司", "cooperationStatus": "持续合作", "cooperationSince": "早期核心IP", "latestSeries": "白昼之月、岛屿狐、森动系列等长线更新", "productLines": "全品类：盲盒、毛绒、箱包、家居、文具、餐厨", "starProducts": "库洛米白昼之月盲盒¥45、口袋精灵整端¥351、玉桂狗抱枕¥59.9、盲盒中性笔¥5.98", "priceMin": 5.98, "priceMax": 474, "channelStrategy": ["全渠道通贩", "主题店"], "ipHeat": 9, "notes": "SKU覆盖面最广IP家族；角色含HelloKitty/玉桂狗/库洛米/美乐蒂/帕恰狗/布丁狗；设酷洛米主题店", "sourceUrl": "https://www.taobao.com/list/product/wap/%E5%90%8D%E5%88%9B%E4%BC%98%E5%93%81%E5%BA%93%E6%B4%9B%E7%B1%B3.htm"},
    {"ipId": "ip-004", "slug": "Chiikawa", "name": "Chiikawa（吉伊卡哇）", "ipType": "日韩系", "licensor": "日本原著IP", "cooperationStatus": "持续合作", "cooperationSince": "2024年初", "latestSeries": "樱花季、人鱼、考拉等季度系列", "productLines": "毛绒公仔、盲盒手办、挂件、卡包证件套", "starProducts": "兵器款毛绒公仔、快乐伙伴盲盒手办、×三丽鸥联名化妆包¥55.9", "priceMin": 20, "priceMax": 200, "channelStrategy": ["全渠道通贩"], "ipHeat": 9, "notes": "2024年现象级联名，让中国市场认识到超级IP爆发力", "sourceUrl": "https://miniso.cn/brand/news_166.html"},
    {"ipId": "ip-005", "slug": "LABUBU---Hello-Kitty", "name": "LABUBU × Hello Kitty", "ipType": "潮玩艺人", "licensor": "泡泡玛特×三丽鸥双授权", "cooperationStatus": "一次性联名", "cooperationSince": "2025-2026", "latestSeries": "LABUBU×Hello Kitty联名系列", "productLines": "盲盒、搪胶毛绒公仔、日用小物", "starProducts": "联名盲盒¥159/个（整盒¥954）、搪胶毛绒公仔¥599、隐藏款二手¥919", "priceMin": 159, "priceMax": 599, "channelStrategy": ["全渠道通贩"], "ipHeat": 10, "notes": "隐藏款二手溢价超5倍；分层浮雕工艺；做工评价两极", "sourceUrl": "https://miniso.cn/brand/news_166.html"},
    {"ipId": "ip-006", "slug": "LISA", "name": "LISA（BLACKPINK）", "ipType": "潮玩艺人", "licensor": "LLOUD Co.", "cooperationStatus": "快闪限定", "cooperationSince": "2026-8-25官宣", "latestSeries": "Born to Shine. Ready to Rock全球巡回快闪", "productLines": "毛绒挂件、盲盒手办、数码配饰、服饰箱包、居家用品（70+ SKU）", "starProducts": "YOYO×LISA搪胶毛绒惊喜盒、曼谷限定银色泰拳手套零钱包", "priceMin": 30, "priceMax": 500, "channelStrategy": ["快闪店", "全球巡回"], "ipHeat": 10, "notes": "9-1曼谷→9-11东京→9-12北京/上海/深圳→10-21雅加达→11-6美国→墨西哥；围绕专辑Alter Ego五角色视觉体系", "sourceUrl": "https://www.prnewswire.com/apac/news-releases/from-bangkok-to-the-world-the-lisa-O-miniso-global-pop-up-is-calling-302869969.html"},
    {"ipId": "ip-007", "slug": "Jennie", "name": "Jennie（BLACKPINK）", "ipType": "潮玩艺人", "licensor": "个人厂牌", "cooperationStatus": "一次性联名", "cooperationSince": "2026-3", "latestSeries": "个人专辑《Ruby》联名快闪", "productLines": "快闪限定周边", "starProducts": "上海快闪开业首日业绩突破220万元", "priceMin": 50, "priceMax": 400, "channelStrategy": ["快闪店"], "ipHeat": 9, "notes": "名创艺人IP快闪模式首战，为LISA全球巡回模式验证打样", "sourceUrl": "https://socialbeta.com/campaign/28385"},
    {"ipId": "ip-008", "slug": "李宇春", "name": "李宇春", "ipType": "潮玩艺人", "licensor": "艺人本人", "cooperationStatus": "战略共创", "cooperationSince": "2026-8-22官宣", "latestSeries": "CHOUCHOU自然收集册系列", "productLines": "搪胶毛绒盲盒（含NFC语音挂件）", "starProducts": "自然收集册系列盲盒（日光/月光/逐风/迎春等+隐藏款新生精灵），首发即售罄、多地限号入场", "priceMin": 59, "priceMax": 99, "channelStrategy": ["全渠道通贩"], "ipHeat": 9, "notes": "双首席身份：集团首席潮流顾问+CHOUCHOU首席创意官，长期战略绑定非普通代言", "sourceUrl": "https://cj.sina.com.cn/articles/view/7879776356/1d5abd864068014l6u"},
    {"ipId": "ip-009", "slug": "史努比", "name": "史努比（SNOOPY）", "ipType": "日韩系", "licensor": "Peanuts Worldwide", "cooperationStatus": "持续合作", "cooperationSince": "早期经典IP", "latestSeries": "开学季系列等", "productLines": "毛绒、卡套、身份证保护套、日常周边", "starProducts": "史努比开学季系列、正版身份证保护套", "priceMin": 6, "priceMax": 150, "channelStrategy": ["全渠道通贩", "主题店"], "ipHeat": 7, "notes": "设Snoopy主题店", "sourceUrl": "https://www.taobao.com"},
    {"ipId": "ip-010", "slug": "龙珠Z", "name": "龙珠Z", "ipType": "国际动漫影视", "licensor": "东映动画/集英社", "cooperationStatus": "快闪限定", "cooperationSince": "2026-8-7", "latestSeries": "龙珠Z联名系列（快闪独家首发）", "productLines": "快闪限定周边（暂无线上渠道）", "starProducts": "广州正佳广场、杭州工联CC双城快闪首发", "priceMin": 30, "priceMax": 300, "channelStrategy": ["快闪店"], "ipHeat": 9, "notes": "暑期定档；快闪限定款不铺常规门店，稀缺度拉满", "sourceUrl": "https://m.sohu.com/a/1059429667_121212001/"},
    {"ipId": "ip-011", "slug": "漫威", "name": "漫威", "ipType": "国际动漫影视", "licensor": "华特迪士尼公司（漫威）", "cooperationStatus": "持续合作", "cooperationSince": "早期经典IP", "latestSeries": "常青产品线", "productLines": "毛绒零钱包、卡套等日常周边", "starProducts": "漫威毛绒零钱荷包小钱包¥9.9", "priceMin": 9.9, "priceMax": 100, "channelStrategy": ["全渠道通贩"], "ipHeat": 7, "notes": "常青通贩类IP", "sourceUrl": "https://www.taobao.com"},
    {"ipId": "ip-012", "slug": "星球大战", "name": "星球大战", "ipType": "国际动漫影视", "licensor": "卢卡斯影业", "cooperationStatus": "持续合作", "cooperationSince": "早期经典IP", "latestSeries": "古古（Grogu）系列等", "productLines": "零钱包、男士卡包", "starProducts": "星球大战古古零钱包、男士商务卡包", "priceMin": 20, "priceMax": 200, "channelStrategy": ["全渠道通贩"], "ipHeat": 7, "notes": "常青通贩类IP", "sourceUrl": "https://www.taobao.com"},
    {"ipId": "ip-013", "slug": "芭比", "name": "芭比（Barbie）", "ipType": "国际动漫影视", "licensor": "美泰", "cooperationStatus": "持续合作", "cooperationSince": "2024爆款", "latestSeries": "芭比65周年系列", "productLines": "主题系列全品类", "starProducts": "芭比65周年系列", "priceMin": 20, "priceMax": 300, "channelStrategy": ["全渠道通贩", "主题店"], "ipHeat": 8, "notes": "2024品牌升级元年爆款系列之一；设芭比主题店", "sourceUrl": "https://miniso.cn/brand/news_166.html"},
    {"ipId": "ip-014", "slug": "小马宝莉", "name": "小马宝莉", "ipType": "国际动漫影视", "licensor": "孩之宝", "cooperationStatus": "持续合作", "cooperationSince": "2024爆款", "latestSeries": "小马宝莉系列", "productLines": "毛绒挂件盲盒、解压捏捏、公仔", "starProducts": "多儿毛绒挂件盲盒、毛绒解压方块捏捏、10号抱腿莉莉坐姿公仔", "priceMin": 20, "priceMax": 200, "channelStrategy": ["全渠道通贩"], "ipHeat": 8, "notes": "2024爆款系列", "sourceUrl": "https://miniso.cn/brand/news_166.html"},
    {"ipId": "ip-015", "slug": "Loopy", "name": "Loopy", "ipType": "日韩系", "licensor": "韩国原创IP", "cooperationStatus": "一次性联名", "cooperationSince": "2024", "latestSeries": "Loopy中国首发系列", "productLines": "毛绒、周边", "starProducts": "Loopy中国首发系列", "priceMin": 20, "priceMax": 200, "channelStrategy": ["全渠道通贩"], "ipHeat": 7, "notes": "2024年中国首发", "sourceUrl": "https://miniso.cn/brand/news_166.html"},
    {"ipId": "ip-016", "slug": "旺旺", "name": "旺旺", "ipType": "国潮", "licensor": "旺旺集团", "cooperationStatus": "一次性联名", "cooperationSince": "2025", "latestSeries": "如意系列", "productLines": "毛绒卡套", "starProducts": "旺旺如意系列毛绒卡套", "priceMin": 10, "priceMax": 60, "channelStrategy": ["全渠道通贩"], "ipHeat": 6, "notes": "国潮代表联名", "sourceUrl": "https://www.taobao.com"},
    {"ipId": "ip-017", "slug": "YOYO", "name": "YOYO", "ipType": "自有IP", "licensor": "名创优品自研", "cooperationStatus": "战略共创", "cooperationSince": "2025-6首发", "latestSeries": "花野蓬蓬、歪头系列、×玩具总动员5（30+款）", "productLines": "搪胶毛绒盲盒、挂件、惊喜盒", "starProducts": "花野蓬蓬搪胶毛绒盲盒（招财转转/蓝聆沙锤/幻彩星星特别款）、YOYO×玩具总动员5与你同萌系列", "priceMin": 39, "priceMax": 200, "channelStrategy": ["全渠道通贩"], "ipHeat": 10, "notes": "首个原创艺术家IP；一年进入全球53国；2026年6/7月连续单月销售额破亿；上央视春晚/巴黎时装周/Met Gala", "sourceUrl": "https://miniso.cn/brand/news_166.html"},
    {"ipId": "ip-018", "slug": "CHOUCHOU", "name": "CHOUCHOU", "ipType": "自有IP", "licensor": "名创优品自研", "cooperationStatus": "战略共创", "cooperationSince": "2026", "latestSeries": "自然收集册系列（李宇春共创）", "productLines": "搪胶毛绒盲盒（含NFC语音挂件）", "starProducts": "自然收集册系列：日光/月光/逐风/迎春/沙野/飞雪/秋叶+隐藏款新生精灵", "priceMin": 59, "priceMax": 99, "channelStrategy": ["全渠道通贩"], "ipHeat": 9, "notes": "治愈系精灵形象'做自己隐藏款'；李宇春任首席创意官；首发8城11店当日售罄", "sourceUrl": "https://cj.sina.com.cn/articles/view/7879776356/1d5abd864068014l6u"},
    {"ipId": "ip-019", "slug": "DUNDUN鸡", "name": "DUNDUN鸡", "ipType": "自有IP", "licensor": "名创优品自研", "cooperationStatus": "持续合作", "cooperationSince": "2024", "latestSeries": "DUNDUN鸡系列", "productLines": "潮玩周边、主题店产品线", "starProducts": "DUNDUN鸡主题店系列", "priceMin": 20, "priceMax": 150, "channelStrategy": ["主题店"], "ipHeat": 7, "notes": "设专属主题店", "sourceUrl": "https://miniso.cn/brand/news_166.html"},
    {"ipId": "ip-020", "slug": "迪士尼---F1", "name": "迪士尼 × F1", "ipType": "国际动漫影视", "licensor": "华特迪士尼×Formula 1", "cooperationStatus": "一次性联名", "cooperationSince": "2026-3", "latestSeries": "米奇家族赛车服系列", "productLines": "挂件盲盒、服饰、主题店装置", "starProducts": "米奇F1极速小世界挂件盲盒¥48", "priceMin": 30, "priceMax": 300, "channelStrategy": ["全渠道通贩", "主题店"], "ipHeat": 8, "notes": "体育营销方向试水；上海愚园路CP静安店主题店2026-3-13上线", "sourceUrl": "https://socialbeta.com/campaign/28385"},
    {"ipId": "ip-021", "slug": "宝可梦", "name": "宝可梦", "ipType": "国际动漫影视", "licensor": "The Pokémon Company", "cooperationStatus": "持续合作", "cooperationSince": "2025年起", "latestSeries": "宝可梦主题店系列（北京通州北投爱琴海店开业，首批4家）", "productLines": "毛绒、文具、周边配件、卡牌", "starProducts": "仙子伊布书签套组¥9.9、毛巾绣本¥39.9、徽章挂件套组¥29.9、磁铁拼图¥19.9、搪胶毛绒盲盒¥49", "priceMin": 9.9, "priceMax": 59.9, "channelStrategy": ["全渠道通贩", "主题店"], "ipHeat": 9, "notes": "主题店含主角团等身立牌与主题试衣镜，满39元赠卡包（限购4包）；皮卡丘/胖丁/杰尼龟/可达鸭经典形象全线铺开", "sourceUrl": "https://post.m.smzdm.com/zz/p/a46errlw/"},
    {"ipId": "ip-022", "slug": "蜡笔小新", "name": "蜡笔小新", "ipType": "日韩系", "licensor": "双叶社", "cooperationStatus": "持续合作", "cooperationSince": "长期合作", "latestSeries": "baby系列盲盒（2026）", "productLines": "盲盒、毛绒、生活百货", "starProducts": "baby系列盲盒¥59、动感大作战¥39.6、屁屁系列¥36、手表盲盒¥39.9", "priceMin": 29.9, "priceMax": 59.9, "channelStrategy": ["全渠道通贩"], "ipHeat": 8, "notes": "中端盲盒招牌IP之一，单盒29.9元起、整套两三百元，学生党友好", "sourceUrl": "https://www.miniso.cn/"},
    {"ipId": "ip-023", "slug": "小黄人", "name": "小黄人（神偷奶爸）", "ipType": "国际动漫影视", "licensor": "环球影业", "cooperationStatus": "持续合作", "cooperationSince": "2019年起", "latestSeries": "不蕉虑市集夏季系列（全国门店上线）", "productLines": "创意家居、季节产品、精品包饰、美妆工具、生活百货、彩妆、数码电器、文具玩具", "starProducts": "大眼钢杯、香蕉斜挎包、耳机包、签名款12生肖摆件、涂鸦购物袋", "priceMin": 9.9, "priceMax": 129, "channelStrategy": ["全渠道通贩", "快闪店"], "ipHeat": 8, "notes": "单系列112个SKU覆盖十大品类，海外同步上市；门店打造小黄人主题市集与UGC互动", "sourceUrl": "https://www.miniso.cn/brand/news_71.html"},
    {"ipId": "ip-024", "slug": "海贼王", "name": "海贼王（ONE PIECE）", "ipType": "国际动漫影视", "licensor": "集英社/东映动画", "cooperationStatus": "持续合作", "cooperationSince": "长期合作", "latestSeries": "航海王周边系列", "productLines": "抱枕靠垫、冰箱贴、拼图、家居", "starProducts": "路飞索隆抱枕靠垫、航海王拼图冰箱贴", "priceMin": 19.9, "priceMax": 99, "channelStrategy": ["全渠道通贩"], "ipHeat": 7, "notes": "长青日漫IP，产品以软家居+贴纸配件为主，与拼装类形成互补", "sourceUrl": "https://www.miniso.cn/"},
    {"ipId": "ip-025", "slug": "哆啦A梦", "name": "哆啦A梦", "ipType": "国际动漫影视", "licensor": "藤子·F·不二雄工作室", "cooperationStatus": "持续合作", "cooperationSince": "长期合作", "latestSeries": "哆啦A梦联名系列", "productLines": "毛绒、文具、生活百货", "starProducts": "联名主题毛绒与文具套装", "priceMin": 12.9, "priceMax": 99, "channelStrategy": ["全渠道通贩"], "ipHeat": 8, "notes": "国民级日漫IP，覆盖多年龄段，常与其他三丽鸥/日系IP组成货架组合", "sourceUrl": "https://www.miniso.cn/"},
    {"ipId": "ip-026", "slug": "轻松熊", "name": "轻松熊（Rilakkuma）", "ipType": "日韩系", "licensor": "San-X", "cooperationStatus": "持续合作", "cooperationSince": "2024年起", "latestSeries": "温柔天使联名系列（2026-8，上海愚园路+深圳罗湖东门主题空间）", "productLines": "香氛挂件盲盒、冰箱贴盲盒、TWS耳机、毛绒", "starProducts": "温柔天使香氛挂件盲盒、冰箱贴盲盒、联名TWS耳机", "priceMin": 29.9, "priceMax": 199, "channelStrategy": ["全渠道通贩", "快闪店"], "ipHeat": 8, "notes": "2026-8-21预售，双城主题空间落地；门店满109元核销互动码参与见面会", "sourceUrl": "https://post.m.smzdm.com/p/a4q5ozg8/"},
    {"ipId": "ip-027", "slug": "蛋黄哥", "name": "蛋黄哥（Gudetama）", "ipType": "日韩系", "licensor": "三丽鸥", "cooperationStatus": "持续合作", "cooperationSince": "长期合作", "latestSeries": "联名卡通系列（纸品线）", "productLines": "手帕纸、纸巾、生活百货", "starProducts": "联名卡通系列手帕纸/纸巾（5款换装）", "priceMin": 5, "priceMax": 29.9, "channelStrategy": ["全渠道通贩"], "ipHeat": 6, "notes": "低客单高频引流型IP，纸品线展示名创以日耗品放大IP触达的策略", "sourceUrl": "https://tissue.glawind.com/detail.php?page=detail&tid=702"},
    {"ipId": "ip-028", "slug": "大耳狗", "name": "大耳狗（Cinnamoroll）", "ipType": "日韩系", "licensor": "三丽鸥", "cooperationStatus": "持续合作", "cooperationSince": "长期合作", "latestSeries": "大耳狗联名系列", "productLines": "毛绒、盲盒、文具、包饰", "starProducts": "大耳狗毛绒公仔与盲盒系列", "priceMin": 19.9, "priceMax": 99, "channelStrategy": ["全渠道通贩"], "ipHeat": 8, "notes": "三丽鸥人气票选四年冠军、连续多年三甲，年轻女性客群号召力强", "sourceUrl": "https://www.miniso.cn/"},
    {"ipId": "ip-029", "slug": "喜羊羊与灰太狼", "name": "喜羊羊与灰太狼", "ipType": "国潮", "licensor": "原创动力（奥飞娱乐）", "cooperationStatus": "持续合作", "cooperationSince": "长期合作", "latestSeries": "喜羊羊盲盒系列", "productLines": "盲盒、毛绒、文具", "starProducts": "喜羊羊与灰太狼盲盒", "priceMin": 29.9, "priceMax": 59.9, "channelStrategy": ["全渠道通贩"], "ipHeat": 7, "notes": "国民级国产动画IP，儿童+怀旧双客群，是国潮线的主力之一", "sourceUrl": "https://www.miniso.cn/"},
    {"ipId": "ip-030", "slug": "蛋仔派对-YOYO", "name": "蛋仔派对×YOYO", "ipType": "自有IP", "licensor": "网易游戏×名创优品", "cooperationStatus": "一次性联名", "cooperationSince": "2026年起", "latestSeries": "蛋仔派对×YOYO联动系列（2026-7-24）", "productLines": "盲盒、毛绒、周边配件", "starProducts": "蛋仔派对联名盲盒（3.5×4.5cm规格，海外同步发售）", "priceMin": 19.9, "priceMax": 59.9, "channelStrategy": ["全渠道通贩"], "ipHeat": 8, "notes": "自有IP YOYO与网易顶流手游联动，海外（秘鲁等）同步上新，验证自有IP反哺路径", "sourceUrl": "https://party.163.com/official/20260727/35180_1309150.html"},
    {"ipId": "ip-031", "slug": "多邻国", "name": "多邻国（Duolingo）", "ipType": "国际动漫影视", "licensor": "Duolingo", "cooperationStatus": "快闪限定", "cooperationSince": "2026年起", "latestSeries": "多邻国联名系列（与哈利波特25周年、玩具总动员5同档上新）", "productLines": "盲盒、配件、生活百货", "starProducts": "多邻国猫头鹰Duo主题周边", "priceMin": 19.9, "priceMax": 59.9, "channelStrategy": ["全渠道通贩", "快闪店"], "ipHeat": 7, "notes": "互联网梗文化IP入局案例，与影视大IP同档期组货，主打年轻社媒话题人群", "sourceUrl": "https://www.miniso.cn/"},
    {"ipId": "ip-032", "slug": "蒙奇奇", "name": "蒙奇奇（Monchhichi）", "ipType": "日韩系", "licensor": "Sekiguchi（关口玩具）", "cooperationStatus": "持续合作", "cooperationSince": "长期合作", "latestSeries": "蒙奇奇联名系列", "productLines": "毛绒、盲盒、包饰", "starProducts": "蒙奇奇毛绒公仔与挂件系列", "priceMin": 19.9, "priceMax": 129, "channelStrategy": ["全渠道通贩"], "ipHeat": 6, "notes": "日本经典绒偶IP，补充日系中性客群，多走毛绒高客单货架位", "sourceUrl": "https://www.miniso.cn/"},
    {"ipId": "ip-033", "slug": "wigglewiggle", "name": "wigglewiggle", "ipType": "潮玩艺人", "licensor": "wigglewiggle（韩国）", "cooperationStatus": "持续合作", "cooperationSince": "2025年起", "latestSeries": "wigglewiggle联名系列", "productLines": "毛绒、盲盒、包饰、生活百货", "starProducts": "wigglewiggle主题毛绒与挂件", "priceMin": 19.9, "priceMax": 99, "channelStrategy": ["全渠道通贩"], "ipHeat": 7, "notes": "韩系ins风新锐IP，社媒话题度高，与Loopy共同构成韩流潮玩矩阵", "sourceUrl": "https://www.miniso.cn/"},
]

TYPE_FILTERS = ["国际动漫影视", "日韩系", "潮玩艺人", "国潮", "自有IP"]
STATUS_FILTERS = ["持续合作", "战略共创", "一次性联名", "快闪限定"]

# ── 别名归一（合并去重时把扩充库别名归一到策展库主名，反之亦然）──────────────

ALIAS_NORMALIZE: dict[str, str] = {
    # 跨语言别名（策展库英文名 ↔ 扩充库中文名）
    "sanrio": "三丽鸥",
    "disney": "迪士尼",
    "harry potter": "哈利·波特",
    "barbie": "芭比",
    "one piece": "海贼王",
    "航海王": "海贼王",
    "marvel": "漫威",
    "pokémon": "宝可梦",
    "pokemon": "宝可梦",
    "minions": "小黄人",
    "神偷奶爸": "小黄人",
    "snoopy / peanuts": "史努比",
    "吉伊卡哇": "chiikawa",
    # 别称
    "航海王（one piece）": "海贼王",
}


def _strip_parens(name: str) -> str:
    """剥掉名字末尾的括号后缀：「三丽鸥（Sanrio）」→「三丽鸥」、「小黄人（神偷奶爸）」→「小黄人」"""
    import re

    return re.split(r"[（(]", name, maxsplit=1)[0].strip()


def normalize_ip_name(name: str) -> str:
    """IP 名归一（剥括号 → 小写 → 别名表），用于同名/别名去重"""
    key = (name or "").strip().lower()
    if not key:
        return key
    stripped = _strip_parens(key)
    for candidate in (key, stripped):
        if candidate in ALIAS_NORMALIZE:
            return ALIAS_NORMALIZE[candidate]
    return stripped or key


# ── 飞书拉取（feishu 档）────────────────────────────────────────

_API = "https://open.feishu.cn/open-apis/bitable/v1/apps"
_REQ_TIMEOUT = 10
_library_cache: list[dict[str, Any]] | None = None


def _feishu_headers() -> dict[str, str] | None:
    """飞书鉴权请求头（供图片代理端点复用）；未配置返回 None"""
    from feishu.auth import FeishuAuth
    from feishu.config import FeishuConfig

    config = FeishuConfig.from_env()
    if not config.app_id or not config.app_secret:
        return None
    try:
        token = FeishuAuth(config).get_token()
    except Exception:  # noqa: BLE001 — 鉴权失败按未配置处理（调用方降级）
        return None
    return {"Authorization": f"Bearer {token}"}


def _to_text(raw: Any) -> str:
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw
    if isinstance(raw, dict):
        return str(raw.get("text") or "")
    if isinstance(raw, list):
        return "".join(str(x.get("text") if isinstance(x, dict) else x) for x in raw)
    return str(raw)


def _to_float(raw: Any) -> float | None:
    try:
        return float(str(raw).strip())
    except (TypeError, ValueError):
        return None


def _feishu_records() -> list[dict[str, Any]] | None:
    """从飞书 base_ip_partnerships 拉全表；失败返回 None（降级 seed）"""
    app_token = os.getenv("FEISHU_BASE_APP_TOKEN")
    table_id = os.getenv("FEISHU_IP_PARTNERSHIP_TABLE_ID")
    if not app_token or not table_id:
        return None
    from feishu.auth import FeishuAuth
    from feishu.config import FeishuConfig

    config = FeishuConfig.from_env()
    if not config.app_id or not config.app_secret:
        return None
    try:
        token = FeishuAuth(config).get_token()
        headers = {"Authorization": f"Bearer {token}"}
        records: list[dict[str, Any]] = []
        page_token: str | None = None
        while True:
            url = f"{_API}/{app_token}/tables/{table_id}/records?page_size=100"
            if page_token:
                url += f"&page_token={page_token}"
            resp = requests.get(url, headers=headers, timeout=_REQ_TIMEOUT)
            if resp.status_code >= 400:
                return None
            data = resp.json()
            if data.get("code") != 0:
                return None
            records.extend(data.get("data", {}).get("items") or [])
            page_token = data.get("data", {}).get("page_token")
            if not page_token or not data.get("data", {}).get("has_more"):
                break
        return records
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return None


def _map_feishu_record(item: dict[str, Any]) -> dict[str, Any]:
    """飞书记录 fields(snake_case) → camelCase 结构（与 seed 一致）"""
    f = item.get("fields") or {}

    def txt(k: str) -> str:
        return _to_text(f.get(k))

    heat = _to_float(f.get("ip_heat"))
    channel = f.get("channel_strategy")
    if isinstance(channel, str):
        channel = [c.strip() for c in channel.split("、") if c.strip()]
    if not isinstance(channel, list):
        channel = []
    images = []
    for att in f.get("ip_image") or []:
        if isinstance(att, dict) and att.get("file_token"):
            images.append(att["file_token"])
    name = txt("ip_name") or f"ip-{item.get('record_id', '')}"
    return {
        "ipId": txt("ip_id") or item.get("record_id", ""),
        "slug": _slugify(name),
        "name": name,
        "ipType": txt("ip_type") or "国际动漫影视",
        "licensor": txt("licensor"),
        "cooperationStatus": txt("cooperation_status"),
        "cooperationSince": txt("cooperation_since"),
        "latestSeries": txt("latest_series"),
        "productLines": txt("product_lines"),
        "starProducts": txt("star_products"),
        "priceMin": _to_float(f.get("price_min")),
        "priceMax": _to_float(f.get("price_max")),
        "channelStrategy": channel,
        "ipHeat": int(heat) if heat is not None else 0,
        "notes": txt("notes"),
        "sourceUrl": _link_of(f.get("source_url")),
        "ipImage": images,
    }


def _link_of(raw: Any) -> str:
    if isinstance(raw, dict):
        return str(raw.get("link") or "")
    return str(raw or "")


def get_ip_library() -> list[dict[str, Any]]:
    """IP 资源库（扩充）全量：feishu 档优先，失败降级 seed；统一补展示字段"""
    global _library_cache
    if _library_cache is not None:
        return _library_cache
    records: list[dict[str, Any]] | None = None
    if os.getenv("BASE_PROVIDER_MODE", "disabled").strip().lower() == "feishu":
        raw = _feishu_records()
        if raw is not None and raw:
            records = [_map_feishu_record(r) for r in raw]
    ips = [apply_display_fields(r) for r in (records if records else IP_LIBRARY_SEED)]
    _library_cache = ips
    return ips


def reset_library_cache() -> None:
    """测试辅助：清缓存"""
    global _library_cache
    _library_cache = None


# ── IP官候选池合并（策展 12 + 扩充 33，同名/别名去重，字段并集）──────────────

def merged_candidate_pool(curated_pool: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """把扩充库并入 IP官 候选池。

    curated_pool：insightBase.ipPool（各数据源供给）。
    去重键：normalize_ip_name（含别名归一）；命中时保留并集：
    策展侧 styleTags/matrix/audience + 扩充侧 授权方/合作状态/价格带/热度。
    """
    from app.planning.ip_resource import IP_RESOURCE

    pool: list[dict[str, Any]] = [dict(ip) for ip in (curated_pool or [])]
    seen = {normalize_ip_name(str(ip.get("name") or "")) for ip in pool}

    # 策展 12（ip_resource）先并入（去重）
    for ip in IP_RESOURCE:
        key = normalize_ip_name(str(ip.get("nameCn") or ip.get("name") or ""))
        if key and key not in seen:
            seen.add(key)
            pool.append({
                "name": ip.get("nameCn") or ip.get("name"),
                "status": "合作中",
                "heat": str(ip.get("heat", "")),
                "fit": [f"风格：{'、'.join(ip.get('styleTags', [])[:3])}"],
                "audienceGroup": ip.get("audienceGroup"),
                "styleTags": ip.get("styleTags"),
                "matrix": ip.get("matrix"),
            })

    # 扩充 33（ip_library）并入：同名保留并集
    for ip in get_ip_library():
        key = normalize_ip_name(str(ip.get("name") or ""))
        if not key:
            continue
        price_band = f"¥{ip.get('priceMin', '?')}-¥{ip.get('priceMax', '?')}"
        extra = {
            "licensor": ip.get("licensor"),
            "cooperationStatus": ip.get("cooperationStatus"),
            "priceBand": price_band,
            "ipHeat": ip.get("ipHeat"),
        }
        if key in seen:
            for exist in pool:
                if normalize_ip_name(str(exist.get("name") or "")) == key:
                    for k, v in extra.items():
                        if v is not None:
                            exist.setdefault(k, v)
                    break
        else:
            seen.add(key)
            pool.append({
                "name": ip.get("name"),
                "status": ip.get("cooperationStatus") or "合作中",
                "heat": str(ip.get("ipHeat", "")),
                "fit": [f"{ip.get('licensor', '')} · {ip.get('latestSeries', '')[:40]}"],
                **extra,
                "audienceGroup": ip.get("audienceGroup"),
                "styleTags": ip.get("styleTags"),
                "matrix": ip.get("matrix"),
            })
    return pool
