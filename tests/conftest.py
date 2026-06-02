"""Shared test fixtures. Sets OPENROUTER_API_KEY before any kriterion import."""
import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-stub-key")
