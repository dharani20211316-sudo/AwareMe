#!/usr/bin/env python3
"""
AwareMe System Class Diagram Generator
Generates a comprehensive class diagram for the AwareMe Flask application
"""

import graphviz
from datetime import datetime

def create_class_diagram():
    """Generate a class diagram for the AwareMe system"""

    # Create a new directed graph
    dot = graphviz.Digraph('AwareMe_Class_Diagram', comment='AwareMe System Architecture')

    # Set graph attributes
    dot.attr(rankdir='TB', size='12,16')
    dot.attr('node', shape='record', fontname='Arial', fontsize='10')

    # Main Flask Application
    dot.node('FlaskApp', '''{
Flask Application (app.py)|
+ app: Flask|
+ groq_client: Groq|
+ mongo_client: MongoClient|
+ users_collection: Collection|
+ youtube_collection: Collection|
+ chat_collection: Collection|
+ CSV_FILE: str|
+ log_action(username, action, ip)|
+ register()|
+ login()|
+ run_analysis()|
+ chat_with_ai()|
+ navigation routes (/, /home, etc.)
}''')

    # Database Collections
    dot.node('UsersCollection', '''{
Users Collection (MongoDB)|
+ username: str|
+ password: str (hashed)|
+ created_at: datetime|
+ status: str|
+ find_one(query)|
+ insert_one(document)|
+ update_one(query, update)
}''')

    dot.node('YouTubeCollection', '''{
YouTube Collection (MongoDB)|
+ daily_summary: dict|
+ videos: list[dict]|
+ analysis_date: str|
+ total_videos_processed: int|
+ distortion_category_breakdown: dict|
+ insert_one(document)|
+ find_one(query, sort)
}''')

    dot.node('ChatCollection', '''{
Chat Collection (MongoDB)|
+ daily_summary: dict|
+ entries: list[dict]|
+ analysis_date: str|
+ total_entries_processed: int|
+ insert_one(document)|
+ find_one(query)
}''')

    # YouTube Analyzer
    dot.node('YouTubeAnalyzer', '''{
YouTubeAnalyzer (youtube_analyzer.py)|
+ parse_youtube_history(html_file_path) -> DataFrame|
+ extract_youtube_transcripts_for_date(date, df) -> dict|
+ analyze_youtube_data(date, html_file) -> dict
}''')

    dot.node('FreeTranscriptExtractor', '''{
FreeTranscriptExtractor|
+ whisper_model: Whisper|
+ extract(url, use_direct_transcript) -> str|
+ _extract_youtube_transcript(url) -> str|
+ _download_and_transcribe(url) -> str
}''')

    # Chat History Analyzer
    dot.node('ChatHistoryAnalyzer', '''{
ChatHistoryAnalyzer (chat_history_analyzer.py)|
+ process_chat_data(date, csv_path) -> dict|
+ get_chat_collection() -> Collection
}''')

    # Model Processor
    dot.node('ModelProcessor', '''{
ModelProcessor (model_processor.py)|
+ identify_cognitive_distortions_llm(text) -> dict|
+ regex_distortion_detector(text, distortions) -> dict|
+ split_into_sentences(text) -> list|
+ clean_overlapping_snippets(snippets) -> list|
+ process_transcripts(csv_path) -> dict|
+ get_db_collection() -> Collection
}''')

    # Mental Health Library
    dot.node('MentalHealthLibrary', '''{
MentalHealthLibrary (LearnMore.py)|
+ groq_client: Groq|
+ vector_store: FAISS|
+ pipeline: LangChain Pipeline|
+ __init__(groq_api_key, docs_folder, index_folder)|
+ _get_vector_store() -> FAISS|
+ _build_pipeline() -> Pipeline|
+ ask(query) -> str
}''')

    # Chatbot Module
    dot.node('Chatbot', '''{
Chatbot (chatbot.py)|
+ initialize_csv()|
+ log_chat(mode, user_text, ai_text)|
+ get_ai_response(user_message) -> str
}''')

    # External Services
    dot.node('GroqAPI', '''{
Groq API (External Service)|
+ chat.completions.create()|
+ model: llama-3.3-70b-versatile|
+ temperature: float|
+ max_tokens: int
}''')

    dot.node('HuggingFaceAPI', '''{
HuggingFace API (External Service)|
+ InferenceClient.text_generation()|
+ model: custom LLM endpoint|
+ max_new_tokens: int
}''')

    dot.node('MongoDB', '''{
MongoDB (Database)|
+ authentication.users|
+ historyDB.youtube|
+ historyDB.personal_chats|
+ serverSelectionTimeoutMS: 5000|
+ ping() -> bool
}''')

    # Define relationships (edges)
    # Flask App relationships
    dot.edge('FlaskApp', 'UsersCollection', label='uses')
    dot.edge('FlaskApp', 'YouTubeCollection', label='uses')
    dot.edge('FlaskApp', 'ChatCollection', label='uses')
    dot.edge('FlaskApp', 'YouTubeAnalyzer', label='calls')
    dot.edge('FlaskApp', 'ChatHistoryAnalyzer', label='calls')
    dot.edge('FlaskApp', 'ModelProcessor', label='calls')
    dot.edge('FlaskApp', 'MentalHealthLibrary', label='imports')
    dot.edge('FlaskApp', 'Chatbot', label='imports')
    dot.edge('FlaskApp', 'GroqAPI', label='uses')
    dot.edge('FlaskApp', 'MongoDB', label='connects to')

    # Analyzer relationships
    dot.edge('YouTubeAnalyzer', 'FreeTranscriptExtractor', label='uses')
    dot.edge('YouTubeAnalyzer', 'ModelProcessor', label='calls')
    dot.edge('YouTubeAnalyzer', 'YouTubeCollection', label='writes to')

    dot.edge('ChatHistoryAnalyzer', 'ModelProcessor', label='calls')
    dot.edge('ChatHistoryAnalyzer', 'ChatCollection', label='writes to')

    dot.edge('ModelProcessor', 'HuggingFaceAPI', label='uses')
    dot.edge('ModelProcessor', 'YouTubeCollection', label='writes to')
    dot.edge('ModelProcessor', 'ChatCollection', label='writes to')

    # Mental Health Library relationships
    dot.edge('MentalHealthLibrary', 'GroqAPI', label='uses')

    # Chatbot relationships
    dot.edge('Chatbot', 'GroqAPI', label='uses')

    # Database relationships
    dot.edge('UsersCollection', 'MongoDB', label='belongs to')
    dot.edge('YouTubeCollection', 'MongoDB', label='belongs to')
    dot.edge('ChatCollection', 'MongoDB', label='belongs to')

    return dot

