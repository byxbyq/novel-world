# -*- coding: utf-8 -*-
"""
复杂命运线系统 - 处理多阶段任务、命运线、冲突等

优化内容：
1. 奖励类型系统 - 物品、属性、关系、剧情解锁等
2. 奖励发放机制 - 自动发放任务奖励
3. 奖励通知系统 - 明确告知用户奖励内容
"""
import random
import logging
import time
from typing import List, Dict, Optional, Tuple, Any, Callable, Union
from dataclasses import dataclass, field
from enum import Enum
from collections import deque

logger = logging.getLogger(__name__)


# ============================================================
# 奖励类型
# ============================================================
class RewardType(Enum):
    """奖励类型"""
    ITEM = "item"                   # 物品
    GOLD = "gold"                   # 金币
    EXPERIENCE = "experience"       # 经验值
    ATTRIBUTE = "attribute"         # 属性提升
    SKILL = "skill"                 # 技能
    RELATIONSHIP = "relationship"   # 关系改善
    FATE_UNLOCK = "fate_unlock"     # 解锁命运线
    AREA_UNLOCK = "area_unlock"     # 解锁区域
    TITLE = "title"                 # 称号
    ACHIEVEMENT = "achievement"     # 成就
    CUSTOM = "custom"               # 自定义


# ============================================================
# 奖励数据结构
# ============================================================
@dataclass
class Reward:
    """奖励"""
    type: RewardType
    name: str                       # 奖励名称
    value: Union[int, float, str]   # 奖励值（数量/属性名/命运线ID等）
    target: Optional[str] = None    # 目标（角色/关系对象等）
    description: str = ""           # 描述
    
    def to_dict(self) -> Dict:
        return {
            "type": self.type.value,
            "name": self.name,
            "value": self.value,
            "target": self.target,
            "description": self.description,
        }
    
    @classmethod
    def from_dict(cls, d: Dict) -> 'Reward':
        return cls(
            type=RewardType(d["type"]),
            name=d["name"],
            value=d["value"],
            target=d.get("target"),
            description=d.get("description", ""),
        )
    
    def get_display_text(self) -> str:
        """获取显示文本"""
        if self.type == RewardType.ITEM:
            return f"获得物品【{self.name}】x{self.value}"
        elif self.type == RewardType.GOLD:
            return f"获得金币 {self.value} 枚"
        elif self.type == RewardType.EXPERIENCE:
            return f"获得经验值 {self.value}"
        elif self.type == RewardType.ATTRIBUTE:
            return f"{self.name} +{self.value}"
        elif self.type == RewardType.SKILL:
            return f"习得技能【{self.name}】"
        elif self.type == RewardType.RELATIONSHIP:
            return f"与【{self.target}】的关系改善了"
        elif self.type == RewardType.FATE_UNLOCK:
            return f"解锁命运线【{self.name}】"
        elif self.type == RewardType.AREA_UNLOCK:
            return f"解锁区域【{self.name}】"
        elif self.type == RewardType.TITLE:
            return f"获得称号【{self.name}】"
        elif self.type == RewardType.ACHIEVEMENT:
            return f"达成成就【{self.name}】"
        else:
            return self.description or f"获得 {self.name}"


# ============================================================
# 奖励发放结果
# ============================================================
@dataclass
class RewardResult:
    """奖励发放结果"""
    success: bool
    reward: Reward
    actual_value: Any = None        # 实际发放的值
    message: str = ""
    timestamp: float = field(default_factory=time.time)


