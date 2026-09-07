"""Offline evaluation of every retrieval mode against a fixed test suite.

The report is generated ahead of time by `python -m app.evaluation.runner` and
served as a static artefact from `/api/eval`. Nothing here runs per request.
"""
