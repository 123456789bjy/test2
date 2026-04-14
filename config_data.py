
md5_path = "./md5.text"


# Chroma
collection_name = "rag"
persist_directory = "./chroma_db"


# spliter
chunk_size = 1000
chunk_overlap = 100
separators = ["\n\n", "\n", ".", "!", "?", "。", "！", "？", " ", ""]
max_split_char_number = 1000        # 文本分割的阈值

#
similarity_threshold = 1            # 检索返回匹配的文档数量

embedding_model_name = "text-embedding-v4"
chat_model_name = "qwen3-max"

session_config = {
        "configurable": {
            "session_id": "user_001",
        }
    }
# 人工复核任务："json"=本地 JSON，无需 Redis；"redis"=需本机启动 Redis
review_tasks_backend = "json"
review_path = "./data/review.json"

# redis_host = "127.0.0.1"
# redis_port = 6379
# redis_db = 0
# redis_password = None
# review_tasks_redis_prefix = "review"
