import os
import warnings
import hashlib
from operator import itemgetter
from langchain_groq import ChatGroq
from huggingface_hub import InferenceClient
from langchain_core.embeddings import Embeddings
from langchain_community.document_loaders import PyPDFLoader, DirectoryLoader
from langchain_community.vectorstores import FAISS
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import StrOutputParser
from langchain_community.chat_message_histories import ChatMessageHistory

warnings.filterwarnings("ignore")


class HFInferenceEmbeddings(Embeddings):
    """Lightweight wrapper using huggingface_hub InferenceClient for embeddings."""
    def __init__(self, api_key, model="sentence-transformers/all-MiniLM-L6-v2"):
        self.client = InferenceClient(token=api_key)
        self.model = model

    def embed_documents(self, texts, batch_size=50):
        all_embeddings = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            results = self.client.feature_extraction(batch, model=self.model)
            all_embeddings.extend(results.tolist())
        return all_embeddings

    def embed_query(self, text):
        return self.client.feature_extraction(text, model=self.model).tolist()


class MentalHealthLibrary:
    def __init__(self, groq_api_key, docs_folder="my_pdfs", index_folder="faiss_index"):
        self.docs_folder = docs_folder
        self.index_folder = index_folder
        
        # Initialize embeddings via HuggingFace Inference API (no local model loading)
        hf_token = os.getenv("HF_TOKEN")
        if not hf_token:
            raise ValueError("HF_TOKEN environment variable is required for embeddings")
        self.embeddings = HFInferenceEmbeddings(api_key=hf_token)
        self.history = ChatMessageHistory()
        
        # 1. Setup Vector Store
        self.vector_store = self._get_vector_store()
        
        # 2. Setup LLM
        self.llm = ChatGroq(groq_api_key=groq_api_key, model_name="llama-3.3-70b-versatile", temperature=0.2)
        
        # 3. Build the RAG Pipeline
        if self.vector_store:
            self.rag_pipeline = self._build_pipeline()
        else:
            self.rag_pipeline = None

    def _generate_folder_hash(self):
        """Creates a unique fingerprint based on file names and modification times."""
        if not os.path.exists(self.docs_folder):
            return ""
            
        files = [f for f in os.listdir(self.docs_folder) if f.endswith('.pdf')]
        if not files:
            return ""
        
        # Sort files to ensure the same files always produce the same hash
        files.sort()
        
        state_string = ""
        for f in files:
            file_path = os.path.join(self.docs_folder, f)
            # We track the filename AND the 'last modified' timestamp
            state_string += f"{f}_{os.path.getmtime(file_path)}"
            
        return hashlib.md5(state_string.encode()).hexdigest()

    def _get_vector_store(self):
        """
        Logic called by app.py: 
        Checks if the folder has changed. If yes, rebuilds. If no, loads existing.
        """
        if not os.path.exists(self.docs_folder):
            os.makedirs(self.docs_folder)
            return None

        current_hash = self._generate_folder_hash()
        state_file = os.path.join(self.index_folder, "state.txt")
        
        # --- Check if we can skip the rebuild ---
        if os.path.exists(self.index_folder) and os.path.exists(state_file):
            with open(state_file, "r") as f:
                saved_hash = f.read().strip()
            
            if current_hash == saved_hash:
                print("✅ [SYNC] No changes detected. Loading existing index.")
                return FAISS.load_local(
                    self.index_folder, 
                    self.embeddings, 
                    allow_dangerous_deserialization=True
                )

        # --- Rebuild Logic ---
        pdf_files = [f for f in os.listdir(self.docs_folder) if f.endswith('.pdf')]
        if not pdf_files:
            print("⚠️ [SYNC] No PDF files found in folder.")
            return None

        print(f"🔄 [SYNC] Changes detected. Re-indexing {len(pdf_files)} files...")
        
        try:
            loader = DirectoryLoader(self.docs_folder, glob="./*.pdf", loader_cls=PyPDFLoader)
            raw_docs = loader.load()
            
            text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=150)
            docs = text_splitter.split_documents(raw_docs)
            
            vs = FAISS.from_documents(docs, self.embeddings)
            
            if not os.path.exists(self.index_folder):
                os.makedirs(self.index_folder)
                
            vs.save_local(self.index_folder)

            # Update the state file so we don't rebuild again next time
            with open(state_file, "w") as f:
                f.write(current_hash)
            
            print("✨ [SYNC] Library rebuild complete.")
            return vs
            
        except Exception as e:
            print(f"❌ [SYNC] Error during indexing: {e}")
            return None

    def _format_docs(self, docs):
        return "\n\n".join(doc.page_content for doc in docs)

    def _build_pipeline(self):
        """Re-called by app.py after vector_store is updated."""
        if not self.vector_store:
            return None
            
        prompt = ChatPromptTemplate.from_messages([
            ("system",
             "You are a Mental Health Educator for the AwareMe application. "
             "You MUST answer ONLY using the provided context below. "
             "Do NOT use any outside knowledge whatsoever.\n\n"
             "STRICT RULES:\n"
             "1. If the answer is found in the context, answer accurately from it.\n"
             "2. If the answer is NOT in the context, reply ONLY with: "
             "\"I don't have that information in my library.\"\n"
             "3. If the user asks about anything unrelated to mental health or the documents "
             "(e.g. financial advice, coding, recipes, news, math, summarizing external content, "
             "or any other off-topic request), reply ONLY with: "
             "\"I'm sorry, that's outside my area. I can only answer questions based on the "
             "mental health resources in my library.\"\n"
             "4. Do NOT provide partial answers, guesses, or helpful redirects for off-topic requests.\n"
             "5. When the user says goodbye, thank you, bye, take care, that's all, I'm done, "
             "or anything that signals the conversation is over, respond with a warm closing message "
             "and include the exact phrase [CONVERSATION_END] at the very end of your response "
             "(on its own line). This signals the system to gracefully close the chat.\n\n"
             "Context:\n{context}"),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{input}"),
        ])

        retriever = self.vector_store.as_retriever(search_kwargs={"k": 3})
        
        return (
            {
                "context": itemgetter("input") | retriever | self._format_docs,
                "input": itemgetter("input"),
                "chat_history": itemgetter("chat_history"),
            }
            | prompt
            | self.llm
            | StrOutputParser()
        )

    def ask(self, query):
        if not self.rag_pipeline:
            return "The library is currently empty. Please add PDFs and click 'Sync Library'."
            
        response = self.rag_pipeline.invoke({
            "input": query,
            "chat_history": self.history.messages
        })
        
        self.history.add_user_message(query)
        self.history.add_ai_message(response)
        return response