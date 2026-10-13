# 播客图解制作计划

## 当前规则（2026-10-13更新）

每5小时续做一次，两账号合计目标5套漫画幻灯片。先整理文字讲解并发布，再逐步补齐PDF和选图；文字成功不依赖幻灯片成功。每轮优先尝试5篇尚未完成的讲解，幻灯片优先补已有文字的单集。平台限流、失败和超时可能导致实际数量低于目标，必须记录实际结果。

```bash
cd /Users/sym/code/podcast-atlas
# 只看本轮计划，不调用NotebookLM、不保存新批次：
python3 scripts/cycle.py --plan-only
# 第一阶段：先整理文字，不提交幻灯片；结束后校对并发布文字版：
python3 scripts/cycle.py --text-only --article-limit 5 --wait-minutes 150
# 第二阶段：同周期复用目标与已整理文字，补齐最多5套幻灯片：
python3 scripts/cycle.py --slide-limit 5 --article-limit 5 --wait-minutes 150
# 结束后校对新PDF和插图，再发布补齐版。
```

文字阶段结束后先发布，之后再运行幻灯片阶段，避免文字等待PPT。两个阶段和中间发布共用同一150分钟续做窗口，第二次调用不会重置预算；制作进程与部署命令顺序执行。

周期记录在state/progress.json.cycles。周期按config.json.cycle_anchor_at划分，每5小时一个窗口，不因跨午夜重置。同一窗口重跑复用目标、尝试与远端ID，不新增一批。每集每个步骤当天最多3次失败，历史记录保留；次日只重置当天计数。幻灯片未知失败与明确限流均按5小时退避；更晚的真实额度恢复时间则延期。冷却、排队和已记录的失败不重复计数。同一集在本周期最多提交一次，结果不明先查远端。

普通CLI请求至少间隔15秒；每个账号最多一个在途幻灯片，生成提交间隔至少10分钟。提交后先等待20分钟，再每5分钟查一次，每轮每个笔记本只查一次。协调器可同时保留两账号的远端任务，但在本地用共同写锁保护进度；等待期间释放写锁。不切换nlm保存的全局默认账号。

## 内容分工与优先级

用户可主动要求批量预生产网页文字。2026-10-13已授权5个sub agent补齐现有48个专题单集：互联网与半拿铁股市9集、苹果与日漫9集、硅谷/芯片/任天堂12集、小酒馆股市/房产/养老10集、饮料/科龙8集。按可用并发分批启动，总批次保存在state/progress.json.text_batches，单集分配互不重复。直接根据本地文稿改写并校对content JSON，不调用NotebookLM；文字可独立上线，已有PPT队列、远端ID、失败历史与冷却保留。完成专题后再从新到旧处理单集精选。

只读取 /Users/sym/code/my-data/xiaoyuzhou 的现有文稿，不修改私有项目、不抓新节目。现有487集可用、23集缺少文稿。缺失文稿保留目录，不用节目简介补位。

- default：优先中国互联网故事，然后按固定专题顺序、剩余单集从新到旧。
- account-b：苹果公司简史1—5，然后日本漫画史1—7，系列内顺序；保留百度上半场补齐任务。QQ已由default完成，第二账号superseded记录只供追溯，不再重复制作。
- 两账号的来源、笔记本、产物、冷却和失败次数分别保存。主进度合并完成结果，默认runner跳过delegated_profile集。
- 每轮目标按两账号轮流分配（通常default3套、account-b2套）；一个账号无可用任务时由另一个补足目标，仍不超过合计5套。失败和冷却不能为了凑数而绕过。

半拿铁与知行小酒馆的专题以“播客 + 专题”分组。同名专题有独立页面、计数和下一集导航。搜索覆盖公开节目元数据和已加工的讲解正文，不公开原始逐字稿、认证或内部错误日志。

## 校对与公开发布

网站状态分为“文字待整理”“文字已整理、幻灯片待补”“文字 + 幻灯片”。文字讲解可以独立上线；幻灯片生成成功后还须下载校验PDF、校对姓名和数字、检查插图，再补入网站。complete仅表示文字与PDF齐备，publication_status=verified仅在真实HTTPS校验通过后写入。

```bash
npm run build
python3 scripts/check.py
npm run deploy:check
```

用户已授权公开发布。使用hn-project-publisher：应用变更递增版本，运行检查，仅暂存明确文件到唯一main，提交推送成功后从同一提交构建，以本地锁定Wrangler手动部署。生成与部署分开进行。不创建发布分支、GitHub Actions或Workers Git自动部署。

实际网站：https://xiaosang.cc/podcast-atlas/ 。Cloudflare达到100个Custom Domains上限，因此保留独立podcast-atlas Worker与xiaosang.cc/podcast-atlas路径路由、worker.js、wrangler.jsonc和base_path，不改其他项目路由。有效的作品集、GitHub Profile、二维码和仓库Homepage复用。

部署后运行 `python3 scripts/record_deployment.py --deployment-id 实际部署ID`，校验首页版本、播客专题、搜索目录、单集、PDF哈希和插图后，才记录源码SHA与上线状态。若认证网络失败，可使用NODE_OPTIONS=--dns-result-order=ipv4first；真正凭据失效才需要用户登录。

## 本地进度

- state/progress.json：主进度、周期计划、远端ID、失败历史与发布记录。
- state/accounts/account-b.json：第二账号的独立记录。
- state/queue.json：固定现有节目目录，不含逐字稿正文。
- content/*.json：加工后的文字讲解。
- assets/slides/*.pdf 与 assets/illustrations/：经过校对的幻灯片和选图。
- work/：临时来源、诊断材料和历史计划，仅本地保留。

用户手动重试时记录manual_retry_watch：check_not_before之前不查询该笔记本，核实结果前不新建重复任务。诊断产物ID列入diagnostic_artifact_ids，禁止当正式成品发布。所有现有文稿与成品都完成后关闭自动化。
