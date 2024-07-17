# Vimeo 2 YouTube

Prepare videos to be uploaded to YouTube from Vimeo. Download videos from Vimeo, add metadata (speaker, title,
description, link to slides)

## YouTube

### Upload

Videos need to be uploaded via the YouTube web interface.
API Uploads make videos private by default, and there is no way to change this setting.

Uploading is easy: one can upload 15 videos at a time by drag and drop.

The following steps are recommended:

1. Name the files: {ID}-{Title}.mp4.
2. Make sure in Settings/Upload Default the title is empty. YouTube will use the filename as title. This makes it eas to
   find the video later.

Caveats:

* It's impossible to get the filename used for the upload via the API, although it's available via the web interface see
  recommendations, step 2.
* API limits: Queries are limited, use them wisely.

### API
Cloud project used: python-videos in Alexander's Google Developer Console


## LinkedIn

### Apps/Products
Request both
- Share on LinkedIn
- Sign In with LinkedIn using OpenID Connect (required to get author UID)

https://api.linkedin.com/v2/userinfo
'sub' is urn:li:person:{sub}
https://stackoverflow.com/questions/77962676/how-to-get-linkedin-urn

Token generator:
https://www.linkedin.com/developers/tools/oauth/token-generator?

Blogposts:
https://blog.futuresmart.ai/how-to-automate-your-linkedin-posts-using-python-and-the-linkedin-api
https://towardsdatascience.com/linkedin-api-python-programmatically-publishing-d88a03f08ff1
https://www.jcchouinard.com/linkedin-api-how-to-post/
