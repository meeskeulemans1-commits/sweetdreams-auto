"""Verhaal schrijven met de Claude API (platte tekst in een vast formaat; robuuster dan tool-use)."""
import os, random, re

MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5-5")

PLACES = [
    "a lighthouse on a quiet coast", "a cozy mountain cabin in the snow", "a small bookshop on a rainy evening",
    "a night train through the countryside", "a wooden rowboat on a still lake", "a seaside village at dusk",
    "an old library with a crackling fireplace", "a tea house in a bamboo forest", "a lantern-lit harbor at night",
    "a cottage garden after a summer shower", "a sailboat drifting under the stars", "a quiet orchard at twilight",
    "a snowy village on the longest night", "a hillside farm at sunset", "a stone bridge over a misty river",
    "a forest path lit by fireflies", "a warm bakery before dawn", "a hot-air balloon floating at dusk",
    "a desert camp under the milky way", "a houseboat on a slow river", "a greenhouse full of rain and plants",
    "a lakeside sauna cabin in winter", "an island with a tiny fishing hut", "a mountain meadow at golden hour",
    "a quiet beach under a full moon", "a cabin by a waterfall", "a night market closing slowly in the rain",
    "a countryside inn with a warm hearth", "a cliff-top path above a moonlit sea", "a canal town in soft fog",
    "a pine forest after the first snowfall", "an observatory on a hill", "a stargazing hut in the highlands",
    "a riverside walk at blue hour", "a tiny cabin in an autumn forest", "a rooftop garden above a sleepy city",
]

SYSTEM = """You are the writer for 'Sweet Dreams', a YouTube channel of calm sleep stories for adults.
Write ONE original, soothing sleep story in English, narrated in second person, present tense ("you walk...").
Style: slow, gentle, sensory (warmth, soft light, quiet sounds, slow breathing), lots of calm repetition, no conflict,
no danger, no plot twists, no cliffhangers. The listener is guided slowly through a peaceful place and the story drifts
toward sleep; the final chapter gets quieter and shorter and ends with the listener drifting off.
Rules: no brands, no real people, no known fictional characters or places from books/films, no religion or politics,
no medical claims (never promise to cure insomnia or anxiety), no mention of AI or of YouTube. Do not start with
'Welcome' (a spoken intro already welcomes the listener). Paragraphs of 40-90 words, every chapter 5-7 paragraphs.
Chapter search phrases: 5 concrete English search phrases (1-3 words) for REAL stock footage that fits that chapter
(nature, water, night sky, candles, rain, snow, trains, cozy interiors, lights). No people close-ups, no text, no logos.
Mix calm daytime/dusk/night footage that matches the scene.

Reply ONLY in this exact plain-text format, with nothing before or after it, and no markdown:
TITLE: <short evocative title, 3-7 words, Title Case, no pipes or colons>
KEYWORDS: <2-3 words like 'Lake Sounds' or 'Rain Sounds'>
SUMMARY: <2-3 sentence YouTube description of the story, no medical claims>
TAGS: <12-16 YouTube tags separated by commas>
=== CHAPTER: <chapter title>
QUERIES: <5 stock footage search phrases separated by |>
<paragraph 1>

<paragraph 2>

(blank line between paragraphs; then the next chapter starts with a new line '=== CHAPTER: ...')"""

MIN_WORDS, MAX_WORDS = int(os.environ.get("MIN_WORDS", 2000)), int(os.environ.get("MAX_WORDS", 3000))


def words(story):
    return sum(len(p.split()) for c in story["chapters"] for p in c["paragraphs"])


def _field(head, name, nxt):
    m = re.search(rf"^{name}:[ \t]*(.*?)\s*(?=^(?:{nxt}):|\Z)", head, flags=re.M | re.S)
    return m.group(1).strip() if m else ""


def parse(text):
    text = text.replace("\r\n", "\n").replace("**", "")
    parts = re.split(r"^=== CHAPTER:[ \t]*", text, flags=re.M)
    head, chs = parts[0], parts[1:]
    story = {
        "title": " ".join(re.sub(r"[|:]", " ", _field(head, "TITLE", "KEYWORDS|SUMMARY|TAGS")).split()),
        "title_keywords": _field(head, "KEYWORDS", "SUMMARY|TAGS"),
        "summary": " ".join(_field(head, "SUMMARY", "TAGS").split()),
        "tags": [t.strip() for t in _field(head, "TAGS", "ZZZ").replace("\n", " ").split(",") if t.strip()][:16],
        "chapters": [],
    }
    for ch in chs:
        lines = ch.strip().split("\n")
        title = lines[0].strip()
        body = "\n".join(lines[1:])
        m = re.search(r"^QUERIES:[ \t]*(.*)$", body, flags=re.M)
        queries = [q.strip() for q in m.group(1).split("|") if q.strip()] if m else []
        if m: body = body[:m.start()] + body[m.end():]
        paras = [" ".join(p.split()) for p in re.split(r"\n\s*\n", body) if p.strip()]
        story["chapters"].append({"title": title, "pexels_queries": queries, "paragraphs": paras})
    return story


def problems(story):
    out = []
    if not story["title"]: out.append("missing TITLE line")
    if not story["summary"]: out.append("missing SUMMARY line")
    if len(story["tags"]) < 8: out.append("TAGS line needs 12-16 comma-separated tags")
    n = len(story["chapters"])
    if not 7 <= n <= 10: out.append(f"{n} chapters (need 8-9, each starting with a line '=== CHAPTER: title')")
    w = words(story)
    if w < MIN_WORDS: out.append(f"only {w} words, need {MIN_WORDS}-{MAX_WORDS}: make every paragraph and chapter longer")
    if w > MAX_WORDS: out.append(f"{w} words, need {MIN_WORDS}-{MAX_WORDS}: shorten")
    for c in story["chapters"]:
        if len(c["pexels_queries"]) < 4: out.append("each chapter needs a QUERIES line with 5 phrases separated by |"); break
    for c in story["chapters"]:
        if not c["paragraphs"]: out.append("empty chapter"); break
    return out


def write_story(recent_titles, recent_places):
    import anthropic
    client = anthropic.Anthropic()
    pool = [p for p in PLACES if p not in recent_places] or PLACES
    place = random.choice(pool)
    prompt = (f"Setting for tonight's story: {place}.\n"
              f"Target: 8-9 chapters, about {int((MIN_WORDS+MAX_WORDS)/2)} words in total (this is about 25 minutes when read slowly).\n"
              f"Make it clearly different from these recent titles: {', '.join(recent_titles[-15:]) or 'none yet'}.")
    feedback = ""
    for attempt in range(5):
        msg = client.messages.create(model=MODEL, max_tokens=16000, system=SYSTEM,
                                     messages=[{"role": "user", "content": prompt + feedback}])
        text = "".join(b.text for b in msg.content if b.type == "text")
        story = parse(text)
        issues = problems(story)
        print(f"[story] attempt {attempt+1}: {words(story)} words, {len(story['chapters'])} chapters, stop={msg.stop_reason}, issues={issues}", flush=True)
        if issues and not story["chapters"]:
            print("[story] begin van antwoord:", repr(text[:300]), flush=True)
        if not issues:
            story["place"] = place
            return story
        feedback = "\n\nYour previous attempt had problems: " + "; ".join(issues) + ". Fix them and follow the exact format."
    raise RuntimeError("Could not get a valid story: " + "; ".join(issues))
