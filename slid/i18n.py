"""UI strings and language detection.

The language picks the UI strings *and* the word list, so each language has its
own daily puzzle. It comes from, in order: a `?lang=` query parameter (shared
links carry it, so they open the same puzzle the sharer played), the `slid_lang`
cookie (set only when the player picks one), then the browser's Accept-Language.
"""

from fastapi import Request

from .words import WORDS

LANGS = {"en": "English", "pt-BR": "Português"}
DEFAULT = "en"
COOKIE = "slid_lang"

# Values may contain trusted HTML (rendered with |safe). "{n}"-style placeholders are filled in JS.
STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "description": "A new word sliding puzzle every day.",
        "today_link": "Slid, today's game",
        "past_games": "Past games",
        "mute": "Mute sounds",
        "unmute": "Unmute sounds",
        "how_to_play": "How to play",
        "language": "Language",
        "step_slide": "Tap a tile next to the empty space to slide it in, or swipe it. Arrow keys and "
        "<kbd>WASD</kbd> work too.",
        "step_push": "Swipe a tile further along the same row or column and every tile between it and the "
        "empty space moves with it.",
        "step_spell": "Spell the word <b>left to right</b> in a row or <b>top to bottom</b> in a column.",
        "step_short": "A 3-letter word only counts when the empty space completes its row or column.",
        "step_moves": "Every tile that moves counts as a move. The fewer moves, the better your score.",
        "step_challenge": "Each day has a challenge: a number of moves we know it can be solved in. "
        "Match it, or beat it.",
        "step_daily": "There's a new word every day, and every past day stays open in the calendar.",
        "lets_play": "Let's play",
        "prev_month": "Previous month",
        "next_month": "Next month",
        "won": "Solved",
        "playing": "In progress",
        "not_played": "Not played",
        "challenge": "Challenge: {n}",
        "streak_one": "{n}-day streak",
        "streak_other": "{n}-day streak",
        "streak_pending": "Solve today's word to keep it going",
        "share_streak": "🔥 {n} days",
        "challenge_hint": "This word can be solved in {n} moves. Can you match it?",
        "challenge_beaten": "You beat the challenge of {n} moves!",
        "challenge_matched": "You matched the challenge of {n} moves.",
        "challenge_missed": "The challenge was {n} moves.",
        "target_word": "Target word: {word}",
        "tile_label": "{letter}, row {row}, column {col}",
        "move_one": "move",
        "move_other": "moves",
        "solved_title": "Solved!",
        "next_word": "Next word in",
        "share": "Share",
        "copied": "Copied!",
    },
    "pt-BR": {
        "description": "Um quebra-cabeça de palavras deslizantes novo todo dia.",
        "today_link": "Slid, jogo de hoje",
        "past_games": "Jogos anteriores",
        "mute": "Desativar sons",
        "unmute": "Ativar sons",
        "how_to_play": "Como jogar",
        "language": "Idioma",
        "step_slide": "Toque em uma peça ao lado do espaço vazio, ou arraste-a, para deslizá-la. "
        "As setas e <kbd>WASD</kbd> também funcionam.",
        "step_push": "Arraste uma peça mais distante na mesma linha ou coluna e todas as peças entre ela e o "
        "espaço vazio vão junto.",
        "step_spell": "Forme a palavra <b>da esquerda para a direita</b> em uma linha "
        "ou <b>de cima para baixo</b> em uma coluna.",
        "step_short": "Uma palavra de 3 letras só vale quando o espaço vazio completa a linha ou coluna dela.",
        "step_moves": "Cada peça que se move conta como um movimento. Quanto menos movimentos, melhor.",
        "step_challenge": "Todo dia tem um desafio: um número de movimentos em que sabemos que dá para resolver. "
        "Iguale ou supere.",
        "step_daily": "Todo dia tem uma palavra nova, e todos os dias anteriores ficam disponíveis no calendário.",
        "lets_play": "Vamos jogar",
        "prev_month": "Mês anterior",
        "next_month": "Próximo mês",
        "won": "Resolvido",
        "playing": "Em andamento",
        "not_played": "Não jogado",
        "challenge": "Desafio: {n}",
        "streak_one": "Sequência de {n} dia",
        "streak_other": "Sequência de {n} dias",
        "streak_pending": "Resolva a palavra de hoje para mantê-la",
        "share_streak": "🔥 {n} dias",
        "challenge_hint": "Esta palavra pode ser resolvida em {n} movimentos. Você consegue?",
        "challenge_beaten": "Você superou o desafio de {n} movimentos!",
        "challenge_matched": "Você igualou o desafio de {n} movimentos.",
        "challenge_missed": "O desafio era de {n} movimentos.",
        "target_word": "Palavra: {word}",
        "tile_label": "{letter}, linha {row}, coluna {col}",
        "move_one": "movimento",
        "move_other": "movimentos",
        "solved_title": "Resolvido!",
        "next_word": "Próxima palavra em",
        "share": "Compartilhar",
        "copied": "Copiado!",
    },
}

assert all(STRINGS[lang].keys() == STRINGS[DEFAULT].keys() for lang in LANGS), "every language needs every key"
assert LANGS.keys() == WORDS.keys(), "every language needs a word list"


def _match(tag: str) -> str | None:
    tag = tag.strip().lower()
    for lang in LANGS:  # "pt", "pt-PT" and "pt-BR" all get Brazilian Portuguese for now
        if tag == lang.lower() or tag.split("-")[0] == lang.lower().split("-")[0]:
            return lang
    return None


def from_accept_language(header: str) -> str:
    """Best supported language from an Accept-Language header, honouring q-values."""
    tags = []
    for i, part in enumerate(header.split(",")):
        tag, _, params = part.partition(";")
        q = 1.0
        if params.strip().startswith("q="):
            try:
                q = float(params.strip()[2:])
            except ValueError:
                q = 0.0
        tags.append((-q, i, tag))
    for _, _, tag in sorted(tags):
        if lang := _match(tag):
            return lang
    return DEFAULT


def pick(request: Request) -> str:
    for value in (request.query_params.get("lang"), request.cookies.get(COOKIE)):
        if value in LANGS:
            return value
    return from_accept_language(request.headers.get("accept-language", ""))
