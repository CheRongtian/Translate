import copy
import json

import streamlit as st

from .documents import extract_uploaded_text
from .state import (
    initialize_state,
    push_revision,
    rerun_app,
    reset_for_source,
    restore_revision,
    run_translation,
    upsert_term,
)
from .terminology import (
    affected_block_indices,
    analyze_terms,
    build_glossary_from_rows,
    count_term,
    editor_records,
    merge_term_candidates,
    replace_in_translation,
)
from .text_processing import normalize_text, split_text


def render_term_editor():
    st.subheader("2. 可选：统一术语")
    st.caption(
        "在“指定译法”中直接填写即可；留空会跳过，"
        "勾选“保留原文”会忽略指定译法。"
    )

    with st.expander("导入已有术语表"):
        imported_file = st.file_uploader(
            "选择术语表（JSON）",
            type=["json"],
            key="glossary_import",
        )
        if imported_file is not None and st.button("导入"):
            try:
                imported = json.loads(imported_file.getvalue().decode("utf-8"))
                if not isinstance(imported, list):
                    raise ValueError("术语表顶层必须是数组")
                imported_rows = []
                for item in imported:
                    if (
                        not isinstance(item, dict)
                        or not str(item.get("source", "")).strip()
                    ):
                        continue
                    source = str(item["source"]).strip()
                    preserve = (
                        bool(item.get("preserve"))
                        or item.get("action") == "保留原文"
                    )
                    imported_rows.append({
                        "source": source,
                        "final": "" if preserve else str(
                            item.get("final") or ""
                        ).strip(),
                        "preserve": preserve,
                        "count": count_term(
                            st.session_state.normalized_source,
                            source,
                        ),
                    })
                st.session_state.term_rows = merge_term_candidates(
                    st.session_state.term_rows + imported_rows,
                    st.session_state.normalized_source,
                )
                st.session_state.term_editor_version += 1
                rerun_app()
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
                st.error(f"导入术语表失败：{exc}")

    editor_data = copy.deepcopy(st.session_state.term_rows)
    if not editor_data:
        editor_data = [{
            "source": "",
            "final": "",
            "preserve": False,
            "count": 0,
        }]
    edited = st.data_editor(
        editor_data,
        key=f"term_editor_{st.session_state.term_editor_version}",
        num_rows="dynamic",
        hide_index=True,
        use_container_width=True,
        column_order=["source", "final", "preserve", "count"],
        column_config={
            "source": st.column_config.TextColumn("原文词项"),
            "final": st.column_config.TextColumn("指定译法（可留空）"),
            "preserve": st.column_config.CheckboxColumn("保留原文"),
            "count": st.column_config.NumberColumn("出现次数", min_value=0),
        },
        disabled=["count"],
    )
    if st.button("使用以上设置开始翻译", type="primary"):
        rows, glossary, errors = build_glossary_from_rows(
            editor_records(edited)
        )
        if errors:
            for error in errors:
                st.error(error)
        else:
            st.session_state.term_rows = rows
            st.session_state.confirmed_glossary = glossary
            st.session_state.local_overrides = {}
            st.session_state.translations = []
            st.session_state.initial_translations = []
            st.session_state.revision_history = []
            st.session_state.term_editor_version += 1
            indices = list(range(len(st.session_state.source_chunks)))
            run_translation(indices, glossary, "正在翻译")
            st.session_state.initial_translations = copy.deepcopy(
                st.session_state.translations
            )
            rerun_app()


