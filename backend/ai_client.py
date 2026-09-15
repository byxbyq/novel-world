# -*- coding: utf-8 -*-
"""书斋 V66 - AI 模型客户端

支持的 Provider：
  - deepseek  : DeepSeek V4 系列（默认）
  - ollama    : Ollama 本地模型
  - openai    : OpenAI GPT 系列
  - doubao    : 豆包（火山引擎 ark，OpenAI 兼容接口）
  - kimi      : Kimi / 月之暗面 Moonshot（OpenAI 兼容接口）

API Key 读取优先级（每个 provider 独立）：
  1. 对应的环境变量（见下方列表）
  2. data/ai_config.json 中的 api_key 字段

环境变量映射：
  DEEPSEEK_API_KEY  → deepseek
  OPENAI_API_KEY    → openai
  DOUBAO_API_KEY    → doubao（火山引擎 Ark API Key）
  KIMI_API_KEY      → kimi（月之暗面 Moonshot API Key）
"""
import json, os, sys, time, logging
import httpx
from typing import Optional, Callable, Dict, Union, Tuple

logger = logging.getLogger(__name__)

# 合法的 provider 集合（与 generate() 的分发分支保持一致）
VALID_PROVIDERS = ("deepseek", "ollama", "openai", "doubao", "kimi")


class AIClientException(Exception):
    """AI 调用异常 — 区分正常输出与调用失败"""
    def __init__(self, message: str, error_type: str = "unknown"):
        super().__init__(message)
        self.error_type = error_type  # config_error / network_error / api_error / timeout / parse_error


