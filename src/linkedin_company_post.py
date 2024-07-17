from pathlib import Path

import requests
import json

from omegaconf import OmegaConf


class LinkedIn:
    def __init__(self, credentials):
        self.credentials = credentials

    @property
    def company_id(self):
        return self.credentials["COMPANY_ID"]

    @property
    def access_token(self):
        return self.credentials["ACCESS_TOKEN"]

    def post(self, text):
        content = {
            "author": f"urn:li:organization:{self.company_id}",
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {
                        "text": text
                    },
                    "shareMediaCategory": "NONE"
                }
            },
            "visibility": {
                "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
            }
        }

        # LinkedIn API endpoint for sharing posts
        url = f"https://api.linkedin.com/v2/ugcPosts"

        # Headers for the request
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0"
        }

        # Make the POST request to share the content
        response = requests.post(url, headers=headers, data=json.dumps(content))

        # Check the response
        if response.status_code == 201:
            print("Post shared successfully!")
        else:
            print(f"Failed to share post: {response.status_code}")
            print(response.json())

    def get_person_urn_via_link(self, profile_url):
        url = 'https://api.linkedin.com/v2/people/(url=' + profile_url + ')'
        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json',
            'X-Restli-Protocol-Version': '2.0.0'
        }
        response = requests.get(url, headers=headers)
        data = response.json()
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
