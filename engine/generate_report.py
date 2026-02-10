import json
import os
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openai import OpenAI


# -------------------------
# Paths / constants
# -------------------------
ROOT = Path(__file__).resolve().parents[1]
ENGINE_DIR = ROOT / "engine"
REPORTS_DIR = ROOT / "reports"

STATE_PATH = ENGINE_DIR / "state.json"

ELLIS_NAME = "Ellis (Proctor-Head)"
GLYPH_NAME = "Glyph"

# Special days (MM-DD)
SPECIAL_ELLIS_MMDD = "12-21"
SPECIAL_GLYPH_MMDD = "01-01"

ENGINE_VERSION = "0.1"


# -------------------------
# Helpers: robust JSON IO
# -------------------------
def _debug(msg: str) -> None:
    if os.getenv("DEBUG", "").strip() in {"1", "true", "TRUE", "yes", "YES"}:
        print(msg)


def read_text_safely(path: Path) -> str:
    """
    Read text from disk even if it was accidentally saved as UTF-16 or UTF-8 with BOM.
    Raises if content is truly not decodable.
    """
    b = path.read_bytes()

    # UTF-16 BOM (LE/BE)
    if b.startswith(b"\xff\xfe") or b.startswith(b"\xfe\xff"):
        _debug(f"[read_text_safely] {path} detected UTF-16 BOM")
        return b.decode("utf-16")

    # UTF-8 BOM
    if b.startswith(b"\xef\xbb\xbf"):
        _debug(f"[read_text_safely] {path} detected UTF-8 BOM")
        return b.decode("utf-8-sig")

    # Plain UTF-8
    return b.decode("utf-8", errors="strict")


def read_json_safely(path: Path) -> Any:
    if not path.exists():
        return None
    text = read_text_safely(path)
    return json.loads(text)


