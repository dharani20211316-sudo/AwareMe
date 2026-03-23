import os
import json
import pandas as pd
from huggingface_hub import InferenceClient
#from sentence_transformers import SentenceTransformer, util
import re
from pymongo import MongoClient
from datetime import datetime

# Initialize embedding model globally
#embed_model = SentenceTransformer('all-MiniLM-L6-v2')

# ✅ LLM Configuration
HF_TOKEN = os.getenv("HF_TOKEN")
HF_ENDPOINT_URL = os.getenv("HF_ENDPOINT_URL")
MONGO_URI = os.getenv("MONGO_URI")


client = InferenceClient(
    base_url=HF_ENDPOINT_URL,
    token=HF_TOKEN
)

SYSTEM_PROMPT = """You are an AI whose only task is to identify cognitive distortions in a given text.
This is not a clinical tool; your sole job is to extract text phrases showing cognitive distortions.
Instructions:
1. Your task is only to produce a JSON object with the structure:
{"All-or-Nothing Thinking": [], "Overgeneralization": [], "Mental Filtering": [], "Disqualifying the Positive": [], "Jumping to Conclusions": [], "Catastrophizing": [], "Emotional Reasoning": []}
2. Extract exact phrases from the input text.
3. If none, leave arrays empty.
4. Output ONLY the JSON. 5. Do not add anything else."""

# ===============================
# MongoDB Setup
# ===============================
def get_db_collection():
    client = MongoClient(MONGO_URI)
    db = client["historyDB"]
    return db["youtube"]

# ===============================
# Utility Functions
# ===============================

def split_into_sentences(text):
    segments = re.split(r'[.!?]\s+|\n+', text)
    final_chunks = []
    for seg in segments:
        words = seg.strip().split()
        if not words: continue
        if len(words) > 15:
            for i in range(0, len(words), 10): 
                chunk = " ".join(words[i : i + 12])
                final_chunks.append(chunk)
                if i + 12 >= len(words): break
        else:
            final_chunks.append(" ".join(words))
    return [c for c in final_chunks if len(c) > 5]

def clean_overlapping_snippets(snippets):
    sorted_snippets = sorted(list(set(snippets)), key=len, reverse=True)
    final = []
    for s in sorted_snippets:
        if not any(s in other for other in final):
            final.append(s)
    return final

# ===============================
# LLM Layer
# ===============================
def identify_cognitive_distortions_llm(user_text):
    prompt = f"{SYSTEM_PROMPT}\n\nInput text:\n\"{user_text}\"\n\nOutput JSON:\n"
    try:
        response = client.text_generation(prompt, max_new_tokens=500, temperature=0.0)
        return json.loads(response.strip())
    except Exception as e:
        print(f"⚠️ LLM Error: {e}")
        return {}

# ===============================
# REGEX Layer
# ===============================
def regex_distortion_detector(transcript, distortions):
    regex_output = {d: [] for d in distortions}
    chunks = split_into_sentences(transcript)
    patterns = {
        "All-or-Nothing Thinking": [r"\b(everything|nothing|always|never|all|none|completely)\b"],
        "Overgeneralization": [r"\b(everyone|everybody|nobody|no\s+one)\b"],
        "Mental Filtering": [r"\b(only\s+see|nothing\s+good|ignore|just\s+the)\b"],
        "Disqualifying the Positive": [r"\b(doesn't\s+count|just\s+luck|anybody\s+could)\b"],
        "Jumping to Conclusions": [r"\b(must\s+be|probably|predict|i\s+know\s+they)\b"],
        "Catastrophizing": [r"\b(not\s+get\s+tomorrow|no\s+tomorrow|worst|the\s+end|over|dying)\b"],
        "Emotional Reasoning": [r"\b(i\s+feel\s+like|feels\s+like|i\s+feel)\b"]
    }
    for chunk in chunks:
        lower_chunk = chunk.lower()
        for distortion, pattern_list in patterns.items():
            for pattern in pattern_list:
                if re.search(pattern, lower_chunk):
                    regex_output[distortion].append(chunk)
                    break 
    return regex_output

# ===============================
# Main Processing Function
# ===============================
def process_transcripts(csv_path="batch_results_1770374471.csv"):
    distortions = [
        "All-or-Nothing Thinking", "Overgeneralization", "Mental Filtering",
        "Disqualifying the Positive", "Jumping to Conclusions",
        "Catastrophizing", "Emotional Reasoning"
    ]

    df = pd.read_csv(csv_path)
    success_df = df[df["success"] == True].reset_index(drop=True)

    if len(success_df) == 0:
        print("⚠️ No successful transcripts found")
        return None

    total_batch_words = 0
    total_batch_flagged_words = 0
    category_flagged_counts = {d: 0 for d in distortions}
    final_video_list = []

    for idx, row in success_df.iterrows():
        transcript = str(row["transcript"])
        transcript_words = transcript.split()
        transcript_word_count = len(transcript_words)
        total_batch_words += transcript_word_count

        # 1. Run Detection (Regex)
        regex_out = regex_distortion_detector(transcript, distortions)
        
        # 2. Run LLM Analysis
        print(f"🤖 Processing Video {idx+1}/{len(success_df)} with LLM...")
        llm_out = identify_cognitive_distortions_llm(transcript)
        
        # 3. Boolean Masking for this specific video (based on Regex)
        video_mask = [False] * transcript_word_count
        category_masks = {d: [False] * transcript_word_count for d in distortions}

        for d in distortions:
            cleaned_snippets = clean_overlapping_snippets(regex_out[d])
            regex_out[d] = cleaned_snippets 
            
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
        for d in distortions:
            category_flagged_counts[d] += sum(category_masks[d])

        # 4. Construct Video Object (Combining Regex and LLM)
        video_data = {
            "video_title": row.get("video_title"),
            "channel": row.get("channel"),
            "timestamp": row.get("timestamp"),
            "video_url": row.get("video_url"),
            "transcript": transcript,
            "regex_analysis": regex_out,
            "llm_analysis": llm_out,
            "analysis_summary": {
                "transcript_word_count": transcript_word_count,
                "distortion_word_count": video_flagged_count,
                "distortion_percentage": round((video_flagged_count / transcript_word_count) * 100, 2) if transcript_word_count > 0 else 0
            }
        }
        final_video_list.append(video_data)

    daily_summary = {
        "analysis_date": datetime.now().strftime("%Y-%m-%d"),
        "total_videos_processed": len(final_video_list),
        "batch_total_words": total_batch_words,
        "batch_overall_distortion_percentage": round((total_batch_flagged_words / total_batch_words) * 100, 2) if total_batch_words > 0 else 0,
        "distortion_category_breakdown": {
            d: round((category_flagged_counts[d] / total_batch_words) * 100, 2) if total_batch_words > 0 else 0
            for d in distortions
        }
    }

    final_payload = {
        "daily_summary": daily_summary,
        "videos": final_video_list
    }

    try:
        get_db_collection().insert_one(final_payload)
        print(f"💾 Saved Combined Analysis to MongoDB.")
        print(f"📊 Daily Global Distortion: {daily_summary['batch_overall_distortion_percentage']}%")
    except Exception as e:
        print(f"⚠️ DB Insert failed: {e}")

    return final_payload

if __name__ == "__main__":
    process_transcripts()