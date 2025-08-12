import os
import time
import random
import traceback
import threading
import requests
from flask import Flask
from instagrapi import Client
from instagrapi.exceptions import (
    ClientError, ClientLoginRequired, ChallengeRequired,
    FeedbackRequired, SentryBlock, PleaseWaitFewMinutes,
    LoginRequired
)

# ========================
# CONFIGURATION
# ========================
SESSION_FILE = "session.json"
SESSION_TXT = "session.txt"
THREAD_FILE = "gc.txt"
MESSAGE_FILE = "msg.txt"
DELAY_RANGE = (60, 120)  # 1-2 minutes between messages
CYCLE_DELAY = 300  # 5 minutes between cycles
MAX_RETRIES = 3
MAX_MESSAGE_LENGTH = 1000
PORT = int(os.getenv("PORT", "10000"))  # Render's port binding requirement
KEEP_ALIVE_URL = "https://your-service-name.onrender.com"  # CHANGE TO YOUR RENDER URL

# ========================
# FLASK SERVER (For port binding)
# ========================
app = Flask(__name__)

@app.route('/')
def health_check():
    """Health check endpoint for Render port binding"""
    return "Instagram Bot is Active | Status: Running", 200

def run_web_server():
    """Run Flask server in separate thread"""
    app.run(host='0.0.0.0', port=PORT)

# ========================
# KEEP-ALIVE MECHANISM
# ========================
def keep_alive_pinger():
    """Ping our own service to prevent Render from sleeping"""
    while True:
        try:
            response = requests.get(KEEP_ALIVE_URL)
            print(f"🔁 Keep-alive ping: {response.status_code} | Next in 5 minutes")
        except Exception as e:
            print(f"⚠️ Keep-alive failed: {str(e)}")
        time.sleep(300)  # Ping every 5 minutes

# ========================
# FILE HANDLING
# ========================
def ensure_files_exist():
    """Verify required files exist or create them from environment variables"""
    # Create session.txt if environment variable exists
    if "RENDER_SESSION_ID" in os.environ and not os.path.exists(SESSION_TXT):
        with open(SESSION_TXT, "w") as f:
            f.write(os.environ["RENDER_SESSION_ID"])
        print(f"Created {SESSION_TXT} from environment variable")
    
    # Create msg.txt if environment variable exists
    if "RENDER_MESSAGE_TEXT" in os.environ and not os.path.exists(MESSAGE_FILE):
        with open(MESSAGE_FILE, "w") as f:
            f.write(os.environ["RENDER_MESSAGE_TEXT"])
        print(f"Created {MESSAGE_FILE} from environment variable")
    
    # Create gc.txt if environment variable exists
    if "RENDER_THREAD_IDS" in os.environ and not os.path.exists(THREAD_FILE):
        with open(THREAD_FILE, "w") as f:
            # Convert comma-separated string to line-separated
            thread_ids = os.environ["RENDER_THREAD_IDS"].split(",")
            f.write("\n".join(thread_ids))
        print(f"Created {THREAD_FILE} from environment variable")

def load_config():
    """Load configuration from files with validation"""
    # Ensure files exist
    for file_path in [SESSION_TXT, THREAD_FILE, MESSAGE_FILE]:
        if not os.path.exists(file_path):
            print(f"❌ Error: {file_path} not found!")
            exit(1)
    
    # Load session ID
    with open(SESSION_TXT, "r") as f:
        session_id = f.read().strip()
    if not session_id:
        print(f"❌ Error: {SESSION_TXT} is empty!")
        exit(1)
    
    # Load thread IDs
    with open(THREAD_FILE, "r") as f:
        thread_ids = [line.strip() for line in f.readlines() if line.strip()]
    if not thread_ids:
        print(f"❌ Error: No valid thread IDs in {THREAD_FILE}!")
        exit(1)
    
    # Load message text
    with open(MESSAGE_FILE, "r", encoding="utf-8") as f:
        message_text = f.read().strip()[:MAX_MESSAGE_LENGTH]
    if not message_text:
        print(f"❌ Error: {MESSAGE_FILE} is empty!")
        exit(1)
    
    print(f"• Loaded session ID from {SESSION_TXT}")
    print(f"• Loaded {len(thread_ids)} thread IDs from {THREAD_FILE}")
    print(f"• Loaded message from {MESSAGE_FILE}")
    return session_id, thread_ids, message_text

# ========================
# INSTAGRAM CLIENT
# ========================
def setup_client(session_id):
    """Initialize and authenticate Instagram client"""
    cl = Client()
    cl.request_timeout = 30  # Increase timeout for reliability
    
    # Try to load existing session
    if os.path.exists(SESSION_FILE):
        try:
            cl.load_settings(SESSION_FILE)
            cl.get_timeline_feed()  # Test session validity
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

# ========================
# MESSAGE HANDLING
# ========================
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

# ========================
# BOT OPERATION
# ========================
def run_bot():
    """Main bot operation loop"""
    print("\n🚀 Starting Instagram Bot")
    print("----------------------------------")
    
    # Load configuration from files
    session_id, thread_ids, message_text = load_config()
    
    # Initialize client
    cl = setup_client(session_id)
    
    print("\n⚙️ Settings:")
    print(f"• Message delay: {DELAY_RANGE[0]}-{DELAY_RANGE[1]}s")
    print(f"• Cycle delay: {CYCLE_DELAY}s")
    print(f"• Keep-alive URL: {KEEP_ALIVE_URL}")
    print(f"• Press Ctrl+C to stop")
    print("----------------------------------")
    
    cycle = 0
    while True:
        cycle += 1
        start_time = time.time()
        success_count = 0
        
        print(f"\n🌀 CYCLE #{cycle} STARTED")
        for idx, thread_id in enumerate(thread_ids, 1):
            print(f"[{idx}/{len(thread_ids)}] Sending to {thread_id}...")
            if send_message(cl, message_text, thread_id):
                success_count += 1
                status = "✅ Success"
            else:
                status = "❌ Failed"
            
            delay = random.randint(*DELAY_RANGE)
            print(f"   {status} | Next in {delay}s")
            time.sleep(delay)
        
        elapsed = int(time.time() - start_time)
        print(f"\n⏱️ CYCLE #{cycle} COMPLETE")
        print(f"• Success rate: {success_count}/{len(thread_ids)}")
        print(f"• Duration: {elapsed}s")
        print(f"⏳ Next cycle in {CYCLE_DELAY}s...")
        time.sleep(CYCLE_DELAY)

# ========================
# MAIN EXECUTION
# ========================
if __name__ == "__main__":
    # Render compatibility: Create files from environment variables if needed
    ensure_files_exist()
    
    # Start web server in background thread
    web_thread = threading.Thread(target=run_web_server, daemon=True)
    web_thread.start()
    print(f"🌐 Web server running on port {PORT}")
    
    # Start keep-alive pinger
    pinger_thread = threading.Thread(target=keep_alive_pinger, daemon=True)
    pinger_thread.start()
    print(f"♻️ Keep-alive started for {KEEP_ALIVE_URL}")
    
    # Start bot in main thread
    try:
        run_bot()
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped by user")
    except Exception as e:
        print(f"🔥 Critical error: {traceback.format_exc()}")
