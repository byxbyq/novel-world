---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: 62a5f052892935463ed1c42751e16e2e_f2ecb037818411f180b3525400bff409
    ReservedCode1: X3tQ5tHFxoGO4fmF2Cz4LwutKiSgOLnpBOiJoTqZZ19IVp+zWcUyCwA6flhYp3/QznuEEtbl1sMuOhxq3CgOgktKAHu9EWOevknzrQosfjOzlJWx8zg8CqZ3mQDUyfCrV8kJjwSSe6+vYcFogG3IOcs1OBCug/P4PBHf0Jd/6V2oWifXPeOHlSXiRYk=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: 62a5f052892935463ed1c42751e16e2e_f2ecb037818411f180b3525400bff409
    ReservedCode2: X3tQ5tHFxoGO4fmF2Cz4LwutKiSgOLnpBOiJoTqZZ19IVp+zWcUyCwA6flhYp3/QznuEEtbl1sMuOhxq3CgOgktKAHu9EWOevknzrQosfjOzlJWx8zg8CqZ3mQDUyfCrV8kJjwSSe6+vYcFogG3IOcs1OBCug/P4PBHf0Jd/6V2oWifXPeOHlSXiRYk=
---

# 天意指引（Divine Guidance）功能设计

> 版本：v1.0  
> 日期：2026-07-17  
> 状态：设计中

---

## 一、概述

### 1.1 功能定位

"天意指引"是 DM（地下城主）与单个角色进行超自然对话，并以合理叙事形式融入小说正文的高级干预功能。与现有碰撞引擎（角色间对话）和 DM 指令干预（结构化指令）不同，天意指引聚焦于"天道/命运/天意"与单个角色的心灵交流，DM 扮演天道的角色，通过指引、暗示、警告或预言来影响角色命运。

### 1.2 与现有系统的关系

| 系统 | 交互对象 | 触发方式 | 产物 |
|------|----------|----------|------|
| DialogueSystem | 角色 ↔ 角色 | 自动（距离/事件/随机） | 对话文本 + 关系变化 |
| CollisionEngine | 角色 ↔ 角色 | 位置相同 | 叙事段落 + 目标/关系变化 |
| DM 干预（设计中） | DM → 世界/角色 | DM 手动暂停 | 结构化指令（事件注入/关系修改/目标重定向） |
| **天意指引（本文）** | **DM（天道）→ 单角色** | **DM 暂停 + 选择角色** | **润色后的叙事段落 + 角色记忆/目标变化** |

---

## 二、核心机制

### 2.1 触发方式

```
DM 暂停推演 → 在角色面板中选择目标角色 → 开启"天意对话"面板 → 
输入指引内容 → AI 生成角色响应 → DM 确认融入形式 → 下一章正文中自然融入
```

### 2.2 对话交互模型

DM 以"天道/天意/命运"的身份向角色发话。角色以自身人格、目标、当前心境来接收并响应。

**交互流程：**

1. DM 输入一段话（指引 / 暗示 / 警告 / 预言）
2. 系统构建 prompt（角色设定 + 当前状态 + DM 的天意信息）
3. AI 以角色的视角生成响应（30-80字的合理反应）
4. DM 审核角色响应，不满意可重新生成
5. 选择融入形式 → 确认 → 标记为"待融入"

### 2.3 融入正文的五种叙事形式

对话内容不直接以"天音入耳"形式插入原文，而是由 AI 润色为符合小说世界观的自然叙事。DM 可选择具体形式或让 AI 自动判断：

| 编号 | 融入形式 | 叙事模板 | 适用场景 |
|------|----------|----------|----------|
| F1 | **梦境** | 「当晚，{角色名}做了一个奇怪的梦。梦中{场景描述}，一个声音说：'{指引内容}'。醒来后，{角色名}{角色反应}。」 | 夜间/休息时的指引，适合预言、警告 |
| F2 | **顿悟** | 「{场景描述}间，一道灵光闪过{角色名}的脑海——{指引内容}。{角色名}{角色反应}。」 | 行走/修炼中的灵感，适合暗示、启发 |
| F3 | **天象** | 「{环境描写}。天空中{天象描述}，似乎在预示着什么。{角色名}心中若有所感：{指引内容}。」 | 宏大预言、命运转折、外部征兆 |
| F4 | **偶遇** | 「{场景描述}。路边{路人描述}的一句无心之言，却让{角色名}陷入了沉思：'{指引内容}'。」 | 日常场景中埋藏线索，适合暗示、线索提示 |
| F5 | **内心独白** | 「不知为何，{角色名}心中升起一种莫名的预感——{指引内容}。{角色名}{角色反应}。」 | 内心的直觉、模糊预感，适合轻微指引 |

