import base64, io, json, os, uuid, zipfile
import flet as ft
from PIL import Image, ImageOps

DIR = os.getenv("FLET_APP_STORAGE_DATA") or os.path.join(os.path.expanduser("~"), ".mustamsakat")
os.makedirs(DIR, exist_ok=True)
DBF = os.path.join(DIR, "db.json")
BG, SU, MU, MINT = "#0F1419", "#1A222B", "#9AA7B2", "#5EEAD4"
COL = ["#5EEAD4", "#C4B5FD", "#F5B454", "#93C5FD", "#F9A8D4"]
# (الاسم, العرض ملم, الارتفاع ملم, الأوجه, ألوان البطاقة)  -- عدّل الأبعاد حسب مستمسكاتك الحقيقية
T = [("الهوية الوطنية", 85.6, 54, ["وجه", "ظهر"], ("#5EEAD4", "#2DD4BF")),
     ("بطاقة السكن", 85.6, 54, ["وجه", "ظهر"], ("#F5B454", "#F59E0B")),
     ("شهادة الجنسية", 148, 210, ["صفحة"], ("#C4B5FD", "#A78BFA")),
     ("جواز السفر", 125, 88, ["صفحة 1", "صفحة 2"], ("#93C5FD", "#60A5FA")),
     ("البطاقة التموينية", 148, 105, ["صفحة 1", "صفحة 2"], ("#BEF264", "#84CC16")),
     ("إجازة السوق", 85.6, 54, ["وجه", "ظهر"], ("#F9A8D4", "#EC4899")),
     ("مستمسك آخر", 85.6, 54, ["وجه", "ظهر"], ("#CBD5E1", "#94A3B8")),
     ("سنوية السيارة", 85.6, 54, ["وجه", "ظهر"], ("#FCD34D", "#F59E0B")),
     ("هوية الدائرة", 54, 85.6, ["وجه", "ظهر"], ("#67E8F9", "#06B6D4")),  # طولي
     ("ورقة A4 (مستمسك آخر)", 210, 297, ["صفحة 1", "صفحة 2"], ("#E2E8F0", "#94A3B8")),
     ("صورة شخصية 3×4 سم", 30, 40, ["صورة"], ("#FDE68A", "#FBBF24")),
     ("صورة شخصية 4×6 سم", 40, 60, ["صورة"], ("#FDBA74", "#FB923C"))]
PHT = {10, 11}  # الصور الشخصية تذهب تلقائياً إلى ورقة الصور
# حجم الورق (العرض, الارتفاع, الهامش, المسافة بين العناصر, توسيط) بالملم. راجع مقاس ورق طابعتك وعدّل الهامش إن لزم
PAPERS = {"A4": (210, 297, 10, 4, False),
          "Selphy بوستكارد 100×148": (100, 148, 3, 0, True),
          "Selphy L 89×119": (89, 119, 3, 0, True),
          "Selphy بطاقة 54×86": (54, 86, 3, 0, True)}


def load():
    try:
        return json.load(open(DBF, encoding="utf-8"))
    except Exception:
        return {"people": [{"id": uuid.uuid4().hex[:8], "name": "أنا", "color": COL[0], "photo": ""}], "docs": []}


