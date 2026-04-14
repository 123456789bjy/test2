import json
import os
import uuid# 用于生成唯一的任务 ID（不会重复）
from datetime import datetime# 用于生成当前时间（创建时间、审核时间）
from typing import Any# 类型标注：任意类型


# 导入项目配置文件（读取 JSON 文件保存路径）
import config_data as config


# 从配置文件读取：待审核任务默认保存的 JSON 文件路径
store = config.review_path


def exist(path: str) -> None:#判断文件夹是否存在
    d = os.path.dirname(os.path.abspath(path))
    if d:    # 如果目录不为空
        os.makedirs(d, exist_ok=True) # 创建目录，exist_ok=True 表示目录已存在也不会报错

def load(path: str | None = None) -> list[dict[str, Any]]:#从JSON文件中读取数据 list里面套字典dict
    path = path or store# 如果没传 path，就使用默认路径
    if not os.path.exists(path):# 如果文件不存在，直接返回空列表
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)# 把JSON转成list/dict
    return data if isinstance(data, list) else []    # 如果读取出来的是列表(本身JSON是列表套字典)，就返回；否则返回空列表


def save(data: list[dict[str, Any]], path: str | None = None) -> None:# 将所有任务存到JSON
    path = path or store
    exist(path)#判断是否存在
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)#将列表存入JSON，rows存入f

def addtask(#添加待审核任务
    *,
    session_id: str,        # ID
    question: str,          # 问题
    answer: str,            # 回答
    basis: str,             # 依据
    path: str | None = None,# 路径
) -> str:
    return addtask_json(    #直接调用JSON添加实现
        session_id=session_id,
        question=question,
        answer=answer,
        basis=basis,
        path=path,
    )

def addtask_json(#往JSON文件里添加一条新任务
    *,
    session_id: str,
    question: str,
    answer: str,
    basis: str,
    path: str | None = None,
) -> str:
    path = path or store
    data = load(path)
    task_id = str(uuid.uuid4())#生成一个唯一id
    data.append(    # 构造一条新的任务记录
        {
            "task_id": task_id,               # ID
            "created_at": datetime.now().isoformat(timespec="seconds"),  #时间
            "session_id": session_id,         # 会话ID
            "question": question,             # 问题
            "answer": answer,                 # 回答
            "basis": basis,                   # 依据
            "status": "pending",              # 状态
            "reviewed_at": None,              # 审核时间
            "reviewer_note": "",              # 备注
        }
    )
    save(data, path)# 把新列表写回文件
    return task_id  # 返回任务的ID


def find(state: str | None = None, path: str | None = None) -> list[dict[str, Any]]:#查询返回任务列表
    data = load(path)
    if state: #如果传了审核状态(通过，驳回，待审核)，只返回对应状态的任务
        return [r for r in data if r.get("status") == state]
    return data    # 否则返回全部任务

def update(#外层包装，对待审核任务的状态更新
    task_id: str,            # 待审核ID
    *,
    status: str,             # 要审核状态状态：approved/rejected
    reviewer_note: str = "", # 备注
    path: str | None = None, # 路径
) -> bool:
    return update_json(
        task_id=task_id,
        status=status,
        reviewer_note=reviewer_note,
        path=path
    )

def update_json(# 第层真正执行，使用task_id 找到任务并修改状态、审核时间、备注
    task_id: str,
    *,
    status: str,
    reviewer_note: str = "",
    path: str | None = None,
) -> bool:
    path = path or store
    data = load(path)
    for d in data:    # 遍历所有任务，找到与task_id匹配的任务
        if d.get("task_id") == task_id:
            d["status"] = status #修改状态
            d["reviewed_at"] = datetime.now().isoformat(timespec="seconds") #修改时间
            d["reviewer_note"] = reviewer_note #备注
            save(rows, path) #保存
            return True  #修改成功
    return False #没找到文件