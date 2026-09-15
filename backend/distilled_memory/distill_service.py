# -*- coding: utf-8 -*-
"""
小说世界 - 蒸馏服务
从书斋V66 backend/services/distill_service.py 移植与适配

核心能力：
- 5路并行提取器（情节/技法/场景/反面/世界观）
- 单章蒸馏 distill_single_chapter()
- 状态记忆保存 save_state_memory()
- 10x压缩比（60K字→6K字符关键信息）

适配说明：原书斋V66 使用 backend.ai_client.AIClient 做AI调用，
小说世界适配为可注入的 LLM 调用接口（llm_callable），降低耦合。
"""

import os
import json
import logging
from datetime import datetime
from typing import Optional, List, Dict, Callable

from .memory_synthesizer import MemorySynthesizer
from .vector_memory import VectorMemory

logger = logging.getLogger(__name__)

# ============================================================
# 常量
# ============================================================

MAX_INPUT_CHARS = 80000
SAMPLE_CHARS = 60000

EXTRACTORS = {
    "plot": "情节结构提取器",
    "tech": "写作技法提取器",
    "scene": "场景实例提取器",
    "anti": "烂俗套路提取器",
    "world": "世界观设计提取器",
}

# 5路提取器模板（精简版，原书斋V66完整prompt在 EXTRACTOR_PROMPTS 中）
EXTRACTOR_TEMPLATES = {
    "plot": "提取本章情节结构技巧：悬念递进/高潮转折/节奏控制/升级节奏。",
    "tech": "提取本章写作技法：描写手法/对话设计/心理刻画/叙事视角。",
    "scene": "提取本章经典场景：环境/动作/对话片段，每场景附原文引用。",
    "anti": "提取本章可能落入的套路陷阱及规避方式。",
    "world": "提取本章世界观细节：设定/规则/势力/地点。",
}


# ============================================================
# DistillService
# ============================================================

