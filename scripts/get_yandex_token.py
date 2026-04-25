from yandex_music import Client


def on_code(code):
    print(f"Open: {code.verification_url}")
    print(f"Code: {code.user_code}")


client = Client()
token = client.device_auth(on_code=on_code)

print("access_token:", token.access_token)
print("refresh_token:", token.refresh_token)
print("expires_in:", token.expires_in)
