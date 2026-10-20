# 主风格描述库 · 联网整理版

收集与核验日期：2026-10-19。当前共77条可独立选为主导的视觉描述；包含流派、媒介和工艺分支，不声称它们属于同一分类层级，也不以灯光/配色/布局组合凑风格数。

中文Prompt与IP适配要求由本项目根据来源自行总结，未复制上游正负提示词、未下载艺术作品图片。所有条目当前为text_reviewed、image_validated=false。描述已进入编排脚本，但效果仍须看真实成图。

新任务使用各条目的visual_prompt正向画法描述，主体与画法分别管理。无IP时直接设计选定主体；有IP时在完整场景里选择少量对应时代或画风的纹样、材质和配饰，识别要求由统一角色规则维护。旧prompt、no_ip_prompt与ip_adaptation字段仅供历史任务恢复，不整段注入新Prompt。

执行数据以[风格JSON](../config/visual-directions.json)为准，[来源登记](../config/visual-style-sources.json)包含原始页面、仓库提交、许可证与采用方式。检索和使用方式见[多样化编排](visual-directions.md)。

```sh
python scripts/visual_directions.py --list-styles --query 水墨 --detail
```

## 艺术与设计流派（15条）

### 行动绘画笔势 · action-painting-gesture

有方向的宽笔势与疏密有序的洒点建立能量，主体和道具采用同材质具象处理，重点结构清楚可辨。

