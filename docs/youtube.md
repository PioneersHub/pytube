# YouTube

!!! warning
    The Google-API wrapper currently does not work for macOS Sequoia, yet (22.09.2024).

## Preparations
[See the required API access below.](#api).


## Uploading Videos

Videos need to be uploaded via the YouTube **web interface**.  
API Uploads make videos private by default, and there is no way to change this setting.

Uploading is easy: one can upload 15 videos at a time by drag and drop.

All following steps are required:

1. Include PreTix-Session-ID in name the files, e.g., {PreTix-Session-ID}-{Title}.mp4.
2. Make sure in Settings/Upload Default the title is **empty**. 
 
YouTube will use the filename as title, which is the desired behavior. 
This way, it's straightforward to assign the video later (metadata updates, sharing links).

### Caveats

* It's impossible to get the filename used for the upload via the API, although the information is
available via the web interface. 
  Follow the recommendations above, step 2.
* API limits: Queries are limited per day, use them wisely.

## API

Access to the YouTube API V3 is required to update the metadata of the videos.
To access the YouTube API V3 a Google Cloud project is required. 

### How to Get a YouTube API Key
1. Log in to Google Developers Console.
2. Create a new project.
3. On the new project dashboard, click Explore & Enable APIs.
4. In the library, navigate to YouTube Data API v3 under YouTube APIs.
5. Enable the YouTube API V3.
6. Create credentials:
    a. API key
    b. OAuth2.0 client ID

There are plenty of detailed tutorials available on the web.

### Caveats
 * Metadata updates require OAuth2.0 authentication. API keys or service accounts are not sufficient.
 * Status updates can be requested with a simple API key.
