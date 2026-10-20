# 主风格描述库 · 联网整理版

收集与核验日期：2026-10-19。当前共77条可独立选为主导的视觉描述；包含流派、媒介和工艺分支，不声称它们属于同一分类层级，也不以灯光/配色/布局组合凑风格数。

中文Prompt与IP适配要求由本项目根据来源自行总结，未复制上游正负提示词、未下载艺术作品图片。所有条目当前为text_reviewed、image_validated=false。描述已进入编排脚本，但效果仍须看真实成图。

无IP任务使用各条目的no_ip_prompt，不套用IP身份与服装约束；有IP时允许少量对应时代或画风的纹样、材质和配饰，主要识别特征仍保留。

执行数据以[风格JSON](../config/visual-directions.json)为准，[来源登记](../config/visual-style-sources.json)包含原始页面、仓库提交、许可证与采用方式。检索和使用方式见[多样化编排](visual-directions.md)。

```sh
python scripts/visual_directions.py --list-styles --query 水墨 --detail
```

## 艺术与设计流派（15条）

### 行动绘画笔势 · action-painting-gesture

整张场景以少量有方向的宽笔势和控制良好的洒点建立能量，角色、道具采用同材质的可辨具象处理；颜料动作呼应IP动作。文字区、脸部和Logo不覆盖飞溅。登记为行动绘画启发适配。

IP适配：保持所选IP的脸型、发型、体型、参考服装和关键标识；整体采用该主风格的材料与造型语言，不改变角色身份。原版Logo原样保留，标题继续服从独立字体参考。同套首张定调，后两张引用首张改变动作状态。宽笔势和洒点主要组织场景，IP面部和标识不被颜料遮挡。

