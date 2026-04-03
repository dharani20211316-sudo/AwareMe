import os
import json
import csv as csv_module
import pandas as pd
from huggingface_hub import InferenceClient
import re
from pymongo import MongoClient
from datetime import datetime
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from langdetect import detect, LangDetectException

# =====================================================================
# CONFIG
# =====================================================================
HF_TOKEN = os.getenv("HF_TOKEN")
HF_ENDPOINT_URL = os.getenv("HF_ENDPOINT_URL")
MONGO_URI = os.getenv("MONGO_URI")
LLM_AVAILABLE = bool(HF_TOKEN and HF_ENDPOINT_URL)

client = None
if LLM_AVAILABLE:
    client = InferenceClient(
        base_url=HF_ENDPOINT_URL,
        token=HF_TOKEN
    )

DISTORTIONS = [
    "All-or-Nothing Thinking",
    "Overgeneralization",
    "Mental Filtering",
    "Disqualifying the Positive",
    "Jumping to Conclusions",
    "Catastrophizing",
    "Emotional Reasoning",
]

SYSTEM_PROMPT = """You are a cognitive distortion detector. Analyze the text and extract ONLY phrases that clearly demonstrate a cognitive distortion.

## DISTORTION DEFINITIONS (use these strictly):

1. **All-or-Nothing Thinking**: Seeing things in absolute black-or-white categories with NO middle ground. The person frames outcomes as total success or total failure.
   - YES: "If I don't get 100%, I'm a complete failure"
   - YES: "Either you love me completely or you don't love me at all"
   - NO: "I always enjoy pizza" (preference, not distortion)
   - NO: "Everything tonight" (song lyric / expression, not distortion)

2. **Overgeneralization**: Taking ONE specific event and applying it as a universal rule using words like "always", "never", "everyone", "nobody" to describe a PATTERN from a single incident.
   - YES: "I failed one test, I'll never pass anything"
   - YES: "Nobody ever listens to me" (after one person didn't listen)
   - NO: "Everyone is welcome" (invitation, not distortion)
   - NO: "I always wake up at 7am" (factual habit, not distortion)
   - NO: "Never gonna give you up" (song lyric / expression)

3. **Mental Filtering**: Focusing EXCLUSIVELY on negative details while ignoring all positive aspects of a situation.
   - YES: "I got 9 compliments and 1 criticism — my work is terrible"
   - NO: "I only see beauty in nature" (positive filtering)

4. **Disqualifying the Positive**: Actively rejecting or dismissing positive experiences by insisting they "don't count."
   - YES: "They only said that to be nice, they don't really mean it"
   - YES: "That success was just luck, not my skill"
   - NO: "Anyone could do that" (may be factual modesty)

5. **Jumping to Conclusions**: Making negative interpretations WITHOUT supporting evidence. Includes mind-reading ("they must hate me") and fortune-telling ("this will definitely go wrong").
   - YES: "She didn't text back — she must be angry at me"
   - YES: "I know this interview will be a disaster"
   - NO: "It will probably rain" (weather prediction based on evidence)

6. **Catastrophizing**: Imagining the absolute WORST possible outcome and treating it as inevitable. Blowing things way out of proportion.
   - YES: "If I make one mistake, my entire career is over"
   - YES: "This headache must be a brain tumor"
   - NO: "That was the worst movie I've seen" (opinion, not catastrophizing)

7. **Emotional Reasoning**: Believing something must be true BECAUSE of how you feel, using emotions as evidence for facts.
   - YES: "I feel stupid, therefore I am stupid"
   - YES: "I feel like a burden, so I must be one"
   - NO: "I feel tired today" (describing a state, not reasoning from it)
   - NO: "I feel like eating pizza" (desire, not distortion)

## CRITICAL RULES:
- Extract ONLY the exact phrase from the text. Do not paraphrase.
- A phrase must show DISTORTED THINKING by a person, not just contain trigger words.
- Song lyrics, hashtags, product descriptions, and casual expressions are NOT distortions unless they express genuine distorted beliefs.
- "always", "never", "everyone", "nobody" in normal conversational context (habits, invitations, expressions) are NOT distortions.
- If the text has NO distortions, ALL arrays MUST be empty. Empty results are correct and expected for most content.
- When uncertain, leave it OUT. Only flag clear, unambiguous distortions.
- Do NOT add "Personalization" or any category not listed below.

## OUTPUT FORMAT:
Return ONLY this JSON structure, nothing else:
{"All-or-Nothing Thinking": [], "Overgeneralization": [], "Mental Filtering": [], "Disqualifying the Positive": [], "Jumping to Conclusions": [], "Catastrophizing": [], "Emotional Reasoning": []}"""

