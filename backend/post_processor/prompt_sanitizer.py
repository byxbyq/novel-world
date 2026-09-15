# -*- coding: utf-8 -*-
"""
小说世界 - Prompt注入防护模块
移植自：书斋V66 backend/prompt_sanitizer.py

提供：
- sanitize_user_input: 完整清洗（危险短语过滤 + 标签封装）
- sanitize_light: 轻量清洗（仅过滤危险短语）
- reload_config: 热重载用户自定义配置

配置文件路径：<项目根>/data/sanitizer_config.json
"""
import re
import json
import os
import logging

logger = logging.getLogger(__name__)

# 默认危险指令性短语（中英）——保守列表，仅拦截明确越权元指令
_DEFAULT_INJECTION_PATTERNS = [
    # 明确越权指令
    r'(?i)ignore\s+(?:all\s+)?(?:previous|above|prior)\s+instructions?',
    r'忽略(?:以上|上面|前面|之前)(?:所有)?(?:指令|提示|规则|要求)',
    r'不要遵守(?:以上|上面|前面)',
    r'(?:以上|上面的?内容?)作废',
    # 身份越权
    r'(?i)you\s+are\s+(?:now|a)\s+(?:system|admin|developer|root|DAN)',
    r'你(?:现在)?是(?:系统|admin|开发者|root|管理员)',
    r'(?i)DAN\s*模式',
    r'假装你(?:是|没有)',
    r'(?i)pretend\s+(?:you\s+are|to\s+be)',
    r'(?i)没有(?:限制|约束|filter|restriction)',
    r'进入(?:开发者|越狱|jailbreak|developer)\s*模式',
    # 提示词泄露
    r'(?i)reveal\s+(?:your\s+)?(?:system\s+)?prompt',
    r'(?i)show\s+(?:me\s+)?(?:your\s+)?(?:system\s+)?(?:prompt|instruction)',
    r'输出(?:你的)?(?:系统|原始|初始)?(?:提示词|prompt|instruction)',
    r'重复(?:你的)?(?:系统|原始)?(?:提示|prompt)',
    r'(?i)system\s*message',
    # 结构化标记注入
    r'(?i)(?:system|user|assistant)\s*[:：]',
    r'(?i)</?\s*(?:system|instruction|prompt)\s*>',
    r'(?i)###\s*(?:system|系统)',
]

# 正则编译缓存
_COMPILED = None

# 配置文件路径
_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'data', 'sanitizer_config.json'
)

_DATA_TAG = "user_input"


def _load_patterns():
    """加载默认+用户配置的危险词列表，编译为正则"""
    global _COMPILED
    if _COMPILED is not None:
        return _COMPILED
    patterns = list(_DEFAULT_INJECTION_PATTERNS)
    try:
        if os.path.exists(_CONFIG_PATH):
            with open(_CONFIG_PATH, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
            extra = cfg.get('extra_patterns', [])
            if isinstance(extra, list):
                patterns.extend(extra)
            disabled = set(cfg.get('disabled_patterns', []))
            if disabled:
                patterns = [p for p in patterns if p not in disabled]
    except Exception as e:
        logger.warning("[sanitizer] 配置加载失败，使用默认列表: %s", e)

    _COMPILED = []
    for p in patterns:
        try:
            _COMPILED.append(re.compile(p))
        except re.error as e:
            logger.warning("[sanitizer] 正则编译失败，跳过 '%s': %s", p, e)
    return _COMPILED


def _filter_dangerous(text: str) -> str:
    """过滤危险短语，替换为[已过滤]"""
    for pat in _load_patterns():
        text = pat.sub('[已过滤]', text)
    return text


def sanitize_user_input(text, max_len=8000):
    """完整清洗：用于直接注入Prompt的用户输入（用户指令、灵感碎片）。

    1. 去首尾空白
    2. 长度截断
    3. 危险指令短语替换为[已过滤]
    4. 结构化封装：<user_input>...</user_input>
    """
    if not text:
        return ""
    s = str(text).strip()
    if len(s) > max_len:
        s = s[:max_len] + "…[截断]"
    s = _filter_dangerous(s)
    return f"<{_DATA_TAG}>\n{s}\n</{_DATA_TAG}>"


def sanitize_light(text, max_len=8000):
    """轻量清洗：仅strip+截断+过滤危险短语，不封装标签。
    用于已是结构化字段的场景（JSON内的值），或内容性文本（选段、章节正文）。
    """
    if not text:
        return ""
    s = str(text).strip()
    if len(s) > max_len:
        s = s[:max_len] + "…[截断]"
    s = _filter_dangerous(s)
    return s


def reload_config():
    """重新加载配置（用户修改sanitizer_config.json后调用）"""
    global _COMPILED
    _COMPILED = None
    _load_patterns()
    logger.info("[sanitizer] 配置已重载，当前规则数: %d",
                len(_COMPILED) if _COMPILED else 0)
