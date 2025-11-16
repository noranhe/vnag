<!-- 14af1ef5-f7ba-4834-a6fb-462df87c9860 2b1bfbc9-0feb-42e5-9f9c-98192c18b91d -->
# 引入Agent基类和管理功能方案 (框架最终版)

本方案旨在构建一个面向未来的、可扩展的Agent框架。其核心思想是：**`Agent`实例是管理自身所有会话（Sessions）的、长生命周期的、有状态的服务。**

## 1. 核心架构：以Agent为中心的会话管理

| 组件 | 职责 | 状态管理 |

| :--- | :--- | :--- |

| **`AgentEngine`** | **Agent的工厂和注册中心**。负责从配置创建、持有并提供对所有`Agent`实例的访问。是Agent的“操作系统”。 | 持有所有`Agent`的活动实例 (`Dict[agent_id, BaseAgent]`)。 |

| **`BaseAgent`** | **自治的服务实体**。一个`Agent`实例可以管理**多个**并发的`Session`。它封装了自身的核心逻辑和所有与之相关的对话历史。 | **持有并维护自身所有的`Session`** (`Dict[session_id, Session]`)。这是本次架构的核心升级。 |

| **`SessionWidget`** | **特定Agent的特定Session的视图**。它只是一个UI外壳，用于展示一个对话，并将用户操作转发给对应的`Agent`实例。 | 仅持有`agent_id`和`session_id`作为“指针”，不直接管理`Session`对象的生命周期。 |

| **`Session`** | **对话历史的数据载体**。它现在完全由其所属的`Agent`实例在内部进行创建、加载、更新和持久化。 | 无，纯数据对象。 |

## 2. 方案详细设计

### 2.1. `AgentEngine`：纯粹的工厂和注册中心

- 职责不变，但新增一个关键接口：`get_agent(agent_id: str) -> BaseAgent`，用于直接获取`Agent`的活动实例，这是解耦UI与Agent的关键。

### 2.2. `BaseAgent`：升级为会话管理器

`BaseAgent` 将被赋予管理其自身所有 `Session` 的能力。

```python
# vnag/agent.py (示意)

class BaseAgent(ABC):
    def __init__(self, engine: "AgentEngine", config: Agent):
        self.engine: "AgentEngine" = engine
        self.config: Agent = config
        self.sessions: Dict[str, Session] = {}  # 内部维护所有会话

    def create_session(self) -> Session:
        """为自己创建一个新的会话。"""
        # ... 创建 new_session, 设置 id, name, agent_id=self.config.id
        self.sessions[new_session.id] = new_session
        self.save_session(new_session.id)  # 持久化
        return new_session

    def load_session(self, session_id: str) -> Session | None:
        """从文件加载会话到内存。"""
        pass

    def save_session(self, session_id: str) -> None:
        """将会话持久化到文件。"""
        pass
        
    def delete_session(self, session_id: str) -> None:
        """删除会话（内存和文件）。"""
        pass

    # stream 和 invoke 接口的签名发生根本性变化
    @abstractmethod
    def stream(self, session_id: str, user_input: str, **kwargs) -> Generator[Delta, None, None]:
        """在指定的会话中处理用户输入。内部会负责更新该session的消息历史并保存。"""
        pass

    @abstractmethod
    def invoke(self, session_id: str, user_input: str, **kwargs) -> Response:
        pass
```

### 2.3. `SessionWidget`：简化为纯粹的UI视图

`SessionWidget` 的逻辑将大大简化，它不再管理任何业务状态。

1.  **启动新聊天**：`MainWindow` 通过 `engine.get_agent(agent_id)` 获取Agent实例，调用 `agent.create_session()` 创建新会话，然后将 `agent_id` 和 `session_id` 传递给新创建的 `SessionWidget`。
2.  **加载旧聊天**：`MainWindow` 在启动时扫描所有`session`文件，解析出`session_id`和`agent_id`，创建对应的`SessionWidget`。当用户点击某个`SessionWidget`时，再通知对应的`Agent`实例按需（`lazy load`）将会话数据从文件加载到内存。
3.  **发送消息**：`SessionWidget` 只做一件事：调用 `engine.get_agent(self.agent_id).stream(self.session_id, user_input)`，然后将返回的 `Delta` 更新到界面上。所有消息的追加、`Session`的保存，都在`Agent`内部完成。

## 3. 架构优势总结

-   **一个配置，一个实例，多个会话**：这完美地实现了您的设想。用户定义一个“市场研究员”Agent配置，引擎只创建一个实例。多个UI窗口可以同时与这个实例交互，每个窗口都有独立的会话，由Agent实例内部的字典进行隔离和管理。
-   **支持未来扩展**：此模型完美支持无UI的脚本调用 (`agent.invoke(...)`) 和Agent间的交互，为项目成为真正的Agent框架奠定了坚实的基础。