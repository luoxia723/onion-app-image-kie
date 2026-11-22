# 限重 PNG 的色带与抖动

渐变里的宽条、色块和假轮廓属于色带。连续的颜色被映射到少数调色板颜色时，原先平滑的区域会分成几档。抖动通过分布相邻颜色减弱这些交界，也可能留下可见颗粒或重复纹理。索引 PNG 最多 256 个调色板项，每项可以关联一个透明度。无损重压只重新表达现有像素，适合让略超限的候选过线。 [W3C PNG 调色板与透明度](https://www.w3.org/TR/png-3/#11PLTE)、[ImageMagick 抖动示例](https://usage.imagemagick.org/quantize/)、[OxiPNG](https://github.com/oxipng/oxipng)

## 开源方案

| 方案 | 对当前导出的作用 |
| --- | --- |
| pngquant 可调误差扩散 | 继续使用已有候选。只在超限且渐变色带明显时，补一次低强度抖动或低速编码，从同一张全彩成图比较格式、实际字节数与细节。`--floyd` 支持 0 到 1，`--speed` 在速度与量化质量间取舍。 [pngquant 选项](https://github.com/kornelski/pngquant/blob/main/README.md#options) |
| libimagequant 区域权重 | 可为容易产生色带的渐变争取更多调色板项，同时保留文字与人物细节。`liq_image_set_importance_map` 设置逐像素权重，`liq_image_add_fixed_color` 可保留少量已知品牌颜色。区域权重影响调色板分配。输出仍需编码 PNG，并核验 Logo、文字边缘和透明度。 [libimagequant API](https://pngquant.org/lib/) |
| FFmpeg `palettegen` / `paletteuse` | 可离线比较 Sierra 2 Lite、Burkes、Atkinson 等误差扩散。`alpha_threshold` 按阈值处理透明，带半透明圆角的图需沿用原有的透明度合成和回读校验。 [FFmpeg 调色板过滤器](https://ffmpeg.org/ffmpeg-filters.html#paletteuse)、[paletteuse 实现](https://github.com/FFmpeg/FFmpeg/blob/master/libavfilter/vf_paletteuse.c) |
| FFmpeg / libplacebo 去色带 | 仅当全彩底图已经有色带时，用背景局部弱去色带做候选，文字、Logo 和主体保持原有细节。提高过滤强度会降低细节。FFmpeg 的 `gradfun` 面向播放，有损减色可能再次引入色带。 [libplacebo 去色带参数](https://github.com/haasn/libplacebo/blob/master/docs/options.md#debanding)、[FFmpeg gradfun](https://ffmpeg.org/ffmpeg-filters.html#gradfun) |
| Netflix CAMBI | 逐帧检测色带，可用于离线对照同一张图的原图和压缩结果。它面向视频，适合作为静态广告图的补充信号，同看全图、局部保真分以及原尺寸视觉结果。 [Netflix CAMBI](https://github.com/Netflix/vmaf/blob/master/resource/doc/cambi.md) |

## 读书郎 1280×348 本机实测

截图匹配到读书郎二级页样图。从同一母版、裁框及 Logo 重走实际导出路径，得到 539,689 字节的全彩基准。全彩背景过渡平滑，限重 PNG 的相同位置出现可见色带。这次只测一张不透明 PNG。所有表中压缩成品均保持 1280×348、PNG 格式及 Logo 专用调色板，严格小于 102,400 字节。

| 同一全彩基准 | 字节 | 实际色数 | SSIMULACRA2 全图 | 截图局部 |
| --- | ---: | ---: | ---: | ---: |
| 当前成品 | 101,767 | 135 | 58.37 | 63.18 |
| pngquant `speed=1`，`floyd=0.12` | 101,698 | 135 | 59.53 | 64.07 |
| FFmpeg 本轮最高分，无抖动 | 97,842 | 141 | 54.46 | 57.52 |

共比较 80 个新增候选，14 个达标。pngquant 比较两档速度、六档画面色数和五档抖动强度。FFmpeg 比较五档画面色数及关闭抖动、Sierra 2 Lite、Burkes、Atkinson 四种方式，五个达标候选均为无抖动。低强度抖动只小幅改善了当前样图，原图所示背景色带仍可见。CAMBI 全图／局部由当前成品的 0.0072／0.0224 变为最高保真方案的 0.0094／0.0437，全彩为 0，单凭此项不足以给这一类插画择优。

现阶段保留本机编码流程。对严格限重的版位，仍有明显色带时优先试画面规则相同、背景纹理更简单的合规母版，同时保持正文、Logo、人物范围、尺寸、格式、字节和透明度要求。区域权重适合在多张紧限额样图上离线验证，通过后再评估是否加入生产候选。 [现行导出规则](../export-rules.md)
