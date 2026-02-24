"""
Word cloud generation logic.
Extracts keywords from X list names, scores by frequency, and deduplicates.
"""
import re
from collections import Counter

# Common stop words to filter out of list names
STOP_WORDS = {
    'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
    'of', 'with', 'by', 'from', 'is', 'it', 'as', 'are', 'was', 'were',
    'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did',
    'will', 'would', 'could', 'should', 'may', 'might', 'shall', 'can',
    'not', 'no', 'nor', 'so', 'if', 'then', 'than', 'too', 'very',
    'just', 'about', 'above', 'after', 'again', 'all', 'also', 'am',
    'any', 'because', 'before', 'between', 'both', 'each', 'few',
    'more', 'most', 'other', 'out', 'over', 'own', 'same', 'some',
    'such', 'that', 'these', 'this', 'those', 'through', 'under',
    'until', 'up', 'we', 'what', 'when', 'where', 'which', 'while',
    'who', 'whom', 'why', 'you', 'your', 'my', 'me', 'i', 'he', 'she',
    'her', 'him', 'his', 'its', 'our', 'us', 'they', 'them', 'their',
    'list', 'lists', 'follow', 'following', 'followers',
}


def extract_word_scores(memberships: list[dict]) -> dict[str, int]:
    """
    Extract and score keywords from list names.

    Args:
        memberships: List of dicts with 'name', 'owner', 'id' keys.

    Returns:
        Dict of {word: frequency_count}, sorted descending by count.
    """
    word_counter = Counter()

    for m in memberships:
        name = m.get("name", "")
        # Clean: replace non-alphanumeric with spaces, split, filter short/stop words
        cleaned = re.sub(r'[^a-zA-Z0-9\s]', ' ', name.lower())
        tokens = cleaned.split()
        meaningful = [t for t in tokens if len(t) > 2 and t not in STOP_WORDS]
        word_counter.update(meaningful)

    # Sort by frequency descending, return as dict
    sorted_words = dict(word_counter.most_common(100))
    return sorted_words


def group_lists_by_word(word: str, memberships: list[dict]) -> list[dict]:
    """
    Given a word and all memberships, return the subset of lists
    whose names contain that word (case-insensitive).
    """
    results = []
    for m in memberships:
        if word.lower() in m.get("name", "").lower():
            results.append(m)
    return results
