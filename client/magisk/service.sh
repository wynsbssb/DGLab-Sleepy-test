#!/system/bin/sh

# ===================== 安全设置 =====================
# 不用 set -e（很多命令可能失败但不应退出），只做未定义变量防护更稳
set -u

# ===================== 读取配置文件 =====================
SCRIPT_DIR="$(cd "${0%/*}" 2>/dev/null && pwd)"
[ -z "$SCRIPT_DIR" ] && SCRIPT_DIR="${0%/*}"
CONFIG_FILE="${SCRIPT_DIR}/config.cfg"

if [ ! -f "$CONFIG_FILE" ]; then
  echo "[FATAL] config.cfg 不存在: $CONFIG_FILE"
  exit 1
fi

# shellcheck disable=SC1090
. "$CONFIG_FILE"

# ===================== 工具函数 =====================
trim() {
  # 去首尾空白 + 去掉 \r
  echo "$1" | tr -d '\r' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//'
}

strip_cr() { echo "$1" | tr -d '\r'; }

# JSON 转义：\, ", 换行、制表等
json_escape() {
  # 输出一行，内部把真实换行替换为 \n
  # 注意：这里会把多行内容合并为 \n 字面量，服务端 JSON 安全
  printf "%s" "$1" \
    | sed \
      -e 's/\\/\\\\/g' \
      -e 's/"/\\"/g' \
      -e ':a;N;$!ba;s/\n/\\n/g' \
      -e 's/\t/\\t/g' \
      -e 's/\r//g'
}

# ===================== 清理旧脚本实例 =====================
cleanup_old_instances() {
  SCRIPT_NAME="$(basename "$0")"
  CURRENT_PID=$$
  SCRIPT_PATH="$(readlink -f "$0" 2>/dev/null || echo "$0")"
  
  echo "正在清理旧脚本实例..."
  
  # 查找并杀死同脚本的其他进程
  pids=$(ps -eo pid,args 2>/dev/null | grep -E "(sh|bash).*${SCRIPT_NAME}" | grep -v "grep" | grep -v "$CURRENT_PID" | awk '{print $1}')
  
  for pid in $pids; do
    if [ -n "$pid" ] && [ "$pid" -ne "$CURRENT_PID" ]; then
      echo "终止旧进程: PID $pid"
      kill -9 "$pid" 2>/dev/null
    fi
  done
  
  # 查找通过不同路径执行的相同脚本
  all_pids=$(ps -eo pid,cmd 2>/dev/null | grep -v "grep" | grep -v "$CURRENT_PID" | awk '{print $1" "substr($0, index($0,$2))}')
  
  echo "$all_pids" | while read -r pid cmd; do
    if [ -z "$pid" ] || [ "$pid" -eq "$CURRENT_PID" ]; then
      continue
    fi
    
    # 检查命令是否包含脚本名
    if echo "$cmd" | grep -q "${SCRIPT_NAME}"; then
      # 获取脚本路径
      script_in_cmd=$(echo "$cmd" | sed -n "s/.* \([^ ]*${SCRIPT_NAME}\)/\1/p")
      if [ -n "$script_in_cmd" ] && [ -f "$script_in_cmd" ]; then
        # 比较文件内容（简单比较前100字符）
        existing_script_content=$(head -c 100 "$script_in_cmd" 2>/dev/null)
        current_script_content=$(head -c 100 "$0" 2>/dev/null)
        if [ "$existing_script_content" = "$current_script_content" ]; then
          echo "终止相同脚本进程: PID $pid (路径: $script_in_cmd)"
          kill -9 "$pid" 2>/dev/null
        fi
      fi
    fi
  done
  
  # 等待一段时间确保旧进程被清理
  sleep 2
  
  # 再次检查，确保没有残留
  remaining=$(ps -eo pid,args 2>/dev/null | grep -E "(sh|bash).*${SCRIPT_NAME}" | grep -v "grep" | grep -v "$CURRENT_PID" | wc -l)
  if [ "$remaining" -gt 0 ]; then
    echo "警告: 仍有 $remaining 个疑似旧进程在运行"
  else
    echo "旧脚本实例清理完成"
  fi
}

# 立即执行清理
cleanup_old_instances

# ===================== 清理配置变量 =====================
SECRET="$(trim "${SECRET:-}")"
DEVICE_ID="$(strip_cr "${DEVICE_ID:-}")"
URL="$(strip_cr "${URL:-}")"
LOG_NAME="$(strip_cr "${LOG_NAME:-device_status.log}")"
DEVICE_NAME="$(strip_cr "${DEVICE_NAME:-}")"
CACHE="$(strip_cr "${CACHE:-${SCRIPT_DIR}/app_name_cache.txt}")"
GAME_PACKAGES="$(strip_cr "${GAME_PACKAGES:-}")"

if [ -z "$SECRET" ] || [ -z "$DEVICE_ID" ] || [ -z "$URL" ]; then
  echo "[FATAL] SECRET / DEVICE_ID / URL 不能为空"
  exit 1
fi

# cache 文件不存在则创建
[ -f "$CACHE" ] || : > "$CACHE"

# ===================== 日志系统 =====================
LOG_PATH="${SCRIPT_DIR}/${LOG_NAME}"
log() {
  msg="[$(date '+%Y-%m-%d %H:%M:%S')] $1"
  echo "$msg" >> "$LOG_PATH"
}

sleepy=0

# ===================== 计算 BASE_URL（用于 /status/set） =====================
# 兼容：如果 URL 里带 /device/xxx，就截到 /device 前；否则用 URL 去掉尾部 path
get_base_url() {
  u="$1"
  case "$u" in
    */device/*)
      echo "$u" | sed 's#^\(.*\)/device/.*#\1#'
      ;;
    *)
      # 去掉最后一个 / 后面的部分
      echo "$u" | sed 's#^\(.*\)/[^/]*$#\1#'
      ;;
  esac
}

BASE_URL="$(get_base_url "$URL")"

# ===================== 判断是否为游戏：输出 sleep 秒数 =====================
get_interval_seconds() {
  pkg="$1"
  for game in $GAME_PACKAGES; do
    if [ "$game" = "$pkg" ]; then
      # 游戏进程：更长间隔（你原注释写 300 秒，这里给 100/300 二选一：按注释走 300）
      echo "300"
      return
    fi
  done
  echo "3"
}

# ===================== 解析应用名称（包名->缓存->小米商店） =====================
get_app_name() {
  package_name="$1"

  if [ "$package_name" = "NotificationShade" ]; then
    echo "锁屏了"
    return
  fi

  cached_name="$(awk -F '=' -v pkg="$package_name" '$1==pkg {print $2; exit}' "$CACHE" 2>/dev/null)"
  if [ -n "$cached_name" ]; then
    echo "$cached_name"
    return
  fi

  temp_file="${SCRIPT_DIR}/temp.html"
  if curl --silent --show-error --fail -A "Mozilla/5.0" -o "$temp_file" "https://app.mi.com/details?id=$package_name" 2>/dev/null; then
    app_name="$(sed -n 's/.*<title>\(.*\)<\/title>.*/\1/p' "$temp_file" | sed 's/-[^-]*$//')"
    rm -f "$temp_file"

    if [ -n "$app_name" ]; then
      echo "$app_name"
      echo "$package_name=$app_name" >> "$CACHE"
    else
      echo "$package_name"
    fi
  else
    rm -f "$temp_file"
    echo "$package_name"
  fi
}