# ============================================================
# 奖励管理器
# ============================================================
class RewardManager:
    """奖励管理器"""
    
    def __init__(self):
        # 奖励处理器
        self._handlers: Dict[RewardType, Callable] = {}
        
        # 奖励历史
        self._reward_history: List[RewardResult] = []
        self._max_history = 1000
        
        # 待领取奖励
        self._pending_rewards: Dict[str, List[Reward]] = {}  # 角色ID -> 奖励列表
        
        # 通知回调
        self._notification_callbacks: List[Callable] = []
        
        # 注册默认处理器
        self._register_default_handlers()
    
    def _register_default_handlers(self):
        """注册默认处理器"""
        self._handlers[RewardType.ITEM] = self._handle_item
        self._handlers[RewardType.GOLD] = self._handle_gold
        self._handlers[RewardType.EXPERIENCE] = self._handle_experience
        self._handlers[RewardType.ATTRIBUTE] = self._handle_attribute
        self._handlers[RewardType.SKILL] = self._handle_skill
        self._handlers[RewardType.RELATIONSHIP] = self._handle_relationship
        self._handlers[RewardType.FATE_UNLOCK] = self._handle_fate_unlock
        self._handlers[RewardType.AREA_UNLOCK] = self._handle_area_unlock
        self._handlers[RewardType.TITLE] = self._handle_title
        self._handlers[RewardType.ACHIEVEMENT] = self._handle_achievement
        self._handlers[RewardType.CUSTOM] = self._handle_custom
    
    def register_handler(self, reward_type: RewardType, handler: Callable):
        """注册自定义处理器"""
        self._handlers[reward_type] = handler
    
    def add_notification_callback(self, callback: Callable):
        """添加通知回调"""
        self._notification_callbacks.append(callback)
    
    def grant_reward(
        self,
        reward: Reward,
        character_id: str,
        immediate: bool = True
    ) -> RewardResult:
        """
        发放奖励
        
        Args:
            reward: 奖励
            character_id: 角色ID
            immediate: 是否立即发放
        
        Returns:
            发放结果
        """
        if not immediate:
            # 添加到待领取列表
            if character_id not in self._pending_rewards:
                self._pending_rewards[character_id] = []
            self._pending_rewards[character_id].append(reward)
            
            return RewardResult(
                success=True,
                reward=reward,
                message=f"奖励已添加到待领取列表",
            )
        
        # 获取处理器
        handler = self._handlers.get(reward.type)
        if handler is None:
            result = RewardResult(
                success=False,
                reward=reward,
                message=f"未知的奖励类型: {reward.type}",
            )
        else:
            try:
                # 执行处理
                actual_value, message = handler(reward, character_id)
                
                result = RewardResult(
                    success=True,
                    reward=reward,
                    actual_value=actual_value,
                    message=message,
                )
                
                logger.info(f"Reward granted: {reward.get_display_text()} to {character_id}")
                
            except Exception as e:
                result = RewardResult(
                    success=False,
                    reward=reward,
                    message=f"发放失败: {e}",
                )
                logger.error(f"Failed to grant reward: {e}")
        
        # 记录历史
        self._reward_history.append(result)
        if len(self._reward_history) > self._max_history:
            self._reward_history = self._reward_history[-self._max_history:]
        
        # 发送通知
        self._send_notification(result, character_id)
        
        return result
    
    def grant_rewards(
        self,
        rewards: List[Reward],
        character_id: str,
        immediate: bool = True
    ) -> List[RewardResult]:
        """批量发放奖励"""
        return [self.grant_reward(r, character_id, immediate) for r in rewards]
    
    def claim_pending_rewards(self, character_id: str) -> List[RewardResult]:
        """领取待领取的奖励"""
        if character_id not in self._pending_rewards:
            return []
        
        rewards = self._pending_rewards.pop(character_id)
        return self.grant_rewards(rewards, character_id, immediate=True)
    
    def get_pending_rewards(self, character_id: str) -> List[Reward]:
        """获取待领取的奖励"""
        return self._pending_rewards.get(character_id, [])
    
    def _send_notification(self, result: RewardResult, character_id: str):
        """发送通知"""
        for callback in self._notification_callbacks:
            try:
                callback(result, character_id)
            except Exception as e:
                logger.error(f"Notification callback error: {e}")
    
    # ==================== 默认处理器 ====================
    
    def _handle_item(self, reward: Reward, character_id: str) -> Tuple[Any, str]:
        """处理物品奖励"""
        # 这里应该调用物品系统添加物品
        # 返回: (实际添加的数量, 消息)
        item_name = reward.name
        quantity = int(reward.value)
        
        # 示例：记录到日志
        logger.debug(f"Adding item {item_name} x{quantity} to {character_id}")
        
        return quantity, f"获得 {item_name} x{quantity}"
    
    def _handle_gold(self, reward: Reward, character_id: str) -> Tuple[Any, str]:
        """处理金币奖励"""
        amount = int(reward.value)
        logger.debug(f"Adding {amount} gold to {character_id}")
        return amount, f"获得金币 {amount} 枚"
    
    def _handle_experience(self, reward: Reward, character_id: str) -> Tuple[Any, str]:
        """处理经验值奖励"""
        exp = int(reward.value)
        logger.debug(f"Adding {exp} experience to {character_id}")
        return exp, f"获得经验值 {exp}"
    
    def _handle_attribute(self, reward: Reward, character_id: str) -> Tuple[Any, str]:
        """处理属性提升奖励"""
        attr_name = reward.name
        value = float(reward.value)
        logger.debug(f"Increasing {attr_name} by {value} for {character_id}")
        return value, f"{attr_name} +{value}"
    
    def _handle_skill(self, reward: Reward, character_id: str) -> Tuple[Any, str]:
        """处理技能奖励"""
        skill_name = reward.name
        logger.debug(f"Granting skill {skill_name} to {character_id}")
        return skill_name, f"习得技能【{skill_name}】"
    
    def _handle_relationship(self, reward: Reward, character_id: str) -> Tuple[Any, str]:
        """处理关系改善奖励"""
        target = reward.target
        improvement = float(reward.value)
        logger.debug(f"Improving relationship between {character_id} and {target} by {improvement}")
        return improvement, f"与【{target}】的关系改善了"
    
    def _handle_fate_unlock(self, reward: Reward, character_id: str) -> Tuple[Any, str]:
        """处理命运线解锁奖励"""
        fate_id = str(reward.value)
        logger.debug(f"Unlocking fate {fate_id} for {character_id}")
        return fate_id, f"解锁命运线【{reward.name}】"
    
    def _handle_area_unlock(self, reward: Reward, character_id: str) -> Tuple[Any, str]:
        """处理区域解锁奖励"""
        area_name = reward.name
        logger.debug(f"Unlocking area {area_name} for {character_id}")
        return area_name, f"解锁区域【{area_name}】"
    
    def _handle_title(self, reward: Reward, character_id: str) -> Tuple[Any, str]:
        """处理称号奖励"""
        title_name = reward.name
        logger.debug(f"Granting title {title_name} to {character_id}")
        return title_name, f"获得称号【{title_name}】"
    
    def _handle_achievement(self, reward: Reward, character_id: str) -> Tuple[Any, str]:
        """处理成就奖励"""
        achievement_name = reward.name
        logger.debug(f"Achievement {achievement_name} unlocked for {character_id}")
        return achievement_name, f"达成成就【{achievement_name}】"
    
    def _handle_custom(self, reward: Reward, character_id: str) -> Tuple[Any, str]:
        """处理自定义奖励"""
        return reward.value, reward.description or f"获得 {reward.name}"
    
    # ==================== 查询方法 ====================
    
    def get_reward_history(self, limit: int = 100) -> List[RewardResult]:
        """获取奖励历史"""
        return self._reward_history[-limit:]
    
    def get_character_rewards(self, character_id: str, limit: int = 50) -> List[RewardResult]:
        """获取角色的奖励历史"""
        # 这里简化处理，实际应该按角色过滤
        return self._reward_history[-limit:]
    
    def get_statistics(self) -> Dict:
        """获取统计信息"""
        total = len(self._reward_history)
        success = sum(1 for r in self._reward_history if r.success)
        
        by_type = {}
        for result in self._reward_history:
            if result.success:
                t = result.reward.type.value
                by_type[t] = by_type.get(t, 0) + 1
        
        return {
            "total_rewards": total,
            "successful_rewards": success,
            "failed_rewards": total - success,
            "by_type": by_type,
            "pending_count": sum(len(r) for r in self._pending_rewards.values()),
        }


