# 播客图解项目约定

- 项目唯一源码分支为 `main`。原始数据在 `/Users/sym/code/my-data/xiaoyuzhou`，只读；禁止修改、复制进仓库或部署目录。
- 产物、网页源码和计划保存在本项目。NotebookLM 使用 `nlm`，中文、详细、丁丁历险记漫画风格，一集一套。
- 制作前读 `PLAN.md`、`state/progress.json` 和 `state/queue.json`。每天北京时间13:00选择10个新单集，历史未完成任务另行续做；同一天重跑复用原批次，不追加新集。
- 进度文件是本地权威记录。`complete` 仅表示图文和PDF都已准备好；只有经HTTPS验证后才写 `publication_status=verified`。失败与提交不明的生成不能记为成功。
- 只重试未完成步骤，结果不明的提交先查NotebookLM；不得删除已有笔记本或产物。同一步当天最多重试3次，超过后记录并报告，次日继续；不盲目重复提交结果不明的任务。
- 文案用短句、常用词；核对同音人名、金额和数量。保留原节目、章节时间戳，避免绝对化和未经来源支持的人物指责。
- 幻灯片选页作为网站插图；不要用装饰占位图冒充内容插图。公开站点只包含 `dist/`，不包含 `state/`、`work/` 和认证信息。
- 使用 hn-project-publisher 发布到 Cloudflare Workers 自定义域名及 xiaosang.cc 作品集。用户已明确授权首次发布和每日内容更新；GitHub公开仓库只含本项目的源码与加工产物。
- 不创建发布分支、GitHub Actions或Workers Git自动部署。每天内容通过本地锁定版Wrangler从已提交、已推送的main同一提交发布。
- 作品集为 `/Users/sym/code/holynova.github.io` 的 master，保留其他工作区文件和条目。有效条目后续复用。

- 请求节奏：生成间隔至少10分钟、最多一个在途任务；提交后先等待20分钟，再每5分钟查状态一次、普通CLI请求至少间隔15秒。限流或生成失败后同一账号冷却5小时，冷却和排队不记作失败。禁止为凑每日目标绕过冷却或失败次数上限。

- 第二账号account-b已授权补做首批百度上半场、腾讯QQ。各账号独立计算请求间隔、冷却和失败次数，保留原账号历史；由supplement_account.py管理这两集，默认runner跳过delegated_profile集，避免重复提交。