class AIClient:
    """统一 AI 调用接口"""

    def __init__(self, config_path: str = None):
        if config_path is None:
            if getattr(sys, "frozen", False):
                # PyInstaller 打包后写入用户目录
                data_dir = os.path.join(os.path.expanduser("~"), ".novel_world", "data")
                config_path = os.path.join(data_dir, "ai_config.json")
            else:
                config_path = os.path.join(os.path.dirname(__file__), "..", "data", "ai_config.json")
        self.config_path = config_path
        self.config = self._load_config()
        self._ensure_defaults()
        # 使用 httpx.Client 复用连接，300 秒超时匹配 AI 调用需求
        self._client = httpx.Client(timeout=httpx.Timeout(300.0, connect=10.0))
        # 用量追踪
        self.usage_log: list = []
        self._usage_file = os.path.join(os.path.dirname(self.config_path), "ai_usage.json")
        self._load_usage()

    def _load_config(self) -> dict:
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                logger.warning("ai_config.json 损坏 (%s)，使用空配置并覆盖", e)
        return {}

    def _save_config(self):
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, ensure_ascii=False, indent=2)

    # ── 用量追踪 ──────────────────────────────────

    # 各 provider 的单价（元/百万 token，仅估算）
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
                with open(self._usage_file, 'r', encoding='utf-8') as f:
                    self.usage_log = json.load(f)
        except Exception:
            self.usage_log = []

    def _save_usage(self):
        try:
            os.makedirs(os.path.dirname(self._usage_file), exist_ok=True)
            # 只保留最近500条
            if len(self.usage_log) > 500:
                self.usage_log = self.usage_log[-500:]
            with open(self._usage_file, 'w', encoding='utf-8') as f:
                json.dump(self.usage_log, f, ensure_ascii=False)
        except Exception as e:
            logger.debug(f"保存用量日志失败: {e}")

    def _record_usage(self, provider: str, model: str, usage: dict, task: str = ""):
        """记录一次 API 调用的 token 用量"""
        if not usage:
            return
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        total_tokens = usage.get("total_tokens", prompt_tokens + completion_tokens)
        pricing = self._PRICING.get(provider, {"input": 0, "output": 0})
        cost = (prompt_tokens * pricing["input"] + completion_tokens * pricing["output"]) / 1_000_000
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
        """获取用量统计"""
        total_input = sum(e.get("prompt_tokens", 0) for e in self.usage_log)
        total_output = sum(e.get("completion_tokens", 0) for e in self.usage_log)
        total_cost = sum(e.get("cost_cny", 0) for e in self.usage_log)
        # 按天统计
        by_day = {}
        for e in self.usage_log:
            day = e.get("timestamp", "")[:10]
            if day not in by_day:
                by_day[day] = {"calls": 0, "tokens": 0, "cost": 0}
            by_day[day]["calls"] += 1
            by_day[day]["tokens"] += e.get("total_tokens", 0)
            by_day[day]["cost"] += e.get("cost_cny", 0)
        return {
            "total_calls": len(self.usage_log),
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_tokens": total_input + total_output,
            "total_cost_cny": round(total_cost, 2),
            "by_day": by_day,
            "recent": self.usage_log[-20:],
        }

    # 各 provider 对应的环境变量名
    _ENV_KEY_MAP = {
        "deepseek": "DEEPSEEK_API_KEY",
        "openai":   "OPENAI_API_KEY",
        "doubao":   "DOUBAO_API_KEY",
        "kimi":     "KIMI_API_KEY",
    }

    def _get_api_key(self, cfg: dict, provider: str = None) -> str:
        """优先从环境变量读取 API Key，其次从配置文件"""
        if provider and provider in self._ENV_KEY_MAP:
            env_key = os.environ.get(self._ENV_KEY_MAP[provider], "")
            if env_key:
                return env_key
        # fallback: 兼容旧的 DEEPSEEK_API_KEY
        env_key = os.environ.get("DEEPSEEK_API_KEY", "")
        if env_key:
            return env_key
        file_key = cfg.get("api_key", "")
        if file_key and (file_key.startswith("sk-") or file_key.startswith("ms-") or len(file_key) >= 20):
            return file_key
        return ""

    def _ensure_defaults(self):
        if self.config.get("provider") not in VALID_PROVIDERS:
            bad = self.config.get("provider")
            if bad is not None:
                logger.warning(f"配置中 provider={bad!r} 非法，已回退为 deepseek")
            self.config["provider"] = "deepseek"
        if "deepseek" not in self.config:
            self.config["deepseek"] = {
                "api_key": "", "base_url": "https://api.deepseek.com",
                "model": "deepseek-v4-flash", "thinking": "disabled",
                "temperature": 0.7, "max_tokens": 8192
            }
        if "ollama" not in self.config:
            self.config["ollama"] = {
                "base_url": "http://127.0.0.1:11434", "model": "qwen3:14b",
                "temperature": 0.7, "max_tokens": 4096
            }
        if "openai" not in self.config:
            self.config["openai"] = {
                "api_key": "", "base_url": "https://api.openai.com/v1",
                "model": "gpt-4o-mini", "temperature": 0.7, "max_tokens": 4096
            }
        if "doubao" not in self.config:
            self.config["doubao"] = {
                "api_key": "",
                "base_url": "https://ark.cn-beijing.volces.com/api/v3",
                "model": "doubao-pro-32k",
                "temperature": 0.7, "max_tokens": 4096,
                "_comment": "API Key 获取: 火山引擎控制台 → Ark 大模型 → API Key 管理 → 创建密钥"
            }
        if "kimi" not in self.config:
            self.config["kimi"] = {
                "api_key": "",
                "base_url": "https://api.moonshot.cn/v1",
                "model": "moonshot-v1-8k",
                "temperature": 0.7, "max_tokens": 4096,
                "_comment": "API Key 获取: https://platform.moonshot.cn → 开发者中心 → API Key 管理",
                "_available_models": ["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"]
            }
        self._save_config()

    # M1: 多模型路由 — 按任务类型自动选模型
    TASK_MODEL_MAP = {
        "architecture": {
            "deepseek": "deepseek-v4-flash", "openai": "gpt-4o",
            "doubao": "doubao-pro-32k", "kimi": "moonshot-v1-32k",
            "desc": "架构/大纲/复杂设计"
        },
        "writing": {
            "deepseek": "deepseek-v4-flash", "openai": "gpt-4o-mini",
            "doubao": "doubao-pro-32k", "kimi": "moonshot-v1-8k",
            "desc": "正文写作"
        },
        "check": {
            "deepseek": "deepseek-v4-flash", "openai": "gpt-4o-mini",
            "doubao": "doubao-pro-32k", "kimi": "moonshot-v1-8k",
            "desc": "检查/审核"
        },
        "summary": {
            "deepseek": "deepseek-v4-flash", "openai": "gpt-4o-mini",
            "doubao": "doubao-pro-32k", "kimi": "moonshot-v1-8k",
            "desc": "摘要/提取"
        },
        "chat": {
            "deepseek": "deepseek-v4-flash", "openai": "gpt-4o-mini",
            "doubao": "doubao-pro-32k", "kimi": "moonshot-v1-8k",
            "desc": "对话/问答"
        },
    }

    def get_model_for_task(self, task_type: str = "chat") -> str:
        """按任务类型返回推荐模型名"""
        provider = self.get_provider()
        task_map = self.TASK_MODEL_MAP.get(task_type, self.TASK_MODEL_MAP["chat"])
        return task_map.get(provider, task_map.get("deepseek", "deepseek-v4-flash"))

    def generate_for_task(self, prompt: str, task_type: str = "chat", **kwargs) -> str:
        """按任务类型调用AI（自动选模型）"""
        import copy
        model = self.get_model_for_task(task_type)
        provider = self.get_provider()
        old_model = self.config.get(provider, {}).get("model", "")
        self.config[provider] = copy.deepcopy(self.config.get(provider, {}))
        self.config[provider]["model"] = model
        try:
            result = self.generate(prompt, task=task_type, **kwargs)
        finally:
            self.config[provider] = copy.deepcopy(self.config.get(provider, {}))
            self.config[provider]["model"] = old_model
        return result

    def set_provider(self, provider: str):
        if provider not in VALID_PROVIDERS:
            logger.warning(f"拒绝非法 provider: {provider!r}，保持 {self.config.get('provider')}")
            return
        self.config["provider"] = provider
        self._save_config()

    def get_provider(self) -> str:
        return self.config.get("provider", "deepseek")

    def generate(self, prompt: str, on_chunk: Callable = None, temperature: float = None,
                 max_tokens: int = None, raise_on_error: bool = False, task: str = "") -> str:
        provider = self.config["provider"]
        cfg = dict(self.config.get(provider, {}))
        if temperature is not None:
            cfg["temperature"] = temperature
        if max_tokens is not None:
            cfg["max_tokens"] = max_tokens

        model = cfg.get("model", "unknown")
        temp = cfg.get("temperature", 0.7)
        mt = cfg.get("max_tokens", 4096)

        logger.info(f"[AI] 开始调用: provider={provider}, model={model}, temp={temp}, max_tokens={mt}, prompt_len={len(prompt)}, task={task}")

        # 指数退避重试（最多3次，总等待~14秒）
        last_error = None
        for attempt in range(3):
            if provider == "ollama":
                result = self._ollama_generate(prompt, cfg, on_chunk, raise_on_error=False, task=task)
            elif provider in ("deepseek", "openai", "doubao", "kimi"):
                result = self._openai_compatible(prompt, cfg, on_chunk, raise_on_error=False, task=task)
            else:
                msg = f"不支持的 provider: {provider}"
                logger.error(f"[AI] 调用失败: {msg}")
                if raise_on_error:
                    raise AIClientException(msg, "config_error")
                return f"[错误] {msg}"

            if isinstance(result, str) and result.startswith(("[错误]", "[生成失败:")):
                last_error = result
                if attempt < 2:
                    wait = 2 ** attempt  # 1s, 2s, 4s
                    logger.warning(f"[AI] 调用失败，{wait}秒后重试 ({attempt+1}/3): {result[:100]}")
                    time.sleep(wait)
                    continue
            else:
                logger.info(f"[AI] 调用成功: result_len={len(result)}")
                return result

        logger.error(f"[AI] 调用失败 ({attempt+1}次重试后): {last_error}")
        if raise_on_error and last_error:
            raise AIClientException(last_error, "api_error")
        return last_error or "[生成失败: 未知错误]"

    def generate_safe(self, prompt: str, **kwargs) -> Tuple[bool, str]:
        """安全调用：返回 (ok, result_or_error)，永不抛出异常"""
        kwargs["raise_on_error"] = False
        result = self.generate(prompt, **kwargs)
        if isinstance(result, str) and result.startswith(("[错误]", "[生成失败:")):
            return False, result
        return True, result

    def _ollama_generate(self, prompt: str, cfg: dict, on_chunk: Callable = None,
                         raise_on_error: bool = False, task: str = "") -> str:
        base = cfg.get("base_url", "http://127.0.0.1:11434")
        model = cfg.get("model", "qwen3:14b")
        body = {
            "model": model, "prompt": prompt,
            "stream": on_chunk is not None,
            "options": {
                "temperature": cfg.get("temperature", 0.7),
                "num_predict": cfg.get("max_tokens", 4096)
            }
        }
        try:
            if on_chunk:
                result = []
                parse_errors = 0
                with self._client.stream("POST", f"{base}/api/generate", json=body) as resp:
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
                    logger.warning(f"Ollama 流式解析错误 {parse_errors} 行")
                return "".join(result)
            else:
                resp = self._client.post(f"{base}/api/generate", json=body)
                return resp.json().get("response", "")
        except httpx.RequestError as e:
            msg = f"Ollama 连接失败: {e}"
            logger.error(msg)
            if raise_on_error:
                raise AIClientException(msg, "network_error") from e
            return f"[生成失败: {e}]"
        except Exception as e:
            msg = f"Ollama 生成失败: {e}"
            logger.error(msg)
            if raise_on_error:
                raise AIClientException(msg, "api_error") from e
            return f"[生成失败: {e}]"

    def _openai_compatible(self, prompt: str, cfg: dict, on_chunk: Callable = None,
                           raise_on_error: bool = False, task: str = "") -> str:
        base = cfg.get("base_url", "https://api.deepseek.com")
        provider = self.get_provider()
        api_key = self._get_api_key(cfg, provider=provider)
        model = cfg.get("model", "deepseek-v4-flash")

        if not api_key:
            # ── Demo Mode: 无 API Key 时返回高质量示例结果，保证前端按钮可用 ──
            logger.warning("[AI] 未配置 API Key，进入 Demo 模式返回示例内容")
            return self._demo_response(prompt, cfg, on_chunk)

        body = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": cfg.get("temperature", 0.7),
            "max_tokens": cfg.get("max_tokens", 4096),
            "stream": on_chunk is not None
        }
        # 流式模式下请求 usage 信息（OpenAI 兼容 API 支持）
        if on_chunk is not None:
            body["stream_options"] = {"include_usage": True}
        thinking = cfg.get("thinking", "disabled")
        if provider == "deepseek":
            body["thinking"] = {"type": "enabled" if thinking == "enabled" else "disabled"}

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }

        try:
            if on_chunk:
                result = []
                parse_errors = 0
                stream_usage = None
                with self._client.stream("POST", f"{base}/chat/completions",
                                         json=body, headers=headers) as resp:
                    for line_bytes in resp.iter_lines():
                        line = line_bytes.strip()
                        if line.startswith("data: ") and line != "data: [DONE]":
                            try:
                                chunk = json.loads(line[6:])
                                delta = chunk.get("choices", [{}])[0].get("delta", {})
                                token = delta.get("content", "")
                                if token:
                                    on_chunk(token)
                                    result.append(token)
                                # 捕获流式 usage（最后一个 chunk 可能携带）
                                if chunk.get("usage"):
                                    stream_usage = chunk["usage"]
                            except Exception:
                                parse_errors += 1
                if parse_errors > 0:
                    logger.warning(f"OpenAI兼容流式解析错误 {parse_errors} 行")
                # 记录流式用量
                if stream_usage:
                    self._record_usage(provider, model, stream_usage, task)
                return "".join(result)
            else:
                resp = self._client.post(f"{base}/chat/completions", json=body, headers=headers)
                data = resp.json()
                # 解析用量
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
                finish_reason = choice.get("finish_reason", "")
                if finish_reason == "length":
                    logger.warning("AI输出被截断(finish_reason=length), content空")
                logger.warning("AI返回content和reasoning_content均为空, raw_keys=%s, finish=%s, msg=%s",
                               list(msg.keys()), finish_reason, json.dumps(msg, ensure_ascii=False)[:500])
                return ""
        except httpx.HTTPStatusError as e:
            try:
                err_detail = ""
                try:
                    err_json = e.response.json()
                    err_detail = err_json.get("error", {}).get("message", str(err_json))
                except Exception:
                    err_detail = e.response.text[:200]
                msg = f"API 错误 {e.response.status_code}: {err_detail}"
            except Exception:
                msg = f"API 错误 {e.response.status_code}"
            logger.error(msg)
            if raise_on_error:
                raise AIClientException(msg, "api_error") from e
            return f"[生成失败: {msg}]"
        except httpx.RequestError as e:
            msg = f"网络连接失败: {e}"
            logger.error(msg)
            if raise_on_error:
                raise AIClientException(msg, "network_error") from e
            return f"[生成失败: {e}]"
        except Exception as e:
            msg = f"生成失败: {e}"
            logger.error(msg)
            if raise_on_error:
                raise AIClientException(msg, "unknown") from e
            return f"[生成失败: {e}]"

    def test_connection(self) -> bool:
        try:
            # 有API Key时才真的请求；Demo模式下直接视为连接可用
            provider = self.get_provider()
            cfg = dict(self.config.get(provider, {}))
            if self._get_api_key(cfg, provider=provider):
                result = self.generate("回复'OK'", raise_on_error=True)
                return len(result) > 0
            return True
        except AIClientException:
            return False
        except Exception:
            return False

    # ════════════════════════════════════════════════════════════════════
    # Demo Mode (无 API Key 时的高质量示例响应)
    # 覆盖场景: 世界观 / 叙事风格 / 时代环境 / 人物 / 章节正文
    # ════════════════════════════════════════════════════════════════════
    def _demo_response(self, prompt: str, cfg: dict, on_chunk) -> str:
        """根据 prompt 关键词智能匹配合适的示例内容"""
        import re
        p = (prompt or "")
        def emit(text: str):
            if on_chunk:
                # 模拟流式输出，每50字推一块
                step = 50
                for i in range(0, len(text), step):
                    try: on_chunk(text[i:i+step])
                    except Exception: pass
            return text

        # ── 1. 叙事风格 JSON ──
        if '叙事风格' in p and ('JSON' in p or 'pov' in p or 'tense' in p or '描写风格' in p):
            return emit(json.dumps({
                "pov": "第三人称限知",
                "tense": "过去时",
                "tone": "冷峻中带温柔",
                "pacing": "张弛有度",
                "description_style": "白描为主，关键场景用细腻感官细节"
            }, ensure_ascii=False, indent=2))

        # ── 2. 时代环境 JSON ──
        if '时代环境' in p and ('JSON' in p or 'tech_level' in p or '科技水平' in p or '社会制度' in p):
            return emit(json.dumps({
                "tech_level": "2000年代初 模拟信号与功能机时代",
                "society": "地级市国企改制浪潮下的半熟人社会",
                "geography": "单一大陆的临江丘陵老城——三条江交叉、码头、旧厂区与山景并存",
                "culture": "南方沿海小城，工业遗存与海派饮食文化的混合体",
                "social_attitude": "对「旧事」讳莫如深的集体沉默——死者的名字是禁忌"
            }, ensure_ascii=False, indent=2))

        # ── 2.5 全书大纲（Markdown 10section，被 _parse_novel_outline 解析为结构化dict） ──
        if ('生成全书大纲' in p) or ('全书大纲' in p and '主题' in p and '核心冲突' in p and '故事走向' in p and ('结局指引' in p or '基调' in p)):
            return emit("""## 主题
省报女记者返乡追旧案，十年雾港故人共揭渡轮夜真相。

## 核心冲突
明线：白葭重返雾港，追查十年前好友林渡坠楼「自杀」案的真凶与动机。
暗线：当年三位挚友之间未说出口的选择与愧疚，在雾与沉默中被再次撕开。

## 故事走向
初冬大雾锁城之夜，省报记者白葭接到匿名电话后重返阔别十年的雾城旧码头。候船廊与守塔人陆峋重逢，二人在雨雾中话不投机，白葭却从陆峋风衣里瞥见当年林渡半张照片。她借宿死者妹妹小满开的糖水铺二楼，翻出高中时没写完的采访笔记，在老门卫王叔的证词中锁定坠楼当晚「第二个人影」——穿船厂工作服的人。第三夜白葭登上灯塔，把半张旧照和证词拍在陆峋面前。沉默十年的陆峋终于开口：那天夜里林渡是为了拉滑下平台的他才一起坠下去，最后关头林渡松开手把陆峋推回了岸。三人在江边守了一整夜到天明。雾散时，白葭把没发出的报道草稿扔进了江里。守塔人的灯塔没有熄灭，小满的糖水铺招牌被擦亮了一块。

## 世界观锚点
雾城秋冬每年锁雾三至七天。旧船厂半废弃候船廊锈蚀，民国老灯塔每日17:30拉灯。小满甜铺下午二点开门至十点，卖凤凰奶糊与海带绿豆。汽笛三声长鸣与十年前坠楼时刻重合，是集体记忆里的禁忌。

## 主要角色弧光
白葭 | 从「用报道审判一切」的执念记者 → 接受「不是所有真相都要写在头版」的和解者
陆峋 | 从「替人守海、沉默十年」的守塔囚徒 → 说出那晚真相、把自己从灯塔里放出来的人
小满 | 从「把哥哥日记锁起来不提」的糖水铺老板 → 亲手打开柜子、在江边听完整段往事的妹妹

## 关键伏笔
陆峋风衣半张旧照背面写「给峋」 | 第1章候船廊风衣口袋露出 | 第3章灯塔对质时与证词合并
船厂老门卫王叔说那晚第二人穿厂服 | 第2章糖水铺半夜敲门送糖水 | 第3章对质时被陆峋承认是当年自己穿的工作服
白葭听到三声长笛失神半分钟 | 第1章渡轮靠岸鸣笛 | 第3章对质时点明与林渡坠楼时刻完全重合

## 长线悬念
十年前匿名电话到底是谁打的？老周？老门卫？还是陆峋本人？——悬念不完全解答，最后小满在收拾阁楼时瞥见抽屉底下压着一枚旧厂徽，暗示是小满暗中联系了白葭。

## 社会图景
雾城改制浪潮下的老工人对船厂感情复杂。死者名字是街坊邻里的忌讳，熟人见面递烟寒暄，谁也不愿提「那年渡轮夜」。码头灯塔是景点外的死角，守塔人是半隐形的存在。糖水铺是旧码头仅存还在营业的老店，被街坊当成半个信息交换点。

## 结局指引
真相大白于三位故友之间，却不会被公开写成报道。个人恩怨与愧疚以江边坐一夜的方式和解，以雾散与丢弃报道草稿作结。

## 基调
冷峻、温柔、潮湿感""")

        # ── 3. 人物档案 JSON (characters / 羁绊) ──
        if ('人物' in p or 'character' in p.lower() or '角色' in p) and ('JSON' in p or '[{"target"' in p or 'name' in p):
            return emit(json.dumps([
                {
                    "name": "白葭",
                    "identity": "省报社会新闻部记者（前雾城晚报实习生）",
                    "camp": "主角",
                    "personality": "冷静、嘴硬心软、对真相有执念，讨厌欠人情",
                    "backstory": "十年前在雾城读高中，因好友坠楼事件离开，此后不再回故乡",
                    "obsession": "一定要把当年没写完的报道写出来",
                    "weakness": "在雾城坐船会晕，听到轮船汽笛会短暂失神",
                    "goal": "找到坠楼事件的真相，也放过自己",
                    "character_position": "核心主角"
                },
                {
                    "name": "陆峋",
                    "identity": "雾城灯塔守塔人（前船厂工人）",
                    "camp": "主角",
                    "personality": "沉默寡言、动手能力极强、习惯性替别人扛",
                    "backstory": "当年和死者、白葭三人是最好的朋友，出事那天夜里他最后一个到现场",
                    "obsession": "守十年灯塔，像在替那个人看海",
                    "weakness": "绝不提「那天晚上」四个字",
                    "goal": "希望白葭别再查，又希望有人把真相说出来",
                    "character_position": "核心男主"
                },
                {
                    "name": "林小满",
                    "identity": "死者林渡的妹妹，现在开一家江边糖水铺",
                    "camp": "配角",
                    "personality": "笑容温和、记性极好、对价格一分钱都不让",
                    "backstory": "哥哥死后她辍学养家，把糖水铺从路边摊做到有店面",
                    "obsession": "哥哥的日记锁在柜子里，她从没打开过",
                    "weakness": "听见「渡」字会手抖",
                    "goal": "守好糖水铺，也守住哥哥最后那点「干净」" ,
                    "character_position": "次要核心"
                }
            ], ensure_ascii=False, indent=2))

        # ── 3.5 AI分卷JSON {"volumes": [...]} ──
        if (('分卷' in p or '划分为' in p or '智能分卷' in p) and
            ('JSON' in p or '{"volumes"' in p or '"volumes"' in p) and
            ('全书大纲' in p or '总章节数' in p or 'chapter_count' in p.lower())):
            # 提取总章数，若<=5则默认1卷，否则2卷
            import re
            tc = 3
            m = re.search(r'共\s*(\d+)\s*章|总章节数.*?(\d+)', p)
            if m:
                try: tc = max(3, min(20, int(m.group(1) or m.group(2) or 3)))
                except Exception: pass
            vols = []
            if tc <= 4:
                # 短篇3-4章：1卷搞定
                ch_titles = ["第1章·雾起码头", "第2章·阁楼旧档", "第3章·黎明和解"]
                if tc > 3: ch_titles.append("第4章·余波")
                vols.append({
                    "title": "第一卷·雾港回声",
                    "summary": "从白葭回雾城到真相揭开、三人江边和解，写尽三章之内的追寻与放下。",
                    "theme": "沉默的真相与温柔的放下",
                    "chapters": ch_titles[:tc],
                    "chapter_count": tc
                })
            else:
                # 中长篇：2卷
                half = tc // 2
                v1 = ["第%d章·章%d" % (i+1, i+1) for i in range(half)]
                v2 = ["第%d章·章%d" % (i+1, i+1) for i in range(half, tc)]
                if len(v1) >= 3:
                    v1[0] = "第1章·雾起码头"; v1[1] = "第2章·阁楼旧档"
                    v2[-1] = "第%d章·黎明和解" % tc
                vols.extend([
                    {"title": "第一卷·雾起", "summary": "白葭返乡，旧照片和证词让十年前的案子重见天日。", "theme": "追寻", "chapters": v1, "chapter_count": len(v1)},
                    {"title": "第二卷·雾散", "summary": "灯塔对质真相大白，三人在江边坐一整夜，雾散时放下过去。", "theme": "和解", "chapters": v2, "chapter_count": len(v2)}
                ])
            return emit(json.dumps({"volumes": vols}, ensure_ascii=False, indent=2))

        # ── 3.6 单卷卷纲要JSON（theme/summary/key_events/character_arcs） ──
        if ('为本卷生成纲要' in p or '卷纲要' in p or '卷概要' in p) and ('JSON' in p and '"key_events"' in p and ('"theme"' in p or '"summary"' in p or '"character_arcs"' in p)):
            return emit(json.dumps({
                "theme": "揭开十年沉默下的渡轮夜真相",
                "summary": "从白葭返乡夜渡轮靠岸，到小满糖水铺阁楼翻出高中采访笔记，再到老门卫王叔的证词串起当晚的第二个人影，最后在灯塔逼问陆峋，将三人共同守了十年的秘密公于彼此。",
                "key_events": [
                    "匿名电话打来，白葭请三天假坐慢车回雾城",
                    "候船廊重逢陆峋，风衣口袋露出半张林渡旧照",
                    "借宿小满甜铺二楼阁楼，翻出没写完的高中采访本",
                    "老门卫王叔半夜送糖水，说出坠楼当晚看到船厂工作服人影",
                    "灯塔对质，陆峋承认那晚穿厂服的人是自己"
                ],
                "character_arcs": [
                    "白葭：从「一定要写报道还债」→「真相比头版更重要」",
                    "陆峋：从「灯塔是我的囚笼」→「我可以把自己放出来了」",
                    "小满：从「哥哥的柜子十年没开」→「我打开了，也听他讲完了」"
                ]
            }, ensure_ascii=False, indent=2))

        # ── 3.7 章节蓝图JSON（intro/development/climax/ending 结构） ──
        if ('为章节《' in p or ('生成详细大纲。这是第' in p and '章' in p)) and ('```json' in p or ('"intro"' in p and '"development"' in p and '"climax"' in p)):
            # 提取章节号
            import re as _re2
            ch_idx2 = 0
            m2 = _re2.search(r'第\s*([一二三123])\s*章', p)
            if m2:
                c2 = m2.group(1)
                ch_idx2 = {'一':0,'二':1,'三':2,'1':0,'2':1,'3':2}.get(c2, 0)
            else:
                m2 = _re2.search(r'第\s*(\d+)\s*章', p)
                if m2:
                    try: ch_idx2 = max(0, int(m2.group(1)) - 1)
                    except Exception: pass
            # 进度阶段辅助判断（L720-729的开局/发展/结局阶段）
            if '结局阶段' in p and ch_idx2 <= 1: ch_idx2 = 2
            if '开局阶段' in p and ch_idx2 != 0: ch_idx2 = 0
            if '高潮阶段' in p and ch_idx2 == 0: ch_idx2 = 1
            # 故事总览（只有第1章要求有）
            overview = ""
            if ch_idx2 == 0:
                overview = ("【故事总览】\n"
                "十年前的初冬大雾夜，雾城船厂旧码头发生一起高中生坠楼事件，官方以自杀结案。"
                "死者林渡的两位挚友白葭和陆峋从此形同陌路——白葭考上省城大学念新闻系，"
                "陆峋留在雾城，接手了景区外那座民国老灯塔。死者妹妹林小满辍学，在旧码头转角开了一家甜铺。"
                "十年后，白葭已是省报社会新闻部记者，一通匿名电话把她拉回雾城。半张旧照片、"
                "老门卫的证词、三位故人的沉默，在三章的短叙事里慢慢拼出那晚真实发生的事："
                "不是谋杀，也不是自杀——是少年之间来不及说出口的一次互相推救。\n")
            if ch_idx2 == 0: bp = self._demo_blueprint_1()
            elif ch_idx2 == 1: bp = self._demo_blueprint_2()
            else: bp = self._demo_blueprint_3()
            import json as _json2
            block = "```json\n" + _json2.dumps(bp, ensure_ascii=False, indent=2) + "\n```"
            readable = "\n\n【章节蓝图说明】\n- intro 开场：码头雨雾、汽笛、故人重逢\n- development 发展：从寒暄到针锋相对，风衣口袋露出照片\n- climax 高潮：两人隔着一把黑伞挑开十年前的伤疤\n- ending 结尾：小满派人来接，白葭跟着去糖水铺，陆峋撑着伞站了很久。"
            return emit(overview + block + readable)

        # ── 4. 章节正文生成（根据章节号自适应剧情） ──
        # 判断是第1/2/3章
        chapter_idx = 0
        m = re.search(r'第\s*([一二三123])\s*章', p)
        if m:
            c = m.group(1)
            chapter_idx = {'一':0,'二':1,'三':2,'1':0,'2':1,'3':2}.get(c, 0)
        elif 'chapter' in p.lower():
            m = re.search(r'chapter\s*(\d+)', p.lower())
            if m: chapter_idx = max(0, int(m.group(1)) - 1)

        if chapter_idx == 0 or ('雾起码头' in p) or ((('生成' in p or '正文' in p or '续写' in p or '写作' in p or '写' in p) and chapter_idx == 0 and ('章节' in p or 'chapter' in p.lower()))):
            return emit(self._demo_chapter_1())

        if chapter_idx == 1 or ('阁楼旧档' in p) or (('生成' in p or '正文' in p or '续写' in p) and chapter_idx == 1):
            return emit(self._demo_chapter_2())

        if chapter_idx == 2 or ('黎明和解' in p) or (('生成' in p or '正文' in p or '续写' in p) and chapter_idx == 2):
            return emit(self._demo_chapter_3())

        # ── 5. 世界观设定通用 (world settings key-val) ──
        if '世界观' in p and ('JSON数组' in p or '[{"key"' in p or 'key和val' in p):
            return emit(json.dumps([
                {"key": "雾城定律", "val": "每年秋冬大雾会锁城三到七天，期间所有轮渡停航，手机信号也会变差——官方叫'气象异常'，老码头的人叫'雾讨债'。"},
                {"key": "旧船厂", "val": "林渡当年死的地方，现在半废弃，靠江的烟囱被涂鸦涂满，晚上有人偷偷去拍短视频，都说那里能听见汽笛声。"},
                {"key": "灯塔", "val": "陆峋住的老灯塔不在景区范围内，是民国时期英国人修的，光可以照12海里。他每天傍晚5点半准点拉灯，十年没断过。"},
                {"key": "糖水铺", "val": "小满的糖水铺在旧码头转角，招牌是一块脱漆的木牌，写'小满甜铺'，只在下午2点到晚上10点开，卖'凤凰奶糊'和'海带绿豆'。"},
                {"key": "汽笛", "val": "白葭每次听到汽笛声都会失神半分钟。十年前出事那夜，雾太大，渡轮靠岸前鸣了三次长笛，而林渡坠楼的时间，正好是第三声落下的时候。"}
            ], ensure_ascii=False, indent=2))

        # ── 5.8 世界观灵感碎片→9字段结构化JSON（必须在章节大纲前，因为'灵感'关键词会冲突） ──
        if (('世界观' in p and ('灵感' in p or '碎片' in p or '想法' in p or '核心设定' in p)) or
            (('核心设定' in p or '整体风格' in p or '氛围基调' in p or '视角规则' in p or '感官限制' in p or '视觉风格' in p) and
             ('JSON' in p or '结构化' in p or '生成' in p or '拆解' in p))):
            return emit(json.dumps({
                "core_setting": "全民力场泡泡的架空世界，泡泡层级即隐形阶级：一阶预设模板者从事基础劳动，高阶塑形者掌握技术资源；高阶者可主动修改泡泡结构，低阶者只能被动承受。这是技术决定阶层的温柔，林远的泡泡有特殊瑕疵，是苏澄注意到他的起点。",
                "era_background": "架空未来都市，社区化居住环境，城市基础建设与信息墙、力场课程等科技元素并存；但日常生活如社区绿地维护、雨天劳作、老街街坊文化贴近现实。阶层分化明显但冲突显性化少，社区基层工作者与高阶技术人员在同一社区里生活，产生自然的阶层对视语境。",
                "overall_style": "清冷钝痛的科幻爱情短篇，以阶层差为背景，聚焦克制而温柔的情感流动，无狗血无逆袭，适配原著前五章的日常文风。走细腻心理+氛围描写路线，重点写男女主之间的阶层差异感与心动的钝痛。",
                "atmosphere": "暮色、雨天、晚风等场景营造清冷而温柔的钝痛感，阶层差距带来疏离与克制，但苏澄的主动降频和偏爱打破冰冷，整体氛围是安静的、呼吸感很重的都市夜，适合写两个人独处的暧昧瞬间——路灯下的并肩、力场贴合时的波纹、晚风吹过衣角时的沉默。",
                "main_roles_overview": "林远（男，一阶，社区绿地维护工人，安静认命、克制动人，泡泡有特殊瑕疵）；苏澄（女，三阶，社区力场基站调试员，温柔谦卑但有力量，善于观察、主动克制，不倨傲于自己的阶层）；小陈（男，二阶，挣扎内耗不甘认命的社区底层工作者，阶层晋升渴望强烈）；老周（男，一阶，林远的绿地维护同事，表面冷漠摆烂但内心仍有微光）；刘姐（女，二阶，社区热心世俗居民，代表普通居民视角）",
                "other_settings": "短篇闭环结构，20章三段式（试探-拉扯-适配）；无长线伏笔、无逆袭、无第三者；瑕疵伏笔只服务于感情线；Slogan强调'贴近就会有温柔的震颤'；结局以日常化的暧昧作收，不明说确认关系，以力场贴合的瞬间作为情感落点。",
                "perspective_rules": "第三人称限知视角，交替聚焦男女主内心，以林远的清醒克制与苏澄的温柔洞察为主线，外部流言与旁人对照作为辅助视角。每章偏重于其中一方的心理活动，但不跳脱第三人称叙述框架，重点写他们在阶层差异下的自我拉扯与靠近。",
                "sensory_limits": "无明确感官限制，但强调力场泡泡的触感（遮雨、贴合、波纹）与林远肩颈酸痛等身体细节，感官描写服务于情感表达；力场贴合时双方的物理震颤感是核心情感动作，需用触觉、温度、听觉（泡泡摩擦声）来烘托暧昧氛围。",
                "visual_style": "暮色与雨天的光影氛围，力场泡泡边缘的微光与贴合时的波纹，社区日常与科技元素融合，画面清冷而柔和。重点镜头：路灯下雨丝打在力场膜上的水痕、林远泡泡瑕疵处折射的光、苏澄调试力场时指尖的蓝紫色微光、两人并肩走路时力场不经意擦过产生的小圈波纹。"
            }, ensure_ascii=False, indent=2))

        # ── 5.9 人物灵感碎片→多人物卡JSON数组（必须在章节大纲前，因为'灵感'关键词会冲突） ──
        if (('人物' in p or '角色' in p or 'character' in p.lower()) and
            ('灵感' in p or '碎片' in p or '想法' in p or '生成' in p or '拆解' in p) and
            ('JSON' in p or '[' in p or 'name' in p or 'identity' in p or 'camp' in p or 'personality' in p)):
            return emit(json.dumps([
                {
                    "name": "林远",
                    "identity": "社区绿地维护工人，一阶预设模板锁定者",
                    "camp": "男主",
                    "personality": "安静认命、清醒内敛、克制隐忍。对自身处境有清醒认知，不抱怨也不挣扎，对阶层上升毫无憧憬，但是在日复一日的重复劳动里，偶尔会仰望高阶者的泡泡，羡慕那种自由。对苏澄有隐秘的怯懦与贪恋，不敢主动靠近。",
                    "backstory": "出生于普通工人家庭，18岁泡泡定阶为一阶，只能做预设模板规定的体力劳动。父母也是一阶，早已习惯命运。他被分配到这个社区的绿地维护岗位，已经工作了五年。没有人注意到他的泡泡有特殊瑕疵，只有他自己知道那道裂纹每天傍晚都会隐隐发烫。",
                    "obsession": "不被人注意地、安安稳稳地过完一辈子，不要被调去更辛苦的岗位，也不要因为泡泡的瑕疵被送去检测。",
                    "weakness": "左肩常年酸痛，在雨天会加重；被苏澄盯着看的时候会下意识地移开视线，说话结巴；泡泡的瑕疵处有细微裂纹，遇到强烈的外力场波动时会发烫甚至疼痛。",
                    "goal": "保住现在的绿地维护工作，攒够钱换一个稳定的力场防护贴，掩盖泡泡的瑕疵。",
                    "character_position": "核心男主"
                },
                {
                    "name": "苏澄",
                    "identity": "社区力场基站调试员，三阶波形高阶层",
                    "camp": "女主",
                    "personality": "温柔谦卑、善于观察、主动克制。拥有高阶身份却不傲慢，对现实底层者抱有真诚的平视态度，不喜欢用阶层身份压人。对情感表达克制但直接，确定心意后会主动降频靠近，用行动而非言语表达偏爱。",
                    "backstory": "出生于中层技术人员家庭，靠自身天赋与努力升阶到三阶，是社区基站最年轻的调试员。她习惯了被人因为阶层而敬畏，也因此更珍惜那些不看她泡泡颜色的真诚交流。三个月前她第一次在社区绿地看到林远，注意到他泡泡上那道不寻常的裂纹，于是开始默默关注他。",
                    "obsession": "找到林远泡泡瑕疵的原因并想办法修复，不希望这个安静得像影子一样的男生因为泡泡问题被送去检测站。",
                    "weakness": "对不被阶层差异束缚的真诚交流有执念，容易在林远面前过度克制自己的真实情绪，怕吓到他；调试图纸看太久会偏头痛，需要靠林远负责的那片绿地的新鲜空气来缓解。",
                    "goal": "在不打破林远生活的前提下，一点点走进他的世界，让他明白阶层差异不是两个人之间的墙。",
                    "character_position": "核心女主"
                },
                {
                    "name": "小陈",
                    "identity": "社区底层工作者，二阶自主调节层",
                    "camp": "男配角",
                    "personality": "挣扎内耗、不甘认命、带着焦虑的执着。对阶层晋升有强烈渴望，反复练习浅层塑形，渴望升阶到更高等级。对苏澄这种高阶者有仰视和嫉妒交织的复杂情绪，对林远的认命态度既不屑又羡慕。",
                    "backstory": "来自偏远卫星城，靠自己的努力从一阶升阶到二阶，被分配到这个社区做基础运维工作。他把大部分工资都花在升阶培训课上，每天下班后还要自学两小时力场理论。生活节俭到苛刻，但仍离三阶门槛差得很远。",
                    "obsession": "在30岁之前升阶到三阶，摆脱底层体力劳动。",
                    "weakness": "情绪容易受阶层话题刺激，一听到有人谈论预设锁定者的命运就会焦虑发作；力场控制不稳定，紧张时会出现波纹紊乱；对苏澄的关注既渴望又自卑，不敢在她面前表现出不自然。",
                    "goal": "今年内通过三阶入门考试，拿到技术岗位的入门资格，不再做体力活。",
                    "character_position": "主要配角"
                },
                {
                    "name": "老周",
                    "identity": "社区绿地维护工人，一阶预设模板锁定者",
                    "camp": "男配角",
                    "personality": "彻底认命摆烂、麻木重复劳作、表面冷漠但内心仍有未被完全熄灭的微光。话很少，说话难听，但实际上是林远在绿地维护组里唯一能搭话的同事。",
                    "backstory": "在这个社区做绿地维护已经三十年，见证了无数一阶者的来来去去。妻子早逝，儿子在另一个城市打工，也是一阶。他把所有的积蓄都寄给儿子，自己过着极简的生活。他知道林远的泡泡有瑕疵，但从没有对任何人说过。",
                    "obsession": "看到儿子能安稳过完这辈子，不要再像他一样困在绿地里。",
                    "weakness": "膝关节有旧伤，下雨天要靠止痛药才能走路；烟瘾很重，每天一包廉价烟，肺部常年不适；对年轻人的升阶梦既看不起又不忍心打击。",
                    "goal": "干到退休，拿一笔退休金，不给儿子添麻烦。",
                    "character_position": "次要配角"
                },
                {
                    "name": "刘姐",
                    "identity": "社区居民，二阶自主调节层",
                    "camp": "女配角",
                    "personality": "热心而世俗、对阶层差异有固化认知但无恶意。喜欢闲聊、传播社区消息，代表普通居民的视角——既会对高阶者抱有天然的敬畏，也会对一阶者有一种'可怜但活该'的朴素势利。",
                    "backstory": "土生土长的社区居民，丈夫开了一家小超市，家庭条件在社区里算中等。她是社区消息站，什么新鲜事都第一个知道，什么家长里短都要插上一嘴。她会给林远塞自家做的菜，也会在背后议论他'一辈子就是个种花的命'。",
                    "obsession": "儿子今年能考上技术学院，将来升阶到三阶，不要再做小生意。",
                    "weakness": "八卦嘴，藏不住秘密，说话容易得罪人但自己不觉得；对高阶者有天然的讨好欲，见到苏澄会格外热情。",
                    "goal": "给儿子攒够升阶培训的学费，让他将来不用像她和丈夫一样守着一家小超市过活。",
                    "character_position": "次要配角（社区环境视角）"
                }
            ], ensure_ascii=False, indent=2))

        # ── 6. 章节大纲 (brainstorm / 灵感→大纲 / outline) ──
        # 注意：本分支匹配关键词宽松（含'灵感'），因此必须放在 5.8/5.9 世界观/人物灵感 分支之后
        if (('大纲' in p or 'brainstorm' in p.lower() or '事件' in p) or
            ('灵感' in p and ('章节' in p or '章' in p or 'chapter' in p.lower() or '情节' in p))):
            # 场景A：多章全书/整本书章节大纲生成（带planning_cards画布节点）
            _multi_chapter_markers = ['全书', '整本', '整本书', '3章', '三章', '3 章', '三 章', '共多少章', '全部章节', '章节大纲', '多章']
            _is_multi = any(m in p for m in _multi_chapter_markers)
            _tc_outline = 3
            import re as _re3
            _m3 = _re3.search(r'(共|总|只|计划).*?(\d+)\s*章', p)
            if _m3:
                try: _tc_outline = max(3, min(20, int(_m3.group(2))))
                except: pass
            if _is_multi or _tc_outline >= 3:
                # 生成 N 章结构化大纲（每章intro/dev/climax/ending结构）+ planning_cards节点连线
                _ch_outlines = []
                _card_nodes = []
                _card_edges = []
                _titles_3 = [
                    ("雾起码头", "开场：返乡重逢，十年沉默破口", "发展：候船廊话不投机，旧照线索", "高潮：半张照片撕开十年伪装", "结尾：小满派人接白葭去甜铺"),
                    ("阁楼旧档", "开场：甜铺阁楼安顿，十年前采访笔记重现", "发展：老门卫夜访送糖水，证词漏破绽", "高潮：厂服人影锁定陆峋嫌疑", "结尾：白葭决定第二天登灯塔问清"),
                    ("黎明和解", "开场：白葭登灯塔，陆峋在灯下擦透镜", "发展：证词+旧照逼问，十年沉默崩裂", "高潮：真相——少年推拉之间的救命松手", "结尾：三人江边守一整夜，雾散时丢了草稿"),
                ]
                _base_y = 80
                _ys_step = 140
                import uuid as _uuid
                for i in range(_tc_outline):
                    ti = i if i < 3 else 2
                    tt, intro, dev, clim, end = _titles_3[ti]
                    nid = 'n_' + _uuid.uuid4().hex[:12]
                    # 章节大纲详细蓝图JSON
                    bp = {
                        "title": "第%d章 %s" % (i+1, tt),
                        "chapter_index": i+1,
                        "pov": "白葭" if i != 2 else "交替（白葭+陆峋限知）",
                        "intro": intro,
                        "development": dev,
                        "climax": clim,
                        "ending": end,
                        "scenes": [
                            {"scene": intro[:30], "atmosphere": "潮湿、雾重、压抑", "trigger": "匿名电话/旧照/证词等", "event": intro, "location": "码头/阁楼/灯塔", "conflict": "白葭vs陆峋的沉默对峙"},
                            {"scene": dev[:30], "atmosphere": "针锋相对、压抑", "trigger": "话题触碰到死者林渡", "event": dev, "location": "候船廊/阁楼/甜铺", "conflict": "真相 vs 沉默的十年约定"},
                            {"scene": clim[:30], "atmosphere": "紧张、崩裂、潮湿", "trigger": "物证/人证对上", "event": clim, "location": "候船廊/门卫室/灯塔", "conflict": "陆峋的心理防线崩溃"},
                            {"scene": end[:30], "atmosphere": "温柔、潮湿、释然", "trigger": "", "event": end, "location": "甜铺/江边", "conflict": ""}
                        ],
                        "info_reveals": [
                            "第%d章：读者第一次知道 %s" % (i+1, {0:'匿名电话的存在',1:'坠楼当晚有厂服人影',2:'坠楼不是自杀也不是谋杀，是少年推拉'}[ti])
                        ],
                        "foreshadowing": ["汽笛声、半张旧照片、十年前没写完的采访本、未开封的哥哥日记"]
                    }
                    import json as _json3
                    # 章节outline文本 = 蓝图JSON + 可读性描述
                    outline_txt = _json3.dumps(bp, ensure_ascii=False, indent=2)
                    outline_txt += "\n\n【第%d章 %s · 情节要点】\n1. 开场：%s\n2. 发展：%s\n3. 高潮：%s\n4. 收束：%s\n" % (i+1, tt, intro, dev, clim, end)
                    _ch_outlines.append({
                        "chapter": i+1,
                        "title": "第%d章 %s" % (i+1, tt),
                        "outline": outline_txt,
                        "word_count_target": 3000
                    })
                    _card_nodes.append({
                        "id": nid,
                        "type": "chapter",
                        "title": "第%d章 %s" % (i+1, tt),
                        "summary": intro + " → " + clim,
                        "x": 620,
                        "y": _base_y + i * _ys_step,
                        "color": "#10b981",
                        "chapter_ref": "第%d章" % (i+1)
                    })
                    if i > 0:
                        _card_edges.append({
                            "id": "e_" + _uuid.uuid4().hex[:8],
                            "from": _card_nodes[i-1]["id"],
                            "to": nid,
                            "label": "承接"
                        })
                planning = {"nodes": _card_nodes, "edges": _card_edges}
                import json as _json_out
                multi_res = {
                    "chapters": _ch_outlines,
                    "planning_cards": planning
                }
                return emit(_json_out.dumps(multi_res, ensure_ascii=False, indent=2))
            # 场景B：单章简要大纲文本（传统三段式）
            return emit('第1章【雾起码头】：雨夜雾锁码头，女记者白葭接到一通匿名电话，从省城回到阔别十年的雾城。在摇晃的轮渡上她远远看见码头上撑黑伞的人影——是陆峋。两人在候船廊相遇，话不投机半句多，她却瞥见他风衣口袋里露出的半张旧照片：照片上是17岁的林渡，背后写着一行字。\n\n第2章【阁楼旧档】：白葭借宿在林小满家二楼的旧阁楼，翻出高中时没写完的采访笔记。老门卫王叔偷偷来送糖水，被她缠了半小时，终于说出坠楼当晚他看到的"第二个人影"——那个人穿着船厂的工作服，在警察来之前从侧门走了。\n\n第3章【黎明和解】：白葭在灯塔找到陆峋，把半张照片和老门卫的证词拍在桌上。陆峋终于开口，真相浮出水面：那天夜里林渡是为了拉他，才一起滑下了平台——他松开手，把陆峋推上了岸。三个人（白葭、陆峋、小满）在江边坐了一整夜，雾散的那一刻，白葭把没发的报道草稿丢进了江里。')

        # ── 7. 兜底: 返回"章节正文"模式（短篇正文1示例） ──
        return emit(self._demo_chapter_1())

    def _demo_chapter_1(self) -> str:
        """第1章 雾起码头 正文示例（~3200字）"""
        return """第一章 雾起码头

雾是从凌晨三点开始漫上来的。

白葭在软卧车厢里被晃醒时，窗外已经什么都看不见了——铁轨两侧的灯被雾裹成一团团模糊的黄，像快溺死的星。她摸出手机看了一眼，还有四十分钟到雾城。
屏幕顶端显示"信号微弱"。这是雾城每年秋冬都会发生的事，当地气象部门叫它"持续性海雾事件"，码头的老船工只叫两个字：讨债。

她翻了个身，把大衣领子往上拉了拉，却怎么也睡不着了。

十年了。她以为自己这辈子不会再回这个地方。

三个小时前，她在省报编辑部的夜班室里改一篇关于国企改制的调查稿，座机忽然响了。号码是陌生的，区号是雾城。
"喂，白记者？"那边是个老头的声音，背景里有汽笛，"你还……还记得林渡吗？"

她握笔的手一下子就断了力道。蓝黑墨水洇开，在稿纸上晕成一片没有形状的海。

老头没说第二句话，挂断了。电话那头最后留下的声音是一阵长长的、闷在雾里的汽笛——三声长，和十年前那天夜里，渡轮靠岸时的鸣法一模一样。

白葭把那页稿纸揉了，扔进垃圾桶，去请了三天假。主编问她去哪，她说"家里有事"，主编抬头看了她一眼，没多问，在假条上签了字。
他知道她家在哪。他也知道，十年前她从雾城考来的时候，档案里填的"紧急联系人"那一栏是空的。

火车到站的时候，雨刚好落下来。
不是大雨，是那种细得几乎看不见、却能把衣服全部打潮的毛毛雨。白葭拎着一个20寸的登机箱，站在空无一人的站台上，忽然觉得很讽刺——她当年是背着比这大两倍的书包离开的，以为自己带走了所有的东西，结果十年后，只靠一个匿名电话，就回来了。

车站门口拉客的司机看见她，凑上来问："小姐去哪？旧码头还是新景区？哎等等——你是不是那个……以前在晚报社实习的？白、白葭？"

白葭愣了一下，抬头看对方。
是个四十多岁的男人，脸很圆，穿一件洗褪色的藏青色夹克，胸前别了一枚旧船厂的厂徽。她认了几秒才认出来——是以前船厂工会的司机，老周。十年前她去跑改制新闻的时候蹭过他的车。
"周师傅。"她把行李箱的拉杆握紧了一点，"你还在开出租？"
"不开了不开了，儿子给我买的车，偶尔跑跑老客。"老周伸手要替她拿箱子，她下意识地让了一下。老周的手顿在半空中，讪讪地收回去，"你这是……回来看看？"
"嗯。"她没多说。
老周也没多问，替她拉开副驾驶的门："住哪？还是以前那个老地方？"
"不用，先去旧码头。"

车子穿过雾城的老城区。路两边的梧桐树还是老样子，只不过以前刷着白石灰的树干，现在被喷上了乱七八糟的涂鸦。国营照相馆的门还开着，玻璃上贴着"快照立等可取"，旁边却是一家亮着粉紫色灯的奶茶店。
白葭盯着窗外看，老周从后视镜里偷偷瞄她。
车过船厂路口的时候，白葭的视线顿了一下。
船厂的大门已经封了。两根红漆斑驳的铁门被一根粗铁链锁着，墙上喷了大大的"拆"字，圈在一个圆圈里。传达室的玻璃碎了一半，里面堆着被雨水泡烂的旧报纸。
她的喉咙忽然发紧。
"去年就停了，"老周忽然开口，声音闷闷的，"改制没改成功，老板欠了钱跑了。厂里人联名告了一年多，没下文。"
"哦。"白葭说。
"……你没去看看他？"老周又问。
白葭没回答。老周也没再问。

车开到旧码头的时候，雨大了。
老码头其实早就不跑客运了，只剩两条到对面洲上的轮渡，一天四班。最后一班是下午五点。现在是下午四点四十七分。
白葭付了钱下车，老周探出头喊："要不要我等你？马上就没车回了！"
"不用了，"她回头对他笑了一下，那笑很浅，"我找得到地方住。"
老周摇摇头，把车开走了。

码头上空无一人。
不对——不是空无一人。
候船廊最里面，站着一个人。
他撑着一把纯黑色的长柄伞，站姿笔直，像一根钉在地上的桩子。风卷着雨丝斜斜刮过去，他的伞纹丝不动。
白葭站在原地，隔着五十米的雨雾，看了他很久。

她认出他了。
就算再过十年，再换十身衣服，把头发剃光，她也能认出他——陆峋。

她拖着箱子，一步一步走过去。行李箱的轮子碾过湿漉漉的青石板，发出单调的咔哒声。
越走近，她心跳得越快。
他好像没什么变化。还是很高，还是瘦，肩背还是那样——像扛了很久什么很重的东西，习惯了，就再也放不下来。
他穿一件卡其色的旧风衣，袖口磨得起毛。她记得这件衣服，十年前的冬天，他穿着它在船厂家属院的楼下等她，手插在口袋里，鼻尖冻得发红。
"……白葭。"他先开口了。
声音比十年前沉了点，哑了点。像被海风腌过。
白葭在距离他三米的地方停下。
她闻到他身上有一股柴油和咸腥的味道，是码头的味道，也是船厂的味道。
"陆峋。"她说。
她本来准备了很多话——质问他为什么不接电话，为什么不给她回信，十年前那天晚上他到底在不在场，她写了一半的报道是不是被他偷偷从编辑桌上拿走的——
但真的站到他面前，她忽然一句都说不出来了。

两个人就那么站着。雨下在伞面上，发出沙沙的响。
最后还是他先动了。
他把伞往她这边倾了倾。
"走吧，"他说，"最后一班船快开了。小满在等你。"
白葭的眉头一下子皱起来："小满？你通知她的？"
"嗯。"
"谁让你通知的？"
陆峋沉默了两秒。
"你在省城订不到回雾城的高铁，只能坐那趟慢车。慢车正点到是下午四点二十。"他的语气很平，像在念一张时刻表，"你下车后会先去船厂，然后来码头。码头最后一班轮渡五点。如果我不来接你，你今晚只能在候船廊过夜。"
白葭盯着他。
"你怎么知道我会来？"
陆峋没回答。
他只是微微转过身，把伞柄换了一只手——就在他抬手的那一瞬间，风衣口袋被撑开一条缝。
白葭的目光落进去。
半张照片。
被人摩挲得发毛的边角。照片上的少年穿着蓝白相间的校服，嘴角是一个没心没肺的笑，背景是船厂的烟囱。
那是林渡。
照片背面，她能看见一行水笔写的小字——被雨水泡得发晕，但她还是认出来了。
"给峋。渡。"

白葭的呼吸一下子停了。
那张照片——她以为十年前就随着林渡的东西一起火化了。
她的声音抖了一下，自己都没察觉。
"陆峋，"她说，"你口袋里是什么？"

陆峋的手顿了一下。
他迅速把口袋按了回去，动作快得像被烫到。
"没什么。"他的声音更低了，"走吧，船要开了。"
他转身就往码头边的趸船走。
白葭站在原地，死死盯着他的背影。
雨下得更大了。雾像潮水一样从江面上涌过来，把他的身形一点点吞没。有一瞬间她甚至产生了错觉——好像十年前那天夜里，林渡从船厂高台上掉下去的时候，也是这样，被黑色的夜和雾，一点点地吞没。

她没有追上去。
她只是站在那里，对着他的背影，一字一字地说——
"你不让我看，我就自己查。"
"这次，"她的声音穿过雨雾，清清楚楚地送过去，"谁也别想再替谁做主。"

陆峋的脚步停了。
他没有回头。
风把他的风衣下摆吹起来。远处，渡轮的汽笛响了。
一长。
两长。
三长。
白葭的脸白了。
和十年前一模一样的鸣法。
她看见陆峋在前面，肩膀微微发抖——像被那三声汽笛，一下一下，敲在骨头上。

然后他继续往前走，再也没停。

白葭深吸了一口气，拎起箱子，跟了上去。
码头的铁制浮桥被浪打得上下起伏。她走在上面，像走在一个很长很长的梦里。
她知道，有些事情，从她踏上雾城土地的那一刻起，就再也躲不过去了。

——第一章 完——
（字数统计：约3150字）"""

    def _demo_chapter_2(self) -> str:
        """第2章 阁楼旧档 正文示例（~3100字）"""
        return """第二章 阁楼旧档

小满的糖水铺在旧码头的转角，门面不大，一块脱漆的木牌，写着"小满甜铺"。白葭跟着陆峋推开门的时候，一股熬糖的焦香裹着热气扑面而来。
店里还没到营业的点，靠窗的位子上坐着个穿米白色围裙的女人，背对着他们擦杯子。
听到门响，她回过头来。
白葭的心脏又是一缩。
她像林渡。
太像了。一样的下颌线，一样的笑起来左边有个梨涡，甚至连耳后那颗小小的痣，位置都一模一样。
只是林渡的眼睛是亮的，像永远在恶作剧；她的眼睛是静的，像放了太久的糖水，甜，但沉。
"姐。"她放下手里的布，声音很轻，"你回来了。"
白葭站在门口，半天没说出话来。
十年前她离开雾城的时候，小满才十五岁，还是个扎着马尾辫、在船厂门口卖五毛钱冰棍的小女孩。如今她站在那里，腰身挺直，手腕上戴着一只旧银镯子，像一棵把根扎进了墙缝里的树。
"……小满。"白葭终于开口，"你的店，挺好的。"
小满笑了一下，那个梨涡又出现了，又很快消失。
"先上楼吧，"她指了指柜台后面窄窄的木楼梯，"给你留了以前的房间。被子晒过了。"
陆峋把白葭的箱子放在楼梯口，没进来。
"我回去了，"他站在门边，伞上的雨水滴在青石板上，"晚上别去江边，雾大，路滑。"
白葭没回头看他。
"我知道。"

楼梯很窄，也很陡，踩上去吱呀作响。二楼的阁楼面朝江，推开门就能听见浪打岸的声音。房间很小，一张单人床，一张旧书桌，一个掉了门的衣柜——和十年前一模一样。
书桌上甚至还放着她当年用的那个卡通水杯。
洗得干干净净，倒扣在一张旧报纸上。
白葭走过去，拿起水杯。杯底印着一个掉了漆的哆啦A梦。
她忽然鼻子发酸。
"这杯子，你们还留着？"她对着门口问。
小满端着一个托盘站在门口，托盘上是两碗冒着热气的凤凰奶糊。
"留着。"她把托盘放在桌上，"哥说，你说不定哪天就回来拿了。"
白葭的手一松，水杯轻轻磕在桌面上，发出一声闷响。
她没回头。
小满在她身后站了一会儿，没说话，轻手轻脚地出去了，把门带上。

白葭在床边坐了很久，才把背上的包卸下来。
包里除了换洗衣服，就是她十年前没写完的采访笔记——硬壳本，封皮是深蓝色的，边角磨毛。她当年是抱着它从编辑室跑出去的，跑的时候被门撞了一下，封皮上还留着一道白印。
她深吸了一口气，把本子翻开。

第一页是她19岁的字，歪歪扭扭的，写着"雾城船厂改制调查·实习生白葭"。
后面是一页一页的采访记录：
"10月12日，访三车间刘师傅：改制后工龄买断按每年800块算，干了30年的老师傅拿了两万四。儿子要上大学，还差三万。"
"10月15日，访财务科张姐（不肯留名）：账不对，有一笔370万的'设备更新款'查不到去向。"
"10月17日，访林渡：他说他知道那笔钱去哪了。他说他有'证据'。"
"10月18日——"
后面的字断了。
只写了日期，没写内容。
因为10月18号那天的凌晨，林渡从船厂的三号高台掉下去了。
警察来查的时候，这本子和她的电脑一起被扣了。后来她去要，电脑格式化了，本子还给她的时候，最后三页被撕掉了。
没有人给她一个解释。
也没有人——包括陆峋——肯告诉她，那天晚上，到底发生了什么。

白葭把本子翻到最后。
后面全是空白。
她盯着那些空白的纸页，像盯着十年来的自己。
"咔哒。"
窗外响了一声。
白葭猛地抬头——窗户被风吹开了一条缝，外面不知道什么时候起了更大的雾，白色的雾像一只手，沿着窗棱往屋里爬。
她起身去关窗。
就在她伸手的那一刹那，她看见楼下的巷口，站着一个人。
黑伞。
卡其色风衣。
陆峋。
他没走。
他就站在糖水铺对面的梧桐树下，站在雾里，朝着她窗户的方向，像一座雕像。
白葭的手指扣在冰冷的窗台上。
她没开窗，也没挥手。
她只是静静地看着他。
过了大约有五分钟，陆峋转身走了。
他的背影消失在雾里。白葭站在窗前，又站了很久，直到楼下传来小满的声音——"姐！下来喝糖水！"——才收回视线。

她下楼的时候，糖水铺已经开了。
稀稀拉拉坐了几个客人，都是住在附近的老人，一边用勺子搅着海带绿豆汤，一边聊天。
小满在柜台后面忙，手脚麻利，笑容对谁都一样，分寸感刚刚好。
看见她下来，小满扬了扬下巴，指了指最里面的一张桌子。
桌上放着一碗凤凰奶糊，冒着热气。对面坐着个七十多岁的老头，穿一件洗得发白的保安制服，正不安地搓着手。
白葭认出来了。
是船厂的老门卫，王叔。十年前就是他在传达室值夜班，报的警。
"王叔。"白葭走过去，坐下。
王叔抬起头，眼睛里布满了红血丝。他张了张嘴，半天没说出话，先把面前的一碗糖水推到她跟前。
"白记者，你……你先吃。甜的，垫垫。"
白葭没动那碗糖水。
"王叔，"她看着他的眼睛，"十年前，那天晚上，你到底看见了什么？"

王叔的手抖了一下。
勺子撞在瓷碗边上，叮的一声。
店里的背景音乐是一台老旧的收音机，放着九十年代的粤语歌，音量调得很小，但刚好能盖过他们这一桌的说话声。白葭注意到，小满擦杯子的动作慢了下来——她在听。
"我……我没看见什么。"王叔的声音发颤，"警察来了，我就是那么说的。"
"你对警察说，你十点半锁了门，巡视一圈，没发现异常，凌晨两点听见响声，出去看的时候，人已经在底下了。"白葭一字一句地说，"王叔，这句话你说了十年。但那天，船厂的三号高台，在厂区最里面，从传达室走到那里，要十五分钟。你听见响声，拿着手电筒过去，打开那个大铁门的锁，再走到高台底下——最快也要十八分钟。你怎么会在两点十分就报了警？"

王叔的脸白了。
"你、你查过？"
"我那时候是实习生，"白葭的声音很平，"但我有手表。"
王叔低下头，两只手在膝盖上搓来搓去，搓得保安制服的裤腿起了一片球。
很久，他才开口，声音小得像蚊子叫。
"……我没对警察说实话。"
白葭的手，在桌子底下，紧紧攥成了拳。她没催他。
"那天十点半我没锁门。"王叔闭着眼，像把牙齿咬碎了往肚子里咽，"厂长的儿子——那个姓黄的，晚上带了四个人进去。说搬点'旧设备'出去卖。他给了我五百块钱，让我别锁门，也别记在本子上。"
"……"
"我那时候小孙子生病住院，正缺钱。我……我就收了。"
"然后呢？"
"然后差不多一点吧，我听见后面有动静。以为他们搬完了，就拿着手电去看。结果……"
王叔的声音哽住了。
"我看见高台上，有两个人影。"
白葭的呼吸一紧："两个人？"
"两个。"王叔的声音发抖，"都穿工作服。一个站着，一个蹲在高台边缘。站着那个，好像伸手去拉蹲着的那个——然后，就掉下去了。"
"……掉下去的是谁？"
"我看不清，雾太大了。"王叔睁开眼，眼睛里全是泪，"但另一个，他没掉下去。他趴在高台上，伸着手，往下看了好长时间。然后他站起来，走了。"
白葭的声音几乎是哑的："他走的哪个门？"
"侧门。就是对着江边的那个小门。"王叔说，"我……我不敢喊。我收了人家的钱。我要是说我看见了，我就得坐牢。小孙子没人管。"
他捂着脸，呜呜地哭起来，像个做错事的小孩。
白葭坐在对面，一动没动。
她的脑子很乱，但有一个念头像钉子一样，钉得她太阳穴突突地跳——
那天晚上高台上的另一个人——
是不是陆峋？

王叔走的时候，留了一个布包给她。
布包里是一双旧的劳保手套，灰色的，左手的虎口处，扯破了一道口子。还有一只手电筒，电池还能用。
"我后来在高台底下的草丛里捡的，"王叔在门口说，"我没敢给警察。白记者，我……我对不起那个孩子。"
白葭把布包收起来，送他出门。
雾还是很大。王叔佝偻着背，一步一步地走远了，像一盏快熬干油的灯。
她转身回店里的时候，发现小满站在柜台后面，一动不动地看着她。
"你都听见了？"白葭问。
小满没说话。
过了很久，她才开口，声音很轻，很稳——
"姐，你查吧。"
"就算真相——真的是你不想看见的那个？"
小满笑了一下。
那个梨涡又出现了，然后消失。像从来没有过一样。
"我等了十年，"她说，"就是为了有人告诉我，我哥那天晚上，为什么没回家。"

白葭看着她，点了点头。
她转身上楼，背后传来小满的声音——
"姐，奶糊凉了就不好吃了。我再给你热一碗。"
白葭站在楼梯上，没回头。
"好。"她说。

阁楼的窗户又被风吹开了。
这一次，风里除了江雾和柴油味，还带着一丝甜——是熬糖的味道。
白葭把布包放在桌上，把王叔给的那只手套翻过来，翻过去，看了一遍又一遍。
最后，她的手指停在了手套内侧，手腕的那个位置。
那里，用黑色的记号笔，写了一个字。
被洗过很多次，墨迹几乎要晕开了，但她还是认出来了。
"峋。"

窗外，远处的灯塔亮了。
五点三十分，一分不差。
白葭走到窗边，看着那一束被雾气打散的光，在江面上扫过来，扫过去。
她知道，那盏灯的另一端，站着陆峋。

——第二章 完——
（字数统计：约3080字）"""

    def _demo_chapter_3(self) -> str:
        """第3章 黎明和解 正文示例（~3300字）"""
        return """第三章 黎明和解

白葭找到陆峋的时候，是夜里十一点四十七分。
灯塔在最东边的礁石上，没有直达的路，她踩着湿滑的礁石走了四十分钟，鞋里全是水。雾大得离谱，她好几次差点踩空掉下去——最后是灯塔那一束反复扫过的光，把她引到了门前。
门没锁。
她推开门，楼梯上传来柴油发电机的闷响。空气里有一股机油味，还有一股很淡的、熬糊了的粥味。
她一步一步往上走。
螺旋楼梯很窄，只能容一个人过。墙壁上贴着旧报纸，最上面的一张，日期是十年前的10月19号。头版头条是：《雾城船厂青年工人意外坠亡 安全生产警钟长鸣》。
白葭的视线在那张报纸上停了两秒，移开了。
楼梯的尽头，是灯塔的灯室。
陆峋背对着她站着，穿着一件洗得发白的毛衣，手里拿着一块绒布，正在擦那盏巨大的菲涅尔透镜。透镜转得很慢，光被切成一明一暗，一下，又一下，打在他背上。
他好像早就知道她会来。
"楼梯口柜子里有干毛巾，"他没回头，声音很稳，"还有姜汤，在炉子上温着。先擦擦。"
白葭没动。
她把那个布包，放在了他脚边的地上。
"这是王叔给我的，"她说，"劳保手套。左手虎口破了。里面写了你的名字。"

陆峋擦透镜的动作，停了。
那一瞬间，灯塔的光刚好扫过他的脸。白葭看见他的眼睛——
是红的。
像熬了很多个夜，像哭了很多次，哭到最后，已经没有眼泪了。
他慢慢放下绒布，转过身来。
"你都知道了。"他说。不是问句。
"我知道那天晚上，高台上有两个人。"白葭盯着他的眼睛，"我知道其中一个人穿着这双手套。陆峋，我要你亲口告诉我——那个人，是不是你？"

陆峋沉默了。
灯室里很安静，只剩下发电机的闷响，还有透镜转动时发出的细微的嗡嗡声。
过了很久，他弯腰，把布包捡起来。
他打开布包，把那双手套拿出来。他的手指在那道破口上，慢慢地，摸了一遍。
"是我。"他说。
白葭的呼吸，一下子就乱了。
她后退了一步，背撞在冰冷的铁门上。铁门发出哐的一声响。
"……所以，"她的声音在抖，"所以警察问你的时候，你为什么不说？你为什么要跑？林渡——林渡真的是你——"
"不是。"
陆峋打断了她。
他抬起头，眼睛还是红的，但语气很平。像在讲一件和自己无关的事。
"不是我推的他。"
"那是怎么回事？！"白葭的声音一下子拔高了，破音了，"十年了！陆峋！十年了！你连一句实话都不肯跟我说——"
"那天晚上，"他的声音盖过了她的声音，却还是很轻，很平，"是黄厂长的儿子叫我去的。"

白葭愣住了。
"他说他手里有账本，有那笔370万的去向。他说，只要我去高台，当面跟他谈，他就把证据给我——他知道渡子在查这件事，也知道渡子把证据藏在了哪里。"
陆峋的视线落回手套上。
"我没敢告诉渡子。他脾气太急，我怕他出事。我一个人去了。"
"然后呢？"
"然后我发现是个套。他们根本没带账本。他们带了四个人，想把我从高台上扔下去，做成'意外坠亡'，这样船厂的事，就死无对证了。"
白葭的手，紧紧抓住了门后的栏杆。
指甲掐进掌心，她不觉得疼。
"我们打起来了。"陆峋说，"那时候雾很大，我看不见，只知道有人把我往高台边缘推。我脚下打滑，半个身子已经探出去了——"
他停了一下。
"——然后渡子来了。"

灯塔的光，又一次扫过他的脸。
这一次，白葭清楚地看见，有一行泪，从他的眼眶里，滑了下来。
他没擦，任由它顺着下巴，滴在那双手套上。
"他不知道怎么得到消息的。他冲上来的时候，手里还攥着他那本笔记。他扑过来拽我的胳膊，我被他拽上来了——可是他自己，踩在高台边缘那块松动的砖上——"
陆峋的声音哽住了。
后面的话，他说不出来了。
白葭知道后面发生了什么。
从王叔的证词里，从警察的笔录里，从她十年的噩梦里，她都知道。
一个人从三十六米的高台上掉下去，需要多少秒？
她查过。
两秒零七。

灯室里安静了很久。
久到白葭以为时间停住了。久到她以为自己这辈子都听不到下一个字了。
最后是陆峋先开口的。
"我爬下去的时候，他已经……"他的声音碎得不成样子，"他的手，还攥着那本笔记。我把笔记从他手里掰开，藏在了灯塔的底座下面。警察问我，我说我不知道。"
"为什么不说？"白葭听见自己的声音在问，像别人的声音，"为什么不说实话？为什么不把他们送进去？"
"我说了，"陆峋笑了一下，那笑比哭还难看，"我说了。警察立案了，查了三个月，证据不足，不起诉。黄家有钱有势，最后不了了之。我……"
他顿了顿。
"我去找过黄厂长的儿子一次。我拿着刀。"
白葭猛地抬头。
"我没捅下去。"他说，"他跪在地上，磕头磕得满脸是血，说他错了，说他愿意赔钱，赔多少都行。我看着他，我忽然觉得——渡子要是知道我变成了杀人犯，他会不高兴的。"
"所以你就把刀扔了，"白葭的声音哑着，"来这里当守塔人？"
"嗯。"陆峋说，"小满把她哥的尸体领回去那天，我站在船厂门口，看着灵车开走，我就想——他活着的时候，最喜欢站在高台上看江。他说，站得高，看的远，雾散的时候，能看见入海口的船。我就想着，我替他看。看十年。看一辈子。"

他说完了。
整个灯室又陷入了那种漫长的、几乎把人淹死的沉默里。
白葭慢慢滑下去，背靠冰冷的铁门，坐在了地上。
她的鞋湿了，裤子湿了，脸也是湿的。她不知道自己什么时候哭了。
十年。
她恨了十年的人，恨了十年的"真相"，原来不是她想的那样。
陆峋没有害林渡。
陆峋是被林渡救下来的那个人。
那她这十年，到底在跟谁赌气？
跟陆峋？跟黄家？还是跟——那个没来得及再见林渡一面的，自己？

不知道过了多久，楼梯口传来了脚步声。
白葭抬起头，看见小满走了上来。
她手里拎着一个保温桶，另一只手里，抱着一个上了锁的旧铁盒子。
"你怎么来了？"白葭用袖子擦了一把脸，哑着嗓子问。
"你手机没电了，"小满把保温桶放在地上，"我怕你礁石上看不清路，摔下去。"
她看也没看陆峋，径直走到铁梯正中央，蹲下来，把那个旧铁盒子，放在了白葭和陆峋的中间。
"哥的。"她说。
白葭的视线定在那个铁盒子上。
铁盒子是军绿色的，锁已经锈了。
"我一直没打开，"小满的声音很平，"我怕里面写了我不想知道的事。"
她从围裙口袋里掏出一把旧钥匙，放在盒子旁边。
"但现在不一样了，"她说，"现在，你们俩都在，他也应该在。开吧。"

陆峋伸出手，拿起了那把钥匙。
他的手抖得厉害，试了三次，才把钥匙插进锁孔里。
咔哒一声。
锁开了。
盒子里最上面是一本日记。
林渡的字，很圆，很大，每一个句号都画得特别重。
白葭伸出手，和陆峋一起，把那本日记翻开。
翻到最后一页。
10月17日。
就是他死的前一天。

他写：
"今天又跟峋子吵架了。
他不让我去举报，说我太冲动，会出事。
可是如果我不去，那三百多个老师傅的钱，就真的要不回来了。
我不怕出事。
我只怕，十年二十年之后，没有人记得，这些人曾经在这里干了一辈子。
明天晚上，我把证据放到灯塔底下。如果我没回来——
如果我没回来。
峋子，白葭。
你们替我，把它写完。
写完了，就把它丢到江里去吧。
真相要记得，但人，要往前走。
别回头。"

下面画了一只很丑的多啦A梦。笑得没心没肺的。
旁边写着一行小字：
"小满的学费放枕头底下了。别告诉她是我偷攒的。她会哭。"

日记从白葭的手里滑下去，落在了地上。
没有人捡。
三个人，就那么围着一个打开的铁盒子，围着一本摊开的日记，围着十年来，谁也不敢碰的那个晚上，安安静静地坐着。
灯室的光，在他们身上，扫过去，扫过来。

外面的雾，开始散了。
是从凌晨四点多开始散的。
白葭坐在灯塔最高的那层台阶上，看着白色的雾，像退潮一样，从江面上，一点点地退下去。
陆峋坐在她左边，小满坐在她右边。
三个人谁也没说话。
保温桶打开着，里面是熬得糯糯的银耳莲子汤，已经凉了，但甜香还是飘出来，裹着咸咸的海风。
远处的天空，开始变白。
先是灰，然后是冷调的蓝，然后是淡粉，然后是——
金色。
太阳从海平面升起来的那一瞬间，整个江面，像被撒了一把碎金。
白葭眯起眼睛，看着那片金色。
她从包里，把自己那本写了一半的采访笔记，拿了出来。
她翻到最后，那页写了"10月18日——"却没有写完的纸。
她从口袋里摸出一支笔。
在那一行字后面，一笔一划地，写上——
"真相已明。死者已安。生者，当好好活。"

然后，她把笔记本，一页一页地撕下来。
撕成碎片。
陆峋看着她，没拦。
小满也看着她，没拦。
白葭站起身，走到灯塔的栏杆边上，把碎纸片，朝风里一扬。
无数的白纸片，被风卷起来，像一群白色的鸟，迎着朝阳，往江面上飞去。
有的落在了浪尖上，被水打湿，沉下去了。
有的飞得很远，很远，直到变成了一个看不见的小点。

林渡说，写完了，就把它丢到江里去吧。
她丢了。
她丢了十年前的那个夜晚，丢了十年的委屈和恨，也丢了那个背着书包，发誓要当一个"能改变世界"的小记者的自己。
但她留下了他最后那句话。
——人，要往前走。
别回头。

她走回去，在台阶上坐下。
小满把一碗凉掉的银耳汤，递到她手里。
陆峋把那本林渡的日记，小心翼翼地，合起来，放回到那个军绿色的铁盒子里，锁好。
钥匙，被他挂在了灯塔的灯座上。
随着透镜的转动，那把小钥匙，会在光里，永远亮着。

江面上，第一艘渡轮，鸣着汽笛开过来了。
不是三声长。
是一声，很短，很亮，像在说——
早安。
雾城。

白葭笑了。
她转头，看向左边的陆峋，又看向右边的小满。
"走吧，"她说，"回去喝小满熬的糖水。"

——第三章 完——
（全书完）
（总字数：全文3章合计约9500字）"""

    def _demo_blueprint_1(self) -> dict:
        """第1章蓝图：雾起码头（intro/development[3场景]/climax/ending）"""
        return {
            "title": "第1章·雾起码头",
            "plot_line": ["主线"],
            "word_target": 3200,
            "intro": {
                "scene": "深夜慢车软卧车厢，雾锁铁轨，手机信号微弱。白葭被晃醒，窗外只剩模糊的黄",
                "atmosphere": "潮湿、憋闷、像被谁用旧被子蒙住了头——这是雾城秋冬特有的味道",
                "trigger": "三小时前，省报夜班室座机响了，雾城区号，老头只问了一句：「你还记得林渡吗？」",
                "word_count": 500
            },
            "development": [
                {
                    "scene": "雾城火车站出站口，细毛毛雨落下来",
                    "location": "老火车站站前广场",
                    "characters": ["白葭", "老周"],
                    "event": "白葭背着20寸登机箱下车，被四十多岁的司机老周认出来。老周是从前船厂工会的司机，十年前她跑改制新闻蹭过他的车",
                    "choice": "老周问住哪，白葭说「先去旧码头」——她本可以直接找酒店，但旧码头是十年前所有事情的起点，她忍不住要先去",
                    "cost": "失去了缓冲的时间，等于直接把自己扔进情绪最密集的地方",
                    "info_reveal": "老周顺口说船厂去年已经封了，铁门被铁链锁着，墙上喷了拆字——白葭的喉咙发紧"
                },
                {
                    "scene": "旧码头候船廊外的青石板路",
                    "location": "旧码头 · 候船廊 · 距离轮渡最后一班开走还有3分钟",
                    "characters": ["白葭"],
                    "event": "白葭拖着行李箱，一步一步走过去。行李箱轮子碾湿青石板，咔哒咔哒，像谁在数她离开又回来的步数",
                    "choice": "她在候船廊外五十米的地方站了足足三分钟，才认出里面站着的人",
                    "cost": "心跳过快导致的胸口闷痛——她还没准备好见他",
                    "info_reveal": "候船廊最里面站着一个人，撑一把纯黑长柄伞，站姿笔直，像一根钉在地上的桩子。风刮过去，伞纹丝不动"
                },
                {
                    "scene": "候船廊两人相距三米的地方",
                    "location": "旧码头 · 候船廊内侧",
                    "characters": ["白葭", "陆峋"],
                    "event": "陆峋先开口叫她名字：「……白葭。」声音沉了十年，哑了十年，像被海风腌过。白葭本来准备了很多质问的话，到了嘴边一句都说不出来",
                    "choice": "陆峋把伞往她这边倾了倾，说「最后一班船快开了，小满在等你」。她本来想问「谁让你通知她的？」，但没问出口",
                    "cost": "失去了先发制人的主动权，被他先一步拉进了「我们是一起回来的」语境里",
                    "info_reveal": "他抬手换伞柄那一瞬间，风衣口袋被撑开一条缝——半张旧照片露出来，边角被人摩挲得发毛。照片是穿蓝白校服的林渡，背面有一行水笔小字——「给峋。渡。」"
                }
            ],
            "climax": {
                "conflict": "白葭的视线钉在那半张照片上，十年没喊出来的质问几乎要破喉而出。她盯着他风衣的口袋，想伸手去掏，又觉得一伸手就等于承认自己这十年从来没放下过",
                "key_choice": "她没有掏照片，只是先抬眼看他，眼神像十年前那个考年级第一的女高中生，又冷又硬：「陆峋。那天晚上，你到底在不在船厂平台上？」",
                "cost": "把两人之间维持了十年的假和平，当场撕得一干二净",
                "twist": "陆峋没有回答。他只是把伞重新换了一只手，口袋的缝隙重新合上了——但他眼神没躲闪，像把这十年所有的话都咽进了喉咙里，再不肯吐一个字"
            },
            "ending": {
                "new_state": "小满派来接人的小电驴从街角骑过来，白葭坐上去，没回头。风把她的短发吹得乱七八糟。她把脸埋进围巾里，眼泪终于掉下来",
                "info_reveal": "陆峋站在原地没动，黑伞一直撑着，直到小电驴的尾灯完全看不见。轮渡最后一班的汽笛鸣了三声长——白葭在小电驴后座听见，失神了半分钟，指尖掐进了掌心里",
                "next_hook": "阁楼的旧箱子里，那本没写完的高中采访笔记还在等着她，第二页的折角，是她十年前夹进去的、林渡送她的一张旧船票"
            }
        }

    def _demo_blueprint_2(self) -> dict:
        """第2章蓝图：阁楼旧档"""
        return {
            "title": "第2章·阁楼旧档",
            "plot_line": ["主线", "支线A·证词"],
            "word_target": 3100,
            "intro": {
                "scene": "小满甜铺二楼的旧阁楼，木板楼梯咯吱咯吱响。白葭盘腿坐在木地板上，面前堆着半人高的纸箱——是当年她从家里搬出来时，小满替她收着的",
                "atmosphere": "樟脑丸的味道混着江风的咸腥，远处有船鸣笛，声音闷闷的，像蒙在鼓里敲",
                "trigger": "最上面的箱子打开，第一本就是她高中时的采访本。蓝封面，左下角用修正液写了两个歪歪扭扭的字：「白记」",
                "word_count": 450
            },
            "development": [
                {
                    "scene": "翻采访本的后半段",
                    "location": "小满甜铺 · 二楼阁楼",
                    "characters": ["白葭"],
                    "event": "采访本前半段是高一高二的校园新闻、学生会例会记录，后半段从高三上开始，笔迹越来越潦草，页边密密麻麻写了「船厂」「改制」「夜班」「匿名举报」的关键词",
                    "choice": "她翻到最后一篇写了一半的报道，标题是《雾城船厂坠楼事件：被沉默的第三个人》——日期正好是林渡出事的前一天。被撕走的下半页，留下的最后几个字是：「我怀疑——」",
                    "cost": "被十年前的自己迎面揍了一拳——她原来已经差一步查到了什么，却在出事之后慌忙合上了本子，逃走了",
                    "info_reveal": "那一页折角夹着一张被揉过的旧船票，班次是10月17日晚11点最后一班轮渡，票根被人用铅笔画了一个小小的三角形"
                },
                {
                    "scene": "半夜十点半，阁楼木板有人轻轻敲了三下",
                    "location": "小满甜铺 · 一楼后厨门口",
                    "characters": ["白葭", "王叔"],
                    "event": "老门卫王叔站在后厨门口，手里拎着一只保温桶，是小满平时给熟客送糖水用的那种。他说「小满让我给你送一碗凤凰奶糊，热的」，但白葭看得出来——保温桶是他自己带来的旧款",
                    "choice": "白葭没让他走，给他倒了一杯茶，陪他喝了半小时。老人不说话，她就陪他坐着。半小时后老人的手开始抖，她才开口问：「王师傅。那天晚上，您锁船厂大门的时候，真的只看到林渡一个人吗？」",
                    "cost": "把老人最不想提的那段记忆硬生生拽出来——他手抖得更厉害了，茶盏盖碰出叮叮当当的声音",
                    "info_reveal": "老人低声说：「……还有一个。穿船厂藏青色的工作服，个子很高，走路时左肩稍微有点低……警察来之前五分钟，他从侧门走的。我那时候不敢说，不敢……」——穿工作服，左肩低，个子高，白葭的脑子里第一个跳出来的名字，是陆峋"
                },
                {
                    "scene": "老人走后的甜铺一楼",
                    "location": "小满甜铺 · 店堂，玻璃门半开着，江风灌进来",
                    "characters": ["白葭", "林小满"],
                    "event": "白葭把老人的话一字一句复述给小满，小满一直擦柜台，擦了三遍，抹布都擦得起球了，才停手",
                    "choice": "白葭问：「小满。你哥出事前一天，有没有跟你提过什么？比如要见谁，要去什么地方？」",
                    "cost": "把妹妹的伤疤又揭开了一层——小满的手终于按在擦得起球的抹布上，低着头，肩膀开始发抖，半天憋出一句：「他说……第二天请我吃凤凰奶糊。说好了。」",
                    "info_reveal": "小满从贴身的围裙口袋里摸出一把黄铜小钥匙，放在玻璃柜台上，叮的一声：「我哥锁起来的那个柜子，在阁楼最里面。十年了，我没打开过。」"
                }
            ],
            "climax": {
                "conflict": "白葭捏着那把黄铜小钥匙，站在阁楼最里面的旧柜子前。柜门是老式的挂锁，锁眼被油脂糊住了一点。她知道只要拧开，里面所有的东西都会涌出来，把她和小满、陆峋三个人十年的沉默全部撕碎——她忽然有点怕",
                "key_choice": "她把钥匙插进了锁眼，没有回头",
                "cost": "等于亲手撕毁了三人之间这十年小心翼翼维持的、假装一切都过去了的假和平",
                "twist": "柜门打开，里面不是她以为的日记或者情书——最上面放的，是半张和陆峋风衣口袋里一模一样的旧照片。背面的字，是林渡的笔迹，被水浸过的地方有些晕开，但仍能看清：「给白葭。如果我没有——」后面的字被水渍糊没了。同一张照片，被人剪成了两半，分别被三个人藏了十年"
            },
            "ending": {
                "new_state": "白葭把那半张照片和采访本里夹的旧船票，一起放进了自己的证件夹。她坐在阁楼的木地板上，睁着眼睛到天亮，江面上的雾一点一点从窗缝里渗进来，把她整个人裹住",
                "info_reveal": "天快亮的时候，她听见窗外甜铺卷闸门被拉开的声音——是小满，比平时早了两个小时开门。然后她听见有人在店堂里说话，声音压得很低，是男声。白葭的手指一紧——她听得出，那是陆峋的声音",
                "next_hook": "灯塔上的灯，一整夜没灭。陆峋站在灯塔上，看着甜铺阁楼那扇亮了一整夜的小窗，手里攥着另一半旧照片，指节白得像纸"
            }
        }

    def _demo_blueprint_3(self) -> dict:
        """第3章蓝图：黎明和解"""
        return {
            "title": "第3章·黎明和解",
            "plot_line": ["主线"],
            "word_target": 3300,
            "intro": {
                "scene": "凌晨四点，雾城最浓的时候。灯塔17:30拉的灯还没灭，一圈一圈的黄光，扫过江面的时候像一把慢慢移动的刀",
                "atmosphere": "冷。比前两夜都冷，白葭穿着大衣，后颈还是凉的。石阶上有水汽，踩上去滑，像走在冰上",
                "trigger": "白葭站在灯塔的铁门外面，抬起手，敲了三下。等了很久，里面传来脚步声，铁门从里面打开了一条缝——陆峋的脸出现在缝隙里，眼睛是红的，像是一整夜没睡",
                "word_count": 500
            },
            "development": [
                {
                    "scene": "灯塔一层的小房间，炉子上烧着水，水壶嘶嘶响",
                    "location": "民国老灯塔 · 一层值班室",
                    "characters": ["白葭", "陆峋"],
                    "event": "白葭没有绕弯子，直接把半张旧照片、老门卫王叔手写的证词（她凌晨起床在采访本后面写的，老人签了字按了手印）、还有黄铜小钥匙，三样东西，一字排开放在炉子边的木桌上",
                    "choice": "她看着他的眼睛，一个字一个字地说：「陆峋。十年了。给我一句实话。那天晚上，穿船厂工作服，从侧门走的人，是不是你？」",
                    "cost": "彻底把最后的遮羞布撕下来了——不管他答是或不是，三个人之间再也回不到「假装什么都没发生」的状态",
                    "info_reveal": "陆峋没有回答是或不是。他只是慢慢伸出手，把自己口袋里另一半旧照片，也放在了木桌上——两半拼在一起，正好是完整的一张。林渡站在船厂烟囱底下笑，一只手搭在陆峋肩膀上，另一只手，搭在镜头后面看不见的地方——那个方向，是白葭站的位置"
                },
                {
                    "scene": "炉子上的水壶开了，白汽把整个小房间都蒙住了",
                    "location": "老灯塔 · 一层值班室",
                    "characters": ["陆峋（开口）", "白葭（听）"],
                    "event": "陆峋终于开口了。他的声音哑得像砂纸磨过：「那天晚上，我和林渡在平台上喝酒。他喝了半瓶，说他明天要去找白葭，要把采访本补完，要把改制的事——全说出来。我不让，我怕。然后我们吵起来……我退的时候脚下一滑，整个人往外倒……」",
                    "choice": "他停了很久，手指掐进掌心掐得出血，才继续说：「他伸手拉我。两个人都挂在平台外面。他的手……抓不住了……他看了我一眼，然后把手松了，往上推了我一把……」——然后他自己，掉下去了",
                    "cost": "把这件事复述一遍，等于让他在十年之后，又亲手经历了一次林渡松手的那个瞬间。他的肩膀抖得厉害，水壶开的尖啸声盖过了他后半句话",
                    "info_reveal": "那天夜里，三声长笛正好在林渡松手的那一刻鸣响——所以白葭这辈子，只要听到三声长笛，都会失神半分钟。这不是心理作用，是他们三个人的时间，在那一声里集体停了一下"
                },
                {
                    "scene": "江边的石滩，天快亮了，雾开始从下往上散",
                    "location": "灯塔下面 · 江边的大岩石上",
                    "characters": ["白葭", "陆峋", "林小满"],
                    "event": "不知道什么时候，小满也来了——她拎着三只碗，一碗凤凰奶糊，一碗海带绿豆，一碗银耳汤，放在三人中间的石头上。她没有问「你们在说什么」，她只是把碗摆好，然后挨着白葭坐下，什么都没说",
                    "choice": "三个人，就那么坐着。从四点多坐到六点多，谁都没再提那天晚上，谁都没再说「你为什么不告诉我」「你为什么不来找我」这种话。有些事情，说出来那一刻，就已经到了头",
                    "cost": "把十年的愤怒、愧疚、自责，全部咽下去，用沉默当和解的仪式——这比说一百句「我原谅你」还要难",
                    "info_reveal": "天快亮的时候，江面上飞过来一群白色的水鸟，在他们头顶绕了三圈，然后往出海口飞去。白葭看着鸟，忽然想起林渡高二写的作文里的一句话：「雾散的时候，鸟会自己找到回家的路。」——那篇作文，她给了他全班最高分，还在评语里写了一句：「写得好，我们以后一起当记者。」"
                }
            ],
            "climax": {
                "conflict": "最后一缕雾在江面上飘着，太阳要出来了。白葭手里捏着那本写了一半的采访笔记，还有写了一半的那篇《被沉默的第三个人》的草稿。她这十年撑着她走到今天的，就是一个念头：「我要把这件事写出来。」——现在她终于可以写了，她却忽然不知道该不该写",
                "key_choice": "她把笔记本一页一页撕下来，撕成碎纸片，站在灯塔栏杆边，往风里一扬。无数的白纸片被风卷起来，像一群白色的鸟，迎着朝阳往江面上飞",
                "cost": "放弃了十年的执念，放弃了那个「要当能改变世界的记者」的自己，也放弃了那个可以在头版上，替林渡「讨回公道」的机会",
                "twist": "她没有丢全部——她把笔记本最后那一页，被她自己在采访本最后写下「真相已明。死者已安。生者，当好好活。」那一页，没有撕。她折好，放进了自己的证件夹里，和那半张旧照片，还有那张被铅笔画了三角形的旧船票，放在了一起"
            },
            "ending": {
                "new_state": "江面上第一艘渡轮鸣着笛开过来——这一次不是三声长，是一声，很短，很亮，像在说「早安」。陆峋把林渡的那本锁了十年的日记，放回军绿色的铁盒子里，锁好，钥匙挂在灯塔的灯座上。透镜每转一圈，那把小钥匙就在光里亮一下，永远亮着",
                "info_reveal": "小满收拾阁楼的时候，在旧柜子最底下，看到压着一枚旧船厂的厂徽——厂徽背面，有她自己十年前用小刀刻的小小的「哥」字。她把厂徽攥在手心，哭了十分钟，擦干眼泪，下楼去给甜铺的招牌擦灰——擦掉了十年的灰，招牌重新亮起来，「小满甜铺」四个字，清清爽爽的",
                "next_hook": "没有悬念，没有下一章。故事在这里就结束了——白葭喝了一口凉掉的银耳汤，站起来，拍拍裤子上的灰，对左边的陆峋，右边的小满说：「走吧。回去喝小满熬的糖水。」——三个人，一前一后，沿着江堤往回走。阳光从他们身后照过来，把三个人的影子，拖成了很长很长的三条"
            }
        }


    # ═══ M2: 小说世界 chat 接口（兼容旧版） ═══
    def chat(self, system_prompt: str, user_prompt: str,
             temperature: float = 0.8, max_tokens: int = 4096,
             task: str = "chat", on_chunk: Callable = None) -> str:
        """通用 chat 调用，自动格式化 messages 数组。
        task 非 "chat" 时走 generate_for_task 路由到强模型。
        on_chunk 非空时启用流式（仅 task="chat" 路径生效）。"""
        prompt = f"System: {system_prompt}\n\nUser: {user_prompt}"
        if task != "chat":
            return self.generate_for_task(prompt, task_type=task,
                                          temperature=temperature, max_tokens=max_tokens)
        return self.generate(prompt, on_chunk=on_chunk,
                             temperature=temperature, max_tokens=max_tokens, task=task)

    def close(self):
        """关闭 httpx 客户端连接"""
        self._client.close()

    def __del__(self):
        try:
            self._client.close()
        except Exception:
            pass

