from pathlib import Path
import json

from ..engine import AgentEngine
from ..utility import WORKING_DIR
from ..object import Session
from ..agent import AgentConfig, BaseAgent
from .. import __version__
from .widget import AgentWidget, ToolsDialog, ModelsDialog, AgentsDialog
from .qt import QtWidgets, QtGui, QtCore


SESSION_DIR = WORKING_DIR.joinpath("session")
SESSION_DIR.mkdir(parents=True, exist_ok=True)


class MainWindow(QtWidgets.QMainWindow):
    """主窗口"""

    def __init__(self, engine: AgentEngine) -> None:
        """构造函数"""
        super().__init__()

        self.engine: AgentEngine = engine

        self.agent_configs: dict[str, AgentConfig] = {}
        self.agent_widgets: dict[str, AgentWidget] = {}
        self.current_id: str = ""
        self.models: list[str] = self.engine.list_models()

        self.init_ui()
        self.load_data()

    def init_ui(self) -> None:
        """初始化UI"""
        self.setWindowTitle(f"VeighNa Agent - {__version__} - [ {WORKING_DIR} ]")

        self.init_menu()
        self.init_widgets()

        self.status_label: QtWidgets.QLabel = QtWidgets.QLabel()
        self.status_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.statusBar().addWidget(self.status_label, 1)

    def init_widgets(self) -> None:
        """初始化中央控件"""
        # 左侧会话相关
        self.new_button: QtWidgets.QPushButton = QtWidgets.QPushButton("新建会话")
        self.new_button.setFixedHeight(50)
        self.new_button.clicked.connect(self.new_session)

        self.session_list: QtWidgets.QListWidget = QtWidgets.QListWidget()

        # 设置自定义样式表
        stylesheet: str = """
            QListWidget::item {
                padding-top: 10px;
                padding-bottom: 10px;
                padding-left: 10px;
                border-radius: 12px;
            }
            QListWidget::item:hover {
                background-color: rgba(42, 92, 142, 0.3);
                color: white;
            }
            QListWidget::item:selected {
                background-color: #4a90e2;
                color: white;
            }
        """
        self.session_list.setStyleSheet(stylesheet)

        self.session_list.itemClicked.connect(self.on_item_clicked)
        self.session_list.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.session_list.customContextMenuRequested.connect(self.on_menu_requested)
        self.session_list.installEventFilter(self)

        left_vbox: QtWidgets.QVBoxLayout = QtWidgets.QVBoxLayout()
        left_vbox.addWidget(self.session_list)
        left_vbox.addWidget(self.new_button)

        left_widget: QtWidgets.QWidget = QtWidgets.QWidget()
        left_widget.setLayout(left_vbox)
        left_widget.setFixedWidth(300)

        # 右侧聊天相关
        self.stacked_widget: QtWidgets.QStackedWidget = QtWidgets.QStackedWidget()

        # 主布局
        main_hbox: QtWidgets.QHBoxLayout = QtWidgets.QHBoxLayout()
        main_hbox.addWidget(left_widget)
        main_hbox.addWidget(self.stacked_widget)

        central_widget = QtWidgets.QWidget()
        central_widget.setLayout(main_hbox)
        self.setCentralWidget(central_widget)

    def init_menu(self) -> None:
        """初始化菜单"""
        menu_bar: QtWidgets.QMenuBar = self.menuBar()

        sys_menu: QtWidgets.QMenu = menu_bar.addMenu("系统")
        sys_menu.addAction("退出", self.close)

        function_menu: QtWidgets.QMenu = menu_bar.addMenu("功能")
        function_menu.addAction("新建会话", self.new_session)
        function_menu.addAction("管理智能体", self.show_agents)
        function_menu.addAction("查看工具", self.show_tools)
        function_menu.addAction("查看模型", self.show_models)

        help_menu: QtWidgets.QMenu = menu_bar.addMenu("帮助")
        help_menu.addAction("官网", self.open_website)
        help_menu.addAction("关于", self.show_about)

    def show_agents(self) -> None:
        """显示智能体管理界面"""
        dialog: AgentsDialog = AgentsDialog(self.engine, self)
        dialog.exec()

        # 重新加载智能体配置
        self.agent_configs = self.engine.load_agent_configs()

    def show_tools(self) -> None:
        """显示工具"""
        dialog: ToolsDialog = ToolsDialog(self.engine, self)
        dialog.exec()

    def show_models(self) -> None:
        """显示模型"""
        dialog: ModelsDialog = ModelsDialog(self.engine, self)
        dialog.exec()

    def load_data(self) -> None:
        """加载智能体配置和所有会话"""
        self.agent_configs = self.engine.load_agent_configs()

        # 如果没有任何Agent配置，则创建一个默认的
        if not self.agent_configs:
            default_config: AgentConfig = AgentConfig(
                name="通用聊天助手",
                agent_type="ChatAgent",
                system_prompt="你是一个乐于助人的人工智能助手。"
            )
            self.engine.save_agent_config(default_config)
            self.agent_configs[default_config.id] = default_config

        self.load_sessions()

    def load_sessions(self) -> None:
        """加载所有会话"""
        self.agent_widgets.clear()

        session_files: list[Path] = sorted(
            SESSION_DIR.glob("*.json"),
            key=lambda f: f.stat().st_mtime,
            reverse=True
        )

        for file_path in session_files:
            with open(file_path, encoding="UTF-8") as f:
                data: dict = json.load(f)
                session: Session = Session.model_validate(data)

            agent_config: AgentConfig | None = self.agent_configs.get(session.agent_id)
            if not agent_config:
                agent_config = next(iter(self.agent_configs.values()))

            agent: BaseAgent = self.engine.create_agent_instance(agent_config, session)
            self.add_agent_widget(agent)

        if not self.agent_widgets:
            self.new_session()
        else:
            self.current_id = next(iter(self.agent_widgets.keys()))
            self.switch_session(self.current_id)

        self.update_list()

    def update_list(self) -> None:
        """更新会话列表UI"""
        self.session_list.clear()

        sorted_widgets = sorted(
            self.agent_widgets.values(),
            key=lambda w: Path(SESSION_DIR, f"{w.agent.session.id}.json").stat().st_mtime,
            reverse=True
        )

        for widget in sorted_widgets:
            session: Session = widget.agent.session
            item: QtWidgets.QListWidgetItem = QtWidgets.QListWidgetItem(session.name)
            item.setData(QtCore.Qt.ItemDataRole.UserRole, session.id)
            self.session_list.addItem(item)

            if session.id == self.current_id:
                self.session_list.setCurrentItem(item)

    def new_session(self) -> None:
        """创建新会话"""
        # 如果没有Agent配置则返回
        if not self.agent_configs:
            QtWidgets.QMessageBox.warning(self, "创建失败", "请先在“功能”->“管理智能体”中创建一个智能体配置。")
            return

        # 让用户选择一个Agent配置
        agent_names: list[str] = [config.name for config in self.agent_configs.values()]
        name, ok = QtWidgets.QInputDialog.getItem(
            self,
            "选择智能体",
            "请选择要用于新会话的智能体：",
            agent_names,
            0,
            False
        )
        if not (ok and name):
            return

        selected_config: AgentConfig | None = None
        for config in self.agent_configs.values():
            if config.name == name:
                selected_config = config
                break

        if not selected_config:
            return

        # 创建新Session和Agent实例
        session: Session = Session(agent_id=selected_config.id)
        agent: BaseAgent = self.engine.create_agent_instance(selected_config, session)
        agent.save_session()

        self.add_agent_widget(agent)
        self.update_list()
        self.switch_session(session.id)

    def add_agent_widget(self, agent: BaseAgent) -> None:
        """添加会话窗口"""
        widget: AgentWidget = AgentWidget(self.engine, agent, self.models)
        self.stacked_widget.addWidget(widget)
        self.agent_widgets[agent.session.id] = widget

    def switch_session(self, session_id: str) -> None:
        """根据ID切换会话"""
        self.current_id = session_id

        widget: AgentWidget = self.agent_widgets[session_id]
        self.stacked_widget.setCurrentWidget(widget)
        self.update_list()

    def rename_session(self, session_id: str) -> None:
        """重命名会话"""
        widget: AgentWidget | None = self.agent_widgets.get(session_id)
        if not widget:
            return

        session: Session = widget.agent.session
        text, ok = QtWidgets.QInputDialog.getText(self, "重命名会话", "请输入新的会话名称：", text=session.name)

        if ok and text:
            session.name = text
            self.update_list()
            widget.agent.save_session()

    def delete_session(self, session_id: str) -> None:
        """删除会话"""
        reply: QtWidgets.QMessageBox.StandardButton = QtWidgets.QMessageBox.question(
            self,
            "删除会话",
            "确定要删除该会话吗？此操作不可恢复。",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
            QtWidgets.QMessageBox.StandardButton.Yes,
        )

        if reply == QtWidgets.QMessageBox.StandardButton.Yes:
            # 移除对应的控件
            widget: AgentWidget = self.agent_widgets.pop(session_id, None)
            if widget:
                # 从文件系统删除
                widget.agent.delete_session()

                self.stacked_widget.removeWidget(widget)
                widget.deleteLater()

            # 如果删除的是当前会话，则切换到另一个会话
            if self.current_id == session_id:
                if self.agent_widgets:
                    self.current_id = next(iter(self.agent_widgets.keys()))
                    self.switch_session(self.current_id)
                else:
                    self.new_session()

            self.update_list()

    def show_about(self) -> None:
        """显示关于"""
        QtWidgets.QMessageBox.information(
            self,
            "关于",
            (
                "VeighNa Agent\n"
                "\n"
                f"版本号：{__version__}\n"
                "\n"
                f"运行目录：{WORKING_DIR}"
            ),
            QtWidgets.QMessageBox.StandardButton.Ok
        )

    def open_website(self) -> None:
        """打开官网"""
        QtGui.QDesktopServices.openUrl(QtCore.QUrl("https://www.github.com/vnpy/vnag"))

    def eventFilter(self, obj: QtCore.QObject, event: QtCore.QEvent) -> bool:
        """事件过滤器"""
        if obj is self.session_list and event.type() == QtCore.QEvent.Type.KeyPress:
            if event.key() == QtCore.Qt.Key.Key_Delete:
                item: QtWidgets.QListWidgetItem = self.session_list.currentItem()
                if item:
                    self.delete_session(item.data(QtCore.Qt.ItemDataRole.UserRole))
                    return True

        return super().eventFilter(obj, event)

    def on_item_clicked(self, item: QtWidgets.QListWidgetItem) -> None:
        """处理列表项点击事件"""
        session_id: str = item.data(QtCore.Qt.ItemDataRole.UserRole)
        self.switch_session(session_id)

    def on_menu_requested(self, pos: QtCore.QPoint) -> None:
        """显示会话的右键菜单"""
        item: QtWidgets.QListWidgetItem | None = self.session_list.itemAt(pos)
        if not item:
            return

        session_id: str = item.data(QtCore.Qt.ItemDataRole.UserRole)

        menu: QtWidgets.QMenu = QtWidgets.QMenu(self)

        rename_action: QtGui.QAction = menu.addAction("重命名")
        rename_action.triggered.connect(lambda: self.rename_session(session_id))

        delete_action: QtGui.QAction = menu.addAction("删除")
        delete_action.triggered.connect(lambda: self.delete_session(session_id))

        menu.exec(self.session_list.mapToGlobal(pos))
