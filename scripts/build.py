#!/usr/bin/env python3
import collections, html, json, pathlib, re, shutil, math
try:
    from site_assets import prepare, write_asset
except ModuleNotFoundError:
    from scripts.site_assets import prepare, write_asset
ROOT = pathlib.Path(__file__).resolve().parents[1]
DIST = ROOT / 'dist'
CFG = json.loads((ROOT / 'config.json').read_text())
VERSION = json.loads((ROOT / 'package.json').read_text())['version']
QUEUE = json.loads((ROOT / 'state/queue.json').read_text()) if (ROOT / 'state/queue.json').exists() else []
ARTICLES = {p.stem: json.loads(p.read_text()) for p in (ROOT / 'content').glob('*.json')}
ASSET_PREFIX = '/'
INLINE_CSS = ''
COVERS = {}
CHAPTER_IMAGES = {}
SLIDE_DECKS = {}
SEARCH_URL = '/search-index.json'
CATALOG_URL = '/catalog.json'
PAGE_SIZE = 24
E = lambda v: html.escape(str(v), quote=True)
TOPICS = list(dict.fromkeys(ep['topic'] for ep in QUEUE))
SHOWS = {'半拿铁':'bannatie', '知行小酒馆':'zhixing'}
TOPIC_GROUPS = list(dict.fromkeys((ep['show'],ep['topic']) for ep in QUEUE))
PPT_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 21h8M12 17v4"/></svg>'
BENTO_ARROW = '<span class="bento-arrow" aria-hidden="true">→</span>'