# ===================== 发送设备状态请求 =====================
send_device_status() {
  package_name="$1"

  app_name="$(get_app_name "$package_name")"

  # 电量（更稳：直接抓 level 行）
  battery_level="$(dumpsys battery 2>/dev/null | grep -m 1 "level" | awk -F ':' '{gsub(/ /,"",$2); print $2}')"
  case "$battery_level" in
    ''|*[!0-9]*)
      battery_level="??"
      ;;
  esac

  charging_flag="false"
  charging_status="🔋"
  if dumpsys battery 2>/dev/null | grep -qE "AC powered: true|USB powered: true|Wireless powered: true"; then
    charging_flag="true"
    charging_status="⚡"
  fi

  # 设备显示名
  CLEAN_DEVICE_MODEL="$(printf "%s" "$device_model" | tr -d '\r')"

  # 最终文本（包含换行），随后 json_escape 成 \\n
  final_app_name="电量:${battery_level}%${charging_status}
应用:${app_name}"

  # JSON 里必须转义
  js_secret="$(json_escape "$SECRET")"
  js_id="$(json_escape "$DEVICE_ID")"
  js_show_name="$(json_escape "$CLEAN_DEVICE_MODEL")"
  js_app_name="$(json_escape "$final_app_name")"
  js_app_name_only="$(json_escape "$app_name")"
  js_pkg="$(json_escape "$PACKAGE_NAME")"

  response_file="${SCRIPT_DIR}/curl_response.txt"
  error_file="${SCRIPT_DIR}/curl_error.txt"

  http_code="$(curl -s -w "%{http_code}" -o "$response_file" \
    --connect-timeout 20 \
    --max-time 35 \
    -X POST \
    -H "Content-Type: application/json" \
    -H "User-Agent: DeviceStatusMonitor/1.0" \
    -d "{
      \"secret\":\"${js_secret}\",
      \"id\":\"${js_id}\",
      \"show_name\":\"${js_show_name}\",
      \"using\":${using},
      \"app_name\":\"${js_app_name}\",
      \"app_name_only\":\"${js_app_name_only}\",
      \"app_pkg\":\"${js_pkg}\"
    }" \
    "$URL" 2>"$error_file")"

  # 记录请求结果
  response_content=""
  [ -f "$response_file" ] && response_content="$(tr -d '\r\n' < "$response_file" 2>/dev/null | head -c 300)"

  if [ "$http_code" = "200" ]; then
    log "设备状态已同步: ${app_name} (电量:${battery_level}%${charging_status})"
  else
    error_content=""
    if [ -f "$error_file" ] && [ -s "$error_file" ]; then
      error_content="$(tr -d '\r\n' < "$error_file" 2>/dev/null | head -c 300)"
    fi

    if [ -n "$error_content" ]; then
      log "设备状态请求失败[HTTP $http_code]: curl错误: $error_content, 服务器响应: $response_content"
    else
      log "设备状态请求失败[HTTP $http_code]: 服务器响应: $response_content"
    fi
  fi

  rm -f "$response_file" "$error_file" 2>/dev/null
}

