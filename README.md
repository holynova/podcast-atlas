# 播客图解 / Podcast Atlas

把半拿铁、知行小酒馆的故事整理成中文图文知识库：按专题阅读，查看时间线、人物关系和因果链，搭配 NotebookLM 生成的详细漫画幻灯片。两档播客各有专题目录，可按 Cmd/Ctrl+K 搜索标题、人物与讲解正文。每5小时续做一轮，两账号合计目标5套幻灯片；文字先发布，PDF与选图逐步补齐，失败保留记录。原始逐字稿留在独立私有数据项目中，不公开上传到本站或仓库。

A Chinese visual reading library for Half Latte and Zhixing Tavern podcasts. Topic collections connect episode explainers, timelines, people, causal diagrams and illustrated NotebookLM slide decks. Separate podcast topic collections and Cmd/Ctrl+K search cover titles, people and processed articles. A local task runs every five hours, targets five slide decks across both accounts, and publishes text before adding reviewed slides. Original transcripts stay outside this repository and the public website.

![真实网站预览 / Website screenshot](assets/screenshot.png)

- [Cloudflare Demo](https://xiaosang.cc/podcast-atlas/)
- [GitHub Repo](https://github.com/holynova/podcast-atlas)

<img src="assets/qr.png" width="160" alt="扫码访问播客图解网站 / Scan to visit Podcast Atlas">

## 本地运行 / Run locally

```bash
npm install
npm run build
npm run dev
```

See `config.json` for the read-only source directory, `PLAN.md` for production order and `state/progress.json` for local progress. To resume a cycle, run `python3 scripts/cycle.py --slide-limit 5 --article-limit 5 --wait-minutes 150`. Use `--text-only` to prepare articles first, or `--plan-only` to inspect the shared cycle without making requests. NotebookLM requires an authenticated `nlm` CLI. PDF previews use the bundled Python/Pillow/pypdf and Poppler runtime paths configured in `scripts/render_slides.py`.

## 发布 / Deploy

```bash
npm run build
python3 scripts/check.py
npm run deploy:check
npm run deploy
```

Cloudflare Workers · Domain: `xiaosang.cc` · Route: `/podcast-atlas/`.
Use the sole `main` source branch and deploy locally from its committed, pushed state. No Cloudflare CI or Git integration. The five-hour Codex task invokes the same local workflow.

网页讲解与漫画为AI辅助整理，可能存在识别或生成错误；每集保留原节目入口及回听时间。完整原始逐字稿不属于公开产物。
