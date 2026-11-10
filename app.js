import {normalize, searchEntries} from './search.js';
const search = document.querySelector('#search');
const grid = document.querySelector('.episode-grid');
const libraryMore = document.querySelector('#library-more');
const libraryStatus = document.querySelector('#library-status');
let show = 'all', libraryStart = Number(grid?.dataset.offset || 0), libraryLimit = 24, filterToken = 0;
function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}
function libraryCard(entry) {
  const card = element('article', undefined, 'episode-card');
  const cover = element('a', undefined, 'card-cover'); cover.href = entry.url;
  if (entry.image) {
    const {variants, width, height} = entry.image;
    const image = document.createElement('img');
    const base = new URL(dialog.dataset.searchIndex, location.href).pathname.split('/static/')[0];
    image.src = base + variants[Math.min(1, variants.length-1)].url;
    image.srcset = variants.map(v => `${base}${v.url} ${v.width}w`).join(', ');
    image.sizes = '(max-width: 650px) calc(100vw - 40px), (max-width: 1000px) 44vw, 360px';
    image.width = width; image.height = height; image.alt = entry.title;
    image.loading = 'lazy'; image.decoding = 'async'; cover.append(image);
  } else {
    const placeholder = element('div', undefined, 'cover-pending');
    placeholder.append(element('span','先读文字讲解'),element('small','漫画幻灯片稍后补充')); cover.append(placeholder);
  }
  const copy = element('div', undefined, 'card-copy');
  const meta = element('div', undefined, 'card-meta');
  meta.append(element('span', entry.topic), document.createTextNode(' · '), element('time', entry.date));
  const title = element('h3'); const link = element('a', entry.title); link.href = entry.url; title.append(link);
  const bottom = element('div', undefined, 'card-bottom');
  if (entry.slides) bottom.append(element('span', 'PPT', 'card-tag ppt'));
  copy.append(meta, title, element('p', entry.summary), bottom);
  card.dataset.show = entry.show; card.append(cover, copy); return card;
}
async function filter(reset = true) {
  if (!grid) return;
  const token = ++filterToken;
  if (reset) {libraryStart=0;libraryLimit=24;}
  libraryStatus.textContent='正在查找单集…';
  try {
    await loadIndex(); if(token!==filterToken)return;
    const hasQuery = Boolean(search?.value.trim());
    await Promise.all([loadLibraryMeta(), hasQuery ? loadMetaShards() : Promise.resolve()]);
    if(token!==filterToken)return;
    const list = searchEntries(entries,search?.value,show).filter(e=>e.ready);
    // Preserve the source's topic order for browsing; rank only actual searches.
    if (!hasQuery) list.sort((a,b)=>a.order-b.order);
    const end = Math.min(libraryStart+libraryLimit,list.length);
    grid.replaceChildren(...list.slice(libraryStart,end).map(libraryCard));
    document.querySelector('#empty').hidden=list.length>0;
    libraryMore.hidden=end>=list.length;
    libraryStatus.textContent=list.length?`显示 ${libraryStart+1}—${end} 集，共 ${list.length} 集`:'没有匹配的单集';
    return true;
  } catch {libraryStatus.textContent='目录暂时没加载好，请重试或按下面的分页继续阅读。';return false;}
}
let libraryTimer;
search?.addEventListener('input',()=>{clearTimeout(libraryTimer);libraryTimer=setTimeout(()=>filter(),120);});
document.querySelectorAll('[data-filter]').forEach(button=>button.addEventListener('click',()=>{
  show=button.dataset.filter;
  document.querySelectorAll('[data-filter]').forEach(item=>{item.classList.toggle('active',item===button);item.setAttribute('aria-pressed',String(item===button));});
  filter();
}));
libraryMore?.addEventListener('click',async event=>{
  event.preventDefault();libraryLimit+=24;
  if (!await filter(false) && show === 'all' && !search?.value.trim()) location.assign(libraryMore.href);
});