# ===================== 设置全局状态 =====================
set_global_status() {
  status_code="$1"

  response_file="${SCRIPT_DIR}/status_response.txt"
  error_file="${SCRIPT_DIR}/status_error.txt"

  http_code="$(curl -s -w "%{http_code}" -o "$response_file" \
    --connect-timeout 20 \
    --max-time 35 \
    -H "Sleepy-Secret: ${SECRET}" \
    "${BASE_URL}/status/set?status=${status_code}" 2>"$error_file")"

  resp=""
  [ -f "$response_file" ] && resp="$(tr -d '\r\n' < "$response_file" 2>/dev/null | head -c 300)"

  if [ "$http_code" = "200" ]; then
    log "全局状态已设置: status=${status_code}"
  else
    err=""
    [ -s "$error_file" ] && err="$(tr -d '\r\n' < "$error_file" 2>/dev/null | head -c 300)"
    log "设置全局状态失败[HTTP $http_code]: $err, resp=$resp"
  fi

  rm -f "$response_file" "$error_file" 2>/dev/null
}

# ===================== 主流程 =====================
LAST_PACKAGE=""
: > "$LOG_PATH"
log "===== 服务启动 ====="

device_model="$(getprop ro.product.model 2>/dev/null)"
android_version="$(getprop ro.build.version.release 2>/dev/null)"
log "设备: ${device_model}, Android ${android_version}"

if [ -n "$DEVICE_NAME" ]; then
  device_model="$DEVICE_NAME"
  log "使用自定义设备名: ${device_model}"
fi

sleep 3
log "开始监控应用状态..."
is_sleep_status_set="false"

while true; do
  isLock="$(dumpsys window policy 2>/dev/null | grep -o 'showing=[a-z]*' | head -1 | cut -d= -f2)"

  if [ "$isLock" = "true" ]; then
    sleepy=$((sleepy + 1))
    PACKAGE_NAME="NotificationShade"
    using="false"

    if [ "$is_sleep_status_set" = "false" ]; then
      # 1 = 似了
      set_global_status 1
      is_sleep_status_set="true"
    fi
  else
    sleepy=0
    using="true"

    CURRENT_FOCUS="$(dumpsys activity activities 2>/dev/null | grep -m 1 'ResumedActivity')"
    PACKAGE_NAME="$(echo "$CURRENT_FOCUS" | sed -E 's/.*u0 ([^/]+).*/\1/')"

    if [ "$is_sleep_status_set" = "true" ]; then
      # 0 = 活着
      set_global_status 0
      log "全局状态已恢复为: 活着"
      is_sleep_status_set="false"
    fi
  fi

  if [ -n "$PACKAGE_NAME" ] && [ "$PACKAGE_NAME" != "$LAST_PACKAGE" ]; then
    send_device_status "$PACKAGE_NAME"
    LAST_PACKAGE="$PACKAGE_NAME"
  fi

  sleep_sec="$(get_interval_seconds "$PACKAGE_NAME")"
  sleep "$sleep_sec"
done