def import_img(src, aspect, width):
    """يقص الصورة من الوسط على نسبة المستمسك ويحفظها JPEG داخل التطبيق."""
    im = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
    w, h = im.size
    if w / h > aspect:
        nw = int(h * aspect)
        im = im.crop(((w - nw) // 2, 0, (w - nw) // 2 + nw, h))
    else:
        nh = int(w / aspect)
        im = im.crop((0, (h - nh) // 2, w, (h - nh) // 2 + nh))
    im = im.resize((width, round(width / aspect)))
    name = uuid.uuid4().hex[:10] + ".jpg"
    im.save(os.path.join(DIR, name), quality=90)
    return {"img": name, "pw": im.width, "ph": im.height}


def rows(its, W, gap):
    """يرتب مجموعة بصفوف بعرض W ويرجع (المواضع النسبية، الارتفاع، العرض المستخدم)."""
    pos, x, y, rh, wd = [], 0, 0, 0, 0
    for it in its:
        if x > 0 and x + it["w"] > W + 1e-6:
            y, x, rh = y + rh + gap, 0, 0
        pos.append((x, y))
        wd = max(wd, x + it["w"])
        x += it["w"] + gap
        rh = max(rh, it["h"])
    return pos, (y + rh if its else 0), wd


def face(top, bot, mirror, pp):
    """وجه واحد من الورقة: «فوق» يبدأ من الأعلى و«تحت» يلتصق بالأسفل.
    الخلف يُرتَّب معكوساً (من اليسار) لينطبق خلف الوجه عند الطباعة على الوجهين."""
    PW, PH, mg, gap, ctr = pp
    W, Hh = PW - 2 * mg, PH - 2 * mg
    al = top + bot
    if any(i["w"] > W + 1e-6 or i["h"] > Hh + 1e-6 for i in al):  # مستمسك بحجم الورقة كاملة
        if len(al) > 1:
            return None
        i = al[0]
        return [{**i, "x": (PW - i["w"]) / 2, "y": (PH - i["h"]) / 2}]
    (tp, th, tw), (bp, bh, bw) = rows(top, W, gap), rows(bot, W, gap)
    if len(al) > 1 and (th > Hh + 1e-6 or bh > Hh + 1e-6 or (top and bot and th + bh + gap > Hh)):
        return None
    out = []
    for grp, pos, y0, wd in ((top, tp, mg, tw), (bot, bp, PH - mg - bh, bw)):
        span = wd if ctr else W
        base = mg + (W - wd) / 2 if ctr else mg
        for i, (x, y) in zip(grp, pos):
            out.append({**i, "x": base + x if mirror else base + span - x - i["w"], "y": y0 + y})
    return out


def layout(its, pp):
    """يوزع المستمسكات على أوراق: لكل مستمسك وجه/خلف الورقة وفوق/تحت. يرجع (الصفحات، أسماؤها)."""
    sheets_ = []

    def new():
        sheets_.append([[[], []], [[], []]])  # [وجه, خلف][فوق, تحت]
        return sheets_[-1]

    cur = new()
    for it in its:
        f, z = it["f"], it["z"]
        cur[f][z].append(it)
        if face(cur[f][0], cur[f][1], f == 1, pp) is None:
            cur[f][z].pop()
            cur = new()
            cur[f][z].append(it)
    pages, labels = [], []
    for n, sh in enumerate(sheets_, 1):
        for f in (0, 1):
            if sh[f][0] or sh[f][1] or (f == 0 and (sh[1][0] or sh[1][1])):
                pages.append(face(sh[f][0], sh[f][1], f == 1, pp) or [])
                labels.append(f"ورقة {n} · {'الوجه' if f == 0 else 'الخلف'}")
    return pages, labels


def mkpdf(pages, pw=210, ph=297):
    """PDF بحجم A4، كل صورة بأبعادها الحقيقية بالملم، بدون أي إضافات."""
    k = 72 / 25.4
    out, offs = bytearray(b"%PDF-1.4\n"), {}
    ims = [it for p in pages for it in p]
    for n, it in enumerate(ims):
        it["n"] = n
    I = len(ims)

    def ob(i, body):
        offs[i] = len(out)
        out.extend(f"{i} 0 obj\n".encode() + body + b"\nendobj\n")

    f = lambda v: f"{v * k:.2f}"
    ob(1, b"<</Type/Catalog/Pages 2 0 R>>")
    kids = " ".join(f"{3 + I + 2 * i} 0 R" for i in range(len(pages)))
    ob(2, f"<</Type/Pages/Count {len(pages)}/Kids[{kids}]>>".encode())
    for n, it in enumerate(ims):
        d = open(it["path"], "rb").read()
        ob(3 + n, (f"<</Type/XObject/Subtype/Image/Width {it['pw']}/Height {it['ph']}/ColorSpace/DeviceRGB"
                   f"/BitsPerComponent 8/Filter/DCTDecode/Length {len(d)}>>\nstream\n").encode() + d + b"\nendstream")
    for i, p in enumerate(pages):
        pid = 3 + I + 2 * i
        xo = " ".join(f"/I{it['n']} {3 + it['n']} 0 R" for it in p)
        cs = "\n".join(f"q {f(it['w'])} 0 0 {f(it['h'])} {f(it['x'])} {f(ph - it['y'] - it['h'])} cm /I{it['n']} Do Q"
                       for it in p).encode()
        ob(pid, f"<</Type/Page/Parent 2 0 R/MediaBox[0 0 {f(pw)} {f(ph)}]/Resources<</XObject<<{xo}>>>>/Contents {pid + 1} 0 R>>".encode())
        ob(pid + 1, f"<</Length {len(cs)}>>\nstream\n".encode() + cs + b"\nendstream")
    N, xs = 3 + I + 2 * len(pages), len(out)
    out.extend(f"xref\n0 {N}\n0000000000 65535 f \n".encode())
    for i in range(1, N):
        out.extend(f"{offs[i]:010d} 00000 n \n".encode())
    out.extend(f"trailer\n<</Size {N}/Root 1 0 R>>\nstartxref\n{xs}\n%%EOF".encode())
    return bytes(out)


def render_jpg(items_, pp, dpi=300):
    """ورقة الطباعة كصورة JPG بدقة dpi وبالحجم الحقيقي (للطباعة من المعرض أو من تطبيق الطابعة)."""
    k = dpi / 25.4
    im = Image.new("RGB", (round(pp[0] * k), round(pp[1] * k)), "white")
    for it in items_:
        a = Image.open(it["path"]).convert("RGB").resize((max(1, round(it["w"] * k)), max(1, round(it["h"] * k))), Image.LANCZOS)
        im.paste(a, (round(it["x"] * k), round(it["y"] * k)))
    b = io.BytesIO()
    im.save(b, "JPEG", quality=95, dpi=(dpi, dpi))
    return b.getvalue()


def main(page: ft.Page):
    page.title = "محفظة المستمسكات"
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = BG
    page.padding = 0
    db = load()
    S = {"tab": 0, "pid": db["people"][0]["id"], "sel": [], "sh": "pdf", "del": None, "pl": {}, "gr": {}, "cp": {}, "pa": ["A4", "Selphy بوستكارد 100×148"], "mg": None, "gp": None}
    cache = {}
    fp, fs = ft.FilePicker(), ft.FilePicker()
    page.overlay.extend([fp, fs])
    R, END, CEN = ft.TextAlign.RIGHT, ft.CrossAxisAlignment.END, ft.CrossAxisAlignment.CENTER

    def persist():
        json.dump(db, open(DBF, "w", encoding="utf-8"), ensure_ascii=False)

    def toast(m):
        page.open(ft.SnackBar(ft.Text(m, text_align=R)))

    def img64(n):
        if n not in cache:
            cache[n] = base64.b64encode(open(os.path.join(DIR, n), "rb").read()).decode()
        return cache[n]

    P = lambda i: next((p for p in db["people"] if p["id"] == i), None)
    Dd = lambda i: next((d for d in db["docs"] if d["id"] == i), None)
    txt = lambda s, **k: ft.Text(s, text_align=R, **k)
    row = lambda *c, **k: ft.Row(list(c)[::-1], alignment=ft.MainAxisAlignment.END, vertical_alignment=CEN, **k)

    def btn(t, f, primary=False, **k):
        return ft.ElevatedButton(t, on_click=f, bgcolor=MINT if primary else SU, color=BG if primary else "#F2F5F7", **k)

    def pick(cb, exts=None):
        fp.on_result = lambda e: cb(e.files[0].path) if e.files else None
        if exts:
            fp.pick_files(allowed_extensions=exts)
        else:
            fp.pick_files(file_type=ft.FilePickerFileType.IMAGE)

    pending = {}

    def fs_done(e):
        if e.path and pending.get("d"):  # على الكمبيوتر التطبيق هو الذي يكتب الملف بالمكان المختار
            try:
                open(e.path, "wb").write(pending["d"])
                toast("تم الحفظ: " + e.path)
            except Exception:
                pass

    fs.on_result = fs_done

    def put(name, data):
        """يحفظ الملف بمجلد التنزيلات (إن أمكن) وبمجلد التطبيق، ويعرض المكان، مع زر لاختيار مكان آخر."""
        ex = os.path.join(DIR, "exports")
        os.makedirs(ex, exist_ok=True)
        saved = os.path.join(ex, name)
        open(saved, "wb").write(data)
        public = None
        for base in ("/storage/emulated/0/Download", "/sdcard/Download", os.path.join(os.path.expanduser("~"), "Downloads")):
            try:
                if os.path.isdir(base):
                    public = os.path.join(base, name)
                    open(public, "wb").write(data)
                    break
            except Exception:
                public = None
        pending.update(d=data)

        def choose(e):
            page.close(dg)
            try:
                fs.save_file(dialog_title="اختر مكان الحفظ", file_name=name, src_bytes=data)
            except Exception:
                toast("تعذر فتح نافذة اختيار المكان")

        body_ = [txt(name, weight="bold"), txt(public or saved, size=12, color=MU, selectable=True)]
        body_.append(txt("المكان: مجلد التنزيلات (Download)" if public else
                         "تعذر الحفظ بمجلد التنزيلات. الملف داخل مجلد التطبيق، فاضغط «اختيار مكان الحفظ».", size=12))
        dg = ft.AlertDialog(title=txt("تم حفظ الملف" if public else "تم حفظ نسخة داخل التطبيق"),
                            content=ft.Column(body_, tight=True, horizontal_alignment=END),
                            actions=[ft.TextButton("اختيار مكان الحفظ", on_click=choose), ft.TextButton("تم", on_click=lambda e: page.close(dg))])
        page.open(dg)

    def export(files, zname="documents.zip"):
        """ملف واحد يُحفظ مباشرة، وأكثر من ملف يُحفظ داخل zip."""
        if len(files) == 1:
            n, d = next(iter(files.items()))
            return put(n, d)
        z = io.BytesIO()
        with zipfile.ZipFile(z, "w") as f:
            for n, d in files.items():
                f.writestr(n, d)
        put(zname, z.getvalue())

    def items():
        out = []
        for k in S["sel"]:
            i, n = k.split(":")
            d = Dd(i)
            if d and d["sides"][int(n)].get("img"):
                s = d["sides"][int(n)]
                pl = S["pl"].setdefault(k, [0, 0])  # [وجه=0/خلف=1, فوق=0/تحت=1]
                g = S["gr"].get(k, 1 if d["ti"] in PHT else 0)  # 0 ورقة المستمسكات، 1 ورقة الصور
                out.append({"f": 0 if g else pl[0], "z": 0 if g else pl[1], "g": g, "c": S["cp"].get(k, 1), "k": k, "d": d, "s": s, "p": P(d["pid"]), "w": d["w"], "h": d["w"] * s["ph"] / s["pw"],
                            "path": os.path.join(DIR, s["img"]), "pw": s["pw"], "ph": s["ph"]})
        return out

    def av(p, z=56, ring=False):
        if p.get("photo"):
            inner = ft.Image(src_base64=img64(p["photo"]), width=z, height=z, fit=ft.ImageFit.COVER, border_radius=z / 2)
        else:
            inner = ft.Container(ft.Text(p["name"][:1], weight="bold", color=BG, size=z * .42), width=z, height=z,
                                 bgcolor=p["color"], border_radius=z / 2, alignment=ft.alignment.center)
        return ft.Container(inner, border=ft.border.all(2, MINT) if ring else None, border_radius=z, padding=2 if ring else 0)

    # ---------- الشاشات ----------
    def tg(k):
        S["sel"].remove(k) if k in S["sel"] else S["sel"].append(k)
        render()

    def go(t):
        S["tab"] = t
        render()

    def view(title, ims):
        """عرض المستمسك كبيراً (تكبير وتحريك بالأصابع) لنقل المعلومات منه."""
        w = min((page.width or 400) - 70, 400)
        col = [ft.Column([txt(l, size=12, color=MU), ft.InteractiveViewer(
            ft.Image(src_base64=img64(n), width=w, height=w * ph / pw, fit=ft.ImageFit.FILL), min_scale=1, max_scale=6),
            ft.TextButton("حفظ كصورة JPG", on_click=lambda e, n=n: put(n, open(os.path.join(DIR, n), "rb").read()))],
            horizontal_alignment=CEN) for l, n, pw, ph in ims]
        dg = ft.AlertDialog(title=txt(title), content=ft.Column(col, scroll=ft.ScrollMode.AUTO, tight=True),
                            actions=[ft.TextButton("إغلاق", on_click=lambda e: page.close(dg))])
        page.open(dg)

    def pp_of(g):
        PW, PH, mg, gap, ctr = PAPERS[S["pa"][g]]
        if g and S["mg"] is not None:
            mg = S["mg"]
        if g and S["gp"] is not None:
            gap = S["gp"]
        return PW, PH, mg, gap, ctr

    def sheets(its):
        """[(مجموعة, صفحات, أسماء, مقاس)] : 0 ورقة المستمسكات، 1 ورقة الصور (مع تكرار النسخ)."""
        out = []
        for g in (0, 1):
            sel = [{**i} for i in its if i["g"] == g for _ in range(i["c"])]
            if sel:
                pp = pp_of(g)
                pages, labels = layout(sel, pp)
                out.append((g, pages, [l.replace("ورقة ", "ورقة الصور ").replace(" · الوجه", "") if g else l for l in labels], pp))
        return out

    def setnum(k, v):
        try:
            S[k] = max(0.0, float(v))
        except Exception:
            pass
        render()

    def setgr(k, g):
        S["gr"][k] = 1 - g
        render()

    def setcp(k, d):
        S["cp"][k] = max(1, S["cp"].get(k, 1) + d)
        render()

    def fill(k):
        it = next(i for i in items() if i["k"] == k)
        pp, n = pp_of(it["g"]), 1
        while n < 80 and len(layout([{**it} for _ in range(n + 1)], pp)[0]) == 1:
            n += 1
        S["cp"][k] = n
        render()

    def save_pdf(g):
        for gg, pages, labels, pp in sheets(items()):
            if gg == g:
                put("photos.pdf" if g else "documents.pdf", mkpdf(pages, pp[0], pp[1]))

    def save_jpg(g):
        files = {}
        for gg, pages, labels, pp in sheets(items()):
            if gg == g:
                for n, pg in enumerate(pages, 1):
                    files[f"{'photos' if g else 'documents'}-{n}.jpg"] = render_jpg(pg, pp)
        if files:
            export(files, "photos-jpg.zip" if g else "documents-jpg.zip")

    def flip(k, i):
        S["pl"][k][i] ^= 1
        render()

    def mv(k, d):
        i, j = S["sel"].index(k), S["sel"].index(k) + d
        if 0 <= j < len(S["sel"]):
            S["sel"][i], S["sel"][j] = S["sel"][j], S["sel"][i]
        render()

    def rm_doc(i):
        if S["del"] != i:
            S["del"] = i
            return render()
        db["docs"] = [d for d in db["docs"] if d["id"] != i]
        S["sel"] = [k for k in S["sel"] if not k.startswith(i + ":")]
        S["del"] = None
        persist()
        render()

    def card(d):
        t = T[d["ti"]]
        chips = []
        for i, s in enumerate(d["sides"]):
            if s.get("img"):
                k = f"{d['id']}:{i}"
                on = k in S["sel"]
                chips.append(ft.ElevatedButton(("✓ " if on else "") + s["l"], on_click=lambda e, k=k: tg(k),
                                               bgcolor=BG if on else "#260F1419", color=MINT if on else BG))
        return ft.Container(
            ft.Column([row(ft.Column([txt(d["name"], size=19, weight="bold", color=BG), txt(f"العرض {d['w']} ملم", size=13, color=BG)],
                                     spacing=0, horizontal_alignment=END, expand=True), ft.Row(chips[::-1], wrap=True)),
                       ft.Row([ft.TextButton("تأكيد الحذف؟" if S["del"] == d["id"] else "حذف", on_click=lambda e, i=d["id"]: rm_doc(i),
                                             style=ft.ButtonStyle(color=BG)),
                               ft.TextButton("عرض", on_click=lambda e, d=d: view(d["name"], [(s["l"], s["img"], s["pw"], s["ph"]) for s in d["sides"] if s.get("img")]),
                                             style=ft.ButtonStyle(color=BG))])], horizontal_alignment=END),
            gradient=ft.LinearGradient(colors=list(t[4]), begin=ft.alignment.top_left, end=ft.alignment.bottom_right),
            border_radius=24, padding=16)

    def home():
        p = P(S["pid"])
        cs = [row(ft.Column([txt(f"محفظة «{p['name']}»", size=13, color=MU), txt("مستمسكاتي", size=30, weight="bold")],
                            spacing=0, horizontal_alignment=END, expand=True), btn("+ مستمسك", lambda e: doc_dlg(), True))]
        strip = []
        for q in db["people"]:
            c = sum(1 for k in S["sel"] if (Dd(k.split(":")[0]) or {}).get("pid") == q["id"])
            strip.append(ft.GestureDetector(
                ft.Column([av(q, 56, q["id"] == p["id"]), txt(q["name"] + (f" · {c}" if c else ""), size=12, color=MU)],
                          horizontal_alignment=CEN, spacing=4), on_tap=lambda e, i=q["id"]: pk(i)))
        strip.append(ft.GestureDetector(ft.Column([
            ft.Container(ft.Text("+", size=24, color=MU), width=56, height=56, border_radius=28, border=ft.border.all(1.5, MU),
                         alignment=ft.alignment.center), txt("إضافة", size=12, color=MU)], horizontal_alignment=CEN, spacing=4),
            on_tap=lambda e: person_dlg(None)))
        cs.append(ft.Row(strip[::-1], scroll=ft.ScrollMode.AUTO, alignment=ft.MainAxisAlignment.END))
        if S["sel"]:
            n = len({(Dd(k.split(":")[0]) or {}).get("pid") for k in S["sel"]})
            cs.append(row(txt(f"{len(S['sel'])} محددة · {n} {'أشخاص' if n > 1 else 'شخص'}", weight="bold"),
                          btn("ترتيب على A4", lambda e: go(1), True)))
        ds = [d for d in db["docs"] if d["pid"] == p["id"]]
        cs += [card(d) for d in ds] or [txt("لا توجد مستمسكات بعد. اضغط «+ مستمسك».", color=MU)]
        return cs

    def prt():
        its = items()
        if not its:
            return [txt("الطباعة", size=30, weight="bold"), txt("حدد مستمسكات من الصفحة الرئيسية أولاً", color=MU)]
        cs = [txt("معاينة كما ستُطبع", size=13, color=MU), txt("ترتيب الصفحة", size=30, weight="bold"),
              txt("اضغط على أي مستمسك بالمعاينة لعرضه كبيراً ونقل معلوماته.", size=12, color=MU)]
        NUM = ft.KeyboardType.NUMBER
        for g, pages, labels, pp in sheets(its):
            sc = min(2.0, ((page.width or 400) - 40) / pp[0])
            cs.append(ft.Dropdown(label="ورقة الصور" if g else "ورقة المستمسكات", value=S["pa"][g],
                                  options=[ft.dropdown.Option(n) for n in PAPERS],
                                  on_change=lambda e, g=g: (S["pa"].__setitem__(g, e.control.value), render())))
            if g:
                cs.append(ft.Row([ft.TextField(label="المسافة بين الصور (ملم)", value=str(pp[3]), expand=True, keyboard_type=NUM,
                                               on_blur=lambda e: setnum("gp", e.control.value)),
                                  ft.TextField(label="هامش الورقة (ملم)", value=str(pp[2]), expand=True, keyboard_type=NUM,
                                               on_blur=lambda e: setnum("mg", e.control.value))]))
            for pg, lb in zip(pages, labels):
                cs.append(txt(lb, size=13, weight="bold"))
                cs.append(ft.Container(ft.Stack([ft.Container(
                    ft.Image(src_base64=img64(it["s"]["img"]), width=it["w"] * sc, height=it["h"] * sc, fit=ft.ImageFit.FILL),
                    left=it["x"] * sc, top=it["y"] * sc,
                    on_click=lambda e, it=it: view(it["d"]["name"], [(it["s"]["l"], it["s"]["img"], it["pw"], it["ph"])])) for it in pg],
                    width=pp[0] * sc, height=pp[1] * sc), bgcolor="white"))
            cs.append(row(btn("حفظ PDF", lambda e, g=g: save_pdf(g), True), btn("حفظ JPG", lambda e, g=g: save_jpg(g), True)))
        cs.append(txt("✓ الحجم الحقيقي · المستمسك فقط بدون إطار أو علامات. خلف الورقة مرتّب معكوساً لينطبق خلف الوجه "
                      "عند الطباعة على الوجهين (قلب على الحافة الطويلة).", size=12, color=MU))
        for it in its:
            k, g = it["k"], it["g"]
            ctl = [btn("ورقة الصور" if g else "ورقة المستمسكات", lambda e, k=k, g=g: setgr(k, g)),
                   ft.IconButton(ft.Icons.REMOVE, on_click=lambda e, k=k: setcp(k, -1)), ft.Text(f"{it['c']} نسخة"),
                   ft.IconButton(ft.Icons.ADD, on_click=lambda e, k=k: setcp(k, 1)), btn("ملء الورقة", lambda e, k=k: fill(k))]
            pos = [] if g else [btn("وجه الورقة" if it["f"] == 0 else "خلف الورقة", lambda e, k=k: flip(k, 0)),
                                btn("فوق" if it["z"] == 0 else "تحت", lambda e, k=k: flip(k, 1))]
            cs.append(ft.Container(ft.Column([
                row(av(it["p"], 30), txt(f"{it['d']['name']} · {it['s']['l']} · {it['p']['name']}", size=14, expand=True),
                    ft.IconButton(ft.Icons.ARROW_UPWARD, on_click=lambda e, k=k: mv(k, -1)),
                    ft.IconButton(ft.Icons.ARROW_DOWNWARD, on_click=lambda e, k=k: mv(k, 1)),
                    ft.IconButton(ft.Icons.CLOSE, on_click=lambda e, k=k: tg(k))),
                row(*ctl, wrap=True)] + ([row(*pos)] if pos else []), horizontal_alignment=END, spacing=2),
                bgcolor=SU, border_radius=16, padding=ft.padding.symmetric(horizontal=12, vertical=6)))
        return cs

    def shr():
        its = items()
        if not its:
            return [txt("مشاركة", size=30, weight="bold"), txt("حدد مستمسكات من الصفحة الرئيسية أولاً", color=MU)]
        rg = ft.RadioGroup(value=S["sh"], on_change=lambda e: S.update(sh=e.control.value), content=ft.Column([
            ft.Radio(value="pdf", label="ملفات PDF جاهزة للطباعة (مستمسكات وصور بالحجم الحقيقي)"),
            ft.Radio(value="sheet", label="ورقة الطباعة كصورة JPG (للطباعة من المعرض أو تطبيق الطابعة)"),
            ft.Radio(value="img", label="كل مستمسك أو صورة كملف JPG"),
            ft.Radio(value="pp", label="ملف PDF لكل شخص")]))

        def do(e):
            m, its = S["sh"], items()
            files = {}
            if m == "pdf":
                for g, pages, labels, pp in sheets(its):
                    files["photos.pdf" if g else "documents.pdf"] = mkpdf(pages, pp[0], pp[1])
            elif m == "sheet":
                for g, pages, labels, pp in sheets(its):
                    for n, pg in enumerate(pages, 1):
                        files[f"{'photos' if g else 'documents'}-{n}.jpg"] = render_jpg(pg, pp)
            elif m == "img":
                for n, it in enumerate(its, 1):
                    files[f"doc-{n}.jpg"] = open(it["path"], "rb").read()
            else:
                ppl = {}
                for it in its:
                    ppl.setdefault(it["d"]["pid"], []).append(it)
                for n, v in enumerate(ppl.values(), 1):
                    for g, pages, labels, pp in sheets(v):
                        files[f"person-{n}-{'photos' if g else 'documents'}.pdf"] = mkpdf(pages, pp[0], pp[1])
            export(files)

        return [txt(f"{len(its)} محددة", size=13, color=MU), txt("مشاركة", size=30, weight="bold"), rg,
                txt("✓ الملف يحتوي المستمسك فقط، بدون إطار أو تحديد أو علامات", size=13, color=MU), btn("حفظ ومشاركة", do, True)]

    def bak():
        def mk(e):
            z = io.BytesIO()
            with zipfile.ZipFile(z, "w") as f:
                f.write(DBF, "db.json")
                for fn in os.listdir(DIR):
                    if fn.endswith(".jpg"):
                        f.write(os.path.join(DIR, fn), fn)
            put("wallet-backup.zip", z.getvalue())

        def restore(path):
            try:
                with zipfile.ZipFile(path) as f:
                    names = [n for n in f.namelist() if n == "db.json" or (n.endswith(".jpg") and "/" not in n and "\\" not in n)]
                    new = json.loads(f.read("db.json"))
                    assert new["people"]
                    for n in names:
                        open(os.path.join(DIR, n), "wb").write(f.read(n))
                db.clear()
                db.update(new)
                S["sel"], S["pid"] = [], db["people"][0]["id"]
                cache.clear()
                persist()
                render()
                toast("تمت الاستعادة")
            except Exception:
                toast("ملف غير صالح")

        return [txt("كل البيانات محفوظة على جهازك فقط", size=13, color=MU), txt("النسخ الاحتياطي", size=30, weight="bold"),
                txt(f"{len(db['people'])} أشخاص · {len(db['docs'])} مستمسك"),
                txt("ملف النسخة غير مشفّر، فاحفظه بمكان آمن. الاستعادة تستبدل البيانات الحالية.", size=13, color=MU),
                row(btn("إنشاء ومشاركة", mk, True), btn("استعادة", lambda e: pick(restore, ["zip"])))]

    # ---------- النوافذ ----------
    def pk(i):
        if i == S["pid"]:
            return person_dlg(i)
        S["pid"] = i
        render()

    def person_dlg(pid):
        new = pid is None
        t = dict(P(pid)) if pid else {"id": uuid.uuid4().hex[:8], "name": "", "color": COL[len(db["people"]) % 5], "photo": ""}
        name = ft.TextField(value=t["name"], label="الاسم", text_align=R, on_change=lambda e: t.update(name=e.control.value))
        holder = ft.Container()

        def build():
            return ft.Column([av({**t, "name": t["name"] or "؟"}, 100), btn("اختيار صورة", lambda e: pick(got)),
                              ft.Row([ft.Container(width=34, height=34, bgcolor=c, border_radius=17,
                                                   border=ft.border.all(3, "white") if t["color"] == c else None,
                                                   on_click=lambda e, c=c: setc(c)) for c in COL],
                                     alignment=ft.MainAxisAlignment.CENTER)], horizontal_alignment=CEN)

        def paint():
            holder.content = build()
            page.update()

        def got(path):
            t["photo"] = import_img(path, 1, 320)["img"]
            paint()

        def setc(c):
            t["color"] = c
            paint()

        def ok(e):
            t["name"] = (name.value or "").strip()
            if not t["name"]:
                return toast("اكتب الاسم")
            if new:
                db["people"].append(t)
                S["pid"] = t["id"]
            else:
                db["people"] = [t if p["id"] == t["id"] else p for p in db["people"]]
            persist()
            page.close(dlg)
            render()

        def rm(e):
            db["docs"] = [d for d in db["docs"] if d["pid"] != t["id"]]
            db["people"] = [p for p in db["people"] if p["id"] != t["id"]]
            S["sel"] = [k for k in S["sel"] if Dd(k.split(":")[0])]
            S["pid"] = db["people"][0]["id"]
            persist()
            page.close(dlg)
            render()

        holder.content = build()
        acts = [ft.TextButton("إلغاء", on_click=lambda e: page.close(dlg)), ft.TextButton("حفظ", on_click=ok)]
        if not new and len(db["people"]) > 1:
            acts.insert(0, ft.TextButton("حذف الشخص", on_click=rm, style=ft.ButtonStyle(color="#fca5a5")))
        dlg = ft.AlertDialog(modal=True, title=txt("شخص جديد" if new else "تعديل الشخص"),
                             content=ft.Column([holder, name], tight=True, scroll=ft.ScrollMode.AUTO), actions=acts)
        page.open(dlg)

    def doc_dlg():
        t = T[0]
        d = {"id": uuid.uuid4().hex[:8], "pid": S["pid"], "ti": 0, "name": t[0], "w": t[1], "h": t[2], "sides": [{"l": l} for l in t[3]]}
        holder = ft.Container()

        def refresh():
            holder.content = build()
            page.update()

        def settype(i):
            t = T[i]
            d.update(ti=i, name=t[0], w=t[1], h=t[2], sides=[{"l": l} for l in t[3]])
            refresh()

        def dim(k, v):
            try:
                v = float(v)
                assert v >= 10
            except Exception:
                return refresh()
            if v != d[k]:
                d[k] = v
                if any(s.get("img") for s in d["sides"]):
                    d["sides"] = [{"l": s["l"]} for s in d["sides"]]
                    toast("تم مسح الصور لأن الأبعاد تغيّرت، صوّرها من جديد")
                refresh()

        def setimg(i, path):
            d["sides"][i].update(import_img(path, d["w"] / d["h"], 1400))
            refresh()

        def build():
            rows = []
            for i, s in enumerate(d["sides"]):
                th = ft.Image(src_base64=img64(s["img"]), width=84, height=min(110, 84 * d["h"] / d["w"]), fit=ft.ImageFit.FILL) \
                    if s.get("img") else ft.Container(width=84, height=min(110, 84 * d["h"] / d["w"]), bgcolor="#2A3541")
                rows.append(row(th, txt(s["l"] + (" ✓" if s.get("img") else ""), weight="bold", expand=True),
                                btn("تغيير" if s.get("img") else "اختيار", lambda e, i=i: pick(lambda p: setimg(i, p)))))
            return ft.Column([
                ft.Dropdown(value=str(d["ti"]), options=[ft.dropdown.Option(str(i), x[0]) for i, x in enumerate(T)],
                            on_change=lambda e: settype(int(e.control.value))),
                ft.TextField(value=d["name"], label="الاسم", text_align=R, on_change=lambda e: d.update(name=e.control.value)),
                txt("الأبعاد الحقيقية بالملم (قِسها بالمسطرة وعدّلها قبل التصوير)", size=12, color=MU),
                ft.Row([ft.TextField(value=str(d["w"]), label="العرض", expand=True, keyboard_type=ft.KeyboardType.NUMBER,
                                     on_blur=lambda e: dim("w", e.control.value)),
                        ft.TextField(value=str(d["h"]), label="الارتفاع", expand=True, keyboard_type=ft.KeyboardType.NUMBER,
                                     on_blur=lambda e: dim("h", e.control.value))]), *([txt("للصورة الشخصية: خلفية بيضاء والوجه بوسط الصورة، فالقص يكون من الوسط.", size=12, color=MU)] if d["ti"] in PHT else []), *rows], tight=True, horizontal_alignment=END)

        def ok(e):
            d["name"] = d["name"].strip()
            if not d["name"]:
                return toast("اكتب الاسم")
            if not any(s.get("img") for s in d["sides"]):
                return toast("أضف صورة واحدة على الأقل")
            db["docs"].append(d)
            persist()
            page.close(dlg)
            render()

        holder.content = build()
        dlg = ft.AlertDialog(modal=True, title=txt("مستمسك جديد"), content=ft.Container(holder, width=380),
                             actions=[ft.TextButton("إلغاء", on_click=lambda e: page.close(dlg)), ft.TextButton("حفظ", on_click=ok)])
        page.open(dlg)

    # ---------- الإطار العام ----------
    body = ft.Column(scroll=ft.ScrollMode.AUTO, expand=True, horizontal_alignment=END, spacing=12)
    nav = ft.NavigationBar(bgcolor=SU, on_change=lambda e: go(3 - int(e.control.selected_index)), destinations=[
        ft.NavigationBarDestination(icon=ft.Icons.CLOUD_UPLOAD_OUTLINED, label="النسخ"),
        ft.NavigationBarDestination(icon=ft.Icons.SHARE, label="المشاركة"),
        ft.NavigationBarDestination(icon=ft.Icons.PRINT, label="الطباعة"),
        ft.NavigationBarDestination(icon=ft.Icons.ACCOUNT_BALANCE_WALLET_OUTLINED, label="المستمسكات")])
    page.navigation_bar = nav
    page.add(ft.SafeArea(body, expand=True))

    def render():
        nav.selected_index = 3 - S["tab"]
        body.controls = [ft.Container(ft.Column([home, prt, shr, bak][S["tab"]](), spacing=12, horizontal_alignment=END),
                                      padding=ft.padding.all(20))]
        page.update()

    render()


if __name__ == "__main__":
    ft.app(target=main)