const dialog = document.querySelector('#command-search');
const query = dialog?.querySelector('#command-query');
const results = dialog?.querySelector('#command-results');
const status = dialog?.querySelector('#command-status');
const retry = dialog?.querySelector('.command-retry');
let entries = null, indexPromise = null, libraryUrl = null, libraryPromise = null, metaPromise = null, scope = 'all', active = -1, origin = null;
let matches = [], visibleLimit = 20, shards = [], bodyLoading = false;
const bodyLoaded = new Set(), bodyFailed = new Set();
let bodyTimer;
const pendingBodies = () => shards.filter(s => (scope === 'all' || s.show === scope) && !bodyLoaded.has(s.url));
function setActive(index) {
  const options = [...results.querySelectorAll('[role="option"]')];
  active = Math.max(-1, Math.min(index, options.length - 1));
  options.forEach((option,i) => option.setAttribute('aria-selected', String(i === active)));
  if (active >= 0) {
    query.setAttribute('aria-activedescendant', options[active].id);
    options[active].scrollIntoView({block:'nearest'});
  } else query.removeAttribute('aria-activedescendant');
}
function render() {
  if (!entries) return;
  const selectedHref = active >= 0 ? results.querySelector('[aria-selected="true"]')?.href : null;
  matches = searchEntries(entries, query.value, scope);
  results.replaceChildren();
  const list = matches.slice(0, visibleLimit);
  list.forEach((entry,i) => {
    const li = document.createElement('li'); li.setAttribute('role','presentation');
    const a = document.createElement('a'); a.href = entry.url; a.id = `command-option-${i}`;
    a.setAttribute('role','option'); a.setAttribute('aria-selected','false'); a.tabIndex = -1;
    const title = document.createElement('strong'); title.textContent = entry.title;
    const meta = document.createElement('span');
    const stage = entry.ready ? (entry.slides ? '文字 + 幻灯片' : '文字已整理 · 幻灯片待补') : (entry.available ? '文字待整理' : '文稿缺失');
    meta.textContent = `${entry.show} · ${entry.topic} · ${stage}`;
    a.append(title,meta);
    const token = normalize(query.value).split(' ').filter(Boolean)[0];
    if (token && entry.text) {
      const passage = entry.text.split(/[。！？]/).find(part => normalize(part).includes(token));
      if (passage) {
        const excerpt = document.createElement('p'); excerpt.className = 'command-result-snippet';
        excerpt.textContent = passage.trim().slice(0,110) + (passage.trim().length > 110 ? '…' : '');
        a.append(excerpt);
      }
    }
    li.append(a); results.append(li);
  });
  const more = dialog.querySelector('[data-search-more]');
  more.hidden = matches.length <= list.length;
  status.textContent = query.value.trim() ? (matches.length ? `找到 ${matches.length} 集，显示 ${list.length} 集。` : '没有找到匹配单集，试试人物、公司或专题名。') : (matches.length ? '最近整理的单集，也可以输入关键词搜索全部目录。' : '这档播客还没有已整理单集，输入关键词可搜索待整理目录。');
  if (query.value.trim() && pendingBodies().length) {
    if (!matches.length) status.textContent = '暂未找到标题或人物匹配。';
    status.textContent += bodyLoading ? ' 正在补充正文匹配…' : (bodyFailed.size ? ' 部分正文暂未加载，可以重试。' : ' 即将补充正文匹配…');
  }
  retry.hidden = !bodyFailed.size;
  setActive(selectedHref ? [...results.querySelectorAll('[role="option"]')].findIndex(option => option.href === selectedHref) : -1);
}
function inflateLiteEntries(data) {
  if (Array.isArray(data.entries)) {
    return { items: data.entries, shardList: data.shards || [], libUrl: null };
  }
  if (!Array.isArray(data.e)) throw new Error('Search unavailable');
  const base = data.b || '';
  const items = data.e.map((x, order) => ({
    id: x[0],
    title: x[1],
    original_title: x[2],
    show: x[3],
    topic: x[4],
    date: x[5],
    ready: Boolean(x[6]),
    slides: Boolean(x[7]),
    available: Boolean(x[8]),
    order,
    url: base + (x[9] || `/episodes/${x[0]}/`),
    text: '',
    summary: '',
    image: null
  }));
  return { items, shardList: data.s || [], libUrl: data.l || null };
}
function applyShardPayload(byId, payload) {
  for (const [id, val] of Object.entries(payload)) {
    const entry = byId.get(id);
    if (!entry) continue;
    if (Array.isArray(val)) {
      if (val[0]) entry.summary = val[0];
      if (val[1] && !entry._metaLoaded) {
        entry.text = val[1] + (entry.text ? ' ' + entry.text : '');
        entry._metaLoaded = true;
      }
    } else if (typeof val === 'string') {
      entry.text += (entry.text ? ' ' : '') + val;
    }
  }
}
async function loadLibraryMeta() {
  if (!libraryUrl) return;
  if (!libraryPromise) {
    libraryPromise = fetch(libraryUrl).then(r => {
      if (!r.ok) throw new Error('Library unavailable');
      return r.json();
    }).then(data => {
      const byId = new Map((entries || []).map(e => [e.id, e]));
      for (const [id, row] of Object.entries(data.i || {})) {
        const entry = byId.get(id);
        if (!entry) continue;
        if (row[0]) entry.summary = row[0];
        if (Array.isArray(row[1])) {
          const [width, height, vars] = row[1];
          entry.image = { width, height, variants: vars.map(([w, hash]) => ({ width: w, url: `/static/${hash}.webp` })) };
        }
      }
    }).catch(err => { libraryPromise = null; throw err; });
  }
  return libraryPromise;
}
async function loadMetaShards() {
  const todo = shards.filter(s => s.k === 'm' && !bodyLoaded.has(s.url));
  if (!todo.length) return;
  if (!metaPromise) {
    const byId = new Map((entries || []).map(e => [e.id, e]));
    metaPromise = Promise.all(todo.map(shard => fetch(shard.url).then(r => {
      if (!r.ok) throw new Error('Search unavailable');
      return r.json();
    }).then(payload => {
      applyShardPayload(byId, payload);
      bodyLoaded.add(shard.url);
    }))).catch(err => { metaPromise = null; throw err; });
  }
  return metaPromise;
}
async function loadIndex() {
  if (!indexPromise) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 30000);
    indexPromise = fetch(dialog.dataset.searchIndex, {signal:controller.signal}).then(r => {
      if (!r.ok) throw new Error('Search unavailable');
      return r.json();
    }).then(data => {
      const inflated = inflateLiteEntries(data);
      entries = inflated.items;
      shards = inflated.shardList;
      libraryUrl = inflated.libUrl;
    }).catch(error => {indexPromise = null; throw error;}).finally(() => clearTimeout(timer));
  }
  if (dialog.open) {retry.hidden = true; status.textContent = '正在加载搜索目录…';}
  try {await indexPromise; if (dialog.open) render();}
  catch (error) {if (dialog.open) {status.textContent = '搜索目录暂时没加载好，请检查网络后重试。'; retry.hidden = false;} throw error;}
}
function openSearch() {
  if (!dialog || dialog.open) return;
  origin = document.activeElement;
  dialog.showModal(); query.setAttribute('aria-expanded','true'); query.focus();
  visibleLimit = 20;
  if (entries) {render(); scheduleBodies();} else loadIndex().then(scheduleBodies).catch(()=>{});
}
document.querySelectorAll('[data-open-search]').forEach(button => {
  button.addEventListener('click', openSearch);
  button.addEventListener('pointerenter', () => { if (!entries) loadIndex().catch(() => {}); }, { once: true });
  button.addEventListener('focus', () => { if (!entries) loadIndex().catch(() => {}); }, { once: true });
});
document.addEventListener('keydown',event => {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k' && !event.altKey && !event.isComposing) {
    event.preventDefault(); openSearch();
  }
});
dialog?.querySelector('[data-close-search]').addEventListener('click',() => dialog.close());
dialog?.addEventListener('keydown',event => {
  if (event.key === 'Escape' && !event.isComposing) {event.preventDefault(); dialog.close();}
});
dialog?.addEventListener('close',() => {
  query.setAttribute('aria-expanded','false'); query.removeAttribute('aria-activedescendant');
  if (origin?.isConnected) origin.focus();
});
dialog?.addEventListener('click',event => {
  if (event.target !== dialog) return;
  const box = dialog.getBoundingClientRect();
  if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) dialog.close();
});
query?.addEventListener('input',event => {visibleLimit = 20; active = -1; render(); if(!event.isComposing) scheduleBodies();});
query?.addEventListener('compositionend',scheduleBodies);
query?.addEventListener('keydown',event => {
  if (event.isComposing) return;
  if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
    event.preventDefault(); setActive(active + (event.key === 'ArrowDown' ? 1 : -1));
  } else if (event.key === 'Enter' && active >= 0) {
    event.preventDefault(); results.querySelectorAll('[role="option"]')[active]?.click();
  }
});
dialog?.querySelectorAll('[data-search-show]').forEach(button => button.addEventListener('click',() => {
  scope = button.dataset.searchShow; visibleLimit = 20; active = -1;
  dialog.querySelectorAll('[data-search-show]').forEach(item => item.setAttribute('aria-pressed',String(item === button)));
  render(); scheduleBodies(); query.focus();
}));
retry?.addEventListener('click',()=>{if(!entries) loadIndex().then(scheduleBodies).catch(()=>{});else {bodyFailed.clear();scheduleBodies();}});
dialog?.querySelector('[data-search-more]').addEventListener('click',() => {visibleLimit += 20; render(); query.focus();});