# ============================================================
# 命运阶段和任务状态
# ============================================================
class FateStage(Enum):
    """命运阶段"""
    INTRO = "开端"
    RISING = "上升"
    CLIMAX = "高潮"
    FALLING = "下降"
    RESOLUTION = "结局"


class TaskStatus(Enum):
    """任务状态"""
    PENDING = "待处理"
    IN_PROGRESS = "进行中"
    COMPLETED = "已完成"
    FAILED = "失败"
    ABANDONED = "放弃"


# ============================================================
# 命运任务
# ============================================================
@dataclass
class FateTask:
    """命运任务"""
    id: str
    character: str
    title: str
    description: str
    stages: List[str]
    current_stage: int = 0
    status: TaskStatus = TaskStatus.PENDING
    progress: float = 0.0
    
    # 奖励（结构化）
    rewards: List[Reward] = field(default_factory=list)
    
    # 失败后果
    consequences: List[str] = field(default_factory=list)
    
    # 截止时间
    deadline: int = 0
    
    # 奖励是否已发放
    rewards_granted: bool = False
    
    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "character": self.character,
            "title": self.title,
            "description": self.description,
            "stages": self.stages,
            "current_stage": self.current_stage,
            "status": self.status.value,
            "progress": self.progress,
            "rewards": [r.to_dict() for r in self.rewards],
            "consequences": self.consequences,
            "deadline": self.deadline,
            "rewards_granted": self.rewards_granted,
        }
    
    @classmethod
    def from_dict(cls, d: Dict) -> 'FateTask':
        return cls(
            id=d["id"],
            character=d["character"],
            title=d["title"],
            description=d["description"],
            stages=d["stages"],
            current_stage=d["current_stage"],
            status=TaskStatus(d["status"]),
            progress=d["progress"],
            rewards=[Reward.from_dict(r) for r in d.get("rewards", [])],
            consequences=d.get("consequences", []),
            deadline=d.get("deadline", 0),
            rewards_granted=d.get("rewards_granted", False),
        )


