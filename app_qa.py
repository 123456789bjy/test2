import time
from rag import RagService
import streamlit as st
import config_data as config
from review import addtask, find, update
# 标题
st.set_page_config(page_title="服装智能客服", layout="wide")
st.markdown("""
<style>
:root {
    --brand: #4f46e5;
    --brand-light: #eef2ff;
    --bg: #f8fafc;
    --text: #0f172a;
    --muted: #64748b;
}
.stApp {
    background: linear-gradient(180deg, #f8fafc 0%, #eef2ff 100%);
}
.block-container {
    padding-top: 1.2rem;
    padding-bottom: 1.5rem;
    max-width: 1100px;
}
.main-title {
    padding: 18px 22px;
    border-radius: 16px;
    background: white;
    border: 1px solid #e2e8f0;
    box-shadow: 0 8px 24px rgba(15, 23, 42, 0.06);
}
.main-title h1 {
    margin: 0 0 6px 0;
    color: var(--text);
    font-size: 1.6rem;
}
.main-title p {
    margin: 0;
    color: var(--muted);
}
[data-testid="stChatMessage"] {
    border-radius: 14px;
    border: 1px solid #e2e8f0;
    box-shadow: 0 6px 18px rgba(15, 23, 42, 0.05);
    padding: 6px 4px;
    margin-bottom: 10px;
    background: #ffffff;
}
[data-testid="stChatMessage"][aria-label="chat message user"] {
    background: #eff6ff;
    border-color: #bfdbfe;
}
[data-testid="stChatInput"] {
    position: sticky;
    bottom: 12px;
}
.small-tip {
    color: var(--muted);
    font-size: 0.9rem;
}
</style>
""", unsafe_allow_html=True)
st.markdown("""
<div class="main-title">
  <h1>👗 服装领域智能客服</h1>
  <p>支持检索依据展示 + 自动进入待审核队列，保证回答可解释、可复核。</p>
</div>
""", unsafe_allow_html=True)
with st.sidebar:
    st.markdown("### 🧭 使用说明")
    st.caption("1. 在下方输入问题\n2. 查看回答和检索依据\n3. 审核页进行人工复核")
st.markdown('<p class="small-tip">示例问题：羽绒服怎么洗？羊毛大衣起球怎么办？</p>', unsafe_allow_html=True)

if "message" not in st.session_state:
    st.session_state["message"] = [{"role": "assistant", "content": "你好，有什么可以帮助你？"}]

if "rag" not in st.session_state:
    st.session_state["rag"] = RagService()

tab_chat, tab_review = st.tabs(["智能问答", "待审核队列"])

with tab_chat:#后续的内容挂在只能回答下面
    for message in st.session_state["message"]:#显示所有的聊天记录
        with st.chat_message(message["role"]):
            if message["role"] == "assistant" and message.get("basis"):
                with st.expander("点击展开查看全部回答依据", expanded=False):
                    st.markdown(message["basis"])#如果是回复的话那就讲依据附上
            st.markdown(message["content"])

    prompt = st.chat_input("请输入您的问题…")
    if prompt:
        with st.chat_message("user"):
            st.markdown(prompt)     #显示用户的输入
        st.session_state["message"].append({"role": "user", "content": prompt})
        #讲用户的输入存入到状态中
        docs = st.session_state["rag"].retrieve_documents(prompt)#调用 RAG 服务的文档检索方法，根据用户问题从向量库中匹配相关文档；
        basis_text = RagService.format_answer_basis(docs)#将检索到的文档列表格式化为容易读的形式，针对可解释来编写，检索出来的结果放在basis_txt
        ai_res_list: list[str] = []#缓存 AI 流式返回的文本片段，最终拼接为完整回答；
        with st.chat_message("assistant"):
            with st.expander("检索依据", expanded=False):
                st.markdown(basis_text)#模型回复依据
            with st.spinner("AI思考中…"):
                res_stream = st.session_state["rag"].chain.stream(
                    {"input": prompt}, config.session_config
                )#调用 RAG 链的流式生成方法，返回逐段的生成结果
                def capture(gen, cache_list: list[str]):#封装生成器，在返回每段文本的同时，将文本片段追加到 ai_res_list 缓存；
                    for chunk in gen:
                        cache_list.append(chunk)
                        yield chunk
                st.write_stream(capture(res_stream, ai_res_list))#流式回答
        full_answer = "".join(ai_res_list)#拼接形成完整的回答
        st.session_state["message"].append(
            {"role": "assistant", "content": full_answer, "basis": basis_text}
        )#拼接流式返回的文本片段，得到完整回答 并将机器人的回答和依据追加到历史对话，确保刷新页面后仍能展示依据。
        session_id = config.session_config.get("configurable", {}).get("session_id", "default")
        try:
            addtask(#将本次问答记录（问题、回答、依据、会话 ID）写入待审核队列；
                session_id=session_id,
                question=prompt,
                answer=full_answer,
                basis=basis_text,
            )
        except Exception as error:
            st.error(f"写入待审核队列失败：{error}")
        st.rerun()
with tab_review:# 人工复核界面
    st.subheader("待人工复核任务")
    st.caption("以下为用户的问答记录，请核对内容和对应答案是否匹配。")

    pending = find(state="pending")#查询所有「待审核」状态的任务；
    st.markdown(f"**当前待审核：{len(pending)} 条**")

    if not pending:
        st.warning(
            "当前没有「待审核」任务。"
        )#展示待审核任务的数量，若为空则展示警告提示
    else:
        for task in reversed(pending):#倒序展示任务（最新的任务在前）；
            with st.container(border=True):#提供一个带边框的容器，包裹单个任务的所有信息，视觉分层；
                st.markdown(f"**任务 ID**：`{task['task_id']}`  ·  **会话**：{task.get('session_id', '')}")
                st.markdown(f"**提交时间**：{task.get('created_at', '')}")
                st.markdown("**用户问题**")
                st.write(task.get("question", ""))
                with st.expander("点击展开查看全部回答", expanded=False):
                    st.markdown("**系统回答**")
                    st.write(task.get("answer", ""))

                with st.expander("点击展开查看全部回答依据", expanded=False):
                    st.markdown(task.get("basis", ""))
                #依次展示任务 ID、会话 ID、提交时间、用户问题、系统回答、回答依据；
                c1, c2 = st.columns(2)#创建两列布局，分别放置「通过」和「驳回」按钮；

                with c1:
                    if st.button("通过", key=f"approve_{task['task_id']}", type="primary"):#为每个按钮设置唯一 key（避免 Streamlit 报错）；
                        update(task["task_id"], status="approved")
                        st.success("已标记为通过")#点击「通过」：调用 update将任务状态改为 approved，展示成功提示并刷新页面；
                        st.rerun()#立即刷新页面，更新任务列表状态。
                with c2:
                    if st.button("驳回", key=f"reject_{task['task_id']}"):
                        update(task["task_id"], status="rejected")
                        st.warning("已标记为驳回")#点击「驳回」：调用 update 将任务状态改为 rejected，展示警告提示并刷新页面；
                        st.rerun()#立即刷新页面，更新任务列表状态。
