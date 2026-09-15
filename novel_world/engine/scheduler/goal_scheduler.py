# -*- coding: utf-8 -*-
"""
目标调度器 - 管理角色的目标生命周期和失败处理

核心概念：
- GoalStatus: 目标状态（待执行/执行中/已完成/延迟/放弃）
- GoalLevel: 目标层级（日常/阶段/终极）
- Goal: 目标数据结构（含降级/改道/放弃分支逻辑）
- GoalScheduler: 目标调度器（目标创建、推进、完成、失败处理）

目标层级体系：
  ULTIMATE（终极目标）
    └── STAGE（阶段目标）
          └── DAILY（日常目标）
  
  日常目标服务于阶段目标，阶段目标服务于终极目标。
  当所有子目标完成时，父目标自动推进。

失败处理三分支策略：
  当目标被延迟超过阈值（defer_threshold）时，触发失败处理：
  1. downgrade（降级）: 降低目标要求，创建简化版本
  2. reroute（改道）: 改变达成路径，添加新上下文
  3. abandon（放弃）: 彻底放弃该目标

设计原则：
- 目标自动编号，格式: goal_{tick:04d}_{index:03d}
- 父子目标形成树形结构
- 备选池（backup_pool）用于目标失败时生成替代目标
- 支持独立运行，不依赖 SwimlaneManager
"""
import json, random, sys, os
from typing import Dict, List, Optional

# 从统一数据源导入 Goal / GoalStatus / GoalLevel
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
from novel_world.engine.core.goal import Goal, GoalStatus, GoalLevel  # noqa: E402


