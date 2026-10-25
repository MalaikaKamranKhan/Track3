"""One small interface over several LLM providers. LLM_PROVIDER=fake runs fully offline for demos and tests."""
from __future__ import annotations

import asyncio
import json
import random
import re

import httpx

from . import config

DEFAULT_MODELS = {
    "gemini": "gemini-3.5-flash-lite",
    "anthropic": "claude-haiku-5-5",
    "openai": "gpt-4o-mini",
    "bedrock": "amazon.nova-lite-v1:0",
}

QUESTION_PROMPT = """You write quiz questions for a college study group playing a "boss battle" game in their group chat.
Topic: {topic}
{context_block}
{material_block}
Write {n} multiple-choice questions that check real understanding (mix recall, "why", and small worked problems).
Rules: 4 options each, exactly one correct, plausible wrong options, under 200 characters per question,
under 80 characters per option, a one-sentence explanation, and a 1-3 word sub-topic tag.
Base the questions on the material when material is given.
Reply with only JSON: {{"questions": [{{"prompt": "...", "options": ["...","...","...","..."], "answer": 0,
"explanation": "...", "topic": "..."}}]}} where answer is the index 0-3 of the correct option."""

LIE_PROMPT = """You write rounds of "Two Truths and a Lie" for a college study group's group chat.
Topic: {topic}
{context_block}
{material_block}
Write {n} rounds. Each round has exactly 3 short statements about the topic (under 140 characters each): two true,
one false. The false one must be plausible, a common misconception, not a joke. Vary where the lie sits.
Give a one-sentence explanation of why the lie is false, and a 1-3 word sub-topic tag.
Reply with only JSON: {{"rounds": [{{"statements": ["...","...","..."], "lie": 0, "explanation": "...",
"topic": "..."}}]}} where lie is the index 0-2 of the false statement."""

EXPLAIN_PROMPT = """You run "Explain It", a teach-back game for a college study group's group chat.
Topic: {topic}
{context_block}
{material_block}
Pick {n} different core concepts from the topic that a student should be able to explain in 2-3 sentences.
For each give: the concept name, a one-line prompt asking a student to explain it (start with "Explain"), and the
3 key points a good explanation must mention (short phrases).
Reply with only JSON: {{"items": [{{"concept": "...", "ask": "Explain ...", "key_points": ["...","...","..."]}}]}}"""

GRADE_PROMPT = """A college student explained a concept to their study group. Grade it like a kind but honest TA.
Concept: {concept}
Key points a good answer covers: {key_points}
Student's explanation: <<<{answer}>>>
Score 0-10 for correctness and clarity (10 = covers every key point correctly and clearly; wrong statements cost
points; length alone earns nothing). Write one short sentence of feedback addressed to the student, and list the key
points they missed (empty if none).
Reply with only JSON: {{"score": 7, "feedback": "...", "missed": ["..."]}}"""

MOMENT_PROMPT = """These are the latest messages from a college group chat:
{messages}
Is the group worried about or preparing for a specific test, assignment or course topic right now?
Reply with only JSON: {{"study": true/false, "topic": "short topic to quiz on, e.g. CPU caches", "course": "course code or empty"}}"""


class LLMError(RuntimeError):
    pass


def _extract_json(text: str):
    text = text.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    for opener, closer in (("{", "}"), ("[", "]")):
        start, end = text.find(opener), text.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                continue
    raise LLMError("model did not return JSON")


async def _complete(prompt: str) -> str:
    provider = config.LLM_PROVIDER
    model = config.LLM_MODEL or DEFAULT_MODELS.get(provider, "")
    async with httpx.AsyncClient(timeout=120) as http:
        if provider == "gemini":
            r = await http.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                headers={"x-goog-api-key": config.GEMINI_API_KEY},
                json={"contents": [{"parts": [{"text": prompt}]}],
                      "generationConfig": {"responseMimeType": "application/json", "temperature": 0.8}})
            r.raise_for_status()
            return r.json()["candidates"][0]["content"]["parts"][0]["text"]
        if provider == "anthropic":
            r = await http.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": config.ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01"},
                json={"model": model, "max_tokens": 2000, "messages": [{"role": "user", "content": prompt}]})
            r.raise_for_status()
            return "".join(b.get("text", "") for b in r.json()["content"])
        if provider == "openai":
            r = await http.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {config.OPENAI_API_KEY}"},
                json={"model": model, "messages": [{"role": "user", "content": prompt}],
                      "response_format": {"type": "json_object"}})
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
    if provider == "bedrock":
        return await asyncio.to_thread(_bedrock, model, prompt)
    raise LLMError(f"unknown LLM_PROVIDER {provider!r}")


def _bedrock(model: str, prompt: str) -> str:
    import boto3  # only needed for this provider: pip install boto3

    client = boto3.client("bedrock-runtime", region_name=config.AWS_REGION)
    resp = client.converse(modelId=model, messages=[{"role": "user", "content": [{"text": prompt}]}],
                           inferenceConfig={"maxTokens": 2000, "temperature": 0.8})
    return "".join(part.get("text", "") for part in resp["output"]["message"]["content"])


