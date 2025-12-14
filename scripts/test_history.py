from datetime import datetime, timedelta
try:
    import pytz
except Exception:
    pytz = None
import json
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
# inject a minimal env module to avoid dependency on python-dotenv for tests
if 'env' not in sys.modules:
    from types import SimpleNamespace
    main = SimpleNamespace(timezone='Asia/Shanghai', checkdata_interval=60, debug=False, https_enabled=False, host='0.0.0.0', port=9012, ssl_cert='', ssl_key='')
    util = SimpleNamespace(metrics=False, auto_switch_status=False)
    page = SimpleNamespace()
    status = SimpleNamespace()
    sys.modules['env'] = SimpleNamespace(main=main, util=util, page=page, status=status)
# stub `setting` if missing (avoid json5 dependency for tests)
if 'setting' not in sys.modules:
    sys.modules['setting'] = SimpleNamespace(metrics_list={})
from data import data

if __name__ == '__main__':
    d = data()
    try:
        tz = pytz.timezone('Asia/Shanghai')
        now = datetime.now(tz)
    except Exception:
        now = datetime.now()
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
    print('--- single device details ---')
    print(json.dumps(details, indent=2, ensure_ascii=False))

    # add another device and test aggregate
    other = 'test-device-2'
    events2 = [
        {'time': (now - timedelta(minutes=20)).isoformat(), 'app_name': 'AppC raw', 'app_name_only': 'AppC', 'app_pkg': 'com.example.appc', 'using': True},
        {'time': (now - timedelta(minutes=10)).isoformat(), 'app_name': 'AppC raw', 'app_name_only': 'AppC', 'app_pkg': 'com.example.appc', 'using': False},
    ]
    ah[other] = events2
    d.save()

    agg = d.get_app_usage_aggregate(hours=3)
    print('\n--- aggregate details ---')
    print(json.dumps(agg, indent=2, ensure_ascii=False))

    # extra: test get_app_usage_details_v2 and hourly breakdown
    v2 = d.get_app_usage_details_v2(device_id, hours=3)
    print('\n--- details v2 ---')
    print(json.dumps(v2, indent=2, ensure_ascii=False))

    # hour breakdown for aggregate and device
    hour_key = (now - timedelta(hours=1)).replace(minute=0, second=0, microsecond=0).strftime('%Y-%m-%d %H:00')
    print('\nHour:', hour_key)
    print('\n- device hour breakdown:')
    print(json.dumps(d.get_app_hour_breakdown(device_id, hour_key), indent=2, ensure_ascii=False))
    print('\n- aggregate hour breakdown:')
    print(json.dumps(d.get_app_hour_breakdown('', hour_key), indent=2, ensure_ascii=False))

