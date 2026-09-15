# -*- coding: utf-8 -*-
"""
剧情节点管理 - 多主题适配系统
"""
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field
from enum import Enum
import random


class GrowthStage(Enum):
    """成长阶段"""
    INFANT = "infant"
    GROWING = "growing"
    ADULT = "adult"


class ThemeType(Enum):
    """游戏主题"""
    DAILY = "日常"
    CULTIVATION = "修仙"
    FANTASY = "奇幻"
    APOCALYPSE = "末世"
    SCIFI = "科幻"
    HORROR = "恐怖"
    MYTHOLOGY = "神话"
    CUSTOM = "自定义"


@dataclass
class PlotNode:
    """剧情节点"""
    name: str
    description: str
    required_elements: List[str] = field(default_factory=list)
    next_nodes: List[str] = field(default_factory=list)
    is_ending: bool = False
    applicable_stages: Set[GrowthStage] = field(default_factory=lambda: {GrowthStage.INFANT, GrowthStage.GROWING, GrowthStage.ADULT})


@dataclass
class ConflictTrigger:
    """冲突触发器"""
    name: str
    description: str
    trigger_probability: float
    applicable_nodes: List[str] = field(default_factory=list)
    applicable_stages: Set[GrowthStage] = field(default_factory=lambda: {GrowthStage.INFANT, GrowthStage.GROWING, GrowthStage.ADULT})


