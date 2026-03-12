# Emby / TMDB 媒体库命名规范指南 v1.6

> 更新说明：v1.6 在 v1.5 基础上整合了剧集多版本、绝对集数（Absolute Order）、Extras 完整目录、蓝光原盘根目录要求、多版本数量上限、软链接/硬链接、动漫高级方案、扩展 NFO 字段、ID 格式统一建议与检查清单增强项。

---

## 一、基本原则

| 原则 | 说明 |
|------|------|
| **TMDB 优先** | 名称、年份、季集编号以 TMDB 为准，避免本地分组习惯直接套用 |
| **英文原名** | 文件夹与文件名优先使用英文原名，降低刮削歧义 |
| **年份必填** | 电影、剧集目录均建议带年份，防止同名误匹配 |
| **ID 锁定** | 易混淆条目建议附加 TMDB/IMDb ID，减少错刮 |
| **结构统一** | 同一媒体类型保持统一命名规则，不混用多种风格 |
| **编码规范** | NFO、字幕统一 UTF-8；NFO 建议 UTF-8 无 BOM |

### 1.1 ID 嵌入格式（统一建议）

推荐在本文档统一使用方括号格式：

```text
[tmdbid=155]
[imdbid=tt0468569]
```

Emby 也兼容其他常见变体（可识别但不建议混用）：

```text
{tmdb-155}
{tmdb=155}
[tmdbid-155]
```

---

## 二、电影命名

### 2.1 标准格式

```text
Movies/
└── Movie Title (Year) [tmdbid=12345]/
    └── Movie Title (Year).ext
```

### 2.2 基础示例

```text
Movies/
├── The Dark Knight (2008) [tmdbid=155]/
│   └── The Dark Knight (2008).mkv
├── Avatar (2009) [tmdbid=19995]/
│   └── Avatar (2009).mkv
└── Spider-Man- No Way Home (2021) [tmdbid=634649]/
    └── Spider-Man- No Way Home (2021).mkv
```

### 2.3 多版本电影

同一电影的多个版本放在同一目录，用版本后缀区分：

```text
The Dark Knight (2008) [tmdbid=155]/
├── The Dark Knight (2008) - 1080p Bluray.mkv
├── The Dark Knight (2008) - 4K HDR.mkv
└── The Dark Knight (2008) - Director's Cut.mkv
```

注意：Emby 对单个媒体条目的多版本识别上限为 **8 个**。超过部分不会作为“版本”被正确归并。

### 2.4 蓝光原盘 / ISO 目录结构

ISO 与 BDMV 目录均可使用；若为原盘目录，`BDMV` 必须直接位于电影根目录下：

```text
The Dark Knight (2008) [tmdbid=155]/
├── The Dark Knight (2008).iso
├── BDMV/
│   ├── index.bdmv
│   └── STREAM/
│       └── 00001.m2ts
└── CERTIFICATE/
```

错误示例：`The Dark Knight (2008)/disc1/BDMV/`（多包一层目录）可能导致 Emby 无法识别为蓝光结构。

### 2.5 电影 Extras（附加内容）目录

以下文件夹名可用于电影附加内容归类（放在电影根目录）：

| 文件夹名称 | 用途 |
|------------|------|
| `extras` | 通用花絮 |
| `specials` | 特别收录 |
| `behind the scenes` | 幕后制作 |
| `deleted scenes` | 删除片段 |
| `interviews` | 访谈 |
| `scenes` | 场景剪辑 |
| `shorts` | 短片 |
| `featurettes` | 特辑 |
| `trailers` | 预告片 |
| `other` | 其他 |

### 2.6 电影合集（Collections）

Emby 通常会依据 TMDB 的 `belongs_to_collection` 自动聚合。
如需手动控制，可在 NFO 使用 `<set>`：

```xml
<?xml version="1.0" encoding="UTF-8"?>
<movie>
  <title>The Dark Knight</title>
  <set>
    <name>The Dark Knight Collection</name>
  </set>
</movie>
```

---

## 三、剧集命名

### 3.1 标准格式

```text
TV Shows/
└── Show Name (Year) [tmdbid=12345]/
    ├── Season 01/
    │   └── Show Name (Year) - S01E01 - Episode Title.ext
    └── Season 00/
        └── Show Name (Year) - S00E01 - Special Title.ext
```

### 3.2 完整示例

```text
TV Shows/
└── Breaking Bad (2008) [tmdbid=1396]/
    ├── tvshow.nfo
    ├── poster.jpg
    ├── fanart.jpg
    ├── Season 01/
    │   ├── season01-poster.jpg
    │   ├── Breaking Bad (2008) - S01E01 - Pilot.mkv
    │   ├── Breaking Bad (2008) - S01E02 - Cat's in the Bag.mkv
    │   └── Breaking Bad (2008) - S01E01-E03.mkv
    └── Season 00/
        └── Breaking Bad (2008) - S00E01 - No-Rough-Stuff-Type Deal.mkv
```

