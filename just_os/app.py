import glob
import json
import logging
import os
import random
import secrets
import threading
import re
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Generator, Optional

from flask import Flask, Response, abort, render_template, request, jsonify, send_file
from werkzeug.middleware.proxy_fix import ProxyFix
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.exceptions import TooManyRequests

from config.settings import get_config
from just_os.chat_manager import ChatManager
from just_os import criteria
from just_os import eval_report
from just_os.scores import SCALE as SCORE_SCALE, row as scores_row
from just_os.decisions import ROUTERS
from just_os.extensions import flask_static_digest
from just_os import messages as msg

# INFO shows the "Timing:" lines of each answer in `docker compose logs web`
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# a: A is better, b: B is better, tie: both are good, bad: both are bad
# Arena: each answer is rated on these criteria and scale (config/criteria.json, #54); the answer time is measured
ARENA_CRITERIA = criteria.ARENA
ARENA_LABELS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

APPEND_LOCK = threading.Lock()  # chat, feedback and arena logs (_append_jsonl)

# Review page (#8): per question one decision and scores on shared criteria and the same scale as the arena
# (config/criteria.json, #54), "n/a" when the bot gave no answer
REVIEW_DECISIONS = criteria.DECISIONS
REVIEW_CRITERIA = criteria.REVIEW
REVIEW_VALUES = ("", "n/a", *(str(v) for v in criteria.SCALE))
def review_rows(data: Dict[str, Any], items: Dict[str, Dict]) -> tuple:
    """(problem or None, score rows, #54) for a POST from /review:
    {"reviewer": name, "rubric": true when the rubric setting was on,
     "scores": {item key: {"decision", <criterion>: "1"-"5" or "n/a", "note", "rubric": {item id: "1"-"5"}}}}.
    One row per decision, criterion and rubric item scored, for the item's answer_id; the note goes with the
    first row of its answer."""
    reviewer = data.get("reviewer")
    scores = data.get("scores")
    if not isinstance(reviewer, str) or not reviewer.strip() or len(reviewer) > 80:
        return "Write your name (at most 80 characters) at the top.", []
    if not isinstance(scores, dict) or not scores or not set(scores) <= set(items):
        return "No scores, or scores for unknown questions.", []
    reviewer, setting = reviewer.strip(), "rubric" if data.get("rubric") is True else "default"
    rows, now = [], datetime.now(timezone.utc).isoformat(timespec="seconds")
    for item_key, s in scores.items():
        item = items[item_key]
        rubric = s.get("rubric", {}) if isinstance(s, dict) else None
        if not isinstance(s, dict) or s.get("decision", "") not in ("", *REVIEW_DECISIONS) or \
                any(str(s.get(k, "")) not in REVIEW_VALUES for k in REVIEW_CRITERIA) or \
                not isinstance(s.get("note", ""), str) or len(s.get("note", "")) > 2000 or \
                not isinstance(rubric, dict) or not set(rubric) <= {r["id"] for r in item.get("rubric", [])} or \
                any(str(v) not in REVIEW_VALUES[2:] for v in rubric.values()):
            return f"Invalid score for {item.get('id', item_key)}.", []
        answer = []

        def add(criterion, score, scale, row_setting="default"):
            answer.append(scores_row(item["answer_id"], item.get("id", ""), criterion, score, scale, "person", reviewer,
                                     now, setting=row_setting))

        if s.get("decision"):
            add("decision", s["decision"], None)
        for k in REVIEW_CRITERIA:
            if str(s.get(k, "")) not in ("", "n/a"):
                add(k, int(s[k]), SCORE_SCALE)
        for rubric_id, v in rubric.items():
            add(f"rubric:{rubric_id}", int(v), SCORE_SCALE, setting)
        if answer:
            answer[0]["note"] = s.get("note", "")
        elif s.get("note", "").strip():
            return f"The note on {item.get('id', item_key)} needs a decision or a score to be saved.", []
        rows += answer
    if not rows:
        return "Nothing scored yet.", []
    return None, rows


def valid_ratings(ratings) -> bool:
    """{"A": {"correct": s, "references": s, "clarity": s}, ...}, s on the shared scale, with at least one answer."""
    return (
        isinstance(ratings, dict)
        and bool(ratings)
        and all(
            isinstance(scores, dict)
            and set(scores) == set(ARENA_CRITERIA)
            and all(type(v) is int and v in criteria.SCALE for v in scores.values())
            for scores in ratings.values()
        )
    )


