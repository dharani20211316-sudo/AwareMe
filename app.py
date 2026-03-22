import os
import csv
from flask import Flask, render_template, request, jsonify
from datetime import datetime
from pymongo import MongoClient
from urllib.parse import unquote
from werkzeug.security import generate_password_hash, check_password_hash
from groq import Groq
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
# ------------------------------
# Import Analyzers
# ------------------------------
from youtube_analyzer import analyze_youtube_data

# Ensure chat_history_analyzer.py has the function 'process_chat_data' 
# that accepts a date string as an argument
try:
    from chat_history_analyzer import process_chat_data 
except ImportError:
    process_chat_data = None

# Import RAG class
try:
    from LearnMore import MentalHealthLibrary
except ImportError:
    MentalHealthLibrary = None

FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://127.0.0.1:27017/")

app = Flask(__name__)
app.secret_key = FLASK_SECRET_KEY

groq_client = Groq(api_key=GROQ_API_KEY)
CSV_FILE = "chat_history.csv"

if MentalHealthLibrary:
    mental_health_lib = MentalHealthLibrary(groq_api_key=GROQ_API_KEY)

# Initialize CSV if not exists
if not os.path.exists(CSV_FILE):
    with open(CSV_FILE, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(["Timestamp", "Mode", "User Input", "AI Response"])

# ------------------------------
# MongoDB Setup
# ------------------------------
mongo_client = MongoClient(MONGO_URI)
history_db = mongo_client["historyDB"]
youtube_collection = history_db["youtube"]
chat_collection = history_db["personal_chats"]
auth_db = mongo_client["authentication"]
users_collection = auth_db["users"]

# ------------------------------
# Navigation Routes
# ------------------------------
@app.route("/")
def login_page(): return render_template("login.html")

@app.route("/signup")
def signup_page(): return render_template("signup.html")

@app.route("/home")
def home(): return render_template("home_page.html")

@app.route("/flash_cards")
def flash_cards(): return render_template("flash_cards.html")

@app.route("/chat")
def chat(): return render_template("chatbot.html")

@app.route("/calendar")
def calendar(): return render_template("calender.html")

@app.route("/analysis")
def youtube_analysis_dashboard(): return render_template("analysis.html")

@app.route("/chat-analysis")
def chat_analysis_dashboard(): return render_template("chat_dashboard.html")

@app.route("/learning")
def learning_page():
    pdf_folder = "my_pdfs"
    pdfs = [f for f in os.listdir(pdf_folder) if f.endswith('.pdf')] if os.path.exists(pdf_folder) else []
    return render_template("learn_more.html", pdfs=pdfs)

# ------------------------------
# Unified Analysis Engine (The Traffic Controller)
# ------------------------------
@app.route("/api/run-analysis", methods=["POST"])
def run_analysis():
    """Route triggered by the Calendar to start specific platform analysis."""
    try:
        data = request.get_json()
        selected_date = data.get("date")      # Format: YYYY-MM-DD
        platform = data.get("platform")        # Format: 'youtube' or 'safespace'
        
        if not selected_date or not platform:
            return jsonify({"error": "Missing date or platform"}), 400

        # Handle YouTube Analysis
        if platform == "youtube":
            date_obj = datetime.strptime(selected_date, "%Y-%m-%d").date()
            result = analyze_youtube_data(date_obj)
            return jsonify({"status": "success", "redirect": "/analysis"})

        # Handle SafeSpace (Chat History) Analysis
        elif platform == "safespace":
            if process_chat_data:
                # Pass the date string directly to your analyzer function
                result = process_chat_data(selected_date) 
                
                # Check if the analyzer returned an error (e.g., no logs for that date)
                if isinstance(result, dict) and result.get("status") == "error":
                    return jsonify(result), 404
                    
                return jsonify({"status": "success", "redirect": "/chat-analysis"})
            else:
                return jsonify({"error": "Chat analyzer script (chat_history_analyzer.py) not found or process_chat_data function missing"}), 500

        return jsonify({"error": "Invalid platform"}), 400

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ------------------------------
# Data APIs for Dashboards
# ------------------------------
@app.route('/api/get-latest-chat-analysis')
def get_latest_chat():
    latest_doc = chat_collection.find().sort("_id", -1).limit(1)
    result = list(latest_doc)
    if not result:
        return jsonify({"daily_summary": {}, "entries": []})
    result[0].pop('_id')
    return jsonify(result[0])

@app.route("/get-chart-data")
def get_youtube_chart_data():
    doc = youtube_collection.find_one({}, sort=[("_id", -1)])
    if doc and "videos" in doc:
        return jsonify(doc["videos"]), 200
    return jsonify({"error": "No data found"}), 404

# ------------------------------
# AI Chat & RAG APIs
# ------------------------------
@app.route("/api/chat", methods=["POST"])
def chat_with_ai():
    try:
        data = request.get_json()
        user_message = data.get("message")
        messages = [
            {"role": "system", "content": "You are AwareMe, an empathetic therapeutic assistant specializing in cognitive distortions."},
            {"role": "user", "content": user_message}
        ]
        completion = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
        )
        ai_response = completion.choices[0].message.content
        return jsonify({"reply": ai_response, "label": "Analysis Complete"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/learn", methods=["POST"])
def learn_api():
    if not mental_health_lib:
        return jsonify({"error": "Library not initialized"}), 500
    data = request.get_json()
    answer = mental_health_lib.ask(data.get("question"))
    return jsonify({"answer": answer}), 200

# ------------------------------
# Authentication
# ------------------------------
@app.route("/register", methods=["POST"])
def register():
    data = request.get_json()
    username, password = data.get("username"), data.get("password")
    if users_collection.find_one({"username": username}): 
        return jsonify({"error": "User exists"}), 400
    users_collection.insert_one({
        "username": username, 
        "password": generate_password_hash(password), 
        "created_at": datetime.utcnow()
    })
    return jsonify({"message": "User registered"}), 201

@app.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    user = users_collection.find_one({"username": data.get("username")})
    if user and check_password_hash(user["password"], data.get("password")):
        return jsonify({"message": "Login successful"}), 200
    return jsonify({"error": "Invalid credentials"}), 401

if __name__ == "__main__":
    app.run(debug=True)





# import os
# from flask import Flask, render_template, request, jsonify, redirect, url_for
# from datetime import datetime
# from youtube_analyzer import analyze_youtube_data
# from pymongo import MongoClient
# from urllib.parse import unquote
# from werkzeug.security import generate_password_hash, check_password_hash
# from groq import Groq

# app = Flask(__name__)
# app.secret_key = os.environ.get("FLASK_SECRET_KEY", "supersecretkey")
# groq_client = Groq(api_key="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")
# # ------------------------------
# # MongoDB Setup
# # ------------------------------
# mongo_client = MongoClient("mongodb://127.0.0.1:27017/")
# history_db = mongo_client["historyDB"]
# youtube_collection = history_db["youtube"]

# auth_db = mongo_client["authentication"]
# users_collection = auth_db["users"]

# # ------------------------------
# # Page Rendering Routes
# # ------------------------------
# @app.route("/")
# def login_page(): 
#     return render_template("login.html")

# @app.route("/home")
# def home(): 
#     return render_template("home_page.html")

# @app.route("/flash_cards")
# def flash_cards_page(): 
#     return render_template("flash_cards.html")

# @app.route("/analysis")
# def analysis(): 
#     return render_template("analysis.html")

# @app.route("/piechartnew.html")
# def piechart_page():
#     return render_template("piechartnew.html")

# @app.route("/calendar")
# def calendar(): 
#     return render_template("calender.html")

# @app.route("/signup")
# def signup_page(): 
#     return render_template("signup.html")

# @app.route('/transcript')
# def transcript_page(): 
#     return render_template('transcript.html')

# # ------------------------------
# # Authentication Routes
# # ------------------------------
# @app.route("/register", methods=["POST"])
# def register():
#     data = request.get_json()
#     username, password = data.get("username"), data.get("password")
#     if not username or not password: 
#         return jsonify({"error": "Missing credentials"}), 400
#     if users_collection.find_one({"username": username}): 
#         return jsonify({"error": "User exists"}), 400
    
#     users_collection.insert_one({
#         "username": username,
#         "password": generate_password_hash(password),
#         "created_at": datetime.utcnow()
#     })
#     return jsonify({"message": "User registered successfully"}), 201

# @app.route("/login", methods=["POST"])
# def login():
#     data = request.get_json()
#     user = users_collection.find_one({"username": data.get("username")})
#     if user and check_password_hash(user["password"], data.get("password")):
#         return jsonify({"message": "Login successful"}), 200
#     return jsonify({"error": "Invalid credentials"}), 401

# # ------------------------------
# # YouTube Analyzer API
# # ------------------------------
# @app.route("/api/analyze/youtube", methods=["POST"])
# def analyze_youtube():
#     try:
#         data = request.get_json()
#         selected_date = data.get("selectedDate")
#         selected_date_obj = datetime.strptime(selected_date, "%Y-%m-%d").date()
#         result = analyze_youtube_data(selected_date_obj)
#         return jsonify(result), 200
#     except Exception as e:
#         return jsonify({"status": "error", "message": str(e)}), 500

# # ------------------------------
# # Dashboard / Data APIs
# # ------------------------------

# # New Route: Specifically for your separate table query
# @app.route("/api/video-stats-table")
# def get_video_stats_table():
#     try:
#         # Fetching only the videos field from all documents
#         cursor = youtube_collection.find({}, {"videos": 1, "_id": 0})
#         table_data = []
        
#         for doc in cursor:
#             videos = doc.get("videos", [])
#             for video in videos:
#                 analysis = video.get("analysis_summary", {})
#                 table_data.append({
#                     "timestamp": video.get("timestamp", "N/A"),
#                     "distortion_percentage": analysis.get("distortion_percentage", 0.0),
#                     "video_title": video.get("video_title", "Unknown Title")
#                 })
        
#         return jsonify(table_data), 200
#     except Exception as e:
#         return jsonify({"error": str(e)}), 500

# # Used by the 3D Pie Chart (piechartnew.html)
# @app.route("/api/distortion-breakdown")
# def get_distortion_breakdown():
#     try:
#         doc = youtube_collection.find_one({}, sort=[("_id", -1)])
#         if doc and "daily_summary" in doc:
#             return jsonify(doc["daily_summary"]["distortion_category_breakdown"]), 200
#         return jsonify({"status": "error", "message": "No summary found"}), 404
#     except Exception as e:
#         return jsonify({"status": "error", "message": str(e)}), 500

# # Used by analysis.html for the result table
# @app.route("/get-chart-data")
# def get_chart_data():
#     try:
#         doc = youtube_collection.find_one({}, sort=[("_id", -1)])
#         if doc and "videos" in doc:
#             return jsonify(doc["videos"]), 200
#         return jsonify({"error": "No data found"}), 404
#     except Exception as e:
#         return jsonify({"error": str(e)}), 500

# @app.route('/api/get-transcript')
# def get_transcript_api():
#     video_title = unquote(request.args.get('title', ''))
#     doc = youtube_collection.find_one(
#         {"videos.video_title": video_title},
#         sort=[("_id", -1)],
#         projection={"videos.$": 1}
#     )
#     if doc:
#         return jsonify(doc["videos"][0]), 200
#     return jsonify({"error": "Video not found"}), 404

# # ------------------------------
# # File Upload
# # ------------------------------
# @app.route('/upload-analysis-file', methods=['POST'])
# def upload_file():
#     file = request.files.get('file')
#     if file:
#         file.save(os.path.join(os.getcwd(), file.filename))
#         return jsonify({"message": "File saved"}), 200
#     return jsonify({"error": "Upload failed"}), 400


# @app.route("/chat")
# def chat(): 
#     # This assumes your chatbot file is named 'chatbot.html' inside the 'templates' folder
#     return render_template("chatbot.html")

# # Add this import at the top of app.py
# from groq import Groq

# # Initialize Groq client
# groq_client = Groq(api_key="your_gsk_key_here")

# # Define the Chat API
# @app.route("/api/chat", methods=["POST"])
# def chat_with_ai():
#     try:
#         data = request.get_json()
#         user_message = data.get("message")
        
#         # System prompt to maintain the "AwareMe" persona
#         messages = [
#             {"role": "system", "content": "You are AwareMe, a therapeutic assistant specializing in detecting cognitive distortions."},
#             {"role": "user", "content": user_message}
#         ]

#         # Call Groq API
#         completion = groq_client.chat.completions.create(
#             model="llama-3.3-70b-versatile",
#             messages=messages,
#         )

#         ai_response = completion.choices[0].message.content
        
#         # Here you could add logic to detect patterns and return a 'label' 
#         # for your frontend "distortion-alert" tag.
#         return jsonify({
#             "reply": ai_response,
#             "label": "Pattern Analysis Complete"
#         }), 200

#     except Exception as e:
#         return jsonify({"error": str(e)}), 500

# if __name__ == "__main__":
#     app.run(debug=True)












# # import os
# # from flask import Flask, render_template, request, jsonify, redirect, url_for
# # from datetime import datetime
# # from youtube_analyzer import analyze_youtube_data
# # from pymongo import MongoClient
# # from urllib.parse import unquote
# # from werkzeug.security import generate_password_hash, check_password_hash

# # app = Flask(__name__)
# # app.secret_key = os.environ.get("FLASK_SECRET_KEY", "supersecretkey")

# # # ------------------------------
# # # MongoDB Setup
# # # ------------------------------
# # mongo_client = MongoClient("mongodb://127.0.0.1:27017/")
# # history_db = mongo_client["historyDB"]
# # youtube_collection = history_db["youtube"]

# # auth_db = mongo_client["authentication"]
# # users_collection = auth_db["users"]

# # # ------------------------------
# # # Page Rendering Routes
# # # ------------------------------
# # @app.route("/")
# # def login_page(): 
# #     return render_template("login.html")

# # @app.route("/home")
# # def home(): 
# #     return render_template("home_page.html")

# # @app.route("/flash_cards")
# # def flash_cards_page(): 
# #     return render_template("flash_cards.html")

# # @app.route("/analysis")
# # def analysis(): 
# #     return render_template("analysis.html")

# # # FIXED: Added the route for piechartnew.html to resolve 404
# # @app.route("/piechartnew.html")
# # def piechart_page():
# #     return render_template("piechartnew.html")

# # @app.route("/calendar")
# # def calendar(): 
# #     return render_template("calender.html")

# # @app.route("/signup")
# # def signup_page(): 
# #     return render_template("signup.html")

# # @app.route('/transcript')
# # def transcript_page(): 
# #     return render_template('transcript.html')

# # # ------------------------------
# # # Authentication Routes
# # # ------------------------------
# # @app.route("/register", methods=["POST"])
# # def register():
# #     data = request.get_json()
# #     username, password = data.get("username"), data.get("password")
# #     if not username or not password: 
# #         return jsonify({"error": "Missing credentials"}), 400
# #     if users_collection.find_one({"username": username}): 
# #         return jsonify({"error": "User exists"}), 400
    
# #     users_collection.insert_one({
# #         "username": username,
# #         "password": generate_password_hash(password),
# #         "created_at": datetime.utcnow()
# #     })
# #     return jsonify({"message": "User registered successfully"}), 201

# # @app.route("/login", methods=["POST"])
# # def login():
# #     data = request.get_json()
# #     user = users_collection.find_one({"username": data.get("username")})
# #     if user and check_password_hash(user["password"], data.get("password")):
# #         return jsonify({"message": "Login successful"}), 200
# #     return jsonify({"error": "Invalid credentials"}), 401

# # # ------------------------------
# # # YouTube Analyzer API
# # # ------------------------------
# # @app.route("/api/analyze/youtube", methods=["POST"])
# # def analyze_youtube():
# #     try:
# #         data = request.get_json()
# #         selected_date = data.get("selectedDate")
# #         selected_date_obj = datetime.strptime(selected_date, "%Y-%m-%d").date()

# #         # Executes the AI analysis logic
# #         result = analyze_youtube_data(selected_date_obj)
# #         return jsonify(result), 200
# #     except Exception as e:
# #         return jsonify({"status": "error", "message": str(e)}), 500

# # # ------------------------------
# # # Dashboard / Data APIs
# # # ------------------------------

# # # Used by the 3D Pie Chart (piechartnew.html)
# # @app.route("/api/distortion-breakdown")
# # def get_distortion_breakdown():
# #     try:
# #         # Get latest document and pull the breakdown object
# #         doc = youtube_collection.find_one({}, sort=[("_id", -1)])
# #         if doc and "daily_summary" in doc:
# #             # Returns the object containing { "Category": Percentage }
# #             return jsonify(doc["daily_summary"]["distortion_category_breakdown"]), 200
# #         return jsonify({"status": "error", "message": "No summary found"}), 404
# #     except Exception as e:
# #         return jsonify({"status": "error", "message": str(e)}), 500

# # # Used by analysis.html for the result table
# # @app.route("/get-chart-data")
# # def get_chart_data():
# #     try:
# #         doc = youtube_collection.find_one({}, sort=[("_id", -1)])
# #         if doc and "videos" in doc:
# #             return jsonify(doc["videos"]), 200
# #         return jsonify({"error": "No data found"}), 404
# #     except Exception as e:
# #         return jsonify({"error": str(e)}), 500

# # @app.route('/api/get-transcript')
# # def get_transcript_api():
# #     video_title = unquote(request.args.get('title', ''))
# #     doc = youtube_collection.find_one(
# #         {"videos.video_title": video_title},
# #         sort=[("_id", -1)],
# #         projection={"videos.$": 1}
# #     )
# #     if doc:
# #         return jsonify(doc["videos"][0]), 200
# #     return jsonify({"error": "Video not found"}), 404

# # # ------------------------------
# # # File Upload
# # # ------------------------------
# # @app.route('/upload-analysis-file', methods=['POST'])
# # def upload_file():
# #     file = request.files.get('file')
# #     if file:
# #         file.save(os.path.join(os.getcwd(), file.filename))
# #         return jsonify({"message": "File saved"}), 200
# #     return jsonify({"error": "Upload failed"}), 400

# # if __name__ == "__main__":
# #     app.run(debug=True)