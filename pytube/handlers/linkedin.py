import json

import requests

from pytube import conf, logger


class LinkedInPost:
    def __init__(self):
        self.credentials = conf.linkedin
        # same for all requests
        self.headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0",
            "LinkedIn-Version": "202409",
        }

    @property
    def company_id(self) -> str:
        return self.credentials.company_id

    @property
    def access_token(self) -> str:
        return self.credentials.access_token

    # noinspection SpellCheckingInspection
    def register_image(self):
        """ Images only"""
        return self.register_media()

    def register_media(self) -> dict | None:
        """ For images and videos """
        contents = {
            "initializeUploadRequest": {
                "owner": f"urn:li:organization:{self.company_id}",
            }
        }
        url = "https://api.linkedin.com/rest/images?action=initializeUpload"
        response = requests.post(url, headers=self.headers, json=contents)
        data = response.json()
        if response.status_code == 200:  # noqa PLR2004
            print("Media registered successfully!")
            return data
        else:
            logger.error(f"Failed to share post: {data['status']}: {data['code']} {data['message']}")

    @classmethod
    def upload_media(cls, url, file_path, content_type: str = "image/png"):
        """" Upload the file to LinkedInPost """
        if not file_path.exists():
            logger.error(f"File not found: {file_path}")
            return
        headers = {'Authorization': 'Bearer redacted',
                   'Content-type': content_type, 'Slug': file_path.name}
        try:
            with open(file_path, "rb") as f:
                response = requests.post(url, headers=headers, files={'file': (file_path.name, f, content_type)})
                logger.info(f"Uploaded media: {response.status_code}")
                return True
        except Exception as e:
            logger.error(f"Failed to upload media: {e}")

    def post(self, data):
        """ Post a message with optional media attachment to LinkedInPost
         :param data: dict with keys 'post' and 'title'

         LinkedInPost API can be confusing:
         This method follows this: https://learn.microsoft.com/en-us/linkedin/consumer/integrations/self-serve/share-on-linkedin
         """
        # noinspection SpellCheckingInspection
        content = {
            "author": f"urn:li:organization:{self.company_id}",
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {
                        "text": data["post"]
                    },
                    "shareMediaCategory": "ARTICLE",
                    "media": [
                        {
                            "status": "READY",
                            "description": {
                                "text": f"Watch {data['title']}"
                            },
                            "originalUrl": f"https://www.youtube.com/watch?v={data['youtube_video_id']}",
                            "title": {
                                "text": f"📺 Watch the talk {data['title']} on YouTube"
                            }
                        }
                    ]
                }
            },
            "visibility": {
                "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
            }
        }
        url = "https://api.linkedin.com/v2/ugcPosts"
        response = requests.post(url, headers=self.headers, data=json.dumps(content))
        if response.status_code == 201:  # noqa PLR2004
            print("Post shared successfully!")
            return True
        else:
            logger.error(f"Failed to share post: {data['status']}: {data['code']} {data['message']}")

    # TODO requires community API access -> !! this isn ANOTHER LinkedInPost App with different credentials !!!
    def get_person_urn_via_link(self, profile_url):
        url = 'https://api.linkedin.com/v2/people/(url=' + profile_url + ')'
        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json',
            'X-Restli-Protocol-Version': '2.0.0'
        }
        response = requests.get(url, headers=headers)
        data = response.json()
        if response.status_code != 200:  # noqa PLR2004
            logger.error(f"Failed to get person URN: {data['status']}: {data['code']} {data['message']}")
            return

        # Extract the member URN from the search results
        if 'id' in data:
            member_urn = f"urn:li:person:{data['id']}"
            print("Member URN:", member_urn)
            return member_urn
        else:
            print("Member not found")