def _blocks(material: str, context: str) -> dict:
    return {
        "material_block": f"Material from the students' course:\n\"\"\"\n{material[:12000]}\n\"\"\"" if material else "",
        "context_block": (f"Course context from the students' own Canvas: {context}\n"
                          "Write for THIS course at THIS level. Course codes mean different things at different "
                          "universities, so follow the course name and topics above, not your assumptions.")
        if context else "",
    }


async def generate_questions(topic: str, material: str = "", n: int | None = None, context: str = "") -> list[dict]:
    n = n or config.QUESTIONS_PER_BATTLE
    if config.LLM_PROVIDER == "fake":
        return fake_questions(topic, n)
    data = _extract_json(await _complete(QUESTION_PROMPT.format(topic=topic, n=n, **_blocks(material, context))))
    questions = data["questions"] if isinstance(data, dict) else data
    return questions[:n]


async def generate_lies(topic: str, material: str = "", n: int | None = None, context: str = "") -> list[dict]:
    """Two Truths and a Lie rounds, returned in the same shape as questions (3 options, answer = the lie)."""
    n = n or config.QUESTIONS_PER_BATTLE
    if config.LLM_PROVIDER == "fake":
        rounds = fake_lies(topic, n)
    else:
        data = _extract_json(await _complete(LIE_PROMPT.format(topic=topic, n=n, **_blocks(material, context))))
        rounds = data["rounds"] if isinstance(data, dict) else data
    return [{"prompt": "Which one is the lie?", "options": r["statements"], "answer": r["lie"],
             "explanation": r.get("explanation", ""), "topic": r.get("topic", "")} for r in rounds[:n]]


async def explain_items(topic: str, material: str = "", n: int = 3, context: str = "") -> list[dict]:
    if config.LLM_PROVIDER == "fake":
        return fake_explain(topic, n)
    data = _extract_json(await _complete(EXPLAIN_PROMPT.format(topic=topic, n=n, **_blocks(material, context))))
    items = data["items"] if isinstance(data, dict) else data
    out = []
    for it in items[:n]:
        concept = str(it.get("concept", "")).strip()[:80]
        if concept:
            out.append({"concept": concept, "ask": str(it.get("ask") or f"Explain {concept}.").strip()[:200],
                        "key_points": [str(k).strip()[:100] for k in (it.get("key_points") or [])[:4]]})
    if not out:
        raise LLMError("no concepts returned")
    return out


async def grade_explanation(concept: str, key_points: list[str], answer: str) -> dict:
    if config.LLM_PROVIDER == "fake":
        return fake_grade(key_points, answer)
    data = _extract_json(await _complete(GRADE_PROMPT.format(concept=concept, key_points="; ".join(key_points),
                                                              answer=answer[:1500])))
    try:
        score = max(0, min(10, int(round(float(data.get("score", 0))))))
    except (TypeError, ValueError):
        score = 0
    return {"score": score, "feedback": str(data.get("feedback", "")).strip()[:300],
            "missed": [str(m).strip()[:100] for m in (data.get("missed") or [])[:4]]}


async def detect_moment(messages: list[str]) -> dict:
    """Ask the model whether recent chat is a study moment. Returns {} when it isn't."""
    if config.LLM_PROVIDER == "fake":
        return fake_moment(messages)
    try:
        data = _extract_json(await _complete(MOMENT_PROMPT.format(messages="\n".join(messages[-15:]))))
    except (LLMError, httpx.HTTPError, KeyError):
        return {}
    return data if isinstance(data, dict) and data.get("study") and data.get("topic") else {}


# offline mode ---------------------------------------------------------------

CACHE_BANK = [
    {"prompt": "A 2-way set-associative cache has 64 sets. How many index bits does an address use?",
     "options": ["5", "6", "7", "64"], "answer": 1,
     "explanation": "64 sets = 2^6, so 6 index bits pick the set.", "topic": "index bits"},
    {"prompt": "Which miss happens the very first time a block is ever accessed?",
     "options": ["Conflict miss", "Capacity miss", "Compulsory miss", "Coherence miss"], "answer": 2,
     "explanation": "Compulsory (cold) misses happen on first access no matter the cache size.", "topic": "miss types"},
    {"prompt": "Block size is 16 bytes. How many offset bits are in each address?",
     "options": ["2", "4", "8", "16"], "answer": 1,
     "explanation": "16 = 2^4, so 4 offset bits select the byte inside the block.", "topic": "offset bits"},
    {"prompt": "Raising associativity from direct-mapped to 4-way mostly reduces which misses?",
     "options": ["Compulsory", "Conflict", "Capacity", "All of them equally"], "answer": 1,
     "explanation": "More ways means fewer blocks fighting over one set: fewer conflict misses.", "topic": "associativity"},
    {"prompt": "A write-back cache writes a dirty block to memory when...",
     "options": ["Every store happens", "The block is evicted", "The CPU is idle", "A read misses"], "answer": 1,
     "explanation": "Write-back defers the memory write until the dirty block is evicted.", "topic": "write policy"},
    {"prompt": "Hit time 1 cycle, miss rate 5%, miss penalty 100 cycles. What is the AMAT?",
     "options": ["5 cycles", "6 cycles", "100 cycles", "105 cycles"], "answer": 1,
     "explanation": "AMAT = 1 + 0.05 x 100 = 6 cycles.", "topic": "AMAT"},
]


