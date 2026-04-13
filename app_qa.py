import time
from rag import RagService
import streamlit as st
import config_data as config
from review import append_pending_task, list_tasks, store_diagnostics, update_task
# 标题
st.title("智能客服")
st.divider()            # 分隔符

if "message" not in st.session_state:
    st.session_state["message"] = [{"role": "assistant", "content": "你好，有什么可以帮助你？"}]

if "rag" not in st.session_state:
    st.session_state["rag"] = RagService()

tab_chat, tab_review = st.tabs(["智能问答", "待审核队列"])

with tab_chat:
    for message in st.session_state["message"]:
        with st.chat_message(message["role"]):
            if message["role"] == "assistant" and message.get("basis"):
                with st.expander("回答依据（检索可解释性）", expanded=False):
                    st.markdown(message["basis"])
            st.markdown(message["content"])

    prompt = st.chat_input("请输入您的问题…")
    if prompt:
        with st.chat_message("user"):
            st.markdown(prompt)
        st.session_state["message"].append({"role": "user", "content": prompt})

        docs = st.session_state["rag"].retrieve_documents(prompt)
        basis_text = RagService.format_answer_basis(docs)

        ai_res_list: list[str] = []
        with st.chat_message("assistant"):
            with st.expander("回答依据（检索可解释性）", expanded=True):
                st.markdown(basis_text)
            with st.spinner("AI思考中…"):
                res_stream = st.session_state["rag"].chain.stream(
                    {"input": prompt}, config.session_config
                )

                def capture(gen, cache_list: list[str]):
                    for chunk in gen:
                        cache_list.append(chunk)
                        yield chunk

                st.write_stream(capture(res_stream, ai_res_list))

        full_answer = "".join(ai_res_list)
        st.session_state["message"].append(
            {"role": "assistant", "content": full_answer, "basis": basis_text}
        )

        session_id = config.session_config.get("configurable", {}).get("session_id", "default")
        try:
            append_pending_task(
                session_id=session_id,
                question=prompt,
                answer=full_answer,
                basis=basis_text,
            )
        except Exception as e:
            st.error(f"写入待审核队列失败：{e}")

with tab_review:
    st.subheader("待人工复核任务")
    st.caption("以下为系统自动派发的问答记录，请核对答案与依据是否一致、内容是否合规。")

    diag = store_diagnostics()
    if diag.get("backend") == "redis":
        if diag.get("redis_ok") is False:
            st.error(
                f"无法连接 Redis：{diag.get('redis_error', '未知错误')}。"
                "请启动本机 Redis，或把 config_data.py 里 review_tasks_backend 改为 \"json\"。"
            )
        else:
            st.caption("存储：Redis · 连接正常")

    pending = list_tasks(status="pending")
    st.markdown(f"**当前待审核：{len(pending)} 条**")

    if not pending:
        st.warning(
            "当前没有「待审核」任务。"
            
        )
    else:
        for task in reversed(pending):
            with st.container(border=True):
                st.markdown(f"**任务 ID**：`{task['task_id']}`  ·  **会话**：{task.get('session_id', '')}")
                st.markdown(f"**提交时间**：{task.get('created_at', '')}")
                st.markdown("**用户问题**")
                st.write(task.get("question", ""))
                st.markdown("**系统回答**")
                st.write(task.get("answer", ""))
                st.markdown("**回答依据**")
                st.markdown(task.get("basis", ""))

                c1, c2 = st.columns(2)
                with c1:
                    if st.button("通过", key=f"approve_{task['task_id']}", type="primary"):
                        update_task(task["task_id"], status="approved")
                        st.success("已标记为通过")
                        st.rerun()
                with c2:
                    if st.button("驳回", key=f"reject_{task['task_id']}"):
                        update_task(task["task_id"], status="rejected")
                        st.warning("已标记为驳回")
                        st.rerun()
