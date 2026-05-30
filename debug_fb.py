import os, json, requests
from dotenv import load_dotenv

dotenv_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path, override=True)

token = os.getenv("META_PAGE_ACCESS_TOKEN", "")
app_id = os.getenv("META_APP_ID", "")
app_secret = os.getenv("META_APP_SECRET", "")
page_id = os.getenv("META_PAGE_ID", "")

print(f"META_PAGE_ID: {page_id}")
print(f"META_APP_ID: {app_id}")
print(f"Token starts with: {token[:15]}...")
print(f"Token length: {len(token)}")

if app_id and app_secret and token:
    url = "https://graph.facebook.com/debug_token"
    params = {"input_token": token, "access_token": f"{app_id}|{app_secret}"}
    r = requests.get(url, params=params, timeout=10)
    d = r.json().get("data", {})
    print(f"\n=== TOKEN INFO ===")
    print(f"Type: {d.get('type')}")
    print(f"App ID: {d.get('app_id')}")
    print(f"Is Valid: {d.get('is_valid')}")
    print(f"Scopes: {d.get('scopes')}")

    granter = d.get('granter', {})
    if granter:
        print(f"Granter ID: {granter.get('id')}")
        print(f"Granter Name: {granter.get('name')}")
        if str(granter.get('id')) == str(page_id):
            print("\n>>> CONCLUSION: It's a PAGE TOKEN for your restaurant page")
        else:
            print(f"\n>>> CONCLUSION: It's a USER TOKEN - NOT a Page Token!")
elif token and (not app_id or not app_secret):
    print("Can't debug token - META_APP_ID or META_APP_SECRET is missing")
