"""Re-record docs/media/*.{webm,mp4,gif} from a running instance.

  pip install playwright && python -m playwright install chromium   # + ffmpeg on PATH
  python scripts/record_media.py all [http://localhost:8000]
  python scripts/record_media.py recovered                            # one clip
"""
import os, shutil, subprocess, sys
from playwright.sync_api import sync_playwright

CLIPS = ["full", "run", "recovered", "escalated", "stale"]
name = sys.argv[1] if len(sys.argv) > 1 else "all"
BASE = sys.argv[2] if len(sys.argv) > 2 else "http://localhost:8000"
W, H = 1280, 800
OUT = os.path.join(os.path.dirname(__file__), "..", "docs", "media")
os.makedirs(OUT, exist_ok=True)
os.makedirs("/tmp/rec", exist_ok=True)

if name == "all":
    for c in CLIPS:
        subprocess.run([sys.executable, __file__, c, BASE], check=True)
    sys.exit(0)

def ctx_for(p, b):
    d=f"/tmp/rec/{name}"; os.makedirs(d, exist_ok=True)
    return b.new_context(viewport={"width":W,"height":H}, record_video_dir=d, record_video_size={"width":W,"height":H})

def smooth_scroll(pg, px, steps=8):
    for _ in range(steps):
        pg.mouse.wheel(0, px/steps); pg.wait_for_timeout(60)

with sync_playwright() as p:
    b=p.chromium.launch(); ctx=ctx_for(p,b); pg=ctx.new_page()
    pg.goto(BASE); pg.wait_for_timeout(1500)

    if name=="full":
        pg.click("button.btn-ghost:has-text('Reset run')"); pg.wait_for_timeout(1500)
        pg.click("button.btn:has-text('Run recovery')"); pg.wait_for_timeout(9000)
        smooth_scroll(pg, 700); pg.wait_for_timeout(2500)
        pg.wait_for_timeout(26000)                      # batch finishes
        pg.goto(BASE); pg.wait_for_timeout(2000)
        smooth_scroll(pg, 500); pg.wait_for_timeout(1500)
        pg.click(".footer a:has-text('P0042')"); pg.wait_for_timeout(3500)
        smooth_scroll(pg, 400); pg.wait_for_timeout(2000)
        pg.click(".footer a:has-text('P0099')"); pg.wait_for_timeout(3500)
        smooth_scroll(pg, 400); pg.wait_for_timeout(2000)
        pg.click(".footer a:has-text('P0210')"); pg.wait_for_timeout(3000)
        pg.locator("button.btn-ghost", has_text="Audit trail").click(); pg.wait_for_timeout(1500)
        pg.fill("input.search","P0042"); pg.wait_for_timeout(3000)

    elif name=="run":
        pg.click("button.btn-ghost:has-text('Reset run')"); pg.wait_for_timeout(1200)
        pg.click("button.btn:has-text('Run recovery')"); pg.wait_for_timeout(6000)
        smooth_scroll(pg, 750); pg.wait_for_timeout(6000)
        smooth_scroll(pg, -750); pg.wait_for_timeout(24000)

    elif name=="recovered":
        pg.click(".footer a:has-text('P0042')"); pg.wait_for_timeout(2500)
        smooth_scroll(pg, 450, 12); pg.wait_for_timeout(2500)
        pg.locator("button.btn-ghost", has_text="Audit trail").click(); pg.wait_for_timeout(3500)

    elif name=="escalated":
        pg.click(".footer a:has-text('P0099')"); pg.wait_for_timeout(2500)
        smooth_scroll(pg, 450, 12); pg.wait_for_timeout(3000)
        pg.locator("button.btn-ghost", has_text="Audit trail").click(); pg.wait_for_timeout(1200)
        pg.click("button.chip:has-text('Policy checks')"); pg.wait_for_timeout(2500)

    elif name=="stale":
        pg.click(".footer a:has-text('P0210')"); pg.wait_for_timeout(4000)
        pg.click(".footer a:has-text('P0117')"); pg.wait_for_timeout(3000)
        smooth_scroll(pg, 400, 10); pg.wait_for_timeout(2500)

    ctx.close(); b.close()
    d=f"/tmp/rec/{name}"; f=[x for x in os.listdir(d) if x.endswith(".webm")][0]
    src=f"/tmp/rec/{name}.webm"; shutil.move(os.path.join(d,f), src)

mp4=os.path.join(OUT, f"{name}.mp4"); gif=os.path.join(OUT, f"{name}.gif")
subprocess.run(["ffmpeg","-y","-loglevel","error","-i",src,"-c:v","libx264","-pix_fmt","yuv420p","-crf","26","-preset","slow","-movflags","+faststart",mp4], check=True)
scale = 800 if name in ("full","run") else 900
fps = 6 if name in ("full","run") else 7
colors = 64 if name in ("full","run") else 80
subprocess.run(["ffmpeg","-y","-loglevel","error","-i",src,"-vf",
    f"fps={fps},scale={scale}:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors={colors}:stats_mode=diff[p];[b][p]paletteuse=dither=none:diff_mode=rectangle", gif], check=True)
print("ok", name, "->", mp4, gif)
