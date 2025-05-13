#!/usr/bin/false

import re
from collections import Counter
from typing import Dict, List, Tuple

from rapidfuzz import fuzz
from rapidfuzz import utils as fuzzutils
from sonarr_api import is_monitored_episode
from util import date_distance_days


def extract_episode_hint(title: str) -> Tuple[int, int]:
    """Attempts to parse season and episode numbers from the title."""
    patterns = [
        r"[Ss](\d+)[Ee](\d+)",  # S2E3
        r"[Ss]eason[^\d]*(\d+)[^\d]+Episode[^\d]*(\d+)",  # Season 2 Episode 3
        r"[Ss](\d+)[^\d]+Ep(?:isode)?[^\d]*(\d+)",  # S2 Ep 3
        r"[Ee]pisode[^\d]*(\d+)",  # Episode 3
        r"[Ee]p[^\d]*(\d+)",  # Ep 3
    ]
    for pattern in patterns:
        match = re.search(pattern, title, re.IGNORECASE)
        if match:
            groups = match.groups()
            if len(groups) == 2:
                return int(groups[0]), int(groups[1])
            elif len(groups) == 1:
                return -1, int(groups[0])
    return -1, -1


def build_token_frequencies(sonarr_data: List[Dict]) -> Dict[str, int]:
    token_counts = Counter()
    for entry in sonarr_data:
        tokens = fuzzutils.default_process(entry["title"]).split()
        token_counts.update(tokens)
    return token_counts


def compute_weighted_overlap(
    input_tokens: set, candidate_tokens: set, freq_map: Dict[str, int]
) -> float:
    if not candidate_tokens:
        return 0.0

    total_weight = 0
    overlap_weight = 0

    for token in candidate_tokens:
        # Inverse frequency weight: more rare = more important
        weight = 1 / freq_map.get(token, 1)
        total_weight += weight
        if token in input_tokens:
            overlap_weight += weight

    return overlap_weight / total_weight if total_weight > 0 else 0


def score_candidate(
    main_title: str,
    season: int,
    episode: int,
    candidate: Dict,
    token_freq: Dict[str, int],
) -> Tuple[int, str]:
    score = 0
    reasons = []

    if season != -1 and episode != -1:
        if candidate["season"] == season and candidate["episode"] == episode:
            score += 50
            reasons.append("season/episode exact match")
        else:
            reasons.append("season/episode mismatch")

    input_tokens = set(fuzzutils.default_process(main_title).split())
    candidate_tokens = set(fuzzutils.default_process(candidate["title"]).split())

    token_score = fuzz.token_set_ratio(main_title, candidate["title"])
    weighted_recall = compute_weighted_overlap(
        input_tokens, candidate_tokens, token_freq
    )

    score += int(token_score * 0.3)  # Up to 30
    score += int(weighted_recall * 70)  # Up to 70

    # Penalize missed tokens (input expected but not found)
    missed_tokens = input_tokens - candidate_tokens
    missed_penalty = len(missed_tokens) * 5
    score -= missed_penalty
    reasons.append(f"missed tokens: {len(missed_tokens)} (-{missed_penalty})")

    # Penalize extra tokens (unexpected tokens in candidate)
    extra_tokens = candidate_tokens - input_tokens
    extra_penalty = len(extra_tokens) * 2.5  # Lighter penalty per extra token
    score -= int(extra_penalty)
    reasons.append(f"extra tokens: {len(extra_tokens)} (-{int(extra_penalty)})")

    reasons.append(f"token set similarity: {token_score}%")
    reasons.append(f"weighted keyword recall: {int(weighted_recall * 100)}%")

    return score, "; ".join(reasons)


def clean_text(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9\s]", "", text).lower()


def clean_sonarr_data(sonarr_data):
    return [
        {
            **entry,
            "series": clean_text(entry.get("series", "")),
            "title": clean_text(entry.get("title", "")),
            "orig_title": entry.get("title", ""),
        }
        for entry in sonarr_data
    ]


def match_title_to_sonarr_episode(
    main_title: str, airdate: str, sonarr_data: List[Dict]
) -> Dict:
    """Attempts to match a streaming title to a Sonarr entry with weighted keyword and date proximity scoring."""
    cleaned_title = clean_text(main_title)
    cleaned_data = clean_sonarr_data(sonarr_data)

    token_freq = build_token_frequencies(cleaned_data)
    season, episode = extract_episode_hint(cleaned_title)

    best_match = None
    best_score = -1
    best_reason = ""

    for candidate in cleaned_data:
        score, reason = score_candidate(
            cleaned_title, season, episode, candidate, token_freq
        )

        # Date distance bonus
        episode_date = candidate.get("air_date")
        if episode_date != 0:
            date_gap = date_distance_days(airdate, episode_date)
            if date_gap >= 0:
                # Closer dates = higher score boost (e.g. linear penalty)
                date_score_bonus = max(0, 50.0 - (date_gap * 25))
                score += date_score_bonus
                reason += f"; date_gap={date_gap}d (bonus={date_score_bonus:.2f})"
            else:
                reason += "; no airdate match"

        # Monitored bonus
        if score > 70 and is_monitored_episode(
            candidate["series_id"], candidate["season"], candidate["episode"]
        ):
            score += 1

        if score > best_score:
            best_match = candidate
            best_score = score
            best_reason = reason

    return {
        "input": main_title,
        "matched_show": best_match["series"] if best_match else None,
        "season": best_match["season"] if best_match else None,
        "episode": best_match["episode"] if best_match else None,
        "episode_title": best_match["title"] if best_match else None,
        "episode_orig_title": best_match["orig_title"] if best_match else None,
        "score": best_score,
        "reason": best_reason,
    }


def match_title_to_sonarr_show(main_title: str, sonarr_shows) -> Dict:
    """Matches a streaming title to the best-matching Sonarr show using strict verbatim and token-based scoring."""
    input_tokens = set(fuzzutils.default_process(main_title).split())

    best_match = None
    best_score = -1
    best_reason = ""
    best_id = ""

    for show_title, show_id in set(sonarr_shows):
        processed_show = fuzzutils.default_process(show_title)
        show_tokens = set(processed_show.split())

        # Priority boost if show name appears verbatim
        verbatim_match = processed_show in fuzzutils.default_process(main_title)
        verbatim_bonus = 35 + len(show_title) if verbatim_match else 0

        # Token similarity and keyword overlap
        token_score = fuzz.token_set_ratio(main_title, show_title)
        keyword_overlap = (
            len(show_tokens & input_tokens) / len(show_tokens) if show_tokens else 0
        )

        score = verbatim_bonus + int(token_score * 0.10) + int(keyword_overlap * 50)

        reason = (
            f"{'verbatim match; ' if verbatim_match else ''}"
            f"token set similarity: {token_score}%, "
            f"keyword overlap: {int(keyword_overlap * 100)}%"
        )

        if score > best_score:
            best_id = show_id
            best_match = show_title
            best_score = score
            best_reason = reason

    return {
        "input": main_title,
        "matched_id": best_id,
        "matched_show": best_match,
        "score": best_score,
        "reason": best_reason,
    }
