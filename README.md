# APP 图片生成 · KIE API 独立版

将已确认的 APP 图片文案，经配置卡、KIE GPT Image 2 生成、候选选择和本地规格处理，转成采纳图片。保留原有 Logo、IP、字体参考和102条版位规则，直接调用 KIE API。

## 使用

将整个仓库作为一个 Skill 文件夹安装，保留文件名 `onion-app-image-kie`。支持 Skill 的 Agent 从根目录 [SKILL.md](SKILL.md) 读取流程。直接向 Agent 提出：

> 使用 onion-app-image-kie，按我已确认的文案打开配置卡，生成 APP 图片候选，并按我的选择交付。

首次配置需要 Python 3.10+ 和 KIE API Key。在本地创建虚拟环境并安装依赖：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Windows 使用 `.venv\Scripts\python.exe`。运行脚本时使用安装了依赖的 Python。

在本机 `~/.config/onion-app-image-kie/.env` 中配置 `KIE_API_KEY`，或通过同名进程环境变量提供。不要将真实 Key 放入仓库或聊天。配置详情和任务恢复方式见 [KIE API 合同](references/provider-contract.md)。

运行工作目录由 `ONION_IMAGE_WORKSPACE` 指定，未设置时使用当前目录。图片和任务写入该目录的 `工作区/产物/`；Skill 安装位置与工作目录可以不同。产品事实由用户提供当前确认的资料；仓库携带品牌图片，不包含完整的价格、权益或渠道时效资料。

## 验证

```sh
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest tests -q
```

测试使用本地样例与模拟API，不发起真实付费生图。正式使用前仍需配置有效 Key，并确认本次参考图上传和生图数量。当前仅完成离线验证，未进行真实 KIE 端到端验收。

## 来源与维护

由 `content-automation` 中的 APP 图片 Skill 独立适配而来。本仓库维护 KIE API 变体，原 MCP 版本保持原有维护位置。

关联任务：[content-automation#119](https://github.com/luoxia723/content-automation/issues/119)。仓库包含洋葱品牌参考资产；这些品牌资产不因源码公开而获得额外使用授权。
