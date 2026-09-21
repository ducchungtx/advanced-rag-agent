import os

from dotenv import load_dotenv
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma

load_dotenv()

# llm = ChatGoogleGenerativeAI(model=os.getenv("GOOGLE_MODEL"), temperature=0)

# # Thử nghiệm LLM
# # response = llm.invoke("Xin chào, bạn khoẻ không?")
# # print(response.content)

embeddings = GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-001")

# --- Ingest (chỉ bật khi thêm PDF mới hoặc tạo lại DB) ---
# loader = PyPDFLoader("data/pdfs/260826_TB93_VPCL_Chan chinh cong tac to chuc an giua ca tai Can tin VP THACO Chu Lai.pdf")
# documents = loader.load()
# text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200, separators=["\n\n", "\n", ".", " ", ""])
# texts = text_splitter.split_documents(documents)
# vectorstore = Chroma.from_documents(texts, embeddings, persist_directory="data/chroma")
# print(len(texts))
# print(texts[1].page_content)

# Mở lại Vector DB đã lưu
vectorstore = Chroma(
    persist_directory="data/chroma",
    embedding_function=embeddings,
)

# Tạo công cụ tìm kiếm từ Vector Database, lấy ra 4 đoạn liên quan nhất (k=4)
retriever = vectorstore.as_retriever(search_kwargs={"k": 4})

query = "Thời gian ăn trưa là lúc mấy giờ?"

# Lệnh này sẽ tự động: nhúng câu hỏi -> tìm kiếm -> trả về kết quả
relevant_docs = retriever.invoke(query)

print(f"Đã tìm thấy {len(relevant_docs)} đoạn tài liệu liên quan nhất!")
for i, doc in enumerate(relevant_docs, 1):
    print(f"\n--- Đoạn {i} ---\n{doc.page_content}")
