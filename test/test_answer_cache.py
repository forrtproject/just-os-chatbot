import fakeredis

from just_os import qualle
from just_os.answer_cache import AnswerCache
from test_qualle import CONFIG, FakeClient, completion, make_qualle, node

VECTORS = {
    "What is preregistration?": [1.0, 0.0, 0.0],
    "what is preregistration": [0.99, 0.05, 0.0],  # nearly the same question
    "What is open data?": [0.0, 1.0, 0.0],
}


class FakeEmbed:
    def get_query_embedding(self, query):
        return VECTORS[query]


def cache(ttl=3600, **config):
    settings = {
        "ANSWER_CACHE_TTL": ttl,
        "ANSWER_CACHE_MIN_SIMILARITY": 0.95,
        "ANSWER_CACHE_MAX_ITEMS": 2,
        "CITATION_MODEL": "m",
        **config,
    }
    return AnswerCache(fakeredis.FakeRedis(), FakeEmbed(), settings)


def test_similar_question_hits_and_different_question_misses():
    c = cache()
    c.store("What is preregistration?", {"status": "complete", "message": "A"}, "A")
    assert c.lookup("what is preregistration")["response"]["message"] == "A"
    assert c.lookup("What is open data?") is None


def test_expired_entries_are_ignored():
    c = cache(ttl=-1)  # every entry is already too old
    c.store("What is preregistration?", {"message": "A"}, "A")
    assert c.lookup("What is preregistration?") is None


def test_other_model_has_its_own_cache():
    redis = fakeredis.FakeRedis()
    settings = {"ANSWER_CACHE_TTL": 60, "ANSWER_CACHE_MIN_SIMILARITY": 0.9, "ANSWER_CACHE_MAX_ITEMS": 5}
    a = AnswerCache(redis, FakeEmbed(), {**settings, "CITATION_MODEL": "a"})
    b = AnswerCache(redis, FakeEmbed(), {**settings, "CITATION_MODEL": "b"})
    a.store("What is preregistration?", {"message": "A"}, "A")
    assert b.lookup("What is preregistration?") is None


def test_cache_keeps_at_most_max_items():
    c = cache()
    for q in VECTORS:
        c.store(q, {"message": q}, q)
    assert c.redis.llen(c.key) == 2


def test_second_similar_question_makes_no_llm_call():
    q = make_qualle(True, [node("Paper")], [node("Paper")], "Answer [0].")
    q.answer_cache = cache()
    first = list(q.get_response("What is preregistration?", "chat-1"))[-1]
    calls = len(q.response_generator.client_manager.calls)

    second = list(q.get_response("what is preregistration", "chat-2"))[-1]

    assert second == first
    assert len(q.response_generator.client_manager.calls) == calls


def test_short_prompt_style():
    client = FakeClient(completion(content="x"))
    generator = qualle.ResponseGenerator(client, {**CONFIG, "PROMPT_STYLE": "short"}, None)
    generator.generate_response("question", "[0] Title: T Text: t")
    messages = client.calls[0]["messages"]
    assert messages[0]["content"] == qualle.SHORT_SYSTEM_PROMPT + " " + qualle.LANGUAGE_RULE
    assert "Question: question" in messages[1]["content"]


def test_openscholar_prompt_is_default():
    generator = qualle.ResponseGenerator(FakeClient(), CONFIG, None)
    assert not generator.system_prompt.startswith(qualle.SHORT_SYSTEM_PROMPT)


def test_both_prompt_styles_ask_for_the_question_language_and_english_terms():
    for style in ("openscholar", "short"):
        prompt = qualle.ResponseGenerator(FakeClient(), {**CONFIG, "PROMPT_STYLE": style}, None).system_prompt
        assert "language of the question" in prompt and "preregistration" in prompt and "HARKing" in prompt
