import pandas as pd
import re
from bs4 import BeautifulSoup
from datetime import datetime, date, timedelta
import os
import tempfile
import time
import json
import sys
from typing import Dict, Any, List, Optional
import subprocess
import importlib.util
import yt_dlp
from pydub import AudioSegment
import shutil
from model_processor import process_transcripts, update_processing_status
import sys




# # Install required packages if not available
# def install_required_packages():
#     """Install required packages for YouTube analysis"""
#     required_packages = [
#         'beautifulsoup4',
#         'lxml',
#         'yt-dlp',
#         'openai-whisper',
#         'youtube-transcript-api',
#         'pandas'
#     ]
    
#     for package in required_packages:
#         try:
#             importlib.import_module(package.replace('-', '_'))
#             print(f"✅ {package} already installed")
#         except ImportError:
#             print(f"📦 Installing {package}...")
#             subprocess.check_call([sys.executable, "-m", "pip", "install", package])
    
#     # Install system dependencies for Whisper
#     try:
#         import whisper
#     except:
#         print("🔧 Installing Whisper system dependencies...")
#         if os.name == 'posix':  # Linux/Unix
#             subprocess.check_call(['apt-get', 'update'])
#             subprocess.check_call(['apt-get', 'install', '-y', 'ffmpeg'])
#         elif os.name == 'nt':  # Windows
#             print("⚠️ On Windows, please install FFmpeg manually and add to PATH")

class FreeTranscriptExtractor:
    def __init__(self, whisper_model_size="base"):
        """Initialize with specified Whisper model size"""
        print(f"🔧 Loading Whisper {whisper_model_size} model...")
        import whisper
        self.whisper_model = whisper.load_model(whisper_model_size)
        print("✅ Whisper model loaded successfully!")

    def extract(self, url, use_direct_transcript=True):
        """Main extraction method"""
        url = url.strip()
        
        # Try YouTube direct transcript first
        if use_direct_transcript and ("youtube.com" in url or "youtu.be" in url):
            transcript = self._extract_youtube_transcript(url)
            if transcript and not transcript.startswith("No direct transcript"):
                return transcript
        
        # Fallback to Whisper
        return self._download_and_transcribe(url)

    def _extract_youtube_transcript(self, url):
        """Extract existing YouTube captions"""
        try:
            from youtube_transcript_api import YouTubeTranscriptApi
            
            # Extract video ID
            patterns = [
                r'(?:v=|\/)([0-9A-Za-z_-]{11})',
                r'(?:embed\/)([0-9A-Za-z_-]{11})',
                r'(?:shorts\/)([0-9A-Za-z_-]{11})'
            ]
            
            video_id = None
            for pattern in patterns:
                match = re.search(pattern, url)
                if match:
                    video_id = match.group(1)
                    break
            
            if not video_id:
                return None
            
            # Get transcript
            transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
            transcript = ' '.join([item['text'] for item in transcript_list])
            
            if transcript and len(transcript) > 10:
                return transcript
            return None
            
        except Exception as e:
            return None

    def _download_and_transcribe(self, url):
        """Download audio in Whisper-optimized format and transcribe"""
        import yt_dlp
        from pydub import AudioSegment

        with tempfile.TemporaryDirectory() as tmpdir:
            ydl_opts = {
                # Save bandwidth but preserve speech clarity
                "format": "bestaudio[abr<=96]/bestaudio",
                "outtmpl": os.path.join(tmpdir, "audio.%(ext)s"),
                "quiet": True,
                "no_warnings": True,
                "restrictfilenames": True,
            }

            try:
                # Clean URL (remove tracking params)
                clean_url = re.sub(r'(\?|&)si=[^&]*', '', url)
                clean_url = re.sub(r'(\?|&)t=[^&]*', '', clean_url)

                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(clean_url, download=True)

                    if info:
                        print(f"📥 Downloaded: {info.get('title', 'Unknown title')}")
                        print(f"⏱️ Duration: {info.get('duration', 0)} seconds")

                # Find downloaded audio file
                audio_file = None
                for file in os.listdir(tmpdir):
                    if file.endswith((".m4a", ".webm", ".mp3")):
                        audio_file = os.path.join(tmpdir, file)
                        break

                if not audio_file:
                    return "❌ Could not find downloaded audio file"

                print(f"🎵 Audio file found: {os.path.basename(audio_file)}")

                # Convert to Whisper-friendly WAV
                audio = AudioSegment.from_file(audio_file)
                audio = audio.set_channels(1)        # mono
                audio = audio.set_frame_rate(16000)  # 16 kHz

                wav_path = os.path.join(tmpdir, "audio_whisper.wav")
                audio.export(wav_path, format="wav")

                # Transcribe
                print("🔊 Transcribing audio with Whisper...")
                result = self.whisper_model.transcribe(wav_path)

                return result["text"]

            except Exception as e:
                error_msg = str(e)
                if "403" in error_msg:
                    return "❌ Error: Access denied (403). YouTube may be blocking the request."
                elif "Private video" in error_msg:
                    return "❌ Error: Video is private or requires login"
                elif "unavailable" in error_msg.lower():
                    return "❌ Error: Video unavailable or region blocked"
                else:
                    return f"❌ Error: {error_msg}"



