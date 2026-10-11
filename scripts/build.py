#!/usr/bin/env python3
import collections, html, json, pathlib, shutil
ROOT = pathlib.Path(__file__).resolve().parents[1]
DIST = ROOT / 'dist'
CFG = json.loads((ROOT / 'config.json').read_text())
VERSION = json.loads((ROOT / 'package.json').read_text())['version']
STATE = json.loads((ROOT / 'state/progress.json').read_text())
QUEUE = json.loads((ROOT / 'state/queue.json').read_text()) if (ROOT / 'state/queue.json').exists() else []
ARTICLES = {p.stem: json.loads(p.read_text()) for p in (ROOT / 'content').glob('*.json')}
E = lambda v: html.escape(str(v), quote=True)
TOPICS = list(dict.fromkeys(ep['topic'] for ep in QUEUE))

def shell(title, body, description='把播客里的长故事，变成看得懂的图文。半拿铁与知行小酒馆的中文图解知识库。', home=False):
    result = f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{E(title)} · 播客图解</title><meta name="description" content="{E(description)}"><meta name="theme-color" content="#f5f0e6"><link rel="icon" href="/favicon.svg" type="image/svg+xml"><link rel="stylesheet" href="/style.css"><meta property="og:title" content="{E(title)} · 播客图解"><meta property="og:description" content="{E(description)}"><meta property="og:image" content="{CFG['domain']}/assets/share.svg"><script defer src="https://cloud.umami.is/script.js" data-website-id="e01c9f78-4607-4e60-b01c-77c8190b12b4"></script><script defer src="/app.js"></script></head><body><a class="skip" href="#main">跳到正文</a><header class="topbar"><a class="brand" href="/" aria-label="播客图解首页"><span class="brand-icon">▰</span> 播客图解<span class="brand-en">PODCAST ATLAS</span></a><nav aria-label="主导航"><a href="/#series">专题</a><a href="/#library">单集</a><a href="/progress/">制作进度</a><a href="{CFG['repo']}" target="_blank" rel="noopener noreferrer">GitHub ↗</a></nav></header><main id="main">{body}</main><footer><a class="brand" href="/">播客图解</a><p>故事来自半拿铁与知行小酒馆。图文由逐字稿整理，保留原节目入口；识别和整理可能有误，建议结合原节目阅读。</p><span>中文图文知识库 · v{VERSION}</span><a href="{CFG['repo']}" target="_blank" rel="noopener noreferrer">源码与说明 ↗</a></footer></body></html>'''

    base = CFG.get('base_path', '')
    return result.replace('href="/', 'href="'+base+'/').replace('src="/', 'src="'+base+'/')

def topic_url(topic): return '/topics/' + str(TOPICS.index(topic) + 1) + '/'
def article_url(eid): return '/episodes/' + eid + '/'
def clean_title(t): return __import__('re').sub(r'^No\.\d+\s*[^\u4e00-\u9fffA-Za-z「《]*', '', t).split(' | ')[0]
def cover(ep):
    path = ROOT / 'assets/illustrations' / ep['id'] / '0.webp'
    if path.exists(): return f'<img src="/assets/illustrations/{ep["id"]}/0.webp" alt="{E(clean_title(ep["title"]))}：漫画幻灯片封面" loading="lazy" width="960" height="540">'
    return '<div class="cover-pending"><span>漫画配图制作中</span><small>等待漫画幻灯片生成</small></div>'

def card(ep):
    a = ARTICLES.get(ep['id']); ready = bool(a)
    link = article_url(ep['id']) if ready else topic_url(ep['topic'])
    headline = a['headline'] if a else clean_title(ep['title'])
    dek = a['dek'] if a else '这一集正在制作队列中，完成后会在这里补上图文讲解与中文漫画幻灯片。'
    pdf = (ROOT / 'assets/slides' / (ep['id'] + '.pdf')).exists()
    return f'''<article class="episode-card" data-search="{E(ep['title']+' '+ep['topic']+' '+ep['show'])}" data-show="{E(ep['show'])}"><a href="{link}" class="card-cover">{cover(ep)}</a><div class="card-copy"><div class="eyebrow">{E(ep['show'])} <span> / </span> {E(ep['topic'])}</div><h3><a href="{link}">{E(headline)}</a></h3><p>{E(dek)}</p><div class="card-bottom"><span>{ep['date']}</span><a href="{link}">{'阅读图解 ↗' if ready else '查看专题 →'}</a></div>{'<span class="pdf-badge">漫画幻灯片已就绪</span>' if pdf else ''}</div></article>'''

def index():
    completed = len(ARTICLES); available = sum(ep['available'] for ep in QUEUE)
    hero_ep = next((ep for ep in QUEUE if ep['id'] in ARTICLES), QUEUE[0] if QUEUE else None)
    if hero_ep:
        hero_art = ARTICLES.get(hero_ep['id']); hero_link = article_url(hero_ep['id']) if hero_art else topic_url(hero_ep['topic'])
        hero_visual = f'<a class="hero-story" href="{hero_link}">{cover(hero_ep)}<div class="hero-caption"><span>从这里开始 · 中国互联网故事 01</span><strong>{E(hero_art["headline"] if hero_art else "互联网之前，谁是中国的科技巨头？")}</strong><span>走进专题 →</span></div></a>'
    else: hero_visual = ''
    series = ''
    for i, topic in enumerate(TOPICS[:6]):
        eps = [ep for ep in QUEUE if ep['topic'] == topic]; n = sum(ep['id'] in ARTICLES for ep in eps)
        brief = {'中国互联网故事':'从中关村的第一批创业者，到我们每天使用的平台。','苹果公司简史':'从车库起步，走过低谷，重新定义个人电脑与手机。','中国股市往事':'交易所怎样诞生，市场又怎样一步步走到今天。','硅谷神话':'技术、资本与人物，怎样共同写下硅谷的故事。','芯片江湖':'一枚小芯片背后的产业、竞争与漫长追赶。','任天堂往事':'游戏机、好游戏，以及始终不变的玩家之心。'}.get(topic,'把相关故事放在一起，沿着一条清晰的线读下去。')
        series += f'<a class="series-item" href="{topic_url(topic)}"><span class="series-no">0{i+1}</span><div><h3>{E(topic)}</h3><p>{E(brief)}</p></div><span class="series-count">{n} / {len(eps)} 集<br><b>→</b></span></a>'
    cards = ''.join(card(ep) for ep in QUEUE if ep['id'] in ARTICLES)
    body = f'''<section class="hero wrap"><div class="hero-copy"><p class="eyebrow">听过的故事，值得看懂。</p><h1>把长故事，<br>读成一张<span>清晰的地图。</span></h1><p class="hero-dek">跟着人物、时间和转折，读懂商业与生活。<br>从一集播客开始，让知识慢慢连成线。</p><div class="hero-actions"><a class="button" href="#library">开始阅读 <span>↗</span></a><a class="text-link" href="#series">沿专题读下去 →</a></div><div class="hero-stats"><span><strong>{completed:02d}</strong> 已整理单集</span><span><strong>{available}</strong> 可用文稿</span><span><strong>10</strong> 每日制作目标</span></div></div>{hero_visual}</section><section id="series" class="wrap section"><div class="section-heading"><div><p class="eyebrow">FOLLOW THE THREAD</p><h2>沿着一个专题，读下去。</h2></div><a class="text-link" href="/topics/">查看全部专题 →</a></div><div class="series-list">{series}</div></section><section id="library" class="wrap section"><div class="section-heading"><div><p class="eyebrow">THE READING ROOM</p><h2>今天，想读哪个故事？</h2></div><a href="/progress/" class="text-link">查看制作计划 →</a></div><div class="library-tools"><div class="filters" role="group" aria-label="按播客筛选"><button class="active" data-filter="all" aria-pressed="true">全部</button><button data-filter="半拿铁" aria-pressed="false">半拿铁</button><button data-filter="知行小酒馆" aria-pressed="false">知行小酒馆</button></div><label class="search"><span>搜索</span><input id="search" type="search" placeholder="人物、公司或专题" aria-label="搜索已制作单集"></label></div><div class="episode-grid">{cards}</div><p class="empty" id="empty" hidden>还没有匹配的已制作图解，换个关键词试试。</p>{'<p class="notice">首批图解正在生成，完成后会出现在这里。</p>' if not cards else ''}</section><section class="reading-note wrap"><span>一集，两种读法。</span><p>网页帮你理清故事，漫画幻灯片帮你记住画面。<br>每集都附原节目入口，想听更多细节时，随时回去。</p><a href="/progress/">看看下一批做什么 →</a></section>'''
    return shell('把故事读成地图', body, home=True)

def timestamp_seconds(s):
    parts = list(map(int, s.split(':')))
    return sum(v * 60 ** i for i,v in enumerate(reversed(parts)))

def episode(ep, a):
    eid = ep['id']; pdf = (ROOT / 'assets/slides' / (eid + '.pdf')).exists()
    samples = sorted((ROOT / 'assets/illustrations' / eid).glob('*.webp'))
    chapter_links = ''.join(f'<a href="#chapter-{i}"><span>{i+1:02d}</span>{E(s["title"])}</a>' for i,s in enumerate(a['sections']))
    sections = ''
    for i,s in enumerate(a['sections']):
        paragraphs = ''.join(f'<p>{E(p)}</p>' for p in s['paragraphs'])
        figure = ''
        if i % 2 == 0 and len(samples) > 1:
            sample = samples[min(i // 2 + 1, len(samples)-1)]
            figure = f'<figure><img src="/assets/illustrations/{eid}/{sample.name}" alt="本集漫画幻灯片：{E(s["title"])}相关内容" loading="lazy" width="960" height="540"><figcaption>本集漫画幻灯片选页 · 完整故事见 PDF</figcaption></figure>'
        sections += f'<section class="chapter" id="chapter-{i}"><div class="chapter-kicker"><span>CHAPTER {i+1:02d}</span><a href="{E(ep["url"])}" target="_blank" rel="noopener noreferrer">原节目 {E(s["timestamp"])} ↗</a></div><h2>{E(s["title"])}</h2>{paragraphs}{figure}</section>'
    timeline = ''.join(f'<li><span>{E(t["date"])}</span><div><h3>{E(t["title"])}</h3><p>{E(t["detail"])}</p></div></li>' for t in a['timeline'])
    people = ''.join(f'<article><span class="person-initial">{E(p["name"][:1])}</span><h3>{E(p["name"])}</h3><small>{E(p["role"])}</small><p>{E(p["detail"])}</p></article>' for p in a['people'])
    connections = ''.join(f'<li><strong>{E(c["from"])}</strong><span>{E(c["label"])} <b>→</b></span><strong>{E(c["to"])}</strong></li>' for c in a['connections'])
    flow = ''.join(f'<li><span>{i+1:02d}</span><h3>{E(s["label"])}</h3><p>{E(s["detail"])}</p></li>' for i,s in enumerate(a['mechanism']['steps']))
    terms = ''.join(f'<div><dt>{E(g["term"])}</dt><dd>{E(g["meaning"])}</dd></div>' for g in a['glossary'])
    takeaways = ''.join(f'<li>{E(t)}</li>' for t in a['takeaways'])
    caveats = ''.join(f'<li>{E(c)}</li>' for c in a['caveats'])
    citations = ''.join(f'<li><a href="{E(c["url"])}" target="_blank" rel="noopener noreferrer">{E(c["title"])} ↗</a></li>' for c in a.get('editorial_sources', []))
    if citations: caveats += '<li>姓名核对参考：<ul>' + citations + '</ul></li>'
    siblings = [x for x in QUEUE if x['topic'] == ep['topic'] and x['id'] in ARTICLES]
    position = next(i for i,x in enumerate(siblings) if x['id'] == eid)
    next_ep = siblings[position + 1] if position + 1 < len(siblings) else None
    next_link = f'<a href="{article_url(next_ep["id"])}">接着读：{E(ARTICLES[next_ep["id"]]["headline"])} →</a>' if next_ep else f'<a href="{topic_url(ep["topic"])}">回到专题，看看后面的故事 →</a>'
    slides = f'<a class="button" href="/assets/slides/{eid}.pdf" target="_blank" rel="noopener">查看漫画幻灯片 ↗</a><a class="text-link" href="/assets/slides/{eid}.pdf" download>下载 PDF ↓</a>' if pdf else '<span class="notice">本集漫画幻灯片仍在生成，完成后会补上。</span>'
    body = f'''<div class="wrap article-intro"><a class="breadcrumb" href="{topic_url(ep['topic'])}">← {E(ep['topic'])}</a><p class="eyebrow">{E(ep['show'])} / 第 {ep['order']} 集 · {ep['date']}</p><h1>{E(a['headline'])}</h1><p class="article-dek">{E(a['dek'])}</p><div class="hero-actions">{slides}<a class="text-link" href="{E(ep['url'])}" target="_blank" rel="noopener noreferrer">听原节目 ↗</a></div></div><div class="wrap article-layout"><aside class="toc"><span class="eyebrow">这集怎么读</span>{chapter_links}<a href="#timeline">故事时间线</a><a href="#people">人物与关系</a><a href="#mechanism">理清因果</a><a href="#glossary">术语说人话</a></aside><div class="article-content"><section class="takeaways"><p class="eyebrow">先记住这几件事</p><ul>{takeaways}</ul></section>{sections}<section class="chapter" id="timeline"><p class="eyebrow">PUT IT IN ORDER</p><h2>把故事放回时间里。</h2><ol class="timeline">{timeline}</ol></section><section class="chapter" id="people"><p class="eyebrow">WHO SHAPED THE STORY</p><h2>谁，推动了这个故事？</h2><div class="people-grid">{people}</div><h3 class="subheading">把关系连起来</h3><ul class="connections">{connections}</ul></section><section class="chapter" id="mechanism"><p class="eyebrow">CONNECT THE DOTS</p><h2>{E(a['mechanism']['title'])}</h2><ol class="mechanism">{flow}</ol></section><section class="chapter" id="glossary"><p class="eyebrow">IN PLAIN LANGUAGE</p><h2>这些词，其实不难懂。</h2><dl class="glossary">{terms}</dl></section><section class="source-note"><h3>读到这里，也保留一点疑问。</h3><ul>{caveats}</ul><p>本文根据《{E(ep['show'])}》{E(ep['title'])}逐字稿整理，不是逐字复制。文稿和AI整理都可能出错；章节旁标出原节目时间，方便回听。图像为AI生成的漫画演绎。</p><a href="{E(ep['url'])}" target="_blank" rel="noopener noreferrer">查看原节目与作者 ↗</a></section><nav class="next-story" aria-label="继续阅读">{next_link}</nav></div></div>'''
    return shell(a['headline'], body, a['dek'])

def topic_page(topic):
    eps = [ep for ep in QUEUE if ep['topic'] == topic]; n = sum(ep['id'] in ARTICLES for ep in eps)
    rows = ''
    for ep in eps:
        a = ARTICLES.get(ep['id']); status = '已制作' if a else '待制作' if ep['available'] else '缺少逐字稿'
        title = E(a['headline'] if a else clean_title(ep['title']))
        name = f'<a href="{article_url(ep["id"])}">{title} ↗</a>' if a else title
        rows += f'<li class="topic-row"><span class="series-no">{ep["order"]:02d}</span><div><h2>{name}</h2><p>{E(ep["title"])} · {ep["date"]}</p></div><span class="status {"ready" if a else ""}">{status}</span></li>'
    return shell(topic, f'<section class="wrap topic-intro"><a class="breadcrumb" href="/#series">← 全部专题</a><p class="eyebrow">FOLLOW THE THREAD / {n} 集已整理</p><h1>{E(topic)}</h1><p class="article-dek">按故事顺序阅读。已制作的集数可以打开图文讲解，后续内容会逐步补齐。</p><ol class="topic-episodes">{rows}</ol></section>')

def all_topics():
    rows = ''
    for i, topic in enumerate(TOPICS):
        eps = [ep for ep in QUEUE if ep['topic'] == topic]
        n = sum(ep['id'] in ARTICLES for ep in eps)
        rows += f'<a class="series-item" href="{topic_url(topic)}"><span class="series-no">{i+1:02d}</span><div><h3>{E(topic)}</h3><p>{"按故事系列顺序制作与阅读" if topic != "单集精选" else "两档播客其他单集，按发布时间从新到旧"}</p></div><span class="series-count">{n} / {len(eps)} 集<br><b>→</b></span></a>'
    return shell('全部专题', f'<section class="wrap topic-intro"><a class="breadcrumb" href="/">← 首页</a><p class="eyebrow">FIND YOUR THREAD</p><h1>选一条线，把故事连起来。</h1><p class="article-dek">先制作完整专题，再从较新的单集往回读。未制作和缺失文稿的单集都保留在目录中。</p><div class="series-list">{rows}</div></section>')

def progress_page():
    n = len(ARTICLES); slides = len(list((ROOT / 'assets/slides').glob('*.pdf')))
    missing = sum(not ep['available'] for ep in QUEUE)
    rows = ''.join(f'<tr><td>{E(topic)}</td><td>{sum(ep["id"] in ARTICLES for ep in QUEUE if ep["topic"] == topic)} / {sum(ep["topic"] == topic for ep in QUEUE)}</td><td>{"专题顺序" if topic != "单集精选" else "发布时间从新到旧"}</td></tr>' for topic in TOPICS)
    next_eps = [ep for ep in QUEUE if ep['available'] and ep['id'] not in ARTICLES][:10]
    next_list = ''.join(f'<li>{E(ep["title"])}</li>' for ep in next_eps)
    return shell('制作进度', f'<section class="wrap progress-page"><a class="breadcrumb" href="/">← 首页</a><p class="eyebrow">A LIBRARY IN THE MAKING</p><h1>故事，正在一集集变清楚。</h1><p class="article-dek">每天北京时间 13:00 制作，目标 10 集。先读完整专题，再从较新的单集往回读。</p><div class="progress-stats"><div><strong>{n}</strong><span>图文已完成</span></div><div><strong>{slides}</strong><span>幻灯片已下载</span></div><div><strong>{missing}</strong><span>缺少逐字稿</span></div></div><h2>专题制作顺序</h2><div class="table-wrap"><table><thead><tr><th>专题</th><th>已整理 / 总集数</th><th>阅读顺序</th></tr></thead><tbody>{rows}</tbody></table></div><h2>接下来的故事</h2><ol class="up-next">{next_list}</ol><p class="notice">这里展示当前已发布产物。缺失文稿保留记录，不用节目简介冒充逐字稿；生成失败的任务会记录并重试。</p></section>')

def save(rel, content):
    p = DIST / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(content)

def main():
    if DIST.exists(): shutil.rmtree(DIST)
    DIST.mkdir()
    for name in ['style.css', 'app.js', 'favicon.svg']: shutil.copyfile(ROOT / name, DIST / name)
    if (ROOT / 'assets').exists(): shutil.copytree(ROOT / 'assets', DIST / 'assets')
    save('index.html', index()); save('progress/index.html', progress_page()); save('topics/index.html', all_topics())
    for topic in TOPICS: save(topic_url(topic).strip('/') + '/index.html', topic_page(topic))
    for ep in QUEUE:
        if ep['id'] in ARTICLES: save(article_url(ep['id']).strip('/') + '/index.html', episode(ep, ARTICLES[ep['id']]))
    save('404.html', shell('这一页还没画出来', '<section class="wrap topic-intro"><h1>这一页，还没画出来。</h1><p>可能是链接有误，或故事尚未制作。</p><a class="button" href="/">回到首页 →</a></section>'))
    urls = ['/', '/progress/', '/topics/'] + [topic_url(t) for t in TOPICS] + [article_url(eid) for eid in ARTICLES]
    save('sitemap.xml', '<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + ''.join(f'<url><loc>{CFG["domain"]}{u}</loc></url>' for u in urls) + '</urlset>')
    save('robots.txt', f'User-agent: *\nAllow: /\nSitemap: {CFG["domain"]}/sitemap.xml\n')
    print(f'Built {len(ARTICLES)} articles, {len(TOPICS)} topics → {DIST}')

if __name__ == '__main__': main()
