"""Top 10-script schrijven (Nederlands) met de Claude API, daarna een feitencontrole-ronde."""
import os, random, re

MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5-5")
MIN_WORDS, MAX_WORDS = int(os.environ.get("MIN_WORDS", 1350)), int(os.environ.get("MAX_WORDS", 1750))

THEMES = [
    "dieren met superkrachten", "de slimste dieren", "de snelste dieren", "dieren die je kunt vinden in de diepzee",
    "de beste ouders in het dierenrijk", "dieren met de vreemdste verdedigingstrucs", "dieren die nooit lijken te slapen",
    "de gevaarlijkste jagers", "dieren in de poolgebieden", "dieren die kunnen glijden of vliegen", "de grootste dieren ooit",
    "de kleinste dieren ter wereld", "dieren die kunnen camoufleren", "dieren met het beste gehoor of de beste neus",
    "dieren die samenwerken", "dieren in de woestijn", "dieren in het regenwoud", "dieren die gereedschap gebruiken",
    "dieren met de langste reizen", "dieren die in de nacht leven", "dieren met de vreemdste tanden of bekken",
    "de sterkste dieren voor hun formaat", "dieren die hun eigen huis bouwen", "dieren die kunnen zwemmen en duiken als geen ander",
    "dieren met de gekste manieren van communiceren", "dieren die schijnbaar niet ouder worden of heel oud worden",
    "dieren in Nederland die je misschien niet kent", "dieren uit Australië", "dieren uit Afrika", "dieren uit Zuid-Amerika",
    "dieren uit Azië", "baby-dieren met bijzondere eigenschappen", "dieren die kleur veranderen", "dieren die giftig zijn",
    "dieren die in groepen jagen", "dieren die kunnen overwinteren of een winterslaap houden", "bijzondere vogels",
    "bijzondere insecten", "bijzondere zeedieren", "bijzondere reptielen", "dieren met de gekste ogen", "dieren met de vreemdste voeten of poten",
    "dieren die opvallend goed kunnen springen of klimmen", "dieren die elkaar helpen", "dieren met een geheim talent",
]

SYSTEM = """Je bent de scriptschrijver van het Nederlandse YouTube-kanaal 'WistJeDatDieren'. Je schrijft een Top 10 van ongeveer 9-10 minuten
voor een groot publiek (kinderen vanaf 9 jaar, jongeren en volwassenen) in helder, levendig, gesproken Nederlands. Je schrijft voor een voice-over.

STIJL: kort en pakkend, korte zinnen, af en toe een vraag, een tikkeltje humor, geen opsommingstoon. Spreek de kijker aan met 'je'. Geen emoji's, geen
haakjes, geen cijfers als 'm²' of afkortingen die lastig uit te spreken zijn: schrijf getallen en eenheden voluit zoals je ze uitspreekt ('twintig kilometer per uur').
FEITEN: gebruik alleen feiten waarvan je zeker bent dat ze kloppen. Gebruik 'ongeveer', 'tot wel' of 'meer dan' bij getallen. Geen mythes als feit, geen
twijfelachtige records, geen medische of gevaarlijke adviezen. Bij twijfel: kies een ander dier of een ander feit.
OPBOUW: aftellen van 10 naar 1; plaats het meest verrassende dier op 1. Elk dier krijgt 3-4 feiten: de bekendste/verbluffendste als laatste van dat blok.
Elk blok eindigt met een korte overgang naar de volgende nummer (zonder 'en dan nu').
HOOK_TITLE: de YouTube-titel, 45-70 tekens, wekt nieuwsgierigheid (open vraag, uitdaging of verrassende belofte), is WAAR voor de video, begint met het sterkste woord,
geen clickbait-woorden als 'schokkend' of 'je gelooft het niet', geen ALL CAPS, geen pipe-tekens, mag 'Top 10' bevatten.
THUMB_TEXT: 2-4 woorden in HOOFDLETTERS, maximaal 20 tekens, vult de titel aan (geen kopie).
INTRO: 55-75 woorden, begint met een harde hook (geen 'hallo' of 'welkom'), belooft wat er komt en noemt dat nummer 1 bijzonder is.
OUTRO: 35-50 woorden: korte samenvatting, vraag aan de kijker welk dier zijn favoriet is (reageren), en een vriendelijke oproep om te abonneren.
BEELD: per dier 3 Engelse zoekopdrachten (1-3 woorden) voor ECHT stockbeeld van dat dier ('lion', 'lion hunting', 'lion cubs'). Geen tekst of logo's in beeld.
ENGLISH: de Engelse naam van het dier (enkelvoud, 1-2 woorden) voor het zoeken.

Antwoord UITSLUITEND in dit vaste tekstformaat, zonder markdown, zonder iets ervoor of erna:
HOOK_TITLE: <titel>
THUMB_TEXT: <2-4 woorden, hoofdletters>
SUMMARY: <2-3 zinnen beschrijving voor onder de video, vermeld dat het om dierenweetjes gaat>
TAGS: <12-16 tags, gescheiden door komma's, Nederlands en Engels>
=== INTRO
<tekst>
=== ITEM 10
NAME: <Nederlandse naam van het dier>
ENGLISH: <Engelse naam>
QUERIES: <zoekopdracht 1> | <zoekopdracht 2> | <zoekopdracht 3>
FACT: <voice-overtekst van 110-150 woorden>
=== ITEM 9
...
(tot en met ITEM 1)
=== OUTRO
<tekst>"""

