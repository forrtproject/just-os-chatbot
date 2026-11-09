# -*- coding: utf-8 -*-

import os

from distutils.util import strtobool

bind = f"0.0.0.0:{os.getenv('PORT', '8000')}"
accesslog = "-"
access_log_format = (
    "%(h)s %(l)s %(u)s %(t)s '%(r)s' %(s)s %(b)s '%(f)s' '%(a)s' in %(D)sµs"  # noqa: E501
)

workers = int(os.getenv("WEB_CONCURRENCY", 1)) # conservative default to prevent ooms
threads = int(os.getenv("PYTHON_MAX_THREADS", 1))

reload = bool(strtobool(os.getenv("WEB_RELOAD", "false")))

timeout = int(os.getenv("WEB_TIMEOUT", 120))


def post_worker_init(worker):
    # Load the models and index (about 1 min) when the worker starts, not inside
    # the first request, where the load counts against the timeout.
    try:
        from just_os.rag_service import create_rag_service

        create_rag_service()
    except Exception as e:
        # The app loads the service lazily on the first request instead
        worker.log.error(f"Could not preload the RAG service: {e}")
