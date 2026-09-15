"""
章节 SpecBuilder
从 FictionForge framework/spec_builder.py 提取，构建章节「写作规格」。
Spec 作为 LLM 调用的结构化参数集，控制叙事风格、节奏、视角等。

主要导出：
- Spec: 章节写作规格（style/mode/rhythm/density 等字段）
- SpecBuilder: 构建器类，从世界设定/角色/引擎配置生成 Spec
- build_spec_mechanical(): 纯机械层构建（不含 LLM）
- fields_spec_schema(): Spec 字段的可选值 schema
"""
from .spec_builder import (
    Spec,
    SpecBuilder,
    build_spec_mechanical,
    fields_spec_schema,
)

__all__ = [
    "Spec",
    "SpecBuilder",
    "build_spec_mechanical",
    "fields_spec_schema",
]