来源：[MoMA — Action painting](https://www.moma.org/collection/terms/action-painting)；[github-twri-styler](https://github.com/twri/sdxl_prompt_styler)。

选择抽象表现主义中的动作笔势分支，保留具象IP，是广告适配。

### 色域绘画空间 · color-field-atmosphere

缓慢渗化的大色域形成安静空间，细微边缘与色层带来呼吸感，清晰标题构成阅读焦点。

来源：[MoMA — Glossary of Art Terms](https://www.moma.org/momaorg/shared/flattened_pages/moma_learning/glossary/)。

### 构成主义视觉工程 · constructivist-visual-construction

交叠几何板块、强方向线和清晰结构关系组织场景，有限色面、硬边界与工业纸板质感形成秩序。

来源：[MoMA — Constructivism](https://www.moma.org/collection/terms/constructivism)；[github-twri-styler](https://github.com/twri/sdxl_prompt_styler)。

### 立体主义平面切分 · cubist-faceted-construction

物件与背景由穿插的几何平面构成，浅空间与多视点形成节奏，主体识别完整清楚。

来源：[Met — Cubism](https://www.metmuseum.org/essays/cubism)；[github-twri-styler](https://github.com/twri/sdxl_prompt_styler)。

### 风格派矩形秩序 · de-stijl-rectilinear

直角线与长方色面构成有节奏的视觉平衡，克制配色与平面空间形成清楚秩序。

来源：[MoMA — Glossary of Art Terms](https://www.moma.org/momaorg/shared/flattened_pages/moma_learning/glossary/)；[github-mk-styles](https://github.com/K3nt3L/MK-Styles)。

### 表现主义笔触 · expressionist-painting

有力笔触与张力轮廓组织场景，色彩对比表达由困惑到主动的情绪变化，主体姿态具有明确动势。

来源：[MoMA — Glossary of Art Terms](https://www.moma.org/momaorg/shared/flattened_pages/moma_learning/glossary/)；[github-twri-styler](https://github.com/twri/sdxl_prompt_styler)。

### 野兽派色面 · fauvist-color-planes

果断笔触和高饱和色面塑造主体与环境，冷暖色对比形成明暗，压缩空间富有表现力。

来源：[Met — Fauvism](https://www.metmuseum.org/essays/fauvism)。

### 未来主义动态 · futurist-motion-painting

连续斜线、重复轮廓与流动几何面表现动作速度，主体和道具共享清晰运动方向，中心轮廓稳定。

来源：[MoMA — Futurism](https://www.moma.org/collection/terms/futurism)。

### 印象派光色 · impressionist-light-painting

断续而有方向的色笔触、明亮空气感、彩色阴影和瞬时日光贯穿主体与环境，远景柔化，近景结构清晰。

来源：[Met — Impressionism: Art and Modernity](https://www.metmuseum.org/essays/impressionism-art-and-modernity)；[github-twri-styler](https://github.com/twri/sdxl_prompt_styler)。

### 极简几何雕塑感 · minimalist-geometric

少量简洁实体、哑光工业材质、清楚间距与大块留白组成画面，轻柔阴影呈现雕塑体积。

来源：[MoMA — Glossary of Art Terms](https://www.moma.org/momaorg/shared/flattened_pages/moma_learning/glossary/)。

### 新印象派点彩 · neo-impressionist-pointillism

规律的小色点形成明暗与环境，轮廓由色点密度逐渐聚合，整体明亮有秩序。

来源：[Met — Neo-Impressionism](https://www.metmuseum.org/exhibitions/listings/2001/paul-signac-circle)；[github-twri-styler](https://github.com/twri/sdxl_prompt_styler)。

### 欧普几何视错觉 · op-art-optical-geometry

规则重复线与几何网格形成轻微深度错觉，围绕道具组织节奏，主体与标题区域稳定平整。

来源：[MoMA — Op art](https://www.moma.org/collection/terms/op-art)。

### 波普广告图像 · pop-graphic

粗而清楚的轮廓、果断平涂色块、局部规则印刷网点与日常物件组成轻快利落的商业插画。

来源：[MoMA — What is Pop art?](https://www.moma.org/collection/terms/pop-art/consumer-goods-mass-media-and-popular-culture)；[github-twri-styler](https://github.com/twri/sdxl_prompt_styler)。

### 文艺复兴绘画 · renaissance

稳定比例和清晰体积转折塑造主体，有秩序的透视与前后关系建立空间，轮廓柔和准确，细密颜料层塑造扎实结构。

来源：[github-twri-styler](https://github.com/twri/sdxl_prompt_styler)。

### 超现实梦境 · surrealist-dream-scene

可辨物体构造连贯的幻想空间，书页阶梯或悬浮任务路径以统一光影连接，现实材质与梦境尺度形成反差。

来源：[Met — Surrealism](https://www.metmuseum.org/essays/surrealism)；[MoMA — Surrealism](https://www.moma.org/collection/terms/surrealism)；[github-twri-styler](https://github.com/twri/sdxl_prompt_styler)。

## 绘画与印制媒介（24条）

### 丙烯绘画 · acrylic

以不透明颜料的覆盖、干刷与清晰色块塑造主体和场景，边缘可在硬朗与松动之间变化，空间用有力的前后层次建立，表面保留局部堆色和画布上的刷痕。

来源：[github-milehigh-styler](https://github.com/TripleHeadedMonkey/ComfyUI_MileHighStyler)。

### 酒精墨水 · alcohol-ink

用透明墨色的流动边界、自然聚散与层层扩散形成画面语言，背景带有细腻的液体沉积感，主体和关键道具维持清楚造型，色层之间呈流动而有组织的浅层空间。

来源：[github-mk-styles](https://github.com/K3nt3L/MK-Styles)。

### 飞尘腐蚀版画 · aquatint

以细密的腐蚀颗粒与受控线条塑造明暗，色面像由金属版上的微小纹理印出，主体和道具轮廓准确，空间通过颗粒浓淡与层次交叠展开，保留压印纸张的实体触感。

来源：[github-mk-styles](https://github.com/K3nt3L/MK-Styles)。

### 溴油印相 · bromoil-print

让画面呈手工刷敷油墨的摄影印相质地，主体体积完整，局部边缘有柔和的颗粒过渡，空间像经过人工选择性加深的纸上影像，表面保留墨迹轻重与纸纤维的变化。

来源：[github-mk-styles](https://github.com/K3nt3L/MK-Styles)。

### 炭笔素描 · charcoal-tonal-drawing

黑灰炭粉块面、擦拭形成的柔光和有方向的线条塑造主体与物件，纸纹可见，少量高光由留白形成。

来源：[MoMA — Charcoal](https://www.moma.org/collection/terms/charcoal)；[github-milehigh-styler](https://github.com/TripleHeadedMonkey/ComfyUI_MileHighStyler)。

### 彩色石版印刷 · chromolithography

以层层套印的平整色面和细密颗粒塑造主体与道具，边缘清楚又有手工印制的细微差异，空间呈传统印刷插画的层次，色层覆盖关系和纸面质地带来温润而扎实的效果。

来源：[github-mk-styles](https://github.com/K3nt3L/MK-Styles)。

### 彩色油毡版画 · color-linocut

少量套色、厚实简洁轮廓和圆润刀口贯穿主体与场景，边缘呈轻微手工节奏，纸面疏朗。

来源：[V&A — What is print?](https://www.vam.ac.uk/articles/what-is-print)。

### 蓝晒 · cyanotype

用感光印相般的深色底与明亮形体建立画面，轮廓边缘保留轻微渗透，细节呈接触印制的自然层次，主体和道具以清楚的正负形关系组织，表面有感光纸的纤维与沉积感。

来源：[github-mk-styles](https://github.com/K3nt3L/MK-Styles)。

### 蜡画 · encaustic

以半透明蜡层覆盖、局部刮刻和温润堆叠塑造形体，主体与道具在柔和层次间清楚浮现，空间由蜡层遮叠和边缘深浅形成，表面保留凝固、擦磨与材料厚度。

来源：[github-mk-styles](https://github.com/K3nt3L/MK-Styles)。

### 铜版雕刻线描 · engraved-line-illustration

规律排线和交叉线塑造体积，准确轮廓与浅色纸面呈手工图解感，空间疏朗。

来源：[V&A — What is print?](https://www.vam.ac.uk/articles/what-is-print)；[Getty — Hatched! Creating Form with Line](https://www.getty.edu/art/exhibitions/hatched/index.html)。

### 写意水墨 · expressive-ink

简练毛笔线塑形，干湿笔触与浓淡墨层组织体积，大块留白和轻微纸纤维形成舒展空间。

来源：[Met — Chinese Painting](https://www.metmuseum.org/essays/chinese-painting)。

### 工细设色 · fine-line-mineral-color

细而稳定的轮廓线、层层柔和设色、克制的矿物色感与丝绢底，以精细表面纹理和道具纹理形成秩序，背景层次舒展。

来源：[Met — Chinese Painting](https://www.metmuseum.org/essays/chinese-painting)。

### 罩染油画 · glazed-oil-painting

薄层色彩反复罩染，边缘柔硬有序，暗部透亮、亮部细腻，渐进色层与稳定光源塑造空间。

来源：[Getty — Conserving Canvas: Glossary](https://www.getty.edu/publications/conserving-canvas/glossary/)。

### 丝网套色 · graphic_screenprint

有限专色、厚实平涂、清楚硬边和局部半调组织插画，克制的套印手感突出关键动作。

来源：[V&A — What is print?](https://www.vam.ac.uk/articles/what-is-print)。

### 半色调网点印刷 · halftone-print

用规律可见的网点大小与间距表达主体和物体的明暗，外轮廓采用清楚的印刷线，空间依靠稳定的透视与分区层次建立，表面呈纸张吸墨后的颗粒与色层覆盖关系。

来源：[github-mk-styles](https://github.com/K3nt3L/MK-Styles)。

### 厚涂油画 · impasto-oil-painting

宽笔与调色刀留下起伏颜料脊，实体色块建立主体与道具，光照显出笔触触觉，关键结构精细可辨。

来源：[Getty — Conserving Canvas: Glossary](https://www.getty.edu/publications/conserving-canvas/glossary/)。

### 钢笔线描 · line-art

用有轻重变化的钢笔轮廓与受控排线说明主体结构、动作和道具体积，线条之间保留充足呼吸，前后空间依靠疏密、遮挡与线重变化建立，表面呈清楚的纸上墨迹。

来源：[github-twri-styler](https://github.com/twri/sdxl_prompt_styler)。

### 石版画粉蜡笔感 · lithographic-crayon-illustration

颗粒蜡笔线与柔和擦染结合，薄而稳定的色层、明快轮廓和轻微纸面肌理形成石版插画质地。

来源：[V&A — What is print?](https://www.vam.ac.uk/articles/what-is-print)。

### 黑白木刻 · monochrome-woodcut

深色实体和刀刻留白构成图像，方向性刻痕塑造体积，动作与物件轮廓简洁有力。

来源：[V&A — What is print?](https://www.vam.ac.uk/articles/what-is-print)；[github-milehigh-styler](https://github.com/TripleHeadedMonkey/ComfyUI_MileHighStyler)。

### 油画 · oil-painting

以不透明颜料的细腻罩染与局部厚涂塑造主体和学习道具，体积转折扎实，轮廓有选择地清晰或融入环境，空间依靠层层色面和前后关系展开，表面保留画布纹理与受控笔触。

来源：[github-milehigh-styler](https://github.com/TripleHeadedMonkey/ComfyUI_MileHighStyler)。

### 连续单线绘画 · one-line

以连续而有节奏的单一线迹组织主体和道具，让轮廓在转折、停顿与呼应中说明动作，空间通过线的交叠和少量平整色面交代，纸面保持轻盈，形体简洁但关系完整。

来源：[github-mk-styles](https://github.com/K3nt3L/MK-Styles)。

### 不透明水粉 · opaque-gouache

柔厚不透明色面覆盖底纸，哑光表面、可见刷痕和干净边缘形成绘本整体，简化色块塑造阴影。

来源：[V&A — What is watercolour?](https://www.vam.ac.uk/articles/what-is-watercolour)。

### 软粉彩 · soft-pastel

粉质颗粒、柔软叠色和局部排线共同塑造体积，光线温柔，暗部保留彩色颗粒与粉彩触感。

来源：[Getty — The Birth of Pastel](https://www.getty.edu/news/the-birth-of-pastel/)。

### 透明水彩 · watercolor_illustration

透明色层交叠，纸白高光与自然水痕呼应，轻铅笔辅助结构，远处湿边与近处清晰边交替。

来源：[V&A — What is watercolour?](https://www.vam.ac.uk/articles/what-is-watercolour)；[github-twri-styler](https://github.com/twri/sdxl_prompt_styler)。

## 手作与工艺表现（17条）

### 黏土手作 · craft-clay

将主体与道具表现为手工捏制的柔软实体，圆润体块之间有清楚连接，局部保留指压和工具痕，空间像真实搭建的微型场景，表面呈微哑光的材料颗粒与温和不规则边缘。

来源：[github-twri-styler](https://github.com/twri/sdxl_prompt_styler)。

### 十字绣图像 · cross-stitch-imagery

可见交叉针脚在规则布底上构成插画，色线形成大形与柔和明暗，纤维触感统一。

来源：[V&A — Embroidery styles: an illustrated guide](https://www.vam.ac.uk/articles/embroidery-styles-an-illustrated-guide)。

### 自由表面刺绣 · freestyle-surface-embroidery

沿主体轮廓铺排丝线，长短针形成明暗，连续线材光泽与细腻底布呈现统一纤维触感。

来源：[V&A — Embroidery styles: an illustrated guide](https://www.vam.ac.uk/articles/embroidery-styles-an-illustrated-guide)；[github-mk-styles](https://github.com/K3nt3L/MK-Styles)。

### 实物拓印画法 · gyotaku

以浓淡墨迹、细纹与纸面空隙塑造物体表面，完整轮廓与吸墨纸质感呈现实体拓印效果。

来源：[github-mk-styles](https://github.com/K3nt3L/MK-Styles)。

取鱼拓的接触印制机制作为非鱼题材的广告适配，不自动增加鱼形。

### 立体剪纸 · kirigami

以剪切后翻折竖起的纸片构建主体与学习环境，轮廓干净，转角和连接处说明纸张结构，空间像展开的立体纸模型，表面保持纸纤维与折痕，层次来自真实的切口和支撑。

来源：[github-twri-styler](https://github.com/twri/sdxl_prompt_styler)。

### 木纹金属 · mokume-gane

多层金属压合形成流动层纹，层纹随曲面转折，温润表面呈精细金属浮雕质感。

来源：[github-mk-styles](https://github.com/K3nt3L/MK-Styles)。

### 马赛克镶嵌 · mosaic

以大小有节奏变化的细小镶片组成完整主体与环境，镶片走向跟随形体结构，片缝清楚可见，空间通过块面明暗与前后遮挡建立，表面有陶石材料的轻微不规则与手工铺设感。

来源：[github-mk-styles](https://github.com/K3nt3L/MK-Styles)。

### 折纸 · origami

连续折面、折脊和纸角构成主体与道具，纸纤维与几何折线形成真实搭建的折纸场景。

来源：[github-twri-styler](https://github.com/twri/sdxl_prompt_styler)。

### 纸浆塑形 · paper-mache

用纸浆堆塑的实体体块塑造主体与道具，轮廓略带手工起伏，表面可见细小纤维和覆盖痕迹，空间像布置好的手作模型，形体厚实而轻盈，层层糊制的边缘构成材料特点。

来源：[github-twri-styler](https://github.com/twri/sdxl_prompt_styler)。

### 衍纸 · paper-quilling

用卷曲、折弯与并排的纸条构成主体和场景，形体边缘可见纸条截面，内部以疏密不同的卷纸填充，空间呈可触摸的浅浮雕，纸层之间保留细小投影和手工拼装关系。

来源：[github-twri-styler](https://github.com/twri/sdxl_prompt_styler)。

### 剪纸拼贴 · paper_collage

纸片剪裁边缘与重叠层次建立主体和场景，完整纸面颜色与微小投影展示手工拼贴厚度。

来源：[MoMA — Glossary of Art Terms](https://www.moma.org/momaorg/shared/flattened_pages/moma_learning/glossary/)。

### 分层纸雕 · papercut-shadow-box

以一层层切割纸片构成主体、桌面和背景，轮廓清楚，纸层厚度与间距产生自然的空间顺序，材料表面微哑，切边保持整洁，整幅像可从侧面看见层叠结构的纸雕场景。

来源：[github-twri-styler](https://github.com/twri/sdxl_prompt_styler)。

### 立体浮绣 · raised-work-textile-relief

主体和学习物件以软垫浮起，边缘针脚与分层布片形成真实浅浮雕，侧向柔光显出厚度，触觉柔软、空间层次稳定。

来源：[V&A — Embroidery styles: an illustrated guide](https://www.vam.ac.uk/articles/embroidery-styles-an-illustrated-guide)。

### 精细刻纹浅浮雕 · scrimshaw

以细密刻线和点刻在温润浅色材料上塑造主体与器物，明暗由线条疏密逐步叠加，空间像一件被精细刻绘的浅浮雕，轮廓准确，表面呈细腻磨制与手工刻痕的对照。

来源：[github-mk-styles](https://github.com/K3nt3L/MK-Styles)。

借鉴刻线视觉语言，不要求或生成真实动物骨材。

### 绞缬染织 · shibori

借助织物捆扎、折叠与染液渗透形成的边界语言表现主体和场景，图形既有规则重复也有自然扩散，空间趋于平面，表面可见布纹与染色浓淡，轮廓保留手工织染感。

来源：[github-mk-styles](https://github.com/K3nt3L/MK-Styles)。

### 彩色玻璃 · stained-glass

以相互镶嵌的透光玻璃色块组织主体和环境，深色接缝明确划分形体，块面大小随结构变化，空间由色块叠合与前后轮廓建立，表面可见轻微玻璃纹理和铅条连接感。

来源：[github-twri-styler](https://github.com/twri/sdxl_prompt_styler)。

### 珐琅 · vitreous-enamel

用清楚的金属分隔边和圆润饱满的釉面色块塑造主体与道具，体积像精工烧制的浅浮雕，空间关系简洁，表面呈玻璃质釉层的厚度与温润反射，边缘连接精确。

来源：[github-mk-styles](https://github.com/K3nt3L/MK-Styles)。

## 插画、设计与现代视觉语言（21条）

### 非洲未来主义 · afrofuturism

将雕塑式几何结构、富有节奏的纹样与未来技术形体结合，环境具有完整的结构秩序，主体与器物由饱满块面塑形，材质可见织物、陶土与金属之间的对照和连接。

来源：[github-mk-styles](https://github.com/K3nt3L/MK-Styles)。

### 装饰艺术几何 · art-deco-geometric

修长造型、阶梯轮廓与放射线形成几何秩序，大色面搭配克制金属细节，表面精致清爽。

来源：[V&A — An introduction to Art Deco](https://www.vam.ac.uk/articles/an-introduction-to-art-deco)；[github-twri-styler](https://github.com/twri/sdxl_prompt_styler)。

### 新艺术有机曲线 · art-nouveau-organic

流动植物曲线、柔韧轮廓与扁平色面贯穿场景，弧线围绕主体和道具形成连续节奏。

来源：[MoMA — Art Nouveau](https://www.moma.org/collection/terms/art-nouveau-new-art)；[github-twri-styler](https://github.com/twri/sdxl_prompt_styler)。

### 原子时代未来 · atompunk

以原子时代的圆润工业造型、轨道式装饰和实体仪表构建设想中的未来学习环境，主体与道具轮廓饱满，浅层空间整洁明快，表面呈搪瓷、塑料与金属的实体触感。

来源：[github-mk-styles](https://github.com/K3nt3L/MK-Styles)。

### 包豪斯功能几何 · bauhaus-functional-geometry

圆、矩形与简化工业体块构成空间，清楚色面、功能化造型、克制装饰与明确间距形成视觉平衡。

来源：[Met — The Bauhaus, 1919–1933](https://www.metmuseum.org/essays/the-bauhaus-1919-1933)；[github-mk-styles](https://github.com/K3nt3L/MK-Styles)。

### 漫画印刷 · comic-book

用有力度的勾线、清楚的明暗块面与局部印刷网点塑造主体和道具，动作具有连贯的叙事张力，空间透视明确，背景简化为节奏化结构，表面保留纸本漫画的印刷感。

来源：[github-twri-styler](https://github.com/twri/sdxl_prompt_styler)。

### 精致商业动漫 · commercial_anime

清晰线稿、利落色块与柔和体积光，主体表情明确，背景细节克制。

来源：[本项目原有风格起点](../config/visual-directions.json)。

### 赛博朋克 · cyberpunk

将模块化电子结构、透明信息面板与实体机械连接成高密度环境，主体轮廓清楚，空间有明显纵深，表面区分玻璃、聚合物与金属，技术细节形成统一的工业语言。

来源：[github-twri-styler](https://github.com/twri/sdxl_prompt_styler)。

### 平面编辑插画 · flat_editorial

以平面轮廓、概括阴影和干净色块构成画面，减少透视和材质细节。

来源：[本项目原有风格起点](../config/visual-directions.json)。

### 微缩立体模型 · isometric_miniature

主体和道具呈精细微缩模型质感，体块连接、边缘厚度与细小接缝清楚可见，空间层次完整。

来源：[本项目原有风格起点](../config/visual-directions.json)。

### 低多边形 · low-poly

将主体、桌面与道具转化为清楚可见的多边形体块，用平整切面交代体积转折，空间像简洁搭建的立体模型，材料依靠面之间的差异表达，保持整体结构和轮廓的统一。

来源：[github-twri-styler](https://github.com/twri/sdxl_prompt_styler)。

### 日式漫画 · manga

以流畅而精确的线稿、选择性的黑面和细致网纹组织画面，主体表情与动作清楚，环境线条有稳定透视，形体在写意与结构之间平衡，表面呈纸上墨线与网纸的统一质地。

来源：[github-twri-styler](https://github.com/twri/sdxl_prompt_styler)。

### 叙事绘本插画 · painterly_light

凝练手绘轮廓、柔厚色块与轻微纸上笔触组织场景，温和体积与舒展空间突出明确叙事焦点。

来源：[本项目原有风格起点](../config/visual-directions.json)。

### 像素艺术 · pixel-art

清晰像素网格搭建主体与场景，阶梯式色块转折塑造轮廓，有限层次像素簇表达体积与图案节奏。

来源：[github-twri-styler](https://github.com/twri/sdxl_prompt_styler)。

### 迷幻视觉 · psychedelic

用连续弯曲的轮廓、波纹形色面与层层套叠的图形构成流动视觉，主体和道具有统一的有机线势，空间通过图形穿插展开，表面带平版印刷般的均匀质地。

来源：[github-twri-styler](https://github.com/twri/sdxl_prompt_styler)。

### 复古未来主义 · retro-futurism

用早期太空想象中的流线外壳、实体按键与圆角机器描绘学习场景，主体和道具具有清楚体积，透视空间像搭建的未来展示场，表面呈旧式工业材料的温润实体感。

来源：[github-twri-styler](https://github.com/twri/sdxl_prompt_styler)。

### 柔和3D · soft_3d

主体和场景采用统一的柔和三维体积、哑光材质与柔光。

来源：[本项目原有风格起点](../config/visual-directions.json)。

### 蒸汽朋克 · steampunk

以可读的机械传动、管道与铆接结构构建学习器具和环境，主体和物体采用扎实的手绘体积，空间层层展开，金属、皮革和木材有清楚触感，机械细节服务场景功能。

来源：[github-twri-styler](https://github.com/twri/sdxl_prompt_styler)。

### 浮世绘彩色木版 · ukiyo-e-color-woodblock

清晰墨线与分层平涂色块组织主体和道具，平面空间、前后遮挡与轮廓节奏呈现纸质和套印手感。

来源：[Met — Woodblock Prints in the Ukiyo-e Style](https://www.metmuseum.org/essays/woodblock-prints-in-the-ukiyo-e-style)；[github-mk-styles](https://github.com/K3nt3L/MK-Styles)。

### 蒸汽波 · vaporwave

用早期数码界面的图形、光滑几何体与复古三维空间构成带有怀旧意味的虚拟场景，主体以清晰轮廓嵌入其中，平面符号和立体物体相互叠合，材质呈刻意的数字合成感。

来源：[github-twri-styler](https://github.com/twri/sdxl_prompt_styler)。

### 禅绕绘画 · zentangle

用细密、重复而有规则的手绘纹样填充清楚的形体分区，曲线与几何图案相互交织，空间由纹样密度和留白产生，整体保持钢笔绘制的精确边缘与耐心细作的纸面质感。

来源：[github-twri-styler](https://github.com/twri/sdxl_prompt_styler)。

## 来源筛选报告

- [经典艺术与博物馆来源研究](research/classic-style-sources.md)
- [GitHub开源描述库与许可证核验](research/github-style-sources.md)
- [第三方来源及许可说明](research/THIRD_PARTY_NOTICES.md)
