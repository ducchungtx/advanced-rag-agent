import os

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from langchain_google_genai import GoogleGenerativeAIEmbeddings, ChatGoogleGenerativeAI
from langchain_chroma import Chroma
import uvicorn

load_dotenv()

app = FastAPI(title="RAG API Hỗ Trợ Nội Bộ")


class QueryRequest(BaseModel):
    query: str


llm = ChatGoogleGenerativeAI(model=os.getenv("GOOGLE_MODEL"), temperature=0)
embeddings = GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-001")

vectorstore = Chroma(
    persist_directory="data/chroma",
    embedding_function=embeddings,
)


@app.post("/chat")
async def chat_with_rag(request: QueryRequest):
    try:
        user_query = request.query

        retriever = vectorstore.as_retriever(search_kwargs={"k": 4})
        relevant_docs = retriever.invoke(user_query)

        context = "\n".join(doc.page_content for doc in relevant_docs)
        response = llm.invoke(
            f"Dựa trên tài liệu sau, trả lời câu hỏi.\n\nTài liệu:\n{context}\n\nCâu hỏi: {user_query}"
        )

        return {"answer": response.content, "query": user_query}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
