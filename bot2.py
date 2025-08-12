import os
import time
import random
import traceback
from instagrapi import Client
from instagrapi.exceptions import (
    ClientError, ClientLoginRequired, ChallengeRequired,
    BadPassword, FeedbackRequired, SentryBlock, PleaseWaitFewMinutes,
    LoginRequired
)

# Configuration
SESSION_FILE = "session.json"
SESSION_ID_FILE = "session.txt"  # Added session ID file
THREAD_FILE = "gc.txt"
MESSAGE_FILE = "msg.txt"
DELAY_RANGE = (100, 300)  # Safer delay range (1-2 minutes)
CYCLE_DELAY = 500  # 5 minutes between cycles
MAX_RETRIES = 3
MAX_MESSAGE_LENGTH = 1000

def load_config():
    """Load configuration with UTF-8 encoding support and session ID"""
    config = {
        'session_id': '',
        'thread_ids': [],
        'message_text': ''
    }
    
    # Load session ID
    if not os.path.exists(SESSION_ID_FILE):
        print(f"❌ Error: Session file '{SESSION_ID_FILE}' not found!")
        print(f"Please create a file named '{SESSION_ID_FILE}' with your session ID")
        exit(1)
    
    with open(SESSION_ID_FILE, 'r') as f:
        config['session_id'] = f.read().strip()
    
    if not config['session_id']:
        print(f"❌ Error: Session file '{SESSION_ID_FILE}' is empty!")
        exit(1)
    
    # Load thread IDs
    try:
        if os.path.exists(THREAD_FILE):
            with open(THREAD_FILE, 'r', encoding='utf-8') as f:
                config['thread_ids'] = [line.strip() for line in f if line.strip()]
    except Exception as e:
        print(f"⚠️ Error loading threads: {str(e)}")
    
    if not config['thread_ids']:
        print(f"❌ No valid thread IDs found in {THREAD_FILE}")
        exit(1)
    
    # Load message text with UTF-8 encoding
    try:
        if os.path.exists(MESSAGE_FILE):
            with open(MESSAGE_FILE, 'r', encoding='utf-8') as f:
                config['message_text'] = f.read().strip()[:MAX_MESSAGE_LENGTH]
    except UnicodeDecodeError:
        # Try alternative encoding if UTF-8 fails
        try:
            with open(MESSAGE_FILE, 'r', encoding='utf-16') as f:
                config['message_text'] = f.read().strip()[:MAX_MESSAGE_LENGTH]
        except Exception as e:
            print(f"⚠️ Encoding error: {str(e)}")
    except Exception as e:
        print(f"⚠️ Error loading message: {str(e)}")
    
    if not config['message_text']:
        print(f"❌ Message content missing in {MESSAGE_FILE}")
        exit(1)
    
    return config

def setup_client(session_id):
    """Initialize and authenticate client using session ID"""
    cl = Client()
    cl.request_timeout = 30
    
    # Try to load existing session or create new
    if os.path.exists(SESSION_FILE):
        try:
            cl.load_settings(SESSION_FILE)
            # Verify session is still valid
            cl.get_timeline_feed()
            print("✅ Session loaded successfully")
            return cl
        except (ClientLoginRequired, ChallengeRequired, LoginRequired):
            print("⚠️ Session expired, re-authenticating with session ID...")
    else:
        print("⚠️ No session file found, authenticating with session ID...")
    
    try:
        cl.login_by_sessionid(session_id)
        cl.dump_settings(SESSION_FILE)
        print("✅ Login successful! Session saved")
        return cl
    except (ChallengeRequired, ClientLoginRequired) as e:
        print(f"❌ Authentication failed: {str(e)}")
        print("⚠️ Manual login might be required through Instagram app")
        exit(1)
    except Exception as e:
        print(f"🚨 Login error: {traceback.format_exc()}")
        exit(1)

def send_message(cl, message, thread_id, attempt=1):
    """Send message with enhanced error recovery"""
    try:
        cl.direct_send(message, thread_ids=[thread_id])
        return True
    except (FeedbackRequired, SentryBlock, PleaseWaitFewMinutes) as e:
        if attempt <= MAX_RETRIES:
            wait = 120 * attempt
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

def main():
    print("\n🚀 Instagram Group Promotion Bot")
    print("----------------------------------")
    
    config = load_config()
    print(f"• Loaded session ID from '{SESSION_ID_FILE}'")
    print(f"• Loaded {len(config['thread_ids'])} thread IDs")
    print(f"• Message: {config['message_text'][:50]}...")
    
    cl = setup_client(config['session_id'])
    
    print("\n⚙️ Settings:")
    print(f"• Message delay: {DELAY_RANGE[0]}-{DELAY_RANGE[1]}s")
    print(f"• Cycle delay: {CYCLE_DELAY}s")
    print(f"• Press Ctrl+C to stop anytime\n")
    print("----------------------------------")
    
    cycle = 0
    try:
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
            
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped by user")
    except Exception as e:
        print(f"🔥 Critical error: {traceback.format_exc()}")
        cl.dump_settings(SESSION_FILE)
        print(f"💾 Session saved to {SESSION_FILE}")

if __name__ == "__main__":
    main()