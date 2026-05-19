import os
import json
import re
import asyncio
import sys
import time
import random
import base64
import requests
import discord
from openai import OpenAI
import paho.mqtt.client as mqtt
import paho.mqtt.publish as publish
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from meshtastic.protobuf import mqtt_pb2, mesh_pb2

from audio import generate_speech
from config import *
from database import EmergencyDB
from telemetry import check_emergency_apis
from crypto import decrypt_packet

ai_client = OpenAI(base_url=LEMONADE_URL, api_key="lemonade")
intents = discord.Intents.default()
intents.message_content = True
discord_client = discord.Client(intents=intents)

main_async_loop = None

def sanitize_text(text):
    if not text: return ""
    return re.sub(r'[^\x20-\x7E]', '', text).strip()

def hex_to_int(hex_str):
    if hex_str.startswith('!'):
        return int(hex_str[1:], 16)
    return int(hex_str, 16)

async def dispatch_to_discord_channel(content):
    channel = discord_client.get_channel(TARGET_CHANNEL_ID)
    if channel:
        await channel.send(content)

def forward_to_mqtt_pipeline(text_message, target_node_int=4294967295):
    packet = mesh_pb2.MeshPacket()
    setattr(packet, 'from', VIRTUAL_GATEWAY_NODE_ID)
    packet.to = target_node_int 
    setattr(packet, 'id', random.randint(1000000000, 2000000000)) 
    packet.channel = 122
    packet.want_ack = False
    packet.hop_limit = 3
    packet.rx_time = int(time.time()) 
    
    data_payload = mesh_pb2.Data()
    data_payload.portnum = 1 
    data_payload.payload = text_message.encode('utf-8')
    unencrypted_bytes = data_payload.SerializeToString()
    
    key_bytes = base64.b64decode(CHANNEL_KEY_BASE64.encode('ascii'))
    
    packet_id_bytes = getattr(packet, "id").to_bytes(8, "little")
    from_node_bytes = getattr(packet, "from").to_bytes(8, "little")
    nonce = packet_id_bytes + from_node_bytes
    
    cipher = Cipher(algorithms.AES(key_bytes), modes.CTR(nonce), backend=default_backend())
    encryptor = cipher.encryptor()
    encrypted_bytes = encryptor.update(unencrypted_bytes) + encryptor.finalize()
    
    packet.encrypted = encrypted_bytes 
    
    se = mqtt_pb2.ServiceEnvelope()
    se.packet.CopyFrom(packet)
    se.channel_id = "BumbleBee" 
    virtual_node_hex = f"!{VIRTUAL_GATEWAY_NODE_ID:08x}"
    se.gateway_id = virtual_node_hex
    
    target_publish_topic = MQTT_TOPIC.replace("#", virtual_node_hex)
    
    publish.single(
        target_publish_topic, 
        payload=se.SerializeToString(), 
        hostname=MQTT_BROKER, 
        port=MQTT_PORT, 
        auth={'username': MQTT_USER, 'password': MQTT_PASS}
    )
    
    target_log = "Broadcast" if target_node_int == 4294967295 else "Targeted"
    print(f"[INFO] MQTT Egress: {target_log} alert dispatched.")

mesh_outbound_queue = asyncio.Queue()

async def mesh_transmission_worker():
    """Rate-limited egress queue for LoRa transmission, TTY, and Audio."""
    while True:
        node_id, target_node_int, message_text = await mesh_outbound_queue.get()
        try:
            print(f"\n\033[91m[TTY TX] Target: {node_id} | Payload: {message_text}\033[0m\n")
            
            forward_to_mqtt_pipeline(message_text, target_node_int)
            
            if target_node_int == 4294967295:
                await dispatch_to_discord_channel(f"➡️ **Mesh TX:** `{message_text}`")
            else:
                await dispatch_to_discord_channel(f"⚠️ **Alert TX to `{node_id}`:** `{message_text}`")
            
            loop = asyncio.get_running_loop()
            audio_text = f"Base station alert for {node_id}. {message_text}"
            await loop.run_in_executor(None, generate_speech, audio_text)
            
            print("[INFO] Queue: Message dispatched. 15s TX cooldown active.")
            await asyncio.sleep(15) 
            
        except Exception as e:
            print(f"[ERROR] Queue dispatch failed: {e}")
        finally:
            mesh_outbound_queue.task_done()

