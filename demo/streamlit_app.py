"""LearnArken Day 6 demo frontend — a deliberately dumb client.

This file must never import `learnarken` (test-enforced): every substantive
computation — validation, indexing, retrieval, generation, citation
verification — happens in the FastAPI backend at API_BASE. The UI only
renders what the wire says, including the SSE retraction protocol:
streamed tokens are labeled unverified, and a `retract` event withdraws
them visibly (SPEC day6 decision 3).

Model- and document-derived text is always rendered escaped (st.text /
st.table, never unsafe_allow_html): an uploaded module cannot smuggle
HTML/JS into the operator's browser.
"""

import json

import requests
import streamlit as st

API_BASE = "http://127.0.0.1:8100"

STAGE_LABELS = {
    "retrieval": "检索中 (retrieval)…",
    "rerank": "重排中 (rerank)…",
    "generating": "生成中 (LLM)…",
}
GATE_LABELS = {
    "threshold": "检索相关度阈值门 (threshold)",
    "llm": "模型判定不可回答 (llm)",
    "llm-contract": "模型输出契约门 (llm-contract)",
    "citation-validation": "引用确证门 (citation-validation)",
}


def safe_json(text, default=None):
    """Parse JSON, or return `default` — the backend may hand back an HTML
    error page or a truncated body; a dumb client must degrade, not crash."""
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return default


def sse_events(response):
    """Minimal SSE parse: (event, data-json-string) per blank-line-ended block."""
    event, data_lines = None, []
    for raw in response.iter_lines(decode_unicode=True):
        if raw is None:
            continue
        if raw == "":
            if event or data_lines:
                yield event or "message", "\n".join(data_lines)
            event, data_lines = None, []
        elif raw.startswith("event:"):
            event = raw[len("event:") :].strip()
        elif raw.startswith("data:"):
            data_lines.append(raw[len("data:") :].strip())


def render_answer(entry: dict) -> None:
    """Render one completed assistant turn from its stored outcome."""
    if entry.get("retracted"):
        st.warning(
            "⚠️ 已回撤:本次有内容生成,但未通过 "
            f"{GATE_LABELS.get(entry.get('gate', ''), entry.get('gate', '?'))}"
            " —— 刚才流式显示的内容不作为有效回答,已被撤回。"
        )
    if entry.get("error"):
        st.error(f"🚫 服务失败(fail closed,未降级作答):{entry['error']}")
        return
    result = entry.get("result")
    if result is None:
        return
    if result["refused"]:
        st.info(
            f"⛔ 拒答:{result['answer_text']}\n\n"
            f"触发关卡:{GATE_LABELS.get(result.get('refusal_gate', ''), '?')}"
            f" · trace={result['trace_id']}"
        )
        return
    st.text(result["answer_text"])
    st.caption(f"✅ 引用已确证 · model={result.get('model')} · trace={result['trace_id']}")
    citations = result.get("citations", [])
    if citations:
        st.table(
            [
                {
                    "chunk_id": c["chunk_id"],
                    "DMC": c["dmc"],
                    "XPath": c["source_path"],
                    "佐证原文": c["supporting_quote"],
                }
                for c in citations
            ]
        )


def render_upload_outcome(status_code: int, payload: dict) -> None:
    status = payload.get("status", "")
    if status == "ingested":
        replaced = "(覆盖了同名旧文件)" if payload.get("replaced") else ""
        st.success(
            f"✅ 校验通过,已入库 {replaced} — 全库共 {payload['indexed_chunks']} "
            f"个 chunk 已重建索引,可立即提问。"
        )
        warnings = [
            f for f in payload.get("report", {}).get("findings", []) if f["severity"] != "error"
        ]
        for f in warnings:
            st.warning(f"⚠️ [{f['rule_id']}] {f['file']}: {f['message']}")
    elif status == "rejected":
        st.error("❌ 校验失败,未入库(文件已移除):")
        findings = payload.get("report", {}).get("findings", [])
        if not findings and payload.get("message"):
            st.text(payload["message"])
        for f in findings:
            st.text(
                f"[{f['layer']}/{f['rule_id']}/{f['severity']}] "
                f"{f['file']}: {f['message']}"
            )
    elif status == "index_failed":
        st.error(f"🚫 校验通过但入库失败(fail closed,文件已移除):{payload.get('message')}")
    else:
        st.warning(f"⚠️ 上传被拒(HTTP {status_code}):{payload.get('detail', payload)}")


