import json
import os
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from openai import OpenAI  # official SDK uses OpenAI() client

ROOT = Path(__file__).resolve().parents[1]
ENGINE_DIR = ROOT / "engine"
STATE_PATH = ENGINE_DIR / "state.json"
REPORTS_DIR = ROOT / "reports"

ELLIS_NAME = "Ellis (Proctor-Head)"
GLYPH_NAME = "Glyph"

SPECIAL_ELLIS_MMDD = "12-21"
SPECIAL_GLYPH_MMDD = "01-01"

ENGINE_VERSION = "0.1"


# ---------- Encoding-safe JSON helpers ----------

def read_text_smart(path: Path) -> str:
    """
    Reads text safely from UTF-8 / UTF-8-SIG / UTF-16 (LE/BE) files.
    The UTF-16 BOM is what causes the 0xFF decode error if you read as UTF-8.
    """
    b = path.read_bytes()
    if b.startswith(b"\xff\xfe") or b.startswith(b"\xfe\xff"):
        return b.decode("utf-16")
    if b.startswith(b"\xef\xbb\xbf"):
        return b.decode("utf-8-sig")
    return b.decode("utf-8")


def read_json_smart(path: Path) -> dict:
    return json.loads(read_text_smart(path))


def write_json_utf8(path: Path, obj: dict, indent: int = 2) -> None:
    path.write_text(json.dumps(obj, indent=indent, ensure_ascii=False), encoding="utf-8", newline="\n")


# ---------- Core engine ----------

@dataclass(frozen=True)
class CouncilMember:
    name: str
    domain_bias: list[str]
    stance: str
    cadence: str


def build_council() -> list[CouncilMember]:
    base = [
        CouncilMember(GLYPH_NAME, ["systems", "power", "technology"],
                      "constraint-first realism; convert chaos into structure", "severe minimal"),
        CouncilMember("Nina Simone", ["culture", "justice", "music"],
                      "moral confrontation; truth over comfort", "blues-fire"),
        CouncilMember("James Baldwin", ["culture", "identity", "society"],
                      "clarity under pressure; name the lie precisely", "sermon-knife"),
        CouncilMember("Sun Tzu", ["war", "strategy", "statecraft"],
                      "win by position and timing; spend force wisely", "laconic"),
        CouncilMember("Miyamoto Musashi", ["war", "discipline", "craft"],
                      "mastery through practice; cut what’s unnecessary", "cold-precise"),
        CouncilMember("Mary Shelley", ["art", "science", "ethics"],
                      "creation carries consequence; responsibility is the frame", "gothic-clarity"),
        CouncilMember("Victor Hugo", ["politics", "humanity", "history"],
                      "see the people; make the age visible", "grand-orator"),
        # Add more later
    ]
    names = [m.name for m in base]
    assert names.count(GLYPH_NAME) == 1
    return base


def load_or_init_state(council_names: list[str]) -> dict:
    ENGINE_DIR.mkdir(parents=True, exist_ok=True)

    if STATE_PATH.exists():
        return read_json_smart(STATE_PATH)

    seed = int.from_bytes(os.urandom(8), "big")
    rng = random.Random(seed)

    rotation = council_names.copy()
    rng.shuffle(rotation)

    state = {
        "seed": seed,
        "rotation": rotation,
        "pointer": 0,
        "cycles_completed": 0,
    }
    write_json_utf8(STATE_PATH, state)
    return state


def utc_today() -> datetime:
    return datetime.now(timezone.utc)


def date_path(dt: datetime) -> Path:
    yyyy = dt.strftime("%Y")
    mm = dt.strftime("%m")
    ymd = dt.strftime("%Y-%m-%d")
    return REPORTS_DIR / yyyy / mm / f"{ymd}.json"


def ensure_reports_dirs(dt: datetime) -> None:
    (REPORTS_DIR / dt.strftime("%Y") / dt.strftime("%m")).mkdir(parents=True, exist_ok=True)


def web_intake(client: OpenAI, dt: datetime) -> str:
    prompt = f"""
Date (UTC): {dt.strftime('%Y-%m-%d')}
Task: Collect a tension-weighted snapshot of today's civilization across finance, war/geopolitics, technology, culture, science.
Rules:
- Prefer structural stress, acceleration, fracture, regime change, technological leaps.
- Avoid gossip/fluff.
- Output 8-12 bullet signals, each 1 sentence max.
"""
    resp = client.responses.create(
        model="gpt-5",
        tools=[{"type": "web_search"}],
        input=prompt,
    )
    return resp.output_text.strip()


def pick_today_winner(dt: datetime, state: dict) -> tuple[str, bool]:
    mmdd = dt.strftime("%m-%d")
    if mmdd == SPECIAL_ELLIS_MMDD:
        return ELLIS_NAME, True
    if mmdd == SPECIAL_GLYPH_MMDD:
        return GLYPH_NAME, True

    rotation = state["rotation"]
    pointer = state["pointer"]
    winner = rotation[pointer]
    return winner, False


