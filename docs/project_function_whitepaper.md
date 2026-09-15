---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: 62a5f052892935463ed1c42751e16e2e_f3adc7df818411f1bbe75254006c9bbf
    ReservedCode1: VVUqCHcQZk5l3Ay3me6R3oWMJQ3/uKD7NSCnCfzNTDihqQXd10QDXWHafFXz78FrlXbDwZx+nBB9qTL0Klaj6pSyGX3WnmcbF18e9eaP8MehVEvVm41N1B+oDKI3eKQViunFnr9Cv9UcqvK4UbAy07F7E8V2LRWWS7vbZ2tMhliPGR3DWNYmkXuyqG8=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: 62a5f052892935463ed1c42751e16e2e_f3adc7df818411f1bbe75254006c9bbf
    ReservedCode2: VVUqCHcQZk5l3Ay3me6R3oWMJQ3/uKD7NSCnCfzNTDihqQXd10QDXWHafFXz78FrlXbDwZx+nBB9qTL0Klaj6pSyGX3WnmcbF18e9eaP8MehVEvVm41N1B+oDKI3eKQViunFnr9Cv9UcqvK4UbAy07F7E8V2LRWWS7vbZ2tMhliPGR3DWNYmkXuyqG8=
---



# 小说世界 项目功能白皮书

> 生成日期：2026-07-17  
> 扫描范围：H:\小说\小说世界\ 全部代码、前端、文档、配置  
> 扫描引擎模块数：**98+** .py 文件，架构分层：backend (Flask Web) + novel_world/engine (完整框架)  

---

## 一、已实现功能

### 1.1 核心引擎

#### 1.1.1 角色系统（Character System）

| 功能模块 | 说明 | 来源文件 |
|----------|------|----------|
| CharType 六大角色类型 | PROTAGONIST / ANTAGONIST / HEROINE / NPC / FACTION_LEADER / CUSTOM | `novel_world/engine/core/character.py:20-26` |
| CharState 十种角色状态 | IDLE / MOVING / FIGHTING / DEAD / TRADING / TALKING / RESTING / CULTIVATING / HIDING / CUSTOM | `novel_world/engine/core/character.py:28-38` |
| 角色属性系统 | 基础属性(name/age/gender)、性格库(按6题材)、技能系统、目标系统(短期+长期)、命运弧(fate_arc) | `novel_world/engine/core/character.py:50-323` |
| 六题材预设性格库 | 日常/修仙/奇幻/末世/科幻/恐怖每个题材有独立性格池和命运弧池 | `novel_world/engine/core/character.py:103-200` |
| 关系系统 | relationships 字典，relation_type 枚举，跨角色关系查询 | `novel_world/engine/core/character.py` |
| NPC 随机生成 | generate_random_character()，按题材生成随机NPC | `novel_world/engine/core/character.py:280-323` |
| NPC 生成校验 | RuleValidator.validate_npc_generation()，检查重复/不符合规则的NPC并自动重命名 | `novel_world/engine/core/engine.py:140-150` |
| **Backend 简化版** CharacterAgent | Goal 系统(short/long/mood)、记忆系统、关系系统 | `backend/character.py:16-140` |
| **Backend 简化版** CharacterConfig | 简化 dataclass (name/age/gender/personality/background/appearance/goals/abilities/weaknesses) | `backend/config.py:12-42` |

#### 1.1.2 世界系统（World System）

| 功能模块 | 说明 | 来源文件 |
|----------|------|----------|
| 地图生成 | TileType 枚举 12 种地形（GRASS/FOREST/MOUNTAIN/WATER/DESERT/SWAMP/SNOW/CAVE/CITY/ROAD/BRIDGE/LAVA），支持 map_size 自定义 | `novel_world/engine/core/world.py:16-33` |
| 势力系统 | Faction 类（name/color/member_ids/territory），自动分配角色到势力 | `novel_world/engine/core/world.py:135-286` |
| 六题材地名池 | 每种题材独立的地名生成词库 | `novel_world/engine/core/world.py:89-133` |
| 资源系统 | 世界级资源管理 | `novel_world/engine/core/world.py` |
| 序列化/反序列化 | to_dict / from_dict 持久化 | `novel_world/engine/core/world.py:220-286` |
| 地盘更新 | _update_faction_territory() 每10 tick更新 | `novel_world/engine/core/engine.py:200` |
| **Backend 简化版** World | chapter计数/events日志/character_positions/who_is_nearby() | `backend/world.py:1-57` |
| **Backend 简化版** WorldConfig | 简化dataclass (name/genre/era/description/rules/key_locations/tone) | `backend/config.py:46-74` |