# ===============================
# MongoDB Setup
# ===============================
def get_db_collection(platform="youtube"):
    client = MongoClient(MONGO_URI)
    db = client["historyDB"]
    return db[platform]

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
# LLM Layer (with validation)
# ===============================
_llm_failures = 0  # Track consecutive failures to avoid spamming a paused endpoint
_LLM_MAX_FAILURES = 2  # Stop trying after this many consecutive failures

def call_llm(user_text):
    """Call LLM and parse JSON response. Returns empty dict if LLM not available or endpoint is down."""
    global _llm_failures
    if not LLM_AVAILABLE or client is None:
        return {}
    if _llm_failures >= _LLM_MAX_FAILURES:
        return {}
    full_prompt = f"{SYSTEM_PROMPT}\n\nInput text:\n\"{user_text}\"\n\nOutput JSON:\n"
    try:
        response = client.text_generation(full_prompt, max_new_tokens=600, temperature=0.0)
        _llm_failures = 0  # Reset on success
        raw = response.strip()
        json_match = re.search(r'\{.*\}', raw, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        return json.loads(raw)
    except Exception as e:
        _llm_failures += 1
        if _llm_failures <= _LLM_MAX_FAILURES:
            print(f"⚠️ LLM Error: {e}")
        if _llm_failures == _LLM_MAX_FAILURES:
            print("⚠️ LLM endpoint appears down — skipping LLM for remaining items")
        return {}


def validate_llm_output(llm_result, original_text):
    """
    Post-process LLM output to remove hallucinated phrases,
    unknown categories, and short fragments.
    """
    validated = {d: [] for d in DISTORTIONS}
    original_lower = original_text.lower()

    IGNORE_CATEGORIES = {"Personalization", "Labeling", "Should Statements",
                         "Magnification", "Minimization", "Blaming"}

    for category, phrases in llm_result.items():
        if category not in validated:
            continue
        if not isinstance(phrases, list):
            continue
        for phrase in phrases:
            if not isinstance(phrase, str):
                continue
            phrase = phrase.strip()
            if len(phrase.split()) < 3:
                continue
            if phrase.startswith('#') or all(w.startswith('#') for w in phrase.split()):
                continue
            phrase_lower = phrase.lower().strip()
            if phrase_lower not in original_lower:
                phrase_words = set(phrase_lower.split())
                text_words = set(original_lower.split())
                overlap = len(phrase_words & text_words) / len(phrase_words) if phrase_words else 0
                if overlap < 0.7:
                    continue
            validated[category].append(phrase)
    return validated


# Backward-compatible alias
def identify_cognitive_distortions_llm(user_text):
    raw = call_llm(user_text)
    return validate_llm_output(raw, user_text) if raw else {}

# ===============================
# Improved REGEX Layer
# ===============================
def improved_regex_detector(text):
    """
    Stricter regex patterns that look for distortion-indicating CONTEXTS,
    not just trigger words in isolation.
    """
    result = {d: [] for d in DISTORTIONS}
    chunks = split_into_sentences(text)

    patterns = {
        "All-or-Nothing Thinking": [
            r"\b(complete(?:ly)?\s+(?:failure|disaster|waste|useless))",
            r"\b(either\s+.{3,30}\s+or\s+(?:not|nothing|never))\b",
            r"\b((?:totally|completely|absolutely)\s+(?:ruined|worthless|hopeless|useless|awful))",
            r"\b(100%|zero\s+(?:chance|hope))\b",
            r"\b((?:the\s+)?(?:whole|entire)\s+(?:day|week|life|thing|career|year)\s+is\s+(?:ruined|wasted|over|destroyed))",
            r"\b(i\s+(?:am|'m)\s+(?:completely|totally|absolutely)\s+(?:useless|worthless|hopeless|stupid))",
            r"\b((?:don'?t|doesn'?t|never)\s+belong)",
            r"\b((?:won'?t|can'?t)\s+(?:be\s+able\s+to\s+)?(?:do\s+anything|focus\s+on\s+anything|get\s+anything))",
        ],
        "Overgeneralization": [
            r"\b(i\s+(?:always|never)\s+(?:fail|mess|screw|ruin|lose|forget|get))",
            r"\b((?:no\s*one|nobody)\s+(?:ever\s+)?(?:loves?|likes?|cares?|listens?|wants?))",
            r"\b((?:everyone|everybody)\s+(?:hates?|leaves?|thinks?\s+i'm?|judges?|is\s+(?:smarter|better|faster|more)))",
            r"\b((?:nothing)\s+(?:ever|good)\s+(?:works?|happens?|goes?))",
            r"\b(i\s+(?:always|never)\s+(?:end\s+up|wind\s+up|make|do\s+(?:things?|it)))",
            r"\b(nobody\s+(?:ever\s+)?(?:will|would|wants?\s+to))",
        ],
        "Mental Filtering": [
            r"\b(only\s+(?:bad|negative|wrong|terrible)\s+things?)\b",
            r"\b(nothing\s+(?:good|right|positive)\s+(?:ever\s+)?(?:happens?))",
            r"\b(can't\s+see\s+any(?:thing)?\s+(?:good|positive))",
            r"\b(only\s+(?:think|focus|see|remember)\s+(?:about\s+)?(?:the\s+)?(?:bad|negative|wrong))",
        ],
        "Disqualifying the Positive": [
            r"\b((?:just|only)\s+(?:luck|being\s+nice|saying\s+that|pity))\b",
            r"\b(doesn'?t\s+(?:really\s+)?(?:count|matter|mean\s+anything))",
            r"\b((?:anyone|anybody)\s+could\s+(?:have\s+)?(?:done?|do)\s+that)",
            r"\b(they\s+(?:were|are)\s+just\s+(?:being\s+)?(?:nice|polite|kind))",
        ],
        "Jumping to Conclusions": [
            r"\b((?:they|she|he)\s+(?:must|probably)\s+(?:think|hate|be\s+(?:angry|mad|upset)))",
            r"\b(i\s+(?:just\s+)?know\s+(?:it|this|they|i)\s+will\s+(?:fail|go\s+wrong))",
            r"\b((?:this|it)\s+(?:will|is\s+going\s+to)\s+(?:be\s+)?(?:a\s+)?(?:disaster|terrible|awful))",
            r"\b((?:maybe|probably|must\s+be)\s+(?:ignoring|avoiding|hating|angry\s+at|mad\s+at)\s+me)",
            r"\b((?:i\s+)?(?:said|did)\s+something\s+wrong)",
            r"\b((?:she|he|they)\s+(?:is|are)\s+(?:ignoring|avoiding|annoyed\s+with|upset\s+with)\s+me)",
            r"\b((?:doesn'?t|don'?t)\s+want\s+to\s+(?:talk|be|hang)\s+(?:to|with)\s+me)",
        ],
        "Catastrophizing": [
            r"\b((?:my|the)\s+(?:whole\s+)?(?:life|career|future|world)\s+is\s+(?:over|ruined|destroyed))",
            r"\b((?:worst|end\s+of\s+the\s+world|everything\s+is\s+(?:falling|over)))",
            r"\b((?:can'?t|won'?t)\s+(?:ever\s+)?(?:recover|survive|get\s+through))",
            r"\b((?:i\s+)?(?:might|will)\s+(?:never|not)\s+(?:get|find|have|make\s+it|succeed))",
            r"\b((?:chose|choosing)\s+the\s+wrong\s+(?:field|path|career|major|job))",
        ],
        "Emotional Reasoning": [
            r"\b(i\s+feel\s+(?:like\s+)?(?:a\s+)?(?:failure|burden|worthless|stupid|ugly|loser|fraud))",
            r"\b(i\s+feel\s+(?:so\s+)?(?:dumb|hopeless|helpless|pathetic))",
            r"\b((?:feel(?:s)?)\s+(?:like\s+)?(?:everything|nothing|no\s*one))",
            r"\b(i\s+(?:am|'m)\s+(?:so\s+)?(?:stupid|dumb|useless|worthless|pathetic|a\s+failure))",
            r"\b(i\s+feel\s+like\s+i\s+(?:am|'m|don'?t|can'?t|shouldn'?t))",
        ],
    }

    for chunk in chunks:
        lower = chunk.lower().strip()
        for distortion, pats in patterns.items():
            for pat in pats:
                if re.search(pat, lower):
                    result[distortion].append(chunk.strip())
                    break
    return result


# Backward-compatible alias
def regex_distortion_detector(transcript, distortions):
    return improved_regex_detector(transcript)

# ===============================
# LAYER 1: Sentiment Pre-filter
# ===============================
_vader = SentimentIntensityAnalyzer()

def sentiment_score(text):
    return _vader.polarity_scores(text)['compound']

def sentiment_gate(text):
    score = sentiment_score(text)
    if score < -0.3:
        return 1.0, score
    elif score < 0.1:
        return 0.85, score
    else:
        return 0.6, score

# ===============================
# LAYER 2: Language Detection
# ===============================
def is_english(text):
    clean = re.sub(r'[#@]\w+', '', text)
    clean = re.sub(r'[^\w\s.,!?\'-]', '', clean).strip()
    if len(clean.split()) < 4:
        return bool(re.search(r'[a-zA-Z]{3,}', clean))
    try:
        return detect(clean) == 'en'
    except LangDetectException:
        return False

# ===============================
# LAYER 3: First-Person Pronoun Gate
# ===============================
FIRST_PERSON = re.compile(
    r"\b(i|i'm|i've|i'll|i'd|me|my|mine|myself|we|we're|we've|our|ours|ourselves)\b",
    re.IGNORECASE
)

def first_person_ratio(text):
    words = text.split()
    if not words:
        return 0.0
    fp_count = sum(1 for w in words if FIRST_PERSON.match(w))
    return fp_count / len(words)

def first_person_gate(text):
    ratio = first_person_ratio(text)
    if ratio > 0.02:
        return 1.0, ratio
    else:
        return 0.5, ratio

# ===============================
# LAYER 4: Content-Type Classifier
# ===============================
def classify_content_type(text):
    lower = text.lower()
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    meaningful_lines = [l for l in lines if len(l) > 3 and not l.startswith('#')
                        and not all(c in '.·•-—_~' for c in l.replace(' ', ''))]
    if len(meaningful_lines) >= 3:
        unique_lines = set(l.lower() for l in meaningful_lines)
        if len(unique_lines) < len(meaningful_lines) * 0.7:
            return 'song_lyrics', True

    song_signals = [r'\b(verse|chorus|bridge|feat\.?|ft\.?|prod\.?|remix|lyrics)\b',
                    r'\b(la\s+la|na\s+na|oh\s+oh|yeah\s+yeah)\b']
    if sum(1 for p in song_signals if re.search(p, lower)) >= 1:
        return 'song_lyrics', True

    ad_signals = [r'[\$£€]\d+', r'\b(discount|sale|off|buy|shop|order|promo|coupon)\b',
                  r'\b(delivery|shipping|subscribe|unsubscribe)\b',
                  r'\b(www\.|\.com|\.lk|\.io)\b']
    if sum(1 for p in ad_signals if re.search(p, lower)) >= 2:
        return 'ad/product', True

    news_signals = [r'\b(according\s+to|reported|announced|released|launched|designed)\b',
                    r'\b(company|corporation|organization|government|officials?)\b',
                    r'\b(users?|customers?|consumers?|employees?)\b']
    if sum(1 for p in news_signals if re.search(p, lower)) >= 2 and first_person_ratio(text) < 0.01:
        return 'news', True

    if first_person_ratio(text) > 0.03:
        return 'personal', False
    return 'other', False

# ===============================
# LAYER 5: Confidence Scoring
# ===============================
CONFIDENCE_THRESHOLD = 0.4
CONFIDENCE_THRESHOLD_NO_LLM = 0.3

def compute_confidence(text, regex_result, llm_result, category):
    signals = 0
    max_signals = 5

    if regex_result.get(category):
        signals += 1
    if llm_result.get(category):
        signals += 1
    elif not LLM_AVAILABLE:
        max_signals -= 1
    if sentiment_score(text) < -0.05:
        signals += 1
    if first_person_ratio(text) > 0.02:
        signals += 1
    all_phrases = (regex_result.get(category, []) or []) + (llm_result.get(category, []) or [])
    if any(len(p.split()) >= 5 for p in all_phrases):
        signals += 1
    return signals / max_signals if max_signals > 0 else 0

# ===============================
# FULL PIPELINE: All layers combined
# ===============================
def full_pipeline(text, skip_content_gate=False):
    """
    Run the complete enhanced detection pipeline:
    1. Language gate
    2. Content-type classifier
    3. Minimum text length
    4. Sentiment pre-filter
    5. First-person gate
    6. Improved regex detection
    7. LLM detection + validation
    8. Confidence-based merge

    skip_content_gate: If True, skip the content-type classifier (used when
    individual posts were already pre-filtered before aggregation).
    """
    pipeline_info = {}

    # Gate 1: Language
    eng = is_english(text)
    pipeline_info['is_english'] = eng
    if not eng:
        pipeline_info['skipped'] = 'non-English text'
        return {d: [] for d in DISTORTIONS}, pipeline_info

    # Gate 2: Content type
    if not skip_content_gate:
        content_type, should_skip = classify_content_type(text)
        pipeline_info['content_type'] = content_type
        if should_skip:
            pipeline_info['skipped'] = f'content type: {content_type}'
            return {d: [] for d in DISTORTIONS}, pipeline_info
    else:
        pipeline_info['content_type'] = 'pre-filtered'

    # Gate 3: Minimum text length
    word_count = len(text.split())
    pipeline_info['word_count'] = word_count
    if word_count < 6:
        pipeline_info['skipped'] = 'text too short (<6 words)'
        return {d: [] for d in DISTORTIONS}, pipeline_info

    # Sentiment scoring
    sent_multiplier, sent_score = sentiment_gate(text)
    pipeline_info['sentiment'] = round(sent_score, 3)

    # First-person scoring
    fp_multiplier, fp_ratio = first_person_gate(text)
    pipeline_info['first_person_ratio'] = round(fp_ratio, 3)

    # Detection: Regex
    regex_out = improved_regex_detector(text)

    # Detection: LLM (skipped if not available)
    llm_raw = call_llm(text)
    llm_validated = validate_llm_output(llm_raw, text) if llm_raw else {}
    pipeline_info['llm_available'] = LLM_AVAILABLE

    # Merge with confidence
    final = {d: [] for d in DISTORTIONS}
    threshold = CONFIDENCE_THRESHOLD if LLM_AVAILABLE else CONFIDENCE_THRESHOLD_NO_LLM

    for d in DISTORTIONS:
        base_confidence = compute_confidence(text, regex_out, llm_validated, d)
        adjusted_confidence = base_confidence * sent_multiplier * fp_multiplier

        regex_phrases = set(regex_out.get(d, []))
        llm_phrases = set(llm_validated.get(d, []))
        all_phrases = regex_phrases | llm_phrases

        if all_phrases and adjusted_confidence >= threshold:
            if regex_phrases and llm_phrases:
                final[d] = list(all_phrases)
            elif regex_phrases:
                final[d] = list(regex_phrases)
            elif LLM_AVAILABLE:
                final[d] = list(llm_phrases)

    # Deduplicate
    for d in DISTORTIONS:
        final[d] = list(dict.fromkeys(final[d]))

    pipeline_info['confidence'] = {
        d: round(compute_confidence(text, regex_out, llm_validated, d) * sent_multiplier * fp_multiplier, 2)
        for d in DISTORTIONS if final[d]
    }
    return final, pipeline_info

# ===============================
# CSV Reading Helper
# ===============================
def _read_csv_safe(csv_path):
    try:
        df = pd.read_csv(csv_path, engine='python', encoding='utf-8')
        return df
    except Exception:
        pass
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv_module.reader(f)
            rows = list(reader)
        if len(rows) < 2:
            return pd.DataFrame()
        header = rows[0]
        data = rows[1:]
        cleaned = []
        for row in data:
            if len(row) >= len(header):
                cleaned.append(row[:len(header)])
            else:
                cleaned.append(row + [''] * (len(header) - len(row)))
        return pd.DataFrame(cleaned, columns=header)
    except Exception as e:
        print(f"  ERROR: Failed to read CSV: {e}")
        return None

# ===============================
# Status Tracking
# ===============================
def update_processing_status(status, platform="youtube"):
    client = MongoClient(MONGO_URI)
    db = client["historyDB"]
    # Update a specific document to track the state
    db["status_tracker"].update_one(
        {"_id": f"{platform}_analysis_task"},
        {"$set": {
            "status": status, 
            "last_updated": datetime.now()
        }},
        upsert=True
    )

# ===============================
# Content Trend Analysis (Instagram / short-text sources)
# ===============================
def analyze_content_trends(df, text_col, title_col, ts_col):
    """
    Analyze content consumption trends from Instagram-style data.
    Returns meaningful patterns even when no cognitive distortions are found.
    Looks at: interaction types, content themes, sentiment distribution,
    and generates human-readable observations.
    """
    trends = {}

    # --- 1. Interaction types (parsed from [type] in video_title) ---
    if title_col:
        interaction_types = {}
        for _, row in df.iterrows():
            title = str(row.get(title_col, ""))
            match = re.match(r'\[(\w+(?:_\w+)*)\]', title)
            if match:
                itype = match.group(1).replace('_', ' ')
                interaction_types[itype] = interaction_types.get(itype, 0) + 1
        if interaction_types:
            trends['interaction_types'] = dict(sorted(
                interaction_types.items(), key=lambda x: x[1], reverse=True))

    # --- 2. Content themes via keyword matching ---
    theme_keywords = {
        'Food & Dining': ['food', 'restaurant', 'eat', 'cook', 'recipe', 'meal',
                          'pizza', 'ice cream', 'icecream', 'taste', 'flavor',
                          'delicious', 'yummy', 'dessert', 'cafe', 'foodie'],
        'Wellness & Mental Health': ['heal', 'therapy', 'therapist', 'anxiety',
                                     'attachment', 'mental', 'stress', 'mindful',
                                     'meditat', 'self-care', 'wellness', 'calm',
                                     'emotion', 'brain', 'relax'],
        'Technology & Innovation': ['robot', 'ai ', 'tech', 'app', 'software',
                                    'gadget', 'digital', 'innovation', 'automat'],
        'Relationships & Social': ['love', 'relationship', 'partner', 'dating',
                                   'support', 'connection', 'attach', 'trust',
                                   'comfort', 'softness', 'gentle'],
        'Beauty & Fashion': ['hair', 'beauty', 'style', 'fashion', 'makeup',
                             'skincare', 'color', 'stylist'],
        'Nature & Plants': ['nature', 'plant', 'flower', 'garden', 'outdoor',
                            'lavender', 'bloom', 'green'],
        'Shopping & Products': ['buy', 'shop', 'order', 'product', 'price',
                                'available', 'delivery', 'cod ', 'branch'],
        'Entertainment & Media': ['movie', 'film', 'series', 'show', 'music',
                                  'song', 'game', 'reel', 'clip'],
        'Self-Improvement': ['growth', 'mindset', 'confidence', 'strength',
                             'intelligence', 'aware', 'learn', 'improve',
                             'independent', 'respect', 'honor'],
    }

    theme_counts = {}
    for _, row in df.iterrows():
        text = str(row.get(text_col, "")).lower()
        for theme, keywords in theme_keywords.items():
            if any(kw in text for kw in keywords):
                theme_counts[theme] = theme_counts.get(theme, 0) + 1

    if theme_counts:
        trends['content_themes'] = dict(sorted(
            theme_counts.items(), key=lambda x: x[1], reverse=True))

    # --- 3. Sentiment distribution ---
    sentiments = {'positive': 0, 'neutral': 0, 'negative': 0}
    sentiment_scores = []
    for _, row in df.iterrows():
        text = str(row.get(text_col, ""))
        if text and text.lower() != 'nan' and len(text.strip()) > 3:
            score = sentiment_score(text)
            sentiment_scores.append(score)
            if score >= 0.05:
                sentiments['positive'] += 1
            elif score <= -0.05:
                sentiments['negative'] += 1
            else:
                sentiments['neutral'] += 1

    trends['sentiment_distribution'] = sentiments
    if sentiment_scores:
        trends['avg_sentiment'] = round(
            sum(sentiment_scores) / len(sentiment_scores), 3)

    # --- 4. Time-of-day patterns ---
    if ts_col:
        try:
            hours = pd.to_datetime(df[ts_col], errors='coerce').dt.hour.dropna()
            if len(hours) > 0:
                hour_bins = {'morning (6-12)': 0, 'afternoon (12-18)': 0,
                             'evening (18-24)': 0, 'night (0-6)': 0}
                for h in hours:
                    if 6 <= h < 12:
                        hour_bins['morning (6-12)'] += 1
                    elif 12 <= h < 18:
                        hour_bins['afternoon (12-18)'] += 1
                    elif 18 <= h < 24:
                        hour_bins['evening (18-24)'] += 1
                    else:
                        hour_bins['night (0-6)'] += 1
                trends['activity_times'] = {k: v for k, v in hour_bins.items() if v > 0}
        except Exception:
            pass

    # --- 5. Generate observations ---
    observations = []

    if trends.get('interaction_types'):
        top_interaction = max(trends['interaction_types'],
                              key=trends['interaction_types'].get)
        count = trends['interaction_types'][top_interaction]
        observations.append(
            f"Most common activity: {top_interaction} ({count} instances)")

    if trends.get('content_themes'):
        top_themes = list(trends['content_themes'].keys())[:3]
        observations.append(f"Top content interests: {', '.join(top_themes)}")

    if sentiments['negative'] > sentiments['positive']:
        observations.append(
            "Content consumption leans negative — may indicate processing "
            "difficult emotions or seeking validation through content")
    elif sentiments['positive'] > max(sentiments['negative'], 1) * 2:
        observations.append(
            "Content consumption is predominantly positive — "
            "healthy and uplifting engagement pattern")
    else:
        observations.append(
            "Mixed sentiment in consumed content — "
            "balanced engagement with diverse perspectives")

    if theme_counts.get('Wellness & Mental Health', 0) >= 1:
        observations.append(
            "Active interest in wellness/mental health content — "
            "shows self-awareness and willingness to grow")

    if theme_counts.get('Relationships & Social', 0) >= 2:
        observations.append(
            "Significant engagement with relationship-related content — "
            "relationships appear to be a key focus area")

    if theme_counts.get('Self-Improvement', 0) >= 1:
        observations.append(
            "Engaging with self-improvement content — "
            "indicates a growth-oriented mindset")

    if trends.get('activity_times'):
        peak_time = max(trends['activity_times'],
                        key=trends['activity_times'].get)
        observations.append(f"Most active during: {peak_time}")

    trends['observations'] = observations
    return trends


# ===============================
# Main Processing Function
# ===============================
def process_transcripts(csv_path="batch_results_1770374471.csv", platform="youtube"):
    df = _read_csv_safe(csv_path)
    if df is None or len(df) == 0:
        print("⚠️ No data found in CSV")
        return None

    # Auto-detect text column
    TEXT_COLS = ['transcript', 'User Input', 'text', 'content', 'message']
    text_col = None
    for col_name in TEXT_COLS:
        if col_name in df.columns:
            text_col = col_name
            break
    if text_col is None:
        print(f"⚠️ No text column found. Columns: {list(df.columns)}")
        return None

    # Auto-detect title column
    TITLE_COLS = ['video_title', 'Mode', 'title', 'channel', 'source']
    title_col = None
    for col_name in TITLE_COLS:
        if col_name in df.columns:
            title_col = col_name
            break

    # Auto-detect timestamp column
    TS_COLS = ['timestamp', 'Timestamp']
    ts_col = None
    for col_name in TS_COLS:
        if col_name in df.columns:
            ts_col = col_name
            break

    # Filter to successful entries if column exists
    if "success" in df.columns:
        df = df[df["success"].astype(str).str.lower() == "true"].reset_index(drop=True)

    if len(df) == 0:
        print("⚠️ No successful transcripts found")
        return None

    # Detect Instagram-like data (has [saved_post], [message], etc. in titles)
    has_interaction_markers = False
    if title_col:
        sample_titles = df[title_col].dropna().astype(str).head(10)
        has_interaction_markers = any(
            re.match(r'\[(\w+(?:_\w+)*)\]', t) for t in sample_titles)

    # Check average word count
    word_counts = df[text_col].dropna().apply(lambda x: len(str(x).split()))
    avg_words = word_counts.mean() if len(word_counts) > 0 else 0
    use_aggregation = (avg_words < 80 and ts_col is not None and len(df) > 1
                       and has_interaction_markers)

    # --- Branch: Aggregated-by-day for Instagram-like short-text sources ---
    if use_aggregation:
        print(f"📱 Instagram-like data detected (avg {avg_words:.0f} words/entry) -> aggregating by day")
        return _process_aggregated(df, text_col, title_col, ts_col, platform)

    # --- Standard per-row analysis (YouTube, chat history, etc.) ---
    print(f"🔍 Standard mode (avg {avg_words:.0f} words/entry) -> per-entry analysis")

    total_batch_words = 0
    total_batch_flagged_words = 0
    category_flagged_counts = {d: 0 for d in DISTORTIONS}
    final_video_list = []

    for idx, row in df.iterrows():
        transcript = str(row[text_col])
        if not transcript or transcript.lower() == "nan":
            continue

        transcript_words = transcript.split()
        transcript_word_count = len(transcript_words)
        total_batch_words += transcript_word_count

        # Run full enhanced pipeline
        print(f"🔍 Processing {idx+1}/{len(df)}...")
        pipeline_result, pipeline_info = full_pipeline(transcript)

        if 'skipped' in pipeline_info:
            print(f"   Skipped ({pipeline_info['skipped']})")
            final_video_list.append({
                "video_title": row.get("video_title"),
                "channel": row.get("channel"),
                "timestamp": row.get("timestamp"),
                "video_url": row.get("video_url"),
                "transcript": transcript,
                "distortion_analysis": {d: [] for d in DISTORTIONS},
                "pipeline_info": pipeline_info,
                "analysis_summary": {
                    "transcript_word_count": transcript_word_count,
                    "distortion_word_count": 0,
                    "distortion_percentage": 0
                }
            })
            continue

        # Boolean Masking based on pipeline result
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

        video_data = {
            "video_title": row.get("video_title"),
            "channel": row.get("channel"),
            "timestamp": row.get("timestamp"),
            "video_url": row.get("video_url"),
            "transcript": transcript,
            "distortion_analysis": pipeline_result,
            "pipeline_info": pipeline_info,
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
            for d in DISTORTIONS
        },
        "llm_available": LLM_AVAILABLE
    }

    final_payload = {
        "daily_summary": daily_summary,
        "videos": final_video_list
    }

    # Add content trends for Instagram-like sources (even in per-row mode)
    if has_interaction_markers and ts_col:
        content_trends = analyze_content_trends(df, text_col, title_col, ts_col)
        final_payload["content_trends"] = content_trends
        print(f"📊 Content trends: {len(content_trends.get('observations', []))} observations")

    try:
        get_db_collection(platform).insert_one(final_payload)
        update_processing_status("completed", platform)
        print(f"💾 Saved Combined Analysis to MongoDB ({platform}).")
        print(f"📊 Daily Global Distortion: {daily_summary['batch_overall_distortion_percentage']}%")
    except Exception as e:
        print(f"⚠️ DB Insert failed: {e}")

    return final_payload