| 编号 | 融入形式 | 叙事模板 | 适用场景 |
|------|----------|----------|----------|
| F6 | **古籍/遗迹** | 「{角色名}在{地点}偶然发现了一卷古籍/一处遗迹。上面的文字写道：'{指引内容}'。{角色名}{角色反应}。」 | 探索场景，适合世界观揭示、任务提示 |
| F7 | **修炼异象** | 「修炼中，{角色名}体内灵气突然{异象描述}，一段信息莫名浮现于识海：{指引内容}。」 | 修炼突破、功法领悟，适合修为相关指引 |

### 2.4 强度控制

指引的强度控制 AI 生成叙事时的直接程度和确定性：

| 强度 | 标识 | 叙事特征 | 角色响应变化 |
|------|------|----------|--------------|
| **指引 (Guidance)** | ★★★ | 明确的信息，角色清楚知道该做什么 | 目标明确，行动力增强 |
| **暗示 (Hint)** | ★★☆ | 模糊但有指向性，角色需要思考解读 | 产生疑问，可能产生新目标 |
| **模糊预感 (Vague)** | ★☆☆ | 朦胧的感觉，角色不完全确定 | 心境变化，记忆记录，但不一定行动 |

### 2.5 频率限制

防止滥用，确保天意指引保持稀缺性和特殊感：

| 限制维度 | 默认值 | 说明 |
|----------|--------|------|
| 每章最大次数 | 3 | 单章内所有角色的天意指引总数上限 |
| 每角色每章 | 1 | 同一角色每章最多被天意指引一次 |
| 连续章节 | 不允许同一角色连续2章接收指引 | 防止某个角色过度被"天意眷顾" |
| 全局冷却 | 2 次普通碰撞事件 | 两次天意指引之间至少经历一些自然叙事 |

> 频率限制参数可通过 `EngineConfig` 配置，DM 可在游戏启动时调整。

---

## 三、技术设计

### 3.1 DivineGuidanceManager 类

