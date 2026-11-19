// Cloudflare Pages middleware: Markdown for agents + AI bot logging (D1).
// Runs on every request to the Pages project.

const BOTS = [
  // [regex on User-Agent, bot name, kind]
  [/GPTBot/i, 'GPTBot', 'ai-training'],
  [/OAI-SearchBot/i, 'OAI-SearchBot', 'ai-search'],
  [/ChatGPT-User/i, 'ChatGPT-User', 'ai-assistant'],
  [/ClaudeBot/i, 'ClaudeBot', 'ai-training'],
  [/Claude-SearchBot/i, 'Claude-SearchBot', 'ai-search'],
  [/Claude-User/i, 'Claude-User', 'ai-assistant'],
  [/PerplexityBot/i, 'PerplexityBot', 'ai-search'],
  [/Perplexity-User/i, 'Perplexity-User', 'ai-assistant'],
  [/Google-CloudVertexBot|Gemini/i, 'Gemini', 'ai-assistant'],
  [/Applebot-Extended/i, 'Applebot-Extended', 'ai-training'],
  [/Meta-ExternalAgent|meta-externalfetcher/i, 'Meta-AI', 'ai-training'],
  [/Bytespider/i, 'Bytespider', 'ai-training'],
  [/CCBot/i, 'CCBot', 'ai-training'],
  [/Amazonbot/i, 'Amazonbot', 'ai-training'],
  [/DuckAssistBot/i, 'DuckAssistBot', 'ai-assistant'],
  [/MistralAI-User/i, 'MistralAI-User', 'ai-assistant'],
  [/Googlebot/i, 'Googlebot', 'search'],
  [/bingbot/i, 'Bingbot', 'search'],
  [/coccocbot/i, 'CocCocBot', 'search'],
  [/Applebot/i, 'Applebot', 'search'],
  [/Zalo/i, 'Zalo', 'link-preview'],
  [/facebookexternalhit|FacebookBot/i, 'Facebook', 'link-preview'],
  [/HeadlessChrome|Playwright|python-urllib|curl|wget/i, 'Tool', 'tool'],
];

function classify(ua) {
  for (const [re, name, kind] of BOTS) if (re.test(ua)) return { bot: name, kind };
  return { bot: null, kind: 'human' };
}

const LOGGED = /^\/(index\.html|index\.md|llms\.txt|robots\.txt|sitemap\.xml)?$/;

export async function onRequest(context) {
  const { request, env, next, waitUntil } = context;
  const url = new URL(request.url);
  const ua = request.headers.get('user-agent') || '';
  const accept = request.headers.get('accept') || '';
  const wantsMd = /text\/markdown/i.test(accept);
  const isHome = url.pathname === '/' || url.pathname === '/index.html';

  let response, served;
  if (isHome && wantsMd) {
    // Content negotiation: same URL, Markdown body for agents that ask for it
    const md = await env.ASSETS.fetch(new URL('/index.md', url));
    const body = await md.text();
    response = new Response(body, {
      headers: {
        'content-type': 'text/markdown; charset=utf-8',
        'vary': 'Accept',
        'cache-control': 'public, max-age=300',
        'x-markdown-tokens': String(Math.round(body.length / 3.2)),
      },
    });
    served = 'markdown';
  } else {
    response = await next();
    if (isHome) {
      response = new Response(response.body, response);
      response.headers.append('vary', 'Accept');
      response.headers.set('link', '</index.md>; rel="alternate"; type="text/markdown"');
    }
    served = response.headers.get('content-type')?.split(';')[0] || 'unknown';
  }

  if (env.DB && LOGGED.test(url.pathname)) {
    const { bot, kind } = classify(ua);
    waitUntil(
      env.DB.prepare(
        'INSERT INTO hits (path, bot, kind, wants_markdown, served, country, ua) VALUES (?, ?, ?, ?, ?, ?, ?)'
      ).bind(url.pathname, bot, kind, wantsMd ? 1 : 0, served,
             request.cf?.country || null, ua.slice(0, 300)).run().catch(() => {})
    );
  }
  return response;
}
