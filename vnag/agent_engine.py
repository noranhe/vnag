from typing import Any
from collections.abc import Generator

from vnag.gateway import BaseGateway
from vnag.engine import BaseEngine
from vnag.rag_service import RAGService
from vnag.session_manager import SessionManager
from vnag.object import Request, Message, Role
from vnag.utility import load_json

from vnag.gateways.openai_gateway import OpenaiGateway
from vnag.gateways.anthropic_gateway import AnthropicGateway


GATEWAY_MAP = {
    "openai": OpenaiGateway,
    "anthropic": AnthropicGateway,
}


class AgentEngine(BaseEngine):
    """Agent 引擎：负责业务编排（历史、RAG、附件等），并调用网关获得流式结果。

    MVP骨架：网关在引擎内部创建，后续逐步迁移 RAG 与会话逻辑。
    """

    def __init__(self) -> None:
        """构造函数"""
        super().__init__()

        self.gateway: BaseGateway
        self.rag_service: RAGService
        self.session_manager: SessionManager

        self.inited: bool = False

        self.chat_history: list = []

    def init_engine(self, gateway_name: str) -> None:
        """初始化引擎依赖（例如网关）。"""
        gateway_name = gateway_name.lower()
        gateway_filename: str = f"connect_{gateway_name}.json"
        setting: dict = load_json(gateway_filename)

        self.gateway = GATEWAY_MAP.get(gateway_name, OpenaiGateway)()
        self.inited = self.gateway.init(setting)

        if self.inited:
            # 网关成功初始化后再创建 RAGService / SessionManager
            self.rag_service = RAGService()
            self.session_manager = SessionManager()

            # 加载历史会话
            self.load_history()

    def prepare_messages(
        self,
        messages: list,
        use_rag: bool,
        user_files: list | None,
    ) -> list:
        """预处理消息（RAG/CHAT），由引擎负责，不再放在网关。"""
        if use_rag:
            return self.rag_service.prepare_rag_messages(messages, user_files)
        else:
            return self.rag_service.prepare_chat_messages(messages, user_files)

    def send_message(
        self,
        message: str,
        model_name: str,
        max_tokens: int,
        temperature: float,
        use_rag: bool = True,  # 占位参数，后续接入 RAG
        user_files: list[str] | None = None,  # 占位参数，后续接入附件
    ) -> Generator[str, None, None]:
        """最小实现：直接将单轮 user 消息发给网关。

        说明：
        - 后续会在此处接入：历史管理、RAG 预处理、用户文件读取等。
        - 目前仅构造最小 messages，便于逐步迁移。
        """
        if not self.inited:
            yield from ()

        if not model_name:
            print("模型名称为空")
            yield from ()

        if not message.strip():
            yield from ()

        # 载入当前会话历史，并在引擎侧完成 RAG/CHAT 处理
        history: list = self.session_manager.load_session()
        base_messages: list = history + [{"role": "user", "content": message}]
        messages: list = self.prepare_messages(base_messages, use_rag=use_rag, user_files=user_files)

        # 与 gateway 一致：使用 self.chat_history 持有内存态，供 UI 流式刷新读取
        self.chat_history = history + [
            {"role": "user", "content": message},
            {"role": "assistant", "content": ""},
        ]

        # 网关层负责实际的流式调用（按次传入 model_name 与 kwargs）

        # RAG模板只围绕最后一条user问题做检索与拼装
        # 发给模型的messages是完整会话历史 + 本轮处理后的消息

        # 转换为标准消息对象列表（显式循环）
        msg_objs: list[Message] = []
        for m in messages:
            msg_objs.append(Message(role=Role(m["role"]), content=m["content"]))

        req: Request = Request(
            model=model_name,
            messages=msg_objs,
            max_tokens=max_tokens,
            temperature=temperature,
        )

        for delta in self.gateway.stream(req):
            if delta.content:
                # 流式累积到最后一条 assistant（同步内存态）
                if self.chat_history and self.chat_history[-1].get("role") == "assistant":
                    self.chat_history[-1]["content"] += delta.content
                yield delta.content

        # 持久化本轮对话
        self.session_manager.save_session(self.chat_history)

    def get_chat_history(self) -> list:
        """获取当前对话历史"""
        return self.chat_history.copy()

    def clear_history(self) -> None:
        """清空当前会话历史"""
        if not self.inited:
            return

        self.session_manager.save_session([])

    def load_history(self) -> None:
        """加载当前会话历史"""
        if not self.inited:
            return

        self.chat_history = self.session_manager.load_session()

    def new_session(self) -> str:
        """创建新会话并返回会话ID"""
        if not self.inited:
            return ""

        return self.session_manager.create_session()

    def get_all_sessions(self) -> list:
        """获取所有未删除的会话"""
        if not self.inited:
            return []

        return self.session_manager.get_all_sessions()

    def switch_session(self, session_id: str) -> bool:
        """切换到指定会话"""
        if not self.inited:
            return False

        return self.session_manager.switch_session(session_id)

    def delete_session(self, session_id: str) -> bool:
        """软删除会话"""
        if not self.inited:
            return False

        return self.session_manager.delete_session(session_id)

    def export_session(self, session_id: str | None = None) -> tuple:
        """导出会话：(标题, 历史)"""
        if not self.inited:
            return ("未知会话", [])

        return self.session_manager.export_session(session_id)

    def get_deleted_sessions(self) -> list:
        """获取回收站会话列表"""
        if not self.inited:
            return []

        return self.session_manager.get_deleted_sessions()

    def restore_session(self, session_id: str) -> bool:
        """恢复已删除的会话"""
        if not self.inited:
            return False

        return self.session_manager.restore_session(session_id)

    def cleanup_deleted_sessions(self, force_all: bool = False) -> int:
        """清理已删除会话，返回清理数量"""
        if not self.inited:
            return 0

        return self.session_manager.cleanup_deleted_sessions(force_all)