function scheduleBodies() {
  clearTimeout(bodyTimer);
  if (entries && query.value.trim() && dialog.open) bodyTimer=setTimeout(loadBodies,180);
}
async function loadBodies() {
  if (bodyLoading || !query.value.trim() || !dialog.open) return;
  const todo=pendingBodies().filter(s=>!bodyFailed.has(s.url));
  if(!todo.length)return;
  bodyLoading=true;render();
  const byId=new Map(entries.map(e=>[e.id,e]));
  async function worker() {
    while(todo.length && dialog.open && query.value.trim()) {
      const shard=todo.shift();if(scope!=='all' && shard.show!==scope)continue;
      const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),12000);
      try {
        const response=await fetch(shard.url,{signal:controller.signal});if(!response.ok)throw Error('Search unavailable');
        const bodies=await response.json();
        applyShardPayload(byId, bodies);
        bodyLoaded.add(shard.url);
      } catch {bodyFailed.add(shard.url);} finally {clearTimeout(timer);}
      if(dialog.open)render();
    }
  }
  await Promise.all([worker(),worker(),worker()]);bodyLoading=false;
  if(dialog.open){render();scheduleBodies();}
}

// -------------------------------------------------------------
// 1. Image Lightbox (图片点击放大、全屏查看)
// -------------------------------------------------------------
const lightbox = document.querySelector('#image-lightbox');
const lightboxImg = lightbox?.querySelector('#lightbox-img');
const lightboxCaption = lightbox?.querySelector('#lightbox-caption');
const lightboxClose = lightbox?.querySelector('[data-close-lightbox]');

function openLightbox(img) {
  if (!lightbox || !lightboxImg || !img) return;
  const src = img.currentSrc || img.src;
  if (!src) return;
  lightboxImg.src = src;
  lightboxImg.alt = img.alt || '';
  if (lightboxCaption) {
    const text = img.alt || '';
    lightboxCaption.textContent = text;
    lightboxCaption.hidden = !text;
  }
  lightbox.showModal();
}

function closeLightbox() {
  if (lightbox?.open) lightbox.close();
  lightboxImg?.classList.remove('zoomed');
}

lightboxImg?.addEventListener('click', () => {
  lightboxImg.classList.toggle('zoomed');
});

lightboxClose?.addEventListener('click', closeLightbox);
lightbox?.addEventListener('click', event => {
  if (event.target === lightbox || event.target.classList.contains('lightbox-shell') || event.target.classList.contains('lightbox-stage')) {
    closeLightbox();
  }
});
lightbox?.addEventListener('keydown', event => {
  if (event.key === 'Escape' && !event.isComposing) {
    event.preventDefault();
    closeLightbox();
  }
});

// Click on zoomable images in article content, figures, and covers
document.addEventListener('click', event => {
  const img = event.target.closest('.chapter figure img, .chapter img, figure img');
  if (img && !img.closest('#slide-viewer') && !img.closest('#image-lightbox')) {
    event.preventDefault();
    openLightbox(img);
  }
});