def create_data_flow_diagram():
    """Create a data flow diagram showing the system workflow"""

    dot = graphviz.Digraph('AwareMe_Data_Flow', comment='AwareMe Data Flow')
    dot.attr(rankdir='LR', size='14,10')
    dot.attr('node', shape='box', fontname='Arial', fontsize='10')

    # Data sources
    dot.node('UserInput', 'User Input\n(Registration/Login)')
    dot.node('YouTubeHTML', 'YouTube History\n(watch-history.html)')
    dot.node('ChatCSV', 'Chat History\n(chat_history.csv)')
    dot.node('UserQuery', 'User Query\n(Chat Interface)')

    # Processing components
    dot.node('FlaskRoutes', 'Flask Routes\n(/register, /login, /api/...)')
    dot.node('YouTubeParser', 'YouTube Parser\n(parse_youtube_history)')
    dot.node('TranscriptExtractor', 'Transcript Extractor\n(FreeTranscriptExtractor)')
    dot.node('ChatProcessor', 'Chat Processor\n(process_chat_data)')
    dot.node('DistortionDetector', 'Distortion Detector\n(ModelProcessor)')
    dot.node('LLMProcessor', 'LLM Processor\n(Groq/HuggingFace)')
    dot.node('MentalHealthRAG', 'Mental Health RAG\n(MentalHealthLibrary)')

    # Storage
    dot.node('MongoDB', 'MongoDB\n(Users, YouTube, Chats)')
    dot.node('CSVLogs', 'CSV Logs\n(chat_history.csv)')

    # Outputs
    dot.node('AnalysisResults', 'Analysis Results\n(Distortion Reports)')
    dot.node('ChatResponse', 'Chat Response\n(AI Answers)')
    dot.node('UserSession', 'User Session\n(Authenticated)')

    # Data flow edges
    dot.edge('UserInput', 'FlaskRoutes')
    dot.edge('YouTubeHTML', 'YouTubeParser')
    dot.edge('ChatCSV', 'ChatProcessor')
    dot.edge('UserQuery', 'FlaskRoutes')

    dot.edge('FlaskRoutes', 'YouTubeParser', label='platform=youtube')
    dot.edge('FlaskRoutes', 'ChatProcessor', label='platform=safespace')
    dot.edge('FlaskRoutes', 'LLMProcessor', label='chat request')

    dot.edge('YouTubeParser', 'TranscriptExtractor')
    dot.edge('TranscriptExtractor', 'DistortionDetector')
    dot.edge('ChatProcessor', 'DistortionDetector')

    dot.edge('DistortionDetector', 'LLMProcessor')
    dot.edge('LLMProcessor', 'AnalysisResults')

    dot.edge('FlaskRoutes', 'MentalHealthRAG', label='learning query')
    dot.edge('MentalHealthRAG', 'ChatResponse')

    dot.edge('FlaskRoutes', 'UserSession')
    dot.edge('AnalysisResults', 'MongoDB')
    dot.edge('ChatResponse', 'CSVLogs')
    dot.edge('UserSession', 'MongoDB')

    return dot

def main():
    """Generate both class diagram and data flow diagram"""

    print("🎯 Generating AwareMe System Diagrams...")
    print("=" * 50)

    # Generate class diagram
    print("📊 Creating Class Diagram...")
    class_diagram = create_class_diagram()
    class_diagram.render('awareme_class_diagram', format='png', cleanup=True)
    class_diagram.render('awareme_class_diagram', format='svg', cleanup=True)
    print("✅ Class diagram saved as: awareme_class_diagram.png and .svg")

    # Generate data flow diagram
    print("🔄 Creating Data Flow Diagram...")
    data_flow = create_data_flow_diagram()
    data_flow.render('awareme_data_flow', format='png', cleanup=True)
    data_flow.render('awareme_data_flow', format='svg', cleanup=True)
    print("✅ Data flow diagram saved as: awareme_data_flow.png and .svg")

    print("\n" + "=" * 50)
    print("🎉 Diagrams generated successfully!")
    print("\n📁 Files created:")
    print("   - awareme_class_diagram.png/svg (Class relationships)")
    print("   - awareme_data_flow.png/svg (Data flow and processing)")

    print("\n📖 Diagram Contents:")
    print("   Class Diagram: Shows all classes, methods, and relationships")
    print("   Data Flow: Illustrates how data moves through the system")
    print("   Both diagrams are suitable for thesis documentation")

    print("\n🔧 Requirements: pip install graphviz")
    print("   (Also requires system graphviz: apt-get install graphviz)")

if __name__ == "__main__":
    main()