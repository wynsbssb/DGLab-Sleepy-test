from datetime import datetime, timedelta
import pytz
import json
from data import data

if __name__ == '__main__':
    d = data()
    tz = pytz.timezone('Asia/Shanghai')
    now = datetime.now(tz)
    device_id = 'test-device'

    # create synthetic events: AppA used from now-90min to now-60min, AppB used from now-30min to now
    events = [
        {'time': (now - timedelta(minutes=90)).isoformat(), 'app_name': 'AppA raw', 'app_name_only': 'AppA', 'app_pkg': 'com.example.appa', 'using': True},
        {'time': (now - timedelta(minutes=60)).isoformat(), 'app_name': 'AppA raw', 'app_name_only': 'AppA', 'app_pkg': 'com.example.appa', 'using': False},
        {'time': (now - timedelta(minutes=30)).isoformat(), 'app_name': 'AppB raw', 'app_name_only': 'AppB', 'app_pkg': 'com.example.appb', 'using': True},
    ]

    ah = d.data.setdefault('app_history', {})
    ah[device_id] = events
    d.save()

    details = d.get_app_usage_details(device_id, hours=3)
    print(json.dumps(details, indent=2, ensure_ascii=False))
