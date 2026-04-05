import pandas as pd
import re
from bs4 import BeautifulSoup
from datetime import datetime, date
import os
import time
import tempfile
import zipfile
import glob
from typing import Dict, Any, Optional, List
import instaloader
from model_processor import process_transcripts, update_processing_status


class InstagramContentExtractor:
    """Extracts caption text from Instagram posts using instaloader."""

    def __init__(self):
        self.loader = instaloader.Instaloader(
            download_pictures=False,
            download_videos=False,
            download_video_thumbnails=False,
            download_geotags=False,
            download_comments=False,
            save_metadata=False,
            compress_json=False,
        )

    def extract_caption(self, url: str) -> Optional[str]:
        """Extract caption text from an Instagram post/reel URL."""
        shortcode = self._extract_shortcode(url)
        if not shortcode:
            return None

        try:
            post = instaloader.Post.from_shortcode(self.loader.context, shortcode)
            caption = post.caption
            return caption if caption else ""
        except instaloader.exceptions.QueryReturnedNotFoundException:
            return None
        except instaloader.exceptions.ConnectionException:
            return None
        except Exception:
            return None

    @staticmethod
    def _extract_shortcode(url: str) -> Optional[str]:
        """Extract shortcode from Instagram post/reel URL."""
        match = re.search(r'instagram\.com/(?:p|reel)/([A-Za-z0-9_-]+)', url)
        return match.group(1) if match else None


class ReelTranscriber:
    """
    Downloads audio from Instagram reels via yt-dlp and transcribes
    with Whisper. Only works for reel URLs (instagram.com/reel/...).
    """

    def __init__(self, whisper_model_size="base"):
        self.whisper_model = None
        self._model_size = whisper_model_size

    def _ensure_model(self):
        """Lazy-load Whisper model on first use."""
        if self.whisper_model is None:
            print(f"   Loading Whisper {self._model_size} model...")
            import whisper
            self.whisper_model = whisper.load_model(self._model_size)
            print("   Whisper model loaded.")

    @staticmethod
    def is_reel_url(url: str) -> bool:
        """Check if the URL is an Instagram reel (has audio to transcribe)."""
        return bool(re.search(r'instagram\.com/reel/', url))

    def transcribe(self, url: str) -> Optional[str]:
        """
        Download reel audio and transcribe it.
        Returns the transcript text, or None on failure.
        """
        if not self.is_reel_url(url):
            return None

        self._ensure_model()

        import yt_dlp
        from pydub import AudioSegment

        with tempfile.TemporaryDirectory() as tmpdir:
            ydl_opts = {
                "format": "bestaudio[abr<=96]/bestaudio",
                "outtmpl": os.path.join(tmpdir, "audio.%(ext)s"),
                "quiet": True,
                "no_warnings": True,
                "restrictfilenames": True,
            }

            try:
                clean_url = re.sub(r'(\?|&).*$', '', url)

                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(clean_url, download=True)
                    duration = info.get('duration', 0) if info else 0
                    if duration and duration > 300:
                        print(f"      Skipping transcription (duration {duration}s > 5min)")
                        return None

                audio_file = None
                for f in os.listdir(tmpdir):
                    if f.endswith((".m4a", ".webm", ".mp3", ".ogg", ".opus")):
                        audio_file = os.path.join(tmpdir, f)
                        break

                if not audio_file:
                    return None

                audio = AudioSegment.from_file(audio_file)
                audio = audio.set_channels(1).set_frame_rate(16000)
                wav_path = os.path.join(tmpdir, "audio_whisper.wav")
                audio.export(wav_path, format="wav")

                result = self.whisper_model.transcribe(wav_path)
                text = result.get("text", "").strip()
                return text if text else None

            except Exception as e:
                print(f"      Reel transcription failed: {e}")
                return None


