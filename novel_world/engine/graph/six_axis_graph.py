# -*- coding: utf-8 -*-
"""
六轴关系图 - 小说角色碰撞检测系统

六轴定义：
  FB (前/后) - 因果关系（正=推动，负=阻碍）
  UD (上/下) - 层级关系（正=仰视，负=压制）
  LR (左/右) - 利益关系（正=合作共赢，负=竞争对立）
  SD (深/浅) - 理念关系（正=共鸣，负=冲突）
  IO (内/外) - 交互关系（正=亲密，负=疏离）
  TM (时序)  - 时间关系（正值=先后顺序权重）

核心算法：detect_convergence()
  给定一组激活节点及激活值，沿边传播激活，找到多个来源汇聚的节点 = 碰撞点
"""
import json, os
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple


class SixAxis(Enum):
    """六轴枚举"""
    FB = "fb"   # 因果轴 (Causality)
    UD = "ud"   # 层级轴 (Hierarchy)
    LR = "lr"   # 利益轴 (Interest)
    SD = "sd"   # 理念轴 (Ideology)
    IO = "io"   # 交互轴 (Interaction)
    TM = "tm"   # 时序轴 (Temporal)


@dataclass
class SixAxisEdge:
    """六轴有向边"""
    src: str                           # 源节点ID
    dst: str                           # 目标节点ID
    fb: float = 0.0                    # 因果权重
    ud: float = 0.0                    # 层级权重
    lr: float = 0.0                    # 利益权重
    sd: float = 0.0                    # 理念权重
    io: float = 0.0                    # 交互权重
    tm: float = 0.0                    # 时序权重
    weight: float = 1.0                # 综合权重
    metadata: Dict = field(default_factory=dict)

    def get_axis_value(self, axis: SixAxis) -> float:
        """获取指定轴的值"""
        return getattr(self, axis.value, 0.0)

    def to_dict(self) -> dict:
        return {
            "src": self.src, "dst": self.dst,
            "fb": self.fb, "ud": self.ud, "lr": self.lr,
            "sd": self.sd, "io": self.io, "tm": self.tm,
            "weight": self.weight, "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SixAxisEdge":
        return cls(**data)


@dataclass
class ConvergenceEvent:
    """碰撞事件 - 多个激活来源汇聚到同一节点"""
    node_id: str                                # 碰撞节点ID
    sources: List[str]                          # 来源节点列表
    total_activation: float                     # 总激活值
    axis_breakdown: Dict[str, float]            # 各轴激活分值
    collision_type: str                         # 碰撞类型

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "sources": self.sources,
            "total_activation": self.total_activation,
            "axis_breakdown": self.axis_breakdown,
            "collision_type": self.collision_type,
        }