// -------------------------------------------------------------
// 2. In-Page Slide Viewer (PDF 在页面中打开、纯粹翻页查看)
// -------------------------------------------------------------
const slideViewer = document.querySelector('#slide-viewer');
const slideTitle = slideViewer?.querySelector('#slide-title');
const slidePageNum = slideViewer?.querySelector('#slide-page-num');
const slidePageCount = slideViewer?.querySelector('#slide-page-count');
const slideDownloadBtn = slideViewer?.querySelector('#slide-download-btn');
const slideFsBtn = slideViewer?.querySelector('#slide-fs-btn');
const slideCloseBtn = slideViewer?.querySelector('[data-close-slides]');
const slideCanvas = slideViewer?.querySelector('#slide-canvas');
const slideImg = slideViewer?.querySelector('#slide-img');
const slideLoading = slideViewer?.querySelector('#slide-loading');
const slidePrevBtn = slideViewer?.querySelector('#slide-prev');
const slideNextBtn = slideViewer?.querySelector('#slide-next');
const slideCanvasBox = slideViewer?.querySelector('#slide-canvas-box');
const slideEndCard = slideViewer?.querySelector('#slide-end-card');
const slideEndTitle = slideViewer?.querySelector('#slide-end-current-title');
const slideJumpNext = slideViewer?.querySelector('#slide-jump-next');
const slideJumpNextTitle = slideViewer?.querySelector('#slide-jump-next-title');
const slideJumpPrev = slideViewer?.querySelector('#slide-jump-prev');
const slideJumpPrevTitle = slideViewer?.querySelector('#slide-jump-prev-title');
const slideReplayBtn = slideViewer?.querySelector('#slide-replay-btn');

let currentPdfDoc = null;
let currentSlidePages = null;
const slideImgCache = new Map();
let slideRenderToken = 0;
let currentPdfPage = 1;
let totalPdfPages = 0;
let isRendering = false;
let pendingPage = null;
let currentRenderTask = null;
let catalogData = null;
let currentSlideMeta = {
  id: '',
  url: '',
  title: '',
  prevSlides: '',
  prevId: '',
  prevPrefix: '',
  prevCount: '',
  prevTitle: '',
  nextSlides: '',
  nextId: '',
  nextPrefix: '',
  nextCount: '',
  nextTitle: ''
};

function slidesListFromMeta(meta) {
  if (Array.isArray(meta.slidePages) && meta.slidePages.length) return meta.slidePages;
  const count = Number(meta.slideCount || 0);
  if (meta.slidePrefix && count > 0) {
    const prefix = meta.slidePrefix.endsWith('/') ? meta.slidePrefix : meta.slidePrefix + '/';
    return Array.from({ length: count }, (_, i) => `${prefix}${i + 1}.webp`);
  }
  return null;
}

function pdfBasePrefix() {
  const baseEl = document.querySelector('#command-search');
  return (new URL(baseEl?.dataset.searchIndex || location.href, location.href).pathname.split('/static/')[0] || '').replace(/\/+$/, '');
}

function neighborDecksFromCatalog(eid) {
  if (!catalogData || !eid) return null;
  const groups = catalogData.groups || [];
  let topicSlideEps = null;
  const allSlideEps = [];
  for (const g of groups) {
    const eps = (g.eps || []).filter(ep => ep.p);
    if (eps.some(ep => ep.id === eid)) topicSlideEps = eps;
    allSlideEps.push(...eps);
  }
  const base = pdfBasePrefix();
  const findPrevNext = (list, targetId) => {
    const idx = list.findIndex(x => x.id === targetId);
    return {
      prev: idx > 0 ? list[idx - 1] : null,
      next: idx >= 0 && idx + 1 < list.length ? list[idx + 1] : null
    };
  };
  const topicRel = topicSlideEps ? findPrevNext(topicSlideEps, eid) : { prev: null, next: null };
  const globalRel = findPrevNext(allSlideEps, eid);
  const pack = (ep) => ep ? {
    id: ep.id,
    url: `${base}/assets/slides/${ep.id}.pdf`,
    prefix: ep.sp || '',
    count: String(ep.sc || ''),
    title: ep.h || ''
  } : { id: '', url: '', prefix: '', count: '', title: '' };
  return {
    prev: pack(topicRel.prev || globalRel.prev),
    next: pack(topicRel.next || globalRel.next)
  };
}

async function getPdfjs() {
  if (window.pdfjsLib) return window.pdfjsLib;
  const base = pdfBasePrefix();
  const lib = await import(base + '/vendor/pdf.min.mjs');
  lib.GlobalWorkerOptions.workerSrc = base + '/vendor/pdf.worker.min.mjs';
  window.pdfjsLib = lib;
  return lib;
}

function showEndCard() {
  if (!slideEndCard) return;
  if (slideEndTitle) slideEndTitle.textContent = currentSlideMeta.title;
  if (currentSlideMeta.nextSlides) {
    if (slideJumpNext) {
      slideJumpNext.hidden = false;
      if (slideJumpNextTitle) slideJumpNextTitle.textContent = currentSlideMeta.nextTitle || '下一篇';
    }
  } else {
    if (slideJumpNext) slideJumpNext.hidden = true;
  }
  if (currentSlideMeta.prevSlides) {
    if (slideJumpPrev) {
      slideJumpPrev.hidden = false;
      if (slideJumpPrevTitle) slideJumpPrevTitle.textContent = currentSlideMeta.prevTitle || '上一篇';
    }
  } else {
    if (slideJumpPrev) slideJumpPrev.hidden = true;
  }
  slideEndCard.hidden = false;
}

function hideEndCard() {
  if (slideEndCard) slideEndCard.hidden = true;
}

