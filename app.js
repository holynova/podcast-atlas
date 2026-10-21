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
  const copy = element('div',undefined,'card-copy');
  const title = element('h3'); const link = element('a',entry.title); link.href=entry.url;title.append(link);
  const bottom = element('div',undefined,'card-bottom');const read=element('a','阅读图解 ↗');read.href=entry.url;bottom.append(element('span',entry.date),read);
  copy.append(element('div',`${entry.show} / ${entry.topic}`,'eyebrow'),title,element('p',entry.summary),bottom,element('span',entry.slides?'文字 + 漫画幻灯片':'文字已整理 · 幻灯片待补',entry.slides?'pdf-badge':'pdf-badge text-ready'));
  card.dataset.show=entry.show;card.append(cover,copy);return card;
}
async function filter(reset = true) {
  if (!grid) return;
  const token = ++filterToken;
  if (reset) {libraryStart=0;libraryLimit=24;}
  libraryStatus.textContent='正在查找单集…';
  try {
    await loadIndex(); if(token!==filterToken)return;
    const list = searchEntries(entries,search?.value,show).filter(e=>e.ready);
    // Preserve the source's topic order for browsing; rank only actual searches.
    if (!search?.value.trim()) list.sort((a,b)=>a.order-b.order);
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
let entries = null, indexPromise = null, scope = 'all', active = -1, origin = null;
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
  setActive(-1);
}
async function loadIndex() {
  if (!indexPromise) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 30000);
    indexPromise = fetch(dialog.dataset.searchIndex, {signal:controller.signal}).then(r => {
      if (!r.ok) throw new Error('Search unavailable');
      return r.json();
    }).then(data => {
      if (!Array.isArray(data.entries)) throw new Error('Search unavailable');
      entries = data.entries; shards = data.shards || [];
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
document.querySelectorAll('[data-open-search]').forEach(button => button.addEventListener('click',openSearch));
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
query?.addEventListener('input',event => {visibleLimit = 20; render(); if(!event.isComposing) scheduleBodies();});
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
  scope = button.dataset.searchShow; visibleLimit = 20;
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
        for(const [id,text] of Object.entries(bodies)){const entry=byId.get(id);if(entry&&typeof text==='string')entry.text+=' '+text;}
        bodyLoaded.add(shard.url);
      } catch {bodyFailed.add(shard.url);} finally {clearTimeout(timer);}
      if(dialog.open)render();
    }
  }
  await Promise.all([worker(),worker(),worker()]);bodyLoading=false;
  if(dialog.open){render();scheduleBodies();}
}