### 3.3 多版本剧集（同一集多版本）

```text
TV Shows/
└── Game of Thrones (2011) [tmdbid=1399]/
    └── Season 01/
        ├── Game of Thrones (2011) - S01E01 - Winter Is Coming.mkv
        ├── Game of Thrones (2011) - S01E01 - Extended Edition.mkv
        └── Game of Thrones (2011) - S01E01 - 4K HDR.mkv
```

注意：剧集与电影相同，单条目多版本上限同为 **8 个**。

### 3.4 集数补零规则

| 场景 | 正确写法 |
|------|----------|
| 第 1 季第 1 集 | `S01E01` |
| 第 10 季第 10 集 | `S10E10` |
| 单季超过 99 集 | `S01E100` |
| 特别篇第 1 集 | `S00E01` |

### 3.5 多集合并文件

```text
Breaking Bad (2008) - S01E01-E02.mkv
Breaking Bad (2008) - S01E01-E04.mkv
```

---

## 四、动漫命名

> 动漫条目务必先确认 TMDB 的“作品条目 + 季度划分”。

### 4.1 按 TMDB 季度命名（推荐默认方案）

```text
Anime/
└── Demon Slayer- Kimetsu no Yaiba (2019) [tmdbid=85937]/
    ├── Season 01/
    │   └── Demon Slayer- Kimetsu no Yaiba (2019) - S01E01.mkv
    ├── Season 02/
    │   └── Demon Slayer- Kimetsu no Yaiba (2019) - S02E01.mkv
    └── Season 03/
        └── Demon Slayer- Kimetsu no Yaiba (2019) - S03E01.mkv
```

### 4.2 绝对集数（Absolute Order）高级方案

| 方案 | 示例 | 配合工具 | 说明 |
|------|------|----------|------|
| 绝对集数命名 | `One Piece - 0001.mkv` | Absolute Series Scanner / Shoko Server | 通过绝对编号映射到 TMDB 季集 |
| 标准季集命名 | `One Piece (1999) - S01E01.mkv` | 无额外扫描器 | 直接按 TMDB 季集，兼容性最高 |

建议：优先使用“标准季集命名”。仅当 TMDB 季集与常见分组差异过大时，再采用绝对集数方案。

### 4.3 OVA / 特别篇 / 总集篇

统一放入 `Season 00`：

```text
Sword Art Online (2012) [tmdbid=45782]/
└── Season 00/
    ├── Sword Art Online (2012) - S00E01 - Special Edition.mkv
    ├── Sword Art Online (2012) - S00E02 - Recap Episode.mkv
    └── Sword Art Online (2012) - S00E03 - Extra Edition.mkv
```

### 4.4 动漫剧场版

剧场版建议按电影独立建库：

```text
Movies/
└── Demon Slayer- Kimetsu no Yaiba - The Movie- Mugen Train (2020) [tmdbid=635302]/
    └── Demon Slayer- Kimetsu no Yaiba - The Movie- Mugen Train (2020).mkv
```

### 4.5 高级动漫管理（AniDB / Shoko）

- `Shoko Server`：通过文件哈希匹配 AniDB，可生成 NFO、辅助重命名并处理绝对集数映射。
- AniDB 与 TMDB 并行时：建议以 TMDB 为主展示源，AniDB 信息写入自定义 NFO 字段作为补充。
- 先在小样本目录验证映射结果，再全库批量应用。

---

## 五、纪录片命名

### 5.1 纪录片电影

```text
Documentaries/
└── Free Solo (2018) [tmdbid=549220]/
    └── Free Solo (2018).mkv
```

### 5.2 纪录片剧集

```text
Documentary Series/
└── Our Planet (2019) [tmdbid=79242]/
    └── Season 01/
        ├── Our Planet (2019) - S01E01 - One Planet.mkv
        └── Our Planet (2019) - S01E02 - Frozen Worlds.mkv
```

---

## 六、音乐 MV / 演唱会命名

### 6.1 演唱会（建议归入电影库）

```text
Movies/
└── Taylor Swift- The Eras Tour (2023) [tmdbid=916745]/
    └── Taylor Swift- The Eras Tour (2023).mkv
```

### 6.2 MV 合集（建议归入剧集库）

```text
TV Shows/
└── Taylor Swift - Music Videos/
    └── Season 01/
        ├── Taylor Swift - Music Videos - S01E01 - Shake It Off.mkv
        └── Taylor Swift - Music Videos - S01E02 - Blank Space.mkv
```

---

## 七、字幕文件命名

