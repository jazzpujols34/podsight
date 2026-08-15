// Vercel Edge Middleware - Basic Auth gate for the private archive at /admin/.
//
// /admin/ is the hub listing every 兆華與股惑仔 episode; /admin/<ep>/ is one
// episode. The whole namespace is private: 版權 caution, excluded from the
// sitemap and disallowed in robots.txt (see generate_public_site.py).
// Crawlers get 401 here and never reach the HTML at all.
//
// Setup: set ZHAOHUA_PASSWORD in the Vercel project's Environment Variables,
// then redeploy. Any username works; only the password is checked.

export const config = {
  matcher: ['/admin', '/admin/:path*'],
}

const REALM = 'PodSight archive'

function unauthorized(message) {
  return new Response(message, {
    status: 401,
    headers: {
      'WWW-Authenticate': `Basic realm="${REALM}", charset="UTF-8"`,
      'Content-Type': 'text/plain; charset=utf-8',
      'Cache-Control': 'no-store',
      'X-Robots-Tag': 'noindex, nofollow',
    },
  })
}

// Constant-time compare so the response time does not leak the password.
function matches(a, b) {
  if (a.length !== b.length) return false
  let diff = 0
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i)
  return diff === 0
}

export default function middleware(request) {
  const expected = process.env.ZHAOHUA_PASSWORD

  // Fail closed. An unset variable must not silently publish the archive.
  if (!expected) return unauthorized('Archive is not configured.')

  const header = request.headers.get('authorization') || ''
  const [scheme, encoded] = header.split(' ')

  if (scheme === 'Basic' && encoded) {
    let decoded = ''
    try {
      decoded = atob(encoded)
    } catch {
      return unauthorized('Malformed credentials.')
    }
    const separator = decoded.indexOf(':')
    if (separator !== -1 && matches(decoded.slice(separator + 1), expected)) {
      return // continue to the static page
    }
  }

  return unauthorized('Authentication required.')
}
