"""
飞书配置
"""
import os

from pydantic import BaseModel


class FeishuConfig(BaseModel):
    """飞书应用配置"""
    app_id: str
    app_secret: str
    # 验证回调的 token 和加密 key（事件与回调页面配置）
    verification_token: str = ""
    encrypt_key: str = ""

    @classmethod
    def from_env(cls) -> "FeishuConfig":
        """从环境变量加载配置"""
        return cls(
            app_id=os.getenv("FEISHU_APP_ID", ""),
            app_secret=os.getenv("FEISHU_APP_SECRET", ""),
            verification_token=os.getenv("FEISHU_VERIFICATION_TOKEN", ""),
            encrypt_key=os.getenv("FEISHU_ENCRYPT_KEY", ""),
        )
