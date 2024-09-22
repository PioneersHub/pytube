# Vimeo 2 YouTube

Prepare videos hosted on Vimeo to be uploaded to YouTube. 

1. Download videos from Vimeo
2. Add metadata (eg., speaker, title, description, link to slides)

## Configration

There is a general configuration file `config.yaml` that provides the general structure.

Individual configurations are stored in the local file `config_local.yaml` which must not be shared.

- Vimeo API access
- Google Spreadsheet IDs: They contain the Vimeo video links and Pretalx ID)
- Pretalx: Event information, custom assignments of session ID to a release channel (pycon/pydata)
  Note: Pretalx access is provided via `pythanis` which stores the credentials in a separate local file
- YouTube: API access
- OpenAI: API access

### Credentials for Pythanis

Pretalx, Google and Helpdesk (sending Emails):  
[See here](https://florianwilhelm.info/pytanis/latest/usage/installation/#retrieving-the-credentials-and-tokens) 
how to add credentials.

## YouTube

### Upload

Videos need to be uploaded via the YouTube **web interface**.  
API Uploads make videos private by default, and there is no way to change this setting.

Uploading is easy: one can upload 15 videos at a time by drag and drop.

The following steps are strongly recommended:

1. Name the files: {ID}-{Title}.mp4.
2. Make sure in Settings/Upload Default the title is **empty**.
   YouTube will use the filename as title, which is the desired behavior. 
   This way, it's straightforward to assign the video later (metadata updates, sharing links).

Caveats:

* It's impossible to get the filename used for the upload via the API, although it's available via the web interface. 
  Follow the recommendations above, step 2.
* API limits: Queries are limited per day, use them wisely.

### API

Cloud project used: python-videos in Alexander's *personal* Google Developer Console.

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
