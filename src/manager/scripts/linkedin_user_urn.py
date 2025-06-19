import uuid
import webbrowser

import requests

# Replace with your LinkedIn App credentials
CLIENT_ID = "784pnik1rmuv6d"
CLIENT_SECRET = "WPL_AP1.9sNcVFJALGDlcbbK.NNAu3A=="
REDIRECT_URI = "http://localhost:8000"

# Scopes required for posting and profile access
SCOPES = "w_member_social"
STATE = str(uuid.uuid4())  # Generates a random state value

# Scopes requested: OpenID + Profile + Email + Posting permission
SCOPES = "openid profile email r_liteprofile r_emailaddress w_member_social"

# LinkedIn OAuth URLs
AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
USERINFO_URL = "https://api.linkedin.com/v2/userinfo"
POST_URL = "https://api.linkedin.com/v2/ugcPosts"


# Step 1: Redirect user to LinkedIn for authentication
def get_authorization_code():
    auth_link = (
        f"{AUTH_URL}?response_type=code&client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}&scope={SCOPES}&state={STATE}"
    )
    print("\n[STEP 1] Redirecting user to LinkedIn authentication page...")
    print(f"Navigate to this URL and authorize the application:\n{auth_link}")
    webbrowser.open(auth_link)  # Opens browser for user login
    auth_code = input("\nEnter the authorization code from the LinkedIn redirect URL: ").strip()
    return auth_code


# Step 2: Exchange authorization code for access token
def get_access_token(auth_code):
    data = {
        "grant_type": "authorization_code",
        "code": auth_code,
        "redirect_uri": REDIRECT_URI,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    }
    print("\n[STEP 2] Requesting access token from LinkedIn...")
    response = requests.post(TOKEN_URL, data=data)
    if response.status_code == 200:
        token_data = response.json()
        print("✅ Access token obtained successfully.")
        return token_data["access_token"]
    else:
        print(f"❌ Failed to get access token: {response.status_code} - {response.text}")
        return None


# Step 3: Retrieve user profile and email
def get_user_info(access_token):
    headers = {"Authorization": f"Bearer {access_token}"}
    print("\n[STEP 3] Fetching user profile and email from LinkedIn...")
    response = requests.get(USERINFO_URL, headers=headers)
    if response.status_code == 200:
        user_info = response.json()
        print("✅ User information retrieved successfully:")
        print(user_info)
        return user_info
    else:
        print(f"❌ Failed to fetch user info: {response.status_code} - {response.text}")
        return None


# Step 4: Post on LinkedIn
def post_on_linkedin(access_token, author_urn, message):
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "X-RestLi-Protocol-Version": "2.0.0",
    }
    post_data = {
        "author": author_urn,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": message},
                "shareMediaCategory": "NONE",
            }
        },
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
    }
    print("\n[STEP 4] Attempting to post on LinkedIn...")
    response = requests.post(POST_URL, headers=headers, json=post_data)
    if response.status_code == 201:
        print("✅ Post created successfully on LinkedIn.")
        print(response.json())
    else:
        print(f"❌ Failed to create post: {response.status_code} - {response.text}")


# Main execution flow
if __name__ == "__main__":
    print("\n🔹 LinkedIn OAuth 2.0 Authentication Script 🔹")
    auth_code = get_authorization_code()

    if auth_code:
        access_token = get_access_token(auth_code)

        if access_token:
            user_info = get_user_info(access_token)

            if user_info:
                author_urn = user_info.get("sub")  # Extracting LinkedIn ID for posting
                if author_urn:
                    print("\nDo you want to post on LinkedIn?")
                    post_decision = input("Type 'yes' to post a message, or press Enter to skip: ").strip().lower()
                    if post_decision == "yes":
                        post_message = input("Enter the message you want to post on LinkedIn: ").strip()
                        post_on_linkedin(access_token, author_urn, post_message)

    print("\n🔹 Script Execution Completed 🔹")