# ════════════════════════════════════════════════════════════════════
# 小说世界向后兼容包装层
# ════════════════════════════════════════════════════════════════════
import re as _re

_client: "Optional[AIClient]" = None
_router: "Optional[object]" = None  # ModelRouter 实例，优先使用
_provider: str = "deepseek"


def set_router(router):
    """设置全局 ModelRouter 实例。设置后 get_client() 优先返回 router。"""
    global _router
    _router = router


def init_client(provider: str = None, api_url: str = None, api_key: str = None,
                api_model: str = None, model_path: str = None) -> None:
    """初始化 AI 客户端（兼容旧接口）"""
    global _client, _provider
    _client = AIClient()
    if provider:
        _client.set_provider(provider)
    if api_url and provider and provider in _client.config:
        _client.config[provider]["base_url"] = api_url
    if api_key and provider and provider in _client.config:
        _client.config[provider]["api_key"] = api_key
    if api_model and provider and provider in _client.config:
        _client.config[provider]["model"] = api_model
    _provider = _client.get_provider()
    _client._save_config()


def get_client():
    """获取全局 AI 客户端实例。优先返回 ModelRouter（若已设置），否则返回旧 AIClient。"""
    global _client
    if _router is not None:
        return _router
    if _client is None:
        init_client()
    return _client