# ============================================================
# 命运线
# ============================================================
@dataclass
class FateLine:
    """命运线"""
    character: str
    goal: str
    current_state: str
    stage: FateStage = FateStage.INTRO
    tasks: List[FateTask] = field(default_factory=list)
    key_events: List[str] = field(default_factory=list)
    conflicts: List[str] = field(default_factory=list)
    
    # 完成奖励
    completion_rewards: List[Reward] = field(default_factory=list)
    rewards_granted: bool = False


# ============================================================
# 冲突
# ============================================================
@dataclass
class Conflict:
    """冲突"""
    party1: str
    party2: str
    type: str
    description: str
    intensity: float = 0.5
    resolved: bool = False
    resolution: str = ""
    
    # 解决奖励
    resolution_rewards: List[Reward] = field(default_factory=list)
    rewards_granted: bool = False


# ============================================================
# 命运线系统（优化版）
# ============================================================
class FateSystem:
    """命运线系统 - 带奖励发放"""
    
    def __init__(self, reward_manager: Optional[RewardManager] = None):
        self.fate_lines: Dict[str, FateLine] = {}
        self.tasks: Dict[str, FateTask] = {}
        self.conflicts: List[Conflict] = []
        
        self.task_counter = 0
        
        # 奖励管理器
        self.reward_manager = reward_manager or RewardManager()
        
        # 奖励通知
        self._reward_notifications: deque = deque(maxlen=100)
    
    def create_fate_line(
        self,
        character: str,
        goal: str,
        initial_state: str = "",
        completion_rewards: List[Reward] = None
    ) -> FateLine:
        """创建命运线"""
        fate = FateLine(
            character=character,
            goal=goal,
            current_state=initial_state or f"开始追寻{goal}",
            completion_rewards=completion_rewards or [],
        )
        self.fate_lines[character] = fate
        return fate
    
    def add_task(
        self,
        character: str,
        title: str,
        description: str,
        stages: List[str],
        rewards: List[Reward] = None,
        deadline: int = 0
    ) -> FateTask:
        """添加任务"""
        self.task_counter += 1
        task_id = f"task_{self.task_counter}"
        
        task = FateTask(
            id=task_id,
            character=character,
            title=title,
            description=description,
            stages=stages,
            rewards=rewards or [],
            deadline=deadline,
        )
        
        self.tasks[task_id] = task
        
        if character in self.fate_lines:
            self.fate_lines[character].tasks.append(task)
        
        return task
    
    def advance_task(self, task_id: str, progress: float = 0.2) -> Tuple[bool, str, List[RewardResult]]:
        """
        推进任务
        
        Returns:
            (成功, 消息, 奖励结果列表)
        """
        if task_id not in self.tasks:
            return False, "任务不存在", []
        
        task = self.tasks[task_id]
        
        if task.status == TaskStatus.COMPLETED:
            return False, "任务已完成", []
        
        # 更新进度
        task.progress = min(1.0, task.progress + progress)
        task.status = TaskStatus.IN_PROGRESS
        
        # 检查阶段推进
        stages_count = len(task.stages)
        if stages_count > 0:
            new_stage = int(task.progress * stages_count)
            if new_stage > task.current_stage and new_stage < stages_count:
                task.current_stage = new_stage
        
        # 检查完成
        if task.progress >= 1.0:
            task.status = TaskStatus.COMPLETED
            
            # 发放奖励
            reward_results = self._grant_task_rewards(task)
            
            # 构建消息
            reward_text = ""
            if reward_results:
                success_rewards = [r for r in reward_results if r.success]
                if success_rewards:
                    reward_text = "\n获得奖励：\n" + "\n".join(
                        f"  • {r.reward.get_display_text()}" for r in success_rewards
                    )
            
            return True, f"任务【{task.title}】完成！{reward_text}", reward_results
        
        # 返回当前状态
        current_stage_name = task.stages[task.current_stage] if task.stages else "进行中"
        return True, f"任务【{task.title}】推进：{current_stage_name}（{int(task.progress*100)}%）", []
    
    def _grant_task_rewards(self, task: FateTask) -> List[RewardResult]:
        """发放任务奖励"""
        if task.rewards_granted or not task.rewards:
            return []
        
        results = self.reward_manager.grant_rewards(
            task.rewards, task.character, immediate=True
        )
        
        task.rewards_granted = True
        
        # 记录通知
        for result in results:
            if result.success:
                self._reward_notifications.append({
                    "type": "task_reward",
                    "task_id": task.id,
                    "task_title": task.title,
                    "character": task.character,
                    "reward": result.reward.get_display_text(),
                    "time": time.time(),
                })
        
        return results
    
    def create_conflict(
        self,
        party1: str,
        party2: str,
        conflict_type: str,
        description: str,
        intensity: float = 0.5,
        resolution_rewards: List[Reward] = None
    ) -> Conflict:
        """创建冲突"""
        conflict = Conflict(
            party1=party1,
            party2=party2,
            type=conflict_type,
            description=description,
            intensity=intensity,
            resolution_rewards=resolution_rewards or [],
        )
        
        self.conflicts.append(conflict)
        
        for party in [party1, party2]:
            if party in self.fate_lines:
                self.fate_lines[party].conflicts.append(
                    f"与{party1 if party == party2 else party2}的{conflict_type}"
                )
        
        return conflict
    
    def resolve_conflict(
        self,
        conflict_index: int,
        resolution: str,
        grant_rewards: bool = True
    ) -> Tuple[bool, str, List[RewardResult]]:
        """
        解决冲突
        
        Args:
            conflict_index: 冲突索引
            resolution: 解决方案
            grant_rewards: 是否发放奖励
        
        Returns:
            (成功, 消息, 奖励结果列表)
        """
        if not (0 <= conflict_index < len(self.conflicts)):
            return False, "冲突不存在", []
        
        conflict = self.conflicts[conflict_index]
        conflict.resolved = True
        conflict.resolution = resolution
        
        reward_results = []
        
        # 发放解决奖励
        if grant_rewards and conflict.resolution_rewards and not conflict.rewards_granted:
            # 给双方都发放奖励
            for party in [conflict.party1, conflict.party2]:
                results = self.reward_manager.grant_rewards(
                    conflict.resolution_rewards, party, immediate=True
                )
                reward_results.extend(results)
            
            conflict.rewards_granted = True
            
            # 记录通知
            for result in reward_results:
                if result.success:
                    self._reward_notifications.append({
                        "type": "conflict_resolution_reward",
                        "conflict": conflict.description,
                        "reward": result.reward.get_display_text(),
                        "time": time.time(),
                    })
        
        reward_text = ""
        if reward_results:
            success_rewards = [r for r in reward_results if r.success]
            if success_rewards:
                reward_text = "\n获得奖励：\n" + "\n".join(
                    f"  • {r.reward.get_display_text()}" for r in success_rewards
                )
        
        return True, f"冲突已解决：{resolution}{reward_text}", reward_results
    
    def advance_fate_stage(self, character: str) -> Tuple[bool, str, List[RewardResult]]:
        """
        推进命运阶段
        
        Returns:
            (成功, 消息, 奖励结果列表)
        """
        if character not in self.fate_lines:
            return False, "命运线不存在", []
        
        fate = self.fate_lines[character]
        stages = list(FateStage)
        current_idx = stages.index(fate.stage)
        
        if current_idx >= len(stages) - 1:
            return False, "命运线已达最终阶段", []
        
        fate.stage = stages[current_idx + 1]
        
        # 检查是否完成
        if fate.stage == FateStage.RESOLUTION:
            # 发放完成奖励
            return self._complete_fate_line(fate)
        
        return True, f"命运线推进到【{fate.stage.value}】阶段", []
    
    def _complete_fate_line(self, fate: FateLine) -> Tuple[bool, str, List[RewardResult]]:
        """完成命运线"""
        reward_results = []
        
        if fate.completion_rewards and not fate.rewards_granted:
            reward_results = self.reward_manager.grant_rewards(
                fate.completion_rewards, fate.character, immediate=True
            )
            fate.rewards_granted = True
            
            for result in reward_results:
                if result.success:
                    self._reward_notifications.append({
                        "type": "fate_completion_reward",
                        "character": fate.character,
                        "goal": fate.goal,
                        "reward": result.reward.get_display_text(),
                        "time": time.time(),
                    })
        
        reward_text = ""
        if reward_results:
            success_rewards = [r for r in reward_results if r.success]
            if success_rewards:
                reward_text = "\n获得奖励：\n" + "\n".join(
                    f"  • {r.reward.get_display_text()}" for r in success_rewards
                )
        
        return True, f"命运线【{fate.goal}】完成！{reward_text}", reward_results
    
    def update_fate_state(self, character: str, new_state: str, is_key_event: bool = False):
        """更新命运状态"""
        if character not in self.fate_lines:
            return
        
        fate = self.fate_lines[character]
        fate.current_state = new_state
        
        if is_key_event:
            fate.key_events.append(new_state)
            if len(fate.key_events) > 10:
                fate.key_events = fate.key_events[-10:]
    
    def get_character_fate_summary(self, character: str) -> str:
        """获取角色命运摘要"""
        if character not in self.fate_lines:
            return f"{character}暂无命运线"
        
        fate = self.fate_lines[character]
        lines = [
            f"【{character}的命运】",
            f"目标：{fate.goal}",
            f"阶段：{fate.stage.value}",
            f"当前：{fate.current_state}",
        ]
        
        active_tasks = [t for t in fate.tasks if t.status != TaskStatus.COMPLETED]
        if active_tasks:
            lines.append(f"任务：{len(active_tasks)}个进行中")
        
        active_conflicts = [c for c in self.conflicts if not c.resolved and 
                          (c.party1 == character or c.party2 == character)]
        if active_conflicts:
            lines.append(f"冲突：{len(active_conflicts)}个未解决")
        
        return "\n".join(lines)
    
    def get_all_fate_summaries(self) -> str:
        """获取所有命运摘要"""
        if not self.fate_lines:
            return "暂无命运线"
        
        summaries = [self.get_character_fate_summary(char) for char in self.fate_lines]
        return "\n\n".join(summaries)
    
    def check_deadlines(self, current_tick: int) -> List[str]:
        """检查任务截止日期"""
        expired = []
        for task_id, task in self.tasks.items():
            if task.deadline > 0 and current_tick > task.deadline:
                if task.status == TaskStatus.IN_PROGRESS:
                    task.status = TaskStatus.FAILED
                    expired.append(f"任务【{task.title}】超时失败")
        return expired
    
    def get_recent_notifications(self, limit: int = 20) -> List[Dict]:
        """获取最近的奖励通知"""
        return list(self._reward_notifications)[-limit:]
    
    def get_reward_manager(self) -> RewardManager:
        """获取奖励管理器"""
        return self.reward_manager


# ============================================================
# 全局实例
# ============================================================
_fate_system: Optional[FateSystem] = None
_reward_manager: Optional[RewardManager] = None


def get_reward_manager() -> RewardManager:
    """获取奖励管理器实例"""
    global _reward_manager
    if _reward_manager is None:
        _reward_manager = RewardManager()
    return _reward_manager


def get_fate_system() -> FateSystem:
    """获取命运线系统实例"""
    global _fate_system
    if _fate_system is None:
        _fate_system = FateSystem(get_reward_manager())
    return _fate_system
