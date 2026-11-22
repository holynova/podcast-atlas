<p align="right"><a href="README.en.md">English</a></p>

<p align="center">
  <img src="./assets/readme/hero.svg" width="100%" alt="播客图解 Podcast Atlas — 把长故事，读成一张清晰的地图：半拿铁与知行小酒馆的中文图文知识库，364 已整理单集">
</p>

<p align="center">
  <a href="https://xiaosang.cc/podcast-atlas/">▶ 在线阅读</a>
  ·
  <a href="https://github.com/holynova/podcast-atlas">GitHub 仓库</a>
</p>

播客图解把半拿铁、知行小酒馆的故事整理成中文图文知识库：按专题阅读，每集有讲解正文、时间线、人物关系与因果链，搭配中文漫画幻灯片。两档播客各有专题目录，按 Cmd/Ctrl+K 可搜索标题、人物与讲解正文。

## 截图

<p align="center">
  <img src="./assets/readme/screenshot-home.png" width="100%" alt="播客图解首页：把长故事读成一张清晰的地图，364 已整理单集、510 单集总数、12 深度专题，右侧是苹果简史漫画幻灯片封面">
</p>

## 收录规模

| 播客 | 专题 | 单集 |
|---|---:|---:|
| 半拿铁 | 9 个 | 239 集 |
| 知行小酒馆 | 3 个 | 271 集 |
| **合计** | **12 个深度专题** | **510 集，364 集已整理** |

数量以仓库 `content/` 的 364 份单集讲解与线上首页统计为准（2026-11-22）。漫画幻灯片 426 套（6,119 张图片），插图 2,983 张。

## 每集包含什么

- **讲解正文**： headline + 导读 + 分节正文，把一集长故事讲成可读的文章。
- **要点**：一集的核心结论，先看要点再决定读不读全文。
- **时间线**：事件按时间展开，看到因果如何一步步发生。
- **人物**：出场人物小传与关系，复杂的人物网一图看清。
- **因果链与机制**：事情为什么会这样、背后的机制是什么。
- **术语与注意事项**：生词解释，以及整理时不确定的地方。
- **漫画幻灯片**：中文漫画风格的幻灯片（WebP 图片），一集一图讲清主线。
- **原节目入口**：每集保留小宇宙原节目链接及回听时间。

## 阅读方式

- **按专题读**：首页「沿着一个专题，读下去」，从一个话题连续读完相关单集。
- **按单集读**：单集列表分批加载，每批 24 集，滚动到底自动续载。
- **搜索**：按 Cmd/Ctrl+K，搜标题、人物与讲解正文；搜索先加载轻量目录，再按需加载正文。

## 本地运行

```bash
npm install
npm run build
npm run dev
```

构建封面缩略图需要 Pillow；页面使用系统中文字体。内容持续更新，每 5 小时续做一轮：文字先发布，幻灯片逐步补齐。原始逐字稿留在独立的私有数据项目中，不公开上传到本站或仓库。

## 目录结构

```
app.js                前端交互：筛选、搜索、灯箱
search.js             搜索分片加载
style.css             全站样式
config.json           站点配置（域名、路径、生产节奏）
content/              364 份单集讲解（JSON，一集一份）
assets/slide-decks.json  426 decks, 6,119 page image hashes
assets/illustrations/ 2,983 张漫画插图（webp）
scripts/build.py      构建脚本：生成静态站
scripts/cycle.py      生产周期脚本（每 5 小时一轮）
scripts/pipeline.py   内容生产流水线
tests/                搜索、生产周期与站点性能测试
```

## 声明

网页讲解与漫画为 AI 辅助整理，可能存在识别或生成错误；每集保留原节目入口及回听时间。完整原始逐字稿不属于公开产物。

运行 `npm run build` 构建当前公开资料。在发布窗口将源码推送到 `main` 后，运行 `npm run deploy:check` 与 `npm run deploy`。

<a href="https://xiaosang.cc/podcast-atlas/"><img src="assets/readme/qr.png" width="112" alt="扫码打开网站"></a>

## 纯图片交付（2026-11-22）

网站只展示 WebP 幻灯片，不发布、查看或下载 PDF。完成依据是 `assets/slide-decks.json` 中的整套图片清单及文字，不能以本地 PDF 是否存在判断或重新提交已完成任务。NotebookLM 的 PDF 只作为临时转换输入保存在 `work/slide-inputs/`；全部输出图片通过上线哈希验证后自动删除对应输入。生成、转换、状态写入及发布仍遵守现有锁与额度规则。

图片清单入 Git，完整页图片缓存位于被忽略的 `work/site-slides/`。构建缺少图片时，从已发布 HTTPS 地址恢复并验证 SHA-256；恢复失败则停止发布，避免丢失旧页面。新生成且未上线的图片必须保留。`npm run build` 可重建 `dist/`，macOS 优先采用 APFS 写时复制，避免重复占用。Wrangler 按内容复用已上传文件，每次仍提交完整资源清单，不能只部署新增文件目录。旧 Git 历史不在本次改写范围。