def _process_aggregated(df, text_col, title_col, ts_col, platform):
    """
    Process Instagram-like short-text data by aggregating entries per day.
    Pre-filters individual posts (news/ads/songs) before combining.
    Also computes content trends.
    """
    try:
        df['_date'] = pd.to_datetime(df[ts_col], errors='coerce').dt.date
    except Exception:
        df['_date'] = 'all'

    aggregated_distortions = {d: [] for d in DISTORTIONS}
    total_batch_words = 0
    total_batch_flagged_words = 0
    category_flagged_counts = {d: 0 for d in DISTORTIONS}
    final_video_list = []
    days_processed = 0

    for day, group in df.groupby('_date'):
        # Pre-classify individual posts and filter out non-analyzable ones
        texts = []
        skipped_types = {}
        for _, row in group.iterrows():
            text = str(row.get(text_col, ""))
            if not text or text.lower() == "nan" or len(text.strip()) == 0:
                continue
            text = text.strip()
            content_type, should_skip = classify_content_type(text)
            if should_skip:
                skipped_types[content_type] = skipped_types.get(content_type, 0) + 1
                continue
            texts.append(text)

        if skipped_types:
            for ctype, cnt in skipped_types.items():
                print(f"    -> Filtered out {cnt} {ctype} post(s)")

        if not texts:
            continue

        combined_text = "\n".join(texts)
        word_count = len(combined_text.split())
        total_batch_words += word_count
        print(f"  Day {day}: {len(texts)} entries (after filtering), {word_count} words combined")

        if word_count < 6:
            print(f"    -> Still too short, skipping")
            continue

        result, info = full_pipeline(combined_text, skip_content_gate=True)
        days_processed += 1

        if 'skipped' in info:
            print(f"    -> Skipped ({info['skipped']})")
        else:
            total_found = sum(len(v) for v in result.values())
            if total_found == 0:
                print(f"    -> No distortions")
            else:
                print(f"    -> {total_found} distortion(s) found")

            # Accumulate distortions
            for d in DISTORTIONS:
                aggregated_distortions[d].extend(result[d])
                # Count flagged words for this category
                for phrase in result[d]:
                    phrase_word_count = len(phrase.split())
                    total_batch_flagged_words += phrase_word_count
                    category_flagged_counts[d] += phrase_word_count

        # Store day-level result in video list
        final_video_list.append({
            "video_title": f"Instagram activity - {day}",
            "channel": "aggregated",
            "timestamp": str(day),
            "video_url": "",
            "transcript": combined_text[:500] + "..." if len(combined_text) > 500 else combined_text,
            "distortion_analysis": result,
            "pipeline_info": info,
            "analysis_summary": {
                "transcript_word_count": word_count,
                "distortion_word_count": sum(len(p.split()) for d_list in result.values() for p in d_list),
                "distortion_percentage": round(
                    (sum(len(p.split()) for d_list in result.values() for p in d_list) / word_count) * 100, 2
                ) if word_count > 0 else 0
            }
        })

    # Deduplicate
    for d in DISTORTIONS:
        aggregated_distortions[d] = list(dict.fromkeys(aggregated_distortions[d]))

    print(f"\n  Days analyzed: {days_processed}")

    # Build payload
    daily_summary = {
        "analysis_date": datetime.now().strftime("%Y-%m-%d"),
        "total_videos_processed": len(final_video_list),
        "batch_total_words": total_batch_words,
        "batch_overall_distortion_percentage": round(
            (total_batch_flagged_words / total_batch_words) * 100, 2
        ) if total_batch_words > 0 else 0,
        "distortion_category_breakdown": {
            d: round((category_flagged_counts[d] / total_batch_words) * 100, 2) if total_batch_words > 0 else 0
            for d in DISTORTIONS
        },
        "llm_available": LLM_AVAILABLE
    }

    # Content trends
    content_trends = analyze_content_trends(df, text_col, title_col, ts_col)

    final_payload = {
        "daily_summary": daily_summary,
        "videos": final_video_list,
        "content_trends": content_trends
    }

    try:
        get_db_collection(platform).insert_one(final_payload)
        update_processing_status("completed", platform)
        print(f"💾 Saved Combined Analysis to MongoDB ({platform}).")
        print(f"📊 Daily Global Distortion: {daily_summary['batch_overall_distortion_percentage']}%")
        if content_trends.get('observations'):
            print(f"📊 Content trends: {len(content_trends['observations'])} observations")
    except Exception as e:
        print(f"⚠️ DB Insert failed: {e}")

    return final_payload


if __name__ == "__main__":
    process_transcripts()