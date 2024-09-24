# import json
# import os
# from pathlib import Path
# from pprint import pprint
#
# from googleapiclient.discovery import build
# from oauth2client.service_account import ServiceAccountCredentials
# from googleapiclient.http import MediaFileUpload
#
# try:
#     import httplib
# except ImportError:
#     import http.client as httplib
#
# import apiclient.http
# import httplib2
# from google_auth_oauthlib.flow import InstalledAppFlow
#
# import sys
#
# scopes = [
#     "https://www.googleapis.com/auth/youtube",
#     "https://www.googleapis.com/auth/youtube.force-ssl",
#     # "https://www.googleapis.com/auth/youtube.readonly"
# ]
#
# CLIENT_SECRET_FILE = "_private/client_secret_64160613381-i4q4jbrkr1ngl4cjvbrnfj7j20d6i2rf.apps.googleusercontent.com.json"
# CHANNEL_ID = "UCji5VWDkGzuRenyRQZ9OpFQ"  # PyConDE
# API_KEY = "AIzaSyBsyVMhtIawjANg8Wto2oaCbEMH70IiN-o"
#
# service_account_name = "conference-videos@pycon-videos.iam.gserviceaccount.com"
# oauth2_key_file_path = "_private/pycon-videos-150973a154e5.p12"
#
# API_SERVICE_NAME = 'youtube'
# API_VERSION = 'v3'
#
# youtube_data_api = None
#
#
# def authorize_service_account(service_account_name, oauth2_key_file_path):
#     credentials = ServiceAccountCredentials.from_p12_keyfile(
#         service_account_name,
#         oauth2_key_file_path,
#         scopes=scopes)
#     http = httplib2.Http()
#     http = credentials.authorize(http)
#     return http
#
#
# def list_videos(channel_id, max_results=50, page_token=None):
#     # Do you handle pagination  ?
#     global youtube_data_api
#     listresponse = youtube_data_api.search().list(
#         part='snippet',
#         # onBehalfOfContentOwner=content_owner,
#         # forContentOwner=content_owner,
#         channelId=channel_id,
#         type='video',
#         maxResults=max_results,
#         pageToken='' if not page_token else page_token
#     ).execute()
#     return listresponse
#
#
# def list_channel_videos(channel_id):
#     all_videos = []
#     videos = list_videos(channel_id)
#     pprint(videos)
#     all_videos.extend(videos.get('items'))
#     while videos.get('nextPageToken'):
#         videos = list_videos(CHANNEL_ID, page_token=videos.get('nextPageToken'))
#         all_videos.extend(videos.get('items'))
#         pprint(videos)
#     import json
#     with open('channel_videos.json', 'w') as f:
#         json.dump(all_videos, f)
#     return videos
#
#
# class YouTube:
#     """
#     Videos
#     methods and properties
#     https://developers.google.com/youtube/v3/docs/videos#resource
#     """
#
#     def __init__(self):
#         self.client = None
#         self.get_authenticated_service()
#
#     def get_authenticated_service(self):
#         flow = InstalledAppFlow.from_client_secrets_file(
#             CLIENT_SECRET_FILE, scopes)
#
#         credentials = flow.run_console()
#         self.client = build(API_SERVICE_NAME, API_VERSION, credentials=credentials)
#
#     def update_video_description(self, video_id, title, description, tags=None,
#                                  category_id=28,
#                                  default_language='en',
#                                  privacy_status='unlisted',
#                                  video_license='youtube',
#                                  embeddable=True,
#                                  recorded_iso=None,
#                                  ):
#         body = {
#             "id": video_id,
#             "snippet": {
#                 "categoryId": category_id,
#                 "defaultLanguage": default_language,
#                 "description": description,
#                 "tags": tags,
#                 "title": title,
#             },
#             "status": {
#                 "license": video_license,
#                 "privacyStatus": privacy_status,
#                 "embeddable": embeddable,
#             },
#             "recordingDetails": {}
#         }
#         if recorded_iso:
#             body['recordingDetails']['recordingDate'] = recorded_iso
#         try:
#             response = self.client.videos().update(
#                 body=body, part='snippet,status,recordingDetails').execute()
#             return response
#         except Exception as e:
#             return
#
#     def set_tumbnail(self, video_id, filepath):
#         request = self.client.thumbnails().set(
#             videoId=video_id,
#             media_body=MediaFileUpload(filepath)
#         )
#         response = request.execute()
#         return response
#
#     def upload_to_request(self, request, progress_callback):
#         """Upload a video to a Youtube request. Return video ID."""
#         while 1:
#             status, response = request.next_chunk()
#             if status and progress_callback:
#                 progress_callback(status.total_size, status.resumable_progress)
#             if response:
#                 if "id" in response:
#                     return response['id']
#                 else:
#                     raise KeyError("Expected field 'id' not found in response")
#
#
# def debug(obj, fd=sys.stderr):
#     """Write obj to standard error."""
#     print(obj, file=fd)
#
#
# def upload(resource, path, body, chunksize=4 * 1024 * 1024,
#            progress_callback=None, max_retries=10):
#     """Upload video to Youtube. Return video ID."""
#     body_keys = ",".join(body.keys())
#     media = apiclient.http.MediaFileUpload(path, chunksize=chunksize,
#                                            resumable=True, mimetype="application/octet-stream")
#     request = resource.videos().insert(part=body_keys, body=body, media_body=media)
#     upload_fun = lambda: _upload_to_request(request, progress_callback)
#     return lib.retriable_exceptions(upload_fun,
#                                     RETRIABLE_EXCEPTIONS, max_retries=max_retries)
#
#
# def set_description_from_json(recorded_at, video, video_id, website, yt):
#     tags = [x.strip() for x in video['domains'].split(',')]
#     if video['track'] == "PyData":
#         tags = ["Data Science", "Python"] + tags
#     else:
#         tags = ["Python"] + tags
#     title = video['title']
#
#     if 'Tutorial' in video['submission_type']:
#         title = 'Tutorial: ' + title
#
#     if len(title) > 100:
#         title = title[:99] + "…"
#
#     category_id = 28  # categoryId=28 - Wissenschaft
#     default_language = 'en'  # 2-letter ISO-639-1-Code
#     privacy_status = 'unlisted'
#     video_license = 'youtube'
#     video_embeddable = True
#     recorded_iso = video['recorded']
#     speakers_info = f"Speaker: {', '.join([x.get('name', '') for x in video['speakers']])}"
#     talk_website = f"https://de.pycon.org/program/{video['code']}"
#     description = f'{speakers_info}\n\nTrack:{video["track"]}\n{video["abstract"]}\n\n{recorded_at}\n{website}\n\n' \
#                   f'More details at the conference page: {talk_website}\n' \
#                   f'Twitter:  https://twitter.com/pydataberlin' \
#                   f'\nTwitter:  https://twitter.com/pyconde\n\n\n\n'
#
#     # <, > not allowed in YT titles, description
#     title = title.replace('>', '').replace('<', '')
#     description = description.replace('>', '').replace('<', '')
#
#     response = yt.update_video_description(video_id, title, description, tags, category_id,
#                                            default_language, privacy_status, video_license, video_embeddable, recorded_iso)
#     return response
#
#
# def read_pydata_video_ids():
#     with open("pydata_playlist_2019.txt") as f:
#         plist = f.readlines()
#     id_video = {v.strip().split(' _§_ ')[0]: {'youtube_id': k.strip(), 'name': v.strip().split(' _§_ ')[1]} for k, v in
#                 zip(plist[::2], plist[1::2])}
#     print(id_video)
#     return id_video
#
#
# def add_video_links_to_private_submissions():
#     video_list = json.load(open('talks_with_video_id.json'))
#     replace_ids = read_pydata_video_ids()
#     the_video_list = []
#     for d in video_list:
#         for vid, vd in replace_ids.items():
#             if d['code'] == vid:
#                 d['youtube_id'] = vd['youtube_id']
#                 continue
#         the_video_list.append(d)
#     submissions = json.load(open('../_private/submissions.json'))
#     new_submissions = []
#     for s in submissions:
#         for v in the_video_list:
#             if s['code'] == v['code']:
#                 s['youtube_id'] = v['youtube_id']
#                 s['video_link'] = f"https://www.youtube.com/embed/{v['youtube_id']}"
#                 continue
#         new_submissions.append(s)
#     json.dump(new_submissions, open('../_private/submissions.json', 'w'), indent=4)
#
#
# def main(video_list):
#     global youtube_data_api
#
#     # Disable OAuthlib's HTTPS verification when running locally.
#     # *DO NOT* leave this option enabled in production.
#     os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
#
#     recorded_at = "Recorded at the PyConDE & PyData Berlin 2019 conference."
#     website = "https://pycon.de"
#
#     videodir = Path('/Volumes/SD/PyConDE-Videos')
#
#     yt = YouTube()
#
#     do_this = ["description", "thumbnails"]  # description, upload, thumbnails
#
#     for video in video_list:
#         # if not video.get('filename'):
#         #     continue
#
#         # video_path = videodir / video['filename']
#         # if not video_path.exists():
#         #     continue
#
#         video_id = video['youtube_id']
#
#         res = "NO FEEDBACK"
#         if "description" in do_this:
#             res = set_description_from_json(recorded_at, video, video_id, website, yt)
#
#         if "thumbnails" in do_this:
#             filepath = Path(f"../website/assets/static/media/twitter/{video['code']}.jpg").resolve()
#             if not filepath.exists():
#                 print("thumbnail not found.", video['code'], video['title'])
#                 continue
#             res = yt.set_tumbnail(video_id, str(filepath))
#
#         print(res)
#
#         a = 1
#
#
# def rename_de_pyconde_to_remove():
#     video_list = youtube_pydata()
#     pycondede_video_list = json.load(open('talks_with_video_id.json'))
#     yt = YouTube()
#     for video in video_list:
#         # get YT id @ PYCONDE
#         match = [x for x in pycondede_video_list if x['code'] == video['code']]
#         if not match:
#             continue
#         video_id = match[0]['youtube_id']
#         title = f"MOVED2PYDATA {video['title']}"
#         if len(title) > 100:
#             title = title[:99] + "…"
#         title = title.replace('>', '').replace('<', '')
#         res = "NO FEEDBACK"
#         category_id = 28  # categoryId=28 - Wissenschaft
#
#         body = {
#             "id": video_id,
#             "snippet": {
#                 "title": title,
#                 "categoryId": category_id,
#             }
#         }
#         try:
#             res = yt.client.videos().update(
#                 body=body, part='snippet').execute()
#             print(res)
#         except Exception as e:
#             return
#
#
# def youtube_con():
#     video_list = json.load(open('talks_with_video_id.json'))
#     return video_list
#
#
# def youtube_pydata():
#     pydata_videos = read_pydata_video_ids()
#     all_videos = json.load(open('talks_with_video_id.json'))
#     video_list = []
#     for code in pydata_videos:
#         match = [x for x in all_videos if x['code'] == code]
#         if not match:
#             raise AssertionError(f'code {code} not found')
#         if match:
#             match = match[0]
#             match['youtube_id'] = pydata_videos[code]['youtube_id']
#             video_list.append(match)
#
#     return video_list
#
#
# def get_talks_per_confernece():
#     all_videos = json.load(open('../website/databags/submissions.json'))
#
#
#
# if __name__ == "__main__":
#     # video_list = youtube_pydata()
#     # main(video_list)
#     # rename_de_pyconde_to_remove()
#     add_video_links_to_private_submissions()
