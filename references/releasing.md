# 源码发布与干净安装

GitHub默认分支提供可直接下载的完整源码。分发范围为应用、前端、配置、注册素材、测试与文档；个人配置、任务数据和模型成品留在本机。发布不改变仓库可见性、品牌素材授权或已有模型请求。

## 检查顺序

1. 在仓库运行`python scripts/build_workbench_bundle.py --check`。它检查Git索引中的本地数据路径、实际本机Key、常见凭据格式、私钥、一次性登录链接和非空示例Key；输出只包含文件名，不打印凭据。不能将此检查视为对任意秘密的自动证明，提交前仍检查暂存文件范围。
2. 执行`python scripts/check_workbench.py --suite all`，确认当前、历史、回环HTTP传输与前端检查通过。
3. 生成源码包到仓库之外：`python scripts/build_workbench_bundle.py --output-dir <发布目录>`。从ZIP或tar.gz解压到新的中文／空格路径，不复制原项目`.env`、`.venv`和`.onion-local`。
4. 在解压目录运行`python bootstrap.py --install-only`及新环境的`python run.py --help`，证明运行只需Pillow，开发机残留OpenCV或NumPy不能掩盖缺依赖问题。
5. 使用临时状态目录、空env和独立端口启动，验证界面、内置素材、学习机离线预览、Key保存与接口脱敏。只填写明显的测试Key，不测试外部连接、不提交真实图片；结束后停止该验收服务。
6. 检查暂存差异，提交并正常推送；远程领先时先核对变更，不覆盖历史。推送后核对远端SHA，并查看该SHA对应的GitHub Actions结果。

## 默认服务与旧配置

新安装沿用内部规划地址`https://ops-ai-gateway.yc345.tv/v1`和`gpt-6.1-terra`，图片使用原KIE接口与`GPT Image 2.6 Flare`；用户通过设置页填写自己的网关Key和KIE Key。兼容规划服务需同时设置其地址与模型。已有`.env`中的显式配置继续优先，不为发布重写当前用户的Key、网关或任务。

运行依赖仅见`requirements.txt`；`requirements-dev.txt`和Node.js用于测试。`run.py`和启动器均应在仅运行依赖的环境可用。GitHub Actions覆盖Windows/macOS多个Python版本；本机验证不冒充Windows实机或外部模型可用性验证。

## 分发内容

`.gitignore`与源码打包器共同排除`.env`、私钥、虚拟环境、数据库及WAL、上传、缓存、备份、日志、压缩图包、工作区产物和Logo实验草稿。已被Git跟踪的禁用文件会使发布检查失败，应仅解除跟踪并保留本机文件。内置样图和品牌素材为注册运行资产，随源码提供，不读取用户历史生成结果作为默认素材。

源码包不依赖Git即可启动；仅再次使用源码打包器时需要Git工作区。真实付费验证产物保存在验收机器，不复制进GitHub；公开文档只保留技术结论和验证范围。

## 本次分发验收

从无Key源码包解压到中文及空格路径，启动器创建全新虚拟环境，仅安装Pillow即能运行入口与本机HTTP服务。44版位／45张输出的配置预览离线完成；只保存两项测试Key后，内部原网关、模型与KIE接口保持不变，响应不回传Key，本机env权限为0600，未提交模型请求。完整本地回归Python784项、前端231项通过。验收日志、临时env、空状态库和生成源码包保存在仓库之外，不纳入提交。
