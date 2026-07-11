import discord
from discord.ext import commands, tasks
from discord import ui, app_commands
import asyncio
import datetime
import re
import os
import json
import random
import string
import aiohttp
import xml.etree.ElementTree as ET


TOKEN = "replace bot token here"         
GEMINI_API_KEY = "replace gemini ai api key here"     
PREFIX = "!"


# === AUTHORIZED USERS (Correct IDs to be filled by User) ===
AUTHORIZED_IDS = [
    "REPLACE YOUR USERID", # User 1
]

def is_authorized(user_id: int) -> bool:
    """Check if a user is in the strictly authorized list."""
    return user_id in AUTHORIZED_IDS



intents = discord.Intents.all()
intents.message_content = True
intents.members = True 
intents.guilds = True  

def get_prefix(bot, message):
    if not message.guild:
        return PREFIX
    return global_data.get("prefixes", {}).get(str(message.guild.id), PREFIX)

bot = commands.Bot(command_prefix=get_prefix, intents=intents, help_command=None)

SOURCE_GUILD_ID = "MAIN SERVER ID""
DEST_GUILD_ID = "LOGS SERVER ID"

LOG_CHANNELS_CONFIG = {
    "ban-logs": "Bans and Unbans",
    "kick-logs": "Kicks",
    "message-edit-logs": "Message Edits",
    "message-delete-logs": "Message Deletions",
    "member-join-logs": "Member Joins",
    "member-leave-logs": "Member Leaves",
    "role-update-logs": "Role Changes",
    "nickname-change-logs": "Nickname Updates",
    "voice-logs": "Voice Channel Activity",
    "report-logs": "User Reports",
    "moderation-logs": "General Moderation Actions",
    "audit-logs": "Full Audit Log Synchronization",
    "mass-action-logs": "Mass Action & Anti-Raid Alerts",
    "message-clone-logs": "Real-Time Message Mirror",
    "bot-add-logs": "Bot Addition Alerts",
    "server-settings-logs": "Server Setting Guards",
    "invite-logs": "Invite Activity & Tracking",
    "ai-security-logs": "AI Behavior & Pattern Detection",
    "permission-audit-logs": "Daily Security & Permission Reports",
    "promotion-logs": "Rank Promotions and Demotions"
}

# Constants for Roles
MOD_ROLE_ID = "REPLACE MOD ROLE ID"
MOD_ROLE_LOW_ID = "REPLACE MOD ROLE LOW ID"
GOVERNOR_ROLE_ID = "REPLACE GOVERNOR ROLE ID"

class MassActionMonitor:
    def __init__(self, bot):
        self.bot = bot
        # Format: {guild_id: {user_id: {action_type: [timestamps]}}}
        self.tracking = {}
        self.default_thresholds = {
            "ban": 2,
            "kick": 2,
            "channel_delete": 3,
            "channel_create": 3,
            "role_delete": 3,
            "role_update": 3,
            "bot_add": 2,
            "invite_create": 3,
            "server_update": 1
        }
        self.window = 300 # 5 minutes

    async def track_action(self, guild, user, action_type):
        # NO WHITELIST - Applies to all users (Zero-Trust Enforcement)
        
        guild_id = str(guild.id)
        user_id = str(user.id)
        now = discord.utils.utcnow().timestamp()

        self.tracking.setdefault(guild_id, {}).setdefault(user_id, {}).setdefault(action_type, [])
        
        # Add new action and cleanup old ones
        self.tracking[guild_id][user_id][action_type].append(now)
        self.tracking[guild_id][user_id][action_type] = [
            t for t in self.tracking[guild_id][user_id][action_type] if now - t < self.window
        ]

        count = len(self.tracking[guild_id][user_id][action_type])
        
        # Load configurable threshold
        custom_thresholds = global_data.get("mass_action_thresholds", {}).get(guild_id, {})
        threshold = custom_thresholds.get(action_type, self.default_thresholds.get(action_type, 3))

        print(f"[MASS-ACTION] Tracking {action_type} for {user.name}: {count}/{threshold}")

        if count >= threshold:
            await self.trigger_punishment(guild, user, action_type, count)
            return True
        
        # Integrate with AI analyzer for cross-action pattern detection
        await ai_analyzer.analyze_action(guild, user, action_type)
        
        return False

    async def trigger_punishment(self, guild, user, action_type, count):
        """Immediately strips all roles/permissions from the user."""
        try:
            # 1. Strip all roles
            # We must be careful not to trigger more audit log events that loop back
            # But usually role removals are different action types.
            
            # Save roles in case of false positive / manual restore
            roles_to_remove = [r for r in user.roles if r != guild.default_role and r < guild.me.top_role]
            
            await user.edit(roles=[], reason=f"Mass Action Detected: {count} {action_type} in 5min.")
            
            # 2. Assign punishment role if exists
            punish_role_name = "AutoMod Punished"
            punish_role = discord.utils.get(guild.roles, name=punish_role_name)
            if not punish_role:
                try:
                    punish_role = await guild.create_role(name=punish_role_name, color=discord.Color.dark_red(), reason="Anti-Raid Setup")
                    await punish_role.edit(permissions=discord.Permissions.none())
                except: pass
            
            if punish_role:
                await user.add_roles(punish_role)

            # 3. Log to Global System
            embed = discord.Embed(
                title="🚨 MASS ACTION DETECTED - RAID PROTECTION",
                description=f"**User:** {user.mention} (`{user.id}`)\n**Action:** `{action_type}`\n**Count:** `{count}`\n**Window:** `5 Minutes`",
                color=discord.Color.red(),
                timestamp=discord.utils.utcnow()
            )
            embed.add_field(name="Punishment Applied", value="✅ All roles stripped\n✅ Administrator permissions removed\n✅ Punishment Role Assigned\n✅ Monitoring locked")
            add_branding(embed)
            
            await log_transfer.forward("mass-action-logs", embed)
            
            # Also log to local monitor if configured
            await log_monitor_event(guild, "🚨 RAID PROTECTION TRIGGERED", f"User {user.mention} has been stripped for mass {action_type}.", discord.Color.red())

        except Exception as e:
            print(f"[MASS-ACTION] Failed to punish user {user.id}: {e}")

mass_monitor = MassActionMonitor(bot)

class AISecurityAnalyzer:
    def __init__(self, bot):
        self.bot = bot
        self.risk_scores = {} # {guild_id: {user_id: score}}
        self.threshold = 10
        self.action_weights = {
            "ban": 5,
            "kick": 4,
            "channel_delete": 3,
            "role_delete": 4,
            "server_update": 8,
            "bot_add": 7,
            "invite_create": 2
        }

    async def analyze_action(self, guild, user, action_type):
        guild_id = str(guild.id)
        user_id = str(user.id)
        
        # Increase risk score
        weight = self.action_weights.get(action_type, 1)
        self.risk_scores.setdefault(guild_id, {}).setdefault(user_id, 0)
        self.risk_scores[guild_id][user_id] += weight
        
        score = self.risk_scores[guild_id][user_id]
        
        # Log suspected patterns if score is climbing
        if score >= 5:
            embed = discord.Embed(
                title="🧠 AI Security Analyzer - Pattern Detected",
                description=f"**User:** {user.mention} (`{user.id}`)\n**Detected Pattern:** Rapid high-impact actions\n**Current Risk Score:** `{score}/{self.threshold}`",
                color=discord.Color.orange(),
                timestamp=discord.utils.utcnow()
            )
            embed.add_field(name="Recent Action", value=f"`{action_type}` (Weight: {weight})")
            add_branding(embed)
            await log_transfer.forward("ai-security-logs", embed)

        # Trigger mass protection if threshold exceeded
        if score >= self.threshold:
            # Trigger full raid protection
            await mass_monitor.trigger_punishment(guild, user, "AI_Pattern_Detection", score)
            
            # Reset score after punishment
            self.risk_scores[guild_id][user_id] = 0
            
            # Critical Log
            embed = discord.Embed(
                title="🚨 AI SECURITY TRIGGER - CRITICAL RISK",
                description=f"**User:** {user.mention} (`{user.id}`)\n**Reason:** Abnormal behavior pattern matching raid signature.\n**Final Score:** `{score}`",
                color=discord.Color.dark_red(),
                timestamp=discord.utils.utcnow()
            )
            embed.add_field(name="Automatic Response", value="✅ Intelligence-Based Lockdown\n✅ User Permissions Neutralized")
            add_branding(embed)
            await log_transfer.forward("ai-security-logs", embed)

    async def decay_scores(self):
        """Periodically reduce risk scores to ignore old behavior."""
        while not self.bot.is_closed():
            await asyncio.sleep(60) # Every minute
            for gid in self.risk_scores:
                for uid in list(self.risk_scores[gid].keys()):
                    self.risk_scores[gid][uid] = max(0, self.risk_scores[gid][uid] - 1)

ai_analyzer = AISecurityAnalyzer(bot)

class PermissionDriftAuditor:
    def __init__(self, bot):
        self.bot = bot
        self.dangerous_perms = [
            'administrator',
            'manage_guild',
            'manage_roles',
            'manage_channels',
            'ban_members',
            'kick_members',
            'manage_webhooks'
        ]

    async def run_audit(self):
        """Scans all guilds for permission drift and sends reports."""
        for guild in self.bot.guilds:
            # Skip guilds we don't need to audit if needed, but for now scan all
            
            admin_users = []
            manage_server_users = []
            risky_roles = []
            
            # Scan Members
            for member in guild.members:
                if member.bot: continue
                if member.guild_permissions.administrator:
                    admin_users.append(f"{member.mention} (`{member.id}`)")
                elif member.guild_permissions.manage_guild:
                    manage_server_users.append(f"{member.mention} (`{member.id}`)")
            
            # Scan Roles
            for role in guild.roles:
                if role.is_default(): continue
                perms = []
                for p_name in self.dangerous_perms:
                    if getattr(role.permissions, p_name):
                        perms.append(p_name.replace("_", " ").title())
                
                if perms:
                    risky_roles.append(f"**{role.name}**: {', '.join(perms)}")

            # Prepare Report
            embed = discord.Embed(
                title=f"📋 DAILY SECURITY AUDIT - {guild.name}",
                description=f"Automated scan for 'Permission Creep' and unauthorized elevations.",
                color=discord.Color.dark_grey(),
                timestamp=discord.utils.utcnow()
            )
            
            embed.add_field(name="👑 Administrators", value="\n".join(admin_users[:15]) or "None Detected", inline=False)
            embed.add_field(name="🛠️ Manage Server Access", value="\n".join(manage_server_users[:15]) or "None Detected", inline=False)
            embed.add_field(name="⚠️ Dangerous Roles", value="\n".join(risky_roles[:10]) or "No risky roles identified", inline=False)
            
            embed.set_footer(text="Permission Drift Auditor • 24h Intelligence Cycle")
            add_branding(embed)
            
            await log_transfer.forward("permission-audit-logs", embed)

    async def audit_loop(self):
        """Infinite loop to run audit every 24 hours."""
        while not self.bot.is_closed():
            # Wait 24 hours (86400 seconds)
            # For testing or initial run, we can run once then wait
            await self.run_audit()
            await asyncio.sleep(86400)

perm_auditor = PermissionDriftAuditor(bot)

class YouTubeMonitor:
    def __init__(self, bot):
        self.bot = bot
        self.session = None

    async def get_latest_video(self, channel_id):
        url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
        if not self.session:
            self.session = aiohttp.ClientSession()
        
        try:
            async with self.session.get(url, timeout=10) as resp:
                if resp.status != 200:
                    return None
                xml_text = await resp.text()
                root = ET.fromstring(xml_text)
                
                # Namespace handling for RSS XML
                ns = {'atom': 'http://www.w3.org/2005/Atom', 'yt': 'http://www.youtube.com/xml/schemas/2015'}
                entry = root.find('atom:entry', ns)
                if entry is None:
                    return None
                
                video_id = entry.find('yt:videoId', ns).text
                title = entry.find('atom:title', ns).text
                return {"id": video_id, "title": title}
        except Exception as e:
            # Minimal logging to save resources
            return None

    async def monitor_loop(self):
        await self.bot.wait_until_ready()
        print("[YOUTUBE-MONITOR] Intelligence Loop Active.")
        while not self.bot.is_closed():
            try:
                yt_config = global_data.get("youtube_notifications", {})
                for guild_id_str, config in yt_config.items():
                    guild = self.bot.get_guild(int(guild_id_str))
                    if not guild: continue
                    
                    notify_channel_id = config.get("channel_id")
                    if not notify_channel_id: continue
                    
                    target_channel = guild.get_channel(notify_channel_id)
                    if not target_channel: continue
                    
                    creators = config.get("creators", {})
                    for yt_channel_id, data in creators.items():
                        latest = await self.get_latest_video(yt_channel_id)
                        if latest:
                            # Primary Check: If we've already notified for this video ID recently
                            processed = data.get("processed_videos", [])
                            # Backward compatible check for single last_video_id
                            if latest["id"] == data.get("last_video_id") or latest["id"] in processed:
                                continue
                                
                            video_url = f"https://www.youtube.com/watch?v={latest['id']}"
                            creator_name = data.get("name", "Unknown")
                            video_title = latest.get("title", "Unknown Title")
                            
                            template = global_data.get("youtube_templates", {}).get(guild_id_str)
                            if template:
                                msg = template.replace("{name}", creator_name).replace("{title}", video_title).replace("{url}", video_url)
                            else:
                                msg = f"🚨 **NEW VIDEO FROM {creator_name}!**\n{video_url}\n@everyone"
                                
                            try:
                                await target_channel.send(msg)
                            except: pass
                            
                            data["last_video_id"] = latest["id"]
                            # Track last 10 videos to prevent duplicates from RSS instability
                            if "processed_videos" not in data:
                                data["processed_videos"] = []
                            if latest["id"] not in data["processed_videos"]:
                                data["processed_videos"].append(latest["id"])
                            
                            # Keep only the last 10 to save memory
                            if len(data["processed_videos"]) > 10:
                                data["processed_videos"] = data["processed_videos"][-10:]
                                
                            await save_data()
                            await asyncio.sleep(2) # Small delay
                
                await asyncio.sleep(600) # 10 minute cycle
            except Exception:
                await asyncio.sleep(60)

yt_monitor = YouTubeMonitor(bot)

class GlobalLogTransfer:
    def __init__(self, bot):
        self.bot = bot
        self.dest_guild = None
        self.channels = {}
        self.webhooks = {} # {channel_name: webhook_url}
        self.queue = asyncio.Queue()
        self.worker_task = None

    async def ensure_setup(self):
        """Ensures the destination guild and channels exist."""
        self.dest_guild = self.bot.get_guild(DEST_GUILD_ID)
        if not self.dest_guild:
            print(f"[LOG-TRANSFER] Error: Could not find destination guild {DEST_GUILD_ID}")
            return False

        # Ensure Category exists
        category_name = "SPG GLOBAL LOGS"
        category = discord.utils.get(self.dest_guild.categories, name=category_name)
        if not category:
            category = await self.dest_guild.create_category(category_name)

        # Ensure individual channels exist
        for channel_name in LOG_CHANNELS_CONFIG.keys():
            channel = discord.utils.get(category.text_channels, name=channel_name)
            if not channel:
                overwrites = {
                    self.dest_guild.default_role: discord.PermissionOverwrite(read_messages=False),
                    self.dest_guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, embed_links=True, manage_webhooks=True)
                }
                channel = await self.dest_guild.create_text_channel(channel_name, category=category, overwrites=overwrites)
                print(f"[LOG-TRANSFER] Created channel: {channel_name}")
            
            self.channels[channel_name] = channel
            
            # Setup Webhook for high-speed delivery
            if channel:
                # Find or Create Webhook
                whs = await channel.webhooks()
                wh = discord.utils.get(whs, name="SPG-Intelligence-Feed")
                if not wh:
                    wh = await channel.create_webhook(name="SPG-Intelligence-Feed", reason="High-speed log mirroring")
                self.webhooks[channel_name] = wh

        # Start the worker task if not running
        if self.worker_task is None or self.worker_task.done():
            self.worker_task = self.bot.loop.create_task(self._process_queue())

        return True

    async def _process_queue(self):
        """Background worker to handle log outflow with rate limit protection."""
        print("[LOG-TRANSFER] Log processor active.")
        while True:
            log_type, embed = await self.queue.get()
            
            # Use Webhook if available (much higher rate limits)
            webhook = self.webhooks.get(log_type)
            channel = self.channels.get(log_type)
            
            try:
                if webhook:
                    await webhook.send(embed=embed, username="SPG Global Intelligence", avatar_url=self.bot.user.display_avatar.url)
                elif channel:
                    await channel.send(embed=embed)
            except discord.HTTPException as e:
                if e.status == 429: # Ratelimit handled by library mostly, but log it
                    print(f"[LOG-TRANSFER] Warning: Hitting ratelimits on {log_type}. Retrying later.")
                    await asyncio.sleep(2) # Extra buffer
                    await self.queue.put((log_type, embed)) # Put back in queue
                else:
                    print(f"[LOG-TRANSFER] Delivery error: {e}")
            except Exception as e:
                print(f"[LOG-TRANSFER] Worker Error: {e}")
            
            # Small delay to ensure we stay under the most aggressive global limits
            await asyncio.sleep(0.5) 
            self.queue.task_done()

    async def forward(self, log_type, embed):
        """Puts a log into the high-speed delivery queue."""
        if not self.dest_guild:
            # We don't await setup here to avoid blocking, 
            # instead we just try to init once or rely on on_ready
            pass

        await self.queue.put((log_type, embed))

log_transfer = GlobalLogTransfer(bot)

DATA_FILE = "data.json"
_storage_lock = asyncio.Lock()  

global_data = {}

# Transient data for rate-limiting
anti_nuke_cache = {} 

chat_stopped_users = set()
snipe_data = {} # Key: channel_id, Value: (content, author_name, timestamp)
start_time = discord.utils.utcnow() 

@tasks.loop(hours=1)
async def server_report_task():
    for guild in bot.guilds:
        modlog = await get_modlog_channel(guild)
        if modlog:
            # Gather quick stats
            bans = 0
            async for _ in guild.bans(limit=10): bans += 1 # Just check if recent bans exist basically
            
            warns_count = sum(1 for uid, count in global_data["warns"].items() if guild.get_member(int(uid)))
            
            try:
                embed = discord.Embed(title="Hourly Server Safety Report", color=discord.Color.green())
                embed.add_field(name="Status", value="✅ **Secure**", inline=False)
                
                # Check bans (handle permissions)
                bans = 0
                if guild.me.guild_permissions.ban_members:
                    async for _ in guild.bans(limit=10): bans += 1
                    embed.add_field(name="Recent Bans", value=f"{bans}+", inline=True)
                else:
                    embed.add_field(name="Recent Bans", value="Unknown (No Perms)", inline=True)
                
                warns_count = sum(1 for uid, count in global_data["warns"].items() if guild.get_member(int(uid)) if uid.isdigit())
                embed.add_field(name="Total Warns Active", value=str(warns_count), inline=True)
                
                embed.add_field(name="Auto-Mod", value="Enabled" if guild.id not in global_data["disabled_automod_guilds"] else "Disabled", inline=True)
                embed.timestamp = discord.utils.utcnow()
                
                await modlog.send(embed=embed)
            except Exception as e:
                print(f"Error in server report for {guild.name}: {e}")

@server_report_task.before_loop
async def before_server_report():
    await bot.wait_until_ready()


def initialize_data_structure(data):
    """Ensures all necessary top-level keys exist in the loaded data."""
    data.setdefault("warns", {})
    data.setdefault("moderator_roles", {})
    data.setdefault("ticket_channels", {})
    data.setdefault("modlog_channels", {})
    data.setdefault("disabled_automod_guilds", set()) 
    data.setdefault("automod_exempt_roles", {})
    data.setdefault("badges", {})
    data.setdefault("blacklist", {})
    data.setdefault("anti_nuke", {})
    data.setdefault("prefixes", {})
    data.setdefault("verification", {})
    data.setdefault("monitor_channels", {})
    data.setdefault("report_channels", {}) # NEW: For user reports
    data.setdefault("server_activity", {}) 
    data.setdefault("bad_words", {}) # NEW: {guild_id: [words]}
    data.setdefault("global_bad_words", []) # NEW: Global bad words list
    data.setdefault("mass_action_thresholds", {}) # NEW: Configurable protection limits

    data.setdefault("afk", {}) # NEW: AFK system
    data.setdefault("applications_open", False) # NEW: Application status
    data.setdefault("ticket_panel_message", {}) # NEW: {guild_id: {channel: id, message: id}}
    data.setdefault("banned_apply_roles", {}) # NEW: Key: guild_id, Value: role_id
    data.setdefault("ticket_categories", {}) # NEW: Key: guild_id, Value: category_id
    data.setdefault("ticket_ping_roles", {}) # NEW: Key: guild_id, Value: [role_id]
    data.setdefault("welcome_channels", {}) # NEW: Key: guild_id, Value: channel_id
    data.setdefault("shifts", {}) # NEW: Shift tracking system
    data.setdefault("official_members", {}) # NEW: Current official members {guild_id: {user_id: data}}
    data.setdefault("official_history", {}) # NEW: History of official/unofficial actions {guild_id: {user_id: [entries]}}
    data.setdefault("required_apply_roles", {}) # NEW: Key: guild_id, Value: role_id
    data.setdefault("promotion_channels", {}) # {guild_id: channel_id}
    data.setdefault("promotion_templates", {}) # {guild_id: {"promote": text, "demote": text}}
    data.setdefault("afk", {}) # {user_id: {"reason": str, "time": timestamp}}
    data.setdefault("youtube_templates", {}) # {guild_id: template_text}
    data.setdefault("auto_replies", {}) # {guild_id: {trigger: response}}
    return data

def _load_json(path):
    if not os.path.exists(path):
        return initialize_data_structure({})
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if "disabled_automod_guilds" in data and isinstance(data["disabled_automod_guilds"], list):
                data["disabled_automod_guilds"] = set(data["disabled_automod_guilds"])
            return initialize_data_structure(data)
    except Exception as e:
        print(f"Error loading {path}: {e}")
        return initialize_data_structure({})

def _save_json(path, data):
    save_data = data.copy()
    # Convert set back to list for JSON serialization
    if "disabled_automod_guilds" in save_data:
        save_data["disabled_automod_guilds"] = list(save_data["disabled_automod_guilds"])

    with open(path, "w", encoding="utf-8") as f:
        json.dump(save_data, f, indent=2, ensure_ascii=False)

global_data = _load_json(DATA_FILE)

user_spam_data = {}
chat_stopped_users = set() # Fix: Initialize chat_stopped_users globally



async def save_data():
    async with _storage_lock:
        _save_json(DATA_FILE, global_data)



# ===== ULTIMATE AUTO MOD SYSTEM =====
# ===== ADVANCED LOCAL AI (NO GEMINI) =====
class LocalAI:
    def __init__(self):
        # Heuristic "Training Data"
        self.toxic_stems = {"bad", "hate", "kill", "stupid", "idiot", "dumb", "ugly", "shut", "die", "trash", "scam",
                            "fuck", "shit", "bitch", "asshole", "bastard", "cunt", "nigga", "nigger", "faggot", "slut", "whore", "dick"} 
        
    def calculate_entropy(self, text):
        """Calculates Shannon entropy to detect random spam."""
        import math
        if not text: return 0
        prob = [text.count(c) / len(text) for c in set(text)]
        return -sum(p * math.log2(p) for p in prob)

    def get_caps_ratio(self, text):
        if not text: return 0
        return sum(1 for c in text if c.isupper()) / len(text)

    def analyze(self, text, extra_bad_words=None):
        """Returns specific violation type or None."""
        text_lower = text.lower()
        
        # 0. Custom Bad Words (Regex Boundary Check)
        if extra_bad_words:
            # Sort by length descending to catch longer phrases first
            for bad_word in sorted(extra_bad_words, key=len, reverse=True):
                # Use regex to match whole words only (prevents "Ofc" matching "f")
                pattern = r'(?:\b|^)' + re.escape(bad_word.lower()) + r'(?:\b|$)'
                if re.search(pattern, text_lower):
                     return f"BAD WORD ({bad_word})"
        
        # 1. Check Entropy (Gibberish)
        if len(text) > 10 and self.calculate_entropy(text) > 4.5:
             if " " not in text: 
                 return "SPAM (Keymash)"

        # 2. Check Caps
        if len(text) > 12 and self.get_caps_ratio(text) > 0.7:
             return "EXCESSIVE CAPS"

        # 3. Anti-Zalgo
        zalgo_chars = [c for c in text if ord(c) > 0x0300 and ord(c) < 0x036F]
        if len(zalgo_chars) > len(text) * 0.3 and len(text) > 10:
             return "ZALGO / GLITCH TEXT"

        # 4. Anti-Invite
        if "discord.gg/" in text_lower or "discord.com/invite/" in text_lower:
             return "UNAUTHORIZED INVITE"

        return None

local_ai = LocalAI()

