"""Verhaal schrijven met de Claude API (gestructureerde uitvoer via tool-use)."""
import json, os, random

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
Chapter pexels_queries: 5 concrete English search phrases (1-3 words) for REAL stock footage that fits that chapter
(nature, water, night sky, candles, rain, snow, trains, cozy interiors, lights). No people close-ups, no text, no logos.
Mix calm daytime/dusk/night footage that matches the scene."""

TOOL = {
    "name": "submit_story",
    "description": "Submit the finished sleep story.",
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Short evocative title, 3-7 words, Title Case, no pipes or colons"},
            "title_keywords": {"type": "string", "description": "2-3 words like 'Lake Sounds' or 'Rain Sounds' for the title suffix"},
            "summary": {"type": "string", "description": "2-3 sentence YouTube description of the story, no medical claims"},
            "tags": {"type": "array", "items": {"type": "string"}, "description": "12-16 YouTube tags"},
            "chapters": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "paragraphs": {"type": "array", "items": {"type": "string"}},
                        "pexels_queries": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["title", "paragraphs", "pexels_queries"],
                },
            },
        },
        "required": ["title", "title_keywords", "summary", "tags", "chapters"],
    },
}

MIN_WORDS, MAX_WORDS = int(os.environ.get("MIN_WORDS", 2200)), int(os.environ.get("MAX_WORDS", 2900))


def _load(x):
    """Het model geeft geneste lijsten soms als JSON-tekst terug; zet ze terug naar echte lijsten."""
    if isinstance(x, str):
        try: return json.loads(x, strict=False)
        except ValueError: return []
    return x


def fix(story):
    story = dict(story)
    story["chapters"] = [dict(c, paragraphs=_load(c.get("paragraphs", [])), pexels_queries=_load(c.get("pexels_queries", [])))
                         for c in (_load(c) for c in _load(story.get("chapters", []))) if isinstance(c, dict)]
    story["tags"] = _load(story.get("tags", []))
    return story


def words(story):
    return sum(len(p.split()) for c in story["chapters"] for p in c["paragraphs"])


def problems(story):
    out = []
    n = len(story["chapters"])
    if not 7 <= n <= 10: out.append(f"{n} chapters (need 8-9)")
    w = words(story)
    if w < MIN_WORDS: out.append(f"only {w} words, need {MIN_WORDS}-{MAX_WORDS}: make every paragraph and chapter longer")
    if w > MAX_WORDS: out.append(f"{w} words, need {MIN_WORDS}-{MAX_WORDS}: shorten")
    for c in story["chapters"]:
        if len(c.get("pexels_queries", [])) < 4: out.append("each chapter needs 5 pexels_queries")
        if not c["paragraphs"]: out.append("empty chapter")
    return out


def write_story(recent_titles, recent_places):
    import anthropic
    client = anthropic.Anthropic()
    pool = [p for p in PLACES if p not in recent_places] or PLACES
    place = random.choice(pool)
    prompt = (f"Setting for tonight's story: {place}.\n"
              f"Target: 8-9 chapters, about {int((MIN_WORDS+MAX_WORDS)/2)} words in total (this is about 25 minutes when read slowly).\n"
              f"Make it clearly different from these recent titles: {', '.join(recent_titles[-15:]) or 'none yet'}.\nDeliver the story by calling the submit_story tool exactly once.")
    feedback = ""
    for attempt in range(4):
        msg = client.messages.create(
            model=MODEL, max_tokens=16000, system=SYSTEM, tools=[TOOL],
            tool_choice={"type": "auto"},
            messages=[{"role": "user", "content": prompt + feedback}],
        )
        raw = next((b.input for b in msg.content if b.type == "tool_use"), {})
        story = fix(raw)
        if not story["chapters"]:
            print(f"[story] stop={msg.stop_reason} blocks={[b.type for b in msg.content]} raw={str(raw)[:700]}", flush=True)
        issues = problems(story)
        print(f"[story] attempt {attempt+1}: {words(story)} words, {len(story['chapters'])} chapters, issues={issues}", flush=True)
        if not issues:
            story["place"] = place
            return story
        feedback = "\n\nYour previous attempt had problems: " + "; ".join(issues) + ". Fix them."
    raise RuntimeError("Could not get a valid story: " + "; ".join(issues))