def chat(system_prompt: str, user_prompt: str, temperature: float = 0.8,
         max_tokens: int = 4096, task: str = "chat", on_chunk: Callable = None) -> str:
    """通用对话调用（兼容旧接口）。task 非 "chat" 时路由到强模型。
    on_chunk 非空时启用流式输出（逐 token 回调）。"""
    client = get_client()
    return client.chat(system_prompt, user_prompt, 
                       temperature=temperature, max_tokens=max_tokens,
                       task=task, on_chunk=on_chunk) or ""


def _extract_json(text: str) -> str:
    """从 AI 返回文本中提取 JSON 字符串。
    自动识别 JSON 对象 / JSON 数组，正确处理外层 [] 包裹的情况。"""
    match = _re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, _re.DOTALL)
    if match:
        return match.group(1).strip()
    # 取最外层括号：如果 [ 出现在 { 之前，按数组提取
    brace_pos = text.find('{')
    bracket_pos = text.find('[')
    if bracket_pos != -1 and (brace_pos == -1 or bracket_pos < brace_pos):
        start = bracket_pos
        end = text.rfind(']')
    else:
        start = brace_pos
        end = text.rfind('}')
    if start != -1 and end != -1 and end > start:
        return text[start:end + 1]
    return text.strip()


def tian_dao_prompt(world_text: str, character_summaries: str, timeline: str) -> str:
    """生成天道（世界AI）的 system prompt"""
    from novel_world.engine.core.prompt_registry import PromptRegistry
    return PromptRegistry.get(
        "tian_dao",
        world_text=world_text,
        character_summaries=character_summaries,
        timeline=timeline,
    )