def shell(title, body, description='把播客里的长故事，变成看得懂的图文。半拿铁与知行小酒馆的中文图解知识库。', home=False, current_eid=None, head_extra=''):
    style_tag = f'<style>{INLINE_CSS}</style>' if INLINE_CSS else '<link rel="stylesheet" href="/style.css">'
    result = f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{E(title)} · 播客图解</title><meta name="description" content="{E(description)}"><meta name="theme-color" content="#f5f0e6"><link rel="icon" href="/favicon.svg" type="image/svg+xml">{style_tag}{head_extra}<meta property="og:title" content="{E(title)} · 播客图解"><meta property="og:description" content="{E(description)}"><meta property="og:image" content="{CFG['domain']}/assets/share.svg"><script type="module" src="{ASSET_PREFIX}app.js"></script></head><body><a class="skip" href="#main">跳到正文</a><header class="topbar"><a class="brand" href="/" aria-label="播客图解首页"><span class="brand-icon">▰</span> 播客图解</a><nav aria-label="主导航"><button class="catalog-trigger" type="button" data-open-catalog aria-label="打开全站目录" title="目录 (M)"><span class="catalog-icon">☰</span> 目录</button><button class="command-trigger" type="button" data-open-search aria-haspopup="dialog">搜索 <kbd>⌘ K</kbd></button></nav></header><main id="main">{body}</main><button class="floating-catalog" type="button" data-open-catalog aria-label="打开全站目录" title="目录 (M)"><span>☰ 目录</span></button>{search_dialog()}{lightbox_dialog()}{slide_viewer_dialog()}{catalog_drawer(current_eid)}<footer><a class="brand" href="/">播客图解</a><p>故事来自半拿铁与知行小酒馆。图文由逐字稿整理，保留原节目入口；识别和整理可能有误，建议结合原节目阅读。</p><span>中文图文知识库 · v{VERSION}</span><a href="{CFG['repo']}" target="_blank" rel="noopener noreferrer">源码与说明 ↗</a></footer><script async src="https://cloud.umami.is/script.js" data-website-id="e01c9f78-4607-4e60-b01c-77c8190b12b4"></script></body></html>'''

    base = CFG.get('base_path', '')
    for attr in [
        'href="/', 'src="/', 'data-open-slides="/', 'data-prev-slides="/', 'data-next-slides="/',
        'data-slide-prefix="/', 'data-prev-slide-prefix="/', 'data-next-slide-prefix="/',
    ]:
        result = result.replace(attr, attr[:-1] + base + '/')
    return result

def build_catalog_data():
    base = CFG.get('base_path', '')
    groups = []
    for show, topic in TOPIC_GROUPS:
        eps = [e for e in QUEUE if e['show'] == show and e['topic'] == topic]
        ready_count = sum(e['id'] in ARTICLES for e in eps)
        items = []
        for e in eps:
            a = ARTICLES.get(e['id'])
            has_pdf = (ROOT / 'assets/slides' / (e['id'] + '.pdf')).exists()
            link = article_url(e['id']) if a else (topic_url(topic, show) + '#episode-' + e['id'])
            title = a['headline'] if a else clean_title(e['title'])
            order_text = f'{e["order"]:02d}' if e.get('order', 10000) < 10000 else ''
            row = {'id': e['id'], 'o': order_text, 'h': title, 'u': base + link}
            if has_pdf:
                row['p'] = 1
                deck = SLIDE_DECKS.get(e['id'])
                if deck:
                    row['sp'] = base + deck['prefix']
                    row['sc'] = deck['pages']
            items.append(row)
        groups.append({'s': show, 't': topic, 'u': base + topic_url(topic, show), 'r': ready_count, 'n': len(eps), 'eps': items})
    return {'groups': groups}

def catalog_drawer(current_eid=None):
    base = CFG.get('base_path', '')
    return (
        f'<dialog id="global-catalog" class="global-catalog" aria-label="全站故事目录" data-catalog-url="{base}{CATALOG_URL}" data-current-eid="{E(current_eid or "")}">'
        f'<div class="catalog-shell">'
        f'<header class="catalog-header">'
        f'<div class="catalog-title-row">'
        f'<h3>故事目录</h3>'
        f'<div class="catalog-links"><a href="/topics/" class="catalog-link">专题</a><a href="/progress/" class="catalog-link">制作进度</a></div>'
        f'<button type="button" class="catalog-close" data-close-catalog aria-label="关闭目录">✕</button>'
        f'</div>'
        f'<div class="catalog-tools">'
        f'<div class="catalog-tabs" role="group" aria-label="按播客筛选">'
        f'<button type="button" class="active" data-cat-filter="all">全部</button>'
        f'<button type="button" data-cat-filter="半拿铁">半拿铁</button>'
        f'<button type="button" data-cat-filter="知行小酒馆">知行小酒馆</button>'
        f'</div>'
        f'<input type="search" id="catalog-filter-input" placeholder="在目录中搜索..." aria-label="搜索目录">'
        f'</div>'
        f'</header>'
        f'<div class="catalog-body" id="catalog-body"><p class="catalog-status">正在载入目录…</p></div>'
        f'</div>'
        f'</dialog>'
    )

def topic_url(topic, show=None):
    if show is None: return '/topics/' + str(TOPICS.index(topic) + 1) + '/'
    return '/shows/' + SHOWS[show] + '/topics/' + str(TOPICS.index(topic) + 1) + '/'

def search_dialog():
    base = CFG.get('base_path', '')
    return (
        f'<dialog id="command-search" class="command-search" aria-label="搜索故事" data-search-index="{base}{SEARCH_URL}">'
        f'<div class="command-bar">'
        f'<svg class="command-search-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>'
        f'<input id="command-query" type="search" placeholder="搜索故事、人物或主题…" autocomplete="off" maxlength="120" role="combobox" aria-autocomplete="list" aria-expanded="false" aria-controls="command-results" aria-label="搜索故事">'
        f'<button type="button" class="command-close" data-close-search aria-label="关闭搜索" title="关闭 (Esc)">✕</button>'
        f'</div>'
        f'<div id="command-status" class="command-status sr-only" role="status" aria-live="polite"></div>'
        f'<button class="command-retry" type="button" hidden>重新加载</button>'
        f'<ul id="command-results" role="listbox" aria-label="搜索结果"></ul>'
        f'<button type="button" class="command-more" data-search-more hidden>加载更多结果</button>'
        f'</dialog>'
    )

def lightbox_dialog():
    return '''<dialog id="image-lightbox" class="image-lightbox" aria-modal="true" aria-label="查看大图"><div class="lightbox-shell"><button type="button" class="lightbox-close" data-close-lightbox aria-label="关闭大图">关闭 <kbd>Esc</kbd></button><div class="lightbox-stage"><img id="lightbox-img" src="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg'/%3E" alt=""><p id="lightbox-caption" class="lightbox-caption"></p></div></div></dialog>'''

def slide_viewer_dialog():
    return '''<dialog id="slide-viewer" class="slide-viewer" aria-modal="true" aria-label="幻灯片查看器"><div class="slide-viewer-shell"><header class="slide-viewer-top"><div class="slide-viewer-info"><h3 id="slide-title"></h3><span class="slide-counter"><b id="slide-page-num">1</b> / <span id="slide-page-count">-</span></span></div><div class="slide-viewer-tools"><button type="button" class="slide-btn" id="slide-fs-btn" aria-label="全屏模式">⛶ 全屏</button><a class="slide-btn" id="slide-download-btn" href="" download>↓ 下载</a><button type="button" class="slide-btn slide-btn-close" data-close-slides aria-label="关闭幻灯片">✕</button></div></header><div class="slide-viewer-body" id="slide-body"><button type="button" class="slide-arrow slide-prev" id="slide-prev" aria-label="上一页">‹</button><div class="slide-canvas-box" id="slide-canvas-box"><img id="slide-img" class="slide-img" alt="幻灯片内容" hidden><canvas id="slide-canvas"></canvas><div class="slide-loading" id="slide-loading"><span>正在载入幻灯片…</span></div><div class="slide-end-card" id="slide-end-card" hidden><div class="slide-end-inner"><span class="slide-end-kicker">本集幻灯片已看完</span><h4 id="slide-end-current-title"></h4><div class="slide-end-actions"><button type="button" class="slide-end-btn next" id="slide-jump-next" hidden><span class="slide-end-btn-dir">下一篇幻灯片 →</span><strong id="slide-jump-next-title"></strong></button><button type="button" class="slide-end-btn prev" id="slide-jump-prev" hidden><span class="slide-end-btn-dir">← 上一篇幻灯片</span><strong id="slide-jump-prev-title"></strong></button><button type="button" class="slide-end-btn replay" id="slide-replay-btn"><span>↺ 从头再看</span></button></div></div></div></div><button type="button" class="slide-arrow slide-next" id="slide-next" aria-label="下一页">›</button></div></div></dialog>'''

def article_url(eid): return '/episodes/' + eid + '/'
def clean_title(t): return __import__('re').sub(r'^No\.\d+\s*[^\u4e00-\u9fffA-Za-z「《]*', '', t).split(' | ')[0]
def _render_cover_img(ep, alt, priority=False, sizes=None, eager=False, responsive=True):
    """Render cover <img> from prebuilt thumbnails or raw illustration."""
    path = ROOT / 'assets/illustrations' / ep['id'] / '0.webp'
    image = COVERS.get(ep['id'])
    load_mode = 'eager' if (priority or eager) else 'lazy'
    if image:
        variants = image['variants']
        if not responsive:
            load_attr = '' if load_mode == 'eager' else f' loading="{load_mode}"'
            return f'<img src="{variants[0]["url"]}" alt="{E(alt)}"{load_attr} decoding="async" width="{image["width"]}" height="{image["height"]}">'
        srcset = ', '.join(CFG.get('base_path', '') + v['url'] + ' ' + str(v['width']) + 'w' for v in variants)
        target_sizes = sizes or ('(max-width: 650px) calc(100vw - 68px), (max-width: 1000px) 45vw, 520px' if priority else '(max-width: 650px) calc(100vw - 40px), (max-width: 1000px) 44vw, 360px')
        fp_attr = ' fetchpriority="high"' if priority else ''
        return f'<img src="{variants[1 if len(variants)>1 else 0]["url"]}" srcset="{srcset}" sizes="{target_sizes}" alt="{E(alt)}" loading="{load_mode}"{fp_attr} decoding="async" width="{image["width"]}" height="{image["height"]}">'
    if path.exists():
        return f'<img src="/assets/illustrations/{ep["id"]}/0.webp" alt="{E(alt)}" loading="{load_mode}" width="960" height="540">'
    return ''

def cover(ep, priority=False):
    rendered = _render_cover_img(ep, clean_title(ep['title']), priority=priority)
    if rendered:
        return rendered
    return '<div class="cover-pending"><span>先读文字讲解</span><small>漫画幻灯片稍后补充</small></div>'

def card(ep):
    a = ARTICLES.get(ep['id']); ready = bool(a)
    link = article_url(ep['id']) if ready else topic_url(ep['topic'],ep['show'])
    headline = a['headline'] if a else clean_title(ep['title'])
    dek = a['dek'] if a else '这一集正在制作队列中，完成后会在这里补上图文讲解与中文漫画幻灯片。'
    pdf = (ROOT / 'assets/slides' / (ep['id'] + '.pdf')).exists()
    search_text = ep['title']+' '+ep['topic']+' '+ep['show']
    if a:
        search_text += ' '+a['headline']+' '+a['dek']+' '+' '.join(p['name']+' '+p['role'] for p in a['people'])+' '+' '.join(s['title'] for s in a['sections'])+' '+' '.join(g['term'] for g in a['glossary'])
    badge = '<span class="card-tag ppt">PPT</span>' if pdf else ''
    return f'''<article class="episode-card" data-search="{E(search_text)}" data-show="{E(ep['show'])}"><a href="{link}" class="card-cover">{cover(ep)}</a><div class="card-copy"><div class="card-meta"><span>{E(ep['topic'])}</span> · <time>{ep['date']}</time></div><h3><a href="{link}">{E(headline)}</a></h3><div class="card-bottom">{badge}</div></div></article>'''

def index(page=1):
    completed = len(ARTICLES); available = sum(ep['available'] for ep in QUEUE)
    hero_id = '64804a7d6752b5f9de296733'
    hero_ep = next((ep for ep in QUEUE if ep['id'] == hero_id), None) or next((ep for ep in QUEUE if ep['id'] in ARTICLES), QUEUE[0] if QUEUE else None)
    head_extra = ''
    if hero_ep:
        hero_art = ARTICLES.get(hero_ep['id'])
        hero_link = article_url(hero_ep['id']) if hero_art else topic_url(hero_ep['topic'], hero_ep['show'])
        hero_headline = hero_art["headline"] if hero_art else clean_title(hero_ep['title'])
        hero_order = f'{hero_ep["order"]:02d}' if hero_ep.get('order', 0) < 10000 else '01'
        hero_visual = f'<a class="hero-story" href="{hero_link}">{cover(hero_ep, priority=True)}<div class="hero-caption"><span>{E(hero_ep["topic"])} · {hero_order}</span><strong>{E(hero_headline)}</strong></div></a>'
        hero_image = COVERS.get(hero_ep['id'])
        if hero_image:
            variants = hero_image['variants']
            base = CFG.get('base_path', '')
            srcset = ', '.join(base + v['url'] + ' ' + str(v['width']) + 'w' for v in variants)
            sizes = '(max-width: 650px) calc(100vw - 68px), (max-width: 1000px) 45vw, 520px'
            fallback = variants[1 if len(variants) > 1 else 0]['url']
            head_extra = f'<link rel="preload" as="image" href="{fallback}" imagesrcset="{srcset}" imagesizes="{sizes}" fetchpriority="high">'
    else: hero_visual = ''
    series = ''.join(_bento_show_group(show, group_tag='h3', card_tag='h4')[0] for show in SHOWS)
    ready = sorted([ep for ep in QUEUE if ep['id'] in ARTICLES], key=lambda ep: (ep.get('date', ''), ep.get('order', 0), ep['id']), reverse=True)
    offset = (page - 1) * PAGE_SIZE
    cards = ''.join(card(ep) for ep in ready[offset:offset+PAGE_SIZE])
    next_url = '/library/' + str(page+1) + '/#library' if offset+PAGE_SIZE < len(ready) else '#library'
    previous_url = '/#library' if page == 2 else '/library/' + str(page-1) + '/#library'
    previous = f'<a href="{previous_url}">← 上一页</a>' if page > 1 else ''
    pager = f'<div class="library-pagination">{previous}<p id="library-status" role="status">显示 {offset+1}—{min(offset+PAGE_SIZE,len(ready))} 集，共 {len(ready)} 集</p><a class="button" id="library-more" href="{next_url}" {"hidden" if offset+PAGE_SIZE>=len(ready) else ""}>加载更多 ↓</a></div>'
    body = f'''<section class="hero wrap"><div class="hero-copy"><h1>把长故事，<br>读成一张<span>清晰的地图。</span></h1><p class="hero-dek">跟着人物、时间和转折，读懂商业与生活。<br>从一集播客开始，让知识慢慢连成线。</p><div class="hero-actions"><a class="button" href="#library">开始阅读 <span>↗</span></a><a class="text-link" href="#series">沿专题读下去 →</a></div><div class="hero-stats"><span><strong>{completed:02d}</strong> 已整理单集</span><span><strong>{available}</strong> 可用文稿</span><span><strong>{len(TOPIC_GROUPS)}</strong> 深度专题</span></div></div>{hero_visual}</section><section id="series" class="wrap section"><div class="section-heading"><h2>沿着一个专题，读下去。</h2><a class="text-link" href="/topics/">查看全部专题 →</a></div>{series}</section><section id="library" class="wrap section"><div class="section-heading"><h2>今天，想读哪个故事？</h2><a href="/progress/" class="text-link">查看制作计划 →</a></div><div class="library-tools"><div class="filters" role="group" aria-label="按播客筛选"><button class="active" data-filter="all" aria-pressed="true">全部</button><button data-filter="半拿铁" aria-pressed="false">半拿铁</button><button data-filter="知行小酒馆" aria-pressed="false">知行小酒馆</button></div><label class="search" for="search"><svg class="search-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg><input id="search" type="search" placeholder="搜索故事、人物或主题…" aria-label="搜索已制作单集"></label></div><div class="episode-grid" data-offset="{offset}">{cards}</div>{pager}<p class="empty" id="empty" hidden>还没有匹配的已制作图解，换个关键词试试。</p>{'<p class="notice">首批图解正在生成，完成后会出现在这里。</p>' if not cards else ''}</section>'''
    return shell('把故事读成地图', body, home=True, head_extra=head_extra)