class DistillService:
    """蒸馏服务 — 5路并行提取 + 10x压缩

    使用方式：
        service = DistillService(llm_callable=my_llm_function)
        result = service.distill_single_chapter(chapter_text, chapter_num=1)
        service.save_state_memory(result, chapter=1)

    压缩比：约10x（60K字输入 → 6K字符关键信息提取）
    """

    def __init__(
        self,
        llm_callable: Optional[Callable] = None,
        data_dir: str = "",
    ):
        """
        Args:
            llm_callable: LLM调用函数，签名为 (prompt: str) -> str
            data_dir: 蒸馏结果存储目录
        """
        self.llm = llm_callable
        self._data_dir = data_dir

        # 子模块
        self.memory_synthesizer = MemorySynthesizer(
            storage_dir=os.path.join(data_dir, "synthesizer") if data_dir else ""
        )
        self.vector_memory = VectorMemory(
            storage_dir=os.path.join(data_dir, "vector_memory") if data_dir else ""
        )

        if data_dir:
            os.makedirs(data_dir, exist_ok=True)

    # ── 主入口 ──

    def distill_single_chapter(
        self,
        chapter_text: str,
        chapter_num: int = 1,
        volume_num: int = 1,
        extractors: Optional[List[str]] = None,
    ) -> dict:
        """单章蒸馏：5路并行提取 → 聚合 → 状态记忆

        Args:
            chapter_text: 章节全文
            chapter_num: 章节号
            volume_num: 卷号
            extractors: 要运行的提取器列表，默认全部

        Returns:
            {
                "chapter": int,
                "extractions": {"plot": [...], "tech": [...], ...},
                "summary": str,
                "stats": {"input_chars": int, "extracted_chars": int, "compression_ratio": float}
            }
        """
        if not chapter_text:
            return {"chapter": chapter_num, "extractions": {}, "summary": "", "stats": {}}

        # 截断过长的输入
        if len(chapter_text) > MAX_INPUT_CHARS:
            chapter_text = chapter_text[:MAX_INPUT_CHARS]

        extractor_list = extractors or list(EXTRACTORS.keys())
        extractions = {}
        all_results = []

        for ext_name in extractor_list:
            if ext_name not in EXTRACTORS:
                continue
            result = self._run_extractor(ext_name, chapter_text, chapter_num)
            extractions[ext_name] = result
            all_results.extend(result)

        # 生成压缩摘要
        summary = self._generate_summary(extractions, chapter_text, chapter_num)

        input_chars = len(chapter_text)
        extracted_chars = sum(
            len(item.get("content", "")) for item in all_results
        ) + len(summary)

        stats = {
            "input_chars": input_chars,
            "extracted_chars": extracted_chars,
            "compression_ratio": round(input_chars / max(1, extracted_chars), 1),
            "extractors_used": list(extractions.keys()),
            "items_extracted": len(all_results),
        }

        return {
            "chapter": chapter_num,
            "volume": volume_num,
            "extractions": extractions,
            "summary": summary,
            "stats": stats,
            "timestamp": datetime.now().isoformat(),
        }

    def _run_extractor(
        self,
        ext_name: str,
        chapter_text: str,
        chapter_num: int,
    ) -> List[dict]:
        """运行单个提取器"""
        template = EXTRACTOR_TEMPLATES.get(ext_name, "")
        prompt = (
            f"## 第{chapter_num}章文本\n\n{chapter_text[:SAMPLE_CHARS]}\n\n"
            f"## 提取任务\n{template}\n\n"
            "请以JSON数组格式输出，每项包含：\n"
            "- id: 唯一标识\n"
            "- title: 简洁标题\n"
            "- content: 提取内容\n"
            "- tags: 标签列表\n"
            "- source_quote: 原文引用（≤150字）"
        )

        if self.llm:
            try:
                response = self.llm(prompt)
                return self._parse_extractor_response(response, ext_name, chapter_num)
            except Exception as e:
                logger.warning(f"提取器 {ext_name} LLM调用失败: {e}")

        # 无LLM时返回空结果
        return []

    def _parse_extractor_response(
        self,
        response: str,
        ext_name: str,
        chapter_num: int,
    ) -> List[dict]:
        """解析提取器响应"""
        import re as _re
        try:
            json_match = _re.search(r'\[[\s\S]*\]', response)
            if json_match:
                items = json.loads(json_match.group())
                for i, item in enumerate(items):
                    if "id" not in item:
                        item["id"] = f"{ext_name}_{chapter_num:03d}_{i+1:02d}"
                return items
        except (json.JSONDecodeError, AttributeError):
            pass
        return []

    def _generate_summary(
        self,
        extractions: dict,
        chapter_text: str,
        chapter_num: int,
    ) -> str:
        """生成章节压缩摘要"""
        parts = [f"第{chapter_num}章蒸馏摘要"]

        for ext_name, items in extractions.items():
            if items:
                titles = [item.get("title", "") for item in items[:5] if item.get("title")]
                if titles:
                    parts.append(f"[{EXTRACTORS.get(ext_name, ext_name)}] " + "、".join(titles))

        if len(parts) == 1:
            # 无提取结果时用前200字兜底
            parts.append(chapter_text[:200])

        return "\n".join(parts)

    # ── 保存状态记忆 ──

    def save_state_memory(self, distill_result: dict, chapter: int, volume: int = 1):
        """将蒸馏结果保存为状态记忆（写入 synthesizer + vector_memory）"""
        chapter_num = distill_result.get("chapter", chapter)
        extractions = distill_result.get("extractions", {})
        summary = distill_result.get("summary", "")

        # 保存到 MemorySynthesizer
        self.memory_synthesizer.add_entry(
            content=summary,
            scope="chapter_state",
            chapter=chapter_num,
            volume=volume,
            confidence=0.9,
            source_file=f"distill_ch{chapter_num:03d}",
            tags=["summary"],
        )

        # 保存到 VectorMemory
        self.vector_memory.add(
            content=summary,
            memory_type="chapter_memory",
            chapter=chapter_num,
            volume=volume,
            metadata={"distill_timestamp": distill_result.get("timestamp", "")},
        )

        # 各提取器结果
        for ext_name, items in extractions.items():
            for item in items:
                content = item.get("content", "")
                if not content:
                    continue

                memory_type = self._map_extractor_to_memory_type(ext_name)

                # 角色提取特殊处理
                if ext_name == "world" and "character" in str(item.get("tags", [])).lower():
                    memory_type = "character_memory"

                self.vector_memory.add(
                    content=content,
                    memory_type=memory_type,
                    chapter=chapter_num,
                    volume=volume,
                    metadata={
                        "extractor": ext_name,
                        "title": item.get("title", ""),
                        "tags": item.get("tags", []),
                    },
                    keywords=self._extract_keywords(content),
                )

        # 持久化
        self.memory_synthesizer.save()
        self.vector_memory.save()

    @staticmethod
    def _map_extractor_to_memory_type(ext_name: str) -> str:
        mapping = {
            "plot": "event_memory",
            "tech": "technique_memory",
            "scene": "event_memory",
            "anti": "technique_memory",
            "world": "world_memory",
        }
        return mapping.get(ext_name, "event_memory")

    @staticmethod
    def _extract_keywords(text: str, max_kw: int = 5) -> List[str]:
        """简单关键词提取（基于词频）"""
        import re as _re
        words = _re.findall(r'[\u4e00-\u9fff]{2,}', text)
        word_freq = {}
        for w in words:
            if len(w) >= 2:
                word_freq[w] = word_freq.get(w, 0) + 1
        sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
        return [w for w, _ in sorted_words[:max_kw]]

    # ── 批量蒸馏 ──

    def distill_chapters(
        self,
        chapters: List[dict],  # [{"num": 1, "text": "..."}, ...]
        volume_num: int = 1,
    ) -> List[dict]:
        """批量蒸馏多章"""
        results = []
        for ch in chapters:
            result = self.distill_single_chapter(
                chapter_text=ch.get("text", ""),
                chapter_num=ch.get("num", 1),
                volume_num=volume_num,
            )
            self.save_state_memory(result, chapter=ch.get("num", 1), volume=volume_num)
            results.append(result)
        return results