def parse_youtube_history(html_file_path: str) -> pd.DataFrame:
    """
    Parse YouTube watch history HTML file
    
    Args:
        html_file_path: Path to YouTube watch history HTML
        
    Returns:
        DataFrame with parsed YouTube data
    """
    print(f"📄 Parsing YouTube history from {html_file_path}...")
    
    with open(html_file_path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f, "lxml")
    
    records = []
    
    for div in soup.find_all("div", class_="content-cell"):
        text = div.get_text(separator=" ", strip=True)
        
        if text.startswith("Watched"):
            links = div.find_all("a")
            full_text = div.get_text(separator=" ", strip=True)
            
            # Extract date and time
            date_time_pattern = r'([A-Z][a-z]{2} \d{1,2}, \d{4}, \d{1,2}:\d{2}:\d{2}\s*[AP]M)'
            date_time_match = re.search(date_time_pattern, full_text)
            
            title = links[0].text if len(links) > 0 else None
            url = links[0]["href"] if len(links) > 0 else None
            channel = links[1].text if len(links) > 1 else None
            
            date_str = None
            time_str = None
            
            if date_time_match:
                date_time_str = date_time_match.group(1)
                parts = date_time_str.split(', ')
                
                if len(parts) >= 2:
                    date_str = parts[0] + ', ' + parts[1]
                    
                    if len(parts) >= 3:
                        time_str = parts[2].split(' GMT')[0].strip()
            
            records.append({
                "video_title": title,
                "channel": channel,
                "video_url": url,
                "date": date_str,
                "time": time_str
            })
    
    # Create DataFrame
    df = pd.DataFrame(records).dropna(subset=["video_title"])
    
    if len(df) == 0:
        raise ValueError("No YouTube data found in HTML file")
    
    # Parse datetime
    df['datetime'] = pd.to_datetime(
        df['date'] + ' ' + df['time'],
        format='%b %d, %Y %I:%M:%S %p',
        errors='coerce'
    )
    
    df = df.dropna(subset=['datetime'])
    
    print(f"✅ Parsed {len(df)} total YouTube watch history entries")
    print(f"📅 Date range: {df['datetime'].min().date()} to {df['datetime'].max().date()}")
    
    return df

def extract_youtube_transcripts_for_date(selected_date: date, df: pd.DataFrame) -> Dict[str, Any]:
    """
    Extract transcripts for YouTube videos on a specific date
    
    Args:
        selected_date: Date to analyze
        df: DataFrame with YouTube history
        
    Returns:
        Dictionary with extracted transcripts and metadata
    """
    print(f"📊 Filtering for selected date: {selected_date}")
    selected_date_str = selected_date.strftime('%Y-%m-%d')
    #filtered_df = df[df['datetime'].dt.strftime('%Y-%m-%d') == selected_date_str].copy()
    filtered_df = df[df['datetime'].dt.strftime('%Y-%m-%d') == selected_date_str].head(1).copy()
    
    if len(filtered_df) == 0:
        raise ValueError(f"No YouTube data found for date {selected_date_str}")
    
    #print(f"✅ Found {len(filtered_df)} videos watched on {selected_date_str}")
    
    # Save filtered data to CSV
    save_df = filtered_df.copy()
    save_df['time'] = save_df['datetime'].dt.strftime('%I:%M %p')
    save_df = save_df[['time', 'video_title', 'channel', 'video_url']]
    
    videos_csv_path = "vedios.csv"
    save_df.to_csv(videos_csv_path, index=False)
    print(f"💾 Saved daily watch history to: {videos_csv_path}")
    
    # Extract transcripts
    print(f"\n🎙️ Extracting transcripts for {len(filtered_df)} videos...")
    
    # Initialize transcript extractor
    extractor = FreeTranscriptExtractor(whisper_model_size="base")
    
    all_transcripts = []
    batch_results = []
    
    for i, (index, row) in enumerate(filtered_df.iterrows()):
        url = row['video_url']
        title = row['video_title']
        
        print(f"\n Processing: {title[:50]}...")
        print(f"URL: {url}")
        
        update_processing_status(
            "processing", "youtube",
            step="Extracting transcripts", step_number=3, total_steps=5,
            detail=f"Transcript {i+1} of {len(filtered_df)}: {title[:40]}...",
            progress=int(30 + (i / max(len(filtered_df), 1)) * 25)
        )
        
        start_time = time.time()
        transcript = extractor.extract(url, use_direct_transcript=True)
        elapsed_time = time.time() - start_time
        
        if transcript and not transcript.startswith("❌"):
            print(f"✅ Success! ({elapsed_time:.1f}s, {len(transcript)} chars)")
            
            # Save individual transcript
            transcript_data = {
                'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
                'video_title': title,
                'channel': row['channel'],
                'video_url': url,
                'transcript': transcript,
                'char_count': len(transcript),
                'word_count': len(transcript.split()),
                'extraction_time_seconds': elapsed_time,
                'success': True
            }
            
            all_transcripts.append(transcript)
            batch_results.append(transcript_data)
            
        else:
            print(f"❌ Failed ({elapsed_time:.1f}s)")
            batch_results.append({
                'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
                'video_title': title,
                'channel': row['channel'],
                'video_url': url,
                'transcript': '',
                'char_count': 0,
                'word_count': 0,
                'extraction_time_seconds': elapsed_time,
                'success': False,
                'error': transcript if transcript else "Unknown error"
            })
    
    # Save batch results to CSV
    batch_results_path = f"batch_results_.csv"
    if batch_results:
        batch_df = pd.DataFrame(batch_results)
        batch_df.to_csv(batch_results_path, index=False)
        print(f"\n💾 Batch results saved to: {batch_results_path}")
        process_transcripts(batch_results_path)
    else:
        batch_df = pd.DataFrame()
        print("\n⚠️ No batch results to save")
    
    # Filter successful transcripts
    success_df = batch_df[batch_df["success"] == True].reset_index(drop=True)
    
    result_data = {
        "date": selected_date_str,
        "video_count": len(filtered_df),
        "successful_transcripts": len(success_df),
        "videos": filtered_df.to_dict('records'),
        "transcripts": batch_results,
        "csv_paths": {
            "daily_videos": videos_csv_path,
            "batch_results": batch_results_path
        }
    }
    
    return result_data

