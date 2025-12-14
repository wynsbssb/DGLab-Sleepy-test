// 获取 base url
const routerIndex = window.location.href.indexOf('?');
const baseUrl = window.location.href.slice(0, routerIndex > 0 ? routerIndex : window.location.href.length);

// sleep (只能加 await 在 async 函数中使用)
const sleep = (delay) => new Promise((resolve) => setTimeout(resolve, delay));

function sliceText(text, maxLength) {
    /*
    截取指定长度文本
    */
    if (
        text.length <= maxLength || // 文本长度小于指定截取长度
        maxLength == 0 // 截取长度设置为 0 (禁用)
    ) {
        return text;
    }
    return text.slice(0, maxLength - 3) + '...';
}

function escapeHtml(str) {
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

function escapeJs(str) {
    return String(str)
        .replace(/\\/g, '\\\\')
        .replace(/'/g, "\\'")
        .replace(/\n/g, '\\n')
        .replace(/\r/g, '\\r');
}

function formatDuration(seconds) {
    const sec = Math.max(0, Math.round(seconds || 0));
    if (sec >= 3600) {
        const h = Math.floor(sec / 3600);
        const m = Math.floor((sec % 3600) / 60);
        return `${h}小时${m ? m + '分钟' : ''}`;
    }
    if (sec >= 60) {
        const m = Math.round(sec / 60);
        return `${m}分钟`;
    }
    return `${sec}秒`;
}

function getFormattedDate(date) {
    const pad = (num) => (num < 10 ? '0' + num : num);
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}

async function checkVercelDeploy() {
    /*
    检查是否为 Vercel 部署 (经测试 Vercel 不支持 SSE)
    测试方法: 请求 /none，检查返回 Headers 中是否包含 x-vercel-id
    */
    console.log(`[Vercel] 测试请求 ${baseUrl + 'none'} 中...`);
    return await fetch(baseUrl + 'none', { timeout: 10000 })
        .then(resp => {
            const xVercelId = resp.headers.get('x-vercel-id');
            console.log(`[Vercel] 获取到 x-vercel-id: ${xVercelId}`);
            if (xVercelId) {
                console.log(`[Vercel] 确定为 Vercel 部署`);
                return true;
            } else {
                console.log(`[Vercel] 非 Vercel 部署`);
                return false;
            }
        })
        .catch(error => {
            console.log(`[Vercel] 请求错误: ${error}`);
            return false;
        });
}

function updateElement(data) {
    /*
    正常更新状态使用
    data: api / events 返回数据
    */
    const statusElement = document.getElementById('status');
    const lastUpdatedElement = document.getElementById('last-updated');

    // 更新状态
    if (statusElement) {
        statusElement.textContent = data.info.name;
        document.getElementById('additional-info').innerHTML = data.info.desc;
        let last_status = statusElement.classList.item(0);
        statusElement.classList.remove(last_status);
        statusElement.classList.add(data.info.color);
    }

    // 更新设备状态
    var deviceStatus = '<hr/><b><p id="device-status"><i>Device</i> Status</p></b>';
    const devicesEntries = Object.entries(data.device); // [id, obj]
    const devicesListEl = document.getElementById('devices-list');

    const resolveDeviceState = (device) => {
        const app = device.app_name || '';
        if (device.using) return { label: '运行中', cls: 'status-running' };
        if (/待机|standby/i.test(app)) return { label: '待机', cls: 'status-standby' };
        return { label: '已停止', cls: 'status-stopped' };
    };

    const findBatteryPercent = (device) => {
        if (typeof device.battery_percent === 'number') return device.battery_percent;
        if (typeof device.battery_percent === 'string') {
            const ms = device.battery_percent.match(/(\d{1,3})/);
            if (ms) return parseInt(ms[1], 10);
        }
        try {
            const m = (device.app_name || '').match(/电量[:：]?\s*(\d{1,3})%/);
            const m2 = (device.app_name || '').match(/🔋\s*(\d{1,3})%/);
            if (m) return parseInt(m[1], 10);
            if (m2) return parseInt(m2[1], 10);
        } catch(e) { /* ignore */ }
        return null;
    };

    function updateStatusStrip(details, device) {
        const lastAppEl = document.getElementById('last-app');
        const stateEl = document.getElementById('device-state');
        const runtimeEl = document.getElementById('runtime-minutes');
        const statusMeta = device ? resolveDeviceState(device) : { label: '—' };
        const lastRecent = details && details.recent && details.recent.length ? details.recent[0] : null;
        const lastAppRaw = (lastRecent && lastRecent.app_name) || (device && device.app_name) || '';
        const displayApp = /待机|standby/i.test(lastAppRaw || '') ? '设备待机' : (lastAppRaw || '暂无记录');
        const totalSeconds = details && details.totals_seconds ? Object.values(details.totals_seconds).reduce((s,x)=>s+(x||0),0) : 0;
        const runtimeSeconds = (device && device.using && details && details.current_runtime) ? details.current_runtime : totalSeconds;

        if (lastAppEl) lastAppEl.textContent = displayApp;
        if (stateEl) stateEl.textContent = statusMeta.label;
        if (runtimeEl) runtimeEl.textContent = runtimeSeconds ? `${Math.max(1, Math.round(runtimeSeconds/60))} 分钟` : '—';
    }

    if (devicesListEl) {
        devicesListEl.innerHTML = '';
        for (let [id, device] of devicesEntries) {
            const statusMeta = resolveDeviceState(device);
            const batteryPercent = findBatteryPercent(device);
            const batteryText = batteryPercent !== null && batteryPercent !== undefined ? `${batteryPercent}%` : '—%';
            const box = document.createElement('div');
            box.className = `device-box ${statusMeta.cls}`;
            box.dataset.id = id;
            box.innerHTML = `<div class="device-box-head"><div class="device-title">${escapeHtml(device.show_name || id)}</div><span class="status-chip ${statusMeta.cls}">${statusMeta.label}</span></div>` +
                `<div class="device-app-pill" title="${escapeHtml(device.app_name || '暂无运行应用')}"><span class="pill-label">当前应用</span><span class="pill-value">${device.app_name ? escapeHtml(device.app_name) : '暂无运行应用'}</span></div>` +
                `<div class="device-meta-row"><div class="battery-inline"><svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><rect x="2" y="7" width="18" height="10" rx="2" ry="2" stroke="currentColor" stroke-width="1.6" fill="none"></rect><rect x="20" y="10" width="2" height="4" rx="1" fill="currentColor"></rect><rect x="4" y="9" width="12" height="6" rx="1" fill="currentColor" opacity="0.18"></rect></svg><span>${batteryText}</span></div></div>`;

            devicesListEl.appendChild(box);
        }
    }


    const showDashboardError = (msg) => {
        const parts = [
            ['donut-root', true],
            ['hourly-root', true],
            ['progress-list', false],
            ['recent-table', false],
        ];
        parts.forEach(([id, wrap]) => {
            const el = document.getElementById(id);
            if (el) {
                el.innerHTML = `<div class="muted">${msg}</div>`;
                if (wrap) {
                    el.parentElement?.classList?.add('chart-error');
                }
            }
        });
    };

    const firstEntry = data.device && Object.keys(data.device).length ? Object.entries(data.device)[0] : null;
    const chosenId = (window.selectedDeviceId && data.device[window.selectedDeviceId]) ? window.selectedDeviceId : (firstEntry ? firstEntry[0] : null);
    if (chosenId) {
        window.selectedDeviceId = chosenId;
        window.currentDevice = data.device[chosenId];
        try {
            const resp = await fetch(`/device/history?id=${encodeURIComponent(chosenId)}&hours=24`);
            const jd = await resp.json();
            if (jd.success && jd.history) {
                renderDashboardAggregate(jd.history, data.device[chosenId]);
            } else {
                showDashboardError('暂无可用数据');
                updateStatusStrip(null, data.device[chosenId]);
            }
        } catch (e) {
            console.warn('history fetch failed', e);
            showDashboardError('加载失败，请稍后重试');
            updateStatusStrip(null, data.device[chosenId]);
        }
    }

    function renderHistory(history, container) {
        if (!container) return;
        if (!history || !history.length) {
            container.innerHTML = '<div class="muted">暂无历史</div>';
            return;
        }

        // Build chart structure
        if (container && !container.classList.contains('history-chart')) {
            container.classList.add('history-chart');
        }
        const header = document.createElement('div');
        header.className = 'history-header';
        header.innerHTML = '<span>过去24小时</span><span class="muted">0-23 时段</span>';
        container.innerHTML = '';
        container.appendChild(header);
        const grid = document.createElement('div');
        grid.className = 'history-grid';
        // determine max seconds for height scaling
        const secondsMap = (container.dataset.hourlySeconds) ? JSON.parse(container.dataset.hourlySeconds) : {};
        const sumSec = Object.values(secondsMap).reduce((s,x)=>s+(x||0),0) || 1;
        const maxSec = Math.max(1, history.reduce((m,h)=> Math.max(m, secondsMap[h.hour] || 0), 0));
        history.forEach(h => {
            const div = document.createElement('div');
            div.className = 'hour';
            const sec = secondsMap[h.hour] || 0;
            const heightPct = Math.min(100, Math.round((sec / maxSec) * 100));
            div.style.height = '28px';
            div.style.display = 'flex';
            div.style.alignItems = 'flex-end';
            const pctOfDay = Math.round((sec / sumSec) * 100);
            div.title = `${h.hour} — ${Math.round(sec/60)} 分钟 (${pctOfDay}% 当日占比)`;
            const bar = document.createElement('div');
            bar.className = h.top_app ? 'filled' : 'empty';
            bar.style.width = '100%';
            bar.style.height = (heightPct * 0.9) + '%';
            bar.style.display = 'flex';
            bar.style.alignItems = 'center';
            bar.style.justifyContent='center';
            bar.style.fontSize='10px';
            if (h.top_app) bar.innerText = h.top_app;
            div.appendChild(bar);
            grid.appendChild(div);
        });
        container.appendChild(grid);
    }
    // select app from donut
    // select app from donut: scroll to detail and highlight
    function selectAppFromDonut(appName){
        // find details row
        const rows = document.querySelectorAll('.tot-item');
        for(const r of rows){
            if(r.textContent.trim().startsWith(appName)){
                r.scrollIntoView({behavior:'smooth', block:'center'});
                r.classList.add('highlight');
                setTimeout(()=> r.classList.remove('highlight'), 3000);
                break;
            }
        }
    }

    // animate number helper
    function animateNumber(el, from, to, duration=800){
        if(!el) return;
        from = Number(from)||0; to = Number(to)||0;
        const start = performance.now();
        function tick(now){
            const p = Math.min(1, (now-start)/duration);
            const cur = Math.round(from + (to-from)*p);
            el.textContent = cur + 's';
            if(p<1) requestAnimationFrame(tick);
        }
        requestAnimationFrame(tick);
    }

    // 绘制带图例的环形图
    function drawDonut(container, data){
        container.innerHTML = '';
        if(!data || !data.length){
            container.innerHTML = '<div class="muted">暂无数据</div>';
            return;
        }
        const total = data.reduce((s,i)=>s+i.seconds,0)||1;
        const wrap = document.createElement('div');
        wrap.className = 'donut-layout';

        const graphic = document.createElement('div');
        graphic.className = 'donut-graphic';
        const svg = document.createElementNS('http://www.w3.org/2000/svg','svg');
        svg.setAttribute('viewBox','0 0 240 240');
        const radius = 90;
        const circumference = 2 * Math.PI * radius;
        let offset = 0;

        // 底环
        const baseCircle = document.createElementNS('http://www.w3.org/2000/svg','circle');
        baseCircle.setAttribute('cx','120'); baseCircle.setAttribute('cy','120');
        baseCircle.setAttribute('r', radius);
        baseCircle.setAttribute('fill','none');
        baseCircle.setAttribute('stroke','rgba(255,255,255,0.08)');
        baseCircle.setAttribute('stroke-width','26');
        svg.appendChild(baseCircle);

        data.forEach((d)=>{
            const pct = d.seconds/total;
            const segLength = pct * circumference;
            const circle = document.createElementNS('http://www.w3.org/2000/svg','circle');
            circle.setAttribute('cx','120'); circle.setAttribute('cy','120');
            circle.setAttribute('r', radius);
            circle.setAttribute('fill','none');
            circle.setAttribute('stroke', d.color);
            circle.setAttribute('stroke-width','26');
            circle.setAttribute('stroke-dasharray', `${segLength} ${circumference}`);
            circle.setAttribute('stroke-dashoffset', `${-offset}`);
            circle.setAttribute('stroke-linecap','round');
            offset += segLength;
            circle.addEventListener('click', ()=> { selectAppFromDonut(d.name); setCenter(d); });
            circle.addEventListener('mouseover', ()=> setCenter(d));
            svg.appendChild(circle);
        });

        const center = document.createElement('div');
        center.className = 'donut-center';
        function setCenter(d){
            const pct = Math.round((d.seconds/total)*100);
            center.innerHTML = `<div class="title">应用使用时间</div><div class="value">${formatDuration(d.seconds)}</div><div class="subtitle">${escapeHtml(d.name)} · ${pct}%</div>`;
        }
        if(data.length) setCenter(data[0]);

        graphic.appendChild(svg);
        graphic.appendChild(center);

        const legend = document.createElement('div');
        legend.className = 'donut-legend';
        data.forEach((d)=>{
            const item = document.createElement('div');
            item.className = 'legend-item';
            const pct = Math.round((d.seconds/total)*100);
            item.innerHTML = `<div class="legend-swatch" style="background:${d.color}"></div>` +
                `<div class="legend-text"><div class="legend-name" title="${escapeHtml(d.name)}">${escapeHtml(d.name)}</div>` +
                `<div class="legend-meta">${formatDuration(d.seconds)} · ${pct}%</div></div>`;
            item.addEventListener('click', ()=> { selectAppFromDonut(d.name); setCenter(d); });
            legend.appendChild(item);
        });

        wrap.appendChild(graphic);
        wrap.appendChild(legend);
        container.appendChild(wrap);
    }

    // generate color palette
    function generateColors(n){
        const base = ['#1570EF','#2E7D32','#6C5CE7','#FF7043','#0288D1','#8E24AA','#03A9F4'];
        const out = [];
        for(let i=0;i<n;i++) out.push(base[i%base.length]);
        return out;
    }

    function renderRecentTable(root, records){
        if(!root) return;
        root.innerHTML = '';
        if(!records || !records.length){
            root.innerHTML = '<div class="muted">无最近记录</div>';
            return;
        }
        const wrapper = document.createElement('div');
        wrapper.className = 'recent-table-wrapper collapsed';
        const table = document.createElement('table');
        table.innerHTML = '<tr><th>应用</th><th>开始</th><th>结束</th><th>持续</th></tr>';
        records.forEach(r=>{
            const tr = document.createElement('tr');
            if(!r.end_time || r.status === 'running') tr.classList.add('running');
            const endTxt = r.end_time? new Date(r.end_time*1000).toLocaleString() : '运行中';
            const durTxt = r.duration ? Math.round(r.duration)+'s' : (r.end_time? '—':'运行中');
            tr.innerHTML = `<td class="app-name" title="${escapeHtml(r.app_name||'—')}">${escapeHtml(sliceText(r.app_name||'—', 64))}</td>`+
                `<td>${new Date(r.start_time*1000).toLocaleString()}</td>`+
                `<td>${endTxt}</td>`+
                `<td>${durTxt}</td>`;
            table.appendChild(tr);
        });
        wrapper.appendChild(table);
        root.appendChild(wrapper);
        if(records.length > 5){
            const toggle = document.createElement('button');
            toggle.className = 'recent-toggle ghost-btn';
            toggle.textContent = '展开查看更多';
            toggle.addEventListener('click', ()=>{
                const expanded = wrapper.classList.toggle('expanded');
                wrapper.classList.toggle('collapsed', !expanded);
                toggle.textContent = expanded ? '收起列表' : '展开查看更多';
            });
            root.appendChild(toggle);
        }
    }

    // Render dashboard aggregate panels, donut and hourly chart
    function renderDashboardAggregate(details, device){
        if(!details) return;
        // top stats
        const appCount = Object.keys(details.totals_seconds||{}).length || 0;
        const totalSeconds = Object.values(details.totals_seconds||{}).reduce((s,x)=>s+(x||0),0) || 0;
        const totalTimeText = totalSeconds >= 3600 ? Math.round(totalSeconds/3600)+'h' : Math.round(totalSeconds/60)+'m';
        const topApp = details.top_app || '—';
        const setText = (id,txt)=>{ const el=document.getElementById(id); if(el) el.querySelector('.stat-value').textContent=txt };
        setText('stat-app-count', appCount);
        setText('stat-total-time', totalTimeText);
        setText('stat-top-app', topApp);
        updateStatusStrip(details, device || window.currentDevice || null);

        // donut data from totals_seconds
        const totals = details.totals_seconds || {};
        const entries = Object.entries(totals).sort((a,b)=>b[1]-a[1]);
        const donutData = entries.map((it,i)=>({name:it[0], seconds:it[1]}));
        const donutRoot = document.getElementById('donut-root');
        if(donutRoot){
            drawDonut(donutRoot, donutData.map((d,i)=>({name:d.name, seconds:d.seconds, color: generateColors(donutData.length)[i]})));
        }

        // hourly chart
        const hourlyRoot = document.getElementById('hourly-root');
        if(hourlyRoot){
            hourlyRoot.innerHTML = '';
            hourlyRoot.dataset.hourlySeconds = JSON.stringify(details.hourly_seconds || {});
            renderHistory(details.hourly || [], hourlyRoot);
        }

        // progress list
        const pl = document.getElementById('progress-list');
        if(pl){
            pl.innerHTML = '';
            const total = Math.max(1, totalSeconds);
            const wrap = document.createElement('div');
            wrap.className = 'progress-wrapper collapsed';
            entries.forEach(([name,sec],i)=>{
                const pct = Math.round(sec/total*100);
                const row = document.createElement('div'); row.className='app-row';
                row.innerHTML = `<div><strong>${escapeHtml(name)}</strong></div><div>${Math.round(sec/60)}分 <span class="muted">(${pct}%)</span></div>`;
                const prog = document.createElement('div'); prog.className='progress'; const fill = document.createElement('div'); fill.className='progress-fill'; fill.style.width=pct+'%'; fill.style.background=generateColors(entries.length)[i%7]; prog.appendChild(fill);
                wrap.appendChild(row); wrap.appendChild(prog);
            });
            pl.appendChild(wrap);
            if(entries.length > 6){
                const toggle = document.createElement('button');
                toggle.className = 'ghost-btn progress-toggle';
                toggle.textContent = '展开详细数据';
                toggle.addEventListener('click', ()=>{
                    const expanded = wrap.classList.toggle('expanded');
                    wrap.classList.toggle('collapsed', !expanded);
                    toggle.textContent = expanded ? '收起详细数据' : '展开详细数据';
                });
                pl.appendChild(toggle);
            } else {
                wrap.classList.remove('collapsed');
            }
        }

        // recent table (if provided)
        const recentRoot = document.getElementById('recent-table');
        if(recentRoot){
            recentRoot.innerHTML = '<div class="loading">加载最近记录...</div>';
            (async()=>{
                const deviceQuery = chosenId ? `id=${encodeURIComponent(chosenId)}&` : '';
                try{
                    const resp = await fetch(`/recent?${deviceQuery}limit=10&hours=48`);
                    const jd = await resp.json();
                    if(jd.success){
                        renderRecentTable(recentRoot, jd.records || []);
                        return;
                    }
                }catch(e){ /* fallback */ }
                renderRecentTable(recentRoot, (details.recent||[]).slice(0,10));
            })();
        }
    }
    // 更新最后更新时间
    const timenow = getFormattedDate(new Date());
    if (lastUpdatedElement) {
        lastUpdatedElement.innerHTML = `
最后更新:
<a class="awake" 
title="服务器时区: ${data.timezone}" 
href="javascript:alert('浏览器最后更新时间: ${timenow}\\n数据最后更新时间 (基于服务器时区): ${data.last_updated}\\n服务端时区: ${data.timezone}')">
${data.last_updated}
</a>`;
    }
}

// 全局变量 - 重要：保证所有函数可访问
let evtSource = null;
let reconnectInProgress = false;
let countdownInterval = null;
let delayInterval = null;
let connectionCheckTimer = null;
let lastEventTime = Date.now();
let connectionAttempts = 0;
let firstError = true; // 是否为 SSR 第一次出错 (如是则激活 Vercel 部署检测)
const maxReconnectDelay = 30000; // 最大重连延迟时间为 30 秒

// 重连函数
function reconnectWithDelay(delay) {
    if (reconnectInProgress) {
        console.log('[SSE] 已经在重连过程中，忽略此次请求');
        return;
    }

    reconnectInProgress = true;
    console.log(`[SSE] 安排在 ${delay / 1000} 秒后重连`);

    // 清除可能存在的倒计时
    if (countdownInterval) {
        clearInterval(countdownInterval);
    }

    // 更新UI状态
    const statusElement = document.getElementById('status');
    if (statusElement) {
        statusElement.textContent = '[!错误!]';
        document.getElementById('additional-info').textContent = '与服务器的连接已断开，正在尝试重新连接...';
        let last_status = statusElement.classList.item(0);
        statusElement.classList.remove(last_status);
        statusElement.classList.add('error');
    }

    // 添加倒计时更新
    let remainingSeconds = Math.floor(delay / 1000);
    const lastUpdatedElement = document.getElementById('last-updated');
    if (lastUpdatedElement) {
        lastUpdatedElement.innerHTML = `连接服务器失败，${remainingSeconds} 秒后重新连接... <a href="javascript:reconnectNow();" target="_self" style="color: rgb(0, 255, 0);">立即重连</a>`;
    }

    countdownInterval = setInterval(() => {
        remainingSeconds--;
        if (remainingSeconds > 0 && lastUpdatedElement) {
            lastUpdatedElement.innerHTML = `连接服务器失败，${remainingSeconds} 秒后重新连接... <a href="javascript:reconnectNow();" target="_self" style="color: rgb(0, 255, 0);">立即重连</a>`;
        } else if (remainingSeconds <= 0) {
            clearInterval(countdownInterval);
        }
    }, 1000);

    delayInterval = setTimeout(() => {
        if (reconnectInProgress) {
            console.log('[SSE] 开始重连...');
            clearInterval(countdownInterval); // 清除倒计时
            setupEventSource();
            reconnectInProgress = false;
        }
    }, delay);
}

// 立即重连函数
function reconnectNow() {
    console.log('[SSE] 用户选择立即重连');
    clearInterval(delayInterval); // 清除当前倒计时
    clearInterval(countdownInterval);
    connectionAttempts = 0; // 重置重连计数
    setupEventSource(); // 立即尝试重新连接
    reconnectInProgress = false;
}


// 建立SSE连接
function setupEventSource() {
    // 重置重连状态
    reconnectInProgress = false;

    // 清除可能存在的倒计时
    if (countdownInterval) {
        clearInterval(countdownInterval);
        countdownInterval = null;
    }

    // 清除旧的定时器
    if (connectionCheckTimer) {
        clearTimeout(connectionCheckTimer);
        connectionCheckTimer = null;
    }

    // 更新UI状态
    const statusElement = document.getElementById('status');
    const lastUpdatedElement = document.getElementById('last-updated');
    if (lastUpdatedElement) {
        lastUpdatedElement.innerHTML = `正在连接服务器... <a href="javascript:location.reload();" target="_self" style="color: rgb(0, 255, 0);">刷新页面</a>`;
    }

    // 关闭旧连接
    if (evtSource) {
        evtSource.close();
    }

    // 创建新连接
    evtSource = new EventSource(baseUrl + 'events');

    // 监听连接打开事件
    evtSource.onopen = function () {
        console.log('[SSE] 连接已建立');
        connectionAttempts = 0; // 重置重连计数
        lastEventTime = Date.now(); // 初始化最后事件时间
    };

    // 监听更新事件
    evtSource.addEventListener('update', function (event) {
        lastEventTime = Date.now(); // 更新最后收到消息的时间

        const data = JSON.parse(event.data);
        console.log(`[SSE] 收到数据更新:`, data);

        // 处理更新数据
        if (data.success) {
            updateElement(data);
        } else {
            if (statusElement) {
                statusElement.textContent = '[!错误!]';
                document.getElementById('additional-info').textContent = data.info || '未知错误';
                let last_status = statusElement.classList.item(0);
                statusElement.classList.remove(last_status);
                statusElement.classList.add('error');
            }
        }
    });

    // 监听心跳事件
    evtSource.addEventListener('heartbeat', function (event) {
        console.log(`[SSE] 收到心跳: ${event.data}`);
        lastEventTime = Date.now(); // 更新最后收到消息的时间
    });

    // 错误处理 - 立即开始重连
    evtSource.onerror = async function (e) {
        console.error(`[SSE] 连接错误: ${e}`);
        evtSource.close();

        // 如是第一次错误，检查是否为 Vercel 部署
        if (firstError) {
            if (await checkVercelDeploy()) {
                // 如是，清除所有定时器，并回退到原始轮询函数
                if (countdownInterval) {
                    clearInterval(countdownInterval);
                    countdownInterval = null;
                }
                if (connectionCheckTimer) {
                    clearTimeout(connectionCheckTimer);
                    connectionCheckTimer = null;
                }
                update();
                return;
            } else {
                // 如不是，以后错误跳过检查
                firstError = false;
            }
        }


        // 计算重连延迟时间 (指数退避)
        const reconnectDelay = Math.min(1000 * Math.pow(2, connectionAttempts), maxReconnectDelay);
        connectionAttempts++;

        // 使用统一重连函数
        reconnectWithDelay(reconnectDelay);
    };

    // 设置长时间未收到消息的检测
    function checkConnectionStatus() {
        const currentTime = Date.now();
        const elapsedTime = currentTime - lastEventTime;

        // 只有在连接正常但长时间未收到消息时才触发重连
        if (elapsedTime > 120 * 1000 && !reconnectInProgress) {
            console.warn('[SSE] 长时间未收到服务器消息，正在重新连接...');
            evtSource.close();

            // 使用与onerror相同的重连逻辑
            const reconnectDelay = Math.min(1000 * Math.pow(2, connectionAttempts), maxReconnectDelay);
            connectionAttempts++;
            reconnectWithDelay(reconnectDelay);
        }

        // 仅当没有正在进行的重连时才设置下一次检查
        if (!reconnectInProgress) {
            connectionCheckTimer = setTimeout(checkConnectionStatus, 10000);
        }
    }

    // 启动连接状态检查
    connectionCheckTimer = setTimeout(checkConnectionStatus, 10000);

    // 在页面卸载时关闭连接
    window.addEventListener('beforeunload', function () {
        if (evtSource) {
            evtSource.close();
        }
    });
}

// 初始化SSE连接或回退到轮询
document.addEventListener('DOMContentLoaded', function () {
    // 初始化变量
    lastEventTime = Date.now();
    connectionAttempts = 0;

    // 仅刷新设备状态的按钮
    const refreshBtn = document.getElementById('refresh-devices');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', async () => {
            refreshBtn.disabled = true;
            refreshBtn.classList.add('spinning');
            try {
                const resp = await fetch(baseUrl + 'query', { timeout: 10000 });
                const jd = await resp.json();
                if (jd.success) {
                    updateElement(jd);
                }
            } catch (e) {
                console.warn('刷新设备状态失败', e);
            } finally {
                refreshBtn.disabled = false;
                refreshBtn.classList.remove('spinning');
            }
        });
    }

    // 页面初始化时先拉取一次 /query，避免在 /events 未返回前一直停留在“加载中”
    (async () => {
        try {
            const resp = await fetch(baseUrl + 'query', { timeout: 10000 });
            const jd = await resp.json();
            if (jd && jd.success) {
                updateElement(jd);
            }
        } catch (e) {
            console.warn('初始查询失败', e);
        }
    })();

    // 检查浏览器是否支持SSE
    if (typeof (EventSource) !== "undefined") {
        console.log('[SSE] 浏览器支持SSE，开始建立连接...');
        // 初始建立连接
        setupEventSource();
    } else {
        // 浏览器不支持SSE，回退到轮询方案
        console.log('[SSE] 浏览器不支持SSE，回退到轮询方案');
        update();
    }
});

