# 本机 PNG 联合量化工具

此独立命令行程序为严格限重的 PNG 生成额外候选。工作台在 `PATH` 上找到 `onion-learning-png` 时按需执行。日常启动和普通导出仍可用原有 Python 安装。

有 Rust 1.92 或更新版本时，在仓库根目录安装。

```bash
cargo install --locked --path tools/learning-png
```

将 Cargo 的 `bin` 目录加入启动工作台的 `PATH`。工具使用本机 RGB 像素生成索引调色板。工作台恢复版位的 Logo 专用色与原 alpha，编码 PNG 后再次核验文件。

此目录中的独立工具按 [AGPL-3.0-only](COPYING) 提供，依赖 [zenquant 0.1.3](https://github.com/imazen/zenquant/tree/v0.1.3)。源码发布只包含此工具的源码，编译在用户本机完成。
