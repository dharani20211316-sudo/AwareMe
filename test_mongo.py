import requests

# Flask app running locally on port 10000
url = "http://127.0.0.1:10000/login"

data = {
    "username": "Nethmi",
    "password": "123"  # use the password you set for Nethmi
}

response = requests.post(url, json=data)
print("Status Code:", response.status_code)
print("Response:", response.json())