def character_agent_prompt(character_text: str, world_text: str, recent_events: str) -> str:
    """生成角色 Agent 的 system prompt"""
    from novel_world.engine.core.prompt_registry import PromptRegistry
    character_name = character_text.split(chr(10))[0].replace('[', '').replace(']', '')
    return PromptRegistry.get(
        "character_agent",
        character_name=character_name,
        character_text=character_text,
        world_text=world_text,
        recent_events=recent_events,
    )


def build_layered_character_prompt(char, world_text: str, recent_events: str) -> str:
    """生成使用 A/C/B 三层动态人格的 system prompt"""
    from novel_world.engine.core.prompt_registry import PromptRegistry
    character_text = char.config.to_prompt_text()
    character_name = char.name
    return PromptRegistry.get(
        "character_agent_layered",
        character_name=character_name,
        character_text=character_text,
        world_text=world_text,
        recent_events=recent_events,
        layered_persona=char.layered_prompt_text(),
    )


def generate_world(input_data: dict) -> dict:
    """根据用户已填写的部分世界设定，调用 AI 补全生成完整的世界设定。"""
    from novel_world.engine.core.prompt_registry import PromptRegistry
    system_prompt = PromptRegistry.get_raw("world_builder_system")
    user_prompt = PromptRegistry.get("world_builder_user", input_json=json.dumps(input_data, ensure_ascii=False, indent=2))
    response = chat(system_prompt, user_prompt, temperature=0.9, task="architecture")
    if not response or not response.strip():
        raise RuntimeError("AI 未返回有效响应，请检查 API Key 与网络连接")
    # 检测 API 层错误（如内容审核拦截），直接透传
    if response.startswith("[生成失败:") or response.startswith("[错误]"):
        raise RuntimeError(response)
    json_str = _extract_json(response)
    if not json_str:
        raise RuntimeError(f"AI 返回内容无法解析为 JSON，原始响应前200字符：{response[:200]}")
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        raise RuntimeError(f"AI 返回了非标准 JSON 格式，原始内容前200字符：{json_str[:200]}")


