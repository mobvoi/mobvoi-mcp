import asyncio
import logging
import os
import time
import hashlib

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from mcp.types import TextContent

import mobvoi_mcp
from mobvoi_mcp.utils import (
    make_output_path,
    make_output_file,
    handle_input_file,
    play,
    speaker_list_filter
)
from mobvoi_mcp.api_client import ApiClient, download_file
from mobvoi_mcp.utils import LanguageTable

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

logger.info(f"mobvoi-mcp version: {mobvoi_mcp.__version__}")

load_dotenv()
app_key = os.getenv("APP_KEY")
app_secret = os.getenv("APP_SECRET")
base_path = os.getenv("MOBVOI_MCP_BASE_PATH")
region = os.getenv("MOBVOI_MCP_REGION")

logger.info(f"region: {region}")
logger.info(f"base_path: {base_path}")

if not app_key:
    raise ValueError("APP_KEY environment variable is required")
if not app_secret:
    raise ValueError("APP_SECRET environment variable is required")
if not region:
    region = "mainland"

mcp = FastMCP("Mobvoi")

api_client = ApiClient(app_key, app_secret, region)
language_table = LanguageTable()

@mcp.tool(
    description="""Obtain the list of speaker IDs from Mobvoi sound library and cloned by users themselves.
    
    Args:
        voice_type (str, optional): The type of voices to list. Values range ["all", "system", "voice_cloning"], with "all" being the default.

    Returns:
        Text content with the list of speaker IDs(include mobvoi_sound_library, user_cloned).
    """
)
def get_speaker_list(voice_type: str = "all"):
    logger.info(f"get_speaker_list is called.")
    timestamp = str(int(time.time()))
    message = '+'.join([app_key, app_secret, timestamp])
    m = hashlib.md5()
    m.update(message.encode("utf8"))
    signature = m.hexdigest()
    request = {
        "appkey": app_key,
        "timestamp": timestamp,
        "signature": signature
    }
    try:
        res = api_client.post("tts.get_speaker_list", request)
        systemVoice = res.json()['data']['systemVoice']
        voiceCloning = res.json()['data']['voiceCloning']
        galaxy_speakers = speaker_list_filter(systemVoice)
        output_text = ""
        if voice_type == "all":
            output_text = f"Success. Get Speaker list success, systemVoice: {galaxy_speakers}, voiceCloning: {voiceCloning}"
        elif voice_type == "system":
            output_text = f"Success. Get Speaker list success, systemVoice: {galaxy_speakers}"
        elif voice_type == "voice_cloning":
            output_text = f"Success. Get Speaker list success, voiceCloning: {voiceCloning}"
        return TextContent(
            type="text",
            text=f"Success. Get Speaker list success, {output_text}",
        )
    except Exception as e:
        logger.exception(f"Error in get_speaker_list: {str(e)}")
        return TextContent(type="text", text=f"Error: {str(e)}")