// 原始轮询函数 (仅作为后备方案)
async function update() {
    let refresh_time = 5000;
    while (true) {
        if (document.visibilityState == 'visible') {
            console.log('[Update] 页面可见，更新中...');
            let success_flag = true;
            let errorinfo = '';
            const statusElement = document.getElementById('status');
            // --- show updating
            document.getElementById('last-updated').innerHTML = `正在更新状态, 请稍候... <a href="javascript:location.reload();" target="_self" style="color: rgb(0, 255, 0);">刷新页面</a>`;
            // fetch data
            fetch(baseUrl + 'query', { timeout: 10000 })
                .then(response => response.json())
                .then(async (data) => {
                    console.log(`[Update] 返回: ${data}`);
                    if (data.success) {
                        updateElement(data);
                        // update refresh time
                        refresh_time = data.refresh;
                    } else {
                        errorinfo = data.info;
                        success_flag = false;
                    }
                })
                .catch(error => {
                    errorinfo = error;
                    success_flag = false;
                });
            // 出错时显示
            if (!success_flag) {
                statusElement.textContent = '[!错误!]';
                document.getElementById('additional-info').textContent = errorinfo;
                last_status = statusElement.classList.item(0);
                statusElement.classList.remove(last_status);
                statusElement.classList.add('error');
            }
        } else {
            console.log('[Update] 页面不可见，跳过更新');
        }

        await sleep(refresh_time);
    }
}

