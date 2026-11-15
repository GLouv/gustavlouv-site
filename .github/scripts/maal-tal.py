#!/usr/bin/env python3
"""maal-tal.py: måler tallene til gustavlouv.com én gang i døgnet (.github/workflows/tal.yml) og skriver tal.json.
Forsiden læser tal.json ved hvert besøg og henter desuden npm og GitHub direkte. Chrome Web Store kan kun måles her.
Fejler en kilde, beholdes det forrige tal for netop den kilde, og kørslen siger det. Fejler alle, ændres intet (exit 1)."""
import datetime, json, os, pathlib, re, sys, urllib.request

ROD = pathlib.Path(__file__).resolve().parents[2]
FIL = ROD / "tal.json"
UA = {"User-Agent": "gustavlouv-tal/1.0 (+https://gustavlouv.com)", "Accept-Language": "en-US,en;q=0.9"}
BUTIK = "https://chromewebstore.google.com/detail/agent360-browser-mcp/jdehgalffmffhfhmmhaokfbfnafnmgcl?hl=en"
PAKKER = {"browser": ("@agent360/browser-mcp", "2026-04-02", "Agent360dk/browser-mcp"),
          "computer": ("@agent360/computer-mcp", "2026-09-18", "Agent360dk/computerMCP")}
# Gustav 15/11-2026: ca. 2.500 faste brugere om ugen. Butikkens side runder ned til hele tusinder og viste «2,000 users».
# Så længe den viser 2.000, står Gustavs 2.500; går butikkens tal op eller ned, står butikkens eget. (Samme regel som tal.py lokalt.)
CWS_GUSTAV, CWS_SPAND = 2500, 2000


def hent(url, json_=True):
    h = dict(UA)
    if url.startswith("https://api.github.com/") and os.environ.get("GH_TOKEN"):
        h["Authorization"] = "Bearer " + os.environ["GH_TOKEN"]
    with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=30) as r:
        s = r.read().decode("utf-8", "replace")
    return json.loads(s) if json_ else s


def main():
    gl = json.loads(FIL.read_text(encoding="utf-8")) if FIL.exists() else {}
    idag = datetime.date.today()
    ny = {"maalt": idag.isoformat(), "cws": gl.get("cws"), "cws_butik": gl.get("cws_butik")}
    ok, fejl = 0, []
    try:
        m = re.search(r"([\d,]+)\+?\s+users", hent(BUTIK, json_=False))
        butik = int(m.group(1).replace(",", ""))
        ny["cws_butik"], ny["cws"] = butik, (CWS_GUSTAV if butik == CWS_SPAND else butik)
        ok += 1
    except Exception as e:
        fejl.append(f"Chrome Web Store: {e!r}")
    for navn, (pakke, foerste, repo) in PAKKER.items():
        g = gl.get(navn, {})
        d = {k: g.get(k) for k in ("npm_i_alt", "npm_30_dage", "stjerner", "forks")}
        try:
            dage, a = [], datetime.date.fromisoformat(foerste)
            while a <= idag:  # npm svarer højst 18 måneder ad gangen
                b = min(a + datetime.timedelta(days=364), idag)
                dage += hent(f"https://api.npmjs.org/downloads/range/{a}:{b}/{pakke}")["downloads"]
                a = b + datetime.timedelta(days=1)
            total = sum(x["downloads"] for x in dage)
            # Hentninger i alt kan kun vokse. Falder tallet, har npm svaret afkortet: behold det forrige
            if d["npm_i_alt"] is None or total >= d["npm_i_alt"]:
                d["npm_i_alt"] = total
            else:
                fejl.append(f"{navn}: npm i alt faldt {d['npm_i_alt']} → {total}; det forrige beholdes")
            # 30-dages-tallet tages kun, når det stemmer med de samme dage i svaret ovenfor (som på forsiden)
            j = hent(f"https://api.npmjs.org/downloads/point/last-month/{pakke}")
            tjek = sum(x["downloads"] for x in dage if j["start"] <= x["day"] <= j["end"])
            if j["downloads"] == tjek and j["downloads"] > 0:
                d["npm_30_dage"] = j["downloads"]
            else:
                fejl.append(f"{navn}: 30-dages-tallet {j['downloads']} stemmer ikke med dagene ({tjek}); det forrige beholdes")
            ok += 1
        except Exception as e:
            fejl.append(f"{navn} npm: {e!r}")
        try:
            r = hent(f"https://api.github.com/repos/{repo}")
            d["stjerner"], d["forks"] = int(r["stargazers_count"]), int(r["forks_count"])
            ok += 1
        except Exception as e:
            fejl.append(f"{navn} GitHub: {e!r}")
        ny[navn] = d
    for f in fejl:
        print(f"::warning::{f}")
    if not ok:
        print("::error::Ingen kilde svarede. tal.json er ikke ændret."); sys.exit(1)
    if not isinstance(ny["cws"], int):
        print("::error::Chrome-tallet mangler, og der er intet forrige. tal.json er ikke ændret."); sys.exit(1)
    FIL.write_text(json.dumps(ny, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(ny, ensure_ascii=False))


if __name__ == "__main__":
    main()