#### 1.1.3 Tick 模拟（Tick Simulation）

| 功能模块 | 说明 | 来源文件 |
|----------|------|----------|
| tick() 主循环 | 角色移动 → AI叙事 → 对话 → 状态解析 → 势力更新 → 摘要压缩 → 自动存档 | `novel_world/engine/core/engine.py:422-530` |
| 角色随机移动 | _random_move_characters() 每tick小范围位移 | `novel_world/engine/core/engine.py:430` |
| 叙事过滤规则 | 过滤元叙事/无意义输出/narrative_type分类 | `novel_world/engine/core/engine.py:460-490` |
| 状态解析 | _update_states_from_narrative() 从叙事文本提取状态变化 | `novel_world/engine/core/engine.py:500` |
| 角色入场 | EntryScene，支持4种入场动机（GOAL_DRIVEN/FATE_DRIVEN/RELATION_DRIVEN/ACCIDENT） | `novel_world/engine/collision/collision_engine.py:147-190` |
| 死亡检测 & 永久死亡 | 检测死亡状态，永久移除角色 | `novel_world/engine/core/engine.py:540-560` |
| 故事开头 AI 生成 | 模型预加载后自动生成故事开头（150-250字） | `novel_world/engine/core/engine.py:165-228` |
| 模型异步预加载 | preload_model() 不阻塞启动 | `novel_world/engine/core/ai_client.py:120-160` |
| **Backend 简化版** 章节循环 | 5步循环：天道事件 → 角色行动 → 碰撞 → 叙事 → 记忆更新 | `backend/engine.py:40-157` |

#### 1.1.4 碰撞引擎（CollisionEngine）

| 功能模块 | 说明 | 来源文件 |
|----------|------|----------|
| 三大碰撞类型 | 感知对冲（一方泄露一方感知）、目标对冲（目的地相同/相反）、能力对冲（克制点=短板） | `novel_world/engine/collision/collision_engine.py:8-16` |
| 对立关键词表 | 30+对键值（保护↔摧毁、寻找↔隐藏、进攻↔防守…）用于目标对冲检测 | `novel_world/engine/collision/collision_engine.py:23-45` |
| 感知关键词 | 13个感知类技能关键词（感知/侦查/洞察/识破/追踪/天眼…） | `novel_world/engine/collision/collision_engine.py:48-50` |
| 隐匿关键词 | 10个隐匿类技能关键词（隐匿/潜行/遁形/伪装/隐身…） | `novel_world/engine/collision/collision_engine.py:52-54` |
| 空间距离阈值 | _PROXIMITY_THRESHOLD = 3 | `novel_world/engine/collision/collision_engine.py:57` |
| CollisionEvent 数据结构 | 含id/tick/双方信息/碰撞类型/原因/技能/地点/叙事/对话/后遗症/伏笔/危机 | `novel_world/engine/collision/collision_engine.py:64-145` |
| 去重机制 | EventDeduplicator，句式模式去重 + 冲突类型字典去重 | `novel_world/engine/quality/narrative_corrector.py:80-160` |
| **Backend 简化版** 碰撞 | CollisionEngine.process_collision()，单次AI叙事输出 + 解析（_narrative/_goal_changes/_relation_changes） | `backend/collision.py:15-135` |

### 1.2 AI 能力

#### 1.2.1 AI 客户端层

| 功能模块 | 说明 | 来源文件 |
|----------|------|----------|
| AIClient 三模式 | local（本地Qwen模型）/ api（OpenAI兼容）/ none（模板降级） | `novel_world/engine/core/ai_client.py:30-80` |
| 异步预加载 | 本地模型后台加载，不阻塞启动 | `novel_world/engine/core/ai_client.py:120-160` |
| chat() 统一接口 | 统一调用方法，自动路由到对应 provider | `novel_world/engine/core/ai_client.py:170-246` |
| **Backend 简化版** AI 客户端 | init_client() / chat() / tian_dao_prompt() / character_agent_prompt()，OpenAI 兼容 | `backend/ai_client.py:1-70` |
| **Backend 简化版** AI 生成世界 | generate_world() 根据用户输入补全世界设定 | `backend/ai_client.py:100-150` |
| **Backend 简化版** AI 生成角色 | generate_characters() 根据世界设定生成角色 | `backend/ai_client.py:160-200` |
| **Backend 简化版** 灵感分析 | analyze_content() 分析用户灵感文本，提取世界+角色设定 | `backend/ai_client.py:210-244` |