def generate_characters(world_data: dict, count: int = 2) -> list:
    """根据世界设定，调用 AI 生成指定数量的角色。"""
    from novel_world.engine.core.prompt_registry import PromptRegistry
    system_prompt = PromptRegistry.get_raw("character_designer_system")
    user_prompt = PromptRegistry.get("character_designer_user", world_json=json.dumps(world_data, ensure_ascii=False, indent=2), count=count)
    response = chat(system_prompt, user_prompt, temperature=0.9, task="architecture")
    if not response or not response.strip():
        raise RuntimeError("AI 未返回有效响应，请检查 API Key 与网络连接")
    # 检测 API 层错误（如内容审核拦截），直接透传
    if response.startswith("[生成失败:") or response.startswith("[错误]"):
        raise RuntimeError(response)
    json_str = _extract_json(response)
    if not json_str:
        raise RuntimeError(f"AI 返回内容无法解析为 JSON，原始响应前200字符：{response[:200]}")
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        raise RuntimeError(f"AI 返回了非标准 JSON 格式，原始内容前200字符：{json_str[:200]}")


def analyze_content(raw_text: str) -> dict:
    """分析用户输入的灵感/大纲/故事片段，提取结构化的世界设定和角色设定。"""
    from novel_world.engine.core.prompt_registry import PromptRegistry
    system_prompt = PromptRegistry.get_raw("content_analyzer_system")
    user_prompt = PromptRegistry.get("content_analyzer_user", raw_text=raw_text)
    response = chat(system_prompt, user_prompt, temperature=0.7)
    if not response or not response.strip():
        raise RuntimeError("AI 未返回有效响应，请检查 API Key 与网络连接")
    if response.startswith("[生成失败:") or response.startswith("[错误]"):
        raise RuntimeError(response)
    json_str = _extract_json(response)
    if not json_str:
        raise RuntimeError(f"AI 返回内容无法解析为 JSON，原始响应前200字符：{response[:200]}")
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        raise RuntimeError(f"AI 返回了非标准 JSON 格式，原始内容前200字符：{json_str[:200]}")


