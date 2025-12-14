# coding: utf-8

import os
import pytz
import json
import json5
import threading
from time import sleep
from datetime import datetime, timedelta

import utils as u
import env as env
from setting import metrics_list


class data:
    '''
    data 类，存储当前/设备状态
    可用 `.data['xxx']` 直接调取数据 (加载后) *(?)*
    '''
    data: dict
    preload_data: dict
    data_check_interval: int = 60

    def __init__(self):
        with open(u.get_path('data.template.jsonc'), 'r', encoding='utf-8') as file:
            self.preload_data = json5.load(file, encoding='utf-8')
        if os.path.exists(u.get_path('data.json')):
            try:
                self.load()
            except Exception as e:
                u.warning(f'Error when loading data: {e}, try re-create')
                os.remove(u.get_path('data.json'))
                self.data = self.preload_data
                self.save()
                self.load()
        else:
            u.info('Could not find data.json, creating.')
            try:
                self.data = self.preload_data
                self.save()
            except Exception as e:
                u.exception(f'Create data.json failed: {e}')

    # --- Storage functions

    def load(self, ret: bool = False, preload: dict = {}, error_count: int = 5) -> dict:
        '''
        加载状态

        :param ret: 是否返回加载后的 dict (为否则设置 self.data)
        :param preload: 将会将 data.json 的内容追加到此后
        '''
        if not preload:
            preload = self.preload_data
        attempts = error_count

        while attempts > 0:
            try:
                if not os.path.exists(u.get_path('data.json')):
                    u.warning('data.json not exist, try re-create')
                    self.data = self.preload_data
                    self.save()
                with open(u.get_path('data.json'), 'r', encoding='utf-8') as file:
                    Data = json.load(file)
                    DATA: dict = {**preload, **Data}
                    if ret:
                        return DATA
                    else:
                        self.data = DATA
                break  # 成功加载数据后跳出循环
            except Exception as e:
                attempts -= 1
                if attempts > 0:
                    u.warning(f'Load data error: {e}, retrying ({attempts} attempts left)')
                else:
                    u.error(f'Load data error: {e}, reached max retry count!')
                    raise

    def save(self):
        '''
        保存配置
        '''
        try:
            with open(u.get_path('data.json'), 'w', encoding='utf-8') as file:
                json.dump(self.data, file, indent=4, ensure_ascii=False)
        except Exception as e:
            u.error(f'Failed to save data.json: {e}')

    def dset(self, name, value):
        '''
        设置一个值
        '''
        self.data[name] = value

    def dget(self, name, default=None):
        '''
        读取一个值
        '''
        try:
            gotdata = self.data[name]
        except KeyError:
            gotdata = default
        return gotdata

    # --- Metrics

    def metrics_init(self):
        try:
            self.data['metrics']
        except KeyError:
            u.debug('[metrics] Metrics data init')
            self.data['metrics'] = {
                'today_is': '',
                'month_is': '',
                'year_is': '',
                'today': {},
                'month': {},
                'year': {},
                'total': {}
            }
            self.record_metrics()

    def get_metrics_resp(self, json_only: bool = False):
        now = datetime.now(pytz.timezone(env.main.timezone))
        '''
        if json_only:
            # 仅用于调试
            return {
                'time': f'{now}',
                'timezone': env.main.timezone,
                'today_is': self.data['metrics']['today_is'],
                'month_is': self.data['metrics']['month_is'],
                'year_is': self.data['metrics']['year_is'],
                'today': self.data['metrics']['today'],
                'month': self.data['metrics']['month'],
                'year': self.data['metrics']['year'],
                'total': self.data['metrics']['total']
            }
        else:
        '''
        return u.format_dict({
            'time': f'{now}',
            'timezone': env.main.timezone,
            'today_is': self.data['metrics']['today_is'],
            'month_is': self.data['metrics']['month_is'],
            'year_is': self.data['metrics']['year_is'],
            'today': self.data['metrics']['today'],
            'month': self.data['metrics']['month'],
            'year': self.data['metrics']['year'],
            'total': self.data['metrics']['total']
        })

    def check_metrics_time(self) -> None:
        '''
        跨 日 / 月 / 年 检测
        '''
        if not env.util.metrics:
            return

        # get time now
        now = datetime.now(pytz.timezone(env.main.timezone))
        year_is = str(now.year)
        month_is = f'{now.year}-{now.month}'
        today_is = f'{now.year}-{now.month}-{now.day}'

        # - check time
        if self.data['metrics']['today_is'] != today_is:
            u.debug(f'[metrics] today_is changed: {self.data["metrics"]["today_is"]} -> {today_is}')
            self.data['metrics']['today_is'] = today_is
            self.data['metrics']['today'] = {}
        # this month
        if self.data['metrics']['month_is'] != month_is:
            u.debug(f'[metrics] month_is changed: {self.data["metrics"]["month_is"]} -> {month_is}')
            self.data['metrics']['month_is'] = month_is
            self.data['metrics']['month'] = {}
        # this year
        if self.data['metrics']['year_is'] != year_is:
            u.debug(f'[metrics] year_is changed: {self.data["metrics"]["year_is"]} -> {year_is}')
            self.data['metrics']['year_is'] = year_is
            self.data['metrics']['year'] = {}

    def record_metrics(self, path: str = None) -> None:
        '''
        记录调用

        :param path: 访问的路径
        '''

        # check metrics list
        if not path in metrics_list:
            return

        self.check_metrics_time()

        # - record num
        today = self.data['metrics'].setdefault('today', {})
        month = self.data['metrics'].setdefault('month', {})
        year = self.data['metrics'].setdefault('year', {})
        total = self.data['metrics'].setdefault('total', {})

        today[path] = today.get(path, 0) + 1
        month[path] = month.get(path, 0) + 1
        year[path] = year.get(path, 0) + 1
        total[path] = total.get(path, 0) + 1

    # --- App usage history

    def record_app_usage(self, device_id: str, app_name: str, using: bool, app_pkg: str = None, app_name_only: str = None) -> None:
        '''
        记录设备上报的 app 使用事件（时间点事件）
        :param device_id: 设备 id
        :param app_name: 上报的应用名（原始）
        :param using: 是否正在使用
        :param app_pkg: (可选) 应用包名或标识
        :param app_name_only: (可选) 清洗后的应用名（优先使用）
        '''
        try:
            now = datetime.now(pytz.timezone(env.main.timezone)).isoformat()
        except Exception:
            now = datetime.utcnow().isoformat()

        # 规范化应用名：优先使用传入的 app_name_only，再尝试从原始 app_name 中提取
        def normalize(name):
            if not name:
                return ''
            # 常见 magisk 上报格式包含 "应用:" 或 "应用："
            import re
            m = re.search(r'[\n\r]*应用[:：]\s*(.+)$', name)
            if m:
                return m.group(1).strip()
            # 若包含换行，尝试取最后一行
            if '\n' in name:
                last = name.split('\n')[-1].strip()
                return last
            return name.strip()

        clean_name = (app_name_only or '').strip() or normalize(app_name)

        ah = self.data.setdefault('app_history', {})
        lst = ah.setdefault(device_id, [])
        lst.append({'time': now, 'app_name': app_name or '', 'app_name_only': clean_name, 'app_pkg': app_pkg or '', 'using': bool(using)})

        # 清理旧数据，仅保留最近 48 小时的记录以防增长过大
        try:
            cutoff = datetime.now(pytz.timezone(env.main.timezone))
        except Exception:
            from datetime import timezone
            cutoff = datetime.now(timezone.utc)
        cutoff = cutoff.timestamp() - 48 * 3600
        newlst = []
        for e in lst:
            try:
                t = datetime.fromisoformat(e['time']).timestamp()
                if t >= cutoff:
                    newlst.append(e)
            except Exception:
                # 如果解析失败，保守保留
                newlst.append(e)
        ah[device_id] = newlst

    def get_app_usage(self, device_id: str, hours: int = 24) -> list:
        '''
        聚合返回过去 `hours` 小时内每小时的 app 事件计数和排名。
        返回格式: [{ 'hour': 'YYYY-MM-DD HH:00', 'counts': {app: n, ...}, 'top_app': app, 'top_count': n }, ...]
        '''
        try:
            now = datetime.now(pytz.timezone(env.main.timezone))
        except Exception:
            from datetime import timezone
            now = datetime.now(timezone.utc)

        start_ts = (now.timestamp() - hours * 3600)
        raw = self.data.get('app_history', {}).get(device_id, [])
        buckets = {}
        for e in raw:
            try:
                t = datetime.fromisoformat(e['time'])
            except Exception:
                continue
            ts = t.timestamp()
            if ts < start_ts:
                continue
            # bucket by hour start
            hour_dt = t.replace(minute=0, second=0, microsecond=0)
            key = hour_dt.strftime('%Y-%m-%d %H:00')
            counts = buckets.setdefault(key, {})
            app = e.get('app_name_only') or e.get('app_name') or '[unknown]'
            counts[app] = counts.get(app, 0) + 1

        # Build result array from start->now (hours entries)
        res = []
        for i in range(hours, 0, -1):
            hour_dt = (now - timedelta(hours=i-1)).replace(minute=0, second=0, microsecond=0)
            key = hour_dt.strftime('%Y-%m-%d %H:00')
            counts = buckets.get(key, {})
            if counts:
                # find top
                top_app = max(counts.items(), key=lambda x: x[1])[0]
                top_count = counts[top_app]
            else:
                top_app = None
                top_count = 0
            res.append({'hour': key, 'counts': counts, 'top_app': top_app, 'top_count': top_count})
        return res

    def get_app_usage_details(self, device_id: str, hours: int = 24) -> dict:
        '''
        返回更详细的使用统计：按小时桶的聚合（同 get_app_usage），以及总用时统计、最常用应用、当前运行应用和当前运行时长。
        '''
        try:
            now = datetime.now(pytz.timezone(env.main.timezone))
        except Exception:
            from datetime import timezone
            now = datetime.now(timezone.utc)
        start_ts = now.timestamp() - hours * 3600

        raw = self.data.get('app_history', {}).get(device_id, [])
        # sort by time ascending
        events = []
        for e in raw:
            try:
                t = datetime.fromisoformat(e['time']).timestamp()
            except Exception:
                continue
            events.append({'ts': t, 'app': e.get('app_name_only') or e.get('app_name') or '[unknown]', 'using': bool(e.get('using', False))})
        events.sort(key=lambda x: x['ts'])

        totals = {}
        # iterate, create sessions from event[i] -> event[i+1]
        for i, ev in enumerate(events):
            start = ev['ts']
            end = events[i+1]['ts'] if i+1 < len(events) else now.timestamp()
            if end <= start:
                continue
            # clip to window
            if end < start_ts:
                continue
            seg_start = max(start, start_ts)
            seg_end = end
            duration = seg_end - seg_start
            if ev['using']:
                totals[ev['app']] = totals.get(ev['app'], 0) + duration

        # convert totals to readable seconds and find top
        if totals:
            top_app = max(totals.items(), key=lambda x: x[1])[0]
            top_seconds = int(totals[top_app])
        else:
            top_app = None
            top_seconds = 0

        # current app and running time
        current_app = None
        current_runtime = 0
        # check if device currently marked using and has events
        device_status = self.data.get('device_status', {}).get(device_id, {})
        if device_status and device_status.get('using'):
            current_app = device_status.get('app_name') or device_status.get('show_name')
            # find last 'using' event for same app
            last_using_ts = None
            for ev in reversed(events):
                if ev['using'] and ev['app'] in (device_status.get('app_name') or device_status.get('show_name') or ev['app']):
                    last_using_ts = ev['ts']
                    break
            if last_using_ts:
                current_runtime = int(now.timestamp() - last_using_ts)

        return {
            'hours': hours,
            'totals_seconds': {k: int(v) for k, v in totals.items()},
            'top_app': top_app,
            'top_seconds': top_seconds,
            'current_app': current_app,
            'current_runtime': current_runtime,
            'hourly': self.get_app_usage(device_id, hours)
        }

    def get_app_usage_aggregate(self, hours: int = 24) -> dict:
        """
        聚合所有设备的使用统计，返回与 `get_app_usage_details` 相同的结构，但基于所有设备的事件合并计算。
        """
        # collect all events across devices
        all_raw = []
        for device_id, lst in self.data.get('app_history', {}).items():
            for e in lst:
                all_raw.append(e)

        # temporarily store and sort events similar to get_app_usage_details
        try:
            now = datetime.now(pytz.timezone(env.main.timezone))
        except Exception:
            from datetime import timezone
            now = datetime.now(timezone.utc)
        start_ts = now.timestamp() - hours * 3600

        events = []
        for e in all_raw:
            try:
                t = datetime.fromisoformat(e['time']).timestamp()
            except Exception:
                continue
            events.append({'ts': t, 'app': e.get('app_name_only') or e.get('app_name') or '[unknown]', 'using': bool(e.get('using', False))})
        events.sort(key=lambda x: x['ts'])

        totals = {}
        for i, ev in enumerate(events):
            start = ev['ts']
            end = events[i+1]['ts'] if i+1 < len(events) else now.timestamp()
            if end <= start:
                continue
            if end < start_ts:
                continue
            seg_start = max(start, start_ts)
            seg_end = end
            duration = seg_end - seg_start
            if ev['using']:
                totals[ev['app']] = totals.get(ev['app'], 0) + duration

        if totals:
            top_app = max(totals.items(), key=lambda x: x[1])[0]
            top_seconds = int(totals[top_app])
        else:
            top_app = None
            top_seconds = 0

        # current app - for aggregate we don't define a single current app, leave None
        current_app = None
        current_runtime = 0

        # hourly buckets: merge per-hour counts across devices
        buckets = {}
        for e in all_raw:
            try:
                t = datetime.fromisoformat(e['time'])
            except Exception:
                continue
            ts = t.timestamp()
            if ts < start_ts:
                continue
            hour_dt = t.replace(minute=0, second=0, microsecond=0)
            key = hour_dt.strftime('%Y-%m-%d %H:00')
            counts = buckets.setdefault(key, {})
            app = e.get('app_name_only') or e.get('app_name') or '[unknown]'
            counts[app] = counts.get(app, 0) + 1

        # build hourly array
        res = []
        for i in range(hours, 0, -1):
            hour_dt = (now - timedelta(hours=i-1)).replace(minute=0, second=0, microsecond=0)
            key = hour_dt.strftime('%Y-%m-%d %H:00')
            counts = buckets.get(key, {})
            if counts:
                top_app_h = max(counts.items(), key=lambda x: x[1])[0]
                top_count = counts[top_app_h]
            else:
                top_app_h = None
                top_count = 0
            res.append({'hour': key, 'counts': counts, 'top_app': top_app_h, 'top_count': top_count})

        return {
            'hours': hours,
            'totals_seconds': {k: int(v) for k, v in totals.items()},
            'top_app': top_app,
            'top_seconds': top_seconds,
            'current_app': current_app,
            'current_runtime': current_runtime,
            'hourly': res
        }

    # --- Timer check - save data

    def start_timer_check(self, data_check_interval: int = 60):
        '''
        使用 threading 启动下面的 `timer_check()`

        :param data_check_interval: 检查间隔 *(秒)*
        '''
        self.data_check_interval = data_check_interval
        self.timer_thread = threading.Thread(target=self.timer_check, daemon=True)
        self.timer_thread.start()

    def check_device_status(self, trigged_by_timer: bool = False):
        '''
        按情况自动切换状态

        :param trigged_by_timer: 是否由计时器触发 (为 True 将不记录日志)
        '''
        device_status: dict = self.data.get('device_status', {})
        current_status: int = self.data.get('status', 0)  # 获取当前 status，默认为 0
        auto_switch_enabled: bool = env.util.auto_switch_status

        # 检查是否启用自动切换功能，并且当前 status 为 0 或 1
        last_status = self.data['status']
        if auto_switch_enabled:
            if current_status in [0, 1]:
                any_using = any(device.get('using', False) for device in device_status.values())
                if any_using:
                    self.data['status'] = 0
                else:
                    self.data['status'] = 1
                if last_status != self.data['status']:
                    u.debug(f'[check_device_status] 已自动切换状态 ({last_status} -> {self.data["status"]}).')
                elif not trigged_by_timer:
                    u.debug(f'[check_device_status] 当前状态已为 {current_status}, 无需切换.')
            elif not trigged_by_timer:
                u.debug(f'[check_device_status] 当前状态为 {current_status}, 不适用自动切换.')

    def timer_check(self):
        '''
        定时检查更改并自动保存
        * 根据 `data_check_interval` 参数调整 sleep() 的秒数
        * 需要使用 threading 启动新线程运行
        '''
        u.info(f'[timer_check] started, interval: {self.data_check_interval} seconds.')
        while True:
            sleep(self.data_check_interval)
            try:
                self.check_metrics_time()  # 检测是否跨日
                self.check_device_status(trigged_by_timer=True)  # 检测设备状态并更新 status
                file_data = self.load(ret=True)
                if file_data != self.data:
                    self.save()
            except Exception as e:
                u.warning(f'[timer_check] Error: {e}, retrying.')

    # --- check device heartbeat
    # TODO