#### 1.2.2 叙事引擎（NarrativeEngine）

| 功能模块 | 说明 | 来源文件 |
|----------|------|----------|
| generate_tick_narrative() | 基于世界+角色生成每tick叙事 | `novel_world/engine/core/events.py:1-2208` |
| 人生重开事件池 | life_restart_event_pool，可扩展事件库 | `novel_world/engine/core/events.py:8-12` |
| 事件触发管理器 | event_trigger_manager，条件触发事件 | `novel_world/engine/core/events.py:14-18` |
| 角色参数库 | character_params，角色维度参数化 | `novel_world/engine/core/events.py:27-29` |
| 场景参数库 | scene_params，场景维度参数化 | `novel_world/engine/core/events.py:28-29` |
| 模板降级 | _template_fallback()，AI不可用时的模板叙事 | `novel_world/engine/core/engine.py:485` |
| 叙事增强集成 | narrative_integration_fix.integrate_improved_narrative_enhancer() | `novel_world/engine/core/engine.py:117-120` |
| 输出清洗 | _clean_output() 清洗 AI 输出的 think 标签等 | `novel_world/engine/core/engine.py:478` |
| **Backend 简化版** 叙事 | NarrativeGenerator.generate_chapter() 天道综合角色→小说正文+世界事件 | `backend/narrative.py:1-93` |

### 1.3 Web 界面

#### 1.3.1 设置向导页

| 功能模块 | 说明 | 来源文件 |
|----------|------|----------|
| 灵感输入区 | 用户输入灵感觉/大纲，AI分析填充世界+角色 | `frontend/index.html:15-22`, `frontend/app.js:385-430` |
| 世界设定 Tab | 题材(6种下拉)/时代(5种)/描述/基调(5种)/世界规则/关键地点/当前局势 | `frontend/index.html:23-80` |
| 角色设定 Tab | 动态增删角色卡片(name/age/gender/personality/background/appearance/goals/abilities/weaknesses/location) | `frontend/index.html:98-107`, `frontend/app.js:50-96` |
| 确认 Tab | 世界+角色预览摘要、API Key 配置区、启动按钮 | `frontend/index.html:110-126`, `frontend/app.js:108-138` |

#### 1.3.2 游戏主界面

| 功能模块 | 说明 | 来源文件 |
|----------|------|----------|
| 三栏布局 | 左：章节列表+世界事件 / 中：正文区 / 右：角色状态 | `frontend/index.html:130-172` |
| 章节列表 | 可点击切换章节，高亮当前章节 | `frontend/app.js:297-340` |
| 世界事件面板 | 历章世界事件汇总 | `frontend/app.js:315-330` |
| 角色状态面板 | 实时展示角色位置/心情/长期目标/短期目标 | `frontend/app.js:226-245` |
| 天道推演按钮 | 生成下一章，loading动画，错误提示 | `frontend/app.js:248-275` |
| 章节标题编辑 | 可选输入本章标题 | `frontend/app.js:251` |
| 碰撞摘要展示 | 每章生成的碰撞事件摘要（角色vs角色+目标变化） | `frontend/app.js:280-295` |
| 存档/加载 | 多槽位存档，页面弹窗加载 | `frontend/app.js:347-382` |
| API Key 配置 | 保存到 .env，格式校验(sk-开头)，实时生效 | `frontend/app.js:141-165`, `app.py:162-178` |

#### 1.3.3 AI 智能填充

| 功能模块 | 说明 | 来源文件 |
|----------|------|----------|
| AI 填充世界 | 根据已填写的部分世界设定，AI补全其余字段 | `frontend/app.js:420-450` |
| AI 填充角色 | 根据世界设定AI生成角色(1-5人) | `frontend/app.js:455-490` |
| 灵感分析填充 | 输入自由文本，AI提取世界设定和角色列表 | `frontend/app.js:385-410` |

### 1.4 文件产物