### 7.1 格式规范

```text
视频文件名.语言代码.扩展名
视频文件名.语言代码.forced.扩展名
视频文件名.语言代码.sdh.扩展名
```

### 7.2 常用语言代码

| 代码 | 语言 | 备注 |
|------|------|------|
| `chs` | 简体中文 | Emby 常见兼容写法 |
| `cht` | 繁体中文 | Emby 常见兼容写法 |
| `zh-Hans` | 简体中文 | BCP47 标准 |
| `zh-Hant` | 繁体中文 | BCP47 标准 |
| `en` | 英语 | |
| `ja` | 日语 | |
| `ko` | 韩语 | |
| `fr` | 法语 | |
| `de` | 德语 | |

建议：优先使用 Emby 可识别的标准语言代码，并在全库保持一致。

### 7.3 字幕示例

```text
The Dark Knight (2008)/
├── The Dark Knight (2008).mkv
├── The Dark Knight (2008).chs.srt
├── The Dark Knight (2008).cht.srt
├── The Dark Knight (2008).en.srt
├── The Dark Knight (2008).en.sdh.srt
└── The Dark Knight (2008).chs.forced.srt
```

---

## 八、多音轨 / 附加音频

Emby 原生支持 MKV 内封多音轨。外挂音频可用于评论音轨等场景：

```text
The Dark Knight (2008)/
├── The Dark Knight (2008).mkv
└── The Dark Knight (2008).commentary.mp3
```

---

## 九、图片与附加元数据文件

### 9.1 电影目录常见文件

```text
The Dark Knight (2008) [tmdbid=155]/
├── The Dark Knight (2008).mkv
├── The Dark Knight (2008).nfo
├── poster.jpg
├── fanart.jpg
├── banner.jpg
├── disc.jpg
├── logo.png
└── thumb.jpg
```

### 9.2 剧集目录常见文件

```text
Breaking Bad (2008) [tmdbid=1396]/
├── tvshow.nfo
├── poster.jpg
├── fanart.jpg
├── banner.jpg
└── Season 01/
    ├── season01-poster.jpg
    ├── Breaking Bad (2008) - S01E01 - Pilot.mkv
    ├── Breaking Bad (2008) - S01E01 - Pilot.nfo
    └── Breaking Bad (2008) - S01E01 - Pilot-thumb.jpg
```

### 9.3 剧集/电影 Extras 文件夹位置

上述 `extras`、`trailers` 等附加内容文件夹可放在电影目录根下，也可放在剧集根目录下，由 Emby 归类到“附加内容”。

---

## 十、NFO 元数据说明

NFO 用于锁定元数据来源，降低刮削覆盖风险。建议统一 UTF-8 无 BOM。

### 10.1 电影 NFO 最小结构

```xml
<?xml version="1.0" encoding="UTF-8"?>
<movie>
  <title>The Dark Knight</title>
  <originaltitle>The Dark Knight</originaltitle>
  <year>2008</year>
  <tmdbid>155</tmdbid>
  <imdbid>tt0468569</imdbid>
</movie>
```

### 10.2 电影 NFO 扩展示例

```xml
<?xml version="1.0" encoding="UTF-8"?>
<movie>
  <title>The Dark Knight</title>
  <originaltitle>The Dark Knight</originaltitle>
  <sorttitle>Dark Knight, The</sorttitle>
  <year>2008</year>
  <premiered>2008-07-18</premiered>
  <tmdbid>155</tmdbid>
  <imdbid>tt0468569</imdbid>
  <set>
    <name>The Dark Knight Collection</name>
  </set>
  <genre>Action</genre>
  <genre>Crime</genre>
  <country>USA</country>
</movie>
```

### 10.3 剧集 `tvshow.nfo` 最小结构

```xml
<?xml version="1.0" encoding="UTF-8"?>
<tvshow>
  <title>Breaking Bad</title>
  <year>2008</year>
  <tmdbid>1396</tmdbid>
  <imdbid>tt0903747</imdbid>
</tvshow>
```

### 10.4 动漫剧场版与正片关联建议

- `<related>` 等自定义标签并非通用标准，Emby 不保证识别。
- 建议把剧场版作为独立电影条目。
- 优先依赖 TMDB 的合集关系自动聚合；必要时在 Emby 内手动建立合集。

---

## 十一、特殊字符清理规则

| 字符/问题 | 处理方式 | 示例 |
|-----------|----------|------|
| `:` | 替换为 `-` 或 ` - ` | `Spider-Man: No Way Home` → `Spider-Man- No Way Home` |
| `?` | 删除 | `Who Am I?` → `Who Am I` |
| `/` | 替换为 `-` | `AC/DC` → `AC-DC` |
| `"` | 删除 | `"Hello"` → `Hello` |
| `\|` | 替换为 `-` | |
| `*` | 删除 | |
| `< >` | 删除 | |
| 文件名尾部空格 | 删除 | `Movie Name .mkv` → `Movie Name.mkv` |
| 文件名尾部点 `.` | 删除 | `Movie Name..mkv` → `Movie Name.mkv` |

