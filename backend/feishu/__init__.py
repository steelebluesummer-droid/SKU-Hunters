"""
飞书对接模块
- 群机器人 WebSocket 长连接与 Card 2.0 交互
- 六步企划闭环：机会点选、企划卡、归档与在线完整企划文档
- 企划通知与多维表格资产同步
"""

from .bot import FeishuBot
from .config import FeishuConfig

__all__ = ["FeishuBot", "FeishuConfig"]