def render_translation_result():
    translations = st.session_state.translations
    if not translations:
        return
    errors = [
        (index, item["errors"])
        for index, item in enumerate(translations)
        if item["errors"]
    ]
    if errors:
        st.error(f"有 {len(errors)} 个段落翻译失败。")
        for index, messages in errors:
            st.caption(f"第 {index + 1} 段：{'；'.join(messages)}")
    else:
        st.success("翻译完成。")

    combined = "\n\n".join(
        item["target"]
        for item in translations
        if item["target"]
    )
    st.text_area(
        "翻译结果",
        value=combined,
        height=420,
        key=f"translation_output_{st.session_state.output_version}",
    )
    st.download_button(
        "下载译文",
        data=combined.encode("utf-8"),
        file_name="translation.txt",
        mime="text/plain",
    )
    glossary_export = [
        {
            "source": entry["source"],
            "final": "" if entry["action"] == "保留原文" else entry["final"],
            "preserve": entry["action"] == "保留原文",
        }
        for entry in st.session_state.confirmed_glossary.values()
    ]
    st.download_button(
        "导出术语表",
        data=json.dumps(
            glossary_export,
            ensure_ascii=False,
            indent=2,
        ).encode("utf-8"),
        file_name="glossary.json",
        mime="application/json",
    )

    retry_indices = sorted({index for index, _ in errors})
    if retry_indices and st.button("重试失败段落"):
        push_revision("重试异常段落")
        run_translation(
            retry_indices,
            st.session_state.confirmed_glossary,
            "正在重试",
        )
        rerun_app()


def render_revision_tools():
    if not st.session_state.translations:
        return
    st.subheader("3. 译后补充术语")
    st.caption(
        "填写原词和指定译法；也可以勾选保留原文。"
        "默认应用到全文并只重翻相关段落。"
    )
    left_input, right_input = st.columns(2)
    with left_input:
        source_term = st.text_input(
            "原文词项",
            key="revision_source_term",
        ).strip()
    with right_input:
        preserve = st.checkbox("保留原文", key="revision_preserve")
        desired = st.text_input(
            "指定译法（保留原文时无需填写）",
            disabled=preserve,
            key="revision_desired",
        ).strip()
    action = "保留原文" if preserve else "使用指定译法"
    final_value = source_term if action == "保留原文" else desired
    matching_indices = affected_block_indices(
        st.session_state.source_chunks,
        source_term,
    )
    with st.expander("高级设置"):
        scope = st.radio(
            "应用范围",
            ["全文", "本处"],
            horizontal=True,
            key="revision_scope",
        )
        selected_index = None
        if scope == "本处" and matching_indices:
            selected_number = st.selectbox(
                "选择原文段落",
                [index + 1 for index in matching_indices],
                key="revision_block_number",
            )
            selected_index = selected_number - 1
        method = st.radio(
            "修订方式",
            ["重新翻译受影响段落", "直接替换现有译文"],
            horizontal=True,
            key="revision_method",
        )
        current_wrong = ""
        if method == "直接替换现有译文":
            current_wrong = st.text_input(
                "现有译文中需要替换的文字",
                key="revision_wrong",
            ).strip()
    if source_term and not matching_indices:
        st.warning("原文中没有找到这个词项。")

    if st.button("应用并修订相关段落", type="primary"):
        if not source_term:
            st.error("请输入原文词项。")
            return
        if not final_value:
            st.error("请输入指定译法，或选择保留原文。")
            return
        if not matching_indices:
            st.error("原文中没有找到这个词项。")
            return
        if method == "直接替换现有译文" and not current_wrong:
            st.error("直接替换需要填写现有译文中的错误文字。")
            return
        target_indices = matching_indices if scope == "全文" else [selected_index]
        if method == "直接替换现有译文":
            replacement_count = sum(
                st.session_state.translations[index]["target"].count(current_wrong)
                for index in target_indices
            )
            if replacement_count == 0:
                st.error("选定范围内没有找到需要替换的现有译文。")
                return
        push_revision(f"修订词项：{source_term}")
        if scope == "全文":
            upsert_term(source_term, final_value, action)
            for overrides in st.session_state.local_overrides.values():
                overrides.pop(source_term, None)
            revision_glossary = st.session_state.confirmed_glossary
        else:
            local_entry = {
                "source": source_term,
                "final": final_value,
                "action": action,
            }
            st.session_state.local_overrides.setdefault(selected_index, {})[
                source_term
            ] = local_entry
            revision_glossary = st.session_state.confirmed_glossary
        if method == "重新翻译受影响段落":
            run_translation(
                target_indices,
                revision_glossary,
                "正在修订",
            )
        else:
            updated = copy.deepcopy(st.session_state.translations)
            for index in target_indices:
                updated[index]["target"], _ = replace_in_translation(
                    updated[index]["target"],
                    current_wrong,
                    final_value,
                )
            st.session_state.translations = updated
            st.session_state.output_version += 1
        rerun_app()

    left, right = st.columns(2)
    with left:
        if st.session_state.revision_history and st.button("撤销上一次修订"):
            snapshot = st.session_state.revision_history.pop()
            restore_revision(snapshot)
            rerun_app()
    with right:
        if st.session_state.initial_translations and st.button("恢复初始译文"):
            push_revision("恢复初始译文前")
            st.session_state.translations = copy.deepcopy(
                st.session_state.initial_translations
            )
            st.session_state.output_version += 1
            rerun_app()


