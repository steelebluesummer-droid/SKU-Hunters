"""pytest 根配置：保证从 backend/ 目录运行 pytest 时 app 包可导入"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest


@pytest.fixture(autouse=True)
def isolated_test_env(monkeypatch):
    """测试环境与本地 .env 解耦：CI 无 .env，本地 .env 的 AGENT_PROVIDER=real、
    PLANNING_DEFAULT_MODE 等配置不得影响「默认值」类断言。

    显式测试严格模式/生产行为的用例会在自身 fixture 中再次覆盖这些变量。
    """
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.delenv("AGENT_PROVIDER", raising=False)
    monkeypatch.delenv("PLANNING_DEFAULT_MODE", raising=False)
    monkeypatch.delenv("ALLOW_MOCK", raising=False)
