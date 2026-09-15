"""
双管线整合（Dual Pipeline）
从 FictionForge 的 server/gen_proxy.py 和 scripts/gen.py 提取双管线架构：
- 本地 LLM 调用（直接 HTTP 请求本地/局域网模型服务）
- API 代理（OpenRouter / DeepSeek / DashScope 统一路由 + SSE 转发）

主要导出：
- PipeConfig: 管线配置（服务地址/认证/模型名）
- DualPipeline: 统一接口，按模型名自动选择后端
- pipe_text(): 文本生成便捷方法
"""
from .pipeline import (
    PipeConfig,
    DualPipeline,
)

__all__ = [
    "PipeConfig",
    "DualPipeline",
]
