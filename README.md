# Meshtastic Emergency Communicator

This repository sets up a meshtastic emergency communicator node. It uses discord for bidirectional communication for alerts and provides the ability to subscribe to emergency feeds based on the user's GPS position data. 

[Video Demo](https://youtu.be/5cE8dATKnr8)

## Setup

If using ROCM ensure you install the latest version:
Install ROCM following AMD guide https://rocm.docs.amd.com/projects/install-on-linux/en/latest/install/install-methods/package-manager/package-manager-ubuntu.html#install-kernel-driver

Install text to speech software:
```
sudo apt-get install espeak-ng mpv -y
sudo usermod -a -G dialout $USER
sudo reboot
```

Add the Lemonade stable PPA:
```
sudo add-apt-repository ppa:lemonade-team/stable
sudo apt update
sudo apt install lemonade-server
```

Install SQLite for DB purposes:
```
sudo apt install sqlite3
```

For ROCM use the backend install:
```
lemonade backends install vllm:rocm
```
Note: it failed for me the first time I ran but worked on a subsequent run with the cached files on disk from the first

Install my Meshtastic finetune of Gemma 4 and Kokoro-v1:
```
lemonade pull CosmicBee/gemma_4_finetune:gemma-4-31b.Q8_0.gguf
lemonade run user.gemma_4_finetune-gemma-4-31b.Q8_0.gguf --ctx-size 32768
lemonade run kokoro-v1
```

Pull the repo and CD into it:
```
git clone git@github.com:Cosmic-Bee/lemon-mesh-emergency-communicator.git
cd lemon-mesh-emergency-communicator
```

Create the virtual environment and activate it:
```
python3 -m venv venv
source venv/bin/activate
```

Install pip dependencies:
```
pip install -r requirements.txt
```

Set the volume up for TTY purposes:
```
amixer sset Master 100%
amixer sset PCM 100%
```

### Setup Discord Bot:

- Create the App: Go to the Discord Developer Portal, click New Application, and name it.
- Enable Intents: Go to the Bot tab on the left. Scroll down to Privileged Gateway Intents and turn Message Content Intent to ON. Save changes.
- Get Your Token: On that same Bot tab, click Reset Token, copy the string, and save it.
- Invite the Bot: Go to OAuth2 -> URL Generator.
    -- Check bot.
    -- Under Bot Permissions, check View Channels, Send Messages, and Read Message History (Integer: 68608).
    -- Copy the URL at the bottom, paste it into your browser, and invite the bot to your server.
- Get Channel ID: In your Discord app settings, go to Advanced -> turn ON Developer Mode. Right-click your target text channel and select Copy Channel ID.

Use those to setup the .env values (see .example.env, copy to .env, and set):
```
DISCORD_BOT_TOKEN=
TARGET_CHANNEL_ID=
```

### Setup FIRMS key:

Get a FIRMS key by signing up for the service: https://firms.modaps.eosdis.nasa.gov/api/map_key/

```
FIRMS_MAP_KEY=
```

### Setup Meshtastic Channel Encrypted Key:

Get the encrypted key from Meshtastic after creating a private channel.

You'll need to:
- Setup a meshtastic node with the software
- Once connected over bluetooth with your device you'll need to connect to your WiFi network
- As the device will struggle to connect to both you'll switch to WiFi as the configuration mode when it comes back online
- Under LoRa you'll need to enable "Ok to MQTT" and "Transmit Enabled"
- On the channels screen you'll want to create a new channel called "BumbleBee" and ensure it's on the 0 channel ID
- Here you can get the PSK value you'll use for the .env but you'll also want to set uplink enabled, downlink enabled, position enabled, and precision location
- Once the channel has been added ensure you move it to the first position
- After this you'll need to go into MQTT config and enable it, enable encryption

```
CHANNEL_KEY_BASE64=
```

## Actions

- !subscribe: Adds the user to the subscription of emergency state notifications
- !unsubscribe: Removes the user from the subscription of emergency state notifications
- !discord [message]: Sends message to discord channel setup