function jumpDeck(direction) {
  const isNext = direction === 'next';
  const url = isNext ? currentSlideMeta.nextSlides : currentSlideMeta.prevSlides;
  if (!url) return;
  const targetId = isNext ? currentSlideMeta.nextId : currentSlideMeta.prevId;
  const prefix = isNext ? currentSlideMeta.nextPrefix : currentSlideMeta.prevPrefix;
  const count = isNext ? currentSlideMeta.nextCount : currentSlideMeta.prevCount;
  const title = isNext ? currentSlideMeta.nextTitle : currentSlideMeta.prevTitle;
  const neighbors = neighborDecksFromCatalog(targetId);
  openSlideViewer(url, title, {
    slideId: targetId,
    slidePrefix: prefix,
    slideCount: count,
    prevSlides: neighbors?.prev.url || '',
    prevId: neighbors?.prev.id || '',
    prevPrefix: neighbors?.prev.prefix || '',
    prevCount: neighbors?.prev.count || '',
    prevTitle: neighbors?.prev.title || '',
    nextSlides: neighbors?.next.url || '',
    nextId: neighbors?.next.id || '',
    nextPrefix: neighbors?.next.prefix || '',
    nextCount: neighbors?.next.count || '',
    nextTitle: neighbors?.next.title || ''
  });
  if (!neighbors && targetId) {
    fetchCatalogData().then(() => {
      if (currentSlideMeta.id !== targetId) return;
      const resolved = neighborDecksFromCatalog(targetId);
      if (!resolved) return;
      currentSlideMeta.prevSlides = resolved.prev.url;
      currentSlideMeta.prevId = resolved.prev.id;
      currentSlideMeta.prevPrefix = resolved.prev.prefix;
      currentSlideMeta.prevCount = resolved.prev.count;
      currentSlideMeta.prevTitle = resolved.prev.title;
      currentSlideMeta.nextSlides = resolved.next.url;
      currentSlideMeta.nextId = resolved.next.id;
      currentSlideMeta.nextPrefix = resolved.next.prefix;
      currentSlideMeta.nextCount = resolved.next.count;
      currentSlideMeta.nextTitle = resolved.next.title;
      if (slideEndCard && !slideEndCard.hidden) showEndCard();
    }).catch(() => {});
  }
}

slideJumpNext?.addEventListener('click', () => jumpDeck('next'));
slideJumpPrev?.addEventListener('click', () => jumpDeck('prev'));
slideReplayBtn?.addEventListener('click', () => {
  hideEndCard();
  renderSlidePage(1);
});

function preloadSlideUrl(url) {
  if (!url) return Promise.resolve();
  if (slideImgCache.has(url)) return slideImgCache.get(url);
  if (slideImgCache.size >= 45) slideImgCache.delete(slideImgCache.keys().next().value);
  const im = new Image();
  im.decoding = 'async';
  im.src = url;
  const p = (im.decode ? im.decode() : new Promise((res, rej) => { im.onload = res; im.onerror = rej; })).catch(() => {});
  slideImgCache.set(url, p);
  return p;
}

function preloadSlideImg(pageNum) {
  if (!currentSlidePages || pageNum < 1 || pageNum > currentSlidePages.length) return Promise.resolve();
  return preloadSlideUrl(currentSlidePages[pageNum - 1]);
}

async function openSlideViewer(pdfUrl, title, meta = {}) {
  if (!slideViewer) return;
  slideRenderToken++;
  slideViewer.showModal();
  if (slideTitle) slideTitle.textContent = title || '漫画幻灯片';
  if (slideDownloadBtn) slideDownloadBtn.href = pdfUrl;
  if (slideLoading) {
    slideLoading.hidden = false;
    slideLoading.replaceChildren(element('span', '正在载入幻灯片…'));
  }
  if (slidePageNum) slidePageNum.textContent = '1';
  if (slidePageCount) slidePageCount.textContent = '-';
  hideEndCard();

  currentSlidePages = slidesListFromMeta(meta);
  currentSlideMeta = {
    id: meta.slideId || '',
    url: pdfUrl,
    title: title || '漫画幻灯片',
    prevSlides: meta.prevSlides || '',
    prevId: meta.prevId || '',
    prevPrefix: meta.prevPrefix || '',
    prevCount: meta.prevCount || '',
    prevTitle: meta.prevTitle || '',
    nextSlides: meta.nextSlides || '',
    nextId: meta.nextId || '',
    nextPrefix: meta.nextPrefix || '',
    nextCount: meta.nextCount || '',
    nextTitle: meta.nextTitle || ''
  };

  if (currentSlidePages && slideImg) {
    currentPdfDoc = null;
    if (slideCanvas) slideCanvas.hidden = true;
    slideImg.hidden = false;
    totalPdfPages = currentSlidePages.length;
    if (slidePageCount) slidePageCount.textContent = String(totalPdfPages);
    currentPdfPage = 1;
    await renderSlidePage(1);
    return;
  }

  if (slideImg) slideImg.hidden = true;
  if (slideCanvas) slideCanvas.hidden = false;

  try {
    const pdfjs = await getPdfjs();
    const loadingTask = pdfjs.getDocument(pdfUrl);
    currentPdfDoc = await loadingTask.promise;
    totalPdfPages = currentPdfDoc.numPages;
    if (slidePageCount) slidePageCount.textContent = String(totalPdfPages);
    currentPdfPage = 1;
    renderSlidePage(currentPdfPage);
  } catch (err) {
    console.error('Slide viewer load error:', err);
    if (slideLoading) {
      slideLoading.replaceChildren(element('span', '幻灯片在线解析失败，请点击右上角直接下载或在新窗口打开。'));
    }
  }
}

