# -*- coding: utf-8 -*-
"""
小说世界 - 多模型路由模块
移植自：书斋V66 backend/ai_client.py

支持的 Provider：
  - deepseek  : DeepSeek V4 系列（默认）
  - ollama    : Ollama 本地模型
  - openai    : OpenAI GPT 系列
  - doubao    : 豆包（火山引擎 ark，OpenAI 兼容接口）
  - kimi      : Kimi / 月之暗面 Moonshot（OpenAI 兼容接口）

API Key 读取优先级（每个 provider 独立）：
  1. 对应的环境变量
  2. data/ai_config.json 中的 api_key 字段
"""
import json
import os
import sys
import time
import logging
import httpx
from typing import Optional, Callable, Dict, Union, Tuple

logger = logging.getLogger(__name__)


class AIClientException(Exception):
    """AI 调用异常"""

    def __init__(self, message: str, error_type: str = "unknown"):
        super().__init__(message)
        self.error_type = error_type


class ModelRouter:
    """统一 AI 调用接口 — 多模型路由"""

    def __init__(self, config_path: str = None):
        if config_path is None:
            if getattr(sys, "frozen", False):
                # PyInstaller 打包态：配置写 exe 同目录 data/（绿色便携）
                base = os.environ.get("NOVEL_WORLD_WRITABLE", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                config_path = os.path.join(base, "data", "ai_config.json")
            else:
                config_path = os.path.join(
                    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "data", "ai_config.json"
                )
        self.config_path = config_path
        self.config = self._load_config()
        self._ensure_defaults()
        self._client = httpx.Client(timeout=httpx.Timeout(300.0, connect=10.0))
        self.usage_log: list = []
        self._usage_file = os.path.join(
            os.path.dirname(self.config_path), "ai_usage.json"
        )
        self._load_usage()

    # ── 配置管理 ────────────────────────────

    def _load_config(self) -> dict:
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                logger.warning(
                    "ai_config.json 损坏 (%s)，使用空配置并覆盖", e
                )
        return {}

    def _save_config(self):
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(self.config, f, ensure_ascii=False, indent=2)

    # ── 用量追踪 ────────────────────────────

    _PRICING = {
        "deepseek": {"input": 1.0, "output": 2.0},
        "openai": {"input": 2.5, "output": 10.0},
        "doubao": {"input": 0.8, "output": 2.0},
        "kimi": {"input": 12.0, "output": 12.0},
        "ollama": {"input": 0, "output": 0},
    }

    def _load_usage(self):
        try:
            if os.path.exists(self._usage_file):
                with open(self._usage_file, "r", encoding="utf-8") as f:
                    self.usage_log = json.load(f)
        except Exception:
            self.usage_log = []

    def _save_usage(self):
        try:
            os.makedirs(os.path.dirname(self._usage_file), exist_ok=True)
            if len(self.usage_log) > 500:
                self.usage_log = self.usage_log[-500:]
            with open(self._usage_file, "w", encoding="utf-8") as f:
                json.dump(self.usage_log, f, ensure_ascii=False)
        except Exception as e:
            logger.debug("保存用量日志失败: %s", e)

    def _record_usage(
        self, provider: str, model: str, usage: dict, task: str = ""
    ):
        if not usage:
            return
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        total_tokens = usage.get(
            "total_tokens", prompt_tokens + completion_tokens
        )
        pricing = self._PRICING.get(provider, {"input": 0, "output": 0})
        cost = (
            prompt_tokens * pricing["input"]
            + completion_tokens * pricing["output"]
        ) / 1_000_000
        entry = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "provider": provider,
            "model": model,
            "task": task,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "cost_cny": round(cost, 4),
        }
        self.usage_log.append(entry)
        self._save_usage()

    def get_usage_stats(self) -> dict:
        total_input = sum(
            e.get("prompt_tokens", 0) for e in self.usage_log
        )
        total_output = sum(
            e.get("completion_tokens", 0) for e in self.usage_log
        )
        total_cost = sum(e.get("cost_cny", 0) for e in self.usage_log)
        by_day = {}
        for e in self.usage_log:
            day = e.get("timestamp", "")[:10]
            if day not in by_day:
                by_day[day] = {"calls": 0, "tokens": 0, "cost": 0}
            by_day[day]["calls"] += 1
            by_day[day]["tokens"] += e.get("total_tokens", 0)
            by_day[day]["cost"] += e.get("cost_cny", 0)

        # 月度配额预警：data/ai_config.json 顶层配置 monthly_quota_tokens（0/缺省=不限）
        month_prefix = time.strftime("%Y-%m")
        month_tokens = sum(
            e.get("total_tokens", 0) for e in self.usage_log
            if str(e.get("timestamp", "")).startswith(month_prefix)
        )
        month_cost = sum(
            e.get("cost_cny", 0) for e in self.usage_log
            if str(e.get("timestamp", "")).startswith(month_prefix)
        )
        try:
            quota_tokens = int(self.config.get("monthly_quota_tokens", 0) or 0)
        except (TypeError, ValueError):
            quota_tokens = 0
        monthly = {
            "month": month_prefix,
            "quota_tokens": quota_tokens,
            "used_tokens": month_tokens,
            "used_cost_cny": round(month_cost, 2),
            "used_pct": round(month_tokens * 100 / quota_tokens, 1) if quota_tokens > 0 else 0,
            # ok / warning(≥80%) / exceeded(≥100%) / unlimited
            "level": "unlimited",
        }
        if quota_tokens > 0:
            monthly["level"] = (
                "exceeded" if month_tokens >= quota_tokens
                else "warning" if month_tokens >= quota_tokens * 0.8
                else "ok"
            )

        return {
            "total_calls": len(self.usage_log),
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_tokens": total_input + total_output,
            "total_cost_cny": round(total_cost, 2),
            "by_day": by_day,
            "recent": self.usage_log[-20:],
            "monthly": monthly,
        }

    # ── Provider 管理 ────────────────────────

    _ENV_KEY_MAP = {
        "deepseek": "DEEPSEEK_API_KEY",
        "openai": "OPENAI_API_KEY",
        "doubao": "DOUBAO_API_KEY",
        "kimi": "KIMI_API_KEY",
    }

    def _get_api_key(self, cfg: dict, provider: str = None) -> str:
        if provider and provider in self._ENV_KEY_MAP:
            env_key = os.environ.get(self._ENV_KEY_MAP[provider], "")
            if env_key:
                return env_key
        env_key = os.environ.get("DEEPSEEK_API_KEY", "")
        if env_key:
            return env_key
        file_key = cfg.get("api_key", "")
        if file_key and (
            file_key.startswith("sk-")
            or file_key.startswith("ms-")
            or len(file_key) >= 20
        ):
            return file_key
        return ""

    def _ensure_defaults(self):
        if "provider" not in self.config:
            self.config["provider"] = "deepseek"
        defaults = {
            "deepseek": {
                "api_key": "",
                "base_url": "https://api.deepseek.com",
                "model": "deepseek-v4-flash",
                "thinking": "disabled",
                "temperature": 0.7,
                "max_tokens": 8192,
            },
            "ollama": {
                "base_url": "http://127.0.0.1:11434",
                "model": "qwen3:14b",
                "temperature": 0.7,
                "max_tokens": 4096,
            },
            "openai": {
                "api_key": "",
                "base_url": "https://api.openai.com/v1",
                "model": "gpt-4o-mini",
                "temperature": 0.7,
                "max_tokens": 4096,
            },
            "doubao": {
                "api_key": "",
                "base_url": "https://ark.cn-beijing.volces.com/api/v3",
                "model": "doubao-pro-32k",
                "temperature": 0.7,
                "max_tokens": 4096,
            },
            "kimi": {
                "api_key": "",
                "base_url": "https://api.moonshot.cn/v1",
                "model": "moonshot-v1-8k",
                "temperature": 0.7,
                "max_tokens": 4096,
            },
        }
        for k, v in defaults.items():
            if k not in self.config:
                self.config[k] = dict(v)
        self._save_config()

    def set_provider(self, provider: str):
        self.config["provider"] = provider
        self._save_config()

    def get_provider(self) -> str:
        return self.config.get("provider", "deepseek")

    # ── 多模型路由 ───────────────────────────

    TASK_MODEL_MAP = {
        "architecture": {
            "deepseek": "deepseek-v4-pro",
            "openai": "gpt-4o",
            "doubao": "doubao-pro-32k",
            "kimi": "moonshot-v1-32k",
            "desc": "架构/大纲/复杂设计",
        },
        "writing": {
            "deepseek": "deepseek-v4-flash",
            "openai": "gpt-4o-mini",
            "doubao": "doubao-pro-32k",
            "kimi": "moonshot-v1-8k",
            "desc": "正文写作",
        },
        "check": {
            "deepseek": "deepseek-v4-flash",
            "openai": "gpt-4o-mini",
            "doubao": "doubao-pro-32k",
            "kimi": "moonshot-v1-8k",
            "desc": "检查/审核",
        },
        "summary": {
            "deepseek": "deepseek-v4-flash",
            "openai": "gpt-4o-mini",
            "doubao": "doubao-pro-32k",
            "kimi": "moonshot-v1-8k",
            "desc": "摘要/提取",
        },
        "chat": {
            "deepseek": "deepseek-v4-flash",
            "openai": "gpt-4o-mini",
            "doubao": "doubao-pro-32k",
            "kimi": "moonshot-v1-8k",
            "desc": "对话/问答",
        },
    }

    def get_model_for_task(self, task_type: str = "chat") -> str:
        provider = self.get_provider()
        task_map = self.TASK_MODEL_MAP.get(
            task_type, self.TASK_MODEL_MAP["chat"]
        )
        return task_map.get(provider, task_map.get("deepseek", "deepseek-v4-flash"))

    def chat_with_messages(
        self,
        messages: list,
        on_chunk: Callable = None,
        temperature: float = None,
        max_tokens: int = None,
        task: str = "",
    ) -> str:
        """使用 messages 格式调用 AI，支持 system/user/assistant 多角色。

        messages 格式：[{"role": "system", "content": "..."}, {"role": "user", "content": "..."}]
        与 generate() 的区别：generate() 只发送单条 user prompt，本方法发送完整 messages 数组。
        """
        provider = self.config["provider"]
        cfg = dict(self.config.get(provider, {}))
        if temperature is not None:
            cfg["temperature"] = temperature
        if max_tokens is not None:
            cfg["max_tokens"] = max_tokens

        model = cfg.get("model", "unknown")
        temp = cfg.get("temperature", 0.7)
        mt = cfg.get("max_tokens", 4096)

        logger.info(
            "[AI] chat_with_messages: provider=%s, model=%s, "
            "msg_count=%s, task=%s",
            provider, model, len(messages), task,
        )

        last_error = None
        for attempt in range(3):
            if provider == "ollama":
                # Ollama 用 generate API，将 messages 拼接为 prompt
                prompt = self._ollama_messages_to_prompt(messages)
                result = self._ollama_generate(
                    prompt, cfg, on_chunk, task=task
                )
            elif provider in ("deepseek", "openai", "doubao", "kimi"):
                result = self._openai_compatible_messages(
                    messages, cfg, on_chunk, task=task
                )
            else:
                msg = f"不支持的 provider: {provider}"
                logger.error("[AI] 调用失败: %s", msg)
                return f"[错误] {msg}"

            if isinstance(result, str) and result.startswith(
                ("[错误]", "[生成失败:")
            ):
                last_error = result
                if attempt < 2:
                    wait = 2 ** attempt
                    logger.warning(
                        "[AI] 调用失败，%s秒后重试 (%s/3): %s",
                        wait, attempt + 1, result[:100],
                    )
                    time.sleep(wait)
                    continue
            else:
                logger.info("[AI] chat_with_messages 成功: result_len=%s", len(result))
                return result

        logger.error("[AI] 调用失败: %s", last_error)
        return last_error or "[生成失败: 未知错误]"

    @staticmethod
    def _ollama_messages_to_prompt(messages: list) -> str:
        """将 messages 列表拼接为 Ollama prompt 字符串"""
        parts = []
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            if role == "system":
                parts.append(f"<system>\n{content}\n</system>")
            elif role == "assistant":
                parts.append(f"<assistant>\n{content}\n</assistant>")
            else:
                parts.append(f"<user>\n{content}\n</user>")
        return "\n".join(parts) + "\n<assistant>\n"

    def _openai_compatible_messages(
        self,
        messages: list,
        cfg: dict,
        on_chunk: Callable = None,
        task: str = "",
    ) -> str:
        """OpenAI 兼容 API 调用 —— messages 版本"""
        base = cfg.get("base_url", "https://api.deepseek.com")
        provider = self.get_provider()
        api_key = self._get_api_key(cfg, provider=provider)
        model = cfg.get("model", "deepseek-v4-flash")

        if not api_key:
            msg = "未配置 API Key"
            return f"[错误] {msg}"

        body = {
            "model": model,
            "messages": messages,
            "temperature": cfg.get("temperature", 0.7),
            "max_tokens": cfg.get("max_tokens", 4096),
            "stream": on_chunk is not None,
        }
        if on_chunk is not None:
            body["stream_options"] = {"include_usage": True}
        thinking = cfg.get("thinking", "disabled")
        if provider == "deepseek":
            body["thinking"] = {
                "type": "enabled" if thinking == "enabled" else "disabled"
            }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }

        try:
            if on_chunk:
                result = []
                parse_errors = 0
                stream_usage = None
                with self._client.stream(
                    "POST",
                    f"{base}/chat/completions",
                    json=body,
                    headers=headers,
                ) as resp:
                    # 非 200 时错误体不是 SSE，直接读文本报错（避免吞成空串）
                    if resp.status_code != 200:
                        err_text = resp.read().decode("utf-8", errors="replace")[:200]
                        msg = f"API 错误 {resp.status_code}: {err_text}"
                        logger.error(msg)
                        return f"[生成失败: {msg}]"
                    for line_bytes in resp.iter_lines():
                        line = line_bytes.strip()
                        if line.startswith("data: ") and line != "data: [DONE]":
                            try:
                                chunk = json.loads(line[6:])
                                delta = (
                                    chunk.get("choices", [{}])[0].get(
                                        "delta", {}
                                    )
                                )
                                token = delta.get("content", "")
                                if token:
                                    on_chunk(token)
                                    result.append(token)
                                if chunk.get("usage"):
                                    stream_usage = chunk["usage"]
                            except Exception:
                                parse_errors += 1
                if parse_errors > 0:
                    logger.warning("流式解析错误 %s 行", parse_errors)
                if stream_usage:
                    self._record_usage(provider, model, stream_usage, task)
                return "".join(result)
            else:
                resp = self._client.post(
                    f"{base}/chat/completions",
                    json=body,
                    headers=headers,
                )
                # httpx 不会自动抛 HTTP 错误：非 200 必须显式报错，
                # 否则 401/4xx 的错误 JSON 无 choices，会被吞成空串误判成功
                if resp.status_code != 200:
                    msg = f"API 错误 {resp.status_code}: {resp.text[:200]}"
                    logger.error(msg)
                    return f"[生成失败: {msg}]"
                data = resp.json()
                usage = data.get("usage")
                if usage:
                    self._record_usage(provider, model, usage, task)
                choice = data.get("choices", [{}])[0]
                msg = choice.get("message", {})
                content = msg.get("content", "")
                if content:
                    return content
                reasoning = msg.get("reasoning_content", "")
                if reasoning:
                    return reasoning
                logger.warning("AI返回content和reasoning_content均为空")
                return ""
        except httpx.HTTPStatusError as e:
            try:
                err_detail = ""
                try:
                    err_json = e.response.json()
                    err_detail = err_json.get("error", {}).get(
                        "message", str(err_json)
                    )
                except Exception:
                    err_detail = e.response.text[:200]
                msg = f"API 错误 {e.response.status_code}: {err_detail}"
            except Exception:
                msg = f"API 错误 {e.response.status_code}"
            logger.error(msg)
            return f"[生成失败: {msg}]"
        except httpx.RequestError as e:
            msg = f"网络连接失败: {e}"
            logger.error(msg)
            return f"[生成失败: {e}]"
        except Exception as e:
            msg = f"生成失败: {e}"
            logger.error(msg)
            return f"[生成失败: {e}]"

    def generate_for_task(
        self, prompt: str, task_type: str = "chat", **kwargs
    ) -> str:
        import copy

        model = self.get_model_for_task(task_type)
        provider = self.get_provider()
        old_model = self.config.get(provider, {}).get("model", "")
        self.config[provider] = copy.deepcopy(self.config.get(provider, {}))
        self.config[provider]["model"] = model
        try:
            result = self.generate(prompt, task=task_type, **kwargs)
        finally:
            self.config[provider] = copy.deepcopy(
                self.config.get(provider, {})
            )
            self.config[provider]["model"] = old_model
        return result

    # ── 兼容旧 chat 接口 ────────────────────

    def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.8,
        max_tokens: int = 4096,
        task: str = "chat",
        on_chunk: Callable = None,
    ) -> str:
        """通用 chat 调用（兼容旧 AIClient 接口）。

        task 非 "chat" 时走 generate_for_task 路由到强模型。
        on_chunk 透传给 generate 启用流式输出（必须接受，否则
        ai_client.chat 兼容层传参会导致所有调用抛 TypeError）。
        """
        prompt = f"System: {system_prompt}\n\nUser: {user_prompt}"
        logger.warning("[DIAG] ModelRouter.chat called: task=%s, prompt_len=%s", task, len(prompt))
        if task != "chat":
            return self.generate_for_task(
                prompt, task_type=task,
                temperature=temperature, max_tokens=max_tokens,
            )
        return self.generate(
            prompt, on_chunk=on_chunk, temperature=temperature,
            max_tokens=max_tokens, task=task,
        )

    # ── 核心生成 ─────────────────────────────

    def generate(
        self,
        prompt: str,
        on_chunk: Callable = None,
        temperature: float = None,
        max_tokens: int = None,
        raise_on_error: bool = False,
        task: str = "",
    ) -> str:
        provider = self.config["provider"]
        cfg = dict(self.config.get(provider, {}))
        if temperature is not None:
            cfg["temperature"] = temperature
        if max_tokens is not None:
            cfg["max_tokens"] = max_tokens

        model = cfg.get("model", "unknown")
        temp = cfg.get("temperature", 0.7)
        mt = cfg.get("max_tokens", 4096)

        logger.info(
            "[AI] 开始调用: provider=%s, model=%s, temp=%s, "
            "max_tokens=%s, prompt_len=%s, task=%s",
            provider, model, temp, mt, len(prompt), task,
        )

        last_error = None
        for attempt in range(3):
            if provider == "ollama":
                result = self._ollama_generate(
                    prompt, cfg, on_chunk, task=task
                )
            elif provider in ("deepseek", "openai", "doubao", "kimi"):
                result = self._openai_compatible(
                    prompt, cfg, on_chunk, task=task
                )
            else:
                msg = f"不支持的 provider: {provider}"
                logger.error("[AI] 调用失败: %s", msg)
                if raise_on_error:
                    raise AIClientException(msg, "config_error")
                return f"[错误] {msg}"

            if isinstance(result, str) and result.startswith(
                ("[错误]", "[生成失败:")
            ):
                last_error = result
                if attempt < 2:
                    wait = 2 ** attempt
                    logger.warning(
                        "[AI] 调用失败，%s秒后重试 (%s/3): %s",
                        wait, attempt + 1, result[:100],
                    )
                    time.sleep(wait)
                    continue
            else:
                logger.info("[AI] 调用成功: result_len=%s", len(result))
                return result

        logger.error(
            "[AI] 调用失败 (%s次重试后): %s", attempt + 1, last_error
        )
        if raise_on_error and last_error:
            raise AIClientException(last_error, "api_error")
        return last_error or "[生成失败: 未知错误]"

    def generate_safe(self, prompt: str, **kwargs) -> Tuple[bool, str]:
        kwargs["raise_on_error"] = False
        result = self.generate(prompt, **kwargs)
        if isinstance(result, str) and result.startswith(
            ("[错误]", "[生成失败:")
        ):
            return False, result
        # 空返回也是失败（如 401 被吞成空串），不得误报成功
        if not isinstance(result, str) or not result.strip():
            return False, "AI 返回空内容（请检查 API Key 与模型名是否有效）"
        return True, result

    # ── Ollama ──────────────────────────────

    def _ollama_generate(
        self,
        prompt: str,
        cfg: dict,
        on_chunk: Callable = None,
        task: str = "",
    ) -> str:
        base = cfg.get("base_url", "http://127.0.0.1:11434")
        model = cfg.get("model", "qwen3:14b")
        body = {
            "model": model,
            "prompt": prompt,
            "stream": on_chunk is not None,
            "options": {
                "temperature": cfg.get("temperature", 0.7),
                "num_predict": cfg.get("max_tokens", 4096),
            },
        }
        try:
            if on_chunk:
                result = []
                parse_errors = 0
                with self._client.stream(
                    "POST", f"{base}/api/generate", json=body
                ) as resp:
                    for line_bytes in resp.iter_lines():
                        line = line_bytes.strip()
                        if line:
                            try:
                                chunk = json.loads(line)
                                token = chunk.get("response", "")
                                if token:
                                    on_chunk(token)
                                    result.append(token)
                            except json.JSONDecodeError:
                                parse_errors += 1
                if parse_errors > 0:
                    logger.warning(
                        "Ollama 流式解析错误 %s 行", parse_errors
                    )
                return "".join(result)
            else:
                resp = self._client.post(
                    f"{base}/api/generate", json=body
                )
                return resp.json().get("response", "")
        except httpx.RequestError as e:
            msg = f"Ollama 连接失败: {e}"
            logger.error(msg)
            return f"[生成失败: {e}]"
        except Exception as e:
            msg = f"Ollama 生成失败: {e}"
            logger.error(msg)
            return f"[生成失败: {e}]"

    # ── OpenAI 兼容 ──────────────────────────

    def _openai_compatible(
        self,
        prompt: str,
        cfg: dict,
        on_chunk: Callable = None,
        task: str = "",
    ) -> str:
        base = cfg.get("base_url", "https://api.deepseek.com")
        provider = self.get_provider()
        api_key = self._get_api_key(cfg, provider=provider)
        model = cfg.get("model", "deepseek-v4-flash")

        if not api_key:
            msg = (
                "未配置 API Key"
                "（请设置环境变量 DEEPSEEK_API_KEY 或在 ai_config.json 中配置）"
            )
            return f"[错误] {msg}"

        body = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": cfg.get("temperature", 0.7),
            "max_tokens": cfg.get("max_tokens", 4096),
            "stream": on_chunk is not None,
        }
        if on_chunk is not None:
            body["stream_options"] = {"include_usage": True}
        thinking = cfg.get("thinking", "disabled")
        if provider == "deepseek":
            body["thinking"] = {
                "type": "enabled" if thinking == "enabled" else "disabled"
            }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }

        # 诊断日志：确认实际发出的请求参数
        logger.warning(
            "[DIAG] URL=%s, provider=%s, model=%s, thinking=%s, body_keys=%s",
            f"{base}/chat/completions", provider, model,
            body.get("thinking", "N/A"), list(body.keys()),
        )

        try:
            if on_chunk:
                result = []
                parse_errors = 0
                stream_usage = None
                with self._client.stream(
                    "POST",
                    f"{base}/chat/completions",
                    json=body,
                    headers=headers,
                ) as resp:
                    # 非 200 时错误体不是 SSE，直接读文本报错（避免吞成空串）
                    if resp.status_code != 200:
                        err_text = resp.read().decode("utf-8", errors="replace")[:200]
                        msg = f"API 错误 {resp.status_code}: {err_text}"
                        logger.error(msg)
                        return f"[生成失败: {msg}]"
                    for line_bytes in resp.iter_lines():
                        line = line_bytes.strip()
                        if line.startswith("data: ") and line != "data: [DONE]":
                            try:
                                chunk = json.loads(line[6:])
                                delta = (
                                    chunk.get("choices", [{}])[0].get(
                                        "delta", {}
                                    )
                                )
                                token = delta.get("content", "")
                                if token:
                                    on_chunk(token)
                                    result.append(token)
                                if chunk.get("usage"):
                                    stream_usage = chunk["usage"]
                            except Exception:
                                parse_errors += 1
                if parse_errors > 0:
                    logger.warning(
                        "OpenAI兼容流式解析错误 %s 行", parse_errors
                    )
                if stream_usage:
                    self._record_usage(
                        provider, model, stream_usage, task
                    )
                return "".join(result)
            else:
                resp = self._client.post(
                    f"{base}/chat/completions",
                    json=body,
                    headers=headers,
                )
                # httpx 不会自动抛 HTTP 错误：非 200 必须显式报错，
                # 否则 401/4xx 的错误 JSON 无 choices，会被吞成空串误判成功
                if resp.status_code != 200:
                    msg = f"API 错误 {resp.status_code}: {resp.text[:200]}"
                    logger.error(msg)
                    return f"[生成失败: {msg}]"
                data = resp.json()
                usage = data.get("usage")
                if usage:
                    self._record_usage(provider, model, usage, task)
                choice = data.get("choices", [{}])[0]
                msg = choice.get("message", {})
                content = msg.get("content", "")
                if content:
                    return content
                reasoning = msg.get("reasoning_content", "")
                if reasoning:
                    return reasoning
                logger.warning("AI返回content和reasoning_content均为空")
                return ""
        except httpx.HTTPStatusError as e:
            try:
                err_detail = ""
                try:
                    err_json = e.response.json()
                    err_detail = err_json.get("error", {}).get(
                        "message", str(err_json)
                    )
                except Exception:
                    err_detail = e.response.text[:200]
                msg = (
                    f"API 错误 {e.response.status_code}: {err_detail}"
                )
            except Exception:
                msg = f"API 错误 {e.response.status_code}"
            logger.error(msg)
            return f"[生成失败: {msg}]"
        except httpx.RequestError as e:
            msg = f"网络连接失败: {e}"
            logger.error(msg)
            return f"[生成失败: {e}]"
        except Exception as e:
            msg = f"生成失败: {e}"
            logger.error(msg)
            return f"[生成失败: {e}]"

    # ── 工具方法 ─────────────────────────────

    def test_connection(self) -> bool:
        try:
            result = self.generate("回复'OK'", raise_on_error=True)
            return len(result) > 0
        except (AIClientException, Exception):
            return False

    def close(self):
        self._client.close()

    def __del__(self):
        try:
            self._client.close()
        except Exception:
            pass
