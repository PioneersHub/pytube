import json
from pathlib import Path

import requests
from omegaconf import OmegaConf

from src import logger


class LinkedIn:
    def __init__(self, credentials):
        self.credentials = credentials['LINKED_IN']
        # same for all requests
        self.headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0"
        }

    @property
    def company_id(self) -> str:
        return self.credentials["COMPANY_ID"]

    @property
    def access_token(self) -> str:
        return self.credentials["ACCESS_TOKEN"]

    # noinspection SpellCheckingInspection
    def register_image(self):
        """ Images only"""
        return self.register_media(feed_share="feedshare-image")

    def register_media(self, feed_share) -> dict | None:
        """ For images and videos """
        payload = {
            "registerUploadRequest": {
                "recipes": [
                    f"urn:li:digitalmediaRecipe:{feed_share}"
                ],
                "owner": f"urn:li:organization:{self.company_id}",
                "serviceRelationships": [
                    {
                        "relationshipType": "OWNER",
                        "identifier": "urn:li:userGeneratedContent"
                    }
                ]
            }
        }
        url = "https://api.linkedin.com/v2/assets?action=registerUpload"
        response = requests.post(url, headers=self.headers, json=payload)
        data = response.json()
        if response.status_code == 201:  # noqa PLR2004
            print("Post shared successfully!")
            return data
        else:
            logger.error(f"Failed to share post: {data['status']}: {data['code']} {data['message']}")

    def upload_media(self, url, file_path):
        """" Upload the file to LinkedIn """
        headers = {'Authorization': 'Bearer redacted'}
        with open(file_path, "rb") as f:
            response = requests.put(url, headers=headers, data=f)
            logger.info(f"Upload media: {response.status_code}")
            return response.json()

    def post(self, data, asset_urn: str | None = None):
        """ Post a message with optional media attachment to LinkedIn
         :param data: dict with keys 'post' and 'title'
         :param asset_urn: URN of the media asset as received by LinkedIn after the preceding upload."""
        # noinspection SpellCheckingInspection
        content = {
            "author": f"urn:li:organization:{self.company_id}",
            "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
            "lifecycleState": "PUBLISHED",
            "isReshareDisabledByAuthor": False
        }
        if asset_urn is None:
            # this will create a simple text post
            content["commentary"] = data["post"],
            return

        content["specificContent"] = {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {
                    "text": data["post"]
                },
                "shareMediaCategory": "IMAGE",
                "media": [
                    {
                        "status": "READY",
                        "description": {
                            "text": data["title"]
                        },
                        "media": asset_urn,
                        "title": {
                            "text": "LinkedIn Talent Connect 2021"
                        }
                    }
                ]
            }}

        url = "https://api.linkedin.com/v2/ugcPosts"
        # Make the POST request to share the content
        response = requests.post(url, headers=self.headers, data=json.dumps(content))
        data = response.json()
        if response.status_code == 201:  # noqa PLR2004
            print("Post shared successfully!")
            return data
        else:
            logger.error(f"Failed to share post: {data['status']}: {data['code']} {data['message']}")

    # TODO requires community API acccess -> !! this isn ANOTHER LinkedIn App with different credentials !!!
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


if __name__ == "__main__":
    local_credentials = OmegaConf.load(Path(__file__).parents[1] / "_secret" / "linked_in.yml")
    li = LinkedIn(local_credentials)
    # li.get_person_urn_via_link("https://www.linkedin.com/in/hendorf/")
    li.post("Hello LinkedIn! This is our new Agent speaking, stay tuned for more updates!")
    a = 44
