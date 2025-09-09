from pathlib import Path
import markdown     # type: ignore[import-untyped]
import time
from datetime import datetime
from collections.abc import Generator

from PySide6 import QtWidgets, QtGui, QtCore

from .agent_engine import AgentEngine
from .setting import SETTINGS, SETTING_FILENAME
from .utility import AGENT_DIR, save_json, load_json, write_text_file
from . import __version__


# 样式常量（避免多处硬编码）
PILL_LIST_QSS: str = (
    "QListWidget { border: none; background: transparent; padding: 1px 0 1px 0; margin: 0; }"
    "QListWidget::item { border: none; margin: 0; padding: 0; }"
    "QListWidget::item:selected { background: transparent; }"
    "QListWidget::item:hover { background: transparent; }"
)
WHITE_TEXT_QSS: str = "color: white;"
PILL_CLOSE_BTN_QSS: str = "QPushButton { border: none; font-weight: bold; }"
MENU_BUTTON_QSS: str = "QPushButton { border: none; }"
TIME_LABEL_QSS: str = "color: gray; font-size: 9pt;"
CURRENT_MODEL_LABEL_QSS: str = "color: #FFFFFF;"
CURRENT_MODEL_PLACEHOLDER_QSS: str = "font-style: italic; color: #999999;"


