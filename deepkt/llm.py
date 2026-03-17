"""LLM integration — Claude Haiku for genre analysis and artist expansion."""

import json
import os

import anthropic

MODEL = "claude-haiku-4-5-20251001"

def _build_step1(artists: list[str], user_query: str | None) -> str:
    parts = []
    if artists:
        parts.append(f"I really like these artists: {', '.join(artists)}.")
    if user_query:
        parts.append(f"The vibe I'm going for: {user_query}")
    parts.append(
        "\nCome up with a list of 100 artists that reside in the same space as them, "
        "and come up with the 10 best tags for finding similar music on SoundCloud "
        "— very specific tags for that genre.\n\n"
        'Return ONLY valid JSON:\n'
        '{"artists": ["Artist1", "Artist2", "...100 total"], "tags": ["tag1", "tag2", "...10 total"]}'
    )
    return "\n".join(parts)


def _build_step2(artists: list[str], user_query: str | None, step1_json: str) -> str:
    original = ", ".join(artists) if artists else user_query or ""
    return (
        f"Here are the original artists the user likes: {original}\n\n"
        f"Here is a list of 100 similar artists and genre tags:\n{step1_json}\n\n"
        "Rank the 100 artists by how similar they are to the genre/scene of the "
        "original artists. Return ONLY the top 30, with a one-sentence reason for each.\n\n"
        'Return ONLY valid JSON:\n'
        '{"status": "success", "tags": ["tag1", "...10 total"], '
        '"seed_artists": [{"name": "Artist", "reason": "why they fit"}], '
        '"filtered_out": [{"artist": "Name", "reason": "why excluded"}]}'
    )


def _parse_json(raw_text: str) -> dict | None:
    """Extract JSON from LLM response, handling markdown code blocks."""
    raw_text = raw_text.strip()
    if raw_text.startswith("```"):
        lines = raw_text.split("\n")
        json_lines = []
        in_block = False
        for line in lines:
            if line.strip().startswith("```") and not in_block:
                in_block = True
                continue
            elif line.strip() == "```" and in_block:
                break
            elif in_block:
                json_lines.append(line)
        raw_text = "\n".join(json_lines)
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        return None


def analyze_artists(artists: list[str], tracks: list[dict] | None = None,
                    user_query: str | None = None) -> dict:
    """Two-step analysis: generate 100 candidates, then rank down to top 30."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return {
            "status": "failed",
            "tags": [],
            "seed_artists": [],
            "message": "LLM service not configured (ANTHROPIC_API_KEY not set)",
            "filtered_out": [],
        }

    if len(artists) < 3 and not user_query:
        return {
            "status": "failed",
            "tags": [],
            "seed_artists": [],
            "message": f"Need at least 3 artists, got {len(artists)}.",
            "filtered_out": [],
        }

    client = anthropic.Anthropic(api_key=api_key)

    # Step 1: Generate 100 artists + 10 tags
    step1_msg = _build_step1(artists, user_query)
    resp1 = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        messages=[{"role": "user", "content": step1_msg}],
    )
    step1_raw = resp1.content[0].text
    step1 = _parse_json(step1_raw)

    if not step1:
        return {
            "status": "failed",
            "tags": [],
            "seed_artists": [],
            "message": f"Step 1 failed to parse: {step1_raw[:200]}",
            "filtered_out": [],
        }

    # Step 2: Rank and pick top 30
    step2_msg = _build_step2(artists, user_query, json.dumps(step1))
    resp2 = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        messages=[{"role": "user", "content": step2_msg}],
    )
    step2_raw = resp2.content[0].text
    result = _parse_json(step2_raw)

    if not result:
        return {
            "status": "failed",
            "tags": step1.get("tags", []),
            "seed_artists": [],
            "message": f"Step 2 failed to parse: {step2_raw[:200]}",
            "filtered_out": [],
        }

    return {
        "status": result.get("status", "success"),
        "tags": result.get("tags", step1.get("tags", [])),
        "seed_artists": result.get("seed_artists", []),
        "message": result.get("message"),
        "filtered_out": result.get("filtered_out", []),
    }