| 产物 | 说明 | 来源文件 |
|------|------|----------|
| novel.txt | 完整小说纯文本导出 | `novel_world/engine/novel_output/novel_writer.py:350-400` |
| novel.epub | EPUB 电子书导出 | `novel_world/engine/novel_output/novel_writer.py:400-450` |
| novel.html | HTML 网页小说导出 | `novel_world/engine/novel_output/novel_writer.py:450-500` |
| project.json | 项目持久化文件（世界/角色/技能/碰撞全量数据） | `novel_world/engine/novel_output/novel_writer.py:200-300` |
| 碰撞日志 | collision_log 碰撞明细记录 | `novel_world/engine/novel_output/novel_writer.py:150-180` |
| 技能快照 | skill_snapshot 角色技能状态快照 | `novel_world/engine/novel_output/novel_writer.py:130-150` |
| 章节写入 | chapter_write 逐章追加到小说文件 | `novel_world/engine/novel_output/novel_writer.py:50-130` |
| 大纲追加 | outline_append 动态大纲维护 | `novel_world/engine/novel_output/novel_writer.py:80-100` |

### 1.5 运行模式

| 模式 | 说明 | 来源文件 |
|------|------|----------|
| 在线模式（Flask Web） | Flask 服务，API 驱动，前端交互式创建世界+角色+逐章生成 | `app.py`, `run_game.py`, `start.bat` |
| 离线模式（Demo） | run_demo.py，3角色(李青云/魔尊玄冥/苏晚)×3章×20tick，模板降级，NovelWriter导出 | `run_demo.py:1-627` |
| 一键启动 | start.bat 自动检测Python/.env/依赖安装/浏览器打开 | `start.bat:1-41` |
| 依赖安装 | install_deps.bat | 项目根目录 |

### 1.6 质量管控体系（Quality Layer）

这是 novel_world/engine/quality/ 下已实现的 19 个质量管理模块：

| 模块 | 行数 | 核心功能 | 来源文件 |
|------|------|----------|----------|
| HardConstraintController | 914 | 高频词替换词库、空洞句式拦截(EMPTY_PATTERNS)、空洞表述拦截词库 | `quality/hard_constraint_controller.py` |
| NarrativeCorrector | 552 | 强制修正系统：EventDeduplicator(句式+冲突类型去重)、人设防崩塌、不可击败角色保护 | `quality/narrative_corrector.py` |
| NarrativeQualityController | 491 | 5级叙事优先级(NarrativePriority)、NarrativeFragment数据结构、CharacterStateTracker | `quality/narrative_quality_controller.py` |
| NarrativeEnhancer | 272 | 集成场景变化/动作扩展/剧情分支/缓存管理四大子模块 | `quality/narrative_enhancer.py` |
| ActionExpander | 445 | 动作库管理(7种ActionType)、动态动作组合、角色差异化动作风格、动作去重轮换 | `quality/action_expander.py` |
| SceneVariator | 388 | 光线变化(8种LightCondition)、天气动态(WeatherCondition)、氛围变化(AtmosphereType)、细节物件互动 | `quality/scene_variator.py` |
| NarrativeDedup | 373 | 场景特征提取、相似度计算、去重建议 | `quality/narrative_dedup.py` |
| PlotNodes | 371 | 剧情节点管理(PlotNode/ConflictTrigger/GrowthStage/ThemeType)、6题材适配 | `quality/plot_nodes.py` |
| RuleValidator | - | NPC 生成规则校验、世界规则校验 | `quality/rule_validator.py` |
| PlotBrancher | - | 剧情分支管理(ConflictLevel/EmotionPhase/PlotBranchType) | `quality/plot_brancher.py` |
| NarrativeCache | - | 叙事缓存(ElementType)、避免重复元素 | `quality/narrative_cache.py` |
| 其他 8 个模块 | - | narrative_integration_fix, item_system 等 | `quality/` 目录 |

### 1.7 调度与时间管理（Scheduler Layer）