def write_json_utf8(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8", newline="\n")


# -------------------------
# Council
# -------------------------
@dataclass(frozen=True)
class CouncilMember:
    name: str
    domain_bias: list[str]
    stance: str
    cadence: str


def build_council() -> list[CouncilMember]:
    """
    Bulletproof minimal council list. Expand later (121 etc).
    """
    base = [
        CouncilMember(GLYPH_NAME, ["systems", "power", "technology"], "constraint-first realism; convert chaos into structure", "severe minimal"),
        CouncilMember("Nina Simone", ["culture", "justice", "music"], "moral confrontation; truth over comfort", "blues-fire"),
        CouncilMember("James Baldwin", ["culture", "identity", "society"], "clarity under pressure; name the lie precisely", "sermon-knife"),
        CouncilMember("Sun Tzu", ["war", "strategy", "statecraft"], "win by position and timing; spend force wisely", "laconic"),
        CouncilMember("Miyamoto Musashi", ["war", "discipline", "craft"], "mastery through practice; cut what’s unnecessary", "cold-precise"),
        CouncilMember("Mary Shelley", ["art", "science", "ethics"], "creation carries consequence; responsibility is the frame", "gothic-clarity"),
        CouncilMember("Victor Hugo", ["politics", "humanity", "history"], "see the people; make the age visible", "grand-orator"),
    ]

    names = [m.name for m in base]
    if names.count(GLYPH_NAME) != 1:
        raise SystemExit("Council must include Glyph exactly once.")
    return base


# -------------------------
# State (rotation)
# -------------------------
def load_or_init_state(council_names: list[str]) -> dict:
    ENGINE_DIR.mkdir(parents=True, exist_ok=True)

    if STATE_PATH.exists():
        try:
            state = read_json_safely(STATE_PATH)
            if isinstance(state, dict) and "rotation" in state and "pointer" in state:
                # sanity
                if not isinstance(state.get("rotation"), list):
                    raise ValueError("rotation not list")
                if not isinstance(state.get("pointer"), int):
                    raise ValueError("pointer not int")
                return state
        except Exception as e:
            _debug(f"[state] Failed to read state.json safely: {e}. Reinitializing.")

    # fresh state
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


def pick_today_winner(dt: datetime, state: dict) -> tuple[str, bool]:
    mmdd = dt.strftime("%m-%d")
    if mmdd == SPECIAL_ELLIS_MMDD:
        return ELLIS_NAME, True
    if mmdd == SPECIAL_GLYPH_MMDD:
        return GLYPH_NAME, True

    rotation = state["rotation"]
    pointer = state["pointer"]

    if not rotation:
        return GLYPH_NAME, False

    pointer = pointer % len(rotation)
    return rotation[pointer], False


def advance_rotation(state: dict) -> None:
    rotation = state.get("rotation", [])
    if not rotation:
        return
    state["pointer"] = int(state.get("pointer", 0)) + 1
    if state["pointer"] >= len(rotation):
        state["pointer"] = 0
        state["cycles_completed"] = int(state.get("cycles_completed", 0)) + 1


# -------------------------
# Reports paths
# -------------------------
def utc_today() -> datetime:
    return datetime.now(timezone.utc)


def date_path(dt: datetime) -> Path:
    yyyy = dt.strftime("%Y")
    mm = dt.strftime("%m")
    ymd = dt.strftime("%Y-%m-%d")
    return REPORTS_DIR / yyyy / mm / f"{ymd}.json"


def ensure_reports_dirs(dt: datetime) -> None:
    (REPORTS_DIR / dt.strftime("%Y") / dt.strftime("%m")).mkdir(parents=True, exist_ok=True)


# -------------------------
# Intake + Report gen
# -------------------------
def web_intake(client: OpenAI, dt: datetime) -> str:
    prompt = f"""
Date (UTC): {dt.strftime('%Y-%m-%d')}
Task: Collect a tension-weighted snapshot of today's civilization across finance, war/geopolitics, technology, culture, science.
Rules:
- Prefer structural stress, acceleration, fracture, regime change, technological leaps.
- Avoid gossip/fluff.
- Output 8-12 bullet signals, each 1 sentence max.
"""

    # Use web_search when available; if tool fails, fallback to model-only text.
    try:
        resp = client.responses.create(
            model="gpt-5",
            tools=[{"type": "web_search"}],
            input=prompt,
        )
        return (resp.output_text or "").strip()
    except Exception as e:
        _debug(f"[web_intake] web_search failed ({e}); falling back to model-only.")
        resp = client.responses.create(
            model="gpt-5",
            input=prompt + "\n(If you cannot browse, infer cautiously and mark uncertainty.)",
        )
        return (resp.output_text or "").strip()


def generate_report(client: OpenAI, dt: datetime, council: list[CouncilMember], winner_name: str, signals: str) -> dict:
    council_names = [m.name for m in council]

    # If winner isn't in council (because council list incomplete), force Glyph.
    if winner_name != ELLIS_NAME and winner_name not in council_names:
        winner_name = GLYPH_NAME

    # Choose 7 voices total: Glyph + winner + 5 others (if available)
    pool = [m for m in council if m.name not in {GLYPH_NAME, winner_name}]
    rng = random.Random(int(dt.strftime("%Y%m%d")))  # deterministic per day
    sampled = rng.sample(pool, k=min(5, len(pool)))

    voices: list[CouncilMember] = []
    voices.append(next(m for m in council if m.name == GLYPH_NAME))

    if winner_name == ELLIS_NAME:
        voices.append(CouncilMember(ELLIS_NAME, ["proctor-head"], "stewardship; scope; coherence; craft as duty", "plain-iron"))
    else:
        voices.append(next(m for m in council if m.name == winner_name))

    voices.extend(sampled)
    voices = voices[:7]

    voice_cards = "\n".join(
        [f"- {v.name}: bias={','.join(v.domain_bias)}; stance={v.stance}; cadence={v.cadence}" for v in voices]
    )

    instructions = f"""
You are "Gold Umbrella / The Round Table" engine.

OUTPUT RULE:
- Output strict JSON only.
- No markdown.
- No commentary.
- No extra keys.

Required top-level keys:
- date (YYYY-MM-DD)
- cultural_diagnosis (string)
- agon (object)
- mandate (string)
- artifact (object)
- engine_version (string)

Hard frame:
- cultural_diagnosis: essay (Proctor lens + includes short debate snippets from 7 voices)
- agon: include "winner" and a tight summary; winner MUST be "{winner_name}"
- mandate: 8-hour composition command (direct, executable, no fluff)
- artifact: {{ "status": "PENDING", "link": "" }}
- engine_version: "{ENGINE_VERSION}"

Debate format inside cultural_diagnosis:
- Start with a neutral Proctor field summary (2-4 short paragraphs).
- Then include exactly 7 short labeled voice blocks (1 paragraph each) using the roster below.
- End with a brief Proctor adjudication and transition into the winner.

Tone: severe minimal. Controlled rhetoric only.

Voice roster (exactly these 7 today):
{voice_cards}

Field signals (today's intake):
{signals}
"""

    resp = client.responses.create(
        model="gpt-5",
        input=instructions,
    )
    text = (resp.output_text or "").strip()

    data = json.loads(text)

    # Force invariants (even if model slips)
    data["date"] = dt.strftime("%Y-%m-%d")
    data["engine_version"] = ENGINE_VERSION
    data.setdefault("artifact", {"status": "PENDING", "link": ""})

    # Force winner
    if "agon" not in data or not isinstance(data["agon"], dict):
        data["agon"] = {}
    data["agon"]["winner"] = winner_name

    return data


# -------------------------
# Index + Latest (the part that keeps breaking)
# -------------------------
def update_indexes(dt: datetime, daily_path: Path) -> None:
    index_path = REPORTS_DIR / "index.json"
    latest_path = REPORTS_DIR / "latest.json"

    # Read index safely (or init)
    index: dict
    if index_path.exists():
        try:
            loaded = read_json_safely(index_path)
            if isinstance(loaded, dict) and isinstance(loaded.get("dates"), list):
                index = loaded
            else:
                index = {"dates": []}
        except Exception as e:
            _debug(f"[update_indexes] index.json unreadable ({e}); resetting.")
            index = {"dates": []}
    else:
        index = {"dates": []}

    ymd = dt.strftime("%Y-%m-%d")
    if ymd not in index["dates"]:
        index["dates"].append(ymd)
    index["dates"] = sorted(index["dates"], reverse=True)

    write_json_utf8(index_path, index)

    # latest.json is a JSON copy of today's report (read safe, write utf-8)
    latest_obj = read_json_safely(daily_path)
    if latest_obj is None:
        latest_obj = {"status": "EMPTY"}
    write_json_utf8(latest_path, latest_obj)


# -------------------------
# Main
# -------------------------
def main() -> None:
    # OpenAI SDK reads OPENAI_API_KEY from env automatically, but we fail loudly if missing.
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("OPENAI_API_KEY is missing (set in GitHub repo Secrets).")

    client = OpenAI()
    council = build_council()
    dt = utc_today()

    ensure_reports_dirs(dt)

    council_names = [m.name for m in council if m.name != ELLIS_NAME]
    state = load_or_init_state(council_names)

    winner_name, is_special = pick_today_winner(dt, state)

    signals = web_intake(client, dt)
    report = generate_report(client, dt, council, winner_name, signals)

    out_path = date_path(dt)

    # Immutable by policy: do not overwrite.
    if out_path.exists():
        raise SystemExit(f"Refusing to overwrite existing report: {out_path}")

    write_json_utf8(out_path, report)

    update_indexes(dt, out_path)

    if not is_special:
        advance_rotation(state)
        write_json_utf8(STATE_PATH, state)

    print(f"OK: wrote {out_path}")


if __name__ == "__main__":
    main()
