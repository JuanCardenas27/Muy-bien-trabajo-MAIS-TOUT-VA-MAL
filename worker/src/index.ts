import type { R2Bucket } from '@cloudflare/workers-types';

export interface Env {
  SITE: R2Bucket;
  ALLOWED_ORIGIN: string;
}

// Solo estas dos rutas existen; todo lo demás es 404 sin tocar el bucket.
const ROUTE_RE = /^\/(bundle\.json|d\/[0-9a-f]{32}\.bin)$/;

const BUNDLE_CACHE = 'no-cache';
const BIN_CACHE = 'public, max-age=31536000, immutable';

function cors(origin: string): Headers {
  return new Headers({ 'access-control-allow-origin': origin });
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const origin = env.ALLOWED_ORIGIN;

    if (request.method === 'OPTIONS') {
      const headers = cors(origin);
      headers.set('access-control-allow-methods', 'GET, HEAD, OPTIONS');
      headers.set('access-control-max-age', '86400');
      return new Response(null, { status: 204, headers });
    }

    if (request.method !== 'GET' && request.method !== 'HEAD') {
      return new Response('Method Not Allowed', { status: 405, headers: cors(origin) });
    }

    const path = new URL(request.url).pathname;
    if (!ROUTE_RE.test(path)) {
      return new Response('Not Found', { status: 404, headers: cors(origin) });
    }

    const object = await env.SITE.get(`site${path}`);
    if (object === null) {
      return new Response('Not Found', { status: 404, headers: cors(origin) });
    }

    const headers = cors(origin);
    headers.set('cache-control', path === '/bundle.json' ? BUNDLE_CACHE : BIN_CACHE);
    headers.set('etag', object.etag);

    if (request.headers.get('if-none-match') === object.etag) {
      return new Response(null, { status: 304, headers });
    }
    if (request.method === 'HEAD') {
      return new Response(null, { status: 200, headers });
    }
    return new Response(object.body, { status: 200, headers });
  },
};
