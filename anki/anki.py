import json
from settings import settings
import urllib.request

# Anki Integration Helper
def ankiconnect_request(action, **params):
    url = settings.get('anki_url', 'http://127.0.0.1:8765')
    request_data = json.dumps({
        "action": action,
        "version": 6,
        "params": params
    }).encode('utf-8')
    request = urllib.request.Request(url, request_data)
    response = json.loads(urllib.request.urlopen(request).read())
    return response['result']
