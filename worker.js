const BASE = '/podcast-atlas';

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === BASE) {
      url.pathname = `${BASE}/`;
      return Response.redirect(url.toString(), 308);
    }
    if (!url.pathname.startsWith(`${BASE}/`)) return new Response('Not found', { status: 404 });
    url.pathname = url.pathname.slice(BASE.length);
    let response = await env.ASSETS.fetch(new Request(url, request));
    // Only content-addressed files are immutable. Stable PDF/image URLs remain
    // revalidated so later editorial corrections cannot be hidden by old caches.
    if (response.ok && /^\/static\/[a-f0-9]{16}(?:\/|\.)/.test(url.pathname)) {
      const headers = new Headers(response.headers);
      headers.set('Cache-Control', 'public, max-age=31536000, immutable');
      response = new Response(response.body, {status: response.status, headers});
    }
    const location = response.headers.get('location');
    if (!location) return response;
    const target = new URL(location, url);
    if (target.origin !== url.origin || target.pathname.startsWith(`${BASE}/`)) return response;
    target.pathname = BASE + target.pathname;
    const headers = new Headers(response.headers);
    headers.set('location', target.toString());
    return new Response(response.body, { status: response.status, headers });
  }
};