# =====================================================================
# Resolve the Instagram download folder from any uploaded file
# =====================================================================
def _resolve_ig_root(file_path: str) -> str:
    """
    Given any file from the Instagram data download (.zip preferred,
    or start_here.html / liked_posts.html), return the root directory
    that contains 'your_instagram_activity/'.

    For a .zip it extracts into uploads/instagram_data/, then returns
    the extracted root.  For loose files it walks upward or auto-discovers.
    """
    # --- Handle .zip uploads (preferred path) ---
    if file_path.lower().endswith('.zip'):
        print("   📦 ZIP file detected, extracting...")
        extract_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads', 'instagram_data')
        os.makedirs(extract_dir, exist_ok=True)
        print(f"   📂 Extracting to: {extract_dir}")
        with zipfile.ZipFile(file_path, 'r') as zf:
            total_files = len(zf.namelist())
            print(f"   📄 ZIP contains {total_files} files, extracting...")
            zf.extractall(extract_dir)
        print(f"   ✅ Extraction complete")
        for root, dirs, _files in os.walk(extract_dir):
            if 'your_instagram_activity' in dirs:
                print(f"   ✅ Found Instagram data at: {root}")
                return root
        raise ValueError(
            "Could not find 'your_instagram_activity' inside the ZIP. "
            "Make sure you uploaded the correct Instagram data download ZIP."
        )

    # --- Walk upward from the file (works when file is in the actual IG folder) ---
    print(f"   🔍 Checking parent directories of: {file_path}")
    current = os.path.dirname(os.path.abspath(file_path))
    for _ in range(5):
        if os.path.isdir(os.path.join(current, 'your_instagram_activity')):
            return current
        current = os.path.dirname(current)

    # --- Auto-discover: file was uploaded detached via browser ---
    print("   ⚠️ File is detached from original folder (browser upload)")
    print("   🔍 Auto-discovering Instagram download folder...")
    home = os.path.expanduser("~")
    search_dirs = [
        os.path.join(home, "Desktop"),
        os.path.join(home, "Downloads"),
        home,
    ]
    for search_dir in search_dirs:
        if not os.path.isdir(search_dir):
            continue
        print(f"   🔍 Scanning: {search_dir}")
        try:
            for entry in os.scandir(search_dir):
                if entry.is_dir() and entry.name.lower().startswith('instagram-'):
                    candidate = os.path.join(entry.path, 'your_instagram_activity')
                    if os.path.isdir(candidate):
                        print(f"   ✅ Found Instagram folder: {entry.path}")
                        return entry.path
        except PermissionError:
            continue

    raise ValueError(
        "Could not find Instagram data root. "
        "Please upload the Instagram data download as a .zip file."
    )


# =====================================================================
# Parsers for each content type
# =====================================================================

def _parse_timestamp(date_str: str) -> Optional[datetime]:
    """Parse Instagram's timestamp format: 'Mar 29, 2026 8:38 am'"""
    for fmt in ('%b %d, %Y %I:%M %p', '%b %d, %Y %I:%M:%S %p'):
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue
    return None


def _read_html_soup(path: str) -> Optional[BeautifulSoup]:
    """Read an HTML file and return a BeautifulSoup object, or None if missing."""
    if not os.path.exists(path):
        return None
    with open(path, 'r', encoding='utf-8') as f:
        return BeautifulSoup(f.read(), 'html.parser')


def parse_liked_posts(ig_root: str) -> List[Dict]:
    """
    Parse liked_posts.html → list of {post_url, owner_name, username, datetime, source}.
    These require instaloader to fetch actual caption text.
    """
    path = os.path.join(ig_root, 'your_instagram_activity', 'likes', 'liked_posts.html')
    soup = _read_html_soup(path)
    if not soup:
        return []

    entries = []
    for date_div in soup.find_all('div', class_='_3-94 _a6-o'):
        dt = _parse_timestamp(date_div.get_text(strip=True))
        container = date_div.parent
        if not container or not dt:
            continue

        post_url = None
        for a in container.find_all('a', target='_blank'):
            href = a.get('href', '')
            if re.search(r'instagram\.com/(?:p|reel)/', href):
                post_url = href
                break
        if not post_url:
            continue

        owner_name = username = 'Unknown'
        for td in container.find_all('td', class_='_a6_q'):
            label = td.get_text(strip=True)
            val_td = td.find_next_sibling('td', class_='_2piu _a6_r')
            if label == 'Name' and val_td:
                owner_name = val_td.get_text(strip=True)
            elif label == 'Username' and val_td:
                username = val_td.get_text(strip=True)

        entries.append({
            'post_url': post_url,
            'owner_name': owner_name,
            'username': username,
            'datetime': dt,
            'source': 'liked_post',
            'text': None  # to be fetched via instaloader
        })

    print(f"  📌 liked_posts: {len(entries)} entries")
    return entries


