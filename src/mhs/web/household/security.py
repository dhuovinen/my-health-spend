"""Response security headers (PRV-08): a Content Security Policy that allows only this app's own scripts,
styles and images, so no third-party script can load and no inline script can run."""

CSP = "; ".join([
    "default-src 'none'",
    "script-src 'self'",
    "style-src 'self'",
    "img-src 'self' data:",
    "font-src 'self'",
    "connect-src 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
    "base-uri 'none'",
    "object-src 'none'",
])

HEADERS = {
    "Content-Security-Policy": CSP,
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    # same-origin, not no-referrer: under no-referrer browsers send "Origin: null" on our own form posts,
    # which the app's cross-origin check would refuse.
    "Referrer-Policy": "same-origin",
    "Permissions-Policy": "camera=(self), geolocation=(), microphone=(), interest-cohort=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
}


def apply(headers, path: str) -> None:
    """Set the security headers on a response; nothing outside /static is cached."""
    for name, value in HEADERS.items():
        headers[name] = value
    if not path.startswith("/static/"):
        headers["Cache-Control"] = "no-store"