class MainWindow(QtWidgets.QMainWindow):
    """主窗口"""

    def __init__(self) -> None:
        """构造函数"""
        super().__init__()

        # 初始化引擎
        self.engine: AgentEngine = AgentEngine()

        self.init_ui()
        self.refresh_display()

    def init_ui(self) -> None:
        """初始化UI"""
        settings: dict = SETTINGS.copy()
        settings.update(load_json(SETTING_FILENAME))

        self.model_name: str = settings["model_name"]
        self.max_tokens: int = settings["max_tokens"]
        self.temperature: float = settings["temperature"]
        self.gateway_name: str = settings["gateway_name"]

        self.engine.init_engine(self.gateway_name)
        self.engine.cleanup_deleted_sessions(force_all=False)

        self.setWindowTitle(f"VeighNa Agent - {__version__} - [ {AGENT_DIR} ]")

        self.init_menu()
        self.init_widgets()

    def init_widgets(self) -> None:
        """初始化中央控件"""
        desktop: QtCore.QRect = (QtWidgets.QApplication.primaryScreen().availableGeometry())

        # 创建主分割布局
        main_splitter: QtWidgets.QSplitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)

        # ========== 左侧区域 ==========
        left_widget: QtWidgets.QWidget = QtWidgets.QWidget()
        left_layout: QtWidgets.QVBoxLayout = QtWidgets.QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        # 创建标签页
        self.tab_widget: QtWidgets.QTabWidget = QtWidgets.QTabWidget()

        # 会话标签页
        self.session_tab: QtWidgets.QWidget = QtWidgets.QWidget()
        session_layout: QtWidgets.QVBoxLayout = QtWidgets.QVBoxLayout(self.session_tab)

        # 会话列表
        self.session_list: QtWidgets.QListWidget = QtWidgets.QListWidget()
        self.session_list.itemClicked.connect(self.on_session_selected)

        # 新建会话按钮
        new_session_button: QtWidgets.QPushButton = QtWidgets.QPushButton("新建会话")
        new_session_button.clicked.connect(self.new_session)

        session_layout.addWidget(self.session_list)
        session_layout.addWidget(new_session_button)

        # 配置标签页
        self.config_tab: QtWidgets.QWidget = QtWidgets.QWidget()
        config_layout: QtWidgets.QVBoxLayout = QtWidgets.QVBoxLayout(self.config_tab)

        # 配置表单
        config_form: QtWidgets.QFormLayout = QtWidgets.QFormLayout()

        self.config_gateway_name: QtWidgets.QLineEdit = QtWidgets.QLineEdit(self.gateway_name)
        self.config_model_name: QtWidgets.QLineEdit = QtWidgets.QLineEdit(self.model_name)
        self.config_max_tokens: QtWidgets.QLineEdit = QtWidgets.QLineEdit(str(self.max_tokens))
        self.config_temperature: QtWidgets.QLineEdit = QtWidgets.QLineEdit(str(self.temperature))

        # 添加到表单
        config_form.addRow("网关名称:", self.config_gateway_name)
        config_form.addRow("模型名称:", self.config_model_name)
        config_form.addRow("最大Token:", self.config_max_tokens)
        config_form.addRow("温度系数:", self.config_temperature)

        # 保存按钮
        save_config_button: QtWidgets.QPushButton = QtWidgets.QPushButton("保存并应用配置")
        save_config_button.clicked.connect(self.save_config)

        config_layout.addLayout(config_form)
        config_layout.addStretch()
        config_layout.addWidget(save_config_button)

        # 添加标签页
        self.tab_widget.addTab(self.session_tab, "会话")
        self.tab_widget.addTab(self.config_tab, "配置")

        left_layout.addWidget(self.tab_widget)

        # ========== 右侧区域 ==========
        right_widget: QtWidgets.QWidget = QtWidgets.QWidget()
        right_layout: QtWidgets.QVBoxLayout = QtWidgets.QVBoxLayout(right_widget)
        right_layout.setSpacing(2)

        # 历史消息显示区域
        self.history_widget: QtWidgets.QTextEdit = QtWidgets.QTextEdit()
        self.history_widget.setReadOnly(True)

        # 输入区域
        input_container: QtWidgets.QWidget = QtWidgets.QWidget()
        input_layout: QtWidgets.QVBoxLayout = QtWidgets.QVBoxLayout(input_container)
        input_layout.setContentsMargins(0, 0, 0, 0)
        input_layout.setSpacing(2)

        self.input_widget: QtWidgets.QTextEdit = QtWidgets.QTextEdit()
        self.input_widget.setMaximumHeight(desktop.height() // 4)

        # 输入框上方的控件
        input_top_layout: QtWidgets.QHBoxLayout = QtWidgets.QHBoxLayout()
        input_top_layout.addStretch()

        # 移除Stream开关

        # RAG开关
        self.rag_switch: RagSwitchButton = RagSwitchButton()
        self.rag_switch.toggled.connect(self.toggle_rag_mode)
        self.rag_switch.setChecked(True)  # 默认开启
        input_top_layout.addWidget(self.rag_switch)

        # 输入框底部的控件
        input_bottom_layout: QtWidgets.QHBoxLayout = QtWidgets.QHBoxLayout()

        # 文件按钮（使用图标）
        self.file_button: QtWidgets.QPushButton = QtWidgets.QPushButton("📎")
        self.file_button.setToolTip("添加文件")
        self.file_button.clicked.connect(self.select_files)
        self.file_button.setFixedSize(30, 30)

        # 模型选择按钮
        self.model_button: QtWidgets.QPushButton = QtWidgets.QPushButton("@")
        self.model_button.setToolTip("选择模型")
        self.model_button.clicked.connect(self.show_model_selector)
        self.model_button.setFixedSize(30, 30)

        # 发送按钮
        self.send_button: QtWidgets.QPushButton = QtWidgets.QPushButton("发送")
        self.send_button.clicked.connect(self.send_message)
        self.send_button.setFixedWidth(100)

        input_bottom_layout.addWidget(self.file_button)
        input_bottom_layout.addWidget(self.model_button)
        input_bottom_layout.addStretch()
        input_bottom_layout.addWidget(self.send_button)

        # 状态标签
        self.status_label: QtWidgets.QLabel = QtWidgets.QLabel("就绪")

        # 旧的滚动区域文件显示已移除，改用下方的流式列表

        # 新增：文件“药丸”列表（使用QListWidget流式模式），嵌入输入框内部顶端（Cursor式）
        self.file_list_widget: QtWidgets.QListWidget = QtWidgets.QListWidget(self.input_widget)
        self.file_list_widget.setFlow(QtWidgets.QListView.Flow.LeftToRight)
        self.file_list_widget.setWrapping(False)
        self.file_list_widget.setResizeMode(QtWidgets.QListView.ResizeMode.Adjust)
        self.file_list_widget.setSpacing(4)
        self.file_list_widget.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.file_list_widget.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.file_list_widget.setVerticalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.file_list_widget.setFixedHeight(20)
        self.file_list_widget.setVisible(False)
        # 去除选中/焦点与边框的视觉干扰
        self.file_list_widget.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.NoSelection
        )
        self.file_list_widget.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        self.file_list_widget.setStyleSheet(PILL_LIST_QSS)

        # 已选文件列表需在刷新显示前初始化
        self.selected_files: list[str] = []

        # 组装输入区域
        input_layout.addLayout(input_top_layout)
        input_layout.addWidget(self.input_widget)
        input_layout.addLayout(input_bottom_layout)

        # 将“药丸”列表覆盖在输入框视口之上，并监听输入框尺寸变化以同步定位
        self.input_container: QtWidgets.QWidget = input_container
        self.input_widget.installEventFilter(self)
        # 先基于输入框字体计算药丸行高，再定位和刷新
        self._recalc_pill_metrics()
        self._position_file_pills()
        self._refresh_file_pills_display()

        # 组装右侧布局
        right_layout.addWidget(self.history_widget)
        right_layout.addWidget(input_container)
        right_layout.addWidget(self.status_label)

        # 添加到分割器
        main_splitter.addWidget(left_widget)
        main_splitter.addWidget(right_widget)

        # 设置初始分割比例
        main_splitter.setSizes([
            int(desktop.width() * 0.3),
            int(desktop.width() * 0.7)
        ])

        # 设置为中央控件
        self.setCentralWidget(main_splitter)

    def append_message(self, role: str, content: str) -> None:
        """在会话历史组件中添加消息"""
        self.history_widget.moveCursor(QtGui.QTextCursor.MoveOperation.End)

        if role == "user":
            # 用户内容不需要被渲染
            escaped_content: str = (content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>"))

            # 外层容器加标识，方便后续复制交互
            user_html: str = (
                f'<div class="msg" data-role="user" style="margin: 12px 0; display: block;">'
                f'<div style="margin-bottom: 8px; font-weight: bold;">💬 User</div>'
                f'<div>{escaped_content}</div>'
                f'</div>'
            )
            self.history_widget.textCursor().insertBlock()
            self.history_widget.insertHtml(user_html)
            # 插入后再断开一段，形成独立空行
            self.history_widget.textCursor().insertBlock()

        elif role == "assistant":
            # AI返回内容以Markdown渲染
            html_content: str = markdown.markdown(
                content,
                extensions=['fenced_code', 'codehilite']
            )

            # 外层容器加标识，方便后续复制交互
            assistant_html: str = (
                f'<div class="msg" data-role="assistant" style="margin: 12px 0; display: block;">'
                f'<div style="margin-bottom: 8px; font-weight: bold;">✨ Assistant</div>'
                f'<div style="margin:0; padding:0;">{html_content}</div>'
                f'</div>'
            )
            self.history_widget.textCursor().insertBlock()
            self.history_widget.insertHtml(assistant_html)
            # 插入后再断开一段，形成独立空行
            self.history_widget.textCursor().insertBlock()

        # 确保滚动条滚动到最新消息
        self.history_widget.moveCursor(QtGui.QTextCursor.MoveOperation.End)

    def eventFilter(self, watched: QtCore.QObject, event: QtCore.QEvent) -> bool:
        """监听输入框大小变化以定位药丸列表"""
        if watched is self.input_widget and event.type() in (
            QtCore.QEvent.Type.Resize,
            QtCore.QEvent.Type.Show,
        ):
            self._recalc_pill_metrics()
            self._position_file_pills()
            self._refresh_file_pills_display()
        return bool(super().eventFilter(watched, event))

    def _position_file_pills(self) -> None:
        """将药丸条固定在输入框内部顶部，文本从其下方开始（Cursor式）"""
        if not hasattr(self, "file_list_widget"):
            return

        # 顶部留白等于“药丸条高度”
        bar_h: int = getattr(self, "_pill_bar_height", self.file_list_widget.height())
        top_margin: int = bar_h if (self.file_list_widget.isVisible()) else 0
        self.input_widget.setViewportMargins(0, top_margin, 0, 0)

        # 对齐到 QTextEdit 的可视区域
        vp: QtWidgets.QWidget = self.input_widget.viewport()
        vp_geom: QtCore.QRect = vp.geometry()

        # 列表高度=药丸高+2，条内垂直居中（不额外偏移）
        list_h: int = min(bar_h, self._pill_height + 2) if top_margin > 0 else 0
        y_offset: int = ((bar_h - list_h) // 2) if top_margin > 0 else 0
        self.file_list_widget.setGeometry(
            vp_geom.x(),
            vp_geom.y() - top_margin + y_offset,
            vp_geom.width(),
            list_h,
        )
        self.file_list_widget.raise_()

    def _recalc_pill_metrics(self) -> None:
        """根据输入框字体度量行高，设置药丸行高和控件尺寸"""
        fm: QtGui.QFontMetrics = self.input_widget.fontMetrics()

        # 输入框单行高度
        self._line_height: int = max(20, fm.height())
        # 回到你确认的版本：药丸≈0.85×行高（更饱满），条高≈1.5×行高
        self._pill_height: int = max(16, int(round(self._line_height * 0.85)))
        self._pill_bar_height: int = max(24, int(round(self._line_height * 1.5)))

        if hasattr(self, "file_list_widget"):
            self.file_list_widget.setFixedHeight(self._pill_bar_height)

    def _create_pill_widget(self, file_path: str) -> QtWidgets.QWidget:
        """创建单个文件药丸小部件"""
        file_name: str = Path(file_path).name
        display_name: str = (file_name[:17] + "...") if len(file_name) > 20 else file_name

        pill: QtWidgets.QWidget = QtWidgets.QWidget()
        ph: int = getattr(self, "_pill_height", 18)

        # 药丸高度 = 目标高度（条内留白由条 padding 控制为上下各 2px）
        pill.setFixedHeight(ph)

        pill_layout: QtWidgets.QHBoxLayout = QtWidgets.QHBoxLayout(pill)

        # 依据 pill 行高设置边距与间距，保证垂直居中
        vpad: int = max(1, (pill.height() - 12) // 2)
        pill_layout.setContentsMargins(6, vpad, 6, vpad)
        pill_layout.setSpacing(3)

        label: QtWidgets.QLabel = QtWidgets.QLabel(display_name)

        # 字号：与输入框一致或小1，避免拥挤
        base_pt: int = self.input_widget.font().pointSize()
        if base_pt <= 0:
            base_pt = 10

        font: QtGui.QFont = label.font()
        font.setPointSize(max(6, base_pt - 4))
        label.setFont(font)
        label.setStyleSheet(WHITE_TEXT_QSS)
        label.setToolTip(str(file_path))

        close_btn: QtWidgets.QPushButton = QtWidgets.QPushButton("×")
        btn_h: int = max(10, pill.height() - 6)
        close_btn.setFixedSize(btn_h, btn_h)
        close_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(PILL_CLOSE_BTN_QSS)
        close_btn.setToolTip("移除该文件")
        close_btn.clicked.connect(lambda checked=False, fp=file_path: self._remove_file(fp))

        pill.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)
        radius: int = max(6, pill.height() // 2)
        pill.setStyleSheet(
            f"background-color: #3C3C3C; color: white; border-radius: {radius}px;"
        )
        pill_layout.addWidget(label)
        pill_layout.addWidget(close_btn)
        return pill

    def _create_more_button(self, hidden_count: int) -> QtWidgets.QPushButton:
        """创建 n+ ‘更多’ 按钮"""
        btn: QtWidgets.QPushButton = QtWidgets.QPushButton(f"{hidden_count}+")
        btn.setProperty("is_more_button", True)
        ph: int = getattr(self, "_pill_height", 18)
        btn.setFixedHeight(max(12, ph))

        # 字号与药丸内文字一致
        base_pt: int = self.input_widget.font().pointSize()
        if base_pt <= 0:
            base_pt = 10

        f: QtGui.QFont = btn.font()
        f.setPointSize(max(6, base_pt - 4))
        btn.setFont(f)
        btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        radius: int = max(6, btn.height() // 2)
        btn.setStyleSheet(
            "QPushButton { border: none; background-color: #555; color: white;"
            f"border-radius: {radius}px; padding: 0 6px; "
            "}"
        )
        btn.setToolTip("查看所有已选文件")
        btn.clicked.connect(self._show_all_selected_files)
        return btn

    def _refresh_file_pills_display(self) -> None:
        """根据可用宽度刷新可见药丸，溢出折算为 n+"""
        if not hasattr(self, "file_list_widget"):
            return

        lw: QtWidgets.QListWidget = self.file_list_widget
        lw.clear()

        if not self.selected_files:
            lw.setVisible(False)
            return

        lw.setVisible(True)
        # 现在药丸位于输入框上方一行，无需额外定位
        available_width: int = lw.width()
        spacing: int = lw.spacing()

        # 预计算每个药丸宽度
        pill_widgets: list[QtWidgets.QWidget] = []
        widths: list[int] = []
        for fp in self.selected_files:
            pill_widget: QtWidgets.QWidget = self._create_pill_widget(fp)
            pill_widgets.append(pill_widget)
            widths.append(pill_widget.sizeHint().width())

        used: int = 0
        visible_count: int = 0
        total: int = len(pill_widgets)
        for _i, width_val in enumerate(widths):
            next_used: int = used + (spacing if visible_count > 0 else 0) + width_val
            if next_used <= available_width:
                used = next_used
                visible_count += 1
            else:
                break

        hidden: int = total - visible_count
        if hidden > 0:
            # 让出空间给 n+
            more_btn: QtWidgets.QPushButton = self._create_more_button(hidden)
            more_w: int = more_btn.sizeHint().width()
            # 若放不下，回退可见数量直到能放下 n+
            while visible_count > 0 and (used + (spacing if visible_count > 0 else 0) + more_w) > available_width:
                used -= widths[visible_count - 1]
                if visible_count > 1:
                    used -= spacing
                visible_count -= 1

        # 添加可见药丸
        for i in range(visible_count):
            item: QtWidgets.QListWidgetItem = QtWidgets.QListWidgetItem()
            item.setSizeHint(pill_widgets[i].sizeHint())
            lw.addItem(item)
            lw.setItemWidget(item, pill_widgets[i])

        # 添加 n+
        hidden = total - visible_count
        if hidden > 0:
            more_btn = self._create_more_button(hidden)
            item = QtWidgets.QListWidgetItem()
            item.setSizeHint(more_btn.sizeHint())
            lw.addItem(item)
            lw.setItemWidget(item, more_btn)

        self._position_file_pills()

    def _show_all_selected_files(self) -> None:
        """弹出对话框显示所有已选文件，支持移除"""
        dialog: QtWidgets.QDialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("已选文件")
        dialog.resize(520, 360)

        vbox: QtWidgets.QVBoxLayout = QtWidgets.QVBoxLayout(dialog)
        listw: QtWidgets.QListWidget = QtWidgets.QListWidget()

        for fp in self.selected_files:
            item: QtWidgets.QListWidgetItem = QtWidgets.QListWidgetItem(str(fp))
            listw.addItem(item)

        btn_layout: QtWidgets.QHBoxLayout = QtWidgets.QHBoxLayout()
        remove_btn: QtWidgets.QPushButton = QtWidgets.QPushButton("移除所选")
        close_btn: QtWidgets.QPushButton = QtWidgets.QPushButton("关闭")

        btn_layout.addWidget(remove_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(close_btn)
        vbox.addWidget(listw)
        vbox.addLayout(btn_layout)

        def do_remove() -> None:
            """移除所选文件"""
            selected: list[QtWidgets.QListWidgetItem] = listw.selectedItems()
            if not selected:
                return

            for it in selected:
                path: str = it.text()
                if path in self.selected_files:
                    self.selected_files.remove(path)

            self._refresh_file_pills_display()

            # 重新填充列表
            listw.clear()
            for fp in self.selected_files:
                listw.addItem(QtWidgets.QListWidgetItem(str(fp)))

        remove_btn.clicked.connect(do_remove)
        close_btn.clicked.connect(dialog.accept)
        dialog.exec_()

    def init_menu(self) -> None:
        """初始化菜单"""
        menu_bar: QtWidgets.QMenuBar = self.menuBar()

        sys_menu: QtWidgets.QMenu = menu_bar.addMenu("系统")
        sys_menu.addAction("退出", self.close)

        session_menu: QtWidgets.QMenu = menu_bar.addMenu("会话")
        session_menu.addAction("新建会话", self.new_session)
        session_menu.addAction("回收站", self.show_trash)

        help_menu: QtWidgets.QMenu = menu_bar.addMenu("帮助")
        help_menu.addAction("官网", self.open_website)
        help_menu.addAction("关于", self.show_about)

    def send_message(self) -> None:
        """发送消息（纯UI交互）"""
        text: str = self.input_widget.toPlainText().strip()
        if not text:
            return

        self.input_widget.clear()

        self.status_label.setText("AI服务正在思考中...")
        QtWidgets.QApplication.processEvents()

        # 收集UI状态参数
        use_rag: bool = self.rag_switch.isChecked()
        user_files: list | None
        if self.selected_files:
            user_files = self.selected_files
        else:
            user_files = None

        # 流式输出模式
        try:
            # 先在UI侧展示用户输入（仅UI层，不直接操作历史）
            self.append_message("user", text)

            # 收集模型参数（直接透传至引擎，底层自行校验）
            model_name: str = self.config_model_name.text().strip()
            mt_text: str = self.config_max_tokens.text().strip()
            tp_text: str = self.config_temperature.text().strip()

            # 获取引擎流式结果
            stream: Generator[str, None, None] = self.engine.send_message(
                message=text,
                model_name=model_name,
                max_tokens=int(mt_text),
                temperature=float(tp_text),
                use_rag=use_rag,
                user_files=user_files
            )

            # 简化流式输出：直接使用append_message的格式
            full_content: str = ""

            # 创建缓冲区，减少UI更新频率
            chunk_buffer: str = ""
            update_interval: float = 0.2  # 200ms更新一次
            buffer_size_threshold: int = 20  # 缓冲区大小阈值
            last_update_time: float = time.time()

            for chunk in stream:
                # 正常内容处理
                full_content += chunk
                chunk_buffer += chunk

                # 控制UI更新频率
                current_time: float = time.time()
                if (
                    current_time - last_update_time >= update_interval
                    or len(chunk_buffer) >= buffer_size_threshold
                    or any(mark in chunk for mark in ["。", ".", "\n", "!", "?", "！", "？"])
                ):

                    # 清空历史显示并重新渲染
                    self.history_widget.clear()
                    hist_dbg = self.engine.get_chat_history()
                    for message in hist_dbg:
                        self.append_message(message["role"], message["content"])

                    # 滚动到底部
                    self.history_widget.moveCursor(QtGui.QTextCursor.MoveOperation.End)
                    QtWidgets.QApplication.processEvents()

                    # 重置缓冲区和计时器
                    chunk_buffer = ""
                    last_update_time = current_time

            # 保存会话由 engine.send_message 末尾负责
            self.status_label.setText("就绪")

        except Exception as e:
            self.status_label.setText(f"流式输出错误: {str(e)}")

        # 不清理选择的文件，保留药丸供多轮追问使用
        self._position_file_pills()

    def refresh_display(self) -> None:
        """刷新UI显示（从引擎获取数据）"""
        # 从引擎获取对话历史
        chat_history: list = self.engine.get_chat_history()

        # 更新UI显示
        self.history_widget.clear()
        for message in chat_history:
            self.append_message(message["role"], message["content"])

        # 更新会话列表
        self.refresh_session_list()

    def refresh_session_list(self) -> None:
        """刷新会话列表"""
        try:
            # 保存当前选中的会话ID
            current_item: QtWidgets.QListWidgetItem | None = self.session_list.currentItem()
            current_id: str | None = None
            if current_item:
                try:
                    current_id = current_item.data(QtCore.Qt.ItemDataRole.UserRole)
                except RuntimeError:
                    # 如果项已被删除，忽略错误
                    pass

            # 清空列表
            self.session_list.clear()

            # 获取所有会话
            sessions: list = self.engine.get_all_sessions()

            # 添加到列表
            for session in sessions:
                title: str = session.get('title', '未命名会话')
                updated_at: str = (session.get('updated_at', '')[:16].replace('T', ' '))

                # 创建列表项
                item: QtWidgets.QListWidgetItem = QtWidgets.QListWidgetItem()
                item.setData(QtCore.Qt.ItemDataRole.UserRole, session['id'])
                self.session_list.addItem(item)

                # 创建自定义组件
                widget: QtWidgets.QWidget = QtWidgets.QWidget()
                layout: QtWidgets.QHBoxLayout = QtWidgets.QHBoxLayout(widget)
                layout.setContentsMargins(5, 2, 5, 2)

                # 标题标签
                title_label: QtWidgets.QLabel = QtWidgets.QLabel(title)
                title_label.setWordWrap(True)

                # 时间标签
                time_label: QtWidgets.QLabel = QtWidgets.QLabel(updated_at)
                time_label.setStyleSheet(TIME_LABEL_QSS)

                # 菜单按钮
                menu_button: QtWidgets.QPushButton = QtWidgets.QPushButton("...")
                menu_button.setFixedSize(25, 20)
                menu_button.setStyleSheet(MENU_BUTTON_QSS)
                menu_button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)

                # 创建菜单
                menu: QtWidgets.QMenu = QtWidgets.QMenu()
                edit_action = menu.addAction("编辑标题")
                delete_action = menu.addAction("删除会话")
                export_action = menu.addAction("导出会话")

                # 连接菜单项信号
                session_id: str = session['id']
                edit_action.triggered.connect(lambda checked=False, sid=session_id, t=title: self.edit_session_title(sid, t))
                delete_action.triggered.connect(lambda checked=False, sid=session_id: self.delete_session(sid))
                export_action.triggered.connect(lambda checked=False, sid=session_id, t=title: self.export_session(sid, t))

                # 连接按钮点击事件
                menu_button.clicked.connect(lambda checked=False, m=menu, b=menu_button: m.exec_(b.mapToGlobal(QtCore.QPoint(0, b.height()))))

                # 添加到布局
                right_layout: QtWidgets.QVBoxLayout = QtWidgets.QVBoxLayout()
                right_layout.addWidget(time_label, alignment=QtCore.Qt.AlignmentFlag.AlignRight)
                right_layout.addWidget(menu_button, alignment=QtCore.Qt.AlignmentFlag.AlignRight)

                layout.addWidget(title_label, 1)  # 1表示伸展因子
                layout.addLayout(right_layout, 0)  # 0表示不伸展

                # 设置自定义组件
                self.session_list.setItemWidget(item, widget)

                # 调整列表项高度以适应内容
                item.setSizeHint(widget.sizeHint())

                # 如果是当前会话，选中它
                if session['id'] == current_id:
                    self.session_list.setCurrentItem(item)

        except Exception as e:
            # 捕获任何可能的异常，确保UI不会崩溃
            print(f"刷新会话列表时出错: {e}")

    def load_history(self) -> None:
        """加载对话历史"""
        self.engine.load_history()
        self.refresh_display()

    def clear_history(self) -> None:
        """清空会话历史（UI交互）"""
        i: QtWidgets.QMessageBox.StandardButton = QtWidgets.QMessageBox.question(
            self,
            "清空历史",
            "确定要清空历史吗？",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No
        )

        if i == QtWidgets.QMessageBox.StandardButton.Yes:
            # 业务逻辑交给引擎
            self.engine.clear_history()

            # 刷新UI显示
            self.refresh_display()

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
                f"运行目录：{AGENT_DIR}"
            ),
            QtWidgets.QMessageBox.StandardButton.Ok
        )

    def select_files(self) -> None:
        """选择文件"""
        file_paths, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self,
            "选择要分析的文件",
            "",
            "支持的文档 (*.md *.txt *.pdf *.py);;所有文件 (*)"
        )

        if file_paths:
            # 累加添加新文件（去重）
            for fp in file_paths:
                if fp not in self.selected_files:
                    self.selected_files.append(fp)

            # 统一刷新可见药丸与 n+
            self.file_list_widget.setVisible(bool(self.selected_files))
            self._position_file_pills()
            self._refresh_file_pills_display()

            # 显示数量（总数）
            self.status_label.setText(
                f"已选择 {len(self.selected_files)} 个文件"
                if self.selected_files else "就绪"
            )

    def _remove_file(self, file_path: str) -> None:
        """移除选择的文件"""
        # 从已选文件列表中移除
        if file_path in self.selected_files:
            self.selected_files.remove(file_path)

        # 统一刷新显示与 n+
        self._refresh_file_pills_display()
        if self.selected_files:
            self.status_label.setText(f"已选择 {len(self.selected_files)} 个文件")
        else:
            self.file_list_widget.setVisible(False)
            self._position_file_pills()
            self.status_label.setText("就绪")

    def new_session(self) -> None:
        """新建会话"""
        self.engine.new_session()
        self.load_history()
        self.status_label.setText("已创建新会话")

    def toggle_rag_mode(self, checked: bool) -> None:
        """切换RAG模式"""
        # 确保 status_label 已经初始化
        if hasattr(self, "status_label"):
            if checked:
                self.status_label.setText("RAG模式已开启")
            else:
                self.status_label.setText("RAG模式已关闭")

    def open_website(self) -> None:
        """打开官网"""
        QtGui.QDesktopServices.openUrl(
            QtCore.QUrl("https://www.github.com/vnpy/vnag")
        )

    def show_trash(self) -> None:
        """显示回收站（已删除的会话）"""
        # 获取已删除会话
        deleted_sessions: list = self.engine.get_deleted_sessions()

        if not deleted_sessions:
            QtWidgets.QMessageBox.information(self, "回收站", "回收站为空", QtWidgets.QMessageBox.StandardButton.Ok)
            return

        dialog: TrashDialog = TrashDialog(deleted_sessions, self.engine)
        if dialog.exec_():
            self.refresh_session_list()

    def edit_session_title(self, session_id: str, current_title: str) -> None:
        """编辑会话标题"""
        new_title, ok = QtWidgets.QInputDialog.getText(
            self,
            "编辑标题",
            "请输入新标题:",
            QtWidgets.QLineEdit.EchoMode.Normal,
            current_title
        )

        if ok and new_title and new_title != current_title:
            # 更新标题
            if self.engine.session_manager.update_session_title(session_id, new_title):
                # 刷新会话列表
                self.refresh_session_list()

    def delete_session(self, session_id: str) -> None:
        """删除会话"""
        reply: QtWidgets.QMessageBox.StandardButton = QtWidgets.QMessageBox.question(
            self, "确认删除", "确定要删除这个会话吗？",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No
        )

        if reply == QtWidgets.QMessageBox.StandardButton.Yes:
            # 检查是否是当前会话
            is_current: bool = self.engine.session_manager.current_session_id == session_id

            if self.engine.delete_session(session_id):
                # 刷新会话列表
                self.refresh_session_list()

                # 如果删除的是当前会话，则清空历史显示
                if is_current:
                    self.history_widget.clear()
                    self.status_label.setText("请从左侧选择一个会话或创建新会话")

                QtWidgets.QMessageBox.information(self, "成功", "会话已删除", QtWidgets.QMessageBox.StandardButton.Ok)

    def export_session(self, session_id: str, title: str) -> None:
        """导出会话"""
        title, messages = self.engine.export_session(session_id)

        if not messages:
            QtWidgets.QMessageBox.information(self, "导出会话", "会话为空或不存在", QtWidgets.QMessageBox.StandardButton.Ok)
            return

        # 选择保存路径
        file_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "导出会话",
            f"{title}.md",
            "Markdown文件 (*.md)"
        )

        if not file_path:
            return

        try:
            content: str = format_session_export(title, messages)
            write_text_file(file_path, content)

            QtWidgets.QMessageBox.information(self, "导出会话", f"会话已成功导出到: {file_path}", QtWidgets.QMessageBox.StandardButton.Ok)

        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "导出失败", f"导出会话时发生错误: {str(e)}", QtWidgets.QMessageBox.StandardButton.Ok)

    def show_model_selector(self) -> None:
        """显示模型选择对话框"""
        # 如果没获取到模型列表则不显示对话框
        model_list: list[str] = self.engine.gateway.list_models()
        if not model_list:
            QtWidgets.QMessageBox.information(self, "模型列表", "模型列表为空", QtWidgets.QMessageBox.StandardButton.Ok)
            return

        dialog: ModelSelectorDialog = ModelSelectorDialog(self.model_name, model_list)

        if dialog.exec_():
            # 如果用户选择了模型，更新配置表单
            model_name: str = dialog.selected_model
            if model_name:
                # 只更新配置表单，不更新实例属性或配置文件
                self.config_model_name.setText(model_name)

                # 提示用户保存配置
                QtWidgets.QMessageBox.information(
                    self,
                    "模型已选择",
                    f"已选择模型: {model_name}\n请在配置页面点击保存按钮以应用更改。",
                    QtWidgets.QMessageBox.StandardButton.Ok
                )

                # 切换到配置标签页
                self.tab_widget.setCurrentIndex(1)

    def on_session_selected(self, item: QtWidgets.QListWidgetItem) -> None:
        """选择会话"""
        try:
            session_id: str = item.data(QtCore.Qt.ItemDataRole.UserRole)
            session_name: str = item.text()
            if self.engine.switch_session(session_id):
                self.load_history()
                self.status_label.setText(f"已切换到会话: {session_name}")
        except RuntimeError:
            # 如果列表项已被删除，则忽略
            pass

    def save_config(self) -> None:
        """保存配置"""
        settings: dict = {
            "gateway_name": self.config_gateway_name.text(),
            "model_name": self.config_model_name.text(),
            "max_tokens": int(self.config_max_tokens.text()),
            "temperature": float(self.config_temperature.text())
        }

        save_json("gateway_setting.json", settings)

        QtWidgets.QMessageBox.information(self, "配置已保存", "配置已保存。", QtWidgets.QMessageBox.StandardButton.Ok)


