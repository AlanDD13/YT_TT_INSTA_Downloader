import logging
import asyncio
from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import Message, FSInputFile
import yt_dlp
import os
import re
import time
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()


TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

DOWNLOAD_DIR = 'downloads'

bot = Bot(token=TOKEN)
dp = Dispatcher()

@dp.message(CommandStart())
async def start_command(message: Message):
    await message.reply("Hi! Send me an Instagram or TikTok link, and I’ll download the video without watermarks.")

@dp.message(lambda message: message.text and message.text not in ['help', 'start'])
async def download_video(message: Message):
    url = message.text.strip()
    
    if any(domain in url for domain in ['instagram.com', 'tiktok.com', 'youtube.com', 'youtu.be']):
        status_message = await message.reply("Downloading your video without watermarks, please wait...")
        
        try:
            if not os.path.exists(DOWNLOAD_DIR):
                os.makedirs(DOWNLOAD_DIR)
                
            timestamp = int(time.time())
            output_template = f'{DOWNLOAD_DIR}/{timestamp}_%(title)s.%(ext)s'
            
            platform = "unknown"
            if 'tiktok.com' in url:
                platform = "tiktok"
            elif 'instagram.com' in url:
                platform = "instagram"
            elif 'youtube.com' in url or 'youtu.be' in url:
                platform = "youtube"

            # Base yt-dlp options for all platforms
            ydl_opts = {
                'format': 'bestvideo+bestaudio/best',  # Best quality video and audio
                'merge_output_format': 'mp4',          # Output as mp4
                'outtmpl': output_template,            # Output template
                'quiet': False,                        # Show output for debugging
                'no_warnings': False,                  # Show warnings
                'ignoreerrors': True,                  # Continue on download errors
                'prefer_ffmpeg': True,                 # Use FFmpeg
                'keepvideo': True,                     # Keep video file
                'verbose': False,                       # Verbose output
                'postprocessors': [{
                    'key': 'FFmpegVideoRemuxer',
                    'preferedformat': 'mp4',
                }],
            }
            
            if platform == "tiktok":
                cookies_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tiktok_cookies.txt')
                
                if os.path.exists(cookies_file):
                    ydl_opts.update({
                        'cookiefile': cookies_file,  
                    })
                else:
                    browsers = ['chrome', 'firefox', 'edge', 'safari', 'opera']
                    for browser in browsers:
                        try:
                            ydl_opts.update({
                                'cookiesfrombrowser': (browser, None, None, None),
                            })
                            break
                        except:
                            continue
                
                ydl_opts.update({
                    'format': 'best[format_id!*=watermark]/best',  
                    'extractor_args': {
                        'tiktok': {
                            'app_version': '2022.7.0',  
                            'device_id': 'XXXXXXXXXXXXXXXX',
                            'api_hostname': 'api22-normal-useast2a.tiktokv.com', 
                        }
                    },
                })
                await status_message.edit_text("Downloading TikTok video (using authentication)...")
                
            elif platform == "instagram":
                cookies_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instagram_cookies.txt')
                
                if os.path.exists(cookies_file):
                    ydl_opts.update({
                        'cookiefile': cookies_file,
                    })
                else:
                    browsers = ['chrome', 'firefox', 'edge', 'safari', 'opera']
                    for browser in browsers:
                        try:
                            ydl_opts.update({
                                'cookiesfrombrowser': (browser, None, None, None),
                            })
                            break
                        except:
                            continue
                
                ydl_opts.update({
                    'format': 'bestvideo+bestaudio/best',
                    'extract_flat': False,
                })
                await status_message.edit_text("Downloading Instagram video in original quality...")
                
            elif platform == "youtube":
                ydl_opts.update({
                    'format': 'bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4]/best',
                })
                await status_message.edit_text("Downloading YouTube video in best quality...")

            download_success = False
            
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    if info is None:
                        raise Exception("Failed to extract video information")
                    
                    if 'entries' in info:  
                        video_info = info['entries'][0] 
                    else:
                        video_info = info
                    
                    filename = ydl.prepare_filename(video_info)
                    
                    if not os.path.exists(filename):
                        base_filename = filename.rsplit('.', 1)[0]  # Remove extension
                        for ext in ['mp4', 'mkv', 'webm']:
                            if os.path.exists(f"{base_filename}.{ext}"):
                                filename = f"{base_filename}.{ext}"
                                break
                
                download_success = os.path.exists(filename)
            except Exception as first_error:
                logging.error(f"First download attempt failed: {str(first_error)}")
                
                # If TikTok and first attempt failed, try alternative methods
                if platform == "tiktok" and "requiring login" in str(first_error):
                    await status_message.edit_text("TikTok requires login. Trying alternative method...")
                    
                    #TikTok API
                    try:
                        # Extract video ID from URL
                        video_id = None
                        match = re.search(r'tiktok\.com/.*?/video/(\d+)', url)
                        if match:
                            video_id = match.group(1)
                        
                        if video_id:
                            # Try using TikTokDL api
                            api_url = f"https://api16-normal-c-useast1a.tiktokv.com/aweme/v1/feed/?aweme_id={video_id}"
                            headers = {
                                "User-Agent": "TikTok 26.2.0 rv:262018 (iPhone; iOS 14.4.2; en_US) Cronet"
                            }
                            
                            async with aiohttp.ClientSession() as session:
                                async with session.get(api_url, headers=headers) as response:
                                    if response.status == 200:
                                        data = await response.json()
                                        video_url = None
                                        
                                        # Extract no-watermark video URL
                                        if data.get('aweme_list') and len(data['aweme_list']) > 0:
                                            aweme = data['aweme_list'][0]
                                            if aweme.get('video') and aweme['video'].get('play_addr'):
                                                video_url = aweme['video']['play_addr'].get('url_list', [])[0]
                                        
                                        if video_url:
                                            # Download the video using aiohttp
                                            filename = f"{DOWNLOAD_DIR}/{timestamp}_tiktok_{video_id}.mp4"
                                            async with session.get(video_url) as video_response:
                                                if video_response.status == 200:
                                                    with open(filename, 'wb') as f:
                                                        f.write(await video_response.read())
                                                    download_success = True
                                                    video_info = {"title": f"TikTok_{video_id}"}
                    except Exception as api_error:
                        logging.error(f"TikTok API method failed: {str(api_error)}")
                        
                        # Option 2: Try a different extractor or format
                        if not download_success:
                            try:
                                # Try with different extractor settings
                                new_opts = dict(ydl_opts)
                                new_opts.update({
                                    'format': 'best',  # Just get any format that works
                                    'force_generic_extractor': True,  # Force generic extractor
                                })
                                
                                with yt_dlp.YoutubeDL(new_opts) as ydl:
                                    info = ydl.extract_info(url, download=True)
                                    if info:
                                        video_info = info
                                        filename = ydl.prepare_filename(video_info)
                                        # Check if file exists with any extension
                                        if not os.path.exists(filename):
                                            base_filename = filename.rsplit('.', 1)[0]
                                            for ext in ['mp4', 'mkv', 'webm']:
                                                if os.path.exists(f"{base_filename}.{ext}"):
                                                    filename = f"{base_filename}.{ext}"
                                                    download_success = True
                                                    break
                            except Exception as third_error:
                                logging.error(f"Alternative download method failed: {str(third_error)}")
            
            if not download_success or not os.path.exists(filename):
                await status_message.edit_text(
                    "Failed to download the video. This TikTok video requires authentication.\n\n"
                    "To fix this:\n"
                    "1. Log in to TikTok in your browser\n"
                    "2. Export cookies to a file named 'tiktok_cookies.txt'\n"
                    "3. Place the file in the bot's directory\n"
                    "4. Try downloading again"
                )
                return
                
            file_size_mb = os.path.getsize(filename) / (1024 * 1024)
            if file_size_mb > 50:
                await status_message.edit_text(f"Video is too large ({file_size_mb:.1f}MB > 50MB) for Telegram. Try a shorter clip!")
                os.remove(filename)
                return

            await status_message.edit_text("Processing video to ensure compatibility...")
            
            # Create a new filename for the processed video
            processed_filename = f"{filename.rsplit('.', 1)[0]}_processed.mp4"
            
            ffmpeg_cmd = [
                'ffmpeg', '-i', filename,
                '-c:v', 'libx264', '-profile:v', 'baseline', '-level', '3.0',
                '-pix_fmt', 'yuv420p', '-preset', 'medium', '-crf', '23',
                '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart',
                '-y', processed_filename
            ]
            
            process = await asyncio.create_subprocess_exec(
                *ffmpeg_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            await process.communicate()
            
            if os.path.exists(processed_filename) and os.path.getsize(processed_filename) > 0:
                os.remove(filename)
                filename = processed_filename
            
            await status_message.edit_text("Processing complete! Sending to Telegram...")
            
            # Get video title or use filename as fallback
            video_title = getattr(video_info, 'get', lambda x, y: os.path.basename(filename))('title', os.path.basename(filename))
            
            # Clean the filename to avoid Telegram API issues
            clean_title = re.sub(r'[^\w\s.-]', '', str(video_title))
            
            # Ensure filename isn't too long
            if len(clean_title) > 60:
                clean_title = clean_title[:57] + "..."
            
            # Add mp4 extension if missing
            if not clean_title.lower().endswith('.mp4'):
                clean_title += '.mp4'
                
            file = FSInputFile(path=filename, filename=clean_title)
            
            # Try sending as video first
            try:
                video_message = await bot.send_video(
                    chat_id=message.chat.id,
                    video=file,
                    caption=f"Downloaded from {platform.capitalize()}: {url[:50]}...",
                    supports_streaming=True
                )
                success = True
            except Exception as video_error:
                logging.error(f"Error sending as video: {str(video_error)}")
                # If sending as video fails, try sending as document
                try:
                    file = FSInputFile(path=filename, filename=clean_title)  # Recreate FSInputFile
                    await bot.send_document(
                        chat_id=message.chat.id,
                        document=file,
                        caption=f"Downloaded from {platform.capitalize()}: {url[:50]}... (Sent as file due to compatibility issues)"
                    )
                    success = True
                except Exception as doc_error:
                    logging.error(f"Error sending as document: {str(doc_error)}")
                    success = False
                    await status_message.edit_text(f"Failed to send video. Error: {str(doc_error)[:100]}...")

            # Clean up
            try:
                if os.path.exists(filename):
                    os.remove(filename)
                
                base_dir = os.path.dirname(filename)
                base_name = os.path.basename(filename).split('_')[0]  
                
                for file in os.listdir(base_dir):
                    if file.startswith(base_name) and os.path.join(base_dir, file) != filename:
                        try:
                            os.remove(os.path.join(base_dir, file))
                        except:
                            pass
            except Exception as cleanup_error:
                logging.error(f"Error during cleanup: {str(cleanup_error)}")
                
            if success:
                await status_message.edit_text(f"✅ {platform.capitalize()} video downloaded and sent successfully!")

        except Exception as e:
            error_message = str(e)
            await status_message.edit_text(f"Sorry, an error occurred: {error_message[:100]}...")
            logging.error(f"Download error for {url}: {error_message}")
    else:
        platforms = "YouTube, Instagram, or TikTok"
        await message.reply(f"Please send a valid {platforms} URL.")
        
async def main():
    await dp.start_polling(bot) 

if __name__ == "__main__":
    asyncio.run(main())


