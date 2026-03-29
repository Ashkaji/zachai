"""Unit tests for LoRA pipeline helpers (Story 4.4). Run: pytest test_lora_pipeline.py from this directory."""
import os

import pytest

# Minimal env so lora_pipeline can import without full Docker config
os.environ.setdefault("MINIO_ACCESS_KEY", "test")
os.environ.setdefault("MINIO_SECRET_KEY", "test")
os.environ.setdefault("MODEL_READY_CALLBACK_SECRET", "test-secret")

import lora_pipeline as lp  # noqa: E402


def test_train_eval_split_reproducible():
    train, ev = lp.train_eval_split_indices(10, 0.2, 42)
    train2, ev2 = lp.train_eval_split_indices(10, 0.2, 42)
    assert train == train2 and ev == ev2
    assert len(train) + len(ev) == 10
    assert not train.intersection(ev)


def test_train_eval_split_reserves_train_row_when_n_gt_1():
    train, ev = lp.train_eval_split_indices(2, 0.99, 1)
    assert len(train) >= 1
    assert len(ev) <= 1


def test_normalize_pointer_content():
    assert lp.normalize_pointer_content("  foo/bar  ") == "foo/bar/"
    assert lp.normalize_pointer_content("x/") == "x/"


def test_short_process_suffix():
    s = lp.short_process_suffix("abc-def-1234567890")
    assert len(s) <= 10
    assert s.isalnum()


def test_wer_eval_score_for_items_empty():
    score, err = lp.wer_eval_score_for_items([], training_stub=True)
    assert score is None
    assert err and "eval split is empty" in err


def test_wer_eval_score_for_items_non_stub_not_implemented():
    score, err = lp.wer_eval_score_for_items([{"corrected_text": "hello"}], training_stub=False)
    assert score is None
    assert err and "not implemented" in err


def test_wer_eval_score_for_items_stub_identical_refs():
    items = [{"corrected_text": "one two"}, {"corrected_text": "three"}]
    score, err = lp.wer_eval_score_for_items(items, training_stub=True)
    assert err is None
    assert score == 0.0