class RagSwitchButton(QtWidgets.QWidget):
    """RAG开关按钮"""

    toggled = QtCore.Signal(bool)

    def __init__(self) -> None:
        """构造函数"""
        super().__init__()
        self.setFixedSize(100, 30)  # 调整宽度以容纳更长的文本
        self._checked: bool = False

    def setChecked(self, checked: bool) -> None:
        """设置选中状态"""
        if self._checked != checked:
            self._checked = checked
            self.update()
            self.toggled.emit(checked)

    def isChecked(self) -> bool:
        """获取选中状态"""
        return self._checked

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        """鼠标点击事件"""
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.setChecked(not self._checked)

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        """绘制开关"""
        painter: QtGui.QPainter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

        # 开关背景
        rect: QtCore.QRect = self.rect().adjusted(2, 5, -2, -5)  # 减小上下边距
        radius: int = rect.height() // 2

        if self._checked:
            # 开启状态：绿色背景
            painter.setBrush(QtGui.QBrush(QtGui.QColor(76, 175, 80)))
        else:
            # 关闭状态：灰色背景
            painter.setBrush(QtGui.QBrush(QtGui.QColor(117, 117, 117)))

        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.drawRoundedRect(rect, radius, radius)

        # 开关圆形按钮
        button_rect: QtCore.QRect = QtCore.QRect()
        button_rect.setSize(QtCore.QSize(rect.height() - 4, rect.height() - 4))

        if self._checked:
            # 开启状态：按钮在右侧
            button_rect.moveCenter(QtCore.QPoint(
                rect.right() - radius, rect.center().y()
            ))
        else:
            # 关闭状态：按钮在左侧
            button_rect.moveCenter(QtCore.QPoint(
                rect.left() + radius, rect.center().y()
            ))

        painter.setBrush(QtGui.QBrush(QtGui.QColor(255, 255, 255)))
        painter.drawEllipse(button_rect)

        # 文字标签
        painter.setPen(QtGui.QColor(255, 255, 255))  # 使用白色文字，更加醒目
        font: QtGui.QFont = painter.font()
        font.setPointSize(8)  # 调大字号
        font.setBold(True)
        painter.setFont(font)

        # 直接在开关内部绘制文字
        if self._checked:
            painter.drawText(
                rect, QtCore.Qt.AlignmentFlag.AlignCenter, "RAG ON"
            )
        else:
            painter.drawText(
                rect, QtCore.Qt.AlignmentFlag.AlignCenter, "RAG OFF"
            )