class SixAxisGraph:
    """
    六轴关系图 - 用于角色碰撞检测

    使用邻接表存储，支持：
    - 添加/移除边
    - 激活传播 + 碰撞检测
    - 环检测
    - 节点封禁/解封
    - 序列化/反序列化
    """

    def __init__(self):
        self.adj: Dict[str, List[SixAxisEdge]] = {}  # 邻接表
        self.propagation_decay: float = 0.7           # 传播衰减系数
        self._blocked_nodes: set = set()              # 封禁节点集合

    # ─── 边操作 ───

    def add_edge(self, src: str, dst: str,
                 fb: float = 0, ud: float = 0, lr: float = 0,
                 sd: float = 0, io: float = 0, tm: float = 0,
                 weight: float = 1.0, metadata: dict = None):
        """添加一条六轴有向边"""
        edge = SixAxisEdge(
            src=src, dst=dst, fb=fb, ud=ud, lr=lr,
            sd=sd, io=io, tm=tm, weight=weight,
            metadata=metadata or {},
        )
        self.adj.setdefault(src, []).append(edge)
        # 确保 dst 也存在于邻接表（即使无出边）
        self.adj.setdefault(dst, [])

    def remove_edge(self, src: str, dst: str) -> bool:
        """移除 src->dst 的边"""
        if src not in self.adj:
            return False
        original_len = len(self.adj[src])
        self.adj[src] = [e for e in self.adj[src] if e.dst != dst]
        return len(self.adj[src]) < original_len

    def get_edge(self, src: str, dst: str) -> Optional[SixAxisEdge]:
        """获取 src->dst 的边（如有）"""
        if src not in self.adj:
            return None
        for e in self.adj[src]:
            if e.dst == dst:
                return e
        return None

    def get_neighbors(self, node: str, axis: SixAxis = None) -> List[SixAxisEdge]:
        """
        获取节点的邻居边
        axis: 若指定，只返回该轴值非零的边
        """
        edges = self.adj.get(node, [])
        if axis is None:
            return list(edges)
        return [e for e in edges if e.get_axis_value(axis) != 0]

    # ─── 碰撞检测（核心） ───

    def detect_convergence(self, activated_nodes: Dict[str, float]) -> List[ConvergenceEvent]:
        """
        碰撞检测 - 核心算法

        给定一组激活节点及其激活值，沿边传播激活信号。
        当多个来源的激活汇聚到同一节点时，产生碰撞事件。

        Args:
            activated_nodes: {节点ID: 激活值}，激活值范围 0~1

        Returns:
            碰撞事件列表，按总激活值降序排列
        """
        # 第一步：传播激活 - 收集每个节点收到的激活（来源 -> 值 -> 轴分值）
        # received[node_id] = [(source, activation, axis_breakdown), ...]
        received: Dict[str, List[Tuple[str, float, Dict[str, float]]]] = {}

        for src, activation in activated_nodes.items():
            if src in self._blocked_nodes:
                continue
            for edge in self.adj.get(src, []):
                if edge.dst in self._blocked_nodes:
                    continue
                # 计算沿此边传播后的激活值
                propagated = activation * self.propagation_decay * edge.weight
                if propagated < 0.01:
                    continue  # 忽略极小激活
                # 计算各轴贡献
                axis_contrib = {}
                for axis in SixAxis:
                    val = edge.get_axis_value(axis)
                    if val != 0:
                        axis_contrib[axis.value] = propagated * abs(val)
                if not axis_contrib:
                    axis_contrib["tm"] = propagated  # 无显式轴时归入时序
                received.setdefault(edge.dst, []).append(
                    (src, propagated, axis_contrib)
                )

        # 第二步：识别碰撞 - 收到多个来源激活的节点
        events = []
        for node_id, sources_list in received.items():
            if len(sources_list) < 2:
                continue  # 需要至少2个来源才算碰撞
            # 合并所有来源
            all_sources = []
            total_act = 0.0
            merged_axes: Dict[str, float] = {}
            for source, act, axes in sources_list:
                all_sources.append(source)
                total_act += act
                for axis_name, val in axes.items():
                    merged_axes[axis_name] = merged_axes.get(axis_name, 0) + val
            # 分类碰撞类型
            collision_type = self._classify_collision(merged_axes)
            events.append(ConvergenceEvent(
                node_id=node_id,
                sources=all_sources,
                total_activation=round(total_act, 4),
                axis_breakdown={k: round(v, 4) for k, v in merged_axes.items()},
                collision_type=collision_type,
            ))

        # 按总激活值降序排列
        events.sort(key=lambda e: e.total_activation, reverse=True)
        return events

    def _classify_collision(self, axis_breakdown: Dict[str, float]) -> str:
        """
        根据各轴激活分值，分类碰撞类型

        分类规则：
        - 因果冲突/合作：fb 轴占主导且为负/正
        - 利益竞争：lr 轴占主导且为负
        - 理念冲突：sd 轴占主导且为负
        - 层级压制/反抗：ud 轴占主导且为负/正
        - 多维碰撞：多个轴同时活跃
        - 弱遭遇：所有轴激活值都很低
        """
        if not axis_breakdown:
            return "weak_encounter"

        total = sum(abs(v) for v in axis_breakdown.values())
        if total < 0.01:
            return "weak_encounter"

        # 计算各轴占比
        ratios = {k: abs(v) / total for k, v in axis_breakdown.items()}

        # 检查是否有多个轴活跃（占比>20%的轴>=2个）
        active_axes = [k for k, r in ratios.items() if r > 0.20]

        if len(active_axes) >= 3:
            return "multi_dimensional"

        # 检查主导轴（占比>40%）
        dominant = max(ratios, key=ratios.get)
        dominant_ratio = ratios[dominant]

        if dominant_ratio < 0.30:
            return "weak_encounter"

        # 判断方向（取原始值的符号）
        raw_val = axis_breakdown.get(dominant, 0)

        if dominant == "fb":
            return "causal_conflict" if raw_val < 0 else "causal_cooperation"
        elif dominant == "lr":
            return "interest_competition" if raw_val < 0 else "interest_cooperation"
        elif dominant == "sd":
            return "ideology_conflict" if raw_val < 0 else "ideology_resonance"
        elif dominant == "ud":
            return "hierarchy_suppress" if raw_val < 0 else "hierarchy_rebellion"
        elif dominant == "io":
            return "interaction_conflict" if raw_val < 0 else "interaction_harmony"
        elif dominant == "tm":
            return "temporal_encounter"

        return "weak_encounter"

    # ─── 环检测 ───

    def detect_cycles(self) -> List[List[str]]:
        """
        检测图中的所有环（DFS 方法）
        返回环路径列表，每条环为节点ID序列
        """
        visited = set()
        rec_stack = set()
        cycles = []

        def dfs(node, path):
            visited.add(node)
            rec_stack.add(node)
            path.append(node)
            for edge in self.adj.get(node, []):
                neighbor = edge.dst
                if neighbor not in visited:
                    dfs(neighbor, path)
                elif neighbor in rec_stack:
                    # 找到环：从 neighbor 在 path 中的位置到末尾
                    idx = path.index(neighbor)
                    cycle = path[idx:] + [neighbor]
                    cycles.append(cycle)
            path.pop()
            rec_stack.discard(node)

        for node in list(self.adj.keys()):
            if node not in visited:
                dfs(node, [])
        return cycles

    # ─── 节点封禁 ───

    def block_node(self, node_id: str):
        """封禁节点：该节点不再参与激活传播"""
        self._blocked_nodes.add(node_id)

    def unblock_node(self, node_id: str):
        """解封节点"""
        self._blocked_nodes.discard(node_id)

    # ─── 序列化 ───

    def to_dict(self) -> dict:
        """序列化为字典"""
        edges = []
        for src, edge_list in self.adj.items():
            for e in edge_list:
                edges.append(e.to_dict())
        return {
            "adj": {src: [e.to_dict() for e in el] for src, el in self.adj.items()},
            "propagation_decay": self.propagation_decay,
            "blocked_nodes": list(self._blocked_nodes),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SixAxisGraph":
        """从字典反序列化"""
        graph = cls()
        graph.propagation_decay = data.get("propagation_decay", 0.7)
        graph._blocked_nodes = set(data.get("blocked_nodes", []))
        for src, edge_list in data.get("adj", {}).items():
            for edge_data in edge_list:
                e = SixAxisEdge.from_dict(edge_data)
                graph.adj.setdefault(src, []).append(e)
                graph.adj.setdefault(e.dst, [])
        return graph

    def save(self, path: str):
        """保存到 JSON 文件"""
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, path: str) -> "SixAxisGraph":
        """从 JSON 文件加载"""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)

    # ─── 统计 ───

    def get_stats(self) -> dict:
        """返回图统计信息"""
        total_edges = sum(len(el) for el in self.adj.values())
        return {
            "node_count": len(self.adj),
            "edge_count": total_edges,
            "blocked_count": len(self._blocked_nodes),
            "propagation_decay": self.propagation_decay,
            "nodes": list(self.adj.keys()),
        }
