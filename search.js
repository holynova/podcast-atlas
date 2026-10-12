export function normalize(value) {
  return String(value || '').normalize('NFKC').toLocaleLowerCase().replace(/\s+/g, ' ').trim();
}
export function searchEntries(entries, query, show = 'all') {
  const tokens = normalize(query).split(' ').filter(Boolean);
  return entries.filter(e => show === 'all' || e.show === show).map(entry => {
    const title = normalize(entry.title + ' ' + entry.original_title);
    const meta = normalize(entry.show + ' ' + entry.topic + ' ' + entry.date);
    const body = normalize(entry.text);
    if (!tokens.length) return entry.ready ? {entry, score: 0} : null;
    if (!tokens.every(t => (title + ' ' + meta + ' ' + body).includes(t))) return null;
    return {entry, score: tokens.reduce((n,t) => n + (title.includes(t) ? 8 : meta.includes(t) ? 4 : 1), 0) + (entry.ready ? 2 : 0)};
  }).filter(Boolean).sort((a,b) => b.score - a.score || b.entry.date.localeCompare(a.entry.date)).map(result => result.entry);
}