```python
# backend/divine_guidance.py

"""天意指引管理器 —— DM 与角色的超自然对话"""

import json
import time
from dataclasses import dataclass, field
from typing import Optional, List
from enum import Enum


class GuidanceIntensity(Enum):
    """指引强度"""
    GUIDANCE = "guidance"   # 指引：明确信息
    HINT = "hint"           # 暗示：模糊但有指向性
    VAGUE = "vague"         # 模糊预感：朦胧感觉


class IntegrationForm(Enum):
    """融入形式"""
    DREAM = "dream"             # 梦境
    EPIPHANY = "epiphany"       # 顿悟
    CELESTIAL = "celestial"     # 天象
    ENCOUNTER = "encounter"     # 偶遇
    INNER_VOICE = "inner_voice" # 内心独白
    ANCIENT_TEXT = "ancient_text"  # 古籍/遗迹
    CULTIVATION = "cultivation"    # 修炼异象
    AUTO = "auto"               # AI 自动判断


@dataclass
class DivineGuidance:
    """一次天意指引记录"""
    id: str                          # 唯一标识
    character_name: str              # 目标角色
    chapter: int                     # 所在章节
    dm_message: str                  # DM 的原始指引内容
    intensity: GuidanceIntensity     # 指引强度
    character_response: str          # AI 生成的角色响应
    integration_form: IntegrationForm  # 选择的融入形式
    status: str = "pending"          # pending / integrated / cancelled
    created_tick: int = 0
    integrated_tick: int = 0
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "character_name": self.character_name,
            "chapter": self.chapter,
            "dm_message": self.dm_message,
            "intensity": self.intensity.value,
            "character_response": self.character_response,
            "integration_form": self.integration_form.value,
            "status": self.status,
        }


class DivineGuidanceManager:
    """天意指引管理器"""

    INTEGRATION_PROMPTS = {
        IntegrationForm.DREAM: """
【融入形式：梦境】
请将以下天意指引以"梦境"形式融入小说叙事。要求：
- 创建一个合理的梦境场景
- 指引内容通过梦中的声音/画面/象征物传达
- 角色醒来后的反应要符合{intensity}的程度
- 梦境描写控制在80-150字
- 叙事要自然，不刻意，不出现"天意"、"天道"等元叙事词汇

指引内容：{dm_message}
角色当前心境：{character_mood}
""",

        IntegrationForm.EPIPHANY: """
【融入形式：顿悟】
请将以下天意指引以"顿悟/灵光一闪"形式融入小说叙事。要求：
- 描述角色在某个日常场景中突然产生灵感的瞬间
- 指引内容化为角色的内心领悟
- 顿悟的程度要符合{intensity}
- 控制在60-120字
- 叙事要自然，不刻意

指引内容：{dm_message}
角色当前心境：{character_mood}
""",

        IntegrationForm.CELESTIAL: """
【融入形式：天象】
请将以下天意指引以"天象征兆"形式融入小说叙事。要求：
- 描写一个契合世界观的异常天象（流星/异光/云象/星象变化）
- 角色观察天象后内心有所感触
- 天象的明显程度要符合{intensity}
- 控制在80-130字
- 叙事要自然，不刻意

指引内容：{dm_message}
角色当前心境：{character_mood}
世界类型：{world_genre}
""",

        IntegrationForm.ENCOUNTER: """
【融入形式：偶遇】
请将以下天意指引以"偶遇/路人之言"形式融入小说叙事。要求：
- 创建一个自然的偶遇场景（路边老者/旅人/孩童等）
- 指引内容化为路人的一句话或一段对话
- 路人说完后自然离去，不刻意解释身份
- 控制在80-150字
- 叙事要自然，不刻意

指引内容：{dm_message}
角色当前心境：{character_mood}
""",

        IntegrationForm.INNER_VOICE: """
【融入形式：内心独白】
请将以下天意指引以"内心独白/莫名预感"形式融入小说叙事。要求：
- 描述角色心中突然涌现的预感或念头
- 指引内容化为角色内心的直觉
- 预感的模糊程度要符合{intensity}
- 控制在60-100字
- 叙事要自然，不刻意

指引内容：{dm_message}
角色当前心境：{character_mood}
""",

        IntegrationForm.ANCIENT_TEXT: """
【融入形式：古籍/遗迹】
请将以下天意指引以"古籍/遗迹"形式融入小说叙事。要求：
- 描述角色偶然发现古籍/碑文/遗迹的场景
- 指引内容化为古籍上的文字
- 发现过程的偶然性要符合世界观
- 控制在80-150字
- 叙事要自然，不刻意

指引内容：{dm_message}
角色当前心境：{character_mood}
世界类型：{world_genre}
""",

        IntegrationForm.CULTIVATION: """
【融入形式：修炼异象】
请将以下天意指引以"修炼异象"形式融入小说叙事。要求：
- 描述角色修炼时体内出现的异常现象
- 指引内容化为识海中浮现的信息
- 异象的程度要符合{intensity}
- 控制在80-130字
- 叙事要自然，不刻意

指引内容：{dm_message}
角色当前心境：{character_mood}
""",
    }

    def __init__(self, ai_client=None, config: dict = None):
        self.ai = ai_client
        self.config = config or {}
        self.guidance_history: List[DivineGuidance] = []
        self._guidance_counter = 0

        # 频率限制配置
        self.max_per_chapter = self.config.get("max_per_chapter", 3)
        self.max_per_character_per_chapter = self.config.get("max_per_character_per_chapter", 1)
        self.consecutive_chapter_cooldown = self.config.get("consecutive_chapter_cooldown", True)

        # 角色章节使用记录: {角色名: [使用过的章节号]}
        self._character_chapter_usage: dict[str, list[int]] = {}

    def check_availability(
        self,
        character_name: str,
        chapter: int,
    ) -> tuple[bool, str]:
        """
        检查是否可以对指定角色发起天意指引

        Returns:
            (是否可用, 不可用原因)
        """
        # 检查本章总次数
        chapter_count = sum(
            1 for g in self.guidance_history
            if g.chapter == chapter and g.status != "cancelled"
        )
        if chapter_count >= self.max_per_chapter:
            return False, f"本章天意指引已达上限（{self.max_per_chapter}次）"

        # 检查该角色本章次数
        char_chapter_count = sum(
            1 for g in self.guidance_history
            if g.character_name == character_name
            and g.chapter == chapter
            and g.status != "cancelled"
        )
        if char_chapter_count >= self.max_per_character_per_chapter:
            return False, f"角色「{character_name}」本章已接收天意指引"

        # 检查连续章节限制
        if self.consecutive_chapter_cooldown and chapter > 1:
            prev_chapter = chapter - 1
            char_prev = any(
                g.character_name == character_name
                and g.chapter == prev_chapter
                and g.status == "integrated"
                for g in self.guidance_history
            )
            if char_prev:
                return False, f"角色「{character_name}」上一章已接收天意指引，本章不可连续使用"

        return True, ""

    def generate_character_response(
        self,
        character,
        dm_message: str,
        intensity: GuidanceIntensity,
    ) -> str:
        """
        以角色的视角生成对天意指引的响应

        Args:
            character: CharacterAgent 实例
            dm_message: DM 的指引内容
            intensity: 指引强度

        Returns:
            角色响应文本（30-80字）
        """
        intensity_hints = {
            GuidanceIntensity.GUIDANCE: "你清楚地接收到了这个信息，明确知道这意味着什么",
            GuidanceIntensity.HINT: "你收到了一个模糊的信息，觉得其中必有深意，但还需要思考",
            GuidanceIntensity.VAGUE: "你只是有一种朦胧的感觉，不太确定这意味着什么",
        }

        prompt = f"""【天意指引 - 角色响应】

你正在扮演{character.name}。以下是你的基本设定和当前状态：

{character.full_state_text()}

---
突然之间，你感受到了一股来自天地的意志——不是任何人的声音，而是一种超越凡俗的感应。

指引内容：{dm_message}

{intensity_hints.get(intensity, "")}

请以{character.name}的第一人称视角，描述你接收这个指引后内心的反应和想法。
要求：
- 字数30-80字
- 符合你的性格和当前心境
- 直接输出角色内心反应，不要加"角色名："前缀
- 不要出现"天道"、"天意"等打破第四面墙的词汇
- 自然、真实、沉浸
"""

        if self.ai and hasattr(self.ai, 'is_available') and self.ai.is_available:
            try:
                response = self.ai.generate(prompt, max_tokens=200)
                if response:
                    return response.strip()
            except Exception:
                pass

        # Fallback
        return f"{character.name}心头一震，似乎冥冥中有所感应，却说不清道不明。"

    def generate_narrative_integration(
        self,
        guidance: DivineGuidance,
        character,
        world,
    ) -> str:
        """
        生成融入正文的叙事段落

        Args:
            guidance: 天意指引记录
            character: CharacterAgent 实例
            world: World 实例

        Returns:
            润色后的叙事段落（80-200字）
        """
        # 如果选择 AUTO，由 AI 自动选择最合适的形式
        if guidance.integration_form == IntegrationForm.AUTO:
            guidance.integration_form = self._auto_select_form(
                guidance.dm_message,
                guidance.intensity,
                character,
            )

        form = guidance.integration_form
        template = self.INTEGRATION_PROMPTS.get(form, self.INTEGRATION_PROMPTS[IntegrationForm.INNER_VOICE])

        prompt = template.format(
            dm_message=guidance.dm_message,
            character_mood=character.current_mood,
            intensity=guidance.intensity.value,
            world_genre=world.config.genre if world else "玄幻",
        )

        if self.ai and hasattr(self.ai, 'is_available') and self.ai.is_available:
            try:
                response = self.ai.generate(prompt, max_tokens=400)
                if response:
                    return response.strip()
            except Exception:
                pass

        # Fallback
        return self._fallback_narrative(guidance, character)

    def _auto_select_form(
        self,
        dm_message: str,
        intensity: GuidanceIntensity,
        character,
    ) -> IntegrationForm:
        """AI 自动选择最合适的融入形式"""
        # 基于简单的关键词启发式规则
        msg_lower = dm_message.lower()

        if any(kw in msg_lower for kw in ["修炼", "突破", "功法", "灵气", "丹田", "境界"]):
            return IntegrationForm.CULTIVATION
        if any(kw in msg_lower for kw in ["预言", "灾难", "大劫", "命运", "星象"]):
            return IntegrationForm.CELESTIAL
        if any(kw in msg_lower for kw in ["遗产", "秘典", "古", "传承", "遗迹"]):
            return IntegrationForm.ANCIENT_TEXT
        if intensity == GuidanceIntensity.GUIDANCE:
            return IntegrationForm.DREAM
        if intensity == GuidanceIntensity.HINT:
            return IntegrationForm.ENCOUNTER
        return IntegrationForm.INNER_VOICE

    def _fallback_narrative(self, guidance: DivineGuidance, character) -> str:
        """Fallback 叙事模板"""
        templates = {
            IntegrationForm.DREAM:
                f"当晚，{character.name}做了一个奇怪的梦。梦中似乎有人在低语，但醒来后只记得一种模糊的感觉——{guidance.dm_message[:50]}。",
            IntegrationForm.EPIPHANY:
                f"{character.name}心中忽然涌起一个念头：{guidance.dm_message[:50]}。这念头来得毫无缘由，却又挥之不去。",
            IntegrationForm.CELESTIAL:
                f"夜空中一道异光掠过。{character.name}心中一动，似乎感应到了什么——{guidance.dm_message[:50]}。",
            IntegrationForm.ENCOUNTER:
                f"路旁一位老者的无心之言飘入耳中，{character.name}不禁驻足——{guidance.dm_message[:50]}。",
            IntegrationForm.INNER_VOICE:
                f"不知为何，{character.name}心中升起一种莫名的预感——{guidance.dm_message[:50]}。",
            IntegrationForm.ANCIENT_TEXT:
                f"在一处不起眼的角落，{character.name}发现了一卷残破古籍，上面依稀写着：{guidance.dm_message[:50]}。",
            IntegrationForm.CULTIVATION:
                f"修炼中，{character.name}识海中忽然浮现一段信息：{guidance.dm_message[:50]}。",
        }
        return templates.get(guidance.integration_form, templates[IntegrationForm.INNER_VOICE])

    def create_guidance(
        self,
        character_name: str,
        chapter: int,
        dm_message: str,
        intensity: GuidanceIntensity,
        character_response: str,
        integration_form: IntegrationForm,
    ) -> DivineGuidance:
        """创建一条天意指引记录"""
        self._guidance_counter += 1
        guidance = DivineGuidance(
            id=f"dg_{chapter}_{self._guidance_counter}",
            character_name=character_name,
            chapter=chapter,
            dm_message=dm_message,
            intensity=intensity,
            character_response=character_response,
            integration_form=integration_form,
            status="pending",
        )
        self.guidance_history.append(guidance)
        return guidance

    def apply_to_character(self, guidance: DivineGuidance, character):
        """
        将天意指引的效果应用到角色（更新记忆、可能更新目标）
        """
        # 记录记忆
        memory_content = f"感受到天意：{guidance.dm_message[:60]}"
        character.remember("天意", memory_content)

        # 根据强度可能影响目标
        if guidance.intensity == GuidanceIntensity.GUIDANCE:
            # 明确指引 → 可能产生新短期目标
            character.add_goal(
                description=f"遵循指引：{guidance.dm_message[:40]}",
                priority=8,
            )

        elif guidance.intensity == GuidanceIntensity.HINT:
            # 暗示 → 记录但不一定产生目标
            character.current_mood = "若有所思"

        elif guidance.intensity == GuidanceIntensity.VAGUE:
            # 模糊预感 → 仅影响心境
            pass

    def get_pending_guidances(self, chapter: int = None) -> List[DivineGuidance]:
        """获取待融入的天意指引"""
        result = [
            g for g in self.guidance_history
            if g.status == "pending"
            and (chapter is None or g.chapter == chapter)
        ]
        return result

    def mark_integrated(self, guidance_id: str):
        """标记为已融入"""
        for g in self.guidance_history:
            if g.id == guidance_id:
                g.status = "integrated"
                break

    def get_chapter_summary(self, chapter: int) -> str:
        """获取某章的天意指引摘要（用于叙事 prompt）"""
        pendings = self.get_pending_guidances(chapter)
        if not pendings:
            return ""

        lines = ["## 天意指引（需融入本章正文）"]
        for g in pendings:
            lines.append(
                f"- 目标角色：{g.character_name}\n"
                f"  指引内容：{g.dm_message}\n"
                f"  融入形式：{g.integration_form.value}\n"
                f"  已生成的叙事段落：\n{g.generate_narrative_integration(g, ...)}"
            )
        return "\n\n".join(lines)
```

