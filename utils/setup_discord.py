#!/usr/bin/env python3
"""
Discord Bot Setup Helper

This script helps you set up your Discord bot properly with environment variables.
"""

import os
import sys

def create_env_file():
    """Create a .env file with Discord bot configuration."""
    print("🤖 Discord Bot Setup Helper")
    print("=" * 40)
    print()
    
    # Check if .env already exists
    if os.path.exists('.env'):
        overwrite = input("⚠️  .env file already exists. Overwrite? (y/n): ").strip().lower()
        if overwrite != 'y':
            print("Setup cancelled.")
            return
    
    print("📋 Please provide the following information from Discord Developer Portal:")
    print("   (https://discord.com/developers/applications)")
    print()
    
    # Get bot token
    token = input("🔑 Bot Token (from Bot tab > Reset Token): ").strip()
    if not token:
        print("❌ Bot token is required!")
        return
    
    # Optional settings
    print("\n📍 Optional Settings (press Enter to skip):")
    guild_id = input("   Server ID (to restrict bot to specific server): ").strip()
    channel_id = input("   Channel ID (to restrict bot to specific channel): ").strip()
    
    # Create .env content
    env_content = f"""# Discord Bot Configuration
DISCORD_BOT_TOKEN={token}
"""
    
    if guild_id:
        env_content += f"GUILD_ID={guild_id}\n"
    
    if channel_id:
        env_content += f"CHANNEL_ID={channel_id}\n"
    
    env_content += """
# Database Configuration (uncomment for cloud deployment)
# DATABASE_URL=postgresql://user:pass@host:5432/dbname

# OCR Configuration (uncomment if tesseract not in PATH)  
# TESSERACT_PATH=/usr/local/bin/tesseract
"""
    
    # Write .env file
    try:
        with open('.env', 'w') as f:
            f.write(env_content)
        
        print("\n✅ .env file created successfully!")
        print("\n🔒 Security Note:")
        print("   - Never commit the .env file to Git!")
        print("   - Add '.env' to your .gitignore file")
        print()
        
        # Create .gitignore if it doesn't exist
        create_gitignore()
        
        print("📋 Next Steps:")
        print("   1. Invite your bot to Discord server using this URL:")
        
        # Extract client ID from token (first part before first dot)
        try:
            import base64
            # Bot tokens are base64 encoded, first part is the client ID
            client_id = token.split('.')[0]
            client_id = base64.b64decode(client_id + '==').decode('utf-8')
            invite_url = f"https://discord.com/api/oauth2/authorize?client_id={client_id}&permissions=274877967360&scope=bot"
            print(f"      {invite_url}")
        except:
            print("      https://discord.com/api/oauth2/authorize?client_id=YOUR_CLIENT_ID&permissions=274877967360&scope=bot")
            print("      (Replace YOUR_CLIENT_ID with your Application ID)")
        
        print("\n   2. Run the bot:")
        print("      python bot.py")
        print("\n   3. Upload a Mario Kart results image to test!")
        
    except Exception as e:
        print(f"❌ Error creating .env file: {e}")

def create_gitignore():
    """Create or update .gitignore to include .env file."""
    gitignore_entries = [
        ".env",
        "*.db",
        "__pycache__/",
        "*.pyc",
        "*.log",
        "table_presets.json",
        "temp_roi_*.png"
    ]
    
    existing_entries = set()
    if os.path.exists('.gitignore'):
        with open('.gitignore', 'r') as f:
            existing_entries = set(line.strip() for line in f.readlines())
    
    new_entries = [entry for entry in gitignore_entries if entry not in existing_entries]
    
    if new_entries:
        with open('.gitignore', 'a') as f:
            f.write('\n# Mario Kart Bot\n')
            for entry in new_entries:
                f.write(f'{entry}\n')
        print("✅ .gitignore updated with security entries")

def show_invite_url():
    """Show bot invite URL."""
    print("🔗 Bot Invite URL Generator")
    print("=" * 30)
    
    client_id = input("Enter your Bot's Client ID (from General Information tab): ").strip()
    if not client_id:
        print("❌ Client ID is required!")
        return
    
    permissions = "274877967360"  # Calculated permissions for our bot
    invite_url = f"https://discord.com/api/oauth2/authorize?client_id={client_id}&permissions={permissions}&scope=bot"
    
    print(f"\n🎯 Invite URL:")
    print(f"   {invite_url}")
    print("\n📋 This URL gives your bot these permissions:")
    print("   • Read Messages")
    print("   • Send Messages") 
    print("   • Manage Messages")
    print("   • Embed Links")
    print("   • Attach Files")
    print("   • Add Reactions")
    print("   • Read Message History")

def main():
    if len(sys.argv) > 1 and sys.argv[1] == "invite":
        show_invite_url()
    else:
        create_env_file()

if __name__ == "__main__":
    main() 