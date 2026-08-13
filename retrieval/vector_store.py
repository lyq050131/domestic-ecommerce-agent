"""向量知识库封装：优先 ChromaDB + 本地 Embedding；依赖缺失时自动降级为无 RAG 模式。"""
import os
from typing import Dict, List, Optional

from config.settings import settings
from utils.logger import logger

try:
    import chromadb
    from chromadb.utils import embedding_functions

    CHROMA_AVAILABLE = True
except Exception:  # pragma: no cover
    CHROMA_AVAILABLE = False


class VectorStore:
    """ChromaDB 封装（本地持久化 + 本地 Embedding）

    未安装 chromadb / sentence-transformers 或模型加载失败时，
    自动降级为"无 RAG 模式"：检索返回空、写入为空操作，业务流程不受影响。
    """

    def __init__(self):
        self.available = False
        self.client = None
        self.embedding_function = None
        if CHROMA_AVAILABLE:
            try:
                self.embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(
                    model_name=settings.EMBEDDING_MODEL,
                    device=settings.EMBEDDING_DEVICE,
                )
                os.makedirs(settings.VECTOR_DB_PATH, exist_ok=True)
                self.client = chromadb.PersistentClient(path=settings.VECTOR_DB_PATH)
                self.available = True
                logger.info("✅ 向量数据库初始化完成（ChromaDB + 本地 Embedding）")
                return
            except Exception as e:
                logger.warning(f"向量库初始化失败，降级为无 RAG 模式: {e}")
        else:
            logger.info("未安装 chromadb，降级为无 RAG 模式（检索返回空，业务不受影响）")

    def _empty_result(self) -> Dict:
        return {"documents": [[]], "metadatas": [[]], "distances": [[]], "ids": [[]]}

    def get_collection(self, collection_name: str):
        if not self.available:
            return None
        return self.client.get_or_create_collection(
            name=collection_name,
            embedding_function=self.embedding_function,
            metadata={"hnsw:space": "cosine"},
        )

    def add_documents(self, collection_name: str, documents: List[str], metadatas: List[Dict], ids: List[str]):
        if not self.available:
            return
        try:
            collection = self.get_collection(collection_name)
            collection.add(documents=documents, metadatas=metadatas, ids=ids)
            logger.info(f"已添加 {len(documents)} 条文档到集合 [{collection_name}]")
        except Exception as e:
            logger.warning(f"写入向量库失败（跳过）: {e}")

    def search(self, collection_name: str, query: str, n_results: int = 5, filter_cond: Optional[Dict] = None) -> Dict:
        if not self.available:
            return self._empty_result()
        try:
            collection = self.get_collection(collection_name)
            results = collection.query(query_texts=[query], n_results=n_results, where=filter_cond)
            logger.info(f"在 [{collection_name}] 中检索到 {len(results['documents'][0])} 条结果")
            return results
        except Exception as e:
            logger.warning(f"向量检索失败（返回空）: {e}")
            return self._empty_result()

    def count_documents(self, collection_name: str) -> int:
        if not self.available:
            return 0
        try:
            return self.get_collection(collection_name).count()
        except Exception:
            return 0

    def get_all_collections(self) -> List[str]:
        if not self.available:
            return []
        return [col.name for col in self.client.list_collections()]


vector_store = VectorStore()