def parse_post_comments(ig_root: str) -> List[Dict]:
    """
    Parse post_comments_1.html → user's own comment text.
    Structure per comment:
      <div class="pam _3-95 _2ph- _a6-g uiBoxWhite noborder">
        <table>
          <tr><td colspan="2" class="_2pin _a6_q">Comment<div><div>TEXT</div></div></td></tr>
          <tr><td colspan="2" class="_2pin _a6_q">Media Owner<div><div>USERNAME</div></div></td></tr>
          <tr><td class="_2pin _a6_q">Time</td><td class="_2pin _2piu _a6_r">TIMESTAMP</td></tr>
        </table>
      </div>
    """
    pattern = os.path.join(ig_root, 'your_instagram_activity', 'comments', 'post_comments*.html')
    files = glob.glob(pattern)
    if not files:
        return []

    entries = []
    for fpath in files:
        soup = _read_html_soup(fpath)
        if not soup:
            continue

        # Each comment block is a top-level div with these classes
        for block in soup.find_all('div', class_='pam _3-95 _2ph- _a6-g uiBoxWhite noborder'):
            table = block.find('table')
            if not table:
                continue

            comment_text = ''
            media_owner = ''
            dt = None

            for td in table.find_all('td', class_='_2pin _a6_q'):
                label = td.get_text(strip=True)
                if label.startswith('Comment'):
                    # Text is inside nested divs: <td>Comment<div><div>TEXT</div></div></td>
                    inner_div = td.find('div')
                    if inner_div:
                        comment_text = inner_div.get_text(strip=True)
                elif label.startswith('Media Owner'):
                    inner_div = td.find('div')
                    if inner_div:
                        media_owner = inner_div.get_text(strip=True)
                elif label.startswith('Time'):
                    # Time value is in the sibling td
                    val_td = td.find_next_sibling('td')
                    if val_td:
                        dt = _parse_timestamp(val_td.get_text(strip=True))

            if comment_text and dt:
                entries.append({
                    'post_url': '',
                    'owner_name': f'Comment on {media_owner}' if media_owner else 'Your comment',
                    'username': media_owner,
                    'datetime': dt,
                    'source': 'your_comment',
                    'text': comment_text
                })

    print(f"  💬 post_comments: {len(entries)} entries")
    return entries


def parse_own_posts(ig_root: str) -> List[Dict]:
    """
    Parse posts_1.html → list of entries with the user's own post captions.
    Caption is in <h2> with class '_a6-h _a6-i' or the first text div.
    """
    pattern = os.path.join(ig_root, 'your_instagram_activity', 'media', 'posts*.html')
    files = glob.glob(pattern)
    if not files:
        return []

    entries = []
    for fpath in files:
        soup = _read_html_soup(fpath)
        if not soup:
            continue

        for date_div in soup.find_all('div', class_='_3-94 _a6-o'):
            dt = _parse_timestamp(date_div.get_text(strip=True))
            container = date_div.parent
            if not container or not dt:
                continue

            # Caption is typically in the <h2> within the same block
            # but NOT the "Creation Source" or "Device" headers
            caption = ''
            for h2 in container.find_all('h2', class_='_a6-h'):
                h2_text = h2.get_text(strip=True)
                # Skip metadata headers
                if h2_text.lower() in ('creation source', 'device id', 'source type'):
                    continue
                caption = h2_text
                break

            if caption:
                entries.append({
                    'post_url': '',
                    'owner_name': 'Your own post',
                    'username': 'self',
                    'datetime': dt,
                    'source': 'your_post',
                    'text': caption
                })

    print(f"  📝 own_posts: {len(entries)} entries")
    return entries


def parse_saved_posts(ig_root: str) -> List[Dict]:
    """
    Parse saved_posts.html → URL + date.
    Structure per saved post:
      <div class="pam _3-95 _2ph- _a6-g uiBoxWhite noborder">
        <h2 class="_a6-h _a6-i">USERNAME</h2>
        <table>
          <tr><td colspan="2">Saved on<div><a target="_blank" href="URL">URL</a></div></td></tr>
          <tr><td>Saved on</td><td class="_2pin _2piu _a6_r">TIMESTAMP</td></tr>
        </table>
      </div>
    """
    path = os.path.join(ig_root, 'your_instagram_activity', 'saved', 'saved_posts.html')
    soup = _read_html_soup(path)
    if not soup:
        return []

    entries = []
    for block in soup.find_all('div', class_='pam _3-95 _2ph- _a6-g uiBoxWhite noborder'):
        # Username is in the h2
        h2 = block.find('h2', class_='_a6-h')
        username = h2.get_text(strip=True) if h2 else 'Unknown'

        # URL from <a target="_blank">
        post_url = None
        for a in block.find_all('a', target='_blank'):
            href = a.get('href', '')
            if re.search(r'instagram\.com/(?:p|reel)/', href):
                post_url = href
                break
        if not post_url:
            continue

        # Timestamp from the value td
        dt = None
        for td in block.find_all('td', class_='_2pin _2piu _a6_r'):
            dt = _parse_timestamp(td.get_text(strip=True))
            if dt:
                break
        if not dt:
            continue

        entries.append({
            'post_url': post_url,
            'owner_name': username,
            'username': username,
            'datetime': dt,
            'source': 'saved_post',
            'text': None  # to be fetched via instaloader
        })

    print(f"  🔖 saved_posts: {len(entries)} entries")
    return entries


