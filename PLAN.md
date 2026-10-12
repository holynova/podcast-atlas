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

生成节奏：新幻灯片请求间隔至少10分钟，整个账户本项目同时最多一个在途任务。先收取和核实旧任务，再提交下一集；跨进程保留最后提交时间和冷却时间。提交后先等待20分钟，再每5分钟查询一次状态，每轮每个笔记本只查一次；普通CLI请求至少间隔15秒，不启用生成请求的隐式重试。

明确限流后暂停新幻灯片提交5小时；无详情的生成失败只要求从上次提交起间隔至少30分钟，不认定额度耗尽；这是项目退避策略，不等同已确认账户重置时间；账户Usage提供恢复时间时应以实际时间调整。冷却期间仍可收取已成功产物。延期不记为失败，不重置已有失败次数。每日运行最多150分钟，只提交时间窗口内允许的任务，其余持久化留到下一次；每天10集是目标，不保证额度允许全部成功。先做旧任务，再安排当日新内容。

第二个账号补齐：用户已授权account-b制作首批缺失的百度上半场、腾讯QQ。运行 `python3 scripts/supplement_account.py --profile account-b --wait-minutes 60`。账号B有独立笔记本、来源、产物ID、失败次数和冷却，记录在被忽略的state/accounts/account-b.json，主进度保留第一账号历史。未完成集标记delegated_profile，默认任务不再重复制作；成功后合并到主进度并统一发布。默认账号其他集及原有产物保持原样，不切换CLI全局默认账号。

账号B本次创建笔记本曾返回NOT_FOUND，刷新会话后恢复并成功上传两集。百度上半场生成失败后额度仍显示100%，原因未知，冷却至2026-10-12 01:18:58（北京时间）。腾讯QQ尚未提交；续做优先未尝试过的任务，避免失败项一直占住队列。额度可用不意味着应跳过已设置冷却。

2026-10-11 22:23后复查：第二账号百度任务距提交已超过两小时，远端仍为failed；第一账号百度、QQ也没有新完成产物。新增generation_initial_wait_seconds=1200，提交时间逐集持久化，首20分钟不查询或判失败，此后每5分钟检查。第二账号补齐窗口延长为60分钟，可覆盖两集顺序生成。

2026-10-12续做修复：收取已归档failed产物时不再把旧失败记作新失败或延长冷却；保留原始错误及本次纠正记录，恢复原冷却截止。QQ已获提交机会。

2026-10-12每日批次：中国互联网故事12—21共10集已安排；7篇讲解完成，今日头条、电商三国综合篇、盛大3篇因查询超时/SSL错误未完成。仅讲解重试的两次自动权限审核都超时，执行未开始，保留任务。第二账号QQ与第一账号校内网幻灯片均在等待20分钟后确认failed，接口未提供原因，分别冷却至18:25:21和19:31:33；未新增PDF。v1.0.5准备发布7篇讲解，幻灯片选图显示等待状态，复用既有8套PDF。

2026-10-12晚间诊断：两个账号原参数的原地重试都仍失败；第二账号同一QQ来源的短普通提示词与短丁丁漫画提示词对照均成功下载15页PDF。生产模板改用实测短漫画提示词，保留中文、详细模式及单集来源。对照文件只在work中，不计正式完成，不公开。服务端没有给出具体失败原因，不能把提示词相关性等同已确认内部根因。

用户手动重试时，state/progress.json.manual_retry_watch记录最早检查时间。在此时间前不查询该笔记本；核实远端结果前不新建重复任务。原地重试可用项目本地CLI扩展 `python3 scripts/retry_tracked_slide.py --profile default --episode EPISODE_ID --artifact ARTIFACT_ID`，只允许已确认失败的跟踪产物，保留来源、原参数和失败历史。此操作本身不保证修复服务端失败。

当前两个runner共享运行锁且自动化顺序调用，尚不支持真正的双账号并行；不要绕过锁并发写主进度。单账号20分钟生成、150分钟窗口不保证每日10套完成。

21:45:13 nlm核实第一账号手动重试后，5个原失败产物转为completed：阿里巨头史3套、阿里创业史1套、腾讯QQ1套。前两集已有发布成品，本次只补QQ正式15页PDF和7张选图。账号B的QQ任务记superseded，保留失败历史及诊断记录，避免重复制作；百度上半场仍未完成。

2026-10-12 22:59：第二账号新增苹果公司简史1—5、日漫史1—7共12集队列，先苹果再日漫，使用nlm和短中文丁丁漫画模板。一集完成后再提交下一集，每个账号最多一个在途。图文与幻灯片分阶段记录；排队和提交不记为完成。

2026-10-12 23:17复查第一账号：本轮新增2套completed（王兴/校内网、QQ另一版本），仅王兴补为新完成单集。第二账号苹果简史1于23:05提交，等待20分钟后收取completed，15页。已校对姓名错字、首创/价格表述及Apple II硬件示意说明；原PDF仅保存work中。正式完成11集，v1.0.7准备统一发布王兴和苹果第1集；苹果余4集、日漫7集继续排队。