async def check_gemini_toxicity(text):
    """Checks text using Google Gemini 1.5 Flash API (Free Tier)."""
    if not GEMINI_API_KEY: return None
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    
    payload = {
        "contents": [{
            "parts": [{"text": f"Classify this message for Discord moderation. If it contains Hate Speech, Severe Toxicity, Sexual Content, or Self-Harm, reply 'UNSAFE: <Reason>'. If it is safe, slang, or mild profanity, reply 'SAFE'. Message: '{text}'"}]
        }]
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as resp:
                if resp.status != 200: return None
                data = await resp.json()
                
                # Parse Response
                try:
                    result = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                    if result.upper().startswith("UNSAFE"):
                        return result.replace("UNSAFE:", "").strip()
                except:
                    pass
    except:
        pass
    return None

async def check_huggingface_toxicity(text):
    """
    Checks toxicity using the Open Source 'unitary/multilingual-toxic-xlm-roberta' model
    hosted on Hugging Face's public inference API.
    """
    api_url = "https://api-inference.huggingface.co/models/unitary/multilingual-toxic-xlm-roberta"
    # Note: Public API is rate-limited. For production, add 'Authorization': 'Bearer YOUR_HF_TOKEN' header.
    headers = {} 
    
    payload = {"inputs": text}
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(api_url, headers=headers, json=payload) as resp:
                if resp.status != 200: 
                    return None # API busy or down
                
                data = await resp.json()
                # Expected format: [[{'label': 'toxic', 'score': 0.99}, ...]]
                if isinstance(data, list) and len(data) > 0 and isinstance(data[0], list):
                    for result in data[0]:
                        if result['label'] == 'toxic' and result['score'] > 0.85:
                             return f"AI DETECTED (Strict): {result['label']} ({int(result['score']*100)}%)"
                        # XLM-RoBERTa labels might be different (e.g. toxicity, severe_toxicity)
                        # Actually 'unitary' model usually outputs:
                        # [{'label': 'toxicity', 'score': ...}, {'label': 'severe_toxicity', ...}]
                        if result['score'] > 0.90:
                            return f"AI DETECTED: {result['label']}"
    except:
        pass
    return None

class AutoModSystem:
    def __init__(self):
        self.message_cache = {} 

    async def check_toxicity(self, message):
        # 1. Strict Local Check (Fastest)
        bad_words = global_data.get("global_bad_words", []).copy()
        if message.guild:
             bad_words.extend(global_data.get("bad_words", {}).get(str(message.guild.id), []))
        
        local_result = local_ai.analyze(message.content, bad_words)
        if local_result: return local_result

        # Skip AI for very short messages to save limits
        if len(message.content) < 4: return None

        # 2. Open Source AI (Hugging Face - Multilingual)
        hf_result = await check_huggingface_toxicity(message.content)
        if hf_result: return hf_result

        # 3. Gemini AI (Advanced Contextual Fallback)
        ai_result = await check_gemini_toxicity(message.content)
        if ai_result: return f"AI DETECTED: {ai_result}"
             
        return None

    async def punish(self, message, reason, punishment="delete", duration=60):
        try: await message.delete()
        except: pass
        
        # 1. Send warning to the channel (Temporary)
        try:
            alert_embed = discord.Embed(
                description=f"⚠️ {message.author.mention}, your message was deleted.\n**Reason:** {reason}",
                color=discord.Color.red()
            )
            await message.channel.send(embed=alert_embed, delete_after=5)
        except Exception:
            pass

        # 2. DM the User
        try:
            dm_embed = discord.Embed(title="⚠️ Auto-Mod Warning", color=discord.Color.orange())
            dm_embed.description = f"You triggered the Auto-Moderator in **{message.guild.name}**."
            dm_embed.add_field(name="Reason", value=reason, inline=False)
            dm_embed.add_field(name="Action Taken", value=punishment, inline=False)
            add_branding(dm_embed)
            await message.author.send(embed=dm_embed)
        except:
            pass # User might have DMs off

        # 3. Log to Server ModLog
        modlog = await get_modlog_channel(message.guild)
        if modlog:
            e = discord.Embed(title="🤖 Auto-Mod Action", color=discord.Color.red(), timestamp=discord.utils.utcnow())
            e.add_field(name="User", value=f"{message.author.mention}", inline=True)
            e.add_field(name="Reason", value=reason, inline=True)
            e.add_field(name="Action", value=punishment, inline=True)
            e.add_field(name="Content", value=message.content[:500], inline=False)
            add_branding(e)
            await modlog.send(embed=e)

        # 4. DM Authorized IDs (Security Alert)
        # Verify AUTHORIZED_IDS is defined
        if "AUTHORIZED_IDS" in globals():
            alert_content = f"🚨 **AutoMod Alert** | {message.guild.name}"
            alert_embed = discord.Embed(color=discord.Color.dark_red(), timestamp=discord.utils.utcnow())
            alert_embed.add_field(name="User", value=f"{message.author} (`{message.author.id}`)", inline=True)
            alert_embed.add_field(name="Reason", value=reason, inline=True)
            alert_embed.add_field(name="Msg", value=message.content[:200], inline=False)
            
            for admin_id in AUTHORIZED_IDS:
                try:
                    admin_user = message.guild.get_member(admin_id) or bot.get_user(admin_id) or await bot.fetch_user(admin_id)
                    if admin_user:
                        await admin_user.send(content=alert_content, embed=alert_embed)
                except:
                    pass

        if punishment == "timeout":
             try: await message.author.timeout(datetime.timedelta(minutes=5), reason=f"AutoMod: {reason}")
             except: pass
        
        return True

    async def process_message(self, message):
        content = message.content
        if not content: return False

        # 1. Local AI Analysis
        violation = await self.check_toxicity(message)
        if violation:
            return await self.punish(message, violation, "timeout" if "TOXIC" in violation else "delete")

        # 2. Anti-Spam (Rate Limit)
        now = discord.utils.utcnow().timestamp()
        uid = message.author.id
        self.message_cache.setdefault(uid, [])
        self.message_cache[uid] = [t for t in self.message_cache[uid] if now - t < 5.0]
        self.message_cache[uid].append(now)
        
        if len(self.message_cache[uid]) > 5:
             self.message_cache[uid] = [] 
             return await self.punish(message, "Rate Limit (Spam)", "timeout")

        # 3. Mass Ping
        if len(message.mentions) > 4:
            return await self.punish(message, f"Mass Ping ({len(message.mentions)})", "timeout")

        # 4. Anti-Link (Basic)
        if "http" in content.lower():
            allowed = global_data.get("safe_links", {}).get(str(message.guild.id), [])
            if not allowed:
                allowed = ["discord.com", "google.com", "youtube.com", "tenor.com", "giphy.com"]

            if not any(domain in content.lower() for domain in allowed):
                return await self.punish(message, "Unauthorized Link", "delete")

        return False

auto_mod = AutoModSystem()

# ===== REPORTING SYSTEM (PHASE 8) =====

@bot.command(name="setreportchannel")
@commands.has_permissions(administrator=True)
async def set_report_channel(ctx, channel: discord.TextChannel):
    """Sets the channel where user reports will be sent."""
    global_data["report_channels"][str(ctx.guild.id)] = channel.id
    await save_data()
    embed = discord.Embed(title="✅ Report Channel Set", description=f"Reports will now be sent to {channel.mention}.", color=discord.Color.green())
    add_branding(embed)
    await ctx.send(embed=embed)



# ===== BAD WORDS CONFIGURATION =====
@bot.command(name="addbadword")
@commands.has_permissions(administrator=True)
async def add_bad_word(ctx, word: str):
    """Add a word to the server's restricted list."""
    guild_id = str(ctx.guild.id)
    if "bad_words" not in global_data: global_data["bad_words"] = {}
    if guild_id not in global_data["bad_words"]: global_data["bad_words"][guild_id] = []
    
    if word.lower() in global_data["bad_words"][guild_id]:
        await ctx.send("⚠️ Word is already in the list.")
        return
        
    global_data["bad_words"][guild_id].append(word.lower())
    await save_data()
    await ctx.send(f"✅ Added `{word}` to the bad words list.")

@bot.command(name="removebadword")
@commands.has_permissions(administrator=True)
async def remove_bad_word(ctx, word: str):
    """Remove a word from the restricted list."""
    guild_id = str(ctx.guild.id)
    if guild_id not in global_data["bad_words"] or word.lower() not in global_data["bad_words"][guild_id]:
        await ctx.send("❌ Word not found in the list.")
        return
        
    global_data["bad_words"][guild_id].remove(word.lower())
    await save_data()
    await ctx.send(f"✅ Removed `{word}` from the bad words list.")

@bot.command(name="addsafelink")
@commands.has_permissions(administrator=True)
async def add_safe_link(ctx, link: str):
    """Whitelists a domain/link for the Auto-Mod (allows subdomains)."""
    from urllib.parse import urlparse
    
    # Normalize input
    if not link.startswith("http"):
        target = "https://" + link
    else:
        target = link
        
    try:
        domain = urlparse(target).netloc
        if not domain: domain = target
    except:
        domain = target

    # Strip www. for broader matching
    if domain.startswith("www."):
        domain = domain[4:]
        
    guild_id = str(ctx.guild.id)
    if "safe_links" not in global_data: global_data["safe_links"] = {}
    if guild_id not in global_data["safe_links"]: global_data["safe_links"][guild_id] = []
    
    if domain.lower() in global_data["safe_links"][guild_id]:
        await ctx.send(f"⚠️ `{domain}` is already in the safe list.")
        return

    global_data["safe_links"][guild_id].append(domain.lower())
    await save_data()
    await ctx.send(f"✅ **Link Whitelisted**: `{domain}` and its subdomains will now be allowed.")

@bot.command(name="removesafelink")
@commands.has_permissions(administrator=True)
async def remove_safe_link(ctx, link: str):
    """Removes a domain from the whitelist."""
    # Attempt to clean input to match storage
    domain = link.lower().replace("https://", "").replace("http://", "").replace("www.", "")
    if domain.endswith("/"): domain = domain[:-1]

    guild_id = str(ctx.guild.id)
    if "safe_links" not in global_data or guild_id not in global_data["safe_links"]:
        await ctx.send("❌ No dynamic safe links configured.")
        return

    if domain in global_data["safe_links"][guild_id]:
        global_data["safe_links"][guild_id].remove(domain)
        await save_data()
        await ctx.send(f"✅ **Link Removed**: `{domain}` is no longer whitelisted.")
    else:
        await ctx.send(f"❌ `{domain}` was not found in your safe list.")

# ===== NEW GAMES (PHASE 4) =====
@bot.command(name="rps")
async def rps_game(ctx, choice: str):
    """Play Rock Paper Scissors."""
    choices = ["rock", "paper", "scissors"]
    if choice.lower() not in choices:
        await ctx.send("Please choose rock, paper, or scissors.")
        return
    
    bot_choice = random.choice(choices)
    result = "Draw!"
    if (choice == "rock" and bot_choice == "scissors") or \
       (choice == "paper" and bot_choice == "rock") or \
       (choice == "scissors" and bot_choice == "paper"):
        result = "You Win! 🎉"
    elif choice != bot_choice:
        result = "I Win! 🤖"
        
    e = discord.Embed(title="Rock Paper Scissors", color=discord.Color.magenta())
    e.add_field(name="Your Choice", value=choice.title(), inline=True)
    e.add_field(name="My Choice", value=bot_choice.title(), inline=True)
    e.add_field(name="Result", value=result, inline=False)
    add_branding(e)
    await ctx.send(embed=e)

@bot.command(name="coinflip")
async def coinflip_game(ctx):
    """Flip a coin."""
    result = random.choice(["Heads", "Tails"])
    e = discord.Embed(title="🪙 Coin Flip", description=f"The coin landed on **{result}**!", color=discord.Color.gold())
    add_branding(e)
    await ctx.send(embed=e)

@bot.command(name="dice")
async def dice_game(ctx):
    """Roll a 6-sided die."""
    result = random.randint(1, 6)
    e = discord.Embed(title="🎲 Dice Roll", description=f"You rolled a **{result}**!", color=discord.Color.green())
    add_branding(e)
    await ctx.send(embed=e)

@bot.command(name="slots")
async def slots_game(ctx):
    """Play Slots."""
    emojis = ["🍎", "🍊", "🍇", "🍒", "💎", "7️⃣"]
    a = random.choice(emojis)
    b = random.choice(emojis)
    c = random.choice(emojis)
    
    e = discord.Embed(title="🎰 Slots", description=f"| {a} | {b} | {c} |", color=discord.Color.gold())
    if a == b == c:
        e.add_field(name="Result", value="**JACKPOT!** 🚨💎🚨", inline=False)
    elif a == b or b == c or a == c: 
        e.add_field(name="Result", value="Two of a kind! Nice.", inline=False)
    else:
        e.add_field(name="Result", value="No match. Try again!", inline=False)
    add_branding(e)
    await ctx.send(embed=e)





# ===== BACKUP SYSTEM (NEW) =====
BACKUPS_FILE = "backups.json"

def _load_backups():
    if not os.path.exists(BACKUPS_FILE): return {}
    try:
        with open(BACKUPS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except: return {}

def _save_backups(data):
    with open(BACKUPS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

@bot.command(name="createbackup")
@commands.has_permissions(administrator=True)
async def create_backup(ctx):
    """Creates a full backup of server roles, channels, AND member roles."""
    msg = await ctx.send("⏳ Creating backup... This may take a moment.")
    guild = ctx.guild
    
    # 1. Backup Roles
    roles = []
    for role in guild.roles:
        if role.is_default(): continue
        roles.append({
            "name": role.name,
            "permissions": role.permissions.value,
            "color": role.color.value,
            "hoist": role.hoist,
            "mentionable": role.mentionable,
            "id": role.id
        })
    
    # 2. Backup Categories & Channels
    categories = []
    total_channels = 0
    for cat in guild.categories:
        channels = []
        for ch in cat.channels:
            total_channels += 1
            channel_data = {
                "name": ch.name,
                "type": str(ch.type),
                "position": ch.position,
                "nsfw": getattr(ch, "nsfw", False),
                "overwrites": {str(t.id): p.pair()[0].value for t, p in ch.overwrites.items()} 
            }
            channels.append(channel_data)
            
        categories.append({
            "name": cat.name,
            "position": cat.position,
            "channels": channels,
            "overwrites": {str(t.id): p.pair()[0].value for t, p in cat.overwrites.items()}
        })
        
    # Text channels without category
    orphaned_channels = []
    for ch in guild.text_channels + guild.voice_channels:
        if not ch.category:
             total_channels += 1
             orphaned_channels.append({
                "name": ch.name,
                "type": str(ch.type),
                "position": ch.position,
                "nsfw": getattr(ch, "nsfw", False)
            })

    # 3. Backup Member Roles
    member_roles = {}
    for member in guild.members:
        if member.bot: continue 
        m_roles = [r.id for r in member.roles if r.name != "@everyone"]
        if m_roles:
            member_roles[str(member.id)] = m_roles

    backup_data = {
        "timestamp": str(discord.utils.utcnow()),
        "author_id": ctx.author.id,
        "guild_name": guild.name,
        "roles": roles,
        "categories": categories,
        "orphaned_channels": orphaned_channels,
        "member_roles": member_roles
    }
    
    backups = _load_backups()
    if str(guild.id) not in backups: backups[str(guild.id)] = {}
    
    backup_id = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    backups[str(guild.id)][backup_id] = backup_data
    _save_backups(backups)
    
    # Helper to truncate lists
    def format_list(items):
        if not items: return "None"
        text = ", ".join(items)
        if len(text) > 1000:
            return text[:1000] + "... (truncated)"
        return text

    role_names = [r["name"] for r in roles]
    cat_names = [c["name"] for c in categories]
    chan_names = []
    for c in categories:
        chan_names.extend([ch["name"] for ch in c["channels"]])
    chan_names.extend([ch["name"] for ch in orphaned_channels])

    embed = discord.Embed(title="✅ Backup Created Successfully", description=f"Backup ID: `{backup_id}`", color=discord.Color.green())
    
    embed.add_field(name=f"🎭 Roles ({len(roles)})", value=format_list(role_names), inline=False)
    embed.add_field(name=f"📂 Categories ({len(categories)})", value=format_list(cat_names), inline=False)
    embed.add_field(name=f"💬 Channels ({total_channels})", value=format_list(chan_names), inline=False)
    embed.add_field(name="👥 Member Roles Saved", value=f"{len(member_roles)} Members", inline=False)
    
    embed.set_footer(text="Use !loadbackup <id> to restore. Includes roles & permissions.")
    add_branding(embed)
    await msg.edit(content=None, embed=embed)

@bot.command(name="loadbackup")
@commands.has_permissions(administrator=True)
async def load_backup(ctx, backup_id: str):
    """Restores a backup. WARNING: Deletes existing channels/roles!"""
    if not is_authorized(ctx.author.id):
        await ctx.send("❌ Only authorized owners can load backups due to destructive nature.")
        return

    backups = _load_backups()
    guild_backups = backups.get(str(ctx.guild.id), {})
    data = guild_backups.get(backup_id)
    
    if not data:
        await ctx.send("❌ Backup ID not found.")
        return
        
    await ctx.send("⚠️ **WARNING**: This will DELETE all current roles and channels and replace them with the backup. Type `CONFIRM` to proceed.")
    
    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel and m.content == "CONFIRM"
        
    try:
        await bot.wait_for("message", check=check, timeout=15)
    except asyncio.TimeoutError:
        await ctx.send("❌ Timed out. Backup cancelled.")
        return
    
    msg = await ctx.send("♻️ **Restoring Server...** (This will take time)")
    guild = ctx.guild
    
    # 1. Nuke existing (except critical ones)
    try:
        for ch in guild.channels:
            try: await ch.delete()
            except: pass
        for role in guild.roles:
            if role.is_default() or role.managed or role >= guild.me.top_role: continue
            try: await role.delete()
            except: pass
    except Exception as e:
        print(f"Cleanup error: {e}")

    # 2. Restore Roles
    role_map = {} # Old ID -> New Object
    for r_data in data["roles"]:
        try:
             new_role = await guild.create_role(
                 name=r_data["name"],
                 permissions=discord.Permissions(r_data["permissions"]),
                 color=discord.Color(r_data["color"]),
                 hoist=r_data["hoist"],
                 mentionable=r_data["mentionable"]
             )
             role_map[str(r_data["id"])] = new_role
        except Exception as e:
            print(f"Role create error: {e}")

    # 3. Restore Categories & Channels
    for cat_data in data["categories"]:
        try:
            # Reconstruct Overwrites (Basic)
            cat = await guild.create_category(name=cat_data["name"], position=cat_data["position"])
            
            for ch_data in cat_data["channels"]:
                if ch_data["type"] == "text":
                    await cat.create_text_channel(name=ch_data["name"], position=ch_data["position"], nsfw=ch_data["nsfw"])
                elif ch_data["type"] == "voice":
                    await cat.create_voice_channel(name=ch_data["name"], position=ch_data["position"])
        except Exception as e:
            print(f"Category restore error: {e}")
            
    # 4. Restore Member Roles (NEW)
    member_roles_data = data.get("member_roles", {})
    restored_count = 0
    if member_roles_data:
        await msg.edit(content=f"♻️ Restoring Member Roles ({len(member_roles_data)} members)...")
        for member_id_str, role_ids in member_roles_data.items():
            try:
                member = guild.get_member(int(member_id_str))
                if member:
                    roles_to_add = []
                    for rid in role_ids:
                        if str(rid) in role_map:
                            roles_to_add.append(role_map[str(rid)])
                    if roles_to_add:
                        await member.add_roles(*roles_to_add)
                        restored_count += 1
                        await asyncio.sleep(0.1) # Rate limit protection
            except:
                pass

    await ctx.author.send(f"✅ Backup `{backup_id}` has been restored on {guild.name}!\nRestored roles for {restored_count} members.")

@bot.command(name="backuplist")
@commands.has_permissions(administrator=True)
async def list_backups(ctx):
    """Lists available backups for this server."""
    if not is_authorized(ctx.author.id):
        await ctx.send("❌ Only authorized owners can view backups.")
        return

    backups = _load_backups()
    guild_backups = backups.get(str(ctx.guild.id), {})
    
    if not guild_backups:
        await ctx.send("❌ No backups found for this server.")
        return

    embed = discord.Embed(title=f"📦 Backups for {ctx.guild.name}", color=discord.Color.blue(), timestamp=discord.utils.utcnow())
    embed.description = "Use `!loadbackup <ID>` to restore."
    
    count = 0
    for bid, data in list(guild_backups.items())[-10:]: # Show last 10
        date_str = data.get("timestamp", "Unknown Date")
        # Try to make it a relative timestamp if it matches iso format
        try:
             dt = datetime.datetime.fromisoformat(date_str)
             display_date = f"<t:{int(dt.timestamp())}:R> ({date_str.split('.')[0]})"
        except:
             display_date = date_str

        author = f"<@{data.get('author_id')}>"
        details = (
            f"**Created:** {display_date}\n"
            f"**Author:** {author}\n"
            f"**Roles:** {len(data.get('roles', []))} | **Channels:** {len(data.get('categories', []))*2 + len(data.get('orphaned_channels', []))} | **Members:** {len(data.get('member_roles', {}))}"
        )
        embed.add_field(name=f"🆔 {bid}", value=details, inline=False)
        count += 1
        
    embed.set_footer(text=f"Showing last {count} backups.")
    add_branding(embed)
    await ctx.send(embed=embed)

# ===== END BACKUP SYSTEM =====


# ===== HELPER FUNCTIONS (Anti-Nuke additions) =====

def add_branding(embed: discord.Embed):
    """Adds the Special Protection Group branding to an embed."""
    # embed.add_field(name="\u200b", value="⚡ [Powered by Special Protection Group](https://specialprotectiongroup-emh.com)", inline=False)
    # User requested removal of marketing. Let's just return embed clean or with subtle footer if needed.
    # Actually, the user said "remove marketing from everything that powered by webifylabs".
    # I will replace the "Powered by..." field with nothing, effectively removing it.
    return embed

# NO WHITELIST SYSTEM (ZERO-TRUST ENFORCEMENT)
# Whitelist feature has been completely removed to ensure equal protection for all users.

def get_anti_nuke_config(guild_id: int) -> dict:
    """Get the anti-nuke config for a guild, initializing if necessary."""
    guild_id_str = str(guild_id)
    if guild_id_str not in global_data["anti_nuke"]:
        global_data["anti_nuke"][guild_id_str] = {
            "whitelisted_users": [],
            "whitelisted_roles": [],
            "enabled": False,
            "punishment": "BAN", # Default punishment
            "limits": {
                "channel_create": 3, "channel_delete": 3,
                "role_create": 3, "role_delete": 3,
                "ban": 3, "kick": 3
            }
        }
    # Ensure nested keys exist for old configs
    if "punishment" not in global_data["anti_nuke"][guild_id_str]:
         global_data["anti_nuke"][guild_id_str]["punishment"] = "BAN"
    if "limits" not in global_data["anti_nuke"][guild_id_str]:
         global_data["anti_nuke"][guild_id_str]["limits"] = {
                "channel_create": 3, "channel_delete": 3,
                "role_create": 3, "role_delete": 3,
                "ban": 3, "kick": 3
         }
    return global_data["anti_nuke"][guild_id_str]

async def anti_nuke_punishment(guild, member, reason):
    """Executes the configured punishment."""
    config = get_anti_nuke_config(guild.id)
    action = config.get("punishment", "BAN")
    
    try:
        if action == "BAN":
            await guild.ban(member, reason=reason)
            return "Banned"
        elif action == "KICK":
            await guild.kick(member, reason=reason)
            return "Kicked"
        elif action == "STRIP":
            # Remove all roles below bot
            to_remove = [r for r in member.roles if r != guild.default_role and r < guild.me.top_role]
            await member.remove_roles(*to_remove, reason=reason)
            return "Roles Stripped"
        elif action == "NONE":
            return "Logged Only (No Action)"
    except Exception as e:
        return f"Action Failed: {e}"

async def check_anti_nuke(guild, member, action_type):
    """
    Checks if a user is exceeding rate limits for administrative actions.
    Trigger punishment if threshold is crossed.
    """
    # NO WHITELIST - Applies to all users (Zero-Trust Enforcement)
    if not member:
        return

    config = get_anti_nuke_config(guild.id)
    if not config["enabled"]:
        return

    now = discord.utils.utcnow()
    
    # Initialize cache structure
    if guild.id not in anti_nuke_cache:
        anti_nuke_cache[guild.id] = {}
    if member.id not in anti_nuke_cache[guild.id]:
        anti_nuke_cache[guild.id][member.id] = []

    # Clean up old actions (> 10 seconds ago)
    anti_nuke_cache[guild.id][member.id] = [
        (t, a) for t, a in anti_nuke_cache[guild.id][member.id] 
        if (now - t).total_seconds() < 10
    ]

    # Add new action
    anti_nuke_cache[guild.id][member.id].append((now, action_type))

    # Count actions of this type
    recent_actions = [a for t, a in anti_nuke_cache[guild.id][member.id] if a == action_type]
    limit = config.get("limits", {}).get(action_type, 3) 

    if len(recent_actions) > limit:
        # TRIGGER PUNISHMENT
        punishment_result = await anti_nuke_punishment(guild, member, f"Anti-Nuke: Limit exceeded for {action_type}")
        
        # Log to modlog
        modlog = await get_modlog_channel(guild)
        if modlog:
            embed = discord.Embed(title="🚨 Anti-Nuke Triggered", color=discord.Color.red())
            embed.add_field(name="User", value=member.mention, inline=False)
            embed.add_field(name="Action", value=action_type, inline=True)
            embed.add_field(name="Punishment", value=punishment_result, inline=True)
            add_branding(embed)
            await modlog.send(content="@everyone", embed=embed) # Mention everyone on nuke

        # PANIC MODE: If extreme (limit * 2), lockdown server
        if len(recent_actions) > (limit * 2):
             try:
                 await guild.default_role.edit(permissions=discord.Permissions(send_messages=False), reason="Anti-Nuke Panic Mode")
                 if guild.owner:
                     await guild.owner.send(f"🚨 **PANIC MODE ACTIVATED** in {guild.name} due to mass {action_type} by {member}!")
             except: pass


async def get_audit_executor(guild, action, target_id=None):
    """
    Attempts to find the user who performed an action by checking audit logs.
    """
    try:
        if not guild.me.guild_permissions.view_audit_log:
            return None
            
        async for entry in guild.audit_logs(limit=5, action=action):
            if (discord.utils.utcnow() - entry.created_at).total_seconds() > 10:
                continue # Too old
                
            if target_id:
                if entry.target.id == target_id:
                    return entry.user
            else:
                return entry.user # Return the first recent matching action if no target specified
    except:
        pass
    return None

async def get_modlog_channel(guild):
    modlog_id = global_data["modlog_channels"].get(str(guild.id))
    if modlog_id:
        channel = guild.get_channel(modlog_id)
        if channel:
            return channel
    channel = discord.utils.get(guild.text_channels, name="modlogs")
    if not channel:
        try:
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                guild.me: discord.PermissionOverwrite(read_messages=True)
            }
            channel = await guild.create_text_channel("modlogs", overwrites=overwrites)
            # Save new channel ID
            global_data["modlog_channels"][str(guild.id)] = channel.id
            await save_data()
        except discord.Forbidden:
            return None
    return channel

async def get_or_create_role(guild, role_name, color=discord.Color.default()):
    role = discord.utils.get(guild.roles, name=role_name)
    if not role:
        try:
            role = await guild.create_role(name=role_name, color=color)
        except discord.Forbidden:
            return None
    return role

async def check_hierarchy(mod, target):
    """Zero-Trust Hierarchy: Prevents same-role or higher-role actions."""
    if mod.id == mod.guild.owner_id: return True
    if not isinstance(target, discord.Member): return True
    if mod.top_role.position <= target.top_role.position:
        return "❌ **Hierarchy Error**: You cannot action someone with the same or higher role than you."
    return True

class ModApprovalView(ui.View):
    def __init__(self, action_type, mod, target, reason):
        super().__init__(timeout=3600)
        self.action_type = action_type
        self.mod = mod
        self.target = target
        self.reason = reason

    async def _is_high_staff(self, user):
        if user.id == user.guild.owner_id: return True
        governor_role = user.guild.get_role(GOVERNOR_ROLE_ID)
        return governor_role in user.roles if governor_role else False

    @ui.button(label="Approve", style=discord.ButtonStyle.success, emoji="✅")
    async def approve(self, interaction: discord.Interaction, button: ui.Button):
        if not await self._is_high_staff(interaction.user):
            return await interaction.response.send_message("❌ Only staff with the **Governor** role can approve this.", ephemeral=True)
        
        if interaction.user.id == self.mod.id:
            return await interaction.response.send_message("❌ **Security Violation**: You cannot approve your own mod action. Another staff member must authorize this.", ephemeral=True)
        
        try:
            if self.action_type == "ban":
                await interaction.guild.ban(self.target, reason=f"{self.reason} (Approved by {interaction.user})")
                await interaction.channel.send(f"🔨 **Banned** {self.target.mention} (Approved by {interaction.user.mention}).")
            elif self.action_type == "kick":
                await self.target.kick(reason=f"Kicked by {self.mod} (Approved by {interaction.user}): {self.reason}")
                await interaction.channel.send(f"👢 {self.target.mention} has been kicked (Approved by {interaction.user.mention}).")
            elif self.action_type == "warn":
                await warn_user(interaction.channel, self.target, self.reason, mod=self.mod)
                await interaction.channel.send(f"✅ **Warning Approved** for {self.target.mention} (By {interaction.user.mention}).")
            elif self.action_type == "timeout":
                # Assuming reason format "duration|actual_reason"
                try:
                    parts = self.reason.split("|", 1)
                    minutes = int(parts[0])
                    actual_reason = parts[1]
                    await self.target.timeout(datetime.timedelta(minutes=minutes), reason=f"Timed out by {self.mod} (Approved by {interaction.user}): {actual_reason}")
                    await interaction.channel.send(f"⏳ **Timeout Approved** for {self.target.mention} ({minutes}m) (By {interaction.user.mention}).")
                except:
                    await interaction.response.send_message("❌ Error executing timeout (Invalid reason format).", ephemeral=True)
                    return
            
            for child in self.children: child.disabled = True
            await interaction.response.edit_message(content=f"✅ {self.action_type.title()} Approved by {interaction.user.mention}", view=self)
        except Exception as e:
            await interaction.response.send_message(f"❌ Execution failed: {e}", ephemeral=True)

    @ui.button(label="Deny", style=discord.ButtonStyle.danger, emoji="❌")
    async def deny(self, interaction: discord.Interaction, button: ui.Button):
        if not await self._is_high_staff(interaction.user):
            return await interaction.response.send_message("❌ Only staff with the **Governor** role can deny this.", ephemeral=True)
        
        for child in self.children: child.disabled = True
        await interaction.response.edit_message(content=f"❌ {self.action_type.title()} Denied by {interaction.user.mention}", view=self)
        await interaction.channel.send(f"❌ {interaction.user.mention} denied the {self.action_type} for {self.target.mention}.")

async def is_moderator(ctx_or_member):
    # Access: global_data["moderator_roles"]
    if isinstance(ctx_or_member, commands.Context):
        member = ctx_or_member.author
    elif isinstance(ctx_or_member, discord.Interaction):
        member = ctx_or_member.user
    else:
        member = ctx_or_member
    if member.guild_permissions.manage_messages:
        return True
    
    g = member.guild
    if not g:
        return False

    mod_role1 = g.get_role(MOD_ROLE_ID)
    mod_role2 = g.get_role(MOD_ROLE_LOW_ID)
    gov_role = g.get_role(GOVERNOR_ROLE_ID)
    
    if (mod_role1 and mod_role1 in member.roles) or (mod_role2 and mod_role2 in member.roles) or (gov_role and gov_role in member.roles):
        return True

    mod_role_id = global_data["moderator_roles"].get(str(g.id))
    if mod_role_id:
        mod_role = g.get_role(mod_role_id)
        if mod_role and mod_role in member.roles:
            return True
    return False

async def needs_approval(member):
    """Checks if a staff member requires Governor approval for actions."""
    if member.id == member.guild.owner_id:
        return False
    
    # Check specifically for the Moderator roles
    mod_role1 = member.guild.get_role(MOD_ROLE_ID)
    mod_role2 = member.guild.get_role(MOD_ROLE_LOW_ID)
    
    if (mod_role1 and mod_role1 in member.roles) or (mod_role2 and mod_role2 in member.roles):
        return True
        
    # Also check if they are lower than the bot (original Zero-Trust fallback)
    return member.top_role.position < member.guild.me.top_role.position

async def has_automod_exempt_role(member: discord.Member) -> bool:
    # Access: global_data["automod_exempt_roles"]
    exempt_role_id = global_data["automod_exempt_roles"].get(str(member.guild.id))
    if not exempt_role_id:
        return False
    exempt_role = member.guild.get_role(exempt_role_id)
    return exempt_role and exempt_role in member.roles

def generate_badge():
    letter = random.choice(string.ascii_uppercase)
    digits = ''.join(random.choices(string.digits, k=3))
    return f"{letter}-{digits}"





async def legacy_check_anti_nuke(guild: discord.Guild, user_id: int, action: str):
    """
    Checks if a user is rate-limited on moderation/destructive actions.
    action: 'ban', 'kick', 'channel_delete'
    """
    guild_id = guild.id
    user = guild.get_member(user_id)
    if not user: return # Cannot process if we don't know the member

    # NO WHITELIST - Zero-Trust Enforcement
    pass

    config = get_anti_nuke_config(guild_id)
    if not config["enabled"]:
        return

    # Initialize guild and user cache
    anti_nuke_cache.setdefault(guild_id, {})
    user_cache = anti_nuke_cache[guild_id].setdefault(user_id, {"bans": 0, "kicks": 0, "channel_dels": 0, "last_action": 0})
    
    now = discord.utils.utcnow().timestamp()
    
    # Reset counts if the last action was more than 10 seconds ago
    if now - user_cache["last_action"] > 10:
        user_cache["bans"] = 0
        user_cache["kicks"] = 0
        user_cache["channel_dels"] = 0

    user_cache[action] += 1
    user_cache["last_action"] = now

    # Define Nuke Thresholds (e.g., 3 actions in 10 seconds)
    BAN_THRESHOLD = 3
    KICK_THRESHOLD = 5
    CHANNEL_DEL_THRESHOLD = 3

    reason = None
    if action == "ban" and user_cache["bans"] >= BAN_THRESHOLD:
        reason = f"Rapid Ban Threshold ({BAN_THRESHOLD} bans in <10s) breached."
    elif action == "kick" and user_cache["kicks"] >= KICK_THRESHOLD:
        reason = f"Rapid Kick Threshold ({KICK_THRESHOLD} kicks in <10s) breached."
    elif action == "channel_delete" and user_cache["channel_dels"] >= CHANNEL_DEL_THRESHOLD:
        reason = f"Rapid Channel Delete Threshold ({CHANNEL_DEL_THRESHOLD} channels in <10s) breached."

    if reason:
        # Panic Mode Check: If any threshold is severely breached (e.g., doubled), lockdown server
        PANIC_MULTIPLIER = 2
        if (action == "ban" and user_cache["bans"] >= BAN_THRESHOLD * PANIC_MULTIPLIER) or \
           (action == "kick" and user_cache["kicks"] >= KICK_THRESHOLD * PANIC_MULTIPLIER) or \
           (action == "channel_delete" and user_cache["channel_dels"] >= CHANNEL_DEL_THRESHOLD * PANIC_MULTIPLIER):
            
            # TRIGGER SERVER LOCKDOWN
            reason += " [PANIC MODE TRIGGERED]"
            # 1. Strip Admin from everyone (if possible - risky but effective)
            # 2. Deny Send Messages for @everyone
            try:
                default_role = guild.default_role
                await default_role.edit(permissions=discord.Permissions(send_messages=False), reason="Anti-Nuke Panic Mode")
                
                # Notify Owner explicitly
                if guild.owner:
                    await guild.owner.send(f"🚨 **PANIC MODE TRIGGERED** in {guild.name} due to {reason}. I have disabled `@everyone` send permissions.")
            except: pass

        # Punish and clear cache to avoid repeated punishment within the same trigger
        user_cache["bans"] = 0
        user_cache["kicks"] = 0
        user_cache["channel_dels"] = 0
        await anti_nuke_punishment(guild, user, reason)


# ===== FULL SERVER LOGGING (NEW) =====
async def log_server_event(guild, title, description, color=discord.Color.blue()):
    """Helper to log global server events."""
    modlog = await get_modlog_channel(guild)
    if not modlog: return
    
    embed = discord.Embed(title=title, description=description, color=color, timestamp=discord.utils.utcnow())
    embed.set_footer(text=f"Server ID: {guild.id}")
    add_branding(embed)
    await modlog.send(embed=embed)


# ===== SERVER MONITORING (PHASE 3) =====

async def get_monitor_channel(guild):
    """Get the specific monitor channel or fall back to modlog."""
    chan_id = global_data.get("monitor_channels", {}).get(str(guild.id))
    if chan_id:
        channel = guild.get_channel(chan_id)
        if channel: return channel
    return await get_modlog_channel(guild)

async def log_monitor_event(guild, title, description, color=discord.Color.blurple(), fields=None):
    """Logs detailed server events to the monitor channel."""
    
    embed = discord.Embed(title=title, description=description, color=color, timestamp=discord.utils.utcnow())
    if fields:
        for name, value, inline in fields:
            embed.add_field(name=name, value=value, inline=inline)
    
    embed.set_footer(text=f"Server ID: {guild.id}")
    add_branding(embed)

    # --- GLOBAL LOG TRANSFER HOOK ---
    if guild.id == SOURCE_GUILD_ID:
        # Determine log type based on title
        log_type = "moderation-logs" # Default
        t_low = title.lower()
        if "ban" in t_low: log_type = "ban-logs"
        elif "kick" in t_low: log_type = "kick-logs"
        elif "edit" in t_low: log_type = "message-edit-logs"
        elif "delete" in t_low: log_type = "message-delete-logs"
        elif "join" in t_low: log_type = "member-join-logs"
        elif "left" in t_low or "leave" in t_low or "remove" in t_low: log_type = "member-leave-logs"
        elif "role" in t_low: log_type = "role-update-logs"
        elif "nickname" in t_low: log_type = "nickname-change-logs"
        elif "voice" in t_low: log_type = "voice-logs"
        elif "promotion" in t_low or "demotion" in t_low: log_type = "promotion-logs"
        
        await log_transfer.forward(log_type, embed)

    channel = await get_monitor_channel(guild)
    if not channel: return
    await channel.send(embed=embed)

@bot.command(name="servermonitor")
@commands.has_permissions(administrator=True)
async def set_server_monitor(ctx, channel: discord.TextChannel):
    """Sets the channel for detailed server monitoring logs."""
    global_data["monitor_channels"][str(ctx.guild.id)] = channel.id
    await save_data()
    
    embed = discord.Embed(title="✅ Monitor Channel Set", description=f"Detailed server logs will now be sent to {channel.mention}.", color=discord.Color.green())
    add_branding(embed)
    await ctx.send(embed=embed)

@bot.event
async def on_guild_update(before, after):
    executor = await get_audit_executor(after, discord.AuditLogAction.guild_update)
    if not executor: return

    # Check for core setting changes
    changes = []
    if before.name != after.name: changes.append(f"Name: {before.name} -> {after.name}")
    if before.icon != after.icon: changes.append("Icon Updated")
    if before.description != after.description: changes.append("Description Modified")
    if before.verification_level != after.verification_level: changes.append(f"Verification: {before.verification_level} -> {after.verification_level}")
    if before.explicit_content_filter != after.explicit_content_filter: changes.append(f"Content Filter: {before.explicit_content_filter} -> {after.explicit_content_filter}")
    if before.default_notifications != after.default_notifications: changes.append(f"Notifications: {before.default_notifications} -> {after.default_notifications}")

    if not changes: return

    # Trigger Protection
    triggered = await mass_monitor.track_action(after, executor, "server_update")
    
    if triggered:
        # Revert changes if possible (Name is easiest, others might need more permissions/logic)
        try:
            # Revert the most critical setting: Name
            if before.name != after.name:
                await after.edit(name=before.name, reason="Server Settings Guard: Unauthorized Change Reverted")
        except: pass

        # Log to server-settings-logs
        embed = discord.Embed(
            title="🛡️ Server Settings Guard - ACTIVATED",
            description=f"**User:** {executor.mention} (`{executor.id}`)\n**Changes Detected:**\n- " + "\n- ".join(changes),
            color=discord.Color.red(),
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="Action Taken", value="✅ Change Reversion Attempted\n✅ User Roles Stripped\n✅ Punishment Role Assigned")
        add_branding(embed)
        await log_transfer.forward("server-settings-logs", embed)
        
        # Local log
        await log_monitor_event(after, "⚔️ SETTINGS GUARD TRIGGERED", f"Unauthorized server changes by {executor.mention} were detected and reverted.", discord.Color.red())

@bot.event
async def on_message_edit(before, after):
    if not before.guild or before.author.bot: return
    if before.content == after.content: return
    
    await log_monitor_event(before.guild, "✏️ Message Edited", f"**User:** {before.author.mention}\n**Channel:** {before.channel.mention}", discord.Color.blue(),
                            fields=[
                                ("Before", before.content[:1020] or "[Attachment/Embed]", False),
                                ("After", after.content[:1020] or "[Attachment/Embed]", False)
                            ])

    # --- MESSAGE CLONE SYSTEM (EDIT) ---
    if before.guild.id == SOURCE_GUILD_ID:
        timestamp = discord.utils.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        e = discord.Embed(
            title="✏️ Message Edited (Cloned)",
            color=discord.Color.gold(),
            description=f"**User:** {before.author.mention} {before.author} (`{before.author.id}`)\n"
                        f"**Before:** {before.content or '*No text*'}\n"
                        f"**After:** {after.content or '*No text*'}\n"
                        f"**Time:** {timestamp}\n"
                        f"**Channel:** {before.channel.mention} (`{before.channel.id}`)"
        )
        add_branding(e)
        await log_transfer.forward("message-clone-logs", e)

@bot.event
async def on_message_delete(message):
    if not message.guild or message.author.bot: return
    
    content = message.content[:1900] or "[Attachment/Embed]"
    
    # SNIPE: Store deleted message
    snipe_data[message.channel.id] = {
        "content": content,
        "author": message.author,
        "time": discord.utils.utcnow()
    }
    
    # Ghost Ping Detection (Phase 8)
    if message.mentions and (discord.utils.utcnow() - message.created_at).total_seconds() < 20:
        # If deleted within 20 seconds and has mentions
        pinged = ", ".join([m.mention for m in message.mentions])
        await log_monitor_event(message.guild, "👻 Ghost Ping Detected", 
                              f"**User:** {message.author.mention}\n**Pinged:** {pinged}\n**Content:** {content}", 
                              discord.Color.dark_grey())

    await log_monitor_event(message.guild, "🗑️ Message Deleted", f"**User:** {message.author.mention}\n**Channel:** {message.channel.mention}\n**Content:**\n{content}", discord.Color.red())

    # --- MESSAGE CLONE SYSTEM (DELETE) ---
    if message.guild.id == SOURCE_GUILD_ID:
        timestamp = discord.utils.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        e = discord.Embed(
            title="🗑️ Message Deleted (Cloned)",
            color=discord.Color.red(),
            description=f"**User:** {message.author.mention} {message.author} (`{message.author.id}`)\n"
                        f"**Message:** {message.content or '*No text content*'}\n"
                        f"**Time:** {timestamp}\n"
                        f"**Channel:** {message.channel.mention} (`{message.channel.id}`)"
        )
        if message.attachments:
            att_text = "\n".join([f"[{a.filename}]({a.url})" for a in message.attachments])
            e.add_field(name="Deleted Attachments", value=att_text, inline=False)
            
        add_branding(e)
        await log_transfer.forward("message-clone-logs", e)

@bot.event
async def on_webhooks_update(channel):
    await log_monitor_event(channel.guild, "⚓ Webhooks Updated", f"Webhooks changed in {channel.mention}", discord.Color.orange())

@bot.event
async def on_member_update(before, after):
    # Nickname Changes
    if before.nick != after.nick:
        executor = await get_audit_executor(after.guild, discord.AuditLogAction.member_update, after.id)
        await log_monitor_event(after.guild, "🏷️ Nickname Changed", f"**User:** {after.mention}\n**Old:** {before.nick or 'None'}\n**New:** {after.nick or 'None'}{f'\n**By:** {executor.mention}' if executor else ''}", discord.Color.blue())

    # Role Changes
    if before.roles != after.roles:
        added = [r for r in after.roles if r not in before.roles]
        removed = [r for r in before.roles if r not in after.roles]
        
        executor = await get_audit_executor(after.guild, discord.AuditLogAction.member_role_update, after.id)
        exec_text = f"\n**By:** {executor.mention}" if executor else ""

        if added:
            roles_str = ", ".join([r.mention for r in added])
            await log_monitor_event(after.guild, "📈 Roles Added", f"**User:** {after.mention}\n**Roles:** {roles_str}{exec_text}", discord.Color.green())
        if removed:
             roles_str = ", ".join([r.mention for r in removed])
             await log_monitor_event(after.guild, "📉 Roles Removed", f"**User:** {after.mention}\n**Roles:** {roles_str}{exec_text}", discord.Color.red())

@bot.event
async def on_role_create(role):
    executor = await get_audit_executor(role.guild, discord.AuditLogAction.role_create, role.id)
    exec_text = f"\n**By:** {executor.mention}" if executor else ""
    
    await log_monitor_event(role.guild, "🆕 Role Created", f"**Role:** {role.mention} (`{role.id}`){exec_text}", discord.Color.green())
    await _check_audit_log_trigger(role.guild, discord.AuditLogAction.role_create, 'role_create', role.id)

@bot.event
async def on_role_delete(role):
    executor = await get_audit_executor(role.guild, discord.AuditLogAction.role_delete, role.id)
    exec_text = f"\n**Deleted By:** {executor.mention}" if executor else ""
    
    # Note: role.mention won't work perfectly after deletion, but name will.
    await log_monitor_event(role.guild, "🗑️ Role Deleted", f"**Role:** {role.name} (`{role.id}`){exec_text}", discord.Color.red())
    await _check_audit_log_trigger(role.guild, discord.AuditLogAction.role_delete, 'role_delete', role.id)


@bot.event
async def on_invite_create(invite):
    """Monitor mass invite creation."""
    guild = invite.guild
    executor = invite.inviter
    if not executor: return

    # Track mass invite creation
    triggered = await mass_monitor.track_action(guild, executor, "invite_create")
    
    # Log the creation
    embed = discord.Embed(
        title="✉️ Invite Created",
        description=f"**Creator:** {executor.mention} (`{executor.id}`)\n**Code:** `{invite.code}`\n**Channel:** {invite.channel.mention}",
        color=discord.Color.green(),
        timestamp=discord.utils.utcnow()
    )
    if triggered:
        embed.title = "🚨 MASS INVITE CREATION DETECTED"
        embed.color = discord.Color.red()
        embed.add_field(name="Action Taken", value="✅ Creator Roles Stripped\n✅ Invite potentially dangerous", inline=False)
        
        # Optionally delete the invite if triggered
        try:
            await invite.delete(reason="Mass Invite Protection")
        except: pass

    add_branding(embed)
    await log_transfer.forward("invite-logs", embed)

@bot.event
async def on_role_update(before, after):
    executor = await get_audit_executor(after.guild, discord.AuditLogAction.role_update, after.id)
    exec_text = f"\n**By:** {executor.mention}" if executor else ""

    if before.name != after.name:
        await log_monitor_event(after.guild, "✏️ Role Name Changed", f"**Before:** {before.name}\n**After:** {after.name}{exec_text}", discord.Color.blurple())
    if before.permissions.administrator != after.permissions.administrator:
        if executor:
             await mass_monitor.track_action(after.guild, executor, 'role_update')
        
        if after.permissions.administrator:
            await log_monitor_event(after.guild, "⚠️ Admin Permission Granted", f"**Role:** {after.mention} now has ADMINISTRATOR.{exec_text}", discord.Color.red())
        else:
            await log_monitor_event(after.guild, "🛡️ Admin Permission Revoked", f"**Role:** {after.mention} no longer has ADMINISTRATOR.{exec_text}", discord.Color.green())

@bot.event
async def on_voice_state_update(member, before, after):
    if before.channel != after.channel:
        if after.channel:
            await log_monitor_event(member.guild, "🔊 Voice Join/Move", f"{member.mention} joined **{after.channel.name}**", discord.Color.blurple())
        else:
            await log_monitor_event(member.guild, "🔇 Voice Leave", f"{member.mention} left voice.", discord.Color.greyple())

# ===== WARN SYSTEM (UPDATED FOR global_data) =====
async def warn_user(channel, member, reason, mod=None, auto=False):
    # Access/Update: global_data["warns"]
    guild = channel.guild
    user_id = str(member.id)
    warns_data = global_data["warns"]

    warns_data.setdefault(user_id, 0)
    warns_data[user_id] += 1
    warn_count = warns_data[user_id]
    await save_data() # Save the updated warns count

    moderator_name = "Auto-Moderator" if auto else mod.name if mod else "Unknown"
    try:
        await member.send(f"⚠️ You have been warned in **{guild.name}** for: *{reason}*. This is warning #{warn_count}.")
    except Exception:
        pass # Handle closed DMs or other message errors
    await channel.send(f"⚠️ {member.mention} has been warned. (Total warns: {warn_count}) Reason: {reason}")
    modlog = await get_modlog_channel(guild)
    if modlog:
        await modlog.send(f"⚠️ **Warned**: {member.mention} (`{member.id}`) | **By**: {moderator_name} | **Reason**: {reason} | **Total Warns**: {warn_count}")
    
    # Punishment logic (unchanged)
    if warn_count == 2:
        try:
            await member.timeout(datetime.timedelta(hours=1), reason="2nd Warning")
            await channel.send(f"⏳ {member.mention} has been timed out for 1 hour for reaching 2 warnings. Make sure read the server rule.")
        except discord.Forbidden:
            await channel.send("⚠️ Could not time out the user.")
    elif warn_count == 3:
        try:
            await member.timeout(datetime.timedelta(days=1), reason="3rd Warning")
            await channel.send(f"⏳ {member.mention} has been timed out for 1 day for reaching 3 warnings. Make sure read the server rule.")
        except discord.Forbidden:
            await channel.send("⚠️ Could not time out the user.")
    elif warn_count >= 4:
        try:
            await member.ban(reason="4 or more warnings")
            await channel.send(f"🚫 {member.mention} has been **banned** for reaching 4 warnings. Make sure read the server rule.")
        except discord.Forbidden:
            await channel.send("⚠️ Could not ban the user.")

# ===== EVENTS (Updated for Anti-Nuke and Chat-Stop) =====

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    
    # Initialize Global Log Transfer
    print("[LOG-TRANSFER] Initializing Global Log Transfer system...")
    await log_transfer.ensure_setup()
    
    # Start Background Intelligence Loops
    bot.loop.create_task(ai_analyzer.decay_scores())
    bot.loop.create_task(perm_auditor.audit_loop())
    bot.loop.create_task(yt_monitor.monitor_loop())

    # Set the activity before syncing the tree
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name=f"{PREFIX}help"))
    try:
        # Check if the slash command tree is available and sync it
        if bot.tree:
            await bot.tree.sync()
            print("✅ Slash commands synced.")
    except Exception as e:
        print(f"❌ Slash command sync error: {e}")
    
    if not server_report_task.is_running():
        server_report_task.start()

