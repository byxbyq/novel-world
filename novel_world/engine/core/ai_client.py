"""
AI 客户端 - 支持本地LLM和API接口
"""

import json
import logging
import requests
import threading

logger = logging.getLogger(__name__)

class AIClient:
    """统一 AI 调用接口"""

    def __init__(self, provider="none", api_url="", api_key="", api_model="",
                 local_model_path=""):
        self.provider = provider  # "local", "api", "none"
        self.api_url = api_url
        self.api_key = api_key
        self.api_model = api_model
        self.local_model_path = local_model_path
        self._local_llm = None
        self._ready = False
        self._load_lock = threading.Lock()  # 防止并发重复加载模型
        self._preload_started = False  # 是否已开始预加载

    @property
    def is_available(self):
        return self.provider != "none"

    @property
    def is_model_loading(self):
        """模型是否正在加载中"""
        if self.provider != "local": return False
        # 检查预加载是否已开始（即使 _local_llm 还没创建）
        if self._preload_started:
            if self._local_llm and hasattr(self._local_llm, 'is_loading'):
                return self._local_llm.is_loading
            return True  # 预加载已开始但实例还没创建
        return False

    @property
    def is_model_ready(self):
        """模型是否已就绪"""
        if self.provider != "local": return self.is_available
        return self._ready and (self._local_llm.is_ready if self._local_llm else False)

    def preload_model(self, callback=None):
        """预加载模型（异步），在游戏启动时调用"""
        if self.provider != "local":
            if callback:
                try: callback(True)
                except Exception: pass
            return
        if self._preload_started: return
        self._preload_started = True
        logger.info("Starting model preload...")
        
        def _on_loaded(success):
            if success:
                self._ready = True
                logger.info("Model preload completed")
            else:
                logger.warning("Model preload failed")
            if callback:
                try: callback(success)
                except Exception: pass
        
        def _init_and_load():
            try:
                import sys as _sys
                _llm_path = os.environ.get("LOCAL_LLM_MODULE", "")
                if _llm_path and _llm_path not in _sys.path: _sys.path.insert(0, _llm_path)
                from local_llm import LocalLLM
                
                # 如果指定了模型路径，先重置单例
                if self.local_model_path:
                    import os as _os
                    _mdir = _os.path.join(_root, "models", "checkpoints", "llm", self.local_model_path)
                    if _os.path.isdir(_mdir):
                        LocalLLM.reset_instance()
                
                self._local_llm = LocalLLM()
                if self.local_model_path:
                    import os as _os
                    _mdir = _os.path.join(_root, "models", "checkpoints", "llm", self.local_model_path)
                    if _os.path.isdir(_mdir): self._local_llm.MODEL_CANDIDATES = [_mdir]
                self._local_llm.load_async(callback=_on_loaded)
            except Exception as e:
                logger.error(f"Preload init failed: {e}")
                if callback:
                    try: callback(False)
                    except Exception: pass
        
        threading.Thread(target=_init_and_load, daemon=True, name="ModelPreloader").start()

    def _ensure_local(self):
        """确保本地模型已加载，支持等待异步预加载"""
        if self._ready and self._local_llm is not None:
            return True  # 已就绪
        
        if self.provider != "local":
            return False
        
        # 如果指定了模型路径，先重置单例以确保加载正确的模型
        if self.local_model_path:
            try:
                import sys as _sys
                _llm_path = os.environ.get("LOCAL_LLM_MODULE", "")
                if _llm_path and _llm_path not in _sys.path: _sys.path.insert(0, _llm_path)
                from local_llm import LocalLLM
                import os as _os
                _mdir = _os.path.join(_root, "models", "checkpoints", "llm", self.local_model_path)
                if _os.path.isdir(_mdir):
                    # 重置单例，允许加载新模型
                    LocalLLM.reset_instance()
            except Exception as e:
                logger.warning(f"重置模型单例失败: {e}")
        
        # 检查是否已有预加载的实例正在加载
        if self._local_llm is not None:
            # 等待异步加载完成
            if hasattr(self._local_llm, 'is_loading') and self._local_llm.is_loading:
                logger.info("等待异步预加载完成...")
                import time
                while self._local_llm.is_loading:
                    time.sleep(0.1)
                self._ready = self._local_llm.is_ready
                return self._ready
            # 检查是否已加载完成
            if hasattr(self._local_llm, 'is_ready') and self._local_llm.is_ready:
                self._ready = True
                return True
        
        # 没有预加载，同步加载（fallback）
        if not self._load_lock.acquire(blocking=False):
            logger.info("另一线程正在加载模型，等待...")
            with self._load_lock:
                pass
            return self._ready and self._local_llm is not None
        
        try:
            if self._ready:
                return True
            import sys as _sys
            _llm_path = os.environ.get("LOCAL_LLM_MODULE", "")
            if _llm_path and _llm_path not in _sys.path: _sys.path.insert(0, _llm_path)
            from local_llm import LocalLLM
            self._local_llm = LocalLLM()
            if self.local_model_path:
                import os as _os
                _mdir = _os.path.join(_root, "models", "checkpoints", "llm", self.local_model_path)
                if _os.path.isdir(_mdir): self._local_llm.MODEL_CANDIDATES = [_mdir]
            self._local_llm.load()
            self._ready = True
            logger.info("本地LLM加载成功")
        except Exception as e:
            logger.warning(f"本地LLM加载失败: {e}")
            self.provider = "none"
        finally:
            self._load_lock.release()
        
        return self._ready and self._local_llm is not None
    def chat(self, system_prompt: str, user_prompt: str, max_tokens: int = 200, temperature: float = 0.8) -> str:
        """统一调用接口"""
        if self.provider == "none":
            return ""
        if self.provider == "local":
            return self._chat_local(system_prompt, user_prompt, max_tokens)
        elif self.provider == "vllm":
            return self._chat_vllm(system_prompt, user_prompt, max_tokens)
        elif self.provider == "api":
            return self._chat_api(system_prompt, user_prompt, max_tokens, temperature)
        return ""

    def _chat_local(self, system_prompt, user_prompt, max_tokens):
        """调用本地 Qwen 模型"""
        if not self._ensure_local():
            return ""
        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
            tokenizer = self._local_llm.tokenizer
            model = self._local_llm.model
            # Try chat template first (Qwen3.5 / Qwen2.5)
            try:
                text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True, enable_thinking=False)
            except TypeError:
                text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            except Exception:
                text = f"<|im_start|>system\n{system_prompt}<|im_end|>\n"
                text += f"<|im_start|>user\n{user_prompt}<|im_end|>\n"
                text += "<|im_start|>assistant\n"
            # 限制输入长度，避免 KV cache 过大
            inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=8192).to(model.device)
            import torch
            with torch.no_grad():
                out = model.generate(
                    **inputs, 
                    max_new_tokens=max_tokens, 
                    temperature=0.8, 
                    top_p=0.9, 
                    do_sample=True,
                    pad_token_id=tokenizer.pad_token_id or tokenizer.eos_token_id,
                )
            new_tokens = out[0][inputs["input_ids"].shape[1]:]
            reply = tokenizer.decode(new_tokens, skip_special_tokens=True)
            # 清理显存
            del inputs, out, new_tokens
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                import gc
                gc.collect()
            return reply.strip()
        except Exception as e:
            logger.warning(f"本地LLM调用失败: {e}")
            return ""

    def _chat_api(self, system_prompt, user_prompt, max_tokens, temperature=0.8):
        """调用 API 接口（OpenAI 兼容格式）"""
        if not self.api_url:
            return ""
        try:
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            payload = {
                "model": self.api_model or "default",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
            resp = requests.post(
                self.api_url, headers=headers,
                json=payload, timeout=60
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            logger.warning(f"API调用失败: {e}")
            return ""

    # ── vLLM 后端（可选，高性能本地推理）──

    def _chat_vllm(self, system_prompt, user_prompt, max_tokens):
        """通过 vLLM 兼容 API 调用本地模型（vLLM / llama.cpp server / ollama 等）。

        使用本地 API 地址（默认 http://localhost:8000/v1/chat/completions）。
        与 API 后端的区别：不需要 API key，超时更长，专门用于本地推理服务。
        """
        vllm_url = self.local_model_path if self.local_model_path and "http" in self.local_model_path else ""
        if not vllm_url:
            vllm_url = "http://localhost:8000/v1/chat/completions"
        try:
            headers = {"Content-Type": "application/json"}
            payload = {
                "model": self.api_model or "default",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "max_tokens": max_tokens,
                "temperature": 0.8,
            }
            resp = requests.post(
                vllm_url, headers=headers,
                json=payload, timeout=300
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            logger.warning(f"vLLM 调用失败: {e}")
            return ""


# ==========================================================================
# 工厂函数：自动检测并创建最优 AI 客户端
# ==========================================================================

def create_ai_client(
    preferred: str = "auto",
    api_url: str = "",
    api_key: str = "",
    api_model: str = "",
    local_model_path: str = "",
) -> AIClient:
    """根据环境自动创建最优 AI 客户端。

    优先级（preferred=auto 时）：
        1. vLLM 本地服务（端口 8000 可连通）
        2. 本地 transformers 模型（local_model_path 存在）
        3. 云端 API（api_url + api_key 可用）
        4. none 模式（模板 fallback）

    Args:
        preferred: 首选模式 ("auto", "vllm", "local", "api", "none")
        api_url: 云端 API 地址
        api_key: 云端 API 密钥
        api_model: 模型名称
        local_model_path: 本地模型路径或 vLLM 服务 URL

    Returns:
        AIClient 实例
    """
    env = detect_ai_environment(api_url=api_url, api_key=api_key,
                                 local_model_path=local_model_path)

    if preferred == "none":
        return AIClient(provider="none")

    if preferred == "api" and env["api_available"]:
        return AIClient(provider="api", api_url=api_url, api_key=api_key,
                        api_model=api_model)

    if preferred == "vllm" and env["vllm_available"]:
        client = AIClient(provider="api", api_url=env["vllm_url"],
                          api_key="EMPTY", api_model=api_model or "default")
        client.provider = "vllm"
        return client

    if preferred == "local" and env["local_available"]:
        return AIClient(provider="local", local_model_path=local_model_path)

    # auto 模式：按优先级选
    if preferred in ("auto", ""):
        if env["vllm_available"]:
            client = AIClient(provider="api", api_url=env["vllm_url"],
                              api_key="EMPTY", api_model=api_model or "default")
            client.provider = "vllm"
            return client
        if env["local_available"]:
            return AIClient(provider="local", local_model_path=local_model_path)
        if env["api_available"]:
            return AIClient(provider="api", api_url=api_url, api_key=api_key,
                            api_model=api_model)

    # 兜底
    return AIClient(provider="none")


def detect_ai_environment(api_url: str = "", api_key: str = "",
                          local_model_path: str = "") -> dict:
    """检测当前可用的 AI 推理环境。

    Returns:
        dict with keys:
            - vllm_available: bool
            - vllm_url: str
            - local_available: bool (本地 transformers 模型)
            - api_available: bool
            - vram_gb: float (估算显存)
            - recommended_mode: str
    """
    result = {
        "vllm_available": False,
        "vllm_url": "",
        "local_available": False,
        "api_available": False,
        "vram_gb": 0.0,
        "recommended_mode": "none",
    }

    # 1. 检测显存
    try:
        import torch
        if torch.cuda.is_available():
            result["vram_gb"] = round(
                torch.cuda.get_device_properties(0).total_mem / (1024**3), 1
            )
    except Exception:
        pass

    # 2. 检测 vLLM 服务
    vllm_url = ""
    if local_model_path and "http" in local_model_path:
        vllm_url = local_model_path
    else:
        vllm_url = "http://localhost:8000/v1/models"
    try:
        resp = requests.get(vllm_url, timeout=2)
        if resp.status_code == 200:
            result["vllm_available"] = True
            result["vllm_url"] = vllm_url.replace("/models", "/chat/completions")
    except Exception:
        pass

    # 3. 检测本地模型文件
    if local_model_path and "http" not in local_model_path:
        import os
        if os.path.isdir(local_model_path):
            has_model = any(
                fn.endswith(('.bin', '.safetensors', '.gguf'))
                for fn in os.listdir(local_model_path)
            )
            if has_model or result["vram_gb"] >= 6:
                result["local_available"] = True

    # 4. 检测云端 API
    if api_url and api_key:
        result["api_available"] = True

    # 5. 推荐模式
    if result["vllm_available"]:
        result["recommended_mode"] = "vllm"
    elif result["local_available"]:
        result["recommended_mode"] = "local"
    elif result["api_available"]:
        result["recommended_mode"] = "api"
    else:
        result["recommended_mode"] = "none"

    return result