### 3.2 与现有引擎的集成

#### 3.2.1 GameEngine 改造

在 `backend/engine.py` 的 `GameEngine` 中集成天意指引：

```python
# backend/engine.py 新增集成点

class GameEngine:
    def __init__(self):
        # ... 现有初始化 ...
        from .divine_guidance import DivineGuidanceManager
        self.divine_guidance = DivineGuidanceManager(ai_client=_client)

    def run_chapter(self, title: str = "") -> dict:
        # ... 步骤1-3 保持不变 ...

        # 步骤3.5：获取待融入的天意指引叙事段落
        divine_narratives = []
        pending_guidances = self.divine_guidance.get_pending_guidances(
            self.world.current_chapter
        )
        for guidance in pending_guidances:
            char = self._get_character(guidance.character_name)
            if char:
                narrative = self.divine_guidance.generate_narrative_integration(
                    guidance, char, self.world
                )
                divine_narratives.append({
                    "character": guidance.character_name,
                    "form": guidance.integration_form.value,
                    "narrative": narrative,
                })
                # 应用效果到角色
                self.divine_guidance.apply_to_character(guidance, char)
                self.divine_guidance.mark_integrated(guidance.id)

        # 步骤4：生成章节正文时，将天意叙事作为额外素材传入
        narrative = self.narrative_generator.generate_chapter(
            self.world, self.characters, character_actions, title,
            divine_narratives=divine_narratives,  # 新增参数
        )
        # ...
```

