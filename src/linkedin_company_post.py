from pathlib import Path

import requests
import json

from omegaconf import OmegaConf

from src import logger


class LinkedIn:
    def __init__(self, credentials):
        self.credentials = credentials['LINKED_IN']

    @property
    def company_id(self) -> str:
        return self.credentials["COMPANY_ID"]

    @property
    def access_token(self) -> str:
        return self.credentials["ACCESS_TOKEN"]

    def post(self, text) -> dict | None:
        # content = {
        #     "author": f"urn:li:organization:{self.company_id}",
        #     "lifecycleState": "PUBLISHED",
        #     "specificContent": {
        #         "com.linkedin.ugc.ShareContent": {
        #             "shareCommentary": {
        #                 "text": text
        #             },
        #             "shareMediaCategory": "NONE"
        #         }
        #     },
        #     "visibility": {
        #         "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
        #     }
        # }
        content = {
            "author": f"urn:li:organization:{self.company_id}",
            "commentary": text,
            "visibility": "PUBLIC",
            "distribution": {
                "feedDistribution": "MAIN_FEED",
                "targetEntities": [],
                "thirdPartyDistributionChannels": []
            },
            "lifecycleState": "PUBLISHED",
            "isReshareDisabledByAuthor": False
        }

        # LinkedIn API endpoint for sharing posts
        # url = f"https://api.linkedin.com/v2/ugcPosts"
        url = "https://api.linkedin.com/v2/posts"

        # Headers for the request
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0"
        }

        # Make the POST request to share the content
        response = requests.post(url, headers=headers, data=json.dumps(content))

        # Check the response
        data = response.json()
        if response.status_code == 201:
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
        if response.status_code != 200:
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
