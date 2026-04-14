from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough, RunnableWithMessageHistory, RunnableLambda
from file_history_store import get_history
from vector_stores import VectorStoreService
from langchain_community.embeddings import DashScopeEmbeddings
import config_data as config
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_community.chat_models.tongyi import ChatTongyi


def print_prompt(prompt):
    print("="*20)
    print(prompt.to_string())
    print("="*20)

    return prompt


class RagService(object):
    def __init__(self):

        self.vector_service = VectorStoreService(
            embedding=DashScopeEmbeddings(model=config.embedding_model_name)
        )#创建向量库服务实例，绑定嵌入模型，是检索的基础；
        self._retriever = self.vector_service.get_retriever()
        #从向量库服务中获取检索器（as_retriever），后续链内检索和外部调用都复用该检索器；
        self.prompt_template = ChatPromptTemplate.from_messages(
            [
                ("system", "以我提供的已知参考资料为主，"
                 "简洁和专业的回答用户问题。参考资料:{context}。"),
                ("system", "并且我提供用户的对话历史记录，如下："),
                MessagesPlaceholder("history"),
                ("user", "请回答用户提问：{input}")
            ]
        )#定义大模型的提示词模板，核心逻辑是「参考资料 + 对话历史 + 用户问题」；

        self.chat_model = ChatTongyi(model=config.chat_model_name)#创建大模型实例，用于生成回答；
        self.chain = self.__get_chain()#调用 __get_chain 构建完整的 RAG 执行链，并作为类属性保存。

    def retrieve_documents(self, query: str) -> list[Document]:
        """与对话链使用同一检索器，便于展示「回答依据」。"""
        return self._retriever.invoke(query)#调用检索器的 invoke 方法，用户调用方法传入问题，返回匹配的文档列表。
    @staticmethod
    def format_answer_basis(docs: list[Document]) -> str:
        if not docs:#空结果处理：明确告知用户回答来源（模型常识 + 历史），提示核查准确性；
            return (
                "本次检索未命中知识库中的相关片段，回答主要依据模型常识与对话历史；"
                "建议人工重点核查事实准确性。"
            )
        parts: list[str] = []# 初始化片段列表，用于拼接最终结果
        for i, doc in enumerate(docs, 1):
            src = doc.metadata.get("source", "未知来源")# 获取文档元数据中的来源，无则默认“未知来源”
            snippet = (doc.page_content or "").strip().replace("\n", " ") # 提取文档内容，去掉空格、换行符，避免排版混乱
            parts.append(f"{i}. **来源**：{src}\n   **片段**：{snippet}")#  将列表中的片段用两个换行符分隔，拼接成最终字符串
        return "\n\n".join(parts)

    def __get_chain(self):
        """获取最终的执行链"""
        # 复用类属性的检索器
        retriever = self._retriever

        # 定义文档格式化函数：将检索到的 Document 列表转换成字符串
        def format_document(docs: list[Document]):
            if not docs:
                return "无相关参考资料"
            formatted_str = ""
            for doc in docs:
                # 拼接文档内容和元数据，方便提示词使用
                formatted_str += f"文档片段：{doc.page_content}\n文档元数据：{doc.metadata}\n\n"
            return formatted_str

        # 定义检索器输入格式化函数：提取用户问题
        def format_for_retriever(value: dict) -> str:
            return value["input"]

        # 定义提示词模板输入格式化函数：适配参数结构
        def format_for_prompt_template(value):
            # 目标结构：{input: 用户问题, context: 检索内容, history: 对话历史}
            new_value = {}
            # 提取原始输入中的用户问题
            new_value["input"] = value["input"]["input"]
            # 提取检索到的上下文
            new_value["context"] = value["context"]
            # 提取对话历史
            new_value["history"] = value["input"]["history"]
            return new_value

        # 构建基础 RAG 链
        chain = (
                {
                    # 原始输入（包含用户问题+对话历史）
                    "input": RunnablePassthrough(),
                    # 检索分支：提取用户问题 → 调用检索器 → 格式化文档
                    "context": RunnableLambda(format_for_retriever) | retriever | format_document
                }
                # 格式化链输入，适配提示词模板的参数结构
                | RunnableLambda(format_for_prompt_template)
                # 填充提示词模板
                | self.prompt_template
                # 打印提示词（调试用）
                | print_prompt
                # 调用大模型
                | self.chat_model
                # 解析输出为字符串
                | StrOutputParser()
        )

        # 包装成带对话历史的链
        conversation_chain = RunnableWithMessageHistory(
            chain,  # 基础 RAG 链
            get_history,  # 会话历史获取函数
            input_messages_key="input",  # 输入消息的 key（对应用户问题）
            history_messages_key="history"  # 历史消息的 key（对应对话历史）
        )

        return conversation_chain


# if __name__ == '__main__':
#     # session id 配置
#     session_config = {
#         "configurable": {
#             "session_id": "user_001",
#         }
#     }
#
#     res = RagService().chain.invoke({"input": "针织毛衣如何保养？"}, session_config)
#     print(res)