#### 3.2.2 NarrativeGenerator 改造

在 `backend/narrative.py` 的叙事生成 prompt 中融入天意指引段落：

```python
# backend/narrative.py

class NarrativeGenerator:
    def generate_chapter(
        self,
        world: World,
        characters: list[CharacterAgent],
        character_actions: dict[str, str],
        title: str = "",
        divine_narratives: list[dict] = None,  # 新增参数
    ) -> str:
        # ... 构建 action_summaries ...

        # 构建天意叙事部分
        divine_section = ""
        if divine_narratives:
            divine_section = "\n## 需要融入的天意叙事段落\n"
            divine_section += "请将以下段落自然地编织到本章叙事中，不要原样照抄，而是作为叙事的一部分自然融入：\n"
            for i, dn in enumerate(divine_narratives):
                divine_section += f"\n{i+1}. [角色：{dn['character']}，形式：{dn['form']}]\n{dn['narrative']}\n"

        prompt = f"""请作为小说作者，根据以下素材撰写第{world.current_chapter}章的正文。

## 本章标题
{title or f'第{world.current_chapter}章'}

## 角色行动
{chr(10).join(action_summaries)}

## 世界事件
{world.recent_events()}
{divine_section}

## 叙事要求
1. 小说的叙事基调：{world.config.tone}
2. 字数在800-1500字之间
3. 不要使用'本章讲述'等元叙事
4. 场景描写要生动，对话要自然
5. 结尾要有悬念或下一步的暗示
6. 如果提供了天意叙事段落，请在合适的位置自然融入，不要标注来源
"""
        # ...
```