def _get_daily_nodes():
    """日常主题节点"""
    return {
        # 婴儿期
        "婴儿-苏醒": PlotNode("婴儿-苏醒", "婴儿睁开眼睛", ["新动作", "新情绪"], ["婴儿-观察", "婴儿-哭闹"], False, {GrowthStage.INFANT}),
        "婴儿-观察": PlotNode("婴儿-观察", "婴儿观察环境", ["新动作", "新情绪"], ["婴儿-互动", "婴儿-学习"], False, {GrowthStage.INFANT}),
        "婴儿-哭闹": PlotNode("婴儿-哭闹", "婴儿哭闹", ["新动作", "新情绪"], ["婴儿-安抚", "婴儿-观察"], False, {GrowthStage.INFANT}),
        "婴儿-安抚": PlotNode("婴儿-安抚", "婴儿被安抚", ["新对话", "新情绪"], ["婴儿-互动", "婴儿-学习"], False, {GrowthStage.INFANT}),
        "婴儿-互动": PlotNode("婴儿-互动", "婴儿与家人互动", ["新对话", "新动作"], ["婴儿-学习", "婴儿-成长"], False, {GrowthStage.INFANT}),
        "婴儿-学习": PlotNode("婴儿-学习", "婴儿学习新技能", ["新动作", "新情绪"], ["婴儿-互动", "婴儿-成长"], False, {GrowthStage.INFANT}),
        "婴儿-成长": PlotNode("婴儿-成长", "婴儿成长里程碑", ["新动作", "新情绪"], ["阶段过渡"], False, {GrowthStage.INFANT}),
        # 成长期
        "成长-上学": PlotNode("成长-上学", "开始上学", ["新动作", "新情绪"], ["成长-学习", "成长-交友"], False, {GrowthStage.GROWING}),
        "成长-学习": PlotNode("成长-学习", "学习新知识", ["新动作", "新情绪"], ["成长-考试", "成长-交友"], False, {GrowthStage.GROWING}),
        "成长-交友": PlotNode("成长-交友", "结交朋友", ["新对话", "新情绪"], ["成长-互动", "成长-冲突"], False, {GrowthStage.GROWING}),
        "成长-互动": PlotNode("成长-互动", "与朋友玩耍", ["新对话", "新动作"], ["成长-学习", "成长-考试"], False, {GrowthStage.GROWING}),
        "成长-考试": PlotNode("成长-考试", "面临考试", ["新动作", "新情绪"], ["成长-成绩", "成长-挫折"], False, {GrowthStage.GROWING}),
        "成长-成绩": PlotNode("成长-成绩", "考试结果", ["新情绪", "新对话"], ["成长-学习", "成长-压力"], False, {GrowthStage.GROWING}),
        "成长-压力": PlotNode("成长-压力", "学业压力", ["新情绪", "新动作"], ["成长-调节", "成长-挫折"], False, {GrowthStage.GROWING}),
        "成长-调节": PlotNode("成长-调节", "调节情绪", ["新动作", "新情绪"], ["成长-学习", "成长-成熟"], False, {GrowthStage.GROWING}),
        "成长-冲突": PlotNode("成长-冲突", "与朋友矛盾", ["新对话", "新情绪"], ["成长-和解", "成长-挫折"], False, {GrowthStage.GROWING}),
        "成长-和解": PlotNode("成长-和解", "与朋友和解", ["新对话", "新情绪"], ["成长-互动", "成长-学习"], False, {GrowthStage.GROWING}),
        "成长-挫折": PlotNode("成长-挫折", "遭遇挫折", ["新情绪", "新动作"], ["成长-克服", "成长-求助"], False, {GrowthStage.GROWING}),
        "成长-克服": PlotNode("成长-克服", "克服困难", ["新动作", "新情绪"], ["成长-学习", "成长-成熟"], False, {GrowthStage.GROWING}),
        "成长-求助": PlotNode("成长-求助", "向他人求助", ["新对话", "新动作"], ["成长-克服", "成长-互动"], False, {GrowthStage.GROWING}),
        "成长-成熟": PlotNode("成长-成熟", "逐渐成熟", ["新动作", "新情绪"], ["阶段过渡"], False, {GrowthStage.GROWING}),
        # 成年期
        "成年-毕业": PlotNode("成年-毕业", "从学校毕业", ["新动作", "新情绪"], ["成年-求职", "成年-迷茫"], False, {GrowthStage.ADULT}),
        "成年-求职": PlotNode("成年-求职", "找工作", ["新动作", "新情绪"], ["成年-工作", "成年-挫折"], False, {GrowthStage.ADULT}),
        "成年-工作": PlotNode("成年-工作", "开始工作", ["新动作", "新情绪"], ["成年-事业", "成年-人际"], False, {GrowthStage.ADULT}),
        "成年-事业": PlotNode("成年-事业", "事业发展", ["新动作", "新情绪"], ["成年-升职", "成年-瓶颈"], False, {GrowthStage.ADULT}),
        "成年-升职": PlotNode("成年-升职", "获得升职", ["新情绪", "新对话"], ["成年-事业", "成年-压力"], False, {GrowthStage.ADULT}),
        "成年-瓶颈": PlotNode("成年-瓶颈", "事业瓶颈", ["新情绪", "新动作"], ["成年-突破", "成年-转型"], False, {GrowthStage.ADULT}),
        "成年-突破": PlotNode("成年-突破", "突破瓶颈", ["新动作", "新情绪"], ["成年-事业", "成年-成就"], False, {GrowthStage.ADULT}),
        "成年-转型": PlotNode("成年-转型", "职业转型", ["新动作", "新情绪"], ["成年-学习", "成年-迷茫"], False, {GrowthStage.ADULT}),
        "成年-学习": PlotNode("成年-学习", "学习新技能", ["新动作", "新情绪"], ["成年-事业", "成年-突破"], False, {GrowthStage.ADULT}),
        "成年-人际": PlotNode("成年-人际", "职场人际", ["新对话", "新情绪"], ["成年-合作", "成年-冲突"], False, {GrowthStage.ADULT}),
        "成年-合作": PlotNode("成年-合作", "与同事合作", ["新对话", "新动作"], ["成年-事业", "成年-人际"], False, {GrowthStage.ADULT}),
        "成年-冲突": PlotNode("成年-冲突", "职场冲突", ["新对话", "新情绪"], ["成年-解决", "成年-压力"], False, {GrowthStage.ADULT}),
        "成年-解决": PlotNode("成年-解决", "解决冲突", ["新对话", "新动作"], ["成年-人际", "成年-事业"], False, {GrowthStage.ADULT}),
        "成年-压力": PlotNode("成年-压力", "工作压力", ["新情绪", "新动作"], ["成年-调节", "成年-挫折"], False, {GrowthStage.ADULT}),
        "成年-调节": PlotNode("成年-调节", "调节压力", ["新动作", "新情绪"], ["成年-事业", "成年-生活"], False, {GrowthStage.ADULT}),
        "成年-生活": PlotNode("成年-生活", "工作生活平衡", ["新动作", "新情绪"], ["成年-爱好", "成年-家庭"], False, {GrowthStage.ADULT}),
        "成年-爱好": PlotNode("成年-爱好", "培养爱好", ["新动作", "新情绪"], ["成年-生活", "成年-成就"], False, {GrowthStage.ADULT}),
        "成年-家庭": PlotNode("成年-家庭", "家庭生活", ["新对话", "新情绪"], ["成年-责任", "成年-温馨"], False, {GrowthStage.ADULT}),
        "成年-责任": PlotNode("成年-责任", "承担责任", ["新动作", "新情绪"], ["成年-成就", "成年-压力"], False, {GrowthStage.ADULT}),
        "成年-温馨": PlotNode("成年-温馨", "家庭温馨", ["新情绪", "新对话"], ["成年-生活", "成年-成就"], False, {GrowthStage.ADULT}),
        "成年-迷茫": PlotNode("成年-迷茫", "人生迷茫", ["新情绪", "新动作"], ["成年-思考", "成年-求助"], False, {GrowthStage.ADULT}),
        "成年-思考": PlotNode("成年-思考", "思考人生", ["新情绪", "新动作"], ["成年-决定", "成年-迷茫"], False, {GrowthStage.ADULT}),
        "成年-决定": PlotNode("成年-决定", "做出决定", ["新动作", "新情绪"], ["成年-行动", "成年-犹豫"], False, {GrowthStage.ADULT}),
        "成年-行动": PlotNode("成年-行动", "付诸行动", ["新动作", "新情绪"], ["成年-成就", "成年-挫折"], False, {GrowthStage.ADULT}),
        "成年-犹豫": PlotNode("成年-犹豫", "犹豫不决", ["新情绪", "新动作"], ["成年-决定", "成年-迷茫"], False, {GrowthStage.ADULT}),
        "成年-求助": PlotNode("成年-求助", "向他人求助", ["新对话", "新动作"], ["成年-支持", "成年-孤独"], False, {GrowthStage.ADULT}),
        "成年-支持": PlotNode("成年-支持", "获得支持", ["新对话", "新情绪"], ["成年-行动", "成年-温馨"], False, {GrowthStage.ADULT}),
        "成年-孤独": PlotNode("成年-孤独", "感到孤独", ["新情绪", "新动作"], ["成年-社交", "成年-思考"], False, {GrowthStage.ADULT}),
        "成年-社交": PlotNode("成年-社交", "社交活动", ["新对话", "新动作"], ["成年-交友", "成年-生活"], False, {GrowthStage.ADULT}),
        "成年-交友": PlotNode("成年-交友", "结交朋友", ["新对话", "新情绪"], ["成年-社交", "成年-支持"], False, {GrowthStage.ADULT}),
        "成年-成就": PlotNode("成年-成就", "取得成就", ["新动作", "新情绪"], ["成年-满足", "成年-事业"], False, {GrowthStage.ADULT}),
        "成年-满足": PlotNode("成年-满足", "感到满足", ["新情绪", "新动作"], ["剧情结尾", "成年-生活"], False, {GrowthStage.ADULT}),
        "成年-挫折": PlotNode("成年-挫折", "遭遇挫折", ["新情绪", "新动作"], ["成年-坚持", "成年-求助"], False, {GrowthStage.ADULT}),
        "成年-坚持": PlotNode("成年-坚持", "坚持不懈", ["新动作", "新情绪"], ["成年-突破", "成年-挫折"], False, {GrowthStage.ADULT}),
    }