def analyze_youtube_data(selected_date: date, html_file_path: str = "watch-history.html") -> Dict[str, Any]:
    """
    Main function to analyze YouTube data
    
    Args:
        selected_date: Date to analyze
        html_file_path: Path to YouTube watch history HTML
        
    Returns:
        Dictionary with analysis results
    """
    try:
        print("="*80)
        print("🎬 YOUTUBE ANALYSIS STARTING")
        print("="*80)
        
        # Step 1: Install required packages
        print("\n📦 Step 1: Checking/Installing required packages...")
        update_processing_status(
            "processing", "youtube",
            step="Initializing", step_number=1, total_steps=5,
            detail="Setting up analysis environment",
            progress=5
        )
        #install_required_packages()
        
        # Step 2: Parse YouTube watch history
        print(f"\n📄 Step 2: Parsing YouTube history...")
        update_processing_status(
            "processing", "youtube",
            step="Parsing watch history", step_number=2, total_steps=5,
            detail="Reading your YouTube watch history file",
            progress=15
        )
        if not os.path.exists(html_file_path):
            return {
                "status": "error",
                "error": f"YouTube history file not found: {html_file_path}",
                "data": None
            }
        
        df = parse_youtube_history(html_file_path)
        
        # Step 3: Extract transcripts for selected date
        print(f"\n🎙️ Step 3: Extracting transcripts...")
        update_processing_status(
            "processing", "youtube",
            step="Extracting transcripts", step_number=3, total_steps=5,
            detail="Downloading and extracting video transcripts",
            progress=30
        )
        result = extract_youtube_transcripts_for_date(selected_date, df)
        
        if result["successful_transcripts"] == 0:
            return {
                "status": "error",
                "error": "No successful transcript extractions",
                "data": result
            }
        
        print(f"\n✅ YouTube analysis completed successfully!")
        print(f"📅 Date: {result['date']}")
        print(f"🎬 Videos: {result['video_count']}")
        print(f"📝 Successful Transcripts: {result['successful_transcripts']}")
        print("="*80)
        
        return {
            "status": "success",
            "message": "YouTube data processed successfully",
            "data": result
        }
    
    
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"\n❌ ERROR in YouTube analysis: {str(e)}")
        print(f"Details: {error_details}")
        
        return {
            "status": "error",
            "error": str(e),
            "traceback": error_details,
            "data": None
        }

if __name__ == "__main__":
    try:
        # Get date from Flask (command line argument)
        if len(sys.argv) < 2:
            print("❌ No date provided")
            sys.exit(1)

        date_string = sys.argv[1]  # format: YYYY-MM-DD
        selected_date = datetime.strptime(date_string, "%Y-%m-%d").date()

        print(f"\n🎯 Running YouTube analysis for date: {selected_date}")

        html_path = "watch-history.html"

        result = analyze_youtube_data(selected_date, html_path)

        # Print JSON result so Flask can capture it
        print(json.dumps(result))

    except Exception as e:
        print(json.dumps({
            "status": "error",
            "error": str(e)
        }))

