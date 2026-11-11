"""Refusals and errors in the language of the question (config/refusals.csv)."""

import csv
import importlib.util
import logging
from pathlib import Path

import markdown
import pytest

from just_os import messages
from test_qualle import make_qualle, node

TR_OFF_TOPIC = "Akademide kariyer ilerlemesi için hangi beceriler gereklidir?"
KN_OFF_TOPIC = "ಶೈಕ್ಷಣಿಕ ವೃತ್ತಿಜೀವನದಲ್ಲಿ ಮುನ್ನಡೆಯಲು ಯಾವ ಕೌಶಲ್ಯಗಳು ಬೇಕು?"
ES_OFF_TOPIC = "¿Qué habilidades se necesitan para avanzar en la carrera académica?"


def table():
    return messages.messages()


# --- the CSV the maintainer edits


def test_every_row_of_the_csv_is_valid():
    with open(messages.MESSAGES_FILE, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    assert list(rows[0]) == ["language", *messages.MESSAGE_KEYS]
    for row in rows:
        assert messages.row_problems(row) == [], row["language"]
    assert len(table()) == len(rows)


def test_texts_survive_markdown():
    # eval/run.py finds a refusal by its text inside the HTML message
    for key in messages.MESSAGE_KEYS:
        for text in messages.all_texts(key):
            assert text in markdown.markdown(text)


def write_csv(path, rows):
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["language", *messages.MESSAGE_KEYS])
        writer.writerows(rows)


def test_bad_row_is_skipped(tmp_path, caplog):
    path = tmp_path / "refusals.csv"
    full = ["a", "b", "c", "d", "e"]
    write_csv(path, [["en", *full], ["xx", *full], ["tr", "a", "", "c", "d", "e"], ["it", *full]])
    with caplog.at_level(logging.ERROR):
        loaded = messages.load_messages(path)
    assert set(loaded) == {"en", "it"}
    assert "line 3" in caplog.text and "line 4" in caplog.text


def test_row_with_an_unquoted_comma_is_skipped(tmp_path, caplog):
    # An unquoted comma splits a text in two, so every later text moves one column
    path = tmp_path / "refusals.csv"
    write_csv(path, [["en", "a", "b", "c", "d", "e"], ["it", "Mi dispiace", " posso", "b", "c", "d", "e"]])
    with caplog.at_level(logging.ERROR):
        loaded = messages.load_messages(path)
    assert set(loaded) == {"en"}
    assert "line 3" in caplog.text and "1 field too many" in caplog.text


def test_second_row_for_a_language_is_skipped(tmp_path, caplog):
    path = tmp_path / "refusals.csv"
    write_csv(path, [["en", "a", "b", "c", "d", "e"], ["EN", "x", "b", "c", "d", "e"]])
    with caplog.at_level(logging.ERROR):
        loaded = messages.load_messages(path)
    assert loaded["en"]["off_topic"] == "a"
    assert "line 3" in caplog.text and "second row" in caplog.text


def test_english_row_is_required(tmp_path):
    path = tmp_path / "refusals.csv"
    write_csv(path, [["it", "a", "b", "c", "d", "e"]])
    with pytest.raises(ValueError):
        messages.load_messages(path)


# --- detection


@pytest.mark.parametrize(
    "question, language",
    [
        ("What are the key skills needed for career advancement in academia?", "en"),
        (TR_OFF_TOPIC, "tr"),
        (KN_OFF_TOPIC, "kn"),
        ("Was ist Präregistrierung und warum ist sie wichtig?", "de"),
        ("Hoe kan ik kwalitatief onderzoek preregistreren?", "nl"),
        ("Cos'è la preregistrazione?", "it"),
        ("पूर्वनोंदणी म्हणजे काय आणि ती का महत्त्वाची आहे?", "mr"),
        ("पूर्व-पंजीकरण क्या है और यह क्यों महत्वपूर्ण है?", "hi"),
    ],
)
def test_detects_the_language(question, language):
    assert messages.detect_language(question) == language


def test_language_without_a_row_gets_english():
    # Spanish has no row; detecting over all languages keeps it from passing for Italian
    assert messages.detect_language(ES_OFF_TOPIC) == "es"
    assert messages.message("off_topic", ES_OFF_TOPIC) == table()["en"]["off_topic"]


def test_undetectable_text_gets_english():
    assert messages.message("off_topic", "???") == table()["en"]["off_topic"]
    assert messages.message("off_topic", "") == table()["en"]["off_topic"]


# --- the pipeline answers in the language of the question


def test_off_topic_refusal_in_turkish():
    q = make_qualle(False, [], [], "unused")
    final = list(q.get_response(TR_OFF_TOPIC, "chat"))[-1]
    assert final["status"] == "complete"
    assert table()["tr"]["off_topic"] in final["message"]


def test_no_sources_in_kannada():
    q = make_qualle(True, [], [], "unused")
    final = list(q.get_response(KN_OFF_TOPIC, "chat"))[-1]
    assert table()["kn"]["no_sources"] in final["message"]
    assert q.chat_manager.messages[-1]["content"] == table()["kn"]["no_sources"]


def test_model_unavailable_in_turkish():
    q = make_qualle(None, [], [], "unused")
    final = list(q.get_response(TR_OFF_TOPIC, "chat"))[-1]
    assert final["status"] == "error"
    assert table()["tr"]["model_unavailable"] in final["message"]


def test_english_refusal_unchanged():
    q = make_qualle(False, [], [], "unused")
    final = list(q.get_response("How do I bake bread?", "chat"))[-1]
    assert final["message"] == "<p>Sorry, I'm only able to answer questions related to Open Science.</p>"


def test_arena_refusal_in_turkish():
    q = make_qualle(False, [], [], "unused")
    final = list(q.get_arena_response(TR_OFF_TOPIC, ["a", "b"]))[-1]
    assert table()["tr"]["off_topic"] in final["message"]


def test_generation_error_in_turkish():
    q = make_qualle(True, [node("Paper")], [node("Paper")], "")  # the answer model returns nothing
    final = list(q.get_response(TR_OFF_TOPIC, "chat"))[-1]
    assert table()["tr"]["generation_error"] in final["message"]


def test_unexpected_error_in_turkish():
    q = make_qualle(True, [], [], "unused")

    def fail(query):
        raise RuntimeError("index broken")

    q.document_retriever.retrieve_and_rerank = fail
    final = list(q.get_response(TR_OFF_TOPIC, "chat"))[-1]
    assert final["status"] == "error"
    assert table()["tr"]["unexpected_error"] in final["message"]
    arena = list(q.get_arena_response(TR_OFF_TOPIC, ["a"]))[-1]
    assert table()["tr"]["unexpected_error"] in arena["message"]


# --- eval/run.py counts a refusal in any language as a refusal


def test_eval_outcome_recognises_translated_refusals():
    spec = importlib.util.spec_from_file_location(
        "eval_run", Path(__file__).resolve().parent.parent / "eval" / "run.py"
    )
    run = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(run)
    for texts in table().values():
        refusal = {"status": "complete", "message": markdown.markdown(texts["off_topic"])}
        no_sources = {"status": "complete", "message": markdown.markdown(texts["no_sources"])}
        assert run.outcome_of(refusal) == "refused"
        assert run.outcome_of(no_sources) == "no_sources"
    assert run.outcome_of({"status": "complete", "message": "<p>An answer [0].</p>"}) == "answered"