| 模块 | 行数 | 核心功能 | 来源文件 |
|------|------|----------|----------|
| ConsistencyChecker | 632 | 8检查维度(character_state/timeline/goal/foreshadowing/time_backflow/item/six_axis/world_rule)、3级检查(ERROR/WARNING/INFO)、增量+全量 | `scheduler/consistency_checker.py` |
| GoalScheduler | 777 | 目标生命周期(GoalStatus 5态)、3层目标体系(终极/阶段/日常)、三分支失败处理(降级/改道/放弃) | `scheduler/goal_scheduler.py` |
| SwimlaneManager | 567 | 角色泳道、5种生命周期(LifecycleStage)、行动记录(ActionRecord)、休眠/唤醒状态管理 | `scheduler/swimlane_manager.py` |
| WorldTimeline | 346 | WorldTick 时间刻、时间标记(7时段: dawn→midnight)、immutable tick锁定 | `scheduler/world_timeline.py` |
| WorldRuleGuard | - | 世界规则执行守卫 | `scheduler/world_rule_guard.py` |
| TimelineBranch | - | 时间线分支管理 | `scheduler/timeline_branch.py` |
| CausalCollisionScheduler | - | 因果碰撞调度 | `scheduler/causal_collision_scheduler.py` |

### 1.8 子系统

| 模块 | 行数 | 核心功能 | 来源文件 |
|------|------|----------|----------|
| DialogueSystem | 694 | 9种对话类型(闲聊/交易/结盟/冲突/密谈/谈判/八卦/任务/浪漫)、5种触发条件(TriggerType)、角色意愿判断、冷却时间 | `core/dialogue_system.py` |
| FateSystem | 843 | 10种奖励类型(RewardType)、多阶段任务、命运线、奖励自动发放+通知 | `core/fate_system.py` |
| InteractionSystem | 204 | 6种互动类型(交易/结盟/任务/决斗/交换情报/共享秘密)、TradeOffer/Alliance数据结构 | `core/interaction_system.py` |
| SkillRegistry | - | 技能注册表、skill_model数据结构 | `skills/skill_registry.py` |
| SixAxisGraph | - | 六轴角色关系图 | `graph/six_axis_graph.py` |
| VectorMemory | - | 向量化记忆存储 | `storage/vector_memory.py` |
| TruthLedger | - | 不可变事实账本 | `memory/truth_ledger.py` |
| TemplateParser | 359 | GameConfig → 游戏对象解析 | `core/template_parser.py` |
| StoryGenerator | - | 故事生成器 | `core/story.py` |
| 8+ 题材规则文件 | - | 各题材独立规则配置 | `utils/themes/`, `core/themes/` |

### 1.9 存档系统

| 功能 | 说明 | 来源文件 |
|------|------|----------|
| JSON 存档 | 世界配置+状态+角色+章节完整序列化 | `backend/storage.py:1-184` |
| 多槽位管理 | list_slots() / delete_slot() | `backend/storage.py:150-184` |
| 存档 API | /api/save, /api/load/<slot>, /api/saves, /api/delete_save/<slot> | `app.py:130-160` |

### 1.10 API 端点总览

模块化架构：`app.py` 启动时通过 `exec` 加载 `api/*_api.py` 注册路由，
端点来源均标注实际所在文件。章节与大纲端点的完整参数/返回值说明见
[`api_reference.md`](./api_reference.md)。

| 端点 | 方法 | 功能 | 来源 |
|------|------|------|------|
| `/api/init` | POST | 初始化游戏（世界+角色+引擎配置） | `api/chapter_api.py` |
| `/api/chapter` | POST | 生成下一章（标题可从大纲回填） | `api/chapter_api.py` |
| `/api/state` | GET | 获取当前状态 | `api/chapter_api.py` |
| `/api/chapters` | GET | 获取所有章节（空标题从大纲回填） | `api/chapter_api.py` |
| `/api/add-character` | POST | 运行时添加角色 | `api/chapter_api.py` |
| `/api/guide-plot` | POST | 逐章模式引导情节（注入事件/目标/改角色） | `api/chapter_api.py` |
| `/api/chapter/<index>` | PUT / DELETE | 编辑 / 删除指定章节 | `api/chapter_api.py` |
| `/api/chapter/<index>/history` | GET / POST | 查询 / 保存章节编辑历史 | `api/chapter_api.py` |
| `/api/chapter/<index>/rollback` | POST | 章节版本回滚 | `api/chapter_api.py` |
| `/api/outline` | GET / PUT | 获取 / 更新大纲 | `api/outline_api.py` |
| `/api/outline/generate` | POST | AI 生成大纲（超5卷自动分批） | `api/outline_api.py` |
| `/api/outline/continue` | POST | AI 续写大纲（追加卷+扩容章数+重置终局锁） | `api/outline_api.py` |
| `/api/outline/summaries/regenerate` | POST | AI 重建丢失的章节摘要 | `api/outline_api.py` |
| `/api/outline/volume` | POST | 添加卷 | `api/outline_api.py` |
| `/api/outline/volume/<vol_index>` | DELETE | 删除卷 | `api/outline_api.py` |
| `/api/outline/volume/<vol_index>/generate` | POST | AI 生成指定卷纲要 | `api/outline_api.py` |
| `/api/outline/save` | POST | 保存手动编辑的大纲 Markdown | `api/outline_api.py` |
| `/api/save` | POST | 保存游戏 | `api/save_api.py` |
| `/api/load/<slot>` | POST | 加载存档 | `api/save_api.py` |
| `/api/saves` | GET | 列出存档 | `api/save_api.py` |
| `/api/delete_save/<slot>` | DELETE | 删除存档 | `api/save_api.py` |
| `/api/save-key` | POST | 保存 API Key | `api/save_api.py` |
| `/api/generate-world` | POST | AI 生成/补全世界设定 | `api/generate_api.py` |
| `/api/generate-characters` | POST | AI 生成角色 | `api/generate_api.py` |
| `/api/analyze-content` | POST | AI 分析灵感文本 | `api/generate_api.py` |

