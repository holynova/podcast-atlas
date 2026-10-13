import {normalize, searchEntries} from './search.js';
const search = document.querySelector('#search');
const cards = [...document.querySelectorAll('.episode-card')];
let show = 'all';
function filter() {
  const tokens = normalize(search?.value).split(' ').filter(Boolean);
  let count = 0;
  cards.forEach(card => {
    const visible = (show === 'all' || card.dataset.show === show) && tokens.every(t => normalize(card.dataset.search).includes(t));
    card.hidden = !visible;
    if (visible) count++;
  });
  const empty = document.querySelector('#empty');
  if (empty) empty.hidden = count > 0;
}
search?.addEventListener('input', filter);
document.querySelectorAll('[data-filter]').forEach(button => button.addEventListener('click', () => {
  show = button.dataset.filter;
  document.querySelectorAll('[data-filter]').forEach(item => {item.classList.toggle('active', item === button); item.setAttribute('aria-pressed', String(item === button));});
  filter();
}));

const dialog = document.querySelector('#command-search');
const query = dialog?.querySelector('#command-query');
const results = dialog?.querySelector('#command-results');
const status = dialog?.querySelector('#command-status');
const retry = dialog?.querySelector('.command-retry');
let entries = null, indexPromise = null, scope = 'all', active = -1, origin = null;
let matches = [], visibleLimit = 20;
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
      entries = data.entries;
    }).catch(error => {indexPromise = null; throw error;}).finally(() => clearTimeout(timer));
  }
  retry.hidden = true; status.textContent = '正在加载搜索目录…';
  try {await indexPromise; if (dialog.open) render();}
  catch {if (dialog.open) {status.textContent = '搜索目录暂时没加载好，请检查网络后重试。'; retry.hidden = false;}}
}
function openSearch() {
  if (!dialog || dialog.open) return;
  origin = document.activeElement;
  dialog.showModal(); query.setAttribute('aria-expanded','true'); query.focus();
  visibleLimit = 20;
  if (entries) render(); else loadIndex();
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
query?.addEventListener('input',() => {visibleLimit = 20; render();});
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
  render(); query.focus();
}));
retry?.addEventListener('click',loadIndex);
dialog?.querySelector('[data-search-more]').addEventListener('click',() => {visibleLimit += 20; render(); query.focus();});
