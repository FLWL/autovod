from moviepy.editor import *
import numpy as np
import requests
import sys
import json
import datetime
import subprocess
import time
import os
from proglog import TqdmProgressBarLogger


# --- content configuration
twitch_channel_name = "TwitchChannelName" # Twitch channel name to scan for highlights
video_intro_duration = 0.4 # Fade in duration in seconds at the start of the final clip
video_outro_duration = 0.4 # Fade out duration in seconds at the end of the final clip
max_time_without_events = 60 * 10 # If visual processing of the broadcast has not detected any events in this amount
# of seconds, make sure that a highlight gets made out of this region based on audio cues. Default is 60 * 10 =
# 600 seconds = 10 minutes.
do_visual_processing = False # whether to analyze the broadcast frames instead of relying only on audio
highlight_cut_volume_threshold = 0.01 # to avoid abruptly ending or starting a highlight mid-action, it can be
# extended until the audio volume falls below this threshold
max_extra_start_time = 5.0 # how long a highlight can be extended from the start due to high audio volume
max_extra_end_time = 5.0 # the same thing, but for the end (in seconds)
post_event_duration = 4.0 # include this many seconds after the event has occurred in the highlight
pre_event_duration = 10.0 # include this many seconds before the event in the highlight
join_highlights_closer_than = 30.0 # if two highlights occur this many seconds close to each other, they will be
# merged and treated as one in the final clip
youtube_category_id = 20 # what category to put the final clip in, for example 20 = gaming
youtube_privacy_status = "public"
youtube_video_language = "en"
youtube_playlists_dictionary = { # a list of playlists and their IDs the YouTube channel has, to add the final video to suitable ones
    "TwitchChannelName": "PLc_***",
    "GAME'S NAME": "PLc_***"
}
watermark_font = "Titillium-WebBold" # a simple text in the corner of the video to let viewers know its a highlight
watermark_font_size = 28
watermark_color = "white"


# ---- technical configuration
binary_path = "bin/"
concat_binary_name = "concat_win.exe" if os.name == 'nt' else "concat_linux"
youtubeuploader_binary_name = "youtubeuploader_windows_amd64.exe" if os.name == 'nt' else "youtubeuploader_linux_amd64"
twitch_client_id = "***" # the key to access Twitch API
num_threads = 6 # number of CPU threads to use when encoding the final clip


# ---- program code
cut_audio = lambda i: my_clip.audio.subclip(i - 0.75, i + 0.75).to_soundarray(fps=22000)
calculate_volume = lambda array: np.sqrt(((1.0 * array) ** 2).mean())


def find_sound_event(my_clip, last_event_time, current_time):
    # go through the clip's audio in 10 second intervals
    highest_volume = 0.0
    highest_volume_time = 0
    for i in range(last_event_time + 5, current_time - 5, 10):
        sound_array = my_clip.audio.subclip(i - 5, i + 5).to_soundarray(fps=22000)
        volume = calculate_volume(sound_array)

        if volume > highest_volume:
            highest_volume = volume
            highest_volume_time = i
            print("Highest volume found at " + str(i) + ", scanning " + str(last_event_time) + " to " + str(current_time) + ", volume: " + str(volume))

    if highest_volume_time != 0:
        return highest_volume_time

    return -1


def download_vod(video_id):
    wd = os.getcwd()
    os.chdir(binary_path)
    subprocess.call([concat_binary_name, "-vod", video_id])
    os.chdir(wd)


def upload_video(video_path, metadata_path):
    wd = os.getcwd()
    os.chdir(binary_path)
    subprocess.call([youtubeuploader_binary_name, '-headlessAuth', '-filename', '../' + video_path, '-metaJSON', '../' + metadata_path])
    os.chdir(wd)


print("Starting script. Time is: " + str(datetime.datetime.now()))
logger = TqdmProgressBarLogger()

# check which broadcasts have already been processed
with open("resources/processed_broadcasts.txt", "r+") as f:
    processed_broadcasts = f.readlines()

processed_broadcasts = [x.strip() for x in processed_broadcasts] # remove whitespace characters like `\n` at the end of each line