---

## 二、设计中功能

以下功能来自 `docs/dm_mode_and_timeline_check_design_v2.md`（2346行），已形成完整设计文档但**尚未实现**。

### 2.1 时间线检查（TimelineChecker）

| 功能 | 设计要点 | 来源 |
|------|----------|------|
| FastCheck（快速检查） | 基于规则引擎的轻量检查，检测时间回溯/事件顺序/角色状态一致性 | `dm_mode_and_timeline_check_design_v2.md:120-300` |
| DeepCheck（深度检查） | 全量遍历检查，对比 TruthLedger 不可变事实 | `dm_mode_and_timeline_check_design_v2.md:300-450` |
| AIAssistedCheck（AI辅助检查） | 调用LLM理解语义层面的矛盾 | `dm_mode_and_timeline_check_design_v2.md:450-550` |
| 七维度检查体系 | 时间回溯/因果链/角色一致性/物品/关系/世界规则/伏笔 | `dm_mode_and_timeline_check_design_v2.md:100-120` |
| TimelineCheckReport | 标准化检查报告，含严重级别和修复建议 | `dm_mode_and_timeline_check_design_v2.md:550-600` |

### 2.2 实时 DM 模式（DMManager）

| 功能 | 设计要点 | 来源 |
|------|----------|------|
| 状态机 | PAUSED → WAITING_INPUT → PROCESSING → RESUMING → RUNNING | `dm_mode_and_timeline_check_design_v2.md:700-800` |
| 暂停/恢复 | 任意tick暂停叙事，注入干预后恢复 | `dm_mode_and_timeline_check_design_v2.md:800-850` |
| 五类干预 | 角色行动干预 / 世界事件注入 / 角色关系修改 / 目标重定向 / 叙事风格调整 | `dm_mode_and_timeline_check_design_v2.md:850-950` |
| DM 指令格式 | 结构化指令 JSON 格式 | `dm_mode_and_timeline_check_design_v2.md:950-1000` |

### 2.3 Prompt 管理体系（PromptRegistry）

| 功能 | 设计要点 | 来源 |
|------|----------|------|
| PromptRegistry | 集中注册所有 prompt 模板 | `dm_mode_and_timeline_check_design_v2.md:1050-1150` |
| 版本管理 | 每个 prompt 带 version 字段，支持版本对比 | `dm_mode_and_timeline_check_design_v2.md:1150-1200` |
| 热重载 | 不重启引擎即可切换 prompt 版本 | `dm_mode_and_timeline_check_design_v2.md:1200-1250` |
| 回滚 | 支持回滚到任意历史版本 | `dm_mode_and_timeline_check_design_v2.md:1250-1300` |
| 13 个硬编码 prompt 的迁移规划 | 当前 backend/ai_client.py 和 novel_world/engine 中所有 prompt 字符串需迁移到注册表 | `dm_mode_and_timeline_check_design_v2.md:1055-1060` |

### 2.4 章节数量设定（EngineConfig）

| 功能 | 设计要点 | 来源 |
|------|----------|------|
| max_chapters | EngineConfig 新增字段，指定最大章节数 | `dm_mode_and_timeline_check_design_v2.md:1350-1400` |
| 章节元数据 | 每章标题/摘要/字数统计/碰撞次数/角色参与度 | `dm_mode_and_timeline_check_design_v2.md:1400-1450` |
| 自动收尾 | 到达 max_chapters 时触发结局生成 | `dm_mode_and_timeline_check_design_v2.md:1450-1500` |

