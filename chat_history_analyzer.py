import os
import pandas as pd
from datetime import datetime
from pymongo import MongoClient
from model_processor import (
    improved_full_pipeline, DISTORTIONS,
    clean_overlapping_snippets, update_processing_status
)

MONGO_URI = os.getenv("MONGO_URI")

def get_chat_collection():
    client = MongoClient(MONGO_URI)
    db = client["historyDB"]
    return db["safespace"]

def get_chat_history_collection():
    client = MongoClient(MONGO_URI)
    db = client["historyDB"]
    return db["chat_history"]

def process_chat_data(selected_date):
    """Analyze chat history for a given date using the full detection pipeline."""
    try:
        update_processing_status(
            "processing", "safespace",
            step="Loading chat history", step_number=1, total_steps=5,
            detail="Reading your conversation data",
            progress=5
        )
        col = get_chat_history_collection()
        docs = list(col.find({"Timestamp": {"$regex": f"^{selected_date}"}}))
        if not docs:
            return {"error": f"No logs found for {selected_date}"}
        df = pd.DataFrame(docs)
    except Exception as e:
        return {"error": f"Failed to load chat history: {str(e)}"}

    update_processing_status(
        "processing", "safespace",
        step="Filtering conversations", step_number=2, total_steps=5,
        detail=f"Finding conversations from {selected_date}",
        progress=15
    )

    day_data = df

    total_batch_words = 0
    total_batch_flagged_words = 0
    category_flagged_counts = {d: 0 for d in DISTORTIONS}
    final_video_list = []
    total_entries = len(day_data)

    for idx_count, (idx, row) in enumerate(day_data.iterrows()):
        text = str(row['User Input'])
        if not text or text.lower() == "nan":
            continue

        update_processing_status(
            "processing", "safespace",
            step="Analyzing conversations", step_number=3, total_steps=5,
            detail=f"Analyzing message {idx_count+1} of {total_entries}",
            progress=int(25 + (idx_count / max(total_entries, 1)) * 55)
        )

        transcript_words = text.split()
        transcript_word_count = len(transcript_words)
        total_batch_words += transcript_word_count

        # Run full enhanced pipeline
        pipeline_result, pipeline_info = improved_full_pipeline(text)

        if 'skipped' in pipeline_info:
            final_video_list.append({
                "video_title": f"Chat {idx_count+1}",
                "timestamp": row.get('Timestamp'),
                "transcript": text,
                "distortion_analysis": {d: [] for d in DISTORTIONS},
                "pipeline_info": pipeline_info,
                "analysis_summary": {
                    "transcript_word_count": transcript_word_count,
                    "distortion_word_count": 0,
                    "distortion_percentage": 0
                }
            })
            continue

        # Boolean masking for word-level distortion percentage
        video_mask = [False] * transcript_word_count
        category_masks = {d: [False] * transcript_word_count for d in DISTORTIONS}

        for d in DISTORTIONS:
            cleaned_snippets = clean_overlapping_snippets(pipeline_result[d])
            pipeline_result[d] = cleaned_snippets
            for snippet in cleaned_snippets:
                s_words = snippet.split()
                n = len(s_words)
                for i in range(transcript_word_count - n + 1):
                    if transcript_words[i : i + n] == s_words:
                        for j in range(i, i + n):
                            video_mask[j] = True
                            category_masks[d][j] = True

        video_flagged_count = sum(video_mask)
        total_batch_flagged_words += video_flagged_count
        for d in DISTORTIONS:
            category_flagged_counts[d] += sum(category_masks[d])

        final_video_list.append({
            "video_title": f"Chat {idx_count+1}",
            "timestamp": row.get('Timestamp'),
            "transcript": text,
            "distortion_analysis": pipeline_result,
            "pipeline_info": pipeline_info,
            "analysis_summary": {
                "transcript_word_count": transcript_word_count,
                "distortion_word_count": video_flagged_count,
                "distortion_percentage": round(
                    (video_flagged_count / transcript_word_count) * 100, 2
                ) if transcript_word_count > 0 else 0
            }
        })

    daily_summary = {
        "analysis_date": selected_date,
        "total_videos_processed": len(final_video_list),
        "batch_total_words": total_batch_words,
        "batch_overall_distortion_percentage": round(
            (total_batch_flagged_words / total_batch_words) * 100, 2
        ) if total_batch_words > 0 else 0,
        "distortion_category_breakdown": {
            d: round((category_flagged_counts[d] / total_batch_words) * 100, 2)
            if total_batch_words > 0 else 0
            for d in DISTORTIONS
        },
        "source_type": "chat_history"
    }

    final_payload = {
        "daily_summary": daily_summary,
        "videos": final_video_list
    }

    # Save to MongoDB
    try:
        update_processing_status(
            "processing", "safespace",
            step="Saving results", step_number=5, total_steps=5,
            detail="Writing analysis to database",
            progress=95
        )
        col = get_chat_collection()
        col.insert_one(final_payload)
        update_processing_status("completed", "safespace")
        print(f"💾 Saved SafeSpace analysis to MongoDB (safespace).")
    except Exception as e:
        print(f"⚠️ DB Insert failed: {e}")
        update_processing_status("error", "safespace")

    return {"status": "success", "entries_count": len(final_video_list)}