class GoalScheduler:
    """
    目标调度器 - 管理角色的目标创建、推进、完成和失败处理

    核心职责：
    1. 创建多层级目标（日常/阶段/终极）
    2. 跟踪目标执行状态
    3. 处理目标完成（检查父子关系，触发级联）
    4. 处理目标失败（延迟计数 -> 三分支策略）
    5. tick 推进时自动处理未完成的目标

    支持独立运行：不设置 SwimlaneManager 时，完成/延迟操作只更新本地数据。

    使用方式：
        gs = GoalScheduler()
        gs.add_goal("修炼突破", GoalLevel.STAGE, "林逸", tick=1)
        gs.add_goal("打坐冥想", GoalLevel.DAILY, "林逸",
                    parent_goal_id="goal_0001_001", tick=1)
        gs.start_goal("goal_0001_001", tick=2)
        gs.complete_goal("goal_0001_001", tick=3)
    """

    def __init__(self):
        """初始化目标调度器"""
        self.goals: Dict[str, Goal] = {}                   # 所有目标
        self.character_goals: Dict[str, List[str]] = {}    # 角色 -> 目标 ID 列表
        self.swimlane_manager = None                       # SwimlaneManager 引用（可选）

    # ─── 引用设置 ───

    def set_swimlane_manager(self, sm):
        """
        设置 SwimlaneManager 引用

        Args:
            sm: SwimlaneManager 实例
        """
        self.swimlane_manager = sm

    # ─── 目标创建 ───

    def add_goal(self, content: str, level: GoalLevel,
                 character_name: str, parent_goal_id: str = None,
                 backup_pool: List[str] = None, tick: int = 0) -> Goal:
        """
        创建新目标

        自动生成目标 ID（格式: goal_{tick:04d}_{index:03d}），
        并建立父子关联。

        Args:
            content: 目标描述
            level: 目标层级
            character_name: 所属角色名
            parent_goal_id: 父目标 ID（可选）
            backup_pool: 备选目标描述列表（可选）
            tick: 当前 tick 编号

        Returns:
            新创建的 Goal 对象
        """
        # 生成目标 ID
        index = len(self.goals) + 1
        goal_id = f"goal_{tick:04d}_{index:03d}"

        goal = Goal(
            id=goal_id,
            content=content,
            level=level,
            character_name=character_name,
            parent_goal_id=parent_goal_id,
            backup_pool=list(backup_pool) if backup_pool else [],
            created_tick=tick,
            metadata={"index": index},
        )
        self.goals[goal_id] = goal

        # 更新角色目标索引
        self.character_goals.setdefault(character_name, []).append(goal_id)

        # 建立父子关联
        if parent_goal_id and parent_goal_id in self.goals:
            parent = self.goals[parent_goal_id]
            parent.child_goal_ids.append(goal_id)

        print(f"[GoalScheduler] 创建目标: {goal_id} [{level.value}] {content}")
        return goal

    def add_mainline_goal(self, content: str, character_name: str,
                           level: GoalLevel = GoalLevel.STAGE,
                           tick: int = 0) -> Goal:
        """根据世界主线目标（main_objective）创建高权重目标。

        自动设定 weight=3.0（主线权重），确保在调度排序中优先于普通目标。
        主线目标通常为 STAGE 层级，由引擎在 init_game 时为每个核心角色调用。

        Args:
            content: 主线目标描述
            character_name: 所属角色名
            level: 目标层级（默认 STAGE，主线目标通常不设为 DAILY）
            tick: 当前 tick 编号

        Returns:
            新创建的 Goal 对象，weight=3.0
        """
        index = len(self.goals) + 1
        goal_id = f"goal_{tick:04d}_{index:03d}"

        goal = Goal(
            id=goal_id,
            content=content,
            level=level,
            character_name=character_name,
            weight=3.0,
            created_tick=tick,
            metadata={"index": index, "source": "main_objective"},
        )
        self.goals[goal_id] = goal
        self.character_goals.setdefault(character_name, []).append(goal_id)

        print(f"[GoalScheduler] 创建主线目标: {goal_id} [{level.value}] (weight=3.0) {content}")
        return goal

    # ─── 目标查询 ───

    def get_character_goals(self, character_name: str,
                            level: GoalLevel = None,
                            status: GoalStatus = None) -> List[Goal]:
        """
        获取角色的目标列表

        Args:
            character_name: 角色名称
            level: 过滤目标层级（可选）
            status: 过滤目标状态（可选）

        Returns:
            Goal 列表
        """
        goal_ids = self.character_goals.get(character_name, [])
        result = []
        for gid in goal_ids:
            goal = self.goals.get(gid)
            if goal is None:
                continue
            if level is not None and goal.level != level:
                continue
            if status is not None and goal.status != status:
                continue
            result.append(goal)
        return result

    def get_daily_goals_for_tick(self, character_name: str, tick: int) -> List[Goal]:
        """
        获取角色在指定 tick 应该处理的日常目标

        返回 PENDING 或 EXECUTING 状态的 DAILY 目标。

        Args:
            character_name: 角色名称
            tick: tick 编号（用于日志）

        Returns:
            DAILY 目标列表
        """
        all_daily = self.get_character_goals(character_name, level=GoalLevel.DAILY)
        return [
            g for g in all_daily
            if g.status in (GoalStatus.PENDING, GoalStatus.EXECUTING)
        ]

    def get_weighted_daily_goals_for_tick(self, character_name: str, tick: int) -> List[Goal]:
        """获取角色的日常目标，按 weight 降序排列。

        高权重目标优先返回，weight 相同则按创建时间（created_tick）排序。
        用于确保主线/长期目标优先获得 Tick 资源分配。

        Args:
            character_name: 角色名称
            tick: tick 编号

        Returns:
            按 weight 降序排列的 DAILY 目标列表
        """
        goals = self.get_daily_goals_for_tick(character_name, tick)
        goals.sort(key=lambda g: (g.weight, -g.created_tick), reverse=True)
        return goals

    def get_all_active_goals_weighted(self, character_name: str) -> List[Goal]:
        """获取角色所有层级活跃目标，按 weight 降序排列。

        包含 DAILY / STAGE / ULTIMATE 层级中 PENDING 或 EXECUTING 状态的目标。
        高权重目标排在前，供调度器按优先级分配资源。

        Args:
            character_name: 角色名称

        Returns:
            按 weight 降序排列的活跃目标列表
        """
        all_goals = self.get_character_goals(character_name)
        active = [
            g for g in all_goals
            if g.status in (GoalStatus.PENDING, GoalStatus.EXECUTING)
        ]
        active.sort(key=lambda g: (g.weight, -g.created_tick), reverse=True)
        return active

    # ─── 目标执行 ───

    def start_goal(self, goal_id: str, tick: int):
        """
        开始执行目标

        Args:
            goal_id: 目标 ID
            tick: 当前 tick 编号
        """
        goal = self.goals.get(goal_id)
        if goal is None:
            print(f"[GoalScheduler] 警告: 目标 '{goal_id}' 不存在，无法开始")
            return

        if goal.status not in (GoalStatus.PENDING, GoalStatus.DEFERRED):
            print(f"[GoalScheduler] 警告: 目标 '{goal_id}' 状态为 {goal.status.value}，无法开始")
            return

        goal.status = GoalStatus.EXECUTING
        print(f"[GoalScheduler] 开始执行目标: {goal_id} [{goal.content}]")

    def complete_goal(self, goal_id: str, tick: int) -> List[Goal]:
        """
        完成目标

        完成逻辑：
        1. 标记目标为 COMPLETED，记录完成 tick
        2. 如果有父目标：检查所有兄弟目标是否都已完成
           - 全部完成：推进父目标状态
        3. 如果是 DAILY 目标且无父目标：尝试从 backup_pool 或阶段目标生成下一个日常目标

        Args:
            goal_id: 目标 ID
            tick: 当前 tick 编号

        Returns:
            因完成此目标而新创建的 Goal 列表
        """
        goal = self.goals.get(goal_id)
        if goal is None:
            print(f"[GoalScheduler] 警告: 目标 '{goal_id}' 不存在，无法完成")
            return []

        goal.status = GoalStatus.COMPLETED
        goal.completed_tick = tick
        print(f"[GoalScheduler] 完成目标: {goal_id} [{goal.content}]")

        newly_created = []

        # 情况1：有父目标，检查兄弟是否全部完成
        if goal.parent_goal_id and goal.parent_goal_id in self.goals:
            parent = self.goals[goal.parent_goal_id]
            siblings_completed = all(
                self.goals[sid].status == GoalStatus.COMPLETED
                for sid in parent.child_goal_ids
                if sid in self.goals
            )
            if siblings_completed and parent.status == GoalStatus.EXECUTING:
                parent.status = GoalStatus.COMPLETED
                parent.completed_tick = tick
                print(f"[GoalScheduler] 父目标完成: {parent.id} [{parent.content}]")

        # 情况2：DAILY 目标且无父目标，尝试生成下一个
        if goal.level == GoalLevel.DAILY and not goal.parent_goal_id:
            # 优先从 backup_pool 取
            if goal.backup_pool:
                next_content = goal.backup_pool.pop(0)
                new_goal = self.add_goal(
                    content=next_content,
                    level=GoalLevel.DAILY,
                    character_name=goal.character_name,
                    backup_pool=goal.backup_pool,
                    tick=tick,
                )
                newly_created.append(new_goal)
            else:
                # 从同角色的 STAGE 目标中提取
                stage_goals = self.get_character_goals(
                    goal.character_name, level=GoalLevel.STAGE
                )
                for sg in stage_goals:
                    if sg.status in (GoalStatus.PENDING, GoalStatus.EXECUTING):
                        # 基于阶段目标生成简化的日常目标
                        daily_content = f"推进阶段目标: {sg.content[:20]}"
                        new_goal = self.add_goal(
                            content=daily_content,
                            level=GoalLevel.DAILY,
                            character_name=goal.character_name,
                            parent_goal_id=sg.id,
                            tick=tick,
                        )
                        newly_created.append(new_goal)
                        break

        return newly_created

    def defer_goal(self, goal_id: str, tick: int):
        """
        延迟目标

        增加延迟计数，判断是否触发失败处理。
        未达阈值时标记为 DEFERRED（下一个 tick 可重试）。

        Args:
            goal_id: 目标 ID
            tick: 当前 tick 编号
        """
        goal = self.goals.get(goal_id)
        if goal is None:
            return

        goal.defer_count += 1
        print(f"[GoalScheduler] 延迟目标: {goal_id} (第{goal.defer_count}次, 阈值={goal.defer_threshold})")

        if goal.defer_count >= goal.defer_threshold:
            # 触发失败处理
            self._resolve_failed_goal(goal_id, tick)
        else:
            # 标记为延迟，下个 tick 可重试
            goal.status = GoalStatus.DEFERRED

    def _resolve_failed_goal(self, goal_id: str, tick: int) -> Optional[Goal]:
        """
        失败目标处理 - 三分支策略

        当目标被延迟次数超过阈值时，根据目标层级和上下文，
        选择合适的处理分支：

        1. "downgrade"（降级）: 降低目标要求，创建简化版本
           - 适用：DAILY 目标、STAGE 目标
           - 策略：保留目标核心，移除额外条件

        2. "reroute"（改道）: 改变达成路径，添加新上下文
           - 适用：STAGE 目标、ULTIMATE 目标
           - 策略：改变路径描述，增加替代信息

        3. "abandon"（放弃）: 彻底放弃该目标
           - 适用：所有层级（作为最后手段）
           - 策略：标记为 ABANDONED，从活跃目标中移除

        Args:
            goal_id: 目标 ID
            tick: 当前 tick 编号

        Returns:
            修改后的目标或新创建的目标（abandon 时返回 None）
        """
        goal = self.goals.get(goal_id)
        if goal is None:
            return None

        print(f"[GoalScheduler] 处理失败目标: {goal_id} [{goal.content}]")

        # 根据目标层级选择分支策略
        # DAILY 目标优先降级，ULTIMATE 目标优先改道
        if goal.level == GoalLevel.DAILY:
            branch = "downgrade"
        elif goal.level == GoalLevel.STAGE:
            # 50% 概率改道，30% 降级，20% 放弃
            r = random.random()
            if r < 0.5:
                branch = "reroute"
            elif r < 0.8:
                branch = "downgrade"
            else:
                branch = "abandon"
        else:  # ULTIMATE
            # 60% 改道，40% 放弃（终极目标不降级）
            r = random.random()
            if r < 0.6:
                branch = "reroute"
            else:
                branch = "abandon"

        goal.failed_branch = branch

        if branch == "downgrade":
            # 降级：简化目标内容，创建新版本
            original_content = goal.content
            # 降级标记
            downgraded_content = f"{original_content}（简化版）"
            goal.content = downgraded_content
            goal.defer_count = 0  # 重置延迟计数
            goal.status = GoalStatus.PENDING  # 重新设为待执行
            print(f"[GoalScheduler] 目标降级: {goal_id} -> {downgraded_content}")
            return goal

        elif branch == "reroute":
            # 改道：修改目标描述，添加替代信息
            original_content = goal.content
            rerouted_content = f"{original_content}（改道）"
            goal.content = rerouted_content
            goal.defer_count = 0
            goal.status = GoalStatus.PENDING
            goal.metadata["rerouted_from"] = original_content
            print(f"[GoalScheduler] 目标改道: {goal_id} -> {rerouted_content}")
            return goal

        elif branch == "abandon":
            # 放弃：标记为 ABANDONED
            goal.status = GoalStatus.ABANDONED
            print(f"[GoalScheduler] 目标放弃: {goal_id} [{original_content}]")
            return None

        return goal

    # ─── Tick 推进 ───

    def tick_advance(self, character_name: str, tick: int) -> Dict:
        """
        Tick 推进处理 - 检查角色的执行中目标

        对于每个 EXECUTING 状态的日常目标：
        - 如果该 tick 未被完成，则延迟
        - 返回处理摘要

        Args:
            character_name: 角色名称
            tick: 当前 tick 编号

        Returns:
            处理摘要字典
        """
        daily_goals = self.get_character_goals(
            character_name, level=GoalLevel.DAILY, status=GoalStatus.EXECUTING
        )

        deferred = []
        completed = []
        still_executing = []

        for goal in daily_goals:
            if goal.status == GoalStatus.COMPLETED:
                completed.append(goal.id)
            elif goal.status == GoalStatus.EXECUTING:
                # 该 tick 未被完成，执行延迟
                self.defer_goal(goal.id, tick)
                if goal.status == GoalStatus.DEFERRED:
                    deferred.append(goal.id)
                else:
                    still_executing.append(goal.id)

        # 将 DEFERRED 的目标重新设为 PENDING（下个 tick 可重试）
        for gid in deferred:
            g = self.goals.get(gid)
            if g and g.status == GoalStatus.DEFERRED:
                g.status = GoalStatus.PENDING

        summary = {
            "character": character_name,
            "tick": tick,
            "total_executing": len(daily_goals),
            "completed": completed,
            "deferred": deferred,
            "still_executing": still_executing,
            "failed": [gid for gid in deferred
                       if self.goals.get(gid) and self.goals[gid].status == GoalStatus.ABANDONED],
        }
        return summary

    # ─── 目标层级查询 ───

    def get_goal_hierarchy(self, character_name: str) -> Dict:
        """
        获取角色的目标层级树结构

        返回格式：
        {
            "ultimate": [...],
            "stage": [...],
            "daily": [...],
        }

        每个目标包含其子目标列表，形成树形结构。

        Args:
            character_name: 角色名称

        Returns:
            目标层级树字典
        """
        result = {"ultimate": [], "stage": [], "daily": []}

        all_goals = self.get_character_goals(character_name)

        for goal in all_goals:
            node = {
                "id": goal.id,
                "content": goal.content,
                "status": goal.status.value,
                "level": goal.level.value,
                "defer_count": goal.defer_count,
                "children": [],
            }
            if goal.level == GoalLevel.ULTIMATE:
                result["ultimate"].append(node)
            elif goal.level == GoalLevel.STAGE:
                result["stage"].append(node)
            else:
                result["daily"].append(node)

        # 填充子节点引用
        for level in ("ultimate", "stage", "daily"):
            for node in result[level]:
                goal = self.goals.get(node["id"])
                if goal:
                    node["children"] = [
                        {
                            "id": cid,
                            "content": self.goals[cid].content,
                            "status": self.goals[cid].status.value,
                        }
                        for cid in goal.child_goal_ids
                        if cid in self.goals
                    ]

        return result

    def tick_advance_all(self, tick: int, character_names: List[str] = None) -> Dict:
        """批量推进所有（或指定）角色的目标

        Args:
            tick: 当前 tick 编号
            character_names: 要推进的角色名列表（None = 推进所有有目标的角色）

        Returns:
            汇总字典：{
                "total_characters": N,
                "total_new_goals": N,
                "total_deferred": N,
                "total_failed": N,
                "per_character": {char_name: summary}
            }
        """
        if character_names is None:
            character_names = list(self.character_goals.keys())

        total_new = 0
        total_deferred = 0
        total_failed = 0
        per_char = {}

        for name in character_names:
            summary = self.tick_advance(name, tick)
            per_char[name] = summary
            total_new += len(summary.get("new_goals", []))
            total_deferred += len(summary.get("deferred", []))
            total_failed += len(summary.get("failed", []))

        return {
            "total_characters": len(character_names),
            "total_new_goals": total_new,
            "total_deferred": total_deferred,
            "total_failed": total_failed,
            "per_character": per_char,
        }

    # ─── 父子目标验证 ───

    def validate_goal_hierarchy(self, goal_id: str = None) -> List[str]:
        """验证父子目标绑定的合法性

        检查点：
        - 父目标必须存在
        - 子目标的层级必须低于父目标（ultimate > stage > daily）
        - 不能出现循环引用
        - 子目标的 character_name 应与父目标一致（跨角色目标需显式标注）

        Args:
            goal_id: 验证单个目标（None = 验证全部）

        Returns:
            问题描述列表
        """
        issues = []
        level_rank = {"ultimate": 0, "stage": 1, "daily": 2}

        targets = [goal_id] if goal_id else list(self.goals.keys())

        for gid in targets:
            goal = self.goals.get(gid)
            if not goal:
                issues.append(f"目标 '{gid}' 不存在")
                continue

            # 父目标存在性
            if goal.parent_goal_id:
                parent = self.goals.get(goal.parent_goal_id)
                if not parent:
                    issues.append(
                        f"目标 '{goal.content}'({gid}) 的父目标 "
                        f"'{goal.parent_goal_id}' 不存在"
                    )
                    continue

                # 层级合理性（子目标层级应 <= 父目标层级，rank 值更大）
                child_rank = level_rank.get(goal.level.value, 99)
                parent_rank = level_rank.get(parent.level.value, 99)
                if child_rank < parent_rank:
                    issues.append(
                        f"层级不合理: 子目标 '{goal.content}'({goal.level.value}) "
                        f"层级高于父目标 '{parent.content}'({parent.level.value})"
                    )

                # 角色一致性
                if (goal.character_name and parent.character_name
                        and goal.character_name != parent.character_name):
                    issues.append(
                        f"跨角色父子目标: 子目标 '{goal.content}' 属于 "
                        f"'{goal.character_name}'，但父目标 '{parent.content}' 属于 "
                        f"'{parent.character_name}'（如属正常跨角色协作可忽略）"
                    )

        # 循环引用检测（全量时才做）
        if goal_id is None:
            cycles = self._detect_goal_cycles()
            for cycle in cycles:
                issues.append(f"目标循环引用: {' -> '.join(cycle)}")

        return issues

    def _detect_goal_cycles(self) -> List[List[str]]:
        """检测目标父子关系中的循环引用"""
        cycles = []
        visited = set()
        path = []

        def dfs(gid: str):
            if gid in path:
                idx = path.index(gid)
                cycles.append(path[idx:] + [gid])
                return
            if gid in visited:
                return
            visited.add(gid)
            path.append(gid)
            goal = self.goals.get(gid)
            if goal and goal.parent_goal_id:
                dfs(goal.parent_goal_id)
            path.pop()

        for gid in self.goals:
            dfs(gid)

        return cycles

    # ─── 序列化 ───

    def to_dict(self) -> dict:
        """序列化为字典"""
        return {
            "goals": {gid: g.to_dict() for gid, g in self.goals.items()},
            "character_goals": self.character_goals,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GoalScheduler":
        """从字典反序列化"""
        gs = cls()
        for gid, gd in data.get("goals", {}).items():
            goal = Goal.from_dict(gd)
            gs.goals[gid] = goal
        gs.character_goals = data.get("character_goals", {})
        return gs

    # ─── 统计 ───

    def get_stats(self) -> Dict:
        """返回目标调度器统计信息"""
        # 各状态目标数
        status_counts = {}
        for g in self.goals.values():
            s = g.status.value
            status_counts[s] = status_counts.get(s, 0) + 1

        # 各层级目标数
        level_counts = {}
        for g in self.goals.values():
            l = g.level.value
            level_counts[l] = level_counts.get(l, 0) + 1

        # 失败分支统计
        branch_counts = {}
        for g in self.goals.values():
            if g.failed_branch:
                branch_counts[g.failed_branch] = branch_counts.get(g.failed_branch, 0) + 1

        # 各角色的目标数
        char_counts = {
            name: len(gids) for name, gids in self.character_goals.items()
        }

        return {
            "total_goals": len(self.goals),
            "status_distribution": status_counts,
            "level_distribution": level_counts,
            "failed_branch_distribution": branch_counts,
            "character_goal_counts": char_counts,
            "has_swimlane_manager": self.swimlane_manager is not None,
        }
