# ./tests/test_challenge_evidence.py
"""
Validate pure challenge-evidence classification so deny pages cannot masquerade as successful progression.
Run: `python -m pytest tests/test_challenge_evidence.py -q`.
Inputs: deterministic HTML fixtures embedded in the test module.
Outputs: assertions on visible-text extraction, deny/challenge detection, and residual-marker handling.
Side effects: none.
Operational notes: keeps regression coverage browserless and deterministic.
"""

from __future__ import annotations

from web_scraper_toolkit.diagnostics import evaluate_page_evidence, extract_visible_text
from web_scraper_toolkit.diagnostics import challenge_evidence as challenge_mod


def test_visible_text_ignores_script_and_style_noise() -> None:
    html = """
    <html>
      <head>
        <style>.x{content:'should not count';}</style>
        <script>window.payload = 'cloudflare challenge platform ' + 'word '.repeat(4000);</script>
      </head>
      <body><main><h1>Visible Title</h1><p>Only these words count.</p></main></body>
    </html>
    """
    visible = extract_visible_text(html)
    assert "Visible Title" in visible
    assert "challenge platform" not in visible


def test_deny_page_with_css_js_noise_is_not_real() -> None:
    html = """
    <html>
      <head>
        <title>Access to this page has been denied</title>
        <script>var noise = 'perimeterx ' + 'token '.repeat(5000);</script>
      </head>
      <body><div id='px-captcha'><button>Press &amp; Hold</button></div></body>
    </html>
    """
    evidence = evaluate_page_evidence(
        status=429,
        final_url="https://example.com/company/123",
        content=html,
    )
    assert evidence.likely_real_page is False
    assert evidence.deny_page_detected is True
    assert evidence.challenge_detected is True
    assert evidence.content_quality in {"deny", "challenge"}


def test_real_page_with_sparse_residual_markers_is_soft_signal_only() -> None:
    body_text = " ".join(["real visible content for the success page"] * 120)
    html = f"""
    <html>
      <head><title>Knowledge Base</title><meta property='og:title' content='Knowledge Base'></head>
      <body>
        <main>
          <article>
            <h1>Knowledge Base</h1>
            <section><p>{body_text}</p></section>
            <footer>Residual perimeterx reference in archived docs.</footer>
          </article>
        </main>
      </body>
    </html>
    """
    evidence = evaluate_page_evidence(
        status=200,
        final_url="https://example.com/docs",
        content=html,
    )
    assert evidence.likely_real_page is True
    assert evidence.marker_soft_signal_only is True
    assert evidence.challenge_detected is False
    assert evidence.progressed is True


def test_benign_url_with_challenge_word_is_not_url_only_false_positive() -> None:
    body_text = " ".join(["real visible content on a normal documentation page"] * 140)
    html = f"""
    <html>
      <head><title>Turnstile Demo Reference</title></head>
      <body>
        <main>
          <article>
            <h1>Turnstile Demo Reference</h1>
            <section><p>{body_text}</p></section>
          </article>
        </main>
      </body>
    </html>
    """
    evidence = evaluate_page_evidence(
        status=200,
        final_url="https://example.com/demo/cloudflare-turnstile-challenge",
        content=html,
    )
    assert "challenge_url" not in evidence.reason_codes
    assert evidence.likely_real_page is True
    assert evidence.challenge_detected is False


def test_real_page_requires_corroboration_for_block_reason_false_positive(
    monkeypatch,
) -> None:
    body_text = " ".join(
        ["cloudflare demo documentation content that is visibly real"] * 130
    )
    html = f"""
    <html>
      <head><title>Cloudflare Challenge demo reference</title></head>
      <body>
        <main>
          <article>
            <h1>Cloudflare Challenge demo reference</h1>
            <section><p>{body_text}</p></section>
          </article>
        </main>
      </body>
    </html>
    """
    monkeypatch.setattr(
        challenge_mod,
        "classify_bot_block",
        lambda **_: "google_unusual_traffic",
    )
    evidence = challenge_mod.evaluate_page_evidence(
        status=200,
        final_url="https://example.com/demo/cloudflare-turnstile-challenge",
        content=html,
    )
    assert evidence.likely_real_page is True
    assert evidence.challenge_detected is False
    assert evidence.progressed is True