### 2.5 已有隐式检查层对齐

| 功能 | 设计要点 | 来源 |
|------|----------|------|
| 质量管控分层架构图 | 将现有 12+ quality 模块映射到设计文档的分层体系 | `dm_mode_and_timeline_check_design_v2.md:1600-1700` |
| Backend 与 NovelWorld 双轨对齐 | adapter 适配层设计，统一 Flask 简化版和完整框架的接口 | `design_vs_code_gap_analysis.md:50-100` |
| TruthLedger 对接 | 将 ConsistencyChecker 的检查结果写入 TruthLedger 不可变事实 | `dm_mode_and_timeline_check_design_v2.md:1700-1750` |

### 2.6 天意指引（Divine Guidance）

| 功能 | 设计要点 | 来源 |
|------|----------|------|
| DivineGuidanceManager | DM 扮演天道，与单个角色进行超自然对话，AI 润色后融入小说正文 | `divine_guidance_design.md:三` |
| 七种融入形式 | 梦境/顿悟/天象/偶遇/内心独白/古籍/修炼异象，DM 可选择或 AI 自动判断 | `divine_guidance_design.md:2.3` |
| 三级强度控制 | 指引(Guidance)/暗示(Hint)/模糊预感(Vague)，影响叙事的直接程度和对角色的影响 | `divine_guidance_design.md:2.4` |
| 频率限制 | 每章最多3次、每角色每章1次、不允许同一角色连续2章接收指引 | `divine_guidance_design.md:2.5` |
| DM 面板交互 | 右侧角色面板新增"天意对话"按钮，弹出模态面板进行完整交互流程 | `divine_guidance_design.md:3.4` |
| 叙事生成集成 | 天意叙事段落作为额外素材传入 NarrativeGenerator，无缝融入章节正文 | `divine_guidance_design.md:3.2` |
| REST API | `/api/divine-guidance/check\|respond\|integrate\|confirm\|history` 五端点 | `divine_guidance_design.md:3.3` |

---

## 三、待建设功能

以下为 `design_vs_code_gap_analysis.md` 识别的核心差距及新增待建项：

### 3.1 完全未实现的 v2 设计模块

| 功能 | 当前状态 | 优先级 | 说明 |
|------|----------|--------|------|
| TimelineChecker | 未实现 | 高 | 设计文档已完整，需新建 `novel_world/engine/timeline_checker/` 模块，实现 FastCheck/DeepCheck/AIAssistedCheck 三档 |
| DMManager | 未实现 | 高 | 需新建 `novel_world/engine/dm_manager/`，实现状态机 + 五类干预 + Web 端 DM 面板 |
| PromptRegistry | 未实现 | 中 | 需新建 `novel_world/engine/prompt_registry/`，迁移 13 个硬编码 prompt |
| EngineConfig 扩展 | 部分实现 | 中 | engine.py 已有 settings dict，需标准化为 EngineConfig dataclass，增加 max_chapters/收尾逻辑 |
| Adapter 适配层 | 未实现 | 中 | 需桥接 backend/ (Flask) 和 novel_world/engine/ (完整框架) 两套代码体系的接口 |

### 3.2 代码层面缺失

| 功能 | 说明 | 来源 |
|------|------|------|
| 双代码体系统一 | backend/ (Flask简化版) 和 novel_world/engine/ (完整框架) 是独立开发的两套引擎，需通过适配层统一 | `design_vs_code_gap_analysis.md:30-50` |
| NovelWorld 引擎集成到 Web | 当前 app.py 调用的是 backend/ 简化引擎，novel_world/engine/ 的完整能力（quality/scheduler/collision 等）未在 Web 端暴露 | `design_vs_code_gap_analysis.md:100-130` |

### 3.3 功能增强建议

| 功能 | 说明 |
|------|------|
| Web DM 面板 | 游戏主界面增加 DM 干预面板，支持暂停/注入事件/修改关系/重定向目标 |
| 时间线可视化 | 前端展示角色时间线泳道图 |
| 章节规划器 | 前端设置总章节数和每章主题 |
| 导出增强 | 支持 PDF 导出（当前已有 TXT/EPUB/HTML） |
| 多语言支持 | 当前仅支持中文，可扩展英文/日文叙事 |
| 测试覆盖 | 当前无明显测试代码 |