@mcp.tool(
    description="""The text_to_speech service of Mobvoi. Convert text to speech with a given speaker and save the output audio file to a given directory.
    Directory is optional, if not provided, the output file will be saved to $HOME/Desktop.
    You can choose speaker by providing speaker parameter. If speaker is not provided, the default speaker(xiaoyi_meet) will be used.
    
    ⚠️ COST WARNING: This tool makes an API call to Mobvoi TTS service which may incur costs. Only use when explicitly requested by the user.
    
    Args:
        text (str): The text to convert to speech.
        speaker (str): Determine which speaker's voice to be used to synthesize the audio.
        audio_type (str): Determine the format of the synthesized audio. Value can choose form [pcm/mp3/speex-wb-10/wav].
        speed (float): Control the speed of the synthesized audio. Values range from 0.5 to 2.0, with 1.0 being the default speed. Lower values create slower, more deliberate speech while higher values produce faster-paced speech. Extreme values can impact the quality of the generated speech. Range is 0.7 to 1.2.
        rate(int): Control the sampling rate of the synthesized audio. Value can choose from [8000/16000/24000], with 24000 being the deault rate.
        volume(float): Control the volume of the synthesized audio. Values range from 0.1 to 1.0,  with 1.0 being the default volume.
        pitch(float): Control the pitch of the synthesized audio. Values range from -10 to 10,  with 0 being the default pitch. If the parameter is less than 0, the pitch will become lower; otherwise, it will be higher.
        streaming(bool): Whether to output in a streaming manner. The default value is false.
        output_directory (str): Directory where files should be saved.
            Defaults to $HOME/Desktop if not provided.

    Returns:
        Text content with the path to the output file and name of the speaker used.
    """
)
def text_to_speech(
    text: str,
    speaker: str = "xiaoyi_meet",
    audio_type: str = "mp3",
    speed: float = 1.0,
    rate: int = 24000,
    volume: float = 1.0,
    pitch: float = 0.0,
    streaming: bool = False,
    output_directory: str = "",
):
    logger.info(f"text_to_speech is called.")
    
    if text == "":
        return TextContent(type="text", text="Error: Text is required.")
    
    output_path = make_output_path(output_directory, base_path)
    output_file_name = make_output_file("tts", speaker, output_path, "mp3")
    
    timestamp = str(int(time.time()))
    message = '+'.join([app_key, app_secret, timestamp])
    m = hashlib.md5()
    m.update(message.encode("utf8"))
    signature = m.hexdigest()
    request = {
        "appkey": app_key,
        "timestamp": timestamp,
        "signature": signature,
        "text": text,
        "speaker": speaker,
        "audio_type": audio_type,
        "speed": speed,
        "rate": rate,
        "volume": volume,
        "pitch": pitch,
        "streaming": streaming
    }
    try:
        res = api_client.post("tts.text_to_speech", request)
        content = res.content
        if len(content) < 100:
            logger.error(f"Invalid audio data length: {len(content)}")
            raise Exception("Failed to get audio data from text to speech service")
        else:
            with open(output_path / output_file_name, "wb") as f:
                f.write(content)
                logger.info(f"Audio file written: {output_path / output_file_name}")
            return TextContent(
                type="text",
                text=f"Success. File saved as: {output_path / output_file_name}. Speaker used: {speaker}",
            )
            
    except Exception as e:
        logger.exception(f"Error in text_to_speech: {str(e)}")
        return TextContent(type="text", text=f"Error: {str(e)}")

@mcp.tool(
    description="""The voice_clone service of Mobvoi. Clone a voice from a given url or local audio file. This tool will return a speaker id which can be used in text_to_speech tool.
    
    ⚠️ COST WARNING: This tool makes an API call to Mobvoi TTS service which may incur costs. Only use when explicitly requested by the user.
    
    Args:
        is_url (bool): Whether the audio file is a url.
        audio_file (str): The path or url of the audio file to clone.
    """
)
def voice_clone(is_url: bool, audio_file: str):
    logger.info(f"voice_clone is called.")
    
    timestamp = str(int(time.time()))
    message = '+'.join([app_key, app_secret, timestamp])
    m = hashlib.md5()
    m.update(message.encode("utf8"))
    signature = m.hexdigest()
    request = {
        "appkey": app_key,
        "timestamp": timestamp,
        "signature": signature,
        "wavUri": audio_file if is_url else None
    }
    files = {
        'file': open(audio_file, 'rb')
    } if not is_url else None
    logger.info(f"audio file length: {len(files['file'].read())}")
    try:
        res = api_client.post("tts.voice_clone", request={}, data=request, file=files)
        return TextContent(type="text", text=f"Success. Speaker id: {res.json()['speaker']}")
    except Exception as e:
        logger.exception(f"Error in voice_clone: {str(e)}")
        return TextContent(type="text", text=f"Error: {str(e)}")

