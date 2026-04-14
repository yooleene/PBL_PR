"""RAG 시스템 - ChromaDB + Gemini 임베딩
회사 내부 자료(입장문, 보도자료 등)를 벡터DB에 저장하고 검색하는 모듈"""

import os
import uuid
import chromadb
from google import genai

# 싱글턴
_client = None
_collection = None


def _get_collection():
    """ChromaDB 컬렉션 가져오기 (없으면 생성)"""
    global _client, _collection
    if _collection is None:
        db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "chroma_db")
        os.makedirs(db_path, exist_ok=True)
        _client = chromadb.PersistentClient(path=db_path)
        _collection = _client.get_or_create_collection(
            name="company_docs",
            metadata={"hnsw:space": "cosine"},
        )
    return _collection


def _get_embedding(text):
    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
    result = client.models.embed_content(
        model="text-embedding-004",
        contents=text,
    )
    return result.embeddings[0].values


def _split_text(text, chunk_size=500, overlap=50):
    """텍스트를 청크로 분할"""
    if len(text) <= chunk_size:
        return [text]
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        if chunk.strip():
            chunks.append(chunk.strip())
        start = end - overlap
    return chunks


# ──────────────────────────────────────────────
# 문서 저장
# ──────────────────────────────────────────────

def add_document(text, filename, category="기타", company="포스코홀딩스"):
    """
    문서를 벡터DB에 저장
    - text: 문서 전체 텍스트
    - filename: 파일명
    - category: 입장문/보도자료/내부자료/사과문/기타
    - company: 관련 사업회사
    반환: (doc_id, chunk_count)
    """
    collection = _get_collection()
    doc_id = f"{uuid.uuid4().hex[:8]}_{filename}"

    chunks = _split_text(text, chunk_size=500, overlap=50)

    ids = []
    documents = []
    embeddings = []
    metadatas = []

    for i, chunk in enumerate(chunks):
        chunk_id = f"{doc_id}__chunk_{i}"
        embedding = _get_embedding(chunk)

        ids.append(chunk_id)
        documents.append(chunk)
        embeddings.append(embedding)
        metadatas.append({
            "doc_id": doc_id,
            "filename": filename,
            "category": category,
            "company": company,
            "chunk_index": i,
        })

    if ids:
        collection.add(
            ids=ids,
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas,
        )

    return doc_id, len(ids)


# ──────────────────────────────────────────────
# 문서 검색
# ──────────────────────────────────────────────

def search_documents(query, company=None, n_results=5):
    """
    쿼리와 관련된 문서 검색
    - query: 검색 키워드/문장
    - company: 특정 사업회사로 필터 (None이면 전체)
    - n_results: 반환할 결과 수
    """
    collection = _get_collection()
    if collection.count() == 0:
        return []

    query_embedding = _get_embedding(query)

    # 사업회사 필터
    where_filter = {"company": company} if company else None

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=min(n_results, collection.count()),
        where=where_filter,
    )

    docs = []
    if results and results["documents"]:
        for i, doc_text in enumerate(results["documents"][0]):
            meta = results["metadatas"][0][i] if results["metadatas"] else {}
            distance = results["distances"][0][i] if results["distances"] else 0
            similarity = round(1 - distance, 3)

            docs.append({
                "content": doc_text,
                "metadata": meta,
                "similarity": similarity,
            })

    return docs


def search_and_format_for_prompt(query, company=None, n_results=5):
    """
    검색 결과를 Gemini 프롬프트에 넣을 텍스트로 포맷
    """
    docs = search_documents(query, company, n_results)

    if not docs:
        return "(관련 내부 자료 없음)", docs

    formatted = []
    for i, doc in enumerate(docs, 1):
        meta = doc["metadata"]
        formatted.append(
            f"[내부자료 {i}] (유사도: {doc['similarity']})\n"
            f"- 파일: {meta.get('filename', '알 수 없음')}\n"
            f"- 분류: {meta.get('category', '기타')}\n"
            f"- 관련회사: {meta.get('company', '전체')}\n"
            f"- 내용: {doc['content']}"
        )

    return "\n\n".join(formatted), docs


# ──────────────────────────────────────────────
# 문서 관리
# ──────────────────────────────────────────────

def get_all_documents():
    """저장된 모든 문서 목록 (doc_id 기준 그룹핑)"""
    collection = _get_collection()
    if collection.count() == 0:
        return []

    results = collection.get()
    doc_map = {}
    for i, chunk_id in enumerate(results["ids"]):
        meta = results["metadatas"][i] if results["metadatas"] else {}
        doc_id = meta.get("doc_id", chunk_id)

        if doc_id not in doc_map:
            doc_map[doc_id] = {
                "id": doc_id,
                "filename": meta.get("filename", "알 수 없음"),
                "category": meta.get("category", "기타"),
                "company": meta.get("company", "전체"),
                "chunk_count": 0,
            }
        doc_map[doc_id]["chunk_count"] += 1

    return list(doc_map.values())


def delete_document(doc_id):
    """문서 삭제 (모든 청크)"""
    collection = _get_collection()
    all_data = collection.get()
    to_delete = []
    for i, chunk_id in enumerate(all_data["ids"]):
        meta = all_data["metadatas"][i]
        if meta.get("doc_id") == doc_id:
            to_delete.append(chunk_id)

    if to_delete:
        collection.delete(ids=to_delete)
    return len(to_delete)


def get_doc_count():
    """저장된 총 청크 수"""
    collection = _get_collection()
    return collection.count()