def parse_messages(ig_root: str) -> List[Dict]:
    """
    Parse all message_1.html files in inbox/ → extract message text.
    Each message has a sender name in <h2> and text in the content div.
    """
    inbox_dir = os.path.join(ig_root, 'your_instagram_activity', 'messages', 'inbox')
    if not os.path.isdir(inbox_dir):
        return []

    entries = []
    message_files = glob.glob(os.path.join(inbox_dir, '*', 'message_*.html'))

    for fpath in message_files:
        soup = _read_html_soup(fpath)
        if not soup:
            continue

        for date_div in soup.find_all('div', class_='_3-94 _a6-o'):
            dt = _parse_timestamp(date_div.get_text(strip=True))
            container = date_div.parent
            if not container or not dt:
                continue

            # Sender name
            sender_h2 = container.find('h2', class_='_a6-h')
            sender = sender_h2.get_text(strip=True) if sender_h2 else 'Unknown'

            # Message text: content within _a6-p div, excluding links/images
            content_div = container.find('div', class_='_a6-p')
            if not content_div:
                continue

            # Get text from immediate div children (not links, images)
            msg_parts = []
            for child_div in content_div.find_all('div', recursive=False):
                text = child_div.get_text(strip=True)
                if text:
                    msg_parts.append(text)

            msg_text = ' '.join(msg_parts).strip()
            if msg_text:
                entries.append({
                    'post_url': '',
                    'owner_name': f'Message from {sender}',
                    'username': sender,
                    'datetime': dt,
                    'source': 'message',
                    'text': msg_text
                })

    print(f"  📨 messages: {len(entries)} entries")
    return entries


# =====================================================================
# Master parser: collect ALL content, filter by date
# =====================================================================

def parse_all_instagram_data(ig_root: str) -> pd.DataFrame:
    """
    Parse all Instagram activity data into a single DataFrame.

    Sources collected:
    - Liked posts (URLs → need instaloader)
    - Your own comments (direct text)
    - Your own posts / captions (direct text)
    - Saved posts (URLs → need instaloader)
    - Messages sent/received (direct text)

    Returns DataFrame with: post_url, owner_name, username, datetime, source, text
    """
    print(f"📄 Parsing ALL Instagram data from: {ig_root}")
    print(f"   Scanning sources...")

    all_entries = []
    all_entries.extend(parse_liked_posts(ig_root))
    all_entries.extend(parse_post_comments(ig_root))
    all_entries.extend(parse_own_posts(ig_root))
    all_entries.extend(parse_saved_posts(ig_root))
    all_entries.extend(parse_messages(ig_root))

    if not all_entries:
        raise ValueError("No Instagram activity data found in the download folder.")

    df = pd.DataFrame(all_entries)
    df = df.dropna(subset=['datetime'])
    df = df.sort_values('datetime', ascending=False).reset_index(drop=True)

    source_counts = df['source'].value_counts().to_dict()
    print(f"\n✅ Parsed {len(df)} total Instagram activity entries")
    for src, count in source_counts.items():
        print(f"   {src}: {count}")
    print(f"📅 Date range: {df['datetime'].min().date()} to {df['datetime'].max().date()}")

    return df