REVIEW = """Je bent een kritische feitencontroleur voor een Nederlands kanaal over dieren. Hieronder staat een script. Controleer elk feit.
Verwijder of herschrijf alles wat onjuist, overdreven, twijfelachtig of niet algemeen aangetoond is (getallen, records, 'enige dier dat...', 'nooit').
Houd de lengte, stijl, structuur en het exacte tekstformaat gelijk (dezelfde regels HOOK_TITLE/THUMB_TEXT/SUMMARY/TAGS, dezelfde === koppen, NAME/ENGLISH/QUERIES/FACT).
AI-SLOP-CONTROLE (even streng): schrap of herschrijf vulling en holle superlatieven (fascinerend, ongelooflijk, indrukwekkend, 'stel je voor', 'zonder twijfel'), zinnen die niets concreets zeggen,
herhaalde zinsopbouw tussen blokken (laat blokken op verschillende manieren beginnen), gedachtestrepen en beletselteken. Elk blok moet minstens twee concrete, controleerbare details bevatten (getal, plaats, naam, vergelijking)
en een eigen, menselijke toon hebben (korte zin, droge opmerking of vraag), geen sjabloon. Behoud verder alles.
Als een dier als geheel niet te redden is, vervang het door een ander dier en pas ook NAME/ENGLISH/QUERIES aan. Geef ALLEEN het verbeterde script terug."""


def _call(system, user, max_tokens=7000, temperature=0.9):
    import anthropic
    c = anthropic.Anthropic()
    r = c.messages.create(model=MODEL, max_tokens=max_tokens, system=system, messages=[{"role": "user", "content": user}])
    return "".join(b.text for b in r.content if getattr(b, "type", "") == "text")


def wc(t): return len(re.findall(r"\w+", t))


# --- AI-slop-poort: vulwoorden, holle superlatieven en herhaling worden afgekeurd
SLOP = ["fascinerend", "ongelooflijk", "verbazingwekkend", "wonderbaarlijk", "indrukwekkend", "duik mee", "laten we", "in de wereld van", "het is belangrijk", "kortom",
        "al met al", "zonder meer", "een echte topper", "niet te geloven", "wist je dat", "ontdek", "reis door", "tot slot kunnen we", "het dierenrijk zit vol", "natuurlijk wonder",
        "meesterwerk", "ware kampioen", "zonder twijfel", "absoluut", "echt waar", "geloof het of niet", "stel je voor"]


def slop_hits(st):
    txt = " ".join([st.get("intro", ""), st.get("outro", "")] + [i["fact"] for i in st["items"]]).lower()
    hits = [w for w in SLOP if w in txt]
    if "—" in txt or "–" in txt or "…" in txt: hits.append("gedachtestreepje/beletselteken")
    return hits


def repeated_openers(st):
    firsts = [" ".join(re.findall(r"\w+", i["fact"].lower())[:2]) for i in st["items"]]
    from collections import Counter
    return [k for k, v in Counter(firsts).items() if v >= 3]


def parse(text):
    text = text.replace("\r", "").strip()
    def field(name):
        m = re.search(rf"^{name}:\s*(.+)$", text, re.M); return m.group(1).strip() if m else ""
    st = {"hook_title": field("HOOK_TITLE"), "thumb_text": field("THUMB_TEXT").upper(), "summary": field("SUMMARY"),
          "tags": [t.strip() for t in field("TAGS").split(",") if t.strip()]}
    parts = re.split(r"^=== ", text, flags=re.M)[1:]
    st["items"] = []
    for p in parts:
        head, _, body = p.partition("\n"); head = head.strip().upper(); body = body.strip()
        if head == "INTRO": st["intro"] = re.sub(r"\s+", " ", body)
        elif head == "OUTRO": st["outro"] = re.sub(r"\s+", " ", body)
        elif head.startswith("ITEM"):
            rank = int(re.search(r"\d+", head).group())
            g = lambda n: (re.search(rf"^{n}:\s*(.+?)(?=^\w+:|\Z)", body, re.M | re.S) or [None, ""])[1].strip()
            st["items"].append({"rank": rank, "name": g("NAME"), "english": g("ENGLISH"),
                                "queries": [q.strip() for q in g("QUERIES").split("|") if q.strip()],
                                "fact": re.sub(r"\s+", " ", g("FACT"))})
    return st


