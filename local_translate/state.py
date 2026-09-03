import copy

import streamlit as st

from .ollama_client import TranslationError
from .terminology import count_term, enforce_glossary_terms
from .translation import translate_block, validate_translation


STATE_DEFAULTS = {
    "source_snapshot": "",
    "normalized_source": "",
    "source_chunks": [],
    "term_rows": [],
    "analysis_complete": False,
    "analysis_errors": [],
    "confirmed_glossary": {},
    "local_overrides": {},
    "translations": [],
    "initial_translations": [],
    "revision_history": [],
    "term_editor_version": 0,
    "output_version": 0,
    "file_cache_name": "",
    "file_cache_bytes": b"",
    "file_cache_text": "",
}


def initialize_state():
    for key, value in STATE_DEFAULTS.items():
        if key not in st.session_state:
            st.session_state[key] = copy.deepcopy(value)


def reset_for_source(source_text):
    st.session_state.source_snapshot = source_text
    st.session_state.normalized_source = ""
    st.session_state.source_chunks = []
    st.session_state.term_rows = []
    st.session_state.analysis_complete = False
    st.session_state.analysis_errors = []
    st.session_state.confirmed_glossary = {}
    st.session_state.local_overrides = {}
    st.session_state.translations = []
    st.session_state.initial_translations = []
    st.session_state.revision_history = []
    st.session_state.term_editor_version += 1
    st.session_state.output_version += 1


def push_revision(label):
    st.session_state.revision_history.append({
        "label": label,
        "translations": copy.deepcopy(st.session_state.translations),
        "glossary": copy.deepcopy(st.session_state.confirmed_glossary),
        "local_overrides": copy.deepcopy(st.session_state.local_overrides),
        "term_rows": copy.deepcopy(st.session_state.term_rows),
    })


def restore_revision(snapshot):
    st.session_state.translations = snapshot["translations"]
    st.session_state.confirmed_glossary = snapshot["glossary"]
    st.session_state.local_overrides = snapshot["local_overrides"]
    st.session_state.term_rows = snapshot["term_rows"]
    st.session_state.term_editor_version += 1
    st.session_state.output_version += 1


def upsert_term(source, final, action):
    for row in st.session_state.term_rows:
        if row.get("source", "") == source:
            row["final"] = final
            row["preserve"] = action == "保留原文"
            break
    else:
        st.session_state.term_rows.append({
            "source": source,
            "final": final,
            "preserve": action == "保留原文",
            "count": count_term(st.session_state.normalized_source, source),
        })
    st.session_state.confirmed_glossary[source] = {
        "source": source,
        "final": final,
        "action": action,
    }
    st.session_state.term_editor_version += 1


def rerun_app():
    if hasattr(st, "rerun"):
        st.rerun()
    else:
        st.experimental_rerun()


def run_translation(indices, glossary, progress_label):
    translations = copy.deepcopy(st.session_state.translations)
    if not translations:
        translations = [
            {
                "source": block,
                "target": "",
                "errors": ["尚未翻译"],
                "warnings": [],
            }
            for block in st.session_state.source_chunks
        ]
    progress = st.progress(0, text=progress_label)
    total = len(indices)
    for completed, index in enumerate(indices, start=1):
        progress.progress(
            completed / total,
            text=f"{progress_label}：第 {completed}/{total} 段",
        )
        block_glossary = copy.deepcopy(glossary)
        block_glossary.update(st.session_state.local_overrides.get(index, {}))
        try:
            translations[index] = translate_block(
                st.session_state.source_chunks[index],
                block_glossary,
            )
        except TranslationError as exc:
            translations[index] = {
                "source": st.session_state.source_chunks[index],
                "target": "",
                "errors": [str(exc)],
                "warnings": [],
            }
    progress.empty()
    for index, translation in enumerate(translations):
        if not translation["target"]:
            continue
        effective_glossary = copy.deepcopy(glossary)
        effective_glossary.update(
            st.session_state.local_overrides.get(index, {})
        )
        translation["target"] = enforce_glossary_terms(
            translation["target"],
            effective_glossary,
        )
        translation["errors"], translation["warnings"] = validate_translation(
            translation["source"],
            translation["target"],
        )
    st.session_state.translations = translations
    st.session_state.output_version += 1
