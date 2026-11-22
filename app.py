"""ImgGrab: paste a website link, get every image as one ZIP.
Run locally:  pip install -r requirements.txt && python app.py   (open http://localhost:5000)
Only use on sites you own or have permission to copy from."""
import os, re, time, uuid, shutil, hashlib, zipfile, socket, ipaddress, tempfile, html
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup
from flask import Flask, request, send_from_directory, abort, Response

app = Flask(__name__)
JOBS = os.path.join(tempfile.gettempdir(), "imggrab_jobs")
os.makedirs(JOBS, exist_ok=True)
EXT = (".jpg", ".jpeg", ".png", ".webp")
ALLOW_PRIVATE = os.environ.get("ALLOW_PRIVATE") == "1"   # for local testing only
TIME_BUDGET = int(os.environ.get("TIME_BUDGET", "90"))   # seconds per job
UA = {"User-Agent": "Mozilla/5.0 (compatible; ImgGrab/1.0)"}

def safe_url(u):
    """Block private/internal addresses so the tool can't be used to probe your network."""
    p = urlparse(u)
    if p.scheme not in ("http", "https") or not p.hostname: return False
    if ALLOW_PRIVATE: return True
    try:
        for info in socket.getaddrinfo(p.hostname, None):
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved: return False
    except Exception:
        return False
    return True

def get_html(url, js):
    if js:
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as pw:
                b = pw.chromium.launch(); pg = b.new_page()
                pg.goto(url, wait_until="networkidle", timeout=45000)
                for _ in range(12):                      # scroll so lazy images load
                    pg.mouse.wheel(0, 2500); pg.wait_for_timeout(500)
                h = pg.content(); b.close(); return h
        except Exception:
            pass                                          # fall back to plain request
    r = requests.get(url, headers=UA, timeout=20); r.raise_for_status()
    return r.text

def find_images(soup, base):
    out = []
    for t in soup.find_all(["img", "source"]):
        for a in ("src", "data-src", "data-lazy-src", "data-original"):
            if t.get(a): out.append(urljoin(base, t[a]))
        for a in ("srcset", "data-srcset"):
            if t.get(a):
                parts = [x.strip().split(" ")[0] for x in t[a].split(",") if x.strip()]
                if parts: out.append(urljoin(base, parts[-1]))
    for m in re.findall(r'url\(["\']?([^)"\']+)', str(soup)): out.append(urljoin(base, m))
    for m in soup.find_all("meta", attrs={"property": "og:image"}):
        if m.get("content"): out.append(urljoin(base, m["content"]))
    return out

def run_job(start, max_pages, min_kb, js):
    jid = uuid.uuid4().hex[:12]; d = os.path.join(JOBS, jid); os.makedirs(d)
    host = urlparse(start).netloc; t0 = time.time()
    pages, queue, seen_img, hashes, saved = set(), [start], set(), set(), []
    while queue and len(pages) < max_pages and time.time() - t0 < TIME_BUDGET:
        page = queue.pop(0)
        if page in pages or not safe_url(page): continue
        pages.add(page)
        try: soup = BeautifulSoup(get_html(page, js), "html.parser")
        except Exception: continue
        for a in soup.find_all("a", href=True):
            u = urljoin(page, a["href"]).split("#")[0]
            if urlparse(u).netloc == host and u not in pages and not u.lower().split("?")[0].endswith(EXT): queue.append(u)
        for u in find_images(soup, page):
            if time.time() - t0 > TIME_BUDGET: break
            if u in seen_img or not u.lower().split("?")[0].endswith(EXT) or not safe_url(u): continue
            seen_img.add(u)
            try: data = requests.get(u, headers=UA, timeout=25).content
            except Exception: continue
            h = hashlib.md5(data).hexdigest()
            if len(data) < min_kb * 1024 or h in hashes: continue
            hashes.add(h)
            ext = os.path.splitext(u.split("?")[0])[1].lower()
            name = f"image_{len(saved)+1:03d}{ext}"
            open(os.path.join(d, name), "wb").write(data); saved.append(name)
    with zipfile.ZipFile(os.path.join(d, "images.zip"), "w") as z:
        for n in saved: z.write(os.path.join(d, n), n)
    return jid, saved, len(pages)

def cleanup():
    for j in os.listdir(JOBS):
        p = os.path.join(JOBS, j)
        if time.time() - os.path.getmtime(p) > 3600: shutil.rmtree(p, ignore_errors=True)

CSS = """body{font-family:system-ui,sans-serif;margin:0;background:#f6f4ef;color:#14202b}
main{max-width:720px;margin:0 auto;padding:1.25rem}h1{margin:.2rem 0 .3rem}p{color:#5b6670;line-height:1.5}
form{display:grid;gap:.9rem;background:#fff;padding:1.1rem;border-radius:12px;margin-top:1rem}
label{display:grid;gap:.3rem;font-weight:600;font-size:.9rem}input,select{font:inherit;padding:.8rem;border:1px solid #d8d2c4;border-radius:8px}
button,.btn{background:#14202b;color:#fff;border:0;border-radius:8px;padding:.95rem;font:700 1rem system-ui;text-align:center;text-decoration:none;display:block}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(110px,1fr));gap:.5rem;margin:1rem 0}.grid img{width:100%;aspect-ratio:1;object-fit:cover;border-radius:8px}
.note{font-size:.85rem}"""
def page(body): return f"<!doctype html><meta name=viewport content='width=device-width,initial-scale=1'><title>ImgGrab</title><style>{CSS}</style><main>{body}</main>"

@app.get("/")
def home():
    return page("""<h1>ImgGrab</h1><p>Paste a website link. We scan its pages and give you every image as one ZIP.</p>
<form method=post action=/grab>
<label>Website link<input name=url type=url required placeholder="https://example.com"></label>
<label>Pages to scan<select name=pages><option>10</option><option selected>30</option><option>60</option></select></label>
<label>Skip images smaller than<select name=minkb><option value=15 selected>15 KB (skips icons)</option><option value=50>50 KB</option><option value=0>Keep all</option></select></label>
<label>Site loads photos with JavaScript?<select name=js><option value=0>No (faster)</option><option value=1>Yes (slower, needs Playwright)</option></select></label>
<button>Grab images</button></form>
<p class=note>Only use this on websites you own or have permission to copy from.</p>""")

@app.post("/grab")
def grab():
    cleanup()
    url = request.form.get("url", "").strip()
    if not safe_url(url): return page("<h1>Link not allowed</h1><p>Enter a public http(s) website address.</p><a class=btn href=/>Back</a>"), 400
    jid, saved, npages = run_job(url, min(int(request.form.get("pages", 30)), 60), int(request.form.get("minkb", 15)), request.form.get("js") == "1")
    if not saved: return page(f"<h1>No images found</h1><p>Scanned {npages} page(s). Try the JavaScript option or a different page.</p><a class=btn href=/>Back</a>")
    thumbs = "".join(f"<img loading=lazy src='/f/{jid}/{n}' alt=''>" for n in saved)
    return page(f"<h1>{len(saved)} images found</h1><p>Scanned {npages} page(s).</p><a class=btn href='/f/{jid}/images.zip' download>Download ZIP</a><div class=grid>{thumbs}</div><a class=btn href=/>Scan another site</a>")

@app.get("/f/<jid>/<name>")
def files(jid, name):
    if not re.fullmatch(r"[0-9a-f]{12}", jid) or not re.fullmatch(r"[\w.]+", name): abort(404)
    return send_from_directory(os.path.join(JOBS, jid), name)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
