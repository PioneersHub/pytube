# PyTube

Prepare videos hosted on Vimeo to be uploaded to YouTube. 

To share the videos, the following steps are required:

1. Download videos from Vimeo
2. Indentify and separate videos to upload them to the correct YouTube channel. Filter videos not to be shared.
3. Upload videos to the designated YouTube channel.
4. Collect metadata (e.g., speaker, title, description, link to slides)  
   and make a `record` (JSON) file for each video with all metadata:
   a. Via the Pretalx API: session and speaker information  
   b. Add descriptions from data collected in a. for social media sharing with OpenAI's GPT-3
   c. Cleanup and amke information provided consistent (Links to LinkedIn, GitHub,...)
5. Add YouTube metadata (title, description, tags, thumbnail) to the record files.

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



