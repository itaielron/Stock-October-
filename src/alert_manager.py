import subprocess

def send_imessage(phone_number: str, message: str):
    """
    Sends an iMessage using macOS native AppleScript.
    This runs completely locally and for free on your Mac.
    """
    apple_script = f'''
    tell application "Messages"
        set targetService to 1st service whose service type = iMessage
        set targetBuddy to buddy "{phone_number}" of targetService
        send "{message}" to targetBuddy
    end tell
    '''
    try:
        subprocess.run(["osascript", "-e", apple_script], check=True, capture_output=True)
        print(f"Phone alert successfully sent to {phone_number}")
    except subprocess.CalledProcessError as e:
        print(f"Failed to send phone alert: {e.stderr.decode('utf-8')}")

def send_discord_message(content: str):
    """
    Sends a message to the specific Discord channel 'jacksonaiforrealz' in 'The Truffle-Pig Pen'.
    Uses the bot token found in your previous projects.
    """
    import requests
    
    # Split message into 2000 character chunks (Discord limit)
    chunks = [content[i:i+1950] for i in range(0, len(content), 1950)]
    
    token = 'YOUR_DISCORD_TOKEN_HERE'
    channel_id = '1469448171108171899'
    url = f'https://discord.com/api/v10/channels/{channel_id}/messages'
    
    headers = {
        'Authorization': f'Bot {token}',
        'Content-Type': 'application/json'
    }
    
    try:
        for chunk in chunks:
            response = requests.post(url, json={'content': chunk}, headers=headers)
            response.raise_for_status()
        print(f"Discord alert successfully forwarded to jacksonaiforrealz!")
    except Exception as e:
        print(f"Failed to send Discord alert: {e}")
