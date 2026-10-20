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

检查预计图片数并取得当前任务授权后，以相同参数将 `--validate-only` 替换为 `--approved-in-current-task`。超过12张时，用户明确确认具体数量后额外传 `--approved-count <数量>`，上限20。授权覆盖当前批次参考图上传和候选生成，不由历史JSON继承。

每张任务状态保存在候选PNG相邻的 `.kie-task.json`。提交前落盘 `submitting`，一旦请求发出且没有可信taskId，按状态未知停止；保留文件，不自动重提。查询超时但有taskId时，同一命令只继续查询原任务。输入指纹改变时必须使用新版本；不能删除状态文件绕过重复调用保护。明确失败也不自动建立新的付费任务。

参考图按SHA-256命名并在当前运行内去重上传。重启后未提交的job可重新上传参考图；已取得taskId的job不重新上传或创建。状态文件和上传缓存属于本地运行数据，不复制进Skill安装包。

本地独占锁阻止同一输出或同一清单同时执行；异常退出遗留锁时先确认原进程已停止，再移除精确锁目录并按原状态恢复，不能删除任务状态。

本地SHA-256用于验证保存文件的一致性，不能声称是与供应商提供的哈希对账。生成成功后仍需由用户选择，再运行原有本地交付和打包脚本。
