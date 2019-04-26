# AutoVOD
A Python script to automatically scan a Twitch user's past broadcasts and make highlight videos for every day, combining the important moments from all videos from during that day into a single clip.

By default this works by detecting the loudest moments in the stream audio. There is an optional way to scan the broadcast at a specified framerate and inspect individual frames and their pixel values to extract useful information and determine parts of the video to be highlighted.

## Dependencies
* [concat](https://github.com/ArneVogel/concat) - to download videos from Twitch.
* [youtubeuploader](https://github.com/porjo/youtubeuploader) - to upload videos to YouTube.
* Python packages: moviepy, requests, numpy
* ImageMagick
* ffmpeg

## Installation
* Move the `concat` and `youtubeuploader` binaries into the `bin` folder.
* Provide `youtubeuploader` with a `client_secrets.json` file in the `bin` folder. See `youtubeuploader`'s README.
* Acquire a Twitch API key and fill it in at the beginning of `autovod.py`.
* Configure other settings, such as the Twitch channel name, at the beginning of the `autovod.py` Python script.
* Optionally install the font provided in the `resources` folder that is suitable for the text in final rendered clips.