async function renderSlidePage(num) {
  if (currentSlidePages && slideImg) {
    const token = ++slideRenderToken;
    const idx = Math.max(1, Math.min(num, currentSlidePages.length));
    const url = currentSlidePages[idx - 1];
    await preloadSlideImg(idx);
    if (token !== slideRenderToken || !slideViewer?.open) return;
    slideImg.src = url;
    currentPdfPage = idx;
    if (slidePageNum) slidePageNum.textContent = String(idx);
    if (slidePrevBtn) slidePrevBtn.disabled = idx <= 1;
    if (slideNextBtn) slideNextBtn.disabled = idx >= totalPdfPages;
    if (slideLoading) slideLoading.hidden = true;
    if (idx === totalPdfPages) showEndCard(); else hideEndCard();
    preloadSlideImg(idx + 1);
    preloadSlideImg(idx + 2);
    return;
  }

  if (!currentPdfDoc || !slideCanvas) return;
  if (isRendering) {
    pendingPage = num;
    if (currentRenderTask) {
      try { currentRenderTask.cancel(); } catch {}
    }
    return;
  }
  isRendering = true;
  if (!currentPdfPage && slideLoading) slideLoading.hidden = false;

  try {
    const page = await currentPdfDoc.getPage(num);
    const box = slideCanvasBox || slideCanvas.parentElement;
    const boxRect = box.getBoundingClientRect();
    const unscaledViewport = page.getViewport({ scale: 1 });

    const availWidth = Math.max(280, boxRect.width - 24);
    const availHeight = Math.max(180, boxRect.height - 24);
    const scale = Math.min(availWidth / unscaledViewport.width, availHeight / unscaledViewport.height);
    const dpr = Math.min(window.devicePixelRatio || 1, 2.5);
    const viewport = page.getViewport({ scale });

    // Double-buffering: render onto offscreen canvas first to eliminate blank strobe
    const offscreen = document.createElement('canvas');
    offscreen.width = Math.floor(viewport.width * dpr);
    offscreen.height = Math.floor(viewport.height * dpr);
    const offCtx = offscreen.getContext('2d');
    offCtx.setTransform(dpr, 0, 0, dpr, 0, 0);

    currentRenderTask = page.render({ canvasContext: offCtx, viewport });
    await currentRenderTask.promise;
    currentRenderTask = null;

    // Seamlessly swap in one frame
    slideCanvas.width = offscreen.width;
    slideCanvas.height = offscreen.height;
    slideCanvas.style.width = Math.floor(viewport.width) + 'px';
    slideCanvas.style.height = Math.floor(viewport.height) + 'px';
    const ctx = slideCanvas.getContext('2d');
    ctx.drawImage(offscreen, 0, 0);

    currentPdfPage = num;
    if (slidePageNum) slidePageNum.textContent = String(num);
    if (slidePrevBtn) slidePrevBtn.disabled = num <= 1;
    if (slideNextBtn) slideNextBtn.disabled = num >= totalPdfPages;

    if (num === totalPdfPages) {
      showEndCard();
    } else {
      hideEndCard();
    }
  } catch (err) {
    if (err?.name !== 'RenderingCancelledException') {
      console.error('Render error:', err);
    }
  } finally {
    isRendering = false;
    if (slideLoading) slideLoading.hidden = true;
    if (pendingPage !== null) {
      const p = pendingPage;
      pendingPage = null;
      renderSlidePage(p);
    }
  }
}

function prevSlide() {
  if (currentPdfPage > 1) {
    hideEndCard();
    renderSlidePage(currentPdfPage - 1);
  }
}

function nextSlide() {
  if (currentPdfPage < totalPdfPages) {
    renderSlidePage(currentPdfPage + 1);
  } else if (currentPdfPage === totalPdfPages) {
    showEndCard();
  }
}

function isSlideFs() {
  return Boolean(
    document.fullscreenElement ||
    document.webkitFullscreenElement ||
    slideViewer?.classList.contains('is-fullscreen')
  );
}

function updateFsButton(fs) {
  if (slideFsBtn) {
    slideFsBtn.textContent = fs ? '🗗 退出' : '⛶ 全屏';
    slideFsBtn.setAttribute('aria-label', fs ? '退出全屏' : '全屏模式');
  }
}

function toggleSlideFullscreen() {
  if (!slideViewer) return;
  const inFs = isSlideFs();
  if (!inFs) {
    const req = slideViewer.requestFullscreen ||
                slideViewer.webkitRequestFullscreen ||
                slideViewer.mozRequestFullScreen ||
                slideViewer.msRequestFullscreen;
    if (req) {
      req.call(slideViewer).then(() => {
        updateFsButton(true);
        setTimeout(() => renderSlidePage(currentPdfPage), 100);
      }).catch(() => {
        slideViewer.classList.add('is-fullscreen');
        updateFsButton(true);
        renderSlidePage(currentPdfPage);
      });
    } else {
      slideViewer.classList.add('is-fullscreen');
      updateFsButton(true);
      renderSlidePage(currentPdfPage);
    }
  } else {
    const exit = document.exitFullscreen ||
                 document.webkitExitFullscreen ||
                 document.mozCancelFullScreen ||
                 document.msExitFullscreen;
    if (document.fullscreenElement || document.webkitFullscreenElement) {
      exit?.call(document).catch(() => {});
    }
    slideViewer.classList.remove('is-fullscreen');
    updateFsButton(false);
    setTimeout(() => renderSlidePage(currentPdfPage), 100);
  }
}

document.addEventListener('fullscreenchange', () => {
  const inFs = Boolean(document.fullscreenElement);
  updateFsButton(inFs);
  if (slideViewer?.open) renderSlidePage(currentPdfPage);
});
document.addEventListener('webkitfullscreenchange', () => {
  const inFs = Boolean(document.webkitFullscreenElement);
  updateFsButton(inFs);
  if (slideViewer?.open) renderSlidePage(currentPdfPage);
});

