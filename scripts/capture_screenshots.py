"""Re-capture the screenshots/ folder from a running instance.

  pip install playwright && python -m playwright install chromium
  python scripts/capture_screenshots.py [http://localhost:8000]
"""
import os, sys
from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
OUT = os.path.join(os.path.dirname(__file__), "..", "screenshots") + os.sep
os.makedirs(OUT, exist_ok=True)
CASES = [("P0042", "04-payment-P0042-retry-recovered"), ("P0003", "05-payment-P0003-payment-link"),
         ("P0099", "06-payment-P0099-escalated"), ("P0117", "07-payment-P0117-retry-failed"),
         ("P0210", "08-payment-P0210-stale-event-blocked")]

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1280, "height": 900}, device_scale_factor=1.5)
    pg.goto(BASE); pg.wait_for_timeout(2200)
    pg.screenshot(path=OUT + "01-overview.png")
    pg.screenshot(path=OUT + "02-overview-full.png", full_page=True)
    pg.click("button.btn-ghost:has-text('Reset run')"); pg.wait_for_timeout(1200)
    pg.click("button.btn:has-text('Run recovery')"); pg.wait_for_timeout(9000)
    pg.screenshot(path=OUT + "03-run-in-progress.png")
    pg.wait_for_timeout(30000)
    for pid, name in CASES:
        pg.goto(BASE); pg.wait_for_timeout(1200)
        pg.click(f".footer a:has-text('{pid}')"); pg.wait_for_timeout(1800)
        pg.screenshot(path=OUT + name + ".png", full_page=True)
    pg.locator("button.btn-ghost", has_text="Audit trail").click(); pg.wait_for_timeout(1500)
    pg.screenshot(path=OUT + "09-audit-P0210.png", full_page=True)
    pg.fill("input.search", "P0042"); pg.wait_for_timeout(1300)
    pg.screenshot(path=OUT + "10-audit-P0042.png", full_page=True)
    pg.fill("input.search", "P0099"); pg.wait_for_timeout(1300)
    pg.click("button.chip:has-text('Policy checks')"); pg.wait_for_timeout(500)
    pg.screenshot(path=OUT + "11-audit-P0099-policy-filter.png", full_page=True)
    pg.fill("input.search", ""); pg.click("button.chip:has-text('All events')"); pg.wait_for_timeout(1300)
    pg.screenshot(path=OUT + "12-audit-global-feed.png")
    pg.goto(BASE); pg.wait_for_timeout(1500)
    pg.click("button.chip:has-text('Escalated')"); pg.wait_for_timeout(800)
    pg.mouse.wheel(0, 900); pg.wait_for_timeout(600)
    pg.screenshot(path=OUT + "13-decisions-filter-escalated.png")
    b.close()
print("wrote", OUT)