说明：文件名末尾空格或点在部分文件系统会被截断，导致路径不一致或重命名失败。

---

## 十二、软链接 / 硬链接场景

- 硬链接（Hard Link）：适合同一文件系统内“一个文件，多库呈现”，不重复占用空间。
- 软链接（Symbolic Link）：适合跨目录或跨盘场景；需在 Emby 中启用“跟随符号链接”。
- 推荐用途：跨库复用、系列合集镜像、测试库与正式库共用文件。
- 注意事项：避免循环链接；批量迁移前先抽样扫描确认路径可达。

---

## 十三、常见错误对照表

| 错误写法 | 正确写法 | 原因 |
|----------|----------|------|
| `黑暗骑士 (2008)` | `The Dark Knight (2008)` | 中文名常导致 TMDB 匹配偏差 |
| `The Dark Knight` | `The Dark Knight (2008)` | 缺少年份 |
| `S1E1` | `S01E01` | 位数不足 |
| `EP01.mkv` | `Show Name (Year) - S01E01.mkv` | 缺少季集规则 |
| `Season 1/` | `Season 01/` | 缺少补零 |
| 特别篇放在正片季 | 放入 `Season 00/` | 季集映射错位 |
| `Avatar (2009)` 未加 ID | `Avatar (2009) [tmdbid=19995]` | 同名冲突时易误匹配 |
| `Movie/disc1/BDMV` | `Movie/BDMV` | 蓝光原盘层级错误 |

---

## 十四、媒体库目录结构总览

```text
媒体根目录/
├── Movies/
│   ├── The Dark Knight (2008) [tmdbid=155]/
│   │   ├── The Dark Knight (2008).mkv
│   │   ├── The Dark Knight (2008).nfo
│   │   ├── poster.jpg
│   │   └── trailers/
│   │       └── Trailer 1.mkv
│   └── Avatar (2009) [tmdbid=19995]/
│       └── Avatar (2009).mkv
│
├── TV Shows/
│   └── Breaking Bad (2008) [tmdbid=1396]/
│       ├── tvshow.nfo
│       ├── Season 00/
│       │   └── Breaking Bad (2008) - S00E01.mkv
│       └── Season 01/
│           └── Breaking Bad (2008) - S01E01 - Pilot.mkv
│
├── Anime/
│   └── Demon Slayer- Kimetsu no Yaiba (2019) [tmdbid=85937]/
│       ├── Season 00/
│       ├── Season 01/
│       └── Season 02/
│
└── Documentaries/
    └── Free Solo (2018) [tmdbid=549220]/
        └── Free Solo (2018).mkv
```

---

## 十五、命名检查清单（v1.6）

- [ ] 使用 TMDB 英文原名与正确年份
- [ ] 电影/剧集命名格式统一且季集补零正确
- [ ] 特别篇 / OVA / 总集篇已归入 `Season 00`
- [ ] 多版本命名后缀规范，且每条目版本数不超过 8
- [ ] 电影原盘目录正确（`BDMV` 位于电影根目录）
- [ ] 若使用绝对集数，已配置对应扫描/映射工具
- [ ] 已对易混淆条目附加 `[tmdbid=xxxx]` 或 `[imdbid=ttxxxx]`
- [ ] 字幕与视频同名同目录，语言代码使用统一规范
- [ ] NFO 编码为 UTF-8（建议无 BOM）
- [ ] 文件名无非法字符，且结尾无空格或点
- [ ] 软链接场景已启用“跟随符号链接”并完成抽样验证

---

## 附录：推荐工具

| 工具 | 用途 | 平台 |
|------|------|------|
| [FileBot](https://www.filebot.net/) | 批量重命名与基础刮削 | Win / Mac / Linux |
| [tinyMediaManager](https://www.tinymediamanager.org/) | 图形化刮削与 NFO 管理 | Win / Mac / Linux |
| [Bazarr](https://www.bazarr.media/) | 自动字幕下载与同步 | Win / Mac / Linux |
| [Radarr](https://radarr.video/) | 电影自动化管理 | Win / Mac / Linux |
| [Sonarr](https://sonarr.tv/) | 剧集自动化管理 | Win / Mac / Linux |
| [Shoko Server](https://shokoanime.com/) | AniDB 哈希匹配、动漫元数据与重命名辅助 | Win / Linux / Docker |

---

*Emby / TMDB 媒体库命名规范指南 v1.6 · 2026-02-25*

