# 洋葱广告图工作台：开发指引

本仓库是本机广告图应用：Python HTTP 服务、SQLite/文件持久化、原生 JavaScript 前端。业务术语见 [CONTEXT.md](CONTEXT.md)；修改模块边界、状态或调用链时先读 [技术架构](references/architecture.md)。

## 工作入口

- 从仓库根目录工作，先检查 `git status --short`，保留已有未提交改动。
- 启动：`python bootstrap.py`；已有虚拟环境可用 `.venv/bin/python run.py --no-browser`。运行应用不需要 Node.js。
- 测试依赖在 `requirements-dev.txt`，前端测试使用 Node.js 内置 `node:test`，无前端构建或 npm 安装步骤。
- 手动验收使用独立临时 `--state-dir`、`--env-file` 和端口。正式实例有任务时保留运行状态；需要重载时先核对队列并保留数据库备份。
- 修改启动、默认配置或源码发布时，按[发布检查](references/releasing.md)验证无Key干净安装、仅运行依赖启动和源码凭据检查；已有本机`.env`优先于内部默认值。

## 验证

- 默认当前行为：`.venv/bin/python scripts/check_workbench.py`，包含 Python core 和前端测试。
- 完整回归：`.venv/bin/python scripts/check_workbench.py --suite all`，包含当前、历史、离线 HTTP 适配和前端。
- 定向检查：`--suite history` / `--suite transport`；加 `--collect` 查看实际范围。
- 单文件：`.venv/bin/python -m pytest -q path/to/test.py`；历史或传输测试需加相应 `-m history` / `-m transport`，也可用 `-m ''` 取消默认 core 过滤。
- 修改持久化、任务恢复、交付、共享规则或测试分组时执行完整回归；普通修复运行相关行为测试即可。测试分类、fixture 和视觉验证边界见 [测试说明](references/testing.md)。

## 关键边界

- `Engine` 组织状态、队列、交付和维护；网络规划在 `scene_planner.py`，图片适配在 `kie_client.py` / 独立 worker，前端只经本机 API 读写。
- 正式数据在 `.onion-local/`、配置的图片工作区和 `.env`。测试使用临时目录、假 Key、回环 HTTP 服务；真实规划或生图按用户明确授权的范围执行。
- 轮次、来源图片、模型、提示词和素材按版本冻结。读取旧任务时使用旧记录；当前渠道配置变更不能回写旧版本或破坏旧图包。
- 修改 API 字段时同步其前端消费者；追加字段优先，明确区分配置计划、已生成图片、用户确认和交付状态。
- 图片任务通过共享 `FairImagePool.submit_for(owner, ...)` 分发，普通任务与学习机合计上限20，按批次轮转；规划使用单并发池，本机处理共用4槽，活动学习机批次上限8，等待图片任务上限512。
- 网络、下载、图片处理和打包遵循现有锁边界；状态不明的供应商任务先恢复查询，保留幂等与请求指纹约束。
- 修改Logo、图片后处理、导出选项或版本清理时，先读[Logo独立图层](references/logo-layers.md)。新普通任务保留无Logo底图与两款冻结素材；学习机按版位固定有无。旧图只有明确的图层来源记录才可切换Logo，实际请求与旧ZIP保持可追溯。

## 前端后台

修改导航、任务/交付聚合、阶段页或图片详情时先读[后台UI合同](references/workspace-ui.md)。`workspace.js`处理导航和列表，`production.js`展示冻结制作状态；查看页签不触发模型，跨类型分页和图包预览保留来源身份。前端测试应加载正式页面模块。

## 学习机

修改普通画幅、安全区、裁切或请求恢复时，先读[无框自然画布](references/natural-canvas.md)。制作使用完整自然画布和固定窗口，已停用的旧制作协议拒绝执行；已有图片与图包保留。

修改选图适配、共用母版分组或整组重试时，先读[多尺寸共用母版](references/shared-master-canvases.md)。该入口按来源/文案/剧情/方向分组，整张自然画布生成后按固定窗口导出；创建只冻结计划，用户启动才调用模型。

修改学习机时先读 [基础配置](references/learning-machine-setup.md) 和 [提示词合同](references/learning-machine-prompts.md)。

- 唯一路径：基准图 → 用户查看确认 → 按组制作 → 精确尺寸与图层导出。制作接口已接入本地演练与显式真实模式；配置预览始终不执行模型。真实模式仅按用户明确动作调用，本机演练同时替代规划与图片服务。
- 当前规则以 `config/learning-machine-content-rules.json`、`learning-machine-master-groups.json`、Logo/遮罩模板为准。旧 `learning-machine-workflow.json` 是兼容旧轮次所需快照，不是新任务入口。
- 所有功能名关闭，精选角标和附加文案留待后续配置；正文、CTA 有无按版位固定。IP、画风、字体和参考素材每套确定一次。
- 共用基准图不代表已经确认；各图生图分支独立引用确认后的同一版本。单张重出只更新目标图片。
- 固定比例、安全区和最终宽高由代码决定；图层顺序为尺寸 → 底灰遮罩 → Logo → 圆角。模板预览、几何正确、成图视觉合格分别验证。
- 自然背景通过`learning_background.py`与正常图片队列执行；渐变色占位只供模型看构图，交付使用模型结果的精确裁切。背景请求与指南按版本冻结，恢复查询保持原指纹，具体输入输出见[模型上下文合同](references/learning-image-context.md)。

## 修改后维护文档

- 调用链或持久化边界变化：更新 `references/architecture.md`。
- 测试入口、分组或 fixture 变化：更新 `references/testing.md`。
- 用户入口或能力边界变化：更新 `README.md`、`本机工作台说明.md` 和对应行为文档。
- 新业务术语：更新 `CONTEXT.md`；它只保留术语定义，具体规则留在对应配置和合同中。

## Code Review Rules

- 标出用当前目录重建所谓历史规格、丢失冻结来源/版本/哈希的修改；优先保持旧记录和旧交付物可读。
- 标出可能重复付费提交的重试、恢复或幂等改动；已有任务号的状态不明请求走查询。
- 标出配置预览调用外部规划/图片模型、伪造基准图确认或自动扩套的修改；离线预览应可在没有 Key 时使用。
- 测试应调用真实被测逻辑，在请求、时钟、文件与 DOM 边界替身；业务预期不能只从被测结果自己推导。行为测试不以 CSS 写法或源码字符串代替可见效果验收。
