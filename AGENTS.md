# 播客图解项目约定

- 唯一源码分支main。/Users/sym/code/my-data/xiaoyuzhou仅只读；不修改私有项目，不抓新节目，不将原文、认证或内部错误日志放入仓库或dist。
- 先读PLAN.md、config.json、state/progress.json与state/queue.json。当前调度每5小时一次，两账号合计目标5套幻灯片；旧“每天13:00、10集”已被替代。
- 第一阶段运行 `python3 scripts/cycle.py --text-only --article-limit 5 --wait-minutes 150`，结束后先校对并发布文字；第二阶段运行 `python3 scripts/cycle.py --slide-limit 5 --article-limit 5 --wait-minutes 150`，结束后校对PDF与选图再发布。两阶段及中间发布共用150分钟窗口，不重置预算。state/progress.json.cycles保存周期目标，同周期重跑不追加、不重复提交。
- 各步骤分别记录；complete要求文字及PDF齐备，publication_status=verified要求HTTPS验证通过。排队、提交和下载都不能冒充已上线。失败与历史不能删除；同集同步骤当天最多3次失败，次日保留历史后重置日计数。
- NotebookLM制作和排查只用nlm CLI。详细中文、丁丁历险记漫画风格，一集一套、指定单集source ID。两账号独立保存认证上下文、来源、笔记本、产物ID和冷却，不切换CLI保存的全局默认账号。
- default优先中国互联网故事；account-b优先苹果公司简史5集、再日本漫画史7集，并保留百度上半场补齐。config.json.account_b_series_ids是明确队列；QQ已由default完成时记superseded，禁止重复制作。
- 每个账号最多一个在途生成，提交间隔至少10分钟；首20分钟不查状态，此后每5分钟查一次，每轮每笔记本只查一次。普通CLI请求至少间隔15秒。失败后5小时退避，不将无详情失败认定为额度耗尽；更晚的实际Usage恢复时间优先。禁止为了凑目标绕过冷却或失败上限。
- 每周期每集最多一次提交机会，提交前持久化记录；结果不明先查远端。手动重试遵守manual_retry_watch，check_not_before前不查询，核实结果前不重复提交。diagnostic_artifact_ids禁止当正式成品使用。
- 协调器同时管理两账号的远端任务，本地写进度共用runner.lock；等待时释放锁，不绕过锁并发覆盖主进度。生成与部署不得同时进行。
- 文字用短句和常用词；校对同音人名、日期、金额、引用及PDF选图。文字已整理但幻灯片未齐时明确显示等待状态，不用装饰占位图冒充插图。
- 网站专题按“播客 + 专题”隔离，统计与下一集导航不得串播客。搜索只索引公开目录与加工后的讲解。
- 使用hn-project-publisher发布，用户已授权更新。仅暂存明确文件、提交推送main成功，再从同一提交用锁定Wrangler手动部署；不创建发布分支、GitHub Actions或Workers Git自动部署。
- 网站为https://xiaosang.cc/podcast-atlas/，保留podcast-atlas Worker、主域名路径路由、base_path、worker.js与wrangler.jsonc；不改其他项目路由。作品集master的有效条目与GitHub Profile复用。
- 部署后运行record_deployment.py，通过专题、搜索、单集、PDF和图片HTTPS检查才记verified。全部现有文稿及产物完成后关闭自动化。