def extract_instagram_content_for_date(selected_date: date, df: pd.DataFrame) -> Dict[str, Any]:
    """
    For a selected date, collect all textual content across all activity types.

    - Items with text already (comments, own posts, messages): used directly.
    - Items needing instaloader (liked/saved posts): captions fetched from Instagram.

    All results are saved to CSV in the same format as YouTube batch_results
    for compatibility with process_transcripts().
    """
    selected_date_str = selected_date.strftime('%Y-%m-%d')
    print(f"\n📊 Filtering all activity for: {selected_date_str}")

    filtered_df = df[df['datetime'].dt.strftime('%Y-%m-%d') == selected_date_str].copy()

    if len(filtered_df) == 0:
        raise ValueError(f"No Instagram activity found for date {selected_date_str}")

    source_counts = filtered_df['source'].value_counts().to_dict()
    print(f"✅ Found {len(filtered_df)} entries for {selected_date_str}:")
    for src, count in source_counts.items():
        print(f"   {src}: {count}")

    # Separate items that have text vs items that need fetching
    has_text = filtered_df[filtered_df['text'].notna() & (filtered_df['text'] != '')].copy()
    needs_fetch = filtered_df[filtered_df['text'].isna() & filtered_df['post_url'].str.len() > 0].copy()

    # Deduplicate URLs to avoid fetching the same post twice
    needs_fetch = needs_fetch.drop_duplicates(subset='post_url')

    batch_results = []

    # 1) Process items that already have text (comments, own posts, messages)
    print(f"\n📝 {len(has_text)} items with direct text content")
    for _, row in has_text.iterrows():
        text = str(row['text'])
        batch_results.append({
            'timestamp': row['datetime'].strftime('%Y-%m-%d %H:%M:%S'),
            'video_title': f"[{row['source']}] {row['owner_name']}",
            'channel': row['username'],
            'video_url': row.get('post_url', ''),
            'transcript': text,
            'char_count': len(text),
            'word_count': len(text.split()),
            'extraction_time_seconds': 0,
            'success': True
        })

    # 2) Fetch captions + transcribe reels for liked/saved posts
    if len(needs_fetch) > 0:
        print(f"\n🌐 Fetching captions for {len(needs_fetch)} liked/saved posts via instaloader...")
        extractor = InstagramContentExtractor()
        reel_transcriber = ReelTranscriber()  # lazy-loads Whisper only if needed

        for i, (_, row) in enumerate(needs_fetch.iterrows()):
            url = row['post_url']
            owner = row['owner_name']
            username = row['username']
            source = row['source']
            is_reel = ReelTranscriber.is_reel_url(url)

            print(f"  [{i+1}/{len(needs_fetch)}] {source}: {owner} (@{username}){' [REEL]' if is_reel else ''}")

            start_time = time.time()

            # Get caption via instaloader
            caption = extractor.extract_caption(url)
            caption = caption.strip() if caption else ""

            # For reels, also attempt audio transcription
            audio_transcript = None
            if is_reel:
                print(f"    🎤 Attempting reel audio transcription...")
                audio_transcript = reel_transcriber.transcribe(url)
                if audio_transcript:
                    print(f"    🎤 Transcribed: {len(audio_transcript)} chars")
                else:
                    print(f"    🎤 No audio transcript available")

            # Combine caption + audio transcript
            parts = []
            if caption:
                parts.append(caption)
            if audio_transcript:
                parts.append(audio_transcript)
            combined_text = "\n".join(parts).strip()

            elapsed = time.time() - start_time

            if combined_text:
                print(f"    ✅ {len(combined_text)} chars ({elapsed:.1f}s)")
                batch_results.append({
                    'timestamp': row['datetime'].strftime('%Y-%m-%d %H:%M:%S'),
                    'video_title': f"[{source}] {owner} (@{username})",
                    'channel': username,
                    'video_url': url,
                    'transcript': combined_text,
                    'char_count': len(combined_text),
                    'word_count': len(combined_text.split()),
                    'extraction_time_seconds': elapsed,
                    'success': True
                })
            else:
                print(f"    ❌ No content ({elapsed:.1f}s)")
                batch_results.append({
                    'timestamp': row['datetime'].strftime('%Y-%m-%d %H:%M:%S'),
                    'video_title': f"[{source}] {owner} (@{username})",
                    'channel': username,
                    'video_url': url,
                    'transcript': '',
                    'char_count': 0,
                    'word_count': 0,
                    'extraction_time_seconds': elapsed,
                    'success': False,
                    'error': 'No caption or audio transcript available'
                })

            # Rate limit between requests
            if i < len(needs_fetch) - 1:
                wait = 5 if is_reel else 3
                print(f"    ⏳ Rate limiting... waiting {wait}s")
                time.sleep(wait)

    # Save results
    batch_results_path = "batch_results_instagram.csv"
    if batch_results:
        batch_df = pd.DataFrame(batch_results)
        batch_df.to_csv(batch_results_path, index=False)
        print(f"\n💾 Saved {len(batch_results)} results to: {batch_results_path}")

        success_count = batch_df[batch_df['success'] == True].shape[0]
        failed_count = len(batch_df) - success_count
        print(f"   📊 Results: {success_count} successful, {failed_count} failed")
        if success_count > 0:
            print(f"\n🤖 Step 4: Running cognitive distortion analysis (regex + LLM) on {success_count} items...")
            print(f"   This may take a while depending on text volume...")
            analysis_start = time.time()
            process_transcripts(batch_results_path, platform="instagram")
            print(f"   ⏱️ Distortion analysis took {time.time()-analysis_start:.1f}s")
            print(f"   ✅ Results saved to MongoDB (historyDB.instagram)")
        else:
            print("⚠️ No successful content extractions to analyze")
    else:
        batch_df = pd.DataFrame()

    success_df = batch_df[batch_df["success"] == True].reset_index(drop=True) if len(batch_df) > 0 else pd.DataFrame()

    return {
        "date": selected_date_str,
        "total_entries": len(filtered_df),
        "successful_extractions": len(success_df),
        "source_breakdown": source_counts,
        "results": batch_results,
        "csv_path": batch_results_path
    }


