import pandas as pd
from datetime import datetime
from pymongo import MongoClient
from model_processor import regex_distortion_detector, identify_cognitive_distortions_llm

def get_chat_collection():
    client = MongoClient("mongodb://127.0.0.1:27017/")
    db = client["historyDB"]
    return db["personal_chats"]

def process_chat_data(selected_date, csv_path='chat_history.csv'):
    """Refactored to accept selected_date as an argument"""
    distortions = [
        "All-or-Nothing Thinking", "Overgeneralization", "Mental Filtering",
        "Disqualifying the Positive", "Jumping to Conclusions",
        "Catastrophizing", "Emotional Reasoning"
    ]

    data = []
    try:
        # Using pandas read_csv is safer for handling commas in quotes
        df = pd.read_csv(csv_path)
    except Exception as e:
        return {"error": f"CSV Load failed: {str(e)}"}

    # Filter by the date passed from the Flask route
    df['Timestamp_dt'] = pd.to_datetime(df['Timestamp'], errors='coerce')
    day_data = df[df['Timestamp_dt'].dt.strftime('%Y-%m-%d') == selected_date].copy()

    if day_data.empty:
        return {"error": f"No logs found for {selected_date}"}

    processed_entries = []
    for _, row in day_data.iterrows():
        text = str(row['User Input'])
        
        # Run your detection logic
        regex_results = regex_distortion_detector(text, distortions)
        llm_results = identify_cognitive_distortions_llm(text)

        entry_obj = {
            "timestamp": row['Timestamp'],
            "transcript": text,
            "regex_analysis": regex_results,
            "llm_analysis": llm_results,
            "analysis_summary": {
                "transcript_word_count": len(text.split()),
                "source": "personal_chat"
            }
        }
        processed_entries.append(entry_obj)

    final_payload = {
        "daily_summary": {
            "analysis_date": selected_date,
            "total_entries_processed": len(processed_entries),
            "source_type": "chat_history"
        },
        "entries": processed_entries
    }

    # Save to MongoDB
    col = get_chat_collection()
    col.insert_one(final_payload)
    return {"status": "success", "entries_count": len(processed_entries)}