"""
Japanese YouTube Transcript Fetcher - Flask Server
Fetches Japanese transcripts from YouTube videos using youtube-transcript-api
Supports proxy rotation to avoid YouTube IP blocking
"""

import os
import json
import random
from flask import Flask, request, jsonify
from flask_cors import CORS
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import TranscriptsDisabled, NoTranscriptFound

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Proxy configuration from environment variables
# Format: PROXY_URL=http://user:pass@proxy.example.com:port
# For multiple proxies (rotation): PROXY_URLS=http://p1:port,http://p2:port,http://p3:port
PROXY_URL = os.environ.get('PROXY_URL')
PROXY_URLS = os.environ.get('PROXY_URLS', '').split(',') if os.environ.get('PROXY_URLS') else []

def get_proxy_config():
    """Get proxy configuration, rotating if multiple proxies available"""
    proxy = None

    # If multiple proxies configured, pick random one for rotation
    if PROXY_URLS and PROXY_URLS[0]:
        proxy = random.choice(PROXY_URLS)
        print(f"[PROXY] Using rotating proxy: {proxy[:30]}...")
    elif PROXY_URL:
        proxy = PROXY_URL
        print(f"[PROXY] Using single proxy: {proxy[:30]}...")

    if proxy:
        return {"http": proxy, "https": proxy}

    print("[PROXY] No proxy configured - using direct connection")
    return None

def create_transcript_api():
    """Create YouTubeTranscriptApi instance with optional proxy"""
    proxies = get_proxy_config()
    if proxies:
        return YouTubeTranscriptApi(proxies=proxies)
    return YouTubeTranscriptApi()

def fetch_japanese_transcript(video_id):
    """
    Fetch Japanese transcript for a YouTube video
    Prioritizes manual Japanese over auto-generated Japanese
    """
    try:
        # Create YouTubeTranscriptApi instance with optional proxy support
        ytt_api = create_transcript_api()
        transcript_list = ytt_api.list(video_id)

        available_transcripts = []
        japanese_transcripts = []

        # Collect all available transcripts and identify Japanese ones
        for transcript in transcript_list:
            transcript_info = {
                'language': transcript.language,
                'language_code': transcript.language_code,
                'is_generated': transcript.is_generated,
                'is_translatable': transcript.is_translatable
            }
            available_transcripts.append(transcript_info)

            # Check for Japanese transcripts
            if (transcript.language_code == 'ja' or
                'japanese' in transcript.language.lower() or
                '日本語' in transcript.language):
                japanese_transcripts.append({
                    'transcript': transcript,
                    'info': transcript_info
                })

        print(f"Available transcripts for {video_id}: {len(available_transcripts)}")
        print(f"Japanese transcripts found: {len(japanese_transcripts)}")

        selected_transcript = None

        if japanese_transcripts:
            # Prefer manual Japanese over auto-generated Japanese
            manual_japanese = [jt for jt in japanese_transcripts if not jt['info']['is_generated']]
            if manual_japanese:
                selected_transcript = manual_japanese[0]['transcript']
                print(f"Selected manual Japanese transcript: {manual_japanese[0]['info']['language']}")
            else:
                selected_transcript = japanese_transcripts[0]['transcript']
                print(f"Selected auto-generated Japanese transcript: {japanese_transcripts[0]['info']['language']}")
        else:
            # No Japanese transcripts found
            print("ERROR: No Japanese transcripts available for this video")
            return {
                'available': False,
                'videoId': video_id,
                'message': 'No Japanese transcripts available for this video',
                'availableLanguages': [t['language'] + ' (' + t['language_code'] + ')' for t in available_transcripts],
                'source': 'custom-server'
            }

        # Fetch the actual transcript data
        fetched_transcript = selected_transcript.fetch()

        # Transform to expected format - handle both dict and object access
        segments = []
        for snippet in fetched_transcript:
            # Try dict access first, fall back to attribute access
            try:
                start = float(snippet['start'])
                duration = float(snippet['duration'])
                text = snippet['text'].strip()
            except (TypeError, KeyError):
                start = float(snippet.start)
                duration = float(snippet.duration)
                text = snippet.text.strip()

            end = start + duration

            # Skip empty or music/sound effect annotations
            if text and not (text.startswith('[') and text.endswith(']')):
                segments.append({
                    'start': start,
                    'duration': duration,
                    'end': end,
                    'text': text
                })

        return {
            'available': True,
            'videoId': video_id,
            'title': f'Video {video_id}',
            'language': selected_transcript.language,
            'languageCode': selected_transcript.language_code,
            'isJapanese': True,
            'isGenerated': selected_transcript.is_generated,
            'availableLanguages': [jt['info']['language'] + (' (auto)' if jt['info']['is_generated'] else ' (manual)')
                                 for jt in japanese_transcripts],
            'segments': segments,
            'totalSegments': len(segments),
            'totalDuration': segments[-1]['end'] if segments else 0,
            'source': 'custom-server'
        }

    except TranscriptsDisabled:
        return {
            'available': False,
            'videoId': video_id,
            'message': 'Transcripts are disabled for this video',
            'source': 'custom-server'
        }
    except NoTranscriptFound as e:
        return {
            'available': False,
            'videoId': video_id,
            'message': f'No transcript found: {str(e)}',
            'source': 'custom-server'
        }
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"Full error traceback: {error_details}")
        return {
            'available': False,
            'videoId': video_id,
            'message': f'Error fetching transcript: {str(e)}',
            'error_type': type(e).__name__,
            'source': 'custom-server'
        }


@app.route('/get-japanese-transcript', methods=['GET', 'POST', 'OPTIONS'])
def get_transcript():
    """
    HTTP endpoint for transcript fetching
    Handles CORS and processes transcript requests
    """
    # Handle CORS preflight
    if request.method == 'OPTIONS':
        response = jsonify({})
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        return response, 204

    try:
        # Get video ID from query parameter or JSON body
        video_id = None

        if request.method == 'GET':
            video_id = request.args.get('videoId')
        elif request.method == 'POST':
            request_json = request.get_json(silent=True)
            if request_json and 'videoId' in request_json:
                video_id = request_json['videoId']

        if not video_id:
            return jsonify({
                'error': 'Video ID is required',
                'message': 'Please provide videoId as query parameter or in request body'
            }), 400

        print(f"Processing transcript request for video: {video_id}")

        # Fetch transcript
        result = fetch_japanese_transcript(video_id)

        return jsonify(result), 200

    except Exception as e:
        print(f"Error in server: {str(e)}")
        return jsonify({
            'error': 'Internal server error',
            'message': str(e),
            'available': False,
            'source': 'custom-server'
        }), 500


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({'status': 'healthy', 'service': 'transcript-server'}), 200


@app.route('/', methods=['GET'])
def root():
    """Root endpoint with service info"""
    proxy_status = 'rotating' if PROXY_URLS and PROXY_URLS[0] else ('single' if PROXY_URL else 'none')
    return jsonify({
        'service': 'YouTube Transcript Service',
        'version': '1.1.0',
        'proxy_status': proxy_status,
        'endpoints': {
            'transcript': 'GET /get-japanese-transcript?videoId={id}',
            'health': 'GET /health'
        }
    }), 200


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