### 3.3 REST API 设计

在 `app.py` 中新增以下端点：

```python
# 天意指引 API

@app.route("/api/divine-guidance/check", methods=["POST"])
def api_divine_guidance_check():
    """检查是否可以对某角色发起天意指引"""
    data = request.get_json() or {}
    character_name = data.get("character_name", "")
    if not character_name:
        return jsonify({"error": "缺少角色名称"}), 400

    available, reason = engine.divine_guidance.check_availability(
        character_name, engine.world.current_chapter
    )
    return jsonify({
        "available": available,
        "reason": reason,
        "chapter": engine.world.current_chapter,
        "stats": {
            "chapter_used": sum(1 for g in engine.divine_guidance.guidance_history if g.chapter == engine.world.current_chapter and g.status != "cancelled"),
            "chapter_max": engine.divine_guidance.max_per_chapter,
        }
    })


@app.route("/api/divine-guidance/respond", methods=["POST"])
def api_divine_guidance_respond():
    """生成角色对天意指引的响应"""
    data = request.get_json() or {}
    character_name = data.get("character_name", "")
    dm_message = data.get("message", "")
    intensity = data.get("intensity", "hint")

    if not character_name or not dm_message:
        return jsonify({"error": "缺少必要参数"}), 400

    # 查找角色
    char = next((c for c in engine.characters if c.name == character_name), None)
    if not char:
        return jsonify({"error": f"未找到角色：{character_name}"}), 404

    intensity_enum = GuidanceIntensity(intensity)
    response = engine.divine_guidance.generate_character_response(
        char, dm_message, intensity_enum
    )
    return jsonify({
        "character_name": character_name,
        "response": response,
    })


@app.route("/api/divine-guidance/integrate", methods=["POST"])
def api_divine_guidance_integrate():
    """预览融入效果（生成叙事段落）"""
    data = request.get_json() or {}
    character_name = data.get("character_name", "")
    dm_message = data.get("message", "")
    integration_form = data.get("integration_form", "auto")
    intensity = data.get("intensity", "hint")
    character_response = data.get("character_response", "")

    char = next((c for c in engine.characters if c.name == character_name), None)
    if not char:
        return jsonify({"error": f"未找到角色：{character_name}"}), 404

    # 创建临时指引记录用于生成预览
    temp_guidance = DivineGuidance(
        id="preview",
        character_name=character_name,
        chapter=engine.world.current_chapter,
        dm_message=dm_message,
        intensity=GuidanceIntensity(intensity),
        character_response=character_response,
        integration_form=IntegrationForm(integration_form),
    )

    narrative = engine.divine_guidance.generate_narrative_integration(
        temp_guidance, char, engine.world
    )
    return jsonify({
        "narrative": narrative,
        "integration_form": integration_form,
    })


@app.route("/api/divine-guidance/confirm", methods=["POST"])
def api_divine_guidance_confirm():
    """确认天意指引，标记为待融入"""
    data = request.get_json() or {}
    character_name = data.get("character_name", "")
    dm_message = data.get("message", "")
    intensity = data.get("intensity", "hint")
    character_response = data.get("character_response", "")
    integration_form = data.get("integration_form", "auto")

    guidance = engine.divine_guidance.create_guidance(
        character_name=character_name,
        chapter=engine.world.current_chapter,
        dm_message=dm_message,
        intensity=GuidanceIntensity(intensity),
        character_response=character_response,
        integration_form=IntegrationForm(integration_form),
    )
    return jsonify({
        "status": "ok",
        "guidance": guidance.to_dict(),
    })


@app.route("/api/divine-guidance/history", methods=["GET"])
def api_divine_guidance_history():
    """获取天意指引历史"""
    chapter = request.args.get("chapter", type=int)
    guidances = [
        g.to_dict() for g in engine.divine_guidance.guidance_history
        if chapter is None or g.chapter == chapter
    ]
    return jsonify({"guidances": guidances})
```