def parse_mesh_payload(sender_id, raw_text):
    text = sanitize_text(raw_text)
    if not text: return

    if text.startswith("!subscribe"):
        EmergencyDB.add_subscription(sender_id)
        msg = f"**Subscription:** Node `{sender_id}` added to active channel."
    elif text.startswith("!unsubscribe"):
        EmergencyDB.remove_subscription(sender_id)
        msg = f"**Unsubscription:** Node `{sender_id}` removed."
    elif text.startswith("!discord "):
        actual_content = text[9:]
        msg = f"**Mesh RX [{sender_id}]:** `{actual_content}`"
    else:
        print(f"[DEBUG] Ignored standard chatter from {sender_id}")
        return

    pos = EmergencyDB.get_raw_position(sender_id)
    if pos:
        age_seconds = time.time() - pos[2]
        if age_seconds > GPS_VALIDITY_WINDOW:
            msg += f"\n📍 [Map](https://www.google.com/maps?q={pos[0]},{pos[1]}) *(Stale)*"
        else:
            msg += f"\n📍 [Map](https://www.google.com/maps?q={pos[0]},{pos[1]})"

    if main_async_loop:
        asyncio.run_coroutine_threadsafe(dispatch_to_discord_channel(msg), main_async_loop)

def on_connect(client, userdata, flags, reason_code, properties=None):
    if reason_code == 0:
        print(f"[INFO] MQTT Connected. Subscribed to {MQTT_TOPIC}")
        client.subscribe(MQTT_TOPIC)
    else:
        print(f"[ERROR] MQTT connection failed: {reason_code}")

def on_mqtt_message(client, userdata, msg):
    try:
        se = mqtt_pb2.ServiceEnvelope()
        se.ParseFromString(msg.payload)
        
        raw_sender_int = getattr(se.packet, 'from', 0)
        if raw_sender_int == VIRTUAL_GATEWAY_NODE_ID:
            return  
            
        packet_id = getattr(se.packet, 'id', 0)
        if packet_id in SEEN_PACKETS:
            return  
            
        SEEN_PACKETS.add(packet_id)
        if len(SEEN_PACKETS) > MAX_CACHE_SIZE:
            SEEN_PACKETS.pop() 
            
        sender_id = f"!{raw_sender_int:08x}"
        decoded_data = decrypt_packet(se.packet, CHANNEL_KEY_BASE64)
        if not decoded_data:
            return
            
        portnum = decoded_data.portnum

        if portnum == 3:
            pos = mesh_pb2.Position()
            pos.ParseFromString(decoded_data.payload)
            if pos.latitude_i and pos.longitude_i:
                lat = pos.latitude_i / 10000000.0
                lon = pos.longitude_i / 10000000.0
                
                was_valid = EmergencyDB.get_valid_position(sender_id) is not None
                is_subbed = EmergencyDB.is_subscribed(sender_id)
                
                EmergencyDB.update_position(sender_id, lat, lon)
                
                if is_subbed and not was_valid:
                    msg_text = f"**GPS Lock:** Node `{sender_id}` active.\n📍 [Map](https://www.google.com/maps?q={lat},{lon})"
                    if main_async_loop:
                        asyncio.run_coroutine_threadsafe(dispatch_to_discord_channel(msg_text), main_async_loop)

        elif portnum == 1:
            mesh_text = decoded_data.payload.decode('utf-8', errors='ignore')
            parse_mesh_payload(sender_id, mesh_text)

    except Exception as e:
        print(f"[ERROR] Packet processing failed: {e}")