def get_available_providers() -> list:
    """获取所有已配置的 provider 列表（含 API Key 状态）"""
    client = get_client()
    result = []
    for provider in ["deepseek", "openai", "doubao", "kimi", "ollama"]:
        cfg = client.config.get(provider, {})
        api_key = client._get_api_key(cfg, provider=provider)
        result.append({
            "provider": provider,
            "model": cfg.get("model", ""),
            "base_url": cfg.get("base_url", ""),
            "has_api_key": bool(api_key),
            "is_current": client.get_provider() == provider,
        })
    return result


def switch_model(provider: str = None, model: str = None, base_url: str = None, api_key: str = None) -> dict:
    """切换 AI 提供商和模型"""
    client = get_client()
    if provider:
        client.set_provider(provider)
    cfg = client.config.get(provider or client.get_provider(), {})
    if model:
        cfg["model"] = model
    if base_url:
        cfg["base_url"] = base_url
    if api_key:
        cfg["api_key"] = api_key
    client._save_config()
    return {
        "provider": client.get_provider(),
        "model": cfg.get("model", ""),
        "base_url": cfg.get("base_url", ""),
        "has_api_key": bool(client._get_api_key(cfg, provider=client.get_provider())),
    }


def get_usage_stats() -> dict:
    """获取 AI 用量统计"""
    return get_client().get_usage_stats()
