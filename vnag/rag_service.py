import logging
from typing import Generator

from .document_service import DocumentService
from .gateway import AgentGateway
from .vector_service import VectorService


logger = logging.getLogger(__name__)


RAG_PROMPT_TEMPLATE = """基于以下上下文信息回答用户问题。如果上下文中没有相关信息，请说明无法从提供的文档中找到答案。

上下文信息：
{context}

用户问题：{question}

请基于上下文提供准确的回答："""


class RAGService:
    """RAG核心服务"""

    def __init__(self, gateway: AgentGateway) -> None:
        """构造函数"""
        self.gateway = gateway
        self.document_service = DocumentService()
        self.vector_service = VectorService()

        self._init_knowledge_base()
        logger.info("RAG service initialized")

    def _init_knowledge_base(self) -> None:
        """初始化知识库"""
        from .utility import AGENT_DIR
        docs_dir = AGENT_DIR / "docs"
        
        if not docs_dir.exists():
            return
            
        # 收集所有支持的文档文件
        doc_files = []
        for pattern in ["**/*.md", "**/*.txt", "**/*.pdf", "**/*.docx"]:
            doc_files.extend(docs_dir.glob(pattern))
        
        if doc_files and self.vector_service.get_document_count() == 0:
            file_paths = [str(f) for f in doc_files]
            self.add_documents(file_paths)
            logger.info(f"Initialized knowledge base with {len(file_paths)} documents")

    def add_documents(self, file_paths: list[str]) -> bool:
        """添加文档到知识库"""
        if not file_paths:
            return False
            
        all_chunks = []
        for file_path in file_paths:
            logger.info(f"Processing document: {file_path}")
            chunks = self.document_service.process_file(file_path)
            all_chunks.extend(chunks)

        if all_chunks:
            self.vector_service.add_documents(all_chunks)
            logger.info(f"Successfully added {len(file_paths)} documents with {len(all_chunks)} chunks")
            return True

        return False

    def _process_user_files(self, user_files: list[str] | None) -> str:
        """处理用户提交的文件"""
        if not user_files:
            return ""
            
        user_content = ""
        for file_path in user_files:
            chunks = self.document_service.process_file(file_path)
            user_content += f"\n\n用户提交文件 {file_path}:\n"
            user_content += "\n".join([chunk.text for chunk in chunks])
        return user_content

    def query(self, question: str, chat_history: list[dict[str, str]], user_files: list[str] | None = None) -> str | None:
        """RAG问答查询"""
        if not question.strip():
            return None
            
        # 检索知识库文档
        relevant_docs = self.vector_service.similarity_search(question, k=3)
        
        # 处理用户提交的文件
        user_content = self._process_user_files(user_files)
        
        # 如果既没有知识库文档也没有用户文件，使用普通聊天
        if not relevant_docs and not user_content:
            return self.gateway.invoke_model(chat_history + [{"role": "user", "content": question}])
        
        # 构建完整上下文
        context_parts = []
        
        if relevant_docs:
            kb_context = "\n\n".join([
                f"知识库文档 {i+1}:\n{doc['text']}" 
                for i, doc in enumerate(relevant_docs)
            ])
            context_parts.append(kb_context)
        
        if user_content:
            context_parts.append(user_content)
        
        context = "\n\n".join(context_parts)
        
        # 构建RAG prompt
        rag_prompt = RAG_PROMPT_TEMPLATE.format(
            context=context,
            question=question
        )
        
        # 使用RAG prompt进行问答
        messages = chat_history + [{"role": "user", "content": rag_prompt}]
        response = self.gateway.invoke_model(messages)
        
        logger.info(f"RAG query completed with {len(relevant_docs)} knowledge base docs and {len(user_files or [])} user files")
        return response

    def query_without_rag(self, question: str, chat_history: list[dict[str, str]], user_files: list[str] | None = None) -> str | None:
        """非RAG模式查询 - 只处理用户文件，不检索知识库"""
        if not question.strip():
            return None
        
        # 只处理用户提交的文件，不使用知识库
        user_content = self._process_user_files(user_files)
        
        if user_content:
            # 将用户文件内容直接加入消息（不使用RAG模板）
            final_question = f"{question}\n\n参考文件内容：{user_content}"
            messages = chat_history + [{"role": "user", "content": final_question}]
            
            logger.info(f"Non-RAG query with {len(user_files)} user files")
        else:
            # 纯对话，无文件
            messages = chat_history + [{"role": "user", "content": question}]
            logger.info("Pure chat query without RAG")
        
        return self.gateway.invoke_model(messages)

    def query_streaming(self, question: str, chat_history: list[dict[str, str]], user_files: list[str] | None = None) -> Generator[str, None, None]:
        """RAG流式问答查询"""
        if not question.strip():
            return
            
        # 检索知识库文档
        relevant_docs = self.vector_service.similarity_search(question, k=3)
        
        # 处理用户提交的文件
        user_content = self._process_user_files(user_files)
        
        # 如果既没有知识库文档也没有用户文件，使用普通聊天
        if not relevant_docs and not user_content:
            yield from self.gateway.invoke_streaming(chat_history + [{"role": "user", "content": question}])
            return
        
        # 构建完整上下文
        context_parts = []
        
        if relevant_docs:
            kb_context = "\n\n".join([
                f"知识库文档 {i+1}:\n{doc['text']}" 
                for i, doc in enumerate(relevant_docs)
            ])
            context_parts.append(kb_context)
        
        if user_content:
            context_parts.append(user_content)
        
        context = "\n\n".join(context_parts)
        
        # 构建RAG prompt
        rag_prompt = RAG_PROMPT_TEMPLATE.format(
            context=context,
            question=question
        )
        
        # 使用RAG prompt进行流式问答
        messages = chat_history + [{"role": "user", "content": rag_prompt}]
        
        logger.info(f"RAG streaming query started with {len(relevant_docs)} knowledge base docs and {len(user_files or [])} user files")
        yield from self.gateway.invoke_streaming(messages)

    def get_document_count(self) -> int:
        """获取文档数量"""
        return self.vector_service.get_document_count()

    def clear_documents(self) -> None:
        """清空知识库"""
        self.vector_service.clear_documents()
        logger.info("Knowledge base cleared")