class ModelSelectorDialog(QtWidgets.QDialog):
    """模型选择对话框"""

    def __init__(
        self,
        current_model: str,
        model_list: list[str]
    ) -> None:
        """构造函数"""
        super().__init__()

        self.current_model: str = current_model
        self.selected_model: str = ""
        self.model_ids: list[str] = model_list

        self.init_ui()
        self.load_models()

    def init_ui(self) -> None:
        """初始化UI"""
        self.setWindowTitle("选择模型")
        self.setFixedSize(400, 300)

        # 当前模型显示
        current_model_layout: QtWidgets.QHBoxLayout = QtWidgets.QHBoxLayout()
        current_model_layout.addWidget(QtWidgets.QLabel("当前模型:"))

        if self.current_model:
            current_model_label: QtWidgets.QLabel = QtWidgets.QLabel(self.current_model)
            current_model_label.setStyleSheet(CURRENT_MODEL_LABEL_QSS)  # 白色文本
        else:
            current_model_label = QtWidgets.QLabel("未选择")
            current_model_label.setStyleSheet(CURRENT_MODEL_PLACEHOLDER_QSS)

        current_model_layout.addWidget(current_model_label)
        current_model_layout.addStretch()

        # 搜索框
        self.search_box: QtWidgets.QLineEdit = QtWidgets.QLineEdit()
        self.search_box.setPlaceholderText("搜索模型...")
        self.search_box.textChanged.connect(self.filter_models)

        # 模型列表
        self.model_list: QtWidgets.QListWidget = QtWidgets.QListWidget()
        self.model_list.itemDoubleClicked.connect(self.accept)

        # 刷新按钮
        refresh_button: QtWidgets.QPushButton = QtWidgets.QPushButton("查询")
        refresh_button.clicked.connect(self.load_models)

        # 确定和取消按钮
        button_box: QtWidgets.QDialogButtonBox = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok |
            QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.on_accept)
        button_box.rejected.connect(self.reject)

        # 状态标签
        self.status_label: QtWidgets.QLabel = QtWidgets.QLabel("正在加载模型列表...")

        # 布局
        layout: QtWidgets.QVBoxLayout = QtWidgets.QVBoxLayout()
        layout.addLayout(current_model_layout)
        layout.addWidget(self.search_box)
        layout.addWidget(QtWidgets.QLabel("可用模型:"))
        layout.addWidget(self.model_list)
        layout.addWidget(refresh_button)
        layout.addWidget(self.status_label)
        layout.addWidget(button_box)

        self.setLayout(layout)

    def load_models(self) -> None:
        """加载模型列表"""
        self.model_list.clear()
        self.status_label.setText("正在加载模型列表...")

        for model_id in sorted(self.model_ids):
            self.model_list.addItem(model_id)

        self.status_label.setText(f"已加载 {len(self.model_ids)} 个模型")

        # 应用当前搜索过滤
        self.filter_models(self.search_box.text())

    def filter_models(self, text: str) -> None:
        """根据搜索文本过滤模型列表"""
        for i in range(self.model_list.count()):
            item: QtWidgets.QListWidgetItem = self.model_list.item(i)

            if text.lower() in item.text().lower():
                item.setHidden(False)
            else:
                item.setHidden(True)

    def on_accept(self) -> None:
        """确认选择"""
        current_item: QtWidgets.QListWidgetItem | None = self.model_list.currentItem()

        if current_item:
            self.selected_model = current_item.text()
            self.accept()
        else:
            QtWidgets.QMessageBox.warning(
                self,
                "未选择模型",
                "请选择一个模型。"
            )


