"""
双管线整合（Dual Pipeline）
从 FictionForge gen_proxy.py + gen.py 提取适配。

架构：
- 本地管线：直接 HTTP 调用本地/局域网 LLM 服务（如 llama.cpp / vLLM / Ollama）
- API 代理管线：通过 OpenRouter / DeepSeek / DashScope 等平台的 OpenAI 兼容 API
- 统一接口 DualPipeline.pipe()，按 model 标识自动路由

适用场景：
- 小说世界用户可自由切换本地模型与云端 API
- 降级策略：API 不可用时自动回退本地管线
- SSE 流式支持（可选）
"""

from __future__ import annotations

import json
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


# ── 管线配置 ───────────────────────────────────────────────────────────────

@dataclass
class PipeConfig:
    """管线配置。

    示例：
        local: PipeConfig(kind="local", base_url="http://localhost:8080/v1",
                          model="qwen2.5-7b", api_key="not-needed")

        api: PipeConfig(kind="api", base_url="https://api.openai.com/v1",
                        model="gpt-4o", api_key="sk-xxx", provider="openai")
    """
    kind: str = "api"                          # "local" | "api"
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o"
    api_key: str = ""
    provider: str = "openai"                   # "openai" | "openrouter" | "deepseek" | "dashscope"
    max_tokens: int = 4096
    temperature: float = 0.8
    timeout: int = 120                         # 请求超时秒数
    max_retries: int = 2                       # 失败重试
    extra_headers: dict = field(default_factory=dict)

    @property
    def chat_url(self) -> str:
        """拼接 chat completions 端点。"""
        base = self.base_url.rstrip("/")
        if self.provider == "dashscope":
            # DashScope 使用独立的 text-generation API
            return f"{base}/services/aigc/text-generation/generation"
        return f"{base}/chat/completions"

    def to_headers(self) -> dict:
        """构建 HTTP 请求头。"""
        headers = {"Content-Type": "application/json"}
        if self.provider == "dashscope":
            headers["Authorization"] = f"Bearer {self.api_key}"
        elif self.provider == "openrouter":
            headers["Authorization"] = f"Bearer {self.api_key}"
            headers["HTTP-Referer"] = "https://novel-world.local"
            headers["X-Title"] = "NovelWorld"
        else:
            headers["Authorization"] = f"Bearer {self.api_key}"
        headers.update(self.extra_headers)
        return headers


# ── 双管线 ─────────────────────────────────────────────────────────────────