def _get_daily_conflicts():
    """日常主题冲突"""
    return [
        ConflictTrigger("饥饿", "婴儿感到饥饿", 0.25, ["婴儿-观察", "婴儿-互动"], {GrowthStage.INFANT}),
        ConflictTrigger("生病", "婴儿生病", 0.15, ["婴儿-学习", "婴儿-互动"], {GrowthStage.INFANT}),
        ConflictTrigger("考试失利", "考试成绩不理想", 0.25, ["成长-考试", "成长-学习"], {GrowthStage.GROWING}),
        ConflictTrigger("朋友误解", "被朋友误解", 0.20, ["成长-互动", "成长-交友"], {GrowthStage.GROWING}),
        ConflictTrigger("家庭矛盾", "与家人矛盾", 0.15, ["成长-互动", "成长-学习"], {GrowthStage.GROWING}),
        ConflictTrigger("工作失误", "工作失误", 0.20, ["成年-工作", "成年-事业"], {GrowthStage.ADULT}),
        ConflictTrigger("人际摩擦", "人际摩擦", 0.25, ["成年-人际", "成年-合作"], {GrowthStage.ADULT}),
        ConflictTrigger("健康问题", "健康问题", 0.10, ["成年-压力", "成年-生活"], {GrowthStage.ADULT}),
        ConflictTrigger("经济压力", "经济压力", 0.15, ["成年-事业", "成年-生活"], {GrowthStage.ADULT}),
    ]