def advance_rotation(state: dict) -> None:
    rotation = state["rotation"]
    state["pointer"] += 1
    if state["pointer"] >= len(rotation):
        state["pointer"] = 0
        state["cycles_completed"] += 1


def generate_report(client: OpenAI, dt: datetime, council: list[CouncilMember], winner_name: str, signals: str) -> dict:
    names = [m.name for m in council]
    if winner_name not in names and winner_name != ELLIS_NAME:
        winner_name = GLYPH_NAME

    pool = [m for m in council if m.name not in {GLYPH_NAME, winner_name}]
    rng = random.Random(int(dt.strftime("%Y%m%d")))  # deterministic per-day sampling
    sampled = rng.sample(pool, k=min(5, len(pool)))

    voices = [next(m for m in council if m.name == GLYPH_NAME)]
    if winner_name != ELLIS_NAME:
        voices.append(next(m for m in council if m.name == winner_name))
    else:
        voices.append(CouncilMember(ELLIS_NAME, ["proctor-head"],
                                    "stewardship; scope; coherence; craft as duty", "plain-iron"))

    voices.extend(sampled)
    voices = voices[:7]

    voice_cards = "\n".join(
        [f"- {v.name}: bias={','.join(v.domain_bias)}; stance={v.stance}; cadence={v.cadence}" for v in voices]
    )

    instructions = f"""
You are "Gold Umbrella / The Round Table" engine.
You MUST output strict JSON only (no markdown, no extra keys).

Hard frame:
- cultural_diagnosis: essay (proctor lens + includes short debate snippets from 7 voices)
- agon: summary + winner (winner MUST be "{winner_name}")
- mandate: 8-hour composition command (direct, executable, no fluff)
- artifact: status PENDING and link "" by default
- engine_version: "{ENGINE_VERSION}"

Debate format inside cultural_diagnosis:
- Start with a neutral Proctor field summary (2-4 short paragraphs).
- Then include exactly 7 short labeled voice blocks (1 paragraph each) using the provided voice roster.
- End with a brief Proctor adjudication and transition into the winner.

Elements of Eloquence: controlled cadence, rhetorical figures sparingly, severe minimal tone.

Voice roster (exactly these 7 today):
{voice_cards}

Field signals (today's intake):
{signals}
"""

    resp = client.responses.create(
        model="gpt-5",
        input=instructions,
    )
    text = resp.output_text.strip()
    data = json.loads(text)  # enforce strict JSON

    data["date"] = dt.strftime("%Y-%m-%d")
    data.setdefault("artifact", {"status": "PENDING", "link": ""})
    data["engine_version"] = ENGINE_VERSION
    return data


def update_indexes(dt: datetime, daily_path: Path) -> None:
    index_path = REPORTS_DIR / "index.json"
    latest_path = REPORTS_DIR / "latest.json"

    def read_text_safely(path: Path) -> str:
        b = path.read_bytes()

        # UTF-16 BOM (little or big endian)
        if b.startswith(b"\xff\xfe") or b.startswith(b"\xfe\xff"):
            return b.decode("utf-16")

        # UTF-8 BOM
        if b.startswith(b"\xef\xbb\xbf"):
            return b.decode("utf-8-sig")

        # Plain UTF-8
        return b.decode("utf-8")

    # --- load/repair index.json ---
    if index_path.exists():
        index = json.loads(read_text_safely(index_path))
    else:
        index = {"dates": []}

    ymd = dt.strftime("%Y-%m-%d")
    if ymd not in index["dates"]:
        index["dates"].append(ymd)

    # newest first
    index["dates"] = sorted(index["dates"], reverse=True)

    # write back as clean UTF-8 every time (this “heals” bad encodings)
    index_path.write_text(json.dumps(index, indent=2), encoding="utf-8", newline="\n")

    # latest.json is a copy of today’s report (today’s report is already UTF-8)
    latest_path.write_text(daily_path.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")


def main():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("OPENAI_API_KEY is missing (set in GitHub repo Secrets).")

    client = OpenAI(api_key=api_key)
    council = build_council()
    dt = utc_today()

    ensure_reports_dirs(dt)

    council_names = [m.name for m in council if m.name != ELLIS_NAME]
    state = load_or_init_state(council_names)

    winner_name, is_special = pick_today_winner(dt, state)

    signals = web_intake(client, dt)
    report = generate_report(client, dt, council, winner_name, signals)

    out_path = date_path(dt)
    if out_path.exists():
        raise SystemExit(f"Refusing to overwrite existing report: {out_path}")

    write_json_utf8(out_path, report)

    update_indexes(dt, out_path)

    if not is_special:
        advance_rotation(state)
        write_json_utf8(STATE_PATH, state)


if __name__ == "__main__":
    main()