slideFsBtn?.addEventListener('click', toggleSlideFullscreen);

function closeSlideViewer() {
  if (isSlideFs()) {
    toggleSlideFullscreen();
  }
  if (currentRenderTask) {
    try { currentRenderTask.cancel(); } catch {}
    currentRenderTask = null;
  }
  currentPdfDoc = null;
  currentSlidePages = null;
  hideEndCard();
  if (slideViewer?.open) slideViewer.close();
}

slidePrevBtn?.addEventListener('click', prevSlide);
slideNextBtn?.addEventListener('click', nextSlide);
slideCloseBtn?.addEventListener('click', closeSlideViewer);

slideViewer?.addEventListener('keydown', event => {
  if (event.key === 'Escape') {
    event.preventDefault();
    closeSlideViewer();
  } else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp' || event.key === 'PageUp') {
    event.preventDefault();
    prevSlide();
  } else if (event.key === 'ArrowRight' || event.key === 'ArrowDown' || event.key === 'PageDown' || event.key === ' ') {
    event.preventDefault();
    nextSlide();
  } else if (event.key === 'Home') {
    event.preventDefault();
    renderSlidePage(1);
  } else if (event.key === 'End') {
    event.preventDefault();
    renderSlidePage(totalPdfPages);
  }
});

// Click left / right sides of canvas/image to navigate
slideCanvasBox?.addEventListener('click', event => {
  if (slideEndCard && !slideEndCard.hidden && slideEndCard.contains(event.target)) return;
  if (event.target === slideCanvas || event.target === slideImg) {
    const rect = event.target.getBoundingClientRect();
    const x = event.clientX - rect.left;
    if (x < rect.width * 0.4) prevSlide();
    else if (x > rect.width * 0.6) nextSlide();
  }
});

// Mobile touch swipe gesture
let touchStartX = 0;
let touchStartY = 0;
slideCanvasBox?.addEventListener('touchstart', event => {
  touchStartX = event.changedTouches[0].clientX;
  touchStartY = event.changedTouches[0].clientY;
}, {passive: true});
slideCanvasBox?.addEventListener('touchend', event => {
  const diffX = event.changedTouches[0].clientX - touchStartX;
  const diffY = event.changedTouches[0].clientY - touchStartY;
  if (Math.abs(diffX) > 40 && Math.abs(diffX) > Math.abs(diffY)) {
    if (diffX > 0) prevSlide();
    else nextSlide();
  }
}, {passive: true});

// Resize re-render
let resizeTimer;
window.addEventListener('resize', () => {
  if (slideViewer?.open && currentPdfDoc) {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => renderSlidePage(currentPdfPage), 150);
  }
});

// -------------------------------------------------------------
// 3. Global Catalog Drawer (全站故事目录 - Lazy DOM + Cached JSON)
// -------------------------------------------------------------
const catalogDialog = document.querySelector('#global-catalog');
const catalogBody = catalogDialog?.querySelector('#catalog-body');
const catalogFilterInput = catalogDialog?.querySelector('#catalog-filter-input');
const catalogTabs = catalogDialog?.querySelectorAll('[data-cat-filter]');
let currentCatShow = 'all';
let catalogBuilt = Boolean(catalogBody?.querySelector('.cat-group'));
let catalogPromise = null;

function buildCatalogDom(data) {
  if (!catalogBody || catalogBuilt) return;
  const currentEid = catalogDialog?.dataset.currentEid || '';
  const frag = document.createDocumentFragment();
  for (const g of data.groups || []) {
    const groupDiv = element('div', undefined, 'cat-group');
    groupDiv.dataset.show = g.s;
    const header = element('div', undefined, 'cat-group-header');
    const h4 = document.createElement('h4');
    const topicLink = element('a', g.t);
    topicLink.href = g.u;
    h4.append(topicLink);
    const countSpan = element('span', `${g.r}/${g.n} 集`, 'cat-group-count');
    header.append(h4, countSpan);
    const ul = element('ul', undefined, 'cat-list');
    for (const ep of g.eps) {
      const isActive = ep.id === currentEid;
      const li = element('li', undefined, isActive ? 'cat-item active' : 'cat-item');
      li.dataset.eid = ep.id;
      li.dataset.show = g.s;
      const a = document.createElement('a');
      a.href = ep.u;
      if (isActive) a.setAttribute('aria-current', 'page');
      const order = element('span', ep.o, 'cat-order');
      const title = element('span', ep.h, 'cat-title');
      a.append(order, title);
      if (ep.p) a.append(element('span', 'PPT', 'cat-tag'));
      li.append(a);
      ul.append(li);
    }
    groupDiv.append(header, ul);
    frag.append(groupDiv);
  }
  catalogBody.replaceChildren(frag);
  catalogBuilt = true;
}

function fetchCatalogData() {
  if (catalogData) return Promise.resolve(catalogData);
  if (!catalogPromise) {
    const url = catalogDialog?.dataset.catalogUrl;
    if (!url) return Promise.resolve(null);
    catalogPromise = fetch(url)
      .then(r => { if (!r.ok) throw new Error('Catalog unavailable'); return r.json(); })
      .then(data => {
        catalogData = data;
        return data;
      })
      .catch(err => {
        catalogPromise = null;
        throw err;
      });
  }
  return catalogPromise;
}

function loadCatalog() {
  if (catalogBuilt) return Promise.resolve();
  return fetchCatalogData()
    .then(data => { if (data) buildCatalogDom(data); })
    .catch(err => {
      if (catalogBody) catalogBody.replaceChildren(element('p', '目录加载失败，请刷新重试。', 'catalog-status'));
      throw err;
    });
}