def _get_cultivation_nodes():
    """修仙主题节点"""
    return {
        # 婴儿期
        "婴儿-降生": PlotNode("婴儿-降生", "降生于修仙世家", ["新动作", "新情绪"], ["婴儿-灵根", "婴儿-凡体"], False, {GrowthStage.INFANT}),
        "婴儿-灵根": PlotNode("婴儿-灵根", "测出灵根", ["新情绪", "新对话"], ["婴儿-启蒙", "婴儿-期待"], False, {GrowthStage.INFANT}),
        "婴儿-凡体": PlotNode("婴儿-凡体", "测出凡体", ["新情绪", "新对话"], ["婴儿-不甘", "婴儿-平凡"], False, {GrowthStage.INFANT}),
        "婴儿-启蒙": PlotNode("婴儿-启蒙", "修仙启蒙", ["新动作", "新情绪"], ["婴儿-感悟", "婴儿-修炼"], False, {GrowthStage.INFANT}),
        "婴儿-期待": PlotNode("婴儿-期待", "期待仙途", ["新情绪", "新动作"], ["婴儿-启蒙", "婴儿-感悟"], False, {GrowthStage.INFANT}),
        "婴儿-不甘": PlotNode("婴儿-不甘", "不甘平凡", ["新情绪", "新动作"], ["婴儿-逆天", "婴儿-平凡"], False, {GrowthStage.INFANT}),
        "婴儿-逆天": PlotNode("婴儿-逆天", "决心逆天改命", ["新动作", "新情绪"], ["婴儿-苦修", "阶段过渡"], False, {GrowthStage.INFANT}),
        "婴儿-苦修": PlotNode("婴儿-苦修", "刻苦修炼", ["新动作", "新情绪"], ["阶段过渡"], False, {GrowthStage.INFANT}),
        "婴儿-平凡": PlotNode("婴儿-平凡", "接受平凡", ["新情绪", "新动作"], ["阶段过渡"], False, {GrowthStage.INFANT}),
        "婴儿-感悟": PlotNode("婴儿-感悟", "感悟灵气", ["新动作", "新情绪"], ["婴儿-修炼", "婴儿-启蒙"], False, {GrowthStage.INFANT}),
        "婴儿-修炼": PlotNode("婴儿-修炼", "引气入体", ["新动作", "新情绪"], ["阶段过渡"], False, {GrowthStage.INFANT}),
        # 成长期
        "成长-拜师": PlotNode("成长-拜师", "拜入仙门", ["新动作", "新情绪"], ["成长-学艺", "成长-考验"], False, {GrowthStage.GROWING}),
        "成长-学艺": PlotNode("成长-学艺", "学习功法", ["新动作", "新情绪"], ["成长-修炼", "成长-历练"], False, {GrowthStage.GROWING}),
        "成长-修炼": PlotNode("成长-修炼", "勤修苦练", ["新动作", "新情绪"], ["成长-突破", "成长-瓶颈"], False, {GrowthStage.GROWING}),
        "成长-突破": PlotNode("成长-突破", "境界突破", ["新动作", "新情绪"], ["成长-稳固", "成长-历练"], False, {GrowthStage.GROWING}),
        "成长-稳固": PlotNode("成长-稳固", "稳固境界", ["新动作", "新情绪"], ["成长-修炼", "成长-历练"], False, {GrowthStage.GROWING}),
        "成长-瓶颈": PlotNode("成长-瓶颈", "修炼瓶颈", ["新情绪", "新动作"], ["成长-顿悟", "成长-求助"], False, {GrowthStage.GROWING}),
        "成长-顿悟": PlotNode("成长-顿悟", "顿悟突破", ["新动作", "新情绪"], ["成长-突破", "成长-历练"], False, {GrowthStage.GROWING}),
        "成长-历练": PlotNode("成长-历练", "下山历练", ["新动作", "新情绪"], ["成长-遇敌", "成长-机缘"], False, {GrowthStage.GROWING}),
        "成长-遇敌": PlotNode("成长-遇敌", "遭遇敌人", ["新动作", "新情绪"], ["成长-战斗", "成长-逃遁"], False, {GrowthStage.GROWING}),
        "成长-战斗": PlotNode("成长-战斗", "战斗", ["新动作", "新情绪"], ["成长-胜利", "成长-受伤"], False, {GrowthStage.GROWING}),
        "成长-胜利": PlotNode("成长-胜利", "战胜敌人", ["新情绪", "新动作"], ["成长-收获", "成长-历练"], False, {GrowthStage.GROWING}),
        "成长-受伤": PlotNode("成长-受伤", "战斗受伤", ["新情绪", "新动作"], ["成长-疗伤", "成长-逃遁"], False, {GrowthStage.GROWING}),
        "成长-疗伤": PlotNode("成长-疗伤", "疗伤", ["新动作", "新情绪"], ["成长-历练", "成长-修炼"], False, {GrowthStage.GROWING}),
        "成长-逃遁": PlotNode("成长-逃遁", "逃离危险", ["新动作", "新情绪"], ["成长-历练", "成长-修炼"], False, {GrowthStage.GROWING}),
        "成长-机缘": PlotNode("成长-机缘", "遇到机缘", ["新动作", "新情绪"], ["成长-获得", "成长-历练"], False, {GrowthStage.GROWING}),
        "成长-获得": PlotNode("成长-获得", "获得造化", ["新动作", "新情绪"], ["成长-修炼", "阶段过渡"], False, {GrowthStage.GROWING}),
        "成长-考验": PlotNode("成长-考验", "宗门考验", ["新动作", "新情绪"], ["成长-学艺", "成长-淘汰"], False, {GrowthStage.GROWING}),
        "成长-淘汰": PlotNode("成长-淘汰", "考验失败", ["新情绪", "新动作"], ["成长-坚持", "成长-放弃"], False, {GrowthStage.GROWING}),
        "成长-坚持": PlotNode("成长-坚持", "坚持不懈", ["新动作", "新情绪"], ["成长-学艺", "成长-考验"], False, {GrowthStage.GROWING}),
        "成长-放弃": PlotNode("成长-放弃", "放弃修仙", ["新情绪", "新动作"], ["阶段过渡"], False, {GrowthStage.GROWING}),
        "成长-求助": PlotNode("成长-求助", "向师长求助", ["新对话", "新动作"], ["成长-顿悟", "成长-修炼"], False, {GrowthStage.GROWING}),
        "成长-收获": PlotNode("成长-收获", "收获战利品", ["新动作", "新情绪"], ["成长-历练", "成长-修炼"], False, {GrowthStage.GROWING}),
        # 成年期
        "成年-筑基": PlotNode("成年-筑基", "筑基成功", ["新动作", "新情绪"], ["成年-结丹", "成年-稳固"], False, {GrowthStage.ADULT}),
        "成年-结丹": PlotNode("成年-结丹", "结成金丹", ["新动作", "新情绪"], ["成年-元婴", "成年-失败"], False, {GrowthStage.ADULT}),
        "成年-元婴": PlotNode("成年-元婴", "突破元婴", ["新动作", "新情绪"], ["成年-化神", "成年-稳固"], False, {GrowthStage.ADULT}),
        "成年-化神": PlotNode("成年-化神", "突破化神", ["新动作", "新情绪"], ["成年-渡劫", "成年-稳固"], False, {GrowthStage.ADULT}),
        "成年-渡劫": PlotNode("成年-渡劫", "准备渡劫", ["新动作", "新情绪"], ["成年-飞升", "成年-陨落"], False, {GrowthStage.ADULT}),
        "成年-飞升": PlotNode("成年-飞升", "渡劫飞升", ["新动作", "新情绪"], ["剧情结尾"], False, {GrowthStage.ADULT}),
        "成年-陨落": PlotNode("成年-陨落", "渡劫失败", ["新情绪", "新动作"], ["剧情结尾"], False, {GrowthStage.ADULT}),
        "成年-稳固": PlotNode("成年-稳固", "稳固境界", ["新动作", "新情绪"], ["成年-修炼", "成年-历练"], False, {GrowthStage.ADULT}),
        "成年-失败": PlotNode("成年-失败", "突破失败", ["新情绪", "新动作"], ["成年-重修", "成年-放弃"], False, {GrowthStage.ADULT}),
        "成年-重修": PlotNode("成年-重修", "重新修炼", ["新动作", "新情绪"], ["成年-结丹", "成年-稳固"], False, {GrowthStage.ADULT}),
        "成年-放弃": PlotNode("成年-放弃", "放弃突破", ["新情绪", "新动作"], ["成年-历练", "剧情结尾"], False, {GrowthStage.ADULT}),
        "成年-修炼": PlotNode("成年-修炼", "继续修炼", ["新动作", "新情绪"], ["成年-突破", "成年-瓶颈"], False, {GrowthStage.ADULT}),
        "成年-突破": PlotNode("成年-突破", "境界突破", ["新动作", "新情绪"], ["成年-稳固", "成年-历练"], False, {GrowthStage.ADULT}),
        "成年-瓶颈": PlotNode("成年-瓶颈", "遇到瓶颈", ["新情绪", "新动作"], ["成年-顿悟", "成年-历练"], False, {GrowthStage.ADULT}),
        "成年-顿悟": PlotNode("成年-顿悟", "顿悟突破", ["新动作", "新情绪"], ["成年-突破", "成年-修炼"], False, {GrowthStage.ADULT}),
        "成年-历练": PlotNode("成年-历练", "外出历练", ["新动作", "新情绪"], ["成年-遇敌", "成年-机缘"], False, {GrowthStage.ADULT}),
        "成年-遇敌": PlotNode("成年-遇敌", "遭遇强敌", ["新动作", "新情绪"], ["成年-战斗", "成年-逃遁"], False, {GrowthStage.ADULT}),
        "成年-战斗": PlotNode("成年-战斗", "战斗", ["新动作", "新情绪"], ["成年-胜利", "成年-受伤"], False, {GrowthStage.ADULT}),
        "成年-胜利": PlotNode("成年-胜利", "战胜敌人", ["新情绪", "新动作"], ["成年-收获", "成年-历练"], False, {GrowthStage.ADULT}),
        "成年-受伤": PlotNode("成年-受伤", "战斗受伤", ["新情绪", "新动作"], ["成年-疗伤", "成年-逃遁"], False, {GrowthStage.ADULT}),
        "成年-疗伤": PlotNode("成年-疗伤", "疗伤", ["新动作", "新情绪"], ["成年-修炼", "成年-历练"], False, {GrowthStage.ADULT}),
        "成年-逃遁": PlotNode("成年-逃遁", "逃离危险", ["新动作", "新情绪"], ["成年-历练", "成年-修炼"], False, {GrowthStage.ADULT}),
        "成年-机缘": PlotNode("成年-机缘", "遇到机缘", ["新动作", "新情绪"], ["成年-获得", "成年-历练"], False, {GrowthStage.ADULT}),
        "成年-获得": PlotNode("成年-获得", "获得造化", ["新动作", "新情绪"], ["成年-修炼", "成年-突破"], False, {GrowthStage.ADULT}),
        "成年-收获": PlotNode("成年-收获", "收获战利品", ["新动作", "新情绪"], ["成年-历练", "成年-修炼"], False, {GrowthStage.ADULT}),
    }