@bot.event
async def on_guild_channel_delete(channel):
    """Monitor channel deletions."""
    # Recreate log channels if deleted from the destination guild
    if channel.guild.id == DEST_GUILD_ID:
        if channel.name in LOG_CHANNELS_CONFIG:
            print(f"[LOG-TRANSFER] Channel {channel.name} deleted. Recreating...")
            await log_transfer.ensure_setup()
            return
    if not channel.guild: return
    executor = await get_audit_executor(channel.guild, discord.AuditLogAction.channel_delete, channel.id)
    exec_text = f"\n**Deleted By:** {executor.mention}" if executor else ""
    
    await log_monitor_event(channel.guild, "🗑️ Channel Deleted", f"**Name:** {channel.name}\n**ID:** {channel.id}{exec_text}", discord.Color.red())
    await _check_audit_log_trigger(channel.guild, discord.AuditLogAction.channel_delete, 'channel_delete', channel.id)

@bot.event
async def on_guild_channel_create(channel):
    """Monitor channel creations."""
    if not channel.guild: return
    executor = await get_audit_executor(channel.guild, discord.AuditLogAction.channel_create, channel.id)
    exec_text = f"\n**Created By:** {executor.mention}" if executor else ""

    await log_monitor_event(channel.guild, "🆕 Channel Created", f"**Name:** {channel.name}\n**ID:** {channel.id}{exec_text}", discord.Color.green())
    await _check_audit_log_trigger(channel.guild, discord.AuditLogAction.channel_create, 'channel_create', channel.id)

@bot.event
async def on_guild_channel_update(before, after):
    """Monitor channel updates (name, topic, etc)."""
    if not after.guild: return
    
    executor = await get_audit_executor(after.guild, discord.AuditLogAction.channel_update, after.id)
    exec_text = f"\n**By:** {executor.mention}" if executor else ""
    
    # 1. Name Change
    if before.name != after.name:
        await log_monitor_event(after.guild, "📝 Channel Renamed", f"**Before:** {before.name}\n**After:** {after.name}\n**ID:** {after.id}{exec_text}", discord.Color.blurple())
        
    # 2. Topic Change
    if isinstance(after, discord.TextChannel) and before.topic != after.topic:
         await log_monitor_event(after.guild, "📋 Topic Changed", f"**Channel:** {after.mention}\n**Old:** {(before.topic or '')[:100]}...\n**New:** {(after.topic or '')[:100]}...{exec_text}", discord.Color.blue())

    # 3. Category Change
    if before.category != after.category:
         cat_name = after.category.name if after.category else "None"
         await log_monitor_event(after.guild, "📂 Category Changed", f"**Channel:** {after.mention}\n**New Category:** {cat_name}", discord.Color.orange())

@bot.event
async def on_member_remove(member):
    """Monitor leaves and kicks."""
    if not member.guild: return
    
    # Generic Leave Log (Monitoring)
    roles = [r.name for r in member.roles if r.name != "@everyone"]
    await log_monitor_event(member.guild, "📤 Member Left", f"{member.mention} (`{member.id}`) left.\n**Roles:** {', '.join(roles) or 'None'}", discord.Color.red())
    
    # Anti-Nuke Trigger
    await _check_audit_log_trigger(member.guild, discord.AuditLogAction.kick, 'kick', member.id)

@bot.event
async def on_member_ban(guild, user):
    """Monitor bans."""
    executor = await get_audit_executor(guild, discord.AuditLogAction.ban, user.id)
    await log_monitor_event(guild, "🚫 Member Banned", f"**User:** {user.mention} (`{user.id}`){f'\n**By:** {executor.mention}' if executor else ''}", discord.Color.red())
    await _check_audit_log_trigger(guild, discord.AuditLogAction.ban, 'ban', user.id)

@bot.event
async def on_member_unban(guild, user):
    """Monitor unbans."""
    executor = await get_audit_executor(guild, discord.AuditLogAction.unban, user.id)
    await log_monitor_event(guild, "🔓 Member Unbanned", f"**User:** {user.mention} (`{user.id}`){f'\n**By:** {executor.mention}' if executor else ''}", discord.Color.green())

async def _check_audit_log_trigger(guild, action_enum, action_str, target_id):
    """Helper to check audit logs and trigger anti-nuke."""
    if not guild.me.guild_permissions.view_audit_log: return
    
    try:
        # Wait a brief moment for audit log to propagate
        await asyncio.sleep(1) 
        async for entry in guild.audit_logs(limit=5, action=action_enum):
            if entry.target.id == target_id and (discord.utils.utcnow() - entry.created_at).total_seconds() < 20:
                # Get member object for the perpetrator
                member = guild.get_member(entry.user.id)
                if member:
                    print(f"[TRACE] Action detected: {action_str} by {member.name} (ID: {member.id})")
                    # Trigger standard anti-nuke
                    await check_anti_nuke(guild, member, action_str)
                    # Trigger advanced Mass Action Monitor (Raid Protection)
                    await mass_monitor.track_action(guild, member, action_str)
                return
    except Exception as e:
        print(f"Audit Log Check Failed: {e}") 

@bot.event
async def on_member_join(member: discord.Member):
    """Handles NEW: unwanted bot detection AND existing blacklist."""
    
    # 1. Bot Protection Check
    if member.bot:
        guild = member.guild
        inviter_id = None
        if guild.me.guild_permissions.view_audit_log:
            try:
                async for entry in guild.audit_logs(limit=3, action=discord.AuditLogAction.bot_add):
                    if entry.target.id == member.id and (discord.utils.utcnow() - entry.created_at).total_seconds() < 20:
                        inviter_id = entry.user.id
                        break
            except: pass
        
        inviter = guild.get_member(inviter_id) if inviter_id else None
        if inviter:
            # Track and Punish
            triggered = await mass_monitor.track_action(guild, inviter, "bot_add")
            
            # Log to bot-add-logs
            embed = discord.Embed(
                title="🤖 Bot Added",
                description=f"**Bot:** {member.mention} (`{member.id}`)\n**Added By:** {inviter.mention} (`{inviter.id}`)",
                color=discord.Color.blue(),
                timestamp=discord.utils.utcnow()
            )
            if triggered:
                embed.title = "🚨 MASS BOT ADD DETECTED"
                embed.color = discord.Color.red()
                embed.add_field(name="Action Taken", value="✅ Inviter Roles Stripped\n✅ Bot Kick Attempted")
                try:
                    await member.kick(reason="Mass Bot Add Protection")
                except: pass

            add_branding(embed)
            await log_transfer.forward("bot-add-logs", embed)

    # 2. Invite Tracking
    else:
        # Try to find which invite was used
        invited_by = "Unknown"
        invite_code = "Unknown"
        guild = member.guild
        try:
            if guild.me.guild_permissions.manage_guild:
                # We fetch invites and look for the one that incremented
                # Note: This is an approximation. In high-traffic servers, this needs a cache.
                invites = await guild.invites()
                for inv in invites:
                    # We log the join info
                    if inv.uses > 0: # This is a very rough guess without a cache
                        pass 
                
                # Log join to invite-logs
                embed = discord.Embed(
                    title="👤 Member Joined (Invite Tracking)",
                    description=f"**Member:** {member.mention} (`{member.id}`)\n**Account Age:** <t:{int(member.created_at.timestamp())}:R>",
                    color=discord.Color.green(),
                    timestamp=discord.utils.utcnow()
                )
                add_branding(embed)
                await log_transfer.forward("invite-logs", embed)
        except: pass

        # Log Join with Tracking
        await log_monitor_event(member.guild, "📥 Member Joined", f"{member.mention} (`{member.id}`)\n**Account Age:** <t:{int(member.created_at.timestamp())}:R>", discord.Color.green())

    # 3. Generic Join Log (Monitoring) & Welcome Message
    # Welcome Message Logic
    welcome_channel_id = global_data.get("welcome_channels", {}).get(str(member.guild.id))
    if welcome_channel_id:
        channel = member.guild.get_channel(welcome_channel_id)
        if channel:
            embed = discord.Embed(
                title=f"Welcome {member.name}!",
                description=f"Welcome to **{member.guild.name}**\nYou are member **#{member.guild.member_count}**\n\n🚫 **Hate speech, abuse, or rule violations are strictly prohibited.**\n*Automated moderation systems are active at all times.*",
                color=discord.Color.gold(),
                timestamp=discord.utils.utcnow()
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            add_branding(embed)
            
            view = discord.ui.View()
            view.add_item(discord.ui.Button(label="Official Website", url="https://specialprotectiongroup-emh.com/", style=discord.ButtonStyle.link))
            view.add_item(discord.ui.Button(label="Official Members", url="https://specialprotectiongroup-emh.com/official-members.html", style=discord.ButtonStyle.link))
            
            try:
                await channel.send(content=member.mention, embed=embed, view=view)
            except: pass

    # Monitoring Log
    await log_monitor_event(member.guild, "📥 Member Joined", f"{member.mention} (`{member.id}`)\n**Account Age:** <t:{int(member.created_at.timestamp())}:R>", discord.Color.green())
    
    # 2. Blacklist Check
    # 4. Alt Account Detection (NEW)
    # Check if account is younger than 7 days
    if (discord.utils.utcnow() - member.created_at).days < 7:
        modlog = await get_modlog_channel(member.guild)
        if modlog:
            days_old = (discord.utils.utcnow() - member.created_at).days
            e = discord.Embed(title="⚠️ Suspicious Account (Alt?)", color=discord.Color.orange(), timestamp=discord.utils.utcnow())
            e.description = f"{member.mention} has joined, but their account is only **{days_old} days old**."
            e.add_field(name="User ID", value=member.id)
            e.add_field(name="Created At", value=member.created_at.strftime("%Y-%m-%d %H:%M:%S"))
            e.set_footer(text="Action: Alert Only (No Kick)")
            await modlog.send(embed=e) 

    # 2. Existing Blacklist Check (Runs for all users)
    uid = str(member.id)
    blacklist_data = global_data["blacklist"]
    if uid in blacklist_data:
        reason = blacklist_data[uid].get("reason", "Blacklisted")
        try:
            await member.send(f"You are on the server blacklist and cannot join this team. Reason: {reason}")
        except Exception:
            pass
        modlog = await get_modlog_channel(member.guild)
        try:
            await member.kick(reason=f"Auto-kick: blacklisted user joined. Reason: {reason}")
            if modlog:
                e = discord.Embed(title="Blacklisted Member Kicked",
                                  description=f"{member.mention} (`{member.id}`) was kicked because they are blacklisted.",
                                  color=discord.Color.red(),
                                  timestamp=discord.utils.utcnow())
                e.add_field(name="Reason", value=reason, inline=False)
                await modlog.send(embed=e)
        except discord.Forbidden:
            if modlog:
                await modlog.send(f"⚠️ Could not kick blacklisted member {member.mention} (`{member.id}`). Missing permissions.")

@bot.event
async def on_command_error(ctx, error):
    # Ignore CommandNotFound to prevent console spam for typos
    if isinstance(error, commands.CommandNotFound):
        return

    # 1. Permission Errors
    if isinstance(error, commands.MissingPermissions):
        await ctx.send(f"❌ You are missing required permissions: {', '.join(error.missing_permissions)}")
    elif isinstance(error, commands.BotMissingPermissions):
        await ctx.send(f"❌ I am missing required permissions: {', '.join(error.missing_permissions)}")
    elif isinstance(error, commands.CheckFailure):
        await ctx.send("❌ You do not have permission to use this command.")

    # 2. Argument Errors
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Missing argument: **{error.param.name}**\nUsage: `{ctx.prefix}{ctx.command.name} {ctx.command.signature}`")
    elif isinstance(error, commands.BadArgument):
        await ctx.send(f"❌ Invalid argument provided. Please check your input.")
        
    # 3. Cooldowns
    elif isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"⏳ This command is on cooldown. Try again in {error.retry_after:.1f}s.")

    # 4. Unexpected Errors (Log these!)
    else:
        # If the error is wrapped in CommandInvokeError, get the original
        original_error = getattr(error, "original", error)
        
        # Format the traceback
        import traceback
        tb_str = "".join(traceback.format_exception(type(original_error), original_error, original_error.__traceback__))
        
        print(f"ERROR in command {ctx.command}: {original_error}")
        
        # Notify User
        try:
            await ctx.send(f"❌ **An unexpected error occurred:**\n`{str(original_error)}`\n\nI have reported this to the logs.")
        except:
            pass # Use might have blocked bot or channel perms issue
            
        # Log to ModLog
        if ctx.guild:
            modlog = await get_modlog_channel(ctx.guild)
            if modlog:
                # Truncate traceback if too long
                if len(tb_str) > 1000: 
                    tb_str = tb_str[-1000:]
                    
                e = discord.Embed(title="⚠️ Command Error Report", color=discord.Color.red(), timestamp=discord.utils.utcnow())
                e.add_field(name="Command", value=f"`{ctx.command.name}`", inline=True)
                e.add_field(name="User", value=f"{ctx.author} (`{ctx.author.id}`)", inline=True)
                e.add_field(name="Channel", value=f"{ctx.channel.mention}", inline=True)
                e.add_field(name="Exception", value=f"```python\n{str(original_error)}\n```", inline=False)
                # e.add_field(name="Traceback", value=f"```python\n{tb_str}\n```", inline=False) # Optional: Can be spammy
                e.set_footer(text=f"Guild: {ctx.guild.name}")
                
                try:
                    await modlog.send(embed=e)
                except Exception as log_err:
                    print(f"Failed to log error to modlog: {log_err}")

# Duplicate on_message removed. Logic merged into the main on_message handler below.

# ===== Moderation panel logic (Modal/View classes) =====

# --- UPDATED EMBED SENDING UI COMPONENTS ---

