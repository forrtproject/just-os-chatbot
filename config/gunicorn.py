# -*- coding: utf-8 -*-

import os

bind = f"0.0.0.0:{os.getenv('PORT', '8000')}"
accesslog = "-"
access_log_format = (
    "%(h)s %(l)s %(u)s %(t)s '%(r)s' %(s)s %(b)s '%(f)s' '%(a)s' in %(D)sµs"  # noqa: E501
)

workers = int(os.getenv("WEB_CONCURRENCY", 1)) # conservative default to prevent ooms
# > 1 switches to the gthread worker. With 1 thread, one idle browser connection (Chrome
# opens spare ones) or one slow LLM call blocks every other request. Threads share the models.
threads = int(os.getenv("PYTHON_MAX_THREADS", 8))

reload = os.getenv("WEB_RELOAD", "false").lower() in ("1", "true", "yes", "on")

timeout = int(os.getenv("WEB_TIMEOUT", 120))


def post_worker_init(worker):
    # Load the models and index (about 1 min) when the worker starts, not inside
    # the first request, where the load counts against the timeout. Gunicorn has loaded the app
    # (worker.wsgi) by now: load through it, so the service shares the app's config and chat
    # manager. /ready answers 503 until this load has succeeded.
    try:
        flask_app = getattr(getattr(worker, "wsgi", None), "extensions", {}).get("just_os")
        if flask_app is not None:
            ok = flask_app.get_rag_service() is not None  # logs its own error and keeps it for /ready
        else:
            from just_os.rag_service import create_rag_service

            ok = create_rag_service() is not None
        if not ok:
            worker.log.error("Could not preload the RAG service; /ready stays 503 and requests retry the load")
    except Exception as e:
        # The app loads the service lazily on the first request instead
        worker.log.error(f"Could not preload the RAG service: {e}")
