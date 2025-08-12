import os
import time
import random
import traceback
import threading
from flask import Flask
from instagrapi import Client
from instagrapi.exceptions import (
    ClientError, ClientLoginRequired, ChallengeRequired,
    FeedbackRequired, SentryBlock, PleaseWaitFewMinutes,
    LoginRequired
)

# ========================
# CONFIGURATION (Environment Variables)
# ========================
SESSION_FILE = "session.json"
DELAY_RANGE = tuple(map(int, os.getenv('DELAY_RANGE', '60,120').split(',')))  # Default: 60-120s
CYCLE_DELAY = int(os.getenv('CYCLE_DELAY', '300'))  # Default: 300s (5 min)
MAX_RETRIES = 3
MAX_MESSAGE_LENGTH = 1000
PORT = int(os.getenv('PORT', '10000'))  # Render requires port binding

# ========================
# FLASK SERVER (For port binding)
# ========================
app = Flask(__name__)

@app.route('/')
def home():
    """Simple health check endpoint"""
    return "Instagram Bot is Running | Status: Active", 200

def run_web_server():
    """Run Flask server in separate thread"""
    app.run(host='0.0.0.0', port=PORT)

# ========================
# BOT FUNCTIONS
# ========================
def load_config():
    """Load configuration from environment variables"""
    config = {
        'session_id': os.getenv('SESSION_ID'),
        'thread_ids': [],
        'message_text': ''
    }
    
    # Validate session ID
    if not config['session_id']:
        print("❌ Error: SESSION_ID environment variable not set!")
        exit(1)
    
    # Parse thread IDs
    thread_ids_str = os.getenv('THREAD_IDS', '')
    if thread_ids_str:
        config['thread_ids'] = [tid.strip() for tid in thread_ids_str.split(',') if tid.strip()]
    else:
        print("❌ Error: THREAD_IDS environment variable not set!")
        exit(1)
    
    # Get message content
    config['message_text'] = os.getenv('MESSAGE_TEXT', '')[:MAX_MESSAGE_LENGTH]
    if not config['message_text']:
        print("❌ Error: MESSAGE_TEXT environment variable not set!")
        exit(1)
    
    print(f"• Loaded {len(config['thread_ids'])} thread IDs")
    print(f"• Message: {config['message_text'][:50]}...")
    return config

def setup_client(session_id):
    """Initialize and authenticate Instagram client"""
    cl = Client()
    cl.request_timeout = 30  # Increase timeout for reliability
    
    # Try to load existing session
    if os.path.exists(SESSION_FILE):
        try:
            cl.load_settings(SESSION_FILE)
            cl.get_timeline_feed()  # Test session
            print("✅ Session loaded successfully")
            return cl
        except (ClientLoginRequired, ChallengeRequired, LoginRequired):
            print("⚠️ Session expired, re-authenticating...")
    
    # New authentication
    try:
        cl.login_by_sessionid(session_id)
        cl.dump_settings(SESSION_FILE)
        print("✅ Login successful! Session saved")
        return cl
    except Exception as e:
        print(f"🚨 Critical login error: {str(e)}")
        traceback.print_exc()
        exit(1)

def send_message(cl, message, thread_id, attempt=1):
    """Send message with error handling and retries"""
    try:
        cl.direct_send(message, thread_ids=[thread_id])
        return True
    except (FeedbackRequired, SentryBlock, PleaseWaitFewMinutes) as e:
        if attempt <= MAX_RETRIES:
            wait = 120 * attempt  # Exponential backoff
            print(f"⏳ Instagram limit: Waiting {wait}s (Attempt {attempt}/{MAX_RETRIES})")
            time.sleep(wait)
            return send_message(cl, message, thread_id, attempt+1)
        print(f"❌ Permanent send error: {str(e)}")
        return False
    except (ClientError, LoginRequired) as e:
        print(f"⚠️ Client error: {str(e)}")
        if attempt <= MAX_RETRIES:
            time.sleep(10)
            return send_message(cl, message, thread_id, attempt+1)
        return False
    except Exception as e:
        print(f"🚨 Unexpected error: {traceback.format_exc()}")
        return False

def bot_operation():
    """Main bot operational loop"""
    print("\n🚀 Starting Instagram Bot")
    print("----------------------------------")
    
    config = load_config()
    cl = setup_client(config['session_id'])
    
    print("\n⚙️ Settings:")
    print(f"• Message delay: {DELAY_RANGE[0]}-{DELAY_RANGE[1]}s")
    print(f"• Cycle delay: {CYCLE_DELAY}s")
    print(f"• Press Ctrl+C to stop")
    print("----------------------------------")
    
    cycle = 0
    while True:
        cycle += 1
        start_time = time.time()
        success = 0
        
        print(f"\n🌀 CYCLE #{cycle} STARTED")
        for i, thread_id in enumerate(config['thread_ids'], 1):
            print(f"[{i}/{len(config['thread_ids'])}] Sending to {thread_id}...")
            if send_message(cl, config['message_text'], thread_id):
                success += 1
                status = "✅ Success"
            else:
                status = "❌ Failed"
            
            delay = random.randint(*DELAY_RANGE)
            print(f"   {status} | Next in {delay}s")
            time.sleep(delay)
        
        elapsed = int(time.time() - start_time)
        print(f"\n⏱️ CYCLE #{cycle} COMPLETE")
        print(f"• Success rate: {success}/{len(config['thread_ids'])}")
        print(f"• Duration: {elapsed}s")
        print(f"⏳ Next cycle in {CYCLE_DELAY}s...")
        time.sleep(CYCLE_DELAY)

# ========================
# MAIN EXECUTION
# ========================
if __name__ == "__main__":
    # Start web server in background thread
    web_thread = threading.Thread(target=run_web_server, daemon=True)
    web_thread.start()
    print(f"🌐 Web server running on port {PORT}")
    
    # Start bot in main thread
    try:
        bot_operation()
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped by user")
    except Exception as e:
        print(f"🔥 Critical error: {traceback.format_exc()}")
