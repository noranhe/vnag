from collections.abc import Generator

from ..agent import BaseAgent, AgentConfig
from ..object import Message, Delta, Role, Response, Session
from ..engine import AgentEngine


class ChatAgent(BaseAgent):
    """
    一个由系统提示词和工具驱动的通用聊天Agent。
    """

    def __init__(self, engine: "AgentEngine", config: AgentConfig, session: Session) -> None:
        """构造函数"""
        super().__init__(engine, config, session)

    def _prepare_messages(self) -> list[Message]:
        """准备请求所用的消息列表"""
        messages = self.session.messages.copy()

        # 如果有系统提示词，则将其作为第一条消息
        if self.config.system_prompt and (not messages or messages[0].role != Role.SYSTEM):
            system_message = Message(role=Role.SYSTEM, content=self.config.system_prompt)
            messages.insert(0, system_message)

        return messages

    def stream(self, prompt: str, **kwargs) -> Generator[Delta, None, None]:
        """流式生成"""
        # 添加系统提示词
        if not self.session.messages:
            system_message: Message = Message(role=Role.SYSTEM, content=self.config.system_prompt)
            self.session.messages.append(system_message)

        # 将用户输入添加到会话
        user_message: Message = Message(role=Role.USER, content=prompt)
        self.session.messages.append(user_message)

        # 完整返回的信息缓存
        full_content: str = ""

        # 通过引擎流式生成响应
        for delta in self.engine.stream(
            messages=self.session.messages,
            model=self.session.model,
            tools=self.config.tools,
            **kwargs
        ):
            # 如果生成内容不为空，则添加到信息缓存
            if delta.content:
                full_content += delta.content

            # 返回流式响应
            yield delta

        # 如果生成内容不为空，则添加到会话
        if full_content:
            assistant_message: Message = Message(role=Role.ASSISTANT, content=full_content)
            self.session.messages.append(assistant_message)

        # 将最新会话保存到文件
        self.save_session()

    def invoke(self, prompt: str, **kwargs) -> Response:
        """阻塞式生成"""
        # 将用户输入添加到会话
        user_message: Message = Message(role=Role.USER, content=prompt)
        self.session.messages.append(user_message)

        # 通过引擎阻塞式生成响应
        response = self.engine.invoke(
            messages=self.session.messages,
            model=self.session.model,
            tools=self.config.tools,
            **kwargs
        )

        # 如果生成内容不为空，则添加到会话
        if response.content:
            assistant_message: Message = Message(role=Role.ASSISTANT, content=response.content)
            self.session.messages.append(assistant_message)

        # 将最新会话保存到文件
        self.save_session()

        return response
