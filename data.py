# coding: utf-8

import os
import re
import shutil
try:
    import pytz
except Exception:
    pytz = None
import json
try:
    import json5
except Exception:
    json5 = json
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
            # json5 may be a fallback to json; json.load doesn't accept encoding param
            try:
                self.preload_data = json5.load(file)
            except Exception:
                # If json5 not available or parsing fails (json5 may support comments), fall back to minimal defaults
                file.seek(0)
                try:
                    self.preload_data = json.loads(file.read())
                except Exception:
                    self.preload_data = {}

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
                    content = file.read()
                    if not content.strip():
                        raise ValueError('data.json is empty, possible interrupted write')
                    Data = json.loads(content)
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
                    backup_path = u.get_path('data.json.bak')
                    if os.path.exists(backup_path):
                        try:
                            with open(backup_path, 'r', encoding='utf-8') as file:
                                backup_content = file.read()
                                if not backup_content.strip():
                                    raise ValueError('backup file is empty')
                                Data = json.loads(backup_content)
                                DATA = {**preload, **Data}
                                if ret:
                                    return DATA
                                else:
                                    self.data = DATA
                                    # 用备份文件修复损坏的 data.json
                                    self.save()
                                break
                        except Exception as backup_error:
                            u.error(f'Load data error: {e}, fallback backup failed: {backup_error}')
                    u.error(f'Load data error: {e}, reached max retry count!')
                    raise

    def save(self):
        '''
        保存配置
        '''
        try:
            data_path = u.get_path('data.json')
            tmp_path = f"{data_path}.tmp"
            backup_path = f"{data_path}.bak"

            # 生成备份，避免写入被中断导致文件为空
            if os.path.exists(data_path):
                try:
                    shutil.copy2(data_path, backup_path)
                except Exception as e:
                    u.warning(f'Failed to backup data.json: {e}')

            with open(tmp_path, 'w', encoding='utf-8') as file:
                json.dump(self.data, file, indent=4, ensure_ascii=False)
                file.flush()
                os.fsync(file.fileno())

            os.replace(tmp_path, data_path)
        except Exception as e:
            u.error(f'Failed to save data.json: {e}')
            # 确保临时文件不会残留
            try:
                if 'tmp_path' in locals() and os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass

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

    def _safe_parse_ts(self, value):
        try:
            dt = datetime.fromisoformat(value)
            return dt.timestamp()
        except Exception:
            return None

    def _extract_heart_rate(self, text: str):
        if not text:
            return None
        m = re.search(r'(-?\d+(?:\.\d+)?)\s*bpm$', str(text).strip(), re.IGNORECASE)
        if not m:
            return None
        try:
            return float(m.group(1))
        except Exception:
            return None

    # --- Time helpers

    def _calc_time_window(self, hours: int = 24):
        '''
        计算统计窗口，针对 24 小时窗口使用服务器当日 00:00-24:00 的时间范围。
        返回 (start_dt, end_dt, now_dt)
        '''
        try:
            tz = pytz.timezone(env.main.timezone)
        except Exception:
            tz = None

        now_dt = datetime.now(tz) if tz else datetime.utcnow()

        if hours == 24:
            start_dt = now_dt.replace(hour=0, minute=0, second=0, microsecond=0)
            end_dt = start_dt + timedelta(hours=24)
        else:
            start_dt = now_dt - timedelta(hours=hours)
            end_dt = now_dt

        # 防止异常情况导致 end 早于 start
        if end_dt < start_dt:
            end_dt = start_dt

        return start_dt, end_dt, now_dt

    # --- Heart rate helpers

    def record_heart_rate(self, device_id: str, heart_rate: float, when: datetime = None):
        '''记录心率数据，默认保留最近 48 小时'''
        try:
            tz = pytz.timezone(env.main.timezone)
        except Exception:
            tz = None
        now_dt = when or (datetime.now(tz) if tz else datetime.utcnow())

        hist = self.data.setdefault('heart_history', {})
        lst = hist.setdefault(device_id, [])
        lst.append({'time': now_dt.isoformat(), 'value': float(heart_rate)})

        cutoff = (now_dt - timedelta(hours=48)).timestamp()
        filtered = []
        for e in lst:
            ts = self._safe_parse_ts(e.get('time'))
            if ts is None:
                continue
            if ts >= cutoff:
                filtered.append(e)
        hist[device_id] = filtered
        try:
            self.save()
        except Exception as e:
            u.warning(f'[record_heart_rate] failed to save: {e}')

    def get_heart_rate_details(self, device_id: str, hours: int = 24) -> dict:
        start_dt, end_dt, now_dt = self._calc_time_window(hours)
        start_ts = start_dt.timestamp()
        end_ts = end_dt.timestamp()

        hist = self.data.get('heart_history', {}).get(device_id, [])
        samples = []
        latest = None
        for e in hist:
            ts = self._safe_parse_ts(e.get('time'))
            if ts is None:
                continue
            if ts < start_ts or ts > end_ts:
                continue
            try:
                val = float(e.get('value'))
            except Exception:
                continue
            samples.append({'time': ts, 'value': val})
            if latest is None or ts > latest['time']:
                latest = {'time': ts, 'value': val}

        samples.sort(key=lambda x: x['time'])
        try:
            tz = pytz.timezone(env.main.timezone)
        except Exception:
            tz = None

        def format_ts(ts):
            if tz:
                return datetime.fromtimestamp(ts, tz).isoformat()
            return datetime.fromtimestamp(ts).isoformat()

        return {
            'current': (int(latest['value']) if latest else None),
            'history': [{'time': format_ts(s['time']), 'value': s['value']} for s in samples],
            'window_start': format_ts(start_ts),
            'window_end': format_ts(end_ts)
        }

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

        heart_val = self._extract_heart_rate(clean_name or app_name)
        if heart_val is not None:
            self.record_heart_rate(device_id, heart_val, when=datetime.fromisoformat(now))

        # 立即持久化，避免进程异常退出导致事件丢失
        try:
            self.save()
        except Exception as e:
            u.warning(f'[record_app_usage] failed to save: {e}')

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
        start_dt, end_dt, now = self._calc_time_window(hours)
        start_ts = start_dt.timestamp()
        end_ts = end_dt.timestamp()
        raw = self.data.get('app_history', {}).get(device_id, [])
        buckets = {}
        for e in raw:
            try:
                t = datetime.fromisoformat(e['time'])
            except Exception:
                continue
            ts = t.timestamp()
            if ts < start_ts or ts > end_ts:
                continue
            # bucket by hour start
            hour_dt = t.replace(minute=0, second=0, microsecond=0)
            key = hour_dt.strftime('%Y-%m-%d %H:00')
            counts = buckets.setdefault(key, {})
            app = e.get('app_name_only') or e.get('app_name') or '[unknown]'
            counts[app] = counts.get(app, 0) + 1

        # Build result array from start->now (hours entries)
        res = []
        cur = start_dt
        while cur < end_dt:
            hour_dt = cur.replace(minute=0, second=0, microsecond=0)
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
            cur = hour_dt + timedelta(hours=1)
        return res

    def get_app_usage_details(self, device_id: str, hours: int = 24) -> dict:
        '''
        返回更详细的使用统计：按小时桶的聚合（同 get_app_usage），以及总用时统计、最常用应用、当前运行应用和当前运行时长。
        '''
        start_dt, end_dt, now = self._calc_time_window(hours)
        start_ts = start_dt.timestamp()
        end_ts = end_dt.timestamp()

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
            end = events[i+1]['ts'] if i+1 < len(events) else min(now.timestamp(), end_ts)
            if end <= start:
                continue
            # clip to window
            if end < start_ts or start > end_ts:
                continue
            seg_start = max(start, start_ts)
            seg_end = min(end, end_ts)
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

        # NOTE: the function originally returned above. We keep compatibility by returning above, but
        # to provide richer data (per-app stats and per-hour seconds), add a wrapper function below.

    def get_app_usage_details_v2(self, device_id: str, hours: int = 24) -> dict:
        """
        更丰富的使用详情：除了 `get_app_usage_details` 的内容之外，额外返回：
        - per_app: 每个应用的总时长、启动次数、平均单次时长、最后使用时间
        - hourly_seconds: 每小时的总使用秒数（用于柱状图高度）
        - hourly_breakdown(app/sec) 由 `get_app_hour_breakdown` 获取
        """
        base = self.get_app_usage_details(device_id, hours)

        # 重新计算更详细的 per-app 数据
        start_dt, end_dt, now = self._calc_time_window(hours)
        start_ts = start_dt.timestamp()
        end_ts = end_dt.timestamp()

        raw = self.data.get('app_history', {}).get(device_id, [])
        events = []
        for e in raw:
            try:
                t = datetime.fromisoformat(e['time']).timestamp()
            except Exception:
                continue
            if t < start_ts:
                continue
            events.append({'ts': t, 'app': e.get('app_name_only') or e.get('app_name') or '[unknown]', 'using': bool(e.get('using', False))})
        events.sort(key=lambda x: x['ts'])

        per_app = {}
        last_seen = {}
        launches = {}
        sessions = {}

        for i, ev in enumerate(events):
            app = ev['app']
            start = ev['ts']
            end = events[i+1]['ts'] if i+1 < len(events) else min(now.timestamp(), end_ts)
            if end <= start:
                continue
            # update last seen
            last_seen[app] = max(last_seen.get(app, 0), int(ev['ts']))
            # count launches: when an event is using and previous event is not using or previous app differs
            prev = events[i-1] if i-1 >= 0 else None
            if ev['using']:
                is_new_launch = False
                if prev is None:
                    is_new_launch = True
                else:
                    if (not prev['using']) or (prev['app'] != app):
                        is_new_launch = True
                if is_new_launch:
                    launches[app] = launches.get(app, 0) + 1
                # add duration clipped to window
                seg_start = max(start, start_ts)
                seg_end = end
                duration = seg_end - seg_start
                sessions[app] = sessions.get(app, 0) + duration

        for app, sec in sessions.items():
            per_app[app] = {
                'seconds': int(sec),
                'launches': launches.get(app, 0),
                'avg_session': int(sec / launches.get(app, 1)) if launches.get(app, 0) > 0 else 0,
                'last_used': int(last_seen.get(app, 0))
            }

        # hourly_seconds aggregation
        hourly_seconds = {}
        # iterate sessions again and split into hour buckets
        for i, ev in enumerate(events):
            start = ev['ts']
            end = events[i+1]['ts'] if i+1 < len(events) else min(now.timestamp(), end_ts)
            if end <= start:
                continue
            if not ev['using']:
                continue
            seg_start = max(start, start_ts)
            seg_end = min(end, end_ts)
            # split into hours
            cur = seg_start
            while cur < seg_end:
                try:
                    tz = pytz.timezone(env.main.timezone) if pytz else None
                except Exception:
                    tz = None
                if tz:
                    hour_dt = datetime.fromtimestamp(cur, tz).replace(minute=0, second=0, microsecond=0)
                else:
                    hour_dt = datetime.fromtimestamp(cur).replace(minute=0, second=0, microsecond=0)
                hour_start = hour_dt.timestamp()
                hour_end = hour_start + 3600
                part_end = min(seg_end, hour_end)
                add = part_end - cur
                key = hour_dt.strftime('%Y-%m-%d %H:00')
                hourly_seconds[key] = hourly_seconds.get(key, 0) + add
                cur = part_end

        base['per_app'] = per_app
        base['hourly_seconds'] = {k: int(v) for k, v in hourly_seconds.items()}
        # recent sessions for this device (most recent first)
        recent = []
        # build sessions from events list used above
        for i, ev in enumerate(events):
            if not ev['using']:
                continue
            start = ev['ts']
            end = events[i+1]['ts'] if i+1 < len(events) else min(now.timestamp(), end_ts)
            # clip to window
            if end <= start or end < start_ts or start > end_ts:
                continue
            seg_start = max(start, start_ts)
            seg_end = min(end, end_ts)
            duration = int(seg_end - seg_start)
            running = (i+1 >= len(events) and ev['using'] and (end >= now.timestamp() - 1))
            recent.append({
                'app_name': ev['app'],
                'device_id': device_id,
                'start_time': int(start),
                'end_time': (None if running else int(end)),
                'duration': duration,
                'status': ('running' if running else 'stopped')
            })
        # sort and trim
        recent.sort(key=lambda x: x['start_time'], reverse=True)
        base['recent'] = recent[:200]
        base['heart_rate'] = self.get_heart_rate_details(device_id, hours)
        return base

    def get_app_hour_breakdown(self, device_id: str, hour_key: str, hours: int = 24) -> dict:
        """
        返回指定 hour (格式 'YYYY-MM-DD HH:00') 的每应用使用秒数与启动次数。
        如果 device_id 为空字符串，则聚合所有设备。
        """
        try:
            hour_dt = datetime.strptime(hour_key, '%Y-%m-%d %H:00')
        except Exception:
            raise ValueError('hour must be YYYY-MM-DD HH:00')
        # compute window
        try:
            hour_start = pytz.timezone(env.main.timezone).localize(hour_dt).timestamp()
        except Exception:
            hour_start = hour_dt.timestamp()
        hour_end = hour_start + 3600

        def collect_for_list(lst):
            per_app = {}
            launches = {}
            last_seen = {}
            # build events sorted
            events = []
            for e in lst:
                try:
                    t = datetime.fromisoformat(e['time']).timestamp()
                except Exception:
                    continue
                events.append({'ts': t, 'app': e.get('app_name_only') or e.get('app_name') or '[unknown]', 'using': bool(e.get('using', False))})
            events.sort(key=lambda x: x['ts'])
            for i, ev in enumerate(events):
                start = ev['ts']
                end = events[i+1]['ts'] if i+1 < len(events) else hour_end
                if end <= start:
                    continue
                # clip to hour window
                if end <= hour_start or start >= hour_end:
                    continue
                seg_start = max(start, hour_start)
                seg_end = min(end, hour_end)
                if ev['using']:
                    per_app[ev['app']] = per_app.get(ev['app'], 0) + (seg_end - seg_start)
                    # launches count similar heuristic
                    prev = events[i-1] if i-1 >= 0 else None
                    is_new_launch = False
                    if prev is None:
                        is_new_launch = True
                    else:
                        if (not prev['using']) or (prev['app'] != ev['app']):
                            is_new_launch = True
                    if is_new_launch:
                        launches[ev['app']] = launches.get(ev['app'], 0) + 1
                last_seen[ev['app']] = max(last_seen.get(ev['app'], 0), int(ev['ts']))
            return per_app, launches, last_seen

        if device_id:
            raw = self.data.get('app_history', {}).get(device_id, [])
            per_app, launches, last_seen = collect_for_list(raw)
        else:
            per_app = {}
            launches = {}
            last_seen = {}
            for did, lst in self.data.get('app_history', {}).items():
                pa, la, ls = collect_for_list(lst)
                for k, v in pa.items():
                    per_app[k] = per_app.get(k, 0) + v
                for k, v in la.items():
                    launches[k] = launches.get(k, 0) + v
                for k, v in ls.items():
                    last_seen[k] = max(last_seen.get(k, 0), v)

        # format
        res = {}
        for app, sec in per_app.items():
            res[app] = {
                'seconds': int(sec),
                'launches': int(launches.get(app, 0)),
                'last_used': int(last_seen.get(app, 0))
            }
        return res

    def get_recent_records(self, device_id: str, hours: int = 24) -> list:
        """
        返回指定设备最近的应用使用记录。

        :param device_id: 设备 ID（必填）
        :param hours: 统计窗口，默认最近 24 小时
        """
        if not device_id:
            raise ValueError('device_id required')

        # 复用单设备的拆分逻辑，避免聚合后混淆设备来源
        history = self.get_app_usage_details_v2(device_id, hours)
        recent = history.get('recent', []) if isinstance(history, dict) else []
        return recent if isinstance(recent, list) else []

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
        start_dt, end_dt, now = self._calc_time_window(hours)
        start_ts = start_dt.timestamp()
        end_ts = end_dt.timestamp()

        events = []
        for e in all_raw:
            try:
                t = datetime.fromisoformat(e['time']).timestamp()
            except Exception:
                continue
            events.append({'ts': t, 'app': e.get('app_name_only') or e.get('app_name') or '[unknown]', 'using': bool(e.get('using', False))})
        events.sort(key=lambda x: x['ts'])

        totals = {}
        launches = {}
        last_seen = {}
        for i, ev in enumerate(events):
            start = ev['ts']
            end = events[i+1]['ts'] if i+1 < len(events) else min(now.timestamp(), end_ts)
            if end <= start:
                continue
            if end < start_ts or start > end_ts:
                continue
            seg_start = max(start, start_ts)
            seg_end = min(end, end_ts)
            duration = seg_end - seg_start
            if ev['using']:
                totals[ev['app']] = totals.get(ev['app'], 0) + duration
                # 启动次数：当前事件为 using 且前一事件未使用或 app 不同
                prev = events[i-1] if i-1 >= 0 else None
                is_new_launch = False
                if prev is None:
                    is_new_launch = True
                else:
                    if (not prev['using']) or (prev['app'] != ev['app']):
                        is_new_launch = True
                if is_new_launch:
                    launches[ev['app']] = launches.get(ev['app'], 0) + 1
                last_seen[ev['app']] = max(last_seen.get(ev['app'], 0), int(ev['ts']))

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
        hourly_seconds = {}
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

        # 计算每小时使用秒数（基于事件构造的 session）
        for i, ev in enumerate(events):
            start = ev['ts']
            end = events[i+1]['ts'] if i+1 < len(events) else now.timestamp()
            if end <= start or end < start_ts:
                continue
            if not ev['using']:
                continue
            seg_start = max(start, start_ts)
            seg_end = end
            cur = seg_start
            while cur < seg_end:
                try:
                    tz = pytz.timezone(env.main.timezone) if pytz else None
                except Exception:
                    tz = None
                if tz:
                    hour_dt = datetime.fromtimestamp(cur, tz).replace(minute=0, second=0, microsecond=0)
                else:
                    hour_dt = datetime.fromtimestamp(cur).replace(minute=0, second=0, microsecond=0)
                hour_start = hour_dt.timestamp()
                hour_end = hour_start + 3600
                part_end = min(seg_end, hour_end)
                add = part_end - cur
                key = hour_dt.strftime('%Y-%m-%d %H:00')
                hourly_seconds[key] = hourly_seconds.get(key, 0) + add
                cur = part_end

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

        # build recent sessions across all devices
        recent = []
        for device_id, lst in self.data.get('app_history', {}).items():
            # build events for this device
            evs = []
            for e in lst:
                try:
                    t = datetime.fromisoformat(e['time']).timestamp()
                except Exception:
                    continue
                evs.append({'ts': t, 'app': e.get('app_name_only') or e.get('app_name') or '[unknown]', 'using': bool(e.get('using', False))})
            evs.sort(key=lambda x: x['ts'])
            for i, ev in enumerate(evs):
                if not ev['using']:
                    continue
                start = ev['ts']
                end = evs[i+1]['ts'] if i+1 < len(evs) else now.timestamp()
                if end <= start or end < start_ts:
                    continue
                seg_start = max(start, start_ts)
                seg_end = end
                duration = int(seg_end - seg_start)
                running = (i+1 >= len(evs) and ev['using'] and (end >= now.timestamp() - 1))
                recent.append({
                    'app_name': ev['app'],
                    'device_id': device_id,
                    'start_time': int(start),
                    'end_time': (None if running else int(end)),
                    'duration': duration,
                    'status': ('running' if running else 'stopped')
                })
        recent.sort(key=lambda x: x['start_time'], reverse=True)

        return {
            'hours': hours,
            'totals_seconds': {k: int(v) for k, v in totals.items()},
            'top_app': top_app,
            'top_seconds': top_seconds,
            'current_app': current_app,
            'current_runtime': current_runtime,
            'hourly': res,
            'per_app': {k: {'seconds': int(v), 'launches': launches.get(k, 0), 'last_used': last_seen.get(k, 0)} for k, v in totals.items()},
            'hourly_seconds': {k: int(v) for k, v in hourly_seconds.items()},
            'recent': recent[:500]
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

    def mark_stale_devices_offline(self, threshold_hours: int = 2):
        """
        将超过指定时间未上报的设备标记为离线。

        :param threshold_hours: 超过多少小时未上报视为离线
        """
        try:
            tz = pytz.timezone(env.main.timezone)
        except Exception:
            tz = None

        now_dt = datetime.now(tz) if tz else datetime.utcnow()
        cutoff = now_dt - timedelta(hours=threshold_hours)
        device_status: dict = self.data.get('device_status', {})
        changed = False

        for device_id, info in device_status.items():
            updated_at = info.get('updated_at')
            heart_updated_at = info.get('heart_updated_at')
            timestamps = []
            for ts in [updated_at, heart_updated_at]:
                ts_val = self._safe_parse_ts(ts) if ts else None
                if ts_val:
                    timestamps.append(ts_val)
            if not timestamps:
                continue

            last_seen_ts = max(timestamps)
            last_seen = datetime.fromtimestamp(last_seen_ts, tz)

            if last_seen < cutoff:
                if not info.get('offline'):
                    info['offline'] = True
                    info['using'] = False
                    info['app_name'] = '超时自动离线'
                    changed = True
            elif info.get('offline'):
                info['offline'] = False
                changed = True

        if changed:
            self.data['last_updated'] = now_dt.strftime('%Y-%m-%d %H:%M:%S')

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
                self.mark_stale_devices_offline()  # 标记长时间未上报的设备
                self.check_metrics_time()  # 检测是否跨日
                self.check_device_status(trigged_by_timer=True)  # 检测设备状态并更新 status
                file_data = self.load(ret=True)
                if file_data != self.data:
                    self.save()
            except Exception as e:
                u.warning(f'[timer_check] Error: {e}, retrying.')

    # --- check device heartbeat
    # TODO
