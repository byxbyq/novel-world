# -*- coding: utf-8 -*-
"""反外部检测去AI味测试：结构扰动 / 全文重写 / 强制模式不空转"""

import sys
import os

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

import post_processor.ai_detector as ai_detector_mod
import post_processor.chapter_fixer as fixer_mod
from post_processor.de_ai_rules import apply_structure_perturb
from post_processor.chapter_fixer import anti_external_rewrite, local_fix_multi_round, humanize_rewrite


def _build_text():
    """5 段合成文本：2 个长段（含多个句子）+ 3 个相邻短段"""
    long1 = "他站在门口没有动。" * 6 + "走廊尽头的灯忽明忽暗，像是要灭了。" + "风从窗缝里挤进来，带着雨腥味。"
    long2 = "白墨把东西攥在手心。" * 6 + "指节发白了也没松开。" + "门外有人敲了三下，又停住。"
    return "\n\n".join([long1, "短段落一。", "短段落二而已。", "第三段也很短。", long2])


class TestStructurePerturb:
    def test_content_preserved(self):
        """任何扰动都不得改动文字内容（忽略空白）"""
        text = _build_text()
        import re
        for seed in range(15):
            result = apply_structure_perturb(text, seed=seed)
            assert re.sub(r'\s', '', result) == re.sub(r'\s', '', text), f"seed={seed} 内容被改动"

    def test_deterministic_with_seed(self):
        text = _build_text()
        assert apply_structure_perturb(text, seed=7) == apply_structure_perturb(text, seed=7)

    def test_changes_structure_for_some_seed(self):
        """至少存在某个种子能改变段落结构（拆段或合段）"""
        text = _build_text()
        changed = any(apply_structure_perturb(text, seed=s) != text for s in range(15))
        assert changed, "15 个种子均未产生结构变化"

    def test_short_text_untouched(self):
        assert apply_structure_perturb("太短了。", seed=1) == "太短了。"


class TestAntiExternalRewrite:
    """书斋 deai-deep 批量算法：3 段一批重写全部段落，temp=1.05"""

    def test_rewrites_all_paragraphs_in_batches(self, monkeypatch):
        """全部段落（含短段）按批重写，批次长度正常则接受"""
        import backend.ai_client as ai_mod
        calls = []

        def fake_chat(system_prompt=None, user_prompt=None, temperature=0.8,
                      max_tokens=2048, task="chat", on_chunk=None, **kw):
            calls.append(temperature)
            # 从提示词里截出【原文段落】后的批次文本原样返回（长度不变必过闸门）
            batch = user_prompt.split("【原文段落】\n")[1]
            return batch

        monkeypatch.setattr(ai_mod, "chat", fake_chat)
        text = _build_text()
        new_content, report = anti_external_rewrite(text)
        assert report["rewritten"] == 5   # 全部 5 段都参与重写
        assert report["failed"] == 0
        assert report["content_changed"] is False  # 原样返回→内容未变
        assert all(t == 1.05 for t in calls)  # 书斋同款温度
        assert len(calls) == 2  # 5 段 = 2 批（3+2）

    def test_batch_length_guard_rejects(self, monkeypatch):
        """批次结果长度异常时回退原文，失败段落计入 failed"""
        import backend.ai_client as ai_mod
        monkeypatch.setattr(ai_mod, "chat", lambda **kw: "太短")
        new_content, report = anti_external_rewrite(_build_text())
        assert report["rewritten"] == 0
        assert report["failed"] == 5   # 两批全拒，5 段全部计失败
        assert report["content_changed"] is False
        assert new_content == _build_text()  # 原文完整保留

    def test_short_content_untouched(self):
        content, report = anti_external_rewrite("短文本。")
        assert content == "短文本。"
        assert report["content_changed"] is False


class TestHumanizeRewrite:
    """书斋“去AI味”同款：全文粗粝重写，temp=1.3"""

    def test_success_changes_content(self, monkeypatch):
        import backend.ai_client as ai_mod
        calls = []

        def fake_chat(system_prompt=None, user_prompt=None, temperature=0.8,
                      max_tokens=2048, task="chat", on_chunk=None, **kw):
            calls.append(temperature)
            return "完全不同的重写版本。" * 20  # 长度在 50%~200% 内

        monkeypatch.setattr(ai_mod, "chat", fake_chat)
        new_content, report = humanize_rewrite(_build_text())
        assert report["success"] is True
        assert report["content_changed"] is True
        assert new_content != _build_text()
        assert calls == [1.3]  # 书斋同款温度

    def test_empty_result_falls_back(self, monkeypatch):
        import backend.ai_client as ai_mod
        monkeypatch.setattr(ai_mod, "chat", lambda **kw: "")
        new_content, report = humanize_rewrite(_build_text())
        assert report["success"] is False
        assert report["content_changed"] is False
        assert new_content == _build_text()

    def test_length_anomaly_falls_back(self, monkeypatch):
        import backend.ai_client as ai_mod
        monkeypatch.setattr(ai_mod, "chat", lambda **kw: "短。")
        new_content, report = humanize_rewrite(_build_text())
        assert report["success"] is False
        assert "长度异常" in report["reason"]
        assert new_content == _build_text()


class TestForceModeNoIdle:
    def test_force_continues_when_no_issues(self, monkeypatch):
        """自家检测零问题时，force 模式不得空转：应合成全局重写问题并调用修复"""
        monkeypatch.setattr(ai_detector_mod, "detect_ai_flavor", lambda c: {
            "score": 5, "ai_probability": 0, "issues": [], "level": "clean",
            "summary": "", "stats": {},
        })

        captured = []

        def fake_local_fix(content, flavor, max_fixes=5, dry_run=False,
                           aggressive=False, fixed_fingerprints=None):
            captured.append({"issues": flavor.get("issues", []), "aggressive": aggressive})
            return content, {"fixed": 0, "content_changed": False, "results": [], "summary": ""}

        monkeypatch.setattr(fixer_mod, "local_fix_from_flavor", fake_local_fix)

        long_text = "这是一段足够长的测试文本。" * 12
        _, report = local_fix_multi_round(
            long_text, max_rounds=2, force=True, apply_rules_first=False
        )
        assert len(captured) == 2, f"force 模式应每轮都执行修复，实际 {len(captured)} 轮"
        for c in captured:
            assert c["aggressive"] is True, "force 模式应全程激进"
            assert any(i.get("type") == "uniform_paragraphs" for i in c["issues"]), \
                "零问题时应合成全局重写问题"

    def test_non_force_stops_when_no_issues(self, monkeypatch):
        """非 force 模式下零问题应立即停止（保持原有省 Token 行为）"""
        monkeypatch.setattr(ai_detector_mod, "detect_ai_flavor", lambda c: {
            "score": 5, "ai_probability": 0, "issues": [], "level": "clean",
            "summary": "", "stats": {},
        })
        captured = []

        def fake_local_fix(content, flavor, **kw):
            captured.append(1)
            return content, {"fixed": 0, "content_changed": False, "results": [], "summary": ""}

        monkeypatch.setattr(fixer_mod, "local_fix_from_flavor", fake_local_fix)

        long_text = "这是一段足够长的测试文本。" * 12
        _, report = local_fix_multi_round(long_text, max_rounds=3, force=False, apply_rules_first=False)
        assert len(captured) == 0, "非 force 且零问题不应调用 AI 修复"
