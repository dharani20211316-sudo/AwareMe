import csv
import os
from datetime import datetime
from groq import Groq
from dotenv import load_dotenv

# Load .env file
load_dotenv()

# ---------------------------
# INITIALIZE
# ---------------------------
# It is better to load the key from an environment variable for security
API_KEY = os.getenv("GROQ_API_KEY")
client = Groq(api_key=API_KEY)
CSV_FILE = "chat_history.csv"

# Ensure CSV exists with headers
def initialize_csv():
    if not os.path.exists(CSV_FILE):
        with open(CSV_FILE, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(["Timestamp", "Mode", "User Input", "AI Response"])

def log_chat(mode, user_text, ai_text):
    """Saves the chat interaction to a CSV file."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(CSV_FILE, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([timestamp, mode, user_text, ai_text])

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
        
        # Log to CSV automatically
        log_chat("Web-Chat", user_message, ai_reply)
        
        return ai_reply

    except Exception as e:
        print(f"Error calling Groq API: {e}")
        return "I'm sorry, I'm having trouble processing that right now."

# Initialize the CSV file when the module is loaded
initialize_csv()