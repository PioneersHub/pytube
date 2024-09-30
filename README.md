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