def _get_cultivation_conflicts():
    """修仙主题冲突"""
    return [
        ConflictTrigger("天劫预警", "天劫将来", 0.15, ["成年-修炼", "成年-稳固"], {GrowthStage.ADULT}),
        ConflictTrigger("心魔入侵", "心魔入侵", 0.20, ["成年-修炼", "成年-瓶颈"], {GrowthStage.ADULT}),
        ConflictTrigger("仇家寻仇", "仇家寻仇", 0.25, ["成年-历练", "成年-修炼"], {GrowthStage.ADULT}),
        ConflictTrigger("宗门危机", "宗门危机", 0.15, ["成长-学艺", "成长-历练"], {GrowthStage.GROWING}),
        ConflictTrigger("资源匮乏", "资源不足", 0.20, ["成长-修炼", "成年-修炼"], {GrowthStage.GROWING, GrowthStage.ADULT}),
        ConflictTrigger("走火入魔", "走火入魔", 0.10, ["成长-修炼", "成年-修炼"], {GrowthStage.GROWING, GrowthStage.ADULT}),
        ConflictTrigger("灵根异常", "灵根异常", 0.15, ["婴儿-灵根", "婴儿-启蒙"], {GrowthStage.INFANT}),
    ]

# 主题配置
THEME_CONFIGS = {
    ThemeType.DAILY: {
        "nodes": _get_daily_nodes(),
        "conflicts": _get_daily_conflicts(),
        "start_nodes": {GrowthStage.INFANT: "婴儿-苏醒", GrowthStage.GROWING: "成长-上学", GrowthStage.ADULT: "成年-毕业"},
    },
    ThemeType.CULTIVATION: {
        "nodes": _get_cultivation_nodes(),
        "conflicts": _get_cultivation_conflicts(),
        "start_nodes": {GrowthStage.INFANT: "婴儿-降生", GrowthStage.GROWING: "成长-拜师", GrowthStage.ADULT: "成年-筑基"},
    },
}