class TrashDialog(QtWidgets.QDialog):
    """回收站对话框"""

    def __init__(
        self,
        deleted_sessions: list[dict],
        engine: AgentEngine,
    ) -> None:
        """构造函数"""
        super().__init__()

        self.deleted_sessions: list = deleted_sessions
        self.engine: AgentEngine = engine
        self.init_ui()

    def init_ui(self) -> None:
        self.setWindowTitle("回收站")
        self.setFixedSize(600, 400)

        # 会话列表
        self.session_list: QtWidgets.QListWidget = QtWidgets.QListWidget()
        for session in self.deleted_sessions:
            title: str = session.get('title', '未命名会话')
            deleted_at: str = session.get('updated_at', '')[:16].replace('T', ' ')
            item_text: str = f"{title} (删除于 {deleted_at})"

            item: QtWidgets.QListWidgetItem = QtWidgets.QListWidgetItem(item_text)
            item.setData(QtCore.Qt.ItemDataRole.UserRole, session['id'])
            self.session_list.addItem(item)

        # 按钮
        button_layout: QtWidgets.QHBoxLayout = QtWidgets.QHBoxLayout()

        restore_button: QtWidgets.QPushButton = QtWidgets.QPushButton("恢复")
        restore_button.clicked.connect(self.restore_session)

        permanent_delete_button: QtWidgets.QPushButton = QtWidgets.QPushButton("永久删除")
        permanent_delete_button.clicked.connect(self.permanent_delete)

        cleanup_button: QtWidgets.QPushButton = QtWidgets.QPushButton("清理全部")
        cleanup_button.clicked.connect(self.cleanup_all)

        close_button: QtWidgets.QPushButton = QtWidgets.QPushButton("关闭")
        close_button.clicked.connect(self.reject)

        button_layout.addWidget(restore_button)
        button_layout.addWidget(permanent_delete_button)
        button_layout.addWidget(cleanup_button)
        button_layout.addStretch()
        button_layout.addWidget(close_button)

        # 主布局
        main_layout: QtWidgets.QVBoxLayout = QtWidgets.QVBoxLayout()
        main_layout.addWidget(QtWidgets.QLabel("已删除的会话："))
        main_layout.addWidget(self.session_list)
        main_layout.addLayout(button_layout)

        self.setLayout(main_layout)

    def restore_session(self) -> None:
        """恢复会话"""
        current_item: QtWidgets.QListWidgetItem | None = self.session_list.currentItem()
        if not current_item:
            QtWidgets.QMessageBox.warning(self, "警告", "请选择一个会话", QtWidgets.QMessageBox.StandardButton.Ok)
            return

        try:
            session_id: str = current_item.data(QtCore.Qt.ItemDataRole.UserRole)
            if self.engine.restore_session(session_id):
                row: int = self.session_list.row(current_item)
                self.session_list.takeItem(row)
                QtWidgets.QMessageBox.information(self, "成功", "会话已恢复", QtWidgets.QMessageBox.StandardButton.Ok)

                # 如果列表为空，关闭对话框
                if self.session_list.count() == 0:
                    self.accept()
            else:
                QtWidgets.QMessageBox.warning(self, "错误", "恢复会话失败", QtWidgets.QMessageBox.StandardButton.Ok)
        except RuntimeError:
            QtWidgets.QMessageBox.warning(self, "错误", "会话项已失效，请重新选择", QtWidgets.QMessageBox.StandardButton.Ok)

    def permanent_delete(self) -> None:
        """永久删除会话"""
        current_item: QtWidgets.QListWidgetItem | None = self.session_list.currentItem()
        if not current_item:
            QtWidgets.QMessageBox.warning(self, "警告", "请选择一个会话", QtWidgets.QMessageBox.StandardButton.Ok)
            return

        reply: QtWidgets.QMessageBox.StandardButton = QtWidgets.QMessageBox.question(
            self, "确认永久删除",
            "确定要永久删除这个会话吗？此操作不可撤销！",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No
        )

        if reply == QtWidgets.QMessageBox.StandardButton.Yes:
            try:
                session_id: str = current_item.data(QtCore.Qt.ItemDataRole.UserRole)
                # 直接调用内部方法进行永久删除
                if self.engine.session_manager._permanent_delete_session(session_id):
                    row: int = self.session_list.row(current_item)
                    self.session_list.takeItem(row)
                    QtWidgets.QMessageBox.information(self, "成功", "会话已永久删除", QtWidgets.QMessageBox.StandardButton.Ok)

                    # 如果列表为空，关闭对话框
                    if self.session_list.count() == 0:
                        self.accept()
                else:
                    QtWidgets.QMessageBox.warning(self, "错误", "永久删除会话失败", QtWidgets.QMessageBox.StandardButton.Ok)
            except RuntimeError:
                QtWidgets.QMessageBox.warning(self, "错误", "会话项已失效，请重新选择", QtWidgets.QMessageBox.StandardButton.Ok)

    def cleanup_all(self) -> None:
        """清理所有已删除的会话"""
        reply: QtWidgets.QMessageBox.StandardButton = QtWidgets.QMessageBox.question(
            self, "确认清理",
            "确定要清理所有已删除的会话吗？此操作不可撤销！",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No
        )

        if reply == QtWidgets.QMessageBox.StandardButton.Yes:
            # 强制清理所有已删除的会话（忽略30天限制）
            count: int = self.engine.cleanup_deleted_sessions(force_all=True)
            if count > 0:
                QtWidgets.QMessageBox.information(self, "成功", f"已清理 {count} 个会话", QtWidgets.QMessageBox.StandardButton.Ok)
                self.accept()
            else:
                QtWidgets.QMessageBox.information(self, "提示", "没有可清理的会话", QtWidgets.QMessageBox.StandardButton.Ok)


# 导出相关：格式化为 Markdown 文本
def format_session_export(title: str, messages: list[dict]) -> str:
    """格式化导出会话为 Markdown 字符串（UI侧文案约定）。

    后续可直接复用于：复制全文到剪贴板、批量导出、分享等功能。
    """
    lines: list[str] = []
    lines.append(f"# {title}\n\n")
    lines.append(f"导出时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

    for msg in messages:
        if msg.get("role") == "user":
            role = "用户"
        else:
            role = "助手"

        timestamp: str = str(msg.get("timestamp", "")).replace('T', ' ')[:16]
        lines.append(f"## {role} ({timestamp})\n\n")
        lines.append(f"{msg.get('content', '')}\n\n")

    text: str = "".join(lines)
    return text