def leaderboard(ratings: list[dict]) -> list[dict]:
    """One row per model: number of ratings, mean per criterion, overall mean, mean time."""
    by_model: Dict[str, list] = {}
    for rating in ratings:
        by_model.setdefault(rating["model"], []).append(rating)
    rows = []
    for model, items in by_model.items():
        row = {"model": model, "ratings": len(items)}
        for criterion in ARENA_CRITERIA:
            row[criterion] = round(sum(i[criterion] for i in items) / len(items), 2)
        row["overall"] = round(sum(row[c] for c in ARENA_CRITERIA) / len(ARENA_CRITERIA), 2)
        row["seconds"] = round(sum(i["seconds"] for i in items) / len(items), 1)
        rows.append(row)
    return sorted(rows, key=lambda r: (-r["overall"], r["seconds"]))


class RateLimitManager:
    """
    Manages rate limiting configuration and functionality.
    """

    def __init__(self, app: Flask, config: Dict[str, Any]):
        """
        Initialize rate limiting for the application.

        Args:
            app: Flask application instance
            config: Configuration dictionary
        """
        self.app = app
        self.config = config

        # Initialize rate limiter
        self.limiter = Limiter(
            key_func=self._get_rate_limit_key,
            app=self.app,
            storage_uri=f"redis://{config['REDIS_HOST']}:{config['REDIS_PORT']}/{config['REDIS_DB']}",
            strategy="fixed-window",
        )

        # Register error handler for rate limit exceeded
        self.app.errorhandler(429)(self._handle_rate_limit_exceeded)

    def _get_rate_limit_key(self):
        return get_remote_address()

    def get_chat_rate_limit(self) -> str:
        """
        Get the rate limit for the chat endpoint from config.

        Returns:
            str: Rate limit string in the format "X per minute/hour"
        """
        # Check if rate limits are defined in config
        if "RATE_LIMIT" in self.config:
            return self.config["RATE_LIMIT"]
        
        return None

    def _handle_rate_limit_exceeded(self, e: TooManyRequests):
        """
        Handle rate limit exceeded errors with a proper JSON response.

        Args:
            e: The TooManyRequests exception

        Returns:
            Response: JSON response with error details
        """
        response = jsonify(
            {
                "status": "error",
                "message": "Rate limit exceeded. Please try again later.",
                "retry_after": e.description,
            }
        )
        response.status_code = 429
        return response

