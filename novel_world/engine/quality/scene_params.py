# -*- coding: utf-8 -*-
"""
场景参数库 - 场景类型、过渡逻辑、可触发动作参数化设计
"""
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
import random


@dataclass
class SceneDetail:
    """场景细节参数"""
    area: str  # 区域名称
    actions: List[str]  # 可触发动作
    atmosphere: str = ""  # 氛围描述
    

@dataclass
class SceneType:
    """场景类型参数"""
    name: str  # 场景名称
    category: str  # 场景类别（室内/室外/公共/私人）
    details: List[SceneDetail]  # 场景细节列表
    transition_phrases: List[str] = field(default_factory=list)  # 过渡语句
    max_switches: int = 3  # 同一剧情线最大切换次数
    

class SceneParams:
    """场景参数库"""
    
    def __init__(self):
        self._scenes: Dict[str, SceneType] = {}
        self._detail_blacklist: Dict[str, int] = {}  # 细节黑名单（细节 -> 出现次数）
        self._max_detail_repeat = 1  # 同一细节最大重复次数
        self._initialize_default_scenes()
    
    def _initialize_default_scenes(self):
        """初始化默认场景参数"""
        
        # 超市场景
        self._scenes["超市"] = SceneType(
            name="超市",
            category="公共",
            details=[
                SceneDetail("生鲜区", ["挑选蔬菜", "比较价格", "查看新鲜度"], "明亮整洁"),
                SceneDetail("零食区", ["浏览零食", "拿起查看", "放入购物车"], "琳琅满目"),
                SceneDetail("收银台", ["排队结账", "等待", "付款"], "人来人往"),
                SceneDetail("日用品区", ["寻找商品", "对比品牌", "挑选规格"], "整齐有序"),
            ],
            transition_phrases=[
                "走向另一个区域",
                "转了一圈",
                "来到另一排货架",
            ],
            max_switches=3
        )
        
        # 茶水间场景
        self._scenes["茶水间"] = SceneType(
            name="茶水间",
            category="室内",
            details=[
                SceneDetail("咖啡机", ["接咖啡", "等待", "调整浓度"], "咖啡飘香"),
                SceneDetail("休息区", ["坐下休息", "聊天", "看手机"], "轻松惬意"),
                SceneDetail("饮水机", ["接水", "等待", "离开"], "简洁实用"),
            ],
            transition_phrases=[
                "换个位置",
                "走到另一边",
            ],
            max_switches=2
        )
        
        # 办公室场景
        self._scenes["办公室"] = SceneType(
            name="办公室",
            category="室内",
            details=[
                SceneDetail("工位", ["工作", "看电脑", "整理文件"], "安静专注"),
                SceneDetail("会议室", ["开会", "讨论", "记录"], "正式严肃"),
                SceneDetail("走廊", ["走动", "交谈", "思考"], "来来往往"),
            ],
            transition_phrases=[
                "离开工位",
                "走向另一个区域",
            ],
            max_switches=3
        )
        
        # 街道场景
        self._scenes["街道"] = SceneType(
            name="街道",
            category="室外",
            details=[
                SceneDetail("人行道", ["走路", "看手机", "观察周围"], "熙熙攘攘"),
                SceneDetail("商店门口", ["驻足", "看橱窗", "进入"], "热闹繁华"),
                SceneDetail("路口", ["等待", "过马路", "张望"], "车水马龙"),
            ],
            transition_phrases=[
                "继续往前走",
                "转向另一条街",
            ],
            max_switches=3
        )
        
        # 餐厅场景
        self._scenes["餐厅"] = SceneType(
            name="餐厅",
            category="公共",
            details=[
                SceneDetail("用餐区", ["吃饭", "交谈", "看菜单"], "温馨舒适"),
                SceneDetail("点餐台", ["排队", "点餐", "等待"], "井然有序"),
                SceneDetail("座位", ["坐下", "用餐", "聊天"], "轻松愉快"),
            ],
            transition_phrases=[
                "换个位置",
                "走向另一区域",
            ],
            max_switches=2
        )
    
    def get_scene(self, scene_name: str) -> Optional[SceneType]:
        """获取场景参数"""
        return self._scenes.get(scene_name)
    
    def get_random_detail(self, scene_name: str) -> Optional[Tuple[str, List[str]]]:
        """获取随机场景细节（区域 + 动作列表）"""
        scene = self.get_scene(scene_name)
        if not scene or not scene.details:
            return None
        
        # 过滤掉黑名单中的细节
        available_details = [
            d for d in scene.details 
            if self._detail_blacklist.get(d.area, 0) < self._max_detail_repeat
        ]
        
        if not available_details:
            # 如果所有细节都用过了，重置黑名单
            self._detail_blacklist.clear()
            available_details = scene.details
        
        detail = random.choice(available_details)
        
        # 更新黑名单
        self._detail_blacklist[detail.area] = self._detail_blacklist.get(detail.area, 0) + 1
        
        return (detail.area, detail.actions)
    
    def get_random_action(self, scene_name: str, area: str = None) -> Optional[str]:
        """获取随机动作"""
        scene = self.get_scene(scene_name)
        if not scene:
            return None
        
        if area:
            # 指定区域
            for detail in scene.details:
                if detail.area == area and detail.actions:
                    return random.choice(detail.actions)
        else:
            # 随机区域
            result = self.get_random_detail(scene_name)
            if result:
                _, actions = result
                return random.choice(actions) if actions else None
        
        return None
    
    def get_transition_phrase(self, scene_name: str) -> Optional[str]:
        """获取场景过渡语句"""
        scene = self.get_scene(scene_name)
        if not scene or not scene.transition_phrases:
            return None
        return random.choice(scene.transition_phrases)
    
    def check_scene_switch_limit(self, scene_name: str, current_switches: int) -> bool:
        """检查场景切换是否超过限制"""
        scene = self.get_scene(scene_name)
        if not scene:
            return current_switches < 3  # 默认限制
        return current_switches < scene.max_switches
    
    def is_scene_valid(self, scene_name: str) -> bool:
        """检查场景是否有效（是否在参数库中）"""
        return scene_name in self._scenes
    
    def add_scene(self, scene_name: str, scene: SceneType):
        """添加新场景"""
        self._scenes[scene_name] = scene
    
    def list_scenes(self) -> List[str]:
        """列出所有场景"""
        return list(self._scenes.keys())
    
    def reset_detail_blacklist(self):
        """重置细节黑名单"""
        self._detail_blacklist.clear()


# 单例模式
_scene_params_instance = None

def get_scene_params() -> SceneParams:
    """获取场景参数库单例"""
    global _scene_params_instance
    if _scene_params_instance is None:
        _scene_params_instance = SceneParams()
    return _scene_params_instance