# get latest broadcasts from twitch
print("Fetching latest broadcasts from Twitch...")
twitch_api_link = "https://api.twitch.tv/kraken/channels/" + twitch_channel_name + "/videos?client_id=" + twitch_client_id + "&broadcast_type=archive"
twitch_response_text = requests.get(twitch_api_link).text
twitch_response = json.loads(twitch_response_text)
print("Twitch response (max 128 chars): " + twitch_response_text[:128] + (" ..." if len(twitch_response_text) > 128 else ""))

# find oldest unprocessed broadcast and the others that were published on the same day
oldest_video_title = ""
oldest_video_date = ""
videos_to_process = []
for video in reversed(twitch_response["videos"]):
    video_id = video["_id"][1:]
    video_length = video["length"]

    if video_id in processed_broadcasts:
        continue

    date = datetime.datetime.strptime(video["published_at"], "%Y-%m-%dT%H:%M:%SZ")

    if not oldest_video_date:
        oldest_video_date = date
        oldest_video_title = video["title"]
    elif date.date() != oldest_video_date.date():
        continue # skip this broadcast if its not on the same date as the oldest unprocessed one we found

    videos_to_process.append(video_id)
    print("Added video " + video_id + " of length " + str(video_length) + " from " + str(date.date()) + " to list: " + video["title"])

if len(videos_to_process) == 0:
    sys.exit("Exiting: no videos to process at this time.")

# check if a ready made video is already done and is waiting for upload
formatted_date = oldest_video_date.strftime("%d.%m.%Y")
formatted_date_long = oldest_video_date.strftime("%d. %B %Y")
final_clip_path = "resources/edit_" + formatted_date + ".mp4"
final_metadata_path = "resources/edit_" + formatted_date + ".json"

final_clip_exists = False
try:
    VideoFileClip(final_clip_path).close()
    final_clip_exists = True
    print("Final clip already exists.")
except Exception as e:
    final_clip_exists = False
    print("Final clip has not been created yet.")

# check if we have already built metadata for the final clip
final_metadata_exists = False
if os.path.isfile(final_metadata_path):
    final_metadata_exists = True
    print("Final metadata already exists.")
else:
    final_metadata_exists = False
    print("Final metadata has not been created yet.")

# start putting together the video description
title = twitch_channel_name + " Highlights " + formatted_date + ": " + oldest_video_title
description = "Live stream highlights from " + twitch_channel_name + " on " + formatted_date + ": " + oldest_video_title + "\n\n"
tags = ["highlights", "twitch"]