class FlaskApp:
    """
    Main Flask application class that handles routes and services.
    """

    def __init__(self):
        """Initialize the Flask application with all necessary components."""
        # Load configuration
        self.config = get_config()
        if self.config.get("AUTO_DEFAULTS"):
            # the eval winners become the defaults of chat and arena (read again at every start)
            chosen = eval_report.best_defaults(self.config.get("EVAL_RESULTS_DIR", "eval/results"), ROUTERS)
            logger.info("AUTO_DEFAULTS: %s (fallback: %s, %s)", chosen or "no eval results",
                        self.config["CITATION_MODEL"], self.config.get("ROUTER") or "DECISION_ROUTER")
            self.config.update(chosen)

        # Initialize Flask app
        self.app = Flask(__name__, static_folder="../public", static_url_path="")
        self.app.secret_key = os.getenv("SECRET_KEY", secrets.token_hex(16))
        self.app.config.update(self.config)
        if self.config["PROXY_FIX_X_FOR"]:
            # Behind a trusted reverse proxy: rate-limit by the client IP in X-Forwarded-For
            self.app.wsgi_app = ProxyFix(self.app.wsgi_app, x_for=self.config["PROXY_FIX_X_FOR"])

        # Initialize components
        self.chat_manager = ChatManager()
        self._rag_service = None

        # Initialize rate limiting
        self.rate_limit_manager = RateLimitManager(self.app, self.config)

        # Configure CORS for cross-origin API access
        self._configure_cors()

        # Set up routes
        self.setup_routes()

        logger.debug("Flask application initialized")

    def _configure_cors(self):
        """
        Configure CORS (Cross-Origin Resource Sharing) to allow
        specified origins to access the API.
        """
        allowed_origins = self.config.get("ALLOWED_ORIGINS", [])
        
        if allowed_origins:
            CORS(
                self.app,
                resources={
                    r"/chat": {
                        "origins": allowed_origins,
                        "methods": ["POST", "OPTIONS"],
                        "allow_headers": ["Content-Type"],
                    }
                },
            )
            logger.info(f"CORS enabled for origins: {allowed_origins}")
        else:
            logger.debug("CORS not configured - no ALLOWED_ORIGINS specified")

    def _validate_message(self, message: str) -> tuple[bool, Optional[str]]:
        """
        Validate the user's message.

        Args:
            message: The message to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        max_length = self.config.get("MAX_MESSAGE_LENGTH", 2000)
        min_length = self.config.get("MIN_MESSAGE_LENGTH", 3)

        if len(message) < min_length:
            return False, f"Message too short (minimum {min_length} characters)"
        if len(message) > max_length:
            return False, f"Message too long (maximum {max_length} characters)"
        return True, None

    def setup_routes(self):
        """Set up all application routes."""

        @self.app.context_processor
        def page_links():
            """For templates/_nav.html: link to the arena only when it is on."""
            return {"nav_arena": self.config["ARENA_ENABLED"], "default_router": self.config.get("ROUTER") or "",
                    "nav_review": os.path.isfile(self.config.get("REVIEW_ITEMS_FILE") or ""),
                    "nav_topics": self._topic_map() is not None}

        @self.app.route("/")
        def home():
            """Home page route."""
            # Get background color from URL parameter, default to #fefdf6 if not provided
            bg_color = request.args.get("bg_color", "#fefdf6")

            # Validate the background color (simple validation for hex colors and named colors)
            import re

            if bg_color.startswith("#"):
                # Validate hex color format (#RGB, #RRGGBB, #RRGGBBAA)
                if not re.match(
                    r"^#([0-9A-Fa-f]{3}|[0-9A-Fa-f]{6}|[0-9A-Fa-f]{8})$", bg_color
                ):
                    bg_color = "#fefdf6"  # Default if invalid

            return render_template(
                "index.html",
                bg_color=bg_color,
                models=self.chat_models(),
                default_model=self.config["CITATION_MODEL"],
                routers=ROUTERS,
                debug_panel=bool(self.config.get("DEBUG_PANEL", True)),
            )

        @self.app.route("/chat", methods=["POST"])
        @self.rate_limit_manager.limiter.limit(
            self.rate_limit_manager.get_chat_rate_limit
        )
        def chat():
            """
            Chat endpoint that processes user messages and returns responses.
            Uses server-sent events for streaming responses.
            """
            # Extract request data
            try:
                user_message = request.json["message"]
                chat_id = request.json["chat_id"]
                # Optional: the built-in page can choose the answer model; the widget sends none
                model = request.json.get("model") or None
                # Optional: the built-in page asks for "partial" messages (#41); the widget does not
                stream = request.json.get("stream") is True
                # Optional topic check for this question (the page's dropdown; see ROUTERS)
                router = request.json.get("router") or None
                # Optional: the page's debug panel (?debug=1) asks for the trace of the turn
                debug = request.json.get("debug") is True and bool(self.config.get("DEBUG_PANEL", True))
            except (KeyError, TypeError) as e:
                logger.error(f"Invalid request data: {str(e)}")
                return jsonify(
                    {
                        "status": "error",
                        "message": "Invalid request data. 'message' and 'chat_id' are required.",
                    }
                ), 400

            # Validate message content
            is_valid, error_msg = self._validate_message(user_message)
            if not is_valid:
                logger.warning(f"Message validation failed: {error_msg}")
                return jsonify(
                    {
                        "status": "error",
                        "message": error_msg,
                    }
                ), 400

            if model is not None and model not in self.chat_models():
                return jsonify({"status": "error", "message": "Unknown model."}), 400
            if router is not None and router not in ROUTERS:
                return jsonify({"status": "error", "message": "Unknown topic check."}), 400

            return Response(
                self._generate_chat_response(user_message, chat_id, model, stream, router, debug),
                mimetype="text/event-stream",
            )

        @self.app.route("/review")
        def review_page():
            """Human review of the bot's answers (#8): scores per question, saved as CSV."""
            items = self._review_items()
            if items is None:
                abort(404)
            return render_template("review.html", items=items, criteria=REVIEW_CRITERIA, decisions=REVIEW_DECISIONS,
                                   scale=criteria.SCALE_LABELS, levels=criteria.RUBRIC_LEVELS)

        @self.app.route("/topics")
        def topics_page():
            """The topic map of the index (PR #52, eval/topic_map/): the newest eval/results/topic_map_*.html,
            shown under the site's header and links."""
            path = self._topic_map()
            if path is None:
                abort(404)
            return render_template("topics.html", run=os.path.basename(path)[len("topic_map_"):-len(".html")])

        @self.app.route("/topics/map")
        def topics_map():
            path = self._topic_map()
            if path is None:
                abort(404)
            return send_file(os.path.abspath(path), mimetype="text/html")

        @self.app.route("/review/save", methods=["POST"])
        @self.rate_limit_manager.limiter.limit(self.rate_limit_manager.get_chat_rate_limit)
        def review_save():
            """One reviewer's scores -> SCORES_DIR/scores_review_<name>_<time>.jsonl, score rows (#54);
            a new file per save, never overwritten."""
            items = self._review_items()
            problem, rows = review_rows(request.get_json(silent=True) or {}, {i["key"]: i for i in items or []})
            if problem:
                return jsonify({"status": "error", "message": problem}), 400
            name = re.sub(r"[^a-z0-9]+", "-", rows[0]["scorer"].lower()).strip("-")[:40] or "reviewer"
            folder = self.config.get("SCORES_DIR", "data/scores")
            path = os.path.join(folder, f"scores_review_{name}_{datetime.now(timezone.utc):%y%m%d-%H%M%S}.jsonl")
            try:
                os.makedirs(folder, exist_ok=True)
                with open(path, "x", encoding="utf-8") as f:
                    f.write("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
            except OSError as error:  # the reviewer still has the Export CSV button
                logger.error("Could not save review %s: %s", path, error)
                return jsonify({"status": "error", "message": "Could not save on the server; use Export CSV."}), 500
            return jsonify({"status": "ok", "file": os.path.basename(path), "rows": len({r["answer_id"] for r in rows})})

        @self.app.route("/chat/feedback", methods=["POST"])
        @self.rate_limit_manager.limiter.limit(
            self.rate_limit_manager.get_chat_rate_limit
        )
        def chat_feedback():
            """Store Good/Bad and an optional comment for one answer (once per turn)."""
            data = request.get_json(silent=True) or {}
            rating, comment = data.get("rating"), data.get("comment") or ""
            if rating not in ("good", "bad") or not isinstance(comment, str) or len(comment) > 2000:
                return jsonify({"status": "error", "message": "Send rating good or bad and a comment of at most 2000 characters."}), 400
            turn_id = data.get("turn_id")
            # getdel: one feedback per answer
            turn = self.chat_manager.redis.getdel(f"chat:turn:{turn_id}") if isinstance(turn_id, str) else None
            if turn is None:
                return jsonify({"status": "error", "message": "Unknown or already rated answer."}), 404
            turn = json.loads(turn)
            row = {
                "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "rating": rating,
                "comment": comment.strip(),
                **{k: turn[k] for k in ("turn_id", "chat_id", "model", "question", "outcome", "answer", "references")},
                "answer_time": turn["time"],
            }
            self._append_jsonl(self.config.get("CHAT_FEEDBACK_FILE"), [json.dumps(row)])
            return jsonify({"status": "ok"})

        @self.app.route("/eval")
        def eval_page():
            """Eval results per model: answer runs, classifiers, embeddings, arena ratings."""
            folder = self.config.get("EVAL_RESULTS_DIR", "eval/results")
            arena = []
            if self.config["ARENA_ENABLED"]:
                try:
                    arena = leaderboard(self._arena_ratings())
                except Exception as error:  # no Redis: the tables from files still show
                    logger.warning("Arena ratings unavailable for /eval: %s", error)
            runs = eval_report.answer_runs(folder)
            classifiers = eval_report.classifier_runs(folder)
            for run in runs:
                run["score"] = eval_report.score(run)

            def group(kind: str, search: bool, score: str) -> list:
                """The newest run per model (or configuration) of one kind of run."""
                return eval_report.by_model([r for r in runs if r["kind"] == kind and
                                             r["config"].startswith("search-") == search], score)

            return render_template(
                "eval.html",
                pairs=eval_report.pair_results(folder),
                people=eval_report.people_and_judges(self.config.get("SCORES_DIR", "data/scores"),
                                                     self.config.get("ANSWERS_DIR", "data/answers")),
                answer_models=group("full pipeline", False, "correct"),
                papers_models=sorted(group("papers", False, "judge"), key=lambda r: -(r["score"] or -1)),
                defaults=eval_report.best_defaults(folder, ROUTERS),
                questions=eval_report.question_spread(os.path.dirname(os.path.abspath(folder))),
                routers=ROUTERS,
                forrt_models={r["model"]: r for r in group("FORRT pages", False, "hit")},
                search_configs=group("papers", True, "hit"),
                classifier_models=eval_report.by_model(classifiers, "accuracy"),
                runs=runs,
                classifiers=classifiers,
                embeddings=eval_report.embedding_runs(folder),
                arena=arena,
                criteria=ARENA_CRITERIA,
                scale=criteria.SCALE_LABELS,
            )

        @self.app.route("/up")
        def up():
            """Health check for Docker and load balancers."""
            return "ok"

        @self.app.route("/arena")
        def arena():
            """Arena page: chosen models answer the same question; the user rates each answer."""
            if not self.config["ARENA_ENABLED"]:
                abort(404)
            return render_template(
                "arena.html",
                # the default answer model first, marked like on the chat page
                models=sorted(self.arena_models(), key=lambda m: m != self.config["CITATION_MODEL"]),
                default_model=self.config["CITATION_MODEL"],
                max_models=self.config["ARENA_MAX_MODELS"],
                routers=ROUTERS,
                criteria=ARENA_CRITERIA,
                scale=criteria.SCALE_LABELS,
                blind=self.config["ARENA_BLIND"],
            )

        @self.app.route("/arena/chat", methods=["POST"])
        @self.rate_limit_manager.limiter.limit(
            self.rate_limit_manager.get_chat_rate_limit
        )
        def arena_chat():
            """Answer one question with each chosen model (names hidden until rated)."""
            if not self.config["ARENA_ENABLED"]:
                abort(404)
            data = request.get_json(silent=True) or {}
            user_message = data.get("message")
            if not isinstance(user_message, str):
                return jsonify({"status": "error", "message": "'message' is required."}), 400
            is_valid, error_msg = self._validate_message(user_message)
            if not is_valid:
                return jsonify({"status": "error", "message": error_msg}), 400
            available = self.arena_models()
            models = data.get("models") or available
            if (
                not isinstance(models, list)
                or not models
                or len(set(models)) != len(models)
                or any(m not in available for m in models)
                or len(models) > self.config["ARENA_MAX_MODELS"]
            ):
                limit = self.config["ARENA_MAX_MODELS"]
                return jsonify({"status": "error", "message": f"Choose 1 to {limit} models from the list."}), 400
            # Random order: the card position must not give away the model
            router = data.get("router") or None
            if router is not None and router not in ROUTERS:
                return jsonify({"status": "error", "message": "Unknown topic check."}), 400
            models = random.sample(models, len(models))
            return Response(
                self._generate_arena_response(user_message, models, router),
                mimetype="text/event-stream",
            )

        @self.app.route("/arena/rate", methods=["POST"])
        def arena_rate():
            """Store ratings per answer and criterion, then reveal the model names."""
            if not self.config["ARENA_ENABLED"]:
                abort(404)
            data = request.get_json(silent=True) or {}
            ratings = data.get("ratings")
            if not valid_ratings(ratings):
                names = ", ".join(ARENA_CRITERIA)
                return jsonify({"status": "error", "message": f"Rate each answer {criteria.SCALE[0]}-{criteria.SCALE[-1]} on: {names}."}), 400
            # getdel: one rating round per battle
            battle = self.chat_manager.redis.getdel(f"arena:battle:{data.get('battle_id')}")
            if battle is None:
                return jsonify({"status": "error", "message": "Unknown or already rated battle."}), 404
            battle = json.loads(battle)
            if any(label not in battle["answers"] for label in ratings):
                return jsonify({"status": "error", "message": "Unknown answer label."}), 400
            now = datetime.now(timezone.utc).isoformat(timespec="seconds")
            rows = [
                json.dumps({
                    "time": now,
                    "battle_id": data.get("battle_id"),
                    "question": battle["question"],
                    "model": battle["answers"][label]["model"],
                    "seconds": battle["answers"][label]["seconds"],
                    "timings": battle.get("timings", {}),
                    **scores,
                    "answer": battle["answers"][label].get("answer", ""),
                    "sources": battle["answers"][label].get("sources", ""),
                })
                for label, scores in ratings.items()
            ]
            self.chat_manager.redis.rpush("arena:ratings", *rows)
            self._save_ratings_to_file(rows)
            return jsonify({
                "status": "ok",
                "models": {label: a["model"] for label, a in battle["answers"].items()},
            })

        @self.app.route("/arena/leaderboard")
        def arena_leaderboard():
            """Mean rating per model and criterion, mean answer time, number of ratings."""
            if not self.config["ARENA_ENABLED"]:
                abort(404)
            return jsonify(leaderboard(self._arena_ratings()))

        @self.app.route("/arena/ratings")
        def arena_ratings():
            """All stored ratings (for analysis)."""
            if not self.config["ARENA_ENABLED"]:
                abort(404)
            return jsonify(self._arena_ratings())

    def _save_ratings_to_file(self, rows: list[str]) -> None:
        """Append ratings to ARENA_RATINGS_FILE; Redis stays the source of the leaderboard."""
        self._append_jsonl(self.config.get("ARENA_RATINGS_FILE"), rows)

    def _topic_map(self) -> Optional[str]:
        """The newest topic map page (eval/topic_map/page.py), or None."""
        maps = sorted(glob.glob(os.path.join(self.config.get("EVAL_RESULTS_DIR", "eval/results"), "topic_map_*.html")))
        return maps[-1] if maps else None

    def _review_items(self) -> Optional[list]:
        """The review questions (eval/build_review.py), or None when the file is missing."""
        try:
            with open(self.config.get("REVIEW_ITEMS_FILE") or "", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return None

    def _append_jsonl(self, path: Optional[str], rows: list[str]) -> None:
        """Append JSON lines to path (empty path: do nothing).

        One lock for all threads: a chat log line holds the whole answer (often > 8 KB), which Python
        writes in several system calls, so two answers finishing at once could interleave their lines."""
        if not path:
            return
        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with APPEND_LOCK, open(path, "a", encoding="utf-8") as file:
                file.write("".join(row + "\n" for row in rows))
        except OSError as error:  # a log write must never fail the user's request
            logger.warning("Could not append to %s: %s", path, error)

    def _log_turn(
        self, question: str, chat_id: str, model: Optional[str], response: Dict[str, Any],
        router: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Append a final chat message to CHAT_LOG_FILE and keep it one day in Redis, so
        feedback can refer to it by turn_id. Returns the message with its turn_id."""
        turn_id = str(uuid.uuid4())
        default = "answered" if response.get("status") == "complete" else "error"
        lang = msg.confident_language(question)
        answer_lang = msg.confident_language(re.sub(r"<[^>]+>", " ", response.get("message", "")))
        row = json.dumps({
            "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "turn_id": turn_id,
            "chat_id": chat_id,
            "model": model or self.config["CITATION_MODEL"],
            "router": router or self.config.get("ROUTER") or "default",
            "question": question,
            # language of the question and of the answer (None: too short to tell), to find answers
            # in another language than the question
            "lang": lang,
            "answer_lang": answer_lang,
            "outcome": response.get("outcome", default),  # cached answers have none
            "answer": response.get("message", ""),  # HTML, as shown
            "references": (response.get("metadata") or {}).get("references", []),
            # seconds per step: classify_s, search_s, rerank_s, answer_s, total_s
            "timings": response.get("timings", {}),
        })
        self._append_jsonl(self.config.get("CHAT_LOG_FILE"), [row])
        if lang and answer_lang and lang != answer_lang:
            logger.warning("Answer language %s differs from the question's (%s), turn %s", answer_lang, lang, turn_id)
        try:
            self.chat_manager.redis.set(f"chat:turn:{turn_id}", row, ex=86400)
        except Exception as error:  # no Redis: the answer still goes out, without feedback
            logger.warning("Could not keep chat turn for feedback: %s", error)
            return response
        return {**response, "turn_id": turn_id}

    def _arena_ratings(self) -> list[dict]:
        return [json.loads(r) for r in self.chat_manager.redis.lrange("arena:ratings", 0, -1)]

    def chat_models(self) -> list[str]:
        """Models the chat page offers: CITATION_MODEL first, then the arena models."""
        return list(dict.fromkeys([self.config["CITATION_MODEL"], *self.arena_models()]))

    def arena_models(self) -> list[str]:
        """ARENA_MODELS, without OpenScholar when its server is not configured."""
        models = [m.strip() for m in self.config["ARENA_MODELS"].split(",") if m.strip()]
        if not self.config.get("OPENSCHOLAR_BASE_URL"):
            models = [m for m in models if m != self.config.get("OPENSCHOLAR_MODEL")]
        return models

    def _generate_arena_response(
        self, user_message: str, models: list[str], router: Optional[str] = None
    ) -> Generator[str, None, None]:
        """
        Stream an arena round. Answers get labels A, B, C, ...; with ARENA_BLIND the model
        names stay hidden until the user rates. The round is kept in Redis for one day.
        """
        rag_service = self.get_rag_service()
        if not rag_service:
            yield json.dumps({"status": "error", "message": "RAG service is not available in this environment."}) + "\n"
            return
        options = {"router": router} if router else {}  # without it the call is as before
        for chunk in rag_service.get_arena_response(user_message, models, **options):
            if "responses" in chunk:
                battle_id = str(uuid.uuid4())
                answers = {}
                for label, response in zip(ARENA_LABELS, chunk["responses"]):
                    answers[label] = {
                        "model": response["model"],
                        "seconds": response["seconds"],
                        "answer": response.get("message", ""),  # HTML, as shown on the card
                        "sources": response.get("sources", ""),
                    }
                    response["label"] = label
                    if self.config["ARENA_BLIND"]:
                        del response["model"]  # names appear after the ratings
                self.chat_manager.redis.set(
                    f"arena:battle:{battle_id}",
                    json.dumps({"question": user_message, "answers": answers, "timings": chunk.get("timings", {})}),
                    ex=86400,
                )
                # Every round, rated or not (ratings.jsonl rows carry the same battle_id)
                self._append_jsonl(self.config.get("ARENA_ROUNDS_FILE"), [json.dumps({
                    "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "battle_id": battle_id,
                    "question": user_message,
                    "answers": answers,
                    "timings": chunk.get("timings", {}),  # classify_s, search_s, rerank_s (shared)
                })])
                chunk["battle_id"] = battle_id
            yield json.dumps(chunk) + "\n"

    def _generate_chat_response(
        self, user_message: str, chat_id: str, model: Optional[str] = None, stream: bool = False,
        router: Optional[str] = None, debug: bool = False,
    ) -> Generator[str, None, None]:
        """
        Generate chat responses as a stream.

        Args:
            user_message: The user's message
            chat_id: The chat session ID

        Yields:
            JSON-encoded response chunks
        """
        try:
            # Lazy-load RAG service only when needed
            rag_service = self.get_rag_service()
            if rag_service:
                # without the flag the call is exactly as before #41 (widget, older services)
                options = {**({"stream": True} if stream else {}), **({"router": router} if router else {}),
                           **({"debug": True} if debug else {})}
                for response in rag_service.get_response(user_message, chat_id, model, **options):
                    if response.get("status") in ("complete", "error"):
                        response = self._log_turn(user_message, chat_id, model, response, router)
                    yield json.dumps(response) + "\n"
            else:
                yield (
                    json.dumps(
                        {
                            "status": "error",
                            "message": "RAG service is not available in this environment.",
                        }
                    )
                    + "\n"
                )

        except Exception as e:
            logger.error(f"Error processing chat request: {str(e)}")
            error = {"status": "error", "message": msg.message("unexpected_error", user_message), "outcome": "error"}
            yield json.dumps(self._log_turn(user_message, chat_id, model, error, router)) + "\n"

    def get_rag_service(self):
        """
        Lazy-load the RAG service only when needed.

        Returns:
            The RAG service instance or None if initialization fails
        """
        if self._rag_service is None:
            try:
                from just_os.rag_service import create_rag_service

                self._rag_service = create_rag_service(self.config, self.chat_manager)
                logger.debug("RAG service initialized")
            except Exception as e:
                logger.error(f"Failed to initialize RAG service: {str(e)}")
                return None

        return self._rag_service

    def create_app(self) -> Flask:
        """
        Finalize and return the Flask application instance.

        Returns:
            Flask: The configured Flask application
        """
        # Initialize extensions
        flask_static_digest.init_app(self.app)
        return self.app


def get_app():
    # Create application instance
    flask_app = FlaskApp()
    return flask_app.create_app()