st.set_page_config(page_title="LearnArken Demo", page_icon="📘", layout="wide")
st.title("LearnArken — 上传 + 有据问答 Demo(Day 6)")

with st.sidebar:
    st.subheader("后端状态")
    st.caption("Streamlit 是哑客户端:所有计算都发生在 FastAPI 后端。")
    try:
        resp = requests.get(f"{API_BASE}/health", timeout=10)
        health = safe_json(resp.text, default={})
        services = health.get("services") if isinstance(health, dict) else None
        if not services:
            st.error(f"后端返回了非预期响应(HTTP {resp.status_code})。请先 `make demo`。")
        else:
            for name, s in services.items():
                if s.get("ok"):
                    st.markdown(f"🟢 {name}")
                else:
                    st.markdown(f"🔴 {name}")
                    st.caption(s.get("detail", ""))
    except requests.RequestException as exc:
        st.error(f"后端不可达({API_BASE}):{exc.__class__.__name__}。请先 `make demo`。")

upload_tab, qa_tab = st.tabs(["📤 上传文档", "💬 问答"])

with upload_tab:
    st.caption("上传合成 S1000D 数据模块(.xml ≤ 2 MiB)。后端跑四层校验;通过才入库。")
    uploaded = st.file_uploader("选择 XML 文件", type=["xml"])
    if uploaded is not None and st.button("上传并校验", type="primary"):
        with st.spinner("校验 + 入库中(通过则全库重建索引,需要一点时间)…"):
            try:
                resp = requests.post(
                    f"{API_BASE}/upload",
                    files={"file": (uploaded.name, uploaded.getvalue(), "application/xml")},
                    timeout=600,
                )
                try:
                    payload = resp.json()
                except ValueError:
                    payload = {"detail": resp.text[:300]}
                render_upload_outcome(resp.status_code, payload)
            except requests.RequestException as exc:
                st.error(f"后端不可达:{exc.__class__.__name__}。请先 `make demo`。")

with qa_tab:
    if "history" not in st.session_state:
        st.session_state.history = []
    for entry in st.session_state.history:
        with st.chat_message("user"):
            st.text(entry["question"])
        with st.chat_message("assistant"):
            render_answer(entry)

    question = st.chat_input("对已入库的文档提问(3–500 字符)…")
    if question:
        with st.chat_message("user"):
            st.text(question)
        entry = {"question": question}
        with st.chat_message("assistant"):
            stage = st.empty()
            stream_area = st.empty()
            streamed = ""
            try:
                with requests.post(
                    f"{API_BASE}/query",
                    json={"question": question},
                    stream=True,
                    timeout=600,
                ) as resp:
                    if resp.status_code != 200:
                        body = safe_json(resp.text, default={})
                        detail = body.get("detail", resp.text[:300]) if body else resp.text[:300]
                        entry["error"] = f"HTTP {resp.status_code}: {detail}"
                    else:
                        for event, data in sse_events(resp):
                            payload = safe_json(data, default={}) if data else {}
                            if event == "status":
                                stage.caption(
                                    STAGE_LABELS.get(payload.get("stage"), payload.get("stage"))
                                )
                            elif event == "token":
                                streamed += payload["text"]
                                stream_area.text(
                                    "⏳ 生成中 — 以下内容未经引用确证,可能被回撤:\n\n" + streamed
                                )
                            elif event == "retract":
                                entry["retracted"] = True
                                entry["gate"] = payload.get("gate")
                                stream_area.empty()  # withdraw the unverified text
                            elif event == "result":
                                entry["result"] = payload
                            elif event == "error":
                                entry["error"] = payload.get("message")
            except requests.RequestException as exc:
                entry["error"] = f"后端不可达:{exc.__class__.__name__}"
            stage.empty()
            stream_area.empty()
            render_answer(entry)
        st.session_state.history.append(entry)