def timestamp_seconds(s):
    parts = list(map(int, s.split(':')))
    return sum(v * 60 ** i for i,v in enumerate(reversed(parts)))

def reviewed_chapter_images(eid, chapter_count):
    directory = ROOT / 'assets/illustrations' / eid
    manifest = directory / 'pages.json'
    mapping = json.loads(manifest.read_text()).get('chapter_images', {}) if manifest.exists() else {}
    images = {}
    for chapter, filename in mapping.items():
        if not re.fullmatch(r'\d+', chapter) or int(chapter) >= chapter_count or not re.fullmatch(r'\d+\.webp', filename):
            raise ValueError('Invalid reviewed chapter image: ' + eid)
        image = directory / filename
        if not image.is_file(): raise ValueError('Missing reviewed chapter image: ' + eid)
        images[int(chapter)] = image
    return images

def chapter_image_path(chapter_idx, samples, reviewed):
    sample = reviewed.get(chapter_idx)
    if not reviewed and chapter_idx % 2 == 0 and len(samples) > 1:
        sample = samples[min(chapter_idx // 2 + 1, len(samples) - 1)]
    return sample

def episode_chapter_sources():
    paths = []
    seen = set()
    for eid, a in ARTICLES.items():
        samples = sorted((ROOT / 'assets/illustrations' / eid).glob('*.webp'))
        reviewed = reviewed_chapter_images(eid, len(a['sections']))
        for i in range(len(a['sections'])):
            sample = chapter_image_path(i, samples, reviewed)
            if sample:
                rel = f'{eid}/{sample.name}'
                if rel not in seen:
                    seen.add(rel)
                    paths.append(rel)
    return sorted(paths)

def episode(ep, a):
    eid = ep['id']; pdf = (ROOT / 'assets/slides' / (eid + '.pdf')).exists()
    samples = sorted((ROOT / 'assets/illustrations' / eid).glob('*.webp'))
    reviewed = reviewed_chapter_images(eid, len(a['sections']))
    chapter_links = ''.join(f'<a href="#chapter-{i}"><span>{i+1:02d}</span>{E(s["title"])}</a>' for i,s in enumerate(a['sections']))
    sections = ''
    first_img_head = None
    sizes = '(max-width: 650px) calc(100vw - 40px), (max-width: 1100px) calc(100vw - 290px), 738px'
    for i,s in enumerate(a['sections']):
        paragraphs = ''.join(f'<p>{E(p)}</p>' for p in s['paragraphs'])
        time_label = '文稿时间异常 · 听原节目' if s.get('timestamp_quality') == 'source_repeated' else '原节目 ' + s['timestamp']
        figure = ''
        sample = chapter_image_path(i, samples, reviewed)
        if sample:
            chap_key = f'{eid}/{sample.name}'
            chap_info = CHAPTER_IMAGES.get(chap_key)
            is_first = first_img_head is None
            loading_attr = 'eager' if is_first else 'lazy'
            priority_attr = 'high' if is_first else 'auto'
            if chap_info:
                variants = chap_info['variants']
                base = CFG.get('base_path', '')
                srcset = ', '.join(base + v['url'] + f' {v["width"]}w' for v in variants)
                fallback_url = variants[-1]['url']
                figure = f'<figure><img src="{fallback_url}" srcset="{srcset}" sizes="{sizes}" alt="本集漫画幻灯片：{E(s["title"])}相关内容" loading="{loading_attr}" fetchpriority="{priority_attr}" decoding="async" width="{chap_info["width"]}" height="{chap_info["height"]}"></figure>'
                if is_first:
                    first_img_head = f'<link rel="preload" as="image" href="{fallback_url}" imagesrcset="{srcset}" imagesizes="{sizes}" fetchpriority="high">'
            else:
                src = f'/assets/illustrations/{eid}/{sample.name}'
                figure = f'<figure><img src="{src}" alt="本集漫画幻灯片：{E(s["title"])}相关内容" loading="{loading_attr}" fetchpriority="{priority_attr}" decoding="async" width="960" height="540"></figure>'
                if is_first:
                    first_img_head = f'<link rel="preload" as="image" href="{src}" fetchpriority="high">'
        sections += f'<section class="chapter" id="chapter-{i}"><div class="chapter-kicker"><a href="{E(ep["url"])}" target="_blank" rel="noopener noreferrer">{E(time_label)} ↗</a></div><h2>{E(s["title"])}</h2>{paragraphs}{figure}</section>'
    timeline = ''.join(f'<li><span>{E(t["date"])}</span><div><h3>{E(t["title"])}</h3><p>{E(t["detail"])}</p></div></li>' for t in a['timeline'])
    people = ''.join(f'<article><span class="person-initial">{E(p["name"][:1])}</span><h3>{E(p["name"])}</h3><small>{E(p["role"])}</small><p>{E(p["detail"])}</p></article>' for p in a['people'])
    connections = ''.join(f'<li><strong>{E(c["from"])}</strong><span>{E(c["label"])} <b>→</b></span><strong>{E(c["to"])}</strong></li>' for c in a['connections'])
    flow = ''.join(f'<li><span>{i+1:02d}</span><h3>{E(s["label"])}</h3><p>{E(s["detail"])}</p></li>' for i,s in enumerate(a['mechanism']['steps']))
    terms = ''.join(f'<div><dt>{E(g["term"])}</dt><dd>{E(g["meaning"])}</dd></div>' for g in a['glossary'])
    takeaways = ''.join(f'<li>{E(t)}</li>' for t in a['takeaways'])
    caveats = ''.join(f'<li>{E(c)}</li>' for c in a['caveats'])
    citations = ''.join(f'<li><a href="{E(c["url"])}" target="_blank" rel="noopener noreferrer">{E(c["title"])} ↗</a></li>' for c in a.get('editorial_sources', []))
    if citations: caveats += '<li>校对参考：<ul>' + citations + '</ul></li>'
    siblings = [x for x in QUEUE if x['topic'] == ep['topic'] and x['show'] == ep['show'] and x['id'] in ARTICLES]
    position = next(i for i,x in enumerate(siblings) if x['id'] == eid)
    prev_ep = siblings[position - 1] if position > 0 else None
    next_ep = siblings[position + 1] if position + 1 < len(siblings) else None

    # Slide navigation context for viewer
    all_slide_eps = [x for x in QUEUE if (ROOT / 'assets/slides' / (x['id'] + '.pdf')).exists()]
    topic_slide_eps = [x for x in siblings if (ROOT / 'assets/slides' / (x['id'] + '.pdf')).exists()]
    topic_slide_pos = next((i for i, x in enumerate(topic_slide_eps) if x['id'] == eid), -1)
    if topic_slide_pos > 0:
        prev_slide_ep = topic_slide_eps[topic_slide_pos - 1]
    else:
        glob_slide_pos = next((i for i, x in enumerate(all_slide_eps) if x['id'] == eid), -1)
        prev_slide_ep = all_slide_eps[glob_slide_pos - 1] if glob_slide_pos > 0 else None

    if topic_slide_pos >= 0 and topic_slide_pos + 1 < len(topic_slide_eps):
        next_slide_ep = topic_slide_eps[topic_slide_pos + 1]
    else:
        glob_slide_pos = next((i for i, x in enumerate(all_slide_eps) if x['id'] == eid), -1)
        next_slide_ep = all_slide_eps[glob_slide_pos + 1] if glob_slide_pos >= 0 and glob_slide_pos + 1 < len(all_slide_eps) else None

    def ep_headline(target_ep):
        if not target_ep: return ''
        if target_ep['id'] in ARTICLES: return ARTICLES[target_ep['id']]['headline']
        return clean_title(target_ep['title'])

    def slide_ref(target_ep):
        if not target_ep: return '', '', ''
        t_id = target_ep['id']
        t_deck = SLIDE_DECKS.get(t_id)
        return (
            f'/assets/slides/{t_id}.pdf',
            t_deck['prefix'] if t_deck else '',
            str(t_deck['pages']) if t_deck else ''
        )

    if pdf:
        pdf_url, slide_prefix, slide_count = slide_ref(ep)
        prev_slide_url, prev_slide_prefix, prev_slide_count = slide_ref(prev_slide_ep)
        prev_slide_title = ep_headline(prev_slide_ep)
        next_slide_url, next_slide_prefix, next_slide_count = slide_ref(next_slide_ep)
        next_slide_title = ep_headline(next_slide_ep)
        slide_attrs = (
            f'data-open-slides="{pdf_url}" '
            f'data-slide-id="{eid}" '
            f'data-slide-prefix="{slide_prefix}" '
            f'data-slide-count="{slide_count}" '
            f'data-title="{E(a["headline"])}" '
            f'data-prev-slides="{prev_slide_url}" '
            f'data-prev-slide-id="{prev_slide_ep["id"] if prev_slide_ep else ""}" '
            f'data-prev-slide-prefix="{prev_slide_prefix}" '
            f'data-prev-slide-count="{prev_slide_count}" '
            f'data-prev-title="{E(prev_slide_title)}" '
            f'data-next-slides="{next_slide_url}" '
            f'data-next-slide-id="{next_slide_ep["id"] if next_slide_ep else ""}" '
            f'data-next-slide-prefix="{next_slide_prefix}" '
            f'data-next-slide-count="{next_slide_count}" '
            f'data-next-title="{E(next_slide_title)}"'
        )
        slides = f'<button type="button" class="button button-slides" {slide_attrs}>{PPT_ICON}<span>看 PPT</span></button>'
        toc_ppt = f'<button type="button" class="toc-ppt-btn" {slide_attrs}>{PPT_ICON}<span>看 PPT</span></button>'
    else:
        slides = '<span class="notice">文字讲解已整理，可以先读。漫画幻灯片会逐步补上。</span>'
        toc_ppt = ''

    if prev_ep:
        prev_card = f'<a class="pagination-card prev" href="{article_url(prev_ep["id"])}"><span class="pagination-direction">← 上一篇</span><strong class="pagination-title">{E(ARTICLES[prev_ep["id"]]["headline"])}</strong><span class="pagination-meta">{E(prev_ep["show"])} · 第 {prev_ep["order"]} 集</span></a>'
    else:
        prev_card = f'<a class="pagination-card back-topic" href="{topic_url(ep["topic"], ep["show"])}"><span class="pagination-direction">专题全集</span><strong class="pagination-title">《{E(ep["topic"])}》</strong><span class="pagination-meta">已是本专题第一集</span></a>'

    if next_ep:
        next_card = f'<a class="pagination-card next" href="{article_url(next_ep["id"])}"><span class="pagination-direction">下一篇 →</span><strong class="pagination-title">{E(ARTICLES[next_ep["id"]]["headline"])}</strong><span class="pagination-meta">{E(next_ep["show"])} · 第 {next_ep["order"]} 集</span></a>'
    else:
        next_card = f'<a class="pagination-card back-topic" href="{topic_url(ep["topic"], ep["show"])}"><span class="pagination-direction">专题全集</span><strong class="pagination-title">《{E(ep["topic"])}》</strong><span class="pagination-meta">已是本专题最后一集</span></a>'

    pagination = f'<nav class="article-pagination" aria-label="相邻故事导航">{prev_card}{next_card}</nav>'

    order_str = f'第 {ep["order"]} 集' if ep.get('order', 0) < 10000 else ''
    meta_parts = [
        f'<a class="meta-breadcrumb" href="{topic_url(ep["topic"], ep["show"])}">← {E(ep["topic"])}</a>',
        f'<span>{E(ep["show"])}</span>',
        f'<span>{order_str}</span>' if order_str else None,
        f'<span>{ep["date"]}</span>'
    ]
    meta_html = ' <span class="meta-sep">·</span> '.join(p for p in meta_parts if p)

    body = f'''<div class="wrap article-intro"><div class="article-meta">{meta_html}</div><h1>{E(a['headline'])}</h1><p class="article-dek">{E(a['dek'])}</p><div class="hero-actions">{slides}</div></div><div class="wrap article-layout"><aside class="toc">{toc_ppt}{chapter_links}<a href="#timeline">故事时间线</a><a href="#people">人物与关系</a><a href="#mechanism">理清因果</a><a href="#glossary">术语说人话</a></aside><div class="article-content"><section class="takeaways"><ul>{takeaways}</ul></section>{sections}<section class="chapter" id="timeline"><h2>把故事放回时间里。</h2><ol class="timeline">{timeline}</ol></section><section class="chapter" id="people"><h2>谁，推动了这个故事？</h2><div class="people-grid">{people}</div><ul class="connections">{connections}</ul></section><section class="chapter" id="mechanism"><h2>{E(a['mechanism']['title'])}</h2><ol class="mechanism">{flow}</ol></section><section class="chapter" id="glossary"><h2>这些词，其实不难懂。</h2><dl class="glossary">{terms}</dl></section><section class="source-note"><h3>读到这里，也保留一点疑问。</h3><ul>{caveats}</ul><p>本文根据《{E(ep['show'])}》{E(ep['title'])}逐字稿整理，不是逐字复制。文稿和AI整理都可能出错；章节旁标出原节目时间，方便回听。图像为AI生成的漫画演绎。</p><a href="{E(ep['url'])}" target="_blank" rel="noopener noreferrer">查看原节目与作者 ↗</a></section>{pagination}</div></div>'''
    return shell(a['headline'], body, a['dek'], current_eid=eid, head_extra=first_img_head or '')

def topic_page(topic, show=None):
    if show is None:
        owners=[owner for owner,name in TOPIC_GROUPS if name==topic]
        if len(owners)==1:return topic_page(topic,owners[0])
        choices=''.join(f'<a class="button" href="{topic_url(topic,owner)}">{E(owner)} · {E(topic)} →</a>' for owner in owners)
        return shell(topic,f'<section class="wrap topic-intro"><h1>{E(topic)}</h1><p class="article-dek">两档播客的专题分别整理，选一档继续阅读。</p><div class="hero-actions">{choices}</div></section>')
    eps=[ep for ep in QUEUE if ep['topic']==topic and ep['show']==show]
    n=sum(ep['id'] in ARTICLES for ep in eps);rows=''
    for position,ep in enumerate(eps,1):
        a=ARTICLES.get(ep['id']);pdf=(ROOT/'assets/slides'/(ep['id']+'.pdf')).exists()
        status=('文字 + 幻灯片' if pdf else '文字已整理 · 幻灯片待补') if a else ('文字待整理' if ep['available'] else '文稿缺失')
        title=E(a['headline'] if a else clean_title(ep['title']))
        name=f'<a href="{article_url(ep["id"])}">{title} ↗</a>' if a else title
        order_no = ep["order"] if ep.get("order", 10000) < 10000 else position
        rows+=f'<li class="topic-row" id="episode-{ep["id"]}" data-show="{E(show)}"><span class="series-no">{order_no:02d}</span><div><h2>{name}</h2><p>{E(ep["title"])} · {ep["date"]}</p></div><span class="status {"ready" if a else ""}">{status}</span></li>'
    return shell(show+' · '+topic,f'<section class="wrap topic-intro"><a class="breadcrumb" href="/topics/#{SHOWS[show]}">← {E(show)}的专题</a><div class="topic-meta"><span>{E(show)} / {n} 集已整理</span></div><h1>{E(topic)}</h1><p class="article-dek">先读文字讲解，漫画幻灯片逐步补齐。这里收录《{E(show)}》共 {len(eps)} 集（已整理 {n} 集）。</p><ol class="topic-episodes">{rows}</ol></section>')

def _topic_summary(show, topic):
    """Collect verified counts, date span, digest snippet, and cover episode for a topic."""
    eps = [ep for ep in QUEUE if ep['show'] == show and ep['topic'] == topic]
    ready_eps = [ep for ep in eps if ep['id'] in ARTICLES]
    ppt_count = sum(1 for ep in eps if (ROOT / 'assets/slides' / (ep['id'] + '.pdf')).exists())
    cover_ep = next(
        (ep for ep in ready_eps + eps if ep['id'] in COVERS or (ROOT / 'assets/illustrations' / ep['id'] / '0.webp').exists()),
        None,
    )
    dates = sorted(ep['date'] for ep in eps if ep.get('date'))
    year_span = (
        dates[0][:4] if dates and dates[0][:4] == dates[-1][:4]
        else f'{dates[0][:4]}–{dates[-1][:4]}'
    ) if dates else ''
    short_names = []
    for ep in ready_eps[:3]:
        headline = ARTICLES[ep['id']]['headline']
        seg = re.split(r'[：:，,？?]', headline)[0].strip()
        if seg and seg not in short_names:
            short_names.append(seg)
    digest = ' · '.join(short_names[:3]) or '图文梳理进行中'
    total = len(eps)
    pct = round((len(ready_eps) / total) * 100) if total else 0
    return {
        'show': show,
        'topic': topic,
        'url': topic_url(topic, show),
        'total': total,
        'text_count': len(ready_eps),
        'ppt_count': ppt_count,
        'year_span': year_span,
        'digest': digest,
        'cover_ep': cover_ep,
        'pct': pct,
        'is_archive': topic == '单集精选',
    }


def _topic_thumb(ep, topic, hero=False):
    if not ep:
        return '<div class="bento-cover-empty">图文筹备中</div>' if hero else ''
    return _render_cover_img(ep, '', eager=True, responsive=False)


def _bento_hero_card(d, extra_cls='', card_tag='h3'):
    cls = f'bento-hero-card {extra_cls}'.strip()
    return (
        f'<a class="{cls}" href="{d["url"]}">'
        f'{_topic_thumb(d["cover_ep"], d["topic"], hero=True)}'
        f'<div class="bento-card-content">'
        f'<div class="bento-title-row"><{card_tag}>{E(d["topic"])}</{card_tag}><span class="bento-count num"><b>{d["text_count"]}</b>/{d["total"]} 篇</span></div>'
        f'<div class="bento-digest">{E(d["digest"])}</div>'
        f'<div class="b-bar" style="--p:{d["pct"]}%"></div>'
        f'<div class="bento-sub num"><span>{d["ppt_count"]} 套幻灯片 · {E(d["year_span"])}</span>{BENTO_ARROW}</div>'
        f'</div></a>'
    )


def _bento_mid_card(d, card_tag='h3'):
    return (
        f'<a class="bento-mid-card" href="{d["url"]}">'
        f'<div class="bento-mid-top">{_topic_thumb(d["cover_ep"], d["topic"])}'
        f'<div><{card_tag}>{E(d["topic"])}</{card_tag}><span class="num">{d["text_count"]}/{d["total"]} 篇 · {d["ppt_count"]} PPT</span></div></div>'
        f'<div class="bento-digest">{E(d["digest"])}</div>'
        f'<div class="b-bar" style="--p:{d["pct"]}%"></div>'
        f'</a>'
    )


def _bento_short_chip(d):
    return (
        f'<a class="bento-chip" href="{d["url"]}">'
        f'<div><strong>{E(d["topic"])}</strong>'
        f'<small class="num">{d["text_count"]}/{d["total"]} 篇 · {d["ppt_count"]} PPT · {E(d["year_span"])}</small></div>'
        f'{BENTO_ARROW}</a>'
    )


def _bento_archive_card(d, card_tag='h3'):
    return (
        f'<a class="bento-archive-card" href="{d["url"]}">'
        f'<div class="bento-archive-copy">'
        f'<{card_tag}>{E(d["topic"])} · 散篇收录</{card_tag}>'
        f'<div class="bento-digest">{E(d["digest"])} 等 {d["total"]} 篇独立故事</div>'
        f'</div>'
        f'<div class="bento-archive-meta num">'
        f'<span><b>{d["text_count"]}</b>/{d["total"]} 篇 · {d["ppt_count"]} PPT</span>'
        f'{BENTO_ARROW}'
        f'</div></a>'
    )


def _bento_show_group(show, group_tag='h2', card_tag='h3'):
    """Render one podcast's hierarchical Bento topic section and return (html, summaries)."""
    topics = [topic for owner, topic in TOPIC_GROUPS if owner == show]
    summaries = [_topic_summary(show, topic) for topic in topics]
    archive_items = [d for d in summaries if d['is_archive']]
    series_items = [d for d in summaries if not d['is_archive']]
    archive_cards = ''.join(_bento_archive_card(d, card_tag=card_tag) for d in archive_items)

    if len(series_items) <= 2:
        grid_inner = (
            ''.join(_bento_hero_card(d, card_tag=card_tag) for d in series_items)
            + archive_cards
        )
    else:
        hero_items = [d for d in series_items if d['total'] >= 20]
        mid_items = [d for d in series_items if d not in hero_items and d['total'] >= 5]
        short_items = [d for d in series_items if d not in hero_items and d['total'] < 5]
        hero_cls = 'bento-hero-full' if len(hero_items) == 1 else ''
        grid_inner = (
            ''.join(_bento_hero_card(d, extra_cls=hero_cls, card_tag=card_tag) for d in hero_items)
            + ''.join(_bento_mid_card(d, card_tag=card_tag) for d in mid_items)
            + (f'<div class="bento-chip-row">{"".join(_bento_short_chip(d) for d in short_items)}</div>' if short_items else '')
            + archive_cards
        )
    total_show_eps = sum(d['total'] for d in summaries)
    section_html = (
        f'<section class="bento-group" id="{SHOWS[show]}" aria-labelledby="show-{SHOWS[show]}">'
        f'<div class="bento-group-title"><{group_tag} id="show-{SHOWS[show]}">{E(show)}</{group_tag}>'
        f'<span class="num">{len(summaries)} 个专题 · {total_show_eps} 集</span></div>'
        f'<div class="bento-grid">{grid_inner}</div></section>'
    )
    return section_html, summaries


def all_topics():
    """Render /topics/ using the hierarchical Bento overview grouped by podcast."""
    groups = [_bento_show_group(show, group_tag='h2', card_tag='h3') for show in SHOWS]
    sections = [section for section, _ in groups]
    all_summaries = [d for _, summaries in groups for d in summaries]

    total_topics = len(all_summaries)
    total_ready = sum(d['text_count'] for d in all_summaries)
    total_slides = sum(d['ppt_count'] for d in all_summaries)
    body = (
        f'<section class="wrap topics-bento">'
        f'<div class="topics-bento-head">'
        f'<div><a class="breadcrumb" href="/">← 首页</a><h1>播客专题地图</h1></div>'
        f'<div class="bento-summary num"><b>{total_topics}</b> 个专题 · <b>{total_ready}</b> / {len(QUEUE)} 篇图文 · <b>{total_slides}</b> 套幻灯片</div>'
        f'</div>{"".join(sections)}</section>'
    )
    return shell('全部专题', body)

def search_index(full=True):
    entries=[]
    for ep in QUEUE:
        a=ARTICLES.get(ep['id']);pdf=(ROOT/'assets/slides'/(ep['id']+'.pdf')).exists()
        fields=[]
        if a:
            fields=[a['dek'],*a['takeaways'],*[t for sec in a['sections'] for t in [sec['title'],*sec['paragraphs']]],*[p['name']+' '+p['role']+' '+p['detail'] for p in a['people']],*[g['term']+' '+g['meaning'] for g in a['glossary']],*[t['date']+' '+t['title']+' '+t['detail'] for t in a['timeline']]]
        href=article_url(ep['id']) if a else topic_url(ep['topic'],ep['show'])+'#episode-'+ep['id']
        entries.append({'id':ep['id'],'title':a['headline'] if a else clean_title(ep['title']),'original_title':ep['title'],'show':ep['show'],'topic':ep['topic'],'date':ep['date'],'ready':bool(a),'slides':bool(pdf),'available':ep['available'],'order':len(entries),'url':CFG.get('base_path','')+href,'text':' '.join(fields) if full else (' '.join([p['name']+' '+p['role'] for p in a['people']] + [sec['title'] for sec in a['sections']] + [g['term'] for g in a['glossary']]) if a else ''), 'summary':a['dek'] if a else '', 'image':COVERS.get(ep['id'])})
    return {'version':VERSION,'entries':entries}

def progress_page():
    n = len(ARTICLES); slides = len(list((ROOT / 'assets/slides').glob('*.pdf')))
    missing = sum(not ep['available'] for ep in QUEUE)
    rows = ''.join(f'<tr><td>{E(show)} · {E(topic)}</td><td>{sum(ep["id"] in ARTICLES for ep in QUEUE if ep["topic"] == topic and ep["show"] == show)} / {sum(ep["topic"] == topic and ep["show"] == show for ep in QUEUE)}</td><td>{"专题顺序" if topic != "单集精选" else "发布时间从新到旧"}</td></tr>' for show,topic in TOPIC_GROUPS)
    pending=[ep for ep in QUEUE if ep['available'] and ep['id'] not in ARTICLES]
    b_ids=CFG.get('account_b_series_ids',[])
    a_queue=[ep for ep in pending if ep['id'] not in b_ids]
    b_queue=sorted([ep for ep in pending if ep['id'] in b_ids],key=lambda ep:b_ids.index(ep['id']))
    next_eps=[]
    while len(next_eps)<CFG.get('cycle_article_limit',5) and (a_queue or b_queue):
        for queue in [a_queue,b_queue]:
            if queue and len(next_eps)<CFG.get('cycle_article_limit',5):next_eps.append(queue.pop(0))
    next_list = ''.join(f'<li>{E(ep["title"])}</li>' for ep in next_eps)
    return shell('制作进度', f'<section class="wrap progress-page"><a class="breadcrumb" href="/">← 首页</a><h1>故事，正在一集集变清楚。</h1><p class="article-dek">每5小时续做一轮，两账号合计目标20套幻灯片。文字讲解先发布，幻灯片和插图逐步补齐。</p><div class="progress-stats"><div><strong>{n}</strong><span>文字已整理</span></div><div><strong>{slides}</strong><span>幻灯片已补齐</span></div><div><strong>{missing}</strong><span>缺少逐字稿</span></div></div><h2>专题制作顺序</h2><div class="table-wrap"><table><thead><tr><th>专题</th><th>已整理 / 总集数</th><th>阅读顺序</th></tr></thead><tbody>{rows}</tbody></table></div><h2>接下来先整理的文字</h2><ol class="up-next">{next_list}</ol><p class="notice">这里展示当前已发布产物。缺失文稿保留记录，不用节目简介冒充逐字稿；生成失败的任务会记录并重试。</p></section>')

def build_browser_search_url(metadata):
    base = CFG.get('base_path', '')
    meta_by_show = collections.defaultdict(dict)
    library_items = {}
    lite_entries = []
    for entry in metadata['entries']:
        eid = entry['id']
        rel_url = entry['url'].removeprefix(base)
        default_url = article_url(eid)
        row = [
            eid, entry['title'], entry['original_title'], entry['show'],
            entry['topic'], entry['date'], int(entry['ready']),
            int(entry['slides']), int(entry['available']),
        ]
        if rel_url != default_url:
            row.append(rel_url)
        lite_entries.append(row)
        if entry['ready']:
            meta_by_show[entry['show']][eid] = [entry['summary'], entry['text']]
        img = entry.get('image')
        compact_img = (
            [img['width'], img['height'], [[v['width'], v['url'].removeprefix('/static/').removesuffix('.webp')] for v in img['variants']]]
            if img else None
        )
        if entry['summary'] or compact_img:
            library_items[eid] = [entry['summary'], compact_img]

    meta_shards = []
    for show, rows in meta_by_show.items():
        pairs = list(rows.items())
        for start in range(0, len(pairs), 64):
            chunk = dict(pairs[start:start + 64])
            url = write_asset(DIST, json.dumps(chunk, ensure_ascii=False, separators=(',', ':')).encode(), '.meta.json')
            meta_shards.append({'show': show, 'url': base + url, 'k': 'm'})

    library_url = write_asset(
        DIST,
        json.dumps({'b': base, 'i': library_items}, ensure_ascii=False, separators=(',', ':')).encode(),
        '.library.json',
    )
    lite_payload = {'b': base, 'l': base + library_url, 'e': lite_entries, 's': meta_shards + metadata['shards']}
    return write_asset(DIST, json.dumps(lite_payload, ensure_ascii=False, separators=(',', ':')).encode(), '.search-lite.json')

def save(rel, content):
    p = DIST / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(content)

def main():
    global ASSET_PREFIX, INLINE_CSS, COVERS, CHAPTER_IMAGES, SLIDE_DECKS, SEARCH_URL, CATALOG_URL
    if DIST.exists(): shutil.rmtree(DIST)
    DIST.mkdir()
    for name in ['style.css', 'app.js', 'search.js', 'favicon.svg']: shutil.copyfile(ROOT / name, DIST / name)
    if (ROOT / 'assets').exists(): shutil.copytree(ROOT / 'assets', DIST / 'assets')
    if (ROOT / 'vendor').exists(): shutil.copytree(ROOT / 'vendor', DIST / 'vendor')
    ASSET_PREFIX, INLINE_CSS, COVERS, CHAPTER_IMAGES, SLIDE_DECKS = prepare(ROOT, DIST, chapter_sources=episode_chapter_sources())
    CATALOG_URL = write_asset(DIST, json.dumps(build_catalog_data(), ensure_ascii=False, separators=(',', ':')).encode(), '.catalog.json')
    metadata = search_index(full=False)
    bodies = collections.defaultdict(dict)
    for entry in search_index()['entries']:
        if entry['ready']: bodies[entry['show']][entry['id']] = entry['text']
    metadata['shards'] = []
    for show, rows in bodies.items():
        pairs = list(rows.items())
        for start in range(0, len(pairs), 16):
            chunk = dict(pairs[start:start+16])
            url = write_asset(DIST, json.dumps(chunk,ensure_ascii=False,separators=(',',':')).encode(), '.json')
            metadata['shards'].append({'show':show,'url':CFG.get('base_path','')+url})
    encoded = json.dumps(metadata,ensure_ascii=False,separators=(',',':'))
    save('search-index.json', encoded)
    SEARCH_URL = build_browser_search_url(metadata)
    save('index.html', index()); save('progress/index.html', progress_page()); save('topics/index.html', all_topics())
    for topic in TOPICS: save(topic_url(topic).strip('/') + '/index.html', topic_page(topic))
    for show,topic in TOPIC_GROUPS: save(topic_url(topic,show).strip('/')+'/index.html',topic_page(topic,show))
    for page in range(2, math.ceil(len(ARTICLES)/PAGE_SIZE)+1):
        save(f'library/{page}/index.html', index(page))
    for ep in QUEUE:
        if ep['id'] in ARTICLES: save(article_url(ep['id']).strip('/') + '/index.html', episode(ep, ARTICLES[ep['id']]))
    save('404.html', shell('这一页还没画出来', '<section class="wrap topic-intro"><h1>这一页，还没画出来。</h1><p>可能是链接有误，或故事尚未制作。</p><a class="button" href="/">回到首页 →</a></section>'))
    urls = ['/', '/progress/', '/topics/'] + [topic_url(t,show) for show,t in TOPIC_GROUPS] + [article_url(eid) for eid in ARTICLES]
    save('sitemap.xml', '<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + ''.join(f'<url><loc>{CFG["domain"]}{u}</loc></url>' for u in urls) + '</urlset>')
    save('robots.txt', f'User-agent: *\nAllow: /\nSitemap: {CFG["domain"]}/sitemap.xml\n')
    save('asset-manifest.json', json.dumps({'version': VERSION, 'files': [p.relative_to(DIST).as_posix() for p in sorted((DIST/'static').rglob('*')) if p.is_file()]}, separators=(',', ':')))
    print(f'Built {len(ARTICLES)} articles, {len(TOPICS)} topics → {DIST}')

if __name__ == '__main__': main()
