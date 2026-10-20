# 主风格描述库来源与许可说明

本项目风格JSON中的中文视觉描述、IP适配及广告约束为本项目自行总结与改写，description_origin区分original_synthesis和project_authored。没有直接导入上游完整正向模板、negative_prompt、模型权重、工作流代码或馆藏图片。

## 开源检索来源

- MK-Styles：CC0-1.0。锁定源文件与许可链接保存在config/visual-style-sources.json；优先核对其MK条目，不把聚合的所有上游内容都推定为CC0。
- twri/sdxl_prompt_styler：MIT，Copyright (c) 2023 twri。
- TripleHeadedMonkey/ComfyUI_MileHighStyler：仓库LICENSE为MIT，Copyright (c) 2023 twri；聚合来源仍按每条记录核对。
- wolfden、Styler-Pipeline、Fooocus只登记作研究参考，本轮未将其原始模板直接导入。StyleSelectorXL未找到明确LICENSE，未收编其原文。

为保留MIT来源声明，附其许可文本；这不把博物馆文章、品牌资产或其他未知上游内容重新许可为MIT。

```text
MIT License

Copyright (c) 2023 twri

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## 博物馆与设计史来源

Met、MoMA、V&A、Getty的文章和术语页只用于风格基本事实核对；没有复制段落或取用馆藏图片，也不把文章标为CC0。具象IP、现代学习场景、原版Logo及文字可读性属于本项目的广告适配推断，不冒称历史原作特征。

所有来源URL、检查日期、采用范围与描述来源见config/visual-style-sources.json。当前image_validated=false表示尚未对新库逐条做付费成图验收，不影响如实保留已有研究。