---

## 四、项目架构总览

```
H:\小说\小说世界\
├── app.py                     # Flask Web 入口（271行）
├── run_game.py                # Web 模式启动（7行）
├── run_demo.py                # 离线Demo（627行）
├── start.bat                  # 一键启动脚本
├── .env / .env.example        # OpenAI API 配置
│
├── backend/                   # Flask 简化版引擎（9个模块）
│   ├── ai_client.py           # OpenAI兼容客户端（244行）
│   ├── character.py           # CharacterAgent + Goal系统（140行）
│   ├── collision.py           # 碰撞引擎简化版（135行）
│   ├── config.py              # WorldConfig / CharacterConfig（74行）
│   ├── engine.py              # GameEngine 章节循环（157行）
│   ├── narrative.py           # NarrativeGenerator（93行）
│   ├── storage.py             # 存档系统（184行）
│   └── world.py               # World 状态管理（57行）
│
├── novel_world/engine/        # 完整框架引擎（98+模块）
│   ├── core/                  # 12个核心模块
│   │   ├── engine.py          # 推演引擎（972行）
│   │   ├── character.py       # 角色系统（323行）
│   │   ├── world.py           # 世界系统（286行）
│   │   ├── ai_client.py       # AI客户端三模式（246行）
│   │   ├── events.py          # 叙事引擎（2208行）
│   │   ├── story.py           # 故事生成器
│   │   ├── dialogue_system.py # 对话系统（694行）
│   │   ├── fate_system.py     # 命运线系统（843行）
│   │   ├── interaction_system.py # 互动系统（204行）
│   │   ├── template_parser.py # 模板解析器（359行）
│   │   ├── storage.py         # 持久化
│   │   └── themes/            # 题材规则
│   │
│   ├── collision/             # 碰撞引擎
│   │   └── collision_engine.py # 3碰撞类型+去重（1395行）
│   │
│   ├── quality/               # 质量管控（19个模块）
│   │   ├── hard_constraint_controller.py  # 硬约束（914行）
│   │   ├── narrative_corrector.py         # 强制修正（552行）
│   │   ├── narrative_quality_controller.py # 质量控制器（491行）
│   │   ├── narrative_enhancer.py          # 增强器（272行）
│   │   ├── action_expander.py             # 动作扩展（445行）
│   │   ├── scene_variator.py              # 场景变化（388行）
│   │   ├── narrative_dedup.py             # 去重（373行）
│   │   ├── plot_nodes.py                  # 剧情节点（371行）
│   │   ├── rule_validator.py              # 规则校验
│   │   ├── plot_brancher.py               # 剧情分支
│   │   ├── narrative_cache.py             # 缓存
│   │   └── ...                            # 其他8模块
│   │
│   ├── scheduler/             # 调度与时间管理（7个模块）
│   │   ├── consistency_checker.py         # 一致性检查（632行）
│   │   ├── goal_scheduler.py              # 目标调度（777行）
│   │   ├── swimlane_manager.py            # 泳道管理（567行）
│   │   ├── world_timeline.py              # 时间轴（346行）
│   │   ├── world_rule_guard.py            # 规则守卫
│   │   ├── timeline_branch.py             # 时间线分支
│   │   └── causal_collision_scheduler.py  # 因果调度
│   │
│   ├── novel_output/          # 小说输出
│   │   └── novel_writer.py    # TXT/EPUB/HTML导出（794行）
│   │
│   ├── skills/                # 技能系统
│   ├── graph/                 # 关系图
│   ├── storage/               # 向量记忆
│   ├── memory/                # 事实账本
│   └── utils/                 # 事件触发/引用 + themes
│
├── frontend/                  # Web 前端
│   ├── index.html             # 页面结构（175行）
│   └── app.js                 # 交互逻辑（713行）
│
├── docs/                      # 设计文档
│   ├── dm_mode_and_timeline_check_design_v2.md  # v2设计（2346行）
│   └── design_vs_code_gap_analysis.md           # 差距分析（303行）
│
└── saves/                     # 存档目录
```

---

*白皮书生成完毕。功能盘点基于 `H:\小说\小说世界\` 项目文件的完整静态扫描，涵盖 98+ 模块。*
*（内容由AI生成，仅供参考）*
*（内容由AI生成，仅供参考）*
