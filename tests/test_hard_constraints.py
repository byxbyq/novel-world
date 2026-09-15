#!/usr/bin/env python3
"""
test_hard_constraints.py — 硬约束/质量门禁单元测试。

测试覆盖：
- FORBIDDEN_WORDS 合并后数量
- FORBIDDEN_PLOTS 合并后数量
- build_narrative_rules 生成注入文本
- 禁词/禁桥段在 prompt 注入中可见
"""
import sys
import os

NOVEL_WORLD = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "novel_world")
if NOVEL_WORLD not in sys.path:
    sys.path.insert(0, NOVEL_WORLD)

from engine.quality.constants import (
    FORBIDDEN_WORDS,
    FORBIDDEN_PLOTS,
    build_narrative_rules,
)


def test_forbidden_words_count():
    """合并后 FORBIDDEN_WORDS≥20项。"""
    n = len(FORBIDDEN_WORDS)
    assert n >= 20, f"禁词数量应≥20, actual={n}"
    # 确认书斋V66新增项存在
    v66_words = ["微微一笑", "他缓缓说道", "她淡淡一笑", "一股暖流"]
    for w in v66_words:
        assert w in FORBIDDEN_WORDS, f"书斋V66禁词 [{w}] 缺失"
    print(f"  ✓ constants: FORBIDDEN_WORDS={n} 项 (含V66 4项)")


def test_forbidden_plots_count():
    """合并后 FORBIDDEN_PLOTS≥9项。"""
    n = len(FORBIDDEN_PLOTS)
    assert n >= 9, f"禁桥段数量应≥9, actual={n}"
    v66_plots = ["主角被动等待救援", "每段对话以XX说开头", "结尾预告句式"]
    for p in v66_plots:
        found = any(p in item for item in FORBIDDEN_PLOTS)
        assert found, f"书斋V66禁桥段 [{p}] 缺失"
    print(f"  ✓ constants: FORBIDDEN_PLOTS={n} 项 (含V66 3项)")


def test_build_narrative_rules():
    """build_narrative_rules 生成有效注入文本。"""
    rules = build_narrative_rules()
    assert isinstance(rules, str)
    assert len(rules) > 100
    # 禁词应出现在规则中
    assert "眼中闪过一丝" in rules
    # 禁桥段应出现
    assert "天降救兵" in rules
    # 写作规范应包含
    assert "写作规范" in rules
    print(f"  ✓ constants: build_narrative_rules 长度={len(rules)}")


def test_forbidden_words_no_duplicates():
    """禁词列表无重复。"""
    assert len(FORBIDDEN_WORDS) == len(set(FORBIDDEN_WORDS))
    print("  ✓ constants: 禁词列表无重复")


def test_forbidden_plots_no_duplicates():
    """禁桥段列表无重复（按前10字符去重）。"""
    # 桥段描述较长，用开头字符去重
    prefixes = [p[:10] for p in FORBIDDEN_PLOTS]
    assert len(prefixes) == len(set(prefixes)), f"禁桥段前缀重复: {prefixes}"
    print("  ✓ constants: 禁桥段无前缀重复")


if __name__ == "__main__":
    print("=" * 50)
    print("  硬约束/质量门禁单元测试")
    print("=" * 50)
    print()

    tests = [
        test_forbidden_words_count,
        test_forbidden_plots_count,
        test_build_narrative_rules,
        test_forbidden_words_no_duplicates,
        test_forbidden_plots_no_duplicates,
    ]

    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"  ✗ {t.__name__}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print()
    print(f"结果: {passed}/{len(tests)} 通过", end="")
    if failed:
        print(f", {failed} 失败", end="")
    print()
    sys.exit(0 if failed == 0 else 1)