def problems(st):
    p = []
    if not 40 <= len(st["hook_title"]) <= 74: p.append("titellengte")
    if not 6 <= len(st["thumb_text"]) <= 22: p.append("thumb_text")
    if sorted(i["rank"] for i in st["items"]) != list(range(1, 11)): p.append("niet precies 10 nummers")
    for i in st["items"]:
        if not i["name"] or not i["english"] or len(i["queries"]) < 2 or wc(i["fact"]) < 70: p.append(f"nummer {i['rank']} onvolledig")
    if len({i["name"].lower() for i in st["items"]}) != len(st["items"]): p.append("dubbele dieren")
    if not st.get("intro") or not st.get("outro"): p.append("intro/outro mist")
    h = slop_hits(st)
    if len(h) > 1: p.append("slop-woorden: " + ", ".join(h))
    if repeated_openers(st): p.append("te vaak dezelfde zinsopbouw: " + ", ".join(repeated_openers(st)))
    n = words(st)
    if not MIN_WORDS <= n <= MAX_WORDS: p.append(f"woorden {n} buiten {MIN_WORDS}-{MAX_WORDS}")
    return p


def words(st): return wc(st.get("intro", "")) + wc(st.get("outro", "")) + sum(wc(i["fact"]) for i in st["items"])


def render_text(st):
    out = [f"HOOK_TITLE: {st['hook_title']}", f"THUMB_TEXT: {st['thumb_text']}", f"SUMMARY: {st['summary']}", f"TAGS: {', '.join(st['tags'])}", "=== INTRO", st["intro"]]
    for i in sorted(st["items"], key=lambda x: -x["rank"]):
        out += [f"=== ITEM {i['rank']}", f"NAME: {i['name']}", f"ENGLISH: {i['english']}", f"QUERIES: {' | '.join(i['queries'])}", f"FACT: {i['fact']}"]
    out += ["=== OUTRO", st["outro"]]
    return "\n".join(out)


def write(history_titles, theme=None, tries=4):
    theme = theme or random.choice([t for t in THEMES if t not in history_titles] or THEMES)
    last = []
    for n in range(tries):
        user = (f"Thema van deze video: {theme}.\nSchrijf de Top 10. Eerder gemaakte titels (niet herhalen, ook geen dezelfde dieren-selectie): "
                + "; ".join(history_titles[-25:]) + "\n" + (f"Let op, vorige poging had problemen: {', '.join(last)}. Los die op. Totaal ongeveer 1500 woorden." if last else "Totaal ongeveer 1500 woorden (intro + 10 blokken + outro)."))
        st = parse(_call(SYSTEM, user))
        last = problems(st)
        if last: print("[story] poging", n + 1, "problemen:", last, flush=True); continue
        try:
            rv = parse(_call(REVIEW, render_text(st), temperature=0.2))
            if not problems(rv): print("[story] feitencontrole toegepast", flush=True); st = rv
            else: print("[story] feitencontrole gaf problemen, origineel gehouden:", problems(rv), flush=True)
        except Exception as e:
            print("[story] feitencontrole mislukt:", str(e)[:150], flush=True)
        st["theme"] = theme; st["items"].sort(key=lambda x: -x["rank"]); return st
    raise SystemExit("Script voldeed na meerdere pogingen niet: " + ", ".join(last))


REPLACE = """Vervang in het onderstaande Top 10-script ALLEEN nummer {rank} door een ander dier met een feitelijk betrouwbaar, goed filmbaar verhaal. Het dier moet gewoon in stockbeeld voor te komen zijn.
Niet gebruiken: {banned}. Houd stijl en lengte gelijk (110-150 woorden) en geef ALLEEN dit blok terug in exact dit formaat:
NAME: <Nederlandse naam>
ENGLISH: <Engelse naam>
QUERIES: <zoekopdracht 1> | <zoekopdracht 2> | <zoekopdracht 3>
FACT: <voice-overtekst>"""


def replace_item(st, rank, banned):
    out = _call(REPLACE.format(rank=rank, banned=", ".join(banned)), render_text(st), max_tokens=1200, temperature=0.8)
    g = lambda n: (re.search(rf"^{n}:\s*(.+?)(?=^\w+:|\Z)", out.strip(), re.M | re.S) or [None, ""])[1].strip()
    new = {"rank": rank, "name": g("NAME"), "english": g("ENGLISH"), "queries": [q.strip() for q in g("QUERIES").split("|") if q.strip()], "fact": re.sub(r"\s+", " ", g("FACT"))}
    if not new["name"] or wc(new["fact"]) < 70: raise ValueError("vervanging onvolledig")
    st["items"] = [new if i["rank"] == rank else i for i in st["items"]]
    return new