def main():
    st.set_page_config(page_title="我的全能私有翻译官", layout="wide")
    initialize_state()
    st.title("我的全能私有翻译官")

    st.subheader("1. 输入文档")
    uploaded_file = st.file_uploader(
        "直接拖拽文件到这里（支持 TXT、PDF、Word、图片）",
        type=["txt", "pdf", "docx", "png", "jpg", "jpeg"],
    )
    user_input = st.text_area("或者直接粘贴文本：", height=180)

    extracted_text = ""
    if uploaded_file is not None:
        file_bytes = uploaded_file.getvalue()
        cache_hit = (
            uploaded_file.name == st.session_state.file_cache_name
            and file_bytes == st.session_state.file_cache_bytes
        )
        if cache_hit:
            extracted_text = st.session_state.file_cache_text
        else:
            try:
                extracted_text = extract_uploaded_text(uploaded_file)
                st.session_state.file_cache_name = uploaded_file.name
                st.session_state.file_cache_bytes = file_bytes
                st.session_state.file_cache_text = extracted_text
            except Exception as exc:
                st.error(f"解析文件失败：{exc}")
        if extracted_text.strip():
            st.success("文件文字提取成功。")
            with st.expander("预览提取文字"):
                st.text(extracted_text)
        else:
            st.warning("文件中没有提取到可翻译文字。")

    source_parts = [
        part
        for part in (extracted_text, user_input)
        if part and part.strip()
    ]
    source_text = "\n\n".join(source_parts)
    if source_text != st.session_state.source_snapshot:
        reset_for_source(source_text)

    if st.button("分析术语", disabled=not source_text.strip()):
        normalized = normalize_text(source_text)
        chunks = split_text(normalized)
        if not chunks:
            st.warning("没有可分析的文字。")
        else:
            st.session_state.normalized_source = normalized
            st.session_state.source_chunks = chunks
            progress = st.progress(0, text="正在分析术语")

            def update_analysis_progress(index, total):
                progress.progress(
                    index / total,
                    text=f"正在分析术语：第 {index}/{total} 段",
                )

            rows, analysis_errors = analyze_terms(
                normalized,
                chunks,
                update_analysis_progress,
            )
            progress.empty()
            st.session_state.term_rows = rows
            st.session_state.analysis_complete = True
            st.session_state.analysis_errors = analysis_errors
            st.session_state.confirmed_glossary = {}
            st.session_state.local_overrides = {}
            st.session_state.translations = []
            st.session_state.initial_translations = []
            st.session_state.revision_history = []
            st.session_state.term_editor_version += 1
            st.session_state.output_version += 1

    if st.session_state.analysis_complete:
        for error in st.session_state.analysis_errors:
            st.warning(error)
        if not st.session_state.term_rows:
            if st.session_state.analysis_errors:
                st.error(
                    "术语分析没有生成候选词。可以重新分析或手动添加。"
                )
            else:
                st.info("未发现候选词。可以手动添加，也可以直接开始翻译。")

    if st.session_state.source_chunks:
        chunk_count = len(st.session_state.source_chunks)
        if chunk_count == 1:
            st.caption("正文符合单次上下文预算，将整篇一次翻译。")
        else:
            st.caption(
                "正文超出单次上下文预算，将按完整段落尽量合并为 "
                f"{chunk_count} 段翻译。"
            )
        render_term_editor()

    render_translation_result()
    render_revision_tools()