# create final clip if it does not exist
total_games = []
if not final_clip_exists or not final_metadata_exists:
    print("Fetching " + str(len(videos_to_process)) + " videos...")

    loaded_videos = []
    loaded_videos_ids = []
    for video_id in videos_to_process:
        video_path = "bin/" + video_id + ".mp4"

        tries = 0
        max_tries = 3
        while True:
            # try to open the video file to see if it is valid or needs (re)downloading
            try:
                loaded_videos.append(VideoFileClip(video_path))
                loaded_videos_ids.append(video_id)
                print("Video " + video_id + " loaded.")
                break
            except Exception as e:
                if tries == max_tries:
                    print("Failed to download " + video_id + " after " + str(max_tries) + " tries. Skipping video.")
                    break

                print("----------------- Downloading " + video_id + "... (" + str(tries) + "/" + str(max_tries) + ")")
                tries += 1
                download_vod(video_id)

    print(str(len(loaded_videos)) + " videos were loaded for processing.")

    clips = []
    clips_total_duration = 0
    for i, my_clip in enumerate(loaded_videos):
        time.sleep(0.25)
        print("----------------- Processing " + loaded_videos_ids[i] + "... (" + str(i+1) + "/" + str(len(loaded_videos)) + ")")
        print("Duration of video: ", my_clip.duration)
        print("FPS: ", my_clip.fps)
        time.sleep(0.25) # time so console messages don't get messed up

        event_times = []
        event_times_games = []
        events = 1

        saved_event_times_file = "resources/edit_" + formatted_date + "_events_" + str(i) + ".json"
        print("Saving the times of detected events to: " + saved_event_times_file)
        visually_processed = False

        # check if we have already done visual processing
        try:
            with open(saved_event_times_file, 'r+') as f:
                data = json.load(f)
                visually_processed = data["visually_processed"]
                event_times = data["event_times"]
                event_times_games = data["event_times_games"]
                print("Opened events file: " + data["event_times_games"])
        except Exception as e:
            print("No saved times file.")

        if not visually_processed:
            if do_visual_processing:
                for t, frame in my_clip.iter_frames(fps=4, with_times=True, logger=logger): # scan a frame from the video every 0.25 seconds
                    # Here the image data is accessible for visual analysis, such as reading the color
                    # of pixels at the most basic level.

                    # As an example we check a value of a single pixel to detect something on screen.
                    # In practice just doing that is quite unreliable, but a combination of multiple
                    # pixel checks can be quite effective, for example to detect specific ending screens
                    # of a game or kill messages.
                    pixel = frame[10][10] # get the pixel from 10, 10 coordinates
                    if pixel[0] == 124 and pixel[1] == 199 and pixel[2] == 19: # check for some arbitary value
                        print("Event detected at: " + str(t))
                        event_times.append(t) # by marking down the event time, we make sure it gets included in the final clip
                        event_times_games.append("GAME'S NAME")
                        events += 1
                        #my_clip.save_frame("resources/frames/event" + str(events) + ".png", t) # a way to debug by saving images of event frames

            # save event times for this clip and mark it visually processed
            with open(saved_event_times_file, 'w') as f:
                data = {}
                data["event_times"] = event_times
                data["event_times_games"] = event_times_games
                data["visually_processed"] = True
                json.dump(data, f, indent=4)
        else:
            print("Clip has already been visually processed. Loaded events from json file.")

        # check for long periods without any events, and attempt to fill such voids
        # by analyzing audio cues for highlights
        last_event_time = 0
        current_event_index = 0
        for current_time in range(0, int(my_clip.duration), 60):
            if len(event_times) > current_event_index and event_times[current_event_index] < current_time:
                last_event_time = int(event_times[current_event_index])
                current_event_index += 1

            if current_time - last_event_time > max_time_without_events:
                print("No events in last " + str(max_time_without_events / 60) + " minutes: " + str(current_time))

                additional_event_time = find_sound_event(my_clip, last_event_time, current_time)
                if additional_event_time != -1:
                    event_times.insert(current_event_index, additional_event_time)
                    event_times_games.insert(current_event_index, "")
                    current_event_index += 1

                last_event_time = current_time

        # video analyzed, events found, figure out times to clip
        print("Found " + str(len(event_times)) + " events:")
        print(event_times)

        clip_start_times = []
        clip_end_times = []
        clip_games = []

        # calculate starting/ending positions for all events
        for event_n, event_t in enumerate(event_times):
            # calculate ending position
            base_end_time = event_t + post_event_duration
            extra_end_time = 0.0

            while True:
                volume = calculate_volume(cut_audio(base_end_time + extra_end_time))

                if volume < highlight_cut_volume_threshold or extra_end_time > max_extra_end_time:
                    break
                else:
                    extra_end_time += 0.5

            # calculate start position
            base_start_time = event_t - pre_event_duration
            extra_start_time = 0.0

            while True:
                volume = calculate_volume(cut_audio(base_start_time - extra_start_time))

                if volume < highlight_cut_volume_threshold or extra_start_time > max_extra_start_time:
                    break
                else:
                    extra_start_time += 0.5

            start_time = max(0, base_start_time - extra_start_time)
            end_time = base_end_time + extra_end_time
            clip_start_times.append(start_time)
            clip_end_times.append(end_time)
            clip_games.append(event_times_games[event_n])

        # join clips that are too close together or overlapping
        total_clips_joined = 0
        while True:
            clips_joined = 0

            for i in range(len(clip_start_times) - 1):
                current_end = clip_end_times[i]
                next_start = clip_start_times[i + 1]

                if next_start - current_end <= join_highlights_closer_than:
                    clip_end_times[i] = clip_end_times[i + 1]

                    del clip_start_times[i + 1]
                    del clip_end_times[i + 1]
                    del clip_games[i + 1]
                    clips_joined += 1
                    total_clips_joined += 1
                    break

            if clips_joined == 0:
                break

        print(str(total_clips_joined) + " clips joined.")
        print("Clips' start and end times calculated (" + str(len(clip_start_times)) + " clips):")
        print(clip_start_times)
        print(clip_end_times)
        print(clip_games)

        # cut out clips at the calculated times and add them to the main array
        current_game = ""
        for i in range(len(clip_start_times)):
            if current_game != clip_games[i] and len(clip_games[i]) != 0:
                # we switched to a different game, mark it down in the description
                seconds_into_video = video_intro_duration + clips_total_duration
                formatted_seconds = time.strftime("%M:%S", time.gmtime(seconds_into_video))
                description += formatted_seconds + " - " + clip_games[i] + "\n"
                current_game = clip_games[i]

                if current_game not in total_games:
                    total_games.append(current_game)

                if current_game not in tags:
                    tags.append(current_game)

            clip = my_clip.subclip(clip_start_times[i], clip_end_times[i])
            clips.append(clip)
            clips_total_duration += clip.duration

    if len(clips) == 0:
        time.sleep(0.25)
        print("No clips to combine. Skipping.")

        # mark videos as processed
        with open("resources/processed_broadcasts.txt", "a+") as f:
            for item in videos_to_process:
                if item:
                    f.write(item)
                    f.write("\r\n")

        for video_id in videos_to_process:
            path = "bin/" + video_id + ".mp4"
            os.remove(path)

        sys.exit("No clips to combine. Exiting.")

    description += "\nVisit " + twitch_channel_name + " on Twitch: https://twitch.tv/" + twitch_channel_name

    if not final_metadata_exists:
        print("----------------- Creating final clip metadata...")

        playlist_ids = []
        if twitch_channel_name in youtube_playlists_dictionary:
            playlist_ids.append(youtube_playlists_dictionary[twitch_channel_name])

        for game in total_games:
            if game in youtube_playlists_dictionary:
                if youtube_playlists_dictionary[game] not in playlist_ids:
                    playlist_ids.append(youtube_playlists_dictionary[game])

        data = {}
        data["title"] = title
        data["description"] = description
        data["tags"] = tags
        data["privacyStatus"] = youtube_privacy_status
        data["embeddable"] = True
        data["categoryId"] = str(youtube_category_id)
        data["playlistIds"] = playlist_ids
        data["language"] = youtube_video_language

        with open(final_metadata_path, 'w') as f:
            json.dump(data, f, indent=4)

    if not final_clip_exists:
        print("----------------- Rendering final clip...")
        clips[0] = clips[0].fadein(video_intro_duration)
        clips[-1] = clips[-1].fadeout(video_outro_duration)

        # text on screen that notifies the viewer that these are highlights and what time are they taken on
        watermark = TextClip("HIGHLIGHTS FROM " + formatted_date, color=watermark_color, fontsize=watermark_font_size, font=watermark_font).set_pos((20, 10)).set_duration(clips_total_duration)

        # save the final clip
        final_clip = CompositeVideoClip([concatenate_videoclips(clips), watermark])
        final_clip.write_videofile(final_clip_path, threads=num_threads)
        final_clip.close()

    # close the loaded videos to prevent memory leaks and pipe errors hopefully
    for vid in loaded_videos:
        vid.close()

# upload to youtube
print("----------------- Uploading to YouTube...")
upload_video(final_clip_path, final_metadata_path)

# mark videos as processed
with open("resources/processed_broadcasts.txt", "a+") as f:
    for item in videos_to_process:
        if item:
            f.write(item)
            f.write("\r\n")

for video_id in videos_to_process:
    path = "bin/" + video_id + ".mp4"
    os.remove(path)