class EmbedChannelSelect(discord.ui.Select):
    """A Select menu for choosing the destination channel."""
    def __init__(self, guild_channels):
        options = []
        for channel in guild_channels:
            # Only include text channels the bot can send messages in
            if isinstance(channel, discord.TextChannel) and channel.permissions_for(channel.guild.me).send_messages:
                options.append(discord.SelectOption(
                    label=channel.name,
                    value=str(channel.id),
                    description=f"#{channel.name}"
                ))
            if len(options) >= 25: # Limit to 25 options
                break
        
        super().__init__(
            placeholder="Choose a channel to send the embed to...",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        # Store the selected channel ID in the parent view
        self.view.target_channel_id = int(self.values[0])
        # Respond by launching the main embed content modal
        await interaction.response.send_modal(EmbedContentModal(self.view.target_channel_id))
        # Disable this select menu now that a choice has been made
        for item in self.view.children:
            item.disabled = True
        await interaction.message.edit(view=self.view)

class EmbedChannelView(discord.ui.View):
    """The initial view to select a channel."""
    def __init__(self, guild_channels, author_id):
        super().__init__(timeout=180)
        self.target_channel_id = None
        self.author_id = author_id
        self.add_item(EmbedChannelSelect(guild_channels))
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This embed creation panel is not for you!", ephemeral=True)
            return False
        return True

class EmbedContentModal(discord.ui.Modal, title="Embed Message Content"):
    """Modal to gather the main content of the embed. ADDED CONTENT AND THUMBNAIL."""
    def __init__(self, channel_id: int):
        super().__init__()
        self.channel_id = channel_id
        
    message_content = discord.ui.TextInput(
        label="Message Content (Above Embed - Optional)",
        style=discord.TextStyle.paragraph,
        placeholder="Optional message text to send above the embed...",
        required=False,
        max_length=2000
    )
    embed_title = discord.ui.TextInput(
        label="Embed Title (Optional)",
        style=discord.TextStyle.short,
        placeholder="A bold title for the embed",
        required=False,
        max_length=256
    )
    embed_description = discord.ui.TextInput(
        label="Embed Message (Required)",
        style=discord.TextStyle.paragraph,
        placeholder="The main message of your embed (supports markdown)",
        required=True,
        max_length=4000
    )
    embed_color = discord.ui.TextInput(
        label="Hex Color (Optional: e.g., #FF0000)",
        style=discord.TextStyle.short,
        placeholder="#0099ff (blue) or leave blank",
        required=False,
        max_length=7
    )
    embed_thumbnail = discord.ui.TextInput(
        label="Thumbnail URL (Optional)",
        style=discord.TextStyle.short,
        placeholder="Small image on the top right (URL)",
        required=False
    )

    embed_image = discord.ui.TextInput(
        label="Image URL (Optional)",
        style=discord.TextStyle.short,
        placeholder="Large image at the bottom (URL)",
        required=False
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        # Initial response to prevent timeout
        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            # 1. Process Color
            color_value = self.embed_color.value.strip()
            color = discord.Color.default() 
            if color_value and re.fullmatch(r"#[0-9a-fA-F]{6}", color_value):
                color = discord.Color(int(color_value[1:], 16))
            
            # 2. Build the Embed
            embed = discord.Embed(
                title=self.embed_title.value or discord.Embed.Empty,
                description=self.embed_description.value,
                color=color,
                timestamp=discord.utils.utcnow()
            )
            
            # Add Image (if provided)
            image_url = self.embed_image.value.strip()
            if image_url:
                embed.set_image(url=image_url)

            # Add Thumbnail (if provided)
            thumbnail_url = self.embed_thumbnail.value.strip()
            if thumbnail_url:
                embed.set_thumbnail(url=thumbnail_url)

            # 3. Add Author/Footer
            embed.set_footer(text=f"Sent by {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)
            
            # 4. Send the preview and continue to interactive components step
            channel = interaction.guild.get_channel(self.channel_id)
            if not channel:
                await interaction.followup.send("❌ Could not find the selected channel.", ephemeral=True)
                return

            # Store the optional message content for later
            message_content = self.message_content.value or None 
            
            # Store embed components for the next step (buttons/selects)
            self.view = EmbedFinalizationView(channel.id, embed, interaction.user.id, message_content)
            await interaction.followup.send(
                "✅ **Embed Preview & Customization**\n"
                "Your embed is ready. Use the buttons below to add interactive components (link buttons) or send the final message.",
                embed=embed,
                view=self.view,
                ephemeral=True
            )

        except Exception as e:
            print(f"Error in EmbedContentModal submit: {e}")
            await interaction.followup.send(f"❌ An error occurred during embed creation: {e}", ephemeral=True)
            
# A class to collect button data for the embed
class AddButtonModal(discord.ui.Modal, title="Add an Embed Button"):
    def __init__(self, parent_view):
        super().__init__()
        self.parent_view = parent_view

    button_label = discord.ui.TextInput(
        label="Button Label (Text on the button)",
        style=discord.TextStyle.short,
        placeholder="Click Me!",
        required=True,
        max_length=80
    )
    button_url = discord.ui.TextInput(
        label="Button Link (URL)",
        style=discord.TextStyle.short,
        placeholder="https://example.com",
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        label = self.button_label.value
        url = self.button_url.value
        
        # Limit to 5 buttons per message
        if len(self.parent_view.buttons) >= 5:
            await interaction.response.send_message("❌ Cannot add more than 5 buttons to the embed message.", ephemeral=True)
            return

        try:
            # Simple URL check
            if not url.startswith("http"):
                 await interaction.response.send_message("❌ Button link must be a valid URL starting with `http` or `https`.", ephemeral=True)
                 return
                 
            # Add the button object itself
            self.parent_view.buttons.append(discord.ui.Button(label=label, style=discord.ButtonStyle.link, url=url))
            
            await interaction.response.edit_message(
                content=f"✅ Button **'{label}'** added. Total buttons: {len(self.parent_view.buttons)}/5. Add more or send the message.", 
                embed=self.parent_view.embed, 
                view=self.parent_view
            )

        except Exception as e:
            await interaction.response.send_message(f"❌ An error occurred while adding the button: {e}", ephemeral=True)



# ===== MESSAGE EVENT & ACTIVITY TRACKER (PHASE 7) =====
@bot.event
async def on_message(message):
    # --- MESSAGE CLONE SYSTEM ---
    if message.guild and message.guild.id == SOURCE_GUILD_ID:
        # Create the clone embed
        author = message.author
        content = message.content or "*No text content*"
        timestamp = discord.utils.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        
        e = discord.Embed(
            title="📥 Message Cloned",
            color=discord.Color.blue(),
            description=f"**User:** {author.mention} {author} (`{author.id}`)\n"
                        f"**Message:** {content}\n"
                        f"**Time:** {timestamp}\n"
                        f"**Channel:** {message.channel.mention} (`{message.channel.id}`)"
        )
        
        # Handle Attachments
        if message.attachments:
            att_text = "\n".join([f"[{a.filename}]({a.url})" for a in message.attachments])
            e.add_field(name="Attachments", value=att_text, inline=False)
            if any(a.content_type and a.content_type.startswith("image") for a in message.attachments):
                e.set_image(url=message.attachments[0].url)

        add_branding(e)
        await log_transfer.forward("message-clone-logs", e)

    # --- AUTO MOD CHECKS ---
    if message.author.bot: return

    # 1. Anti-Spam / Rate Limit Check
    # (Simple bucket: 5 messages in 5 seconds)
    bucket = user_spam_data.get(message.author.id, {"count": 0, "time": datetime.datetime.now().timestamp()})
    now = datetime.datetime.now().timestamp()
    
    if now - bucket["time"] > 5:
        bucket["count"] = 0
        bucket["time"] = now
        
    bucket["count"] += 1
    user_spam_data[message.author.id] = bucket
    
    if bucket["count"] > 6 and not await is_moderator(message.author):
        # Trigger Anti-Spam
        await message.delete()
        # Only warn once per burst
        if bucket["count"] == 7:
            await automod_system.punish(message, "Anti-Spam (Rate Limit)", "WARN")
        return

    # 2. Activity Tracking (Phase 7)
    if message.guild:
        guild_id = str(message.guild.id)
        user_id = str(message.author.id)
        
        # Initialize if missing
        if "server_activity" not in global_data: global_data["server_activity"] = {}
        if guild_id not in global_data["server_activity"]: global_data["server_activity"][guild_id] = {}
        
        # Increment
        current = global_data["server_activity"][guild_id].get(user_id, 0)
        global_data["server_activity"][guild_id][user_id] = current + 1
        
        # Save occasionally logic could go here, but omitted for performance. Use manual save or relying on other triggers.

    # 2. Chat Stop Check
    if message.author.id in chat_stopped_users:
        try: await message.delete()
        except: pass
        return

    # 3. AFK System (UPGRADED)
    # Check if author is AFK - remove status
    if "afk" in global_data and str(message.author.id) in global_data["afk"]:
        afk_data = global_data["afk"].pop(str(message.author.id))
        await save_data()
        
        # Calculate duration
        start_time = datetime.datetime.fromisoformat(afk_data["time"])
        duration = datetime.datetime.utcnow() - start_time
        hours, remainder = divmod(int(duration.total_seconds()), 3600)
        minutes, _ = divmod(remainder, 60)
        
        time_str = ""
        if hours > 0: time_str += f"{hours}h "
        if minutes > 0 or hours > 0: time_str += f"{minutes}m"
        else: time_str += f"{int(duration.total_seconds())}s"

        try:
            await message.channel.send(f"👋 Welcome back {message.author.mention}, I've removed your AFK status. You were gone for **{time_str}**.", delete_after=10)
        except: pass

    # Check if mentioned user is AFK
    if message.mentions:
        for mention in message.mentions:
            if "afk" in global_data and str(mention.id) in global_data["afk"]:
                afk_info = global_data["afk"][str(mention.id)]
                reason = afk_info["reason"]
                ts = afk_info["time"]
                
                # Format relative time if possible or just the duration logic
                start_time = datetime.datetime.fromisoformat(ts)
                duration = datetime.datetime.utcnow() - start_time
                minutes = int(duration.total_seconds() // 60)
                
                time_display = f"{minutes}m ago" if minutes > 0 else "just now"
                if minutes > 60: time_display = f"{minutes // 60}h {minutes % 60}m ago"

                try:
                    await message.channel.send(f"💤 **{mention.display_name}** is AFK: {reason} ({time_display})", delete_after=15)
                except: pass

    # 4. Auto-Mod
    if message.guild and message.guild.id not in global_data["disabled_automod_guilds"]:
        # Check Exemptions (Admin or Role)
        is_exempt = False
        if await has_automod_exempt_role(message.author):
            is_exempt = True
        elif message.author.guild_permissions.administrator:
            is_exempt = True
            
        if not is_exempt:
            if await auto_mod.process_message(message):
                return # Message punishment triggered

    # 5. Auto-Replies (Custom Triggers)
    if message.guild:
        guild_id_str = str(message.guild.id)
        if "auto_replies" in global_data and guild_id_str in global_data["auto_replies"]:
            content_lower = message.content.lower().strip()
            # Split to check word boundaries
            words = content_lower.split()
            
            auto_replies = global_data["auto_replies"][guild_id_str]
            for trigger, response in auto_replies.items():
                trigger_lower = trigger.lower()
                # Check for standalone word or exact multi-word phrase
                if trigger_lower == content_lower or trigger_lower in words or (" " in trigger_lower and trigger_lower in content_lower):
                    try:
                        await message.channel.send(response)
                        break # Only trigger one auto-reply per message
                    except Exception: 
                        pass

    await bot.process_commands(message)

class EmbedFinalizationView(discord.ui.View):
    """The final view for adding components and sending the embed."""
    def __init__(self, channel_id, embed: discord.Embed, author_id: int, message_content: str = None):
        super().__init__(timeout=300)
        self.channel_id = channel_id
        self.embed = embed
        self.author_id = author_id
        self.message_content = message_content # New: Content above the embed
        self.buttons = [] # List to hold discord.ui.Button objects
        
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This finalization panel is not for you!", ephemeral=True)
            return False
        return True
    
    @discord.ui.button(label="Add Link Button", style=discord.ButtonStyle.secondary, emoji="🔗")
    async def add_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AddButtonModal(self))

    @discord.ui.button(label="Send Final Embed", style=discord.ButtonStyle.success, emoji="🚀")
    async def send_final(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True, thinking=True)
        channel = interaction.guild.get_channel(self.channel_id)
        
        # Create a final view for the message being sent
        final_view = discord.ui.View(timeout=None)
        for btn in self.buttons:
            final_view.add_item(btn)

        try:
            # Send the message
            await channel.send(
                content=self.message_content, # NEW: send content
                embed=self.embed, 
                view=final_view if self.buttons else None
            )
            
            # Update the original interaction message to confirm and close
            for item in self.children:
                item.disabled = True
            await interaction.message.edit(content=f"✅ **Success!** Your embed has been sent to {channel.mention}.", embed=None, view=self)

        except discord.Forbidden:
            await interaction.followup.send(f"❌ I do not have permission to send messages in {channel.mention}.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ An unexpected error occurred while sending: {e}", ephemeral=True)
            
    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger, emoji="✖️")
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content="❌ Embed creation cancelled.", embed=None, view=self)

# --- END UPDATED EMBED SENDING UI COMPONENTS ---


class ModActionModal(ui.Modal):
    def __init__(self, target_member: discord.Member, action_type: str):
        self.target_member = target_member
        self.action_type = action_type
        super().__init__(title=f"{action_type.title()} {target_member.name}")
    reason_input = ui.TextInput(label="Reason", style=discord.TextStyle.short, placeholder="Enter reason for action", required=True)
    async def on_submit(self, interaction: discord.Interaction):
        reason = self.reason_input.value
        modlog = await get_modlog_channel(interaction.guild)
        if self.action_type == "warn":
            # Hierarchy Check
            h_check = await check_hierarchy(interaction.user, self.target_member)
            if h_check is not True: return await interaction.response.send_message(h_check, ephemeral=True)
            
            # Forced Approval for MOD_ROLE
            if await needs_approval(interaction.user):
                view = ModApprovalView("warn", interaction.user, self.target_member, reason)
                embed = discord.Embed(title="🛡️ Warning Approval Required", color=discord.Color.orange())
                embed.description = (f"**Moderator:** {interaction.user.mention}\n"
                                   f"**Target:** {self.target_member.mention}\n"
                                   f"**Reason:** {reason}\n\n"
                                   f"*Staff with the **Governor** role must approve this warning.*")
                add_branding(embed)
                await interaction.response.send_message(embed=embed, view=view)
                return

            await warn_user(interaction.channel, self.target_member, reason, mod=interaction.user)
            await interaction.response.send_message(f"✅ Warned {self.target_member.mention}.", ephemeral=True)
        elif self.action_type in ["kick", "ban"]:
            # Hierarchy Check
            h_check = await check_hierarchy(interaction.user, self.target_member)
            if h_check is not True: return await interaction.response.send_message(h_check, ephemeral=True)

            # Mandatory Approval for Destructive Actions (Zero-Trust)
            if await needs_approval(interaction.user):
                view = ModApprovalView(self.action_type, interaction.user, self.target_member, reason)
                embed = discord.Embed(title=f"🔒 {self.action_type.title()} Approval Required", color=discord.Color.orange())
                embed.description = (f"**Moderator:** {interaction.user.mention}\n"
                                   f"**Target:** {self.target_member.mention}\n"
                                   f"**Reason:** {reason}\n\n"
                                   f"*Staff with the **Governor** role must approve this action.*")
                add_branding(embed)
                await interaction.response.send_message(embed=embed, view=view)
                return

            # Immediate Execution
            try:
                if self.action_type == "kick":
                    await self.target_member.kick(reason=f"Kicked by {interaction.user.name}: {reason}")
                    await interaction.response.send_message(f"✅ Kicked {self.target_member.mention}.", ephemeral=True)
                    if modlog: await modlog.send(f"👢 **Kicked**: {self.target_member.mention} | **By**: {interaction.user.mention} | **Reason**: {reason}")
                else: # ban
                    await self.target_member.ban(reason=f"Banned by {interaction.user.name}: {reason}")
                    await interaction.response.send_message(f"✅ Banned {self.target_member.mention}.", ephemeral=True)
                    if modlog: await modlog.send(f"🚫 **Banned**: {self.target_member.mention} | **By**: {interaction.user.mention} | **Reason**: {reason}")
            except discord.Forbidden:
                await interaction.response.send_message(f"❌ I don't have permission to {self.action_type} this user.", ephemeral=True)

class TimeoutModal(ui.Modal, title="Timeout User"):
    def __init__(self, target_member: discord.Member):
        self.target_member = target_member
        super().__init__()
    duration_input = ui.TextInput(label="Duration (minutes)", style=discord.TextStyle.short, placeholder="e.g., 10 for 10 minutes", required=True)
    reason_input = ui.TextInput(label="Reason", style=discord.TextStyle.paragraph, placeholder="Enter reason for timeout", required=True)
    async def on_submit(self, interaction: discord.Interaction):
        # Hierarchy Check
        h_check = await check_hierarchy(interaction.user, self.target_member)
        if h_check is not True: return await interaction.response.send_message(h_check, ephemeral=True)

        duration = self.duration_input.value
        if not duration.isdigit():
            await interaction.response.send_message("❌ Duration must be a number.", ephemeral=True)
            return
        minutes = int(duration)
        reason = self.reason_input.value
        
        # Forced Approval for MOD_ROLE
        if await needs_approval(interaction.user):
            # We encode duration in the reason for the approval view
            approval_reason = f"{minutes}|{reason}"
            view = ModApprovalView("timeout", interaction.user, self.target_member, approval_reason)
            embed = discord.Embed(title="🛡️ Timeout Approval Required", color=discord.Color.orange())
            embed.description = (f"**Moderator:** {interaction.user.mention}\n"
                               f"**Target:** {self.target_member.mention}\n"
                               f"**Duration:** {minutes}m\n"
                               f"**Reason:** {reason}\n\n"
                               f"*Staff with the **Governor** role must approve this timeout.*")
            add_branding(embed)
            await interaction.response.send_message(embed=embed, view=view)
            return

        try:
            await self.target_member.timeout(datetime.timedelta(minutes=minutes), reason=f"Timed out by {interaction.user.name}: {reason}")
            await interaction.response.send_message(f"✅ Timed out {self.target_member.mention} for {minutes} minutes.", ephemeral=True)
            modlog = await get_modlog_channel(interaction.guild)
            if modlog: await modlog.send(f"⏳ **Timed Out**: {self.target_member.mention} | **By**: {interaction.user.mention} | **Duration**: {minutes} mins | **Reason**: {reason}")
        except discord.Forbidden:
            await interaction.response.send_message("❌ I don't have permission to timeout this user.", ephemeral=True)

class PurgeUserModal(ui.Modal, title="Purge User Messages"):
    def __init__(self, target: discord.Member):
        self.target = target
        super().__init__()
    amount = ui.TextInput(label="Amount (1-100)", placeholder="Number of messages to delete", required=True, max_length=3)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            limit = int(self.amount.value)
            if not 0 < limit <= 100: raise ValueError
        except:
             await interaction.response.send_message("❌ Invalid amount.", ephemeral=True)
             return
             
        await interaction.response.defer(ephemeral=True)
        # Custom purge logic
        def check(m): return m.author.id == self.target.id
        deleted = await interaction.channel.purge(limit=limit, check=check)
        await interaction.followup.send(f"✅ Deleted {len(deleted)} messages from {self.target.mention}.", ephemeral=True)

class ModPanelView(ui.View):
    def __init__(self, author: discord.Member, target: discord.Member):
        super().__init__(timeout=180)
        self.author = author
        self.target = target
        
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("This is not for you!", ephemeral=True)
            return False
        return True

    # --- ROW 0: Aggressive Actions ---
    @ui.button(label="Warn", style=discord.ButtonStyle.primary, emoji="⚠️", row=0)
    async def warn_button(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(ModActionModal(target_member=self.target, action_type="warn"))

    @ui.button(label="Timeout", style=discord.ButtonStyle.primary, emoji="⏳", row=0)
    async def timeout_button(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(TimeoutModal(target_member=self.target))

    @ui.button(label="Kick", style=discord.ButtonStyle.secondary, emoji="👢", row=0)
    async def kick_button(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(ModActionModal(target_member=self.target, action_type="kick"))

    @ui.button(label="Ban", style=discord.ButtonStyle.danger, emoji="🚫", row=0)
    async def ban_button(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(ModActionModal(target_member=self.target, action_type="ban"))

    # --- ROW 1: Remedial / Status Actions ---
    @ui.button(label="Remove Warn", style=discord.ButtonStyle.secondary, emoji="➖", row=1)
    async def remove_warn_button(self, interaction: discord.Interaction, button: ui.Button):
        user_id = str(self.target.id)
        warns_data = global_data["warns"]
        if user_id in warns_data and warns_data[user_id] > 0:
            warns_data[user_id] -= 1
            await save_data() 
            await interaction.response.send_message(f"✅ Removed one warn. Total: {warns_data[user_id]}.", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ No warnings to remove.", ephemeral=True)

    @ui.button(label="Remove Timeout", style=discord.ButtonStyle.success, emoji="🕊️", row=1)
    async def remove_timeout_button(self, interaction: discord.Interaction, button: ui.Button):
        try:
            await self.target.timeout(None, reason=f"Timeout removed by {self.author.name}")
            await interaction.response.send_message(f"✅ Removed timeout.", ephemeral=True)
        except:
            await interaction.response.send_message("❌ Permission denied.", ephemeral=True)

    @ui.button(label="Chat Stop/Start", style=discord.ButtonStyle.danger, emoji="🔇", row=1)
    async def toggle_chat_stop(self, interaction: discord.Interaction, button: ui.Button):
        if self.target.id in chat_stopped_users:
            chat_stopped_users.remove(self.target.id)
            await interaction.response.send_message(f"🔊 Chat allowed for {self.target.mention}.", ephemeral=True)
        else:
            chat_stopped_users.add(self.target.id)
            await interaction.response.send_message(f"🔇 Chat stopped for {self.target.mention}.", ephemeral=True)

    # --- ROW 2: Utility ---
    @ui.button(label="Purge User", style=discord.ButtonStyle.secondary, emoji="🧹", row=2)
    async def purge_user_btn(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(PurgeUserModal(self.target))

    @ui.button(label="Info", style=discord.ButtonStyle.secondary, emoji="ℹ️", row=2)
    async def info_btn(self, interaction: discord.Interaction, button: ui.Button):
        # Quick Embed Stats
        e = discord.Embed(title=f"User Info: {self.target.name}", color=self.target.color)
        e.add_field(name="Joined", value=self.target.joined_at.strftime("%Y-%m-%d"), inline=True)
        e.add_field(name="Created", value=self.target.created_at.strftime("%Y-%m-%d"), inline=True)
        e.add_field(name="Roles", value=str(len(self.target.roles)-1), inline=True)
        await interaction.response.send_message(embed=e, ephemeral=True)
        
    @ui.button(label="Voice Mute", style=discord.ButtonStyle.secondary, emoji="🎙️", row=2)
    async def voice_mute_btn(self, interaction: discord.Interaction, button: ui.Button):
        if not self.target.voice:
             await interaction.response.send_message("❌ User is not in voice.", ephemeral=True)
             return
        try:
            if self.target.voice.mute:
                await self.target.edit(mute=False, reason=f"Unmuted by {self.author}")
                await interaction.response.send_message("🔊 Unmuted in voice.", ephemeral=True)
            else:
                await self.target.edit(mute=True, reason=f"Muted by {self.author}")
                await interaction.response.send_message("🔇 Muted in voice.", ephemeral=True)
        except:
             await interaction.response.send_message("❌ Permission denied.", ephemeral=True)

class CreateTicketModal(ui.Modal, title="Create a Ticket"):
    reason_input = ui.TextInput(label="Reason for ticket", style=discord.TextStyle.paragraph, placeholder="Explain your issue here...", required=True, max_length=1000)
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        reason = self.reason_input.value
        guild = interaction.guild
        member = interaction.user
        
        mod_role_id = global_data["moderator_roles"].get(str(guild.id))
        mod_role = guild.get_role(mod_role_id) if mod_role_id else None
        
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            member: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        if mod_role:
            overwrites[mod_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
        
        
        # Determine Category
        category = None
        cat_id = global_data["ticket_categories"].get(str(guild.id))
        if cat_id:
            category = guild.get_channel(cat_id)
            
        # Determine Ping Roles
        ping_role_ids = global_data["ticket_ping_roles"].get(str(guild.id), [])
        ping_roles = []
        for rid in ping_role_ids:
            r = guild.get_role(rid)
            if r:
                ping_roles.append(r)
                overwrites[r] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        ticket_channel = await guild.create_text_channel(f"ticket-{member.name}", overwrites=overwrites, category=category)
        global_data["ticket_channels"][str(ticket_channel.id)] = member.id 
        await save_data()

        # Ping the mod role if it exists, otherwise just say "Moderators"
        mentions = [r.mention for r in ping_roles]
        if mod_role: mentions.append(mod_role.mention)
        if not mentions: mentions.append("Moderators")
        
        ping_str = " ".join(mentions)
        
        await ticket_channel.send(
            f"{member.mention} {ping_str}\n"
            f"**New Ticket Created**\n"
            f"**Reason**: {reason}\n"
            "A staff member will be with you shortly.",
            view=CloseTicketView()
        )
        await interaction.followup.send(f"✅ Your ticket has been created at {ticket_channel.mention}", ephemeral=True)

class CloseTicketView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    @ui.button(label="Close Ticket", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="close_ticket_btn")
    async def close_button(self, interaction: discord.Interaction, button: ui.Button):
        channel = interaction.channel
        channel_id_str = str(channel.id)
        user_id = global_data["ticket_channels"].get(channel_id_str)
        
        # Check if user is creator OR moderator
        is_creator = interaction.user.id == user_id
        is_mod = await is_moderator(interaction)

        if not is_creator and not is_mod:
            await interaction.response.send_message("❌ Only the ticket creator or a moderator can close this ticket.", ephemeral=True)
            return
        
        await interaction.response.send_message("Closing this ticket in 5 seconds...", ephemeral=True)
        await asyncio.sleep(5)
        
        if channel_id_str in global_data["ticket_channels"]:
            del global_data["ticket_channels"][channel_id_str]
            await save_data()
        
        await channel.delete()


class TicketPanelView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    @ui.button(label="Create a Ticket", style=discord.ButtonStyle.success, emoji="🎟️", custom_id="create_ticket_btn")
    async def create_button(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(CreateTicketModal())

# ===== APPLICATION SYSTEM (NEW) =====
@bot.command(name="setrequiredrole")
@commands.has_permissions(administrator=True)
async def set_required_apply_role(ctx, role: discord.Role):
    """Sets a role that is REQUIRED to submit an application."""
    if "required_apply_roles" not in global_data: global_data["required_apply_roles"] = {}
    global_data["required_apply_roles"][str(ctx.guild.id)] = role.id
    await save_data()
    await ctx.send(f"✅ **Required Role Set**: Only users with {role.mention} can now submit applications.")

@bot.command(name="spgreport", aliases=["gamereport", "playerreport"])
async def report_user_command(ctx, user: str, *, reason: str):
    """Simple command to report a user."""
    report_channel_id = global_data.get("report_channels", {}).get(str(ctx.guild.id))
    if not report_channel_id:
        await ctx.send("❌ Report channel not configured. Ask an admin to run `!setreportchannel`.")
        return

    channel = ctx.guild.get_channel(report_channel_id)
    if not channel:
        await ctx.send("❌ Report channel not found.")
        return

    e = discord.Embed(title="🚨 User Report", color=discord.Color.red(), timestamp=discord.utils.utcnow())
    e.add_field(name="Reported User", value=user, inline=True)
    e.add_field(name="Reported By", value=ctx.author.mention, inline=True)
    e.add_field(name="Reason", value=reason, inline=False)
    e.set_footer(text=f"ID: {ctx.author.id}")
    
    await channel.send(embed=e)
    await ctx.send("✅ Report submitted to moderators.", delete_after=5)
    await ctx.message.delete()

class ReportModal(discord.ui.Modal, title="Advanced Incident Report"):
    target = discord.ui.TextInput(label="Reported User/ID", placeholder="Username or ID", required=True)
    incident_time = discord.ui.TextInput(label="Approx Time/Date", placeholder="Today at 5pm...", required=True)
    description = discord.ui.TextInput(label="Detailed Description", style=discord.TextStyle.paragraph, required=True, min_length=20)
    evidence = discord.ui.TextInput(label="Evidence Links (Optional)", placeholder="https://youtube.com/...", required=False)

    async def on_submit(self, interaction: discord.Interaction):
        report_channel_id = global_data.get("report_channels", {}).get(str(interaction.guild.id))
        
        e = discord.Embed(title="📁 Advanced Incident Report", color=discord.Color.orange(), timestamp=discord.utils.utcnow())
        e.set_author(name=f"{interaction.user.display_name} ({interaction.user.id})", icon_url=interaction.user.display_avatar.url)
        e.add_field(name="Suspect", value=self.target.value, inline=False)
        e.add_field(name="Time", value=self.incident_time.value, inline=True)
        e.add_field(name="Description", value=self.description.value, inline=False)
        if self.evidence.value:
            e.add_field(name="Evidence", value=self.evidence.value, inline=False)
        
        add_branding(e)

        # --- GLOBAL LOG TRANSFER HOOK ---
        if interaction.guild.id == SOURCE_GUILD_ID:
            await log_transfer.forward("report-logs", e)

        if report_channel_id:
            channel = interaction.guild.get_channel(report_channel_id)
            if channel:
                await channel.send(embed=e)
            
        await interaction.response.send_message("✅ Your detailed report has been filed.", ephemeral=True)

# Slash command for reporting
@bot.tree.command(name="report", description="Submit a report to the moderation team")
async def report_slash(interaction: discord.Interaction):
    await interaction.response.send_modal(ReportModal())

class ReportView(discord.ui.View):
    @discord.ui.button(label="File Advanced Report", style=discord.ButtonStyle.danger, emoji="🚨")
    async def report_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ReportModal())

@bot.command(name="advanced_report")
async def advanced_report_command(ctx):
    """Opens the Advanced Report Wizard."""
    e = discord.Embed(
        title="🚨 Secure Reporting System", 
        description="Use this system to report serious violations, exploiters, or staff abuse.\n\nClick the button below to open the reporting form.",
        color=discord.Color.dark_red()
    )
    add_branding(e)
    await ctx.send(embed=e, view=ReportView())

class TicketModal(discord.ui.Modal, title="SPG Application"):
    name = discord.ui.TextInput(label="IRL Name / Age", placeholder="e.g. John, 18", required=True)
    roblox = discord.ui.TextInput(label="Roblox Username", placeholder="YourUsername123", required=True)
    xp = discord.ui.TextInput(label="Current XP / Rank", placeholder="e.g. 50,000 XP", required=True)
    why = discord.ui.TextInput(label="Why do you want to join?", style=discord.TextStyle.paragraph, required=True, min_length=50)

    async def on_submit(self, interaction: discord.Interaction):
        # 1. Check if application system is open
        if not global_data.get("applications_open", False):
             await interaction.response.send_message("❌ **Applications are currently CLOSED.** Please try again later.", ephemeral=True)
             return

        # 2. Check Banned Role
        banned_role_id = global_data.get("banned_apply_roles", {}).get(str(interaction.guild.id))
        if banned_role_id:
            role = interaction.guild.get_role(banned_role_id)
            if role and role in interaction.user.roles:
                 await interaction.response.send_message("❌ **You are restricted from applying.** (Banned Role)", ephemeral=True)
                 # Alert admins? 
                 return

        # 3. Check Required Role (NEW)
        required_role_id = global_data.get("required_apply_roles", {}).get(str(interaction.guild.id))
        if required_role_id:
            role = interaction.guild.get_role(required_role_id)
            if role and role not in interaction.user.roles:
                 await interaction.response.send_message(f"❌ **Missing Requirements.** You need the {role.mention} role to apply.", ephemeral=True)
                 return
        
        # 4. Create Ticket Channel
        guild = interaction.guild
        category_id = global_data.get("ticket_categories", {}).get(str(guild.id))
        category = guild.get_channel(category_id) if category_id else None
        
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
        }
        
        # Add Ticket Mods
        ping_msg = ""
        mod_role_ids = global_data.get("ticket_ping_roles", {}).get(str(guild.id), [])
        for role_id in mod_role_ids:
            r = guild.get_role(role_id)
            if r:
                overwrites[r] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
                ping_msg += f"{r.mention} "

        try:
            channel = await guild.create_text_channel(f"app-{interaction.user.name}", category=category, overwrites=overwrites)
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to create application: {e}", ephemeral=True)

class ApplicationView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="Apply Now", style=discord.ButtonStyle.primary, emoji="📝", custom_id="apply_now_btn")
    async def apply_btn(self, interaction: discord.Interaction, button: ui.Button):
        # 1. Check Banned Role
        guild_id = str(interaction.guild.id)
        banned_role_id = global_data.get("banned_apply_roles", {}).get(guild_id)
        
        if banned_role_id:
            role = interaction.guild.get_role(banned_role_id)
            if role and role in interaction.user.roles:
                await interaction.response.send_message("❌ You are **banned** from applying.", ephemeral=True)
                return

        # 2. Check Status
        if not global_data.get("applications_open", False):
            await interaction.response.send_message("🔒 **Applications are mostly CLOSED.**\nPlease wait for an announcement.", ephemeral=True)
            return
        await interaction.response.send_modal(TicketModal())

# ===== SHIFT MANAGEMENT SYSTEM (NEW - CLAN ULTIMATE) =====
class ShiftView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @ui.button(label="Start Shift", style=discord.ButtonStyle.success, emoji="🟢", custom_id="shift_start_btn")
    async def start_shift_btn(self, interaction: discord.Interaction, button: ui.Button):
        await handle_shift_action(interaction, "start")

    @ui.button(label="End Shift", style=discord.ButtonStyle.danger, emoji="🔴", custom_id="shift_end_btn")
    async def end_shift_btn(self, interaction: discord.Interaction, button: ui.Button):
        await handle_shift_action(interaction, "end")

    @ui.button(label="My Stats", style=discord.ButtonStyle.secondary, emoji="📊", custom_id="shift_stats_btn")
    async def stats_btn(self, interaction: discord.Interaction, button: ui.Button):
         await show_shift_stats(interaction, interaction.user)

async def handle_shift_action(interaction, action):
    guild_id = str(interaction.guild.id)
    user_id = str(interaction.user.id)
    
    # Init data
    if "shifts" not in global_data: global_data["shifts"] = {}
    if guild_id not in global_data["shifts"]: global_data["shifts"][guild_id] = {}
    if user_id not in global_data["shifts"][guild_id]: 
        global_data["shifts"][guild_id][user_id] = {"current_start": None, "history": []}
        
    user_data = global_data["shifts"][guild_id][user_id]
    
    if action == "start":
        if user_data.get("current_start"):
            await interaction.response.send_message("❌ You are already on shift!", ephemeral=True)
            return
        
        user_data["current_start"] = discord.utils.utcnow().timestamp()
        await save_data()
        
        # Log to monitor
        await log_monitor_event(interaction.guild, "🟢 Shift Started", f"**User:** {interaction.user.mention}\n**Time:** <t:{int(user_data['current_start'])}:F>", discord.Color.green())
        
        await interaction.response.send_message(f"✅ **Shift Started!** Good luck out there, {interaction.user.mention}.", ephemeral=True)
        
    elif action == "end":
        if not user_data.get("current_start"):
            await interaction.response.send_message("❌ You are not on shift!", ephemeral=True)
            return
            
        start_time = user_data["current_start"]
        end_time = discord.utils.utcnow().timestamp()
        duration = end_time - start_time
        
        # Save to history
        user_data["history"].append({
            "start": start_time,
            "end": end_time,
            "duration": duration
        })
        user_data["current_start"] = None
        await save_data()
        
        # Format duration
        hours, remainder = divmod(int(duration), 3600)
        minutes, seconds = divmod(remainder, 60)
        time_str = f"{hours}h {minutes}m {seconds}s"
        
        # Log
        await log_monitor_event(interaction.guild, "🔴 Shift Ended", f"**User:** {interaction.user.mention}\n**Duration:** {time_str}", discord.Color.red())
        
        await interaction.response.send_message(f"✅ **Shift Ended.**\n**Duration:** {time_str}\nGreat work today!", ephemeral=True)

async def show_shift_stats(interaction, target):
    guild_id = str(interaction.guild.id)
    user_id = str(target.id)
    
    if "shifts" not in global_data or guild_id not in global_data["shifts"] or user_id not in global_data["shifts"][guild_id]:
        await interaction.response.send_message(f"❌ No shift data found for {target.name}.", ephemeral=True)
        return

    data = global_data["shifts"][guild_id][user_id]
    history = data.get("history", [])
    
    total_seconds = sum(h["duration"] for h in history)
    hours, remainder = divmod(int(total_seconds), 3600)
    minutes, seconds = divmod(remainder, 60)
    
    embed = discord.Embed(title=f"👮 Shift Stats: {target.display_name}", color=discord.Color.blue(), timestamp=discord.utils.utcnow())
    embed.set_thumbnail(url=target.display_avatar.url)
    embed.add_field(name="Total Shifts", value=str(len(history)), inline=True)
    embed.add_field(name="Total Duration", value=f"{hours}h {minutes}m {seconds}s", inline=True)
    
    if data.get("current_start"):
        start_ts = int(data["current_start"])
        embed.add_field(name="Current Status", value=f"🟢 On Shift (Started <t:{start_ts}:R>)", inline=False)
    else:
        embed.add_field(name="Current Status", value="🔴 Off Duty", inline=False)
        
    # Last 3 shifts
    if history:
        last_shifts_str = ""
        for s in history[-3:]:
             dur = s['duration']
             h, r = divmod(int(dur), 3600)
             m, _ = divmod(r, 60)
             last_shifts_str += f"• <t:{int(s['end'])}:d>: {h}h {m}m\n"
        embed.add_field(name="Recent Activity", value=last_shifts_str, inline=False)
        
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.group(name="shift", invoke_without_command=True)
async def shift_group(ctx):
    """Manage shifts."""
    embed = discord.Embed(title="Shift Management", description="Use the buttons below to manage your shift status.", color=discord.Color.blue())
    add_branding(embed)
    await ctx.send(embed=embed, view=ShiftView())

@shift_group.command(name="panel")
@commands.has_permissions(administrator=True)
async def shift_panel(ctx):
    """Deploys a permanent shift panel."""
    embed = discord.Embed(title="👮 Shift Clock", description="Click the buttons below to clock in/out for your patrol.", color=discord.Color.gold())
    embed.set_image(url="https://media.discordapp.net/attachments/1127191214375055360/1155000000000000000/shift_banner.png") # Placeholder or generic
    add_branding(embed)
    await ctx.send(embed=embed, view=ShiftView())

@shift_group.command(name="leaderboard")
async def shift_lb(ctx):
    """View shift leaderboard."""
    guild_id = str(ctx.guild.id)
    if "shifts" not in global_data or guild_id not in global_data["shifts"]:
         await ctx.send("No shift data recorded yet.")
         return
         
    # Aggregate
    lb = []
    for uid, data in global_data["shifts"][guild_id].items():
        total_sec = sum(h["duration"] for h in data.get("history", []))
        if total_sec > 0:
            lb.append((uid, total_sec))
            
    # Sort
    lb.sort(key=lambda x: x[1], reverse=True)
    
    embed = discord.Embed(title="🏆 Shift Leaderboard", color=discord.Color.gold())
    
    desc = ""
    for idx, (uid, sec) in enumerate(lb[:10], 1):
        member = ctx.guild.get_member(int(uid))
        name = member.display_name if member else f"User {uid}"
        hours = sec / 3600
        desc += f"**{idx}. {name}**: {hours:.1f} hours\n"
        
    embed.description = desc or "No entries yet."
    add_branding(embed)
    await ctx.send(embed=embed)


@bot.command(name="manageapps")
@commands.has_permissions(administrator=True)
async def manage_apps(ctx, action: str):
    """Open or close applications. Usage: manageapps open/close"""
    if action.lower() == "open":
        global_data["applications_open"] = True
        await ctx.send("✅ Applications are now **OPEN**.")
    elif action.lower() == "close":
        global_data["applications_open"] = False
        await ctx.send("🔒 Applications are now **CLOSED**.")
    else:
        await ctx.send("Usage: `manageapps open` or `manageapps close`")
    await save_data()

# ===== DASHBOARD SYSTEM (NEW & EXPANDED) =====

class SetupChannelModal(ui.Modal):
    def __init__(self, key_name: str, title: str):
        self.key_name = key_name # e.g. "modlog_channels" or "report_channels"
        super().__init__(title=title)
        
    channel_id_input = ui.TextInput(label="Channel ID", placeholder="123456789012345678", required=True, min_length=15, max_length=20)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            cid = int(self.channel_id_input.value)
            channel = interaction.guild.get_channel(cid)
            if not channel:
                await interaction.response.send_message("❌ Channel not found in this guild.", ephemeral=True)
                return
            
            # Ensure the top-level key exists
            if self.key_name not in global_data:
                global_data[self.key_name] = {}

            global_data[self.key_name][str(interaction.guild.id)] = cid
            await save_data()
            await interaction.response.send_message(f"✅ Configuration saved! Set {channel.mention} for this setting.", ephemeral=True)
        except ValueError:
            await interaction.response.send_message("❌ Invalid ID format.", ephemeral=True)

class ManagementModal(ui.Modal):
    def __init__(self, action: str, title: str, label: str):
        self.action = action # "add_bad_word", "whitelist_user", "blacklist_user"
        super().__init__(title=title)
        self.input = ui.TextInput(label=label, placeholder="Value here...", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        val = self.input.value
        guild_id = str(interaction.guild.id)
        
        if self.action == "add_bad_word":
            if "bad_words" not in global_data: global_data["bad_words"] = {}
            if guild_id not in global_data["bad_words"]: global_data["bad_words"][guild_id] = []
            
            if val.lower() in global_data["bad_words"][guild_id]:
                await interaction.response.send_message("⚠️ Word already in list.", ephemeral=True)
            else:
                global_data["bad_words"][guild_id].append(val.lower())
                await save_data()
                await interaction.response.send_message(f"✅ Added `{val}` to bad words.", ephemeral=True)

        elif self.action == "create_ticket_panel":
             # Deploy the panel in current channel
             embed = discord.Embed(title=val, description="Click the button below to open a ticket.", color=discord.Color.blue())
             add_branding(embed)
             await interaction.channel.send(embed=embed, view=TicketPanelView())
             await interaction.response.send_message("✅ Ticket Panel Deployed.", ephemeral=True)

        elif self.action == "set_prefix":
            global_data["prefixes"][guild_id] = val
            await save_data()
            await interaction.response.send_message(f"✅ Prefix set to `{val}`.", ephemeral=True)

        elif self.action == "set_verify_role":
            try:
                rid = int(val)
                role = interaction.guild.get_role(rid)
                if not role: raise ValueError
                if "verification" not in global_data: global_data["verification"] = {}
                if guild_id not in global_data["verification"]: global_data["verification"][guild_id] = {}
                global_data["verification"][guild_id]["role_id"] = rid
                await save_data()
                await interaction.response.send_message(f"✅ Verification Role set to {role.mention}.", ephemeral=True)
            except:
                await interaction.response.send_message("❌ Invalid Role ID.", ephemeral=True)

        elif self.action == "blacklist_user":
            try:
                uid = str(int(val))
                if uid in global_data["blacklist"]:
                    await interaction.response.send_message("⚠️ User already blacklisted.", ephemeral=True)
                else:
                    global_data["blacklist"][uid] = {
                        "reason": "Dashboard Blacklist",
                        "added_by": interaction.user.id,
                        "timestamp": discord.utils.utcnow().isoformat()
                    }
                    await save_data()
                    await interaction.response.send_message(f"✅ User `{val}` has been blacklisted.", ephemeral=True)
            except:
                 await interaction.response.send_message("❌ Invalid User ID.", ephemeral=True)

        elif self.action == "give_badge":
            try:
                uid = str(int(val))
                new_badge = generate_badge()
                global_data["badges"][uid] = {
                    "badge": new_badge,
                    "assigned_by": interaction.user.id, 
                    "timestamp": discord.utils.utcnow().isoformat()
                }
                await save_data()
                await interaction.response.send_message(f"✅ Badge `{new_badge}` assigned to User `{val}`.", ephemeral=True)
            except:
                 await interaction.response.send_message("❌ Invalid User ID or generator error.", ephemeral=True)

        elif self.action == "ban_id":
             try:
                 uid = int(val)
                 user = discord.Object(id=uid)
                 await interaction.guild.ban(user, reason=f"Dashboard Ban by {interaction.user.name}")
                 await interaction.response.send_message(f"✅ Banned User ID `{uid}`.", ephemeral=True)
             except Exception as e:
                 await interaction.response.send_message(f"❌ Failed to ban: {e}", ephemeral=True)

        elif self.action == "unban_id":
             try:
                 uid = int(val)
                 user = discord.Object(id=uid)
                 await interaction.guild.unban(user, reason=f"Dashboard Unban by {interaction.user.name}")
                 await interaction.response.send_message(f"✅ Unbanned User ID `{uid}`.", ephemeral=True)
             except Exception as e:
                 await interaction.response.send_message(f"❌ Failed to unban: {e}", ephemeral=True)

        elif self.action == "set_slowmode":
             try:
                 seconds = int(val)
                 if seconds < 0 or seconds > 21600: raise ValueError
                 await interaction.channel.edit(slowmode_delay=seconds)
                 await interaction.response.send_message(f"✅ Slowmode set to {seconds}s.", ephemeral=True)
             except:
                 await interaction.response.send_message(f"❌ Invalid seconds (0-21600).", ephemeral=True)

class QuickUserActionModal(ui.Modal):
    def __init__(self, action: str):
        self.action = action # "warn_check", "user_info", "purge", "nuke_channel"
        title = "User Action"
        if action == "purge": title = "Purge Messages"
        elif action == "warn_check": title = "Check Warnings"
        elif action == "user_info": title = "User Info Lookup"
        elif action == "nuke_channel": title = "NUKE CHANNEL (Confirm)"
        super().__init__(title=title)
        
        if action == "purge":
            self.input = ui.TextInput(label="Amount", placeholder="1-100", required=True, max_length=3)
        elif action == "nuke_channel":
             self.input = ui.TextInput(label="Type 'CONFIRM' to delete & clone", placeholder="CONFIRM", required=True)
        else:
            self.input = ui.TextInput(label="User ID", placeholder="User ID here...", required=True, min_length=15, max_length=20)
            
    async def on_submit(self, interaction: discord.Interaction):
        val = self.input.value
        
        if self.action == "nuke_channel":
             if val != "CONFIRM":
                 await interaction.response.send_message("❌ Action ignored. You must type 'CONFIRM'.", ephemeral=True)
                 return
             
             channel = interaction.channel
             pos = channel.position
             try:
                 new_channel = await channel.clone(reason="Nuked by Dashboard")
                 await channel.delete(reason="Nuked by Dashboard")
                 await new_channel.edit(position=pos)
                 await new_channel.send("💥 **Channel Nuked (Reset)** by monitoring systems.\nhttps://tenor.com/view/explosion-mushroom-cloud-atomic-bomb-bomb-boom-gif-4464831")
             except:
                 await interaction.response.send_message("❌ Failed to nuke channel.", ephemeral=True)
             return

        if self.action == "purge":
            if not interaction.user.guild_permissions.manage_messages:
                 await interaction.response.send_message("❌ Missing Permissions (Manage Messages).", ephemeral=True)
                 return
            try:
                limit = int(val)
                if not 0 < limit <= 100: raise ValueError
                await interaction.response.defer(ephemeral=True)
                deleted = await interaction.channel.purge(limit=limit)
                await interaction.followup.send(f"✅ Deleted {len(deleted)} messages.", ephemeral=True)
            except:
                 await interaction.response.send_message("❌ Invalid amount (1-100).", ephemeral=True)
        else:
            # User Lookup actions
            try:
                uid = int(val)
                member = interaction.guild.get_member(uid) or await interaction.guild.fetch_member(uid)
            except:
                await interaction.response.send_message("❌ User not found.", ephemeral=True)
                return
                
            if self.action == "warn_check":
                 count = global_data["warns"].get(str(uid), 0)
                 await interaction.response.send_message(f"📊 **{member.display_name}** has **{count}** warnings.", ephemeral=True)
            elif self.action == "user_info":
                 # Call the existing userinfo logic or simple embed
                 created = member.created_at.strftime("%b %d, %Y")
                 joined = member.joined_at.strftime("%b %d, %Y")
                 roles = ", ".join([r.name for r in member.roles if r.name != "@everyone"]) or "None"
                 
                 e = discord.Embed(title=f"User Info: {member.display_name}", color=member.color)
                 e.set_thumbnail(url=member.display_avatar.url)
                 e.add_field(name="ID", value=member.id, inline=True)
                 e.add_field(name="Account Created", value=created, inline=True)
                 e.add_field(name="Joined Server", value=joined, inline=True)
                 e.add_field(name="Roles", value=roles[:1024], inline=False)
                 add_branding(e)
                 await interaction.response.send_message(embed=e, ephemeral=True)

class DashboardView(ui.View):
    def __init__(self, ctx):
        super().__init__(timeout=300)
        self.ctx = ctx
        self.update_buttons()

    def update_buttons(self):
        guild_id = self.ctx.guild.id
        anti_nuke_on = get_anti_nuke_config(guild_id)["enabled"]
        auto_mod_on = guild_id not in global_data["disabled_automod_guilds"]

        # Row 1: Status Toggles
        self.children[0].style = discord.ButtonStyle.green if anti_nuke_on else discord.ButtonStyle.red
        self.children[0].label = "Anti-Nuke: ON" if anti_nuke_on else "Anti-Nuke: OFF"
        
        self.children[1].style = discord.ButtonStyle.green if auto_mod_on else discord.ButtonStyle.red
        self.children[1].label = "Auto-Mod: ON" if auto_mod_on else "Auto-Mod: OFF"

    # --- ROW 1: Security Toggles ---
    @ui.button(label="Anti-Nuke", style=discord.ButtonStyle.secondary, emoji="🛡️", row=0)
    async def toggle_antinuke(self, interaction: discord.Interaction, button: ui.Button):
        if not is_authorized(interaction.user.id):
             await interaction.response.send_message("❌ Access Denied. Only authorized users can toggle Anti-Nuke.", ephemeral=True)
             return
        config = get_anti_nuke_config(interaction.guild.id)
        config["enabled"] = not config["enabled"]
        await save_data()
        self.update_buttons()
        await interaction.response.edit_message(view=self)
        
    @ui.button(label="Auto-Mod", style=discord.ButtonStyle.secondary, emoji="🤖", row=0)
    async def toggle_automod(self, interaction: discord.Interaction, button: ui.Button):
        if not interaction.user.guild_permissions.administrator:
             await interaction.response.send_message("❌ You need Admin permissions.", ephemeral=True)
             return
        gid = interaction.guild.id
        if gid in global_data["disabled_automod_guilds"]:
            global_data["disabled_automod_guilds"].remove(gid)
        else:
            global_data["disabled_automod_guilds"].add(gid)
        await save_data()
        self.update_buttons()
        await interaction.response.edit_message(view=self)

    @ui.button(label="Panic Mode", style=discord.ButtonStyle.danger, emoji="🚨", row=0)
    async def panic_mode(self, interaction: discord.Interaction, button: ui.Button):
        if not is_authorized(interaction.user.id):
            await interaction.response.send_message("❌ Unauthorized.", ephemeral=True)
            return
        
        # Immediate Lockdown
        await interaction.response.defer(ephemeral=True)
        try:
            await interaction.guild.default_role.edit(permissions=discord.Permissions(send_messages=False), reason="DASHBOARD PANIC MODE")
            await interaction.followup.send("🚨 **PANIC MODE ACTIVATED**: Server Locked Down.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Lockdown Failed: {e}", ephemeral=True)

    @ui.button(label="Nuke Channel", style=discord.ButtonStyle.danger, emoji="💥", row=0)
    async def nuke_channel_btn(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(QuickUserActionModal("nuke_channel"))

    # --- ROW 2: Configuration ---
    @ui.button(label="Set ModLogs", style=discord.ButtonStyle.secondary, emoji="📜", row=1)
    async def set_modlog_btn(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(SetupChannelModal("modlog_channels", "Set ModLog Channel"))

    @ui.button(label="Set Reports", style=discord.ButtonStyle.secondary, emoji="📨", row=1)
    async def set_report_btn(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(SetupChannelModal("report_channels", "Set User Report Channel"))

    @ui.button(label="Server Status", style=discord.ButtonStyle.primary, emoji="📊", row=1)
    async def server_status_btn(self, interaction: discord.Interaction, button: ui.Button):
         # ... existing code ...
         g = interaction.guild
         embed = discord.Embed(title="Server Quick Stats", color=discord.Color.blue())
         embed.add_field(name="Members", value=str(g.member_count))
         embed.add_field(name="Warns Active", value=str(len(global_data["warns"])))
         embed.add_field(name="Boosts", value=str(g.premium_subscription_count))
         add_branding(embed)
         await interaction.response.send_message(embed=embed, ephemeral=True)

    @ui.button(label="Transcript", style=discord.ButtonStyle.secondary, emoji="📝", row=1)
    async def transcript_btn(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer(ephemeral=True)
        messages = [message async for message in interaction.channel.history(limit=100)]
        output = [f"[{m.created_at.strftime('%Y-%m-%d %H:%M:%S')}] {m.author}: {m.content}" for m in reversed(messages)]
        # We can't easily write a file, just send as code block
        text = "\n".join(output)
        if len(text) > 1900:
            text = text[-1900:]
            await interaction.followup.send(f"📜 **Last 100 Messages (Truncated):**\n```\n{text}\n```", ephemeral=True)
        else:
            await interaction.followup.send(f"📜 **Last 100 Messages:**\n```\n{text}\n```", ephemeral=True)


    # --- ROW 3: Moderation Tools ---
    @ui.button(label="Check Warns", style=discord.ButtonStyle.secondary, emoji="⚠️", row=2)
    async def check_warns_btn(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(QuickUserActionModal("warn_check"))

    @ui.button(label="User Lookup", style=discord.ButtonStyle.secondary, emoji="🔍", row=2)
    async def user_lookup_btn(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(QuickUserActionModal("user_info"))

    @ui.button(label="Purge Chat", style=discord.ButtonStyle.secondary, emoji="🧹", row=2)
    async def purge_btn(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(QuickUserActionModal("purge"))

    @ui.button(label="Slowmode", style=discord.ButtonStyle.secondary, emoji="🐢", row=2)
    async def slowmode_btn(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(ManagementModal("set_slowmode", "Set Slowmode (Seconds)", "Seconds (0=Off)"))

    @ui.button(label="Ban ID", style=discord.ButtonStyle.danger, emoji="🔨", row=2)
    async def mass_ban_btn(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(ManagementModal("ban_id", "Force Ban User by ID", "User ID"))


    # --- ROW 4: Backups & Misc ---
    # (create_backup_btn removed due to duplication/row limit)

    @ui.button(label="Block Word", style=discord.ButtonStyle.secondary, emoji="🤬", row=3)
    async def block_word_btn(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(ManagementModal("add_bad_word", "Block Bad Word", "Word to Block"))


    # --- ROW 5: TOOLS ---
    @ui.button(label="Lock Channel", style=discord.ButtonStyle.danger, emoji="🔒", row=4)
    async def lockdown_btn(self, interaction: discord.Interaction, button: ui.Button):
        # Lock current channel
        try:
            overwrite = interaction.channel.overwrites_for(interaction.guild.default_role)
            overwrite.send_messages = False
            await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=overwrite, reason=f"Dashboard Lock by {interaction.user}")
            await interaction.response.send_message("🔒 **Channel Locked**.", ephemeral=True)
        except:
             await interaction.response.send_message("❌ Failed to lock channel.", ephemeral=True)

    @ui.button(label="Unlock Channel", style=discord.ButtonStyle.success, emoji="🔓", row=4)
    async def unlockchain_btn(self, interaction: discord.Interaction, button: ui.Button):
        try:
            overwrite = interaction.channel.overwrites_for(interaction.guild.default_role)
            overwrite.send_messages = None
            await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=overwrite, reason=f"Dashboard Unlock by {interaction.user}")
            await interaction.response.send_message("🔓 **Channel Unlocked**.", ephemeral=True)
        except:
             await interaction.response.send_message("❌ Failed to unlock channel.", ephemeral=True)

    @ui.button(label="Deploy Tickets", style=discord.ButtonStyle.primary, emoji="🎫", row=4)
    async def deploy_ticket_btn(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(ManagementModal("create_ticket_panel", "Deploy Ticket System", "Panel Title (e.g. Support)"))

    # --- ROW 3 Remaining ---
    @ui.button(label="Set Prefix", style=discord.ButtonStyle.secondary, emoji="⚙️", row=3)
    async def set_prefix_btn(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(ManagementModal("set_prefix", "Set Server Prefix", "New Prefix"))

    @ui.button(label="Verify Role", style=discord.ButtonStyle.secondary, emoji="🆔", row=3)
    async def verify_role_btn(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(ManagementModal("set_verify_role", "Set Verification Role", "Role ID"))

    @ui.button(label="Blacklist", style=discord.ButtonStyle.danger, emoji="🚫", row=3)
    async def blacklist_btn(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(ManagementModal("blacklist_user", "Blacklist User", "User ID"))

    # --- ROW 4 Remaining ---
    @ui.button(label="Give Badge", style=discord.ButtonStyle.success, emoji="🏅", row=4)
    async def give_badge_btn(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(ManagementModal("give_badge", "Assign Badge", "User ID"))

    @ui.button(label="Backup", style=discord.ButtonStyle.success, emoji="💾", row=4)
    async def backup_btn(self, interaction: discord.Interaction, button: ui.Button):
        if not is_authorized(interaction.user.id):
             await interaction.response.send_message("❌ Unauthorized.", ephemeral=True)
             return
        # Create Backup Logic
        backup_id = f"backup_{int(discord.utils.utcnow().timestamp())}"
        backup_data = {
            "guild_id": interaction.guild.id,
            "guild_name": interaction.guild.name,
            "roles": [{"name": r.name, "permissions": r.permissions.value, "color": r.color.value} for r in interaction.guild.roles if not r.is_default()],
            "categories": [{"name": c.name, "channels": [ch.name for ch in c.channels]} for c in interaction.guild.categories],
            "channels": [{"name": c.name, "type": str(c.type)} for c in interaction.guild.channels if not c.category]
        }
        
        # Save to backups.json
        try:
            with open("backups.json", "r") as f:
                backups = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            backups = {}
            
        backups[backup_id] = backup_data
        with open("backups.json", "w") as f:
            json.dump(backups, f, indent=4)
            
        await interaction.response.send_message(f"✅ **Backup Created!** ID: `{backup_id}`", ephemeral=True)


@bot.command(name="dashboard")
@commands.has_permissions(administrator=True)
async def dashboard_command(ctx):
    """Opens the interactive server dashboard."""
    embed = discord.Embed(title="🎛️ Ultimate Control Dashboard", description="Manage your server's security settings below.", color=discord.Color.dark_theme())
    add_branding(embed)
    view = DashboardView(ctx)
    await ctx.send(embed=embed, view=view)


@bot.command(name="setperm")
async def set_perm_command(ctx, user_id: str, action: str):
    """
    (Owner Only) Add/Remove user from AUTHORIZED_IDS.
    Usage: !setperm <user_id> <add/remove>
    NOTE: This updates code-level access for the runtime (if we used a DB it would be better, but this updates the list in memory).
    To make it persistent, one should check AUTHORIZED_IDS from a file, but user asked for "setperm".
    """
    if ctx.author.id not in AUTHORIZED_IDS and ctx.author.id != ctx.guild.owner_id:
        await ctx.send("❌ You do not have permission to use this command.")
        return
        
    try:
        uid = int(user_id)
    except:
        await ctx.send("❌ Invalid User ID.")
        return

    if action.lower() == "add":
        if uid not in AUTHORIZED_IDS:
            AUTHORIZED_IDS.append(uid)
            await ctx.send(f"✅ User `{uid}` added to Authorized list.")
        else:
            await ctx.send("⚠️ User is already authorized.")
    elif action.lower() == "remove":
        if uid in AUTHORIZED_IDS:
            AUTHORIZED_IDS.remove(uid)
            await ctx.send(f"✅ User `{uid}` removed from Authorized list.")
        else:
            await ctx.send("⚠️ User is not in the list.")
    else:
        await ctx.send("❌ Usage: `setperm <id> <add/remove>`")

# ===== ANTI-NUKE COMMANDS (NEW) =====

@bot.command(name="setmasslimit")
@commands.has_permissions(administrator=True)
async def set_mass_limit(ctx, action: str, limit: int):
    """Sets a custom limit for the Mass Action Monitor."""
    valid_actions = ["ban", "kick", "channel_delete", "channel_create", "role_delete", "role_update"]
    if action.lower() not in valid_actions:
        await ctx.send(f"❌ Invalid action. Valid actions: {', '.join(valid_actions)}")
        return
    
    if limit < 1:
        await ctx.send("❌ Limit must be at least 1.")
        return

    guild_id = str(ctx.guild.id)
    if "mass_action_thresholds" not in global_data:
        global_data["mass_action_thresholds"] = {}
    
    if guild_id not in global_data["mass_action_thresholds"]:
        global_data["mass_action_thresholds"][guild_id] = {}
    
    global_data["mass_action_thresholds"][guild_id][action.lower()] = limit
    await save_data()
    await ctx.send(f"✅ **Mass Action Limit Updated**: `{action}` threshold set to `{limit}` for this server.")

@bot.command(name="masslimits")
@commands.has_permissions(administrator=True)
async def view_mass_limits(ctx):
    """Displays current limits for the Mass Action Monitor."""
    guild_id = str(ctx.guild.id)
    custom = global_data.get("mass_action_thresholds", {}).get(guild_id, {})
    
    embed = discord.Embed(title="⚙️ Mass Action Thresholds", color=discord.Color.blue())
    
    monitor = mass_monitor
    for action, default in monitor.default_thresholds.items():
        limit = custom.get(action, default)
        embed.add_field(name=action.replace("_", " ").title(), value=f"`{limit}` (Default: {default})", inline=True)
    
    embed.set_footer(text="Window: 5 Minutes")
    add_branding(embed)
    await ctx.send(embed=embed)

@bot.command(name="antinuke")
async def anti_nuke_toggle(ctx, status: str):
    """Enable or disable the server-wide Anti-Nuke system. (Restricted)"""
    # Authorization Check
    if not is_authorized(ctx.author.id):
        await ctx.send("❌ Access Denied. Only authorized users can toggle Anti-Nuke.")
        return

    status = status.lower()
    config = get_anti_nuke_config(ctx.guild.id)
    
    if status in ["on", "enable", "start"]:
        config["enabled"] = True
        await save_data()
        await ctx.send("✅ **Anti-Nuke System Enabled**: I am now monitoring for mass bans, kicks, channel deletions, and unauthorized bot adds.")
    elif status in ["off", "disable", "stop"]:
        config["enabled"] = False
        await save_data()
        await ctx.send("⚠️ **Anti-Nuke System Disabled**: Monitoring is turned off. Use with caution.")
    else:
        await ctx.send(f"❌ Invalid status. Use `on` or `off`. Current status: {'Enabled' if config['enabled'] else 'Disabled'}")

@bot.command(name="setnukeaction")
@commands.has_permissions(administrator=True)
async def set_nuke_action(ctx, action: str):
    """
    Set the punishment for Anti-Nuke triggers.
    Options: BAN, KICK, STRIP, NONE
    """
    action = action.upper()
    valid_actions = ["BAN", "KICK", "STRIP", "NONE"]
    
    if action not in valid_actions:
        await ctx.send(f"❌ Invalid action. Choose from: {', '.join(valid_actions)}")
        return
        
    config = get_anti_nuke_config(ctx.guild.id)
    config["punishment"] = action
    await save_data()
    
    descriptions = {
        "BAN": "Ban the user immediately.",
        "KICK": "Kick the user.",
        "STRIP": "Remove all roles from the user.",
        "NONE": "Log the event but take no action."
    }
    
    embed = discord.Embed(title="🛡️ Anti-Nuke Action Updated", color=discord.Color.gold())
    embed.add_field(name="New Action", value=f"**{action}**", inline=False)
    embed.add_field(name="Description", value=descriptions[action], inline=False)
    add_branding(embed)
    await ctx.send(embed=embed)


@bot.command(name="about")
async def about_bot(ctx):
    """Details about the bot's mission and technical capabilities."""
    embed = discord.Embed(
        title="🛡️ SPG Security & Monitoring Intelligence",
        description="I am the core security engine for the **Special Protection Group**. My mission is total server integrity and continuous surveillance.",
        color=discord.Color.dark_red(),
        timestamp=discord.utils.utcnow()
    )
    
    embed.add_field(
        name="🔒 Zero-Trust Protection",
        value="Every action is monitored. There are **NO whitelists** and **NO bypasses**. Even Administrators and Server Owners are subject to immediate punishment for mass actions (Bans, Kicks, Channel/Role deletions).",
        inline=False
    )
    
    embed.add_field(
        name="🛰️ Global Data Transfer",
        value="**Nothing escapes.** Every log, every deleted message, every edited post, and every modification is mirrored in real-time to an **External Secure Server and Database**. Your entire history is saved off-site.",
        inline=False
    )
    
    embed.add_field(
        name="📁 Restricted Access",
        value="The external database and mirroring system are accessible **ONLY to SPG Directors** and authorized high-level command. Local deletions on this server do NOT affect the external records.",
        inline=False
    )
    
    capabilities = (
        "✅ **Mass Action Monitor**: Detects 2+ bans/kicks or 3+ channel changes.\n"
        "✅ **AI Behavior Analyzer**: Intelligence-based risk scoring and pattern detection.\n"
        "✅ **Server Settings Guard**: Automatically reverts unauthorized name/icon/config changes.\n"
        "✅ **Bot Addition Shield**: Kicks unauthorized bots and punishes the inviter.\n"
        "✅ **Real-Time Mirroring**: Clones all message traffic for permanent off-site archiving."
    )
    embed.add_field(name="🛠️ Tactical Capabilities", value=capabilities, inline=False)
    
    embed.set_footer(text="SPG Surveillance System • Intelligence Active")
    add_branding(embed)
    await ctx.send(embed=embed)


@bot.command(name="nukestatus")
@commands.has_permissions(administrator=True)
async def anti_nuke_status(ctx):
    """Display the current Anti-Nuke configuration."""
    config = get_anti_nuke_config(ctx.guild.id)
    
    embed = discord.Embed(title="🛡️ Anti-Nuke Security Status", color=discord.Color.red() if config["enabled"] else discord.Color.greyple())
    embed.add_field(name="System Status", value="**" + ("ENABLED" if config["enabled"] else "DISABLED") + "**", inline=False)
    
    embed.add_field(name="Policy", value="Zero-Trust Enforcement (No Whitelist)", inline=False)
    
    embed.set_footer(text=f"Server ID: {ctx.guild.id}")
    add_branding(embed)
    await ctx.send(embed=embed)


# ===== FUN COMMANDS (NEW) =====

@bot.command(name="8ball")
async def eight_ball(ctx, *, question: str):
    """Ask the magic 8-ball a question."""
    responses = [
        "It is certain.", "It is decidedly so.", "Without a doubt.", "Yes, definitely.",
        "You may rely on it.", "As I see it, yes.", "Most likely.", "Outlook good.",
        "Yes.", "Signs point to yes.", "Reply hazy, try again.", "Ask again later.",
        "Better not tell you now.", "Cannot predict now.", "Concentrate and ask again.",
        "Don't count on it.", "My reply is no.", "My sources say no.",
        "Outlook not so good.", "Very doubtful."
    ]
    
    response = random.choice(responses)
    
    embed = discord.Embed(
        title="🎱 The Magic 8-Ball",
        description=f"**Question**: {question}\n\n**Answer**: {response}",
        color=discord.Color.purple()
    )
    embed.set_footer(text=f"Asked by {ctx.author.display_name}")
    add_branding(embed)
    await ctx.send(embed=embed)

@bot.command(name="avatar")
async def get_avatar(ctx, member: discord.Member = None):
    """
    Get the full-size avatar of a specified user or yourself.
    """
    member = member or ctx.author
    
    embed = discord.Embed(
        title=f"{member.display_name}'s Avatar",
        color=member.color
    )
    embed.set_image(url=member.display_avatar.url)
    embed.set_footer(text=f"Requested by {ctx.author.display_name}")
    add_branding(embed)
    await ctx.send(embed=embed)


# ===== NEW CHAT-STOP COMMANDS (HIGH-PRIORITY MOD) =====

@bot.command(name="stopchat")
@commands.check(is_moderator)
async def stop_chat(ctx, member: discord.Member):
    """
    Prevents a user from sending messages by immediately deleting them.
    This overrides all roles/permissions.
    """
    if member.id == ctx.author.id:
        await ctx.send("❌ You cannot chat-stop yourself.")
        return
        
    if await is_moderator(member) and not ctx.author.guild_permissions.administrator and member.id != ctx.guild.owner_id:
        await ctx.send("❌ You cannot chat-stop another moderator without administrator permissions.")
        return
        
    if member.id in chat_stopped_users:
        await ctx.send(f"❌ {member.mention} is already chat-stopped.")
        return
        
    chat_stopped_users.add(member.id)
    
    modlog = await get_modlog_channel(ctx.guild)
    
    e = discord.Embed(title="🚫 User Chat-Stopped", color=discord.Color.red(), timestamp=discord.utils.utcnow())
    e.add_field(name="User", value=f"{member.mention} (`{member.id}`)", inline=False)
    e.add_field(name="Action", value="All messages will be immediately deleted.", inline=False)
    e.set_footer(text=f"By {ctx.author.display_name}")
    add_branding(e)
    
    await ctx.send(f"🚫 {member.mention} has been **chat-stopped**. All future messages will be deleted.", embed=e)
    if modlog:
        await modlog.send(embed=e)

@bot.command(name="startchat")
@commands.check(is_moderator)
async def start_chat(ctx, member: discord.Member):
    """Removes a user from the chat-stop list."""
    
    if member.id not in chat_stopped_users:
        await ctx.send(f"❌ {member.mention} is not currently chat-stopped.")
        return
        
    chat_stopped_users.remove(member.id)
    
    modlog = await get_modlog_channel(ctx.guild)
    
    e = discord.Embed(title="✅ User Chat-Restarted", color=discord.Color.green(), timestamp=discord.utils.utcnow())
    e.add_field(name="User", value=f"{member.mention} (`{member.id}`)", inline=False)
    e.add_field(name="Action", value="Messages will no longer be deleted on sight.", inline=False)
    e.set_footer(text=f"By {ctx.author.display_name}")
    add_branding(e)
    
    await ctx.send(f"✅ {member.mention} is **no longer chat-stopped**.")
    if modlog:
        await modlog.send(embed=e)

@bot.command(name="afk")
async def afk_command(ctx, *, reason: str = "AFK"):
    """Set your status to AFK (Auto-removes on message)."""
    if "afk" not in global_data: global_data["afk"] = {}
    
    global_data["afk"][str(ctx.author.id)] = {
        "reason": reason,
        "time": datetime.datetime.utcnow().isoformat()
    }
    await save_data()
    
    embed = discord.Embed(
        title="💤 AFK Status Set",
        description=f"{ctx.author.mention} is now AFK.\n**Reason:** {reason}",
        color=discord.Color.blue()
    )
    embed.set_footer(text="I will remove your AFK when you send a message.")
    add_branding(embed)
    await ctx.send(embed=embed)
    
# ===== CONFIGURATION COMMANDS (NEW) =====

@bot.command(name="setprefix")
@commands.has_permissions(administrator=True)
async def set_prefix(ctx, new_prefix: str):
    """Change the bot's prefix for this server."""
    global_data["prefixes"][str(ctx.guild.id)] = new_prefix
    await save_data()
    embed = discord.Embed(title="✅ Prefix Updated", description=f"The prefix has been set to `{new_prefix}`", color=discord.Color.green())
    add_branding(embed)
    await ctx.send(embed=embed)

@bot.command(name="setverifyrole")
@commands.has_permissions(administrator=True)
async def set_verify_role(ctx, role: discord.Role):
    """Set the role given upon verification (for API integration)."""
    if "verification" not in global_data: global_data["verification"] = {}
    if str(ctx.guild.id) not in global_data["verification"]: global_data["verification"][str(ctx.guild.id)] = {}
    
    global_data["verification"][str(ctx.guild.id)]["role_id"] = role.id
    await save_data()
    
    embed = discord.Embed(title="✅ Verification Role Set", description=f"The verification role is now {role.mention}.", color=discord.Color.green())
    add_branding(embed)
    await ctx.send(embed=embed)

@bot.command(name="setverifyguild")
@commands.has_permissions(administrator=True)
async def set_verify_guild(ctx):
    """Set this server as the active verification guild."""
    if "verification" not in global_data: global_data["verification"] = {}
    if str(ctx.guild.id) not in global_data["verification"]: global_data["verification"][str(ctx.guild.id)] = {}
    
    global_data["verification"][str(ctx.guild.id)]["guild_id"] = ctx.guild.id
    await save_data()
    
    embed = discord.Embed(title="✅ Verification Server Set", description=f"This server (`{ctx.guild.id}`) is now set for verification checks.", color=discord.Color.green())
    add_branding(embed)
    await ctx.send(embed=embed)

@bot.command(name="setting")
@commands.has_permissions(administrator=True)
async def setting_command(ctx):
    """Displays the server configuration/settings."""
    guild_id = str(ctx.guild.id)
    
    # Helper to get role mention or "None"
    def get_role_mention(key_path):
        rid = global_data.get(key_path, {}).get(guild_id)
        if rid:
            role = ctx.guild.get_role(rid)
            return role.mention if role else f"ID: {rid} (Deleted)"
        return "Not Set"

    # Helper for channel
    def get_channel_mention(key_path):
        cid = global_data.get(key_path, {}).get(guild_id)
        if cid:
            ch = ctx.guild.get_channel(cid)
            return ch.mention if ch else f"ID: {cid} (Deleted)"
        return "Not Set"

    embed = discord.Embed(title=f"⚙️ Settings for {ctx.guild.name}", color=discord.Color.dark_grey(), timestamp=discord.utils.utcnow())
    
    # 1. Moderation Settings
    mod_role = get_role_mention("moderator_roles")
    mod_log = get_channel_mention("modlog_channels")
    report_channel = get_channel_mention("report_channels")
    auto_mod_status = "Enabled" if ctx.guild.id not in global_data["disabled_automod_guilds"] else "Disabled"
    
    embed.add_field(name="🛡️ Moderation", value=(
        f"**Mod Role**: {mod_role}\n"
        f"**Mod Log**: {mod_log}\n"
        f"**Report Channel**: {report_channel}\n"
        f"**Auto-Mod**: {auto_mod_status}"
    ), inline=False)

    # 2. Ticket / Application Settings
    req_role = get_role_mention("required_apply_roles")
    ban_role = get_role_mention("banned_apply_roles")
    ticket_cat_id = global_data.get("ticket_categories", {}).get(guild_id)
    ticket_cat = ctx.guild.get_channel(ticket_cat_id).name if ticket_cat_id and ctx.guild.get_channel(ticket_cat_id) else "Not Set"
    
    # Ping Roles (List)
    ping_role_ids = global_data.get("ticket_ping_roles", {}).get(guild_id, [])
    ping_roles = []
    for rid in ping_role_ids:
        r = ctx.guild.get_role(rid)
        if r: ping_roles.append(r.mention)
    ping_roles_str = ", ".join(ping_roles) if ping_roles else "None"

    embed.add_field(name="🎟️ Tickets & Apps", value=(
        f"**Required Role**: {req_role}\n"
        f"**Banned Role**: {ban_role}\n"
        f"**Ticket Category**: {ticket_cat}\n"
        f"**Ping Roles**: {ping_roles_str}"
    ), inline=False)
    
    # 3. Verification
    verify_role_id = global_data.get("verification", {}).get(guild_id, {}).get("role_id")
    verify_role = ctx.guild.get_role(verify_role_id).mention if verify_role_id and ctx.guild.get_role(verify_role_id) else "Not Set"
    
    embed.add_field(name="✅ Verification", value=f"**Verified Role**: {verify_role}", inline=False)
    
    # 4. Anti-Nuke
    anti_nuke = get_anti_nuke_config(ctx.guild.id)
    embed.add_field(name="☢️ Anti-Nuke", value=f"**Status**: {'Enabled' if anti_nuke['enabled'] else 'Disabled'}\n**Punishment**: {anti_nuke['punishment']}", inline=False)

    embed.set_footer(text=f"Use the Dashboard command ({PREFIX}dashboard) to change these settings.")
    add_branding(embed)
    await ctx.send(embed=embed)




# ===== NEW UTILITY COMMANDS =====

@bot.command(name="botinfo")
async def bot_info(ctx):
    """Displays essential information about the bot."""
    embed = discord.Embed(
        title="Bot Information",
        description="A powerful moderation and utility bot for Discord.",
        color=discord.Color.blue(),
        timestamp=discord.utils.utcnow()
    )

    embed.add_field(name="Prefix", value=f"`{PREFIX}`", inline=True)
    embed.add_field(name="Library", value=f"discord.py v{discord.__version__}", inline=True)
    embed.add_field(name="Bot ID", value=bot.user.id, inline=True)
    
    uptime = discord.utils.utcnow() - bot.user.created_at
    embed.add_field(name="Bot Uptime", value=f"{uptime.days}d {uptime.seconds // 3600}h {(uptime.seconds % 3600) // 60}m", inline=False)
    
    member_count = sum(guild.member_count for guild in bot.guilds)
    embed.add_field(name="Servers/Users", value=f"{len(bot.guilds)} servers | {member_count} members", inline=True)

    embed.set_footer(text="Created by SPG-EMH")
    add_branding(embed)
    await ctx.send(embed=embed)

@bot.command(name="serversnapshot")
@commands.check(is_moderator)
async def server_snapshot(ctx):
    """
    Takes a snapshot of key server stats and logs it to the modlog channel.
    """
    await ctx.send("Gathering server snapshot data...", delete_after=5)
    
    guild = ctx.guild
    modlog = await get_modlog_channel(guild)
    
    if not modlog:
        await ctx.send("❌ Cannot perform snapshot: No modlog channel configured or created.")
        return

    # Count members
    total_members = guild.member_count
    bot_members = len([m for m in guild.members if m.bot])
    human_members = total_members - bot_members
    
    # Count channels
    text_channels = len(guild.text_channels)
    voice_channels = len(guild.voice_channels)
    
    # Anti-Nuke Status
    anti_nuke_config = get_anti_nuke_config(guild.id)
    nuke_status = "✅ Enabled" if anti_nuke_config["enabled"] else "❌ Disabled"
    
    # Moderation config
    mod_role_id = global_data["moderator_roles"].get(str(guild.id))
    mod_role = guild.get_role(mod_role_id) if mod_role_id else "Not Set"

    embed = discord.Embed(
        title=f"📸 Server Snapshot: {guild.name}",
        color=discord.Color.dark_teal(),
        timestamp=discord.utils.utcnow()
    )
    embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
    
    # General Stats
    embed.add_field(name="📊 General Stats", value=(
        f"**ID**: `{guild.id}`\n"
        f"**Owner**: {guild.owner.mention}\n"
        f"**Region**: {guild.preferred_locale}\n"
        f"**Created**: {guild.created_at.strftime('%b %d, %Y')}"
    ), inline=False)

    # Member Stats
    embed.add_field(name="👥 Member Count", value=(
        f"**Total Members**: {total_members}\n"
        f"**Humans**: {human_members}\n"
        f"**Bots**: {bot_members}"
    ), inline=True)
    
    # Channel Stats
    embed.add_field(name="💬 Channel Count", value=(
        f"**Text**: {text_channels}\n"
        f"**Voice**: {voice_channels}\n"
        f"**Categories**: {len(guild.categories)}"
    ), inline=True)

    # Bot Configuration
    embed.add_field(name="⚙️ Bot Configuration", value=(
        f"**Anti-Nuke Status**: {nuke_status}\n"
        f"**Mod Role**: {mod_role.mention if isinstance(mod_role, discord.Role) else mod_role}\n"
        f"**Auto-Mod**: {'❌ Disabled' if guild.id in global_data['disabled_automod_guilds'] else '✅ Enabled'}"
    ), inline=False)
    
    # Send to modlog
    add_branding(embed)
    await modlog.send(f"**Snapshot requested by** {ctx.author.mention}", embed=embed)
    await ctx.send(f"✅ Snapshot successfully logged to {modlog.mention}.")


@bot.command(name="nuke_channel")
@commands.has_permissions(administrator=True)
async def nuke_channel_command(ctx):
    """Deletes and recreates the current channel, effectively clearing all messages."""
    await ctx.send("⚠️ **WARNING**: This will delete all messages and settings in this channel and recreate it. Type `CONFIRM` to proceed.")
    
    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel and m.content == "CONFIRM"
        
    try:
        await bot.wait_for("message", check=check, timeout=15)
    except asyncio.TimeoutError:
        await ctx.send("❌ Timed out. Channel nuke cancelled.")
        return
    
    try:
        channel = ctx.channel
        new_channel = await channel.clone(reason=f"Channel nuked by {ctx.author.name}")
        await channel.delete(reason=f"Channel nuked by {ctx.author.name}")
        await new_channel.edit(position=channel.position) # Try to maintain position
        await new_channel.send("💥 **Channel Nuked!** All messages have been cleared.\nhttps://tenor.com/view/explosion-mushroom-cloud-atomic-bomb-bomb-boom-gif-4464831")
    except discord.Forbidden:
        await ctx.send("❌ I do not have the necessary permissions to nuke this channel (Manage Channels).")
    except Exception as e:
        await ctx.send(f"❌ An error occurred while nuking the channel: {e}")


# ===== MODERATION COMMANDS (UPDATED FOR global_data) =====
@bot.command(name="setmod")
@commands.has_permissions(administrator=True)
async def set_moderator_role(ctx, role: discord.Role):
    global_data["moderator_roles"][str(ctx.guild.id)] = role.id
    await save_data()
    await ctx.send(f"✅ **Moderator Role Set**: Members with the `{role.name}` role can now use mod commands.")

@bot.command(name="setmodlog")
@commands.has_permissions(administrator=True)
async def set_modlog_channel(ctx, channel: discord.TextChannel):
    global_data["modlog_channels"][str(ctx.guild.id)] = channel.id
    await save_data()
    await ctx.send(f"✅ **Modlog Channel Set**: All moderation actions will now be logged in {channel.mention}.")

@bot.command(name="setautomodexempt")
@commands.has_permissions(administrator=True)
async def set_automod_exempt(ctx, role: discord.Role):
    global_data["automod_exempt_roles"][str(ctx.guild.id)] = role.id
    await save_data()
    await ctx.send(f"✅ **Auto-Mod Exempt Role Set**: Members with the `{role.name}` role will now be ignored by the auto-moderation system.")

@bot.command(name="stopautomod")
@commands.has_permissions(administrator=True)
async def stop_automod(ctx):
    global_data["disabled_automod_guilds"].add(ctx.guild.id)
    await save_data()
    await ctx.send("✅ Auto-moderation has been **stopped** for this server.")

@bot.command(name="startautomod")
@commands.has_permissions(administrator=True)
async def start_automod(ctx):
    if ctx.guild.id in global_data["disabled_automod_guilds"]:
        global_data["disabled_automod_guilds"].remove(ctx.guild.id)
        await save_data()
        await ctx.send("✅ Auto-moderation has been **started** for this server.")
    else:
        await ctx.send("⚠️ Auto-moderation is already running.")

@bot.command(name="setpromotionchannel")
@commands.has_permissions(administrator=True)
async def set_promotion_channel(ctx, channel: discord.TextChannel):
    """Sets the channel where promotion/demotion announcements will be sent."""
    global_data["promotion_channels"][str(ctx.guild.id)] = channel.id
    await save_data()
    await ctx.send(f"✅ **Promotion Channel Set**: Announcements will now be sent to {channel.mention}")

@bot.command(name="setpromotiontext")
@commands.has_permissions(administrator=True)
async def set_promotion_text(ctx, *, template: str):
    """Sets the template for promotion messages. Use {member}, {old_role}, {new_role}, {mod}."""
    guild_id = str(ctx.guild.id)
    if guild_id not in global_data["promotion_templates"]:
        global_data["promotion_templates"][guild_id] = {}
    global_data["promotion_templates"][guild_id]["promote"] = template
    await save_data()
    await ctx.send("✅ **Promotion Template Updated**.")

@bot.command(name="setdemotiontext")
@commands.has_permissions(administrator=True)
async def set_demotion_text(ctx, *, template: str):
    """Sets the template for demotion messages. Use {member}, {old_role}, {new_role}, {mod}."""
    guild_id = str(ctx.guild.id)
    if guild_id not in global_data["promotion_templates"]:
        global_data["promotion_templates"][guild_id] = {}
    global_data["promotion_templates"][guild_id]["demote"] = template
    await save_data()
    await ctx.send("✅ **Demotion Template Updated**.")

@bot.command(name="setnotify")
@commands.has_permissions(administrator=True)
async def set_youtube_notify(ctx, channel: discord.TextChannel):
    """Sets the channel for YouTube notifications."""
    guild_id = str(ctx.guild.id)
    if "youtube_notifications" not in global_data:
        global_data["youtube_notifications"] = {}
    if guild_id not in global_data["youtube_notifications"]:
        global_data["youtube_notifications"][guild_id] = {"channel_id": None, "creators": {}}
    
    global_data["youtube_notifications"][guild_id]["channel_id"] = channel.id
    await save_data()
    embed = discord.Embed(title="✅ Notification Channel Set", description=f"YouTube notifications will now be sent to {channel.mention}", color=discord.Color.green())
    add_branding(embed)
    await ctx.send(embed=embed)

async def get_youtube_channel_id(url_or_handle):
    """Deep search for a YouTube Channel ID from a handle or link."""
    url = url_or_handle.strip()
    
    # Check if it's already a raw Channel ID (UC...)
    if len(url) == 24 and url.startswith("UC"):
        return url
    if url.startswith("@"):
        url = f"https://www.youtube.com/{url}"
    elif not url.startswith("http"):
        if "@" in url: url = f"https://www.youtube.com/@{url.split('@')[1]}"
        else: url = f"https://www.youtube.com/channel/{url}"

    if "youtube.com/channel/" in url:
        return url.split("youtube.com/channel/")[1].split("/")[0].split("?")[0]
    
    async with aiohttp.ClientSession() as session:
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
            async with session.get(url, headers=headers, timeout=10) as resp:
                if resp.status == 200:
                    html = await resp.text()
                    # RSS
                    match = re.search(r'href="https://www.youtube.com/feeds/videos.xml\?channel_id=([^"]+)"', html)
                    if match: return match.group(1)
                    # Meta
                    match = re.search(r'meta itemprop="identifier" content="([^"]+)"', html)
                    if match: return match.group(1)
                    # JS
                    match = re.search(r'"channelId":"(UC[^"]+)"', html)
                    if match: return match.group(1)
                    # external
                    match = re.search(r'"externalId":"(UC[^"]+)"', html)
                    if match: return match.group(1)
        except: pass
    return None

@bot.command(name="addyoutube")
@commands.has_permissions(administrator=True)
async def add_youtube_creator(ctx, url: str):
    """Adds a YouTube channel to the monitor list."""
    channel_id = await get_youtube_channel_id(url)

    if not channel_id or not channel_id.startswith("UC"):
        await ctx.send("❌ Could not extract YouTube Channel ID. Please ensure the link or handle is correct (e.g., `https://youtube.com/@user` or just `@user`).")
        return

    guild_id = str(ctx.guild.id)
    if "youtube_notifications" not in global_data:
        global_data["youtube_notifications"] = {}
    if guild_id not in global_data["youtube_notifications"]:
        global_data["youtube_notifications"][guild_id] = {"channel_id": None, "creators": {}}
    
    # Get latest video to set baseline
    latest = await yt_monitor.get_latest_video(channel_id)
    last_id = latest["id"] if latest else None
    
    global_data["youtube_notifications"][guild_id]["creators"][channel_id] = {
        "name": latest["title"] if latest else "Unknown Creator",
        "last_video_id": last_id,
        "processed_videos": [last_id] if last_id else []
    }
    await save_data()
    await ctx.send(f"✅ Added YouTube channel (ID: `{channel_id}`) to the monitor list. Baseline set to current latest video.")

@bot.command(name="removeyoutuber")
@commands.has_permissions(administrator=True)
async def remove_youtube_creator(ctx, url_or_id: str):
    """Removes a YouTube channel from the monitor list."""
    guild_id = str(ctx.guild.id)
    if "youtube_notifications" not in global_data or guild_id not in global_data["youtube_notifications"]:
        await ctx.send("❌ No YouTube channels registered for this server.")
        return
    
    to_remove = None
    creators = global_data["youtube_notifications"][guild_id]["creators"]
    
    # Try direct ID match first
    if url_or_id in creators:
        to_remove = url_or_id
    else:
        # Try to resolve handle/URL to ID
        resolved_id = await get_youtube_channel_id(url_or_id)
        if resolved_id and resolved_id in creators:
            to_remove = resolved_id
        else:
            # Fallback to name search
            search_term = url_or_id.lower().replace("@", "")
            for cid, data in creators.items():
                if search_term in cid.lower() or search_term in data["name"].lower():
                    to_remove = cid
                    break
    
    if to_remove:
        del creators[to_remove]
        await save_data()
        await ctx.send(f"✅ Removed YouTube channel from monitor.")
    else:
        await ctx.send("❌ Could not find that YouTube channel in the list.")

@bot.command(name="setyoutubetext")
@commands.has_permissions(administrator=True)
async def set_youtube_text(ctx, *, template: str):
    """Sets the template for YouTube notifications. Use {name}, {title}, {url}."""
    global_data["youtube_templates"][str(ctx.guild.id)] = template
    await save_data()
    await ctx.send("✅ **YouTube Notification Template Updated**.")

@bot.command(name="testyoutube")
@commands.has_permissions(administrator=True)
async def test_youtube_system(ctx):
    """Tests if the YouTube notification system is ready."""
    guild_id = str(ctx.guild.id)
    config = global_data.get("youtube_notifications", {}).get(guild_id)
    
    if not config:
        await ctx.send("⚠️ YouTube system is NOT configured for this server. Use `spg setnotify` and `spg addyoutube`.")
        return
    
    channel = ctx.guild.get_channel(config.get("channel_id"))
    creators = config.get("creators", {})
    
    embed = discord.Embed(title="📺 YouTube System Diagnostic", color=discord.Color.red())
    embed.add_field(name="Notify Channel", value=channel.mention if channel else "❌ Not Set", inline=True)
    embed.add_field(name="Monitored Channels", value=str(len(creators)), inline=True)
    
    if creators:
        creator_list = "\n".join([f"• {data.get('name', 'Unknown')} (`{cid}`)" for cid, data in creators.items()])
        embed.add_field(name="Creators List", value=creator_list[:1024], inline=False)
    
    add_branding(embed)
    await ctx.send(embed=embed)

@bot.command(name="sendlatestvideo")
@commands.has_permissions(administrator=True)
async def send_latest_video(ctx, *, url_or_query: str):
    """Manually fetches and sends the latest video from a monitored creator."""
    guild_id = str(ctx.guild.id)
    config = global_data.get("youtube_notifications", {}).get(guild_id)
    
    if not config:
        await ctx.send("⚠️ YouTube system is NOT configured. Use `spg setnotify` and `spg addyoutube`.")
        return
    
    channel = ctx.guild.get_channel(config.get("channel_id"))
    if not channel:
        await ctx.send("❌ Notification channel not found.")
        return
        
    creators = config.get("creators", {})
    target_id = None
    
    # 1. Direct ID match
    if url_or_query in creators:
        target_id = url_or_query
    else:
        # 2. Resolve URL/Handle
        target_id = await get_youtube_channel_id(url_or_query)
        if not (target_id and target_id in creators):
            # 3. Search by Name
            query = url_or_query.lower().replace("@", "")
            for cid, data in creators.items():
                if query in cid.lower() or query in data.get("name", "").lower():
                    target_id = cid
                    break
    
    if not target_id:
        await ctx.send("❌ Creator not found in your monitored list.")
        return
        
    await ctx.send(f"🔍 Fetching latest video for **{creators[target_id].get('name', 'Unknown')}**...")
    
    latest = await yt_monitor.get_latest_video(target_id)
    if not latest:
        await ctx.send("❌ Failed to fetch latest video from YouTube API/RSS.")
        return
        
    creator_name = creators[target_id].get("name", "Unknown")
    video_url = f"https://www.youtube.com/watch?v={latest['id']}"
    video_title = latest.get("title", "Unknown Title")
    
    template = global_data.get("youtube_templates", {}).get(guild_id)
    if template:
        msg = template.replace("{name}", creator_name).replace("{title}", video_title).replace("{url}", video_url)
    else:
        msg = f"🚨 **MANUAL NOTIFICATION: {creator_name}**\n{video_url}\n@everyone"
        
    try:
        await channel.send(msg)
        await ctx.send(f"✅ Successfully sent manual alert for: **{video_title}**")
    except Exception as e:
        await ctx.send(f"❌ Failed to send message: {e}")

@bot.command(name="addrole")
@commands.has_permissions(manage_roles=True)
async def add_role_command(ctx, member: discord.Member, role: discord.Role):
    if ctx.author.top_role <= member.top_role:
        await ctx.send("❌ You cannot manage roles for a user with an equal or higher role than yourself.")
        return
    if role >= ctx.guild.me.top_role:
        await ctx.send("❌ I cannot manage roles that are equal to or higher than my own role.")
        return
    try:
        await member.add_roles(role)
        await ctx.send(f"✅ Successfully added role `{role.name}` to {member.mention}.")
        await log_monitor_event(ctx.guild, "📈 Role Added (Command)", f"**Target:** {member.mention}\n**Role:** {role.mention}\n**By:** {ctx.author.mention}", discord.Color.green())
    except discord.Forbidden:
        await ctx.send("❌ I don't have permission to add that role.")

@bot.command(name="removerole")
@commands.has_permissions(manage_roles=True)
async def remove_role_command(ctx, member: discord.Member, role: discord.Role):
    if ctx.author.top_role <= member.top_role:
        await ctx.send("❌ You cannot manage roles for a user with an equal or higher role than yourself.")
        return
    if role >= ctx.guild.me.top_role:
        await ctx.send("❌ I cannot manage roles that are equal to or higher than my own role.")
        return
    try:
        await member.remove_roles(role)
        await ctx.send(f"✅ Successfully removed role `{role.name}` from {member.mention}.")
        await log_monitor_event(ctx.guild, "📉 Role Removed (Command)", f"**Target:** {member.mention}\n**Role:** {role.mention}\n**By:** {ctx.author.mention}", discord.Color.red())
    except discord.Forbidden:
        await ctx.send("❌ I don't have permission to remove that role.")


@bot.command(name="checkwarn")
@commands.check(is_moderator)
async def check_warn_command(ctx, member: discord.Member):
    warn_count = global_data["warns"].get(str(member.id), 0)
    await ctx.send(f"📝 {member.mention} currently has {warn_count} warnings.")



@bot.command(name="modpanel")
@commands.check(is_moderator)
async def mod_panel(ctx, member: discord.Member):
    if member.id == ctx.author.id:
        await ctx.send("❌ You cannot moderate yourself.")
        return
    if member.top_role >= ctx.author.top_role and member.id != ctx.guild.owner_id:
        await ctx.send("❌ You cannot moderate a member with an equal or higher role.")
        return
        
    embed = discord.Embed(
        title=f"Moderation Panel for {member.name}",
        description=f"Select an action to perform on {member.mention}.",
        color=discord.Color.orange()
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="User ID", value=member.id)
    embed.add_field(name="Current Warnings", value=global_data["warns"].get(str(member.id), 0))
    add_branding(embed)
    await ctx.send(embed=embed, view=ModPanelView(author=ctx.author, target=member))

@bot.command()
@commands.check(is_moderator)
async def warn(ctx, member: discord.Member, *, reason: str = "No reason provided."):
    """Warn a member after hierarchy check (Requires Governor approval for Mods)."""
    h_check = await check_hierarchy(ctx.author, member)
    if h_check is not True: return await ctx.send(h_check)
    
    # Forced Approval for MOD_ROLE
    if await needs_approval(ctx.author):
        view = ModApprovalView("warn", ctx.author, member, reason)
        embed = discord.Embed(title="🛡️ Warning Approval Required", color=discord.Color.orange())
        embed.description = (f"**Moderator:** {ctx.author.mention}\n"
                           f"**Target:** {member.mention}\n"
                           f"**Reason:** {reason}\n\n"
                           f"*Staff with the **Governor** role must approve this warning.*")
        add_branding(embed)
        await ctx.send(embed=embed, view=view)
        return

    await warn_user(ctx.channel, member, reason, mod=ctx.author)
    await ctx.send(f"✅ Warned {member.mention}.")

@bot.command(name="ban")
@commands.check(is_moderator)
async def ban_command(ctx, user: discord.User, *, reason: str = "No reason provided"): # Changed member -> user
    """Ban a user by Mention or ID with Approval requirements."""
    # Hierarchy Check (if member is in guild)
    if isinstance(user, discord.Member):
        h_check = await check_hierarchy(ctx.author, user)
        if h_check is not True: return await ctx.send(h_check)

    # Mandatory Approval (Zero-Trust)
    if await needs_approval(ctx.author):
        view = ModApprovalView("ban", ctx.author, user, reason)
        embed = discord.Embed(title="🔒 Ban Approval Required", color=discord.Color.orange())
        embed.description = (f"**Moderator:** {ctx.author.mention}\n"
                           f"**Target:** {user.mention} (`{user.id}`)\n"
                           f"**Reason:** {reason}\n\n"
                           f"*Staff with the **Governor** role must approve this action.*")
        add_branding(embed)
        await ctx.send(embed=embed, view=view)
        return

    try:
        await ctx.guild.ban(user, reason=f"{reason} (By {ctx.author.name})")
        await ctx.send(f"🔨 **Banned** {user.mention}.")
        modlog = await get_modlog_channel(ctx.guild)
        if modlog: await modlog.send(f"🔨 **Banned**: {user.mention} (`{user.id}`) | By: {ctx.author.mention} | Reason: {reason}")
    except discord.Forbidden:
        await ctx.send("❌ I don't have permissions to ban members.")
    except Exception as e:
        await ctx.send(f"❌ Failed to ban: {e}")

@bot.command()
@commands.check(is_moderator)
async def kick(ctx, member: discord.Member, *, reason: str = "No reason provided."):
    """Kick a member with Approval requirements."""
    # Hierarchy Check
    h_check = await check_hierarchy(ctx.author, member)
    if h_check is not True: return await ctx.send(h_check)

    # Mandatory Approval (Zero-Trust)
    if await needs_approval(ctx.author):
        view = ModApprovalView("kick", ctx.author, member, reason)
        embed = discord.Embed(title="🔒 Kick Approval Required", color=discord.Color.orange())
        embed.description = (f"**Moderator:** {ctx.author.mention}\n"
                           f"**Target:** {member.mention} (`{member.id}`)\n"
                           f"**Reason:** {reason}\n\n"
                           f"*Staff with the **Governor** role must approve this action.*")
        add_branding(embed)
        await ctx.send(embed=embed, view=view)
        return

    try:
        await member.kick(reason=f"Kicked by {ctx.author.name}: {reason}")
        await ctx.send(f"👢 {member.mention} has been kicked.")
        modlog = await get_modlog_channel(ctx.guild)
        if modlog: await modlog.send(f"👢 **Kicked**: {member.mention} | By: {ctx.author.mention} | Reason: {reason}")
    except discord.Forbidden:
        await ctx.send("❌ I don't have permission to kick this member.")

@bot.command(name="unban")
@commands.check(is_moderator)
async def unban_command(ctx, *, user: discord.User): # Changed to discord.User to accept ID/mention
    """Unban a user by ID or Mention."""
    try:
        await ctx.guild.unban(user, reason=f"Unbanned by {ctx.author.name}")
        await ctx.send(f"✅ Unbanned {user.mention} (`{user.id}`).")
        modlog = await get_modlog_channel(ctx.guild)
        if modlog: await modlog.send(f"✅ **Unbanned**: {user.mention} (`{user.id}`) | By: {ctx.author.mention}")
    except discord.NotFound:
        await ctx.send("❌ User is not banned.")
    except Exception as e:
        await ctx.send(f"❌ Failed to unban: {e}")

@bot.command()
@commands.check(is_moderator)
async def purge(ctx, amount: int):
    if amount <= 0:
        await ctx.send("❌ Amount must be a positive number.")
        return
    if amount > 100:
        await ctx.send("❌ Cannot delete more than 100 messages at once.")
        return
    try:
        deleted = await ctx.channel.purge(limit=amount + 1)
        await ctx.send(f"✅ Deleted {len(deleted) - 1} messages.", delete_after=5)
    except discord.Forbidden:
        await ctx.send("❌ I don't have permission to manage messages.")

@bot.command(name="tempban")
@commands.check(is_moderator)
async def tempban_command(ctx, member: discord.User, duration_str: str, *, reason: str = "Temporary Ban"):
    """
    Temporarily ban a user.
    Usage: !tempban @user 1d Rule violation
    """
    # ... logic remains mostly the same, but using discord.User allows banning people not in server
    # However, ctx.guild.ban(member) works with discord.User too.
    
    # Parse duration
    try:
        duration = int(duration_str[:-1])
        unit = duration_str[-1]
    except:
         await ctx.send("❌ Invalid duration. Example: 1d, 12h, 30m.")
         return
         
    seconds = 0
    if unit == "m": seconds = duration * 60
    elif unit == "h": seconds = duration * 3600
    elif unit == "d": seconds = duration * 86400
    elif unit == "w": seconds = duration * 604800
    
    try:
        await ctx.guild.ban(member, reason=f"Tempbanned by {ctx.author.name}: {reason}")
        await ctx.send(f"🚫 {member.mention} has been banned for {duration}{unit}.")
        modlog = await get_modlog_channel(ctx.guild)
        if modlog: await modlog.send(f"🚫 **Temp-Banned**: {member.mention} for {duration}{unit} | By: {ctx.author.mention} | Reason: {reason}")
        
        await asyncio.sleep(seconds)
        
        try:
             await ctx.guild.unban(member, reason="Temporary ban expired")
             if modlog: await modlog.send(f"✅ **Unbanned**: {member.mention} (temp-ban expired)")
        except:
             pass # Maybe they were already unbanned
             
    except discord.Forbidden:
        await ctx.send("❌ I don't have permissions to ban/unban members.")
    except Exception as e:
        await ctx.send(f"❌ Error: {e}")


# ===== NEW COMMANDS: BADGE, BLACKLIST, MESSAGING (UPDATED FOR global_data) =====

@bot.command(name="givebadge")
@commands.check(is_moderator)
async def give_badge(ctx, member: discord.Member):
    """Generate and assign a badge to a user. Moderator only."""
    uid = str(member.id)
    badges_data = global_data["badges"]
    
    old = badges_data.get(uid)
    new_badge = generate_badge()
    badges_data[uid] = {"badge": new_badge, "assigned_by": ctx.author.id, "timestamp": discord.utils.utcnow().isoformat()}
    await save_data()
    
    e = discord.Embed(title="Badge Assigned", color=discord.Color.green(), timestamp=discord.utils.utcnow())
    e.add_field(name="User", value=f"{member.mention} (`{member.id}`)", inline=False)
    e.add_field(name="Badge", value=new_badge, inline=True)
    e.add_field(name="Assigned by", value=ctx.author.mention, inline=True)
    if old:
        e.set_footer(text=f"Note: Overwrote previous badge: {old.get('badge')}")
    add_branding(e)
    await ctx.send(embed=e)
    try:
        dm = discord.Embed(title="You received a badge!", color=discord.Color.blue(), timestamp=discord.utils.utcnow())
        dm.add_field(name="Badge", value=new_badge, inline=False)
        dm.add_field(name="Assigned by", value=ctx.author.name, inline=False)
        dm.set_footer(text=f"Keep this badge safe — use {PREFIX}mybadge to view it anytime.")
        await member.send(embed=dm)
    except Exception:
        pass

@bot.command(name="mybadge")
async def my_badge(ctx):
    """Show your assigned badge (if any)."""
    uid = str(ctx.author.id)
    data = global_data["badges"].get(uid)
    
    if not data:
        e = discord.Embed(title="No Badge Found", description="You don't have a badge assigned yet.", color=discord.Color.greyple(), timestamp=discord.utils.utcnow())
        e.add_field(name="How to get one", value=f"Ask a moderator to run `{PREFIX}givebadge @you`", inline=False)
        await ctx.send(embed=e)
        return
    e = discord.Embed(title="Your Badge", color=discord.Color.gold(), timestamp=discord.utils.utcnow())
    e.add_field(name="Badge", value=data["badge"], inline=True)
    assigned_by = data.get("assigned_by")
    if assigned_by:
        e.add_field(name="Assigned by", value=f"<@{assigned_by}>", inline=True)
    e.add_field(name="Assigned at", value=data.get("timestamp", "Unknown"), inline=False)
    add_branding(e)
    await ctx.send(embed=e)

# Blacklist management
@bot.command(name="addblacklist")
@commands.check(is_moderator)
async def add_blacklist(ctx, user: str, *, reason: str = "No reason provided."):
    """Blacklist a user by Mention, ID, or Name. Works even if they aren't in the server."""
    uid = user
    # Try to extract ID from mention or use raw string
    if user.startswith("<@") and user.endswith(">"):
        uid = user.strip("<@!>")
    
    if not uid.isdigit():
        await ctx.send("❌ Please provide a valid User ID or Mention.")
        return

    blacklist_data = global_data["blacklist"]

    if uid in blacklist_data:
        # Try to resolve name for display
        try: member = await bot.fetch_user(int(uid))
        except: member = f"ID: {uid}"
        
        e = discord.Embed(title="Already Blacklisted", color=discord.Color.orange(), timestamp=discord.utils.utcnow())
        e.add_field(name="User", value=f"{member} (`{uid}`)", inline=False)
        e.add_field(name="Existing Reason", value=blacklist_data[uid].get("reason", "Unknown"), inline=False)
        await ctx.send(embed=e)
        return
    
    blacklist_data[uid] = {"reason": reason, "added_by": ctx.author.id, "timestamp": discord.utils.utcnow().isoformat()}
    await save_data()
    
    try: member = await bot.fetch_user(int(uid))
    except: member = f"ID: {uid}"

    e = discord.Embed(title="User Blacklisted", color=discord.Color.red(), timestamp=discord.utils.utcnow())
    e.add_field(name="User", value=f"{member} (`{uid}`)", inline=False)
    e.add_field(name="Reason", value=reason, inline=False)
    e.add_field(name="Added by", value=ctx.author.mention, inline=True)
    add_branding(e)
    await ctx.send(embed=e)
    modlog = await get_modlog_channel(ctx.guild)
    if modlog:
        await modlog.send(embed=e)
        
    # Attempt to kick if they are in the server
    guild_member = ctx.guild.get_member(int(uid))
    if guild_member:
        try: 
            await guild_member.kick(reason=f"Blacklisted: {reason}")
            await ctx.send(f"👢 Auto-kicked {guild_member.mention}.")
        except: 
            pass

@bot.command(name="removeblacklist")
@commands.check(is_moderator)
async def remove_blacklist(ctx, user: str):
    """Remove a user from the blacklist by ID or Mention."""
    uid = user
    if user.startswith("<@") and user.endswith(">"):
        uid = user.strip("<@!>")
        
    if not uid.isdigit():
        await ctx.send("❌ Invalid ID.")
        return

    blacklist_data = global_data["blacklist"]

    if uid not in blacklist_data:
        await ctx.send(f"❌ ID `{uid}` is not on the blacklist.")
        return
    
    old = blacklist_data.pop(uid)
    await save_data()
    
    try: member = await bot.fetch_user(int(uid))
    except: member = f"ID: {uid}"
    
    e = discord.Embed(title="Removed from Blacklist", color=discord.Color.green(), timestamp=discord.utils.utcnow())
    e.add_field(name="User", value=f"{member} (`{uid}`)", inline=False)
    e.add_field(name="Old Reason", value=old.get("reason", "Unknown"), inline=False)
    e.add_field(name="Removed by", value=ctx.author.mention, inline=True)
    await ctx.send(embed=e)
    modlog = await get_modlog_channel(ctx.guild)
    if modlog:
        await modlog.send(embed=e)

@bot.command(name="checkblacklist")
@commands.check(is_moderator)
async def check_blacklist_embed(ctx, member: discord.Member):
    """Responds in embed format with blacklist status for the specified user."""
    uid = str(member.id)
    blacklist_data = global_data["blacklist"]

    if uid in blacklist_data:
        data = blacklist_data[uid]
        e = discord.Embed(title="Blacklist Status: ❌ Blacklisted", color=discord.Color.red(), timestamp=discord.utils.utcnow())
        e.add_field(name="User", value=f"{member.mention} (`{member.id}`)", inline=False)
        e.add_field(name="Reason", value=data.get("reason", "No reason provided."), inline=False)
        e.add_field(name="Added by", value=f"<@{data.get('added_by')}>", inline=True)
        e.add_field(name="When", value=data.get("timestamp"), inline=True)
        await ctx.send(embed=e)
    else:
        e = discord.Embed(title="Blacklist Status: ✅ Not Blacklisted", color=discord.Color.green(), timestamp=discord.utils.utcnow())
        e.add_field(name="User", value=f"{member.mention} (`{member.id}`)", inline=False)
        e.add_field(name="Note", value="This user is not present in the blacklist.", inline=False)
        await ctx.send(embed=e)

# Messaging commands

@bot.command(name="send")
@commands.check(is_moderator)
async def send_message_to_user(ctx, user: discord.User, *, text: str):
    """Send a custom message to a user by ID or Mention."""
    try:
        # User is already converted
        await user.send(text)
        e = discord.Embed(title="Message Sent", color=discord.Color.green(), timestamp=discord.utils.utcnow())
        e.add_field(name="Recipient", value=f"{user.mention} (`{user.id}`)", inline=False)
        e.add_field(name="Message", value=text[:1000], inline=False)
        await ctx.send(embed=e)
    except Exception as e:
        await ctx.send(f"❌ Failed to send message: {e}")

@bot.command(name="announcement")
@commands.check(is_moderator)
async def announcement_command(ctx, channel: discord.TextChannel, *, text: str):
    """Sends an announcement to a specific channel."""
    try:
        embed = discord.Embed(title="📢 Announcement", description=text, color=discord.Color.green())
        embed.set_footer(text=f"Sent by {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)
        add_branding(embed)
        await channel.send(embed=embed)
        await ctx.send(f"✅ Announcement sent to {channel.mention}.")
    except discord.Forbidden:
        await ctx.send(f"❌ I don't have permission to send messages in {channel.mention}.")
    except Exception as e:
        await ctx.send(f"❌ Failed to send announcement: {e}")

PRESET_MESSAGES = {
    "approved": "You are approved to join SPG. Welcome! Please follow server rules and reach out to staff for next steps.",
    "blacklisted": "You are on the SPG blacklist. You are not allowed to join the team or request roles.",
    "kicked": "You have been kicked from SPG. Contact staff if you believe this was a mistake.",
    "welcome": "Welcome to SPG! Read the rules and verify to get access.",
    "info": "Information: Please follow staff instructions and ensure your account is secure."
}

@bot.command(name="sendpreset")
@commands.check(is_moderator)
async def send_preset(ctx, user_id: int, preset: str):
    preset_key = preset.lower()
    if preset_key not in PRESET_MESSAGES:
        await ctx.send(f"❌ Unknown preset. Available: {', '.join(PRESET_MESSAGES.keys())}")
        return
    try:
        user = await bot.fetch_user(user_id)
        await user.send(PRESET_MESSAGES[preset_key])
        e = discord.Embed(title="Preset Message Sent", color=discord.Color.green(), timestamp=discord.utils.utcnow())
        e.add_field(name="Recipient", value=f"{user} (`{user.id}`)", inline=False)
        e.add_field(name="Preset", value=preset_key, inline=True)
        e.add_field(name="Message", value=PRESET_MESSAGES[preset_key], inline=False)
        await ctx.send(embed=e)
    except Exception as e:
        await ctx.send(f"❌ Failed to send preset message: {e}")
        
@bot.command(name="poll")
@commands.has_permissions(manage_messages=True)
async def create_poll(ctx, *, question: str):
    """Create a simple Yes/No poll."""
    e = discord.Embed(title="📊 Poll", description=question, color=discord.Color.gold(), timestamp=discord.utils.utcnow())
    e.set_footer(text=f"Asked by {ctx.author.name}")
    add_branding(e)
    msg = await ctx.send(embed=e)
    await msg.add_reaction("👍")
    await msg.add_reaction("👎")

@bot.command(name="serverinfo")
async def server_info(ctx):
    """View detailed statistics about the current server."""
    guild = ctx.guild
    e = discord.Embed(title=f"ℹ️ {guild.name}", color=discord.Color.blurple(), timestamp=discord.utils.utcnow())
    if guild.icon: e.set_thumbnail(url=guild.icon.url)
    
    e.add_field(name="Owner", value=guild.owner.mention, inline=True)
    e.add_field(name="Created On", value=guild.created_at.strftime("%b %d, %Y"), inline=True)
    e.add_field(name="Members", value=f"{guild.member_count}", inline=True)
    e.add_field(name="Roles", value=f"{len(guild.roles)}", inline=True)
    e.add_field(name="Channels", value=f"{len(guild.channels)}", inline=True)
    e.add_field(name="Boosts", value=f"Level {guild.premium_tier} ({guild.premium_subscription_count} boosts)", inline=True)
    
    add_branding(e)
    await ctx.send(embed=e)

@bot.command(name="whois")
async def whois_user(ctx, member: discord.Member = None):
    """Alias for userinfo."""
    member = member or ctx.author
    # Reuse existing userinfo logic by invoking it directly or copying logic. 
    # For simplicity, we'll re-implement a robust view here or alias the command.
    await user_info_logic(ctx, member)

async def user_info_logic(ctx, member):
    # 1. Key Permissions
    permissions = []
    if member.guild_permissions.administrator: permissions.append("Administrator")
    if member.guild_permissions.ban_members: permissions.append("Ban Members")
    if member.guild_permissions.kick_members: permissions.append("Kick Members")
    if member.guild_permissions.manage_guild: permissions.append("Manage Server")
    if member.guild_permissions.manage_channels: permissions.append("Manage Channels")
    if member.guild_permissions.manage_roles: permissions.append("Manage Roles")
    perm_str = ", ".join(permissions) if permissions else "None (Regular User)"

    # 2. Account Age & Join Order
    now = discord.utils.utcnow()
    created_at = member.created_at
    acc_age = now - created_at
    join_age = now - member.joined_at
    
    # Calculate Join Position
    sorted_members = sorted(ctx.guild.members, key=lambda m: m.joined_at)
    join_pos = sorted_members.index(member) + 1

    # 3. Public Flags
    flags = [flag[0] for flag in member.public_flags if flag[1]]
    flags_str = ", ".join(flags).replace("_", " ").title() if flags else "None"

    # 4. Message Activity (Phase 7)
    activity_count = 0
    if "server_activity" in global_data and str(ctx.guild.id) in global_data["server_activity"]:
        activity_count = global_data["server_activity"][str(ctx.guild.id)].get(str(member.id), 0)

    roles = [role.mention for role in member.roles if role.name != "@everyone"]
    roles_str = ", ".join(roles) if roles else "None"
    
    e = discord.Embed(title=f"👤 {member.name}", color=member.color, timestamp=now)
    e.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)
    e.set_footer(text=f"Requested by {ctx.author.name}")
    
    e.add_field(name="🆔 ID", value=member.id, inline=True)
    e.add_field(name="📛 Account Age", value=f"{acc_age.days} days\n({created_at.strftime('%Y-%m-%d')})", inline=True)
    e.add_field(name="📥 Joined Server", value=f"#{join_pos} ({join_age.days} days ago)\n{member.joined_at.strftime('%Y-%m-%d')}", inline=True)
    
    e.add_field(name="📨 Activity", value=f"**{activity_count}** messages", inline=True)
    e.add_field(name="🔑 Key Permissions", value=f"`{perm_str}`", inline=False)
    e.add_field(name="🚩 Public Flags", value=f"`{flags_str}`", inline=False)
    
    # Truncate roles if too long
    if len(roles_str) > 1000: roles_str = roles_str[:1000] + "..."
    e.add_field(name=f"🎭 Roles ({len(roles)})", value=roles_str, inline=False)
    
    add_branding(e)
    await ctx.send(embed=e)

@bot.command(name="spgscan")
@commands.has_permissions(administrator=True)
async def spg_scan_security(ctx):
    """
    Audits the server for security risks (Dangerous Admins, Open Permissions).
    """
    await ctx.send("🕵️ Scanning server security... Please wait.")
    
    dangerous_perms = ["administrator", "manage_guild", "ban_members", "kick_members", "manage_roles", "manage_channels"]
    risky_users = {}
    risky_bots = {}
    
    # Scan Members
    for member in ctx.guild.members:
        user_risks = []
        for perm in dangerous_perms:
            if getattr(member.guild_permissions, perm):
                user_risks.append(perm.replace("_", " ").title())
        
        if user_risks:
            risk_entry = f"Has: {', '.join(user_risks)}"
            if member.bot:
                risky_bots[member.name] = risk_entry
            else:
                risky_users[member.name] = risk_entry

    # Calculate Score
    # Base 100, minus 5 for every risky human admin (excluding owner), minus 2 for every risky bot
    score = 100
    owner_id = ctx.guild.owner_id
    
    # Count risky humans excluding owner
    risky_humans_count = sum(1 for m in ctx.guild.members if m.id != owner_id and not m.bot and m.guild_permissions.administrator)
    
    score -= (risky_humans_count * 5)
    score = max(0, score) # No negative scores

    # Generate Report
    e = discord.Embed(title="🛡️ SPG Security Audit", color=discord.Color.dark_red() if score < 70 else discord.Color.green(), timestamp=discord.utils.utcnow())
    e.description = f"**Security Score:** `{score}/100`\n"
    if score < 100:
        e.description += "⚠️ Risks detected! Review the list below."
    else:
        e.description += "✅ Excellent! Only necessary people have power."

    # List Risky Humans
    if risky_users:
        users_desc = ""
        for name, reason in list(risky_users.items())[:10]: # Limit to 10
            users_desc += f"**{name}**: {reason}\n"
        if len(risky_users) > 10: users_desc += f"...and {len(risky_users)-10} others."
        e.add_field(name=f"👤 Risky Users ({len(risky_users)})", value=users_desc, inline=False)

    # List Risky Bots
    if risky_bots:
         bots_desc = ""
         for name, reason in list(risky_bots.items())[:5]:
             bots_desc += f"**{name}**: {reason}\n"
         e.add_field(name=f"🤖 Privileged Bots ({len(risky_bots)})", value=bots_desc, inline=False)
    
    # Activity Report (Phase 7)
    if "server_activity" in global_data:
        activity_data = global_data["server_activity"].get(str(ctx.guild.id), {})
        total_msgs = sum(activity_data.values())
        
        # Sort by count descending
        sorted_users = sorted(activity_data.items(), key=lambda x: x[1], reverse=True)[:5]
        
        report_lines = []
        for uid, count in sorted_users:
            member = ctx.guild.get_member(int(uid))
            name = member.name if member else f"Unknown ({uid})"
            report_lines.append(f"**{name}**: {count} msgs")
            
        e.add_field(name=f"📊 Activity Report (Total: {total_msgs})", value="\n".join(report_lines) or "No activity recorded yet.", inline=False)

    e.set_footer(text="Tip: Only give 'Administrator' to people you trust with your life.")
    add_branding(e)
    await ctx.send(embed=e)

@bot.command(name="userinfo")
async def user_info_command(ctx, member: discord.Member = None):
    await user_info_logic(ctx, member or ctx.author)

@bot.command(name="listbadges")
@commands.check(is_moderator)
async def list_badges(ctx):
    """Moderator-only: list currently assigned badges (small summary)."""
    badges_data = global_data["badges"]
    
    if not badges_data:
        await ctx.send("No badges assigned.")
        return
    e = discord.Embed(title="Assigned Badges", color=discord.Color.blurple(), timestamp=discord.utils.utcnow())
    count = 0
    # Show up to 25 badges in the list
    for uid, data in list(badges_data.items())[:25]:
        count += 1
        member = ctx.guild.get_member(int(uid))
        name = member.name if member else uid
        e.add_field(name=name, value=data.get("badge"), inline=True)
        
    e.set_footer(text=f"Showing {count} of {len(badges_data)} badges")
    await ctx.send(embed=e)

# ===== OFFICIAL CLAN MANAGEMENT SYSTEM (NEW) =====

@bot.command(name="addofficial")
@commands.check(is_moderator)
async def add_official_member(ctx, user: discord.User):
    """Registers a user as an Official Member (Supports ID even if not in server)."""
    guild_id = str(ctx.guild.id)
    user_id = str(user.id)
    
    # Init Data
    if "official_members" not in global_data: global_data["official_members"] = {}
    if guild_id not in global_data["official_members"]: global_data["official_members"][guild_id] = {}
    if "official_history" not in global_data: global_data["official_history"] = {}
    if guild_id not in global_data["official_history"]: global_data["official_history"][guild_id] = {}
    
    if user_id in global_data["official_members"][guild_id]:
        await ctx.send(f"⚠️ {user.mention} is already an Official Member.")
        return

    # Add to Active List
    global_data["official_members"][guild_id][user_id] = {
        "added_by": ctx.author.id,
        "timestamp": discord.utils.utcnow().isoformat()
    }
    
    # Log to History
    history_entry = {
        "action": "ADDED",
        "by": ctx.author.id,
        "reason": "Official Member Registration",
        "timestamp": discord.utils.utcnow().isoformat()
    }
    if user_id not in global_data["official_history"][guild_id]:
        global_data["official_history"][guild_id][user_id] = []
    global_data["official_history"][guild_id][user_id].append(history_entry)
    
    await save_data()
    
    e = discord.Embed(title="🛡️ Official Member Added", color=discord.Color.green())
    e.description = f"{user.mention} (`{user.id}`) has been registered as an **Official Member**."
    e.add_field(name="Registered By", value=ctx.author.mention)
    add_branding(e)
    await ctx.send(embed=e)

@bot.command(name="removeofficial")
@commands.check(is_moderator)
async def remove_official_member(ctx, user: discord.User, *, reason: str):
    """Removes a user from Official Members list (Supports ID)."""
    guild_id = str(ctx.guild.id)
    user_id = str(user.id)
    
    if "official_members" not in global_data or guild_id not in global_data["official_members"] or user_id not in global_data["official_members"][guild_id]:
        await ctx.send(f"❌ {user.mention} (`{user.id}`) is NOT currently an Official Member.")
        return

    # Remove from Active List
    del global_data["official_members"][guild_id][user_id]
    
    # Log to History
    history_entry = {
        "action": "REMOVED",
        "by": ctx.author.id,
        "reason": reason,
        "timestamp": discord.utils.utcnow().isoformat()
    }
    if "official_history" not in global_data: global_data["official_history"] = {}
    if guild_id not in global_data["official_history"]: global_data["official_history"][guild_id] = {}
    if user_id not in global_data["official_history"][guild_id]:
         global_data["official_history"][guild_id][user_id] = []
         
    global_data["official_history"][guild_id][user_id].append(history_entry)
    
    await save_data()
    
    e = discord.Embed(title="🛡️ Official Member Removed", color=discord.Color.red())
    e.description = f"{user.mention} (`{user.id}`) has been removed from Official Members."
    e.add_field(name="Reason", value=reason)
    e.add_field(name="Removed By", value=ctx.author.mention)
    add_branding(e)
    await ctx.send(embed=e)

@bot.command(name="promote")
@commands.check(is_moderator)
async def promote_member(ctx, member: discord.Member, role: discord.Role):
    """Promotes a member to a new role and logs the change."""
    guild_id_str = str(ctx.guild.id)
    old_roles = [r for r in member.roles if r != ctx.guild.default_role]
    old_role_name = member.top_role.name if old_roles else "Civilian"
    
    try:
        await member.add_roles(role, reason=f"Promotion by {ctx.author}")
        
        # Determine notification message
        template = global_data.get("promotion_templates", {}).get(guild_id_str, {}).get("promote")
        if template:
            msg_content = template.replace("{member}", member.mention).replace("{old_role}", old_role_name).replace("{new_role}", role.mention).replace("{mod}", ctx.author.mention)
        else:
            msg_content = f"{member.mention} (`{member.id}`) has been promoted.\n\n**From:** `{old_role_name}`\n**To:** {role.mention} (`{role.id}`)"

        e = discord.Embed(title="📈 Member Promoted", description=msg_content, color=discord.Color.green())
        e.set_thumbnail(url=member.display_avatar.url)
        add_branding(e)
        
        # Send to specific promotion channel if configured, otherwise stay in ctx
        promo_chan_id = global_data.get("promotion_channels", {}).get(guild_id_str)
        promo_chan = ctx.guild.get_channel(promo_chan_id) if promo_chan_id else None
        
        if promo_chan:
            await promo_chan.send(embed=e)
            await ctx.send(f"✅ Promotion successful. Notification sent to {promo_chan.mention}")
        else:
            await ctx.send(embed=e)
        
        # Log to Official History
        user_id = str(member.id)
        if "official_history" not in global_data: global_data["official_history"] = {}
        if guild_id_str not in global_data["official_history"]: global_data["official_history"][guild_id_str] = {}
        if user_id not in global_data["official_history"][guild_id_str]: global_data["official_history"][guild_id_str][user_id] = []
        
        history_entry = {
            "action": "PROMOTED",
            "by": ctx.author.id,
            "old_role": old_role_name,
            "new_role": role.name,
            "timestamp": discord.utils.utcnow().isoformat()
        }
        global_data["official_history"][guild_id_str][user_id].append(history_entry)
        await save_data()

        # Log to Clan Logs
        await log_monitor_event(ctx.guild, "📈 PROMOTION", f"User {member.mention} promoted from `{old_role_name}` to {role.name} by {ctx.author.mention}", discord.Color.green())
    except Exception as e_err:
        await ctx.send(f"❌ Failed to promote: {e_err}")

@bot.command(name="demote")
@commands.check(is_moderator)
async def demote_member(ctx, member: discord.Member, role: discord.Role):
    """Demotes a member to a lower role."""
    guild_id_str = str(ctx.guild.id)
    old_role_name = member.top_role.name
    
    try:
        await member.remove_roles(member.top_role, reason=f"Demotion by {ctx.author}")
        await member.add_roles(role, reason=f"Demotion adjustment")
        
        # Determine notification message
        template = global_data.get("promotion_templates", {}).get(guild_id_str, {}).get("demote")
        if template:
            msg_content = template.replace("{member}", member.mention).replace("{old_role}", old_role_name).replace("{new_role}", role.mention).replace("{mod}", ctx.author.mention)
        else:
            msg_content = f"{member.mention} (`{member.id}`) has been demoted.\n\n**From:** `{old_role_name}`\n**To:** {role.mention} (`{role.id}`)"

        e = discord.Embed(title="📉 Member Demoted", description=msg_content, color=discord.Color.orange())
        e.set_thumbnail(url=member.display_avatar.url)
        add_branding(e)
        
        # Send to specific promotion channel if configured
        promo_chan_id = global_data.get("promotion_channels", {}).get(guild_id_str)
        promo_chan = ctx.guild.get_channel(promo_chan_id) if promo_chan_id else None
        
        if promo_chan:
            await promo_chan.send(embed=e)
            await ctx.send(f"✅ Demotion successful. Notification sent to {promo_chan.mention}")
        else:
            await ctx.send(embed=e)
        
        # Log to Official History
        user_id = str(member.id)
        if "official_history" not in global_data: global_data["official_history"] = {}
        if guild_id_str not in global_data["official_history"]: global_data["official_history"][guild_id_str] = {}
        if user_id not in global_data["official_history"][guild_id_str]: global_data["official_history"][guild_id_str][user_id] = []
        
        history_entry = {
            "action": "DEMOTED",
            "by": ctx.author.id,
            "old_role": old_role_name,
            "new_role": role.name,
            "timestamp": discord.utils.utcnow().isoformat()
        }
        global_data["official_history"][guild_id_str][user_id].append(history_entry)
        await save_data()

        # Log to Clan Logs
        await log_monitor_event(ctx.guild, "📉 DEMOTION", f"User {member.mention} demoted from `{old_role_name}` to {role.name} by {ctx.author.mention}", discord.Color.orange())
    except Exception as e_err:
        await ctx.send(f"❌ Failed to demote: {e_err}")

@bot.command(name="officiallist")
async def list_official_members(ctx):
    """Lists all current Official Members."""
    guild_id = str(ctx.guild.id)
    if "official_members" not in global_data or guild_id not in global_data["official_members"] or not global_data["official_members"][guild_id]:
        await ctx.send("ℹ️ No Official Members registered yet.")
        return
        
    e = discord.Embed(title="🛡️ Official Members List", color=discord.Color.blue())
    
    members = []
    for uid, data in global_data["official_members"][guild_id].items():
        mem = ctx.guild.get_member(int(uid))
        name = mem.display_name if mem else f"ID: {uid}"
        added_at = data.get("timestamp", "").split("T")[0]
        members.append(f"• **{name}** (Since {added_at})")
        
    # Pagination placeholder (simple text split for now)
    desc = "\n".join(members)
    if len(desc) > 4000:
        desc = desc[:4000] + "\n... (truncated)"
        
    e.description = desc
    e.set_footer(text=f"Total: {len(members)}")
    add_branding(e)
    await ctx.send(embed=e)

@bot.command(name="award")
@commands.check(is_moderator)
async def award_medal(ctx, user: discord.User, *, medal_name: str):
    """Awards a medal to an Official Member."""
    guild_id = str(ctx.guild.id)
    user_id = str(user.id)
    
    if guild_id not in global_data.get("official_members", {}) or user_id not in global_data["official_members"][guild_id]:
        await ctx.send(f"❌ {user.mention} is not an Official Member. Register them first with `addofficial`.")
        return

    # Initialize medals if missing
    if "medals" not in global_data["official_members"][guild_id][user_id]:
        global_data["official_members"][guild_id][user_id]["medals"] = []
        
    medal_entry = {
        "name": medal_name,
        "by": ctx.author.id,
        "timestamp": discord.utils.utcnow().isoformat()
    }
    global_data["official_members"][guild_id][user_id]["medals"].append(medal_entry)
    
    # Log to History
    history_entry = {
        "action": "AWARDED",
        "medal": medal_name,
        "by": ctx.author.id,
        "timestamp": discord.utils.utcnow().isoformat()
    }
    if user_id not in global_data["official_history"][guild_id]:
        global_data["official_history"][guild_id][user_id] = []
    global_data["official_history"][guild_id][user_id].append(history_entry)
    
    await save_data()
    
    e = discord.Embed(title="🏅 Medal Awarded", color=discord.Color.gold())
    e.description = f"{user.mention} has been awarded the **{medal_name}**!"
    e.add_field(name="Awarded By", value=ctx.author.mention)
    e.set_thumbnail(url="https://cdn-icons-png.flaticon.com/512/179/179249.png")
    add_branding(e)
    await ctx.send(embed=e)

@bot.command(name="loa")
async def loa_command(ctx, *, reason: str = "No reason provided."):
    """Request/Set Leave of Absence."""
    guild_id = str(ctx.guild.id)
    user_id = str(ctx.author.id)

    if guild_id not in global_data.get("official_members", {}) or user_id not in global_data["official_members"][guild_id]:
        await ctx.send(f"❌ Only **Official Members** can request LOA.")
        return

    global_data["official_members"][guild_id][user_id]["loa"] = {
        "reason": reason,
        "timestamp": discord.utils.utcnow().isoformat()
    }
    
    # Log to History
    history_entry = {
        "action": "LOA_START",
        "reason": reason,
        "timestamp": discord.utils.utcnow().isoformat()
    }
    if user_id not in global_data["official_history"][guild_id]:
        global_data["official_history"][guild_id][user_id] = []
    global_data["official_history"][guild_id][user_id].append(history_entry)
    
    await save_data()
    
    e = discord.Embed(title="✈️ LOA Started", color=discord.Color.blue())
    e.description = f"{ctx.author.mention} is now on **Leave of Absence**.\n**Reason:** {reason}"
    add_branding(e)
    await ctx.send(embed=e)

@bot.command(name="endloa")
async def end_loa(ctx):
    """End your Leave of Absence."""
    guild_id = str(ctx.guild.id)
    user_id = str(ctx.author.id)

    if guild_id not in global_data.get("official_members", {}) or user_id not in global_data["official_members"][guild_id]:
        return

    if "loa" not in global_data["official_members"][guild_id][user_id]:
        await ctx.send(f"❌ You are not on LOA.")
        return

    del global_data["official_members"][guild_id][user_id]["loa"]
    
    # Log to History
    history_entry = {
        "action": "LOA_END",
        "timestamp": discord.utils.utcnow().isoformat()
    }
    global_data["official_history"][guild_id][user_id].append(history_entry)
    
    await save_data()
    await ctx.send(f"✅ Welcome back {ctx.author.mention}! Your **LOA** has been ended.")

@bot.command(name="clanprofile")
async def clan_profile(ctx, user: discord.User = None):
    """View an Official Member's career dossier."""
    user = user or ctx.author
    guild_id = str(ctx.guild.id)
    user_id = str(user.id)

    if guild_id not in global_data.get("official_members", {}) or user_id not in global_data["official_members"][guild_id]:
        await ctx.send(f"❌ This user is not an **Official Member**.")
        return

    data = global_data["official_members"][guild_id][user_id]
    history = global_data["official_history"][guild_id].get(user_id, [])
    
    e = discord.Embed(title=f"🛡️ SPG Career Dossier: {user.name}", color=discord.Color.blue())
    e.set_thumbnail(url=str(user.display_avatar.url) if hasattr(user, 'display_avatar') else "")
    
    status = "🟢 Active"
    if "loa" in data:
        status = f"✈️ ON LOA ({data['loa']['reason']})"
    
    e.add_field(name="Current Status", value=status, inline=False)
    e.add_field(name="Joined Clan", value=data["timestamp"].split("T")[0], inline=True)
    
    # Medals
    medals = data.get("medals", [])
    medal_list = "None"
    if medals:
        list_items = []
        for m in medals:
            ts_dt = datetime.datetime.fromisoformat(m['timestamp'])
            list_items.append(f"🏅 {m['name']} (<t:{int(ts_dt.timestamp())}:R>)")
        medal_list = "\n".join(list_items)
    e.add_field(name="Medals & Awards", value=medal_list, inline=False)
    
    # Recent Career History (Last 5)
    recent_history = history[-5:][::-1]
    history_str = "No records found."
    if recent_history:
        lines = []
        for entry in recent_history:
            action = entry["action"]
            ts = int(datetime.datetime.fromisoformat(entry["timestamp"]).timestamp())
            if action == "PROMOTED":
                lines.append(f"📈 **Promoted** to {entry['new_role']} <t:{ts}:R>")
            elif action == "DEMOTED":
                lines.append(f"📉 **Demoted** to {entry['new_role']} <t:{ts}:R>")
            elif action == "AWARDED":
                lines.append(f"🏅 **Awarded** {entry['medal']} <t:{ts}:R>")
            elif action == "LOA_START":
                lines.append(f"✈️ **Start LOA** <t:{ts}:R>")
            elif action == "ADDED":
                 lines.append(f"🛡️ **Registered** <t:{ts}:R>")
        history_str = "\n".join(lines) if lines else "Career records are active."
        
    e.add_field(name="Service History", value=history_str, inline=False)
    
    add_branding(e)
    await ctx.send(embed=e)

@bot.command(name="checkofficial")
async def check_official_member(ctx, user: discord.User): # Changed to discord.User
    """Check Official status and history by Mention or ID."""
    guild_id = str(ctx.guild.id)
    user_id = str(user.id)
    
    # Check Status
    is_official = False
    join_date = "N/A"
    
    if "official_members" in global_data and guild_id in global_data["official_members"]:
         if user_id in global_data["official_members"][guild_id]:
             is_official = True
             data = global_data["official_members"][guild_id][user_id]
             ts = int(datetime.datetime.fromisoformat(data["timestamp"]).timestamp())
             join_date = f"<t:{ts}:F> (<t:{ts}:R>)"
             
    e = discord.Embed(title=f"🛡️ Dossier: {user.name}", color=discord.Color.green() if is_official else discord.Color.greyple())
    e.set_thumbnail(url=user.display_avatar.url)
    e.add_field(name="Official Status", value="✅ **ACTIVE**" if is_official else "❌ **CIVILIAN/INACTIVE**", inline=False)
    if is_official:
        e.add_field(name="Inducted", value=join_date, inline=True)

    # History
    history_text = "No recorded history."
    if "official_history" in global_data and guild_id in global_data["official_history"]:
        history_list = global_data["official_history"][guild_id].get(user_id, [])
        if history_list:
            lines = []
            for entry in reversed(history_list[-8:]): # Last 8 events
                action = entry["action"]
                action_emoji = "➕" if action == "ADDED" else "➖"
                if action == "PROMOTED": action_emoji = "📈"
                elif action == "DEMOTED": action_emoji = "📉"
                
                ts = int(datetime.datetime.fromisoformat(entry["timestamp"]).timestamp())
                by_user = f"<@{entry['by']}>"
                reason = entry.get('reason', 'N/A')
                
                detail = f"📝 *{reason}*"
                if action in ["PROMOTED", "DEMOTED"]:
                    detail = f"Rank: `{entry.get('old_role', 'Unknown')}` ⮕ `{entry.get('new_role', 'Unknown')}`"
                
                lines.append(f"{action_emoji} **{action}** <t:{ts}:R> by {by_user}\n└ {detail}")
            history_text = "\n".join(lines)
            
    e.add_field(name="Recent History", value=history_text, inline=False)
    add_branding(e)
    await ctx.send(embed=e)

# --- NEW ADVANCED EMBED COMMAND (Uses updated modal/view) ---
@bot.command(name="spgsendembed", aliases=["embed", "embedbuilder"])
@commands.check(is_moderator)
async def send_embed_panel(ctx):
    """
    Starts an interactive panel to create and send a rich embed with components
    to a specified channel. (Moderator Only)
    """
    if not ctx.guild:
        await ctx.send("This command must be used inside a server.")
        return
        
    # Start the multi-step process by presenting the channel selector
    await ctx.send(
        "**Start Embed Creation**\n"
        "First, select the channel where you want the embed to be sent.",
        view=EmbedChannelView(ctx.guild.channels, ctx.author.id),
        ephemeral=True
    )
# --- END NEW ADVANCED EMBED COMMAND ---

# ===== BOT IDENTITY COMMANDS (NEW) =====
@bot.command(name="setlogo")
async def set_logo(ctx, url: str = None):
    """
    Change the bot's avatar.
    Usage: !setlogo <url> OR upload an image/gif with the command.
    """
    if not is_authorized(ctx.author.id):
        await ctx.send("❌ Unauthorized. Only bot owners can change identity.")
        return

    image_data = None
    
    # 1. Check Attachments
    if ctx.message.attachments:
        try:
            image_data = await ctx.message.attachments[0].read()
        except Exception as e:
            await ctx.send(f"❌ Failed to read attachment: {e}")
            return

    # 2. Check URL
    elif url:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        await ctx.send("❌ Failed to download image from URL.")
                        return
                    image_data = await resp.read()
        except Exception as e:
            await ctx.send(f"❌ Invalid URL: {e}")
            return
    else:
        await ctx.send("❌ Please provide a URL or upload an image.")
        return

    # 3. Apply Change
    try:
        await bot.user.edit(avatar=image_data)
        await ctx.send("✅ **Success!** My avatar has been updated.")
    except discord.HTTPException as e:
        await ctx.send(f"❌ Discord API Error: {e} (You might be changing it too fast!)")
    except Exception as e:
        await ctx.send(f"❌ Error: {e}")

@bot.command(name="setbanner")
async def set_banner(ctx, url: str = None):
    """
    Change the bot's banner.
    Usage: !setbanner <url> OR upload an image/gif.
    """
    if not is_authorized(ctx.author.id):
        await ctx.send("❌ Unauthorized. Only bot owners can change identity.")
        return

    image_data = None
    
    # 1. Check Attachments
    if ctx.message.attachments:
        try:
            image_data = await ctx.message.attachments[0].read()
        except Exception as e:
            await ctx.send(f"❌ Failed to read attachment: {e}")
            return

    # 2. Check URL
    elif url:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        await ctx.send("❌ Failed to download image from URL.")
                        return
                    image_data = await resp.read()
        except Exception as e:
            await ctx.send(f"❌ Invalid URL: {e}")
            return
    else:
        await ctx.send("❌ Please provide a URL or upload an image.")
        return

    # 3. Apply Change
    try:
        await bot.user.edit(banner=image_data)
        await ctx.send("✅ **Success!** My banner has been updated.")
    except Exception as e:
        await ctx.send(f"❌ Error: {e}")

@bot.command(name="setstatus")
async def set_status(ctx, status_type: str):
    """
    Set the bot's online status.
    Usage: !setstatus <online|idle|dnd|invisible>
    """
    if not is_authorized(ctx.author.id):
        await ctx.send("❌ Unauthorized.")
        return

    status_type = status_type.lower()
    try:
        if status_type == "online":
            await bot.change_presence(status=discord.Status.online)
        elif status_type == "idle":
            await bot.change_presence(status=discord.Status.idle)
        elif status_type == "dnd":
            await bot.change_presence(status=discord.Status.dnd)
        elif status_type == "invisible":
            await bot.change_presence(status=discord.Status.invisible)
        else:
            await ctx.send("❌ Invalid status. Choose: `online`, `idle`, `dnd`, `invisible`.")
            return
        await ctx.send(f"✅ Status changed to **{status_type}**.")
    except Exception as e:
        await ctx.send(f"❌ Error setting status: {e}")

@bot.command(name="setactivity")
async def set_activity(ctx, activity_type: str, *, text: str):
    """
    Set the bot's activity.
    Usage: !setactivity <playing|watching|listening|streaming> <text>
    Note: Streaming uses a default twitch URL if none provided in code (can be enhanced).
    """
    if not is_authorized(ctx.author.id):
        await ctx.send("❌ Unauthorized.")
        return

    activity_type = activity_type.lower()
    try:
        activity = None
        if activity_type == "playing":
            activity = discord.Game(name=text)
        elif activity_type == "watching":
            activity = discord.Activity(type=discord.ActivityType.watching, name=text)
        elif activity_type == "listening":
            activity = discord.Activity(type=discord.ActivityType.listening, name=text)
        elif activity_type == "streaming":
            activity = discord.Activity(type=discord.ActivityType.streaming, name=text, url="https://www.twitch.tv/specialprotectiongroup")
        else:
            await ctx.send("❌ Invalid type. Choose: `playing`, `watching`, `listening`, `streaming`.")
            return
        
        # Preserve current status (online/dnd etc) while changing activity is tricky without caching it, 
        # but change_presence allows passing just activity.
        await bot.change_presence(activity=activity)
        await ctx.send(f"✅ Activity changed to **{activity_type} {text}**.")
    except Exception as e:
        await ctx.send(f"❌ Error setting activity: {e}")

# ===== HELP COMMAND (NEW) =====
class HelpSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Moderation", emoji="🔨", description="Kick, Ban, Mute, Warn"),
            discord.SelectOption(label="Anti-Nuke", emoji="☢️", description="Protection & Panic Mode"),
            discord.SelectOption(label="Auto-Mod", emoji="🤖", description="Automated Filter Settings"),
            discord.SelectOption(label="Config", emoji="⚙️", description="Prefix, Logs, Setup"),
            discord.SelectOption(label="Backups", emoji="♻️", description="Backup & Restore"),
            discord.SelectOption(label="Monitoring", emoji="🖥️", description="Server & Member Logging"),
            discord.SelectOption(label="Utility", emoji="🔧", description="User Info, Badge System"),
            discord.SelectOption(label="Fun", emoji="🎲", description="8ball, RPS, Slots"),
            discord.SelectOption(label="Clan System", emoji="🛡️", description="Official Member Management"),
            discord.SelectOption(label="Ticket System", emoji="🎟️", description="Applications & Panels"),
            discord.SelectOption(label="Socials", emoji="📺", description="YouTube Notifications"),
            discord.SelectOption(label="Bot Identity", emoji="🤖", description="Status, Activity, Logo, Banner")
        ]
        super().__init__(placeholder="Select a category...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        category = self.values[0]
        embed = discord.Embed(title=f"{category} Commands", color=discord.Color.blue())
        embed.add_field(name="📜 Documentation", value="[**Click Here to View Full Docs**](http://specialprotectiongroup-emh.com/bot/docs.html)", inline=False)
        
        if category == "Moderation":
            embed.description = """
            `!warn <user> [reason]` - Warn a user.
            `!checkwarn <user>` - Check user warnings.
            `!kick <user> [reason]` - Kick a user.
            `!ban <user> [reason]` - Ban a user.
            `!unban <id>` - Unban a user ID.
            `!tempban <user> <time> [reason]` - Temp ban (e.g. 1d, 1h).
            `!purge <amount>` - Delete messages.
            `!modpanel <user>` - Open interactive mod panel.
            `!stopchat <user>` / `!startchat` - Control user chat.
            `!spgreport <user> <reason>` - Report user to admins.
            `!setreportchannel <#channel>` - Set report destination.
            `!announcement <channel> <text>` - Send an announcement.
            `!send <user> <message>` - DM a user via bot (ID or Mention).
            `!listbadges` - List all assigned badges.
            """
        elif category == "Anti-Nuke":
            embed.description = """
            **🛡️ Systems Engaged:** Anti-Nuke, Anti-Raid, Anti-Spam, Zero-Trust Architecture
            
            `! about` - Details on bot intelligence & off-site logging.
            `! antinuke <on/off>` - Toggle Anti-Nuke system.
            `! nukestatus` - View current security policy.
            `! masslimits` - View protection thresholds.
            `! setmasslimit <action> <limit>` - Configure protection.
            `! setnukeaction <BAN/KICK/STRIP/NONE>` - Set punishment.
            `! dashboard` - Access monitoring via dashboard.
            """
        elif category == "Auto-Mod":
             embed.description = """
             **🤖 Systems Engaged:** Local AI, Regex Filter, Google Gemini (Context), XLM-Roberta (Toxicity)
             
            `! dashboard` - Open Dashboard UI.
            `! startautomod` / `spg stopautomod` - Toggle system.
            `! setautomodexempt <role>` - Exempt role from filters.
            `! addsafelink <link>` - Whitelist a link domain.
            `! removesafelink <link>` - Remove a link domain.
            `! addbadword <word>` - Add word to blocked list.
            `! removebadword <word>` - Remove word from blocked list.
            """
        elif category == "Config":
            embed.description = """
            `! setting` - View full server configuration.
            `! setprefix <new_prefix>` - Change bot prefix.
            `! setmodlog <channel>` - Set moderation log channel.
            `! setmod <role>` - Set moderator role.
            `! setverifyrole <role>` - Set role specifically for verification.
            `! setverifyguild` - Set current server as verification source.
            `! setperm <id> <add/remove>` - Manage bot owner access.
            `! setwelcomechannel <#channel>` - Set welcome channel.
            `! testwelcome` - Test welcome message.
            `! addautoreply <trigger> <reply>` - Add auto-reply for a word/phrase.
            `! removeautoreply <trigger>` - Remove an auto-reply.
            `! autoreplylist` - List active auto-replies.
            """
        elif category == "Bot Identity":
             embed.description = """
             `! setstatus <online/idle/dnd/invisible>` - Set bot's online status.
             `! setactivity <type> <text>` - Set bot's activity (playing/watching/listening/streaming).
             `! setlogo <url/upload>` - Change bot avatar.
             `! setbanner <url/upload>` - Change bot banner.
             """
        elif category == "Backups":
            embed.description = """
            `! createbackup` - **Backup** roles, channels, categories.
            `! loadbackup <backup_id>` - **Restore** a backup (Destructive).
            `! backuplist` - View available backups.
            """
        elif category == "Monitoring":
            embed.description = """
            `! servermoniter <channel>` - Set channel for detailed logs.
            `! spgscan` - Audit server security & admins.
            `! serversnapshot` - Take a snapshot of server stats.
            *Logs:* Message Edit/Delete, Member Join/Leave, Role Changes, Channel Changes, Webhooks.
            """
        elif category == "Fun":
            embed.description = """
            `! 8ball <question>` - Ask the magic 8-ball.
            `! rps <rock/paper/scissors>` - Play RPS.
            `! coinflip` - Flip a coin.
            `! dice` - Roll a die.
            `! slots` - Play slots.
            """
        elif category == "Utility":
            embed.description = """
            `! spgsendembed` - Create advanced embeds.
            `! userinfo [user]` - View user details.
            `! whois <user>` - Alias for userinfo.
            `! serverinfo` - View server statistics.
            `! membercount` - View Human/Bot count.
            `! botinfo` - View bot stats.
            `! pg poll <question>` - Create a poll.
            `! mybadge` - View your badge.
            `! givebadge <user>` - Assign badge (Mod).
            `! afk [reason]` - Set AFK status.
            `! setnick <user> <nick>` - Change nickname.
            `! slowmode <seconds>` - Set channel slowmode.
            `! snippet` - View last deleted message.
            `! ping` - Check bot latency.
            `! uptime` - Check bot uptime.
            `! avatar [user]` - View user avatar.
            `! remind <time> <text>` - Set a reminder.
            """
        elif category == "Ticket System":
             embed.description = """
             **📝 Application Management**
             `! applicationopen` - Open apps & update panel.
             `! applicationclosed` - Close apps & update panel.
             `! ticketpanel` - Send/Refresh the application panel.
             `! setapplybannedrole <role>` - Set role that CANNOT apply.
             `! unbanapplyrole` - Remove the banned role constraint.
             `! setticketcategory <category_id>` - Set category for new tickets.
             `! addticketmod <role>` - Add role to ticket ping list.
             `! removeticketmod <role>` - Remove role from ticket ping list.
             `! setrequiredrole <role>` - Set role required to create ticket.
             """
            
             
        elif category == "Clan System":
            embed.description = """
            **🛡️ Official Clan Management**
            `! addofficial <user>` - Register a user as an Official Member.
            `! removeofficial <user> <reason>` - Remove a user and log the reason.
            `! promote <user> <role>` - Move a member to a higher rank.
            `! demote <user> <role>` - Move a member to a lower rank.
            `! officiallist` - View all current Official Members.
            `! checkofficial <user>` - Check member status and history (joins/leaves).
            **⚙️ Configuration**
            `! setpromotionchannel <#channel>` - Set announcement channel.
            `! setpromotiontext <msg>` - Custom promotion text.
            `! setdemotiontext <msg>` - Custom demotion text.
            *(Placeholders: {member}, {old_role}, {new_role}, {mod})*
            
            **👮 Shift System**
            `! shift` - Open shift management panel.
            `! shift panel` - Deploy permanent shift panel.
            `! shift leaderboard` - View shift activity.

            **🎖️ Career & History**
            `! clanprofile [user]` - View high-detail career dossier.
            `! award <user> <medal>` - Grant an official medal/honor.
            `! loa <reason>` / `! endloa` - Manage Leave of Absence.
            """
        elif category == "Socials":
            embed.description = """
            **📺 YouTube Notifications**
            `! setnotify <#channel>` - Set destination for pings.
            `! addyoutube <id/link>` - Add creator to watchlist.
            `! removeyoutuber <id/link>` - Remove creator from watchlist.
            `! sendlatestvideo <query>` - Manually trigger latest video alert.
            `! setyoutubetext <msg>` - Custom notification text.
            `! testyoutube` - Diagnostic check.

            **🎨 Customizing Notifications**
            Use `spg setyoutubetext` with these placeholders:
            • `{name}` - Creator Name
            • `{title}` - Video Title
            • `{url}` - Video Link
            *Example:* `spg setyoutubetext 🚨 {name} uploaded: {title}! {url}`

            **💡 Pro-Tip: How to get Channel ID?**
            1. Go to the YouTube Channel.
            2. Click **'More'** or the **'About'** arrow.
            3. Click **'Share Channel'** -> **'Copy Channel ID'**.
            *Starts with **`UC...`***
            """

        add_branding(embed)
        await interaction.response.edit_message(embed=embed)

class HelpView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.add_item(HelpSelect())

bot.remove_command("help")
@bot.command(name="help")
async def help_command(ctx):
    """Displays the interactive help menu."""
    embed = discord.Embed(title="🤖 SPG Server Big Daddy Help", description="Select a category below to view commands.", color=discord.Color.gold())
    view = HelpView()
    await ctx.send(embed=embed, view=view)

# ===== AUTO-REPLY COMMANDS =====
@bot.command(name="addautoreply")
@commands.has_permissions(administrator=True)
async def add_autoreply(ctx, trigger: str, *, response: str):
    """Add a custom auto-reply trigger."""
    guild_id = str(ctx.guild.id)
    if "auto_replies" not in global_data: global_data["auto_replies"] = {}
    if guild_id not in global_data["auto_replies"]: global_data["auto_replies"][guild_id] = {}
    
    global_data["auto_replies"][guild_id][trigger.lower()] = response
    await save_data()
    embed = discord.Embed(title="✅ Auto-Reply Added", color=discord.Color.green())
    embed.add_field(name="Trigger", value=f"`{trigger.lower()}`", inline=False)
    embed.add_field(name="Response", value=response, inline=False)
    add_branding(embed)
    await ctx.send(embed=embed)

@bot.command(name="removeautoreply")
@commands.has_permissions(administrator=True)
async def remove_autoreply(ctx, *, trigger: str):
    """Remove a custom auto-reply trigger."""
    guild_id = str(ctx.guild.id)
    trigger = trigger.lower()
    
    if "auto_replies" in global_data and guild_id in global_data["auto_replies"]:
        if trigger in global_data["auto_replies"][guild_id]:
            del global_data["auto_replies"][guild_id][trigger]
            await save_data()
            await ctx.send(f"✅ Removed auto-reply for: `{trigger}`")
            return
    await ctx.send(f"❌ Auto-reply for `{trigger}` not found.")

@bot.command(name="autoreplylist")
@commands.has_permissions(administrator=True)
async def list_autoreplies(ctx):
    """List all auto-replies configured in the server."""
    guild_id = str(ctx.guild.id)
    
    if "auto_replies" not in global_data or guild_id not in global_data["auto_replies"] or not global_data["auto_replies"][guild_id]:
        await ctx.send("ℹ️ No auto-replies configured for this server.")
        return
        
    embed = discord.Embed(title="🗣️ Active Auto-Replies", color=discord.Color.blue())
    
    replies = global_data["auto_replies"][guild_id]
    desc = ""
    for trigger, response in replies.items():
        # Truncate long responses
        disp_resp = response if len(response) <= 50 else response[:47] + "..."
        desc += f"• **`{trigger}`** ➔ {disp_resp}\n"
        
    embed.description = desc
    add_branding(embed)
    await ctx.send(embed=embed)

@bot.command(name="setnick")
@commands.has_permissions(manage_nicknames=True)
async def set_nick(ctx, member: discord.Member, *, nickname: str = None):
    """Change a user's nickname. Leave empty to reset."""
    try:
        await member.edit(nick=nickname)
        if nickname:
            await ctx.send(f"✅ Changed nickname of {member.mention} to **{nickname}**.")
        else:
            await ctx.send(f"✅ Reset nickname of {member.mention}.")
    except discord.Forbidden:
        await ctx.send("❌ I don't have permission to change that user's nickname.")

@bot.command(name="slowmode")
@commands.has_permissions(manage_channels=True)
async def slowmode(ctx, seconds: int):
    """Set slowmode for the current channel."""
    try:
        await ctx.channel.edit(slowmode_delay=seconds)
        if seconds > 0:
            await ctx.send(f"🐢 Slowmode set to **{seconds} seconds**.")
        else:
            await ctx.send(f"✅ Slowmode **disabled**.")
    except Exception as e:
        await ctx.send(f"❌ Failed to set slowmode: {e}")

@bot.command(name="membercount")
async def member_count_cmd(ctx):
    """View detailed member count."""
    guild = ctx.guild
    total = guild.member_count
    bots = len([m for m in guild.members if m.bot])
    humans = total - bots
    
    # Approx online count
    online = len([m for m in guild.members if m.status != discord.Status.offline])

    e = discord.Embed(title=f"📊 Member Count: {guild.name}", color=discord.Color.blue())
    e.add_field(name="Total", value=str(total), inline=True)
    e.add_field(name="Humans", value=str(humans), inline=True)
    e.add_field(name="Bots", value=str(bots), inline=True)
    e.add_field(name="Online (Approx)", value=str(online), inline=True)
    add_branding(e)
    await ctx.send(embed=e)



# ===== APPLICATION COMMANDS =====

async def update_panel(ctx, guild_id):
    """Helper to edit existing panel or send new one."""
    panel_info = global_data.get("ticket_panel_message", {}).get(str(guild_id))
    
    embed = discord.Embed(title="📋 Apply for Police Department", description="Click the button below to start your application.\n\n**Requirements:**\n- Must be active\n- Must have valid XP\n\n**Status:** " + ("🟢 OPEN" if global_data.get("applications_open", False) else "🔴 CLOSED"), color=discord.Color.blue())
    add_branding(embed)
    
    if panel_info:
        try:
            channel = ctx.guild.get_channel(panel_info["channel"])
            if channel:
                msg = await channel.fetch_message(panel_info["message"])
                await msg.edit(embed=embed, view=ApplicationView())
                # await ctx.send("✅ Panel updated.") # Optional feedback
                return
        except (discord.NotFound, discord.Forbidden):
            pass # Message deleted or no perms, send new one
            
    # If we reached here, no valid panel exists, so send new one in CURRENT channel
    await ticket_panel_command(ctx)

@bot.command(name="applicationopen")
@commands.check(is_moderator)
async def app_open(ctx):
    """Opens applications, announces it, and updates the panel."""
    global_data["applications_open"] = True
    await save_data()
    
    # 1. Announcement
    embed = discord.Embed(title="📢 Applications OPEN", description="We are now accepting new applications! Apply via the ticket panel below.", color=discord.Color.green())
    embed.set_image(url="https://fileshare.specialprotectiongroup-emh.com/media/1768200452-69649904c2c94-BlackSimpleRecordVlogYoutubeIntro1.png") 
    add_branding(embed)
    await ctx.send(embed=embed)
    
    # 2. Update/Send Panel
    await update_panel(ctx, ctx.guild.id)

@bot.command(name="applicationclosed")
@commands.check(is_moderator)
async def app_closed(ctx):
    """Closes applications, announces it, and updates the panel."""
    global_data["applications_open"] = False
    await save_data()
    
    # 1. Announcement
    embed = discord.Embed(title="🔒 Applications CLOSED", description="Applications are now closed. Thank you for your interest.", color=discord.Color.red())
    embed.set_image(url="https://fileshare.specialprotectiongroup-emh.com/media/1768200371-696498b32e593-BlackSimpleRecordVlogYoutubeIntro.png")
    add_branding(embed)
    await ctx.send(embed=embed)
    
    # 2. Update/Send Panel
    await update_panel(ctx, ctx.guild.id)

@bot.command(name="ticketpanel", aliases=["ticketpanl"])
@commands.check(is_moderator)
async def ticket_panel_command(ctx):
    """Sends the Application Panel and stores its location."""
    embed = discord.Embed(title="📋 Apply for Police Department", description="Click the button below to start your application.\n\n**Requirements:**\n- Must be active\n- Must have valid XP\n\n**Status:** " + ("🟢 OPEN" if global_data.get("applications_open", False) else "🔴 CLOSED"), color=discord.Color.blue())
    add_branding(embed)
    msg = await ctx.send(embed=embed, view=ApplicationView())
    
    # Store message info for future edits
    if "ticket_panel_message" not in global_data:
        global_data["ticket_panel_message"] = {}
    
    global_data["ticket_panel_message"][str(ctx.guild.id)] = {
        "channel": ctx.channel.id,
        "message": msg.id
    }
    await save_data()

@bot.command(name="setapplybannedrole")
@commands.has_permissions(administrator=True)
async def set_apply_banned_role(ctx, role: discord.Role):
    """Sets a role that is FORBIDDEN from creating applications."""
    if "banned_apply_roles" not in global_data:
        global_data["banned_apply_roles"] = {}
        
    global_data["banned_apply_roles"][str(ctx.guild.id)] = role.id
    await save_data()
    await ctx.send(f"✅ Users with {role.mention} can no longer submit applications.")

@bot.command(name="unbanapplyrole")
@commands.has_permissions(administrator=True)
async def unban_apply_role(ctx):
    """Removes the banned role restriction for applications."""
    if str(ctx.guild.id) in global_data.get("banned_apply_roles", {}):
        del global_data["banned_apply_roles"][str(ctx.guild.id)]
        await save_data()
        await ctx.send("✅ Application ban role removed. Everyone can apply now.")
    else:
        await ctx.send("❌ No banned apply role is currently set.")

@bot.command(name="setticketcategory")
@commands.has_permissions(administrator=True)
async def set_ticket_category(ctx, category_id: int):
    """Sets the category where new tickets/applications will be created."""
    category = ctx.guild.get_channel(category_id)
    if not category or not isinstance(category, discord.CategoryChannel):
        await ctx.send("❌ Invalid Category ID. Please provide a valid category ID.")
        return
        
    global_data["ticket_categories"][str(ctx.guild.id)] = category.id
    await save_data()
    await ctx.send(f"✅ Ticket Category set to **{category.name}**.")

@bot.command(name="addticketmod")
@commands.has_permissions(administrator=True)
async def add_ticket_mod(ctx, role: discord.Role):
    """Adds a role to be pinged/added when a new ticket is opened."""
    guild_id = str(ctx.guild.id)
    if guild_id not in global_data["ticket_ping_roles"]:
         global_data["ticket_ping_roles"][guild_id] = []
         
    if role.id not in global_data["ticket_ping_roles"][guild_id]:
        global_data["ticket_ping_roles"][guild_id].append(role.id)
        await save_data()
        await ctx.send(f"✅ Role {role.mention} will now be pinged in new tickets.")
    else:
        await ctx.send("⚠️ Role is already in the ticket mod list.")

@bot.command(name="removeticketmod")
@commands.has_permissions(administrator=True)
async def remove_ticket_mod(ctx, role: discord.Role):
    """Removes a role from the ticket ping list."""
    guild_id = str(ctx.guild.id)
    if guild_id in global_data["ticket_ping_roles"] and role.id in global_data["ticket_ping_roles"][guild_id]:
        global_data["ticket_ping_roles"][guild_id].remove(role.id)
        await save_data()
        await ctx.send(f"✅ Role {role.mention} removed from ticket pings.")
    else:
        await ctx.send("❌ Role not found in the list.")

@bot.command(name="setwelcomechannel")
@commands.has_permissions(administrator=True)
async def set_welcome_channel(ctx, channel: discord.TextChannel):
    """Sets the channel where welcome messages will be sent."""
    global_data["welcome_channels"][str(ctx.guild.id)] = channel.id
    await save_data()
    await ctx.send(f"✅ Welcome messages will now be sent to {channel.mention}.")

@bot.command(name="testwelcome")
@commands.has_permissions(administrator=True)
async def test_welcome(ctx):
    """Simulates a member joining to test the welcome message."""
    welcome_channel_id = global_data.get("welcome_channels", {}).get(str(ctx.guild.id))
    if not welcome_channel_id:
        await ctx.send("❌ No welcome channel set. Use `!setwelcomechannel <#channel>` first.")
        return
        
    channel = ctx.guild.get_channel(welcome_channel_id)
    if not channel:
        await ctx.send("❌ Welcome channel exists in DB but not found (deleted?). Reset it.")
        return

    member = ctx.author
    embed = discord.Embed(
        title=f"Welcome {member.name}!",
        description=f"Welcome to **{member.guild.name}**\nYou are member **#{member.guild.member_count}**\n\n🚫 **Hate speech, abuse, or rule violations are strictly prohibited.**\n*Automated moderation systems are active at all times.*",
        color=discord.Color.gold(),
        timestamp=discord.utils.utcnow()
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    add_branding(embed)
    
    view = discord.ui.View()
    view.add_item(discord.ui.Button(label="Official Website", url="https://specialprotectiongroup-emh.com", style=discord.ButtonStyle.link))
    view.add_item(discord.ui.Button(label="Official Members", url="https://specialprotectiongroup-emh.com/official-members.html", style=discord.ButtonStyle.link))
    
    await channel.send(content=member.mention, embed=embed, view=view)
    await ctx.send(f"✅ Test welcome sent to {channel.mention}.")



# ===== FINISH & RUN (unchanged) =====
if __name__ == "__main__":
    # Basic safety check for placeholder tokens
    if TOKEN in ["YOUR_DISCORD_BOT_TOKEN_HERE", "", None]:
        print("ERROR: Please replace TOKEN placeholder with real value before running.")
    else:
        # ===== TESTING & LOCKDOWN COMMANDS (NEW) =====

        @bot.command(name="purgeuser")
        @commands.check(is_moderator)
        async def purge_user_command(ctx, member: discord.Member, amount: int = 10):
            """Delete messages from a specific user."""
            if amount < 1 or amount > 100:
                await ctx.send("❌ Limit must be between 1 and 100.")
                return

            def check(m):
                return m.author == member

            deleted = await ctx.channel.purge(limit=amount, check=check)
            await ctx.send(f"✅ Deleted {len(deleted)} messages from {member.mention}.", delete_after=3)

        @bot.command(name="lockdown")
        @commands.has_permissions(manage_channels=True)
        async def lockdown(ctx):
            """Lock the current channel (Deny Send Messages for @everyone)."""
            if not is_authorized(ctx.author.id):
                await ctx.send("❌ Unauthorized.")
                return
                
            msg = await ctx.send("🔒 Locking down this channel...")
            
            try:
                # Overwrite permissions for the specific channel
                overwrite = ctx.channel.overwrites_for(ctx.guild.default_role)
                overwrite.send_messages = False
                await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrite, reason=f"Manual Lockdown by {ctx.author}")
                await msg.edit(content="🔒 **CHANNEL LOCKED**: @everyone cannot send messages here.")
            except Exception as e:
                await msg.edit(content=f"❌ Lockdown Failed: {e}")

        @bot.command(name="unlockdown")
        @commands.has_permissions(manage_channels=True)
        async def unlockdown(ctx):
            """Unlock the current channel."""
            if not is_authorized(ctx.author.id):
                await ctx.send("❌ Unauthorized.")
                return
                
            try:
                overwrite = ctx.channel.overwrites_for(ctx.guild.default_role)
                overwrite.send_messages = None # Reset to default (usually inherits true/false or neutral)
                await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrite, reason=f"Unlockdown by {ctx.author}")
                await ctx.send(f"🔓 **CHANNEL UNLOCKED**: Permissions restored.")
            except Exception as e:
                await ctx.send(f"❌ Unlock Failed: {e}")

        @bot.command(name="testprotection")
        async def test_protection(ctx):
            """(Authorized Only) Simulates attacks to verify Anti-Nuke/Auto-Mod."""
            if not is_authorized(ctx.author.id):
                await ctx.send("❌ Only authorized users can run diagnostics.")
                return

            embed = discord.Embed(title="🛡️ Protection Systems Diagnostic", color=discord.Color.orange())
            embed.add_field(name="Auto-Mod Status", value="Checking...", inline=False)
            message = await ctx.send(embed=embed)

            # 1. Check Auto Mod
            automod_status = "✅ Active" if ctx.guild.id not in global_data["disabled_automod_guilds"] else "❌ Disabled"
            
            # 2. Check Gemini (Removed)
            gemini_status = "❌ Removed (Local AI Only)"

            # 3. Check Anti-Nuke

            # 3. Check Anti-Nuke
            nuke_config = get_anti_nuke_config(ctx.guild.id)
            nuke_status = "✅ Enabled" if nuke_config["enabled"] else "❌ Disabled"
            
            # Update Embed
            embed.color = discord.Color.green()
            embed.clear_fields()
            embed.add_field(name="🤖 Auto-Mod System", value=automod_status, inline=True)
            embed.add_field(name="🧠 AI Engine (Gemini)", value=gemini_status, inline=True)
            embed.add_field(name="☢️ Anti-Nuke System", value=nuke_status, inline=True)
            
            embed.add_field(name="📝 Simulation Test", value="To test actual blocking:", inline=False)
            embed.add_field(name="Spam Test", value="Type 6 messages in 5 seconds.", inline=True)
            embed.add_field(name="Link Test", value="Post a non-whitelisted link (e.g., `http://evil.com`).", inline=True)
            embed.add_field(name="Toxicity Test", value="Say something mild like 'idiot' to test filter.", inline=True)
            
            add_branding(embed)
            await message.edit(embed=embed)

        # Run the bot
        bot.run(TOKEN)