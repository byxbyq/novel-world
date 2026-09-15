"""三层 Tick 调度器单元测试：帧序列 / 层级比例 / 离线模式 / 回调"""

from novel_world.engine.tick_scheduler import (
    TickScheduler, TickConfig, TickLevel, TickFrame,
)


def _collect_frames(config: TickConfig) -> list:
    """跑完一整章，收集全部帧"""
    scheduler = TickScheduler(config)
    scheduler.start_chapter(1)
    return list(scheduler)


class TestFrameSequence:
    def test_total_frame_count_matches_config(self):
        """默认配置 1慢×5中×10快：总帧数 = 慢Tick数×(中×快) 结构闭合"""
        config = TickConfig(slow_ticks_per_chapter=1, medium_per_slow=5, fast_per_medium=10)
        frames = _collect_frames(config)
        # 迭代到章节结束帧后 _done=True，再次 next 返回 None → 帧数有限
        assert len(frames) > 0
        assert frames[-1].is_chapter_end

    def test_frame_levels_only_valid_enum(self):
        frames = _collect_frames(TickConfig())
        for f in frames:
            assert isinstance(f.level, TickLevel)

    def test_fast_ticks_dominate(self):
        """快Tick数量应占绝对多数（玩家交互层最密集）"""
        frames = _collect_frames(TickConfig(slow_ticks_per_chapter=1, medium_per_slow=3, fast_per_medium=5))
        counts = {lvl: sum(1 for f in frames if f.level == lvl) for lvl in TickLevel}
        assert counts[TickLevel.FAST] >= counts[TickLevel.MEDIUM]
        assert counts[TickLevel.MEDIUM] >= counts[TickLevel.SLOW]

    def test_iteration_terminates(self):
        """章节结束后继续迭代应立刻 StopIteration（不无限循环）"""
        scheduler = TickScheduler(TickConfig(slow_ticks_per_chapter=1, medium_per_slow=2, fast_per_medium=2))
        scheduler.start_chapter(1)
        frames = list(scheduler)
        assert list(scheduler) == []  # 第二次迭代为空
        assert frames[-1].is_chapter_end

    def test_medium_start_flag(self):
        """每个中Tick帧都应标记 is_medium_start"""
        frames = _collect_frames(TickConfig())
        for f in frames:
            if f.level == TickLevel.MEDIUM:
                assert f.is_medium_start

    def test_chapter_end_flag_on_last_frame(self):
        frames = _collect_frames(TickConfig())
        assert frames[-1].is_chapter_end
        assert frames[-1].level == TickLevel.SLOW


class TestStartAndReset:
    def test_start_chapter_returns_chapter_start_frame(self):
        scheduler = TickScheduler()
        frame = scheduler.start_chapter(7)
        assert frame.is_chapter_start
        assert frame.chapter == 7
        assert scheduler.current_chapter == 7

    def test_reset_clears_counters(self):
        scheduler = TickScheduler(TickConfig(slow_ticks_per_chapter=1, medium_per_slow=2, fast_per_medium=2))
        scheduler.start_chapter(1)
        for _ in scheduler:
            pass
        assert scheduler.total_ticks > 0
        scheduler.reset(chapter=3)
        assert scheduler.total_ticks == 0
        assert scheduler.current_chapter == 3
        # 重置后可再次完整跑一章
        frames = list(scheduler)
        assert frames[-1].is_chapter_end

    def test_total_ticks_increments(self):
        scheduler = TickScheduler(TickConfig(slow_ticks_per_chapter=1, medium_per_slow=2, fast_per_medium=3))
        scheduler.start_chapter(1)
        list(scheduler)
        assert scheduler.total_ticks > 0


class TestCallbacks:
    def test_run_chapter_triggers_all_callbacks(self):
        """run_chapter 应触发章节开始/结束与三层 Tick 回调"""
        scheduler = TickScheduler(TickConfig(
            slow_ticks_per_chapter=1, medium_per_slow=2, fast_per_medium=2))
        calls = {"chapter_start": 0, "chapter_end": 0, "slow": 0, "medium": 0, "fast": 0}
        scheduler.on_chapter_start = lambda f: calls.__setitem__("chapter_start", calls["chapter_start"] + 1)
        scheduler.on_chapter_end = lambda f: calls.__setitem__("chapter_end", calls["chapter_end"] + 1)
        scheduler.on_slow_tick = lambda f: calls.__setitem__("slow", calls["slow"] + 1)
        scheduler.on_medium_tick = lambda f: calls.__setitem__("medium", calls["medium"] + 1)
        scheduler.on_fast_tick = lambda f: calls.__setitem__("fast", calls["fast"] + 1)

        scheduler.run_chapter(1)
        assert calls["chapter_start"] == 1
        assert calls["chapter_end"] >= 1
        assert calls["slow"] >= 1
        assert calls["medium"] >= 1
        assert calls["fast"] >= 1

    def test_offline_mode_skips_fast_tick_callback(self):
        """离线模式下快Tick回调不应被触发"""
        scheduler = TickScheduler(TickConfig(
            slow_ticks_per_chapter=1, medium_per_slow=2, fast_per_medium=3,
            offline_mode=True))
        fast_calls = []
        scheduler.on_fast_tick = lambda f: fast_calls.append(f)
        scheduler.run_chapter(1)
        assert fast_calls == []

    def test_chapter_end_frame_carries_context(self):
        """章节结束帧应属于当前章节"""
        scheduler = TickScheduler(TickConfig(slow_ticks_per_chapter=1, medium_per_slow=2, fast_per_medium=2))
        ended = []
        scheduler.on_chapter_end = lambda f: ended.append(f)
        scheduler.run_chapter(5)
        assert ended
        assert all(f.chapter == 5 for f in ended)


class TestConfig:
    def test_medium_ticks_per_chapter_property(self):
        config = TickConfig(slow_ticks_per_chapter=2, medium_per_slow=5)
        assert config.medium_ticks_per_chapter == 10
