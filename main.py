import os
import re
import yt_dlp
import telebot
import threading
import time
import traceback

# -------------------------------
# CONFIG
# -------------------------------
BOT_TOKEN = "7799322927:AAFRY0mJ0keUAtnIpi8GLpWq9T4m6uJ8pO4"
bot = telebot.TeleBot(BOT_TOKEN)

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

progress_data = {}
cancel_flags = {}

# -------------------------------
# CLEAN UTILITY
# -------------------------------
def clean_text(text):
    return re.sub(r'\x1b\[[0-9;]*m', '', str(text or ""))

# -------------------------------
# PROGRESS HOOK
# -------------------------------
def progress_hook(d):
    chat_id = d.get('chat_id')
    if cancel_flags.get(chat_id):
        raise yt_dlp.utils.DownloadError("User canceled the download.")

    if d['status'] == 'downloading':
        try:
            percent = float(clean_text(d.get('_percent_str', '0%')).replace('%', '').strip() or 0)
        except:
            percent = 0.0

        bar = '█' * int(percent // 10) + '░' * (10 - int(percent // 10))
        speed = clean_text(d.get('_speed_str', '0 KiB/s'))
        eta = clean_text(d.get('_eta_str', '00:00'))
        progress_data[chat_id] = f"⏬ [{bar}] {int(percent)}% | ⚡ {speed} | ⏱ ETA: {eta}"

    elif d['status'] == 'finished':
        progress_data[chat_id] = "✅ Download complete! Preparing upload..."

# -------------------------------
# WELCOME
# -------------------------------
@bot.message_handler(commands=['start', 'help'])
def start(msg):
    text = (
        "👋 *Welcome to Turbo YouTube Downloader!*\n\n"
        "🎵 /audio <link> – MP3 Audio\n"
        "📺 /360p <link> – 360p Video\n"
        "📺 /480p <link> – 480p Video\n"
        "📺 /720p <link> – 720p HD\n"
        "📺 /1080p <link> – Full HD\n"
        "📂 /playlist <link> – Full Playlist\n\n"
        "⚡ Fast | ETA | Auto Clean\n\n"
        "🔥 *Made by* @ApkaChotaBhaiJex"
    )
    bot.reply_to(msg, text, parse_mode="Markdown")

# -------------------------------
# DOWNLOAD HANDLER
# -------------------------------
def download_media(url, quality, chat_id, msg_id):
    try:
        cancel_flags[chat_id] = False def hook_wrapper(d):
            d['chat_id'] = chat_id
            progress_hook(d)

        # ⚡ Turbo Optimized Options
        ydl_opts = {
            'outtmpl': f'{DOWNLOAD_DIR}/%(title)s.%(ext)s',
            'progress_hooks': [hook_wrapper],
            'quiet': True,
            'merge_output_format': 'mp4',
            'noplaylist': True,
            'concurrent_fragment_downloads': 8,
            'retries': 5,
            'fragment_retries': 5,
            'socket_timeout': 30,
            'throttledratelimit': 0,
            'nocheckcertificate': True,
            'geo_bypass': True,
            'continuedl': True,
            'no_warnings': True,
        }

        if quality == "audio":
            ydl_opts.update({
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }]
            })
        elif quality == "playlist":
            ydl_opts.update({'noplaylist': False})
        else:
            ydl_opts['format'] = f'bestvideo[height<={quality[:-1]}]+bestaudio/best/best'

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)

        # find correct file
        if not os.path.exists(filename):
            base, _ = os.path.splitext(filename)
            for ext in [".mp4", ".webm", ".m4a", ".mp3"]:
                if os.path.exists(base + ext):
                    filename = base + ext
                    break

        if not os.path.exists(filename):
            bot.edit_message_text("⚠️ File not found after download.", chat_id, msg_id)
            return

        bot.edit_message_text("📤 Uploading to Telegram...", chat_id, msg_id)

        with open(filename, 'rb') as f:
            if quality == "audio":
                bot.send_audio(chat_id, f, timeout=1200)
            else:
                bot.send_video(chat_id, f, timeout=1200)

        bot.send_message(chat_id, "✅ Done! File uploaded successfully.")
        try:
            os.remove(filename)
        except:
            pass

    except yt_dlp.utils.DownloadError:
        bot.edit_message_text("❌ Download canceled by user.", chat_id, msg_id)
    except Exception as e:
        err = clean_text(str(e)) or "Unknown error"
        print(traceback.format_exc())
        bot.edit_message_text(f"⚠️ Error: {err}", chat_id, msg_id)
# -------------------------------
# COMMAND HANDLER
# -------------------------------
@bot.message_handler(commands=['audio', '360p', '480p', '720p', '1080p', 'playlist'])
def handle_download(msg):
    try:
        parts = msg.text.split(" ", 1)
        if len(parts) < 2:
            bot.reply_to(msg, "⚠️ Please send a YouTube link.")
            return

        cmd = msg.text.split()[0][1:].lower()
        url = parts[1].strip()

        buttons = telebot.types.InlineKeyboardMarkup()
        buttons.row(
            telebot.types.InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_{msg.chat.id}"),
            telebot.types.InlineKeyboardButton("🔁 Refresh", callback_data=f"refresh_{msg.chat.id}")
        )

        start_msg = bot.reply_to(msg, f"🎬 Starting {cmd.upper()} download...", reply_markup=buttons)

        def run():
            download_media(url, cmd, msg.chat.id, start_msg.message_id)

        t = threading.Thread(target=run)
        t.start()

        # progress loop
        while t.is_alive():
            time.sleep(2)
            if msg.chat.id in progress_data:
                try:
                    bot.edit_message_text(progress_data[msg.chat.id],
                                          msg.chat.id,
                                          start_msg.message_id,
                                          reply_markup=buttons)
                except:
                    pass
            if cancel_flags.get(msg.chat.id):
                return
        progress_data.pop(msg.chat.id, None)
    except Exception as e:
        bot.reply_to(msg, f"⚠️ Error: {clean_text(e)}")

# -------------------------------
# INLINE BUTTON HANDLER
# -------------------------------
@bot.callback_query_handler(func=lambda call: True)
def buttons(call):
    chat_id = call.message.chat.id
    if call.data.startswith("cancel_"):
        cancel_flags[chat_id] = True
        bot.answer_callback_query(call.id, "❌ Canceled download.")
    elif call.data.startswith("refresh_"):
        msg = progress_data.get(chat_id, "No active download.")
        bot.answer_callback_query(call.id, msg, show_alert=True)

# -------------------------------
print("✅ Turbo Bot is running...")
bot.infinity_polling()