### 3.4 DM 面板前端设计

在游戏主界面的右侧面板（角色状态区）中，为每个角色新增"天意对话"按钮：

```
┌─────────────────────────────────┐
│  角色状态                       │
│                                 │
│  ┌─────────────────────────┐   │
│  │ 李青云  [天意对话] [状态]│   │
│  │ 位置：青云宗              │   │
│  │ 心情：平静                │   │
│  │ 目标：...                 │   │
│  └─────────────────────────┘   │
│                                 │
│  ┌─────────────────────────┐   │
│  │ 魔尊玄冥  [天意对话]     │   │
│  │ ...                      │   │
│  └─────────────────────────┘   │
└─────────────────────────────────┘
```

点击"天意对话"后弹出模态面板：

```
┌──────────────────────────────────────┐
│  天意指引 - 李青云               [X] │
│                                      │
│  ── 你的指引 ──                      │
│  ┌──────────────────────────────┐   │
│  │ 输入你想传达给角色的指引、暗 │   │
│  │ 示、警告或预言...            │   │
│  │                              │   │
│  └──────────────────────────────┘   │
│                                      │
│  指引强度：  ○ 指引  ● 暗示  ○ 模糊预感│
│                                      │
│  [生成角色响应]                      │
│                                      │
│  ── 角色响应 ──                       │
│  ┌──────────────────────────────┐   │
│  │ "心头一震，这感觉如此熟悉..."│   │
│  └──────────────────────────────┘   │
│                                      │
│  融入形式：                          │
│  ○ 梦境  ● 顿悟  ○ 天象             │
│  ○ 偶遇  ○ 内心独白  ○ 古籍         │
│  ○ 修炼异象  ○ AI自动判断           │
│                                      │
│  [预览融入效果]                      │
│                                      │
│  ── 融入预览 ──                       │
│  ┌──────────────────────────────┐   │
│  │ 行走在山路上，一道灵光闪过... │   │
│  └──────────────────────────────┘   │
│                                      │
│  [确认融入]  [取消]                 │
│                                      │
│  本章已用 1/3 次                     │
└──────────────────────────────────────┘
```

### 3.5 融入正文的 Prompt 设计

#### 3.5.1 总体原则

天意叙事段落作为"高级素材"传给叙事生成器，AI 需要在综合角色行动、碰撞事件的基础上，自然地插入天意段落。关键要求：

1. **无缝融入**：不标注来源，不出现"天道"、"天意"等元叙事词汇
2. **时机自然**：选择合理的叙事节奏点插入（如过渡段、场景切换处）
3. **比例适当**：天意段落不超过全文 20%
4. **角色反应一致**：角色对话语和行为需与之前的天意指引响应一致

#### 3.5.2 叙事生成 Prompt 增强

在 `NarrativeGenerator.generate_chapter()` 中：

```
## 天意叙事融入指南

你需要在本章叙事中自然融入以下天意叙事段落。融入原则：
1. 不要原样照抄这些段落，而是将其作为"素材"进行二次创作
2. 选择合适的叙事节奏点：过渡段、独处时刻、场景切换处
3. 融入后的段落应与其他叙事无缝衔接，读者不应察觉"拼接"痕迹
4. 天意叙事的总字数不超过全文的20%
5. 融入后角色在后续叙事中的行为，应与天意指引的内容保持一致性
```

---

## 四、数据流与生命周期

### 4.1 完整时序图

