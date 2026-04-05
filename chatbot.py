import os
from datetime import datetime
from groq import Groq
from pymongo import MongoClient
from dotenv import load_dotenv

# Load .env file
load_dotenv()

# ---------------------------
# INITIALIZE
# ---------------------------
API_KEY = os.getenv("GROQ_API_KEY")
MONGO_URI = os.getenv("MONGO_URI")
client = Groq(api_key=API_KEY)

def get_chat_history_collection():
    mongo_client = MongoClient(MONGO_URI)
    db = mongo_client["historyDB"]
    return db["chat_history"]

def log_chat(mode, user_text, ai_text):
    """Saves the chat interaction to MongoDB."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    col = get_chat_history_collection()
    col.insert_one({
        "Timestamp": timestamp,
        "Mode": mode,
        "User Input": user_text,
        "AI Response": ai_text
    })

def get_ai_response(user_message):
    """
    Connects to Groq API and returns the AI's response.
    This replaces the 'while True' loop for web compatibility.
    """
    try:
        # System prompt defines the AI's personality
        messages = [
            {
                "role": "system", 
                "content": "You are AwareMe, a professional cognitive assistant. "
                           "Your goal is to help users identify cognitive distortions. "
                           "Be empathetic, grounded, and helpful."
            },
            {"role": "user", "content": user_message}
        ]

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            stream=False # Stream=False is easier for simple web responses
        )
        
        ai_reply = response.choices[0].message.content
        
        # Log to MongoDB
        log_chat("Web-Chat", user_message, ai_reply)
        
        return ai_reply

    except Exception as e:
        print(f"Error calling Groq API: {e}")
        return "I'm sorry, I'm having trouble processing that right now."