@mcp.tool(description="Play an audio file. Supports WAV and MP3 formats.")
def play_audio(input_file_path: str) -> TextContent:
    file_path = handle_input_file(input_file_path)
    play(open(file_path, "rb").read(), use_ffmpeg=False)
    return TextContent(type="text", text=f"Successfully played audio file: {file_path}")


@mcp.tool(
    description="""Generate a video from a given image URL and an audio URL. If a person is in the image, the video will be a talking head video, driven by the audio.
    It will consume some time to generate the video, wait with patience.
    It will return a text message indicating that the task is submitted successfully, task id will be returned.
    After getting the task id, you may use the query_photo_drive_avatar tool to query the result of the task.
    
    ⚠️ COST WARNING: This tool makes an API call to Mobvoi which may incur costs. Only use when explicitly requested by the user.

    Args:
        image_url: The URL of the image to use in the video.
        audio_url: The URL of the audio to use in the video.

    Returns:
        A text message indicating the success of the video generation task, task id will be returned if success.
    """
)
def photo_drive_avatar(image_url: str, audio_url: str):
    logger.info(f"photo_drive_avatar is called.")

    request = {
        "imageUrl": image_url,
        "audioUrl": audio_url
    }
    try:
        res = api_client.post("avatar.photo_drive_avatar", request).json()
        if res is None:
            raise Exception("Failed to call photo drive avatar service")
        task_id = res.get("data", None)
        if task_id is None:
            raise Exception("Failed to get task id")
    except Exception as e:
        logger.exception(f"Error in photo_drive_avatar: {str(e)}")
        return TextContent(type="text", text=f"Error: {str(e)}")
    
    return TextContent(type="text", text=f"Success. Task id: {task_id}")

@mcp.tool(
    description="""Query the result of the photo drive avatar task.
    It will return a text message indicating that the task is completed and the video is saved to the output directory.
    If the output directory is not specified, only result url will be returned.

    If the return status indiacting the task is still running, you may use this tool again after a while.

    Args:
        task_id: The task id of the photo drive avatar task.
        output_dir: The directory to save the generated video, you can send the absolute path of the current working directory.
                    The result will be saved into $output_dir/$task_id/result.mp4.

    Returns:
        A text message indicating the status of the task.
        Result url will be returned if success, saved path will be returned if output directory is specified.
    """
)
def query_photo_drive_avatar(task_id: str, output_dir: str = ""):
    logger.info(f"query_photo_drive_avatar is called.")
    try:
        response = api_client.get("avatar.query_photo_drive_avatar", path=task_id).json()
        res = response.get("data", None)
        logger.info(f"query_photo_drive_avatar response: {res}")
        if res is None:
            raise Exception("Failed to call photo drive avatar result service")
        status = res.get("status", None)
        if status == "suc":
            result_url = res.get("resultUrl", None)
            if output_dir != "":
                output_path = os.path.join(output_dir, f"{task_id}.mp4")
                os.makedirs(output_dir, exist_ok=True)
                download_file(result_url, output_path)
                return TextContent(type="text", text=f"Success. Result url: {result_url}. Result saved as: {output_path}")
            else:
                return TextContent(type="text", text=f"Success. Result url: {result_url}")
        elif status == "ing":
            return TextContent(type="text", text=f"Task {task_id} is still running, please wait for a while.")
        else:
            raise Exception(f"Task {task_id} failed with status: {status}, message: {res.get('msg', 'Unknown error')}")
    except Exception as e:
        logger.exception(f"Error in query_photo_drive_avatar: {str(e)}")
        return TextContent(type="text", text=f"Error: {str(e)}")