async function openCatalog() {
  if (!catalogDialog) return;
  catalogDialog.showModal();
  if (!catalogBuilt) {
    await loadCatalog().catch(() => {});
  }
  filterCatalog();
  const activeItem = catalogDialog.querySelector('.cat-item.active');
  if (activeItem) {
    setTimeout(() => {
      activeItem.scrollIntoView({ block: 'center', behavior: 'smooth' });
    }, 40);
  }
}

function closeCatalog() {
  if (catalogDialog?.open) catalogDialog.close();
}

function filterCatalog() {
  if (!catalogDialog || !catalogBuilt) return;
  const q = (catalogFilterInput?.value || '').trim().toLowerCase();
  const groups = catalogDialog.querySelectorAll('.cat-group');
  groups.forEach(group => {
    const groupShow = group.dataset.show;
    const showMatch = currentCatShow === 'all' || groupShow === currentCatShow;
    if (!showMatch) {
      group.hidden = true;
      return;
    }
    const items = group.querySelectorAll('.cat-item');
    let visibleInGroup = 0;
    items.forEach(item => {
      const title = (item.querySelector('.cat-title')?.textContent || '').toLowerCase();
      const match = !q || title.includes(q);
      item.hidden = !match;
      if (match) visibleInGroup++;
    });
    group.hidden = visibleInGroup === 0;
  });
}

catalogTabs?.forEach(btn => {
  btn.addEventListener('click', () => {
    currentCatShow = btn.dataset.catFilter;
    catalogTabs.forEach(b => b.classList.toggle('active', b === btn));
    filterCatalog();
  });
});

catalogFilterInput?.addEventListener('input', filterCatalog);
catalogDialog?.querySelector('[data-close-catalog]')?.addEventListener('click', closeCatalog);
catalogDialog?.addEventListener('click', event => {
  if (event.target === catalogDialog) closeCatalog();
});

document.querySelectorAll('[data-open-catalog]').forEach(btn => {
  btn.addEventListener('pointerenter', () => { loadCatalog().catch(() => {}); }, { once: true });
  btn.addEventListener('focus', () => { loadCatalog().catch(() => {}); }, { once: true });
});

document.querySelectorAll('[data-open-slides]').forEach(btn => {
  const warmSlide = () => {
    const p = btn.dataset.slidePrefix;
    if (p && Number(btn.dataset.slideCount) > 0) preloadSlideUrl((p.endsWith('/') ? p : p + '/') + '1.webp');
  };
  btn.addEventListener('pointerenter', warmSlide, { once: true });
  btn.addEventListener('focus', warmSlide, { once: true });
});

[search, libraryMore, ...document.querySelectorAll('[data-filter]')].filter(Boolean).forEach(el => {
  const warmLibrary = () => { loadIndex().then(() => loadLibraryMeta()).catch(() => {}); };
  el.addEventListener('pointerenter', warmLibrary, { once: true });
  el.addEventListener('focus', warmLibrary, { once: true });
});

// Progressive sticky PPT button reveal once hero button scrolls out of view
const heroActionsEl = document.querySelector('.article-intro .hero-actions');
const tocEl = document.querySelector('.toc');
if (heroActionsEl && tocEl?.querySelector('.toc-ppt-btn')) {
  const obs = new IntersectionObserver(entries => {
    tocEl.classList.toggle('show-ppt', !entries[0].isIntersecting);
  }, { threshold: 0 });
  obs.observe(heroActionsEl);
}

// -------------------------------------------------------------
// 4. Global Keyboard Shortcuts & Event Delegation
// -------------------------------------------------------------
window.addEventListener('keydown', event => {
  if (event.target.matches('input, textarea, select')) return;
  if (document.querySelector('dialog[open]')) return;
  if (event.altKey || event.ctrlKey || event.metaKey) return;

  if (event.key === 'ArrowLeft') {
    const prev = document.querySelector('.article-pagination .pagination-card.prev');
    if (prev && prev.href) {
      event.preventDefault();
      location.assign(prev.href);
    }
  } else if (event.key === 'ArrowRight') {
    const next = document.querySelector('.article-pagination .pagination-card.next');
    if (next && next.href) {
      event.preventDefault();
      location.assign(next.href);
    }
  } else if (event.key === 'm' || event.key === 'M') {
    event.preventDefault();
    openCatalog();
  }
});

// Global trigger for [data-open-catalog]
document.addEventListener('click', event => {
  if (event.target.closest('[data-open-catalog]')) {
    event.preventDefault();
    openCatalog();
  }
});

// Global trigger for [data-open-slides]
document.addEventListener('click', event => {
  const btn = event.target.closest('[data-open-slides]');
  if (btn) {
    event.preventDefault();
    let slidePages = null;
    if (btn.dataset.slidePages) {
      try { slidePages = JSON.parse(btn.dataset.slidePages); } catch {}
    }
    openSlideViewer(btn.dataset.openSlides, btn.dataset.title, {
      slideId: btn.dataset.slideId,
      slidePrefix: btn.dataset.slidePrefix,
      slideCount: btn.dataset.slideCount,
      prevSlides: btn.dataset.prevSlides,
      prevId: btn.dataset.prevSlideId,
      prevPrefix: btn.dataset.prevSlidePrefix,
      prevCount: btn.dataset.prevSlideCount,
      prevTitle: btn.dataset.prevTitle,
      nextSlides: btn.dataset.nextSlides,
      nextId: btn.dataset.nextSlideId,
      nextPrefix: btn.dataset.nextSlidePrefix,
      nextCount: btn.dataset.nextSlideCount,
      nextTitle: btn.dataset.nextTitle,
      slidePages
    });
  }
});
