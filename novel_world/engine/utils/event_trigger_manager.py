# -*- coding: utf-8 -*-
"""
事件触发管理器 - 管理 TRIGGER_ 变量和事件触发逻辑

核心功能：
1. 检查事件是否可以触发（检查 TRIGGER_ 变量和其他条件）
2. 触发事件后更新 TRIGGER_ 变量
3. 评估条件表达式
"""
import re
from typing import Dict, List, Optional, Set, Any


class EventTriggerManager:
    """事件触发管理器"""
    
    def __init__(self, world=None):
        self.world = world
        self._trigger_prefix = "TRIGGER_"
    
    def set_world(self, world):
        """设置世界对象"""
        self.world = world
    
    def get_trigger_states(self) -> Dict[str, int]:
        """获取所有 TRIGGER_ 变量"""
        if self.world and hasattr(self.world, 'trigger_states'):
            return self.world.trigger_states
        return {}
    
    def get_trigger(self, name: str) -> int:
        """获取单个 TRIGGER_ 变量值（默认0）"""
        states = self.get_trigger_states()
        key = name if name.startswith(self._trigger_prefix) else f"{self._trigger_prefix}{name}"
        return states.get(key, 0)
    
    def set_trigger(self, name: str, value: int = 1):
        """设置 TRIGGER_ 变量值"""
        if self.world and hasattr(self.world, 'trigger_states'):
            key = name if name.startswith(self._trigger_prefix) else f"{self._trigger_prefix}{name}"
            self.world.trigger_states[key] = value
    
    def reset_trigger(self, name: str):
        """重置 TRIGGER_ 变量为0"""
        self.set_trigger(name, 0)
    
    # === 条件评估 ===
    
    def evaluate_condition(self, condition: str, context: Dict = None) -> bool:
        """
        评估条件表达式
        
        支持的格式：
        - TRIGGER_剧情名 == 0  (TRIGGER变量检查)
        - AGE >= 16  (属性检查)
        - EVT?[10009]  (事件是否发生过)
        - TLT?[1048]  (天赋检查)
        - STR < 5  (属性比较)
        - & (AND) | (OR) 逻辑组合
        """
        if not condition or condition == "None":
            return True
        
        if context is None:
            context = {}
        
        try:
            # 替换 TRIGGER_ 变量
            result = self._replace_triggers(condition)
            
            # 替换属性变量 (AGE, STR, INT, MNY, SPR, LIF, CHR 等)
            result = self._replace_attributes(result, context)
            
            # 替换事件检查 EVT?[...]
            result = self._replace_event_checks(result, context)
            
            # 替换天赋检查 TLT?[...]
            result = self._replace_talent_checks(result, context)
            
            # 评估最终表达式
            return self._eval_expression(result)
        except Exception as e:
            print(f"[EventTriggerManager] 条件评估失败: {condition} -> {e}")
            return True  # 评估失败时默认允许触发
    
    def _replace_triggers(self, condition: str) -> str:
        """替换 TRIGGER_ 变量为实际值"""
        states = self.get_trigger_states()
        
        # 匹配 TRIGGER_xxx
        pattern = r'TRIGGER_(\w+)'
        
        def replace(match):
            name = f"TRIGGER_{match.group(1)}"
            value = states.get(name, 0)
            return str(value)
        
        return re.sub(pattern, replace, condition)
    
    def _replace_attributes(self, condition: str, context: Dict) -> str:
        """替换属性变量"""
        # 属性名列表
        attrs = ['AGE', 'STR', 'INT', 'MNY', 'SPR', 'LIF', 'CHR']
        
        for attr in attrs:
            if attr in condition:
                value = context.get(attr, 0)
                condition = condition.replace(attr, str(value))
        
        return condition
    
    def _replace_event_checks(self, condition: str, context: Dict) -> str:
        """替换事件检查 EVT?[...]"""
        # EVT?[id1,id2,...] 表示事件是否发生过
        # EVT![id1,id2,...] 表示事件是否没发生过
        
        if not self.world:
            return condition
        
        event_log = getattr(self.world, 'event_log', [])
        happened_ids = set(str(e.get('id', e.get('$id', ''))) for e in event_log if isinstance(e, dict))
        
        # EVT?[...] - 事件发生过
        def replace_evt_yes(match):
            ids_str = match.group(1)
            ids = [i.strip() for i in ids_str.split(',')]
            for id_ in ids:
                if id_ in happened_ids:
                    return "True"
            return "False"
        
        condition = re.sub(r'EVT\?\[([^\]]+)\]', replace_evt_yes, condition)
        
        # EVT![...] - 事件没发生过
        def replace_evt_no(match):
            ids_str = match.group(1)
            ids = [i.strip() for i in ids_str.split(',')]
            for id_ in ids:
                if id_ in happened_ids:
                    return "False"
            return "True"
        
        condition = re.sub(r'EVT!\[([^\]]+)\]', replace_evt_no, condition)
        
        return condition
    
    def _replace_talent_checks(self, condition: str, context: Dict) -> str:
        """替换天赋检查 TLT?[...]"""
        # 简化处理：从 context 获取天赋列表
        talents = context.get('talents', set())
        
        def replace_tlt(match):
            ids_str = match.group(1)
            ids = [i.strip() for i in ids_str.split(',')]
            for id_ in ids:
                if id_ in talents:
                    return "True"
            return "False"
        
        condition = re.sub(r'TLT\?\[([^\]]+)\]', replace_tlt, condition)
        
        return condition
    
    def _eval_expression(self, expr: str) -> bool:
        """安全评估简单布尔表达式"""
        # 清理表达式
        expr = expr.strip()
        
        if not expr or expr == "None":
            return True
        
        # 替换逻辑运算符
        expr = expr.replace('&', ' and ')
        expr = expr.replace('|', ' or ')
        
        # 只允许安全的字符
        allowed = set('0123456789 TrueFalseandor<>=!() ')
        if not all(c in allowed for c in expr):
            print(f"[EventTriggerManager] 不安全的表达式: {expr}")
            return True
        
        try:
            return bool(eval(expr))
        except:
            return True
    
    # === 事件触发处理 ===
    
    def can_trigger_event(self, event: Dict, context: Dict = None) -> bool:
        """
        检查事件是否可以触发
        
        检查顺序：
        1. include 条件
        2. exclude 条件
        3. TRIGGER_ 变量条件
        """
        if context is None:
            context = {}
        
        # 检查 include 条件
        include = event.get('include', '')
        if include and include != 'None':
            if not self.evaluate_condition(include, context):
                return False
        
        # 检查 exclude 条件（如果满足 exclude 则不能触发）
        exclude = event.get('exclude', '')
        if exclude and exclude != 'None':
            if self.evaluate_condition(exclude, context):
                return False
        
        return True
    
    def on_event_triggered(self, event: Dict):
        """
        事件触发后调用，更新 TRIGGER_ 变量
        
        从事件的 effect 字段提取 TRIGGER_ 变量设置
        """
        # 检查 effect 字段
        effect = event.get('effect', '')
        if effect and effect != 'None':
            self._apply_effect(effect)
        
        # 检查 effect:* 字段
        for key, value in event.items():
            if key.startswith('effect:') and value:
                self._apply_effect_value(key, value)
        
        # 记录事件到 event_log
        if self.world and hasattr(self.world, 'event_log'):
            self.world.event_log.append({
                'id': event.get('$id', ''),
                'event': event.get('event', ''),
                'time': self.world.tick_count if hasattr(self.world, 'tick_count') else 0
            })
    
    def _apply_effect(self, effect: str):
        """应用效果字符串"""
        # 解析格式如 "TRIGGER_剧情名=1"
        pattern = r'TRIGGER_(\w+)\s*=\s*(\d+)'
        matches = re.findall(pattern, effect)
        for name, value in matches:
            self.set_trigger(f"TRIGGER_{name}", int(value))
    
    def _apply_effect_value(self, key: str, value: Any):
        """应用效果值"""
        # effect:TRIGGER_xxx 格式
        if key.startswith('effect:TRIGGER_'):
            trigger_name = key[7:]  # 去掉 "effect:"
            if isinstance(value, (int, float)):
                self.set_trigger(trigger_name, int(value))


# 全局实例
_trigger_manager: Optional[EventTriggerManager] = None


def get_trigger_manager(world=None) -> EventTriggerManager:
    """获取事件触发管理器"""
    global _trigger_manager
    if _trigger_manager is None:
        _trigger_manager = EventTriggerManager(world)
    elif world:
        _trigger_manager.set_world(world)
    return _trigger_manager
