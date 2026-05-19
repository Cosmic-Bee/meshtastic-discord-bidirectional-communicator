import os
import sys
from dotenv import load_dotenv

load_dotenv()

# --- Credentials ---
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
TARGET_CHANNEL_ID_STR = os.getenv("TARGET_CHANNEL_ID")
CHANNEL_KEY_BASE64 = os.getenv("CHANNEL_KEY_BASE64", "AQ==")
FIRMS_MAP_KEY = os.getenv("FIRMS_MAP_KEY")

if not DISCORD_BOT_TOKEN or not TARGET_CHANNEL_ID_STR:
    print("❌ Error: Missing credentials. Please check your .env file.")
    sys.exit(1)

TARGET_CHANNEL_ID = int(TARGET_CHANNEL_ID_STR)

# --- External APIs ---
LEMONADE_URL = "http://127.0.0.1:13305/v1"
MODEL_NAME = "user.gemma_4_finetune-gemma-4-31b.Q8_0.gguf"

# --- MQTT Specs ---
MQTT_BROKER = "mqtt.meshtastic.org"
MQTT_PORT = 1883
MQTT_USER = "meshdev"
MQTT_PASS = "large4cats"
MQTT_TOPIC = "msh/US/2/e/BumbleBee/#"
VIRTUAL_GATEWAY_NODE_ID = 3999999999 

# --- Timing Constants (Seconds) ---
GPS_VALIDITY_WINDOW = 1800          
UNACTIVATED_REAP_WINDOW = 1200      
ABSOLUTE_SUBSCRIPTION_EXPIRY = 14400 
HEARTBEAT_INTERVAL = 60

SEEN_PACKETS = set()
MAX_CACHE_SIZE = 100