# =====================================================================
# Main entry point
# =====================================================================

def analyze_instagram_data(selected_date: date, html_file_path: str) -> Dict[str, Any]:
    """
    Main function: parse all Instagram data, filter by date, extract text, analyze.

    Args:
        selected_date: Date to analyze
        html_file_path: Path to any file from the Instagram download
                        (start_here.html, liked_posts.html, or .zip)
    """
    pipeline_start = time.time()
    try:
        print("=" * 80)
        print("📸 INSTAGRAM ANALYSIS STARTING")
        print(f"   Date: {selected_date}  |  File: {html_file_path}")
        print("=" * 80)

        # Step 1: Resolve download root
        step_t = time.time()
        print(f"\n📂 Step 1: Locating Instagram data...")
        update_processing_status(
            "processing", "instagram",
            step="Locating data", step_number=1, total_steps=5,
            detail="Finding your Instagram data folder",
            progress=5
        )
        ig_root = _resolve_ig_root(html_file_path)
        print(f"   ✅ Root found: {ig_root}  ({time.time()-step_t:.1f}s)")

        # Step 2: Parse ALL activity data
        step_t = time.time()
        print(f"\n📄 Step 2: Parsing all Instagram activity...")
        update_processing_status(
            "processing", "instagram",
            step="Parsing activity data", step_number=2, total_steps=5,
            detail="Reading all your Instagram activity files",
            progress=15
        )
        df = parse_all_instagram_data(ig_root)
        print(f"   ⏱️ Parsing took {time.time()-step_t:.1f}s")

        # Step 3: Extract content for selected date & run analysis
        step_t = time.time()
        print(f"\n📝 Step 3: Extracting content for {selected_date}...")
        update_processing_status(
            "processing", "instagram",
            step="Extracting content", step_number=3, total_steps=5,
            detail=f"Collecting content from {selected_date}",
            progress=35
        )
        result = extract_instagram_content_for_date(selected_date, df)
        print(f"   ⏱️ Extraction + analysis took {time.time()-step_t:.1f}s")

        if result["successful_extractions"] == 0:
            update_processing_status("error", platform="instagram")
            print(f"\n❌ No successful extractions. Pipeline finished in {time.time()-pipeline_start:.1f}s")
            return {
                "status": "error",
                "error": "No successful content extractions for the selected date",
                "data": result
            }

        print(f"\n{'='*80}")
        print(f"✅ INSTAGRAM ANALYSIS COMPLETED SUCCESSFULLY")
        print(f"   Total pipeline time: {time.time()-pipeline_start:.1f}s")
        print(f"   Entries analyzed: {result['successful_extractions']}/{result['total_entries']}")
        print(f"{'='*80}")
        return {
            "status": "success",
            "data": result
        }

    except ValueError as e:
        update_processing_status("error", platform="instagram")
        return {"status": "error", "error": str(e), "data": None}
    except Exception as e:
        update_processing_status("error", platform="instagram")
        print(f"❌ Instagram analysis failed: {e}")
        return {"status": "error", "error": str(e), "data": None}