# 其他主题使用日常配置作为默认
for theme in [ThemeType.FANTASY, ThemeType.APOCALYPSE, ThemeType.SCIFI, ThemeType.HORROR, ThemeType.MYTHOLOGY, ThemeType.CUSTOM]:
    THEME_CONFIGS[theme] = THEME_CONFIGS[ThemeType.DAILY]


class PlotNodeManager:
    """剧情节点管理器 - 多主题适配"""
    
    def __init__(self, theme: ThemeType = ThemeType.DAILY):
        self._theme = theme
        self._nodes: Dict[str, PlotNode] = {}
        self._conflicts: List[ConflictTrigger] = []
        self._current_node: Optional[str] = None
        self._node_history: List[str] = []
        self._max_paragraphs = 8
        self._paragraph_count = 0
        self._current_stage: GrowthStage = GrowthStage.INFANT
        self._current_chapter: int = 1
        self._chapter_name: str = "序章"
        self._start_nodes = {}
        self._load_theme_config(theme)
    
    def _load_theme_config(self, theme: ThemeType):
        """加载主题配置"""
        config = THEME_CONFIGS.get(theme, THEME_CONFIGS[ThemeType.DAILY])
        self._nodes.clear()
        self._conflicts.clear()
        self._nodes.update(config["nodes"])
        self._nodes["阶段过渡"] = PlotNode("阶段过渡", "阶段过渡", ["新情绪", "新动作"], ["剧情结尾"], False, {GrowthStage.INFANT, GrowthStage.GROWING, GrowthStage.ADULT})
        self._nodes["剧情结尾"] = PlotNode("剧情结尾", "剧情结尾", ["新对话"], [], True, {GrowthStage.INFANT, GrowthStage.GROWING, GrowthStage.ADULT})
        self._conflicts.extend(config["conflicts"])
        self._start_nodes = config["start_nodes"]
        self._theme = theme
    
    def set_theme(self, theme: ThemeType):
        """设置主题"""
        self._load_theme_config(theme)
        self._current_node = None
        self._node_history = []
        self._paragraph_count = 0
    
    def get_theme(self) -> ThemeType:
        return self._theme
    
    def set_growth_stage(self, stage: GrowthStage):
        self._current_stage = stage
        stage_names = {GrowthStage.INFANT: "婴儿期", GrowthStage.GROWING: "成长期", GrowthStage.ADULT: "成年期"}
        self._chapter_name = stage_names.get(stage, "序章")
    
    def get_current_stage(self) -> GrowthStage:
        return self._current_stage
    
    def get_chapter_info(self) -> tuple:
        return (self._current_chapter, self._chapter_name)
    
    def start_new_plot(self, start_node: str = None) -> PlotNode:
        if start_node is None:
            start_node = self._start_nodes.get(self._current_stage, "婴儿-苏醒")
        self._current_node = start_node
        self._node_history = [start_node]
        self._paragraph_count = 0
        return self._nodes.get(start_node)
    
    def get_current_node(self) -> Optional[PlotNode]:
        if not self._current_node:
            return None
        return self._nodes.get(self._current_node)
    
    def advance_to_next_node(self) -> Optional[PlotNode]:
        current = self.get_current_node()
        if not current or current.is_ending:
            return None
        if not current.next_nodes:
            self._current_node = "剧情结尾"
            self._node_history.append("剧情结尾")
            return self._nodes.get("剧情结尾")
        valid_next_nodes = []
        for node_name in current.next_nodes:
            node = self._nodes.get(node_name)
            if node and self._current_stage in node.applicable_stages:
                valid_next_nodes.append(node_name)
        if not valid_next_nodes:
            if "阶段过渡" in current.next_nodes:
                valid_next_nodes = ["阶段过渡"]
            elif "剧情结尾" in current.next_nodes:
                valid_next_nodes = ["剧情结尾"]
            else:
                valid_next_nodes = ["剧情结尾"]
        next_node_name = random.choice(valid_next_nodes)
        self._current_node = next_node_name
        self._node_history.append(next_node_name)
        return self._nodes.get(next_node_name)
    
    def check_should_end(self) -> bool:
        if self._paragraph_count >= self._max_paragraphs:
            return True
        current = self.get_current_node()
        if current and current.is_ending:
            return True
        return False
    
    def increment_paragraph(self):
        self._paragraph_count += 1
    
    def try_trigger_conflict(self) -> Optional[ConflictTrigger]:
        current = self.get_current_node()
        if not current:
            return None
        applicable_conflicts = [c for c in self._conflicts if current.name in c.applicable_nodes and self._current_stage in c.applicable_stages]
        if not applicable_conflicts:
            return None
        for conflict in applicable_conflicts:
            if random.random() < conflict.trigger_probability:
                return conflict
        return None
    
    def validate_content_has_progress(self, content: str, previous_content: str = "") -> bool:
        current = self.get_current_node()
        if not current:
            return True
        action_keywords = ["走", "跑", "看", "说", "想", "做", "拿", "去", "来"]
        dialogue_keywords = ["说", "问", "答", "告诉", "询问", "回应"]
        emotion_keywords = ["开心", "难过", "生气", "害怕", "期待", "满足", "失望", "沮丧"]
        has_action = any(kw in content for kw in action_keywords)
        has_dialogue = any(kw in content for kw in dialogue_keywords)
        has_emotion = any(kw in content for kw in emotion_keywords)
        return has_action or has_dialogue or has_emotion
    
    def get_node_history(self) -> List[str]:
        return self._node_history.copy()
    
    def add_custom_node(self, node_name: str, node: PlotNode):
        self._nodes[node_name] = node
    
    def add_custom_conflict(self, conflict: ConflictTrigger):
        self._conflicts.append(conflict)
    
    def list_nodes(self) -> List[str]:
        return list(self._nodes.keys())
    
    def list_nodes_for_stage(self, stage: GrowthStage) -> List[str]:
        return [name for name, node in self._nodes.items() if stage in node.applicable_stages]


_plot_node_manager_instance = None

def get_plot_node_manager() -> PlotNodeManager:
    global _plot_node_manager_instance
    if _plot_node_manager_instance is None:
        _plot_node_manager_instance = PlotNodeManager()
    return _plot_node_manager_instance
