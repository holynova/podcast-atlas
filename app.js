const search = document.querySelector('#search');
const cards = [...document.querySelectorAll('.episode-card')];
let show = 'all';
function filter() {
  const term = search?.value.trim().toLocaleLowerCase() || '';
  let count = 0;
  cards.forEach(card => {
    const visible = (show === 'all' || card.dataset.show === show) && card.dataset.search.toLocaleLowerCase().includes(term);
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
