# KIE API 直连配置与恢复

本 Skill 使用本地 Python 访问 KIE。模型固定为 GPT Image 2.5 Sunburst 图生图，分辨率固定1K；本地继续限制最多8张参考图、每张最多10MB。

## 首次配置

使用 Python 3.10+，在用户指定工作目录建立虚拟环境并安装本 Skill 的 `requirements.txt`。所有脚本使用该虚拟环境的 Python。

Key 从进程环境变量 `KIE_API_KEY` 读取，也可由用户写入 `~/.config/onion-app-image-kie/.env`，格式为 `KIE_API_KEY=实际密钥`；该文件仅存本机，建议权限0600。不要让用户在聊天、文案、清单或共享Skill包中填写真实Key。

将 `ONION_IMAGE_WORKSPACE` 设为用户指定工作目录的绝对路径，或者始终从该工作目录执行脚本。脚本和资产可以安装在其他位置。API地址默认为下列官方地址，无需另外填写。

使用 `scripts/artifact_workspace.py create --code AIMG --title "业务主题" --business-line app --project-root <工作目录>` 创建任务。这里的 `AIMG` 是保留的 APP 图片产物代码。脚本返回任务版本目录；配置卡的 `--output-dir` 使用其中的 `02_过程`，候选路径使用 `03_候选`。新任务版本用 `new-version --task-root <任务根目录>` 创建。

## 官方接口

- 生图：`POST https://api.kie.ai/api/v1/jobs/createTask`；`model=gpt-image-2-5-sunburst-image-to-image`，`input.resolution=1K`，`input.background=opaque`，参考图URL放在 `input.input_urls`。至少需要一张参考图；单图和首张使用原版Logo/IP/字体/UI等资产，同套分支只传首张PNG。首张缺少素材时补充本轮原版资产，不切换文生图或其他型号。
- 查询：`GET https://api.kie.ai/api/v1/jobs/recordInfo?taskId=...`。
- 参考图上传：`POST https://kieai.redpandaai.co/api/file-base64-upload`。
- 三者使用 `Authorization: Bearer <KIE_API_KEY>`；下载图片不携带Key。

依据：[GPT Image 2.5参数](https://kie.ai/gpt-image-2-5)、[Sunburst图生图接口](https://docs.kie.ai/43286923e0)、[上传接口](https://docs.kie.ai/file-upload-api/upload-file-base-64)，核对日期2026-10-19。上传链接是短时运行缓存，不属于正式交付。

## 1K费用与比例

按用户提供的账号区域报价截图估算3积分/张；此数值只用于预算展示，不是传给KIE的计费参数。KIE公开页面的通用1K价格与截图不同，实际扣费以账号区域报价和任务回执为准。本地请求锁定型号及1K，不会自动改用2K/4K；本次迁移没有发起付费生图或验证真实扣费。

供应商当前支持的固定比例见 `scripts/kie_model.py`。显式使用比例而非 `auto`；其中27:16、16:27、9:8、8:9仅在1K可用。原版位的 `render_width/render_height/render_size` 是旧规则中的构图参考，不再代表供应商实际输出像素。新任务按所选版位的 `target_width/target_height` 计算比例；API只传 `aspect_ratio` 和1K档位。

预计常规裁切达到6%（含6%）时先按[白底蓝框适配](blue-frame-adaptation.md)生成布局参考，走框内广告、框外纯白、OpenCV去框后拉伸的分支；小于6%的常规处理。蓝框仍是`input_urls`中的普通参考，不是API硬蒙版。下载后使用实际框线坐标，原图保留，处理后的候选由用户查看再采纳；1K交付大尺寸可能需要放大，保持1K不自动升档。详细清单见[比例适配报告](model-size-compatibility.md)。

切换型号或分辨率会改变任务指纹；已有旧模型任务的输出路径保持原状，新型号任务使用新版本，避免重复提交或覆盖旧结果。

## 执行

双/三图按[prompt-rules.md的同套生成规则](prompt-rules.md#同套双图三图生成)执行。所有分支先做依赖/路径/文案校验，首张落盘后再验证其真实PNG与回执，不能用伪造文件通过预检。

先执行 `scripts/validate_task.py <任务合同.json>`，再执行：

```text
python scripts/direct_batch.py --manifest <image-render-manifest.json> --config <image-config-result.json> --validate-only
```

检查预计候选图片数、正常预算和含超时重开的预算上限并取得当前任务授权后，以相同参数将 `--validate-only` 替换为 `--approved-in-current-task`。超过12张时，用户明确确认具体数量后额外传 `--approved-count <数量>`，候选上限20。重开属于同一逻辑图片的额外付费尝试，计入预算上限，不混作新的文案或套组。授权覆盖当前批次参考图上传、候选生成及已确认策略内的有限重开，不由历史JSON继承。

### 并发与4分钟等待策略

新配置保存`execution_policy={"concurrency":3,"generation_timeout_seconds":240,"max_timeout_restarts":1}`。不同套首张、独立单图可并发；同套首张成功落盘且回执哈希一致后，图2/3可并发，二者都只引用本套图1。并发用独立子进程隔离stdout、任务状态与输出锁；引用上传按内容哈希共享缓存。`--concurrency`可覆盖并发数，范围1–12；上传、下载时间另计。

240秒从本次任务提交时间计算，恢复时使用原提交时间，不重新开始4分钟。到阈值后最多用10秒查询最终状态：成功则下载；只有服务端明确仍为waiting、queuing或generating时，才允许一次重开。查询失败、状态不明、提交响应丢失、明确失败、下载中断和内容偏差都不触发新付费任务。网络中断与下载失败仍恢复原taskId。替代任务再次超时则停止，重跑相同命令也不会获得第三次提交额度。

公开的[Market任务状态文档](https://docs.kie.ai/market/common/get-task-detail)提供查询，但本次未找到可确认的生图取消接口。因此“中断”是停止本地等待，不声称已取消服务端任务。原任务可能继续完成并收费；预算按每张最多2次计，例如6张按3积分/次估算，正常18、含全部重开最多36积分，实际以账号扣费为准。成功的替代图仍进入候选，附上可能重复计费的提示；不自动丢弃内容偏差图。

每张状态保存在候选PNG相邻的`.kie-task.json`。提交前落盘submitting；一旦请求发出且没有可信taskId，按状态未知停止。重开前先原子保存restart_ready和attempt_history，保留原taskId、超时确认、未确认取消标记与已用次数；新提交结果不明时仍停止，不再次重提。成功后当前taskId与原尝试历史同时保留，结果中的previous_attempts用于审计，不能删除状态文件绕过上限。输入指纹改变仍须新任务或新版本。

历史配置缺少execution_policy时，默认并发3、等待240秒，但max_timeout_restarts=0，保留原任务恢复语义。不要给旧付费任务补写新策略来追认额外生成。独立render.py同样默认等待240秒；当前任务授权包含额外尝试时，显式加`--max-timeout-restarts 1`。

参考图按SHA-256命名，批次通过`.runtime/<任务ID>/reference-upload-cache.json`跨worker去重上传。已取得taskId的job恢复查询或下载时不重新上传；只有按已确认超时策略建立替代任务时才复用或补齐原参考上传。状态文件和临时URL缓存属于本地运行数据，不复制进Skill安装包或正式交付包。

本地独占锁阻止同一输出或同一清单同时执行；异常退出遗留锁时先确认原进程已停止，再移除精确锁目录并按原状态恢复，不能删除任务状态。

本地SHA-256用于验证保存文件的一致性，不能声称是与供应商提供的哈希对账。生成成功后仍需由用户选择，再运行原有本地交付和打包脚本。