```
DM                   前端                  API                    GameEngine           AI
│                    │                     │                     │                    │
│  点击"天意对话"    │                     │                     │                    │
│ ─────────────────>│                     │                     │                    │
│                    │ GET /divine-guidance│                     │                    │
│                    │ /check              │                     │                    │
│                    │ ──────────────────>│                     │                    │
│                    │                     │ check_availability  │                    │
│                    │                     │ ──────────────────>│                    │
│                    │                     │ <── (available=True)│                    │
│                    │ <── {available:true}│                     │                    │
│                    │                     │                     │                    │
│  输入指引内容       │                     │                     │                    │
│ ─────────────────>│                     │                     │                    │
│                    │ POST /divine-guidance│                    │                    │
│                    │ /respond            │                     │                    │
│                    │ ──────────────────>│                     │                    │
│                    │                     │ generate_character_ │                    │
│                    │                     │ response()          │ chat()             │
│                    │                     │ ──────────────────────────────────────>│
│                    │                     │ <── 角色响应 ─────────────────────────│
│                    │ <── {response: ...} │                     │                    │
│                    │                     │                     │                    │
│  选择融入形式       │                     │                     │                    │
│ ─────────────────>│                     │                     │                    │
│                    │ POST /divine-guidance│                    │                    │
│                    │ /integrate (预览)    │                     │                    │
│                    │ ──────────────────>│                     │                    │
│                    │                     │ generate_narrative_ │                    │
│                    │                     │ integration()       │ chat()             │
│                    │                     │ ──────────────────────────────────────>│
│                    │                     │ <── 融入叙事段落 ──────────────────────│
│                    │ <── {narrative: ...}│                     │                    │
│                    │                     │                     │                    │
│  DM审核，确认融入    │                     │                     │                    │
│ ─────────────────>│                     │                     │                    │
│                    │ POST /divine-guidance│                    │                    │
│                    │ /confirm            │                     │                    │
│                    │ ──────────────────>│                     │                    │
│                    │                     │ create_guidance()   │                    │
│                    │                     │ ──────────────────>│                    │
│                    │ <── {status:"ok"}   │                     │                    │
│                    │                     │                     │                    │
│  ===== 稍后：DM 推演下一章 =====         │                     │                    │
│                    │                     │                     │                    │
│                    │ POST /api/chapter   │                     │                    │
│                    │ ──────────────────>│                     │                    │
│                    │                     │ run_chapter()       │                    │
│                    │                     │  ├ 获取待融入的      │                    │
│                    │                     │  │ divine_narratives │                    │
│                    │                     │  ├ apply_to_character│                    │
│                    │                     │  ├ mark_integrated  │                    │
│                    │                     │  └ generate_chapter │ chat()             │
│                    │                     │    (含天意叙事)     │ ──────────────────>│
│                    │                     │                     │ <── 完整章节正文 ──│
│                    │ <── {chapter: ...}  │                     │                    │
│                    │                     │                     │                    │
```

### 4.2 存档兼容

天意指引记录随 `GameEngine` 序列化（`guidance_history` 字段），存档/读档时完整保存和恢复。`divine_guidance` 作为 `GameEngine` 的属性，在 `Storage.save()` / `Storage.load()` 中一并处理。

---

## 五、与 DMManager 的关系

"天意指引"是 DM 干预体系的一个子模块，与现有的 DM 模式设计（`dm_mode_and_timeline_check_design_v2.md`）的关系如下：

| DM 干预类型 | 触发时机 | 作用对象 | 融入方式 |
|-------------|----------|----------|----------|
| 角色行动干预 | 暂停时 | 单个角色 | 直接修改角色行动 |
| 世界事件注入 | 暂停时 | 世界 | 新增世界事件 |
| 关系修改 | 暂停时 | 角色间 | 直接修改关系数据 |
| 目标重定向 | 暂停时 | 单个角色 | 直接修改目标 |
| **天意指引** | **暂停时** | **单角色（叙事层）** | **AI 润色后融入正文** |
| 叙事风格调整 | 暂停时 | 全局 | 修改叙事参数 |

天意指引与其他 DM 干预的核心区别在于：**它操作的是"叙事层"而非"数据层"**。它不是直接改角色的目标或关系，而是通过一段精心设计的叙事段落来间接影响角色的行为和命运，保留了小说的文学性和自然感。

---

## 六、实现优先级

| 阶段 | 内容 | 说明 |
|------|------|------|
| Phase 1 | `DivineGuidanceManager` 核心类 + API 端点 | 后端核心逻辑，独立可测 |
| Phase 2 | `NarrativeGenerator` 集成 | 叙事生成 prompt 增强 |
| Phase 3 | 前端天意对话面板 | DM 交互界面 |
| Phase 4 | 频率限制 + 存档兼容 | 完善边界处理 |
| Phase 5 | AUTO 模式的 AI 自动选择融入形式 | 智能判断最优形式 |

---

*设计完成。*
*（内容由AI生成，仅供参考）*