def fake_questions(topic: str, n: int) -> list[dict]:
    if "cache" in topic.lower():
        return random.sample(CACHE_BANK, min(n, len(CACHE_BANK)))
    return [{"prompt": f"[demo] Practice question {i + 1} on {topic}: which option is correct?",
             "options": ["This one", "Not this", "Nope", "Also no"], "answer": 0,
             "explanation": "Offline demo mode. Set LLM_PROVIDER to get real questions.", "topic": topic}
            for i in range(n)]


CACHE_LIES = [
    {"statements": ["Write-back caches write to memory on every store.", "A dirty bit marks a modified block.",
                    "Compulsory misses happen on first access."], "lie": 0,
     "explanation": "Write-back only writes a dirty block when it's evicted; write-through writes on every store.",
     "topic": "write policy"},
    {"statements": ["More associativity reduces conflict misses.", "A direct-mapped cache is 1-way set associative.",
                    "Bigger blocks always lower the miss rate."], "lie": 2,
     "explanation": "Past a point, bigger blocks mean fewer blocks and more misses (and a bigger miss penalty).",
     "topic": "block size"},
    {"statements": ["AMAT = hit time + miss rate x miss penalty.", "L1 caches are usually smaller than L2.",
                    "LRU evicts the most recently used block."], "lie": 2,
     "explanation": "LRU evicts the least recently used block.", "topic": "replacement"},
    {"statements": ["The offset bits pick a byte inside a block.", "Index bits pick the set.",
                    "Tag bits pick the byte inside the set."], "lie": 2,
     "explanation": "Tag bits identify which block is stored; they're compared, they don't select a byte.",
     "topic": "address bits"},
    {"statements": ["Capacity misses happen when the working set is bigger than the cache.",
                    "A fully associative cache has no conflict misses.", "Caches exploit only spatial locality."],
     "lie": 2, "explanation": "Caches exploit both temporal and spatial locality.", "topic": "locality"},
]

CACHE_EXPLAIN = [
    {"concept": "write-back caches", "ask": "Explain how a write-back cache handles stores.",
     "key_points": ["writes go to the cache", "dirty bit marks changed blocks", "memory written on eviction"]},
    {"concept": "set associativity", "ask": "Explain what a 2-way set-associative cache is.",
     "key_points": ["address maps to one set", "block can go in either of 2 ways", "fewer conflict misses"]},
    {"concept": "AMAT", "ask": "Explain what AMAT measures and how to compute it.",
     "key_points": ["average memory access time", "hit time plus miss rate times miss penalty", "lower is better"]},
]


def fake_lies(topic: str, n: int) -> list[dict]:
    if "cache" in topic.lower():
        return random.sample(CACHE_LIES, min(n, len(CACHE_LIES)))
    return [{"statements": [f"[demo] True fact {i + 1}a about {topic}.", f"[demo] This is the lie ({i + 1}).",
                            f"[demo] True fact {i + 1}b about {topic}."], "lie": 1,
             "explanation": "Offline demo mode. Set LLM_PROVIDER for real rounds.", "topic": topic} for i in range(n)]


def fake_explain(topic: str, n: int) -> list[dict]:
    if "cache" in topic.lower():
        return CACHE_EXPLAIN[:n]
    return [{"concept": f"{topic} idea {i + 1}", "ask": f"Explain {topic} idea {i + 1} in 2-3 sentences.",
             "key_points": [topic, "why it matters", "an example"]} for i in range(n)]


def fake_grade(key_points: list[str], answer: str) -> dict:
    words = set(re.findall(r"[a-z0-9]+", answer.lower()))
    hit = [k for k in key_points if set(re.findall(r"[a-z0-9]+", k.lower())) & words]
    missed = [k for k in key_points if k not in hit]
    score = min(10, round(10 * len(hit) / max(1, len(key_points))) + (1 if len(answer) > 80 else 0))
    return {"score": score, "feedback": "Nice!" if score >= 7 else "Good start, add the missing pieces.",
            "missed": missed}


def fake_moment(messages: list[str]) -> dict:
    joined = " ".join(messages[-10:]).lower()
    if "cache" in joined:
        return {"study": True, "topic": "CPU caches", "course": "CSE 230"}
    from .engine import course_in, looks_like_study_moment
    if looks_like_study_moment(joined):
        course = course_in(" ".join(messages[-10:]))
        return {"study": True, "topic": course or "this week's material", "course": course}
    return {}
