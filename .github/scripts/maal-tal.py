#!/usr/bin/env python3
"""maal-tal.py: måler tallene til gustavlouv.com én gang i døgnet (.github/workflows/tal.yml) og skriver tal.json.
Forsiden læser tal.json ved hvert besøg og henter desuden npm og GitHub direkte. Chrome Web Store kan kun måles her.
Fejler en kilde, beholdes det forrige tal for netop den kilde, og kørslen siger det. Fejler alle, ændres intet (exit 1).
Chrome-tallet (16/11-2026, Gustav valgte «ugentlige brugere»): users-7d fra Googles Chrome Web Store API v2 med en læsenøgle
(repoets hemmeligheder CWS_*). Svarer API'et ikke, står det forrige tal, og arbejdsgangen bliver rød til sidst (chrome_fejl=1)."""
import datetime, json, os, pathlib, re, sys, urllib.error, urllib.parse, urllib.request

ROD = pathlib.Path(__file__).resolve().parents[2]
FIL = ROD / "tal.json"
UA = {"User-Agent": "gustavlouv-tal/1.0 (+https://gustavlouv.com)", "Accept-Language": "en-US,en;q=0.9"}
BUTIK = "https://chromewebstore.google.com/detail/agent360-browser-mcp/jdehgalffmffhfhmmhaokfbfnafnmgcl?hl=en"
PAKKER = {"browser": ("@agent360/browser-mcp", "2026-04-02", "Agent360dk/browser-mcp"),
          "computer": ("@agent360/computer-mcp", "2026-09-18", "Agent360dk/computerMCP")}
CWS_NOEGLER = ("CWS_CLIENT_ID", "CWS_CLIENT_SECRET", "CWS_REFRESH_TOKEN", "CWS_PUBLISHER_ID", "CWS_EXTENSION_ID")
TOKEN_URL = "https://oauth2.googleapis.com/token"
CWS_API = "https://chromewebstore.googleapis.com"


def ugentlige_brugere(n, idag):
    """users-7d (aktive brugere de seneste 7 dage) for den nyeste dag med tal. n: de fem CWS_*-nøgler. Giver (tal, dato) eller fejler.
    Målt mod Google 16/11: rækkerne kommer nyeste først og bærer dimensionValues ["total"]; en opdeling (land, OS) tælles aldrig med."""
    mangler = [k for k in CWS_NOEGLER if not n.get(k)]
    if mangler:
        raise RuntimeError("mangler " + ", ".join(mangler))
    krop = urllib.parse.urlencode({"client_id": n["CWS_CLIENT_ID"], "client_secret": n["CWS_CLIENT_SECRET"],
                                   "refresh_token": n["CWS_REFRESH_TOKEN"], "grant_type": "refresh_token"}).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(TOKEN_URL, data=krop, method="POST",
                                    headers={"Content-Type": "application/x-www-form-urlencoded"}), timeout=30) as r:
            tok = json.loads(r.read().decode())["access_token"]
    except urllib.error.HTTPError as e:  # Googles svar bærer «error» (fx invalid_grant = nøglen er udløbet/tilbagekaldt), aldrig nøglen
        try:
            grund = json.loads(e.read().decode("utf-8", "replace")).get("error")
        except Exception:
            grund = None
        raise RuntimeError(f"nøglen blev afvist (HTTP {e.code}, {grund})") from None
    fra = idag - datetime.timedelta(days=14)
    q = [("metrics", "users-7d"), ("timeSpec.firstDate.year", fra.year), ("timeSpec.firstDate.month", fra.month),
         ("timeSpec.firstDate.day", fra.day), ("timeSpec.lastDate.year", idag.year), ("timeSpec.lastDate.month", idag.month),
         ("timeSpec.lastDate.day", idag.day), ("pageSize", 100)]
    navn = urllib.parse.quote(f"publishers/{n['CWS_PUBLISHER_ID']}/items/{n['CWS_EXTENSION_ID']}")
    try:
        with urllib.request.urlopen(urllib.request.Request(f"{CWS_API}/v2/{navn}:queryMetrics?{urllib.parse.urlencode(q)}",
                                    headers={"Authorization": "Bearer " + tok}), timeout=30) as r:
            j = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"queryMetrics svarede HTTP {e.code}") from None
    bedst = None
    for row in j.get("metricRows", []):
        if row.get("dimensionValues") not in (None, [], ["total"]):
            continue
        d = datetime.date(int(row["date"]["year"]), int(row["date"]["month"]), int(row["date"]["day"]))
        for mv in row.get("metricValues", []):
            if mv.get("metric") == "users-7d" and mv.get("value") is not None and (bedst is None or d > bedst[1]):
                bedst = (int(mv["value"]), d)
    if not bedst or bedst[0] <= 0:
        raise RuntimeError("svaret havde intet users-7d-tal")
    return bedst


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
    ny = {"maalt": idag.isoformat(), "cws": gl.get("cws"), "cws_dato": gl.get("cws_dato"), "cws_butik": gl.get("cws_butik")}
    ok, fejl, chrome_fejl = 0, [], None
    try:
        ny["cws"], d = ugentlige_brugere({k: os.environ.get(k, "") for k in CWS_NOEGLER}, idag)
        ny["cws_dato"] = d.isoformat()
        ok += 1
    except Exception as e:
        chrome_fejl = f"Chrome Web Store API: {e}"
        fejl.append(chrome_fejl + "; det forrige tal beholdes")
    try:  # butikkens offentlige, afrundede tal gemmes til sammenligning; det bruges kun, hvis der aldrig har været et API-tal
        m = re.search(r"([\d,]+)\+?\s+users", hent(BUTIK, json_=False))
        ny["cws_butik"] = int(m.group(1).replace(",", ""))
        if ny["cws"] is None:
            ny["cws"] = ny["cws_butik"]
    except Exception as e:
        fejl.append(f"Chrome Web Store-siden: {e!r}")
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
    if chrome_fejl:  # tal.json gemmes stadig med de andre tal; arbejdsgangens sidste trin bliver rødt, så fejlen ikke går i stå i stilhed
        print(f"::error::{chrome_fejl}. Siden viser det forrige Chrome-tal ({ny['cws']}).")
        if os.environ.get("GITHUB_OUTPUT"):
            with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
                f.write("chrome_fejl=1\n")


if __name__ == "__main__":
    main()