来源：[MoMA — Action painting](https://www.moma.org/collection/terms/action-painting)；[github-twri-styler](https://github.com/twri/sdxl_prompt_styler)。

选择抽象表现主义中的动作笔势分支，保留具象IP，是广告适配。

### 色域绘画空间 · color-field-atmosphere

大面积缓慢渗化的色域形成安静空间，细微边缘与色层让画面有呼吸感，IP与少量任务物件清楚浮现。广告需要可读焦点，因此这是色域启发适配；不要把背景的低对比要求套用到标题。

IP适配：保持所选IP的脸型、发型、体型、参考服装和关键标识；整体采用该主风格的材料与造型语言，不改变角色身份。原版Logo原样保留，标题继续服从独立字体参考。同套首张定调，后两张引用首张改变动作状态。大色域组织环境，IP和标题仍有明确焦点；不是纯色域作品。

来源：[MoMA — Glossary of Art Terms](https://www.moma.org/momaorg/shared/flattened_pages/moma_learning/glossary/)。

### 构成主义视觉工程 · constructivist-visual-construction

以交叠几何板块、强方向线和清晰结构关系组织场景，有限色面、硬边界和工业纸板质感形成构成秩序；IP作为稳定叙事中心。没有政治符号，不用随机大字填满画面。

IP适配：保持所选IP的脸型、发型、体型、参考服装和关键标识；整体采用该主风格的材料与造型语言，不改变角色身份。原版Logo原样保留，标题继续服从独立字体参考。同套首张定调，后两张引用首张改变动作状态。避免无关政治符号，以IP和学习目标作为叙事核心。

来源：[MoMA — Constructivism](https://www.moma.org/collection/terms/constructivism)；[github-twri-styler](https://github.com/twri/sdxl_prompt_styler)。

### 立体主义平面切分 · cubist-faceted-construction

将书本、桌面和背景分解成相互穿插的几何平面，形成浅空间和多视点节奏；保留角色连续外轮廓与正常五官。此为保留具象IP的立体主义启发适配，不把脸拆成多重眼睛。

IP适配：保持所选IP的脸型、发型、体型、参考服装和关键标识；整体采用该主风格的材料与造型语言，不改变角色身份。原版Logo原样保留，标题继续服从独立字体参考。同套首张定调，后两张引用首张改变动作状态。背景与道具可分面，脸部不做多视点解剖或增加眼睛。

来源：[Met — Cubism](https://www.metmuseum.org/essays/cubism)；[github-twri-styler](https://github.com/twri/sdxl_prompt_styler)。

### 风格派矩形秩序 · de-stijl-rectilinear

直角线与长方色面构成有节奏的视觉平衡，颜色数量克制，画面以平面关系取代写实深景；在几何环境中保留清楚具象IP。登记为风格派启发的商业适配。

IP适配：保持所选IP的脸型、发型、体型、参考服装和关键标识；整体采用该主风格的材料与造型语言，不改变角色身份。原版Logo原样保留，标题继续服从独立字体参考。同套首张定调，后两张引用首张改变动作状态。矩形秩序用于环境，具象角色作为商业适配例外保留。

来源：[MoMA — Glossary of Art Terms](https://www.moma.org/momaorg/shared/flattened_pages/moma_learning/glossary/)；[github-mk-styles](https://github.com/K3nt3L/MK-Styles)。

### 表现主义笔触 · expressionist-painting

笔触有力，场景轮廓略带张力，背景色彩对比强调从困惑到主动的情绪变化；角色姿态具有明确动势。保留IP比例和五官，避免畸变、恐惧表情或压迫阴影。

IP适配：保持所选IP的脸型、发型、体型、参考服装和关键标识；整体采用该主风格的材料与造型语言，不改变角色身份。原版Logo原样保留，标题继续服从独立字体参考。同套首张定调，后两张引用首张改变动作状态。张力来自笔触和姿态，不通过脸型或体型畸变实现。

来源：[MoMA — Glossary of Art Terms](https://www.moma.org/momaorg/shared/flattened_pages/moma_learning/glossary/)；[github-twri-styler](https://github.com/twri/sdxl_prompt_styler)。

### 野兽派色面 · fauvist-color-planes

用果断笔触和高饱和色面塑造环境，明暗由冷暖色对比形成，空间压缩而富表现力；IP保持原本肤色与服装识别色，非自然色主要落在背景、道具和光影。

IP适配：保持所选IP的脸型、发型、体型、参考服装和关键标识；整体采用该主风格的材料与造型语言，不改变角色身份。原版Logo原样保留，标题继续服从独立字体参考。同套首张定调，后两张引用首张改变动作状态。原肤色和服装识别色保持，非自然强色主要用于背景与光影。

来源：[Met — Fauvism](https://www.metmuseum.org/essays/fauvism)。

### 未来主义动态 · futurist-motion-painting

连续斜向线、重复轮廓和流动几何面表现学习动作的速度，人物与道具共享一个清楚的运动方向；中心轮廓稳定，避免复制角色手脚。借动态画法，不带入历史政治主题。

IP适配：保持所选IP的脸型、发型、体型、参考服装和关键标识；整体采用该主风格的材料与造型语言，不改变角色身份。原版Logo原样保留，标题继续服从独立字体参考。同套首张定调，后两张引用首张改变动作状态。速度由背景和道具重复线表现，不复制角色肢体。

来源：[MoMA — Futurism](https://www.moma.org/collection/terms/futurism)。

### 印象派光色 · impressionist-light-painting

断续但有方向的色笔触、明亮空气感、彩色阴影和瞬时日光贯穿人物及环境；远景边缘柔化，近景表情和任务道具保持可辨。标题与Logo使用清晰、干净的原有呈现。

IP适配：保持所选IP的脸型、发型、体型、参考服装和关键标识；整体采用该主风格的材料与造型语言，不改变角色身份。原版Logo原样保留，标题继续服从独立字体参考。同套首张定调，后两张引用首张改变动作状态。

来源：[Met — Impressionism: Art and Modernity](https://www.metmuseum.org/essays/impressionism-art-and-modernity)；[github-twri-styler](https://github.com/twri/sdxl_prompt_styler)。

### 极简几何雕塑感 · minimalist-geometric

少量简洁实体、哑光工业材质、清楚间距和大块空白组成画面；保留一个明确动作的IP和必要学习道具，阴影轻而有体积。采用极简视觉启发，避免把“少内容”冒充完整历史流派复现。

IP适配：保持所选IP的脸型、发型、体型、参考服装和关键标识；整体采用该主风格的材料与造型语言，不改变角色身份。原版Logo原样保留，标题继续服从独立字体参考。同套首张定调，后两张引用首张改变动作状态。极简背景不削去角色必要特征；声明为具象IP适配。

来源：[MoMA — Glossary of Art Terms](https://www.moma.org/momaorg/shared/flattened_pages/moma_learning/glossary/)。

### 新印象派点彩 · neo-impressionist-pointillism

选择精密点彩这一分支，以有规律的小色点形成明暗和环境，轮廓由色点密度逐渐聚合；整体明亮有秩序。IP脸部和小图标减少点的颗粒干扰，字区完全保持干净。

IP适配：保持所选IP的脸型、发型、体型、参考服装和关键标识；整体采用该主风格的材料与造型语言，不改变角色身份。原版Logo原样保留，标题继续服从独立字体参考。同套首张定调，后两张引用首张改变动作状态。

来源：[Met — Neo-Impressionism](https://www.metmuseum.org/exhibitions/listings/2001/paul-signac-circle)；[github-twri-styler](https://github.com/twri/sdxl_prompt_styler)。

### 欧普几何视错觉 · op-art-optical-geometry

规则重复线和几何网格形成轻微深度错觉，围绕学习道具构成有秩序的节奏；角色轮廓与标题区域保持稳定平整，减少高频密纹。不要让视错觉扭曲IP脸部或削弱文字辨认。

IP适配：保持所选IP的脸型、发型、体型、参考服装和关键标识；整体采用该主风格的材料与造型语言，不改变角色身份。原版Logo原样保留，标题继续服从独立字体参考。同套首张定调，后两张引用首张改变动作状态。视错觉只在环境中受控使用，不扭曲人脸或文字。

来源：[MoMA — Op art](https://www.moma.org/collection/terms/op-art)。

### 波普广告图像 · pop-graphic

粗而清楚的角色轮廓、果断平涂色块、少量规则印刷网点与日常学习物件构成轻快商业图像；整体统一而利落。网点只进插画，禁止从示例继承对话框文字或口号。

IP适配：保持所选IP的脸型、发型、体型、参考服装和关键标识；整体采用该主风格的材料与造型语言，不改变角色身份。原版Logo原样保留，标题继续服从独立字体参考。同套首张定调，后两张引用首张改变动作状态。

来源：[MoMA — What is Pop art?](https://www.moma.org/collection/terms/pop-art/consumer-goods-mass-media-and-popular-culture)；[github-twri-styler](https://github.com/twri/sdxl_prompt_styler)。

### 文艺复兴绘画 · renaissance

以稳定的人体比例和清晰的体积转折塑造角色，环境遵循有秩序的透视与前后关系；轮廓柔和而准确，颜料层细密叠加，学习道具像静物一样具备扎实结构。

IP适配：沿用原有脸型发型服装与标识，用细腻体积塑形表达原IP，不替换成其他人物，可少量加入对应时代的服装细节。

来源：[github-twri-styler](https://github.com/twri/sdxl_prompt_styler)。

### 超现实梦境 · surrealist-dream-scene

以清楚可辨的物体构造不可能但连贯的空间，例如书页形成阶梯、任务卡悬浮成路径；光影统一，现实材质与梦境尺度形成反差。角色身份保持现实连续性，避免无意义怪物和新增标语。

IP适配：保持所选IP的脸型、发型、体型、参考服装和关键标识；整体采用该主风格的材料与造型语言，不改变角色身份。原版Logo原样保留，标题继续服从独立字体参考。同套首张定调，后两张引用首张改变动作状态。超现实尺度与物件关系用于场景，角色身体结构保持连续。

来源：[Met — Surrealism](https://www.metmuseum.org/essays/surrealism)；[MoMA — Surrealism](https://www.moma.org/collection/terms/surrealism)；[github-twri-styler](https://github.com/twri/sdxl_prompt_styler)。

## 绘画与印制媒介（24条）

### 丙烯绘画 · acrylic

以不透明颜料的覆盖、干刷与清晰色块塑造人物和场景，边缘可在硬朗与松动之间变化；空间用有力的前后层次建立，表面保留局部堆色和画布上的刷痕。

IP适配：保留脸型发型原服装与标识，面部用受控笔触表达，衣褶可概括但不改服装款式。

来源：[github-milehigh-styler](https://github.com/TripleHeadedMonkey/ComfyUI_MileHighStyler)。

### 酒精墨水 · alcohol-ink

用透明墨色的流动边界、自然聚散与层层扩散形成画面语言，背景带有细腻的液体沉积感；人物和关键道具维持清楚造型，色层之间呈流动而有组织的浅层空间。

IP适配：保持脸型发型服装及标识，液体扩散作用于大色面和背景，识别区保留稳定线面。

来源：[github-mk-styles](https://github.com/K3nt3L/MK-Styles)。

### 飞尘腐蚀版画 · aquatint

以细密的腐蚀颗粒与受控线条塑造明暗，色面像由金属版上的微小纹理印出；人物和道具轮廓准确，空间通过颗粒浓淡与层次交叠展开，保留压印纸张的实体触感。

IP适配：保持脸型发型服装和标识，五官用更细致线条表达，服装标识保留清楚边界。

来源：[github-mk-styles](https://github.com/K3nt3L/MK-Styles)。

### 溴油印相 · bromoil-print

让画面呈手工刷敷油墨的摄影印相质地，人物体积完整，局部边缘有柔和的颗粒过渡；空间像经过人工选择性加深的纸上影像，表面保留墨迹轻重与纸纤维的变化。

IP适配：保留脸型发型服装和标识，用受控颗粒表现材质，面部与标识维持准确清晰。

来源：[github-mk-styles](https://github.com/K3nt3L/MK-Styles)。

### 炭笔素描 · charcoal-tonal-drawing

黑灰炭粉块面、擦拭形成的柔光和有方向的线条塑造角色与物件，纸纹可见，少量高光由留白形成。保持IP特有轮廓与关键标记；若原色是强制身份条件，该方向应降低优先级而不是擅自去色。

IP适配：保持所选IP的脸型、发型、体型、参考服装和关键标识；整体采用该主风格的材料与造型语言，不改变角色身份。原版Logo原样保留，标题继续服从独立字体参考。同套首张定调，后两张引用首张改变动作状态。炭笔主导笔触和明暗，必须保留的服装/标识原色以局部设色保留；不可用去色覆盖品牌身份约束。

来源：[MoMA — Charcoal](https://www.moma.org/collection/terms/charcoal)；[github-milehigh-styler](https://github.com/TripleHeadedMonkey/ComfyUI_MileHighStyler)。

### 彩色石版印刷 · chromolithography

以层层套印的平整色面和细密颗粒塑造人物与道具，边缘清楚又有手工印制的细微差异；空间呈传统印刷插画的层次，色层覆盖关系和纸面质地带来温润而扎实的效果。

IP适配：保留脸型发型服装及标识，套印差异只作用于辅助边缘，面部和标识避免错位。

来源：[github-mk-styles](https://github.com/K3nt3L/MK-Styles)。

### 彩色油毡版画 · color-linocut

少量套色、厚实简洁轮廓和圆润刀口贯穿角色与场景，边缘有轻微手工节奏，纸面保持干净；用大块造型表达身份，避免满屏细密刻痕。

IP适配：保持所选IP的脸型、发型、体型、参考服装和关键标识；整体采用该主风格的材料与造型语言，不改变角色身份。原版Logo原样保留，标题继续服从独立字体参考。同套首张定调，后两张引用首张改变动作状态。

来源：[V&A — What is print?](https://www.vam.ac.uk/articles/what-is-print)。

### 蓝晒 · cyanotype

用感光印相般的深色底与明亮形体建立画面，轮廓边缘保留轻微渗透，细节呈接触印制的自然层次；人物和道具以清楚的正负形关系组织，表面有感光纸的纤维与沉积感。

IP适配：保留脸型发型服装和标识，以明暗形状维持识别；需要保留的标识不被简化成空白块。必须保留的角色身份色在关键区域局部原色呈现，深蓝感光语言用于其余区域；Logo仍保持原版。

来源：[github-mk-styles](https://github.com/K3nt3L/MK-Styles)。

### 蜡画 · encaustic

以半透明蜡层覆盖、局部刮刻和温润堆叠塑造形体，人物与道具在柔和层次间清楚浮现；空间由蜡层遮叠和边缘深浅形成，表面保留凝固、擦磨与材料厚度。

IP适配：保留脸型发型服装和标识，关键轮廓清晰，蜡层不遮盖五官或服装识别图形。

来源：[github-mk-styles](https://github.com/K3nt3L/MK-Styles)。

### 铜版雕刻线描 · engraved-line-illustration

以细密而规律的排线和交叉线塑造体积，外轮廓准确，纸面浅色，物件结构具有手工图解感。保留足够疏朗空间；标题和Logo不改成雕刻排线。

IP适配：保持所选IP的脸型、发型、体型、参考服装和关键标识；整体采用该主风格的材料与造型语言，不改变角色身份。原版Logo原样保留，标题继续服从独立字体参考。同套首张定调，后两张引用首张改变动作状态。

来源：[V&A — What is print?](https://www.vam.ac.uk/articles/what-is-print)；[Getty — Hatched! Creating Form with Line](https://www.getty.edu/art/exhibitions/hatched/index.html)。

### 写意水墨 · expressive-ink

以简练毛笔线造型，墨色浓淡和干湿笔触组织体积，淡墨层次与大块留白形成空间；不依赖写实投影，纸纤维质感轻微可见。IP五官和发型轮廓清楚，不新增题字、落款或印章。

IP适配：保持所选IP的脸型、发型、体型、参考服装和关键标识；整体采用该主风格的材料与造型语言，不改变角色身份。原版Logo原样保留，标题继续服从独立字体参考。同套首张定调，后两张引用首张改变动作状态。水墨简化不得省略角色辨识线；必须保留的身份色以局部原色设色呈现。

来源：[Met — Chinese Painting](https://www.metmuseum.org/essays/chinese-painting)。

### 工细设色 · fine-line-mineral-color

细而稳定的轮廓线、层层柔和设色、克制的矿物色感与丝绢底；以精细衣褶和道具纹理形成秩序，背景层次舒展。保留IP原服装的主要识别特征，可加入少量古风纹样、配饰或材质。

IP适配：保持所选IP的脸型、发型、体型、参考服装和关键标识；整体采用该主风格的材料与造型语言，不改变角色身份。原版Logo原样保留，标题继续服从独立字体参考。同套首张定调，后两张引用首张改变动作状态。延续原服装与现代物件，不擅自改成古装人物。

来源：[Met — Chinese Painting](https://www.metmuseum.org/essays/chinese-painting)。

### 罩染油画 · glazed-oil-painting

薄层色彩反复叠加，边缘柔硬有序，暗部透亮、亮部细腻，空间由渐进色层与稳定光源塑造；角色轮廓和表情完整，避免厚涂刀痕主导。这与厚涂油画应为两个具体视觉分支。

IP适配：保持所选IP的脸型、发型、体型、参考服装和关键标识；整体采用该主风格的材料与造型语言，不改变角色身份。原版Logo原样保留，标题继续服从独立字体参考。同套首张定调，后两张引用首张改变动作状态。

来源：[Getty — Conserving Canvas: Glossary](https://www.getty.edu/publications/conserving-canvas/glossary/)。

### 丝网套色 · graphic_screenprint

有限专色、厚实平涂、清楚硬边和局部半调组织整张插画，微小套印手感保持克制；重点动作具有强辨识度。不让套色错位影响文案和Logo。

IP适配：保持所选IP的脸型、发型、体型、参考服装和关键标识；整体采用该主风格的材料与造型语言，不改变角色身份。原版Logo原样保留，标题继续服从独立字体参考。同套首张定调，后两张引用首张改变动作状态。

来源：[V&A — What is print?](https://www.vam.ac.uk/articles/what-is-print)。

### 半色调网点印刷 · halftone-print

用规律可见的网点大小与间距表达人物和物体的明暗，外轮廓采用清楚的印刷线；空间依靠稳定的透视与分区层次建立，表面呈纸张吸墨后的颗粒与色层覆盖关系。

IP适配：锁定脸型发型服装及标识，五官与标识使用细网点或实线，避免粗网点造成识别丢失。

来源：[github-mk-styles](https://github.com/K3nt3L/MK-Styles)。

### 厚涂油画 · impasto-oil-painting

宽笔与调色刀留下起伏颜料脊，实体色块建立角色与道具，光照使笔触有触觉感；局部精细描绘脸部和识别标记。主视觉必须具有颜料行为，不只是加一层画布纹理。

IP适配：保持所选IP的脸型、发型、体型、参考服装和关键标识；整体采用该主风格的材料与造型语言，不改变角色身份。原版Logo原样保留，标题继续服从独立字体参考。同套首张定调，后两张引用首张改变动作状态。厚笔触不能抹掉脸部、发型和服装识别标记。

来源：[Getty — Conserving Canvas: Glossary](https://www.getty.edu/publications/conserving-canvas/glossary/)。

### 钢笔线描 · line-art

用有轻重变化的钢笔轮廓与受控排线说明人物结构、动作和道具体积，线条之间保留充足呼吸；前后空间依靠疏密、遮挡与线重变化建立，表面呈清楚的纸上墨迹。

IP适配：保持脸型发型服装结构和标识，以精准轮廓保留识别点，不用密排线覆盖五官。

来源：[github-twri-styler](https://github.com/twri/sdxl_prompt_styler)。

### 石版画粉蜡笔感 · lithographic-crayon-illustration

颗粒蜡笔线与柔和擦染结合，色层薄而稳定，人物和学习道具具有手绘石版海报感；浅空间、明快轮廓、轻微纸面肌理。不要自动增加复古招贴标题。

IP适配：保持所选IP的脸型、发型、体型、参考服装和关键标识；整体采用该主风格的材料与造型语言，不改变角色身份。原版Logo原样保留，标题继续服从独立字体参考。同套首张定调，后两张引用首张改变动作状态。

来源：[V&A — What is print?](https://www.vam.ac.uk/articles/what-is-print)。

### 黑白木刻 · monochrome-woodcut

以深色实体和刀刻留白构成版画图像，方向性刻痕取代柔和渐变，角色动作和物件轮廓简洁有力。用于IP广告时允许服装身份色局部保留，Logo和文字不做木刻化处理。

IP适配：保持所选IP的脸型、发型、体型、参考服装和关键标识；整体采用该主风格的材料与造型语言，不改变角色身份。原版Logo原样保留，标题继续服从独立字体参考。同套首张定调，后两张引用首张改变动作状态。黑白木刻主导环境和造型；若IP身份必须保留原色，则角色局部保留原色，作为单色版画启发的商业适配；不可强制全画面去色。

来源：[V&A — What is print?](https://www.vam.ac.uk/articles/what-is-print)；[github-milehigh-styler](https://github.com/TripleHeadedMonkey/ComfyUI_MileHighStyler)。

### 油画 · oil-painting

以不透明颜料的细腻罩染与局部厚涂塑造人物和学习道具，体积转折扎实，轮廓有选择地清晰或融入环境；空间依靠层层色面和前后关系展开，表面保留画布纹理与受控笔触。

IP适配：保持脸型发型原服装和标识，用油彩塑造体积而不改变五官比例，标识边缘清楚。

来源：[github-milehigh-styler](https://github.com/TripleHeadedMonkey/ComfyUI_MileHighStyler)。

### 连续单线绘画 · one-line

以连续而有节奏的单一线迹组织人物和道具，让轮廓在转折、停顿与呼应中说明动作；空间通过线的交叠和少量平整色面交代，纸面保持轻盈，形体简洁但关系完整。

IP适配：锁定脸型发型与服装特征，连续线概括主体，标识可用独立清楚的完整图形保留。

来源：[github-mk-styles](https://github.com/K3nt3L/MK-Styles)。

### 不透明水粉 · opaque-gouache

以柔厚不透明色面覆盖底纸，哑光表面、可见刷痕和干净色块边缘形成绘本般整体；阴影用简化色块，避免透明水彩式大面积渗漏。角色和场景统一水粉画法。

IP适配：保持所选IP的脸型、发型、体型、参考服装和关键标识；整体采用该主风格的材料与造型语言，不改变角色身份。原版Logo原样保留，标题继续服从独立字体参考。同套首张定调，后两张引用首张改变动作状态。

来源：[V&A — What is watercolour?](https://www.vam.ac.uk/articles/what-is-watercolour)。

### 软粉彩 · soft-pastel

粉质颗粒、柔软叠色和局部排线共同塑造体积，光线温柔，暗部保留彩色颗粒；硬轮廓仅用于身份和动作要点，整张维持粉彩触感。不要把粉彩等同于只换成浅色调。

IP适配：保持所选IP的脸型、发型、体型、参考服装和关键标识；整体采用该主风格的材料与造型语言，不改变角色身份。原版Logo原样保留，标题继续服从独立字体参考。同套首张定调，后两张引用首张改变动作状态。

来源：[Getty — The Birth of Pastel](https://www.getty.edu/news/the-birth-of-pastel/)。

### 透明水彩 · watercolor_illustration

透明色层交叠，保留纸白高光和自然水痕；轻铅笔结构辅助轮廓，远处湿边与近处清晰边交替。IP识别特征清楚，不能把字和Logo冲淡成水迹。

IP适配：保持所选IP的脸型、发型、体型、参考服装和关键标识；整体采用该主风格的材料与造型语言，不改变角色身份。原版Logo原样保留，标题继续服从独立字体参考。同套首张定调，后两张引用首张改变动作状态。

来源：[V&A — What is watercolour?](https://www.vam.ac.uk/articles/what-is-watercolour)；[github-twri-styler](https://github.com/twri/sdxl_prompt_styler)。

## 手作与工艺表现（17条）

### 黏土手作 · craft-clay

将人物与道具表现为手工捏制的柔软实体，圆润体块之间有清楚连接，局部保留指压和工具痕；空间像真实搭建的微型场景，表面呈微哑光的材料颗粒与温和不规则边缘。

IP适配：保留脸型发型服装结构及标识，发型用成束黏土塑形，标识以完整薄片贴附。

来源：[github-twri-styler](https://github.com/twri/sdxl_prompt_styler)。

### 十字绣图像 · cross-stitch-imagery

整幅插画由可见交叉针脚在规则布底上构成，色线形成大形与柔和明暗，统一纤维触感；足够细的针格保住IP五官。只把插画绣出来，标题和原版Logo不刺绣化。

IP适配：保持所选IP的脸型、发型、体型、参考服装和关键标识；整体采用该主风格的材料与造型语言，不改变角色身份。原版Logo原样保留，标题继续服从独立字体参考。同套首张定调，后两张引用首张改变动作状态。针格须足够细，以保证IP五官与服装轮廓清楚；文字不绣化。

来源：[V&A — Embroidery styles: an illustrated guide](https://www.vam.ac.uk/articles/embroidery-styles-an-illustrated-guide)。

### 自由表面刺绣 · freestyle-surface-embroidery

顺着角色轮廓和衣褶走向铺排丝线，长短针形成明暗，物件色面有连续线材光泽，底布纹理清楚但不抢眼；线的方向和密度统一，IP身份特征准确。

IP适配：保持所选IP的脸型、发型、体型、参考服装和关键标识；整体采用该主风格的材料与造型语言，不改变角色身份。原版Logo原样保留，标题继续服从独立字体参考。同套首张定调，后两张引用首张改变动作状态。线材沿角色结构方向铺排，不使角色外貌变成无关玩偶。

来源：[V&A — Embroidery styles: an illustrated guide](https://www.vam.ac.uk/articles/embroidery-styles-an-illustrated-guide)；[github-mk-styles](https://github.com/K3nt3L/MK-Styles)。

### 实物拓印画法 · gyotaku

借鉴拓印时接触与留痕的材料逻辑，以不均匀墨迹、细纹与纸面空隙塑造物体表面；人物与学习道具仍有完整轮廓，空间简洁，整体像将实体纹理转印到吸墨纸上。

IP适配：保持脸型发型服装与标识，拓印纹理作用于表面，不加入无关鱼形或改变人物形体。

来源：[github-mk-styles](https://github.com/K3nt3L/MK-Styles)。

取鱼拓的接触印制机制作为非鱼题材的广告适配，不自动增加鱼形。

### 立体剪纸 · kirigami

以剪切后翻折竖起的纸片构建人物与学习环境，轮廓干净，转角和连接处说明纸张结构；空间像展开的立体纸模型，表面保持纸纤维与折痕，层次来自真实的切口和支撑。

IP适配：锁定脸型发型服装与标识，主体关键形状保留完整，切口不穿过五官和识别图形。

来源：[github-twri-styler](https://github.com/twri/sdxl_prompt_styler)。

### 木纹金属 · mokume-gane

以多层金属压合后呈现的流动纹理组织人物与道具表面，造型保持清楚，层纹随曲面转折；空间像经过精细制作的金属浮雕，纹理与实体结构一致，呈温润而非镜面的材料质感。

IP适配：保留脸型发型服装和标识，金属层纹避开五官与标识边界，不让纹理改变识别形状。

来源：[github-mk-styles](https://github.com/K3nt3L/MK-Styles)。

### 马赛克镶嵌 · mosaic

以大小有节奏变化的细小镶片组成完整人物与环境，镶片走向跟随形体结构，片缝清楚可见；空间通过块面明暗与前后遮挡建立，表面有陶石材料的轻微不规则与手工铺设感。

IP适配：保留脸型发型服装和标识，面部使用更细镶片，标识边界完整，避免块面分割造成变形。

来源：[github-mk-styles](https://github.com/K3nt3L/MK-Styles)。

### 折纸 · origami

让人物、书本与道具由连续折面形成，折脊、谷线和纸角共同说明体积，表面保持完整纸张的质感；空间像真实搭建的折纸场景，几何轮廓统一，细节用折线而非写实纹理表达。

IP适配：保留脸型发型服装及标识，五官使用清楚的纸面绘制细节，服装不因折纸化变成别的款式。

来源：[github-twri-styler](https://github.com/twri/sdxl_prompt_styler)。

### 纸浆塑形 · paper-mache

用纸浆堆塑的实体体块塑造人物与道具，轮廓略带手工起伏，表面可见细小纤维和覆盖痕迹；空间像布置好的手作模型，形体厚实而轻盈，层层糊制的边缘构成材料特点。

IP适配：保留脸型发型服装及标识，控制面部表面起伏，服装标识以完整清楚的表面图形呈现。

来源：[github-twri-styler](https://github.com/twri/sdxl_prompt_styler)。

### 衍纸 · paper-quilling

用卷曲、折弯与并排的纸条构成人物和场景，形体边缘可见纸条截面，内部以疏密不同的卷纸填充；空间呈可触摸的浅浮雕，纸层之间保留细小投影和手工拼装关系。

IP适配：保留脸型发型服装和标识，用较细纸条塑造五官，标识做完整清楚的纸面图形。

来源：[github-twri-styler](https://github.com/twri/sdxl_prompt_styler)。

### 剪纸拼贴 · paper_collage

用清楚的纸片剪裁边缘与重叠层次建立人物、桌面和道具，纸面颜色完整，微小投影展示厚度；细节简洁但IP脸部可辨。不拼入报纸文字、不把Logo剪碎，不贴成多个互不相关画风。

IP适配：保持所选IP的脸型、发型、体型、参考服装和关键标识；整体采用该主风格的材料与造型语言，不改变角色身份。原版Logo原样保留，标题继续服从独立字体参考。同套首张定调，后两张引用首张改变动作状态。

来源：[MoMA — Glossary of Art Terms](https://www.moma.org/momaorg/shared/flattened_pages/moma_learning/glossary/)。

### 分层纸雕 · papercut-shadow-box

以一层层切割纸片构成人物、桌面和背景，轮廓清楚，纸层厚度与间距产生自然的空间顺序；材料表面微哑，切边保持整洁，整幅像可从侧面看见层叠结构的纸雕场景。

IP适配：保持脸型发型服装和标识，人物识别区使用独立细层，标识不被纸层遮挡。

来源：[github-twri-styler](https://github.com/twri/sdxl_prompt_styler)。

### 立体浮绣 · raised-work-textile-relief

角色和学习物件以软垫浮起，边缘针脚与分层布片形成真实浅浮雕，侧向柔光显出厚度；触觉柔软、空间层次稳定。保持IP体型，不把角色改成无关布偶；Logo与字体仍按原版独立呈现。

IP适配：保持所选IP的脸型、发型、体型、参考服装和关键标识；整体采用该主风格的材料与造型语言，不改变角色身份。原版Logo原样保留，标题继续服从独立字体参考。同套首张定调，后两张引用首张改变动作状态。浮起的布料体积跟随原IP体型，不擅自改造成另一款布偶。

来源：[V&A — Embroidery styles: an illustrated guide](https://www.vam.ac.uk/articles/embroidery-styles-an-illustrated-guide)。

### 精细刻纹浅浮雕 · scrimshaw

以细密刻线和点刻在温润浅色材料上塑造人物与器物，明暗由线条疏密逐步叠加；空间像一件被精细刻绘的浅浮雕，轮廓准确，表面呈细腻磨制与手工刻痕的对照。

IP适配：保持脸型发型服装及标识，用更精细刻线表现脸部，标识仍是原有完整图形。

来源：[github-mk-styles](https://github.com/K3nt3L/MK-Styles)。

借鉴刻线视觉语言，不要求或生成真实动物骨材。

### 绞缬染织 · shibori

借助织物捆扎、折叠与染液渗透形成的边界语言表现人物和场景，图形既有规则重复也有自然扩散；空间趋于平面，表面可见布纹与染色浓淡，轮廓保留手工织染感。

IP适配：保留脸型发型服装和标识，染织纹理用于大面与背景，五官及标识区维持清楚稳定。

来源：[github-mk-styles](https://github.com/K3nt3L/MK-Styles)。

### 彩色玻璃 · stained-glass

以相互镶嵌的透光玻璃色块组织人物和环境，深色接缝明确划分形体，块面大小随结构变化；空间由色块叠合与前后轮廓建立，表面可见轻微玻璃纹理和铅条连接感。

IP适配：保留脸型发型服装与标识，面部采用较大完整玻璃块，接缝避开五官关键部位。

来源：[github-twri-styler](https://github.com/twri/sdxl_prompt_styler)。

### 珐琅 · vitreous-enamel

用清楚的金属分隔边和圆润饱满的釉面色块塑造人物与道具，体积像精工烧制的浅浮雕；空间关系简洁，表面呈玻璃质釉层的厚度与温润反射，边缘连接精确。

IP适配：保持脸型发型服装与标识，用细金属线限定识别特征，标识以完整釉面图形保留。

来源：[github-mk-styles](https://github.com/K3nt3L/MK-Styles)。

## 插画、设计与现代视觉语言（21条）

### 非洲未来主义 · afrofuturism

将雕塑式几何结构、富有节奏的纹样与未来技术形体结合，环境具有完整的结构秩序；人物与器物由饱满块面塑形，材质可见织物、陶土与金属之间的对照和连接。

IP适配：保留原IP的脸型发型服装及标识，风格可用于场景、道具、表面结构与少量配饰，不改角色身份。

来源：[github-mk-styles](https://github.com/K3nt3L/MK-Styles)。

### 装饰艺术几何 · art-deco-geometric

修长简化造型、阶梯式轮廓、秩序鲜明的几何边框与少量放射线；大色面搭配克制金属细节，浅景深空间和清爽表面形成精致感。装饰集中于场景，不改造品牌标识。

IP适配：保持所选IP的脸型、发型、体型、参考服装和关键标识；整体采用该主风格的材料与造型语言，不改变角色身份。原版Logo原样保留，标题继续服从独立字体参考。同套首张定调，后两张引用首张改变动作状态。

来源：[V&A — An introduction to Art Deco](https://www.vam.ac.uk/articles/an-introduction-to-art-deco)；[github-twri-styler](https://github.com/twri/sdxl_prompt_styler)。

### 新艺术有机曲线 · art-nouveau-organic

流动植物曲线、柔韧轮廓和扁平化色面贯穿整张场景，弧线围绕角色和学习道具形成连续节奏；不使用厚重写实阴影。装饰避开标题与IP脸部。

IP适配：保持所选IP的脸型、发型、体型、参考服装和关键标识；整体采用该主风格的材料与造型语言，不改变角色身份。原版Logo原样保留，标题继续服从独立字体参考。同套首张定调，后两张引用首张改变动作状态。

来源：[MoMA — Art Nouveau](https://www.moma.org/collection/terms/art-nouveau-new-art)；[github-twri-styler](https://github.com/twri/sdxl_prompt_styler)。

### 原子时代未来 · atompunk

以原子时代的圆润工业造型、轨道式装饰和实体仪表构建设想中的未来学习环境；人物与道具轮廓饱满，浅层空间整洁明快，表面呈搪瓷、塑料与金属的实体触感。

IP适配：锁定脸型发型及原服装标识，未来元素可用于道具、环境与少量服装细节，保留原制服的主要识别轮廓。

来源：[github-mk-styles](https://github.com/K3nt3L/MK-Styles)。

### 包豪斯功能几何 · bauhaus-functional-geometry

以圆、矩形和简化工业体块构成学习空间，角色结构简洁，色面边缘清楚，装饰减少，间距与视觉平衡明确。背景与道具使用功能化造型；标题仍沿用指定字体，不自行换成历史西文字体。

IP适配：保持所选IP的脸型、发型、体型、参考服装和关键标识；整体采用该主风格的材料与造型语言，不改变角色身份。原版Logo原样保留，标题继续服从独立字体参考。同套首张定调，后两张引用首张改变动作状态。

来源：[Met — The Bauhaus, 1919–1933](https://www.metmuseum.org/essays/the-bauhaus-1919-1933)；[github-mk-styles](https://github.com/K3nt3L/MK-Styles)。

### 漫画印刷 · comic-book

用有力度的勾线、清楚的明暗块面与局部印刷网点塑造人物和道具，动作具有连贯的叙事张力；空间透视明确，背景简化为节奏化结构，表面保留纸本漫画的印刷感。

IP适配：保持脸型发型服装和标识，以动作与表情变化叙事，不替换角色的五官比例。

来源：[github-twri-styler](https://github.com/twri/sdxl_prompt_styler)。

### 精致商业动漫 · commercial_anime

清晰线稿、利落色块与柔和体积光，人物表情明确，背景细节克制。

IP适配：保留原版角色脸型、发型、体型、服装与关键标识，允许少量对应画风或时代的纹样、材质和配饰融入，保留身份与年龄。

来源：[本项目原有风格起点](../config/visual-directions.json)。

### 赛博朋克 · cyberpunk

将模块化电子结构、透明信息面板与实体机械连接成高密度环境，人物轮廓清楚，空间有明显纵深；表面区分玻璃、聚合物与金属，技术细节形成统一的工业语言。

IP适配：锁定脸型发型服装及标识，电子化主要作用于环境和工具，不改造成机械面孔。

来源：[github-twri-styler](https://github.com/twri/sdxl_prompt_styler)。

### 平面编辑插画 · flat_editorial

以平面轮廓、概括阴影和干净色块构成画面，减少透视和材质细节，保持IP脸型、发型、体型和服装识别。

IP适配：保留原版角色脸型、发型、体型、服装与关键标识，允许少量对应画风或时代的纹样、材质和配饰融入，保留身份与年龄。

来源：[本项目原有风格起点](../config/visual-directions.json)。

### 微缩立体模型 · isometric_miniature

人物与道具采用精细微缩模型的统一实体质感，体块连接、边缘厚度和微小接缝可见；在简洁立体场景中保持完整人物识别，镜头服从本套布局，不把等距投影本身当成全部风格。

IP适配：保留原版角色脸型、发型、体型、服装与关键标识，允许少量对应画风或时代的纹样、材质和配饰融入，保留身份与年龄。

来源：[本项目原有风格起点](../config/visual-directions.json)。

### 低多边形 · low-poly

将人物、桌面与道具转化为清楚可见的多边形体块，用平整切面交代体积转折；空间像简洁搭建的立体模型，材料依靠面之间的差异表达，保持整体结构和轮廓的统一。

IP适配：锁定脸型发型服装及标识，面部切面保持适度，标识以完整表面图形附着。

来源：[github-twri-styler](https://github.com/twri/sdxl_prompt_styler)。

### 日式漫画 · manga

以流畅而精确的线稿、选择性的黑面和细致网纹组织画面，人物表情与动作清楚，环境线条有稳定透视；形体在写意与结构之间平衡，表面呈纸上墨线与网纸的统一质地。

IP适配：保留脸型发型服装和标识，沿用原有五官设计，漫画化主要表现在线稿与明暗方式。

来源：[github-twri-styler](https://github.com/twri/sdxl_prompt_styler)。

### 叙事绘本插画 · painterly_light

以凝练的手绘轮廓、柔厚的概括色块和轻微纸上笔触组织人物与场景，造型带温和体积，空间舒展而有明确叙事焦点；以清楚的表情和动作推动画面，不只增加光效。

IP适配：保留原版角色脸型、发型、体型、服装与关键标识，允许少量对应画风或时代的纹样、材质和配饰融入，保留身份与年龄。

来源：[本项目原有风格起点](../config/visual-directions.json)。

### 像素艺术 · pixel-art

以可辨识的像素网格搭建人物和场景，轮廓用阶梯式色块转折，体积以有限层次的像素簇表达；空间结构简洁一致，纹理由图案节奏形成，避免模糊的平滑涂抹。

IP适配：保留脸型发型和服装主结构，像素尺度要足以呈现关键标识，标识不以随机点代替。

来源：[github-twri-styler](https://github.com/twri/sdxl_prompt_styler)。

### 迷幻视觉 · psychedelic

用连续弯曲的轮廓、波纹形色面与层层套叠的图形构成流动视觉，人物和道具有统一的有机线势；空间通过图形穿插展开，表面带平版印刷般的均匀质地。

IP适配：保持脸型发型和服装轮廓清楚，波纹主要围绕角色展开，服装标识不变形。

来源：[github-twri-styler](https://github.com/twri/sdxl_prompt_styler)。

### 复古未来主义 · retro-futurism

用早期太空想象中的流线外壳、实体按键与圆角机器描绘学习场景，人物和道具具有清楚体积；透视空间像搭建的未来展示场，表面呈旧式工业材料的温润实体感。

IP适配：保持脸型发型服装和标识，用复古技术造型改变学习工具，原服饰保留主要配色和识别轮廓，可加入少量对应风格的细节。

来源：[github-twri-styler](https://github.com/twri/sdxl_prompt_styler)。

### 柔和3D · soft_3d

人物和场景采用统一的柔和三维体积、哑光材质与柔光，保留所选IP身份与服装，不改成另一个角色。

IP适配：保留原版角色脸型、发型、体型、服装与关键标识，允许少量对应画风或时代的纹样、材质和配饰融入，保留身份与年龄。

来源：[本项目原有风格起点](../config/visual-directions.json)。

### 蒸汽朋克 · steampunk

以可读的机械传动、管道与铆接结构构建学习器具和环境，人物和物体采用扎实的手绘体积；空间层层展开，金属、皮革和木材有清楚触感，机械细节服务场景功能。

IP适配：保留脸型发型原服装与标识，机械元素可用于道具背景，也可少量融入扣件、袖口或腰带，面部与标识保持清楚。

来源：[github-twri-styler](https://github.com/twri/sdxl_prompt_styler)。

### 浮世绘彩色木版 · ukiyo-e-color-woodblock

以清晰墨线和分层平涂色块组织角色与道具，空间偏平面，采用清楚的前后遮挡和富节奏的轮廓；轻微纸质与套印手感。只借画法，不套用名作海浪或旧式画中文字。

IP适配：保持所选IP的脸型、发型、体型、参考服装和关键标识；整体采用该主风格的材料与造型语言，不改变角色身份。原版Logo原样保留，标题继续服从独立字体参考。同套首张定调，后两张引用首张改变动作状态。使用所选IP轮廓与衣着，仅转换版画线色；不搬用名作构图。

来源：[Met — Woodblock Prints in the Ukiyo-e Style](https://www.metmuseum.org/essays/woodblock-prints-in-the-ukiyo-e-style)；[github-mk-styles](https://github.com/K3nt3L/MK-Styles)。

### 蒸汽波 · vaporwave

用早期数码界面的图形、光滑几何体与复古三维空间构成带有怀旧意味的虚拟场景；人物以清晰轮廓嵌入其中，平面符号和立体物体相互叠合，材质呈刻意的数字合成感。

IP适配：保持脸型发型服装和标识，数码处理用于场景及道具，面部不加入故障碎片。

来源：[github-twri-styler](https://github.com/twri/sdxl_prompt_styler)。

### 禅绕绘画 · zentangle

用细密、重复而有规则的手绘纹样填充清楚的形体分区，曲线与几何图案相互交织；空间由纹样密度和留白产生，整体保持钢笔绘制的精确边缘与耐心细作的纸面质感。

IP适配：保持脸型发型服装与标识，纹样用于衣物大面和背景，五官及标识区保持简明。

来源：[github-twri-styler](https://github.com/twri/sdxl_prompt_styler)。

## 来源筛选报告

- [经典艺术与博物馆来源研究](research/classic-style-sources.md)
- [GitHub开源描述库与许可证核验](research/github-style-sources.md)
- [第三方来源及许可说明](research/THIRD_PARTY_NOTICES.md)
