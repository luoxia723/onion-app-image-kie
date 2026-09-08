# KIE API 直连配置与恢复

本 Skill 使用本地 Python 访问 KIE，不需要 MCP、公司云账号或部署服务。模型和业务参数保持 GPT Image 2、2K、最多8张参考图、每张最多10MB。

## 首次配置

使用 Python 3.10+，在用户指定工作目录建立虚拟环境并安装本 Skill 的 `requirements.txt`。所有脚本使用该虚拟环境的 Python。

Key 从进程环境变量 `KIE_API_KEY` 读取，也可由用户写入 `~/.config/onion-app-image-kie/.env`，格式为 `KIE_API_KEY=实际密钥`；该文件仅存本机，建议权限0600。不要让用户在聊天、文案、清单或共享Skill包中填写真实Key。

将 `ONION_IMAGE_WORKSPACE` 设为用户指定工作目录的绝对路径，或者始终从该工作目录执行脚本。脚本和资产可以安装在其他位置。API地址默认为下列官方地址，无需另外填写。

使用 `scripts/artifact_workspace.py create --code AIMG --title "业务主题" --business-line app --project-root <工作目录>` 创建任务。这里的 `AIMG` 是保留的 APP 图片产物代码。脚本返回任务版本目录；配置卡的 `--output-dir` 使用其中的 `02_过程`，候选路径使用 `03_候选`。新任务版本用 `new-version --task-root <任务根目录>` 创建。

## 官方接口

- 生图：`POST https://api.kie.ai/api/v1/jobs/createTask`；无参考图用 `gpt-image-2-text-to-image`，有参考图用 `gpt-image-2-image-to-image`，参考图URL放在 `input.input_urls`。
- 查询：`GET https://api.kie.ai/api/v1/jobs/recordInfo?taskId=...`。
- 参考图上传：`POST https://kieai.redpandaai.co/api/file-base64-upload`。
- 三者使用 `Authorization: Bearer <KIE_API_KEY>`；下载图片不携带Key。

依据：[GPT Image 2](https://kie.ai/gpt-image-2)、[图生图接口](https://docs.kie.ai/market/gpt/gpt-image-2-image-to-image)、[上传接口](https://docs.kie.ai/file-upload-api/upload-file-base-64)，核对日期2026-09-08。上传链接是短时运行缓存，不属于正式交付。

## 执行

先执行 `scripts/validate_task.py <任务合同.json>`，再执行：

```text
python scripts/direct_batch.py --manifest <image-render-manifest.json> --config <image-config-result.json> --validate-only
```

检查预计图片数并取得当前任务授权后，以相同参数将 `--validate-only` 替换为 `--approved-in-current-task`。超过12张时，用户明确确认具体数量后额外传 `--approved-count <数量>`，上限20。授权覆盖当前批次参考图上传和候选生成，不由历史JSON继承。

每张任务状态保存在候选PNG相邻的 `.kie-task.json`。提交前落盘 `submitting`，一旦请求发出且没有可信taskId，按状态未知停止；保留文件，不自动重提。查询超时但有taskId时，同一命令只继续查询原任务。输入指纹改变时必须使用新版本；不能删除状态文件绕过重复调用保护。明确失败也不自动建立新的付费任务。

参考图按SHA-256命名并在当前运行内去重上传。重启后未提交的job可重新上传参考图；已取得taskId的job不重新上传或创建。状态文件和上传缓存属于本地运行数据，不复制进Skill安装包。

本地独占锁阻止同一输出或同一清单同时执行；异常退出遗留锁时先确认原进程已停止，再移除精确锁目录并按原状态恢复，不能删除任务状态。

本地SHA-256用于验证保存文件的一致性，不能声称是与供应商提供的哈希对账。生成成功后仍需由用户选择，再运行原有本地交付和打包脚本。