// popover showing app details
function showAppPopover(name, stats){
    // remove existing
    let pop = document.getElementById('app-popover');
    if (pop) pop.remove();
    pop = document.createElement('div');
    pop.id = 'app-popover';
    pop.className = 'popover';
    const last = stats.last_used ? new Date(stats.last_used * 1000).toLocaleString() : '—';
    pop.innerHTML = `<div style="font-weight:700;margin-bottom:6px">${escapeHtml(name)}</div><div class="muted">今日启动次数: ${stats.launches || 0}</div><div class="muted">平均单次: ${stats.avg_session||0}s</div><div class="muted">最近一次使用: ${escapeHtml(last)}</div>`;
    document.body.appendChild(pop);
    // position near first matching row
    const rows = document.querySelectorAll('.detailed-row');
    for(const r of rows){
        if(r.textContent.trim().startsWith(name)){
            const rect = r.getBoundingClientRect();
            pop.style.left = (rect.right + 12) + 'px';
            pop.style.top = (rect.top + window.scrollY) + 'px';
            break;
        }
    }
    // auto dismiss on click outside
    function onDoc(e){ if(!pop.contains(e.target)) { pop.remove(); document.removeEventListener('click', onDoc); }}
    setTimeout(()=>document.addEventListener('click', onDoc), 10);
}