class DualPipeline:
    """
    双管线统一接口。

    使用示例：
        local_cfg = PipeConfig(kind="local", base_url="http://localhost:8080/v1",
                               model="qwen2.5-7b", api_key="not-needed")
        api_cfg = PipeConfig(kind="api", base_url="https://api.openai.com/v1",
                             model="gpt-4o", api_key="sk-xxx")
        pipe = DualPipeline(local_config=local_cfg, api_config=api_cfg)
        text = pipe.pipe("写一段玄幻开篇")
    """

    def __init__(self,
                 local_config: Optional[PipeConfig] = None,
                 api_config: Optional[PipeConfig] = None,
                 default_pipe: str = "api",
                 on_fallback: Optional[Callable[[str, str], None]] = None):
        """
        Args:
            local_config: 本地管线配置
            api_config: API 管线配置
            default_pipe: 默认管线 ("local" | "api")
            on_fallback: 降级回调 (from_pipe, to_pipe) → None
        """
        self.local = local_config
        self.api = api_config
        self.default_pipe = default_pipe
        self.on_fallback = on_fallback

    def pipe(self, messages: list[dict], *,
             model: Optional[str] = None,
             temperature: Optional[float] = None,
             max_tokens: Optional[int] = None,
             stream: bool = False,
             force_local: bool = False) -> str:
        """
        统一调用：按模型名或 force_local 选择管线。

        Args:
            messages: OpenAI 格式消息列表 [{"role":"system","content":"..."}, ...]
            model: 指定模型（覆盖配置）
            temperature: 覆盖温度
            max_tokens: 覆盖 token 上限
            stream: 是否流式（暂不支持，预留）
            force_local: 强制使用本地管线

        Returns:
            LLM 生成的文本
        """
        # 选择管线
        config = self._select_config(model=model, force_local=force_local)

        # 尝试主管线
        try:
            return self._call(config, messages, temperature, max_tokens)
        except Exception as e:
            # 降级尝试
            fallback_config = self._fallback_config(config)
            if fallback_config:
                if self.on_fallback:
                    self.on_fallback(config.kind, fallback_config.kind)
                return self._call(fallback_config, messages, temperature, max_tokens)
            raise RuntimeError(f"双管线均不可用。主管线错误: {e}")

    def pipe_text(self, prompt: str, *, system: str = "",
                  model: Optional[str] = None,
                  temperature: Optional[float] = None,
                  max_tokens: Optional[int] = None,
                  force_local: bool = False) -> str:
        """
        便捷方法：单文本 prompt （自动转为 messages）。
        """
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return self.pipe(messages, model=model, temperature=temperature,
                         max_tokens=max_tokens, force_local=force_local)

    # ── 内部方法 ──

    def _select_config(self, model: Optional[str] = None,
                       force_local: bool = False) -> PipeConfig:
        """按优先级选择管线配置。"""
        if force_local:
            if not self.local:
                raise RuntimeError("未配置本地管线")
            return self.local
        if model:
            # 按模型名自动路由：含 "local:" 前缀 → 本地
            if model.startswith("local:"):
                if not self.local:
                    raise RuntimeError("未配置本地管线")
                cfg = PipeConfig(**{**self.local.__dict__, "model": model[6:]})
                return cfg
            else:
                if not self.api:
                    raise RuntimeError("未配置 API 管线")
                cfg = PipeConfig(**{**self.api.__dict__, "model": model})
                return cfg
        # 默认
        target = self.local if self.default_pipe == "local" else self.api
        if not target:
            # 回退到另一个
            fallback = self.api if self.default_pipe == "local" else self.local
            if not fallback:
                raise RuntimeError("双管线均未配置")
            return fallback
        return target

    def _fallback_config(self, failed: PipeConfig) -> Optional[PipeConfig]:
        """返回降级管线配置。"""
        if failed.kind == "api" and self.local:
            return self.local
        elif failed.kind == "local" and self.api:
            return self.api
        return None

    def _call(self, config: PipeConfig, messages: list[dict],
              temperature: Optional[float] = None,
              max_tokens: Optional[int] = None) -> str:
        """执行单次 LLM 调用。"""
        t = temperature if temperature is not None else config.temperature
        mt = max_tokens if max_tokens is not None else config.max_tokens

        if config.provider == "dashscope":
            return self._call_dashscope(config, messages, t, mt)
        return self._call_openai_compat(config, messages, t, mt)

    def _call_openai_compat(self, config: PipeConfig, messages: list[dict],
                            temperature: float, max_tokens: int) -> str:
        """OpenAI 兼容 API 调用（OpenAI / OpenRouter / DeepSeek / vLLM 等）。"""
        payload = {
            "model": config.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        data = json.dumps(payload).encode("utf-8")

        for attempt in range(config.max_retries + 1):
            try:
                req = urllib.request.Request(
                    config.chat_url,
                    data=data,
                    headers=config.to_headers(),
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=config.timeout) as resp:
                    body = resp.read().decode("utf-8")
                    result = json.loads(body)
                    return result["choices"][0]["message"]["content"]
            except urllib.error.HTTPError as e:
                error_body = e.read().decode("utf-8", errors="replace")
                if attempt < config.max_retries:
                    time.sleep(2 ** attempt)
                    continue
                raise RuntimeError(
                    f"LLM 调用失败 (HTTP {e.code}): {error_body[:300]}"
                ) from e
            except urllib.error.URLError as e:
                if attempt < config.max_retries:
                    time.sleep(2 ** attempt)
                    continue
                raise RuntimeError(f"LLM 连接失败: {e.reason}") from e

        raise RuntimeError("LLM 调用失败：已达最大重试次数")

    def _call_dashscope(self, config: PipeConfig, messages: list[dict],
                        temperature: float, max_tokens: int) -> str:
        """DashScope (阿里百炼) API 调用。"""
        # 转换 OpenAI 消息格式为 DashScope 格式
        dashscope_messages = []
        for msg in messages:
            dashscope_messages.append({
                "role": msg["role"],
                "content": msg["content"],
            })

        payload = {
            "model": config.model,
            "input": {"messages": dashscope_messages},
            "parameters": {
                "temperature": temperature,
                "max_tokens": max_tokens,
                "result_format": "message",
            },
        }
        data = json.dumps(payload).encode("utf-8")

        for attempt in range(config.max_retries + 1):
            try:
                req = urllib.request.Request(
                    config.chat_url,
                    data=data,
                    headers=config.to_headers(),
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=config.timeout) as resp:
                    body = resp.read().decode("utf-8")
                    result = json.loads(body)
                    return result["output"]["choices"][0]["message"]["content"]
            except (urllib.error.HTTPError, urllib.error.URLError) as e:
                if attempt < config.max_retries:
                    time.sleep(2 ** attempt)
                    continue
                raise RuntimeError(f"DashScope 调用失败: {e}") from e

        raise RuntimeError("DashScope 调用失败：已达最大重试次数")


# ── 便捷工厂函数 ──────────────────────────────────────────────────────────

def create_default_pipeline() -> DualPipeline:
    """创建基于环境默认值的最小管线（本地 Ollama + 空 API 插槽）。"""
    local_cfg = PipeConfig(
        kind="local",
        base_url="http://localhost:11434/v1",
        model="qwen2.5:7b",
        api_key="ollama",
        provider="openai",
    )
    # API 插槽留空，由用户在前端填写
    api_cfg = PipeConfig(
        kind="api",
        base_url="https://api.openai.com/v1",
        model="gpt-4o",
        api_key="",
        provider="openai",
    )
    return DualPipeline(local_config=local_cfg, api_config=api_cfg, default_pipe="api")
