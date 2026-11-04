# 旧制作入口清理

2026-11-03。按本地内部自用范围，将制作统一到bootstrap.py/run.py及现有工作台。

已移除9个没有被本地工作台调用的旧流程脚本：interactive_server、direct_batch、batch_render、build_selection_page、prepare_accepted_deliveries、package_accepted_images、validate_task、series_chain、execution_policy；同步移除旧配置卡/选择页的两个HTML模板和专属测试。render.py保留工作台使用的HTTP、上传、查询、下载与回执函数，移除独立CLI编排。

共享规划、Logo/IP/字体、OpenCV、压缩、目录创建和历史回执读取继续保留。渠道规格测试改为直接检查当前工作台目录，避免依赖被清理的配置卡。保留实际有恢复用途的历史提示词格式测试，不再用它限制人工编辑。

Skill仍提供画面规划方法，实际操作改为当前工作台；README及相关合同文档同步更新，去掉单版位单选、固定单模型、一段式人工限制及超时自动重开的旧流程要求。测试默认检查现行代码，传输和历史格式可单独选取。

清理前的源码、测试和说明备份：.onion-local/backups/legacy-entry-cleanup-20261103.tar.gz，不包含在分享包中。任务数据库、原图、图片版本和交付包没有删除。当前主流程检查191项及前端26项通过，启动导入及运行服务健康检查通过，未调用付费生图。