@mcp.tool(
    description="""This tool aims to perform the voice over task, which generates a video from a given video URL and an audio URL.
    The result video will be a talking head video, with lip sync driven by the audio.
    It will consume some time to generate the video, wait with patience.
    It will return a text message indicating that the task is submitted successfully, task id will be returned.
    After getting the task id, you may use the query_video_dubbing tool to query the result of the task.

    ⚠️ COST WARNING: This tool makes an API call to Mobvoi which may incur costs. Only use when explicitly requested by the user.

    Args:
        video_url: The URL of the video to use as the base.
        audio_url: The URL of the audio to use in the video.

    Returns:
        A text message indicating the success of the video generation task.
    """
)
def video_dubbing(video_url: str, audio_url: str):
    logger.info(f"video_dubbing is called.")

    request = {
        "videoUrl": video_url,
        "wavUrl": audio_url
    }

    try:
        res = api_client.post("avatar.video_dubbing", request).json()
        logger.info(f"video_dubbing response: {res}")
        if res is None:
            raise Exception("Failed to call video dubbing service")
        task_id = res.get("data", None)
        if task_id is None:
            raise Exception("Failed to get task id")
    except Exception as e:
        logger.exception(f"Error in video_dubbing: {str(e)}")
        return TextContent(type="text", text=f"Error: {str(e)}")
    
    return TextContent(type="text", text=f"Success. Task id: {task_id}")

@mcp.tool(
    description="""Query the result of the video dubbing task.
    It will return a text message indicating that the task is completed and the video is saved to the output directory.
    If the output directory is not specified, only result url will be returned.

    If the return status indiacting the task is still running, you may use this tool again after a while.

    Args:
        task_id: The task id of the video dubbing task.
        output_dir: The directory to save the generated video, you can send the absolute path of the current working directory.
                    The result will be saved into $output_dir/$task_id/result.mp4.

    Returns:
        A text message indicating the status of the task.
        Result url will be returned if success, saved path will be returned if output directory is specified.
"""
)
def query_video_dubbing(task_id: str, output_dir: str = ""):
    logger.info(f"query_video_dubbing is called.")

    task_id_req = {
        "taskId": task_id,
        "taskUuid": task_id
    }

    header = {"Content-Type": "application/json"}

    try:
        response = api_client.get("avatar.query_video_dubbing", request=task_id_req, headers=header).json()
        res = response.get("data", None)
        logger.info(f"query_video_dubbing response: {res}")
        if res is None:
            raise Exception("Failed to query video dubbing result.")
        status = res.get("status", None)
        if status == "suc":
            result_url = res.get("resultUrl", None)
            if output_dir != "":
                output_path = os.path.join(output_dir, f"{task_id}.mp4")
                os.makedirs(output_dir, exist_ok=True)
                download_file(result_url, output_path)
                return TextContent(type="text", text=f"Success. Result url: {result_url}. Result saved as: {output_path}")
            else:
                return TextContent(type="text", text=f"Success. Result url: {result_url}")
        elif status == "ing":
            return TextContent(type="text", text=f"Task {task_id} is still running, please wait for a while.")
        else:
            raise Exception(f"Task {task_id} failed with status: {status}, message: {res.get('msg', 'Unknown error')}")
    except Exception as e:
        logger.exception(f"Error in query_video_dubbing: {str(e)}")
        return TextContent(type="text", text=f"Error: {str(e)}")

@mcp.tool(
    description="""Get a list of supported languages for video translation.

    This function is still work in progress, use with caution.
    The language list format looks like:
    chinese (zh), True, False

    * The first column is the language name.
    * The second column is the language code. 
    * The third column is whether the language can be used as source language.
    * The fourth column is whether the language can be used as target language.

    Returns:
        A text message indicating the information of supported languages for video translation

    """
)
def video_translate_language_list():
    logger.info(f"video_translate_language_list is called.")
    language_list = language_table.get_language_list()
    language_list_str = "\n".join([f"{language.name} ({language.code}), {language.is_src}, {language.is_target}" for language in language_list])
    return TextContent(type="text", text=language_list_str)

def main():
    logger.info("Starting MCP server")
    mcp.run()


if __name__ == "__main__":
    main()