import requests

# TODO

# Replace the below with your LinkedIn app credentials
CLIENT_ID = 'your_client_id'
CLIENT_SECRET = 'your_client_secret'
REDIRECT_URI = 'your_redirect_uri'
AUTHORIZATION_CODE = 'authorization_code_from_redirect'

# Exchange authorization code for access token
response = requests.post('https://www.linkedin.com/oauth/v2/accessToken', data={
    'grant_type': 'authorization_code',
    'code': AUTHORIZATION_CODE,
    'redirect_uri': REDIRECT_URI,
    'client_id': CLIENT_ID,
    'client_secret': CLIENT_SECRET,
})

data = response.json()
ACCESS_TOKEN = data['access_token']
print("Access Token:", ACCESS_TOKEN)

###########

# Replace the below with the LinkedIn profile URL you want to search for
profile_url = "https://www.linkedin.com/in/profile-url"

# LinkedIn API endpoint for search
url = 'https://api.linkedin.com/v2/people/(url=' + profile_url + ')'

# Headers for the request
headers = {
    'Authorization': f'Bearer {ACCESS_TOKEN}',
    'Content-Type': 'application/json',
    'X-Restli-Protocol-Version': '2.0.0'
}

# Make the GET request to search for the user
response = requests.get(url, headers=headers)
data = response.json()

# Extract the member URN from the search results
if 'id' in data:
    member_urn = f"urn:li:person:{data['id']}"
    print("Member URN:", member_urn)
else:
    print("Member not found")
