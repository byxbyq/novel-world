# -*- coding: utf-8 -*-
"""
角色深度互动系统 - 处理交易、结盟、任务等复杂互动
"""
import random
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum


class InteractionType(Enum):
    """互动类型"""
    TRADE = "交易"           # 物品交易
    ALLIANCE = "结盟"        # 势力结盟
    TASK = "任务"            # 委托任务
    DUEL = "决斗"            # 决斗
    EXCHANGE_INFO = "交换情报"  # 交换情报
    SHARED_SECRET = "共享秘密"  # 共享秘密


@dataclass
class TradeOffer:
    """交易提议"""
    proposer: str           # 提议者
    receiver: str           # 接收者
    offer_items: List[str]  # 提供的物品
    request_items: List[str] # 请求的物品
    accepted: bool = False


@dataclass
class Alliance:
    """结盟关系"""
    faction1: str           # 势力1
    faction2: str           # 势力2
    strength: float = 0.5   # 结盟强度
    duration: int = 0       # 持续tick数
    terms: str = ""         # 结盟条款


@dataclass
class Task:
    """委托任务"""
    issuer: str             # 发布者
    assignee: str           # 接受者
    description: str        # 任务描述
    reward: str             # 奖励
    deadline: int = 0       # 截止tick
    completed: bool = False


class InteractionSystem:
    """角色深度互动系统"""
    
    def __init__(self):
        self.trades: List[TradeOffer] = []
        self.alliances: List[Alliance] = []
        self.tasks: List[Task] = []
        
        # 历史记录
        self.interaction_history: List[str] = []
        self.max_history = 100
    
    def propose_trade(self, char1, char2, offer_items: List[str], 
                      request_items: List[str]) -> TradeOffer:
        """提议交易"""
        trade = TradeOffer(
            proposer=char1.name,
            receiver=char2.name,
            offer_items=offer_items,
            request_items=request_items
        )
        
        # 判断是否接受（基于关系和物品价值）
        rel = char1.relationships.get(char2.name, 0.5) if hasattr(char1, 'relationships') else 0.5
        accept_prob = rel * 0.7 + 0.2  # 基础概率20%，关系加成
        
        trade.accepted = random.random() < accept_prob
        
        self.trades.append(trade)
        self._record_interaction(f"{char1.name}向{char2.name}提议交易，{'成功' if trade.accepted else '被拒绝'}")
        
        return trade
    
    def execute_trade(self, trade: TradeOffer, char1, char2) -> str:
        """执行交易"""
        if not trade.accepted:
            return "交易未达成"
        
        # 交换物品（简化实现）
        result = f"{trade.proposer}将{', '.join(trade.offer_items)}交给{trade.receiver}"
        if trade.request_items:
            result += f"，换取了{', '.join(trade.request_items)}"
        
        # 更新关系
        if hasattr(char1, 'relationships'):
            char1.relationships[char2.name] = min(1.0, char1.relationships.get(char2.name, 0.5) + 0.1)
        if hasattr(char2, 'relationships'):
            char2.relationships[char1.name] = min(1.0, char2.relationships.get(char1.name, 0.5) + 0.1)
        
        return result
    
    def form_alliance(self, faction1_name: str, faction2_name: str, 
                      terms: str = "") -> Alliance:
        """形成结盟"""
        alliance = Alliance(
            faction1=faction1_name,
            faction2=faction2_name,
            strength=0.6,
            terms=terms
        )
        
        self.alliances.append(alliance)
        self._record_interaction(f"{faction1_name}与{faction2_name}结盟")
        
        return alliance
    
    def check_alliance(self, faction1_name: str, faction2_name: str) -> Optional[Alliance]:
        """检查是否有结盟关系"""
        for alliance in self.alliances:
            if (alliance.faction1 == faction1_name and alliance.faction2 == faction2_name) or \
               (alliance.faction1 == faction2_name and alliance.faction2 == faction1_name):
                return alliance
        return None
    
    def break_alliance(self, faction1_name: str, faction2_name: str) -> bool:
        """解除结盟"""
        for i, alliance in enumerate(self.alliances):
            if (alliance.faction1 == faction1_name and alliance.faction2 == faction2_name) or \
               (alliance.faction1 == faction2_name and alliance.faction2 == faction1_name):
                self.alliances.pop(i)
                self._record_interaction(f"{faction1_name}与{faction2_name}解除结盟")
                return True
        return False
    
    def issue_task(self, issuer, assignee, description: str, 
                   reward: str, deadline: int = 0) -> Task:
        """发布任务"""
        task = Task(
            issuer=issuer.name if hasattr(issuer, 'name') else issuer,
            assignee=assignee.name if hasattr(assignee, 'name') else assignee,
            description=description,
            reward=reward,
            deadline=deadline
        )
        
        self.tasks.append(task)
        self._record_interaction(f"{task.issuer}向{task.assignee}发布任务：{description}")
        
        return task
    
    def complete_task(self, task: Task) -> str:
        """完成任务"""
        task.completed = True
        result = f"{task.assignee}完成了{task.issuer}的任务，获得{task.reward}"
        self._record_interaction(result)
        return result
    
    def update_alliances(self, tick: int):
        """更新结盟状态"""
        for alliance in self.alliances:
            alliance.duration += 1
            # 结盟强度随时间衰减
            alliance.strength *= 0.995
            # 强度过低则解除
            if alliance.strength < 0.3:
                self.break_alliance(alliance.faction1, alliance.faction2)
    
    def get_active_tasks(self, assignee_name: str = None) -> List[Task]:
        """获取活跃任务"""
        tasks = [t for t in self.tasks if not t.completed]
        if assignee_name:
            tasks = [t for t in tasks if t.assignee == assignee_name]
        return tasks
    
    def get_alliance_summary(self) -> str:
        """获取结盟摘要"""
        if not self.alliances:
            return "当前无结盟关系"
        
        lines = []
        for alliance in self.alliances:
            status = "稳固" if alliance.strength > 0.7 else "一般" if alliance.strength > 0.4 else "动摇"
            lines.append(f"{alliance.faction1}↔{alliance.faction2}（{status}）")
        return "、".join(lines)
    
    def _record_interaction(self, interaction: str):
        """记录互动历史"""
        self.interaction_history.append(interaction)
        if len(self.interaction_history) > self.max_history:
            self.interaction_history = self.interaction_history[-self.max_history:]


# 全局实例
_interaction_system: Optional[InteractionSystem] = None


def get_interaction_system() -> InteractionSystem:
    """获取互动系统实例"""
    global _interaction_system
    if _interaction_system is None:
        _interaction_system = InteractionSystem()
    return _interaction_system
