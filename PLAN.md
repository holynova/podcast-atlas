# 播客图解制作计划

来源：半拿铁231集、知行小酒馆256集，共487集可用；23集缺失文稿。仅处理2026-10-09下载的现有数据，不抓新节目。

## 优先级

1. 中国互联网故事，按系列编号。第2集文稿缺失，保留缺失记录。首批为1、3—11，共10集。
2. 苹果公司简史，共5集，按1—5。
3. 中国股市往事，再到硅谷神话、芯片江湖、任天堂往事、日本漫画史、中国饮料故事、房产万事屋、养老专题、科龙往事。
4. 其余两档播客合并，按发布时间从新到旧。

专题归类基于实际节目标题；对不明确的主题不强行归类。`state/queue.json`保存完整510集顺序与可用性。原文缺失不是制作失败，不用简介补位。

## 每日流程

每天北京时间13:00，由当前Codex聊天的定时任务继续，Mac需开机联网且Codex可运行。首批立即执行。

```bash
cd /Users/sym/code/podcast-atlas
python3 scripts/pipeline.py run --limit 10 --wait-minutes 150
python3 scripts/pipeline.py status
# 只收取已提交的结果，不发起新生成：
python3 scripts/pipeline.py collect --wait-minutes 0
```

程序使用文件锁避免并发、原子写入进度；同日重复执行复用已选10个新单集。历史未完成任务另记retry_ids，续收与重试不挤占当天的新单集队列。先上传带时间戳逐字稿，再逐集指定source ID生成详细中文漫画幻灯片和结构化讲解。生成成功后下载并验证PDF，导出封面及内页WebP，构建静态网站。每集分别保存source、article、slides、download、publication状态。原始上传暂存文件在被忽略的work目录。

NotebookLM按专题共用笔记本；其余单集按节目每50集分组，避免为487集各建一个笔记本超出账户上限。所有查询和幻灯片都只选择对应单集来源。

同一步当天失败至多3次，历史错误永久保留，次日重置当天失败计数再续做。连接错误可重跑同一批次；明确额度耗尽记录重置时间后续做。已确认生成失败可用以下命令启用重试；结果不明的提交必须先核实NotebookLM，不盲目再提交。

```bash
python3 scripts/pipeline.py retry --id EPISODE_ID --stage article
python3 scripts/pipeline.py retry --id EPISODE_ID --stage slides
```

每日目标10集；若平台额度或认证阻止达成，准确记录实际成功量，不虚报成功。每天按队列选10个未安排过的新单集，同时续做旧任务。图文成功而PDF未完成时允许网页先上线，页面明确显示幻灯片等待中。

## 校对与发布

校对人名、章节时间和关键数字，确认讲解覆盖全程、使用通俗语言且没有把片头混剪当正文。核实图像和PDF实际内容、封面与正文对应。图文及PDF下载成功不等于已公开上线。

```bash
npm run build
python3 scripts/check.py
npm run deploy:check
```

有应用变更时递增版本、更新截图、按本次明确路径提交到main并推送；从该提交重新构建，在本地`npm run deploy`。只上传dist目录。域名为 `https://xiaosang.cc/podcast-atlas/`，Worker为 `podcast-atlas`。Wrangler精确版本由package-lock.json固定。

首次发布还需要真实截图、二维码、双语README、GitHub Homepage、Umami以及xiaosang.cc作品集独立部署与回读验证。每日新增内容已获发布授权，使用本地Wrangler，不添加Git或CI自动部署。

部署后执行 `python3 scripts/record_deployment.py --deployment-id <真实部署ID>`，实际HTTPS验证首页、单集深层路径、CSS、JS、PDF和图片后，才在state/progress.json记录源码SHA、版本、部署ID、上线集数和publication_status=verified。作品集有效条目后续复用。全部现有文稿完成后关闭定时任务。

## 本地文件

- `state/progress.json`：权威进度、远端ID、错误与发布记录。
- `state/queue.json`：固定现有数据制作队列，不含逐字稿正文。
- `content/*.json`：加工后的讲解、时间线、人物关系和术语。
- `assets/slides/*.pdf`：中文详细漫画幻灯片。
- `assets/illustrations/*/*.webp`：幻灯片精选插图。
- `dist/`：可公开部署的网站；构建产物不入Git。

## 外部状态

每日自动化已创建（ID：automation），每天13:00触发当前聊天。Cloudflare认证已核实有效。如网络导致认证刷新失败，先使用 `NODE_OPTIONS=--dns-result-order=ipv4first npx wrangler whoami` 重试；仅在确认凭据无效时请用户完成登录。

## 已核实的发布例外

Cloudflare 返回 code 100122：xiaosang.cc 已达到100个 Workers Custom Domains 上限。因此本项目复用现有主域名，使用独立 podcast-atlas Worker 的路径路由 `xiaosang.cc/podcast-atlas` 与 `xiaosang.cc/podcast-atlas/*`。最终网站地址为 https://xiaosang.cc/podcast-atlas/。worker.js 去除请求前缀后读取 ASSETS，并保留资源重定向前缀。所有公开链接、二维码、README、GitHub Homepage和作品集都使用此地址。不更改其他项目域名、不新增Pages或CI部署。

网络：scripts/run_wrangler.py 和 NotebookLM runner 会继承已设置的HTTP_PROXY/HTTPS_PROXY；没有命令行代理变量时读取Mac已有的系统HTTPS代理，供当前命令使用。npm部署命令因此可以沿用本机Clash网络配置。

生成节奏：新幻灯片请求间隔至少10分钟，整个账户本项目同时最多一个在途任务。先收取和核实旧任务，再提交下一集；跨进程保留最后提交时间和冷却时间。每5分钟查询一次状态，每轮每个笔记本只查一次；普通CLI请求至少间隔15秒，不启用生成请求的隐式重试。

明确限流或没有详细原因的生成失败后，暂停新幻灯片提交5小时，这是保守退避，不等同已确认账户重置时间；账户Usage提供恢复时间时应以实际时间调整。冷却期间仍可收取已成功产物。延期不记为失败，不重置已有失败次数。每日运行最多150分钟，只提交时间窗口内允许的任务，其余持久化留到下一次；每天10集是目标，不保证额度允许全部成功。先做旧任务，再安排当日新内容。
