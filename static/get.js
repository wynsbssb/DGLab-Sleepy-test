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
    const deviceDetailEl = document.getElementById('device-detail');

    if (devicesListEl) {
        devicesListEl.innerHTML = '';
        for (let [id, device] of devicesEntries) {
            const box = document.createElement('div');
            box.className = 'device-box';
            box.dataset.id = id;

            const title = document.createElement('div');
            title.className = 'device-title';
            title.innerText = device.show_name || id;
            const meta = document.createElement('div');
            meta.className = 'meta';
            // 解析电量
            let batteryText = '';
            try {
                const m = (device.app_name || '').match(/电量[:：]?\s*(\d{1,3})%/);
                const m2 = (device.app_name || '').match(/🔋\s*(\d{1,3})%/);
                batteryText = m ? (m[1] + '%') : (m2 ? (m2[1] + '%') : '');
            } catch(e) { batteryText = ''; }
            const statusEl = document.createElement('div');
            statusEl.className = 'device-meta-row';
            statusEl.innerHTML = `<div class="status-dot ${device.using ? 'alive' : 'idle'}"></div> <div class="meta-text">${escapeHtml(device.using ? (device.app_name || '使用中') : '未使用')}</div> <div class="battery-inline">${batteryText ? (' ' + escapeHtml(batteryText)) : ''}</div>`;

            box.appendChild(title);
            box.appendChild(statusEl);

            box.addEventListener('click', function () {
                selectDevice(id, device);
            });

            // 如果当前为已选设备，标记为 active
            if (window.selectedDeviceId && window.selectedDeviceId === id) {
                box.classList.add('active');
            }

            devicesListEl.appendChild(box);
        }
    }

    // 不再自动选中 server 指定的 device id，改为显示聚合与所有设备详情
    // 如果当前有选中设备则刷新它的详情（以便显示最新的 app_name）
    if (window.selectedDeviceId && data.device[window.selectedDeviceId]) {
        renderDeviceDetail(window.selectedDeviceId, data.device[window.selectedDeviceId]);
    } else {
        // 显示所有设备的聚合与每台设备的卡片视图
        renderAllDevices(data);
    }

    // 选择设备并展示详情（保留单设备查看能力）
    window.selectDevice = function (id, device) {
        window.selectedDeviceId = id;
        document.querySelectorAll('.device-box').forEach(b => b.classList.remove('active'));
        const box = document.querySelector(`.device-box[data-id="${id}"]`);
        if (box) box.classList.add('active');
        renderDeviceDetail(id, device);
    }

    async function renderDeviceDetail(id, device) {
        if (!deviceDetailEl) return;
        const show = device.show_name || id;
        const using = device.using ? '使用中' : '未使用';
        const app = device.app_name || '';
        deviceDetailEl.innerHTML = `<div class="info-box"><h4>${escapeHtml(show)}</h4><div class="meta">${escapeHtml(using)} ${escapeHtml(app ? ' - ' + app : '')}</div><div id="summary-wrap"><div class="loading">加载统计...</div></div><div id="history-wrap"><div class="loading">加载历史...</div></div></div>`;
        try {
            const resp = await fetch(`/device/history?id=${encodeURIComponent(id)}&hours=24`);
            const jd = await resp.json();
            if (jd.success && jd.history) {
                // show summary
                const sumwrap = document.getElementById('summary-wrap');
                if (sumwrap) {
                    const details = jd.history;
                    let html = '<div class="summary-row">';
                    html += `<div class="stat-box">最常用: <b>${escapeHtml(details.top_app || '—')}</b><div class="muted">${details.top_seconds}s</div></div>`;
                    html += `<div class="stat-box">当前应用: <b>${escapeHtml(details.current_app || '—')}</b><div class="muted">运行 ${details.current_runtime}s</div></div>`;
                    html += '</div>';
                    sumwrap.innerHTML = html;
                }
                renderHistory(jd.history.hourly, document.getElementById('history-wrap'));

                // also show totals list
                if (jd.history.totals_seconds) {
                    const totals = jd.history.totals_seconds;
                    const tl = document.createElement('div');
                    tl.className = 'totals-list';
                    let items = Object.entries(totals).sort((a,b)=>b[1]-a[1]).slice(0,6);
                    if (items.length) {
                        tl.innerHTML = '<div class="muted">常用应用排行（最近24小时）:</div>' + items.map(it=>`<div class="tot-item">${escapeHtml(it[0])} <span class="muted">— ${it[1]}s</span></div>`).join('');
                        document.getElementById('history-wrap').appendChild(tl);
                    }
                }
            } else {
                document.getElementById('history-wrap').innerHTML = '<div class="muted">无历史数据</div>';
            }
        } catch (e) {
            document.getElementById('history-wrap').innerHTML = '<div class="muted">获取历史失败</div>';
        }
    }

    function renderHistory(history, container) {
        if (!container) return;
        if (!history || history.length === 0) {
            container.innerHTML = '<div style="opacity:0.7;margin-top:8px;">无历史数据</div>';
            return;
        }
        const grid = document.createElement('div');
        grid.className = 'history-grid';
        history.forEach(h => {
            const div = document.createElement('div');
            div.className = 'hour';
            if (h.top_app) {
                div.classList.add('filled');
                div.title = `${h.hour} - ${h.top_app} (${h.top_count})`;
                div.innerText = h.top_app;
            } else {
                div.classList.add('empty');
                div.title = `${h.hour} - 无数据`;
                div.innerText = '';
            }
            grid.appendChild(div);
        });
        container.innerHTML = '<div style="font-size:0.9em;margin-top:8px;">过去24小时（每格为一小时，鼠标悬停查看）</div>';
        container.appendChild(grid);
    }
    // helper: 从 app_name 中解析电量信息
    function parseBattery(text) {
        if (!text) return null;
        // 支持格式: 电量:NN% 或 🔋NN% 或 [🔋NN%] 等
        const m1 = text.match(/电量[:：]?\s*(\d{1,3})%/);
        if (m1) return {percent: parseInt(m1[1], 10)};
        const m2 = text.match(/🔋\s*(\d{1,3})%/);
        if (m2) return {percent: parseInt(m2[1], 10)};
        // 其他括号内形式
        const m3 = text.match(/\[(?:🔋)?(\d{1,3})%\s*.*?\]/);
        if (m3) return {percent: parseInt(m3[1], 10)};
        return null;
    }

    // 渲染所有设备和聚合统计
    async function renderAllDevices(data) {
        if (!deviceDetailEl) return;
        deviceDetailEl.innerHTML = '';
        // All devices aggregate box
        const allBox = document.createElement('div');
        allBox.className = 'info-box all-devices-box';
        allBox.innerHTML = '<h4>全部设备（聚合）</h4><div id="all-summary" class="summary-row"><div class="loading">加载聚合统计...</div></div><div id="all-history" class="history-wrap"><div class="loading">加载历史...</div></div>';
        deviceDetailEl.appendChild(allBox);
        try {
            const resp = await fetch('/device/history?hours=24');
            const jd = await resp.json();
            if (jd.success && jd.history) {
                const sum = document.getElementById('all-summary');
                sum.innerHTML = `<div class="stat-box">最常用: <b>${escapeHtml(jd.history.top_app || '—')}</b><div class="muted">${jd.history.top_seconds}s</div></div>`;
                renderHistory(jd.history.hourly, document.getElementById('all-history'));
            } else {
                document.getElementById('all-history').innerHTML = '<div class="muted">无聚合历史</div>';
            }
        } catch (e) {
            document.getElementById('all-history').innerHTML = '<div class="muted">获取聚合历史失败</div>';
        }

        // 每台设备的卡片
        const wrap = document.createElement('div');
        wrap.className = 'devices-detail-grid';
        for (let [id, device] of Object.entries(data.device)) {
            const card = document.createElement('div');
            card.className = 'device-card';
            const show = device.show_name || id;
            const battery = parseBattery(device.app_name || '');
            const alive = device.using ? '使用中' : '空闲';
            card.innerHTML = `<div class="card-head"><div class="device-title">${escapeHtml(show)}</div><div class="battery-box">${battery ? (battery.percent + '%') : '—'}</div></div><div class="device-status">${escapeHtml(alive)}</div><div class="mini-history muted">加载...</div>`;
            // click toggles detailed view
            card.addEventListener('click', () => selectDevice(id, device));
            wrap.appendChild(card);
            // fetch mini history for each device (6小时缩略图)
            (async function(cardEl, did) {
                try {
                    const r = await fetch(`/device/history?id=${encodeURIComponent(did)}&hours=6`);
                    const jd2 = await r.json();
                    const mh = cardEl.querySelector('.mini-history');
                    if (jd2.success && jd2.history) {
                        const container = document.createElement('div');
                        container.className = 'mini-grid';
                        jd2.history.hourly.forEach(h => {
                            const d = document.createElement('div');
                            d.className = 'mini-hour' + (h.top_app ? ' filled' : ' empty');
                            d.title = `${h.hour} - ${h.top_app || '—'}`;
                            container.appendChild(d);
                        });
                        mh.innerHTML = '';
                        mh.appendChild(container);
                    } else {
                        mh.innerHTML = '<div class="muted">无历史</div>';
                    }
                } catch (e) {
                    const mh = cardEl.querySelector('.mini-history');
                    mh.innerHTML = '<div class="muted">获取失败</div>';
                }
            })(card, id);
        }
        deviceDetailEl.appendChild(wrap);
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
    evtSource = new EventSource('/events');

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