async def heartbeat_monitor():
    await discord_client.wait_until_ready()
    while not discord_client.is_closed():
        try:
            reaped_nodes = EmergencyDB.check_and_reap_subscriptions()
            for node_id in reaped_nodes:
                alert = f"**Expired:** Node `{node_id}` removed from active list."
                await dispatch_to_discord_channel(alert)
                print(f"[INFO] Reaped stale node: {node_id}")

            active_nodes = EmergencyDB.get_all_activated_nodes()
            for node_id, lat, lon in active_nodes:
                alert_payloads = await check_emergency_apis(lat, lon)
                if not alert_payloads:
                    continue

                for alert_item in alert_payloads:
                    alert_hash = alert_item.get("id")
                    if EmergencyDB.has_alert_been_dispatched(node_id, alert_hash):
                        continue

                    inference_item = {
                        "payload": alert_item["payload"],
                        "severity": alert_item["severity"],
                        "type": alert_item["type"]
                    }
                    api_json_response = json.dumps([inference_item])
                    
                    print(f"[DEBUG] Heartbeat API evaluation for {node_id}")
                    
                    messages = [
                        {
                            "role": "system",
                            "content": (
                                "You are an off-grid emergency communications router. You ingest telemetry, "
                                "verify hazards, and output structured JSON. CRITICAL: If you decide to send an alert, "
                                "set 'send_alert' to true and provide a 'message' string destined for the mesh network "
                                "that is strictly under 140 characters, clear, and highly compressed using standard "
                                "tactical abbreviations (e.g., rpt, poss, sys, rgr). If no immediate tactical action is "
                                "required (such as a future watch), set 'send_alert' to false."
                            )
                        },
                        {
                            "role": "user",
                            "content": (
                                f"Analyze this telemetry batch for GPS {lat}, {lon}. "
                                f"Live emergency API data received: {api_json_response}"
                            )
                        }
                    ]

                    loop = asyncio.get_event_loop()
                    response = await loop.run_in_executor(
                        None, lambda: ai_client.chat.completions.create(
                            model=MODEL_NAME,
                            messages=messages,
                            temperature=0.0,
                            max_tokens=150,
                            response_format={"type": "json_object"} 
                        )
                    )
                    model_output = response.choices[0].message.content.strip()
                    
                    print(f"[DEBUG] LLM Decision Output:\n{model_output}")
                    
                    try:
                        json_match = re.search(r'\{.*\}', model_output, re.DOTALL)
                        if json_match:
                            alert_data = json.loads(json_match.group(0))
                        else:
                            alert_data = json.loads(model_output)

                        if "arguments" in alert_data:
                            args = alert_data["arguments"]
                            if isinstance(args, str):
                                args = json.loads(args)
                            send_alert = args.get("send_alert")
                            alert_msg = args.get("message", "EMERGENCY ALERT")
                        else:
                            send_alert = alert_data.get("send_alert")
                            alert_msg = alert_data.get("message", "EMERGENCY ALERT")

                        if send_alert:
                            node_int = hex_to_int(node_id)
                            await mesh_outbound_queue.put((node_id, node_int, alert_msg))
                            EmergencyDB.mark_alert_dispatched(node_id, alert_hash)
                            
                    except json.JSONDecodeError:
                        print("[ERROR] Failed to parse JSON from LLM output.")
                    
        except Exception as e:
            print(f"[ERROR] Heartbeat loop: {e}")
            
        await asyncio.sleep(HEARTBEAT_INTERVAL)

@discord_client.event
async def on_ready():
    global main_async_loop
    main_async_loop = asyncio.get_running_loop()
    print(f"[INFO] Discord connected as {discord_client.user}")
    
    discord_client.loop.create_task(heartbeat_monitor())
    discord_client.loop.create_task(mesh_transmission_worker())
    
    channel = discord_client.get_channel(TARGET_CHANNEL_ID)
    if channel:
        await channel.send("**System Online.** MQTT Bridge, AES cipher, and heartbeat active.")

@discord_client.event
async def on_message(message):
    if message.author == discord_client.user or message.channel.id != TARGET_CHANNEL_ID:
        return

    sanitized = sanitize_text(message.content)
    if not sanitized: return

    raw_prompt = (
        "<|turn>system\n"
        "You are an off-grid emergency communications router. You ingest telemetry and community feeds, "
        "use local tools to verify hazards, and output structured JSON. CRITICAL: Every broadcast message "
        "destined for the mesh network must be strictly under 140 characters, clear, and highly compressed "
        "using standard tactical abbreviations.<turn|>\n"
        "<|turn>user\n"
        f"Prepare telegram message for transmission: \"{message.author.display_name}: {sanitized}\"<turn|>\n"
        "<|turn>model\n"
    )

    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(
        None, lambda: ai_client.completions.create(
            model=MODEL_NAME, prompt=raw_prompt, max_tokens=100, temperature=0.0, stop=["<turn|>", "<|turn>"]
        )
    )
    model_output = response.choices[0].text.strip()
    
    try:
        alert_data = json.loads(model_output)
        if alert_data.get("message"):
            await mesh_outbound_queue.put(("GLOBAL", 4294967295, alert_data["message"]))
    except Exception as e:
        print(f"[ERROR] Discord trigger JSON failure: {e}")
        await message.channel.send(f"**TX Failed:** {e}")

if __name__ == "__main__":
    EmergencyDB.init()

    try:
        mqtt_sub = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    except AttributeError:
        mqtt_sub = mqtt.Client() 
        
    mqtt_sub.username_pw_set(MQTT_USER, MQTT_PASS)
    mqtt_sub.on_connect = on_connect
    mqtt_sub.on_message = on_mqtt_message
    
    mqtt_sub.connect(MQTT_BROKER, MQTT_PORT, 60)
    mqtt_sub.loop_start()

    try:
        discord_client.run(DISCORD_BOT_TOKEN)
    except Exception as e:
        print(f"[FATAL] Core fail: {e}")